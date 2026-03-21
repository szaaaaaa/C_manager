use serde::Serialize;

/// A single file record extracted from scanning.
#[derive(Clone, Serialize)]
pub struct FileRecord {
    pub path: String,
    pub name: String,
    pub size: u64,
    pub is_dir: bool,
}
