# C盘守护者 — 本地小模型微调部署方案

> 目标：用 Qwen3.5-0.8B 蒸馏微调替代云端 API，实现离线、免费、秒级响应的文件解释能力。

---

## 一、方案总览

### 1.1 为什么需要本地模型？

| 对比项 | 云端 API | 本地微调模型 |
|--------|---------|------------|
| 费用 | 按 token 计费 | 一次性训练，永久免费使用 |
| 隐私 | 文件路径上传到第三方 | 所有数据留在本地 |
| 离线 | 不可用 | 完全离线可用 |
| 延迟 | 网络延迟 1-3 秒 | 本地推理 0.3-1 秒 |
| 准确性 | 高（大模型能力强） | 中高（蒸馏 + 规则兜底） |

### 1.2 架构设计

```
用户点击文件
    │
    ├── 第一层：rules.json 规则匹配（确定性，零误判）
    │     ├── 命中 → 直接返回判定，不调模型
    │     └── 未命中 → 进入第二层
    │
    └── 第二层：蒸馏微调后的 Qwen3.5-0.8B
          └── 输入：文件名 + 路径 + 大小
          └── 输出：【名称】【释义】【判定】【理由】
```

**设计原则：模型只做"翻译"（把技术信息翻译成白话），不做"决策"（删不删）。决策权优先由确定性规则兜底。**

> **为什么不用 RAG？** 2026 年 3 月的实证研究 (arxiv 2603.11513) 发现：7B 以下模型 85%-100% 无法正确利用检索上下文，且添加 RAG context 会摧毁 42%-100% 原本能答对的答案。对 0.8B 模型而言，RAG 是净负面效果。正确做法是将知识直接蒸馏进模型权重。

### 1.3 为什么选 Qwen3.5-0.8B？

| 模型 | 参数量 | 内存占用 | 中文能力 | 适合场景 |
|------|--------|---------|---------|---------|
| Qwen3.5-0.8B | 0.8B | ~0.5GB | 良好 | 结构化短文本生成 |
| Qwen3.5-2B | 2B | ~1.3GB | 优秀 | 需要更强推理时备选 |
| Qwen3.5-4B | 4B | ~2.5GB | 极佳 | 预算充足时最优 |

0.8B 选型理由：
- 我们的任务是**结构化短文本生成**（4 行输出），不需要长篇推理
- 通过蒸馏微调可以将大模型知识压缩到小模型中
- 0.5GB 内存占用，普通用户电脑无压力
- 推理速度快，体感秒回

---

## 二、训练数据准备

### 2.1 数据来源策略

训练数据的核心思路：**用大模型（ChatGPT 5.4）标注 → 人工审核 → 喂给小模型学习**。

这在业界叫"知识蒸馏"（Knowledge Distillation），是小模型落地的标准做法。

| 数据来源 | 方法 | 预计数量 |
|---------|------|---------|
| 实机采样 | 扫描真实 C 盘，取典型路径 | ~20,000 条种子路径 |
| 大模型标注 | 用 GPT-5.4 批量生成解释 | ~5,000 条训练样本 |
| 知识库内化 | Windows 系统文件/扩展名/常见软件知识直接编入训练数据 | ~1,500 条补充 |
| 社区知识 | 知乎/Stack Overflow "C盘清理"问答 | ~500 条补充 |

**最终目标：4,000-6,000 条清洗后的高质量训练数据。质量 > 数量，确保三种判定分布均衡（放心删 / 看看再删 / 千万别删各占约 1/3）。**

> **知识内化而非 RAG**：Windows 系统文件说明、扩展名百科、常见软件产生的文件等知识，全部以训练样本形式并入训练集，让模型直接学会，而不是推理时检索。

### 2.2 Step 1：采集真实文件路径

扫描本地 C 盘，导出文件路径作为种子数据：

