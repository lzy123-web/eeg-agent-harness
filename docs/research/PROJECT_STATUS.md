# 项目状态

## 当前阶段

Issue #13：CCEP v1 方法研发与真实 Agent 集成已完成本轮有界交付。选定机制为 Lineage-aware Residual Scientific Planning（LRSP）；它已实际改变质量反馈后的后续动作并避免全计划重放，但尚未在冻结协议上优于同规则动态 Expert，当前结论为 **可运行研究候选 / 创新性未证实**。Baseline v1.0、CCEP v0 及 Issue #8–#12 历史结果保持不变。

正式项目已成为可独立维护的 Python 工程；审计和复用源仍为本地相邻的原 EEGAgent 只读目录。本阶段没有修改原 EEGAgent 核心实现，也没有复制真实 EDF 或模型权重。

## 已完成工作

- 完成 EEGAgent 目录、38 个 Python 源文件、依赖、配置、数据样例、11 个注册工具和 11 个工具权重的盘点。
- 定位 Agent 入口、核心循环、Prompt、LLM 调用、工具注册、文本解析和工具执行链。
- 梳理默认 EDF 加载、预处理、22 导双极派生、全局数据注册、特征计算和模型推理链路。
- 核对 TUEV、Sleep-EDF 和 MDD 评估/训练脚本及其路径、通道和输入条件。
- 将各模块划分为可直接复用、封装后复用和不建议直接复用。
- 确定第一阶段最小基线：EDF、基础特征、事件检测和 `seizureNormalModel_OneSecond` 推理；ERP 与 ASD 不在第一阶段。
- 建立项目长期规则、源码审计报告和基线计划。
- 初始化 `src/eeg_harness` Python 包、CLI、最小配置、依赖说明、来源与许可状态说明。
- 迁移并最小封装 `polar.py`、`preprocessing.py`、`dataLoad.py`、`registerData.py`、幅值/PSD、RoPE 模型组件及 `seizureNormalModel_OneSecond`。
- 使用显式 EDF/权重路径和惰性模型加载，避免工具发现时加载无关模型。
- 建立标准库 `unittest` smoke test，覆盖真实 EDF、特征、模型输出、JSON 序列化和缺失权重失败。
- 建立 `.gitignore`，排除 EEG 数据、模型权重、密钥、本地资源配置和生成结果。
- 新增通用 `EEGRecord` 数据对象，显式保存二维 EEG 数组、真实采样率、通道名、参考/导联说明、原始来源、处理步骤和来源元数据。
- 新增统一 `EEGRecord.slice` 接口，校验未知通道、负时间、倒置时间、空时间窗、记录越界和采样后空窗。
- 将幅值、PSD、`seizureNormalModel_OneSecond` 及 `pipeline.py` 改为显式接收/传递 `EEGRecord`；正式执行链不再导入或调用 `legacy.register_data`。
- 保留原始预处理、幅值、Welch PSD、模型结构和权重加载算法，未修改相邻原始 EEGAgent 项目。
- 实现 `TaskProfile`，提供 `tuev_bipolar_22` 与 `edf_native` 两种数据适配；加载器与 Profile 分离。
- 初始实现四个标准工具，Milestone 2 扩展至八个；惰性 `ToolRegistry` 和结构化 `Executor` 统一返回 JSON 安全的 `ToolResult` 与错误码。
- 实现任务隔离的 `ExecutionContext`、`ExecutionTrace`、结果引用和确定性多工具 Workflow。
- 实现 OpenAI 兼容原生 Tool Calling Agent Loop、环境变量配置和 `DemoFakeLLM`。
- 新增 Workflow CLI 与 Agent CLI；没有实现候选论文创新机制、ASD、RAG 或新模型训练。
- 增加无私有资源 GitHub Actions，并加固数组元素、非有限数值、空/越界窗口、额外参数及 Profile 不匹配测试。
- 新增 `EventSet`、`EpochSet`、MNE annotation 映射、边界试次拒绝和可选 baseline 校正。
- 新增 `list_events`、`create_epochs`、`epoch_summary`、`event_bandpower`，Epoch 数组只保存在任务 artifact store。
- 新增确定性事件工作流、合成事件 CLI 与 Fake LLM 四工具链；未引入 ASD/TD/R3 标签语义。
- 修复共享 Executor 的 artifact 会话隔离，新增 MNE 绝对时间/crop/重采样样本级回归及非有限值、短 Welch 窗口失败行为。
- 通用 EDF 适配支持显式选导、滤波、陷波、平均参考和可选重采样；R3 专有配置位于 `applications/r3`。
- 新增 R3 资源诊断、单文件事件工作流、外部事件表适配、去标识公开摘要和显式受试者聚合。
- 受试者聚合先在 participant 内合并记录，再进行可选 group 描述；无显式映射时拒绝组间描述。
- 新增结构化任务、EEG 状态快照、工具操作契约、Plan、规划轨迹和有限动态重规划；没有修改 EEG 数值算法。
- Planner 复用原 Registry/Executor/ExecutionContext，能执行前拒绝静态非法目标并构造事件 artifact 依赖链。
- 冻结 16 项开发/保留任务，公平比较 Execution-only、强 Expert DAG、候选 Planner 及三项消融。
- v2 将旧 Expert 保留为无恢复消融，并为强 Expert 与 Planner 配置相同的状态观察、一次恢复和调用预算。
- ToolSpec 新增 Artifact 生产/消费、事件前置条件、状态观察与科学前置条件声明；新增 `epoch_summary` 路径无需 Planner 工具名专用分支。
- 增加五类确定性故障注入、22 项冻结任务集、逐例 JSON 结果和自然语言结构化目标桥；原生 Agent 保持可用。
- 新增 `record_quality`、`epoch_quality` 和 `select_quality_epochs`，输出来源阶段、单位、validity、经验阈值及数据影响，不生成质量总分。
- 新增 EvidenceGoal/Requirement、固定流程、强 Expert 和 Candidate 三策略公平对照；合法替代必须由目标显式授权。
- 冻结并执行 16 个合成质量/覆盖案例；Candidate 与强 Expert 结果和调用数完全持平。
- 加固 `OpenAICompatibleClient`：非思考模式、输出上限、有限重试、usage/finish reason、空 content、多 tool call 和脱敏错误。
- 新增 `llm_smoke`，分别检查配置、网络/认证、结构化工具调用和带 `tool_call_id` 的结果回传。
- 新增无需 EDF/权重的 `agent_cli --demo-synthetic` 真实 LLM 入口；外部服务只接收合成记录元数据、工具 schema 和派生结果。
- 新增四项有界真实 LLM 验收套件与默认跳过的联网测试；CI 不需要密钥。
- 真实 `deepseek-flash` 完成基础信息、指定窗 PSD、事件 artifact 三步链和临床诊断拒绝；脱敏逐例结果已固化。
- 冻结 Baseline v1 的 30 项自然语言任务集、18/12 development/holdout、15 项真实 DeepSeek 子集及独立判定规则。
- 新增统一 Baseline Runner、三种合成场景、总请求/Token 预算、逐例脱敏 Trace 与分层判定；请求不暴露工具名和调用顺序。
- Fake/Mock 30 项全部跑通协议链；真实 DeepSeek 初始严格 3/15，12 项失败均保留并分类。
- 通用最小工具 Prompt 修复后只复测 5 个 development 案例，5/5 通过；holdout 未复测且不再声称未见。
- 本地真实 EDF+权重工作流以及两份匿名 R3 的事件、特征和质量链均复现；真实数据没有进入外部 LLM。
- 核实 CogEEGAgent、NeuroWeaver、WINGS/PROV-O 和 MNE 重采样/Epoch 官方文档，明确 semantic workflow、typed contract、DAG 与 provenance 本身不是新颖性证据。
- 在原型结果前冻结 Issue #8 的 18 个 development/holdout 科学语义任务、独立 oracle、三种公平对照与统一预算。
- 新增隔离 `research/semantic_planning` 原型：不可变 Artifact/Effect/Requirement/Plan、raw/processed 分支、events 联合重采样、Epoch 筛选 lineage 与 8 个操作契约。
- 所有研究操作复用现有 Registry、Executor、ExecutionContext、EEGRecord 与 EpochSet；没有侵入 Baseline v1 执行链。
- Strong Expert、Generic Semantic 与 Candidate 在 18×3 案例上完全持平；Candidate 没有正确性、调用成本或相对 Generic 的扩展维护优势。
- 冻结 24 项科学意图任务与独立 slot gold；真实 DeepSeek 在 11 个可评价 development 案例中出现 1 个未授权事件条件选择。
- 将 5 个 controlled injection 与自然错误分开：5/5 合法执行且离线意图不匹配，但不计作模型错误。
- 在剩余预算内比较两个 holdout：Native/Intent Contract 为 2/2，Strong Preflight 为 1/2；样本不足且候选未优于 Native，停止方法扩展。

