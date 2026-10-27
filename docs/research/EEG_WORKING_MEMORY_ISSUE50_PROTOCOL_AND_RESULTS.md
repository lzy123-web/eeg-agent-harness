# Issue #50：执行职责调整与任务记忆诊断

## 研究问题与实施状态

本阶段检验控制架构的职责，而非再提出记忆算法。起点为`80271e7fe01afbab59cb57a3f680d9b35bb83ea8`，安全fetch确认远端一致、工作区干净。旧lifecycle、Issue49成绩与所有首次失败保留。新入口`memory_version=managed`接入原EEGAgent.run，数值仍经原Executor。

Issue49的B因事件来源包装连带阻断独立连续分析；A历史RMS实际存在，却因保守最终输入预约无法读回。旧真实请求还可能因未touch而被误拒。这些是本仓库已观察的控制问题，不能直接推断其他EEG Agent都有相同缺陷。

选择：模型提出科学目标、下一动作、真正澄清与解释；程序从实际行动维护来源、不可变结果、版本、工件身份和归档；科学约束逐动作及真实依赖检查；预算保护实际当前最终输入快照。主方法及取舍见[方法文档](EEG_WORKING_MEMORY_METHOD_AND_INTEGRATION.md)。

## 冻结前离线门槛

- compileall通过；完整回归536项，521通过、15资源门槛跳过；pip check无依赖冲突。Fake数据流不算真实自主成功。
- 真实Executor科学预检34个独立数值oracle通过，连续幅值V、功率V²、事件相对窗1.25秒；0.75秒仅负例。没有改变原算法。
- 三种层2历史都由真实工具产生3个任务、5个结果，科学内容hash相同。它们是受控前史，不冒充模型自主建立。
- 新适配器初版独立审查发现三个错误：C1旧窗/C2新窗来源可被拼成未授权组合；同工具成功误清其他对象待补项；错误猜值被永久登记为科学要求。现改为整范围来源绑定、按实际已确认对象清欠、技术提议错误与科学缺参分离。新增正反例保留这些首次失败的复现条件。
- 历史恢复真实行动观察进入下一Fake输入，并在同一原Epoch追加质量；错记录、跨对象范围、工件身份及未授权处理保留拒绝。

- 联网前补审另复现：逗号连接的连续范围被借给事件；分次读同结果覆盖早先字段、归档后丢已见功率。现按通用科学子句及实际对象校验范围，按本轮实际可见字段合并证据，失败读取不污染，未读字段不预取；保留离线复现，不将其算在线机制收益。

## 真实诊断协议（联网前固定）

完整机器协议：`config/point1_working_memory_issue50.json`；执行器：`research/working_memory_issue50.py`。不向Agent注入gold、正确子目标/任务ID或操作顺序。

1. 少量开发：新架构、完整历史，两轮自然混合请求，最多两次有明确根因的架构修订。相同架构故障先停止在线修离线；不逐句修改提示追分。
2. 层1：同一3轮请求旧lifecycle/full与新managed/full各一次，按old-full→managed-full。连续RMS及alpha可独立执行；事件窗口待真实补充；随后修订连续窗、比较旧新、追问旧RMS。第二轮只有模型实际报告相关事件窗待补才发送，不能由评测器代模型制造成功前提。开发与确认合成幅值不同，题型共享是开发诊断，不报未见泛化成绩。
3. 层2：仅新路径实际基本科学分析与回答可用后，managed/full→summary→working各一次。相同真实工具受控历史，追问旧RMS、沿原Epoch追加质量并比较两通道theta。直接可见即可使用，不强迫读/restore。分别记录精确读取与过程恢复。

模型设置一致：既有DeepSeek服务，`deepseek-chat`请求别名，实际响应标识另记；max_output_tokens=1800，max_retries=0，timeout=60秒；Agent每轮最多24轮/24工具动作。两层分别冻结代码、协议、设置；首次结果保留，不按确认结果调方法重跑。

预算是新只追加账本64 completion/400,000 tokens，所有失败/重试/最终回答都计入。以实际UTF-8 wire bytes＋最大输出保守预约；同时保护实际当前最终快照。过期快照只能标partial，不能把后续未出现的数值冒充交付。层1入场至少24次/200k、层2至少18次/90k是完整单元排程余量，不是每臂额度或任意会话完成保证。

评判以原请求完整性、实际数值/单位、记录/窗口/事件/版本、是否错误猜参或声称未测质量、是否合法复用原工件为准。模型completed和数值正确均不代替完整交付。失败分为语义选择、全局门控、生命周期管理、科学合同、数值执行、记忆信息、最终交付和资源中止。控制架构改善不等于记忆独立收益。

## 复现

在已配置Python环境及`PYTHONPATH=src`下：

```powershell
python -m compileall -q src tests
python -m unittest discover -s tests -q
python -m eeg_harness.research.working_memory_issue50 --preflight
python -m eeg_harness.working_memory_cli --help
```

真实诊断必须有本阶段授权及临时环境凭据；本地原始日志与账本位于被Git忽略的`artifacts/point1_task_memory/issue50/`，新run-id禁止覆盖。阶段结束不得继续消费余量。

```powershell
python -m eeg_harness.research.working_memory_issue50 --real --phase development --arm development --run-id issue50-dev1
```

## 结果

当前为实现与离线完成、真实诊断尚未运行的保存点。后续只追加真实结果、冻结提交、实际成本和失败边界，不把此预检当在线验收。

对照边界：本阶段强summary与working共享任务组织与领域档案，只检查同一可用架构内呈现/读取粒度；不冒称与完全无任务组织的普通通用摘要比较，不能单独证明领域适配的整体收益。
