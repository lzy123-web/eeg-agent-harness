# EEG Agent Harness

> Issue #42（Draft PR #37）已冻结并运行完整 EEG 任务记忆验收：合成 EEG 的连续双记录/参数修订任务 F/S/HC 均 6/6；事件—连续交错任务分别 3/6、4/6、5/6（修正通用评分器的逗号拆句误拒后）。HC 在连续任务比强 S 略省 556 tokens，但混合任务更多调用、token、延迟且中途漏报，**无稳定独立优势**。本轮真实 DeepSeek 52 calls / 98,029 tokens，请求 `deepseek-chat`、实际报告 `deepseek-flash`。推荐保留不可变任务历史、来源/版本/范围守卫，以强 S 为简单默认；HC 仅选用，勿将其包装成已证创新。见[冻结协议](docs/research/EEG_TASK_MEMORY_ISSUE42_PROTOCOL.md)与[逐例结论](docs/research/EEG_TASK_MEMORY_ISSUE42_RESULTS.md)。离线入口：`$env:PYTHONPATH='src'; python -m eeg_harness.research.task_memory_issue42 --offline`。

> Issue #41（Draft PR #37）在原任务记忆上新增小型真实结果内联、较大结果字段索引与全臂共用的按需精确读回。独立合成确认四问 F/S/H/HC 严格有效分别 3/4、4/4、3/4、4/4；HC 与强 S 均 5 次调用，分别 10,030/10,416 实际 API tokens，但 HC 墙钟延迟更高。连续及事件短闭环 S/HC 均正确，HC 成本反高；事件闭环是明确标注的协议后补充，不能混成主确认。请求 `deepseek-chat`，实际返回 `deepseek-flash`；Issue #41 独立阶段累计 59 completion / 123,623 tokens，已停止。原始失败及评分器追加审计均保留。见[冻结协议](docs/research/EEG_TASK_MEMORY_ISSUE41_PROTOCOL.md)和[逐例结果](docs/research/EEG_TASK_MEMORY_ISSUE41_RESULTS.md)。无付费复验：`$env:PYTHONPATH='src'; python -m unittest tests.test_task_memory_issue41 -q`。

> Issue #39（Draft PR #37）现已对 HiAgent 启发的任务记忆做真实 DeepSeek＋合成 EEG 四臂初评与独立确认。短链 F/S/H/HE 均 3/3；长链 H 6/8、HE 5/8、F 5/8，S 因跨运行 300,000-token 硬预算在第 3 轮前停止，**不能得出完整长链四臂优劣结论**。HE 的 EEG 对象/版本附加组织尚无可归因收益，不宣称论文创新已证。全部新阶段 126 completion / 292,532 tokens，请勿自动续跑。见 [冻结与版本化协议](docs/research/EEG_TASK_MEMORY_ISSUE39_PROTOCOL.md)、[逐例及成本](docs/research/EEG_TASK_MEMORY_ISSUE39_RESULTS.md)、[阶段判断](docs/research/EEG_TASK_MEMORY_DECISION.md)。无 API 可复验旧/压缩版：`PYTHONPATH=src python -m eeg_harness.research.task_memory_eval --mode replay-v3 --memory-variant original|optimized`（实际执行时二选一）。

> Issue #36 的独立研究分支新增 opt-in 多轮 EEG 任务上下文原型：按真实分析任务保存不可变历史、记录/事件作用域与参数修订，F（完整历史）、S（通用摘要）、G（强通用任务记忆）、E（EEG 作用域适配）共用同一工具/读取接口。合成短会话中 G/E 均能完成核心分析，E 的独立端到端收益**尚未证实**。见 [设计](docs/research/EEG_TASK_MEMORY_DESIGN.md)、[冻结协议](docs/research/EEG_TASK_MEMORY_PROTOCOL.md)、[逐例结果](docs/research/EEG_TASK_MEMORY_RESULTS.md)和[研究判断](docs/research/EEG_TASK_MEMORY_DECISION.md)。无 API 的回放与定向测试：

PR #37 审查后追加 v2 离线协议：3/6/10 条由真实工具执行的有效历史，6/10 条时摘要和 top-3 选择确实触发；G 已具通用时间/版本检索，事件标签来自合成记录元信息。离线 G/E 均在全部 10 个查询中 top-1 取对，**不能据此宣称真实模型或 EEG 附加排序胜出**。冻结范围、逐例语义评分和下一阶段未授权预算见 [v2 协议](docs/research/EEG_TASK_MEMORY_PROTOCOL_V2.md)与[结果追加](docs/research/EEG_TASK_MEMORY_RESULTS.md)。本轮不调用付费模型。

