# PR #27 跨任务 Harness 开发验收与研究判断（2026-10-25）

## 协议与证据等级

本轮先冻结 [C1–C8 请求、合成数据、目标参数和 oracle](MULTITASK_ACCEPTANCE_PROTOCOL.md)，再运行 Fake 与真实模型。C1 连续记录信息/幅值/PSD，C2 事件试次/质量/功率，C3 严格 Profile 下的既有癫痫模型，C4 连续与事件组合，C5 缺窗澄清，C6 无事件科学停止，C7 未支持的 ERP/ASD 诊断，C8 频带配置改变后的证据失效。这里的任务数不等于独立数据集数；这是一组有限开发验收，**不是未见统计评测**，更不是 CIEDG 对强 Expert 的优势实验。历史 Issue #16 结果与旧候选代码均未改。

执行路径为 `InstanceGoalEEGAgent → capability_catalog/目标实例 → SharedEvidenceGraphCore → ExecutionContext/Executor/ToolRegistry → 当前证据 token → evidence_bundle`，没有独立模拟执行器。合成样本才允许调用外部 LLM；波形/试次矩阵不进入模型消息。数值 oracle 另从合成数组用 NumPy 或 SciPy Welch+积分计算，不取工具答案当真值。谱估计同用 SciPy，故这是切片、积分与条件聚合的独立调用核对，不是对 Welch 库本身的交叉实现验证。

## 首个结构性缺陷与方法修订

C8 在旧图中实际复现：`freq_bands.alpha` 从 `[8,13]` 改为 `[9,11]` 后，已完成的连续 PSD 与事件条件功率仍被视为有效，`next_action()` 为空，应用继续交付旧数值。原因是证据只绑定 EEG/Epoch 内容，未绑定工具实际使用的科学分析配置。这是跨连续与事件任务族的**共同证据生命周期错误**，不是某一句 Prompt 或事件单工具 Bug。

比较过三种边界：全图无条件重跑会误失效记录信息与试次计数；给 PSD/事件功率各写一套调用补丁会复制规则；在 Registry `ToolSpec` 声明配置依赖，由共同图把该配置纳入证据 identity/semantic identity 并按依赖撤销，是本轮选择。当前 `psd` 与 `event_bandpower` 均声明 `freq_bands`；配置变更只失效这两个目标及其真正下游，`record_info/epoch_summary` 保留。输出逐目标包含实际频带配置、采样率、输入绑定、依赖 token、方法与限制；合成应用示例直接消费此字段。独立 oracle 核对两个新 alpha 值，且旧/新值不同。此处实现了科学配置参与状态传播；`ToolSpec` 元数据与 PROV 式依赖并非原创，只有在公平跨任务实验中证明额外价值后才可谈方法贡献。

## 确定性与本地资源结果

| 检查 | 实际结果 |
|---|---|
| C1/C2/C4 数值 | 幅值由 NumPy 重算；连续和逐 Epoch alpha 功率由独立调用 Welch+积分重算；C2 stimulus 2 有效/1 越界，C4 control 1 有效；禁止筛选时没有筛选调用。 |
| C3 | 缺权重时零推理调用、明确拒绝；本地已有原 EEGAgent 权重开启时对合成、已验证 22 导/256 Hz 输入输出一窗两类有限分数。未计算诊断准确率。 |
| C5–C7 | C5 首轮零 EEG 工具调用，补窗后原目标/通道不漂移；C6/C7 零 EEG 工具调用并拒绝。 |
| C8 | 频带改动使两个频谱证据失效并重算，不相关结果保留；bundle 披露实际配置且可 JSON 序列化。 |
| 完整回归 | `compileall`、`pip check` 通过；`unittest discover` 273 tests / OK / 15 skipped；设置本地既有权重后 273 tests / OK / 13 skipped。 |
| Fake 套件 | C1–C4 精确目标类型和参数均匹配；C5 澄清后匹配；C6/C7 安全拒绝。Fake 固定 payload 不能证明自然语言理解。 |

运行方式：在项目根设置 `PYTHONPATH=src`，用已有 `eegagent` 环境执行 `python -m compileall -q src tests`、`python -m unittest discover -s tests -q`、`python -m eeg_harness.research.integrated_method.v3_acceptance`。模型可选地通过 `EEG_HARNESS_MODEL_PATH` 指向本地已存在权重；不要把权重或真实 EDF 提交。验收 JSON 及原始联网响应只保存在 Git 忽略的本地 `artifacts/`，不存在仓库中。`v3_acceptance --real` 需要合法本地服务配置与显式合成输入，默认套件不会把任何受试者数据发送外部。

## 有界真实 DeepSeek：失败按时间保留

