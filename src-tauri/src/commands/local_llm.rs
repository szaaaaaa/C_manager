use std::num::NonZeroU32;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use super::local_server::{self, LocalServer};
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

pub enum LoadedModel {
    Native {
        model: LlamaModel,
        backend: LlamaBackend,
    },
    Server(LocalServer),
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
    pub model_id: String,
    pub model_name: String,
    pub error: Option<String>,
}

impl LoadedModel {
    fn info(&mut self) -> LocalModelInfo {
        let (id, name, loaded) = match self {
            Self::Native { .. } => ("builtin", MODEL_FILENAME, true),
            Self::Server(server) => {
                let loaded = server.is_running();
                (
                    server.choice.id.as_str(),
                    server.choice.name.as_str(),
                    loaded,
                )
            }
        };
        LocalModelInfo {
            loaded,
            model_id: id.into(),
            model_name: name.into(),
            error: (!loaded).then(|| "模型进程已退出，请重新加载".into()),
        }
    }
}

#[derive(Serialize)]
pub struct ModelOption {
    id: String,
    name: String,
}

#[tauri::command]
pub fn list_local_models(app: tauri::AppHandle) -> Result<Vec<ModelOption>, String> {
    let mut result = vec![ModelOption {
        id: "builtin".into(),
        name: "Qwen3.5-0.8B（内置）".into(),
    }];
    result.extend(
        local_server::choices(&app)?
            .into_iter()
            .map(|m| ModelOption {
                id: m.id,
                name: m.name,
            }),
    );
    Ok(result)
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
    model_id: Option<String>,
) -> Result<LocalModelInfo, String> {
    let id = model_id.unwrap_or_else(|| "builtin".into());
    let choice = if id == "builtin" {
        None
    } else {
        Some(
            local_server::choices(&app)?
                .into_iter()
                .find(|m| m.id == id)
                .ok_or("未知本地模型，请刷新模型列表")?,
        )
    };
    let native_path = if choice.is_none() {
        Some(find_model_path(&app)?)
    } else {
        None
    };
    let inner = state.inner.clone();
    tokio::task::spawn_blocking(move || {
        let mut guard = inner.lock().map_err(|e| e.to_string())?;
        if let Some(loaded) = guard.as_mut() {
            let info = loaded.info();
            if info.model_id == id && info.loaded {
                return Ok(info);
            }
        }
        // Release the old model before allocating another model's RAM/VRAM.
        drop(guard.take());
        let loaded = if let Some(choice) = choice {
            LoadedModel::Server(LocalServer::start(choice)?)
        } else {
            let backend = LlamaBackend::init().map_err(|e| format!("llama.cpp 初始化失败: {e}"))?;
            let model = LlamaModel::load_from_file(
                &backend,
                native_path.unwrap(),
                &LlamaModelParams::default(),
            )
            .map_err(|e| format!("模型加载失败: {e}"))?;
            LoadedModel::Native { model, backend }
        };
        *guard = Some(loaded);
        Ok(guard.as_mut().unwrap().info())
    })
    .await
    .map_err(|e| format!("加载任务失败: {e}"))?
}

#[tauri::command]
pub async fn get_local_model_status(
    state: tauri::State<'_, LocalLlmState>,
) -> Result<LocalModelInfo, String> {
    let inner = state.inner.clone();
    tokio::task::spawn_blocking(move || {
        let mut guard = inner.lock().map_err(|e| e.to_string())?;
        Ok(guard
            .as_mut()
            .map(LoadedModel::info)
            .unwrap_or(LocalModelInfo {
                loaded: false,
                model_id: "builtin".into(),
                model_name: MODEL_FILENAME.into(),
                error: None,
            }))
    })
    .await
    .map_err(|e| e.to_string())?
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
    infer_with_grammar(inner, messages, super::explain::GRAMMAR)
}

pub fn infer_with_grammar(
    inner: &Arc<Mutex<Option<LoadedModel>>>, messages: &[serde_json::Value], grammar: &str,
) -> Result<String, String> {
    let mut guard = inner.lock().map_err(|e| e.to_string())?;
    let loaded = guard
        .as_mut()
        .ok_or("本地模型未加载，请先在设置中点击「加载模型」")?;

    let (model, backend) = match loaded {
        LoadedModel::Server(server) => return server.infer_with_grammar(messages, grammar),
        LoadedModel::Native { model, backend } => (model, backend),
    };
    let prompt = format_chatml(messages);

    let ctx_params = LlamaContextParams::default()
        .with_n_ctx(NonZeroU32::new(CTX_SIZE))
        .with_n_batch(CTX_SIZE);

    let mut ctx = model
        .new_context(backend, ctx_params)
        .map_err(|e| format!("创建推理上下文失败: {}", e))?;

    // Tokenize prompt
    let tokens = model
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
        LlamaSampler::grammar(model, grammar, "root")
            .map_err(|e| format!("结构约束初始化失败: {e}"))?,
        LlamaSampler::greedy(),
    ]);

    let mut output = Vec::new();
    let mut n_decoded = tokens.len();
    let mut completed = false;

    for _ in 0..MAX_RESPONSE_TOKENS.min(CTX_SIZE as usize - tokens.len()) {
        let token = sampler.sample(&ctx, -1);
        // sample() already accepts the token; accepting twice corrupts grammar state.

        if model.is_eog_token(token) {
            completed = true;
            break;
        }

        // Tokens may contain only part of a UTF-8 character; decode after collecting the bytes.
        let piece = model
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
        let inner = Arc::new(Mutex::new(Some(LoadedModel::Native { model, backend })));
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
