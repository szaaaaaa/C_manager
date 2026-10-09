"""Fixed RAG-SFT experiment; starts from fresh base weights, never from pure-SFT weights."""
import argparse
from pathlib import Path
import finetune

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", required=True, type=Path)
    args = parser.parse_args()
    assert args.base_model.is_dir(), "Download the fresh base model before running this experiment"
    finetune.BASE_MODEL = str(args.base_model.resolve())
    finetune.OUTPUT_DIR = finetune.PROJECT_ROOT / "output/rag_model"
    finetune.GGUF_DIR = finetune.PROJECT_ROOT / "output/rag_model_gguf"
    finetune.EPOCHS = 2
    finetune.LEARNING_RATE = 1e-4
    finetune.WARMUP_STEPS = 5
    finetune.SAVE_STEPS = 10
    finetune.main()
