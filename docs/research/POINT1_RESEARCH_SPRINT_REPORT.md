# Issue #30 工作点一科研冲刺报告（2026-10-25）

## 半页结论

**研究什么？** 多任务 EEG Agent 接到连续、事件和严格模型请求后，怎样把用户目标与科学对象、处理阶段、来源版本、执行证据联系起来，避免虽合法但已过期、错作用域或不完整的结果发布。**确实提出/改进了什么？** 旧 CIEDG/v3 已实现目标实例、共同证据图、科学合同/资源预检和局部恢复；本轮没有新增算法，仅给出可复述的方法定义、五个跨族反例与先行工作可区分性审查。**与先行工作差异？** EEG 状态字段及工程集成有领域价值，但声明式读/写投影可被成熟 typed DAG + provenance/增量重算及同规则 Expert 等价表达，尚无独立机制差异。**证据支持/反对？** 旧正式比较与强 Expert 24/24、109/109 持平；一次扩展 42/41 LOC，开发版 C1–C8 不是正式胜负。质量自适应旧 Pilot 亦与强 Expert 持平。**决策：STOP 把投影/图作为已成立的论文算法贡献；保留 Harness 系统，不继续为证明优势加代码。** 两个转向缺少可执行的独立真值/校准，暂不立项。若导师要求方法点，需先解决真值与公平最近邻对照，而不是让实现量反推创新性。

## 1. 执行边界与状态

- Issue #30 阶段 0：核对 PR #27 远端 `fb5b85b` 与本地等树分叉；`git fetch` 后用非强制、非重置 `--no-ff` merge 得 `2a54367`，在其上建 `research/point1-sprint`。旧代码树、冻结结果、main 均未修改。检查 `v3.py`、`v3_agent.py`、`v2_graph.py`、`v11.py`、ToolSpec、Issue #16/PR #23/质量 Pilot 文档。
- 阶段 1：**先于任何核心代码改动**提交 `7b096e7` 的 `POINT1_RESEARCH_SPRINT_DECISION.md`。P1–P5 涉及连续+事件的频带/事件范围/参考，以及模型资源与 Profile；逐案评估合理 typed workflow/Expert 可表达性，结论投影方法 NO-GO。并非以已有 C1–C8 包装新 holdout。
- 阶段 2B：比较目标相对质量/采集条件与专业协同冲突两条方向。前者已有 SME/PREP/自动质控先行工作、旧质量 Pilot 强 Expert 持平且缺跨范式校准；后者若只是合同不一致或多 Agent 投票，未区别于成熟约束/权限机制，也无独立冲突真值。两者在本轮依赖下都不能给出公平而有判别力的 PoC，所以按 Issue 停线**未选择、不实现**。阶段 2A 不适用。
- 阶段 3：未启动新方法/新 holdout，不伪造独立比较或消融；本轮只核查既有证据、执行回归，历史结果保持原样。全图重放只能说明基础增量效果，不作为决定性对手。Native LLM 不等同于同规则 Expert。没有付费 API 调用、没有真实 EEG 读取或外发。
- 阶段 4：形成 `POINT1_RESEARCH_SPRINT_METHOD_CHAPTER.md` 章节级批判性草稿，包含定义、算法、信任边界、不变量、复杂度、先行对照、两个转向和停线。它不是论文完成或原创算法确认。

## 2. 原始依据与失败归因

| 证据/故障 | 可检验事实 | 对本轮判断的影响 |
|---|---|---|
| Issue #16 冻结 parsed-task | Strong Expert 与 CIEDG 均 24/24、109 calls；whole replay 121；S09 protocol-invalid。 | 失效恢复有工程作用，但同规则 Expert 无劣势，旧正式集不能证投影优越。 |
| PR #23 扩展 | 双方均 7/7、37 calls；方法特定 42 vs 41 LOC。 | “扩展减少专家维护”目前无正面实测依据。 |
| v3 开发 C1–C8 | 连续/事件/严格模型在可用 Profile 下通过开发验收；C2 真模型漏事件 `labels` 后安全澄清。 | 可用性不等于意图完备或公平新胜率。C2 是语义提议层，不由图合同自动修复。 |
| 质量 Pilot | Candidate/同规则 Expert 均 16/16、32 calls；真实阈值敏感。 | 不应把同门控规则迁移成“新自适应方法”；缺校准和跨范式真值。 |
| P1–P5 预写依赖例 | typed workflow 与合理 Expert 在相同专家合同下原则上均可实现。 | 这是机制可表达性反例，**不是运行实验分数**。 |

