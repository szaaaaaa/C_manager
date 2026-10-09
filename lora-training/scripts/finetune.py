"""
Fine-tune Qwen3.5 0.8B with LoRA using Unsloth.
Usage: python finetune.py

Requirements:
    pip install unsloth datasets trl peft
    (Unsloth will handle torch + CUDA automatically)

Output:
    output/finetuned_model/       — merged model (safetensors)
    output/finetuned_model_gguf/  — GGUF for Ollama
"""
import json
import hashlib
import importlib.metadata
import random
import subprocess
import sys
import tempfile
from pathlib import Path

# ============================================================
# Config — adjust these if needed
# ============================================================
BASE_MODEL = "unsloth/Qwen3.5-0.8B"  # Unsloth optimized Qwen3.5 0.8B
# Alternatives:
#   "unsloth/Qwen3.5-0.8B"               — 16-bit (recommended, your 8GB VRAM is enough)
#   "unsloth/Qwen3-0.6B"                 — Qwen3 0.6B if you want even smaller
# Unsloth gives ~1.5x faster training + 50% less VRAM vs standard HF training

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRAINING_DATA = PROJECT_ROOT / "data" / "rag_training_data.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "output" / "finetuned_model"
GGUF_DIR = PROJECT_ROOT / "output" / "finetuned_model_gguf"

# LoRA params
LORA_R = 16
LORA_ALPHA = 16  # alpha = r is the recommended setting for Qwen3.5
LORA_DROPOUT = 0.05
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj",
                   "gate_proj", "up_proj", "down_proj"]

# Training params
EPOCHS = 3
BATCH_SIZE = 2
GRAD_ACCUM = 4        # effective batch = 2 * 4 = 8
LEARNING_RATE = 2e-4
MAX_SEQ_LENGTH = 1024  # enough for our short prompts + responses
WARMUP_STEPS = 10
LOGGING_STEPS = 10
SAVE_STEPS = 100


