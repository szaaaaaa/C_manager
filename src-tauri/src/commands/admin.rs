/// Check if the current process is running with admin privileges.
#[tauri::command]
pub fn check_admin() -> bool {
    #[cfg(windows)]
    {
        is_elevated()
    }
    #[cfg(not(windows))]
    {
        false
    }
}

/// Re-launch the current executable as administrator via UAC prompt.
#[tauri::command]
pub fn relaunch_as_admin(app: tauri::AppHandle) -> Result<(), String> {
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;

        let exe = std::env::current_exe()
            .map_err(|e| format!("Failed to get exe path: {}", e))?;

        let exe_wide: Vec<u16> = exe
            .as_os_str()
            .encode_wide()
            .chain(std::iter::once(0))
            .collect();

        let verb: Vec<u16> = "runas\0".encode_utf16().collect();

        let result = unsafe {
            windows_sys::Win32::UI::Shell::ShellExecuteW(
                std::ptr::null_mut(),
                verb.as_ptr(),
                exe_wide.as_ptr(),
                std::ptr::null(),
                std::ptr::null(),
                1, // SW_SHOWNORMAL
            )
        };

        if result as usize > 32 {
            // New admin process launched — gracefully exit this one
            app.exit(0);
            Ok(())
        } else {
            Err("UAC elevation was cancelled or failed".to_string())
        }
    }

    #[cfg(not(windows))]
    {
        let _ = app;
        Err("Admin elevation not supported on this platform".to_string())
    }
}

#[cfg(windows)]
fn is_elevated() -> bool {
    use windows_sys::Win32::Security::{GetTokenInformation, TokenElevation, TOKEN_ELEVATION, TOKEN_QUERY};
    use windows_sys::Win32::System::Threading::{GetCurrentProcess, OpenProcessToken};

    unsafe {
        let mut token = std::ptr::null_mut();
        if OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) == 0 {
            return false;
        }

        // Ensure CloseHandle is called regardless of how we exit this scope
        struct HandleGuard(*mut core::ffi::c_void);
        impl Drop for HandleGuard {
            fn drop(&mut self) {
                unsafe { windows_sys::Win32::Foundation::CloseHandle(self.0); }
            }
        }
        let _guard = HandleGuard(token);

        let mut elevation = TOKEN_ELEVATION { TokenIsElevated: 0 };
        let mut size = 0u32;
        let ok = GetTokenInformation(
            token,
            TokenElevation,
            &mut elevation as *mut _ as *mut _,
            std::mem::size_of::<TOKEN_ELEVATION>() as u32,
            &mut size,
        );

        ok != 0 && elevation.TokenIsElevated != 0
    }
}
