# 工作点一新版本：跨任务 EEG 目标—状态—证据图设计（Issue #26）

## Issue #26 纠偏后的三项清单（2026-10-24）

| 分类 | 内容与依据 |
|---|---|
| 保留 | 现有 `EEGRecord/EventSet/EpochSet`、Profile、`ToolRegistry/Executor/ExecutionContext`，旧 CIEDG 的目标依赖 token、内容与身份分离、失效传播及局部恢复思想；保留旧 v1.1 路径和历史实验原样。新版本已完成的记录内容绑定、跨族原子预检和本地模型输入核验继续保留。 |
| 任务专有化 | `labels/tmin/tmax/baseline`、源/筛选后 Epoch、试次质量与授权筛选属于事件适配策略；通道窗与严格 22 导模型约束属于对应记录/模型策略。它们不能充当通用图的默认字段或默认前提。 |
| 重构 | 初版 `MultiTaskContractGraphPlanner` 继承 event-only 的 `ContractGraphResidualPlanner`，虽然复用了同一个 frontier、失效与发布过程，却仍继承 `_compile_dependencies` 的 Epoch 筛选分支、`state_dict` 的 Epoch 默认结构、`next_action` 的筛选特例，以及按记录/事件分别预检的入口。不能把它直接称为已完成的共同机制；新版需把“目标依赖、输入类型、适用性、状态更新、失败与证据发布”移到任务中性的核心，事件语义变为适配策略。 |

上述分类来自 [Issue #26 最新纠偏](https://github.com/lzy123-web/eeg-agent-harness/issues/26#issuecomment-6382639080) 与本地真实调用链审查。下文为初版设计记录；最终实现与局限以迭代/验证文档为准，不以保住旧 CIEDG 架构为目标。

## 要解决的具体缺陷

冻结 v1.1 CIEDG 的依赖图仅接收 `event_workflow`；`ConstraintCarryingEEGAgentV11.run` 将连续信号与模型任务交给单工具 `ConstrainedPlanRunner`。于是同一 Harness 虽有多类工具，却没有对连续记录/模型输入和事件 Epoch 一致的剩余目标、输入版本、证据失效与恢复机制。PR #23 的 Epoch 只读 consumer 扩展没有解决此跨科学对象缺口，也未证明较强 Expert 更低维护成本。

## 方案比较与选择

| 路线 | 优点 | 主要问题 | 决定 |
|---|---|---|---|
| A. 旧 v1.1 保持 event-only，外层 router 对连续/模型各调用原单工具 Planner | 变更最少 | 没有共同目标/状态/证据路径；record 状态变化不使已完成工具结果失效 | 排除 |
| B. 把连续记录伪装成一个事件/Epoch | 可勉强套用旧 input policy | 伪造事件科学语义，模型输入条件被混淆 | 排除 |
| C. 新版 graph contract 显式增加 `record` 输入策略，把 record 与 Epoch 目标放入同一前沿、证据 token、失效传播、局部恢复、发布机制；旧 v1.1 运行路径不变 | 面向实际缺口，复用旧图执行与现有 Registry/Executor；可测试混合目标及内容变更 | 仍需目标编译和科学 preflight；本轮语言层仍有单意图限制 | **选用** |

WINGS 已用语义约束表达科学组件与数据适配（[原论文](https://doi.org/10.1109/MIS.2010.9)）；[W3C PROV-O](https://www.w3.org/TR/prov-o/) 已形式化使用/派生/失效；[CogEEGAgent](https://arxiv.org/abs/2607.25045) 已区分语言与科学权限。因此本工作不能把“新增图”“显式 metadata”单独声称创新。研究问题是 EEG 中**记录窗、事件派生与严格模型输入三种科学对象**如何在同一执行图内绑定当前内容与来源、保留科学约束，并在变化后精确撤销旧证据。相对公平强专家的价值尚未验证。

## 核心契约与伪代码

新 `MultiTaskRequest` 为 parsed-task 边界：`objectives`、每目标参数、共享事件参数、禁止操作。自然语言仍由已有 EvidenceBoundIntentInterpreter 解释，不在本轮开展 ESOCC 或自由语言目标完备性新研究。`compile` 只允许 Registry 现有工具对应的明示目标，未知目标/不受支持组合整体拒绝。

```text
request -> immutable TaskSpec + obligation ledger
for each requested goal and graph dependency:
    validate profile / channels / time / events / epoch duration / resource
if any goal invalid or forbidden: reject entire task before tool execution
graph.frontier := contracts with all dependencies evidenced
for each action:
    bind current record content+source OR current Epoch artifact ID+fingerprint
    execute through existing ExecutionContext -> Executor -> Registry tool
    create goal evidence token with arguments, input binding, dependency tokens
    after every state observation, reconcile changed bindings and descendants
    retry bounded failures; only reuse scientifically equivalent consumer evidence
release only answer-required evidence bound to current state
```

`record` binding必须同时涵盖 EEG 数组内容、采样率、通道、参考/导联、来源及处理元数据；不把原始数组送给 LLM。记录内容或来源变化会使 record-level 结果、`list_events/create_epochs` 及其下游证据失效。Epoch consumer 继续沿用旧 `source/effective` artifact ID+fingerprint、授权筛选和旧图的局部恢复。科学操作仍只经现有 Executor 执行，不创建第二套 EEG 算法或执行器。

## 不变量与任务边界

1. 无事件记录的连续任务不创建虚假 EventSet/EpochSet；事件任务缺事件/标签时预检拒绝。
2. 同一任务任一目标缺参、资源缺失、Profile 不符或变换未授权时，**整体**拒绝，不静默执行可完成子集。
3. record window 使用真实采样率、通道和时间边界；模型另需指定合法 Profile、256 Hz、1 秒输入及权重。通道数相同不等于 Profile 合法。
4. 记录或 Epoch 输入变化后，当前回答不得引用失效的旧 token；content 等价复用与 source identity 不混同。
5. `epoch_quality` 只是经验筛查证据，不能默认删试次；绝对 PSD 不能被称 ERP/ERD/ERS 或 ASD 评分。
6. answer gate 由合同声明的 `answer_required` 目标决定，不再对连续/事件写两套结果发布路径；数值须指向真实 ToolResult 标量。

新版本保留旧 v1.1 类和历史正式实验；可提取并改造目标图机制，但不能以“只能继承旧事件类”为架构限制。事件与连续必须在新版共享任务中性的 frontier、证据 token、输入绑定、状态失效、错误边界和结果门；模型若资源可用，也只作为合法调用协议证明，而非 ASD 应用模型。
