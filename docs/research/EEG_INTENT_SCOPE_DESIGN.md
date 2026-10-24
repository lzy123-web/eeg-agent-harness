# EEG 目标—数据阶段关系编译器设计

日期：2026-10-24（Asia/Shanghai）

## 1. 问题边界

Issue #17 的 H14 不是普通同义词漏识别。用户同时要求“重参考前质量”和“重参考后功率”，而冻结 Transfer CIEDG 在存在 `epoch_rereference` 时把 quality、summary、bandpower 全部绑定到统一 `effective_epochs`。旧 `IntentSpec.source_stage` 只有全局值，无法表达每个目标读取哪个 Epoch 版本，v1 又用有限 regex 提前检查，最终把两个谱系静默合并。

本轮只编译并验证关系，不扩展 CIEDG 双分支执行、不新增状态转换、不修改 EEG 数值工具。

## 2. 文献启发与适用边界

- Allen 的 interval algebra 将相对时序作为关系约束而非绝对时间值，并用约束传播检查一致性。这里借用“显式关系图 + 一致性”，不实现完整 13 关系代数：https://doi.org/10.1145/182.358434
- 事件时序抽取研究指出逐对关系会产生全局不一致或循环，需在事件图层检查全局一致性：https://aclanthology.org/2023.matching-1.3/
- W3C PROV-O 区分 Activity 使用的 Entity 与生成/派生的新 Entity，为 source Epoch、转换活动和 derived Epoch 的分离提供标准语义：https://www.w3.org/TR/prov-o/
- SWIRL 说明科学工作流可先进入独立 IR，再由编译器处理数据移动和执行，而不是把自然语言直接当可执行计划：https://arxiv.org/abs/2407.01838
- type-and-effect/data-flow 研究说明状态效果可以作为静态证书检查，而不必只依赖运行时成功：https://doi.org/10.4230/LIPIcs.FSCD.2020.15

这些工作支持表示选择，但没有直接提出本项目的 EEG scope graph；因此不能据此宣称新颖性。

## 3. 候选机制

### A. 每目标单一 `input_stage` 槽

在 IntentSpec 给每个 objective 添加 `source/effective`。优点是最小；缺点是无法表达 before/after、同状态、多转换冲突和环，也难解释同一 `effective` 到底由筛选还是重参考产生。未选择。

### B. 第二个自由 NLI/Judge

让另一个模型判断“是否支持”。它可以处理语言变体，但把筛除或重参考安全性转交给概率判断，且无法证明下游 Planner 能实现所判关系。未选择为最终 gate。

### C. 证据约束 Typed Goal–State Relation Graph（TGSRG，选择）

语言模型只提出候选图；每个 node/relation 必须引用用户原文精确片段。静态编译器完成：

1. **目标完备性**：图节点必须与已验证 Intent objectives 一一对应，不能漏掉 quality、power 或 transform。
2. **状态类型**：consumer 读取 `source_epochs` 或某 transition 生成的 `effective_epochs`；transition 显式声明 source→derived effect。
3. **关系闭包**：`before/after/same_input_state` 转成有向约束，检查自环、循环、缺边和冲突。
4. **能力投影**：把图与冻结 CIEDG contract 比较，而不是让 LLM决定“可执行”。
5. **授权隔离**：TGSRG 不产生筛选/重参考授权；授权仍由 v1 exact evidence + scoped safety gate 决定。
6. **Fail closed**：当前 Planner 只能表达一个 effective branch；source consumer 与 post-transform consumer 并存时澄清 `analysis_stage`，不自动移动目标。

## 4. 当前能力证书

| 目标组合 | 冻结运行时可表达的数据阶段 |
|---|---|
| 无 transition | 所有 consumer 共用 source/current Epoch |
| quality → authorized selection → summary/power | quality 读取 source；summary/power 读取 selected effective Epoch |
| authorized rereference → quality/summary/power | transform 读取 source；其余 consumer 读取 rereferenced effective Epoch |
| selection + rereference | 未验证组合，拒绝执行 |
| source consumer + rereferenced consumer | 需要双分支，当前不支持，澄清 |
| 同一 consumer 同时要求 pre/post 比较 | 需要双分支，当前不支持，澄清 |

该表由代码 contract 生成/维护，不由模型自由决定。

## 5. 解析—验证边界

- Scope extractor 是软语义候选：输出 goal、input_state、transform effect、关系和 exact evidence。
- 编译器不要求固定英语词形命中；它只检查引用确实来自原文、图结构完整且无矛盾。
- 高风险动作最终仍须 v1 的独立授权证据，并须存在当前 contract 的静态实现路径。
- 含 transition 的请求若 scope graph 缺目标、缺状态、缺关系、引用非原文或无法投影到 contract，一律澄清；无 transition 的合法简单任务不增加第二次 scope 调用。

这不能数学保证 LLM 不会把一个精确引用标错关系，但比 regex 提供了可审计的错误位置，并使 Planner 能力成为独立静态门槛。真实模型对抗测试必须单独报告此残余风险。

## 6. 科学不变量

- H14 必须在任何 EEG 工具调用前停止。
- 不把 pre-transform quality 改写成 post-transform quality。
- 不从 TGSRG 推导用户授权，也不猜参考通道、事件标签或时间窗。
- 不允许有环关系、同一目标多输入状态或未注册状态。
- 不允许 selection 与 rereference 在当前任务中组合。
- 合法明确 post-rereference 单阶段任务继续进入原 Transfer CIEDG；执行数学与 evidence release 不变。
- v0、v1、Issue #17 manifest、raw outputs 和分数保持不可变。

## 7. 冻结协议

- 新独立对抗集 20 例：development 8、holdout 12；旧 H14 只作开发回归，不计入新成绩。
- manifest SHA-256：`e6d47bd3c38eaf0efa26e8b7e8bcab32bf535b5faf5d774ffae2db80b1c1d250`。
- 只有一名审校者，没有第二人盲审，明确不报告标注一致性。

## 8. 已知风险

- Scope 候选仍来自 LLM；exact span 证明来源而非证明语义标签必然正确。
- 当前只支持两个已存在的 transition family，不代表通用 EEG 时序逻辑。
- 单人 gold 无法提供标注一致性证据。
- TGSRG 是 opt-in safety candidate，未通过未见 dangerous-accept 门槛前不得成为默认实现。

## 9. 开发迭代

### v2.0-a：直接边能力证书

初版要求 scope graph 显式包含 runtime contract 的每一条直接先后边。例如
`rereference → quality` 与 `rereference → power` 必须同时出现。确定性合法链测试发现，模型若忠实表达
`rereference → quality → power`，图已经保证 transform 先于 power，但初版仍会误拒。

### v2.0-b：传递可达能力证书（当前实现）

能力投影改为检查有向无环图上的可达性，而不是固定直接边；循环检查仍独立执行。这是图验证算法修改，
不是 Prompt 或关键词补丁。它降低合法链式关系的结构性误拒，同时不放宽状态类型、目标完备性、授权隔离和
单 effective branch 边界。H14 仍因 `epoch_quality=source_epochs` 与现有 runtime 要求的
`effective_epochs` 冲突而在工具执行前澄清。
