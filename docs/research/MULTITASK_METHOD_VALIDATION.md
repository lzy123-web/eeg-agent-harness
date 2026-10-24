# 多任务共同机制开发验证（Issue #26）

## 环境、隐私与复现命令

- 本地环境：Windows、Python `eegagent` Conda 环境；合成记录由 `demo.py` 构造。GitHub CI 不依赖私有 EDF/模型/API。
- 只读/离线本地资源：原 EEGAgent 示例 EDF 和原权重；权重 SHA-256 `e67a7b7aa958642b4d194c03fe4750995be89150e84b82cf78d662d35831c41b`。真实资源未提交，也未送入 LLM。模型输入合法性与一次真实本地推理只证明程序协议和输出形状，不证明医学性能。
- 快速回归：`python -m compileall -q src tests`；`$env:PYTHONPATH='src'; python -m unittest discover -s tests -q`。
- 合成 Fake 自然语言：`$env:PYTHONPATH='src'; python -m eeg_harness.research.integrated_method.v2_validation`。详细 JSON 默认写入被 Git 忽略的 `artifacts/`。
- 本地资源门控：设置 `EEG_HARNESS_TEST_EDF` 与 `EEG_HARNESS_MODEL_PATH` 为本机只读资源，再执行 `python -m unittest discover -s tests -p test_point1_multitask_v2.py -q`。此处不公开私人绝对路径。
- 真实 LLM 只在合成输入运行：临时设置 `EEG_HARNESS_LLM_BASE_URL/MODEL/API_KEY/MAX_TOKENS/TIMEOUT/MAX_RETRIES`，运行同一验证模块 `--real --max-requests 8 --max-total-tokens 12000`。密钥仅在本地进程环境，输出写忽略目录。LLM 客户端不向模型发送原始 EEG 数组；真实 EEG/事件细节/派生特征从未外发。
- `agent_cli --agent-mode point1-v2` 的非 Fake 联网入口现在要求 `--demo-synthetic`，在加载 EDF 前拒绝真实记录；Fake 或离线 parsed-task 方法仍可处理本地合法 EDF。此 CLI 限制不是通用隐私系统：程序化调用方仍须遵守数据授权与外发边界。

## 核心方法路径的逐族证据

| 任务需求 | 新方法实际路径 | 输入/输出与科学约束 | 故障和证据处理 | 未覆盖 |
|---|---|---|---|---|
| 无事件记录 0–2 s 绝对频带功率 | 自然语言→意图验证→`MultiTaskRequest(psd)`→`SharedEvidenceGraphCore` record 绑定→Context/Executor/`psd`→答案证据门 | `EDF_NATIVE` 合成 128 Hz，明示通道与窗口；Welch 绝对功率对象 | record 内容/来源改变即撤销 token；窗口/通道错误预检拒绝；答案指向工具真实数值 | 非 ERD/ERS、无儿童规范阈值 |
| 同一无事件记录质量+PSD | parsed 双目标→同一图内两个独立 record goal→同一 Executor；不创建 Event/Epoch | 质量经验指标+Welch 功率；禁止筛选保持无状态转换 | 两目标任一参数不合法则整体预检拒绝；不把质量测量当自动筛选授权 | 真实 LLM 多正向目标尚缺稳定验证 |
| 事件 0–1 s 质量+条件功率 | 自然语言→事件目标→同一新版图 frontier：`list_events→create_epochs→epoch_quality→event_bandpower`→来源绑定→答案证据门 | 明示 `stimulus`、窗口、禁止筛除；合成 EventSet 与真实 Epoch 工具 | 缺标签/越界整体拒绝；Epoch 内容变动导致下游证据失效；禁止操作不执行 | 不等于完整 ERP/ERD/ERS；真实 R3 在此版本未重复跑 |
| 既有模型适用性与推理 | parsed 模型目标→同一图 record+资源绑定→ToolSpec/Profile/权重预检→原 `seizure_detection` 工具→结果类型门 | 仅 `tuev_bipolar_22`、256 Hz、一秒窗、有效通道与权重；本地示例 EDF/权重实际执行，输出 shape `[1]` | 错 Profile/缺资源零调用拒绝；权重在任务中改变时 fail closed；结果数组类型核对 | 模型训练集/性能“源码未提供”；不作 ASD 证据或临床诊断 |

