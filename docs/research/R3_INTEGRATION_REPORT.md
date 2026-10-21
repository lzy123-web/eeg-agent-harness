# R3 集成与真实事件验证报告

## 1. 范围与结论

本报告对应 GitHub Issue #2。R3 被实现为通用 Harness 之外的应用适配层；没有实现 ASD 分类、临床诊断、论文候选创新机制或新模型训练。

本地真实资源可以访问。只读诊断与匿名单文件工作流证明了数据结构和工程调用链可运行，但不足以确认实验范式、标签含义、参与者身份或临床分组。因此，本里程碑不报告组差异、单人特征、分类性能或医学结论。

## 2. 实际核验事实

对本地两个资源目录共 69 个 EDF 逐文件读取，得到以下可公开事实：

| 项目 | 实测结果 |
|---|---|
| EDF 文件数 | 69 |
| EEG 通道 | 每文件 21 个，布局一致 |
| 其他可读信号 | `Status`，由 MNE 识别为 stim，不纳入 EEG 数组 |
| 采样率 | 全部 300 Hz |
| annotation 标签 | 字符串 `1`–`9` |
| 单文件事件数 | 40–116 |
| 单文件时长 | 108–406 秒 |

上述结果来自 EDF 本身。文件夹名和文件名不被作为参与者或临床组映射依据。

未能从 EDF 或现有统计表权威确认：

- “细动作”实验范式及标签 1–8 的动作/条件定义；
- 标签 9 是否必然是 Boundary；现有统计文件仅提示“可能”；
- 两个目录对应人群的正式纳排、诊断与参与者映射；
- 采集参考、设备说明和推荐预处理方案。

## 3. 配置与适配边界

`R3_PROFILE` 位于 `src/eeg_harness/applications/r3/adapter.py`，配置：21 个观察通道、300 Hz、1–40 Hz 带通、50 Hz 陷波、平均参考。`R3DatasetRules` 配置标签 1–8 为当前分析集合、标签 9 为 Boundary 候选、Epoch `[-0.2, 0.8)`、baseline `[-0.2, 0)`。

通道与采样率是文件事实；滤波、参考、Epoch、baseline 和标签排除规则是 Issue 指定的可复现分析配置，科学适用性尚未确认。标签 9 的规则没有进入通用 `EEGRecord`、`TaskProfile`、Registry 或事件工具。

外部 CSV 事件表只在 R3 应用层支持，要求 `onset_seconds`、`label`，可选 `duration_seconds`，并通过显式 offset 对齐记录起点；来源记录为表内容 SHA-256，不从文件名补全语义。

## 4. 实际调用链

```text
显式 EDF → read_edf → R3_PROFILE/configured_native → EEGRecord
       → ExecutionContext → ToolRegistry/Executor
       → list_events → create_epochs → epoch_summary → event_bandpower
       → version/config/input hash/ExecutionTrace
```

`event_bandpower` 的定义是：对每个 1 秒完整 Epoch 计算 Welch PSD，对配置频带积分，再在同一 condition 的 Epoch 间算术平均。baseline 仅执行时域均值校正；该输出不是 baseline-normalized ERD/ERS。

## 5. 真实运行结果

从两个资源目录各显式选择一个匿名 EDF 运行相同链路：

| 匿名输入 | EEG 通道/采样率 | 总事件 | 标签 1–8 有效 Epoch | 边界拒绝 | 状态 |
|---|---:|---:|---:|---:|---|
| 样例 A | 21 / 300 Hz | 96 | 60 | 0 | 完成 |
| 样例 B | 21 / 300 Hz | 81 | 72 | 0 | 完成 |

表中不包含路径、文件名、参与者 ID、输入哈希或单文件特征。两个样例只证明工作流兼容性；A/B 不代表已确认的人群分组。

## 6. 受试者级聚合

`aggregation.py` 要求调用者显式提供 `record_key`、`participant_id`、可选 `group` 和有限数值特征。算法先对同一参与者的多记录求均值，再对参与者等权计算组描述，避免把 Epoch 或记录当作独立受试者。

当前本地资源没有可采用的权威映射表，因此真实受试者聚合与组间比较未执行。代码不会依据文件名或目录名自动补充分组。

## 7. 隐私与可复现性

- EDF、统计表、真实派生特征和本地输出均不进入 Git。
- Trace/bundle 记录 Harness 版本、Profile、参数、处理步骤、输入 SHA-256、事件来源、Epoch 接受/拒绝和终止原因，不记录原始数组或原始路径。
- `public_workflow_summary` 进一步移除 record-level 频带特征和事件 onset，只保留去标识计数。
- GitHub Actions 不访问真实数据，只运行合成与无资源回归。

## 8. 遗留问题

1. 获取权威实验方案，确认标签 1–9、Boundary、任务窗口、baseline 与预处理依据。
2. 获取明确的记录—参与者—组映射后，才能运行受试者级聚合；需要先审计重复记录和缺失记录。
3. 在解释事件特征前增加坏道/坏段、伪迹与数据质量协议，并建立固定真实验证子集。
4. 频带功率不是完整 ERP、时频 ERD/ERS 或统计推断；这些能力仍未实现。
