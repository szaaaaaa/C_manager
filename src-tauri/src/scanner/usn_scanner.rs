//! Fast file enumeration via Windows FSCTL_ENUM_USN_DATA.
//!
//! Phase 1: Kernel enumerates ALL MFT entries in ~1-2 seconds (names, parents, attributes).
//! Phase 2: Build full paths from the in-memory parent tree.
//! Phase 3: Query file sizes via std::fs::metadata (only for non-directory files).

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Mutex;
use std::{mem, ptr};

use rayon::prelude::*;

use windows_sys::Win32::Foundation::{CloseHandle, HANDLE, INVALID_HANDLE_VALUE};
use windows_sys::Win32::Storage::FileSystem::{
    CreateFileW, FILE_SHARE_DELETE, FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING,
};
use windows_sys::Win32::System::IO::DeviceIoControl;

use super::models::FileRecord;
use super::{EventFn, ScanEvent};

const FSCTL_ENUM_USN_DATA: u32 = 0x000900b3;
const FILE_ATTRIBUTE_DIRECTORY: u32 = 0x10;

#[repr(C)]
struct MftEnumDataV0 {
    start_file_reference_number: u64,
    low_usn: i64,
    high_usn: i64,
}

#[repr(C)]
struct UsnRecordV2 {
    record_length: u32,
    major_version: u16,
    minor_version: u16,
    file_reference_number: u64,
    parent_file_reference_number: u64,
    usn: i64,
    time_stamp: i64,
    reason: u32,
    source_info: u32,
    security_id: u32,
    file_attributes: u32,
    file_name_length: u16,
    file_name_offset: u16,
}

/// Compact MFT entry — names stored in a shared StringArena to avoid per-entry heap allocation.
struct FileEntry {
    name_offset: u32,
    name_len: u16,
    parent_ref: u64,
    is_dir: bool,
}

/// Arena allocator for file name strings. All names are appended into one contiguous buffer.
struct StringArena {
    buf: Vec<u8>,
}

impl StringArena {
    fn with_capacity(cap: usize) -> Self {
        Self { buf: Vec::with_capacity(cap) }
    }

    fn push(&mut self, s: &str) -> (u32, u16) {
        let offset = self.buf.len() as u32;
        let len = s.len() as u16;
        self.buf.extend_from_slice(s.as_bytes());
        (offset, len)
    }

    fn get(&self, offset: u32, len: u16) -> &str {
        let start = offset as usize;
        let end = start + len as usize;
        // SAFETY: we only store valid UTF-8 from String::from_utf16_lossy
        unsafe { std::str::from_utf8_unchecked(&self.buf[start..end]) }
    }
}

