# CIEDG 与 Strong Dynamic Expert 可扩展性审计

## 1. 审计问题与版本边界

本审计只回答：在新增一个合法 EEG 分析 consumer 时，冻结 CIEDG 与认真维护的 Strong Dynamic Expert 各自需要哪些适配，是否能在科学正确性和恢复能力持平时观察到较少的**方法特定**维护。Issue #16 的 24/24、109 次调用持平结果保持原样；本轮结果不得改称其为 unseen，也不得外推到跨任务类型泛化。

冻结代码位于 `research/point1-integrated-method-v0`。本轮不修改 `integrated_method/v11.py`、`integrated_method/transfer.py`、`formal_evaluation/expert.py` 和 Issue #16 原始 JSON，而是在独立包中实现 `CIEDG+extension` 与 `Expert+extension`。

## 2. 逐层真实扩展点

| 层 | 当前实现事实 | 新 consumer 所需工作 | 分类 |
|---|---|---|---|
| TaskSpec | `planning.py::TaskSpec` 是通用 goal/arguments 容器，不限制枚举；但 `StateAwareConstrainedPlanner.plan` 对 event objectives 有固定分支 | 隔离协议编译器暴露新 objective；冻结静态 planner 不能直接验证它 | 共有暴露 + 当前硬编码 |
| IntentSpec | `integrated_method/intent.py` 的 schema、semantic anchors 和 objective 校验枚举已知目标 | 若接自然语言必须扩 schema/grounding；本轮 parsed-task 实验不修改它 | 共有工作；本轮不计入方法优劣 |
| Ledger | `contracts.py::compile_intent`（64–106）显式列举 summary、bandpower、rereference 对应工具 | 新目标需要 ledger obligation；隔离协议统一生成，双方相同 | 共有科学/协议工作 |
| ToolRegistry | `tools.py::build_default_registry`（253–453）逐工具注册，ToolSpec 可声明 consumes/produces/state effect | 注册真实只读 consumer、schema、handler | unavoidable 共有工作 |
| Executor | `executor.py::Executor.execute`（52–140）通用处理 profile、schema、artifact/JSON 错误 | 无需修改；新工具走真实 Executor | 已可直接复用 |
| Goal contract | `v11.py::GOAL_CONTRACTS`（78–102）逐目标声明 role、input policy、依赖和 priority | 增加一个 consumer contract | CIEDG 特有声明 |
| Dependency graph | `_compile_dependencies`（159–176）按 contract 递归，并把 effective consumer 接到 selection；`transfer.py::_compile_dependencies`（40–52）把它接到 rereference | 新 consumer 可复用角色驱动依赖；selection/rereference 仍由不同类处理 | 通用机制 + 状态族特例 |
| action/binding | `v11.py::_action_arguments`（442–456）对一般 artifact consumer 生成 ID+fingerprint | 无需 consumer 特例 | CIEDG 通用复用 |
| invalidation/recovery | `_reconcile`、`_restore_cached_consumer` 依据 dependency token、artifact fingerprint 与 consumer role 失效/复用 | 新 consumer 理论上无需专用 recovery；必须用 fault 实测 | CIEDG 通用机制 |
| Evidence Gate | 基础 `_required_answer_tools`（548–557）硬编码 summary/bandpower；transfer 版本（66–75）已改成 contract-driven | selection planner 需要隔离 override；否则会错误漏检新结果 | CIEDG 特有 glue，否定“纯注册”主张 |
| release/final answer | `_release_results` 按 `answer_required` 释放；真实 LLM answer 还依赖 scalar manifest/提示层 | parsed-task 实验验证 release，不做 LLM 文案适配 | 机制可复用；自然语言接入另需共有工作 |
| Strong Expert | `formal_evaluation/expert.py`（107–218）显式执行 event/epoch/quality/selection/rereference/summary/bandpower，bandpower 分支内手写 recovery | 可抽取 consumer 描述表；仍需把新 consumer 纳入执行、release、等价复用和内容变化重算 | Expert 特有分支/重放 |

## 3. 三类增量的真实成本

### 3.1 新只读 consumer

共有工作是工具、科学定义、oracle、协议 fixture 和结果评分。CIEDG 需要 contract 与基础 Evidence Gate 适配；图调度、effective binding 和 fingerprint 恢复有望复用。Expert 需要 consumer 执行/release/recovery 适配，但允许使用表驱动抽象，不能人为要求复制整个工作流。

### 3.2 新旧目标组合

同一状态族内，CIEDG 的 consumer 组合主要由 contract graph 合并；Expert 可用 consumer 循环减少组合分支。跨 selection+rereference 的组合在 `transfer.py` 27–31 被明确拒绝，当前不能把 CIEDG 描述为任意组合规划。本轮也不解除该冻结限制。

### 3.3 第三种状态转换（只审计，不实现）

CIEDG 至少需要新 transition contract、授权参数、effective binding、依赖重写、状态输出和冲突恢复语义；现有 selection/rereference 分属不同实现，说明尚未达到纯声明式转换扩展。Expert 需要新的转换分支、前后依赖和重放逻辑。两者成本都可能显著，本轮没有证据比较，禁止据此宣称 CIEDG 优势。

## 4. 成本边界

- **共有且不计入双方差异**：EEG 数值工具、ToolSpec、独立 oracle、合成 fixture、fault、协议、统一 scorer、parsed-task 暴露。
- **CIEDG 特有**：新增 GoalContract、候选 planner 选择/适配、Evidence Gate/answer-required 绑定，以及任何对 graph/reconcile/cache 核心的修改。
- **Expert 特有**：过程式目标分派、consumer 执行/release、故障时的重放和语义复用分支。
- 共享 import、测试断言和报告不作为方法特定 LOC。LOC/分支数仅为描述性代理，不等价于人工工时、认知负担或长期维护成本。

## 5. 审计先验结论

当前最强可检验假设是：**对现有 Epoch source/effective 契约内的只读 consumer，CIEDG 的 graph/invalidation/cache 可能减少专用恢复代码**。更强的“任意 EEG 新任务低成本扩展”在实现前已经不成立，因为 intent、ledger、静态 planner、基础 Evidence Gate 和状态族选择均有硬编码。若隔离实验证明 CIEDG 特有适配并不低于 Expert，研究结论必须收缩或 No-Go。

