# 多任务 EEG Agent 最小可运行基线方案

## 1. 目标与边界

基线目标是建立与具体疾病和数据集解耦的 EEG Agent Harness，使同一套执行框架可以加载 EEG、校验任务条件、运行基础分析和至少一种本地模型推理，并留下可复现的执行记录。

第一阶段只支持 EDF、基础 EEG 分析、时间窗事件检测和一种已存在的癫痫模型推理。ASD 仅作为后续应用案例；ERP/诱发电位、候选论文机制、新模型训练和大型数据集接入均不进入第一阶段。

## 2. 最小架构与接口

### 2.1 显式 EEG 数据对象

新增通用 `EEGRecord`（或等价 `EEGContext`）数据契约，至少包含：

- `data: float32[C, T]`；
- `sfreq: float`，表示数组的真实采样率；
- `channel_names: list[str]` 和规范化后的通道映射；
- `montage/reference` 描述；
- `duration_seconds`；
- EDF 头元数据和来源路径；
- 已执行的预处理步骤及参数；
- 数据/任务 Profile 标识，但不得在通用类中编码数据集标签。

数据对象由会话显式持有并传入工具，禁止使用 `_register_data` 一类进程级全局数据。切片统一通过 `record.slice(start_s, end_s, channels)` 或等价服务完成，负责时间和通道校验。

### 2.2 Loader 与 Profile

- `EDFLoader` 只负责读取原始记录、标准化元数据和通道名，不隐式决定任务。
- `PreprocessingPipeline` 根据 Profile 执行滤波、陷波、重采样、参考变换和通道排序，并记录 provenance。
- `TaskProfile` 声明：必需/可选通道、参考方式、目标采样率、窗口长度、允许工具、模型输入 shape 和标签语义。
- 第一阶段只实现 `tuev_bipolar_22` Profile：复用现有 22 对双极 montage、0.5–70 Hz、60 Hz 陷波和 256 Hz 目标采样率。
- Sleep 的 2 导 Profile、MDD 的 19 导 Profile 只登记为后续工作，不在默认 Agent 中暴露相关工具。

### 2.3 Tool Registry 与 Executor

Registry 只保存工具描述、标准 JSON Schema、兼容 Profile、资源声明和惰性工厂，不在发现阶段导入所有模型权重。

统一工具接口建议为：

```text
execute(context: EEGContext, request: ToolRequest) -> ToolResult
```

`ToolResult` 必须仅包含 JSON 可序列化值，并带有工具名、输入窗口、使用通道、结果、警告、模型/权重标识和耗时。Executor 在调用前统一检查：

- 工具是否兼容当前 Profile；
- 通道是否存在且顺序正确；
- `0 <= start < end <= duration`；
- 窗口长度和步长；
- 采样率、输入 shape 和 dtype；
- 权重是否存在且校验值匹配；
- 输出能否序列化。

失败统一返回带错误码的结构化结果，例如 `INVALID_CHANNEL`、`OUT_OF_RANGE`、`INCOMPATIBLE_PROFILE`、`MODEL_RESOURCE_MISSING`、`MODEL_INPUT_MISMATCH`；不把 Python traceback 直接交给 LLM。

### 2.4 Agent 与执行追踪

- 保留 OpenAI 兼容客户端和最多 N 轮的有界循环。
- 优先使用服务端支持的结构化 tool calling；如需兼容文本协议，应使用严格 parser 和 schema 校验，不再依赖单个非贪婪正则。
- Agent 只看到与当前 Profile 兼容且资源就绪的工具。
- 每轮记录用户目标、模型、Prompt 版本、工具请求、校验结果、工具返回、停止原因和耗时，形成 `ExecutionTrace`。
- RAG 保持可选；资源不完整时在初始化阶段报告禁用状态，不在每次请求中重复尝试加载。

## 3. 原模块处理策略

### 保留并优先迁移

- `tools/preprocessing.py` 的滤波、陷波、重采样顺序。
- `tools/polar.py` 的 22 导 montage，作为 `tuev_bipolar_22` Profile 默认值，而不是全局唯一 montage。
- `tools/windowInfo.py` 的幅值、Welch PSD、相关/SSIM 算法。
- `tools/singleChannel.py::SingleChannelEEG` 与 `seizureNormalModel_OneSecond` 对应权重。
- `tools/localModels/net.py`、`vote.py` 的模型组件。
- `utils/tuev_metrics.py` 与 `TUEV_oracle_run.py` 的工具直测和事件级评分思路。

### 调整后复用

