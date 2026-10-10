pub mod models;

#[cfg(windows)]
pub mod mft_reader;
#[cfg(windows)]
pub mod usn_scanner;

use models::{FileRecord, ScanReport, ScanStatus};
use rayon::prelude::*;
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

pub enum ScanEvent {
    Progress(u64, u64),
    FileFound(FileRecord),
    FilesFound(Vec<FileRecord>),
}

pub type EventFn = Box<dyn Fn(ScanEvent) + Send + Sync>;
const BATCH_SIZE: usize = 256;
const UPDATE_INTERVAL: Duration = Duration::from_millis(100);

/// Scan every entry in the tree, without following name-surrogate links.
pub fn scan_drive(
    root: &str,
    min_size_bytes: u64,
    cancel: Arc<AtomicBool>,
    on_event: Option<EventFn>,
) -> Result<ScanReport, String> {
    scan_readdir(root, min_size_bytes, 4, cancel, on_event)
}

// Both engines share retention, batching and completion semantics.
pub(super) struct Collector<'a> {
    report: ScanReport,
    pending: Vec<FileRecord>,
    started: Instant,
    last_emit: Instant,
    on_event: &'a Option<EventFn>,
}

impl<'a> Collector<'a> {
    pub(super) fn new(engine: &str, on_event: &'a Option<EventFn>) -> Self {
        Self {
            report: ScanReport::new(engine),
            pending: Vec::new(),
            started: Instant::now(),
            last_emit: Instant::now(),
            on_event,
        }
    }

    pub(super) fn merge(&mut self, mut chunk: ScanReport) {
        self.report.summary.entries_scanned += chunk.summary.entries_scanned;
        self.report.summary.issues.append(&mut chunk.summary.issues);
        self.report
            .summary
            .excluded_links
            .append(&mut chunk.summary.excluded_links);
        self.report.summary.timings.enumeration_ms += chunk.summary.timings.enumeration_ms;
        self.report.summary.timings.metadata_ms += chunk.summary.timings.metadata_ms;
        self.report.summary.timings.path_ms += chunk.summary.timings.path_ms;
        for file in chunk.files {
            if self.on_event.is_some() {
                self.pending.push(file.clone());
            }
            self.report.files.push(file);
            if self.pending.len() == BATCH_SIZE {
                self.flush();
            }
        }
        if self.last_emit.elapsed() >= UPDATE_INTERVAL {
            self.flush();
        }
    }

    fn flush(&mut self) {
        if let Some(cb) = self.on_event {
            if !self.pending.is_empty() {
                cb(ScanEvent::FilesFound(std::mem::take(&mut self.pending)));
            }
            cb(ScanEvent::Progress(
                self.report.summary.entries_scanned,
                self.report.files.len() as u64,
            ));
        }
        self.last_emit = Instant::now();
    }

    pub(super) fn finish(mut self, cancel: &AtomicBool) -> ScanReport {
        self.flush();
        self.report.summary.status = if cancel.load(Ordering::Relaxed) {
            ScanStatus::Cancelled
        } else if self.report.summary.issues.is_empty() {
            ScanStatus::Completed
        } else {
            ScanStatus::Partial
        };
        let start = Instant::now();
        self.report
            .files
            .sort_unstable_by(|a, b| b.size.cmp(&a.size).then_with(|| a.path.cmp(&b.path)));
        self.report.summary.timings.sort_ms = start.elapsed().as_secs_f64() * 1000.0;
        self.report.summary.files_matched = self.report.files.len() as u64;
        self.report.summary.elapsed_ms = self.started.elapsed().as_millis() as u64;
        self.report
    }
}

pub(super) struct EntryInfo {
    size: u64,
    is_dir: bool,
    is_link: bool,
    identity: (u64, u64),
    #[cfg(windows)]
    links: u32,
}

