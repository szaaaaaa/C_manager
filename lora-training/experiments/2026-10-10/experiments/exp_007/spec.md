# Experiment: exp_007

**Objective**: 实测4B NF4 QLoRA在8GB GPU和现有环境上能否正确训练。
**Dataset**: 168条全部先tokenize，长度<=768、prompt边界/labels自检；训练150条中seed42次序8条做2步，pip-cache18条留出。
**Model**: 公开Qwen3.5-4B HF base另下载并锁定真实revision，NF4+double quant、bf16计算；冻结base只训练rank8 q/k/v/o adapter；不训练GGUF。
**Metric**: 2optimizer steps、finite loss/gradient、至少一个LoRA权重改变、base未变、prompt/padding label=-100、无OOM、peak allocated<=7168MiB。不是质量评价。
**Compute budget**: CUDA torch2.10cu128、RTX5070 Laptop8GB，1200s硬截止含加载/编译；不与其他GPU任务并行。
**Hypothesis**: seq768/batch1/checkpointing/注意力rank8可能适配8GB；Unsloth/kernel可能不兼容，须以实测决定。

官方不推荐Qwen3.5 QLoRA，4B BF16 LoRA估算10GB；本实验为探索性可行性检查。确认实际Linear4bit NF4/double-quant、trainable全部lora、dtype/device、完整token边界。超长样本直接失败不删/截断。逐步保存loss/gradnorm、显存allocated/reserved/总占用、墙钟和版本。OOM、非法mask、非有限梯度、超时写failed/timed_out，不默默升级或换9B/Gemma。exp_008必须fresh base+adapter重开，不继承smoke两步；smokeadapter不部署。见[总计划](../../plan.md)。
