# Issue56 共享控制接口收敛：设计、离线对照与结果

起点b8328b5，2026-11-01（Asia/Shanghai）。原分支/远端一致、工作区干净、无实验进程或锁。新增研究API额度0；不恢复凭据、不实例化服务客户端、不修改Issue55账本。原48次/312,387tokens/保守US$0.1052811保持。

## 根因与主设计

已读取六个会话原始requests/responses/turn/manifest及快照，逐一核对公开索引哈希；原生arguments及tool_call批次不根据摘要补写。b8328b5上未修改消息重放保存before-native.json。它是旧共享机制上的反事实重放，不冒充各会话当时40c3edb等版本的逐位复现；T04首败的静态响应耗尽为llm_error，而原运行no_progress，差异如实保留。首次重放夹具误将case对象传入partition产生ValueError，原日志保留，修正仅适配器调用。

主设计只在现有接口内收敛四项职责：

1. 从Registry抽取同一计算scope契约，供scientific、DAG计划/修订及Store使用；报告指标仍是goal文字，不把metric/band/baseline伪装成计算参数。计划允许缺参，类型错误给路径；保留真实运行时物理约束。
2. 在已有SourceFrame上公开带轮次、请求摘要和偏移的稳定source_ref，解析回完整父句。新接口不要求全文复写；旧span只作兼容入口，不能与ref并存覆盖。跨轮来源必须经过既有历史对象/真实结果与当前补参核验，locator不是语义证明。
3. 数值动作可明确task_id/output_key/revision；同一原生批次按原循环顺序处理，批次中的科学动作须明确归属。单步旧省参路径兼容，显式owner不靠可变current猜测。先核验owner/输出/参数一致再切换，保留逐动作状态和原生调用配对。不取消合法独立批次、不新增执行器。
4. finish_task结构化声明要询问哪个任务/交付缺失字段，程序核验并将实际问题渲染到最终回答；驱动只接受已送达且匹配协议的有效澄清。内部WAITING_INPUT、状态标签或无关自由文本不再自动获得预定补参；无法判定时留审核记录。协议元数据只在评估器，gold不进入Agent。

不采用：继续扩充词序/连接词规则；宽松忽略错误参数；自动修DAG或将所有批量调用禁用；另一套自然语言裁判/Planner/来源数据库。新增复杂度局限于契约派生、定位解析和已有控制器的明确所有权/澄清。schema体积与运行兼容成本会实测，不预设下降。

## 证据约定与验收

分别保留：①原始native消息未改重放；②机械来源引用迁移（不能替错误源猜正确父句）及明确标注的受控恢复；③独立构造正反例。只有原真实日志能证明历史模型行为，本阶段全部新结果是离线机制证据。旧评分和原题不改。

原自洽错误语义边界继续有效；三臂与相关消融共用适用接口，保留验收自动化/依赖证据选择差异。

## 实现与离线验收结论

**离线阶段通过；新接口真实自主复测未运行；完整跨轮自主能力与相对强基线收益仍未证明。** 通过指下述执行契约、实际Agent/Store/Executor集成及已列出的科学反例通过，不指所有旧native提案都成功，更不指任意错误语义都被阻断。实现提交与CI见PROJECT_STATUS发布回执。PR37保持Draft，Issue55/56保持open待独立审查。

最小公开证据：[issue56_interfaces.json](evidence/issue56_interfaces.json)。包含36份原件逐项哈希、六会话前后动作/错误/状态、机械迁移前后参数、补参组合反例、24条受控路径数值oracle、84个实际Agent运行快照摘要及关键全链动作，关联本机完整产物路径/哈希；不公开私有思维链。所有数据来自既有合成记录，无真实受试者数据。研究API新增completion/token/费用均0，正式账本SHA256仍为`f8bf2cc546dbb5a07330842f7554736cc8a925ca7854ceaf66dab8ebc8e31a6d`。

