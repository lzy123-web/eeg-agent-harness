# EEG 科学意图作用域研究判断

日期：2026-10-24（Asia/Shanghai）

## 决策

**NOT SAFE TO ADOPT / 工程原型保留 / 独立论文贡献 No-Go。**

TGSRG 确实修复了旧 H14 的已知危险路径：目标、数据阶段和先后关系进入显式图，静态能力证书能在任何 EEG
工具调用前拒绝当前 CIEDG 不支持的双阶段目标；合法单阶段任务仍通过真实执行器和证据门控完成。这不是简单增加
英文关键词，也不是把 gold 放进运行时。

但未见 SH01/Pro 表明，第一层 Intent 一旦漏掉 transition 与下游目标，“仅对已抽取 transition 启动 scope”的
设计会把不完整目标当成单阶段合法请求执行。由于运行时无法证明目标集合对用户原文完备，现有 candidate 没有形成
可靠的端到端安全保证。按预注册停止条件，不继续在 holdout 上补 Prompt、特例或回改 gold。

## 工程价值与研究价值边界

可保留的工程完善：

- 可审计的 goal—state—precedence 中间表示；
- DAG 循环、目标双射、exact evidence、授权隔离和 runtime capability projection；
- 对不支持双分支的明确 `analysis_stage` 澄清；
- 传递可达性替代固定直接边，减少图表达导致的结构误拒；
- 有界评估、失败留痕和真实 Agent 零工具安全停止。

尚不足以作为独立论文贡献：

- 图/lineage/type-and-effect 思想本身有成熟前例；本轮没有证明新的 EEG 语义学习或形式完备性；
- 与强语义检查或第二模型 judge 尚未完成足够规模的公平比较；
- 作用域正确性仍依赖 LLM，且目标遗漏可绕过 gate；
- 2 例/模型、单人 gold 不能支持性能或泛化主张。

因此它更适合作为 CIEDG 前端安全失败的诊断性工程研究，而不是第二个工作点，也不应改写冻结 CIEDG 的正式结果。

## 后续如需继续的严格入口

本 Issue 到此停止，不在当前 holdout 上继续调参。未来只有在新协议、新分支和独立标注条件满足时，才可研究：

1. 与单一 Intent 抽取解耦的“请求目标完备性证明/反证”机制；
2. 对每个原文 claim span 强制覆盖，而不是只验证模型主动提交的目标；
3. 同预算的双解析器或形式化语法基线，并单独报告误拒成本；
4. 新未见数据上把 dangerous accept 作为首要门槛。

在这些条件完成前，默认 Agent 继续使用既有冻结路径，TGSRG v2 仅保留为 opt-in research prototype。
