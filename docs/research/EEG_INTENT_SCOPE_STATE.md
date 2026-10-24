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

## 已完成实现

- 新增 opt-in `IntentScopeCompilerV2Interpreter` 与两类 Agent adapter；冻结 v1 和 CIEDG 未修改。
- Scope node 显式携带 goal、source/effective state 与 exact evidence；relation 构成可检查 DAG。
- 能力证书按实际 Transfer CIEDG 合法状态投影，并将授权继续交给 v1 检查。
- H14 冻结 raw Intent 回放会澄清 `analysis_stage`；真实 Agent 测试确认零 EEG 工具调用。
- 合法单阶段重参考链通过原 Executor/CIEDG，Evidence Gate 与回答校验闭合。
- 发现并修复“只接受直接边、误拒等价传递链”的图算法缺陷，改为 DAG 可达性判断。
- 2026-10-24：`compileall` 通过；全套 239 tests 通过、12 个资源条件测试跳过。

## 下一步

1. 锁定候选实现后运行不超过 24 请求、65,000 tokens 的 Flash/Pro 对照。
2. 保留任何未见 dangerous accept；若出现则结论必须为 NOT SAFE TO ADOPT。
3. 完成结果、失败归因、研究价值边界与恢复入口文档。
