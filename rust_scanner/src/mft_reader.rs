use std::collections::HashMap;
use std::fs::File;
use std::io::BufReader;

use mft::attribute::MftAttributeContent;
use mft::MftParser;

use crate::models::FileRecord;

/// Read and parse MFT entries from a volume (e.g. "\\\\.\\C:").
/// Returns file records with size >= min_size_bytes, sorted by size descending,
/// limited to top_n results.
pub fn scan_mft(
    volume: &str,
    min_size_bytes: u64,
    top_n: usize,
) -> Result<Vec<FileRecord>, String> {
    let file = File::open(volume).map_err(|e| format!("Cannot open volume {}: {}", volume, e))?;
    let reader = BufReader::new(file);
    let mut parser =
        MftParser::from_read_seek(reader, None).map_err(|e| format!("MFT parse error: {}", e))?;

    // Phase 1: Collect all entries to build parent map and file list
    let mut name_map: HashMap<u64, (String, u64)> = HashMap::new(); // entry_id -> (name, parent_id)
    let mut files: Vec<FileRecord> = Vec::new();

    for entry_result in parser.iter_entries() {
        let entry = match entry_result {
            Ok(e) => e,
            Err(_) => continue,
        };

        let entry_id = entry.header.record_number;

        // Find the $FILE_NAME attribute to get name, parent ref, and flags
        for attr_result in entry.iter_attributes() {
            let attr = match attr_result {
                Ok(a) => a,
                Err(_) => continue,
            };

            if let MftAttributeContent::AttrX30(file_name_attr) = attr.data {
                let name = file_name_attr.name.clone();

                // Skip DOS short names (namespace 2) — prefer Win32 or Win32+DOS
                if file_name_attr.namespace == 2 {
                    continue;
                }

                let parent_id = file_name_attr.parent.entry;
                let is_dir = entry.header.flags.bits() & 0x02 != 0;
                let size = file_name_attr.logical_size;

                name_map.insert(entry_id, (name.clone(), parent_id));

                if !is_dir && size >= min_size_bytes {
                    files.push(FileRecord {
                        entry_id,
                        parent_entry_id: parent_id,
                        name,
                        size,
                        is_directory: false,
                    });
                }

                break; // Use the first valid $FILE_NAME
            }
        }
    }

    // Phase 2: Sort by size descending, take top_n
    files.sort_unstable_by(|a, b| b.size.cmp(&a.size));
    files.truncate(top_n);

    // Phase 3: Rebuild full paths for the top_n files
    for file in &mut files {
        file.name = rebuild_path(file.parent_entry_id, &file.name, &name_map);
    }

    Ok(files)
}

/// Walk up the parent chain to rebuild the full path.
fn rebuild_path(
    parent_id: u64,
    file_name: &str,
    name_map: &HashMap<u64, (String, u64)>,
) -> String {
    let mut parts: Vec<&str> = vec![file_name];
    let mut current = parent_id;
    let mut depth = 0;

    // MFT root entry is typically entry 5
    while current != 5 && depth < 64 {
        match name_map.get(&current) {
            Some((name, parent)) => {
                parts.push(name.as_str());
                current = *parent;
                depth += 1;
            }
            None => break, // Orphan entry — stop here
        }
    }

    parts.reverse();
    format!("C:\\{}", parts.join("\\"))
}
