# C盘守护者

Windows 桌面文件分析工具：扫描大文件，解释常见软件文件的用途，并给出保守的清理建议。它也用于研究 Qwen3.5-0.8B 这类极小模型的微调和本地检索增强生成。

## 当前功能

- **文件扫描**：有权限时通过 `FSCTL_ENUM_USN_DATA` 枚举 NTFS 文件记录，再查询文件大小；失败则使用目录遍历。扫描根目录、最小大小和最大深度均生效。浅层扫描不能代表完整 C 盘。
- **本地解释**：Rust 内嵌 llama.cpp，使用 GGUF 模型；训练所需的 Python 不属于应用运行依赖。本地用途资料通过路径规则检索，覆盖 WebView2、OneNote 缓存、pip 缓存、PyTorch、Hugging Face 缓存、Node.js 依赖和两类临时目录。
- **云端解释**：支持 OpenRouter 和 OpenAI 兼容接口。配置 Tavily 后可为本地模式补充搜索资料；使用云端或搜索会向相应服务发送路径或查询信息。
- **安全分类**：红色为系统关键位置，黄色表示需要确认，绿色表示已识别的可清理类别。缓存名称、下载目录或 `.bak` 扩展名本身不足以判定安全；绿色也需要确认是否在用、是否需保留。
- **用户操作**：可打开文件所在位置，也可在界面中选择文件并确认移入回收站。项目实际存在删除功能，早期“不会执行任何删除操作”的说明不准确；AI 解释不会自动触发删除。

路径只能提供线索，不能证明文件内容、应用依赖或备份状态。未知路径应明确说明无法确定，解释和颜色都不能作为数据可恢复的保证。

## 实验和验证

本轮四组实验的 [结果与结论](lora-training/experiments/2026-10-09/RESULTS.md) 已公开保存：基础模型、纯 SFT、基础模型＋RAG、检索感知 SFT＋RAG 的固定关键词检查为 8/24、5/24、13/24、21/24。它们不是事实准确率；新模型仍有 pip 删除影响混淆和模板重复。

固定条件见 [实验协议](lora-training/experiments/2026-10-09/PROTOCOL.md)，脚本和训练流程见 [微调说明](lora-training/README.md)。原始回答以 JSON 保存，关键词检查和逐条事实审阅分别报告；验证 loss 不能替代实际回答质量。本机开发/资源目录已换为通过六条原生 smoke 测试的实验 GGUF，重启后生效；GitHub 不含模型权重，仍需按说明生成或放置文件。

扫描修复前，目录遍历忽略配置，强制走 30 层；本机一次读盘比较为 100.94 秒。修复后，配置的 3 层扫描为 3.56 秒，返回范围也更小。这验证了深度参数修复，不是“完整扫描提速 28 倍”。管理员 USN 全盘扫描未在该比较中测量，不能据此承诺秒级扫完整个 C 盘。

## 开发

需要 Windows、Rust stable、Node.js，以及 [Tauri 2 开发环境](https://tauri.app/start/prerequisites/)。本地模型文件不存入 Git，需按微调说明生成或放置模型。

```powershell
cd frontend
npm install
npx tauri dev
```

设置中选择本地模型并加载，或配置云端 API Key、Base URL 和模型名。开发版优先读取 `lora-training/output/finetuned_model_gguf/qwen3.5-0.8b-q4_k_m.gguf`，然后尝试 `src-tauri/resources/`。修改或替换模型后需重启应用重新加载。

```powershell
# 前端检查
cd frontend
npm test
npm run lint
npm run build

# Rust 单元测试（从项目根目录执行）
cd ../src-tauri
cargo test --lib
```

实际模型测试及 C 盘性能比较默认忽略，分别可用 `local_model_chinese_and_explanation_smoke`、`default_scan_performance` 测试名配合 `--ignored --nocapture` 运行。性能比较只读取磁盘，耗时和覆盖范围取决于权限、文件数与深度。

## 构建

先将经过验证的 `qwen3.5-0.8b-q4_k_m.gguf` 放入 `src-tauri/resources/`，再执行：

```powershell
cd frontend
npx tauri build
```

安装包位于 `src-tauri/target/release/bundle/`。模型作为 Tauri resource 打包；模型加载、BF16 实验和安装包端到端验收是不同的检查，实验报告会说明实际完成了哪些。
