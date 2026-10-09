pub mod models;

#[cfg(windows)]
pub mod mft_reader;
#[cfg(windows)]
pub mod usn_scanner;

use models::FileRecord;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

/// Events emitted during scanning.
pub enum ScanEvent {
    /// Periodic progress: (entries_scanned, files_matched)
    Progress(u64, u64),
    /// A matching file was found.
    FileFound(FileRecord),
}

pub type EventFn = Box<dyn Fn(ScanEvent) + Send + Sync>;

/// Scan drive for large files.
/// On Windows with admin: uses FSCTL_ENUM_USN_DATA (kernel-speed MFT enumeration + rayon parallel metadata).
/// Fallback: recursive readdir.
pub fn scan_drive(
    root: &str,
    min_size_bytes: u64,
    max_depth: u32,
    top_n: usize,
    cancel: Arc<AtomicBool>,
    on_event: Option<EventFn>,
) -> Result<Vec<FileRecord>, String> {
    if cancel.load(Ordering::SeqCst) {
        return Err("Scan cancelled".to_string());
    }
    std::fs::read_dir(root).map_err(|e| format!("Cannot scan {}: {}", root, e))?;
    #[cfg(windows)]
    {
        // Enumerating a whole volume is only useful when the requested root is that volume.
        let volume_root = root.trim_end_matches(['\\', '/']);
        if volume_root.len() == 2 && volume_root.as_bytes()[0].is_ascii_alphabetic()
            && volume_root.as_bytes()[1] == b':' && root.len() > 2 {
            match usn_scanner::scan_usn(volume_root, min_size_bytes, max_depth, top_n, &cancel, &on_event) {
                Ok(results) => return Ok(results),
                Err(e) if cancel.load(Ordering::SeqCst) => return Err(e),
                Err(_) => {}
            }
        }
    }
    scan_readdir(root, min_size_bytes, max_depth, top_n, cancel, on_event)
}

fn scan_readdir(
    root: &str,
    min_size_bytes: u64,
    max_depth: u32,
    top_n: usize,
    cancel: Arc<AtomicBool>,
    on_event: Option<EventFn>,
) -> Result<Vec<FileRecord>, String> {
    use std::fs;

    let mut files: Vec<FileRecord> = Vec::new();
    let mut count: u64 = 0;

    fn walk(
        dir: &std::path::Path,
        files: &mut Vec<FileRecord>,
        count: &mut u64,
        min_size: u64,
        depth: u32,
        max_depth: u32,
        cancel: &AtomicBool,
        on_event: &Option<EventFn>,
    ) {
        if depth > max_depth || cancel.load(Ordering::SeqCst) {
            return;
        }
        let entries = match fs::read_dir(dir) {
            Ok(e) => e,
            Err(_) => return,
        };
        for entry in entries.flatten() {
            if cancel.load(Ordering::SeqCst) {
                return;
            }
            *count += 1;
            if *count % 500 == 0 {
                if let Some(ref cb) = on_event {
                    cb(ScanEvent::Progress(*count, files.len() as u64));
                }
            }
            let path = entry.path();
            let ft = match entry.file_type() {
                Ok(ft) => ft,
                Err(_) => continue,
            };
            if ft.is_file() {
                if let Ok(meta) = entry.metadata() {
                    if meta.len() >= min_size {
                        let record = FileRecord {
                            path: path.to_string_lossy().to_string(),
                            name: entry.file_name().to_string_lossy().to_string(),
                            size: meta.len(),
                            is_dir: false,
                        };
                        if let Some(ref cb) = on_event {
                            cb(ScanEvent::FileFound(record.clone()));
                        }
                        files.push(record);
                    }
                }
            } else if ft.is_dir() {
                walk(&path, files, count, min_size, depth + 1, max_depth, cancel, on_event);
            }
        }
    }

    walk(
        std::path::Path::new(root),
        &mut files,
        &mut count,
        min_size_bytes,
        0,
        max_depth,
        &cancel,
        &on_event,
    );

    if cancel.load(Ordering::SeqCst) {
        return Err("Scan cancelled".to_string());
    }

    if let Some(ref cb) = on_event {
        cb(ScanEvent::Progress(count, files.len() as u64));
    }
    files.sort_unstable_by(|a, b| b.size.cmp(&a.size));
    files.truncate(top_n);
    Ok(files)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scan_respects_root_depth_and_reports_missing_roots() {
        let root = std::env::temp_dir().join(format!("c-manager-scan-{}", std::process::id()));
        std::fs::create_dir(&root).unwrap();
        std::fs::create_dir(root.join("child")).unwrap();
        std::fs::write(root.join("top.bin"), [0; 16]).unwrap();
        std::fs::write(root.join("child/deep.bin"), [0; 32]).unwrap();
        let results = scan_drive(root.to_str().unwrap(), 1, 0, 10,
            Arc::new(AtomicBool::new(false)), None).unwrap();
        let progress = Arc::new(std::sync::Mutex::new((0, 0)));
        let captured = progress.clone();
        let limited = scan_drive(root.to_str().unwrap(), 1, 1, 0,
            Arc::new(AtomicBool::new(false)), Some(Box::new(move |event| {
                if let ScanEvent::Progress(scanned, matched) = event {
                    *captured.lock().unwrap() = (scanned, matched);
                }
            }))).unwrap();
        let resolved_root = root.canonicalize().unwrap();
        assert!(resolved_root.starts_with(std::env::temp_dir().canonicalize().unwrap()));
        std::fs::remove_dir_all(&resolved_root).unwrap();
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].name, "top.bin");
        assert!(limited.is_empty());
        assert_eq!(progress.lock().unwrap().1, 2);
        assert!(scan_drive(root.to_str().unwrap(), 1, 0, 10,
            Arc::new(AtomicBool::new(false)), None).is_err());
    }

    #[test]
    #[ignore = "reads the C: drive to compare the default depth with the old traversal"]
    fn default_scan_performance() {
        let start = std::time::Instant::now();
        let old = scan_readdir("C:\\", 10 * 1024 * 1024, 30, 1000,
            Arc::new(AtomicBool::new(false)), None).unwrap();
        println!("Old 30-level traversal: {:?}, {} retained files", start.elapsed(), old.len());
        let start = std::time::Instant::now();
        let new = scan_drive("C:\\", 10 * 1024 * 1024, 3, 1000,
            Arc::new(AtomicBool::new(false)), None).unwrap();
        println!("Configured 3-level scan: {:?}, {} retained files", start.elapsed(), new.len());
    }
}
