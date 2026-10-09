use std::num::NonZeroU32;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use llama_cpp_2::context::params::LlamaContextParams;
use llama_cpp_2::llama_backend::LlamaBackend;
use llama_cpp_2::llama_batch::LlamaBatch;
use llama_cpp_2::model::params::LlamaModelParams;
use llama_cpp_2::model::{AddBos, LlamaModel};
use llama_cpp_2::sampling::LlamaSampler;
use serde::Serialize;
use tauri::Manager;

const MODEL_FILENAME: &str = "qwen3.5-0.8b-q4_k_m.gguf";
const CTX_SIZE: u32 = 2048;
const MAX_RESPONSE_TOKENS: usize = 512;

pub struct LoadedModel {
    backend: LlamaBackend,
    model: LlamaModel,
}

// llama.cpp model is thread-safe for reading (creating contexts).
// The Mutex serializes access, making this safe.
unsafe impl Send for LoadedModel {}

pub struct LocalLlmState {
    pub inner: Arc<Mutex<Option<LoadedModel>>>,
}

impl LocalLlmState {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(Mutex::new(None)),
        }
    }
}

#[derive(Serialize, Clone)]
pub struct LocalModelInfo {
    pub loaded: bool,
    pub model_name: String,
    pub error: Option<String>,
}

/// Find model GGUF file. Checks:
/// Fresh training output in dev mode, then the bundled resource.
fn find_model_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    #[cfg(debug_assertions)]
    {
        let project = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        candidates.push(project.join("..").join("lora-training").join("output")
            .join("finetuned_model_gguf").join(MODEL_FILENAME));
        candidates.push(project.join("resources").join(MODEL_FILENAME));
    }
    // Production: Tauri bundled resource
    if let Ok(dir) = app.path().resource_dir() {
        candidates.push(dir.join("resources").join(MODEL_FILENAME));
    }
    for candidate in &candidates {
        if candidate.is_file() {
            return Ok(candidate.clone());
        }
    }

    Err(format!(
        "未找到模型文件 {}。请将 GGUF 模型放入 src-tauri/resources/ 目录。",
        MODEL_FILENAME
    ))
}

#[tauri::command]
pub async fn init_local_model(
    app: tauri::AppHandle,
    state: tauri::State<'_, LocalLlmState>,
) -> Result<LocalModelInfo, String> {
    // Check if already loaded
    {
        let guard = state.inner.lock().map_err(|e| e.to_string())?;
        if guard.is_some() {
            return Ok(LocalModelInfo {
                loaded: true,
                model_name: MODEL_FILENAME.to_string(),
                error: None,
            });
        }
    }

    let model_path = find_model_path(&app)?;
    let model_path_clone = model_path.clone();

    // Load model in blocking thread (takes 1-2 seconds)
    let loaded = tokio::task::spawn_blocking(move || -> Result<LoadedModel, String> {
        let backend =
            LlamaBackend::init().map_err(|e| format!("llama.cpp 初始化失败: {}", e))?;

        let model_params = LlamaModelParams::default();
        let model =
            LlamaModel::load_from_file(&backend, &model_path_clone, &model_params)
                .map_err(|e| format!("模型加载失败: {}", e))?;

        Ok(LoadedModel { backend, model })
    })
    .await
    .map_err(|e| format!("加载任务失败: {}", e))??;

    let mut guard = state.inner.lock().map_err(|e| e.to_string())?;
    *guard = Some(loaded);

    Ok(LocalModelInfo {
        loaded: true,
        model_name: MODEL_FILENAME.to_string(),
        error: None,
    })
}

#[tauri::command]
pub fn get_local_model_status(
    state: tauri::State<'_, LocalLlmState>,
) -> LocalModelInfo {
    let guard = state.inner.lock().unwrap_or_else(|e| e.into_inner());
    LocalModelInfo {
        loaded: guard.is_some(),
        model_name: MODEL_FILENAME.to_string(),
        error: None,
    }
}

/// Format messages into Qwen ChatML prompt
fn format_chatml(messages: &[serde_json::Value]) -> String {
    let mut prompt = String::new();
    for msg in messages {
        let role = msg["role"].as_str().unwrap_or("user");
        let content = msg["content"].as_str().unwrap_or("");
        prompt.push_str(&format!("<|im_start|>{}\n{}<|im_end|>\n", role, content));
    }
    // Prompt the model to generate assistant response
    prompt.push_str("<|im_start|>assistant\n<think>\n\n</think>\n\n");
    prompt
}

