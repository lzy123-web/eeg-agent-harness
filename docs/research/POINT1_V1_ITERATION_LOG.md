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

## 迭代 2：内容 lineage 与回答条件修订

### 缺陷探针

在迭代 1 提交 `d96c764` 上执行受控探针：完成 `create_epochs → epoch_quality` 后，不改变 artifact ID，而将第 0 个 Epoch 原地改为 flatline，再请求下一动作。实际输出为：

```json
{"probe":"same_id_content_mutation_after_quality","quality_before":[1],"next_action_after_mutation":"select_quality","detected":false}
```

这证明仅按 artifact ID 绑定会复用陈旧质量证据。它是受控并发/外部变更探针，不声称当前单线程工具自然发生了该错误，但暴露了机制不变量没有被代码强制执行。

另外发现两个相关问题：

1. `select_quality_epochs` 会内部重新测量质量，但调用方不能声明它预期使用的 evidence ID，存在检查—执行时间差；
2. Evidence Gate 能约束数值引用，却没有强制最终文本说明 identity/derived/no-selection 分支和经验阈值边界。

### 算法与接口修订

- `EpochSet.content_fingerprint()` 对关键 Epoch 科学元数据和连续数组内容计算 SHA-256；摘要只暴露哈希，不暴露波形。
- `epoch_quality` 的 evidence ID 同时绑定 artifact ID、内容 fingerprint 和阈值。
- artifact 消费工具可选接收 `expected_artifact_fingerprint`；选择工具还可接收 `expected_quality_evidence_id`，不匹配时由现有 Executor 返回结构化失败。
- LRSP 在每次生成 frontier 前重算内容 fingerprint；同 ID 内容变化会撤销 quality/selection/bandpower 的完成状态并重新测量，而不是继续使用陈旧证据。
- 最终 LLM 引用通过校验后，由确定性运行时追加 identity/derived/no-selection 和“经验阈值未临床校准”披露；数值仍来自 ToolResult。

### 修订后验证

- 同 ID 内容变化后下一动作由 `select_quality` 改为 `measure_quality`，新 evidence ID 与旧 ID 不同；
- 人为提供过期 quality evidence ID 时，选择工具以结构化 `TOOL_EXECUTION_FAILED` 拒绝；
- clean 分支最终文本明确说明未创建筛选派生数据；
- 相关回归 51/51 通过，另有 1 个需要本地 EDF/权重环境变量的模型测试按设计跳过。

这轮改进是 lineage/state 机制改进，不是增加关键词或针对某个自然语言短语写特例。