#[cfg(windows)]
pub(super) fn entry_info(path: &Path) -> std::io::Result<EntryInfo> {
    use std::os::windows::{fs::OpenOptionsExt, io::AsRawHandle};
    use windows_sys::Win32::Storage::FileSystem::*;
    // Query the open file, not the directory's potentially stale hard-link size.
    let file = std::fs::OpenOptions::new()
        .access_mode(FILE_READ_ATTRIBUTES)
        .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE)
        .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS)
        .open(path)?;
    let mut info: BY_HANDLE_FILE_INFORMATION = unsafe { std::mem::zeroed() };
    if unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut info) } == 0 {
        return Err(std::io::Error::last_os_error());
    }
    let mut is_link = false;
    if info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT != 0 {
        let mut tag: FILE_ATTRIBUTE_TAG_INFO = unsafe { std::mem::zeroed() };
        if unsafe {
            GetFileInformationByHandleEx(
                file.as_raw_handle(),
                FileAttributeTagInfo,
                &mut tag as *mut _ as *mut _,
                std::mem::size_of_val(&tag) as u32,
            )
        } == 0
        {
            return Err(std::io::Error::last_os_error());
        }
        is_link = tag.ReparseTag & 0x2000_0000 != 0;
    }
    Ok(EntryInfo {
        size: ((info.nFileSizeHigh as u64) << 32) | info.nFileSizeLow as u64,
        is_dir: info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY != 0,
        is_link,
        identity: (
            info.dwVolumeSerialNumber as u64,
            ((info.nFileIndexHigh as u64) << 32) | info.nFileIndexLow as u64,
        ),
        links: info.nNumberOfLinks,
    })
}

#[cfg(unix)]
pub(super) fn entry_info(path: &Path) -> std::io::Result<EntryInfo> {
    use std::os::unix::fs::MetadataExt;
    let info = std::fs::symlink_metadata(path)?;
    Ok(EntryInfo {
        size: info.len(),
        is_dir: info.is_dir(),
        is_link: info.is_symlink(),
        identity: (info.dev(), info.ino()),
    })
}

pub(super) fn record_file(path: &Path, info: &EntryInfo, min_size: u64, chunk: &mut ScanReport) {
    if info.is_link {
        chunk
            .summary
            .excluded_links
            .push(path.to_string_lossy().into_owned());
    } else if !info.is_dir && info.size >= min_size {
        match (path.to_str(), path.file_name().and_then(|n| n.to_str())) {
            (Some(path), Some(name)) => chunk.files.push(FileRecord {
                path: path.to_string(),
                name: name.to_string(),
                size: info.size,
                is_dir: false,
            }),
            _ => chunk.issue(
                path,
                "path_encoding",
                "文件名不能无损表示为 Unicode，未加入可操作列表",
            ),
        }
    }
}