## 实际验证结果

最新验证日期：2026-10-23。本轮调用真实 DeepSeek API，但只使用确定性合成 EEG；未向外部服务发送真实受试者数据，未下载数据、未训练模型。

| 检查项 | 结果 |
|---|---|
| Python 源码语法读取 | 38 个 `.py` 文件均可由 `ast.parse` 解析。 |
| 运行环境 | 使用 `C:\Users\Nick\.conda\envs\eegagent\python.exe`；`pip check` 无损坏依赖。 |
| 关键环境 | Python 3.10.17、MNE 1.6.1、NumPy 1.24.4、SciPy 1.10.1、PyTorch 2.14.1+cpu。最小基线不依赖 OpenAI。 |
| 工具注册 | 成功发现 11 个工具。 |
| EDF 样例 | `gped_049_a_6.edf` 原始 250 Hz、33 信号、241 秒。 |
| 默认预处理输出 | `(22, 61696)`、`float32`，目标采样率 256 Hz。 |
| 成功路径 | 幅值、PSD、对称性、单通道癫痫、10 秒慢波/癫痫/背景、整段正常/异常。 |
| Sleep 工具 | 在默认 22 导数据上失败：模型期望 2 导。 |
| MDD 工具 | 在默认 22 导数据上失败：模型期望 19 导。 |
| RAG | BGE-M3 目录缺少 `model.safetensors`/`pytorch_model.bin`，初始化抛出 `OSError`；Agent 可降级跳过。 |
| 外部 LLM | 未执行，未验证 API 可用性、真实工具规划或端到端回答质量。 |
| 现有测试 | 未发现标准 `test_*.py`/`*test*.py` 测试套件；评估脚本会写输出，不在本轮执行。 |
| 改造前 smoke test | `python -m unittest discover -s tests -v`：原有 5 项全部通过。 |
| 显式数据对象回归测试 | 同一命令共 10 项全部通过：新增 5 项覆盖正常切片、无效通道、时间越界、空时间窗和两份记录交替使用的数据隔离。 |
| 正式项目 CLI | 成功生成 `artifacts/baseline_result.json`；该目录被 Git 忽略。 |
| 幅值结果（FP1-F7, 0–1 s） | mean_abs `1.74e-05`、RMS `2.37e-05`、max `2.63e-05`、min `-6.14e-05`。 |
| PSD 结果（FP1-F7, 0–1 s） | delta `1.86e-10`、theta `1.24e-10`、alpha `2.03e-11`、beta `1.56e-12`、gamma `6.96e-13`。 |
| 癫痫模型结果（FP1-F7, 0–1 s） | `Non-seiz=0.0`、`seiz=1.0`；这是现有权重在单一样例窗口的工程输出，不是性能或临床结论。 |
| 模型输入与权重 | 单窗 shape `[1, 256]`；`seiz&normal.pth` SHA-256 `e67a7b7aa958642b4d194c03fe4750995be89150e84b82cf78d662d35831c41b`。 |
| EDF 校验值 | `gped_049_a_6.edf` SHA-256 `9f83f1294724fa04686e9051f085c4a9c0d1fe9854126c3c13c52c25577104cf`；资源未进入 Git。 |
| 改造前后回归 | 使用同一 EDF、权重、`FP1-F7` 0–1 秒窗口比较；输出 shape、256 Hz 采样率、幅值与五频带 PSD 结果、模型概率、EDF 与模型 SHA-256 全部一致，确定性字段无差异。 |
| MVP 完整测试 | `compileall` 通过；`unittest discover` 共 32 项通过、0 失败、0 跳过（已提供真实资源）。 |
| Profile | `tuev_bipolar_22` 输出 `(22, 61696)`/256 Hz；`edf_native` 保留所选 EDF 通道与原始 250 Hz。 |
| Registry/Executor | 当前 8 个工具注册；Native 暴露 7 个，双极 Profile 暴露 8 个；列表查询不加载权重。 |
| Workflow | 基础信息→PSD→癫痫推理三步成功，结果与 Trace 可 JSON 序列化。 |
| Fake LLM | 基础信息、频带功率、真实癫痫权重调用闭环均通过；工具调用上限测试通过。 |
| 真实 LLM | 环境未配置 Base URL、API Key、模型名，故未执行、未验证。 |
| Milestone 2 全量测试 | 46 项通过、0 失败、0 跳过（提供现有 EDF/权重）；无资源环境 37 项通过、9 项跳过。 |
| 合成事件验证 | 128 Hz 合成信号及独立测试信号验证 annotation 时刻、Epoch shape、边界拒绝、baseline 和频带功率可复现。 |
| 事件工具链 | `list_events → create_epochs → epoch_summary → event_bandpower` 经确定性 Workflow 与 Fake LLM 均成功。 |
| 真实带事件 EDF | 本地 `gped_049_a_6.edf` 实测 0 个 annotation；因此真实 EDF+事件集成未验证。 |
| CI | GitHub Actions 执行 compileall 和无资源 unittest，不下载私有 EDF、权重或大型数据。 |
| R3 资源诊断 | 只读检查 69 个 EDF；统一 21 个 EEG 通道、300 Hz、数字 annotation 1–9；单文件事件数范围 40–116、时长范围 108–406 秒。 |
| R3 单文件链路 | 两个目录各取 1 个匿名文件均完成加载→预处理→事件→Epoch→频带功率；事件数分别 96/81，有效 Epoch 60/72，均为工程链路计数。 |
| R3 科学语义 | 标签 1–8、标签 9 Boundary 规则、细动作范式和目录所指人群均无权威实验说明确认，状态为未验证。 |
| 受试者/组分析 | 未发现可采用的显式参与者映射与权威分组表，未执行真实受试者聚合或组间比较。 |
| Milestone 3 测试 | `compileall` 通过；提供 EEGAgent EDF/权重和 R3 样例时 59 项通过；无私有资源时 48 项通过、11 项按设计跳过。 |
| 规划先导对照 | Planner 有效任务完成率 100%、正确拒绝率 100%；Expert DAG 为 83.3%/100%，唯一完成率差异来自单个动态 artifact 丢失案例。 |
| 调用与开销 | Expert 10 次工具调用，Planner 16 次；一次本地描述性平均耗时约 0.157/0.211 ms，不作统计推断。 |
| 消融 | 无状态追踪 66.7%/0%；无重规划 83.3%/100%；仅参数校验 33.3%/0%（完成率/正确拒绝率）。 |
| Planner 真实资源 smoke | 现有 EEGAgent EDF/权重的一秒模型任务 1 调用完成；匿名 R3 标签 1 事件任务 3 调用完成。 |
| 真实 LLM | 三个必需环境变量均未配置，未执行、未验证。 |
| Milestone 4 全量测试 | `compileall` 通过；提供 EEGAgent EDF/权重和匿名 R3 样例时 76 项通过；无私有资源时 65 项通过、11 项按设计跳过。 |
| v2 公平对照 | 强 Expert 与 Planner 均为有效任务完成率 100%、正确拒绝率 100%、2 次瞬态恢复、0 失败；工具调用分别 20/27，未观察到 Planner 结果优势。 |
| v2 消融 | 无恢复 Expert 与无重规划 Planner 的有效完成率均为 77.8%；无状态 Planner 为 66.7%。 |
| Fake 自然语言对照 | 9 条人工模板；结构化目标桥下 Expert/Planner 为 100%，原生 Fake 为 55.6%。这是模板覆盖差异，不是实际 LLM 性能结论。 |
| Milestone 5 全量测试 | `compileall` 通过；提供 EEGAgent EDF/权重和匿名 R3 样例时 98 项全部通过；无私有资源时 87 项通过、11 项按设计跳过。 |
| 真实 LLM | 三个必需环境变量仍未配置，未执行；token/API 成本和自然语言质量均未验证。 |
| 合成质量检出 | 通道注入 TP=7、FP=0、FN=0、TN=9；4 个可测 Epoch 案例的标记数均与注入真值一致。只适用于合成真值。 |
| 证据策略公平对照 | 强 Expert 与 Candidate 均为目标成功率 100%、正确拒绝率 100%、总体正确率 100%、32 次调用；Candidate 无额外价值。 |
| 固定流程对照 | 目标成功率 30%、正确拒绝率 100%、总体正确率 56.25%、25 次调用；仅说明质量门控有用。 |
| 两个匿名 R3 质量 smoke | 前 10 秒均无 flatline 标记；默认 200 µV 下幅值标记 3/0 通道，100/500 µV 下为 6/0 和 5/0，显示阈值敏感；50 Hz 均不可观测。 |
| Milestone 6 全量测试 | `compileall`/`pip check` 通过；有资源 108 项全部通过；无资源 97 项通过、11 项跳过。 |
| DeepSeek 协议探针 | 配置、网络/认证、强制 tool call、tool result 回传全部通过；3 请求、619 tokens。 |
| 真实 LLM 分析闭环 | 3 个真实工具闭环全部成功：`record_info`、`psd`、`list_events → create_epochs → event_bandpower`。 |
| 真实 LLM 安全负例 | 临床诊断请求被明确拒绝；未调用 Native Profile 不支持的癫痫模型，未编造结果。 |
| 事件 artifact 传递 | `event_bandpower` 使用与 `create_epochs` 返回值完全相同的 artifact ID；2 个有效 Epoch、1 个越界拒绝。 |
| DeepSeek 调用成本 | 四案例 9 次请求、5 次工具调用、16,041 tokens；非思考模式，单请求上限 768 tokens。 |
| Issue #6 全量测试 | `compileall`/`pip check` 通过；有 EDF/权重/R3 资源时 116 项通过、真实联网测试 1 项默认跳过；无私有资源时 105 项通过、12 项跳过。 |
| Baseline v1 冻结集 | 30 项：development 18、holdout 12；真实 DeepSeek 固定子集 15；规范化 SHA-256 `e1713cda…4654ae1`。 |
| Fake/Mock Runner | 30/30 协议案例完成；59 次本地 Fake 请求。该结果不作为语言模型性能。 |
| DeepSeek 首次固定子集 | 严格 3/15；37 请求、72,358 tokens。必需工具/禁止动作/结果/参数/artifact/回答检查均通过，12 项因额外工具调用不满足最小集合。 |
| DeepSeek 有界复测 | 通用最小调用 Prompt 修复后，5 个 development 案例 5/5；9 请求、16,819 tokens。holdout 未复测。 |
| DeepSeek 总预算 | 46 请求、89,177 tokens，低于 48 请求/120k tokens 限制；cost 未取得可靠 API 金额，记录为 null。 |
| 本地 EEGAgent 资源 | `[22,61696]`/256 Hz；信息、PSD、癫痫模型全部成功，单窗模型原始输出仍为 `Non-seiz=0.0, seiz=1.0`。 |
| 两份匿名 R3 | 21 通道/300 Hz；事件 81/96、有效 Epoch 72/60；事件频带、记录质量与 Epoch 质量均成功；未解释组别或标签。 |
| Baseline v1 全量测试 | `pip check`/`compileall` 通过；有资源 124 项中 123 通过、1 项联网跳过；无资源 112 通过、12 跳过。 |
| Baseline v1 GitHub Actions | run `39787839835` 对提交 `7c852da` 执行无私有资源测试，结论 `success`。 |
| Issue #8 冻结集 | 18 项（development 12、holdout 6），规范化 SHA-256 `1e2de202eb91b76e3df32e133ad4bf37578be74d506f15b302b1a39d4ffb5d47`。 |
| 科学语义公平对照 | Strong Expert、Generic Semantic、Candidate 均为合法完成率/正确拒绝率/总体/holdout 100%，误拒与成功语义非法执行均为 0。 |
| Issue #8 成本 | 三种方法均 25 次工具调用、19 次状态查询；Candidate 未显示调用优势。 |
| 事件独立 oracle | 最大对齐误差 0.002625 秒，小于冻结容差 0.00390625 秒；只适用于当前合成条件。 |
| 扩展模拟 | 新 `epoch_variance` consumer 的方法特定修改点 Expert/Generic/Candidate 为 2/0/1；单开发者弱证据，不支持 H2 相对 Generic。 |
| Issue #8 全量测试 | `pip check`/`compileall` 通过；有 EDF/权重时 137 项中 134 通过、3 跳过；无私有资源 125 通过、12 跳过。 |
| Issue #8 决策 | 当前 EEG 专属规划排序为 NO-GO；显式科学语义契约只保留为工程机制，不宣称创新点一成立。 |
| Issue #9 冻结集 | 24 项（development/holdout 各 12），真实子集 12；规范化 SHA-256 `53c041d3…d5d4`。 |
| Issue #9 自然 DeepSeek | 12 项运行、11 项可评价、10/11 意图匹配；1 项真实未授权事件条件选择，0 项完整错误链全部成功；30 请求、57,065 tokens。 |
| Issue #9 冻结缺陷 | 1 项 0.6 秒事件窗违反现有工具的最短 1 秒条件；原结果保留并排除，不修改 gold。 |
| Issue #9 人工注入 | 5/5 被 Executor 接受且离线意图不一致；只证明边界，不计为自然模型错误。 |
| Issue #9 最小比较 | 两个 holdout × 三方法；Native 2/2、Strong Preflight 1/2、Intent Contract 2/2；6 请求、4,877 tokens。 |
| Issue #9 总预算 | 36 请求、61,942 tokens，未超过 36 请求/80k tokens；只传合成元数据与派生结果。 |
| Issue #9 决策 | 问题存在性 Conditional Go；当前方法 No-Go/证据不足，不宣称优于原生 Agent。 |
| Issue #9 全量回归 | `pip check`/`compileall` 通过；提供本地 EDF、权重和匿名 R3 样例时 146 项中 145 通过、1 项联网测试按设计跳过。 |

