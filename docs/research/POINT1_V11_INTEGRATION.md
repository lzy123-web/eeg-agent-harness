# CCEP/LRSP v1.1 集成与验证报告

更新时间：2026-10-23（Asia/Shanghai）

## 1. 集成边界

LRSP v1.1 作为 opt-in `point1-v11` 模式接入现有链路：

```text
自然语言
  → 原有 Intent Interpreter / 语义一致性检查
  → immutable task + obligation ledger
  → StateAwareConstrainedPlanner 静态科学 preflight
  → CIEDG residual planner
  → 原有 ExecutionContext / ToolRegistry / Executor
  → 真实 EEG event/quality/selection/summary/bandpower tools
  → Evidence Gate / 最终引用解析
```

没有建立第二套 Executor，没有修改 Baseline v1、CCEP v0 或 LRSP v1 的默认模式。LLM 仍只负责解释请求和提交 evidence references；依赖、授权、质量 guard、artifact 失效和恢复由确定性运行时决定。

## 2. v1.1 相对 v1 的真实算法变化

| 维度 | LRSP v1 | LRSP v1.1 |
|---|---|---|
| 目标表示 | `next_action/_goal_status/apply_result` 专用字段与分支 | `GoalContract` + 请求目标依赖闭包 |
| consumer | 仅 `event_bandpower` | `epoch_summary` 与 `event_bandpower` 共享 effective Epoch |
| 完成证据 | 专用结果字段 | 通用 `GoalEvidence`，绑定输入/输出、上游 token、参数与模式 |
| 失效 | 手写质量/选择/功率撤销列表 | 从 dependency token 和 artifact binding 自动传播 |
| 身份重建 | 依赖 consumer 全部重放 | 内容与上游语义等价时仅恢复纯 consumer evidence |
| 计划 frontier | 固定事件顺序 | 依赖闭包中优先级最高的 ready residual goal |

`trial_selection` 仍是 EEG-specific resolver：它检查明确授权、质量 evidence、每请求条件至少一个 usable Epoch，并选择 identity/derived 分支。这是科学 guard，不强行抽象为任意通用 transition。

## 3. 新支持的任务组合

在 v1 已有事件质量/筛选/频带功率上，v1.1 增加：

- 授权筛选后同时获取试次摘要和绝对频带功率；
- 明确禁止筛选时，测量质量但让多个 consumer 共同使用 original Epoch；
- clean 数据使用 identity transition，让两个 consumer 共享原 artifact；
- 多条件任务中任一条件零 usable 时阻断全部 destructive/downstream 操作；
- 派生 artifact 身份丢失后局部重建，并在内容等价时保留已完成纯 consumer 证据。

仍不支持任意 EEG 工具自动组合、ERP/ERD-ERS、统计检验、临床结论或跨数据集泛化。当前 bandpower 是 whole-Epoch Welch 绝对功率，不是 baseline-normalized ERD/ERS。

## 4. 确定性验证

### 4.1 真实工具链与 oracle

- 异常索引 `[1]` 的三试次合成记录实际从 3 筛到 2；
- `epoch_summary` 与 `event_bandpower` 读取同一 selected artifact ID/fingerprint；
- 派生数组逐样本等于独立 oracle；全部通道/频带值等于独立 SciPy Welch oracle；
- 禁止筛选时二者读取 original artifact 且摘要保持 3 个试次；
- changed-content repair 不命中缓存；content-equivalent repair 将 summary 调用从 2 次降为 1 次；
- `ARTIFACT_NOT_FOUND` 与 `ARTIFACT_STATE_CONFLICT` 结构化返回，无 traceback 外泄。

### 4.2 Fake LLM

固定三例全部完成，6 次协议调用：异常+授权双 consumer、异常+禁止筛选双 consumer、clean+授权 summary。完整轨迹在 `docs/research/results/point1_v11_fake.json`。

### 4.3 真实 DeepSeek

仅使用确定性合成 EEG；三例均完成，6 次请求，18,253 tokens（prompt 14,951、completion 3,302），低于预设 8 请求/20,000 tokens 上限。三例 Evidence Gate 均 closed，最终引用检查均 valid：

| 用例 | selection | 工具调用 | 结果 |
|---|---|---:|---|
| one-bad + 授权 + 双 consumer | derived | 6 | completed |
| one-bad + 禁止筛选 + 双 consumer | none/original | 5 | completed |
| clean + 授权 + summary | identity | 4 | completed |

完整脱敏轨迹在 `docs/research/results/point1_v11_deepseek.json`。这只证明三个合成请求的真实 tool-calling 闭环，不是准确率、泛化或临床验证。

### 4.4 回归

- `compileall`：通过；
- `pip check`：无 broken requirements；
- 全仓：199 tests，187 passed、12 个私有资源/联网 gated skipped、0 failed；
- v1.1 定向：9 tests 全通过；此前 v1/CCEP 测试未删除或放宽。

## 5. 可复现入口

```powershell
$env:PYTHONPATH = 'src'
$python = 'python'

# 无联网固定三例
& $python -m eeg_harness.research.integrated_method.v11_evaluation `
  --output artifacts\point1_v11_fake.json

# 真实服务仅在临时环境变量配置后运行；只使用模块内置合成 EEG
& $python -m eeg_harness.research.integrated_method.v11_evaluation --real `
  --max-requests 8 --max-tokens 20000 `
  --output artifacts\point1_v11_real.json

# 完整回归
& $python -m compileall -q src tests
& $python -m unittest discover -s tests -v
```

## 6. 已知问题

1. contract 表仍是有限注册能力，不是任意工具效果推理器。
2. 强 Expert 诊断目前覆盖无故障匹配路径，尚未冻结与 CIEDG 完全同恢复规则的正式故障套件。
3. quality evidence ID 含执行实例 artifact ID，导致两次独立执行的 provenance fingerprint 不同；科学输出比较需剥离瞬时 ID。
4. fingerprint 为全数组 SHA-256；本机 2.88 MB EpochSet 中位约 1.88 ms，但更大数据仍需评估。
5. 缓存仅限当前任务内无副作用 consumer，未做跨进程持久化与并发事务。
