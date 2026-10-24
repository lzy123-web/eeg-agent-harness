# 多任务 Harness 方法研发状态（Issue #26 / #28）

## Issue #28 当前安全检查点（2026-10-24）

- 分支仍为 `research/multitask-harness-method-v2`、Draft PR #27；远端审查基点 `0f44df1` 与本地等价树 `c2c71ec` 的 SHA 不同，禁止强推。旧 v1.1/v2 运行路径及 Issue #16 历史实验未改。开始时命令行 GitHub fetch 不稳定，GitHub 仓库接口可读；提交/发布前需再核远端。
- 设计选用 Registry-backed 能力目录 + 参数化目标实例图，而非脚本路由或为每种组合写 HTN；理论边界和成熟先行机制见 `MULTITASK_METHOD_DESIGN.md`。新增 `v3.py`、`v3_agent.py`、`v3_application.py`、`v3_validation.py`，仍经 `SharedEvidenceGraphCore/ExecutionContext/Executor/ToolRegistry`。应用仅消费合成证据包，不生成诊断。
- 确定性 18 项新增模块测试（本地权重可用时全部运行）覆盖双窗数值 oracle、跨族同图、事件 scope 共享/隔离、模型门控、失效局部恢复、澄清恢复、共指/引文和证据序列化。最终 `compileall`、完整 **256 tests / OK / 14 skipped**、`pip check` 通过；本地权重门控 v3 **18/18 OK**。Fake 三案例：双窗、连续+事件、缺参→继续均完成。
- 真实 DeepSeek 仅合成数据四轮共 15 completion/32,066 tokens；首三轮错误和完整原始响应均留忽略的本地 `artifacts/`，末轮三案例完成。请求 `deepseek-chat`，末轮响应四次均报告 `deepseek-flash`。不是正式未见评价；后续代码整理只做 Fake/回归，不倒填新的真实成功。
- 已发现并修订：单引文混淆实例范围和概念证据；同一事件共指须完整 scope 等价；Tool Calling 仅允许单字符冗余末括号修复；新版直接继承共享图而不继承 v2 事件适配类；任务内稳定实例 ID、来源阶段与质量窗口原子预检。不足：开放语言目标完备性、复杂共指、可授权部分执行、跨数据版本分支及正式公平 Expert/Native 比较未完成。
- 本地功能提交 `190f4ef`（参数化目标实例、真实共享图执行、自然语言入口、证据包、合成应用、18 项测试）；本节研究文档为后续提交。远端安全合并/普通推送和 CI 尚需核验。
- 下一精确入口：最终运行 compileall/完整单测/本地权重门控；核查隐私与 `git diff`；更新状态里的实际提交/远端/CI，再在 PR #27 和 Issue #28 报告。勿重跑旧事件 benchmark 或进入 R3/ASD 真数据。

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

## 发布检查点

- 远端旧研究 base `bff894065b1647fc168f1c0ac4b226c16768e263` 与本地起点一致；新分支原先在远端不存在。普通 `git push -u` 成功，未强推，未改 main。
- 已建 [Draft PR #27](https://github.com/lzy123-web/eeg-agent-harness/pull/27)，base 为旧已审查研究分支，head 为本分支；当前四个本地提交 `343e4a7`、`b5cc2f7`、`6b660dd`、`38c502b` 均已推送。
- 提交前扫描新增差异，未发现密钥、私有资源绝对路径、真实 EEG/权重或生成产物。GitHub Actions `unit-tests` 运行 #157 对应 `38c502b` 已成功。
- 发布后补充的隐私边界：新版真实 LLM CLI 必须显式 `--demo-synthetic`，在 EDF 读取前拒绝其它输入；新增回归测试。仅限制 CLI，程序化调用方仍需自行遵守授权。此检查在 Draft PR 上作为后续非强推提交。
- 补充后本地 `compileall`、237 tests（13 skipped）通过；本地 EDF+权重门控新版 16/16。下一步提交/推送此补充并核实末轮 CI、Issue 评论及状态。
- 针对“共同状态机制”再加一个受控反例：新版图中间 Epoch 内容变化会同时撤销 producer 与下游质量证据，并恢复至 `create_epochs` 前沿，不只是 record 状态可失效。最后本地 `compileall`、238 tests（13 skipped）和本地资源门控 17/17 通过；待补充提交/CI。

## Issue #26 本轮交付检查点

- 最新功能/测试提交 `c76cbfd` 已普通推送至独立分支，[Draft PR #27](https://github.com/lzy123-web/eeg-agent-harness/pull/27) 保持 Draft 且可合并，但**未执行合并**；旧 base 与 main 无改写。
- GitHub Actions `unit-tests` #157、#159、最新功能提交的 [#161](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40083915694) 均成功。Issue #26 已评论实际路径、失败/限制并补充最终 CI 结果。此状态文档同步提交属于纯文档后续提交；不改变上述功能/实验结果。
- 本轮停止于 opt-in 多任务共同核心及其开发验证；下一精确入口是依 `MULTITASK_EVALUATION_PLAN.md` 冻结新的跨族未见实验与公平强 Expert，同步开展 ASD 报告需求的权威资料确认，不继续在本轮开发集上刷成功率。
