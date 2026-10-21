# 第三方来源说明

## EEGAgent 来源

本项目中的以下实现迁移或最小改编自本地原始 EEGAgent 源码：

- `src/eeg_harness/legacy/polar.py` ← `tools/polar.py`
- `src/eeg_harness/legacy/preprocessing.py` ← `tools/preprocessing.py`
- `src/eeg_harness/legacy/data_load.py` ← `tools/dataLoad.py`
- `src/eeg_harness/legacy/register_data.py` ← `tools/registerData.py`
- `src/eeg_harness/legacy/features.py` ← `tools/windowInfo.py` 中幅值和 PSD 实现
- `src/eeg_harness/legacy/model_components.py` ← `tools/localModels/net.py`
- `src/eeg_harness/legacy/seizure.py` ← `tools/singleChannel.py` 中 `SingleChannelEEG` 与 `seizureNormalModel_OneSecond`
- `config/baseline.json` ← `config/config.json` 中与本链路相关的配置

审计时的本地来源目录为：

`D:\Profession\Programs\CANKAO\EEGAgent-main\EEGAgent-main`

原项目 README 给出的引用信息为：

> Sha Zhao, Mingyi Peng, Haiteng Jiang, Tao Li, Shijian Li, Gang Pan. “EEGAgent: A Unified Framework for Automated EEG Analysis Using Large Language Models.” arXiv:2511.09947, 2025.

## 许可状态

在原始目录及其直接父目录中未发现 `LICENSE`、`COPYING` 或 `NOTICE` 文件，也未发现 Python 包元数据声明许可证。因此，迁移代码及随仓模型权重的许可状态目前不明确。本文件只记录来源，不构成额外许可授权。

在公开发布、对外分发或将代码/权重用于论文附件之前，应向原作者或正式上游仓库确认：

1. 源码许可证；
2. 模型权重的分发和使用许可；
3. 训练数据来源及其使用限制；
4. 论文引用和衍生作品要求。

## 未纳入仓库的资源

真实 EDF、`.rec` 标注、本地 `.pth`/`.pt` 权重、API 密钥和生成结果均不纳入 Git。运行时使用者必须自行提供具有合法使用权的资源路径。
