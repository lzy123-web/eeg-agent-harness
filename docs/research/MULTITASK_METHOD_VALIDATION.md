# 多任务共同机制开发验证（Issue #26）

## 环境、隐私与复现命令

- 本地环境：Windows、Python `eegagent` Conda 环境；合成记录由 `demo.py` 构造。GitHub CI 不依赖私有 EDF/模型/API。
- 只读/离线本地资源：原 EEGAgent 示例 EDF 和原权重；权重 SHA-256 `e67a7b7aa958642b4d194c03fe4750995be89150e84b82cf78d662d35831c41b`。真实资源未提交，也未送入 LLM。模型输入合法性与一次真实本地推理只证明程序协议和输出形状，不证明医学性能。
- 快速回归：`python -m compileall -q src tests`；`$env:PYTHONPATH='src'; python -m unittest discover -s tests -q`。
- 合成 Fake 自然语言：`$env:PYTHONPATH='src'; python -m eeg_harness.research.integrated_method.v2_validation`。详细 JSON 默认写入被 Git 忽略的 `artifacts/`。
- 本地资源门控：设置 `EEG_HARNESS_TEST_EDF` 与 `EEG_HARNESS_MODEL_PATH` 为本机只读资源，再执行 `python -m unittest discover -s tests -p test_point1_multitask_v2.py -q`。此处不公开私人绝对路径。
- 真实 LLM 只在合成输入运行：临时设置 `EEG_HARNESS_LLM_BASE_URL/MODEL/API_KEY/MAX_TOKENS/TIMEOUT/MAX_RETRIES`，运行同一验证模块 `--real --max-requests 8 --max-total-tokens 12000`。密钥仅在本地进程环境，输出写忽略目录。LLM 客户端不向模型发送原始 EEG 数组；真实 EEG/事件细节/派生特征从未外发。

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
- 记录内容变化使先前 `record_info` token 失效并要求重新执行；两个 `EEGRecord/ExecutionContext` 交替使用，证据隔离。模型文件在预检后变化被拒绝，避免旧 loader 按路径缓存掩盖资源变更。
- 故障注入：PSD 的注册输入类型篡改为 Epoch 后预检 `GOAL_TOOL_CONTRACT_MISMATCH`；工具成功返回错误类型后图级 `TOOL_RESULT_TYPE_MISMATCH`，不发布答案；无请求目标却传事件参数被 `UNREQUESTED_PARAMETERS` 拒绝。生产工具未改。
- 最新 `compileall` 通过；完整 `unittest discover` 为 **236 tests, OK (skipped=13)**；本地 EDF+真实权重门控的新测试 **15/15 OK**。13 个默认跳过包含资源/联网可选项，不等同这些功能已在 CI 验证。
- Fake 两个自然语言请求均完成、证据闭合、答案门通过；合成连续执行工具 `psd`，事件执行工具 `list_events/create_epochs/epoch_quality/event_bandpower`。详细 synthetic-only JSON 本地留档，不进入 Git。

## 真实 DeepSeek：有界、保留失败，不作为正式成功率

本轮三次同配置开发检查（没有根据 holdout 调提示词），同两条合成请求，共 **10 completion、18,365 tokens**，低于 Issue 上限 24/60,000；单次套件硬限制 8 请求/12,000 tokens、max output 1,200、超时 35 秒、禁止重试。原始 assistant 响应每次到达即写本地忽略 JSONL，失败不覆盖。

| 开发检查 | 连续任务 | 事件任务 | 请求/tokens | 说明 |
|---|---|---|---:|---|
| 初版 v2 | 完成 | 安全澄清 | 3 / 5,015 | 事件解释额外提出未获原文支持的 `epoch_summary`；`INTENT_TYPE_MISMATCH`，零事件工具调用 |
| 任务中性核心修订后 | 完成 | 同类安全澄清 | 3 / 5,147 | 旧语言层非确定性/重复误解析；未放松科学语义门 |
| 增加响应模型身份记录后 | 完成 | 完成 | 4 / 8,203 | 两条链路均证据闭合、答案门通过；事件工具序列如上 |

请求名 `deepseek-chat`；最后一次四个响应均报告 `deepseek-flash`。前两次 SDK 未记录服务端响应身份，不能倒填为已核实版本。工具结果外发仅限合成记录。第三次成功不覆盖前两次失败，不能据此声称 100% 端到端可靠性。失败层归因：模型意图多提出 `epoch_summary`，独立 grounding 正确拒绝；不是图调度/数值/答案证据失败。尚未通过自由语言组合目标的独立 holdout，也未验证临床解释。
