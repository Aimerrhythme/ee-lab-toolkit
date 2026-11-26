# 非侵入式负荷分解数据对齐与滑窗切分 (nilm-window-prep)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Align aggregate and appliance power by timestamp, resample, fill short gaps, and cut seq2point windows (Python + MATLAB).**

NILM（非侵入式负荷分解）模型训练前的数据准备：把总表功率与分项电器功率按时间戳对齐到规则网格，补上短缺口，再切成"总功率窗 → 窗口中点电器功率"的样本对（seq2point 的输入形式）。步骤：

1. 按 `step_s` 秒分箱取均值（第 k 箱覆盖 [t0+k·step, t0+(k+1)·step)），空箱记 NaN
2. 长度 ≤ `max_gap_steps` 的内部 NaN 段线性插值；更长的缺口保持缺失（不硬补）
3. 每隔 `stride` 箱取一个长度为 `window`（奇数）的窗；只有窗内总功率全有限、且中点电器功率有限时才保留

思路参考 NILMTK（[github.com/nilmtk/nilmtk](https://github.com/nilmtk/nilmtk)）的数据对齐流程；本工具**不依赖 NILMTK、不联网、不下载数据**，示例是合成数据（冰箱周期 + 三次水壶 + 噪声，含一个 12 s 和一个 120 s 缺口）。

## Dependencies

- Python 3.10+：`numpy`、`matplotlib`（测试另需 `pytest`）
- MATLAB R2021b+：只用基础函数，无需工具箱

## Quick start

```bash
# Python
python examples/run_demo.py
pytest tests
```

```matlab
% MATLAB (from the matlab/ folder)
demo_nilm_window_prep
```

两边打印相同的摘要行：`bins / empty_bins / filled / candidates / windows / dropped / y_mean_w`（Python 示例：300 / 22 / 4 / 97 / 87 / 10 / 229.885）。输出写入 `examples/output/`（已 gitignore）。

## Input format

`timestamp_s,aggregate_w,appliance_w`：时间戳为秒（相对或 epoch 均可），必须严格递增，允许不等间隔和缺行；功率单位 W。

## API

`nilm_window_prep(csv_path, step_s=6, max_gap_steps=3, window=11, stride=1, output_csv=None, output_png=None, show=False)`

MATLAB：`nilm_window_prep(csvPath, 'step_s', 6, 'max_gap_steps', 3, 'window', 11, 'stride', 1, 'output_csv', '', 'output_png', '', 'show', false)`

| 参数 | 默认 | 含义 |
|---|---|---|
| `step_s` | 6 | 重采样步长（秒），> 0 |
| `max_gap_steps` | 3 | 可被线性插值的最长缺口（箱数），0 表示不补 |
| `window` | 11 | 窗长（箱），必须为正奇数 |
| `stride` | 1 | 相邻窗起点间隔（箱） |
| `output_csv` | 无 | 每行 `start_bin,t_mid_s,y_w,x0..x{window-1}` |
| `output_png` | 无 | 上：重采样序列与未补缺口；下：样例窗与中点目标 |

返回：`X`（窗数×window）、`y`、`starts`（0 起始箱号）、`t_mid`、`agg`、`app`，以及计数 `n_bins、n_empty_bins、n_filled、n_candidates、n_windows、n_dropped`。`n_empty_bins` 是补缺前总功率的空箱数；`n_filled` 是两条序列补上的箱数之和。

## Example output

示例 1800 s 数据在 6 s 网格上得 300 箱；12 s 缺口被补上，120 s 缺口保留，覆盖它的窗被丢弃。上图红色为未补缺口，下图是 4 个样例窗，黑点是中点水壶功率（约 0 或 2000 W）。

## Limitations

- 示例数据是合成的，不代表真实家庭用电；真实数据（如 REDD、UK-DALE）请自行下载并整理成三列 CSV
- 只取分箱均值，不做去尖峰、归一化、训练/验证按时间划分；做模型前请先按时间切分再取窗，避免窗口重叠造成泄漏
- 只处理单个电器一列；多电器请分别运行
- MATLAB 版未在 MATLAB 环境实跑，仅按与 Python 相同语义人工核对

## FAQ

**为什么长缺口不补？** 补出来的是"想象的"功率，会让模型学到假样本；宁可丢窗。

**窗长为什么必须是奇数？** 这样"中点"是一个确定的采样点。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助理解 NILM 数据准备流程，结果不作为用电计量、计费或成绩评定依据。请勿把学生姓名、学号、成绩或未公开的真实用户用电数据放进示例或提交到仓库。本工具随仓库以 MIT 许可证发布，见根目录 [LICENSE](../../LICENSE)。
