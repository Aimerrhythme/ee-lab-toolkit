# 风速—功率分箱曲线与离群点过滤

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Bin a wind-turbine power curve, mark shutdown and curtailment, and compare the scatter with the nameplate curve (Python + MATLAB).**

把风速–功率散点按风速分箱，在每个箱子里算中位数和四分位距，再按规则标出负功率、停机、限电和散点离群点。图上同时给出清洗前、清洗后和理论功率曲线。课堂用的是分箱四分位法。Long、Sang、Wu、Gu 的 [arXiv:2307.08539](https://arxiv.org/abs/2307.08539) 把异常点分成负功率、离散点和堆叠点（停机或限电），并用图像形态学清洗；本工具只用他们的这三类名字，不实现那篇论文里的图像算法。

理论曲线是教材里的三次方铭牌曲线，单位 kW，风速单位 m/s：

```text
P = 0                                      v < v_cut_in 或 v >= v_cut_out
P = P_rated                                v_rated <= v < v_cut_out
P = P_rated * (v^3 - v_cut_in^3)
    / (v_rated^3 - v_cut_in^3)             v_cut_in <= v < v_rated
```

箱子是半开区间 `[v_min + i*bin_width, v_min + (i+1)*bin_width)`。四分位数用 Hyndman–Fan 第 7 型线性插值，和 NumPy `quantile`、MATLAB `quantile` 的默认定义相同。`IQR = Q3 - Q1`。样本数不少于 `min_bin_count` 时，功率落在闭区间 `[Q1 - iqr_k*IQR, Q3 + iqr_k*IQR]` 外面的点记为离群点。正好落在端点上的点保留。

规则按这个顺序，先命中的生效。四分位只在还没被前四条标出的点上计算，所以限电形成的横带不会把箱子的中位数拉低：

1. `negative` — 功率 < 0 且风速 ≥ 切入。切入以下的小负值当成传感器噪声留下。
2. `shutdown` — 功率 ≤ `p_shutdown_kw`，同时理论功率 ≥ `p_shutdown_theory_frac * P_rated`，且风速 < 切出。刚过切入、理论功率本来就很小的点不会被当成停机。
3. `curtailment` — 功率高于停机带，但低于 `curtail_ratio *` 理论功率，且理论功率 ≥ `curtail_theory_frac * P_rated`，风速在 `[切入, 切出)` 内。
4. `outlier` — 理论功率已经是 0 的区域（低于切入，或达到切出）里，功率仍高于停机带。`reason` 写成 `below_cut_in` 或 `above_cut_out`。
5. `outlier` — 落在箱子围栏外。`reason` 写成 `iqr`。

示例是合成的 2 MW 机组，不是某台风电机组的运行记录，也没有学生信息。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`、`matplotlib`（见仓库 `requirements.txt`）。分箱和四分位只用 numpy，不调用 SciPy 或 pandas |
| MATLAB R2021b+ | 基础 MATLAB 即可，不需要工具箱 |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/wind-curve-binning-filter/examples/run_demo.py
```

脚本读取 `examples/data/synthetic_wind_power.csv`，把逐点结果写到 `examples/output/wind_curve_binning_filter_demo.csv`，把分箱表写到同名的 `_bins.csv`，把对比图写到同名的 `.png`（该目录已 gitignore）。

```python
import sys
sys.path.insert(0, "tools/wind-curve-binning-filter/python")
from wind_curve_binning_filter import wind_curve_binning_filter

result = wind_curve_binning_filter(
    "tools/wind-curve-binning-filter/examples/data/synthetic_wind_power.csv",
    p_rated_kw=2000,
    output_png="tools/wind-curve-binning-filter/examples/output/wind_curve_binning_filter_demo.png",
)
result.summary
result.n_keep, result.n_curtailment
```

不读 CSV 时，第一个参数是风速 (m/s)，第二个是功率 (kW)：

```python
result = wind_curve_binning_filter([4.0, 10.0, 14.0], [10.0, 450.0, 2000.0])
result.flag
```

### MATLAB

```matlab
cd('tools/wind-curve-binning-filter/matlab')
demo_wind_curve_binning_filter
```

或从仓库根目录：

```matlab
addpath('tools/wind-curve-binning-filter/matlab')
demo_wind_curve_binning_filter
```

图写到 `tools/wind-curve-binning-filter/examples/output/wind_curve_binning_filter_demo_matlab.png`，两张表写到同目录下带 `_matlab` 的 CSV。要在 IDE 里留住窗口，把 demo 中的 `'show', false` 改成 `'show', true`。

```matlab
result = wind_curve_binning_filter([4.0 10.0 14.0], [10.0 450.0 2000.0]);
result.flag
result.summary
```

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。MATLAB 名值对不区分大小写。`p_shutdown_kw` 留空时等于 `0.02 * p_rated_kw`。

| Name | Default | Description |
|------|---------|-------------|
| `bin_width` | `0.5` | 风速箱宽，m/s，必须 > 0 |
| `v_min` | `0` | 第一只箱子的左端，m/s，必须 ≥ 0。风速小于它会报错 |
| `v_cut_in` | `3` | 切入风速，m/s |
| `v_rated` | `12` | 额定风速，m/s。必须满足 `v_cut_in < v_rated < v_cut_out` |
| `v_cut_out` | `25` | 切出风速，m/s。达到切出后理论功率为 0 |
| `p_rated_kw` | `2000` | 额定功率，kW，必须 > 0 |
| `p_shutdown_kw` | `0.02 * P_rated` | 停机带上沿，kW，必须 ≥ 0。也用来判断切入以下和切出以上的功率是不是还停在 0 附近 |
| `p_shutdown_theory_frac` | `0.10` | 只有理论功率达到额定功率的这个比例，低功率才记为停机。范围 `[0, 1]` |
| `curtail_ratio` | `0.60` | 功率低于 `curtail_ratio *` 理论功率才记为限电。范围 `(0, 1)` |
| `curtail_theory_frac` | `0.30` | 理论功率达到额定功率的这个比例之后才做限电判断。范围 `[0, 1]` |
| `iqr_k` | `1.5` | Tukey 围栏系数，必须 ≥ 0。`1.5` 是常用的内围栏 |
| `min_bin_count` | `5` | 箱子里参与四分位的点数少于此数时，仍报告中位数和四分位距，但不剔除离群点 |
| `wind_col` | 自动 | CSV 风速列。可写 `wind_mps`、`wind`、`v`、`风速` 等 |
| `power_col` | 自动 | CSV 功率列，单位 kW。可写 `power_kw`、`power`、`p`、`功率` 等 |
| `output_csv` | 不写 | 逐点表。父目录不存在时会创建 |
| `output_bins_csv` | 不写 | 分箱表 |
| `output_png` | 不保存 | 清洗前后对比图。Python demo 使用无界面后端 |
| `show` | `false` | 为真时留下图窗。Python 只接受 `True`/`False`；MATLAB 也接受 `0`/`1` |

CSV 可用逗号或分号。空的风速或功率格子会丢掉，并计入 `n_missing`；两格都空的行直接跳过。非数字会报错。`label` 这样的额外列会被忽略。建议列：

| Column | Required | Meaning |
|--------|----------|---------|
| `wind_mps` | 是 | 风速，m/s。也认 `wind_speed`、`wind`、`v`、`风速` |
| `power_kw` | 是 | 有功功率，kW。也认 `power`、`p`、`功率`、`有功` |
| `label` | 否 | 仅合成示例使用，工具不读。取值 `normal`、`negative`、`shutdown`、`curtailment`、`outlier` |

`examples/data/synthetic_wind_power.csv` 由 `examples/make_data.py` 生成，共 676 行。0 到 26 m/s 每 0.5 m/s 一只箱子，每只箱子 4 个风速，每个风速三个功率：理论值加 `-40`、`0`、`+40` kW，小于 0 的裁到 0。另外种入 5 个负功率、10 个停机、26 个 450 kW 的限电横带，以及 11 个离群点（曲线上方 +700 kW、额定区 1500 kW、切入以下和切出以上仍在发电）。重新生成：

```bash
python tools/wind-curve-binning-filter/examples/make_data.py
```

## API

两侧返回同一组字段。`result.bins` 从风速最小的一只箱子排到样本所在的最后一只，中间空箱子保留，统计量是 NaN。MATLAB 的序列是列向量，`flag` 和 `reason` 是元胞字符向量；Python 里是一维数组和字符串列表。

| Field | Meaning |
|-------|---------|
| `wind_mps`, `power_kw`, `theory_kw` | 输入风速、功率，以及每个点上的理论功率 |
| `bin_index` | 从 0 开始的箱号 |
| `flag` | `normal`、`negative`、`shutdown`、`curtailment`、`outlier` |
| `reason` | 正常点是空串；离群点还会写成 `iqr`、`below_cut_in`、`above_cut_out` |
| `keep` | 只有 `normal` 为真 |
| `bins` | 下表的每一行 |
| `n_rows`, `n_keep`, `n_negative`, `n_shutdown`, `n_curtailment`, `n_outlier` | 行数和各类点数 |
| `n_missing` | CSV 里丢掉的残缺行。数组输入时为 0 |
| `bin_width`, `v_min`, `v_cut_in`, `v_rated`, `v_cut_out`, `p_rated_kw`, `p_shutdown_kw` | 实际使用的参数 |
| `summary` | 与 `format_summary` 相同的一行字 |
| `output_csv`, `output_bins_csv`, `output_png` | 写出的路径。未写时 Python 为 `None`，MATLAB 为 `''` |
| `fig` | `show` 为真时的图窗；否则为空 |

每只箱子的字段：

| Field | Meaning |
|-------|---------|
| `bin_index`, `v_left`, `v_right`, `v_center` | 箱号和两端、中心风速 |
| `n_raw` | 落在这只箱子里的全部点数 |
| `n_quartile` | 参与四分位的点数（规则 1–4 没标出的点，含随后被围栏剔除的点） |
| `n_clean` | 最后留下的正常点数 |
| `median_kw`, `q1_kw`, `q3_kw`, `iqr_kw` | 四分位样本的中位数、Q1、Q3、IQR |
| `lower_kw`, `upper_kw`, `fence_applied` | 围栏两端，以及是否真的用它剔除了点 |
| `median_clean_kw` | 剔除之后的中位数，右图上的红色横段用这个值 |
| `theory_kw` | 箱中心上的理论功率 |

逐点 CSV 的列是 `wind_mps,power_kw,theory_kw,bin_index,v_left,flag,reason,keep`。分箱 CSV 的列与上表一致，`fence_applied` 和 `keep` 写成 `1`/`0`，NaN 写成 `nan`。

图左是全部散点，按五类上色，黑线是理论曲线。图右只留正常点，黄色带是 Q1–Q3，同色虚线是围栏，红色横段是清洗后的分箱中位数，黑线仍是理论曲线。坐标和标题是英文。

## Example output

默认参数，`p_rated_kw = 2000`。10 m/s 的理论功率是 `2000 * (1000 - 27) / (1728 - 27) = 1144.03` kW。

```text
wind-curve-binning-filter: rows=676 keep=624 negative=5 shutdown=10 curtailment=26 outlier=11 bin_width=0.5 p_rated_kw=2000
bin v=[12,12.5) n_raw=14 n_clean=12 median_clean_kw=2000.0000 q1_kw=1960.0000 q3_kw=2040.0000 theory_kw=2000.0000
```

可以顺着这张图讲四件事：

- **正常带贴着三次方曲线。** 每个风速有理论值以及上下各 40 kW。额定区理论功率是 2000 kW，所以 `[12, 12.5)` 的正常点是 1960、2000、2040。清洗后中位数仍是 2000。
- **四分位不会被单个离群点带动。** 这只箱子里还有一个 1500 kW 的点。它进入四分位样本，但 Q1 仍是 1960、Q3 仍是 2040，IQR 是 80，围栏是 `[1840, 2160]`。1500 低于 1840，记为 `iqr` 后剔除。限电的 450 kW 在四分位之前就被拿走了。
- **停机看的是“这里本该有功率”。** 4 m/s 的理论功率大约 43.5 kW，不到额定的 10%（200 kW），所以功率为 0 仍是正常点。7 m/s 的理论功率大约 407 kW，功率为 0 才记为停机。
- **限电是理论曲线下方的横带。** 从 9.25 m/s 到 21.75 m/s，每 0.5 m/s 有一个 450 kW 的点。那里的理论功率已经高于 600 kW，而 450 又低于理论值的 60%，所以记为 `curtailment`。清洗后的右图里这条横带消失，红色中位数回到铭牌曲线上。

手算一只箱子可以核对两边是否一致。风速和功率：

```text
(10.10, 1100), (10.20, 1120), (10.30, 1160), (10.40, 1180), (10.45, 1200)
(10.15, 500), (10.25, 0), (10.35, 2000), (8.0, -30)
```

前五个是正常点。500 kW 是限电，0 是停机，-30 kW 是负功率。2000 kW 和前五个一起做四分位，排序后是 `1100, 1120, 1160, 1180, 1200, 2000`。Q1 = 1130，中位数 = 1170，Q3 = 1195，IQR = 65，围栏 = `[1032.5, 1292.5]`。2000 在围栏外。剔掉之后的中位数是 1160。

## Limitations

- 这不是 IEC 61400-12-1 的功率曲线测试。标准里用的是分箱平均，并且有自己的剔除和扇区规则；这里按课堂要求用中位数和四分位距
- 理论曲线没有空气密度、推力系数或厂家保证曲线，只是切入到额定之间的三次方，到额定后被铭牌封顶
- 围栏是水平的。一只箱子里如果正常点本身沿着陡峭的三次方拉开，而样本又很少，两端的正常点可能被 1.5 倍 IQR 碰到。示例把同一风速上的功率做成 ±40 kW 的窄带，就是为了让正常点留在围栏里
- 限电和停机的阈值是相对这条理论曲线设定的。曲线参数和机组对不上时，横带会被误判
- 少于 `min_bin_count` 的箱子不做围栏剔除
- 示例是合成散点，不能当作某台风电场的考核或并网依据

## FAQ

**为什么限电要在算四分位之前拿走？**  
限电点会在一只箱子里堆成同一功率。如果它们占了多数，中位数和 Q1 都会掉到横带上，围栏就围住了限电、反而把正常曲线当成离群点。先用理论曲线把横带标出来，四分位才是在正常带上算的。

**4 m/s、功率为 0，为什么不是停机？**  
停机带是“功率已经低到 40 kW，而这只风速的理论功率至少有 200 kW”。刚过 3 m/s 时理论功率自己还不到 40 kW，0 是正常的低出力。

**围栏端点上的点留不留？**  
留。比较是严格的 `<` 下端和 `>` 上端。五个点 `10, 20, 30, 40, 70` 的 Q1 = 20、Q3 = 40、上端 = 70，70 仍是 `normal`；70.1 才是 `outlier`。

**箱子点数不够怎么办？**  
仍给出中位数和 Q1、Q3，但 `fence_applied` 为假，一个点都不因为围栏被删。默认门槛是 5 个点。

**CSV 里的功率是 W 或 MW 怎么办？**  
工具不换算单位。示例和 `p_rated_kw` 都是 kW。

**需要工具箱吗？**  
不需要。Python 用 numpy 排序和 matplotlib 作图；MATLAB 用 `sort`、`floor` 和基础绘图。两边的箱号、旗标、四分位和摘要文本一致。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助对照风速分箱、四分位围栏和限电/停机点的标法，结果不作为功率曲线考核、电量结算或成绩评定依据。请勿把学生姓名、学号、成绩或未公开的风电场运行数据放进示例或提交到仓库。本工具随仓库以 MIT 许可证发布，见根目录 [LICENSE](../../LICENSE)。
