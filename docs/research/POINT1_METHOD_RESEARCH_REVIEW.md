# 工作点一方法论审查：多任务 EEG 的科学状态—证据一致执行

审查日期：2026-10-25；审查基点：Draft PR #27 分支 `research/multitask-harness-method-v2` 的 `c1edcb1`。性质：**研究决策文件，不是新实验或新方法已实现声明**。旧 CIEDG v1.1、Issue #16 正式结果、PR #23 扩展结果和 PR #27 开发失败保持原样。本文件不评价第二工作点或 ASD 应用。

## 一页执行摘要：给导师讨论的结论

**一句话问题：**当 EEG Agent 同时处理连续信号特征、事件派生特征和严格 Profile 下的模型输入时，用户目标、科学数据对象、处理配置及来源版本会相互约束；工具即使逐个合法，也可能在数据或配置变化后把**已过期或不属于所请求作用域的结果**交付为当前证据。工作点一研究的是如何把这些跨任务约束转成可执行的目标—科学状态—证据关系，并在状态变化时安全撤销、最小恢复和发布；不是“让 LLM 多调用几个工具”。单次只读、固定记录和固定参数的分析通常没有动态失效问题，普通参数校验已足够。

例如，连续窗 PSD 必须绑定记录/通道/时间窗/参考/实际频带定义；事件条件功率必须绑定事件标签、Epoch 窗、有效试次集合及同一频带定义。两者科学对象不同，但配置或源记录改变都会使部分结果失效。严格 22 导模型又需要采样率、导联 Profile 和权重身份；“22 个通道”本身不能证明模型适用。这些前提不能交给通用语言模型猜测。

**审查结论：首选 REFINE（有严格停线），不是 KEEP。** 现有 v3 已有可运行的目标实例与共同执行核心，但它是由成熟 typed workflow、provenance、增量重算和 EEG 适配组成的**候选原型**，尚未形成相对最接近先行方法的独立优势证据。旧 CIEDG 与同规则强 Expert 正确性和调用数完全持平；扩展维护成本也未赢；新 v3 没有正式公平对照。不能把“图 + fingerprint + EEG 标签”称为创新。仅建议把分散在 `input_policy`、`config_keys` 和事件/模型分支中的科学状态依赖收束成**一个可检查的状态投影契约**，然后以未见跨族故障集与成熟 typed workflow、强动态 Expert 对照。若该收束既未降低适配/审计代价，也未带来独立可证的正确性或恢复差异，应停止将此机制包装为独立方法贡献，保留 Harness 作为系统成果。

## 1. 当前代码究竟有什么方法

为避免把规划、意图和工程混成一个新缩写，下文暂称候选为“**EEG 状态投影的目标—证据执行**”，只是可复述的工作名称，不宣称新算法已完成。

当前 **v1.1 CIEDG**：`v11.py::ContractGraphResidualPlanner.__init__` 仅接收 `event_workflow`（122–123 行）；`ConstraintCarryingEEGAgentV11.run` 对其他任务转到 `ConstrainedPlanRunner`（754 行附近）。它解决了特定 Epoch 筛选/重参考工作流里的 source/effective、artifact 内容与身份、失效/有界恢复，不是跨连续/事件/模型的统一实现。

当前 **opt-in v3**：`v3_agent.py::InstanceGoalEEGAgent._attempt` 从自然语言提交目标实例，但对模型遗漏的显式目标/参数没有一般完备性保证；用户请求与解析结果需分开评分。`v3.py::capability_catalog` 从 Registry 与 Profile/资源生成当前能力；`compile_instances` 逐目标预检并合并同 scope 的内部 Event→Epoch producer，但事件仍调用 `StateAwareConstrainedPlanner.plan(TaskSpec("event_workflow", ...))`（190 行附近），不是所有科学前提都由统一声明自动推导。`InstanceEvidenceGraph` 继承 `v2_graph.py::SharedEvidenceGraphCore` 的 frontier、依赖、工具执行、token 失效和有界恢复；`ExecutionContext.execute → Executor.execute → ToolRegistry` 是**唯一真实执行链**。`v3.py::run_instances` 在全目标闭合后给出逐目标 `evidence_bundle`，失败不把部分结果发布。`ToolSpec.config_keys` 目前只为 PSD 与事件功率标明 `freq_bands`；v3 由此补了跨两任务族的配置变化失效，但尚非覆盖全部潜在配置的统一规范。

