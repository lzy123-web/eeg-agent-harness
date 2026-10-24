# 工作点一正式实验运行手册

冻结日期：2026-10-23（Asia/Shanghai）

## 1. 冻结对象

| 对象 | 冻结值 |
|---|---|
| Candidate source | `921b04a561b27c2e68964d5f3f1e995ee08c8c6d` |
| 协议骨架 | `config/point1_formal_eval_protocol_v1.json` |
| 骨架 SHA-256 | `e6170f9c92905d56286c199140918f09726dffc1ac6db2d1afbf81cd2360c6ad` |
| Case supplement | `config/point1_formal_eval_cases_v1.json` |
| Supplement SHA-256 | `43e7fb634ff1eb246e2685a0831bf28c3bf08bed05f481bb36a8ebc5e45d49f2` |
| 工具调用上限 | 16 |
| 状态修复上限 | 2 |
| 外部总上限 | 72 provider requests / 180,000 tokens |

Candidate 提交以后不修改 `transfer.py`、`v11.py`、Intent/Planner/Executor/EEG tools。Issue #16 新代码只位于 formal evaluation、测试、配置和研究文档。若发现 Candidate 缺陷，按失败记录，不修候选追分。

## 2. 两层实验

### 2.1 Parsed-task planning 层

所有方法获得 supplement 中同一份 `task`，不需要 LLM，不可见 `gold`：

- CIEDG：冻结 Agent 的真实 contract graph runner；
- Strong dynamic Expert：相同 Registry/Executor、授权、fingerprint、故障反馈、semantic reuse、调用/修复预算，显式覆盖 selection 和 rereference；
- 消融：无依赖传播、无内容等价 cache、全图重放、无 EEG guard。

离线 scorer 在执行结束后读取 trace，并用独立 NumPy/SciPy oracle核验，不调用 Candidate Validator 作为真值。

### 2.2 自然语言端到端层

CIEDG 与 Native tool-calling 从相同 `request` 开始，使用相同 DeepSeek client、模型、上下文元数据、Registry/Executor 与预算。gold 不进入 prompt。Intent、Planner、科学状态、恢复、回答证据分别评分。

本地 Fake 只验证协议与序列化，不冒充真实 LLM。真实请求仅使用 deterministic synthetic EEG，外部上下文不得包含波形、真实受试者信息、本地路径或实验室派生结果。

## 3. 合成 fixture 与科学边界

所有 fixture 为 128 Hz、10 秒、二通道、事件 onset `[1,4,7]` 秒。正常 Epoch 为固定 10/6 Hz 正弦；注入异常为固定 20/18 Hz 高幅正弦。seed 是冻结审计字段，不加入随机噪声。

Selection oracle 直接按注入索引切片原 `EEGRecord`；rereference oracle 直接计算：

```text
x' = x - mean(x[explicit_reference_channels])
```

频带真值由独立 SciPy Welch 路径计算。scorer 核验 shape、sfreq、事件、Epoch 内容、参考、每条件计数、频带值和 lineage，不使用工具返回反推 gold。

显式参考通道会数学上变为零，现有质量规则因此可能报告 flatline。该 flag 必须如实保留，但不等价于“授权重参考非法”。单 Epoch 仅视为可计算，不声称统计可靠或临床有效。

## 4. Fault 冻结语义

- `effective_artifact_expiry`：第一次 bandpower 前删除当前派生 artifact；
- `same_id_changed_content`：第一次 bandpower 前给 record channel 0 加 `1e-6 V` 并清空 artifact store；
- `different_id_equal_content`：第一次 bandpower 前保持 record 不变但清空 artifact store；
- `one_shot_bandpower_failure`：第一次 bandpower 返回 `INJECTED_TRANSIENT_FAILURE`；
- 每个 fault 只触发一次；Candidate 与 Expert 使用同一 wrapper。

## 5. 分层评分

每例分别输出：

1. `intent`：execute/clarify/reject、参数与授权；
2. `planning`：期望/禁止工具、合法终止；
3. `scientific_state`：Epoch 数、内容、reference、每条件 usable；
4. `recovery`：失效传播、重算与调用预算；
5. `provenance`：当前 ID/fingerprint、semantic reuse release；
6. `answer_evidence`：引用事实是否来自成功的当前证据；
7. `tool_cost`：总调用、重复调用、repair。

正确拒绝、正确澄清、科学阻断和成功分析分别报告。误拒不是安全成功；正确停止也不算完成分析。

错误分类固定为：`intent_error`、`planning_error`、`scientific_state_error`、`recovery_error`、`provenance_error`、`answer_evidence_error`、`tool_error`、`protocol_invalid`。

## 6. 执行纪律

1. 先运行 8 个 development case，修复运行器/scorer/错误 gold；任何修改须升 supplement/evaluator 版本并留痕。
2. development 锁定后，一次性运行 16 个 holdout；不得根据结果调整 Candidate、Expert 能力、科学阈值或 gold。
3. raw trace 与 scored output 分开保存；失败和 provider error 不删除。
4. 统计仅报告分母、比例、Wilson 95% CI 与每例错误；24 例不宣称跨数据集显著性。

## 7. 环境与命令

```powershell
$python = 'C:\Users\Nick\.conda\envs\eegagent\python.exe'
$env:PYTHONPATH = "$PWD\src"

& $python -m unittest tests.test_point1_formal_cases -v
& $python -m eeg_harness.research.formal_evaluation.cli --split development --output <dev.json>
# dev 审查并锁定 evaluator 后才允许：
& $python -m eeg_harness.research.formal_evaluation.cli --split holdout --output <holdout.json>
```

真实 DeepSeek 固定为 `deepseek-chat`、thinking disabled、单响应 max tokens 1024、HTTP retry 1。本次分层子集另设 40 requests / 140,000 tokens 硬上限，低于协议总上限。当前 OpenAI-compatible client **未发送 temperature 字段**，因此温度是 provider default，不能虚构为 0；所有方法共享同一限制。服务日期与实际 usage 写入结果。

API key 只临时进入进程环境；不得写入配置、结果、日志或 Issue。

## 8. 已执行命令与追加审计

```powershell
& $python -m eeg_harness.research.formal_evaluation.cli `
  --split holdout --include-ablations `
  --output docs/research/results/point1_formal_holdout_v1.json

& $python -m eeg_harness.research.formal_evaluation.audit_cli `
  --input docs/research/results/point1_formal_holdout_v1.json `
  --output docs/research/results/point1_formal_holdout_invariant_audit_v1.json

& $python -m eeg_harness.research.formal_evaluation.e2e_cli `
  --case-ids S02 S06 R05 R11 `
  --max-requests 40 --max-total-tokens 140000 `
  --output docs/research/results/point1_formal_real_llm_v1.json

& $python -m eeg_harness.research.formal_evaluation.e2e_audit_cli `
  --input docs/research/results/point1_formal_real_llm_v1.json `
  --output docs/research/results/point1_formal_real_llm_audit_v1.json
```

主结果文件只追加、不覆盖。打开 holdout 后发现的 invariant 覆盖缺口与真实 LLM acceptance 缺口均通过独立 audit 文件修正解释，不回写原始记录或冻结 gold。
