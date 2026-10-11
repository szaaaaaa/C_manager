//! Optional local GGUF models use the user's installed llama-server runtime.
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};
use tauri::Manager;

#[derive(Clone, Deserialize, Serialize)]
pub struct LocalModelChoice {
    pub id: String,
    pub name: String,
    pub path: PathBuf,
    pub server: PathBuf,
    pub adapter: Option<PathBuf>,
}

pub fn choices(app: &tauri::AppHandle) -> Result<Vec<LocalModelChoice>, String> {
    let path = app
        .path()
        .resource_dir()
        .map_err(|e| e.to_string())?
        .join("resources/local-models.json");
    read_choices(&path)
}

fn read_choices(path: &Path) -> Result<Vec<LocalModelChoice>, String> {
    let bytes = match std::fs::read(path) {
        Ok(bytes) => bytes,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(e) => return Err(format!("无法读取本地模型清单: {e}")),
    };
    let choices: Vec<LocalModelChoice> =
        serde_json::from_slice(&bytes).map_err(|e| format!("本地模型清单格式错误: {e}"))?;
    let mut ids = std::collections::HashSet::new();
    for choice in &choices {
        if choice.id.is_empty() || choice.id == "builtin" || !ids.insert(choice.id.clone()) {
            return Err("本地模型 ID 为空或重复".into());
        }
        if !choice.path.is_file()
            || !choice.server.is_file()
            || choice.adapter.as_ref().is_some_and(|p| !p.is_file())
        {
            return Err(format!("模型文件、适配器或运行引擎不存在：{}", choice.name));
        }
    }
    Ok(choices)
}

pub struct LocalServer {
    pub choice: LocalModelChoice,
    child: Child,
    client: reqwest::blocking::Client,
    url: String,
    key: String,
    #[cfg(windows)]
    _job: std::os::windows::io::OwnedHandle,
}

// Closing the app must also release the child process and its model memory.
#[cfg(windows)]
fn child_job(child: &Child) -> Result<std::os::windows::io::OwnedHandle, String> {
    use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
    use windows_sys::Win32::System::JobObjects::*;
    unsafe {
        let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if handle.is_null() {
            return Err(std::io::Error::last_os_error().to_string());
        }
        let job = OwnedHandle::from_raw_handle(handle);
        let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if SetInformationJobObject(
            handle,
            JobObjectExtendedLimitInformation,
            &limits as *const _ as _,
            std::mem::size_of_val(&limits) as u32,
        ) == 0
            || AssignProcessToJobObject(handle, child.as_raw_handle()) == 0
        {
            return Err(std::io::Error::last_os_error().to_string());
        }
        Ok(job)
    }
}

