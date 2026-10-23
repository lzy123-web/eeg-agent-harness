# 工作点一第二状态转换研发状态

更新时间：2026-10-23（Asia/Shanghai）

## 当前阶段

Issue #15 阶段 E 已完成：显式 Epoch 重参考、来源安全的最小恢复、同规则强动态 Expert、冻结协议、有界真实 DeepSeek 与完整回归均已完成。方法建议冻结，下一阶段转入预注册正式比较与消融，不再增加状态转换模块。

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

1. 等待 Draft PR 最新 CI 并记录 run 状态。
2. 后续新任务按冻结协议执行 development/holdout 正式比较，不在 holdout 上调规则。
3. 若实验否定优势，保留 No-Go/工程基线结论，不新增第三种转换救结果。

## 提交

- 阶段 A：`a5dacf8`（候选比较与设计，已推送）。
- 阶段 B：`6bc4df2`（真实重参考、状态迁移和 provenance 修复，已推送）。
- 阶段 C：`953a8b5`（同规则 Expert、Fake calibration 与冻结协议，已推送）。
- 阶段 D：`3306e94`（真实 DeepSeek 失败保留、标量 evidence manifest 与有界复测，已推送）。
- 阶段 E：`81aecd7`（方法冻结审查、README 与项目状态，已推送）；GitHub Actions run `39959623831` 成功。
