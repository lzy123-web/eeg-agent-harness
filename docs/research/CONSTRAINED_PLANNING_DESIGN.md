# EEG 状态感知与约束规划：最小方法设计

## 1. 研究问题与边界

本轮研究的问题是：在多任务 EEG Harness 中，把已经验证的数据状态、工具前置条件和中间产物依赖显式用于执行前决策，能否减少不合法调用并提供更清晰的安全拒绝，同时不改变 EEG 数值算法。

这只是先导原型。ToolSpec、Validator、DAG、状态机或结构化错误本身已有广泛先例，也与现有 scientific contracts/preflight/evidence binding 思路重叠；本轮不能仅凭工程实现宣称方法创新成立。

## 2. 执行时校验与规划时约束

| 层次 | 当前/拟实现职责 | 失败时机 |
|---|---|---|
| Executor Validator | 校验单次工具的 schema、Profile、通道、时间窗、采样率、资源和 artifact 是否存在 | 工具被请求之后、算法运行之前 |
| 规划时约束 | 根据当前状态与目标选择合法步骤、补齐明确的 artifact 生产步骤、在任何工具调用前拒绝不可满足目标 | 形成 Plan 时 |
| 执行期状态更新 | 把实际 ToolResult/artifact 纳入当前 Context，必要时有限次重新规划或安全停止 | 每个步骤之后 |

规划层不替代 Executor。三种比较策略均保留相同 Validator；规划层也不得静默修改通道、时间窗、标签或 Profile 来“修复”请求。

## 3. 当前真实 EEG 依赖

- Profile、通道、参考、montage 与采样率必须来自当前 `EEGRecord/TaskProfile`。
- 幅值、PSD 和癫痫工具需要合法通道及 `[start, end)` 窗口；癫痫模型还要求已验证的 `tuev_bipolar_22`、256 Hz 和模型资源。
- Epoch 需要当前记录存在 annotation、请求标签实际存在、`tmin < tmax` 且 baseline 位于窗口内部。
- `epoch_summary/event_bandpower` 消费当前 Context 内由 `create_epochs` 产生的 Epoch artifact；不同 Context、记录或 Profile 的 artifact 不可复用。
- `event_bandpower` 还要求至少 1 秒 Epoch 才能达到当前约定的 1 Hz Welch 分辨率。
- 数据质量目前没有经验证的坏道、伪迹或信噪比事实，因此状态中保持 `unknown`，Planner 不据此推断科学质量。

## 4. 结构化对象

- `TaskSpec`：结构化目标、参数和可选子任务，不包含自然语言临床推断。
- `EEGStateSnapshot`：当前 Context、Profile、来源摘要、采样率、时长、通道、实际事件标签、会话 artifact、资源可用性和已验证质量事实。
- `OperationContract`：工具必需参数、兼容 Profile、资源、事件前置条件、消费/产生的 artifact 和合法状态效果。
- `PlanStep/Plan`：显式步骤、依赖、目的、状态摘要和拒绝原因。

状态快照不包含原始 EEG。artifact 同时绑定 Context、Profile 和去标识记录来源；只能表示已存在事实，不能推断未来输出或标签含义。

## 5. 公平比较预注册口径

比较三种策略，所有策略使用相同 TaskSpec、记录、Profile、Registry、Executor、资源和安全校验：

1. Execution-only：不做全局前置规划，直接请求目标工具。
2. Expert Conditional Workflow：透明、合理的领域条件与已知依赖 DAG，可安全停止，不设置为弱基线。
3. State-Aware Constrained Planner：由状态快照与 OperationContract 构造计划。

任务在实现策略前按生成规则冻结，分为开发集合与保留集合，覆盖合法/非法窗口、通道、Profile、资源、事件、artifact 生命周期及异构组合。分别统计：有效任务完成率、合法拒绝准确性、预执行不合法调用比例、运行时错误、调用数、耗时及重复调用。拒绝不可执行任务不计作“有效任务完成”，错误也不自动等同正确拒绝。

候选方法可能与 Expert DAG 持平或更差。若优势仅相对 Execution-only，或仅来自基础参数校验，则不足以支持论文创新性结论。
