# CIEDG 可扩展性小型实证结果

## 1. 实验身份

- 协议：`point1-extensibility-v1`，2026-10-24 在实现前冻结。
- 原始结果：`docs/research/results/point1_extensibility_v1.json`。
- 原始结果 SHA-256：`d7b41934687c9527c86cc910aa4f41bedfe1ab9a8e300c2b0f910211b0b305f9`。
- 数据：确定性合成 EEG；没有真实受试者数据、外部 LLM 或离线 gold 进入运行时。
- 方法：`CIEDG+extension` 与 `strong_dynamic_expert+extension`。前者是冻结 CIEDG 的隔离扩展变体，不能替代 Issue #16 Candidate；后者允许合理的 consumer 表驱动抽象。

## 2. 科学结果与调用成本

| Case | 场景 | CIEDG | Expert | 两者总调用 | variance 行为 |
|---|---|---:|---:|---:|---|
| X01 | source variance | 通过 | 通过 | 各 3 | 执行一次 |
| X02 | 质量筛选后的 effective variance | 通过 | 通过 | 各 5 | 执行一次，2 个 retained Epoch |
| X03 | 测量质量但禁止筛选 | 通过 | 通过 | 各 4 | source 上执行，保留 3 个 Epoch |
| X04 | 显式重参考后的 variance | 通过 | 通过 | 各 4 | effective rereferenced artifact 上执行 |
| X05 | selection artifact 失效后内容等价重建 | 通过 | 通过 | 各 8（7 成功） | 工具只执行一次，证据以 current-lineage view 复用 |
| X06 | source 内容变化并清空 artifact | 通过 | 通过 | 各 9（8 成功） | fingerprint 改变，variance 执行两次 |
| X07 | variance 一次瞬时失败 | 通过 | 通过 | 各 4（3 成功） | 只重试失败 consumer |

汇总：两种方法均为 **7/7**，各 **37 次总工具调用、34 次成功调用**。所有条件试次数和通道方差均通过独立显式平方离差 oracle（`rtol=1e-6, atol=1e-15`）；禁止工具未执行；发布结果的 artifact identity/fingerprint 与当前 effective state 一致。

这与 Issue #16 的主结果方向一致：在同规则、同反馈和同预算下，两者科学正确性和运行工具成本持平。本轮没有产生新的准确率或执行成本优势。

## 3. 扩展维护代理

### 3.1 共有工作

双方共同使用并因此不计入方法差异：一个 Registry/Executor `epoch_variance` 数值工具、合成 fixture、TaskSpec/ledger 暴露、故障注入、独立 oracle、scorer、7 个协议案例及测试。新增工具没有进入正式默认 Registry，避免把隔离研究能力误报为产品能力。

### 3.2 方法特定结果

指标由源码中的 `EXTENSION_DELTA` 边界确定：CIEDG 统计 contract、Evidence Gate 和 selection/reference adapter；Expert 统计新增 consumer 调度、重试、重建后复用/重算。Expert 文件其余部分是为不修改冻结实现而复制的既有过程工作流，不作为“新增能力”的增量。

| 方法 | 方法特定文件 | 冻结 core 修改 | 增量非空非注释 LOC | 增量条件节点 | 隔离 adapter 总 LOC |
|---|---:|---:|---:|---:|---:|
| CIEDG+extension | 1 | 0 | 42 | 6 | 48 |
| Strong Expert+extension | 1 | 0 | 41 | 11 | 172 |

解释：

- CIEDG 确实复用了通用 graph frontier、effective binding、dependency invalidation、fingerprint cache 和局部恢复；新 consumer 没有专用恢复分支。
- 但冻结 CIEDG 的基础 Evidence Gate 硬编码已知 consumers，transfer planner 构造器也不允许传入扩展 contracts，因此 selection/reference 两个 adapter 仍需显式代码。最终增量 LOC **没有低于**合理抽象后的 Expert（42 对 41）。
- Expert 的增量条件节点较多（11 对 6），说明过程式恢复控制流更分支化；但单一小案例的 AST 节点数只是维护复杂度代理，不能换算为人工成本或论文优势。
- `objective_literal_mentions` 不作为主指标：CIEDG contract/adapter 中出现 4 次，Expert 表驱动实现只出现 1 次；字面量次数受代码风格影响太大。

## 4. 组合性观察

新 consumer 在 source、quality-only、quality selection、rereference 以及与既有 bandpower 组合时均能运行。CIEDG 的 consumer 依赖可以随 effective binding 自动迁移；Expert 通过 consumer 表也能避免为每个消费者组合建立完整笛卡尔流程。

未验证且仍不支持：selection+rereference 组合、第三种状态转换、跨 event_workflow 的任务类型、自然语言 IntentSpec 扩展、真实 EEG 泛化。特别是 IntentSpec、`compile_intent` 和静态 Planner 仍有目标枚举；本轮用双方共享的 parsed-task adapter 隔离了这一共有成本。

## 5. 失败与局限

- 没有科学失败案例：14 个 method×case 运行均通过；这只是闭合合成协议结果，不是广泛泛化证据。
- 最初结果统计只计算成功调用，会漏掉注入失败；在报告前修正为总调用与成功调用并存，原始 JSON 已按修正口径重新生成。
- adapter 总 LOC（48 对 172）不能直接比较，因为 Expert 为保护冻结源文件复制了既有工作流；公平结论采用增量区域（42 对 41），不利用隔离方式人为放大差异。
- 方差是单一只读 consumer。它能检验 existing state/evidence/recovery 复用，但不能代表新增转换或新增 EEG 范式。

## 6. 验证

- `python -m unittest tests.test_point1_extensibility -v`：4/4 通过。
- `python -m unittest discover -s tests -v`：225 tests，213 passed、12 resource-gated skipped、0 failed。
- `python -m compileall -q src tests`：通过。
- `python -m pip check`：`No broken requirements found`。

