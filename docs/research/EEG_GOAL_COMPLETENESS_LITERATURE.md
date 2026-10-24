# EEG 科学目标完备性：文献核查

日期：2026-10-24（Asia/Shanghai）

## 1. 检索问题与纪律

问题不是“如何生成合法 JSON”，而是：候选计划遗漏用户明确要求的操作时，能否从原文侧独立发现未覆盖 claim？检索聚焦
约束解码、NL→plan、计划验证、instruction coverage、工作流 IR/provenance、选择性拒绝和 EEG 分析状态。只记录可访问的
论文/标准原文；VerifyLLM 的方法与结论仅核对到 IEEE 出版页摘要，未独立审计全文实验细节。

## 2. 核心研究表

| 来源 | 原文核实内容 | 能检查什么 | 检查不了什么 | 与本项目重合/启发 |
|---|---|---|---|---|
| Scholak et al., **PICARD**, EMNLP 2021, https://aclanthology.org/2021.emnlp-main.779/ | 增量 parser 在解码时拒绝不符合 SQL grammar 的 token | 语法/部分类型合法性 | 合法 SQL 是否覆盖问题全部语义 | 对应 schema gate；不能解决 SH01 |
| Gestrin et al., **NL2Plan**, 2024, https://arxiv.org/abs/2405.04215 | 分阶段抽取 domain/problem，生成 PDDL 后交给 classical planner；中间结果可检查 | 结构化分解、planner soundness、失败显式化 | 自然语言→PDDL 信息是否无遗漏仍依赖 LLM/专家 | 支持“独立 IR + planner”，但不是 coverage 证明 |
| Grigorev et al., **VerifyLLM**, IROS 2025, https://doi.org/10.1109/IROS60139.2025.11246320 | 出版页摘要描述 NL→LTL 后检查 action sequence 的逻辑一致性与 gap | 已形式化计划的先后/前提检查 | LTL 翻译若先漏目标，后验 checker 未必恢复 | 类似 TGSRG/CIEDG preflight；全文实验未独立核查 |
| W3C, **PROV-O**, Recommendation, https://www.w3.org/TR/prov-o/ | 定义 Entity、Activity、Agent、used/generated/derived relations与 Plan | 数据谱系、活动与派生实体的可交换表示 | 不解析用户意图，也不规定目标覆盖 | 为 source/effective EEG lineage 提供语义，不提供 source claims |
| Zhou et al., **IFEval**, 2023, https://arxiv.org/abs/2311.07911 | 对可客观验证的原子指令做 prompt/指令级 strict/loose accuracy | 已知、可程序验证约束的逐项覆盖 | 开放科学语义先如何分解成约束 | 启发 prompt-level all-obligations 指标与 selective scope |
| Jiang et al., **FollowBench**, ACL 2024, https://aclanthology.org/2024.acl-long.257/ | 多级增加 content/situation/style/format/example 约束；逐项判断满足 | 复杂指令下的细粒度 constraint following | open-ended 项仍使用强 LLM judge，非形式证明 | 启发 source obligation 分解与难度分层；judge 相关误差需披露 |
| Oswald et al., **LLMs as Planning Domain Generators**, ICAPS 2024, https://research.ibm.com/publications/large-language-models-as-planning-domain-generators | 用实例计划集合比较生成 PDDL domain 的行为，报告 7 模型/9 domains | 通过行为等价发现 domain model 缺陷 | 需要可穷举/代表性实例；不能直接覆盖自由 EEG 语言 | 启发用 counterexample fixtures 检验目标模型，而非只看 JSON |
| Colonnelli et al., **SWIRL**, 2024, https://arxiv.org/abs/2407.01838 | 科学工作流低层 IR、DAG→IR 翻译与语义一致性/重写 | 已建模工作流的一致性与等价重写 | 上游自然语言是否完整 | 与 CIEDG/TGSRG 重合较高，不能据 IR 本身主张新颖性 |
| Zhao et al., **EEGAgent**, AAAI 2026, https://ojs.aaai.org/index.php/AAAI/article/view/38867 | LLM 调度 EEG 预处理、特征、事件/模型工具，强调多任务连续推理 | EEG 工具编排与多任务能力 | 论文未给出 source-side omission certificate | 证明问题场景真实，但不直接解决目标完备性 |
| Hou et al., **CogEEGAgent**, 2026 preprint, https://arxiv.org/abs/2607.25045 | 分离 semantic route 与 deterministic scientific authority；错误 template 可内部一致并通过 preflight | 合同、执行、release 边界与封闭 catalogue routing | 论文明确指出 consistency 不能恢复 linguistic intent，semantic fit 仍由模型/curator负责 | 与本问题最直接：支持把遗漏检测视为独立 semantic boundary；尚非完备解法 |
| Robbins et al., **How Sensitive Are EEG Results to Preprocessing Methods**, 2020, https://pubmed.ncbi.nlm.nih.gov/32217478/ | 17 个 EEG studies、多个自动预处理 pipeline，比较频谱/ERP/ERSP 等差异 | 证明 preprocessing 选择会改变下游量 | 不研究自然语言或 Agent | 支持将 transform/stage omission 设为高风险而非普通字段遗漏 |
| Pernet et al., **COBIDAS-MEEG**, Nat. Neurosci. 2020, https://doi.org/10.1038/s41593-020-00709-0 | EEG/MEG 可复现研究的 acquisition、preprocessing、modeling、reporting建议 | 定义应显式记录的科学决策类别 | 不提供 NL parser 或 coverage verifier | 可作为 EEG obligation ontology 的 curator 依据 |
| MNE-Python, **EEG reference / Epoch rejection docs**, https://mne.tools/stable/auto_tutorials/preprocessing/55_setting_eeg_reference.html 与 https://mne.tools/stable/generated/mne.Epochs.html | 重参考改变数据；`drop_bad` 删除 Epoch，质量估计时窗有明确语义 | 核查操作 effect 与输入状态 | 不判断用户是否要求操作 | 为 transform effect、授权风险和 oracle 定义提供官方实现依据 |

