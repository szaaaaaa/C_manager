# Experiment: exp_008

**Objective**: 可行性通过后探索4B检索感知SFT，提高证据使用并保持未知用途校准。
**Dataset**: 168 RAG样本整家族split，150训练/pip-cache18验证；24测试不参与训练、选checkpoint或改参数。
**Model**: fresh锁定Qwen3.5-4B HF base，NF4冻结、bf16计算、rank8 alpha8 q/k/v/o adapter dropout0；不是GGUF。
**Metric**: 完成38 optimizer steps、finite loss/grad、无OOM；target heldout eval_loss不高于step0。用途/风险/自然度由exp_009/010同NF4评估。
**Compute budget**: RTX5070 Laptop8GB CUDA，1740s含加载/编译/验证/保存；seq768、batch1×accum4，1epoch/38steps先到。
**Hypothesis**: 包含相关/不相关/缺失资料的SFT可能改善证据依赖；短训练和固定输出可能無收益或加重样板。

exp_007检查全部通过才启动；同revision fresh base、seed42新adapter。LR5e-5、warmup3、cosine、adamw8bit、checkpointing，packing=false。完整168条预tokenize不截断，mask所有prompt/padding，只assistant answer/EOS loss。step0及19/38记录18验证NLL，只以验证loss选择checkpoint。记录全sample索引/家族、长度分布、mask自检、实际steps/epoch、每步loss/grad、VRAMpeak、墙钟/exitcode。超时保留partial而非声称38步完成。只保存adapter/tokenizer，不默认GPU merge或GGUF导出；不追加测试答案。见[总计划](../../plan.md)。
