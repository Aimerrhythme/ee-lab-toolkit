# 波形傅里叶与 THD 速算

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Single-sided Fourier spectrum and THD for one sampled waveform (Python + MATLAB).**

读入一段均匀采样的电压或电流，画出单边幅度谱，找出基波，列出各次谐波的峰值、有效值、相对基波的百分比和相位，并算出总谐波畸变率 THD。默认例子是 50 Hz 基波，叠上 3、5、7 次谐波、5 V 直流和一小点噪声，正好 10 个周期。数字是合成的，不是录波，也没有学生信息。

课堂用的定义（峰值或有效值，比值相同；直流不进分子）：

```text
THD = sqrt(A2^2 + A3^2 + ... + AH^2) / A1
THD% = 100 * THD
```

谐波表不是直接读 FFT 的那一个格子，而是在基波频率的整数倍上做最小二乘：

```text
x[n] = dc + sum_h Ah * sin(2*pi*h*f0*n/fs + phi_h)
```

周期正好落在格子上时，矩形窗的谱线和这张表一致。周期对不齐时，谱线会泄漏，最小二乘仍按给定的 `f0` 把各次幅值收回来。`window` 只决定画出来的那条谱，不改 THD 的算法。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`、`matplotlib`（见仓库 `requirements.txt`）。谱和拟合只用 numpy，不调用 SciPy |
| MATLAB R2021b+ | 基础 MATLAB 即可。Hann 窗是按公式写的，不调用 `hann`，因此不需要 Signal Processing Toolbox |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/fft-thd/examples/run_demo.py
```

脚本读取 `examples/data/synthetic_waveform.csv`，把谐波表写到 `examples/output/fft_thd_demo.csv`，把波形和频谱写到 `examples/output/fft_thd_demo.png`（该目录已 gitignore）。

在自己的脚本里调用：

```python
import sys
sys.path.insert(0, "tools/fft-thd/python")
from fft_thd import fft_thd, format_table

result = fft_thd(
    "tools/fft-thd/examples/data/synthetic_waveform.csv",
    f0=50,
    n_harmonics=7,
    amp_floor_ratio=0.002,
    output_png="tools/fft-thd/examples/output/fft_thd_demo.png",
    output_csv="tools/fft-thd/examples/output/fft_thd_demo.csv",
)
print(result.thd_percent, result.fundamental_amplitude)
print(format_table(result))
```

只有采样序列、没有时间轴时，必须给 `fs`：

```python
result = fft_thd(samples, fs=5000, f0=50, n_harmonics=7)
```

不传 `f0` 时，在 Hann 谱上找搜索频段里最大的峰，当作基波，再用残差把频率收细。

### MATLAB

```matlab
cd('tools/fft-thd/matlab')
demo_fft_thd
```

或从仓库根目录：

```matlab
addpath('tools/fft-thd/matlab')
demo_fft_thd
```

图写到 `tools/fft-thd/examples/output/fft_thd_demo_matlab.png`，表写到同目录的 `fft_thd_demo_matlab.csv`。要在 IDE 里留住窗口，把 demo 中的 `'show', false` 改成 `'show', true`。

已知采样率和基波时：

```matlab
result = fft_thd(samples, 'fs', 5000, 'f0', 50, 'n_harmonics', 7);
result.thd_percent
result.harmonics(3).amplitude   % 3 次谐波峰值
```

时间列和信号列也可以一起放进来：`fft_thd(time, signal, 'f0', 50)`。

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。第一个位置参数是 CSV 路径或信号向量。Python 的第二个位置参数、MATLAB 的第二个位置参数在它是向量时表示信号，此时第一个参数是时间。MATLAB 名值对不区分大小写。

| Name | Default | Description |
|------|---------|-------------|
| `fs` | 由时间列估计 | 采样率，Hz。没有时间列时必填。和时间列同时给时，两者相对差要在 0.1% 以内 |
| `f0` | 自动检测 | 基波频率，Hz。给定以后谐波就锁在 `h*f0` 上，不再改这个数 |
| `n_harmonics` | `25` | 最高谐波次数，含基波。高于奈奎斯特的次数会丢掉 |
| `window` | `auto` | `auto`、`rect` 或 `hann`。`auto`：记录长度距整数个周期在 0.02 个周期以内用矩形窗，否则用 Hann。只影响频谱图 |
| `remove_dc` | `true` | 为真时，画谱之前先减去均值，避免直流把纵轴撑满。谐波拟合始终单独估计直流 |
| `f_search_min` | `10` | 自动找基波时的下限，Hz。默认避开直流裙边 |
| `f_search_max` | 奈奎斯特频率 | 自动找基波时的上限，Hz |
| `amp_floor_ratio` | `0` | 低于 `amp_floor_ratio * A1` 的次数仍列表，但不进 THD 分子。`0` 表示从 2 次起到最高次全部计入 |
| `output_csv` | 不写 | 谐波表路径。父目录不存在时会创建 |
| `output_png` | 不保存 | 上图波形、下图频谱。Python demo 使用无界面后端 |
| `show` | `false` | 为真时留下图窗 |

