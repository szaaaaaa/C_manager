# C_manager — C盘守护者

## 项目简介
C盘守护者：一个专治"C盘清理焦虑症"的桌面端智能文件解释工具。
- 直击痛点：解决普通用户面对 C 盘里各种晦涩英文文件夹时，"看不懂、不敢删、怕删崩系统"的终极恐惧
- 核心机制：Rust 直读 NTFS MFT 秒级扫描 + AI 白话翻译 + 红绿灯安全评级
- 最大卖点：Agent 只当军师，绝不越权代劳删除操作

## 架构
Tauri 桌面应用：Rust 后端 + React 前端（WebView）。无 Python 依赖。

## 开发规范（强制）
**每次写代码前，必须先阅读以下 skills：**
- `.claude/skills/first-principles-thinking.md` — 先追溯本质需求
- `.claude/skills/implementation-discipline.md` — 先读后写，完整实现
- `.claude/skills/solution-standards.md` — 最短路径，不过度封装
- `.claude/skills/session-discipline.md` — 跨轮次一致性

## 技术栈
- 扫描引擎：Rust（mft crate，Windows 直读 MFT；非 Windows 用 read_dir 遍历）
- 后端：Rust（Tauri commands，reqwest 代理 LLM API）
- 前端：React 19 + TypeScript + Vite + Framer Motion
- LLM：OpenRouter / OpenAI 兼容接口
- 安全评级：编译时嵌入的 rules.json 模式匹配
- 安全原则：**绝对不执行任何删除操作**，只提供建议

## 项目结构
```
C_manager/
├── src-tauri/                 # Tauri Rust 后端
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   └── src/
│       ├── lib.rs             # Tauri 入口，注册 commands
│       ├── main.rs
│       ├── commands/          # Tauri commands
│       │   ├── scan.rs        # scan_drive — MFT 扫描
│       │   ├── drive.rs       # get_drive_info — 磁盘信息
│       │   ├── explain.rs     # explain_item — LLM 解释代理
│       │   └── models.rs      # fetch_models, get_env_key
│       ├── scanner/           # 扫描引擎
│       │   ├── mft_reader.rs  # NTFS MFT 解析（Windows only）
│       │   └── models.rs      # FileRecord
│       └── safety/            # 安全评级
│           ├── mod.rs         # rate_safety()
│           └── rules.json     # 红绿灯规则
└── frontend/                  # React 前端
    └── src/
        ├── App.tsx
        ├── api.ts             # invoke() 调用 Tauri commands
        ├── types.ts
        └── components/
```
