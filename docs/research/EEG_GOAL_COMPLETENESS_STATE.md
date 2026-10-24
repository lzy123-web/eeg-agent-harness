# EEG 科学目标完备性研究状态

最后更新：2026-10-24（Asia/Shanghai）

## 当前边界

- 仓库：`lzy123-web/eeg-agent-harness`
- 分支：`research/eeg-intent-compiler-v1`
- Draft PR：#18
- 任务：Issue #20，仅文献、问题建模、方法设计与 GO/NO-GO 判断
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

## 关键决策

- 研究判断：**CONDITIONAL GO（仅有界 Pilot）/ 当前第二创新点主张 NO-GO**。
- 自由自然语言不能获得绝对目标完备性证明；只能在有限 ontology 中测量 omission recall、dangerous accept 与澄清代价。
- 目标遗漏检测必须拥有候选之外的原文侧 source obligations；只检查候选内部结构属于循环论证。
- ESOCC 不自动补写或执行 missing goal，只能证书化差异并澄清。
- 受控语言是不可削弱的强工程基线；第二 LLM judge 是概率基线，不是 oracle。

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

1. source extractor 与 candidate extractor 的 joint-miss 是否足够低，尚无新实验。
2. 有限 EEG ontology 的闭合边界与双语 exact-span 标注规范尚未冻结。
3. 尚无双人独立标注和一致性结果。
4. “比强 judge/受控语言多出的价值”尚未证明。
5. 尚未完成系统性综述；当前文献判断不能作为全球新颖性证明。

## 若获准开展 Pilot，精确入口

1. 先写纯标注规范和 10–15 例盲标 calibration，不写 Agent 代码；
2. 一致性可接受后冻结 60–100 例新协议与 ontology hash；
3. 实现独立 SourceClaimLedger 与 deterministic matcher，保持 TGSRG/CIEDG 不变；
4. 先离线比较强基线，再决定是否进行有界真实模型调用；
5. 任何危险 joint miss 触发预注册停止，不继续堆规则。

## Git 与远端状态

- 问题模型与文献核查提交：`f04d9f9`。
- 方法比较与研究决策提交：`07b7065`。
- 本状态与项目总状态将在下一提交保存；最终远端 head 与 CI run 在推送后补记。
- 分支将普通推送到 Draft PR #18；不 force push、不合并 main。
