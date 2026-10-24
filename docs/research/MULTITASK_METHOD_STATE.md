# 多任务 Harness 方法研发状态（Issue #26）

- 分支：`research/multitask-harness-method-v2`，从已审查的 `research/point1-integrated-method-v0` `bff8940` 建立；远端基线 SHA 已经仓库接口核对一致。旧 CIEDG、Issue #16 gold/trace/results 不改。
- 纠偏检查点：已重新读取 Issue #26 正文与 [评论 6382639080](https://github.com/lzy123-web/eeg-agent-harness/issues/26#issuecomment-6382639080)。明确“保留/任务专有化/重构”清单见设计文档；本地初版虽然连续与事件走同一 `run/_reconcile`，但仍继承 event-only 类与 Epoch 默认结构，因此**尚未达到共同机制验收**。
- 当前阶段：A 任务族与机制缺口审计；B ASD 报告需求证据检索；C 新方法设计中。
- 已核查：旧 `v11.py::ContractGraphResidualPlanner` 仅接受 `event_workflow`，连续/模型走 `ConstrainedPlanRunner` 单工具路径；`EEGRecord`、Registry、Executor 与 Context 可复用。PR #23 的独立扩展实验仅为 Epoch 只读 consumer，强 Expert 与 CIEDG 7/7、37 次调用持平，不能推论跨任务泛化。
- 资源：原 EEGAgent 中已知 EDF 和 `seiz&normal.pth` 均存在；权重校验值与项目历史报告一致。不得纳入 Git/外部 LLM。
- 初步候选：① 对旧事件运行器加一层任务路由（不能形成共同机制，排除）；② 新版统一目标图内显式区分 record 与 Epoch 输入绑定，复用旧图执行/失效/证据逻辑，并保持旧版原样（选用）。
- 初版实测：13 项新增测试中 12 通过、1 项本地资源门控跳过；之前完整回归 233 项、13 跳过。Fake 合成连续与事件各 1 条完成。真实 DeepSeek `deepseek-chat` 合成请求 2 条共 3 completion、5015 tokens：连续 PSD 完成，事件质量+功率因旧意图语义校验误拒而澄清；原始响应与失败留在忽略的 `artifacts/`。这些不是多任务共同核心已充分验证的证据。
- 当前本地提交：`343e4a7`（矩阵/初步设计），`b5cc2f7`（初版跨族目标图）；均尚未推送。纠偏后不回滚正确初版，需实质重构事件默认核心并再测。
- 下一精确入口：将 v2 的任务图推进为任务中性的目标/输入/依赖/适用性/状态与证据引擎，把 Epoch 语义收敛到适配层；新增验证证明无事件任务在没有任何 Epoch 默认字段时可运行，模型适用性/资源与事件状态共用失败和证据边界。随后完成 ASD 映射和运行记录。
- Git/PR/CI：Draft PR 尚未创建；直连 GitHub 曾不可用，须先检查；禁止强推。

## 纠偏实施后的安全检查点（2026-10-24）

- `6b660dd` 已把共享 frontier/绑定校验/依赖失效/有界失败/证据发布迁到不默认 Epoch 的 `v2_graph.py::SharedEvidenceGraphCore`；`v2.py` 只保留记录、模型、源/有效 Epoch 的输入适配及授权筛选策略。编译/执行都核对 Registry 的输入输出类型及 Profile；旧 v1.1 不动。
- 完整回归 `compileall` 与 236 tests（13 skipped）通过，`pip check` 通过；本地合法 EDF+权重门控 15/15；Fake 合成连续与事件链 2/2；真实 DeepSeek 三次开发检查累计 10 completion / 18,365 tokens，最初两次事件请求因 LLM 幻增未获支持的 `epoch_summary` 安全澄清，第三次两任务完成。实际响应模型 `deepseek-flash` 仅在第三次有日志支持。不能把第三次覆盖成稳定成功率。
- 新增 `ASD_REPORT_REQUIREMENTS_AND_EVIDENCE.md`、`MULTITASK_METHOD_ITERATIONS.md`、`MULTITASK_METHOD_VALIDATION.md`、`MULTITASK_EVALUATION_PLAN.md`，均明确未验证部分；报告生成、ASD 诊断和正式比较尚未实现。
- 下一精确入口：检查所有新增文件的隐私与研究表述，提交本阶段文档；安全检查远端历史后将分支推送并建 Draft PR，再查 CI。若 Git 网络不可用，只能在核对远端 SHA 的条件下使用等价文件树发布，不强推、不改 main；最后记录实际 PR/CI、更新 Issue。
