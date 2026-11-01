## 本文后续状态（2026-11-01）

下文是1bb3d6c职责收敛时的完整记录。随后已恢复服务并完成48次真实开发，当前配置/累计账本不再未知；原T04一次自主复查通过，T07失败，T03/T05未完成跨轮。开发次数耗尽、确认未准入。全部后续小范围修订、702项最终回归、费用及失败见[真实接续结果](EEG_WORKING_MEMORY_ISSUE55_HISTORY_AND_LIVE.md)。不删除下文原语义安全反证或将受控结果改称自主成功。

# Issue55 职责收敛设计与验证

2026-11-01，续接评论6553986150；起点fd78394。开始时工作区干净、fetch后本地/远端相同，未启动其他实验进程。首次完整反例保存在 `artifacts/point1_task_memory/issue55/responsibility-first-reproduction.json`：四臂合法事件切段0次，错误连续幅值1次；record_info/list_events各触发错误stage safety_stop。不是隔离函数结果冒充全链。

## 实施前最小设计

过去两次把“通道是否出现/最近对象”当时基解释，导致对称回归；把模型解释当全部事实或要求字面证明全部意图都不可行。本次不增加词表或解析器。采用现有 DeliveryItem 的可选 interpretation：完整父句、明确时间基准、测量通道与字段引用。Planner承担可审查的解释；源值存在、完整父句、目标记录、元数据、窗口成对、工具时基、工件/版本由共享Store核验。混合对象且没有解释时不再猜测角色；已有单一对象字面路径及合法历史引用保留。结构化解释不是模型正确理解自然语言的证明，须在证据中标明。

原 channel_reference 收敛为解释中的字段关系（保留旧动作接口兼容定位），允许目标省略通道名，但要求唯一明确的源字段、完整目标父句/独立窗口/元数据兼容、无显式目标选择冲突。引用关系语义由Planner解释，程序不再要求用户重复逐字命名，也不宣称唯一候选证明自然语言指代。没有解释的裸关系不充当事实。拒绝提案不写准入缓存。

执行前与归档复用同一解释和已验证scope；数值仍由原Executor产生，下游按真实工件/版本读取。辅助操作沿用原工具契约和来源验证；运行器科学停机只检查实际来源/绑定/时基/数值不变量，独立gold只检查原请求交付与遗漏，不作为工具白名单。保留额外合法观察和中间产物的原始轨迹。

计量复用现有wire预约、journal和final lease，新增每笔预约固定计价依据；恢复只用该笔模型/输入输出费率，缺历史依据维持保守占用并阻止新付费。异常模型即使usage合法也不释放预约。实际生效端点身份、model/返回版本、thinking/timeout/max_tokens/retries及源码/数据/评分进入冻结；凭据不入日志。

替代方案：继续修词序会重复对称回归；把gold当路线权限会阻断合法探索；完全放开参数则失去可确定安全边界；另建NLU/账务平台超出范围。所选方案是现有表示、共享核验和原运行器的职责调整，不宣称候选方法独占收益。后续记录实现、首次失败、修订与实际结果，不修改原题或评分。

## 已实现：一份解释、三种职责

`DeliveryItem.interpretation` 是现有交付表示的可选字段，包含原文完整父句、现有工具采用的 time_reference，以及可选 measurement_channels、range_span 和 channel_reference。分析对象仍由原 record/scope/InputRef/工件表示，通道是可组合的测量维度，不因出现位置改变对象或时基。没有新任务本体、Planner、Executor、状态仓库或自然语言解析器。

1. **Planner 解释**：TaskPlanEEGAgent 从原请求提出解释和字段关系。上下文中的原文索引只报告字面元数据，不预先猜测 scientific family。执行动作沿用所选交付的同一解释，不能暗中覆盖；修订走原计划接口。
2. **Store 确定核验**：检查完整且唯一的父句、目标记录、实际通道/事件、成对窗口数值与原文定位、工具时基以及原有工件/fingerprint/版本。源值不存在、父句裁剪、错误记录、目标冲突、错误时基和虚构窗仍阻止执行/准入。来源证据同时标记 `model_interpretation_not_intent_proof` 和已核验事实；解释不会被记成“程序已证明原文意图”。缺窗保留原 MISSING_SCIENTIFIC_PARAMETER 和续接契约。
3. **独立评价**：live 逐轮按照未修改的原请求 gold 检查必要结果/遗漏，保留接受的回答、原始 journal 和证据快照。模型完成自己提出的 DAG 不等于原请求完成；whole_request_correct 仍需回答审查，数值正确不能代填它。

字段关系只归一化通道名：目标记录、目标窗、时基、工件/版本分别核验；源多候选、目标缺通道、显式目标选择冲突、借用源窗均拒绝。原 T04 的“同名通道”不再要求再次逐字命名；这是 Planner 可解释且事实一致的省略关系，不是用户额外确认。原裸 channel_reference 接口保留兼容，但不能绕过解释边界。

