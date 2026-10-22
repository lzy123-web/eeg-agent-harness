# 研究点一：EEG 科学语义约束规划文献与问题核对

## 1. 核对范围与结论

本报告对应 Issue #8 的阶段 A。检索日期为 2026-10-22；外部依据限定为可核对的论文页面、论文正文和官方 API 文档。当前可证伪问题不是“科学工作流是否能使用语义约束”（已有工作已经回答可以），而是：在共享科学规则、状态、工具、预算和 Executor 边界时，EEG 专属规划策略能否在未预写完整流程的组合任务上，比强 Expert Conditional DAG 和通用语义工作流规划器带来额外正确性或更低维护成本。

阶段 A 在任何新原型运行前完成以下冻结：18 个合成任务（development 12、holdout 6）、三类科学 oracle、三类主对照和统一预算。冻结文件为 `config/point1_semantic_planning_v1.json`，规范化 JSON SHA-256 为 `1e2de202eb91b76e3df32e133ad4bf37578be74d506f15b302b1a39d4ffb5d47`。Executor 拒绝单独记为“运行时安全拒绝”，不记为“语义不合法操作已经成功执行”。

## 2. 可核查前人工作

### 2.1 CogEEGAgent

- 真实题名：*CogEEGAgent: Toward Autonomous Cognitive EEG Analysis with Grounded Execution and Selection-Aware Verification*，arXiv:2607.25045，v1，2026-07-27：<https://arxiv.org/abs/2607.25045>。
- 已有机制：论文把语言语义权限与科学权限分开；LLM 选择注册分析，确定性组件验证 typed contract、控制 confirmation access，并在证据绑定后决定 release。摘要明确报告 prespecified routing benchmark、matched preflight、participant-disjoint confirmation 和 policy stress test。
- 已验证场景：正文及补充材料报告认知 EEG 的 ERN、N400、MMN 注册分析，以及 outcome-blind campaign。其论证重点是选择后验证、确认集隔离和 fail-closed release，而非任意预处理 DAG 搜索。
- 未验证范围：论文没有证明面向任意 EEG 数据变换的自动组合优于同规则通用语义 planner，也没有覆盖本 Issue 的原始/滤波分支、重采样事件坐标和 Epoch 选择 lineage 三项组合基准。
- 可证伪区别：本研究候选不主张替代预注册/confirmation control；只测试“数据语义状态 + 操作效果”能否在相同规则下改进跨步骤组合。若通用 planner 或强专家读取同一契约即可同样完成，独立规划贡献不成立。

### 2.2 NeuroWeaver

- 真实题名：*NeuroWeaver: An Autonomous Evolutionary Agent for Exploring the Programmatic Space of EEG Analysis Pipelines*，arXiv:2602.13473，当前页面为 v4，2026-09-05：<https://arxiv.org/abs/2602.13473>。
- 已有机制：把 EEG pipeline engineering 表述为离散约束优化；Domain-Informed Subspace Initialization 限制到神经科学上较合理的搜索子空间，多目标进化优化平衡性能、新颖性和效率，并由 LLM 生成可执行代码。
- 已验证场景：论文页面报告五个异质 benchmark 的轻量 pipeline 合成。这里仅引用作者报告，不在本仓库复现或重新确认其指标。
- 未验证范围：其目标是 pipeline/code optimization；没有从论文摘要证实它专门解决“同源多分支证据不可混用、事件时间坐标 lineage、筛选前后 Epoch 证据绑定”。本轮已取得 arXiv 页面和正文入口，但未复现其代码与实验。
- 可证伪区别：本研究固定操作与科学目标，不优化预测指标，也不允许根据结果挑数据；只比较状态/lineage 驱动的合法组合。若领域契约本身而非 EEG 专属规划策略解释结果，则应给出 No-Go。

### 2.3 WINGS 与通用 provenance

- WINGS 官方说明：<https://wings-workflows.org/>；代表论文 *Wings: Intelligent Workflow-Based Design of Computational Experiments*（Gil 等，IEEE Intelligent Systems 26(1), 2011）列于官方 readings：<https://wings-workflows.org/readings.html>。
- 已有机制：WINGS 用数据和组件的语义约束生成、验证工作流，并为新数据产品生成元数据。Wings/Pegasus 的 provenance 工作还区分应用级语义来源与执行映射来源：<https://doi.org/10.1002/cpe.1228>。
- 已验证场景：公开工作覆盖大型分布式科学工作流与多领域应用；因此“typed artifact + pre/postcondition + 自动 DAG + provenance”本身不是本研究的新颖点。
- 未验证范围：这些材料没有给出本轮三个 EEG 场景上的强 EEG 专家公平对照。
- 可证伪区别：候选只有在共享同一 typed artifacts/规则的通用 planner 不能达到相同性能，而差异能归因于可复现的 EEG 规划策略时，才可能有额外贡献。
- provenance 标准：W3C PROV-O 是 2013 Recommendation，提供 Entity/Activity/Agent 等可扩展 provenance 语义：<https://www.w3.org/TR/prov-o/>。本原型只采用最小 lineage 思路，不声称实现完整 PROV-O。

