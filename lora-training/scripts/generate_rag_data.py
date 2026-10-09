"""Generate evidence-based SFT data; leave the pure-SFT corpus intact."""
import json
from grounding import ROOT, KNOWLEDGE, build_sample


def generate():
    samples = []
    unknown_answer = ("仅凭这个文件名和路径，无法确定它的具体用途，也不能保证删除后能恢复。"
                      "如果要清理，先通过创建它的软件确认内容，并备份需要保留的数据。")
    for index, entry in enumerate(KNOWLEDGE["entries"]):
        for path in entry["examples"]:
            for variant in range(6):
                path_variant = path.replace("Example", f"Train{variant}").replace("145.0.1000.1", f"144.0.900.{variant}")
                is_dir = path_variant.rsplit("\\", 1)[-1] in {"cache", "node_modules"}
                sample = build_sample(path_variant, is_dir, size=f"{100 + 50 * variant} MB")
                sample.update(output=entry["answer"], confidence="high", group=entry["id"], evidence="relevant")
                samples.append(sample)
            # Train against one unrelated snippet, both with and without the relevant evidence.
            distractor = KNOWLEDGE["entries"][(index + 1) % len(KNOWLEDGE["entries"])]
            for facts, answer, evidence in [
                (entry["facts"] + "\n另一个路径的资料（可能不相关）：\n" + distractor["facts"], entry["answer"], "mixed"),
                ("没有与当前路径匹配的资料。以下资料来自另一个路径，不可据此猜测当前文件：\n" + distractor["facts"], unknown_answer, "irrelevant"),
                (KNOWLEDGE["unknown"], unknown_answer, "missing"),
            ]:
                sample = build_sample(path.replace("Example", "Training"), is_dir, facts=facts)
                sample.update(output=answer, confidence="high", group=entry["id"], evidence=evidence)
                samples.append(sample)
    for username in ["TrainA", "TrainB", "TrainC", "TrainD"]:
        for suffix in [r"Documents\collection.bin", r"Documents\cache\entry.db", r"Downloads\backup.zip",
                       r"AppData\Local\UnlistedApp\data.db", r"AppData\Local\Microsoft\UnlistedApp\unknown.bin",
                       r"AppData\Local\pip\cache-backup\entry.body"]:
            sample = build_sample(fr"C:\Users\{username}\{suffix}", False)
            sample.update(output=unknown_answer, confidence="high", group="unknown", evidence="missing")
            samples.append(sample)
    output = ROOT / "lora-training/data/rag_training_data.jsonl"
    for sample in samples:
        assert "{verdict}" not in sample["instruction"] and sample["output"]
    output.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in samples), encoding="utf-8", newline="\n")
    print(f"Generated {len(samples)} grounded samples in {output}")


if __name__ == "__main__":
    generate()
