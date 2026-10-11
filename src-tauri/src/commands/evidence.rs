use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{fs, io::Read, path::Path, time::UNIX_EPOCH};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Evidence {
    pub id: String,
    pub kind: String,
    pub title: String,
    pub content: String,
    pub url: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct EvidencePacket {
    pub path: String,
    pub size_human: String,
    pub fingerprint: String,
    pub query: Option<String>,
    pub evidence: Vec<Evidence>,
    pub warnings: Vec<String>,
    pub checked_at: u64,
}

pub fn now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn is_link(meta: &fs::Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        meta.file_attributes() & 0x400 != 0
    }
    #[cfg(not(windows))]
    {
        meta.file_type().is_symlink()
    }
}

fn checked_metadata(path: &Path) -> Result<fs::Metadata, String> {
    #[cfg(windows)]
    {
        use std::path::{Component, Prefix};
        if !matches!(path.components().next(), Some(Component::Prefix(p)) if matches!(p.kind(), Prefix::Disk(_) | Prefix::VerbatimDisk(_)))
        {
            return Err("仅支持本机盘符路径，不访问网络共享或设备路径".into());
        }
    }
    if path
        .components()
        .any(|c| matches!(c, std::path::Component::ParentDir))
    {
        return Err("路径不能包含上级目录跳转".into());
    }
    if !path.is_absolute() {
        return Err("只分析绝对路径".into());
    }
    for ancestor in path.ancestors() {
        let meta = fs::symlink_metadata(ancestor).map_err(|e| format!("无法检查文件路径：{e}"))?;
        if is_link(&meta) {
            return Err("路径含符号链接或目录联接点，需先确认实际目标；未读取目标内容".into());
        }
    }
    fs::metadata(path).map_err(|e| format!("无法读取文件信息：{e}"))
}

fn read_small(path: &Path) -> Result<String, String> {
    let meta = checked_metadata(path)?;
    if !meta.is_file() || meta.len() > 65536 {
        return Err("不是普通文件或超过64KiB读取上限".into());
    }
    let file = fs::File::open(path).map_err(|e| e.to_string())?;
    let mut bytes = Vec::new();
    file.take(65537)
        .read_to_end(&mut bytes)
        .map_err(|e| e.to_string())?;
    if bytes.len() > 65536 {
        return Err("读取时文件超过64KiB上限".into());
    }
    String::from_utf8(bytes).map_err(|_| "配置不是UTF-8文本".into())
}

// Search terms are a closed vocabulary: private names and arbitrary config text never enter a query.
pub fn search_query(path: &str) -> Option<String> {
    let p = path.to_lowercase().replace('/', "\\");
    let parts: Vec<_> = p.split('\\').collect();
    let sequence = |wanted: &[&str]| parts.windows(wanted.len()).any(|w| w == wanted);
    let query = if sequence(&["pip", "cache"]) {
        "pip cache documentation cache purge"
    } else if sequence(&["huggingface", "hub"]) {
        "Hugging Face Hub cache snapshots blobs manage cache documentation"
    } else if sequence(&["site-packages", "torch"]) {
        "PyTorch Python package installation uninstall documentation"
    } else if sequence(&["site-packages", "tensorflow"]) {
        "TensorFlow Python package installation documentation"
    } else if parts.contains(&"node_modules") {
        "npm node_modules dependencies npm uninstall documentation"
    } else if p.ends_with(".safetensors") {
        "safetensors model weights format documentation"
    } else if p.ends_with(".gguf") {
        "GGUF model weights format documentation"
    } else if p.ends_with(".vhdx") {
        "Microsoft VHDX virtual disk management documentation"
    } else {
        return None;
    };
    Some(query.into())
}

