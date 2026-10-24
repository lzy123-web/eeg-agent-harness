# EEG 科学意图编译器 v1 有界实验结果

日期：2026-10-24（Asia/Shanghai）

## 1. 实验边界

- 协议：30 例，开发 14、holdout 16；本轮联网只预选 8 个开发例和 9 个 holdout 例。
- 冻结哈希：`b14fcb611ac2f8c854fb5b543860f2e76597be4b4e13ddf576f6ce95d544af9f`。
- 输入：确定性合成 EEG 的去波形元数据；没有发送 EEG 数组、实验室数据、受试者信息或 gold。
- 因果控制：一次模型输出同时进入冻结 v0 validator 和 v1 compiler，不为两个方法分别采样。
- 模型条件：`thinking=disabled`、`max_tokens=900`、同 prompt、同 tool schema、同记录状态；客户端未显式设置 temperature，使用服务端默认。
- 人工标注：仅 1 名审核者，没有第二独立审核，不报告一致性系数。

本次共 31 次 chat-completion 请求、56,776 tokens；另有 1 次 `/models` 只读发现调用。合计 32 次服务端调用，未超过 Issue 规定的 32 请求与 80,000 tokens 上限。

## 2. 模型身份核实

2026-10-24 的 `/models` 实际返回 `deepseek-flash` 与 `deepseek-v4-pro`。所有实验 response body 的 `model` 字段分别回报相同标识。官方更新页在该日期把它们描述为 DeepSeek-V4.1-Flash-1017 与 DeepSeek-V4-Pro-0813；API 响应本身没有返回更细粒度权重哈希。

Issue #16 历史日志只保存请求别名 `deepseek-chat`，没有保存 response body 的 `model`。因此历史实际后端保持 `unknown`，不能追认成上述任一版本。

## 3. 开发诊断（不作为 holdout 成绩）

| 指标 | deepseek-flash，8 例 |
|---|---:|
| 请求 / tokens | 8 / 14,628 |
| 严格原始字段全对 | 3/8 |
| v0 决策正确 | 4/8 |
| v1 决策正确 | 7/8 |
| raw-correct 条件下 v0 | 1/3 |
| raw-correct 条件下 v1 | 3/3 |
| dangerous accept | v0 0；v1 0 |

I14 的原始输出把 `quality_measurement` 错写成未注册的 `epoch_quality` 语义概念，并额外产生禁止项。修正 scorer 后该例归为基座模型 schema 错误，而不是 Harness 误拒。没有据此放宽 compiler。

## 4. 一次性 holdout 模型对照

同一组 9 例为 H01、H03、H04、H05、H06、H10、H11、H13、H14。

| 指标 | deepseek-flash | deepseek-v4-pro |
|---|---:|---:|
| 请求 / tokens | 9 / 16,157 | 9 / 15,829 |
| 严格原始字段全对 | 2/9 | 3/9 |
| v0 决策正确 | 2/9 | 2/9 |
| v1 决策正确 | 5/9 | 3/9 |
| raw-correct 条件下 v0 | 1/2 | 2/3 |
| raw-correct 条件下 v1 | 2/2 | 2/3 |
| v0 dangerous accept | 0 | 0 |
| v1 dangerous accept | 1 | 1 |

该小样本、单次采样不支持模型能力排名。它只说明“换成 Pro”没有自动解决本协议问题：Pro 出现把候选参考误判为已授权等高风险参数错误；Flash 也有目标缺失、未支持任务误分类和额外禁止项。

## 5. 关键失败归因

### 基座模型意图错误

- H01：两个模型均遗漏或错误组织质量先决目标/语义概念，属于原始任务分解错误。
- H10：两个模型都没有稳定将 ERD/ERS + 认知判断识别为当前未注册任务。
- H05 Pro：把“candidate reference / if appropriate”解释成明确重参考授权；这是高风险参数错误。
- 多例产生用户没有表达的 `forbidden_operations`。v1 会以请求侧规范禁止项覆盖它们，但 scorer 仍把它们记录为模型字段错误。

### Harness 必须承担的错误

- H14 在两个模型上都被 v1 错误执行。请求要求“重参考前质量 + 重参考后功率”，应澄清为双阶段分支；候选的 mixed-stage 检查没有覆盖英文 `before re-referencing` 形态。由于这是 holdout，未后验补规则，原始 dangerous accept 保留。
- H05 Flash 得到正确澄清槽；Pro 的错误授权载荷虽最终被另一语义检查拦截，但错误码是 `analysis_type` 而非 `rereference_authorized`，说明失败解释仍不稳定。

### 评价器错误（已在打开 holdout 前修复）

开发首版 scorer 没有直接比较模型禁止项和语义概念 schema，曾把 I14 错归为 Harness。修复后同时报告原始字段和 validator 决策，避免用候选终态掩盖模型错误。

## 6. 真实 Agent 闭环

使用 `deepseek-flash` 和合成 EEG 执行两例，共 4 请求、10,162 tokens：

| 案例 | 链路 | 结果 |
|---|---|---|
| I10 连续 PSD | Intent → v1 compiler → Planner/Executor → `psd` → Evidence Gate | completed；answer valid；evidence closed |
| I01 事件质量筛选 | Intent → v1 compiler → CIEDG → `list_events → create_epochs → epoch_quality → select_quality_epochs → epoch_summary → event_bandpower` → Evidence Gate | completed；3 个 Epoch 中筛除 1 个，保留 2 个；answer valid；evidence closed |

两例 response model 均为 `deepseek-flash`。这是工程闭环证据，不代表 9 例 holdout 的失败被修复，也不代表临床或多数据集有效性。

## 7. 可复现文件

- 开发原始记录：`docs/research/results/eeg_intent_compiler_v1_dev_flash.json`
- Flash holdout：`docs/research/results/eeg_intent_compiler_v1_holdout_flash.json`
- V4 Pro holdout：`docs/research/results/eeg_intent_compiler_v1_holdout_v4_pro.json`
- 真实 Agent：`docs/research/results/eeg_intent_compiler_v1_real_agent_flash.json`

结果文件保留逐例请求、原始 IntentSpec、字段评分、v0/v1 决策、compiler diagnostics、用量与返回模型标识；不含密钥、认证头、波形或私人路径。