Issue #38 继续同一 PR 的既定 HiAgent→EEG 路线：opt-in `EpisodeMemorySession` 把当前分析任务的行动/观察与完成任务摘要分开，历史查询经共同只读接口恢复实际证据；H 为任务记忆直接迁移，HE 再组织 EEG 科学对象的多版本关系。错误条件的证据读取由各臂共用范围校验拒绝。F/S/H/HE 在 3/6/10 条合成、真实工具生成的历史中离线可读 10/10，H/HE top-1 均 10/10，HE 暂无增益且上下文略长；**无新付费调用，不能推断真实模型效果**。完整边界见[设计](docs/research/EEG_TASK_MEMORY_DESIGN.md)、[结果](docs/research/EEG_TASK_MEMORY_RESULTS.md)与[阶段判断](docs/research/EEG_TASK_MEMORY_DECISION.md)。

```powershell
$env:PYTHONPATH = 'src'
python -m eeg_harness.research.task_memory_eval --mode replay
python -m eeg_harness.research.task_memory_eval --mode replay-v2
python -m eeg_harness.research.task_memory_eval --mode replay-v3
python -m unittest tests.test_task_memory -q
python -m unittest tests.test_task_memory_v2 -q
python -m unittest discover -s tests -p test_task_memory_v3.py -q
```

真实模型入口可加 `--mode real --sessions M1 --policies G E --max-requests 20 --max-total-tokens 50000 --final-answer`，但**本轮既定 96 次外部调用预算已经用尽**，此命令仅供另行批准预算后的复现；只允许合成 EEG，密钥从环境变量读取，原始响应写入被 Git 忽略的本地目录。不能把首次失败后的开发复测当成独立未见成绩。

> PR #27 的跨任务合成开发验收与方法边界见 [冻结协议](docs/research/MULTITASK_ACCEPTANCE_PROTOCOL.md) 和 [实测报告](docs/research/MULTITASK_ACCEPTANCE_REPORT.md)。`v3_acceptance` 可以用固定 Fake 负载离线检查连续、事件、现有模型、组合、澄清与科学停止；真实 DeepSeek 只允许合成输入、显式预算与私有本地日志。旧 CIEDG 正式实验结果不因此改变。

本项目是论文《面向多任务脑电分析的智能体执行框架研究与应用》的通用 EEG Harness 基线。当前实现提供显式 EEG 数据、两类 Profile、标准工具注册与执行、可复现 Trace，以及由 Fake LLM 和真实 DeepSeek API 验证的结构化 Tool Calling Agent Loop；同一运行核心可执行癫痫时间窗推理和事件→Epoch→事件频带特征两类任务。

Issue #26 在独立研究分支新增 opt-in 的多任务共同证据图：连续无事件分析、事件→Epoch 分析和严格输入模型任务通过同一目标/输入类型/状态版本/失败/证据发布核心。事件专有窗口、质量筛选和 Epoch lineage 留在任务策略，通用图不默认 Epoch。旧 CIEDG 和 Baseline v1 路径保留；新方法仍是**研究候选，不是已证明优于强动态 Expert 的论文创新**。见 [任务矩阵](docs/research/MULTITASK_HARNESS_RESEARCH_MAP.md)、[设计与修订](docs/research/MULTITASK_METHOD_DESIGN.md)、[实际验证](docs/research/MULTITASK_METHOD_VALIDATION.md)、[ASD 证据需求](docs/research/ASD_REPORT_REQUIREMENTS_AND_EVIDENCE.md)。

Issue #28 的 opt-in v3 让一个自然语言任务包含多个带独立参数/来源的目标实例：同一 PSD 两个窗口不再被同名去重，连续与事件任务仍走同一共享图/Executor，并交付可由应用读取的逐目标 `evidence_bundle`。这只在合成开发例和受限本地模型协议上验证；旧方法与历史实验不改。复现 Fake 协议三案例与自动化测试：

PR #27 阶段审查后，v3 对同名但不同值的参数执行目标引文归属检查，并在澄清续接中锁定已确认目标和禁止操作；不完整任务不发布部分证据。`capability_catalog(context)` 只列当前记录/Profile/资源可通过 v3 执行的能力，`capability_inventory(context)` 另列旧入口已注册但 v3 尚未迁移的工具；不能把“有工具”当成所有 EEG 数据都已验证。

