use serde::Serialize;

#[derive(Serialize)]
pub struct ModelInfo {
    id: String,
    name: String,
    context_length: u64,
}

#[derive(Serialize)]
pub struct EnvKeyInfo {
    has_env_key: bool,
    source: Option<String>,
}

#[tauri::command]
pub async fn fetch_models(
    api_key: String,
    base_url: String,
) -> Result<Vec<ModelInfo>, String> {
    let key = if !api_key.is_empty() {
        api_key
    } else {
        std::env::var("OPENROUTER_API_KEY")
            .or_else(|_| std::env::var("OPENAI_API_KEY"))
            .map_err(|_| "API key required to fetch models".to_string())?
    };

    let client = reqwest::Client::new();
    let resp = client
        .get(format!("{}/models", base_url))
        .header("Authorization", format!("Bearer {}", key))
        .send()
        .await
        .map_err(|e| format!("Failed to fetch models: {}", e))?;

    if !resp.status().is_success() {
        return Err(format!("Models API error: {}", resp.status()));
    }

    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("Failed to parse models response: {}", e))?;

    let models_array = data["data"].as_array().unwrap_or(&Vec::new()).clone();

    let models: Vec<ModelInfo> = models_array
        .iter()
        .filter_map(|m| {
            Some(ModelInfo {
                id: m["id"].as_str()?.to_string(),
                name: m["name"]
                    .as_str()
                    .unwrap_or(m["id"].as_str()?)
                    .to_string(),
                context_length: m["context_length"].as_u64().unwrap_or(0),
            })
        })
        .collect();

    Ok(models)
}

#[tauri::command]
pub fn get_env_key() -> EnvKeyInfo {
    if std::env::var("OPENROUTER_API_KEY").is_ok() {
        EnvKeyInfo {
            has_env_key: true,
            source: Some("OPENROUTER_API_KEY".to_string()),
        }
    } else if std::env::var("OPENAI_API_KEY").is_ok() {
        EnvKeyInfo {
            has_env_key: true,
            source: Some("OPENAI_API_KEY".to_string()),
        }
    } else {
        EnvKeyInfo {
            has_env_key: false,
            source: None,
        }
    }
}
