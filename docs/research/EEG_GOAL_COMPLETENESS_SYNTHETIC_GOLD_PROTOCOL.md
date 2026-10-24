# EEG 科学目标完备性：无标注者受控真值协议

日期：2026-10-24（Asia/Shanghai）  
协议：`eeg_goal_completeness_controlled_gold_v1`  
seed：`21021`  
冻结 manifest SHA-256：`94111eb7a025c0fc7bb4780e53d894cac2d5833c8c21f4ac613b9b073541381a`

## 1. 协议目的和效度边界

本协议不使用外部人工标注，也不让 LLM 生成文本后再给自己打分。研究者先定义结构化 EEG 科学合同，再由确定性模板渲染请求，
从而得到可追溯的 `text ↔ source claims` 真值。它能检验：

1. 有限 claim DSL 是否能无歧义表示操作、对象、阶段、极性、授权和先后关系；
2. typed matcher 对确定性注入的漏操作、错授权、错阶段、缺关系和额外操作能否给出正确诊断；
3. 风险策略能否拒绝不支持目标、澄清冲突，同时不澄清完全一致且可执行的合同。

它**不能**检验自由中英文 source extraction、真实用户表达、独立标注一致性、真实 EEG 泛化或 ESOCC 相对强语义模型的优势。
所有结果必须标为 `controlled synthetic, not independently annotated real NL`。

## 2. 真值来源与冻结边界

- 设计者：单作者/研究开发 Agent；没有第二位 EEG 研究者复核，不报告 IAA、Cohen's κ 或 human accuracy。
- 科学能力来源：仓库现有 event/Epoch 能力和冻结 CIEDG/TGSRG 契约；本轮不修改这些实现。
- 文本来源：手写静态句法和短语表；没有 LLM paraphrase。
- manifest：`config/eeg_goal_completeness_cases_v1.json`，共 24 条受控请求。
- schema：`config/eeg_goal_completeness_schema_v1.json`。
- 生成器：`src/eeg_harness/research/goal_completeness/protocol.py`；相同代码、seed 和 ontology 必须生成相同字节 hash。
- 开发/留出拆分按模板家族，而非随机拆句：development 使用 `dev_en_direct/dev_zh_direct`；holdout 使用
  `holdout_en_sequence/holdout_zh_sequence`。两组表面模板不重叠，但仍共享同一闭合 ontology，不能视为自然语言 unseen。

冻结后不根据 dry run 修改 gold 或模板以追逐满分。若发现协议实现错误，只允许记录原因、修复并重新冻结版本/hash；首次失败必须
保留在研究报告中。

## 3. 最小 EEG Claim DSL

每条 claim 包含：

| 字段 | 语义 |
|---|---|
| `operation` | quality、selection、summary、bandpower、rereference；另含两个明确不支持目标 |
| `object_type` | 本协议固定为 `event_epochs` |
| `target_label` | `target` 或 `control`，不绑定疾病/组别语义 |
| `tmin/tmax` | 事件窗；必须满足 `tmax > tmin` |
| `input_stage` | `source_epochs` 或 `effective_epochs` |
| `output_stage` | 观察操作与输入相同；合法转换产生 `effective_epochs`；禁止转换为 `null` |
| `polarity` | `required` 或 `forbidden` |
| `authorization` | `not_required/granted/denied/unspecified` |
| `supported` | 由冻结 operation catalogue 决定，不能由 candidate 自报 |
| `parameters` | 当前仅筛选 criterion 与重参考通道 |
| `evidence_span` | 请求中唯一、连续、逐字相同的片段 |

合同另含 `precedence`、`runtime_supported` 和 `expected_disposition`。先后边只连接正向 required claim；禁止操作保留为独立 claim，
不能被误写成正向 transition。

### 3.1 支持的操作

- `epoch_quality`
- `trial_selection`
- `epoch_summary`
- `event_bandpower`
- `epoch_rereference`

### 3.2 明确不支持的操作

- `erd_ers`
- `functional_connectivity`

它们只用于验证“明确拒绝而非静默删除”，不代表 Harness 已实现对应算法。

## 4. 科学状态与授权规则

