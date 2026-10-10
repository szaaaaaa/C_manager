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
}

#[derive(Clone, Debug, Serialize)]
pub struct ScanSummary {
    pub status: ScanStatus,
    pub engine: String,
    pub entries_scanned: u64,
    pub files_matched: u64,
    pub issues: Vec<ScanIssue>,
    pub excluded_links: Vec<String>,
    pub elapsed_ms: u64,
    pub timings: ScanTimings,
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
                status: ScanStatus::Completed,
                engine: engine.to_string(),
                entries_scanned: 0,
                files_matched: 0,
                issues: Vec::new(),
                excluded_links: Vec::new(),
                elapsed_ms: 0,
                timings: ScanTimings::default(),
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