调度仍用 PlanGraph 与原独立分支、缺参续接、局部修订；交付复用还核对解释时基与实际 evidence。真实工具经原 Executor 产出 TaskEntry/工件，分层记忆继续用原 presented/expected/used/use_attempt 和版本化档案读取，未创建第二份科学真值。A/B/C/A-equivalent 共用修复，不把共享底座改善记作 C 独有收益。

## 前后证据及明确代价

下表主审两句均为原 Agent/Store/Executor 完整链；“执行”指实际进入工具计算。修复后受控提供合理解释，不是让真实模型自主产生解释，不能声称动作输入完全没变。

| 材料 | fd78394 首次结果/历史 | 本轮结果 |
| --- | --- | --- |
| 事件对象中通道在窗口前：stimulus/SYNTH-C2/事件相对0–1.25秒 | 四臂合法 create_epochs 各0次，错误 amplitude 各1次 | 同一合理 event_relative 解释下合法各1次、错工具各0次；通道移到窗后及更名/换窗也通过 |
| 先查看事件信息并计算 SYNTH-C1 在2–4秒 RMS | 上轮历史修复为 RMS 1次/事件0次 | 同一合理 record_absolute 解释下保持 RMS 1次/事件0次；裸混合父句不再按最近名称猜测 |
| 原 T04 三臂，未重写用户请求 | partial，各1次；B交付缺失 | completed，各2次；只在原计划交付中补解释，工具/目标范围/独立gold不变 |
| 原 T07 三臂 | 两轮完成/4次 | 合理解释后两轮完成/4次；**原裸动作接口现在 partial/1次**，保留这一兼容代价而不隐藏 |
| T01–T08，A/B/C 24条受控路径 | 上轮108/108数值核验，少3项T04结果 | 111/111，恢复3项B结果；并非24条自主会话成功率 |
| live 先 record_info/list_events | 首次各触发错误 stage safety_stop | 合法元数据→计算→交付不停机；额外合法 record_quality 和中间工件也不因不在gold而停机 |

live guard 不再把独立交付清单当动作白名单，也没有仅豁免两个工具名。实际来源、绑定、观察请求与归档 scope、工具时基和数值仍核验。注入真实归档时基错误后在下一次模型调用前停止，保留错误现场；缺交付则由独立评价报告，不自动等同越界。

**尚存语义反例**：对“先查看stimulus事件信息并计算SYNTH-C1在2到4秒的RMS”，故意给出 event_relative 的错误解释，其元数据和数值仍可自洽，当前程序会执行1次 create_epochs。独立原请求评分判 RMS 缺失、all_required_results_correct=false、whole_request_correct=null；公开证据保留该失败。不能再笼统宣称原句在所有提案下都零错误计算，或安全完全未退化。确定性的事实约束没有取消，但时基语义正确性明确由 Planner 承担，存在真实模型误解风险；必须由有限自主诊断和原请求评价回答。最新指令明确允许合理语义解释、禁止用字面规则证明任意含义，因此没有继续为该句增加特判。若验收要求“即使模型给出自洽但错误的解释也必须永不计算”，现机制不满足，需要明确更强的意图确认边界；本轮不擅自扩展新解析系统。

## 费用、恢复与冻结

复用 Issue50Client 的原子 wire 预约，只增加可选 reservation_metadata 钩子。每笔记录当时模型、允许返回版本、输入/输出费率与依据、端点身份哈希、预约美元上限和实际运行设置。恢复不按当前费率重定价；金额是保守预算占用，不冒充服务账单。

| Fake/模拟费率反例 | 旧行为 | 本轮断言 |
| --- | --- | --- |
| 异常返回模型，但usage合法；2363 token预约、最高费率1.2美元/百万 | 先结算为US$0.000144再停机 | 保留US$0.0028356，reconciliation_required=true并停止 |
| 已received未settled，旧输入/输出1.2/0.1、新0.1/1.2 | 相同rate_ceiling仍可能套新费率 | 恢复US$0.000122，不能重定价为US$0.000034；不发送新请求 |
| 缺历史计价依据、网络异常/中断 | 未必有可核对来源 | 保守预约保留；缺依据不伪造money_settled，中断/异常不释放US$0.0012测试预约；均阻止后续请求 |
| thinking/timeout/端点变化 | 冻结不完整 | 实际runtime进入确认freeze，会话内漂移也在请求前拒绝 |

真实费用核对流程是：保留原 reservation/received/failed、服务原模型/费率依据及账单，核对每笔原始计价；缺依据的 safety_stop 不自动消除，不重开满额账本。此处没有新建完整财务平台或自动审计清除机制。异常期间的保守数值不能当精确实扣；正式账本未改。次数/Token/金额、独立开发和确认池、失败尝试、最终回答不可变预留、一次冻结和禁止择优重跑继续使用原机制。