CSV 建议两列（逗号或分号）。时间列可缺，缺了就要给 `fs`。

| Column | Required | Accepted names |
|--------|----------|----------------|
| time | 否 | `time_s` `time` `t` `timestamp` |
| signal | 是 | `signal` `value` `voltage` `current` `waveform` `x` `v` `i`，或除时间以外唯一的一列 |

时间必须严格递增，步长要均匀（最大步长与最小步长之差不超过中位步长的 0.01%）。

## API

两侧返回同一组字段。MATLAB 里的波形、时间和频谱是列向量，Python 里是一维数组。

| Field | Meaning |
|-------|---------|
| `fs`, `f0` | 采样率，以及拟合使用的基波频率，Hz |
| `f0_source` | `given` 或 `detected` |
| `n_samples`, `cycles` | 点数，以及 `N * f0 / fs`（可以不是整数） |
| `window` | 频谱实际使用的窗：`rect` 或 `hann` |
| `remove_dc` | 画谱时是否去掉了均值 |
| `dc` | 拟合得到的直流 |
| `fundamental_amplitude`, `fundamental_rms` | 基波峰值、基波有效值（峰值 `/ sqrt(2)`） |
| `signal_rms` | 去掉该直流之后，时域序列的有效值 |
| `thd`, `thd_percent` | THD 的比值和百分数 |
| `n_harmonics`, `amp_floor_ratio` | 本次使用的次数上限和门槛 |
| `spectrum_frequency`, `spectrum_amplitude` | 单边谱。频率从 0 到奈奎斯特，幅度是峰值 |
| `harmonics` | 从 1 次排到实际拟合到的最高次 |
| `time`, `signal` | 时间轴和原始序列。没有时间列时，时间是 `(0:N-1)/fs` |
| `output_csv`, `output_png` | 写出的路径；未写时 Python 为 `None`，MATLAB 为 `''` |
| `fig` | `show` 为真时的图窗；否则为空 |

`harmonics` 的每一行：

| Field | Meaning |
|-------|---------|
| `order`, `frequency_hz` | 次数，以及 `order * f0` |
| `amplitude`, `rms` | 该次正弦的峰值和有效值 |
| `percent` | `100 * amplitude / A1`。基波这一行是 100 |
| `phase_rad`, `phase_deg` | 相位。约定是 `Ah*sin(2*pi*f*t + phase)`，`t = 0` 在第一个采样点 |
| `in_thd` | 这一行是否进了 THD 分子。基波恒为假 |

Python 另有 `format_table(result)`，demo 用它打表。MATLAB demo 打印同样的列。

## Example output

`examples/data/synthetic_waveform.csv` 的生成式（`fs = 5000` Hz，`N = 1000`，正好 10 个周期）：

```text
dc = 5
v(t) = 5
     + 100*sin(2*pi*50*t)
     +   8*sin(2*pi*150*t - pi/6)
     +   5*sin(2*pi*250*t + pi/5)
     +   2*sin(2*pi*350*t + pi/2)
     + Normal(0, 0.3), numpy Generator seed 42
```

无噪声时 `THD = sqrt(8^2 + 5^2 + 2^2) / 100 = 9.6437%`。Demo 取 `f0=50`、`n_harmonics=7`、`amp_floor_ratio=0.002`（0.2% 以下不进分子），所以 2、4、6 次的噪声残留被留在表里、不进 THD：

