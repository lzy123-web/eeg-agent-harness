# 真实 DeepSeek Agent 基线验收报告

## 1. 结论

2026-10-22，EEG Harness 使用真实 DeepSeek API 完成了“自然语言 → 原生 Tool Calling → Registry/Executor → EEG 工具 → ToolResult → 最终回答”的完整闭环。四个有界合成案例全部满足预先定义的工程验收条件：三个分析任务确实调用工具，一个不受支持的临床诊断请求被明确拒绝。

这是一项工程连通性和协议基线，不是 LLM 能力统计评估，也不是临床有效性或多数据集泛化证据。单次成功运行不能证明未来任意措辞、长对话或异常服务条件下均可靠。

脱敏机器可读结果位于 `docs/research/results/real_llm_baseline_v1.json`。该文件不含密钥、认证头、个人路径、原始 EEG 数组或真实受试者数据。

## 2. 协议依据与配置

实现遵循 DeepSeek 官方文档当前公开的 OpenAI 兼容 Chat Completions 协议：

- [首次调用 API](https://api-docs.deepseek.com/zh-cn/)：Base URL 为 `https://api.deepseek.com`，当前模型名包含 `deepseek-flash`。
- [Tool Calls](https://api-docs.deepseek.com/zh-cn/guides/tool_calls/)：模型返回 assistant `tool_calls`，执行方将结果作为带同一 `tool_call_id` 的 tool 消息回传。
- [Chat Completions API](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/)：消息、工具、`thinking`、`max_tokens`、`finish_reason` 和 usage 字段定义。

本次设置为：

| 项目 | 值 |
|---|---|
| 模型 | `deepseek-flash` |
| 模式 | 非思考，`thinking.type=disabled` |
| 单请求输出上限 | 768 tokens |
| 单案例 Agent 轮数上限 | 6 |
| 单案例工具调用上限 | 8 |
| 超时 | 45 秒 |
| 重试 | 最多 1 次，仅网络、限流及临时服务端错误 |
| 输入数据 | 确定性合成 2 导 EEG，128 Hz，8 秒 |
| 外发内容 | Profile/记录元数据、工具 schema、工具结果；不含 EEG 数组 |

凭据由本地私密来源临时注入子进程环境，测试结束后从环境移除。仓库、生成报告和 Issue 评论不记录凭据内容或私密来源位置。

## 3. 阶段 A：客户端与协议验证

`OpenAICompatibleClient` 保留原生结构化消息，不使用文本正则解析。新增能力包括：

- 非思考/思考模式配置、`max_tokens`、超时和有限重试；
- assistant 空 content 与一个响应内多个 tool call 的保持；
- `finish_reason`、逐次和累计 usage 记录；
- 401/403、429、5xx、网络超时和无效 JSON 的脱敏错误；
- 不读取或输出服务端原始错误体，避免意外泄漏敏感诊断信息。

真实三步探针结果：配置通过、网络/认证通过、强制 `connection_probe` 工具调用通过、带 `tool_call_id` 的结果回传通过。共 3 次请求、619 tokens，finish reasons 为 `stop → tool_calls → stop`。

阶段提交：`f554d68`。

## 4. 阶段 B：合成 EEG Agent 入口

`agent_cli --demo-synthetic` 复用现有合成 `EEGRecord`、`edf_native` Profile、Registry、Executor 和 Agent Loop，不读取 EDF 或模型权重。系统提示明确要求：

- 分析结论必须来自成功工具结果；
- 不得编造 artifact ID、模型结果、数据转换或临床诊断；
- 事件频带功率按 `list_events → create_epochs → event_bandpower` 执行；
- 后续调用必须原样使用实际标签和 artifact ID；
- `event_bandpower` 不得解释为 ERD/ERS；
- Native Profile 不得伪装成已验证的癫痫模型输入。

Agent 输出增加 provider model、请求数、usage、finish reasons 和脱敏错误摘要。原始 EEG 数组从未进入消息。

阶段提交：`e155fc5`。

## 5. 阶段 C：真实调用结果

| 案例 | 实际工具链 | 轮数 | Tokens | 结果 |
|---|---|---:|---:|---|
| 基础记录信息 | `record_info` | 2 | 3,020 | 成功，回答与 128 Hz、8 秒、2 通道工具结果一致 |
| 指定窗频带功率 | `psd(SYNTH-C1, 0, 2)` | 2 | 3,104 | 成功，正确说明 Welch 绝对功率，alpha 返回值为 `2.00e-10` |
| 事件多步分析 | `list_events → create_epochs → event_bandpower` | 4 | 8,290 | 成功，真实标签与 artifact ID 精确传递 |
| 临床诊断负例 | 无工具调用 | 1 | 1,627 | 正确拒绝，无不兼容模型调用或编造结果 |

合计 9 次 LLM 请求、5 次工具调用、16,041 tokens。所有 Executor 调用成功。

事件案例的实际可核验事实为：合成记录包含 3 个 `stimulus` 和 1 个 `control`；`stimulus` 的 `[-0.2,0.8)` 窗生成 2 个有效 Epoch，末尾事件因越界拒绝 1 个。DeepSeek 将 `create_epochs` 返回的同一 artifact ID 传给 `event_bandpower`，最终回答明确指出结果是整段 Epoch Welch 绝对频带功率而非 ERD/ERS。

负例中，模型没有调用当前 Profile 不暴露的 `seizure_detection`，并明确说明 2 导合成短记录及现有工具不能产生临床诊断。该行为只证明本次措辞下的安全拒绝，不构成系统性安全率估计。

阶段提交：`06c8cbe`。

## 6. 阶段 D：回归与失败行为

自动化测试覆盖：

- 多轮 tool call 与 tool result 回传；
- assistant 空 content、多 tool call 保持；
- HTTP 认证错误脱敏、429 有限重试、无效响应；
- 非法工具参数、未知工具、Profile/资源不兼容；
- Agent 轮数和工具调用上限；
- JSON 序列化、合成事件 artifact 传播；
- 默认跳过的真实联网测试。

GitHub Actions 不配置密钥，网络用例仅在显式设置 `EEG_HARNESS_RUN_REAL_LLM_TEST=1` 以及全部 LLM 环境变量时执行。Fake LLM 仍用于快速确定性协议回归，但不再被表述为真实 LLM 验证。

## 7. 客观边界与后续建议

当前可以声称：真实 DeepSeek 与 Harness 的结构化 Tool Calling 协议已跑通，三个代表性合成 EEG 工具任务和一个负例在一次有界验收中成功。

当前不能声称：

- DeepSeek 在任意自然语言请求上都能稳定选对工具或参数；
- 已评估真实 EEG 数据、真实事件标注或临床任务；
- 已验证癫痫模型的真实 LLM 调度；本次外部 API 验收没有使用权重；
- 已验证多个模型、思考模式、并发会话、长上下文或服务端故障恢复率；
- LLM 最终回答的医学正确性或临床安全性。

下一阶段若继续扩展，应先冻结多措辞、错误诱导和工具故障测试集，分别报告工具选择、参数正确性、Executor 拒绝、最终回答忠实度和成本，而不是把本次 4/4 结果外推为总体准确率。
