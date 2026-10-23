# CCEP/LRSP v1.1 研发状态

更新时间：2026-10-23（Asia/Shanghai）

## 当前阶段

Issue #14 阶段 C：声明式目标契约图及内容寻址 evidence 恢复已接入真实 Agent/Registry/Executor；准备进行有界 Fake/DeepSeek 集成验证和交付审查。继续使用 `research/point1-integrated-method-v0` 与 Draft PR #11；不替换 Baseline v1、CCEP v0 或 LRSP v1。

## 已冻结问题

- v1 的 `next_action()`、`_goal_status()`、`apply_result()` 和失效列表都按三个事件目标写定。
- v1 只有 `event_bandpower` 一个分析 consumer；无法证明共享 Epoch 对多个目标的复用和独立失效。
- v1 用 artifact ID/fingerprint 保证内容一致性，但没有通用的“完成证据依赖哪些目标、输入和版本”表示。
- 每轮多次重算同一 artifact fingerprint；检查与工具执行间变化会安全失败，但 v1 将其作为永久失败停止。

## 选定路线

实现 **Contract-Indexed Evidence Dependency Graph（CIEDG）**：

1. 用小型 `GoalContract` 表声明目标的工具、输入策略、依赖、优先级和结果角色；
2. 从用户请求的原子目标生成闭包和动态依赖图；
3. 每个完成目标产生绑定输入/输出 artifact fingerprint 与上游 evidence token 的 `GoalEvidence`；
4. 每轮依据真实 artifact 版本失效 token 并传播到依赖目标；
5. 只选择 ready residual goal 的一个 frontier；
6. EEG 专属 selection guard 仍由确定性代码掌握授权、质量和每条件 usable count。

新增现有 `epoch_summary` 作为第二 consumer，与 `event_bandpower` 共享 effective Epoch。新增 consumer 的主规划变化应限于一条 contract 与意图目标声明，不再修改 `next_action/apply_result/_goal_status` 分支。

## 不变量

- Intent 的 label/window/source/objectives/authorization 不漂移；
- consumer 只能读取由 requested selection branch 决定的 effective artifact；
- selection 必须依赖同一 source fingerprint 的质量 evidence 和明确授权；
- 每个请求条件至少保留一个可计算 Epoch，否则安全停止；
- evidence token 的输入 fingerprint 或上游 token 失效时，依赖目标必须失效；
- 无关且仍有效的目标不重放；
- LLM 不决定阈值、失效传播、恢复范围或工具参数。

## 阶段 B 原型实测

- 新增 opt-in `point1-v11` Agent 模式；原有 v0/v1 路径不变。
- 六个目标由 `GoalContract` 和依赖闭包生成，不再在 `next_action/apply_result/_goal_status` 中复制 consumer 分支。
- `epoch_summary` 与 `event_bandpower` 已在真实工具链上共享 original/selected effective Epoch，数值和试次数由独立 NumPy oracle 校验。
- artifact 不存在与内容冲突现在使用 `ARTIFACT_NOT_FOUND` / `ARTIFACT_STATE_CONFLICT` 区分，不向 Agent 暴露 traceback。
- 针对性回归：36 项通过。
- 控制故障发现：selected artifact 在 bandpower 前被删除后，系统可只重建 selection 分支并完成任务，但已完成的 `epoch_summary` 被执行两次。科学结果正确，增量复用不充分。

## 下一步

1. 阶段 D：运行固定合成用例的 Fake 与有界 DeepSeek，保留失败。
2. 完整回归、方法/集成/研究判断文档及 README/PROJECT_STATUS 更新。
3. 推送分阶段提交并更新 Draft PR #11 与 Issue #14。

## 提交

- 阶段 A：`037d2c1 research: design LRSP v1.1 evidence dependency graph`
- 阶段 B：`c11bb95 feat: integrate LRSP v1.1 contract evidence graph`
- 阶段 C：待提交。
