# 工作点一正式实验状态

更新时间：2026-10-23（Asia/Shanghai）

## 冻结边界

- Candidate 源码冻结提交：`921b04a561b27c2e68964d5f3f1e995ee08c8c6d`。
- 原协议骨架：`config/point1_formal_eval_protocol_v1.json`，SHA-256 `e6170f9c92905d56286c199140918f09726dffc1ac6db2d1afbf81cd2360c6ad`，保持不覆盖。
- 禁止新增 EEG 状态转换、Planner、科学规则或创新点；后续修改只允许实验夹具、独立 oracle/scorer、同规则基线、消融、运行器和研究文档。
- Draft PR：#11；研究分支：`research/point1-integrated-method-v0`。

## 当前阶段

Issue #16 阶段 A：24 个登记场景已补齐 append-only case supplement、自然语言、fixture、fault、gold 和 lineage invariants，并冻结 hash；准备实现独立 oracle/scorer。在 development 校验前不打开 holdout。

## 已识别的协议风险

1. Rereference 后指定参考通道数学上变为零，现有通道级 flatline 规则可能把全部 Epoch 标为质量异常；它是当前工具定义的可预期结果，不能把 `quality_usable=0` 自动解释为重参考非法。
2. 单 Epoch 只表示工具可计算，不表示频谱估计具有统计可靠性；正式 scorer 只核验计算与谱系，不评价临床/统计充分性。
3. `unsupported_profile`、`invalid_event_label` 等失败必须区分 intent、planning/preflight 与 Executor 层，不能用统一“安全失败”掩盖误拒或错误执行。
4. 原生 Agent 与 CIEDG 的最终回答形式不同，需要共享、独立的事实/工具结果 scorer；不能只给 CIEDG 使用结构化 Evidence Gate 优势。

## 下一步

1. 实现独立 fixture/oracle/scorer、完整 selection+rereference Strong Expert 及预注册消融。
2. 仅运行 8 个 development 校验实验基础设施；审查后锁定 evaluator，再一次性打开 16 个 holdout。
3. 保存逐例 raw trace、分层错误类型和预算；最后形成 GO / Conditional / NO-GO 判断。

## 提交

- 阶段 A supplement SHA-256：`43e7fb634ff1eb246e2685a0831bf28c3bf08bed05f481bb36a8ebc5e45d49f2`。
- 阶段 A：待提交。
