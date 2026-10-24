# EEG 科学目标完备性：候选方法比较与最小设计

日期：2026-10-24（Asia/Shanghai）

## 1. 设计目标与不可越过的边界

目标是在有限 EEG 工具域内发现：候选 Intent 是否遗漏了用户**明确要求**的科学操作、输出、禁止、授权或阶段关系。
检测器必须拥有候选 Intent 之外的原文侧观察量，否则只是让模型验证自己的摘要。

本轮不实现方法。以下设计也不承诺自由自然语言的形式完备性；只有受控语法、闭合 ontology 与已验证 parser 的交集内，
才可能谈相对完备。自由中英文请求只能得到经验性的 coverage certificate 与有界风险。

设计约束：

- 不读取离线 gold，不使用实验场景 ID，不查看未来执行结果；
- source-side 解析必须先于且独立于候选 Intent，不能把候选目标当检索提示；
- 静态规则只核对类型化字段，不从自由文本中“猜回”被遗漏目标；
- 不确定时只澄清，不自动补写或执行用户未确认的状态转换；
- EEG 波形不进入外部模型；只处理用户请求、工具 catalogue 与必要的非敏感元数据；
- 必须保留 exact span、未解析片段、匹配理由和拒绝原因，允许人工复核。

## 2. 路线 A：原文侧 Claim Ledger + 双射覆盖证书

### 2.1 核心机制

在生成执行 Intent 之前，从原文独立构造 `SourceClaimLedger`。每条 claim 至少包含：

```text
claim_id, exact_span, act_type, scientific_object,
input_stage, output_stage, polarity, authorization,
relation_targets, confidence_or_unresolved
```

执行 Intent 再投影成相同 claim schema。确定性 matcher 计算二部图，而不是只比较目标名称：

```text
SourceClaimLedger ── typed match ── CandidateClaimLedger
       │                                  │
       └── missing / ambiguous / covered / extra ── CoverageCertificate
```

匹配键包含 operation/object、阶段、极性、授权作用域及关系。证书不能仅有布尔值；它必须报告：

- `covered_source_claims`：有唯一且兼容候选 claim；
- `missing_source_claims`：原文 claim 无匹配；
- `ambiguous_matches`：一对多、阶段不明或 exact evidence 冲突；
- `unsupported_source_claims`：用户明确要求但 catalogue 无能力；
- `extra_candidate_claims`：候选目标缺少原文支持；
- `unresolved_clauses`：source parser 无法可靠归类、但不能静默丢弃的片段。

策略层按风险选择：高风险 transformation/prohibition/stage claim 未覆盖时必须澄清；低风险输出格式缺失可提示；只有覆盖闭合
且 CIEDG/TGSRG 后续验证通过才进入规划。

### 2.2 SH01 走例

Source ledger 应独立产生：

1. `epoch_quality(source, target, 0–1 s)`；
2. `epoch_rereference(source→effective, SYNTH-C2, authorized)`；
3. `event_bandpower(effective/new-reference)`；
4. `quality ≺ rereference ≺ bandpower`。

Flash 候选三目标可进入 TGSRG，随后因当前 CIEDG 不支持双分支而安全澄清。Pro 候选只有 quality；二部匹配得到 S2/S3/S4
缺失，必须在 Intent 进入 Ledger 前澄清。系统不能自动补执行重参考。

### 2.3 优势、假设与失败面

- 优势：遗漏成为可审计集合差，而不是笼统 LLM judge 分数；可以与 CIEDG/TGSRG 串联而不修改冻结方法；EEG 阶段、
  lineage、授权可进入类型系统。
- 核心假设：source extractor 对关键 claim 的 recall 足够高，且与 candidate extractor 的错误不完全相关。
- 主要风险：若两个 extractor 共享模型、Prompt 结构或语义偏差，会一致漏掉 SH01；ledger 看似闭合但仍是假闭合。
- 防护：source extractor 不看 candidate；先做子句枚举并保留 `unresolved_clause`；使用不同的任务分解与输出顺序；实验中单独
  量化 source recall，不把 matcher 成功等同于系统正确。
- 成本：多一次受限解析调用和一套 EEG claim ontology；matcher、审计和风险策略可确定性实现。
- 可解释性：高。每个 missing claim 能定位到 exact span 和不匹配字段。

