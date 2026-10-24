# 工作点一候选：科学需求与执行反馈驱动的渐进任务编排

日期：2026-10-25；Issue #32；分支 `research/point1-adaptive-orchestration`。**这是 opt-in 研究原型，不是已证优于专家的算法**。旧 CIEDG/v3、Issue #16/PR #23 的负面结果保持原样。本轮不做第二工作点、真实受试者数据、ASD 报告或临床解释。

## 1. 先行方法与真正需要检验的差别

| 方案 | 已有能力 | 与本原型的区别/重合 |
|---|---|---|
| [EEGAgent 原论文](https://ojs.aaai.org/index.php/AAAI/article/view/38867/42829) | LLM 组织多种 EEG 工具、连续推理和探索。 | 多工具调度非原创；本地原源码的固定 22 导/全局状态是工程差异，不直接证明算法优势。 |
| [CogEEGAgent 原稿](https://arxiv.org/html/2607.25045) | 语义提议与确定性科学控制分离，typed contracts、evidence-bound release、研究确认边界。 | 权限/预检/发布高度重合。本原型考察**一个请求内、根据事件与有效试次的实测反馈决定观察及后续展开**，不是宣称其论文没有此可能。 |
| [ReAct 原论文](https://arxiv.org/abs/2210.03629) | 思考—动作—观察交替，能随环境反馈调整计划。 | 观察反馈本身非创新；这里的可检验新增点只能是 EEG 科学前提和原子目标授权如何约束“是否先观察、展开到哪一层”。 |
| [Plan-and-Solve 原论文](https://aclanthology.org/2023.acl-long.147/)与 [HTN 原方法](https://www.cs.umd.edu/~nau/papers/erol1996complexity.pdf) | 先规划后执行、层次分解与条件任务网络。 | 渐进展开借用成熟思想，不能以“动态分解”四字自称新算法；比较固定计划和同规则动态专家是必要的。 |
| [WINGS](https://wings-workflows.org/about.html)/[Pegasus](https://deelman.isi.edu/wordpress/wp-content/papercite-data/pdf/deelman-fgcs-2015.pdf) | 语义约束、数据依赖、工作流执行/重用。 | 本原型不重做 DAG/来源/缓存，使用现有 Context/Executor；运行时选择仍可由成熟条件工作流表达。 |
| 专业子 Agent 文献/实践 | 不同角色可分工提议与审查。 | 本任务科学前提和反馈都可由单一确定性策略与工具返回处理，增加子 Agent 只会引入同类状态复制/协商成本；本轮不用。 |

事件 Epoch 边界丢失是可核实的 EEG 问题；[MNE 官方 Epoch 教程](https://mne.tools/stable/auto_tutorials/epochs/10_epochs_overview.html)记录边界外试次被舍弃。试次数阈值不能凭通用经验硬设；[ERP 测量报告建议](https://pubmed.ncbi.nlm.nih.gov/27619493/)指出应根据研究分数/可靠性说明阈值。本原型仅接受请求者显式给出的 `minimum_valid_epochs`，不替用户决定充分性。

## 2. 方法输入、信息边界和动作

输入 `Q=(G,F,m,K)`：`G` 是已有 `GoalInstance` 的独立目标及显式参数；`F` 是禁止操作集合；`m(g)` 是请求者声明的最低有效 Epoch 数（默认 1，仅作是否执行其分析的条件）；`K` 是工具预算。`ExecutionContext` 包含 EEGRecord、Profile、Registry、Executor、会话 artifact 与 trace。静态 preflight 使用实际记录通道、采样率、时窗、Profile、模型资源与 ToolSpec，但**事件标签是否真的存在和边界内有效试次**在研究协议里只经已有 `list_events`/`create_epochs` 的结果进入策略决策。所有臂同一信息接口与科学规则；不能把某臂预先告知结果。

状态 `S=(G_unfulfilled, need_graph, observations, artifacts, tool_budget, F)`。`need_graph` 是由 ToolSpec 的 `consumes_artifact` 与单个 EEG `epochs` acquisition recipe 推导的前提层：事件 inventory（在 m>1 且可观察时可能提前剪枝）→ 已授权 `create_epochs` → 当前 artifact 消费者；连续/模型目标不依赖这个 recipe。它不是另一套 Executor，所有动作仍为 `ExecutionContext.execute(ToolRequest)`。静态 preflight 一旦目标非法则整单零工具拒绝；缺事件标签零工具澄清，不用 inventory 自行替用户选标签。

动作空间：`OBSERVE`（真实 `list_events`）、`MATERIALIZE`（真实 `create_epochs`）、`ANALYZE`（PSD/幅值/事件功率/严格模型等真实已注册工具）、`CLARIFY/REJECT/SCIENTIFIC_STOP/PUBLISH`。只能用请求中获授权的目标和事件 scope；不筛选试次、不修改标签、时窗、参考或数据。`list_events` 被禁止时，可在显式标签已给的条件下直接建 Epoch，并只根据实际合法输出继续。

规则不是声称概率校准的 VOI。它是**确定性前提价值判断**：若全任务原子发布且一个低成本观测可证明某个必要条件不满足，就先观测，避免后续无谓工具；若 m=1 或观测被禁止，则不做该额外 inventory。Epoch 构建后，真正有效试次（非原始事件数）决定是否运行消费者。严格 Profile/资源检查在执行前完成，避免无意义模型调用。

```text
preflight_every_goal(Q, Context)    # 所有目标、禁令、Profile、资源、参数
if any missing/illegal: clarify_or_reject_without_tool
group epoch consumers by exact event scope
if any group has m>1 and list_events is authorized:
    inventory = Context.execute(list_events)       # 一次覆盖全部组
    if any required label count < its m: science_stop_without_publication
for group in event groups:
    epochs = Context.execute(create_epochs, exact_scope)
    if fail or any valid per-label count < m: science_stop_without_publication
for group: execute its consumers on exact returned artifact + fingerprint
for independent goal: execute direct tool
publish only if every explicit user goal succeeded; otherwise no complete bundle
```

**这不是类型路由器**：D2/D3/D4 的用户目标类型相同，但不同实测事件数/有效 Epoch 数使执行止于不同层；D5/D6 组合任务中前提是否满足改变后续连续 PSD 是否需要执行。**这也不是旧质量 Pilot**：没有质量阈值、换窗或自动试次筛除，策略解决的是观察/展开/停止时机。

## 3. 不变量、复杂度及信任边界

- 所有目标先静态预检，不能在完成一个目标后才发现另一个显式通道或模型 Profile 非法。
- 任一被禁工具不调用；事件标签与最低试次数不由系统擅自补写；事件边界造成的有效试次数减少必须从真实 producer 输出核对。
- 只有全部目标的当前结果才发布 `evidence_bundle.publication=all_goals`；失败时工具结果可审计，但 `publication=none`，不包装部分结果为完整报告。
- 不保证原 LLM 对自由语言目标提议完整；本轮主实验是结构化目标后的策略验证，不能用它证明语义理解。工具数值 oracle 独立 SciPy/NumPy；自动测试通过不等于真实数据科学效度。
- 若 `g` 个目标、`e` 个不同事件 scope、`s` 个数组样本，分组/排序与前提检查约 `O(g+e)`（不含 ToolSpec/数组校验）；事件与数值工具、artifact 指纹仍付各自真实成本。该策略无需全记录 SHA 重复计算，但原工具可能对 Epoch 指纹线性扫描；要报实际 wall-clock，不只报调用数。

## 4. 实际迭代：原子多作用域门控

预冻结 D1–D9 首跑：候选与 Strong Expert 均 9/9、14 次调用；固定顺序 9/9、15 次。额外开发探针 D10（**后设，不作为未见成绩**）：同一请求含 `stimulus` 和 `control` 两个事件 scope、各要 2 个有效 Epoch，默认记录只有 1 个 `control`。初版按每个 group 完整执行，轨迹为 `list_events → create_epochs → event_bandpower → list_events`，虽安全停止且不发布，却做了本可避免的 producer/consumer，候选/Expert/固定三臂都发生。首次原始结果保存在 `results/point1_adaptive_probe_initial.json`。

修订不是补关键词：把单 scope 串行展开改为**全局前提层的先决门**，一次 inventory 检查全部 scope，再逐 scope 建 Epoch、最后才运行消费者。候选和 Strong Expert 同步实现，修订后 D10 均在一次 `list_events` 后科学停止，固定仍 4 调用且不误发布。最初评价器将“无谓调用”并入科学 `all_ok` 是评分层错误；修订后将 `global_gate_ok` 作为独立成本指标，保留第一次记录，不用效率差异刷科学正确率。旧 D1–D9 数值结论不变。这个迭代改善了多目标编排，但**强 Expert 同样容易实现，尚不构成独立方法证据**。

## 5. 可证伪预测与结果边界

协议、开发/未见案例与独立 oracle 见 `POINT1_ADAPTIVE_ORCHESTRATION_PROTOCOL.md`。H1：同目标不同事件/边界反馈走不同执行层；H2：原子组合可较固定用户顺序减少不可发布的消费者，但预计与强 Expert 持平；H3：增加纯只读连续能力若需要目标名专用逻辑，则“通用适配”主张受损。**只有同规则动态 Expert 难以同等成本达到并在未见跨任务场景反复成立时，才考虑更强论文方法主张。**本文没有概率模型，也没有宣称 Bayes 最优或跨设备临床有效性。
