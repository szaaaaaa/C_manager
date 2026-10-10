# 极小模型微调与本地 RAG 实验

## 2026-10-10：量化模型与微调对照

新的独立实验目录为 `D:\small-model-experiments`，权重、缓存与产物均在 D 盘；原 `D:\C_manager` 作为只读代码和数据来源。本轮 [计划](experiments/2026-10-10/plan.md) 分为三部分：三个量化模型的无资料/RAG 对照、4B NF4 QLoRA 的可行性与检索感知 SFT、同 NF4 基座的微调前后评估。GGUF 部署量化与训练 NF4 是不同格式，跨运行时差异不能直接叫微调收益。

三种量化模型的六组推理均完成：[量化阶段报告](experiments/2026-10-10/report-quantized.md)、[逐条分析](experiments/2026-10-10/analysis-quantized.md)、[执行进度](experiments/2026-10-10/progress.md)。三个RAG条件严格资料忠实性为4B 14/24、9B 10/24、Gemma 17/24；未知拒猜为5/7、2/7、3/7，没有一组达成完整可靠性目标。9B关键词24/24不代表事实正确，Gemma的0资料矛盾/0危险主张仅对应当前定义和24个合成案例。评审为单助手可见配置复核，原始回答、SHA与理由全部保存；[4B阶段报告](experiments/2026-10-10/report-4b.md)保留。NF4训练和适配器效果仍待实测。

Unsloth 当前估计 4B BF16 LoRA 约需 10GB，且不推荐 Qwen3.5 QLoRA；8GB 本机的 NF4 训练须先通过两步冒烟，结果未知。[官方训练指南](https://unsloth.ai/docs/models/qwen3.5/fine-tune)。下面的训练与部署步骤对应此前 0.8B 实验，不是本轮 4B 配置。


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
