# CPU数据与评价预审：passed

固定project D:\small-model-experiments，project_id 46bb9df518194783a69ee24582b3b7c6；run exp_20261010_150741。**输入数据与最终计划/评价元数据独立CPU审计通过，无阻塞数据异常。** 本状态不代表GPU训练、实际label mask、参数冻结、推理runtime或解释质量通过；这些运行门槛由主聊天与训练角色核验。本审阅未读取任何本轮实验result/records、运行器或decode-map，没有GPU执行。

## Findings：实际核验结果

1. [data-audit.json](data-audit.json)按磁盘实际内容重算data全部manifest文件bytes/SHA，均匹配；72评测=历史24+主48派生数组逐项相同，不计派生切片为额外样本。三臂各160=96阳性+64阴性，共享32val=16阳性+16阴性；每份train和val内路径均唯一。主48为28已知/20必须拒猜，历史24为17已知/7拒猜。
2. A/B逐ID全部instruction/input/路径/facts/reference/行顺序相同；120行output及target_variant改变，其余40行相同。A精确目标9种、B36种，并非160个独立表达。B/C96阳性整行相同，64负例全部替换，原普通未知换为16近似、16缺资料、16不相关资料、16要求猜测；64个负例目标文本及全局ID顺序保持相同。
3. 按外空白、斜杠、Unicode casefold与末尾斜杠归一，train/val/test精确路径交集均0，train/val/test完整input交集也0。历史24的ID/路径/messages与上一轮014和015逐项相同，使用原KB SHA547f1cb9e11aae21796c4d7fe897b90f52dd8fe5bceec6b726ffc28a4d25cf0d；新facts没有重建旧输入。路径字符串隔离不证明内容、家族事实或模板独立。
4. 独立遍历ABC/val及旧168全部字符串字段，npm-cache/_cacache/npm cache、git-objects/.git/objects/git gc/对象库等词与语义锚点、两家族完整facts均0曝光；逐条目标/资料审阅未见等价新家族事实。只称监督数据无曝光，不证明预训练未知。八旧家族facts在监督数据共享、验证表达与训练模板重叠，这些边界保留。
5. 20个必须拒猜都没有一段已核验且匹配的family facts。8近似路径、4形似但缺资料、4普通未知，以及4明确未核验候选冲突，标记合理；4干扰阳性有匹配第一段和另路径第二段，应答已知且拒绝迁移干扰。两个新家族各4阳性在资料中明确指定合成缓存配置/仓库对象库成员，不要求仅凭同名路径认证真实来源。
6. 全32已知表达变体及4未知模板对照v2 facts未发现无根据功能/恢复保证；部分目标省略单独列出的风险解释或工具，不等于每个目标都已任务完整。输出字符/token量不同，不把多样答案干预归因唯一文风变量。实际target（含终止）token总数A7976、B7517、C7517；B/C负例长度不变但输入难度/上下文分布改变。
7. CPU用固定本地tokenizer先render chat template（enable_thinking=False）再encode，无模型/CUDA加载。实际train完整序列最大A375/B378/C439，val413，均≤768；全部prompt为完整序列的精确前缀。72评测最长输入432，加max_new_tokens256为688≤2048。本检查不验证执行训练的-100 label mask，实际mask/无截断门槛仍由训练角色检查。
8. 最终[plan](plan.md)、[004 spec](experiments/exp_004/spec.md)、[007 spec](experiments/exp_007/spec.md)与[data/grading_rubric](data/grading_rubric.json)已经一致：strict只评实际主张与校准；遗漏单列known_task_complete/necessary_caveats；主要strict≥44/48、拒猜20/20、unsafe0、自然度≥4、已知完成≥26/28，留出supported_complete=strict AND known_task_complete≥7/8。主48必要条件条目固定100，历史24固定48。
9. [分析者rubric v2](rubric.md)在读任何新回答前固定，原strict/风险/自然度尺度保持；同助手条件盲化、shuffle seed1042、root独占map、评分SHA冻结后才揭盲。该方法不是独立真人盲评，设计/旧回答先验及文风识别风险仍在。数据自检/manifest原non-blind和strict混入遗漏描述已由design角色修正，本预审未修改其文件。

## Conflicts：已解决与持续边界

初版grading_rubric把最少用途/必要条件混入strict，并仍写non-blind。最终文件已将任务完成及条件覆盖分离，条件标签隐藏直到评分冻结，沿用原strict；这些是读本轮答案前的设计修订，不是看到效果后改尺度。

npm官方资料支持配置缓存、opaque内容寻址、verify/空间回收clean与不能保证具体资源总可再得；它不认证任意用户同名文件。Git对象库结构支持仓库数据用途与手删损坏的保守推论，gc并发/备份条件保留，不保证远程包含本地未推送内容。审阅者本次读sources注册与冻结facts，没有再次浏览官方网页或读取真实用户文件；来源owner的官方资料复核仍是来源证据，不能将此CPU通过称为真实文件内容验证。

历史24已经用于识别上一轮问题并影响新设计，只作回归诊断；新48也是合成封闭家族案例。A/B目标长度及表达同时变，B/C负例路径/可用资料/用户请求同时变，旧adapter训练规模/事实/步数不同。研究只能描述对应训练包的差别，不支持纯单因素或统计显著性主张。C未训练矛盾候选负例，冲突测试属于组合拒猜应用。

## Open questions：运行与质量仍待证据

root随后冻结数据/本rubric/审计/预审SHA并先公开协议，分析者不会覆盖冻结文件；新发现写analysis.md/evidence.json。训练角色须实测每组40步/验证选模、mask、有限非零梯度、LoRA更新与真实基座冻结、num_items_in_batch警告、包含加载的显存峰和实际退出码。主聊天全部checkpoint固定后生成匿名审阅包，逐条review只读匿名ID/facts/refs，不读本轮结果/条件映射；揭盲后才关联原记录/actualruntime/质量目标。当前不存在解释质量结果。

## 本预审实际读取的最终SHA256

| 文件 | SHA256 |
|---|---|
| [sources.json](sources.json) | 09b84f87ff9bac166f5caa31282f0c6c74fd1260ef96e205a02bd1689c5d3680 |
| [plan.md](plan.md) | 6af2be541e760bbf9bcc19ae922b7421123c7db897aa1b508b9fd1143b2a094b |
| [data/manifest.json](data/manifest.json) | 9bf0a899a8b4b049f15dc244b92e859274ab876521222ef4cec81cc5a4b70dda |
| [rubric.md](rubric.md) | faa7944c139b30606c4942f34dfeda5289044de31051e6c0052c68916f7d7b8a |
| [experiments/exp_004/spec.md](experiments/exp_004/spec.md) | 8e5a012b5b851ba3c3ed5d868c25f393de861d868069530bf14a270d72dd58e7 |
| [experiments/exp_007/spec.md](experiments/exp_007/spec.md) | 362c9104880dd3fb0060b690f938f684342f8e13088ef7f46359d4683ce98cfd |
| [data/grading_rubric.json](data/grading_rubric.json) | 8ebb39e89c70dffb77b7d13bafbb13136c81a4f8b1a32bda8d640d1737ece11b |

[data-audit.json](data-audit.json)实际SHA256：cdde2c662a14b81f1418544a8f2454dc9d23fd0efab9141a0a6fc77968907e24。审计范围为保存数据/计划/评分元数据；未来root冻结清单如补充生命周期状态，应保留此实际快照及其SHA，不将运行成功回填本事前审计。
