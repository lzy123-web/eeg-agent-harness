# 多任务 EEG Agent Baseline v1.0 完整验收报告

## 1. 验收结论

Issue #7 的 A→E 已完成。Baseline v1.0 具备统一 EEGRecord/Profile/Registry/Executor/Context/Trace、11 个工具、确定性离线工作流、Fake/Mock 回归和真实 DeepSeek 原生 Tool Calling。真实 EDF+模型、本地 R3 与真实 DeepSeek 合成链均已分别验证；没有把未经授权的真实 EEG 发送到外部 API。

本次不实现新的 Planner、证据自适应、ASD 评估、模型训练或 RAG，也不形成论文创新点的 Go/No-Go 结论。

## 2. A：能力与协议冻结

- 冻结 30 个自然语言案例：development 18、holdout 12。
- 请求不含注册工具名、函数调用顺序或 `artifact_id` 参数提示。
- 15 项真实 DeepSeek 子集覆盖基础、事件、质量、模型和不支持任务。
- 每项预先声明允许/必需/禁止工具、参数、预期完成/拒绝/澄清、artifact 流和回答检查。
- 规范化 JSON SHA-256：`e1713cda4c90c073d3b1290dc9af8df8cfa6788b88c969a310b3660884654ae1`。

阶段提交：`e320d3c`。完整矩阵见 `BASELINE_V1_SCOPE.md`。

## 3. B：自主工具选择 Runner

`eeg_harness.baseline_v1` 使用同一 `EEGAgent → ToolRegistry → Executor → ExecutionContext`，没有引入 Prompt 文本路由。生产 Prompt 只声明通用安全、最小必要工具、缺参澄清和 artifact 来源原则；事件任务的具体调用顺序由模型依据工具契约决定。

Runner 支持：

- `fake`：执行全部 30 项，Case-aware protocol double 仅验证执行器与判定器，不计入 LLM 性能；
- `real`：只执行冻结的 15 项合成子集，或用 `--case-id` 有界复测；
- 三种合成场景：Native 有事件、Native 无事件、22 导/256 Hz 兼容模型协议；
- 全局 48 请求/120k tokens、每例 6 轮/8 工具调用限制；
- 逐例保存 ToolResult、Trace、参数、usage、停止原因与判定；cost 因未从 API 得到可靠金额而保持 `null`。

Fake/Mock 30/30 通过只证明协议闭环。阶段提交：`a8eefd7`。

## 4. C：本地真实资源链

### 原 EEGAgent EDF 与权重

- Profile：`tuev_bipolar_22`；输出 `[22,61696]`、256 Hz。
- `record_info → psd → seizure_detection` 全部成功并留下 Trace。
- FP1-F7 `[0,1)` 秒的 PSD 与历史回归一致；模型原始输出 `Non-seiz=0.0, seiz=1.0`。
- 该值只是现有权重在单一窗口的工程输出，不是性能指标或临床诊断。

### 两份匿名 R3 EDF

- 两份均为 21 通道、300 Hz，事件→Epoch→绝对频带功率、记录质量、Epoch 质量均完成。
- 匿名 A：81 个事件、72 个有效 Epoch、0 个边界拒绝。
- 匿名 B：96 个事件、60 个有效 Epoch、0 个边界拒绝。
- 未解释 ASD/TD、标签 1–9 或目录语义；未执行组间统计。

阶段提交：`44ab04a`。脱敏结果见 `results/baseline_v1_local_resources.json`。

## 5. D：真实 DeepSeek 自然语言鲁棒性

模型为 `deepseek-flash` 非思考模式。所有请求只使用合成 EEG；没有外发真实路径、事件、特征、数组或受试者信息。

### 首次冻结子集

| 指标 | 结果 |
|---|---:|
| 案例 | 15（development 8、holdout 7） |
| 严格通过 | 3/15 |
| 必需工具被尝试 | 15/15 |
| 禁止工具未调用 | 15/15 |
| 正确完成/拒绝/澄清 | 15/15 |
| 参数检查 | 6/6 |
| artifact 精确传播 | 3/3 |
| 回答安全/忠实检查 | 20/20 |
| 仅使用冻结允许工具集合 | 3/15 |
| LLM 请求 | 37 |
| Tokens | 72,358 |

严格失败 12 项全部保留。主因是模型额外调用了 `record_info`，部分事件任务又增加 `epoch_quality`；这些调用通常安全且结果正确，但违反预先冻结的最小允许集合，因此不得事后算作通过。

首次结果还暴露两个判定器缺陷：拒绝任务中的安全只读观察被错误计为“未拒绝”，以及“不能解释为 ERD/ERS”的否定句识别过窄。修正判定器后严格结果仍为 3/15，因为多余工具问题独立存在。

### 有界修复与复测

通用 Prompt 改为直接使用已有 `RECORD_METADATA`，只调用解决目标所需的最小工具。没有添加识别验收语句的路由。只复测 5 个 development 失败案例：PSD、缺参澄清、无事件拒绝、质量检查、合成兼容模型；5/5 通过，9 请求、16,819 tokens。

holdout 没有复测，并明确标记为初始运行后已暴露；不能声称修复后留出集准确率。全程合计 46 请求、89,177 tokens，低于 48/120k 上限。

阶段提交：`9ffb7fd`。逐例结果见 `results/baseline_v1_deepseek_evaluation.json`。

## 6. E：完整回归

- Python 3.10.17；MNE 1.6.1、NumPy 1.24.4、SciPy 1.10.1、PyTorch 2.14.1+cpu。
- `pip check`：通过。
- `compileall`：通过。
- 有合法本地 EDF/权重/R3 样例：124 项，123 通过、1 项真实联网测试默认跳过。
- 无私有资源：124 项，112 通过、12 项按设计跳过。
- 真实 DeepSeek 网络测试保持 opt-in，GitHub Actions 不配置密钥。

## 7. 三类完整示例的性质

1. **真实 DeepSeek + 合成 EEG**：自主选择记录、幅值、PSD、事件、质量及合成兼容模型工具；这是协议/自然语言工程验收。
2. **真实 EDF + 现有权重，本地离线**：22 导/256 Hz 一秒癫痫模型链；这是工具资源契约验证，不是模型性能验证。
3. **真实 R3，本地离线**：事件、Epoch、绝对频带特征和质量；这是数据适配与执行链验证，不是 ASD/TD 或实验效应验证。

三者不能互相替代。`真实 LLM + 合规真实 EEG` 仍为未验证，因为当前没有将实验室数据外发的治理授权。

## 8. 当前支持边界

已支持：EDF Native 基础信息/幅值/PSD、annotation/Epoch/事件绝对频带功率、经验质量证据与显式筛选、严格 22 导 Profile 的现有癫痫窗口模型、R3 应用层离线事件链、Fake 与 DeepSeek 原生 Tool Calling。

不支持或未验证：Sleep/MDD、完整 ERP/evoked/统计推断、ASD 分类或综合评估、临床诊断、多数据集泛化、真实 LLM+真实 EEG、模型性能/泛化、质量阈值临床校准、并发和大规模语言鲁棒性。

## 9. 下一步判断

Baseline v1.0 已足够作为后续论文实验的稳定工程底座。下一阶段不应继续无边界扩充 Harness；应转向 EEG Agent、scientific workflow、Agent Harness 与 EEG 方法文献梳理，基于可验证科学问题重新筛选研究贡献，并使用独立冻结数据与强基线评估。
