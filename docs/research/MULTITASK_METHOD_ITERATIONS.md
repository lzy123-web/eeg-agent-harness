# 工作点一多任务方法迭代记录（Issue #26）

## 初版：跨族目标进入同一图，但核心仍有事件默认假设

初版 `b5cc2f7` 将连续记录 `record_info/record_quality/amplitude/psd`、严格模型 `seizure_detection` 与事件目标写入一个 `MULTITASK_CONTRACTS`。它让无事件 PSD 和 Event→Epoch→质量→条件频带功率经过相同的 `run/_reconcile/_materialize_evidence`，并给 record/model 输入增加内容与资源绑定。本地合成测试、真实 EDF+本地权重的输出形状测试通过。修复的早期缺陷：未知目标原会在构图时触发 `KeyError`；模型文件变化但 loader 可能按路径缓存，现必须 fail closed；record-only 请求中附加事件参数原会被静默忽略，现整体拒绝。

但针对 [Issue #26 纠偏评论](https://github.com/lzy123-web/eeg-agent-harness/issues/26#issuecomment-6382639080) 审查发现，初版继承旧 `ContractGraphResidualPlanner`，后者以 `event_workflow` 与源/有效 Epoch 作为结构默认值。初版部分方法虽覆盖了这些假设，核心依然不清楚哪些状态是跨任务科学属性、哪些只是事件策略。故**不能将初版直接视为共同机制完成**。

## 修订：任务中性图核心 + 事件专有策略

`6b660dd` 增加 `v2_graph.py::SharedEvidenceGraphCore`：单一 frontier、目标依赖、绑定比对、证据失效、消费者内容等价复用、有限重试/修复、工具调用预算、结果发布。新版 `MultiTaskContractGraphPlanner` 只负责按 contract 把 record、record+model、source/effective Epoch 映射到各自输入对象；事件专有的 trial selection 授权、质量证据与 identity/derived 转变仅在事件策略方法中。旧 v1.1 文件与正式 gold/trace/results 未改，仍可运行。

此外，编译阶段把每个目标与**同一个 Registry 的 ToolSpec**核对：消费/产出 artifact 类型、Profile 适用性必须一致；执行后核对 declared return type，以及产出 artifact 的真实指纹。此检查跨记录、事件和模型目标生效，防止“工具返回 success 但数据类型/来源已错”进入答案证据。受控反例：把 PSD ToolSpec 改成消费 Epoch，预检 `GOAL_TOOL_CONTRACT_MISMATCH` 且零执行；把 `record_info` handler 改成返回 array，执行后 `TOOL_RESULT_TYPE_MISMATCH`，不发布结果。测试只使用合成输入，故障未改生产工具。

## 仍存在的机制/接口边界

1. 编译阶段仍借用现有 `StateAwareConstrainedPlanner` 的工具和事件适用性预检；这是任务策略，不是第二套执行器。未来若增加独立任务族，应新增契约与适配校验，而不复制 graph runtime。是否真的降低强动态 Expert 的维护成本**未做正式扩展实验**。
2. 自由语言意图解释沿用旧 EvidenceBoundIntentInterpreter，仍可能过度解析或漏目标。真实 DeepSeek 在合成事件请求中把“试次”错列为 `epoch_summary` 概念，证据 quote 不符合独立 grounding，安全澄清；这是**语言解析错误被 Harness 拒绝**，不是事件图失败，也不能算任务完成。没有为一次失败放松语义校验或调关键词。
3. 当前 event-specific 源/有效 Epoch 绑定仍为显式策略分支；它不影响无事件任务，不代表所有未来任务自动适配。完整 ERP/ERD/ERS、儿童 ASD 解释、跨数据集模型泛化均不在本轮实现。

## 可检验的新旧行为差异

| 场景 | 冻结 v1.1 | 初版 v2 | 修订 v2 |
|---|---|---|---|
| 无事件的 PSD / 质量+PSD | 旧 CIEDG 图不运行；单工具路径 | 同一图，但继承事件类 | 任务中性图，record 输入绑定，无 Epoch 默认数据状态 |
| 事件多步 | 旧事件图 | 共享旧事件图函数 | 同一新版图运行；Epoch 与筛选是策略分支 |
| 本地合法模型输入 | 单工具路径 | 图内 record+资源绑定 | 同一新版图，Profile/ToolSpec/资源和结果类型共同检查 |
| 工具 contract/输出不一致 | Executor 有参数/序列化检查 | 未建立图级类型门 | 图编译/证据发布前拒绝，旧结果不引用 |

这仍是研究原型，而非已证明的新论文贡献；WINGS 类语义工作流与 PROV-O 来源/失效思想已存在，独立价值需与公平强动态 Expert 比较。

## Issue #28 v3：目标实例机制的实际迭代（原 v2 记录不改）

1. **首版实现与通过项。** `v3.py` 将 Registry 可见能力编成带 `instance_id/parameters` 的用户目标，事件前提另用内部节点，仍由 `SharedEvidenceGraphCore` 和原 Executor 执行。合成无事件记录上整段质量+两个窗口 PSD；合成事件记录上连续 PSD+Epoch 质量+事件功率均通过。独立 SciPy Welch/积分 oracle 对两窗 alpha 值核验；不同 event scope 生成不同 Epoch，完全同参数只共享一次执行。此时 v3 曾通过绕开构造器继承 v2 的事件适配类，虽不复制 Executor，却让新版依赖旧版特殊字段，审查后改为**直接继承任务中性共享图**，显式实现 record/model/epoch 输入绑定。
2. **真实 LLM 首轮科学证据误拒。** 首次 `deepseek-chat` 请求在合成案例上双窗任务被 `capability_quote_not_grounded` 拒绝：模型给首窗的实例引文只包含窗口，科学操作“绝对频带功率”位于共同后置短语。根因是单一引文承担“实例范围”和“分析概念”双角色。机制修订：`request_quote` 与 `concept_quote` 分离，参数仍逐值引用原文。这不是 PSD 关键词特例；两个目标可以引用同一共同操作概念，但必须各有独立参数范围。首轮失败原始响应保存在忽略目录，不改写为成功。
3. **第二轮观察的范围与共指问题。** 模型为两个窗口的 `request_quote` 拼接了省略号，并把“同一事件”的标签引文写成未含标签值的代词，触发安全澄清。修订后的验证要求窗口范围引文必须是原文最短连续片段；对“同一事件/试次”只在已有前序目标的**完整事件 scope 一致且前序参数已落地**时允许引用，证据包记录 `parameter_sources`。不等价 scope 的负例零执行拒绝。此修订是参数/来源绑定机制，不靠增加 PSD/amplitude 词表。
4. **第三轮协议故障与安全边界。** DeepSeek 有两次 Tool Calling 参数末尾额外一个 `}`，导致 JSONDecodeError；只允许在解析器确认为最后一个字符多余右括号时做单字符修复，随后完整语义/参数预检，不能修任意半截 JSON。另一次模型把缺时间窗误放到 `unsupported_requests`，整体拒绝；协议说明现将缺参和能力不存在区分，代码仍不猜时间值。原始三次错误保留。
5. **第四轮有界验证。** 同三条合成请求均完整闭合：整段质量+双窗 PSD、连续+事件质量/条件功率、缺参先澄清后继续。请求模型为 `deepseek-chat`，实际四次响应均报告 `deepseek-flash`。这只是开发集末轮，不抵消前三轮失败，也不推断真实任务泛化。代码随后补任务内稳定 ID、来源阶段拒绝、质量窗口原子预检、非闭合证据包；这些后续改动以 Fake/单测和完整回归验证，不倒称为新一轮真实 LLM 成功。

四次真实开发套件合计 **15 completion / 32,066 tokens**，低于 Issue #28 的 32/80,000 上限；每次不超过 8/24,000，禁止客户端重试。所有请求只含合成记录元数据、能力说明和自然语言请求；没有真实 EEG/事件/受试者或派生特征外发。分别保存四轮 JSON 与逐请求原始响应 JSONL 在 Git 忽略的本地 `artifacts/`，不提交。失败的科学层级分别是引文/目标范围、共指引用、Tool Calling 格式、缺参分类；图执行的独立测试未因这些语言故障失效。
