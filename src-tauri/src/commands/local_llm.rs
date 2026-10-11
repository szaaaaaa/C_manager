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
const CTX_SIZE: u32 = 4096;
const MAX_RESPONSE_TOKENS: usize = 1024;

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
        candidates.push(
            project
                .join("..")
                .join("lora-training")
                .join("output")
                .join("finetuned_model_gguf")
                .join(MODEL_FILENAME),
        );
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
        let backend = LlamaBackend::init().map_err(|e| format!("llama.cpp 初始化失败: {}", e))?;

        let model_params = LlamaModelParams::default();
        let model = LlamaModel::load_from_file(&backend, &model_path_clone, &model_params)
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
pub fn get_local_model_status(state: tauri::State<'_, LocalLlmState>) -> LocalModelInfo {
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
        // Keep untrusted file names/web text from becoming ChatML control tokens.
        let content = msg["content"].as_str().unwrap_or("").replace("<|", "< |");
        prompt.push_str(&format!("<|im_start|>{}\n{}<|im_end|>\n", role, content));
    }
    // Prompt the model to generate assistant response
    prompt.push_str("<|im_start|>assistant\n<think>\n\n</think>\n\n");
    prompt
}

/// Run inference on the loaded model. Called from explain.rs.
/// Takes Arc<Mutex<...>> so it can be used from spawn_blocking.
pub fn infer_structured(
    inner: &Arc<Mutex<Option<LoadedModel>>>,
    messages: &[serde_json::Value],
) -> Result<String, String> {
    let guard = inner.lock().map_err(|e| e.to_string())?;
    let loaded = guard
        .as_ref()
        .ok_or("本地模型未加载，请先在设置中点击「加载模型」")?;

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

    if tokens.len() + MAX_RESPONSE_TOKENS > CTX_SIZE as usize {
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
        LlamaSampler::grammar(&loaded.model, super::explain::GRAMMAR, "root")
            .map_err(|e| format!("结构约束初始化失败: {e}"))?,
        LlamaSampler::greedy(),
    ]);

    let mut output = Vec::new();
    let mut n_decoded = tokens.len();
    let mut completed = false;

    for _ in 0..MAX_RESPONSE_TOKENS.min(CTX_SIZE as usize - tokens.len()) {
        let token = sampler.sample(&ctx, -1);
        // sample() already accepts the token; accepting twice corrupts grammar state.

        if loaded.model.is_eog_token(token) {
            completed = true;
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

    if !completed {
        return Err("模型输出达到长度限制，未展示不完整解释".into());
    }
    String::from_utf8(output).map_err(|_| "模型返回无效UTF-8".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[ignore = "requires the local GGUF model"]
    fn local_model_chinese_and_explanation_smoke() {
        let backend = LlamaBackend::init().unwrap();
        let path = std::env::var_os("C_MANAGER_TEST_MODEL")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("resources")
                    .join(MODEL_FILENAME)
            });
        let model =
            LlamaModel::load_from_file(&backend, path, &LlamaModelParams::default()).unwrap();
        let text = "这是浏览器缓存，保存网页图片。🧪";
        let tokens = model.str_to_token(text, AddBos::Never).unwrap();
        let decoded: Vec<u8> = tokens
            .iter()
            .flat_map(|t| model.token_to_piece_bytes(*t, 1024, false, None).unwrap())
            .collect();
        assert_eq!(String::from_utf8(decoded).unwrap(), text);
        let inner = Arc::new(Mutex::new(Some(LoadedModel { backend, model })));
        let packet = super::super::evidence::EvidencePacket {
            path: "C:\\example\\unknown.bin".into(),
            size_human: "200 MB".into(),
            fingerprint: String::new(),
            query: None,
            checked_at: 0,
            evidence: vec![super::super::evidence::Evidence {
                id: "L1".into(),
                kind: "local_observation".into(),
                title: "文件属性".into(),
                content: "文件名unknown.bin，200MB，没有用途、依赖和备份资料".into(),
                url: None,
            }],
            warnings: vec!["未确认用途、备份、依赖及恢复条件".into()],
        };
        let messages = super::super::explain::build_prompt(&packet, None);
        let response = infer_structured(&inner, &messages).unwrap();
        println!("Structured explanation: {response}");
        let parsed = super::super::explain::parse_explanation(&response, &packet.evidence).unwrap();
        println!(
            "Validated explanation: {}",
            serde_json::to_string(&parsed).unwrap()
        );
    }
}
