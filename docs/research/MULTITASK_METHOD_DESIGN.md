# 工作点一新版本：跨任务 EEG 目标—状态—证据图设计（Issue #26）

## Issue #26 纠偏后的三项清单（2026-10-24）

| 分类 | 内容与依据 |
|---|---|
| 保留 | 现有 `EEGRecord/EventSet/EpochSet`、Profile、`ToolRegistry/Executor/ExecutionContext`，旧 CIEDG 的目标依赖 token、内容与身份分离、失效传播及局部恢复思想；保留旧 v1.1 路径和历史实验原样。新版本已完成的记录内容绑定、跨族原子预检和本地模型输入核验继续保留。 |
| 任务专有化 | `labels/tmin/tmax/baseline`、源/筛选后 Epoch、试次质量与授权筛选属于事件适配策略；通道窗与严格 22 导模型约束属于对应记录/模型策略。它们不能充当通用图的默认字段或默认前提。 |
| 重构 | 初版 `MultiTaskContractGraphPlanner` 继承 event-only 的 `ContractGraphResidualPlanner`，虽然复用了同一个 frontier、失效与发布过程，却仍继承 `_compile_dependencies` 的 Epoch 筛选分支、`state_dict` 的 Epoch 默认结构、`next_action` 的筛选特例，以及按记录/事件分别预检的入口。不能把它直接称为已完成的共同机制；新版需把“目标依赖、输入类型、适用性、状态更新、失败与证据发布”移到任务中性的核心，事件语义变为适配策略。 |

