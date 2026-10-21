# 约束规划 v2 复现实验与可行性结论

## 结论先行

在补齐同等状态观察、一次恢复机会、8 次工具调用上限后，强 Expert DAG 与 Constrained Planner 在冻结 v2 合成任务集上均达到：有效任务完成率 100%、正确拒绝率 100%、瞬态恢复 2 例、失败 0 例。Planner 使用 27 次工具调用，强 Expert 使用 20 次。当前实验**没有观察到 Planner 相对强专家的任务结果优势**。

因此，对“研究点一已经具有性能优势”的判断为 **No-Go**。对继续研究其“声明式约束能否降低多任务扩展维护成本”的判断为 **Conditional Go**：代码结构显示潜在价值，但当前只有两个 Artifact consumer，尚不足以形成外部有效性证据。

## 协议与可复现入口

- 冻结清单：`config/planning_benchmark_v2.json`
- 清单 SHA-256：`89e3a6d3247359268a54d66de347de4117861434d6509acc56c06d22c249d934`
- 评估代码基线：`be0522c37dc699a32dceb7025ebc79eea9379826`
- 完整逐例输出：`docs/research/results/planning_benchmark_v2.json`
- Fake 自然语言对照：`docs/research/results/nl_agent_fake_comparison.json`

```powershell
$env:PYTHONPATH = "$PWD\src"
& $python -m eeg_harness.plan_cli --benchmark `
  --suite config/planning_benchmark_v2.json `
  --output artifacts\planning_benchmark_v2.json
& $python -m eeg_harness.plan_cli --nl-benchmark `
  --output artifacts\nl_agent_fake_comparison.json
```

任务预算统一为最多 8 次工具调用、8 次状态检查、1 次恢复。结果区分直接完成、瞬态恢复、预检拒绝、Executor 拒绝和失败。Executor 拒绝表示安全边界生效，不表述为危险执行。

## 公平专家基线

v1 的 `expert_dag` 没有恢复机会，而 Planner 有一次重规划；唯一完成率差异来自 Artifact 在预检后失效。v2 将原策略保留为 `expert_dag_no_recovery` 消融，并令强 `expert_dag` 与 Planner 使用相同恢复和状态检查预算。

| 策略 | 有效完成率 | 正确拒绝率 | 瞬态恢复 | 失败 | 工具调用 | 状态检查 |
|---|---:|---:|---:|---:|---:|---:|
| Execution-only | 22.2% | 100% | 0 | 7 | 23 | 0 |
| Expert DAG 无恢复 | 77.8% | 100% | 0 | 2 | 17 | 0 |
| 强 Expert DAG | 100% | 100% | 2 | 0 | 20 | 26 |
| Constrained Planner | 100% | 100% | 2 | 0 | 27 | 26 |
| Planner 无状态消融 | 66.7% | 100% | 0 | 3 | 28 | 0 |
| Planner 无重规划消融 | 77.8% | 100% | 0 | 2 | 23 | 22 |

正确拒绝率不能单独说明规划质量：Execution-only 通过 Executor 运行时拒绝也达到 100%，但对可完成的跨工具任务完成率低。Planner 多出的调用主要来自显式 `list_events` 状态观察；wall-clock 仅为单机微秒/毫秒级描述值，不作统计推断。

## 声明式扩展观察

`ToolSpec` 现声明 `consumes_artifact`、`produces_artifact`、`requires_events`、`observes_state`、`preconditions` 和 `state_effect`。`build_operation_contracts` 不再维护工具名→依赖的静态字典。新增 `epoch_summary` 路径时，Planner 的 Artifact consumer 规划函数未增加 `epoch_summary` 专用分支；其生产者、观察器和依赖均从契约发现。

这说明“减少一处工具名硬编码”已经实现，但不能外推为“大规模任务扩展成本更低”。强专家在本轮也被泛化为读取同一 Artifact 契约，最终结果与 Planner 持平。更可信的扩展性结论需要多个不同 Artifact 类型、独立开发者盲测以及变更工时/缺陷统计。

## 动态故障与有效性限制

实现了 Artifact 过期、事件变化、模型资源失效、Profile 不匹配和一次性工具失败五种确定性注入，固定在初始决策之后、首次受影响调用之前。Artifact 过期和一次性工具失败可恢复；事件或资源确实消失时应拒绝，系统不会伪造转换。

冻结清单中的 `holdout_profile_change` 本身使用 Native Profile 请求癫痫模型，在注入前已因不兼容而拒绝，因此该条**没有测到动态 Profile 变化**。为避免事后修改锁定留出集，清单保持不变；动态 Profile 注入改由独立回归测试验证。这是 v2 留出集的已知设计缺陷，不能隐藏或按动态恢复样例计数。

事件存在只表示有机器可读 annotation，不证明 Epoch 科学适用、数据质量合格或可做 ERP/ERD/ERS。所有合成任务只验证执行约束，不构成临床或神经科学结论。

## 自然语言 Agent

增加了可选 `NaturalLanguageGoalInterpreter → TaskSpec → Planner → Executor` 桥，保留原生 Tool Calling Agent。发往模型的状态只含 Profile、采样率、时长、通道、事件计数和工具名，不含 EEG 数组、路径、Artifact ID 或派生特征。

9 条人工模板的 Fake 对照中，结构化目标桥下的强专家与 Planner 均为 100% 意图/结果正确；原生 Tool Calling Fake 为 55.6%。该差异来自人工 Fake 的协议覆盖不同，且两种输出模式使用不同格式 Prompt，**不是 Planner 或真实 LLM 优势证据**。Fake 结果只证明软件闭环与错误处理可测试。

2026-10-21 检查 `EEG_HARNESS_LLM_BASE_URL/API_KEY/MODEL` 均未配置，未调用真实外部 LLM，真实意图解析、token/API 成本和端到端稳定性保持未验证。

## 真实资源与测试

- 原 EEGAgent `gped_049_a_6.edf` + 现存 `seiz&normal.pth`：癫痫模型工具、Workflow 和 Fake Agent smoke 均通过。
- 本地匿名 R3 单文件：Profile、事件工作流和去标识输出测试通过；不解释标签、组别或临床意义。
- `compileall` 通过；提供上述资源时 98 项测试全部通过；无私有资源时 87 项通过、11 项按设计跳过。

## 客观决策

- **性能优越性：No-Go。** 强专家与 Planner 结果完全持平，Planner 工具调用更多。
- **可靠执行机制：Conditional Go。** 状态快照、声明式依赖、结构化拒绝和恢复边界具有工程可用性，但需真实任务分布验证。
- **论文创新点一：尚未成立。** 后续若继续，应把研究问题收缩为可量化的可维护性、迁移成本或复杂依赖一致性，而不是预设成功率优势。
- **真实自然语言 Agent 结论：No-Go（证据不足）。** 无真实 API 运行，不得从 Fake 模板推断。
