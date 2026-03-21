"""
Safety rating rules for common Windows C-drive paths.
Returns: "green" (safe to delete), "yellow" (caution), "red" (system critical).
"""

# (path_fragment_lower, rating, reason_zh)
_RULES: list[tuple[str, str, str]] = [
    # Red — system critical
    ("windows/system32", "red", "Windows 核心系统文件，删了系统直接崩"),
    ("windows/syswow64", "red", "32位程序的系统支撑层，删了32位软件全废"),
    ("windows/winsxs", "red", "Windows 组件存储，系统修复靠它"),
    ("windows/boot", "red", "系统引导文件，删了电脑开不了机"),
    ("windows/drivers", "red", "硬件驱动库，删了鼠标键盘可能全哑"),
    ("programdata/microsoft/windows/", "red", "Windows 系统级数据，别动"),
    ("users/default/", "red", "新用户模板目录，别碰"),

    # Yellow — caution
    ("program files (x86)", "yellow", "32位软件安装目录，卸载软件用控制面板，别直接删"),
    ("program files", "yellow", "软件安装目录，卸载软件请用控制面板"),
    ("programdata", "yellow", "软件运行数据，直接删可能让软件崩溃"),
    ("users", "yellow", "用户个人文件夹，误删会丢文件"),
    ("windows/temp", "green", "临时文件，可以放心清理"),
    ("windows/prefetch", "yellow", "程序预加载缓存，删了不会崩但会变慢"),
    ("windows/installer", "yellow", "安装包缓存，删了修复/更新软件可能出问题"),
    ("windows/softwaredistribution", "yellow", "Windows 更新下载缓存，需要的话可以清理"),
    ("windows", "yellow", "Windows 系统目录，未知子项请谨慎"),

    # Green — safe
    ("users/*/appdata/local/temp", "green", "用户临时文件，完全可以删"),
    ("users/*/appdata/local/microsoft/windows/temporary internet files", "green", "IE 缓存，可删"),
    ("$recycle.bin", "green", "回收站，可以直接清空"),
    ("temp", "green", "临时文件夹，可以清理"),
    ("tmp", "green", "临时文件夹，可以清理"),
]

_KNOWN_SAFE_EXTENSIONS = {".tmp", ".log", ".bak", ".old", ".dmp", ".etl"}


def rate_path(path: str) -> dict:
    """
    Given a file/folder path, return {"rating": str, "reason": str}.
    rating is "red" | "yellow" | "green".
    """
    path_lower = path.replace("\\", "/").lower()

    for fragment, rating, reason in _RULES:
        if fragment in path_lower:
            return {"rating": rating, "reason": reason}

    # Extension-based fallback for files
    ext = path_lower.rsplit(".", 1)[-1] if "." in path_lower.split("/")[-1] else ""
    if f".{ext}" in _KNOWN_SAFE_EXTENSIONS:
        return {"rating": "green", "reason": "常见临时/日志文件，通常可以删除"}

    return {"rating": "yellow", "reason": "未知路径，建议先搜索了解用途再决定"}