/// Scan a volume using FSCTL_ENUM_USN_DATA for fast enumeration.
pub fn scan_usn(
    drive_letter: &str, // e.g. "C:"
    min_size_bytes: u64,
    top_n: usize,
    cancel: &AtomicBool,
    on_event: &Option<EventFn>,
) -> Result<Vec<FileRecord>, String> {
    // Phase 1: Open volume and enumerate all MFT entries via USN
    let volume_path: Vec<u16> = format!("\\\\.\\{}", drive_letter)
        .encode_utf16()
        .chain(std::iter::once(0))
        .collect();

    let handle = unsafe {
        CreateFileW(
            volume_path.as_ptr(),
            0x80000000, // GENERIC_READ
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            ptr::null(),
            OPEN_EXISTING,
            0,
            ptr::null_mut(),
        )
    };

    if handle == INVALID_HANDLE_VALUE {
        return Err(format!(
            "Cannot open volume {}  (admin required)",
            drive_letter
        ));
    }

    // RAII guard for the handle
    struct HandleGuard(HANDLE);
    impl Drop for HandleGuard {
        fn drop(&mut self) {
            unsafe { CloseHandle(self.0); }
        }
    }
    let _guard = HandleGuard(handle);

    // Enumerate all files — pre-allocate for typical C: drive (~1M entries)
    const ESTIMATED_ENTRIES: usize = 1_000_000;
    let mut entries: HashMap<u64, FileEntry> = HashMap::with_capacity(ESTIMATED_ENTRIES);
    let mut arena = StringArena::with_capacity(ESTIMATED_ENTRIES * 20); // ~20 bytes avg name
    let mut input = MftEnumDataV0 {
        start_file_reference_number: 0,
        low_usn: 0,
        high_usn: i64::MAX,
    };
    let mut buffer = vec![0u8; 128 * 1024]; // 128KB buffer
    let mut enum_count: u64 = 0;

    loop {
        if cancel.load(Ordering::SeqCst) {
            return Err("Scan cancelled".to_string());
        }

        let mut bytes_returned: u32 = 0;
        let ok = unsafe {
            DeviceIoControl(
                handle,
                FSCTL_ENUM_USN_DATA,
                &input as *const _ as *const std::ffi::c_void,
                mem::size_of::<MftEnumDataV0>() as u32,
                buffer.as_mut_ptr() as *mut std::ffi::c_void,
                buffer.len() as u32,
                &mut bytes_returned,
                ptr::null_mut(),
            )
        };

        if ok == 0 || bytes_returned <= 8 {
            break;
        }

        // First 8 bytes = next StartFileReferenceNumber for pagination
        input.start_file_reference_number =
            unsafe { *(buffer.as_ptr() as *const u64) };

        // Parse USN_RECORD_V2 entries after the first 8 bytes
        let mut offset = 8usize;
        while offset < bytes_returned as usize {
            let record = unsafe { &*(buffer.as_ptr().add(offset) as *const UsnRecordV2) };

            if record.record_length == 0 {
                break;
            }

            // Extract UTF-16 file name
            let name_byte_offset = record.file_name_offset as usize;
            let name_char_count = record.file_name_length as usize / 2;
            let name = if name_char_count > 0 && offset + name_byte_offset + name_char_count * 2 <= bytes_returned as usize {
                let name_ptr = unsafe { buffer.as_ptr().add(offset + name_byte_offset) as *const u16 };
                let name_slice = unsafe { std::slice::from_raw_parts(name_ptr, name_char_count) };
                String::from_utf16_lossy(name_slice)
            } else {
                String::new()
            };

            // Lower 48 bits = MFT entry number
            let file_ref = record.file_reference_number & 0x0000_FFFF_FFFF_FFFF;
            let parent_ref = record.parent_file_reference_number & 0x0000_FFFF_FFFF_FFFF;
            let is_dir = (record.file_attributes & FILE_ATTRIBUTE_DIRECTORY) != 0;

            if !name.is_empty() {
                let (name_offset, name_len) = arena.push(&name);
                entries.insert(file_ref, FileEntry { name_offset, name_len, parent_ref, is_dir });
            }

            enum_count += 1;
            if enum_count % 5000 == 0 {
                if let Some(ref cb) = on_event {
                    cb(ScanEvent::Progress(enum_count, 0));
                }
            }

            offset += record.record_length as usize;
        }
    }

    if cancel.load(Ordering::SeqCst) {
        return Err("Scan cancelled".to_string());
    }

    if let Some(ref cb) = on_event {
        cb(ScanEvent::Progress(enum_count, 0));
    }

    // Phase 2: Build full paths (serial — uses mutable path_cache)
    let mut path_cache: HashMap<u64, String> = HashMap::new();
    path_cache.insert(5, drive_letter.to_string());

    let mut file_entries: Vec<(String, String)> = Vec::new();
    let mut path_count: u64 = 0;

    // Collect non-directory IDs first to avoid borrow issues
    let file_ids: Vec<u64> = entries.iter()
        .filter(|(_, e)| !e.is_dir)
        .map(|(id, _)| *id)
        .collect();

    for id in &file_ids {
        if cancel.load(Ordering::SeqCst) {
            return Err("Scan cancelled".to_string());
        }
        let path = build_path(*id, &entries, &arena, &mut path_cache);
        if !path.is_empty() {
            let name = arena.get(entries[id].name_offset, entries[id].name_len).to_owned();
            file_entries.push((name, path));
        }
        path_count += 1;
        if path_count % 50000 == 0 {
            if let Some(ref cb) = on_event {
                cb(ScanEvent::Progress(path_count, 0));
            }
        }
    }

    // Free the two largest allocations before Phase 3
    drop(path_cache);
    drop(entries);
    drop(arena);

    if cancel.load(Ordering::SeqCst) {
        return Err("Scan cancelled".to_string());
    }

    let total_files = file_entries.len() as u64;
    if let Some(ref cb) = on_event {
        cb(ScanEvent::Progress(total_files, 0));
    }

    // Phase 3: Query file sizes in parallel, streaming FileFound events immediately
    let num_threads = (std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4)
        / 2)
        .max(2);

    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(num_threads)
        .build()
        .map_err(|e| format!("Failed to create thread pool: {}", e))?;

    let matched_count = AtomicU64::new(0);
    let checked_count = AtomicU64::new(0);
    let files_collector: Mutex<Vec<FileRecord>> = Mutex::new(Vec::new());

    pool.install(|| {
        file_entries
            .par_iter()
            .for_each(|(name, path)| {
                if cancel.load(Ordering::Relaxed) {
                    return;
                }

                let checked = checked_count.fetch_add(1, Ordering::Relaxed);
                if checked % 5000 == 0 {
                    if let Some(ref cb) = on_event {
                        let matched = matched_count.load(Ordering::Relaxed);
                        cb(ScanEvent::Progress(checked, matched));
                    }
                }

                let size = match std::fs::metadata(path).ok() {
                    Some(m) => m.len(),
                    None => return,
                };
                if size < min_size_bytes {
                    return;
                }

                let record = FileRecord {
                    path: path.clone(),
                    name: name.clone(),
                    size,
                    is_dir: false,
                };

                matched_count.fetch_add(1, Ordering::Relaxed);

                // Stream the file to frontend immediately
                if let Some(ref cb) = on_event {
                    cb(ScanEvent::FileFound(record.clone()));
                }

                files_collector.lock().unwrap().push(record);
            });
    });

    if cancel.load(Ordering::SeqCst) {
        return Err("Scan cancelled".to_string());
    }

    let mut files = files_collector.into_inner().unwrap();

    // Partial sort: O(M + N log N) instead of O(M log M)
    if files.len() > top_n {
        files.select_nth_unstable_by(top_n, |a, b| b.size.cmp(&a.size));
        files.truncate(top_n);
    }
    files.sort_unstable_by(|a, b| b.size.cmp(&a.size));

    Ok(files)
}

fn build_path(
    file_ref: u64,
    entries: &HashMap<u64, FileEntry>,
    arena: &StringArena,
    cache: &mut HashMap<u64, String>,
) -> String {
    if let Some(cached) = cache.get(&file_ref) {
        return cached.clone();
    }

    let entry = match entries.get(&file_ref) {
        Some(e) => e,
        None => return String::new(),
    };

    // Prevent infinite loops (self-referencing parents)
    if entry.parent_ref == file_ref {
        return String::new();
    }

    let parent_path = build_path(entry.parent_ref, entries, arena, cache);
    if parent_path.is_empty() && entry.parent_ref != 5 {
        // Parent not found and not root — orphaned entry
        return String::new();
    }

    let name = arena.get(entry.name_offset, entry.name_len);
    let full_path = if parent_path.is_empty() {
        name.to_owned()
    } else {
        format!("{}\\{}", parent_path, name)
    };

    cache.insert(file_ref, full_path.clone());
    full_path
}
