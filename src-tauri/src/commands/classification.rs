use regex::{Regex, RegexBuilder, RegexSet, RegexSetBuilder};
use serde::{Deserialize, Serialize};
use std::{collections::{HashMap, HashSet}, sync::LazyLock};

#[derive(Deserialize)]
struct Rule {
    id: String,
    category: String,
    group: String,
    label: String,
    kind: String,
    recursive: bool,
    default_selected: bool,
    requires_idle: bool,
    paths: Vec<String>,
    extensions: Vec<String>,
    filters: Vec<String>,
}
#[derive(Deserialize)]
struct Rules {
    rules: Vec<Rule>,
    file_categories: Vec<HashMap<String, String>>,
}
#[derive(Clone, Serialize)]
pub struct RuleMatch {
    rule_id: String,
    category: String,
    group: String,
    label: String,
    path_pattern: String,
    default_selected: bool,
    requires_idle: bool,
}
#[derive(Clone, Serialize)]
pub struct Classification {
    pub file_type: String,
    pub matches: Vec<RuleMatch>,
}
#[derive(Deserialize)]
pub struct ClassificationInput {
    path: String,
    is_dir: bool,
}
struct CompiledRule {
    extensions: Vec<Regex>,
    filters: Vec<Regex>,
}
struct Classifier {
    source: Rules,
    paths: RegexSet,
    owners: Vec<(usize, String)>,
    compiled: Vec<CompiledRule>,
    types: HashMap<String, String>,
}

fn filename_regex(value: &str) -> Regex {
    // The source engine converts only dots/stars and uses full-name matching.
    let pattern = value.replace('.', "\\.").replace('*', ".*");
    RegexBuilder::new(&format!("^(?:.*{pattern})$"))
        .case_insensitive(true).build().expect("valid embedded filename rule")
}

