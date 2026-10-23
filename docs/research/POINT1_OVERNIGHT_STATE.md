# 工作点一集成方法：通宵状态

更新时间：2026-10-23（Asia/Shanghai）

## 当前阶段

Issue #12 Evidence Phase 已完成实现、独立 oracle、冻结比较与有界真实 DeepSeek 验证。工作分支仍为 `research/point1-integrated-method-v0`，不替换 Baseline v1；CCEP v0 的相对优势主张判定为 No-Go，代码仅作为 opt-in 科学安全骨架 Conditional Keep。

## 已确认状态

- Issue #10 要求形成一条 opt-in 的真实集成链，不修改或替换 Baseline v1 默认 Agent。
- Baseline v1、Issue #8 与 Issue #9 的历史结果保持冻结。
- 当前可用技能中没有 ARIS `research-lit`、`research-refine`、`research-implement-feature` 或 `experiment-audit`，本轮不安装第三方脚本。
- 现有核心可复用对象包括 `EEGAgent`、`NaturalLanguageGoalInterpreter`、`StateAwareConstrainedPlanner`、`ConstrainedPlanRunner`、`ExecutionContext`、`Executor`、`ToolRegistry`。
- 已有意图解释只输出单个 `TaskSpec`，尚未把显式值、未知 slot、禁止假设、科学来源与回答证据作为同一运行时契约贯穿到底。
- 已选择 Constraint-Carrying EEG Plan（CCEP）：不可弱化的 obligation ledger 贯穿 Intent、状态绑定、计划、执行、恢复和证据回答；创新性未证明。
- 设计已保存于 `POINT1_METHOD_BLUEPRINT.md`，不再扩展 Issue #8 的 EEG 专属搜索排序。
- 新增 opt-in `--agent-mode point1`；默认 `native` 和旧 `--planning` 路径未替换。
- 已跑通 Fake 自然语言→IntentSpec→obligation ledger→旧 Planner→原 Executor/PSD→Evidence Gate→最终回答。
- Intent slot 必须附用户原文精确片段；label/channel 值还必须出现在该片段中，阻止模型用当前 record 值冒充用户显式值。
- 事件任务使用旧 Planner 生成真实 `list_events → create_epochs → event_bandpower`，并由 Evidence Gate 检查 artifact lineage。
- 缺事件 label 会在执行前 clarify；不存在标签、短于 1 秒的事件功率窗和处理后数据上的 raw 请求会安全拒绝。
- 明确授权的质量筛选固定为 `create_epochs → epoch_quality → select_quality_epochs`，禁止未测量先筛选。
- 临时工具失败和 artifact 失效各允许一次恢复；每次重规划重新检查相同 obligation，不能改 label/channel/window。
- 首轮真实 DeepSeek 暴露了参数 schema 过松：模型产生 `channel/event_label/window_*` 别名，并把普通 PSD 误判为事件分析；该轮 3/3 均安全澄清、没有误执行。
- 将 tool schema 收紧为七个 canonical slot 并补充分析类型边界后，第二轮真实验证中 PSD 单步与事件多步均完成，缺事件条件请求保持澄清。
- 两轮共 8 次 provider 请求、总计 10,477 tokens，低于 36 请求/90k tokens 预算；只使用确定性合成 EEG，未发送真实受试者数据或原始数组。
- 审查修复了四类假阳性边界：数值必须真实出现在证据 span、未显式暴露 raw 分支时拒绝 raw 请求、计划/执行不得丢失 obligation 参数、最终回答失败不得报告完整成功。
- `trial_selection_or_rejection` 等模型生成的选择禁令现可归一到实际选择工具，避免命名变化绕过禁止操作。
- 提供本地 EDF、既有 seizure 权重与匿名 R3 样例后，全量 161 项中 160 通过、1 项联网 opt-in 测试按设计跳过；`compileall` 和 `pip check` 通过。
- 清除所有私有资源/LLM 环境变量后，无资源回归 149 通过、12 项按设计跳过。
- Draft PR #11 的 GitHub Actions run `39814383931` 中安装、compileall 和无资源 unittest 步骤均完成且结论为 success。
- 已新增覆盖全部 9 个已支持分析类型（含组合任务）的声明式科学概念契约。analysis type 由原文绑定概念集合独立解析并与模型声明交叉检查；合法 PSD 参数但声明 amplitude 的对抗用例在 0 工具调用时澄清。
- 新增 `quality_selected_bandpower` 完整状态链：`list_events → create_epochs → epoch_quality → select_quality_epochs → event_bandpower`。最终分析消费筛选工具新产生的 Epoch artifact，Evidence Gate 按执行顺序检查两级 lineage。
- 最终回答改为证据寻址协议：LLM 只选择成功 ToolResult 的 request id 与标量 JSON path；运行时验证路径、必要工具覆盖并确定性渲染。无效路径或缺少质量/筛选/分析任一必要证据时返回 `completed_without_llm_answer`。
- 首次真实复杂链暴露模型把 `ToolResult.data` 内部路径误写为以 `data` 开头。完整未跟踪 JSON 被同名重测覆盖，仓库没有伪造还原，而是保存 `raw_response_preserved=false` 的观测字段摘要。补充相对路径协议后，重测完成五工具链并引用 `epoch_quality`、`select_quality_epochs` 和 `event_bandpower` 的实际值。
- 对比请求“不要筛选或剔除试次”在 Planner 前以 `clarification_required` 停止，工具调用为 0；命令式“并筛选异常试次”则属于真实授权并正常执行，不能将其误记为缺少授权。
- Issue #12 阶段 A 已新增独立造数与 NumPy/SciPy oracle：3 个合成 Epoch 中固定注入 1 个高幅异常试次，真实 Registry→Executor 将计数从 3 降到 2；派生 artifact 波形逐样本等于 oracle 保留试次，原 artifact 未修改，筛选前后频带结果分别与独立 Welch oracle 一致。
- 全部 3 个试次异常时，选择工具明确失败且不产生派生 artifact；没有把空结果包装成成功。
- 事件意图已从四个固定复合 analysis type 收敛为一个 `event_workflow` 与三个可组合原子目标：`epoch_quality`、`trial_selection`、`event_bandpower`。Planner 在一个共享 Epoch artifact 上按目标和授权生成 DAG。
- “测量质量 + 禁止筛选 + 未筛选 bandpower”现在执行 `list_events → create_epochs → epoch_quality → event_bandpower`；`select_quality_epochs` 不在计划或 trace 中，最终分析消费原始 Epoch artifact。
- 真正授权筛选时仍必须先测质量并让 bandpower 消费派生 artifact；质量工具故障会在选择前停止，ledger 中 label/window/授权义务保持不变。
- 24 项 Evidence Phase 协议已在首次比较前冻结，12/12 development/holdout，语料 SHA-256 为 `e85b5cda…e696`。
- 共享解析任务层的 18 个可评价案例中，Strong route+preflight 与 CCEP 均为 18/18 正确、10/10 科学完成、55 次工具调用、2 次重规划；未观察到 ledger 增量收益。
- 两个固定真实 DeepSeek holdout 中 Native 2/2、CCEP 1/2。CCEP 在授权筛选例误报缺 `analysis_type` 并安全澄清，失败已冻结且未据此调 Prompt。
- 真实比较总计 13 次 Provider 请求、34,263 tokens；只使用确定性合成 EEG。

