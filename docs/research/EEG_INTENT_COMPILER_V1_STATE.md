# EEG Intent Compiler v1 研发状态

更新时间：2026-10-24（Asia/Shanghai）

## 冻结边界

- 起点：Issue #16 最终提交 `bff894065b1647fc168f1c0ac4b226c16768e263`。
- 分支：`research/eeg-intent-compiler-v1`；新 Draft PR，stacked base 为 `research/point1-integrated-method-v0`。
- CIEDG Candidate `921b04a`、旧 24 例、旧真实报告与追加审计完全不修改。
- 新协议：30 例；SHA-256 `b14fcb611ac2f8c854fb5b543860f2e76597be4b4e13ddf576f6ce95d544af9f`。

## 阶段 A 结论

- S02/S06：模型核心字段正确，旧短语 anchor 对 evidence quote 的表达变体误拒。
- R05：模型正确识别缺 reference channel，但旧校验先以错误 analysis mismatch 终止。
- R11：意图与执行正确，失败属于 Answer Evidence Gate。
- 历史 `deepseek-chat` 实际后端不可证实，记为 unknown；当前官方 `/models` 仅返回 `deepseek-flash`、`deepseek-v4-pro`。
- 选择“类型化 Claim–Evidence + Requirement Projection + prerequisite closure + scoped safety gate”，拒绝仅扩词表或让第二 LLM 决定授权。

## 当前验证

- 旧四例原始 payload 离线 replay：S02 execute、S06 execute、R05 正确澄清 reference_channels、R11 execute。
- 未授权/否定筛选回归：v1 不执行。
- 协议与 LLM metadata 单测：10/10 通过。
- 同载荷开发诊断：`deepseek-flash` 8 请求、14,628 tokens；严格字段全对 3/8，v0/v1 端到端分别 4/8、7/8；在 raw-correct 子集分别 1/3、3/3；均无 dangerous accept。
- I14 保留为基座 schema 错误：错误概念名和额外禁止项，未放宽编译器迎合。
- scorer 已修正为直接评价模型字段、语义概念与证据；I13 否定名词化由有界作用域规则规范化。

## 下一步

1. 候选与 evaluator 已冻结；一次性 holdout 已完成，不后验调参。
2. 完成全回归、敏感信息检查、提交、Draft PR 与 Issue 评论。
3. H14 dangerous accept 固定为未来新预注册协议的回归反例；本分支不继续补规则。

## Holdout 与真实 Agent

- 9 例同条件对照：Flash v0/v1 为 2/9、5/9；V4 Pro 为 2/9、3/9；v1 两模型均有 H14 dangerous accept。
- 严格 raw-correct：Flash 2/9，Pro 3/9。换模型没有消除意图错误。
- 真实 Agent 两例（连续 PSD、授权质量筛选多步骤）均 completed、Evidence Gate valid；4 请求、10,162 tokens。
- 全部联网：31 chat requests、56,776 tokens，另 1 次 `/models`；仅合成元数据，无波形外发。
- 完整回归：`compileall`、`pip check` 通过；230 tests 中 218 passed、12 resource-gated skipped、0 failed。

## GitHub 交付

- Draft PR：#18；base `research/point1-integrated-method-v0`，保持 Draft、未合并。
- 远端快照：`7446f30`；Issue #17 已评论真实结果与 No-Go/Keep 判断。
- 本地阶段提交：`9d21f3b`、`76d164a`、`cd06e65`、`ef33345`。因 smart-HTTP 连接 reset，远端通过 Git Data API 从同一 base 写入内容等价快照；未 force push、未覆盖历史。
