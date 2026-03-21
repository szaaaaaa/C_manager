use serde::Deserialize;
use std::sync::LazyLock;

#[derive(Deserialize)]
struct SafetyRules {
    red: Vec<String>,
    red_names: Vec<String>,
    yellow: Vec<String>,
    green: Vec<String>,
}

static RULES: LazyLock<SafetyRules> = LazyLock::new(|| {
    serde_json::from_str(include_str!("rules.json")).unwrap()
});

/// Rate the safety of a file path. Returns "red", "yellow", or "green".
pub fn rate_safety(path: &str) -> &'static str {
    let path_lower = path.to_lowercase().replace('/', "\\");
    let filename = path_lower.rsplit('\\').next().unwrap_or("");

    // Green first — specific safe-to-clean subpaths override broad patterns
    for pattern in &RULES.green {
        let pat_stripped = pattern.trim_end_matches('\\');
        if path_lower.contains(pattern.as_str()) || path_lower.ends_with(pat_stripped) {
            return "green";
        }
    }

    // Red — system-critical
    for pattern in &RULES.red {
        if path_lower.contains(pattern.as_str()) {
            return "red";
        }
    }
    if RULES.red_names.iter().any(|n| n == filename) {
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
