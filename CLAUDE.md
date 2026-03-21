# C_manager — C盘守护者

## 项目简介
C盘守护者：一个专治"C盘清理焦虑症"的桌面端智能文件解释工具。
- 直击痛点：解决普通用户面对 C 盘里各种晦涩英文文件夹时，"看不懂、不敢删、怕删崩系统"的终极恐惧
- 核心机制：Rust 直读 NTFS MFT 秒级扫描 + AI 白话翻译 + 红绿灯安全评级
- 最大卖点：Agent 只当军师，绝不越权代劳删除操作

## 核心功能
1. **Rust MFT 极速扫描** — 直读 NTFS 主文件表，秒级扫完全盘大文件
2. **AI 白话翻译** — 点击文件调用 LLM，用通俗幽默的大白话解释文件用途
3. **红绿灯安全评级** — 🟢安全可删、🟡建议保留、🔴系统核心别碰

## 开发规范（强制）
**每次写代码前，必须先阅读以下 skills：**
- `.claude/skills/first-principles-thinking.md` — 先追溯本质需求
- `.claude/skills/implementation-discipline.md` — 先读后写，完整实现
- `.claude/skills/solution-standards.md` — 最短路径，不过度封装
- `.claude/skills/session-discipline.md` — 跨轮次一致性

## 技术栈
- 扫描引擎：Rust（mft crate + PyO3）
- 前端：React + TypeScript + Vite + Framer Motion
- LLM：OpenRouter / OpenAI 兼容接口，预留本地模型接口
- 安全原则：**绝对不执行任何删除操作**，只提供建议

## 项目结构
```
C_manager/
├── CLAUDE.md              # 本文件
├── .claude/               # Claude Code 配置
│   ├── skills/            # 开发规范
│   └── settings.json      # 权限和 hooks
├── rust_scanner/          # Rust MFT 扫描器（PyO3 扩展）
│   ├── Cargo.toml
│   ├── pyproject.toml
│   └── src/
│       ├── lib.rs         # PyO3 模块入口
│       ├── mft_reader.rs  # MFT 解析 + 路径重建
│       └── models.rs      # FileRecord 结构体
└── frontend/              # React 前端
    └── src/
        ├── App.tsx
        ├── api.ts
        ├── types.ts
        └── components/
```
