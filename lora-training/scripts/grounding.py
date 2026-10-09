"""Shared local retrieval and prompts for the controlled experiment."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = json.loads((ROOT / "src-tauri/src/safety/knowledge.json").read_text(encoding="utf-8"))
SYSTEM_PROMPT = (
    "你是一个帮普通用户看懂电脑文件的助手。根据完整路径解释这个{kind}的用途、删除影响和处理建议。\n"
    "像懂电脑的朋友一样，用两到四句自然中文回答，不用固定标签或重复安全判定。\n"
    "优先依据用途资料，不补写资料没有说明的具体功能或恢复保证；没有匹配资料时明确说无法确定。\n"
    "规则判定是{verdict}。路径不足以确认用途时直说无法确定，不要编造软件名、功能或恢复方式。涉及个人数据时先提醒确认备份。"
)


def retrieve(path):
    normalized = path.lower().replace("/", "\\").rstrip("\\") + "\\"
    return next((entry for entry in KNOWLEDGE["entries"]
                 if all(pattern in normalized for pattern in entry["patterns"])), None)


def build_sample(path, is_dir, size="200 MB", use_rag=True, facts=None):
    entry = retrieve(path)
    safety = entry["safety"] if entry else "yellow"
    kind = "文件夹" if is_dir else "文件"
    verdict = {"red": "千万别删", "yellow": "看看再删", "green": "可清理"}[safety]
    desc = {
        "red": "系统核心文件，删除可能导致系统崩溃或无法启动",
        "yellow": "用途或删除影响需要确认，可能包含软件或个人数据",
        "green": "疑似可清理的缓存、临时文件或残留，仍需确认是否在用或需要保留",
    }[safety]
    parts = path.replace("/", "\\").split("\\")
    parent = "\\".join(parts[-4:-1] if len(parts) > 3 else parts[:-1])
    text = (f"{kind}名：{parts[-1]}\n完整路径：{path}\n所在目录：{parent}\n"
            f"大小：{size}\n初步分类：{desc}")
    if use_rag:
        if facts is None:
            facts = entry["facts"] if entry else KNOWLEDGE["unknown"]
        text += "\n\n用途资料：\n" + facts
    return {"instruction": SYSTEM_PROMPT.format(kind=kind, verdict=verdict), "input": text}


if __name__ == "__main__":
    for entry in KNOWLEDGE["entries"]:
        assert entry["patterns"] and entry["facts"] and entry["answer"] and entry["source"]
        for path in entry["examples"]:
            assert retrieve(path)["id"] == entry["id"], path
            assert retrieve(path.replace("\\", "/").upper())["id"] == entry["id"]
    assert retrieve(r"C:\Users\Test\AppData\Local\pip\cache-backup\notes.bin") is None
    assert retrieve(r"C:\Program Files\Microsoft\UnknownApp\data.bin") is None
    print("Shared knowledge and component-boundary retrieval checks passed")
