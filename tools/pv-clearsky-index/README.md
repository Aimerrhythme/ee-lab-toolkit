# 光伏晴空指数计算与晴/多云/阴天划分 (pv-clearsky-index)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Compute the daily clear-sky index from measured irradiance and split days into clear / cloudy / overcast (Python + MATLAB).**

光伏预测常按天气分型分别建模。本工具用 Haurwitz 晴空模型算出理论水平面辐照 GHI_cs，与实测 GHI 相除得到日晴空指数 kt，再按阈值分三类并出图：

- 晴空模型：`GHI_cs = 1098·cosz·exp(-0.057/cosz)`；赤纬用 Cooper 公式，时角 `15°·(hour-12)`（`hour` 为当地**太阳时**，免去时区与时差修正）
- 日指数：`kt = Σ GHI / Σ GHI_cs`，仅统计 `cosz ≥ min_cosz`（默认 0.2）的样本，避开日出日落附近的大比值噪声
- 分类：`kt ≥ 0.75` 晴；`0.35 ≤ kt < 0.75` 多云；其余阴
- 本工具**不联网、不依赖 pvlib**；pvlib（[pvlib-python](https://github.com/pvlib/pvlib-python)）提供更完整的晴空模型，可作进阶对照。示例为合成数据。

## Dependencies

- Python 3.10+：`numpy`、`matplotlib`（测试另需 `pytest`）
- MATLAB R2021b+：仅基础函数，无需工具箱

## Quick start

```bash
# Python
python examples/run_demo.py
pytest tests
```

```matlab
% MATLAB (from the matlab/ folder)
demo_pv_clearsky_index
```

两边打印相同摘要（`days=10 clear=4 cloudy=4 overcast=2` 及逐日 kt 与类别），输出写入 `examples/output/`（已 gitignore）。MATLAB 版未在本仓库 CI 中运行，请课前在机房试跑一次。

## Input format

`date,hour,ghi`：`date` 为 ISO `yyyy-mm-dd`，`hour` 为 0–24 的当地太阳时（可为小数），`ghi` 为非负实测 W/m²。示例 `examples/data/synthetic_ghi.csv` 由 `examples/make_data.py` 生成（10 天逐小时，无随机数）。

## API

`pv_clearsky_index(csv_path, lat=25.0, clear_thr=0.75, overcast_thr=0.35, min_cosz=0.2, output_csv=None, output_png=None, show=False)`

MATLAB：`pv_clearsky_index(csvPath, 'lat', 25, 'clear_thr', 0.75, 'overcast_thr', 0.35, 'min_cosz', 0.2, 'output_csv', '', 'output_png', '', 'show', false)`

| 参数 | 默认 | 含义 |
|---|---|---|
| `lat` | 25.0 | 纬度（度，北纬为正） |
| `clear_thr` | 0.75 | kt 不低于此值为 clear |
| `overcast_thr` | 0.35 | kt 低于此值为 overcast，需 0 < overcast_thr < clear_thr |
| `min_cosz` | 0.2 | 参与统计的最小天顶角余弦 |
| `output_csv` | 无 | `date,ghi_sum,clearsky_sum,kt,sky_type` |
| `output_png` | 无 | 左：逐日曲线按类别着色并叠加首日晴空曲线；右：逐日 kt 柱状图 |
| `show` | false | 是否弹出图窗 |

返回：`dates`、`kt`、`sky_type`、`ghi_sum`、`clearsky_sum`、`counts`、`lat`、`n_days`（Python 为 dict，MATLAB 为 struct）。

## Example output

左图：各日 GHI 曲线，橙=晴、灰=多云、蓝=阴，虚线为晴空曲线；右图：逐日 kt 柱状图。示例中 4 晴、4 多云、2 阴。

## Limitations & teaching disclaimer

Haurwitz 模型忽略气溶胶、水汽与海拔；不做时区/时差换算（输入须为太阳时）；阈值是课堂经验值，不同站点需重新标定；不处理跨日缺测。教学辅助用途，结果不作为发电量评估或工程依据。MIT License。
