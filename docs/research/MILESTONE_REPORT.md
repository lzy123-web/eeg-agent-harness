# EEG Agent Harness 基础运行时 MVP 里程碑报告

## 范围与边界

本里程碑按 A→B→C→D 建立通用 EEG Harness 基础运行时。它不包含 Constraint Planner、Evidence-Driven Policy、ASD 评估、模型训练、RAG 或新增数据集验证。原始 EEGAgent 的许可证状态仍未明确，本项目不据此声明可自由再许可。

## 阶段 A：TaskProfile 与通用数据适配

状态：已完成。

- 新增通用 `TaskProfile`、`tuev_bipolar_22` 和 `edf_native`。
- EDF 读取与 Profile 适配分离；原生 Profile 保留选定 EDF EEG 通道及原始采样率。
- 22 导 Profile 继续使用原滤波、陷波、重采样和双极派生逻辑，真实样例输出仍为 `(22, 61696)`、256 Hz。
- 癫痫工具兼容性绑定到 `tuev_bipolar_22`，不通过通道数量推断适用性。
- `compileall` 通过；15 项测试通过，包含缺导、错误采样率、Profile 不兼容和两类真实 EDF 适配测试。

Commit：`4c07b20`（`实现 TaskProfile 与 EDF 数据适配`）。

## 阶段 B：Tool Registry 与 Executor

状态：已完成。

- 建立 `ToolSpec`、`ToolRequest`、`ToolResult`、`ToolRegistry` 和统一 `Executor`。
- 注册基础信息、幅值、PSD、癫痫推理四个标准工具；Native Profile 只暴露前三个。
- Registry 查询只返回工具元数据，不加载模型权重；癫痫权重仅在对应工具实际执行时惰性加载。
- Executor 在算法调用前校验 Profile、参数、通道、时间窗、采样率和模型资源。
- 所有结果均可 JSON 序列化；错误以稳定错误码返回，不向上层暴露 traceback。
- `compileall` 通过；22 项测试通过，包含真实 EDF 与真实权重的 Executor 推理。

Commit：`a27b16c`（`建立工具注册与安全执行器`）。

## 阶段 C：执行状态与可复现工作流

状态：已完成。

- 新增每任务独立的 `ExecutionContext`，持有 `EEGRecord`、Profile、Executor、结果映射和调用历史。
- `ExecutionTrace` 记录序号、工具、解析后参数、校验/执行状态、输出摘要、耗时、结构化错误和终止原因。
- 支持通过显式 `$result` 引用读取前一步结果；引用不存在或路径错误时返回 `RESULT_REFERENCE_ERROR`，不推断数据转换。
- 新增确定性 Workflow 与 CLI：EDF → 基础信息 → PSD →（仅兼容 Profile）癫痫推理。
- Reproducibility bundle 保存 Profile、采样率、通道、shape、处理步骤、配置、请求、结果和 Trace，不保存原始 EEG 数组。
- `compileall` 通过；27 项测试通过，包含上下文隔离、结果引用、非法工具后恢复、轨迹序列化和真实多工具工作流。

Commit：将在阶段提交完成后回填。

