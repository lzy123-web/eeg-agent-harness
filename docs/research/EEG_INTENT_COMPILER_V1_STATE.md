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

1. 冻结当前实现和 evaluator，仅打开一次预选 holdout 子集。
2. 运行 Flash/Pro 同条件对照和少量真实 Agent 链。
3. 全回归、论文判断、提交、Draft PR 与 Issue 评论。
