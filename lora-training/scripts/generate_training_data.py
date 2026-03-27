"""
Generate distillation training data from scan results.
Groups files by pattern, generates ideal responses for each unique pattern.
Output: training_data.jsonl
"""
import json
import re
import os

# Load scan results
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(PROJECT_ROOT, "data", "raw", "scan_results.json"), "r", encoding="utf-8") as f:
    scan_results = json.load(f)

SYSTEM_PROMPT = (
    "你是一个帮普通用户看懂电脑文件的助手。用户发现C盘里有个占空间的{kind}，看不懂是什么，需要你用大白话解释。\n\n"
    "请用自然的中文写一段话（不要用【】标签），按这个顺序说清楚：\n"
    "1. 第一句：这是「XX软件」的什么数据（必须从路径推断出具体软件名）\n"
    "2. 第二句：用大白话说这个数据具体干什么用的，别说\"缓存\"\"配置\"这种笼统词，要说清对用户意味着什么\n"
    "3. 空一行，单独写判定：{{verdict}}\n"
    "4. 接着自然地说：删了会怎样（具体影响哪个功能），如果不用这个软件了怎么处理，删了之后能不能恢复\n\n"
    "语气要求：像一个懂电脑的朋友在跟你解释，简洁但不冷冰冰。总共不超过100字。"
)

def get_verdict(safety: str) -> str:
    return {"red": "千万别删", "yellow": "看看再删", "green": "放心删"}.get(safety, "看看再删")

def get_safety_desc(safety: str) -> str:
    return {
        "red": "系统核心文件，删除可能导致系统崩溃或无法启动",
        "yellow": "属于某个软件或服务，如果用户不再使用该软件可以考虑删除",
        "green": "缓存、临时文件或残留数据，删除不影响任何功能",
    }.get(safety, "无法确定安全性")

def get_parent_chain(path: str) -> str:
    parts = path.replace("/", "\\").split("\\")
    if len(parts) > 3:
        return "\\".join(parts[-4:-1])
    return "\\".join(parts[:-1])

def build_input(item: dict) -> str:
    kind = "文件夹" if item["is_dir"] else "文件"
    return (
        f"{kind}名：{item['name']}\n"
        f"完整路径：{item['path']}\n"
        f"所在目录：{get_parent_chain(item['path'])}\n"
        f"大小：{item['size_human']}\n"
        f"初步分类：{get_safety_desc(item['safety'])}"
    )

# --- Pattern-based ideal response generation ---
# Each pattern: (match_fn, response_fn, confidence)

def match_path(item, *keywords):
    p = item["path"].lower()
    return all(k in p for k in keywords)

