# 多任务 EEG Harness 任务—能力—方法—证据矩阵（Issue #26）

## 划分原则与现状

“多任务”按科学对象与前置条件区分，而非工具数量。同一 Epoch 再计算一个统计量仍属事件相关分析。选定三类：①无需事件的连续信号；②事件锁定的 Epoch/条件分析；③严格 Profile/资源约束下的既有模型推理。这覆盖当前真实工具边界，不暗示完整 ERP、ERD/ERS、临床分类或多数据集泛化。

旧 CIEDG `integrated_method/v11.py::ContractGraphResidualPlanner.__init__` 只接受 `event_workflow`；`ConstraintCarryingEEGAgentV11.run` 对其他任务转用 `ConstrainedPlanRunner`。其记录级工具有 preflight 与 ledger，却没有同一 goal-evidence 图的状态绑定、失效传播和结果发布。PR #23 的只读 `epoch_variance` 扩展仍在 Epoch 家族内，未检验跨任务类型；强 Expert 与候选 7/7、37 次调用持平（[审计](https://github.com/lzy123-web/eeg-agent-harness/blob/9a185361f87990ff7a2a712a2e45a0d62336b80c/docs/research/POINT1_EXTENSIBILITY_AUDIT.md)、[结果](https://github.com/lzy123-web/eeg-agent-harness/blob/9a185361f87990ff7a2a712a2e45a0d62336b80c/docs/research/POINT1_EXTENSIBILITY_RESULTS.md)）。此处不挪用其代码或结果作为新版成绩。

## 逐族矩阵

| 任务/自然语言目标示例 | 输入与科学前提 | 输出/所需证据 | 已有能力、资源与当前路径 | 旧 CIEDG 覆盖及核心缺口 | 新版机制目标、验证数据 | ASD 报告关系 |
|---|---|---|---|---|---|---|
| 连续信号信息：“这段记录的采样率和通道是什么？” | 当前 EEGRecord；来源、实际采样率和通道名，不需要事件 | 元数据与来源证明；不能推断范式 | `record_info`、`EEGRecord`、`EDF_NATIVE`；原生 Agent/单工具 planner 已实现 | 走单工具 `ConstrainedPlanRunner`，不进入 CIEDG 图 | record 作为有版本的证据输入，目标与 answer-required 由 contract 决定；合成无事件及已授权 EDF 本地验证 | 可形成“数据范围/采集信息”，但采集方案仍需外部资料 |
| 连续窗幅值/绝对频带功率：“在指定通道和 0–2 秒测量功率” | 显式 channels/start/end、合法窗口、Profile；PSD 是 Welch 绝对功率 | 数值、单位/方法、准确参数和记录版本，不能当 ERP/ERD/ERS | `amplitude`、`psd`、`EEGRecord.slice`、Executor；EDF 本地 smoke | 旧 CIEDG 无 record-binding graph；多连续目标不能共享同一剩余目标/失效机制 | record input policy + 目标图，变更记录内容后使证据失效；合成数值 oracle/无事件反例 | 仅在参考、年龄、任务匹配与质量证据充分时用于研究描述；无通用儿童正常范围 |
| 连续质量：“先测质量并报告该窗频谱，不要删数据” | 质量范围、经验阈值和当前处理阶段；禁止自动筛选 | 质量指标、有效性声明和后续功率来源 | `record_quality` + `psd`；质量规则未临床校准 | 两独立工具可调用，但旧图不共同追踪两个目标和源状态 | 同一 record graph 的双目标，禁止转变保留；合成劣质段/混合目标测试 | “可解释性限制/需人工复核”；不能转成儿童功能评分 |
| 事件相关：“对明确标签分 Epoch、测质量、汇总条件功率” | EventSet、显式 labels/tmin/tmax/baseline；至少 1 秒用于频带工具；授权作用域 | 事件计数、接受/边界拒绝数、质量、条件特征及 Epoch lineage | `list_events/create_epochs/epoch_quality/epoch_summary/event_bandpower`；旧 CIEDG 已覆盖；R3 只能本地用数字代码 | 旧 CIEDG 此族有图，但不能与 record 目标走同一方法；冻结成果保留 | 新版同一个图引擎仍跑事件链；合成事件故障、数值/来源 oracle；R3 只作为以后独立应用验证 | 若范式、标签与参与者映射未知，仅能报告数字条件，不解释动作/社交能力；不是完整 ERP/ERD/ERS |
| 严格模型推理：“对合法双极通道的一秒窗做已有模型推理” | 仅 `tuev_bipolar_22`、256 Hz、存在且校验一致的权重、合法通道/1 秒窗；训练来源源码未提供 | 输入契约、权重来源/哈希、输出形状和研究用途边界 | `seizure_detection`，已知本地 EDF/权重可用；当前走单工具 planner | 旧图不绑定模型输入与资源条件；不能拿 22 导数量代替 Profile 合法性 | 同一 record graph 目标，复用现有 planner+Executor 的 Profile/资源 preflight；本地合法资源一次推理及缺权重/错 Profile 拒绝 | 既有癫痫模型**不**作为 ASD 状态推断或儿童能力证据；仅通用方法第三族验证 |
| ASD 儿童辅助评估报告 | 经授权受试者/年龄/任务/量表等背景、科学有效指标与解释依据 | 观测—计算—解释—限制分层的证据链，专业复核 | 未实现完整报告；R3 缺范式与身份映射 | 不属于旧 CIEDG 自动报告能力 | 本轮仅映射证据需求，不生成真实儿童报告或诊断 | 最终综合应用，必须单独验证且遵守临床边界 |

