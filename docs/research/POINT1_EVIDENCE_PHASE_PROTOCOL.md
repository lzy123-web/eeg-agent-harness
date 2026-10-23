# CCEP Evidence Phase 独立实验协议

冻结日期：2026-10-23。协议版本：`point1-evidence-phase-v1`。

执行状态：已完成。结果见 `POINT1_EVIDENCE_PHASE_RESULTS.md`；协议内容和 gold 未按结果修改。

## 1. 研究对象与假设

候选机制不是关键词词表、Prompt、JSON Schema 或单次 preflight，而是同一组科学 obligations 在自然语言解释、计划、派生 EEG 状态、有限恢复和回答发布之间持续保持。需要检验的最小假设是：

- H1：动态产生或改变 Epoch artifact 后，CCEP 不会让后续工具消费错误 lineage；
- H2：明确值、禁令和选择授权在失败恢复后不被弱化；
- H3：回答只发布当前有效 lineage 中真实 ToolResult 的可寻址证据；
- H4：相对同规则强方法，上述持续约束能降低非法状态变换或错误闭合，而不只增加误拒和成本。

H1–H3 可以先做机制正确性验证；H4 才决定其是否具有独立论文方法价值。CogEEGAgent 已包含 typed contracts、preflight 与 evidence-bound release，因此这些通用组件本身不作为新颖性主张。

## 2. 冻结语料与独立 oracle

语料文件为 `config/point1_evidence_phase_v1.json`，共 24 条，development/holdout 各 12 条。冻结内容包含：

- 中英文未见措辞；质量、功率、明确授权选择、明确禁止选择及其组合；
- 缺 label/window、未知事件、无事件、短窗、反向窗和全部试次被筛空；
- 每例的科学 disposition、必要/禁止工具、输入/输出试次数、bandpower 应消费的 artifact 类型和回答边界。

离线 oracle 不进入部署 Agent。实际筛选验证另由独立造数真值和 NumPy/SciPy Welch oracle 完成，不以 CCEP plan、quality 输出或 validator 自证正确。冻结后发现标注错误时只能新增 `protocol-invalid` 记录，不能静默改 gold。

## 3. 两层实验严格分离

### 规划阶段：shared parsed task

所有方法获得完全相同的已解析意图、EEGStateSnapshot、Registry、Executor、经验质量规则、故障反馈和一次恢复预算。该层不评价语言理解：

1. `strong_route_preflight`：使用同一状态感知 route/preflight 和恢复能力，但没有 persistent ledger、重规划后 obligation 再检查或回答证据 Gate；
2. `ccep`：相同 route 与 Executor，增加 ledger 在初始计划、恢复及证据闭合时的检查。

语料中 `shared_intent=null` 的澄清案例不进入规划完成率分母，只用于端到端意图实验。强基线拥有与 CCEP 相同的科学规则，不能被故意削弱。

### 端到端：自然语言输入

Native Structured Tool Calling、Strong route+preflight 和 CCEP 分别从同一自然语言开始，使用同一 DeepSeek 配置、工具、合成 EEG、请求/Token 上限和 scorer。gold 只在运行后由离线 scorer 使用。解析错误与规划错误分别报告，不把解释差异算作 Planner 优势。

## 4. 指标

- 科学合法完成率：只统计应完成且工具、参数、lineage、计数和回答均正确的案例；正确拒绝不计完成；
- 正确拒绝/澄清率与误拒率；
- 非法状态变换率，包括未授权选择、筛空后继续和错误 artifact 消费；
- 任务语义一致性与恢复后目标保持率；
- answer reference precision；
- 工具调用、Provider 请求、tokens、重规划次数和时延。

所有分母、不可评价和 `protocol-invalid` 必须显式列出。

## 5. 公平权限与预算

所有方法可见相同脱敏状态、事件 label/count、ToolSpec、经验阈值状态、工具错误和 artifact 摘要；强 Expert 可以编码相同的先测量后选择、最短 Epoch、来源和授权规则。任何方法均不可见离线 gold 或异常注入索引。

真实 DeepSeek 总预算上限为 36 Provider requests / 80,000 tokens，只使用合成 EEG；实验室真实 EEG、受试者元数据、真实事件或派生值不得外发。预算不足或服务不可用的部分标为 `untested`，Fake 不冒充真实模型。

## 6. 预注册消融与判断

只保留三个机制性消融：

1. 去掉重规划后的 ledger 再检查；
2. 去掉派生 artifact lineage 检查；
3. 去掉回答证据寻址，只保留自由文本回答。

若 CCEP 与公平 Strong/Generic 在新 holdout 上持平且成本更高，则当前具体机制为 NO-GO 或仅保留工程价值；若只在人工故障注入或 development 上占优，不视为论文证据；若降低非法执行但提高误拒，应报告安全—效用权衡，不使用单一总分掩盖。
