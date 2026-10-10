//! Shared MFT parsing; FSCTL records are restored, raw records require USA fixups first.
#[path = "mft_bulk.rs"]
mod bulk;
pub use bulk::scan_mft_bulk;
use std::collections::{HashMap, HashSet};
use std::ffi::OsString;
use std::fs::{File, OpenOptions};
use std::os::windows::{ffi::OsStringExt, fs::OpenOptionsExt, io::AsRawHandle};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Instant;
use windows_sys::Win32::System::IO::DeviceIoControl;

use super::models::ScanReport;
use super::usn_scanner::{verify_entries, FileEntry};
use super::{entry_info, Collector, EventFn};

const FSCTL_GET_NTFS_VOLUME_DATA: u32 = 0x00090064;
const FSCTL_GET_NTFS_FILE_RECORD: u32 = 0x00090068;
const INDEX_MASK: u64 = 0x0000_ffff_ffff_ffff;

struct ParsedRecord {
    id: u64,
    base: u64,
    is_dir: bool,
    name: Option<FileEntry>,
    name_omitted: bool,
    size: Option<u64>,
}

#[derive(Default)]
struct RecordIndex {
    counts: super::models::MftRecordCounts,
    entries: HashMap<u64, FileEntry>,
    nameless: HashMap<u64, bool>,
    extensions: HashMap<u64, FileEntry>,
    min_size: Option<u64>,
    filtered: HashSet<u64>,
    small_nameless: HashSet<u64>,
}

impl RecordIndex {
    fn insert(&mut self, record: ParsedRecord) {
        if record.base != 0 {
            self.counts.extension_records += 1;
            if let Some(name) = record.name {
                self.extensions.entry(record.base).or_insert(name);
            }
        } else {
            self.counts.base_records += 1;
            let small = !record.is_dir
                && self
                    .min_size
                    .zip(record.size)
                    .is_some_and(|(min, size)| size < min);
            if small && record.name_omitted {
                self.filtered.insert(record.id);
            } else if let Some(name) = record.name {
                if small {
                    // Keep the full reference to distinguish extensions from reused record slots.
                    self.filtered.insert(record.id);
                } else {
                    self.entries.insert(record.id, name);
                }
            } else {
                self.nameless.insert(record.id, record.is_dir);
                if small {
                    self.small_nameless.insert(record.id);
                }
            }
        }
    }

    fn finish(mut self, report: &mut ScanReport) -> HashMap<u64, FileEntry> {
        for (base, mut name) in self.extensions {
            if self.entries.contains_key(&base) || self.filtered.contains(&base) {
                continue;
            }
            if let Some(is_dir) = self.nameless.remove(&base) {
                // Extension headers do not define the base file's directory type.
                name.is_dir = is_dir;
                if self.small_nameless.contains(&base) {
                    self.filtered.insert(base);
                } else {
                    self.entries.insert(base, name);
                }
            } else {
                report.issue(
                    Path::new(&format!("file-reference:{base:#x}")),
                    "mft_base_missing",
                    "扩展记录对应的基础记录缺失或解析失败，未将扩展记录当作独立文件",
                );
            }
        }
        for (id, _) in self.nameless {
            report.issue(
                Path::new(&format!("file-reference:{id:#x}")),
                "mft_name_missing",
                "基础记录及扩展记录均未提供可用文件名",
            );
        }
        report.summary.size_filtered = self.filtered.len() as u64;
        self.counts.logical_entries = (self.entries.len() + self.filtered.len()) as u64;
        report.summary.mft_records = Some(self.counts);
        self.entries
    }
}

fn control(file: &File, code: u32, input: &[u8], output: &mut [u8]) -> Result<usize, String> {
    let mut returned = 0;
    let ok = unsafe {
        DeviceIoControl(
            file.as_raw_handle(),
            code,
            input.as_ptr() as *const _,
            input.len() as u32,
            output.as_mut_ptr() as *mut _,
            output.len() as u32,
            &mut returned,
            std::ptr::null_mut(),
        )
    };
    if ok == 0 {
        return Err(std::io::Error::last_os_error().to_string());
    }
    if returned as usize > output.len() {
        return Err("MFT 返回长度超出缓冲区".into());
    }
    Ok(returned as usize)
}