## 3. 路线 B：受控 EEG 请求语言 + 类型化语法

### 3.1 核心机制

为闭合工具域定义受控语言，例如：

```text
MEASURE quality ON source(target, 0s..1s)
THEN AUTHORIZE rereference(channel=SYNTH-C2)
THEN COMPUTE bandpower ON effective
```

parser 对语法内请求生成唯一 AST；类型检查器验证 operation、data stage、authorization 和 temporal relation。自由语言先被转换为
该语言，并要求用户确认 canonical form，确认后才执行。

### 3.2 SH01 与能力边界

若用户直接提交或确认上述 canonical form，三目标和两条顺序边不会被 parser 静默遗漏；目标完备性是相对于受控语法的。
但从原始 SH01 到 canonical form 的 LLM 翻译仍可能只生成 quality。若没有用户确认，问题只是前移而未解决。

### 3.3 优势、假设与失败面

- 优势：在支持子集内可给出最强静态保证；非常适合作为强工程基线和高风险操作界面。
- 假设：用户愿意确认形式化请求；ontology 与 grammar 足够稳定。
- 风险：中英文同义、隐含条件和复杂实验范式会产生高拒绝率；语言覆盖扩张成本高；用户确认可能流于形式。
- 成本：grammar、parser、编辑器/确认 UI 与版本化规范；外部模型调用可以为零。
- 可解释性：最高，但自然语言体验和开放任务覆盖最弱。
- 研究独立性：主要是安全工程；除非证明新的 EEG 类型系统或交互协议，否则论文新颖性有限。

## 4. 路线 C：往返重建 + 双向蕴含/反事实遗漏检测

### 4.1 核心机制

从候选 Intent 生成规范化请求 `R(P)`，再比较原文 `U` 与 `R(P)`：

- `U ⇒ R(P)` 检查候选是否有原文支持；
- `R(P) ⇒ U` 的操作性近似用于发现原文比重建更丰富；
- 将原文分成命题单元，逐个删除或遮蔽，检查候选是否随关键命题变化；
- 第二模型输出带证据 span 的 `entailed / missing / conflicting / uncertain`。

SH01 的 Pro 重建只会说“测量 target Epoch 质量”；原文中的 rereference 授权与 new-reference power 无法由重建覆盖，judge
应返回 missing。

### 4.2 优势、假设与失败面

- 优势：对开放表达更灵活，不必先冻结全部同义词；反事实测试比一次“是否完整”判断暴露更多信息。
- 假设：judge 与原 parser 的错误足够独立；蕴含标签在科学语言上可校准。
- 风险：自然语言蕴含不是形式证明，双重否定、阶段和授权很容易被 judge 混淆；共享基座会产生相关遗漏；逐子句反事实成本高。
- 成本：至少一个额外 judge 调用，反事实版本可能线性增加 token/延迟。
- 可解释性：中等；必须输出 exact evidence 和冲突类别，否则只得到不可审计分数。
- 研究独立性：若只是“再问一次 LLM”，属于弱工程补丁；只有与类型化 EEG claim 和选择性风险校准结合才可能形成研究对象。

## 5. 路线 D：风险选择性澄清（策略层，不是独立检测器）

当 source ledger 与 candidate ledger 不一致、存在 unresolved clause，或 judge/grammar 之间分歧时，系统不猜测目标，而生成
最小澄清问题。风险函数可考虑：

```text
risk = operation_effect × lineage_impact × authorization_ambiguity × downstream_dependence
```

它不能独立发现遗漏，必须叠加 A/B/C 的某种观察量。其价值在于把不可消除的自然语言不确定性变成可测的 abstention：危险误接受、
合法任务误拒、用户打断次数和澄清后恢复率可以共同评价。

## 6. 横向比较

