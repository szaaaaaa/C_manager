use std::collections::HashMap;
use std::fs::File;
use std::io::BufReader;

use mft::attribute::MftAttributeContent;
use mft::attribute::x30::FileNamespace;
use mft::MftParser;

use super::models::FileRecord;

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
    let mut name_map: HashMap<u64, (String, u64)> = HashMap::new();
    let mut files: Vec<(u64, u64, String, u64)> = Vec::new(); // (entry_id, parent_id, name, size)

    for entry_result in parser.iter_entries() {
        let entry = match entry_result {
            Ok(e) => e,
            Err(_) => continue,
        };

        let entry_id = entry.header.record_number;

        for attr_result in entry.iter_attributes() {
            let attr = match attr_result {
                Ok(a) => a,
                Err(_) => continue,
            };

            if let MftAttributeContent::AttrX30(file_name_attr) = attr.data {
                // Skip DOS short names
                if file_name_attr.namespace == FileNamespace::DOS {
                    continue;
                }

                let name = file_name_attr.name.clone();
                let parent_id = file_name_attr.parent.entry;
                let is_dir = entry.header.flags.bits() & 0x02 != 0;
                let size = file_name_attr.logical_size;

                name_map.insert(entry_id, (name.clone(), parent_id));

                if !is_dir && size >= min_size_bytes {
                    files.push((entry_id, parent_id, name, size));
                }

                break;
            }
        }
    }

    // Phase 2: Sort by size descending, take top_n
    files.sort_unstable_by(|a, b| b.3.cmp(&a.3));
    files.truncate(top_n);

    // Phase 3: Rebuild full paths
    let results = files
        .into_iter()
        .map(|(_, parent_id, file_name, size)| {
            let full_path = rebuild_path(parent_id, &file_name, &name_map);
            let display_name = file_name;
            FileRecord {
                path: full_path,
                name: display_name,
                size,
                is_dir: false,
            }
        })
        .collect();

    Ok(results)
}

fn rebuild_path(
    parent_id: u64,
    file_name: &str,
    name_map: &HashMap<u64, (String, u64)>,
) -> String {
    let mut parts: Vec<&str> = vec![file_name];
    let mut current = parent_id;
    let mut depth = 0;

    while current != 5 && depth < 64 {
        match name_map.get(&current) {
            Some((name, parent)) => {
                parts.push(name.as_str());
                current = *parent;
                depth += 1;
            }
            None => break,
        }
    }

    parts.reverse();
    format!("C:\\{}", parts.join("\\"))
}
