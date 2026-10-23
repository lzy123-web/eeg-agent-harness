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

- 迭代 1 实现及相同故障的 A/B 调用数比较；
- 多条件中单条件零 usable 的停止行为；
- fingerprint 时间/空间开销测量；
- 同规则强动态 Expert 的可执行诊断；
- 有界真实 DeepSeek 合成 EEG 验证。
