# EEGAgent 源码系统审计

## 1. 审计范围与结论口径

- 审计日期：2026-10-21。
- 审计源根目录：`D:\Profession\Programs\CANKAO\EEGAgent-main\EEGAgent-main`。
- 文档所在项目：`D:\Profession\Programs\CANKAO\eeg-agent-harness`。
- `D:\Profession\Programs\CANKAO\eeg-harness-validation` 是独立验证原型，不属于本报告所称“当前 EEGAgent 实现”。
- 本报告只把源码、随仓资源和本轮只读运行结果视为事实。README 或论文描述若没有对应可运行代码，会单独标记。
- 下文路径均相对审计源根目录；行号对应 2026-10-21 审计时的文件内容。

总体判断：当前项目是一个可在单记录、单进程场景中运行部分工具的研究原型。它具备 Agent 循环、动态工具注册、基础 EEG 特征、多个本地模型工具、RAG 代码和评估脚本，但尚不是数据契约统一、工具可隔离复用、任务可配置切换的通用 Harness。最主要断点是主入口固定使用 22 导双极加载链，而睡眠和 MDD 工具分别要求 2 导与 19 导输入。

## 2. Agent 架构与执行位置

| 能力 | 实际位置 | 实现事实 |
|---|---|---|
| 命令行示例入口 | `main.py:149-159` | 从环境变量读取 API key/base URL，固定示例 EDF 和英文问题。没有独立 CLI 参数解析。 |
| Agent 初始化 | `main.py:14-41`, `EEGAgent.__init__` | 读取 JSON 配置和报告模板、拼接数据路径、加载 EEG、注册全局数据、提取 EDF 基本信息、初始化 OpenAI 客户端和系统消息。 |
| LLM 调用 | `main.py:46-59`, `call_model` | 调用 `OpenAI(...).chat.completions.create`；默认模型来自 `EEGAGENT_MODEL`，否则为 `qwen3-235b-a22b`；超时 60 秒。 |
| 核心循环 | `main.py:95-146`, `run` | 可选 RAG 后加入用户消息；每轮先调用 LLM，再解析并执行工具；没有工具调用时结束，默认最多 8 轮。 |
| 工具调度/执行 | `main.py:61-93`, `handle_tool_calls` | 解析文本工具调用、按名称查注册表、自动注入 `config`、直接执行 Python 函数、捕获工具异常并回注。 |
| Prompt | `prompt.py:1-18`, `getSystemPrompt` | 注入 EEG 信息、先验知识和工具 schema，规定 `<FUNCTION>`/`<ARGS>` 文本格式、时间边界和少调用原则。 |
| 工具调用解析 | `utils/parseCalling.py:5-25`, `extract_tool_calls` | 用正则提取函数名和非贪婪 JSON 对象；不是 OpenAI 原生 tool calling，嵌套或非严格 JSON 容易解析失败。 |
| 工具结果回注 | `utils/messageMerge.py:3-10`, `messageMerge` | 把参数和返回值序列化后直接追加到上一条 assistant 消息，而不是新增标准 `tool` 消息。 |
| Tool Registry | `tools/register.py:16-128`, `FunctionRegistry` | 装饰器注册函数和自定义 schema；支持查询、列举和导出元数据。 |
| 工具自动发现 | `tools/__init__.py:5-16`, `import_all_modules` | `pkgutil.walk_packages` 递归导入整个 `tools` 包。多个模型在模块顶层加载，发现工具即加载权重。 |

### Prompt 与报告生成的实际情况

`main.py:18-19` 会读取 `RAG/report_template.yaml`，并在 `main.py:40` 将其传给 `getSystemPrompt`；但当前生效的 `prompt.py:1-18` 没有插入 `report_template`。只有被注释掉的旧 Prompt 在 `prompt.py:43-46`、`89-91` 引用模板。因此“EEG 报告生成”在 README 中被描述，但当前生效 Prompt 没有模板化报告流程，不能视为已完整实现。

### RAG 的实际情况

`main.py:96-111` 在每次 `run` 时创建 `BGEEmbedder` 和 `FaissSearcher`，检索前三条并按相似度阈值追加到 system prompt。`RAG/embedder.py:7-20` 从本地 `RAG/sentenceModel/bge-m3` 加载 Transformer；`RAG/searcher.py:7-28` 加载 FAISS 索引和文本块。

