# 光伏日出力特征提取

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Daily PV features: peak power, ramp rate, energy, and a variability index (Python + MATLAB).**

从一条光伏出力时间序列里，按自然日提取峰值功率和峰值时刻、日发电量与容量因子、开机窗口、步长爬坡和窗口爬坡，以及波动指数。默认例子是三天合成曲线：晴天正弦包络、两段云、以及中午的 5 分钟闪变。功率单位是 kW。数字不是某座电站的运行记录，也没有学生信息。

时间是本地钟面时间，不换时区。一天里的时刻用从午夜算起的分钟。

```text
E_kWh = sum_i 0.5 * (P_i + P_{i+1}) * (t_{i+1} - t_i) / 60
CF    = E_kWh / (P_rated * 24)                 给了铭牌才有定义
ramp_i = (P_j - P_i) / (t_j - t_i)             kW/min
         t_j 是不早于 t_i + ramp_minutes 的第一个采样
VI    = sum_i |P_{i+1} - P_i| / (2 * P_peak)
```

只上升一次、到达一个峰、再回到同一个最低点的曲线，VI = 1。云造成的额外升降会把 VI 抬到 1 以上。`P_peak` 取第一个达到最大值的采样。步长爬坡用相邻两点；窗口爬坡用 `ramp_minutes`。

采样已经等间隔时，按原序列计算。间隔不匀，或者显式给了 `step_minutes`，就线性重采样。为了留下最后一个点，最后一格可以比步长更短。

开机阈值 `p_on_kw` 不给时：有铭牌就用铭牌的 2%，否则用当天峰值的 5%（峰值不大于 0 时用 0）。`hours_window` 是第一个不低于阈值的点到最后一个这样的点。`hours_above` 把“开机”看成 0/1 序列，再用同一套梯形积分，所以跨过阈值的那一格只算一半。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`、`matplotlib`（见仓库 `requirements.txt`）。积分和爬坡只用 numpy，不调用 SciPy 或 pandas |
| MATLAB R2021b+ | 基础 MATLAB 即可，不需要工具箱。同一套 `.m` 也能在 GNU Octave 里算完并出图 |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/pv-daily-features/examples/run_demo.py
```

脚本读取 `examples/data/synthetic_pv_kw.csv`，把特征表写到 `examples/output/pv_daily_features_demo.csv`，把两张子图写到同名的 `.png`（该目录已 gitignore）。

在自己的脚本里调用：

```python
import sys
sys.path.insert(0, "tools/pv-daily-features/python")
from pv_daily_features import format_table, pv_daily_features

result = pv_daily_features(
    "tools/pv-daily-features/examples/data/synthetic_pv_kw.csv",
    p_rated_kw=100,
    ramp_minutes=10,
    output_png="tools/pv-daily-features/examples/output/pv_daily_features_demo.png",
    output_csv="tools/pv-daily-features/examples/output/pv_daily_features_demo.csv",
)
day = result.days[0]
day.p_peak_kw, day.t_peak, day.variability_index
print(format_table(result))
```

不读 CSV 时，第一个参数是时刻，第二个是功率（kW）。时刻可以是 `YYYY-MM-DD HH:MM:SS` 字符串，也可以是从 `day` 当天午夜起算的分钟：

```python
result = pv_daily_features([0, 10, 20, 30, 40], [0, 10, 10, 0, 0], p_rated_kw=10, day="2024-06-21")
result.days[0].energy_kwh, result.days[0].variability_index
```

### MATLAB

```matlab
cd('tools/pv-daily-features/matlab')
demo_pv_daily_features
```

或从仓库根目录：

```matlab
addpath('tools/pv-daily-features/matlab')
demo_pv_daily_features
```

图写到 `tools/pv-daily-features/examples/output/pv_daily_features_demo_matlab.png`，表写到同名的 `.csv`。要在 IDE 里留住窗口，把 demo 中的 `'show', false` 改成 `'show', true`。

单日数组。`day` 只在时刻是“从午夜起的分钟”时使用：

```matlab
result = pv_daily_features([0 10 20 30 40], [0 10 10 0 0], ...
    'p_rated_kw', 10, 'day', '2024-06-21');
result.days(1).energy_kwh
result.days(1).variability_index
```

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。MATLAB 名值对不区分大小写。第一个参数是 CSV 路径，或与 `power` 一起传入的时刻。