### 2.4 MNE 官方数据语义依据

- `Raw.resample`：官方文档警告连续数据下采样会造成 trigger timing jitter；若必须重采样连续数据，应先从原数据构造 events，并通过 `events` 参数与 raw 联合重采样：<https://mne.tools/stable/generated/mne.io.Raw.html#mne.io.Raw.resample>。因此本研究 oracle 使用原始秒时刻作为独立真值，并允许由目标采样格点决定的非零容差，不宣称普遍零误差。
- 滤波/频率适用性：MNE 的 filtering/resampling 教程说明滤波改变信号频谱，重采样会应用抗混叠处理：<https://mne.tools/stable/auto_tutorials/preprocessing/30_filtering_resampling.html>。因此 1–40 Hz 分支的 50 Hz 值不能被称作原始 50 Hz 噪声证据；“不可观测”不能被替换为 false。
- Epoch 筛选：`Epochs.drop_bad` 以声明的 peak-to-peak/flat 规则丢弃 Epoch，且一旦丢弃不可恢复；`Epochs.drop` 的索引指当前未丢弃集合，不必等同外部事件索引：<https://mne.tools/stable/generated/mne.Epochs.html#mne.Epochs.drop_bad>。
- Epoch metadata：`Epochs` metadata 行数必须与 events 相等，子集化时 metadata 与 selection 同步：<https://mne.tools/stable/generated/mne.Epochs.html>。因此筛选前后试次数、条件标签和选择记录必须绑定具体 artifact。

这些 API 是实现语义边界的依据，不是方法优越性的证据。滤波参数、质量阈值和任务合法性仍需由具体实验协议确定。

## 3. 仓库现状与不重造边界

已有可复用机制：

- `record.py::EEGRecord`：显式数组、真实采样率、通道、处理元数据与严格切片；
- `events.py::EventSet/EpochSet/create_epoch_set`：秒时间坐标、边界拒绝、标签与 Epoch artifact；
- `tooling.py::ToolSpec/ToolRegistry`、`executor.py::Executor`、`context.py::ExecutionContext`：schema/Profile/资源校验、会话 artifact、结构化 ToolResult 与 Trace；
- `planning.py`：现有工具依赖与动态状态 Pilot，已证明与公平强专家结果持平；
- `quality.py`：明确 valid/unknown/not_observable 的质量证据，但阈值未临床校准；
- `provenance.py`：对外只暴露哈希化来源引用。

本轮原型必须隔离于 `eeg_harness.research.semantic_planning`，通过现有 Executor/Context 执行，不替换 Baseline v1，不修改其冻结配置与历史结果。

## 4. 冻结假设与反例

### H1：组合正确性

在相同科学规则、数据状态、工具和预算下，候选 EEG Semantic Planner 能自动组合未预写完整流程的新任务，并相对强 Expert Conditional DAG 与通用语义 Planner 减少“成功执行但科学语义不合法”的计划，同时不显著增加误拒。

反例：若强 Expert 或通用 planner 从同一操作契约自动获得相同分支、顺序与拒绝，则 H1 不支持；Executor 最后拦截错误也只能算运行时拒绝，不能伪装为 planner 正确。

### H2：扩展维护成本

接入一个合理的新 producer/consumer 或 transform 时，候选方法需要更少的人工规则改动（文件、修改点、有效代码行），且完成率、调用数与延迟不明显劣化。

反例：若通用 planner 同样只增加声明式契约，或强专家读取同一契约后无需专用分支，则没有 EEG 专属维护优势。单开发者 LOC 只作为弱证据，不外推团队工程成本。

## 5. 冻结任务、oracle 与分层

- 任务：18 项，覆盖 raw/1–40 Hz 分支、重采样/事件对齐、Epoch/选择 lineage；含合法、不可观测、未授权、试次不足、组合与新 consumer。
- 预算：每例最多 8 个工具调用、8 次状态查询、1 次恢复；三种方法相同。
- 主对照：完整领域规则的强 Expert Conditional DAG、同 typed artifacts/pre/postconditions 的 Generic Semantic Workflow Planner、Candidate EEG Semantic Planner。
- 独立 oracle：直接读取合成源注入参数与实际数组；事件误差以原始秒时刻对照执行后时刻；Epoch oracle 从原始事件、边界、明确排除索引独立重算标签和数量；不读取 planner 自报“合法”标签评分。
- 分层结果：plan-time reject、executor reject、completed-valid、completed-invalid、budget exhausted、internal failure。核心错误只计 completed-invalid；两种 reject 分开报告。
- 指标：合法完成、正确拒绝、误拒、实际语义非法执行、branch/lineage、对齐误差、holdout/未见组合、调用/查询、延迟及扩展改动。

该冻结不是正式 preregistration；它是首次原型结果产生前的仓库内协议锁定。
