# EEG 科学目标完备性研究决策

日期：2026-10-24（Asia/Shanghai）

## 1. 决策摘要

**结论：CONDITIONAL GO，仅允许进入一个预注册、有限域的研究 Pilot；目前不是已成立的第二创新点，不开发 v3。**

理由：Issue #17/#19 的 SH01/Pro 是真实危险遗漏，现有 Intent compiler、TGSRG、CIEDG 与 Answer Gate 均无法从一个已经截断
的目标集合中恢复缺失目标。文献也表明 grammar、planner、workflow IR 和 provenance 主要验证已形式化对象，不能自动证明
NL→specification 没有遗漏。问题真实、边界清楚且有 EEG-specific 风险，但自由语言完备性不可形式保证，首选 source ledger
仍依赖另一个可能相关出错的语义 extractor。

因此本轮冻结在“问题建模 + 候选设计 + 实验门槛”。没有代码、Prompt、协议结果或 LLM 实验被修改。

## 2. 为什么不是直接 GO

### 2.1 真实问题不等于独立创新已经成立

SH01 证明了危险误接受：模型遗漏重参考与功率，而 Harness 合法执行质量子任务。但这只能证明研究问题存在，不能证明新增的
source extractor 比第二 LLM judge、用户确认式受控语言或强专家 schema 更可靠。

### 2.2 “独立 verifier”仍可能同源共错

若 SourceClaimLedger 与 Intent 使用同一模型、相近 Prompt 和相同 ontology，两者会共同遗漏。把两次相同判断包装成 certificate
不会产生科学保证。未来必须分开测量 source recall、candidate recall 与 joint miss，并披露实际模型标识。

### 2.3 EEG 特点提供约束，不提供语义 oracle

EEG 的 reference、Epoch selection、event window、lineage 与授权能定义哪些遗漏风险高，也能让 matcher 确定性检查；但 ontology
本身不能判断自由原文是否明确要求了某个目标。将领域词表扩充称为新方法是不充分的。

## 3. 与已有两层方法的边界

| 层 | 输入 | 核心问题 | 本轮是否修改 |
|---|---|---|---|
| ESOCC 候选（上游） | 用户原文 + 候选 Intent | 明示 source claims 是否全部进入候选 | 未实现，仅设计 |
| TGSRG | 已提交目标与关系 | 多目标的数据阶段/作用域是否合法、当前能力是否支持 | 冻结 |
| CIEDG | 合法目标 + EEG 执行状态 | 证据依赖、状态转换、失效与最小恢复 | 冻结 |
| Answer Gate | 执行证据 + 最终回答 | 回答是否忠实于实际证据 | 冻结 |

潜在独立研究对象是“有限 EEG ontology 下的 source-to-contract coverage 与风险选择性拒绝”，不是另一个 Planner，也不是给
CIEDG/TGSRG 增加 Prompt。若未来结果只说明双模型复核有效，则应归为必要工程修复，不应作为独立论文贡献。

## 4. 论文贡献判定标准

### 4.1 可能具有研究价值的机制

- 将用户原文中的 operation/object/stage/polarity/authorization/relation 建模为可追溯 source obligations；
- 候选外的二部覆盖证书，使“遗漏”成为显式、可归因的集合差；
- 针对 EEG lineage-changing operation 与 downstream dependence 的风险选择性澄清；
- 在相同规则、预算与 catalogue 下，证明 typed coverage 相对强 judge/受控语言基线的增量价值。

### 4.2 仅属于工程完善的内容

- 再调用一次相同 LLM 问“是否完整”；
- 扩充 PSD、amplitude、rereference 等关键词；
- 只增加 JSON schema、枚举或 Prompt 示例；
- 根据旧 SH01/H14 调规则并把回归成绩当 unseen 结果；
- 自动把检测到的 missing claim 写入 Intent 并直接执行。

## 5. 条件性 Pilot 的启动条件

只有同时满足下列条件才建议新开实现 Issue：

1. source claim schema 与有限 EEG ontology 先冻结，覆盖当前已支持操作而非新增 EEG 功能；
2. 新协议由至少两名 EEG 背景标注者独立标注，旧失败只作开发回归；
3. source extractor 不读取候选 Intent、gold、场景 ID 或执行结果；
4. 强基线包括受控语言/用户确认与独立 LLM judge，规则、预算、模型信息透明；
5. 预注册危险接受、误拒、调用成本与停止规则，不根据 holdout 改 Prompt 或 scientific truth；
6. 不发送真实 EEG 波形或受试者信息，只测试语言合同。

若无法获得双人标注、稳定模型标识或足够新 holdout，则本课题转为 **NO-GO：仅作为 CCEP 的安全工程限制讨论**。

## 6. 硕士论文可行性

- **问题重要性：中到高。** 漏掉状态转换/禁止/下游输出可能改变 EEG 科学含义。
- **技术独立性：条件性。** 与 CIEDG/TGSRG 的验证对象不同，但与 instruction following、semantic parsing 和 double-check
  的边界很近。
- **工程可行性：中。** 可复用现有 Intent schema、TGSRG 与 Agent adapter，不需新模型训练或真实数据外发。
- **实验风险：高。** source extractor 可能与候选共漏；安全提升可能完全来自更高澄清率；样本和标注成本不可忽略。
- **创新性证据：当前不足。** 本轮文献核查未发现完全同构的 EEG coverage certificate，但不是系统综述或新颖性证明。

综合判断：保留为**候选独立研究问题**，用一次有界 Pilot 决定；在 Pilot 通过前，论文仍应以冻结 CIEDG 工作点一为主体，不能
宣布第二创新点成立。

## 7. 明确的停止条件

出现任一情况即停止方法扩张：

- 新 holdout 仍出现高风险 joint miss/dangerous accept；
- ESOCC 相对强 judge/受控语言无增量，或只靠显著更高误拒获得安全；
- 贡献无法从 Prompt engineering、schema validation 或双模型复核中分离；
- 为提高结果需要修改 scientific gold、弱化对照或使用旧失败调参；
- 研究周期挤压 CIEDG 正式复现与论文写作。

## 8. 本轮最终判断

本轮既不是强行 GO，也不是因为一次失败就放弃问题。最诚实的决策是：

> **CONDITIONAL GO for a bounded, preregistered pilot; NO-GO for claiming a second thesis contribution today.**

下一步精确入口是先做人工 source-claim 标注规范和盲标一致性试验，而不是写 v3、增加 Planner 或重新运行 DeepSeek。
