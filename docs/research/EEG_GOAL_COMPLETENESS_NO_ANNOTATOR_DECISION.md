# EEG 科学目标完备性无标注者 Pilot：结果与研究决策

日期：2026-10-24（Asia/Shanghai）

## 1. 结论先行

**决策：作为独立第二创新点暂时 NO-GO；保留 DSL、manifest 和 matcher 作为可审计实验夹具，暂停继续扩展 ESOCC。**

本轮证明了有限 EEG claim DSL 可以一致表达目标、授权、禁止、数据阶段与先后关系，也证明 typed matcher 能识别结构化注入的遗漏
和冲突。但最关键的研究问题——如何从自由自然语言独立、可靠地得到 source claims——没有被本实验检验。受控 parser 与生成器共享
闭合 grammar，在这种条件下 100% 是一致性测试的预期结果，不是自然语言泛化或方法优势。

## 2. 实际实现

- 新建独立研究包 `research/goal_completeness`，没有接入默认 Intent、TGSRG、CIEDG、Planner 或 Executor。
- 冻结 `eeg_goal_claims_v1`：5 个当前已支持 operation、2 个明确不支持 operation、source/effective stage、polarity、authorization、
  parameters 和 precedence。
- 由 24 个结构化 prototype 确定性生成中英文受控请求：development 12、holdout 12；模板家族不重叠。
- 每条请求含一个 exact candidate 和一个单故障 candidate，共 48 对；故障包括漏操作、授权冲突、阶段冲突、缺关系和额外操作。
- 两条离线评价臂：直接 AST 比较的 oracle upper bound，以及不读取 case gold 的闭合语法 parser。
- 所有诊断均为 JSON 可序列化的 `covered/missing/extra/conflicts/relations/unsupported/disposition`。

## 3. Dry run 结果

原始结果：`docs/research/results/eeg_goal_completeness_no_annotator_v1.json`  
protocol SHA-256：`94111eb7a025c0fc7bb4780e53d894cac2d5833c8c21f4ac613b9b073541381a`

| 指标 | 实际结果 |
|---|---:|
| 受控请求 | 24（development 12 / holdout 12） |
| source–candidate 对 | 48 |
| 故障对 | 24 |
| 受控 parser 与 source AST 完全一致 | 24/24 |
| oracle 检出预置主故障 | 24/24 |
| controlled parser 路径检出预置主故障 | 24/24 |
| exact candidate disposition 正确 | 24/24 |
| 应 accept 的 exact candidate | 16 |
| accept 样例的不必要澄清 | 0/16 |

故障分布：authorization conflict 7、extra operation 4、omitted operation 6、missing relation 4、stage conflict 3。源合同的合法终止为
accept 16、clarify 6、reject 2。

这些数字只描述 24 个研究者设计的闭合样例；没有抽样误差、真实语言分布或独立 gold，不能做统计显著性和泛化表述。

## 4. 发现并保留的实现问题

首次专项测试没有直接通过：

1. 禁止筛选 prototype 未携带 parser 固定赋予的 `criterion=quality_flagged`，导致 round-trip 仅 22/24；修正为所有 selection claim
   统一显式参数，并重新生成 manifest/hash。
2. 单测的故障查找函数只检查第一条 case，导致四类故障 `StopIteration`；修正为跨 case 查找。
3. 初始 runtime rule 把所有“source observation → transition → effective output”都判为不支持，错误覆盖了合法的
   quality → selection → effective consumer 链。修正为：selection 的 source quality 是合法先决条件；其它 source consumer 与
   effective consumer 并存才属于当前不支持双分支。
4. 测试最初假设所有 fault 都应 `clarify`；当 source 本身是不支持 operation 时，正确终止应保持 `reject`，同时报告额外故障。

这些是协议/实现错误，不是方法成功率改进。最终 hash 在修正后冻结，旧失败没有被写成正式成绩。

## 5. 本轮真正验证了什么

### 5.1 已验证

- DSL 能把“测量质量但禁止筛选，随后计算 source power”与“授权筛选后计算 effective power”区分开。
- 授权不是布尔附属字段：`granted/denied/unspecified` 冲突可独立诊断。
- source/effective stage 和 precedence 缺失可以与 operation omission 分开归因。
- 完整覆盖不等于可执行：不支持目标应 reject，多分支或缺授权任务应 clarify。
- matcher 不读取请求文本、模板 ID 或离线期望标签；它只比较调用者提交的两个合同。

### 5.2 未验证

- source extractor 是否能从自由中英文恢复这些 claims；
- source extractor 与原 Intent parser 是否会 joint miss；
- 真实用户是否认为模板语义自然且无歧义；
- ESOCC 是否优于受控语言、用户确认或强 LLM judge；
- EEG 数据、真实实验范式、R3/ASD 或临床泛化；
- 人类一致性、统计显著性或危险遗漏发生率。

## 6. 为什么 24/24 不支持继续宣称创新

受控 parser 与 renderer 共享同一闭合语法，oracle 又直接读取 source AST；两条路径的满分说明实现自洽，而不是系统从未知表达中
发现遗漏。typed matcher 本质是带 EEG 字段的结构化集合对齐；它很有用、可审计，但在没有独立 source extraction 证据时，不能
单独构成足够强的研究贡献。

而且强受控语言基线已经在其定义域内达到同样结果。继续增加模板、同义词或更多人为故障，只会扩大工程资产，不会回答
joint-miss 问题。为了凑第二创新点继续堆模块，研究收益低于对冻结 CIEDG 做正式复现、扩展论文论证和完成综合案例。

## 7. ESOCC 去留判断

### 保留

- source/candidate schema；
- 可复现 manifest、seed 与 hash；
- deterministic matcher 与诊断格式；
- 作为未来 Intent compiler 的回归夹具、受控语言安全基线和论文限制案例。

### 暂停

- 不接入生产 Agent；
- 不创建 v3；
- 不扩充模板数量来制造样本规模；
- 不运行付费 LLM 来追求表面成功率；
- 不把 24/24 写成自由语言性能。

### 只有满足下列新证据之一才重启

1. 获得与本代码独立产生的 EEG 自然语言—workflow 标注；
2. 找到可合法复用的公开 NL→scientific-workflow 数据，并明确 EEG 迁移边界；
3. 用户未来只做 5–10 条单人抽查时，将其标为 researcher spot-check，而不是独立人工 gold；
4. 新预注册实验能直接测量 source extraction joint miss，并有强受控语言/第二 judge 对照。

## 8. 论文策略

当前最稳妥表述是：目标完备性是 CIEDG/TGSRG 的已知输入信任边界；本轮提供了一个可复现的受控校准夹具，证明 typed coverage
诊断在闭合合同上可实现，但没有证明其解决开放自然语言。因此 ESOCC 不作为已经成立的第二创新点。论文资源应优先投入冻结
CIEDG 的正式复现、边界分析和综合应用；若未来没有独立语义证据，本方向以安全限制和未来工作收束。
