# 多轮 EEG 任务上下文管理：方法边界与最小设计

## 原始研究与本项目推断

- [HiAgent（ACL 2025）](https://aclanthology.org/2025.acl-long.1575/) 将子目标作为工作记忆块，保留当前子目标详细行动—观察，完成的子目标摘要化且可追索轨迹。它研究**单次长任务内** working memory；跨用户轮次、EEG 对象和分析版本是我们的适配，不声称复现其完整方法或论文成绩。官方[代码](https://github.com/HiAgent2024/HiAgent)仅用于核对公开设计；本项目不拷贝其实现。
- [LongMemEval](https://arxiv.org/html/2410.10813) 是聊天长期记忆 benchmark，提出索引→检索→读取的统一视角，评价信息抽取、跨会话、时间推理、知识更新和拒答。本项目只借鉴问题拆分与评价维度，不把其 500 问题直接当 EEG benchmark。
- [EEGAgent](https://arxiv.org/html/2511.09947v2) 已论述工具规划中的上下文、知识检索、记忆和用户互动；[BrainAgent 预印本](https://arxiv.org/html/2606.25400v1) 描述有全局对话历史的 supervisor 与子代理隔离。不能说“EEG Agent 首次引入记忆”，也不从论文未测多版本 EEG 追问推断已有系统必失败。

**可证伪假设**：在相同可见对话与真实工具证据、正常长度和预算下，按分析任务保存不可变历史，把记录/科学作用域/参数版本与结果绑定并检索，可能减少多轮 EEG 中错用记录、窗口、事件条件和旧结果的错误，或以接近的准确性减少上下文成本。若强通用结构化记忆 G 已同样准确且成本相近，则复杂领域适配不值得继续。

## 共同接口与候选差异

所有臂共用 `MultiTurnEEGSession`：用户消息；记录别名对应隔离的 `ExecutionContext`；真实 `ToolResult` 与不可变 task entry；通用 `read_task(task_id)` 只读证据；新分析统一走原 `run_instances`→Registry/Executor，修订创建新 entry 并保留旧 entry。切换记录只改变可见当前别名，不能跨记录拿 artifact。当前请求的任务解析及回答格式对 F/S/G/E 相同；不能让候选独享 TaskSpec 或 gold ID。

F：完整历史与所有 task card；S：最近 3 个 task card + 早期条目的通用滚动摘要（保留标识、记录、类型、窗/事件、数值结果入口，不故意删除关键事实）；G：HiAgent/LongMemEval-inspired 的任务块与通用字段/词面检索，允许 record/time/field 和历史只读读取；E：在 G 的信息上增加 EEG 科学对象（连续窗/事件 Epoch）、来源/配置与不可变修订关系的索引与排序。G/E 都能读取相同完整条目，区别只是挑选工作上下文；F 不压缩且成本单独报告。消融 E−scope 去掉 EEG 作用域排序，其余相同。G 若已能解决，则如实持平。

历史写入仅取当前用户文本、实际已解析目标、真实执行 bundle/ToolResult；未来请求与离线 gold 不进记忆。检索条件只取当前可见请求、活跃记录与历史字段；遇到多解不猜。项目仅实现轻量本地索引与按需读取，不新建向量数据库、不改 EEG 数值工具、Executor、Planner 或旧 v3 方法。HiAgent-inspired 指任务块/已完成摘要与外部详细证据，LongMemEval-inspired 指分离索引、检索与读取；科学对象/版本关联是 EEG 适配，不是新通用记忆算法。

## 实际实现审计（实验后追加，不改变冻结假设）

`src/eeg_harness/research/task_memory.py` 的 `TaskEntry` 按实际完成的分析任务写入 `task_id`、记录别名、能力、参数、用户话语、`revision_of`、真实结果和 v3 evidence/tool trace。修订只追加新任务；历史读取在公共 `MultiTurnEEGSession.read_task` 中读取对应不可变条目。记录 A/B 是可区分的合成数据，各分析新建原有 `ExecutionContext` 并调用 `run_instances`，事件产物只在该次执行链内使用，不能由别的记录复用。当前轻量实现不是持久化数据库，也不支持跨进程恢复。

F/S/G/E 共用该写入和读取路径；`select_context` 只改变当前提供给模型的工作任务卡。G 用普通词面、记录、通道字段排序，E 在同一索引上增加连续/事件能力、事件标签和修订前后关系排序。E−scope 去掉后一组排序。E 的实现**没有**新 EEG 数值算法或独占正确任务 ID；科学来源、方法配置等保存在真实 evidence 中，但尚未全部进入检索特征。有限中英文字面提示仍是脆弱近似，不能宣称开放语言泛化。

`live_turn` 统一使用一次结构化 `submit_memory_action`，执行后可选第二次模型调用生成有证据边界的自然语言答复。共同能力目录从现有 `capability_catalog` 生成，所有臂共享，修复只改公共接口而非 E 策略。该两阶段交付是在真实工具结果上作答；模型只见合成记录元数据、必要任务卡/结果，不见 EEG 数组。完整原始响应保留在 Git 忽略的本地实验目录。

这是一项**HiAgent/LongMemEval 启发的最小领域适配**，不是对其完整实现或论文成绩的复现。当前 6 会话的任务历史过短，G/E 同为全部命中，S 摘要未真正触发；因此工程机制可运行，但 EEG 作用域排序的独立研究收益尚无充分证据。参见 `EEG_TASK_MEMORY_RESULTS.md` 和 `EEG_TASK_MEMORY_DECISION.md`。
