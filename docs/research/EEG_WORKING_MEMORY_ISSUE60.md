# Issue60：模型操作契约与规划期证据

本报告承接 Issue59 最终 v5，原分支与 Draft PR37。当前处于工程冻结和真实开发准备；真实授权已收到，不需要再次授权。历史结论与首次失败仍见 [Issue59报告](EEG_WORKING_MEMORY_ISSUE59.md)，不能以本阶段受控结果追改旧评分。

## 问题、设计与职责

基点34a85a6、科学行为aa37ad4。原T05第二轮已经读到真实标量，随后仍把既有身份作为新建、携带只读版本或不完整解释，没交付新窗口及比较。T07同版完整通过。故本阶段不是继续放松范围核验，而是使可见操作契约与真实执行要求一致。

比较三种方案：①只增加错误提示，不能解决读写结构近似和比较结构在运行时才拒绝；②增加独立update/compare控制器，会重复既有增量修订与状态事务；③复用现有接口并区分读视图、类型结构和规划证据，选择③。模型仍选择操作、目标、变化、字段和方向，程序提供真实身份/版本/契约并核验。

已实现：

- 读视图使用`declared_outputs`与`revision_targets`，不再展示貌似可直接回写的整TaskSpec。既有精确ID的`plan_tasks`在结构校验前返回操作类别错误与`revise_plan`入口；不自动转换，不按名称相似或语言关键词猜意图，新独立任务仍开放。
- 从同一个TaskSpec schema派生比较分支：恰好两个InputRef、各一个标量字段；比较不要求重新声明EEG窗口解释。数值能力保留原解释约束；比较实际字段/类型/版本继续检验。
- 原`read_dependency`新增`contract`层，返回选定实际结果的字段路径、类型和单位及有效性，不返回数值、不提升证据已读层级、不推断未来字段。旧版本仍须明确选取，精确值沿原result读取。
- 迁移受控检查发现：同一数值对象改通道而保留窗口时，原核验不允许当前通道来源与旧窗口来源组合。最小修正复用显式选择的有效实际旧结果，并要求未变窗口与其原始执行来源完全匹配；无实际证据的同数值旧文字不够。当前冲突窗口、错记录/时基、过期结果仍拒绝。此为通用字段继承，未引入任务/通道/窗口特判；不是意图理解证明。

复杂度取舍：新增一个只读证据层和schema分支，未新增状态容器或第二修订系统；保持原六组自动接受/证据供给差异。源引用检查新增的是实际旧结果中不变字段的合法路径，不替模型选择旧结果。读视图名称变化对旧脚本需机械映射，生产写契约不改名。

## 离线证据边界

原T05 v5提案原样重放前后均为首轮完成、次轮no_progress；错误提案未被手改成成功，现有ID错误得到更准确的操作类别反馈。重放不是新模型行为。

原24条受控链读取字段从`required_outputs`机械映射为`declared_outputs`，科学任务、工具参数和判据不变；111/111数值核验，12条增量链完成。首次全量的14个失败（13个旧读视图夹具、1个结构错误路径断言）及首次未映射报告保留，不能删除后仅展示绿色结果。

迁移初次手写夹具整段多分句source_span被拒，修正夹具后M01仍暴露上述来源字段耦合，M02通过。源机制修正后，两条实际Agent/Store/Executor＋Fake链均通过独立数值核验；这是构造集成验证，不是历史模型自主成功。安全反例涵盖未执行旧文字、错窗/当前冲突窗、跨记录、时基错误、过期绑定；原工件、同值不同身份、循环、控制前提和接受生命周期回归继续保留。

## 冻结协议与预算

原T05/T07不变；两条开发迁移自然请求、独立判据和数据引用在首次API前登记于[协议](../../config/point1_working_memory_issue60.json)。M01改RMS通道并保留窗口/历史比较；M02旧RMS不变后新增另记录平均绝对幅度。迁移仍属开发，非独立确认集。平均绝对幅度oracle使用直接numpy mean(abs(signal))，不改生产算法。

授权实际回执：[Issue55 6597995022](https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6597995022)，ID `issue60-20261103-192c-3500kt-1p70`。固定305次/3,879,334tokens/US$1.2496989；阶段192次/3.5M/US$1.70，开发绝对497次/7,379,334，累计费用US$2.9496989，全账本US$3仍生效。确认池禁用。原唯一账本前缀14ee78772bf3bc3568b70354d05c721e2ef8b8701d38dba548b3d3667e2b122f，不重置历史；第五次幂等授权链TEST覆盖固定起点、硬限、final lease与确认拒绝。

使用原DeepSeek/deepseek-flash/thinking关闭/90秒/输出2200/重试0；每用户轮12completion、36工具、900秒、256000上下文字节。最终四会话预留96调用、初估1.8M tokens与US$0.75，真实请求继续逐次预约结算，不以最大输出单价预扣全部剩余tokens。只发送必要合成信息。

## 公开参数化入口

复用既有运行器，不发布个人启动器或私有配置。将受控环境提供的`EEG_HARNESS_LLM_API_KEY`、原服务`EEG_HARNESS_LLM_BASE_URL`、`EEG_HARNESS_LLM_MODEL=deepseek-flash`注入环境；设置TIMEOUT=90、MAX_TOKENS=2200、MAX_RETRIES=0、THINKING=disabled（均使用同一`EEG_HARNESS_LLM_`前缀）。凭据、原唯一账本和已核attestation均由本地配置定位，下面占位符不得替换成新建账本。准备/授权承接不调用模型。

```powershell
$env:PYTHONPATH='src;tests'
python -m unittest test_issue60_interfaces test_issue60_authorization -v
python -m eeg_harness.research.working_memory_issue55_live --apply-authorization <已核授权JSON> --ledger <原唯一账本> --attestation <冻结attestation>
python -m eeg_harness.research.working_memory_issue55_live --real --phase development --case T05 --ledger <原唯一账本> --attestation <冻结attestation> --output <全新输出目录>
```

`--case`可选原开发题及登记M01/M02；输出包含实际请求/响应、逐轮状态与评分。必须先冻结src/config清单、schema、模型配置、任务、费用起点和测试证据；不得重复同题同科学行为、使用确认池或已有输出目录。授权校验依赖真实回执与原前缀，测试授权只能用于临时TEST账本，不能用于付费。

## 真实结果与限制

待本阶段实际执行后据原始轨迹填写，不能把离线通过写成自主通过。最终同版四条均需完整会话或明确硬阻塞证据；最终覆盖开始后不再修改科学实现。执行者自审与未参与实施/实时执行的只读复核分别记录，后者不等同主审/盲评。稳定泛化、真实数据和相对强基线收益均尚未证明。
