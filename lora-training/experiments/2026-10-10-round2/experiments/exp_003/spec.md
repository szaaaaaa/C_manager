# Experiment: exp_003 — arm C

**Objective**: 保持B阳性整行与表达，等量替换成4类难负例，40步answer-only NF4 LoRA训练。
**Dataset**: data/train_C.jsonl，160条=96阳性+64阴性；共享validation.jsonl 32条=16阳性+16阴性。合成八旧家族，npm-cache/git-objects词、路径、事实和命令不得暴露。
**Training SHA256**: 704e415120d03262b556a0ac770aa6dadccb24e7a5af69e79d29c0668b77748d
**Validation SHA256**: 6aa827f8c960d7dbfb9156fd0208eb1f822931c98079e6a8333f2034b6d743b0
**Model**: 新鲜载入固定 unsloth/Qwen3.5-4B revision3764fa359b9082ea5a1e4a5e3ac3aaf6e9671636；本地HF safetensors经SHA清单验证，bitsandbytes NF4双重量化、BF16 compute。GGUF不是训练权重。
**Compute budget**: RTX5070 Laptop 8GB / RAM32GB，串行单GPU，硬截止1740秒含加载，超时保留实际失败与部分日志。无8GB余量承诺。
**Status**: 设计，尚未执行，待主代理冻结。
**Metric**: completed_optimizer_steps=40、所有loss/梯度有限且非零、实际训练基座723张量与346quant_state冻结、LoRA张量有更新；验证NLL仅选step20/40较低者，step0只诊断，NLL无解释准确率阈值。无OOM；加载allocated目标≤7168MiB，但上轮已超，不与训练峰混用。
**Hypothesis**: 负例分布干预可能改善近似路径/缺资料/干扰/猜测情况下的拒猜，不能归因单一难度变量。

固定seed42，rank8/alpha8 q/k/v/o、dropout0，LR5e-5、warmup3、cosine、AdamW8bit、batch1×accum4、40步（一epoch）、seq768、packing=false、answer-only mask。每臂新初始化adapter，不接续上轮或前一臂权重。实际tokenizer预检所有目标与输入超768即失败，不截断/丢行。使用共有行顺序及同system prompt。step20/40保存adapter并验证，按共享32条NLL选；72评测从不用于选择。

保存实际executed_config、脚本hash、step0/20/40 NLL、逐步loss/grad与时间、加载/训练分别的allocator峰、nvidia设备采样、量化模块与参数/quant_state快照、选中adapter文件SHA/存储dtype、原始stdout/exit。准备期dtype变化与实际训练区间冻结分开，不把失败断言推成具体原因；num_items_in_batch警告若出现原样保留。失败或超时不用success，后续eval依赖未就绪则blocked。配置与运行器由training角色负责，本spec不制造执行结果。见[完整计划](../../plan.md)。
