# Issue #34：未预置 EEG 组合任务的首次真实观察与对照

本文件只报告冻结协议 `config/point1_composition_protocol_v1.json` 的首次结果，不覆盖任何 CIEDG、PR #27/#31/#33 或 Issue #16/#32 历史。协议提交 `bd1243f`，首轮评分器/执行脚本提交 `2f80ec8`。真实输入均为确定性合成 EEG；外部 API 只收到请求、合成元信息和必要的工具文字结果。无真实受试者数据外发。请求模型名 `deepseek-chat`，23 个响应的实际 `model` 均为 `deepseek-flash`；不能将其称作另一个未经核实的模型版本。

## 运行与原始记录

执行环境：已有 `eegagent` Conda Python、NumPy/SciPy/MNE/PyTorch、CPU 上原仓库现存 `seiz&normal.pth`；未下载/训练权重。`PYTHONPATH=src python -m eeg_harness.research.composition_evaluation --split development|holdout --real ...`。密钥仅在本地进程环境临时提供，未进入 Git。执行者分别为 v3 `InstanceGoalEEGAgent`、原生结构化调用 `EEGAgent`（相同合成记录/Profile/Registry 工具、科学禁令、真实 Executor）及独立的条件式 Strong Expert/typed-workflow 近似。后一臂由冻结结构化目标起步，**不评价自然语言理解，亦非 WINGS 软件运行**；空目标的 D05/D06 不给它“预知答案”。原生臂的输出是自由文本，v3 的完成交付是逐目标 `evidence_bundle`，不能简单把两种答案格式当同一指标。

忽略目录 `artifacts/point1_composition/` 保存四个 append-only 运行 JSON 与对应原始响应 JSONL；它们只在本机，不上传 GitHub。公开协议 SHA-256：`05c5ab46cfaee1f3bca59755c2e37a99fe9c660f26cdbcc015e89420166ddae2`。各原始 JSON 哈希按运行先后为 `4a0d005d28455ee2ec43e53ec8890407eee035f4e621f8b0a927dd74de3aa90b`、`1772368e0591c9a102842875aa5dcd6743bfebe018d438fd2644f5c6050f1ab0`、`0fdf308e2d4a45f9bf2e5a9b8150b08171002f7add34e29f7dbff175bb186ba0`、`734322518eec10981f7dfb48117c817c5341060483edd1bef4ee43df9c4c5a98`。原始响应 JSONL 的对应哈希为 `8baa5de14ac22247d9e8d09fc275360daef14de6c7612429daa7d75e6d111a50`、`de063406e519f57ecacceebb5de862344825aa2b096c20f9f5c2708450f8fba6`、`c4a67e7cc75f43dac473689295370c6f0f541ccd4785203fe7a446e0cb4bd360`、`0a5d37a6bc76dfd8845843d2ecdf2a4121557afccc9fde01244e60a8a892d9c5`。

四次外部运行共 **23 completions / 49,411 tokens**（开发 v3：6/13,282；开发 Native：8/15,583；holdout v3：4/9,685；holdout Native：5/10,861），低于 24/50,000 上限；禁自动重试。D06 的 Native 在 `list_events` 后受该次运行预算保护而 `llm_error`，标为**预算截尾，不能当模型自然失败**。没有额外补跑。每个真实请求及首次评分保留在本地原始文件；以下是按层摘要而非改写原始记录。

## 逐例工具轨迹与分层结果

`!` 表工具失败；`→` 表真实先后次序。条件 Expert 的 D05/D06 为 N/A。v3 安全停止的成功只表示未危险误发布，不表示完成目标。

