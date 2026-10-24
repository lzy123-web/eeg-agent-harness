# 多任务 Harness 方法研发状态（Issue #26）

- 分支：`research/multitask-harness-method-v2`，从已审查的 `research/point1-integrated-method-v0` `bff8940` 建立；远端基线 SHA 已经仓库接口核对一致。旧 CIEDG、Issue #16 gold/trace/results 不改。
- 当前阶段：A 任务族与机制缺口审计；B ASD 报告需求证据检索；C 新方法设计中。
- 已核查：旧 `v11.py::ContractGraphResidualPlanner` 仅接受 `event_workflow`，连续/模型走 `ConstrainedPlanRunner` 单工具路径；`EEGRecord`、Registry、Executor 与 Context 可复用。PR #23 的独立扩展实验仅为 Epoch 只读 consumer，强 Expert 与 CIEDG 7/7、37 次调用持平，不能推论跨任务泛化。
- 资源：原 EEGAgent 中已知 EDF 和 `seiz&normal.pth` 均存在；权重校验值与项目历史报告一致。不得纳入 Git/外部 LLM。
- 初步候选：① 对旧事件运行器加一层任务路由（不能形成共同机制，排除）；② 新版统一目标图内显式区分 record 与 Epoch 输入绑定，复用旧图执行/失效/证据逻辑，并保持旧版原样（选用）。
- 下一精确入口：补齐任务—能力—证据矩阵和方法不变量；实现共同目标图的记录绑定、通用 goal contract、逐目标预检与证据发布；先用合成无事件连续任务和事件多步任务检验，再运行本地模型与有界 LLM。
- Git/PR/CI：本分支尚未提交或发布；每阶段验证后更新。直连 GitHub 曾不可用，须先检查；禁止强推。
