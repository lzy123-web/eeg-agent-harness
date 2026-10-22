# 研究点一科学语义规划先导评估

## 1. 结论先行

本轮结论为 **NO-GO（针对当前 EEG 专属规划策略）**。

18 个首次运行前冻结的任务中，Strong Expert Conditional DAG、Generic Semantic Workflow Planner 与 Candidate EEG Semantic Planner 均达到：合法任务完成率 100%、正确安全拒绝率 100%、总体正确率 100%、holdout 正确率 100%、误拒 0、成功执行的语义非法操作 0、Executor 拒绝 0。三者均使用 25 次工具调用和 19 次状态查询。候选没有结果、调用成本或扩展维护上的独立优势。

最大事件时刻误差为 0.002625 秒，低于冻结的半个 128 Hz 采样周期 0.00390625 秒；这是合成事件和当前 MNE 路径的结果，不是对所有数据或重采样方法的零误差保证。

因此 H1、H2 均未得到相对强对照的支持。显式 scientific state、observability、branch 与 lineage 对三个场景有明确工程价值，但这些价值来自共享契约；通用 semantic planner 已能消费同一契约并达到完全相同结果。

## 2. 冻结协议

- 配置：`config/point1_semantic_planning_v1.json`
- 规范化 JSON SHA-256：`1e2de202eb91b76e3df32e133ad4bf37578be74d506f15b302b1a39d4ffb5d47`
- 冻结提交：`f14d20a`
- 任务：18（development 12、holdout 6）
- 预算：每例 8 工具调用、8 状态查询、1 恢复机会；本轮没有注入动态故障，三者均未使用恢复。
- 场景：原始/低通分支，重采样/events/Epoch 对齐，Epoch 筛选/试次数/lineage，以及跨场景组合和新 consumer。
- 结果：`docs/research/results/point1_semantic_planning_v1.json`

评估配置和预期在原型结果产生前提交并推送。它是仓库内 protocol freeze，不是公开 preregistration。

## 3. 公平对照

| 方法 | 合法完成率 | 正确拒绝率 | holdout | 误拒 | 语义非法成功执行 | 工具调用 | 状态查询 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Strong Expert Conditional DAG | 100% | 100% | 100% | 0 | 0 | 25 | 19 |
| Generic Semantic Workflow Planner | 100% | 100% | 100% | 0 | 0 | 25 | 19 |
| Candidate EEG Semantic Planner | 100% | 100% | 100% | 0 | 0 | 25 | 19 |

三者共享完全相同的 `SemanticArtifact`、`SemanticEffect`、operation contracts、合成场景、Executor、工具实现、科学 oracle 和预算。Expert 手写完整动态条件路径；Generic 使用 domain-neutral BFS；Candidate 只增加 EEG 目标相关搜索排序。没有限制 Expert 分支，也没有给 Candidate 更多状态或工具权限。

本地单次平均规划耗时分别约 0.043、0.073、0.071 ms，仅是非隔离 Windows 进程的描述值，不作显著性检验。Candidate 没有表现出延迟优势。

## 4. 独立 oracle 与三个场景

### 4.1 原始 50 Hz 与低通分支

oracle 直接检查实际输入 `EEGRecord.processing_metadata` 和注入频率，而非读取 Planner 自报“合法”字段。line-noise feature 只接受无低通/陷波处理的 raw payload；要求 40 Hz 处理的 bandpower 必须来自实际包含 `lowpass_filter(h_freq=40)` 的另一分支。raw 不存在时三个方法都在 plan-time 拒绝，没有把 filtered 分支低值解释成原始噪声。

### 4.2 重采样与事件对齐

运行时使用 MNE `Raw.resample(target, events=events)` 联合重采样。oracle 保存独立的源秒时刻，按请求标签筛选后与实际 `EpochSet.event_onsets_seconds` 比较。250→128 Hz 的非整数格点案例产生本轮最大误差 0.002625 秒；所有案例在声明容差内。

### 4.3 Epoch 筛选、数量与 lineage

