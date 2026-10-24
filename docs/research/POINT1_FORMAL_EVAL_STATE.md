# 工作点一正式实验状态

更新时间：2026-10-24（Asia/Shanghai）

## 冻结边界

- Candidate 源码冻结提交：`921b04a561b27c2e68964d5f3f1e995ee08c8c6d`。
- 原协议骨架：`config/point1_formal_eval_protocol_v1.json`，SHA-256 `e6170f9c92905d56286c199140918f09726dffc1ac6db2d1afbf81cd2360c6ad`，保持不覆盖。
- 禁止新增 EEG 状态转换、Planner、科学规则或创新点；后续修改只允许实验夹具、独立 oracle/scorer、同规则基线、消融、运行器和研究文档。
- Draft PR：#11；研究分支：`research/point1-integrated-method-v0`。

## 当前阶段

Issue #16 的冻结协议、parsed-task holdout 与有界真实 DeepSeek 子集均已运行。原始记录保持不覆盖；当前进入逐例分析与论文判断，不再修改 Candidate 或科学 gold。

## 已识别的协议风险

1. Rereference 后指定参考通道数学上变为零，现有通道级 flatline 规则可能把全部 Epoch 标为质量异常；它是当前工具定义的可预期结果，不能把 `quality_usable=0` 自动解释为重参考非法。
2. 单 Epoch 只表示工具可计算，不表示频谱估计具有统计可靠性；正式 scorer 只核验计算与谱系，不评价临床/统计充分性。
3. `unsupported_profile`、`invalid_event_label` 等失败必须区分 intent、planning/preflight 与 Executor 层，不能用统一“安全失败”掩盖误拒或错误执行。
4. 原生 Agent 与 CIEDG 的最终回答形式不同，需要共享、独立的事实/工具结果 scorer；不能只给 CIEDG 使用结构化 Evidence Gate 优势。

## Development evaluator 修订（打开 holdout 前）

首次 dry run 原样保存为 `point1_formal_dev_dryrun.json`，暴露三项 eval-only 问题：

1. scorer 错误要求 selection 前 quality evidence 绑定筛选后的 effective artifact；修正为 role-aware provenance；
2. 质量输出省略零计数条件，gold 显式写 `0`；scorer 对请求条件补零后比较；
3. Strong Expert 未把成功 rereference transition 纳入 release evidence；补齐后与 Candidate 使用同一 answer evidence scorer。

这些修改没有改变 Candidate、EEG 工具、scientific threshold、case/gold 或 holdout。修订后 development Candidate 8/8、Expert 8/8；无 EEG guard 消融在 S04/R04 正确暴露 2 个未授权转换，其他无 fault 的 dev 消融未观察差异。

首次 holdout 启动在 Strong Expert 处理第一个 preflight rejection 时因 eval adapter 读取不存在的 `Plan.error_code` 而中止，未生成结果文件。字段修正为现有 `Plan.reason_code/reason`；这是使同规则 Expert 能表达冻结拒绝分支的运行器 Bug，不改变 case、gold、scorer 或任何方法输出。中止事实保留后重新从头执行一次完整 holdout。

## Holdout 与追加式协议审计

- 唯一完整 holdout：16 个 case × 6 种方法，共 96 行，原始文件 `point1_formal_holdout_v1.json`。
- 主评分：CIEDG 16/16，Strong Dynamic Expert 16/16；两者均为 76 次工具调用，未观察到 Candidate 相对同规则强专家的正确率或成本优势。
- whole-plan replay 为 88 次调用；without-dependency-invalidation 与 without-semantic-evidence-reuse 均为 79 次；without-EEG-guards 为 14/16，R05/R08 执行了未经充分指定/范围冲突的转换。
- 打开 holdout 后发现主 scorer 没有逐条执行全部冻结 trace invariant。没有回写主评分，而是新增 append-only `point1_formal_holdout_invariant_audit_v1.json`。
- 审计确认 S09 的源 Epoch 虽为新 ID/同 fingerprint，但 selection 派生 fingerprint 含随机 quality evidence ID，因此没有实例化预登记的“effective artifact 新 ID/同 fingerprint”；S09 标为 `protocol_invalid`，不能作为语义复用证据。
- 排除 S09 后，CIEDG 与 Strong Expert 均在 15/15 有效场景通过全部冻结不变量。R11 正确实例化不同 ID、相同 effective fingerprint，并观察到 CIEDG summary 语义复用。

## 真实 DeepSeek 子集

- 使用 S02、S06、R05、R11 四个合成场景；每个场景比较 CIEDG 与 Native Agent，共 8 行。
- 真实消耗 22 次请求、59,515 tokens，未发送原始 EEG 数组；未保存密钥、认证头或本地密钥路径。
- 初始汇总暴露两项 evaluator 问题：CIEDG 的 invalid answer gate 未纳入 accepted；Native 在只查询状态后要求补参被误归为 completed。保留原始 `point1_formal_real_llm_v1.json`，另以 `point1_formal_real_llm_audit_v1.json` 追加审计，不重跑、不改方法。
- 审计后 CIEDG 1/4，Native 0/4。CIEDG：S02/S06 因模型提交无关 `unknown_slots` 且缺 `analysis_type` 引证而澄清，R05 正确澄清，R11 工具/恢复正确但最终 evidence-answer schema 校验失败。Native：S02 未识别已有筛选授权，S06 静默丢失零可用 control 条件，R05 补参回答包含无证据数值，R11 未从 artifact expiry 恢复且回答声称已完成。
- 这些是真实失败，不以 Fake LLM 或提示词调参覆盖。

## 下一步

1. 完成逐例错误分类表及统计区间，明确协议无效 case。
2. 运行全量回归与 CI，不再追加 API 调用。
3. 形成工作点一 Conditional/No-Go 判断和论文可主张边界。

## 提交

- 阶段 A supplement SHA-256：`43e7fb634ff1eb246e2685a0831bf28c3bf08bed05f481bb36a8ebc5e45d49f2`。
- 阶段 A：`6661b65`（协议 supplement）与 `ffe9ee3`（development evaluator）。