```powershell
$env:PYTHONPATH = 'src'
python -m eeg_harness.research.integrated_method.v3_validation
python -m unittest tests.test_point1_multitask_v3 -q
```

具备合法环境变量时，上述验证模块可加 `--real --max-requests 8 --max-total-tokens 24000` 做**仅合成 EEG**的有界真实 Tool Calling；详情与原始响应只写被忽略的 `artifacts/`。单条自然语言入口为 `python -m eeg_harness.agent_cli --agent-mode point1-v3 --demo-synthetic --request '<自然语言 EEG 分析需求>'`，无事件合成记录可用 `--demo-synthetic-no-events`。此 v3 CLI 不提供任意请求的 Fake 意图理解；Fake 场景入口是上述固定验证模块。真实 EDF 不允许进入 v3 联网入口，离线结构化 `run_instances` 才能使用本地合法数据/权重。

本地合成验证入口（只输出到被 Git 忽略的 `artifacts/`，不需要 EDF/权重/API）：

```powershell
$env:PYTHONPATH = 'src'
python -m eeg_harness.research.integrated_method.v2_validation
python -m unittest discover -s tests -p test_point1_multitask_v2.py -q
```

如有合法的 OpenAI 兼容服务配置，可用同一模块加 `--real --max-requests 8 --max-total-tokens 12000` 做**仅合成数据**有界验证；请求/响应模型身份、tokens 与原始 assistant 响应存于忽略目录。不要对真实受试者运行此联网入口。`agent_cli --agent-mode point1-v2 --demo-synthetic --fake` 也可交互检查单次自然语言请求。

Baseline v1.0 已完成冻结任务集、真实 DeepSeek 自主工具选择、本地 EDF+模型、两份匿名 R3 离线链和完整回归验收。首次严格真实 LLM 子集为 3/15；主要失败是安全但不必要的额外工具调用。通用最小调用修复后的 5 个 development 复测为 5/5，holdout 未复测，因此不得表述为总体可靠率。详见 `docs/research/BASELINE_V1_ACCEPTANCE.md`。

Milestone 5 完成了约束规划强基线复核：在同等观察与恢复预算下，强 Expert DAG 与 Planner 的完成/拒绝结果持平，Planner 调用更多，因此当前“性能优势”为 No-Go；声明式扩展价值仅作 Conditional Go。详见 `docs/research/PLANNING_V2_EVALUATION.md`。

Milestone 6 增加了显式 EEG 质量证据与自适应分析 Pilot。受控合成指标通过，但真实阈值明显敏感；Candidate 与同证据、同预算的强 Expert 完全持平，因此研究点二为 No-Go。质量工具作为工程能力保留，详见 `docs/research/EVIDENCE_ADAPTIVE_EVALUATION.md`。

Issue #8 对收缩后的研究点一完成了独立 research spike：18 个冻结科学语义任务上，强 Expert DAG、通用语义 Planner 与候选 EEG Planner 的合法完成、正确拒绝和 holdout 均完全持平，调用数也相同；候选没有显示独立增益，结论为 **No-Go**。这不否定显式科学状态/lineage 的工程价值，但禁止把当前实现写成已成立的论文创新。详见 `docs/research/POINT1_PILOT_EVALUATION.md`。

Issue #10 在不改写 Baseline v1 默认路径的前提下，新增 opt-in 的 Constraint-Carrying EEG Plan（CCEP）初版：意图原文证据、科学 obligation、Planner/恢复校验、实际 ToolResult 与 artifact lineage 贯穿为一个可检查闭环。它已用 Fake LLM 和真实 DeepSeek+合成 EEG 跑通单步 PSD、事件多步与缺参澄清，但仍是**创新性未证明的方法候选**。详见 `docs/research/POINT1_INTEGRATION_ACCEPTANCE.md`。

Issue #13 在同一 opt-in 研究路径上增加 CCEP v1 的 Lineage-aware Residual Scientific Planning（LRSP）：事件任务按实际质量证据逐步生成剩余 frontier，clean/异常/全坏/禁止筛选状态会改变后续动作；瞬态失败只重试未完成 frontier，Epoch 内容 fingerprint 与质量 evidence 显式绑定。Fake 与真实 DeepSeek 的固定三例合成链均跑通，但尚未与同规则动态 Expert 做冻结正式比较，**不能宣称方法优于强基线或创新已经成立**。详见 `docs/research/POINT1_V1_RESEARCH_DESIGN.md` 与 `docs/research/POINT1_V1_ITERATION_LOG.md`。

