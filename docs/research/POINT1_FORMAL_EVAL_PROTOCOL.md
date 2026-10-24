# 工作点一正式公平实验协议（冻结版）

冻结日期：2026-10-23

机器可读协议：`config/point1_formal_eval_protocol_v1.json`  
SHA-256：`e6170f9c92905d56286c199140918f09726dffc1ac6db2d1afbf81cd2360c6ad`

## 1. 目的与当前状态

本协议用于后续比较 CIEDG、同规则强动态 Expert 与原生 Agent。本轮只冻结设计并运行两个开发 calibration；正式 24 例和留出结果**尚未执行**，不得将 calibration 写成正式优越性结论。

## 2. 任务与分层

共 24 例：质量筛选 family 12 例、显式重参考 family 12 例；每类 4 例 development、8 例 holdout。覆盖授权/禁止/缺参、科学前提错误、正常状态转换、artifact 丢失、同 ID 内容变化、不同 ID 内容等价和 consumer transient failure。

开发集只允许检查实现与评分器。协议冻结后，不根据 holdout 结果改提示、规则、case 或阈值；若必须修改，升版 protocol ID、记录原因并把原结果保留。

## 3. 公平条件

- 三种方法看到相同自然语言、EEG 元数据和工具 schema；
- CIEDG 与原生 Agent 使用同一模型、temperature、请求/token 上限；
- CIEDG 与 Expert 使用相同 Registry/Executor、科学规则、故障反馈、16 次工具调用和 2 次恢复预算；
- Expert 获得完整合法动态分支、semantic reuse 和 state validation，不被削弱；
- 离线 oracle 和预期结局只供 evaluator，运行时不可见；
- 所有 LLM-facing EEG 为 deterministic synthetic，不发送真实受试者数据。

## 4. 指标

主要指标：科学正确终态、goal/evidence closure、provenance 正确性、未授权/不安全转换率。次要指标：工具调用数、恢复数、正确澄清率。不能用单一 completion rate 代替科学正确性。

结果必须同时报告每 case、family 宏平均、失败类型和置信区间；24 例规模较小，统计检验仅作描述，不宣称稳定泛化。

## 5. 消融

预注册四项：移除依赖失效、移除 semantic evidence reuse、整图重放、移除 EEG 科学 guard。消融必须保持相同模型和预算；“无 guard”若产生更高完成率但有非法转换，按安全失败记录。

## 6. 冻结纪律

协议文件的 hash、提交和分区共同构成冻结点。后续执行脚本只能读取协议，不能在运行中改 expected outcome。真实 LLM 原始响应、解析失败和负结果均保留；不在 holdout 上反复调 Prompt。
