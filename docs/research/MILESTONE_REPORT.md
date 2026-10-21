# EEG Agent Harness 基础运行时 MVP 里程碑报告

## 范围与边界

本里程碑按 A→B→C→D 建立通用 EEG Harness 基础运行时。它不包含 Constraint Planner、Evidence-Driven Policy、ASD 评估、模型训练、RAG 或新增数据集验证。原始 EEGAgent 的许可证状态仍未明确，本项目不据此声明可自由再许可。

## 阶段 A：TaskProfile 与通用数据适配

状态：已完成。

- 新增通用 `TaskProfile`、`tuev_bipolar_22` 和 `edf_native`。
- EDF 读取与 Profile 适配分离；原生 Profile 保留选定 EDF EEG 通道及原始采样率。
- 22 导 Profile 继续使用原滤波、陷波、重采样和双极派生逻辑，真实样例输出仍为 `(22, 61696)`、256 Hz。
- 癫痫工具兼容性绑定到 `tuev_bipolar_22`，不通过通道数量推断适用性。
- `compileall` 通过；15 项测试通过，包含缺导、错误采样率、Profile 不兼容和两类真实 EDF 适配测试。

Commit：`4c07b20`（`实现 TaskProfile 与 EDF 数据适配`）。

## 阶段 B：Tool Registry 与 Executor

状态：已完成。

- 建立 `ToolSpec`、`ToolRequest`、`ToolResult`、`ToolRegistry` 和统一 `Executor`。
- 注册基础信息、幅值、PSD、癫痫推理四个标准工具；Native Profile 只暴露前三个。
- Registry 查询只返回工具元数据，不加载模型权重；癫痫权重仅在对应工具实际执行时惰性加载。
- Executor 在算法调用前校验 Profile、参数、通道、时间窗、采样率和模型资源。
- 所有结果均可 JSON 序列化；错误以稳定错误码返回，不向上层暴露 traceback。
- `compileall` 通过；22 项测试通过，包含真实 EDF 与真实权重的 Executor 推理。

Commit：`a27b16c`（`建立工具注册与安全执行器`）。

## 阶段 C：执行状态与可复现工作流

状态：已完成。

- 新增每任务独立的 `ExecutionContext`，持有 `EEGRecord`、Profile、Executor、结果映射和调用历史。
- `ExecutionTrace` 记录序号、工具、解析后参数、校验/执行状态、输出摘要、耗时、结构化错误和终止原因。
- 支持通过显式 `$result` 引用读取前一步结果；引用不存在或路径错误时返回 `RESULT_REFERENCE_ERROR`，不推断数据转换。
- 新增确定性 Workflow 与 CLI：EDF → 基础信息 → PSD →（仅兼容 Profile）癫痫推理。
- Reproducibility bundle 保存 Profile、采样率、通道、shape、处理步骤、配置、请求、结果和 Trace，不保存原始 EEG 数组。
- `compileall` 通过；27 项测试通过，包含上下文隔离、结果引用、非法工具后恢复、轨迹序列化和真实多工具工作流。

Commit：`1450179`（`实现可追踪多工具执行上下文`）。

## 阶段 D：LLM Agent Loop

状态：已完成 Fake LLM 与客户端实现；真实外部 LLM 取决于本地环境配置。

- 新增有界 `EEGAgent` 循环，使用 OpenAI 兼容 Chat Completions 的原生 `tool_calls` 结构，不使用文本正则协议。
- Agent 只发送 Profile、采样率、时长、通道、参考、montage、shape、工具定义和工具结果，不发送 EEG 原始数组。
- 支持最大轮数和最大工具调用数；工具错误回注模型后可继续，LLM 异常和调用上限具有明确停止原因。
- API Base URL、API Key、模型名和超时均从 `EEG_HARNESS_LLM_*` 环境变量读取，无硬编码凭据或模型名。
- 内置 `DemoFakeLLM` 完成基础信息、频带功率和符合条件的真实癫痫模型三类闭环；Native Profile 会拒绝癫痫工具。
- `compileall` 通过；32 项测试通过，包括 Fake LLM 闭环、真实权重推理和工具调用上限。

Commit：`d51de85`（`接入结构化工具调用 Agent Loop`）。

## 最终验证