这不是把工具数当多任务：第三族输入合法性与模型资源独立于 Event/Epoch；无事件连续路径不造伪事件。共同核心真正负责契约类型核对、DAG 依赖、状态指纹、失效、限次失败/恢复和证据发布；每族差异留在输入/操作策略。旧 v1.1 运行路径仍在。

## 数值、状态、异常与回归

- 合成无事件 PSD 的 alpha 数值由独立 `scipy.signal.welch` + 频带积分 oracle 核对，与原工具格式化输出完全一致；非自比较 Harness 输出。
- 新版事件路径真实调用 Registry/Executor，工具顺序、闭合 token、无筛选行为在测试中断言。合成质量筛选 identity 转换按 `epoch_quality` 证据解析，不擅自造新 Epoch。
- 记录内容变化使先前 `record_info` token 失效并要求重新执行；**同一新版图**内 Epoch 内容改变使 `create_epochs` 及下游质量证据失效并重新进入前沿。两个 `EEGRecord/ExecutionContext` 交替使用，证据隔离。模型文件在预检后变化被拒绝，避免旧 loader 按路径缓存掩盖资源变更。
- 故障注入：PSD 的注册输入类型篡改为 Epoch 后预检 `GOAL_TOOL_CONTRACT_MISMATCH`；工具成功返回错误类型后图级 `TOOL_RESULT_TYPE_MISMATCH`，不发布答案；无请求目标却传事件参数被 `UNREQUESTED_PARAMETERS` 拒绝。生产工具未改。
- 最终 `compileall` 通过；完整 `unittest discover` 为 **238 tests, OK (skipped=13)**；本地 EDF+真实权重门控的新版测试 **17/17 OK**。默认跳过包含资源/联网可选项，不等同这些功能已在 CI 验证。PR 首轮 GitHub Actions `unit-tests` #157 已成功；补充隐私门和事件失效测试后的末轮 CI 另行核实。
- Fake 两个自然语言请求均完成、证据闭合、答案门通过；合成连续执行工具 `psd`，事件执行工具 `list_events/create_epochs/epoch_quality/event_bandpower`。详细 synthetic-only JSON 本地留档，不进入 Git。

## 真实 DeepSeek：有界、保留失败，不作为正式成功率

本轮三次同配置开发检查（没有根据 holdout 调提示词），同两条合成请求，共 **10 completion、18,365 tokens**，低于 Issue 上限 24/60,000；单次套件硬限制 8 请求/12,000 tokens、max output 1,200、超时 35 秒、禁止重试。原始 assistant 响应每次到达即写本地忽略 JSONL，失败不覆盖。

| 开发检查 | 连续任务 | 事件任务 | 请求/tokens | 说明 |
|---|---|---|---:|---|
| 初版 v2 | 完成 | 安全澄清 | 3 / 5,015 | 事件解释额外提出未获原文支持的 `epoch_summary`；`INTENT_TYPE_MISMATCH`，零事件工具调用 |
| 任务中性核心修订后 | 完成 | 同类安全澄清 | 3 / 5,147 | 旧语言层非确定性/重复误解析；未放松科学语义门 |
| 增加响应模型身份记录后 | 完成 | 完成 | 4 / 8,203 | 两条链路均证据闭合、答案门通过；事件工具序列如上 |

请求名 `deepseek-chat`；最后一次四个响应均报告 `deepseek-flash`。前两次 SDK 未记录服务端响应身份，不能倒填为已核实版本。工具结果外发仅限合成记录。第三次成功不覆盖前两次失败，不能据此声称 100% 端到端可靠性。失败层归因：模型意图多提出 `epoch_summary`，独立 grounding 正确拒绝；不是图调度/数值/答案证据失败。尚未通过自由语言组合目标的独立 holdout，也未验证临床解释。

## Issue #28 v3 的独立开发验证（不替换上述 Issue #26 历史结果）

复现命令（激活已有依赖环境后）：

```powershell
$env:PYTHONPATH='src'
python -m compileall -q src tests
python -m unittest tests.test_point1_multitask_v3 -q
python -m unittest discover -s tests -q
python -m eeg_harness.research.integrated_method.v3_validation
```

