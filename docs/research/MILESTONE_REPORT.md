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

Commit：将在阶段提交完成后回填。