| Name | Default | Description |
|------|---------|-------------|
| `time_col` | 自动 | CSV 的时间列。可写 `timestamp`、`time`、`时间` 等，见下方别名 |
| `power_col` | 自动 | CSV 的功率列，单位 kW。可写 `power_kw`、`p`、`功率` 等 |
| `p_rated_kw` | 空 | 铭牌功率，kW。用来算容量因子，并在未给 `p_on_kw` 时把开机阈值设为铭牌的 2% |
| `p_on_kw` | 见上 | 开机阈值，kW，必须 ≥ 0。空着则用铭牌的 2%，没有铭牌就用当天峰值的 5% |
| `ramp_minutes` | `10` | 窗口爬坡的分钟数，必须 > 0。短于整段记录时，窗口爬坡为 NaN，步长爬坡仍给出 |
| `step_minutes` | 自动 | 重采样步长，分钟。空着时，等间隔序列保持原样；不等间隔则用间隔的中位数 |
| `day` | `1970-01-01` | 数值分钟所属的起始日期，`YYYY-MM-DD`。只用于分钟向量，不能和 CSV 或时间戳同时给 |
| `csv_path` | 空 | CSV 路径。和位置参数不要同时给 |
| `output_csv` | 不写 | 每日特征表。父目录不存在时会创建 |
| `output_png` | 不保存 | 功率与窗口爬坡图。Python demo 使用无界面后端 |
| `show` | `false` | 为真时留下图窗 |

时间戳接受这几种零填充写法：`YYYY-MM-DD HH:MM:SS`、`YYYY-MM-DD HH:MM`、中间的空格可以换成 `T`，日期分隔符可以是 `-` 或 `/`。

CSV 可用逗号或分号。空的功率格子和 `nan` 会丢掉，并计入 `n_missing`；同一时刻的重复行保留文件中的第一行。建议列：

| Column | Required | Meaning |
|--------|----------|---------|
| `timestamp` | 是 | 本地时间。也认 `datetime`、`time`、`时间`、`时刻`、`日期` |
| `power_kw` | 是 | 功率，kW。也认 `p_kw`、`pv_kw`、`power`、`p`、`功率`、`出力`、`有功` |

`examples/data/synthetic_pv_kw.csv` 是三天、每 5 分钟一个点的课堂数据，从当天 00:00 到 23:55。

晴天（2024-06-21）在 06:00 到 18:00 之间是

```text
P = 80 * sin(pi * (minute - 360) / 720)    单位 kW，minute 从午夜算起
```

两端以外为 0。云天（2024-06-22）把这条包络乘上一段折线透过率，折点是（分钟, 透过率）：`(570, 1)`、`(600, 0.25)`、`(615, 0.25)`、`(645, 1)`、`(780, 1)`、`(800, 0.15)`、`(840, 0.15)`、`(880, 1)`。闪变日（2024-06-23）在 11:00 到 13:00 之间，把 `:05`、`:15`、`:25`、`:35`、`:45`、`:55` 这些点乘 0.4，其余点仍是晴天包络。

## API

两侧返回同一组字段。`result.days` 是每一天一条。MATLAB 里的曲线是列向量，Python 里是一维数组。没有定义的标量是 NaN，没有定义的钟点字符串是 `nan`。`capacity_factor` 是分数 `E / (P_rated * 24)`，不是百分数。

| Field | Meaning |
|-------|---------|
| `date` | `YYYY-MM-DD` |
| `n_samples`, `step_minutes`, `resampled` | 用于计算的点数、名义步长（分钟）、是否重采样过。单点日的步长是 NaN |
| `p_rated_kw`, `p_on_kw` | 铭牌和这一天实际使用的开机阈值 |
| `p_peak_kw`, `t_peak`, `t_peak_min` | 峰值功率、峰值钟点、从午夜起的分钟。并列峰值取第一个 |
| `energy_kwh`, `hours_span`, `p_mean_kw` | 梯形积分电量、首尾时刻跨度（小时）、电量除以跨度 |
| `capacity_factor` | 电量除以铭牌乘 24 h。没给铭牌时为 NaN |
| `t_on`, `t_off`, `hours_window` | 开机窗口的两端和长度。整天都低于阈值时，`hours_window` 为 NaN，摘要写 `on=undefined` |
| `hours_above` | 开机指示量的梯形积分，小时 |
| `ramp_minutes` | 请求的窗口长度 |
| `ramp_up_kw_per_min`, `ramp_down_kw_per_min` | 窗口爬坡的最大升、最大降（降是负数） |
| `ramp_up_span_min`, `ramp_down_span_min` | 这两个窗口的实际分钟数。粗采样时可以长于 `ramp_minutes` |
| `t_ramp_up`, `t_ramp_down` | 窗口起点的钟点 |
| `ramp_step_up_kw_per_min`, `ramp_step_down_kw_per_min` | 相邻采样爬坡的最大升和最大降 |
| `t_step_up`, `t_step_down` | 步长爬坡起点的钟点 |
| `variability_index` | 上面的 VI。峰值不大于 0，或只有一个点时为 NaN |
| `minute`, `hour`, `power_kw` | 计算用的曲线 |
| `ramp_kw_per_min` | 从该点出发的窗口爬坡。后面不够一个窗口的点是 NaN |
| `summary` | 与 `format_table` 相同的文本。只在结果上，不在每一天上 |
| `n_rows`, `n_missing`, `n_duplicates` | 清洗后的点数、丢掉的空功率、丢掉的重复时刻 |
| `output_csv`, `output_png` | 写出的路径。未写时 Python 为 `None`，MATLAB 为 `''` |
| `fig` | `show` 为真时的图窗；否则为空 |

