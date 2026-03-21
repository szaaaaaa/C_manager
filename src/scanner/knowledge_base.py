"""
Static knowledge base of known Windows paths with safety ratings.

Matching logic (applied in order):
1. Exact path match (case-insensitive, normalised with forward slashes)
2. Suffix/substring match against known patterns
3. Extension-based match
4. Default: UNKNOWN

All path patterns are stored as lowercase with forward slashes for
platform-independent comparison.
"""

from .models import SafetyRating

# ---------------------------------------------------------------------------
# Exact / prefix path rules
# Each entry: (normalised_path_fragment, SafetyRating, reason)
# The fragment is matched against the *normalised* absolute path of the item.
# Matching is done as: normalised_item_path.startswith(fragment)
# ---------------------------------------------------------------------------

PATH_RULES: list[tuple[str, SafetyRating, str]] = [
    # ── DANGER: system core ────────────────────────────────────────────────
    ("c:/windows/system32",         SafetyRating.DANGER,
     "Windows 核心系统文件，删了系统直接崩"),
    ("c:/windows/syswow64",         SafetyRating.DANGER,
     "32位兼容层系统文件，删了32位程序全挂"),
    ("c:/windows/winsxs",           SafetyRating.DANGER,
     "Windows 组件库，系统自己管着，别碰"),
    ("c:/windows/boot",             SafetyRating.DANGER,
     "启动引导文件，删了开机直接黑屏"),
    ("c:/windows/fonts",            SafetyRating.DANGER,
     "系统字体，删了界面文字全乱套"),
    ("c:/windows/inf",              SafetyRating.DANGER,
     "驱动安装信息文件，删了装驱动会出问题"),
    ("c:/bootmgr",                  SafetyRating.DANGER,
     "Windows 引导管理器，删了开不了机"),
    ("c:/boot",                     SafetyRating.DANGER,
     "启动文件夹，删了系统无法启动"),
    ("c:/system volume information",SafetyRating.DANGER,
     "系统还原点数据，删了丢失所有还原点"),
    ("c:/program files/windows nt", SafetyRating.DANGER,
     "系统核心程序，别动"),
    ("c:/program files (x86)/windows nt", SafetyRating.DANGER,
     "系统核心程序（32位），别动"),
    ("c:/users/default",            SafetyRating.DANGER,
     "新用户模板，删了新建账户会出问题"),

    # ── SAFE: definite junk ────────────────────────────────────────────────
    ("c:/windows/temp",             SafetyRating.SAFE,
     "系统临时文件，随时可删，删了系统自动重建"),
    ("c:/windows/softwaredistribution/download", SafetyRating.SAFE,
     "Windows Update 下载缓存，删了下次更新重新下就好"),
    ("c:/windows/installer/$patchcache$", SafetyRating.SAFE,
     "安装包补丁缓存，一般可以安全清理"),
    ("c:/windows.old",              SafetyRating.SAFE,
     "上个版本的 Windows 备份，升级后可以放心删掉，能省几十个 GB"),
    ("c:/windows/panther",          SafetyRating.SAFE,
     "Windows 安装日志，安装完成后没用了"),
    ("c:/windows/logs",             SafetyRating.SAFE,
     "系统日志文件，占空间但不影响运行"),
    ("c:/windows/minidump",         SafetyRating.SAFE,
     "系统崩溃转储文件，如果系统稳定可以删"),
    ("c:/windows/memory.dmp",       SafetyRating.SAFE,
     "内存转储文件，系统稳定时可以删，能省很多空间"),
    ("c:/windows/prefetch",         SafetyRating.SAFE,
     "程序预取缓存，删了不影响运行，只是首次启动慢一点"),
    ("c:/programdata/microsoft/windows/wer", SafetyRating.SAFE,
     "Windows 错误报告，可以安全删除"),
    # ── CAUTION: user data / app settings ─────────────────────────────────
    ("c:/program files",            SafetyRating.CAUTION,
     "已安装程序，通过控制面板卸载更安全"),
    ("c:/program files (x86)",      SafetyRating.CAUTION,
     "已安装程序（32位），通过控制面板卸载更安全"),
    ("c:/programdata",              SafetyRating.CAUTION,
     "程序共享数据，可能有配置文件，谨慎清理"),
]

# ---------------------------------------------------------------------------
# Per-user path pattern rules (path contains these substrings)
# ---------------------------------------------------------------------------