| 机制 | 本轮具体变化 | 正反例及结果 |
|---|---|---|
| 统一计算参数 | `scientific_contracts`提取原Registry派生逻辑，scientific、DAG公开schema和Store共同使用。计划/修订嵌套字段按同一有限schema词汇验证，给出field_path和原入口恢复信息 | 支持能力可保留缺参；scope中的报告band/metric或错类型原子拒绝；修正计划后原工具正常执行，图版本/活动scope/旧结果不因拒绝改变 |
| 完整来源定位 | `source_ref`由请求轮次、请求摘要、完整frame偏移组成，按原用户请求重新解析；`range_ref`只在合法历史补参/修订时引入当前范围 | 原同名字段引用无需复抄父句或重新完整命名；正确跨记录“仅通道名”关系通过。未知/错记录/跨父句拼窗/不适用旧窗/ref与span冲突拒绝；失败不形成准入缓存 |
| 动作及批次 | 原控制器接受显式task_id/output_key/可选revision；省略已知scope仍合法。批次依原Agent循环顺序执行，每个科学动作明确归属，记录调用ID及前后状态 | 同能力两窗口、交错select、独立B先推进均绑定正确；错owner/key/record/过期或布尔revision、批次隐式owner均零计算。声明的辅助质量工具可执行，交付清单未成为实验gold动作白名单 |
| 对外补参 | finish声明现有任务/交付的实际缺失字段，程序把问题写入真正送达答案；驱动核验合法部分交付、当前revision、完整缺字段、来源缺值和后轮协议关系 | B正确+A内部等待但无关/没有询问：旧实际驱动均发送第二轮，新版均停止；真实缺参的结构化询问允许发送。少问字段、已知窗口、伪缺参、遗漏B均停止，不靠关键词或付费裁判 |
| DAG—科学交付—证据记忆 | 原依赖/版本/读回机制继续使用；历史locator允许合法补参，当前range_ref允许局部修订 | 六臂三轮链：B先交付→补A窗口→原Epoch功率→读原过程并对同一artifact做质量检查；不重建工件。局部改A窗口保留旧值用于compare，B结果不变；不以DAG完成替代原请求独立评价 |

这里的六臂是A/B/C/C-no-delivery/C-no-selection/A-equivalent。公开schema完全一致；原方法关于自动交付验收、依赖证据选择的差异仍在。测试值、预定动作和evaluation_only只在研究夹具/驱动，不进入正式Agent提示或执行许可。实现不包含任务编号、事件名称、窗口数值或给定句式分支；新补参策略配置映射既有followup_policy语义，而非T03/C02编号。

## 原始失败、迁移与构造证据分开解释

本机目录为`artifacts/point1_task_memory/issue56/`，全部新产物单独保存。`before-native.json`来自隔离的b8328b5源码；`release-native.json`来自本轮源码哈希绑定的实际Agent；`release-locator-migration.json`只将唯一完整父句机械换为locator，不修正DAG、scope、顺序或owner。

| 原会话 | 旧共享机制上的原消息重放 | 新接口原消息重放 | 解释 |
|---|---|---|---|
| T04首次 | llm_error，1个RMS | llm_error，1个RMS | 原历史为no_progress；固定响应耗尽与交互模型不同。来源/交付歧义没有被机械重放自动纠正 |
| T04修订复查 | completed，2个RMS | llm_error，1个RMS | **兼容代价**：旧select+amplitude批次没有owner，新版拒绝；后续硬编码结果ID失配。历史真实成功不撤销，新接口也不能冒称原样成功 |
| T07首次/修订 | 均no_progress，0计算 | 均no_progress，0计算 | 错scope/input_refs/malformed JSON仍拒绝；新入口直接定位非法scope字段，正确恢复入口保持plan/revise |
| T03首次 | partial，B RMS正确 | partial，B RMS正确 | 原模型确实写了询问窗口的文本，但未使用新结构化声明；不能冒充已完成新驱动续接，需后续模型复测或人工审核 |
| T05首次 | round_limit，A PSD正确、B缺失 | round_limit，0计算 | 旧混合批次缺owner；B错来源仍不被迁移猜正。禁止把更早拒绝算成任务成功 |

仅替换source_ref的机械重放与新版原生停止结果相同，说明locator不会自动修复错误计划/归属。原36份文件、首次失败、原评分均未改动。

另外两类独立证据：

- **迁移既有手写合法夹具**：`interface_steps`在原`interpreted_actions`上只按唯一原父句映射locator、按当前node唯一delivery填owner、为缺窗finish声明字段。T01–T08×A/B/C共24条，111/111独立数值核验，0控制错误。T03澄清后完成，T05/T07/T08两轮完成，T06真实试次数不足保持partial。它们不是六会话模型原提案，也不是自主表现。
- **独立构造配对集成**：8个测试方法，84个真实Agent运行快照（部分同一会话的连续轮次），覆盖六臂；另用同样构造输入分别运行旧/新驱动，复现补参组合漏洞。覆盖矩阵见上表；原Issue55时基/来源/费用/冻结/原子修订反例包含在全回归中。

## 失败归因、修订边界与开销

采用一次主设计，没有第二套Planner/Executor/来源数据库，没有超出两轮实质设计调整额度。实现内补全隐式记录补参的frame对齐、合法历史结果窗口核验及布尔revision拒绝，均是上述契约的编程补齐。首败保留：

