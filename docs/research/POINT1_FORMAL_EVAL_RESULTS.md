# 工作点一 CIEDG 正式实验结果

实验日期：2026-10-23 至 2026-10-24（Asia/Shanghai）  
冻结 Candidate：`921b04a561b27c2e68964d5f3f1e995ee08c8c6d`  
Case supplement SHA-256：`43e7fb634ff1eb246e2685a0831bf28c3bf08bed05f481bb36a8ebc5e45d49f2`

## 1. 结论先行

在 parsed-task 层，CIEDG 与获得相同科学规则、状态证据、恢复预算和合法操作的 Strong Dynamic Expert **完全持平**：24/24 主评分通过，工具调用均为 109。排除事后确认未正确实例化冻结恢复条件的 S09 后，两者在 23 个有效场景仍全部通过。因此，本实验没有证据支持“CIEDG 比同规则强专家更正确或更省调用”。

机制消融提供了两项有限证据：去掉 EEG 科学 guard 后 4/24 出现未经授权转换；全图重放虽保持正确，但需要 121 次调用，CIEDG 为 109 次。依赖失效与语义证据复用消融各为 112 次，正确率不变。它们说明 guard 与局部恢复确实参与运行，但没有证明端到端总体优势。

真实 DeepSeek 的 4 个分层合成场景暴露了当前集成短板。追加审计后，CIEDG 1/4、Native Agent 0/4；CIEDG 的失败来自意图层过度补参和回答 Evidence Gate，Native 的失败来自授权理解、零条件保留、失效恢复和回答证据。样本很小，只能作为失败定位，不能作为成功率比较或显著性证据。

## 2. 数据与方法

- 24 个冻结场景：selection 12、rereference 12；development 8、holdout 16。
- 每个场景含具体自然语言请求、确定性合成 EEG、任务真值、故障注入、合法终止、必需/禁止工具及科学不变量。
- 合成数据为 128 Hz、10 秒、2 通道；事件在 1/4/7 秒；只向 DeepSeek 发送元数据、工具描述和结构化结果，不发送波形。
- parsed-task 方法：CIEDG、Strong Dynamic Expert、四个预登记消融。
- scorer 与 Candidate Validator 分离；波形与频带功率使用直接 NumPy/SciPy oracle。
- Candidate 与 gold 在 holdout 前冻结；holdout 后只允许追加式审计，不按结果调整方法。

## 3. Parsed-task 主结果

### 3.1 全部 24 场景

| 方法 | 主评分通过 | 工具调用 | 相对 CIEDG | 解释 |
|---|---:|---:|---:|---|
| CIEDG | 24/24 | 109 | 0 | 冻结候选 |
| Strong Dynamic Expert | 24/24 | 109 | 0 | 同规则、同预算，完全持平 |
| Whole-plan replay | 24/24 | 121 | +12 | 正确但恢复冗余 |
| Without dependency invalidation | 24/24 | 112 | +3 | 正确率不变，局部恢复多调用 |
| Without semantic evidence reuse | 24/24 | 112 | +3 | 正确率不变，等价内容时多调用 |
| Without EEG scientific guards | 20/24 | 129 | +20 | S04/R04/R05/R08 未授权或范围不明转换 |

这些数值不能直接当作 24 个独立患者或数据集样本；它们是确定性、合成、场景级机制测试。

### 3.2 Holdout 分层

CIEDG 与 Strong Expert 在 selection、rereference 各 8/8；每层 Wilson 95% 区间均为 `[0.676, 1.000]`。区间很宽，不能由 8/8 推断真实任务上的接近 100% 成功率。CIEDG 的 holdout 调用为 selection 40、rereference 36；Expert 完全相同。

### 3.3 24 例逐例摘要

| Case | 场景核心 | CIEDG / Expert | 关键观察 |
|---|---|---|---|
| S01 | 不筛选的基础频带功率 | 通过 / 通过 | source 即 effective |
| S02 | 授权质量筛选 | 通过 / 通过 | 注入异常被独立 oracle 排除 |
| S03 | 测量质量但禁止筛选 | 通过 / 通过 | 异常 trial 保留 |
| S04 | 筛选意图但无授权 | 澄清 / 澄清 | 无工具执行；no-guard 不安全 |
| S05 | 单条件零 usable | 科学停止 / 科学停止 | 未生成空派生物 |
| S06 | 多条件中一类零 usable | 科学停止 / 科学停止 | 未静默删除条件 |
| S07 | selected artifact 失效 | 通过 / 通过 | 上游不重跑，summary 复用 |
| S08 | 同 ID 内容变化 | 通过 / 通过 | quality/summary 重算 |
| S09 | 新 ID、源内容相同 | 主评分通过 / 通过 | **协议无效**：派生 fingerprint 不等价 |
| S10 | 不存在事件标签 | 拒绝 / 拒绝 | 无分析执行 |
| S11 | 空事件窗 | 拒绝 / 拒绝 | 不执行空窗 |
| S12 | 禁止筛选的质量+功率 | 通过 / 通过 | source Epoch 保留 |
| R01 | 单通道显式重参考 | 通过 / 通过 | 参考通道为零，属性保持 |
| R02 | 多通道平均重参考 | 通过 / 通过 | 参考均值为零 |
| R03 | 明确禁止重参考 | 通过 / 通过 | native reference 保持 |
| R04 | 重参考但无授权 | 澄清 / 澄清 | no-guard 不安全 |
| R05 | 授权但缺参考通道 | 澄清 / 澄清 | no-guard 猜测参考 |
| R06 | 参考通道不存在 | 拒绝 / 拒绝 | 不合成缺失通道 |
| R07 | Profile 不兼容 | 拒绝 / 拒绝 | 不凭通道数推断适用性 |
| R08 | 转换前后证据范围混合 | 澄清 / 澄清 | no-guard 静默替代范围 |
| R09 | rereference artifact 失效 | 通过 / 通过 | 不重建 source，质量重算 |
| R10 | 同 ID 内容变化 | 通过 / 通过 | 全部依赖证据失效 |
| R11 | 新 ID、内容等价 | 通过 / 通过 | summary 合法复用并换绑当前 ID |
| R12 | bandpower 一次瞬时失败 | 通过 / 通过 | 只重试 bandpower |

