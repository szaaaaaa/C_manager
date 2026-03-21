# C盘守护者

专治"C盘清理焦虑症"的桌面端智能文件解释工具。

普通用户面对 C 盘里 `WinSxS`、`SoftwareDistribution`、`ntoskrnl.exe` 这些天书般的文件名，只有两个反应：不敢删，或者删完蓝屏。C盘守护者解决的就是这个问题——**扫描大文件 → 用大白话解释是什么 → 红绿灯告诉你能不能删**。

核心原则：**只当军师，绝不动手**。本工具不会执行任何删除操作。

## 功能

- **Rust MFT 极速扫描** — 直读 NTFS 主文件表，秒级扫完整个 C 盘
- **AI 白话翻译** — 点击文件，AI 用通俗幽默的中文解释它是干嘛的
- **红绿灯安全评级** — 🟢可以删 🟡建议保留 🔴系统核心别碰
- **多模型支持** — OpenRouter 动态拉取可用模型列表，预留本地模型接口

## 技术栈

| 层 | 技术 |
|----|------|
| 扫描引擎 | Rust（mft crate + PyO3） |
| 前端 | React 19, TypeScript, Vite, Framer Motion |
| AI | OpenRouter / OpenAI 兼容 API |

## 项目结构

```
C_manager/
├── rust_scanner/              # Rust MFT 扫描器
│   ├── Cargo.toml             # 依赖: mft, pyo3, rayon
│   ├── pyproject.toml         # maturin 构建配置
│   └── src/
│       ├── lib.rs             # PyO3 模块入口，暴露 scan_mft()
│       ├── mft_reader.rs      # MFT 解析、路径重建、排序
│       └── models.rs          # FileRecord 结构体
└── frontend/                  # React 前端
    └── src/
        ├── App.tsx            # 主容器
        ├── api.ts             # HTTP 客户端
        ├── types.ts           # 类型定义
        └── components/
            ├── Dashboard.tsx       # 扫描控制面板
            ├── ScanResults.tsx     # 结果列表
            ├── ExplanationBubble.tsx # AI 解释气泡
            ├── Sidebar.tsx         # 导航 + 设置面板
            ├── DriveRing.tsx       # 磁盘用量环形图
            └── SafetyBadge.tsx     # 红绿灯徽章
```

## 编译 Rust 扫描器

```bash
cd rust_scanner
pip install maturin
maturin develop --release
```

需要管理员权限运行才能读取 MFT。

## 前端开发

```bash
cd frontend
npm install
npm run dev
```

## 设置

侧边栏「设置」中可配置：

- **AI 后端** — 云端 API / 本地模型 / 自动
- **API Key** — 环境变量自动识别，或手动输入
- **Base URL** — 默认 OpenRouter，可改为任意 OpenAI 兼容接口
- **模型选择** — 下拉列表从 OpenRouter 动态拉取，也支持手动输入
