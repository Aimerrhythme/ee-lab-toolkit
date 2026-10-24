# 负荷 CSV 清洗与标准出图

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Clean a timestamped load CSV and save a standard load figure (Python + MATLAB).**

把实验或仿真导出的负荷曲线整理成可直接贴进报告的图：识别时间列与负荷列（kW），解析时间、处理缺失、用 IQR 或 z-score 标出尖峰，并可选计算日均负荷。示例数据是合成的三日小时负荷，不含真实用户或电网数据。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`, `pandas`, `matplotlib`（见仓库 `requirements.txt`） |
| MATLAB R2021b+ | 基础 MATLAB 即可，无需额外工具箱 |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/load-csv-plot/examples/run_demo.py
```

脚本会读取 `examples/data/synthetic_load_kw.csv`，并把图写到 `examples/output/load_csv_plot_demo.png`（该目录已 gitignore）。

在自己的脚本里调用：

```python
import sys
sys.path.insert(0, "tools/load-csv-plot/python")
from load_csv_plot import load_csv_plot

result = load_csv_plot(
    "tools/load-csv-plot/examples/data/synthetic_load_kw.csv",
    agg="daily_mean",
    output_png="tools/load-csv-plot/examples/output/load_csv_plot_demo.png",
)
print(result.n_rows, result.n_missing, result.n_outliers, round(result.mean_kw, 2))
```

### MATLAB

```matlab
cd('tools/load-csv-plot/matlab')
demo_load_csv_plot
```

或从仓库根目录：

```matlab
addpath('tools/load-csv-plot/matlab')
demo_load_csv_plot
```

图写到 `tools/load-csv-plot/examples/output/load_csv_plot_demo_matlab.png`。要在 IDE 里留住窗口，把 demo 中的 `'show', false` 改成 `'show', true`。

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。

| Name | Default | Description |
|------|---------|-------------|
| `csv_path` | — | CSV 路径。逗号或分号分隔，UTF-8 |
| `time_col` | 自动 | 时间列。可用表头别名，或显式指定 |
| `load_col` | 自动 | 负荷列，单位 kW |
| `agg` | `none` | `none` 只画清洗曲线；`mean` 叠加全程均值线；`daily_mean` 增加日均面板 |
| `outlier_method` | `iqr` | `iqr`、`zscore` 或 `none`。有限样本少于 4 个时不标记尖峰 |
| `z_thresh` | `3` | z-score 阈值，超出则记为尖峰。使用样本标准差（N−1） |
| `iqr_k` | `1.5` | IQR 倍数。区间为 `[Q1 − k·IQR, Q3 + k·IQR]`，IQR 为 0 时不标记 |
| `fill_method` | `interpolate` | `interpolate` 按时间线性插值（端点取最近有效值）；`ffill` 先前向再后向；`drop` 删掉缺失负荷行，尖峰保留在曲线上 |
| `output_png` | 不保存 | PNG 输出路径。父目录不存在时会创建 |
| `show` | `false` | 为真时显示图窗。Python demo 使用无界面后端，只保存文件 |

时间列表头（忽略大小写、空格、下划线和括号）包括 `timestamp`、`time`、`datetime`、`date`、`时间`、`时刻`、`时间戳`。负荷列包括 `load_kw`、`load`、`power`、`kw`、`Load (kW)`、`负荷`、`负荷(kW)`、`有功功率`。无法识别时传入 `time_col` / `load_col`。

## API

两侧返回同一组字段。

| Field | Meaning |
|-------|---------|
| `time` | 解析后的时间，已排序并去掉重复时刻（保留先出现的一行） |
| `load_kw` | 清洗后的负荷。`interpolate` / `ffill` 时，尖峰位置被填补 |
| `load_raw_kw` | 原始数值；缺失为 NaN |
| `is_outlier` | 与 `time` 对齐的尖峰标记 |
| `n_rows` | 返回序列长度（`drop` 之后） |
| `n_missing` | 时间有效行里，填补前的非有限负荷个数 |
| `n_outliers` | 尖峰个数 |
| `mean_kw` | `load_kw` 的均值 |
| `daily_mean` | 列 `date`、`mean_kw`。仅当 `agg='daily_mean'` 时有数据，且用的是清洗后的序列 |
| `output_png` | 实际写入的路径；未保存时为空 |
| `fig` | 显示图窗时的句柄；不显示时为空 |

## Example output

`examples/data/synthetic_load_kw.csv` 为 2024-06-01 至 2024-06-03 的小时负荷，共 72 行，并故意放入三处缺陷：

- `2024-06-01 04:00` 负荷缺失
- `2024-06-02 12:00` 尖峰 `950 kW`
- `2024-06-03 18:00` 跌落 `5 kW`

默认 IQR 会标出后两处。demo 使用 `agg='daily_mean'`：上图是清洗后的负荷曲线（夜间低谷、早晨抬升、傍晚高峰），红叉落在清洗曲线上，并标注原始值（`raw 950 kW`、`raw 5 kW`），避免 950 kW 把纵轴撑扁；下图是清洗后的三日日均。z-score 在这个文件上通常只抓住 950 kW，因为该点把标准差拉大了，5 kW 的跌落不再超过 3σ。坐标和标题使用英文，机房缺少中文字体时也不会乱码。

## Limitations

- 只接受单独的时间戳列，不会把「日期 + 时刻」两列拼起来
- 尖峰规则是对负荷值的单变量 IQR / z-score，不是分季节、分时段的用电校验
- 时间按朴素时间处理，不做时区换算；日均按时间戳上的日历日分组
- 有效样本少于 4 个时不判尖峰；序列完全相同（IQR 或标准差为 0）时不判尖峰
- 示例曲线是公式生成的，不代表任何实际馈线或用户

## FAQ

**表头不是 `timestamp,load_kw` 怎么办？**  
中英文常见写法会自动匹配，也支持分号分隔。对不上时传入 `time_col` 和 `load_col`。

**尖峰会被删掉吗？**  
不会从原始列里抹掉。`load_raw_kw` 仍是原值，`is_outlier` 为真。默认插值只影响 `load_kw` 和日均，使曲线和图轴保持可读。`fill_method='drop'` 只删除缺失负荷行，尖峰仍留在曲线上。

**日均会被 950 kW 拉高吗？**  
不会。日均使用清洗后的 `load_kw`。若需要保留尖峰再做平均，请改用 `fill_method='drop'`（尖峰仍在）或 `outlier_method='none'`。

## Teaching disclaimer

教学辅助用途：帮助理解负荷曲线清洗和出图，结果不作为工程投运、计量或考核结算依据。请勿把学生姓名、学号、成绩或未授权的电网/用户数据放进示例或提交到仓库。