最后一个命令为 Fake 协议测试，只用 `build_synthetic_no_event_record` / `build_synthetic_event_record`；详细 JSON 和合成应用样张在 Git 忽略的 `artifacts/`。本地真实权重测试可临时设置 `EEG_HARNESS_MODEL_PATH` 后重跑 v3 模块测试，**只在本机对合成 22 导输入调用现有权重**；未发送模型结果给外部服务。真实联网检查在相同验证模块加 `--real --max-requests 8 --max-total-tokens 24000`，需临时配置 LLM 环境变量，绝不把 Key 放入命令/仓库。通用 `agent_cli --agent-mode point1-v3 --demo-synthetic[-no-events] --request ...` 可接自然语言；非合成 EDF 在联网前拒绝。此版 Fake 用固定协议场景，不假装可自由理解任意文本。

确定性断言覆盖：Registry 能力发现不加载权重；整段质量/两 PSD 窗口三目标；独立 SciPy Welch+积分核对两个窗口数值与事件条件 alpha 功率的逐 Epoch 均值；同参数结果只调用一次、不同参数必分别调用；事件目标相同完整 scope 共享一个 Epoch，不同标签产生两个 Epoch；连续与事件目标在同一图，禁止筛选未执行；中间 Epoch 内容变化撤销事件侧证据并保留连续侧；缺事件/窗口/来源阶段/资源与 Profile 不符时原子拒绝或澄清；结构化结果 JSON 可序列化；合成应用仅消费 bundle；Fake 缺参→继续及错误意图拒绝。独立 oracle 与工具同用 SciPy Welch 库、同频带配置，因此核对积分/切片/条件聚合调用链，不是完全独立的谱估计实现。现有模型路径测试只断言输出结构，不作性能/医学判断。

四轮真实 DeepSeek 开发检查均为合成 EEG，共 15 completion / 32,066 tokens；首轮双窗误拒、第二轮范围/共指误拒、第三轮 Tool Calling 格式与缺参分类失败、末轮三例完成。各轮原始响应按到达顺序写本地忽略 JSONL；末轮 `deepseek-chat` 请求的四次实际响应均报告 `deepseek-flash`。末轮闭合目标数为双窗 3、混合 3、澄清后 1，实际工具分别为 `record_quality+psd+psd`、`list_events+create_epochs+psd+epoch_quality+event_bandpower`、`psd`，不把必要 producer 算成用户新增目标。此结果不代表未见请求成功率，也不证明相对强专家优势。

本轮末次完整 `unittest discover` 为 **258 tests，OK，14 skipped**（资源/环境可选项）；`compileall`、`pip check` 通过。v3 本地权重启用时 **20/20 OK**。内部必要 `list_events/create_epochs` 可运行，但模型额外提出 `epoch_summary` 且无原文目标证据时整单澄清、零工具调用。`3df256d` 的 GitHub Actions `unit-tests` #169 成功；最后状态同步提交的 CI 需另核对。生成产物不提交。

## PR #27 审查后增量验收（不替换前述 258 项历史检查）

仅使用合成 EEG/Fake，不增加本轮真实 DeepSeek 调用。定向新增反例：两个同类 PSD 目标在首轮互借两个窗口的时间引文，旧实现实际返回 `completed`，修订后 `PARAMETER_GOAL_OWNERSHIP_UNCLEAR` 且零工具调用；缺参续接中删除禁止筛选、变更已确认参数或交换两个同类窗口，返回 `GOAL_SET_CHANGED_ON_RESUME`；保持前两目标与禁止项、只补第二窗口唯一缺失终点时完成。非事件记录的事件能力、未配权重的模型能力不再标为 v3 当前可用，已注册重参考工具标为旧入口未迁移。注入第二 PSD 窗运行失败后，公开 bundle 保持 `goals=[]`、两个目标均列未发布；应用拒绝计数不完整的 bundle。

命令为 `PYTHONPATH=src python -m compileall -q src tests`、`PYTHONPATH=src python -m unittest discover -s tests -q`、`PYTHONPATH=src python -m eeg_harness.research.integrated_method.v3_validation`。当前本地环境 `eegagent` 已执行 compileall、`pip check` 和完整 **263 tests / OK / 14 skipped**（即 249 实际执行无失败）；Fake 固定三例状态为 completed、completed、clarification_required→completed。此为开发集回归，不是未见任务准确率或 CIEDG 对强 Expert 的胜负证据。阶段审查还指出旧历史“258 tests”应读为 244 执行/14 跳过，本文保留原记录并明确解释。