fn normalize(path: &str) -> String {
    path.replace('/', "\\").trim_start_matches(r"\\?\").trim_end_matches('\\').to_lowercase()
}

fn path_regex(path: &str, recursive: bool) -> String {
    let normalized = normalize(path);
    let mut parts = normalized.split('\\');
    let first = parts.next().unwrap_or("");
    let mut pattern = if first == "*" || first == "*:" { "[a-z]:".into() }
        else { regex::escape(first).replace(r"\*", r"[^\\]*") };
    for part in parts {
        pattern.push_str(r"\\");
        pattern.push_str(&regex::escape(part).replace(r"\*", r"[^\\]*"));
    }
    format!("^{pattern}\\\\{}$", if recursive { r"(?:[^\\]+\\)*[^\\]+" } else { r"[^\\]+" })
}

fn system_roots() -> HashMap<String, String> {
    let mut roots = HashMap::new();
    #[cfg(windows)]
    for (name, id) in [("CSIDL_APPDATA", 0x1a), ("CSIDL_LOCAL_APPDATA", 0x1c),
        ("CSIDL_PROGRAM_FILES", 0x26), ("CSIDL_PROGRAM_FILESX86", 0x2a),
        ("CSIDL_COMMON_APPDATA", 0x23), ("CSIDL_PROFILE", 0x28),
        ("CSIDL_MYDOCUMENTS", 5), ("CSIDL_WINDOWS", 0x24), ("CSIDL_SYSTEM", 0x25),
        ("CSIDL_COMMON_DOCUMENTS", 0x2e), ("CSIDL_RECENT", 8)] {
        let mut buffer = [0u16; 260];
        let status = unsafe { windows_sys::Win32::UI::Shell::SHGetFolderPathW(
            std::ptr::null_mut(), id, std::ptr::null_mut(), 0, buffer.as_mut_ptr()) };
        if status >= 0 {
            let end = buffer.iter().position(|c| *c == 0).unwrap_or(buffer.len());
            roots.insert(name.into(), String::from_utf16_lossy(&buffer[..end]));
        }
    }
    if let Ok(profile) = std::env::var("USERPROFILE") { roots.insert("USERPROFILE".into(), profile); }
    roots
}

impl Classifier {
    fn new(roots: &HashMap<String, String>) -> Self {
        let source: Rules = serde_json::from_str(include_str!("cleanup_rules.json")).expect("embedded rules");
        let variables = Regex::new(r"%([^%]+)%").unwrap();
        let mut patterns = Vec::new();
        let mut owners = Vec::new();
        let mut compiled = Vec::new();
        for (index, rule) in source.rules.iter().enumerate() {
            compiled.push(CompiledRule {
                extensions: rule.extensions.iter().map(|s| filename_regex(s)).collect(),
                filters: rule.filters.iter().map(|s| filename_regex(s)).chain(
                    [Regex::new(r"(?i)^[Dd]esktop.ini$").unwrap()]).collect(),
            });
            // Registry/recycle/WPS rules invoke special handlers; their '*' is not a file glob.
            if rule.kind != "file" { continue; }
            for path in &rule.paths {
                let mut unresolved = false;
                let expanded = variables.replace_all(path, |caps: &regex::Captures| {
                    roots.get(&caps[1]).cloned().unwrap_or_else(|| { unresolved = true; String::new() })
                });
                // INSTALLPATH depends on Lenovo's software inventory; never widen a missing root.
                if unresolved || expanded.len() <= 3 { continue; }
                patterns.push(path_regex(&expanded, rule.recursive));
                owners.push((index, path.clone()));
            }
        }
        let mut types = HashMap::new();
        for category in &source.file_categories {
            for (name, extensions) in category {
                for ext in extensions.split(';').filter(|s| !s.is_empty()) {
                    types.insert(ext.to_lowercase(), name.clone());
                }
            }
        }
        Self { source, paths: RegexSetBuilder::new(patterns).case_insensitive(true)
            .size_limit(64 * 1024 * 1024).build().expect("valid embedded paths"), owners, compiled, types }
    }

    fn classify(&self, path: &str, is_dir: bool) -> Classification {
        let path = normalize(path);
        let filename = path.rsplit('\\').next().unwrap_or("");
        let file_type = if is_dir { "其他".into() } else {
            filename.rfind('.').and_then(|i| self.types.get(&filename[i..])).cloned().unwrap_or_else(|| "其他".into())
        };
        let mut matches = Vec::new();
        let mut seen = HashSet::new();
        if !is_dir {
            for index in self.paths.matches(&path) {
                let (owner, pattern) = &self.owners[index];
                let compiled = &self.compiled[*owner];
                if compiled.filters.iter().any(|r| r.is_match(filename)) ||
                    (!compiled.extensions.is_empty() && !compiled.extensions.iter().any(|r| r.is_match(filename))) {
                    continue;
                }
                if !seen.insert(*owner) { continue; }
                let rule = &self.source.rules[*owner];
                matches.push(RuleMatch { rule_id: rule.id.clone(), category: rule.category.clone(), group: rule.group.clone(),
                    label: rule.label.clone(), path_pattern: pattern.clone(), default_selected: rule.default_selected,
                    requires_idle: rule.requires_idle });
            }
        }
        matches.sort_by_key(|m| std::cmp::Reverse(m.path_pattern.len()));
        Classification { file_type, matches }
    }
}

static CLASSIFIER: LazyLock<Classifier> = LazyLock::new(|| Classifier::new(&system_roots()));

pub fn classify(path: &str, is_dir: bool) -> Classification { CLASSIFIER.classify(path, is_dir) }

#[tauri::command]
pub async fn classify_files(files: Vec<ClassificationInput>) -> Result<Vec<Classification>, String> {
    if files.len() > 1000 { return Err("每批分类最多1000个文件".into()); }
    tokio::task::spawn_blocking(move || files.iter().map(|f| classify(&f.path, f.is_dir)).collect())
        .await.map_err(|e| format!("文件分类失败：{e}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(windows)]
    #[test]
    fn current_user_known_folders_are_resolved_without_assuming_c_drive() {
        let roots = system_roots();
        assert!(roots.contains_key("CSIDL_MYDOCUMENTS"));
        let temp = format!("{}\\Temp\\nested\\classification.test", roots["CSIDL_LOCAL_APPDATA"]);
        assert!(classify(&temp, false).matches.iter().any(|m| m.label == "系统临时文件"));
    }

    #[test]
    fn imported_rules_classify_paths_not_deletion_safety() {
        let c = Classifier::new(&HashMap::from([
            ("CSIDL_WINDOWS".into(), r"C:\Windows".into()),
            ("CSIDL_LOCAL_APPDATA".into(), r"C:\Users\Test\AppData\Local".into()),
            ("CSIDL_MYDOCUMENTS".into(), r"D:\MovedDocuments".into()),
            ("CSIDL_APPDATA".into(), r"C:\Users\Test\AppData\Roaming".into()),
        ]));
        assert_eq!(c.source.rules.len(), 1375);
        assert_eq!(c.source.rules.iter().map(|r| r.paths.len()).sum::<usize>(), 2971);
        let labels = |p: &str| c.classify(p, false).matches.into_iter().map(|m| m.label).collect::<Vec<_>>();
        assert!(labels(r"C:\Windows\INF\SETUPAPI.LOG").contains(&"Windows 系统日志".into()));
        assert!(!labels(r"C:\Windows\INF\child\a.log").contains(&"Windows 系统日志".into()));
        assert!(labels(r"C:\Windows\Logs\CBS\child\a.log").contains(&"Windows 系统完整性检查日志".into()));
        assert!(labels(r"C:\Users\Test\Desktop\工作记录.log").is_empty());
        assert!(labels(r"C:\Windows\TempBackup\a.log").is_empty());
        assert!(labels(r"C:\Windows\Temp\child\a.unknown").contains(&"系统临时文件".into()));
        assert!(labels(r"D:\MovedDocuments\WeChat Files\account\FileStorage\Image\a.special").iter().any(|s| s.contains("图片")));
        assert!(labels(r"C:\Users\Test\Documents\WeChat Files\account\FileStorage\Image\a.special").is_empty());
        assert!(labels(r"C:\Windows\INF\desktop.ini").is_empty());
        let received = c.classify(r"D:\MovedDocuments\xwechat_files\account\msg\file\photo.jpg", false);
        assert!(received.matches.iter().any(|m| m.label == "微信接收到的文件" && !m.default_selected));
        assert!(labels(r"D:\MovedDocuments\WeChat Files\account\Applet\app\temp\file.bin").contains(&"微信小程序缓存文件".into()));
        assert!(!labels(r"D:\MovedDocuments\WeChat Files\account\Applet\app\temp\the-real-index").contains(&"微信小程序缓存文件".into()));
        assert!(labels(r"D:\Elsewhere\log\file.logEncode").is_empty());

        assert!(c.classify(r"C:\Windows\Temp", true).matches.is_empty());
        assert_eq!(c.classify(r"D:\design.AI", false).file_type, "图片");
        assert_eq!(c.classify(r"D:\program.exe", false).file_type, "安装包");
        assert_eq!(c.classify(r"D:\model.safetensors", false).file_type, "其他");
        assert!(!filename_regex("index$").is_match("index.log"));
        assert!(filename_regex("index$").is_match("the-real-index"));
        assert!(!filename_regex("cookies").is_match("cookies.txt"));
        assert!(filename_regex("cookies").is_match("MyCookies"));
        assert!(!filename_regex(".log").is_match("a.log.bak"));
        assert!(Regex::new(&path_regex(r"*\App\*\cache", false)).unwrap().is_match(r"d:\app\user\cache\file"));
        assert!(!Regex::new(&path_regex(r"*\App\*\cache", false)).unwrap().is_match(r"d:\other\app\user\cache\file"));
    }
}
