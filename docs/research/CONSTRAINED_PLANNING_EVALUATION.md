# EEG 状态感知与约束规划先导评估

## 1. 评估目的

本评估检验最小状态感知约束 Planner 是否具备工程可行性，以及它相对保留完整 Executor Validator 的 Execution-only 和强 Expert Conditional DAG 是否表现出值得继续研究的差异。评估不预设候选方法更优，也不把测试通过视为论文创新成立。

## 2. 方法与 EEG 约束对应

| EEG 约束 | 状态/契约事实 | 规划行为 |
|---|---|---|
| Profile、通道、参考、采样率 | 当前 `EEGRecord` 与 `TaskProfile` | 不兼容时执行前拒绝，不自动重采样或改通道 |
| annotation 与标签 | 当前记录实际 `EventSet` 计数 | 无事件或缺标签时拒绝，不解释标签语义 |
| Epoch 与 baseline | 请求窗口、baseline、当前采样率 | 检查窗口顺序、baseline 包含关系及 1 秒 Welch 下限 |
| artifact 生命周期 | 当前 Context 中的 artifact、Profile、来源摘要 | 只消费同 Context 已存在 artifact；需要时显式规划生产步骤 |
| 模型适用性 | ToolSpec Profile、采样率、资源路径可用性 | 缺资源或 Profile 不符时拒绝，不替换模型 |
| 数据质量 | 当前没有经验证的质量事实 | 保持 unknown，不推断坏道、伪迹或科学有效性 |

Planner 不改变幅值、PSD、Epoch、Welch 或模型算法，最终执行仍使用原 `ToolRegistry / Executor / ExecutionContext`。

## 3. 冻结任务集

任务集为 `config/planning_benchmark_v1.json`，版本 1.0，共 16 个确定性合成任务，在查看策略结果前固定参数和期望结果：

- 开发集 8 项：合法幅值、合法事件功率、非法通道、缺失标签、无事件、Native Profile 请求癫痫模型、缺模型资源、窗口越界。
- 保留集 8 项：不同通道 PSD、未用于开发条件的事件 B、过短 Welch、错误模型采样率、外部 artifact、幅值+事件异构组合、执行期 artifact 丢失、不可支持的临床诊断目标。
- 6 项期望完成，10 项期望安全拒绝。

动态 artifact 案例在三种策略完成预检后统一删除已有会话 artifact。TaskSpec 同时保留合法 labels/window，因而动态 Planner 可以重新构造 artifact；Expert DAG 没有动态恢复步骤。该案例是人为控制的状态变化，不代表真实环境发生率。

## 4. 比较策略

1. **Execution-only**：把目标直接提交给相同 Executor，不进行全局依赖规划；Validator 完整保留。
2. **Expert DAG**：显式检查 Profile、schema、通道、窗口、资源、事件和 artifact，事件任务使用 `create_epochs → event_bandpower`，是强条件基线。
3. **Constrained Planner**：从 `EEGStateSnapshot + OperationContract` 构造 Plan；事件任务使用 `list_events → create_epochs → event_bandpower`，允许一次动态重规划。

消融包括：移除状态预检但保留依赖模板、禁用动态重规划、只保留普通参数/Executor 校验。

## 5. 总体结果

以下为同一环境一次冻结运行的结果。完成率、拒绝率、错误数和调用数是确定性的；毫秒耗时仅作描述，不用于统计推断。

| 策略 | 有效任务完成率 | 正确拒绝率 | 不合法调用/总调用 | 运行时错误 | 工具调用 | 平均耗时 ms | 重规划 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Execution-only | 33.3% | 0% | 14/17（82.4%） | 14 | 17 | 0.074 | 0 |
| Expert DAG | 83.3% | 100% | 1/10（10.0%） | 1 | 10 | 0.157 | 0 |
| Constrained Planner | 100% | 100% | 1/16（6.3%） | 1 | 16 | 0.211 | 1 |
| 消融：无状态追踪 | 66.7% | 0% | 12/20（60.0%） | 12 | 20 | 0.164 | 0 |
| 消融：无重规划 | 83.3% | 100% | 1/13（7.7%） | 1 | 13 | 0.159 | 0 |
| 消融：仅普通参数校验 | 33.3% | 0% | 14/17（82.4%） | 14 | 17 | 0.066 | 0 |

