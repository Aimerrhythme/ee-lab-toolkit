# 典型日负荷曲线聚类

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**k-means on peak-normalized daily load profiles (Python + MATLAB).**

把多日负荷切成一条条日曲线，按峰值归一化后做 k-means，得到每一天的簇标签和各簇的典型日形状。默认例子是 14 天合成负荷：工作日白天较平的商业曲线、傍晚尖峰的居民曲线，以及峰值更低、下午更宽的周末曲线。功率单位是 kW。数字是课堂公式加一点固定噪声，不是某条馈线的运行记录，也没有学生信息。

聚类看的是形状，不是千瓦水平。默认把每一天除以当天的峰值：

```text
x_d,t = P_d,t / max_t P_d,t          peak，默认
x_d,t = P_d,t / mean_t P_d,t         mean
x_d,t = P_d,t                        none，保留 kW
SSE   = sum_d || x_d - c_label(d) ||^2
```

`c` 是归一化空间里的簇中心，也就是典型日形状。轮廓系数是各天轮廓值的平均；某一天单独成簇时该天记 0，`k < 2` 或出现空簇时整个系数为 NaN。

中心用 k-means++ 选出，再用 Lloyd 迭代更新到标签不再变化，或达到 `max_iter`。`n_init` 次重启保留簇内平方和最小的一次；平方和相同则留下更早的那次。第 `i` 次重启（从 0 计）的随机数种子是 `(seed + i) mod 2^32`。随机数是两边共用的 32 位 LCG，不是 NumPy 的 Generator，也不是 MATLAB 的 `rng`，所以同一个 `seed` 在 Python 和 MATLAB 里得到同一套标签。

收敛之后按质心峰值所在的小时把簇重编号为 1…k，峰值越早编号越小。峰值时刻并列时，保留重编号前较小的那个编号。因此标签是“第几种形状”，不是初始化时抽到的顺序。距离用欧氏距离；平方距离按时间列从左到右累加，两边顺序一致。并列时归到编号更小的簇。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`、`matplotlib`（见仓库 `requirements.txt`）。k-means 只用 numpy 手写，不调用 scikit-learn |
| MATLAB R2021b+ | 基础 MATLAB 即可，不需要 Statistics Toolbox。同一套 `.m` 也能在 GNU Octave 里算完并出图 |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/load-kmeans/examples/run_demo.py
```

脚本读取 `examples/data/synthetic_load_kw.csv`，把每日标签写到 `examples/output/load_kmeans_demo.csv`，把两张子图写到同名的 `.png`（该目录已 gitignore）。

在自己的脚本里调用：

```python
import sys
sys.path.insert(0, "tools/load-kmeans/python")
from load_kmeans import format_table, load_kmeans

result = load_kmeans(
    "tools/load-kmeans/examples/data/synthetic_load_kw.csv",
    k=3,
    seed=0,
    normalize="peak",
    output_png="tools/load-kmeans/examples/output/load_kmeans_demo.png",
    output_csv="tools/load-kmeans/examples/output/load_kmeans_demo.csv",
)
result.labels, result.centroids.shape, result.sse, result.silhouette
print(format_table(result))
```

不读 CSV 时，可以传入“每天一行”的矩阵，也可以传入时刻和功率。矩阵的列默认均匀铺满 24 小时，第一列在 00:00。单独的一行是一天。时刻可以是 `YYYY-MM-DD HH:MM:SS` 字符串，也可以是从 `day` 当天午夜起算、落在 `[0, 1440)` 里的分钟：

```python
profiles = [
    [20, 100, 100, 20],
    [18, 30, 40, 90],
]
result = load_kmeans(profiles, k=2, normalize="peak", seed=0)
result = load_kmeans([0, 60, 120], [10, 40, 20], k=1, day="2024-03-04")
```

### MATLAB

```matlab
cd('tools/load-kmeans/matlab')
demo_load_kmeans
```

或从仓库根目录：

```matlab
addpath('tools/load-kmeans/matlab')
demo_load_kmeans
```

图写到 `tools/load-kmeans/examples/output/load_kmeans_demo_matlab.png`，表写到同名的 `.csv`。要在 IDE 里留住窗口，把 demo 中的 `'show', false` 改成 `'show', true`。

矩阵按行是一天。单独的数值向量是一天；再跟一个同样长度的功率向量，则第一个是时刻：

```matlab
result = load_kmeans([0 0; 2 0; 4 0], 'k', 1, 'normalize', 'none');
result = load_kmeans([0 60 120], [10 40 20], 'k', 1, 'day', '2024-03-04');
result.sse
```

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。MATLAB 名值对不区分大小写。第一个参数是 CSV 路径、日曲线矩阵，或与 `power` 一起传入的时刻。

