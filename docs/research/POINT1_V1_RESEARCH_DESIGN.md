# CCEP v1：动态 EEG 科学状态与增量约束规划研究设计

## 1. 研究问题的精确定义

CCEP v1 研究的问题不是“LLM 是否能写出更长的 EEG 工具链”，而是：

> 给定已经由自然语言阶段冻结的用户目标、参数、禁止操作和授权，当 EEG 工具在运行时才产生质量、每条件可用试次、派生 artifact、资源或故障状态时，执行器如何只为尚未满足的科学目标选择下一个合法动作，并保证已完成证据不被无理由重算、失效证据不被继续复用？

可测对象是运行时状态更新、剩余目标、动作 frontier、lineage 与重算原因，而不是最终成功率本身。

## 2. CCEP v0 的具体断点

源码审查确认：

1. `planning.py::StateAwareConstrainedPlanner._plan_event_workflow` 在质量结果产生前就构造完整 DAG；质量数值不能改变后续步骤。
2. `ConstrainedPlanRunner.execute_plan` 失败后重新生成整张计划，并从第一步执行，导致 `list_events/create_epochs/epoch_quality` 等成功步骤被重复。
3. `EEGStateSnapshot` 只枚举 artifact 元数据；`verified_quality_facts` 没有从真实结果填充。
4. v0 对 clean Epoch 仍调用 `select_quality_epochs`，创建数据完全相同但名字不同的派生 artifact；这混淆了“授权选择”与“实际发生筛除”。
5. 多条件筛选可能只保留部分条件；当前选择工具只在全部 Epoch 为空时失败，后续 bandpower 可静默缺少某个用户请求条件。
6. artifact lineage 主要在最终 `close_ledger` 检查，不能主动决定下一动作或撤销依赖失效 artifact 的完成项。

这些问题是机制层断点，不是补 Prompt 或关键词可以解决的意图错误。

## 3. 相关工作的直接启示