| 维度 | A：source ledger | B：受控语言 | C：round-trip/judge | D：选择性策略 |
|---|---|---|---|---|
| 独立于候选的观察量 | 是，但 extractor 仍可能相关 | 语法内是 | 弱到中，取决于 judge 独立性 | 否 |
| 自由语言覆盖 | 中 | 低 | 高 | 继承上游 |
| 可形式化程度 | matcher 高、source extraction 低 | 语法内高 | 低 | policy 可确定 |
| EEG 特异性 | claim/stage/lineage/authorization | EEG 类型语法 | 需额外注入 ontology | 风险权重可 EEG-specific |
| SH01 预期 | 缺 S2/S3/S4→澄清 | 确认 AST 后安全 | 可能检出，非保证 | 对分歧安全澄清 |
| 主要失败 | 双 extractor 共漏 | NL 前端漏或用户负担 | judge 共错/不稳定 | 过度澄清 |
| 实现成本 | 中 | 高 | 中到高 token | 低到中 |
| 适合作为强基线 | 是 | 是 | 是 | 否，属组合层 |

## 7. 推荐候选：A + D 的有限域覆盖证书

若未来进入下一阶段，最值得做的不是 v3 Planner，而是一个位于 Intent 前的
**EEG Source-Obligation Coverage Certificate（ESOCC）**：

```text
用户原文
  ├─ 独立 source claim extraction ─ SourceClaimLedger
  └─ 原 Intent extraction ─ CandidateClaimLedger
                              │
                deterministic typed bipartite matcher
                              │
        CoverageCertificate + risk-selective clarification
                              │
              TGSRG → CIEDG → Executor → Answer Gate
```

它与 CIEDG/TGSRG 分工明确：ESOCC 问“原文目标是否都进入合同”，TGSRG 问“合同中的目标阶段关系是否合法”，CIEDG 问
“合法合同如何随 EEG 状态、证据失效和恢复执行”。推荐仅限**条件性研究候选**；本轮没有实现或验证。

## 8. 公平实验蓝图（未执行）

### 8.1 数据与标注

- 新建且预注册 60–100 条中英双语多目标请求；Issue #17/#19 旧例只作 development regression，不能包装成 unseen。
- 分层覆盖：单目标、完整多目标、整个操作遗漏、阶段/关系遗漏、授权/禁止遗漏、输出消费者遗漏、不支持目标混合、干扰句。
- 两名具备 EEG 背景的独立标注者标注 source claims/exact spans/风险，报告一致性并由第三方或共识会议裁决。
- 冻结 tool catalogue、ontology、Prompt、模型标识、采样参数和 hash 后再打开 holdout。

### 8.2 公平对照

1. Intent compiler v1；
2. TGSRG v2；
3. 单独第二 LLM completeness judge；
4. 受控语言/确认式强工程基线；
5. ESOCC 候选；
6. ESOCC 去掉 exact-span/unresolved/risk policy 的必要消融。

所有方法看到相同请求和 catalogue，不得读取 gold。报告同调用数结果与 cost-normalized 结果；不能降低强基线的 EEG 规则或授权能力。

### 8.3 指标与归因

- 主安全指标：dangerous accept 数、危险遗漏 recall、每类遗漏 recall；
- 效用指标：合法请求 false clarification、prompt-level exact coverage、用户打断次数；
- 成本指标：请求数、tokens、延迟；
- 可靠性：模型/语言/改写稳定性、校准曲线、置信区间；
- 分层归因：source extraction、candidate extraction、matcher、policy、TGSRG/CIEDG、answer evidence。

使用配对 bootstrap 或精确配对检验并报告置信区间；小样本“0 次危险接受”不能写成零风险。

### 8.4 预注册停止门槛

- 任一 holdout 高风险遗漏被危险接受：不得宣称安全采用；
- source extractor 的危险 claim recall 未显著高于 candidate parser，或两者共漏占主导：方法 No-Go；
- 相对第二 judge/受控语言基线没有降低危险接受，或通过大量误拒换取表面安全：独立研究贡献 No-Go；
- 只有在新 holdout 上同时改善危险遗漏、保持可接受澄清成本，并显示 EEG typed coverage/风险策略的必要性，才进入论文候选。

## 9. 本轮结论

三条实质路线都可定义，但没有任何一条在本轮获得实验支持。A+D 最能把“原文目标集合”变成可审计对象，也最容易与冻结的
CIEDG/TGSRG 分层集成；其最大未解问题恰是 source extractor 自己也会漏。B 应作为强工程对照，C 应作为概率基线，不能把
二者弱化来制造候选优势。