fn scan_readdir(
    root: &str,
    min_size: u64,
    workers: usize,
    cancel: Arc<AtomicBool>,
    on_event: Option<EventFn>,
) -> Result<ScanReport, String> {
    if root.trim().is_empty() {
        return Err("扫描路径不能为空".to_string());
    }
    let root = std::path::absolute(root).map_err(|e| e.to_string())?;
    let collector = Mutex::new(Collector::new("directory", &on_event));
    if cancel.load(Ordering::Relaxed) {
        return Ok(collector.into_inner().unwrap().finish(&cancel));
    }
    let root_info = entry_info(&root).map_err(|e| format!("无法访问 {}: {}", root.display(), e))?;
    if !root_info.is_dir || root_info.is_link {
        return Err("扫描根路径必须是实际目录；请直接选择链接的目标目录".to_string());
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(workers)
        .build()
        .map_err(|e| e.to_string())?;
    let visited = Mutex::new(HashSet::new());
    let mut directories = vec![root];
    pool.install(|| {
        while !directories.is_empty() && !cancel.load(Ordering::Relaxed) {
            // A frontier is complete only after every active directory task has joined.
            directories = directories
                .into_par_iter()
                .flat_map_iter(|dir| {
                    scan_directory(
                        &dir,
                        min_size,
                        root_info.identity.0,
                        &cancel,
                        &visited,
                        &collector,
                    )
                })
                .collect();
        }
    });
    Ok(collector.into_inner().unwrap().finish(&cancel))
}

fn scan_directory(
    dir: &Path,
    min_size: u64,
    volume: u64,
    cancel: &AtomicBool,
    visited: &Mutex<HashSet<(u64, u64)>>,
    collector: &Mutex<Collector<'_>>,
) -> Vec<PathBuf> {
    let mut chunk = ScanReport::new("directory");
    let mut children = Vec::new();
    if cancel.load(Ordering::Relaxed) {
        return children;
    }
    let checked = Instant::now();
    let info = entry_info(dir);
    chunk.summary.timings.metadata_ms += checked.elapsed().as_secs_f64() * 1000.0;
    match info {
        Ok(info) if info.is_link => {
            chunk
                .summary
                .excluded_links
                .push(dir.to_string_lossy().into_owned());
            chunk.issue(
                dir,
                "directory_changed",
                "待扫描目录已变为链接，原目录未覆盖",
            );
        }
        Ok(info) if !info.is_dir || info.identity.0 != volume => {
            chunk.issue(dir, "directory_changed", "目录类型或所在卷发生变化");
        }
        Ok(info) if !visited.lock().unwrap().insert(info.identity) => {
            chunk.issue(dir, "directory_cycle", "目录标识重复，未重复遍历");
        }
        Ok(_) => {
            let started = Instant::now();
            let entries = std::fs::read_dir(dir);
            chunk.summary.timings.enumeration_ms += started.elapsed().as_secs_f64() * 1000.0;
            match entries {
                Err(e) => chunk.issue(dir, "read_dir", e),
                Ok(mut entries) => {
                    let mut last_merge = Instant::now();
                    loop {
                        if cancel.load(Ordering::Relaxed) {
                            break;
                        }
                        let started = Instant::now();
                        let entry = entries.next();
                        chunk.summary.timings.enumeration_ms +=
                            started.elapsed().as_secs_f64() * 1000.0;
                        let Some(entry) = entry else {
                            break;
                        };
                        chunk.summary.entries_scanned += 1;
                        match entry {
                            Err(e) => chunk.issue(dir, "directory_entry", e),
                            Ok(entry) => {
                                let started = Instant::now();
                                let path = entry.path();
                                chunk.summary.timings.path_ms +=
                                    started.elapsed().as_secs_f64() * 1000.0;
                                let started = Instant::now();
                                let info = entry_info(&path);
                                chunk.summary.timings.metadata_ms +=
                                    started.elapsed().as_secs_f64() * 1000.0;
                                match info {
                                    Err(e) => chunk.issue(&path, "metadata", e),
                                    Ok(info) if info.is_dir && !info.is_link => children.push(path),
                                    Ok(info) => record_file(&path, &info, min_size, &mut chunk),
                                }
                            }
                        }
                        if chunk.summary.entries_scanned >= BATCH_SIZE as u64
                            || last_merge.elapsed() >= UPDATE_INTERVAL
                        {
                            collector
                                .lock()
                                .unwrap()
                                .merge(std::mem::replace(&mut chunk, ScanReport::new("directory")));
                            last_merge = Instant::now();
                        }
                    }
                }
            }
        }
        Err(e) => chunk.issue(dir, "directory_metadata", e),
    }
    collector.lock().unwrap().merge(chunk);
    children
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::sync::atomic::AtomicU64;

    static NEXT_TEST: AtomicU64 = AtomicU64::new(0);
    pub(super) struct Fixture(pub(super) PathBuf);
    impl Fixture {
        pub(super) fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "c-manager-scan-{}-{}",
                std::process::id(),
                NEXT_TEST.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            Self(path.canonicalize().unwrap())
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            assert!(self
                .0
                .starts_with(std::env::temp_dir().canonicalize().unwrap()));
            fs::remove_dir_all(&self.0).unwrap();
        }
    }

    #[test]
    fn complete_scan_keeps_deep_long_paths_and_all_batches() {
        let root = Fixture::new();
        let mut deep = root.0.clone();
        for _ in 0..100 {
            deep.push("deep");
        }
        fs::create_dir_all(&deep).unwrap();
        fs::write(deep.join("大文件.bin"), [0; 65]).unwrap();
        for n in 0..1100 {
            fs::write(root.0.join(format!("{n}.bin")), [0; 64]).unwrap();
        }
        fs::write(root.0.join("below.bin"), [0; 63]).unwrap();
        fs::write(root.0.join("small.bin"), [0; 63]).unwrap();
        fs::hard_link(root.0.join("small.bin"), root.0.join("grown-link.bin")).unwrap();
        fs::OpenOptions::new()
            .write(true)
            .open(root.0.join("small.bin"))
            .unwrap()
            .set_len(128)
            .unwrap();
        let received = Arc::new(Mutex::new(Vec::new()));
        let captured = received.clone();
        let report = scan_drive(
            root.0.to_str().unwrap(),
            64,
            Arc::new(AtomicBool::new(false)),
            Some(Box::new(move |event| {
                if let ScanEvent::FilesFound(files) = event {
                    assert!(files.len() <= BATCH_SIZE);
                    captured
                        .lock()
                        .unwrap()
                        .extend(files.into_iter().map(|f| (f.path, f.size)));
                }
            })),
        )
        .unwrap();
        assert_eq!(report.summary.status, ScanStatus::Completed);
        assert_eq!(report.files.len(), 1103);
        assert_eq!(report.summary.files_matched, 1103);
        let expected: std::collections::BTreeMap<_, _> = report
            .files
            .iter()
            .map(|f| (f.path.clone(), f.size))
            .collect();
        assert_eq!(expected.len(), 1103);
        assert_eq!(expected[deep.join("大文件.bin").to_str().unwrap()], 65);
        assert_eq!(
            expected[root.0.join("grown-link.bin").to_str().unwrap()],
            128
        );
        for n in 0..1100 {
            assert_eq!(
                expected[root.0.join(format!("{n}.bin")).to_str().unwrap()],
                64
            );
        }
        assert!(!expected.contains_key(root.0.join("below.bin").to_str().unwrap()));
        assert_eq!(received.lock().unwrap().len(), expected.len());
        assert_eq!(
            received
                .lock()
                .unwrap()
                .iter()
                .cloned()
                .collect::<std::collections::BTreeMap<_, _>>(),
            expected
        );
        for workers in [1, 2, 8] {
            let other = scan_readdir(
                root.0.to_str().unwrap(),
                64,
                workers,
                Arc::new(AtomicBool::new(false)),
                None,
            )
            .unwrap();
            assert_eq!(other.summary.status, ScanStatus::Completed);
            assert_eq!(
                other
                    .files
                    .iter()
                    .map(|f| (f.path.clone(), f.size))
                    .collect::<std::collections::BTreeMap<_, _>>(),
                expected
            );
        }
    }

    #[test]
    fn cancellation_retains_results_and_flushes_the_last_batch() {
        let root = Fixture::new();
        for n in 0..600 {
            fs::write(root.0.join(format!("{n}.bin")), [0; 1]).unwrap();
        }
        let cancel = Arc::new(AtomicBool::new(false));
        let stop = cancel.clone();
        let received = Arc::new(AtomicU64::new(0));
        let count = received.clone();
        let report = scan_drive(
            root.0.to_str().unwrap(),
            0,
            cancel,
            Some(Box::new(move |event| {
                if let ScanEvent::FilesFound(files) = event {
                    count.fetch_add(files.len() as u64, Ordering::Relaxed);
                    stop.store(true, Ordering::Relaxed);
                }
            })),
        )
        .unwrap();
        assert_eq!(report.summary.status, ScanStatus::Cancelled);
        assert!(!report.files.is_empty());
        assert!(report.files.len() < 600);
        assert_eq!(
            received.load(Ordering::Relaxed),
            report.summary.files_matched
        );
    }

    #[test]
    fn missing_directory_and_unknown_size_are_reported() {
        let root = Fixture::new();
        let missing = root.0.join("missing");
        let events = None;
        let collector = Mutex::new(Collector::new("directory", &events));
        scan_directory(
            &missing,
            1,
            0,
            &AtomicBool::new(false),
            &Mutex::new(HashSet::new()),
            &collector,
        );
        let report = collector
            .into_inner()
            .unwrap()
            .finish(&AtomicBool::new(false));
        assert_eq!(report.summary.status, ScanStatus::Partial);
        assert_eq!(report.summary.issues.len(), 1);
        assert!(report.summary.issues[0].path.ends_with("missing"));
        assert!(entry_info(&missing).is_err());
        assert!(scan_drive(
            missing.to_str().unwrap(),
            0,
            Arc::new(AtomicBool::new(false)),
            None
        )
        .is_err());
    }

    #[cfg(windows)]
    #[test]
    fn hidden_system_files_are_included_and_junctions_do_not_loop_or_escape() {
        use std::os::windows::ffi::OsStrExt;
        use windows_sys::Win32::Storage::FileSystem::{
            SetFileAttributesW, FILE_ATTRIBUTE_HIDDEN, FILE_ATTRIBUTE_SYSTEM,
        };
        let root = Fixture::new();
        let outside = Fixture::new();
        let file = root.0.join("system.bin");
        fs::write(&file, [0; 64]).unwrap();
        fs::write(outside.0.join("outside.bin"), [0; 128]).unwrap();
        let wide: Vec<_> = file.as_os_str().encode_wide().chain(Some(0)).collect();
        assert_ne!(
            unsafe {
                SetFileAttributesW(wide.as_ptr(), FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)
            },
            0
        );
        for (name, target) in [("loop", &root.0), ("external", &outside.0)] {
            let result = std::process::Command::new("cmd.exe")
                .args(["/d", "/c", "mklink", "/J"])
                .arg(root.0.join(name))
                .arg(target)
                .output()
                .unwrap();
            assert!(
                result.status.success(),
                "{}",
                String::from_utf8_lossy(&result.stderr)
            );
        }
        let report = scan_drive(
            root.0.to_str().unwrap(),
            0,
            Arc::new(AtomicBool::new(false)),
            None,
        )
        .unwrap();
        fs::remove_dir(root.0.join("loop")).unwrap();
        fs::remove_dir(root.0.join("external")).unwrap();
        assert_eq!(report.summary.status, ScanStatus::Completed);
        assert_eq!(report.summary.excluded_links.len(), 2);
        assert_eq!(report.files.len(), 1);
        assert_eq!(report.files[0].name, "system.bin");
        assert!(outside.0.join("outside.bin").exists());
    }

    #[cfg(windows)]
    #[test]
    fn access_denied_directory_is_explicitly_partial() {
        let root = Fixture::new();
        let denied = root.0.join("denied");
        fs::create_dir(&denied).unwrap();
        fs::write(denied.join("large.bin"), [0; 64]).unwrap();
        fs::write(root.0.join("visible.bin"), [0; 64]).unwrap();
        let identity = std::process::Command::new("whoami.exe")
            .args(["/user", "/fo", "csv", "/nh"])
            .output()
            .unwrap();
        assert!(identity.status.success());
        let identity = String::from_utf8(identity.stdout).unwrap();
        let sid = identity
            .trim()
            .split(',')
            .next_back()
            .unwrap()
            .trim_matches('"')
            .to_string();
        assert!(sid.starts_with("S-1-"));
        struct RestoreAcl {
            path: PathBuf,
            sid: String,
        }
        impl Drop for RestoreAcl {
            fn drop(&mut self) {
                let result = std::process::Command::new("icacls.exe")
                    .arg(&self.path)
                    .args(["/remove:d", &format!("*{}", self.sid)])
                    .output()
                    .unwrap();
                assert!(result.status.success(), "failed to restore test ACL");
            }
        }
        let restore = RestoreAcl {
            path: denied.clone(),
            sid: sid.clone(),
        };
        let result = std::process::Command::new("icacls.exe")
            .arg(&denied)
            .args(["/deny", &format!("*{sid}:(RD)")])
            .output()
            .unwrap();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        let report = scan_drive(
            root.0.to_str().unwrap(),
            0,
            Arc::new(AtomicBool::new(false)),
            None,
        )
        .unwrap();
        drop(restore);
        assert_eq!(report.summary.status, ScanStatus::Partial);
        assert_eq!(report.files.len(), 1);
        assert_eq!(report.files[0].name, "visible.bin");
        assert!(report
            .summary
            .issues
            .iter()
            .any(|issue| issue.path == denied.to_string_lossy()));
    }

    #[cfg(windows)]
    #[test]
    fn sparse_twenty_gib_file_is_found_without_reading_its_contents() {
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::System::IO::DeviceIoControl;
        let root = Fixture::new();
        let path = root.0.join("large.vhdx");
        let file = fs::File::create(&path).unwrap();
        let mut returned = 0;
        // FSCTL_SET_SPARSE; keep the large-file test from allocating 20 GiB on disk.
        assert_ne!(
            unsafe {
                DeviceIoControl(
                    file.as_raw_handle(),
                    590020,
                    std::ptr::null(),
                    0,
                    std::ptr::null_mut(),
                    0,
                    &mut returned,
                    std::ptr::null_mut(),
                )
            },
            0
        );
        let size = 20 * 1024 * 1024 * 1024u64;
        file.set_len(size).unwrap();
        drop(file);
        let report = scan_drive(
            root.0.to_str().unwrap(),
            10 * 1024 * 1024,
            Arc::new(AtomicBool::new(false)),
            None,
        )
        .unwrap();
        assert_eq!(report.summary.status, ScanStatus::Completed);
        assert_eq!(report.files.len(), 1);
        assert_eq!(report.files[0].size, size);
    }

    #[test]
    #[ignore = "read-only benchmark; set SCAN_BENCH_ROOT to the same tree for every worker count"]
    fn complete_scan_performance() {
        let root = std::env::var("SCAN_BENCH_ROOT").expect("set SCAN_BENCH_ROOT");
        let warmup = scan_readdir(&root, 0, 1, Arc::new(AtomicBool::new(false)), None).unwrap();
        assert_eq!(
            warmup.summary.status,
            ScanStatus::Completed,
            "benchmark requires a fully accessible fixture"
        );
        let expected: std::collections::BTreeMap<_, _> = warmup
            .files
            .iter()
            .map(|f| (f.path.clone(), f.size))
            .collect();
        for (round, order) in [[1, 2, 4, 8], [8, 4, 2, 1], [2, 8, 1, 4]]
            .into_iter()
            .enumerate()
        {
            for workers in order {
                let report =
                    scan_readdir(&root, 0, workers, Arc::new(AtomicBool::new(false)), None)
                        .unwrap();
                assert_eq!(report.summary.status, ScanStatus::Completed);
                let files: std::collections::BTreeMap<_, _> = report
                    .files
                    .iter()
                    .map(|f| (f.path.clone(), f.size))
                    .collect();
                assert_eq!(files, expected, "dataset changed or a scan missed files");
                assert_eq!(
                    report.summary.entries_scanned,
                    warmup.summary.entries_scanned
                );
                println!("workers={workers} round={round} elapsed_ms={} scanned={} matched={} issues={} worker_times={:?}",
                    report.summary.elapsed_ms, report.summary.entries_scanned, report.summary.files_matched,
                    report.summary.issues.len(), report.summary.timings);
            }
        }
    }
}