```text
fft-thd: f0=50 Hz fs=5000 Hz N=1000 window=rect THD=9.6589%
f0=50 Hz (given)  fs=5000 Hz  N=1000  cycles=10.0000  window=rect
dc=4.99133  A1=100  THD=9.6589%  floor=0.002
order   frequency_Hz    amplitude          rms    percent  phase_deg in_thd
    1        50.0000     100.0000      70.7107   100.0000     -0.011      0
    2       100.0000       0.0071       0.0050     0.0071    -79.289      0
    3       150.0000       8.0176       5.6693     8.0176    -30.146      1
    4       200.0000       0.0226       0.0160     0.0226     88.375      0
    5       250.0000       4.9946       3.5317     4.9946     36.049      1
    6       300.0000       0.0065       0.0046     0.0065      1.384      0
    7       350.0000       2.0164       1.4258     2.0164     90.025      1
analytic noise-free THD for 8%, 5%, and 2% harmonics: 9.6437%
```

可以顺着这张表讲四件事：

- **3、5、7 次还在原来的百分数附近。** 8%、5%、2% 对应峰值 8 V、5 V、2 V。噪声把它们挪了大约 0.02 V，THD 从 9.6437% 变成 9.6589%。
- **偶数次是噪声，不是波形里放进去的。** 0.2% 的门槛把它们挡在 THD 外面。门槛改成 0，这些小项会进分子，THD 会再高一点。
- **直流约 5 V，不进 THD。** 相位以第一个点为 0：3 次约 -30°，5 次约 36°，7 次约 90°。
- **10 个整周期，`window=auto` 选了矩形窗。** 频谱在 50、150、250、350 Hz 是细峰，峰高和表里的峰值一致。图上红点标的是基波以及进入 THD、且不小于 0.2% 的谐波。

上图是波形和拟合曲线（虚线）。下图是单边峰值谱，文本框写 `f1` 和 `THD%`。记录比 10 个周期更长时，上图只画前 10 个周期，频谱仍用整段。坐标和标题是英文。

## Limitations

- 默认认为基波是搜索频段里最大的那根谱线。基波比某次谐波还小，或基波低于 `f_search_min`（默认 10 Hz）时，请把 `f0` 直接传进来
- 只拟合整数次谐波。间谐波会漏进邻近次数和残差里，本工具不单独列出来
- 一段稳态记录、均匀采样、一个通道。暂态、掉点、两个采样率拼在一起，先整理再送进来
- 至少 16 个点，且点数要多于拟合系数（1 个直流 + 每个次数的正弦和余弦）。不够时降低 `n_harmonics` 或加长记录
- 基波峰值近于 0 时 THD 没有定义，函数会报错，而不是返回一个很大的数
- 这不是电能质量分析仪，也没有做 IEC 61000-4-7 的分组。示例是合成波形，不能当作某条馈线的录波

## FAQ

**THD 用峰值还是有效值？**  
都可以，比值一样。表里两列都有：有效值 = 峰值 / √2。分子分母必须同一套。

**为什么不直接把 FFT 格子的高度当成谐波幅值？**  
格子只在「周期数是整数、而且没有加窗」时正好等于正弦峰值。Hann 窗会把一根谱线摊到相邻格子上：整周期、周期 Hann 时，中心格仍是峰值，左右邻格各是峰值的一半，那两格不是新的谐波。记录不是整周期时，能量还会漏到别的次数上。所以图用窗函数把谱线收干净，表用最小二乘去读 `h*f0`。

**`window='auto'` 什么时候换成 Hann？**  
`N*f0/fs` 离开最近整数超过 0.02 时换。想对比两种图，把 `window` 改成 `rect` 或 `hann` 即可，THD 表的算法不变。

**没给 `f0` 时频率从哪来？**  
先在 Hann 谱上、`f_search_min` 到 `f_search_max` 之间取最大峰。峰已经落在格子中心（抛物线偏移不超过 0.02 个格子）就用这个格子的频率。否则从对数幅度的抛物线插值出发，对谐波模型的残差做三步牛顿法。电网频率已知时，直接传 `f0=50` 更稳。

**直流算不算畸变？**  
不算。THD 从 2 次加到最高次。直流在 `dc` 里，也在表外。`remove_dc=false` 时频谱会把 0 Hz 画出来，THD 仍然不含它。

**需要工具箱吗？**  
不需要。Python 用 numpy 的 FFT 和最小二乘；MATLAB 用 `fft` 和反斜杠。两边的 Hann 都是 `0.5 - 0.5*cos(2*pi*k/N)`，k = 0…N-1。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助对照频谱和谐波含有率，结果不作为电能质量合格判定、保护整定或考核依据。请勿把学生姓名、学号、成绩或未公开的录波放进示例或提交到仓库。本工具随仓库以 MIT 许可证发布，见根目录 [LICENSE](../../LICENSE)。
