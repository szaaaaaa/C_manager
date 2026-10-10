# 本轮方法边界补充

2026-10-10再次核对[Unsloth官方Qwen3.5训练指南](https://unsloth.ai/docs/models/qwen3.5/fine-tune)：指南列出的4B BF16 LoRA显存参考为10GB，并仍提醒Qwen3.5的4-bit QLoRA可能有较大的量化差异。本轮继续使用上一轮本机验证过的固定NF4软件环境来比较数据干预，不更新依赖，也不把运行成功解释为消除量化误差或满足显存余量。

[RAG感知训练的RAFT原论文](https://arxiv.org/abs/2403.10131)提供相关与干扰资料训练的研究动机。原论文包含资料引用及推理式目标，本轮仅借鉴干扰资料暴露，使用直接中文解释与拒猜样本，不是RAFT完整复现，也不援用其任务或分数证明本项目有效。

新增npm与Git的官方来源保存在sources.json；旧八家族用途支持范围沿用[上一轮审计](https://github.com/szaaaaaa/C_manager/blob/main/lora-training/experiments/2026-10-10/knowledge-source-audit.md)。本轮修订facts只是范围内的用途说明与保守条件，不检查用户实际文件的内容、运行依赖或备份状态。
