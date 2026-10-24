# 冻结 CIEDG 的 R3 应用接入设计

## 方案选择

比较三个接入位置：

1. 修改通用 CIEDG/Planner 以认识 R3：侵入冻结方法且引入数据集语义，排除。
2. 将既有确定性 `run_r3_event_workflow` 的结果包装成 CIEDG：没有真实 graph/evidence 执行，排除。
3. 在 `applications/r3` 建离线结构化任务 adapter：复用 `load_r3_edf`、`R3_PROFILE`、`R3DatasetRules`，用现有 `IntentSpec → compile_intent → StateAwareConstrainedPlanner` 预检，交给原 `ContractGraphResidualPlanner.run`、同一 `ExecutionContext/ToolRegistry/Executor` 执行。选用此方案。

第三方案不经过外部 LLM，自然语言能力不属于本期真实数据验收。adapter 只编译配置中的已知目标，禁止 selection/rereference；若要求冻结 event workflow 无法表达的操作，返回结构化 `unsupported`，不切换另一条手写分析路径。

## 两项任务与共享配置

| 任务 | CIEDG objectives | 输入与结果 |
|---|---|---|
| 事件试次与有效窗口汇总 | `epoch_summary` | 既有数字标签、`[-0.2, 0.8)`、baseline `[-0.2, 0)`；`list_events → create_epochs → epoch_summary` |
| 质量与绝对频带特征 | `epoch_quality`, `event_bandpower` | 同一标签/窗口/预处理；`list_events → create_epochs → epoch_quality → event_bandpower`；只测量，不筛选 |

两个任务分别拥有 `ExecutionContext` 和 artifact store，使用一次 EDF 适配产生的显式 `EEGRecord`。完整 ToolResult/trace 在本地被 Git 忽略；公开报告只有聚合通过/失败结论，不含单记录特征、事件时刻或可关联哈希。

原确定性 R3 workflow 仍作为对照：用相同 EDF、`R3_PROFILE`、`R3DatasetRules` 和 `baseline.json` 运行。它的 `record_quality` 是额外测量，不纳入当前冻结 CIEDG event objectives；交叉核验匹配的 `epoch_quality`、Epoch 摘要和 `event_bandpower`。

## 固定真实子集与核验

在查看结果前固定：从已授权资源根目录中，取按目录名排序的前两个**存储分区**，每个分区递归发现 EDF 后按相对路径排序取前两份，共四份。分区仅用于覆盖资源位置，不代表临床组。资源不足时按实际数量报告，不替换为表现较好的文件。

对每份记录核验：EDF annotation 代码数；显式标签的接受/越界拒绝数；Epoch 数组形状、有限性和标签保留；CIEDG 与确定性 workflow 的数值；从已预处理 EEGRecord 手动按事件切窗、应用同一 baseline 并独立循环 Welch/积分的频带 oracle；artifact ID/fingerprint、goal evidence 和 release 与当前状态的一致性。独立 oracle 不调用被测 `create_epoch_set` 或 `event_bandpower` handler。

数值阈值在运行前定为 `rtol=1e-5, atol=1e-12`（绝对频带功率，单位为信号单位平方）；事件/试次数与 shape 要完全一致。若原确定性流程和 CIEDG 因共同工具而同错，手动切窗与事件核验应暴露；质量规则只核对同一工具结果，本期不独立证明其科学有效性。

## 维护与边界

只新增 R3 应用 adapter、CLI、配置模板和测试；不修改冻结 CIEDG、原 R3 deterministic workflow、正式实验文件或通用 EEG 层。对真实输入发现的方法 bug 单独留痕，不以应用修补重新计为冻结方法的 unseen 结果。应用跑通不构成第二创新点。