本地 BGE-M3 目录只有 tokenizer、配置和 sparse/ColBERT 辅助权重，没有 `model.safetensors` 或 `pytorch_model.bin`。本轮实测 `BGEEmbedder()` 抛出 `OSError`；该异常属于 `main.py:110` 捕获范围，因此 Agent 会打印降级提示并继续，不使用 RAG。`RAG/registered_files.json:2-4` 还保存了外部 Linux 绝对路径，只能视为历史构建信息。

## 3. 实际注册工具、任务、模型与数据证据

运行导入后注册表实际包含 11 个工具。

| 工具函数 | 任务与窗口 | 模型/权重 | 输入条件 | 数据集证据 |
|---|---|---|---|---|
| `compute_amplitude` | 均值绝对值、RMS、极值；≤60 秒 | 无 | 22 导双极名称；共享数据 | 无数据集依赖，见 `tools/windowInfo.py:12-51`。 |
| `compute_psd` | Welch PSD 与 delta/theta/alpha/beta/gamma 带功率；≤60 秒 | 无 | `config.fs` 和 `prior knowledge.freq_bands` | 无数据集依赖，见 `tools/windowInfo.py:54-95`。 |
| `compute_symmetry` | 指定左右导联 Pearson 相关和 SSIM；≤60 秒 | 无 | 成对 22 导双极名称 | 无数据集依赖，见 `tools/windowInfo.py:98-142`。 |
| `reflectData` | 提取原始短窗；代码限制≤1 秒 | 无 | 22 导双极名称；返回 NumPy 数组 | 无数据集依赖，见 `tools/reflectData.py:6-41`。描述与报错文本“10 秒”不一致。 |
| `eyemMuscleModel_OneSecond` | 眼动/肌电伪迹二分类；逐秒，整次≤10 秒 | `SingleChannelEEG`; `muscle&eyem.pth` | 单导输入长度必须为 256 样本 | 训练数据来源源码未提供，见 `tools/singleChannel.py:11-62,64-135`。 |
| `seizureArtiBckgModel_OneSecond` | 背景/伪迹/癫痫三分类；逐秒，整次≤10 秒 | `SingleChannelEEG`; `seiz&arti&bckg.pth` | 单导、256 Hz、每段 256 样本 | 训练数据来源源码未提供，见 `tools/singleChannel.py:137-213`。 |
| `seizureNormalModel_OneSecond` | 非癫痫/癫痫二分类；逐秒，整次≤10 秒 | `SingleChannelEEG`; `seiz&normal.pth` | 单导、256 Hz、每段 256 样本 | 有 TUEV 评估代码，但源码未证明 TUEV 是训练集，见 `tools/singleChannel.py:216-281`、`TUEV_oracle_run.py:263-327`。 |
| `slowSeizBckgModel_TenSeconds` | 背景/慢波/癫痫三分类；完整 10 秒块 | `slowSeizureBckgEEG` 五模型软投票；`slow&seiz&bckg1.pth` 至 `5.pth` | 固定 22 导、256 Hz、每块 2560 样本 | 训练数据来源源码未提供，见 `tools/slowSeizBckg.py:25-88,90-132`。 |
| `normalAbnormalModel` | 整段病理正常/异常二分类 | `NormalAbnormalEEG`; `normal&abnormal.pth` | 固定 22 导；内部重采样至 100 Hz，截断/补零到 20 分钟 | 训练数据来源源码未提供，不应擅自标为 TUAB，见 `tools/normalAbnormal.py:10-62,64-110`。 |
| `sleepStageModel` | W/N1/N2/N3/R 五分类；30 秒 epoch | `SleepStage`; `sleepStage.pth` | 固定 2 导；模型内部将 30 秒拆为 15 段，代码按 `config.fs` 构造输入 | `eval/sleep/README:1-4` 明确 Sleep-EDF；通道为 Fpz-Cz/Pz-Oz，见 `eval/sleep/predeal.py:20-24`。 |
| `healthMDDModel` | 健康/MDD 二分类；5 秒块 | `healthMDD`; `health&MDD.pth` | 固定 19 导、256 Hz、1280 样本 | `eval/MDD/README:1-4` 明确 Figshare “EEG Data New”；通道见 `eval/MDD/predeal.py:10-18`。 |

随仓 `tools/localModels` 中共有 11 个 `.pth`：上述 6 个单权重文件加 5 个慢波/癫痫/背景集成权重。`eval/MDD/checkpoints/best_model.pth` 和 `eval/sleep/checkpoints/best_model.pth` 是另一组训练目录产物；工具实际加载的是 `tools/localModels` 下同任务命名的权重，不能仅凭文件名认定二者相同。

