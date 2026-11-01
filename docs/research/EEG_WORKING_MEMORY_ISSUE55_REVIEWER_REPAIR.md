# Issue55 同阶段主审反例纠偏与运行入口交付

日期：2026-11-01；起点 `f62965bdfa0446e786fd73b0f6f64fcd8fa958b3`，原研究分支，工作区起初干净。延续同一 Issue55 和既有授权，没有另开研究阶段。**当前整阶段验收仍不通过**：主审揭示的错误放行已修复，完整本地运行器已交付；原 T04 的无字面目标通道引用仍未安全解决，不能启动冻结自主确认或正式三臂收益实验。

## 事实纠正与首次复现

主审原请求：`记录A先查看stimulus事件信息并计算SYNTH-C1在2到4秒的RMS。`

错误动作：`create_epochs(labels=["stimulus"], tmin=2, tmax=4)`。用户没有给出事件相对窗口。兼容环境为已有 Python 3.10/eegagent；没有使用缺 NumPy 的系统 Python，也没有安装新环境。

首次复现直接运行 `TaskPlanEEGAgent.run → TaskPlanController → ScientificTaskStore.execute_action → ground_bound_scope → 原 ExecutionContext/Executor`，A/B/C/A-equivalent 全部实际执行了 1 次错误切段，返回 2 个有效试次、1 个越界试次，最终 completed。**不是仅函数提案被接受，而是真正进入了 EEG 计算。** 首次原始结果以独占新文件保存在 `artifacts/point1_task_memory/issue55/reviewer-first-reproduction.json`；公开证据记录原哈希和工具结果，没有覆盖旧结果。主审对 `1fb321d` 的隔离函数结果作为主审提供的历史证据，不冒充本次对该提交的全链复现。

因此撤回旧 `81be293/f62965b` 材料中“已测反例足以支持安全未退化”的广泛结论：当时未覆盖本反例。原文、111 项旧结果和首次失败全部保留，以下新结论优先。

## 架构归因、最小设计与实现

旧修改用“整句含事件 + 含通道 + 单窗口”代替窗口归属，混淆了对象身份、报告选择维度和时间源。事件名只是元信息对象，不能授权后续连续通道的窗口；反过来，事件窗口之后的报告通道也不能把它变为绝对时间。另一个问题是 legacy `_ground_scope` 在完整校验之前就写事实缓存，字段引用若被拒绝，候选来源仍可能残留。

本次选择在同一个绑定函数中建立**元数据对象组到字面范围的归属**：扫描实际记录中的通道/事件名及范围位置，新出现对象组接管后续范围，没有新对象的连续范围只延续最近对象组。多个同类对象可共享一个窗口；存在异类对象时，按照范围之前的对象组区分角色；同名同时属于两种角色时保守拒绝。保留完整父句、记录归属、时间域和原始来源，不信任截断引文。原 legacy 来源只是候选；当前轮范围字段统一经过归属核验，暂存缓存恢复后才提交最终事实。已有精确结果继承、单端点修订、fingerprint/版本/工件检查保持原职责。

这比“只检查数字是否在句中”严格，也没有建立第二套 Planner/Executor 或完整语言解析器。实现不含案例编号、stimulus、SYNTH-C1、特定窗口或任务关键词。它依然是有界字面绑定：不能完整理解否定、倒装和任意指代；复杂表达可能误拒，不能宣称自然语言安全完备。

字段引用的模型 `source_span/target_span` 现在只定位证据，不能凭“唯一前置候选 + 目标有同名通道”创造用户选择。当前保守实现要求目标完整父句明确包含所选通道名；来源/目标元数据、记录和独立窗口仍逐一核验。未确认提案不会写入 admitted_scopes；用户后续明确确认可续接原任务、在 B 真计算，A 零执行。

**代价和未解决点：** 原 T04 的“记录B的同名通道”是原协议要求支持的合法表达，但当前不能证明关系来源。现在仍为 partial/1 次计算，而不是把此误拒重新标为成功。显式确认续接是独立正例，不是替换原题。安全收紧不能证明字段引用问题已完全解决；这使 Issue 的机制准入仍为 `not_passed`。没有以某个指代关键词补丁恢复分数，也没有让用户承担本可本地完成的运行器开发。

## 同条件证据与三模块接缝

