//! USN enumeration retained for explicit benchmarks; the application scans directory paths.
use std::collections::{HashMap, HashSet};
use std::ffi::OsString;
use std::os::windows::ffi::{OsStrExt, OsStringExt};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Instant;
use std::{mem, ptr};

use rayon::prelude::*;
use windows_sys::Win32::Foundation::{
    CloseHandle, GetLastError, ERROR_HANDLE_EOF, ERROR_MORE_DATA, HANDLE, INVALID_HANDLE_VALUE,
};
use windows_sys::Win32::Storage::FileSystem::{
    CreateFileW, FindClose, FindFirstFileNameW, FindNextFileNameW, FILE_SHARE_DELETE,
    FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING,
};
use windows_sys::Win32::System::IO::DeviceIoControl;

use super::models::ScanReport;
use super::{entry_info, record_file, Collector, EventFn};

const FSCTL_ENUM_USN_DATA: u32 = 0x000900b3;

#[repr(C)]
struct MftEnumDataV0 {
    start_file_reference_number: u64,
    low_usn: i64,
    high_usn: i64,
}

struct FileEntry {
    name: OsString,
    parent_ref: u64,
    is_dir: bool,
}

fn parse_records(
    buffer: &[u8],
    entries: &mut HashMap<u64, FileEntry>,
) -> Result<(u64, u64), String> {
    if buffer.len() < 8 {
        return Err("USN response is missing its continuation reference".into());
    }
    let next = u64::from_le_bytes(buffer[..8].try_into().unwrap());
    let mut offset = 8;
    let mut count = 0;
    while offset < buffer.len() {
        let bytes = &buffer[offset..];
        if bytes.len() < 8 {
            return Err("Truncated USN header".into());
        }
        let len = u32::from_le_bytes(bytes[..4].try_into().unwrap()) as usize;
        let version = u16::from_le_bytes(bytes[4..6].try_into().unwrap());
        if version != 2 {
            return Err(format!("Unsupported USN major version: {version}"));
        }
        if len < 60 || len > bytes.len() || !len.is_multiple_of(8) {
            return Err("Invalid USN record length".into());
        }
        let bytes = &bytes[..len];
        let name_len = u16::from_le_bytes(bytes[56..58].try_into().unwrap()) as usize;
        let name_offset = u16::from_le_bytes(bytes[58..60].try_into().unwrap()) as usize;
        if name_len == 0
            || !name_len.is_multiple_of(2)
            || name_offset < 60
            || !name_offset.is_multiple_of(2)
            || name_offset
                .checked_add(name_len)
                .is_none_or(|end| end > len)
        {
            return Err("Invalid USN filename bounds".into());
        }
        let name: Vec<u16> = bytes[name_offset..name_offset + name_len]
            .chunks_exact(2)
            .map(|b| u16::from_le_bytes([b[0], b[1]]))
            .collect();
        let id = u64::from_le_bytes(bytes[8..16].try_into().unwrap());
        let parent_ref = u64::from_le_bytes(bytes[16..24].try_into().unwrap());
        if name
            .iter()
            .any(|c| [0, b'\\' as u16, b'/' as u16, b':' as u16].contains(c))
            || name == [46, 46]
            || (name == [46] && id != parent_ref)
        {
            return Err("Invalid USN filename component".into());
        }
        let attributes = u32::from_le_bytes(bytes[52..56].try_into().unwrap());
        entries.insert(
            id,
            FileEntry {
                name: OsString::from_wide(&name),
                parent_ref,
                is_dir: attributes & 0x10 != 0,
            },
        );
        count += 1;
        offset += len;
    }
    Ok((next, count))
}

