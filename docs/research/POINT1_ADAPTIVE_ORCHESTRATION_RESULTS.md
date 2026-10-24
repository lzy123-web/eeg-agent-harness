# Issue #32 真实工具链原型与公平最小比较结果

日期：2026-10-25。源码 `src/eeg_harness/research/adaptive_orchestration.py`、`adaptive_orchestration_baselines.py`、`adaptive_orchestration_eval.py`，所有数值工具经现有 `ToolRegistry → ExecutionContext → Executor`，无第二执行器。只用确定性合成 EEG；真实受试者数据与外部 LLM 均未使用。

## 1. 先冻结、后实现、再只运行一次未见集

| 节点 | 事实 |
|---|---|
| 协议 `4a3dc46` | D1–D9 与 H1–H5 的目标、合成记录、oracle、禁令、预算和止线先于原型提交；H 不是从旧 C1–C8/Issue #16 文句重标。 |
| 初版 `1af47b5` | 真工具链、固定顺序和独立强动态 Expert 三臂；保存 `results/point1_adaptive_dev_v1.json`、`...probe_initial.json`。开发 D1–D9 均科学正确；额外**后设开发探针** D10 暴露三臂跨事件 scope 的无谓 consumer。 |
| 修订 `8486657` | 候选与 Expert 均增加全局 inventory 门，先检查全部作用域，再建 Epoch，最后执行消费者；固定计划不改。保存 `...dev_revised.json`、`...probe_revised.json`。第一次评价器错误把无谓调用算作科学失败，现分离 `global_gate_ok`，旧原始文件保留。 |
| 预冻结 H1–H5 | 仅在 `8486657` 后运行一次主评价，原始逐例结果 `results/point1_adaptive_holdout_v1.json`。后续发现非 JSON `baseline` 可在 group 构造前引发异常；仅加静态校验与回归，**不根据 H 结果改主张/gold**。`...postfix_replay.json` 是最终代码的已见回归，不重新称未见集。 |

命令（已有 Python 3.10 `eegagent`，先设 `PYTHONPATH=src`）：

```powershell
python -m eeg_harness.research.adaptive_orchestration_eval --set dev --output docs/research/results/point1_adaptive_dev_revised.json
python -m eeg_harness.research.adaptive_orchestration_eval --set holdout --output docs/research/results/point1_adaptive_holdout_v1.json
python -m unittest discover -s tests -q
```

输出 JSON 保存各臂每例的请求、真实 ToolResult、Context trace、策略决策、独立 oracle、工具数和耗时。路径只含合成来源，不含本地模型路径或真实数据。试次最小值是请求者显式给定的实验条件，不能解释为普适 EEG 科学充分性。

## 2. 主指标：科学正确、动态现象、成本

| 划分 | 策略 | 独立 oracle 全部科学条件 | 工具调用总数 | 可重复的区别 |
|---|---|---:|---:|---|
| D1–D9 开发 | 渐进需求/反馈策略 | 9/9 | 14 | D3 停于 inventory；D4 停于 Epoch 后；D2 继续功率；D5 避免不可能发布的 PSD。 |
| D1–D9 开发 | 固定用户目标顺序 + 同规则 preflight/guard | 9/9 | 15 | D5 先做一次 PSD 后才发现事件不足。 |
| D1–D9 开发 | 同规则强动态 Expert | 9/9 | 14 | 与候选完全持平。 |
| H1–H5 一次未见 | 渐进策略 | 5/5 | 9 | H1 双目标完成；H2 边界导致建 Epoch 失败；H3 无事件后不做 PSD；H4 零调用非法通道拒绝；H5 禁观察时直接建 Epoch。 |
| H1–H5 一次未见 | 固定用户目标顺序 | 5/5 | 10 | H3 多一次 PSD，科学发布仍安全。 |
| H1–H5 一次未见 | 强动态 Expert | 5/5 | 9 | 与候选完全持平。 |

**客观解释：**有明确的中间反馈驱动分支，不能用“一次类型路由”描述；但相同科学规则的强专家可同成本实现，没有独立正确性/调用收益。固定臂不是决定性强对手，差 1 次 PSD 只能说明静态用户顺序在原子失败情境有无谓成本。所有方法均未误发布完整 bundle。运行耗时很小且受顺序/缓存影响：开发集累积 wall time 候选 4.67 ms、固定 4.71 ms、Expert 4.32 ms；未见集候选 3.83 ms、固定 3.70 ms、Expert 3.56 ms。没有重复/置信区间，不得据此声称速度优势。昂贵模型未进入主集合，因此调用数不是成本通用结论。

