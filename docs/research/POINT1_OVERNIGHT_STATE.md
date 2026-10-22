# 工作点一集成方法：通宵状态

更新时间：2026-10-23（Asia/Shanghai）

## 当前阶段

阶段 2：必要 EEG-specific 能力已完成，准备进入阶段 3 真实 Agent 验收。工作分支为 `research/point1-integrated-method-v0`，基线起点 `d0ae05c`。

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

## 上次成功验证

阶段 2 集成测试 10/10 通过；可提交 Fake 单步与多步 trace 已保存到 `docs/research/results/point1_integrated_*_fake.json`。阶段 0 基线无资源模式 146 项通过、12 项跳过。

## 下一步

1. 用真实 DeepSeek 在合成 EEG 上运行确切 PSD、事件多步与缺参澄清；上限 36 请求/90k tokens。
2. 根据真实失败只做有价值的 1–2 轮修复，不改测试 gold。
3. 完整回归并保存脱敏真实 trace。

## 阻塞与未验证问题

- 方法新颖性尚未成立；当前目标是可运行的 method candidate。
- 尚未验证真实 DeepSeek 集成路径；Fake 只作为协议回归。
- 真实原始/处理后多分支不是当前生产 Context 的通用能力，不能虚构。
- 不得把 TaskSpec/validator/Prompt 的简单拼接包装为已证明创新。

## 本轮 Commit

- 阶段 0：`cb91166`。
- 阶段 1：`9f55415`。
- 阶段 2：待提交。
