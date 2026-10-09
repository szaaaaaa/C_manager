use serde::{Deserialize, Serialize};
use crate::safety::{file_context, lookup_knowledge, rate_safety};

use super::local_llm::LocalLlmState;

/// Search Tavily API for context about an unknown file. Returns a short summary.
async fn tavily_search(query: &str, api_key: &str) -> Result<String, String> {
    let client = reqwest::Client::new();
    let payload = serde_json::json!({
        "query": query,
        "search_depth": "basic",
        "max_results": 3,
        "include_answer": true,
    });

    let resp = client
        .post("https://api.tavily.com/search")
        .header("Content-Type", "application/json")
        .header("Authorization", format!("Bearer {}", api_key))
        .json(&payload)
        .send()
        .await
        .map_err(|e| format!("Tavily request failed: {}", e))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("Tavily API error {}: {}", status, body));
    }

    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("Failed to parse Tavily response: {}", e))?;

    // Prefer the built-in answer; fall back to concatenating result snippets
    if let Some(answer) = data["answer"].as_str() {
        if !answer.is_empty() {
            return Ok(answer.to_string());
        }
    }

    let snippets: Vec<&str> = data["results"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|r| r["content"].as_str())
                .collect()
        })
        .unwrap_or_default();

    if snippets.is_empty() {
        return Err("Tavily returned no results".to_string());
    }

    // Truncate to ~500 chars to fit in prompt
    let combined: String = snippets.join(" ");
    Ok(combined.chars().take(500).collect())
}

#[derive(Serialize)]
pub struct ExplainResponse {
    path: String,
    safety: String,
    size_human: String,
    explanation: String,
    backend_used: String,
}

use super::{format_size, validate_base_url};

pub(super) fn build_prompt(path: &str, size_human: &str, is_dir: bool, safety: &str, search_context: Option<&str>) -> Vec<serde_json::Value> {
    let kind = if is_dir { "文件夹" } else { "文件" };
    let name = path.rsplit(['\\', '/']).next().unwrap_or(path);
    let (safety_verdict, safety_desc) = match safety {
        "red" => ("千万别删", "系统核心文件，删除可能导致系统崩溃或无法启动"),
        "yellow" => ("看看再删", "用途或删除影响需要确认，可能包含软件或个人数据"),
        "green" => ("可清理", "疑似可清理的缓存、临时文件或残留，仍需确认是否在用或需要保留"),
        _ => ("看看再删", "无法确定安全性"),
    };

    let parts: Vec<&str> = path.split(['\\', '/']).collect();
    let parent_chain = if parts.len() > 3 {
        parts[parts.len().saturating_sub(4)..parts.len().saturating_sub(1)].join("\\")
    } else {
        parts[..parts.len().saturating_sub(1)].join("\\")
    };

    let search_section = match search_context {
        Some(ctx) => format!("\n\n以下是网络搜索到的参考资料，请据此回答（如果搜索结果与文件无关则忽略）：\n{}", ctx),
        None => String::new(),
    };

    let instruction = format!(
        "你是一个帮普通用户看懂电脑文件的助手。根据完整路径解释这个{kind}的用途、删除影响和处理建议。\n\
         像懂电脑的朋友一样，用两到四句自然中文回答，不用固定标签或重复安全判定。\n\
         优先依据用途资料，不补写资料没有说明的具体功能或恢复保证；没有匹配资料时明确说无法确定。\n\
         规则判定是{verdict}。路径不足以确认用途时直说无法确定，不要编造软件名、功能或恢复方式。涉及个人数据时先提醒确认备份。",
        kind = kind, verdict = safety_verdict,
    );
    let input = format!(
        "{kind}名：{name}\n完整路径：{path}\n所在目录：{parent}\n大小：{size}\n初步分类：{safety_desc}\n\n用途资料：\n{facts}{search}",
        kind = kind, name = name, path = path, parent = parent_chain,
        size = size_human, safety_desc = safety_desc, facts = file_context(path), search = search_section,
    );
    vec![
        serde_json::json!({"role": "system", "content": instruction}),
        serde_json::json!({"role": "user", "content": input}),
    ]
}

fn path_is_known(path: &str) -> bool {
    lookup_knowledge(path).is_some()
}

/// Call OpenAI-compatible API (/chat/completions) for cloud providers
async fn call_cloud_llm(
    messages: Vec<serde_json::Value>,
    api_key: &str,
    base_url: &str,
    model: &str,
) -> Result<String, String> {
    let payload = serde_json::json!({
        "model": model,
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.7,
    });

    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{}/chat/completions", base_url))
        .header("Authorization", format!("Bearer {}", api_key))
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

    Ok(data["choices"][0]["message"]["content"]
        .as_str()
        .unwrap_or("无法获取回复")
        .trim()
        .to_string())
}

fn resolve_key(api_key: &str) -> Result<String, String> {
    if !api_key.is_empty() {
        Ok(api_key.to_string())
    } else {
        std::env::var("OPENROUTER_API_KEY")
            .or_else(|_| std::env::var("OPENAI_API_KEY"))
            .map_err(|_| "No API key provided".to_string())
    }
}

