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