- `python -m compileall -q src tests`：通过。
- `python -m unittest discover -s tests -v`：32 项通过、0 失败、0 跳过（本地已显式提供现有 EDF 与权重）。
- 清除资源环境变量后重复运行：23 项通过、9 项资源测试按设计跳过、0 失败，证明核心运行时测试不依赖本地 EDF 或权重。
- 确定性 Workflow CLI 成功生成三步 JSON bundle；Fake Agent CLI 成功调用真实癫痫工具并生成 JSON 结果。
- LLM 环境检查：Base URL、API Key、模型名均未配置，因此真实外部 LLM 端到端状态为“未验证”，未伪造结果。
- EDF、权重和 `artifacts/` 均保持 Git 忽略；相邻原始 EEGAgent 未修改。

## 能力表述边界

上一里程碑结束时，系统具有两个数据适配 Profile、四个工具、统一 Executor、执行 Trace 和可测试 Agent Loop。这表示“一个 Harness 中存在多个 EEG 工具”，不表示已经在多个 EEG 数据集或多种临床任务上完成泛化验证。当前真实数据验证仍只有原仓库提供的单个 EDF 样例；模型训练来源和许可证仍为源码未提供。

## Milestone 2：事件相关 EEG 多任务扩展（Issue #1）

### 阶段 A：稳定化与测试基线

- 基线复测 32 项通过；新增 GitHub Actions，无私有资源运行 compileall 与 unittest。
- 增加数组元素类型、NaN、空窗、额外参数和 Profile 不匹配边界校验。
- Commit：`ec65168`（`阶段A 加固测试基线与参数校验`）。

### 阶段 B：通用事件与 Epoch

- `EventSet` 保存 annotation 标签、相对记录起点时刻、持续时间和来源索引。
- `EpochSet` 保存 `[n_epochs, n_channels, n_times]` 数组、时间窗、采样率、baseline、接受/拒绝试次和参数来源。
- 时间窗定义为 `[event_onset+tmin, event_onset+tmax)`；索引使用 `round(seconds * sfreq)`，越界试次明确拒绝。
- 合成 MNE RawArray 验证事件时刻、shape、baseline、缺失条件、越界和零有效试次。
- Commit：`b33ec14`（`阶段B 实现通用事件与Epoch数据层`）。

### 阶段 C：事件工具与多步执行

- Registry 增至 8 个工具，新增 `list_events`、`create_epochs`、`epoch_summary`、`event_bandpower`。
- Epoch 波形只保存在每任务 `artifact_store`；ToolResult、Trace 与 LLM 只包含 artifact ID、shape、拒绝原因和派生特征。
- 确定性 Workflow 与 Fake LLM 均完成四步事件工具链，非法 artifact 和无事件记录返回结构化错误。
- Commit：`cbcc2ed`（`阶段C 接入事件工具与多步执行`）。

### 阶段 D：多任务验收

- 新增 `eeg_harness.event_cli`，支持明确标记的合成数据确定性/Fake Agent Demo，也允许用户显式提供合法带 annotation EDF。
- 现有癫痫 Workflow、Fake Agent、真实 EDF 和现有权重回归继续通过。
- 全量 46 项测试通过；无资源环境 37 项通过、9 项按设计跳过。
- 本地真实 EDF annotation 数量为 0，因此“真实带事件 EDF 集成验证”为未验证；事件链验证来自合成 MNE 数据。
- 真实 LLM、多数据集泛化、完整 ERP/evoked、临床结论均未验证。

Commit：`524946e`（`阶段D 完成多任务验收与事件Demo`）。

### 多任务能力矩阵

| 能力 | 工具可执行 | Fake LLM 可调度 | 真实 LLM | 多数据集泛化 |
|---|---|---|---|---|
| 22 导癫痫窗口推理 | 是，真实 EDF/权重 smoke | 是 | 未验证 | 未验证 |
| Native EDF 基础特征 | 是 | 是 | 未验证 | 未验证 |
| 事件→Epoch→频带功率 | 是，合成注释数据 | 是 | 未验证 | 未验证 |

## Milestone 3：真实事件验证与 R3 适配（Issue #2）

### 阶段 A：稳定化

