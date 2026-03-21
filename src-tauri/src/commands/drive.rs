use serde::Serialize;

#[derive(Serialize)]
pub struct DriveInfo {
    drive: String,
    total: u64,
    used: u64,
    free: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

#[tauri::command]
pub fn get_drive_info(drive: String) -> DriveInfo {
    #[cfg(windows)]
    {
        use std::ffi::OsStr;
        use std::os::windows::ffi::OsStrExt;

        let wide: Vec<u16> = OsStr::new(&drive)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect();

        let mut free_bytes: u64 = 0;
        let mut total_bytes: u64 = 0;
        let mut total_free_bytes: u64 = 0;

        let ok = unsafe {
            windows_sys::Win32::Storage::FileSystem::GetDiskFreeSpaceExW(
                wide.as_ptr(),
                &mut free_bytes as *mut u64,
                &mut total_bytes as *mut u64,
                &mut total_free_bytes as *mut u64,
            )
        };

        if ok != 0 {
            return DriveInfo {
                drive,
                total: total_bytes,
                used: total_bytes - total_free_bytes,
                free: total_free_bytes,
                error: None,
            };
        }
    }

    // Fallback for non-Windows or if the call fails
    DriveInfo {
        drive,
        total: 0,
        used: 0,
        free: 0,
        error: Some("Could not retrieve drive info".to_string()),
    }
}
