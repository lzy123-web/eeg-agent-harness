# 工作点一正式实验状态

更新时间：2026-10-23（Asia/Shanghai）

## 冻结边界

- Candidate 源码冻结提交：`921b04a561b27c2e68964d5f3f1e995ee08c8c6d`。
- 原协议骨架：`config/point1_formal_eval_protocol_v1.json`，SHA-256 `e6170f9c92905d56286c199140918f09726dffc1ac6db2d1afbf81cd2360c6ad`，保持不覆盖。
- 禁止新增 EEG 状态转换、Planner、科学规则或创新点；后续修改只允许实验夹具、独立 oracle/scorer、同规则基线、消融、运行器和研究文档。
- Draft PR：#11；研究分支：`research/point1-integrated-method-v0`。

## 当前阶段

Issue #16 阶段 A/B 边界：独立 fixture/oracle/scorer、selection+rereference Strong Expert、CIEDG adapter 和四项预注册消融已实现。8 个 development case 已运行；Candidate/Expert 各 8/8 通过共享 scorer。Evaluator 修订已锁定，下一步才允许一次性打开 holdout。

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

## 下一步

1. 提交并锁定 evaluator/Expert 的 dev 版本与测试。
2. 一次性运行 16 个 holdout × Candidate/Expert/四消融，不再修改方法或 gold。
3. 运行相同请求的 Native/CIEDG 真实 DeepSeek 分层子集，保存 provider failures。
4. 汇总逐例错误、成本和 Wilson 区间，形成 GO / Conditional / NO-GO 判断。

## 提交

- 阶段 A supplement SHA-256：`43e7fb634ff1eb246e2685a0831bf28c3bf08bed05f481bb36a8ebc5e45d49f2`。
- 阶段 A：待提交。
