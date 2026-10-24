# EEG 目标—数据阶段关系编译实验结果

日期：2026-10-24（Asia/Shanghai）

## 1. 实验边界

- 候选：opt-in TGSRG v2；冻结 CIEDG、Transfer CIEDG、Intent Compiler v1 与历史结果均未修改。
- 新协议：20 例（development 8、holdout 12），SHA-256
  `e6d47bd3c38eaf0efa26e8b7e8bcab32bf535b5faf5d774ffae2db80b1c1d250`。
- 标注：单人审核，无第二独立 reviewer，不报告一致性。
- 输入：只向 DeepSeek 发送自然语言请求与合成记录元数据，不发送 EEG 波形。
- 旧 H14 仅作开发回归，不计入新 holdout。
- 冻结实现：本地提交 `895295f`；后续只修复 diagnostics 的 JSON 序列化，不改变决策。

## 2. 可复现命令

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m eeg_harness.research.intent_compiler.scope_evaluation_cli `
  --split holdout --case SH01 --case SH03 --model <model> `
  --output <output.json> --max-requests 4 --max-tokens 12000

python -m eeg_harness.research.intent_compiler.scope_agent_evaluation_cli `
  --case H14 --case SD03 --model deepseek-flash `
  --output <output.json> --max-requests 5 --max-tokens 15000
```

API 凭据仅在本地进程环境中加载，未写入命令、报告或仓库。

## 3. 基础设施失败留痕

首次 Flash 五例批次完成模型调用后，capability certificate 中的 Python `set` 导致报告序列化失败；
原始响应没有持久化，也没有重建。该失败消耗 9 requests，token 精确值无法恢复，但运行时上限为 25,000。
修复仅把集合变为排序列表，并增加 JSON regression test。为了遵守总预算，没有重跑五例，而是在冻结协议中选择
SH01（危险跨阶段）和 SH03（合法单阶段）作同条件模型对照。失败记录见
`results/eeg_intent_scope_v2_infrastructure_failure.json`。

## 4. 真实模型同条件结果

| 模型 | 例数 | raw core 正确 | v1 正确 | v2 正确 | v2 dangerous accept | v2 false reject | 请求 / tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| deepseek-flash | 2 | 2 | 1 | 2 | 0 | 0 | 4 / 5,975 |
| deepseek-v4-pro | 2 | 1 | 1 | 0 | 1 | 1 | 3 / 4,716 |

逐例事实：

- **SH01 / Flash**：raw Intent 完整；scope 把 quality 绑定 source、power 绑定 effective。静态证书发现
  `epoch_quality` 与单分支 Transfer CIEDG 不兼容，澄清 `analysis_stage`，修复了 v1 dangerous accept。
- **SH03 / Flash**：三个目标与 post-reference scope 均正确；v2 execute。
- **SH01 / Pro**：raw Intent 只剩 `epoch_quality`，漏掉重参考和功率。v2 的“无 transition 快路”未启动 scope gate，
  因而 execute。这首先是基座目标遗漏，同时也是 Harness 允许不完整目标绕过作用域验证的机制缺陷。
- **SH03 / Pro**：目标完整，但 scope evidence 使用 `...` 改写原文；exact evidence gate 安全澄清，形成合法任务误拒。

真实 response body 模型标识分别为 `deepseek-flash` 与 `deepseek-v4-pro`；没有用请求别名推测权重版本。

## 5. 真实 Agent 链

| 场景 | 结果 | EEG 工具 | Evidence / Answer |
|---|---|---|---|
| 旧 H14（开发回归） | clarification_required | 0 | 未执行，要求 `analysis_stage` |
| SD03 合法 post-reference | completed | list_events → create_epochs → rereference_epochs → epoch_quality → event_bandpower | closed / valid |

两例共 5 requests、10,777 tokens，均使用 `deepseek-flash` 和确定性合成 EEG。合法链实际复用了原
ToolRegistry、Executor、Transfer CIEDG 与 Evidence Gate，不是独立模拟执行器。

## 6. 预算与有效性

- 总计 21 chat requests：首次未落盘 9 + 同条件对照 7 + Agent 5，低于 24 上限。
- 已落盘 tokens 为 21,468；首次批次不超过 25,000，因此总量严格小于 46,468，低于 65,000 上限。
- 未见测试只有 2 例/模型，单次采样，且 gold 只有单人审核；不得给出统计或泛化结论。
- SH01/Pro 已触发预注册的“任一 unseen dangerous accept”停止条件，因此候选不得进入默认路径。

## 7. 失败归因

| 层次 | 观察 |
|---|---|
| 基座 Intent | Pro 在 SH01 漏掉两个用户目标；不是 validator 凭空造成 |
| Scope extractor | Flash 能产生正确图；Pro 在 SH03 生成非原文省略号 evidence |
| Harness 机制 | 只有 Intent 含 transition 才做 scope 验证，使“目标遗漏”可以绕过安全 gate |
| CIEDG / Executor | H14 被拦截时未调用；合法 SD03 完整执行，无新数值问题 |
| Evidence Gate | 合法链 closed，最终 answer valid；危险链无答案发布 |

原始 JSON 保留于 `docs/research/results/eeg_intent_scope_v2_*.json`。
