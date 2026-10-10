# 极小模型微调与本地 RAG 实验

## 2026-10-10 第二轮：表达多样性与困难负例

本轮在 `D:\small-model-experiments\outputs\exp_20261010_150741` 执行，继续复用D盘固定基座与环境。训练前[公开冻结计划](https://github.com/szaaaaaa/C_manager/blob/86385a7935bb47b9b8781a97cef288ba495cc884/lora-training/experiments/2026-10-10-round2/plan.md)及数据、脚本、评分规则。A单一表达、B丰富表达、C丰富表达加困难负例，各160条训练、共享32条验证；三次新鲜NF4基座各40步，rank8注意力LoRA，检查点只按验证NLL选择，三组都选40步。A/B/C独立目标答案数为9/36/36，B/C每个家族只有四种固定变体，不是开放语言多样性。

旧适配器和A/B/C各生成相同72条输入的回答。以下只报告新48主评，历史24单列；全部288条逐条条件匿名审阅，19条预揭盲一致性修订保留完整前后记录，评分和修订SHA冻结后才关联组别。自然度列为1–5分总分除以48，保留原始分子分母。

| 主评条件 | 资料忠实性 | 拒猜 | 已知完成 | 新家族支持且完整 | 危险主张 | 自然度 |
|---|---:|---:|---:|---:|---:|---:|
| 旧适配器 | 31/48 | 14/20 | 23/28 | 6/8 | 2 | 177/48 |
| A：单一表达 | 28/48 | 10/20 | 21/28 | 3/8 | 2 | 175/48 |
| B：丰富表达 | 25/48 | 8/20 | 24/28 | 5/8 | 1 | 177/48 |
| C：丰富表达＋困难负例 | 29/48 | 10/20 | 23/28 | 6/8 | 0 | 178/48 |

**所有条件都未达全部目标**（忠实性≥44/48、拒猜20/20、完成≥26/28、新家族支持且完整≥7/8、危险0、自然度均值≥4）。A→B丰富表达未改善忠实性；B→C的困难负例包部分改善，但不能声称比旧适配器全面更可靠。C的新家族严格支持8/8与支持且完整6/8必须同时报告。共享验证NLL为A2.5631814002990723、B2.53952693939209、C2.536159038543701，最低NLL不等于最佳解释。必要条件完整覆盖条目为60/100、57/100、46/100、49/100，遗漏与事实主张错误分别评价。

见[最终报告](experiments/2026-10-10-round2/report.md)、[最终分析](experiments/2026-10-10-round2/analysis.md)、[原始匿名评分](experiments/2026-10-10-round2/reviews/blind-review.json)、[匿名修订记录](experiments/2026-10-10-round2/reviews/blind-revisions.json)、[汇总](experiments/2026-10-10-round2/review-summary.json)、[执行核验](experiments/2026-10-10-round2/ml-verify.json)。预注册规格文件中的planned是执行前状态；实际终态见每项result.json和原生退出记录。

两家族npm-cache/Git-objects只在评估时提供资料，未在本轮监督训练/验证或旧168条数据中出现；不代表基座预训练未见。全部新48条件都有冻结RAG资料，且都是旧或新适配器，没有无RAG或未微调基座对照，也未测试动态检索链。因此不能从本轮独立测定微调或RAG的整体增益。A→B同时改变目标措辞与长度，B→C同时改变负例路径、请求及资料分布，不是单一抽象因素的因果隔离。单seed、合成路径、同助手条件匿名评审、初始LoRA值未保存跨组哈希限制归因，仍需独立真人复核。旧适配器历史24条原答与第一轮相同24/24；本轮评分13/24与旧17/24是判读/一致性校准差异，不能当行为退化。

七项GPU和observer均真实退出0，无OOM；加载allocated峰8091.861328125–8130.70068359375MiB，超过7168MiB余量目标。PyTorch allocated/reserved和nvidia-smi稀疏设备采样不能混为一个峰，Windows驱动共享显存/分页未单独测量。三组训练期间723基座参数与346量化状态未变、64个LoRA张量更新；适配器存储BF16，实际推理为FP32。本轮没有新GGUF转换或应用集成。

复现需恢复报告规定的D盘目录布局及固定本地基座、软件环境和权重清单。归档的environment.ps1是根目录enter-experiment.ps1的字节副本：应恢复到 `D:\small-model-experiments\enter-experiment.ps1` 并从根目录加载，不能直接在run目录加载而改变缓存根。GitHub不含基座、适配器权重和checkpoint；三组选定权重及SHA见各adapter-manifest.json，权重保留在D盘。

## 2026-10-10 第一轮：量化模型与微调对照

新的独立实验目录为 `D:\small-model-experiments`，权重、缓存与产物均在 D 盘；原 `D:\C_manager` 作为只读代码和数据来源。本轮 [计划](experiments/2026-10-10/plan.md) 分为三部分：三个量化模型的无资料/RAG 对照、4B NF4 QLoRA 的可行性与检索感知 SFT、同 NF4 基座的微调前后评估。GGUF 部署量化与训练 NF4 是不同格式，跨运行时差异不能直接叫微调收益。

三种量化模型的六组推理和4B检索感知NF4 LoRA训练、同基座RAG配对评估均已完成。见[完整报告](experiments/2026-10-10/report.md)、[最终逐条分析](experiments/2026-10-10/analysis.md)、[研究计划与进度](experiments/2026-10-10/progress.md)；[量化阶段报告](experiments/2026-10-10/report-quantized.md)和[4B阶段报告](experiments/2026-10-10/report-4b.md)保留为历史阶段。

三个GGUF的RAG严格资料忠实性为4B14/24、9B10/24、Gemma17/24，未知拒猜5/7、2/7、3/7。NF4同基座配对在加入checkpoint38适配器后，严格资料忠实性13/24→17/24、未知拒猜6/7→6/7、危险主张0→0、自然度3.67→3.83；关键词反而23/24→19/24。没有条件达成完整目标，0危险主张不保证真实文件删除安全，关键词和验证NLL不是事实准确率。

正式训练150条、目标group留出18条，38步NLL2.2960→1.9347，训练期间723基座参数及量化状态不变，64个LoRA张量更新。初始007/011失败及008—010阻塞记录保留，012追加诊断区分准备期dtype转换和训练更新，013—015是条件执行的独立追加实验。150条训练仅110条唯一路径、8种目标答案；测试精确路径无重叠，但所有8类事实都有训练输入曝光，pip事实也在其他目标组干扰样本中出现，不能称知识完全留出。[数据审计](experiments/2026-10-10/data-audit.json)、[失败诊断](experiments/2026-10-10/failure-analysis.md)、[用途来源支持范围](experiments/2026-10-10/knowledge-source-audit.md)可核对。

4B正式训练CUDA allocated加载峰8163.07MiB、训练阶段峰3814.54MiB，分阶段口径不能混用；未OOM不代表7168MiB总峰目标达成。适配器存储BF16，PEFT推理加载为FP32；NF4 CUDA与GGUF Vulkan结果不能用于隔离微调作用。本轮尚未导出新GGUF或做应用集成。权重、缓存及结果在D盘，GitHub只保存研究证据与权重SHA清单，复现需要恢复报告说明的本机目录布局和环境。

Unsloth 官方指南列出 4B BF16 LoRA 约需 10GB，并仍不推荐 Qwen3.5 QLoRA。本机上一轮已完成两步诊断和38步 NF4 LoRA训练，但加载峰超过7GB余量目标；这只证明该固定环境下的训练可执行，不证明量化无损、显存宽裕或解释可靠。[官方训练指南](https://unsloth.ai/docs/models/qwen3.5/fine-tune)。下面的训练与部署步骤对应此前 0.8B 实验，不是本轮 4B 配置。


目标是在 Qwen3.5-0.8B 上比较闭卷解释和依据用途资料的解释，实测事实错误、未知用途的谨慎程度、清理风险、语言表达与延迟。

早期方案中“规则零误判”“几分钟训练完成”“0.3–1 秒回答”“微调后准确性中高”等描述缺乏对应实测，本说明已移除。完整 C 盘的扫描速度也不能由浅层扫描时间推算。

## 数据和方法

- `data/training_data.jsonl`：纯微调基线数据。`scripts/generate_training_data.py` 使用本机扫描数据和人工模板生成，`high` 是模板标签，不代表已经核实所有事实。此前存在判定占位符、错误删除建议和模板重复，已修正发现的问题；这份数据保留用于对照，仍不应当作权威资料库。
- `src-tauri/src/safety/knowledge.json`（项目根目录下）：应用和实验共用的本地资料，含路径条件、用途/删除影响/建议、自然回答示例和来源链接。推理只注入 `facts`，不注入答案示例。当前八类路径覆盖有限，也不读取文件内容。
- `data/rag_training_data.jsonl`：由资料库生成的 168 个训练样本，包含相关资料、相关和无关资料混合、缺少匹配资料、未知路径。训练的是使用证据和表达不确定性，不能通过这份数据证明模型掌握了所有软件知识。
- `data/eval_cases.json`：训练前冻结的 24 条测试路径及检查条件。用户名、版本、盘符和文件名与新训练样本分开；知识类别仍有重叠。另按完整知识类别留出训练验证组。

这是借鉴 [RAFT](https://arxiv.org/abs/2403.10131) 的检索感知 SFT，小样本且未复现论文完整方法。第一轮使用路径条件检索，不引入向量库。生成的重复路径样本也不等于新增独立事实。

## 环境

本次使用 Windows、RTX 5070 Laptop GPU（约 8GB）、PyTorch 2.10.0+cu128、Unsloth 2026.3.10、Transformers 5.3.0、TRL 0.24。具体版本与 GPU 信息保存到结果中。需要正确安装 CUDA 对应的 PyTorch；不能依赖普通 CPU Python 环境运行训练。

使用独立 Python 环境安装 `requirements.txt`。Qwen3.5 使用 BF16 LoRA、1024 token 最大训练长度、非思考模式，并掩码掉系统/用户输入，只计算助手回答的损失。过长样本报错，不截断正确答案。参考 [Unsloth Qwen3.5 文档](https://unsloth.ai/docs/models/qwen3.5/fine-tune) 和 [TRL SFT 文档](https://huggingface.co/docs/trl/v0.24.0/sft_trainer)。

## 复现

以下命令在 `lora-training/` 下、正确的 CUDA Python 环境中执行。先下载原始完整权重，四组应使用同一基础版本：

```powershell
hf download unsloth/Qwen3.5-0.8B --revision 23c69c53358a07516b5827588b3fdb12ae78fd65 --local-dir output/base_model
python scripts/grounding.py
python scripts/generate_rag_data.py

# 基础模型，不提供资料
python scripts/evaluate.py --model output/base_model --mode plain --output experiments/run/base-plain.json

# 基础模型，提供检索资料
python scripts/evaluate.py --model output/base_model --mode rag --output experiments/run/base-rag.json

# 从原始基础模型训练检索感知 LoRA：固定 2 epoch、lr=1e-4
python scripts/train_rag.py --base-model output/base_model
python scripts/evaluate.py --model output/rag_model --mode rag --output experiments/run/sft-rag.json
```

纯 SFT 对照使用本次已保存的 `output/corrected_model/`，执行 `--mode plain`。这是 3 epoch 训练再继续纠错 1 epoch 的历史配方；完整预算和样本数见 [实验协议](experiments/2026-10-09/PROTOCOL.md)，不能把四组差异简单归因于一种算法。要重新训练纯 SFT，需在 `finetune.py` 中显式选择原始数据和单独的输出目录，防止覆盖对照权重。

`evaluate.py` 四组采用相同系统指令、BF16、greedy、256 token 上限和 `use_cache=True`，逐条保存回答、耗时和数据哈希。`cue_pass` 只是关键词检查，不能直接叫作“准确率”；需要对照资料逐条核实，尤其是包含关键词但功能或删除影响错误的回答。这里的 GPU 耗时也不能当作应用 CPU 延迟。

训练指标写入模型目录的 `training_report.json`。默认 `finetune.py` 使用 RAG 数据，但参数是脚本顶部通用配置；`train_rag.py` 固定本次实验参数和独立 `rag_model` 输出。

## GGUF 导出和应用

导出需要完整且配套的 llama.cpp HF 转换器、其 Python 包，以及 `llama-quantize` 可执行文件。可通过 `UNSLOTH_LLAMA_CPP_PATH` 指向工具目录。不要只下载最新的单个转换脚本：当前 upstream 可能依赖额外的 `conversion` 模块。脚本先保存合并的 BF16 权重，再调用同一工具链转换 BF16 GGUF 和 Q4_K_M；两个命令都成功后才替换最终文件，导出失败不会把旧文件伪装成新结果。

固定实验输出为 `output/rag_model_gguf/qwen3.5-0.8b-q4_k_m.gguf`。应先通过原生 llama.cpp 测试再部署：

```powershell
cd ../src-tauri
$env:C_MANAGER_TEST_MODEL = 'D:\C_manager\lora-training\output\rag_model_gguf\qwen3.5-0.8b-q4_k_m.gguf'
cargo test --lib local_model_chinese_and_explanation_smoke -- --ignored --nocapture
```

开发版的默认路径是 `output/finetuned_model_gguf/`，不是所有实验输出目录。将通过验收的模型复制到该默认目录和 `src-tauri/resources/` 后，重启并重新加载模型；发布版从打包 resource 读取。权重、编译缓存和原始扫描数据均不提交 Git。

本轮结果见 [RESULTS.md](experiments/2026-10-09/RESULTS.md)。检索感知 SFT＋RAG 的关键词检查为 21/24，但逐条审阅仍发现 pip 删除影响错误、过于绝对的恢复表述和重复模板。原生 CPU 中文解码和六条解释 smoke 测试已通过，本机默认开发/资源目录已换为这个实验模型；旧资源保留在忽略的 `output/legacy_model_gguf/`。这不是普遍准确率或语言自然度验收，权重没有推送 GitHub。

尚未做独立软件类别的大规模盲测，不能声称 RAG 已消除幻觉，也不能把低验证 loss 当成安全删除建议的保证。




