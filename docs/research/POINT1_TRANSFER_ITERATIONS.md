# CIEDG 第二状态转换迭代记录

更新时间：2026-10-23（Asia/Shanghai）

## 迭代 0：显式重参考接线

初版在 `edf_native` Profile 上增加 `rereference_epochs`：输入不可变 Epoch artifact、显式参考通道和期望 fingerprint，输出新 artifact。数值实现保持最小，仅执行

```text
x' = x - mean(x_reference_channels)
```

独立 NumPy oracle 逐元素一致；MNE `EpochsArray.set_eeg_reference` 的最大绝对差约 `2.91e-11`，来自本项目 artifact 使用 `float32` 而 MNE 内部使用双精度，不是科学逻辑差异。测试容差固定为 `5e-11`，没有据此调整算法。

## 迭代 1：发现来源身份与内容等价混淆

### 失败探针

在 `create_epochs → rereference → quality → summary → bandpower` 中，于 bandpower 前删除转换后 artifact。Planner 正确重建了内容相同的新重参考 artifact，且没有重建 source Epoch；但 v1.1 semantic cache 把旧 summary `ToolResult` 直接恢复到 goal token。其数值仍合法，根级 `artifact_id` 却指向已删除的旧对象。

这不是 EEG 数值 Bug，而是证据发布语义 Bug：相同 fingerprint 允许结果复用，不等于两个 artifact 具有同一来源身份。

### 算法修订

将“历史执行结果”与“当前可发布证据”分离：

1. `tool_results` 继续保存真实执行历史，不修改旧 request 或 artifact ID；
2. 缓存恢复时建立新的 release view，标记 `semantic_evidence_reuse`；
3. release view 同时记录 `reused_from_request_id`、当前 artifact 身份、当前 fingerprint 与 `equivalent_content=true`；
4. Evidence Gate 和最终回答只消费当前 obligation token 的 release evidence；
5. 会产生角色证据的质量工具仍重新执行，不用 content cache 跨身份恢复。

### 结果

受控故障后的调用计数为：`list_events=1`、`create_epochs=1`、`rereference_epochs=2`、`measure_epoch_quality=2`、`epoch_summary=1`、`event_bandpower=2`。这证明事件与 source Epoch 保留，转换与依赖它的质量证据重建，纯 summary consumer 语义复用，失败的 bandpower 最小重试。

## 未采用的“修复”

- 不修改旧 ToolResult 的 artifact ID：这会伪造历史；
- 不把新 artifact 强制赋予旧 UUID：这会混淆对象身份；
- 不禁用全部 cache：虽能规避问题，但失去最小恢复研究对象；
- 不为 summary 写专用重参考特例：发布修复基于 goal token 与 artifact role，适用于声明了相同契约的无副作用 consumer。

## 当前判断

重参考迁移只增加一个 transition contract、一个参数 resolver 和通用发布修复，没有复制 Executor 或为每个 consumer 手写失效链。它初步支持 CIEDG 的声明式迁移假设；但能否形成论文优势仍必须与同规则强动态 Expert 在冻结协议下比较，不能由本轮功能测试推出。
