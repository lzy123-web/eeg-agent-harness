# 工作点一可扩展性研究决策

## 决策

**NO-GO：当前证据不足以把“相同科学正确性下显著降低新 EEG 任务维护成本”作为 CIEDG 工作点一的主要论文贡献。停止继续通过新增工具堆叠这一主张。**

这不是说 CIEDG 没有机制价值。本轮证实它能把新只读 consumer 接入已有 source/effective Epoch、selection/rereference、失效和内容寻址恢复，且新增 consumer 不需要专用 graph/recovery 代码；其增量条件节点少于 Expert（6 对 11）。但公平允许 Expert 做表驱动抽象后，方法特定增量 LOC 为 42 对 41，文件数和运行调用完全持平，没有出现足以支撑主要贡献的维护成本差异。

## 假设为何没有被当前实现支持

1. **端到端扩展仍有枚举硬编码。** IntentSpec、`compile_intent`、静态 Planner、基础 `_required_answer_tools` 都知道具体目标；ToolRegistry 单独注册并不能使自然语言到证据发布自动闭合。
2. **状态族尚未统一声明化。** selection 与 rereference 由不同 planner 类处理，reference planner 构造器固定 contracts，组合被显式拒绝。新 consumer 跨两个状态族需要 adapter glue。
3. **强 Expert 并非只能复制完整 DAG。** 当消费者具有相同 artifact 契约时，Expert 可以合法抽取 consumer 列表和统一恢复循环，显著降低组合分支；公平实验必须承认这一点。
4. **样本只覆盖一个只读 consumer。** 条件分支的差异可能在更多消费者下累积，也可能被更好的 Expert 抽象消除；当前不能外推。

## 仍可保留的工作点一表述

更稳健的表述是：CIEDG 提供**可审计的 EEG 科学状态—目标—证据依赖、内容/身份分离和有界局部恢复**。Issue #16 的消融表明去掉 scientific guards 会产生未授权转换，whole replay 增加调用；本轮进一步显示这些机制能复用于一个新 consumer。但它与同知识 Strong Expert 的科学正确性和工具成本持平，扩展维护成本也未形成明确优势。

因此：

- 可把 contract-indexed evidence graph 作为方法架构和可审计性贡献讨论；
- 不应写成“比强 Expert 更准确”“更省工具调用”或“已证明显著降低维护成本”；
- 若学位论文要求工作点一必须相对强 Expert 展示明确优势，现阶段仍是 **Conditional/No-Go**，需要导师层面的贡献定位，而不是继续加 CIEDG v1.x 功能。

## 停止与后续入口

- 冻结本轮结果，不增加第三种状态转换，不再用更多 consumer 反复寻找优势。
- 保留 Issue #16 正式实验与 ESOCC No-Go 历史，不修改分母和失败。
- 下一工程/应用工作应回到本地 R3/ASD 适配或独立第二研究问题；真实数据只在本地处理，先确认标签/实验语义。
- 若未来正式研究维护性，应先定义跨团队/跨任务的外部变更集和盲审维护实验；不能用本轮 LOC 代理替代人因研究。

