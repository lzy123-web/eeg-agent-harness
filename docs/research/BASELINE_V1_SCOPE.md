# EEG Agent Harness Baseline v1.0 范围冻结

## 1. 目的与冻结规则

本文件冻结 Issue #7 的 Baseline v1.0 能力边界与验收协议。目标是验证已有多任务 EEG Harness，而不是新增论文创新机制。任务集位于 `config/agent_baseline_v1_cases.json`，包含 development 18 项、holdout 12 项。冻结后不得为了提高真实 LLM 分数放宽 holdout 判据；若 Prompt 或工具描述修复后复测，必须同时保留初始结果和复测结果，并将 holdout 标记为已暴露。

冻结清单 SHA-256：`fd76e59c5127cac272d8fba0eaacc97a9dde9a7de1cdde4455c8f01e0ecdc075`。

自然语言请求不得直接写工具函数名、artifact 调用顺序或 JSON 参数。验收规则与请求文本分离，由确定性规则核验工具、参数、错误、artifact 传播和回答忠实度。

## 2. 能力矩阵

“成功”只表示对应列所述验证已完成，不代表临床有效性或跨数据集泛化。

| 任务族 | 工具可用 | Fake Agent | 真实 LLM + 合成 | 真实 EEG 离线 | 真实 LLM + 合规真实 EEG | 边界 |
|---|---|---|---|---|---|---|
| 记录信息 | 是 | 成功 | Issue #6 成功 | EEGAgent EDF/R3 成功 | 未验证 | 仅元数据 |
| 时间窗幅值 | 是 | 工具层成功 | 待本里程碑 | EEGAgent EDF 成功 | 未验证 | 必须显式通道和窗口 |
| Welch 频带功率 | 是 | 成功 | Issue #6 成功 | EEGAgent EDF/R3 成功 | 未验证 | 绝对功率，不是 ERD/ERS |
| annotation 列表 | 是 | 成功 | Issue #6 成功 | R3 成功；EEGAgent 样例无 annotation | 未验证 | 不解释标签科学语义 |
| annotation→Epoch→条件频带特征 | 是 | 成功 | Issue #6 成功 | 两份匿名 R3 成功 | 未验证 | 不是完整 ERP/evoked |
| 记录质量证据 | 是 | 工具层成功 | 待本里程碑 | 两份匿名 R3 smoke | 未验证 | 经验阈值未校准，无总分 |
| Epoch 质量与有条件筛选 | 是 | 工具层成功 | 待本里程碑 | R3 离线成功 | 未验证 | 仅按声明规则筛选，不自动替代科学目标 |
| 癫痫/非癫痫一秒窗模型 | 是，严格 `tuev_bipolar_22`/256 Hz/权重 | 成功 | 待合成兼容输入 smoke | 原 EEGAgent EDF+权重成功 | 未验证 | 训练来源源码未提供；非临床诊断 |
| R3 离线事件案例 | 应用层可用 | 不适用 | 禁止外发真实数据 | 两份匿名 EDF 成功 | 未验证且未授权 | 不推断 ASD/TD/标签 9 含义 |
| Sleep/MDD | 否 | 否 | 否 | 否 | 否 | Profile/资源契约未迁移 |
| 完整 ERP/evoked、统计推断 | 否 | 否 | 否 | 否 | 否 | 当前只有 Epoch 和事件窗频带功率 |
| ASD 分类/辅助评估 | 否 | 否 | 否 | 否 | 否 | 不属于通用基线 |
| 临床诊断 | 禁止 | 正确拒绝 | Issue #6 正确拒绝 | 禁止 | 禁止 | 所有输出仅研究用途 |

## 3. 数据场景

- `synthetic_event_native`：128 Hz、8 秒、`SYNTH-C1/SYNTH-C2`，含 `stimulus/control` 合成 annotation；允许外发元数据和派生结果。
- `synthetic_no_event_native`：同结构但无 annotation，用于验证无事件拒绝。
- `synthetic_tuev_22`：256 Hz、22 导双极通道名的确定性合成信号；只用于 Profile/模型调用协议 smoke，不解释模型概率。
- `local_eegagent_edf`：原 EEGAgent 样例与现有权重，只在本地离线执行，禁止发送 DeepSeek。
- `local_r3_edf`：用户合法持有的匿名 R3 文件，只在本地离线执行，禁止发送事件时间、路径、特征或受试者信息。

## 4. 冻结任务集与判定层次

30 个案例覆盖基础分析、事件相关、质量、模型可用性/推理和不支持任务：

- development：18 项，用于发现协议和通用 Prompt/Tool 描述缺陷；
- holdout：12 项，仅在冻结提交后运行；若据其结果修改实现，复测必须标记为 `holdout_exposed_after_initial_run`；
- 真实 DeepSeek 固定子集：14 项，覆盖两种 split、四个任务族和成功/拒绝/边界情形；
- Fake/Mock：运行全部 30 项，只验证协议与判定器，不作为自然语言模型性能。

逐例规则包含：允许/必需/禁止工具、预期完成或拒绝、参数约束、artifact 传播规则及回答安全检查。分层指标为：

1. 意图/任务类别是否符合人工目标；
2. 工具选择是否在允许集合且覆盖必需工具；
3. 参数、时间边界、Profile、资源和 artifact 依赖是否合法；
4. 执行是完成、正确拒绝还是错误失败；
5. 最终回答数值能否在 ToolResult 中追溯，是否出现 ERD/ERS、临床诊断或数据集语义越界；
6. 工具调用数、LLM 请求数、tokens、停止原因和错误根因。

## 5. 预算与隐私

- 真实联网运行硬上限：48 次 LLM 请求、120,000 tokens；达到任一阈值立即停止并保存已完成案例。
- 默认每案例最多 6 轮、8 次工具调用、单请求 768 输出 tokens、一次瞬态重试。
- 只允许合成数据进入真实 LLM Runner；本地 EEGAgent/R3 资源走独立离线命令。
- 报告不得含凭据、认证头、私密凭据位置、真实 EDF 路径、原始数组、事件时间表或受试者级结果。

## 6. 已知限制

- 质量阈值未跨设备或人工标注校准。
- 癫痫模型训练来源和许可证仍为源码未提供；合成输入输出没有科学解释意义。
- R3 的标签语义、参与者映射和分组尚未得到权威说明。
- 当前 TaskProfile、Schema 校验和工具集是 Baseline v1.0 范围，不代表任意 EEG 任务通用。
- 本里程碑不评价或修改状态约束 Planner、证据自适应 Pilot 的研究结论。
