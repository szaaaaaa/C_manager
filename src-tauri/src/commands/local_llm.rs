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
use sha2::{Digest, Sha256};
use tauri::Manager;
use tokio::io::AsyncWriteExt;

const CTX_SIZE: u32 = 4096;
const MAX_RESPONSE_TOKENS: usize = 1024;

#[derive(Clone, Copy)]
struct ModelSpec {
    id: &'static str,
    name: &'static str,
    filename: &'static str,
    url: &'static str,
    sha256: &'static str,
    size_label: &'static str,
}

const MODELS: [ModelSpec; 2] = [
    ModelSpec {
        id: "qwen35-08b",
        name: "Qwen3.5-0.8B · Q4_K_M",
        filename: "Qwen3.5-0.8B-Q4_K_M.gguf",
        url: "https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/resolve/ed4bdcdbcce9f095bb49e8759176c64e45fa294b/Qwen3.5-0.8B-Q4_K_M.gguf",
        sha256: "bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517",
        size_label: "约 0.5 GB",
    },
    ModelSpec {
        id: "qwen35-4b",
        name: "Qwen3.5-4B · Q4_K_M",
        filename: "Qwen3.5-4B-Q4_K_M.gguf",
        url: "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/b0bd07786f94b700012140fd9263b2de83d4f97b/Qwen3.5-4B-Q4_K_M.gguf",
        sha256: "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4",
        size_label: "约 2.7 GB",
    },
];

pub enum LoadedModel {
    Native {
        model: LlamaModel,
        backend: LlamaBackend,
        id: String,
        name: String,
    },
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
            Self::Native { id, name, .. } => (id.as_str(), name.as_str(), true),
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
    installed: bool,
    size_label: String,
}

#[tauri::command]
pub fn list_local_models(app: tauri::AppHandle) -> Result<Vec<ModelOption>, String> {
    MODELS
        .iter()
        .map(|model| {
            Ok(ModelOption {
                id: model.id.into(),
                name: model.name.into(),
                installed: model_path(&app, model)?.is_file(),
                size_label: model.size_label.into(),
            })
        })
        .collect()
}

fn model_path(app: &tauri::AppHandle, model: &ModelSpec) -> Result<PathBuf, String> {
    Ok(app
        .path()
        .app_local_data_dir()
        .map_err(|e| e.to_string())?
        .join("models")
        .join(model.filename))
}

async fn ensure_model(app: &tauri::AppHandle, model: &ModelSpec) -> Result<PathBuf, String> {
    let path = model_path(app, model)?;
    if path.is_file() {
        return Ok(path);
    }
    let parent = path.parent().ok_or("无法确定模型保存目录")?;
    tokio::fs::create_dir_all(parent)
        .await
        .map_err(|e| format!("无法创建模型目录: {e}"))?;
    let partial = path.with_extension("gguf.download");
    let _ = tokio::fs::remove_file(&partial).await;
    let result: Result<(), String> = async {
        let mut response = reqwest::Client::builder()
            .connect_timeout(std::time::Duration::from_secs(30))
            .user_agent("C-manager/0.2")
            .build()
            .map_err(|e| e.to_string())?
            .get(model.url)
            .send()
            .await
            .map_err(|e| format!("模型下载失败: {e}"))?
            .error_for_status()
            .map_err(|e| format!("模型下载失败: {e}"))?;
        let mut file = tokio::fs::File::create(&partial)
            .await
            .map_err(|e| format!("无法创建模型文件: {e}"))?;
        let mut hasher = Sha256::new();
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|e| format!("模型下载中断: {e}"))?
        {
            file.write_all(&chunk)
                .await
                .map_err(|e| format!("无法写入模型文件: {e}"))?;
            hasher.update(&chunk);
        }
        file.flush()
            .await
            .map_err(|e| format!("无法保存模型文件: {e}"))?;
        drop(file);
        if format!("{:x}", hasher.finalize()) != model.sha256 {
            return Err("模型校验失败，请重试下载".into());
        }
        tokio::fs::rename(&partial, &path)
            .await
            .map_err(|e| format!("无法保存模型文件: {e}"))?;
        Ok(())
    }
    .await;
    if let Err(error) = result {
        let _ = tokio::fs::remove_file(&partial).await;
        return Err(error);
    }
    Ok(path)
}

#[tauri::command]
pub async fn init_local_model(
    app: tauri::AppHandle,
    state: tauri::State<'_, LocalLlmState>,
    model_id: Option<String>,
) -> Result<LocalModelInfo, String> {
    let id = model_id.unwrap_or_else(|| MODELS[0].id.into());
    let spec = MODELS
        .iter()
        .find(|model| model.id == id)
        .copied()
        .ok_or("未知本地模型，请刷新模型列表")?;
    {
        let mut guard = state.inner.lock().map_err(|e| e.to_string())?;
        if let Some(loaded) = guard.as_mut() {
            let info = loaded.info();
            if info.model_id == id && info.loaded {
                return Ok(info);
            }
        }
    }
    let native_path = ensure_model(&app, &spec).await?;
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
        let backend = LlamaBackend::init().map_err(|e| format!("llama.cpp 初始化失败: {e}"))?;
        let model = LlamaModel::load_from_file(
            &backend,
            native_path,
            &LlamaModelParams::default(),
        )
        .map_err(|e| format!("模型加载失败: {e}"))?;
        let loaded = LoadedModel::Native {
            model,
            backend,
            id,
            name: spec.name.into(),
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
                model_id: MODELS[0].id.into(),
                model_name: MODELS[0].name.into(),
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

    let LoadedModel::Native { model, backend, .. } = loaded;
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
                    .join(MODELS[0].filename)
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
        let inner = Arc::new(Mutex::new(Some(LoadedModel::Native {
            model,
            backend,
            id: MODELS[0].id.into(),
            name: MODELS[0].name.into(),
        })));
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
