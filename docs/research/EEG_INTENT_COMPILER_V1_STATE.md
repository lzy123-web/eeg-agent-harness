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

## 下一步

1. 建立独立 scorer 与固定 payload old-vs-new replay。
2. 在 development 调试 frame/作用域机制，记录至少一轮机制级修订。
3. 冻结后仅打开一次 holdout；运行 Flash/Pro 同条件对照和少量真实 Agent 链。
4. 全回归、论文判断、提交、Draft PR 与 Issue 评论。