oracle 从实际 `EpochSet.event_labels` 独立统计条件数，检查 feature 的直接父 artifact、显式 selection history 和 `source_epoch_artifact_id`。未授权筛选在 plan-time 拒绝；授权后不足最小试次同样拒绝。没有把选择后 feature 归因给未选择 Epoch。

本轮用显式排除索引验证语义，没有声称合成高幅 Epoch 或既有经验质量阈值是临床坏试次真值。

## 5. 失败、负结果与扩展性

所有预期拒绝案例均保存在逐例结果中：只有 filtered 数据却请求原始 50 Hz、缺 events、非法目标采样率、未授权筛选、筛选后试次不足。没有 planner 意外失败，也没有 Executor 兜底拒绝；因此无法利用错误恢复场景区分方法。

新 `epoch_variance` consumer 模拟只需共享契约和 runtime 各一个接入点。方法特定修改点：Expert 2、Generic 0、Candidate 1。该观察来自单开发者、单 consumer，且 Generic 的修改少于 Candidate，因此 **不支持 H2 相对通用方法的维护优势**；不能外推为实际团队工时。

完全持平不是“证明三种方法普遍等价”。它说明在这组最小可解释任务中，科学知识主要由声明式契约贡献，EEG 专属搜索排序没有可测额外价值。

## 6. H1/H2 判断

- **H1：不支持。** Candidate 能正确组合未写死的多步骤任务，但 Generic 和 Strong Expert 在同规则下同样正确，非法执行均为 0。
- **H2：不支持。** Candidate 接入扩展没有比 Generic 少改动；调用数完全相同。相对本轮 procedural Expert 只少一个方法特定修改点，但证据过弱，且不能建立相对主要通用对照的优势。

## 7. 可复现命令

```powershell
$env:PYTHONPATH = "$PWD\src"
& $python -m eeg_harness.research.semantic_planning.cli `
  --suite config\point1_semantic_planning_v1.json `
  --output artifacts\point1_semantic_planning.json
& $python -m eeg_harness.research.semantic_planning.cli `
  --demo branch --output artifacts\point1_branch_demo.json
& $python -m eeg_harness.research.semantic_planning.cli `
  --demo events --output artifacts\point1_events_demo.json
& $python -m compileall -q src tests
& $python -m unittest discover -s tests -v
```

两个 demo 分别显示 raw/processed 分支和 resample→Epoch→condition feature。CLI 不调用 LLM、不读取真实 EEG，也不下载资源。

## 8. 验收与 Baseline 回归

- `pip check`：通过。
- `compileall`：通过。
- 无私有资源：137 项中 125 通过、12 项按设计跳过。
- 提供原 EEGAgent 合法本地 EDF/权重：137 项中 134 通过、3 项（R3 2、真实联网 1）按设计跳过。
- 原 EDF、模型权重仅用于既有离线回归；没有进入结果文件或 Git，也没有发送外部服务。
- 未调用真实 DeepSeek：本轮研究目标是 deterministic scientific planning，语言理解会混入额外变量；Issue 将真实 LLM 列为可选而非验收前提。
- Baseline v1 的冻结配置、3/15 初始真实 LLM 结果、5/5 development 复测及历史 JSON 均未改动。

## 9. 论文证据边界与决策

可写入论文的方法学/负结果：显式科学 artifact/observability/branch/lineage 最小建模、三类受控反例和独立 oracle、与同规则强对照完全持平的负结果。

不能写成论文证据：不能称 Candidate 为已成立创新点一；不能从合成案例推断真实 EEG/临床/多数据集泛化；不能把 100% 当自然语言 Agent 性能；不能声称重采样普遍零误差或质量阈值已校准；不能把单开发者修改点当维护成本显著性证据。

**最终决策：NO-GO。** 停止继续扩展这条“EEG 专属搜索排序”具体实现。若后续重新开启研究点一，最小新证据应来自真实复杂 workflow、独立开发者/盲测扩展、多种通用规划器仍无法表达的 EEG 约束，并在新的未见协议下验证；否则显式科学语义层只应定位为 Harness 工程保障。
