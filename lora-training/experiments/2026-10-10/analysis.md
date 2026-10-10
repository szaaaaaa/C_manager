# 小模型RAG与量化微调：分析

已核对六组量化推理、两次真实失败冒烟、追加成功诊断exp_012、正式38步NF4+LoRA训练exp_013，以及同NF4基座RAG的无adapter/有adapter成对评测exp_014/015。两个推理组均success/exit0、各24条完整回答；实际基座快照、输入和生成设置匹配。**本轮adapter使严格资料忠实性从13/24到17/24、自然度从3.667到3.833，但未知拒猜仍6/7，完整可靠性及加载显存余量目标未达成。** 这些是固定合成案例上的单助手可见配置审阅，不能外推事实准确率、人类满意度、统计显著性或独立新知识泛化。

## Findings：目前可以成立的判断

1. 本轮三种量化模型都能在RTX5070 Laptop的短上下文配置完成24条解释。每对补充检索资料提高严格资料忠实性，但六组中没有一组达到完整可靠性目标。这个计数包含明确资料矛盾与未验证细节，属于单助手可见配置复核，不是人类盲评或事实准确率。不同模型在忠实性、未知校准、关系矛盾之间有取舍。依据：[量化阶段分析](analysis-quantized.md)、reviews/exp_001至006及原始result/records。

| 量化RAG配置 | cue/24 | 严格资料忠实性/24 | 未知校准/7 | 明确资料矛盾 | 危险清理主张 | 自然度/5 |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3.5-4B Q4_K_M | 18 | 14 | 5 | 7 | 0 | 3.708 |
| Qwen3.5-9B Q4_K_M | 24 | 10 | 2 | 1 | 1 | 3.708 |
| Gemma4 E4B QAT Q4_0 | 17 | 17 | 3 | 0 | 0 | 3.833 |

9B RAG cue24/24仍有OneNote永久丢失绝对化与未知用途补写；Gemma RAG的明确资料矛盾/危险清理主张均0，不代表总体安全或达到了未知校准7/7。量化、tokenizer/chat模板、架构、GPU/CPU权重驻留等因素同时不同，跨模型结果不能仅归因参数量。详细144条证据、资源口径与事后错误分解见量化阶段分析。

2. exp_013正式NF4+LoRA训练已实际成功38步、总664.436秒，训练日志runtime550.664秒。150训练/18验证、rank8 q/k/v/o、batch1×accumulation4、最长429token不截断、answer-only mask、AdamW8bit、LR5e-5/cosine/warmup3均保留实际配置与运行记录。346个实际NF4双重量化+BF16 Linear4bit模块经脚本校验，而不是仅凭控制台文字认定量化身份。依据：[013结果](experiments/exp_013/result.json)、executed_config.json与executed_training.py。

3. 正式训练的冻结/更新检查有独立阶段证据：四份基座状态均723个参数张量且requires_grad全false；准备前→Trainer构造后0变化，首次验证/切回训练后203个FP32→BF16且统一FP32值hash相同。真正训练基线为after_step0_before_training，与after_training_before_final_eval逐项对比raw bytes/dtype/shape及346份quant_state全部无变化，训练基座变化0。64个LoRA参数张量变化，38步post_clip梯度全部有限且非零（范围0.791584至1.004653）；38条记录loss/grad_norm有限。64个张量共1,572,864标量参数，保存adapter safetensors的header独立核验64个LoRA BF16张量与该总量相符。依据：exp_013四份base_*.json、result、实际脚本、adapter文件header；分析者CPU复算不启动GPU。

基座快照在最终验证之前，只证明捕捉的训练区间参数/量化状态冻结，不涵盖所有非参数buffer或隐式运行状态，也不声称最终验证之后所有状态完全相同。准备期203变化仍不能回填exp_011联合断言具体哪项失败。此前007接口失败、011联合验证失败维持failed/exit1。依据：[失败与诊断分析](failure-analysis.md)。

正式训练还有一项库警告：[exp_013 run.log](experiments/exp_013/run.log)第35–37行明确提示Qwen3_5ForConditionalGeneration不接受num_items_in_batch，使用gradient accumulation会略不精确。本轮未量化该警告对梯度、loss或结果的实际影响，也没有测出偏差数值；batch1×accumulation4只能描述实际配置，不能称等同精确的大batch或严格按token归一化的训练结果。该限制不改写真实退出码、保存结果或既有解释质量评分。