上述分类来自 [Issue #26 最新纠偏](https://github.com/lzy123-web/eeg-agent-harness/issues/26#issuecomment-6382639080) 与本地真实调用链审查。下文为初版设计记录；最终实现与局限以迭代/验证文档为准，不以保住旧 CIEDG 架构为目标。

## 要解决的具体缺陷

冻结 v1.1 CIEDG 的依赖图仅接收 `event_workflow`；`ConstraintCarryingEEGAgentV11.run` 将连续信号与模型任务交给单工具 `ConstrainedPlanRunner`。于是同一 Harness 虽有多类工具，却没有对连续记录/模型输入和事件 Epoch 一致的剩余目标、输入版本、证据失效与恢复机制。PR #23 的 Epoch 只读 consumer 扩展没有解决此跨科学对象缺口，也未证明较强 Expert 更低维护成本。

## 方案比较与选择

| 路线 | 优点 | 主要问题 | 决定 |
|---|---|---|---|
| A. 旧 v1.1 保持 event-only，外层 router 对连续/模型各调用原单工具 Planner | 变更最少 | 没有共同目标/状态/证据路径；record 状态变化不使已完成工具结果失效 | 排除 |
| B. 把连续记录伪装成一个事件/Epoch | 可勉强套用旧 input policy | 伪造事件科学语义，模型输入条件被混淆 | 排除 |
| C. 新版 graph contract 显式增加 `record` 输入策略，把 record 与 Epoch 目标放入同一前沿、证据 token、失效传播、局部恢复、发布机制；旧 v1.1 运行路径不变 | 面向实际缺口，复用旧图执行与现有 Registry/Executor；可测试混合目标及内容变更 | 仍需目标编译和科学 preflight；本轮语言层仍有单意图限制 | **选用** |

WINGS 已用语义约束表达科学组件与数据适配（[原论文](https://doi.org/10.1109/MIS.2010.9)）；[W3C PROV-O](https://www.w3.org/TR/prov-o/) 已形式化使用/派生/失效；[CogEEGAgent](https://arxiv.org/abs/2607.25045) 已区分语言与科学权限。因此本工作不能把“新增图”“显式 metadata”单独声称创新。研究问题是 EEG 中**记录窗、事件派生与严格模型输入三种科学对象**如何在同一执行图内绑定当前内容与来源、保留科学约束，并在变化后精确撤销旧证据。相对公平强专家的价值尚未验证。

## 核心契约与伪代码

当前实现中任务中性核心为 `v2_graph.py::SharedEvidenceGraphCore`；它没有 `labels`、`Epoch` 或疾病默认字段。目标合同由 `v2.py::MULTITASK_CONTRACTS` 声明工具、作用对象策略、依赖、状态角色及答案需求；`compile_multitask` 对整个目标集预检，并与 Executor 使用的 `ToolSpec` 核对消费/产出 artifact 类型和 Profile。各目标实际返回值类型、产出 artifact 指纹在统一图中再次核查，然后才可生成可发布 token。`record` / `record_model` 输入绑定由记录内容、来源、参考、采样率、事件与本地权重哈希组成；`source_epochs` / `effective_epochs` 是事件策略，不是核心前提。

核心与适配层关系：

```text
同一 TaskSpec / GoalContract / ToolSpec
      → 整组目标静态适用性预检（record/window、event/epoch 或 model 条件）
      → SharedEvidenceGraphCore：frontier → Context/Executor → 类型/来源门
                             → 当前状态比对/依赖失效/有界恢复 → 证据发布
      → Answer Gate（只引用当前有效结果）
```

未来新任务族可增加目标合同与输入策略，不应复制 graph runtime。旧 v1.1 继续单独存在以保护历史实验；这里的复用是**思想与数据结构**，不以继承 event-only 类作为强制条件。与旧方法/强动态 Expert 的不同不在于“有 DAG”或“有 ToolSpec”，而在于试验中的跨科学对象状态绑定与统一证据发布；是否有超出合理 Expert 的独立价值尚未正式证明。

新 `MultiTaskRequest` 为 parsed-task 边界：`objectives`、每目标参数、共享事件参数、禁止操作。自然语言仍由已有 EvidenceBoundIntentInterpreter 解释，不在本轮开展 ESOCC 或自由语言目标完备性新研究。`compile` 只允许 Registry 现有工具对应的明示目标，未知目标/不受支持组合整体拒绝。

```text
request -> immutable TaskSpec + obligation ledger
for each requested goal and graph dependency:
    validate profile / channels / time / events / epoch duration / resource
if any goal invalid or forbidden: reject entire task before tool execution
graph.frontier := contracts with all dependencies evidenced
for each action:
    bind current record content+source OR current Epoch artifact ID+fingerprint
    execute through existing ExecutionContext -> Executor -> Registry tool
    create goal evidence token with arguments, input binding, dependency tokens
    after every state observation, reconcile changed bindings and descendants
    retry bounded failures; only reuse scientifically equivalent consumer evidence
release only answer-required evidence bound to current state
```

`record` binding必须同时涵盖 EEG 数组内容、采样率、通道、参考/导联、来源及处理元数据；不把原始数组送给 LLM。记录内容或来源变化会使 record-level 结果、`list_events/create_epochs` 及其下游证据失效。Epoch consumer 继续沿用旧 `source/effective` artifact ID+fingerprint、授权筛选和旧图的局部恢复。科学操作仍只经现有 Executor 执行，不创建第二套 EEG 算法或执行器。

## 不变量与任务边界

1. 无事件记录的连续任务不创建虚假 EventSet/EpochSet；事件任务缺事件/标签时预检拒绝。
2. 同一任务任一目标缺参、资源缺失、Profile 不符或变换未授权时，**整体**拒绝，不静默执行可完成子集。
3. record window 使用真实采样率、通道和时间边界；模型另需指定合法 Profile、256 Hz、1 秒输入及权重。通道数相同不等于 Profile 合法。
4. 记录或 Epoch 输入变化后，当前回答不得引用失效的旧 token；content 等价复用与 source identity 不混同。
5. `epoch_quality` 只是经验筛查证据，不能默认删试次；绝对 PSD 不能被称 ERP/ERD/ERS 或 ASD 评分。
6. answer gate 由合同声明的 `answer_required` 目标决定，不再对连续/事件写两套结果发布路径；数值须指向真实 ToolResult 标量。

新版本保留旧 v1.1 类和历史正式实验；可提取并改造目标图机制，但不能以“只能继承旧事件类”为架构限制。事件与连续必须在新版共享任务中性的 frontier、证据 token、输入绑定、状态失效、错误边界和结果门；模型若资源可用，也只作为合法调用协议证明，而非 ASD 应用模型。

## Issue #28：能力声明→目标实例→共同执行→逐目标证据（opt-in v3）

### 路线比较与研究定位

| 路线 | 解释与编译 | 状态/证据边界 | 本轮判断 |
|---|---|---|---|
| 把每个分析名交给独立脚本/单工具 Agent | 最容易接入自然语言 | 同名不同参数易被覆盖；跨记录/Epoch 状态无共同失效和证据门 | 排除，不满足共同核心 |
| 层级任务网络（HTN）按任务族写方法 | 子任务层级与显式前提清楚 | 每种组合都需人工设计方法，维护成本可能接近强专家；当前请求实例与产物身份仍需另建 | 后续公平对照可采用，不作为本轮主实现 |
| Registry 支撑的能力目录 + 带参数/来源的目标实例图 | LLM 只解释用户正向目标；内部 `list_events/create_epochs` 由编译器补足；同能力可重复 | 复用已有 `SharedEvidenceGraphCore` 的绑定、失效、前沿、Executor 与证据 token；实例 ID 是发布键 | **选用**，改动有界且可检验 |

这一路线借鉴成熟科学工作流的类型/约束思想（[WINGS 原始论文](https://doi.org/10.1109/MIS.2010.9)）、层级规划中任务分解思想（[ICAPS HPlan 论文](https://icaps22.icaps-conference.org/workshops/HPlan/papers/paper-12.pdf)）与来源关系（[W3C PROV-O](https://www.w3.org/TR/prov-o/)）；**图、ToolSpec、结构化 Tool Calling 和 JSON 证据本身不是新的算法贡献**。EEG 专用问题是不同科学对象（整段记录、明确连续窗、特定事件 Epoch、严格模型输入）的参数作用域及科学来源是否能在同一状态图中被正确保持；相对强动态 Expert 的优势尚未做公平实验。

### 实际结构和不变量

`v3.py::capability_catalog` 从当前 `ToolRegistry/ToolSpec` 和 Profile 枚举可见能力，再由小型 EEG 科学适配表给出必填用户参数与单位/类型。新增能力仍需在 Registry 中实现、在科学适配表中声明参数/单位并接受已有 Planner/Executor 前置条件；若涉及新数据对象，还需一项输入绑定策略。**这不等于零改动扩展**，但不应为每种组合新增路由或复制执行器。当前 v3 仅开放 record_info、record_quality、amplitude、psd、seizure_detection、epoch_quality、epoch_summary、event_bandpower；筛选/重参考仍留在旧受控方法，不伪装成 v3 已支持。

`v3_agent.py::InstanceGoalEEGAgent` 用一次原生 Tool Calling 提交全部用户正向目标；`request_quote` 定位实例范围，`concept_quote` 独立定位科学操作，`parameter_quotes` 逐值引文。Harness 分配 `g1…gn` 稳定的任务内 ID。阶段审查后新增结构性绑定：若同一参数槽出现不同值，每个值的引文须与本目标的原文锚点重叠；公共通道等同值可共享引文。澄清时冻结已确认目标的顺序、类型、锚点、概念、参数、来源阶段与禁止操作，只允许填缺项；唯一缺失的参数槽可从补充文本取得值，多个同名缺项仍需更明确的关联。`v3.py::compile_instances` 先对整单进行能力/Profile/资源/窗口/事件/禁止操作检查，再将每个用户目标映射为自己的 `GoalContract`；同参数事件目标才共享内部 `list_events/create_epochs`，内部节点不是用户要发布的输出目标。缺参合并澄清；不支持/不适用整体零调用拒绝；本版不允许静默部分执行。

```text
Registry/ToolSpec + EEG 科学适配 → 可用能力目录
自然语言 → 原生结构化 submit_eeg_goals → 目标实例 g1…gn / 引文 / 参数 / 禁止操作
整单 preflight → 实例合同 + 参数完全一致时共享的内部 producer
SharedEvidenceGraphCore → ExecutionContext → 原 Executor → 原 EEG 工具
输入与权重/产物指纹 + 依赖 token → 仅闭合任务发布逐目标 evidence_bundle
合成应用层只消费 bundle，不重算 EEG、不生成诊断
```

同一 `psd` 的两个窗口是两个实例；相同工具、实参、输入绑定及依赖语义的完全相同实例可共享已完成结果，但各保留独立 token。事件 `labels/tmin/tmax/baseline` 全部参与 producer scope 哈希，不同 scope 不复用 Epoch。连续质量默认整段；若用户给范围则严格检查两端，不把整段质量冒充窗口质量。明确 raw/processed 来源阶段与当前记录不符时拒绝，不发明另一版本。模型仍必须满足 `tuev_bipolar_22`、256 Hz、已有权重和窗口；资源哈希绑定输入。状态变化后共同核心只失效受影响的实例及后继；独立记录目标可保留。

`evidence_bundle` 由实际 `ToolResult` 与 `GoalEvidence` 构造，每项含 ID、能力、参数、引文、来源/阶段、输入绑定、依赖证据、方法/单位、请求 ID、原始结果、研究限制；任务含未完成目标。仅证据闭合时发布数值，异常返回结构化未完成信息。回答文本只概括目标列表并指向 bundle，不让 LLM 回填自由编造的数值。应用层样张见 `v3_application.py`，临床栏目仍未建立。

当前能力接口须分层阅读：`capability_catalog` 只给当前 Profile、事件存在性、采样率和已配置资源下可由 v3 入口执行的能力，发现时仅检查资源文件存在，不加载权重；`capability_inventory` 区分 `available_v3`、`v3_unavailable_for_current_context`、`internal_prerequisite_only`、`registered_not_migrated_to_v3`。未注册工具/科学目标是真正不支持，不能与旧入口已注册但 v3 未迁移的筛选、重参考混为一谈。当前 8 项为 **v3 实现上限**，并非每份记录都可用 8 项。适配表仍须人工维护，不能宣称任意工具零改动接入。

交付采取整单闭合发布：bundle 记录 expected/published 数和 `publication`。预检或运行期故障时公开 `goals=[]`，所有请求目标列为未发布；运行 trace 仍可用于故障审计，但先成功目标的数值不会被应用误读为整单完成。合成应用入口检查完整计数和无未履行目标。该一致性门是工程安全性，并不证明开放语言解析完备。

### 明确限制和待检验研究价值

当前参数关联依赖 LLM 引文与局部同一事件共指；没有独立解决开放自然语言目标完备性，也没有对复杂跨句范围给出形式语义保证。严格引文可能误拒合法请求。`SharedEvidenceGraphCore` 的全记录哈希在大记录上有计算成本；v3 为不改旧 v2 行为而局部复用了相同的绑定实现，后续可在稳定后整理。新能力仍需科学前提和单位适配，并非自动扩展。正式比较应在冻结任务与故障集后，让 Native Agent 和强动态 Expert 拥有同一 ToolSpec、Profile、状态、预算和科学规则，再做实例身份、参数作用域、证据绑定、失效复用的消融；本轮合成开发例**不构成胜负证据**。
