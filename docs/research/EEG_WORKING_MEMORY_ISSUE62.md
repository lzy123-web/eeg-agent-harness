# Issue62：科学操作表达与证据责任边界

## 阶段、许可与事实起点

承接ba191f677c92e2788ce21defe9d3ec59ce214ef8，本地/远端一致、工作区干净、无实验进程或锁；沿research/point1-eeg-task-memory和Draft PR37。已阅读AGENTS、PROJECT_STATUS、Issue58–61架构报告及原始失败，尤其Issue61续作最终v2的实际请求、响应、工具结果与送达答案。阶段scope point1-operation-simplification-20261104，范围许可issue62-simplification-existing-sixth-20261104，[实际用户许可回执6631733161](https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6631733161)。不新增第七资金，不修改旧scope冻结/历史/未知占用。

账本起点558次/7594716guard tokens/保守$2.4579504，剩91/1734074/阶段$1.2837623；无活动保护或未结。第六资金固定409/5328790/$1.7417127不变。新scope最多两候选，初始T05一次诊断，最多一次有新真实根因的科学修正；未改版的诊断可计最终覆盖，改版后原四题同版各一次。最终顺序T05→T07→M01→M02，原续轮停止规则和每轮12请求等限制不变。72次/1.2M tokens/$0.5是规划预留，不是保证四会话均可用满96次；逐请求保护未覆盖会话各18次/300k/$0.125，达到真实预算边界走原最终租约/停止，不能写成普通科学失败。原确认池禁用、503仍累计1/8、不重置。

## 原始复现与职责归因

原Issue61最终原生响应不改、真实Agent/Store/Executor重放：T05 completed/no_progress（旧结果2项）、T07首轮no_progress（0项、续轮本来未发送）、M01 completed/no_progress（旧结果1项）、M02 completed/completed（2项）。改后重放停止/实际结果相同，不把接口迁移后正确手写提案冒充原模型成功。原文件hash、schema和wire及分层快照保留于[evidence/issue62_operation_simplification.json](evidence/issue62_operation_simplification.json)。

T05反复替换整对象source_ref与range_ref，新窗与未变通道的来源纠缠；现行最优A路径仅给range_ref其实合法，故不是没有合法操作。M01没有选择revise_plan是独立操作选择责任，不能自动按名称/自然词改新建为修订。T07已经有Epoch生产者，卡在每交付行重复task goal且字符串不同；这次不是原Issue61漏生产者。M02为合法独立新建且原结果复用的成功反例，不能为了促修订破坏它。

## 四类边界与方案选择

| 边界 | 本阶段分工 |
|---|---|
| 模型必须选择 | 新建/修订/追加，task_id/key/revision，变化字段和值，当前完整来源；比较左右真实标量field与版本/方向 |
| 程序确定保持 | 显式选中交付的未变record/capability/scope/解释及原来源；从实际变化字段路由证据，统一进入原完整候选事务 |
| 歧义不能猜 | 缺来源、错对象/时基、不同子句不能组合的端点、过期实际引用；复杂字段关系用公开interpretation，不隐式生成channel_reference |
| 目标层级 | task_goals仅每task一次任务标题；交付的科学目标由capability/scope/input_refs或left/right表达。标题不授权科学条件、不选修订身份 |

A为当前表示加同质量必要反馈/安全修正；B为原revise_plan的最小delta增加change_source，程序路由变化字段的来源，任务标题与交付行分离。比较过新操作DSL/自动意图重写，因重复状态/语义猜测而放弃。选择窄B，保留旧完整interpretation及canonical/flat旧输入的兼容核验；不新增Planner/Executor/Store/修复Agent/资金平台。

B使用task_id/output_key/revision/reason和scope中变化字段，加当前change_source；仅时间变化置range_ref且保留旧source，非时间对象变化置source并沿既有实际结果规则核验未变窗口，两者变化必须有可归属当前完整来源。waveform的显式channels变化机械同步measurement_channels，不猜通道；旧跨对象channel_reference不能默默当成新对象关系，需公开interpretation。change_source与interpretation不能混用；没有已验证解释时不伪造事实。不变事实来源可以是合法历史用户事实，不必假装已有实际结果；显式过期结果InputRef仍拒绝。

新建默认schema不再在每行暴露goal，task_goals可选且每身份一次；未写标题用显式task_id作为展示标题，不能用其名称推断科学。旧行goal兼容，但冲突定位具体两行；旧行goal与新task_goals混用时拒绝旧行字段，不提示删除公开合法task_goals。数值动作不能改解释，恢复反馈指公开revise_plan的目标及interpretation.channel_reference。比较仍left/right明确真实字段，不默认RMS/alpha，不改变原差比方向和评分。

