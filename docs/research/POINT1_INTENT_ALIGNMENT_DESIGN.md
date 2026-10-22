# 工作点一：最小意图契约原型设计

## 1. 启动原因

Stage B 的真实 DeepSeek 实验在 11 个可评价案例中发现 1 个自然发生、可由冻结 slot 规则复核的错误：请求没有指定事件条件，模型却自行选择两个现有条件并创建 Epoch。该错误不是人工注入，因此满足“存在实际错误”的最低门槛；离线 scorer 能用 `unknown_slots[event_labels]` 和禁止 `create_epochs` 的规则确定判定，满足“可可靠评价”的最低门槛。

同时，完整错误分析链没有全部成功：后续 `event_bandpower` 因 0.6 秒窗口违反最短 1 秒约束而失败。因此本原型只作为最小路由研究，不声称已解决端到端意图对齐。

## 2. 三种公平方法

在两个未运行过真实 LLM 的 holdout 请求上比较：

1. `native_routing`：与当前 Agent 一致的最小安全说明。
2. `strong_preflight`：在作决定前逐项检查分析类型、通道、窗口、来源、事件条件、筛选权限和输出边界；缺关键值时澄清。
3. `intent_contract`：最小三段语义，即 UserIntentContract、ScientificPlanContract 和 EvidenceContract；明确禁止把未知项补成默认值。

三种方法接收完全相同的合成记录元数据、同一自然语言请求和同一个 `submit_decision` JSON schema。每个方法/案例只允许一次 provider request，不执行 EEG 工具，因此没有方法获得额外工具反馈。离线 gold 在调用结束后才用于评分，运行时不可见。

## 3. 验证字段

统一决策包含 `action`、`analysis_type`、`channels`、`window`、`event_labels`、`source_stage` 和理由。评分检查：

- 缺失通道案例必须 `clarify`，且 `channels` 保持空；
- 干扰通道案例必须选择显式目标 `SYNTH-C2`、`[4,6]` 和连续窗 PSD；
- `bandpower`、`band_power`、`absolute_bandpower` 归一为 `psd`。该词汇归一是在查看结果后修正的 scorer 缺陷，原始返回值和修正过程均保留；修正没有使候选方法超过原生方法。

## 4. 严格边界

- 这是一次 2 案例、3 方法、共 6 请求的最小 feasibility probe，不是统计实验。
- 它没有执行 Registry/Executor，也没有评价最终回答忠实度；端到端链已由 Stage B 单独测试。
- 它不能证明三段契约优于原生 Tool Calling、跨模型有效或适用于真实 EEG。
- 后续若继续，必须重新冻结更大的未见 holdout，并在相同总 token、工具反馈和重试预算下运行完整 Agent 链。