“正确拒绝”要求策略在工具调用前明确返回不可满足/不支持；Execution-only 的 Executor 错误不计为规划层正确拒绝。“不合法调用”是提交给 Executor 后失败的工具请求，包括动态状态过期造成的 artifact 失败。

## 6. 开发集与保留集

| 策略 | 开发集完成/拒绝 | 保留集完成/拒绝 |
|---|---:|---:|
| Execution-only | 50% / 0% | 25% / 0% |
| Expert DAG | 100% / 100% | 75% / 100% |
| Constrained Planner | 100% / 100% | 100% / 100% |

Expert 与 Planner 在全部静态可执行/不可执行案例上结论一致。保留集差异完全来自单个“预检后 artifact 被删除”案例：Expert 执行时收到 `ARTIFACT_NOT_FOUND` 并停止；Planner 同样先收到一次错误，随后根据当前状态重新规划三步事件链并完成。因此结果支持“有限动态重规划可以恢复这一类状态过期”，不支持“Planner 全面优于 Expert”。

## 7. 逐类失败分析

- Execution-only：合法事件任务因没有前置 Epoch artifact 而失败；所有应拒绝任务均在 Executor 处成为运行时错误。它证明依赖规划有价值，但不是强领域基线。
- Expert DAG：仅动态 artifact 丢失案例失败；其余任务正确完成或执行前拒绝，并以 10 次工具调用少于 Planner 的 16 次。
- Constrained Planner：动态案例首次消费过期 artifact 时仍产生 1 次运行时错误，之后重规划恢复；额外 `list_events` 和恢复链增加调用及开销。
- 无状态消融：依赖模板能完成部分事件任务，但不能正确拒绝缺标签、无事件或其他不满足约束的目标。
- 无重规划消融：与 Expert 一样在动态案例失败，说明本任务集中 Planner 相对 Expert 的唯一完成率增益来自动态恢复。
- 仅参数校验消融：与 Execution-only 相同，说明单工具 Validator 不能替代跨工具 artifact 依赖规划。

所有策略的精确重复调用计数为 0。Planner 的额外调用属于契约链和重规划，不按“完全相同请求重复”定义计为冗余，但仍构成实际调用成本。

## 8. 端到端与真实资源回归

- 合成时窗任务：生成 1 步 PSD Plan，返回 ToolResult 与 ExecutionTrace。
- 合成事件任务：生成 3 步 Plan，完成事件→Epoch→频带功率。
- 现有 EEGAgent EDF/权重：真实一秒癫痫工具经 Planner 完成 1 次调用；该输出只用于工程回归，不报告诊断或性能。
- 本地 R3 匿名 EDF：标签 `1` 的事件链经 Planner 完成 3 次调用；不报告路径、参与者、组别或单文件特征。
- 真实 OpenAI 兼容环境变量未配置，因此真实 LLM 未验证；Planner 的无 LLM 比较不受影响。

## 9. 局限与客观可行性判断

主要局限：任务集仅 16 个确定性合成案例；Expert 规则与 Planner 都由同一项目知识设计；动态优势来自一个人为扰动；没有自然语言解析误差、并发资源变化、大规模 artifact 图或真实用户任务分布；耗时样本不足；没有与外部 scientific-contract 框架复现比较。

**可行性结论：有条件继续，但目前不足以作为已成立的论文创新点。**

支持继续的证据是：状态/契约模型能在同一 Harness 上工作，正确隔离 artifact，执行前拒绝静态非法目标，并在一个状态过期案例中安全重规划。限制性证据同样明确：强 Expert DAG 在全部静态任务上与 Planner 持平、调用更少、耗时更低；Planner 的唯一完成率优势来自预设动态案例，且恢复前仍发生一次 Executor 错误。

若继续研究，下一步应聚焦于难以由少量 Expert 分支维护的真实异构任务、状态不确定性与 provenance 约束，并扩大冻结保留集；若在更广任务集上仍只与 Expert 持平，应把该机制定位为可靠执行工程，而不是独立创新点。
