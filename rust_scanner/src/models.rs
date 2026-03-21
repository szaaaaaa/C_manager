/// A single file record extracted from MFT.
pub struct FileRecord {
    pub entry_id: u64,
    pub parent_entry_id: u64,
    pub name: String,
    pub size: u64,
    pub is_directory: bool,
}
