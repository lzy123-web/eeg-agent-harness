# 工作点一第二状态转换研发状态

更新时间：2026-10-23（Asia/Shanghai）

## 当前阶段

Issue #15 阶段 A：已完成候选科学转换、现有 CIEDG 边界和 semantic cache provenance 风险审计，准备实现显式 Epoch 重参考与不同-ID/同内容证据发布探针。

分支：`research/point1-integrated-method-v0`；Draft PR：#11。Baseline v1、CCEP v0、LRSP v1/v1.1 均保持不变。

## 选定转换

实现**用户明确授权、明确列出当前 Epoch 中参考通道的离线重参考**：

```text
x'_channel(t) = x_channel(t) - mean(x_reference_channels(t))
```

它改变信号值、reference metadata、content fingerprint 及 reference-sensitive 质量/频带结果；保持 trial 数、事件标签/时间、采样率、Epoch 窗口和通道顺序。

不自动使用“所有通道平均参考”，因为当前 Harness 不保证原记录参考电极已作为零通道存在；不选择 Epoch 重采样，因为其同时引入 anti-alias、逐 Epoch 边界效应、采样网格和频带可用性问题，难以在本轮隔离 CIEDG 的状态机制。

## 待验证风险

v1.1 的 semantic cache 在内容等价时恢复旧 `GoalEvidence`，但 `token.result` 仍可能携带旧 artifact ID/request ID。若重建产生不同 ID，最终 answer selector 可能引用旧 provenance。必须保留历史 ToolResult，同时为发布构造显式标记的当前-lineage evidence view；不能篡改历史或伪装工具重算。

## 下一步

1. 为 `EpochSet` 增加显式 reference 科学属性，并实现真实 `rereference_epochs` 工具。
2. 建立 transfer opt-in Agent/contract，验证 transformed quality/summary/bandpower。
3. 用不同-ID/同内容故障触发局部恢复，先保留失败，再修复 answer evidence provenance。
4. 实现同规则动态 Expert、冻结正式协议、运行有界 Fake/DeepSeek 和完整回归。

## 提交

- 阶段 A：待提交。
