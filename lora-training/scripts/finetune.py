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
import os
import json
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
TRAINING_DATA = PROJECT_ROOT / "data" / "training_data.jsonl"
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
            entry = json.loads(line.strip())
            # Strip confidence/verify_hint — only keep instruction/input/output
            samples.append({
                "instruction": entry["instruction"],
                "input": entry["input"],
                "output": entry["output"],
            })
    print(f"Loaded {len(samples)} training samples")
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
            messages, tokenize=False, add_generation_prompt=False
        )
        formatted.append({"text": text})
    return formatted


def main():
    # ============================================================
    # 1. Load model with Unsloth
    # ============================================================
    print("Loading model with Unsloth...")
    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,       # auto-detect (bfloat16 on RTX 5070)
        load_in_4bit=True,   # QLoRA: 4bit quantized base + bf16 LoRA adapters, saves ~1GB VRAM
    )

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
    formatted = format_for_chat(raw_samples, tokenizer)
    dataset = Dataset.from_list(formatted)
    print(f"Dataset: {len(dataset)} samples")

    # Preview one sample
    print("\n--- Sample preview ---")
    print(dataset[0]["text"][:500])
    print("--- end preview ---\n")

    # ============================================================
    # 4. Train
    # ============================================================
    print("Starting training...")
    from trl import SFTTrainer
    from transformers import TrainingArguments

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=TrainingArguments(
            output_dir=str(OUTPUT_DIR / "checkpoints"),
            num_train_epochs=EPOCHS,
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRAD_ACCUM,
            learning_rate=LEARNING_RATE,
            warmup_steps=WARMUP_STEPS,
            logging_steps=LOGGING_STEPS,
            save_steps=SAVE_STEPS,
            save_total_limit=2,
            bf16=True,
            optim="adamw_8bit",
            lr_scheduler_type="cosine",
            seed=42,
            report_to="none",  # no wandb
        ),
        max_seq_length=MAX_SEQ_LENGTH,
    )

    stats = trainer.train()
    print(f"\nTraining complete!")
    print(f"  Total steps: {stats.global_step}")
    print(f"  Training loss: {stats.training_loss:.4f}")

    # ============================================================
    # 5. Save merged model
    # ============================================================
    print(f"\nSaving merged model to {OUTPUT_DIR}...")
    model.save_pretrained_merged(
        str(OUTPUT_DIR),
        tokenizer,
        save_method="merged_16bit",
    )
    print("Merged model saved.")

    # ============================================================
    # 6. Export to GGUF for Ollama
    # ============================================================
    print(f"\nExporting to GGUF (Q4_K_M) for Ollama...")
    model.save_pretrained_gguf(
        str(GGUF_DIR),
        tokenizer,
        quantization_method="q4_k_m",
    )
    print(f"GGUF model saved to {GGUF_DIR}")

    # ============================================================
    # 7. Print Ollama import instructions
    # ============================================================
    gguf_files = list(GGUF_DIR.glob("*.gguf"))
    if gguf_files:
        gguf_path = gguf_files[0]
        modelfile_path = GGUF_DIR / "Modelfile"
        modelfile_content = f'''FROM {gguf_path.name}

PARAMETER temperature 0.3
PARAMETER num_predict 500

SYSTEM """你是一个帮普通用户看懂电脑文件的助手。用大白话解释文件是什么、属于哪个软件、能不能删。语气像一个懂电脑的朋友。"""
'''
        with open(modelfile_path, "w", encoding="utf-8") as f:
            f.write(modelfile_content)

        print(f"\n{'='*60}")
        print("DONE! To import into Ollama:")
        print(f"{'='*60}")
        print(f"  cd {GGUF_DIR}")
        print(f"  ollama create c-manager-assistant -f Modelfile")
        print(f"  ollama run c-manager-assistant")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
