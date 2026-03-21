pub mod models;

#[cfg(windows)]
pub mod mft_reader;

use models::FileRecord;

/// Scan drive for large files. Uses MFT on Windows, read_dir elsewhere.
pub fn scan_drive(
    root: &str,
    min_size_bytes: u64,
    top_n: usize,
) -> Result<Vec<FileRecord>, String> {
    #[cfg(windows)]
    {
        // Try MFT first (requires admin)
        let volume = format!("\\\\.\\{}", root.trim_end_matches('\\').trim_end_matches('/'));
        match mft_reader::scan_mft(&volume, min_size_bytes, top_n) {
            Ok(results) => return Ok(results),
            Err(_) => {} // Fall through to read_dir
        }
    }

    // Fallback: recursive directory walk
    scan_readdir(root, min_size_bytes, top_n)
}

fn scan_readdir(
    root: &str,
    min_size_bytes: u64,
    top_n: usize,
) -> Result<Vec<FileRecord>, String> {
    use std::fs;

    let mut files: Vec<FileRecord> = Vec::new();

    fn walk(dir: &std::path::Path, files: &mut Vec<FileRecord>, min_size: u64) {
        let entries = match fs::read_dir(dir) {
            Ok(e) => e,
            Err(_) => return,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() {
                if let Ok(meta) = entry.metadata() {
                    if meta.len() >= min_size {
                        files.push(FileRecord {
                            path: path.to_string_lossy().to_string(),
                            name: entry.file_name().to_string_lossy().to_string(),
                            size: meta.len(),
                            is_dir: false,
                        });
                    }
                }
            } else if path.is_dir() {
                walk(&path, files, min_size);
            }
        }
    }

    walk(std::path::Path::new(root), &mut files, min_size_bytes);
    files.sort_unstable_by(|a, b| b.size.cmp(&a.size));
    files.truncate(top_n);
    Ok(files)
}
