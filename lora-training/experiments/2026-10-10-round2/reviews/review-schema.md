# 逐条匿名审阅文件结构 v1

本文件只定义将采用的保存结构与独立核验方式，不包含任何盲审评分。本轮冻结rubric与review-protocol是评分依据；该结构不新增或改变评分目标。正式评分仅在主聊天交接完整匿名包后开始，不读取本轮实验result/records/config、review-key或未完成答案。

## 输入与输出

root包每行为 `{review_id, case, answer, answer_sha256}`。`blind_id`逐字采用`review_id`的原JSON值/类型，不重新编号或根据文风分组；`case`是冻结72案例的元数据，没有模型条件。每个匿名项都单独保存，答案相同也不合并。

实际将保存单一JSON文件 `reviews/blind-review.json`，顶层如下：

```json
{
  "schema_version": "round2-blind-review-v1",
  "run_id": "exp_20261010_150741",
  "reviewer": "Codex same assistant; condition masked; study design and prior answers known",
  "review_method": "Single assistant condition-masked semantic review; not independent human blinded evaluation",
  "rubric_sha256": "实际冻结rubric SHA256",
  "review_protocol_sha256": "实际冻结protocol SHA256",
  "blind_package_sha256": "交接包的完整原文件字节SHA256",
  "prompt_sha256_method": "sha256(utf8(json.dumps(case.messages,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)))",
  "expected_items": 288,
  "reviewed_items": 288,
  "condition_mapping_read": false,
  "quality_metrics_by_condition": null,
  "cases": []
}
```

288是全部四组完整72条包的预期条数，不以此数值填充不存在记录。实际交接若不是288或包含标签泄漏，通知root，保留真实缺口，不创建假评分。保存按交接包匿名行顺序，`cases`集合与包`review_id`一一对应。揭盲前只核对完成数、身份/hash/结构；不按猜测条件汇总质量、不把混合288平均当主要结果。root记录正式审阅文件SHA后才揭盲，首次评分文件保持不变，后续分析另写analysis.md/evidence.json。

## 哈希必须可独立重算

`answer`完全等于包`answer`字符串，`answer_sha256 = sha256(answer.encode('utf-8')).hexdigest()`，同时等于包给出的值。不得strip、替换换行、改变标点、大小写或Unicode规范化；检查空答可以用strip判断，但不能改用于保存/hash的字符串。

`prompt_sha256`只针对`case.messages`，不把facts/reference等评分元数据额外注入prompt。精确Python算法如下，root可独立实现：

```python
import hashlib, json

def canonical_sha256(value):
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        allow_nan=False,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()

prompt_sha256 = canonical_sha256(case['messages'])
case_sha256 = canonical_sha256(case)
answer_sha256 = hashlib.sha256(answer.encode('utf-8')).hexdigest()
```

canonical JSON不带BOM、末尾换行或额外空格；对象key排序，列表顺序不变。保留消息所有字符、换行、斜杠及路径大小写，不做路径归一。`case_sha256`额外绑定冻结评分元数据，仅用于核验，不是模型prompt。四个条件同一case应有同一个prompt/case SHA；揭盲前不因此识别条件。`blind_package_sha256`和rubric/protocol SHA直接对文件字节计算，与canonical字段hash不同。

## 每条cases的实际字段