## 离线验收与复现

兼容环境为既有 Python 3.10.17/eegagent；全量 **693项：678通过、15资源跳过**，compileall、pip check、git diff --check通过。7项解释专项、12项科学范围专项、15项live专项含多臂/变体子测；不是把子测数包装为独立实验样本。

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -p 'test_issue55_interpretation.py'
python -m unittest discover -s tests -p 'test_scientific_scope_issue55.py'
python -m unittest discover -s tests -p 'test_issue55_live.py'
python -m unittest discover -s tests
python -m compileall -q src tests
python -m pip check
git diff --check
```

24条原材料回放可用 `working_memory_issue52.run_case(case, arm, actions=working_memory_issue55_repair.interpreted_actions(case))` 重现，case=T01…T08，arm=A/B/C。旧 repair CLI/旧 repaired_actions 保留原历史行为，不冒充新解释回放。Fake 端到端使用 RawFake、明确 TEST ONLY 授权、模拟费率及临时账本；测试代码不得接入真实客户端。

首次全回归失败保存在 `artifacts/point1_task_memory/issue55/responsibility-first-regression.txt`：3个旧混合对象测试仍依赖字面猜测、5个错误涉及新guard误用绑定字段及旧测试未结交易缺历史价格。随后使用原工具契约取得时基，旧纯费用容量测试补明确 TEST 审计结算，混合对象测试补合理解释；未改原题、窗口、oracle和预算。新增夹具属性/索引错误也在本轮本地修正。最终日志 `responsibility-regression-final-2.txt`，不是删除首次失败后只留绿灯。

[公开合成证据](evidence/issue55_responsibility_repair.json)保存完整源码哈希清单、四臂正反结果、24条回放数值/来源、4个Fake完整会话的账本/逐轮评分、异常金额前后及自洽语义错误见证。原始完整Agent轨迹在本地忽略目录 `artifacts/point1_task_memory/issue55/`：`responsibility-first-reproduction.json`、`responsibility-repair-full.json`、`responsibility-money-before-after.json`，SHA-256见公开证据。金额旧版对照是从git读取fd78394原MoneyBudgetClient的**隔离执行**，不是完整旧live或已发生真实超支。初始/旧结果未覆盖。

## 真实执行条件与当前结论

- **已实现**：现有表示、共享科学核验、执行/档案接口和live计量/冻结职责调整。
- **离线通过**：合理受控解释下的实际工具链、来源/版本/缓存边界及运行器验收；机制门槛允许接续有限开发诊断，不再因“尚无自主成功”循环禁止首次真实调用。
- **真实自主通过**：尚无本轮证据。模型自行解释原T04/T07、完整回答和冻结C01/C02/C03均未运行；确认材料未用于本轮语义调参。
- **相对基线收益**：未验证；共享修复不能归为EEG适配臂独有收益，未做正式付费三臂/消融。

通过本地门槛后复核：进程/用户/系统常规环境均无 EEG_HARNESS_LLM_BASE_URL/API_KEY/MODEL，项目无 .env；项目Issue55产物目录无累计budget账本/运行锁。没有搜索私人凭据位置。本轮新增真实 **0 completion / 0 API tokens / US$0**，历史累计及剩余额度**未知**，不推定0、不重置、不另申请原预算。

最小外部补充是：向既有客户端注入原服务端点/模型/凭据（凭据不入库）、对应实际输入/输出费率及允许返回模型证据、Issue55已有逐笔调用/Token/费用和开发/确认池归属的累计记录。原总144/6M/US$3、开发48/2M、确认96/4M、最大输出2200/重试0继续有效。有上述条件即可使用原入口 `python -m eeg_harness.research.working_memory_issue55_live --real --ledger <既有已核对账本> --attestation <核验记录> --phase development --case T04 --output <全新目录>`；核验记录中的机制门槛绑定本次源码与证据哈希，不发送受控解释/gold。有限开发复核通过后才能按原顺序冻结确认，确认后不修改标准/重跑挑选。

尚存内部边界另列：自洽但错误的模型解释、无解释混合父句的兼容代价、最终回答需独立审查、历史费用缺依据需人工核对。本轮不把这些描述为“仅缺API”。阶段最终验收仍等待独立复核；PR37保持Draft、Issue55保持open。

发布：实现提交 `1bb3d6c926c97d9f1ddef584fbeb77c943ba517f` 已普通推送；[GitHub unit-tests #344](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/41279246528) 安装、编译、回归全部success。[Issue55汇报](https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6554217809)和PR37正文已同步。本发布补记不改变源码、证据或实验标准，CI成功不代替自主研究结论。
