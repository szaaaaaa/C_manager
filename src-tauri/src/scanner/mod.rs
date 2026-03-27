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
    #[cfg(windows)]
    {
        // Try USN scanner first (requires admin — volume handle needs GENERIC_READ)
        let drive_letter = &root[..2]; // "C:" from "C:\\"
        match usn_scanner::scan_usn(drive_letter, min_size_bytes, top_n, &cancel, &on_event) {
            Ok(results) => return Ok(results),
            Err(_) => {
                // Fall through to readdir (no admin, or volume open failed)
            }
        }
    }
    scan_readdir(root, min_size_bytes, 30, top_n, cancel, on_event)
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

    files.sort_unstable_by(|a, b| b.size.cmp(&a.size));
    files.truncate(top_n);
    Ok(files)
}
