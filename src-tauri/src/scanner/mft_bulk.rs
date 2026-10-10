#[path = "mft_io.rs"]
mod concurrent;
use super::super::models::MftBulkStats;
use super::*;
use std::io::{Read, Seek, SeekFrom};
use std::sync::mpsc::sync_channel;
use windows_sys::Win32::Storage::FileSystem::{
    FILE_FLAG_BACKUP_SEMANTICS, FILE_FLAG_OPEN_REPARSE_POINT, FILE_READ_ATTRIBUTES,
};

const GET_RETRIEVAL_POINTERS: u32 = 0x00090073;
const BLOCK_SIZE: usize = 4 * 1024 * 1024;

#[derive(Debug, PartialEq, Eq)]
struct Extent {
    start: u64,
    end: u64,
    disk: u64,
}

fn extents(
    file: &File,
    length: u64,
    cluster: u64,
    volume_bytes: u64,
    cancel: &AtomicBool,
) -> Result<Vec<Extent>, String> {
    let mut result = Vec::new();
    let mut requested = 0u64;
    let mut output = vec![0u8; 65536];
    while requested.checked_mul(cluster).ok_or("MFT VCN 溢出")? < length {
        if cancel.load(Ordering::Relaxed) {
            return Err("已取消 MFT 分段查询".into());
        }
        let mut returned = 0u32;
        let input = requested.to_le_bytes();
        let ok = unsafe {
            DeviceIoControl(
                file.as_raw_handle(),
                GET_RETRIEVAL_POINTERS,
                input.as_ptr().cast(),
                8,
                output.as_mut_ptr().cast(),
                output.len() as u32,
                &mut returned,
                std::ptr::null_mut(),
            )
        };
        if ok == 0 && std::io::Error::last_os_error().raw_os_error() != Some(234) {
            return Err(format!(
                "无法查询 $MFT 磁盘分段: {}",
                std::io::Error::last_os_error()
            ));
        }
        let b = output
            .get(..returned as usize)
            .filter(|b| b.len() >= 16)
            .ok_or("MFT 分段返回头越界")?;
        let count = u32::from_le_bytes(b[..4].try_into().unwrap()) as usize;
        if count == 0 || count > (b.len() - 16) / 16 {
            return Err("MFT 分段数量无效".into());
        }
        let first = i64::from_le_bytes(b[8..16].try_into().unwrap());
        if first < 0 || first as u64 > requested {
            return Err("MFT 分段起点不连续".into());
        }
        let previous_request = requested;
        let mut vcn = first as u64;
        for chunk in b[16..16 + count * 16].chunks_exact(16) {
            let next = i64::from_le_bytes(chunk[..8].try_into().unwrap());
            let lcn = i64::from_le_bytes(chunk[8..16].try_into().unwrap());
            if next < 0 || next as u64 <= vcn || lcn < 0 {
                return Err("不支持稀疏、压缩或无效的 MFT 分段".into());
            }
            let next = next as u64;
            if next <= requested {
                return Err("MFT 分段查询未向前推进".into());
            }
            let start = requested.checked_mul(cluster).ok_or("MFT 偏移溢出")?;
            let end = next.checked_mul(cluster).ok_or("MFT 长度溢出")?.min(length);
            let disk = (lcn as u64)
                .checked_add(requested - vcn)
                .and_then(|v| v.checked_mul(cluster))
                .ok_or("MFT 磁盘偏移溢出")?;
            if disk
                .checked_add(end - start)
                .is_none_or(|v| v > volume_bytes)
            {
                return Err("MFT 分段超出卷边界".into());
            }
            result.push(Extent { start, end, disk });
            requested = next;
            vcn = next;
            if end == length {
                return Ok(result);
            }
        }
        if requested <= previous_request {
            return Err("MFT 分段查询未推进".into());
        }
    }
    Ok(result)
}