|检查|f62965b / 旧证据|本次结果|解释|
|---|---|---|---|
|主审错误事件窗，四臂|每臂 Executor 1 次，completed|每臂 0 次，来源未接纳|同原请求/错误提案；固定脚本继续强行 finish 会被拒绝并耗尽脚本，不冒充模型自主澄清|
|同句合法连续 RMS，四臂|未将旧行为臆测为实测|每臂 1 次，completed|合法窗口仍归连续对象|
|更换记录/通道/事件/窗口、交换语序|新增开发变体|错误事件动作 0，合法连续动作 1|不作为独立确认数据|
|T07 原请求与原动作，A/B/C|旧修复两轮 completed、4 次计算|仍两轮 completed、4 次计算|RMS、事件功率、原工件质量与精确历史读取保留|
|T04 原请求 + 原字段提案，A/B/C|曾 completed/2 次|partial/1 次|撤回模型提案自动升为选择授权的行为；合法省略仍未解决|
|用户明确确认目标通道，四臂|新增边界测试|原任务续接，B 1 次，A 0 次|不是原 T04 成功替代品|
|T03/T05/T06/T08|既有接缝能力|回归保留|独立分支、缺参续接、局部修订、条件不足、旧过程/工件读取|

24 条三臂受控回放，108/108 原采样数值/派生检查通过，较旧 111 少的 3 项正是 T04 的三个 B 结果，不隐藏为样本数变化。数值正确不等于原请求完整；所有脚本/Fake 结果都不是 LLM 自主成功率或候选相对收益。DAG 不补造用户来源；实际获准 scope 随 observation 进入原 TaskEntry，交付匹配和依赖读回继续共用这些证据。

新增/扩展 12 项科学专项测试含四臂子测：范围借用、事件/连续反向借窗、裁剪父句、换记录/换窗、源/目标缺通道、多候选、未确认提案零缓存污染、合法确认续接、同类对象共享范围、后续窗口不得复活更早对象。保留已有过期绑定/工件/版本/可选失败安全测试。

首次新全量回归发现“stimulus 和 control 同取一个窗口”的旧合法用法被拒，原失败保留于 `reviewer-full-regression-1.txt`；按同类对象组共享窗口修正，而非事件名特判。更早旧字段引用测试与新信任边界的两项冲突也保留于 `reviewer-repair-first-tests.txt`。最终全量 **681 项：666 通过、15 资源跳过、0 失败**；compileall、pip check、git diff --check 通过。

## 真实入口、逐轮证据和货币保护：已实现

新入口 `eeg_harness.research.working_memory_issue55_live` 复用原 OpenAICompatibleClient、Issue50 实际 wire 预约/不可变 final lease、JournaledBudgetClient、原 TaskPlanEEGAgent 和原科学工具。旧 preflight CLI 保留离线用途；旧 token-only 工厂现在不接受可调用 client，避免绕开金额保护。

运行器只将协议原自然轮次发送给 Agent，评分清单、答案、DAG、工具顺序不进入模型。新增开发清单是**仅评估器**原请求清单，保留 T04 两个结果要求；确认 C01/C02/C03 原题和标准未修改。每轮独占写入 `turn-N.json`：当轮完整结果、截止评分、真正接受的 final_answer、成本上界。后轮补齐不能修改前轮文件；所有 `whole_request_correct` 仍为 null，回答数值/单位/遗漏/科学条件/记忆真实使用必须结合原始消息人工复核。不能将自动工具评分说成完整自然语言回答验收。

原始请求/响应 journal、源文件及协议哈希、数据/事件/采样哈希、实际模型 ID、usage 和 session-end 均保存。已发生错误范围/数值的独立审查在下一 completion 前及当轮结束时停机；stage safety_stop 阻止新会话。缺窗补充只在实际 clarification_required、独立结果已保存且存在对应缺窗动作/等待节点时发送；仅一个澄清状态或无关问题不能触发预设回复。文字是否准确仍单独审查。

预算规则：

