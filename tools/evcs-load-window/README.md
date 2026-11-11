# 充电桩负荷清洗与特征窗切分

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Clean EV charging-session records, resample to a station load series, and cut fixed windows for forecasting (Python + MATLAB).**

把充电会话记录（起止时间 + 功率）清洗后，按时间重叠折算成固定步长的站级平均功率序列，再切成「输入窗 X / 预测窗 y」导出 CSV，供 LSTM 或基线预测脚本共用。专升本实验的重点是：数据管线先于模型调参。示例数据为合成，不含真实用户或场站数据。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`, `pandas`, `matplotlib`（见仓库 `requirements.txt`）；测试需 `pytest` |
| MATLAB R2021b+ | 基础 MATLAB 即可，无需额外工具箱 |

## Quick start

在仓库根目录执行。

### Python

```bash
pip install -r requirements.txt
python tools/evcs-load-window/examples/run_demo.py
pytest tools/evcs-load-window -q
```

```python
import sys
sys.path.insert(0, "tools/evcs-load-window/python")
from evcs_load_window import evcs_load_window

r = evcs_load_window("tools/evcs-load-window/examples/data/synthetic_sessions.csv",
                     step_min=15, input_len=8, horizon=4, stride=4)
print(r.X.shape, r.y.shape, r.n_dropped)
```

### MATLAB

```matlab
cd('tools/evcs-load-window/matlab')
demo_evcs_load_window
```

输出写到 `tools/evcs-load-window/examples/output/`（已 gitignore）。

## Input CSV

列：`session_id,start_time,end_time,power_kw`。时间格式 `yyyy-MM-dd HH:mm:ss`，功率为会话平均充电功率（kW）。

## Parameters

Python 关键字与 MATLAB 名值对同名。

| Name | Default | Description |
|------|---------|-------------|
| `csv_path` | — | 会话 CSV 路径 |
| `step_min` | `15` | 重采样步长（分钟） |
| `input_len` | `8` | 输入窗长度（步数） |
| `horizon` | `4` | 预测窗长度（步数） |
| `stride` | `4` | 相邻窗起点间隔（步数） |
| `max_power_kw` | `150` | 功率上限；超出视为异常行并丢弃 |
| `output_csv` | 不保存 | 窗口 CSV 输出路径，列 `window_start,x_0..,y_0..` |

## API

| Field | Meaning |
|-------|---------|
| `time` | 每个时间格的起点 |
| `load_kw` | 每格站级平均功率（kW），会话按与格的重叠时间加权，能量守恒 |
| `X` | `n_windows × input_len` 输入矩阵 |
| `y` | `n_windows × horizon` 目标矩阵 |
| `window_start` | 每个窗口首个输入格的时间 |
| `n_sessions` | 读入行数 |
| `n_dropped` | 被清洗丢弃的行数 |
| `step_min` | 实际步长 |
| `output_csv` | 写出的路径；未保存为空 |

清洗规则：字段缺失、结束时间不晚于开始时间、功率不在 `(0, max_power_kw]` 的行被丢弃。窗口个数为 `floor((nbins − input_len − horizon)/stride) + 1`（不足一窗为 0）。

## Example output

`examples/data/synthetic_sessions.csv` 含 2024-06-03 至 06-04 的 44 条合成会话，加 4 条故意放入的坏行（结束早于开始、功率缺失、0 kW、900 kW）。demo 丢弃这 4 行，得到 165 个 15 分钟格、39 个窗口，并画出站级负荷阶梯图（早晚高峰明显，夜间为 0）。

## Limitations

- 以会话平均功率为常数近似，不含充电曲线的恒流/恒压阶段
- 夜间无会话的时段负荷为 0，不做插值或节假日标注
- 窗口按时间顺序切分，划分训练/测试集时请按时间切，勿随机打乱
- 时间按朴素时间处理，不做时区换算；MATLAB 版要求严格的 `yyyy-MM-dd HH:mm:ss`

## FAQ

**Python 和 MATLAB 结果一致吗？** 字段与数值一致；窗口 CSV 中数字的小数位格式可能略有不同（如 `138.0` 与 `138`）。

**为什么不直接用会话数据训练？** 预测模型需要等间隔序列；先聚合、切窗，再比较基线与模型才公平。

## Teaching disclaimer

教学辅助用途：帮助理解充电负荷数据预处理，结果不作为工程投运、调度或结算依据。请勿把学生姓名、学号或未授权的场站/用户数据放进示例或提交到仓库。License: MIT.
