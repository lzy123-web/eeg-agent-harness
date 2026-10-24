# CCEP v1 后续正式研究与公平实验设计

## 1. 本轮客观判断

CCEP v1 已经有区别于普通 Prompt/Schema/一次性 Validator 的运行机制：真实 EEG 工具结果会改变下一动作，完成项按 artifact 内容 lineage 保留或失效，恢复只处理剩余 frontier，最终发布显式携带实际分支条件。

但这仍不足以证明论文创新。一个同规则 guarded conditional DAG 可以实现 clean/异常/全坏、授权和局部重试的相同决策；当前三例真实 DeepSeek 只验证集成，没有形成相对效果证据。因此当前状态是：

- 工程与机制：Go，保留为 opt-in 研究候选；
- “优于 Native/ReAct”：未检验；
- “优于同规则强 Expert”：未检验；
- “形成论文创新点”：尚不可声称。

## 2. 下一次冻结协议

### 2.1 方法

1. **Native structured Agent**：相同 Registry、Executor、工具描述、最大调用数和错误反馈；不提供 offline gold。
2. **Guarded dynamic Expert DAG**：预编译条件分支，但获得与 CCEP 完全相同的质量 evidence、artifact fingerprint、授权、错误码和恢复预算；不得故意删除动态 guard。
3. **CCEP v1 LRSP**：本轮代码冻结版本；不在 holdout 后调 Intent Prompt 或科学阈值。

意图解析误差与运行时规划误差分别计分。若需要排除语言噪声，应另设 shared parsed-intent 轨道，三方法消费同一 IntentSpec；不能只给 CCEP 正确语义。

### 2.2 任务状态

开发集和 holdout 在运行前冻结，至少覆盖：

- clean、one-bad、all-bad；
- 多条件均有剩余、仅一个条件被筛空；
- 明确禁止筛选、明确授权筛选、缺少授权；
- transient bandpower/quality failure；
- source artifact 丢失、derived artifact 丢失；
- 同 ID 内容变化（明确标为受控一致性探针，不混作自然故障）；
- 质量后继续多个合法 consumer，检查完成项复用而非固定单后缀。

所有阈值、随机种子、输入 shape、错误触发点、请求/Token/工具调用预算和停止规则先冻结。真实 LLM 只使用合成 EEG；真实 EEG 只做本地确定性工具验证。

### 2.3 独立 oracle

- 从原记录与预先异常索引独立重建 Epoch，不调用被测 selection 工具；
- 独立 SciPy Welch 积分核对频带值；
- oracle 检查每条件计数、原 artifact 不变、派生波形、父子关系、参数不漂移；
- 失败恢复检查“哪些步骤必须重算”，不能只看最终 completed。

## 3. 主要指标

优先级从高到低：

1. 科学合法完成 / 正确安全停止；
2. 未授权状态改变、条件静默消失、陈旧 evidence 使用、lineage 错配次数；
3. 最终回答的数值、分支和方法边界忠实度；
4. 故障后的必要重算与无关重放次数；
5. 工具调用、LLM 请求、Token 与运行时间。

不以“总成功率”掩盖安全停止，也不把主动拒绝全部当失败。Native 的自由文本需用冻结 scorer 加人工盲审小样本，CCEP 的结构化 gate 不能因此获得更宽松判定。

## 4. 消融

- ID-only lineage（去掉内容 fingerprint）；
- 去掉 expected quality evidence binding；
- 完整重规划/从头重放替代 residual frontier；
- 去掉每条件 usable guard；
- 去掉确定性 branch disclosure，只保留 LLM evidence paths；
- 在相同状态上用 guarded DAG 替代 LRSP。

本轮受控探针已经为 ID-only 消融提供一个失败例，但正式实验必须在冻结集上运行，不能把单个定向反例包装成总体优势。

## 5. Go/No-Go 规则

- 若 LRSP 只减少少量调用、科学结果与动态 Expert 完全相同：方法价值为工程优化，论文创新 No-Go/需重述。
- 若优势仅来自 Intent Prompt：归为语义接口改进，不归因于动态状态规划。
- 若 LRSP 在新 holdout 上减少陈旧状态、错误重放或不合法分支，且动态 Expert 在同信息/预算下仍无法等价达到：才进入机制精炼与统计验证。
- 若动态 Expert 等价达到，仍可研究声明式可扩展性，但必须用新增 consumer/状态维度的预注册维护成本实验，而非弱化 Expert。

## 6. 当前明确限制

- 动态语义目前只覆盖 event quality/selection/bandpower；连续 PSD、幅值和模型推理沿用 v0。
- 质量阈值未临床校准，每条件 1 个 Epoch 只是工具可计算下限，不是统计充分性。
- artifact store 仅存在于单个进程内存 Context；无持久化、跨进程并发或事务。
- 检查后、工具执行前的并发内容变化会被 expected fingerprint 安全拒绝，但当前被归为永久动作失败，不自动重测。
- retry 只接受声明的 transient error code；没有通用错误分类学习。
- 三个真实 DeepSeek 固定案例全部成功，因此本轮没有语言模型失败分布；唯一明确失败来自受控 lineage 探针，已保留。

精确继续入口是：先冻结上述 guarded Expert/LRSP 协议与 corpus hash，再实现 Expert，最后一次性运行 development 与未见 holdout。不要继续在当前三例上调整 Prompt。
