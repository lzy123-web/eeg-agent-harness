# 项目状态

## 当前阶段

阶段 1：显式 EEG 数据对象与最小确定性分析链已建立。

当前工作目录 `D:\Profession\Programs\CANKAO\eeg-agent-harness` 已成为可独立维护的 Python 项目；审计和复用源仍为相邻的 `D:\Profession\Programs\CANKAO\EEGAgent-main\EEGAgent-main`。本阶段没有修改原 EEGAgent 核心实现，也没有复制真实 EDF 或模型权重。

## 已完成工作

- 完成 EEGAgent 目录、38 个 Python 源文件、依赖、配置、数据样例、11 个注册工具和 11 个工具权重的盘点。
- 定位 Agent 入口、核心循环、Prompt、LLM 调用、工具注册、文本解析和工具执行链。
- 梳理默认 EDF 加载、预处理、22 导双极派生、全局数据注册、特征计算和模型推理链路。
- 核对 TUEV、Sleep-EDF 和 MDD 评估/训练脚本及其路径、通道和输入条件。
- 将各模块划分为可直接复用、封装后复用和不建议直接复用。
- 确定第一阶段最小基线：EDF、基础特征、事件检测和 `seizureNormalModel_OneSecond` 推理；ERP 与 ASD 不在第一阶段。
- 建立项目长期规则、源码审计报告和基线计划。
- 初始化 `src/eeg_harness` Python 包、CLI、最小配置、依赖说明、来源与许可状态说明。
- 迁移并最小封装 `polar.py`、`preprocessing.py`、`dataLoad.py`、`registerData.py`、幅值/PSD、RoPE 模型组件及 `seizureNormalModel_OneSecond`。
- 使用显式 EDF/权重路径和惰性模型加载，避免工具发现时加载无关模型。
- 建立标准库 `unittest` smoke test，覆盖真实 EDF、特征、模型输出、JSON 序列化和缺失权重失败。
- 建立 `.gitignore`，排除 EEG 数据、模型权重、密钥、本地资源配置和生成结果。
- 新增通用 `EEGRecord` 数据对象，显式保存二维 EEG 数组、真实采样率、通道名、参考/导联说明、原始来源、处理步骤和来源元数据。
- 新增统一 `EEGRecord.slice` 接口，校验未知通道、负时间、倒置时间、空时间窗、记录越界和采样后空窗。
- 将幅值、PSD、`seizureNormalModel_OneSecond` 及 `pipeline.py` 改为显式接收/传递 `EEGRecord`；正式执行链不再导入或调用 `legacy.register_data`。
- 保留原始预处理、幅值、Welch PSD、模型结构和权重加载算法，未修改相邻原始 EEGAgent 项目。

## 实际验证结果

验证日期：2026-10-21。验证未调用外部 LLM、未下载数据、未训练模型。

| 检查项 | 结果 |
|---|---|
| Python 源码语法读取 | 38 个 `.py` 文件均可由 `ast.parse` 解析。 |
| 运行环境 | 使用 `C:\Users\Nick\.conda\envs\eegagent\python.exe`；`pip check` 无损坏依赖。 |
| 关键环境 | Python 3.10.17、MNE 1.6.1、NumPy 1.24.4、SciPy 1.10.1、PyTorch 2.14.1+cpu。最小基线不依赖 OpenAI。 |
| 工具注册 | 成功发现 11 个工具。 |
| EDF 样例 | `gped_049_a_6.edf` 原始 250 Hz、33 信号、241 秒。 |
| 默认预处理输出 | `(22, 61696)`、`float32`，目标采样率 256 Hz。 |
| 成功路径 | 幅值、PSD、对称性、单通道癫痫、10 秒慢波/癫痫/背景、整段正常/异常。 |
| Sleep 工具 | 在默认 22 导数据上失败：模型期望 2 导。 |
| MDD 工具 | 在默认 22 导数据上失败：模型期望 19 导。 |
| RAG | BGE-M3 目录缺少 `model.safetensors`/`pytorch_model.bin`，初始化抛出 `OSError`；Agent 可降级跳过。 |
| 外部 LLM | 未执行，未验证 API 可用性、真实工具规划或端到端回答质量。 |
| 现有测试 | 未发现标准 `test_*.py`/`*test*.py` 测试套件；评估脚本会写输出，不在本轮执行。 |
| 改造前 smoke test | `python -m unittest discover -s tests -v`：原有 5 项全部通过。 |
| 显式数据对象回归测试 | 同一命令共 10 项全部通过：新增 5 项覆盖正常切片、无效通道、时间越界、空时间窗和两份记录交替使用的数据隔离。 |
| 正式项目 CLI | 成功生成 `artifacts/baseline_result.json`；该目录被 Git 忽略。 |
| 幅值结果（FP1-F7, 0–1 s） | mean_abs `1.74e-05`、RMS `2.37e-05`、max `2.63e-05`、min `-6.14e-05`。 |
| PSD 结果（FP1-F7, 0–1 s） | delta `1.86e-10`、theta `1.24e-10`、alpha `2.03e-11`、beta `1.56e-12`、gamma `6.96e-13`。 |
| 癫痫模型结果（FP1-F7, 0–1 s） | `Non-seiz=0.0`、`seiz=1.0`；这是现有权重在单一样例窗口的工程输出，不是性能或临床结论。 |
| 模型输入与权重 | 单窗 shape `[1, 256]`；`seiz&normal.pth` SHA-256 `e67a7b7aa958642b4d194c03fe4750995be89150e84b82cf78d662d35831c41b`。 |
| EDF 校验值 | `gped_049_a_6.edf` SHA-256 `9f83f1294724fa04686e9051f085c4a9c0d1fe9854126c3c13c52c25577104cf`；资源未进入 Git。 |
| 改造前后回归 | 使用同一 EDF、权重、`FP1-F7` 0–1 秒窗口比较；输出 shape、256 Hz 采样率、幅值与五频带 PSD 结果、模型概率、EDF 与模型 SHA-256 全部一致，确定性字段无差异。 |

