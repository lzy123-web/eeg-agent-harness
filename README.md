# EEG Agent Harness

本仓库是论文《面向多任务脑电分析的智能体执行框架研究与应用》的正式开发目录。当前代码基线只复现原始 EEGAgent 的一条确定性分析链：

```text
真实 EDF → 原有滤波/陷波/重采样 → 显式 EEGRecord（22 导双极数据）
         → 幅值与频带功率 → seizure/non-seizure 模型推理 → JSON 结果
```

该链路不调用 LLM API，不包含状态感知规划、证据驱动自适应分析或 ASD 综合评估。

## 来源和资源边界

代码从本地原始项目 `D:\Profession\Programs\CANKAO\EEGAgent-main\EEGAgent-main` 的相关模块迁移并做最小封装。来源和许可状态见 [THIRD_PARTY_NOTICE.md](THIRD_PARTY_NOTICE.md)。

以下资源不复制进本仓库，也被 `.gitignore` 排除：

- 测试 EDF：原项目 `data/gped_049_a_6.edf`；
- 模型权重：原项目 `tools/localModels/seiz&normal.pth`；
- API 密钥、真实 EEG 数据和运行结果。

运行时必须通过命令行参数或环境变量显式提供资源路径：

- `EEG_HARNESS_EDF_PATH`
- `EEG_HARNESS_MODEL_PATH`

## 已验证环境

- Windows 11
- Python 3.10.17
- MNE 1.6.1
- NumPy 1.24.4
- SciPy 1.10.1
- PyTorch 2.14.1+cpu

可使用现有 Conda 环境：

```powershell
$python = 'C:\Users\Nick\.conda\envs\eegagent\python.exe'
$env:PYTHONPATH = "$PWD\src"
& $python -m pip check
```

新环境可参考 `environment.yml` 或 `requirements.txt`。PyTorch 的 CPU/CUDA 构建应按运行机器和官方安装源选择；`requirements.txt` 记录本次验证的主版本。

## 运行最小链路

```powershell
$python = 'C:\Users\Nick\.conda\envs\eegagent\python.exe'
$env:PYTHONPATH = "$PWD\src"

& $python -m eeg_harness.cli `
  --edf 'D:\Profession\Programs\CANKAO\EEGAgent-main\EEGAgent-main\data\gped_049_a_6.edf' `
  --model 'D:\Profession\Programs\CANKAO\EEGAgent-main\EEGAgent-main\tools\localModels\seiz&normal.pth' `
  --channel 'FP1-F7' `
  --start 0 `
  --end 1 `
  --output 'artifacts\baseline_result.json'
```

也可先设置环境变量，再省略 `--edf` 和 `--model`。CLI 会把真实输入 shape、采样率、特征、模型概率、依赖版本和资源 SHA-256 写入 JSON。`artifacts/` 不进入 Git。

## 自动化测试

资源型 smoke test 通过环境变量接入外部 EDF 和权重；资源未配置时会明确跳过，而缺失模型错误测试始终运行。

```powershell
$python = 'C:\Users\Nick\.conda\envs\eegagent\python.exe'
$env:PYTHONPATH = "$PWD\src"
$env:EEG_HARNESS_TEST_EDF = 'D:\Profession\Programs\CANKAO\EEGAgent-main\EEGAgent-main\data\gped_049_a_6.edf'
$env:EEG_HARNESS_MODEL_PATH = 'D:\Profession\Programs\CANKAO\EEGAgent-main\EEGAgent-main\tools\localModels\seiz&normal.pth'

& $python -m unittest discover -s tests -v
```

## 显式数据对象

正式执行链使用 `EEGRecord` 显式携带二维 EEG 数组、真实采样率、通道名、参考/导联说明、原始来源和处理元数据。幅值、PSD 与癫痫推理工具均直接接收该对象；统一 `record.slice(start, end, channels)` 接口负责通道、时间顺序、空窗口和记录长度校验。`legacy.register_data` 仅为来源对照保留，正式 pipeline 不再导入或调用它。

## 当前遗留边界

- `legacy.register_data` 文件仅作为迁移来源留存，不属于正式执行链；后续确认无兼容需求后可删除。
- 当前只迁移 22 导 TUEV 风格双极链路和一个癫痫二分类权重接口。
- 模型训练数据来源、许可证和原始指标在源码中未提供；输出仅用于工程复现，不构成临床结论。
- LLM、RAG、Sleep、MDD 和其他模型工具未进入本代码基线。
