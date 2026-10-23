# CCEP v1 研发状态

更新时间：2026-10-23（Asia/Shanghai）

## 当前阶段

Issue #13 阶段 V：本轮方法审查、下一步公平实验设计和交付已完成。分支继续使用 `research/point1-integrated-method-v0`，Draft PR #11 保持 Draft；Baseline v1 和 CCEP v0 均未替换或合并。

## 已继承事实

- Issue #12 已证明实际 Epoch 筛选、3→2、派生波形和频带数值实现正确。
- CCEP v0 与同规则强 route+preflight 在共享任务完全持平；真实两例中 CCEP 1/2、Native 2/2。
- v0 的 `event_workflow` 在执行前生成完整 DAG；失败后从首步重放，质量结果不进入后续计划状态。
- 当前质量阈值是未临床校准的 screening suggestion，不能当生物医学真值。

## 选定机制

选择 **Lineage-aware Residual Scientific Planning（LRSP）** 作为 CCEP v1 核心：

1. Intent/ledger 冻结用户目标和禁止操作；
2. 确定性科学状态保存 Epoch lineage、质量证据、每条件计数、完成目标和失败；
3. Planner 每次只计算剩余目标的下一个合法 frontier；
4. Executor 仍是唯一工具执行入口；
5. 新证据到达后重新归约剩余目标，不重放仍有有效证据的步骤；
6. LLM 不决定阈值、不看原始数组，也不负责运行时科学分支。

Guarded conditional DAG 将作为未来强动态 Expert；LLM feedback replanning 不作为 v1 主机制。

## 科学不变量

- label、window、source 与用户授权在运行时不可更改；
- 选择必须有同一 artifact 的质量证据与明确授权；
- 无异常时 selection 以 identity transition 满足，不创建伪派生 artifact；
- 任一请求条件在选择后为零试次时停止，不静默遗漏该条件；
- 后续分析只能消费当前存在且 lineage 合法的 artifact；
- artifact 失效会级联撤销依赖它的完成证据；
- transient retry 只重试剩余 frontier，不重放已完成且仍有效步骤；
- 经验阈值、绝对功率非 ERD/ERS 等边界进入 trace/answer。

## 已实现初版

- `ConstraintCarryingEEGAgentV1` 是 opt-in 入口，非事件任务仍走现有 v0 执行语义且不重复做 Intent 调用。
- `ResidualScientificPlanner` 每次只产生一个 frontier action；异常、干净、全坏与禁止筛选四种质量状态会产生不同后续动作。
- transient bandpower 故障只重试 bandpower；已经成功的事件观察、Epoch、质量与选择不重放。
- 真实选择的 3→2 Epoch 数据和 bandpower 已由独立 NumPy/SciPy oracle 验证。
- 初版新增 7 个测试；CCEP v0、证据阶段及 v1 共 33 个相关测试通过。

## 首轮机制修订

- 实测初版无法发现同 ID Epoch 内容在质量后变化，会错误复用旧 evidence。
- 新增 Epoch 内容 fingerprint；质量 evidence 同时绑定 ID、内容和阈值。
- residual planner 在每个 frontier 前检查 fingerprint，内容变化会撤销下游完成项并回到质量测量。
- 选择工具支持 expected evidence/fingerprint；最终回答由运行时追加真实 branch 与经验阈值边界。
- 修订后相关回归 51/51 通过，1 个外部资源模型测试跳过。

## 阶段 IV 结果

- 全仓 `unittest discover`：190 tests，178 passed，12 skipped；skip 均为未显式配置的 EDF/权重/R3/联网资源测试。
- Fake 固定三例：3/3 completed、6 次协议调用；derived、identity、禁止筛选三条分支均实际发生。
- 真实 DeepSeek 固定三例：3/3 completed、6 次请求、15,363 tokens；只使用合成 EEG，工具链和 answer evidence 均通过。
- 未做大规模比较，不把 3/3 外推为可靠率或相对优势。

## 下一步

1. 等待本轮 PR/Issue 审阅，不在当前三例继续调参。
2. 下一研究轮先冻结 guarded Expert/Native/LRSP 公平协议与 corpus hash，再实现和运行。
3. 不扩展第二论文工作点，不合并 main。

## 提交

- 阶段 I：`b85eef2`，研究设计与恢复状态，已推送。
- 阶段 II：`d96c764`，LRSP 初版、Fake/oracle/恢复测试，已推送。
- 阶段 III：`36c4adf`，内容 fingerprint、evidence binding 与回答条件修订，已推送。
- 阶段 IV：`df334d1`，固定 Fake/真实 DeepSeek 合成轨迹，已推送。
- 阶段 V：待提交。
