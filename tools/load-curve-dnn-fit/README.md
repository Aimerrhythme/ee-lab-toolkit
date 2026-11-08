# 典型日负荷曲线 DNN 拟合小工具

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Polynomial and shallow DNN fit of one daily load curve (Python + MATLAB).**

把一条典型日负荷看成负荷对时刻的函数，用可调次数的多项式和一层 tanh 隐层的小 MLP 去逼近，再比较二者的残差。这是进入「代理模型 / 潮流代理」之前的最小可运行模板：同一个自变量、同一套归一化、同一组误差。默认例子是 2024-03-11 这一天、15 分钟一个点的合成居民曲线，有早晨肩峰和傍晚尖峰。功率单位是 kW。数字是课堂公式加一点固定噪声，不是某条馈线的运行记录，也没有学生信息。

时刻先收成 `[-1, 1)` 里的 `u`。`minute` 是从当天 00:00 起算、落在 `[0, 1440)` 里的分钟：

```text
u = 2 * (minute / 1440) - 1
```

负荷 `P`（kW）再归一化成两边共同拟合的目标 `y`。默认是峰值归一化：

```text
peak:    y = P / max(P)                  scale = max(P),  offset = 0
minmax:  y = (P - min(P)) / span         scale = max(P) - min(P),  offset = min(P)
none:    y = P                           scale = 1,       offset = 0
```

预测映射回千瓦：`P_hat = y_hat * scale + offset`。RMSE、MAE 和最大绝对误差都在这条千瓦残差上计算，残差定义是拟合值减去实测值。`poly_mse` 和 `dnn_mse` 留在 `y` 上，那才是两个模型真正在最小化的均方误差。因此

```text
rmse_kW = sqrt(mse_y) * scale
```

多项式是 `u` 的幂：

```text
y_hat = c0 + c1 u + c2 u^2 + ... + cd u^d
```

`poly_coeff` 从常数项排到最高次。系数来自法方程，用带部分主元的 Gauss-Jordan 消去求解。主元取该列对角线及其下方绝对值最大的一行，并列时留下更靠上的那一行。

网络是 `1-hidden-1` 的 MLP，默认 `hidden = 8`。隐层是 tanh，输出是线性的：

```text
h_j = tanh(w1_j * u + b1_j)
y_hat = sum_j w2_j * h_j + b2
MSE = mean((y_hat - y)^2)
d(MSE)/d(y_hat) = (2/n) * (y_hat - y)
```

训练是全批量 Adam，固定 `epochs` 步，没有提前停止，也没有留出时刻。`beta1^t` 和 `beta2^t` 是连乘 `t` 次，`t` 从 1 计到 `epochs`，不是调用 `pow`。默认 `beta1 = 0.9`、`beta2 = 0.999`、`epsilon = 1e-8`、学习率 `0.05`。

权重用两边共用的 32 位 LCG 抽取，Glorot 均匀初始化；偏置从 0 开始。种子是第一步之前的状态，先对 `2^32` 取模：

```text
state = (1664525 * state + 1013904223) mod 2^32
U = state / 2^32                         落在 [0, 1)
limit = sqrt(6 / (1 + hidden))
w = (2 U - 1) * limit
```

先按隐单元顺序抽完 `w1`，再抽 `w2`。同一个 `seed` 因此在 Python 和 MATLAB 里得到同一组初值。求和也按样本从早到晚、隐单元从小到大的顺序逐项相加，不用会改变累加次序的库函数。

这个例子只借用「用日负荷做函数逼近，再走向代理模型」的课堂动机。公式和网络都是本仓库自己写的，没有从外部课程仓库搬代码。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`、`matplotlib`（见仓库 `requirements.txt`）。拟合只用手写的最小二乘和 MLP，不调用 scikit-learn |
| MATLAB R2021b+ | 基础 MATLAB 即可，不需要 Deep Learning Toolbox 或 Statistics Toolbox。同一套 `.m` 也能在 GNU Octave 里算完并出图 |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/load-curve-dnn-fit/examples/run_demo.py
```