它不包含已被证明为论文创新的规划方法、证据驱动自适应分析、ASD 综合评估、RAG 或新模型训练；当前 Planner 仅为研究先导原型。“具有多个工具”不等于“已在多个 EEG 数据集上验证”。Milestone 3 增加了独立 R3 应用适配器，但其任务标签含义、参与者分组与临床解释仍未验证。

## 架构

```text
EDFReader → TaskProfile Adapter → EEGRecord
                                    ↓
Natural Language → LLM/Fake LLM → ToolRegistry → Executor → EEG Tools
                                                   ↓
                                      ToolResult + ExecutionTrace
```

主要模块：

- `record.py`、`events.py`：通用 `EEGRecord`、`EventSet`、`EpochSet` 与严格时间语义。
- `edf.py`、`profiles.py`：数据集无关读取和 Profile 适配。
- `tooling.py`、`tools.py`、`executor.py`：工具契约、注册、校验与结构化错误。
- `context.py`、`workflow.py`、`event_workflow.py`：任务隔离、会话 artifact、执行轨迹和两类确定性工作流。
- `llm.py`、`agent.py`：OpenAI 兼容客户端、Fake LLM 和有界 Agent Loop。
- `legacy/`：从原 EEGAgent 迁移的数值算法及模型结构；全局 `register_data` 不在正式链路中使用。
- `applications/r3/`：R3 专有 Profile、资源诊断、事件工作流与显式受试者聚合；不污染通用层。
- `planning.py`、`planning_evaluation.py`：研究用状态/声明式工具契约、有限重规划与冻结公平对照；不替代 Executor。
- `planning_agent.py`、`nl_evaluation.py`：可选自然语言结构化目标桥与明确标记的人工 Fake 对照。
- `quality.py`、`adaptive.py`：不生成总分的质量测量、证据要求和受限自适应 Pilot。
- `research/integrated_method/`：opt-in 的 CCEP 意图契约、obligation ledger、计划/恢复验证和 Evidence Gate；复用原 Planner、Executor 与工具。
- `research/integrated_method/v1.py`：opt-in 的 LRSP 动态科学状态、剩余目标、内容 lineage 与局部恢复；当前只为事件质量/选择/bandpower 任务增加动态语义。

## Profile

| Profile | 数据处理 | 工具 | 验证范围 |
|---|---|---|---|
| `tuev_bipolar_22` | 0.5–70 Hz、60 Hz 陷波、256 Hz、22 导双极派生 | 基础信息、幅值、PSD、癫痫推理、事件工具 | 单个现有 EDF 与现有权重；该 EDF 无 annotation |
| `edf_native` | 保留选定 EDF EEG 通道、原始采样率、参考结构和 annotation 时间 | 基础信息、幅值、PSD、事件→Epoch→频带功率 | 合成注释数据；真实带事件 EDF 未验证 |

癫痫模型只允许在 `tuev_bipolar_22` 下运行；系统不会仅凭“有 22 个通道”推断模型适用。

## 外部资源与环境

EDF、模型权重、API 密钥和运行产物不进入 Git。常用环境变量：

```text
EEG_HARNESS_EDF_PATH
EEG_HARNESS_MODEL_PATH
EEG_HARNESS_LLM_BASE_URL
EEG_HARNESS_LLM_API_KEY
EEG_HARNESS_LLM_MODEL
EEG_HARNESS_LLM_TIMEOUT（可选）
EEG_HARNESS_LLM_MAX_TOKENS（可选，默认 1024）
EEG_HARNESS_LLM_MAX_RETRIES（可选，默认 1）
EEG_HARNESS_LLM_THINKING（可选，enabled/disabled）
EEG_HARNESS_R3_DATA_ROOT（可选，仅本地 R3 资源诊断）
```

已验证环境为 Python 3.10.17、MNE 1.6.1、NumPy 1.24.4、SciPy 1.10.1、PyTorch 2.14.1+cpu。来源及许可边界见 `THIRD_PARTY_NOTICE.md`；原始 EEGAgent 未发现许可证文件，本项目不声明相关迁移代码或权重可自由再许可。

## 运行入口

```powershell
$python = 'python'  # 先激活已安装项目依赖的 Conda 环境
$env:PYTHONPATH = "$PWD\src"
$env:EEG_HARNESS_EDF_PATH = '<合法 EDF 路径>'
$env:EEG_HARNESS_MODEL_PATH = '<已有 seizure&normal 权重路径>'
```