关键证据与代码定位：`v2_graph.py:17–53,116–210,214–233,344–401`；`v3.py:48–102,140–236,238–317,399–472`；`v3_agent.py:154–320`；`tooling.py:39–58`；`tools.py:253–390`；`context.py:78–109`；`executor.py:46–140`；回归见 `tests/test_point1_multitask_v3.py` 与 `tests/test_multitask_acceptance.py`。本版本用户可见目标限于 `record_info/record_quality/amplitude/psd/seizure_detection/epoch_quality/epoch_summary/event_bandpower` 在当前 Profile/资源下的子集。筛选、重参考仍是**旧入口能力**，非 v3 已迁移能力；完整 ERP/ERD-ERS、睡眠/MDD、任意模型适用性不支持。v3 的最终 `answer` 主要指向逐目标 bundle，不能等同于已验证的自由叙述科学报告。

### 形式化定义：已实现骨架与尚未满足的完整性

输入为用户请求经模型提出的目标实例集合 `G={(id, capability, θ, scope, stage)}`、禁止操作 `F`，当前科学对象集合 `D={record, event/epoch artifacts, model resource}`，能力合同 `C`（Profile、通道、采样率、窗口、输入/输出 artifact、工具配置），当前版本/配置 `V`，以及已有证据 `E`。输出为下一合法 `ToolRequest` 或澄清/拒绝/科学停止；成功时输出与目标、当前输入版本、配置和依赖对应的证据包。这里的“用户请求→G”并非确定性正确，必须由独立任务真值检验，不能因 `G` 内部一致就宣称理解了用户。

当前证据可抽象为 `e_g=(goal, tool, θ, input_identity, input_content_digest, config_projection, dependency_tokens, output_identity, result, request_id)`。`identity` 指当前 artifact/资源的来源身份，`content_digest` 表示数值/元数据等价的候选依据；两者不可互代。事件标签、Epoch 窗、源/有效试次、参考与采样率是 EEG 相关科学状态；频带定义和模型权重是分析配置/资源状态。`config_projection` 目前只对声明了 `config_keys` 的工具进入 v3 token，不能声称所有可能影响结果的参数均已覆盖。授权/禁止操作进入预检与发布门，但模型未提出的用户目标或禁止项仍可能漏检。

```text
给定 G、F、D、C、V、E：
1  对每个目标校验可用能力、参数、Profile、资源和科学前提；任一不明则整单澄清/拒绝。
2  用声明的依赖与任务策略生成目标实例图；必要的事件观察/Epoch 建立为内部前提。
3  对每个已有 e：核对当前输入身份/内容、配置投影与上游 token；失效则撤销 e 及后继。
4  取依赖均有当前证据的一个剩余目标；仅同一科学输入与依赖可复用结果，否则经原 Executor 执行。
5  工具失败时按错误类别有界重试或重新绑定；结果类型/派生物不符则科学停止。
6  仅当全部用户目标有当前有效证据且禁止操作未执行时发布逐目标 bundle；否则不发布完整结果。
```

步骤 2–6 的主要运行机制已存在；**“任意新 EEG 能力仅靠 ToolSpec 自动生成完整状态影响关系”尚未实现**。前沿调度/哈希 cache/失效传播是成熟工作流方法复用；Profile 和事件窗口核验是 EEG 适配的必要工程；可能有独立价值的只限“跨记录—Epoch—模型科学对象的一致、可审计状态投影及局部证据有效性规则”，而且必须通过最近邻方案比较。自然语言引文、末尾标点、同句共指修复属于接口工程，不是此方法的主创新。

### 可检验不变量、信任边界与代价

- 程序层可检验：已提交目标的参数/Profile/资源合法；证据依赖与当前输入/已声明配置一致；未授权工具不执行；目标未闭合时不发布完整 bundle；有界调用。前提是 Registry、工具和声明真实无遗漏。
- 依赖模型语义：是否**完整且正确**提取用户科学目标、作用域、否定授权；C2 真实模型漏 `labels` 后安全澄清说明此边界未解决。内部合法不等于符合用户意图。
- 需要外部科学真值：频带/参考/质量阈值适合特定范式、模型训练来源与泛化、结果临床含义；现有经验规则和合成输入不能证明这些。
- 当前实现按前沿反复计算记录内容 SHA-256（`v3.py::_record_digest` 把全数组 `tobytes()`），时间与临时内存至少随记录样本数线性增长；模型 digest 还读取权重。图校验/失效约随目标与依赖边增长，且每个新工具仍要提供数值实现、科学条件、参数 schema、状态读取/影响、oracle 与失败语义。不能宣称零代码扩展、常数时间恢复或对任意 EEG 任务自动适用。