PATTERNS = [
    # ===== Claude Desktop =====
    {
        "match": lambda i: match_path(i, "claude", "rootfs.vhdx") and not i["name"].endswith(".zst"),
        "confidence": "high",
        "response": lambda i: f"这是 Claude Desktop（Anthropic 的 AI 助手）的 Linux 虚拟磁盘，里面装着它运行代码分析等高级功能所需的完整系统环境。\n\n{get_verdict(i['safety'])}\n删了的话 Claude Desktop 的代码执行等功能会无法使用，需要重新下载。如果你已经不用 Claude Desktop 了，直接卸载软件即可。重装后会自动重建，但接近 10GB，下载需要时间。"
    },
    {
        "match": lambda i: match_path(i, "claude", "rootfs.vhdx.zst"),
        "confidence": "high",
        "response": lambda i: f"这是 Claude Desktop 虚拟磁盘的压缩备份包，用于快速恢复或更新运行环境，属于 Anthropic 的 AI 助手。\n\n{get_verdict(i['safety'])}\n这是安装包性质的文件，Claude Desktop 更新时会用到。如果你不用 Claude Desktop 了，卸载软件时会一起清掉。"
    },
    {
        "match": lambda i: match_path(i, "claude", "sessiondata.vhdx"),
        "confidence": "high",
        "response": lambda i: f"这是 Claude Desktop 的会话数据磁盘，保存了你和 AI 对话时产生的临时运行数据。\n\n{get_verdict(i['safety'])}\n删了的话正在进行的对话任务会丢失，但不影响软件本身启动。如果你不用 Claude Desktop 了，卸载即可。重启软件后会自动重建。"
    },
    {
        "match": lambda i: match_path(i, "claude", "initrd") and not i["name"].endswith(".zst"),
        "confidence": "high",
        "response": lambda i: f"这是 Claude Desktop 虚拟机的初始化镜像，启动 Linux 运行环境时需要加载它。\n\n{get_verdict(i['safety'])}\n删了的话 Claude Desktop 的高级功能（代码执行等）无法启动。不用 Claude Desktop 的话直接卸载软件。重装会自动恢复。"
    },
    {
        "match": lambda i: match_path(i, "claude", "initrd.zst"),
        "confidence": "high",
        "response": lambda i: f"这是 Claude Desktop 启动镜像的压缩版本，用于安装或更新时快速部署运行环境。\n\n{get_verdict(i['safety'])}\n属于安装资源文件，删了可能导致下次更新失败。不用 Claude Desktop 的话卸载即可。"
    },
    {
        "match": lambda i: match_path(i, "claude", "claude-code") and i["name"] == "claude.exe",
        "confidence": "high",
        "response": lambda i: f"这是 Claude Code 的可执行程序，Anthropic 的 AI 编程助手命令行工具。\n\n{get_verdict(i['safety'])}\n删了的话 Claude Code 命令行工具无法使用。如果你不用 Claude Code 了，可以通过 npm 卸载。版本更新后旧版本可以安全删除。"
    },
    {
        "match": lambda i: match_path(i, "claude", "claude-code-vm"),
        "confidence": "high",
        "response": lambda i: f"这是 Claude Code 的 Linux 版本可执行文件，在虚拟机环境中运行 AI 编程功能时使用。\n\n{get_verdict(i['safety'])}\n删了会影响 Claude Code 的虚拟机模式。不用的话卸载 Claude Code 即可。"
    },
    {
        "match": lambda i: match_path(i, ".local", "claude") and ("versions" in i["path"].lower() or i["name"] == "claude.exe"),
        "confidence": "high",
        "response": lambda i: f"这是 Claude Code CLI 工具的本地安装文件，Anthropic 的 AI 编程命令行助手。\n\n{get_verdict(i['safety'])}\n删了的话终端里的 claude 命令会失效。如果你还在用 Claude Code，不要删。旧版本文件（非当前版本）可以清理。"
    },
    {
        "match": lambda i: match_path(i, "claude") and i["name"].endswith(".log"),
        "confidence": "high",
        "response": lambda i: f"这是 Claude Desktop 的运行日志，记录了软件运行过程中的调试信息。\n\n{get_verdict(i['safety'])}\n纯日志文件，删了不影响任何功能，软件下次运行会自动重新生成。可以放心清理。"
    },
    {
        "match": lambda i: match_path(i, ".claude", "projects") and i["name"].endswith(".jsonl"),
        "confidence": "high",
        "response": lambda i: f"这是 Claude Code 的项目对话记录，保存了你在某个项目中和 AI 的交互历史。\n\n{get_verdict(i['safety'])}\n删了的话对应项目的对话历史会丢失，但不影响 Claude Code 本身使用。如果你不需要回顾历史对话，可以清理。"
    },
    # ===== Trae =====
    {
        "match": lambda i: match_path(i, "trae", "ai-agent", "snapshot"),
        "confidence": "high",
        "response": lambda i: f"这是 Trae（字节跳动的 AI 编程助手）的代码回滚快照，每次 AI 帮你改代码时都会用 Git 保存一份完整的项目备份，方便你撤销 AI 的修改。体积大通常是因为快照了压缩包等大文件。\n\n{get_verdict(i['safety'])}\n删了的话你会失去对过去 AI 编辑操作的撤销能力，但不影响当前项目代码。如果你已经不用 Trae 了，直接卸载即可。"
    },
    {
        "match": lambda i: i["name"] == "Trae.exe",
        "confidence": "high",
        "response": lambda i: f"这是 Trae 的主程序文件，字节跳动开发的 AI 编程助手（类似 VS Code + AI）。\n\n{get_verdict(i['safety'])}\n删了的话 Trae 就无法启动了。如果你不用 Trae，建议从系统设置里正常卸载，而不是直接删文件。"
    },
    {
        "match": lambda i: match_path(i, "trae", "traesetup"),
        "confidence": "high",
        "response": lambda i: f"这是 Trae 的安装包缓存，已经安装完的旧安装文件留在了临时目录里。\n\n{get_verdict(i['safety'])}\n纯安装残留，删了不影响已安装的 Trae。可以放心清理释放空间。"
    },
    {
        "match": lambda i: match_path(i, ".trae", "extensions", "claude-code"),
        "confidence": "high",
        "response": lambda i: f"这是 Trae 编辑器里安装的 Claude Code 插件的可执行文件，让你在 Trae 里使用 Anthropic 的 AI 编程功能。\n\n{get_verdict(i['safety'])}\n删了的话 Trae 里的 Claude Code 插件会失效。如果你在 Trae 里不用 Claude Code 插件，可以在 Trae 的扩展管理里卸载它。"
    },
    {
        "match": lambda i: match_path(i, ".trae", "extensions", "chatgpt") or match_path(i, ".trae", "extensions", "codex"),
        "confidence": "high",
        "response": lambda i: f"这是 Trae 编辑器里安装的 OpenAI Codex 插件，提供 AI 代码补全和对话功能。\n\n{get_verdict(i['safety'])}\n删了的话 Trae 里的 Codex/ChatGPT 插件会失效。如果你不用这个插件，可以在 Trae 扩展管理里卸载。"
    },
    # ===== VSCode =====
    {
        "match": lambda i: match_path(i, ".vscode", "extensions", "claude-code"),
        "confidence": "high",
        "response": lambda i: f"这是 VS Code 里安装的 Claude Code 插件的可执行文件，让你在 VS Code 里使用 Anthropic 的 AI 编程功能。\n\n{get_verdict(i['safety'])}\n删了的话 VS Code 里的 Claude Code 插件会失效。如果你不用这个插件，在 VS Code 扩展管理里卸载即可。"
    },
    {
        "match": lambda i: match_path(i, ".vscode", "extensions", "chatgpt") or match_path(i, ".vscode", "extensions", "codex"),
        "confidence": "high",
        "response": lambda i: f"这是 VS Code 里安装的 OpenAI Codex 插件，提供 AI 代码补全和对话功能。\n\n{get_verdict(i['safety'])}\n删了的话 VS Code 里的 Codex/ChatGPT 插件会失效。如果你不用这个插件，在 VS Code 扩展管理里卸载即可。"
    },
    {
        "match": lambda i: match_path(i, "roaming", "code", "cachedextensionvsixs"),
        "confidence": "high",
        "response": lambda i: f"这是 VS Code 缓存的扩展安装包，已安装完成后留下的副本，方便离线重装。\n\n{get_verdict(i['safety'])}\n纯缓存文件，删了不影响已安装的插件，只是下次重装插件时需要重新下载。可以放心清理。"
    },
    # ===== WSL =====
    {
        "match": lambda i: match_path(i, "wsl") and "ext4.vhdx" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 WSL（Windows 子系统 Linux）的虚拟磁盘，里面存着你的 Linux 系统和所有 Linux 下的文件。\n\n{get_verdict(i['safety'])}\n删了的话你的整个 Linux 环境会丢失，包括里面安装的所有软件和数据。如果你不用 Linux 开发，可以在设置里卸载 WSL。无法恢复，数据会永久丢失。"
    },
    {
        "match": lambda i: match_path(i, "program files", "wsl") and i["name"].endswith(".vhd"),
        "confidence": "high",
        "response": lambda i: f"这是 WSL（Windows 子系统 Linux）的系统镜像文件，包含 Linux 内核和基础系统组件。\n\n{get_verdict(i['safety'])}\n属于 WSL 的核心文件，删了的话 WSL 无法启动。如果你不用 WSL，通过 Windows 功能设置卸载它。"
    },
    # ===== Ollama =====
    {
        "match": lambda i: match_path(i, ".ollama", "models", "blobs"),
        "confidence": "high",
        "response": lambda i: f"这是 Ollama（本地 AI 大模型运行工具）下载的模型权重文件，是你本地跑 AI 对话所需的核心数据。\n\n{get_verdict(i['safety'])}\n删了的话对应的 AI 模型会丢失，需要重新用 ollama pull 下载。如果你不用 Ollama 了，可以用 ollama rm 清理模型，或直接卸载。"
    },
    {
        "match": lambda i: match_path(i, "ollama", "ggml-cuda"),
        "confidence": "high",
        "response": lambda i: f"这是 Ollama 的 CUDA GPU 加速库，让 Ollama 能利用你的 NVIDIA 显卡来加速 AI 推理。\n\n{get_verdict(i['safety'])}\n删了的话 Ollama 会退回到 CPU 运行，速度会慢很多。属于 Ollama 安装的一部分，不建议单独删。"
    },
    {
        "match": lambda i: match_path(i, "ollama", "ggml-hip"),
        "confidence": "high",
        "response": lambda i: f"这是 Ollama 的 AMD ROCm GPU 加速库，支持 AMD 显卡加速 AI 推理。\n\n{get_verdict(i['safety'])}\n你用的是 NVIDIA 显卡，这个 AMD 的加速库实际用不到，但它是 Ollama 安装自带的，删了可能影响 Ollama 更新。"
    },
    {
        "match": lambda i: match_path(i, "ollama") and "cublaslt" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Ollama 自带的 NVIDIA cuBLAS 数学运算库，AI 模型推理时做矩阵计算用的。\n\n{get_verdict(i['safety'])}\n属于 Ollama GPU 加速的核心依赖，删了会导致 Ollama 无法用 GPU 运行。不建议单独删，卸载 Ollama 时会一起清除。"
    },
    {
        "match": lambda i: match_path(i, "ollama", "rocblas"),
        "confidence": "high",
        "response": lambda i: f"这是 Ollama 自带的 AMD ROCm 数学库，用于 AMD 显卡加速。你的电脑是 NVIDIA 显卡，这个库用不到。\n\n{get_verdict(i['safety'])}\n虽然用不到，但它是 Ollama 安装包自带的组件，单独删可能影响 Ollama 的完整性。建议保留。"
    },
    {
        "match": lambda i: match_path(i, "ollama", "mlx"),
        "confidence": "high",
        "response": lambda i: f"这是 Ollama 的 MLX 加速库（Apple Silicon 用的），在 Windows 上实际用不到。\n\n{get_verdict(i['safety'])}\n这是 Ollama 安装包自带的跨平台组件，在你的电脑上不会被调用，但单独删可能影响 Ollama 更新。"
    },
    # ===== HuggingFace =====
    {
        "match": lambda i: match_path(i, ".cache", "huggingface", "hub") and ("model.safetensors" in i["name"] or "pytorch_model.bin" in i["name"]),
        "confidence": "high",
        "response": lambda i: _huggingface_response(i)
    },
    # ===== NVIDIA DXCache =====
    {
        "match": lambda i: match_path(i, "nvidia", "dxcache"),
        "confidence": "high",
        "response": lambda i: f"这是 NVIDIA 显卡的 DirectX 着色器缓存，显卡驱动编译游戏/应用的 GPU 程序后缓存在这里，下次启动更快。\n\n{get_verdict(i['safety'])}\n删了不影响任何功能，只是下次启动游戏或 GPU 应用时会稍微慢一点（重新编译着色器）。会自动重建，可以放心清理。"
    },
    # ===== NVIDIA CUDA Toolkit =====
    {
        "match": lambda i: match_path(i, "nvidia gpu computing toolkit", "cuda"),
        "confidence": "high",
        "response": lambda i: f"这是 NVIDIA CUDA 开发工具包的组件（{i['name']}），做 GPU 编程和深度学习开发时需要的底层库。\n\n{get_verdict(i['safety'])}\n删了的话依赖 CUDA 的开发环境（PyTorch、TensorFlow 等）会无法使用 GPU 加速。如果你不做 AI/GPU 开发，可以从控制面板卸载 CUDA Toolkit。"
    },
    # ===== Lenovo ModelMgr / AIAgent =====
    {
        "match": lambda i: match_path(i, "lenovo", "modelmgr", "plugins", "image", "models") and i["name"].endswith((".ckpt", ".pth", ".pt.flat")),
        "confidence": "high",
        "response": lambda i: f"这是联想电脑自带的「AI 天禧」图像功能的模型文件（{i['name']}），用于 AI 画图、图像编辑等联想预装功能。\n\n{get_verdict(i['safety'])}\n删了的话联想 AI 天禧的图像生成/编辑功能会失效。如果你不用联想自带的 AI 画图功能，可以在联想电脑管家里关闭或卸载「AI 天禧」。"
    },
    {
        "match": lambda i: match_path(i, "lenovo", "modelmgr") and ("nvinfer" in i["name"].lower() or "cublas" in i["name"].lower() or "cudnn" in i["name"].lower() or "cusparse" in i["name"].lower() or "cufft" in i["name"].lower() or "cusolver" in i["name"].lower() or "torch" in i["name"].lower() or "dnnl" in i["name"].lower()),
        "confidence": "high",
        "response": lambda i: f"这是联想「AI 天禧」图像功能依赖的 GPU 运算库（{i['name']}），AI 模型推理时的底层计算组件。\n\n{get_verdict(i['safety'])}\n属于联想 AI 天禧的核心依赖，单独删会导致 AI 功能崩溃。如果不用联想 AI 功能，建议整体卸载「AI 天禧」而不是删单个文件。"
    },
    {
        "match": lambda i: match_path(i, "lenovo", "modelmgr") and "removebackground" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是联想「AI 天禧」的抠图模型，用于一键去除图片背景的 AI 功能。\n\n{get_verdict(i['safety'])}\n删了的话联想自带的 AI 抠图功能会失效。如果你不用联想的 AI 图像功能，可以整体卸载「AI 天禧」。"
    },
    {
        "match": lambda i: match_path(i, "lenovo", "modelmgr") and "segment" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是联想「AI 天禧」的图像分割模型，用于 AI 识别和分离图片中的不同物体。\n\n{get_verdict(i['safety'])}\n删了的话联想自带的 AI 图像分割功能会失效。如果你不用联想 AI 图像功能，可以整体卸载「AI 天禧」。"
    },
    {
        "match": lambda i: match_path(i, "lenovo", "aiagent") and i["name"].endswith((".gguf", ".onnx.data")),
        "confidence": "high",
        "response": lambda i: f"这是联想 AI Agent（小天）的本地大语言模型文件，让联想的 AI 助手可以在不联网的情况下回答问题。\n\n{get_verdict(i['safety'])}\n删了的话联想小天的离线 AI 对话功能会失效。如果你不用联想的 AI 助手，可以在联想电脑管家里关闭或卸载。"
    },
    {
        "match": lambda i: match_path(i, "lenovo", "aiagent") and ("cublas" in i["name"].lower() or "http-server" in i["name"].lower() or "speculator" in i["name"].lower() or "rocblas" in i["name"].lower()),
        "confidence": "high",
        "response": lambda i: f"这是联想 AI Agent（小天）的 GPU 加速引擎组件（{i['name']}），让 AI 助手能利用显卡加速回答。\n\n{get_verdict(i['safety'])}\n属于联想 AI 助手的核心运行依赖，单独删会导致功能异常。如果不用联想 AI 助手，建议整体卸载。"
    },
    {
        "match": lambda i: match_path(i, "lenovo", "aiagent") and "libcef" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是联想 AI Agent（小天）的内嵌浏览器引擎（Chromium），用于显示 AI 助手的界面。\n\n{get_verdict(i['safety'])}\n属于联想 AI 助手的界面组件，单独删会导致界面无法显示。如果不用联想 AI 助手，建议整体卸载。"
    },
    # ===== Lenovo LegionZone =====
    {
        "match": lambda i: match_path(i, "lenovo", "legionzone") and "lzinstall" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是联想拯救者空间（Legion Zone）的安装程序缓存，用于游戏性能调节和硬件监控的联想预装软件。\n\n{get_verdict(i['safety'])}\n如果 Legion Zone 已经装好了，这个安装包缓存可以删。但建议通过联想电脑管家来管理，而不是手动删文件。"
    },
    {
        "match": lambda i: match_path(i, "lenovo", "legionzone") and "libcef" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是联想拯救者空间（Legion Zone）的内嵌浏览器引擎，用于显示软件界面。\n\n{get_verdict(i['safety'])}\n属于 Legion Zone 的核心界面组件，删了软件界面会无法显示。如果不用 Legion Zone，建议整体卸载。"
    },
    # ===== Lenovo PCManager =====
    {
        "match": lambda i: match_path(i, "lenovo", "pcmanager") and "libcef" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是联想电脑管家的内嵌浏览器引擎（Chromium），用于显示管家的界面。\n\n{get_verdict(i['safety'])}\n属于联想电脑管家的核心组件，删了管家界面会打不开。不建议删，联想电脑管家负责驱动更新等重要功能。"
    },
    # ===== Lenovo SLBrowser =====
    {
        "match": lambda i: match_path(i, "lenovo", "slbrowser"),
        "confidence": "high",
        "response": lambda i: f"这是联想预装的安全浏览器（SLBrowser）的组件，一个基于 Chromium 的联想定制浏览器。\n\n{get_verdict(i['safety'])}\n如果你不用联想自带的浏览器（大多数人用 Chrome 或 Edge），可以在控制面板里卸载联想浏览器。"
    },
    # ===== Lenovo LeAppStore / LeFile =====
    {
        "match": lambda i: match_path(i, "lenovo", "leappstore") and "libcef" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是联想应用商店的内嵌浏览器引擎，用于显示应用商店界面。\n\n{get_verdict(i['safety'])}\n属于联想应用商店的核心组件。如果你不用联想应用商店，可以在控制面板卸载。"
    },
    {
        "match": lambda i: match_path(i, "lenovo", "lefile") and "libcef" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是联想文件管理器（乐文件）的内嵌浏览器引擎，用于显示界面。\n\n{get_verdict(i['safety'])}\n属于联想文件管理器的核心组件。如果你不用联想自带的文件管理器，可以在控制面板卸载。"
    },
    # ===== Lenovo UDC =====
    {
        "match": lambda i: match_path(i, "lenovo", "udc") and i["name"].endswith(".sqlite3"),
        "confidence": "high",
        "response": lambda i: f"这是联想 UDC（Universal Device Client）的遥测数据库，定期收集你的设备使用情况和健康信息发送给联想服务器。\n\n{get_verdict(i['safety'])}\n删了不影响电脑正常使用，文件会自动重建。如果你不希望联想收集设备数据，可以在服务管理中禁用 UDClientService。"
    },
    # ===== pip cache =====
    {
        "match": lambda i: match_path(i, "pip", "cache"),
        "confidence": "high",
        "response": lambda i: f"这是 Python pip 的下载缓存，之前用 pip install 安装 Python 包时下载的安装文件副本。\n\n{get_verdict(i['safety'])}\n纯缓存，删了不影响已安装的 Python 包，只是下次重装同一个包时需要重新下载。可以用 pip cache purge 命令一键清理。"
    },
    # ===== npm cache =====
    {
        "match": lambda i: match_path(i, "npm-cache"),
        "confidence": "high",
        "response": lambda i: f"这是 npm（Node.js 包管理器）的下载缓存，之前安装前端/Node.js 依赖时留下的安装包副本。\n\n{get_verdict(i['safety'])}\n纯缓存，删了不影响已安装的项目依赖，只是下次 npm install 时需要重新下载。可以用 npm cache clean --force 清理。"
    },
    # ===== conda / miniforge / micromamba — PyTorch CUDA libs =====
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "torch_cuda" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_torch_response(i, "torch_cuda.dll", "PyTorch 的 CUDA GPU 加速核心库，做深度学习训练和推理时用显卡加速的关键组件")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "torch_cpu" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_torch_response(i, "torch_cpu.dll", "PyTorch 的 CPU 运算核心库，所有深度学习计算的基础组件")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "dnnl" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_torch_response(i, "dnnl.lib", "Intel 深度神经网络数学库，PyTorch 在 CPU 上做推理时的加速组件")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "cublaslt" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_torch_response(i, i["name"], "NVIDIA cuBLAS 矩阵运算库，深度学习训练时做 GPU 矩阵乘法的底层加速组件")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "cudnn_engines_precompiled" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_torch_response(i, i["name"], "NVIDIA cuDNN 预编译引擎，深度学习中卷积运算的 GPU 加速组件")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "cudnn_adv" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_torch_response(i, i["name"], "NVIDIA cuDNN 高级运算库，深度学习中注意力机制等复杂操作的 GPU 加速组件")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "cusparse" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_torch_response(i, i["name"], "NVIDIA 稀疏矩阵运算库，处理稀疏数据时的 GPU 加速组件")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "cufft" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_torch_response(i, i["name"], "NVIDIA 快速傅里叶变换库，信号处理和某些神经网络层的 GPU 加速组件")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "cusolver" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_torch_response(i, i["name"], "NVIDIA 线性代数求解库，矩阵分解等数值计算的 GPU 加速组件")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "nvrtc_static" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_torch_response(i, i["name"], "NVIDIA 运行时编译器的静态库，CUDA 程序运行时编译 GPU 代码用的")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "nvjitlink" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_torch_response(i, i["name"], "NVIDIA JIT 链接器的静态库，CUDA 程序运行时动态链接 GPU 代码用的")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "_pywrap_tensorflow_internal" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_env_response(i, "TensorFlow 的核心 C++ 运算引擎", "TensorFlow（Google 的深度学习框架）")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "_catboost" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_env_response(i, "CatBoost 机器学习库的 C++ 核心引擎，做梯度提升树模型训练的", "CatBoost（Yandex 的机器学习框架）")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "xgboost" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_env_response(i, "XGBoost 机器学习库的核心运算引擎，做梯度提升树模型的", "XGBoost")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "llvmlite" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_env_response(i, "LLVM 编译器的 Python 绑定，Numba JIT 编译器依赖它来加速 Python 数值计算", "Numba/LLVM")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "pandoc" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_env_response(i, "Pandoc 文档格式转换工具，可以把 Jupyter Notebook 导出为 PDF、Word 等格式", "Pandoc")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "libclang" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_env_response(i, "LLVM/Clang 编译器的共享库，某些 Python 包编译 C/C++ 扩展时需要", "libclang")
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and i["name"].endswith((".tar.bz2", ".conda")),
        "confidence": "high",
        "response": lambda i: f"这是 conda 包管理器下载的安装包缓存（{i['name']}），之前安装 Python 包时下载的压缩包副本。\n\n{get_verdict(i['safety'])}\n纯缓存，删了不影响已安装的环境。可以用 conda clean --all 一键清理所有缓存包，释放大量空间。"
    },
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower() or "mamba" in i["path"].lower()) and "pkgs" in i["path"].lower() and "cache" in i["path"].lower() and i["name"].endswith(".json"),
        "confidence": "high",
        "response": lambda i: f"这是 conda/mamba 包管理器的软件源索引缓存，记录了可用的 Python 包列表信息。\n\n{get_verdict(i['safety'])}\n纯缓存，删了不影响已安装的环境，下次搜索包时会自动重新下载。可以用 conda clean --all 清理。"
    },
    # ===== GPT4All =====
    {
        "match": lambda i: match_path(i, "gpt4all") and "llamamodel" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 GPT4All（本地 AI 对话工具）的 LLaMA 推理引擎，支持 CUDA GPU 加速的核心运行库。\n\n{get_verdict(i['safety'])}\n删了的话 GPT4All 的 GPU 加速对话功能会失效。如果你不用 GPT4All 了，可以直接卸载整个 GPT4All 文件夹。"
    },
    {
        "match": lambda i: match_path(i, "gpt4all") and "cublaslt" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 GPT4All 自带的 NVIDIA cuBLAS 数学库，GPU 加速 AI 对话时做矩阵运算用的。\n\n{get_verdict(i['safety'])}\n属于 GPT4All GPU 加速的核心依赖。不建议单独删，卸载 GPT4All 时会一起清除。"
    },
    {
        "match": lambda i: match_path(i, "gpt4all") and "nomic-embed" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 GPT4All 自带的 Nomic 文本嵌入模型，用于文档搜索和语义理解功能（LocalDocs）。\n\n{get_verdict(i['safety'])}\n删了的话 GPT4All 的本地文档搜索功能会失效。如果你不用 GPT4All，可以直接卸载整个文件夹。"
    },
    # ===== Codex (OpenAI) =====
    {
        "match": lambda i: match_path(i, ".codex") and i["name"].endswith(".sqlite"),
        "confidence": "high",
        "response": lambda i: f"这是 OpenAI Codex CLI（AI 编程命令行工具）的核心数据库，保存了所有对话历史和会话状态，支持用 codex resume 恢复之前的编程会话。\n\n{get_verdict(i['safety'])}\n删了的话所有 Codex 对话历史会丢失，无法恢复之前的会话。工具本身还能用，但会从零开始。如果你不用 Codex CLI 了，可以整个 .codex 文件夹删掉。"
    },
    {
        "match": lambda i: match_path(i, ".codex") and "codex.exe" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 OpenAI Codex CLI 的可执行程序，OpenAI 的 AI 编程命令行工具。\n\n{get_verdict(i['safety'])}\n删了的话 codex 命令会失效。如果你不用 OpenAI Codex CLI，可以直接删除整个 .codex 文件夹。"
    },
    # ===== Edge =====
    {
        "match": lambda i: "msedge.dll" in i["name"].lower() and ("edgecore" in i["path"].lower() or "edge\\application" in i["path"].lower() or "edgewebview" in i["path"].lower()),
        "confidence": "high",
        "response": lambda i: f"这是 Microsoft Edge 浏览器的核心引擎文件，Edge 运行网页时的主要组件。\n\n{get_verdict(i['safety'])}\n属于 Edge 浏览器的核心文件，删了 Edge 会无法使用。多个版本并存是 Windows 自动更新导致的，旧版本会被系统自动清理。"
    },
    {
        "match": lambda i: "msedge.dll" in i["name"].lower() and ("winsxs" in i["path"].lower() or "system32" in i["path"].lower()),
        "confidence": "high",
        "response": lambda i: f"这是 Windows 系统内置的 Edge WebView 组件，很多应用（包括系统设置界面）依赖它来显示网页内容。\n\n{get_verdict(i['safety'])}\n属于系统核心组件，删了可能导致多个应用界面显示异常。由 Windows Update 管理，不要手动删除。"
    },
    {
        "match": lambda i: match_path(i, "edge", "user data", "provenancedata"),
        "confidence": "high",
        "response": lambda i: f"这是 Microsoft Edge 浏览器本地部署的 AI 视觉模型（ViT-B/32 量化版），用于 Edge Copilot 的离线图片理解和视觉搜索功能。\n\n{get_verdict(i['safety'])}\n删了的话 Edge 的 AI 图片分析功能会暂时失效，但 Edge 会自动重新下载。不影响正常网页浏览。"
    },
    {
        "match": lambda i: match_path(i, "edge", "component_crx_cache"),
        "confidence": "high",
        "response": lambda i: f"这是 Microsoft Edge 浏览器的组件更新缓存，存储了浏览器自动更新下载的扩展组件。\n\n{get_verdict(i['safety'])}\n缓存文件，删了不影响浏览器使用，下次更新时会重新下载。可以清理释放空间。"
    },
    # ===== Google Updater =====
    {
        "match": lambda i: match_path(i, "google", "googleupdater", "crx_cache"),
        "confidence": "high",
        "response": lambda i: f"这是 Google 软件更新服务的缓存文件，Google Chrome 或其他 Google 产品自动更新时下载的安装包。\n\n{get_verdict(i['safety'])}\n纯更新缓存，删了不影响已安装的 Google 软件，下次更新时会重新下载。"
    },
    # ===== Discord =====
    {
        "match": lambda i: "discord" in i["path"].lower() and i["name"] == "Discord.exe",
        "confidence": "high",
        "response": lambda i: f"这是 Discord（游戏语音聊天社区）的主程序文件。多个版本并存是因为 Discord 自动更新时会保留旧版本。\n\n{get_verdict(i['safety'])}\n当前正在使用的版本不能删，但旧版本（非最新的 app-* 文件夹）理论上可以清理。建议让 Discord 自己管理更新。"
    },
    {
        "match": lambda i: "discord" in i["path"].lower() and i["name"].endswith(".nupkg"),
        "confidence": "high",
        "response": lambda i: f"这是 Discord 的更新安装包缓存，自动更新时下载的旧版本安装文件。\n\n{get_verdict(i['safety'])}\n纯更新缓存，删了不影响 Discord 使用。会在下次更新时自动清理或重新下载。"
    },
    # ===== Unity =====
    {
        "match": lambda i: match_path(i, "unity") and i["name"].endswith(".tgz"),
        "confidence": "high",
        "response": lambda i: f"这是 Unity 游戏引擎的包资源文件（{i['name']}），Unity 编辑器运行时需要加载的内置组件。\n\n{get_verdict(i['safety'])}\n属于 Unity 编辑器的核心资源，删了会导致 Unity 项目无法正常编译或运行。如果你不做游戏开发了，可以通过 Unity Hub 卸载对应的编辑器版本。"
    },
    {
        "match": lambda i: match_path(i, "unity") and ("unity editor resources" in i["name"].lower() or "unity_builtin_extra" in i["name"].lower()),
        "confidence": "high",
        "response": lambda i: f"这是 Unity 游戏引擎编辑器的内置资源文件，包含默认材质、着色器等基础素材。\n\n{get_verdict(i['safety'])}\n属于 Unity 编辑器的核心文件，删了编辑器会崩溃。如果不做游戏开发，通过 Unity Hub 卸载编辑器。"
    },
    {
        "match": lambda i: match_path(i, "unity") and "burst" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Unity Burst 编译器的运行库，用于将 C# 代码编译为高性能原生代码，提升游戏运行效率。\n\n{get_verdict(i['safety'])}\n属于 Unity 编辑器的核心编译组件。如果不做游戏开发，通过 Unity Hub 卸载编辑器版本。"
    },
    {
        "match": lambda i: match_path(i, "unityhub", "templates"),
        "confidence": "high",
        "response": lambda i: f"这是 Unity Hub 下载的项目模板，创建新 Unity 项目时可以选择的起始模板。\n\n{get_verdict(i['safety'])}\n删了的话在 Unity Hub 里创建新项目时这个模板选项会消失，但可以重新下载。不影响已有项目。"
    },
    {
        "match": lambda i: match_path(i, "downloads") and "unityhub" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Unity Hub 的安装程序，已经安装完成后留在下载文件夹里的安装包。\n\n{get_verdict(i['safety'])}\n安装已完成，这个安装包可以放心删除。需要重装时去 Unity 官网重新下载即可。"
    },
    {
        "match": lambda i: "setup guide in-editor tutorial" in i["path"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Unity 入门教程项目的内置资源文件（Burst 编译器库），跟着教程创建的示例项目。\n\n{get_verdict(i['safety'])}\n如果你已经学完教程不需要这个项目了，可以直接删除整个「Setup Guide In-Editor Tutorial」文件夹。"
    },
    # ===== WeChat =====
    {
        "match": lambda i: match_path(i, "tencent", "weixin") and "radiumwmpf" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是微信电脑版的小程序运行引擎，负责在微信里打开和运行小程序。\n\n{get_verdict(i['safety'])}\n删了的话微信里的小程序会无法打开，但聊天、朋友圈等基本功能不受影响。微信更新时会自动恢复。"
    },
    {
        "match": lambda i: match_path(i, "tencent", "weixin") and "weixin.dll" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是微信电脑版的核心运行库，微信所有功能都依赖这个文件。\n\n{get_verdict(i['safety'])}\n删了的话微信电脑版会完全无法使用。不要手动删除，如果要清理空间建议清理微信的聊天文件缓存。"
    },
    {
        "match": lambda i: match_path(i, "tencent", "xwechat") and "flue.dll" in i["name"].lower(),
        "confidence": "medium",
        "confidence": "high",
        "response": lambda i: f"这是微信电脑版的小程序运行框架（RadiumWMPF）的渲染引擎，WeChatAppEx.exe 进程加载它来运行微信里的小程序和内嵌网页。\n\n{get_verdict(i['safety'])}\n删了的话微信小程序会显示白屏。不用担心，删除 XPlugin 文件夹后重启微信会自动重新下载。"
    },
    # ===== WeMeet (Tencent Meeting) =====
    {
        "match": lambda i: match_path(i, "tencent", "wemeet"),
        "confidence": "high",
        "response": lambda i: f"这是腾讯会议的核心网页渲染引擎（{i['name']}），负责显示会议界面和共享屏幕内容。\n\n{get_verdict(i['safety'])}\n删了的话腾讯会议会无法正常运行。如果你不用腾讯会议了，建议通过控制面板正常卸载。"
    },
    # ===== Zoom =====
    {
        "match": lambda i: match_path(i, "zoom", "asr"),
        "confidence": "high",
        "response": lambda i: f"这是 Zoom 会议的本地语音识别模型，用于会议实时字幕和转录功能。\n\n{get_verdict(i['safety'])}\n删了的话 Zoom 的实时字幕/转录功能会暂时失效，但基本的视频会议不受影响。Zoom 会在下次启动时自动重新下载。"
    },
    # ===== Clipchamp =====
    {
        "match": lambda i: "clipchamp" in i["path"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Clipchamp（Windows 自带的视频编辑器）的项目缓存数据，保存了你正在编辑的视频素材。\n\n{get_verdict(i['safety'])}\n删了的话 Clipchamp 里未导出的视频项目会丢失。如果你已经导出了成片不需要再编辑，可以清理。通过 Clipchamp 应用内清理更安全。"
    },
    # ===== Rustup =====
    {
        "match": lambda i: match_path(i, ".rustup"),
        "confidence": "high",
        "response": lambda i: f"这是 Rust 编程语言工具链的核心组件（{i['name']}），编译 Rust 程序时需要的编译器驱动。\n\n{get_verdict(i['safety'])}\n删了的话 Rust 编译器会无法工作。如果你不做 Rust 开发了，可以用 rustup self uninstall 完整卸载 Rust 工具链。"
    },
    # ===== datalab =====
    {
        "match": lambda i: match_path(i, "datalab") and "model.safetensors" in i["name"],
        "confidence": "high",
        "response": lambda i: _datalab_response(i)
    },
    # ===== qlib =====
    {
        "match": lambda i: match_path(i, ".qlib"),
        "confidence": "high",
        "response": lambda i: f"这是 Qlib（微软开源的量化投资框架）下载的 A 股历史行情数据，做量化交易研究和回测用的。\n\n{get_verdict(i['safety'])}\n删了的话需要重新下载股票数据，下载比较耗时。如果你不做量化投资研究了，可以删除整个 .qlib 文件夹。"
    },
    # ===== astroML =====
    {
        "match": lambda i: match_path(i, "astroml_data"),
        "confidence": "high",
        "response": lambda i: f"这是 astroML（天文学机器学习库）下载的 SDSS 天文观测数据集，用于天文学数据分析和研究。\n\n{get_verdict(i['safety'])}\n删了的话需要重新下载。如果你不做天文学相关的数据分析了，可以删除整个 astroML_data 文件夹。"
    },
    # ===== tensorflow_datasets =====
    {
        "match": lambda i: match_path(i, "tensorflow_datasets"),
        "confidence": "high",
        "response": lambda i: f"这是 TensorFlow Datasets 下载的训练数据集（花卉图片分类数据），机器学习实验或教学用的数据。\n\n{get_verdict(i['safety'])}\n删了的话运行相关的机器学习代码时需要重新下载数据集。如果你不再做这个实验了，可以删除整个 tensorflow_datasets 文件夹。"
    },
    # ===== Visual Studio =====
    {
        "match": lambda i: "visualstudio" in i["path"].lower().replace(" ", "") and "intellicode" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Visual Studio 的 IntelliCode 智能代码补全模型，提供 AI 驱动的代码建议功能。\n\n{get_verdict(i['safety'])}\n删了的话 Visual Studio 的 AI 代码补全建议会暂时失效，但会在下次启动 VS 时自动重新下载。"
    },
    {
        "match": lambda i: "visualstudio" in i["path"].lower().replace(".", "").replace(" ", "") and "copilot" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Visual Studio 的 GitHub Copilot 插件安装包，AI 代码助手的扩展文件。\n\n{get_verdict(i['safety'])}\n这是临时目录里的安装缓存，删了不影响已安装的 Copilot 插件。可以放心清理。"
    },
    # ===== NVIDIA app =====
    {
        "match": lambda i: match_path(i, "nvidia corporation", "nvidia app") and "libcef" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 NVIDIA App（显卡管理工具）的内嵌浏览器引擎，用于显示驱动更新和 GeForce 功能的界面。\n\n{get_verdict(i['safety'])}\n属于 NVIDIA App 的核心界面组件。如果你不用 NVIDIA App（之前叫 GeForce Experience），可以卸载它，但建议保留以方便更新显卡驱动。"
    },
    {
        "match": lambda i: match_path(i, "nvidia corporation", "nsight"),
        "confidence": "high",
        "response": lambda i: f"这是 NVIDIA Nsight（GPU 调试和分析工具）的安装程序，面向 CUDA 开发者的性能调优工具。\n\n{get_verdict(i['safety'])}\n如果你不做 CUDA/GPU 性能调优，可以从控制面板卸载 Nsight 工具。这个 MSI 是安装缓存，但不建议单独删文件。"
    },
    # ===== NVIDIA driver files =====
    {
        "match": lambda i: match_path(i, "driverstore") and ("nvdxdlkernels" in i["name"].lower() or "libnvdxdlkernels" in i["name"].lower()),
        "confidence": "high",
        "response": lambda i: f"这是 NVIDIA 显卡驱动的 DLSS/深度学习超采样内核文件，游戏中 AI 画质增强功能的核心组件。\n\n{get_verdict(i['safety'])}\n属于显卡驱动的核心文件，删了可能导致游戏中 DLSS 功能失效甚至驱动崩溃。由 Windows 驱动管理器管理，不要手动删除。"
    },
    {
        "match": lambda i: match_path(i, "system32", "lxss") and "libnvdxdlkernels" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 NVIDIA 为 WSL（Linux 子系统）提供的 GPU 加速内核文件，让 WSL 里的 Linux 程序也能使用显卡。\n\n{get_verdict(i['safety'])}\n属于系统级 GPU 驱动组件，删了会导致 WSL 里无法使用 GPU。由 Windows 和 NVIDIA 驱动管理，不要手动删除。"
    },
    # ===== Intel driver =====
    {
        "match": lambda i: match_path(i, "driverstore") and "libopencl-clang" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Intel 核显驱动的 OpenCL 编译器组件，让程序能利用 Intel 核显进行并行计算。\n\n{get_verdict(i['safety'])}\n属于 Intel 显卡驱动的核心文件，删了可能导致核显相关功能异常。由 Windows 驱动管理，不要手动删除。"
    },
    # ===== Windows Installer (.msi) =====
    {
        "match": lambda i: match_path(i, "windows", "installer") and i["name"].endswith(".msi"),
        "confidence": "high",
        "response": lambda i: f"这是 Windows Installer 缓存的软件安装包（{i['name']}），用于软件修复、卸载和更新时使用。\n\n{get_verdict(i['safety'])}\n属于 Windows 系统管理的安装缓存，删了可能导致对应软件无法卸载或修复。不建议手动删除，可以用系统自带的磁盘清理工具安全处理。"
    },
    # ===== Windows system files =====
    {
        "match": lambda i: i["name"] == "swapfile.sys",
        "confidence": "high",
        "response": lambda i: f"这是 Windows 的 UWP 应用交换文件，系统把暂时不用的应用商店应用数据临时存到这里，释放内存。\n\n{get_verdict(i['safety'])}\n属于 Windows 系统核心文件，由系统自动管理，无法也不应该手动删除。删了系统可能变得不稳定。"
    },
    {
        "match": lambda i: i["name"] == "MRT.exe",
        "confidence": "high",
        "response": lambda i: f"这是 Windows 恶意软件删除工具（Malicious Software Removal Tool），微软每月通过 Windows Update 更新的安全扫描工具。\n\n{get_verdict(i['safety'])}\n属于 Windows 安全组件，删了会降低系统安全性。由 Windows Update 自动管理和更新。"
    },
    # ===== Windows.old =====
    {
        "match": lambda i: "windows.old" in i["path"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Windows 系统升级后保留的旧版系统文件，用于在升级出问题时回退到之前的版本。\n\n{get_verdict(i['safety'])}\n如果你的系统升级后一切正常，可以通过「设置→系统→存储→临时文件→以前的 Windows 安装」来安全清理。不要手动删文件。"
    },
    # ===== Explorer thumbcache =====
    {
        "match": lambda i: "thumbcache" in i["name"].lower() and not "windows.old" in i["path"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Windows 资源管理器的缩略图缓存，存储了你浏览过的图片和视频的预览小图。\n\n{get_verdict(i['safety'])}\n删了不影响任何功能，只是下次浏览图片文件夹时需要重新生成预览图，会稍微慢一点。可以用磁盘清理工具安全清理。"
    },
    # ===== Ubisoft =====
    {
        "match": lambda i: "ubisoft" in i["path"].lower() and "libcef" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Ubisoft Connect（育碧游戏平台）的内嵌浏览器引擎，用于显示商店和社区界面。\n\n{get_verdict(i['safety'])}\n属于育碧平台的核心组件，删了会导致界面无法显示。如果你不玩育碧游戏了，可以卸载 Ubisoft Connect。"
    },
    # ===== Rockstar =====
    {
        "match": lambda i: "rockstar" in i["path"].lower() and "libcef" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Rockstar Games Social Club（R星游戏平台）的内嵌浏览器引擎，运行 GTA、荒野大镖客等游戏时需要。\n\n{get_verdict(i['safety'])}\n属于 R星平台的核心组件。如果你不玩 R星游戏了，可以卸载 Social Club。"
    },
    # ===== @guanjia (Tencent security) =====
    {
        "match": lambda i: "guanjia" in i["path"].lower(),
        "confidence": "medium",
        "confidence": "high",
        "response": lambda i: f"这是 QClaw（腾讯管家团队出品的 AI 远程助手）的自动更新程序缓存。QClaw 可以通过微信远程控制电脑，和腾讯电脑管家是同一个团队的产品。\n\n{get_verdict(i['safety'])}\n如果你不用 QClaw 远程助手，可以卸载 QClaw 后删除这个残留。如果在用，这是更新组件，删了可能影响自动更新。"
    },
    # ===== Lenovo AIAgent RAG =====
    {
        "match": lambda i: match_path(i, "lenovo", "aiagent", "rag"),
        "confidence": "high",
        "response": lambda i: f"这是联想 AI Agent（小天）的本地知识检索引擎组件（{i['name']}），让 AI 助手能搜索和理解本地文档。\n\n{get_verdict(i['safety'])}\n属于联想 AI 助手的核心功能模块，单独删会导致文档问答功能异常。如果不用联想 AI 助手，建议整体卸载。"
    },
    # ===== Lenovo MCP Manager =====
    {
        "match": lambda i: match_path(i, "lenovo", "lemcpmanager"),
        "confidence": "medium",
        "confidence": "high",
        "response": lambda i: f"这是联想 Message Center Plus（消息推送服务）的管理程序，负责在后台检查并推送驱动更新、产品通知等消息弹窗。\n\n{get_verdict(i['safety'])}\n属于联想预装的通知推送组件，不影响电脑核心功能。如果你觉得联想弹窗烦人，可以在服务管理中禁用它。"
    },
    # ===== Lenovo LeFile (cloud search) =====
    {
        "match": lambda i: match_path(i, "lenovo", "lefile") and i["name"].endswith(".db"),
        "confidence": "high",
        "response": lambda i: f"这是联想文件管理器（乐文件）的云搜索索引数据库，记录了文件搜索的索引信息。\n\n{get_verdict(i['safety'])}\n删了的话乐文件的搜索功能需要重新建立索引。如果你不用联想自带的文件管理器，可以卸载。"
    },
    # ===== OpenAI Codex (npm global) =====
    {
        "match": lambda i: match_path(i, "npm", "node_modules", "codex") and "codex.exe" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是通过 npm 全局安装的 OpenAI Codex CLI 工具的可执行程序，AI 编程命令行助手。\n\n{get_verdict(i['safety'])}\n删了的话 codex 命令会失效。如果你不用 OpenAI Codex，可以用 npm uninstall -g @openai/codex 卸载。"
    },
    # ===== VS Code workspace storage =====
    {
        "match": lambda i: match_path(i, "code", "user", "workspacestorage") and "state.vscdb" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 VS Code 的工作区状态数据库，保存了你打开的项目的编辑器状态（标签页、滚动位置等）。\n\n{get_verdict(i['safety'])}\n删了的话对应项目在 VS Code 里的标签页布局和编辑状态会重置，但代码文件本身不受影响。可以清理。"
    },
    # ===== Visual Studio IntelliCode (ProgramData) =====
    {
        "match": lambda i: match_path(i, "programdata", "microsoft", "visualstudio") and ("intellicode" in i["name"].lower() or "intellicode" in i["path"].lower()),
        "confidence": "high",
        "response": lambda i: f"这是 Visual Studio 的 IntelliCode AI 代码补全模型的安装包缓存。\n\n{get_verdict(i['safety'])}\n缓存文件，删了不影响已安装的 IntelliCode 功能。Visual Studio 下次更新插件时会重新下载。"
    },
    # ===== Windows Defender =====
    {
        "match": lambda i: match_path(i, "windows defender") and i["name"].endswith(".vdm"),
        "confidence": "high",
        "response": lambda i: f"这是 Windows Defender（系统自带杀毒软件）的病毒定义数据库，包含最新的恶意软件特征码。\n\n{get_verdict(i['safety'])}\n属于系统安全核心文件，删了会导致杀毒软件无法识别病毒。由 Windows Update 自动管理和更新，不要手动删除。"
    },
    # ===== Zotero =====
    {
        "match": lambda i: match_path(i, "zotero") and i["name"] == "xul.dll",
        "confidence": "high",
        "response": lambda i: f"这是 Zotero（学术文献管理工具）的核心界面引擎，基于 Mozilla 的 XUL 框架构建。\n\n{get_verdict(i['safety'])}\n删了的话 Zotero 会完全无法启动。如果你不做学术研究了，可以通过控制面板卸载 Zotero。"
    },
    # ===== Git pack files =====
    {
        "match": lambda i: i["name"].endswith(".pack") and ".git" in i["path"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Git 仓库的打包数据文件，存储了项目的完整版本历史（所有代码的每次修改记录）。\n\n{get_verdict(i['safety'])}\n删了的话整个 Git 仓库的历史记录会损坏，代码版本管理会出问题。如果这个项目你不再需要，可以删除整个项目文件夹。"
    },
    # ===== Windows system .dat =====
    {
        "match": lambda i: match_path(i, "windows") and i["name"].endswith(".dat") and i["safety"] == "red",
        "confidence": "medium",
        "confidence": "high",
        "response": lambda i: f"这是 Windows 系统目录下的大型数据文件，很可能是 Windows Update 或软件安装过程中断后留下的残留文件。\n\n{get_verdict(i['safety'])}\n不要手动删除 Windows 目录下的文件。可以用系统自带的「磁盘清理」工具（选择「清理系统文件」）来安全处理这类残留。"
    },
    # ===== NVIDIA driver core =====
    {
        "match": lambda i: i["name"] == "nvlddmkm.sys",
        "confidence": "high",
        "response": lambda i: f"这是 NVIDIA 显卡驱动的核心内核模块，显卡所有功能（显示、游戏、AI 加速）都依赖它。\n\n{get_verdict(i['safety'])}\n属于显卡驱动的最核心文件，删了会导致显卡完全无法工作，甚至蓝屏。绝对不要手动删除。"
    },
    # ===== Intel OpenCL driver =====
    {
        "match": lambda i: match_path(i, "driverstore") and "opencl-clang" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Intel 核显驱动的 OpenCL 编译器组件，让应用程序能利用 Intel 核显做并行计算加速。\n\n{get_verdict(i['safety'])}\n属于 Intel 显卡驱动文件，由 Windows 驱动管理器管理。删了可能导致某些应用无法使用核显加速。不要手动删除。"
    },
    # ===== Unity WebGL support =====
    {
        "match": lambda i: match_path(i, "unity") and "webglsupport" in i["path"].lower().replace(" ", ""),
        "confidence": "high",
        "response": lambda i: f"这是 Unity 游戏引擎的 WebGL 构建工具组件，用于将游戏发布为网页版本。\n\n{get_verdict(i['safety'])}\n属于 Unity 编辑器的可选模块。如果你不需要发布网页游戏，可以通过 Unity Hub 移除 WebGL Build Support 模块。"
    },
    {
        "match": lambda i: match_path(i, "unity") and "binaryen" in i["path"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Unity WebGL 构建工具链中的 Binaryen 库，将代码编译为 WebAssembly 格式时使用。\n\n{get_verdict(i['safety'])}\n属于 Unity WebGL 模块的组件。如果不发布网页游戏，可以通过 Unity Hub 移除 WebGL Build Support。"
    },
    # ===== Ollama cublas (non-cublasLt) =====
    {
        "match": lambda i: match_path(i, "ollama") and "cublas64" in i["name"].lower() and "lt" not in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Ollama 自带的 NVIDIA cuBLAS 基础数学库，AI 模型推理时做基本矩阵运算用的。\n\n{get_verdict(i['safety'])}\n属于 Ollama GPU 加速的核心依赖，不建议单独删。卸载 Ollama 时会一起清除。"
    },
    {
        "match": lambda i: match_path(i, "ollama") and "amd_comgr" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是 Ollama 自带的 AMD GPU 编译器组件，用于 AMD 显卡加速。你用的是 NVIDIA 显卡，这个用不到。\n\n{get_verdict(i['safety'])}\n虽然用不到，但它是 Ollama 安装包自带的组件。不建议单独删。"
    },
    # ===== conda cublas (non-cublasLt) =====
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "cublas64" in i["name"].lower() and "lt" not in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_torch_response(i, i["name"], "NVIDIA cuBLAS 基础矩阵运算库，深度学习框架做 GPU 计算的底层依赖")
    },
    # ===== conda cudnn_ops =====
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower()) and "cudnn_ops" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: _conda_torch_response(i, i["name"], "NVIDIA cuDNN 基本运算库，深度学习中卷积、池化等基础操作的 GPU 加速组件")
    },
    # ===== conda/mamba mkl =====
    {
        "match": lambda i: ("miniforge" in i["path"].lower() or "micromamba" in i["path"].lower() or "mamba" in i["path"].lower()) and "mkl" in i["name"].lower() and i["name"].endswith(".conda"),
        "confidence": "high",
        "response": lambda i: f"这是 Intel MKL（数学核心函数库）的 conda 安装包缓存，NumPy 等科学计算库的底层加速依赖。\n\n{get_verdict(i['safety'])}\n纯缓存，删了不影响已安装的环境。可以用 conda clean --all 一键清理。"
    },
    # ===== Lenovo AIAgent X-Engine amd_comgr =====
    {
        "match": lambda i: match_path(i, "lenovo", "aiagent") and "amd_comgr" in i["name"].lower(),
        "confidence": "high",
        "response": lambda i: f"这是联想 AI Agent（小天）的 AMD GPU 编译器组件，用于 AMD 核显加速推理。\n\n{get_verdict(i['safety'])}\n属于联想 AI 助手的跨平台 GPU 支持组件。不建议单独删，卸载联想 AI 助手时会一起清除。"
    },
]


def _datalab_response(item: dict) -> str:
    """Generate response for Datalab/Surya OCR model cache files."""
    path_lower = item["path"].lower()
    if "text_recognition" in path_lower:
        func = "OCR 文字识别模型，能识别 90 多种语言的文字"
    elif "texify" in path_lower:
        func = "LaTeX 公式识别模型，能把图片中的数学公式转成 LaTeX 代码"
    elif "layout" in path_lower:
        func = "文档布局分析模型，能识别页面中的标题、段落、表格等结构"
    else:
        func = "文档分析 AI 模型"

    return (
        f"这是 Surya（开源 OCR 文档分析工具，由 Datalab 维护）缓存的{func}。\n\n"
        f"{get_verdict(item['safety'])}\n"
        f"删了的话下次使用 Surya 时需要重新下载模型。如果你不再做 OCR 或文档分析了，可以删除整个 datalab 缓存文件夹。"
    )


def _huggingface_response(item: dict) -> str:
    """Generate response for HuggingFace model cache files."""
    path = item["path"]
    # Extract model name from path: models--ORG--NAME
    model_match = re.search(r'models--([^\\]+)--([^\\]+)', path)
    if model_match:
        org = model_match.group(1)
        model = model_match.group(2)
        model_full = f"{org}/{model}"
    else:
        model_full = "未知模型"

    return (
        f"这是 HuggingFace 缓存的 AI 模型权重文件（{model_full}），之前你用 Python 加载这个模型时自动下载到本地的。\n\n"
        f"{get_verdict(item['safety'])}\n"
        f"删了的话下次代码里加载这个模型时需要重新下载。如果你不再用这个模型了，可以删除。"
        f"也可以用 huggingface-cli delete-cache 命令统一管理。"
    )

def _get_conda_env_name(path: str) -> str:
    """Extract conda environment name from path."""
    path_lower = path.lower()
    env_match = re.search(r'envs[/\\]([^/\\]+)', path_lower)
    if env_match:
        return env_match.group(1)
    if "miniforge3\\lib" in path_lower or "miniforge3\\pkgs" in path_lower:
        return "base (miniforge3)"
    if "micromamba\\pkgs" in path_lower:
        return "micromamba base"
    return "conda"

def _conda_torch_response(item: dict, lib_name: str, description: str) -> str:
    """Generate response for PyTorch/CUDA libs inside conda environments."""
    env_name = _get_conda_env_name(item["path"])
    is_pkg_cache = "pkgs" in item["path"].lower() and "envs" not in item["path"].lower()

    if is_pkg_cache:
        return (
            f"这是 conda 包缓存中的 {lib_name}，{description}。之前安装 PyTorch 时下载的安装包副本。\n\n"
            f"{get_verdict(item['safety'])}\n"
            f"纯缓存，删了不影响已安装的环境。可以用 conda clean --all 一键清理。"
        )

    return (
        f"这是你的 Python 环境「{env_name}」里的 {lib_name}，{description}。\n\n"
        f"{get_verdict(item['safety'])}\n"
        f"删了的话这个环境里的 PyTorch 会无法使用 GPU。如果你不再用「{env_name}」这个环境了，"
        f"可以用 conda env remove -n {env_name} 整个删掉，比单独删文件更干净。"
    )

def _conda_env_response(item: dict, description: str, lib_name: str) -> str:
    """Generate response for non-PyTorch libs inside conda environments."""
    env_name = _get_conda_env_name(item["path"])
    return (
        f"这是你的 Python 环境「{env_name}」里的 {description}。\n\n"
        f"{get_verdict(item['safety'])}\n"
        f"删了的话这个环境里依赖 {lib_name} 的代码会无法运行。如果你不再用「{env_name}」这个环境，"
        f"可以用 conda env remove -n {env_name} 整个删掉。"
    )


def generate_training_data():
    """Generate training data by matching scan results against patterns."""
    instruction = SYSTEM_PROMPT.format(kind="文件")  # default, will be overridden

    results = []
    unmatched = []

    for item in scan_results:
        kind = "文件夹" if item["is_dir"] else "文件"
        input_text = build_input(item)

        matched = False
        for pattern in PATTERNS:
            if pattern["match"](item):
                entry = {
                    "instruction": SYSTEM_PROMPT.format(kind=kind).replace("{{verdict}}", get_verdict(item["safety"])),
                    "input": input_text,
                    "output": pattern["response"](item),
                    "confidence": pattern.get("confidence", "high"),
                }
                if "verify_hint" in pattern:
                    entry["verify_hint"] = pattern["verify_hint"]
                results.append(entry)
                matched = True
                break

        if not matched:
            unmatched.append(item)

    # Add synthetic data
    synthetic_results = generate_synthetic_data()
    results.extend(synthetic_results)

    # Write training data
    output_path = os.path.join(PROJECT_ROOT, "data", "training_data.jsonl")
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in results:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Write unmatched items for review
    unmatched_path = os.path.join(PROJECT_ROOT, "data", "unmatched_files.json")
    with open(unmatched_path, "w", encoding="utf-8") as f:
        json.dump(unmatched, f, ensure_ascii=False, indent=2)

    # Stats
    high = sum(1 for r in results if r["confidence"] == "high")
    medium = sum(1 for r in results if r["confidence"] == "medium")
    low = sum(1 for r in results if r["confidence"] == "low")

    real_count = len(results) - len(synthetic_results)
    print(f"Generated {len(results)} training samples:")
    print(f"  Real (from scan): {real_count}")
    print(f"  Synthetic: {len(synthetic_results)}")
    print(f"  High confidence: {high}")
    print(f"  Medium confidence: {medium}")
    print(f"  Low confidence: {low}")
    print(f"  Unmatched files: {len(unmatched)}")
    print(f"\nOutput: {output_path}")
    print(f"Unmatched: {unmatched_path}")


def generate_synthetic_data():
    """Generate synthetic training samples for common Windows software not on this machine."""

    # Each entry: (path, name, size_human, size, is_dir, safety, output)
    # Use a generic username "User" for synthetic data
    U = "C:\\Users\\User"

    synthetic = [
        # ===== Chrome =====
        (f"{U}\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Cache\\Cache_Data\\f_00a1b2", "f_00a1b2", "850 MB", 891289600, False, "green",
         "这是 Google Chrome 浏览器的网页缓存文件，保存了你浏览过的网页图片、脚本等资源，下次访问同一网站时加载更快。\n\n放心删\n纯缓存，删了不影响 Chrome 任何功能，只是下次打开常用网站时加载会稍慢。可以在 Chrome 设置→隐私→清除浏览数据里清理。"),
        (f"{U}\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\History", "History", "200 MB", 209715200, False, "yellow",
         "这是 Google Chrome 浏览器的浏览历史数据库，记录了你访问过的所有网页地址和时间。\n\n看看再删\n删了的话 Chrome 的浏览历史和地址栏自动补全建议会清空。如果你不在意历史记录，可以在 Chrome 设置里清除。"),
        (f"{U}\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\IndexedDB", "IndexedDB", "500 MB", 524288000, True, "yellow",
         "这是 Google Chrome 浏览器里各网站存储的本地数据库，比如网页版邮箱的离线数据、在线文档的本地缓存等。\n\n看看再删\n删了的话某些网站的离线功能和本地存储数据会丢失（比如网页版 Gmail 的离线邮件）。Chrome 使用时会自动重建。"),
        (f"{U}\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Service Worker\\CacheStorage", "CacheStorage", "300 MB", 314572800, True, "green",
         "这是 Chrome 浏览器里网站 Service Worker 的缓存，让某些网站（如 Twitter、YouTube）能离线使用或加载更快。\n\n放心删\n纯缓存，删了不影响任何功能，网站下次打开时会自动重建缓存。"),
        (f"C:\\Program Files\\Google\\Chrome\\Application\\125.0.6422.76\\chrome.dll", "chrome.dll", "280 MB", 293601280, False, "yellow",
         "这是 Google Chrome 浏览器的核心引擎文件，Chrome 运行网页时的主要组件。\n\n看看再删\n属于 Chrome 浏览器的核心文件，删了 Chrome 无法启动。多个版本并存是自动更新导致的，旧版本会被 Chrome 自动清理。"),

        # ===== Firefox =====
        (f"{U}\\AppData\\Local\\Mozilla\\Firefox\\Profiles\\abc123.default-release\\cache2\\entries", "entries", "500 MB", 524288000, True, "green",
         "这是 Firefox 浏览器的网页缓存目录，保存了浏览过的网页资源副本。\n\n放心删\n纯缓存，删了不影响 Firefox 任何功能。可以在 Firefox 设置→隐私→清除数据里清理。"),
        (f"{U}\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\abc123.default-release\\places.sqlite", "places.sqlite", "150 MB", 157286400, False, "yellow",
         "这是 Firefox 浏览器的书签和浏览历史数据库。\n\n看看再删\n删了的话你的 Firefox 书签和浏览历史会全部丢失。如果你有 Firefox 账号同步，重新登录可以恢复书签。"),

        # ===== Steam =====
        (f"C:\\Program Files (x86)\\Steam\\steamapps\\common\\Counter-Strike Global Offensive\\csgo\\pak01_dir.vpk", "pak01_dir.vpk", "2.5 GB", 2684354560, False, "yellow",
         "这是 Steam 游戏 CS:GO 的核心游戏资源包，包含游戏的地图、模型、贴图等数据。\n\n看看再删\n删了的话 CS:GO 无法运行，需要在 Steam 里重新下载。如果你不玩这个游戏了，建议在 Steam 库里右键→管理→卸载。"),
        (f"C:\\Program Files (x86)\\Steam\\steamapps\\common\\Grand Theft Auto V\\x64a.rpf", "x64a.rpf", "3.8 GB", 4080218931, False, "yellow",
         "这是 Steam 游戏 GTA V 的核心资源包，包含游戏世界的模型和贴图数据。\n\n看看再删\n删了的话 GTA V 无法运行。如果你不玩了，在 Steam 库里卸载游戏，会一起清理所有游戏文件。"),
        (f"C:\\Program Files (x86)\\Steam\\steamapps\\downloading\\730\\game\\csgo\\pak01_001.vpk", "pak01_001.vpk", "1.2 GB", 1288490188, False, "green",
         "这是 Steam 正在下载或更新游戏时的临时文件，下载完成后会自动移动到游戏目录。\n\n放心删\n如果游戏已经下载完成，这是残留的临时文件，可以删。如果还在下载中，删了需要重新下载。"),
        (f"{U}\\AppData\\Local\\Steam\\htmlcache\\Cache_Data", "Cache_Data", "300 MB", 314572800, True, "green",
         "这是 Steam 客户端的内嵌浏览器缓存，保存了商店页面、社区页面等网页资源。\n\n放心删\n纯缓存，删了不影响 Steam 任何功能，只是下次打开商店页面时加载稍慢。"),
        (f"C:\\Program Files (x86)\\Steam\\steam.exe", "steam.exe", "120 MB", 125829120, False, "yellow",
         "这是 Steam 游戏平台的主程序文件。\n\n看看再删\n删了的话 Steam 无法启动，所有游戏都打不开。如果你不玩游戏了，建议通过控制面板正常卸载 Steam。"),

        # ===== Epic Games =====
        (f"C:\\Program Files\\Epic Games\\Fortnite\\FortniteGame\\Content\\Paks\\pakchunk0-WindowsClient.pak", "pakchunk0-WindowsClient.pak", "4.2 GB", 4509715660, False, "yellow",
         "这是 Epic Games 的堡垒之夜（Fortnite）核心游戏资源包，包含游戏地图和美术素材。\n\n看看再删\n删了的话堡垒之夜无法运行。如果不玩了，在 Epic Games Launcher 里卸载游戏。"),
        (f"{U}\\AppData\\Local\\EpicGamesLauncher\\Saved\\webcache_4430", "webcache_4430", "250 MB", 262144000, True, "green",
         "这是 Epic Games 启动器的网页缓存，保存了商店页面和新闻内容。\n\n放心删\n纯缓存，删了不影响 Epic Games 任何功能。"),

        # ===== WeGame =====
        (f"C:\\Program Files (x86)\\WeGame\\tgp_daemon.exe", "tgp_daemon.exe", "150 MB", 157286400, False, "yellow",
         "这是 WeGame（腾讯游戏平台）的后台服务程序，管理游戏下载和更新。\n\n看看再删\n删了的话 WeGame 无法正常运行。如果你不用 WeGame 了，建议通过控制面板正常卸载。"),

        # ===== Docker =====
        (f"{U}\\AppData\\Local\\Docker\\wsl\\data\\ext4.vhdx", "ext4.vhdx", "15.3 GB", 16424345600, False, "yellow",
         "这是 Docker Desktop 的数据存储磁盘，所有 Docker 容器、镜像和数据卷都保存在这个虚拟磁盘里。\n\n看看再删\n删了的话你的所有 Docker 容器和镜像会丢失。如果你不用 Docker 了，先在 Docker Desktop 里清理镜像，再卸载软件。可以用 docker system prune 释放空间而不删整个磁盘。"),
        (f"C:\\Program Files\\Docker\\Docker\\resources\\docker-desktop.exe", "docker-desktop.exe", "200 MB", 209715200, False, "yellow",
         "这是 Docker Desktop 的主程序文件，管理 Docker 容器的图形界面工具。\n\n看看再删\n删了的话 Docker Desktop 无法启动。如果不用 Docker 了，通过控制面板卸载。"),
        (f"{U}\\AppData\\Local\\Docker\\log\\vm\\dockerd.log", "dockerd.log", "500 MB", 524288000, False, "green",
         "这是 Docker Desktop 的运行日志文件，记录了 Docker 引擎的运行状态和调试信息。\n\n放心删\n纯日志，删了不影响 Docker 任何功能，Docker 下次启动时会自动创建新日志。"),

        # ===== Adobe Photoshop =====
        (f"C:\\Program Files\\Adobe\\Adobe Photoshop 2024\\Photoshop.exe", "Photoshop.exe", "180 MB", 188743680, False, "yellow",
         "这是 Adobe Photoshop 2024 的主程序文件，专业图像编辑软件。\n\n看看再删\n删了的话 Photoshop 无法启动。如果不用了，通过 Adobe Creative Cloud 应用正常卸载。"),
        (f"{U}\\AppData\\Roaming\\Adobe\\Adobe Photoshop 2024\\CT Font Cache", "CT Font Cache", "300 MB", 314572800, True, "green",
         "这是 Adobe Photoshop 的字体缓存目录，Photoshop 扫描系统字体后生成的索引。\n\n放心删\n纯缓存，删了不影响 Photoshop 功能，下次启动时会重新扫描字体（首次启动会稍慢）。"),
        (f"{U}\\AppData\\Local\\Temp\\Photoshop Temp12345678", "Photoshop Temp12345678", "2.0 GB", 2147483648, False, "green",
         "这是 Photoshop 编辑大图时产生的临时暂存文件（scratch disk），编辑过程中用来存放历史记录和图层数据。\n\n放心删\n如果 Photoshop 已经关闭，这是残留的临时文件，可以放心删。正在使用 Photoshop 时不要删。"),

        # ===== Adobe Premiere Pro =====
        (f"{U}\\AppData\\Roaming\\Adobe\\Common\\Media Cache Files", "Media Cache Files", "5.0 GB", 5368709120, True, "green",
         "这是 Adobe Premiere Pro / After Effects 的媒体缓存，导入视频素材后生成的预览文件，加快编辑时的回放速度。\n\n放心删\n纯缓存，删了不影响项目文件和原始素材。下次打开项目时 Premiere 会重新生成缓存，首次回放会稍慢。"),
        (f"C:\\Program Files\\Adobe\\Adobe Premiere Pro 2024\\PremierePro.dll", "PremierePro.dll", "350 MB", 367001600, False, "yellow",
         "这是 Adobe Premiere Pro 视频编辑软件的核心运行库。\n\n看看再删\n删了的话 Premiere Pro 无法启动。如果不用了，通过 Adobe Creative Cloud 正常卸载。"),

        # ===== JetBrains (IntelliJ IDEA, PyCharm, etc.) =====
        (f"C:\\Program Files\\JetBrains\\IntelliJ IDEA 2024.1\\lib\\app.jar", "app.jar", "250 MB", 262144000, False, "yellow",
         "这是 IntelliJ IDEA（JetBrains 的 Java 开发工具）的核心运行库。\n\n看看再删\n删了的话 IntelliJ IDEA 无法启动。如果不用了，通过 JetBrains Toolbox 或控制面板卸载。"),
        (f"{U}\\AppData\\Local\\JetBrains\\IntelliJIdea2024.1\\caches", "caches", "1.5 GB", 1610612736, True, "green",
         "这是 IntelliJ IDEA 的项目索引缓存，分析代码后生成的索引文件，加快代码补全和搜索速度。\n\n放心删\n纯缓存，删了不影响项目代码。下次打开项目时 IDEA 会重新建立索引，首次打开会比较慢。"),
        (f"C:\\Program Files\\JetBrains\\PyCharm 2024.1\\lib\\app.jar", "app.jar", "220 MB", 230686720, False, "yellow",
         "这是 PyCharm（JetBrains 的 Python 开发工具）的核心运行库。\n\n看看再删\n删了的话 PyCharm 无法启动。如果不用了，通过 JetBrains Toolbox 或控制面板卸载。"),
        (f"{U}\\AppData\\Local\\JetBrains\\PyCharm2024.1\\caches", "caches", "800 MB", 838860800, True, "green",
         "这是 PyCharm 的项目索引缓存。\n\n放心删\n纯缓存，删了不影响代码。下次打开项目时会重新索引。"),

        # ===== Spotify =====
        (f"{U}\\AppData\\Local\\Spotify\\Storage", "Storage", "1.0 GB", 1073741824, True, "green",
         "这是 Spotify（音乐流媒体应用）的本地缓存，保存了你最近听过的歌曲数据，减少重复下载流量。\n\n放心删\n纯缓存，删了不影响 Spotify 功能，只是下次听歌需要重新在线加载。已下载的离线歌曲需要重新下载。"),
        (f"{U}\\AppData\\Roaming\\Spotify\\Users\\user123-user\\offline.bnk", "offline.bnk", "2.0 GB", 2147483648, False, "yellow",
         "这是 Spotify 的离线音乐数据库，保存了你下载用于离线播放的歌曲。\n\n看看再删\n删了的话离线下载的歌曲会丢失，需要重新下载。在线播放不受影响。"),

        # ===== Telegram =====
        (f"{U}\\AppData\\Roaming\\Telegram Desktop\\tdata\\user_data\\cache", "cache", "1.5 GB", 1610612736, True, "green",
         "这是 Telegram 电脑版的聊天媒体缓存，保存了你查看过的图片、视频和文件的本地副本。\n\n放心删\n纯缓存，删了不影响聊天记录（消息在云端）。下次查看图片/视频时会重新从服务器加载。可以在 Telegram 设置→数据和存储里管理缓存。"),

        # ===== WhatsApp =====
        (f"{U}\\AppData\\Local\\Packages\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm\\LocalState\\shared\\transfers", "transfers", "800 MB", 838860800, True, "yellow",
         "这是 WhatsApp 电脑版收发的文件缓存，保存了聊天中传输的图片、视频和文档。\n\n看看再删\n删了的话本地缓存的聊天文件会消失，但聊天记录本身还在手机上。重新打开对话时文件需要重新下载。"),

        # ===== Slack =====
        (f"{U}\\AppData\\Roaming\\Slack\\Cache\\Cache_Data", "Cache_Data", "500 MB", 524288000, True, "green",
         "这是 Slack（团队协作工具）的本地缓存，保存了频道消息中的图片和文件预览。\n\n放心删\n纯缓存，删了不影响 Slack 功能，消息和文件都在云端。下次查看时会重新加载。"),
        (f"{U}\\AppData\\Roaming\\Slack\\Service Worker\\CacheStorage", "CacheStorage", "300 MB", 314572800, True, "green",
         "这是 Slack 的 Service Worker 缓存，加速应用加载用的。\n\n放心删\n纯缓存，删了 Slack 下次启动稍慢，之后恢复正常。"),

        # ===== Teams =====
        (f"{U}\\AppData\\Local\\Packages\\MSTeams_8wekyb3d8bbwe\\LocalCache\\Microsoft\\MSTeams\\EBWebView\\Default\\Cache\\Cache_Data", "Cache_Data", "600 MB", 629145600, True, "green",
         "这是 Microsoft Teams（办公协作工具）的网页缓存，保存了聊天界面中的图片和文件预览。\n\n放心删\n纯缓存，删了不影响 Teams 功能，消息都在云端。下次查看时重新加载。"),

        # ===== Notion =====
        (f"{U}\\AppData\\Roaming\\Notion\\Cache\\Cache_Data", "Cache_Data", "400 MB", 419430400, True, "green",
         "这是 Notion（笔记和知识管理工具）的本地缓存，保存了你打开过的页面和图片。\n\n放心删\n纯缓存，删了不影响 Notion 任何数据（所有内容在云端）。下次打开页面时会重新加载。"),

        # ===== OneDrive =====
        (f"{U}\\AppData\\Local\\Microsoft\\OneDrive\\logs\\Business1", "Business1", "200 MB", 209715200, True, "green",
         "这是 OneDrive（微软云盘）的同步日志文件夹，记录了文件同步的详细日志。\n\n放心删\n纯日志，删了不影响 OneDrive 同步功能。OneDrive 下次同步时会自动创建新日志。"),

        # ===== Dropbox =====
        (f"{U}\\AppData\\Local\\Dropbox\\instance1\\content_cache", "content_cache", "1.0 GB", 1073741824, True, "green",
         "这是 Dropbox（云存储工具）的文件预览缓存，保存了你预览过的文件的本地副本。\n\n放心删\n纯缓存，删了不影响 Dropbox 同步和文件安全。下次预览文件时会重新生成。"),

        # ===== iCloud =====
        (f"{U}\\AppData\\Local\\Apple Inc\\iCloud\\iCloudDrive\\session_cache", "session_cache", "500 MB", 524288000, True, "green",
         "这是 iCloud Drive 的同步会话缓存，Windows 上同步 iCloud 文件时产生的临时数据。\n\n放心删\n纯缓存，删了不影响 iCloud 同步功能。"),

        # ===== Java / JDK =====
        (f"C:\\Program Files\\Java\\jdk-21\\lib\\modules", "modules", "130 MB", 136314880, False, "yellow",
         "这是 Java JDK 21 的核心模块文件，包含 Java 标准库的所有类和方法，运行和编译 Java 程序必需。\n\n看看再删\n删了的话所有 Java 程序都无法运行和编译。如果不做 Java 开发了，可以通过控制面板卸载 JDK。"),
        (f"{U}\\.gradle\\caches\\modules-2\\files-2.1", "files-2.1", "3.0 GB", 3221225472, True, "green",
         "这是 Gradle（Java 构建工具）的依赖缓存，下载过的第三方 Java 库都缓存在这里。\n\n放心删\n纯缓存，删了不影响项目代码。下次构建时 Gradle 会重新下载需要的依赖。"),
        (f"{U}\\.m2\\repository", "repository", "2.5 GB", 2684354560, True, "green",
         "这是 Maven（Java 构建工具）的本地仓库，下载过的 Java 依赖包都存在这里。\n\n放心删\n纯缓存，删了不影响项目代码。下次构建时 Maven 会重新下载依赖。可以定期清理节省空间。"),

        # ===== .NET =====
        (f"C:\\Program Files\\dotnet\\shared\\Microsoft.NETCore.App\\8.0.0", "8.0.0", "200 MB", 209715200, True, "yellow",
         "这是 .NET 8.0 运行时的核心文件，很多 Windows 应用和开发工具依赖它来运行。\n\n看看再删\n删了的话依赖 .NET 8 的应用会无法启动。不建议手动删，通过控制面板管理 .NET 版本。"),
        (f"{U}\\AppData\\Local\\NuGet\\v3-cache", "v3-cache", "1.0 GB", 1073741824, True, "green",
         "这是 NuGet（.NET 包管理器）的下载缓存，之前安装的 .NET 库包都缓存在这里。\n\n放心删\n纯缓存，删了不影响已安装的项目。下次构建时 NuGet 会重新下载需要的包。"),

        # ===== Node.js =====
        (f"{U}\\AppData\\Roaming\\nvm\\v20.11.0\\node.exe", "node.exe", "110 MB", 115343360, False, "yellow",
         "这是 Node.js v20.11.0 的运行时可执行文件，通过 nvm（Node 版本管理器）安装的。\n\n看看再删\n删了的话这个版本的 Node.js 无法使用。如果你不需要这个版本了，可以用 nvm uninstall 20.11.0 卸载。"),
        (f"{U}\\AppData\\Local\\Yarn\\Cache\\v6", "v6", "1.5 GB", 1610612736, True, "green",
         "这是 Yarn（前端包管理器）的下载缓存，安装 npm 包时下载的文件副本。\n\n放心删\n纯缓存，删了不影响已安装的项目依赖。可以用 yarn cache clean 清理。"),

        # ===== Git =====
        (f"C:\\Program Files\\Git\\mingw64\\bin\\git.exe", "git.exe", "120 MB", 125829120, False, "yellow",
         "这是 Git 版本控制工具的主程序文件，代码开发和版本管理的核心工具。\n\n看看再删\n删了的话 git 命令会失效，所有依赖 Git 的工具（VS Code、GitHub Desktop 等）也会受影响。如果不做开发了，通过控制面板卸载 Git。"),

        # ===== Blender =====
        (f"C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe", "blender.exe", "180 MB", 188743680, False, "yellow",
         "这是 Blender（开源 3D 建模和动画软件）的主程序文件。\n\n看看再删\n删了的话 Blender 无法启动。如果不用了，通过控制面板卸载。"),
        (f"{U}\\AppData\\Roaming\\Blender Foundation\\Blender\\4.0\\cache", "cache", "500 MB", 524288000, True, "green",
         "这是 Blender 的渲染缓存和临时文件，3D 渲染时产生的中间数据。\n\n放心删\n纯缓存，删了不影响 Blender 功能和项目文件。"),

        # ===== OBS Studio =====
        (f"C:\\Program Files\\obs-studio\\bin\\64bit\\obs64.exe", "obs64.exe", "130 MB", 136314880, False, "yellow",
         "这是 OBS Studio（开源直播和录屏软件）的主程序文件。\n\n看看再删\n删了的话 OBS 无法启动。如果不用了，通过控制面板卸载。"),
        (f"{U}\\Videos\\OBS\\2024-01-15 20-30-45.mkv", "2024-01-15 20-30-45.mkv", "3.5 GB", 3758096384, False, "green",
         "这是 OBS Studio 录制的视频文件，你在某次直播或录屏时生成的。\n\n放心删\n这是你的录制内容，删了就没了。确认不需要后可以删除释放空间。"),

        # ===== VLC =====
        (f"C:\\Program Files\\VideoLAN\\VLC\\plugins", "plugins", "200 MB", 209715200, True, "yellow",
         "这是 VLC 媒体播放器的插件目录，包含各种音视频格式的解码器。\n\n看看再删\n删了的话 VLC 无法播放大部分视频格式。如果不用 VLC 了，通过控制面板卸载。"),

        # ===== 7-Zip =====
        (f"C:\\Program Files\\7-Zip\\7z.dll", "7z.dll", "110 MB", 115343360, False, "yellow",
         "这是 7-Zip 压缩工具的核心解压库，支持 ZIP、7z、RAR 等压缩格式。\n\n看看再删\n删了的话 7-Zip 无法解压任何文件。如果不用了，通过控制面板卸载。"),

        # ===== Visual Studio =====
        (f"C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\Common7\\IDE\\devenv.exe", "devenv.exe", "150 MB", 157286400, False, "yellow",
         "这是 Visual Studio 2022 的主程序文件，微软的集成开发环境（IDE）。\n\n看看再删\n删了的话 Visual Studio 无法启动。如果不用了，通过 Visual Studio Installer 卸载。"),
        (f"{U}\\AppData\\Local\\Microsoft\\VisualStudio\\17.0_abc123\\ComponentModelCache", "ComponentModelCache", "300 MB", 314572800, True, "green",
         "这是 Visual Studio 的组件模型缓存，加速 IDE 启动和扩展加载用的。\n\n放心删\n纯缓存，删了 Visual Studio 下次启动稍慢，之后恢复正常。"),

        # ===== Windows system files =====
        (f"C:\\pagefile.sys", "pagefile.sys", "8.0 GB", 8589934592, False, "red",
         "这是 Windows 的虚拟内存文件（页面文件），当物理内存不够时，系统会把部分数据临时存到这里。\n\n千万别删\n属于 Windows 最核心的系统文件之一，删了可能导致蓝屏或程序频繁崩溃。大小由系统自动管理。"),
        (f"C:\\hiberfil.sys", "hiberfil.sys", "6.0 GB", 6442450944, False, "red",
         "这是 Windows 的休眠文件，电脑进入休眠状态时把内存数据保存到这里，下次开机时快速恢复。\n\n千万别删\n属于系统核心文件。如果你不用休眠功能，可以用管理员命令 powercfg /hibernate off 关闭休眠来释放空间。"),
        (f"C:\\Windows\\SoftwareDistribution\\Download", "Download", "2.0 GB", 2147483648, True, "green",
         "这是 Windows Update 下载的更新安装包缓存，已经安装完成的更新包仍留在这里。\n\n放心删\n已安装的更新不受影响。可以通过系统自带的「磁盘清理」→「清理系统文件」→「Windows 更新清理」安全处理。"),
        (f"C:\\Windows\\Temp", "Temp", "500 MB", 524288000, True, "green",
         "这是 Windows 系统级临时文件夹，各种程序运行时产生的临时数据。\n\n放心删\n纯临时文件，可以通过「磁盘清理」安全处理。正在被其他程序使用的文件会被跳过。"),

        # ===== Windows WinSxS =====
        (f"C:\\Windows\\WinSxS\\Backup", "Backup", "1.5 GB", 1610612736, True, "red",
         "这是 Windows 组件存储的备份目录，保存了系统组件的备用版本，用于系统修复和更新回退。\n\n千万别删\n属于 Windows 系统核心目录，手动删除可能导致系统更新失败或无法修复。可以用 Dism.exe /Online /Cleanup-Image /StartComponentCleanup 安全清理。"),

        # ===== Recycle Bin =====
        (f"C:\\$Recycle.Bin\\S-1-5-21-123456\\$R1A2B3C.zip", "$R1A2B3C.zip", "1.0 GB", 1073741824, False, "green",
         "这是回收站里的一个已删除的 ZIP 压缩包，之前你删除后被移到了回收站。\n\n放心删\n已经在回收站里了，说明你之前就想删它。可以右键回收站→清空回收站来释放空间。"),

        # ===== Printer driver =====
        (f"C:\\Windows\\System32\\spool\\drivers\\x64\\3", "3", "300 MB", 314572800, True, "red",
         "这是 Windows 打印机驱动文件夹，安装过的打印机驱动程序都存在这里。\n\n千万别删\n删了的话所有打印机都会无法打印。属于系统管理的驱动文件，如果要清理旧驱动，用设备管理器操作更安全。"),

        # ===== Windows Error Reports =====
        (f"{U}\\AppData\\Local\\CrashDumps", "CrashDumps", "500 MB", 524288000, True, "green",
         "这是 Windows 保存的程序崩溃转储文件，当应用程序崩溃时系统自动保存的调试数据。\n\n放心删\n除非你需要调试崩溃问题，否则这些文件没有用。删了不影响任何功能。"),
        (f"C:\\ProgramData\\Microsoft\\Windows\\WER\\ReportArchive", "ReportArchive", "200 MB", 209715200, True, "green",
         "这是 Windows 错误报告的归档目录，保存了已发送或待发送的程序错误报告。\n\n放心删\n纯错误报告存档，删了不影响任何功能。"),

        # ===== Font cache =====
        (f"{U}\\AppData\\Local\\Microsoft\\FontCache", "FontCache", "150 MB", 157286400, True, "green",
         "这是 Windows 的字体渲染缓存，系统预处理字体信息后缓存在这里加速文字显示。\n\n放心删\n删了不影响任何功能，系统下次启动时会自动重建字体缓存。"),

        # ===== Windows Defender scans =====
        (f"C:\\ProgramData\\Microsoft\\Windows Defender\\Scans\\History\\Service\\DetectionHistory", "DetectionHistory", "200 MB", 209715200, True, "yellow",
         "这是 Windows Defender 的威胁检测历史记录，保存了之前扫描发现的恶意软件信息。\n\n看看再删\n删了的话 Defender 的扫描历史会清空，但不影响实时防护功能。如果你想保留安全审计记录，建议保留。"),

        # ===== System Restore =====
        (f"C:\\System Volume Information", "System Volume Information", "5.0 GB", 5368709120, True, "red",
         "这是 Windows 系统还原点存储目录，保存了系统在关键时间点的快照，出问题时可以回退。\n\n千万别删\n属于系统核心保护机制。如果需要释放空间，可以在系统保护设置里调整还原点占用的磁盘大小。"),

        # ===== Backup related =====
        (f"{U}\\AppData\\Local\\Microsoft\\Windows\\FileHistory", "FileHistory", "3.0 GB", 3221225472, True, "yellow",
         "这是 Windows 文件历史记录的本地缓存，保存了你的文档和桌面文件的定期备份。\n\n看看再删\n删了的话你的文件备份历史会丢失，无法恢复到之前的版本。如果你有其他备份方案，可以在设置里关闭文件历史记录。"),

        # ===== Common DLL patterns =====
        (f"C:\\Program Files\\Common Files\\Microsoft Shared\\ClickToRun\\OfficeC2RClient.exe", "OfficeC2RClient.exe", "130 MB", 136314880, False, "yellow",
         "这是 Microsoft Office 的即点即用更新客户端，负责 Office 的自动更新和修复。\n\n看看再删\n删了的话 Office 无法自动更新和自我修复。属于 Office 的核心服务组件，不建议单独删除。"),

        # ===== GitHub Desktop =====
        (f"{U}\\AppData\\Local\\GitHubDesktop\\app-3.3.8\\GitHubDesktop.exe", "GitHubDesktop.exe", "150 MB", 157286400, False, "yellow",
         "这是 GitHub Desktop 的主程序文件，Git 图形化管理工具。\n\n看看再删\n删了的话 GitHub Desktop 无法启动。旧版本（非当前使用的 app-* 文件夹）可以清理。"),

        # ===== Postman =====
        (f"{U}\\AppData\\Local\\Postman\\app-10.22.0\\Postman.exe", "Postman.exe", "170 MB", 178257920, False, "yellow",
         "这是 Postman（API 测试工具）的主程序文件。\n\n看看再删\n删了的话 Postman 无法启动。旧版本文件夹可以清理。如果不做 API 开发了，直接卸载。"),

        # ===== Figma =====
        (f"{U}\\AppData\\Local\\Figma\\app-124.5.2\\Figma.exe", "Figma.exe", "160 MB", 167772160, False, "yellow",
         "这是 Figma（UI 设计工具）的桌面客户端主程序。\n\n看看再删\n删了的话 Figma 桌面版无法使用，但你仍可以在浏览器里访问 figma.com 使用在线版。"),

        # ===== Anaconda =====
        (f"{U}\\anaconda3\\pkgs\\cache", "cache", "2.0 GB", 2147483648, True, "green",
         "这是 Anaconda（Python 数据科学平台）的包缓存，之前安装 Python 包时下载的安装文件。\n\n放心删\n纯缓存，删了不影响已安装的环境。可以用 conda clean --all 一键清理。"),
        (f"{U}\\anaconda3\\envs\\myenv\\Lib\\site-packages\\torch\\lib\\torch_cuda.dll", "torch_cuda.dll", "850 MB", 891289600, False, "yellow",
         "这是你的 Anaconda 环境「myenv」里的 PyTorch CUDA GPU 加速核心库。\n\n看看再删\n删了的话这个环境里的 PyTorch 无法使用 GPU。如果你不用这个环境了，可以用 conda env remove -n myenv 整个删掉。"),

        # ===== Cursor (AI code editor) =====
        (f"{U}\\AppData\\Local\\Programs\\cursor\\Cursor.exe", "Cursor.exe", "200 MB", 209715200, False, "yellow",
         "这是 Cursor（AI 驱动的代码编辑器）的主程序文件，内置 AI 编程助手的 VS Code 分支。\n\n看看再删\n删了的话 Cursor 无法启动。如果不用了，通过控制面板卸载。"),
        (f"{U}\\AppData\\Roaming\\Cursor\\Cache\\Cache_Data", "Cache_Data", "400 MB", 419430400, True, "green",
         "这是 Cursor 编辑器的缓存文件，保存了扩展和网页内容的本地副本。\n\n放心删\n纯缓存，删了不影响 Cursor 功能。"),

        # ===== Windsurf (AI code editor) =====
        (f"{U}\\AppData\\Local\\Programs\\windsurf\\Windsurf.exe", "Windsurf.exe", "200 MB", 209715200, False, "yellow",
         "这是 Windsurf（Codeium 出品的 AI 代码编辑器）的主程序文件。\n\n看看再删\n删了的话 Windsurf 无法启动。如果不用了，通过控制面板卸载。"),

        # ===== QQ =====
        (f"C:\\Program Files\\Tencent\\QQNT\\QQ.exe", "QQ.exe", "180 MB", 188743680, False, "yellow",
         "这是 QQ 的主程序文件，腾讯的即时通讯软件。\n\n看看再删\n删了的话 QQ 无法启动。如果不用 QQ 了，通过控制面板卸载。"),
        (f"{U}\\AppData\\Roaming\\Tencent\\QQ\\Cache\\Image", "Image", "1.0 GB", 1073741824, True, "green",
         "这是 QQ 的图片缓存，保存了聊天中收发的图片本地副本。\n\n放心删\n纯缓存，删了不影响聊天记录。下次查看图片时会从服务器重新加载。可以在 QQ 设置里管理缓存。"),

        # ===== BiliBili =====
        (f"{U}\\AppData\\Local\\哔哩哔哩\\cache\\video", "video", "2.0 GB", 2147483648, True, "green",
         "这是哔哩哔哩电脑版的视频缓存，看过的视频会缓存在本地。\n\n放心删\n纯缓存，删了不影响 B 站功能。下次看视频时会重新在线加载。"),

        # ===== NetEase CloudMusic =====
        (f"{U}\\AppData\\Local\\NetEase\\CloudMusic\\Cache", "Cache", "1.5 GB", 1610612736, True, "green",
         "这是网易云音乐的本地缓存，听过的歌曲会缓存在这里，下次播放时不用重新下载。\n\n放心删\n纯缓存，删了不影响网易云功能。已下载的歌曲需要重新下载。可以在网易云设置里管理缓存。"),

        # ===== WPS Office =====
        (f"C:\\Program Files\\Kingsoft\\WPS Office\\12.1.0.16929\\office6\\wps.exe", "wps.exe", "150 MB", 157286400, False, "yellow",
         "这是 WPS Office 的文字处理程序主文件（类似 Word）。\n\n看看再删\n删了的话 WPS 文字处理无法使用。如果不用 WPS 了，通过控制面板卸载。"),
        (f"{U}\\AppData\\Local\\Kingsoft\\WPS Cloud Files\\userdata\\qing\\filecache", "filecache", "500 MB", 524288000, True, "green",
         "这是 WPS 云文档的本地缓存，你在 WPS 里打开过的云端文档的本地副本。\n\n放心删\n纯缓存，删了不影响云端文档。下次打开时会重新从云端加载。"),

        # ===== Feishu / Lark =====
        (f"{U}\\AppData\\Roaming\\Feishu\\Cache", "Cache", "800 MB", 838860800, True, "green",
         "这是飞书（字节跳动的企业协作工具）的本地缓存，保存了聊天中的图片、文件和网页预览。\n\n放心删\n纯缓存，删了不影响飞书功能，消息和文件都在云端。"),

        # ===== DingTalk =====
        (f"{U}\\AppData\\Roaming\\DingTalk\\cache2", "cache2", "600 MB", 629145600, True, "green",
         "这是钉钉（阿里巴巴的企业协作工具）的本地缓存，保存了聊天中的媒体文件和预览数据。\n\n放心删\n纯缓存，删了不影响钉钉功能。"),

        # ===== Baidu Netdisk =====
        (f"C:\\Program Files\\BaiduNetdisk\\BaiduNetdisk.exe", "BaiduNetdisk.exe", "150 MB", 157286400, False, "yellow",
         "这是百度网盘的主程序文件。\n\n看看再删\n删了的话百度网盘无法启动。如果不用了，通过控制面板卸载。"),
        (f"{U}\\AppData\\Local\\BaiduNetdisk\\cache", "cache", "1.0 GB", 1073741824, True, "green",
         "这是百度网盘的下载缓存和预览缓存。\n\n放心删\n纯缓存，删了不影响已下载的文件和云端数据。"),

        # ===== Unknown / hash-named files (teach model to say "不确定") =====
        (f"{U}\\AppData\\Local\\a7b3c9d2e1f4\\data.bin", "data.bin", "500 MB", 524288000, False, "yellow",
         "这个文件的路径中没有可识别的软件名，无法确定它属于哪个应用。文件夹名看起来像是某个软件自动生成的随机 ID。\n\n看看再删\n建议先查看这个文件夹里有没有其他线索（比如 .exe 文件或说明文档）。如果确认不是正在使用的软件，可以先备份再删除。"),
        (f"{U}\\AppData\\Local\\Temp\\82a1b3c4d5e6f7\\extracted\\payload.dat", "payload.dat", "400 MB", 419430400, False, "green",
         "这是临时目录下的解压缓存文件，很可能是某个软件安装或更新时解压的临时数据。\n\n放心删\n在临时目录下的文件通常可以安全删除。如果对应的安装已经完成，这就是残留，可以清理。"),
        (f"C:\\ProgramData\\Package Cache\\{{ABC12345-6789-DEF0-1234-567890ABCDEF}}v16.11.34\\packages\\payload.cab", "payload.cab", "350 MB", 367001600, False, "yellow",
         "这是 Visual Studio 或其他微软产品的安装包缓存（Package Cache），用于软件修复和卸载。\n\n看看再删\n删了可能导致对应软件无法修复或卸载。如果你已经不用对应的软件了，可以先卸载软件再清理这个缓存。"),

        # ===== More "unknown" patterns =====
        (f"{U}\\AppData\\Local\\Temp\\nsd1234.tmp\\ns-temp-file.dat", "ns-temp-file.dat", "200 MB", 209715200, False, "green",
         "这是 NSIS 安装程序（很多免费软件用的安装工具）留下的临时文件。\n\n放心删\n安装完成后的残留，可以放心删除。"),
        (f"{U}\\AppData\\Local\\CrashReportClient\\Saved\\Crashes", "Crashes", "300 MB", 314572800, True, "green",
         "这是 Unreal Engine 游戏的崩溃报告缓存，某个使用虚幻引擎的游戏崩溃时自动保存的调试数据。\n\n放心删\n除非你是游戏开发者需要调试崩溃，否则可以放心删除。"),

        # ===== Brave Browser =====
        (f"{U}\\AppData\\Local\\BraveSoftware\\Brave-Browser\\User Data\\Default\\Cache\\Cache_Data", "Cache_Data", "700 MB", 734003200, True, "green",
         "这是 Brave 浏览器的网页缓存，保存了浏览过的网页资源副本。\n\n放心删\n纯缓存，删了不影响 Brave 功能。可以在浏览器设置里清除浏览数据。"),

        # ===== Opera =====
        (f"{U}\\AppData\\Local\\Opera Software\\Opera Stable\\Cache\\Cache_Data", "Cache_Data", "500 MB", 524288000, True, "green",
         "这是 Opera 浏览器的网页缓存。\n\n放心删\n纯缓存，删了不影响 Opera 功能。"),

        # ===== Vivaldi =====
        (f"{U}\\AppData\\Local\\Vivaldi\\User Data\\Default\\Cache\\Cache_Data", "Cache_Data", "400 MB", 419430400, True, "green",
         "这是 Vivaldi 浏览器的网页缓存。\n\n放心删\n纯缓存，删了不影响 Vivaldi 功能。"),

        # ===== Origin / EA App =====
        (f"C:\\Program Files\\EA Games\\Battlefield 2042\\Data\\Win64\\cas_01.cas", "cas_01.cas", "5.0 GB", 5368709120, False, "yellow",
         "这是 EA 游戏《战地 2042》的核心游戏数据包，包含地图、模型等游戏资源。\n\n看看再删\n删了的话游戏无法运行。如果不玩了，通过 EA App 卸载游戏。"),
        (f"{U}\\AppData\\Local\\Electronic Arts\\EA Desktop\\cache", "cache", "300 MB", 314572800, True, "green",
         "这是 EA Desktop（EA 游戏平台）的界面缓存。\n\n放心删\n纯缓存，删了不影响 EA 游戏。"),

        # ===== GOG Galaxy =====
        (f"C:\\Program Files (x86)\\GOG Galaxy\\GalaxyClient.exe", "GalaxyClient.exe", "140 MB", 146800640, False, "yellow",
         "这是 GOG Galaxy（DRM-Free 游戏平台）的主程序文件。\n\n看看再删\n删了的话 GOG Galaxy 无法启动。如果不用了，通过控制面板卸载。"),

        # ===== Battle.net =====
        (f"C:\\Program Files (x86)\\Battle.net\\Battle.net.exe", "Battle.net.exe", "130 MB", 136314880, False, "yellow",
         "这是暴雪战网（Battle.net）的主程序文件，暴雪游戏平台。\n\n看看再删\n删了的话无法启动战网和暴雪游戏。如果不玩暴雪游戏了，通过控制面板卸载。"),
        (f"{U}\\AppData\\Local\\Battle.net\\Cache", "Cache", "400 MB", 419430400, True, "green",
         "这是暴雪战网的界面缓存和更新缓存。\n\n放心删\n纯缓存，删了不影响游戏。"),

        # ===== Genshin Impact =====
        (f"C:\\Program Files\\Genshin Impact\\Genshin Impact Game\\GenshinImpact_Data\\StreamingAssets\\VideoAssets", "VideoAssets", "3.0 GB", 3221225472, True, "yellow",
         "这是原神（Genshin Impact）的过场动画视频资源包。\n\n看看再删\n删了的话游戏中的过场动画无法播放，但不影响基本游玩。如果不玩原神了，通过启动器卸载游戏。"),

        # ===== League of Legends =====
        (f"C:\\Riot Games\\League of Legends\\Game\\DATA\\FINAL\\Champions", "Champions", "4.0 GB", 4294967296, True, "yellow",
         "这是英雄联盟（League of Legends）的英雄模型和技能资源包。\n\n看看再删\n删了的话游戏无法正常运行。如果不玩了，通过 Riot Client 卸载。"),

        # ===== Valorant =====
        (f"C:\\Riot Games\\VALORANT\\live\\ShooterGame\\Content\\Paks", "Paks", "20.0 GB", 21474836480, True, "yellow",
         "这是 Valorant（拳头公司的 FPS 游戏）的核心游戏资源包。\n\n看看再删\n删了的话 Valorant 无法运行。如果不玩了，通过 Riot Client 卸载。"),

        # ===== Minecraft =====
        (f"{U}\\AppData\\Roaming\\.minecraft\\versions\\1.20.4\\1.20.4.jar", "1.20.4.jar", "150 MB", 157286400, False, "yellow",
         "这是 Minecraft Java 版 1.20.4 的游戏核心文件。\n\n看看再删\n删了的话这个版本的 Minecraft 无法启动。如果不玩这个版本了，可以在启动器里删除。其他版本不受影响。"),
        (f"{U}\\AppData\\Roaming\\.minecraft\\assets\\objects", "objects", "1.5 GB", 1610612736, True, "yellow",
         "这是 Minecraft 的游戏素材文件（音效、贴图、语言包等）。\n\n看看再删\n删了的话 Minecraft 启动时会重新下载这些素材。如果你还在玩 Minecraft，不建议删。"),

        # ===== Python venv =====
        (f"{U}\\Projects\\myproject\\.venv\\Lib\\site-packages\\torch\\lib\\torch_cuda.dll", "torch_cuda.dll", "900 MB", 943718400, False, "yellow",
         "这是你的项目「myproject」的 Python 虚拟环境里的 PyTorch CUDA GPU 加速库。\n\n看看再删\n删了的话这个项目的 PyTorch 无法使用 GPU。如果这个项目不再需要了，可以删除整个 .venv 文件夹。"),

        # ===== Poetry cache =====
        (f"{U}\\AppData\\Local\\pypoetry\\Cache\\artifacts", "artifacts", "800 MB", 838860800, True, "green",
         "这是 Poetry（Python 包管理工具）的下载缓存，之前安装 Python 包时下载的文件副本。\n\n放心删\n纯缓存，删了不影响已安装的项目。可以用 poetry cache clear --all . 清理。"),

        # ===== Rust target =====
        (f"{U}\\Projects\\myapp\\target\\debug", "debug", "2.0 GB", 2147483648, True, "green",
         "这是 Rust 项目「myapp」的编译输出目录，编译过程中产生的中间文件和最终可执行文件。\n\n放心删\n删了不影响源代码，下次 cargo build 时会重新编译。Rust 项目的 target 文件夹往往很大，定期清理可以释放大量空间。"),
        (f"{U}\\.cargo\\registry\\cache", "cache", "1.0 GB", 1073741824, True, "green",
         "这是 Cargo（Rust 包管理器）的依赖缓存，下载过的 Rust 库包都缓存在这里。\n\n放心删\n纯缓存，删了不影响项目代码。下次编译时 Cargo 会重新下载需要的依赖。"),

        # ===== Go modules =====
        (f"{U}\\go\\pkg\\mod\\cache\\download", "download", "1.5 GB", 1610612736, True, "green",
         "这是 Go 语言的模块下载缓存，用 go get 下载的第三方库都缓存在这里。\n\n放心删\n纯缓存，删了不影响项目代码。可以用 go clean -modcache 清理。"),

        # ===== Android Studio =====
        (f"{U}\\.android\\avd\\Pixel_4_API_33.avd\\userdata-qemu.img", "userdata-qemu.img", "2.0 GB", 2147483648, False, "yellow",
         "这是 Android Studio 模拟器的虚拟磁盘，保存了 Android 模拟器里的系统数据和你安装的测试应用。\n\n看看再删\n删了的话这个模拟器的所有数据会丢失（安装的应用、设置等）。如果不用这个模拟器了，在 Android Studio 的 Device Manager 里删除更安全。"),
        (f"{U}\\.gradle\\caches\\transforms-3", "transforms-3", "2.0 GB", 2147483648, True, "green",
         "这是 Android Studio / Gradle 的构建转换缓存，编译 Android 项目时的中间产物。\n\n放心删\n纯缓存，下次构建时会自动重建。可以释放大量空间。"),

        # ===== Xcode (Windows rare but possible through build tools) =====
        # Skip — not relevant on Windows

        # ===== VMware =====
        (f"{U}\\Documents\\Virtual Machines\\Windows 11\\Windows 11.vmdk", "Windows 11.vmdk", "25.0 GB", 26843545600, False, "yellow",
         "这是 VMware 虚拟机的虚拟磁盘文件，里面装着一个完整的 Windows 11 虚拟系统。\n\n看看再删\n删了的话这个虚拟机里的所有数据会永久丢失。如果你不再需要这个虚拟机，可以在 VMware 里右键→从硬盘删除。"),
        (f"C:\\Program Files (x86)\\VMware\\VMware Player\\vmplayer.exe", "vmplayer.exe", "150 MB", 157286400, False, "yellow",
         "这是 VMware Player（虚拟机软件）的主程序文件。\n\n看看再删\n删了的话 VMware 无法启动。如果不用了，通过控制面板卸载。"),

        # ===== VirtualBox =====
        (f"{U}\\VirtualBox VMs\\Ubuntu\\Ubuntu.vdi", "Ubuntu.vdi", "15.0 GB", 16106127360, False, "yellow",
         "这是 VirtualBox 虚拟机的虚拟磁盘文件，里面装着一个完整的 Ubuntu Linux 虚拟系统。\n\n看看再删\n删了的话虚拟机里的所有 Linux 数据会永久丢失。如果不用了，在 VirtualBox 管理器里删除虚拟机。"),

        # ===== Hyper-V =====
        (f"C:\\ProgramData\\Microsoft\\Windows\\Virtual Machines\\GUID.vmcx", "GUID.vmcx", "100 MB", 104857600, False, "yellow",
         "这是 Hyper-V 虚拟机的配置文件，Windows 自带的虚拟化管理器。\n\n看看再删\n删了的话对应的 Hyper-V 虚拟机配置会丢失。如果不用 Hyper-V 了，在 Hyper-V 管理器里删除虚拟机。"),

        # ===== PowerShell modules =====
        (f"{U}\\Documents\\WindowsPowerShell\\Modules", "Modules", "300 MB", 314572800, True, "yellow",
         "这是你安装的 PowerShell 模块（扩展功能包），提供各种系统管理和自动化命令。\n\n看看再删\n删了的话你安装的 PowerShell 自定义命令会失效。如果你不用 PowerShell 做自动化脚本，可以清理。"),

        # ===== Windows SDK =====
        (f"C:\\Program Files (x86)\\Windows Kits\\10\\Debuggers\\x64\\dbgeng.dll", "dbgeng.dll", "150 MB", 157286400, False, "yellow",
         "这是 Windows SDK 的调试引擎，开发 Windows 应用和驱动时需要的调试工具。\n\n看看再删\n属于 Windows SDK 的核心组件。如果不做 Windows 开发了，通过控制面板卸载 Windows SDK。"),

        # ===== Yarn v2+ (PnP) =====
        (f"{U}\\Projects\\webapp\\.yarn\\cache", "cache", "500 MB", 524288000, True, "green",
         "这是 Yarn（前端包管理器）在项目内的依赖缓存，用于零安装模式（Plug'n'Play）。\n\n放心删\n纯缓存，删了后运行 yarn install 会重新生成。"),

        # ===== pnpm =====
        (f"{U}\\AppData\\Local\\pnpm\\store\\v3", "v3", "2.0 GB", 2147483648, True, "green",
         "这是 pnpm（高效的 Node.js 包管理器）的全局存储，所有项目共享同一份依赖文件通过硬链接节省空间。\n\n放心删\n删了的话 pnpm 会在下次安装时重新下载依赖。已有项目可能需要重新 pnpm install。"),

        # ===== Electron apps — general =====
        (f"{U}\\AppData\\Local\\electron-builder\\Cache", "Cache", "500 MB", 524288000, True, "green",
         "这是 Electron Builder 的构建缓存，之前打包 Electron 桌面应用时下载的运行时和工具。\n\n放心删\n纯缓存，删了下次打包时会重新下载。"),

        # ===== Anaconda Navigator =====
        (f"{U}\\anaconda3\\pkgs\\qt-5.15.9-h1a7d735_0.conda", "qt-5.15.9-h1a7d735_0.conda", "250 MB", 262144000, False, "green",
         "这是 Anaconda 的 Qt 图形界面库安装包缓存，之前安装数据可视化工具时下载的。\n\n放心删\n纯缓存，删了不影响已安装的环境。可以用 conda clean --all 清理。"),

        # ===== pip wheel cache =====
        (f"{U}\\AppData\\Local\\pip\\cache\\wheels", "wheels", "800 MB", 838860800, True, "green",
         "这是 pip 构建的 Python 包 wheel 缓存，加速重复安装同一个包。\n\n放心删\n纯缓存，可以用 pip cache purge 一键清理。"),

        # ===== PyInstaller =====
        (f"{U}\\Projects\\myapp\\dist\\myapp.exe", "myapp.exe", "150 MB", 157286400, False, "yellow",
         "这是用 PyInstaller 打包的 Python 程序，把 Python 脚本和所有依赖打包成一个独立 exe。\n\n看看再删\n这是你打包的程序成品。如果你不需要这个程序了，可以删。源代码不受影响。"),

        # ===== Wireshark =====
        (f"C:\\Program Files\\Wireshark\\Wireshark.exe", "Wireshark.exe", "120 MB", 125829120, False, "yellow",
         "这是 Wireshark（网络抓包分析工具）的主程序文件，网络调试和安全分析用的专业工具。\n\n看看再删\n删了的话 Wireshark 无法启动。如果不做网络分析了，通过控制面板卸载。"),

        # ===== AutoCAD =====
        (f"C:\\Program Files\\Autodesk\\AutoCAD 2024\\acad.exe", "acad.exe", "200 MB", 209715200, False, "yellow",
         "这是 AutoCAD 2024 的主程序文件，Autodesk 的专业工程制图软件。\n\n看看再删\n删了的话 AutoCAD 无法启动。如果不用了，通过 Autodesk 卸载工具或控制面板卸载。"),

        # ===== MATLAB =====
        (f"C:\\Program Files\\MATLAB\\R2024a\\bin\\matlab.exe", "matlab.exe", "180 MB", 188743680, False, "yellow",
         "这是 MATLAB（MathWorks 的科学计算软件）的主程序文件。\n\n看看再删\n删了的话 MATLAB 无法启动。如果不做科学计算了，通过控制面板卸载。注意 MATLAB 完整安装通常超过 20GB。"),

        # ===== 迅雷 =====
        (f"C:\\Program Files (x86)\\Thunder Network\\Thunder\\Program\\Thunder.exe", "Thunder.exe", "130 MB", 136314880, False, "yellow",
         "这是迅雷（下载工具）的主程序文件。\n\n看看再删\n删了的话迅雷无法启动。如果不用了，通过控制面板卸载。"),
        (f"{U}\\AppData\\Roaming\\Thunder Network\\Thunder\\Temp", "Temp", "1.0 GB", 1073741824, True, "green",
         "这是迅雷的下载临时文件和缓存。\n\n放心删\n已完成的下载不受影响。正在下载的任务会中断，需要重新开始。"),

        # ===== 360 =====
        (f"C:\\Program Files (x86)\\360\\360Safe\\deepscan\\CloudScan.dll", "CloudScan.dll", "150 MB", 157286400, False, "yellow",
         "这是 360 安全卫士的云查杀引擎，负责扫描和识别恶意软件。\n\n看看再删\n删了的话 360 的杀毒扫描功能会失效。如果你不用 360，建议通过控制面板完整卸载，不要单独删文件。"),

        # ===== 搜狗输入法 =====
        (f"C:\\Program Files (x86)\\SogouInput\\13.5.0.8222\\SogouCloud.dll", "SogouCloud.dll", "120 MB", 125829120, False, "yellow",
         "这是搜狗输入法的云词库和智能联想引擎。\n\n看看再删\n删了的话搜狗输入法的云联想功能会失效，但基本打字不受影响。如果不用搜狗输入法了，通过控制面板卸载。"),

        # ===== 有道词典 =====
        (f"{U}\\AppData\\Local\\Youdao\\dict\\offline\\ecdict.dat", "ecdict.dat", "300 MB", 314572800, False, "yellow",
         "这是有道词典的离线词库数据，让你不联网也能查单词。\n\n看看再删\n删了的话有道词典的离线查词功能会失效，但在线查词不受影响。如果不用有道词典了，通过控制面板卸载。"),

        # ===== WeChat file storage =====
        (f"{U}\\Documents\\WeChat Files\\wxid_abc123\\FileStorage\\File\\2024-01", "2024-01", "2.0 GB", 2147483648, True, "yellow",
         "这是微信电脑版保存的聊天文件（2024年1月），包括别人发给你的文档、图片和视频。\n\n看看再删\n这些是你的微信聊天附件，删了就没了。建议先确认没有重要文件再删除。可以在微信设置→文件管理里查看。"),
        (f"{U}\\Documents\\WeChat Files\\wxid_abc123\\FileStorage\\Cache", "Cache", "1.5 GB", 1610612736, True, "green",
         "这是微信电脑版的缓存文件，浏览过的图片和视频的预览副本。\n\n放心删\n纯缓存，删了不影响聊天记录。原始文件仍在 FileStorage\\File 里。可以在微信设置里清理。"),

        # ===== QQ files =====
        (f"{U}\\Documents\\Tencent Files\\12345678\\FileRecv", "FileRecv", "3.0 GB", 3221225472, True, "yellow",
         "这是 QQ 接收的文件存储目录，别人通过 QQ 发给你的所有文件都保存在这里。\n\n看看再删\n这些是你收到的文件，删了就没了。建议先把重要文件移到其他位置再清理。"),

        # ===== System processes =====
        (f"C:\\Windows\\System32\\ntoskrnl.exe", "ntoskrnl.exe", "120 MB", 125829120, False, "red",
         "这是 Windows 操作系统的内核文件，系统最核心的组件，负责内存管理、进程调度等底层功能。\n\n千万别删\n删了系统会立即无法运行，必须重装 Windows。这是整个操作系统最关键的文件之一。"),
        (f"C:\\Windows\\System32\\drivers\\acpi.sys", "acpi.sys", "150 MB", 157286400, False, "red",
         "这是 Windows 的 ACPI 电源管理驱动，负责电脑的开关机、休眠、电源管理等功能。\n\n千万别删\n属于系统核心驱动，删了可能导致电脑无法正常开关机或蓝屏。"),

        # ===== EFI partition =====
        (f"C:\\Windows\\Boot\\EFI\\bootmgfw.efi", "bootmgfw.efi", "150 MB", 157286400, False, "red",
         "这是 Windows 的 UEFI 启动引导文件，电脑开机时最先加载的文件之一。\n\n千万别删\n删了的话电脑会无法开机，需要用 Windows 安装盘修复。绝对不要碰这个文件。"),

        # ===== Windows Prefetch =====
        (f"C:\\Windows\\Prefetch", "Prefetch", "200 MB", 209715200, True, "green",
         "这是 Windows 的预读取缓存，系统监测你常用的程序后缓存启动数据，加快下次启动速度。\n\n放心删\n删了不影响任何功能，只是程序首次启动会稍慢。系统会自动重新生成。可以通过「磁盘清理」安全处理。"),

        # ===== Icon cache =====
        (f"{U}\\AppData\\Local\\Microsoft\\Windows\\Explorer\\iconcache_256.db", "iconcache_256.db", "150 MB", 157286400, False, "green",
         "这是 Windows 资源管理器的图标缓存，存储了文件和文件夹的图标预览数据。\n\n放心删\n删了后桌面图标可能暂时显示为空白，重启后系统会自动重建。"),

        # ===== Office temp =====
        (f"{U}\\AppData\\Local\\Microsoft\\Office\\16.0\\OfficeFileCache", "OfficeFileCache", "300 MB", 314572800, True, "green",
         "这是 Microsoft Office 的文件缓存，打开过的 OneDrive/SharePoint 文档的本地副本。\n\n放心删\n纯缓存，删了不影响已保存的文档。下次打开云端文档时会重新下载。"),

        # ===== GIMP =====
        (f"C:\\Program Files\\GIMP 2\\bin\\gimp-2.10.exe", "gimp-2.10.exe", "130 MB", 136314880, False, "yellow",
         "这是 GIMP（开源图像编辑软件，类似 Photoshop）的主程序文件。\n\n看看再删\n删了的话 GIMP 无法启动。如果不用了，通过控制面板卸载。"),

        # ===== Krita =====
        (f"C:\\Program Files\\Krita (x64)\\bin\\krita.exe", "krita.exe", "150 MB", 157286400, False, "yellow",
         "这是 Krita（开源数字绘画软件）的主程序文件，专业数字绘画和插画工具。\n\n看看再删\n删了的话 Krita 无法启动。如果不用了，通过控制面板卸载。"),

        # ===== Audacity =====
        (f"C:\\Program Files\\Audacity\\Audacity.exe", "Audacity.exe", "120 MB", 125829120, False, "yellow",
         "这是 Audacity（开源音频编辑软件）的主程序文件。\n\n看看再删\n删了的话 Audacity 无法启动。如果不做音频编辑了，通过控制面板卸载。"),

        # ===== HandBrake =====
        (f"C:\\Program Files\\HandBrake\\HandBrake.exe", "HandBrake.exe", "110 MB", 115343360, False, "yellow",
         "这是 HandBrake（开源视频转码工具）的主程序文件。\n\n看看再删\n删了的话 HandBrake 无法启动。如果不做视频转码了，通过控制面板卸载。"),

        # ===== Zoom =====
        (f"{U}\\AppData\\Roaming\\Zoom\\bin\\Zoom.exe", "Zoom.exe", "160 MB", 167772160, False, "yellow",
         "这是 Zoom（视频会议软件）的主程序文件。\n\n看看再删\n删了的话 Zoom 无法启动，无法参加在线会议。如果不用了，通过控制面板卸载。"),

        # ===== Node modules (project level) =====
        (f"{U}\\Projects\\my-website\\node_modules", "node_modules", "1.5 GB", 1610612736, True, "green",
         "这是前端项目「my-website」安装的 npm 依赖包目录，包含项目运行和构建所需的所有第三方库。\n\n放心删\n删了后在项目目录运行 npm install 就能重新安装。不影响源代码。node_modules 往往是前端项目中最占空间的文件夹。"),

        # ===== Next.js / Nuxt build cache =====
        (f"{U}\\Projects\\my-website\\.next\\cache", "cache", "500 MB", 524288000, True, "green",
         "这是 Next.js 前端框架的构建缓存，加速开发时的热更新和编译。\n\n放心删\n纯缓存，删了后下次 npm run dev 时会重新构建。不影响源代码和最终部署。"),

        # ===== Vercel CLI cache =====
        (f"{U}\\AppData\\Local\\com.vercel.cli", "com.vercel.cli", "300 MB", 314572800, True, "green",
         "这是 Vercel（前端部署平台）CLI 工具的本地缓存。\n\n放心删\n纯缓存，删了不影响已部署的项目。"),

        # ===== Hugging Face (additional models) =====
        (f"{U}\\.cache\\huggingface\\hub\\models--openai--whisper-large-v3\\snapshots\\abc123\\model.safetensors", "model.safetensors", "3.1 GB", 3328599654, False, "yellow",
         "这是 HuggingFace 缓存的 AI 模型权重文件（openai/whisper-large-v3），OpenAI 的语音识别大模型，能把语音转成文字。\n\n看看再删\n删了的话下次代码里加载这个模型时需要重新下载。如果你不再用 Whisper 做语音识别了，可以删除。也可以用 huggingface-cli delete-cache 命令统一管理。"),
        (f"{U}\\.cache\\huggingface\\hub\\models--stabilityai--stable-diffusion-xl-base-1.0\\snapshots\\def456\\unet\\diffusion_pytorch_model.safetensors", "diffusion_pytorch_model.safetensors", "5.1 GB", 5476083098, False, "yellow",
         "这是 HuggingFace 缓存的 Stable Diffusion XL 模型（AI 画图模型），用于根据文字描述生成图片。\n\n看看再删\n删了的话下次运行 SDXL 时需要重新下载 5GB 的模型。如果你不做 AI 画图了，可以删除。"),
        (f"{U}\\.cache\\huggingface\\hub\\models--meta-llama--Llama-2-7b-chat-hf\\snapshots\\ghi789\\model-00001-of-00002.safetensors", "model-00001-of-00002.safetensors", "4.8 GB", 5153960755, False, "yellow",
         "这是 HuggingFace 缓存的 Meta LLaMA 2 7B 对话模型权重，一个开源的大语言模型。\n\n看看再删\n删了的话下次加载 LLaMA 2 时需要重新下载。如果你不再用 LLaMA 做本地 AI 对话，可以删除。"),

        # ===== Ollama additional models =====
        (f"{U}\\.ollama\\models\\blobs\\sha256-1234567890abcdef", "sha256-1234567890abcdef", "4.7 GB", 5046586573, False, "yellow",
         "这是 Ollama 下载的 AI 大模型权重文件，你用 ollama pull 下载的本地 AI 对话模型。\n\n看看再删\n删了的话对应的 AI 模型会丢失，需要重新下载。可以用 ollama list 查看有哪些模型，用 ollama rm 删除不需要的。"),

        # ===== ComfyUI / Stable Diffusion WebUI =====
        (f"{U}\\stable-diffusion-webui\\models\\Stable-diffusion\\v1-5-pruned-emaonly.safetensors", "v1-5-pruned-emaonly.safetensors", "4.3 GB", 4615849984, False, "yellow",
         "这是 Stable Diffusion WebUI 的基础模型文件，用于 AI 画图的核心模型权重。\n\n看看再删\n删了的话 SD WebUI 无法生成图片，需要重新下载模型。如果你不做 AI 画图了，可以删除整个 stable-diffusion-webui 文件夹。"),
        (f"{U}\\stable-diffusion-webui\\outputs\\txt2img-images", "txt2img-images", "5.0 GB", 5368709120, True, "green",
         "这是 Stable Diffusion WebUI 生成的 AI 画图成品输出目录。\n\n放心删\n这些是你生成的图片，删了就没了。确认不需要后可以清理释放空间。"),

        # ===== LM Studio =====
        (f"{U}\\.cache\\lm-studio\\models\\TheBloke\\Mistral-7B-Instruct-v0.2-GGUF\\mistral-7b-instruct-v0.2.Q4_K_M.gguf", "mistral-7b-instruct-v0.2.Q4_K_M.gguf", "4.4 GB", 4724464025, False, "yellow",
         "这是 LM Studio（本地 AI 大模型运行工具）下载的 Mistral 7B 模型，一个开源的 AI 对话模型。\n\n看看再删\n删了的话 LM Studio 里这个模型会消失，需要重新下载。如果你不用 LM Studio 了，可以直接卸载。"),

        # ===== Jan AI =====
        (f"{U}\\jan\\models\\mistral-ins-7b-q4\\model-00001-of-00002.gguf", "model-00001-of-00002.gguf", "4.1 GB", 4402341478, False, "yellow",
         "这是 Jan（本地 AI 对话工具）下载的 Mistral 7B 模型文件。\n\n看看再删\n删了的话 Jan 里这个模型无法使用。如果你不用 Jan 了，可以删除整个 jan 文件夹。"),

        # ===== Low confidence: truly unknown files =====
        (f"{U}\\AppData\\Local\\Temp\\setup_12345\\data1.cab", "data1.cab", "800 MB", 838860800, False, "green",
         "这是某个软件安装程序解压的临时文件（CAB 压缩包），安装完成后没有清理掉的残留。\n\n放心删\n如果对应的软件已经安装完成，这就是安装残留，可以放心删除。"),
        (f"{U}\\AppData\\Local\\{{8A69D345-D564-463C-AFF1-A69D9E530F96}}", "{8A69D345-D564-463C-AFF1-A69D9E530F96}", "200 MB", 209715200, True, "yellow",
         "这个文件夹名是一串 GUID，通常是某个软件自动创建的更新或缓存目录。这个特定的 GUID 属于 Google Chrome 更新服务。\n\n看看再删\n这是 Chrome 的更新缓存目录。如果你还在用 Chrome，建议保留。不用 Chrome 了可以删。"),
        (f"C:\\ProgramData\\Package Cache", "Package Cache", "2.0 GB", 2147483648, True, "yellow",
         "这是 Windows 的软件安装包全局缓存目录，Visual Studio、.NET 等微软产品的安装包都缓存在这里，用于修复和卸载。\n\n看看再删\n不建议整个删除，否则已安装的软件可能无法修复或卸载。可以先卸载不用的软件，对应的缓存会自动清理。"),
        # ===== Chrome — more variants =====
        (f"{U}\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Code Cache\\js", "js", "400 MB", 419430400, True, "green",
         "这是 Chrome 浏览器的 JavaScript 代码缓存，保存了网站脚本的编译结果，加速网页加载。\n\n放心删\n纯缓存，删了不影响 Chrome 功能。可以在 Chrome 设置→清除浏览数据里清理。"),
        (f"{U}\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Local Storage", "Local Storage", "200 MB", 209715200, True, "yellow",
         "这是 Chrome 浏览器里各网站存储的本地数据（类似 Cookie 但容量更大），比如网站的登录状态、个性化设置等。\n\n看看再删\n删了的话某些网站需要重新登录或重新设置偏好。聊天类网站可能丢失未同步的草稿。"),
        (f"{U}\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\GPUCache", "GPUCache", "150 MB", 157286400, True, "green",
         "这是 Chrome 浏览器的 GPU 渲染缓存，加速网页图形显示用的。\n\n放心删\n纯缓存，删了 Chrome 会自动重建。"),
        (f"{U}\\AppData\\Local\\Google\\Chrome\\User Data\\SwReporter", "SwReporter", "120 MB", 125829120, True, "green",
         "这是 Chrome 的软件报告工具缓存，Chrome 用它来检测电脑上是否有影响浏览器的恶意软件。\n\n放心删\n删了不影响 Chrome 浏览功能。Chrome 下次需要时会重新下载。"),

        # ===== Edge — more variants =====
        (f"{U}\\AppData\\Local\\Microsoft\\Edge\\User Data\\Default\\Cache\\Cache_Data", "Cache_Data", "600 MB", 629145600, True, "green",
         "这是 Microsoft Edge 浏览器的网页缓存，保存了浏览过的网页资源副本。\n\n放心删\n纯缓存，删了不影响 Edge 功能。可以在 Edge 设置→隐私→清除浏览数据里清理。"),
        (f"{U}\\AppData\\Local\\Microsoft\\Edge\\User Data\\Default\\Code Cache", "Code Cache", "300 MB", 314572800, True, "green",
         "这是 Edge 浏览器的 JavaScript 代码缓存。\n\n放心删\n纯缓存，删了 Edge 会自动重建。"),
        (f"{U}\\AppData\\Local\\Microsoft\\Edge\\User Data\\Default\\Service Worker\\CacheStorage", "CacheStorage", "250 MB", 262144000, True, "green",
         "这是 Edge 浏览器里网站 Service Worker 的离线缓存。\n\n放心删\n纯缓存，网站下次打开时会自动重建。"),

        # ===== Steam — more variants =====
        (f"C:\\Program Files (x86)\\Steam\\steamapps\\shadercache", "shadercache", "1.0 GB", 1073741824, True, "green",
         "这是 Steam 游戏的着色器预编译缓存，GPU 编译游戏图形效果后缓存在这里，加快游戏启动。\n\n放心删\n纯缓存，删了下次启动游戏时需要重新编译着色器，加载会稍慢一次。"),
        (f"C:\\Program Files (x86)\\Steam\\steamapps\\workshop\\content\\730", "730", "2.0 GB", 2147483648, True, "yellow",
         "这是 Steam 创意工坊下载的游戏模组（CS:GO 的地图、皮肤等），你订阅的社区内容都存在这里。\n\n看看再删\n删了的话你订阅的创意工坊内容会消失，但可以在 Steam 里重新下载。如果不玩这个游戏了，取消订阅后删除。"),
        (f"C:\\Program Files (x86)\\Steam\\steamapps\\common\\Cyberpunk 2077\\archive\\pc\\content", "content", "30.0 GB", 32212254720, True, "yellow",
         "这是 Steam 游戏《赛博朋克 2077》的核心游戏资源，包含整个夜之城的数据。\n\n看看再删\n删了的话游戏无法运行。这个游戏完整安装约 70GB，如果不玩了，在 Steam 库里卸载。"),

        # ===== 微信 — more variants =====
        (f"{U}\\Documents\\WeChat Files\\wxid_abc123\\FileStorage\\Video", "Video", "3.0 GB", 3221225472, True, "yellow",
         "这是微信电脑版保存的聊天视频文件，别人在聊天中发给你的视频都存在这里。\n\n看看再删\n这些是你的聊天视频附件，删了就没了。建议先确认没有重要视频再删除。"),
        (f"{U}\\Documents\\WeChat Files\\wxid_abc123\\FileStorage\\Image", "Image", "1.5 GB", 1610612736, True, "yellow",
         "这是微信电脑版保存的聊天原始图片，收发的高清图片都存在这里。\n\n看看再删\n删了的话微信里以前的图片会变成缩略图（原图丢失）。确认不需要后可以清理。"),
        (f"{U}\\Documents\\WeChat Files\\All Users\\MicroMsg\\Applet", "Applet", "500 MB", 524288000, True, "green",
         "这是微信小程序的缓存目录，你打开过的小程序的临时数据。\n\n放心删\n纯缓存，删了不影响微信功能。小程序下次打开时会重新加载。"),

        # ===== QQ — more variants =====
        (f"{U}\\AppData\\Roaming\\Tencent\\QQ\\Cache\\File", "File", "800 MB", 838860800, True, "green",
         "这是 QQ 的文件缓存，保存了聊天中收发的文件本地副本。\n\n放心删\n纯缓存，原始文件还在 QQ 的文件管理器里。可以在 QQ 设置→文件管理里查看和清理。"),
        (f"C:\\Program Files\\Tencent\\QQNT\\resources\\app\\versions", "versions", "500 MB", 524288000, True, "yellow",
         "这是 QQ 桌面版的历史版本文件，QQ 自动更新时保留的旧版本。\n\n看看再删\n只有当前版本是必需的，旧版本理论上可以清理。但建议让 QQ 自己管理更新。"),

        # ===== 钉钉 — more variants =====
        (f"{U}\\AppData\\Roaming\\DingTalk\\media", "media", "500 MB", 524288000, True, "green",
         "这是钉钉的聊天媒体缓存，查看过的图片和视频的本地副本。\n\n放心删\n纯缓存，删了不影响聊天记录。"),
        (f"{U}\\AppData\\Roaming\\DingTalk\\log", "log", "200 MB", 209715200, True, "green",
         "这是钉钉的运行日志文件。\n\n放心删\n纯日志，删了不影响钉钉功能。"),

        # ===== 腾讯视频 =====
        (f"{U}\\AppData\\Roaming\\Tencent\\QLive\\Cache", "Cache", "2.0 GB", 2147483648, True, "green",
         "这是腾讯视频的本地视频缓存，看过的视频会缓存在这里。\n\n放心删\n纯缓存，删了不影响腾讯视频功能。"),

        # ===== 爱奇艺 =====
        (f"{U}\\AppData\\Roaming\\iQIYI Video\\cache\\video", "video", "1.5 GB", 1610612736, True, "green",
         "这是爱奇艺的本地视频缓存。\n\n放心删\n纯缓存，删了下次看视频时重新在线加载。"),

        # ===== 百度输入法 =====
        (f"{U}\\AppData\\Roaming\\Baidu\\BaiduPinyin\\skins", "skins", "200 MB", 209715200, True, "green",
         "这是百度输入法下载的皮肤包缓存。\n\n放心删\n删了的话自定义皮肤会消失，但默认皮肤不受影响。可以在百度输入法里重新下载。"),

        # ===== WPS — more =====
        (f"{U}\\AppData\\Local\\Kingsoft\\WPS Office\\12.1.0\\office6\\backup\\AllUsers", "AllUsers", "300 MB", 314572800, True, "yellow",
         "这是 WPS Office 的文档自动备份目录，保存了你编辑文档时的定期备份。\n\n看看再删\n删了的话之前的文档备份会丢失，无法恢复到旧版本。如果你的文档都已经正常保存了，可以清理旧备份。"),

        # ===== Figma — cache =====
        (f"{U}\\AppData\\Roaming\\Figma\\Cache\\Cache_Data", "Cache_Data", "300 MB", 314572800, True, "green",
         "这是 Figma 桌面版的界面缓存。\n\n放心删\n纯缓存，删了不影响 Figma 功能，设计文件都在云端。"),

        # ===== AutoCAD — cache =====
        (f"{U}\\AppData\\Local\\Autodesk\\AutoCAD 2024\\R24.3\\temp", "temp", "400 MB", 419430400, True, "green",
         "这是 AutoCAD 的临时文件目录，编辑图纸时产生的中间数据。\n\n放心删\n如果 AutoCAD 已经关闭，这是残留临时文件。正在使用 AutoCAD 时不要删。"),

        # ===== 360 浏览器 =====
        (f"{U}\\AppData\\Local\\360Chrome\\Chrome\\User Data\\Default\\Cache", "Cache", "500 MB", 524288000, True, "green",
         "这是 360 安全浏览器的网页缓存。\n\n放心删\n纯缓存，删了不影响 360 浏览器功能。"),

        # ===== 2345浏览器 =====
        (f"{U}\\AppData\\Local\\2345Explorer\\User Data\\Default\\Cache", "Cache", "400 MB", 419430400, True, "green",
         "这是 2345 浏览器的网页缓存。\n\n放心删\n纯缓存，删了不影响浏览器功能。"),

        # ===== 快手 =====
        (f"{U}\\AppData\\Local\\Kuaishou\\Cache", "Cache", "500 MB", 524288000, True, "green",
         "这是快手电脑版的视频缓存。\n\n放心删\n纯缓存，删了下次看视频重新加载。"),

        # ===== 抖音 =====
        (f"{U}\\AppData\\Local\\Douyin\\cache", "cache", "800 MB", 838860800, True, "green",
         "这是抖音电脑版的视频缓存，看过的视频会缓存在本地。\n\n放心删\n纯缓存，删了不影响抖音功能。"),

        # ===== 印象笔记 =====
        (f"{U}\\AppData\\Local\\Yinxiang\\Evernote\\Databases", "Databases", "500 MB", 524288000, True, "yellow",
         "这是印象笔记的本地笔记数据库，保存了你的所有笔记内容的本地副本。\n\n看看再删\n删了的话本地笔记会丢失，需要重新从云端同步。如果你有印象笔记账号，重新登录可以恢复。"),

        # ===== Everything (search tool) =====
        (f"C:\\Program Files\\Everything\\Everything.db", "Everything.db", "200 MB", 209715200, False, "yellow",
         "这是 Everything（极速文件搜索工具）的文件名索引数据库，记录了硬盘上所有文件的位置信息。\n\n看看再删\n删了的话 Everything 需要重新建立索引（几秒钟即可完成）。不影响任何文件的安全。"),

        # ===== Potplayer =====
        (f"C:\\Program Files\\DAUM\\PotPlayer\\PotPlayerMini64.exe", "PotPlayerMini64.exe", "130 MB", 136314880, False, "yellow",
         "这是 PotPlayer（韩国 DAUM 公司的视频播放器）的主程序文件，功能强大的多媒体播放器。\n\n看看再删\n删了的话 PotPlayer 无法启动。如果不用了，通过控制面板卸载。"),

        # ===== 向日葵远程 =====
        (f"C:\\Program Files\\Oray\\SunLogin\\SunloginClient\\SunloginClient.exe", "SunloginClient.exe", "120 MB", 125829120, False, "yellow",
         "这是向日葵远程控制软件的主程序，用于远程访问和控制其他电脑。\n\n看看再删\n删了的话远程控制功能无法使用。如果不用了，通过控制面板卸载。"),

        # ===== ToDesk =====
        (f"C:\\Program Files\\ToDesk\\ToDesk.exe", "ToDesk.exe", "150 MB", 157286400, False, "yellow",
         "这是 ToDesk 远程桌面软件的主程序文件。\n\n看看再删\n删了的话 ToDesk 无法启动。如果不用了，通过控制面板卸载。"),

        # ===== Cursor — more =====
        (f"{U}\\AppData\\Roaming\\Cursor\\User\\workspaceStorage", "workspaceStorage", "500 MB", 524288000, True, "green",
         "这是 Cursor 编辑器的工作区状态缓存，保存了每个项目的编辑器布局和标签页状态。\n\n放心删\n删了的话打开项目时标签页布局会重置，但代码文件不受影响。"),

        # ===== PyTorch hub cache =====
        (f"{U}\\.cache\\torch\\hub\\checkpoints\\resnet50-0676ba61.pth", "resnet50-0676ba61.pth", "100 MB", 104857600, False, "yellow",
         "这是 PyTorch 自动下载的 ResNet50 预训练模型，做图像识别相关的深度学习代码时自动缓存的。\n\n看看再删\n删了的话下次运行相关代码时会重新下载。如果你不做图像识别了，可以删除整个 torch/hub/checkpoints 文件夹。"),

        # ===== Hugging Face — tokenizer =====
        (f"{U}\\.cache\\huggingface\\hub\\models--bert-base-chinese\\snapshots\\abc123\\vocab.txt", "vocab.txt", "100 MB", 104857600, False, "yellow",
         "这是 HuggingFace 缓存的中文 BERT 模型词表文件，中文自然语言处理任务常用的基础模型。\n\n看看再删\n删了的话下次加载 BERT 中文模型时需要重新下载。如果你不再做中文 NLP 了，可以删除。"),

        # ===== Copilot / AI assistants =====
        (f"{U}\\AppData\\Local\\Microsoft\\Windows\\INetCache\\CopilotCache", "CopilotCache", "200 MB", 209715200, True, "green",
         "这是 Windows Copilot（微软 AI 助手）的本地缓存。\n\n放心删\n纯缓存，删了不影响 Copilot 功能。"),

        # ===== Windows Update logs =====
        (f"C:\\Windows\\Logs\\CBS\\CBS.log", "CBS.log", "200 MB", 209715200, False, "green",
         "这是 Windows 组件服务（CBS）的日志文件，记录了 Windows Update 安装和组件修复的详细过程。\n\n放心删\n纯日志，删了不影响系统功能。系统下次更新时会自动创建新日志。"),
        (f"C:\\Windows\\Logs\\DISM\\dism.log", "dism.log", "100 MB", 104857600, False, "green",
         "这是 DISM（系统映像管理工具）的操作日志。\n\n放心删\n纯日志，删了不影响系统功能。"),

        # ===== Windows delivery optimization =====
        (f"{U}\\AppData\\Local\\DeliveryOptimization\\Cache", "Cache", "500 MB", 524288000, True, "green",
         "这是 Windows 传递优化的缓存，系统更新下载后缓存在这里，方便局域网内其他电脑共享下载。\n\n放心删\n删了不影响系统更新功能。可以在设置→Windows 更新→传递优化里管理。"),

        # ===== Windows search index =====
        (f"C:\\ProgramData\\Microsoft\\Search\\Data\\Applications\\Windows\\Windows.edb", "Windows.edb", "1.0 GB", 1073741824, False, "yellow",
         "这是 Windows 搜索索引数据库，记录了硬盘上所有文件的内容和位置，让你在开始菜单和资源管理器里快速搜索文件。\n\n看看再删\n删了的话 Windows 搜索功能会暂时失效，需要重新建立索引（可能需要几小时）。如果搜索索引太大，可以在「索引选项」里缩小索引范围。"),

        # ===== Hyper-V checkpoint =====
        (f"C:\\ProgramData\\Microsoft\\Windows\\Hyper-V\\Snapshots", "Snapshots", "3.0 GB", 3221225472, True, "yellow",
         "这是 Hyper-V 虚拟机的检查点（快照）文件，保存了虚拟机在某个时间点的完整状态。\n\n看看再删\n删了的话对应的虚拟机检查点会丢失，无法恢复到那个时间点。如果你不需要回滚虚拟机状态，可以在 Hyper-V 管理器里删除检查点。"),

        # ===== Notion — local data =====
        (f"{U}\\AppData\\Roaming\\Notion\\notion.db", "notion.db", "200 MB", 209715200, False, "yellow",
         "这是 Notion 桌面版的本地数据库，缓存了你的笔记页面方便离线查看。\n\n看看再删\n删了的话 Notion 需要重新从云端同步所有数据，首次打开会比较慢。你的数据都在云端，不会丢失。"),

        # ===== Obsidian =====
        (f"{U}\\Documents\\ObsidianVault\\.obsidian\\plugins", "plugins", "200 MB", 209715200, True, "yellow",
         "这是 Obsidian（本地笔记软件）安装的社区插件目录。\n\n看看再删\n删了的话所有 Obsidian 插件会失效，需要重新在插件市场安装。你的笔记文件不受影响。"),

        # ===== XMind =====
        (f"C:\\Program Files\\XMind\\XMind.exe", "XMind.exe", "150 MB", 157286400, False, "yellow",
         "这是 XMind（思维导图软件）的主程序文件。\n\n看看再删\n删了的话 XMind 无法启动。如果不用了，通过控制面板卸载。"),

        # ===== Snipaste =====
        (f"{U}\\AppData\\Roaming\\Snipaste\\snipaste.png.cache", "snipaste.png.cache", "100 MB", 104857600, False, "green",
         "这是 Snipaste（截图贴图工具）的截图缓存。\n\n放心删\n纯缓存，删了不影响 Snipaste 功能。"),

        # ===== 夸克浏览器 =====
        (f"{U}\\AppData\\Local\\Quark\\User Data\\Default\\Cache", "Cache", "400 MB", 419430400, True, "green",
         "这是夸克浏览器的网页缓存。\n\n放心删\n纯缓存，删了不影响浏览器功能。"),

        # ===== Windows Font files =====
        (f"C:\\Windows\\Fonts", "Fonts", "500 MB", 524288000, True, "red",
         "这是 Windows 系统的字体文件夹，系统和所有应用显示文字都依赖这里的字体文件。\n\n千万别删\n删了会导致系统和应用界面文字显示异常甚至无法使用。如果想清理不需要的字体，在设置→个性化→字体里管理。"),

        # ===== Pip — more =====
        (f"{U}\\AppData\\Local\\pip\\cache\\http-v2", "http-v2", "1.5 GB", 1610612736, True, "green",
         "这是 pip 的 HTTP 下载缓存目录，之前 pip install 时下载的所有 Python 包原始文件。\n\n放心删\n纯缓存，删了不影响已安装的包。可以用 pip cache purge 一键清理全部。"),
        (f"{U}\\AppData\\Local\\pip\\cache\\selfcheck", "selfcheck", "100 MB", 104857600, True, "green",
         "这是 pip 的自检缓存，记录了 pip 版本检查信息。\n\n放心删\n纯缓存，完全没用。"),

        # ===== System drivers =====
        (f"C:\\Windows\\System32\\DriverStore\\FileRepository", "FileRepository", "3.0 GB", 3221225472, True, "red",
         "这是 Windows 的驱动程序仓库，系统安装过的所有硬件驱动都存在这里，包括显卡、声卡、网卡等。\n\n千万别删\n属于系统核心目录，删了会导致硬件设备无法正常工作。旧版本驱动可以用系统自带的「磁盘清理」→「设备驱动程序包」安全清理。"),

        # ===== Tencent Meeting — cache =====
        (f"{U}\\AppData\\Roaming\\Tencent\\WeMeet\\Cache", "Cache", "300 MB", 314572800, True, "green",
         "这是腾讯会议的本地缓存，保存了会议录制预览和界面资源。\n\n放心删\n纯缓存，删了不影响腾讯会议功能。"),

        # ===== Media player cache =====
        (f"{U}\\AppData\\Local\\VLC\\vlc-qt-interface.ini.lock", "vlc-qt-interface.ini.lock", "100 MB", 104857600, False, "green",
         "这是 VLC 播放器的锁定文件和临时数据。\n\n放心删\n如果 VLC 没在运行，这是残留文件，可以删除。"),

        # ===== Windows SxS cleanup =====
        (f"C:\\Windows\\WinSxS\\ManifestCache", "ManifestCache", "200 MB", 209715200, True, "red",
         "这是 Windows 组件存储的清单缓存，系统管理组件版本和依赖关系的索引。\n\n千万别删\n属于系统核心管理数据，手动删除可能导致系统更新和修复功能异常。"),

        # ===== Lenovo Vantage =====
        (f"C:\\Program Files\\Lenovo\\Lenovo Vantage Service\\LenovoVantageService.exe", "LenovoVantageService.exe", "120 MB", 125829120, False, "yellow",
         "这是联想 Vantage（联想设备管理工具）的后台服务程序，负责驱动更新和硬件设置管理。\n\n看看再删\n属于联想的设备管理服务。如果你不用 Lenovo Vantage 管理驱动更新，可以在控制面板卸载。"),

        # ===== Dell SupportAssist =====
        (f"C:\\Program Files\\Dell\\SupportAssistAgent\\bin\\SupportAssistAgent.exe", "SupportAssistAgent.exe", "130 MB", 136314880, False, "yellow",
         "这是 Dell SupportAssist（戴尔技术支持工具）的后台服务程序，负责硬件诊断和驱动更新。\n\n看看再删\n属于戴尔预装的技术支持工具。如果你不用它来管理驱动更新，可以卸载。"),

        # ===== HP Support Assistant =====
        (f"C:\\Program Files\\HP\\HP Support Framework\\HPSF.exe", "HPSF.exe", "120 MB", 125829120, False, "yellow",
         "这是 HP Support Assistant（惠普技术支持工具）的主程序，负责硬件诊断和驱动更新。\n\n看看再删\n属于惠普预装的技术支持工具。如果不用它来管理驱动更新，可以卸载。"),

        # ===== ASUS Armoury Crate =====
        (f"C:\\Program Files\\ASUS\\ARMOURY CRATE Lite Service\\ArmouryCrateLiteService.exe", "ArmouryCrateLiteService.exe", "130 MB", 136314880, False, "yellow",
         "这是华硕奥创中心（Armoury Crate）的后台服务，管理 ROG 笔记本的灯效、性能模式和硬件监控。\n\n看看再删\n属于华硕预装的硬件管理工具。如果你不需要调节灯效和性能模式，可以卸载。"),

        # ===== Realtek audio =====
        (f"C:\\Program Files\\Realtek\\Audio\\HDA\\RtkNGUI64.exe", "RtkNGUI64.exe", "120 MB", 125829120, False, "yellow",
         "这是 Realtek 声卡的音频管理界面程序，用于调节电脑声音的输入输出设置。\n\n看看再删\n删了的话 Realtek 音频控制面板无法打开，但电脑声音播放不受影响（驱动还在）。如果你不需要高级音频设置，可以保留驱动但卸载这个界面。"),

        # ===== More browser variants for generalization =====
        (f"{U}\\AppData\\Local\\Google\\Chrome\\User Data\\Profile 2\\Cache\\Cache_Data", "Cache_Data", "500 MB", 524288000, True, "green",
         "这是 Chrome 浏览器第二个配置文件的网页缓存。如果你用 Chrome 的多用户功能，每个用户有独立的缓存。\n\n放心删\n纯缓存，删了不影响 Chrome 功能。"),
        (f"{U}\\AppData\\Local\\Microsoft\\Edge\\User Data\\Default\\IndexedDB", "IndexedDB", "400 MB", 419430400, True, "yellow",
         "这是 Edge 浏览器里各网站存储的本地数据库，保存了网站的离线数据和本地存储。\n\n看看再删\n删了的话某些网站的离线功能和本地数据会丢失。Edge 使用时会自动重建。"),

        # ===== Docker — additional =====
        (f"{U}\\AppData\\Local\\Docker\\wsl\\distro\\ext4.vhdx", "ext4.vhdx", "5.0 GB", 5368709120, False, "yellow",
         "这是 Docker Desktop 的 WSL 发行版磁盘，Docker 引擎运行在这个 Linux 环境里。\n\n看看再删\n删了的话 Docker 需要重新初始化，但不影响已有的镜像和容器（那些在 data 目录下）。如果不用 Docker 了，先卸载 Docker Desktop。"),

        # ===== VS Code — more =====
        (f"{U}\\AppData\\Roaming\\Code\\logs", "logs", "300 MB", 314572800, True, "green",
         "这是 VS Code 的运行日志目录。\n\n放心删\n纯日志，删了不影响 VS Code 功能。"),
        (f"{U}\\AppData\\Roaming\\Code\\CachedData", "CachedData", "200 MB", 209715200, True, "green",
         "这是 VS Code 的字节码缓存，加速启动用的。\n\n放心删\n纯缓存，删了 VS Code 下次启动稍慢，之后恢复正常。"),
        (f"{U}\\AppData\\Roaming\\Code\\Cache\\Cache_Data", "Cache_Data", "300 MB", 314572800, True, "green",
         "这是 VS Code 的网页渲染缓存（VS Code 基于 Electron 构建）。\n\n放心删\n纯缓存，删了不影响 VS Code 功能。"),

        # ===== More game platforms =====
        (f"C:\\Program Files (x86)\\WeGame\\tgp\\gamedata", "gamedata", "500 MB", 524288000, True, "yellow",
         "这是 WeGame（腾讯游戏平台）的游戏配置和缓存数据。\n\n看看再删\n删了可能影响 WeGame 游戏的配置和进度数据。如果不用 WeGame 了，通过控制面板卸载。"),

        # ===== Windows Temp — user level =====
        (f"{U}\\AppData\\Local\\Temp", "Temp", "2.0 GB", 2147483648, True, "green",
         "这是你的用户临时文件目录，各种程序运行时产生的临时数据都放在这里。\n\n放心删\n可以放心清理，正在被使用的文件会被系统跳过。建议用「磁盘清理」工具处理，或直接删除内容（不要删 Temp 文件夹本身）。"),

        # ===== Spotify — more =====
        (f"{U}\\AppData\\Local\\Spotify\\Data", "Data", "300 MB", 314572800, True, "yellow",
         "这是 Spotify 的应用数据目录，保存了你的播放列表缓存和应用设置。\n\n看看再删\n删了的话 Spotify 需要重新登录和同步播放列表。你的账号数据在云端不会丢失。"),

        # ===== Zoom — more =====
        (f"{U}\\AppData\\Roaming\\Zoom\\data", "data", "500 MB", 524288000, True, "yellow",
         "这是 Zoom 的本地数据目录，保存了会议录制、虚拟背景和设置信息。\n\n看看再删\n删了的话本地保存的会议录制和虚拟背景会丢失。Zoom 账号设置在云端，不受影响。"),
        (f"{U}\\AppData\\Roaming\\Zoom\\data\\VirtualBkgnd_Custom", "VirtualBkgnd_Custom", "200 MB", 209715200, True, "green",
         "这是 Zoom 的自定义虚拟背景图片缓存。\n\n放心删\n删了的话你设置的自定义虚拟背景会消失，需要重新添加。"),

        # ===== Python __pycache__ =====
        (f"{U}\\Projects\\myproject\\__pycache__", "__pycache__", "100 MB", 104857600, True, "green",
         "这是 Python 的字节码缓存，Python 运行代码时自动编译生成的中间文件，加快下次启动速度。\n\n放心删\n纯缓存，删了 Python 下次运行时会自动重新编译。不影响源代码。"),

        # ===== Electron — common cache pattern =====
        (f"{U}\\AppData\\Roaming\\discord\\Cache\\Cache_Data", "Cache_Data", "400 MB", 419430400, True, "green",
         "这是 Discord 桌面版的界面缓存（基于 Electron 构建）。\n\n放心删\n纯缓存，删了不影响 Discord 功能，消息都在云端。"),
        (f"{U}\\AppData\\Roaming\\discord\\Code Cache\\js", "js", "200 MB", 209715200, True, "green",
         "这是 Discord 的 JavaScript 代码缓存，加速界面加载用的。\n\n放心删\n纯缓存，Discord 会自动重建。"),

        # ===== GitHub Desktop — more =====
        (f"{U}\\AppData\\Local\\GitHubDesktop\\app-3.3.7", "app-3.3.7", "300 MB", 314572800, True, "green",
         "这是 GitHub Desktop 的旧版本文件夹（3.3.7），当前使用的是更新的版本。\n\n放心删\n旧版本安装目录，当前版本已经更新到新的文件夹。删了不影响 GitHub Desktop 使用。"),

        # ===== iQIYI — more =====
        (f"C:\\Program Files (x86)\\iQIYI\\LStyle\\skin", "skin", "200 MB", 209715200, True, "green",
         "这是爱奇艺客户端的皮肤资源文件。\n\n放心删\n删了的话爱奇艺会恢复默认皮肤，下次打开时可以重新选择。"),

        # ===== 网易有道翻译 =====
        (f"{U}\\AppData\\Local\\Youdao\\YoudaoTranslate\\cache", "cache", "200 MB", 209715200, True, "green",
         "这是网易有道翻译的本地缓存。\n\n放心删\n纯缓存，删了不影响翻译功能。"),

        # ===== Office — OneNote cache =====
        (f"{U}\\AppData\\Local\\Microsoft\\OneNote\\16.0\\cache", "cache", "300 MB", 314572800, True, "green",
         "这是 OneNote 的本地笔记缓存，你的笔记内容的离线副本。\n\n放心删\n删了的话 OneNote 需要重新从云端同步笔记，首次打开会比较慢。你的笔记数据都在 OneDrive 上，不会丢失。"),

        # ===== Outlook cache =====
        (f"{U}\\AppData\\Local\\Microsoft\\Outlook\\abc@outlook.com.ost", "abc@outlook.com.ost", "2.0 GB", 2147483648, False, "yellow",
         "这是 Microsoft Outlook 的离线邮件缓存文件（.ost），保存了你的邮箱所有邮件的本地副本。\n\n看看再删\n删了的话 Outlook 需要重新从服务器同步所有邮件，可能需要较长时间。你的邮件在服务器上不会丢失。关闭 Outlook 后才能删除。"),

        # ===== Anaconda — different env patterns =====
        (f"{U}\\anaconda3\\envs\\tensorflow\\Lib\\site-packages\\tensorflow\\python\\_pywrap_tensorflow_internal.pyd", "_pywrap_tensorflow_internal.pyd", "700 MB", 734003200, False, "yellow",
         "这是你的 Anaconda 环境「tensorflow」里的 TensorFlow 核心运算引擎。\n\n看看再删\n删了的话这个环境里的 TensorFlow 无法使用。如果你不用这个环境了，可以用 conda env remove -n tensorflow 整个删掉。"),

        # ===== Docker — images layer cache =====
        (f"{U}\\AppData\\Local\\Docker\\wsl\\data\\overlay2", "overlay2", "8.0 GB", 8589934592, True, "yellow",
         "这是 Docker 的镜像层存储，你拉取过的所有 Docker 镜像的文件系统层都存在这里。\n\n看看再删\n不要直接删这个目录，应该用 docker system prune 命令来安全清理不用的镜像和容器。直接删可能导致 Docker 状态损坏。"),

        # ===== More unknown/hash files for robustness =====
        (f"{U}\\AppData\\Local\\Temp\\is-AB1CD.tmp\\setup.tmp", "setup.tmp", "300 MB", 314572800, False, "green",
         "这是 Inno Setup 安装程序留下的临时文件（很多 Windows 软件用的安装工具），安装完成后没有清理掉的残留。\n\n放心删\n安装完成后的临时残留，可以放心删除。"),
        (f"{U}\\AppData\\Local\\Temp\\chocolatey\\downloads", "downloads", "500 MB", 524288000, True, "green",
         "这是 Chocolatey（Windows 包管理器）的下载缓存，安装软件时下载的安装包。\n\n放心删\n纯缓存，删了不影响已安装的软件。"),
        (f"{U}\\AppData\\Local\\Temp\\go-build", "go-build", "500 MB", 524288000, True, "green",
         "这是 Go 语言的编译缓存，go build 编译时的中间产物。\n\n放心删\n纯缓存，删了下次编译时会重新生成。可以用 go clean -cache 清理。"),

        # ===== Adobe Creative Cloud =====
        (f"C:\\Program Files\\Adobe\\Adobe Creative Cloud\\ACC\\Creative Cloud.exe", "Creative Cloud.exe", "150 MB", 157286400, False, "yellow",
         "这是 Adobe Creative Cloud 的主程序，管理 Photoshop、Premiere 等 Adobe 软件的安装和更新。\n\n看看再删\n删了的话无法管理和更新 Adobe 软件。如果不用 Adobe 产品了，通过 Adobe Creative Cloud Cleaner Tool 完整卸载。"),
        (f"{U}\\AppData\\Local\\Adobe\\CoreSync\\CoreSync.core.db", "CoreSync.core.db", "200 MB", 209715200, False, "yellow",
         "这是 Adobe Creative Cloud 的文件同步数据库，管理 Adobe 云存储的文件同步。\n\n看看再删\n删了的话 Adobe 云同步需要重新建立索引。你的云端文件不会丢失。"),

        # ===== WeChat desktop — multiple accounts =====
        (f"{U}\\Documents\\WeChat Files\\All Users\\config", "config", "100 MB", 104857600, True, "yellow",
         "这是微信电脑版的全局配置数据，保存了登录信息和通用设置。\n\n看看再删\n删了的话微信需要重新扫码登录。聊天记录不受影响（在各账号目录下）。"),

        # ===== Microsoft Store apps cache =====
        (f"{U}\\AppData\\Local\\Packages\\Microsoft.WindowsStore_8wekyb3d8bbwe\\LocalCache", "LocalCache", "300 MB", 314572800, True, "green",
         "这是 Microsoft Store（应用商店）的本地缓存。\n\n放心删\n纯缓存，删了不影响已安装的应用。应用商店下次打开时会重新加载。"),

        # ===== Xbox Game Pass =====
        (f"C:\\Program Files\\WindowsApps\\Microsoft.GamingApp_2401.1001.6.0_x64__8wekyb3d8bbwe", "Microsoft.GamingApp_2401.1001.6.0_x64__8wekyb3d8bbwe", "300 MB", 314572800, True, "yellow",
         "这是 Xbox 应用（微软游戏平台）的安装目录，Game Pass 订阅玩游戏需要它。\n\n看看再删\n属于 Windows 应用商店管理的应用，不建议手动删文件。如果不用 Xbox Game Pass，可以在设置→应用里卸载。"),

        # ===== Brave — more =====
        (f"{U}\\AppData\\Local\\BraveSoftware\\Brave-Browser\\User Data\\Default\\Local Storage", "Local Storage", "150 MB", 157286400, True, "yellow",
         "这是 Brave 浏览器里各网站存储的本地数据。\n\n看看再删\n删了的话某些网站需要重新登录。"),

        # ===== WeChat — voice =====
        (f"{U}\\Documents\\WeChat Files\\wxid_abc123\\FileStorage\\Voice", "Voice", "500 MB", 524288000, True, "yellow",
         "这是微信电脑版保存的语音消息文件。\n\n看看再删\n删了的话之前的语音消息无法再播放。确认不需要后可以清理。"),

        # ===== Tencent — common libs =====
        (f"C:\\Program Files\\Common Files\\Tencent\\QQBrowser\\QQBrowserHost.exe", "QQBrowserHost.exe", "130 MB", 136314880, False, "yellow",
         "这是 QQ 浏览器的后台服务程序，腾讯预装或捆绑安装的浏览器。\n\n看看再删\n如果你不用 QQ 浏览器，可以通过控制面板卸载。不要单独删文件。"),

        # ===== Node.js — global =====
        (f"C:\\Program Files\\nodejs\\node.exe", "node.exe", "100 MB", 104857600, False, "yellow",
         "这是 Node.js 运行时的主程序文件，前端开发和 JavaScript 服务端开发的核心工具。\n\n看看再删\n删了的话 npm、npx 命令和所有 Node.js 项目都无法运行。如果不做前端开发了，通过控制面板卸载。"),

        # ===== Python — system install =====
        (f"C:\\Program Files\\Python312\\python312.dll", "python312.dll", "100 MB", 104857600, False, "yellow",
         "这是 Python 3.12 的核心运行库文件，运行 Python 脚本必需的系统组件。\n\n看看再删\n删了的话所有依赖 Python 3.12 的程序都无法运行。如果不做 Python 开发了，通过控制面板卸载 Python。"),

        # ===== Spotify — log =====
        (f"{U}\\AppData\\Local\\Spotify\\Browser\\Cache\\Cache_Data", "Cache_Data", "200 MB", 209715200, True, "green",
         "这是 Spotify 的内嵌浏览器缓存。\n\n放心删\n纯缓存，删了不影响 Spotify 音乐播放功能。"),

        # ===== Temp — MSI installer =====
        (f"{U}\\AppData\\Local\\Temp\\{{A1B2C3D4-E5F6-7890}}\\setup.msi", "setup.msi", "250 MB", 262144000, False, "green",
         "这是临时目录下某个软件的 MSI 安装包残留，安装完成后没有清理掉。\n\n放心删\n安装完成后的残留文件，可以放心删除。"),

        # ===== Thunderbird =====
        (f"{U}\\AppData\\Roaming\\Thunderbird\\Profiles\\abc123.default-release\\ImapMail\\imap.gmail.com", "imap.gmail.com", "2.0 GB", 2147483648, True, "yellow",
         "这是 Thunderbird 邮件客户端同步的 Gmail 邮件本地副本。\n\n看看再删\n删了的话 Thunderbird 里的邮件需要重新从 Gmail 服务器同步，可能需要较长时间。服务器上的邮件不会丢失。"),

        # ===== LibreOffice =====
        (f"C:\\Program Files\\LibreOffice\\program\\soffice.bin", "soffice.bin", "130 MB", 136314880, False, "yellow",
         "这是 LibreOffice（开源办公套件）的核心程序文件，类似 Microsoft Office 的免费替代品。\n\n看看再删\n删了的话 LibreOffice 无法启动。如果不用了，通过控制面板卸载。"),

        # ===== R language =====
        (f"C:\\Program Files\\R\\R-4.3.2\\bin\\x64\\R.dll", "R.dll", "120 MB", 125829120, False, "yellow",
         "这是 R 语言（统计分析编程语言）的核心运行库。\n\n看看再删\n删了的话 R 和 RStudio 都无法运行。如果不做统计分析了，通过控制面板卸载 R。"),

        # ===== Julia =====
        (f"{U}\\.julia\\compiled\\v1.10", "v1.10", "500 MB", 524288000, True, "green",
         "这是 Julia（科学计算编程语言）的包编译缓存，安装的 Julia 包编译后的中间文件。\n\n放心删\n纯缓存，删了后 Julia 下次加载包时会重新编译，首次加载会慢一些。"),

        # ===== WSL — Ubuntu distro =====
        (f"{U}\\AppData\\Local\\Packages\\CanonicalGroupLimited.Ubuntu_79rhkp1fndgsc\\LocalState\\ext4.vhdx", "ext4.vhdx", "10.0 GB", 10737418240, False, "yellow",
         "这是 WSL 中 Ubuntu 发行版的虚拟磁盘，你在 Ubuntu 里的所有文件和安装的软件都在里面。\n\n看看再删\n删了的话你的整个 Ubuntu 环境会丢失，包括所有 Linux 文件和数据。如果不用 WSL Ubuntu 了，可以用 wsl --unregister Ubuntu 正式卸载。"),

        # ===== Scoop =====
        (f"{U}\\scoop\\cache", "cache", "500 MB", 524288000, True, "green",
         "这是 Scoop（Windows 命令行包管理器）的下载缓存。\n\n放心删\n纯缓存，删了不影响已安装的软件。可以用 scoop cache rm --all 清理。"),

        # ===== Winget =====
        (f"{U}\\AppData\\Local\\Packages\\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\\LocalState\\Microsoft.WinGet.Source_8wekyb3d8bbwe", "Microsoft.WinGet.Source_8wekyb3d8bbwe", "200 MB", 209715200, True, "green",
         "这是 winget（Windows 包管理器）的软件源索引缓存。\n\n放心删\n纯缓存，winget 下次搜索时会自动更新。"),

        # ===== Vivaldi — more =====
        (f"{U}\\AppData\\Local\\Vivaldi\\User Data\\Default\\IndexedDB", "IndexedDB", "200 MB", 209715200, True, "yellow",
         "这是 Vivaldi 浏览器里各网站存储的本地数据库。\n\n看看再删\n删了的话某些网站的离线功能和登录状态会丢失。"),

        # ===== Bandizip =====
        (f"C:\\Program Files\\Bandizip\\Bandizip.exe", "Bandizip.exe", "110 MB", 115343360, False, "yellow",
         "这是 Bandizip（压缩解压工具）的主程序文件。\n\n看看再删\n删了的话 Bandizip 无法启动。如果不用了，通过控制面板卸载。"),

        # ===== 金山毒霸 =====
        (f"C:\\Program Files (x86)\\kingsoft\\kingsoft antivirus\\KAVCore.dll", "KAVCore.dll", "150 MB", 157286400, False, "yellow",
         "这是金山毒霸的杀毒引擎核心文件。\n\n看看再删\n删了的话金山毒霸的杀毒功能会完全失效。如果不用金山毒霸了，建议通过控制面板完整卸载。"),

        # ===== Typora =====
        (f"C:\\Program Files\\Typora\\Typora.exe", "Typora.exe", "130 MB", 136314880, False, "yellow",
         "这是 Typora（Markdown 编辑器）的主程序文件。\n\n看看再删\n删了的话 Typora 无法启动。如果不用了，通过控制面板卸载。你的 Markdown 文件不受影响。"),

        # ===== MuseScore =====
        (f"C:\\Program Files\\MuseScore 4\\bin\\MuseScore4.exe", "MuseScore4.exe", "130 MB", 136314880, False, "yellow",
         "这是 MuseScore 4（开源乐谱编辑软件）的主程序文件。\n\n看看再删\n删了的话 MuseScore 无法启动。如果不做乐谱编辑了，通过控制面板卸载。"),

        # ===== DaVinci Resolve =====
        (f"C:\\Program Files\\Blackmagic Design\\DaVinci Resolve\\Resolve.exe", "Resolve.exe", "250 MB", 262144000, False, "yellow",
         "这是 DaVinci Resolve（达芬奇，专业视频调色和编辑软件）的主程序文件。\n\n看看再删\n删了的话达芬奇无法启动。如果不做视频编辑了，通过控制面板卸载。完整安装约 3GB。"),

        # ===== Praat =====
        (f"C:\\Program Files\\Praat\\Praat.exe", "Praat.exe", "100 MB", 104857600, False, "yellow",
         "这是 Praat（语音分析软件）的主程序文件，语言学研究中用来分析语音信号的工具。\n\n看看再删\n删了的话 Praat 无法启动。如果不做语音分析了，直接删除 Praat 文件夹即可。"),

        # ===== Logseq =====
        (f"{U}\\AppData\\Roaming\\Logseq\\Cache", "Cache", "200 MB", 209715200, True, "green",
         "这是 Logseq（开源知识管理工具）的界面缓存。\n\n放心删\n纯缓存，你的笔记数据在本地的笔记文件夹里，不在这里。"),

        # ===== Zotero — storage =====
        (f"{U}\\Zotero\\storage", "storage", "3.0 GB", 3221225472, True, "yellow",
         "这是 Zotero 的文献附件存储目录，保存了你导入的所有 PDF 论文和文献附件。\n\n看看再删\n删了的话所有本地存储的文献 PDF 会丢失。如果你有 Zotero 云同步，可以重新下载。建议在 Zotero 里管理文献而不是手动删文件。"),

        # ===== KeePass =====
        (f"{U}\\Documents\\Passwords.kdbx", "Passwords.kdbx", "100 MB", 104857600, False, "yellow",
         "这是 KeePass（密码管理工具）的加密密码数据库，存储了你保存的所有账号密码。\n\n看看再删\n这是你的密码库！删了的话所有保存的密码会永久丢失。强烈建议做好备份后再做任何操作。"),

        # ===== OBS recordings — more =====
        (f"{U}\\Videos\\OBS\\Replay-2024-03-15.mp4", "Replay-2024-03-15.mp4", "1.5 GB", 1610612736, False, "green",
         "这是 OBS Studio 的回放录制文件，你按了回放快捷键时保存的精彩片段。\n\n放心删\n这是你的录制内容。确认不需要后可以删除释放空间。"),

        # ===== NVIDIA GeForce highlights =====
        (f"{U}\\Videos\\NVIDIA\\Highlights", "Highlights", "5.0 GB", 5368709120, True, "green",
         "这是 NVIDIA GeForce Experience 自动录制的游戏精彩时刻视频。\n\n放心删\n这是你游戏过程中的自动录屏。如果你不需要这些回放，可以全部删除。也可以在 GeForce Experience 设置里关闭自动录制。"),

        # ===== NVIDIA shader cache (system level) =====
        (f"C:\\ProgramData\\NVIDIA Corporation\\NV_Cache", "NV_Cache", "500 MB", 524288000, True, "green",
         "这是 NVIDIA 显卡驱动的全局着色器缓存，所有应用共享的 GPU 程序编译结果。\n\n放心删\n纯缓存，删了不影响任何功能。下次启动游戏或 GPU 应用时会自动重建。"),

        # ===== AMD — Radeon cache =====
        (f"{U}\\AppData\\Local\\AMD\\DxCache", "DxCache", "300 MB", 314572800, True, "green",
         "这是 AMD 显卡的 DirectX 着色器缓存，类似 NVIDIA 的 DXCache。\n\n放心删\n纯缓存，删了不影响任何功能。下次启动游戏时会重新编译着色器。"),

        # ===== Windows Sandbox =====
        (f"C:\\ProgramData\\Microsoft\\Windows\\Containers\\Sandboxes", "Sandboxes", "1.0 GB", 1073741824, True, "yellow",
         "这是 Windows 沙盒的容器数据，每次启动 Windows 沙盒时创建的隔离运行环境。\n\n看看再删\n如果你不用 Windows 沙盒功能，可以在 Windows 功能里关闭它。正在使用沙盒时不要删。"),

        # ===== Windows diagnostic data =====
        (f"C:\\ProgramData\\Microsoft\\Diagnosis\\ETLLogs\\AutoLogger", "AutoLogger", "300 MB", 314572800, True, "green",
         "这是 Windows 诊断和遥测的事件跟踪日志，系统自动收集的运行状态数据。\n\n放心删\n纯诊断日志，删了不影响系统功能。系统会自动重新生成。"),

        # ===== Final batch to reach 600 =====
        (f"{U}\\AppData\\Local\\Google\\Chrome\\User Data\\Crashpad\\reports", "reports", "150 MB", 157286400, True, "green",
         "这是 Chrome 浏览器的崩溃报告缓存。\n\n放心删\n纯崩溃日志，删了不影响 Chrome 功能。"),
        (f"{U}\\AppData\\Local\\Microsoft\\Edge\\User Data\\Crashpad\\reports", "reports", "100 MB", 104857600, True, "green",
         "这是 Edge 浏览器的崩溃报告缓存。\n\n放心删\n纯崩溃日志，删了不影响 Edge 功能。"),
        (f"C:\\Program Files (x86)\\Steam\\logs", "logs", "200 MB", 209715200, True, "green",
         "这是 Steam 的运行日志目录。\n\n放心删\n纯日志，删了不影响 Steam 和游戏功能。"),
        (f"{U}\\AppData\\Local\\Tencent\\QQBrowser\\User Data\\Default\\Cache", "Cache", "400 MB", 419430400, True, "green",
         "这是 QQ 浏览器的网页缓存。\n\n放心删\n纯缓存，删了不影响浏览器功能。"),
        (f"{U}\\AppData\\Local\\Programs\\Python\\Python312\\Lib\\site-packages\\torch\\lib\\torch_cpu.dll", "torch_cpu.dll", "250 MB", 262144000, False, "yellow",
         "这是系统级安装的 Python 3.12 环境里的 PyTorch CPU 运算核心库。\n\n看看再删\n删了的话 Python 3.12 环境里的 PyTorch 无法使用。如果不做深度学习了，可以用 pip uninstall torch 卸载 PyTorch。"),
        (f"{U}\\AppData\\Local\\Microsoft\\WindowsApps\\MicrosoftCorporationII.WindowsSubsystemForLinux_8wekyb3d8bbwe", "MicrosoftCorporationII.WindowsSubsystemForLinux_8wekyb3d8bbwe", "150 MB", 157286400, True, "yellow",
         "这是 WSL（Windows 子系统 Linux）的应用商店安装包链接目录。\n\n看看再删\n属于 Windows 应用商店管理的组件，不要手动删除。如果不用 WSL 了，在 Windows 功能或应用管理里关闭。"),
        (f"C:\\Program Files\\NVIDIA Corporation\\NVSMI\\nvidia-smi.exe", "nvidia-smi.exe", "100 MB", 104857600, False, "yellow",
         "这是 NVIDIA 显卡的系统管理接口命令行工具，查看 GPU 使用状态和温度信息用的。\n\n看看再删\n属于 NVIDIA 驱动的管理工具组件。删了的话 nvidia-smi 命令无法使用，但不影响显卡正常工作。"),
        (f"{U}\\AppData\\Local\\Temp\\aria-debug.log", "aria-debug.log", "100 MB", 104857600, False, "green",
         "这是 Microsoft Office 遥测组件（Aria/OTEL）的调试日志。\n\n放心删\n纯日志，删了不影响 Office 功能。"),
        (f"{U}\\AppData\\Local\\Microsoft\\Teams\\Cache\\Cache_Data", "Cache_Data", "400 MB", 419430400, True, "green",
         "这是旧版 Microsoft Teams（非商店版）的界面缓存。\n\n放心删\n纯缓存，删了不影响 Teams 功能。"),
        (f"C:\\ProgramData\\Microsoft\\Windows\\SystemData", "SystemData", "200 MB", 209715200, True, "red",
         "这是 Windows 系统数据目录，保存了锁屏图片、用户头像等系统个性化数据。\n\n千万别删\n属于系统保护目录，手动删除可能导致登录界面异常。"),
        (f"{U}\\AppData\\Roaming\\Code\\User\\globalStorage", "globalStorage", "200 MB", 209715200, True, "yellow",
         "这是 VS Code 扩展的全局存储目录，各扩展保存的持久化数据（如登录令牌、数据库索引等）。\n\n看看再删\n删了的话某些 VS Code 扩展需要重新登录或重新配置。代码文件不受影响。"),
        (f"{U}\\AppData\\Local\\Temp\\tmp_node_modules", "tmp_node_modules", "300 MB", 314572800, True, "green",
         "这是临时目录下某个 Node.js 工具安装的依赖残留。\n\n放心删\n临时目录下的文件可以安全删除。"),
        (f"C:\\ProgramData\\chocolatey\\lib", "lib", "500 MB", 524288000, True, "yellow",
         "这是 Chocolatey（Windows 包管理器）安装的所有软件包的数据目录。\n\n看看再删\n删了的话通过 Chocolatey 安装的软件元数据会丢失，但软件本身还能用。如果你用 Chocolatey 管理软件，不要删。"),
    ]

    instruction_tpl = SYSTEM_PROMPT

    results = []
    for path, name, size_human, size, is_dir, safety, output in synthetic:
        kind = "文件夹" if is_dir else "文件"
        verdict = get_verdict(safety)
        input_text = build_input({
            "path": path, "name": name, "size_human": size_human,
            "size": size, "is_dir": is_dir, "safety": safety
        })
        results.append({
            "instruction": instruction_tpl.format(kind=kind).replace("{{verdict}}", verdict),
            "input": input_text,
            "output": output,
            "confidence": "high",
        })

    return results


if __name__ == "__main__":
    generate_training_data()
