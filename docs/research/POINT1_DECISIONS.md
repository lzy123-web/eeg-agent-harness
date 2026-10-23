# 工作点一集成方法：技术决策记录

## D0：范围与恢复协议

- 日期：2026-10-23。
- 决策：只在独立分支 `research/point1-integrated-method-v0` 开发 opt-in 方法；Baseline v1 默认行为不变。
- 原因：Issue #10 的目标是形成可运行方法对象，不重写 EEG Core，也不覆盖既有负结果。
- 状态：已采用。

## D1：选择约束携带计划作为 dominant mechanism

比较三条路线：

1. scientific state-aware plan synthesis；
2. intent→plan→evidence constraint propagation；
3. 复用旧 Planner 的低复杂度 route+preflight。

选择：采用 `intent→plan→evidence constraint propagation`，命名为 Constraint-Carrying EEG Plan（CCEP）。它将显式值、unknown、禁止操作、来源和证据要求作为不可在恢复中弱化的 obligation；继续复用旧 Planner，不再扩展 Issue #8 已判定 No-Go 的 EEG 专属搜索排序。

原因：现有 `TaskSpec` 无法表达参数是否由用户明确给出，导致 Planner 无从识别模型擅自补全；单纯更强 Prompt/preflight 又缺少执行后证据闭合与恢复单调性。CCEP 提供可检验的跨阶段机制，但新颖性暂记 `unproven`。

反证条件：若公平强 route+preflight 在新的未见任务上完全等价，或 ledger 只产生重复校验而无动态状态/恢复价值，则该机制只能作为工程控制面，不作为论文创新。

## D2：不建立第二套执行器

- 决策：CCEP 只新增 opt-in orchestration/contract 层，工具执行仍由现有 `ExecutionContext → Executor → EEG Tools` 完成。
- 原因：避免分叉数值逻辑、artifact store 和错误语义。

## D3：运行时与离线 gold 隔离

- 决策：IntentSpec 由 LLM 根据自然语言和脱敏状态生成；不读取 Issue #9 case contract 或 scorer gold。确定性 gate 只验证 IntentSpec 自身与当前 Context。
- 原因：防止数据泄漏并保持真实 Agent 条件。

## D4：用原文证据绑定意图 slot

- 决策：LLM 输出的每个关键 slot 必须携带用户请求中的精确连续片段；string label/channel 的归一值必须实际出现在该片段中。关键 slot 无有效证据则 clarify。
- 原因：只让 LLM 声明 `explicit=true` 无法阻止其把 record 中的 `stimulus` 当成用户给定值。原文证据不是离线 gold，可在运行时确定性验证。
- 限制：中文数值表达、同义词和指代的稳健解析仍依赖 LLM；初版只要求数值有限且有精确原文片段，正式实验需要更严格的 span/value normalizer。

## D5：筛选必须先形成质量证据

- 决策：`quality_selection` 是 Planner 中一个声明式复合目标，固定复用单个 Epoch artifact，先执行 `epoch_quality`，再把同一 artifact 交给 `select_quality_epochs`。
- 原因：仅有用户授权仍不足以科学地筛选；选择动作必须由当前 artifact 的实际质量证据先行。
- 边界：经验阈值未校准，输出仍是派生 artifact，不把筛选解释为临床质量真值。

## D6：有限恢复必须重新验证 obligation

- 决策：为通用 `ConstrainedPlanRunner` 增加可选 `plan_validator` hook；CCEP 在初始计划和每次重规划后检查 ledger。默认旧 Planner 不传 hook，行为不变。
- 原因：只在第一次 preflight 检查约束，无法保证恢复计划没有改写显式 label/window/禁止操作。

## D7：真实模型暴露的 schema 漂移用接口约束修复

- 决策：`submit_eeg_intent.parameters` 不再是任意 object，只允许 `channels/start/end/labels/tmin/tmax/selection_authorized`；Prompt 同时明确连续窗 PSD 与事件分析的边界。
- 证据：首轮真实 DeepSeek 把三类请求全部安全停在澄清，其中普通 PSD 被分类为事件分析，且使用了 `channel/event_label/window_*` 等非 canonical key；收紧后 PSD 和事件链完成，真正缺 label 的请求仍然澄清。
- 原因：这是协议契约缺失，不是通过修改 gold 或容错别名掩盖模型错误。严格 schema 让 Planner、gate 与模型共享同一科学 slot 词汇。
- 限制：一次三案例验证只证明链路可运行，不证明泛化或方法优势。

## D8：来源与证据检查采取 fail-closed

- 决策：只有 `EEGRecord.metadata.source_stage == raw` 才允许履行 raw-source obligation；默认 `current` 不再被等同为 raw。数值 obligation 必须能从对应原文 span 提取到相同数值。
- 原因：当前 `EEGRecord` 通常只保存适配/预处理后的单一分支。仅依据没有标注的 `current` 或有限数值就声称原始来源/精确窗口，都会产生科学证据假阳性。
- 限制：本轮没有新增 raw/processed 双分支数据系统；这是安全拒绝，不是自动数据恢复。

## D9：闭合证据要求参数不能消失

- 决策：除纯授权标志外，每个参数 obligation 必须至少出现在计划步骤和实际执行事件一次；不存在与被改写同样视为违约。最终回答调用失败时返回 `completed_without_llm_answer`，保留工具结果但不宣称闭环完整。
- 原因：原实现只检查“若出现则必须相等”，计划静默丢参数时可能错误闭合；工具成功和自然语言回答成功也必须分开记录。

## D10：历史分叉使用普通 merge 收敛

- 决策：网络恢复后 fetch PR 分支，以 `ort` 普通 merge 合并本地归档提交与 GitHub Contents API 产生的等价文档提交，再普通 push。
- 结果：合并无内容差异，commit `1bd8e7c` 已推送；没有改写远端历史或合并 main。

## D11：任务类型由原文科学概念独立解析

- 决策：IntentSpec 新增 `semantic_evidence`。模型必须把请求中的科学操作映射到原文精确 span；运行时依据覆盖全部现有分析类型的声明式概念组合独立解析 capability，再与模型声明的 `analysis_type` 交叉检查。
- 原因：原 ledger 从模型声明的类型开始编译，若 PSD 被错误声明为 amplitude 且通道/窗口参数合法，后续所有约束都可能“正确执行错误目标”。新检查不使用离线 gold，也不是 PSD/amplitude 单一特例。
- 边界：概念词表和唯一组合仍属于可审计的语义契约/validator，不单独构成论文创新；其价值只可能来自与跨步骤 obligation、状态变化和证据闭合结合后的整体机制。

## D12：质量筛选必须产生并消费派生状态

- 决策：组合任务在原有质量证据和授权筛选后继续调用 `event_bandpower`，且只允许消费 `select_quality_epochs` 返回的派生 artifact id。
- 原因：只运行到筛选结束不足以验证状态变化对后续分析的实际影响；五工具链在同一 Context 和现有 Executor 中形成可检查的数据依赖。
- 边界：质量阈值仍为未校准经验规则，链路只证明状态/lineage 执行正确，不证明筛选具有生物医学有效性。
