# Experiment: exp_010

**Objective**: 同HF revision/NF4/CUDA runtime测有adapter的RAG解释，隔离LoRA效果。
**Dataset**: 全24冻结eval cases，逻辑输入同exp_002但runtime/量化不同；不含registry answer。
**Model**: 同锁定Qwen3.5-4B NF4/double-quant、bf16计算，有adapter；adapter只能来自exp_008验证loss选定checkpoint。
**Metric**: cue_pass_count target>=21/24（非准确率）；用途有依据或未知校准正确>=22、危险主张0、自然度mean>=4、median<=10s，逐条配对得失。
**Compute budget**: RTX5070 Laptop8GB CUDA，1740s含加载/编译/暖机，greedy256新token、thinking=false、use_cache=true，GPU串行。
**Hypothesis**: SFT可能改善依据资料回答，也可能无收益或强化模板；NF4 base提供不可缺少的量化一致对照。

使用同tokenizer模板、相同distractor/missing处理，adapter开关为唯一变化。保留raw answer/tokens/time/finish reason与逐条cue、实际GPU和版本。不要把exp_002与exp_010的不同全归于SFT；NF4结果不能替代GGUF部署验收。完整控制及失败状态见[总计划](../../plan.md)。
