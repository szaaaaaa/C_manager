# exp_007 actual failure

Unified exec session 53380 exited 1 after 121.34 seconds, with 0 optimizer steps. Transformers 5.3/TRL 0.24 rejected the removed `save_safetensors` SFTConfig argument. This was a trainer construction compatibility failure, not a successful smoke or an OOM.

Actual 346 Linear4bit modules were NF4 + double quant + bf16; maximum tokenized length 429 and prompt/padding masking passed. No gradient/adapter-change/base-unchanged validation completed. Peak allocated 8089.11 MiB and reserved 8172 MiB were loading/setup peaks and exceeded the 7168 MiB preregistered target. Cold Unsloth import/patching took 86.96 seconds, model loading 15.62 seconds, setup 8.12 seconds; these are phase timings, not isolated compiler timings.

The original runner is preserved as `executed_training.py`. exp_011 is the single permitted compatibility rerun: omit the removed serialization argument; adapter saving still explicitly uses safetensors. Same base revision, NF4 settings, r8 attention adapters, 8 records and 2 steps. No hyperparameters or evaluation gold answers changed. If successful, downstream executed_config must explicitly substitute exp_011 smoke evidence for failed exp_007.

The log reports unavailable fla/causal-conv fast path, falling back to Torch. No native C++ extension build was observed; subsequent shells explicitly set TORCH_EXTENSIONS_DIR on D. No deployment/export is attempted.
