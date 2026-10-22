# 项目状态

## 当前阶段

Milestone 7（Issue #6）：真实 DeepSeek Tool Calling 基线验收已完成。

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

## 实际验证结果

最新验证日期：2026-10-22。本轮调用真实 DeepSeek API，但只使用确定性合成 EEG；未向外部服务发送真实受试者数据，未下载数据、未训练模型。

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

## 下一步候选任务

按优先级排列：

1. 冻结多措辞和错误诱导的真实 LLM 小型测试集，分别报告工具选择、参数、Executor 拒绝、回答忠实度和成本，避免把 4/4 外推为总体准确率。
2. 建立资源 manifest，记录权重 SHA-256、来源状态、输入契约和许可状态，并扩展 CI Python/平台矩阵。
3. 稳定 `TaskProfile` 与 Tool Schema，增加更完整的 JSON Schema 校验、错误码测试和版本兼容策略。
4. 在确认没有兼容调用方后移除 `legacy/register_data.py`，逐步将已验证算法移出 `legacy` 命名空间。
5. 获取合法的带事件 EDF/外部注释数据后建立真实事件回归，严格分离数据适配、工具能力和 Agent 调度质量。
6. Sleep、MDD、ERP 和 ASD 继续后置，必须各自完成 Profile、资源、许可和验证后再接入。
7. 两个候选研究点的当前结论均为 No-Go；如继续研究，应使用独立冻结任务、真实任务日志和强基线，不预设优越性。
8. 优先考虑“跨 Profile/处理阶段的质量证据校准与不确定性传播”，使用独立人工标注或跨设备受控伪迹验证。

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
- Issue #6 阶段 D Commit：由本轮文档与完整回归提交记录。
