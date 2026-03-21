use serde::Serialize;
use crate::safety::rate_safety;

#[derive(Serialize)]
pub struct ExplainResponse {
    path: String,
    safety: String,
    size_human: String,
    explanation: String,
    backend_used: String,
}

fn format_size(bytes: u64) -> String {
    let units = ["B", "KB", "MB", "GB", "TB"];
    let mut size = bytes as f64;
    for unit in &units {
        if size < 1024.0 {
            return format!("{:.1} {}", size, unit);
        }
        size /= 1024.0;
    }
    format!("{:.1} PB", size)
}

fn build_prompt(path: &str, size_human: &str, is_dir: bool, safety: &str) -> String {
    let safety_label = match safety {
        "red" => "\u{1f534}系统核心",
        "yellow" => "\u{1f7e1}建议保留",
        "green" => "\u{1f7e2}可以清理",
        _ => "\u{1f7e1}建议保留",
    };
    let kind = if is_dir { "文件夹" } else { "文件" };
    let name = path.rsplit('\\').next().unwrap_or(path);

    format!(
        "你是一个帮助普通用户理解Windows C盘文件的助手。\n\
         用通俗幽默的中文大白话（2-4句话）解释以下{}是什么用途，普通用户看不懂英文名时应该怎么理解它：\n\n\
         文件路径: {}\n\
         文件名: {}\n\
         大小: {}\n\
         安全评级: {}\n\n\
         要求：\n\
         1. 用类比和生活化的比喻解释\n\
         2. 说明为什么占这么多空间（如果合理的话）\n\
         3. 根据安全评级给出建议（红色=绝对别碰，黄色=谨慎，绿色=可以清）\n\
         4. 语气轻松，像朋友聊天\n\
         5. 不超过4句话",
        kind, path, name, size_human, safety_label
    )
}

#[tauri::command]
pub async fn explain_item(
    path: String,
    size_bytes: u64,
    is_dir: bool,
    api_key: String,
    base_url: String,
    model: String,
) -> Result<ExplainResponse, String> {
    let safety = rate_safety(&path).to_string();
    let size_human = format_size(size_bytes);

    // Resolve API key: param > env
    let key = if !api_key.is_empty() {
        api_key
    } else {
        std::env::var("OPENROUTER_API_KEY")
            .or_else(|_| std::env::var("OPENAI_API_KEY"))
            .map_err(|_| "No API key provided. Set OPENROUTER_API_KEY env var or enter key in settings.".to_string())?
    };

    let prompt = build_prompt(&path, &size_human, is_dir, &safety);

    let payload = serde_json::json!({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
        "temperature": 0.7,
    });

    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{}/chat/completions", base_url))
        .header("Authorization", format!("Bearer {}", key))
        .header("Content-Type", "application/json")
        .json(&payload)
        .send()
        .await
        .map_err(|e| format!("LLM request failed: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("LLM API error {}: {}", status, body));
    }

    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("Failed to parse LLM response: {}", e))?;

    let explanation = data["choices"][0]["message"]["content"]
        .as_str()
        .unwrap_or("无法获取解释")
        .trim()
        .to_string();

    Ok(ExplainResponse {
        path,
        safety,
        size_human,
        explanation,
        backend_used: "api".to_string(),
    })
}
