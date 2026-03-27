pub mod admin;
pub mod scan;
pub mod drive;
pub mod explain;
pub mod models;
pub mod explorer;
pub mod local_llm;

pub fn format_size(bytes: u64) -> String {
    let units = ["B", "KB", "MB", "GB", "TB", "PB", "EB"];
    let mut size = bytes as f64;
    for unit in &units {
        if size < 1024.0 {
            return format!("{:.1} {}", size, unit);
        }
        size /= 1024.0;
    }
    format!("{:.1} ZB", size)
}

/// Validate that a base URL is safe (no SSRF to private/localhost addresses).
pub fn validate_base_url(url: &str) -> Result<(), String> {
    let lower = url.to_lowercase();
    if !lower.starts_with("https://") && !lower.starts_with("http://") {
        return Err("API base URL must start with http:// or https://".to_string());
    }
    // Extract authority (everything between scheme and first '/' or end)
    let after_scheme = if lower.starts_with("https://") {
        &lower[8..]
    } else {
        &lower[7..]
    };
    let authority = after_scheme.split('/').next().unwrap_or("");

    // Strip userinfo (e.g. "user:pass@host" → "host")
    let host_port = if let Some(pos) = authority.rfind('@') {
        &authority[pos + 1..]
    } else {
        authority
    };

    // Extract host, handling IPv6 brackets: [::1]:port → [::1]
    let host = if host_port.starts_with('[') {
        // IPv6: take everything up to and including ']'
        host_port.split(']').next().map(|s| format!("{}]", s)).unwrap_or_default()
    } else {
        // IPv4 / hostname: strip port after last ':'
        host_port.rsplit_once(':').map_or(host_port.to_string(), |(h, _)| h.to_string())
    };

    let blocked = [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "[::1]",
        "[::0]",
        "169.254.",
    ];
    for b in &blocked {
        if host.starts_with(b) {
            return Err(format!("API base URL must not point to local/private address: {}", host));
        }
    }
    // Block common private IP ranges
    if host.starts_with("10.")
        || host.starts_with("192.168.")
        || (host.starts_with("172.") && is_172_private(&host))
    {
        return Err(format!("API base URL must not point to private network: {}", host));
    }

    Ok(())
}

fn is_172_private(host: &str) -> bool {
    if let Some(rest) = host.strip_prefix("172.") {
        if let Some(second) = rest.split('.').next() {
            if let Ok(n) = second.parse::<u8>() {
                return (16..=31).contains(&n);
            }
        }
    }
    false
}
