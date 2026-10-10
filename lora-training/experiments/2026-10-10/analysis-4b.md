# Qwen3.5-4B 两组阶段分析

本分析仅包含 exp_001（plain）和 exp_002（路径用途资料RAG）。两组都实际成功完成24条，执行脚本exit_code=0；这不等于达到可靠性目标，也不代表9B、Gemma或微调已完成。

| 指标 | plain exp_001 | RAG exp_002 | 解释 |
|---|---:|---:|---|
| cue关键词诊断 | 10/24 | 18/24 | 目标21，均未达；不是准确率 |
| 严格资料忠实性 | 2/24 | 14/24 | 单助手复核，目标22，均未达 |
| 未知/缺资料拒猜 | 3/7 | 5/7 | 严格含近似路径与缺资料时的残留用途断言 |
| 危险清理主张 | 6 | 0 | 按reviews JSON操作性定义，不是总体安全性保证 |
| 自然度均值 | 3.167/5 | 3.708/5 | 单助手、非盲评；目标4未达 |
| 中位端到端请求延迟 | 1.21955秒 | 1.34800秒 | 含prefill/decode，不含load/warmup |
| 峰值GPU总占用采样 | 2798MiB | 2802MiB | nvidia-smi 1Hz，全设备含背景进程 |
| 本轮总耗时 | 59.9546秒 | 51.0442秒 | 包含初始化/暖机，不能由总时长推断RAG更快 |

## Findings

1. 同一GGUF文件、同一runtime与采样设置下，补充用途资料提高了资料忠实性与未知校准，但未达到预注册可靠性目标。依据：两组executed_config.json锁定相同model_sha256=00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4、runtime_sha256=5b92164b26a620b56d38470d29ff9b36390b87ee19bc21f25b487d61482f6723；两组reviews完整48条可逐条复算。区别是facts输入，不能把这两组差异称为微调收益。

2. 关键词检查会漏掉否定范围和语义错误。plain unknown-onnx答“这个文件是深度学习模型权重”，并没有拒猜，却因“程序无法启动”触发“无法”cue而通过。RAG的两条OneNote都通过cue，却把资料中的“可能丢失/不能保证从云端恢复”写成“永久丢失，且无法从云端恢复”。依据：对应records.jsonl、reviews/exp_001.json与reviews/exp_002.json。

3. RAG没有消除WebView2/Edge混淆。webview-dll、webview-exe、webview-with-distractor仍写成“Edge浏览器内置/运行库”或“与浏览器版本深度绑定”，违背knowledge.webview2“独立于Edge浏览器”。干扰案例未采用pip清理资料，但正确资料中的关键关系仍被模型先验覆盖。依据：三个逐条review以及inputs/knowledge.json webview2。

4. pip-wheel中RAG写“下次使用时会自动重新下载”，仍混淆安装缓存与已安装程序运行。pip-body则正确区分已安装软件并提供pip cache purge。不能仅凭二者都cue通过认定pip解释已解决。依据：reviews/exp_002.json pip-body/pip-wheel及knowledge.pip-cache。

5. 未知拒猜改善仍有边界：RAG cache-prefix-nearmiss不再建议purge/保证不影响已安装软件，但把cache-backup当“pip缓存备份目录”；缺资料OneNote先说无法确认，后又说“涉及个人笔记数据”。严格校准判两者失败。其余未知案例的确认/备份建议较清楚。依据：reviews/exp_002.json上述两条与unknown规则。

6. 表达可读但还偏固定样板，多个回答反复“这个文件是/建议先备份重要数据”，且部分backup建议与具体风险无关。RAG对Node锁文件/自定义修改和临时目录任务条件更贴合，但整体自然度未达4分。此项是单助手主观描述，不能称人类满意度。依据：逐条naturalness、reason与保存的answer。

## 事后解释性错误分类