| 例 | Strong Expert / typed 近似 | v3 真实 DeepSeek | Native 真实 DeepSeek | 归因 |
|---|---|---|---|---|
| D01 双窗连续 PSD | `psd→psd` 完成 | `psd→psd` 完成，2/2 数值 oracle | `psd→psd` 完成 | 三臂合法，无额外依赖难度 |
| D02 stimulus 计数+事件功率 | `list_events→create_epochs→epoch_summary→event_bandpower` 完成 | 0 工具澄清，未完成 | `create_epochs→epoch_summary→event_bandpower`，工具数值正确；回答功率单位误写 `V²/Hz` | v3 的原始 LLM 目标类型/参数正确，但第二 `request_quote` 用省略号拼接，违反连续原文证据合同；属于意图表示/校验误拒，非 DAG 错误。Native 为回答证据错误 |
| D03 整段质量+幅值+另一窗 PSD | 三工具完成 | `record_quality→amplitude→psd` 完成 | 未运行 | 合法并列组合；质量只核结构，幅值/PSD 独立数值核对 |
| D04 22 导模型单窗 | 模型一次完成 | `seizure_detection` 完成；1 秒、1 导、两分数有限值 | 未运行 | 仅验证合成配置和输出结构，不评价癫痫真实性能 |
| D05 原生 2 导误用模型 | N/A（结构化 gold 无可执行目标） | 0 工具安全拒绝 | `list_events` 后拒绝模型；回答又错误声称模型需事件 Epoch | 安全停止成立，但 Native 多 1 次无关观察、科学理由错误 |
| D06 事件窗缺参数 | N/A（结构化 gold 无可执行目标） | 0 工具澄清 `tmin/tmax` | `list_events` 后预算截尾 | Native 不能评价自然完成能力 |
| H01 连续 PSD + target 计数 + control 事件功率 | `list_events→create_epochs×2→psd→epoch_summary→event_bandpower` 完成 | 同序 6 调用完成；三个作用域正确、数值 oracle 通过 | `psd→create_epochs(target+control)→event_bandpower` 3 调用，利用 producer 摘要计数并只报告 control 功率；**合法完成** | 首次自动评分把合并 producer/缺显式 summary 误判失败；后续独立投影审计修复评分器，原始 false 保留。Native 更少工具调用，不能硬称 Candidate 有成本优势 |
| H02 连续幅值 + 不存在的事件计数，整单不可完成 | 0 工具安全停止 | 0 工具拒绝、不发布部分 bundle | `amplitude→list_events`，回答明确“部分完成、整单未完成” | 符合冻结的“不发布为全部完成”；Native 多做一次无法整单交付的幅值，v3 原子停止较省调用，但不同部分交付政策须披露 |
| H03 双极模型 + 同窗连续 PSD | `psd→seizure_detection` 完成 | 同序完成，数值与模型结构检查通过 | 未运行 | 两类证据未互代；不能推断模型临床适用性 |
| H04 末端 late 事件质量+功率 | `list_events→create_epochs!` 停止 | 同序停于 `EPOCH_CREATION_FAILED`，无 bundle 发布 | 未运行 | 根据真实边界反馈科学停止，无“凭空试次” |

开发集 v3 **5/6** 达到完成或预期安全停止；holdout **4/4**。按完整可执行请求，v3 开发 D01–D04 为 3/4，holdout H01/H03 为 2/2；不把安全停止算分析完成。强 Expert 的 8 条有结构化目标场景均合法完成/停止，D05/D06 为 N/A。Native 实际只跑 D01/D02/D05/D06/H01/H02，其中 D06 预算截尾；其余 5 例的工具证据/安全停止经过追加审计可接受，但 D02 回答单位和 D05 科学理由有错误。Native 与 v3 不是同一 10 例全集，不能给出并列总体胜率。完成场景未出现“目标已正确表达但 v3 依赖计划不合法”的重复失败；新任务组合的真实弱点主要在 LLM 引文、自由文本回答和评价器假定唯一流程。

## 评分器追加审计及限制

H01 首次 Native `pass_action_numeric=false` **保留**在原始 JSON。首次算法错误地要求每个事件目标对应完全相同 label 集合的 producer、且计数必须调用 `epoch_summary`；然而 producer 的 `event_labels` 可提供独立计数，合并 target/control 后 `event_bandpower.conditions.control` 可独立核查。修订后的 scorer 以“目标在已产生的证据中是否有带作用域的独立证明”评分：目标窗口/标签必须包含于 producer 范围，计数从 producer 标签列表独立重算，control 功率用 SciPy 重新计算；新增非模型测试验证这一合法替代计划。**原始 LLM 轨迹、协议、gold、v3、Native 均未更改，也未重试 holdout。**在候选代码冻结前，曾对 holdout 跑过不调用 LLM 的 Expert/数值 smoke；因此“未见”严格指 v3/Native 首次模型输出与未按其修改方法，而不声称评价器从未接触 holdout fixture。

数值 oracle 对 PSD/幅值/事件功率独立重算，事件边界与计数独立检查；质量输出只核结构，模型只核合法输入/有限形状，不核真实标签或泛化性能。10 个任务仍是人为设计的有限合成集，不能推断开放自然语言、真实 EEG、ASD 应用或统计优势。人工适配成本：本轮无候选核心代码、Prompt、工具改动；10 条科学真值/fixture/评分与 Expert 条件 recipe 是共同实验基础。Strong Expert 需要人工输入目标合同，但其中的事件 producer 规则可复用；与 v3 共享科学知识、并没有展示候选新增任务更省维护。ReAct 已实际运行子集；Plan-and-Execute 只按 [原始相关方法](https://aclanthology.org/2023.acl-long.147.pdf) 讨论其先计划后执行的潜在行为，**未运行性能**。WINGS 原始[语义工作流生成方法](https://www.wings-workflows.org/) 支持声明式组件/数据约束，本文仅做最近邻近似，不冒称 WINGS 真实成绩。