fn decode_response(output: &[u8], requested: u64) -> Result<(u64, &[u8]), String> {
    if output.len() < 12 {
        return Err("MFT 返回头不完整".into());
    }
    let index = u64::from_le_bytes(output[..8].try_into().unwrap()) & INDEX_MASK;
    let len = u32::from_le_bytes(output[8..12].try_into().unwrap()) as usize;
    if index > requested {
        return Err("MFT 枚举未向前推进".into());
    }
    let record = output.get(12..12 + len).ok_or("MFT 记录长度越界")?;
    Ok((index, record))
}

#[cfg(test)]
fn parse_names(record: &[u8], index: u64) -> Result<Option<ParsedRecord>, String> {
    parse_names_with_min(record, index, None)
}

fn parse_names_with_min(
    record: &[u8],
    index: u64,
    min_size: Option<u64>,
) -> Result<Option<ParsedRecord>, String> {
    if record.len() < 48 || &record[..4] != b"FILE" {
        return Err("无效 MFT 记录头".into());
    }
    // Sector tails must already be restored, by NTFS or the raw reader.
    let usa = u16::from_le_bytes(record[4..6].try_into().unwrap()) as usize;
    let count = u16::from_le_bytes(record[6..8].try_into().unwrap()) as usize;
    if count < 2 || usa + count * 2 > record.len() || !record.len().is_multiple_of(count - 1) {
        return Err("MFT 更新序列越界".into());
    }
    let stride = record.len() / (count - 1);
    if stride < 512 {
        return Err("MFT 扇区大小无效".into());
    }
    let flags = u16::from_le_bytes(record[22..24].try_into().unwrap());
    if flags & 1 == 0 {
        return Ok(None);
    }
    let sequence = u16::from_le_bytes(record[16..18].try_into().unwrap()) as u64;
    let base = u64::from_le_bytes(record[32..40].try_into().unwrap());
    let id = index | sequence << 48;
    let used = u32::from_le_bytes(record[24..28].try_into().unwrap()) as usize;
    if used > record.len() || used < 48 {
        return Err("MFT 已用长度越界".into());
    }
    let record = &record[..used];
    let mut offset = u16::from_le_bytes(record[20..22].try_into().unwrap()) as usize;
    if offset < 48 {
        return Err("MFT 属性偏移无效".into());
    }
    let mut found = None;
    let mut size = None;
    let mut uncertain_size = false;
    loop {
        let attr = record
            .get(offset..)
            .filter(|b| b.len() >= 4)
            .ok_or("MFT 属性尾不完整")?;
        let kind = u32::from_le_bytes(attr[..4].try_into().unwrap());
        if kind == u32::MAX {
            break;
        }
        if attr.len() < 24 {
            return Err("MFT 属性头不完整".into());
        }
        let len = u32::from_le_bytes(attr[4..8].try_into().unwrap()) as usize;
        if len < 24 || len > attr.len() {
            return Err("MFT 属性长度越界".into());
        }
        // Attribute lists and reparse data require handle verification, not a size guess.
        if kind == 0x20 || kind == 0xc0 {
            uncertain_size = true;
        }
        if kind == 0x80 && attr[9] == 0 {
            let value = data_size(&attr[..len])?;
            if size.is_some() {
                uncertain_size = true;
            }
            size = value;
        }
        if kind == 0x30 {
            if attr[8] != 0 {
                return Err("不支持非常驻文件名属性".into());
            }
            let size = u32::from_le_bytes(attr[16..20].try_into().unwrap()) as usize;
            let start = u16::from_le_bytes(attr[20..22].try_into().unwrap()) as usize;
            if start < 24 {
                return Err("文件名属性偏移无效".into());
            }
            let value = attr
                .get(..len)
                .and_then(|a| a.get(start..start + size))
                .filter(|b| b.len() >= 66)
                .ok_or("文件名属性越界")?;
            let name_len = value[64] as usize * 2;
            let name = value.get(66..66 + name_len).ok_or("文件名长度越界")?;
            if value[65] != 2 && found.is_none() {
                if name.is_empty()
                    || name
                        .chunks_exact(2)
                        .any(|b| [0, 47, 92, 58].contains(&u16::from_le_bytes([b[0], b[1]])))
                    || name == [46, 0, 46, 0]
                    || (name == [46, 0] && (if base == 0 { id } else { base } & INDEX_MASK) != 5)
                {
                    return Err("无效文件名组件".into());
                }
                found = Some((name, u64::from_le_bytes(value[..8].try_into().unwrap())));
            }
        }
        offset += len;
    }
    let size = if uncertain_size { None } else { size };
    // Decide only after all attributes are validated; extensions still need their names.
    let name_omitted = base == 0
        && flags & 2 == 0
        && found.is_some()
        && min_size.zip(size).is_some_and(|(min, size)| size < min);
    let name = if name_omitted {
        None
    } else {
        found.map(|(bytes, parent_ref)| {
            let mut wide = [0u16; 255];
            for (out, b) in wide.iter_mut().zip(bytes.chunks_exact(2)) {
                *out = u16::from_le_bytes([b[0], b[1]]);
            }
            FileEntry {
                name: OsString::from_wide(&wide[..bytes.len() / 2]),
                parent_ref,
                is_dir: flags & 2 != 0,
            }
        })
    };
    Ok(Some(ParsedRecord {
        id,
        base,
        is_dir: flags & 2 != 0,
        name,
        name_omitted,
        size,
    }))
}