仓库内存在历史 TUEV Agent 与 oracle 汇总文件，但本轮未重新复现。相关数字仅在 `CODE_AUDIT.md` 作为历史产物记录，不作为当前基线实验结论。

### 本轮验证命令

在项目根目录设置 `PYTHONPATH=src`，并用环境变量 `EEG_HARNESS_TEST_EDF`、`EEG_HARNESS_MODEL_PATH` 指向原始 EEGAgent 中的现有 EDF 和权重后执行：

```powershell
& $python -m pip check
& $python -m compileall -q src tests
& $python -m unittest discover -s tests -v
& $python -m eeg_harness.cli --edf $env:EEG_HARNESS_TEST_EDF `
  --model $env:EEG_HARNESS_MODEL_PATH `
  --output artifacts\after_explicit_record.json
```

改造前结果保存在本地忽略目录 `artifacts/before_explicit_record.json`，改造后结果保存在 `artifacts/after_explicit_record.json`；两者仅用于本轮本地回归，没有进入 Git。比较时排除生成时间和运行耗时，确定性字段全部相同。

## Issue #10：工作点一集成方法初版

### 实际代码变更

- 新增 opt-in `research/integrated_method`：Evidence-bound `IntentSpec`、obligation ledger、计划/恢复校验、Evidence Gate 与最终证据回答。
- 复用 `StateAwareConstrainedPlanner`、`ConstrainedPlanRunner`、`ExecutionContext`、`Executor` 与现有工具；没有创建第二套 EEG Core 或执行器。
- `planning.py` 增加可选 plan validator hook，并将授权质量筛选实现为同一 Epoch artifact 上的“先质量证据、后筛选”。默认 native/planning 路径保持不变。
- CLI 新增 `--agent-mode point1`；Fake LLM 用于确定性回归，真实 OpenAI 兼容客户端用于合成 EEG 联网验收。
- follow-up 新增覆盖当前分析类型的科学概念契约：模型声明类型必须与用户原文 span 中的概念集合独立解析结果一致，不使用离线 gold。
- 新增质量证据→授权筛选→派生 Epoch→事件频带功率五工具链，Evidence Gate 校验两级 artifact lineage。
- 最终回答改为证据寻址：LLM 只选择成功 ToolResult 的 request id 与相对 `data` 的 JSON path，运行时解析实际标量并确定性渲染。

