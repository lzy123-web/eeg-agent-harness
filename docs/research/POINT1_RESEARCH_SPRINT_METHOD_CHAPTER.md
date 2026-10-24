# 工作点一方法章节草稿：多任务 EEG 的目标—科学对象—证据执行及其创新性边界

> 性质：供硕士论文第三章结构讨论的**批判性草稿**，不是已获验证的原创算法声明。日期 2026-10-25；依据 PR #27 已审查代码树与 Issue #30 决策。旧 CIEDG/v3 保留且未改。这里仅研究工作点一，不讨论第二点或临床应用。

## 1. 问题定义与适用范围

多任务 EEG Agent 的输入不是单一工具名，而是自然语言中的一组分析目标、各自参数、科学对象与操作授权。例如同一请求可要求连续窗频带功率与事件锁定的条件功率；它们依赖同一个信号源，却不共享事件作用域、试次集合或输出含义。逐工具参数合法仍不足以保证最后交付的结果对应用户要求的**当前**科学对象。数据/参考/频带/事件范围/派生 Epoch/模型 Profile 改变时，已取得的证据可能部分过期。

令 `R` 为一条有采样率、通道、参考、来源和处理历史的 EEGRecord；`A` 为从记录派生的科学数据对象集合；`G={g_i}` 为用户目标实例，每个 `g_i=(capability, θ_i, scope_i, stage_i, authorization_i)`；`C` 为专家声明的工具输入、类型、资源与状态影响合同；`E` 为工具结果及其来源版本。Harness 需要输出下一合法动作、澄清/拒绝/科学停止，或逐目标证据包 `B`。其正确性至少要求：（i）目标对应用户意图；（ii）每步科学前提满足；（iii）输出版本与当前 `R,A,C` 一致；（iv）仅在全部获授权目标闭合时发布。

这些条件分属不同信任边界。代码可证明**给定正确 `G,C`** 的许多校验；不能由内部闭合推论 LLM 没漏用户目标，也不能由合成数值核验推断真实 EEG 阈值/临床适用性。CogEEGAgent 已明确区分语义提议与确定性科学授权，此区分不是本项目原创。

## 2. 当前系统的可复述方法（实现说明，非创新宣称）

`v3_agent.py::_attempt` 提议目标实例和引文；`v3.py::capability_catalog/compile_instances` 从同一 Registry 和 Profile 做资源与参数预检、合并科学 scope 完全一致的事件前提；`SharedEvidenceGraphCore` 调度依赖闭合节点，持有 `ArtifactBinding`/`GoalEvidence`，检测变化、撤销失效后继、有界恢复；`ExecutionContext.execute` 经现有 Executor 执行工具；`run_instances` 把每个用户目标的当前证据发布到 bundle。核心仍有事件 `TaskSpec("event_workflow")` 的编译分支，不能声称完全任务无关。

可抽象为以下基于目标实例的工作流算法；它基本复用 DAG、契约、来源、版本化缓存技术：

```text
Input: request text U, record R, registry T, profile P, resources M, budget K
G,F ← language_proposal(U)                 # 提议，不是意图真值
if any required goal parameter, profile, resource, authorization fails:
    return clarify_or_reject_without_tool()
D ← compile_graph(G, T, P)                # 用户目标 + 必需的内部前提
while tool_calls < K:
    invalidate_evidence_with_changed_input_or_declared_config(D, E, R, M)
    if every requested goal has current evidence: return publish_bundle(E,G)
    n ← one dependency-ready unresolved node
    if no n: return science_stop()
    if matching evidence with same tool, args, input, dependencies exists: reuse it
    else: result ← Executor.execute(n.tool, n.args, current_context)
    if invalid result or unrecoverable failure: return science_stop()
    bind(result, input_identity, output_identity, dependency_tokens)
return budget_stop_without_complete_publication()
```

**不变量（有前提）**：同一目标结果不得跨不等价输入、参数与依赖复用；未授权状态转换不得执行；失败或部分完成不得冒充全部交付；严格模型只在其 Profile/资源满足时执行。前提包括 `ToolSpec`、GoalContract、数据/Profile 描述及工具数值实现无漏/无错。`config_keys` 漏掉一个数值影响项就可能破坏第一条，程序无法凭哈希自动发现专家漏写的语义依赖。