fn data_size(attr: &[u8]) -> Result<Option<u64>, String> {
    if attr.len() < 24 {
        return Err("数据属性头不完整".into());
    }
    match attr[8] {
        0 => {
            let size = u32::from_le_bytes(attr[16..20].try_into().unwrap()) as usize;
            let start = u16::from_le_bytes(attr[20..22].try_into().unwrap()) as usize;
            if start < 24 || start.checked_add(size).is_none_or(|end| end > attr.len()) {
                return Err("常驻数据越界".into());
            }
            Ok(Some(size as u64))
        }
        1 => {
            if attr.len() < 64 {
                return Err("非常驻数据头不完整".into());
            }
            let first_vcn = u64::from_le_bytes(attr[16..24].try_into().unwrap());
            let size = i64::from_le_bytes(attr[48..56].try_into().unwrap());
            if size < 0 {
                return Err("数据长度为负数".into());
            }
            Ok((first_vcn == 0).then_some(size as u64))
        }
        _ => Err("数据属性驻留标记无效".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn deferred_name_allocation_preserves_filtering_and_validation() {
        let mut bytes = sample_record();
        bytes[24..28].copy_from_slice(&220u32.to_le_bytes());
        bytes[152..156].copy_from_slice(&0x80u32.to_le_bytes());
        bytes[156..160].copy_from_slice(&64u32.to_le_bytes());
        bytes[160] = 1;
        bytes[200..208].copy_from_slice(&63i64.to_le_bytes());
        bytes[216..220].copy_from_slice(&u32::MAX.to_le_bytes());
        let parsed = parse_names_with_min(&bytes, 9, Some(64)).unwrap().unwrap();
        assert!(parsed.name_omitted && parsed.name.is_none());
        let mut index = RecordIndex {
            min_size: Some(64),
            ..Default::default()
        };
        index.insert(parsed);
        let mut report = ScanReport::new("mft_bulk");
        assert!(index.finish(&mut report).is_empty());
        assert_eq!(report.summary.size_filtered, 1);
        assert!(report.summary.issues.is_empty());
        for min in [None, Some(63)] {
            let parsed = parse_names_with_min(&bytes, 9, min).unwrap().unwrap();
            assert!(parsed.name.is_some() && !parsed.name_omitted);
        }
        bytes[22..24].copy_from_slice(&3u16.to_le_bytes());
        assert!(parse_names_with_min(&bytes, 9, Some(64))
            .unwrap()
            .unwrap()
            .name
            .is_some());
        bytes[22..24].copy_from_slice(&1u16.to_le_bytes());
        bytes[32..40].copy_from_slice(&(10u64 | 7 << 48).to_le_bytes());
        assert!(parse_names_with_min(&bytes, 9, Some(64))
            .unwrap()
            .unwrap()
            .name
            .is_some());
        bytes[32..40].fill(0);
        bytes[24..28].copy_from_slice(&244u32.to_le_bytes());
        bytes[216..220].copy_from_slice(&0x20u32.to_le_bytes());
        bytes[220..224].copy_from_slice(&24u32.to_le_bytes());
        bytes[240..244].copy_from_slice(&u32::MAX.to_le_bytes());
        let parsed = parse_names_with_min(&bytes, 9, Some(64)).unwrap().unwrap();
        assert!(parsed.size.is_none() && parsed.name.is_some());
        bytes[146..148].copy_from_slice(&47u16.to_le_bytes());
        assert!(parse_names_with_min(&bytes, 9, Some(64)).is_err());
    }
    #[test]
    fn early_filter_preserves_directories_unknown_sizes_extensions_and_counts() {
        for reverse in [false, true] {
            let mut records = Vec::new();
            for (id, size, dir, named) in [
                (10, Some(63), false, true),
                (11, Some(64), false, true),
                (12, None, false, true),
                (13, Some(0), true, true),
                (14, Some(1), false, false),
                (15, Some(1), false, false),
            ] {
                let mut r = parse_names(&sample_record(), id).unwrap().unwrap();
                r.size = size;
                r.is_dir = dir;
                if let Some(name) = r.name.as_mut() {
                    name.is_dir = dir;
                }
                if !named {
                    r.name = None;
                }
                records.push(r);
            }
            for (id, base) in [(100, 10), (101, 14)] {
                let mut r = parse_names(&sample_record(), id).unwrap().unwrap();
                r.base = base | 7 << 48;
                records.push(r);
            }
            if reverse {
                records.reverse();
            }
            let mut index = RecordIndex {
                min_size: Some(64),
                ..Default::default()
            };
            for r in records {
                index.insert(r);
            }
            assert!(!index.entries.contains_key(&(10 | 7 << 48)));
            let mut report = ScanReport::new("mft_fast");
            let entries = index.finish(&mut report);
            assert_eq!(entries.len(), 3);
            for id in [11, 12, 13] {
                assert!(entries.contains_key(&(id | 7 << 48)));
            }
            assert!(entries[&(13 | 7 << 48)].is_dir);
            assert_eq!(report.summary.size_filtered, 2);
            let counts = report.summary.mft_records.unwrap();
            assert_eq!(
                (
                    counts.base_records,
                    counts.extension_records,
                    counts.logical_entries
                ),
                (6, 2, 5)
            );
            assert_eq!(report.summary.issues.len(), 1);
            assert_eq!(report.summary.issues[0].stage, "mft_name_missing");
        }
    }
    #[test]
    fn data_sizes_use_unnamed_stream_and_fall_back_for_complex_records() {
        let mut record = sample_record();
        record[24..28].copy_from_slice(&220u32.to_le_bytes());
        record[152..156].copy_from_slice(&0x80u32.to_le_bytes());
        record[156..160].copy_from_slice(&64u32.to_le_bytes());
        record[160] = 1;
        record[200..208].copy_from_slice(&(20i64 << 30).to_le_bytes());
        record[216..220].copy_from_slice(&u32::MAX.to_le_bytes());
        assert_eq!(
            parse_names(&record, 9).unwrap().unwrap().size,
            Some(20 << 30)
        );
        record[161] = 3; // Named stream does not define ordinary file size.
        assert_eq!(parse_names(&record, 9).unwrap().unwrap().size, None);
        record[161] = 0;
        record[168..176].copy_from_slice(&1u64.to_le_bytes());
        assert_eq!(parse_names(&record, 9).unwrap().unwrap().size, None);
        record[168..176].fill(0);
        record[24..28].copy_from_slice(&244u32.to_le_bytes());
        record[216..220].copy_from_slice(&0x20u32.to_le_bytes());
        record[220..224].copy_from_slice(&24u32.to_le_bytes());
        record[240..244].copy_from_slice(&u32::MAX.to_le_bytes());
        assert_eq!(parse_names(&record, 9).unwrap().unwrap().size, None);
        record[200..208].copy_from_slice(&(-1i64).to_le_bytes());
        assert!(parse_names(&record, 9).is_err());
        let mut attr = vec![0; 32];
        attr[16..20].copy_from_slice(&8u32.to_le_bytes());
        attr[20..22].copy_from_slice(&24u16.to_le_bytes());
        assert_eq!(data_size(&attr).unwrap(), Some(8));
        attr[16..20].copy_from_slice(&9u32.to_le_bytes());
        assert!(data_size(&attr).is_err());
    }
    fn sample_record() -> Vec<u8> {
        let mut record = vec![0; 1024];
        record[..4].copy_from_slice(b"FILE");
        record[4..6].copy_from_slice(&48u16.to_le_bytes());
        record[6..8].copy_from_slice(&3u16.to_le_bytes());
        record[16..18].copy_from_slice(&7u16.to_le_bytes());
        record[20..22].copy_from_slice(&56u16.to_le_bytes());
        record[22..24].copy_from_slice(&1u16.to_le_bytes());
        record[24..28].copy_from_slice(&156u32.to_le_bytes());
        record[56..60].copy_from_slice(&0x30u32.to_le_bytes());
        record[60..64].copy_from_slice(&96u32.to_le_bytes());
        record[72..76].copy_from_slice(&70u32.to_le_bytes());
        record[76..78].copy_from_slice(&24u16.to_le_bytes());
        record[80..88].copy_from_slice(&(5u64 | 3 << 48).to_le_bytes());
        record[144] = 2;
        record[145] = 1;
        record[146..148].copy_from_slice(&0x4e2du16.to_le_bytes());
        record[148..150].copy_from_slice(&0xd800u16.to_le_bytes());
        record[152..156].copy_from_slice(&u32::MAX.to_le_bytes());
        record
    }

    #[test]
    fn fsctl_record_is_already_restored_and_must_not_be_fixed_up_again() {
        let mut record = sample_record();
        record[24..28].copy_from_slice(&572u32.to_le_bytes());
        record[60..64].copy_from_slice(&512u32.to_le_bytes());
        record[72..76].copy_from_slice(&482u32.to_le_bytes());
        record[144] = 208;
        for i in 0..208 {
            record[146 + i * 2..148 + i * 2].copy_from_slice(&88u16.to_le_bytes());
        }
        record[568..572].copy_from_slice(&u32::MAX.to_le_bytes());
        record[48..50].copy_from_slice(&88u16.to_le_bytes());
        record[50..52].copy_from_slice(&0x3333u16.to_le_bytes());
        record[1022..1024].copy_from_slice(&0x2222u16.to_le_bytes());
        let parsed = parse_names(&record, 9).unwrap().unwrap();
        use std::os::windows::ffi::OsStrExt;
        assert_eq!(
            parsed.name.unwrap().name.encode_wide().collect::<Vec<_>>(),
            vec![88; 208]
        );
    }

    #[test]
    #[ignore = "requires FSCTL records captured by the administrator diagnostic"]
    fn captured_fsctl_parent_records_parse() {
        let dir = std::env::var_os("C_MANAGER_MFT_RECORD_DIR").expect("record directory");
        let mut count = 0;
        for entry in std::fs::read_dir(dir).unwrap() {
            let entry = entry.unwrap();
            let name = entry.file_name().to_string_lossy().to_string();
            if !name.starts_with("mft-record-") || !name.ends_with(".bin") {
                continue;
            }
            let requested: u64 = name
                .trim_start_matches("mft-record-")
                .trim_end_matches(".bin")
                .parse()
                .unwrap();
            let bytes = std::fs::read(entry.path()).unwrap();
            let (index, record) = decode_response(&bytes, requested).unwrap();
            parse_names(record, index).unwrap_or_else(|e| panic!("record {index}: {e}"));
            count += 1;
        }
        assert!(count > 0);
        println!("validated {count} captured FSCTL records");
    }

    #[test]
    fn extension_must_not_override_base_directory_type() {
        let mut base = sample_record();
        base[22..24].copy_from_slice(&3u16.to_le_bytes());
        let mut extension = sample_record();
        extension[32..40].copy_from_slice(&(9u64 | 7 << 48).to_le_bytes());
        for records in [
            [(100, extension.clone()), (9, base.clone())],
            [(9, base), (100, extension)],
        ] {
            let mut index = RecordIndex::default();
            for (number, record) in records {
                index.insert(parse_names(&record, number).unwrap().unwrap());
            }
            let mut report = ScanReport::new("mft");
            let entries = index.finish(&mut report);
            assert!(report.summary.issues.is_empty());
            assert_eq!(entries.len(), 1);
            assert!(
                entries[&(9 | 7 << 48)].is_dir,
                "extension swallowed the authoritative base directory"
            );
        }
    }

    #[test]
    fn record_bounds_sequences_and_unicode_are_checked() {
        let mut record = sample_record();
        let parsed = parse_names(&record, 9).unwrap().unwrap();
        assert_eq!(parsed.id, 9 | 7 << 48);
        let entry = parsed.name.unwrap();
        assert_eq!(entry.parent_ref, 5 | 3 << 48);
        use std::os::windows::ffi::OsStrExt;
        assert_eq!(
            entry.name.encode_wide().collect::<Vec<_>>(),
            [0x4e2d, 0xd800]
        );
        for len in 0..record.len() {
            assert!(parse_names(&record[..len], 9).is_err());
        }
        record[60..64].copy_from_slice(&0u32.to_le_bytes());
        assert!(parse_names(&record, 9).is_err());
        let mut output = 9u64.to_le_bytes().to_vec();
        output.extend(1024u32.to_le_bytes());
        output.extend(record);
        assert!(decode_response(&output, 8).is_err());
        assert!(decode_response(&output[..20], 9).is_err());
        assert_eq!(decode_response(&output, 10).unwrap().0, 9);
    }

    #[test]
    fn extension_names_require_a_matching_base_and_inherit_its_type() {
        let mut base = sample_record();
        base[22..24].copy_from_slice(&3u16.to_le_bytes());
        base[56..60].copy_from_slice(&u32::MAX.to_le_bytes());
        let mut ext = sample_record();
        ext[32..40].copy_from_slice(&(9u64 | 7 << 48).to_le_bytes());
        for sequence in [7u16, 8u16] {
            base[16..18].copy_from_slice(&sequence.to_le_bytes());
            let mut index = RecordIndex::default();
            index.insert(parse_names(&ext, 100).unwrap().unwrap());
            index.insert(parse_names(&base, 9).unwrap().unwrap());
            let mut report = ScanReport::new("mft");
            let entries = index.finish(&mut report);
            let counts = report.summary.mft_records.unwrap();
            assert_eq!(counts.base_records, 1);
            assert_eq!(counts.extension_records, 1);
            if sequence == 7 {
                assert!(entries[&(9 | 7 << 48)].is_dir);
                assert!(report.summary.issues.is_empty());
            } else {
                assert!(entries.is_empty());
                assert!(report
                    .summary
                    .issues
                    .iter()
                    .any(|i| i.stage == "mft_base_missing"));
                assert!(report
                    .summary
                    .issues
                    .iter()
                    .any(|i| i.stage == "mft_name_missing"));
            }
        }
    }
}
