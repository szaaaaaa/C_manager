use serde::Serialize;
use crate::safety::rate_safety;

#[derive(Serialize)]
pub struct ScanItem {
    path: String,
    name: String,
    size: u64,
    size_human: String,
    is_dir: bool,
    children_count: u32,
    safety: String,
}

fn format_size(bytes: u64) -> String {
    let units = ["B", "KB", "MB", "GB", "TB"];
    let mut size = bytes as f64;
    for unit in &units {
        if size < 1024.0 {
            return format!("{:.1} {}", size, unit);
        }
        size /= 1024.0;
    }
    format!("{:.1} PB", size)
}

#[tauri::command]
pub async fn scan_drive(
    root: String,
    min_size_mb: f64,
    _max_depth: u32,
) -> Result<Vec<ScanItem>, String> {
    let min_bytes = (min_size_mb * 1024.0 * 1024.0) as u64;

    let records = tokio::task::spawn_blocking(move || {
        crate::scanner::scan_drive(&root, min_bytes, 200)
    })
    .await
    .map_err(|e| format!("Scan task failed: {}", e))??;

    let items = records
        .into_iter()
        .map(|r| ScanItem {
            safety: rate_safety(&r.path).to_string(),
            size_human: format_size(r.size),
            path: r.path,
            name: r.name,
            size: r.size,
            is_dir: r.is_dir,
            children_count: 0,
        })
        .collect();

    Ok(items)
}