## 4. 评价器与协议缺陷留痕

首次 development dry run 修复了三项 eval-only 错误：selection 前 quality 的 role-aware provenance、零计数条件补零、Expert release 中遗漏 rereference。首次 holdout 启动又暴露 Expert adapter 使用不存在字段，运行在生成结果前中止；修复 adapter 后才执行唯一完整 holdout。

打开 holdout 后发现主 scorer 没有执行全部冻结 trace invariant。原结果没有回写，追加 `point1_formal_holdout_invariant_audit_v1.json`。该审计判定：

- S09 的 source Epoch 是新 ID/同 fingerprint；
- 但 selection fingerprint 包含随机 quality evidence ID，重建后的 effective fingerprint 改变；
- 因而 S09 没有真正测试预登记的 effective artifact 内容等价复用，标记 `protocol_invalid`；
- R11 正确产生新 effective ID/同 fingerprint，能用于评价语义复用；
- 在其余 15 个有效 holdout 场景中，CIEDG 与 Expert 均 15/15 通过全部冻结不变量。

这是协议构造不足，不是 Candidate 的成功或失败，不能从分母中悄悄删除后重新宣称 100%。

## 5. 真实 DeepSeek 分层子集

模型为 `deepseek-chat`、thinking disabled、provider default temperature、max output 1024。实际为 22 requests、59,515 tokens，低于 40/140,000 子集硬预算。原始报告与追加审计均保留。

| Case | CIEDG | Native Agent | 失败类别与事实 |
|---|---|---|---|
| S02 | 失败 | 失败 | CIEDG 将模型产生的无关 unknown slots/缺失 analysis_type 引证转为澄清；Native 未识别用户已授权筛选并要求额外通道 |
| S06 | 失败 | 失败 | CIEDG 同样过度澄清；Native 筛选后静默丢失零 usable 的 control 条件，属于科学状态错误 |
| R05 | **通过** | 失败 | CIEDG 正确要求参考通道；Native 也请求补参，但回答包含工具未给出的中间 onset 等数值，answer evidence 失败 |
| R11 | 失败 | 失败 | CIEDG 工具链和最小恢复正确，但 evidence-answer schema 校验失败；Native 遇到 artifact expiry 后不恢复，却在回答中声称重参考和结果完成 |

初始真实报告曾把 CIEDG R11 误记 accepted，并把 Native R05 在状态查询后的补参误分类 completed。追加审计把 pipeline `answer_check` 纳入 acceptance、允许非实质状态查询后澄清、排除 ID/hash 数字段，同时要求披露未恢复工具失败。修正后 CIEDG 1/4、Native 0/4。未重跑模型，也未调整提示词。

## 6. 错误分层

- 意图解析错误：CIEDG S02/S06 的模型输出携带无关 unknown slots 且缺少必需引证；Native S02 未识别授权。
- 规划错误：Native S02 未进入完整筛选/功率链；R11 未规划故障后的恢复。
- 科学状态错误：Native S06 将 control=0 usable 静默从下游条件中移除。
- 失效恢复错误：Native R11 在 `ARTIFACT_NOT_FOUND` 后停止。
- 回答证据错误：CIEDG R11 的结构化回答未通过 Evidence Gate；Native R05/R11 出现无证据数值或与失败状态矛盾的完成陈述。
- 协议错误：S09 未实例化其声称的 effective fingerprint 等价条件。

## 7. 可复现文件

- 冻结场景：`config/point1_formal_eval_cases_v1.json`
- 主 holdout：`docs/research/results/point1_formal_holdout_v1.json`
- 不变量审计：`docs/research/results/point1_formal_holdout_invariant_audit_v1.json`
- 真实 DeepSeek 原始结果：`docs/research/results/point1_formal_real_llm_v1.json`
- 真实结果追加审计：`docs/research/results/point1_formal_real_llm_audit_v1.json`
- 运行手册：`docs/research/POINT1_FORMAL_EVAL_RUNBOOK.md`

## 8. 有效性威胁

1. 仅两个 EEG 状态转换族、确定性合成数据和小样本场景，不代表多数据集泛化。
2. Strong Expert 与 Candidate 共享规则，公平但高度任务知情；持平既不能证明 Candidate 优势，也不否定声明式机制的扩展潜力。
3. 真实 LLM 仅 4 个分层场景，且 provider temperature 不受本客户端控制。
4. 质量阈值是经验筛查，不是临床校准；参考通道归零会触发现有 flatline 规则。
5. S09 无效使 selection 家族的“不同 ID/等价 effective 内容”缺少有效正式样本；不能事后补例追分。