fn build_path(
    id: u64,
    entries: &HashMap<u64, FileEntry>,
    cache: &mut HashMap<u64, PathBuf>,
) -> Result<PathBuf, String> {
    let mut current = id;
    let mut chain = Vec::new();
    let mut visited = HashSet::new();
    let mut path = loop {
        if let Some(path) = cache.get(&current) {
            break path.clone();
        }
        if !visited.insert(current) {
            return Err(format!("Parent cycle at file reference {current:#x}"));
        }
        let entry = entries
            .get(&current)
            .ok_or_else(|| format!("Missing parent reference {current:#x}"))?;
        if current != id && !entry.is_dir {
            return Err("Parent reference is not a directory".into());
        }
        chain.push((current, entry));
        current = entry.parent_ref;
    };
    for (id, entry) in chain.into_iter().rev() {
        path.push(&entry.name);
        if entry.is_dir {
            cache.insert(id, path.clone());
        }
    }
    Ok(path)
}

fn hard_link_paths(path: &Path, drive: &str) -> std::io::Result<Vec<PathBuf>> {
    let native_path = path.canonicalize()?;
    let wide: Vec<u16> = native_path
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect();
    let mut buffer = vec![0u16; 1024];
    let handle = loop {
        let mut length = buffer.len() as u32;
        let handle =
            unsafe { FindFirstFileNameW(wide.as_ptr(), 0, &mut length, buffer.as_mut_ptr()) };
        if handle != INVALID_HANDLE_VALUE {
            break handle;
        }
        let error = unsafe { GetLastError() };
        if error == ERROR_MORE_DATA && length as usize > buffer.len() {
            buffer.resize(length as usize, 0);
        } else {
            return Err(std::io::Error::from_raw_os_error(error as i32));
        }
    };
    struct FindGuard(HANDLE);
    impl Drop for FindGuard {
        fn drop(&mut self) {
            unsafe {
                FindClose(self.0);
            }
        }
    }
    let _guard = FindGuard(handle);
    let mut paths = Vec::new();
    loop {
        let end = buffer
            .iter()
            .position(|c| *c == 0)
            .ok_or_else(|| std::io::Error::other("Unterminated hard-link path"))?;
        if buffer.first() != Some(&(b'\\' as u16)) {
            return Err(std::io::Error::other(
                "Hard-link path is not volume-relative",
            ));
        }
        let mut path = OsString::from(drive);
        path.push(OsString::from_wide(&buffer[..end]));
        paths.push(PathBuf::from(path));
        loop {
            let mut length = buffer.len() as u32;
            if unsafe { FindNextFileNameW(handle, &mut length, buffer.as_mut_ptr()) } != 0 {
                break;
            }
            let error = unsafe { GetLastError() };
            if error == ERROR_HANDLE_EOF {
                paths.sort();
                paths.dedup();
                return Ok(paths);
            }
            if error == ERROR_MORE_DATA && length as usize > buffer.len() {
                buffer.resize(length as usize, 0);
            } else {
                return Err(std::io::Error::from_raw_os_error(error as i32));
            }
        }
    }
}

