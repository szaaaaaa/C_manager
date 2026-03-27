//! Standalone CLI: scan a drive and export results as JSON for training data.
//! Usage: cargo run --bin export_scan -- [root] [min_size_mb]
//! Example: cargo run --bin export_scan -- C:\ 100

use c_manager_lib::scanner;
use c_manager_lib::safety::rate_safety;
use std::sync::atomic::AtomicBool;
use std::sync::Arc;

fn format_size(bytes: u64) -> String {
    if bytes >= 1_073_741_824 {
        format!("{:.1} GB", bytes as f64 / 1_073_741_824.0)
    } else {
        format!("{:.0} MB", bytes as f64 / 1_048_576.0)
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let root = args.get(1).map(|s| s.as_str()).unwrap_or("C:\\");
    let min_size_mb: f64 = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(100.0);
    let min_bytes = (min_size_mb * 1024.0 * 1024.0) as u64;

    eprintln!("Scanning {} for files >= {} MB ...", root, min_size_mb);

    let cancel = Arc::new(AtomicBool::new(false));
    let results = scanner::scan_drive(root, min_bytes, 30, 1000, cancel, None)
        .expect("Scan failed");

    eprintln!("Found {} files", results.len());

    // Build JSON array with safety info
    let entries: Vec<serde_json::Value> = results.iter().map(|r| {
        serde_json::json!({
            "path": r.path,
            "name": r.name,
            "size": r.size,
            "size_human": format_size(r.size),
            "is_dir": r.is_dir,
            "safety": rate_safety(&r.path),
        })
    }).collect();

    println!("{}", serde_json::to_string_pretty(&entries).unwrap());
}
