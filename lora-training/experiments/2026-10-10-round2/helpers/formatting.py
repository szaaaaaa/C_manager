"""Copied existing helper functions without project-relative input side effects."""
MAX_SEQ_LENGTH = 768
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
