# 三种量化小模型：阶段实证分析

范围为exp_001至006三种模型各plain/RAG两组，每组固定24案例，均已实际success且driver exit_code=0，合计144条。此处程序完成不等于可靠性达标。微调可行性、训练及NF4 adapter效果不在本文件结论范围。

以下质量计数为同一助手可见模型与条件后的逐条复核，标准沿用analysis-4b.md与review definitions；不是人类盲评、专家事实准确率或总体安全率。严格资料忠实性同时扣除有明显资料矛盾和未经资料验证的额外细节，必须配合事后错误分解读。

| 模型与条件 | 实验 | cue诊断/24 | 严格资料忠实性/24 | 未知拒猜/7 | 危险清理主张 | 自然度/5 | 中位请求秒 |
|---|---|---:|---:|---:|---:|---:|---:|
| Qwen3.5-4B Q4_K_M plain | exp_001 | 10 | 2 | 3 | 6 | 3.167 | 1.21955 |
| Qwen3.5-4B Q4_K_M RAG | exp_002 | 18 | 14 | 5 | 0 | 3.708 | 1.34800 |
| Qwen3.5-9B Q4_K_M plain | exp_003 | 12 | 5 | 2 | 5 | 3.125 | 1.75460 |
| Qwen3.5-9B Q4_K_M RAG | exp_004 | 24 | 10 | 2 | 1 | 3.708 | 1.59840 |
| Gemma4 E4B QAT Q4_0 plain | exp_005 | 6 | 6 | 1 | 6 | 3.500 | 1.05215 |
| Gemma4 E4B QAT Q4_0 RAG | exp_006 | 17 | 17 | 3 | 0 | 3.833 | 0.86450 |

预注册质量目标为严格资料忠实性>=22/24、未知校准7/7、危险清理主张0、自然度>=4。没有一组同时达成这些目标。cue目标21/24只有9B RAG达到（24/24），但这不能替代语义和风险复核。所有组完整24条、空答/截断/thinking leak均0、中位请求延迟均<=10秒；这些是运行条件下的可用性指标，不能证明解释可靠。

## Findings

1. 加用途资料在三个配对中都提高严格资料忠实性，但仍不足：4B 2→14、9B 5→10、Gemma 6→17。每对的模型文件SHA、runtime SHA、generation、engine和实际设备均匹配；区别是检索得到的facts输入，因此只可描述本轮资料条件收益，不是训练收益。依据：各对executed_config.json和reviews/exp_001至006.json，144个回答SHA与原始records逐条一致。

2. 9B的cue满分不等于全正确：OneNote-file把可能丢失变为“会导致...永久丢失”，未确认的UnlistedProduct、onnx、cache-backup和缺资料OneNote仍补写内容/来源。9B RAG的明确资料矛盾比其plain 5→1，说明一些关键关系改善；其unknown严格拒猜仍2/7。依据：reviews/exp_003、004与相应原文，特别是onenote-file、unknown-microsoft、unknown-onnx、cache-prefix-nearmiss、onenote-missing-evidence。

3. Gemma RAG在这组小案例中未出现本定义的明确资料矛盾或危险清理主张，正确表达WebView2桌面应用依赖和OneNote未同步修改可能丢失；但严格资料忠实性17/24、未知拒猜3/7仍未达标。archive.bin仍被称二进制归档，cache-backup被当pip缓存备份，onnx推理用途及缺资料临时文件角色仍由命名猜出。0危险主张只对应本定义和样本，不能保证部署安全。依据：reviews/exp_005、006，特别是webview-dll/exe、onenote-folder/file和四个拒猜失败案例。

4. 没有单一全面胜者：4B RAG严格未知拒猜5/7高于9B 2/7和Gemma 3/7，但明确资料矛盾7条；Gemma RAG此样本的矛盾0与严格忠实性17较好；9B RAG cue最好但有1条矛盾、13条未支持额外细节。不同评分衡量不同方面，不用关键词成绩选择部署模型。依据：主表及下方事后分解。

5. 自然度相对plain改善，但三个RAG均未到4：4B与9B约3.708，Gemma见主表。回答普遍可读，但仍反复“这个文件是/如果删除/建议先确认备份”，近似案例模板复用明显；Gemma语言较口语，未知案例仍有猜测与不完整处理建议。评分是单助手主观尺度，不是用户满意度。依据：各review自然度分与原文理由。

## 事后解释性错误分解

下表保持所有主要目标与原评分不变，只对失败原因作事后解释；不属于新增主要目标或统计检验。clearly_incorrect_claim只用于直接与给定facts/条件范围/操作顺序冲突，不把CPU/CUDA常识或未知物理文件的内容推断称已证实错误。

| 实验 | reference_contradiction | unsupported_extra | calibrated_or_supported |
|---|---:|---:|---:|
| exp_001 | 7 | 15 | 2 |
| exp_002 | 7 | 3 | 14 |
| exp_003 | 5 | 14 | 5 |
| exp_004 | 1 | 13 | 10 |
| exp_005 | 5 | 13 | 6 |
| exp_006 | 0 | 7 | 17 |

