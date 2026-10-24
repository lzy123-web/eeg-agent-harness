# CIEDG 可扩展性小型实证协议（冻结）

## 1. 唯一能力增量

新增 `epoch_variance` 只读 consumer。输入为现有 `EpochSet` artifact；输出包括 artifact ID/fingerprint、方法 `population_variance_ddof_0`、按事件条件与通道汇总的方差、每个条件试次数。对条件 \(c\)、通道 \(k\)，把该条件所有 Epoch×时间样本展平为 \(x_i\)：

\[
\operatorname{Var}_{c,k}=\frac{1}{N}\sum_i(x_i-\bar{x})^2
\]

工具用 `numpy.var(..., ddof=0)`；独立 oracle 用显式均值、平方离差和除法，不调用工具函数。比较容差固定为 `rtol=1e-6, atol=1e-15`。该统计是描述性特征，不解释为临床指标，不产生新 EEG 状态。

## 2. 冻结公平实现计划

### 共有适配

1. 隔离 Registry 在默认 Registry 上注册同一个 `epoch_variance` ToolSpec。
2. 同一个 deterministic fixture、parsed TaskSpec/ledger adapter、fault executor、oracle 和 scorer 服务两种方法。
3. 同样的 `max_tool_calls=16`、`max_repairs=2`、瞬时 retry 上限 1。

### CIEDG+extension（不是冻结 Candidate 本体）

1. 增加一个 `consumer/effective_epochs` GoalContract。
2. 通过隔离 planner 子类把该 answer-required contract 纳入 Evidence Gate；不修改 graph、binding、reconcile 或 cache 核心。
3. selection 与 rereference 继续使用各自原 planner 语义，不开放二者组合。

### Expert+extension

1. 保留同规则过程式 event/epoch/transition/recovery。
2. 允许把只读 consumers 抽为描述表/循环；新增 consumer 不要求复制整个 expert。
3. artifact 重建后：fingerprint 相同可发布不可变历史结果的 current-lineage view；fingerprint 改变必须重新执行。

上述计划在看到实验结果前冻结。实现中只能修复代码/评价器错误，不能改变科学真值、预算或削弱 Expert。

## 3. 冻结案例

| ID | 状态族/目标 | fault | 科学期望 |
|---|---|---|---|
| X01 | source：variance | none | consumer 绑定原始 Epoch；oracle 一致 |
| X02 | selection：quality+授权筛选+variance | none | 异常 Epoch 被排除，variance 绑定 selected effective artifact |
| X03 | source：quality+variance，明确禁止筛选 | none | 不调用 selection；variance 基于全部 source Epoch |
| X04 | rereference：授权重参考+variance | none | variance 基于 rereferenced effective artifact；逐元素 oracle 派生后再算方差 |
| X05 | selection：variance+bandpower | bandpower 时 effective artifact expiry | 重建内容相同；variance 可安全语义复用到当前 lineage，结果与 oracle 一致 |
| X06 | rereference：variance+bandpower | bandpower 时 source 内容改变并清空 artifacts | fingerprint 改变；variance 必须重算，不得释放陈旧数值 |
| X07 | source：variance | variance one-shot transient failure | 两种方法均只重试失败 consumer，不重放已完成 producer |

所有案例使用合成 EEG；新 consumer 与既有 bandpower 的输入必须指向同一 effective artifact。X03 的 `select_quality_epochs` 是 forbidden tool。

## 4. 冻结指标

1. **科学正确性**：状态转换、effective artifact、条件试次数和全部 variance 数值通过独立 oracle；禁止操作未执行；无 stale release。
2. **恢复能力**：合法终止、repair/retry 次数、内容等价复用或内容变化重算行为符合 case gold。
3. **运行成本**：逐例及总工具调用；不预设 CIEDG 更少。
4. **方法特定维护代理**：新增/修改方法特定文件数、非空非注释 LOC、AST 条件分支（`if`/条件表达式/`match`）、新目标字面量引用数、是否修改冻结 core。
5. **回归影响**：隔离测试、全仓 pytest、compileall、pip check；冻结 Issue #16 文件 hash/工作树不被修改。
6. **组合性**：新 consumer 单独、与质量证据、selection/rereference、既有 bandpower 是否在不增加组合专用分支的前提下执行。

不测量开发工具耗时，不把 LOC 换算成人类工时。CIEDG 若需修改 graph/reconcile/cache 核心，或方法特定适配不低于经合理抽象的 Expert，主张判为不支持；若仅在此 consumer 上较少，也只能形成窄范围支持，不能外推到新转换或新任务类型。

## 5. 停止条件

- 不为改善结果修改冻结 Candidate/Expert/Issue #16 结果。
- 不实施第三种状态转换或 selection+rereference 组合。
- 若隔离 adapter 需要大规模 core 重构，停止于审计并给出 No-Go。
- 不运行 DeepSeek；parsed-task 可扩展性无需付费模型。

