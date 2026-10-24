# EEG 科学目标完备性研究状态

最后更新：2026-10-24（Asia/Shanghai，Issue #21）

## 当前边界

- 仓库：`lzy123-web/eeg-agent-harness`
- 分支：`research/eeg-intent-compiler-v1`
- Draft PR：#18
- 任务：Issue #21，无外部标注者条件下的结构化真值与离线 matcher Pilot
- 冻结项：CIEDG、TGSRG、Intent compiler v1/v2、历史 Prompt、协议、原始结果和测试

## 已完成

1. 复核 Issue #17/#19 原始失败与源码控制流；确认 SH01/Pro 的 candidate Intent 只保留 `epoch_quality`，v2 因候选中没有
   transition 而绕过 scope gate。
2. 建立 soundness、completeness、executability、faithfulness 的分层定义和六类遗漏模型。
3. 核查约束解码、NL→planning、计划验证、instruction following、workflow/provenance、EEG Agent、EEG preprocessing 与
   reporting 文献/标准，共 13 项来源。
4. 比较三条主体路线：source claim ledger、受控 EEG 语言、round-trip/NLI；另将风险选择性澄清定义为策略层。
5. 选择 `SourceClaimLedger + typed coverage certificate + risk-selective clarification` 作为条件性 Pilot 候选。
6. 给出独立标注、公平强基线、评价指标、消融和预注册停止门槛。
7. 在无法取得两名 EEG 标注者后，冻结 24 条结构化 prototype 驱动的受控请求、独立 schema、seed 与 manifest hash。
8. 实现只用于研究的闭合语法 parser、source–candidate typed matcher 和离线 evaluator；没有接入生产 Agent。
9. 对 48 个 candidate 对完成无 LLM dry run；24 个预置故障均被识别，16 个合法 accept exact 对无多余澄清。
10. 保存首次协议/测试失败及修正原因，没有把修正前结果包装为正式成绩。

## 关键决策

- 最新研究判断：**ESOCC 作为独立第二创新点暂时 NO-GO；受控夹具工程保留，方法扩张暂停**。
- 自由自然语言不能获得绝对目标完备性证明；只能在有限 ontology 中测量 omission recall、dangerous accept 与澄清代价。
- 目标遗漏检测必须拥有候选之外的原文侧 source obligations；只检查候选内部结构属于循环论证。
- ESOCC 不自动补写或执行 missing goal，只能证书化差异并澄清。
- 受控语言是不可削弱的强工程基线；第二 LLM judge 是概率基线，不是 oracle。
- 本轮满分只证明闭合 grammar/DSL/matcher 自洽，未验证 source extraction 或自由自然语言。

## 本轮未做

- 未开发 v3、未修改任何 `src/`、`tests/`、`config/`、历史结果或冻结方法；
- 未运行新的 Fake/DeepSeek/其他 LLM 实验；
- 未修改既有评价分数、科学 gold 或模型输出；
- 未发送真实 EEG、受试者信息、事件时间或派生结果；
- 未声称 ESOCC 有效、优于基线或已构成论文创新。

## 交付文档

- `EEG_GOAL_COMPLETENESS_FAILURE_MODEL.md`
- `EEG_GOAL_COMPLETENESS_LITERATURE.md`
- `EEG_GOAL_COMPLETENESS_DESIGN_OPTIONS.md`
- `EEG_GOAL_COMPLETENESS_RESEARCH_DECISION.md`
- 本状态文件

## 未解决问题

1. source extractor 与 candidate extractor 的 joint-miss 仍完全未验证。
2. 无双人独立标注；不得报告 IAA 或 human accuracy。
3. “比强 judge/受控语言多出的价值”未证明；闭合 parser 已达到同样结果。
4. 受控模板的自然性和真实请求覆盖没有独立证据。
5. 尚未完成系统性综述；当前文献判断不能作为全球新颖性证明。

## 后续恢复条件

1. 取得独立来源的自然语言—workflow 标注或可迁移公开数据；
2. 或由用户进行少量单人 spot-check，但明确不是独立 gold；
3. 新协议预注册 source extraction joint miss 与强基线后才可重启；
4. 在此之前不扩模板、不创建 v3、不接生产 Agent。

## Git 与远端状态

- 问题模型与文献核查提交：`f04d9f9`。
- 方法比较与研究决策提交：`07b7065`。
- 本状态与项目总状态提交：`0d144cc`；GitHub Actions `unit-tests` run `40061585223` 成功。
- Issue #21 受控协议与 matcher 原型提交：`13f73ed`。
- dry run 原始结果与 NO-GO 决策提交：`3196ed7`。
- 本地验证：`compileall`、`pip check` 通过；249 tests：237 passed、12 resource-gated skipped、0 failed。
- 回归状态提交：`6a89d21`；GitHub Actions `unit-tests` run `40064384919` 成功。
- 分支普通推送到 Draft PR #18；不 force push、不合并 main。
