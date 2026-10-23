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

## D13：回答不再直接信任自由文本

- 决策：最终 LLM 只提交 `request_id + JSON path` 的结构化证据引用。Gate 从真实成功 ToolResult 解析标量，检查组合任务的必要工具覆盖，再用固定中文边界模板渲染。
- 原因：仅验证工具执行成功无法阻止最终回答改写数值、遗漏筛选条件或引用不存在结果。由运行时读取源值可消除“模型填写一个伪造 value 但引用合法 path”的空间。
- 边界：确定性渲染牺牲了流畅的总结与跨值比较；当前保证的是所发布值和条件可追溯，不代表已解决所有自然语言推理忠实度。

## D14：证据路径以 ToolResult.data 为唯一根

- 决策：回答工具提交的 JSON path 必须相对成功 `ToolResult.data`；schema 与 Prompt 同时明确不得添加 `data` 或 `ToolResult` 前缀，运行时仍 fail-closed，不对错误路径静默容错。
- 证据：真实复杂链首次执行成功，但模型引用 `data...` 导致 `ANSWER_EVIDENCE_MISMATCH`；修复接口说明后，同一请求完成并引用质量、筛选和事件频带功率三类实际结果。
- 原因：这是 API 坐标系不明确造成的协议错误。自动剥离前缀会掩盖调用方是否遵守契约，因此只修正文档化接口并保留严格校验。
- 边界：schema、Prompt 和 Validator 本身属于常规工程机制；CCEP 的论文候选价值只能来自同一 obligation 在意图、派生状态 lineage、有限恢复和回答发布之间的可检验传播，且尚未由公平强基线实验确认。

## D15：实际筛选效果必须由独立造数真值与特征 oracle 验证

- 决策：Evidence Phase 不把 `epoch_quality` 的输出或 CCEP 的 Evidence Gate 当科学真值。独立造数程序固定异常 trial 索引，独立 oracle 直接从记录样本重建应保留 Epoch，并单独计算 Welch 频带积分。
- 结果：真实 Registry→Executor 链把 3 个 Epoch 筛为 2 个；异常索引、派生波形、原 artifact 不变性、前后试次数及全部频带数值均通过 oracle。全部试次异常时安全失败且无派生 artifact。
- 边界：这证明当前经验规则和 artifact lineage 在受控合成条件下实现正确，不证明阈值具有临床有效性或真实数据泛化性。

## D16：事件多目标以原子目标集合组合，不增加第十个复合类型

- 决策：CCEP 意图使用一个 `event_workflow` family，正向目标限定为 `epoch_quality`、`trial_selection`、`event_bandpower`；否定操作只进入 forbidden obligations。Planner 只创建一个共享 Epoch artifact，并根据目标集合与选择授权组合 DAG。
- 原因：固定 concept-set→复合 TaskType 会把“测质量、禁止筛选、仍计算功率”误拒；原子目标能表达筛选/不筛选两条合法 lineage，同时保持现有 Planner、Executor 和 EEG Tools。
- 保留硬编码：当前只支持三个已注册事件原子目标；`trial_selection` 仍硬性要求先测质量和显式授权，`event_bandpower` 仍要求至少 1 秒。这是有限 capability composition，不是开放式通用规划。
- 验证：禁止筛选组合使用原 Epoch 计算功率；授权筛选组合使用派生 Epoch；质量测量失败时后续选择/分析不执行。定向 CCEP、Planner 与 oracle 测试 35/35 通过。

## D17：独立协议先冻结，计分错误修复不修改 gold

- 决策：固定 24 案例、12/12 split、合成 fixture、oracle、同权限方法和 36 请求/80k tokens 预算后才运行比较；规范化语料 SHA-256 为 `e85b5cda…e696`。
- 过程：首次 scorer 把“全部 Epoch 被拒且工具明确失败”错误地沿用为输入计数 3。修复为依据该类型化空选择错误计 0；case、gold、方法和输出均未改变，新增回归测试锁定此边界。
- 原因：评测基础设施缺陷不能被包装为方法失败，也不能借修复改变判定目标。

## D18：真实 holdout 不做结果后 Prompt 调参

- 决策：固定两个相反授权的英文 holdout，Native 与 CCEP 各执行一次。CCEP 在授权筛选例因 `analysis_type` 缺失而安全澄清；保留失败，不重跑、不修改 Prompt。
- 结果：Native 2/2、CCEP 1/2；13 次 Provider 请求、34,263 tokens。禁止筛选例的 CCEP Evidence Gate 通过，授权筛选例 0 工具执行。
- 原因：事后修 Prompt 会污染 holdout，也会把接口服从问题伪装成方法优势。

## D19：核心机制增量价值当前判定 No-Go

- 决策：CCEP v0 的“优于同规则强基线”主张为 No-Go；代码作为 opt-in 科学安全骨架 Conditional Keep。
- 证据：共享任务层 Strong 与 CCEP 都是 18/18 正确、10/10 科学完成、55 次工具调用、2 次重规划；真实两例中 CCEP 未超过 Native。
- 含义：持续 ledger 确有跨阶段可审计实现，但本轮没有观测到只有它才能解决的实际错误。后续若继续，必须预先提出一次性 preflight 会失效的动态状态/恢复假设并重新冻结实验。

## D20：v1 采用 lineage-aware residual goals，而不是 LLM 每步重规划

- 决策：LLM 只在开始编译 Intent、结束选择证据；运行中由确定性科学状态逐步选择唯一 frontier。
- 原因：质量、每条件可用 Epoch、选择授权与 artifact lineage 都能由工具结果确定，交给 LLM 会增加目标漂移、费用与不可复现性。
- 边界：guarded conditional DAG 能表达当前相同分支，LRSP 的相对价值必须由未来冻结强对照决定。

## D21：clean selection 是 identity transition

- 决策：用户授权筛选但实际 flagged=0 时，以质量 evidence 满足 selection goal，复用原 Epoch，不调用选择工具制造内容相同的派生 artifact。
- 原因：授权是一种许可，不等于实际必须删除数据；伪派生会混淆 lineage 和回答语义。
- 边界：identity 只在当前经验规则给出零标记时成立，不证明数据没有其他质量问题。

## D22：artifact lineage 必须绑定内容而不只绑定 ID

- 决策：Epoch 科学元数据和数组内容形成 SHA-256 fingerprint；质量 evidence 同时绑定 artifact ID/fingerprint/阈值，下游工具可声明预期绑定。
- 证据：迭代初版在同 ID 内容变化探针中仍选择旧分支；修订后撤销旧质量并重新测量，过期 evidence ID 会被 Executor 拒绝。
- 边界：当前 artifact store 仍为单 Context 内存对象；fingerprint 不是分布式锁，检查后并发修改仍会安全失败但不会自动无限恢复。

## D23：回答中的动态分支由运行时确定性披露

- 决策：LLM 只提交成功 ToolResult 的 JSON path；校验通过后，运行时追加 derived/identity/no-selection 分支及经验阈值边界。
- 原因：工具数值引用正确仍不足以保证回答没有把“授权筛选”写成“实际发生筛除”。动态分支属于 Planner 已验证事实，不需要 LLM 改写。
- 边界：这提高忠实度但牺牲部分自然语言灵活性；它不是科学解释或临床结论生成器。
