use serde::{Deserialize, Serialize};
use crate::safety::rate_safety;

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

fn build_prompt(path: &str, size_human: &str, is_dir: bool, safety: &str, search_context: Option<&str>) -> String {
    let kind = if is_dir { "文件夹" } else { "文件" };
    let name = path.rsplit('\\').next().unwrap_or(path);
    let (safety_verdict, safety_desc) = match safety {
        "red" => ("千万别删", "系统核心文件，删除可能导致系统崩溃或无法启动"),
        "yellow" => ("看看再删", "属于某个软件或服务，如果用户不再使用该软件可以考虑删除"),
        "green" => ("放心删", "缓存、临时文件或残留数据，删除不影响任何功能"),
        _ => ("看看再删", "无法确定安全性"),
    };

    let parts: Vec<&str> = path.split('\\').collect();
    let parent_chain = if parts.len() > 3 {
        parts[parts.len().saturating_sub(4)..parts.len().saturating_sub(1)].join("\\")
    } else {
        parts[..parts.len().saturating_sub(1)].join("\\")
    };

    let search_section = match search_context {
        Some(ctx) => format!("\n\n以下是网络搜索到的参考资料，请据此回答（如果搜索结果与文件无关则忽略）：\n{}", ctx),
        None => String::new(),
    };

    format!(
        "你是一个帮普通用户看懂电脑文件的助手。用户发现C盘里有个占空间的{kind}，看不懂是什么，需要你用大白话解释。\n\n\
         请用自然的中文写一段话（不要用【】标签），按这个顺序说清楚：\n\
         1. 第一句：这是「XX软件」的什么数据（必须从路径推断出具体软件名，如 .claude→Claude Desktop，Trae→Trae AI编程助手，torch→PyTorch）\n\
         2. 第二句：用大白话说这个数据具体干什么用的，别说\"缓存\"\"配置\"这种笼统词，要说清对用户意味着什么\n\
         3. 空一行，单独写判定：{verdict}\n\
         4. 接着自然地说：删了会怎样（具体影响哪个功能），如果不用这个软件了怎么处理，删了之后能不能恢复\n\n\
         语气要求：像一个懂电脑的朋友在跟你解释，简洁但不冷冰冰。总共不超过100字。\n\n\
         {kind}名：{name}\n完整路径：{path}\n所在目录：{parent}\n大小：{size}\n初步分类：{safety_desc}{search}",
        kind = kind,
        verdict = safety_verdict,
        name = name,
        path = path,
        parent = parent_chain,
        size = size_human,
        safety_desc = safety_desc,
        search = search_section,
    )
}

/// Check if a file path contains recognizable software/directory keywords
/// that the local model was trained on. If not, the model likely needs
/// web search context to avoid hallucination.
fn path_is_known(path: &str) -> bool {
    let lower = path.to_lowercase();

    // Well-known software and directory patterns covered by training data
    const KNOWN_PATTERNS: &[&str] = &[
        // OS & System
        "windows", "system32", "syswow64", "winsxs", "boot", "efi",
        "pagefile", "hiberfil", "swapfile", "ntoskrnl",
        // Dev tools
        ".cargo", ".rustup", "python", "node_modules", "npm", ".venv",
        "anaconda", "miniforge", "conda", "pip", ".git", "docker",
        "java", "jdk", "gradle", "maven", ".m2", "go-build",
        // AI/ML
        "huggingface", "torch", "pytorch", "tensorflow", "ollama",
        "llama", "gguf", "safetensors", "onnx", "cuda", "cudnn",
        "nvidia", "model", "lora", "stable-diffusion", "gpt4all",
        // Browsers
        "chrome", "edge", "firefox", "brave", "opera", "vivaldi",
        "qqbrowser", "360chrome",
        // Apps - Communication
        "wechat", "weixin", "qq", "tencent", "dingtalk", "feishu",
        "telegram", "discord", "slack", "teams", "wemeet", "zoom",
        // Apps - Productivity
        "microsoft", "office", "onedrive", "onenote", "outlook",
        "wps", "adobe", "photoshop", "premiere", "autocad", "autodesk",
        "notion", "obsidian", "evernote", "typora", "logseq", "xmind",
        // Apps - Media
        "spotify", "steam", "epic", "blender", "obs-studio", "vlc",
        "potplayer", "audacity", "davinci", "handbrake",
        // Apps - Chinese software
        "baidu", "sogou", "youdao", "kuaishou", "douyin", "iqiyi",
        "quark", "thunder", "sunlogin", "todesk", "kingsoft", "2345",
        "lenovo", "asus", "dell",
        // Apps - Dev/IDE
        ".vscode", "cursor", "trae", "windsurf", "jetbrains",
        "intellij", "pycharm", "visual studio", "codex",
        // Cloud & VM
        "wsl", "lxss", "hyper-v", "virtualbox", "vmware",
        ".vhdx", "ubuntu",
        // Games
        "steamapps", "epic games", "riot", "valorant", "fortnite",
        "genshin", "cyberpunk", "battlefield", "counter-strike",
        // System paths
        "appdata", "program files", "programdata", "temp", "cache",
        "downloads", "$recycle.bin", "prefetch", "driverstore",
        // Claude
        ".claude", "claude",
    ];

    KNOWN_PATTERNS.iter().any(|pat| lower.contains(pat))
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

        let prompt = build_prompt(&path, &size_human, is_dir, &safety, search_context.as_deref());
        let messages = vec![serde_json::json!({"role": "user", "content": prompt})];

        let inner = state.inner.clone();
        tokio::task::spawn_blocking(move || {
            super::local_llm::infer_blocking(&inner, &messages)
        })
        .await
        .map_err(|e| format!("推理任务失败: {}", e))??
    } else {
        let prompt = build_prompt(&path, &size_human, is_dir, &safety, None);
        let messages = vec![serde_json::json!({"role": "user", "content": prompt})];
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

    let kind = if is_dir { "文件夹" } else { "文件" };
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

    let system_msg = format!(
        "你是Windows文件助手，正在帮用户分析一个{}。\n\
         文件名：{}\n路径：{}\n大小：{}\n安全分类：{}{}\n\n\
         用简洁的中文回答用户的追问，不超过3句话。",
        kind, name, path, size_human, safety, search_section
    );

    let mut messages: Vec<serde_json::Value> = vec![
        serde_json::json!({"role": "system", "content": system_msg}),
    ];
    for msg in &history {
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