| Name | Default | Description |
|------|---------|-------------|
| `k` | `3` | 簇数，正整数，不能超过天数 |
| `seed` | `0` | 非负整数。第 `i` 次重启使用 `(seed + i) mod 2^32` |
| `normalize` | `peak` | `peak`、`mean` 或 `none` |
| `n_init` | `10` | 重启次数，保留 SSE 最小的一次 |
| `max_iter` | `100` | 每次重启的 Lloyd 迭代上限 |
| `step_minutes` | 自动 | 各天时钟网格不一致时的重采样步长，分钟，必须整除 24 小时。只用于时间序列 |
| `time_col` | 自动 | CSV 的时间列。可写 `timestamp`、`time`、`时间` 等 |
| `power_col` | 自动 | CSV 的功率列，单位 kW。可写 `power_kw`、`load`、`功率` 等 |
| `dates` | `day-01` … | 矩阵每一行的日期标签。只用于矩阵，长度必须等于天数 |
| `day` | `1970-01-01` | 数值分钟所属的日期，`YYYY-MM-DD`。分钟必须在 `[0, 1440)` |
| `csv_path` | 空 | CSV 路径。和位置参数不要同时给 |
| `output_csv` | 不写 | 每日标签表：`date,label,peak_kw,day_sse`。父目录不存在时会创建 |
| `output_png` | 不保存 | 日曲线与典型日质心图。Python demo 使用无界面后端 |
| `show` | `false` | 为真时留下图窗 |

时间戳接受这几种零填充写法：`YYYY-MM-DD HH:MM:SS`、`YYYY-MM-DD HH:MM`，中间的空格可以换成 `T`，日期分隔符可以是 `-` 或 `/`。

CSV 可用逗号或分号。空的功率格子和 `nan` 会丢掉，并计入 `n_missing`；同一时刻的重复行保留文件中的第一行。各天已经落在同一条时钟网格上时，就用这条网格，不再重采样。网格不一致时，线性插值到从 00:00 开始、步长整除 24 小时的全日网格；某一天盖不住网格两端会报错。建议列：

| Column | Required | Meaning |
|--------|----------|---------|
| `timestamp` | 是 | 本地时间。也认 `datetime`、`time`、`时间`、`时刻`、`日期` |
| `power_kw` | 是 | 功率，kW。也认 `load_kw`、`p_kw`、`power`、`p`、`负荷`、`功率`、`有功` |

`examples/data/synthetic_load_kw.csv` 是 2024-03-04 到 2024-03-17、每小时一个点的课堂数据，从当天 00:00 到 23:00。3 月 4 日是周一。

商业日（3 月 4–8 日，周一到周五）在小时 `h = 0…23` 上是

```text
h = 8…17 时 base = 92，h = 7 或 18 时 base = 55
h = 6 或 19 时 base = 30，其余 base = 16
P = base + 8 * exp(-((h - 12) / 1.2)^2)     单位 kW，正午略高
```

居民日（3 月 11–15 日）是

```text
P = 16 + 22 * exp(-((h - 7) / 1.4)^2) + 70 * exp(-((h - 19) / 1.5)^2)
```

周末（3 月 9–10 日和 3 月 16–17 日）峰值更低，峰在下午：

```text
P = 14 + 34 * exp(-((h - 15) / 3.2)^2)
```

每一天再加 ±3.5 kW 以内的固定噪声。记 `day_index` 从 3 月 4 日的 0 开始：

```text
state = (1664525 * ((day_index + 1) * 1000 + h) + 1013904223) mod 2^32
noise = (2 * state / 2^32 - 1) * 3.5
```

## API

两侧返回同一组字段。`labels` 从 1 计到 `k`。`profiles` 和 `centroids` 在归一化之后的空间里，k-means 用的就是它们。`power_kw` 是对齐后的原始 kW；`centroids_kw` 是簇内原始曲线的平均，不是把归一化质心乘回峰值。MATLAB 里的曲线按行排列，Python 里是二维数组。没有成员的簇，其 `centroids_kw` 和 `mean_peak_kw` 为 NaN。

