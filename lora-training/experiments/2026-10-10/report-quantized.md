# 三种量化小模型的文件解释实验：六组阶段报告

> 历史阶段记录：本文保留当时的结果与结论，文中的“微调尚未运行”只描述该阶段。后续已完成训练及同NF4配对，请以[最终报告](report.md)为当前完整状态。

2026-10-10（Asia/Shanghai）；run `exp_20261010_111944`。Qwen3.5-4B、Qwen3.5-9B和Gemma4 E4B各完成无资料/RAG两组，合计144条回答；六组执行退出码均为0，但没有一组达到完整可靠性目标。**本报告只覆盖量化推理，微调及适配器效果尚未运行。**

## 研究问题与固定输入

研究问题是：增加模型容量或补充用途资料，能否改善中文文件解释、未知用途拒猜和删除风险表述？六组沿用同一冻结24案例：16个已知用途路径变体、6个未知/近似路径、1个干扰资料案例、1个缺失资料案例；文件大小统一为200MB。这些是合成路径，没有读取用户磁盘文件内容或确认实际创建软件。

每个模型的配对只改变是否输入用途资料：同样的中文系统指令、完整路径和初步规则标签，RAG添加8类资料库中的`facts`，不添加标准`answer`。干扰案例同时给相关与不相关资料；缺失案例明确没有匹配信息。这里的检索是路径模式匹配，没有向量数据库或动态联网答案，不能称为复现原RAG论文的Wikipedia检索系统。[ref: lewis2020rag] [原论文](https://arxiv.org/abs/2005.11401)

使用[Qwen4B Q4_K_M](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF)、[Qwen9B Q4_K_M](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF)和[Gemma E4B官方QAT Q4_0](https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf)。文件分别为2740937888、5680522464、5154941280 bytes；实际revision和完整SHA保存在各组`executed_config.json`。Gemma的E4B是有效参数命名，并不代表与普通4B相同的总权重、嵌入结构或内存需求。[ref: gemma4_e4b_qat]

## 指标定义与六组结果

所有质量复核由**同一个助手在看得到模型和条件的情况下**完成，非人类盲评、专家评测或用户满意度调查。定义如下：

- **关键词诊断**：检查required/forbidden文本，目标至少21/24；不能理解否定范围，不能替代语义判断。
- **严格资料忠实性/校准**：用途、影响及恢复的主要断言得到资料支持，或未知用途明确拒猜且不补写未经验证的用途；目标至少22/24。合理但资料没有提供的具体细节也会失败，因此不是总体事实准确率。
- **未知拒猜**：6个未知/近似路径与1个缺失资料案例都不赋予未经核实的用途，目标7/7；一句“无法确定”后继续猜内容仍失败。
- **危险清理主张**：包括没有依据的无损失/无影响保证、缺少必要使用或同步条件的清理建议、卸载错误组件；目标0。保守夸大损失可以是误导，但未必属于这个危险定义。
- **自然度**：1分不通顺，3分可懂但泛化或样板化，5分自然、简洁且忠实；目标均值至少4/5。主张错误与自然度分别评分。

| 实验 | 模型 / 条件 | 关键词诊断 | 严格资料忠实性/校准 | 未知拒猜 | 危险主张 | 自然度/5 |
|---|---|---:|---:|---:|---:|---:|
| [exp_001](experiments/exp_001/result.json) | Qwen3.5-4B Q4_K_M / 无资料 | 10/24 | 2/24 | 3/7 | 6 | 3.166667 |
| [exp_002](experiments/exp_002/result.json) | Qwen3.5-4B Q4_K_M / RAG | 18/24 | 14/24 | 5/7 | 0 | 3.708333 |
| [exp_003](experiments/exp_003/result.json) | Qwen3.5-9B Q4_K_M / 无资料 | 12/24 | 5/24 | 2/7 | 5 | 3.125 |
| [exp_004](experiments/exp_004/result.json) | Qwen3.5-9B Q4_K_M / RAG | 24/24 | 10/24 | 2/7 | 1 | 3.708333 |
| [exp_005](experiments/exp_005/result.json) | Gemma4 E4B QAT Q4_0 / 无资料 | 6/24 | 6/24 | 1/7 | 6 | 3.5 |
| [exp_006](experiments/exp_006/result.json) | Gemma4 E4B QAT Q4_0 / RAG | 17/24 | 17/24 | 3/7 | 0 | 3.833333 |

三个模型加入资料后的严格忠实性分别从2→14、5→10、6→17，均有所改善；RAG未知拒猜分别5/7、2/7、3/7，仍不足。只有9B RAG达到关键词目标24/24，但其严格忠实性只有10/24，自然度及未知校准也未达目标，因此不能说它“解释全部正确”。所有组完整回答24条，空回答、截断、思考内容泄漏均为0，说明该短上下文配置能够执行，不能据此证明答案可靠。

## 典型错误与模型之间的取舍

4B RAG在三个RAG组中未知拒猜计数最高，但仍将WebView2说成Edge浏览器内置或版本绑定，将OneNote的可能丢失/恢复无保证变为必然永久丢失、无法云端恢复；pip-wheel还把重新下载安装与已安装程序运行混淆。它减少了额外补写，却没有减少本组明确资料矛盾。

9B RAG正确表达了WebView2独立性与桌面应用依赖，OneNote-folder也保留了条件性风险；OneNote-file仍写成必然永久丢失。UnlistedProduct、onnx、cache-backup和缺资料OneNote继续按命名补写内容或来源，Hugging Face案例还给出无依据的“不丢失个人数据”保证。因此关键词满分掩盖了语义和来源忠实性的限制。

Gemma RAG正确表达WebView2的桌面应用依赖及OneNote未同步修改可能丢失，没有本定义中的明确资料矛盾或危险主张；但它仍把archive.bin赋予归档类型、cache-backup当pip缓存备份、onnx猜作推理模型、缺资料文件猜作临时文件。Node依赖、缓存离线影响及处理工具等建议也有遗漏。**0矛盾、0危险主张只适用于这组案例和定义，不是通用可靠或安全保证。**

以下为事后解释性分解，原评分和阈值没有改变：“资料矛盾”只收与给定事实、条件或操作顺序直接冲突的断言；“额外未支持”缺少资料验证但不能据此认定现实中为假，例如CPU/CUDA功能常识。

| 模型 | 无资料：矛盾 / 额外未支持 | RAG：矛盾 / 额外未支持 |
|---|---:|---:|
| Qwen3.5-4B | 7 / 15 | 7 / 3 |
| Qwen3.5-9B | 5 / 14 | 1 / 13 |
| Gemma4 E4B | 5 / 13 | 0 / 7 |

这组数据没有单一全面胜者：4B RAG未知拒猜较多，Gemma RAG严格资料忠实性和矛盾计数较好，9B RAG关键词表现最好但补写较多。回答普遍可读，三个RAG自然度仍低于目标，多个回答继续重复“这个文件是/建议先备份”或使用不贴合具体风险的备份建议。选择模型不能只看关键词或参数量。

## 本机资源控制与计时

运行环境为RTX5070 Laptop 8GB、32GB内存、llama.cpp Windows Vulkan b11539，显式选择NVIDIA `Vulkan1`。上下文2048、batch512/ubatch128、并发1、线程8、seed42、temperature0、最多256新token、thinking关闭；各模型用自己的GGUF内置Jinja模板，不互套模板。不加载视觉投影，不联网生成答案，GPU计算串行；每实验上限1740秒。所有模型、实验缓存与结果位于`D:/small-model-experiments`，旧项目只读。

请求中位延迟包括请求、prefill和decode，排除模型加载与短暖机；下表中位数从保存计时用十进制复算，移除浮点计算尾差，原始结果未修改。

| 实验 | 请求中位秒 | 加载秒 | 暖机秒 | 总耗时秒 | 峰值全设备显存MiB |
|---|---:|---:|---:|---:|---:|
| exp_001 | 1.21955 | 7.7337 | 4.502 | 59.9546 | 2798 |
| exp_002 | 1.3480 | 3.5885 | 0.0922 | 51.0442 | 2802 |
| exp_003 | 1.7546 | 8.181 | 0.4569 | 61.7791 | 5065 |
| exp_004 | 1.5984 | 5.6535 | 0.1531 | 54.0123 | 5069 |
| exp_005 | 1.05215 | 12.9365 | 2.5885 | 60.5425 | 2872 |
| exp_006 | 0.8645 | 5.1446 | 0.1406 | 47.6946 | 2876 |

9B日志记录33/33层装入GPU，同时有CPU_Mapped模型缓冲545.62MiB和Vulkan模型缓冲4861.28MiB；Gemma记录43/43层，同时有CPU_Mapped 2730.00MiB和Vulkan 2696.04MiB。**层数装入GPU不等于全部权重驻留显存或全部计算只有GPU**。4B原日志级别较低，没有同样完整的层数/缓冲证据，也不能据命令请求99层宣称全部权重在GPU。

显存为1Hz采样的全设备总占用，含桌面和后台负载，可能遗漏瞬时峰值；RAM未连续采样。实际运行顺序固定，没有重复随机顺序基准；首次编译/暖机、各模型tokenizer及回答长度不同，会影响速度，因此不能从总时间或中位数泛化某模型/架构普遍更快。短上下文能运行也不代表长上下文、并发或微调显存足够。服务退出码1来自驱动程序的受控停服，六组实验驱动退出码均为0，后四组另存`terminated_by_driver=true`。

## 复现目录与执行入口

当前执行器依赖本机布局：`D:/small-model-experiments/inputs`存放三份冻结输入，`models`存放权重，`outputs/exp_20261010_111944`存放公共实现和各实验目录；`D:/C_manager/lora-training/scripts`作为只读函数来源，固定代码提交`c1a1b7a1fc0f117ffc2a5bcc0f2c10e23a58ebca`。输入、模型revision、文件大小和SHA必须与实际配置/下载清单一致，不能重新生成数据替换本轮金标准。

根目录`enter-experiment.ps1`将实验缓存和临时目录指向D盘；`download_models.py`用于取得并校验固定版本的三份量化权重。还需把固定[Vulkan b11539运行时](https://github.com/ggml-org/llama.cpp/releases/tag/b11539)放在`cache/tools/llama-b11539`并核对runtime SHA。执行入口示例为：

```powershell
Set-Location -LiteralPath 'D:\small-model-experiments'
. .\enter-experiment.ps1
& 'C:/Users/ziang/miniforge3/envs/finetune/python.exe' '.\outputs\exp_20261010_111944\experiments\exp_001\script.py'
```

**GitHub归档不是直接在归档文件夹中一键运行的独立包**；复现需要恢复上述源码、数据、权重和工具布局，以及兼容Python环境。执行器拒绝覆盖已有`result.json`，再次实验须使用独立运行副本和对应配置布局，保留本轮原始证据；以上命令只展示入口，不会覆盖已经完成的本轮实验。

## 结论与尚未执行的NF4微调

在本小样本中，补充用途资料改善了三个模型的资料忠实性，但没有完整可靠性达标。各模型的架构、训练来源、tokenizer及量化方式不同，不能把跨模型结果唯一归因参数量；历史0.8B的训练和运行时也不同，不能用于证明参数增大或本轮微调收益。当前尚未做独立人类复核、真实文件来源确认、统计显著性检验、C_manager部署替换或GUI验收。

后续按预注册计划先验证4B训练可行性：另取锁定HF safetensors基座，在加载时转NF4+double quant、bf16计算，冻结基座训练LoRA；这不是直接训练GGUF。[ref: dettmers2023qlora] [QLoRA原论文](https://arxiv.org/abs/2305.14314)；[ref: hf2026bnb] [官方量化文档](https://huggingface.co/docs/transformers/quantization/bitsandbytes)。

训练输入沿用168条RAG记录，整家族留出pip-cache 18条、训练150条，answer-only loss，不用24测试案例选checkpoint；先2步冒烟，再条件性运行最多38步/1epoch，rank8 q/k/v/o、序列768、batch1×accum4。随后用同NF4运行时的无/有adapter配对隔离训练作用，不能将GGUF与NF4差异当微调收益。Unsloth指南列4B BF16 LoRA约10GB、9B约22GB并提示Qwen3.5 QLoRA量化差异，因此8GB设备上的训练仍是可能OOM或兼容失败的探索，不能提前宣称成功。[ref: unsloth2026qwen35training] [官方指南](https://unsloth.ai/docs/models/qwen3.5/fine-tune)

可追溯材料：[冻结计划](plan.md)、[来源登记](sources.json)、[综合分析](analysis-quantized.md)、[4B阶段报告](report-4b.md)。逐条审阅为[001](reviews/exp_001.json)、[002](reviews/exp_002.json)、[003](reviews/exp_003.json)、[004](reviews/exp_004.json)、[005](reviews/exp_005.json)、[006](reviews/exp_006.json)；对应实验目录保留result、records、executed_config和server/execution日志。复核只有单助手、24合成路径与8类资料，结论不能扩展为覆盖整台电脑的文件用途或删除安全性。