- `dataLoad.py` 拆分为读取、通道规范化、montage 和预处理步骤；缺导必须显式失败。
- `register.py` 改为标准 schema、兼容 Profile 和惰性资源注册。
- 所有工具去除 `getRegisteredData`，改为显式上下文和统一结果。
- 模型在首次调用对应工具时加载，并缓存于会话安全的资源管理器。
- `main.py` 拆分为 Agent、Executor、LLM adapter 和 trace；路径与模型名称配置化。
- `baseInfo.py` 迁移到统一 EDF 元数据读取结果，避免再次手工解析同一文件。

### 暂不直接复用

- `registerData.py` 全局状态。
- `tools/__init__.py` 全量递归导入。
- `reflectData` 原始数组直返接口。
- 当前 MDD/Sleep/TUEV Agent 评估脚本的顶层批处理和硬编码路径。
- 不完整的 BGE-M3 本地目录及其自动运行路径。

## 4. 第一阶段任务与数据资源

### 基础 EEG 分析

- 记录基本信息：实际采样率、时长、通道和预处理说明。
- 指定通道/时间窗幅值特征。
- 指定通道/时间窗频带 PSD。
- 指定左右导联对的相关性和 SSIM。

### 时间窗事件检测

- 首个模型工具为癫痫/非癫痫逐秒概率，复用 `seiz&normal.pth`。
- 在契约测试完成后，再逐项启用背景/伪迹/癫痫、眼动/肌电和慢波/癫痫/背景工具。
- 事件输出统一为通道、开始时间、结束时间、类别概率、阈值及模型标识。
- Milestone 2 已实现通用 annotation→Epoch→事件频带功率链及 baseline 校正；尚未实现 evoked/ERP 平均、峰值和统计推断，因此不得将当前能力表述为完整 ERP 分析。

### 所需资源

- 开发冒烟测试使用仓库现存 `data/gped_049_a_6.edf`，不得把它视为完整评估集。
- 模型推理使用现存 `tools/localModels/seiz&normal.pth`，记录 SHA-256；训练来源标记“源码未提供”。
- 事件级正式验证需要用户合法取得的 TUEV EDF/REC 测试数据，数据路径由配置提供；本阶段不下载。
  - LLM 测试需要通过环境变量提供 OpenAI 兼容服务凭据；无凭据时仍必须能运行确定性的工具层测试。2026-10-22 已以 `deepseek-flash` 非思考模式完成合成数据真实 Tool Calling 验收，未发送真实 EEG。

## 5. 分阶段实施与验收

### 阶段 0：审计冻结与环境基线

- 交付工具、权重、数据集、依赖和已知问题清单。
- 固定一个可复现 Python 环境及只读资源检查命令。
- 验收：源码事实均有文件/函数/行号，未知来源无推断，外部 LLM 和历史结果明确标注。

### 阶段 1：确定性 EEG Core

- 实现 `EEGRecord`、EDF loader、`tuev_bipolar_22` Profile、预处理和显式切片。
- 迁移幅值、PSD、对称性和癫痫/非癫痫工具；输出统一 JSON。
- 验收：同一 EDF 在无 LLM 条件下得到 22 导、256 Hz 数据；三个基础工具和一次一秒癫痫推理成功；重复运行 shape、通道顺序和结果一致；所有结果通过 `json.dumps`。

### 阶段 2：受约束 Agent Harness（基础运行时已实现）

- 建立惰性 Registry、Executor、LLM adapter 和 ExecutionTrace。
- 只向 Agent 暴露与当前 Profile 兼容的第一阶段工具。
- 验收：合法请求在限定轮数内完成；非法通道、负时间、倒置/越界窗口、缺失权重和错误维度均返回预期错误码；没有进程级 EEG 全局状态。

2026-10-21 实施状态：`TaskProfile`、惰性 Registry、Executor、ExecutionContext、ExecutionTrace、OpenAI 兼容客户端与 Fake LLM Agent Loop 已实现。此处“受约束”仅指固定 Profile/Schema 的工程校验和有界循环，不代表候选论文机制“状态感知与约束规划”已经实现。

### 阶段 3：事件评估与回归

- 参数化工具直测脚本，固定阈值、事件合并和评分协议。
- 在授权的 TUEV 子集上分别评估工具层与 Agent 层，保存配置、trace 和汇总。
- 验收：同一输入可复现；工具能力与 Agent 规划误差分开报告；指标计算有单元测试；历史结果不自动继承为新基线。

### 后续阶段

- Sleep：完成 2 导 Profile、确认实际工具权重与模型结构、用 Sleep-EDF 验证后启用。
- MDD：完成 19 导 `-LE` Profile、受试者级聚合与数据划分审计后启用。
- 完整 ERP/evoked、ASD 综合应用、状态感知规划和证据驱动自适应分析仍需在稳定基线之后单独立项。

## 6. 最优先的三个问题

