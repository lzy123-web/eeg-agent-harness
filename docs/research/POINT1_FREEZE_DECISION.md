# CIEDG 方法冻结决策

日期：2026-10-23  
结论：**Freeze / 进入正式公平实验；论文优势仍未证实。**

## 1. 最后一轮泛化门槛是否通过

通过有限工程与机制门槛：同一 CIEDG runtime 已支持两类科学上不同的状态变化：

- 质量证据驱动、用户授权的 Epoch trial selection：改变试次数与数据内容；
- 用户授权、显式通道的 Epoch rereference：保持试次数/采样率/事件，改变 reference 与信号内容。

第二类转换没有复制 EEG Core 或 Executor，也没有为每个 consumer 写固定流程。新增的是一个工具、一个 transition contract 和参数 resolver；既有 residual goal、role binding、fingerprint invalidation、semantic consumer reuse 与 bounded repair 机制继续工作。因此“机制能迁移到第二类真实状态变化”的最低门槛成立。

## 2. 相对上一版本的真实算法变化

1. 科学状态由单一 original/selected Epoch 扩展为显式 `reference` transition；
2. consumer/evidence 绑定 current effective artifact，而非固定“筛选后”语义；
3. artifact identity 与 content equivalence 分离：历史执行不可变，当前回答通过 release view 引用新谱系；
4. reference-dependent role evidence 重算，无副作用 consumer 仅在内容等价时复用；
5. Evidence Gate 从当前 goal tokens 发布证据，避免引用已失效 artifact。

标量 evidence manifest、CLI 模式、schema 字段、MNE oracle 和评测 JSON 都是必要工程或验证设施，不是算法贡献。

## 3. 新支持与明确不支持

现在可运行：显式单/多现有通道 Epoch 重参考后，继续做质量测量、Epoch summary 和绝对频带功率；artifact 丢失时做局部恢复。当前验证只覆盖 `edf_native` 合成 EEG。

仍不支持：自动选择“最佳”参考、默认全通道 average reference、TUEV 双极 Profile 重参考、重参考与 trial selection 的组合顺序、同一请求同时保留转换前后两条分析分支、CSD、重采样、真实数据科学泛化。遇到这些情况应澄清或拒绝，不能自动补造转换。

## 4. 失败案例与迭代价值

本轮两个真实缺陷均改变了实现：

- 内容等价重建后 summary 仍指向旧 ID：引入不可变历史与 current-lineage release view；
- DeepSeek 引用对象路径：Evidence Gate 正确拒绝，后增加通用合法标量地址清单，一次有界复测通过。

另一个评价器 tuple/list 误报被修正为 canonical JSON 比较。首次失败结果均保留。没有通过降低科学门槛或改变 oracle 取得成功。

## 5. 公平对照与当前证据

强动态 Expert 获得相同工具、规则、状态、故障反馈、semantic reuse、16 次调用和 2 次恢复预算。正常与 artifact 丢失两例中，双方科学结果和调用序列持平。故当前证据不支持 CIEDG 在成功率、工具成本或科学正确性上优于已知工作流 Expert。

CIEDG 可能形成论文贡献的对象是：以 EEG 科学属性/角色为索引的目标—证据依赖图，在未知组合和状态变化下统一管理失效、谱系与局部恢复。是否有额外价值，只能由冻结多 family 协议相对 Native Agent 和强 Expert 的结果回答。

## 6. 为什么现在冻结

继续添加第三种转换会扩大系统，却不提高当前核心假设的可证伪性。现有两类转换已足以做跨 family、故障、授权、内容/身份反例及消融。正式协议已冻结为 24 例，下一步应执行而不是继续在开发样例上优化。

若正式实验显示 CIEDG 与强 Expert 持平，合理结论是：对已知流程没有性能优势，但可能提供统一可审计表示；若相对 Native 也无优势或错误更多，则工作点一应降为工程框架/No-Go，不再堆模块挽救结论。

## 7. 进入正式实验的条件

核心代码、独立 oracle、强 Expert、故障注入、指标和协议均已具备，可进入有界正式比较。执行前仍需：固定具体 DeepSeek model/version/temperature，保存 API 服务日期与预算；确认 24 case evaluator 均可运行；锁定提交和协议 hash。不得根据 holdout 调 Prompt、阈值或 case。
