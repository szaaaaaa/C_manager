# exp_014: diagnostic follow-up to exp_009

Dataset, base revision, seed42, frozen data hashes, model quantization, LoRA and training/generation parameters are identical to exp_009. Old failed/blocked results stay unchanged. Budget: 1740 seconds including hashing, compilation and execution, serialized GPU.

exp_012 records frozen base parameter name/dtype/shape/raw hash and float32 numerical hash before Trainer, after Trainer, after step0 preparation and after actual training. The freeze baseline starts after Trainer preparation and step0, before optimization; optimizer and requires_grad must contain only LoRA. Every changed base name/count and adapter count is persisted before raising. Training-period base raw values, dtype, shape and quantization state must remain unchanged. Preparation conversions are recorded separately, never mistaken for optimizer updates. Same8-record/2-step smoke; no hyperparameter changes.

exp_013 requires successful exp_012 and restarts fresh base and adapter;150 train/18 whole pip-cache heldout;38 steps; only validation NLL selects checkpoint. exp_014/015 use same NF4 base and RAG generation without/with exp_013 adapter. Explicit tokenizer EOS is validated against assistant-turn chat template and recorded against original generation/text config. Both conditions have identical warmup and generation. Base state after warmup/before tests is saved with one-to-one normalized names; adapter dtype is recorded. Original24 test cases are not used for tuning. Raw generated special tokens are retained and unexpected thinking blocks success.

Actual allocator peaks are separated into load, setup/step0 and training; sparse nvidia-smi samples are device totals rather than process memory. No resource-margin claim follows solely from successful execution.