1. quality、summary、bandpower 必须声明读取 source 或 effective Epoch。
2. selection/rereference 的输入为 source，授权执行时输出 effective。
3. `granted` 才允许状态转换；`unspecified` 必须澄清；`forbidden + denied` 必须保持禁止语义。
4. quality → authorized selection → effective summary/power 是当前合法单分支链。
5. authorized rereference → effective quality/summary/power 是合法单分支链。
6. source 分析结果 → transition → effective 分析结果要求同时保留两版本；冻结运行时不能可靠表达时标为澄清。
7. 同时要求 selection 与 rereference 属于未支持转换组合。
8. 不支持 operation 的一致候选仍应拒绝，不能因为“覆盖完整”而执行。

## 5. 文本生成与保真检查

生成顺序固定为：

```text
结构化 prototype
  → ScientificContract
  → 逐 claim 受控短语
  → split-specific 句法模板
  → exact evidence span 唯一性检查
  → frozen manifest
```

英文和中文各有 development/holdout 模板；语言变体只改变表面短语，不改变结构化 gold。每个 evidence span 必须在请求中恰好出现
一次；受控 parser 必须逐句完整匹配，否则 fail closed。任何自由 paraphrase 都不进入 strong-gold 分母。本版没有 `weak_gold`，
因为没有生成不能程序确认的改写。

## 6. Candidate 对照与故障注入

每条请求绑定两个候选合同：

- `exact`：去除 evidence 文本后的完整结构化副本；用于测不必要澄清和不支持目标拒绝。
- `fault`：只注入一个预先登记的结构变化。

24 个 fault 覆盖五类：

- 删除整个 operation；
- 修改 selection/rereference 的授权值；
- 把 observation 绑定到错误数据阶段；
- 删除一条先后边；
- 增加原文没有的 operation。

故障由结构化 candidate 直接产生，不修改自然语言，也不依赖模型输出。因此这里评价的是 matcher 性质，不是 source extractor
能否从自由语言发现目标。

## 7. 两条评价臂

### 7.1 Oracle upper bound

直接比较 manifest 中的 source AST 与 candidate AST。它验证 matcher 是否正确，只是上界，绝不是可部署系统；生产环境不能读取
用于生成文本的 source gold。

### 7.2 Controlled-language parser

parser 仅接受四个冻结模板家族，将句子按完整 clause grammar 还原为 SourceContract，再调用同一 matcher。它是不使用 gold 的
可执行强工程基线，但只对闭合语法有效；遇到自由文本立即拒绝。

## 8. Matcher 与风险输出

matcher 先按 operation/object/target/window 建立候选配对，再比较 stage、polarity、authorization、support 与 parameters；claim 匹配后
把 candidate relation 映射回 source claim ID。结构化输出包括：

- `covered`
- `missing`
- `extra`
- `conflicts`
- `missing_relations/extra_relations`
- `unsupported_operations`
- `disposition = accept/clarify/reject`

匹配器不读取请求、case ID、模板家族或离线预期标签，也不自动补写 missing goal。

## 9. 手工走查示例

### 9.1 禁止筛选并继续计算功率（GD03）

请求明确包含 quality、`do not remove any trial` 和 source bandpower。Gold 中 selection 是
`polarity=forbidden, authorization=denied, output_stage=null`。故障 candidate 把授权改成 granted。matcher 应报告
`authorization_conflict` 并澄清，不能把“测质量”推导成筛除许可。

### 9.2 双阶段重参考（GD07）

请求依次要求 source quality、授权重参考和 effective bandpower。三目标及两条边均可覆盖，但冻结 CIEDG 不能可靠保留两分支，
所以 exact candidate 仍应 `clarify`。删除 quality→rereference 边时还必须额外报告 `missing_relation`。

### 9.3 合法筛选链（GH04）

请求要求 source quality → 授权 selection → effective summary → effective bandpower。完整 candidate 应执行；删除第一条边应报告
`missing_relation`。该例防止系统通过“一律澄清转换任务”获得虚假安全。

### 9.4 不支持目标（GH10）

功能连接在当前 catalogue 中不支持。即使 candidate 完整覆盖，策略仍应 `reject`；若 candidate 额外加入 quality，还要同时报告
`extra_operation`，不能静默把任务缩成可支持子集。

## 10. 复现命令

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -m unittest tests.test_eeg_goal_completeness -v
python -m eeg_harness.research.goal_completeness.evaluation `
  --output docs/research/results/eeg_goal_completeness_no_annotator_v1.json
```
