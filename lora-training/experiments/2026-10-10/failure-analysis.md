# 微调冒烟失败与冻结基座诊断

本文件分析exp_007、exp_011两次真实失败，以及另编号exp_012的追加诊断。007/011维持failed、exit_code=1；012程序success/exit_code=0只证明本次两步冒烟通过冻结/更新检查，不能证明此前失败已成功，也不能证明微调输出质量改善。正式训练exp_013及成对评测未纳入本文件结论。

| 实验 | 状态/退出码 | 实际优化器步 | 总秒 | 直接证据 |
|---|---|---:|---:|---|
| exp_007 | failed / 1 | 0 | 121.341 | SFTConfig不接受save_safetensors参数 |
| exp_011 | failed / 1 | 2 | 181.038 | changed_base==0 and changed_lora>0联合断言失败 |
| exp_012 | success / 0 | 2 | 146.090 | 训练阶段723基座张量及quant_state不变，64个LoRA参数张量改变 |

## Findings

1. exp_007失败发生在SFTConfig构造阶段，原始异常为`SFTConfig.__init__() got an unexpected keyword argument 'save_safetensors'`。模型已加载并检查到346个实际bitsandbytes NF4+double quant+BF16 compute的Linear4bit模块，prompt mask/最长429token与可训练1,572,864标量参数已记录，但优化器步0、训练日志和回答记录为空。它是接口兼容失败，日志没有OOM异常；不能从没有OOM推出显存目标达成。依据：[result](experiments/exp_007/result.json)、[run.log](experiments/exp_007/run.log)、[实际脚本](experiments/exp_007/executed_training.py)，SFTConfig传入参数见脚本196至207行。

2. exp_011去掉不兼容参数后实际完成两步训练、两次验证，loss/梯度有限，但最后`assert changed_base == 0 and changed_lora > 0`失败。原脚本在断言之后才保存两个changed count，result/observations没有单独计数，因此只能确定至少一项条件不满足，不能说基座一定改变、LoRA一定未更新，或精确多少个参数改变。梯度和训练loss下降也不能代替参数更新/冻结验证。failed状态不能改为success。依据：[result](experiments/exp_011/result.json)、[原始观察](experiments/exp_011/observations.json)、[实际脚本](experiments/exp_011/executed_training.py)219至230行及run.log。

3. exp_012把准备期和训练期分开观测，保存四份状态：Trainer构造前、构造后、step0验证/切回训练后、两步训练后且最终验证前。分析者从文件独立复算如下。状态捕捉固定基座名集合，排除LoRA；每阶段723个基座参数张量、requires_grad全false，346个有量化状态hash。对基座比较dtype、shape、原始bytes SHA256和quant_state SHA256，同时为浮点参数比较统一FP32后的值hash。依据：四份base_*.json、base_stage_changes.json及实际脚本119至176、239至249行。

| 比较区间 | raw/dtype/shape/quant_state变化数 | FP32数值hash变化数 | quant_state变化数 |
|---|---:|---:|---:|
| Trainer构造前→构造后 | 0 | 0 | 0 |
| 构造后→step0验证/切回训练后 | 203 | 0 | 0 |
| step0验证/切回训练后→训练后 | 0 | 0 | 0 |

准备期间203个参数张量全部FP32→BF16，shape相同、统一FP32数值hash相同，分布为language_model 105、visual 98；这批具体观测是表示dtype变化，没有观察到值更新或量化状态变化。构造前的dtype分布为uint8 346、FP32 203、BF16 174；训练前及训练后为uint8 346、BF16 377。旧脚本hash包含dtype和原始字节，因而这类准备期变化本身会触发hash差异；但exp_012的证据不能倒填exp_011联合断言的具体失败项。转换发生在首次验证与切回训练所覆盖的区间，未细分到具体库函数，不能单凭端点定位是哪次内部调用。

base_stage_changes.json的after_training_before_final_eval列203条，是该阶段相对最初before_trainer的比较，包含同一批准备期dtype变化；不能把它解释成训练新改了203个基座张量。真正训练区间基线是after_step0_before_training，随后723个张量的严格raw/dtype/shape/quant_state比较变化0。分析者已从四份JSON独立验证这一区分。

4. exp_012训练期间仅LoRA改变：记录changed_lora_parameter_count=64，changed_base_parameter_count=0，base_parameter_hashes_checked=723，两个优化器步的post_clip_grad_norm约0.99838和0.99755，有限loss/gradient与mask验证均通过。64是改变的LoRA参数张量数量，不是64个标量；总可训练标量参数1,572,864。脚本在准备后另存LoRA快照，并把基座变化/LoRA变化分别持久化再分别断言，避免011的不可诊断联合失败。基座JSON可独立复核，LoRA64依据运行期间前后torch.equal比较与result记录；没有额外保存LoRA前后两份全量张量，不假称这里重新执行过GPU训练。依据：[result](experiments/exp_012/result.json)、executed_training.py320至355行及保存的adapter目录。

