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

// Only installation-directory labels enter the preview automatically; private project paths stay local.
fn installation_terms(path: &str) -> Vec<String> {
    let normalized = path.replace('/', "\\");
    let parts: Vec<_> = normalized.trim_end_matches('\\').split('\\').collect();
    let parent = &parts[..parts.len().saturating_sub(1)];
    let installed = parent.get(1).is_some_and(|p| {
        ["Program Files", "Program Files (x86)", "Windows", "ProgramData"].iter().any(|v| p.eq_ignore_ascii_case(v))
    });
    let user_data = parent.get(1).is_some_and(|p| p.eq_ignore_ascii_case("Users"))
        && parent.get(3).is_some_and(|p| p.eq_ignore_ascii_case("AppData"));
    let start = if installed { 2 } else if user_data { 5 } else { return vec![] };
    let terms: Vec<String> = parent.iter().skip(start)
        .filter(|p| p.chars().count() <= 64 && p.chars().any(char::is_alphabetic)
            && !(p.len() >= 16 && p.chars().all(|c| c.is_ascii_hexdigit() || "-{}".contains(c)))
            && p.chars().all(|c| c.is_alphanumeric() || " _-.()".contains(c)))
        .map(|p| p.to_string()).collect();
    // shortcut: AppData can contain private projects below the vendor/app; deeper labels remain local.
    if user_data { return terms.into_iter().take(2).collect(); }
    let mut selected: Vec<_> = terms.iter().take(2).cloned().collect();
    for term in terms.iter().rev().take(2).rev() {
        if !selected.contains(term) { selected.push(term.clone()); }
    }
    selected
}

pub fn search_query(path: &str) -> String {
    context_query(path, &[])
}

fn context_query(path: &str, products: &[String]) -> String {
    let normalized = path.replace('/', "\\");
    let name = normalized.trim_end_matches('\\').rsplit('\\').next().unwrap_or("");
    let name: String = name.chars().filter(|c| !c.is_control()).take(180).collect();
    let context = installation_terms(path);
    if let Some(product) = products.first() {
        let product: String = product.chars().filter(|c| !c.is_control()).take(70).collect();
        let component = context.last().map(String::as_str).unwrap_or("");
        let name: String = name.chars().take(120).collect();
        return format!("{product} 功能 用途\n{component} {name} 文件用途 删除影响");
    }
    let prefix: String = context.join(" ").chars().take(90).collect();
    format!("{prefix} {name} 文件用途 删除影响").trim().to_string()
}

pub fn search_queries(query: &str) -> Result<Vec<&str>, String> {
    if query.chars().count() > 300 || query.chars().any(|c| c.is_control() && c != '\n' && c != '\r') {
        return Err("搜索词总长不能超过300字，除换行外不能含控制字符".into());
    }
    let queries: Vec<_> = query.lines().map(str::trim).filter(|s| !s.is_empty()).collect();
    if queries.is_empty() || queries.len() > 2 { return Err("请输入1至2条搜索词，每行一条".into()); }
    Ok(queries)
}

#[cfg(windows)]
fn product_metadata(path: &Path) -> Option<serde_json::Value> {
    use std::{ffi::c_void, os::windows::ffi::OsStrExt};
    use windows_sys::Win32::Storage::FileSystem::{GetFileVersionInfoSizeW, GetFileVersionInfoW, VerQueryValueW};
    let meta = checked_metadata(path).ok()?;
    if !meta.is_file() || meta.len() > 64 * 1024 * 1024 { return None; }
    let name: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    // Read version resources without loading or executing the application.
    unsafe {
        let size = GetFileVersionInfoSizeW(name.as_ptr(), std::ptr::null_mut());
        if size == 0 || size > 65536 { return None; }
        let mut data = vec![0u32; (size as usize).div_ceil(4)];
        let block = data.as_mut_ptr().cast::<c_void>();
        if GetFileVersionInfoW(name.as_ptr(), 0, size, block) == 0 { return None; }
        let query = |key: &str| -> Option<(*const u16, usize)> {
            let key: Vec<u16> = key.encode_utf16().chain(Some(0)).collect();
            let mut ptr = std::ptr::null_mut();
            let mut len = 0;
            if VerQueryValueW(block, key.as_ptr(), &mut ptr, &mut len) == 0 || ptr.is_null() { return None; }
            let offset = (ptr as usize).checked_sub(block as usize)?;
            if offset % 2 != 0 || offset >= size as usize { return None; }
            Some((ptr.cast::<u16>(), (len as usize).min((size as usize - offset) / 2)))
        };
        let (translation, len) = query(r"\VarFileInfo\Translation")?;
        if len < 2 { return None; }
        let (language, codepage) = (*translation, *translation.add(1));
        let mut fields = serde_json::Map::new();
        for field in ["ProductName", "CompanyName", "FileDescription"] {
            if let Some((ptr, len)) = query(&format!(r"\StringFileInfo\{language:04x}{codepage:04x}\{field}")) {
                let text = String::from_utf16_lossy(std::slice::from_raw_parts(ptr, len.min(160)));
                let text: String = text.trim_end_matches('\0').chars().filter(|c| !c.is_control()).collect();
                if !text.trim().is_empty() { fields.insert(field.into(), text.trim().into()); }
            }
        }
        (!fields.is_empty()).then_some(serde_json::Value::Object(fields))
    }
}