pub fn collect(path: &str) -> Result<EvidencePacket, String> {
    let target = Path::new(path);
    let meta = checked_metadata(target)?;
    if !meta.is_file() && !meta.is_dir() {
        return Err("不支持该文件类型".into());
    }
    let modified = meta
        .modified()
        .map_err(|e| format!("无法读取修改时间：{e}"))?
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "修改时间异常")?
        .as_nanos();
    let mut packet = EvidencePacket {
        path: path.into(), size_human: if meta.is_dir() { "目录：未递归统计".into() } else { super::format_size(meta.len()) },
        fingerprint: String::new(), query: search_query(path), checked_at: now(), evidence: vec![],
        warnings: vec!["仅检查文件属性、相邻模型配置及最多六层父目录的环境标记；未检查全机引用、进程占用、备份或下载权限。未发现引用不代表无人使用。".into()],
    };
    let mut add = |title: &str, content: String| {
        packet.evidence.push(Evidence {
            id: format!("L{}", packet.evidence.len() + 1),
            kind: "local_observation".into(),
            title: title.into(),
            content,
            url: None,
        });
    };
    add("文件属性", format!("路径：{path}；类型：{}；逻辑长度：{}字节；修改时间(unix ns)：{modified}。大小不等于可释放空间。", if meta.is_dir() { "目录" } else { "文件" }, meta.len()));
    if !meta.is_dir() {
        let parent = target.parent().ok_or("没有父目录")?;
        let filename = target.file_name().and_then(|v| v.to_str()).unwrap_or("");
        for name in ["config.json", "model.safetensors.index.json"] {
            let config = parent.join(name);
            match fs::symlink_metadata(&config) {
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => continue,
                Err(e) => {
                    packet.warnings.push(format!("无法检查{name}：{e}"));
                    continue;
                }
                Ok(_) => {}
            }
            match read_small(&config).and_then(|s| {
                serde_json::from_str::<serde_json::Value>(&s).map_err(|_| "JSON解析失败".into())
            }) {
                Ok(value) => {
                    let content = if name == "config.json" {
                        value.get("model_type").and_then(|v| v.as_str()).filter(|v| v.len() <= 80 && v.chars().all(|c| c.is_ascii_alphanumeric() || c=='_' || c=='-'))
                            .map(|v| format!("同目录config.json声明model_type={v}；只确认配置声明，不证明本文件由哪个仓库下载或被应用使用。"))
                    } else {
                        value.get("weight_map").and_then(|v| v.as_object()).filter(|m| m.values().any(|v| v.as_str() == Some(filename)))
                            .map(|m| format!("同目录{name}的weight_map引用当前文件，索引含{}个条目。它是模型分片关联线索；不代表应用当前在用，也不证明可重新下载。", m.len()))
                    };
                    if let Some(content) = content {
                        packet.evidence.push(Evidence {
                            id: format!("L{}", packet.evidence.len() + 1),
                            kind: "local_observation".into(),
                            title: name.into(),
                            content,
                            url: None,
                        });
                    }
                }
                Err(e) => packet.warnings.push(format!("未读取{name}：{e}")),
            }
        }
    }
    let start = if meta.is_dir() {
        target
    } else {
        target.parent().ok_or("没有父目录")?
    };
    for parent in start.ancestors().take(6) {
        for marker in ["pyvenv.cfg", "conda-meta/history"] {
            let candidate = parent.join(marker);
            match fs::symlink_metadata(&candidate) {
                Ok(m) if m.is_file() && !is_link(&m) => {
                    if checked_metadata(&candidate).is_ok() {
                        packet.evidence.push(Evidence { id:format!("L{}",packet.evidence.len()+1),kind:"local_observation".into(),title:"环境标记".into(),content:format!("父目录{}存在{marker}；确认标记存在，不证明某包归属、项目依赖或环境可安全移除。",parent.display()),url:None });
                    }
                }
                Err(e) if e.kind() != std::io::ErrorKind::NotFound => {
                    packet.warnings.push(format!("环境标记检查失败：{e}"))
                }
                _ => {}
            }
        }
    }
    // shortcut: this fingerprint covers metadata and collected evidence, not full file content; never use it to authorize deletion.
    let bytes = serde_json::to_vec(&(
        path,
        meta.len(),
        modified,
        &packet.evidence,
        &packet.warnings,
    ))
    .map_err(|e| e.to_string())?;
    packet.fingerprint = format!("{:x}", Sha256::digest(bytes));
    Ok(packet)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn queries_never_include_private_names_or_near_misses() {
        assert_eq!(
            search_query(r"C:\Users\secret\private-model.safetensors"),
            search_query(r"D:\other\x.safetensors")
        );
        assert!(search_query(r"C:\private\payroll.zip").is_none());
        assert!(search_query(r"C:\pip\cache-backup\a.bin").is_none());
        assert!(search_query(r"C:\site-packages\torch-backup\a.dll").is_none());
        assert!(search_query(r"C:\pip\cache\http\a.body")
            .unwrap()
            .starts_with("pip"));
    }
    #[test]
    fn inspect_bounded_config_and_detect_changes() {
        let root =
            std::env::temp_dir().join(format!("explain-evidence-{}-{}", std::process::id(), now()));
        fs::create_dir_all(&root).unwrap();
        let target = root.join("model.safetensors");
        fs::write(&target, b"weights").unwrap();
        fs::write(root.join("config.json"), r#"{"model_type":"qwen3"}"#).unwrap();
        fs::write(
            root.join("model.safetensors.index.json"),
            r#"{"weight_map":{"a":"model.safetensors"}}"#,
        )
        .unwrap();
        let first = collect(target.to_str().unwrap()).unwrap();
        assert_eq!(first.evidence.len(), 3);
        assert!(first.evidence[2].content.contains("引用当前文件"));
        fs::write(root.join("config.json"), vec![b' '; 65537]).unwrap();
        let changed = collect(target.to_str().unwrap()).unwrap();
        assert_ne!(first.fingerprint, changed.fingerprint);
        assert!(changed.warnings.iter().any(|s| s.contains("64KiB")));
        fs::remove_file(&target).unwrap();
        assert!(collect(target.to_str().unwrap()).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
