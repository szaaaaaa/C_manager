use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::BufReader;
use std::sync::atomic::{AtomicBool, Ordering};

use mft::attribute::header::ResidentialHeader;
use mft::attribute::x30::FileNamespace;
use mft::attribute::{MftAttributeContent, MftAttributeType};
use mft::MftParser;

use super::models::FileRecord;

/// Read and parse MFT entries from a volume (e.g. "\\\\.\\C:").
///
/// Uses `entry.header.base_reference` to link extension MFT entries back to
/// their base entry, so $DATA attributes stored in extension entries are
/// correctly associated with the file's name from the base entry.
pub fn scan_mft(
    volume: &str,
    drive_letter: &str,
    min_size_bytes: u64,
    top_n: usize,
    cancel: &AtomicBool,
    on_event: &Option<super::EventFn>,
) -> Result<Vec<FileRecord>, String> {
    let file = File::open(volume).map_err(|e| format!("Cannot open volume {}: {}", volume, e))?;
    let reader = BufReader::with_capacity(1024 * 1024, file);
    let mut parser =
        MftParser::from_read_seek(reader, None).map_err(|e| format!("MFT parse error: {}", e))?;

    // name_map: entry_id → (file_name, parent_entry_id)  [from base entries with $FILE_NAME]
    let mut name_map: HashMap<u64, (String, u64)> = HashMap::new();
    // dir_set: entry IDs that are directories
    let mut dir_set: HashSet<u64> = HashSet::new();
    // size_map: base_entry_id → file_size
    // Populated from $DATA in either the base entry itself OR extension entries
    // (linked via base_reference)
    let mut size_map: HashMap<u64, u64> = HashMap::new();
    // fn_size_map: entry_id → logical_size from $FILE_NAME (last-resort fallback)
    let mut fn_size_map: HashMap<u64, u64> = HashMap::new();

    let mut entry_count: u64 = 0;

    for entry_result in parser.iter_entries() {
        if cancel.load(Ordering::SeqCst) {
            return Err("Scan cancelled".to_string());
        }

        entry_count += 1;
        if entry_count % 2000 == 0 {
            if let Some(ref cb) = on_event {
                cb(super::ScanEvent::Progress(entry_count, 0));
            }
        }

        let entry = match entry_result {
            Ok(e) => e,
            Err(_) => continue,
        };

        let entry_id = entry.header.record_number;
        let base_ref = entry.header.base_reference.entry;
        // base_ref == 0 means this IS a base entry; otherwise it's an extension entry
        let is_extension = base_ref != 0;
        let is_dir = entry.header.flags.bits() & 0x02 != 0;

        for attr_result in entry.iter_attributes() {
            let attr = match attr_result {
                Ok(a) => a,
                Err(_) => continue,
            };

            // $FILE_NAME (X30): only present in base entries
            if let MftAttributeContent::AttrX30(ref fna) = attr.data {
                if fna.namespace == FileNamespace::DOS {
                    continue;
                }
                if !name_map.contains_key(&entry_id) {
                    name_map.insert(entry_id, (fna.name.clone(), fna.parent.entry));
                    if fna.logical_size > 0 {
                        fn_size_map.insert(entry_id, fna.logical_size);
                    }
                    if is_dir {
                        dir_set.insert(entry_id);
                    }
                }
            }

            // $DATA (X80, unnamed): get file size from attribute header
            if attr.header.type_code == MftAttributeType::DATA && attr.header.name.is_empty() {
                let size = match &attr.header.residential_header {
                    ResidentialHeader::NonResident(nr) => nr.file_size,
                    ResidentialHeader::Resident(r) => r.data_size as u64,
                };
                if size > 0 {
                    // Key insight: if this is an extension entry, assign size to the BASE entry
                    let target_id = if is_extension { base_ref } else { entry_id };
                    size_map
                        .entry(target_id)
                        .and_modify(|s| *s = (*s).max(size))
                        .or_insert(size);
                }
            }
        }
    }

    // Collect matching files
    let mut files: Vec<(u64, u64, String, u64)> = Vec::new();
    for (entry_id, (name, parent_id)) in &name_map {
        if dir_set.contains(entry_id) {
            continue;
        }
        // Prefer $DATA size, fall back to $FILE_NAME logical_size
        let size = size_map
            .get(entry_id)
            .copied()
            .or_else(|| fn_size_map.get(entry_id).copied())
            .unwrap_or(0);

        if size >= min_size_bytes {
            files.push((*entry_id, *parent_id, name.clone(), size));
        }
    }

    if let Some(ref cb) = on_event {
        cb(super::ScanEvent::Progress(entry_count, files.len() as u64));
    }

    files.sort_unstable_by(|a, b| b.3.cmp(&a.3));
    files.truncate(top_n);

    let drive_prefix = drive_letter.to_string();
    let results: Vec<FileRecord> = files
        .into_iter()
        .map(|(_, parent_id, file_name, size)| {
            let full_path = rebuild_path(parent_id, &file_name, &name_map, &drive_prefix);
            let record = FileRecord {
                path: full_path,
                name: file_name,
                size,
                is_dir: false,
            };
            if let Some(ref cb) = on_event {
                cb(super::ScanEvent::FileFound(record.clone()));
            }
            record
        })
        .collect();

    Ok(results)
}

fn rebuild_path(
    parent_id: u64,
    file_name: &str,
    name_map: &HashMap<u64, (String, u64)>,
    drive_prefix: &str,
) -> String {
    let mut parts: Vec<&str> = vec![file_name];
    let mut current = parent_id;
    let mut depth = 0;

    // MFT entry 5 is the NTFS root directory
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
    format!("{}\\{}", drive_prefix, parts.join("\\"))
}
