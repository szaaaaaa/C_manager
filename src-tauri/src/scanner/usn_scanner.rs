//! NTFS enumeration followed by current metadata verification.
#[cfg(test)]
use super::EventFn;
use std::collections::{HashMap, HashSet};
use std::ffi::OsString;
use std::os::windows::ffi::OsStrExt;
use std::os::windows::ffi::OsStringExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Instant;

use rayon::prelude::*;
use windows_sys::Win32::Foundation::{
    GetLastError, ERROR_HANDLE_EOF, ERROR_MORE_DATA, HANDLE, INVALID_HANDLE_VALUE,
};
use windows_sys::Win32::Storage::FileSystem::{FindClose, FindFirstFileNameW, FindNextFileNameW};

use super::models::ScanReport;
use super::{entry_info, record_file, Collector};

#[derive(Clone)]
pub(super) struct FileEntry {
    pub(super) name: OsString,
    pub(super) parent_ref: u64,
    pub(super) is_dir: bool,
}

#[cfg(test)]
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
            return Err(format!("Parent reference {current:#x} is not a directory"));
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

pub(super) fn hard_link_paths(path: &Path, drive: &str) -> std::io::Result<Vec<PathBuf>> {
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

pub(super) fn verify_entries(
    entries: HashMap<u64, FileEntry>,
    root_info: super::EntryInfo,
    drive_letter: &str,
    min_size_bytes: u64,
    cancel: &AtomicBool,
    collector: Mutex<Collector<'_>>,
) -> Result<ScanReport, String> {
    verify_entries_with_workers(
        entries,
        root_info,
        drive_letter,
        min_size_bytes,
        cancel,
        collector,
        4,
    )
}

fn verify_entries_with_workers(
    entries: HashMap<u64, FileEntry>,
    root_info: super::EntryInfo,
    drive_letter: &str,
    min_size_bytes: u64,
    cancel: &AtomicBool,
    collector: Mutex<Collector<'_>>,
    workers: usize,
) -> Result<ScanReport, String> {
    let started = Instant::now();
    let root = PathBuf::from(format!("{drive_letter}\\"));
    let mut cache = HashMap::from([(root_info.identity.1, root)]);
    let mut initial = ScanReport::new("verification");
    initial.summary.verification.total = entries.values().filter(|e| !e.is_dir).count() as u64;
    initial.summary.verification.workers = workers;
    collector.lock().unwrap().merge(initial);
    let mut candidates = entries.iter().filter(|(_, entry)| !entry.is_dir);
    // par_bridge pulls bounded batches: cached path building overlaps handle verification.
    let batches = std::iter::from_fn(|| {
        let mut files = Vec::with_capacity(256);
        let mut chunk = ScanReport::new("verification");
        let start = Instant::now();
        let mut consumed = 0;
        for (&id, _) in candidates.by_ref().take(256) {
            if cancel.load(Ordering::Relaxed) {
                break;
            }
            consumed += 1;
            match build_path(id, &entries, &mut cache) {
                Ok(path) => files.push((id, path)),
                Err(error) => {
                    chunk.summary.verification.path_errors += 1;
                    chunk.issue(
                        Path::new(&format!("file-reference:{id:#x}")),
                        "path_resolution",
                        error,
                    );
                }
            }
        }
        if consumed == 0 {
            return None;
        }
        chunk.summary.timings.path_ms = start.elapsed().as_secs_f64() * 1000.0;
        collector.lock().unwrap().merge(chunk);
        Some(files)
    });
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(workers)
        .build()
        .map_err(|e| e.to_string())?;
    pool.install(|| {
        batches.par_bridge().for_each(|files| {
            let mut chunk = ScanReport::new("verification");
            for (id, path) in files {
                if cancel.load(Ordering::Relaxed) {
                    break;
                }
                let start = Instant::now();
                let info = entry_info(&path);
                chunk.summary.timings.metadata_ms += start.elapsed().as_secs_f64() * 1000.0;
                chunk.summary.verification.checked += 1;
                match info {
                    Err(error) => chunk.issue(&path, "metadata", error),
                    Ok(info) if info.identity != (root_info.identity.0, id) || info.is_dir => {
                        chunk.issue(
                            &path,
                            "file_changed",
                            "文件标识或类型已改变，原记录大小未知",
                        );
                    }
                    Ok(info) => {
                        // Size is current handle metadata; all files still receive this check.
                        if info.size >= min_size_bytes && info.links > 1 && !info.is_link {
                            let start = Instant::now();
                            chunk.summary.verification.hard_link_queries += 1;
                            match hard_link_paths(&path, drive_letter) {
                                Ok(paths) => {
                                    if paths.len() != info.links as usize {
                                        chunk.issue(
                                            &path,
                                            "hard_links",
                                            "硬链接数量在扫描期间发生变化",
                                        );
                                    }
                                    for alias in paths {
                                        record_file(&alias, &info, min_size_bytes, &mut chunk);
                                    }
                                }
                                Err(error) => {
                                    chunk.issue(&path, "hard_links", error);
                                    record_file(&path, &info, min_size_bytes, &mut chunk);
                                }
                            }
                            chunk.summary.timings.hard_links_ms +=
                                start.elapsed().as_secs_f64() * 1000.0;
                        } else {
                            record_file(&path, &info, min_size_bytes, &mut chunk);
                        }
                    }
                }
            }
            collector.lock().unwrap().merge(chunk);
        });
    });
    let mut collector = collector.into_inner().unwrap();
    let mut timing = ScanReport::new("verification");
    timing.summary.timings.verification_wall_ms = started.elapsed().as_secs_f64() * 1000.0;
    collector.merge(timing);
    Ok(collector.finish(cancel))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture_entries(
        paths: &[(PathBuf, u64)],
    ) -> (HashMap<u64, FileEntry>, super::super::EntryInfo, String) {
        let first = paths[0].0.to_string_lossy();
        let drive = first.strip_prefix(r"\\?\").unwrap_or(&first)[..2].to_string();
        let root = PathBuf::from(format!("{drive}\\"));
        let root_info = entry_info(&root).unwrap();
        let mut entries = HashMap::new();
        for (path, _) in paths {
            let mut current = path.as_path();
            loop {
                let info = entry_info(current).unwrap();
                if info.identity == root_info.identity || entries.contains_key(&info.identity.1) {
                    break;
                }
                let parent = current.parent().unwrap();
                let parent_info = entry_info(parent).unwrap();
                entries.insert(
                    info.identity.1,
                    FileEntry {
                        name: current.file_name().unwrap().to_owned(),
                        parent_ref: parent_info.identity.1,
                        is_dir: info.is_dir,
                    },
                );
                current = parent;
            }
        }
        (entries, root_info, drive)
    }

    fn expected(paths: &[(PathBuf, u64)], min: u64) -> Vec<(String, u64)> {
        let mut files: Vec<_> = paths
            .iter()
            .filter(|(_, size)| *size >= min)
            .map(|(path, size)| {
                let text = path.to_str().unwrap();
                (
                    text.strip_prefix(r"\\?\").unwrap_or(text).to_string(),
                    *size,
                )
            })
            .collect();
        files.sort();
        files
    }

    fn pairs(root: &Path, count: usize) -> Vec<(PathBuf, u64)> {
        let mut paths = Vec::new();
        for n in 0..count {
            let dir = root.join(format!("目录{}", n % 32));
            std::fs::create_dir_all(&dir).unwrap();
            let path = dir.join(format!("{n}.bin"));
            let alias = dir.join(format!("{n}-alias.bin"));
            std::fs::write(&path, [0; 8]).unwrap();
            std::fs::hard_link(&path, &alias).unwrap();
            // Grow through an alias, so directory-entry sizes must not be trusted.
            let size = if n % 128 == 0 { 64 * 1024 * 1024 } else { 8 };
            std::fs::OpenOptions::new()
                .write(true)
                .open(&alias)
                .unwrap()
                .set_len(size)
                .unwrap();
            paths.push((path, size));
            paths.push((alias, size));
        }
        paths
    }

    #[test]
    fn pipelined_verification_preserves_aliases_errors_cancellation_and_skips_small_link_queries() {
        let fixture = super::super::tests::Fixture::new();
        let paths = pairs(&fixture.0, 520);
        let (entries, root_info, drive) = fixture_entries(&paths);
        let root = PathBuf::from(format!("{drive}\\"));
        for min in [0, 1024] {
            let report = verify_entries_with_workers(
                entries.clone(),
                entry_info(&root).unwrap(),
                &drive,
                min,
                &AtomicBool::new(false),
                Mutex::new(Collector::new("usn", &None)),
                2,
            )
            .unwrap();
            let mut actual: Vec<_> = report
                .files
                .iter()
                .map(|f| (f.path.clone(), f.size))
                .collect();
            actual.sort();
            assert_eq!(actual, expected(&paths, min));
            assert!(report.summary.issues.is_empty());
            assert_eq!(report.summary.verification.checked, 520);
            assert_eq!(
                report.summary.verification.hard_link_queries,
                if min == 0 { 520 } else { 5 }
            );
        }
        let mut broken = entries.clone();
        broken.insert(
            u64::MAX,
            FileEntry {
                name: "orphan".into(),
                parent_ref: u64::MAX - 1,
                is_dir: false,
            },
        );
        let removed_id = entry_info(&paths[2].0).unwrap().identity.1;
        std::fs::remove_file(&paths[2].0).unwrap();
        std::fs::remove_file(&paths[3].0).unwrap();
        assert!(broken.contains_key(&removed_id));
        let report = verify_entries_with_workers(
            broken,
            root_info,
            &drive,
            1024,
            &AtomicBool::new(false),
            Mutex::new(Collector::new("mft", &None)),
            4,
        )
        .unwrap();
        assert_eq!(report.summary.engine, "mft");
        assert_eq!(report.summary.verification.path_errors, 1);
        assert!(report.summary.issues.iter().any(|e| e.stage == "metadata"));
        assert_eq!(
            report.summary.status,
            super::super::models::ScanStatus::Partial
        );
        let cancel = std::sync::Arc::new(AtomicBool::new(false));
        let signal = cancel.clone();
        let delivered = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let count = delivered.clone();
        let events: Option<EventFn> = Some(Box::new(move |event| {
            if let super::super::ScanEvent::FilesFound(files) = event {
                count.fetch_add(files.len(), Ordering::Relaxed);
                signal.store(true, Ordering::Relaxed);
            }
        }));
        let report = verify_entries_with_workers(
            entries.clone(),
            entry_info(&root).unwrap(),
            &drive,
            0,
            &cancel,
            Mutex::new(Collector::new("usn", &events)),
            1,
        )
        .unwrap();
        assert_eq!(
            report.summary.status,
            super::super::models::ScanStatus::Cancelled
        );
        assert!(!report.files.is_empty());
        assert_eq!(report.files.len(), delivered.load(Ordering::Relaxed));
        assert!(report.summary.verification.checked < 520);
        let report = verify_entries_with_workers(
            entries,
            entry_info(&root).unwrap(),
            &drive,
            0,
            &cancel,
            Mutex::new(Collector::new("usn", &None)),
            4,
        )
        .unwrap();
        assert_eq!(
            report.summary.status,
            super::super::models::ScanStatus::Cancelled
        );
        assert!(report.files.is_empty());
    }

    #[test]
    #[ignore = "Windows filesystem benchmark; builds a known hard-link fixture"]
    fn verification_worker_benchmark() {
        let fixture = super::super::tests::Fixture::new();
        let paths = if let Some(root) = std::env::var_os("SCAN_VERIFY_ROOT") {
            let mut paths = Vec::new();
            let mut dirs = vec![PathBuf::from(root).canonicalize().unwrap()];
            while let Some(dir) = dirs.pop() {
                for entry in std::fs::read_dir(dir).unwrap() {
                    let entry = entry.unwrap();
                    let metadata = std::fs::symlink_metadata(entry.path()).unwrap();
                    if metadata.file_type().is_symlink() {
                        continue;
                    }
                    if metadata.is_dir() {
                        dirs.push(entry.path());
                    } else if metadata.is_file() {
                        paths.push((entry.path(), metadata.len()));
                    }
                }
            }
            paths
        } else {
            pairs(&fixture.0, 4096)
        };
        assert!(!paths.is_empty());
        let (entries, _, drive) = fixture_entries(&paths);
        let root = PathBuf::from(format!("{drive}\\"));
        for min in [0, 16 * 1024 * 1024] {
            for (round, order) in [[2, 4, 8], [8, 2, 4], [4, 8, 2]].iter().enumerate() {
                for &workers in order {
                    let report = verify_entries_with_workers(
                        entries.clone(),
                        entry_info(&root).unwrap(),
                        &drive,
                        min,
                        &AtomicBool::new(false),
                        Mutex::new(Collector::new("usn", &None)),
                        workers,
                    )
                    .unwrap();
                    let mut actual: Vec<_> = report
                        .files
                        .iter()
                        .map(|f| (f.path.clone(), f.size))
                        .collect();
                    actual.sort();
                    assert_eq!(actual, expected(&paths, min));
                    assert!(report.summary.issues.is_empty());
                    println!(
                        "{}",
                        serde_json::json!({"round": round, "workers": workers, "min_bytes": min,
                        "matched": report.files.len(), "timings": report.summary.timings, "verification": report.summary.verification})
                    );
                }
            }
        }
    }

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