def load_training_data():
    """Load JSONL training data and format for chat template."""
    samples = []
    with open(TRAINING_DATA, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("confidence") != "high" or entry.get("verify_hint"):
                continue
            if "{verdict}" in entry["instruction"]:
                raise ValueError("Unresolved verdict in training data; regenerate it first")
            if not all(entry.get(key, "").strip() for key in ("instruction", "input", "output")):
                raise ValueError("Training samples must contain non-empty instruction/input/output")
            # Strip confidence/verify_hint — only keep instruction/input/output
            samples.append({
                "instruction": entry["instruction"],
                "input": entry["input"],
                "output": entry["output"],
                "group": entry.get("group", entry["output"]),
            })
    print(f"Loaded {len(samples)} training samples")
    if len(samples) < 20:
        raise ValueError("Need at least 20 high-confidence training samples")
    return samples


def format_for_chat(samples, tokenizer):
    """Convert instruction/input/output to chat messages format."""
    formatted = []
    for s in samples:
        messages = [
            {"role": "system", "content": s["instruction"]},
            {"role": "user", "content": s["input"]},
            {"role": "assistant", "content": s["output"]},
        ]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False, enable_thinking=False
        )
        prompt = tokenizer.apply_chat_template(
            messages[:2], tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        if not text.startswith(prompt):
            raise ValueError("Training and inference chat templates do not match")
        tokens = tokenizer.encode(text, add_special_tokens=False)
        prompt_tokens = tokenizer.encode(prompt, add_special_tokens=False)
        if tokens[:len(prompt_tokens)] != prompt_tokens:
            raise ValueError("Prompt token boundary does not match the training sequence")
        if len(tokens) > MAX_SEQ_LENGTH:
            raise ValueError("Training sample exceeds MAX_SEQ_LENGTH; increase it instead of truncating the answer")
        formatted.append({
            "input_ids": tokens,
            "attention_mask": [1] * len(tokens),
            "labels": [-100] * len(prompt_tokens) + tokens[len(prompt_tokens):],
        })
    return formatted


def main():
    # ============================================================
    # 1. Load model with Unsloth
    # ============================================================
    print("Loading model with Unsloth...")
    from unsloth import FastLanguageModel

    model, processor = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,       # auto-detect (bfloat16 on RTX 5070)
        load_in_4bit=False,
        load_in_16bit=True,  # Qwen3.5's linear attention is sensitive to 4-bit training
    )
    tokenizer = processor.tokenizer

    # ============================================================
    # 2. Add LoRA adapters
    # ============================================================
    print("Adding LoRA adapters...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=TARGET_MODULES,
        bias="none",
        use_gradient_checkpointing="unsloth",  # saves VRAM
        random_state=42,
    )

    # Print trainable params
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"Trainable params: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)")

    # ============================================================
    # 3. Prepare dataset
    # ============================================================
    print("Preparing dataset...")
    from datasets import Dataset

    raw_samples = load_training_data()
    # Hold out whole knowledge families instead of leaking their path variants into validation.
    groups = sorted({s["group"] for s in raw_samples})
    random.Random(42).shuffle(groups)
    eval_groups = set(groups[:max(1, len(groups) // 10)])
    dataset = Dataset.from_list(format_for_chat([s for s in raw_samples if s["group"] not in eval_groups], tokenizer))
    eval_dataset = Dataset.from_list(format_for_chat([s for s in raw_samples if s["group"] in eval_groups], tokenizer))
    print(f"Dataset: {len(dataset)} train / {len(eval_dataset)} validation samples")
    print(f"Held-out groups: {sorted(eval_groups)}")

    # Preview one sample
    print("\n--- Sample preview ---")
    print(tokenizer.decode(dataset[0]["input_ids"])[:500])
    print("--- end preview ---\n")

    # ============================================================
    # 4. Train
    # ============================================================
    print("Starting training...")
    from trl import SFTConfig, SFTTrainer
    from transformers import DataCollatorForSeq2Seq
    import torch

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        data_collator=DataCollatorForSeq2Seq(tokenizer=tokenizer),
        train_dataset=dataset,
        eval_dataset=eval_dataset,
        args=SFTConfig(
            output_dir=str(OUTPUT_DIR / "checkpoints"),
            num_train_epochs=EPOCHS,
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRAD_ACCUM,
            learning_rate=LEARNING_RATE,
            warmup_steps=WARMUP_STEPS,
            logging_steps=LOGGING_STEPS,
            save_steps=SAVE_STEPS,
            save_total_limit=2,
            bf16=torch.cuda.is_bf16_supported(),
            fp16=not torch.cuda.is_bf16_supported(),
            max_length=MAX_SEQ_LENGTH,
            eval_strategy="steps",
            eval_steps=SAVE_STEPS,
            load_best_model_at_end=True,
            metric_for_best_model="eval_loss",
            optim="adamw_8bit",
            lr_scheduler_type="cosine",
            seed=42,
            report_to="none",  # no wandb
        ),
    )

    stats = trainer.train()
    validation = trainer.evaluate()
    print(f"Validation: {validation}")
    report = {
        "base_model": BASE_MODEL, "data_sha256": hashlib.sha256(TRAINING_DATA.read_bytes()).hexdigest(),
        "data_sha256_lf": hashlib.sha256(TRAINING_DATA.read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
        "train_samples": len(dataset), "validation_samples": len(eval_dataset), "held_out_groups": sorted(eval_groups),
        "seed": 42, "epochs": EPOCHS, "learning_rate": LEARNING_RATE, "batch_size": BATCH_SIZE,
        "gradient_accumulation": GRAD_ACCUM, "warmup_steps": WARMUP_STEPS,
        "eval_save_steps": SAVE_STEPS, "best_eval_loss": trainer.state.best_metric,
        "best_checkpoint": trainer.state.best_model_checkpoint,
        "lora_r": LORA_R, "lora_alpha": LORA_ALPHA, "lora_dropout": LORA_DROPOUT,
        "target_modules": TARGET_MODULES, "max_length": MAX_SEQ_LENGTH,
        "loss": "assistant response only", "load_in_4bit": False, "load_in_16bit": True,
        "train_steps": stats.global_step, "train_loss": stats.training_loss,
        "train_metrics": stats.metrics, "validation": validation,
        "versions": {name: importlib.metadata.version(name) for name in ["torch", "unsloth", "trl", "transformers"]},
    }
    (OUTPUT_DIR / "training_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"\nTraining complete!")
    print(f"  Total steps: {stats.global_step}")
    print(f"  Training loss: {stats.training_loss:.4f}")

    # ============================================================
    # 5. Save merged model
    # ============================================================
    print(f"\nSaving merged model to {OUTPUT_DIR}...")
    # Training disables the cache; exported HF models should use it for generation.
    model.config.use_cache = True
    model.generation_config.use_cache = True
    model.save_pretrained_merged(
        str(OUTPUT_DIR),
        processor,
        save_method="merged_16bit",
    )
    print("Merged model saved.")

    # ============================================================
    # 6. Export to GGUF for Ollama
    # ============================================================
    print(f"\nExporting to GGUF (Q4_K_M) for Ollama...")
    from unsloth_zoo.llama_cpp import check_llama_cpp, install_llama_cpp

    try:
        quantizer, converter = check_llama_cpp()
    except RuntimeError:
        quantizer, converter = install_llama_cpp(gpu_support=False)
    GGUF_DIR.mkdir(parents=True, exist_ok=True)
    gguf_path = GGUF_DIR / "qwen3.5-0.8b-q4_k_m.gguf"
    # Use the converter shipped with the quantizer; upstream's script layout can change.
    with tempfile.TemporaryDirectory(dir=GGUF_DIR) as directory:
        temporary = Path(directory).resolve()
        assert temporary.is_relative_to(GGUF_DIR.resolve())
        bf16_path = temporary / "model.bf16.gguf"
        q4_path = temporary / gguf_path.name
        subprocess.run([sys.executable, converter, str(OUTPUT_DIR),
                        "--outfile", str(bf16_path), "--outtype", "bf16"], check=True)
        subprocess.run([quantizer, str(bf16_path), str(q4_path), "Q4_K_M"], check=True)
        q4_path.replace(gguf_path)
    print(f"GGUF model saved to {GGUF_DIR}")

    # ============================================================
    # 7. Print Ollama import instructions
    # ============================================================
    if gguf_path.is_file():
        modelfile_path = GGUF_DIR / "Modelfile"
        modelfile_content = f'''FROM {gguf_path.name}

PARAMETER temperature 0.3
PARAMETER num_predict 500

SYSTEM """你是一个帮普通用户看懂电脑文件的助手。依据用户提供的用途资料，用自然中文解释用途、删除影响和建议。未提供匹配资料时说明不确定，不编造具体功能或恢复保证。涉及个人数据先确认备份。"""
'''
        with open(modelfile_path, "w", encoding="utf-8") as f:
            f.write(modelfile_content)

        print(f"\n{'='*60}")
        print("DONE! To import into Ollama:")
        print(f"{'='*60}")
        print(f"  cd {GGUF_DIR}")
        print(f"  ollama create c-manager-assistant -f Modelfile")
        print(f"  ollama run c-manager-assistant")
        print(f"Tauri dev model path: {PROJECT_ROOT / 'output' / 'finetuned_model_gguf' / gguf_path.name}")
        print("Copy the verified experiment model there before restarting the application.")
        print(f"For a release build, copy it to {PROJECT_ROOT.parent / 'src-tauri' / 'resources' / gguf_path.name}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