**计算代价**：设 EEG 数组有 `N` 字节，目标图有 `V` 点、`E_d` 依赖边，某次扫描中记录 digest 为 `Ω(N)` 读取与拷贝开销；当前 `v3.py::_record_digest` 使用 `np.ascontiguousarray(...).tobytes()`，非连续数组可能增加拷贝。模型 digest 还读权重，成本与权重大小线性相关。拓扑遍历/撤销至少与受影响节点和边相关。实际性能必须量墙钟、峰值内存与 EEG 工具耗时，不能只报工具调用次数。

## 3. 最接近已有工作与差异判决

| 比较对象 | 已有机制 | 本项目能正当主张的差别 |
|---|---|---|
| EEGAgent | 多 EEG 工具由 LLM 调度、探索与解释。 | 形式化数据/Profile、证据有效性和失败边界是本地系统工程改进；未有公平实验说明其方法层优势。 |
| CogEEGAgent | EEG 语义提议 + typed scientific contracts + 确定性权限 + evidence-bound release。 | 我们关注动态记录/Epoch/模型版本的局部恢复，但这只是研究重心差异，未证明不可由它的合同/工作流实现。 |
| WINGS / Pegasus / PROV | 语义类型/数据约束、来源、DAG、既有结果重用和增量恢复。 | EEG reference、scope、有效试次、Profile 是领域元数据与合同内容；**尚不是新的图算法**。 |
| 同规则 Strong Dynamic Expert | 获得相同科学规则和反馈后可表驱动决策。 | 旧正式比较科学正确性、调用数持平；一次扩展的专用 LOC 也未减少。 |

