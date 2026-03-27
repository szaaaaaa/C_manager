use serde::Serialize;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tauri::ipc::Channel;
use tauri::State;

use crate::safety::rate_safety;
use crate::scanner::ScanEvent;

pub struct ScanCancel(pub Arc<AtomicBool>);

#[derive(Clone, Serialize)]
#[serde(tag = "type")]
pub enum ScanMessage {
    #[serde(rename = "progress")]
    Progress {
        entries_scanned: u64,
        files_matched: u64,
    },
    #[serde(rename = "file")]
    FileFound {
        path: String,
        name: String,
        size: u64,
        size_human: String,
        is_dir: bool,
        children_count: u32,
        safety: String,
    },
}

use super::format_size;

#[tauri::command]
pub async fn scan_drive(
    root: String,
    min_size_mb: f64,
    max_depth: u32,
    on_event: Channel<ScanMessage>,
    cancel_state: State<'_, ScanCancel>,
) -> Result<(), String> {
    if min_size_mb < 0.0 {
        return Err("min_size_mb must be non-negative".to_string());
    }
    let min_bytes = (min_size_mb * 1024.0 * 1024.0) as u64;
    let cancel = cancel_state.0.clone();

    cancel.store(false, Ordering::SeqCst);

    tokio::task::spawn_blocking(move || {
        let event_fn: crate::scanner::EventFn = Box::new(move |event| {
            let msg = match event {
                ScanEvent::Progress(scanned, matched) => ScanMessage::Progress {
                    entries_scanned: scanned,
                    files_matched: matched,
                },
                ScanEvent::FileFound(record) => ScanMessage::FileFound {
                    safety: rate_safety(&record.path).to_string(),
                    size_human: format_size(record.size),
                    path: record.path,
                    name: record.name,
                    size: record.size,
                    is_dir: record.is_dir,
                    children_count: 0,
                },
            };
            let _ = on_event.send(msg);
        });

        crate::scanner::scan_drive(&root, min_bytes, max_depth, 1000, cancel, Some(event_fn))
    })
    .await
    .map_err(|e| format!("Scan task failed: {}", e))??;

    Ok(())
}

#[tauri::command]
pub fn cancel_scan(cancel_state: State<'_, ScanCancel>) {
    cancel_state.0.store(true, Ordering::SeqCst);
}
