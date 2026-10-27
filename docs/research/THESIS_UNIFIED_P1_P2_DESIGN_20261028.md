# 开题统一研究方案：从 EEG 科学结果到有证据支持的报告（2026-10-28）

> **定位**：研究方案与初步原型说明，非已验证的创新结论。承接工作点一研究分支 `research/point1-eeg-task-memory` 的 Issue #52；本分支仅做工作二研究与两点统一论证，不合并 main，不改写旧实验。

## 1. 一条逻辑主线

**总问题：在多任务、多轮修订的 EEG Agent 中，怎样让科学结果从计算、任务续用直到最终报告，始终保持适用条件、版本和证据的一致性？**

工作一（已在 Issue #52 形成可运行原型）：解决**科学分析过程中的结果交付与复用**。以 Plan-and-Execute 建立 DAG，定义同一子任务的多项结果要求；使用真实 EEG ToolResult 判定已声明的任务交付，并按 DAG 依赖从 HiAgent 式任务档案读取摘要、精确字段、处理工件和原始行动—观察。保存数据来源、通道/事件范围、时基、参数与版本；修订保留旧证据，失效的下游重新核查。不是发明 DAG、记忆或科学验证算法。

工作二（本轮明确的方法研究，尚未完成 LLM 实验）：解决**这些正确分析结果向自然语言报告转换时出现的事实错配、过度解释，以及上游修订后的过时结论**。同一 P1 证据对象既决定下游分析能否消费，也决定报告中的某句事实/解释是否有可追溯依据，以及上游变化后哪些句子需要重审。

**两项工作不是“一个 Agent 加一个 RAG”。** 它们共享一条可版本化的依赖链：

`用户科学要求 → P1 子任务/交付项 → 真实 EEG 结果及版本 → P2 计算事实 Claim → 解释 Claim → 报告`

P1 维护前两条依赖，P2 维护后两条依赖。P1 的 `task_revised/changed_keys` 事件会传到 P2 的 Claim 失效/核验机制。双方不复制另一套虚构的数值事实。工作一单独无法保证报告忠实；工作二如果只有自然语言摘要，难以知道原结果的真实 EEG 时间窗、事件工件及版本。

## 2. 与现有研究的关系：哪里是借鉴，哪里是拟适配

EEGAgent（AAAI 2026）已有 EEG 工具编排与报告；LLMCompiler 已有依赖执行；HiAgent（ACL 2025）已有子目标 AO、摘要及恢复；CogEEGAgent（2026 预印本）已有科学合同/证据控制；ALCE、FActScore、医学 claim-verification 工作已经研究引用支持与原子陈述核查。

**不能说它们“解决不了”，也不能仅凭把两项成熟技术组合就断言已经证明新效果。** 本文的拟研究增量是：把 EEG 执行侧的多交付/部分完成/版本工件身份与报告侧的数值事实、科学解释和版本变化统一建模，设计可核验的 Claim 生命周期和定向失效流程，检验它对复杂 EEG 自然任务的额外可靠性/成本是否有意义。若强 P&E + 强 RAG 配合等价能力也能达到相同效果，保留最简单可行实现并收缩主张。

## 3. 工作二具体架构、对象和责任

### 3.1 P1→P2 唯一权威证据接口

读取 `TaskPlanController.graph/PlanGraph.resolve_ref(task_id,key,revision)`，从 `TaskSpec.outputs` 得到原 `result_id`，再从 TaskStore/TaskEntry 读取真正的 `result`、`parameters`、`evidence.source`、`evidence.binding`、`revision_of` 和行动—观察定位。

- `EvidenceRef = (task_id, delivery_key, field_path, revision=current|指定历史版)`
- `EvidenceFact = (value, 字段级单位, record, 实际scope, source, processing_version, 原result_id, fingerprint)`
- `ReportRequirement` 表示用户要求的报告条目、分析不足及其关联的 P1 交付，不能仅根据 Planner 已声明条目宣称整个原用户意图无遗漏。

**禁止**把 “P1 节点 completed”当作数值真值，把上游失败结果当作有效交付，把工具级单位当字段单位，或者把历史版标成当前结果。所有数值都从实际 ToolResult 读取，复用现有 `result_semantics.py` 的字段单位语义。

### 3.2 陈述对象与有区别的核验