脚本读取 `examples/data/synthetic_daily_load_kw.csv`，把曲线和两条拟合写到 `examples/output/load_curve_dnn_fit_demo.csv`，把两张子图写到同名的 `.png`（该目录已 gitignore）。

在自己的脚本里调用：

```python
import sys
sys.path.insert(0, "tools/load-curve-dnn-fit/python")
from load_curve_dnn_fit import format_table, load_curve_dnn_fit

result = load_curve_dnn_fit(
    "tools/load-curve-dnn-fit/examples/data/synthetic_daily_load_kw.csv",
    degree=5,
    hidden=8,
    epochs=2000,
    learning_rate=0.05,
    seed=0,
    normalize="peak",
    output_png="tools/load-curve-dnn-fit/examples/output/load_curve_dnn_fit_demo.png",
    output_csv="tools/load-curve-dnn-fit/examples/output/load_curve_dnn_fit_demo.csv",
)
result.poly_rmse, result.dnn_rmse, result.poly_coeff, result.w1
print(format_table(result))
```

不读 CSV 时，可以只给一条功率曲线。`n` 个点会均匀铺在当天，第 `i` 点（从 0 计）的分钟是 `i * (1440 / n)`。也可以同时给时刻和功率。数值时刻默认按最大值推断：最大值小于 24 视为小时，小于 1440 视为分钟。想用 `[0, 1)` 的日分数，写 `time_unit="dayfrac"`。

```python
result = load_curve_dnn_fit([6, 8, 10, 12], degree=1, normalize="none", epochs=1, hidden=1)
result = load_curve_dnn_fit([0, 6, 12, 18], [10, 40, 20, 30], time_unit="hour", normalize="peak")
result = load_curve_dnn_fit(
    ["2024-03-11 00:00:00", "2024-03-11 12:00:00"],
    [18, 40],
    degree=1,
    epochs=1,
    hidden=1,
)
```

### MATLAB

```matlab
cd('tools/load-curve-dnn-fit/matlab')
demo_load_curve_dnn_fit
```

或从仓库根目录：

```matlab
addpath('tools/load-curve-dnn-fit/matlab')
demo_load_curve_dnn_fit
```

图写到 `tools/load-curve-dnn-fit/examples/output/load_curve_dnn_fit_demo_matlab.png`，表写到同名的 `.csv`。要在 IDE 里留住窗口，把 demo 中的 `'show', false` 改成 `'show', true`。

单独一条功率曲线按行或列都可以。再跟一个同样长度的功率向量时，第一个是时刻：

```matlab
result = load_curve_dnn_fit([6 8 10 12], 'degree', 1, 'normalize', 'none', 'epochs', 1, 'hidden', 1);
result = load_curve_dnn_fit([0 6 12 18], [10 40 20 30], 'time_unit', 'hour', 'normalize', 'peak');
result.poly_rmse
result.dnn_rmse
```

2000 步全批量训练在示例的 96 个点上通常是几秒。Python 一侧大约不到一秒；MATLAB / Octave 的显式循环大约几十秒。把 `epochs` 改小可以更快看到一条还没拟合好的网络。

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。MATLAB 名值对不区分大小写。第一个参数是 CSV 路径、功率向量，或与 `power` 一起传入的时刻。