```python
# scripts/01_generate_seed_paths.py
"""
扫描 C 盘，导出文件路径、名称、大小。
这些路径将作为训练数据的"输入"部分。
"""
import os
import json

def scan_drive(root="C:\\", max_count=20000):
    paths = []
    for dirpath, dirnames, filenames in os.walk(root):
        for f in filenames:
            full_path = os.path.join(dirpath, f)
            try:
                size = os.path.getsize(full_path)
                if size > 1024:  # 跳过小于 1KB 的文件
                    paths.append({
                        "path": full_path,
                        "name": f,
                        "size": size,
                        "extension": os.path.splitext(f)[1].lower(),
                    })
            except (PermissionError, OSError):
                pass  # 跳过无权限的文件

            if len(paths) >= max_count:
                return paths
    return paths

if __name__ == "__main__":
    print("扫描 C 盘中...")
    paths = scan_drive()
    print(f"采集到 {len(paths)} 个文件路径")

    with open("data/seed_paths.json", "w", encoding="utf-8") as f:
        json.dump(paths, f, ensure_ascii=False, indent=2)
    print("已保存到 data/seed_paths.json")
```

运行：
```bash
mkdir data
python scripts/01_generate_seed_paths.py
```

### 2.3 Step 2：数据去重与采样

不需要对所有 20,000 条路径都生成标注。按**路径模式**去重，确保覆盖多样性：

```python
# scripts/02_deduplicate_and_sample.py
"""
按目录前缀和扩展名去重，确保训练数据覆盖面广。
避免 5000 条数据里 3000 条都是 .dll 文件。
"""
import json
import random
from collections import defaultdict

with open("data/seed_paths.json", encoding="utf-8") as f:
    paths = json.load(f)

# 按 (父目录前两级 + 扩展名) 分组
groups = defaultdict(list)
for p in paths:
    parts = p["path"].split("\\")
    # 取前 3 级目录作为分组键
    prefix = "\\".join(parts[:min(4, len(parts))])
    key = f"{prefix}|{p['extension']}"
    groups[key].append(p)

# 每组最多取 3 条
sampled = []
for key, items in groups.items():
    sampled.extend(random.sample(items, min(3, len(items))))

random.shuffle(sampled)
sampled = sampled[:6000]  # 最多 6000 条

with open("data/sampled_paths.json", "w", encoding="utf-8") as f:
    json.dump(sampled, f, ensure_ascii=False, indent=2)

print(f"去重采样后：{len(sampled)} 条")
```

### 2.4 Step 3：调用 ChatGPT 5.4 批量生成标注

```python
# scripts/03_generate_labels.py
"""
用 ChatGPT 5.4 为每个文件路径生成结构化标注。
这是训练数据的"输出"部分。
"""
import openai
import json
import time
import os

client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

PROMPT_TEMPLATE = """你是Windows文件标注专家。根据以下文件信息，严格按格式输出4行，不要多余内容：

【名称】一个专业短名（如"Edge浏览器缓存""WSL虚拟磁盘""Visual Studio编译产物"）
【释义】一句大白话解释这个文件/文件夹是干什么的（不超过20字）
【判定】从以下三个中选一个：放心删 / 看看再删 / 千万别删
【理由】一句话说明为什么（不超过15字）

判定标准：
- 放心删：缓存、临时文件、下载残留、日志等，删了不影响任何功能
- 看看再删：可能影响某个软件的功能，但如果用户不用该软件就可以删
- 千万别删：系统核心文件、驱动、引导文件、注册表等，删了系统可能崩溃

文件：{name}
路径：{path}
大小：{size_human}"""

def format_size(size_bytes):
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / 1024**3:.1f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / 1024**2:.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"

def generate_label(seed):
    size_human = format_size(seed["size"])
    prompt = PROMPT_TEMPLATE.format(
        name=seed["name"],
        path=seed["path"],
        size_human=size_human,
    )
    resp = client.chat.completions.create(
        model="gpt-5.4",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.3,  # 低温度保证输出一致性
    )
    return resp.choices[0].message.content.strip()

if __name__ == "__main__":
    with open("data/sampled_paths.json", encoding="utf-8") as f:
        seeds = json.load(f)

    results = []
    errors = 0

    for i, seed in enumerate(seeds):
        try:
            output = generate_label(seed)
            size_human = format_size(seed["size"])
            results.append({
                "instruction": f"文件：{seed['name']}\n路径：{seed['path']}\n大小：{size_human}",
                "output": output,
            })
        except Exception as e:
            errors += 1
            print(f"  Error at {i}: {e}")

        if i % 100 == 0:
            print(f"Progress: {i}/{len(seeds)} (errors: {errors})")
            # 每 100 条保存一次，防止中断丢失
            with open("data/training_data_raw.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

        time.sleep(0.05)  # API 限速

    with open("data/training_data_raw.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n完成：{len(results)} 条标注，{errors} 个错误")
```