pub fn scan_usn(
    drive_letter: &str,
    min_size_bytes: u64,
    cancel: &AtomicBool,
    on_event: &Option<EventFn>,
) -> Result<ScanReport, String> {
    if drive_letter.len() != 2
        || !drive_letter.as_bytes()[0].is_ascii_alphabetic()
        || drive_letter.as_bytes()[1] != b':'
    {
        return Err("USN requires a drive letter such as C:".into());
    }
    let collector = Mutex::new(Collector::new("usn", on_event));
    if cancel.load(Ordering::Relaxed) {
        return Ok(collector.into_inner().unwrap().finish(cancel));
    }
    let root = PathBuf::from(format!("{drive_letter}\\"));
    let root_info = entry_info(&root).map_err(|e| e.to_string())?;
    let volume_path: Vec<u16> = format!("\\\\.\\{drive_letter}")
        .encode_utf16()
        .chain(Some(0))
        .collect();
    let handle = unsafe {
        CreateFileW(
            volume_path.as_ptr(),
            0x80000000,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            ptr::null(),
            OPEN_EXISTING,
            0,
            ptr::null_mut(),
        )
    };
    if handle == INVALID_HANDLE_VALUE {
        return Err(format!(
            "无法打开 USN 卷（需要管理员权限）: {}",
            std::io::Error::last_os_error()
        ));
    }
    struct HandleGuard(HANDLE);
    impl Drop for HandleGuard {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.0);
            }
        }
    }
    let _guard = HandleGuard(handle);
    let mut entries = HashMap::new();
    let mut input = MftEnumDataV0 {
        start_file_reference_number: 0,
        low_usn: 0,
        high_usn: i64::MAX,
    };
    let mut buffer = vec![0u8; 128 * 1024];
    loop {
        if cancel.load(Ordering::Relaxed) {
            return Ok(collector.into_inner().unwrap().finish(cancel));
        }
        let started = Instant::now();
        let mut bytes_returned = 0;
        let ok = unsafe {
            DeviceIoControl(
                handle,
                FSCTL_ENUM_USN_DATA,
                &input as *const _ as *const _,
                mem::size_of_val(&input) as u32,
                buffer.as_mut_ptr() as *mut _,
                buffer.len() as u32,
                &mut bytes_returned,
                ptr::null_mut(),
            )
        };
        let mut chunk = ScanReport::new("usn");
        chunk.summary.timings.enumeration_ms = started.elapsed().as_secs_f64() * 1000.0;
        if ok == 0 {
            let error = unsafe { GetLastError() };
            if error != ERROR_HANDLE_EOF {
                chunk.issue(
                    &root,
                    "usn_enumeration",
                    std::io::Error::from_raw_os_error(error as i32),
                );
            }
            collector.lock().unwrap().merge(chunk);
            break;
        }
        match buffer
            .get(..bytes_returned as usize)
            .ok_or_else(|| "USN response exceeds buffer".to_string())
            .and_then(|b| parse_records(b, &mut entries))
        {
            Ok((next, count)) => {
                chunk.summary.entries_scanned = count;
                if next <= input.start_file_reference_number {
                    chunk.issue(&root, "usn_enumeration", "USN continuation did not advance");
                    collector.lock().unwrap().merge(chunk);
                    break;
                }
                input.start_file_reference_number = next;
            }
            Err(error) => {
                chunk.issue(&root, "usn_parse", error);
                collector.lock().unwrap().merge(chunk);
                break;
            }
        }
        collector.lock().unwrap().merge(chunk);
    }

    let mut cache = HashMap::from([(root_info.identity.1, root.clone())]);
    let mut files = Vec::new();
    for (&id, entry) in &entries {
        if cancel.load(Ordering::Relaxed) {
            return Ok(collector.into_inner().unwrap().finish(cancel));
        }
        if entry.is_dir {
            continue;
        }
        let start = Instant::now();
        let path = build_path(id, &entries, &mut cache);
        let mut chunk = ScanReport::new("usn");
        chunk.summary.timings.path_ms = start.elapsed().as_secs_f64() * 1000.0;
        match path {
            Ok(path) => files.push((id, path)),
            Err(error) => chunk.issue(
                Path::new(&format!("file-reference:{id:#x}")),
                "path_resolution",
                error,
            ),
        }
        collector.lock().unwrap().merge(chunk);
    }
    drop(cache);
    drop(entries);
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(4)
        .build()
        .map_err(|e| e.to_string())?;
    pool.install(|| {
        files.par_chunks(256).for_each(|files| {
            let mut chunk = ScanReport::new("usn");
            for (id, path) in files {
                if cancel.load(Ordering::Relaxed) {
                    break;
                }
                let started = Instant::now();
                match entry_info(path) {
                    Err(error) => chunk.issue(path, "metadata", error),
                    Ok(info) if info.identity != (root_info.identity.0, *id) || info.is_dir => {
                        chunk.issue(path, "file_changed", "文件标识或类型已改变，原记录大小未知");
                    }
                    Ok(info) => {
                        if info.links > 1 && !info.is_link {
                            match hard_link_paths(path, drive_letter) {
                                Ok(paths) => {
                                    if paths.len() != info.links as usize {
                                        chunk.issue(
                                            path,
                                            "hard_links",
                                            "硬链接数量在扫描期间发生变化",
                                        );
                                    }
                                    for alias in paths {
                                        record_file(&alias, &info, min_size_bytes, &mut chunk);
                                    }
                                }
                                Err(error) => {
                                    chunk.issue(path, "hard_links", error);
                                    record_file(path, &info, min_size_bytes, &mut chunk);
                                }
                            }
                        } else {
                            record_file(path, &info, min_size_bytes, &mut chunk);
                        }
                    }
                }
                chunk.summary.timings.metadata_ms += started.elapsed().as_secs_f64() * 1000.0;
            }
            collector.lock().unwrap().merge(chunk);
        });
    });
    Ok(collector.into_inner().unwrap().finish(cancel))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn record(id: u64, parent: u64, name: &[u16]) -> Vec<u8> {
        let len = (60 + name.len() * 2 + 7) & !7;
        let mut bytes = vec![0; len];
        bytes[..4].copy_from_slice(&(len as u32).to_le_bytes());
        bytes[4..6].copy_from_slice(&2u16.to_le_bytes());
        bytes[8..16].copy_from_slice(&id.to_le_bytes());
        bytes[16..24].copy_from_slice(&parent.to_le_bytes());
        bytes[56..58].copy_from_slice(&((name.len() * 2) as u16).to_le_bytes());
        bytes[58..60].copy_from_slice(&60u16.to_le_bytes());
        for (n, c) in name.iter().enumerate() {
            bytes[60 + n * 2..62 + n * 2].copy_from_slice(&c.to_le_bytes());
        }
        bytes
    }

    #[test]
    fn parser_checks_version_and_record_local_bounds_and_keeps_full_ids() {
        let id = 0x000a_0000_0000_0007;
        let mut bytes = 99u64.to_le_bytes().to_vec();
        bytes.extend(record(id, 5, &[0xd800, 65]));
        let mut entries = HashMap::new();
        assert_eq!(parse_records(&bytes, &mut entries).unwrap(), (99, 1));
        assert_eq!(
            entries[&id].name.encode_wide().collect::<Vec<_>>(),
            [0xd800, 65]
        );
        for len in 0..bytes.len() {
            if len != 8 {
                assert!(parse_records(&bytes[..len], &mut HashMap::new()).is_err());
            }
        }
        let mut unsupported = bytes.clone();
        unsupported[12..14].copy_from_slice(&3u16.to_le_bytes());
        assert!(parse_records(&unsupported, &mut HashMap::new()).is_err());
        let mut overrun = bytes.clone();
        overrun[64..66].copy_from_slice(&100u16.to_le_bytes());
        overrun.extend(record(9, 5, &[66; 100]));
        assert!(parse_records(&overrun, &mut HashMap::new()).is_err());
    }

    #[test]
    fn paths_are_iterative_and_reject_cycles_or_reused_parents() {
        let mut entries = HashMap::new();
        for id in 6..=206 {
            entries.insert(
                id,
                FileEntry {
                    name: OsString::from("deep"),
                    parent_ref: id - 1,
                    is_dir: true,
                },
            );
        }
        let mut cache = HashMap::from([(5, PathBuf::from("C:\\"))]);
        let path = build_path(206, &entries, &mut cache).unwrap();
        assert_eq!(path.components().count(), 203);
        entries.get_mut(&6).unwrap().parent_ref = 206;
        assert!(build_path(206, &entries, &mut HashMap::new()).is_err());
        entries.get_mut(&6).unwrap().parent_ref = 0x000a_0000_0000_0005;
        assert!(build_path(
            206,
            &entries,
            &mut HashMap::from([(5, PathBuf::from("C:\\"))])
        )
        .is_err());
    }

    #[test]
    fn hard_link_enumeration_returns_every_alias() {
        let root = super::super::tests::Fixture::new();
        let path = root.0.join("original.bin");
        std::fs::write(&path, [0; 10]).unwrap();
        let alias = root.0.join("alias.bin");
        std::fs::hard_link(&path, &alias).unwrap();
        let ordinary = path
            .to_str()
            .unwrap()
            .strip_prefix("\\\\?\\")
            .unwrap_or(path.to_str().unwrap());
        let paths = hard_link_paths(&path, &ordinary[..2]).unwrap();
        let actual: HashSet<_> = paths
            .into_iter()
            .map(|p| p.canonicalize().unwrap())
            .collect();
        assert_eq!(actual, HashSet::from([path, alias]));
    }
}