4. 验证NLL从step0的2.2960197926降至step19的2.0307478905，再到step38的1.9347032309；只在预定step19/38两个checkpoint间按18条pip-cache目标group验证NLL选出checkpoint-38。result、checkpoint-19/38 trainer_state和adapter-manifest的best step/metric一致，未用24测试案例选模。NLL下降0.3613165617仅说明这份重复模板的留出验证目标拟合改善，不能替代实际解释质量。依据：training_logs、两个trainer_state.json、[adapter清单](experiments/exp_013/adapter-manifest.json)。

5. adapter清单与实际文件SHA256已独立重算，并与checkpoint-38逐文件一致：

| 文件 | 实际bytes | 实际SHA256 |
|---|---:|---|
| adapter_model.safetensors | 3155176 | e027eb9d6a68d87f966a1be2ab54465d468bb082075553b164932ce6d0322d7e |
| adapter_config.json | 1234 | 5a69e57998c34cb8ca29b6606c84a62f4cc66bf17adb91b146feb6c8986894f6 |

基座训练目录16份清单文件也按磁盘实际内容重算，全部匹配training-files.json。其中safetensors分片1为5329398688bytes，SHA256=26a93f066e1916adb13453dae5a0c707c0fbc71299ed98779571a907b8e74c61；分片2为3990429408bytes，SHA256=cb544bd9bfae93dc59b0f22b292f5933573854a7f9b97835c67060d7d910e188。固定repo unsloth/Qwen3.5-4B、revision3764fa359b9082ea5a1e4a5e3ac3aaf6e9671636。这里只核验本地文件与清单对应，不宣称重新发布或导出了GGUF。

## 加载显存目标仍未达成

013加载allocated峰8163.0659MiB、reserved峰8230MiB；训练allocated峰3814.5439MiB、reserved峰4698MiB。包含加载的allocated峰比7168MiB目标超995.0659MiB（约13.88%）。没有OOM且训练期更低不等于加载余量达标。013的汇总reserved已保留加载峰8230，post_load_peak_reserved=4698另列；012中的泛字段5044只属统计重置后段，不能当全程峰。依据：各阶段result字段与实际reset调用，详见failure-analysis.md。

CUDA allocator allocated/reserved与nvidia-smi设备占用口径不同；未取得驱动驻留/共享内存细分，不能解释为确证所有字节物理驻留显卡、确证发生分页或证明所有8GB机器都能运行。本次短序列/小batch/Win环境技术成功不外推长上下文、并发、9B训练或全参数训练。

## 数据与知识来源边界

- [数据边界审计](data-audit.json)核对三份冻结输入SHA：eval a516f0f456d18ba589034e23f3a3e47cefb5762f7436387bf22d502d4372603b；train c3a2041e398c84a9c5f854130d298743ad31b38db2ee2852ce354672f14f3c46；knowledge547f1cb9e11aae21796c4d7fe897b90f52dd8fe5bceec6b726ffc28a4d25cf0d。归一斜杠/大小写后，24测试与150训练、18验证的精确路径重叠均0，训练/验证重叠也0；这仅证明路径字符串分离。
- 168合成行只有124条归一唯一路径、9种目标答案；150训练只有110条唯一路径和8种答案（7已知模板+1未知模板），18验证14唯一路径/2种答案。路径变体和上下文变体共享资料与输出模板，不能把样本行数当独立事实数量。
- pip-cache整目标group18行留出，训练没有pip正向答案模板，但pip事实仍在4条OneNote干扰输入出现（mixed2、irrelevant2）；另有4条unknown的pip/cache-backup近似路径在训练。全部8类冻结facts都出现在训练输入。应称目标group留出，不能称pip知识完全留出，也不能从不用测试选模推导独立新知识泛化。
- [冻结资料来源复核](knowledge-source-audit.md)指出文档支持一般用途/保守防护，但没有读取真实文件验证内容。WebView2 Runtime与Edge在依赖逻辑上分开，符合条件时也可能硬链接；逻辑独立不等于每个Runtime文件与浏览器文件在物理存储上都分开。OneNote同步页面支持未同步笔记备份/数据损失风险，没有逐文件证明合成cache内容。
- PyTorch stable入口本次仅重定向，Temp旧短URL本次内部读取错误且找到了官方新路径；不能把这些检索状态伪称某文件用途证明或HTTP404。源审计没有修改本轮冻结KB，严格资料忠实性不自动等同现实文件用途正确率。若更新知识库需新版本与重跑。

## 同NF4基座的RAG与LoRA成对结果：exp_014/015

