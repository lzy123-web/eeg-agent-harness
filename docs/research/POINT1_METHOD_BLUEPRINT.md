# 工作点一集成方法初版：约束携带的 EEG 状态规划

## 1. 研究问题

多任务 EEG Agent 的困难不只在于“选到一个可调用工具”，而在于：自然语言中的科学意图、当前记录的可观测状态、跨步骤 artifact 依赖和最终回答证据必须保持一致。一个调用可以通过 JSON schema、Profile 与窗口校验，却仍可能擅自选择事件条件、用处理后数据回答原始数据问题、未经授权筛选 Epoch，或在恢复时改变用户目标。

本轮选择的 dominant mechanism 是 **Constraint-Carrying EEG Plan（CCEP，约束携带的 EEG 计划）**：把用户明确值、未知 slot、禁止假设/操作、来源要求和回答所需证据编译为不可在恢复中弱化的 obligation ledger；Planner 的每一步都必须满足当前 EEG 状态和该 ledger，并在工具成功后用真实 ToolResult/artifact lineage 消解证据义务。该机制是 method candidate，创新性尚未证明。

## 2. 候选路线比较与选择

| 路线 | 科学必要性 | 与强基线的差异风险 | 复用/成本 | 决策 |
|---|---|---|---|---|
| Scientific state-aware plan synthesis | 能表达事件、采样率、artifact 和资源 | Issue #8 表明共享契约后通用 Planner/Expert 可等价；专属排序无优势 | 现有 `planning.py` 可复用 | 不再以搜索排序为主机制 |
| Intent→plan→evidence constraint propagation | 能阻止解释后、执行中、恢复时和回答时的语义漂移 | 仍可能被强 route+preflight 等价替代，需后续实验 | 可复用意图、Planner、Context、Trace | **选择** |
| 旧 Planner + 更强 Prompt/preflight | 工程上简单可靠 | 很可能只是 validator/Prompt 拼接，论文价值最低 | 最低成本 | 作为强基线，不命名为创新 |

选择原因：Issue #9 已观察到缺失事件条件被擅自补全，而现有 Planner 只接收已经确定的 `TaskSpec`，无法知道哪些参数是用户显式给出、哪些是模型猜测。CCEP 在现有 Planner 前后增加一个持续存在的约束对象，而不是再改搜索排序或复制执行器。

## 3. 架构与职责

```text
自然语言
   │
   ▼
LLM IntentSpec ── explicit / semantic evidence / unknown / forbidden / source
   │  （运行时无离线 gold）
   ▼
Semantic Contract Resolver ── 原文概念组合独立解析 analysis type
   │
   ▼
Intent Gate ── 类型不一致/缺关键 slot → clarify；unsupported → reject
   │
   ▼
Obligation Ledger + EEGStateSnapshot
   │
   ▼
StateAwareConstrainedPlanner ── TaskSpec / PlanStep / artifact dependencies
   │
   ▼
原有 ExecutionContext → Executor → EEG Tools
   │                         │
   └──── ToolResult / artifact lineage / error ────┐
                                                   ▼
       bounded recovery（不得弱化 obligation）→ Evidence Gate
                                                   │
                                                   ▼
                               LLM evidence-bound final answer
```

模块职责：

- `IntentSpec`：保存动作、显式参数、原文绑定的科学操作概念、未知 slot、禁止操作、来源阶段和回答边界。
- Semantic Contract Resolver：根据全部已支持分析声明的概念集合独立解析任务类型；不信任模型自报枚举，也不读取离线 gold。
- Intent Gate：确定性检查关键 slot；不从 record 中自动选择一个用户未指定的标签或通道。
- Obligation Ledger：绑定 `context_id`、Profile 和意图摘要；记录参数/来源/操作/证据义务及其状态。
- Planner adapter：只把 gate 通过的 IntentSpec 编译为现有 `TaskSpec`；调用原 `StateAwareConstrainedPlanner` 与 `ConstrainedPlanRunner`。
- Evidence Gate：从真实结果与 trace 验证所需工具/参数/artifact 是否出现；失败时安全停止，不让 LLM补结果。
- Answerer：只接收脱敏元数据、意图/计划摘要和 JSON ToolResult，不接收 EEG 数组。

## 4. 轻量形式化不变量

令用户意图为 `I`，当前状态为 `S_t`，计划为 `P`，执行结果为 `R_t`，义务集合为 `O_t`。

1. **显式值保持**：对 `I.explicit[k]=v`，任何对应 PlanStep 参数必须等于 `v`。
2. **未知不猜测**：若关键 `k∈I.unknown`，且无用户授权的唯一确定推导，则不得产生改变科学范围的步骤；结果为 clarify。
3. **禁止操作保持**：`P.operations ∩ I.forbidden = ∅`，有限恢复同样不得违反。
4. **状态可满足**：每步前置条件必须由 `S_t` 与 ToolSpec/OperationContract 证明，而非由 LLM 声称。
5. **来源可观测**：请求 `raw` 而当前只有 `processed_only` 时，不以处理后结果替代原始证据。
6. **lineage 保持**：consumer 的 artifact 必须来自同一 Context 中真实成功的 producer 结果。
7. **证据闭合**：只有对应 obligation 被成功 ToolResult/trace 消解，Answerer 才能报告完成；否则报告 clarify/reject/failure。
8. **恢复单调性**：恢复可以新增观察或重建丢失 artifact，但不能删除/改写用户显式义务。
9. **任务类型一致性**：模型声明的 analysis type 必须等于由原文绑定科学概念集合唯一解析出的 capability；参数合法不能替代该证明。

