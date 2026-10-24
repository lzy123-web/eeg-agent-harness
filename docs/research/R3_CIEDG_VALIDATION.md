# 冻结 CIEDG 接入真实 R3 的本地核验（Issue #24）

## 范围与预冻结协议

本次只验证已有 CIEDG 执行核心处理真实 R3 EDF 的工程链路，不运行真实 EEG → 外部 LLM，不改变冻结方法、原确定性 R3 workflow 或历史实验。运行前固定从两个按名称排序的**存储分区**，每个分区按相对路径排序选前两份 EDF，共 4 份；分区名称不用于组别推断。相同 `R3_PROFILE`、显式数字标签 1–8、`[-0.2, 0.8)` Epoch、`[-0.2, 0)` baseline、`config/baseline.json` 用于 CIEDG 与原确定性流程。标签、窗口、滤波和参考的科学适用性尚未验证。

数值验收事先规定：事件、Epoch 数和形状精确一致；数组及绝对频带功率 `rtol=1e-5, atol=1e-12`；所有输出有限；保留条件及 artifact lineage 正确；无自动试次筛选和重参考。全量单记录结果、路径、校验值、事件时刻和完整 trace 仅写入被 Git 忽略的 `r3_outputs/`，不进入本报告。

## 实际运行

使用 Python 3.10.17、MNE 1.6.1、NumPy 1.24.4、SciPy 1.10.1 的本地 `eegagent` 环境；`pip check` 无损坏依赖。本地只读清单为 2 个存储分区、69 份 EDF。固定 4 份成功加载，均为预期 21 导、300 Hz；每份均完成事件摘要与“Epoch 质量测量＋绝对频带功率”两项任务。按 14 项逐例检查，**4/4 通过、0 失败**。

检查包含：原 EDF annotation 与导入 EventSet 的数量/代码/相对时间一致；事件代码计数；接受/越界拒绝 Epoch 数；两个独立任务的 Epoch shape、有限性、标签；冻结 CIEDG 的 goal evidence 关闭；没有执行 selection/rereference；Epoch 摘要与原确定性流程及手动切窗一致；质量证据（除随机 artifact 身份字段）与原确定性流程一致；频带数值与独立 oracle 和原确定性流程一致；消费者和 release 的 artifact ID/fingerprint 对齐。

独立数值路径直接读取已处理 `EEGRecord` 的事件和二维数组，手动按采样率换算切窗、计算时域 baseline 均值，并逐 Epoch/通道用 SciPy `welch` 后频带积分；不调用被测的 `create_epoch_set` 或 `event_bandpower` handler。对 4 份记录，绝对频带功率与该 oracle 的最大绝对差为 `2.5849394142282115e-26`，与原确定性 workflow 的最大绝对差为 `0`。后者复用相同工具，不能单独证明算法无共同错误；手动路径补充了数值交叉检查。独立 oracle 从**已处理** EEGRecord 开始，未独立证明原始 EDF 滤波和平均参考的科学正确性。质量阈值仅做同工具结果一致性比较，未独立验证其生理或临床有效性。

没有为通过验证而换样、修改阈值或调整原方法。公开汇总不包含逐例计数、特征、身份可关联路径或来源哈希。

## 复现命令与回归

在已安装项目依赖的 PowerShell 会话中执行；`<已授权本地R3根目录>` 由操作者本机填写，不放入仓库配置或命令日志：

```powershell
$env:PYTHONPATH = 'src'
python -m eeg_harness.applications.r3.ciedg_cli `
  --data-root '<已授权本地R3根目录>' `
  --application-config config/r3_ciedg.example.json `
  --config config/baseline.json
python -m unittest discover -s tests -p test_r3_ciedg_application.py -v
python -m compileall -q src tests
python -m unittest discover -s tests
python -m pip check
```

CLI 只在 stdout 给出 `tested/passed/failed` 聚合数字；详细报告固定在 `r3_outputs/` 内，本地存在但被 Git 忽略。配置模板没有个人绝对路径。合成应用回归新增 6 项，涵盖真实 Registry/Executor 链、独立频带 oracle、缺失标签预检、unsupported 拒绝、固定选样和私有输出边界。全量本地回归：**227 tests，215 passed、12 按资源/联网门槛跳过、0 failed**；`compileall` 与 `pip check` 通过。CI 只运行无私有资源回归，不宣称 CI 复现了本地真实 EDF。

## 失败与边界

固定 4 份没有出现 IO、事件时间、状态、工具或 CIEDG 执行失败。这个小子集不能证明 69 份全部通过，也不能证明动作条件含义、坏道规则、采集参考、受试者映射、组别差异或 ASD 辅助评估。外部 LLM 未接收任何真实 EDF、路径、事件、特征或 trace。历史旧失败和冻结 CIEDG 实验没有修改。