| Field | Meaning |
|-------|---------|
| `labels` | 每一天的簇编号，1…k |
| `centroids`, `profiles` | 归一化空间里的质心和日曲线。质心按峰值小时从早到晚排列 |
| `centroids_kw`, `power_kw`, `peak_kw` | 簇内原始曲线的平均、对齐后的各日功率、各日峰值（kW） |
| `dates`, `hour`, `minute` | 日期标签、从午夜起的小时和分钟 |
| `k`, `seed`, `n_init`, `max_iter`, `normalize` | 请求的参数。`normalize` 是小写的 `peak`、`mean` 或 `none` |
| `sse`, `day_sse`, `silhouette` | 总簇内平方和、每一天到质心的平方距离、平均轮廓系数 |
| `cluster_sizes`, `centroid_peak_hour`, `mean_peak_kw` | 簇大小、质心峰值小时、簇内日峰值的平均 |
| `n_iter`, `attempt` | 获胜那次重启的 Lloyd 迭代次数，以及它的序号（从 0 计） |
| `step_minutes`, `resampled` | 网格步长（分钟），以及是否做了全日重采样 |
| `summary` | 与 `format_table` 相同的文本 |
| `n_rows`, `n_missing`, `n_duplicates`, `n_days` | 清洗后留下的功率点数、丢掉的空功率、丢掉的重复时刻、天数。矩阵输入时 `n_rows` 是天数乘以时刻数 |
| `output_csv`, `output_png` | 写出的路径。未写时 Python 为 `None`，MATLAB 为 `''` |
| `fig` | `show` 为真时的图窗；否则为空 |

Python 另有 `format_table(result)`，demo 用它打表。MATLAB 的 `result.summary` 是同一段文字。

上图是各日归一化曲线，细线是每一天，粗线是质心。下图只画质心。图例写 `cluster 1 (n=5)` 这种形式，放在左上角。坐标和标题是英文。`peak` 时纵轴是 “Power / daily peak”，`mean` 时是 “Power / daily mean”，`none` 时是 “Power (kW)”。

## Example output

`k = 3`，`seed = 0`，`normalize = peak`。14 天分成 5 + 4 + 5。簇 1 的质心在 12:00 到达峰值，簇 2 在 15:00，簇 3 在 19:00。

```text
load-kmeans: date=2024-03-04 label=1 peak_kw=100.8979 day_sse=0.002203
load-kmeans: date=2024-03-05 label=1 peak_kw=96.6108 day_sse=0.006593
load-kmeans: date=2024-03-06 label=1 peak_kw=99.3236 day_sse=0.000001
load-kmeans: date=2024-03-07 label=1 peak_kw=102.0365 day_sse=0.006266
load-kmeans: date=2024-03-08 label=1 peak_kw=97.7494 day_sse=0.002122
load-kmeans: date=2024-03-09 label=2 peak_kw=48.4704 day_sse=0.000296
load-kmeans: date=2024-03-10 label=2 peak_kw=51.1832 day_sse=0.018126
load-kmeans: date=2024-03-11 label=3 peak_kw=84.9070 day_sse=0.002462
load-kmeans: date=2024-03-12 label=3 peak_kw=87.6198 day_sse=0.003869
load-kmeans: date=2024-03-13 label=3 peak_kw=83.3327 day_sse=0.013887
load-kmeans: date=2024-03-14 label=3 peak_kw=86.0456 day_sse=0.000003
load-kmeans: date=2024-03-15 label=3 peak_kw=88.7584 day_sse=0.011469
load-kmeans: date=2024-03-16 label=2 peak_kw=46.4604 day_sse=0.019925
load-kmeans: date=2024-03-17 label=2 peak_kw=49.1733 day_sse=0.000564
days=14  k=3  seed=0  n_init=10  normalize=peak  sse=0.0877882  silhouette=0.925748  n_iter=1  attempt=0  step_min=60  resampled=0

rows=336  missing=0  duplicates=0

cluster=1  n=5  peak_hour=12  mean_peak_kw=99.3236
cluster=2  n=4  peak_hour=15  mean_peak_kw=48.8218
cluster=3  n=5  peak_hour=19  mean_peak_kw=86.1327

date=2024-03-04  label=1  peak_kw=100.898  day_sse=0.00220315
date=2024-03-05  label=1  peak_kw=96.6108  day_sse=0.00659297
date=2024-03-06  label=1  peak_kw=99.3236  day_sse=1.37079e-06
date=2024-03-07  label=1  peak_kw=102.036  day_sse=0.00626613
date=2024-03-08  label=1  peak_kw=97.7494  day_sse=0.00212247
date=2024-03-09  label=2  peak_kw=48.4704  day_sse=0.000296396
date=2024-03-10  label=2  peak_kw=51.1832  day_sse=0.0181265
date=2024-03-11  label=3  peak_kw=84.907  day_sse=0.00246202
date=2024-03-12  label=3  peak_kw=87.6198  day_sse=0.00386878
date=2024-03-13  label=3  peak_kw=83.3327  day_sse=0.0138874
date=2024-03-14  label=3  peak_kw=86.0456  day_sse=3.34741e-06
date=2024-03-15  label=3  peak_kw=88.7584  day_sse=0.011469
date=2024-03-16  label=2  peak_kw=46.4604  day_sse=0.0199252
date=2024-03-17  label=2  peak_kw=49.1733  day_sse=0.000563513
```