确定性旧基线：

```powershell
& $python -m eeg_harness.cli --channel FP1-F7 --start 0 --end 1
```

带 Trace 的多工具 Workflow：

```powershell
& $python -m eeg_harness.workflow_cli --profile tuev_bipolar_22 `
  --channel FP1-F7 --output artifacts\workflow.json
```

Fake LLM Agent：

```powershell
& $python -m eeg_harness.agent_cli --fake --profile tuev_bipolar_22 `
  --request '检查癫痫活动' --output artifacts\fake_agent.json
```

CCEP v1 合成事件链（不改变默认 Agent）：

```powershell
& $python -m eeg_harness.agent_cli --fake --demo-synthetic --profile edf_native `
  --agent-mode point1-v1 `
  --request '检查 stimulus 事件后 0 秒到 1 秒的质量，允许筛除异常试次，随后计算绝对频带功率'

& $python -m eeg_harness.research.integrated_method.v1_evaluation `
  --output artifacts\point1_v1_fake_traces.json
```

真实 LLM 评估只从环境变量读取配置；代码与文档不含密钥。固定评估仅使用合成 EEG，且设总请求与 Token 上限。

可复现的事件分析 Demo 使用明确标记的合成 MNE RawArray，不伪装成真实 EDF 或 ASD 数据：

```powershell
& $python -m eeg_harness.event_cli --demo-synthetic `
  --output artifacts\event_workflow.json
& $python -m eeg_harness.event_cli --demo-synthetic --fake-agent `
  --output artifacts\event_fake_agent.json
```

对合法的带注释 EDF，可使用 `--edf`、`--native-channel` 和 `--label`；没有 annotation 或指定标签时会明确失败。

R3 本地资源只通过显式路径使用，输出目录须保持 Git 忽略：

```powershell
& $python -m eeg_harness.applications.r3.cli --data-root '<本地 R3 根目录>'
& $python -m eeg_harness.applications.r3.analysis_cli --edf '<单个 EDF>' `
  --output artifacts\r3_local.json
& $python -m eeg_harness.applications.r3.analysis_cli --edf '<单个 EDF>' `
  --public-summary --output artifacts\r3_public.json
```

R3 默认配置为 21 个已观察 EEG 通道、300 Hz、1–40 Hz、50 Hz 陷波、平均参考、`[-0.2, 0.8)` Epoch 和 `[-0.2, 0)` baseline。只有通道、采样率和数字注释 1–9 已从本地文件核验；预处理参数是本里程碑的显式分析配置，标签 9 的 Boundary 含义与标签 1–8 的实验语义尚未得到权威说明确认。

规划 Demo 与冻结对照：

```powershell
& $python -m eeg_harness.plan_cli --demo window --output artifacts\plan_window.json
& $python -m eeg_harness.plan_cli --demo event --output artifacts\plan_event.json
& $python -m eeg_harness.plan_cli --benchmark --output artifacts\planning_benchmark.json
& $python -m eeg_harness.plan_cli --benchmark --suite config\planning_benchmark_v2.json `
  --output artifacts\planning_benchmark_v2.json
& $python -m eeg_harness.plan_cli --nl-benchmark `
  --output artifacts\nl_agent_fake_comparison.json
& $python -m eeg_harness.evidence_cli `
  --output artifacts\evidence_benchmark_v1.json

# Issue #8 冻结科学语义对照（只用确定性合成 EEG）
& $python -m eeg_harness.research.semantic_planning.cli `
  --suite config\point1_semantic_planning_v1.json `
  --output artifacts\point1_semantic_planning.json
& $python -m eeg_harness.research.semantic_planning.cli --demo branch
& $python -m eeg_harness.research.semantic_planning.cli --demo events
```

也可用 `--task <task.json>` 提供结构化 TaskSpec。该入口使用确定性合成 EEG，不需要 LLM；不支持临床诊断目标，也不会解释 R3 标签。

真实 OpenAI 兼容服务需先设置三个必需变量。密钥只应临时进入当前进程环境，不应写入命令历史、仓库配置或输出文件。以下是通用 PowerShell 示例，不包含任何个人路径或真实凭据：

