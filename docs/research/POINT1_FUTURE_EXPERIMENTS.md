# 工作点一后续正式实验与消融设计

## 1. 目的

评估 CCEP 是否在不牺牲任务完成率、成本和回答质量的前提下，降低多步骤 EEG Agent 中的意图弱化、科学约束违规和无证据回答。实验不得重复使用本轮三个验收措辞作为 holdout，也不得预设 CCEP 获胜。

## 2. 公平比较方法

所有方法获得完全相同的自然语言、脱敏 EEG 状态、Registry、Executor、工具预算、LLM 模型/参数与恢复次数：

1. **Native Structured Agent**：Baseline v1 原生结构化 Tool Calling。
2. **Strong Expert DAG**：由独立规则根据已解析意图生成最小合法 DAG；获得相同 EEG 状态、约束和恢复预算。
3. **Generic Contract Planner**：使用通用前置/后置条件与 lineage，不加入 EEG 专属优先级。
4. **CCEP**：IntentSpec + obligation ledger + replan validation + Evidence Gate。

强 Expert 不得缺少 CCEP 可见的证据、合法操作或错误恢复。若比较自然语言解析，则四方法共享同一次冻结解析输出，另设端到端实验单独衡量解析差异。

## 3. 任务集

至少覆盖 development/holdout 两部分并在运行前冻结 hash：

- 连续窗：信息、幅值、PSD、模型兼容/不兼容；
- 事件链：标签存在/缺失、多标签歧义、边界 Epoch、短窗；
- 来源：raw 明示、processed 明示、来源不可观测、分支转换非法；
- 质量与选择：只测量、明确授权筛选、禁止筛选、证据不足；
- 动态状态：artifact 失效、一次性工具错误、资源变化、Profile 变化；
- 多意图：可合法排序的组合、冲突约束、预算不足；
- 回答：完整证据、部分证据、无证据、最终 LLM 失败。

任务的科学 oracle 应由至少两名独立标注者给出允许工具集合、必要参数、禁止操作、预期 lineage 和可接受回答边界；分歧在看模型结果前解决。真实数据只做本地 Executor 验证，不发往外部模型。

## 4. 主要指标

- Intent obligation 保真率：显式 slot 在计划、执行和回答中的保持比例；
- 科学违规率：错误来源、未授权选择、缺失事件条件、非法窗口/模型适用性；
- Evidence closure precision：报告闭合的任务中真正满足工具、参数与 lineage 的比例；
- 合法完成率与正确拒绝/澄清率；
- 恢复保真率：故障后没有改写 obligation 且最终合法完成；
- 调用成本：Provider 请求、tokens、工具调用、重规划次数、时延；
- 回答忠实度：结论是否只来自成功 ToolResult，是否越界到诊断或未执行分析。

报告 development 与 holdout、单步与多步、静态与动态任务的分层结果和置信区间。额外只读工具调用是否算错误必须在冻结协议中明确，不能事后调整。

## 5. 消融

在相同 CCEP 代码与任务上逐项移除：

1. 原文 evidence span；
2. unknown/clarify gate；
3. source-stage obligation；
4. plan-time ledger validation；
5. replan-time ledger validation；
6. artifact lineage check；
7. Evidence Gate；
8. canonical intent schema；
9. EEG-specific 事件/质量规则，仅保留通用约束。

消融的目标是确定贡献来自哪个机制，而不是只比较完整方法与弱 Prompt。若第 9 项与完整方法持平，则 EEG-specific 方法贡献不成立，应降级为通用 Agent 安全工程。

## 6. 停止与判断标准

- 若 CCEP 与公平强 Expert/Generic Planner 在新 holdout 上持平，同时成本更高且无独立维护/可解释收益，则方法为 No-Go。
- 若优势只出现在人工注入、已见措辞或单模型单次采样，不视为论文证据。
- 若 CCEP 显著降低科学违规但合法完成率下降，应报告安全—效用权衡，不以单一总分掩盖。
- 若真实模型错误率过低，先扩大独立任务/重复运行和模型种类；不得人为削弱基线或修改 oracle 制造差异。
- 若 raw/processed、事件语义或 Profile 科学假设无法由数据说明确认，对应任务只报告“未验证”。

## 7. 实施顺序

1. 冻结任务、oracle、预算和统计计划；
2. 增加独立 scorer，不让运行时读取 gold；
3. 先跑确定性 Fake 与故障注入，排除协议 Bug；
4. 再做有界真实 LLM 重复实验；
5. 最后使用合法公开/本地真实事件数据验证 Executor 层，不把真实波形外发；
6. 在看到结果后只允许修复明确 Bug，方法调整必须开启新的版本和新 holdout。