- `measurement`：直接数值事实（例如“记录 A 的 C1 通道在 0–2 s 窗口的 alpha 功率为 x V²”），要求准确 EvidenceRef，程序逐字段检查值/单位/来源/范围/版本。
- `difference/ratio`：两个实际结果的差值/比值，程序计算，不让 LLM 心算，也不由模型自己写“允许比较”取得科学授权。跨窗口/跨记录的比较必须存在 P1 已声明且**实际交付**的合法比较任务，仍仅代表描述性差异。
- `limitation`：对应未交付的具体 `(task_id, delivery_key)`，说明实际未完成原因；禁止一条泛泛“部分完成”掩盖其它应覆盖的结果。
- `interpretation`：连接已经核验的事实 Claim 和精确的解释资料段落（source_id、原段落、研究人群、实验范式、适用范围与资料版本）。单有 DOI/URL 不自动通过；需要独立支持判断，涉及健康或个体能力时需专业复核或保留不确定性，不因一般关联升级为个人诊断。

实现为 `PlanGraph/TaskEntry → EvidenceResolver → ClaimGraph → FactVerifier/KnowledgeReview → ReportComposer`。模型提出候选报告内容，程序持有事实真值、结果身份和修订记录；未知科学解释默认待审核，不存在“自动核验任意自然语言全文”这种保证。

### 3.3 动态证据更新与定向修订

示例：T2 的 PSD 最初对应 A/0–2 s（R_old），报告有 C1“功率值”、C2“相较另一个窗口升高”、C3“基于该差异的解释”。用户把时间窗改为 4–6 s，P1 产生 R_new，保留 R_old，并发布 `task_revised(changed_keys=[alpha])`。

P2 执行：

1. 根据 `(task_id,key,current)` 定位引用受影响结果的 C1；
2. 沿 Claim→Claim 依赖找出 C2、C3；使旧事实、比较和解释失效或待重审；
3. 对当前证据重新计算事实/比较，解释重新检索/核查，生成**新的 Claim 版本**，不悄悄覆盖旧版；
4. 不依赖 T2 的其它记录 B 陈述保留；`revision=1` 明确标注为“历史”的 C1 可以保留历史事实，绝不作为当前事实覆盖需要；
5. 证据缺失/未完成则保留安全部分报告并明示限制，不强行编造缺失脑电结果。

这一步是两个研究点在**数据结构和状态更新方法上的真正耦合**，不是传 JSON 或再加一次 RAG。

## 4. 本次最小代码原型与明确边界

已有 `applications/evidence_statement.py` 仅验证**单条确定性模板数值陈述**，不能检查普通 LLM 报告。新增原型设计为 `applications/report_evidence_graph.py`：

- `TaskPlanEvidenceResolver`：从实际 P1 PlanGraph + TaskStore 解析当前或指定历史证据，使用真实字段语义；
- `EvidenceClaimGraph.add/_verify`：核查 measurement/difference/ratio/limitation，解释陈述只进入 `REVIEW_REQUIRED`；
- `affected_by/refresh`：依赖闭包定位随 P1 修订必须重审的 Claim；同一旧 Claim 不会自动“换数值继续通过”；
- `release`：只输出经过核验的结构化计算事实及明确不足；揭示用户报告要求中的未覆盖交付，不发布未经解释审核的医疗结论。

**当前本轮本地独立原型：12 个确定性测试通过**，涵盖错值/单位、缺结果、差值/比值、未授权比较、未完成限制、旧/新版、变更影响、漏报事项及解释文献不足。尚未在正式仓库 CI 上确认，未接实际 LLM 生成、文献 NLI 或 TC 模型，不冒充端到端效果。

## 5. TC 复用边界：真实可用而不是虚构功能

TC `autodl_latest_data/stage1+stage2_inference.py` 的实际逻辑为 Stage1 输入特征文本生成报告，Stage2 从报告输出情绪能力轻/中/重标签；并**不是**输入任意 EEG PSD 就直接完成 ASD 医学诊断。已有研究材料确认当前 Harness 尚缺 TC 输入中 `higuchi_fd`、`arousal_*`、FAA、`parietal_alpha`、`beta_gamma_mean` 的一致算法/ROI/标签定义；训练数据划分、能力标签依据和使用许可需另行核实。

因此主 P2 实验优先使用当前 EEG Executor 已能真实计算且有字段语义合同的通用研究描述报告；TC 作为可选草稿生成器，只在特征映射、权重/资源、许可及目标标签验证后接入。私有 TC 源码/权重/个人数据不提交公开仓库，顶层会执行训练或连接图库的脚本绝不直接 import。Stage2 不等同 ASD 诊断。

## 6. 对照实验与独立创新归因

### P1：沿用 Issue #52

强 A：正常 P&E + 完整合法结构化 Result / 版本 / 工件 / 重规划 / 检查工具；B：A + 通用任务记忆；C：工作一的科学交付自动核验与依赖感知分层证据。使用相同工具、条件和权限。主要看完整**自然模型会话**科学目标、错用来源/时基/版本、重复计算与实际 tokens。已有 Issue #52 只是受控离线机制，尚未证明 C 优于 A。A-equivalent 加同样验收后成功拦截人为错误，说明自动检查不是不可替代的新算法。