## 上次成功验证

Issue #12 定向 Evidence Phase 测试 10/10 通过；共享任务冻结比较与真实 DeepSeek 结果均已保存。真实 holdout 为两个请求、两种方法，共 13 次 Provider 请求、34,263 tokens；Native 2/2，CCEP 1/2，失败案例完整保留。

最终本地回归为：`pip check`/`compileall` 通过；提供原 EEGAgent EDF/权重时 180 项中 177 通过、3 项按设计跳过；无私有资源时 168 通过、12 跳过。Draft PR #11 的 GitHub Actions run `39906771336` 对 `2d5d9cf` 完成公开无资源回归，结论 `success`。

## 下一步

1. 不围绕本次 holdout 修 Prompt；先提出一次性 preflight 在动态状态/恢复中会失效的可证伪假设。
2. 只有在新方法修改前冻结新任务、独立标注和分层 scorer 后，才重新比较 Native/Strong/CCEP。
3. 若 ledger 消融仍与完整 CCEP 持平，将 CCEP 明确降级为工程安全机制，不再作为性能型论文贡献。

## 阻塞与未验证问题

- 方法新颖性尚未成立；当前目标是可运行的 method candidate。
- `deepseek-flash` 的中文文本在当前服务响应中存在历史已知的乱码现象；结构化参数与执行可验证，但中文自然语言可读性不能据此宣称通过。
- 真实原始/处理后多分支不是当前生产 Context 的通用能力，不能虚构。
- 当前数值 span normalizer 只覆盖阿拉伯数字和 Unicode 负号，不支持中文数字、单位换算和共指消解。
- 科学概念锚点是声明式运行时词表，能阻止已知类型漂移，但其同义词召回率、否定作用域和多意图组合尚未正式评估。
- 原子目标已能表达“禁止筛选但做质量+功率”，但真实授权筛选 holdout 仍因上游意图 schema 服从失败而误拒。
- 证据寻址回答保证发布值可追溯，但现在是固定模板，尚未验证复杂自然语言归纳的忠实度与可读性。
- 不得把 TaskSpec/validator/Prompt 的简单拼接包装为已证明创新。

## 本轮 Commit

- 阶段 0：`cb91166`。
- 阶段 1：`9f55415`。
- 阶段 2：`fbf20e6`。
- 阶段 3：`c35b541`。
- 阶段 4：`e1c1b03`。
- 阶段 5：本地归档提交 `de6ac8e`、`d021eb2`；因本机到 `github.com:443` 暂时不可达，最终六份文档已通过受认证 GitHub Contents API 同步到 Draft PR #11，远端产生等价内容提交而非上述本地 SHA。
- Follow-up 类型一致性：`ceabfc4`。
- Follow-up 派生 EEG 状态链：`8796c82`。
- Follow-up 证据寻址回答：`339aab5`。
- Follow-up Fake/真实验证与交付：`3866818`。
- Follow-up 失败证据留痕：`1d0d392`。
- Issue #12 阶段 A：`f5283cb`。
- Issue #12 阶段 B：`caed65d`。
- Issue #12 协议冻结：`06ab4e9`。
- Issue #12 共享任务比较：`aa6b20a`。
- Issue #12 真实 DeepSeek holdout：`b705638`。
- Issue #12 研究结论与文档：`2d5d9cf`；GitHub Actions run `39906771336` 成功。

## Git 传输恢复入口

- 2026-10-23 已执行 `git fetch origin research/point1-integrated-method-v0` 和非强制 `git merge --no-edit origin/research/point1-integrated-method-v0`；`ort` 合并无文件差异。
- Merge commit 为 `1bd8e7c`，已通过普通 push 更新 Draft PR #11；未 force push、未合并 main。本节历史恢复事项已关闭。