### 验证结果

| 项目 | 结果 |
|---|---|
| Fake 单步 | PSD 完成，1 次工具调用，ledger 与 trace 闭合。 |
| Fake 多步 | `list_events → create_epochs → event_bandpower` 完成，artifact lineage 闭合。 |
| 真实 DeepSeek 首轮 | 3/3 安全澄清、0 工具误执行；暴露任意参数 schema 导致的别名/任务类型漂移。 |
| 真实 DeepSeek 修复后 | PSD 与事件链完成；缺事件 label 正确澄清且 0 工具调用。 |
| 联网预算 | 两轮合计 8 请求、10,477 tokens；只使用合成 EEG 元数据和派生结果。 |
| 针对性回归 | 集成+规划 24/24 通过。 |
| 本地资源全回归 | 161 项中 160 通过、1 项联网 opt-in 测试跳过；`pip check`/`compileall` 通过。 |
| 无私有资源回归 | 161 项中 149 通过、12 项资源/联网测试按设计跳过。 |
| GitHub CI | Draft PR #11 run `39814383931` 的安装、compileall 与无资源 unittest 步骤均为 success。 |
| follow-up Fake | 集成方法与 Planner 定向 30/30；单步、事件和质量筛选后分析轨迹均按新回答协议生成。 |
| follow-up DeepSeek | 4 条不同合成请求、5 次执行，真实总消耗 9 次 Provider 请求、19,275 tokens（含首次失败 2 请求/4,925 tokens）；PSD 对抗及两条授权复杂链完成，禁止筛选请求 0 工具澄清。首次复杂链的错误 `data` 路径被安全阻止，接口说明修复后重测完成；其完整未跟踪 JSON 被覆盖，仓库仅保留明确标注的观测失败摘要，不伪造原始响应。 |
| follow-up 完整回归 | `pip check`/`compileall` 通过；167 项有资源测试除 1 项联网 opt-in 外均通过，R3 两项显式资源测试另行通过；无资源 155 通过、12 跳过。 |
| follow-up GitHub CI | Draft PR #11 run `39892152377` 对 `30ae956` 执行公开无资源 `unit-tests`，结论 `success`。 |

真实 LLM 的中文回答存在服务侧历史乱码，因此只确认结构化调用、工具执行和终止语义，不宣称中文可读性通过。方法当前是可运行候选，创新性和相对优势均未证明。完整报告见 `POINT1_INTEGRATION_ACCEPTANCE.md`，后续公平对照和消融见 `POINT1_FUTURE_EXPERIMENTS.md`。