### 数据集与评估任务

- **TUEV 事件检测评估**：`TUEV_eval.py:12-33` 定义数据目录、正负类别和 22 导映射；`TUEV_eval.py:165-255` 通过 Agent 生成事件并按通道/时间评分。`TUEV_oracle_run.py:263-327` 绕过 LLM，直接调用 `seizureNormalModel_OneSecond`。这证明 TUEV 被用于评估，不证明模型训练来源。
- **Sleep-EDF 睡眠分期**：`eval/sleep/predeal.py:20-154` 读取 PSG/Hypnogram、选 2 导、生成 30 秒 epoch；`Sleep_eval.py:21-54` 要求每个 30 分钟片段返回 60 个 epoch 标签。
- **MDD/健康分类**：`eval/MDD/predeal.py:8-18,37-78` 选择 19 导闭眼 EDF，生成 5 秒、2.5 秒步长切片；`MDD_eval.py:7-32` 定义受试者及 Yes/No 问题。
- README 提到基础感知、时空探索、事件检测、交互和报告生成，但没有覆盖全部能力的自动化测试或统一任务 API。

## 4. EEG 数据真实调用链

### 默认 Agent/TUEV 风格链路

1. `EEGAgent.__init__` 使用 `os.path.join(config['dataPath'], file_name)` 生成路径（`main.py:15-20`）。
2. 固定调用 `dataLoad`，MDD/Sleep 加载器只是被注释的替代行（`main.py:22-26`）。
3. `dataLoad` 通过 `mne.io.read_raw_edf(..., preload=True)` 读取 EDF（`tools/dataLoad.py:27-31`）。
4. `preprocessing` 执行 0.5–70 Hz 滤波、60 Hz 陷波，并在原采样率不等于 256 Hz 时重采样（`tools/preprocessing.py:1-8`；参数来自 `config/config.json:4-7`）。
5. `get_data` 按固定 22 对 `bipolar_pairs` 查找 `EEG <电极>` 前缀并相减，得到 `[22, samples]` 或在缺导时得到不足 22 导的数据（`tools/dataLoad.py:9-24`；montage 位于 `tools/polar.py:1-13`）。
6. `registerData(data)` 把数组写入模块全局 `_register_data`（`tools/registerData.py:1-5`）。
7. 工具通过 `getRegisteredData(start, end, config)` 以 `start*config.fs:end*config.fs` 切片（`tools/registerData.py:7-15`）。
8. 基础工具直接计算数值；模型工具再按固定窗口构造 Tensor、前向推理并 softmax。
9. `handle_tool_calls` 收集返回值，`messageMerge` 用 JSON 文本追加到 assistant 消息，再进入下一轮 LLM（`main.py:66-93`）。

### MDD 和 Sleep 的旁路加载器

- `load_MDD_edf` 只选 19 个 `EEG <name>-LE` 单极导联，不执行通用预处理，也不验证采样率（`tools/dataLoad.py:33-38`）。
- `load_Sleep_edf` 只选 `EEG Fpz-Cz`、`EEG Pz-Oz` 两导，不执行通用预处理，也不验证采样率（`tools/dataLoad.py:40-45`）。
- 二者没有由任务 Profile 自动选择。若手工替换 `main.py:24`，其他 22 导工具仍会被注册并展示给 LLM，形成新的不兼容组合。

## 5. 状态共享、可复用性与外部依赖

### 显式和隐式状态

- `_register_data` 是进程级单例；新的 Agent 初始化会覆盖旧记录。并发 Agent、交错调用和多记录比较会产生串数据风险。
- `EEGAgent.messages` 保存 system/user/assistant 及拼接后的工具文本，是单实例会话状态（`main.py:40-44,55-58`）。
- 工具配置来自 `self.config` 的隐式自动注入（`main.py:75-77`），函数签名没有独立的数据或资源对象。
- `tools` 导入触发全部模型实例与权重加载，模型对象是模块级全局单例。
- 多处路径依赖当前工作目录：`config/config.json`、`data`、`RAG/faiss.index`、评估目录和输出目录。

### 可直接复用

