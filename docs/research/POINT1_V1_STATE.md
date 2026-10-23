# CCEP v1 研发状态

更新时间：2026-10-23（Asia/Shanghai）

## 当前阶段

Issue #13 阶段 II：LRSP 初版已接入真实 `ExecutionContext → Executor → ToolRegistry` 链，正在进行机制缺陷探针与算法修订。分支继续使用 `research/point1-integrated-method-v0`，Draft PR #11 保持 Draft；Baseline v1 和 CCEP v0 均不替换。

## 已继承事实

- Issue #12 已证明实际 Epoch 筛选、3→2、派生波形和频带数值实现正确。
- CCEP v0 与同规则强 route+preflight 在共享任务完全持平；真实两例中 CCEP 1/2、Native 2/2。
- v0 的 `event_workflow` 在执行前生成完整 DAG；失败后从首步重放，质量结果不进入后续计划状态。
- 当前质量阈值是未临床校准的 screening suggestion，不能当生物医学真值。

## 选定机制

选择 **Lineage-aware Residual Scientific Planning（LRSP）** 作为 CCEP v1 核心：

1. Intent/ledger 冻结用户目标和禁止操作；
2. 确定性科学状态保存 Epoch lineage、质量证据、每条件计数、完成目标和失败；
3. Planner 每次只计算剩余目标的下一个合法 frontier；
4. Executor 仍是唯一工具执行入口；
5. 新证据到达后重新归约剩余目标，不重放仍有有效证据的步骤；
6. LLM 不决定阈值、不看原始数组，也不负责运行时科学分支。

Guarded conditional DAG 将作为未来强动态 Expert；LLM feedback replanning 不作为 v1 主机制。

## 科学不变量

- label、window、source 与用户授权在运行时不可更改；
- 选择必须有同一 artifact 的质量证据与明确授权；
- 无异常时 selection 以 identity transition 满足，不创建伪派生 artifact；
- 任一请求条件在选择后为零试次时停止，不静默遗漏该条件；
- 后续分析只能消费当前存在且 lineage 合法的 artifact；
- artifact 失效会级联撤销依赖它的完成证据；
- transient retry 只重试剩余 frontier，不重放已完成且仍有效步骤；
- 经验阈值、绝对功率非 ERD/ERS 等边界进入 trace/answer。

## 已实现初版

- `ConstraintCarryingEEGAgentV1` 是 opt-in 入口，非事件任务仍走现有 v0 执行语义且不重复做 Intent 调用。
- `ResidualScientificPlanner` 每次只产生一个 frontier action；异常、干净、全坏与禁止筛选四种质量状态会产生不同后续动作。
- transient bandpower 故障只重试 bandpower；已经成功的事件观察、Epoch、质量与选择不重放。
- 真实选择的 3→2 Epoch 数据和 bandpower 已由独立 NumPy/SciPy oracle 验证。
- 初版新增 7 个测试；CCEP v0、证据阶段及 v1 共 33 个相关测试通过。

## 下一步

1. 用受控探针检查同 ID artifact 内容变化、质量 evidence 绑定与回答状态表达。
2. 对实际暴露的机制缺陷做至少一轮算法级修订，而不是追加 Prompt 特例。
3. 完成 Fake 全回归、有界 DeepSeek 验证、集成说明与下一步公平实验设计。

## 提交

- 阶段 I：`b85eef2`，研究设计与恢复状态，已推送。
- 阶段 II：待提交。