fn restore_raw(record: &mut [u8], number: u64) -> Result<bool, String> {
    if record.iter().all(|b| *b == 0) {
        return Ok(false);
    }
    if record.len() < 48 || &record[..4] != b"FILE" {
        return Err("原始 MFT 记录签名无效".into());
    }
    let usa = u16::from_le_bytes(record[4..6].try_into().unwrap()) as usize;
    let count = u16::from_le_bytes(record[6..8].try_into().unwrap()) as usize;
    if count < 2
        || usa < 8
        || usa + count * 2 > record.len()
        || !record.len().is_multiple_of(count - 1)
    {
        return Err("原始 MFT 更新序列越界".into());
    }
    let stride = record.len() / (count - 1);
    if stride < 512 || usa + count * 2 > stride - 2 {
        return Err("原始 MFT 扇区布局无效".into());
    }
    let sequence = [record[usa], record[usa + 1]];
    for n in 1..count {
        let tail = n * stride - 2;
        if record[tail..tail + 2] != sequence {
            return Err("原始 MFT 更新序列不匹配，记录可能正在写入".into());
        }
    }
    for n in 1..count {
        let word = [record[usa + n * 2], record[usa + n * 2 + 1]];
        record[n * stride - 2..n * stride].copy_from_slice(&word);
    }
    if u16::from_le_bytes(record[22..24].try_into().unwrap()) & 1 == 0 {
        return Ok(false);
    }
    if u32::from_le_bytes(record[44..48].try_into().unwrap()) != number as u32 {
        return Err("原始 MFT 记录编号不匹配".into());
    }
    Ok(true)
}