数值独立核验示例：H1 连续 alpha PSD 原工具/独立 Welch 均 `2.00e-10`（V²），事件 `target` 3 个边界内 Epoch 的 alpha 均值原工具/独立切片 Welch 均 `1.9999999920083944e-10`（V²）。D2 原始 `stimulus` 事件 3 个，但有效 Epoch 2 个，事件 alpha 独立与工具相同。`result.success` 没有作为 oracle；以合成数组与时间直接重算。不能外推真实 EEG 的特征稳定性。

## 3. 逐类失败与限制，不归因错位

| 案例/层次 | 结果与归因 |
|---|---|
| D8 | 缺用户显式事件标签，三臂均零工具澄清；这是**输入科学信息缺口**，非 LLM 解析率实测。 |
| D9 | 2 导原生 Profile 不适用既有严格 22 导/256 Hz 模型，三臂零模型调用；这是**资源/Profile 科学适用性**，不计模型任务失败。 |
| D10 后设开发探针 | 初版三臂依次 `list_events → create_epochs → event_bandpower → list_events` 才停；属于**全局多目标编排效率缺陷**，非误发布。修订后候选/Expert 各 1 次 inventory 停止，固定 4 次；两动态臂仍持平。此例不计未见成绩。 |
| H2 | 2 个原始事件都靠近记录终点，建 Epoch 返回 `EPOCH_CREATION_FAILED`，未调用派生功率；属于**真实工具对边界数据的科学限制**，不是 planner 修复后可擅自换窗口。 |
| H3 | 缺事件而有独立 PSD 请求，整单原子发布要求下先停，候选/Expert 1 次、固定 2 次；不发布固定已算出的部分 PSD。 |
| 额外安全审查 | `baseline` 非 JSON/非法范围可能在图分组时抛异常；H 主评价之后添加静态拒绝测试。`postfix_replay` 五例保持数值/调用不变，明确属于已见回归。 |
| 自然语言 | 本轮结构化目标验证不测 LLM 用户目标漏提、参数归属、澄清文本和最终自由回答；原 C2 语言失败原样保留，不能算本方法修复。Native ReAct/普通 tool calling 在本轮为 **N/A**，没有 Fake 冒充真实模型。 |

## 4. 模型、扩展与回归边界

模型资源只在本地临时环境变量显式指定既有权重时，用**合成** `tuev_bipolar_22` 记录通过原 `seizure_detection` 真实工具做 1 秒、1 通道输出结构检查；结果为长度 1 的列表和两项模型分数键，未记录/发布分数，也不作诊断或模型效能推断。无权重时该测试 skip；错误 2 导 Profile 在 D9 零调用拒绝。没有外发权重或私有路径。另一个后设开发检查把已注册 `amplitude` 加到事件组合中，候选和 Expert 无新目标名分支、同一调用序列、独立平均绝对幅值核验通过；**这不是新工具扩展成本实验**，不能从中推论新增任意任务更省人工。

最终代码本地 `compileall -q src tests`、`pip check` 通过；`unittest discover -s tests -q` 为 **287 tests OK / 16 skipped**（无模型资源）或 **287 OK / 15 skipped**（合法本地既有权重）；定向 pytest 为 13 passed / 1 skipped，带权重为 14 passed。[GitHub `unit-tests` #195](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40124609648) 对研究交付提交 `c1be342` 已 `success`。外部 LLM 预算实际 **0 completion / 0 tokens**，因为结构化策略已可由真实工具与独立 oracle 验证；没有触碰真实受试者 EEG。初版与修订的合成原始输出均保留，不覆盖旧负结果。

## 5. 研究判断

**最小原型证明了“科学需求与中间执行反馈可以改变同一任务的后续计划”这一可行性命题；没有证明相对动态 Strong Expert 的独立算法增量。** 方法当前是确定性的 EEG 前提门控 + 层次展开，成熟 HTN/条件工作流原则上可实现，而我们的实测强专家也完全持平。它较单次路由/固定用户顺序更合适于原子跨任务请求，但论文贡献还需要证明独立的适配成本、规模扩展或科学正确性收益。本轮仅 9 开发 + 5 合成未见，样本太小且近似正弦，不得宣称泛化/显著性。下一步唯一有价值的实验是预冻结一个**新增科学分析能力及多个独立条件 scope**的扩展成本/信息代价对照，让合理 Expert 也能抽象复用；若继续持平，应将本机制写为系统工程设计而非新规划算法。
