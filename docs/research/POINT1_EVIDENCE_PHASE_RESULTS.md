# CCEP Evidence Phase 实验结果

日期：2026-10-23。实验协议：`point1-evidence-phase-v1`，冻结语料 SHA-256：`e85b5cdad47caf3a083fc87b9116c797e7cab91ce41c1efaddd692884302e696`。

## 1. 实验边界

本轮只研究工作点一 CCEP。所有 EEG 均为确定性合成数据；没有向 DeepSeek 发送实验室 EEG、受试者信息或本地资源路径。离线 oracle/gold 仅在 Agent 返回后计分，运行时不可见。本轮没有围绕 holdout 结果修改 Prompt、schema 或评分标准。

## 2. 实际 Epoch 状态变化

独立造数程序生成 3 个 `target` Epoch，并在索引 1 注入高幅 18/20 Hz 成分。真实 `ToolRegistry → Executor` 链执行：

`create_epochs → epoch_quality → select_quality_epochs → event_bandpower`

结果如下：

- 质量工具标记索引 `[1]`，与造数真值一致；
- 试次数从 3 降为 2，派生 artifact 与原 artifact 的 ID 不同；
- 原 artifact 数据逐样本保持不变；派生 artifact 数据逐样本等于独立 oracle 直接从 EEGRecord 提取的索引 0、2；
- 筛选前 3 试次和筛选后 2 试次的每通道、每频带 Welch 积分均与独立 SciPy oracle 一致；
- 频带结果确实发生变化。例如 `SYNTH-C1` alpha 在筛选后为 `1.9999999920083944e-10`，而异常试次导致的 beta 能量不再出现在筛选后均值中；
- 全部 3 个 Epoch 均被标记时，筛选工具返回 `TOOL_EXECUTION_FAILED`，不创建空派生 artifact，后续频带工具不执行。

这证明当前合成条件下的筛选、artifact lineage、计数和数值实现正确；不证明经验阈值具有临床有效性或真实数据泛化性。

## 3. 多目标合法组合

事件任务不再枚举固定复合类型，而使用 `event_workflow` 和三个原子目标：`epoch_quality`、`trial_selection`、`event_bandpower`。

- “测量质量、禁止筛选、随后算功率”：同一原始 Epoch artifact 依次进入质量与功率工具，计划中不存在选择工具；3 个试次全部进入功率计算。
- “测量质量、授权筛选、随后算筛选后功率”：质量证据先产生，选择工具生成 2 试次派生 artifact，功率工具只消费该派生 artifact。
- 质量测量失败时：选择与功率停止，ledger 中 label、窗口和授权不被恢复过程弱化。

该设计减少了固定流程特例，但仍只覆盖三个已注册事件目标，不是开放域规划器。

## 4. 冻结共享任务规划比较

24 个冻结案例中有 18 个可在共享解析任务层评价，6 个缺参案例归属于端到端意图层。强基线与 CCEP 使用相同 EEG、TaskSpec、Planner、Executor、工具权限、恢复次数和预算；唯一差异是 CCEP 增加持续 ledger 校验与 Evidence closure。

| 方法 | 可评价 | 正确处置 | 应完成且科学完成 | 工具调用 | 重规划 |
|---|---:|---:|---:|---:|---:|
| Strong route+preflight | 18 | 18 | 10/10 | 55 | 2 |
| CCEP | 18 | 18 | 10/10 | 55 | 2 |

两者完全持平。CCEP 没有在该冻结任务集上产生额外规划收益或额外成本。完整结果见 `results/point1_evidence_phase_shared_planning.json`。

## 5. 真实 DeepSeek holdout

预先固定两个英文 holdout，每个案例分别从原始自然语言启动 Native Structured Tool Calling 与 CCEP。总计 13 次 Provider 请求、34,263 tokens，低于 36 请求/80,000 tokens 上限。

| 案例 | Native | CCEP | 主要差异 |
|---|---|---|---|
| 质量 + 禁止筛选 + 功率 | 通过 | 通过 | 两者均使用原 3 试次；CCEP Evidence Gate 有效 |
| 质量 + 明确筛选 + 筛选后功率 | 通过 | 未通过 | CCEP 意图层误报缺少 `analysis_type`，安全澄清且 0 工具调用 |

Native 第二例额外调用了 `record_quality`，因此工具最小性弱于专家/CCEP 路线，但最终执行了正确的 3→2 派生链。人工对照结构化 ToolResult 审核两条 Native 最终回答：试次数、异常索引、频带值、绝对功率非 ERD/ERS 和经验阈值边界均与工具结果一致；该审核不是自动化语义正确率指标。CCEP 第一例的证据寻址回答由运行时校验通过；第二例没有执行和发布数值。

完整脱敏结果见 `results/point1_evidence_phase_deepseek_holdout.json`。结果文件不含 API key、认证头、私人路径或真实 EEG。

## 6. 失败与有效性威胁

- 两个真实 holdout 只用于有界集成探针，样本过小，不能给出统计显著性或模型总体可靠性结论。
- CCEP 的主要真实失败发生在意图解析，而非 ledger、Planner 或 Executor；这说明端到端性能受前置 LLM schema 服从度限制。
- 共享任务实验隔离了解析变量，但也使强专家与 CCEP 的路线相同；它适合检验 ledger 的增量价值，不等同于完整自然语言 Agent 比较。
- 独立 oracle 只验证合成、确定性异常；质量阈值仍未做真实 EEG 或专家标注校准。
- Native 最终答案只做两例人工审计；尚无通用自然语言数值蕴含 scorer。

## 7. 客观结论

本轮确认 CCEP 是一条真实集成、科学状态可追踪且 fail-closed 的执行链，但没有确认其核心 ledger 机制相对同规则强专家产生额外价值。共享任务层完全持平，真实小样本中 CCEP 反而因意图解析失败少完成一例。因此当前证据不支持“CCEP 优于强基线或原生 Agent”的论文主张。