pub fn scan_mft_bulk(
    drive: &str,
    min_size: u64,
    cancel: &AtomicBool,
    on_event: &Option<EventFn>,
) -> Result<ScanReport, String> {
    let engine = "mft_dual";
    let collector = Mutex::new(Collector::new(engine, on_event));
    if cancel.load(Ordering::Relaxed) {
        return Ok(collector.into_inner().unwrap().finish(cancel));
    }
    let root = std::path::PathBuf::from(format!("{drive}\\"));
    let root_info = entry_info(&root).map_err(|e| e.to_string())?;
    let volume = OpenOptions::new()
        .read(true)
        .share_mode(7)
        .open(format!("\\\\.\\{drive}"))
        .map_err(|e| format!("无法打开卷，需要管理员权限和 NTFS: {e}"))?;
    let mft = OpenOptions::new()
        .access_mode(FILE_READ_ATTRIBUTES)
        .share_mode(7)
        .custom_flags(FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT)
        .open(format!("\\\\?\\{drive}\\$MFT"))
        .map_err(|e| format!("无法打开 $MFT 元数据句柄: {e}；可改选原 MFT 大小筛选"))?;
    let started = Instant::now();
    let mut data = [0u8; 96];
    if control(&volume, FSCTL_GET_NTFS_VOLUME_DATA, &[], &mut data)? < 96 {
        return Err("NTFS 卷信息不完整".into());
    }
    let sector = u32::from_le_bytes(data[40..44].try_into().unwrap()) as usize;
    let cluster = u32::from_le_bytes(data[44..48].try_into().unwrap()) as u64;
    let record_size = u32::from_le_bytes(data[48..52].try_into().unwrap()) as usize;
    let valid_len = i64::from_le_bytes(data[56..64].try_into().unwrap());
    let sectors = i64::from_le_bytes(data[8..16].try_into().unwrap());
    if !(512..=65536).contains(&sector)
        || !sector.is_power_of_two()
        || cluster < sector as u64
        || !cluster.is_power_of_two()
        || !(512..=65536).contains(&record_size)
        || !record_size.is_power_of_two()
        || valid_len <= 0
        || valid_len as u64 % record_size as u64 != 0
        || sectors <= 0
    {
        return Err("不支持的 NTFS 扇区、记录大小或长度".into());
    }
    let volume_bytes = (sectors as u64)
        .checked_mul(sector as u64)
        .ok_or("卷长度溢出")?;
    let length = (valid_len as u64)
        .checked_add(sector as u64 - 1)
        .ok_or("MFT 长度溢出")?
        / sector as u64
        * sector as u64;
    let mapping = match extents(&mft, length, cluster, volume_bytes, cancel) {
        Ok(map) => map,
        Err(_) if cancel.load(Ordering::Relaxed) => {
            return Ok(collector.into_inner().unwrap().finish(cancel))
        }
        Err(e) => return Err(e),
    };
    let mut index = RecordIndex {
        min_size: Some(min_size),
        ..Default::default()
    };
    let mut chunk = ScanReport::new(engine);
    chunk.summary.timings.enumeration_ms = started.elapsed().as_secs_f64() * 1000.0;
    // Live raw reads can lag cached NTFS metadata even when every sector passes USA checks.
    chunk.issue(
        &root,
        "raw_mft_consistency",
        "实验性原始 MFT 批量读取：非快照，磁盘记录可能滞后于系统缓存，扫描期间变化尚未补查",
    );
    let mut api_buffer = vec![0u8; record_size + 16];
    let mut record_fallbacks = 0;
    let mut names_omitted = 0;
    let mut parse_ms = 0.0;
    let pipeline_started = Instant::now();
    let consume = |offset: u64, buffer: &mut [u8]| {
        let amount = buffer.len();
        let parse_started = Instant::now();
        let parse_len = (valid_len as u64 - offset).min(amount as u64) as usize;
        for (n, record) in buffer[..parse_len]
            .chunks_exact_mut(record_size)
            .enumerate()
        {
            if cancel.load(Ordering::Relaxed) {
                break;
            }
            let number = offset / record_size as u64 + n as u64;
            let parsed = restore_raw(record, number).and_then(|used| {
                if used {
                    parse_names_with_min(record, number, Some(min_size))
                } else {
                    Ok(None)
                }
            });
            match parsed {
                Ok(Some(record)) => {
                    chunk.summary.entries_scanned += 1;
                    names_omitted += u64::from(record.name_omitted);
                    index.insert(record);
                }
                Ok(None) => {}
                Err(error) => {
                    record_fallbacks += 1;
                    let fallback = control(
                        &volume,
                        FSCTL_GET_NTFS_FILE_RECORD,
                        &number.to_le_bytes(),
                        &mut api_buffer,
                    )
                    .and_then(|len| decode_response(&api_buffer[..len], number))
                    .and_then(|(returned, bytes)| {
                        if returned == number {
                            parse_names_with_min(bytes, number, Some(min_size))
                        } else {
                            Err("API 未返回同一条记录，可能已释放".into())
                        }
                    });
                    match fallback {
                        Ok(Some(record)) => {
                            chunk.summary.entries_scanned += 1;
                            names_omitted += u64::from(record.name_omitted);
                            index.insert(record);
                        }
                        Ok(None) => {}
                        Err(e) => chunk.issue(
                            Path::new(&format!("mft-record:{number}")),
                            "mft_bulk_record",
                            format!("{error}；单条补查失败: {e}"),
                        ),
                    }
                }
            }
        }
        parse_ms += parse_started.elapsed().as_secs_f64() * 1000.0;
        collector
            .lock()
            .unwrap()
            .merge(std::mem::replace(&mut chunk, ScanReport::new(engine)));
        !cancel.load(Ordering::Relaxed)
    };
    let open = || {
        OpenOptions::new()
            .read(true)
            .share_mode(7)
            .open(format!("\\\\.\\{drive}"))
            .map_err(|e| e.to_string())
    };
    let (mut stats, read_error) = concurrent::dual(
        [open()?, open()?],
        &mapping,
        length,
        sector,
        cancel,
        consume,
    );
    stats.pipeline_wall_ms = pipeline_started.elapsed().as_secs_f64() * 1000.0;
    stats.parse_ms = parse_ms;
    stats.record_fallbacks = record_fallbacks;
    stats.names_omitted = names_omitted;
    chunk.summary.timings.enumeration_ms += stats.read_ms;
    if let Some(error) = read_error {
        if !cancel.load(Ordering::Relaxed) {
            chunk.issue(&root, "mft_bulk_read", error);
        }
    }
    if !cancel.load(Ordering::Relaxed) {
        let mut end_data = [0u8; 96];
        if control(&volume, FSCTL_GET_NTFS_VOLUME_DATA, &[], &mut end_data).is_err()
            || end_data[56..64] != data[56..64]
        {
            chunk.issue(&root, "mft_bulk_changed", "扫描期间 MFT 长度变化或无法复查");
        }
        match extents(&mft, length, cluster, volume_bytes, cancel) {
            Ok(current) if current == mapping => {}
            _ => chunk.issue(
                &root,
                "mft_bulk_changed",
                "扫描期间 MFT 磁盘分段变化或无法复查",
            ),
        }
    }
    chunk.summary.mft_bulk = Some(stats);
    let entries = index.finish(&mut chunk);
    collector.lock().unwrap().merge(chunk);
    verify_entries(entries, root_info, drive, min_size, cancel, collector)
}
