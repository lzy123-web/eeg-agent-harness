# 项目状态

## Issue #52：共享强P&E与候选差异已实现，离线阶段交付；自主收益尚未验证

- 安全起点本地与远端`3d99b4c7644119a4ed5b4e6f1dbf82695da37165`，工作区干净、无分叉；继续原研究分支和Draft PR #37。完整读取Issue52及旧失败，当前新外部授权为**0 completion/0 tokens**，不重开任何旧账本。
- 设计`71e81ee`：A强P&E、B一般任务记忆、C科学验收/依赖分层共享真实结果传递、稳定任务/版本、范围/工件安全、合法重规划、全部读取权。所有组正常结果自动绑定；C不独占科学信息。A可调用相同check_deliveries，A-equivalent得到同一自动科学门控时交付差异应消失。
- 新路径`TaskPlanEEGAgent`仍直接继承原`EEGAgent.run`，数值只经原Store→ExecutionContext→Executor；无新数值工具。共享DAG有显式交付key、输入引用和固定历史revision，稳定任务身份与实际执行episode分离。工作记忆在下一决策前提供活动AO、实际依赖结果或过程，完整档案保留。
- 有依据修订：工具成功先置TOOL_SUCCEEDED，科学条件满足后才解锁有条件依赖；共享旧binding失效检查避免候选独享安全；修订引用能固定旧版，未改输出真实复用，新值保留revision_of；过程读取回执与上下文去重。所有修订是离线，不包装成真实模型改进。
- 冻结代码与协议`9e5347c63d3fc3ca9add42ea8be68b0abd9b59db`，核心实现`ff0cbc211213bedd3a3d0912bff160efa98473dc`；配置SHA-256为`25210fc64450adf29749e23d8c5ef2edc954d41a72c26e82831c4c4b7c562ddf`。随后仅保存证据、文档和发布状态，没有按结果继续改方法。原有模式、数值算法和历史实验不改。
- 最终**652项完整回归：637通过/15资源跳过**，compileall、pip check通过。八类×A/B/C共24条受控路径，**93/93独立数值/计数核验通过**。正常连续、双窗口、混合补参、版本修订及原工件续算三组均能完成；这不是24条自然会话全部成功。T04的跨记录同名通道省略、T07的同句连续/事件范围被共享来源绑定保守误拒，只部分交付；不为追分改请求或扩词。T05真实来源片段由离线脚本定位，不能称模型自行纠错。
- 科学验收差异：同一个人为错误的“3试次满足至少4个”完成提议下，C拒绝，A/B可接受错误声明；A-equivalent获得同一自动校验后也拒绝。正常T06三组都读取真实事实并安全停止，不宣称候选独占科学正确性。T08受控过程供给C为7次决策，A/B为8次，均3次数值执行；消融去掉选择后恢复8次。只是指定依赖的控制开销，不是实际API收益或自然模型错误率。
- 冻结后额外6条消融/敏感性回放（T06/T08×C-no-delivery/C-no-selection/A-equivalent）21/21独立数值检查通过，和主表分开保存。三组共享结果自动关联、科学底线、版本绑定及读权，未删除旧测试或刻意缩小上下文。
- **新增外部completion=0、API tokens=0、外部模型费用=0**；没有读取凭据或创建可消费账本。完整输入预检T03三臂保守预约见证589194、T05为654807（wire bytes＋最大输出的保守单位，不是实耗tokens）；未来最小三臂T03建议申请48次/900000 API tokens，仍须新授权。该见证不是任意自主路径上界，也不把已用开发请求改称未见确认。
- 研究判断为**B：可支撑开题方案和实现基础，尚不足以支撑已经成立的独立创新结论**。方法差异限于科学条件自动验收、依赖需要驱动的分层证据供给；稳定身份/版本/科学安全是公共基础。A-equivalent表明校验差别可由成熟P&E配置消除；约千行新增控制/数据模型及相应维护成本需由真实完整配对效用证明，不凭测试数宣称贡献。
- 交付：[设计及代码映射](EEG_WORKING_MEMORY_ISSUE52_DESIGN.md)、[冻结协议、逐例结果、复现与预算](EEG_WORKING_MEMORY_ISSUE52_PROTOCOL.md)、[开题一页总结](EEG_WORKING_MEMORY_ISSUE52_PROPOSAL_SUMMARY.md)、[公开合成证据与首次失败](evidence/issue52_offline_paired_diagnostic.json)。README、主方法和开题包同步；全messages/tools本地忽略保存，公开摘录含真实结果、失败、版本、访问关联及原文件hash，不含真实EEG/密钥/个人路径。
- 复现：`PYTHONPATH=src python -m compileall -q src tests`；`python -m unittest discover -s tests -q`；`python -m eeg_harness.research.working_memory_issue52 --offline --case T01 --case T02 --case T03 --case T04 --case T05 --case T06 --case T07 --case T08 --output <新的本地JSON文件>`；`--preflight`同样须新输出路径。`--real`在本阶段驱动中拒绝；正式Agent/CLI新`--plan-arm`入口只收自然请求，付费运行须另有明确授权。
- 下一唯一优先：获新授权后，按冻结协议做一个完整三臂自然会话单位，分开判断规划、验收、依赖证据使用、最终科学交付和总成本；先诊断共同接口误拒，不继续堆功能。若合理强P&E同样可靠且更简单，则采用简单方案并收缩独立增益主张。本阶段至此停止，不开展工作点二。

## Issue #51：有界研发与冻结确认已结束；完整自主闭环未通过

**最终结论**：新scientific模式已接原Agent/Executor，科学对象绑定、多结果需求、活动AO、精确量纲/比较、读回/过程恢复实现并离线验证。真实DeepSeek自主多结果声明、连续/事件执行、旧结果进入比较已有证据；冻结确认第二轮因辅助失败误作科学完成义务而no_progress，未进入第三轮。完整归档与自主过程恢复、相对强摘要收益均未验证；停止在线，不修分重跑。

