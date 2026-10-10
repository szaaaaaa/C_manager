# 下一轮：目标表达与拒猜分布的三臂实验

研究项目：`D:\small-model-experiments`；MambaResearch project_id `46bb9df518194783a69ee24582b3b7c6`；run_id `exp_20261010_150741`。本计划与数据目前等待主代理核对冻结，尚未运行 GPU，不能当作质量或训练成功结果。

研究问题：在同一新鲜 Qwen3.5-4B NF4 基座及等量训练条件下，有据的表达多样性是否改善自然度而保持忠实性？把普通未知样本替换成近似路径、缺资料、不相关资料和要求猜测的负例，是否改善拒猜？上一轮013选中adapter作为历史参照，不能把它与本轮的差别单独归因表达或难负例，因为训练数据数量、事实措辞和步数也改变了。

| 臂 / 训练实验 | 阳性 | 阴性 | 目标回答 | 阴性分布 |
|---|---:|---:|---|---|
| A / exp_001 | 96 | 64 | 每个已知家族一个审慎目标，未知一个目标 | 普通无资料路径 |
| B / exp_002 | 96 | 64 | 八家族及未知各四种有依据表达，均衡出现 | 与A逐行相同 |
| C / exp_003 | 96 | 64 | 阳性整行与B相同，未知仍四种表达 | 16近似路径、16缺资料、16不相关资料、16请求猜测 |

A/B每行ID、instruction、input、路径、facts和顺序完全相同，只改output表达；目标长度也会改变，这是该表达干预的一部分。B/C每个阳性记录完全相同，64个阴性槽位等量替换并保持表达编号、行顺序和正负比例。C是负例分布的联合干预，路径、可用资料、用户请求及难度会同时改变，不能声称独立单因素。