依据：[EEGAgent 原论文](https://ojs.aaai.org/index.php/AAAI/article/view/38867/42829)、[CogEEGAgent 原稿](https://arxiv.org/html/2607.25045)、[WINGS 语义工作流](https://wings-workflows.org/about.html)、[WINGS/Pegasus 来源原论文](https://doi.org/10.1002/cpe.1228)、[Pegasus 论文](https://deelman.isi.edu/wordpress/wp-content/papercite-data/pdf/deelman-fgcs-2015.pdf)、[PROV-O 标准](https://www.w3.org/TR/prov-o/)。不是对原系统在我们 EEG 数据上的实测复现。

## 4. 本轮否决的候选：统一科学状态读写投影

设每个工具/目标声明 `Read(g)` 与 `Write(g)`：`Read` 可含记录内容、参考、通道、采样率、事件范围、源/有效 Epoch、频带、模型权重；`Write` 为派生 artifact 与科学状态变更。候选规则是 `sig(g)=H(tool, θ, project(state,Read(g)), sig(parents))`，状态变化后撤销签名不匹配节点并重算后继。它能收束当前分散的 `input_policy/config_keys`，但**给同等领域 Read/Write 声明的 typed DAG + 输入签名**会生成相同失效和重算集合。因此没有成立的独立算法预测。科学投影遗漏或错写也可能误发布，不能承诺自动 sound。

阶段 1 在实现前以五例跨连续/事件/模型依赖作可表达性测试，见 `POINT1_RESEARCH_SPRINT_DECISION.md`。所有关键真值都能由合理 typed workflow 和表驱动 Expert 表达；原旧实验既无正确性优势也无维护成本优势。结论是**投影可作为将来可靠性重构，但不可按当前证据写为硕士论文工作点一的新方法**。本轮未实施它，避免把维护工作包装成贡献。

## 5. 两个 EEG-specific 转向及证伪条件（均未立项）

### A. 分析目标相对的数据质量与可观测性

**科学问题**：同一 EEG 的“可用”不应由单一幅值/噪声阈值决定；频域功率与事件平均会受不同污染，notch/滤波后某种原始干扰甚至不可观测。候选机制可用目标相关的不确定性/有效性估计，在同授权候选操作内决定继续、换数据窗或科学停止。这个问题有 EEG 特点，但**非无人研究**：[SME 原论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC8169536/)已论证 ERP 数据质量依赖具体分数；[PREP 原论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC4471356/)及[MNE-BIDS Pipeline 官方步骤](https://mne.tools/mne-bids-pipeline/1.9/features/steps.html)已有自动质控与配置相关重跑。仓库 `EVIDENCE_ADAPTIVE_EVALUATION.md` 在 16 个受控案例中与同证据 Strong Expert 均 16/16、32 calls，阈值在本地记录对照高度敏感。现有质量证据不具跨设备/儿童范式校准，且转向自适应策略可能与被暂停的第二工作点重合。

**真正可证伪主张需先满足**：预先定义连续频带与事件指标各自的误差/覆盖 oracle；合法策略对照得到完全相同质量、备选窗口/通道、预算；候选须在新来源/新范式中显示可重复的有效性或人工规则维护收益，不能只胜过无质量门控的固定流程。需要经授权、独立标注或可控污染的跨范式数据与校准方案。本轮现有依赖只足以复制已知合成阈值结果，不能区分候选与强 Expert；**不选为当前可运行新方法**。

### B. 多专业能力协同与证据冲突

**科学问题**：连续频域、事件条件和模型证据对来源/作用域可能提出不相容主张，如何在共同 EEG 记录上以可审计规则停机或请求澄清。简单增加子 Agent、投票或辩论是通用多 Agent 技术；CogEEGAgent 的确定性科学授权/证据发布和 WINGS 的约束满足已覆盖重要部分。只要冲突可归约为同一合同的参考、Profile、scope 不一致，**单一 Executor + typed preflight 已足够**，新子 Agent 无必然价值。需要有独立专家判定的冲突集、确定性专家系统公平对照、专门衡量新增专业能力时的冲突发现增益。当前没有该实验真值或必要的协同任务，搭建子 Agent 只会增加 API 与调度成本；**不选**。

| 方向 | 所需资源 | 可区分指标 | 实现估计与停线 |
|---|---|---|---|
| A 目标相对质量 | 独立数值误差/覆盖真值、跨范式/设备校准、同权限专家策略 | 科学误发布、无谓拒绝、下游指标误差、人工规则成本；分别与 Expert 比较 | 非小型“改几个阈值”原型可解决；先有校准与 oracle，再考虑方法。若仅与 Expert 同规则持平则停止。 |
| B 协同冲突 | 能明确归因且由单一合同不易表达的真实冲突任务、独立专家真值 | 正确停机/澄清、冲突定位、扩展维护量与额外成本 | 先证明单 Agent+typed constraint 无法同样表达；证明不了就不建立多 Agent。 |

**阶段 2B 裁决：两条目前都没有可辩护、在现有资源下可执行的最小独立性主张，故不选、不造 PoC。** 这不是证明它们永远没有研究价值；只是遵守本轮“无主张就停”门槛。复跑旧质量合成数据或生成两名相互争论的 Fake Agent 只能检验工程，不会补齐缺失的科学真值。

## 6. 现有证据、限制与论文建议

旧 CIEDG 相对强 Expert：正式 parsed-task 24/24 对 24/24，109/109 calls；相对 whole-plan replay 省 12 次，但其不能充当唯一强基线。PR #23 同族扩展 7/7、37/37、42/41 LOC。v3 的 C1–C8 是开发验收，C2 真模型漏事件标签后未完成；S09 是无效协议例，不能修饰为候选成功。仓库 273 个回归仅证明既有实现未退化；不证明论文贡献。

**当前工作点一科学结论：STOP 以“科学状态投影/目标证据图是独立创新算法”继续投入；KEEP 多任务 Harness 为系统工程成果与论文实验平台。** 论文第三章可以准确叙述需求、系统方法、合同、可靠性设计与局限，但不可把本草稿包装成已证的新算法或把旧开发集当正式研究增益。若学位要求独立方法贡献，须与导师重新界定可取得真值的研究问题和资源，先做针对最近邻的预注册可区分实验，再决定下一实现；不自动转入第二工作点。最精确的恢复入口是：确定获得目标相关质量/跨范式校准材料，或能构造不被单一 typed workflow 表达的专业冲突任务；任一条件未满足时不继续加状态转换或词面规则。
