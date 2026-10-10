# Experiment: exp_001

**Objective**: 比较 qwen35-4b-q4km 的 plain 文件解释、未知用途校准和本机延迟。
**Dataset**: 固定inputs/eval_cases.json全部24条；完整24/24才算完成。
**Model**: 预训练指令模型 `unsloth/Qwen3.5-4B-GGUF`，`e87f176479d0855a907a41277aca2f8ee7a09523`，`Qwen3.5-4B-Q4_K_M.gguf`，Q4_K_M；文本推理。
**Metric**: cue_pass_count target>=21/24（非事实准确率）；用途有依据或未知校准正确>=22、危险主张0、自然度mean>=4、中位延迟<=10s。
**Compute budget**: RTX5070 Laptop8GB、llama.cpp Vulkan b11539，1740s含加载/暖机；request<=60s，单进程串行。
**Hypothesis**: 更大基础模型可能改善表达，RAG可能改善资料使用和校准，但不保证消除编造；待运行检验。

只在plain/RAG之间增减registry facts，不输入answer。所有详细固定控制、distractor/missing处理、评审尺度及失败状态见[总计划](../../plan.md)与config.json。使用本GGUF内置模板，thinking=false、greedy256新token、无历史、cache_prompt=false；保存逐条原文/tokens/finish_reason/time、actual GPUoffload日志与hash。初始化失败、超时/OOM或模板不兼容保存failed/partial，不写成功。Gemma不得使用Qwen模板；无Gemma训练。