- 重放脚本第一次把case对象传给partition接口，ValueError；修正调用参数，未动原消息。
- 首次计划/全回归有旧错误字符串与“内部等待即补参”的期待失败；改为准确field_path、实际对外澄清判定。保留首次日志，不降低科学oracle。
- 24条夹具第一次迁移把原`quality_if_not_executed`控制哨兵误包成工具元组，T08第二轮llm_error；修复夹具保留哨兵，原错误产物`migrated-controlled-24.json`不覆盖，成功版另存`migrated-controlled-24-fixed.json`。

删除了scientific/DAG计算scope的重复派生来源，计划与修订不再是无类型对象；模型可只填locator和owner，已知scope不必复写。仍保留旧span输入兼容，但互斥且归一到原完整frame核验，不产生第二权威含义。

代价不是零：C的20个工具schema序列化从15,122增至24,796字节（+9,674，约64%）；六会话首轮可见消息从4,254–4,968增至5,032–6,034字节（逐会话+778–1,066）。locator减少生成端全文复制义务，但完整父句仍供模型检查，历史catalog随请求增长，尚未做大规模长程长度评估。显式owner增加短字段并使旧无owner批次不兼容；程序渲染补参问题增加契约约束。受控路径的操作数/拒绝/上下文字节均在证据中，仅为夹具运行开销，**不是API tokens或模型调用收益**。

用本环境既有jsonschema 4.24.0核验20个工具schema符合Draft2020-12；六臂schema相同，缺参/非法字段矩阵的标准校验与运行时有限验证器一致。未新增依赖；远端服务是否接受这些schema及模型是否稳定使用，未通过API测试。

## 验证及复现

兼容Python 3.10 eegagent环境；运行前设置`PYTHONPATH=src`和`PYTHONIOENCODING=utf-8`。全量结果710项=695通过+15既有资源跳过，48.347秒；8方法末次集成捕获通过，84个快照。compileall、pip check、git diff --check通过。全量日志、原始重放和构造证据的路径/哈希见公开JSON；跳过项未计通过。

```powershell
python -m unittest discover -s tests
python -m unittest discover -s tests -p test_issue56_interfaces.py
python -m compileall -q src tests
python -m pip check
git diff --check
python -m eeg_harness.research.working_memory_issue56 --output artifacts/point1_task_memory/issue56/new-native.json
python -m eeg_harness.research.working_memory_issue56 --output artifacts/point1_task_memory/issue56/new-migrated.json --migrate-source-refs
```

重放需要本机原索引指向的六会话文件；缺失会明确报错，不根据公开摘要伪造。输出使用write_new拒绝覆盖。24条新接口受控链复现：

```python
from pathlib import Path
from eeg_harness.research.working_memory_issue52 import run_case, write_new
from eeg_harness.research.working_memory_issue56 import interface_steps
rows = [run_case(case, arm, actions=interface_steps(case))
        for case in ('T01','T02','T03','T04','T05','T06','T07','T08')
        for arm in ('A','B','C')]
write_new(Path('artifacts/point1_task_memory/issue56/new-controlled.json'),
          {'kind': 'migrated_valid_scripted_fixtures_NOT_autonomy', 'results': rows})
```

旧对照通过`git archive b8328b5 src tests config`在本目录隔离解包、独立进程载入旧源码，没有checkout覆盖当前修改；原重放适配代码/原始响应在对应完整产物中，补参旧/新复现脚本也保留并记录哈希。

## 尚未解决与下一次自主复测问题

本次反例集未发现新增事实约束误放行，错误来源/范围/工件/版本仍拒绝。**这不消除旧安全边界**：自洽但错误的event_relative语义解释可能通过部分确定性检查并执行，原请求独立评分拒绝；相关首败和负例测试仍保留。locator只能定位，不能证明自然语言含义。补参缺值验证有意保守：只自动批准可核查的缺窗；含混、隐式或无法确定的自然语言条件返回审核需求，可能拒绝实际合法的自由文本询问，尚非通用语言理解器。

未来最少待答问题：模型能否按新scope/locator/owner一次正确构造与恢复计划；能否真实询问缺参并完成后轮局部修订、精确旧值及原工件复用；增大schema/历史catalog是否在真实上下文限额内可稳定使用。这些必须由后续真实自主执行回答。

准入条件是用户**另行明确批准**真实开发复测（本阶段不运行、不自动申请），核验现有服务对新schema支持、冻结代码/配置/原协议并承接唯一累计账本和隐私边界。Issue55开发48次已耗尽，确认池96次未准入；货币余额不等于新增调用授权。之后仍先有限开发，不能直接触发C01–C03确认或正式三臂/消融。无新增API配置或消费定位问题需要用户本轮回答。
