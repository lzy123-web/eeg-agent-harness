# Issue #49：科学合同一致、请求交付闭环与有界真实验收

## 1. 范围与当前证据边界

继续 `research/point1-eeg-task-memory` / Draft PR #37。启动本地/远端均为`0b59cb6fe9732d9baf35680166a7fcd47c68ea26`，工作区干净，无需合并或覆盖。承接Issue48实现与失败，保持P1：**在有限工作上下文中正确继续并交付多轮EEG分析**。不研究工作点二，不另造Planner/Executor，不重做选题或改写旧实验。

本文件集中保存设计、冻结协议、预检、真实开发/确认和结果。当前为实现/离线准备；真实成绩只能在实际运行后填入。Issue48的37次/321,201 tokens及所有首次失败原样保留，不计入本阶段，不按新窗改写旧成绩。

## 2. 最小充分方案与继承取舍

只补“不要重算、记得回答”提示，无法保证begin/amend的科学范围一致，也不能区分同一有效结果和内容相似的另一工件。另建完整需求DSL或独立规划/裁判模型则增加范围与付费决策，并不能自动证明用户意图完整。选用现有科学子目标、真实档案和原循环上的三个共同机制：

1. **同一合同校验入口**：创建、补充未知项、技术纠正均检查允许字段/类型/变换边界/来源；已确认科学选择改变必须新版本。拒绝不部分修改合同或执行未经授权的变换。原工具schema支持某参数，不代表当前工作记忆模式已经授权它。
2. **请求—交付进度与有效结果复用**：模型用实际用户引文提出需求及覆盖关系，程序核对可表示的引用、对象和真实结果；等价计算依记录/参数/配置/版本/工件有效绑定复用，不因换标题或delivery key重算。明确重算、新范围、失效和新配置仍允许执行。原请求持续可见，模型清单不是离线gold，遗漏仍算未完成。
3. **完整交付的工作视图与资源收尾**：保留归档后完成反馈、必要精确值和未决项，原轨迹外存可恢复。必要时公共预算策略把工具集合收束到finish_task，让真实模型用已见证据回答完整、部分或澄清；程序不合成科学答案。

这三项适用于working、强summary和full。共同可靠性修复不能算候选独有优势。HiAgent继承是任务组织、当前工作视图、归档与按需恢复；本版实际是结构化进度＋最近原生批次＋必要精确证据，而非“全部当前行动观察直到完成都驻留”。需要足够完成反馈，但不机械重发完整已解决轨迹。

主要代价：科学来源/合同/覆盖字段增加接口及输入成本；来源逐字引用并非任意语言理解证明；保守完整输入预留可能让模型提前部分交付；已完成等价复用必须避免误挡用户合法重算。以上均须以反例及真实日志检查，不以新增测试数代替方法收益。

## 3. 确认协议（首次确认前冻结）

唯一配置为`config/point1_working_memory_issue49.json`。开发两轮使用既有合成记录，属于Issue48类请求开发回归；确认合成数据重新指定分段振幅/频率混合与事件位置，A旧新alpha从较弱到较强、B事件跨两个振幅段。部分自然句式沿用旧失败，它不是全新的未见语言泛化。真实模型只看到自然请求、已加载合成记录、公共工具/实际状态；评分列表、预检步骤、正确ID及oracle不进入模型。

固定顺序 **D→C→A→B**，四类共八次自然请求：

|会话|请求|必须核验|
|---|---|---|
|D（1轮）|B采样率/时长/通道|正常短任务的自然最终回答，无额外控制循环|
|C（2轮）|B/target/C2 theta，先不提供事件窗；相应真实澄清后预定补0～1.25秒|不猜窗先算；同目的补参；实际试次数、功率、相对范围和单位|
|A（3轮）|A/C1 0～2秒RMS/alpha；改4～6秒比较；问最初RMS且不重算|初轮结束、范围/版本保留、旧新比较方向与值、历史精确值复用|
|B（2轮）|B/C1连续1～3秒RMS/alpha＋target事件后0～1.25秒计数/C2theta；沿用原试次追加质量和C1/C2theta比较|全部需求、同一工件、已有功率合法复用、无基线/筛选、处理与经验质量规则说明有真实依据|

C补充消息只在实际`clarification_required`且相应B/target事件功率目的存在、窗口缺失或来源未确认，并且没有先成功执行相关事件数值动作时发送。固定答复不是驱动器自动补参。正确澄清/部分交付/资源停止与成功分别报告。B原工件恢复是重点证据，但若已可见证据足够，直接使用合法；不强迫无用restore动作。

一个或多个子目标均可。原工具计算全频带/通道合法，最后必须交付用户请求字段；计数可由create_epochs、epoch_summary或event_bandpower中的真实计数提供。数值容差连续rtol0.005（沿用原工具三位有效数字）、事件rtol1e−6、atol5e−13。有效试次数仅指边界有效，不自动等于质量合格。最终附加说明同样检查，不因请求关键数值正确而忽略不成立的科学限制。

科学与执行真值独立由原合成采样/实际工具条件决定。不能只看子目标valid或自己缩减后的需求清单。必须区分需求覆盖、合同/引用、数值、版本/复用、工作上下文、最终表达与预算/协议问题。每类确认只运行一次；锁定后不改窗/提示/真值/预算重跑挑分。

## 4. 科学预检与最终输入预检

