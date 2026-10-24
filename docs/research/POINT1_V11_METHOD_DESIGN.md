# CCEP/LRSP v1.1 方法设计：契约索引的证据依赖图

## 1. 研发问题

LRSP v1 已证明工具结果可以在运行中改变后续动作，但其实现仍等价于一条手写的 Epoch 过程：`list → create → quality → optional select → bandpower`。本轮研究问题是：

> 在不引入第二套 EEG Core/Executor 的条件下，如何把“目标是否满足、满足证据依赖哪个 EEG artifact 版本、状态变化应撤销哪些目标”变成可声明和可审计的图，使新增合法 consumer 不必复制整条过程分支？

目标不是开放式任意规划；而是在有限注册 EEG 能力内，把动态 evidence/lineage repair 从工具名 if/else 中分离。

## 2. v1 源码审计

| 位置 | v1 硬编码 | 可保留机制 |
|---|---|---|
| `next_action()` | 固定顺序检查 event/create/quality/select/bandpower | 一次只执行一个 frontier、动态 guard |
| `_goal_status()` | 三个 objective 的专用字段 | pending/satisfied/blocked 语义 |
| `apply_result()` | action kind → 专用实例变量 | 结构化错误、有限重试 |
| `_invalidate_missing_artifacts()` | 手写撤销 quality/selection/bandpower | ID+内容 fingerprint、级联失效原则 |
| `_required_answer_tools()` | 手写工具列表 | Evidence Gate 依据实际分支闭合 |

v1 的算法价值集中在内容绑定、剩余目标和局部恢复，而不在固定工具顺序。v1.1 应保留前三者并删除目标特定状态字段的扩展负担。

## 3. 相关依据与边界