exp_014为同基座+RAG，exp_015为同基座+checkpoint-38 attention LoRA+RAG。两组success/exit0，各完整24条，空答/截断/thinking leak均0；[基础组逐条review](reviews/exp_014.json)与[adapter组逐条review及配对审计](reviews/exp_015.json)保留全部原回答、SHA256、资料证据和逐条理由。评分定义及原阈值全部沿用001–006，error_kind只是事后解释性分解，不是新增主目标。

| 指标 | exp_014：无adapter | exp_015：有adapter | 事先目标及判定 |
|---|---:|---:|---|
| 完整回答 | 24/24 | 24/24 | 24；两组达到 |
| 空答 / 截断 / thinking leak | 0 / 0 / 0 | 0 / 0 / 0 | 均0；两组达到 |
| cue关键词诊断 | 23/24 | 19/24 | ≥21；014达到，015未达；不是准确率 |
| 严格资料忠实性 | 13/24 | 17/24 | ≥22；两组未达 |
| 未知拒猜 | 6/7 | 6/7 | 7/7；两组未达 |
| 明确资料矛盾（事后分解） | 6 | 4 | 不新增阈值；不能替代严格资料忠实性 |
| 未支持额外细节（事后分解） | 5 | 3 | 不新增阈值；不等同已证实事实错误 |
| 危险清理主张 | 0 | 0 | 0；本操作定义下达到，不是总体安全保证 |
| 风险充分 / 不完整 / 误导 | 14 / 3 / 7 | 15 / 5 / 4 | 保留逐条解释，不折算总体安全分 |
| 自然度总分 / 分母 | 88 / 24 | 92 / 24 | 同一单助手1–5评分 |
| 自然度均值 | 3.666667 | 3.833333 | ≥4；两组未达 |
| 请求中位耗时（秒） | 7.618816 | 7.370046 | ≤10；两组达到，未含加载/预热 |

严格资料忠实性改善4条、退步0条：webview-exe不再错绑Edge，onenote-file把绝对无法恢复改为无法保证恢复，torch-env去掉无法恢复的额外断言，unknown-microsoft去掉目录不官方的无根据来源判断。未知拒猜并未改善，因为unknown-microsoft原本已拒猜具体用途，而cache-prefix-nearmiss仍被赋予“pip 的缓存备份目录”功能。已知用途与未知拒猜不是同一指标。

尚失败7条：pip-wheel仍说“下次使用时会重新下载”，两条WebView（dll与干扰案例）仍是“Edge 浏览器的运行库”，onenote-folder仍说“无法从云端恢复”，另有torch-base补写CUDA加速、user-temp补写缓存或进度记录、cache-prefix-nearmiss补写pip缓存备份功能。前四条与冻结资料的关系/模态直接矛盾，后三条缺少支持；CUDA细节可能正确，但资料没有提供，不能把其记成已证实错误。OneNote保守夸大损失计为误导，不按危险删除计分。

cue下降与部分忠实性改善同时发生：onenote-file没有“丢失”关键词，但正确保留“无法保证从云端恢复”；WebView dll/干扰回答去掉WebView字样，却仍有关系错误。Node两条省略重新安装，忠实性仍成立但恢复路径不完整且cue失败。关键词只验证字面片段，不可替代逐条资料复核。

自然度增加4分来自去掉别扭的重装条件、无根据的无法恢复和非官方目录标签，以及更清楚的HF清理步骤；部分HF与Windows句子更通用，单条评分也下降。输出token总数1506→1236，中位62→51.5，说明本轮更短，不能推出人类认为更自然。多个未知回答仍重复“无法确定—创建软件确认—备份”的两句结构，解释个性化依然有限。自然度评分不随训练loss或研究期待调整。

### 真实runtime匹配证据

分析者用CPU再次对照两份base_runtime_after_warmup.json：归一参数键集合相同、各723个非LoRA参数，dtype、shape、requires_grad、device、raw SHA、统一FP32值SHA与quant_state SHA差异全部0，346份quant_state一致。两组实际基座dtype均346 uint8、203 FP32、174 BF16，requires_grad全false。PEFT wrapper的source_name不同，故整个JSON文件SHA不同，不代表参数不同。该检查覆盖预热后的命名参数与量化状态，不覆盖全部非参数buffer/隐式状态，也不证明整段推理结束后所有状态不变。训练期间冻结基线的证据与这项推理组间匹配是两个检查。 主聊天另以[CPU最终核验](final-verify.json)复算48条原记录/result/review的ID、回答全文SHA、证据短句、关键词及质量计数，状态passed且没有GPU执行；它还核验723基座/346量化状态与选中adapter清单。自动核验确认记录和算术一致，不能自动证明语义判断正确或所有非参数状态相同。