1. **数据契约与 Profile**：消除 `_register_data`，解决 22/19/2 导、参考和采样率冲突。
2. **工具生命周期与契约**：工具发现不加载全部权重，调用前校验，结果保证 JSON 化。
3. **可复现验证**：统一配置和路径，先建立无 LLM 测试与资源清单，再恢复 Agent 端到端评估。

## 7. 明确不在第一阶段的内容

- 不训练或引入新模型。
- 通用层不实现 ASD/TD/R3 专有逻辑；已验证的数据集专有规则只能放入独立应用适配层。
- 不在最初阶段实现 ERP/诱发电位流水线；后续 Milestone 2 仅增加通用 Epoch 和事件频带特征，仍不宣称完整 ERP 已实现。
- 不实现候选论文创新机制。
- 不恢复或下载缺失的 RAG 大模型权重。
- 不把研究模型输出包装成临床诊断结论。

## 8. 2026-10-21 实施对照说明

本次代码基线按“复现优先、最小改动”完成了阶段 1 的一个受限版本，实际代码位于 `src/eeg_harness`：

- 已迁移原 EEGAgent 的预处理顺序、22 导双极 montage、EDF 派生逻辑、幅值、PSD、RoPE 模型组件和癫痫/非癫痫单通道模型。
- 已增加无 LLM CLI、外部资源路径、SHA-256、运行环境和 JSON 结果记录。
- 模型权重和测试 EDF 没有复制到正式项目；通过命令行参数或环境变量引用原始项目资源。
- 2026-10-21 的第二次阶段 1 实施已新增通用 `EEGRecord`，由正式 pipeline 显式传入幅值、PSD 和癫痫推理工具；统一切片负责通道、时间顺序、空窗和记录长度校验。`legacy/register_data.py` 只作为迁移来源保留，正式链路和测试不再导入它。
- `EEGRecord`、两个 `TaskProfile`、统一 Registry/Executor、ExecutionTrace 和结构化 Tool Calling Agent Loop 已实现，构成基础运行时 MVP；真实 DeepSeek 已完成基础信息、PSD、事件 artifact 链和安全拒绝四项合成验收。完整的 Profile 插件机制、真实事件评估和多数据集验证仍未实现。
- Milestone 2 在同一运行时上新增 `EventSet/EpochSet`、四个事件工具、会话 artifact 和合成数据验证；原癫痫工作流保持不变。真实带事件 EDF 与多数据集泛化仍未验证。
- Milestone 3 新增 `applications/r3`，以通用 configurable-native Profile 复用同一 Registry/Executor/Context 事件链。真实 R3 文件已验证结构和链路，但任务语义、分组依据和科学假设未确认，不能据此声称多数据集泛化或 ASD 评估已经实现。

## 9. Milestone 3 实施补充

- 通用 `TaskProfile` 增加可配置选导、滤波、陷波、平均参考和采样率适配；核心层没有标签 9、ASD、TD 或 R3 分组判断。
- R3 应用层显式声明 21 个已观察 EEG 通道与 300 Hz 契约。`1–40 Hz`、`50 Hz` 陷波、平均参考、`[-0.2, 0.8)` Epoch 及 `[-0.2, 0)` baseline 是当前可复现配置，不是从 EDF 头推导的实验真值。
- 标签 9 仅在 `R3DatasetRules` 中作为 Boundary 候选排除，状态为“科学含义未验证”；标签 1–8 的动作/条件含义也未确认。
- 受试者聚合强制使用显式 `record_key → participant_id → group` 映射，先对同一参与者的记录求均值，再进行可选组描述；没有映射时拒绝组间分析。
- 当前事件频带功率定义为 whole-Epoch Welch PSD 后按条件算术平均，属于绝对事件窗频带功率，不是 ERD/ERS。

当前确定性入口为 `python -m eeg_harness.cli`，自动化入口为 `python -m unittest discover -s tests -v`。真实样例已验证 22 导、256 Hz、幅值、PSD、模型二分类输出和 JSON 序列化；缺失权重会抛出明确的 `ModelResourceError`。

## 10. Milestone 5 实施补充

- `ToolSpec` 已能声明 Artifact 依赖、状态观察与前置条件；Planner 从声明发现 Epoch 生产者和 consumer，不再在契约构建器中维护工具名映射。
- 自然语言结构化目标桥是可选层；Executor 仍是最终安全边界，原生 Tool Calling Agent 没有被替换。
- v2 强 Expert 与 Planner 结果持平，禁止在论文中写成 Planner 已优于规则基线。当前 No-Go 只否定已证实的性能优势，不否定继续研究可维护性问题。
- 后续实验必须修正动态 Profile 留出案例，使用真实任务日志或独立开发者扩展试验，并将意图解析与计划/执行误差分开。真实 LLM 未验证前不得报告自然语言 Agent 性能。