- 一个既有 Issue55 累计账本，整会话进程锁；次数 144、Token 6M、金额 US$3，开发 48/2M，确认 96/4M；不借池、不初始化正式全额账本、不重开关闭账本。
- 每次实际 wire 字节数 + 2200 输出为保守 token 预约；金额按核实输入/输出非缓存费率的较高者预约，normal 决策同时保护当前 final lease。自动重试 0。费用是上界核算，不冒充服务商账单。
- 有合法 usage 时按输入/输出分开结算；无 usage、网络异常、未完成调用维持完整预约。异常返回模型/非法 usage 写 safety_stop；历史重复交易、负费用、未知 phase 和不合法 token 记录拒绝继续。
- 支持在旧 Issue55 完整交易后追加 `issue55_reconciled` 审计行，不删旧头/旧交易；费率、授权链接、阶段归属及金额须核对。没有交易记录时不能仅写 reconciled=true 声称已核对消费。
- 真实端点 SHA-256、请求模型与允许的返回版本、费率来源须核实；仅既有授权 Flash 服务/已核实别名。test_only 授权不能到真实 client。只有与当前源码一致的机制通过证据才能付费；当前 gate 未通过，不能伪造。
- 确认需开发审查记录；第一次开始冻结实际 src/config/评分/数据/模型/费率，C01→C02→C03 按序且只一次，包括失败/中断；冻结后拒绝开发、改码或重跑。

10 项端到端 Fake 测试覆盖正常多轮、前轮缺项后轮补齐、原 T03/T07、网络异常、缺 usage、错误模型/usage、金额/次数/Token 限制、异常保守计费、最终回答快照不可改、重启沿用消费、冻结顺序/禁止重跑、错误计算停机、无关澄清不发补参。全部使用模拟费率、明确 TEST ONLY 授权和 TemporaryDirectory 临时账本；正式消费记录未动。公开证据另存 5 条完整 Fake 情形摘要及临时交易，原始输入/输出在忽略目录，不能解读为真实开销。

复现（先激活兼容环境；新输出路径不可已存在）：

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -p test_scientific_scope_issue55.py -v
python -m unittest discover -s tests -p test_issue55_live.py -v
python -m unittest discover -s tests -q
python -m compileall -q src tests
python -m pip check
python -m eeg_harness.research.working_memory_issue55_live --help
```

满足机制/配置/账本核对后才可使用的实际入口（这不是本次已运行的命令）：

```powershell
python -m eeg_harness.research.working_memory_issue55_live --real --ledger <既有Issue55账本> --attestation <本地核实记录.json> --phase development --case T07 --output <全新证据目录>
```

本地 attestation 包含 grant=原授权评论 URL、test_only=false、model、accepted_response_models、endpoint_sha256、input_usd_per_million、output_usd_per_million、rate_source、mechanism_gate（status/source_sha256/evidence_sha256）。这是核验记录，不是新的预算授权；当前不能填写通过。确认前在账本追加同源码、已审阅开发证据的 diagnostic_review；不能以未执行的测试或模型自评冒充通过。

## 尚未解决、外部条件和交付状态

2026-11-01 仅检查声明的服务变量存在性：进程/Windows 用户/机器级均无 EEG_HARNESS_LLM_BASE_URL/API_KEY/MODEL；工作区无 .env；项目 Issue55 目录无可核对累计消费的正式账本。未扫描私人目录找凭据，没有请求用户重复批准预算。**本次新增真实 completion=0、API tokens=0、费用=US$0；阶段历史累计未知，不推定为零。**

实际需用户补充的最小外部信息只有：把既有服务端点/模型/密钥配置到运行环境（密钥不要贴进仓库或讨论）；提供该端点对应输入/输出费率及返回模型版本依据；提供已有 Issue55 账本位置或可核对的分阶段次数/Token/费用记录。它们不替代机制前置条件：T04 安全字段引用仍是框架自身未解决问题，不要求用户通过改题替我们验收。

所有其他本地代码、Fake、回归与证据交付已推进完成。没有以缺配置留下运行器开发待办，也没有为了达标继续堆指代特判。确认候选未付费运行，Fake 使用测试身份的冻结流程不能算原确认案例；现有研究内容二、main、旧结果、旧消费记录均未改。PR #37 保持 Draft，Issue55 保持 open。最终 Git SHA 和远端 CI 记录见 PROJECT_STATUS 的发布补记。

公开材料：[纠偏证据](evidence/issue55_reviewer_repair.json)；历史材料：[原修复证据](evidence/issue55_scope_repair.json)、[原协议与结果](EEG_WORKING_MEMORY_ISSUE55_PROTOCOL_AND_RESULTS.md)。新公开证据给出首次复现、全部新受控/Fake 原始文件 SHA-256；受控动作和首次失败保留，未用成功结果覆盖失败。

发布补记：实现提交 `77fc69e1a2a6c1c8331580d004baa0a34293ed0b` 已普通推送；[CI #340](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/41272889170) success；[Issue55纠偏评论](https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6553367729)与PR37正文已同步。后续发布留痕提交仅文档，远端SHA见Git与发布评论。