资料使用修正v2八个旧家族。WebView2的依赖与Edge浏览器分开，不保证所有文件物理独立；OneNote未同步且无其他副本时可能丢失，不说一定永久丢失；pip是下次**安装**需要时可能重新下载或构建，不是每次运行程序。HF、Node、PyTorch和Temp都保留依赖、备份、占用和不能确认具体内容的条件。详细语义参考随每行保存，来源边界沿用[上一轮官方资料复核](https://github.com/szaaaaaa/C_manager/blob/main/lora-training/experiments/2026-10-10/knowledge-source-audit.md)。不读取用户真实文件验证内容。

[npm-cache和git-objects官方来源](sources.json)支持两个新测试家族，相关词名、路径、事实、命令及目标回答均不进入任何train/validation或其中的干扰资料；仅在主评阳性RAG输入给出。该留出只针对本轮监督数据，不宣称预训练从未见过这些知识。新knowledge-v2同时收录测试条目，运行训练只能读冻结train文件，不能把完整知识库随机生成训练输入。

共享32条验证：八旧家族各2阳性（16），四类拒猜各4阴性（16），与训练和测试精确路径分离。所有臂使用同一份验证目标，只在step20/40间按answer-only验证NLL选择checkpoint；step0为诊断，不参与选择。验证答案表达与训练变体有交集、家族事实共享，验证不是独立知识泛化集，NLL不等同解释正确率。72评测不得用于checkpoint选择、早停、调参或改写目标。

| 评测部分 | 条数 | 用途 |
|---|---:|---|
| 历史24 | 24 | 原始014/015 messages逐条一致，沿用旧facts，单独诊断 |
| 主评：已训练家族阳性 | 16 | 每个旧家族2个新路径，修正v2资料 |
| 主评：近似/缺资料拒猜 | 16 | 8近似、4形似但缺资料、4普通未知 |
| 主评：监督未见家族阳性 | 8 | npm-cache、git-objects各4，测试时给官方支持facts |
| 主评：干扰/冲突 | 8 | 4有适用资料但附不相关资料；4未核验候选冲突，应拒猜 |

四个eval exp_004–007分别加载历史013 adapter、A、B、C，使用同一冻结72条messages。主评有20条必须拒猜（16未知/缺资料+4冲突）；历史24有7条。新48精确路径不与任意训练、验证或历史24重叠。路径字符串隔离不意味着独立事实，全部都是合成家族案例，不是实际文件扫描或恢复验证。C训练没有矛盾候选负例，主评冲突考查拒猜组合应用，不是照背训练的冲突格式。

主目标冻结为主48：严格资料忠实性≥44/48，必须拒猜20/20，危险清理主张0，自然度均值≥4/5；空答、截断和thinking泄漏均0、完成48。严格忠实仅判断回答实际提出的实质主张是否由适用资料支持、无关系/模态矛盾或干扰迁移，以及未知是否合理拒猜。遗漏信息单独计任务完成和必要条件覆盖，不自动使strict失败；无根据的安全或恢复保证仍使strict失败。已知任务完成≥26/28，其中监督留出两家族的supported_complete（strict与任务完成同时成立）≥7/8，忠实性与完整性分别报告；必要风险条件覆盖另列计数。每条reference、match_reason、minimal_supported_claims和required_risk_caveats均保存；不得用关键词作事实率。历史24质量计数和旧cue只另报，不与主48合并替代目标。评分助手知道研究设计；主代理先隐藏条件标签、实验编号和权重目录，冻结逐条评分与review SHA后再揭盲，保留回答SHA和证据短句。这是条件盲化，不是独立真人盲评，风格也可能泄露组别，不做显著性或总体安全保证。参见[审阅协议](review-protocol.md)。

训练共同设置：固定公开`unsloth/Qwen3.5-4B` revision `3764fa359b9082ea5a1e4a5e3ac3aaf6e9671636`，本地`models/qwen35-4b-training`及上一轮权重SHA清单；每臂新鲜载入同基座、新初始化rank8/alpha8 q/k/v/o LoRA、dropout0，NF4 double quant/BF16 compute，seed42、LR5e-5、warmup3、cosine、AdamW8bit、batch1×accumulation4、40 optimizer steps（160条一epoch）、answer-only loss、seq768、无packing。实际tokenizer预检超768即失败，不静默截断或删样本。共同推理seed42、do_sample=False、enable_thinking=False、max_new_tokens256、use_cache=True；确认tokenizer的实际im_end EOS。四组基座723参数/346quant_state和相同messages、生成设置需逐项核验，adapter实际runtime dtype也记录，不把磁盘BF16当成运行FP32/BF16证据。

硬件RTX5070 Laptop 8GB、RAM32GB；仅串行GPU、锁文件、每次包含加载/训练或72条推理的硬时限1740秒，超时保留真实失败与部分记录，新编号修复。上一轮加载allocated8163.07MiB已超7168MiB余量目标，本轮不能承诺加载适配或全程余量；分别保存CUDA加载和训练/推理峰、设备采样口径与OOM。官方Qwen3.5指南不推荐QLoRA，本轮仍是本机受限可行性实验。已有num_items_in_batch梯度累积警告若出现要如实保存，未量化影响不宣称等同精确大batch。

所有模型、缓存和新产物在D盘。`D:\C_manager`与上一轮均只读，源码固定`c1a1b7a1fc0f117ffc2a5bcc0f2c10e23a58ebca`；保留同一system prompt/build_sample风格，新的RUN助手直接消费已保存instruction/input，不重新检索新KB去改变历史输入。运行前source根目录enter-experiment.ps1、使用已有finetune Python。GitHub归档不含权重，复现需恢复固定D盘目录及兼容本地运行环境，不能称归档直接一键运行。

[data/manifest.json](data/manifest.json)保存脚本、训练/验证/测试、知识和评分rubric的SHA256与源SHA；[CPU自检](data/self_check.json)已通过结构、对照、隔离、历史精确messages和无目标全文泄露。584个源样本行低于1000（三个160+32+72），两个eval切片只是派生副本。主代理核对及tokenizer检查后冻结文件，之后不覆盖数据生成器输出或先前结果。该设计单seed、小样本、共享事实、合成路径、同助手知道设计的条件盲化评分；B/C每家族仍是四种固定目标模板，而不是开放自然语言表达；不做模型部署、权重发布或GGUF导出。当前只完成设计与CPU数据构建，质量结论待实际运行和逐条审核。
