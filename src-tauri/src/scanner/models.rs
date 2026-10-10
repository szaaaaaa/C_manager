use serde::Serialize;

/// A single file record extracted from scanning.
#[derive(Clone, Debug, Serialize)]
pub struct FileRecord {
    pub path: String,
    pub name: String,
    pub size: u64,
    pub is_dir: bool,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ScanStatus {
    Completed,
    Partial,
    Cancelled,
    Failed,
}

#[derive(Clone, Debug, Serialize)]
pub struct ScanIssue {
    pub path: String,
    pub stage: String,
    pub error: String,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct ScanTimings {
    // Worker time is summed across threads; elapsed_ms below is wall-clock time.
    pub enumeration_ms: f64,
    pub metadata_ms: f64,
    pub path_ms: f64,
    pub sort_ms: f64,
    pub hard_links_ms: f64,
    pub verification_wall_ms: f64,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct VerificationProgress {
    pub total: u64,
    pub checked: u64,
    pub path_errors: u64,
    pub hard_link_queries: u64,
    pub workers: usize,
}

#[derive(Clone, Debug, Serialize)]
pub struct ScanSummary {
    pub mft_bulk: Option<MftBulkStats>,
    pub size_filtered: u64,
    pub mft_records: Option<MftRecordCounts>,
    pub status: ScanStatus,
    pub engine: String,
    pub entries_scanned: u64,
    pub files_matched: u64,
    pub issues: Vec<ScanIssue>,
    pub excluded_links: Vec<String>,
    pub elapsed_ms: u64,
    pub timings: ScanTimings,
    pub verification: VerificationProgress,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct MftRecordCounts {
    pub base_records: u64,
    pub extension_records: u64,
    pub logical_entries: u64,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct MftBulkStats {
    pub block_bytes: u64,
    pub bytes_read: u64,
    pub read_calls: u64,
    pub record_fallbacks: u64,
    pub prefetch_buffers: u32,
    pub names_omitted: u64,
    pub read_ms: f64,
    pub parse_ms: f64,
    pub pipeline_wall_ms: f64,
}

#[derive(Debug, Serialize)]
pub struct ScanReport {
    pub files: Vec<FileRecord>,
    pub summary: ScanSummary,
}

impl ScanReport {
    pub fn new(engine: &str) -> Self {
        Self {
            files: Vec::new(),
            summary: ScanSummary {
                mft_bulk: None,
                size_filtered: 0,
                mft_records: None,
                status: ScanStatus::Completed,
                engine: engine.to_string(),
                entries_scanned: 0,
                files_matched: 0,
                issues: Vec::new(),
                excluded_links: Vec::new(),
                elapsed_ms: 0,
                timings: ScanTimings::default(),
                verification: VerificationProgress::default(),
            },
        }
    }

    pub fn issue(&mut self, path: &std::path::Path, stage: &str, error: impl ToString) {
        self.summary.issues.push(ScanIssue {
            path: path.to_string_lossy().into_owned(),
            stage: stage.to_string(),
            error: error.to_string(),
        });
    }
}
