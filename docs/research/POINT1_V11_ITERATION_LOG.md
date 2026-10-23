# CCEP/LRSP v1.1 迭代记录

更新时间：2026-10-23（Asia/Shanghai）

## 记录原则

本文件记录方法在真实 `ToolRegistry → Executor → EEG Tools` 路径上的缺陷与修订。提示词调整、关键词补充和单纯增加测试不计为算法迭代；失败用例保留为回归。

## 迭代 0：契约图原型

### 假设

把目标表示为 `GoalContract`，把完成状态表示为绑定 artifact fingerprint 和上游 token 的 `GoalEvidence`，可让多个分析 consumer 共享同一 Epoch 状态，并由依赖图自动传播失效。

### 实现

- 从请求目标构建最小依赖闭包；
- 每次只选择一个 ready residual frontier；
- `effective_epochs` 动态解析为 original 或授权筛选后的派生 artifact；
- 增加 `epoch_summary` 第二 consumer，与 `event_bandpower` 使用同一输入；
- 保留 EEG 专属授权、质量阈值和每条件至少一个 usable Epoch 的确定性 guard；
- 所有动作仍由生产 Registry/Executor 执行。

### 正向证据

1. 授权筛选：两个 consumer 使用同一 selected artifact；试次数和频带功率与独立 NumPy oracle 一致。
2. 禁止筛选：质量证据可测量，但两个 consumer 均保持使用 original artifact。
3. 无异常：selection 以 identity transition 满足，不伪造派生 artifact。
4. 原有 v1 与集成 Agent 针对性回归共 36 项通过。

### 暴露的机制缺陷

控制执行器在第一次 bandpower 前删除 selected artifact。原型能够识别 `ARTIFACT_NOT_FOUND`，撤销 selection 及依赖 consumer，再建立相同选择并完成分析；但调用序列中 `epoch_summary` 出现两次。

原因不是科学状态错误，而是证据只按当前 artifact 身份保活：旧 selected artifact 消失后，summary token 被删除；重建得到相同内容 fingerprint 时，运行时没有内容寻址的证据复用机制。因而“最小修复”仍多执行了一个与内容无关的纯 consumer。

### 修订决策

下一迭代加入受限 evidence cache：仅对无副作用 consumer，在目标参数、输入内容 fingerprint、上游 token 和输出语义签名全部一致时恢复旧证据。producer、selection transition 和内容发生变化的结果不得从缓存恢复。该修订改变状态/证据算法，不改变 LLM prompt。

## 尚未完成

- 有界真实 DeepSeek 合成 EEG 验证。

## 迭代 1：内容寻址的 consumer evidence 恢复

### 算法变化

`GoalEvidence` 同时维护两种标识：

- `token_id`：包含 artifact ID、完整参数和上游 token，表示精确执行 provenance；
- `semantic_id`：去除瞬时 artifact/evidence ID，但保留目标参数、输入内容 fingerprint、输出内容 fingerprint、模式及上游 semantic token，表示可复用的科学语义。

artifact 失效时，producer/transition token 仍直接撤销；仅无副作用 consumer token 进入缓存。恢复后必须重新计算 semantic signature，完全匹配才可恢复，并产生 `goal_evidence_reused` trace。内容、目标参数或任一上游语义发生变化都会 cache miss。

### 相同故障 A/B

控制故障均在第一次 `event_bandpower` 边界删除 selected artifact：

| 指标 | 迭代 0 | 迭代 1 |
|---|---:|---:|
| `create_epochs` | 1 | 1 |
| `epoch_quality` | 1 | 1 |
| `select_quality_epochs` | 2 | 2 |
| `epoch_summary` | 2 | 1 |
| `event_bandpower`（含失败尝试） | 2 | 2 |
| 最终状态 | completed | completed |

这证明修订减少的是已完成纯 consumer 的重复计算，不是放宽科学约束。反例中同时清除全部 Epoch artifact 并改变 record 内容，summary 仍执行两次，未错误命中缓存。

### 多条件安全停止

构造 `target/control` 两条件，其中唯一 control Epoch 被独立注入异常。质量工具返回 control usable=0；CIEDG 在 selection resolver 阻断，错误码为 `NO_USABLE_EPOCHS_FOR_CONDITION`，未执行筛选、summary 或 bandpower。该行为基于真实工具证据，不依赖 LLM 决策。

### 强 Expert 小型公平诊断

新增可执行 `run_guarded_epoch_expert`：它获得相同规范化目标、授权、质量证据、工具、数据和 16 次预算，过程式执行同一科学 guard。无故障双 consumer 用例中：

- CIEDG 与 Expert 均为 6 次工具调用；
- 试次数、事件标签/时间和每通道每频带数值完全一致；
- 独立执行的 provenance ID/fingerprint 不相等，因为现有质量 evidence ID 含随机 artifact ID。比较时只核对科学输出，未把不同执行实例的 ID 误当作数值差异。

因此目前证据只支持“声明式扩展与局部恢复可行”，不支持优于同规则强 Expert 的成功率或调用成本。

### fingerprint 开销

同一 Windows/Conda `eegagent` 环境、连续 11 次全内容 SHA-256 的一次性诊断：

| shape / float32 字节数 | median | min–max |
|---|---:|---:|
| `[3,2,128]` / 3,072 B | 0.0135 ms | 0.0132–0.0854 ms |
| `[64,22,512]` / 2,883,584 B | 1.8812 ms | 1.7696–1.9313 ms |

这是本机微基准而非普适性能结论。v1.1 在单个 frontier 周期内缓存 fingerprint，但 artifact 跨周期仍会重新哈希；大规模长 Epoch 集可能需要不可变 artifact 的创建时摘要或分块哈希。