5. 012仅8条训练样本、18条pip-cache家族验证、2步，是技术可行性冒烟；step0验证loss=2.2960197926，末次2.2939100266，差=-0.0021097660。小幅loss变化不能说明文件解释可靠性或表达更自然，也没有本次24案例生成结果。训练过程中基座不变的边界限于捕捉的723参数及346份quant_state，不含所有可能非参数buffer、隐式运行时状态或训练后最终验证期间的再次变化。依据：result、四阶段状态以及最终验证在capture之后的执行顺序。

## 显存目标与阶段口径

预注册peak_allocated_gpu_mib目标<=7168MiB。012实际包括加载的allocated峰8086.4863MiB，超过918.4863MiB（约12.81%）；007整体8089.1113MiB、011整体8128.2007MiB也超目标。012未发生OOM且训练阶段明显更低，不能将成功运行写成显存余量目标达成。

| exp_012阶段 | allocated MiB | reserved MiB | 口径 |
|---|---:|---:|---|
| 加载期间峰 | 8086.4863 | 8150.0000 | 首次reset后加载区间，保留加载瞬态 |
| 已加载当前占用 | 3168.7988 | 4464.0000 | 加载结束时点，非峰 |
| 准备与step0峰 | 4164.2373 | 未单独记录 | 加载后reset至训练前reset |
| 训练峰 | 3602.1299 | 4524.0000 | 训练前reset至trainer.train返回 |
| 最后一次reset后的后段峰 | 3806.8936 | 5044.0000 | 包含训练、hash捕捉、最终验证与保存；泛字段不是全程reserved峰 |
| 包含加载的汇总allocated峰 | 8086.4863 | 不用5044替代加载reserved峰 | 汇总取已记录阶段allocated最大值 |

loaded current与training峰不能相加。generic peak_reserved_gpu_mib=5044是在训练前重置统计后最终读取的后段峰，不含加载reserved峰8150；把5044写成全程峰会隐藏加载压力。007/011未分阶段重置统计，因此其整体CUDA allocator峰不能直接称训练阶段峰。011另有nvidia-smi加载后12次设备总采样最大4760MiB，它是较稀疏的加载后观察，既非CUDA加载瞬态峰也非每进程最大值，不能用4760否定CUDA记录的8128.20或推出加载永远低于7168。Torch allocated/reserved与nvidia-smi设备总占用口径不同，未收集驱动驻留/共享内存细分，不推断发生了具体分页或内存迁移。

## Conflicts 与限制

- Unsloth控制台曾打印“Switching to16bit LoRA”；实际加载代码显式BitsAndBytesConfig NF4/double quant/BF16，运行后346个Linear4bit量化类型/state2/compute_dtype断言通过。本轮量化身份按实际模块检查报告，控制台泛化信息不能替代模块证据；也不把日志警告当成QLoRA质量得到保证。
- 原始011检查含dtype且把准备前与训练后混在一对hash里；012揭示可存在值相同的dtype转换。追加分阶段基线是改善验证证据，保持严格训练冻结检查，而不是允许优化器任意更新基座。它也不是对011原因的确定回溯归因。
- 接口移除参数、显式EOS对齐（248044→tokenizer <|im_end|>248046）、准备期状态/内存分段记录属于脚本兼容与诊断改动；012不是原007脚本无修改复现。actual配置和执行脚本各自保留，不能混用某次结果证明另一次。
- 时间包含import/首次forward/优化器调用及可能编译，没有独立编译计时，012缓存较热；不从两次总时间差单独推断训练速度优化。状态hash捕捉也增加约四次8至10秒CPU复制/校验开销。
- 012程序success但显存目标未达；仅短序列429token最大实际样本、batch1累积4、rank8注意力LoRA两步运行，不外推9B训练、全参数训练、长序列或并发，也不代表8GB设备有充足余量。

## Open questions

- 正式训练exp_013在150/18整家族留出划分上能否完成预定步数、继续保持训练期基座冻结、控制加载峰并选出有效adapter？需要对应实际结果，不能继承冒烟64改变作为正式训练证明。
- 相同NF4基座/runtime和资料输入的exp_014/015成对评测能否改善未知拒猜、资料矛盾及自然度？GGUF与NF4/runtime不同，不能用两者差异隔离adapter效果。
- 若要达到7168MiB余量目标，需要另外设计不掩盖加载峰的加载路径/模型结构或内存方案并实测；本轮不因训练峰低就删除加载峰记录。

本分析只读原始文件，没有修改failed状态/原结果或启动GPU。产物与数字均来自exp_007/011/012真实退出码、日志、冻结状态文件及实际执行脚本。
