"""LLM prompt templates for file/folder explanation."""

EXPLAIN_SYSTEM_PROMPT = """你是一个专业的 Windows 系统文件分析助手，擅长用大白话向普通用户解释神秘的系统文件和文件夹。
你的风格：幽默、接地气、有点小毒舌，就像你那个懂电脑的朋友跟你解释一样。
严格按照JSON格式返回，不要有任何额外说明。"""

EXPLAIN_USER_TEMPLATE = """分析这个 Windows 文件/文件夹：

路径: {path}
大小: {size_human}
类型: {item_type}
父文件夹: {parent_folder}

请用大白话（中文）解释：
1. 这是什么东西，有什么用
2. 是否可以删除，为什么
3. 一句幽默的总结

返回格式（严格JSON）：
{{
  "explanation": "大白话解释（50-100字，要有幽默感）",
  "safety_rating": "safe|caution|danger|unknown",
  "confidence": 0.0到1.0的数字
}}

说明：
- safe: 可以放心删，删了没事
- caution: 建议保留，不确定时别删
- danger: 系统核心，绝对别碰
- unknown: 不认识，不敢乱说"""


def build_explain_prompt(
    path: str,
    size_bytes: int,
    is_dir: bool,
    parent_folder: str,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the explain request."""
    size_human = _format_size(size_bytes)
    item_type = "文件夹" if is_dir else "文件"
    user_prompt = EXPLAIN_USER_TEMPLATE.format(
        path=path,
        size_human=size_human,
        item_type=item_type,
        parent_folder=parent_folder,
    )
    return EXPLAIN_SYSTEM_PROMPT, user_prompt


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / 1024 ** 3:.1f} GB"
    if size_bytes >= 1024 ** 2:
        return f"{size_bytes / 1024 ** 2:.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"