## 首次反证、修正与安全门

独立首版审查发现旧A和新B共同的安全缺口：旧连续C1测量选当前事件相对4–6秒作为改窗来源，会修订并实际执行absolute PSD。首次观察为摘要，随后捕获完整A/B原提案/返回，区分记录，不伪称首次完整原件。修正位于共享interpreted_sources：历史对象不能把当前range parent重新解释成自己的对象/时间family；依据既有SourceFrame完整/相邻对象归属核验，而非句式、事件名、窗口特判。A/B同时拒绝且图/Store不变，反向event借continuous范围也拒；合法分句混合来源与事件修改继续通过。

同句混合对象仍可能被窄delta保守拒绝；显式当前完整interpretation的合法路径仍在。这是已知表达边界，不声称全面自然语言字段继承。独立还发现混合goal迁移时误报task_goals不支持，已关闭。其后17项独立测试通过，报告source 2a97b154b322412adb3234e08b24fcafafbea62dfe3ae78b1b621147920937e1、behavior 2bb189a19d4c2c6e1ddcba822abd675ed60d50e52695734d4d961214250e3c2b；非主审、无研究API/正式账本修改。

执行者首次专项有2个旧schema断言未迁移（不涉及原实验评分）；事件测试错误读取artifact_id位置，及把仅继承合法用户来源误当使用过期结果，均保留首次失败。后者改为显式过期InputRef反例，未增加无依据拒绝规则。新10项科学测试覆盖六组实际连续修订、事件artifact新旧保留及消费者失效、双变化、缺/错来源、错误channel/字段/版本/目标、误混来源、pending用户事实、不合法实际引用、goal冲突和数值动作恢复路径。原科学安全/循环/比较字段/重复计算等回归继承并重跑。

## 公平比较与成本取舍

A/B使用相同事实、反馈、Agent/Store/Executor、真实数值工具和六组权限。12条A与12条B受控链均实际修订计算，故意不执行比较、以partial结束；不是完整原任务成功。每个都一次计划修订写入，T05写入JSON A249/B234字节，M01 A278/B226字节（包含工具名/理由，相同计量）。这是最优合法A对B，不拿原模型冗长错误提案冒充公平基线。

模型少选source_ref/range_ref角色、无需重述旧time_reference或measurement_channels；字段和值仍显式。总工具schema从35365增至36176字节（+811），不是全面缩小；对复杂对象保留公开完整解释的代价、task_goals可选元数据和兼容路径均计入。消息/实际tokens、调用/费用及是否自主触发新分支必须由后续真实运行评价，不能由15/52字节的受控差异宣称有效性。

原24链111/111、六组兼容/默认各78/78、旧保存点六组24链通过；历史受控13/16次超过原单轮限制的情形仍只作机制证据。临时TEST账本3项和旧scope4项通过：幂等、6资金链、前缀、旧冻结、未结/stop、Fake两轮/租约/结算、防重抽、72预留与91累计范围上限。初版全量840项通过（15既有跳过）；最终全量在安全修复后独立执行，结果追加下文。compileall/pip check/diff check通过，正式调用尚未开始。

## 无凭据公开复现

```powershell
$env:PYTHONPATH='src;tests'
python -m unittest test_issue62_simplification test_issue62_scope -v
python -m eeg_harness.research.working_memory_issue62 --variant original --output artifacts/issue62-original-new.json
python -m eeg_harness.research.working_memory_issue62 --variant A --arm all --output artifacts/issue62-A-new.json
python -m eeg_harness.research.working_memory_issue62 --variant B --arm all --output artifacts/issue62-B-new.json
python -m unittest discover -s tests -q
```

真实准入仍原working_memory_issue61_live，新增scope policy而非另建预算系统。明确--scope point1-operation-simplification-20261104承接新范围，原客户端/唯一账本/费率/模型/最终租约及恢复规则保留；不探测服务或搜索凭据。后续真实结果、成本、自审及未参与实时执行者只读复核在此集中报告追加，不改原历史评分。Issue开放、PR草稿，等待主审。

最终首版工程门：846项=831通过+15既有跳过，13项本阶段科学/TEST专项与17项独立只读门通过；source2a97b154、behavior2bb189a1与复核一致。全量含共享时基修正，原24链及六组回归通过，编译/依赖/差异检查通过。真实运行将冻结本实现提交，后续只按许可一次T05诊断，不以离线门宣称自主成功。