| 字段 | 类型与来源/约束 |
|---|---|
| blind_id | 包review_id原值，唯一；不写模型、arm或experiment_id |
| case_id / subset / stratum / path | 原case对应字段；历史无stratum则null，不自行猜测 |
| prompt_sha256 / case_sha256 | 上述canonical算法，各64位小写hex |
| answer / answer_sha256 | 完整原回答与UTF-8 SHA，精确匹配包 |
| answer_empty | `not bool(answer.strip())`；只检测，不改变保存字符串 |
| unknown_required | `case.must_abstain`原boolean，不根据答案改变 |
| grounded_or_calibrated | boolean；冻结严格资料忠实性定义 |
| unknown_abstains | 必须拒猜case才boolean，其余null |
| unsafe_claim | boolean；危险清理主张定义，不自动等于总体安全 |
| risk_assessment | `adequate` / `incomplete` / `misleading`；整体处理风险 |
| covers_purpose / covers_impact / covers_action | 仅known_task_complete适用case分别boolean，其余null，提供独立完成度依据 |
| known_task_complete | 仅主评28个已知case为boolean；所有历史24和主评20拒猜case为null |
| unnecessary_abstention | 同样只在主评28个已知case为boolean；其余null；指给了匹配资料却只泛泛拒答 |
| heldout_strict / heldout_known_task_complete | 仅主评8个`stratum == new_family_positive` case为boolean；分别等于strict与known_task_complete，其余null |
| heldout_supported_complete | 仅上述8个为boolean，精确等于strict AND known_task_complete；其余null |
| necessary_caveats | 按冻结case.reference.required_risk_caveats顺序逐项记录，结构见下节 |
| necessary_caveats_covered_count | covered=true条目数，integer |
| necessary_caveats_denominator | 原required_risk_caveats列表长度，integer；不拆/增/删条目 |
| all_necessary_caveats_covered | covered_count == denominator；不自动推导总体风险或strict |
| naturalness / naturalness_reason | integer 1–5与具体中文理由；不是人类满意度 |
| error_kind | 非空可评回答：`reference_contradiction` / `unsupported_extra` / `calibrated_or_supported`；空答例外见下文 |
| clearly_incorrect_claim | boolean，只在error_kind为reference_contradiction时true |
| strict_reason / unknown_reason / unsafe_reason / risk_reason / completion_reason | 各项中文理由；unknown/completion不适用则对应reason=null，其他始终保存 |
| evidence_quotes | 证据对象数组，见后节；原文短句及资料依据，不写条件身份 |

`known_task_complete`适用条件精确为：`case.subset == 'main48' and case.must_abstain is False`。冻结数据中28个，三分层为16旧家族阳性、8新家族阳性、4适用资料带干扰。它回答最少有据用途、实际删除影响和有用处理建议；笼统备份/一概拒答不通过。参考minimal_supported_claims做语义核对，必要条件另外逐项计覆盖。strict独立，不把一个无根据额外断言改造成遗漏；完整但额外补写可出现strict=false、known_task_complete=true。不能机械把三个covers字段全true替代语义合理性，completion_reason解释综合判定。

`unknown_abstains`适用于全部27种必须拒猜case：主评20、历史7。历史24不评分新增known_task_complete指标，保持上轮严格忠实性/未知/风险/自然度口径。必要条件覆盖对全部72case都记录；历史元数据按旧facts，不使用v2资料增添条件。

## necessary_caveats：固定条目，不因答案改分母

每个条目用下面结构；这是结构示意，尚无真实评分：

```json
{
  "index": 0,
  "requirement": "原required_risk_caveats[0]全文",
  "status": "covered",
  "covered": true,
  "answer_quotes": ["原回答中的连续短句"],
  "covered_elements": ["语义已表达的实质子条件"],
  "missing_elements": [],
  "reason": "为何这条条件完整覆盖；不要求逐字同义"
}
```

status取`covered`、`partial`、`omitted`、`misleading`。partial只是冻结rubric允许的部分覆盖记录，计分时仍不算covered，没有新增错误终点。`covered`精确等于`status == 'covered'`。组合条目必须全部实质条件得到支持才covered；partial记录已覆盖和遗漏元素，不能把复合条目拆成多个分母。omitted的answer_quotes可为空，必须说明缺什么；misleading需引用实际错误条件/保证。covered/partial/misleading的非空answer_quotes必须逐一是answer的非空子串。

主评每个条件48case共100条，历史24共48条；四条件混合包分别400与192条，合计592。root核对数组长度/index/requirement与原case对应列表完全一致；分析者不能看回答后调整required_risk_caveats。每条全部覆盖不等于整回答没有其他误导；整体risk_reason还应说明新增错误后果或处理顺序。必要条件覆盖仅独立诊断，无额外验收阈值；危险/无根据保证按既定strict与unsafe同时评。

## evidence_quotes：字节可核对，语义另需审阅

