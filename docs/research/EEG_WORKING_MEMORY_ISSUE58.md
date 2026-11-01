# Issue58：共享增量计划契约、证据与预算预检

## 当前授权与起点（2026-11-02）

依[Issue58全文](https://github.com/lzy123-web/eeg-agent-harness/issues/58)执行完整零研究API工程阶段。起点本地/实际远端`10a9ad92b1119a6eaca04a624b78630a54a7666c`一致，原分支、干净工作区、根AGENTS.md、Draft PR37已核对，无Python实验进程或运行锁。Issue57接受接缝已获主审接受，仅保持回归。当前新增研究calls/tokens/费用均0，正式账本不写，真实复测必须另获专项授权。

## 原失败与职责判断

已核原T05v3、T07v4 responses/requests/turn原件及公开索引哈希。T05 response5–7把修改A表示为新增alpha_A_rev，比较引用缺标量fields；新来源只指改窗子句。当前准确字段诊断仍拒绝缺fields，不能猜alpha或左右方向。T07 response8/11引用原Epoch但未重复列dependencies；下一请求确有错误回执。其回顾旧RMS/theta却新建测量义务、后续混淆task/delivery字段是另一层模型表示问题，不能都归因于调度丢回执。

修复前实际Agent/Store/Executor原生提案不改重放：T05、T07均首轮completed/后轮no_progress。初次T07遇历史随机artifact_id与新分配ID不同，首轮llm_error，原轨迹保留；用于因果对照的重放仅将测试环境Epoch UUID分配固定为原创建记录中的ID，数值仍实际计算、原助手提案字节不改。另一次定位分配器模块错误的夹具结果也保留。不称这些受控重放为新模型行为。

## 最小方案及取舍

1. 仅补提示/在入口union依赖：不解决版本就绪与控制前提，也不减少修订字段，放弃。
2. 另建统一操作DSL/计划状态：重复Planner/Store职责，新增迁移及安全面，放弃。
3. **选择原契约的共享增量扩展**：InputRef为数据依赖唯一来源；在原PlanGraph处理就绪、循环、历史和失效；revise_plan增加明确单交付patch，经原完整TaskSpec验证、来源/义务检查与同一graph.revise提交。历史读取继续原read_dependency/read_result/restore_task，不新建读取任务。

依赖兼容：旧dependencies中同时被InputRef引用的项仍视为旧式重复数据声明，未被引用的项保留原控制前提；新的control_dependencies用于明确要求某个任务整体完成，即使同时引用其局部交付。两种输入归一为同一控制关系，数据关系始终由引用动态派生，不另存一份可漂移的边表。固定旧版只依赖实际旧输出，不虚构当前节点循环；明确控制前提仍约束当前任务完成。派生来源对外可审查。

增量修改一次只针对一个task/key及预期revision，scope和interpretation只合并明确字段，input_refs/acceptance_rule按整个列表替换。不能改key/record/capability或偷偷移除义务；多交付修改仍用原updates事务，二者互斥并归一到同一原验证/提交路径。修改科学scope必须显式给出来源定位变化，不能由程序猜新来源。未改记录/通道/原对象来源/其他交付保留。未知目标、版本、字段或来源冲突均原子拒绝。合法独立新增仍由plan_tasks表达，不按名称猜修订。

历史视图只增加真实可读/可修订的状态指引；比较字段、记录、时基、左右方向、版本和新条件由模型明确选择。六组共享接口，自动接受与依赖证据呈现差异不变。

## 已实现与因果证据

已在原`task_plan.py`实现数据关系派生，贯穿合法性、当前/历史循环边、实际交付就绪、改动影响传播；独立控制前提单独保留。依赖来源写入原graph history及下一输入，未持久化第二套边状态。已在原`task_plan_agent.py`将单key增量修改归一为原完整更新，继续调用原来源/义务检查、graph.revise、Store与Executor。scope/interpretation按明确字段合并，列表替换；任务/交付身份不猜测，拒绝前不结算活动任务、不修改图版本。读取提示来自真实输出状态，未增设历史任务或数值算法。

这不是名称或句式补丁：通用层只有现有对象身份、InputRef版本、字段合并和统一契约；任务编号、原文、固定窗口及动作序列只存在离线研究夹具。没有自动把新增节点转换为修订，也没有补alpha、比较左右方向或重写source_ref。新质量任务只新增epoch_quality，旧RMS/theta通过原读取工具回顾。已有可见证据可直接使用，机制不强迫读取。

### 三类证据分别解释

| 材料 | 修复前 | 修复后 | 能说明什么 |
| --- | --- | --- | --- |
| T05v3原生提案，原两轮/原字段不改 | completed → no_progress，缺比较fields拒绝 | 相同 | 额外比较字段是模型选择，不能猜成功；原错误来源也未被擅自改正 |
| T07v4原生提案，原两轮/原字段不改、固定原UUID分配 | completed → no_progress；第8和11提案因漏重复依赖拒绝 | 第8提案准入；原后续错层级仍拒绝，第11因已存在任务身份拒绝，不再因漏抄数据边拒绝；最终仍no_progress | 明确的冗余约束消除；不等于模型会选择正确后续动作或完成质量交付 |
| 合法手写夹具：10a9ad9完整旧更新 → 本接口增量更新 | T05/T07×A/B/C全部两轮completed | T05/T07×六组全部两轮completed，0控制错误 | 相同科学意图可少表达重复状态；旧框架原本有合法链，不能包装为此前完全无能力 |
| 独立构造反例/图状态测试 | 原有反例保留 | 当前/固定历史引用、显式控制前提、未知/循环、错目标/版本/字段/来源/时基、未授权窗口、原子拒绝均通过 | 有限行为与安全边界，不是全面语义安全证明 |

原生重放没有生成新的模型响应；新接口链是**对既有手写合法夹具的明确机械迁移**，不是修正旧提案后冒称模型恢复。修复前基线从10a9ad9只读导出源码/config，在隔离本地目录运行；只复制本轮离线夹具帮助函数，不替换原Agent/Store/Executor。所有首次产物及两次UUID定位夹具问题保留。旧真实原文、实际送达答案、原评分和null独立审查字段均未修改。

T05真实工具结果：A原[0,2)绝对窗口alpha为`2.00e-10 V²`，新[4,6)为`3.92e-10 V²`；真实compare_results计算新减旧`1.92e-10 V²`、新/旧`1.96`，操作数带原scope/source/result_id，旧值在revision1保留，新值revision2，B不重算。T07沿原同一artifact_id/fingerprint追加质量测量；3个已创建试次、0个质量标记、可用比例1；平直阈值1e-8 V/比例0.95，高振幅0.0002 V/比例0.01，线噪比0.2，均为实际工具输出的经验标准、非临床校准。原theta/RMS不重算，不新建或删除Epoch。受控最终固定文本不计自主回答正确率，具体数值/范围/质量标准在公开工具证据中逐项列出。

## 表达负担及代价

同科学意图、候选C的配对数据如下；A/B对应实测也在公开证据中，六组工具schema一致。wire是既有序列化见证预算单位（包含输出预留），**不是API tokens或账单**。

| 项目 | 旧完整契约 | 新增量契约 |
| --- | ---: | ---: |
| T05改窗参数体UTF-8字节 | 399 | 212 |
| 实际工具schema字节 | 25,486 | 29,298 |
| T05受控决策数 / EEG计算 / 重复计算 | 9 / 3 / 0 | 9 / 3 / 0 |
| T07受控决策数 / EEG计算 / 重复计算 | 10 / 4 / 0 | 10 / 4 / 0 |
| T05全部消息字节 / wire见证单位 | 114,302 / 364,295 | 122,732 / 407,033 |
| T07全部消息字节 / wire见证单位 | 178,070 / 455,840 | 189,178 / 505,068 |

模型不再重复维护数据边对应dependencies，改窗不再重抄capability/record/channels/原source_ref/time_reference/acceptance_rule/其他交付列表；仍明确task/key/revision、新窗口及range_ref。程序只保留已有未改状态、派生确定关系和维护版本失效。旧入口兼容、增量schema、派生可审查关系及状态指引增加了上下文；步骤和计算数未下降，总wire增加。因此本轮的确定结论是表达责任收敛和可执行性修复，不是token、延迟或模型成功率改善。不能以单次参数体减少掩盖整体成本增加。

## 验证、冻结与原始产物

新增8个测试方法覆盖代表性组合（非笛卡尔积），包括真实两轮六组链、合法独立新增、增量拒绝原子性、数据/控制/固定历史版本区分，以及原live驱动/最终回答预留/费用结算TEST链。保留Issue57接受生命周期及回执交接、比较字段、科学来源/范围/工件和原子修订回归。全量**743项=728通过+15跳过**：14项外部EDF/模型/R3资源，1项默认关闭的真实LLM网络测试。原T01–T08×A/B/C **24链111/111 oracle、0控制错误**，compileall、pip check、diff check通过。

一次旧单元测试仍期待“漏重复dependencies必须拒绝”，随契约改变移出负例并保留未知引用负例；新增正例证明派生边仍要求实际交付。没有放宽既有科学约束来追分。原生后续失败、初次UUID重放失败、所有源材料保留，不称所有原提案通过。

最后一次有限生命周期反证发现：旧dependencies原本是独立控制前提，后续只添加InputRef会使动态分类把它消成重复数据边。首次图状态反例（非模型行为）保留在`control-promotion-first-failure.json`。修正仍在原revise事务内：没有显式修改任务依赖时，把即将丢失的已有控制承诺保留到原control_dependencies字段；不新增状态仓库。新测试证明只获得局部真实输出时仍不放行，整个控制前提完成后才就绪；修正后重跑全部742项基础及新增该项，最终743项/24链/新接口链均通过。该问题没有推给下一阶段，也未扩展到全部旧级联版本重写。

唯一[公开证据索引](evidence/issue58_incremental_contract.json)包含关键原生提案/下一输入错误、前后工具状态、三类材料标注、实际差比/质量结果/工件身份、六组公平性、字节/步数、冻结和预算预检。完整产物位于忽略目录`artifacts/point1_task_memory/issue58/`：`native-before*.json`、`native-after-bound-handles.json`、`controlled-before-legacy.json`、`controlled-final.json`、`controlled24.json`、测试日志及`frozen/TEST-wire-preflight/`中的原live manifest/messages/responses/逐轮截止评分/TEST账本。各原件哈希见公开索引；旧Issue57公开证据不改。

冻结行为源码/config总哈希：`7ff607f37247254c4178ef601e15723755999bd6e98c1f8597ce60ea1300c39f`；原请求/数据/followup_policy/评分未改，tools与各组system提示哈希及数据SHA另见索引。运行目标保持原deepseek-flash、thinking disabled、timeout90、输出2200、重试0；每轮12次completion/36工具/900秒/256000上下文字节。服务端点及费率基于原已核manifest冻结，不搜索凭据、不连通探测；获授权后原客户端实际配置仍须匹配该冻结目标，漂移停止。

复现（激活eegagent环境；输出必须使用不存在的新路径以保护旧证据）：

```powershell
$env:PYTHONPATH='src;tests'
$env:PYTHONIOENCODING='utf-8'
python -m eeg_harness.research.working_memory_issue58 --native-output artifacts/point1_task_memory/issue58/recheck-native.json --original-handles
python -m unittest discover -s tests -p test_issue58_incremental.py -v
python -m unittest discover -s tests -v
python -m compileall -q src tests
python -m pip check
git diff --check
python -m eeg_harness.research.working_memory_issue58 --preflight-output artifacts/point1_task_memory/issue58/recheck/preflight.json
```

原24链用`working_memory_issue52.run_case(case,arm,actions=working_memory_issue56.interface_steps(case))`；新增链用`working_memory_issue58.incremental_steps(case)`，旧完整表达用`legacy_revision=True`并在10a9ad9原科学源码运行。原生重放只恢复历史UUID分配，不修改助手提案。不能从这些命令推断新模型自主成功。

## 一次性专项预算预检：未授权、未消费

正式唯一账本只读：125次、1,234,297输入+输出API tokens、保守US$0.4054206；未结0。开发现行上限144次/2M，余19次/765,703 tokens；总240次/6M/US$3，确认96次/4M保持不动且禁止使用。正式账本SHA256前后均`6346c342723594590ab1fc2112824f403ca8cbf56f4070aadf5d631bc99264d1`。原费用是按既有价率的保守计算，不是服务账单。

预检通过原run_session→MoneyBudgetClient→JournaledBudgetClient→TaskPlanEEGAgent及实际工具链，唯一替代为**无网络传输能力的OfflineWireClient**，写独立明确TEST账本，未制造正式授权。两例共19次Fake决策、908,579实际序列化wire字节，既有保守预约口径合计950,379单位（wire字节+每次2200输出预留）；19个最终回答lease，最大lease28,458，最大当轮决策+lease89,616。模拟usage刻意按预约上界结算，仅为压力见证，不当作真实tokens。所有原生API usage仍待真实响应。该合法受控路径不是任意48次自主选择的资源上界。

申请方案（须用户单独明确批准后才能追加授权并运行）：

| 项目 | 本次请求的可用上界 | 沿原账本累计上限如何修改 |
| --- | --- | --- |
| 会话/顺序 | C组原T05→T07，各一条完整两轮会话，不择优重抽 | 同Issue58/原分支/原账本，不开新池 |
| completion | 最多48次，包含最终回答；不是预计实际消费 | 开发144→173，总240→269，即增加29次上限；与原剩19合成48次，仅新授权后可用 |
| 输入+输出API tokens | 最多1,000,000 | 开发2,000,000→2,234,297，总6,000,000→6,234,297，即增加234,297；确认4M不动 |
| 货币 | 本次保守最多US$1.20 | 原总US$3不增加；累计最多US$1.6054206，含原费用 |

Token申请由完整wire见证950,379加最大最终lease28,458后向上取整至100k得到1M，并非把字节报告为API实耗；真实usage计入同一累计账本，每次发送仍按实际wire保守预约，达到任一上限即停止，不能保证所有未知48步均能跑满。费率沿已核2026-11-01原依据：输入非缓存US$0.3/百万、输出US$1.2/百万，预约按二者较高者。1M×1.2给货币上界；模拟结算US$0.3111993仅为TEST计算，不是预报账单。

最终回答采用现有不可变snapshot lease；未知/异常usage、未结占用或意外模型标识按原预约保守计费并安全停止，不自动重试、不清停机标记。确认池不借，真实受试者数据/私有路径/凭据不出站，仅合成信息。原单次追加授权入口只接受已批准的固定授权；**未来取得专项批准后，须在同一幂等前缀核验/追加路径绑定新评论及本次累计上限**，不清旧交易、不重建预算平台。本预检不把Issue58方向许可当付费许可。

## 工程状态、科学状态及暂停原因

工程实现、有限对照/反证、全量回归与证据文档已完成，正常提交/远端及CI回执记入PROJECT_STATUS。本轮新增研究calls/tokens/费用均0。**真实自主复测尚未运行，等待专项授权**，这是Issue58第5节要求的明确权限暂停点；不是缺配置、额度全部耗尽或工程无法推进。

待验证：模型是否实际选用增量修订/历史读取，能否完整交付T05新旧差比与T07原工件质量续算；总体wire增加能否被减少失败抵消；广泛语义理解、稳定性、全部旧级联版本机制及相对强基线收益仍未证明。旧T04/T03成功仍限原版本，旧T05/T07完整自主失败未撤销，受控结果不填独立评分true。DAG/真实交付/分层证据协作已有离线执行证据，未形成新候选的真实自主成功证据。共享修复不算C独有创新。Issue58/55保持open，PR37保持Draft；不开展正式三臂/消融、确认或研究内容二。获批后同Issue继续两个原自然会话，未获批则到此结束本回合。