- 原 EEGAgent 采用“模型规划—工具反馈—继续推理”的循环，但论文描述没有给出跨工具 EEG artifact 状态、选择授权或 residual-goal 保持机制：[EEGAgent](https://arxiv.org/html/2511.09947)。
- CogEEGAgent 将语义路由与确定性科学 authority 分开，并使用 typed contract、commitment ledger 与 evidence-bound release；作者也明确指出 internally consistent wrong-template 不能被 preflight 发现。其重点是路由、验证和确认数据生命周期，而不是 Epoch 质量反馈后的剩余工作合成：[CogEEGAgent](https://arxiv.org/html/2607.25045)。
- MNE 的 `Epochs.selection`、`drop_log` 和 `drop_bad()` 明确区分保留索引、删除原因与当前剩余 Epoch；一旦 drop，较宽松阈值不能恢复原对象，因此 lineage/副本和选择原因必须显式保留：[MNE Epochs](https://mne.tools/stable/generated/mne.Epochs.html)。
- W3C PROV 将派生描述为 entity 被 activity 使用并生成新 entity，也允许计划在执行中演化并记录其 provenance；这支持把原 Epoch、选择活动和派生 Epoch 分开建模，而不是只记录最后 ID：[PROV-DM](https://www.w3.org/TR/prov-dm/)。
- 经典 plan repair 研究强调在观测状态变化后尽量保留仍有效的旧计划/完成工作，而不是无差别从头重规划；但它并不提供 EEG 科学约束：[Plan Stability](https://cdn.aaai.org/ICAPS/2006/ICAPS06-022.pdf)。
- 类型化科学对象图能改善工具编排和 provenance，但仍需领域状态转移语义：[El Agente Gráfico](https://arxiv.org/abs/2602.17902)。

因此，本项目可能的贡献只能是把 residual planning 与 EEG 的 Epoch/质量/条件计数/授权/lineage 组合成可执行机制；单独的状态机、DAG、schema 或 validator 都不是新颖性证据。

## 4. 候选方案比较

| 方案 | 核心 | 优点 | 主要风险 | 复用与成本 |
|---|---|---|---|---|
| A. Evidence-triggered partial replanning | 每个证据边界后裁剪已完成步骤，再重建后缀 | 易在 v0 runner 上增量实现；能减少重复 | 若只按工具名裁剪，会错误复用参数或 lineage 不同的结果 | 复用 Planner/Runner；中等成本 |
| B. Scientific-state transition + residual goals | 显式状态、目标满足证据和合法转换；每轮合成一个 frontier | 状态、授权、条件计数和 lineage 可统一推理；恢复原因可解释 | 状态模型设计不完整会导致错误缓存或目标误满足 | 复用 Intent/ledger/Executor；中高成本 |
| C. Guarded conditional DAG | 预编译质量/计数/故障分支，运行时按守卫选择 | 完全确定、易审计；是很强的 Expert 基线 | 分支组合膨胀；未知工具状态仍需 repair；容易退化为手写 workflow | 复用 PlanStep/Executor；中等成本 |
| D. LLM execution-feedback replanning | 把每步摘要返回 LLM，让模型重写后续计划 | 开放任务灵活 | 可能改 label/window/阈值；费用与隐私增加；难复现 | 与现有 LLM client 兼容；科学风险高 |

选择 B，并吸收 A 的“只修复后缀”原则。C 不被弱化，留作下一轮公平强动态 Expert。D 只用于第一次 Intent 理解和最终证据选择，不拥有运行时科学 authority。

## 5. 选定机制：Lineage-aware Residual Scientific Planning（LRSP）

### 5.1 状态

`DynamicScientificState` 至少包含：

- 固定任务边界：context/profile/source、labels、window、objectives、selection authorization；
- artifact 节点：ID、类型、是否存在、生成动作、父 artifact、参数签名、每条件计数；
- evidence 节点：质量 evidence ID、绑定 artifact、flagged indices、每条件 usable counts、阈值状态；
- goal ledger：每个原子目标的 `pending/satisfied/blocked`、满足它的 request/result/artifact；
- failures/retries：失败动作签名、错误类型、剩余预算、是否允许同动作重试。

### 5.2 状态转移与 frontier

```text
Intent + immutable obligations
              |
              v
observe events -> create Epoch artifact -> measure quality (when required)
                                               |
                    +--------------------------+-----------------------+
                    |                          |                       |
               flagged = 0              0 < usable < input       usable = 0
                    |                          |                       |
          identity selection state      authorized selection       safe stop
                    |                          |
                    +------------> choose effective artifact <------+
                                                   |
                                            event bandpower
```

每轮执行：刷新 artifact 存活状态 → 撤销失效依赖 → 归约已满足目标 → 检查 blocked guard → 生成唯一 next action → 用现有 Executor 执行 → 将结果和 provenance 写回 → 继续。

### 5.3 不变量

1. **目标不漂移**：label/window/source/objectives/forbidden operations 来自冻结 ledger，运行时不可修改。
2. **selection authority**：没有明确授权时任何状态都不能产生选择动作。
3. **evidence binding**：质量 evidence 只能约束其精确 artifact；派生 artifact 记录 parent 与 evidence ID。
4. **condition preservation**：选择后每个请求 label 至少保留工具可计算的 1 个 Epoch；这只是当前工具可行性下限，不是统计充分性阈值。
5. **identity transition**：授权筛选但 flagged=0 时，选择目标由质量证据满足，复用原 artifact，不伪造派生数据。
6. **valid reuse**：完成项只有在参数签名、依赖 result 和 artifact 都仍有效时才可复用。
7. **monotone recovery**：transient failure 不撤销无关成功项；artifact 失效则只级联撤销依赖该 artifact 的目标。
8. **typed stop**：无试次、未授权、永久工具错误或预算耗尽必须结构化停止，不能降阈值、换 label/window 或跳过必需目标。

## 6. 权限边界

| 层 | 职责 |
|---|---|
| LLM Intent | 将自然语言映射到已注册目标、显式参数、否定和授权；缺参则澄清 |
| LRSP Planner | 根据真实状态和 residual goals 选择下一个已注册动作；不能发明阈值/标签 |
| Executor/Tools | schema/Profile/资源校验与 EEG 数值计算；唯一能读取波形 |
| Runtime Gate | 检查 ledger、不变量、artifact 存活、每条件计数、重试预算 |
| LLM Answer | 只选择成功 ToolResult 的标量路径；运行时解析并发布 |
| 用户 | 提供未知 label/window、筛选授权及超出当前工具语义的科学选择 |

## 7. 预期失败模式与研发探针

- clean 数据被不必要复制：应由 identity selection 修复；
- 多条件中某条件筛空但总数非零：应在选择前停止；
- transient bandpower 失败后重复创建/质量/选择：应只重试 bandpower；
- artifact 被外部清除后仍复用旧 evidence：应级联失效并记录必要重算；
- 同工具、不同参数结果被错误缓存：动作签名必须包含规范化参数和输入 artifact；
- LLM Intent 误拒：与 v0 相同，单独计为语义层错误，不能归为动态 Planner 改进。

## 8. 当前研究地位

LRSP 是待验证的方法候选。专家 guarded DAG 也能表达相同动态分支，本任务不会预先宣称创新成立。v1 的直接成功标准是机制与 v0 可区分、状态确实改变后续动作、恢复不盲目重放、数值/lineage 有独立 oracle；相对优势留给方法稳定后的新冻结实验。
