# CCEP v1 集成说明（开发中）

## 入口和兼容性

CCEP v1 以 `--agent-mode point1-v1` 显式启用。默认 Native Agent、Baseline v1、`point1` CCEP v0 均未替换。v1 复用已有 Intent interpreter、obligation ledger、`StateAwareConstrainedPlanner` 的 preflight、`ExecutionContext`、`Executor`、`ToolRegistry`、EEG 工具与证据回答校验。

```text
自然语言
  → EvidenceBoundIntentInterpreter（一次，冻结意图）
  → obligation ledger + v0 preflight
  → ResidualScientificPlanner（一个 frontier/轮）
  → ExecutionContext → Executor → 真实 EEG Tool
  → 动态科学状态/剩余目标
  → Evidence Gate → 证据路径受限回答
```

## 当前事件任务状态字段

- immutable task：labels、tmin/tmax、objectives、selection authorization；
- artifacts：原始 Epoch、选择后 Epoch、当前 effective artifact；
- quality：evidence ID、绑定 artifact、总/flagged/usable 数、每条件 usable 数；
- goals：`epoch_quality/trial_selection/event_bandpower` 的 pending/satisfied/blocked；
- attempts/blocked：动作尝试次数、结构化停止原因。

## 运行

Fake LLM 示例：

```powershell
$env:PYTHONPATH='src'
python -m eeg_harness.agent_cli --fake --demo-synthetic --profile edf_native `
  --agent-mode point1-v1 `
  --request '检查 stimulus 事件后 0 秒到 1 秒的质量，允许筛除异常试次，随后计算绝对频带功率'
```

CLI 的普通 demo 并非质量异常基准；异常分支使用 `tests/test_point1_v1_dynamic.py` 中显式生成的合成数据。当前不向外部 LLM 发送真实 EEG 数组或实验室数据。

## 尚未冻结

- artifact 的内容级 fingerprint 与同 ID 变更检测；
- selection 工具对先前 quality evidence 的显式绑定；
- 运行时 branch/identity 状态在最终自然语言回答中的确定性表达；
- guarded conditional DAG 公平对照的正式冻结协议。

因此本文件仍是开发中集成说明，不能作为 CCEP v1 创新性或可靠性验收声明。