## 数据与验证安排

## 本轮实际方法路径核对

上表“新版机制目标”是设计前缺口，不可当完成证据。当前实现详见 [方法验证](MULTITASK_METHOD_VALIDATION.md)：连续无事件任务实际进入 `SharedEvidenceGraphCore` 的 record 绑定/结果门；事件任务实际进入**同一个 core** 的依赖/状态/证据门，Epoch 参数与筛选授权仅为事件策略；模型任务以合法本地 EDF+权重进入同一 core 并执行原模型一次，错 Profile/缺资源明确拒绝。三者复用同一个 Registry/Executor/Context，且没有任何伪造 Event/Epoch。未覆盖自由语言跨族双目标、ASD 报告生成、ERP/ERD/ERS 和模型跨队列有效性。首次真实 DeepSeek 事件请求有失败记录，不能用基线工具存在或后来一次成功替代方法可靠性证据。

- **合成 EEG**：提供已知 PSD/事件/故障与无事件反例，可用于程序真值和有界真实 LLM；合成模型概率无科学意义。
- **原 EEGAgent 的合法 EDF/权重**：只本地完成一秒模型输入和输出形状验收，记录校验与缺资源行为；不向外部模型发送 EDF 或特征。其训练数据来源仍为“源码未提供”。
- **R3**：沿用 PR #25 的应用层证据，不作为通用方法定义；缺权威标签、参与者、组别和采集协议，不能做 ASD 比较。
- 其它公开 EEG：本轮不下载。若以后引入，先核对许可、采样率、montage、任务/事件定义、受试者独立划分和数据治理。

## 文献约束与创新边界

[WINGS 原始系统论文](https://doi.org/10.1109/MIS.2010.9) 已用数据/组件语义约束排除无效科学工作流；[W3C PROV-O](https://www.w3.org/TR/prov-o/) 已定义使用、派生和失效等来源关系；[CogEEGAgent 原论文摘要](https://arxiv.org/abs/2607.25045) 亦分离语言与科学权限。故“声明工具输入/输出、画 DAG、记录 provenance”不是独创新颖性。可研究的问题是：在**同一 EEG 运行图**内跨连续记录、事件派生和模型条件维持不可偷换的科学输入绑定，并在状态失效时精确回收目标证据；是否优于合理强专家仍待公平实验，不能提前宣布。