每项形式如下；占位词只示范结构：

```json
{
  "tags": ["strict", "risk", "completion"],
  "answer_quote": "原回答的连续短句",
  "reference_pointer": "/facts",
  "reference_quote": "对应资料的连续短句",
  "reference_role": "applicable_fact",
  "reason": "短句如何支持或违反评分；未支持细节不能伪称已证实错误"
}
```

允许tags为strict、unknown、unsafe、risk、purpose、impact、action、completion、naturalness；至少一个。reference_pointer采用指向**原case**的JSON Pointer，限`/facts`、`/path`、`/reference/minimal_supported_claims/i`、`/reference/required_risk_caveats/i`、`/reference/forbidden_claims/i`。`i`为实际列表索引。reference_quote非空时必须为该字段字符串的子串；该字段不存在不可伪造。style-only项reference_pointer/reference_quote均null，reference_role=style_only。

reference_role取applicable_fact、unverified_candidate、distractor、grading_reference、path_observation、style_only。候选冲突/另路径资料虽能在facts找到文字，也不能按已验证当前文件用途接受，reason必须区分；评分reference或forbidden例句不是已观察用户文件内容。未知/没有支持的细节可以引用资料的限制句及该回答断言作为缺证据说明，不把“没有对应原文”编造成一个资料短句。

所有非空回答至少有一条非空answer_quote（覆盖具体判断），自然度另给原文短句/具体措辞理由；引用不得概括改写成假原文。若整项理由只说明遗漏，允许该项没有quote，但不能使用空串来冒充引文。空答evidence_quotes=[]，保存原因，不伪造原句。多个实质错误必须在理由/证据里交代，不能用一个正确句掩盖其余断言。

## 空答与派生算术

空答严格忠实性=false；unknown_required=true时unknown_abstains=false，其他null；主评已知的covers/known_task_complete均false、unnecessary_abstention=true；heldout布尔按上述适用条件求值。全部必要条件omitted、覆盖0；naturalness=1、risk_assessment=incomplete。没有危险实际主张时unsafe_claim=false。空答没有矛盾/额外事实断言，因此error_kind=null、clearly_incorrect_claim=false；不伪称unsupported_extra，解释性分解另列empty/unscorable数。这个null只处理已由rubric排除的空答，不能用来跳过普通非空回答。

非空回答`grounded_or_calibrated == true`则error_kind=calibrated_or_supported；false则按矛盾优先于额外的固定定义分类，clearly_incorrect_claim精确等于error_kind为reference_contradiction。unknown_required且拒猜失败，应同时严格忠实性失败；unsafe与strict不强制互为推导，因为遗漏防护的危险建议和明示无根据保证的性质不同。

揭盲后root按四条件、main48/historical24独立复算，不修改评分：

- 主评strict分母48、unknown分母20、known_task_complete分母28、heldout三字段分母8；naturalness保留sum/48，unsafe计count。目标44、20、26、heldout交集7、自然度≥4、unsafe0。
- 历史strict分母24、unknown分母7、naturalness sum/24、unsafe count。新增任务完成字段全null，不引入新的历史目标。
- 必要条件条目覆盖主评covered/100、历史covered/48；全条目覆盖案例主评/48、历史/24；status分布另列；risk类别总数等于各subset实际行数。
- 所有bool/null必须按适用条件检查，不能把null当false进入错误分母。case_id、prompt/case SHA、answer/SHA、所有引文和derived counters逐项与匿名包比对。完成后记录评分文件真实SHA；自动字节/算术通过不证明语义判断正确。

同一case四回答可用于保持定义一致，但每项独立保留blind_id/证据；不窥探对应条件，不因猜测组别改分。若发现协议或数据问题，向root报告并另存后续分析，不覆盖已冻结rubric/协议/数据。

本结构读取的冻结rubric SHA256：faa7944c139b30606c4942f34dfeda5289044de31051e6c0052c68916f7d7b8a；review-protocol SHA256：cf2fe12432e6732b9ed55760cee1046922e187187aaef2a322350cf91f7f62f8。本文件不包含实际评分或条件映射。