两组executed_config的model/revision/file manifest、engine、generation、inputs相同；原始24条messages/path/input_tokens逐项相同；Unsloth/Transformers及包版本相同。实际runner SHA=98c68de26a0aaba990b91d979bcad6050f9bbf78aecc503cb20cbb963368ae10。脚本同一tokenizer.apply_chat_template(enable_thinking=False)，同seed42、do_sample=False、max_new_tokens256、use_cache=True，实际EOS均tokenizer <|im_end|> 的248046，修正加载时248044。模型与tokenizer来自同一固定本地目录，tokenizer.json SHA=87a7830d63fcf43bf241c3c5242e96e62dd3fdc29224ca26fed8ea333db72de4，tokenizer_config SHA=04e9017bf53d513db997ce8a472ec0cef89339c7ab3af449e561af79fd45cb71，chat_template SHA=8452ca85cb1e0ff04304c02f417a53305d5ba17f6eb9d5693343ad8355f985a8。

exp_013 adapter在磁盘保存BF16，但exp_015 PeftModel.from_pretrained载入后实际adapter参数dtype为**FP32**，来自result.adapter_runtime_dtypes与实际脚本的named_parameters检查；base-only组为空列表。346 Linear4bit仍NF4双重量化/BF16 compute，不能把“BF16 compute”写成“全部基座/adapter都BF16”。本轮比较支持实际checkpoint-38 adapter加载流程在该固定配置的描述性改善，不是BF16 adapter与FP32 adapter比较，也不验证其他推理引擎/导出格式的收益。exp_002 GGUF Q4_K_M Vulkan与这里HF NF4 CUDA不同，其差异不能全部归因微调。

### 耗时和显存边界

exp_014/015总耗时263.0968/231.7534秒，预热27.0757/9.3088秒；serial先后运行，Triton缓存条目661→1039，冷编译历史与回答长度不同，不能把总耗时或请求中位差直接称为adapter加速。每组只跑一次，没有重复/随机化顺序的基准。

| CUDA阶段口径（MiB） | exp_014 | exp_015 |
|---|---:|---:|
| 加载allocated峰 | 8129.2007 | 8128.2007 |
| 加载reserved峰 | 8222 | 8192 |
| 后段allocated峰 | 3316.1396 | 3319.5972 |
| 后段reserved峰 | 4682 | 4834 |

两组加载allocated仍超过7168MiB探索训练余量目标，后段低值不能代替加载峰。稀疏nvidia-smi设备总占用样本（约5秒间隔）014观察到7878MiB、015观察到5020MiB；014样本也超过推理配置的7680MiB设备占用诊断目标，015较低样本并不能证明短暂加载峰或真实进程占用余量达标。设备总量、CUDA allocator allocated/reserved不可混为同一口径；没有驱动驻留/共享内存细分，不推断分页与物理驻留原因。没有OOM和本机技术成功并不保证所有8GB显卡都有同样表现。

### 24个案例的成对变化

下表忠实性“通过”只指严格资料忠实性；“矛盾/额外/支持”分别对应reference_contradiction/unsupported_extra/calibrated_or_supported。完整证据与原回答在两个review，原014评分保持不变。