#[cfg(not(windows))]
fn product_metadata(_: &Path) -> Option<serde_json::Value> { None }

fn application_context(start: &Path, packet: &mut EvidencePacket) -> Vec<String> {
    let mut products = vec![];
    let mut inspected = 0;
    for parent in start.ancestors().take(6) {
        if parent.parent().is_none() || parent.parent().and_then(Path::file_name).is_some_and(|n| n.eq_ignore_ascii_case("Users")) { break; }
        let label = parent.file_name().and_then(|p| p.to_str()).unwrap_or("").to_lowercase();
        if ["program files", "program files (x86)", "programdata", "users", "windows", "appdata", "local", "roaming", "locallow", "temp", "tmp"].contains(&label.as_str()) { break; }
        let Ok(entries) = fs::read_dir(parent) else { continue };
        // Bounded and non-recursive: opening one explanation must not become a disk scan.
        let mut executables: Vec<_> = entries.take(128).filter_map(Result::ok).map(|e| e.path())
            .filter(|p| p.extension().is_some_and(|e| e.eq_ignore_ascii_case("exe"))).collect();
        executables.sort_by_key(|p| (p.file_stem().is_none_or(|s| !s.eq_ignore_ascii_case(&label)), p.clone()));
        let mut declarations = vec![];
        for executable in executables.into_iter().take(4) {
            if inspected >= 12 { break; }
            inspected += 1;
            let Some(fields) = product_metadata(&executable) else { continue };
            if let Some(product) = fields["ProductName"].as_str() {
                // Prefer product names connected to a directory label over incidental bundled runtimes.
                let context = start.to_string_lossy().to_lowercase();
                let matching_name = context.split(['\\', '/']).filter(|s| s.chars().count() >= 4)
                    .any(|s| product.to_lowercase().contains(s));
                if matching_name && !products.contains(&product.to_string()) {
                    products.push(product.to_string());
                }
            }
            declarations.push(serde_json::json!({"file":executable.file_name().unwrap_or_default().to_string_lossy(), "declared_product":fields}));
        }
        if !declarations.is_empty() {
            packet.evidence.push(Evidence {
                id: format!("L{}", packet.evidence.len() + 1), kind: "local_application".into(),
                title: "父目录的软件产品信息".into(),
                content: format!("当前文件在目录{}内；该目录的软件版本资源声明：{}", parent.display(), serde_json::Value::Array(declarations)), url: None,
            });
        }
        if inspected >= 12 { break; }
    }
    products
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
        fingerprint: String::new(), query: Some(search_query(path)), checked_at: now(), evidence: vec![],
        warnings: vec!["仅检查文件属性、相邻模型配置及最多六层父目录的软件版本资源和环境标记；未检查全机引用、进程占用、备份或下载权限。未发现引用不代表无人使用。软件版本资源只是产品声明，同目录可能是共享运行库，不证明调用关系或模型训练者。".into()],
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
    let classification = super::classification::classify(path, meta.is_dir());
    if !classification.matches.is_empty() {
        add("本地规则分类", format!("联想5.1.200.8201规则的路径与文件名匹配：{}。仅为用途标签，未核验运行状态、文件占用和是否可以删除；default_selected仅记录原工具默认勾选，不代表删除建议。", serde_json::to_string(&classification).unwrap()));
    }
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
                        let mut fields = serde_json::Map::new();
                        for key in ["model_type", "architectures", "_name_or_path"] {
                            if let Some(v) = value.get(key).filter(|v| (v.is_string() || v.is_array()) && v.to_string().len() <= 500) {
                                fields.insert(key.into(), v.clone());
                            }
                        }
                        (!fields.is_empty()).then(|| format!("同目录config.json声明：{}；它描述模型架构，不等于当前软件的实际功能，也不证明训练者、来源或可重新下载。", serde_json::Value::Object(fields)))
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
    let products = application_context(start, &mut packet);
    packet.query = Some(context_query(path, &products));
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
    fn any_filename_gets_a_query_without_private_parent_paths() {
        assert_eq!(search_query(r"C:\Recovery\Customizations\USMT.PPKG"), "USMT.PPKG 文件用途 删除影响");
        for name in ["a.unknownformat", "无扩展名", "archive.zip", "model.gguf"] {
            let query = search_query(&format!(r"C:\Users\private-user\private-project\{name}"));
            assert!(query.contains(name));
            assert!(!query.contains("private-user") && !query.contains("private-project"));
        }
        assert_eq!(search_query("D:/files/README"), "README 文件用途 删除影响");
    }
    #[test]
    fn chinese_queries_include_installation_context_but_not_user_or_generated_ids() {
        let query = search_query(r"C:\Program Files\ExampleVendor\CanvasApp\Plugins\Image\models\vision-encoder\weights.bin");
        for word in ["ExampleVendor", "CanvasApp", "vision-encoder", "weights.bin", "文件用途", "删除影响"] { assert!(query.contains(word), "{query}"); }
        assert!(!query.contains(r"C:\") && !query.contains("file purpose"));
        let query = search_query(r"C:\Users\private-user\AppData\Local\ExampleVendor\CanvasApp\private-project\98abedc498abedc498abedc4\content.bin");
        assert!(query.contains("CanvasApp") && !query.contains("private-user") && !query.contains("private-project") && !query.contains("98ab"));
        let query = context_query(r"C:\Program Files\ExampleVendor\CanvasApp\models\vision-encoder\weights.bin", &["示例画师".into()]);
        assert!(query.starts_with("示例画师 功能 用途\nvision-encoder") && query.ends_with("文件用途 删除影响"));
        assert_eq!(search_queries(&query).unwrap().len(), 2);
        for invalid in ["", "one\ntwo\nthree", "name\0", "name\tvalue"] { assert!(search_queries(invalid).is_err()); }
        assert!(search_query(&format!("D:/{}", "很长的文件名".repeat(100))).chars().count() <= 300);
    }

    #[cfg(windows)]
    #[test]
    fn version_resources_are_read_without_executing_files() {
        let cmd = std::path::PathBuf::from(std::env::var_os("SystemRoot").unwrap()).join("System32/cmd.exe");
        let product = product_metadata(&cmd).expect("Windows cmd has version resources");
        assert!(product["CompanyName"].as_str().unwrap().contains("Microsoft"));
        assert!(product_metadata(&std::env::current_dir().unwrap().join("Cargo.toml")).is_none());
    }

    #[test]
    fn inspect_bounded_config_and_detect_changes() {
        let root =
            std::env::temp_dir().join(format!("explain-evidence-{}-{}", std::process::id(), now()));
        fs::create_dir_all(&root).unwrap();
        let target = root.join("model.safetensors");
        fs::write(&target, b"weights").unwrap();
        fs::write(root.join("config.json"), r#"{"model_type":"qwen3","architectures":["Qwen3ForCausalLM"],"_name_or_path":"private/model","api_key":"must-not-collect"}"#).unwrap();
        fs::write(
            root.join("model.safetensors.index.json"),
            r#"{"weight_map":{"a":"model.safetensors"}}"#,
        )
        .unwrap();
        let first = collect(target.to_str().unwrap()).unwrap();
        let config_evidence: Vec<_> = first.evidence.iter().filter(|e| e.title != "本地规则分类").collect();
        assert_eq!(config_evidence.len(), 3);
        assert!(config_evidence[1].content.contains("Qwen3ForCausalLM"));
        assert!(!config_evidence[1].content.contains("must-not-collect"));
        assert!(config_evidence[2].content.contains("引用当前文件"));
        for rule in first.evidence.iter().filter(|e| e.title == "本地规则分类") {
            assert!(rule.content.contains("不代表删除建议"));
        }
        fs::write(root.join("config.json"), vec![b' '; 65537]).unwrap();
        let changed = collect(target.to_str().unwrap()).unwrap();
        assert_ne!(first.fingerprint, changed.fingerprint);
        assert!(changed.warnings.iter().any(|s| s.contains("64KiB")));
        fs::remove_file(&target).unwrap();
        assert!(collect(target.to_str().unwrap()).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
