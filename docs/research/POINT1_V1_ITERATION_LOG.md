# CCEP v1 可复现迭代记录

更新时间：2026-10-23（Asia/Shanghai）

## 记录规则

本文件区分“设计假设、实际探针、修订与修订后结果”。受控故障会明确标记，不与自然发生的 Agent 错误混淆；失败结果不删除。当前所有 EEG 波形均为仓库生成的合成数据。

## 迭代 0：CCEP v0 诊断

- 观察：事件计划在质量工具运行前已经是完整 DAG；重规划从首步重放。
- 观察：clean Epoch 也产生 `-quality-selected` artifact；质量数值没有进入 Planner 状态。
- 观察：Issue #12 冻结对照中 CCEP 与同规则强 route+preflight 完全持平，不能以成功率支持创新声明。
- 决策：冻结 Intent/ledger，选择 LRSP；不把 LLM 放到每一步科学分支中。

## 迭代 1：最小动态执行初版

实现：

- 每轮从实际 artifact、质量证据、每条件 usable count、剩余目标生成一个 frontier action；
- clean 质量使用 identity transition；有异常且授权时才物化派生 artifact；任一请求条件无 usable Epoch 时安全停止；
- transient frontier 仅在声明的错误码下原地重试，保留有效完成项；
- 最终 Evidence Gate 依据实际分支计算必需工具，而不是把未发生的 identity selection 当缺失工具。

确定性结果：

- 异常 1/3：`list → create → quality → select → bandpower`，派生 Epoch 3→2，数据和频带值与独立 oracle 一致；
- clean 0/3：`list → create → quality → bandpower`，不创建伪派生 artifact；
- 全异常 3/3：质量后以 `NO_USABLE_EPOCHS_FOR_CONDITION` 停止，不执行选择和 bandpower；
- 禁止筛选：质量后直接对原 artifact 做 bandpower，保留 3 个 Epoch；
- 受控一次性 bandpower transient failure：前四步各执行一次，bandpower 执行两次后恢复。

验证命令：

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\Nick\.conda\envs\eegagent\python.exe' -m unittest `
  tests.test_point1_integrated_agent tests.test_point1_evidence_phase `
  tests.test_point1_v1_dynamic -v
```

结果：33/33 通过。下一轮不会据此宣布方法优于 guarded Expert；将先探查 lineage 内容完整性与 evidence 的时间绑定。