- `FunctionRegistry` 的注册/查询思想及大部分元数据，可作为新注册表设计的输入，但 schema 类型需规范化。
- `preprocessing` 中的滤波、陷波和重采样步骤，可迁移为显式配置的纯处理步骤。
- `windowInfo` 中幅值、Welch PSD、相关系数/SSIM 算法，可在去除全局数据和固定 montage 后复用。
- `localModels/net.py` 的 RoPE/Attention 模块、各工具的模型类和 `vote.py::multi_model_predict` 可在输入契约测试通过后复用。
- `utils/tuev_metrics.py` 和 `TUEV_oracle_run.py` 的工具直测思路可用于无 LLM 基线评估。

### 需要封装后复用

- `dataLoad/get_data`：需显式报告缺失/重复通道、保留实际通道映射，并由 Profile 决定参考和 montage。
- 7 个模型工具：需把模块顶层加载改为惰性资源、声明精确 shape/采样率/窗口/标签/设备，并返回统一结构。
- Prompt 和 Agent 循环：需采用结构化工具消息或至少严格解析、前置参数校验、停止原因和 trace。
- RAG：需补齐并登记模型资源后才能启用；知识检索应是可关闭组件，不应在每个请求中重复加载模型。
- `baseInfo`：可保留轻量 EDF 元数据用途，但应优先使用 MNE 已解析信息并处理 EDF/EDF+、编码和异常头。

### 不建议直接复用

- `registerData.py` 的全局数据单例。
- `tools/__init__.py` 的递归全量导入策略。
- `reflectData` 当前返回原始 NumPy 数组的接口；它还可能向 LLM 注入大量波形数据。
- 三个 Agent 评估脚本的顶层执行结构和硬编码路径/密钥占位方式；应先提取成可参数化、可测试入口。

## 6. 主要耦合与已知问题

### 通道和参考耦合

- 默认链固定为 `tools/polar.py:1-8` 的 22 导双极 montage，并假定 EDF 通道名以 `EEG FP1` 等前缀开始。
- MDD 固定 19 导 `-LE`；Sleep 固定 2 个已成对的双极导联。
- `single_name2index` 和 `sleep_name2index` 在 `tools/polar.py:23,28` 错误地由通用 `index2name` 构建，目前虽未进入核心调用，但不能作为正确映射复用。
- `get_data` 静默跳过缺失导联，模型随后才以维度错误失败，缺少加载阶段的契约检查。

### 采样率和窗口耦合

- 默认配置把全部数据重采样到 256 Hz；单通道模型的 `LayerNorm(256)` 要求恰好一秒 256 样本。
- 慢波模型固定 22×2560；正常/异常模型固定 22 导并转换为 100 Hz、20 分钟；MDD 固定 19×1280。
- Sleep 工具模型卷积层实际要求 2 导，且 `LayerNorm(170/30)` 隐含每个内部片段的长度；但训练脚本 `eval/sleep/train.py:58-129` 使用的是另一种 EEGNet 结构，不能把训练 checkpoint 与工具模型混用。
- 时间参数只有最大窗口检查，普遍缺少负数、`end <= start`、记录越界、非整数和尾部不完整片段的统一校验。

### 格式、范式和路径耦合

- 运行时只读取 EDF；TUEV 评估另依赖 `.rec`，Sleep 依赖 Hypnogram EDF 注释，MDD 依赖文件名中的 `H`/`MDD` 和 `EC`。
- `MDD_eval.py:39-46` 只传文件名，而默认 `dataPath` 是 `data`，与 `eval/MDD/raw` 不一致；且 `agent.run` 返回字典，`MDD_eval.py:49` 却调用 `response.strip()`。
- `Sleep_eval.py:146-153` 同样只传 PSG 文件名，默认 `dataPath` 不指向 `eval/sleep/sleep-cassette`；主入口也不会自动使用 2 导加载器。
- `TUEV_eval.py:13,59-68,184-188` 的相对 EDF 路径会再次与 `config.dataPath` 拼接，存在 `data/data/edf/...` 风险；脚本还会写 `candidates` 和运行日志，不能作为只读测试。
- 工具 schema 中使用 `List[str]`、`Dict[...]` 等自定义字符串，而非标准 JSON Schema 类型。当前只将 schema 放进 Prompt，未由 SDK 校验。
- `messageMerge` 在工具函数执行的 `try` 外序列化整体结果；`reflectData` 返回 `np.ndarray`，会在回注阶段触发 `TypeError`。

## 7. 实际验证结果

验证使用 `C:\Users\Nick\.conda\envs\eegagent\python.exe`，未调用外部 LLM、未下载数据、未训练模型。

