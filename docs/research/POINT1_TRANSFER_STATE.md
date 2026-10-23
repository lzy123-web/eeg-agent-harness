# 工作点一第二状态转换研发状态

更新时间：2026-10-23（Asia/Shanghai）

## 当前阶段

Issue #15 阶段 C：显式 Epoch 重参考、来源安全的最小恢复和同规则强动态 Expert 已实现；24 例正式协议已冻结但未执行。准备进行有界真实 DeepSeek、完整回归与方法冻结审查。

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

1. 使用合成 EEG 运行最多 2 个真实 DeepSeek calibration case，不发送波形。
2. 运行完整回归并核对 Draft PR CI。
3. 完成验证、协议和冻结决策文档；不再增加新的转换模块。

## 提交

- 阶段 A：`a5dacf8`（候选比较与设计，已推送）。
- 阶段 B：`6bc4df2`（真实重参考、状态迁移和 provenance 修复，已推送）。
- 阶段 C：待提交。
