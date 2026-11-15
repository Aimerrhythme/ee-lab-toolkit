# 电表日用电周矩阵热图与缺失处理

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Fold daily smart-meter kWh into week × weekday heatmaps, with gap filling (Python + MATLAB).**

把每户的日用电量序列折成「周 × 星期」矩阵：先标出缺失（空值、`NaN`、负数），只对**中间的短缺口**做线性插值，再按户做 min-max 归一化并画热图。缺口太长或在首尾的天数保持缺失（灰色），不硬补。这是窃电 CNN 分类之前的输入准备课：学生先看「正常用户的周纹理」和「用电突降的用户」长什么样。示例数据完全合成。

## Dependencies

- Python 3.10+：`numpy`, `matplotlib`（测试另需 `pytest`）
- MATLAB R2021b+：仅基础 MATLAB，无需工具箱

## Quick start

```bash
# Python (from repo root)
python tools/meter-weekly-heatmap/examples/run_demo.py
python -m pytest -q tools/meter-weekly-heatmap/tests
```

```matlab
% MATLAB: cd tools/meter-weekly-heatmap/matlab, then
demo_meter_weekly_heatmap
```

Python 输出写到 `examples/output/`（已被 gitignore）：`meter_weekly_heatmap/matrix_long.csv`、`summary.csv` 和 `meter_weekly_heatmap_demo.png`。MATLAB 写到同目录的 `*_matlab` 版本，数值应一致。

## Input / API

输入 CSV：`customer_id,label,date,kwh`，日期 `YYYY-MM-DD`。空值、`NaN`、负数都当缺失；同一天重复记录保留第一行。

```python
res = meter_weekly_heatmap(csv_path, output_dir=None, output_png=None, max_gap=3, show=False)
```

```matlab
res = meter_weekly_heatmap(csvPath, 'max_gap', 3, 'output_dir', d, 'output_png', f, 'show', false)
```

| 参数 | 默认 | 含义 |
|---|---|---|
| `max_gap` | 3 | 最长可插值的连续缺失天数（仅限两端都有读数的中间缺口） |
| `output_dir` | 无 | 给定则写 `matrix_long.csv` 与 `summary.csv` |
| `output_png` | 无 | 给定则保存热图 |
| `show` | false | 是否弹出图窗 |

所有用户共用同一张网格：从全局最早日期所在周的周一，到全局最晚日期所在周的周日。星期编号 0 = 周一。

`res.customers` 每户含 `kwh`、`norm`（周数 × 7，缺失为 NaN）、`status`（`observed` / `filled` / `missing`）、`n_observed`、`n_filled`、`n_missing`、`missing_rate`（该户自身首末日期之间的原始缺失比例）、`weekend_ratio`（周末均值 / 工作日均值）。

## Example output

合成 4 户、8 周：`M01` 办公型（工作日高，周末比 ≈ 0.46）；`M02` 居民型（周末高，≈ 1.50）；`M03` 第 29 天起用电骤降到约 1/4（热图后半段整体变暗，是窃电类样本的典型纹理）；`M04` 缺口多，末尾 4 天缺失，保持灰色。运行后终端会打印每户观测 / 插值 / 缺失天数。

## Limitations

- 线性插值只适合短缺口；长缺口是否补、怎么补由实验自己讨论
- min-max 对极端值敏感，一个异常尖峰会压扁其余天数
- 热图只是看数据的手段，不是窃电判定结论
- 示例为随机生成，MATLAB 版本与 Python 逐项对应，但仓库测试只覆盖 Python

## Disclaimer

教学辅助用途（MIT / 教学免责）：用于理解数据预处理，结果不作为用电稽查、处罚或考核依据。请勿把学生姓名、学号、成绩或未公开的真实用电数据放进示例或提交到仓库。

## License

MIT — 见仓库根目录 [LICENSE](../../LICENSE)。