```powershell
$env:EEG_HARNESS_LLM_BASE_URL = 'https://api.deepseek.com'
$env:EEG_HARNESS_LLM_API_KEY = '<临时 API Key>'
$env:EEG_HARNESS_LLM_MODEL = 'deepseek-flash'
$env:EEG_HARNESS_LLM_THINKING = 'disabled'
$env:EEG_HARNESS_LLM_MAX_TOKENS = '768'

# 分别检查配置、网络/认证、结构化工具调用与 tool_result 回传
& $python -m eeg_harness.llm_smoke

# 仅使用明确标记的合成 EEG，不读取 EDF 或模型权重
& $python -m eeg_harness.agent_cli --demo-synthetic `
  --request '分析 SYNTH-C1 从 0 到 2 秒的频带功率'

# 工作点一集成方法初版（opt-in，不替换 native 基线）
& $python -m eeg_harness.agent_cli --demo-synthetic --agent-mode point1 `
  --max-rounds 4 --max-tool-calls 8 `
  --request '计算 SYNTH-C1 从 1 秒到 3 秒的绝对频带功率' `
  --output artifacts\point1_psd.json

# 四项有界真实 LLM 验收，输出目录被 Git 忽略
& $python -m eeg_harness.real_llm_evaluation `
  --output artifacts\real_llm_acceptance.json

# Baseline v1 冻结任务：全部 Fake/Mock（模型资源仅本地引用）
& $python -m eeg_harness.baseline_v1 --backend fake `
  --model '<现有权重路径>' --output artifacts\baseline_v1_fake.json

# Baseline v1 固定真实 DeepSeek 子集；输入均为合成 EEG
& $python -m eeg_harness.baseline_v1 --backend real `
  --model '<现有权重路径>' --output artifacts\baseline_v1_real.json

Remove-Item Env:EEG_HARNESS_LLM_API_KEY
```

客户端使用原生 `tool_calls`，不采用原项目的正则文本协议；默认只对网络错误、限流和临时服务端错误进行一次有限重试。联网测试必须显式设置 `EEG_HARNESS_RUN_REAL_LLM_TEST=1`，CI 不需要也不接收密钥。

## 测试

```powershell
$env:EEG_HARNESS_TEST_EDF = $env:EEG_HARNESS_EDF_PATH
& $python -m compileall -q src tests
& $python -m unittest discover -s tests -v
```

2026-10-23 使用现有 EEGAgent EDF/权重及显式 R3 样例运行：167 项中除 1 项真实联网 opt-in 测试外均通过；两项 R3 本地资源测试也以显式样例单独通过。清除私有资源后 167 项中 155 项通过、12 项按设计跳过；`compileall` 与 `pip check` 通过。GitHub Actions 不下载 EDF、权重或使用 API 密钥。

真实 DeepSeek 合成验收另行执行：4/4 案例通过，其中 3 个完成真实 Tool Calling 闭环，1 个正确拒绝临床诊断；共 9 次模型请求、5 次工具调用、16,041 tokens。逐例脱敏结果见 `docs/research/results/real_llm_baseline_v1.json`，解释边界见 `docs/research/REAL_LLM_BASELINE_REPORT.md`。

Baseline v1 冻结自然语言验收使用 30 项任务，Fake/Mock 协议链 30/30；真实 DeepSeek 首次固定子集严格通过 3/15，修复后的 5 项 development 有界复测为 5/5。完整失败与成本保留在 `docs/research/results/baseline_v1_deepseek_evaluation.json`。

## Baseline v1.0：四条 PowerShell 入口

以下命令中的路径均由使用者显式提供，真实数据只做本地离线计算。

```powershell
# 1. 合成 EEG + 真实 DeepSeek 自然语言分析
& $python -m eeg_harness.agent_cli --demo-synthetic `
  --request '给出 SYNTH-C1 开始后两秒内各频带的绝对功率'

# 2. 本地 EDF + 现有模型，完全离线
& $python -m eeg_harness.workflow_cli --edf '<本地 EDF>' `
  --profile tuev_bipolar_22 --model '<本地权重>' `
  --channel FP1-F7 --start 0 --end 1 --output artifacts\local_model.json

# 3. 本地 R3 事件、特征和质量，完全离线且输出去标识摘要
& $python -m eeg_harness.applications.r3.analysis_cli --edf '<本地 R3 EDF>' `
  --include-quality --public-summary --output artifacts\r3_public.json

# 4a. 冻结任务 Fake/Mock
& $python -m eeg_harness.baseline_v1 --backend fake `
  --model '<本地权重>' --output artifacts\baseline_v1_fake.json

# 4b. 可选真实 DeepSeek，只使用 Runner 内置合成记录
& $python -m eeg_harness.baseline_v1 --backend real `
  --model '<本地权重>' --output artifacts\baseline_v1_real.json
