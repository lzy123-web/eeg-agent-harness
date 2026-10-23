# CIEDG 第二状态转换验证

更新时间：2026-10-23（Asia/Shanghai）

## 1. 验证边界

本轮只验证合成二通道 Epoch 上的显式参考通道减法及 CIEDG 状态机制。它不证明某种参考选择更科学，不外推真实临床 EEG、高密度 average reference、源定位或诊断性能。

## 2. 科学实现 oracle

同一 source Epoch 分别由三条独立路径计算：

1. Harness `rereference_epochs`；
2. NumPy `source - source[:, reference_indices, :].mean(axis=1, keepdims=True)`；
3. MNE `EpochsArray.set_eeg_reference(ref_channels=[...], projection=False)`。

NumPy 路径逐元素一致。MNE 路径最大绝对差约 `2.91e-11`，在预先固定的 `5e-11` 绝对容差内；差异来自 Harness 的 `float32` artifact 与 MNE 双精度计算。shape、sfreq、事件标签/时间、窗口与通道顺序保持，reference、数据值与 fingerprint 改变；单参考通道输出为零。

缺失参考通道、过期 fingerprint 和不兼容 `tuev_bipolar_22` Profile 均由真实 Registry/Executor 返回结构化失败，没有静默转换。

## 3. Agent 与状态恢复

正常链：

```text
list_events → create_epochs → rereference_epochs
            → epoch_quality → epoch_summary → event_bandpower
```

受控在 bandpower 前删除 effective artifact 后：

| 工具 | 调用数 | 解释 |
|---|---:|---|
| list_events | 1 | 与转换身份无关，保留 |
| create_epochs | 1 | source 内容仍存在，保留 |
| rereference_epochs | 2 | effective artifact 丢失，重建 |
| epoch_quality | 2 | reference-dependent role evidence，重算 |
| epoch_summary | 1 | 内容等价时复用，但发布到当前谱系 |
| event_bandpower | 2 | 首次失败，修复后最小重试 |

最终 Evidence Gate 引用 release view 而不是已删除对象。历史 ToolResult 仍保留旧 ID，release view 显式记录旧 request、新 ID、相同 fingerprint 和 `semantic_evidence_reuse`，没有把内容等价伪装成身份相等。

## 4. 强动态 Expert 公平性

`run_guarded_transfer_expert` 是公开、程序化且会动态恢复的强基线，而非故意僵化的静态 DAG。它与 CIEDG 使用：

- 相同 Registry、Executor、Profile 与科学工具；
- 相同授权、通道、fingerprint 与 artifact 规则；
- 相同故障信息、最多 16 次工具调用和 2 次修复；
- 相同的内容等价复用与 provenance 发布规则；
- 不访问离线 gold。

正常与 artifact 丢失 calibration 中，双方工具调用数和科学输出完全匹配。该结果支持“比较公平”，不支持“CIEDG 优于 Expert”。CIEDG 的候选价值是用声明式 goal/role/transition graph 在不同操作间复用恢复机制；Expert 的优势是已知工作流下更直接、可审计。

## 5. 小规模 Fake calibration

结果文件：`docs/research/results/point1_transfer_fake.json`。

- case 数：2（正常、effective artifact 丢失）；
- candidate：2/2 completed；Expert：2/2 completed；
- science signature：2/2 相同；
- 这不是正式实验，也没有运行冻结留出集。

## 6. 失败与限制

- “转换前质量 + 转换后频带功率”的单请求目前要求澄清 analysis stage，不会擅自复制两条 artifact 分支；
- trial selection 与 rereference 同时请求目前被明确拒绝，尚未验证两个有序 transition 的组合；
- 质量阈值在重参考后可能把参考通道判为 flatline；这是现有 screening 定义的真实结果，不能隐藏，但提示未来质量契约可能需要 reference-aware channel exclusions；
- 二通道 synthetic 的参考选择只用于验证数学和状态，不代表现实推荐。