| 案例 | 忠实性014→015 | 错误分解014→015 | 自然度014→015 | 变化与仍存在的边界 |
|---|---|---|---:|---|
| pip-body | 通过→通过 | 支持→支持 | 4→4 | 保持缓存与已安装包分开，purge建议；015下次需要措辞较笼统。 |
| pip-wheel | 失败→失败 | 矛盾→矛盾 | 3→3 | 仍说下次使用触发重下载，安装/运行混淆。 |
| webview-dll | 失败→失败 | 矛盾→矛盾 | 3→3 | 仍错绑Edge浏览器，保留及应用管理建议正确。 |
| webview-exe | 失败→通过 | 矛盾→支持 | 3→4 | 补回WebView2独立依赖；未明确保留/系统应用管理。 |
| onenote-folder | 失败→失败 | 矛盾→矛盾 | 4→4 | 仍将不能保证云恢复绝对化为无法恢复。 |
| onenote-file | 失败→通过 | 矛盾→支持 | 4→4 | 恢复模态校准，去掉永久丢失断言，cue因无丢失字样失败。 |
| torch-base | 失败→失败 | 额外→额外 | 4→4 | CUDA加速细节未在facts支持，不按已证实错误。 |
| torch-env | 失败→通过 | 额外→支持 | 3→4 | 去掉无法恢复；卸载前仍缺项目依赖检查。 |
| hf-weights | 通过→通过 | 支持→支持 | 4→5 | 补全下载条件及HF缓存工具，处理顺序更清楚。 |
| hf-blob | 通过→通过 | 支持→支持 | 5→4 | 仍不猜模型任务；015省略HF缓存工具。 |
| node-folder | 通过→通过 | 支持→支持 | 3→4 | 去掉不再需要项目才重装的别扭条件，却未说明重装/工具。 |
| node-file | 通过→通过 | 支持→支持 | 3→4 | 去掉别扭条件，包管理建议正确，重装恢复路径遗漏。 |
| user-temp | 失败→失败 | 额外→额外 | 3→3 | 仍猜缓存/进度记录；关闭应用/安装和系统工具保护保留。 |
| user-temp-uppercase | 通过→通过 | 支持→支持 | 4→4 | 一般临时目录来源与占用保护保留。 |
| windows-temp | 通过→通过 | 支持→支持 | 5→4 | 未知具体内容与跳过占用保留，015表述更通用。 |
| windows-temp-file | 通过→通过 | 支持→支持 | 4→4 | 仍有任务结束/占用条件与Windows存储工具。 |
| unknown-archive | 通过→通过 | 支持→支持 | 4→4 | 均拒猜archive.bin内容并先确认/备份。 |
| unknown-microsoft | 失败→通过 | 额外→支持 | 3→4 | 去掉目录非官方猜测；用途拒猜两组原本都成立。 |
| unknown-cache | 通过→通过 | 支持→支持 | 4→4 | 均拒猜具体内容；015补齐明确备份。 |
| unknown-download | 通过→通过 | 支持→支持 | 4→4 | 均拒猜zip用途/内容并先备份。 |
| cache-prefix-nearmiss | 失败→失败 | 额外→额外 | 3→3 | 两组仍擅自赋予pip缓存备份功能，未知拒猜均失败。 |
| unknown-onnx | 通过→通过 | 支持→支持 | 4→4 | 均不确定类型/任务；015更简短但未知模板明显。 |
| webview-with-distractor | 失败→失败 | 矛盾→矛盾 | 3→3 | 均未采用pip干扰，但仍错绑Edge运行库。 |
| onenote-missing-evidence | 通过→通过 | 支持→支持 | 4→4 | 均在缺资料时拒猜；可能个人数据只是备份条件提醒。 |

## Conflicts：相同资料下仍有矛盾

训练技术成功、验证NLL下降与解释目标不是同一证据。正式训练梯度/LoRA更新/基座冻结均核对通过，18条目标group验证NLL变低，但成对推理仍有4条明确资料矛盾、3条未支持细节，未知近似路径仍失败，且cue下降。不能用日志success、NLL或危险计数0覆盖质量结果。

量化组中RAG三对均提高严格资料忠实性，但9B的cue24/24对应忠实性仅10/24；参数更多不在本研究中自动意味着更可靠。Gemma RAG资料矛盾0却有7条额外细节/未知猜测，同样不足完整目标。架构、量化方法、模板及权重驻留与参数规模共变，不能解释为唯一参数量效应；历史0.8B使用不同量化/运行时，不能与本轮差异直接归因参数或训练。

冻结facts包含“可能丢失/不能保证恢复”，部分训练输出则有“直接删除会丢失这些内容”等较强句式；多行共享目标模板。重复模板/模态差异是剩余绝对化和僵化的一种可检验解释，不是本轮证明的唯一原因。没有用测试选checkpoint也不能消除共享知识、pip事实干扰曝光和合成路径变体的边界。

## Open questions：本轮目标与下一步证据

本轮可以说在这台机器上完成三种量化模型短上下文推理及4B NF4注意力LoRA38步训练，并在同NF4基座RAG配对中观察到部分忠实性和自然度改善。不能说已经修好全部用途解释、达成完整可靠性或加载显存余量，也不能说进行了一项知识完全留出/用户真实文件的泛化验证。007和011原失败状态保留，012是追加诊断，不能把后续成功改写前两次失败或推定011联合断言具体失败项。

尚需新的独立来源/内容样本、人类盲评及重复运行，才能评估真实文件用途、自然度与资源稳定性；任何知识库修订或更换训练模板都应版本化并另行评测。基于本轮失败，可继续检验资料中条件/可能性的保留、未知近似路径拒猜与更丰富的表达模板是否改善，而不把目前的单助手固定案例增益当作部署可靠性结论。所有判断分别引用原始日志、逐条review、数据审计与来源审计；没有追加GPU执行或修改原始输入/结果。
