use serde::Serialize;

/// Open file/folder location in Windows Explorer with the item selected.
#[tauri::command]
pub fn open_in_explorer(path: String) -> Result<(), String> {
    #[cfg(windows)]
    {
        std::process::Command::new("explorer")
            .arg("/select,")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("无法打开资源管理器: {}", e))?;
        Ok(())
    }
    #[cfg(not(windows))]
    {
        Err("仅支持 Windows".to_string())
    }
}

#[derive(Serialize)]
pub struct DeleteResult {
    pub succeeded: Vec<String>,
    pub failed: Vec<DeleteError>,
}

#[derive(Serialize)]
pub struct DeleteError {
    pub path: String,
    pub error: String,
}

/// Move files to Windows Recycle Bin (recoverable).
#[tauri::command]
pub async fn delete_to_recycle_bin(paths: Vec<String>) -> Result<DeleteResult, String> {
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;
        use std::ffi::OsStr;

        let mut succeeded = Vec::new();
        let mut failed = Vec::new();

        for path in &paths {
            // SHFileOperationW requires double-null-terminated wide string
            let wide: Vec<u16> = OsStr::new(path)
                .encode_wide()
                .chain(std::iter::once(0))
                .chain(std::iter::once(0))
                .collect();

            let mut op = windows_sys::Win32::UI::Shell::SHFILEOPSTRUCTW {
                hwnd: std::ptr::null_mut(),
                wFunc: windows_sys::Win32::UI::Shell::FO_DELETE,
                pFrom: wide.as_ptr(),
                pTo: std::ptr::null(),
                fFlags: (windows_sys::Win32::UI::Shell::FOF_ALLOWUNDO  // → Recycle Bin
                    | windows_sys::Win32::UI::Shell::FOF_NOCONFIRMATION
                    | windows_sys::Win32::UI::Shell::FOF_SILENT) as u16,
                fAnyOperationsAborted: 0,
                hNameMappings: std::ptr::null_mut(),
                lpszProgressTitle: std::ptr::null(),
            };

            let ret = unsafe { windows_sys::Win32::UI::Shell::SHFileOperationW(&mut op) };
            if ret == 0 && op.fAnyOperationsAborted == 0 {
                succeeded.push(path.clone());
            } else {
                failed.push(DeleteError {
                    path: path.clone(),
                    error: format!("SHFileOperation 返回码: {}", ret),
                });
            }
        }

        Ok(DeleteResult { succeeded, failed })
    }
    #[cfg(not(windows))]
    {
        Err("仅支持 Windows".to_string())
    }
}