### 本轮提交

- `cb91166`：研究问题、文献差异与方法蓝图。
- `9f55415`：CCEP 最小集成主干。
- `fbf20e6`：事件链、质量证据与受约束恢复。
- `c35b541`：真实模型 schema 失败修复与脱敏轨迹。
- `e1c1b03`：科学来源、数值证据、参数闭合和回答失败审查修复。
- 最终文档本地归档：`de6ac8e`、`d021eb2`。本机 HTTPS 传输中断后，六份最终文档通过受认证 GitHub Contents API 同步到 Draft PR #11，远端内容完整但 SHA 与本地归档不同；后续按状态文件的非强制 merge 步骤收敛历史。

## 未解决问题

1. 当前仅有 `tuev_bipolar_22` 与 `edf_native`；Sleep 2 导、MDD 19 导及完整 ERP/evoked 尚无已验证 Profile/工具。
2. `legacy/register_data.py` 文件仍为迁移来源保留，但正式 pipeline、工具和测试已不再依赖；尚未执行物理删除。
3. 当前 Registry 已避免枚举时加载权重，但尚无插件发现、资源 manifest 和跨进程模型生命周期管理。
4. 已使用 JSON Schema 风格声明和结构化 Tool Calling，但本地 schema 校验器仅覆盖当前 MVP 所需子集。
5. `reflectData` 返回 NumPy 数组，当前消息回注无法直接 JSON 序列化。
6. RAG 主模型权重缺失，报告模板也没有进入当前生效 Prompt。
7. MDD、Sleep、TUEV Agent 评估脚本与默认路径或返回结构不一致，不能直接作为回归测试。
8. 多数本地权重的训练数据、版本、许可证和指标来源在源码中未提供。
9. 已有 CI、四类 CLI、46 项测试和资源型 smoke test，但尚无跨平台锁文件、完整资源 manifest 或多样本回归集。
11. 本地真实 EDF 没有 annotation；事件能力仅在合成 MNE 数据上验证，未验证 EDF+ 或外部注释文件配对。
10. 原始项目没有发现许可证文件；源码和权重许可需在公开分发前确认。
11. R3 预处理与 Epoch 参数已配置化且可复现，但其科学适用性尚需实验方案确认。
12. 当前未包含坏道、伪迹剔除、ICA、evoked/ERP 峰值或统计推断；不得将频带结果解释为诊断证据。
13. 规划先导任务规模小，且 Expert 与 Planner 在所有静态任务上持平；当前证据不足以确认研究创新性。
14. 动态重规划优势只在一个人工状态变化案例出现，真实发生率、自然语言规划质量和更复杂任务扩展性未知。
15. v2 强 Expert 与 Planner 结果持平，当前不能把状态约束规划作为已成立的性能型创新点。
16. 冻结 v2 的 Profile 变化案例在注入前已静态不兼容；动态注入仅由独立回归测试覆盖，这是锁定留出集的已知缺陷。
17. 质量阈值未做跨设备、跨 Profile 或人工质控校准；真实文件结果对 100/200/500 µV 阈值敏感。
18. Evidence benchmark 在 Pilot 策略实现后、首次结果前冻结，不属于方法实现前预注册。
19. 强 Expert 与 Candidate 完全持平，研究点二当前为 No-Go；研究点一也尚未成立。
20. 真实 LLM 仅完成一次 4 案例合成验收；尚无多措辞重复试验、不同模型比较、长上下文、并发或故障率统计。
21. 本次没有通过真实 LLM 调用本地癫痫权重；已验证的是合成 Native 基础/事件工具与不兼容拒绝，不得外推为模型调度性能。
22. Baseline v1 已用合成 22 导输入让真实 DeepSeek 调度本地权重，但输出仅是协议 smoke；真实 LLM+真实 EEG 仍未授权、未验证。
23. 初始严格自然语言结果 3/15，说明多余工具调用仍是明确基线缺陷；5/5 修复结果只来自 development 复测。
24. Issue #8 三种强方法在全部冻结合成案例完全持平；当前无法证明 EEG 专属规划策略的独立贡献。
25. 18 个合成案例、单开发者扩展修改点和一次本地耗时不足以代表真实 workflow、团队维护成本或统计显著性。
26. 原型只覆盖 low-pass、联合重采样、Epoch/显式索引筛选等最小语义；未验证真实触发漂移、复杂参考、ICA、坏段传播或 BIDS derivative lineage。
27. Issue #9 仅观察到 1 个自然意图错误，且后续分析因窗口前提失败；没有“错误链全成功”的自然样本。
28. Stage C 只有 2 个 holdout、单次 DeepSeek 路由决策；词汇 alias 归一在结果后修正并已披露，不能作统计或泛化结论。
29. CCEP 只有单步 PSD、事件多步与缺参三类真实模型验收；没有新的冻结强基线比较，不能声称创新或优势。
30. 当前原文数值校验不支持中文数字、单位换算、范围共指或复杂多意图。
31. 默认 EEGRecord 没有 raw/processed 双分支；raw obligation 只能在来源未显式可观测时安全拒绝。
32. `deepseek-flash` 当前返回的中文文本存在乱码，结构化链路成功不能替代自然语言质量验收。
33. 科学概念契约尚未覆盖否定作用域、开放同义词、单位换算和多意图组合；“禁止筛选但做质量+功率”目前安全澄清，尚不能自动分解为合法替代计划。
34. 证据寻址回答保证数值和条件可追溯，但固定模板的可读性、跨值归纳与复杂科学表述尚未验证。
35. 概念词表、Prompt、schema 和 Validator 本身不是独立创新；CCEP 的潜在贡献仅是 obligation 在意图、派生状态、恢复和回答发布之间的持续保持，仍需公平强基线证据。

## 下一步候选任务

按优先级排列：

1. 按 `POINT1_FUTURE_EXPERIMENTS.md` 冻结全新任务、独立科学 oracle、强 Expert/Generic/Native 公平基线和统计计划，再评价 CCEP；不得围绕本轮三个验收请求添加特例。
2. 将自然语言解析共享实验与端到端实验分开，使用未见 holdout、多次重复、独立标注和不同模型。
3. 建立资源 manifest，记录权重 SHA-256、来源状态、输入契约和许可状态，并扩展 CI Python/平台矩阵。
4. 获取合法的带事件公开数据后建立真实事件回归；实验室真实数据外发必须先获得明确治理授权。
5. Sleep、MDD、ERP 和 ASD 继续后置，必须各自完成 Profile、资源、许可和验证后再接入。
6. 两个候选研究点当前均未成立；后续必须基于文献、独立数据和强基线重新论证，不因工程便利编造贡献。
7. 若重新评估研究点一，先获得独立开发者与真实复杂任务，在新冻结 holdout 上证明通用 semantic planner 无法表达的具体 EEG 差异。

## Git Commit 信息

