# EEG 科学目标完备性：真实失败模型

日期：2026-10-24（Asia/Shanghai）

## 1. 研究对象

本报告区分五层正确性，避免把不同问题混为一个“Agent 是否成功”：

1. **结构合法性**：JSON、枚举、字段与 schema 可解析。
2. **Soundness**：候选 Intent 中每个目标、参数、授权是否有用户原文支持。
3. **Completeness**：用户原文明示的科学目标、禁止、授权和数据阶段是否全部被候选覆盖。
4. **Executability**：候选目标能否由当前 Profile、Planner、CIEDG 与工具合法执行。
5. **Faithfulness**：最终回答是否只陈述已执行且证据支持的事实。

Issue #20 只研究第 3 层。一个只含 `epoch_quality` 的 Intent 可以 schema-valid、sound、executable，最终回答也可
faithful，但仍然遗漏用户要求的重参考和功率。这就是目标完备性不同于普通 JSON 错误的根本原因。

## 2. 形式化边界

令：

- `U`：用户请求；
- `S(U)`：独立从原文识别出的 source obligations；
- `P(U)`：候选 Intent/TGSRG 提交的目标与关系；
- `M(s,p)`：source obligation 与候选 claim 的可验证匹配；
- `H ⊆ S(U)`：遗漏后可能导致危险执行或错误科学语义的高影响义务。

候选 soundness 近似要求：

```text
∀p ∈ P(U), SupportedByExactEvidence(p, U)
```

目标覆盖要求：

```text
∀s ∈ H, ∃p ∈ P(U): M(s, p)
```

现有 v1/v2 只从 `P(U)` 出发，最多证明第一式；如果 `epoch_rereference` 根本不在 `P(U)`，检查器没有独立的
`s` 可用，第二式是循环论证。

只有当输入受控在一个完备语法 `G` 中、`S_G` 的 parser 对 `G` 已证明 sound/complete、目标 ontology 闭合时，
才可能给出相对于 `G` 的形式完备性。面对中英自由自然语言，只能测量 omission recall、危险误接受风险和选择性
澄清代价，不能声称“证明理解完整”。

## 3. SH01 字段级信息丢失链

原文：

> Obtain quality evidence from untouched target epochs at 0–1 s. Afterwards I approve SYNTH-C2 re-referencing, and spectral power must use that new reference.

理想 source obligations 至少包含：

| ID | 类型 | 内容 | 作用域/阶段 |
|---|---|---|---|
| S1 | observation | epoch quality | source / untouched epochs |
| S2 | authorized transformation | rereference to SYNTH-C2 | after S1, source→effective |
| S3 | analysis output | spectral power | effective / new reference |
| S4 | relation | S1 before S2 before S3 | two-stage request |
| S5 | prohibition | no trial selection implied by untouched | does not cancel S2/S3 |

### 3.1 Flash：信息保留，v2 能检查

已观察事实：Flash raw Intent 含 `epoch_quality + epoch_rereference + event_bandpower`；TGSRG 把质量绑定 source、
功率绑定 effective，静态能力证书发现冻结 CIEDG 只有一个 effective branch，返回
`clarify(analysis_stage)`。这证明 v2 对“已抽取完整”的输入有效。

### 3.2 Pro：目标先被截断，所有后续检查失去观察量

已观察事实：Pro raw Intent 仅含：

```text
objectives = [epoch_quality]
semantic_evidence = {quality_measurement, event_locked}
parameters = {labels=target, tmin=0, tmax=1}
```

其 rationale 把已明确批准的重参考和必须使用新参考的功率错误解释为“future/conditional”。之后发生：

```text
原文 U
  → Intent extractor 丢失 S2/S3/S4
  → v1 只按已提交 semantic_evidence 重建 {epoch_quality}
  → v2 看到 objectives 中无 transition，直接返回 v1
  → Obligation Ledger 只登记 quality
  → Planner/Executor 合法完成 quality
  → Evidence Gate 最多保证 quality 回答忠实
```

因此主因分两层：

- **基座错误**：将明确的后续授权和目标误判为非当前意图；
- **Harness 错误**：把“候选没有 transition”当成“原文没有 transition”，允许 scope gate 被遗漏本身绕过。

这不是 CIEDG 执行错误，也不是 Answer Gate 错误；两者只能忠实执行/报告不完整的 Ledger。

