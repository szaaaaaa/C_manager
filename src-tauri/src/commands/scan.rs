use serde::Serialize;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use tauri::ipc::Channel;
use tauri::State;

use super::format_size;
use crate::safety::rate_safety;
use crate::scanner::models::{FileRecord, ScanReport, ScanStatus, ScanSummary};
use crate::scanner::ScanEvent;

#[derive(Default)]
pub struct ScanState {
    cancel: Arc<AtomicBool>,
    running: Arc<AtomicBool>,
    next_id: AtomicU64,
    report: Arc<Mutex<Option<(u64, ScanReport)>>>,
}

#[derive(Clone, Serialize)]
pub struct ScanItem {
    path: String,
    name: String,
    size: u64,
    size_human: String,
    is_dir: bool,
    children_count: u32,
    safety: String,
}

impl From<FileRecord> for ScanItem {
    fn from(record: FileRecord) -> Self {
        Self {
            safety: rate_safety(&record.path).to_string(),
            size_human: format_size(record.size),
            path: record.path,
            name: record.name,
            size: record.size,
            is_dir: record.is_dir,
            children_count: 0,
        }
    }
}

#[derive(Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ScanMessage {
    Progress {
        entries_scanned: u64,
        files_matched: u64,
    },
    Files {
        sequence: u64,
        files: Vec<ScanItem>,
    },
}

#[derive(Serialize)]
pub struct ScanCompletion {
    scan_id: u64,
    summary: ScanSummary,
    batches_sent: u64,
    transport_error: Option<String>,
}

struct RunningGuard(Arc<AtomicBool>);
impl Drop for RunningGuard {
    fn drop(&mut self) {
        self.0.store(false, Ordering::Release);
    }
}

// Serializes batches and retains the first delivery error instead of discarding it.
struct Delivery {
    batches_sent: u64,
    error: Option<String>,
}
impl Delivery {
    fn send(&mut self, event: ScanEvent, send: impl FnOnce(ScanMessage) -> Result<(), String>) {
        if self.error.is_some() {
            return;
        }
        let msg = match event {
            ScanEvent::Progress(entries_scanned, files_matched) => ScanMessage::Progress {
                entries_scanned,
                files_matched,
            },
            ScanEvent::FileFound(file) => ScanMessage::Files {
                sequence: self.batches_sent,
                files: vec![file.into()],
            },
            ScanEvent::FilesFound(files) => ScanMessage::Files {
                sequence: self.batches_sent,
                files: files.into_iter().map(ScanItem::from).collect(),
            },
        };
        let is_batch = matches!(msg, ScanMessage::Files { .. });
        match send(msg) {
            Ok(()) if is_batch => self.batches_sent += 1,
            Ok(()) => {}
            Err(error) => self.error = Some(error),
        }
    }
}

#[tauri::command]
pub async fn scan_drive(
    root: String,
    min_size_mb: f64,
    on_event: Channel<ScanMessage>,
    scan_state: State<'_, ScanState>,
) -> Result<ScanCompletion, String> {
    if !min_size_mb.is_finite() || min_size_mb < 0.0 || min_size_mb * 1_048_576.0 >= u64::MAX as f64
    {
        return Err("最小文件大小必须是有效的非负数".to_string());
    }
    if scan_state
        .running
        .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
        .is_err()
    {
        return Err("已有扫描正在运行".to_string());
    }
    let guard = RunningGuard(scan_state.running.clone());
    scan_state.cancel.store(false, Ordering::Release);
    let cancel = scan_state.cancel.clone();
    let stored = scan_state.report.clone();
    let scan_id = scan_state.next_id.fetch_add(1, Ordering::Relaxed) + 1;
    tokio::task::spawn_blocking(move || {
        let _guard = guard;
        *stored.lock().unwrap() = None;
        let delivery = Arc::new(Mutex::new(Delivery {
            batches_sent: 0,
            error: None,
        }));
        let output = delivery.clone();
        let event_fn = Box::new(move |event| {
            output
                .lock()
                .unwrap()
                .send(event, |msg| on_event.send(msg).map_err(|e| e.to_string()));
        });
        // A disconnected UI does not discard backend results; they remain available by page.
        let mut report = match crate::scanner::scan_drive(
            &root,
            (min_size_mb * 1_048_576.0) as u64,
            cancel,
            Some(event_fn),
        ) {
            Ok(report) => report,
            Err(error) => {
                let mut report = ScanReport::new("directory");
                report.summary.status = ScanStatus::Failed;
                report.issue(std::path::Path::new(&root), "scan", error);
                report
            }
        };
        let delivery = delivery.lock().unwrap();
        if let Some(error) = &delivery.error {
            report.issue(std::path::Path::new(&root), "transport", error);
            if report.summary.status == ScanStatus::Completed {
                report.summary.status = ScanStatus::Partial;
            }
        }
        let completion = ScanCompletion {
            scan_id,
            summary: report.summary.clone(),
            batches_sent: delivery.batches_sent,
            transport_error: delivery.error.clone(),
        };
        *stored.lock().unwrap() = Some((scan_id, report));
        completion
    })
    .await
    .map_err(|e| format!("扫描任务失败: {e}"))
}

#[tauri::command]
pub fn get_scan_results(
    scan_id: u64,
    offset: usize,
    limit: usize,
    scan_state: State<'_, ScanState>,
) -> Result<Vec<ScanItem>, String> {
    if limit == 0 || limit > 1000 {
        return Err("每页数量必须为 1–1000".into());
    }
    let stored = scan_state.report.lock().map_err(|_| "扫描结果不可用")?;
    let (id, report) = stored.as_ref().ok_or("尚无已结束的扫描")?;
    if *id != scan_id {
        return Err("扫描结果已被后续扫描替换".into());
    }
    if offset > report.files.len() {
        return Err("结果偏移越界".into());
    }
    Ok(report
        .files
        .iter()
        .skip(offset)
        .take(limit)
        .cloned()
        .map(ScanItem::from)
        .collect())
}

#[tauri::command]
pub fn cancel_scan(scan_state: State<'_, ScanState>) {
    scan_state.cancel.store(true, Ordering::Release);
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn delivery_sequences_batches_and_exposes_failure() {
        let file = FileRecord {
            path: "C:\\test.bin".into(),
            name: "test.bin".into(),
            size: 16,
            is_dir: false,
        };
        let mut delivery = Delivery {
            batches_sent: 0,
            error: None,
        };
        for sequence in 0..2 {
            delivery.send(ScanEvent::FilesFound(vec![file.clone()]), |msg| {
                assert!(matches!(msg, ScanMessage::Files { sequence: n, .. } if n == sequence));
                Ok(())
            });
        }
        delivery.send(ScanEvent::FilesFound(vec![file.clone()]), |_| {
            Err("closed".into())
        });
        delivery.send(ScanEvent::FilesFound(vec![file]), |_| {
            panic!("must not hide or retry a failed channel")
        });
        assert_eq!(delivery.batches_sent, 2);
        assert_eq!(delivery.error.as_deref(), Some("closed"));
    }
}