- 正式项目已初始化本地 Git 仓库；相邻原始 EEGAgent 目录保持非 Git、未修改。
- 正式远程仓库：`https://github.com/lzy123-web/eeg-agent-harness.git`，远程名为 `origin`。
- 后续代码或项目文档变更须在验证后提交并推送；禁止提交密钥、真实 EEG 数据、大型模型权重、本地资源配置和生成产物，禁止未经授权强制推送。
- 代码基线 Commit：`9f235b8`（`建立最小 EEG 分析代码基线`）。
- 基线验证状态 Commit：`e962991`（`记录基线验证与提交信息`）。
- 显式数据链路 Commit：`9e48f99`（`引入显式 EEGRecord 数据链路`）。
- 阶段 A Commit：`4c07b20`（`实现 TaskProfile 与 EDF 数据适配`）。
- 阶段 B Commit：`a27b16c`（`建立工具注册与安全执行器`）。
- 阶段 C Commit：`1450179`（`实现可追踪多工具执行上下文`）。
- 阶段 D Commit：`d51de85`（`接入结构化工具调用 Agent Loop`）。
- 里程碑文档 Commit：`35cfa3e`（`完善基础运行时里程碑文档`）。
- Issue #1 阶段 A Commit：`ec65168`（`阶段A 加固测试基线与参数校验`）。
- Issue #1 阶段 B Commit：`b33ec14`（`阶段B 实现通用事件与Epoch数据层`）。
- Issue #1 阶段 C Commit：`cbcc2ed`（`阶段C 接入事件工具与多步执行`）。
- Issue #1 阶段 D Commit：`524946e`（`阶段D 完成多任务验收与事件Demo`）。
- Issue #2 阶段 A Commit：`f7f95da`（`阶段A 修复会话隔离与事件时间校验`）。
- Issue #2 阶段 B Commit：`812a899`（`阶段B 增加通用预处理与R3适配器`）。
- Issue #2 阶段 C Commit：`33244ed`（`阶段C 建立R3事件工作流与受试者聚合`）。
- Issue #2 阶段 D Commit：`c9af7aa`（`阶段D 完成R3真实事件验收与研究文档`）。
- Issue #2 状态汇总 Commit：`a154941`（`记录Issue 2阶段提交与验收结果`）。
- GitHub Actions run `39606303155` 对 `a154941` 执行无私有资源 compileall/unittest，结论为 `success`。
- Issue #3 阶段 A Commit：`c6a168e`（`阶段A 定义EEG状态与操作契约模型`）。
- Issue #3 阶段 B Commit：`a274e5c`（`阶段B 实现状态感知约束规划与有限重规划`）。
- Issue #3 阶段 C Commit：`ac75f7d`（`阶段C 建立冻结任务集与公平规划对照`）。
- Issue #3 阶段 D Commit：`04e2022`（`阶段D 完成规划演示评估与研究结论`）。
- Issue #4 阶段 A Commit：`f449a0a`（`research: establish fair planning evaluation protocol`）。
- Issue #4 阶段 B Commit：`8d126dd`（`feat: declare planning capabilities and evaluation faults`）。
- Issue #4 阶段 C Commit：`569d288`（`feat: bridge natural language goals to constrained plans`）。
- Issue #4 阶段 D Commit：`c39e847`（`eval: run locked planning and fake language comparisons`）。
- Issue #4 契约复核 Commit：`be0522c`（`refactor: apply artifact contract in expert preflight`）。
- Issue #5 阶段 A Commit：`90569f1`（`feat: establish measurable EEG quality evidence`）。
- Issue #5 阶段 B Commit：`82ea91a`（`feat: add evidence-driven adaptive analysis pilot`）。
- Issue #5 评测冻结 Commit：`79c869f`（`research: freeze evidence benchmark before evaluation`）。
- Issue #5 阶段 C Commit：`4131914`（`eval: compare adaptive evidence policy with strong baselines`）。
- Issue #5 阶段 D Commit：`06a0362`（`docs: conclude evidence adaptive pilot with No-Go`）。
- Issue #6 阶段 A Commit：`f554d68`（`feat: harden real LLM protocol client`）。
- Issue #6 阶段 B Commit：`e155fc5`（`feat: add synthetic real-agent execution path`）。
- Issue #6 阶段 C Commit：`06c8cbe`（`test: validate real DeepSeek EEG tool loops`）。
- Issue #6 阶段 D Commit：`750eb04`（`docs: complete real DeepSeek baseline acceptance`）。
- Issue #7 阶段 A Commit：`e320d3c`（`research: freeze Baseline v1 acceptance scope`）。
- Issue #7 阶段 B Commit：`a8eefd7`（`feat: add frozen Baseline v1 Agent runner`）。
- Issue #7 阶段 C Commit：`44ab04a`（`test: verify Baseline v1 local EEG resource chains`）。
- Issue #7 阶段 D Commit：`9ffb7fd`（`eval: run frozen real DeepSeek Baseline v1 subset`）。
- Issue #7 阶段 E Commit：`ac36b45`（`release: accept EEG Agent Baseline v1.0`）。
- Issue #7 状态补记 Commit：`7c852da`（`docs: record Baseline v1 stage commits`）；GitHub Actions run `39787839835` 成功。
- Issue #8 阶段 A Commit：`f14d20a`（`research: freeze EEG semantic planning protocol`）。
- Issue #8 阶段 B Commit：`c2870eb`（`feat: prototype EEG scientific semantic planning`）。
- Issue #8 阶段 C Commit：`93516be`（`eval: compare semantic planner with fair strong baselines`）。
- Issue #8 阶段 D Commit：`0be719a`（`docs: conclude semantic planning spike with No-Go`）。
- Issue #8 GitHub Actions run `39801900191` 对阶段 D 提交 `0be719a` 执行无私有资源回归，结论为 `success`。
- Issue #9 阶段 A Commit：`2cf441c`（`research: freeze intent-alignment problem and cases`）。
- Issue #9 阶段 B Commit：`57a2b4d`（`eval: run real DeepSeek intent-alignment pilot`）。
- Issue #9 阶段 C Commit：`631b9b5`（`research: compare minimal intent contract on holdout`）。
- Issue #9 阶段 D Commit：`84ed297`（`docs: conclude intent-alignment study objectively`）。
- Issue #10 follow-up 历史收敛：`1bd8e7c`（普通 merge，无文件差异）、`f041146`（记录恢复完成）。
- Issue #10 follow-up 意图类型一致性：`ceabfc4`。
- Issue #10 follow-up 派生质量状态链：`8796c82`。
- Issue #10 follow-up 证据寻址回答：`339aab5`。
- Issue #10 follow-up Fake/真实验证与交付：`3866818`。
- Issue #10 follow-up 失败证据留痕：`1d0d392`。

## Issue #12：CCEP Evidence Phase（2026-10-23）

### 已完成