## 4. 非机械重复的目标遗漏类别

### F1：整个正向科学操作遗漏

示例：`检查质量，然后重参考，并计算新参考下功率` 被解析成只有质量。候选内部一致且可执行，但最终只回答第一目标。
SH01/Pro 是真实观察；其它表达的发生率尚未验证。

### F2：目标保留但数据阶段/先后关系遗漏

示例：H14 中质量、重参考、功率都出现，却把“重参考前质量”和“重参考后功率”合并到同一 effective Epoch。
这是 Issue #17 的真实观察。TGSRG 可在目标完整时检测，但不解决 F1。

### F3：授权或禁止的作用域遗漏/错绑

示例：`测量质量但禁止筛除，随后计算功率`。若只保留质量与功率而遗漏“禁止筛除”，Planner 可能将质量异常自动解释为
筛选许可；反之，将“批准以 SYNTH-C2 重参考”解释为尚未授权会造成误拒。仓库已有授权 gate 和禁止筛选测试，但
“source-side 禁止语句被整个遗漏”的真实频率尚未测量。

### F4：输出消费者遗漏

示例：用户要求 `筛除异常试次、报告保留数量并计算功率`，模型只保留筛选。转换本身执行正确，却没有 summary/power
消费者，导致任务被过早视为完成。该类别与缺少科学先决条件不同：summary/power 是用户目标，不能由 Planner 自行删除。

### F5：不支持目标被静默删除，剩余子任务被执行

示例：`计算 ERD/ERS 并解释认知激活，同时给出绝对功率` 被收缩为系统支持的绝对功率。若 unsupported claim 不进入
Intent，schema、执行与回答都可能“成功”，但系统没有向用户说明只完成子集。仓库旧 ERD/ERS 案例表明模型会混淆
注册能力；静默删除组合目标是待独立验证的风险，不能写成已观察发生率。

### F6：用户目标与系统派生先决条件混淆

`trial_selection` 科学上依赖 quality measurement；v1 可以派生 quality。但反向不成立：系统能派生的先决条件不能证明
所有用户目标已被识别。若把 `derived prerequisite closure` 当作 completeness，SH01 的 power 仍无法恢复。

## 5. EEG-specific 风险为何更高

- **操作改变数据实体**：重参考、试次筛除会生成不同 Epoch lineage；遗漏一个转换会改变所有下游数值的含义。
- **同名指标依赖阶段**：quality/power 在 source、selected、rereferenced 数据上不是可互换证据。
- **授权不是普通参数**：筛除与重参考会改变研究数据，必须区分“测量”“建议”“授权执行”“明确禁止”。
- **事件范式约束**：event label、epoch window、baseline/condition 决定分析单位；遗漏关系可能把事件分析降为连续 PSD。
- **分析分叉影响结果**：EEG preprocessing 选择可改变频谱、ERP/ERSP 和解码结论，因此“完成一个合法子任务”不能代替
  “覆盖全部科学请求”。

这些约束提供 EEG 任务 ontology 和风险分层，但不会自动解决自由语言解析。

## 6. 已观察事实与待验证假设

| 命题 | 状态 |
|---|---|
| SH01/Pro 漏掉 rereference 与 power | 已观察、原始 JSON 可复查 |
| v2 因无 transition 快路跳过 scope | 已观察、源码可复查 |
| Ledger/CIEDG 无法恢复未登记目标 | 由代码结构直接推出 |
| Flash 在同一 SH01 保留三目标并安全澄清 | 已观察 |
| 独立 source extractor 一定能修复 | 未验证假设 |
| 第二 LLM 与第一模型错误独立 | 未证实，不能作为保证 |
| EEG ontology 可覆盖所有自由表述 | 不成立；只能对冻结任务域评估 |
| 目标遗漏检测可成为独立论文贡献 | 本轮仅作条件性判断，尚无实验支持 |

## 7. 结论

当前缺口不是“再检查一次 Intent”，而是缺少从原文侧产生、在候选之外存在的 source obligations。没有这一独立观察量，
任何目标双射、TGSRG 或 Obligation Ledger 都只是在验证模型自己的摘要。下一步方案必须回答 source obligation 从何而来、
其错误与候选 parser 是否相关、哪些假设可形式化，以及不确定时为何选择澄清而不是擅自补任务。
