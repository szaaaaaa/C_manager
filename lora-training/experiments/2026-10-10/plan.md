# 量化小模型与检索感知微调实验

Run ID `exp_20261010_111944`，设计日期2026-10-10（Asia/Shanghai）。这是预注册设计，尚无模型运行结果。

工作目录 `D:/small-model-experiments`；`D:/C_manager` 为只读数据来源。模型、下载缓存、checkpoint、临时文件、结果全部在D盘，现有C盘Python仅作为可执行运行时读取。

| 分类 | 实验 | 配置 | 单次计算上限 |
|---|---|---|---|
| A 量化推理 | exp_001 / exp_002 | Qwen3.5-4B Q4_K_M，无资料 / RAG | 各1740秒，24案例 |
| A 量化推理 | exp_003 / exp_004 | Qwen3.5-9B Q4_K_M，无资料 / RAG | 同上 |
| A 量化推理 | exp_005 / exp_006 | Gemma4 E4B官方QAT Q4_0，无资料 / RAG | 同上 |
| B 训练可行性 | exp_007 | Qwen3.5-4B NF4+LoRA，2步冒烟 | 1200秒 |
| B 检索感知SFT | exp_008 | 新鲜NF4 base，150训练/18家族验证，最多38步 | 1740秒 |
| C 微调效果控制 | exp_009 / exp_010 | 同NF4 base+RAG，无adapter / 有adapter | 各1740秒，24案例 |

## 固定输入

24案例包括16已知用途路径变体、6未知/近似路径、1干扰资料、1缺失资料。168 RAG训练样本含96 relevant、16 mixed、16 irrelevant、40 missing。按原脚本排序group再seed42 shuffle，整家族留出pip-cache18条，训练150条；验证路径/答案不进入训练，不用24测试案例选checkpoint、调参或补样本。每个config锁定已核对的inputs副本SHA256，不重生成金标准。

plain/RAG均使用原grounding.py中文system、路径、初步规则标签；唯一内容区别是RAG添加knowledge的facts，禁止添加answer。distractor/missing_evidence处理沿用evaluate.py；检索为8类精确路径模式，本轮没有向量检索或联网答案。所有逐条输入和原始回答保留，输出样板集中造成的自然度限制必须报告。

## 推理控制

固定llama.cpp Windows Vulkan b11539，使用每个GGUF内置Jinja模板，文本输入、不加载视觉投影。GPU offload请求99层、context2048、batch512/ubatch128、并发1、线程8、seed42、greedy temperature0、最多256新token、thinking=false。Qwen通过enable_thinking=false；Gemma用其模板，不插入<|think|>。不能把Qwen ChatML套给Gemma；模板/EOS/关闭thinking不成立就记录兼容失败。

加载后用非测试问题“请只回复准备好了”暖机一次最多16token。model_load_seconds和warmup另报，不计入每案例延迟；端到端案例延迟包含请求、prefill、decode。RAG较长prompt是实际开销不能隐藏。每个案例独立、无聊天历史、cache_prompt=false；记录tokens、finish_reason、截断、runtime原始timings、秒数、模型文件SHA和实际offload日志。

每实验1740秒硬截止包含初始化/暖机，load最多180秒、每请求最多60秒。GPU实验串行，失败/超时保留partial result，不得写success。全offload OOM首先记录失败；最多一次另编号的lower-offload重跑，速度明确标为CPU/GPU混合。禁止靠截断问题或更改金标准凑通过。

## 指标与阈值

主可机读诊断cue_pass_count目标>=21/24，使用原required/forbidden检查；它不是事实准确率。可靠性逐条核对用途supported/unsupported/uncertain、处理风险adequate/incomplete/misleading、未知用途校准、危险无条件删除/恢复保证。事先目标：有资料的主张得到支持，或未知/缺失资料时明确校准且不编造，合计>=22/24；6个未知/近似路径加1个缺失资料案例正确拒猜目标7/7；危险主张0、完整24条、空回答/截断0、自然度均值>=4（1僵化或不通顺；3可懂但样板；5自然简洁忠实）、中位端到端延迟<=10秒。

自动诊断与事实/风险/自然度复核分栏，保存reviewer、单条理由和证据。只有助手审阅则明确单助手审阅，不能称人类盲评或专家准确率；关键词通过也要检查pip安装/运行、OneNote恢复绝对化、WebView浏览器混淆等措辞。24案例和8类资料规模小且同领域，不能作统计显著性或广泛泛化主张。

## 训练的可行性与控制

GGUF Q4_K_M/Q4_0为部署推理格式，本轮不对其反传。训练另取公开HF safetensors base `unsloth/Qwen3.5-4B`，官方metadata已锁定revision `3764fa359b9082ea5a1e4a5e3ac3aaf6e9671636`，两个权重分片5329398688 +3990429408 bytes（约9.32GB），实际下载仍需hash清单，加载为bitsandbytes NF4+double quant、bf16计算；冻结base只训练rank8注意力LoRA。NF4与GGUF量化和runtime不同，因此只有exp_009/010同NF4对照可隔离adapter效果，不能把exp_002与exp_010差异全归于SFT。

Unsloth官方列4B BF16 LoRA约10GB、9B约22GB，且不推荐Qwen3.5 QLoRA。8GB机器不启动4B/9B BF16 LoRA或全参数训练；4B NF4短序列、batch1、checkpointing、rank8 q/k/v/o是有OOM/kernel风险的探索实验，不保证能训练。exp_007必须实测有限loss/grad、至少一个LoRA参数改变、base不变、全部prompt/padding label=-100、无OOM才进入exp_008。

seq768，完整tokenize168样本若超长就失败记录长度，不silent truncate或删掉难样本。150训练、18验证，microbatch1×accumulation4、LR5e-5、warmup3、cosine、adamw8bit、1epoch/最多38步、steps19/38评估并保存，只用家族验证NLL选adapter。编译计入1740秒。smoke的2步不继承到正式训练；fresh base+新adapter重开。只保存adapter/tokenizer，不默认GPU BF16 merge/GGUF导出；部署量化差异需以后单独验证。

已实际查看安装目录，Transformers5.3没有gemma4模块，因此Gemma本轮仅新llama.cpp推理，不假装支持旧环境微调；9B也仅推理。不得默默升级或污染原环境。官方HF base revision查询已通过；若下载、hash或本地加载未完成，保持blocked，不把main可变引用伪装成锁定版本。

## 完成与边界

每实验result.json需真实exit_code/status/actual_steps/elapsed_seconds/metrics与原始records，log可追溯。失败/超时/未运行保持failed/timed_out/planned，不捏造结果。完成后才能分析是否支持假设。最多一次兼容性重跑，没有搜索超参。不开在线API、DPO、9B/Gemma训练，不扫描/删除用户文件，不替换已部署C_manager模型。后续GGUF导出和GUI集成未在本轮推理/adapter评估范围。

## 一手资料

- [Unsloth Qwen3.5训练指南](https://unsloth.ai/docs/models/qwen3.5/fine-tune)：显存与QLoRA注意事项。
- [Transformers bitsandbytes](https://huggingface.co/docs/transformers/quantization/bitsandbytes)：NF4、double quant和量化base上训练额外参数。
- [TRL0.24 SFT](https://huggingface.co/docs/trl/v0.24.0/sft_trainer)：loss/masking。
- [Gemma4官方QAT GGUF](https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf)：E4B有效/总参数、system/thinking和QAT。
- [Qwen4B GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF)、[Qwen9B GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF)。