运行（需要 OpenAI API Key）：
```bash
export OPENAI_API_KEY="sk-..."
python scripts/03_generate_labels.py
```

预计耗时：5000 条约 2-3 小时，API 费用约 $5-10。

### 2.5 Step 4：数据清洗与质量检查

```python
# scripts/04_validate_and_clean.py
"""
自动过滤格式不合规的标注 + 人工抽检。
"""
import json
import random

with open("data/training_data_raw.json", encoding="utf-8") as f:
    data = json.load(f)

REQUIRED_TAGS = ["【名称】", "【释义】", "【判定】", "【理由】"]
VALID_VERDICTS = ["放心删", "看看再删", "千万别删"]

clean = []
rejected = []

for item in data:
    output = item["output"]

    # 检查 1：必须包含所有标签
    if not all(tag in output for tag in REQUIRED_TAGS):
        rejected.append({"reason": "缺少标签", "item": item})
        continue

    # 检查 2：判定必须是三选一
    if not any(v in output for v in VALID_VERDICTS):
        rejected.append({"reason": "判定无效", "item": item})
        continue

    # 检查 3：输出不能太长（防止模型啰嗦）
    if len(output) > 200:
        rejected.append({"reason": "输出过长", "item": item})
        continue

    clean.append(item)

print(f"原始 {len(data)} 条 → 清洗后 {len(clean)} 条 → 淘汰 {len(rejected)} 条")

# 保存
with open("data/training_data_clean.json", "w", encoding="utf-8") as f:
    json.dump(clean, f, ensure_ascii=False, indent=2)

with open("data/rejected.json", "w", encoding="utf-8") as f:
    json.dump(rejected, f, ensure_ascii=False, indent=2)

# 抽检 20 条，人工看看质量
print("\n=== 随机抽检 20 条 ===\n")
for item in random.sample(clean, min(20, len(clean))):
    print(f"输入：{item['instruction'][:60]}...")
    print(f"输出：{item['output']}")
    print("-" * 60)
```

**重要：跑完抽检后人工看一遍，特别关注"千万别删"和"放心删"的判定是否准确。一条错误的"放心删"可能让用户删掉系统文件。**

### 2.6 训练数据格式示例

最终的 `training_data_clean.json` 每条长这样：

```json
{
  "instruction": "文件：msedge.dll\n路径：C:\\Windows\\System32\\Microsoft-Edge-WebView\\msedge.dll\n大小：293.1 MB",
  "output": "【名称】Edge浏览器引擎\n【释义】微软Edge和WebView的核心组件\n【判定】千万别删\n【理由】删除会导致浏览器和部分应用崩溃"
}
```

```json
{
  "instruction": "文件：rootfs.vhdx\n路径：C:\\Users\\user\\AppData\\Local\\Packages\\CanonicalGroupLimited...\\LocalState\\rootfs.vhdx\n大小：9.8 GB",
  "output": "【名称】WSL Linux虚拟磁盘\n【释义】Linux子系统的文件系统镜像\n【判定】看看再删\n【理由】不用Linux子系统可删，用则必留"
}
```

```json
{
  "instruction": "文件：CacheStorage\n路径：C:\\Users\\user\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\CacheStorage\n大小：1.2 GB",
  "output": "【名称】Chrome浏览器缓存\n【释义】网页缓存，加速重复访问\n【判定】放心删\n【理由】删除后浏览器会自动重建"
}
```

---

## 三、微调训练

### 3.1 环境准备

```bash
# 创建虚拟环境
conda create -n finetune python=3.11 -y
conda activate finetune

# 安装 Unsloth（Qwen 官方推荐，训练速度 2x，显存省 80%）
pip install unsloth
pip install trl datasets
```

硬件要求：
- **最低**：8GB 显存 GPU（如 RTX 3060/4060）+ LoRA 微调
- **推荐**：16GB 显存 GPU（如 RTX 4080）
- **无 GPU**：可用 CPU 训练，但非常慢（不推荐）

