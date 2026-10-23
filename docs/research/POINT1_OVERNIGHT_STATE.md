# 工作点一集成方法：通宵状态

更新时间：2026-10-23（Asia/Shanghai）

## 当前阶段

Issue #10 后续迭代：本地/远端历史已安全收敛；意图—任务类型一致性、派生 EEG 状态链和证据寻址回答已实现并完成有界真实验证。工作分支为 `research/point1-integrated-method-v0`，基线起点 `d0ae05c`。

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
- 首次真实复杂链暴露模型把 `ToolResult.data` 内部路径误写为以 `data` 开头；该失败已原样保留。补充相对路径协议后，重测完成五工具链并引用 `epoch_quality`、`select_quality_epochs` 和 `event_bandpower` 的实际值。
- 对比请求“不要筛选或剔除试次”在 Planner 前以 `clarification_required` 停止，工具调用为 0；命令式“并筛选异常试次”则属于真实授权并正常执行，不能将其误记为缺少授权。

## 上次成功验证

当前集成方法与 Planner 定向测试 30/30 通过；三条 Fake 轨迹已按证据寻址协议重新生成。真实 follow-up 共 4 个合成请求、7 次 Provider 请求、14,313 tokens：PSD 类型对抗、两条授权复杂链完成，一条禁止筛选请求零工具澄清；其中复杂链首次回答路径失败后经协议修复成功。完整回归仍待本轮全部改动后重跑。

## 下一步

1. 在全新冻结任务集上比较 Native、同规则 Strong Expert、Generic Contract 与 CCEP；当前不得围绕这四个 follow-up 请求继续调参。
2. 独立评估概念词表的同义词、否定作用域、多意图和单位换算，不把安全澄清等同于任务完成。
3. 保持本分支为 Draft PR，不自动合并 main；等待论文实验设计审查。

## 阻塞与未验证问题

- 方法新颖性尚未成立；当前目标是可运行的 method candidate。
- `deepseek-flash` 的中文文本在当前服务响应中存在历史已知的乱码现象；结构化参数与执行可验证，但中文自然语言可读性不能据此宣称通过。
- 真实原始/处理后多分支不是当前生产 Context 的通用能力，不能虚构。
- 当前数值 span normalizer 只覆盖阿拉伯数字和 Unicode 负号，不支持中文数字、单位换算和共指消解。
- 科学概念锚点是声明式运行时词表，能阻止已知类型漂移，但其同义词召回率、否定作用域和多意图组合尚未正式评估。
- 禁止筛选的真实请求当前安全澄清而非自动降级为“不筛选的质量+功率”计划，说明组合意图的最小充分任务类型仍需扩展；本轮不为单个案例添加特例。
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

## Git 传输恢复入口

- 2026-10-23 已执行 `git fetch origin research/point1-integrated-method-v0` 和非强制 `git merge --no-edit origin/research/point1-integrated-method-v0`；`ort` 合并无文件差异。
- Merge commit 为 `1bd8e7c`，已通过普通 push 更新 Draft PR #11；未 force push、未合并 main。本节历史恢复事项已关闭。
