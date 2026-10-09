"""Run a fixed greedy BF16 ablation; automated cues are not factual accuracy."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from grounding import ROOT, KNOWLEDGE, build_sample, retrieve


def check_response(case, answer):
    missing = [group for group in case["required"] if not any(word in answer for word in group)]
    forbidden = [word for word in case["forbidden"] if word in answer]
    return {"cue_pass": bool(answer.strip()) and not missing and not forbidden,
            "missing_cues": missing, "forbidden_phrases": forbidden}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Local merged model directory")
    parser.add_argument("--mode", required=True, choices=["plain", "rag"])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    probe = {"required": [["无法", "不确定"], ["备份"]], "forbidden": ["放心删"]}
    assert check_response(probe, "无法确定用途，先备份。")["cue_pass"]
    assert not check_response(probe, "无法确定用途，备份后放心删。")["cue_pass"]
    cases_path = ROOT / "lora-training/data/eval_cases.json"
    cases_bytes = cases_path.read_bytes()
    cases = json.loads(cases_bytes)
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        entry = retrieve(case["path"])
        assert (entry["id"] if entry else None) == case["knowledge"], case["id"]

    from unsloth import FastLanguageModel
    import torch
    import transformers
    torch.manual_seed(42)
    model, processor = FastLanguageModel.from_pretrained(
        model_name=str(Path(args.model).resolve()), max_seq_length=2048,
        load_in_4bit=False, load_in_16bit=True, local_files_only=True)
    FastLanguageModel.for_inference(model)
    tokenizer = processor.tokenizer
    results = {
        "model": str(Path(args.model).resolve()), "mode": args.mode,
        "precision": "BF16", "generation": {"do_sample": False, "max_new_tokens": 256, "seed": 42, "use_cache": True},
        "gpu": torch.cuda.get_device_name(), "torch": torch.__version__, "transformers": transformers.__version__,
        "cases_sha256": hashlib.sha256(cases_bytes).hexdigest(),
        "knowledge_sha256": hashlib.sha256((ROOT / "src-tauri/src/safety/knowledge.json").read_bytes()).hexdigest(),
        "records": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    entries = {entry["id"]: entry for entry in KNOWLEDGE["entries"]}
    for case in cases:
        facts = None
        if case.get("missing_evidence"):
            facts = KNOWLEDGE["unknown"]
        elif case.get("distractor"):
            facts = entries[case["knowledge"]]["facts"] + "\n另一个路径的资料（可能不相关）：\n" + entries[case["distractor"]]["facts"]
        sample = build_sample(case["path"], case["is_dir"], use_rag=args.mode == "rag", facts=facts)
        messages = [{"role": "system", "content": sample["instruction"]}, {"role": "user", "content": sample["input"]}]
        inputs = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
            enable_thinking=False, return_dict=True, return_tensors="pt").to(model.device)
        torch.cuda.synchronize()
        start = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=256, do_sample=False, use_cache=True)
        torch.cuda.synchronize()
        seconds = time.perf_counter() - start
        answer = tokenizer.decode(generated[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
        record = {"id": case["id"], "path": case["path"], "answer": answer,
                  "seconds": round(seconds, 4), "input_tokens": inputs.input_ids.shape[1],
                  "output_tokens": generated.shape[1] - inputs.input_ids.shape[1], **check_response(case, answer)}
        results["records"].append(record)
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(record, ensure_ascii=False), flush=True)
    print(f"Automatic cue checks: {sum(r['cue_pass'] for r in results['records'])}/{len(cases)}; review facts manually")


if __name__ == "__main__":
    main()
