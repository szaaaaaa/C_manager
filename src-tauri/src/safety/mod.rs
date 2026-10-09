use serde::Deserialize;
use std::sync::LazyLock;

#[derive(Deserialize)]
struct SafetyRules {
    red: Vec<String>,
    red_names: Vec<String>,
    yellow: Vec<String>,
}

static RULES: LazyLock<SafetyRules> = LazyLock::new(|| {
    serde_json::from_str(include_str!("rules.json")).unwrap()
});

#[derive(Deserialize)]
pub struct KnowledgeEntry {
    patterns: Vec<String>,
    pub safety: String,
    pub facts: String,
}

#[derive(Deserialize)]
struct Knowledge {
    unknown: String,
    entries: Vec<KnowledgeEntry>,
}

static KNOWLEDGE: LazyLock<Knowledge> = LazyLock::new(|| {
    serde_json::from_str(include_str!("knowledge.json")).unwrap()
});

pub fn lookup_knowledge(path: &str) -> Option<&'static KnowledgeEntry> {
    let normalized = format!("{}\\", path.to_lowercase().replace('/', "\\").trim_end_matches('\\'));
    KNOWLEDGE.entries.iter().find(|entry| {
        entry.patterns.iter().all(|pattern| normalized.contains(pattern))
    })
}

pub fn file_context(path: &str) -> &'static str {
    lookup_knowledge(path).map_or(&KNOWLEDGE.unknown, |entry| &entry.facts)
}

/// Rate the safety of a file path. Returns "red", "yellow", or "green".
pub fn rate_safety(path: &str) -> &'static str {
    let path_lower = path.to_lowercase().replace('/', "\\");
    let filename = path_lower.rsplit('\\').next().unwrap_or("");

    if RULES.red_names.iter().any(|n| n == filename)
        || RULES.red.iter().any(|pattern| pattern != "\\windows\\" && path_lower.contains(pattern)) {
        return "red";
    }
    // Only reviewed paths can override a broad directory rule (e.g. Windows Temp).
    if let Some(entry) = lookup_knowledge(path) {
        return &entry.safety;
    }

    if path_lower.contains("\\windows\\") {
        return "red";
    }

    // Yellow — caution
    for pattern in &RULES.yellow {
        if path_lower.contains(pattern.as_str()) {
            return "yellow";
        }
    }

    "yellow"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn caches_and_extensions_do_not_imply_disposable_data() {
        for path in [r"C:\Users\User\Documents\cache\notes.bin", r"C:\Users\User\Downloads\backup.zip",
            r"C:\Users\User\Documents\notes.bak", r"C:\Windows\System32\cache\data.log",
            r"C:\Users\User\AppData\Local\Temp\ntoskrnl.exe"] {
            assert_ne!(rate_safety(path), "green", "{path}");
        }
        assert_eq!(rate_safety(r"C:\Users\User\AppData\Local\Microsoft\OneNote\16.0\cache"), "yellow");
        assert_eq!(rate_safety(r"C:\Users\User\AppData\Local\pip\cache\a.body"), "green");
        assert_eq!(rate_safety(r"C:\Windows\Temp\install.tmp"), "green");
        assert!(lookup_knowledge("c:/Users/用户/APPDATA/LOCAL/PIP/CACHE/a.body").is_some());
        assert!(lookup_knowledge(r"C:\Users\User\AppData\Local\pip\cache-backup\a.body").is_none());
        assert!(lookup_knowledge(r"C:\Program Files\Microsoft\UnknownApp\data.bin").is_none());
    }
}
