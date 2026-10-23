# CCEP v1 研发状态

更新时间：2026-10-23（Asia/Shanghai）

## 当前阶段

Issue #13 阶段 I：设计已冻结，准备实现动态科学状态与 residual-goal 增量执行。分支继续使用 `research/point1-integrated-method-v0`，Draft PR #11 保持 Draft；Baseline v1 和 CCEP v0 均不替换。

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

## 下一步

1. 实现 v1 opt-in runner 与 Agent，保留 v0。
2. 先运行异常、干净、全坏和 transient failure 场景，记录初版缺陷。
3. 至少进行一轮算法级修订，再做 Fake、独立 oracle 与有界 DeepSeek 验证。

## 提交

- 阶段 I：待提交。
