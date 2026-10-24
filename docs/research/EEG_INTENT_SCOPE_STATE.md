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
- 2026-10-24：`compileall`、`pip check` 通过；全套 240 tests 通过、12 个资源条件测试跳过。

## 真实验证与最终状态

- 首次 5 例 Flash 批次因 diagnostics 含 `set` 在写报告时失败；9 次请求计入预算，未重建响应。
- 冻结子集 SH01/SH03：Flash v2 2/2、0 dangerous；Pro v2 0/2、1 dangerous、1 false reject。
- SH01/Pro 的基座 Intent 漏掉 transition 与功率，暴露“无 transition 快路”可被不完整目标绕过。
- 旧 H14 真实 Agent：clarification_required、0 EEG 工具；合法 SD03：5 工具、Evidence closed、Answer valid。
- 联网合计 21 requests；总 tokens 严格小于 46,468；只使用合成元数据/EEG，不外发波形。
- 最终决策：**NOT SAFE TO ADOPT / 工程原型保留 / 独立论文贡献 No-Go**。

## 恢复入口

- 结果：`EEG_INTENT_SCOPE_RESULTS.md`。
- 判断：`EEG_INTENT_SCOPE_DECISION.md`。
- 候选保持 opt-in；不得把 v2 设为默认，也不得基于本次 holdout 继续修改。
- 后续若新开研究，必须换新协议并先解决目标集合完备性，不能只补关键词或 Prompt 特例。
