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
- artifacts 还包含由科学元数据和数组内容计算的 SHA-256 fingerprint；
- quality：evidence ID、绑定 artifact ID/fingerprint、总/flagged/usable 数、每条件 usable 数；
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

工具仍允许旧调用方只传 `artifact_id`，因此 CCEP v0 不被破坏；CCEP v1 会额外传 `expected_artifact_fingerprint`，选择时还传 `expected_quality_evidence_id`。这些值不匹配时 Executor 返回结构化错误，不暴露 traceback。

Evidence Gate 分两层：LLM 只能引用成功 ToolResult 的已解析标量；验证通过后，运行时再确定性追加 actual selection branch 和经验阈值边界，避免回答把 identity transition 说成实际筛除。

## 尚未冻结

- guarded conditional DAG 公平对照的正式冻结协议。
- 多进程/持久化 artifact store；当前 fingerprint 解决单个 `ExecutionContext` 内的内容绑定，不等于分布式事务。
- 质量规则的临床校准与统计充分性；当前每条件至少 1 个 Epoch 只是工具可计算性 guard。

因此本文件仍是开发中集成说明，不能作为 CCEP v1 创新性或可靠性验收声明。