| Name | Default | Description |
|------|---------|-------------|
| `degree` | `5` | 多项式次数，非负整数，必须小于样本数 |
| `hidden` | `8` | 隐层宽度，正整数。结构是 `1-hidden-1`，激活是 tanh |
| `epochs` | `2000` | 全批量 Adam 的步数，正整数 |
| `learning_rate` | `0.05` | Adam 学习率，正的有限数 |
| `beta1` | `0.9` | Adam 一阶矩系数，落在 `[0, 1)` |
| `beta2` | `0.999` | Adam 二阶矩系数，落在 `[0, 1)` |
| `epsilon` | `1e-8` | Adam 分母里的正数 |
| `seed` | `0` | 非负整数。LCG 的初值是 `seed mod 2^32` |
| `normalize` | `peak` | `peak`、`minmax` 或 `none` |
| `time_unit` | `auto` | `auto`、`hour`、`minute` 或 `dayfrac`。只用于数值时刻 |
| `time_col` | 自动 | CSV 的时间列。可写 `timestamp`、`time`、`时间` 等 |
| `power_col` | 自动 | CSV 的功率列，单位 kW。可写 `power_kw`、`load`、`功率` 等 |
| `day` | `day-01` | 数值时刻或单独一条功率曲线的日期标签，`YYYY-MM-DD`。不用于 CSV |
| `csv_path` | 空 | CSV 路径。和位置参数不要同时给 |
| `output_csv` | 不写 | 曲线表：`hour,minute,power_kw,poly_kw,dnn_kw,poly_residual_kw,dnn_residual_kw`。父目录不存在时会创建 |
| `output_png` | 不保存 | 实测、两条拟合和残差图。Python demo 使用无界面后端 |
| `show` | `false` | 为真时留下图窗 |

`time_unit="auto"` 只看数值时刻的范围：最小值不小于 0 且最大值小于 24，当成小时；最大值小于 1440，当成分钟。小时网格不要把 24 算进去，24 会落到分钟那一支。只覆盖到第 20 分钟的序列最大值仍小于 24，自动规则会把它当成小时；这种短序列请写 `time_unit="minute"`。`0.25` 在自动规则下是 0.25 小时，不是一天的 1/4。

时间戳接受这几种零填充写法：`YYYY-MM-DD HH:MM:SS`、`YYYY-MM-DD HH:MM`，中间的空格可以换成 `T`，日期分隔符可以是 `-` 或 `/`。带时区的时间会拒绝。

CSV 可用逗号或分号。空的功率格子和 `nan` 会丢掉，并计入 `n_missing`；同一天、同一分钟的重复行保留文件中的第一行。一天只有一个样本会报错。多天必须落在同一条分钟网格上，工具再按日期顺序逐点做算术平均，得到一条典型日，`date` 记为 `typical`。某一天的网格对不上会报错，不做插值。

| Column | Required | Meaning |
|--------|----------|---------|
| `timestamp` | 是 | 本地时间。也认 `datetime`、`time`、`时间`、`时刻`、`日期` |
| `power_kw` | 是 | 功率，kW。也认 `load_kw`、`p_kw`、`power`、`p`、`负荷`、`功率`、`有功` |

`examples/data/synthetic_daily_load_kw.csv` 是 2024-03-11、从 00:00 到 23:45、每 15 分钟一个点的课堂数据，共 96 行。记 `k = 0…95`，`h = 0.25 k`：

```text
P = 18
  + 28 * exp(-((h - 7.5) / 1.6)^2)
  + 12 * exp(-((h - 12.5) / 2.2)^2)
  + 62 * exp(-((h - 19.2) / 1.8)^2)
  + noise
```

前三项分别是早晨肩峰、中午鼓包和傍晚尖峰，单位 kW。噪声幅度是 1.2 kW：

```text
state = (1664525 * (1000 + k) + 1013904223) mod 2^32
noise = (2 * state / 2^32 - 1) * 1.2
```

## API

两侧返回同一组字段。曲线在 Python 里是一维数组，在 MATLAB 里是列向量。`u` 和 `y` 是送进两个模型的输入和目标。`poly_kw`、`dnn_kw` 是映射回 kW 的拟合。残差是拟合减实测。

