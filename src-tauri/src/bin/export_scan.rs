//! Standalone CLI: scan a drive and export results as JSON for training data.
//! Usage: cargo run --bin export_scan -- [root] [min_size_mb] [mft_dual]
//! Example: cargo run --bin export_scan -- C:\ 100

use c_manager_lib::safety::rate_safety;
use c_manager_lib::scanner;
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
    let min_size_mb: f64 = match args.get(2).map(|s| s.parse()).transpose() {
        Ok(value) => value.unwrap_or(100.0),
        Err(_) => {
            eprintln!("min_size_mb must be a number");
            std::process::exit(1);
        }
    };
    if !min_size_mb.is_finite() || min_size_mb < 0.0 || min_size_mb * 1_048_576.0 >= u64::MAX as f64
    {
        eprintln!("min_size_mb must be finite and non-negative");
        std::process::exit(1);
    }
    let min_bytes = (min_size_mb * 1024.0 * 1024.0) as u64;
    let engine = args.get(3).map(String::as_str).unwrap_or("mft_dual");

    eprintln!("Scanning {} for files >= {} MB ...", root, min_size_mb);

    let cancel = Arc::new(AtomicBool::new(false));
    let report = match scanner::scan_with_engine(root, min_bytes, engine, cancel, None) {
        Ok(report) => report,
        Err(error) => {
            let mut report = scanner::models::ScanReport::new(engine);
            report.summary.status = scanner::models::ScanStatus::Failed;
            report.issue(std::path::Path::new(root), "scan", error);
            eprintln!("{}", serde_json::to_string(&report.summary).unwrap());
            println!("[]");
            std::process::exit(1);
        }
    };

    eprintln!("{}", serde_json::to_string(&report.summary).unwrap());

    // Build JSON array with safety info
    let entries: Vec<serde_json::Value> = report
        .files
        .iter()
        .map(|r| {
            serde_json::json!({
                "path": r.path,
                "name": r.name,
                "size": r.size,
                "size_human": format_size(r.size),
                "is_dir": r.is_dir,
                "safety": rate_safety(&r.path),
            })
        })
        .collect();

    println!("{}", serde_json::to_string_pretty(&entries).unwrap());
    if report.summary.status != scanner::models::ScanStatus::Completed {
        std::process::exit(2);
    }
}
