# CCEP v1 研发状态

更新时间：2026-10-23（Asia/Shanghai）

## 当前阶段

Issue #13 阶段 III：LRSP 初版已接入真实链，并完成首轮内容 lineage/evidence binding/回答条件修订；下一步是完整 Fake 回归和有界真实 DeepSeek 验证。分支继续使用 `research/point1-integrated-method-v0`，Draft PR #11 保持 Draft；Baseline v1 和 CCEP v0 均不替换。

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

## 首轮机制修订

- 实测初版无法发现同 ID Epoch 内容在质量后变化，会错误复用旧 evidence。
- 新增 Epoch 内容 fingerprint；质量 evidence 同时绑定 ID、内容和阈值。
- residual planner 在每个 frontier 前检查 fingerprint，内容变化会撤销下游完成项并回到质量测量。
- 选择工具支持 expected evidence/fingerprint；最终回答由运行时追加真实 branch 与经验阈值边界。
- 修订后相关回归 51/51 通过，1 个外部资源模型测试跳过。

## 下一步

1. 完成全仓 Fake/单元回归并保存两条完整动态轨迹。
2. 使用合成 EEG 进行少量真实 DeepSeek 调用，保留语义层失败，不调 prompt 刷分。
3. 完成下一步 guarded Expert 公平协议、项目状态、PR/Issue 报告。

## 提交

- 阶段 I：`b85eef2`，研究设计与恢复状态，已推送。
- 阶段 II：`d96c764`，LRSP 初版、Fake/oracle/恢复测试，已推送。
- 阶段 III：待提交。
