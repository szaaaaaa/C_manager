use serde::Serialize;
use sha2::{Digest, Sha256};
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

// Shared with api.ts: UTF-8 JSON [position, [[path, decimal size], ...]].
fn batch_checksum(position: u64, files: &[ScanItem]) -> String {
    let records: Vec<_> = files
        .iter()
        .map(|f| (&f.path, f.size.to_string()))
        .collect();
    let bytes = serde_json::to_vec(&(position, records)).expect("serializing scan paths and sizes");
    format!("{:x}", Sha256::digest(bytes))
}

#[derive(Clone, Serialize)]
pub struct ScanPage {
    files: Vec<ScanItem>,
    checksum: String,
}

#[derive(Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ScanMessage {
    Verification { verification: crate::scanner::models::VerificationProgress },
    Progress {
        entries_scanned: u64,
        files_matched: u64,
    },
    Files {
        sequence: u64,
        #[serde(flatten)]
        page: ScanPage,
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
            ScanEvent::Verification(verification) => ScanMessage::Verification { verification },
            ScanEvent::Progress(entries_scanned, files_matched) => ScanMessage::Progress {
                entries_scanned,
                files_matched,
            },
            ScanEvent::FileFound(file) => ScanMessage::Files {
                sequence: self.batches_sent,
                page: self.page(vec![file]),
            },
            ScanEvent::FilesFound(files) => ScanMessage::Files {
                sequence: self.batches_sent,
                page: self.page(files),
            },
        };
        let is_batch = matches!(msg, ScanMessage::Files { .. });
        match send(msg) {
            Ok(()) if is_batch => self.batches_sent += 1,
            Ok(()) => {}
            Err(error) => self.error = Some(error),
        }
    }

    fn page(&self, files: Vec<FileRecord>) -> ScanPage {
        let files: Vec<_> = files.into_iter().map(ScanItem::from).collect();
        ScanPage {
            checksum: batch_checksum(self.batches_sent, &files),
            files,
        }
    }
}

#[tauri::command]
pub async fn scan_drive(
    root: String,
    min_size_mb: f64,
    engine: Option<String>,
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
    let engine = engine.unwrap_or_else(|| "mft_dual".into());
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
        let mut report = match crate::scanner::scan_with_engine(
            &root,
            (min_size_mb * 1_048_576.0) as u64,
            &engine,
            cancel,
            Some(event_fn),
        ) {
            Ok(report) => report,
            Err(error) => {
                let mut report = ScanReport::new(&engine);
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
) -> Result<ScanPage, String> {
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
    let files: Vec<_> = report
        .files
        .iter()
        .skip(offset)
        .take(limit)
        .cloned()
        .map(ScanItem::from)
        .collect();
    Ok(ScanPage {
        checksum: batch_checksum(offset as u64, &files),
        files,
    })
}

#[tauri::command]
pub fn cancel_scan(scan_state: State<'_, ScanState>) {
    scan_state.cancel.store(true, Ordering::Release);
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn checksum_matches_webcrypto_for_unicode_escaping_and_large_files() {
        let files = vec![ScanItem::from(FileRecord {
            path: "C:\\中文😀\\quote\"\t\n.bin".into(),
            name: "ignored.bin".into(),
            size: 20 * 1024u64.pow(3),
            is_dir: false,
        })];
        assert_eq!(
            batch_checksum(1000, &files),
            "0fc9c6f6f5e338e619400d00451e69543d708aee316d3a805dc8b0b1609a1cc2"
        );
        assert_ne!(batch_checksum(0, &files), batch_checksum(1000, &files));
    }
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
                let wire = serde_json::to_value(&msg).unwrap();
                assert_eq!(wire["type"], "files");
                assert_eq!(wire["files"][0]["path"], file.path);
                assert_eq!(
                    wire["checksum"],
                    batch_checksum(sequence, &[file.clone().into()])
                );
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
