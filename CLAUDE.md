# C_manager — C盘守护者

## 项目简介
C盘守护者：一个专治"C盘清理焦虑症"的桌面端实用 Agent。
- 直击痛点：解决普通用户面对 C 盘里各种晦涩英文文件夹时，"看不懂、不敢删、怕删崩系统"的终极恐惧
- 核心机制：本地极速扫描 + 大模型白话翻译 + 红绿灯安全评级
- 最大卖点：Agent 只当军师，绝不越权代劳删除操作

## 核心功能
1. **本地极速扫描** — 高效文件遍历，瞬间揪出占用空间最大的"内存刺客"
2. **大模型白话翻译** — 鼠标悬停时调用 LLM，用通俗幽默的大白话解释文件用途
3. **红绿灯安全评级** — 🟢安全可删、🟡建议保留、🔴系统核心别碰

## 开发规范（强制）
**每次写代码前，必须先阅读以下 skills：**
- `.claude/skills/first-principles-thinking.md` — 先追溯本质需求
- `.claude/skills/implementation-discipline.md` — 先读后写，完整实现
- `.claude/skills/solution-standards.md` — 最短路径，不过度封装
- `.claude/skills/session-discipline.md` — 跨轮次一致性

## 技术约束
- 语言：Python（扫描核心可用 Rust/Go 加速，但 MVP 阶段用 Python）
- UI：桌面端（Electron / Tauri / PyQt 待定）
- LLM 调用：支持多 provider（OpenRouter / OpenAI / 本地模型）
- 安全原则：**绝对不执行任何删除操作**，只提供建议
- 最小依赖：标准库优先，必要时引入 psutil

## 项目结构（规划）
```
C_manager/
├── CLAUDE.md              # 本文件
├── .claude/               # Claude Code 配置
│   ├── skills/            # 开发规范
│   ├── commands/          # 工作流（ship/review-fix/merge）
│   └── settings.json      # 权限和 hooks
├── src/                   # 源代码
│   ├── scanner/           # 文件扫描引擎
│   ├── analyzer/          # LLM 分析和安全评级
│   └── ui/                # 用户界面
├── tests/                 # 测试
└── configs/               # 配置文件
```
