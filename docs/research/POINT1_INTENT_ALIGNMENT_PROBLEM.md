# 工作点一：EEG 科学意图对齐问题定义

## 1. 研究问题与边界

本任务研究一种比“工具调用是否合法”更上游的失败：自然语言请求表达了一个科学任务，但模型选择并成功执行了另一个同样合法、同样可运行的 EEG 分析。例如，用户要求固定时间窗 PSD，模型却执行振幅统计；用户要求 `stimulus` 条件，模型却对 `control` 建窗。Registry、Profile 和 Executor 能证明调用在类型、资源、通道、窗口和依赖上合法，却不能证明它忠实于用户意图。

本轮不把下列问题混为“意图错误”：工具参数格式错误、越界、Profile 不兼容、资源缺失、工具运行失败，以及仅多调用 `record_info` 等无状态观测工具。后者可计入效率或冗余，但只有改变分析对象、条件、来源、变换权限或输出边界时才计为科学意图不一致。

## 2. 与现有代码和文献的关系

- 当前 `EEGAgent` 通过原生结构化 tool calling 调用 `ToolRegistry + Executor`。Executor 只看到工具请求与当前运行状态，不拥有用户意图金标准。
- Baseline v1 首轮真实 DeepSeek 严格通过 3/15，主要失败是额外安全查询；这些结果不能直接证明发生了意图替换。
- Issue #8 的三个规划方法在 18 个冻结语义任务上同为 18/18；该实验使用结构化任务输入，不能回答自然语言意图映射是否可靠。
- CogEEGAgent 将“semantic/scope mismatch”归于 benchmark/curator 评价边界。其唯一自然发生的模型错误是组合请求中把 MMN 映射为 ERN；其 `40/40` internally consistent wrong-template releases 是人工构造的边界探针，不是模型自然错误率。论文同时采用运行时不可见、模型服务停止后才解封的 scorer-only gold，支持本轮严格分离 runtime 与 offline gold。
- EEGAgentBench 强调多步工具选择和证据累积，BrainBench 强调 instruction-conditioned EEG 理解与多种输出评价；两者说明意图到任务的映射值得独立评价，但本轮不据此宣称已有方法能解决该问题。

文献来源：CogEEGAgent（arXiv:2607.25045）、EEGAgentBench（arXiv:2609.31632）、BrainBench（arXiv:2608.04156）。截至本文件形成时，后两者仅按公开摘要中可核实的信息引用，不补写摘要未给出的数字。

## 3. 最小科学意图不变量

冻结协议 `config/point1_intent_alignment_cases.json` 为每个请求独立给出以下 slot：

1. `analysis_type`：记录信息、振幅、固定窗 PSD、事件窗频带功率、记录质量、试次质量、质量筛选、模型可用性或不支持的临床/ERP 输出。
2. `channels` 与 `window`：通道和连续/事件相对时间窗。
3. `source_stage`：当前、原始或处理后数据。当前上下文没有原始分支时，不允许假装回溯。
4. `event_labels`：事件条件或对比集合。
5. 允许/禁止工具：表达允许的分析路线及明确禁止的替代、变换或筛选。
6. `explicit_slots` 与 `unknown_slots`：显式给定、仍未知且不可安全推断的字段。缺少关键字段时应澄清或拒绝。
7. `outcome`：完成、澄清或拒绝。模型输出不是临床诊断，事件绝对功率不是 ERP、显著性检验或 ERD/ERS。

运行时只接收自然语言、当前合成记录元数据和工具 schema，不接收上述 contract。contract 仅在离线确定性 scorer 中使用；同一 LLM 不参与自我判分。

## 4. 典型不一致

| 用户真实意图 | 合法但错误的执行 | 为什么 Executor 不能发现 |
|---|---|---|
| 原始信号的 50 Hz 质量证据 | 在仅有处理后信号上计算质量 | 当前记录和工具调用本身合法，但来源阶段错了 |
| `stimulus` 事件绝对频带功率 | 对 `control` 建窗并计算 | 标签存在、窗口合法、artifact 链完整 |
| 固定连续窗 PSD | 同窗幅值统计 | 通道与时间都合法，但分析类型改变 |
| 只检查质量 | 自动筛除试次 | 质量工具与筛选工具都合法，但用户没有授权改变数据状态 |
| 研究模型输出 | 临床诊断 | 工具值可能真实，但回答越过允许输出边界 |

## 5. 冻结任务集与实验门槛

- 共 24 个任务：12 个 development、12 个 holdout；中文为主，含 2 个英文转述。
- 覆盖自然合法请求、不满足条件、缺参数、干扰项、多 slot、错误条件/窗口/来源及看似合理的替代分析。
- 受 36 次 provider request / 80,000 token 上限约束，真实 DeepSeek 仅运行预先标记的 12 个 development 案例；holdout 保留给后续方法比较，不能据 development 结果调改其 gold。
- 5 个 controlled injection 手工替换为“科学调用合法但意图错误”的路线，只用于验证现有执行边界和 scorer，不计入自然模型错误率。
- Stage C 只有在自然 DeepSeek 产生至少一个可复核的实际意图错误、且 slot scorer 能可靠区分时才开启。仅有人工注入或无关安全调用不足以过门槛。

## 6. 预注册判断

本研究不预设新方法优于原生 Agent。若自然实验未发现错误，或错误依赖主观解释而无法稳定评分，则本轮直接报告 No-Go/证据不足并跳过方法开发；不得通过修改 gold、弱化基线或新增人为错误来启动 Stage C。