### P2：固定相同的 P1 证据和同一报告生成模型

D0：给完整结构化 EEG 结果和全部合法分析条件直接生成；D1：D0 + 正常文献 RAG 和常规句级/全篇事实审核；D2：本文证据→Claim 的字段级门控 + 状态/版本/依赖一致性 + 定向重审。三组使用**相同科学结果、知识语料、LLM、预算**，不故意去掉 D0/D1 的字段、引用或信息。

任务条件包括正常全结果、事件试次数不足、跨记录/事件/连续混合、旧新窗口修订、未完成部分交付、反复修改；保留用户真实自然任务，不用 Gold DAG / 预定模型动作输入。

指标分别报告：
- 数值/单位/记录/范围/版本错误率；
- 逐原子陈述可支持率（区分“有引用”和“引用真正支持”）、无依据解释率；
- 必要结果及未决限制**覆盖率**，不能通过删掉困难内容刷准确率；
- 修订后过期陈述残留率、受影响陈述定位 Precision/Recall、未受影响内容保持率；
- 全链 API 输入输出 tokens、调用/延迟、文本修改量和额外计算次数。

消融 D2-no-science-claim-check、D2-no-dependency-refresh（改全篇重新生成）、D2-no-missing-coverage。文献解释需分级人工/专业评价；普通生成文本需要独立 claim 提取和全文核验，不能把结构化 Claim 自我校验结果当作全文准确率。

### 最终联合验收（体现“一篇论文”）

**同一条自然会话**：用户多任务 EEG 分析→P1 获得真实多项结果、部分未决、版本证据→P2 生成带依据的研究报告→用户更改一个计算窗口→P1 增量执行→P2 识别被影响的事实/比较/解释并更新，同时保留无关段落和历史事实。对照直接 P&E→直接报告以及 P&E→强 RAG/全篇核验。P1、P2 仍各有独立实验归因；联合实验报告端到端证据一致性、错误和成本。

## 7. 开题可直接使用的拟创新点与推进顺序

**研究内容一：科学子任务交付与分层证据记忆协同执行方法。** 在成熟计划执行基础上，以 EEG 实际数值、科学条件和多结果合同组织任务完成及证据复用；面向持续修订与混合分析验证完整交付正确性及成本。

**研究内容二：基于可版本化执行证据的报告陈述约束与增量一致性维护方法。** 将实际结果和适用条件映射到可核验的事实陈述与研究解释；在 P1 上游数据/分析版本改变时自动定位和重审相关陈述，避免证据与报告脱节。

优先实现真实 P1→P2 证据接口、ClaimGraph 及合成离线更新案例；随后再做通用 LLM 报告草稿和许可文献检索，最后安排真实模型对照及 ASD 研究用途应用。不通过新训 7B 模型来证明“工作二做了工作量”。

**5 分钟答辩一句话：** 第一项工作解决脑电 Agent 怎样正确产生、交付和复用科学结果，第二项工作解决这些有版本的结果怎样忠实支持报告、结果变化后如何只更新受影响的结论，两个研究点共享同一套结果身份、科学适用条件和依赖关系。

## 主要文献与事实边界

- EEGAgent (AAAI 2026) https://ojs.aaai.org/index.php/AAAI/article/view/38867
- CogEEGAgent (2026 预印本) https://arxiv.org/abs/2607.25045
- HiAgent (ACL 2025) https://aclanthology.org/2025.acl-long.1575/
- LLMCompiler (ICML 2024) https://arxiv.org/abs/2312.04511
- ALCE (EMNLP 2023) https://aclanthology.org/2023.emnlp-main.398/
- FActScore (EMNLP 2023) https://aclanthology.org/2023.emnlp-main.741/
- Biomedical Claim Verification (BioNLP 2025) https://aclanthology.org/2025.bionlp-1.14/
- Medical KG Fact-Checking (AAAI 2026) https://ojs.aaai.org/index.php/AAAI/article/view/41317
- 医学引用核验的局限 (Nature Communications 2025) https://www.nature.com/articles/s41467-025-58551-6
- P1 前期代码及真实负结果：本仓库 Issue #52 的 DESIGN / PROTOCOL / PROPOSAL_SUMMARY；工作二单句前驱：`applications/evidence_statement.py`。

> 禁止将没有临床验证的 EEG 指标与 ASD、情绪能力等级做个体诊断性关联；报告限于研究用途辅助描述。
