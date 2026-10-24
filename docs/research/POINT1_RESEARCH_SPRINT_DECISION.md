# Issue #30 预实现研究门槛：科学状态投影是否值得作为新方法

日期：2026-10-25。冻结基点：PR #27 远端 `fb5b85b` 的代码树；本地等树历史经非强制 merge 后为 `2a54367`，独立分支 `research/point1-sprint`。**本节的 NO-GO 判断在本轮任何新核心实现前作出；后续不得改写为事后成功假设。**本文件是论证与静态反例，不是新的 EEG 实验。

## 一页决策面板

| 层次 | 事实 | 不能推出 |
|---|---|---|
| 已实现 | `v3_agent.py::_attempt` 产生目标实例；`v3.py::compile_instances` 做原子预检；`SharedEvidenceGraphCore` 管理 DAG 前沿、来源绑定、失效、缓存和有界恢复；原 `ExecutionContext → Executor → ToolRegistry` 运行工具；闭合后给逐目标 bundle。 | 自然语言意图完整、科学合同无遗漏、任意 EEG 任务已通用化。 |
| 已测试 | 旧 v1.1 正式集 CIEDG/同规则 Strong Expert 均 24/24、109/109 calls；PR #23 扩展均 7/7、37/37 calls，方法特定 42/41 LOC；新版 C1–C8 为开发验收。 | 新版对强 Expert 或成熟 typed workflow 有优势。 |
| 理论候选 | 将 `input_policy`、`ToolSpec.config_keys`、事件/模型绑定统一成读写科学状态投影。 | 合同统一即新规划算法，或专家编写合同成本为零。 |
| 已知反例 | S09 冻结恢复条件未正确实例化，属 protocol-invalid；C2 真 DeepSeek 遗漏事件标签后安全澄清；质量自适应 Pilot 与同规则 Expert 16/16、32/32 持平。 | 将这些失败重标为新版 holdout，或称失败已被投影合同解决。 |
| 当前不支持 | v3 尚未迁移筛选、重参考；无任意 Profile 模型适用性、通用 ERP/ERD-ERS、临床报告；现有模型只允许已验证输入。 | 多个注册工具等于多数据集验证。 |

**生命周期**：用户文本 → LLM 提交目标/参数（可错漏）→ Registry/Profile/资源预检 → 目标实例与隐含 Epoch 前提合图 → 共同 graph 按当前输入与依赖 token 选前沿 → 真实 Executor 工具 → 绑定来源/结果 → 状态变化时撤销后继并有限重跑 → 全部目标有效才发布 bundle。当前图对 `record`、`record_model`、`source_epochs`、`effective_epochs` 使用不同绑定；`v3.py::_record_digest` 对整个数组反复 `tobytes()`+SHA-256，模型 digest 还读完整权重。`ToolSpec.config_keys` 当前只覆盖已声明的分析配置，不能保证无漏项。

## 门槛问题与预写科学例子

真值是**依赖关系和发布条件**，不是某个预期胜率。以下案例尚未执行，不能转成新实验结果。

| 案例（任务族） | 科学状态改变时的独立真值 | 合理 typed workflow / 同规则 Expert 是否可表达 |
|---|---|---|
| P1：同记录连续窗 alpha PSD + 事件条件 alpha 功率（连续＋事件） | 频带定义变更使两份 alpha 数值证据失效；`record_info` 与原始事件观察不因频带变更重算。须记录实际参考与来源。 | 可。两消费者都显式依赖频带参数，按参数签名失效；Expert 可表驱动重算。 |
| P2：连续 PSD + 某标签事件 Epoch 均值（连续＋事件） | 事件标签或 Epoch 窗改变，只影响 `create_epochs` 及事件派生结果，不应使不读事件的连续 PSD 失效。 | 可。分开的数据依赖边与输入签名足够；不需要新 EEG 专用规划算法。 |
| P3：源 Epoch 质量测量、授权筛选、有效 Epoch 频带功率（事件） | 筛选产生新 artifact 身份和有效试次集合；仅 effective 消费者重算，source 质量证据在内容/合同未变时仍有效；未授权则不得筛选。 | 可。typed artifact、权限前提、PROV 派生关系和版本化依赖可表达；既有强 Expert 已展示同等结果。 |
| P4：连续特征 + 严格 22 导癫痫推理（连续＋模型） | 仅权重文件变化使模型证据失效，连续特征不失效；Profile/采样率不满足则模型拒绝，不能凭 22 通道数偷换适用性。 | 可。模型资源作为带 digest 的输入节点、Profile 作为前提即可；需同样专家合同。 |
| P5：重新参考后的连续 PSD + 原参考事件功率（连续＋事件） | 两个对象的参考/阶段必须分别标识；若请求同阶段比较而仅一方变换，必须澄清或停止，不得默认为同源。 | 可。参考和 processing stage 可作为数据类型/元数据约束；正确合同仍由专家制定。当前 v3 还未实现该跨阶段任务。 |

## 最近邻机制与可区分性

1. **当前 patch-like 合同**：`GoalContract.input_policy`、依赖和 `ToolSpec.config_keys` 分散；新增跨族状态读写关系易漏标。收束为一个声明的投影可以减少同步点，属于值得做的**工程可靠性改进**。
2. **统一投影**：对节点 `n` 声明 `R_n`（记录内容/参考/通道/采样率、事件 scope、source/effective artifact、配置、资源），`W_n`（新 artifact/状态），证据签名 `H(n, arguments, projection(R_n), upstream)`；状态改变撤销签名失配者及其后继。此规则与 typed DAG 上的输入/参数版本签名及增量构建**同构**。漏声明一个频带/参考输入时两者都可能错误复用；不能称自动 sound。
3. **认真对待的最近邻**：WINGS 已对组件及输入/中间/输出数据表达语义约束并传播元数据；Pegasus 已做 DAG 数据重用、裁剪、恢复与来源；CogEEGAgent 已将 EEG 语义路由、typed scientific contracts、确定性权限和 evidence-bound release 分离。获得相同 EEG 合同的 Strong Expert 可在这五例作同等合法决策。把 `R_n/W_n` 写进一个类，不改变上述信息量、科学真值或最坏重算界。

这并非断言原 WINGS/Pegasus 对本项目五个 EEG 案例有已发表实测结果；这里是对**同等合同下机制可表达性**的分析。EEGAgent 的多工具调度说明多任务目标并非本项目首先提出；本地源码的全局状态等问题只说明本系统工程改进，不证明相对论文的算法创新。来源：[EEGAgent 原论文](https://ojs.aaai.org/index.php/AAAI/article/view/38867/42829)、[CogEEGAgent 原稿](https://arxiv.org/html/2607.25045)、[WINGS 方法及约束说明](https://wings-workflows.org/about.html)、[WINGS/Pegasus provenance 原论文](https://doi.org/10.1002/cpe.1228)、[Pegasus 原论文](https://deelman.isi.edu/wordpress/wp-content/papercite-data/pdf/deelman-fgcs-2015.pdf)、[Pegasus 官方 data reuse](https://pegasus.isi.edu/documentation/reference-guide/mapping.html)。

**预实现裁决：投影合同作为“独立新方法” NO-GO。** 其可测工程指标是遗漏合同数、接口同步点、修复代价、SHA-256 时间，但没有预先成立的相对同规则 typed workflow/Expert 的独立预测；旧扩展结果恰为 42/41 LOC。故本轮不实现投影版核心，不把 P1–P5 伪装成实测优势。转入 Issue #30 阶段 2B，最多比较两个 EEG-specific 切入点；若仍无可信区分假设，则按停线停止，而不是引入第三个状态转换或改弱对手。