## 5. 初版支持场景

### 场景 A：确切连续窗 PSD

请求明确通道与 `[start,end)`。IntentSpec 保存三个显式值；Planner 生成一个 `psd` 步骤；Evidence Gate 检查工具成功、参数一致，再形成回答。

### 场景 B：事件条件绝对频带功率

请求明确 label、`tmin/tmax` 且 Epoch 长度至少 1 秒。Planner 复用 `list_events → create_epochs → event_bandpower`；artifact ID 只能来自当前生产步骤。缺 label 时必须 clarify，不从现有标签中猜选。

后续最小扩展：明确授权的 `epoch_quality → select_quality_epochs`；只有处理后数据时拒绝“原始 50 Hz”请求；artifact 失效时最多一次重建。

### 场景 C：质量证据驱动的授权筛选后分析

用户同时明确事件条件、Epoch 窗口、质量检查、筛选授权和筛选后频带功率。Planner 生成 `list_events → create_epochs → epoch_quality → select_quality_epochs → event_bandpower`。最后一步只能消费选择工具真实产生的新 artifact id；Evidence Gate 逐步验证原 Epoch 与派生 Epoch 的 producer/consumer lineage。筛选授权缺失时不得通过参数默认值补全。

## 6. 与相关工作的实质区别

- EEGAgent 提供多工具调度，本方案关注意图约束从解释到回答的持续保持。
- CogEEGAgent 已有 typed contracts、deterministic preflight 和 evidence-bound release，因此“分权/契约/验证”本身不能作为本工作的独有创新；本方案需验证 obligation 在动态状态与恢复中的传播是否带来可测价值。
- NeuroWeaver 在约束的程序搜索空间中优化 pipeline；本方案不搜索新算法/模型，而在注册工具的运行时计划中保持用户科学约束。
- WINGS 已有 semantic component/data constraints、中间产物驱动工作流生成与 provenance；本方案的潜在区别只能来自自然语言 EEG 意图中的 unknown/authority 与在线执行状态结合，不能声称发明语义工作流。
- MNE 官方文档说明 Raw 重采样会抖动 event timing，建议与 events 联合处理或先 Epoch；这支持把操作顺序/状态作为科学约束，而不是任意工具排序。

## 7. 文献与官方依据

1. EEGAgent: A Unified Framework for Automated EEG Analysis Using Large Language Models（AAAI 2026 / arXiv:2511.09947）：LLM 多工具调度和连续推理基线。
2. CogEEGAgent: Toward Autonomous Cognitive EEG Analysis with Grounded Execution and Selection-Aware Verification（arXiv:2607.25045）：语义/科学权限分离、typed contracts、preflight、evidence-bound release。
3. NeuroWeaver: An Autonomous Evolutionary Agent for Exploring the Programmatic Space of EEG Analysis Pipelines（arXiv:2602.13473）：以领域先验约束离散 pipeline 优化空间。
4. EEGAgentBench（arXiv:2609.31632）：长时程证据累积、多步工具推理仍有限。
5. WINGS: Intelligent Workflow-Based Design of Computational Experiments（IEEE Intelligent Systems, DOI 10.1109/MIS.2010.9）：组件/数据语义约束与非法实验设计排除。
6. Wings for Pegasus（AAAI 2007）：工作流生成与执行交织，中间产物影响后续计划。
7. MNE-Python `Raw.resample` / `Epochs` 官方文档：events 联合重采样、事件 timing 与 Epoch 科学边界。

以上只引用可核实机制；未把论文报告的性能数字外推为本项目结果。

## 8. 不能宣称的内容

- 不能宣称 CCEP 已有算法新颖性、优于 ReAct/强 Expert/通用 semantic workflow，或已通过统计检验。
- 不能把 Prompt、typed dataclass、validator 或 trace 单独称为创新。
- 不能声称支持 ERP、ERD/ERS、统计检验、临床诊断或真实多数据集泛化。
- 不能把合成 EEG 的成功当作生物医学有效性。
- 不能把本轮集成验收改写成正式论文 benchmark。

## 9. 后续必须验证的对照

1. Native ReAct：原生结构化 Tool Calling。
2. Strong route+preflight：同规则、同状态、同请求/token/恢复预算，但没有持续 obligation ledger。
3. CCEP：相同输入与工具，验证未知 slot、显式参数、来源、选择权限、lineage 和恢复单调性。

正式实验需新冻结任务集、独立 gold、未见措辞和公平预算；今晚只完成集成方法初版与有界验收。
