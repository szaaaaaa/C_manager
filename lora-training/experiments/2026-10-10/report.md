# 小模型 RAG 与量化微调：最终实验报告

2026-10-10（Asia/Shanghai），run `exp_20261010_111944`。本轮完成三种GGUF量化模型的六组推理、4B NF4+LoRA真实38步训练，以及同NF4基座的无/有adapter配对评测。适配器使严格资料忠实性从13/24到17/24、自然度从3.666667到3.833333；未知拒猜仍6/7、关键词诊断23→19。**技术实验已完成，完整可靠性及加载显存余量目标未达成。** 这些分数不是现实文件用途准确率或部署安全保证。

## 研究问题、指标与证据口径

目标是检验较大本地量化模型、可核对用途资料和少量检索感知SFT，是否改善中文文件解释、未知用途校准、删除风险与僵化表达。固定24个合成路径包括16个已知用途变体、6个未知/近似路径、1个干扰资料、1个缺失资料案例，大小统一200MB。检索只用8类路径模式资料库的`facts`，不把标准`answer`送入评估提示；不是向量检索或原RAG论文的Wikipedia系统。[ref: lewis2020rag] [RAG原论文](https://arxiv.org/abs/2005.11401)

质量分数来自同一助手可见模型和条件的逐条审阅，**非人类盲评**。严格资料忠实性要求重要断言得到资料支持，或未知用途明确拒猜且不补写；目标≥22/24。未验证但可能正确的CPU/CUDA等细节也会扣分，因此不等于总体事实准确率。未知拒猜目标7/7；危险清理主张目标0，只涵盖本定义的无依据无损失保证、缺必要条件清理或卸载错误组件。自然度按1–5分，目标均值≥4。关键词诊断目标≥21/24，仅检测字面required/forbidden，不理解否定范围，不能替代语义判断。资料矛盾/额外未支持是事后失败原因分解，未改主要目标或原评分。

## A：三模型 GGUF 无资料与 RAG 六组

六组driver均真实exit0、各24条，空答/截断/思考泄漏均0。每个模型配对只增减用途facts；模型revision、完整SHA、实际参数与原始回答均保存。

| 实验 | 模型 / 条件 | 关键词 | 严格忠实性 | 未知拒猜 | 资料矛盾 | 危险主张 | 自然度/5 | 请求中位秒 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| [exp_001](experiments/exp_001/result.json) | Qwen3.5-4B Q4_K_M / 无资料 | 10/24 | 2/24 | 3/7 | 7 | 6 | 3.166667 | 1.21955 |
| [exp_002](experiments/exp_002/result.json) | Qwen3.5-4B Q4_K_M / RAG | 18/24 | 14/24 | 5/7 | 7 | 0 | 3.708333 | 1.3480 |
| [exp_003](experiments/exp_003/result.json) | Qwen3.5-9B Q4_K_M / 无资料 | 12/24 | 5/24 | 2/7 | 5 | 5 | 3.125 | 1.7546 |
| [exp_004](experiments/exp_004/result.json) | Qwen3.5-9B Q4_K_M / RAG | 24/24 | 10/24 | 2/7 | 1 | 1 | 3.708333 | 1.5984 |
| [exp_005](experiments/exp_005/result.json) | Gemma4 E4B QAT Q4_0 / 无资料 | 6/24 | 6/24 | 1/7 | 5 | 6 | 3.5 | 1.05215 |
| [exp_006](experiments/exp_006/result.json) | Gemma4 E4B QAT Q4_0 / RAG | 17/24 | 17/24 | 3/7 | 0 | 0 | 3.833333 | 0.8645 |

三个RAG组忠实性14/10/17，未知拒猜5/2/3，矛盾7/1/0，各有取舍，没有一组完整达标。9B RAG关键词24/24仍补写未知来源/内容和OneNote永久丢失；4B RAG未知拒猜较多，却仍混淆WebView2与Edge；Gemma RAG没有本定义的矛盾或危险主张，但仍有7条未支持细节、未知拒猜仅3/7。**Gemma的两个0不保证通用可靠或安全。** 更大参数不能在本轮自动解释为更可靠；架构、量化方式、模板、tokenizer及权重驻留同时不同，历史0.8B也不是同运行时对照。详细144条证据见[量化分析](analysis-quantized.md)与[历史阶段报告](report-quantized.md)。

## B：失败冒烟、追加诊断与真实训练

GGUF Q4_K_M/Q4_0用于推理，本轮没有直接训练它们。训练另取固定HF基座`unsloth/Qwen3.5-4B`，revision `3764fa359b9082ea5a1e4a5e3ac3aaf6e9671636`，加载为bitsandbytes NF4+double quant、BF16计算，再训练低秩注意力适配器。[ref: dettmers2023qlora] [QLoRA原论文](https://arxiv.org/abs/2305.14314)；[ref: hf2026bnb] [官方量化文档](https://huggingface.co/docs/transformers/quantization/bitsandbytes)。Unsloth官方提示Qwen3.5 QLoRA量化差异，并列4B BF16 LoRA约10GB、9B约22GB；这台8GB机器上的NF4尝试属于探索性兼容实验。[ref: unsloth2026qwen35training] [官方指南](https://unsloth.ai/docs/models/qwen3.5/fine-tune)

| 实验 | 真实状态 / 退出码 | 优化步骤 | 发生了什么 |
|---|---|---:|---|
| [007](experiments/exp_007/result.json) | failed / 1 | 0 | SFTConfig不接受save_safetensors参数；不是已记录的OOM |
| [011](experiments/exp_011/result.json) | failed / 1 | 2 | 基座不变且LoRA更新的联合断言失败；原记录没有分开计数，不能确定哪项失败 |
| [012](experiments/exp_012/result.json) | success / 0 | 2 | 8条训练样本追加分阶段诊断，确认捕捉的训练区间基座冻结、LoRA更新；不等于解释质量通过 |
| [013](experiments/exp_013/result.json) | success / 0 | 38 | fresh base/adapter重开，150训练/18验证完成1epoch，生成选定adapter |
| [008](experiments/exp_008/result.json)、[009](experiments/exp_009/result.json)、[010](experiments/exp_010/result.json) | blocked / null | 0 | 原依赖阻塞记录保留；没有把后续成功覆写为这些实验已执行 |

012在准备期观察到203个基座参数FP32→BF16、统一FP32数值hash不变；真正训练基线设在首次验证/切回训练后，随后723基座参数及346量化状态严格比较均无变化，64个LoRA参数张量改变。这个诊断只解释该次观察，**不能倒填011联合断言的具体失败项**，也不覆盖所有非参数buffer或隐式状态。[失败与诊断审计](failure-analysis.md)

013配置为rank8/alpha8、q/k/v/o、batch1×accum4、LR5e-5、cosine/warmup3、answer-only loss，序列上限768；实际最长429token，无截断。150训练/18验证，验证仅按pip-cache目标group留出。正式训练独立再次确认：训练区间723基座参数及346量化状态变化0，64个LoRA参数张量发生变化，共包含1,572,864个可训练标量参数（未逐标量声称全部数值改变），38步loss/梯度有限。训练日志runtime550.664秒，总耗时664.436秒（含准备/验证/状态核验等）。

013原始run.log还记录库警告：Qwen3_5ForConditionalGeneration不接受`num_items_in_batch`，梯度累积会略不精确。本轮保留该实际警告，未量化其对loss或训练效果的影响，也未据此推断偏差数值或补跑训练。

18条验证NLL为step0 2.2960197926、step19 2.0307478905、step38 1.9347032309；仅按预定19/38两个checkpoint验证NLL选择checkpoint-38，未用24测试案例选模。下降说明这份重复模板的验证目标拟合改善，**不等于用途解释正确**。选定adapter safetensors为3155176 bytes，SHA `e027eb9d6a68d87f966a1be2ab54465d468bb082075553b164932ce6d0322d7e`；[adapter-manifest](experiments/exp_013/adapter-manifest.json)与选中checkpoint逐文件匹配。

加载和训练必须分开看：013加载CUDA allocated峰8163.0659MiB、reserved峰8230MiB，超过7168MiB余量目标；训练allocated峰3814.5439MiB、reserved峰4698MiB。后段较低不能替代加载瞬态。012同样加载超目标；未OOM只证明本机此配置完成，不能证明所有8GB机器都有余量，或推断具体分页、共享内存、物理驻留原因。

## C：同 NF4 基座的无/有 adapter RAG 配对

014与015使用相同本地基座、tokenizer/模板、NF4量化、CUDA/Unsloth运行时、24条messages及输入token数，seed42、greedy256新token、thinking关闭、use_cache=true。两组实际EOS均对齐tokenizer的248046，保留原248044记录；与A组GGUF/Vulkan不同，不能跨运行时把差异全归因微调。

预热后的实际快照核对723个非LoRA参数：归一名称、shape、dtype、device、requires_grad、raw/value hashes和346份quant_state均一致，全部基座参数冻结。此证据覆盖捕捉的参数/量化状态，不证明所有非参数状态或整段推理结束后状态相同。[配对基座核验](experiments/exp_015/paired_base_comparison.json)。adapter在磁盘存储BF16，但PEFT加载后实际运行adapter参数为FP32；346个Linear4bit仍NF4双重量化、BF16 compute，不能称所有基座与adapter都BF16。

| 指标 | [014：无adapter](experiments/exp_014/result.json) | [015：checkpoint-38 adapter](experiments/exp_015/result.json) | 事先目标 |
|---|---:|---:|---|
| 完整回答；空答/截断/思考泄漏 | 24；0/0/0 | 24；0/0/0 | 两组执行完整 |
| 关键词诊断 | 23/24 | 19/24 | ≥21；015未达，不是准确率 |
| 严格资料忠实性 | 13/24 | 17/24 | ≥22；均未达 |
| 未知拒猜 | 6/7 | 6/7 | 7/7；均未达 |
| 资料矛盾 / 额外未支持 | 6 / 5 | 4 / 3 | 事后分解，未设新目标 |
| 危险清理主张 | 0 | 0 | 本操作定义下达到0 |
| 风险充分 / 不完整 / 误导 | 14 / 3 / 7 | 15 / 5 / 4 | 保留逐条原因 |
| 自然度均值 | 3.666667 | 3.833333 | ≥4；均未达 |
| 请求中位秒 | 7.618816 | 7.370046 | ≤10；均达到 |

严格忠实性改善4条、退步0条：webview-exe补回独立依赖，onenote-file把绝对无法恢复改为无法保证，torch-env去掉无依据的无法恢复，unknown-microsoft去掉非官方目录标签。未知拒猜没有提高，因为unknown-microsoft原本已拒猜用途，而cache-backup仍被赋予pip缓存备份功能。

仍失败7条：pip-wheel安装/运行重下载混淆，两条WebView（dll和干扰案例）仍称Edge浏览器运行库，onenote-folder仍绝对否定云端恢复；torch-base、user-temp及cache-backup补写资料未支持的具体功能。前4条为关系/模态矛盾，后3条为未支持细节；CUDA常识未支持不等于已证实错误。Node两条遗漏重新安装路径，OneNote-file没出现“丢失”字样，解释了部分cue下降；关键词与语义得失不能合并成准确率。

自然度总分88→92、输出token总数1506→1236，说明部分句子更简洁或少了别扭条件，但多个未知答案仍共享“无法确定—来源确认—备份”模板。它是单助手评分，不等于人类觉得更自然。训练NLL下降、没有危险主张和执行success不能覆盖这些剩余质量问题。

## 数据、官方资料与泛化边界

[数据审计](data-audit.json)确认斜杠/大小写归一后，测试与训练、验证的精确路径重叠均0；但168行只有124唯一路径/9种目标答案，150训练只有110唯一路径/8种答案（7已知模板+1未知模板）。全部8类facts出现在训练输入。pip正向目标group/答案未训练，但pip事实仍在4条OneNote干扰输入出现，另有4条pip/cache-backup近似路径训练。因此只能称**目标group留出**，不能称pip知识完全留出或独立新知识泛化；没用测试选checkpoint也不消除共享资料与模板的边界。

[来源审计](knowledge-source-audit.md)保留冻结知识库，区分官方一般用途与真实文件核实。Microsoft支持[WebView2 Runtime的分发/依赖关系](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)，符合条件时也可能与Edge硬链接，逻辑独立不等于每个文件物理独立；[OneNote同步帮助](https://support.microsoft.com/en-us/onenote/onenote-help-and-learning/fix-issues-when-you-can-t-sync-onenote)支持未同步笔记备份与数据损失风险，没有证明每条合成cache文件内容；[pip缓存文档](https://pip.pypa.io/en/stable/topics/caching/)支持再次安装缓存复用，不能推为已安装程序每次运行需重下载。

PyTorch stable入口本次只重定向，旧Temp短URL读取为内部错误而非已证实404，审计找到了官方当前路径；来源可读性不能当作某个文件用途证明。官方文档、备份/依赖确认建议都没有验证用户物理文件、删除或恢复。本轮不扫描用户文件或执行清理；知识库若更新须新版本与重跑，而不修改冻结输入沿用旧分数。

## 资源控制与本机布局复现

项目为`D:/small-model-experiments`，权重、模型下载/实验缓存、日志和结果在D盘；GPU计算串行。A组使用llama.cpp Windows Vulkan b11539，显式Vulkan1、上下文2048、batch512/ubatch128、并发1，各模型内置模板。9B日志33/33层装入GPU，却还有CPU_Mapped 545.62MiB；Gemma43/43层，也有CPU_Mapped 2730.00MiB。层数offload不等于全部权重在显存，4B原低日志级别没有完整层数证据。

B/C运行Torch2.10.0+cu128、Unsloth2026.3.10、Transformers5.3.0、TRL0.24.0、PEFT0.18.1、bitsandbytes0.49.2。014/015加载allocated峰8129.2007/8128.2007MiB，仍超过7168MiB；后段allocated3316.1396/3319.5972MiB不能替代加载峰。014设备总占用采样观察到7878MiB，超过7680MiB诊断目标；CUDA allocated/reserved与稀疏nvidia-smi总占用口径不同，不混算、不推断驱动驻留原因。

014/015总耗时263.0968/231.7534秒、预热27.0757/9.3088秒，执行先后顺序、编译缓存与回答长度不同；A组也有首次编译/暖机效应。每配置只运行一次，不能宣称RAG、adapter或某架构普遍加速，更不能外推长上下文、并发、9B微调或全参数训练。

执行器固定依赖`inputs`三份冻结文件、`models`权重、`outputs/exp_20261010_111944`脚本布局，以及只读`D:/C_manager/lora-training/scripts`，源提交`c1a1b7a1fc0f117ffc2a5bcc0f2c10e23a58ebca`。根目录`enter-experiment.ps1`设置D盘缓存；模型下载清单固定revision/大小/SHA。恢复此布局及兼容Python/runtime后，执行入口例如：

```powershell
Set-Location -LiteralPath 'D:\small-model-experiments'
. .\enter-experiment.ps1
& 'C:/Users/ziang/miniforge3/envs/finetune/python.exe' '.\outputs\exp_20261010_111944\experiments\exp_015\script.py'
```

GitHub证据归档不是可在归档目录原地一键运行的独立包，且不包含基座/adapter权重；015需要另行取得或按固定配方重新训练adapter并匹配清单。执行器拒绝覆盖原result，再次运行须另建独立副本与对应布局/配置，保留本次证据。当前没有合并导出GGUF、上传权重、更换C_manager部署模型或完成GUI验收。

## 结论与下一轮需要的新证据

本轮支持的结论是：这台电脑可完成三种量化模型的短上下文推理，以及4B探索性NF4注意力LoRA训练；同NF4配对出现有限的资料忠实性与表达改善。**它没有解决全部解释错误、没有提高本轮未知拒猜计数，也没有达到完整可靠性或加载显存余量目标。**

下一轮可针对已记录的问题另立数据版本：保留资料的可能性/条件范围，增加有依据且不同表达的目标答案，以及cache-backup等近似路径拒猜；使用不共享目标家族及其干扰facts的独立来源样本和人类盲评，分别核验事实、完整建议与自然度。重复顺序随机化运行并单独审计加载峰，可检验资源稳定性。重复模板和目标措辞可能解释部分僵化/绝对化，但本轮没有证明唯一原因；这些方向尚未运行，不能作为新增结果。

证据入口：[完整分析](analysis.md)、[014逐条复核](reviews/exp_014.json)、[015逐条复核](reviews/exp_015.json)、[选中adapter清单](experiments/exp_013/adapter-manifest.json)、[基座配对核验](experiments/exp_015/paired_base_comparison.json)、[数据审计](data-audit.json)、[官方来源审计](knowledge-source-audit.md)、[研究来源登记](sources.json)。主聊天最终[CPU核验记录](final-verify.json)为passed，复算48条ID/回答SHA/证据短句/评分算术、723基座与346量化状态和选中adapter；[核验脚本](verify_final.py)未运行GPU。它证明记录与算术一致，不能自动证明语义判断正确或所有运行状态相同。