### 3.2 微调脚本

```python
# scripts/05_finetune.py
"""
用 Unsloth + LoRA 微调 Qwen3.5-0.8B-Instruct。
Unsloth 是 Qwen 官方推荐的训练框架，显存占用低，训练速度快。
"""
from unsloth import FastLanguageModel
from datasets import load_dataset
from trl import SFTTrainer, SFTConfig

# ===== 配置 =====
MODEL_NAME = "Qwen/Qwen3.5-0.8B-Instruct"
DATA_FILE = "data/training_data_clean.json"
OUTPUT_DIR = "./checkpoints/qwen-file-expert"
FINAL_DIR = "./models/qwen-file-expert-lora"

# ===== 加载模型（Unsloth 自动优化） =====
print("加载模型...")
model, tokenizer = FastLanguageModel.from_pretrained(
    MODEL_NAME,
    max_seq_length=512,      # 我们的输出很短，512 足够
    load_in_4bit=True,       # 4bit 量化加载，大幅省显存
)

# ===== LoRA 配置 =====
model = FastLanguageModel.get_peft_model(
    model,
    r=16,                    # LoRA 秩，越大越强但越费显存
    lora_alpha=32,           # 缩放因子
    target_modules=[         # 要注入 LoRA 的模块
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    lora_dropout=0.05,
)
model.print_trainable_parameters()
# 预期输出：trainable params: ~2M || all params: ~800M || trainable%: ~0.25%

# ===== 加载数据 =====
dataset = load_dataset("json", data_files=DATA_FILE, split="train")
print(f"训练数据：{len(dataset)} 条")

# 用 tokenizer 原生模板转换格式（比手写 ChatML 更健壮）
def format_sample(example):
    """将 instruction/output 对转换为 Qwen 的对话格式。"""
    messages = [
        {"role": "user", "content": example["instruction"]},
        {"role": "assistant", "content": example["output"]},
    ]
    return {"text": tokenizer.apply_chat_template(messages, tokenize=False)}

dataset = dataset.map(format_sample)

# ===== 训练 =====
trainer = SFTTrainer(
    model=model,
    train_dataset=dataset,
    args=SFTConfig(
        output_dir=OUTPUT_DIR,
        num_train_epochs=3,              # 3 轮通常足够
        per_device_train_batch_size=4,   # 根据显存调整
        gradient_accumulation_steps=4,   # 等效 batch_size = 16
        learning_rate=2e-4,              # LoRA 标准学习率
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        logging_steps=50,
        save_steps=500,
        save_total_limit=3,
        fp16=True,                       # 混合精度，省显存
        report_to="none",
        dataset_text_field="text",
        max_seq_length=512,
    ),
)

print("开始训练...")
trainer.train()

# 保存最终模型
trainer.save_model(FINAL_DIR)
tokenizer.save_pretrained(FINAL_DIR)
print(f"训练完成，模型保存至 {FINAL_DIR}")
```

运行：
```bash
python scripts/05_finetune.py
```

预计耗时（Unsloth 加速后）：
- 4000 条数据，RTX 4060：约 15-30 分钟
- 4000 条数据，RTX 3060：约 30-60 分钟

### 3.3 验证微调效果

```python
# scripts/06_test_model.py
"""
测试微调后的模型效果。
"""
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

MODEL_NAME = "Qwen/Qwen3.5-0.8B-Instruct"
LORA_DIR = "./models/qwen-file-expert-lora"

# 加载
tokenizer = AutoTokenizer.from_pretrained(LORA_DIR, trust_remote_code=True)
base_model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME, torch_dtype="auto", device_map="auto", trust_remote_code=True
)
model = PeftModel.from_pretrained(base_model, LORA_DIR)
model.eval()

# 测试用例
test_cases = [
    "文件：pagefile.sys\n路径：C:\\pagefile.sys\n大小：8.0 GB",
    "文件：node_modules\n路径：C:\\Users\\user\\project\\node_modules\n大小：1.2 GB",
    "文件：ext4.vhdx\n路径：C:\\Users\\user\\AppData\\Local\\Packages\\...\\ext4.vhdx\n大小：5.9 GB",
    "文件：cache.db\n路径：C:\\Users\\user\\AppData\\Local\\Temp\\cache.db\n大小：500 MB",
]

for test in test_cases:
    messages = [{"role": "user", "content": test}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    outputs = model.generate(**inputs, max_new_tokens=150, temperature=0.3, do_sample=True)
    result = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

    print(f"输入：{test[:50]}...")
    print(f"输出：{result}")
    print("-" * 60)
```