可以顺着这张表讲四件事：

- **三种形状分开了。** 五个商业日都是簇 1，四个周末都是簇 2，五个居民日都是簇 3。轮廓系数约 0.926，总 SSE 约 0.088。形状差得远，第一次重启就收敛，`attempt=0`、`n_iter=1`。
- **峰值归一化丢掉的是千瓦，不是形状。** 周末的日峰值平均只有约 48.8 kW，商业日约 99.3 kW，居民日约 86.1 kW。聚类时每一天都先除以自己的峰值，所以周末能单独成簇，是因为它的峰在 15:00 且更宽，不是因为它整体更小。把一条商业曲线乘上一个常数，峰值归一化之后会和原来的商业日落在同一个簇。
- **质心的峰值小时就是重编号的依据。** 簇 1 在正午最高，簇 2 在 15:00，簇 3 在 19:00。下图的三条粗线就是这三种典型日。
- **上图的细线是归一化之后的各天。** ±3.5 kW 的噪声在除以日峰值之后只剩下一窄条，所以细线贴着质心，但还能看出不是完全重合。小时数据从 00:00 到 23:00，步长 60 分钟，`resampled=0`。

上图蓝线是簇 1（商业、n=5），红线是簇 2（周末、n=4），绿线是簇 3（居民、n=5）。粗线是质心。下图只保留这三条典型日。

## Limitations

- 默认的峰值归一化只比较形状。要让“同样形状、但整体更低”的日子分开，用 `normalize='none'`
- 距离是对齐之后的欧氏距离，没有动态时间弯曲。峰如果整体平移一小时，会被当成另一种形状
- `k` 要自己定。默认 3 是为了这组例子里的三种形状，不是普遍的最佳簇数。换 `k` 再看 SSE 和轮廓系数即可，工具不自动选 k
- 质心是归一化曲线的平均。`centroids_kw` 才是簇内原始千瓦曲线的平均，两者不要混用
- 各天时钟不一致时会线性重采样。尖峰落在两个采样之间会被抹平；某一天盖不住全日网格的两端会直接报错
- 完全相同的曲线并成一簇时，并列距离归到较小的编号，可能留下空簇。空簇的轮廓系数是 NaN
- 峰值不大于 0 时不能做 `peak` 归一化，日均值不大于 0 时不能做 `mean` 归一化
- 示例是合成曲线，不能当作某条馈线的分类或负荷预测依据

## FAQ

**为什么默认除以峰值，不除以电量？**  
课堂里想比较的通常是“白天平、傍晚尖、下午宽”这种形状。除以峰值以后，最高点都是 1，形状差异留在其余时刻。除以日均值会把基荷的高低也卷进来。想保留千瓦，用 `normalize='none'`。

**周末峰值更低，为什么还能分成一类？**  
因为形状不同。周末的峰在 15:00，商业日的峰在 12:00，居民日的峰在 19:00。`mean_peak_kw` 仍能看到周末只有大约一半的峰值。若把商业日的功率整体乘以 0.5，峰值归一化后它会进商业簇。

**标签为什么从 1 开始，而且换种子也不换号？**  
编号从 1 到 k，和 MATLAB 的习惯一致。收敛后按质心峰值的小时重新排序，所以在这组分得很开的数据上，种子只影响搜索过程，不影响最后印出来的 1、2、3。种子仍然要固定：形状靠近时，不同种子可能得到不同的划分。

**需要工具箱或 scikit-learn 吗？**  
不需要。两边都是同一套 k-means++ 加 Lloyd。仓库的 `requirements.txt` 里虽然有 scikit-learn，这个工具不调用它。

**CSV 里是 W 怎么办？**  
工具不换算单位。先除以 1000 再当作 kW，否则 `peak_kw` 会大一千倍。形状聚类在峰值归一化之下不受单位缩放影响，但 `mean_peak_kw` 会错。

**矩阵的行和列反了会怎样？**  
行是一天，列是同一个时刻。24 个时刻、14 天的矩阵应是 14×24。写成 24×14 会被当成 24 天、每天 14 个点。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助对照典型日负荷曲线的形状聚类，结果不作为负荷预测、用电考核或成绩评定依据。请勿把学生姓名、学号、成绩或未公开的用电数据放进示例或提交到仓库。本工具随仓库以 MIT 许可证发布，见根目录 [LICENSE](../../LICENSE)。
