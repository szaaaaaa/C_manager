"""
Safety analyzer + LLM explanation generator.
Safety rating is purely local (no network). LLM call is optional.
"""
import json
import os
import re
from pathlib import Path
from typing import Optional

# Load safety rules once at module level
_RULES_PATH = Path(__file__).parent.parent.parent / "configs" / "safety_rules.json"
with open(_RULES_PATH, encoding="utf-8") as _f:
    _RULES: dict = json.load(_f)


def rate_safety(path: str) -> str:
    """
    Return 'red', 'yellow', or 'green' based on path patterns.
    Pure local logic — no network calls.
    """
    path_lower = path.lower().replace("/", "\\")

    # Green is checked FIRST so specific safe-to-clean subpaths (e.g. \Windows\Temp)
    # take priority over broad dangerous-folder patterns (e.g. \windows\).
    for pattern in _RULES["green"]:
        pat_stripped = pattern.rstrip("\\")
        if pattern in path_lower or path_lower.endswith(pat_stripped):
            return "green"

    # Red: system-critical
    for pattern in _RULES["red"]:
        if pattern in path_lower:
            return "red"
    # Also check filename
    filename = os.path.basename(path_lower)
    if filename in _RULES["red_names"]:
        return "red"

    # Yellow: caution
    for pattern in _RULES["yellow"]:
        if pattern in path_lower:
            return "yellow"

    # Default: yellow (unknown = caution)
    return "yellow"


def _build_explain_prompt(path: str, size_human: str, is_dir: bool, safety: str) -> str:
    safety_label = {"red": "🔴系统核心", "yellow": "🟡建议保留", "green": "🟢可以清理"}[safety]
    kind = "文件夹" if is_dir else "文件"
    name = os.path.basename(path)
    return f"""你是一个帮助普通用户理解Windows C盘文件的助手。
用通俗幽默的中文大白话（2-4句话）解释以下{kind}是什么用途，普通用户看不懂英文名时应该怎么理解它：

文件路径: {path}
文件名: {name}
大小: {size_human}
安全评级: {safety_label}

要求：
1. 用类比和生活化的比喻解释
2. 说明为什么占这么多空间（如果合理的话）
3. 根据安全评级给出建议（红色=绝对别碰，黄色=谨慎，绿色=可以清）
4. 语气轻松，像朋友聊天
5. 不超过4句话
"""


async def explain_with_llm(
    path: str,
    size_human: str,
    is_dir: bool,
    safety: str,
    api_key: str,
    base_url: str = "https://openrouter.ai/api/v1",
    model: str = "anthropic/claude-haiku-4-5",
) -> str:
    """Call LLM to generate a plain-language explanation. Returns explanation string."""
    import httpx

    prompt = _build_explain_prompt(path, size_human, is_dir, safety)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


def format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"
