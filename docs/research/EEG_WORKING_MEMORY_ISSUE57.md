# Issue57 新接口真实开发：协议、修订与结果

## 当前入口：交付接受生命周期限定收尾（2026-11-02）

依据[最新限定评论6560727410](https://github.com/lzy123-web/eeg-agent-harness/issues/57#issuecomment-6560727410)，本节取代下方历史付费执行安排作为当前状态；历史6会话、首次失败、原评分及版本关系不修改。**本限定收尾离线自验通过，等待独立复核；新接口未真实自主复测。** 不代表完整自然会话、工作一科研目标或相对强基线收益通过。

开工核对本地及实际远端均为`59652769ae410cade805d60e017958269df91707`，原分支、干净工作区、根AGENTS.md、PR37 Draft，无Python实验进程或Issue55运行锁。未启动旧实验、搜索凭据或变更配置。新增研究API/calls/tokens/费用均为0；正式账本字节SHA256前后同为`6346c342723594590ab1fc2112824f403ca8cbf56f4070aadf5d631bc99264d1`，原125次/1,234,297tokens/保守US$0.4054206及剩19次保持不动。

### 原问题确实复现：可计算的生产者没有合法接受入口

在原完整eegagent环境，使用项目合成记录和实际TaskPlanEEGAgent→PlannedTaskStore→Executor→NumPy/SciPy，Fake仅提供控制决策。原请求为“记录A stimulus事件后0到1.25秒建立试次并计算功率；只有试次数至少2才继续功率分析。”同一节点内epochs交付附3≥2条件，power引用epochs。修复前18条轨迹先保存，再改生产代码。全部属于**独立构造集成反例**，不是六个历史模型会话的原始失败重放。

| 科学计划结构 | 修复前A/B/C-no-delivery的实际功率执行次数（每条） | 修复前C/C-no-selection/A-equivalent（每条） | 修复后六组（每条） |
| --- | ---: | ---: | ---: |
| 同任务、有额外条件 | 0 | 1 | 1 |
| 同任务、无额外条件 | 1 | 1 | 1 |
| 生产者/消费者分任务、有条件 | 1 | 1 | 1 |

第一次反例中实际3个Epoch、output_valid/predicate/accepted均为真，但非自动组仍TOOL_SUCCEEDED；整节点complete_node因缺power拒绝，power又因生产者未接受拒绝。这是共享接口的循环等待，不能记作C的方法收益。修复后只为非自动组加入合法局部接受动作，自动组继续自动接受；并非给同样动作序列强行打平结果。旧整节点过早完成仍应拒绝。

### 最小整改及职责边界（已实现）

复用`complete_node`：带`output_key + revision + result_id`时只接受该真实交付；只有task_id时保持整任务完成语义。控制器从现有结果核验身份、范围、来源、时基、实际binding及输入依赖，不能接受空结果、错key/owner、旧revision、替换前结果或失效工件。无需先额外check/read；真实证据已送达即可声明。局部接受不归档、不清空消费者、不切换current、不重算；实际控制回执在下一输入可见。

接受凭证直接存于现有`TaskSpec.outputs[key].acceptance`，不是第二个接受仓库。凭证包含责任方、接受时revision、真实条件诊断及完整DeliveryItem+结果身份/来源/处理配置/工件绑定的指纹。`_sync_outputs`只继承仍匹配的凭证，不能因另一结果同步而清回TOOL_SUCCEEDED；新绑定输入也不能夹带旧凭证。相同结果重复接受幂等。图的原有修订/历史机制负责撤销受影响交付；无关标题或节点版本本身不冒充该交付变化，真正的范围、条件、结果或绑定变化会使旧凭证不适用。消费有条件结果时核验其接受凭证及原实际binding。

三层含义分开：真实结果存在→按方法责任接受该交付→全部必需交付齐全并通过原归档契约后完成任务。公共`delivery_check.accepted`始终是客观条件诊断；凭证不把模型判断写成客观真值。A/B/C-no-delivery继续由模型判断额外acceptance_rule，C/C-no-selection/A-equivalent继续程序判断。测试注入3<4却错误接受时，前者可记录owner=model、scientifically_accepted=false并继续，独立评价必须判错；后者拒绝。共同科学硬约束、用户禁止、真实来源/工件核验不受该方法差异豁免。

没有把所有TOOL_SUCCEEDED放行，也没有强制所有基线自动验收、拆分DAG或增加另一套Planner/Executor。实现仅修改原控制器；通用代码无任务编号、事件名、窗口或句式特判。代价是控制schema多三个可选身份字段，以及每个已接受交付的有界凭证/指纹和诊断；每次同步线性扫描原交付列表并散列其元数据，未增加全局历史扫描。模型显式接受多一次必要控制决策，自动组不必多一次；本轮没有测量真实token收益。

### 成对反证、生命周期与回归

- 六组合法生产者→消费者均只执行一次功率、复用同一真实工件。非自动组不额外check即可接受，回执可见；重复接受、读取、切换独立任务、消费者同步后凭证保持，整体完成前无提前归档。
- 尚无生产者、提前消费、错owner/key/revision/result、错误工件、越出计划范围、用户明示禁止基线处理均拒绝；非法接受不修改图/其他交付。3<4时正确拒绝接受的六组均可保留partial并完成独立B任务；另保留故意错误模型判断及客观失败诊断。
- 实际两轮链：旧窗接受并消费→合法改窗→旧revision/旧result接受被拒、新producer未经接受不能消费→正确接受新producer并消费。旧工件/历史输出保留、B只计算一次。物理记录替换用明确标注的故障注入检验binding失效；条件与结果替换的指纹接缝另列状态级测试，不冒充自然模型动作。
- 新增10个测试方法覆盖上述多组路径；全量**735项=720通过+15资源跳过**，原T01–T08×A/B/C **24链、111/111数值核验、0控制错误**；compileall、pip check、diff check通过。跳过为14项外部EDF/模型/R3资源测试及1项未启用的真实LLM网络测试，具体原因保留在全量日志。
- 开发首次回归有两项失败：负例长串触发原no_progress，改为独立负例会话而不调松生产保护；状态级替换携带旧凭证，修正绑定入口只继承原有效凭证。此为测试开发记录，不是新模型首败；原问题首次完整轨迹未覆盖。

[公开合成证据](evidence/issue57_acceptance_closeout.json)包含三结构×六组前后结果、实际3试次、诊断/责任方/错误码/工件一致性、生命周期及安全反例、24链和完整本地产物哈希。完整messages、Agent结果、快照分别保存在忽略目录`artifacts/point1_task_memory/issue57-closeout/{before,after,lifecycle-safety,controlled24}.json`及测试日志。旧[真实开发证据](evidence/issue57_real_development.json)未改。

复现命令（已激活项目eegagent环境，PowerShell；输出路径必须尚不存在，避免覆盖旧证据）：

```powershell
$env:PYTHONPATH='src;tests'
$env:PYTHONIOENCODING='utf-8'
python tests/test_issue57_acceptance.py --matrix-output artifacts/point1_task_memory/issue57-closeout/recheck.json --local
python -m unittest discover -s tests -p test_issue57_acceptance.py -v
python -m unittest discover -s tests -v
python -m compileall -q src tests
python -m pip check
git diff --check
```

修复前矩阵使用同一夹具`matrix_case(..., local=False)`在5965276代码上运行；当前代码重跑旧整节点动作不等于回退接口。24链沿用`working_memory_issue52.run_case(case, arm, actions=working_memory_issue56.interface_steps(case))`，case=T01…T08、arm=A/B/C，评分/原题不改。

**限制及结束边界：**此次只修交付接受生命周期；新接口未真实自主复测，旧T03v4完整两轮成功不能自动继承，T05/T07完整自主失败不变。语义理解、完整跨轮稳定性、相对强基线收益及全部旧级联版本机制仍未证明。没有重做配置/消费审计，没有推进整体计划接口简化、正式三臂/消融、确认实验或研究内容二。Issue55/57保持open，PR37保持Draft；发布提交与CI见PROJECT_STATUS最新回执，等待独立复核。

---

## 下列为此前真实开发历史（保留原文）

**阶段结论：有限工程整改与开发交付完成，完整科学目标部分通过，等待独立审查。** 已执行6个真实原题会话、10个用户轮次；T04单轮与最终T03两轮经执行者逐项自审通过，T05/T07完整会话未通过。独立`whole_request_correct`/`autonomous_memory_use`仍为null；不同候选不能拼成最终4/4。确认未运行，稳定性与相对强基线收益未证明。

2026-11-01，从本地/远端一致的16a8b87继续原分支和Draft PR37，工作区干净，无实验进程/锁。Issue56独立离线验收已由Issue57正文接受；本阶段结果仍由执行者自查，不替代独立主审。

## 执行前冻结

- 原Issue55唯一账本追加授权[6559557879](https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6559557879)，不initialize、不删除diagnostic_review=failed。原48次/312387tokens/保守US$0.1052811、无未结，前缀SHA256为f8bf2cc546dbb5a07330842f7554736cc8a925ca7854ceaf66dab8ebc8e31a6d。
- 开发累计144次/2M，本轮新增至多96次；总累计240次/6M/US$3；确认96次/4M保留但本阶段禁用。绝对累计限额，不是新增144次或US$3。
- 最小衔接在原live/预算路径增加唯一幂等authorization_revised，记录新旧限额、原/追加授权、账本原字节前缀哈希、累计快照及原服务/价格。无记录仍用旧限额；重复不叠加；改变前缀/限额/服务、关闭/安全停止/确认冻结均拒绝。原交易验证、异常保守结算、实际wire及不可变final lease继续使用。
- 仅候选C，固定原题顺序T04→T03→T05→T07；原Issue52自然请求/数据/followup_policy和Issue55开发评分不改。原每用户轮12次completion、36工具、900秒、256000上下文字节；输出2200、重试0、thinking disabled、timeout90。沿用原DeepSeek服务/deepseek-flash和原已核实峰时非缓存费率上界输入0.3/输出1.2美元每百万，不宣称账单实扣；首个正式T04也是schema兼容观察，不额外ping。
- 四例7轮首次遍历最坏84次；以实际余额优先完成首遍，若共同机制硬阻断则先暂停归因。最多两批由真实失败支持的连贯接口修订，离线反例/回归后冻结；只有具体修正后才完整复查最有信息价值的失败。两轮复查按最坏24次判断可行性，不能承诺新增96足够首遍与所有复查；不靠巨量未来预留封死当前合法工作。同一行为版本不重抽。
- T03只在正确独立交付和有效真实缺参询问后发送原补充；T05/T07按普通后续原政策推进，不额外要求首轮全对。每轮截止分数不被后轮覆盖。模型输入不含gold、夹具动作、正确locator/owner或人工恢复指令。
- 新输出独立保存于artifacts/point1_task_memory/issue57，账本仍在issue55。首次付费前记录源码/提示/schema/协议/评分/数据/服务设置及原账本快照。只发送必要合成信息，不发真实EEG/私人路径/凭据。原历史与新首败全部保留。

## 授权衔接离线验证

临时TEST账本/Fake四项测试覆盖历史48笔继续累计、旧授权拒绝第49次、显式追加后实际Agent多轮链、幂等/重启/冲突前缀、调用/Token/金额上限、确认禁止、未结/异常usage/模型/停止/服务漂移保护。原已关闭阶段不能重开，原费率及final lease不变。正式账本尚未追加前不产生研究API调用；后续结果按实际执行追加。

## 实际结果

初始候选0b3e503：T04首次5次/53785tokens，两项RMS及字段引用正确、实际答案完整（执行者自审，独立字段仍null）。T03首次7次/73326tokens，B正确但repeated_action停止，未实际询问A窗口，原第二轮不发送。累计60次/439498tokens/保守US$0.1457328。

### 第一批修订：未送达回执不能被调度切换清除

真实T03第3次调用完成B amplitude，第4次实际请求只含旧A list_events回执和B完成索引，缺少刚生成的B数值。根因为TaskPlanController._activate把“已归档”和“已送达模型”混同，无条件清除pending。原7份模型原生提案不改的Agent重放复现这一丢失；修复后第4次输入同时含实际amplitude回执。固定旧动作仍repeated_action，不能称为自主修复成功。

最小修改：切换时只清理已包含在last_view的旧回执，未送达的完整native批次保留到下一决策，新exchange自然替换。没有预取其他历史数值；已读字段继续原证据接力，归档与分层依赖选择不改。另将completed节点的select返回已完成事实和read/revise路径，避免误报缺依赖；不重新激活或重算。

构造Agent/Fake在六臂检查未见回执送达、旧回执退场、已完成选择不重算；A/B/C错误范围批次仍拒绝且失败回执送达。首次夹具未填partial.unresolved导致失败，原日志保留，补齐测试契约后通过；未放松生产finish。完整回归与新候选真实复查按后续记录。

20ad1a7真实T03完整复查21次/236622tokens：首轮9次，B答案及真实缺窗询问送达，原协议准许第二轮；第二轮12次，创建3个合法Epoch但无theta最终交付，round_limit。首轮多问默认频带边界、冗余complete/select、一次非法clarification均保留。第二轮多次自引用修订被拒，末次event_bandpower违反final-only限制仍拒绝。累计81次/676120tokens/US$0.2232219，没有科学错误执行或安全停机。

### 第二批修订：任务依赖与交付依赖分开就绪

原模型把分段、试次数和功率放在一个科学目的下，功率input_refs指向同任务分段key；原PlanGraph只允许引用其他task并要求显式dependencies，造成合法工件关系被当成任务自依赖，拆分又触及不得删除义务保护。保留原12份提案前缀，实际Agent双轮重放：旧版连续INVALID_PLAN_REVISION；新版本同一第11份原提案可提交，第12份重复修订拒为no-op。不手改提案或伪造后续自主成功。

沿既有TaskSpec/DeliveryItem/InputRef表达局部交付图，不新增Planner/Executor：节点启动只等待外部依赖，具体动作等待其全部真实且已接受的输入；本任务当前key必须无环，旧revision可显式读历史；改动key的局部传递消费者及外部消费者失效，独立key保留。实际artifact参数必须等于所声明生产者，不能靠计算后匹配才发现冲突。schema只补充同一引用字段的契约说明，不含任务编号/事件名/窗口特判，所有六臂共享。

实际Fake工具链覆盖六臂生产/消费、提前消费与伪工件拒绝，实际双轮改窗保持旧结果和B不重算；图测试覆盖局部循环、未知key/版本原子拒绝、传递失效与固定历史引用。首个构造窗口0.5秒被原Welch最短1秒约束正确拒绝，改为合法测试窗口1.5秒，保留首败；科学约束未删。原24受控链/全量回归另存新产物，不能作为真实模型成绩。

本阶段两批架构修订额度到此用完。先按原序继续T05、T07首次遍历；剩余足够完整两轮（最坏24次）才再复查T03。不在同一行为版本重复抽样，不启动确认。

第二批实现5501c68通过724项（709通过/15跳过）、24链111/111，并获CI #374 success。其T05首次7次/75033tokens：首轮4次两结果与答案正确，普通后续按原政策发送；第二轮3次，比较input_refs未给fields，全部泛化INVALID_CONTROL_ARGUMENT后no_progress。新窗口未计算，不能称完整修订通过。累计88次/751153tokens/US$0.2483958。

第二批普通实现补齐：比较输入的既有“两个引用、每个一个标量field”检查原抛ValueError被外层吞掉。只改为现有ContractError及准确字段路径，plan/revise均反馈；不新增比较规则、不补字段或猜意图。原7份提案未改重放仍拒绝，具体诊断可见，原失败保留。此为同批输入契约诊断补齐，不新增第三个架构假设。后续真实候选另冻结，T05旧候选成绩不合并。

## 最终真实开发结果与逐轮自审

| 会话/候选 | 首轮 → 后轮 | 新增calls / 输入tokens / 输出tokens | 保守费用US$ | 实际结论 |
| --- | --- | --- | --- | --- |
| T04首次 / 0b3e503 | completed | 5 / 52499 / 1286 | 0.0172929 | A [0,2) RMS 1.41e-05 V；B [2,4) 1.30e-05 V；自主字段引用和答案完整 |
| T03首次 / 0b3e503 | repeated_action，未发后轮 | 7 / 72036 / 1290 | 0.0231588 | B数值正确；未送达数值和有效询问，不通过 |
| T03复查 / 20ad1a7 | partial → round_limit | 21 / 229397 / 7225 | 0.0774891 | B答案/澄清合法，第二轮3 Epoch但theta未交付 |
| T05首次 / 5501c68 | completed → no_progress | 7 / 72073 / 2960 | 0.0251739 | 首轮A alpha 2.00e-10 V²、B RMS 1.30e-05 V；后轮无新值/差比 |
| T07首次 / 0ae0840 | completed → no_progress | 14 / 178793 / 8500 | 0.0638379 | 首轮RMS、theta及3试次准确；后轮无质量执行/交付 |
| T03再复查 / 0ae0840 | clarification_required → completed | 23 / 290927 / 4924 | 0.0931869 | 原补窗后A 3试次、theta 1.8449999109511803e-10 V²；B不重算，完整两轮自审通过 |

最终T03首轮12次、第二轮11次：实际澄清由finish.clarifications渲染、原followup gate核验；未猜A窗口。第二轮revise保留历史对象并引用当前[0,1.25)范围，实际create_epochs→epoch_summary→event_bandpower使用同一工件。旧B只有一次amplitude，read_dependency/read_result原值进入下一请求并用于最终答案；计数3、单位V/V²及µV/µV²换算核对一致。一次读取非规范字段被FIELD_NOT_FOUND拒绝，模型自行恢复。多次读/check和错误complete仍存在，接近轮数上限，不代表稳定高效。

T07后轮7次均为计划拒绝：先缺显式外部dependency，再将acceptance_rule等交付字段错放task层，之后漏required_outputs。原journal证明下一输入含准确field_path/合法字段/实际历史任务和工件索引，未发生与T03首败相同的回执丢失。没有质量测量、更没有同原artifact的质量续算成功；原24受控链证明该入口可执行，但不证明模型会稳定构造。继续改层级表示/提示或同版本重抽将超出本轮两批修订，故保留负面证据并止损。

T05缺fields诊断补齐后只做离线原提案重放；最终剩19次小于冻结的完整两轮最坏24次，未开启不完整复查、不借确认池。最终v4真实覆盖T03和T07，**T04成功只在v1；T05只在v3运行**。T03也不能由两个旧首轮/后轮拼接，成功依据是v4单一原生完整会话。

## 证据与开销

[最小公开合成证据](evidence/issue57_real_development.json)含6会话的全部77次原生工具提案（去除非交付助手自由文本）、实际工具参数/关键返回/失败、每轮送达答案与截止评分、下一模型输入的原生call_id及证据字段、原生不变重放前后、每笔模型/usage、会话费用和全部本机原件哈希。公开self_review单列，不填独立null。完整messages/tools、manifest、响应、原唯一账本和各次前后快照保留忽略目录；没有上传密钥、私人配置路径、真实EEG或私有思维链。

各会话从首请求记录到末响应的实测时间依表顺序约10.576、11.270、44.224、17.940、44.051、43.896秒（包含本地轮间开销，非纯服务延迟）。最大可见消息字节分别19839、14971、25076、19221、35971、41392；工具schema v1/v2为24796字节，v3/v4为25218字节（输入引用契约说明+422）。字节不冒充API tokens。全部77响应均为原deepseek-flash、finish_reason=tool_calls，自动重试0，无HTTP失败或未知usage；真实服务接受新schema。

三模块边界：DAG/TaskStore共享就绪、原子修订和版本追踪已实现；确定性来源/对象/数值/实际交付核验离线与本轮实际执行可核对；原请求完整答案仍需独立审查。分层证据已有原工具回执交接及T03跨轮精确读回的真实观察；T05新旧差比和T07原工件质量续算本轮只具受控通过，尚无完整自主通过。没有真实restore→质量续算成功，不强迫已可见证据额外恢复来制造指标。

复杂度取舍：只改原live授权入口、PlanGraph及TaskPlanController；无新Planner/Executor/任务目录/依赖库。任务内key级无环检查和失效闭包有额外图遍历，仍受原32节点、每节点12交付、4修订限制；保留一个最新回执直到可见，增加最多一个native批次的交接负担，仍受原上下文上限。共享A/B/C/适用消融同权，不能算C独有收益。局部依赖与外部任务dependency仍需模型正确区分，schema复杂度不是零。

## 预算、验证与退出

本轮新增77calls、921910 API tokens（输入895725/输出26185）、保守US$0.3001395。原Issue55累计125calls、1234297tokens（输入1195262/输出39035）、US$0.4054206；125笔均结算，无未结占用。开发余19calls/765703tokens；总余115calls/4765703tokens/US$2.5945794，其中确认96calls/4M仍**禁止使用**且实际0。金额按每笔原费率非缓存上界，不是服务账单或账户余额。原账本48笔字节前缀哈希未变；追加授权仅一次，保留旧diagnostic_review=failed，新Issue57同样记failed，未删除停止标记或重置账本。本轮无safety_stop；不以此推断科学语义绝对安全。

最终验证：`PYTHONPATH=src python -m unittest discover -s tests`，725项=710通过+15既有资源跳过；`python -m compileall -q src tests`、`python -m pip check`、`git diff --check`通过。原T01–T08×A/B/C经Issue56既有interface_steps运行24链、111/111独立oracle、0控制错误。四个新增本地依赖/版本方法、回执正反例及授权Fake保留；最后新增比较诊断测试不构成新研究机制。不能以构造夹具成功改写真实首败。

最终行为提交0ae0840的[CI #376](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/41321392219)安装、编译、725项回归全部成功（21.224秒，15跳过）。跳过分别为：真实EDF+权重的Agent/Context/Executor/MultiTaskV2四项及Smoke四项（8）；合成22导联真实权重C3/MultiTaskV3（2）；EDF双极/native Profile（2）；R3真实适配/工作流（2）；默认关闭的联网LLM验收（1）。未为凑全绿加载私人数据/模型或开启额外联网测试。

工程实施、有限真实开发、有界修订、可行完整复查与本地证据交付完成；科学目标部分通过，**整组完整会话验收未通过**。现无API配置/消费定位问题需要用户补充。未解决的是多轮复杂计划结构与字段选择稳定性、冗余控制读回、原工件质量续算与新旧比较的自主交付，以及既有自洽错误interpretation仍可能通过部分事实检查的语义边界。原安全反例/首次失败保留，负例回归未发现新增放行；没有声称安全零退化的普遍证明。

下一最小决策是独立审查这些原始轨迹，决定是否接受当前复杂度或在后续明确范围内简化计划输入契约；不自动启动确认、第三批方案、真实三臂比较或额外付费。PR保持Draft，Issue55/57保持open。

发布：实现/证据提交`534f1c2461956aea37a984cf29c6b7623286537d`普通push并核对远端一致，[CI #378](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/41322369703) success；[Issue57统一回执](https://github.com/lzy123-web/eeg-agent-harness/issues/57#issuecomment-6560142630)、[Issue55](https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6560155937)、[Draft PR37](https://github.com/lzy123-web/eeg-agent-harness/pull/37#issuecomment-6560156263)均已同步，历史正文保留。普通push一度TLS握手失败后原命令重试成功，未关闭TLS校验/改全局配置/强推。83份本机原件索引末次哈希全部一致。此发布回执单独文档提交，不改变候选、原协议或正式消费。