#[tauri::command]
pub async fn explain_item(
    path: String,
    size_bytes: u64,
    is_dir: bool,
    api_key: String,
    base_url: String,
    model: String,
    use_local: bool,
    tavily_key: String,
    state: tauri::State<'_, LocalLlmState>,
) -> Result<ExplainResponse, String> {
    let safety = rate_safety(&path).to_string();
    let size_human = format_size(size_bytes);

    let explanation = if use_local {
        // Pre-check: if path is unknown to training data AND Tavily key available,
        // search first to give the model real context (avoid hallucination)
        let search_context = if !tavily_key.is_empty() && !path_is_known(&path) {
            let file_name = path.rsplit('\\').next().unwrap_or(&path);
            let query = format!("Windows文件 {} 是什么 能否删除", file_name);
            match tavily_search(&query, &tavily_key).await {
                Ok(ctx) => Some(ctx),
                Err(_) => None,
            }
        } else {
            None
        };

        let messages = build_prompt(&path, &size_human, is_dir, &safety, search_context.as_deref());

        let inner = state.inner.clone();
        tokio::task::spawn_blocking(move || {
            super::local_llm::infer_blocking(&inner, &messages)
        })
        .await
        .map_err(|e| format!("推理任务失败: {}", e))??
    } else {
        let messages = build_prompt(&path, &size_human, is_dir, &safety, None);
        let key = resolve_key(&api_key)?;
        validate_base_url(&base_url)?;
        call_cloud_llm(messages, &key, &base_url, &model).await?
    };

    Ok(ExplainResponse {
        path,
        safety,
        size_human,
        explanation,
        backend_used: if use_local { "local".to_string() } else { "api".to_string() },
    })
}

#[derive(Deserialize)]
pub struct ChatMessage {
    role: String,
    content: String,
}

#[tauri::command]
pub async fn chat_about_file(
    path: String,
    size_bytes: u64,
    is_dir: bool,
    history: Vec<ChatMessage>,
    user_message: String,
    api_key: String,
    base_url: String,
    model: String,
    use_local: bool,
    tavily_key: String,
    state: tauri::State<'_, LocalLlmState>,
) -> Result<String, String> {
    let safety = rate_safety(&path).to_string();
    let size_human = format_size(size_bytes);

    let name = path.rsplit('\\').next().unwrap_or(&path);

    // For chat, search if user is asking about something the model might not know
    // Only on first turn and only for local model
    let search_section = if use_local && !tavily_key.is_empty() && history.is_empty() {
        // Check if the user's question hints at needing more context
        let query = format!("Windows {} {} {}", name, user_message, "是什么");
        match tavily_search(&query, &tavily_key).await {
            Ok(ctx) => format!("\n\n网络搜索参考资料：\n{}", ctx),
            Err(_) => String::new(),
        }
    } else {
        String::new()
    };

    let mut messages = build_prompt(&path, &size_human, is_dir, &safety,
        if search_section.is_empty() { None } else { Some(&search_section) });
    for msg in &history {
        if !matches!(msg.role.as_str(), "user" | "assistant") {
            return Err("对话历史只支持 user 和 assistant 角色".to_string());
        }
        messages.push(serde_json::json!({"role": msg.role, "content": msg.content}));
    }
    messages.push(serde_json::json!({"role": "user", "content": user_message}));

    if use_local {
        let inner = state.inner.clone();
        let msgs = messages.clone();
        tokio::task::spawn_blocking(move || {
            super::local_llm::infer_blocking(&inner, &msgs)
        })
        .await
        .map_err(|e| format!("推理任务失败: {}", e))?
    } else {
        let key = resolve_key(&api_key)?;
        validate_base_url(&base_url)?;
        call_cloud_llm(messages, &key, &base_url, &model).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generic_directories_do_not_skip_context_search() {
        assert!(!path_is_known("C:\\Users\\User\\AppData\\Local\\UnknownApp\\data.db"));
        assert!(!path_is_known("C:\\Program Files\\UnknownApp\\model.bin"));
        assert!(!path_is_known("C:\\Users\\User\\Documents\\cache.db"));
        assert!(!path_is_known("C:\\Program Files\\Microsoft\\UnknownApp\\data.bin"));
        assert!(path_is_known("C:\\Users\\User\\AppData\\Local\\pip\\cache\\download.body"));
    }

    #[test]
    fn explanations_and_chat_receive_verified_context() {
        let messages = build_prompt("C:/Users/User/AppData/Local/Microsoft/OneNote/16.0/cache",
            "200 MB", true, "yellow", None);
        assert!(messages[1]["content"].as_str().unwrap().contains("尚未同步"));
        assert!(messages[1]["content"].as_str().unwrap().contains("Microsoft\\OneNote\\16.0"));
        let unknown = build_prompt("C:\\Users\\User\\Documents\\archive.bin", "200 MB", false, "yellow", None);
        assert!(unknown[1]["content"].as_str().unwrap().contains("没有匹配到"));
    }
}
