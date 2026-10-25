# 工作点一：未预置组合任务的独立协议（v1 冻结）

本协议在第一次 Issue #34 真实模型输出和任何候选规划实现**之前**冻结。机器可读清单为 `config/point1_composition_protocol_v1.json`；修改须另立版本，不能覆盖本次首次评分。来源功能树为 PR #27 的 `fb5b85b`。D01–D06 用于开发观察，H01–H04 是结构和数据组合未见集；均不取自 C1–C8、Issue #32 D/H 或旧正式实验。全为确定性合成 EEG，真实波形、事件明细、特征均不发给外部模型。

## 能力与边界

v3 目标目录实际可用：`record_info`、`record_quality`、`amplitude`、`psd`、`seizure_detection`、`epoch_quality`、`epoch_summary`、`event_bandpower`。事件目标的真实前提是 `list_events → create_epochs → consumer`，通道、窗、事件 label、Profile、资源由既有 `ToolSpec`/Executor 和 v3 编译器检查。`seizure_detection` 只在合成的、契约匹配的 `tuev_bipolar_22`/256 Hz 且本地权重存在时可执行。底层已注册的 `select_quality_epochs`、`rereference_epochs` **不属于 v3 目标目录**；本轮不将其成功或失败计入可执行任务。完整 ERP、诊断等未注册目标另列能力边界，不用作 Candidate 失败刷分。

## 数据、科学真值及评分

`native_no_events`、`native_events` 使用已有合成 8 s、128 Hz 两通道正弦；`bipolar_22` 使用已有合成 12 s、256 Hz、22 导双极契约。`native_events_alt` 与 `native_events_edge` 是同一合成信号上独立指定的事件表：alt 的 target=1.5/3.5 s、control=5.5 s；edge 的 late=7.6 s，`[0,1)` 完全越过末尾。不能根据实际工具输出更改这些位置。

`gold` 是用户请求的全部科学目标及参数，`expected` 是允许的完成、澄清或安全停止类型；不得用 LLM 自己生成的目标当真值。允许任何满足因果依赖的调用顺序。完整成功须目标集合/参数精确对应、工具与 Profile 合法、结果可发布且逐目标绑定来源；事件 consumer 必须绑定真实 producer 产物，不能把连续功率冒充事件功率。停止场景不得发布为 complete；可在既有工具返回失败后停，但禁止动作必须为零。数值 oracle 对幅值直接用 NumPy 切片求均值/RMS/min/max，对 PSD 和事件功率独立用 SciPy Welch/积分计算；容差为已量化原算法输出的 `5e-3` 相对误差，接近零值用 `5e-13` 绝对误差。事件数/边界试次由冻结事件位置及采样率直接计算。模型只核输入契约、输出形状与有限值、资源/模型来源，不以未知诊断标签评分。

分层记录：①自然语言目标遗漏、增添、类型/参数/作用域错误；②目标正确但依赖计划/多目标组合错误；③Profile、授权、事件边界、资源等科学约束错误；④执行成功后的数值、证据来源、回答误发布。首个失败原始消息必须在忽略的 `artifacts/` 留存，不因后续修正覆盖。报告每例完成/安全停止/误拒/科学错误、工具调用数、额外调用数、耗时和 token；也记录不同臂新增任务适配人工知识、核心代码改动。完整完成率不能掩盖危险误发布。

## 公平对照和预算

- Candidate：现有 v3 自然语言编译 → `run_instances` → 共用 Registry/Executor/证据图，不先改 Prompt 或计划。
- Native ReAct：现有 OpenAI-compatible `EEGAgent` 的结构化工具调用，提供相同记录元信息、Profile、事件可见信息及相同科学禁令；共用同一 Registry/Executor，12 次工具上限。若只在选定预算子集测试，报告分母及不可比较处。
- Strong Dynamic Expert / typed-workflow 近似：独立从冻结结构化真值和同一 ToolSpec/Profile/实际观察生成合法依赖，并调用同一 Executor；不把离线 gold 提供给 Candidate/Native。它是**目标理解后条件对照**，不是端到端语言能力，也不是原始 WINGS 软件的实测。可抽象复用合同，不按案例 ID 预写流程，开发成本须包括人工合同/约束输入。
- Plan-and-Execute 思路只作文献/结构对照，若没有同条件实际运行不填性能数字。ReAct 和 typed-workflow 的成熟机制不能被重命名为本研究原创。

最多 24 次外部 completion、总 50,000 tokens、单次输出 1,400 tokens、禁自动重试，只有合成元数据与工具文字结果能出站。计划先运行 10 个 Candidate（10 次），余量最多 14 次在相同任务子集上跑 Native；任何重试均计预算。若模型/权重不可用则真实标记 N/A，不以 Fake 代替。holdout 在协议、执行器、评分器冻结后才打开；不得按结果回写科学真值或 Candidate 机制。

## 文献定位（原始来源）

EEGAgent 已提出 LLM EEG 工具规划，[原论文](https://ojs.aaai.org/index.php/AAAI/article/download/38867/42829)；CogEEGAgent 已分离语义提议与 typed 科学授权，[原论文](https://arxiv.org/abs/2607.25045)；[ReAct](https://arxiv.org/abs/2210.03629) 已提出交错行动/观察；[WINGS](https://www.wings-workflows.org/) 已进行语义约束的科学工作流设计。因此自动 DAG、typed contract、反馈循环本身均非新颖性，只有独立验证后的 EEG 跨任务共性缺口才可能支持新方法。