`working_memory_issue49.py::scientific_preflight`在实际Registry/Executor上执行确认所需的记录信息、连续两个窗、1.25秒事件Epoch、计数、功率与同工件质量，独立原采样28字段复算。0.75秒作为**明确应拒绝负例**保留。工具最低1秒来自实际registry前提，未修改原数值算法来迎合协议。质量使用实际经验规则，不编造用户或临床阈值。

`budget_preflight`构造实际Controller视图，检查初始请求、短任务结果后完整最终输入、多结果归档、新旧比较、精确历史读取，以及原过程恢复后在同一工件追加quality再回答的完整输入。是受控的真实工具预检，不算模型自主成功；预检合同与正确引用不进入真实Agent。

首次测量中D首次预约23,644、结果后的final预约12,609；B恢复质量后final预约38,273。预留均含完整messages、真实工具schema、wire封装及最大输出1600，绝非只留输出。联网前复核D为23,644/12,667，B恢复质量后final为38,390，实际记录在本机preflight-paid-gate.json。协议固定未开始会话的入场＋settled-final最低floor：D38,000、C44,000、A40,000、B50,000（测量向上取整＋小余量）。它们不是单例token硬上限，也不是整个复杂流程费用保证；正式运行只检查测量仍在固定floor内，不按成绩重新分配。已开始会话释放其未来floor，后续未开始会话仍受保护。

下一次正常决策前，客户端检查“当前完整请求预约＋下一完整最终请求上界＋未开始会话floor”。最终消息按与真实wire一致的默认JSON空格序列化受96,000字节硬界约束，另加实际finish schema/wrapper与1600最大输出；不使用未经证实的字节/token平均系数。不够再扩展但当前实际final输入仍可预约时，切到仅finish_task，由真实模型回答已有证据及缺项；仍可能只部分交付，绝不改成自动科学答案。消息/工具状态膨胀等异常仍会明确停止，预检不保证任意模型轨迹必然完成。

## 5. 独立账本、冻结与原始记录

用户明确授权新独立上限：全阶段80 completion/500,000输入＋输出API tokens；开发池24/150,000，确认池56/350,000。D/C/A/B共用确认池，不再设单例token分箱。任一先到停止，所有实际出站尝试含失败、必要重试、恢复与回答累计。默认零重试，旧Issue48或更早余额不使用。

只追加账本`artifacts/point1_task_memory/issue49/budget.jsonl`同时核验全局/池，实际wire UTF-8字节作为保守输入上界＋最大输出在出站前预约，API usage真实结算；失败/无usage/未结请求保留预约。正式real_case跨进程只允许一个live session保护后续final空间；异常遗留锁需检查，不能自动重跑重置。固定候选、协议hash、future floors写入确认冻结事件，D/C/A/B一次顺序持久化；确认前要求工作区干净。

每个run保存protocol、manifest、preflight、实际messages/tools/模型设置/response、每轮状态/结果/答案、reserve决策与账本。日志只含合成必要元信息和结果，不记录密钥或私人配置路径。字节分项解释结构，不能伪装成API分项tokens。账本无真实服务账单时，只报告实际usage/调用/缓存/延迟，不编造实扣货币金额。

## 6. 复现入口与结果追加位置

离线，无API：

```powershell
$env:PYTHONPATH='src'
python -m eeg_harness.research.working_memory_issue49 --preflight --output artifacts/point1_task_memory/issue49/new-preflight.json
python -m unittest discover -s tests -p test_working_memory_issue49.py -v
python -m compileall -q src tests
python -m unittest discover -s tests -q
```

本阶段经用户授权、离线门槛/提交完成后，既有环境变量提供服务配置，主执行者按序运行；所有目录必须新建，不覆盖原结果：

```powershell
python -m eeg_harness.research.working_memory_issue49 --real --case development --run-id development-initial
# 最多两次有根因开发修订；确认前冻结clean commit。
python -m eeg_harness.research.working_memory_issue49 --real --case D --run-id confirmation-D
# 之后依次C、A、B；不能重复确认或更改candidate/protocol。
python -m eeg_harness.research.working_memory_issue49_audit --output artifacts/point1_task_memory/issue49/new-readonly-audit.json
```

统一Agent仍是`WorkingMemoryEEGAgent(..., memory_version="lifecycle", request_closure=True, context_mode="working"|"summary"|"full")`的run/continue_run。三模式公共修复与权限相同，本阶段不自动新增真实多臂排行榜。阶段结束后余量不得自动转为新实验。

以下由主执行在实际运行后追加：初版/修订与冻结Commit；完整离线门槛；真实D/C/A/B最终原文与评分；首次失败；restore→实际输入→同工件续算链；全部成本与公开合成JSON；未验证边界与唯一后续重点。当前预检通过不能替代这些结果。

## 7. 初版离线门槛

- 全量488项：473通过、15资源跳过、0失败；compileall、pip check通过。35项本阶段测试包括真实Store13、Agent集成11、协议/预算11，旧模式和原Agent回归保留。
- 独立审查实际发现并修复：原工件约束未覆盖自动绑定/已完成快速复用；改变修订父节点可重复消费一次重算授权；助手自由文本伪造结果JSON能冒充实际可见证据。统一修复后保留合法原工件续算、明确重建、新用户轮重算、strong summary/full真证据正例。
- 实际工具科学预检28项独立数值检查通过，七种实际最终视图预算预检通过；尚无本阶段外部调用。预检是受控机制证据，不是自主Agent成功。