Python 另有 `format_table(result)`，demo 用它打表。MATLAB 的 `result.summary` 是同一段文字。

图上的圆点是峰值。窗口爬坡的上三角是最大升，下三角是最大降。给了铭牌时，上图有一条虚线标出铭牌。

## Example output

`p_rated_kw = 100`，`ramp_minutes = 10`。三天的峰值都是 80 kW，都在 12:00。晴天 VI 印出来是 1。

```text
pv-daily-features: date=2024-06-21 Ppeak=80.0000 t_peak=12:00:00 E=611.1307 VI=1.000000 ramp_up=0.3490 ramp_down=-0.3490
pv-daily-features: date=2024-06-22 Ppeak=80.0000 t_peak=12:00:00 E=500.8205 VI=2.212988 ramp_up=1.9834 ramp_down=-3.3403
pv-daily-features: date=2024-06-23 Ppeak=80.0000 t_peak=12:00:00 E=563.6734 VI=8.081702 ramp_up=4.5721 ramp_down=-4.5721
rows=864  missing=0  duplicates=0  days=3  ramp_min=10

date=2024-06-21  N=288  step=5  resampled=0
Ppeak=80  t_peak=12:00:00  E=611.131  mean=25.5525  span=23.9167  CF=0.254638  Prated=100  Pon=2
on=06:10:00-17:50:00  window=11.6667  above=11.75
ramp_min=10  up=0.348955  down=-0.348955  up_span=10  down_span=10  t_up=06:00:00  t_down=17:50:00
step_up=0.349038  t_step_up=06:00:00  step_down=-0.349038  t_step_down=17:55:00  VI=1

date=2024-06-22  N=288  step=5  resampled=0
Ppeak=80  t_peak=12:00:00  E=500.82  mean=20.9402  span=23.9167  CF=0.208675  Prated=100  Pon=2
on=06:10:00-17:50:00  window=11.6667  above=11.75
ramp_min=10  up=1.98339  down=-3.34031  up_span=10  down_span=10  t_up=10:35:00  t_down=13:00:00
step_up=1.99519  t_step_up=10:40:00  step_down=-3.35819  t_step_down=13:00:00  VI=2.21299

date=2024-06-23  N=288  step=5  resampled=0
Ppeak=80  t_peak=12:00:00  E=563.673  mean=23.5682  span=23.9167  CF=0.234864  Prated=100  Pon=2
on=06:10:00-17:50:00  window=11.6667  above=11.75
ramp_min=10  up=4.5721  down=-4.5721  up_span=10  down_span=10  t_up=12:55:00  t_down=10:55:00
step_up=9.60152  t_step_up=11:55:00  step_down=-9.60152  t_step_down=12:00:00  VI=8.0817
```

可以顺着这张表讲六件事：