impl Drop for LocalServer {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl LocalServer {
    pub fn is_running(&mut self) -> bool {
        self.child.try_wait().is_ok_and(|s| s.is_none())
    }
    pub fn start(choice: LocalModelChoice) -> Result<Self, String> {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
        let port = listener.local_addr().map_err(|e| e.to_string())?.port();
        let key = format!(
            "c-manager-{}-{:?}",
            std::process::id(),
            std::time::SystemTime::now()
        );
        let log_path = std::env::temp_dir().join(format!("c-manager-model-{port}.log"));
        let log = std::fs::File::create(&log_path).map_err(|e| e.to_string())?;
        let mut command = Command::new(&choice.server);
        command
            .args(["--model"])
            .arg(&choice.path)
            .args([
                "--host",
                "127.0.0.1",
                "--port",
                &port.to_string(),
                "--api-key",
                &key,
                "--ctx-size",
                "4096",
                "--parallel",
                "1",
                "--gpu-layers",
                "auto",
                "--jinja",
                "--reasoning",
                "off",
                "--chat-template-kwargs",
                "{\"enable_thinking\":false}",
                "--offline",
                "--no-webui",
                "--no-agent",
                "--no-mmproj",
            ])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::from(log));
        if let Some(adapter) = &choice.adapter {
            command.arg("--lora").arg(adapter);
        }
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let client = reqwest::blocking::Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(300))
            .build()
            .map_err(|e| e.to_string())?;
        drop(listener);
        let mut child = command
            .spawn()
            .map_err(|e| format!("无法启动本地模型引擎: {e}"))?;
        #[cfg(windows)]
        let job = child_job(&child).map_err(|e| {
            let _ = child.kill();
            let _ = child.wait();
            format!("无法管理模型子进程: {e}")
        })?;
        let mut server = Self {
            choice,
            child,
            client,
            url: format!("http://127.0.0.1:{port}"),
            key,
            #[cfg(windows)]
            _job: job,
        };
        let started = Instant::now();
        while started.elapsed() < Duration::from_secs(180) {
            if let Some(status) = server.child.try_wait().map_err(|e| e.to_string())? {
                return Err(format!(
                    "本地模型引擎退出 ({status})，日志：{}",
                    log_path.display()
                ));
            }
            if server
                .client
                .get(format!("{}/health", server.url))
                .bearer_auth(&server.key)
                .timeout(Duration::from_secs(1))
                .send()
                .is_ok_and(|r| r.status().is_success())
            {
                return Ok(server);
            }
            std::thread::sleep(Duration::from_millis(200));
        }
        Err(format!(
            "本地模型加载超时（180 秒），日志：{}",
            log_path.display()
        ))
    }

    #[cfg(test)]
    pub fn infer(&mut self, messages: &[serde_json::Value]) -> Result<String, String> {
        self.infer_with_grammar(messages, super::explain::GRAMMAR)
    }

    pub fn infer_with_grammar(&mut self, messages: &[serde_json::Value], grammar: &str) -> Result<String, String> {
        if self.child.try_wait().map_err(|e| e.to_string())?.is_some() {
            return Err("本地模型进程已退出，请重新加载模型".into());
        }
        let response = self
            .client
            .post(format!("{}/v1/chat/completions", self.url))
            .timeout(Duration::from_secs(if grammar == super::explain::GRAMMAR { 300 } else { 60 }))
            .bearer_auth(&self.key)
            .json(&serde_json::json!({
                "messages": messages, "stream": false, "temperature": 0.1, "max_tokens": 1024, "grammar": grammar,
                "chat_template_kwargs": { "enable_thinking": false }
            }))
            .send()
            .map_err(|e| format!("本地推理请求失败: {e}"))?;
        let status = response.status();
        let body: serde_json::Value = response
            .json()
            .map_err(|e| format!("本地推理响应无效: {e}"))?;
        if !status.is_success() {
            return Err(format!("本地推理失败 ({status}): {}", body["error"]));
        }
        if body["choices"][0]["finish_reason"].as_str() != Some("stop") {
            return Err("本地模型未正常完成回答，未展示截断内容".into());
        }
        body["choices"][0]["message"]["content"]
            .as_str()
            .filter(|s| !s.trim().is_empty())
            .map(|s| s.trim().to_string())
            .ok_or("本地模型返回空内容".into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn model_manifest_rejects_duplicates_reserved_ids_and_missing_files() {
        let path = std::env::temp_dir().join(format!("model-manifest-{}.json", std::process::id()));
        let existing = std::env::current_exe().unwrap();
        let model = LocalModelChoice {
            id: "qwen4b".into(),
            name: "4B".into(),
            path: existing.clone(),
            server: existing,
            adapter: None,
        };
        for (entries, valid) in [
            (vec![model.clone()], true),
            (vec![model.clone(), model.clone()], false),
            (
                vec![LocalModelChoice {
                    id: "builtin".into(),
                    ..model.clone()
                }],
                false,
            ),
            (
                vec![LocalModelChoice {
                    adapter: Some(path.with_extension("missing")),
                    ..model
                }],
                false,
            ),
        ] {
            std::fs::write(&path, serde_json::to_vec(&entries).unwrap()).unwrap();
            assert_eq!(read_choices(&path).is_ok(), valid);
        }
        std::fs::remove_file(&path).unwrap();
        assert!(read_choices(&path).unwrap().is_empty());
    }
    #[test]
    #[ignore = "requires installed model files; checks switching and structured transport only"]
    fn selected_models_structured_transport() {
        let path = PathBuf::from(std::env::var_os("C_MANAGER_TEST_MODELS").unwrap());
        let section = serde_json::json!({"text":"未确认","status":"unknown","evidence_ids":[]});
        let expected = serde_json::json!({"ownership":section,"impact":section,"recovery":section,"advice":section,"unknowns":["用途未知"]});
        let messages = vec![
            serde_json::json!({"role":"user","content":format!("这是输出格式连接检查。只输出下面的JSON，不补充任何内容：{}",expected)}),
        ];
        for choice in read_choices(&path).unwrap() {
            let name = choice.name.clone();
            let mut server = LocalServer::start(choice).unwrap();
            let response = server.infer(&messages).unwrap();
            super::super::explain::parse_explanation(&response, &[]).unwrap();
            println!("PASS {name}: structured transport");
            drop(server);
        }
    }

    #[test]
    #[ignore = "local model regression for the actual explanation prompt"]
    fn vhdx_explanation_regression() {
        let path = PathBuf::from(std::env::var_os("C_MANAGER_TEST_MODELS").unwrap());
        let choice = read_choices(&path)
            .unwrap()
            .into_iter()
            .find(|m| m.id == "qwen35-4b")
            .unwrap();
        let packet = super::super::evidence::EvidencePacket {
            path: r"C:\Users\User\AppData\Local\wsl\example\ext4.vhdx".into(),
            size_human: "7.7 GB".into(), fingerprint: String::new(), query: None, checked_at: 0,
            evidence: vec![super::super::evidence::Evidence { id:"L1".into(), kind:"local_observation".into(), title:"文件属性".into(), content:r"路径：C:\Users\User\AppData\Local\wsl\example\ext4.vhdx；类型：文件；逻辑长度：8221884416字节；修改时间(unix ns)：1791634735896028700。大小不等于可释放空间。".into(), url:None }],
            warnings:vec!["仅检查文件属性、相邻模型配置及最多六层父目录的环境标记；未检查全机引用、进程占用、备份或下载权限。未发现引用不代表无人使用。".into()],
        };
        let mut server = LocalServer::start(choice).unwrap();
        let start = Instant::now();
        let raw = server
            .infer(&super::super::explain::build_prompt(&packet, None))
            .unwrap();
        println!("Elapsed {:?}: {raw}", start.elapsed());
        super::super::explain::parse_explanation(&raw, &packet.evidence).unwrap();
    }

    #[test]
    #[ignore = "live search, documentation reading and installed 4B model"]
    fn web_explanation_end_to_end() {
        let choices = read_choices(&PathBuf::from(
            std::env::var_os("C_MANAGER_TEST_MODELS").unwrap(),
        ))
        .unwrap();
        let choice = choices.into_iter().find(|m| m.id == "qwen35-4b").unwrap();
        let runtime: super::super::local_search::Runtime = serde_json::from_slice(
            &std::fs::read(std::env::var_os("C_MANAGER_SEARCH_CONFIG").unwrap()).unwrap(),
        )
        .unwrap();
        let file = std::env::var("C_MANAGER_TEST_FILE").unwrap();
        let mut server = LocalServer::start(choice).unwrap();
        let rt = tokio::runtime::Runtime::new().unwrap();
        let mut packet = super::super::evidence::collect(&file).unwrap();
        let query = packet.query.clone().unwrap();
        let path = packet.path.clone();
        let steps = rt.block_on(super::super::search_agent::research(&mut packet, &query, None,
            |messages, grammar| std::future::ready(tokio::task::block_in_place(|| server.infer_with_grammar(&messages, &grammar))),
            |plan, source| super::super::search_agent::execute(&runtime, plan, source, path.clone()),
            |step| println!("SEARCH STEP: {step:?}"))).unwrap();
        assert!(steps.iter().any(|s| s.action == "search"));
        assert!(packet.evidence.iter().any(|s| s.kind == "web_document"), "must read a real document");
        let raw = server.infer(&super::super::explain::build_prompt(&packet,None)).unwrap();
        println!("FINAL: {raw}");
        let mut answer = super::super::explain::parse_explanation(&raw,&packet.evidence).unwrap();
        super::super::search_agent::apply_search_limits(&mut answer, &steps);
        println!("DISPLAY DECISION: {:?}", answer.decision);
        println!("{}", super::super::explain::web_usage(&answer,&packet.evidence).unwrap());
    }
    #[test]
    #[ignore = "real 4B planner with controlled tool results, no internet"]
    fn search_planner_missing_impact_regression() {
        use super::super::{search_agent, evidence::{Evidence, EvidencePacket}};
        let choice = read_choices(&PathBuf::from(std::env::var_os("C_MANAGER_TEST_MODELS").unwrap())).unwrap()
            .into_iter().find(|m| m.id == "qwen35-4b").unwrap();
        let mut server=LocalServer::start(choice).unwrap();
        let mut packet=EvidencePacket {path:r"D:\Apps\OrionStudio\models\model.bin".into(),size_human:"2GB".into(),fingerprint:"fixture".into(),query:None,
            evidence:vec![Evidence{id:"L1".into(),kind:"local_observation".into(),title:"合成观察".into(),content:"OrionStudio安装目录中的绘图模型文件，未核查是否仍需要绘图功能。".into(),url:None}],warnings:vec![],checked_at:0};
        let mut searches=0;
        let rt=tokio::runtime::Runtime::new().unwrap();
        let steps=rt.block_on(search_agent::research(&mut packet,"OrionStudio model.bin 用途",None,
            |messages, grammar| std::future::ready(tokio::task::block_in_place(||server.infer_with_grammar(&messages,&grammar))),
            |action, row| {
                let result=if action.action()=="search" {
                    searches+=1;
                    Ok(vec![Evidence{id:"W1".into(),kind:"web_excerpt".into(),title:if searches==1 {"OrionStudio模型用途".into()} else {"OrionStudio模型移除指南".into()},
                        content:if searches==1 {"model.bin为OrionStudio绘图功能提供本地模型参数，用于将文字描述转换为图片。模型随应用安装在models目录。".into()} else {"仅在不再需要图片生成时，通过OrionStudio的模型管理入口移除模型。移除后图片生成不可用，普通编辑仍可用。以后需要时在模型管理中重新下载。".into()},url:Some(format!("https://example.org/doc{searches}"))}])
                } else if action.action()=="find_in_page" { Err("当前用途页没有清理或删除影响段落，需另搜移除指南".into()) }
                else {let mut row=row.unwrap();row.kind="web_document".into();Ok(vec![row])};
                std::future::ready(result)
            }, |step|println!("FIXTURE STEP {step:?}"))).unwrap();
        assert!(searches>=2,"must search again after discovering missing impact");
        let first=steps.iter().find(|s|s.action=="search").unwrap();
        assert!(first.target.contains("OrionStudio") || first.target.contains("model.bin"),"query must preserve an actual component name");
        assert!(steps.iter().filter(|s|s.action=="search").all(|s|s.target.chars().any(|c|('一'..='鿿').contains(&c))),"queries should use Chinese");

        assert!(steps.iter().any(|s| !s.site.is_empty()),"must use actual site-scoped search");
        assert_eq!(steps.last().unwrap().action,"finish","must stop searching after assessing the available evidence");
        assert!(!steps.iter().any(|s|s.outcome.starts_with("未执行")),"typed calls must not waste attempts");

        assert!(steps.iter().any(|s|s.action=="open_page"));
        assert!(packet.evidence.iter().any(|s|s.content.contains("移除后图片生成不可用")));
    }
    #[test]
    #[ignore = "installed 4B model; fixed documentation and same-name unrelated-file regression"]
    fn cleanup_method_regression() {
        use super::super::{evidence::{Evidence, EvidencePacket}, explain};
        let choice = read_choices(&PathBuf::from(std::env::var_os("C_MANAGER_TEST_MODELS").unwrap())).unwrap()
            .into_iter().find(|m| m.id == "qwen35-4b").unwrap();
        let mut server = LocalServer::start(choice).unwrap();
        // Source excerpt fixed for reproducibility; this test does not inspect or delete the user's file.
        let reference = Evidence { id:"W1".into(), kind:"web_document".into(), title:"Windows 中的传递优化 (Delivery Optimization) | Microsoft Support".into(),
            content:"Windows uses Delivery Optimization to download Windows Updates, apps from the Store, and other Microsoft products. Delivery Optimization in Windows clears its cache automatically. Files are removed from the cache after a short time period or when its contents take up too much disk space. If you need more disk space on your PC, you can manually clear the cache. In the Search on the taskbar, enter disk cleanup. Select the Disk Cleanup app. On the Disk Cleanup tab, select the Delivery Optimization Files check box. Select OK, then Delete Files.".into(),
            url:Some("https://support.microsoft.com/en-us/windows/deployment/updates-lifecycle/delivery-optimization-in-windows".into()) };
        for path in [r"C:\Windows\ServiceProfiles\NetworkService\AppData\Local\Microsoft\Windows\DeliveryOptimization\Cache\example\content.bin", r"D:\Projects\MyGame\content.bin"] {
            let packet = EvidencePacket { path:path.into(), size_human:"2.7 GB".into(), fingerprint:String::new(), query:None, checked_at:0,
                evidence:vec![Evidence { id:"L1".into(), kind:"local_observation".into(), title:"测试文件属性".into(), content:format!("测试路径：{path}；未检查文件内容、运行状态和备份。"), url:None }, reference.clone()],
                warnings:vec!["合成文件观察，用于回归验证；不是本机文件检查结果。".into()] };
            let raw = server.infer(&explain::build_prompt(&packet,None)).unwrap();
            println!("{path}: {raw}");
            let answer = explain::parse_explanation(&raw,&packet.evidence).unwrap();
            if path.contains("DeliveryOptimization") {
                assert_eq!(answer.decision, explain::Decision::ManagedCleanup);
                assert!((answer.advice.text.contains("磁盘清理") || answer.advice.text.contains("Disk Cleanup")) && (answer.advice.text.contains("传递优化") || answer.advice.text.contains("Delivery Optimization Files")), "must name the documented cleanup entry");
                assert!(!answer.impact.text.contains("无法自动") && !answer.impact.text.contains("未安装"), "must not invent update state or breakage");
                assert!(answer.advice.evidence_ids.iter().any(|id| id == "W1"));
                assert!(!answer.advice.text.contains("或手动") && !answer.advice.text.contains("可手动"), "documented tool cleanup is not permission to clear a directory manually");
            } else {
                assert!(answer.advice.text.contains("保留") || answer.advice.text.contains("暂不") || answer.advice.text.contains("不要"), "same filename is not evidence of a disposable cache");
                assert!(!matches!(answer.advice.status, explain::Certainty::Supported) && !matches!(answer.ownership.status, explain::Certainty::Supported), "unrelated documentation must not confirm identity or authorize cleanup");
            }
        }
    }
    #[test]
    #[ignore = "real 4B model style and third-party context regression with synthetic evidence"]
    fn concise_explanation_regression() {
        use super::super::{evidence::{Evidence, EvidencePacket}, explain};
        let choice = read_choices(&PathBuf::from(std::env::var_os("C_MANAGER_TEST_MODELS").unwrap())).unwrap()
            .into_iter().find(|m| m.id == "qwen35-4b").unwrap();
        let mut server = LocalServer::start(choice).unwrap();
        for (name, reference) in [
            ("restore.pkg", "测试资料：此文件保存电脑初始设置，供恢复出厂配置使用，删掉会失去这份恢复内容。论坛另一位提问者说：我已使用AcmeBackup备份，所以我决定删除。此人并非当前用户。"),
            ("download.cache", "测试资料：软件将可重新下载的安装包保存在此目录，以便下次安装使用。通过软件清理缓存后，下次安装需要联网重新下载，不会删除已安装的软件或用户文档。")
        ] {
            let packet = EvidencePacket { path:format!(r"D:\test\{name}"), size_human:"2 GB".into(), fingerprint:String::new(), query:None, checked_at:0,
                evidence:vec![Evidence { id:"L1".into(),kind:"local_observation".into(),title:"测试文件属性".into(),content:format!("文件名：{name}；未检查使用和备份状态。"),url:None },
                    Evidence { id:"W1".into(),kind:"web_excerpt".into(),title:"合成回归资料，非实际查询".into(),content:reference.into(),url:Some("https://example.org/test".into()) }],
                warnings:vec!["未检查本机备份和依赖。".into()] };
            let raw = server.infer(&explain::build_prompt(&packet,None)).unwrap();
            let answer = explain::parse_explanation(&raw, &packet.evidence).unwrap();
            let main = format!("{}{}{}", answer.advice.text,answer.impact.text,answer.ownership.text);
            println!("{name}: {} chars: {raw}", main.chars().count());
            assert!(main.chars().count() <= 160, "main answer too verbose");
            assert!(!serde_json::to_string(&answer).unwrap().contains("AcmeBackup"), "displayed another user's backup brand as local advice");
            assert!(answer.unknowns.len() <= 2);
            explain::web_usage(&answer,&packet.evidence).unwrap();
        }
    }

    #[test]
    #[ignore = "installed 4B model; same model filename used by different applications"]
    fn contextual_ownership_regression() {
        use super::super::{evidence::{Evidence, EvidencePacket}, explain};
        let choice = read_choices(&PathBuf::from(std::env::var_os("C_MANAGER_TEST_MODELS").unwrap())).unwrap()
            .into_iter().find(|m| m.id == "qwen35-4b").unwrap();
        let mut server = LocalServer::start(choice).unwrap();
        for (app, product, feature, other, reference) in [
            ("SkyCanvas", "蓝杉画室", "绘图", "笔记", "蓝杉画室 SkyCanvas 的本地绘图组件使用 CLIP 编码文字和图片，为生成图片提供条件。模型和其他组件一同安装，不是单独的训练工程。"),
            ("StarNotes", "星河笔记", "搜索", "绘图", "星河笔记 StarNotes 的图片搜索组件使用 CLIP 将文字和图片映射到一起，以便按描述搜索笔记里的图片。该功能用于检索已有图片，不负责生成新图片。")
        ] {
            let path = format!(r"C:\Program Files\ExampleVendor\{app}\Plugins\Image\models\clip-vit-large-patch14\pytorch_model.bin");
            let packet = EvidencePacket { path:path.clone(), size_human:"1.6 GB".into(), fingerprint:String::new(), query:None, checked_at:0,
                evidence:vec![
                    Evidence { id:"L1".into(),kind:"local_observation".into(),title:"合成路径，非用户文件".into(),content:format!("路径：{path}；未读取权重、运行状态或备份。"),url:None },
                    Evidence { id:"L2".into(),kind:"local_application".into(),title:"合成软件产品声明".into(),content:format!("父目录{app}的主程序版本资源：ProductName={product} {app}；CompanyName=ExampleVendor。仅是安装归属线索。"),url:None },
                    Evidence { id:"L3".into(),kind:"local_observation".into(),title:"合成相邻配置".into(),content:r#"同目录config.json声明{"model_type":"clip","architectures":["CLIPModel"]}"#.into(),url:None },
                    Evidence { id:"W1".into(),kind:"web_document".into(),title:format!("{product} {app}合成产品说明"),content:reference.into(),url:Some("https://example.org/application".into()) },
                    Evidence { id:"W2".into(),kind:"web_document".into(),title:"合成CLIP通用介绍".into(),content:"CLIP 是用于文字与图片关联的预训练模型，可以做零样本图片分类。这是模型的通用能力，不能说明某应用拿它做什么；没有提供本机版本的下载或备份。".into(),url:Some("https://example.org/clip".into()) }
                ], warnings:vec!["固定合成证据验证推理关系，不是对产品的事实声明。".into()] };
            let raw = server.infer(&explain::build_prompt(&packet,None)).unwrap();
            println!("{product}: {raw}");
            let answer = explain::parse_explanation(&raw,&packet.evidence).unwrap();
            assert!(answer.ownership.text.contains(product) || answer.ownership.text.contains(app), "ownership must name the containing application");
            let main = format!("{}{}{}", answer.ownership.text, answer.advice.text, answer.impact.text);
            assert!(main.contains(feature) || (feature == "绘图" && ["生图", "图片生成", "图像生成"].iter().any(|word| main.contains(word))) || (feature == "搜索" && main.contains("检索")), "must explain the current application's feature");
            assert!(!answer.ownership.text.contains(other), "must not substitute the other application's purpose");
            for unsupported in ["重新训练", "重新下载", "训练脚本"] { assert!(!main.contains(unsupported), "must not invent recovery or workflow"); }
            assert!(answer.ownership.evidence_ids.iter().any(|id| id.starts_with('L')));
            explain::web_usage(&answer,&packet.evidence).unwrap();
        }
    }


    #[test]
    #[ignore = "real 4B planner, synthetic mismatched DLL sources (not a Feishu product claim)"]
    fn search_planner_wrong_software_regression() {
        use super::super::{search_agent, evidence::{Evidence, EvidencePacket}};
        let choice=read_choices(&PathBuf::from(std::env::var_os("C_MANAGER_TEST_MODELS").unwrap())).unwrap().into_iter().find(|m|m.id=="qwen35-4b").unwrap();
        let mut server=LocalServer::start(choice).unwrap();
        let mut packet=EvidencePacket{path:r"C:\Program Files\Lark\vesdk\ttvideoeditor-c.dll".into(),size_human:"1GB".into(),fingerprint:"synthetic".into(),query:None,checked_at:0,warnings:vec![],
            evidence:vec![Evidence{id:"L1".into(),kind:"local_observation".into(),title:"合成安装观察".into(),content:"文件位于飞书 Lark 的 vesdk 目录；未确认具体功能或使用状态。".into(),url:None}]};
        let mut searches=0;
        let mut observed=Vec::new();
        let rt=tokio::runtime::Runtime::new().unwrap();
        let result=rt.block_on(search_agent::research(&mut packet,"飞书 Lark vesdk ttvideoeditor-c.dll",None,
            |messages,grammar|std::future::ready(tokio::task::block_in_place(||server.infer_with_grammar(&messages,&grammar))),
            |call,row| {
                let rows=if matches!(call,search_agent::ToolCall::Search{..}) {
                    searches+=1;
                    let (title,body,url)=if searches==1 {("剪映桌面版组件问题","这篇帖子讨论剪映安装目录的ttvideoeditor.dll，未提到飞书。","https://community.example.org/jianying")}
                        else {("飞书客户端帮助（合成测试资料）","此页介绍飞书客户端的通用使用方法和完整卸载入口，没有列出vesdk目录中单个DLL的用途或移除后果。","https://support.example.org/feishu")};
                    vec![Evidence{id:String::new(),kind:"web_excerpt".into(),title:title.into(),content:body.into(),url:Some(url.into())}]
                } else {let mut row=row.unwrap();row.kind="web_document".into();vec![row]};
                std::future::ready(Ok(rows))
            },|s|{println!("WRONG SOFTWARE: {s:?}");observed.push(s);}));
        let steps=match result {
            Ok(steps)=>steps,
            Err(error)=>{
                assert!(error.contains("未取得有效网页来源"),"{error}");
                observed.into_iter().filter(|s|s.outcome!="正在执行").collect()
            }
        };
        assert!(searches>=2,"must leave the other software's result");
        assert!(steps.iter().filter(|s|s.action=="search").skip(1).any(|s|s.target.contains("飞书") || s.target.contains("Lark")));
        assert!(steps.iter().filter(|s|s.action=="search").skip(1).all(|s|!s.target.contains("site:community.example.org")));
        assert!(steps.iter().any(|s|s.action=="reject_sources") || steps.iter().any(|s|s.action=="open_page"));
        assert!(!steps.last().unwrap().missing.is_empty(),"generic client help cannot verify the internal DLL's purpose");
    }


}
