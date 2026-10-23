# CIEDG 第二 EEG 状态转换设计

更新时间：2026-10-23（Asia/Shanghai）

## 1. 研究门槛

本轮检验的不是“再注册一个工具”，而是：CIEDG 能否把一条与质量筛选不同的真实信号转换表示为科学状态，使 reference-sensitive 证据随 lineage 正确失效，reference-independent 证据保留，并在派生 artifact 恢复时最小重放。

## 2. 候选比较

| 候选 | 科学前提与风险 | 当前代码复用 | 对 CIEDG 的检验力 | 决策 |
|---|---|---|---|---|
| 显式现有通道重参考 | 必须由用户授权并明确参考通道；通道必须存在；改变所有通道电位、质量和频谱 | EpochSet、artifact store、质量、Welch consumer 均可复用 | 新状态维度是 reference，不同于 trial selection；可验证属性保持/变化 | 选择 |
| Epoch 重采样 | 需明确目标 sfreq、抗混叠、Nyquist 与时间网格；逐 Epoch 重采样有边界效应 | 需引入 resample 算法及频带兼容检查 | 同时改变 sfreq、shape、时轴和频率条件，混杂较多 | 放弃本轮 |
| 创建 Epoch 后基线校正 | 需要 baseline 窗口且已由 `create_epochs(baseline=...)` 表达 | 高 | 更适合 producer 参数而非独立状态转换 | 不重复实现 |
| CSD/Laplacian | 依赖可靠 montage 几何和电极位置，当前原生 EDF 不保证 | 低 | 科学价值高但缺前提 | 阻断 |

MNE 将 `set_eeg_reference` 定义为对 Raw/Epochs/Evoked 的显式 EEG 重参考，允许一个或多个已有通道构造参考；指定多个通道时减去其均值：[MNE set_eeg_reference](https://mne.tools/stable/generated/mne.set_eeg_reference.html)。MNE 同时提醒，通用 average reference 若缺少原始参考零通道会产生偏差，因此本轮不把“全部当前通道平均”当成默认：[MNE reference tutorial](https://mne.tools/stable/auto_tutorials/preprocessing/55_setting_eeg_reference.html)。已有方法研究也指出参考选择会改变谱功率等测量及其解释，支持把 reference 作为科学状态而非展示元数据：[Rosetta Stone review](https://pmc.ncbi.nlm.nih.gov/articles/PMC2953588/)。

重采样未被选择并不表示它不合法。MNE 的说明指出 Epoch resampling 会低通以避免 aliasing，但会在每个 Epoch 边缘引入处理效应；Raw resampling 又可能降低事件时间精度：[MNE resampling FAQ](https://mne.tools/stable/help/faq.html)。在最后一轮有限泛化门槛中，重参考更能隔离“状态变化—证据失效”机制。

## 3. 新科学状态契约

### 3.1 操作

```text
goal: epoch_rereference
tool: rereference_epochs
input: current source Epoch artifact
required intent:
  rereference_authorized == true
  reference_channels is a non-empty explicit list
preconditions:
  profile == edf_native
  every reference channel exists exactly once
  source artifact fingerprint matches
effect:
  create a new immutable EpochSet with a new artifact ID
  data' = data - mean(reference channels)
  reference = explicit_average(channel list)
```

不允许 LLM选择默认通道、把“禁止重参考”解释为授权、修改事件条件或用转换后数据替代用户明确要求的转换前证据。

### 3.2 保持属性

- `sfreq`、shape、channel names/order；
- event labels、event onset seconds；
- `tmin/tmax`、baseline 声明、boundary rejection；
- source record 的去标识引用及父 artifact fingerprint。

### 3.3 改变与失效

- 改变：sample values、reference、content fingerprint、artifact identity；
- 必须失效：绑定旧 effective artifact 的 `epoch_quality`、`event_bandpower` 及包含当前 fingerprint/reference 的 summary evidence；
- 可保留：`list_events`、source `create_epochs` 和其他仅依赖事件/结构而非当前 reference 的 token；
- 内容等价重建：producer/transition 仍重建；无副作用 consumer 可按 semantic signature 复用，但发布视图必须绑定新 artifact identity。

## 4. 运行图

正常转换任务：

```text
observe_events → create_epochs → epoch_rereference
                                  ├→ epoch_quality
                                  ├→ epoch_summary
                                  └→ event_bandpower
```

受控 artifact 丢失恢复：

```text
events/source token 保留
old rereference output missing
  → invalidate rereference + quality + summary + bandpower
  → rebuild rereference from unchanged source (new ID, same content/reference)
  → quality evidence re-execute（不跨身份缓存 evidence producer）
  → summary semantic evidence reuse with explicit current-lineage release view
  → retry bandpower
```

这同时验证：一个 reference-dependent evidence 必须重算、一个纯 consumer 可在内容等价时复用、事件/source 目标不重放。

## 5. 与 v1.1 的最少扩展

计划新增：

1. `EpochSet.reference` 科学属性进入 fingerprint/summary；
2. 一个生产工具 `rereference_epochs`；
3. 一个 `epoch_rereference` GoalContract 和 `effective_epochs` transition；
4. transfer 专用 planner/agent 子类，不复制 Executor/Registry；
5. Intent schema 增加明确授权和参考通道槽位；
6. answer release 增加“历史 ToolResult”与“当前可发布 evidence view”分离。

若实现需要为每个 consumer 再写专用失效列表，泛化门槛判失败；若只需 contract、一个 transition 参数 resolver 及通用 release 修复，则可视为有限声明式迁移成功。Intent/CLI/Schema 的接线属于工程修改，不作为算法贡献。

## 6. 独立 oracle

- NumPy oracle：逐 Epoch/时间点计算参考通道均值并从全部通道相减；
- MNE oracle：构造 `mne.EpochsArray` 后 `set_eeg_reference(ref_channels=[...], projection=False)`；
- 属性 oracle：shape/sfreq/events/window 不变、reference 改变、参考通道（单参考时）为零；
- Welch oracle：用现有独立 SciPy 实现复算转换前后绝对频带功率，不能假设一定增加或减少。

## 7. 声明边界

本操作是研究用、用户指定的离线数学转换，不判断哪种 reference 临床上“更好”。二通道合成验证只证明实现与 lineage 机制，不能外推高密度 average reference、源定位、临床诊断或真实数据泛化。
