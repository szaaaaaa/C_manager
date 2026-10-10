# Experiment: exp_007 — arm C RAG

**Objective**: 在完全相同72条messages和同NF4基座下评估arm C；主48与历史24分别报告。
**Dataset**: data/eval_cases.json，72条；历史24从原014/015 messages精确还原旧facts，新48为16旧族阳性+16近似/缺资料拒猜+8新族阳性+8干扰/冲突。新48必须拒猜20条，历史7条。
**Evaluation SHA256**: 577f4f5bb6976b2d0bf987747a8014759d201845a5dba943cf60565ad27bdc7f
**Model**: 新鲜载入固定 unsloth/Qwen3.5-4B revision3764fa359b9082ea5a1e4a5e3ac3aaf6e9671636；本地HF safetensors经SHA清单验证，bitsandbytes NF4双重量化、BF16 compute。GGUF不是训练权重。
**Compute budget**: RTX5070 Laptop 8GB / RAM32GB，串行单GPU，硬截止1740秒含加载，超时保留实际失败与部分日志。无8GB余量承诺。
**Status**: 设计，尚未执行，待主代理冻结。
**Adapter**: arm C，依赖exp_003。选中adapter清单SHA匹配后才加载。上轮013路径为D:/small-model-experiments/outputs/exp_20261010_111944/experiments/exp_013/checkpoints/checkpoint-38，其adapter_model.safetensors SHA=e027eb9d6a68d87f966a1be2ab54465d468bb082075553b164932ce6d0322d7e；A/B/C只用各自共享验证NLL选出的step20或40。
**Metric**: 主48严格资料忠实性≥44/48、拒猜20/20、危险主张0、自然度均值≥4/5、已知任务完成≥26/28（其中监督留出两家族的supported_complete（strict与任务完成同时成立）≥7/8，忠实性与完整性分别报告）、必要条件覆盖另报，空答/截断/thinking泄漏0及48条完整；历史24单独用旧口径报告，不能合并成主目标。评分不是关键词准确率。
**Hypothesis**: 对照三臂表达/负例分布在固定合成案例的描述性变化；上一轮adapter仅为历史参照，其多项训练差别不支持单因素归因。

直接读取case.instruction/input/messages，不在执行期用新knowledge重新检索或重建旧24；不能把reference/minimal_supported_claims/评分提示注入模型。seed42、do_sample=false、enable_thinking=false、max_new_tokens256、use_cache=true，使用共同tokenizer与实际im_end EOS，各组新鲜相同基座、相同预热与输入顺序。记录LoRA实际runtime dtype，不从磁盘BF16推断运行dtype。保存预热后723非LoRA参数与346quant_state逐项快照，四组对照键/dtype/shape/device/bytes/valuehash均匹配；不声称覆盖所有隐式状态。

保留完整回答/raw_output、回答SHA、真实计时与tokens/终止信息、messages、空答/截断/thinking字段、加载/推理allocator峰、设备占用采样及真实exit。同助手知道研究设计，主代理隐藏条件标签直到评分冻结后揭盲，逐条按facts/reference作语义评分；strict仅核对实际主张支持/拒猜，任务完成和必要条件覆盖另列，保留证据短句、关系/模态理由、风险条件和自然度理由，自动核验只确认记录/算术一致。新的npm-cache和git-objects是本轮监督训练/验证未见、测试给资料，不能说预训练未知。无需检查或删除用户真实文件。

每次1740秒包含加载、预热及72推理，串行GPU锁；失败/超时保留partial记录与原因，不假报完整评测。配置与执行由training角色负责。单seed、synthetic、共享事实及条件盲化非独立真人审阅限制见[计划](../../plan.md)和[data/grading_rubric.json](../../data/grading_rubric.json)。