请求名为 `deepseek-chat`，本轮保存的十个响应均报告实际 `deepseek-flash`。首轮 C1–C6 共 **7 completion / 15,416 tokens**（单请求最多 1,000 输出 token、35 秒、零重试）：C1、C3、C4 完成且目标**类型与参数**匹配冻结表；C2 `UNGROUNDED_GOAL_OR_PARAMETER` 安全澄清；C5 首轮缺窗澄清正确，但补窗时 `GOAL_SET_CHANGED_ON_RESUME`；C6 安全拒绝。C7 是确定性未支持测试，未付费运行。旧首轮记录不覆盖。

检查原始响应后，C5 失败是模型把同一原文引文末尾 `。` 并入，冻结比较把标点变化误认目标漂移；修订只忽略引文边界标点，仍冻结目标类型、值、来源与禁止操作。C2 首轮事件功率目标的引文不含事件词但同句前目标有完全相同的显式 scope；修订允许按**先前已落地、同句且完整相等的事件 scope**建立来源引用，并保留 `scope_source`，不同 scope/跨句负例仍零执行澄清。这是安全接口修复，不能叫目标完备性方法。

仅对失败的 C2/C5 做一次有界复测，共 **3 completion / 6,410 tokens**：C5 完成且类型/参数匹配；C2 仍安全澄清。第二次 C2 原始输出在功率目标中遗漏 `labels` 参数，虽然前目标明确 `stimulus`，当前验证器不能把缺失的科学参数默默补齐。该残余归为语言编译/作用域绑定不足，**不是** EEG 图执行或数值错误。没有继续为 C2 写句式特例、改变冻结 gold、把安全拒绝改记成功。两轮合计 10 completion / 21,826 tokens，均为合成记录元数据、工具描述与必要合成结果；无真实受试者 EEG 外发。一次开发复测不形成成功率估计。

## 研究问题、能力和停线

| 层面 | 当前可证实 | 未证实或不支持 |
|---|---|---|
| 通用多任务 Harness | 连续、事件与严格 Profile 的现有模型可以分别走同一图/Executor；合法组合的实例参数隔离、内部 producer、原子发布和配置敏感失效有确定性核验。 | 多数据集、所有 EEG 任务或开放自然语言目标完备性；新版未迁移的筛选/重参考不能说已在 v3 可用。 |
| 科学正确性 | 工具输入/Profile/资源门、来源与配置绑定、失效重算、逐目标结果和限制可审计。 | ERP、ERD/ERS、Sleep/MDD、ASD 诊断及已有癫痫模型的临床解释均不支持。质量经验阈值未临床标定。 |
| 工作点一可能贡献 | EEG 不同科学对象与分析配置在共同目标—证据图里的可追踪绑定、局部撤销/恢复与逐目标发布，是值得正式检验的候选。 | Registry、DAG、参数 schema、provenance、Prompt 与标点/共指修复本身是成熟技术或工程；旧 CIEDG 对同规则强 Expert 持平，不能宣称优势。 |
| 最有价值的下一步 | 冻结可比的跨族任务扩展集，给 Native/同规则强动态 Expert 同样能力、规则和预算；量化科学正确性、恢复、人工适配量及端到端语义错误。先为 C2 类缺参/共享作用域建立独立错误分类，不在开发例上刷 Prompt。 | 不再通过增加事件近义词、局部规则或单案例成功数制造创新；不无界增加新任务工具。 |

与 [WINGS 科学工作流](https://doi.org/10.1109/MIS.2010.9) 的语义组件约束、[W3C PROV-O](https://www.w3.org/TR/prov-o/) 的使用/派生/失效、[MNE Welch](https://mne.tools/stable/generated/mne.time_frequency.psd_array_welch.html) 及 [MNE Epochs](https://mne.tools/stable/generated/mne.Epochs.html) 的科学对象和参数要求相比，当前机制的潜在论文价值只在 EEG 跨对象的可执行约束和动态证据语义的**组合效果**，而非发明图或元数据。本轮是开发验收，尚未提供公平强基线和统计证据；工作点一维持“候选/证据不足”，不升级为已确证创新。

## ASD 辅助评估应用边界

`evidence_bundle` 现在可交付记录来源/Profile、采样率、通道/窗或事件 scope、处理阶段、实际频带定义、质量观测、方法、数值、输入/依赖 token 和限制；应用端可以安全形成“本次分析做了什么”的研究性证据摘要。它仍不具备授权记录—儿童映射、年龄/发育背景、R3 事件官方释义、采集与预处理史核验、适龄同范式参考、行为/临床资料、模型外部验证及专业审核。没有这些，不能从 PSD/质量或癫痫模型分数生成 ASD 诊断、严重度或能力评分。当前 `render_auxiliary_evidence_note` 是**合成数据证据样张**，不是儿童报告生成系统。