/// Run inference on the loaded model. Called from explain.rs.
/// Takes Arc<Mutex<...>> so it can be used from spawn_blocking.
pub fn infer_blocking(inner: &Arc<Mutex<Option<LoadedModel>>>, messages: &[serde_json::Value]) -> Result<String, String> {
    let guard = inner.lock().map_err(|e| e.to_string())?;
    let loaded = guard.as_ref().ok_or("本地模型未加载，请先在设置中点击「加载模型」")?;

    let prompt = format_chatml(messages);

    let ctx_params = LlamaContextParams::default()
        .with_n_ctx(NonZeroU32::new(CTX_SIZE))
        .with_n_batch(CTX_SIZE);

    let mut ctx = loaded
        .model
        .new_context(&loaded.backend, ctx_params)
        .map_err(|e| format!("创建推理上下文失败: {}", e))?;

    // Tokenize prompt
    let tokens = loaded
        .model
        .str_to_token(&prompt, AddBos::Never)
        .map_err(|e| format!("分词失败: {}", e))?;

    if tokens.len() >= CTX_SIZE as usize {
        return Err("输入过长，超出模型上下文限制".to_string());
    }

    // Feed prompt tokens
    let mut batch = LlamaBatch::new(CTX_SIZE as usize, 1);
    for (i, &token) in tokens.iter().enumerate() {
        let is_last = i == tokens.len() - 1;
        batch
            .add(token, i as i32, &[0], is_last)
            .map_err(|e| format!("batch 添加失败: {}", e))?;
    }
    ctx.decode(&mut batch)
        .map_err(|e| format!("prompt 解码失败: {}", e))?;

    // Sampling loop
    let mut sampler = LlamaSampler::chain_simple([
        LlamaSampler::temp(0.3),
        LlamaSampler::top_p(0.9, 1),
        LlamaSampler::dist(0),
    ]);

    let mut output = Vec::new();
    let mut n_decoded = tokens.len();

    for _ in 0..MAX_RESPONSE_TOKENS.min(CTX_SIZE as usize - tokens.len()) {
        let token = sampler.sample(&ctx, -1);
        sampler.accept(token);

        if loaded.model.is_eog_token(token) {
            break;
        }

        // Tokens may contain only part of a UTF-8 character; decode after collecting the bytes.
        let piece = loaded
            .model
            .token_to_piece_bytes(token, 1024, false, None)
            .map_err(|e| format!("token 解码失败: {}", e))?;
        output.extend_from_slice(&piece);
        n_decoded += 1;
        if n_decoded >= CTX_SIZE as usize {
            break;
        }

        // Prepare next decode step
        batch.clear();
        batch
            .add(token, n_decoded as i32 - 1, &[0], true)
            .map_err(|e| format!("batch 添加失败: {}", e))?;
        ctx.decode(&mut batch)
            .map_err(|e| format!("解码失败: {}", e))?;
    }

    // Strip Qwen3.5's <think>...</think> blocks
    let output = String::from_utf8_lossy(&output);
    let mut result = output.trim().to_string();
    while let Some(start) = result.find("<think>") {
        if let Some(end) = result.find("</think>") {
            result = format!("{}{}", &result[..start], &result[end + 8..]);
        } else {
            // Unclosed <think> tag — remove from <think> to end
            result = result[..start].to_string();
            break;
        }
    }
    // Strip verdict lines — safety badge is already shown in the UI
    let verdict_keywords = ["千万别删", "看看再删", "放心删"];
    let result: String = result
        .lines()
        .filter(|line| {
            let trimmed = line.trim();
            !verdict_keywords.iter().any(|kw| trimmed == *kw)
        })
        .collect::<Vec<_>>()
        .join("\n")
        .trim()
        .to_string();

    if result.is_empty() {
        return Err("模型返回空内容".to_string());
    }

    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[ignore = "requires the local GGUF model"]
    fn local_model_chinese_and_explanation_smoke() {
        let backend = LlamaBackend::init().unwrap();
        let path = std::env::var_os("C_MANAGER_TEST_MODEL").map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources").join(MODEL_FILENAME));
        let model = LlamaModel::load_from_file(&backend, path, &LlamaModelParams::default()).unwrap();
        let text = "这是浏览器缓存，保存网页图片。🧪";
        let tokens = model.str_to_token(text, AddBos::Never).unwrap();
        let decoded: Vec<u8> = tokens.iter().flat_map(|t| model.token_to_piece_bytes(*t, 1024, false, None).unwrap()).collect();
        assert_eq!(String::from_utf8(decoded).unwrap(), text);
        let inner = Arc::new(Mutex::new(Some(LoadedModel { backend, model })));
        let cases: &[(&str, bool, &str, &[&str])] = &[
            ("C:\\Users\\User\\AppData\\Local\\pip\\cache\\http-v2\\example.body", false, "green", &["pip", "Python"]),
            ("C:\\Program Files (x86)\\Microsoft\\EdgeWebView\\Application\\146.0.3856.72\\msedge.dll", false, "yellow", &["WebView"]),
            ("C:\\Users\\User\\Documents\\archive.bin", false, "yellow", &["无法", "不确定", "不能确定", "难以", "不清楚"]),
            ("C:\\Users\\User\\AppData\\Local\\Microsoft\\OneNote\\16.0\\cache", true, "yellow", &["同步", "备份"]),
            ("C:\\Users\\User\\miniforge3\\Lib\\site-packages\\torch\\lib\\torch_cuda.dll", false, "yellow", &["PyTorch", "torch", "Torch"]),
            ("C:\\Users\\User\\AppData\\Local\\pip\\cache-backup\\saved.body", false, "yellow", &["无法", "不确定", "不能确定", "难以", "不清楚"]),
        ];
        let mut failures = Vec::new();
        for (path, is_dir, safety, expected) in cases {
            let messages = super::super::explain::build_prompt(path, "200 MB", *is_dir, safety, None);
            let response = infer_blocking(&inner, &messages).unwrap();
            println!("Explanation for {}: {}", path, response);
            let unsafe_claim = (path.contains("OneNote") && (response.contains("纯缓存")
                || !["丢", "损失"].iter().any(|word| response.contains(word))))
                || (path.contains("EdgeWebView") && (!["应用", "软件"].iter().any(|word| response.contains(word))
                    || response.contains("删了 Edge") || response.contains("删了Edge")))
                || (path.contains("cache-backup") && response.contains("pip cache purge"));
            if !expected.iter().any(|word| response.contains(word)) || response.contains('\u{fffd}')
                || unsafe_claim || response.contains("conda env remove -n base") || response.contains("pip cache clear") {
                failures.push(*path);
            }
        }
        assert!(failures.is_empty(), "Missing purpose/uncertainty cues in: {:?}", failures);
    }
}