仓库内存在历史 TUEV Agent 与 oracle 汇总文件，但本轮未重新复现。相关数字仅在 `CODE_AUDIT.md` 作为历史产物记录，不作为当前基线实验结论。

### 本轮验证命令

在项目根目录设置 `PYTHONPATH=src`，并用环境变量 `EEG_HARNESS_TEST_EDF`、`EEG_HARNESS_MODEL_PATH` 指向原始 EEGAgent 中的现有 EDF 和权重后执行：

```powershell
& $python -m pip check
& $python -m compileall -q src tests
& $python -m unittest discover -s tests -v
& $python -m eeg_harness.cli --edf $env:EEG_HARNESS_TEST_EDF `
  --model $env:EEG_HARNESS_MODEL_PATH `
  --output artifacts\after_explicit_record.json
```

改造前结果保存在本地忽略目录 `artifacts/before_explicit_record.json`，改造后结果保存在 `artifacts/after_explicit_record.json`；两者仅用于本轮本地回归，没有进入 Git。比较时排除生成时间和运行耗时，确定性字段全部相同。

## 未解决问题

1. 默认主入口固定生成 22 导数据，Sleep 2 导和 MDD 19 导工具无法按任务自动选择正确加载链。
2. `legacy/register_data.py` 文件仍为迁移来源保留，但正式 pipeline、工具和测试已不再依赖；尚未执行物理删除。
3. 工具自动发现会加载全部本地模型；缺少 Profile 过滤、惰性加载和统一资源错误。
4. 工具 schema 不是标准 JSON Schema，工具调用依赖正则文本协议，参数校验不足。
5. `reflectData` 返回 NumPy 数组，当前消息回注无法直接 JSON 序列化。
6. RAG 主模型权重缺失，报告模板也没有进入当前生效 Prompt。
7. MDD、Sleep、TUEV Agent 评估脚本与默认路径或返回结构不一致，不能直接作为回归测试。
8. 多数本地权重的训练数据、版本、许可证和指标来源在源码中未提供。
9. 已有最小 CLI、显式数据对象测试和资源型 smoke test，但尚无 CI、跨平台锁文件、完整资源 manifest 或多样本回归集。
10. 原始项目没有发现许可证文件；源码和权重许可需在公开分发前确认。

## 下一步候选任务

按优先级排列：

1. 把 22 导 montage、采样率和模型输入约束提升为最小 `TaskProfile`，增加缺导和错误采样率测试。
2. 在确认没有兼容调用方后移除已脱离正式链路的 `legacy/register_data.py`，并将迁移工具逐步移出 `legacy` 命名空间。
3. 建立资源 manifest，记录权重 SHA-256、来源状态、输入契约和许可状态。
4. 增加 CI 可运行的无权重单元测试，并为资源型 smoke test保留显式启用方式。
5. 以上接口稳定后再设计统一 Executor/Trace；LLM、Sleep、MDD、ERP 和 ASD 继续后置。
6. 候选研究机制“状态感知与约束规划”和“证据驱动自适应分析”仍为拟研究功能，本阶段没有实施。

## Git Commit 信息

- 正式项目已初始化本地 Git 仓库；相邻原始 EEGAgent 目录保持非 Git、未修改。
- 正式远程仓库：`https://github.com/lzy123-web/eeg-agent-harness.git`，远程名为 `origin`。
- 后续代码或项目文档变更须在验证后提交并推送；禁止提交密钥、真实 EEG 数据、大型模型权重、本地资源配置和生成产物，禁止未经授权强制推送。
- 代码基线 Commit：`9f235b8`（`建立最小 EEG 分析代码基线`）。
- 基线验证状态 Commit：`e962991`（`记录基线验证与提交信息`）。