**检查要点：**
- 输出格式是否严格遵循四行结构？
- 判定是否准确？（pagefile.sys 应该是"千万别删"，cache.db 应该是"放心删"）
- 有没有幻觉或编造信息？

### 3.4 量化评估（必做）

仅靠人工抽检不够。必须用留出的测试集计算关键指标：

```python
# scripts/06b_evaluate.py
"""
在测试集上量化评估模型效果。
重点关注"千万别删"的召回率 — 漏判系统文件后果最严重。
"""
import json
import re

# 从清洗后的数据中留出 15% 作为测试集（训练前就要切分！）
# 假设已在 Step 4 中切分好 data/test_set.json

VALID_VERDICTS = ["放心删", "看看再删", "千万别删"]

def extract_verdict(output: str) -> str | None:
    """从模型输出中提取判定。"""
    match = re.search(r"【判定】(放心删|看看再删|千万别删)", output)
    return match.group(1) if match else None

def evaluate(test_data, predict_fn):
    total = len(test_data)
    format_ok = 0          # 格式合规数
    verdict_correct = 0    # 判定正确数

    # 按判定类型统计
    stats = {v: {"tp": 0, "fp": 0, "fn": 0} for v in VALID_VERDICTS}

    for item in test_data:
        expected_verdict = extract_verdict(item["output"])
        pred_output = predict_fn(item["instruction"])
        pred_verdict = extract_verdict(pred_output)

        # 格式检查
        required_tags = ["【名称】", "【释义】", "【判定】", "【理由】"]
        if all(tag in pred_output for tag in required_tags):
            format_ok += 1

        # 判定准确性
        if pred_verdict and expected_verdict:
            if pred_verdict == expected_verdict:
                verdict_correct += 1
                stats[expected_verdict]["tp"] += 1
            else:
                stats[expected_verdict]["fn"] += 1
                stats[pred_verdict]["fp"] += 1

    print(f"格式合规率：{format_ok}/{total} = {format_ok/total:.1%}")
    print(f"判定准确率：{verdict_correct}/{total} = {verdict_correct/total:.1%}")
    print()

    # 重点：千万别删的召回率
    for v in VALID_VERDICTS:
        tp = stats[v]["tp"]
        fn = stats[v]["fn"]
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        marker = " ← 此项必须 ≥ 95%" if v == "千万别删" else ""
        print(f"  [{v}] 召回率：{recall:.1%}{marker}")

# 使用方法：
# with open("data/test_set.json") as f:
#     test_data = json.load(f)
# evaluate(test_data, predict_fn=your_model_predict)
```

**硬性指标：**

| 指标 | 及格线 | 说明 |
|------|--------|------|
| 格式合规率 | ≥ 95% | 四行结构完整 |
| 判定准确率 | ≥ 85% | 整体准确 |
| "千万别删"召回率 | ≥ 95% | **最关键** — 漏判系统文件 = 用户删崩系统 |
| "放心删"精确率 | ≥ 90% | 误判为"放心删"的后果也很严重 |

> 如果"千万别删"召回率 < 95%，不要部署，先排查训练数据中该类别是否不足。

---

## 四、导出为 Ollama 模型

### 4.1 合并 LoRA 权重

```python
# scripts/07_merge_and_export.py
"""
将 LoRA 权重合并回基础模型，生成完整的模型文件。
"""
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

MODEL_NAME = "Qwen/Qwen3.5-0.8B-Instruct"
LORA_DIR = "./models/qwen-file-expert-lora"
MERGED_DIR = "./models/qwen-file-expert-merged"

print("加载基础模型...")
base_model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME, torch_dtype="auto", trust_remote_code=True
)

print("加载 LoRA 权重...")
model = PeftModel.from_pretrained(base_model, LORA_DIR)

print("合并权重...")
merged = model.merge_and_unload()

print(f"保存到 {MERGED_DIR}...")
merged.save_pretrained(MERGED_DIR)
AutoTokenizer.from_pretrained(LORA_DIR).save_pretrained(MERGED_DIR)

print("完成！")
```

