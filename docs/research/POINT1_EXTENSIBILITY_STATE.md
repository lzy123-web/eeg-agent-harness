# 工作点一可扩展性证据状态

## 任务与边界

- Issue：#22。
- 隔离分支：`research/point1-extensibility-evidence`。
- 基线分支：`research/point1-integrated-method-v0`，起点 `bff894065b1647fc168f1c0ac4b226c16768e263`。
- 冻结候选仍为 Issue #16 记录的 `921b04a561b27c2e68964d5f3f1e995ee08c8c6d`；本分支只增加隔离实验适配层，不修改冻结 CIEDG、Strong Expert、正式协议或历史结果。
- ESOCC 暂停；不运行付费 LLM，不增加第三种状态转换，不使用真实 EEG。

## 当前进度

- [x] 读取 Issue #22 并建立隔离分支。
- [x] 审计 TaskSpec、IntentSpec、GoalContract、ToolRegistry、Executor、Evidence Gate 和 Strong Expert。
- [x] 冻结唯一能力增量、实验案例、oracle、公平口径和停止条件。
- [ ] 实现隔离 registered tool、CIEDG+extension 与 Expert+extension。
- [ ] 运行独立 oracle、故障恢复、公平成本测量和全仓回归。
- [ ] 形成结果、研究决策、Draft PR、CI 与 Issue 评论。

## 已冻结设计

- 唯一新增能力：`epoch_variance`，对 Epoch artifact 计算按条件、按通道的总体方差（`ddof=0`）以及试次数；它是只读 consumer，不产生新 EEG 状态。
- 工具实现使用 `numpy.var`；独立 oracle 使用显式 `sum((x-mean)^2)/N`，不调用工具实现。
- 仅使用确定性合成 EEG；覆盖 source、质量筛选后的 effective Epoch、显式重参考后的 effective Epoch、禁止筛选、瞬时失败、artifact 失效后的内容等价/内容变化恢复。
- CIEDG 和 Expert 使用同一 ToolRegistry、Executor、fixture、oracle、fault、调用/恢复预算；允许 Expert 抽取共享规则，不假定其必须复制全部流程。

## 早期审计结论

- 当前 CIEDG 不是“新增一个 Registry entry 即自动工作”：`IntentSpec`/`compile_intent`/静态 Planner 的目标枚举、`GOAL_CONTRACTS` 以及基础 planner 的 `_required_answer_tools` 都存在显式目标知识。
- 图执行、effective binding、artifact fingerprint、依赖失效和 consumer cache 是角色驱动的通用机制；但 selection 与 rereference 仍由两个 planner 类分别表达，二者组合仍被拒绝。
- Strong Expert 对 summary、bandpower、selection、rereference 和恢复采用显式分支；它同样可以通过认真抽象降低新增 consumer 成本，实验不得阻止这种抽象。