- 冻结`eceb2b2f18354660708ccd0234052f9a9d43edec`；协议SHA256`60c3888f475863a36115f7f56a041ce6296b5620712c57b51865e950eb43900a`。唯一开发修订`2262943`；早期架构`75fc2cd`、协议`4b0e675`。
- 全量离线617项：**602通过/15资源跳过**，compileall/pip check通过。46项独立科学预检；三次真实run共39项数值oracle通过，但不替代最终完整交付。
- 实际费用：**16 completion/187,303 API tokens**（179,878输入+7,425输出），全部返回deepseek-flash，请求deepseek-chat；0HTTP失败/0自动重试/0未结预约。账本已追加关闭，56次/462,697余量不转用；货币账单未核实。
- 确认第一轮partial正确；第二轮3项科学结果全满足，alpha差`6.6e−11 V²`/比`3.0625`、事件C2theta`4.452099644531906e−11 V²`正确。辅助list_events误拒留pending→三次正确主要内容的finish提案被拒→no_progress。旧s1未因新标题s2完成而正确续接；不是所有科学计算失败，也不能算完整会话成功。
- 真实read_result/restore_task均0；第三轮原工件质量未发。历史旧PSD真实用作比较操作数，不能冒充过程恢复；相关恢复续算仅离线/Fake通过。第二层三臂因科学准入未过而未运行，**不是本阶段预算不足**。
- 当前判断：保留HiAgent启发的EEG任务工作记忆候选，收缩完整可靠与相对收益主张。下一阶段唯一优先是科学义务/辅助尝试分离与自然续接的稳定目的身份；本次不开发第二工作点、不改冻结结果。
- 交付：[集中报告](EEG_WORKING_MEMORY_ISSUE51_PROTOCOL_AND_RESULTS.md)、[主方法与最终职责](EEG_WORKING_MEMORY_METHOD_AND_INTEGRATION.md)、[公开原始合成证据/失败/成本](evidence/issue51_scientific_memory_diagnostic.json)，开题包B.6和README同步。复现命令见集中报告。
- Git发布已完成：核心`75fc2cd`、协议`4b0e675`、唯一开发修订`2262943`、冻结`eceb2b2`、证据/开题事实`365cb5766fc58e7c671d3590f8732bfb6429bcb3`均已普通推送。早先TLS握手/直连超时后恢复，安全fetch确认无分叉；未关闭证书验证、未强推、未改main。[交付CI unit-tests #307](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40466989203)已success。
- [Issue #51阶段结果](https://github.com/lzy123-web/eeg-agent-harness/issues/51#issuecomment-6436209583)、[PR #37阶段评论](https://github.com/lzy123-web/eeg-agent-harness/pull/37#issuecomment-6436222531)已发布，PR正文新增本阶段并保留旧历史，核实仍Draft/open/unmerged。当前记录只同步发布及CI，不修改冻结候选或增加模型调用；Issue保持open供审查。

以下为本阶段按时间保留的研发过程，最终状态以上述结论为准。

- 安全起点：本地与远端 `d64474bd444b95b9b4167d66e58f940b50cfffa0`，工作区干净、0 ahead/behind；继续 `research/point1-eeg-task-memory` 和 Draft PR #37。原模式与历史实验保留。
- 已在原 Executor 的真实合成数值路径复现两个问题：裁剪 B 请求片段可错误执行 A 的范围；`expected_tools=[psd,psd]` 去重导致一次 PSD 后过早归档。
- 新 opt-in `scientific`：完整请求对象绑定、按记录/范围区分的结果实例完成、活动行动观察到归档/读回/恢复的一体接口；确定性差值/比值只读真实有语义契约字段。模型选择目的与动作；程序维护科学事实；不声称证明任意原请求全部意图。
- 本阶段独立上限 72 completion /650,000 API 输入输出 tokens，当时尚未调用。先实现、真实工具离线回归和完整会话预算预检；开发最多两次有根因修订，冻结确认不调真值。失败与未触发机制如实留存。
- 核心实现已接原run/continue/CLI，已提交并普通推送`75fc2cd`。新机制44项离线真工具/Fake回归、46项独立数值预检通过；完整回归 **607项，592通过/15资源跳过**，compileall及pip check通过。完整真实三轮资源见证通过科学动作链；去掉控制回复重复账本后full-native保守预约497,715（不等于实际API tokens），确认500,000池可承受此合法路径。当时真实验收尚未运行。
- 资源预检已保存本地初稿及最终版：开发只首轮76,056；完整确认497,715，实际compact最终快照备用路径407,724。精简同历史单个完整任务的三臂见证分别79,644/73,411/72,303；只有确认结束并科学审核、实际剩余≥300,000 tokens/18调用才可整组启动。全阶段总上限不因阶段上限求和而增大。
- 明确保留限制：有界字面对象绑定不是任意语义证明；显式错误要求不会被后续别的合法结果偷偷删除；科学结果集完成不证明整个原请求完整。旧阶段失败仍不改写。
- dev-initial实际3次/25,544tokens：模型科学分组意图基本正确但scope混入输出选择，被公共合同拒绝；原数值路径7项核验通过，最终功率µV²换算错1000倍。修订1将工具派生计算schema与纯文字输出选择分离，逐项科学错误反馈；活动观察附真实数值单位/缩放，恢复过程单一上下文所有权，原失败保留。修改后主路径490,433保守预约适合500,000确认池；待回归后再开发。
- 修订1`2262943`的dev-revision1：3次/27,083tokens，模型主动声明5个结果实例成功接纳，3连续结果正确、2事件依赖待补，目标保持suspended。一次INVALID_SOURCE_SPAN自行纠正；缩放值准确。累计6次/52,627，未调用其他服务。完整回归617项（602通过/15跳过）、compileall通过；冻结后全三轮确认一次，不按确认成绩调要求。

## Issue #50：职责重划已交付；完整科学回答及记忆独立收益仍未通过/验证

- 安全fetch起点本地/远端均`80271e7fe01afbab59cb57a3f680d9b35bb83ea8`，工作区干净；沿用研究分支与Draft PR #37，保留所有旧模式/历史失败。不改main、不改原算法/Executor。
- 初版`d481c8e80d0b2da42b0fb0d49f4a23606bbedb07`：opt-in `managed`由模型选择科学任务/动作，程序自动维护真实来源、范围、版本、工件和归档；任务不作全局门控。原Agent run/continue/CLI接入，活动AO、任务摘要、精确读取/过程恢复、本轮已见字段union、实际最终快照预约均已实现。取消新入口重复coverage和每字段来源登记；仍为有界字面科学校验，不声称任意语言语义证明。
- 初版离线536项（521通过/15资源跳过）、34真工具独立oracle。独立审查修跨对象来源拼接、错误提议变永久要求、错对象待补清除、逗号科学范围借用、分次读字段覆盖与归档后已见数值丢失。不是论文新算法。
- dev1真实5次/44,658tokens：连续RMS/PSD+正确事件待补；次轮当前请求在旧native finish之前，三次重复旧答no_progress。首次原始输入/输出保留，立即停止在线定位。
- 唯一开发修订`0867b59d827ff3475bb5b5034bb0d2edb0f6c605`：按真实轮次排列历史/新user/当前AO，且唯一同记录历史对象来源不依赖pending/touch；新范围仍须当前支持。离线539项（524通过/15资源跳过）及34oracle通过。dev2真实7次/71,030tokens，完成事件补窗3Epoch/C2theta、连续alpha修订及正确比较；两次可选request_span技术误拒后自行修正，未抹除失败。没有第二次开发架构修订。
- 层1冻结候选`0867b59`，协议SHA-256`0116e5aa470f51f1648d6368bff4c6acc53e0f886a52efd4305bd5269f68e055`。旧/full与新/full相同自然请求、数据、工具、模型和资源策略，各一次。确认期间无改代码/提示/窗口/真值，无复跑挑分。
- 旧/full：6次/76,585tokens，仅事件元信息，合法连续结果被全目标门控阻断；次轮时序no_progress，未到第三轮；附加alpha边界写错。新/full：8次/116,822tokens，真实连续/事件/参数修订及第三轮原RMS读取都完成；**第二轮回答功率增量应6.60e−11却写2.06e−10 V²，并无依据将窗口重叠解释成事件成分混入，故整会话不能判无保留正确**。首轮将事件数称试次数也需区分。新方案成本更高且工作量不同，不宣称降成本。
- 实际记忆使用：旧t1 RMS读回→第8个真实模型输入→准确最终值/来源/范围/单位；原Epoch ID用于event_bandpower；新PSD明确revision_of旧PSD。真实focus_task=0、restore_task=0，只有自动单步组织；多结果任务与恢复原工件新增质量有离线真工具/Fake证据，不冒称真实自主触发或压缩收益。
- 层2三个上下文模式的同历史接口/34oracle/受控历史已离线验证，但**未联网**。余90,905tokens不足保守保障三臂两需求完整配对；full首次normal+final lease约84,725，三臂仅首normal预约合计121,944。90k原入场余量不是完成保证，未只跑候选或截断summary。该预算准备局限如实记录；不以经验比例放松上限。
- 全阶段独立账本已追加关闭：**26 completion /309,095 API tokens**，输入298,783、输出10,312，缓存命中150,656/未命中148,127；全部响应deepseek-flash（请求deepseek-chat）；0HTTP失败/0自动网络重试/0未结预约，API记录耗时合计74.5544秒。货币账单未核实。保留余量但不继续消耗、不叠加旧预算。
- 只读审计54个新执行数值字段及1个历史读回字段通过，元信息按实际字段另核验。所有数值正确不代替最终回答正确。真实四run、失败、源/版本/工件、原文及成本在[公开合成证据](evidence/issue50_architecture_diagnostic.json)；全messages/tools/responses/账本保留本地忽略目录。没有真实EEG、个人路径、密钥或权重入库/出站。
- 复现：`PYTHONPATH=src python -m compileall -q src tests`；`python -m unittest discover -s tests -q`；`python -m eeg_harness.research.working_memory_issue50 --preflight`；已有本机日志时`python -m eeg_harness.research.working_memory_issue50_audit --output <新输出文件>`。539项全回归、compileall、pip check通过；资源跳过仍为跳过。
- 交付：[集中协议/结果/失败/成本](EEG_WORKING_MEMORY_ISSUE50_PROTOCOL_AND_RESULTS.md)、主方法文档的责任/继承/适配/代价/代码图、统一managed入口、README及开题事实增补。旧研究结论不覆写。
- 远端验证：冻结候选`0867b59`的[GitHub Actions unit-tests #299](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40452486880)已success；再次fetch确认本地/远端无分叉，PR仍Draft/open/unmerged，Issue无新增纠偏评论。
- 研究判断：保留公共科学事实与职责分离，短任务不强迫分层/恢复；任务压缩可选。控制架构可运行得到证据，任务记忆相对强摘要的实际独立收益尚未得到本阶段证据，不能宣布工作点一完全验收。
- 下一阶段唯一优先目标：保障实际结果之间的派生比较及科学解释边界，再以完整配对单元检验上下文方案。先离线、不得新造回答验证Agent或把修复包装算法；未来真实实验须另行明确授权。本阶段停止，不自动开展工作点二或新方向。
- Git：初版及修订均已普通推送；本轮最终证据/研究状态另作提交并普通推送，准确发布信息附后。PR保持Draft，不合并main、不强推。

- 发布留痕：证据/研究材料提交`b9796b37b9624742974c6c05cba325b5bc682748`已普通推送；首次遇到临时TLS握手错误，普通重试成功，没有force或改写历史。[Issue #50实际结果](https://github.com/lzy123-web/eeg-agent-harness/issues/50#issuecomment-6434402234)、[PR #37阶段评论](https://github.com/lzy123-web/eeg-agent-harness/pull/37#issuecomment-6434402602)已发布；PR正文新增本阶段并保留旧历史，仍Draft/open/unmerged。Issue保持open供研究审查。本条仅同步发布状态，不新增调用、不改冻结候选或确认成绩。

## Issue #49：阶段已交付，完整自主验收仍未通过

- 安全fetch起点本地/远端均`0b59cb6fe9732d9baf35680166a7fcd47c68ea26`，工作区干净，承接原研究分支及Draft PR #37；不改main、不改写旧历史。保留Issue48全部失败与协议。
- 初版`92e3b4381d46a40bff96469e149dbda8bda0f70c`统一begin/amend/数值执行的科学合同，封住baseline补参绕过；新增真实binding等价复用与有来源的重算，原工件身份贯穿执行/自动绑定/完成复用。RequestProgress将原请求、模型引文要求、实际结果与未决项关联；可见证据核验和自动核验归档走原Agent。三模式公共能力，非独立Planner/新记忆算法。
- 独立审查修复原工件替换、修订父节点重复消费重算授权、助手自由文本伪造可见证据；保留合法重建/恢复及strong summary/full直接历史回答正例。没有删旧测试或降低科学要求。
- 联网前488项（473通过/15资源跳过），科学预检28字段复算通过，旧0.75秒功率窗仅负例；七种实际最终输入预算视图通过。独立账本80/500k、开发24/150k、确认共享56/350k；未来D38k/C44k/A40k/B50k为固定最低入场/收尾预留，不是每例硬额度。
- 真实开发7次/37,289tokens：首轮正确完成，次轮保守最终输入预留提前收尾，模型引用未读旧定位项而被拒三次。唯一开发修订`0599d1ca5aea0d4103fb99532d7e55bb827a5b3a`改善真实可见/未读反馈及合法partial路径，保存点不再误示原需求完成；不降低证据真值或用经验比例缩小预算预留。无开发付费复跑。
- 冻结候选`0599d1c`、协议SHA-256`b4a9593c2edbdda7eaca2a4768d2901bb84b7178368c3c605ee8d93b0ad8e596`，确认D→C→A→B各一次，期间不改代码/协议/真值。确认后仅补文档与只读审计摘录，不改算法或旧成绩。
- 四类实际结果：**D完整**（2次/13,564tokens）；**C核心数值完成但科学表述有误**（10/99,427）：同目的澄清补参、3试次及theta3.0917358155695594e−11 V²正确，附加pV²换算错误/未测质量却笼统说无阈值；**A前两轮完整、全会话未完成**（9/67,576）：5.15e−6 V RMS，alpha2.45e−11→8.45e−11 V²及增加正确、旧PSD复用，历史RMS因预算未读回；有旧来源关联但新t3.revision_of为空；**B未完成**（9/71,426）：theta标签来源登记问题使整goal阻断独立连续输出；无原Epoch/质量/比较，末轮旧原文相关性检查误拒安全partial而no_progress。
- 真实本阶段restore为0，未验证恢复→实际输入→原工件新增测量；离线正例不能替代。C曾提议猜测窗但未执行；A资源停线的clarification_required不是必要科学澄清；B未建立原Epoch，后续不存在恢复前提。不能把所有问题混算成记忆检索失败。
- 最终离线490项（475通过/15跳过）、compileall及pip check通过；冻结候选[GitHub Actions unit-tests #291](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40378015288)成功。只读审计30个已产生数值字段全部通过（开发6/A11/C13），D/B元信息另按真实字段核验。44个动作、14失败全部保留，12次数值/元信息真正执行；数值正确不代表完整原请求或自然语言附加结论正确。
- 全阶段 **37 completion / 289,282 API tokens**：输入272,563、输出16,719，缓存159,744/112,819；开发7/37,289，确认30/251,993。全部响应标识deepseek-flash，请求别名deepseek-chat；0HTTP失败、0自动重试、0未结预约。API记录耗时合计92.602秒；无服务账单金额，不编造货币实扣。5次提前仅回答，0出站前硬预约拒绝，阶段与分池未超授权；现停止联网，不续用余量。
- 交付：[集中协议与结果](EEG_WORKING_MEMORY_ISSUE49_PROTOCOL_AND_RESULTS.md)、[公开合成证据](evidence/issue49_request_closure_confirmation.json)、更新方法文档/README/开题材料事实。原始messages/tools/responses/预算留本机忽略目录；公开摘录含全部失败反馈、原请求/最终答案及四个关键真实输入字段，不冒称全部原始上下文公开。
- 尚未解决：单一事件来源登记问题连带阻断独立合法输出；旧pending请求的真实引文被相关性规则误拒；最坏最终输入预留过保守；显式revision边不必然登记；最终附加科学措辞/换算仍可错；真实恢复后的续算未验证。强S/full入口可用且共用修复，但没有新的付费多臂比较，不宣称工作模式优于S。
- 下一阶段唯一优先目标：把来源登记技术修正、独立交付、旧请求欠账与资源停线统一成可执行的公共恢复路径；先复现B/A实际失败，不加关键词、不新造Planner，不用继续付费试跑代替定义。需要更紧预算时必须证明动作/视图上界。
- 实现及唯一开发修订已普通推送；本次证据/文档完成验证后提交并推送。PR保持Draft，不合并main；阶段已停止，待用户审查，不自动开展下阶段。

- 发布留痕：证据/文档提交`1e7102fc230335903e7a91f05600f71b5be0478d`已普通推送；[Issue #49阶段结果](https://github.com/lzy123-web/eeg-agent-harness/issues/49#issuecomment-6424408157)和[PR #37阶段评论](https://github.com/lzy123-web/eeg-agent-harness/pull/37#issuecomment-6424408690)已发布，PR正文新增本轮并保留旧历史，仍Draft/open/unmerged。Issue保持打开，未将未通过的完整验收误关闭。

## Issue #48：阶段交付结束，完整自主会话验收未通过

- 起点安全fetch/快进到`7259345ed23bb21fd39744f69b67132f0270a2d7`，沿用`research/point1-eeg-task-memory`及Draft PR #37。保持P1“有限上下文中正确继续多轮EEG分析”，不启动P2或新Planner/Executor。
- 初版`ef10142`实现opt-in `memory_version=lifecycle`：科学来源/实际字段合同、待补要求与同目标amend、不可暗改阈值/已确认范围、幂等历史绑定、原Agent串行批次/call_id补齐/逐目标归属、完整档案与当前证据视图、强summary/full共同入口。旧single/multi及历史结果保留。
- 开发9calls/95,862 tokens，五交付首轮数值完整但附加科学表述有误，续接未完成。修订1`0dfa882`规范化等价字段来源、去重原生批次及归档索引；修订2`8f0193f`事务性阻止撤销已确认来源后同goal改科学范围。两次修订到此结束。
- 最终候选`8f0193f1b5f81a3b064bffcae45c3292abfa19a0`；确认协议SHA-256 `e45261c125c1206d356bb4840dfb275896c5b695db456f80216064d292616a3d`。冻结后未修改候选/提示/请求/真值，D→C→A→B全部按同一锁定点运行，未补跑挑分。
- 离线453项：438通过、15资源跳过、0失败，compileall通过；覆盖真实工具来源/类型/缺参、表达纠正保留结果、旧新范围/单位、批次中止配对、共享接口、精确读回/原工件恢复续算和不可撤销确认。Fake仅为机制回归，非模型自主成功。
- 完成确认后全量回归仍453项/438通过/15跳过；`pip check`无依赖冲突。冻结候选`8f0193f`的[GitHub Actions unit-tests #283](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40361466088)成功。公开合成JSON的45字段、五次预算拦截、全部manifest/费用与本机审计一致，敏感路径/密钥检查通过。
- 真实确认28calls/225,339tokens：D元信息正确但回答前会话预约停止；C阻止猜窗、实际澄清并同目标补参，Epoch正确，功率未完成；A同一目的重建3次、RMS/PSD各重算3遍后预算停，未执行自然修订/历史追问；B首轮部分交付＋正确短窗澄清，次轮restore真实进入下次模型输入，但无质量/原工件数值续算成功。
- 必须披露的协议疏漏：C/B的0.75秒窗不符合现有event_bandpower≥1秒前提。工具正确拒绝，不能作为合法功率任务上的记忆失败成绩；冻结后未偷偷改1秒。45项已产生字段独立oracle全过（开发19、确认26），不代表四类任务成功。
- 全阶段独立账本 **37 completion / 321,201 API tokens**：输入309,891、输出11,310、缓存命中168,448/未命中141,443；均返回deepseek-flash，请求别名deepseek-chat。零HTTP失败/零自动重试/零未结预约。API记录耗时累计65.144秒，非端到端墙钟。服务账单金额未核实。五次出站前保守预约停止包含开发及四会话；并非全局500k额度用尽。现停止联网，不复用余额或挪会话份额。
- 主交付：[统一协议/结果/根因/复现](EEG_WORKING_MEMORY_ISSUE48_PROTOCOL_AND_RESULTS.md)、[方法集成](EEG_WORKING_MEMORY_METHOD_AND_INTEGRATION.md)、[公开合成证据](evidence/issue48_lifecycle_confirmation.json)、`working_memory_issue48_audit.py`只读审计。原messages/tools/responses/预算/首次失败本机保留于忽略目录；没有真实数据/密钥/权重/个人路径提交。
- 强S和full入口同工具/存储/科学规则/读权，离线可运行且公平性检查通过；本轮没有新增付费多臂比较。不得宣称候选优于S、任意意图被证明、声明齐备即原需求齐备或跨进程恢复已实现。
- 尚未解决：已完成等价目的可重复进入；归档到最终回答不稳定；保守预算未充分保障最后回答；工具前提与实验准备遗漏；B漏声明用户功率需求；未调用质量却陈述阈值状态；真实轨迹恢复后的科学续算链未完成。
- 下一阶段唯一优先目标：同一请求有有效交付后可靠结束/有理由继续。精确入口为`ReliableWorkingMemoryStore.begin_subgoal`、`WorkingMemoryController.build_messages`，保留合法用户重算/新版本，先复现A闭环，不增工具或关键词。未来真实验证前先审计协议可执行性及最后回答预算；需新任务授权，不自动开始。
- 本阶段实现提交已普通推送；最终证据/文档随本次交付提交并推送原分支，保持Draft，不合并main、不强推。当前执行状态为结束，等待用户审查。
- 发布留痕：证据/文档提交`578c21b5044179dbb5a286f182be97338378981c`已普通推送；[Issue #48结果](https://github.com/lzy123-web/eeg-agent-harness/issues/48#issuecomment-6422239943)及[PR #37阶段评论](https://github.com/lzy123-web/eeg-agent-harness/pull/37#issuecomment-6422266395)已发布，PR正文保留旧历史并新增本阶段，仍为Draft/open/unmerged。Issue未关闭，完整验收缺口留待审查。

## Issue #47：阶段交付完成；新版复杂自主验收未通过

- 起点本地/远端均 `1d11cc132cef1ef6e423eff60a1f5d4865cbe208`，安全fetch无分叉、工作区干净，继续原研究分支和Draft PR #37。已读取Issue全文，承接而不重新选题。
- 用户新授权本阶段独立上限48 external completions、300,000 API输入＋输出tokens；旧账本不动。计划开发至多16次/100,000 tokens，确认预留至少32次/200,000；全部请求含失败/重试在新持久账本先预约，零自动重试。先离线通过再启用联网。
- 三项明确缺口：跨目标正常close被重复保护误停；全历史精确证据合并形成累计8项上限；工具级单位污染计数/频率标量。先保留复现，再最小修复。资料与字段语义按Issue允许分工，集成/真实确认顺序执行。
- 主要交付：修复及反例，有限真实模型完整确认，按学校栏目编排的 `THESIS_PROPOSAL_WRITING_PACK.md` 和核实BibTeX。学校正文不少于3000字，未规定文献篇数；不把写作建议当校方要求。
- 联网前锁定时：三项原缺口已真实工具复现，修复后412项测试（397通过/15资源跳过）、compileall通过。公共重复键加入目标身份；全部档案与当前精确证据集分离；字段语义独立核验。确认自然请求及posthoc需求清单在 `config/point1_working_memory_issue47.json`，开发/确认使用不同合成配置；先完成离线后才调用模型。
- 实现提交 `f29f139` 后首次真实开发6次/27,374tokens，2项数值oracle及多结果合同通过；模型并行工具提议被拒后自行恢复，最终“本次未重算”存在来源时间歧义。保留首次日志；开发修订1添加真实轮次/本轮取得标志，46项工作记忆相关测试通过，无付费复跑旧请求。确认前余额42次/272,626tokens，足以保留原确认32次/200,000预留。
- 确认锁定 `83e2c00`，未在确认上调整方法/提示。最终 **36 completion / 277,191 API tokens**，输入271,817、输出5,374；开发6/27,374，确认30/249,817；36次实际返回deepseek-flash（请求deepseek-chat），零未结算、零网络失败、零自动重试。跨运行独立账本保留在忽略目录，旧账本不动。两次大请求在出站前被保守预算预约拒绝，实际总量未越300,000；不将预算保护误报API故障，现已停止而非等待余额继续。
- 真实结果：混合首轮21次/196,983 tokens，主要连续/事件数值已产生，24个工具请求后停止，没有完整回答；续接1次/16,817，未完成新窗口或质量。短查询3次/13,368，正确报告128Hz及SYNTH-C1/C2。缺参5次/22,649，模型自行采用−0.5～0.5秒窗创建Epoch而未澄清，属于实质未通过。开发实际多结果归档、确认实际同轮结果复用；未触发新版旧轨迹恢复，不能算自然修订成功。
- 诊断：并行批次与逐动作接口不一致、未来交付项名误作实际结果依赖ID、计数条件用错字段路径但进入合同、重复复用造成控制与输入开销；缺参科学范围没有可靠授权来源。共有工具返回正确不等于模型目标/最后交付正确。确认后只增加只读审计，不补句式规则或修改冻结事实。
- 独立核验：为避免旧代表字段audit只核C1，本轮事后核对所有实际请求频带及C2事件值，23字段通过（开发6、混合17，后者含额外C1五频带）；原结果、误差、范围、首次失败和哈希见 `evidence/issue47_reliability_and_confirmation.json`。`working_memory_issue47_audit.py` 仅读取本机日志和确定性合成原采样，绝不进入Agent决策。完整原始响应/账本不提交。
- 最终验证：`PYTHONPATH=src python -m compileall -q src tests`；`python -m unittest discover -s tests -q` 为 **412 tests：397 passed、15 resource-gated skipped、0 failed**；`python -m pip check` 无依赖冲突。全部资源跳过仍为跳过。只读审计入口 `python -m eeg_harness.research.working_memory_issue47_audit --output artifacts/point1_task_memory/issue47/new-audit.json`，不覆盖旧输出。
- 写作交付：`THESIS_PROPOSAL_WRITING_PACK.md` 覆盖学校全部栏目，正文超过3000汉字，附20项核实原始来源与 `THESIS_PROPOSAL_REFERENCES.bib`；目的/方法/继承与适配/两工作点公平实验/技术路线/难点/可行性/框架/相对进度/10问答俱全。TC仅只读接口与资料核查，修正两独立推理函数均名generate_output；未读取或外发其真实样本/特征，未运行模型，不复制私有正文/权重/源码。
- 研究结论：保留科学子目标工作记忆的领域适配候选，不把重复保护、工作集分页及单位修复列为创新。方法代码和离线机制具备基础，但完整真实交付与公平相对收益未证实。下一阶段唯一优先项为**科学交付合同的正确接纳、必要澄清及有界修正，先完成一条真实跨任务续接**，再冻结比较；本阶段不继续扩展或自动联网。明天可以据实写研究问题/方案/已有原型及失败边界；只需个人模板信息，应用特征/标签/许可等作为后续明确资料缺口。
- Git：起点、修复和修订均保留，`f29f139`、`83e2c00` 已普通推送原研究分支；本结果与写作材料另作集中提交。PR #37保持Draft，不合并main、不强推；最终交付Commit及CI发布核查随后在本节留痕。
- 发布核查：结果/材料提交 **`43a5c6d56c37a5ceec757bb34d53437054bfa4c3`** 已普通推送、本地/远端无分叉；其 [GitHub Actions unit-tests #273](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40335873505) 安装、编译、资源独立回归步骤均success。PR #37正文已更新且仍Draft/open；[Issue #47实际结果评论](https://github.com/lzy123-web/eeg-agent-harness/issues/47#issuecomment-6417976383)已发布，Issue保留open以反映复杂自主验收缺口。本条仅同步发布状态，不增加调用或改方法。公开文件核查未含密钥、个人资源路径、真实EEG或权重，原始账本与响应经check-ignore确认留本地。

## 后续用户阶段任务：多结果闭环、开题依据与师兄成果复用设计（实现与离线交付完成）

- 安全 fetch 后本地与远端均 `2c34049`、无分叉，继续 PR #37 原研究分支。已完整阅读附件阶段任务、最新主文档和代码。无新外部 completion 授权，保持 Issue #45 账本不动。
- 核实单终端归档缺口，选定“显式交付要求列表＋实际结果清单”的最小扩展；保留旧单结果模式，不新建 Executor，不按案例写流程。将实现后补充分项完成/失败/修订/复用测试。
- TC 私有仓库读取可用，本地资产只读核查中；不执行训练/推理/数据库脚本、不复制私有数据/模型。阶段新增工作点二范围仅为复用设计与合成证据接口样例，覆盖早期“不启动工作点二”的本轮范围限制，不扩展为完整报告系统。

- 实现检查点：设计提交 `555fa84` 后完成 opt-in `MultiResultWorkingMemoryStore`、统一 Agent 列表合同/全部结果交接、原工件/结果复用及按版本修订；原 single 模式和原数值执行器不变。新增确定性声明检查样例与 Controlled CLI，真实 CLI 要求独立新授权配置，不再默认打开旧额度。
- 实测：397 tests（382 passed、15资源跳过），compileall 通过；离线两轮21次受控决策、7次数值工具执行、4子目标7结果，5项独立oracle通过；原事件artifact被恢复后继续质量测量，无重复create_epochs/bandpower。本轮外部模型0次，不把Fake当作真实完整验收。首次2项测试字段假设错误及绑定优先级修订记入主方法文档。
- 实现及离线样例提交 `24d4cd2`。已新增集中开题简报 `THESIS_PROPOSAL_RESEARCH_BRIEF.md`，核对 HiAgent、EEG Agent、EEGAgentBench、CogEEGAgent、NeuroAct 原文，区分2篇正式论文与3篇预印本，形成问题—依据—机制—代码—验证表、方法图、研究判断与公平实验设计。新版本真实模型自主闭环及相对强 S/直接迁移收益尚未验证，不把合同/证据追踪声称为首次创新。
- TC 只读审计：私有远端与本机10个关键脚本逻辑一致（7个blob完全一致、3个仅换行差异）；Stage1特征文本→报告，Stage2报告→情绪能力受损等级；不是ASD诊断。模型训练/推理格式及生成上限存在不一致，部分脚本导入即执行训练/写图。远端LoRA为LFS指针，本机有实际adapter但未加载，依赖/许可/标签依据/特征公式仍待核实；没有导入这些脚本、安装依赖或连接数据库。未拷贝私有源码、数据或权重。
- 复用交付为接口设计和 `evidence_statement.py` 的模板声明示范；公开JSON全部合成，关键值/范围/版本/来源可核查，错值等负例拒绝。没有实际报告模型或临床验证，工作点二仍为拟研究方案。
- 下一阶段唯一方法优先项：获得独立预算后，验证新多结果模式真实自然续接和完整交付；在此之前不跑排行榜、不扩展记忆分组或Planner。报告复用资料优先补特征定义、标签/拆分与使用许可。容量8项精确证据/24KB、消息96KB、未迁入模型推理/变换、无跨进程恢复与自然语言全意图证明仍为边界。发布结果在完成安全扫描和普通推送后追加。
- 发布核查：`555fa84`、`24d4cd2`、`d573d04` 已推送，PR #37 正文更新且保持 Draft/open。直连GitHub超时后使用本机已配置代理，仅按命令临时设置，安全fetch确认无远端新提交再普通push；未修改永久Git配置、未强推。`d573d04` 的 [GitHub Actions unit-tests #267](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40325972571) 安装、compile及资源独立回归均成功。本阶段13个变更文件扫描未发现密钥、个人路径、EEG/权重资源；唯一新公开执行JSON为合成样例，SHA256 `f24b2727ec27fa2b9cd6758491697b0c94d69f8b45a2219c872ac50e49ad7153`。本条为纯文档发布状态同步，不产生新调用；完整交付后停止。

## Issue #45：有界交付，真实完整任务验收尚未通过

- 已提交设计依据 `94aaaf3`，核对 HiAgent 原论文和官方实际加载代码；不复制未明确许可的源码。实现 `1f5f6fe` 为 opt-in 原 `EEGAgent.run` 记忆钩子、科学子目标和原 Executor 逐动作执行，旧入口不变。修订1 `0226293` 明确计算scope反馈；修订2及确认锁定 `bf744c6` 增加实际交付状态、合法关闭/身份别名、减少重复交接及预算预留保护。后续只做诊断/离线审计和文档，没有第三轮方法优化。
- 新代码：`working_memory.py`、`working_memory_agent.py`、`working_memory_cli.py`；实验输入/后验核验单独在 `research/working_memory_validation.py`。保留旧 Issue #36–44 结果，不把本轮实现当成收益证明。
- 最终离线：`python -m compileall -q src tests`、`python -m unittest discover -s tests -q`、`python -m pip check`、`git diff --check` 通过，**379 tests = 364 passed + 15 resource-gated skipped**；工作记忆24项。`python -m eeg_harness.research.working_memory_validation --offline-audit` 核验5条真实数值观察，全部与独立原采样 oracle 一致，包含未归档结果；不能表述为5个完整任务通过。
- 真实 DeepSeek：40/40 响应报告 `deepseek-flash`（请求 `deepseek-chat`），累计 **40/96 calls、228,734/240,000 API tokens**，无未结算；仅合成元信息/工具结果出站。首次2次失败保留，复跑31次发生事件/连续实际分析、统一续接修订、自然触发旧轨迹恢复后复用原artifact。首轮归档 repeated_action，续接完成新分析但旧事件暂挂，不能记整体成功。锁定后7次确认真实计算RMS/PSD/信息，但重复子目标后在第8次网络请求前预算预约失败，未最终交付。
- 预算不足原因明确：开发阶段仅请求数限制未有效保住原预留100k tokens，已记录工程缺陷并增加跨运行token预留保护。原确认缩小后仍未完整结束；未追加额度，停止一切真实调用。旧日志的 `llm_error` 由账本证实为预算阻断，新代码诊断已分为 `budget_exhausted`，不修改原始记录。原计划跨记录事件确认及真实短任务/缺参未执行。
- 交付主文档 `EEG_WORKING_MEMORY_METHOD_AND_INTEGRATION.md`，公开最小合成轨迹 `evidence/issue45_synthetic_trace_excerpt.json`；完整响应/messages/账本留忽略目录。当前仍不支持真实数据联网、跨进程会话恢复、全意图完备性证明、新模式模型推理/筛选/重参考。发现的关键缺口是子目标中多个真实有效输出只有terminal归档，模型可能重复分析。下一阶段唯一优先项为“多结果交付与归档闭合”，先离线失败回放，之后经新预算授权再做完整确认；本轮不继续开发。旧强 S 默认、历史方法/结果、Draft PR #37 保持。
- 最终诊断/测试代码提交 `a15c173`，379项回归适用于该代码；随后只追加中文交付与合成证据摘录。推送前确认未纳入凭据、私有路径、真实 EEG、权重、本地配置或完整 API 日志；忽略账本保留，不重置额度。远端最终文档/CI状态在发布核查后追加。
- 发布核查：交付提交 `36047c2` 已普通推送，本地/远端无分叉、工作区干净；对应 [GitHub Actions unit-tests #263](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40269435985) 已成功（安装、compile、全部资源独立测试步骤通过）。[Issue #45 结果评论](https://github.com/lzy123-web/eeg-agent-harness/issues/45#issuecomment-6408294364)已发布，PR #37 正文及评论已更新，保持 Draft/open，Issue保留开放以反映验收缺口。本条为纯文档状态同步，不产生新模型调用或方法修改。

## 2026-10-26 完成：Issue #44 任务记忆架构与工作点资格评审

- 当前阶段/范围：继续 `research/point1-eeg-task-memory` / Draft PR #37；只审查既有 HiAgent 启发 EEG 任务上下文路线、真实代码与 Issue #36–#43 原始/公开结果。未改 EEG 算法、记忆策略、Executor、旧评分或历史实验；未启动第二工作点、ASD 报告、真实 EEG 外发或新付费实验。
- 交付：新增 [`POINT1_MEMORY_ARCHITECTURE_AND_ASSESSMENT.md`](POINT1_MEMORY_ARCHITECTURE_AND_ASSESSMENT.md)，用 Mermaid 总体架构与证据传递时序、逐模块文件/函数映射、受控入口的 LLM/程序/脚本职责、跨连续/事件/修订的可重跑 N-long 示例，以及贡献—实现—证据—限制表给出完整判断。报告提交 `4d9ba73`；本状态同步另作纯文档提交。
- 复核：本地与远端起点均 `0780419280f7eaf6c81f191336bdf7acb8ffe522`，无分叉；本机 Issue #43 确认原始 JSON SHA-256 `0372f7893659793262c8e386336e2e7abda3f073c952584b6459c7476d8eccb3` 与公开报告一致，27 轮记录、独立账本 37 completion / 82,393 tokens；仅在本机核对，未提交原始响应。`python -m eeg_harness.research.task_memory_issue43 --offline` 通过，3＋4 次合成 EEG 真实工具分析的 evidence token 与冻结配置一致；`python -m eeg_harness.research.task_memory_eval --mode replay-v3 --sessions N-long --policies F S H HE` 通过，10 个真实工具任务、4 臂各 5 问，H/HE top-1 与真实读回各 5/5；该回放无真实 LLM，不冒充最终回答成绩。`python -m unittest tests.test_task_memory_issue43 -q` 为 18/18；`python -m unittest discover -s tests -q` 为 355 tests（340 pass、15 resource-gated skip、0 fail）；`git diff --check` 通过。环境使用本机既有 `eegagent` Python，公开复现命令见报告。Issue #44 新增外部 completion **0/64**、API tokens **0/160,000**。
- 研究判断：首选 **B：已有连贯可运行的应用方法雏形，当前不足以宣称已成立的独立工作点**。成熟任务记忆的 EEG 对象/时间基准/版本/来源/单位适配具有系统意义，但 F/S/H/HC 共享多个科学合同，HC/HE 相对强 S/H 没有稳定独立净收益；Issue #43 公共交接修复不能归 HC 创新。现有证据还不能把科学对象绑定的增量从合理成熟直接迁移中公平隔离；末轮语言仍可能误述版本或过程。原始负结果、严格初筛与追加等价证据审计分别保留。
- 未解决问题：多轮入口在完整实验中仍由脚本预定分析/历史轮；直接回答无逐断言运行时科学核验；范围解析有限，可能误拒合法表述；Session 仅进程内、条目嵌套值非深度冻结；研究接口只允许合成记录及七种能力，未验证开放自然语言/模型推理/受试者泛化。下一阶段唯一优先候选是**预注册、同信息同读权的强通用任务记忆直接迁移与 EEG 科学绑定的证据闭环归因验证**；若实质等价，则收束记忆为 Harness 基础模块，不再追 HC/HE 表示得分。本阶段完成即停止，不自动运行该后续实验。

## 2026-10-26 完成：Issue #43 统一证据交接与完整任务交付

- 阶段/范围：沿用 `research/point1-eeg-task-memory` / Draft PR #37；工作点一既定 HiAgent 启发 EEG 任务上下文路线，不改旧 CIEDG、Issue #42 历史成绩、EEG Executor/数值算法，不开发第二工作点或 ASD 报告。已安全 `git fetch`，起点本地/远端均为 `5dca165`、无分叉。
- 代码：新增 `task_memory_evidence.py` 的规范字段路径、首轮精确值＋成功读回有界集合、来源/记录/参数版本/单位去重与冲突拒绝、结构化多对象科学范围绑定；新增 `task_memory_issue43.py` 的 F/S/HC 统一历史回答、最终输入可见性评分、真实工具完整流程及追加审计 CLI。旧 `task_memory_issue42.py` 仅增加可选 handler/scorer 注入，默认历史入口与旧结果不变。公共修复不归 HC 独有。`config/point1_task_memory_issue43.json` 与协议在模型输出前冻结，旧 C-mixed 用作开发反例，新 N-continuous/N-mixed 用作确认。
- 验证与结果：`PYTHONPATH=src python -m eeg_harness.research.task_memory_issue43 --offline` 使用真实 Registry/Executor 完成新两流程 3＋4 项合成 EEG 分析，独立原样本 oracle 均吻合。消息级旧路径反例与新路径十余种范围/部分读取/去重/失败测试通过。真实 DeepSeek 仅接收合成 EEG 必要元信息/结果：请求 `deepseek-chat`，**37/37 响应报告 `deepseek-flash`**；独立账本 **37/80 completion、82,393/180,000 tokens**（输入 73,410、输出 8,983；0 未结算）。开发旧/新 7 calls/16,330 tokens；新确认 30/66,063。原始响应、账本、首次失败只在 Git 忽略的 `artifacts/point1_task_memory/issue43/`，确认文件 SHA-256 `0372f7893659793262c8e386336e2e7abda3f073c952584b6459c7476d8eccb3`。
- 完整任务：N-continuous F/S/HC 严格自动均 4/4，但 HC 把未修订 B 标为新版并错误称直接可见值“已读取”，人工不记完全忠实；N-mixed F 5/5，S 原严格 4/5 但同科学对象事件功率中的有效计数 `3` 可替代专用计数条目（追加等价证据审计＋人工核查，原分不改），HC 4/5 且末轮因模型三次提供用户未请求的 `version:new` 被守卫拒绝、仅安全部分答复。不能把部分答复当完整成功。详见 `EEG_TASK_MEMORY_ISSUE43_RESULTS.md`。
- 测试命令：`python -m compileall -q src tests`、`python -m pip check`、`python -m unittest tests.test_task_memory_issue43 -v`、`python -m unittest discover -s tests -q`、`git diff --check`；全部通过，**355 tests（340 pass、15 resource-gated skip、0 fail）**，定向 18/18。代码/协议分阶段提交 `58ddaf3`、`2c98828`、`046e5cb`；确认后仅追加审计与测试 `8e0f5e3`，未改原评分或方法；研究文档 `0fe8547`、远端交付状态 `5df0c13`。均已普通推送到 PR #37 原研究分支，远端 PR 仍 Draft、未合并 main、未强推。`5df0c13` 的 GitHub Actions [`unit-tests` #255](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40220216829) 为 `success`；[Issue #43 结果评论](https://github.com/lzy123-web/eeg-agent-harness/issues/43#issuecomment-6401339272)和[PR #37 阶段评论](https://github.com/lzy123-web/eeg-agent-harness/pull/37#issuecomment-6401341068)已发布。本条纯文档状态同步另行提交。
- 研究判断/边界：保留不可变任务历史＋公共科学证据交接，以强 S 作简单默认，HC 可选，HE 不扩展。整体是成熟任务记忆思想的 EEG 领域适配；公共交接修复是工程正确性。两条合成新流程未证明 HC 相对强 S 的稳定论文独立增量、开放语言范围完备性、真实 EEG 泛化或临床意义。下一步仅在导师审查此贡献定位和样本边界后定，不自动追加收费实验、Prompt 特例或第二方向。

## 2026-10-26 完成：Issue #42 任务记忆定型与完整工作流验收

- 当前阶段：继续 Draft PR #37 / `research/point1-eeg-task-memory` 的 HiAgent 启发多轮 EEG 上下文路线，**本阶段已完成并停止**。旧 CIEDG、H/HE 和全部历史实验不变；没有第二工作点、ASD 报告、新 Planner 或新 EEG 数值工具。
- 代码/协议：新增 `task_memory_issue42.py`、冻结配置、8 项定向离线测试及一份协议/结果报告。统一 CLI 组合已有 `GranularEpisodeSession`、`live_turn`、Registry/Executor 与 F/S/HC 工作视图；连续和事件四任务完整流程含中途证据使用、跨记录或跨条件比较、参数修订。比较读取的公共 verbatim `scope_quote` 保持 EEG 科学范围，所有臂同权。结果评分器在确认后只修中文逗号切句错误，原始响应和原始分数保留，追加审计单列。
- 数据与模型：仅确定性合成 EEG；实际工具结果与独立原样本 oracle 一致。开发 D-short 三臂全部完成；确认 C-continuous F/S/HC 追加审计后各 6/6，C-mixed 分别 3/6、4/6、5/6，另做两条同历史三臂读取。请求 `deepseek-chat`，52/52 有效响应实际报告 `deepseek-flash`；**独立阶段总计 52 completion / 98,029 tokens**（input 87,785、output 10,244；0 失败、0 未结算），未超 96 / 240,000。原始逐轮响应与预算账本只在 Git 忽略的本地 `artifacts/point1_task_memory/issue42/`。真实 EEG、密钥、权重不外发或入库。
- 研究判断：不可变任务历史、EEG 对象/参数版本/来源绑定与按需真实证据读回是一套可运行的领域适配；其核心块/摘要/读取思想来自成熟方法。HC 对强 S 仅在连续流程同效略省 556 tokens，而在事件混合流程更贵并漏掉中途连续功率；**独立论文增量尚未证实**。推荐强 S 作默认，HC opt-in，F 短会话/审计用；不为制造优势继续调阈值或延长对话。
- 遗留问题：模型把事件试次数误作跨能力修订；F/S 的可见 `result_preview` 与底层 `read_fields` 路径不一致；HC 有证据选择漏项；严格原文引文守卫对合法比较可能误拒；自动评分仍不能完美理解标题—数值跨行归属，无外部 EEG 专家评审或多模型泛化。本轮只记录，不在已打开的确认集上修候选再称独立成绩。
- 验证：`$env:PYTHONPATH='src'; python -m eeg_harness.research.task_memory_issue42 --offline`、`--offline-cost`、`python -m unittest tests.test_task_memory_issue42 -q`、`python -m compileall -q src tests`、`python -m pip check`、`python -m unittest discover -s tests -q` 均通过；**337 tests，322 passed、15 resource-gated skipped、0 failed**。`git diff --check` 通过，私有账本经 `git check-ignore` 确认不入库。对 `6ecf6e3` 的 GitHub Actions [`unit-tests` #249](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40213072639) 已完成，结论 `success`。方法和逐类失败见 `EEG_TASK_MEMORY_ISSUE42_PROTOCOL.md` / `EEG_TASK_MEMORY_ISSUE42_RESULTS.md`。
- Git：预冻结方法/协议 `38e724d`、开发诊断后锁定 `106df00`、最终结果/评分器追加审计 `6ecf6e3` 均已安全推送到原 Draft PR #37 分支；PR 正文已更新，[Issue #42 结果评论](https://github.com/lzy123-web/eeg-agent-harness/issues/42#issuecomment-6400350101)与[PR #37 阶段评论](https://github.com/lzy123-web/eeg-agent-harness/pull/37#issuecomment-6400351521)已发布。本次状态同步另作纯文档提交；未合并 main、未强推。下一步只等待研究判断审核，不自动启动新的付费实验或方向。

## 2026-10-25 完成：Issue #41 结果保留与读回粒度阶段

- 当前阶段：沿用 Draft PR #37 的 HiAgent 启发 EEG 任务记忆路线；诊断旧 H 小结果读回成本，完成紧凑精确结果卡 HC、公共字段/完整读口、同历史四臂开发与独立确认、一次 S/HC 自然语言闭环。未启动第二工作点、ASD 报告或新的 EEG 数值工具；旧 H/HE、CIEDG 与历史实验不改。
- 代码与资源：新增 `task_memory_issue41.py`、`config/point1_task_memory_issue41.json`、14 项 Issue #41 定向测试及协议/报告。全部历史由现有 Registry/Executor 在两套确定性合成 EEG 脚本上生成，无真实 EDF、权重或实验室数据出站。HC 对 ≤256 UTF-8 字节的真实结果原样保留，大结果仅索引真实字段；所有 F/S/H/HC 共用科学范围守卫、完整/字段读口。开发中发现多动作/路径显示失败，确认前做一次公共接口修订；确认后仅修通用评分解析并追加审计，原始结果不覆盖。
- 真实模型：请求 `deepseek-chat`，59/59 个有效响应报告 `deepseek-flash`。Issue #41 **独立累计 59 completion / 123,623 API tokens**（上限 96 / 240,000），开发 22、确认 20、预注册连续闭环 8、协议后补充事件闭环 9；自动重试关闭、0 未结算。私有响应和账本在 Git 忽略的 `artifacts/point1_task_memory/issue41/`，不入库。
- 同历史严格确认：F 3/4、S 4/4、旧 H 3/4、HC 4/4；分别 4/5/6/5 次响应、11,581/10,416/10,332/10,030 API tokens、0/603/4,124/686 读回字节、8.15/5.85/7.92/7.51 s 累计墙钟。原始自动筛查误拒否定单位和 Unicode 指数；原分数、原始响应仍保留，追加审计后逐例人工核对。F 歧义题没有擅选一个结果，但以 answer 枚举全部候选、不合冻结澄清契约；H 一次错误字段读回。开发原始及修正评分详见 `EEG_TASK_MEMORY_ISSUE41_RESULTS.md`。
- 有限闭环：预注册连续链中 S/HC 各三次自然语言分析加旧 RMS 追问，均 4/4；S 4 call/6,609 tokens，HC 4/6,952，末轮都直答。主确认后发现原闭环遗漏事件对象，追加明确标注的事件集成检查（不混入主确认）：A oddball→B flash 试次→B flash 功率→两通道历史追问，S/HC 均 4/4；S 4 call/8,289 tokens、0 读回字节，HC 5/8,852、3,406 字节，HC 选择完整读回。数值经原数组独立 oracle；完整回答另逐例审阅。
- 研究结论：小值内联与大值字段读取可运行且减少旧 H 的部分额外读回；相对强 S，HC 仅在四题确认中节省 3.7% tokens，但延迟更高、闭环成本反高，**未证独立 EEG-specific 方法优势**。最简建议保留不可变任务历史/科学读口、小型精确结果卡和完整读回兜底；字段级读回为全臂可选接口，HE 额外分组继续暂置。下一步若获新预算，只应预注册自然、有效的较长历史做强 S vs 紧凑方案的完整成本—正确性配对；本阶段不自动续跑。
- 验证：`$env:PYTHONPATH='src'; python -m compileall -q src tests`、`python -m pip check`、`python -m unittest discover -s tests -q` 均通过；**329 tests，314 passed、15 resource-gated skipped、0 failed**。定向 Issue #41 15 项通过；`git diff --check` 无问题，私有原始账本经 `git check-ignore` 确认不入库。完整协议、哈希、逐例、用量和局限见 `EEG_TASK_MEMORY_ISSUE41_PROTOCOL.md`、`EEG_TASK_MEMORY_ISSUE41_RESULTS.md`。
- Git：协议/方法冻结 `dd6040f`，开发失败后的公共接口修订 `a238430`，确认后只修评价器 `026e92c`，逐例报告/审计入口 `fa11d83`，连续阶段状态 `b5a99a3`，协议后补充事件闭环入口 `60235ba`，补充结果报告 `0fd7508`，状态同步 `f1dd48f`。均已普通推送至 `research/point1-eeg-task-memory` / Draft PR #37；代码/报告提交的 GitHub Actions [`unit-tests` #239](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40207756210) 已完成、结论 `success`。Issue #41 [结果评论](https://github.com/lzy123-web/eeg-agent-harness/issues/41#issuecomment-6399659151) 与 PR #37 [阶段评论](https://github.com/lzy123-web/eeg-agent-harness/pull/37#issuecomment-6399661047) 已发布。未强推、未合并 main。

## 2026-10-25 完成：Issue #40 任务记忆效用归因与方法收敛

- 当前阶段：继续工作点一既定 HiAgent 启发任务记忆路线；完成同历史真实模型配对、原因分析、一次公共闭环接口修正及短多轮复核。未更换研究方向，未改 CIEDG/旧实验、数值工具或科学真值；PR #37 继续 Draft。
- 代码与协议：`config/point1_task_memory_issue40.json` 冻结三份由原真实 Registry/Executor 在合成 EEG 上生成的 3/6/10 任务历史，各取开发/确认追问；新增 `task_memory_issue40.py` 的四臂共同答/读/澄清、独立快照、oracle 后评分、整体配对预算准入、跨运行追加账本与 CLI。公共 `revise` 在有效父任务存在且未提供 capability 时继承父任务类型，显式冲突仍拒绝；属公共接口修复，不是 H/HE 专享机制。首次闭环强迫 F 读取，原始结果保留；`closed-direct` 将末轮改为共用直接答/读取接口，前三轮仍走原 Agent/Executor。
- 真实 DeepSeek 仅见合成任务元信息和必要结果：请求 `deepseek-chat`，57 次响应均报告 `deepseek-flash`。**独立阶段累计 57 completion / 103,906 API tokens**，低于 96 / 240,000；无重试、无未结算尝试。私有原始响应与账本在 Git 忽略的 `artifacts/point1_task_memory/issue40/`，未上传密钥、模型权重或真实受试者数据。与 Issue #39 账本完全分开。
- 同历史完整配对：开发/确认各 3 问；F 6/6（6 call、19,031 tokens）、S 6/6（9、19,364）、H 6/6（12、18,141）、HE 5/6（11、18,220）。所有正确答复数值经独立原数组 oracle 与人工文本审阅；HE 一例选对任务却把空归档索引误读为尚未执行，不是检索错误。H 总 tokens 较 F 少约 4.7%，但调用与延迟更高；S 全部完整正确，HE 额外组织无已证增量。
- 有限闭环：N-short 的 F/H 各 3 次真实自然语言分析＋最终历史追问均 4/4；首次旧历史接口各 5 call，因 F 被强迫读不作成本对比。公共接口修正复核后 F 4 call / 6,496 tokens，H 5 / 6,950，最终 A 连续 alpha `2.00e-10 V²` 未误取 B；这只是已见短链开发复核，不是独立长链结论。
- 方法判断：最简推荐 H＋全臂共享 EEG 来源/作用域/版本读口守卫；HE 分组暂置，不删旧版。任务 episode/摘要/按需恢复可运行，但相对强 S 的总成本/正确性优势、EEG-specific 独立贡献和自然长会话泛化**尚未验证**。下一步唯一有价值的实验是预注册更长、自然、有效 EEG 任务历史上的 H vs 强 S 同权配对；不继续加 HE 关键词或另建 Planner。
- 验证命令：`$env:PYTHONPATH='src'; python -m compileall -q src tests`、`python -m pip check`、`python -m unittest discover -s tests -q`，均通过；**314 tests，299 passed、15 resource-gated skipped、0 failed**。定向 Issue #40 6 项通过。详细协议、逐例及限制见 `EEG_TASK_MEMORY_ISSUE40_PROTOCOL.md`、`EEG_TASK_MEMORY_ISSUE40_RESULTS.md`。
- Git：预冻结协议/公共修订/入口/测试 `dac4961`，结果报告/闭环接口修正 `a11e608`，状态同步 `ab42b01` 均已普通推送到 `research/point1-eeg-task-memory`；PR #37 经远端核对仍为 Draft、未合并。对 `ab42b01` 的 [unit-tests #233](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40200823460) 结论为 `success`。本条为后续纯文档 CI 同步，不修改实验。未强推、未提交私有资源。

## 2026-10-25 完成（长链 S 预算截断）：Issue #39 任务记忆真实使用价值评价

- 独立确认：短集四臂 F/S/H/HE 各 3/3 且最终 RMS `1.41e-05 V` 与独立 oracle 相符；长集完整闭环 H 6/8、HE 5/8、F 5/8，S 在前两轮后因累计 token 上限于第三次请求前停止，不给 S 长链率。H 缺修订能力名、HE 首轮把试次数选成质量、F 幻造未注册能力名，均由公共 Executor/读口安全拒绝或导致后续澄清；HE 的另一事件 alpha 修订/读取数值 `3.2799997787269497e-10 V²` 与独立 oracle 一致，但不抹掉其试次数目标错位。10 条历史最终回答逐条审阅；未发现缺失结果凭空生成，HE 一条为错误质量证据链。确认新增 48 completion / 92,182 tokens，**本阶段累计 126 completion / 292,532 tokens**，已停用剩余 7,468 tokens，不超 160 / 300,000。请求 `deepseek-chat`、有效响应均报告 `deepseek-flash`。
- 最终方法判断：任务 episode/不可变历史/按需恢复是成熟技术启发的可运行系统能力。相同历史离线工作上下文 H `65,428→47,722` 字符、HE `69,081→50,801`，10/10 top-1 未变；本次真实长链观察到 H/HE 的 tokens 均不低于 F，**但各臂历史已分叉，不能据此作压缩成本的因果判断**。HE 比 H 更贵、少对一项，**EEG 对象组额外增量未证**。开发集修订 H 9/9、HE 5/9 受采样/历史分叉影响，不作因果收益。下一阶段唯一重点是在新授权预算下完成同历史 F/S/H/HE 最终读取与回答配对，补齐 S 长链，隔离公共能力误选与记忆作用；不自动续付费、不开发第二点。
- 运行和复现：`$env:PYTHONPATH='src'; python -m eeg_harness.research.task_memory_eval --mode replay-v3 --memory-variant original` 与 `--memory-variant optimized` 可无 API 比较旧/压缩版；原始真实响应与跨进程预算账本仅在 Git 忽略的 `artifacts/point1_task_memory/issue39/`。最终 `python -m compileall -q src tests`、`python -m pip check` 通过；`python -m unittest discover -s tests -q` 为 **308 tests、293 passed、15 resource-gated skipped、0 failed**。真实受试者数据、密钥、权重未入库或发给外部模型。
- Git：协议与硬预算 `e0b9a85`、公共父记录修订 `e4d5771`、摘要压缩与确认顺序增补 `ec01ac8`、逐例结论和旧/新版可运行入口 `80253d5` 已普通推送 Draft PR #37；本条仅同步最终提交/测试信息。未合并 main，未强推。远端 CI 在本次状态记录时尚未返回，不能写成已通过。
- 首次真实阶段：6 completion / 11,072 tokens 的合成 smoke 完成；四臂 `N-medium` 各 12 completion，合计 48 completion / 121,982 tokens，F 9/9、S 8/9、H 7/9、HE 7/9。请求 `deepseek-chat`，实际响应报告 `deepseek-flash`。第 8 轮 HE 已有证据却重复计算，最终数值仍正确，分开记为冗余成本；完整记录见 `EEG_TASK_MEMORY_ISSUE39_RESULTS.md`。新阶段累计 **54 completion / 133,054 tokens**，尚未动用确认集。
- 开发修订 1：修订动作未显式给记录但父任务 ID 有效时，由真实父任务绑定记录，避免切到 B 后错误修订 A 的任务；显式矛盾仍拒绝。评分按实际执行记录判定，而非强制要求多余字段。定向 17/17 通过；此修复属于公共工程，不声称 EEG 适配收益。
- 开发复验：同一 `N-medium` H 9/9、HE 5/9，分别 33,410 / 33,886 tokens；HE 的首次无历史分析已选错质量能力，不能归咎检索。阶段累计 78 completion / 200,350 tokens。修订 2 将 H/HE 工作卡的完整结果替为可读回的任务摘要，`C-long` 离线末轮字符 H 4,024、HE 4,762、F 6,432；保留真实值通过公共 `read_task` 恢复。预算驱动地在首次确认前调整长集臂顺序 H→HE→F→S，脚本真值不动；可能无法在 token 上限内完成全四臂，缺失必须公开。`compileall`、307 tests（15 skipped）通过；尚未开始确认，不以离线字符宣称收益。
- 继续独立分支 `research/point1-eeg-task-memory` 与 Draft PR #37；不修改旧 CIEDG、HiAgent 启发路线或历史实验。新阶段预算独立为 ≤160 次外部 completion / ≤300,000 API tokens；旧 96 次不叠加。首次调用前已冻结协议/公共接口，并从 0 次开启跨运行账本。
- 冻结开发 `N-medium` 与独立确认 `C-short` / `C-long` 的合成脚本、F/S/H/HE 公共动作/读口、两层研究问题、分层评分和阶段预算；见 `EEG_TASK_MEMORY_ISSUE39_PROTOCOL.md`。新增跨进程、请求前追加的私有预算账本，默认不调用 API。公共修复允许跨记录切换并计算、合法事件功率通道读取，完整历史不重复注入同一结果；四臂同时受益，不属于 HE 专享优化。
- 预检：冻结确认脚本经原真实工具链完成；新增定向测试覆盖协议和预算重启/失败计账。后续按最多两轮开发修订→独立四臂确认→逐例报告执行。不能将预检写作真实模型结论。
- 遗留：独立确认、完整最终回答忠实度、HE 相对 H 的独立收益尚未验证。只允许合成 EEG 出站；密钥与原始模型响应保留在 Git 忽略本地目录。阶段结论未定。

## 2026-10-25 当前更新：Issue #38 既定 HiAgent→EEG 任务上下文适配阶段

- 阶段与范围：继续 Draft PR #37 的 `research/point1-eeg-task-memory`，沿用 v1/v2、旧真实响应、负结果和冻结 CIEDG，不重新选题；只做工作点一任务级上下文适配。真实受试者数据、密钥、权重未进入 Git；本轮付费 API 调用 **0**。
- 代码：新增 opt-in `task_memory_v3.py` 的任务 episode 状态。实际 `analyze/revise` 与原 Registry/Executor 的结果决定 started/blocked/resumed/archived；完成任务摘要只留真实来源、条件、版本、字段和读取 ID，原始数值/trace 经共同 `read_task` 恢复并可成为下一轮焦点。HE 对实际 EEG 对象的多版本任务分组；公共读口对错记录/连续或事件范围/通道/事件标签/窗口/版本作保守拒绝。F/S/H/HE 共享原始历史和读取 API；旧 v1/v2 入口不变。CLI 新增无 API `--mode replay-v3` 及有显式额外授权/预算门的未来 `real-v3` 配对入口。
- 机制迭代：首次 v3 离线运行发现 HE 给所有单例重复科学绑定，增加上下文而无命中增益；只保留确有多版本的对象组，首次 JSON 保留。本轮没有调科学真值、旧实验或 EEG 算法。方法对应表、真实运行及失败边界见 `EEG_TASK_MEMORY_DESIGN.md` / `EEG_TASK_MEMORY_RESULTS.md` / `EEG_TASK_MEMORY_DECISION.md`。
- 验证：`PYTHONPATH=src python -m eeg_harness.research.task_memory_eval --mode replay-v3` 生成本地忽略 JSON：3/6/10 项实际工具任务，F/S 目标证据可读 10/10，H/HE top-1 均 10/10；中/长历史实际归档 3/7 条；独立原始样本 oracle 核对读取范围与数值。Fake 多轮经原 Executor 完成分析→修订→历史证据恢复；非法通道 blocked→续接、科学范围误读拒绝与切记录焦点清除通过。`python -m compileall -q src tests`、`python -m pip check`、`python -m unittest discover -s tests -q` 在 `eegagent` 环境通过：**300 tests，285 通过、15 skipped、0 失败**。
- 判断与遗留：完成 HiAgent 启发的任务块/压缩/恢复 EEG 适配的可运行阶段，不是原论文完整复现。HE 对 H 无离线命中增益且中/长平均工作卡分别多 449/448 字符；真实模型理解摘要、最终答案、总 token/调用成本仍未验证。旧 M6 的首轮 analyze/switch 误选不由记忆层修复。下一阶段若单独授权，先冻结新语义评分并以明确预算做 F/S/H/HE 配对闭环；当前开发协议不得冒充未见测试。
- Git：`ac031e5`（任务 episode 与集成）、`c702581`（摘要写入时点修订、研究文档）、`65737ef`（科学范围补测和状态）均已普通推送至原 Draft PR #37；GitHub Actions [`unit-tests` #213](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40183916297)、[`#215`](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40184205749)、[`#217`](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40184403607) 均成功。PR 和 Issue #38 已给出中文阶段结果；本条提交仅同步最终 Git/CI 状态，不改变方法或实验。未合并 main、未强推。

## 2026-10-25 当前更新：PR #37 阶段审查后的任务记忆 v2（离线设计验收）

- 按 [审查意见](https://github.com/lzy123-web/eeg-agent-harness/pull/37#issuecomment-6395350899) 保留 Issue #36 的公共多轮接口与旧 v1 结果；先冻结 `point1_task_memory_protocol_v2.json` 和中文协议，再实现独立 v2 选择器。原协议、96 次真实 DeepSeek 响应、旧失败与冻结 CIEDG 均未修改；本轮**新增付费调用 0 次**。
- 方法：任务级不可变历史仍经原 v3/Registry/Executor；S 的完成任务摘要在 6/10 项历史下实际归档 3/7 条，保留真实结果读取 ID。G 有通用文本/字段、记录、显式时间与修订版本检索；E 仅加从真实记录/事件元信息得到的 EEG 通道、事件标签和科学范围排序。`cue/rest/target/standard` 只在合成协议和 EventSet 中，检索核心不写死数据集标签。全臂工作卡共同披露已有来源、来源阶段、单位和配置；不把 HiAgent-inspired 轻量索引称为原论文算法复现。
- 运行：`PYTHONPATH=src python -m eeg_harness.research.task_memory_eval --mode replay-v2`。3/6/10 项真实工具任务对应 2/3/5 个追问；F/S 所需目标均可读，G/E/E−science 的 10/10 查询目标均进 top-3 且 top-1 正确。中/长历史已真实触发 top-3 选择和 S 摘要，F 未截断。G 与 E 持平，E 中/长平均工作上下文字符还分别多 213/125；无 EEG 独立收益证据。评分用公共 `read_task` 核对记录、能力、范围、修订、来源、单位及独立 NumPy/SciPy 重算数值；相同 task ID 但错误内容判错。旧 M6 的 analyze/switch 错误归为公共动作失败，本轮 Fake 接口 smoke 通过但**没有真实模型复验或修复该失误**。
- 实际验证：在现有 `eegagent` 环境执行 `python -m compileall -q src tests`、`python -m pip check`、`python -m unittest discover -s tests -q`，均通过；**290 tests：275 通过、15 resource-gated skipped、0 失败**。v2 定向 9 项通过。生成的回放 JSON 只在 Git 忽略的本地 `artifacts/point1_task_memory/`，未提交密钥、真实 EEG 或模型权重。
- 研究判断：v2 使摘要/选择机制真正受测，仍只是**离线共享历史**；不能以此宣称 F/S 的真实问答能力、E 优于强 G 或论文贡献已成立。下一阶段若获新预算，先按 `EEG_TASK_MEMORY_PROTOCOL_V2.md` 的分层清单做四臂同历史真实读取和 G/E 多轮闭环，逐臂计入写入、摘要、检索、读取与回答成本；不自动执行。
- Git：独立分支 `research/point1-eeg-task-memory`，Draft PR #37，base 为 PR #27 功能分支；`a5164e1` 冻结 v2 设计/协议，`735b6d2` 公共摘要、强通用基线、EEG 作用域检索与语义测试，`530f2ff` 保存离线回放结果与后续预算清单，均已普通推送。对 `530f2ff` 的 GitHub Actions [`unit-tests` #209](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40178863098) 结论为 `success`；本条 CI 状态同步属于后续纯文档提交。不合并 main、不强推。

## 2026-10-25 当前阶段：Issue #36 多轮 EEG 任务上下文管理（本轮研究验证结束）

- 从经核验的 PR #27 功能树 `fb5b85b` 创建独立分支 `research/point1-eeg-task-memory`；未修改旧 CIEDG、PR #35 或 main。核对 HiAgent、LongMemEval、EEGAgent、BrainAgent 原始来源后，冻结 6 条合成多轮脚本及开发/验证切分；明确本研究为成熟记忆技术的 EEG 适配而非新通用算法。
- 代码：新增公共 `MultiTurnEEGSession`、不可变 `TaskEntry` 和 `read_task`，修订创建新版本；分析调用现有 v3 `run_instances`→Registry/Executor，合成 A/B 记录及事件隔离。F/S/G/E/E−scope 使用同一真实任务/结果历史和统一模型动作/工具接口。公共能力目录由既有 `capability_catalog` 生成；可选第二次 LLM 调用在真实工具结果后作最终答复。新增 CLI、独立数值 oracle 和 8 个定向测试。
- 回放：最初逐臂重跑造成 artifact ID 不同的无效结果保留；修正后 6 会话、10 个历史查询，F/S/G/E/E−scope 均 10/10 top-k 覆盖；G 与消融 top-1 为 7/10，E 为 9/10。历史最多 3 项，S 的滚动摘要分支未真正触发，不能宣称 E 的闭环优势或 F/S 付费模型成绩。
- 真实 DeepSeek：仅合成 EEG；请求 `deepseek-chat`，96 个响应均报告 `deepseek-flash`；合计 **96 completions / 113,296 API tokens**，达到请求硬上限，不再继续调用。首轮 M1 G 0/5、E 5/5 主要因共同参数契约，修订后的回归两臂均 0/5；目录化共同契约后开发 M1/M4 两臂各 5/5，首次验证 M6 两臂各 6/6。增加最终文字交付后重复 M6，两臂均 2/6（首轮共同误选 `switch`，级联历史缺失），开发 M1 两臂均 5/5，修改前后 alpha 分别 `2.00e-10`/`3.92e-10 V²` 且最终回答忠实。旧失败不覆盖、重复验证不冒充未见成绩；原始响应留在 Git 忽略的本地 `artifacts/`。
- 检查：使用 `eegagent` 环境运行 `python -m compileall -q src tests`、`python -m pip check`、`python -m unittest discover -s tests -q`；compileall/pip check 通过，**281 tests，266 通过、15 resource-gated skipped、0 失败**。定向 `pytest -q tests/test_task_memory.py` 为 9/9。数值由原始合成数组的独立 SciPy Welch 验证；真实受试者数据、密钥、原始模型响应均不入 Git。
- 结论：多轮任务历史与 EEG 证据绑定原型可运行，E 的短历史 top-1 排序有诊断信号，但 G 已同样覆盖并在实际闭环持平；当前证据**不足以把 EEG 适配称为已证实的论文独立方法贡献**。公共动作解析错误和模型最终回答仍需与检索故障分开研究。下一步只建议一个预注册、更长有效历史但非垃圾干扰的独立会话集；若仍持平，收缩为 G + EEG provenance/版本安全工程能力，停止扩充 E 特例。完整报告见 `EEG_TASK_MEMORY_RESULTS.md` / `EEG_TASK_MEMORY_DECISION.md`。
- Git：`6526cb6` 冻结方法/协议，`565c22e` 共享多轮实现，`fc1b705` 公共参数契约首修（产生回归并保留），`5d5e088` 目录化契约、最终回答及数值测试，`a4751f3` 研究结果/决策/README。均经普通 push 发布到独立分支 `research/point1-eeg-task-memory`；[Draft PR #37](https://github.com/lzy123-web/eeg-agent-harness/pull/37) 以 PR #27 功能分支为 base，保持 Draft。GitHub Actions [unit-tests #205](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40174847980) 对 `a4751f3` 为 `success`。本状态同步为纯文档后续提交；未强推或合并 main。

## 2026-10-25 当前更新：Issue #29 工作点一方法论审查（仅文档）

- 当前阶段：暂停功能开发，审查通用多任务 EEG Harness 的工作点一研究问题、先行方法重合、已有证据与方向决策；审查基点为 Draft PR #27 的 `c1edcb1`。新增 `POINT1_METHOD_RESEARCH_REVIEW.md`，与导师讨论前不启动下一方法版本。
- 实际工作：只读检查旧 CIEDG/v3、形式化审视共同执行图、对照旧 Issue #16 与 PR #23 负结果及 C1–C8 开发验收；查阅 EEGAgent AAAI 原论文、CogEEGAgent arXiv 正文、WINGS、Pegasus 与 W3C PROV-O 原始/官方资料。未修改算法、工具、Prompt、实验结果或科学真值；未调用付费 LLM，未读取/外发私有 EEG。
- 研究判断：**REFINE 一次且设停线**。当前 v3 是成熟工作流机制的 EEG 实例化候选，不足以直接 KEEP 为已证明独立创新。审查文件只提出一项待导师批准的最小“声明式科学状态投影合同”，要求以后与同规则强 Expert、typed workflow 及全图重放公平比较；若无可复现的跨族额外价值，则降为 Harness 工程并停止包装为新规划算法。本轮没有实施该方案或运行新实验。
- 验证：本轮仅检查文档引用、源码定位与 `git diff --check`；历史结果原样引用而非重跑。Issue #16 为 24/24 vs 24/24、109 vs 109 calls，PR #23 为 7/7、各 37 calls、42 vs 41 方法特定 LOC；v3 C1–C8 是合成开发集，不能当正式比较。
- 未解决：跨任务状态投影的完整科学声明、相对成熟 typed workflow 的差异、v3 未迁移筛选/重参考、自然语言目标遗漏、独立真实数据泛化。下一步仅在用户/导师审核方向后确定，不自动进入实现或第二工作点。
- Git：本地文档提交为 `ab27029`、`0805650`。命令行 GitHub HTTPS fetch/push 连续连接失败；逐 blob 与完整 Git tree 核对相同内容后，使用远端原 head `c1edcb1` 为预期父提交、`force=false` 发布等价远端 `313a89b`、`14ca445` 到 Draft PR #27，未合并 main。两端提交 SHA 因发布接口不同而分叉、**内容树相同**；本地 fetch 仍失败，后续网络恢复须安全 fetch/merge，不得重置或强推。本条记录同步另成纯文档提交。

## 2026-10-25 当前更新：PR #27 多任务开发验收与科学配置证据修订

- 当前阶段：通用多任务 Harness 的有限跨族验收与方法缺口诊断；仍在 `research/multitask-harness-method-v2` / Draft PR #27，旧 CIEDG/Issue #16 正式实验未改，未合并 main。按最新 [审查评论 6386061605](https://github.com/lzy123-web/eeg-agent-harness/pull/27#issuecomment-6386061605) 先冻结 C1–C8 请求、目标、合成记录与数值 oracle，再开发验证；见 `MULTITASK_ACCEPTANCE_PROTOCOL.md` / `MULTITASK_ACCEPTANCE_REPORT.md`。
- 本轮变更：Registry `ToolSpec.config_keys` 声明 PSD 与事件条件功率对频带配置的依赖；共同目标图将实际配置纳入证据 identity、语义身份及失效判定，C8 改频带只重算相关频谱目标。逐目标 bundle 和合成应用摘要披露采样率、频带定义、输入/依赖绑定与限制。语义接口只修复边界标点误拒与同句、等值、已落地事件 scope 的来源引用；保留不同 scope/跨句拒绝。无新 Executor、模型训练或 ASD 解释。
- 验证命令：设置 `PYTHONPATH=src`，运行 `python -m compileall -q src tests`、`python -m pip check`、`python -m unittest discover -s tests -q`、`python -m eeg_harness.research.integrated_method.v3_acceptance`。当前已有依赖环境与本地既有权重下 compileall/pip check 通过，273 tests / OK / 13 skipped；不设权重时 273 tests / OK / 15 skipped。Fake C1–C5 目标类型/参数匹配，C6/C7 零工具安全拒绝；C8 两频谱数值由独立 Welch 调用重算，记录信息/试次数保留。实际本地权重仅对合成 22 导模型适用性/一窗输出做验证，不推断性能。
- 真实 DeepSeek（只有合成数据）：首轮 C1–C6 7 completion / 15,416 tokens，C1/C3/C4 完成、C2 安全澄清、C5 澄清续接误拒、C6 安全拒绝；针对 C2/C5 一次复测 3 completion / 6,410 tokens，C5 完成，C2 因模型遗漏事件 `labels` 仍安全澄清。请求 `deepseek-chat`、10 个响应均报告 `deepseek-flash`；原始输出保存在被 Git 忽略的本地 `artifacts/`，失败未覆盖。不是未见成功率或强专家对照。
- 遗留：语言编译仍会遗漏作用域参数/目标；开放请求的完备性无独立证明。v3 的连续/事件/严格模型能力只在合成与本地既有权重条件下验证；旧版筛选/重参考未迁入当前入口；ERP/ERD-ERS、Sleep/MDD、ASD 诊断不支持。应用端只有研究性分析证据摘要，缺授权儿童映射、年龄/范式/事件释义、适龄参考、行为临床资料和专业审核。候选工作点一的额外论文价值仍需跨族任务、同规则强动态 Expert/Native、公平预算和维护成本对照，不能由本轮证明。
- 下一步候选：冻结独立跨族扩展集和评价器，优先检验分析配置/数据来源变动下的正确失效与恢复、任务扩展维护量；另用独立错误集衡量自然语言参数遗漏/安全误拒，不在当前 C2 文句上反复调 Prompt。停止无界增加事件词表或以旧成功覆盖失败。
- Git：`83ea94b` 冻结验收协议，`d563044` 跨任务配置证据、语言接口边界与测试，`2aeaec0` 中文报告与状态；均以普通 push 发布到原 Draft PR #27。GitHub Actions [`unit-tests` #181](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40110954338) 对 `2aeaec0` 已 `success`。本条 CI 状态同步为纯文档后续提交；禁止强推、覆盖 PR 历史或合并 main。

## 2026-10-24 当前更新：PR #27 阶段审查后的跨任务接口验收

- 继续在 `research/multitask-harness-method-v2` 与 Draft PR #27；已读审查评论 [6385322359](https://github.com/lzy123-web/eeg-agent-harness/pull/27#issuecomment-6385322359)。保留 v3 目标实例、共享证据图、旧 v1/v2/CIEDG 与历史正式实验；未增加事件工具或第二研究点。
- 代码：`v3_agent.py` 对有不同值的同名参数做目标锚点—参数引文归属校验；澄清续接冻结已确认目标顺序、能力、引文、参数、来源阶段和禁止操作，只补可唯一归属的缺项。`v3.py` 的目录只公开当前 Profile、事件与资源满足的 v3 能力，`capability_inventory` 区分当前可用、当前不可用、内部前提和旧入口未迁移；`evidence_bundle` 明示整单 expected/published/publication，失败不发布部分结果；合成应用拒绝不完整证据包。原 Registry/Executor/数值算法未改。
- 先复现后修订：旧链可完成互换的双 PSD 窗口；旧续接不锁禁止操作。新增故障注入证明第二工具失败时不能把第一结果当完整交付。增量测试与方法理由见 `MULTITASK_METHOD_ITERATIONS.md` / `MULTITASK_METHOD_VALIDATION.md`。
- 本地验证：`PYTHONPATH=src python -m compileall -q src tests`、`PYTHONPATH=src python -m unittest discover -s tests -q`、`python -m pip check` 均通过；263 tests、14 skipped、249 实际执行无失败；Fake 三例 2 个直接完成、1 个缺参澄清后完成。提交和远端 CI 待本轮收尾更新；**本轮未调用真实 DeepSeek**，不能把此前开发集末轮成功移作新验证。
- 仍未解决：开放语言目标遗漏、复杂跨句/多处同值参数归属、否定操作被模型整体遗漏的独立发现、多个同名缺项的安全续接、自由形式最终报告与临床解释；旧版筛选/重参考不等于 v3 支持。下一候选是在冻结的跨任务开发集之外制定独立未见测试与公平强动态 Expert 对照，不提前宣称方法优势。
- Git：本地功能提交 `ae15882`、状态提交 `425332c`；HTTPS 一度失败，经远端父 SHA、逐 blob 和相同 Git tree 校验，以 `expected_sha`、`force=false` 发布等价远端 `abc110c`、`1eaed2a`。恢复直连后 fetch 发现本地/远端内容树同为 `eef79fe4`，以普通 `--no-ff` merge `f451b7c` 安全汇合，未改写历史。功能与状态提交的 GitHub Actions #40106247323 / #40106328276 均 success；当前合并/本次状态同步仍需最终普通 push 与 CI 核对。未强推、未合并 main，未上传密钥或真实 EEG/派生结果。

## 2026-10-24 当前更新：Issue #28 能力驱动多目标实例（opt-in v3）

当前阶段为工作点一通用多任务共同机制继续研发，不改旧 CIEDG/历史正式结果。Draft PR #27 的研究分支上新增 Registry-backed 能力目录、`GoalInstance` 参数/来源作用域、自然语言多目标编译、同一 `SharedEvidenceGraphCore` 内部前提与逐目标证据包。独立的合成应用示例仅消费证据包，不重新处理 EEG、不生成诊断或能力分数。`record_info/record_quality/amplitude/psd`、事件质量/汇总/条件功率与合法模型输入可分别或在适用 Profile 内组合；事件筛选、重参考、ERP/ERD-ERS、ASD 解释仍不属于新入口已支持目标。

- 已完成变更：`v3.py`、`v3_agent.py`、`v3_application.py`、`v3_validation.py`、`agent_cli.py` 与新增自动化测试；长期规则和四份既有研究文档同步。相同能力不同窗口有独立实例/结果，完全同参数才可共享；事件 producer 只有全 scope 一致才共享；缺参等待澄清、整体不适用零调用拒绝；状态变化只撤销受影响证据。
- 实际验证：合成双窗 PSD 经独立 SciPy Welch/积分核对，事件条件 alpha 功率经逐 Epoch 独立聚合核对；混合连续与事件经真实 Registry/Executor 执行且无未授权筛选；合成 22 导结合本地既有权重做一次真实模型输出结构检查，缺权重/错 Profile 均零调用拒绝。Fake 三案例完成。真实 DeepSeek 四轮开发检查累计 15 completion/32,066 tokens，首三轮误拒、协议/缺参分类失败保留，末轮双窗、跨族、澄清后继续均完成；只发送合成元数据/请求，不外发真实数据。请求 `deepseek-chat`，末轮响应报告 `deepseek-flash`；不能据此宣称稳定泛化或论文优势。完整回归末次 258 tests（14 skipped）通过；`compileall`、`pip check`、v3 本地权重门控 20/20 均通过。
- 遗留问题：语言目标完备性和复杂共指未得到独立验证；用户确认后的部分执行尚未实现；数据版本分叉只作安全拒绝；大 EEG 全记录哈希有性能成本；严格模型训练来源仍“源码未提供”；正式同预算 Native/强动态 Expert 与消融需另行冻结协议。ASD 应用仍缺标签/参与者/范式、适龄参考和专业解释资料。
- 下一任务入口：本轮只剩 Issue #28 客观报告；本地与远端等价树历史已安全 merge，后续再准备独立未见任务集和同预算强 Expert/Native 对照。旧 v2 章节以下保持历史原文。
- Git Commit / 推送：`190f4ef`、`ec284a1`、安全合并 `ff6246c`、`124ded4`、`3df256d` 已普通推送至 Draft PR #27。最后测试本地提交 `d751913` 遇 HTTPS 网络故障，改用 GitHub 仓库接口逐文件校验相同 Git tree `0da7875`，以预期父 SHA 非强制发布等价远端提交 `192f81d`。两端 SHA 不同但文件树相同，已在本地安全 fetch/merge，未 force push/合并 main。[GitHub Actions #171](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40101242537) 对远端 `192f81d` **success**。本状态同步为后续纯文档提交，不改变功能或历史实验。

## 2026-10-24 当前更新：Issue #26 多任务共同机制研发（旧章节保留历史原文）

当前正式主线仍是多任务 EEG Agent Harness；CIEDG 是工作点一候选。ASD 儿童辅助评估报告为将来的综合应用，R3 仅是一种本地数据来源。Issue #26 最新评论要求从旧 event-only 假设中解耦；本轮在独立分支 `research/multitask-harness-method-v2` 实施 opt-in 新版，不修改旧 CIEDG、Issue #16 gold/results/trace 或 main。

- 已完成：三类真实不同任务族的需求—能力—缺口矩阵；“保留/任务专有化/重构”清单；`SharedEvidenceGraphCore` 的统一目标前沿、输入绑定、失效/局部恢复、类型/来源核验和结果发布；连续/事件/模型策略；ASD 报告的证据需求与禁止解释边界；可复现开发验证和正式公平实验预案。旧版初始跨族实现 `b5cc2f7` 存在继承 event-only 结构的不足，后由 `6b660dd` 任务中性核心修订；失败/修订记录保留。
- 实际验证：`python -m compileall -q src tests` 通过；`PYTHONPATH=src python -m unittest discover -s tests -q` 为 **238 项，OK，13 跳过**；提供本地只读 EDF/已有权重的新版模块测试 **17/17 OK**，模型输出 shape `[1]`。合成 PSD 经独立 SciPy Welch/积分 oracle 核对；record 与 Epoch 内容变化均触发同一新版图的证据失效/前沿恢复；Fake 自然语言连续/事件两例均完成并通过答案门。真实 DeepSeek 只使用合成 EEG：三次开发检查累计 10 completion/18,365 tokens；前两次事件请求安全澄清（模型错误提出未获原文支持的 `epoch_summary`），第三次连续/事件均完成，失败原始响应保留在被忽略的本地 `artifacts/`。请求名 `deepseek-chat`，最后一次响应实际报告 `deepseek-flash`；早期调用未记录响应身份，不倒填。新版非 Fake CLI 在读取 EDF 前要求 `--demo-synthetic`。
- 遗留：自由语言多正向/跨族目标完备性尚未独立验证；一次事件成功不能掩盖两次语言层失败；质量阈值未儿童/范式校准；旧模型训练来源“源码未提供”，不用于 ASD 报告；R3 标签/参与者映射与采集方案仍未知；新图相较强动态 Expert 的独立效益尚未正式比较。无 ERP/ERD/ERS、无 ASD 报告生成器/诊断。
- 下一阶段候选：先冻结跨族任务/状态/故障与独立 oracle，再用同工具、同状态信息、同预算的原生 Agent、旧 CIEDG、强动态 Expert 与消融做正式比较；ASD 综合应用需另取得权威范式、身份映射、适龄参考和专业复核方案。不应把这次开发集成绩写为论文增益。
- Git：`343e4a7`（矩阵/初步设计）、`b5cc2f7`（初版）、`6b660dd`（任务中性核心）、`38c502b`（研究文档）、`49f6af9`（联网 CLI 隐私门）、`c76cbfd`（Epoch 失效测试）均已普通推送至独立研究分支；[Draft PR #27](https://github.com/lzy123-web/eeg-agent-harness/pull/27) 指向旧研究分支，不合并 main。GitHub Actions #157、#159、[最新功能提交 #161](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40083915694) 均成功；Issue #26 已报告真实结果/失败/边界。数据、权重、密钥、私有本地路径和生成产物不入 Git，不强推。本状态同步为后续纯文档提交，不改变实验结果。

以下原“当前阶段”等段落是此前里程碑留存，不再代表 Issue #26 最新状态。

## 当前阶段

Issue #16：工作点一 CIEDG 已冻结并完成第一版正式公平实验。parsed-task 层与同规则 Strong Dynamic Expert 完全持平；消融支持 scientific guard 和局部恢复的实际作用，但真实 DeepSeek 分层子集仍暴露显著意图/回答失败。当前结论为 **Conditional-Go：可作为“可审计状态—证据依赖与有界恢复”方法继续论文写作，但不得主张优于强专家或端到端成熟**。Baseline v1.0、CCEP/LRSP/CIEDG 历史结果保持不变。

正式项目已成为可独立维护的 Python 工程；审计和复用源仍为本地相邻的原 EEGAgent 只读目录。本阶段没有修改原 EEGAgent 核心实现，也没有复制真实 EDF 或模型权重。

## 已完成工作

- 完成 EEGAgent 目录、38 个 Python 源文件、依赖、配置、数据样例、11 个注册工具和 11 个工具权重的盘点。
- 定位 Agent 入口、核心循环、Prompt、LLM 调用、工具注册、文本解析和工具执行链。
- 梳理默认 EDF 加载、预处理、22 导双极派生、全局数据注册、特征计算和模型推理链路。
- 核对 TUEV、Sleep-EDF 和 MDD 评估/训练脚本及其路径、通道和输入条件。
- 将各模块划分为可直接复用、封装后复用和不建议直接复用。
- 确定第一阶段最小基线：EDF、基础特征、事件检测和 `seizureNormalModel_OneSecond` 推理；ERP 与 ASD 不在第一阶段。
- 建立项目长期规则、源码审计报告和基线计划。
- 初始化 `src/eeg_harness` Python 包、CLI、最小配置、依赖说明、来源与许可状态说明。
- 迁移并最小封装 `polar.py`、`preprocessing.py`、`dataLoad.py`、`registerData.py`、幅值/PSD、RoPE 模型组件及 `seizureNormalModel_OneSecond`。
- 使用显式 EDF/权重路径和惰性模型加载，避免工具发现时加载无关模型。
- 建立标准库 `unittest` smoke test，覆盖真实 EDF、特征、模型输出、JSON 序列化和缺失权重失败。
- 建立 `.gitignore`，排除 EEG 数据、模型权重、密钥、本地资源配置和生成结果。
- 新增通用 `EEGRecord` 数据对象，显式保存二维 EEG 数组、真实采样率、通道名、参考/导联说明、原始来源、处理步骤和来源元数据。
- 新增统一 `EEGRecord.slice` 接口，校验未知通道、负时间、倒置时间、空时间窗、记录越界和采样后空窗。
- 将幅值、PSD、`seizureNormalModel_OneSecond` 及 `pipeline.py` 改为显式接收/传递 `EEGRecord`；正式执行链不再导入或调用 `legacy.register_data`。
- 保留原始预处理、幅值、Welch PSD、模型结构和权重加载算法，未修改相邻原始 EEGAgent 项目。
- 实现 `TaskProfile`，提供 `tuev_bipolar_22` 与 `edf_native` 两种数据适配；加载器与 Profile 分离。
- 初始实现四个标准工具，Milestone 2 扩展至八个；惰性 `ToolRegistry` 和结构化 `Executor` 统一返回 JSON 安全的 `ToolResult` 与错误码。
- 实现任务隔离的 `ExecutionContext`、`ExecutionTrace`、结果引用和确定性多工具 Workflow。
- 实现 OpenAI 兼容原生 Tool Calling Agent Loop、环境变量配置和 `DemoFakeLLM`。
- 新增 Workflow CLI 与 Agent CLI；没有实现候选论文创新机制、ASD、RAG 或新模型训练。
- 增加无私有资源 GitHub Actions，并加固数组元素、非有限数值、空/越界窗口、额外参数及 Profile 不匹配测试。
- 新增 `EventSet`、`EpochSet`、MNE annotation 映射、边界试次拒绝和可选 baseline 校正。
- 新增 `list_events`、`create_epochs`、`epoch_summary`、`event_bandpower`，Epoch 数组只保存在任务 artifact store。
- 新增确定性事件工作流、合成事件 CLI 与 Fake LLM 四工具链；未引入 ASD/TD/R3 标签语义。
- 修复共享 Executor 的 artifact 会话隔离，新增 MNE 绝对时间/crop/重采样样本级回归及非有限值、短 Welch 窗口失败行为。
- 通用 EDF 适配支持显式选导、滤波、陷波、平均参考和可选重采样；R3 专有配置位于 `applications/r3`。
- 新增 R3 资源诊断、单文件事件工作流、外部事件表适配、去标识公开摘要和显式受试者聚合。
- 受试者聚合先在 participant 内合并记录，再进行可选 group 描述；无显式映射时拒绝组间描述。
- 新增结构化任务、EEG 状态快照、工具操作契约、Plan、规划轨迹和有限动态重规划；没有修改 EEG 数值算法。
- Planner 复用原 Registry/Executor/ExecutionContext，能执行前拒绝静态非法目标并构造事件 artifact 依赖链。
- 冻结 16 项开发/保留任务，公平比较 Execution-only、强 Expert DAG、候选 Planner 及三项消融。
- v2 将旧 Expert 保留为无恢复消融，并为强 Expert 与 Planner 配置相同的状态观察、一次恢复和调用预算。
- ToolSpec 新增 Artifact 生产/消费、事件前置条件、状态观察与科学前置条件声明；新增 `epoch_summary` 路径无需 Planner 工具名专用分支。
- 增加五类确定性故障注入、22 项冻结任务集、逐例 JSON 结果和自然语言结构化目标桥；原生 Agent 保持可用。
- 新增 `record_quality`、`epoch_quality` 和 `select_quality_epochs`，输出来源阶段、单位、validity、经验阈值及数据影响，不生成质量总分。
- 新增 EvidenceGoal/Requirement、固定流程、强 Expert 和 Candidate 三策略公平对照；合法替代必须由目标显式授权。
- 冻结并执行 16 个合成质量/覆盖案例；Candidate 与强 Expert 结果和调用数完全持平。
- 加固 `OpenAICompatibleClient`：非思考模式、输出上限、有限重试、usage/finish reason、空 content、多 tool call 和脱敏错误。
- 新增 `llm_smoke`，分别检查配置、网络/认证、结构化工具调用和带 `tool_call_id` 的结果回传。
- 新增无需 EDF/权重的 `agent_cli --demo-synthetic` 真实 LLM 入口；外部服务只接收合成记录元数据、工具 schema 和派生结果。
- 新增四项有界真实 LLM 验收套件与默认跳过的联网测试；CI 不需要密钥。
- 真实 `deepseek-flash` 完成基础信息、指定窗 PSD、事件 artifact 三步链和临床诊断拒绝；脱敏逐例结果已固化。
- 冻结 Baseline v1 的 30 项自然语言任务集、18/12 development/holdout、15 项真实 DeepSeek 子集及独立判定规则。
- 新增统一 Baseline Runner、三种合成场景、总请求/Token 预算、逐例脱敏 Trace 与分层判定；请求不暴露工具名和调用顺序。
- Fake/Mock 30 项全部跑通协议链；真实 DeepSeek 初始严格 3/15，12 项失败均保留并分类。
- 通用最小工具 Prompt 修复后只复测 5 个 development 案例，5/5 通过；holdout 未复测且不再声称未见。
- 本地真实 EDF+权重工作流以及两份匿名 R3 的事件、特征和质量链均复现；真实数据没有进入外部 LLM。
- 核实 CogEEGAgent、NeuroWeaver、WINGS/PROV-O 和 MNE 重采样/Epoch 官方文档，明确 semantic workflow、typed contract、DAG 与 provenance 本身不是新颖性证据。
- 在原型结果前冻结 Issue #8 的 18 个 development/holdout 科学语义任务、独立 oracle、三种公平对照与统一预算。
- 新增隔离 `research/semantic_planning` 原型：不可变 Artifact/Effect/Requirement/Plan、raw/processed 分支、events 联合重采样、Epoch 筛选 lineage 与 8 个操作契约。
- 所有研究操作复用现有 Registry、Executor、ExecutionContext、EEGRecord 与 EpochSet；没有侵入 Baseline v1 执行链。
- Strong Expert、Generic Semantic 与 Candidate 在 18×3 案例上完全持平；Candidate 没有正确性、调用成本或相对 Generic 的扩展维护优势。
- 冻结 24 项科学意图任务与独立 slot gold；真实 DeepSeek 在 11 个可评价 development 案例中出现 1 个未授权事件条件选择。
- 将 5 个 controlled injection 与自然错误分开：5/5 合法执行且离线意图不匹配，但不计作模型错误。
- 在剩余预算内比较两个 holdout：Native/Intent Contract 为 2/2，Strong Preflight 为 1/2；样本不足且候选未优于 Native，停止方法扩展。

## 实际验证结果

最新验证日期：2026-10-24。本轮调用真实 DeepSeek API，但只使用确定性合成 EEG；未向外部服务发送真实受试者数据，未下载数据、未训练模型。

| 检查项 | 结果 |
|---|---|
| Python 源码语法读取 | 38 个 `.py` 文件均可由 `ast.parse` 解析。 |
| 运行环境 | 使用本地 `eegagent` Conda 环境；`pip check` 无损坏依赖。 |
| 关键环境 | Python 3.10.17、MNE 1.6.1、NumPy 1.24.4、SciPy 1.10.1、PyTorch 2.14.1+cpu。最小基线不依赖 OpenAI。 |
| 工具注册 | 成功发现 11 个工具。 |
| EDF 样例 | `gped_049_a_6.edf` 原始 250 Hz、33 信号、241 秒。 |
| 默认预处理输出 | `(22, 61696)`、`float32`，目标采样率 256 Hz。 |
| 成功路径 | 幅值、PSD、对称性、单通道癫痫、10 秒慢波/癫痫/背景、整段正常/异常。 |
| Sleep 工具 | 在默认 22 导数据上失败：模型期望 2 导。 |
| MDD 工具 | 在默认 22 导数据上失败：模型期望 19 导。 |
| RAG | BGE-M3 目录缺少 `model.safetensors`/`pytorch_model.bin`，初始化抛出 `OSError`；Agent 可降级跳过。 |
| 外部 LLM | 未执行，未验证 API 可用性、真实工具规划或端到端回答质量。 |
| 现有测试 | 未发现标准 `test_*.py`/`*test*.py` 测试套件；评估脚本会写输出，不在本轮执行。 |
| 改造前 smoke test | `python -m unittest discover -s tests -v`：原有 5 项全部通过。 |
| 显式数据对象回归测试 | 同一命令共 10 项全部通过：新增 5 项覆盖正常切片、无效通道、时间越界、空时间窗和两份记录交替使用的数据隔离。 |
| 正式项目 CLI | 成功生成 `artifacts/baseline_result.json`；该目录被 Git 忽略。 |
| 幅值结果（FP1-F7, 0–1 s） | mean_abs `1.74e-05`、RMS `2.37e-05`、max `2.63e-05`、min `-6.14e-05`。 |
| PSD 结果（FP1-F7, 0–1 s） | delta `1.86e-10`、theta `1.24e-10`、alpha `2.03e-11`、beta `1.56e-12`、gamma `6.96e-13`。 |
| 癫痫模型结果（FP1-F7, 0–1 s） | `Non-seiz=0.0`、`seiz=1.0`；这是现有权重在单一样例窗口的工程输出，不是性能或临床结论。 |
| 模型输入与权重 | 单窗 shape `[1, 256]`；`seiz&normal.pth` SHA-256 `e67a7b7aa958642b4d194c03fe4750995be89150e84b82cf78d662d35831c41b`。 |
| EDF 校验值 | `gped_049_a_6.edf` SHA-256 `9f83f1294724fa04686e9051f085c4a9c0d1fe9854126c3c13c52c25577104cf`；资源未进入 Git。 |
| 改造前后回归 | 使用同一 EDF、权重、`FP1-F7` 0–1 秒窗口比较；输出 shape、256 Hz 采样率、幅值与五频带 PSD 结果、模型概率、EDF 与模型 SHA-256 全部一致，确定性字段无差异。 |
| MVP 完整测试 | `compileall` 通过；`unittest discover` 共 32 项通过、0 失败、0 跳过（已提供真实资源）。 |
| Profile | `tuev_bipolar_22` 输出 `(22, 61696)`/256 Hz；`edf_native` 保留所选 EDF 通道与原始 250 Hz。 |
| Registry/Executor | 当前 8 个工具注册；Native 暴露 7 个，双极 Profile 暴露 8 个；列表查询不加载权重。 |
| Workflow | 基础信息→PSD→癫痫推理三步成功，结果与 Trace 可 JSON 序列化。 |
| Fake LLM | 基础信息、频带功率、真实癫痫权重调用闭环均通过；工具调用上限测试通过。 |
| 真实 LLM | 环境未配置 Base URL、API Key、模型名，故未执行、未验证。 |
| Milestone 2 全量测试 | 46 项通过、0 失败、0 跳过（提供现有 EDF/权重）；无资源环境 37 项通过、9 项跳过。 |
| 合成事件验证 | 128 Hz 合成信号及独立测试信号验证 annotation 时刻、Epoch shape、边界拒绝、baseline 和频带功率可复现。 |
| 事件工具链 | `list_events → create_epochs → epoch_summary → event_bandpower` 经确定性 Workflow 与 Fake LLM 均成功。 |
| 真实带事件 EDF | 本地 `gped_049_a_6.edf` 实测 0 个 annotation；因此真实 EDF+事件集成未验证。 |
| CI | GitHub Actions 执行 compileall 和无资源 unittest，不下载私有 EDF、权重或大型数据。 |
| R3 资源诊断 | 只读检查 69 个 EDF；统一 21 个 EEG 通道、300 Hz、数字 annotation 1–9；单文件事件数范围 40–116、时长范围 108–406 秒。 |
| R3 单文件链路 | 两个目录各取 1 个匿名文件均完成加载→预处理→事件→Epoch→频带功率；事件数分别 96/81，有效 Epoch 60/72，均为工程链路计数。 |
| R3 科学语义 | 标签 1–8、标签 9 Boundary 规则、细动作范式和目录所指人群均无权威实验说明确认，状态为未验证。 |
| 受试者/组分析 | 未发现可采用的显式参与者映射与权威分组表，未执行真实受试者聚合或组间比较。 |
| Milestone 3 测试 | `compileall` 通过；提供 EEGAgent EDF/权重和 R3 样例时 59 项通过；无私有资源时 48 项通过、11 项按设计跳过。 |
| 规划先导对照 | Planner 有效任务完成率 100%、正确拒绝率 100%；Expert DAG 为 83.3%/100%，唯一完成率差异来自单个动态 artifact 丢失案例。 |
| 调用与开销 | Expert 10 次工具调用，Planner 16 次；一次本地描述性平均耗时约 0.157/0.211 ms，不作统计推断。 |
| 消融 | 无状态追踪 66.7%/0%；无重规划 83.3%/100%；仅参数校验 33.3%/0%（完成率/正确拒绝率）。 |
| Planner 真实资源 smoke | 现有 EEGAgent EDF/权重的一秒模型任务 1 调用完成；匿名 R3 标签 1 事件任务 3 调用完成。 |
| 真实 LLM | 三个必需环境变量均未配置，未执行、未验证。 |
| Milestone 4 全量测试 | `compileall` 通过；提供 EEGAgent EDF/权重和匿名 R3 样例时 76 项通过；无私有资源时 65 项通过、11 项按设计跳过。 |
| v2 公平对照 | 强 Expert 与 Planner 均为有效任务完成率 100%、正确拒绝率 100%、2 次瞬态恢复、0 失败；工具调用分别 20/27，未观察到 Planner 结果优势。 |
| v2 消融 | 无恢复 Expert 与无重规划 Planner 的有效完成率均为 77.8%；无状态 Planner 为 66.7%。 |
| Fake 自然语言对照 | 9 条人工模板；结构化目标桥下 Expert/Planner 为 100%，原生 Fake 为 55.6%。这是模板覆盖差异，不是实际 LLM 性能结论。 |
| Milestone 5 全量测试 | `compileall` 通过；提供 EEGAgent EDF/权重和匿名 R3 样例时 98 项全部通过；无私有资源时 87 项通过、11 项按设计跳过。 |
| 真实 LLM | 三个必需环境变量仍未配置，未执行；token/API 成本和自然语言质量均未验证。 |
| 合成质量检出 | 通道注入 TP=7、FP=0、FN=0、TN=9；4 个可测 Epoch 案例的标记数均与注入真值一致。只适用于合成真值。 |
| 证据策略公平对照 | 强 Expert 与 Candidate 均为目标成功率 100%、正确拒绝率 100%、总体正确率 100%、32 次调用；Candidate 无额外价值。 |
| 固定流程对照 | 目标成功率 30%、正确拒绝率 100%、总体正确率 56.25%、25 次调用；仅说明质量门控有用。 |
| 两个匿名 R3 质量 smoke | 前 10 秒均无 flatline 标记；默认 200 µV 下幅值标记 3/0 通道，100/500 µV 下为 6/0 和 5/0，显示阈值敏感；50 Hz 均不可观测。 |
| Milestone 6 全量测试 | `compileall`/`pip check` 通过；有资源 108 项全部通过；无资源 97 项通过、11 项跳过。 |
| DeepSeek 协议探针 | 配置、网络/认证、强制 tool call、tool result 回传全部通过；3 请求、619 tokens。 |
| 真实 LLM 分析闭环 | 3 个真实工具闭环全部成功：`record_info`、`psd`、`list_events → create_epochs → event_bandpower`。 |
| 真实 LLM 安全负例 | 临床诊断请求被明确拒绝；未调用 Native Profile 不支持的癫痫模型，未编造结果。 |
| 事件 artifact 传递 | `event_bandpower` 使用与 `create_epochs` 返回值完全相同的 artifact ID；2 个有效 Epoch、1 个越界拒绝。 |
| DeepSeek 调用成本 | 四案例 9 次请求、5 次工具调用、16,041 tokens；非思考模式，单请求上限 768 tokens。 |
| Issue #6 全量测试 | `compileall`/`pip check` 通过；有 EDF/权重/R3 资源时 116 项通过、真实联网测试 1 项默认跳过；无私有资源时 105 项通过、12 项跳过。 |
| Baseline v1 冻结集 | 30 项：development 18、holdout 12；真实 DeepSeek 固定子集 15；规范化 SHA-256 `e1713cda…4654ae1`。 |
| Fake/Mock Runner | 30/30 协议案例完成；59 次本地 Fake 请求。该结果不作为语言模型性能。 |
| DeepSeek 首次固定子集 | 严格 3/15；37 请求、72,358 tokens。必需工具/禁止动作/结果/参数/artifact/回答检查均通过，12 项因额外工具调用不满足最小集合。 |
| DeepSeek 有界复测 | 通用最小调用 Prompt 修复后，5 个 development 案例 5/5；9 请求、16,819 tokens。holdout 未复测。 |
| DeepSeek 总预算 | 46 请求、89,177 tokens，低于 48 请求/120k tokens 限制；cost 未取得可靠 API 金额，记录为 null。 |
| 本地 EEGAgent 资源 | `[22,61696]`/256 Hz；信息、PSD、癫痫模型全部成功，单窗模型原始输出仍为 `Non-seiz=0.0, seiz=1.0`。 |
| 两份匿名 R3 | 21 通道/300 Hz；事件 81/96、有效 Epoch 72/60；事件频带、记录质量与 Epoch 质量均成功；未解释组别或标签。 |
| Baseline v1 全量测试 | `pip check`/`compileall` 通过；有资源 124 项中 123 通过、1 项联网跳过；无资源 112 通过、12 跳过。 |
| Baseline v1 GitHub Actions | run `39787839835` 对提交 `7c852da` 执行无私有资源测试，结论 `success`。 |
| Issue #8 冻结集 | 18 项（development 12、holdout 6），规范化 SHA-256 `1e2de202eb91b76e3df32e133ad4bf37578be74d506f15b302b1a39d4ffb5d47`。 |
| 科学语义公平对照 | Strong Expert、Generic Semantic、Candidate 均为合法完成率/正确拒绝率/总体/holdout 100%，误拒与成功语义非法执行均为 0。 |
| Issue #8 成本 | 三种方法均 25 次工具调用、19 次状态查询；Candidate 未显示调用优势。 |
| 事件独立 oracle | 最大对齐误差 0.002625 秒，小于冻结容差 0.00390625 秒；只适用于当前合成条件。 |
| 扩展模拟 | 新 `epoch_variance` consumer 的方法特定修改点 Expert/Generic/Candidate 为 2/0/1；单开发者弱证据，不支持 H2 相对 Generic。 |
| Issue #8 全量测试 | `pip check`/`compileall` 通过；有 EDF/权重时 137 项中 134 通过、3 跳过；无私有资源 125 通过、12 跳过。 |
| Issue #8 决策 | 当前 EEG 专属规划排序为 NO-GO；显式科学语义契约只保留为工程机制，不宣称创新点一成立。 |
| Issue #9 冻结集 | 24 项（development/holdout 各 12），真实子集 12；规范化 SHA-256 `53c041d3…d5d4`。 |
| Issue #9 自然 DeepSeek | 12 项运行、11 项可评价、10/11 意图匹配；1 项真实未授权事件条件选择，0 项完整错误链全部成功；30 请求、57,065 tokens。 |
| Issue #9 冻结缺陷 | 1 项 0.6 秒事件窗违反现有工具的最短 1 秒条件；原结果保留并排除，不修改 gold。 |
| Issue #9 人工注入 | 5/5 被 Executor 接受且离线意图不一致；只证明边界，不计为自然模型错误。 |
| Issue #9 最小比较 | 两个 holdout × 三方法；Native 2/2、Strong Preflight 1/2、Intent Contract 2/2；6 请求、4,877 tokens。 |
| Issue #9 总预算 | 36 请求、61,942 tokens，未超过 36 请求/80k tokens；只传合成元数据与派生结果。 |
| Issue #9 决策 | 问题存在性 Conditional Go；当前方法 No-Go/证据不足，不宣称优于原生 Agent。 |
| Issue #9 全量回归 | `pip check`/`compileall` 通过；提供本地 EDF、权重和匿名 R3 样例时 146 项中 145 通过、1 项联网测试按设计跳过。 |

仓库内存在历史 TUEV Agent 与 oracle 汇总文件，但本轮未重新复现。相关数字仅在 `CODE_AUDIT.md` 作为历史产物记录，不作为当前基线实验结论。

### 本轮验证命令

在项目根目录设置 `PYTHONPATH=src`，并用环境变量 `EEG_HARNESS_TEST_EDF`、`EEG_HARNESS_MODEL_PATH` 指向原始 EEGAgent 中的现有 EDF 和权重后执行：

```powershell
& $python -m pip check
& $python -m compileall -q src tests
& $python -m unittest discover -s tests -v
& $python -m eeg_harness.cli --edf $env:EEG_HARNESS_TEST_EDF `
  --model $env:EEG_HARNESS_MODEL_PATH `
  --output artifacts\after_explicit_record.json
```

改造前结果保存在本地忽略目录 `artifacts/before_explicit_record.json`，改造后结果保存在 `artifacts/after_explicit_record.json`；两者仅用于本轮本地回归，没有进入 Git。比较时排除生成时间和运行耗时，确定性字段全部相同。

## Issue #10：工作点一集成方法初版

### 实际代码变更

- 新增 opt-in `research/integrated_method`：Evidence-bound `IntentSpec`、obligation ledger、计划/恢复校验、Evidence Gate 与最终证据回答。
- 复用 `StateAwareConstrainedPlanner`、`ConstrainedPlanRunner`、`ExecutionContext`、`Executor` 与现有工具；没有创建第二套 EEG Core 或执行器。
- `planning.py` 增加可选 plan validator hook，并将授权质量筛选实现为同一 Epoch artifact 上的“先质量证据、后筛选”。默认 native/planning 路径保持不变。
- CLI 新增 `--agent-mode point1`；Fake LLM 用于确定性回归，真实 OpenAI 兼容客户端用于合成 EEG 联网验收。
- follow-up 新增覆盖当前分析类型的科学概念契约：模型声明类型必须与用户原文 span 中的概念集合独立解析结果一致，不使用离线 gold。
- 新增质量证据→授权筛选→派生 Epoch→事件频带功率五工具链，Evidence Gate 校验两级 artifact lineage。
- 最终回答改为证据寻址：LLM 只选择成功 ToolResult 的 request id 与相对 `data` 的 JSON path，运行时解析实际标量并确定性渲染。

### 验证结果

| 项目 | 结果 |
|---|---|
| Fake 单步 | PSD 完成，1 次工具调用，ledger 与 trace 闭合。 |
| Fake 多步 | `list_events → create_epochs → event_bandpower` 完成，artifact lineage 闭合。 |
| 真实 DeepSeek 首轮 | 3/3 安全澄清、0 工具误执行；暴露任意参数 schema 导致的别名/任务类型漂移。 |
| 真实 DeepSeek 修复后 | PSD 与事件链完成；缺事件 label 正确澄清且 0 工具调用。 |
| 联网预算 | 两轮合计 8 请求、10,477 tokens；只使用合成 EEG 元数据和派生结果。 |
| 针对性回归 | 集成+规划 24/24 通过。 |
| 本地资源全回归 | 161 项中 160 通过、1 项联网 opt-in 测试跳过；`pip check`/`compileall` 通过。 |
| 无私有资源回归 | 161 项中 149 通过、12 项资源/联网测试按设计跳过。 |
| GitHub CI | Draft PR #11 run `39814383931` 的安装、compileall 与无资源 unittest 步骤均为 success。 |
| follow-up Fake | 集成方法与 Planner 定向 30/30；单步、事件和质量筛选后分析轨迹均按新回答协议生成。 |
| follow-up DeepSeek | 4 条不同合成请求、5 次执行，真实总消耗 9 次 Provider 请求、19,275 tokens（含首次失败 2 请求/4,925 tokens）；PSD 对抗及两条授权复杂链完成，禁止筛选请求 0 工具澄清。首次复杂链的错误 `data` 路径被安全阻止，接口说明修复后重测完成；其完整未跟踪 JSON 被覆盖，仓库仅保留明确标注的观测失败摘要，不伪造原始响应。 |
| follow-up 完整回归 | `pip check`/`compileall` 通过；167 项有资源测试除 1 项联网 opt-in 外均通过，R3 两项显式资源测试另行通过；无资源 155 通过、12 跳过。 |
| follow-up GitHub CI | Draft PR #11 run `39892152377` 对 `30ae956` 执行公开无资源 `unit-tests`，结论 `success`。 |

真实 LLM 的中文回答存在服务侧历史乱码，因此只确认结构化调用、工具执行和终止语义，不宣称中文可读性通过。方法当前是可运行候选，创新性和相对优势均未证明。完整报告见 `POINT1_INTEGRATION_ACCEPTANCE.md`，后续公平对照和消融见 `POINT1_FUTURE_EXPERIMENTS.md`。

### 本轮提交

- `cb91166`：研究问题、文献差异与方法蓝图。
- `9f55415`：CCEP 最小集成主干。
- `fbf20e6`：事件链、质量证据与受约束恢复。
- `c35b541`：真实模型 schema 失败修复与脱敏轨迹。
- `e1c1b03`：科学来源、数值证据、参数闭合和回答失败审查修复。
- 最终文档本地归档：`de6ac8e`、`d021eb2`。本机 HTTPS 传输中断后，六份最终文档通过受认证 GitHub Contents API 同步到 Draft PR #11，远端内容完整但 SHA 与本地归档不同；后续按状态文件的非强制 merge 步骤收敛历史。

## 未解决问题

1. 当前仅有 `tuev_bipolar_22` 与 `edf_native`；Sleep 2 导、MDD 19 导及完整 ERP/evoked 尚无已验证 Profile/工具。
2. `legacy/register_data.py` 文件仍为迁移来源保留，但正式 pipeline、工具和测试已不再依赖；尚未执行物理删除。
3. 当前 Registry 已避免枚举时加载权重，但尚无插件发现、资源 manifest 和跨进程模型生命周期管理。
4. 已使用 JSON Schema 风格声明和结构化 Tool Calling，但本地 schema 校验器仅覆盖当前 MVP 所需子集。
5. `reflectData` 返回 NumPy 数组，当前消息回注无法直接 JSON 序列化。
6. RAG 主模型权重缺失，报告模板也没有进入当前生效 Prompt。
7. MDD、Sleep、TUEV Agent 评估脚本与默认路径或返回结构不一致，不能直接作为回归测试。
8. 多数本地权重的训练数据、版本、许可证和指标来源在源码中未提供。
9. 已有 CI、四类 CLI、46 项测试和资源型 smoke test，但尚无跨平台锁文件、完整资源 manifest 或多样本回归集。
11. 本地真实 EDF 没有 annotation；事件能力仅在合成 MNE 数据上验证，未验证 EDF+ 或外部注释文件配对。
10. 原始项目没有发现许可证文件；源码和权重许可需在公开分发前确认。
11. R3 预处理与 Epoch 参数已配置化且可复现，但其科学适用性尚需实验方案确认。
12. 当前未包含坏道、伪迹剔除、ICA、evoked/ERP 峰值或统计推断；不得将频带结果解释为诊断证据。
13. 规划先导任务规模小，且 Expert 与 Planner 在所有静态任务上持平；当前证据不足以确认研究创新性。
14. 动态重规划优势只在一个人工状态变化案例出现，真实发生率、自然语言规划质量和更复杂任务扩展性未知。
15. v2 强 Expert 与 Planner 结果持平，当前不能把状态约束规划作为已成立的性能型创新点。
16. 冻结 v2 的 Profile 变化案例在注入前已静态不兼容；动态注入仅由独立回归测试覆盖，这是锁定留出集的已知缺陷。
17. 质量阈值未做跨设备、跨 Profile 或人工质控校准；真实文件结果对 100/200/500 µV 阈值敏感。
18. Evidence benchmark 在 Pilot 策略实现后、首次结果前冻结，不属于方法实现前预注册。
19. 强 Expert 与 Candidate 完全持平，研究点二当前为 No-Go；研究点一也尚未成立。
20. 真实 LLM 仅完成一次 4 案例合成验收；尚无多措辞重复试验、不同模型比较、长上下文、并发或故障率统计。
21. 本次没有通过真实 LLM 调用本地癫痫权重；已验证的是合成 Native 基础/事件工具与不兼容拒绝，不得外推为模型调度性能。
22. Baseline v1 已用合成 22 导输入让真实 DeepSeek 调度本地权重，但输出仅是协议 smoke；真实 LLM+真实 EEG 仍未授权、未验证。
23. 初始严格自然语言结果 3/15，说明多余工具调用仍是明确基线缺陷；5/5 修复结果只来自 development 复测。
24. Issue #8 三种强方法在全部冻结合成案例完全持平；当前无法证明 EEG 专属规划策略的独立贡献。
25. 18 个合成案例、单开发者扩展修改点和一次本地耗时不足以代表真实 workflow、团队维护成本或统计显著性。
26. 原型只覆盖 low-pass、联合重采样、Epoch/显式索引筛选等最小语义；未验证真实触发漂移、复杂参考、ICA、坏段传播或 BIDS derivative lineage。
27. Issue #9 仅观察到 1 个自然意图错误，且后续分析因窗口前提失败；没有“错误链全成功”的自然样本。
28. Stage C 只有 2 个 holdout、单次 DeepSeek 路由决策；词汇 alias 归一在结果后修正并已披露，不能作统计或泛化结论。
29. CCEP 只有单步 PSD、事件多步与缺参三类真实模型验收；没有新的冻结强基线比较，不能声称创新或优势。
30. 当前原文数值校验不支持中文数字、单位换算、范围共指或复杂多意图。
31. 默认 EEGRecord 没有 raw/processed 双分支；raw obligation 只能在来源未显式可观测时安全拒绝。
32. `deepseek-flash` 当前返回的中文文本存在乱码，结构化链路成功不能替代自然语言质量验收。
33. 科学概念契约尚未覆盖否定作用域、开放同义词、单位换算和多意图组合；“禁止筛选但做质量+功率”目前安全澄清，尚不能自动分解为合法替代计划。
34. 证据寻址回答保证数值和条件可追溯，但固定模板的可读性、跨值归纳与复杂科学表述尚未验证。
35. 概念词表、Prompt、schema 和 Validator 本身不是独立创新；CCEP 的潜在贡献仅是 obligation 在意图、派生状态、恢复和回答发布之间的持续保持，仍需公平强基线证据。

## 下一步候选任务

按优先级排列：

1. 按 `POINT1_FUTURE_EXPERIMENTS.md` 冻结全新任务、独立科学 oracle、强 Expert/Generic/Native 公平基线和统计计划，再评价 CCEP；不得围绕本轮三个验收请求添加特例。
2. 将自然语言解析共享实验与端到端实验分开，使用未见 holdout、多次重复、独立标注和不同模型。
3. 建立资源 manifest，记录权重 SHA-256、来源状态、输入契约和许可状态，并扩展 CI Python/平台矩阵。
4. 获取合法的带事件公开数据后建立真实事件回归；实验室真实数据外发必须先获得明确治理授权。
5. Sleep、MDD、ERP 和 ASD 继续后置，必须各自完成 Profile、资源、许可和验证后再接入。
6. 两个候选研究点当前均未成立；后续必须基于文献、独立数据和强基线重新论证，不因工程便利编造贡献。
7. 若重新评估研究点一，先获得独立开发者与真实复杂任务，在新冻结 holdout 上证明通用 semantic planner 无法表达的具体 EEG 差异。

## Git Commit 信息

- 正式项目已初始化本地 Git 仓库；相邻原始 EEGAgent 目录保持非 Git、未修改。
- 正式远程仓库：`https://github.com/lzy123-web/eeg-agent-harness.git`，远程名为 `origin`。
- 后续代码或项目文档变更须在验证后提交并推送；禁止提交密钥、真实 EEG 数据、大型模型权重、本地资源配置和生成产物，禁止未经授权强制推送。
- 代码基线 Commit：`9f235b8`（`建立最小 EEG 分析代码基线`）。
- 基线验证状态 Commit：`e962991`（`记录基线验证与提交信息`）。
- 显式数据链路 Commit：`9e48f99`（`引入显式 EEGRecord 数据链路`）。
- 阶段 A Commit：`4c07b20`（`实现 TaskProfile 与 EDF 数据适配`）。
- 阶段 B Commit：`a27b16c`（`建立工具注册与安全执行器`）。
- 阶段 C Commit：`1450179`（`实现可追踪多工具执行上下文`）。
- 阶段 D Commit：`d51de85`（`接入结构化工具调用 Agent Loop`）。
- 里程碑文档 Commit：`35cfa3e`（`完善基础运行时里程碑文档`）。
- Issue #1 阶段 A Commit：`ec65168`（`阶段A 加固测试基线与参数校验`）。
- Issue #1 阶段 B Commit：`b33ec14`（`阶段B 实现通用事件与Epoch数据层`）。
- Issue #1 阶段 C Commit：`cbcc2ed`（`阶段C 接入事件工具与多步执行`）。
- Issue #1 阶段 D Commit：`524946e`（`阶段D 完成多任务验收与事件Demo`）。
- Issue #2 阶段 A Commit：`f7f95da`（`阶段A 修复会话隔离与事件时间校验`）。
- Issue #2 阶段 B Commit：`812a899`（`阶段B 增加通用预处理与R3适配器`）。
- Issue #2 阶段 C Commit：`33244ed`（`阶段C 建立R3事件工作流与受试者聚合`）。
- Issue #2 阶段 D Commit：`c9af7aa`（`阶段D 完成R3真实事件验收与研究文档`）。
- Issue #2 状态汇总 Commit：`a154941`（`记录Issue 2阶段提交与验收结果`）。
- GitHub Actions run `39606303155` 对 `a154941` 执行无私有资源 compileall/unittest，结论为 `success`。
- Issue #3 阶段 A Commit：`c6a168e`（`阶段A 定义EEG状态与操作契约模型`）。
- Issue #3 阶段 B Commit：`a274e5c`（`阶段B 实现状态感知约束规划与有限重规划`）。
- Issue #3 阶段 C Commit：`ac75f7d`（`阶段C 建立冻结任务集与公平规划对照`）。
- Issue #3 阶段 D Commit：`04e2022`（`阶段D 完成规划演示评估与研究结论`）。
- Issue #4 阶段 A Commit：`f449a0a`（`research: establish fair planning evaluation protocol`）。
- Issue #4 阶段 B Commit：`8d126dd`（`feat: declare planning capabilities and evaluation faults`）。
- Issue #4 阶段 C Commit：`569d288`（`feat: bridge natural language goals to constrained plans`）。
- Issue #4 阶段 D Commit：`c39e847`（`eval: run locked planning and fake language comparisons`）。
- Issue #4 契约复核 Commit：`be0522c`（`refactor: apply artifact contract in expert preflight`）。
- Issue #5 阶段 A Commit：`90569f1`（`feat: establish measurable EEG quality evidence`）。
- Issue #5 阶段 B Commit：`82ea91a`（`feat: add evidence-driven adaptive analysis pilot`）。
- Issue #5 评测冻结 Commit：`79c869f`（`research: freeze evidence benchmark before evaluation`）。
- Issue #5 阶段 C Commit：`4131914`（`eval: compare adaptive evidence policy with strong baselines`）。
- Issue #5 阶段 D Commit：`06a0362`（`docs: conclude evidence adaptive pilot with No-Go`）。
- Issue #6 阶段 A Commit：`f554d68`（`feat: harden real LLM protocol client`）。
- Issue #6 阶段 B Commit：`e155fc5`（`feat: add synthetic real-agent execution path`）。
- Issue #6 阶段 C Commit：`06c8cbe`（`test: validate real DeepSeek EEG tool loops`）。
- Issue #6 阶段 D Commit：`750eb04`（`docs: complete real DeepSeek baseline acceptance`）。
- Issue #7 阶段 A Commit：`e320d3c`（`research: freeze Baseline v1 acceptance scope`）。
- Issue #7 阶段 B Commit：`a8eefd7`（`feat: add frozen Baseline v1 Agent runner`）。
- Issue #7 阶段 C Commit：`44ab04a`（`test: verify Baseline v1 local EEG resource chains`）。
- Issue #7 阶段 D Commit：`9ffb7fd`（`eval: run frozen real DeepSeek Baseline v1 subset`）。
- Issue #7 阶段 E Commit：`ac36b45`（`release: accept EEG Agent Baseline v1.0`）。
- Issue #7 状态补记 Commit：`7c852da`（`docs: record Baseline v1 stage commits`）；GitHub Actions run `39787839835` 成功。
- Issue #8 阶段 A Commit：`f14d20a`（`research: freeze EEG semantic planning protocol`）。
- Issue #8 阶段 B Commit：`c2870eb`（`feat: prototype EEG scientific semantic planning`）。
- Issue #8 阶段 C Commit：`93516be`（`eval: compare semantic planner with fair strong baselines`）。
- Issue #8 阶段 D Commit：`0be719a`（`docs: conclude semantic planning spike with No-Go`）。
- Issue #8 GitHub Actions run `39801900191` 对阶段 D 提交 `0be719a` 执行无私有资源回归，结论为 `success`。
- Issue #9 阶段 A Commit：`2cf441c`（`research: freeze intent-alignment problem and cases`）。
- Issue #9 阶段 B Commit：`57a2b4d`（`eval: run real DeepSeek intent-alignment pilot`）。
- Issue #9 阶段 C Commit：`631b9b5`（`research: compare minimal intent contract on holdout`）。
- Issue #9 阶段 D Commit：`84ed297`（`docs: conclude intent-alignment study objectively`）。
- Issue #10 follow-up 历史收敛：`1bd8e7c`（普通 merge，无文件差异）、`f041146`（记录恢复完成）。
- Issue #10 follow-up 意图类型一致性：`ceabfc4`。
- Issue #10 follow-up 派生质量状态链：`8796c82`。
- Issue #10 follow-up 证据寻址回答：`339aab5`。
- Issue #10 follow-up Fake/真实验证与交付：`3866818`。
- Issue #10 follow-up 失败证据留痕：`1d0d392`。

## Issue #12：CCEP Evidence Phase（2026-10-23）

### 已完成

- 增加独立合成异常 Epoch 真值与 SciPy Welch oracle，通过真实 Registry/Executor 验证筛选前后波形、试次数、artifact 不变性和全部频带值。
- 将固定复合事件类型收敛为 `event_workflow` 与三个原子目标，支持“测质量但禁止筛选，再计算未筛选功率”和“明确授权筛选后计算功率”。
- 冻结 24 项（12 development / 12 holdout）独立协议、权限、oracle、预算和规范化 SHA-256，再运行公平比较。
- 保存共享解析任务对照和两个真实 DeepSeek holdout 的脱敏逐例结果；失败结果没有删除或用于事后调 Prompt。
- 新增研究报告 `POINT1_EVIDENCE_PHASE_RESULTS.md` 与方法决策 `POINT1_METHOD_DECISION.md`。

### 实际验证

| 检查 | 结果 |
|---|---|
| 独立 Epoch oracle | 异常索引 `[1]`；3→2；原 artifact 未变；派生波形逐样本相等；筛选前后全部频带与独立 oracle 一致 |
| 全部异常 | `TOOL_EXECUTION_FAILED`；无空派生 artifact；后续功率不执行 |
| 定向 Evidence Phase | 10/10 通过 |
| 冻结共享任务 | Strong 18/18、CCEP 18/18；科学完成均 10/10；各 55 工具调用、2 重规划 |
| 真实 DeepSeek holdout | Native 2/2；CCEP 1/2；13 请求、34,263 tokens；仅合成 EEG |
| CCEP Evidence Gate | 禁止筛选例通过；授权筛选例在意图层安全澄清，0 工具、无数值发布 |
| 有本地 EDF/权重回归 | `pip check`、`compileall` 通过；180 项中 177 通过、3 项按设计跳过 |
| 无私有资源回归 | 180 项中 168 通过、12 项按设计跳过 |
| GitHub CI | Draft PR #11 run `39906771336` 对 `2d5d9cf` 的公开无资源 `unit-tests` 成功 |

### 研究判断与遗留问题

- CCEP v0 的跨意图、计划、派生状态、恢复和回答 obligation 是实际运行机制，不是单一 Prompt；但本轮没有发现相对同规则强专家的增量收益。
- 真实小样本中 CCEP 因意图 schema 服从问题误拒一例，完成率未超过 Native。当前“CCEP 优于强基线”结论为 **No-Go**；作为 opt-in 安全骨架为 **Conditional Keep**。
- 质量阈值仍未临床校准；真实 LLM 只有两个 holdout；Native 最终回答只做逐例人工数值审核；不能外推真实 EEG、临床或多数据集能力。
- 下一入口应是预先提出并冻结“一次性 preflight 会因执行中状态变化/恢复失效”的动态假设，不再围绕本次 holdout 堆 Prompt 或 validator。

### 本轮提交

- `f5283cb`：真实 Epoch 筛选与独立 oracle。
- `caed65d`：事件原子目标组合。
- `06ab4e9`：冻结 Evidence Phase 协议。
- `aa6b20a`：共享任务公平比较。
- `b705638`：真实 DeepSeek holdout。
- 最终文档与状态提交：`2d5d9cf`；GitHub Actions run `39906771336` 成功。

## Issue #13：CCEP v1 动态科学状态与增量约束规划（2026-10-23）

### 方法与实现

- 比较 partial replanning、scientific-state residual goals、guarded conditional DAG 与 LLM feedback replanning 后，选择 LRSP；guarded DAG 保留为未来强动态基线。
- 新增 opt-in `ConstraintCarryingEEGAgentV1`，冻结一次 Intent/ledger，每轮只从实际 artifact、质量 evidence、每条件计数和剩余目标生成一个 frontier action。
- clean 数据走 identity transition；实际异常且用户授权时才创建派生 Epoch；任一请求条件无 usable Epoch 时在选择前安全停止；禁止筛选时分析原 artifact。
- transient failure 只重试当前 frontier，保留已经有效的事件、Epoch、质量和选择结果。
- `EpochSet` 新增内容 fingerprint；质量 evidence 绑定 artifact ID/fingerprint/阈值；下游工具可检查 expected fingerprint/evidence ID。
- 最终回答在 LLM evidence path 校验后，由运行时确定性披露 derived/identity/no-selection 分支与经验阈值边界。

### 实际验证

| 检查 | 结果 |
|---|---|
| 独立 oracle | one-bad 场景实际 3→2；派生数组逐样本一致；全部通道/频带值与独立 SciPy oracle 一致 |
| 状态分支 | one-bad=`derived`；clean=`identity` 且无伪 artifact；禁止筛选=原 artifact；all-bad=质量后安全停止 |
| residual recovery | 一次受控 bandpower transient：list/create/quality/select 各 1 次，bandpower 2 次，完成 |
| 初版失败探针 | 同 ID 内容改变后仍执行 `select_quality`，`detected=false`；结果已保留在迭代日志 |
| 修订后 | 同一探针回到 `measure_quality`；过期 evidence ID 被结构化拒绝 |
| Fake 固定三例 | 3/3 completed，6 次协议调用，完整轨迹已保存 |
| 真实 DeepSeek 固定三例 | 3/3 completed，6 请求、15,363 tokens；仅合成 EEG；不外推准确率 |
| 全仓无私有资源回归 | 190 tests：178 passed、12 resource-gated skipped；0 failed |
| 敏感信息检查 | v1 代码、文档与结果未发现密钥、本地私密路径或原始 EEG 数组 |
| GitHub CI | `unit-tests` run `39926245053` 对提交 `7e0ac46` 完成，结论 `success` |

### 研究判断与遗留问题

- LRSP 已经是实际运行机制，不是单一 Prompt：工具状态会改变动作，内容 lineage 会撤销旧完成项，恢复不重放无关步骤。
- guarded dynamic Expert 能表达当前同类分支，因此本轮没有证明 CCEP v1 的相对优势或新颖性。当前为“可运行研究候选 / 创新性未证实”。
- 动态语义仅覆盖事件质量、选择和绝对频带功率；阈值未临床校准；artifact store 无跨进程事务；检查后并发变化目前安全失败但不自动恢复。
- 下一步只能在预冻结同信息、同规则、同预算的 guarded Expert/Native/LRSP 协议上比较，并将语言解析错误与运行时规划错误分开。

### 本轮提交

- `b85eef2`：冻结研究设计与恢复状态。
- `d96c764`：接入 LRSP、Fake/oracle/局部恢复测试。
- `36c4adf`：内容 fingerprint、quality evidence binding 与回答条件修订。
- `df334d1`：固定 Fake/真实 DeepSeek 合成轨迹与有界评估入口。
- 最终审查与文档提交：`347bc0d`。
- 状态留痕提交：`7e0ac46`；GitHub Actions run `39926245053` 成功。

## Issue #14：CCEP/LRSP v1.1 契约索引证据依赖图（2026-10-23）

### 方法与实现

- 审计 LRSP v1 固定 Epoch 流程，比较过程式扩展、完整动态 plan repair 和契约索引依赖图，选择 CIEDG。
- 新增 opt-in `ConstraintCarryingEEGAgentV11`；从请求目标生成依赖闭包，使用绑定 artifact fingerprint、参数和上游 token 的 `GoalEvidence` 管理完成与失效。
- `epoch_summary` 与 `event_bandpower` 成为两个共享 effective Epoch 的 consumer；禁止筛选、identity、derived 和多条件零 usable 均由真实状态决定。
- 原型暴露“内容相同的 artifact 重建导致 summary 重放”；修订后增加仅限纯 consumer 的 semantic evidence cache，内容变化反例不会错误复用。
- 新增同规则过程式 strong expert 与 fingerprint 微基准，只作为小型诊断，不冒充正式对比实验。

### 实际验证

| 检查 | 结果 |
|---|---|
| 双 consumer + 独立 oracle | selected Epoch 3→2；summary 与 bandpower 共用同一 artifact；波形和全部频带值一致 |
| 禁止筛选 | 测量质量后两个 consumer 均使用 original 3 Epoch；未调用筛选 |
| 多条件零 usable | `NO_USABLE_EPOCHS_FOR_CONDITION`；筛选与下游 consumer 均未执行 |
| 内容等价 repair | selection 2 次；summary 从原型 2 次降为 1 次；任务完成 |
| 内容改变 repair | cache miss；create/summary 均重算，未发布陈旧证据 |
| 强 Expert 小诊断 | 相同 6 次调用、相同试次数与频带数值；未观察候选优势 |
| Fake 固定三例 | 3/3 completed，6 次协议调用 |
| 真实 DeepSeek 固定三例 | 3/3 completed，6 请求、18,253 tokens；Evidence Gate/answer check 均通过；仅合成 EEG |
| 全仓回归 | `compileall`、`pip check` 通过；199 tests：187 passed、12 gated skipped、0 failed |
| GitHub CI | Draft PR #11 `unit-tests` run `39930738446` 对 `53b5869` 完成，结论 `success` |

### 研究判断与遗留问题

- CIEDG 是真实运行时机制，不是只加 Prompt/Schema；它将科学目标、状态版本、证据依赖与局部恢复连接起来。
- 当前结论为 **Conditional Keep / 创新性未证实**。强 Expert 无故障诊断持平，不能宣称成功率、成本或科学正确性优势。
- 尚未冻结强动态 Expert 的故障恢复正式套件；quality evidence ID 含随机 artifact ID；当前只有 event Epoch 状态族和两个 consumer；全数组 fingerprint 的大规模成本未知。
- 尚不具备直接进入正式大规模公平实验的条件。下一入口是冻结独立协议、实现同恢复预算强 Expert、分层指标，并增加一个不同且科学合法的状态转移族。

### 本轮提交

- `037d2c1`：方法审计、候选比较与设计冻结。
- `c11bb95`：CIEDG 原型、双 consumer 与真实 Agent 集成。
- `ea497ac`：内容寻址 evidence 恢复、反例、多条件与 strong expert 诊断。
- 阶段 D 交付提交：`df59826`（有界 Fake/DeepSeek、完整回归与研究判断）。
- 状态留痕提交：`53b5869`；Issue #14 与 Draft PR #11 已评论，CI run `39930738446` 成功。

## Issue #15：CIEDG 第二科学状态转换与方法冻结（2026-10-23）

### 实现与算法迭代

- 比较显式重参考、重采样、基线校正和 CSD 后，选择“用户授权的显式 Epoch 参考通道减法”；仅开放给 `edf_native`，不默认 average reference，不触碰已验证 TUEV 双极模型链。
- `EpochSet.reference` 进入内容 fingerprint；新增惰性、真实 Registry/Executor 工具 `rereference_epochs`，保持 shape、sfreq、通道顺序和事件，改变信号、reference、identity 与 fingerprint。
- transfer Agent 复用 CIEDG goal/role/transition graph；质量、summary、bandpower 绑定 current effective Epoch。
- 受控 artifact 丢失暴露“内容等价但来源身份不同”问题：修订为不可变历史 ToolResult + 当前谱系 release view；质量证据重算，纯 summary consumer 可语义复用。
- 真实 DeepSeek 首次回答引用非标量对象，被 Evidence Gate 拒绝；新增通用 scalar evidence manifest 后一次 development case 复测通过。该项明确归为工程可靠性，不作为研究贡献。

### 实际验证

| 检查 | 结果 |
|---|---|
| 独立科学 oracle | NumPy 逐元素一致；MNE 最大绝对差约 `2.91e-11`（容差 `5e-11`） |
| 属性变化 | shape/sfreq/events/window 保持；reference/data/fingerprint 改变；单参考通道为零 |
| 结构化拒绝 | 缺通道、过期 fingerprint、不兼容 Profile、缺授权/缺参数均拒绝或澄清 |
| 最小恢复 | list/create 各 1；rereference/quality/bandpower 各 2；summary 执行 1 次并安全发布到新谱系 |
| 强动态 Expert | 正常与 artifact 丢失两例：调用序列及科学输出持平，无候选优势 |
| Fake calibration | 2/2 completed，science signature 2/2 相同；非正式实验 |
| 首次真实 DeepSeek | 2 例工具链成功、0/2 回答发布；4 请求、13,038 tokens；失败保留 |
| 修订后真实 DeepSeek | 1 个 development 正常例 completed、answer valid、与 Expert 相同；2 请求、7,641 tokens |
| 联网总预算 | 6 请求、20,679 tokens；仅 synthetic EEG，无波形外发 |
| 完整回归 | compileall、pip check 通过；210 tests：198 passed、12 resource-gated skipped、0 failed |
| 正式协议 | 24 例冻结（selection/rereference 各 12；development 8、holdout 16），尚未执行 |

### 研究判断与遗留问题

- 决策为 **Freeze / 进入正式公平实验，创新性与优势未证实**。第二 transformation family 证明机制有限迁移可行，但不证明比强 Expert 更好。
- 候选论文机制是 EEG 科学属性/角色索引的目标—证据依赖、内容/身份分离、失效和局部恢复；重参考工具、Prompt/Schema、scalar manifest 属于工程实现。
- 暂不支持重参考与筛选组合、转换前后双分支、自动参考选择、TUEV 重参考或真实数据泛化；经验质量阈值对参考通道 flatline 的解释仍需在正式报告中披露。
- 下一步只执行 `config/point1_formal_eval_protocol_v1.json` 的公平比较与消融；不新增第三种状态转换来追逐优势。

### 本轮提交

- `a5dacf8`：候选转换比较与迁移设计。
- `6bc4df2`：真实重参考、CIEDG transfer 与 provenance 修复。
- `953a8b5`：同规则强动态 Expert、Fake calibration 与冻结协议。
- `3306e94`：真实 DeepSeek 失败保留、标量 evidence 地址修复与有界复测。
- `81aecd7`：最终审查、冻结决策和 README；GitHub Actions `unit-tests` run `39959623831` 成功。

## Issue #16：CIEDG 正式公平实验（2026-10-24）

### 冻结协议与实现

- Candidate 固定为 `921b04a561b27c2e68964d5f3f1e995ee08c8c6d`；本轮没有修改 CIEDG、Planner、EEG 状态转换或 scientific gold。
- 在原 24 个登记 ID 上补齐自然语言请求、合成 EEG fixture、故障、合法终止、必需/禁止工具和科学不变量；supplement SHA-256 为 `43e7fb634ff1eb246e2685a0831bf28c3bf08bed05f481bb36a8ebc5e45d49f2`。
- 新增独立 fixture/oracle/scorer、同规则 Strong Dynamic Expert、四个预登记消融、append-only invariant audit 和真实 LLM audit。
- holdout 打开后的 evaluator 缺陷不回写原始结果；所有原始 trace、失败与追加审计均保留。

### 实际结果

| 检查 | 结果 |
|---|---|
| 24 场景主评分 | CIEDG 24/24、Strong Expert 24/24；均 109 次工具调用 |
| Whole-plan replay | 24/24，121 次调用；比 CIEDG 多 12 次 |
| 无 dependency invalidation | 24/24，112 次调用 |
| 无 semantic evidence reuse | 24/24，112 次调用 |
| 无 EEG scientific guards | 20/24；4 个未经授权/范围不明转换 |
| 协议追加审计 | S09 未形成 equal effective fingerprint，标为 protocol-invalid；其余有效 holdout CIEDG/Expert 均 15/15 invariant 通过 |
| 真实 DeepSeek 子集 | 4 场景 × CIEDG/Native；22 requests、59,515 tokens；追加审计后 CIEDG 1/4、Native 0/4 |
| 数据隐私 | 仅确定性合成 EEG；不发送波形，不保存密钥/认证头/本地密钥路径 |
| 完整回归 | `compileall`、`pip check` 通过；221 tests：209 passed、12 resource-gated skipped、0 failed |
| GitHub CI | `unit-tests` run `40053581867` 对提交 `a326837` 完成，结论 `success` |

### 失败分类

- Intent：CIEDG S02/S06 对模型多报 unknown slots 采取 fail-closed 澄清；Native S02 未识别已有筛选授权。
- Planning/scientific state：Native S06 静默丢失零 usable 的 control 条件。
- Recovery：Native R11 未从 `ARTIFACT_NOT_FOUND` 恢复。
- Answer evidence：CIEDG R11 工具链完成但 evidence-answer schema 校验失败；Native R05/R11 含无证据或与失败状态矛盾的陈述。
- Protocol：S09 只能证明 source 等价，不能证明 selection effective artifact 等价。

### 研究判断与遗留问题

- CIEDG 的 guard、依赖失效、内容/身份分离与局部恢复是实际运行机制；但与同规则强专家完全持平，创新性不能用成功率优势表述。
- 论文可有限主张“可审计 EEG 科学状态—证据依赖与有界恢复”；若论文要求显著优于强 Expert，则本次是 No-Go。
- 当前不再新增状态转换或 Planner。后续只允许预注册复现、统计功效扩展、真实数据本地验证和论文写作。
- 真实 LLM 意图与答案边界尚不稳定；不能用 Fake 或 parsed-task 结果替代端到端成功。

### 本轮提交

- `6661b65`：冻结 24 场景可执行 supplement 与运行手册。
- `ffe9ee3`：锁定 development evaluator、Expert 与消融结果。
- `c880676`：唯一完整 holdout、append-only invariant audit、真实 DeepSeek 原始结果与追加审计。
- `743894f`：正式结果报告、逐例失败分析、Conditional-Go 决策、README 与状态更新。
- `a326837`：最终实验状态与提交索引；GitHub Actions run `40053581867` 成功。
