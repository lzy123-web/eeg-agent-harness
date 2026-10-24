# EEG Intent Compiler v1 方法设计

## 1. 研究问题

在允许 LLM 解释语言的同时，如何避免把模型的局部 evidence-span 表述差异误判为 EEG 意图错误，并继续确定性保护事件标签、时间窗、试次筛选授权、参考通道、重参考授权、source stage 和禁止操作？

## 2. 文献与现有方法边界

- PICARD 表明可以在生成/解析边界用形式约束拒绝结构上不合法的候选，但其对象是 SQL 语法和 schema，不能直接提供 EEG 科学授权语义：https://aclanthology.org/2021.emnlp-main.779/
- CogEEGAgent 明确区分 LLM semantic authority 与 deterministic scientific authority，并使用 typed contracts/grounded execution；这支持本项目的层次边界，但不能据此宣称本实现新颖：https://arxiv.org/abs/2607.25045
- Fast Evidence Extraction 说明高风险输出需要显式证据跨度与独立核验；它研究的是摘要证据抽取，不直接解决 EEG 操作授权：https://aclanthology.org/2024.fever-1.24/
- Scientific workflow 研究强调 NL semantic layer、deterministic workflow generation 和 domain knowledge 分层；该架构思想与本项目高度重合：https://arxiv.org/abs/2604.21910
- ARTEMIS 使用低复杂度 distinguishing traces 验证 NL→formal specification，提示不能只看 schema 合法性；本轮只借鉴“翻译与语义验证分开”，没有复现其算法：https://cs.stanford.edu/~trippel/pubs/mendoza_ICSE26.pdf

## 3. 候选路线比较

### 路线一：扩充 `CONCEPT_ANCHORS`

优点是改动小、可离线；缺点是会把 `remove/discard/reject/剔除` 等不断堆成词表，无法表达 action—object、授权作用域、直接目标与科学前置条件的区别。对已见 S02/S06 容易过拟合。未选择。

### 路线二：第二个 LLM/NLI Judge 决定接受或拒绝

能处理语言变体，但增加请求和随机性；更关键的是，不能把试次删除或重参考授权交给另一个模型的自信判断。可作为将来的软证据，不作为安全 gate。未选择。

### 路线三：类型化 Claim–Evidence + Requirement Projection（选择）

模型只提出 IntentSpec；编译器执行四个彼此分离的步骤：

1. **Claim frame 验证**：exact span 仍必须来自原文，但概念不是单关键词命中；安全操作需同时满足 action 与 EEG object 角色。
2. **Requirement projection**：只把 Registry/Task contract 真正要求用户给出的 slot 投影为 required；模型多报的 channels、band definitions 等 advisory unknown 不产生澄清。
3. **Deterministic prerequisite closure**：授权筛选必然依赖质量测量，因此 `epoch_quality` 可以由已验证的 `trial_selection` 科学依赖派生，而不要求用户再说一次固定“质量”关键词。
4. **Scoped safety gate**：筛选/重参考必须同时具备 exact operation span、exact authorization span、同句作用域、无显式否定，以及各自必需参数。参考通道、事件、时间窗仍不得猜测。

选择理由：它能用同一规则解释 S02/S06/R05，不需 case ID 特例；错误可以分解为 frame、slot、scope、closure；输出仍是现有 IntentSpec，可直接进入 TaskSpec/Obligation Ledger/CIEDG。

## 4. 科学不变量

- `trial_selection` 没有明确授权永不 execute；否定优先于模型正向 objective。
- `epoch_rereference` 没有明确授权或 reference_channels 永不 execute。
- labels、tmin、tmax、continuous channels/start/end 仍须由 exact evidence 支持。
- Event bandpower 的“所有现有通道”和 Registry 固定 bands 是工具策略，不是必须由用户补充的科学 slot；不允许模型自创 band edge。
- mixed pre/post transform scope 仍澄清；raw branch 不可观测仍拒绝。
- 编译器只替换意图校验接口，不修改冻结 CIEDG 的 Planner、lineage、recovery 或 Evidence Gate。

## 5. 协议

- 30 例：development 14、holdout 16，中英文、改写、否定、授权作用域、多目标、真实缺参和 unsupported 请求。
- I01/I02/I03/I04 是旧 S02/S06/R05/R11 regression，明确属于已见开发题。
- manifest SHA-256：`b14fcb611ac2f8c854fb5b543860f2e76597be4b4e13ddf576f6ce95d544af9f`。
- 只有一名人工审校者；没有第二作者独立标注，因此不报告 inter-annotator agreement。
- 模型原始字段、v0/v1 validator、端到端 disposition、危险误接受、误拒、请求/token 分开统计。
- 真实 API 硬上限 32 requests / 80,000 tokens；仅使用合成元数据。