CPU/CUDA具体功能、某文件核心/主脚本角色、是否个人数据和官方文档是否解释某文件等未验证细节，会使严格忠实性失败但不一定在真实世界为假。4B阶段已记录此尺度限制，001/002没有为后续模型成绩改分。参考矛盾计数同样不等于所有事实错误都被检出：没有独立资料的主张只能列未支持。

## 资源、速度与运行证据

| 实验 | 加载秒 | 暖机秒 | 本轮总秒 | 峰值全GPU采样MiB |
|---|---:|---:|---:|---:|
| exp_001 | 7.7337 | 4.5020 | 59.9546 | 2798 |
| exp_002 | 3.5885 | 0.0922 | 51.0442 | 2802 |
| exp_003 | 8.1810 | 0.4569 | 61.7791 | 5065 |
| exp_004 | 5.6535 | 0.1531 | 54.0123 | 5069 |
| exp_005 | 12.9365 | 2.5885 | 60.5425 | 2872 |
| exp_006 | 5.1446 | 0.1406 | 47.6946 | 2876 |

- 全部使用同一llama.cpp Windows Vulkan b11539、RTX5070 Laptop显式Vulkan1、上下文2048、greedy最多256新token、同model内置Jinja模板。每个模型的chat模板和tokenizer不同，输入token长度与输出长度会不同；Gemma QAT Q4_0与Qwen Q4_K_M也不同。不能把跨模型差异仅归因参数量。Gemma E4B有效参数命名和每层输入embedding结构不等于普通4B模型相同总权重/运算。依据：executed_config.json与server.log model metadata。
- 003/004日志明确offloaded 33/33 layers，同时CPU_Mapped model buffer=545.62MiB、Vulkan1 model buffer=4861.28MiB；005/006日志offloaded 43/43 layers，同时CPU_Mapped=2730.00MiB、Vulkan1=2696.04MiB。层数offload不等于所有权重都驻留显存；不能称Gemma纯GPU全部权重或从5.15GB文件推算显存。001/002较低日志级别没有同样层数证据，只能报命令请求与采样。
- 峰值nvidia-smi全设备占用按1Hz采样，含后台显示负载且可能遗漏瞬时峰值，不是进程精确最大分配；RAM使用未连续采样。本轮短上下文能运行，不外推长上下文/并发或训练显存。
- 所有raw_response cache_n=0，且无聊天历史；中位延迟含请求+prefill+decode、排除加载/暖机。首次运行编译/热身效果和固定执行顺序影响延迟，总时长也受不同回答长度影响，没有重复随机顺序基准，不能称RAG或某架构普遍更快。
- driver均exit_code=0并24条完整；server退出码1来自受控结束，003至006有terminated_by_driver=true，不把该服务终止码改为0。模型/输入hash、实际配置和原始timings保留可审计。

## Conflicts 与限制

- strict忠实性与常识用途正确率不同；关键词通过与用途校准不同；风险incomplete/misleading也不等于unsafe必真。各定义和逐条理由必须随表一起保留。
- 仅24个固定路径、8类用途资料；未知6+缺资料1占7条，且全部体积设为200MB。没有真实磁盘文件内容读取、创建软件核验、独立人类盲评或统计显著性推断，不能声称能可靠覆盖电脑所有文件。
- RAG是8类路径模式资料库检索，不是向量检索或原始RAG论文的Wikipedia系统。检索输入只用facts而不提供answer，但模型仍可能依靠目录/文件名先验覆盖或补写资料。
- 历史0.8B的训练、量化与运行时不同，本轮不证明参数增大本身改善效果；Qwen4B/9B也未保持训练来源与各项结构容量因素完全不变。
- 未更换C_manager已部署模型、未进行文件清理、未把本轮适配器训练成功作为前提。本文件是六组量化推理阶段分析，最终训练结论需对应实际实验结果。

## Open questions

- 训练能否减少未知目录/文件名先验补写，同时保持OneNote风险条件和WebView独立性？等待相同NF4 runtime下base与adapter的真实对照，不能用GGUF RAG与NF4 adapter差异代替。
- 需要独立人类复核主张与自然度，并加入更多真实文件内容、来源核验及路径边界案例，才能评估部署可靠性；不能为本轮测试答案专门添加资料/改阈值。
- 文献或模型指南对Qwen3.5 QLoRA量化差异的担忧，在这台8GB设备实际训练是否表现为OOM、kernel错误或质量下降？本文件不提前给训练成功/失败结论。

逐条证据：[4B阶段分析](analysis-4b.md)，以及reviews/exp_001.json至exp_006.json；每份review含24个id、完整answer、SHA256、引用facts、具体理由、危险主张/自然度和事后错误类型。原始结果位于experiments/exp_001至006/result.json与records.jsonl。