SUBSTRING_RULES: list[tuple[str, SafetyRating, str]] = [
    # SAFE
    ("/appdata/local/temp",         SafetyRating.SAFE,
     "用户临时文件，可以放心删"),
    ("/appdata/local/microsoft/windows/temporary internet files", SafetyRating.SAFE,
     "IE 浏览器缓存，可以删"),
    ("/appdata/local/microsoft/windows/webcache", SafetyRating.SAFE,
     "浏览器 WebCache，可以删"),
    ("/appdata/local/google/chrome/user data/default/cache", SafetyRating.SAFE,
     "Chrome 缓存，可以安全删除"),
    ("/appdata/local/microsoft/edge/user data/default/cache", SafetyRating.SAFE,
     "Edge 浏览器缓存，可以安全删除"),
    ("/appdata/local/mozilla/firefox/profiles", SafetyRating.SAFE,
     "Firefox 缓存目录，可以清理缓存子文件夹"),
    ("/appdata/local/microsoft/windows/explorer/thumbcache", SafetyRating.SAFE,
     "缩略图缓存，可以删，会自动重建"),
    ("/appdata/local/crashdumps",   SafetyRating.SAFE,
     "程序崩溃转储，稳定时可删"),
    ("/appdata/local/nuget/cache",  SafetyRating.SAFE,
     "NuGet 包缓存，可以删，会自动重新下载"),
    ("/appdata/local/pip/cache",    SafetyRating.SAFE,
     "pip 下载缓存，可以删，重装包时重新下载"),
    ("/appdata/local/yarn/cache",   SafetyRating.SAFE,
     "Yarn 包缓存，可以删"),
    ("/appdata/local/npm-cache",    SafetyRating.SAFE,
     "npm 缓存，可以删"),
    ("/__pycache__",                SafetyRating.SAFE,
     "Python 字节码缓存，可以删，会自动重建"),
    ("/.pytest_cache",              SafetyRating.SAFE,
     "pytest 缓存，可以删"),
    ("/node_modules",               SafetyRating.CAUTION,
     "Node.js 依赖包，删了需要重新 npm install"),
    # CAUTION
    ("/appdata/roaming",            SafetyRating.CAUTION,
     "程序配置和数据，可能有账号设置等重要信息"),
    ("/appdata/local",              SafetyRating.CAUTION,
     "本地程序数据，可能有缓存也可能有重要数据"),
    ("/documents",                  SafetyRating.CAUTION,
     "用户文档，请确认不需要后再删"),
    ("/downloads",                  SafetyRating.CAUTION,
     "下载目录，检查一下有没有还需要的文件"),
    ("/desktop",                    SafetyRating.CAUTION,
     "桌面文件，自己放的东西要确认"),
    ("/users/",                     SafetyRating.CAUTION,
     "用户数据目录，里面可能有重要文件"),
]

# ---------------------------------------------------------------------------
# Extension-based rules (applied last)
# ---------------------------------------------------------------------------

EXTENSION_RULES: dict[str, tuple[SafetyRating, str]] = {
    ".tmp":   (SafetyRating.SAFE,    "临时文件，通常可以安全删除"),
    ".temp":  (SafetyRating.SAFE,    "临时文件，通常可以安全删除"),
    ".log":   (SafetyRating.SAFE,    "日志文件，程序正常运行时可以清理"),
    ".old":   (SafetyRating.SAFE,    "旧版本文件备份，通常可以删除"),
    ".bak":   (SafetyRating.SAFE,    "备份文件，确认不需要后可删除"),
    ".chk":   (SafetyRating.SAFE,    "磁盘检查产生的碎片文件，可以删除"),
    ".dmp":   (SafetyRating.SAFE,    "崩溃转储文件，系统稳定时可删"),
    ".etl":   (SafetyRating.SAFE,    "事件跟踪日志，可以清理"),
    ".cab":   (SafetyRating.CAUTION, "压缩包，可能是安装文件，确认后删除"),
    ".sys":   (SafetyRating.DANGER,  "系统驱动文件，不要随便删"),
    ".dll":   (SafetyRating.DANGER,  "动态链接库，删了程序可能崩溃"),
    ".exe":   (SafetyRating.CAUTION, "可执行文件，确认不需要后才删"),
}


def rate_path(path: str) -> tuple[SafetyRating, str]:
    """
    Return (SafetyRating, reason) for the given absolute path.

    Matching priority:
    1. PATH_RULES  (prefix match, longest match wins)
    2. SUBSTRING_RULES (first match in order)
    3. EXTENSION_RULES
    4. UNKNOWN
    """
    normalised = path.replace("\\", "/").lower()

    # 1. Prefix rules — find longest matching prefix
    best_match: tuple[SafetyRating, str] | None = None
    best_len = 0
    for fragment, rating, reason in PATH_RULES:
        if normalised.startswith(fragment) and len(fragment) > best_len:
            best_match = (rating, reason)
            best_len = len(fragment)
    if best_match:
        return best_match

    # 2. Substring rules
    for fragment, rating, reason in SUBSTRING_RULES:
        if fragment in normalised:
            return rating, reason

    # 3. Extension rules
    dot_idx = normalised.rfind(".")
    if dot_idx != -1:
        ext = normalised[dot_idx:]
        if ext in EXTENSION_RULES:
            rating, reason = EXTENSION_RULES[ext]
            return rating, reason

    return SafetyRating.UNKNOWN, ""