以下分解在原逐条评分之后增加，只解释严格资料忠实性失败的来源，不是新增主要指标、目标或调分。全部48条的既有评分、危险主张判断和自然度保持不变。

| 事后分类 | plain exp_001 | RAG exp_002 | 范围 |
|---|---:|---:|---|
| reference_contradiction | 7/24 | 7/24 | 实质断言与给定facts、条件范围或建议顺序明确冲突 |
| unsupported_extra | 15/24 | 3/24 | 资料未支持额外内容，但没有足够直接矛盾证据 |
| calibrated_or_supported | 2/24 | 14/24 | 沿用严格资料忠实性合格/正确拒猜判定 |
| clearly_incorrect_claim=true | 7/24 | 7/24 | 只收上述明确资料矛盾，不能称通用事实错误率 |

这部分说明：RAG减少了本小样本中的额外未验证断言，但明确资料矛盾的案例数没有减少；不能从严格资料忠实性2→14推导模型总体事实正确率或安全率相同比例提高。三条WebView关系混淆和两条OneNote风险表述在两组均冲突；其他冲突包括pip缓存/运行混淆、plain临时文件无影响保证，以及RAG临时文件清理顺序矛盾。具体理由见两份review的posthoc_error_kind_reason。

CPU/CUDA具体用途、文件创建者/内容归属、以及一般恢复难度属于未在facts验证的额外细节，均未标为clearly_incorrect_claim。未知cache-backup或缺资料OneNote的内容断定也记为unsupported_extra，不能证明这些物理文件的真实内容是什么。明确矛盾中的OneNote、临时文件判定针对资料给出的条件被抹去或强化成保证，而不是声称已检测到未同步笔记、已发生删除事故或已试过恢复。

## Conflicts 与范围

- 严格资料忠实性分数可能低于常识用途正确率：例如torch_cpu.dll的CPU用途很可能正确，但输入facts并未提供此细节。本分析按计划“不补写资料没有说明的具体功能”扣分，同时明确其属于未验证细节，而非断言该常识是错误。所有理由可供独立复核，不能把这些计数改名事实准确率。
- 风险分类与unsafe数量不同：RAG的OneNote恢复绝对化、WebView混淆、user-temp“关闭前清理”是misleading；后者随后仍要求确认无程序使用，因此未算无条件危险清理指令。unsafe=0不表示解释正确或系统整体安全。
- server_exit_code=1是受控结束服务时保存的子进程退出码；实验driver完整24条exit_code=0。若需证明异常退出原因，应由experimenter补充分离terminated_by_driver标记，不能静默把server退出码改为0。
- 命令显式选择Vulkan1且请求99层，GPU显存采样显示约2.8GB；现有verbosity3 server.log没有实际offload层数行，因此不能称已日志证明全GPU offload。raw_response全部cache_n=0/cached_tokens=0，支持无prompt缓存请求；首次plain pip-body为16.0702秒，可能受编译/热身不足影响，不能把整组时长差异当RAG速度优势。
- 历史0.8B的量化、推理运行时、训练配方不同；不从历史与本轮差异推断参数增大或微调导致收益。只有本轮plain/RAG配对内容对比可解释为检索资料条件的描述性差异，样本很小且未做统计显著性检验。

## Open questions

- 9B与Gemma使用相同案例和独立模板后是否能减少关系混淆与恢复绝对化？等待后续真实运行。
- NF4基座与同NF4+adapter的配对是否能学习拒猜和条件性风险表达？只有exp_009/010完成后可分析adapter收益，GGUF与NF4跨运行时对比无法隔离训练效果。
- 需要独立的人类盲评与更大、真实来源/边界案例集复核可靠性和自然度；本轮只有单助手可见配置复核。

原始依据：[exp_001结果](experiments/exp_001/result.json)、[exp_002结果](experiments/exp_002/result.json)、[plain逐条复核](reviews/exp_001.json)、[RAG逐条复核](reviews/exp_002.json)、[预注册计划](plan.md)。
