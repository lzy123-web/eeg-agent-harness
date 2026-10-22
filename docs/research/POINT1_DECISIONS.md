# 工作点一集成方法：技术决策记录

## D0：范围与恢复协议

- 日期：2026-10-23。
- 决策：只在独立分支 `research/point1-integrated-method-v0` 开发 opt-in 方法；Baseline v1 默认行为不变。
- 原因：Issue #10 的目标是形成可运行方法对象，不重写 EEG Core，也不覆盖既有负结果。
- 状态：已采用。

## D1：选择约束携带计划作为 dominant mechanism

比较三条路线：

1. scientific state-aware plan synthesis；
2. intent→plan→evidence constraint propagation；
3. 复用旧 Planner 的低复杂度 route+preflight。

选择：采用 `intent→plan→evidence constraint propagation`，命名为 Constraint-Carrying EEG Plan（CCEP）。它将显式值、unknown、禁止操作、来源和证据要求作为不可在恢复中弱化的 obligation；继续复用旧 Planner，不再扩展 Issue #8 已判定 No-Go 的 EEG 专属搜索排序。

原因：现有 `TaskSpec` 无法表达参数是否由用户明确给出，导致 Planner 无从识别模型擅自补全；单纯更强 Prompt/preflight 又缺少执行后证据闭合与恢复单调性。CCEP 提供可检验的跨阶段机制，但新颖性暂记 `unproven`。

反证条件：若公平强 route+preflight 在新的未见任务上完全等价，或 ledger 只产生重复校验而无动态状态/恢复价值，则该机制只能作为工程控制面，不作为论文创新。

## D2：不建立第二套执行器

- 决策：CCEP 只新增 opt-in orchestration/contract 层，工具执行仍由现有 `ExecutionContext → Executor → EEG Tools` 完成。
- 原因：避免分叉数值逻辑、artifact store 和错误语义。

## D3：运行时与离线 gold 隔离

- 决策：IntentSpec 由 LLM 根据自然语言和脱敏状态生成；不读取 Issue #9 case contract 或 scorer gold。确定性 gate 只验证 IntentSpec 自身与当前 Context。
- 原因：防止数据泄漏并保持真实 Agent 条件。