```

## 当前边界

- 未验证多数据集泛化、真实带事件 EDF、事件级模型性能或临床有效性。
- 当前事件能力是通用 Epoch 与频带特征，不等同于完整 ERP/evoked 分析；Sleep、MDD、ASD 等任务尚未迁移。
- 真实 DeepSeek API 已在一次有界合成验收中验证；这只证明协议与当前四类请求的工程闭环，不证明 LLM 选择工具的总体可靠性、临床有效性或多数据集泛化。
- Baseline v1 冻结子集暴露了明显的工具最小性问题；尽管功能与安全检查通过，初始严格结果只有 3/15。不能用后续 development 复测替代未复测的 holdout 指标。
- 冻结 v2 中强 Expert 与 Planner 均为 100% 完成/正确拒绝，未观察到 Planner 结果优势；Fake 自然语言差异不作为真实模型证据。
- 质量阈值仅为未校准经验规则；Candidate 与强 Expert 在冻结合成案例中完全持平，研究点二未显示独立价值。
- 已有无私有资源 CI；尚无完整资源 manifest、TaskProfile 插件机制和真实事件评估集。
- R3 `event_bandpower` 是整段 Epoch 的 Welch 绝对频带功率后按条件求均值，不是 baseline-normalized ERD/ERS，也不支持临床或组间结论。
- 未取得权威参与者映射和标签说明，因此没有执行 ASD/TD 组间比较或受试者级真实统计。
- `legacy/register_data.py` 仅为来源对照保留，正式运行时不依赖它。
- CCEP 已增加意图—任务类型一致性、质量筛选派生 Epoch 的五工具链和证据寻址回答；真实模型只在有界合成请求上验证，未与公平强基线完成新的正式比较，不得宣称方法优势或多数据集验证。

## Issue #14：LRSP v1.1 契约索引证据依赖图

`point1-v11` 是 opt-in 研究模式。它把事件目标编译为 `GoalContract` 依赖闭包，并用绑定输入/输出内容版本及上游 token 的 `GoalEvidence` 管理动态失效。`epoch_summary` 和 `event_bandpower` 可共享 original/identity/derived effective Epoch；内容等价的 artifact 重建可恢复已完成纯 consumer，内容改变则强制重算。

```powershell
$env:PYTHONPATH = 'src'
$python = 'python'

# 三个确定性合成任务，不联网
& $python -m eeg_harness.research.integrated_method.v11_evaluation `
  --output artifacts\point1_v11_fake.json

# 单请求 CLI；使用 Fake 时加 --fake，真实服务由通用环境变量配置
& $python -m eeg_harness.agent_cli --demo-synthetic --agent-mode point1-v11 --fake `
  --request '检查 target 事件后 0 秒到 1 秒的质量，允许筛除异常试次，汇总筛选后的试次数，并计算绝对频带功率'
```

固定三例 Fake 与真实 DeepSeek 均为 3/3 completed；真实调用共 6 请求、18,253 tokens，仅使用合成 EEG。小型同规则强 Expert 诊断在科学输出和 6 次工具调用上持平，因此当前结论是 Conditional Keep、创新性未证实，尚未进入正式公平实验。详见 `docs/research/POINT1_V11_INTEGRATION.md` 与 `docs/research/POINT1_V11_RESEARCH_DECISION.md`。

## Issue #15：CIEDG 第二状态转换泛化门槛

`point1-transfer` 在不改变 Baseline v1、CCEP v0、LRSP v1/v1.1 默认行为的前提下，把 CIEDG 扩展到用户明确授权的 Epoch 重参考。当前只支持 `edf_native`、显式存在的参考通道；不默认 average reference，也不在已验证双极模型 Profile 上转换。

```powershell
$env:PYTHONPATH = 'src'
$python = 'python'

# 确定性合成校准，不联网
& $python -m eeg_harness.research.integrated_method.transfer_evaluation `
  --output artifacts\point1_transfer_fake.json

# 单请求真实 Agent；加 --fake 可离线运行
& $python -m eeg_harness.agent_cli --demo-synthetic --agent-mode point1-transfer --fake `
  --request '对 target 事件后 0 秒到 1 秒的 Epoch，允许以 SYNTH-C2 作为参考通道重参考，检查转换后质量，汇总试次数并计算绝对频带功率'
