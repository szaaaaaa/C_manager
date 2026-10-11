mod commands;
pub mod safety;
pub mod scanner;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(commands::scan::ScanState::default())
        .manage(commands::local_llm::LocalLlmState::new())
        .invoke_handler(tauri::generate_handler![
            commands::admin::check_admin,
            commands::classification::classify_files,
            commands::admin::relaunch_as_admin,
            commands::scan::scan_drive,
            commands::scan::get_scan_results,
            commands::scan::cancel_scan,
            commands::drive::get_drive_info,
            commands::explain::explain_item,
            commands::explain::prepare_explanation,
            commands::models::fetch_models,
            commands::models::get_env_key,
            commands::explorer::open_in_explorer,
            commands::explorer::delete_to_recycle_bin,
            commands::local_llm::list_local_models,
            commands::local_llm::init_local_model,
            commands::local_llm::get_local_model_status,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
