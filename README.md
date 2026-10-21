# EEG Agent Harness

本项目是论文《面向多任务脑电分析的智能体执行框架研究与应用》的通用 EEG Harness 基础运行时 MVP。当前实现提供显式 EEG 数据、两类 Profile、标准工具注册与执行、可复现 Trace，以及可由 Fake LLM 验证的结构化 Tool Calling Agent Loop。

它不包含状态感知约束规划、证据驱动自适应分析、ASD 综合评估、RAG 或新模型训练。“具有多个工具”不等于“已在多个 EEG 数据集上验证”：当前真实资源验证仍只有原 EEGAgent 的一个 EDF 样例和一个已有权重。

## 架构

```text
EDFReader → TaskProfile Adapter → EEGRecord
                                    ↓
Natural Language → LLM/Fake LLM → ToolRegistry → Executor → EEG Tools
                                                   ↓
                                      ToolResult + ExecutionTrace
```

主要模块：

- `record.py`：通用 `EEGRecord` 与严格时间/通道切片。
- `edf.py`、`profiles.py`：数据集无关读取和 Profile 适配。
- `tooling.py`、`tools.py`、`executor.py`：工具契约、注册、校验与结构化错误。
- `context.py`、`workflow.py`：任务隔离、结果复用、执行轨迹和确定性工作流。
- `llm.py`、`agent.py`：OpenAI 兼容客户端、Fake LLM 和有界 Agent Loop。
- `legacy/`：从原 EEGAgent 迁移的数值算法及模型结构；全局 `register_data` 不在正式链路中使用。

## Profile

| Profile | 数据处理 | 工具 | 验证范围 |
|---|---|---|---|
| `tuev_bipolar_22` | 0.5–70 Hz、60 Hz 陷波、256 Hz、22 导双极派生 | 基础信息、幅值、PSD、癫痫推理 | 单个现有 EDF 与现有权重 |
| `edf_native` | 保留选定 EDF EEG 通道、原始采样率和参考结构 | 基础信息、幅值、PSD | 同一 EDF 的原生通道适配 |

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

真实 OpenAI 兼容服务需先设置三个 `EEG_HARNESS_LLM_*` 必需变量，再移除 `--fake`。客户端使用原生 `tool_calls`，不采用原项目的正则文本协议。

## 测试

```powershell
$env:EEG_HARNESS_TEST_EDF = $env:EEG_HARNESS_EDF_PATH
& $python -m compileall -q src tests
& $python -m unittest discover -s tests -v
```

2026-10-21 使用现有真实 EDF 与权重运行：32 项全部通过。未配置资源时，纯单元测试仍运行，资源型集成测试会明确跳过。

## 当前边界

- 未验证多数据集泛化、事件级性能或临床有效性。
- Sleep、MDD、ERP、ASD 和其他原 EEGAgent 模型尚未迁移到运行时。
- 真实外部 LLM 尚未验证；当前环境没有所需配置。
- 尚无 CI、完整资源 manifest、TaskProfile 插件机制和事件级评估集。
- `legacy/register_data.py` 仅为来源对照保留，正式运行时不依赖它。