```

工具实现通过独立 NumPy/MNE oracle。不同 ID、相同内容的恢复会保留历史 ToolResult，并以明确的 semantic reuse view 绑定当前谱系。正常与 artifact 丢失 calibration 中，CIEDG 与同规则强动态 Expert 科学输出及调用数持平；这证明迁移可行，不证明相对优势。详见 `docs/research/POINT1_TRANSFER_DESIGN.md`、`POINT1_TRANSFER_VALIDATION.md` 和 `POINT1_FREEZE_DECISION.md`。

## Issue #16：工作点一正式实验

CIEDG 已冻结并完成 24 个登记场景的公平实验。parsed-task 主评分中，CIEDG 与同规则 Strong Dynamic Expert 均为 24/24、109 次工具调用；没有观察到相对优势。全图重放为 121 次；去除 EEG scientific guards 后 4/24 发生未经授权或范围不明的转换。追加不变量审计确认 S09 没有正确实例化 effective artifact 内容等价条件，因此该例标记 protocol-invalid，不用于语义复用结论。

真实 `deepseek-chat` 只在 4 个分层合成场景上运行：22 requests、59,515 tokens；追加审计后 CIEDG 1/4、Native 0/4。失败来自意图过度澄清、科学状态、恢复和最终回答证据，而不是用 Fake 冒充成功。当前研究判断为 **Conditional-Go**：可将“可审计 EEG 状态—证据依赖与有界恢复”作为限定工作点，但不得声称优于强 Expert、端到端成熟或多数据集验证。

完整协议、逐例结果、评价器缺陷留痕和论文判断见：

- `docs/research/POINT1_FORMAL_EVAL_RUNBOOK.md`
- `docs/research/POINT1_FORMAL_EVAL_RESULTS.md`
- `docs/research/POINT1_WORKPOINT1_DECISION.md`

## Issue #12：CCEP Evidence Phase

本轮将事件分析统一为 `event_workflow` 与质量、筛选、频带功率三个原子目标。以下两条链共用真实 Registry/Executor 和同一个 Epoch artifact lineage：

- 禁止筛选：`list_events → create_epochs → epoch_quality → event_bandpower`；
- 明确授权筛选：`list_events → create_epochs → epoch_quality → select_quality_epochs → event_bandpower`。

独立造数与 Welch oracle 已验证实际异常 Epoch 被剔除后试次数从 3 变为 2、原 artifact 不变、派生波形及筛选前后各频带值正确。冻结共享任务比较中，Strong route+preflight 与 CCEP 均为 18/18 正确、10/10 科学完成，没有观察到 CCEP 增量优势。两个真实 DeepSeek holdout 中 Native 为 2/2，CCEP 为 1/2；失败是执行前安全误拒，结果没有用于事后调 Prompt。

```powershell
$env:PYTHONPATH = 'src'
$python = 'python' # 或替换为已安装项目依赖的 Python 解释器

# 无联网、可重复的共享解析任务比较
& $python -m eeg_harness.research.evidence_phase.evaluation `
  --output artifacts\point1_evidence_shared.json

# 真实模型实验仅可使用合成 EEG，并须通过环境变量提供服务配置
& $python -m eeg_harness.research.evidence_phase.real_evaluation `
  --output artifacts\point1_evidence_real.json
```

实验报告见 `docs/research/POINT1_EVIDENCE_PHASE_RESULTS.md`，方法决策见 `docs/research/POINT1_METHOD_DECISION.md`。当前结论是：CCEP 作为可审计安全骨架可保留，但“优于强基线”的论文主张为 No-Go。

## Issue #9：科学意图对齐研究验证

仓库新增隔离的 `research/intent_alignment` 评测，不改变 Baseline v1.0 运行时。24 项冻结任务中的 12 项 development 使用真实 DeepSeek 与合成 EEG 运行；11 项可评价，发现 1 项自然发生的未授权事件条件选择。5 项人工合法替换单独统计，不冒充模型错误。

严格预算内的两个 holdout 路由比较为 Native 2/2、Strong Preflight 1/2、Intent Contract 2/2。候选没有优于原生路由，因此当前方法结论为 No-Go/证据不足。详见 `docs/research/POINT1_INTENT_ALIGNMENT_EVALUATION.md`。

```powershell
$env:PYTHONPATH = 'src'
& $python -m eeg_harness.research.intent_alignment.cli --mode injections `
  --output artifacts\intent-injections.json
```