- **峰值一样，日子并不一样。** 三天的峰值都是 80 kW、都在 12:00，因为云和闪变都没盖住正午。容量因子从晴天的 0.255 降到云天的 0.209，闪变日停在 0.235。
- **晴天 VI = 1。** 曲线从 0 升到 80 kW 再回到 0，绝对值增量之和正好是峰值的两倍。连续的正弦积分是 `1920 / pi ≈ 611.15 kWh`；5 分钟梯形积分是 611.131 kWh。
- **开机窗口比日出日落短一截。** 阈值是铭牌的 2%，也就是 2 kW。06:05 只有约 1.75 kW，06:10 约 3.49 kW，所以 `t_on` 是 06:10，对称地 `t_off` 是 17:50。`hours_above` 比这个窗口多 5 分钟（11.75 对 11.6667），因为进出阈值的两格各算了一半。
- **2 kW 阈值看不见这些云。** 云天最深的时候仍有十几千瓦，三天的开机窗口完全相同。云记在 VI 和爬坡上，不记在开机小时上。
- **云天的 10 分钟降爬坡大约是晴天的 10 倍。** 晴天窗口爬坡是日出后第一格 `+0.349 kW/min` 和日落前 `−0.349 kW/min`。云天在 13:00 开始掉进下午的深云，10 分钟降爬坡是 `−3.340 kW/min`；10:35 的回升是 `+1.983 kW/min`。相对 100 kW 铭牌，大约是每分钟 3.34% 和 1.98%。
- **窗口长度决定你看见哪一种云。** 闪变日的 5 分钟步长爬坡在正午附近是 `±9.602 kW/min`，10 分钟窗口只在闪变区间的边缘（10:55 和 12:55）看到 `±4.572 kW/min`，区间内部的 10 分钟窗口落在同一相位上，闪变互相抵消。VI 从晴天的 1 升到云天的 2.21，再升到闪变日的 8.08。

上图是功率对一天中的小时。晴天包络画在最下面，云天和闪变日在重合的地方把它盖住；圆点是三天共用的正午峰值，虚线是 100 kW 铭牌。下图是 10 分钟窗口爬坡，三角标出每一天的最大升和最大降。坐标和标题是英文。

## Limitations

- 这不是晴空物理模型。没有辐照、温度、倾角、组件衰减，也没有逆变器限幅
- 电量只积分文件里实际给出的采样。容量因子仍除以 24 小时，所以缺了高出力时段的文件会把容量因子算低
- 窗口爬坡取“不早于 `t + ramp_minutes` 的第一个点”。步长比窗口还粗时，实际跨度会更长；整段记录短于窗口时，窗口爬坡是 NaN
- 缺测行是直接丢掉，再按剩下的时刻决定要不要重采样，不会替空格子发明一个时间戳
- 重采样是线性插值，云的尖峰如果落在两个点之间会被抹平
- 允许负功率（夜间站用电）。它会减少电量；峰值不大于 0 时 VI 无定义
- 示例是合成曲线，不能当作某座光伏电站的考核或并网依据

## FAQ

**VI 为什么晴天正好是 1？**  
从最低点升到峰值再回到同一个最低点，上升和下降的绝对值之和都是峰值，除以 `2 * P_peak` 就是 1。中间如果平一段，差分为 0，结果不变。云让功率多升降几次，分子变大，VI 就大于 1。

**三天峰值一样，特征还有用吗？**  
有用的是电量、容量因子、爬坡和 VI。只报最大功率会把这三天看成同一天。

**步长爬坡和 10 分钟爬坡为什么差这么多？**  
闪变的周期是 10 分钟里的一上一下。5 分钟步长正好落在半个周期上，10 分钟窗口的两端往往是同一相位。边缘上的 10 分钟窗口会跨进或跨出闪变区，所以下图仍有尖峰，只是比步长爬坡小。

**`hours_above` 为什么比开机窗口长？**  
窗口是两个采样钟点的差。`hours_above` 把刚跨过 2 kW 的那一格算半格。5 分钟数据、前后各半格，就是多出来的 5 分钟。

**阈值为什么没把云记成停机？**  
2 kW 是铭牌的 2%，用来近似“逆变器已经出来了”。示例里的云还远高于这个数。要把云掉到接近零才算停机，需要另给一个更高的 `p_on_kw`，或者直接看爬坡和 VI。

**CSV 里是 W 怎么办？**  
工具不换算单位。先除以 1000 再当作 kW，否则峰值和电量都会大一千倍。

**需要工具箱吗？**  
不需要。Python 用 numpy 的梯形和线性插值；MATLAB 用 `interp1`。两边的分日、重采样、爬坡和摘要文本一致。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助对照光伏日曲线的峰值、爬坡、电量和波动指数，结果不作为发电量评估、并网考核或成绩评定依据。请勿把学生姓名、学号、成绩或未公开的电站运行数据放进示例或提交到仓库。本工具随仓库以 MIT 许可证发布，见根目录 [LICENSE](../../LICENSE)。