- MNE 明确保存 `selection`/`drop_log`，且已 drop 的 Epoch 不能由更宽松阈值恢复，支持把原 Epoch、选择活动和派生版本分开，而不是原地覆盖：[MNE Epochs](https://mne.tools/stable/generated/mne.Epochs.html)。
- W3C PROV 将 entity、activity、generation/usage/derivation 分开，支持结果证据绑定其输入实体版本；它不提供 EEG 选择授权或试次数 guard：[PROV-DM](https://www.w3.org/TR/prov-dm/)。
- plan repair 研究区分从头重规划与保留旧计划内容，说明状态偏离后“最小扰动”是独立目标，但没有定义 EEG 科学有效性：[Plan Stability](https://strathprints.strath.ac.uk/2776/)。
- 科学工作流系统用依赖 DAG、增量重跑和 provenance 管理派生结果，说明内容相同的输入可支持安全复用；这类 build/workflow 机制本身不是 Agent 创新：[Snakemake](https://snakemake.org/)。
- CogEEGAgent 将 LLM 解释与 deterministic typed contract/commitment/evidence release 分权；CIEDG 与其重合于 deterministic authority，但本轮关注运行中 Epoch artifact/evidence 版本与 residual repair，不声称 typed contract 本身新颖：[CogEEGAgent](https://arxiv.org/abs/2607.25045)。

## 4. 候选路线

### 路线 A：继续扩展 v1 的过程式状态机

为 `epoch_summary` 新增字段和 if/else，在 artifact 失效处追加目标名。

- 优点：实现最短，运行路径直观。
- 缺点：每新增 consumer 都要修改 action、状态、失效和 answer 四处；无法检验维护扩展价值。
- 判断：仅适合作为简单强 Expert 的实现方式，不作为 v1.1 候选核心。

### 路线 B：完整动态 plan repair

每次状态变化重新生成完整 Goal DAG，再用旧/新计划匹配保留步骤。

- 优点：能复用已有 Plan 表示，适合复杂拓扑变化。
- 缺点：计划匹配需要参数、artifact、效果等价判定；对当前六个事件操作过重，容易复制第二套规划系统。
- 判断：暂不采用；若未来出现替代变换与多条等价路径再考虑。

### 路线 C：契约索引的证据依赖图（选择）

有限 `GoalContract` 表声明工具与输入角色；运行时保存 `GoalEvidence` token，并从 token/artifact binding 自动推导失效传播和 ready frontier。

- 优点：对当前规模足够紧凑；新增 consumer 是一条 contract；状态/失效可审计；仍经真实 Executor。
- 缂点：selection identity/derived 仍需 EEG 专属 resolver；它不是任意 workflow search。
- 判断：最符合毕业论文最短可行路径，并能与过程式强 Expert 做公平维护/恢复诊断。

## 5. 表示

### 5.1 GoalContract

```text
goal_name
tool_name | deterministic_resolver
role: observation | producer | evidence | transition | consumer
input_policy: none | source_epochs | effective_epochs
base_dependencies
priority
answer_required
```

初版 contract：

| goal | operation | 输入 | 依赖/作用 |
|---|---|---|---|
| observe_events | list_events | 无 | 观察事件空间 |
| create_epochs | create_epochs | record/events | 产生 source Epoch |
| epoch_quality | epoch_quality | source | 产生质量 evidence |
| trial_selection | resolver/select_quality_epochs | source | 依赖 quality+授权；identity 或 derived |
| epoch_summary | epoch_summary | effective | 返回当前试次、窗口、fingerprint 摘要 |
| event_bandpower | event_bandpower | effective | 返回绝对频带功率 |

`effective` 是动态别名：请求了 selection 时指向 selection token 的输出，否则指向 source Epoch。consumer 无需知道具体筛选分支。

### 5.2 GoalEvidence

每个完成目标保存：

- goal/tool/request ID；
- canonical action signature；
- 输入 artifact ID/fingerprint；
- 输出 artifact ID/fingerprint（若有）；
- 依赖 token 的版本签名；
- ToolResult 地址或 identity transition；
- selection mode、阈值状态等必要科学条件。

token 有效当且仅当其所有 artifact binding 当前存在且内容一致、依赖 token 仍有效、冻结参数签名不变。

## 6. 动态算法

```text
compile requested objectives → dependency closure
while budget remains:
    snapshot each relevant artifact fingerprint once for this frontier
    invalidate evidence whose artifact binding changed/disappeared
    transitively invalidate tokens depending on invalid evidence
    restore content-addressed cached evidence only if full signature matches
    if scientific guard is unsatisfiable: typed stop
    ready = pending goals whose dependencies are satisfied
    choose deterministic (priority, goal name) frontier
    resolve effective artifact and construct expected-fingerprint arguments
    execute via existing ExecutionContext → Executor → ToolRegistry
    on success: materialize GoalEvidence
    on transient: retry only frontier
    on artifact-state conflict: reconcile graph within repair budget
    on permanent error: typed stop
```

## 7. EEG-specific invariants

1. label/window/source/objectives/authorization 在运行中不可变。
2. quality 永远绑定 source Epoch，不从选择后数据反向证明选择合法。
3. selection 必须有明确授权和同一 source fingerprint 的质量 evidence。
4. 任一请求条件的 usable count 为零时，不能静默只分析剩余条件。
5. consumer 只能读取当前 effective Epoch；summary 与 bandpower 必须报告相同 artifact ID/fingerprint。
6. 内容改变必须撤销依赖结果；仅 ID 丢失后重建出相同内容时，是否复用 consumer 证据必须由完整内容/参数/依赖签名决定。
7. 经验质量阈值不是临床真值；event bandpower 不是 ERD/ERS。

## 8. v1 → v1.1 的确切算法变化

| v1 | v1.1 |
|---|---|
| 专用实例变量表示目标完成 | `GoalEvidence` 表统一表示 |
| 手写 action 顺序 | contract closure + ready frontier |
| 手写失效目标列表 | artifact binding + token dependency 自动传播 |
| 一个 consumer | summary 与 bandpower 并列 consumer |
| 每处分别决定 source/selected | `effective_epochs` 动态输入策略 |
| artifact conflict 永久停止 | 有界 state-conflict reconcile |
| 每次调用可能重复 hash | 单 frontier 内 fingerprint snapshot；不跨 frontier 不安全缓存 |

内容地址 evidence cache 是待实际失败探针后决定的候选修订，不在实现前预设一定需要。

## 9. 与 Issue #8 原型的区别

Issue #8 的 `research/semantic_planning` 有独立 Profile、Registry、Executor 适配和假设性 scientific operations，研究的是通用语义操作组合。v1.1 不复用其运行时：

- 只编排生产 Harness 已注册工具；
- artifact 是真实 `ExecutionContext.artifacts`；
- contract 只描述 residual goal/evidence dependency，不重新描述数值算法；
- 核心研究对象是运行时证据失效和最小修复，不是开放式路径搜索。

## 10. 研究声明边界

CIEDG 是方法候选，不是已证创新。它可能提供的可量化价值是：新增 consumer 的方法特定修改点、状态失效后的必要重算数、陈旧 evidence 错误与 trace 可解释性。若强 guarded Expert 在相同代码改动和重放成本下等价，本方法应定位为工程组织方式，不能以成功率包装为规划创新。
