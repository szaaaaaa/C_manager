use serde::Deserialize;
use std::{path::PathBuf, process::Stdio, time::Duration};
use tauri::Manager;
use tokio::io::AsyncReadExt;

#[derive(Deserialize)]
pub(super) struct Runtime {
    python: PathBuf,
}

pub(super) async fn runtime(app: &tauri::AppHandle) -> Result<Runtime, String> {
    let path = app.path().resource_dir().map_err(|e| e.to_string())?.join("resources/search-tools.json");
    serde_json::from_slice(&tokio::fs::read(path).await.map_err(|e| format!("无法读取搜索配置：{e}"))?)
        .map_err(|e| format!("搜索配置无效：{e}"))
}

pub(super) async fn run(runtime: &Runtime, query: &str) -> Result<serde_json::Value, String> {
    let mut cmd = tokio::process::Command::new(&runtime.python);
    cmd.args(["-I", "-c", include_str!("ddgs_search.py"), query]);
    normalize(output(cmd).await?)
}

pub(super) async fn pages(
    runtime: &Runtime,
    data: &serde_json::Value,
) -> Result<serde_json::Value, String> {
    let mut cmd = tokio::process::Command::new(&runtime.python);
    cmd.args(["-I", "-c", include_str!("read_pages.py"), &data.to_string()]);
    output(cmd).await
}

async fn output(mut cmd: tokio::process::Command) -> Result<serde_json::Value, String> {
    #[cfg(windows)]
    cmd.creation_flags(0x08000000);
    cmd.stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .kill_on_drop(true);
    let mut child = cmd.spawn().map_err(|e| format!("无法启动搜索工具：{e}"))?;
    let stdout = child.stdout.take().ok_or("搜索输出管道不可用")?;
    let task = async {
        let mut bytes = Vec::new();
        stdout
            .take(1_048_577)
            .read_to_end(&mut bytes)
            .await
            .map_err(|e| e.to_string())?;
        if bytes.len() > 1_048_576 {
            return Err("搜索返回超过1MiB上限".to_string());
        }
        let status = child.wait().await.map_err(|e| e.to_string())?;
        if !status.success() {
            return Err(format!(
                "搜索工具失败（{status}），请检查网络"
            ));
        }
        let data: serde_json::Value =
            serde_json::from_slice(&bytes).map_err(|_| "搜索工具未返回有效JSON".to_string())?;
        Ok(data)
    };
    tokio::time::timeout(Duration::from_secs(30), task)
        .await
        .map_err(|_| "搜索工具超过30秒，已停止".to_string())?
}

fn normalize(data: serde_json::Value) -> Result<serde_json::Value, String> {
    if let Some(error) = data["error"].as_str() { return Err(error.to_string()); }
    let rows = data
        .get("results")
        .or_else(|| data.get("data"))
        .and_then(|v| v.as_array())
        .or_else(|| data.as_array())
        .ok_or("搜索结果结构无效")?;
    let results:Vec<_>=rows.iter().take(5).map(|r|serde_json::json!({"title":r["title"],"url":r.get("url").or_else(||r.get("href")),"content":r.get("content").or_else(||r.get("snippet")).or_else(||r.get("description"))})).collect();
    if results.is_empty() {
        return Err("搜索没有返回结果，不能作为文件用途依据".into());
    }
    Ok(serde_json::json!({"results":results}))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn normalize_both_formats_and_reject_empty() {
        for key in ["results", "data"] {
            let v = serde_json::json!({key:[{"title":"Doc","url":"https://example.org","snippet":"text"}]});
            assert_eq!(normalize(v).unwrap()["results"][0]["content"], "text");
        }
        assert!(normalize(serde_json::json!({"data":[]})).is_err());
        assert!(normalize(serde_json::json!({"error":"blocked"})).is_err());
    }
    #[tokio::test]
    #[ignore = "live public documentation search; requires installed tools"]
    async fn live_local_search_tools() {
        let path = std::env::var_os("C_MANAGER_SEARCH_CONFIG").unwrap();
        let runtime: Runtime = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        for provider in ["ddgs"] {
            let start = std::time::Instant::now();
            let result = run(&runtime, "WSL ext4.vhdx site:learn.microsoft.com").await;
            println!("{provider}: {:?}, {:?}", start.elapsed(), result);
            let data = result.unwrap();
            assert!(data["results"].as_array().unwrap().iter().any(|r| r["url"]
                .as_str()
                .is_some_and(|u| u.starts_with("https://learn.microsoft.com/"))));
        }
    }
}