## 2. 先行方法比较：最接近的反例在何处

下表依据原论文正文/官方规范或原项目源码审计。**未直接核实的实现细节不作缺席断言**；“可能不同”不是创新结论。

| 先行方法 | 已解决的问题与必要前提 | 与本项目重合处 | 可能不同处、尚无证据处 | 原始来源位置 |
|---|---|---|---|---|
| EEGAgent | LLM 调度 EEG 基础、时空探索、事件检测及多种参数/非参数工具；依赖工具与相应模型输入。论文的多任务/报告说法不能与本地代码已运行范围混同。 | 多任务 EEG 工具编排、交互和报告目标本身**不是本项目独有**。本地审计显示原入口固定 22 导加载、全局数据共享、文本协议，不能由此推断论文没有其它实验路径。 | 当前项目把数据契约、Profile、Executor 与逐目标证据做得更显式；尚未证明相对论文系统在科学正确性或任务泛化上有优势。 | [AAAI 2026 原论文摘要、方法/Toolbox Table 1、探索案例](https://ojs.aaai.org/index.php/AAAI/article/view/38867/42829)；仓库 `CODE_AUDIT.md:2–5`、原 `main.py`/`tools/registerData.py`。 |
| CogEEGAgent | 认知 EEG 的语义路由与确定性科学控制；注册目录、typed scientific contracts、证据约束发布；更强的预注册/发现—确认分离需要保留的确认资源与策展者合同。 | LLM 不掌握科学权限、Schema/前提/结果类型检查、来源和 evidence-bound release **高度重合**；不能把这些描述为我们首创。 | 其已发表主张重心是 trace–partition–evidence binding 与确认边界；本项目候选重心是跨 record/Epoch/model 状态版本的增量失效/局部恢复。但 Cog 的 MNE 工具和故障审计也涉及 Epoch/参考/分析选择；**未做同条件机制复现，差异价值未证实**。 | [arXiv v1 §3.1–3.5、§4.6、附录 A/C/E](https://arxiv.org/html/2607.25045)。论文明确说语义 fit 仍由策展者负责。 |
| WINGS | 用组件/数据语义、输入/中间/输出约束淘汰无效科学工作流；可从抽象请求逐步细化候选，前提是策展人已表达正确类型和元数据。原论文也明确讨论知识工程投入。 | 科学类型/条件约束、按目标生成可执行流程属于成熟路线。 | EEG 专用状态投影也可能只是 WINGS 领域建模；若 WINGS 风格表驱动实现同样正确且代价相近，本项目的独立方法主张将减弱。 | [Gil 等《Wings》原论文](https://doi.org/10.1109/MIS.2010.9)、[Gil 等 77 页语义工作流原始方法全文，§3–5 与结论](https://knowledgecaptureanddiscovery.github.io/yolanda_gil_website/papers/gil-etal-jetai11.pdf)。 |
| Pegasus / Wings–Pegasus provenance | DAG 数据依赖、已有输出重用/节点裁剪、任务重试/剩余工作流及执行来源；依赖文件/任务身份和可靠目录。 | 失效/重算、来源与 cache **不是新发明**，甚至与局部恢复很接近。 | EEG artifact 语义、处理阶段及授权可能要求更精细的等价条件，但“只是更细类型”尚未证明算法差异。 | [Deelman 等 Pegasus 原论文全文，工作流变换/可靠性/来源章节](https://deelman.isi.edu/wordpress/wp-content/papercite-data/pdf/deelman-fgcs-2015.pdf)、[Pegasus 官方 Data Reuse §4.1](https://pegasus.isi.edu/documentation/reference-guide/mapping.html)、[Wings/Pegasus 原始 provenance 论文](https://doi.org/10.1002/cpe.1228)。 |
| W3C PROV-O | 标准化 Entity、Activity、使用/派生/失效与来源互换；它是**表示标准**，不代替 EEG 数值 oracle 或完整 planner。 | 来源身份、使用关系、失效和可追踪证据可以直接借用。 | 本项目若只把 token 重命名为 provenance，无独立贡献；须证明领域状态合法性/发布决策有额外可执行保证。 | [PROV-O W3C Recommendation，尤其 §3–4](https://www.w3.org/TR/prov-o/)。 |

**最强反例不是弱 ReAct，而是“同一 EEG ToolSpec/Profile 与 oracle 上的成熟 typed scientific workflow + provenance + 内容签名重用”。** 它原则上可生成相同 DAG 与局部重算，甚至可能比现有手写 `InstanceEvidenceGraph` 更易审计。因此不能只和缺少规则的 Native Agent 比。CogEEGAgent 也已覆盖“LLM 解释、确定性权限、证据发布”的核心口号；如要差异化，只能在**动态 EEG 状态投影及跨任务增量有效性**给出可复现且公平的增量，而不能换术语。

## 3. 证据清账：可说与不能说

| 已有证据 | 严格可支持 | 不可由此推出 |
|---|---|---|
| Issue #16 冻结 parsed-task 24 场景：CIEDG/同规则 Strong Expert **24/24 对 24/24、109 对 109 calls**；whole-plan replay 121；无 guard 为 20/24；S09 protocol-invalid。 | 在两个 Epoch 转换族和预设规则内，候选与强专家科学正确性持平；guard 与局部恢复确实参与运行；比朴素全图重放少 12 次调用。 | 优于强专家、统计泛化、selection 等价复用已证明。真实 LLM 四例追加审计 CIEDG 1/4、Native 0/4 只作失败定位。见 `POINT1_FORMAL_EVAL_RESULTS.md`。 |
| PR #23 只读 Epoch consumer 扩展：双方 **7/7、各 37 calls**，方法特定增量 **42 vs 41 LOC**。 | 在该小型同族扩展上无正确性、调用或增量 LOC 优势；Expert 合理表驱动后并未复制全部流程。 | “加 EEG 任务更少人工维护”已证实，或一项方差工具可代表跨任务族。见远端 `POINT1_EXTENSIBILITY_AUDIT/RESULTS.md`。 |
| v3 C1–C8 开发集：连续、事件、已验证模型和合法组合走共同图；C8 暴露配置变化后旧频谱证据失效并修复；Fake/独立数值 oracle 与有界真实 LLM。 | 已证明**可用性与具体旧错误的修复**，并给出可审计配置；C2 真实模型仍因遗漏事件标签安全澄清。 | 新版相对 Strong Expert/Native 的正式胜负、多数据集、自由语言稳定性或方法独创性。见 `MULTITASK_ACCEPTANCE_PROTOCOL/REPORT.md`。 |
| R3 本地接入：旧冻结 CIEDG 对 4 份真实 EDF 的离线数值流程；R3 标签/分组缺权威释义。 | 仅旧入口在局部真实记录上可执行并与确定性流程对照。 | v3 已在 R3 验证、多数据集泛化、ASD 或临床效能。见 [PR #25 分支原始验证报告](https://github.com/lzy123-web/eeg-agent-harness/blob/research/r3-ciedg-application/docs/research/R3_CIEDG_VALIDATION.md)；本分支 `R3_INTEGRATION_REPORT.md` 是更早的两份文件接入报告，不等于这 4 份实验。 |

上述正反结果的粒度分别是合成场景、单只读扩展、开发请求和局部真实数据，不能相加成一个“综合成功率”。历史 `POINT1_WORKPOINT1_DECISION.md` 的 Conditional-Go 针对当时冻结 CIEDG 的**限定可写性**，不是对新版独立创新的确认；本轮在更强先行对照下把方向审查收紧为 REFINE。

## 4. 简洁替代方案与最多三项可证伪假设

| 替代 | 科学正确性潜力 | 与当前候选的实际比较要点 |
|---|---|---|
| 表驱动 Strong Dynamic Expert | 拥有同一 Profile/ToolSpec/授权/证据和故障反馈时可以精确手写分支，旧实验已全部持平。 | 若新能力只需 Expert 表项与少量分支，而候选也要改事件策略/graph，则候选的维护收益不存在。不得人为削弱 Expert。 |
| WINGS/Pegasus 式 typed workflow + PROV、签名重用 | 可以表达类型、前提、依赖、来源与局部重跑，是最接近方法反例。 | 应以相同 EEG 科学合同、同故障/预算下实现精良最小版本；若表现/变更面同等或更好，图方法只是其 EEG 工程实例化。 |
| 全图重放 + 严格结果签名检查 | 最简单、易审计，旧 Issue #16 也保持正确但 121 vs 109 calls。 | 当 EEG 工具便宜、任务图小、缓存风险大时，节省 12 次调用未必抵过图/哈希/维护代价；必须比较实际耗时与审计复杂度。 |

H1（科学状态）：在**预先冻结**的跨族源记录/频带配置/Epoch 状态变化下，候选与同规则强 Expert、typed workflow 都应保持来源/数值/发布不变量；若候选额外减少错误，须排除是对方规则不等价。**可能全员持平**。

H2（局部恢复）：在同样故障与科学正确性下，候选相比全图重放可减少不必要 EEG 工具/重量级模型重算；但与增量 typed workflow 或表驱动 Expert 可能持平，净墙钟时间还可能被全记录哈希抵消。

H3（扩展面）：新增**另一任务族的只读消费者或合法状态读取关系**时，候选在不改共同 graph 的前提下可减少方法特定分支/审计点；PR #23 的 42 vs 41 LOC 是反证先兆。若公平 Expert/typed workflow 同样低成本，H3 不成立。

### 最小决定性实验草案（本轮不运行）

先在独立文档冻结 12–16 个**未使用 C1–C8、Issue #16、PR #23 文句/随机种子**的受控跨族场景：连续记录频带/参考或配置变化、事件试次筛选/重参考前后、严格模型输入资源变化，各含正常、非法/无授权、状态改变和注入失败；不新增第三种状态转换。科学真值由独立数组变换、Welch/试次计数、资源/Profile 检查与来源不变量预先制定。必要时先把新版接到**已有**筛选/重参考工具，不能把旧 v1.1 不支持的连续/模型任务记成失败；旧版仅在共同支持的事件子集作描述性对照。

同一输入、相同 EEG 工具/ToolSpec/Profile/规则、相同状态与故障反馈、相同次数/时间预算给四臂：候选、可合理重构的 Strong Dynamic Expert、WINGS/Pegasus 思路的最小 typed workflow+provenance、朴素 whole-plan replay；Native Agent 作为端到端参考，不当作科学规则对等的唯一对手。冻结版本与评价器后先跑结构化目标，分别报告科学不变量、完整发布、工具调用/墙钟及来源错误；自然语言层再同模型/提示信息/预算运行少量合成未见请求，单列**意图漏/增/误拒**，不把解析错误归因于状态图。新增任务适配由独立开发者记录共有工具/oracle 工作与候选/Expert/typed 方法特定变更、条件分支、审计工时；LOC 仅辅证。

最小可行工作量估计：固定协议与独立 oracle 约 2–3 人日；两种认真实现的对照/适配与审查约 4–7 人日；运行与逐例归因约 2–3 人日，合计约 **8–13 人日**，不含另一个新模型或临床标注。该估计是计划假设，不是实测成本。决定性并不要求候选“赢每个分数”：若全员科学正确，候选至少需在多个跨族状态变化中显示**可复现且非转嫁给共享规则的**恢复/适配成本收益；若收益只相对朴素重放而与强 Expert、typed workflow 持平，不能保留独立方法优势叙述。

## 5. REFINE 的唯一最小改进与停止条件

**只准一项结构性修订：声明式科学状态投影合同。** 对每种已有工具显式列出它读取的状态分量（例如记录数据/参考/采样率、事件 scope 与有效试次、频带配置、模型资源）和会改变的分量；以同一版本投影生成证据签名，并由共同核心按这些分量自动决定失效/局部恢复。它把目前 `ToolSpec.config_keys`、`GoalContract.input_policy`、事件特殊依赖以及模型 digest 的**分散人工一致性责任**变成一个可审计接口。没有新 Executor、新算法工具、新状态转换、第二创新点或新增缩写；旧 v1.1 和其结果仍冻结。该想法与成熟 typed workflow 很接近，**不是本文件宣称的新贡献**，其价值须由上述对照检验。

若下一轮不愿投入公平 typed-workflow/强 Expert 对照，或无法给投影合同作科学完整性审计，应直接把它降为系统工程，不再用“新规划算法”表述。若实现后仍须每个跨族目标修改图核心，或在预冻结场景下出现错误复用/漏失效，立即停止扩展并修正安全性；若强 Expert/typed workflow 在同等正确性与故障恢复下适配代价和运行成本不高于候选，则**PIVOT 到以通用 Harness 系统实现为主、把科学执行约束列为已知技术的 EEG 应用实例**，而非继续增补第三转换/词表来追求优势。只有上述机制在公平、未见跨族情形下持续产生可解释的差异，才可考虑将工作点一写成有限 EEG-specific 方法贡献。

本轮最终决策仅是 **REFINE 一次，等待导师审查后才决定是否实施/实验**。不自动启动第二工作点或 ASD 应用。若导师要求硕士论文必须有两项算法新颖性，本审查**不提供第二项已成立的保证**，需要另行讨论研究设计，而不能把 Harness 与报告拆成两个创新点。