| Field | Meaning |
|-------|---------|
| `hour`, `minute`, `power_kw` | 小时、分钟，以及拟合用的功率（kW）。多日平均之后这里是典型日 |
| `u`, `y` | 缩放过的时刻，以及归一化后的目标 |
| `poly_y`, `dnn_y` | 两个模型在 `y` 上的预测 |
| `poly_kw`, `dnn_kw` | 映射回 kW 的预测 |
| `poly_residual_kw`, `dnn_residual_kw` | 拟合减实测，kW |
| `poly_coeff` | 多项式系数，常数项在前，长度是 `degree + 1` |
| `w1`, `b1`, `w2`, `b2` | 训练后的网络参数。`w1`、`b1`、`w2` 的长度都是 `hidden` |
| `degree`, `hidden`, `epochs`, `learning_rate` | 请求的模型参数 |
| `beta1`, `beta2`, `epsilon`, `seed` | Adam 系数、随机种子 |
| `normalize`, `activation` | 归一化方式，以及固定的 `tanh` |
| `poly_rmse`, `poly_mae`, `poly_max_abs` | 多项式在 kW 残差上的 RMSE、MAE、最大绝对误差 |
| `dnn_rmse`, `dnn_mae`, `dnn_max_abs` | 网络在 kW 残差上的同样三项 |
| `poly_mse`, `dnn_mse` | `y` 上的均方误差，也就是训练目标 |
| `peak_kw`, `min_kw`, `scale_kw`, `offset_kw` | 曲线的峰值、谷值，以及 `y` 映射回 kW 的比例和偏移 |
| `date`, `dates` | 单日的日期、`day-01`，或多日平均时的 `typical`。`dates` 是参与平均的每一天 |
| `n_samples`, `n_days` | 拟合曲线的点数，以及源数据里的天数 |
| `n_rows`, `n_missing`, `n_duplicates` | 去掉空功率和重复时刻之后留下的点数、丢掉的空功率、丢掉的重复时刻 |
| `averaged`, `step_minutes` | 是否做了多日平均。网格等间距时给出步长（分钟），否则为 NaN |
| `summary` | 与 `format_table` 相同的文本 |
| `output_csv`, `output_png` | 写出的路径。未写时 Python 为 `None`，MATLAB 为 `''` |
| `fig` | `show` 为真时的图窗；否则为空 |

Python 另有 `format_table(result)`，demo 用它打表。MATLAB 的 `result.summary` 是同一段文字。

上图是实测（实线）、多项式（虚线）和 DNN（实线）。下图是两条残差，以及一条零线。图例放在左上角。坐标和标题是英文。运行环境有 `sgtitle` 时，总标题写两组 RMSE；没有该函数时，这一行改放在上图标题里。

## Example output

`degree = 5`，`hidden = 8`，`epochs = 2000`，`learning_rate = 0.05`，`seed = 0`，`normalize = peak`。多项式有 6 个系数，网络有 `3 * 8 + 1 = 25` 个参数。

```text
load-curve-dnn-fit: poly_rmse=10.2522 poly_mae=7.7209 poly_max_abs=27.0413 dnn_rmse=2.4956 dnn_mae=2.0219 dnn_max_abs=6.5276
n=96  degree=5  hidden=8  epochs=2000  lr=0.05  seed=0  normalize=peak  date=2024-03-11  averaged=0  step_min=15

poly_rmse=10.2522  poly_mae=7.72094  poly_max_abs=27.0413  poly_mse=0.0162919

dnn_rmse=2.4956  dnn_mae=2.02194  dnn_max_abs=6.5276  dnn_mse=0.000965355

rows=96  missing=0  duplicates=0  days=1  peak_kw=80.3215  min_kw=18.2967
```

可以顺着这张表讲四件事：

- **两个模型看的是同一条曲线。** `u` 都是缩放过的时刻，`y` 都是除以峰值 80.3215 kW 之后的数。RMSE 再乘回这个峰值，所以 10.25 kW 和 2.50 kW 可以直接比。`sqrt(0.0162919) * 80.3215` 就是多项式的 RMSE。
- **五次多项式跟不上两个峰。** 早晨大约 7:30 的肩峰和傍晚大约 19:15 的尖峰，五次多项式都抹平了。最大绝对误差 27.04 kW 落在傍晚。曲线末尾多项式还会掉到 0 以下，因为它不知道负荷应当非负，也不知道 24:00 要接回 00:00。
- **浅层网络把两个峰都跟上了。** 1-8-1 的 tanh 网络 RMSE 是 2.50 kW，MAE 是 2.02 kW，最大绝对误差是 6.53 kW。合成噪声只有 ±1.2 kW，所以这条残差已经靠近噪声，而不是还停在形状误差上。它用了 25 个参数，多项式只用 6 个；这不是同等容量的比赛，课堂里要把参数个数一起说出来。
- **这是样本内残差，不是预测成绩。** 96 个点全部参与拟合，没有留出小时。换 `seed` 会改变初值，残差会略有不同，但在这组默认设置下仍然明显小于五次多项式。把 `epochs` 降到几百，网络残差会变大，可以当作「还没训练完」的对照。