第一点与第四点是候选方法/对照同样正确的负结果；C2 是意图遗漏；S09 是评价协议错误，不得混为规划科学状态失败。当前尚无新版 v3 相对同规则 Expert/typed workflow 的正式结果，也无跨数据集泛化证据。

## 3. 可复现检查与资源账

环境为本机现存 Python 3.10 `eegagent`，MNE 1.6.1、NumPy 1.24.4、SciPy 1.10.1。起初 base 环境缺 MNE、`eegagent` 环境缺 pytest；为只读回归在**本地环境而非 Git**安装 pytest 8.4.2，未下载数据/模型。混合两环境 site-packages 尝试失败，不作为通过记录。正确验证命令（PowerShell，在仓库根目录）：

```powershell
$env:PYTHONPATH='src'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& '<eegagent-env>\python.exe' -m pytest tests/test_point1_multitask_v3.py -q
& '<eegagent-env>\python.exe' -m pytest tests/test_multitask_acceptance.py -q
& '<eegagent-env>\python.exe' -m compileall -q src tests
& '<eegagent-env>\python.exe' -m unittest discover -s tests -q
```

实测：v3 定向 **29 passed、1 skipped**；跨任务验收 **4 passed、1 skipped**；compileall 通过；完整 unittest **273 tests、OK、15 skipped**。跳过项为当前未给测试加载相应本地资源，不得记作通过。本轮没有改源码/科学真值，以上属于**未退化检查**，不是新方法验证。付费 LLM：0 completion / 0 tokens；真实受试者数据外发：0；未运行新的独立数值/资源 oracle，因为没有实施候选算法。

## 4. 贡献分层与下一步

| 层次 | 现在能诚实表述的内容 |
|---|---|
| 通用 Harness 实现 | EEGRecord/Profile/Registry/Executor/Context、目标实例、结构化结果与轨迹等可运行系统；不是算法原创性的充分条件。 |
| EEG-specific 适配 | 导联/采样率/Profile、事件/Epoch 作用域、source/effective provenance、模型资源门控；必要且可复用，但需专家知识。 |
| 成熟技术拼合 | typed contracts、DAG、哈希、局部重算、来源与证据发布。仅有领域命名并未产生新算法。 |
| 可主张独立贡献 | **当前无充分证据。** 投影合同与最近邻可等价表达；两个 Pivot 候选未满足科学真值及公平对照门槛。 |

建议导师讨论的唯一下一步是决定能否取得预先定义的、**目标相关**质量/有效性真值或专业冲突真值，并约定与获得相同规则的强 Expert/typed workflow 的判别指标和数据来源。若没有，论文工作点一应收缩为经过严格验证的多任务 EEG Harness 系统方法及负结果，**不要继续声称独立规划算法**；需由导师共同调整论文贡献要求。本轮明确停止，不开启第二点、ASD、R3、第三状态转换或没有必要的 LLM 消耗。

## 5. 提交与公开边界

预实现决策提交 `7b096e7`；本报告与章节草稿、状态文档提交 `2333c76`，发布记录 `ea42c01`，均已普通推送至独立分支；[Draft PR #31](https://github.com/lzy123-web/eeg-agent-harness/pull/31) 以 PR #27 原研究分支为 base，保持 Draft。[`unit-tests` #191](https://github.com/lzy123-web/eeg-agent-harness/actions/runs/40120350077) 对 `ea42c01` 已 `success`，这是独立于本地回归的远端 CI。仅文档、无密钥、权重、EDF、私人路径或生成轨迹进入 Git。不合并 main、不 force push。