## 3. 文献支持的边界结论

### 3.1 结构约束不是目标覆盖

PICARD 的保证对象是目标 formal language 中的 admissible token/parse。一个只包含 `epoch_quality` 的 JSON 完全可以合法，
因此 constrained decoding 不会自动发现缺少重参考和功率。IFEval 的成功条件来自研究者事先知道的可验证原子指令；它
提示应逐项评分，却没有解决开放科学请求如何可靠地产生这份原子清单。

### 3.2 Plan verifier 不能校验未进入 specification 的事实

NL2Plan、VerifyLLM、SWIRL 与 PROV-O 都强化“先形式化、后验证”。但若 NL→PDDL/LTL/IR 转换已经遗漏用户目标，后续
planner 最多证明截断 specification 自洽。这与 CIEDG/TGSRG 的失败同构，不能把第二个 verifier 称为完备性证明。

### 3.3 第二 LLM Judge 是测量器，不是 oracle

FollowBench 对 open-ended constraints 使用强模型 judge，并经过人工核验。这说明 model-based coverage judgment 可作为实验
臂，但其输出仍受相关错误、提示敏感和自身遗漏影响。它适合与候选比较，不适合充当形式 gold。

### 3.4 EEG 提供风险结构，而非自动语义真值

EEG 文献与 MNE 文档支持：重参考、筛除和预处理路径会改变数据实体与下游数值；COBIDAS 强调显式记录分析决策。
因此可以合理定义高风险 obligation 类型、阶段关系和授权作用域。但同义、含蓄、跨句中文/英文表达仍需语义解析，
不能由 EEG ontology 单独解决。

### 3.5 与现有 CIEDG/TGSRG 的空缺

- CIEDG：验证已登记目标的状态、证据、失效与恢复。
- TGSRG：验证已登记目标间的数据阶段与关系。
- 目标完备性：验证原文明示 claims 是否全部进入登记集合。

CogEEGAgent 对“内部一致的错误 template 可通过 preflight”的报告与本项目 SH01 共同说明：semantic coverage 是现有
deterministic scientific harness 的真实信任边界，而不是再加一个 schema validator 就能消失的问题。

## 4. 研究空缺判断

存在一个清晰、可测量但不能绝对证明的空缺：**在有限 EEG 任务 ontology 内，以原文侧高风险 claim 为评价单位，检测
候选 Intent 的遗漏并选择性澄清。** 文献中的约束解码、计划验证、provenance 和 EEG Agent 各覆盖相邻部分，尚未从已核实
材料中发现针对 EEG 自然语言多目标请求的 source-to-intent coverage certificate。

这只是“可能的研究空间”，不是新颖性证明。正式主张仍需系统检索、更独立的人工标注和公平实验证据。
