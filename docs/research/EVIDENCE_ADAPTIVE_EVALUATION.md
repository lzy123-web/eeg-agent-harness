# EEG 证据驱动自适应分析先导评估

## 结论

质量证据工具在受控合成注入上能够正确检出本试验定义的 flatline、异常幅值和 50 Hz 干扰，并能正确将预处理后不可观测的工频指标标为 unknown/not observable。但这些结果只证明数值实现与受控真值一致；阈值没有经过设备、数据集或临床校准。

在完全相同的证据、合法候选操作和工具预算下，强 Expert Quality-Gated DAG 与 Candidate Evidence-Driven Policy 在 16 个冻结案例中均为：证据目标成功率 100%、证据不足正确拒绝率 100%、总体正确率 100%、32 次工具调用。Candidate 没有额外结果或成本优势。

因此，研究点二作为独立方法贡献的结论为 **No-Go**。当前 Candidate 实质上是同一质量门控规则的另一种表达。质量工具和显式证据契约具有工程价值，可以保留在 Harness，但不能据此宣称自适应策略创新成立。

## 质量证据有效性

### 指标和独立真值

`record_quality` 测量 flatline fraction、high-amplitude fraction、line-noise ratio 和记录覆盖事实；`epoch_quality` 测量边界拒绝、条件计数、经验质量标记及其对可用 Epoch 数的影响。没有质量总分。

合成真值独立于策略输出生成，包括干净正弦、精确 flatline、500 µV 尖峰、50 Hz 注入、边界事件和受污染 Epoch。冻结评测中三种策略看到完全相同的质量结果：通道注入 TP=7、FP=0、FN=0、TN=9；4 个实际生成 Epoch 证据的案例均精确匹配预期标记数。该准确率不能外推至真实伪迹或临床质量。

### 预处理来源限制

所有 evidence 标注 `source_stage`。若同频 notch 已执行则 line noise 为 `not_applicable`；若目标频率位于已声明通带之外则为 `not_observable`。R3 Profile 为 1–40 Hz 并含 50 Hz notch，因此没有报告伪造的“原始 50 Hz 噪声值”。

### 真实文件阈值敏感性

2026-10-22 对两个合法本地 R3 EDF 各取处理后前 10 秒，只在本地计算聚合计数：两者均为 21 通道、300 Hz，flatline 标记均为 0；默认 200 µV 阈值下 high-amplitude 标记分别为 3 和 0 个通道。阈值改为 100/500 µV 时，第一记录为 6/0，第二记录为 5/0。50 Hz 指标均为 `not_observable`。

该明显阈值敏感性表明默认规则不能被描述为已校准的真实坏道判定。文档不公开文件名、目录、通道级特征或可逆身份信息，也不根据目录推断组别。

## 自适应机制

`EvidenceGoal` 明确目标、`EvidenceRequirement` 明确最小覆盖和预算。策略只能：

- 对固定窗口/通道先测量质量；
- 在用户显式提供的候选通道或窗口中，按质量标记和声明顺序选择；
- 对同一事件目标生成 Epoch、测量覆盖，在满足每条件最低数量时创建仅剔除已标记 Epoch 的派生 artifact；
- 无合法替代、证据 unknown 但目标要求已知、覆盖不足或预算耗尽时返回 `INSUFFICIENT_EVIDENCE`/明确原因。

策略不改变标签、参考、Profile 或未授权时间窗，不按 PSD/模型输出挑选数据，不混合条件，也不把执行错误重试作为贡献。Trace 保存 evidence ID、候选标记数、选择、工具调用、耗时和停止原因。

## 公平对照协议

- 冻结配置：`config/evidence_benchmark_v1.json`
- SHA-256：`3467a86bad3036bca6cecacd97da4445c7a008e09445635dd2ef1c4dc49162c4`
- 冻结 Commit：`79c869f`
- 评估实现 Commit：`4131914`
- 逐例输出：`docs/research/results/evidence_benchmark_v1.json`

清单在 Pilot 策略代码完成后、首次 benchmark 结果运行前提交。因此它是“执行前冻结”，不是方法实现前预注册；本文不作盲测或严格 holdout 优势声明。

| 策略 | 证据目标成功率 | 正确证据不足拒绝 | 总体正确率 | 工具调用 |
|---|---:|---:|---:|---:|
| 固定流程 + 同质量检测 | 30% | 100% | 56.25% | 25 |
| 强 Expert Quality-Gated DAG | 100% | 100% | 100% | 32 |
| Candidate Evidence-Driven Policy | 100% | 100% | 100% | 32 |

固定流程失败说明质量门控/合法替代有用，但不证明 Candidate 优于强规则。强 Expert 与 Candidate 完全持平，且使用相同调用数；Candidate 的“自适应”在当前动作空间内可以被 Expert 条件 DAG 等价表达。

## 回归与资源验证

- `compileall` 与 `pip check` 通过。
- 无私有资源：108 项中 97 通过、11 项按设计跳过。
- 使用现有 EEGAgent EDF/权重和一个匿名 R3 样例：108 项全部通过。
- 另一个匿名 R3 记录完成本地质量摘要与阈值敏感性检查。
- Issue #4 的 planning v2、原癫痫推理、R3 事件链、Executor 和 Fake Agent 测试未退化。
- 三个真实 LLM 环境变量均未配置；未执行外部 LLM，Fake 不作为真实模型证据。

## Go/No-Go 与后续建议

- 质量证据工具：**Conditional Go**。合成数值正确，真实阈值未校准，适合作为显式测量/筛查层，不适合作为科学可靠性总分。
- Candidate 相对固定流程：有优势，但固定流程不是决定性强基线。
- Candidate 相对强 Expert：**No-Go**。结果和调用完全持平，未显示独立方法价值。
- 研究点一与研究点二目前均未成立为独立创新点。

若需替代研究问题，建议转向可由 EEG 方法本身验证的方向：**跨 Profile/预处理阶段的质量证据校准与不确定性传播**。可用滤波前后配对摘要、受控伪迹注入、人工双盲质控标注和跨设备数据，评估指标的校准误差、检出率、阈值迁移和下游特征稳定性；这比把同一启发式规则换成 Agent 策略更可能形成可证伪的方法贡献。