- 增加独立合成异常 Epoch 真值与 SciPy Welch oracle，通过真实 Registry/Executor 验证筛选前后波形、试次数、artifact 不变性和全部频带值。
- 将固定复合事件类型收敛为 `event_workflow` 与三个原子目标，支持“测质量但禁止筛选，再计算未筛选功率”和“明确授权筛选后计算功率”。
- 冻结 24 项（12 development / 12 holdout）独立协议、权限、oracle、预算和规范化 SHA-256，再运行公平比较。
- 保存共享解析任务对照和两个真实 DeepSeek holdout 的脱敏逐例结果；失败结果没有删除或用于事后调 Prompt。
- 新增研究报告 `POINT1_EVIDENCE_PHASE_RESULTS.md` 与方法决策 `POINT1_METHOD_DECISION.md`。

### 实际验证

| 检查 | 结果 |
|---|---|
| 独立 Epoch oracle | 异常索引 `[1]`；3→2；原 artifact 未变；派生波形逐样本相等；筛选前后全部频带与独立 oracle 一致 |
| 全部异常 | `TOOL_EXECUTION_FAILED`；无空派生 artifact；后续功率不执行 |
| 定向 Evidence Phase | 10/10 通过 |
| 冻结共享任务 | Strong 18/18、CCEP 18/18；科学完成均 10/10；各 55 工具调用、2 重规划 |
| 真实 DeepSeek holdout | Native 2/2；CCEP 1/2；13 请求、34,263 tokens；仅合成 EEG |
| CCEP Evidence Gate | 禁止筛选例通过；授权筛选例在意图层安全澄清，0 工具、无数值发布 |
| 有本地 EDF/权重回归 | `pip check`、`compileall` 通过；180 项中 177 通过、3 项按设计跳过 |
| 无私有资源回归 | 180 项中 168 通过、12 项按设计跳过 |
| GitHub CI | Draft PR #11 run `39906771336` 对 `2d5d9cf` 的公开无资源 `unit-tests` 成功 |

### 研究判断与遗留问题

- CCEP v0 的跨意图、计划、派生状态、恢复和回答 obligation 是实际运行机制，不是单一 Prompt；但本轮没有发现相对同规则强专家的增量收益。
- 真实小样本中 CCEP 因意图 schema 服从问题误拒一例，完成率未超过 Native。当前“CCEP 优于强基线”结论为 **No-Go**；作为 opt-in 安全骨架为 **Conditional Keep**。
- 质量阈值仍未临床校准；真实 LLM 只有两个 holdout；Native 最终回答只做逐例人工数值审核；不能外推真实 EEG、临床或多数据集能力。
- 下一入口应是预先提出并冻结“一次性 preflight 会因执行中状态变化/恢复失效”的动态假设，不再围绕本次 holdout 堆 Prompt 或 validator。

### 本轮提交

- `f5283cb`：真实 Epoch 筛选与独立 oracle。
- `caed65d`：事件原子目标组合。
- `06ab4e9`：冻结 Evidence Phase 协议。
- `aa6b20a`：共享任务公平比较。
- `b705638`：真实 DeepSeek holdout。
- 最终文档与状态提交：`2d5d9cf`；GitHub Actions run `39906771336` 成功。

## Issue #13：CCEP v1 动态科学状态与增量约束规划（2026-10-23）

### 方法与实现

- 比较 partial replanning、scientific-state residual goals、guarded conditional DAG 与 LLM feedback replanning 后，选择 LRSP；guarded DAG 保留为未来强动态基线。
- 新增 opt-in `ConstraintCarryingEEGAgentV1`，冻结一次 Intent/ledger，每轮只从实际 artifact、质量 evidence、每条件计数和剩余目标生成一个 frontier action。
- clean 数据走 identity transition；实际异常且用户授权时才创建派生 Epoch；任一请求条件无 usable Epoch 时在选择前安全停止；禁止筛选时分析原 artifact。
- transient failure 只重试当前 frontier，保留已经有效的事件、Epoch、质量和选择结果。
- `EpochSet` 新增内容 fingerprint；质量 evidence 绑定 artifact ID/fingerprint/阈值；下游工具可检查 expected fingerprint/evidence ID。
- 最终回答在 LLM evidence path 校验后，由运行时确定性披露 derived/identity/no-selection 分支与经验阈值边界。

### 实际验证

| 检查 | 结果 |
|---|---|
| 独立 oracle | one-bad 场景实际 3→2；派生数组逐样本一致；全部通道/频带值与独立 SciPy oracle 一致 |
| 状态分支 | one-bad=`derived`；clean=`identity` 且无伪 artifact；禁止筛选=原 artifact；all-bad=质量后安全停止 |
| residual recovery | 一次受控 bandpower transient：list/create/quality/select 各 1 次，bandpower 2 次，完成 |
| 初版失败探针 | 同 ID 内容改变后仍执行 `select_quality`，`detected=false`；结果已保留在迭代日志 |
| 修订后 | 同一探针回到 `measure_quality`；过期 evidence ID 被结构化拒绝 |
| Fake 固定三例 | 3/3 completed，6 次协议调用，完整轨迹已保存 |
| 真实 DeepSeek 固定三例 | 3/3 completed，6 请求、15,363 tokens；仅合成 EEG；不外推准确率 |
| 全仓无私有资源回归 | 190 tests：178 passed、12 resource-gated skipped；0 failed |
| 敏感信息检查 | v1 代码、文档与结果未发现密钥、本地私密路径或原始 EEG 数组 |
| GitHub CI | `unit-tests` run `39926245053` 对提交 `7e0ac46` 完成，结论 `success` |

### 研究判断与遗留问题

- LRSP 已经是实际运行机制，不是单一 Prompt：工具状态会改变动作，内容 lineage 会撤销旧完成项，恢复不重放无关步骤。
- guarded dynamic Expert 能表达当前同类分支，因此本轮没有证明 CCEP v1 的相对优势或新颖性。当前为“可运行研究候选 / 创新性未证实”。
- 动态语义仅覆盖事件质量、选择和绝对频带功率；阈值未临床校准；artifact store 无跨进程事务；检查后并发变化目前安全失败但不自动恢复。
- 下一步只能在预冻结同信息、同规则、同预算的 guarded Expert/Native/LRSP 协议上比较，并将语言解析错误与运行时规划错误分开。

### 本轮提交

- `b85eef2`：冻结研究设计与恢复状态。
- `d96c764`：接入 LRSP、Fake/oracle/局部恢复测试。
- `36c4adf`：内容 fingerprint、quality evidence binding 与回答条件修订。
- `df334d1`：固定 Fake/真实 DeepSeek 合成轨迹与有界评估入口。
- 最终审查与文档提交：`347bc0d`。
- 状态留痕提交：`7e0ac46`；GitHub Actions run `39926245053` 成功。

## Issue #14：CCEP/LRSP v1.1 契约索引证据依赖图（2026-10-23）

### 方法与实现

