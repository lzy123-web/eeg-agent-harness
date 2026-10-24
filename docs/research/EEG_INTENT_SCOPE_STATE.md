# EEG Intent Scope 研发状态

更新时间：2026-10-24（Asia/Shanghai）

## 冻结边界

- 分支继续使用 `research/eeg-intent-compiler-v1`，Draft PR #18。
- 冻结 CIEDG、Issue #16、Issue #17 的 v0/v1 代码、30 例、原始 JSON 和成绩不修改。
- H14 是已知开发回归，不进入新 holdout 成绩。
- 新方法只作为 opt-in 子版本，不扩展双分支 Planner。
- 新协议 20 例已冻结；SHA-256 `e6d47bd3c38eaf0efa26e8b7e8bcab32bf535b5faf5d774ffae2db80b1c1d250`；仅单人审核。

## 当前决策

- 选择 TGSRG：LLM 提议带 exact evidence 的目标—状态—关系图；静态编译器验证图一致性、授权隔离和 CIEDG contract 可实现性。
- 无 transition 的请求沿用 v1，不增加额外模型调用。
- transition 请求缺少完整 scope certificate 时安全澄清。

## 下一步

1. 冻结 20 例独立对抗协议与 hash。
2. 实现 opt-in v2 interpreter、静态 scope compiler 和 Agent adapter。
3. Fake/raw replay 诊断并进行一次机制级修订。
4. 锁定实现后运行不超过 24 请求、65,000 tokens 的 Flash/Pro 对照。
5. 完整回归、客观决策、PR/Issue 评论。
