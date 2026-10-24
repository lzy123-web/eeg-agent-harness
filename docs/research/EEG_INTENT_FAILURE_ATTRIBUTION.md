# EEG 科学意图失败归因：模型理解与 Harness 校验

日期：2026-10-24（Asia/Shanghai）  
输入：Issue #16 不可变原始报告 `point1_formal_real_llm_v1.json` 及追加审计  
历史请求模型名：`deepseek-chat`；历史实际后端版本：**unknown**

## 1. 归因方法

本报告不把旧 `validate_intent` 当作真值。人工先按注册工具、参数契约和用户原文标注 analysis type、目标、参数、授权、禁止操作、真正缺参和预期 disposition，再逐层检查：

1. DeepSeek 原始 `submit_eeg_intent` 字段；
2. JSON/schema 解析；
3. exact-span 与短语 anchor；
4. analysis/objective 一致性；
5. required slots；
6. Intent→TaskSpec→CIEDG；
7. Answer Evidence Gate。

## 2. 四个旧例逐字段归因

| Case | 模型原始科学理解 | 旧 Harness 实际失败谓词 | 主归因 | 正确处理 |
|---|---|---|---|---|
| S02 | `event_workflow`、质量/筛选/计数/功率、target、0–1 s、筛选授权均正确；但质量 evidence quote 只写 `inspect 0–1 s epochs` | 固定 anchor 将局部引用不足升级成整个 analysis type 不匹配 | **共享链路**：核心意图正确；模型 evidence binding 不充分；Harness 错误地用该局部缺陷否定完整任务 | 由已验证的筛选目标派生质量先决条件后 execute |
| S06 | 任务类型、四目标、target/control、0–1 s、筛选授权均正确；部分 evidence quote 使用 `flagged trials` | 合法表达变体没有通过固定 anchor，先于 slot 校验触发 `INTENT_TYPE_MISMATCH` | 以 Harness 误拒为主，但不把 evidence-span 选择质量算成完美模型输出 | execute，随后因 control 零 usable 科学停止 |
| R05 | 重参考、质量、功率、target、0–1 s、授权均正确；模型也明确把 `reference_channels` 放入 unknown | 英文屈折形式 `re-referencing` 没有命中旧 rereference anchor，先触发 `INTENT_TYPE_MISMATCH` | `overstrict_validator`；同时确有 `missing_genuinely_required_parameter` | clarify `reference_channels`，不能以错误的 analysis-type 理由澄清 |
| R11 | 意图与全部必需参数正确；Validator、规划、执行与最小恢复完成 | 最终回答模型引用不存在的 `condition_counts_before_quality` 路径；Evidence Gate 正确拒绝 | **回答模型证据寻址错误**；Gate 本身按设计工作 | 意图/执行成功；回答不发布，单独统计 |

S02/S06 的 `unknown_slots` 含 channels、band definitions、quality threshold 等多余项，但旧代码只在 required-slot 循环内检查 unknown，因此它们**不是这两例的直接触发谓词**。不过，这暴露了 schema 把“模型认为未知”与“工具真正要求用户提供”混为一个未类型化列表的问题。不能把这一点错误写成 S02/S06 的直接根因。

四例均没有 JSON schema parse failure。S02/S06 不是核心任务类型错误，但也不能笼统写成“模型输出完全正确”：S02 至少有 evidence binding 不充分。R05 是“模型正确识别真实缺参，但 Harness 在更早的错误谓词上停止”。R11 不进入意图准确率分母的失败项，且其 Gate 拒绝不是误拒。

## 3. 模型版本核实

- 历史结果只保存了请求别名 `deepseek-chat`；旧客户端没有记录响应体顶层 `model`。
- 仅凭别名不能反推出服务在 2026-10-23 实际路由的模型版本，因此历史后端严格记为 **unknown**，不改写为 Flash。
- 2026-10-24 使用相同官方主机的公开 `/models` 接口实际返回 `deepseek-flash` 与 `deepseek-v4-pro`；没有返回 `deepseek-chat`。
- DeepSeek 官方 Models & Pricing 当前把 `deepseek-flash` 标为 `DeepSeek-V4.1-Flash-1017`，把 `deepseek-v4-pro` 标为 `DeepSeek-V4-Pro-0813`；官方 Change Log 说明 2026-10-17 更新及调用名。
- 新客户端仅增加响应 `model` metadata 留存，不打印 endpoint path、认证头或 key。若响应仍只返回别名，则只报告该别名，不自行映射内部版本。

官方依据：

- https://api-docs.deepseek.com/updates/
- https://api-docs.deepseek.com/quick_start/pricing/
- https://api-docs.deepseek.com/api/create-chat-completion/

## 4. 归因结论

当前证据支持分层而非单标签归因：S02/S06 的核心任务理解正确，但 S02 的 evidence binding 也有模型责任；旧 validator 把局部引用问题升级为 analysis-type 失败，是 Harness 的设计缺陷。R05 同时包含 Harness 错误早停和真实缺参。R11 是回答模型生成了无效 evidence path，Gate 正确拦截。换模型可能改变 evidence span 质量，但无法修复“固定 anchor 等于科学语义真值”的架构问题，也无法自动保证授权、缺参和回答 provenance。