- 审计 LRSP v1 固定 Epoch 流程，比较过程式扩展、完整动态 plan repair 和契约索引依赖图，选择 CIEDG。
- 新增 opt-in `ConstraintCarryingEEGAgentV11`；从请求目标生成依赖闭包，使用绑定 artifact fingerprint、参数和上游 token 的 `GoalEvidence` 管理完成与失效。
- `epoch_summary` 与 `event_bandpower` 成为两个共享 effective Epoch 的 consumer；禁止筛选、identity、derived 和多条件零 usable 均由真实状态决定。
- 原型暴露“内容相同的 artifact 重建导致 summary 重放”；修订后增加仅限纯 consumer 的 semantic evidence cache，内容变化反例不会错误复用。
- 新增同规则过程式 strong expert 与 fingerprint 微基准，只作为小型诊断，不冒充正式对比实验。

### 实际验证

| 检查 | 结果 |
|---|---|
| 双 consumer + 独立 oracle | selected Epoch 3→2；summary 与 bandpower 共用同一 artifact；波形和全部频带值一致 |
| 禁止筛选 | 测量质量后两个 consumer 均使用 original 3 Epoch；未调用筛选 |
| 多条件零 usable | `NO_USABLE_EPOCHS_FOR_CONDITION`；筛选与下游 consumer 均未执行 |
| 内容等价 repair | selection 2 次；summary 从原型 2 次降为 1 次；任务完成 |
| 内容改变 repair | cache miss；create/summary 均重算，未发布陈旧证据 |
| 强 Expert 小诊断 | 相同 6 次调用、相同试次数与频带数值；未观察候选优势 |
| Fake 固定三例 | 3/3 completed，6 次协议调用 |
| 真实 DeepSeek 固定三例 | 3/3 completed，6 请求、18,253 tokens；Evidence Gate/answer check 均通过；仅合成 EEG |
| 全仓回归 | `compileall`、`pip check` 通过；199 tests：187 passed、12 gated skipped、0 failed |
| GitHub CI | Draft PR #11 `unit-tests` run `39930738446` 对 `53b5869` 完成，结论 `success` |

### 研究判断与遗留问题

- CIEDG 是真实运行时机制，不是只加 Prompt/Schema；它将科学目标、状态版本、证据依赖与局部恢复连接起来。
- 当前结论为 **Conditional Keep / 创新性未证实**。强 Expert 无故障诊断持平，不能宣称成功率、成本或科学正确性优势。
- 尚未冻结强动态 Expert 的故障恢复正式套件；quality evidence ID 含随机 artifact ID；当前只有 event Epoch 状态族和两个 consumer；全数组 fingerprint 的大规模成本未知。
- 尚不具备直接进入正式大规模公平实验的条件。下一入口是冻结独立协议、实现同恢复预算强 Expert、分层指标，并增加一个不同且科学合法的状态转移族。

### 本轮提交

- `037d2c1`：方法审计、候选比较与设计冻结。
- `c11bb95`：CIEDG 原型、双 consumer 与真实 Agent 集成。
- `ea497ac`：内容寻址 evidence 恢复、反例、多条件与 strong expert 诊断。
- 阶段 D 交付提交：`df59826`（有界 Fake/DeepSeek、完整回归与研究判断）。
- 状态留痕提交：`53b5869`；Issue #14 与 Draft PR #11 已评论，CI run `39930738446` 成功。

## Issue #15：CIEDG 第二科学状态转换与方法冻结（2026-10-23）

### 实现与算法迭代

- 比较显式重参考、重采样、基线校正和 CSD 后，选择“用户授权的显式 Epoch 参考通道减法”；仅开放给 `edf_native`，不默认 average reference，不触碰已验证 TUEV 双极模型链。
- `EpochSet.reference` 进入内容 fingerprint；新增惰性、真实 Registry/Executor 工具 `rereference_epochs`，保持 shape、sfreq、通道顺序和事件，改变信号、reference、identity 与 fingerprint。
- transfer Agent 复用 CIEDG goal/role/transition graph；质量、summary、bandpower 绑定 current effective Epoch。
- 受控 artifact 丢失暴露“内容等价但来源身份不同”问题：修订为不可变历史 ToolResult + 当前谱系 release view；质量证据重算，纯 summary consumer 可语义复用。
- 真实 DeepSeek 首次回答引用非标量对象，被 Evidence Gate 拒绝；新增通用 scalar evidence manifest 后一次 development case 复测通过。该项明确归为工程可靠性，不作为研究贡献。

### 实际验证

| 检查 | 结果 |
|---|---|
| 独立科学 oracle | NumPy 逐元素一致；MNE 最大绝对差约 `2.91e-11`（容差 `5e-11`） |
| 属性变化 | shape/sfreq/events/window 保持；reference/data/fingerprint 改变；单参考通道为零 |
| 结构化拒绝 | 缺通道、过期 fingerprint、不兼容 Profile、缺授权/缺参数均拒绝或澄清 |
| 最小恢复 | list/create 各 1；rereference/quality/bandpower 各 2；summary 执行 1 次并安全发布到新谱系 |
| 强动态 Expert | 正常与 artifact 丢失两例：调用序列及科学输出持平，无候选优势 |
| Fake calibration | 2/2 completed，science signature 2/2 相同；非正式实验 |
| 首次真实 DeepSeek | 2 例工具链成功、0/2 回答发布；4 请求、13,038 tokens；失败保留 |
| 修订后真实 DeepSeek | 1 个 development 正常例 completed、answer valid、与 Expert 相同；2 请求、7,641 tokens |
| 联网总预算 | 6 请求、20,679 tokens；仅 synthetic EEG，无波形外发 |
| 完整回归 | compileall、pip check 通过；210 tests：198 passed、12 resource-gated skipped、0 failed |
| 正式协议 | 24 例冻结（selection/rereference 各 12；development 8、holdout 16），尚未执行 |

### 研究判断与遗留问题

- 决策为 **Freeze / 进入正式公平实验，创新性与优势未证实**。第二 transformation family 证明机制有限迁移可行，但不证明比强 Expert 更好。
- 候选论文机制是 EEG 科学属性/角色索引的目标—证据依赖、内容/身份分离、失效和局部恢复；重参考工具、Prompt/Schema、scalar manifest 属于工程实现。
- 暂不支持重参考与筛选组合、转换前后双分支、自动参考选择、TUEV 重参考或真实数据泛化；经验质量阈值对参考通道 flatline 的解释仍需在正式报告中披露。
- 下一步只执行 `config/point1_formal_eval_protocol_v1.json` 的公平比较与消融；不新增第三种状态转换来追逐优势。

### 本轮提交

- `a5dacf8`：候选转换比较与迁移设计。
- `6bc4df2`：真实重参考、CIEDG transfer 与 provenance 修复。
- `953a8b5`：同规则强动态 Expert、Fake calibration 与冻结协议。
- `3306e94`：真实 DeepSeek 失败保留、标量 evidence 地址修复与有界复测。
- 最终审查、冻结决策和 CI 状态提交：待本提交与 GitHub Actions 完成后补充。