上图蓝线是实测，红色虚线是五次多项式，绿色实线是 DNN。下图用同样的颜色画残差。多项式在傍晚的残差摆幅大约是网络的四倍，并在一天的末尾冲到零线以下。

## Limitations

- 报告的是样本内残差。它说明曲线能不能被这个函数逼近，不是负荷预测、次日考核或泛化误差
- 默认网络有 25 个参数，五次多项式有 6 个。网络更灵活，所以残差更小并不自动说明「DNN 这种方法更对」
- 多项式不保证功率非负，也不施加 `P(0) = P(24)`。次数升高以后，`[-1, 1]` 上的范德蒙德矩阵会变病态，工具在主元过小时直接报错，而不是自动降次
- 峰值不大于 0 时不能做 `peak`。曲线是常数时不能做 `minmax`
- 多日数据必须已经落在同一条分钟网格上。工具只做算术平均，不插值，也不分工作日和周末
- 数值时刻的自动单位靠最大值推断。短于 24 分钟的序列、或把 24 点写成一天终点的序列，要显式写 `time_unit`
- `seed` 超过 `2^53` 之后，MATLAB 的双精度整数不再精确，两边的初值可能分开。课堂种子用小的非负整数即可
- 示例是合成曲线，不能当作某条馈线的拟合、预测或运行依据

## FAQ

**为什么默认除以峰值，而不是最小-最大？**  
峰值归一化之后，最高点是 1，其余时刻是占峰值的比例，和负荷曲线课上「典型日形状」的说法一致。最小-最大会把谷值拉到 0、峰值拉到 1，形状仍在，但基荷不再占一个固定的比例。想直接在千瓦上拟合，用 `normalize='none'`。三种方式的 RMSE 都映射回 kW，仍然可以横比。

**为什么不用 Deep Learning Toolbox 或 scikit-learn？**  
仓库的 `requirements.txt` 里有 scikit-learn，这个工具不调用它。MATLAB 一侧也不调用 `fitnet`。两边是同一套手写的 1-hidden-1 网络和同一套 Adam，这样没有额外工具箱的机房也能跑，并且同一个 `seed` 能对上同一组权重。

**多项式和网络谁更「准」？**  
在默认例子上，网络的千瓦 RMSE 大约是五次多项式的四分之一。同时它的参数是 25 对 6。把 `degree` 提高到十几，多项式也会把训练点贴得更近，但系数会很难读，曲线两端更容易甩出去。这个工具把次数和隐层宽度都留给课堂自己改。

**残差为什么是拟合减实测？**  
下图的零线以上表示拟合偏高。最大绝对误差不看符号。MAE 是绝对残差的平均，RMSE 对傍晚那几个大偏差更重。

**CSV 里是 W 怎么办？**  
工具不换算单位。先除以 1000 再当作 kW，否则 `peak_kw` 和 RMSE 都会大一千倍。

**多天的表会怎样？**  
每一天的分钟网格必须相同。工具按日期顺序把同一分钟上的功率做平均，得到一条典型日，`averaged` 为真，`date` 为 `typical`。`dates` 里仍能看到是哪几天参与了平均。网格不一致就报错，避免悄悄把缺测时刻插出来。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助对照一条典型日负荷上的多项式拟合和浅层网络拟合，结果不作为负荷预测、用电考核、调度运行或成绩评定依据。请勿把学生姓名、学号、成绩或未公开的用电数据放进示例或提交到仓库。本工具随仓库以 MIT 许可证发布，见根目录 [LICENSE](../../LICENSE)。
