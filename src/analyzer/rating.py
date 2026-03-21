"""
Safety rating engine — classifies file/folder paths into traffic-light categories.
🟢 GREEN  = safe to delete
🟡 YELLOW = review before deleting
🔴 RED    = system critical, never delete

All logic is heuristic / pattern-based; no LLM involved here.
"""

import os
import re
from enum import Enum
from dataclasses import dataclass


class SafetyLevel(str, Enum):
    GREEN = "green"    # 🟢 safe to delete
    YELLOW = "yellow"  # 🟡 review first
    RED = "red"        # 🔴 system critical


@dataclass
class RatingResult:
    level: SafetyLevel
    emoji: str
    reason: str


# ── rule tables ────────────────────────────────────────────────────────────────

# Exact path suffixes / substrings (case-insensitive, normalised to forward slash)
_RED_PATTERNS: list[str] = [
    r"windows[/\\]system32",
    r"windows[/\\]syswow64",
    r"windows[/\\]winsxs",
    r"windows[/\\]boot",
    r"windows[/\\]fonts",
    r"windows[/\\]inf",
    r"windows[/\\]drivers",
    r"program files[/\\]",
    r"program files \(x86\)[/\\]",
    r"windows[/\\]",          # catch-all for anything under Windows\
    r"system volume information",
    r"\$recycle\.bin",
    r"boot[/\\]bcd",
    r"pagefile\.sys$",
    r"hiberfil\.sys$",
    r"swapfile\.sys$",
]

_GREEN_PATTERNS: list[str] = [
    r"\\temp\\",
    r"/temp/",
    r"[/\\]tmp[/\\]",
    r"\\downloads\\",
    r"/downloads/",
    r"appdata[/\\]local[/\\]temp",
    r"appdata[/\\]locallow[/\\]temp",
    r"appdata[/\\]local[/\\]microsoft[/\\]windows[/\\]temporary internet files",
    r"\.cache[/\\]",
    r"[/\\]cache[/\\]",
    r"npm-cache",
    r"pip[/\\]cache",
    r"__pycache__",
    r"\.pytest_cache",
    r"node_modules[/\\]\.cache",
    r"dist[/\\]",             # build outputs
    r"\.tox[/\\]",
    r"thumbs\.db$",
    r"desktop\.ini$",
]

_YELLOW_PATTERNS: list[str] = [
    r"appdata[/\\]local[/\\]",
    r"appdata[/\\]roaming[/\\]",
    r"appdata[/\\]locallow[/\\]",
    r"documents[/\\]",
    r"pictures[/\\]",
    r"videos[/\\]",
    r"music[/\\]",
    r"onedrive[/\\]",
    r"node_modules[/\\]",
]

_RED_RE   = [re.compile(p, re.IGNORECASE) for p in _RED_PATTERNS]
_GREEN_RE = [re.compile(p, re.IGNORECASE) for p in _GREEN_PATTERNS]
_YELLOW_RE = [re.compile(p, re.IGNORECASE) for p in _YELLOW_PATTERNS]


def get_safety_rating(path: str) -> RatingResult:
    """Return a safety rating for the given file/directory path.

    Matching priority: RED > GREEN > YELLOW > default YELLOW.
    """
    normalised = path.replace("\\", "/")

    for pat in _RED_RE:
        if pat.search(normalised):
            return RatingResult(
                level=SafetyLevel.RED,
                emoji="🔴",
                reason="系统核心文件或已安装程序，绝对不要删除",
            )

    for pat in _GREEN_RE:
        if pat.search(normalised):
            return RatingResult(
                level=SafetyLevel.GREEN,
                emoji="🟢",
                reason="临时文件或缓存，安全可删",
            )

    for pat in _YELLOW_RE:
        if pat.search(normalised):
            return RatingResult(
                level=SafetyLevel.YELLOW,
                emoji="🟡",
                reason="用户数据或应用配置，删前确认",
            )

    # Default: unknown path → be cautious
    return RatingResult(
        level=SafetyLevel.YELLOW,
        emoji="🟡",
        reason="未知路径，建议先了解再决定",
    )