### 4.2 转换为 GGUF 格式

```bash
# 安装转换工具
pip install llama-cpp-python

# 克隆 llama.cpp 的转换脚本
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp

# 转换（Q4_K_M 量化，体积小，质量够用）
python convert_hf_to_gguf.py ../models/qwen-file-expert-merged \
    --outfile ../models/file-expert-q4km.gguf \
    --outtype q4_k_m
```

### 4.3 注册到 Ollama

```bash
# 创建 Modelfile
cat > Modelfile <<'EOF'
FROM ./models/file-expert-q4km.gguf

PARAMETER temperature 0.3
PARAMETER num_ctx 512
PARAMETER stop "<|im_end|>"

SYSTEM "你是Windows文件解释助手。根据用户提供的文件信息，用中文严格按以下格式回答：
【名称】专业短名
【释义】一句话解释（不超过20字）
【判定】放心删 / 看看再删 / 千万别删
【理由】一句话（不超过15字）"
EOF

# 创建 Ollama 模型
ollama create file-expert -f Modelfile

# 测试
ollama run file-expert "文件：pagefile.sys
路径：C:\pagefile.sys
大小：8.0 GB"
```

---

## 五、集成到 C盘守护者

### 5.1 用户设置界面

在设置面板中增加"模型来源"选项：

```
[x] 本地 Ollama（推荐，离线可用）
    模型：file-expert
    地址：http://localhost:11434/v1

[ ] 云端 API
    Base URL：https://openrouter.ai/api/v1
    API Key：sk-...
    模型：anthropic/claude-haiku
```

### 5.2 自动检测 Ollama

应用启动时检测本地 Ollama 是否运行：

```typescript
async function detectOllama(): Promise<boolean> {
  try {
    const resp = await fetch('http://localhost:11434/api/tags');
    return resp.ok;
  } catch {
    return false;
  }
}
```

如果检测到 Ollama，自动切换为本地模型，免配置。

### 5.3 降级策略

```
推理请求
  │
  ├── 本地 Ollama 可用？ → 用本地模型
  │
  ├── 云端 API Key 已配置？ → 用云端 API
  │
  └── 都不可用 → 仅展示 rules.json 规则匹配结果（无 AI 解释）
```

---

## 六、完整流程总结

```
第一阶段：数据准备（半天）
  01. 扫描 C 盘采集种子路径        → seed_paths.json
  02. 去重采样                     → sampled_paths.json (6000条)
  03. GPT-5.4 批量标注（蒸馏）     → training_data_raw.json
  04. 清洗验证 + 切分测试集        → training_data_clean.json + test_set.json

第二阶段：模型训练（1-2小时）
  05. Unsloth + LoRA 微调          → qwen-file-expert-lora/
  06. 量化评估（测试集指标）       → 确认"千万别删"召回率 ≥ 95%

第三阶段：部署（30分钟）
  07. 合并权重 + 转 GGUF           → file-expert-q4km.gguf
  08. 注册到 Ollama                → ollama create file-expert
  09. 集成到 C盘守护者设置         → 自动检测本地模型
```

---

## 七、注意事项

### 7.1 安全红线

- **绝不让模型单独决定"放心删"**：对于 rules.json 中标记为红色（系统核心）的文件，无论模型输出什么，前端强制显示"千万别删"
- **兜底策略**：模型输出不包含有效判定时，默认显示"看看再删"
- **免责提示**：始终显示"AI建议仅供参考，本工具不执行任何删除操作"

### 7.2 持续优化

- 收集用户反馈（哪些文件解释不准确）
- 定期用新数据增量微调（知识内化，不用 RAG）
- 重点补充训练数据中覆盖不足的路径模式

### 7.3 模型升级路径

如果 0.8B 效果不够好：
1. 先尝试扩充训练数据到 10,000 条
2. 再尝试升级到 Qwen3.5-2B（内存 +0.8GB）
3. 最后考虑 Qwen3.5-4B（内存 +2GB）
