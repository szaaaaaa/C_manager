"""
LLM-powered path explainer.
Calls an OpenAI-compatible API to produce a plain-Chinese description of
what a given file/folder is and whether it's safe to delete.

Provider is configured via environment variables:
  LLM_API_KEY   — API key (required)
  LLM_BASE_URL  — base URL (default: https://api.openai.com/v1)
  LLM_MODEL     — model name (default: gpt-4o-mini)

If LLM_API_KEY is not set, returns a canned offline explanation.
"""

import os
import json
import urllib.request
import urllib.error
from dataclasses import dataclass


@dataclass
class ExplainResult:
    path: str
    explanation: str   # plain Chinese, ≤ 3 sentences
    is_llm: bool       # True = from LLM, False = offline fallback


_SYSTEM_PROMPT = (
    "你是一个 Windows 系统专家助手。"
    "用户会给你一个文件或文件夹的路径，"
    "请用不超过3句话、通俗易懂的中文解释它是什么、有什么用、能不能删除。"
    "语气轻松幽默，面向普通非技术用户。"
    "不要输出 Markdown，只输出纯文本。"
)


def explain_path(path: str) -> ExplainResult:
    """Return a plain-Chinese LLM explanation for the given path.

    Falls back to an offline description if no API key is configured.
    """
    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        return _offline_fallback(path)

    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"路径：{path}"},
        ],
        "max_tokens": 200,
        "temperature": 0.7,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            text = body["choices"][0]["message"]["content"].strip()
            return ExplainResult(path=path, explanation=text, is_llm=True)
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, IndexError) as exc:
        return ExplainResult(
            path=path,
            explanation=f"（AI解释暂时不可用：{exc}）请根据安全评级自行判断。",
            is_llm=False,
        )


def _offline_fallback(path: str) -> ExplainResult:
    """Rule-based fallback when no LLM key is configured."""
    lower = path.lower().replace("\\", "/")

    rules = [
        ("windows/system32",     "这是 Windows 系统核心目录，里面住着操作系统的命根子。请勿删除，否则系统可能无法启动！"),
        ("appdata/local/temp",   "这是应用程序的临时文件仓库，装满了'用完即弃'的垃圾文件。可以放心清理，定期清一次空间立竿见影。"),
        ("/temp/",               "临时文件目录，程序跑完就没用了。清理它就像倒垃圾桶，完全没问题。"),
        ("downloads",            "这是您的下载文件夹。里面可能有您珍藏的文件，删前看清楚！"),
        ("node_modules",         "这是 Node.js 项目的依赖包目录。如果不再开发这个项目可以删掉，重新 npm install 即可还原。"),
        ("__pycache__",          "Python 编译缓存，删掉完全没问题，Python 下次运行会自动重建。"),
        (".cache",               "程序缓存目录，删掉不影响功能，但下次启动可能稍慢（需要重建缓存）。"),
        ("program files",        "这里住着您安装的软件。请通过「控制面板 → 卸载程序」来管理，不要直接删。"),
    ]

    for keyword, msg in rules:
        if keyword in lower:
            return ExplainResult(path=path, explanation=msg, is_llm=False)

    name = os.path.basename(path.rstrip("/\\"))
    return ExplainResult(
        path=path,
        explanation=(
            f"「{name}」是一个不太常见的路径。"
            "建议先搜索一下它的用途，确认无用后再考虑清理。"
            "（设置 LLM_API_KEY 环境变量可启用 AI 智能解释）"
        ),
        is_llm=False,
    )