- 38 个 `.py` 文件可由 `ast.parse` 解析。
- `pip check` 返回 `No broken requirements found`；关键环境版本包括 MNE 1.6.1、NumPy 1.24.4、SciPy 1.10.1、OpenAI 2.2.0、PyTorch 2.14.1+cpu。
- 导入 `tools` 后得到 11 个注册工具。
- 随仓 `data/gped_049_a_6.edf`：原始 250 Hz、33 信号、241 秒；默认加载后为 `(22, 61696)`、`float32`，与重采样到 256 Hz 后的长度一致。
- 在该数据上成功运行：`compute_amplitude`、`compute_psd`、`compute_symmetry`、`seizureNormalModel_OneSecond`、`slowSeizBckgModel_TenSeconds`、`normalAbnormalModel`。
- 在同一默认数据上，`sleepStageModel` 报“期望 2 通道、实际 22 通道”；`healthMDDModel` 报“期望 19 通道、实际 22 通道”。这验证了主入口的数据链不具备任务自适应能力，不代表两个权重本身无效。
- RAG 初始化因缺少 BGE-M3 主模型权重失败并可被当前 Agent 降级捕获。
- 未执行外部 LLM 端到端调用，也未运行会写结果文件的评估脚本。

仓库包含历史 TUEV 结果：Agent 汇总记录 36 个文件、447 个 GT、hit rate 0.7383；oracle 汇总记录 159 个文件、2736 个 GT、阈值 0.7、hit rate 0.7431。它们依赖仓库中的既定评分协议和外部数据路径，本轮没有重新复现，因此只能标为“历史产物”，不得作为新基线结论或泛化性能。

## 8. 论文描述与实际实现边界

| 事项 | 当前状态 | 依据 |
|---|---|---|
| LLM 多轮工具调度 | 已实现但协议脆弱 | `main.py:95-146`、`utils/parseCalling.py:5-25`。 |
| 基础信息、时窗特征 | 已实现并完成样例直测 | `baseInfo.py`、`windowInfo.py`。 |
| 多种模型工具 | 代码和权重存在 | 7 个模型工具；只有部分能通过默认链运行。 |
| 多任务自动切换 | 未实现 | 主入口固定 `dataLoad`，没有任务 Profile。 |
| 结构化工具调用与强约束执行 | 未实现 | 使用 Prompt 文本和正则解析。 |
| EEG 报告模板生成 | 部分代码存在，当前 Prompt 未启用 | 模板已读取但未插入生效 Prompt。 |
| RAG 知识增强 | 代码存在，当前资源不完整 | BGE-M3 主权重缺失。 |
| EEG 数据状态感知与约束规划 | 拟研究，未实现 | 没有显式状态模型或约束规划器。 |
| EEG 证据驱动的自适应分析 | 拟研究，未实现 | 没有证据状态、停止准则或策略选择模块。 |
| ASD 辅助评估 | 未实现 | 当前源码未发现 ASD、TD、R3 任务代码。 |

## 9. 对最小基线的审计建议

首先保留算法与权重，不扩大模型范围；以显式 EEG 记录、任务 Profile、惰性工具资源和统一执行器替代隐式全局状态。第一条打通的完整链应是：EDF → 22 导 TUEV Profile → 基础特征 → `seizureNormalModel_OneSecond` → JSON 结果 → 可选 Agent 调度。Sleep 和 MDD 在各自 2 导/19 导 Profile、数据与权重契约验证前，不应出现在同一默认工具集合中。

最优先解决：

1. 数据契约和 Profile，消除全局数据及 22/19/2 导冲突。
2. 工具惰性加载、输入校验和 JSON 输出，形成真正可独立复用的工具接口。
3. 可复现路径、资源清单与无 LLM 自动化测试，再恢复 Agent 端到端评估。

## Issue55接口审计补记（2026-11-01）

`task_plan_agent.PlannedTaskStore`已共享分离辅助失败与必需结果；`TaskPlanController`仍复用原EEGAgent和Executor。`scientific_request_binding._request_frames/ground_bound_scope`的字面对象/异域约束导致T04/T07共同误拒，未解决；不可从DAG声明推断完整原请求。唯一运行时修正为拒绝不再计实际used。合成输入契约、依赖/寿命/限制、代码职责图及证据等级见[Issue55审计与协议](EEG_WORKING_MEMORY_ISSUE55_PROTOCOL_AND_RESULTS.md)。没有模型权重/真实数据依赖，没有新的数值算法。原历史审计和失败记录不改。
