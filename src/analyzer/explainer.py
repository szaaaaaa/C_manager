"""
LLM-based explainer for file/folder paths.
Supports OpenAI-compatible APIs (OpenRouter, OpenAI, local).
Falls back to rule-based descriptions when no API key is configured.
"""
import os
from typing import Optional

# Rule-based fallback explanations for common Windows paths
_KNOWN_PATHS: dict[str, str] = {
    "windows": "Windows 操作系统的核心目录，相当于人体的骨架，里面住着系统运行必须的所有程序",
    "system32": "Windows 最核心的系统文件仓库，里面全是.dll和.exe，是系统的'五脏六腑'，缺一不可",
    "syswow64": "专门给32位老程序提供运行环境的兼容层，让老软件能在64位系统上跑起来",
    "winsxs": "Windows 的'零件仓库'，存着各种版本的系统组件，用于系统修复和回滚，体积大但很重要",
    "program files": "正规软件的安装大本营，卸载软件要走控制面板，不能直接删文件夹",
    "program files (x86)": "专门给32位软件住的区域，类似program files但专属老软件",
    "programdata": "软件的'后勤仓库'，存着配置文件、数据库、授权信息，直接删软件可能罢工",
    "users": "所有用户的个人文件总目录，桌面、文档、下载都在这里",
    "appdata": "软件偷偷存在用户目录里的数据，有缓存也有重要配置",
    "local": "本机专属的软件数据，不随账号同步，包含大量缓存",
    "roaming": "会随账号漫游同步的软件数据，换电脑也能带走的设置",
    "temp": "临时文件的中转站，软件用完就该删的垃圾文件堆在这里，可以放心清理",
    "prefetch": "Windows 记录程序启动习惯的笔记本，删了不会崩但下次启动会慢一点",
    "installer": "软件安装包的备份仓库，用于修复和更新，删了修复软件可能出问题",
    "softwaredistribution": "Windows Update 下载更新包的临时仓库，更新完成后可以清理",
    "pagefile.sys": "虚拟内存文件，内存不够时系统借用硬盘空间，系统自动管理",
    "hiberfil.sys": "休眠文件，存储休眠时内存的快照，不用休眠功能可以关掉",
    "swapfile.sys": "UWP应用专用的交换文件，和pagefile.sys配合使用",
    "$recycle.bin": "回收站的真身，里面全是你删掉但还没彻底清空的文件",
    "node_modules": "Node.js项目的依赖包仓库，体积巨大，可以删了再npm install重新生成",
    ".git": "Git 版本控制的数据库，存着整个项目的历史记录",
    "cache": "缓存文件，为了加快速度存的临时数据，通常可以安全清理",
    "logs": "程序运行日志，记录软件的操作历史，通常可以清理旧的",
    "crashdumps": "程序崩溃时保存的内存快照，用于调试，可以安全删除",
    "downloads": "下载文件夹，你自己下载的东西，自己决定要不要留",
    "documents": "我的文档，个人重要文件，删之前请确认",
    "desktop": "桌面文件，你放在桌面上的东西",
    "pictures": "图片文件夹",
    "videos": "视频文件夹，视频文件通常很大",
    "music": "音乐文件夹",
}


def _rule_based_explain(name: str) -> str:
    name_lower = name.lower()
    for key, desc in _KNOWN_PATHS.items():
        if key in name_lower or name_lower == key:
            return desc
    return f"'{name}' 是一个文件夹/文件，建议搜索它的用途再决定是否删除"


def explain_path(path: str, name: str, use_llm: bool = True) -> str:
    """
    Return a plain-Chinese explanation of what the given path/folder is.
    If LLM is available (OPENAI_API_KEY or OPENROUTER_API_KEY set), calls the API.
    Falls back to rule-based explanation otherwise.
    """
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")

    if use_llm and api_key:
        return _llm_explain(path, name, api_key)

    return _rule_based_explain(name)


def _llm_explain(path: str, name: str, api_key: str) -> str:
    """Call OpenAI-compatible API to explain the path."""
    try:
        import httpx

        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

        prompt = (
            f"你是一个帮助普通用户清理C盘的助手。用户想知道这个文件/文件夹是什么用途：\n"
            f"路径：{path}\n"
            f"名称：{name}\n\n"
            f"请用不超过50字的大白话解释它的用途，语气轻松幽默，让普通用户能看懂。"
            f"不要用英文术语，如果必须用请加括号说明。直接给解释，不要加前缀。"
        )

        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.7,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return _rule_based_explain(name)
