# 工作点一集成方法初版验收

日期：2026-10-23

## 1. 研究问题与当前判断

研究问题是：当自然语言 EEG 请求需要经过多步工具、派生 Epoch 与有限恢复时，如何让用户明确给出的通道、时间、事件条件、数据来源与禁止操作不被 Planner 或恢复过程静默弱化，并保证最终回答只引用实际产生且 lineage 一致的证据？

本轮实现的候选机制称为 **Constraint-Carrying EEG Plan（CCEP）**。其核心不是再添加一套 EEG 算法或执行器，而是把意图中的科学义务编译为一个持续存在的 obligation ledger，在计划前、重规划后和回答前分别验证。

当前判断是 **可运行的方法候选，创新性未证明**。已有实现证明了跨层契约能够真实接入 Agent 并阻止若干假阳性，但尚未与原生 ReAct、同规则强 Expert 和通用契约 Planner 在新的冻结任务集上完成正式统计比较。

## 2. 架构与职责

```text
自然语言
  ↓ EvidenceBoundIntentInterpreter（结构化 Tool Calling + 原文 span）
IntentSpec
  ↓ compile_intent
TaskSpec + ObligationLedger
  ↓ StateAwareConstrainedPlanner
Plan ── validate_plan_against_ledger
  ↓ ConstrainedPlanRunner（每次恢复重新验证 ledger）
原 ExecutionContext → Executor → Registry → EEG Tools
  ↓
ToolResult + ExecutionTrace + artifact lineage
  ↓ close_ledger / Evidence Gate
证据受限最终回答
```

实现入口：

- `research/integrated_method/intent.py`：IntentSpec、canonical EEG slot、原文证据和来源可观测性。
- `research/integrated_method/contracts.py`：obligation ledger、计划校验和执行证据闭合。
- `research/integrated_method/agent.py`：opt-in 端到端运行时。
- `planning.py`：复用原 Planner/Runner，仅增加可选 plan validator hook 和质量证据先行的复合目标。
- `agent_cli.py --agent-mode point1`：不替换默认 `native` 基线。

EEG-specific 内容体现在：连续窗与事件窗使用不同科学 slot；事件分析必须由已存在标签建立 Epoch；事件窗受当前工具最短时长约束；质量筛选必须先测量同一 Epoch artifact；raw/processed 来源不能凭空互换；最终事件结果必须与实际 Epoch artifact lineage 对齐。

## 3. 完整执行轨迹

### 3.1 单步：连续窗绝对频带功率

输入请求：对合成通道 `SYNTH-C1` 的 1–3 秒计算绝对频带功率。

真实 DeepSeek 第二轮结果：

- Intent：`psd`，`channels=[SYNTH-C1]`，`start=1`，`end=3`；
- Planner：单步 `psd`；
- Executor：1 次成功工具调用；
- Evidence Gate：所需工具与参数闭合；
- 终止：`completed`；
- Provider：2 请求，2,192 tokens。

完整脱敏 JSON：`results/point1_integrated_deepseek_psd.json`。Fake 回归轨迹：`results/point1_integrated_psd_fake.json`。

### 3.2 多步：事件条件绝对频带功率

输入请求：对 `stimulus` 事件的 `[-0.2, 0.8)` 秒窗口计算绝对频带功率。

真实 DeepSeek 第二轮结果：

1. `list_events` 验证记录中存在 `stimulus`；
2. `create_epochs` 以同一 label/window 产生请求级 artifact；
3. `event_bandpower` 通过 artifact id 消费该 Epoch；
4. Evidence Gate 验证成功工具集合、参数不变和 producer/consumer lineage。

终止为 `completed`；共 3 次工具调用、2 次 Provider 请求、3,300 tokens。完整脱敏 JSON：`results/point1_integrated_deepseek_event.json`。Fake 回归轨迹：`results/point1_integrated_event_fake.json`。

### 3.3 缺参澄清

请求只说“某个事件条件”，没有给出可执行标签。真实 DeepSeek 将 `labels` 保持未知，系统在 Planner 前以 `clarification_required` 停止，工具调用为 0；共 1 次 Provider 请求、1,362 tokens。见 `results/point1_integrated_deepseek_clarify.json`。

## 4. 真实模型失败与修复

首轮三个请求全部安全停在澄清，没有误执行。根因不是 Executor，而是意图 Tool Schema 将 `parameters` 定义成任意 object：模型产生 `channel`、`event_label`、`window_start_seconds` 等别名，并把普通 PSD 误判为事件任务。

修复没有添加 case-specific gold 或接受别名，而是把模型接口收紧为共享 canonical slot：`channels/start/end/labels/tmin/tmax/selection_authorized`，并明确普通连续窗与事件窗的判别边界。第二轮两条完整任务通过，真正缺参请求仍澄清。

两轮合计 8 次 Provider 请求、10,477 tokens，低于 36 请求/90k tokens 上限。所有外部调用仅使用确定性合成记录的元数据和派生工具结果；没有真实 EEG、受试者信息、本地路径、原始数组或凭据进入请求/结果。

当前服务的 `deepseek-flash` 中文响应仍出现历史已知乱码。结构化参数、工具链和终止状态可验证，但不能把最终中文可读性记为通过。

## 5. 科学约束、恢复与安全测试

自动化测试覆盖：

- 缺事件标签时不执行工具；
- 模型从记录状态猜出、但用户原文没有的 label 会被阻止；
- 数值值必须真实出现在所引用的原文 span；
- 不存在事件、短于工具前提的窗口与 Profile 不兼容在执行前拒绝；
- 没有显式 raw 分支时拒绝 raw-source 证据请求；
- 质量筛选必须明确授权，且 `epoch_quality` 先于筛选；
- 选择禁令不能因 LLM 命名变化绕过；
- 临时工具失败和 artifact 失效只允许一次恢复，恢复前重新验证同一 ledger；
- 计划和执行不能静默丢失 obligation 参数；
- 最终 LLM 回答失败时保留工具证据，但使用 `completed_without_llm_answer`，不冒充闭环成功；
- 结果与 trace 均可 JSON 序列化，不包含 EEG 波形。

有本地资源时完整回归为 161 项中 160 通过、1 项真实联网 opt-in 测试按设计跳过；无私有资源时 149 通过、12 项资源/联网测试按设计跳过；`compileall` 和 `pip check` 通过。既有 EDF、seizure 权重与 R3 文件只在本地测试环境引用，没有进入 Git。

## 6. 审查结论

### 可接受

- Baseline v1 默认路径未被替换；研究方法通过显式 CLI 开关启用。
- 没有第二套 Executor、EEG Core 或 artifact store。
- Planner 与有限恢复均受同一 ledger 约束。
- 实际 ToolResult、ExecutionTrace 与 artifact lineage 是回答证据，而非 Planner 自述。
- 失败、澄清、无证据和回答失败具有不同终止语义。

### 尚未成立

- 没有证据表明 CCEP 优于同规则强 Expert 或通用语义 Planner。
- 三个真实模型案例不构成成功率、泛化性或统计结论。
- raw/processed 仅做可观测性拒绝，尚未形成通用双分支数据图。
- 事件频带功率不是 ERP/ERD-ERS；没有完成临床诊断、ASD、Sleep、MDD 或真实事件数据验证。
- 经验质量阈值没有跨设备、跨 Profile 校准。
- 中文数值、单位换算、代词指代和复杂多意图仍未解决。

因此，本轮满足“真实集成初版”的工程验收，但论文方法的 Go/No-Go 必须由后续冻结、公平、可重复实验决定。
