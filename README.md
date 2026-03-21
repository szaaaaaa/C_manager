# C盘守护者

专治"C盘清理焦虑症"的桌面端智能文件解释工具。

普通用户面对 C 盘里 `WinSxS`、`SoftwareDistribution`、`ntoskrnl.exe` 这些天书般的文件名，只有两个反应：不敢删，或者删完蓝屏。C盘守护者解决的就是这个问题——**扫描大文件 → 用大白话解释是什么 → 红绿灯告诉你能不能删**。

核心原则：**只当军师，绝不动手**。本工具不会执行任何删除操作。

## 功能

- **Rust MFT 极速扫描** — 直读 NTFS 主文件表，秒级扫完整个 C 盘
- **AI 白话翻译** — 点击文件，AI 用通俗幽默的中文解释它是干嘛的
- **红绿灯安全评级** — 🟢可以删 🟡建议保留 🔴系统核心别碰
- **多模型支持** — OpenRouter 动态拉取可用模型列表

## 技术栈

| 层 | 技术 |
|----|------|
| 桌面框架 | Tauri 2 |
| 后端 | Rust（mft, reqwest, serde） |
| 前端 | React 19, TypeScript, Vite, Framer Motion |
| AI | OpenRouter / OpenAI 兼容 API |

## 环境要求

- [Rust](https://rustup.rs/) (stable)
- Node.js 18+
- Tauri 2 prerequisites: https://tauri.app/start/prerequisites/

## 开发

```bash
# 安装前端依赖
cd frontend
npm install

# 启动 Tauri 开发模式（同时编译 Rust + 启动 Vite）
npx tauri dev
```

## 构建

```bash
cd frontend
npx tauri build
```

产出在 `src-tauri/target/release/bundle/` 下。

## 设置

侧边栏「设置」中可配置：

- **API Key** — 环境变量（OPENROUTER_API_KEY / OPENAI_API_KEY）自动识别，或手动输入
- **Base URL** — 默认 OpenRouter，可改为任意 OpenAI 兼容接口
- **模型选择** — 下拉列表从 OpenRouter 动态拉取，也支持手动输入
