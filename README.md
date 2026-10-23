# EEG Agent Harness

本项目是论文《面向多任务脑电分析的智能体执行框架研究与应用》的通用 EEG Harness 基线。当前实现提供显式 EEG 数据、两类 Profile、标准工具注册与执行、可复现 Trace，以及由 Fake LLM 和真实 DeepSeek API 验证的结构化 Tool Calling Agent Loop；同一运行核心可执行癫痫时间窗推理和事件→Epoch→事件频带特征两类任务。

Baseline v1.0 已完成冻结任务集、真实 DeepSeek 自主工具选择、本地 EDF+模型、两份匿名 R3 离线链和完整回归验收。首次严格真实 LLM 子集为 3/15；主要失败是安全但不必要的额外工具调用。通用最小调用修复后的 5 个 development 复测为 5/5，holdout 未复测，因此不得表述为总体可靠率。详见 `docs/research/BASELINE_V1_ACCEPTANCE.md`。

Milestone 5 完成了约束规划强基线复核：在同等观察与恢复预算下，强 Expert DAG 与 Planner 的完成/拒绝结果持平，Planner 调用更多，因此当前“性能优势”为 No-Go；声明式扩展价值仅作 Conditional Go。详见 `docs/research/PLANNING_V2_EVALUATION.md`。

Milestone 6 增加了显式 EEG 质量证据与自适应分析 Pilot。受控合成指标通过，但真实阈值明显敏感；Candidate 与同证据、同预算的强 Expert 完全持平，因此研究点二为 No-Go。质量工具作为工程能力保留，详见 `docs/research/EVIDENCE_ADAPTIVE_EVALUATION.md`。

Issue #8 对收缩后的研究点一完成了独立 research spike：18 个冻结科学语义任务上，强 Expert DAG、通用语义 Planner 与候选 EEG Planner 的合法完成、正确拒绝和 holdout 均完全持平，调用数也相同；候选没有显示独立增益，结论为 **No-Go**。这不否定显式科学状态/lineage 的工程价值，但禁止把当前实现写成已成立的论文创新。详见 `docs/research/POINT1_PILOT_EVALUATION.md`。

Issue #10 在不改写 Baseline v1 默认路径的前提下，新增 opt-in 的 Constraint-Carrying EEG Plan（CCEP）初版：意图原文证据、科学 obligation、Planner/恢复校验、实际 ToolResult 与 artifact lineage 贯穿为一个可检查闭环。它已用 Fake LLM 和真实 DeepSeek+合成 EEG 跑通单步 PSD、事件多步与缺参澄清，但仍是**创新性未证明的方法候选**。详见 `docs/research/POINT1_INTEGRATION_ACCEPTANCE.md`。

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
$python = 'C:\Users\Nick\.conda\envs\eegagent\python.exe'
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

## Issue #9：科学意图对齐研究验证

仓库新增隔离的 `research/intent_alignment` 评测，不改变 Baseline v1.0 运行时。24 项冻结任务中的 12 项 development 使用真实 DeepSeek 与合成 EEG 运行；11 项可评价，发现 1 项自然发生的未授权事件条件选择。5 项人工合法替换单独统计，不冒充模型错误。

严格预算内的两个 holdout 路由比较为 Native 2/2、Strong Preflight 1/2、Intent Contract 2/2。候选没有优于原生路由，因此当前方法结论为 No-Go/证据不足。详见 `docs/research/POINT1_INTENT_ALIGNMENT_EVALUATION.md`。

```powershell
$env:PYTHONPATH = 'src'
& $python -m eeg_harness.research.intent_alignment.cli --mode injections `
  --output artifacts\intent-injections.json
```
