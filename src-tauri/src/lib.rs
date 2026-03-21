mod commands;
mod safety;
mod scanner;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            commands::scan::scan_drive,
            commands::drive::get_drive_info,
            commands::explain::explain_item,
            commands::models::fetch_models,
            commands::models::get_env_key,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