- 修复共享 Executor 被后建 Context 覆写 artifact store 的问题，改为每次请求注入会话资源；交错执行和跨任务非法访问均有回归测试。
- 用含 `meas_date/orig_time`、非零 `first_samp`、crop 和 resample 的 MNE RawArray 验证 annotation 转换，继续采用 `[tmin, tmax)` 与 `round(seconds * sfreq)`。
- 非有限 EEG、非有限 baseline、空条件、缺 annotation 和小于 1 秒的 Welch 分析均明确失败。
- Trace 和 bundle 保存 Profile、配置、事件来源摘要、Epoch 参数与拒绝信息，不保存数组和原始路径。

Commit：`f7f95da`（`阶段A 修复会话隔离与事件时间校验`）。

### 阶段 B：R3 应用适配

- 通用 EDF 层新增 configurable-native 预处理，R3 通道与标签规则只存在于 `applications/r3`。
- 本地 69 个 EDF 只读诊断确认统一 21 EEG 通道、300 Hz 和注释 1–9；未从文件确认任务标签含义、分组或标签 9 的科学语义。
- 支持显式外部事件 CSV 及偏移量，保存内容哈希作为来源；不从文件名推断参与者或组别。

Commit：`812a899`（`阶段B 增加通用预处理与R3适配器`）。

### 阶段 C：共用工作流与受试者聚合

- R3 复用 Registry→Executor→ExecutionContext→事件工具链，生成版本、配置、输入哈希与 Trace。
- `event_bandpower` 明确为整段 Epoch Welch 绝对频带功率，不是 ERD/ERS。
- 新增显式映射的受试者聚合，强制“记录→参与者均值→组描述”，避免把 Epoch/记录当作独立受试者。
- 缺少权威参与者映射，真实组间比较未执行。

Commit：`33244ed`（`阶段C 建立R3事件工作流与受试者聚合`）。

### 阶段 D：验收与文档

- 合成测试覆盖时间语义、artifact 隔离、Boundary 规则、baseline、事件和频带特征。
- 两个本地目录各选一个匿名 EDF 跑通完整流程，仅报告去标识计数；没有据目录名宣称临床分组。
- 原癫痫模型、Fake Agent、确定性 workflow 持续回归通过。
- 最终测试数量、CI 和提交状态见 `PROJECT_STATUS.md`；科学边界详见 `R3_INTEGRATION_REPORT.md`。

Commit：`c9af7aa`（`阶段D 完成R3真实事件验收与研究文档`）。

## Milestone 4：状态感知与约束规划先导研究（Issue #3）

### 阶段 A：方法边界与状态模型

- 定义 `TaskSpec`、`EEGStateSnapshot`、`ArtifactSnapshot`、`OperationContract`、`PlanStep/Plan`。
- 状态仅包含当前 Context 已验证事实；artifact 绑定 Context/Profile/记录来源，不包含原始波形或推断质量。
- 设计文档明确区分 Executor 执行时 Validator 与规划时跨工具约束，并预注册公平比较口径。

Commit：`c6a168e`（`阶段A 定义EEG状态与操作契约模型`）。

### 阶段 B：规划与执行联动

- 在原 Registry/Executor/Context 上实现执行前规划、结构化拒绝、事件 artifact 依赖链和最多一次动态重规划。
- 覆盖缺标签、无事件、非法通道/窗口、Profile/采样率不兼容、缺模型资源和跨 Context artifact。
- 原 Workflow、Agent Loop 和工具调用保持向后兼容。

Commit：`a274e5c`（`阶段B 实现状态感知约束规划与有限重规划`）。

### 阶段 C：冻结公平对照

- 冻结 16 项任务（开发/保留各 8），比较 Execution-only、强 Expert DAG、候选 Planner 与三项消融。
- Planner 与 Expert 在静态任务上持平；Planner 只在单个动态 artifact 丢失案例通过重规划取得完成率差异，但总调用更多。
- 结果支持工程可行性，不足以证明创新性或普遍优越性。

Commit：`ac75f7d`（`阶段C 建立冻结任务集与公平规划对照`）。

### 阶段 D：演示、回归与结论

- 新增结构化 JSON/合成 Demo/benchmark CLI，结果包含 Plan、ToolResult、规划轨迹与 ExecutionTrace。
- 真实 EEGAgent 模型窗口与匿名 R3 事件链均经 Planner 跑通；未提交真实数据或特征。
- 真实 LLM 环境未配置，状态为未验证。
- 评估报告结论为“有条件继续，但目前不足以作为已成立的论文创新点”。

