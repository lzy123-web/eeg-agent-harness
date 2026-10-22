# 研究点一最小原型设计

## 1. 定位

实现位于 `src/eeg_harness/research/semantic_planning/`，明确标为研究原型，不替换 Baseline v1 的 `planning.py`、工具或 CLI。原型复用生产 `EEGRecord`、`EventSet/EpochSet`、`ToolSpec/ToolRegistry`、`Executor` 与 `ExecutionContext`；科学操作仍通过既有结构化校验、ToolResult、session artifact 和 ExecutionTrace 执行，没有另建绕开 Executor 的执行器。

规划层与执行层分开：规划层只读取不可变语义元数据；波形保存在 `ArtifactPayload` 的会话内值中，不进入 plan、日志或外部模型上下文。

## 2. 对象与语义

### `SemanticArtifact`

不可变记录：artifact 类型、stage、root/parents lineage、真实采样率、参考、声明通带、通道、时间参考、事件对齐来源、事件标签/条件数、滤波历史、筛选历史、observability 和其他显式属性。

- `unknown` 表示没有来源支持；
- `false` 表示已知不满足；
- `true` 表示有显式来源支持；
- 处理后分支不会继承 `raw_line_noise=true`。

`ArtifactPayload` 将元数据与实际 `EEGRecord/EpochSet/feature` 绑定在当前 `ExecutionContext.artifacts`。公开 summary 只返回元数据。

### `SemanticEffect`

每个操作同时声明通用的 consumes/produces/preserves/changes/invalidates，以及独立的 `scientific_semantics`。这样可以区分 JSON schema 或类型相容与“该频率仍可测”“事件和重采样坐标共同变换”等 EEG 科学条件。

### `ScientificRequirement` 与 `SemanticPlan`

Requirement 保存用户目标的固定参数；Planner 无权改写标签、通道、时窗、目标频率、目标采样率、筛选授权或最小试次数。Plan 是带输入/输出 artifact ID、操作参数和有效性证据的 DAG 线性拓扑序；多目标可保留同源多分支。

## 3. 操作契约

| 操作 | 输入→输出 | 关键科学约束 |
|---|---|---|
| `sp_lowpass` | record→record | Nyquist 必须覆盖 cutoff；产生新分支；使原始工频 observability 失效 |
| `sp_resample_with_events` | record→record | 必须有 events；MNE `Raw.resample(events=...)` 联合变换；保留非零量化容差 |
| `sp_create_epochs` | record→epochs | 标签必须存在；目标 sfreq/所需滤波满足；窗口合法；绑定 event lineage |
| `sp_select_epochs` | epochs→epochs | 只接受用户显式授权和输入 artifact 当前索引；记录排除规则 |
| `sp_line_noise` | raw record→feature | raw 来源且目标频率在 Nyquist/声明通带内；unknown 不当 false |
| `sp_bandpower` | record→feature | 频带可测；如目标要求 40 Hz 处理分支则不能偷用 raw |
| `sp_condition_feature` | epochs→feature | 每标签试次满足最小数；输出绑定精确 Epoch artifact |
| `sp_epoch_variance` | epochs→feature | 扩展 consumer；与 condition feature 使用同一通用 Epoch 前置条件 |

阈值不由 Planner 发明。50 Hz 案例只测注入频率的连续值与来源，不把经验阈值当临床质量真值。

## 4. 三种方法

1. **Strong Expert Conditional DAG**：手写完整领域决策，支持已有/新建处理分支、重采样、Epoch、授权选择与试次数检查；它读取同一契约，不被刻意削弱。
2. **Generic Semantic Workflow Planner**：对同一 typed artifact 和 operation contract 做 domain-neutral breadth-first composition，不包含 EEG 专属路径代码。
3. **Candidate EEG Semantic Planner**：使用相同搜索与真值，只增加 EEG 目标相关的操作排序。它不能获得额外 metadata、预算或绕过 Executor 的权限。

候选当前并非复杂新算法；这种最小差异是有意设计的。如果通用 BFS 已足够，实验应得出 No-Go，而不是增加功能制造差异。

## 5. 三个科学场景

### 原始/处理分支

合成 raw 同时注入 10/6 Hz 信号与 50 Hz 成分。line-noise 必须来自 raw artifact；bandpower 若要求 40 Hz 低通则来自独立 processed artifact。只有 filtered artifact 时原始工频目标拒绝，且不把低值解释为“原始噪声低”。

### 重采样与事件

源 events 先以原始秒时刻生成，执行时转换为原采样格点，并通过 MNE 与 raw 联合重采样。独立 oracle 用注入秒时刻比较输出 `event_onsets_seconds`，容差为半个目标采样周期；该容差是当前合成条件的验收界限，不是普遍误差保证。

### Epoch/筛选 lineage

Epoch 用已有 `create_epoch_set` 创建。选择操作从具体输入 artifact 的当前索引派生新 artifact；feature 必须引用选择后的 ID。未授权选择拒绝；任一目标条件的试次不足拒绝。合成坏 Epoch 只用于确定排除索引，不把幅值规则当临床标签。

## 6. 与现有组件的差异

- 现有 `planning.py` 面向注册工具依赖、Profile、资源和动态恢复；本原型面向信号处理后科学语义、分支和 lineage。
- 现有 `quality.py` 测量当前 artifact；本原型决定某项证据能否从该 artifact 合法提出。
- Executor 继续负责结构化 schema/Profile/异常边界；Planner 拒绝与 Executor 拒绝分别计数。
- 没有 LLM、ASD、诊断、模型训练或研究点二策略。

## 7. 当前硬编码与限制

- 仅有 record、epochs、feature 三种 artifact 和 8 个研究操作；不是通用 EEG ontology。
- Candidate 的 EEG 专属部分只是排序启发式，科学知识主要在共享契约中。
- Expert 是单开发者实现；维护成本测量只能报告修改文件/修改点/LOC，不能代表多人项目工时。
- 合成数据不能验证真实设备滤波、触发漂移、参考变换或真实伪迹。
- 当前 plan 是 DAG 的拓扑序表达，没有并行调度、缓存、恢复或跨进程 artifact 存储。
