# 工作点一集成方法：通宵状态

更新时间：2026-10-23（Asia/Shanghai）

## 当前阶段

阶段 3：合成 EEG 的真实 DeepSeek 验证已完成，进入阶段 4 审查与完整回归。工作分支为 `research/point1-integrated-method-v0`，基线起点 `d0ae05c`。

## 已确认状态

- Issue #10 要求形成一条 opt-in 的真实集成链，不修改或替换 Baseline v1 默认 Agent。
- Baseline v1、Issue #8 与 Issue #9 的历史结果保持冻结。
- 当前可用技能中没有 ARIS `research-lit`、`research-refine`、`research-implement-feature` 或 `experiment-audit`，本轮不安装第三方脚本。
- 现有核心可复用对象包括 `EEGAgent`、`NaturalLanguageGoalInterpreter`、`StateAwareConstrainedPlanner`、`ConstrainedPlanRunner`、`ExecutionContext`、`Executor`、`ToolRegistry`。
- 已有意图解释只输出单个 `TaskSpec`，尚未把显式值、未知 slot、禁止假设、科学来源与回答证据作为同一运行时契约贯穿到底。
- 已选择 Constraint-Carrying EEG Plan（CCEP）：不可弱化的 obligation ledger 贯穿 Intent、状态绑定、计划、执行、恢复和证据回答；创新性未证明。
- 设计已保存于 `POINT1_METHOD_BLUEPRINT.md`，不再扩展 Issue #8 的 EEG 专属搜索排序。
- 新增 opt-in `--agent-mode point1`；默认 `native` 和旧 `--planning` 路径未替换。
- 已跑通 Fake 自然语言→IntentSpec→obligation ledger→旧 Planner→原 Executor/PSD→Evidence Gate→最终回答。
- Intent slot 必须附用户原文精确片段；label/channel 值还必须出现在该片段中，阻止模型用当前 record 值冒充用户显式值。
- 事件任务使用旧 Planner 生成真实 `list_events → create_epochs → event_bandpower`，并由 Evidence Gate 检查 artifact lineage。
- 缺事件 label 会在执行前 clarify；不存在标签、短于 1 秒的事件功率窗和处理后数据上的 raw 请求会安全拒绝。
- 明确授权的质量筛选固定为 `create_epochs → epoch_quality → select_quality_epochs`，禁止未测量先筛选。
- 临时工具失败和 artifact 失效各允许一次恢复；每次重规划重新检查相同 obligation，不能改 label/channel/window。
- 首轮真实 DeepSeek 暴露了参数 schema 过松：模型产生 `channel/event_label/window_*` 别名，并把普通 PSD 误判为事件分析；该轮 3/3 均安全澄清、没有误执行。
- 将 tool schema 收紧为七个 canonical slot 并补充分析类型边界后，第二轮真实验证中 PSD 单步与事件多步均完成，缺事件条件请求保持澄清。
- 两轮共 8 次 provider 请求、总计 11,677 tokens，低于 36 请求/90k tokens 预算；只使用确定性合成 EEG，未发送真实受试者数据或原始数组。

## 上次成功验证

阶段 3 集成测试 11/11 通过；Fake 与真实 DeepSeek 的脱敏 trace 已保存到 `docs/research/results/point1_integrated_*.json`。最终真实结果为 PSD `completed`（1 工具）、事件分析 `completed`（3 工具）、缺参请求 `clarification_required`（0 工具）。阶段 0 基线无资源模式 146 项通过、12 项跳过。

## 下一步

1. 审查来源可观测性、数值 span/value 一致性、Evidence Gate 与最终回答失败语义。
2. 运行带本地 EDF/既有权重的完整回归；资源仅本机引用，不写入仓库。
3. 完成验收报告、后续公平对照/消融设计与 Draft PR。

## 阻塞与未验证问题

- 方法新颖性尚未成立；当前目标是可运行的 method candidate。
- `deepseek-flash` 的中文文本在当前服务响应中存在历史已知的乱码现象；结构化参数与执行可验证，但中文自然语言可读性不能据此宣称通过。
- 真实原始/处理后多分支不是当前生产 Context 的通用能力，不能虚构。
- 不得把 TaskSpec/validator/Prompt 的简单拼接包装为已证明创新。

## 本轮 Commit

- 阶段 0：`cb91166`。
- 阶段 1：`9f55415`。
- 阶段 2：`fbf20e6`。
- 阶段 3：待提交。
