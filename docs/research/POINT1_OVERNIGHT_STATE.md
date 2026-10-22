# 工作点一集成方法：通宵状态

更新时间：2026-10-23（Asia/Shanghai）

## 当前阶段

阶段 1：最小完整集成已完成，准备进入阶段 2。工作分支为 `research/point1-integrated-method-v0`，基线起点 `d0ae05c`。

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

## 上次成功验证

阶段 1 新增测试 2/2 通过；Fake PSD trace 已生成到 Git 忽略的 `artifacts/point1_psd_fake.json`。阶段 0 基线无资源模式 146 项通过、12 项跳过。

## 下一步

1. 增加事件多步骤、缺参澄清、来源不可观测、未授权筛选和状态反馈测试。
2. 修复初版 obligation/Planner 对组合任务和有限恢复的真实缺口。
3. 保存可提交的单步/多步脱敏 trace。

## 阻塞与未验证问题

- 方法新颖性尚未成立；当前目标是可运行的 method candidate。
- 尚未验证真实 DeepSeek 集成路径；Fake 只作为协议回归。
- 真实原始/处理后多分支不是当前生产 Context 的通用能力，不能虚构。
- 不得把 TaskSpec/validator/Prompt 的简单拼接包装为已证明创新。

## 本轮 Commit

- 阶段 0：`cb91166`。
- 阶段 1：待提交。
