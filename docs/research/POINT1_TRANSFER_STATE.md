# 工作点一第二状态转换研发状态

更新时间：2026-10-23（Asia/Shanghai）

## 当前阶段

Issue #15 阶段 B：显式 Epoch 重参考已接入真实 Registry/Executor/Agent；独立 NumPy、MNE oracle 与受控 artifact 丢失恢复均已通过。准备实现同规则强动态 Expert 与冻结协议。

分支：`research/point1-integrated-method-v0`；Draft PR：#11。Baseline v1、CCEP v0、LRSP v1/v1.1 均保持不变。

## 选定转换

实现**用户明确授权、明确列出当前 Epoch 中参考通道的离线重参考**：

```text
x'_channel(t) = x_channel(t) - mean(x_reference_channels(t))
```

它改变信号值、reference metadata、content fingerprint 及 reference-sensitive 质量/频带结果；保持 trial 数、事件标签/时间、采样率、Epoch 窗口和通道顺序。

不自动使用“所有通道平均参考”，因为当前 Harness 不保证原记录参考电极已作为零通道存在；不选择 Epoch 重采样，因为其同时引入 anti-alias、逐 Epoch 边界效应、采样网格和频带可用性问题，难以在本轮隔离 CIEDG 的状态机制。

## 已发现并修复的机制风险

受控删除转换后 artifact 时，重建会产生新 ID 但相同 content fingerprint。v1.1 原先恢复的 consumer cache 仍携带旧 artifact ID/request ID，导致回答层可能把“内容等价”错误表述成“来源身份相同”。修复后：

- 历史 ToolResult 保持不可变；
- semantic cache 生成 `execution_kind=semantic_evidence_reuse` 的发布视图；
- 发布视图显式记录原 request、新 artifact ID/fingerprint 和等价判断；
- Evidence Gate 只从当前 goal token 的发布视图选证据。

质量证据不跨 artifact 身份复用，因此重参考恢复后重新执行；结构 summary 可在内容等价时复用；事件观察与 source Epoch 不重放。

## 下一步

1. 实现同规则动态 Expert，给它相同状态、规则、故障反馈与恢复预算。
2. 冻结 24--36 例正式协议及开发/留出边界，仅运行小规模 calibration。
3. 运行有界 Fake/DeepSeek、完整回归，形成冻结或 No-Go 决策。

## 提交

- 阶段 A：`a5dacf8`（候选比较与设计，已推送）。
- 阶段 B：待提交。
