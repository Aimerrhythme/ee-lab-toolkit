# 简单传递函数 Bode 图演示

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](../../LICENSE)

**Bode magnitude, phase, gain margin, and phase margin for a classroom transfer function (Python + MATLAB).**

把一个单输入单输出传递函数画成 Bode 图：对数频率轴上的幅值（dB）和相位（deg），并在有定义的地方给出增益穿越频率、相位穿越频率、相位裕度和增益裕度。示例是合成的一阶惯性、二阶阻尼扫描，以及和 `pid-step-compare` 同一组参数的 PID 开环，外加一个可以手算增益裕度的三阶对象。没有装置记录，也没有学生信息。

分子、分母都按降幂排列。频率响应就是多项式求值，两边同一套式子：

```text
H(jw) = polyval(num, jw) / polyval(den, jw)
magnitude_dB = 20 log10(|H|)
phase_deg    = unwrap(angle(H))，单位度
```

Python 调用 `scipy.signal.freqs`，它就是上面这个求值。MATLAB 用基础的 `polyval`，不需要 Control System Toolbox，也不需要 Signal Processing Toolbox。

裕度用正频率上的课堂定义。相位是展开后的度数：

```text
PM    = wrap_180(phase_deg(w_gc) + 180)
GM_dB = -magnitude_dB(w_pc)
```

`w_gc` 是幅值穿过 0 dB 的增益穿越频率，`w_pc` 是相位穿过 `-180 + 360k` 度（负实轴）的相位穿越频率。有多个穿越时，表上报的是裕度最小的那一个；全部穿越仍留在结果里。整段幅值都低于 0 dB 时相位裕度记为 `+inf`；相位碰不到负实轴时增益裕度记为 `+inf`；整段幅值都高于 0 dB、网格里没有穿越时，相位裕度记为 `nan`。

四种写法：

| `form` | 传递函数 |
|--------|----------|
| `tf` | 直接给 `num`、`den` |
| `first_order` | `k / (tau s + 1)` |
| `second_order` | `k wn^2 / (s^2 + 2 zeta wn s + wn^2)` |
| `pid_loop` | 开环 `L(s) = C(s) G(s)`。对象是上面的二阶式，控制器是带滤波微分的并联 PID |

```text
C(s) = Kp + Ki/s + Kd * (kd_n * s) / (s + kd_n)
```

`kd_n` 就是 `pid-step-compare` 里的滤波系数 `N`，默认 10。`Ki = Kd = 0` 时控制器退化为比例。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`、`scipy`、`matplotlib`（见仓库 `requirements.txt`）。频率响应用 `scipy.signal.freqs` |
| MATLAB R2021b+ | 基础 MATLAB 即可。`polyval`、`roots`、`logspace` 都在基础语言里，不需要 Control System Toolbox 或 Signal Processing Toolbox |

## Quick start

在仓库根目录执行。

### Python

```bash
python tools/bode-demo/examples/run_demo.py
```

脚本读取 `examples/data/systems.csv`，把四张图写到 `examples/output/`（该目录已 gitignore）：

- `bode_demo_first_order.png`
- `bode_demo_damping.png`
- `bode_demo_pid_loop.png`
- `bode_demo_textbook.png`

在自己的脚本里调用：

```python
import sys
sys.path.insert(0, "tools/bode-demo/python")
from bode_demo import bode_demo, format_margins_table

result = bode_demo([1.0], [1.0, 1.0], frequency_rad_s=[1.0])
print(result.magnitude_db[0, 0], result.phase_deg[0, 0])

result = bode_demo(
    "tools/bode-demo/examples/data/systems.csv",
    names=["zeta=0.5", "textbook"],
    output_png="tools/bode-demo/examples/output/bode_demo_demo.png",
)
print(format_margins_table(result.margins))
```

不传对象时，默认是 `G(s) = 1/(s^2 + s + 1)`（`wn = 1`，`zeta = 0.5`）。

### MATLAB

一行：

```matlab
addpath('tools/bode-demo/matlab'); demo_bode_demo
```

或先进入函数目录：

```matlab
cd('tools/bode-demo/matlab')
demo_bode_demo
```

图写到 `examples/output/bode_demo_*_matlab.png`。要在 IDE 里留住窗口，把 demo 里的 `'show', false` 改成 `'show', true`。

换一组系数：

```matlab
result = bode_demo([1], [1 1 1], 'w_min', 0.05, 'w_max', 20, 'show', true);
```

`result.frequency_rad_s` 是列向量。`magnitude_db`、`phase_deg` 的每一列对应一个系统，和 Python 的「频率 × 系统」一致。

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。系数或系统是位置参数；MATLAB 里用 `[]` 表示「这一侧不用」。

| Name | Default | Description |
|------|---------|-------------|
| `num` | 见下 | 分子系数，降幂。也可以是一条系统、系统列表，或 CSV 路径 |
| `den` | — | 分母系数，降幂。`num` 是系数向量时必填 |
| `systems` | — | 与位置参数二选一：struct / cell / CSV |
| `form` | 无对象时为 `second_order` | `tf`、`first_order`、`second_order`、`pid_loop` |
| `name` | 按形式自动起名 | 单个对象的名字。CSV 或列表里各自带 `name` |
| `names` | 全部 | 只保留这些名字，并按这个顺序画 |
| `k` | `1` | 一阶、二阶和 PID 对象的增益 |
| `tau` | `1` | 一阶时间常数，秒，必须为正 |
| `wn` | `1` | 自然频率，rad/s，必须为正 |
| `zeta` | `0.5` | 阻尼比，可以为 0 以外的负数（右半平面极点）。`zeta = 0` 的极点在虚轴上，会报错 |
| `kp`, `ki`, `kd` | `1`, `0`, `0` | 只用于 `pid_loop` |
| `kd_n` | `10` | 微分滤波系数。`kd ≠ 0` 时必须为正 |
| `w_min`, `w_max` | 由零极点估一档 | 频率网格两端，rad/s，必须为正且 `w_max > w_min` |
| `n_points` | `800` | 对数网格点数，2 到 20000 |
| `frequency_rad_s` | 不指定 | 直接给定正频率。给定之后不要再传 `w_min` / `w_max` |
| `output_png` | 不保存 | PNG 路径。父目录不存在时会创建 |
| `show` | `false` | 为真时留下图窗。Python demo 使用无界面后端，只保存文件 |

自动网格取非零零极点模的 1/10 到 10 倍。严格真分且高频幅值仍不低于 0 dB 时，上端最多再放宽 4 个十倍频。原点极点多于原点零点、而低频端幅值仍不高于 0 dB 时，下端同样最多放宽 4 个十倍频，这样小增益的积分环节也不会把穿越频率留在网格外面。

`k`、`tau`、`wn`、`zeta`、`kp`、`ki`、`kd`、`kd_n` 只在用 `form` 造一个对象时生效。读 CSV 或传入系统列表时，这些数写在每一行里；再在调用里改它们会报错，避免悄悄没用上。

## API

两侧返回同一组字段。MATLAB 的 `frequency_rad_s` 是列向量；Python 是一维数组。`magnitude_db` 和 `phase_deg` 都是「频率 × 系统」。

| Field | Meaning |
|-------|---------|
| `frequency_rad_s` | 升序频率，rad/s |
| `magnitude_db` | 幅值，dB。非有限点在图上会断开 |
| `phase_deg` | 展开后的相位，度 |
| `names` | 每列的名字 |
| `margins` | 每列一条裕度记录，字段见下表 |
| `w_min`, `w_max` | 实际网格的两端 |
| `n_points` | `frequency_rad_s` 的长度 |
| `output_png` | 写出的路径；未保存时 Python 为 `None`，MATLAB 为 `''` |
| `fig` | `show` 为真时的图窗；否则为空 |

`margins` 字段：

| Field | Meaning |
|-------|---------|
| `name`, `form` | 名字和形式 |
| `num`, `den` | 实际使用的系数，降幂 |
| `gain_crossover_rad_s` | 每一个 0 dB 穿越 |
| `phase_crossover_rad_s` | 每一个负实轴穿越 |
| `phase_margin_deg` | 最小相位裕度，度 |
| `phase_margin_rad_s` | 对应的增益穿越频率 `w_gc`。没有则为 NaN |
| `gain_margin_db` | 最小增益裕度，dB |
| `gain_margin_rad_s` | 对应的相位穿越频率 `w_pc`。没有则为 NaN |

表头上的 `w_gc` 就是 `phase_margin_rad_s`，`w_pc` 就是 `gain_margin_rad_s`。名字容易反：相位裕度读在增益穿越上，增益裕度读在相位穿越上。

Python 另有 `format_margins_table(margins)`。MATLAB demo 打同样的列。

## Example output

`run_demo.py` 的四段表如下。幅值和相位都是在网格上算完、再对穿越频率做对分细化之后的结果。

一阶 `k/(tau s+1)`。直流增益是 1，有限频率上幅值始终低于 0 dB，相位只落到 -90°，所以两个裕度都是无穷。拐点本身不在这张裕度表里：`tau = 1` 时 `w = 1` 的幅值是 `-10 log10(2) ≈ -3.0103 dB`，相位是 -45°。`tau = 0.2` 的拐点在 5 rad/s，数值相同。

```text
name             form                 w_gc     PM_deg       w_pc      GM_dB
tau=1            first_order           nan        inf        nan        inf
tau=0.2          first_order           nan        inf        nan        inf
```

二阶阻尼扫描，`wn = 1`，`k = 1`。`zeta = 0.5` 时 `|G(j wn)| = 1/(2 zeta) = 1`，相位正好 -90°，所以 `w_gc = 1`、`PM = 90°`。相位要到无穷远处才到 -180°，增益裕度是无穷。`zeta = 0.707` 是 `1/sqrt(2)`，谐振峰刚好消失，有限频率上不再穿过 0 dB。

```text
name             form                 w_gc     PM_deg       w_pc      GM_dB
zeta=0.2         second_order        1.356    32.8599        nan        inf
zeta=0.5         second_order            1    90.0000        nan        inf
zeta=0.707       second_order          nan        inf        nan        inf
zeta=1           second_order          nan        inf        nan        inf
zeta=1.5         second_order          nan        inf        nan        inf
```

PID 开环用 `G(s) = 1/(s+1)^2`，增益和 `pid-step-compare` 的示例相同：P 是 `Kp = 2`，PI 加上 `Ki = 1.5`，PID 再加上 `Kd = 0.8`、`kd_n = 10`。相对阶都是 2，相位趋近 -180° 但在有限频率上不过，所以增益裕度仍是无穷；加上积分以后相位裕度从 90° 降到约 48°，滤波微分再把它拉回到约 71°。

```text
name             form                 w_gc     PM_deg       w_pc      GM_dB
P                pid_loop                1    90.0000        nan        inf
PI               pid_loop            1.172    48.3202        nan        inf
PID              pid_loop            1.077    71.2520        nan        inf
```

手算增益裕度用 `L(s) = 1 / (s(s+1)^2)`，系数 `num = [1]`，`den = [1 2 1 0]`。`den(jw) = -2 w^2 + j w (1-w^2)`，虚部在 `w = 1` 为零，此时 `L = -1/2`，相位是 -180°，`GM = -20 log10(1/2) = 6.0206 dB`。`|L| = 1` 的频率来自 `u = w^2` 的三次方程 `u^3 + 2 u^2 + u - 1 = 0`，正根给出 `w_gc ≈ 0.6823`，相位裕度约 21.39°。

```text
name             form                 w_gc     PM_deg       w_pc      GM_dB
textbook         tf                 0.6823    21.3864          1     6.0206
```

图是上下两栏，横轴对数，坐标和标题都是英文。上栏幅值，下栏相位。灰色点线是 0 dB 和 -180°（相位若继续往下，-540° 等负实轴也会画出来）。圆点标在增益穿越上，方点标在相位穿越上。图例里带这一列的 PM 和 GM。颜色按系统循环，线型按实线、虚线、点划线、点线循环。

## Limitations

- 只做单输入单输出的线性传递函数。裕度是正频率上的穿越定义，不是完整的 Nyquist 圈数判定
- 原点上的极点可以画（网格从 `w > 0` 开始）。其他虚轴极点会使幅值无界，直接报错
- 自动频率范围最多再放宽 4 个十倍频。穿越若仍落在网格外，对应裕度是 `inf` 或 `nan`，把 `w_min` / `w_max` 设宽即可
- 阻尼非常小、相位在共振附近掉得很快时，把 `n_points` 加大。穿越位置由对分细化，不靠网格刚好踩中
- 负直流增益在 `w = 0` 处落在负实轴上。那个点不是有限频率穿越，表里不会把它算成 `w_pc = 0`
- PID 的微分是滤波后的，不是理想 `Kd s`。把 `kd_n` 加大会更接近理想微分
- 阶数上限是 8。示例都是合成系数，不能代替装置上的扫频

Python 与 MATLAB 的幅值、相位和裕度用同一组式子。自动网格的两端来自多项式求根，两种求根器在最后几位上可能不同，所以网格点不必逐点相同；穿越只要落在网格里面，对分之后的裕度是对齐的。

## FAQ

**一阶拐点为什么是 -3 dB、-45°？**  
`G(jw) = 1 / (1 + j tau w)`。`w = 1/tau` 时模是 `1/sqrt(2)`，`20 log10` 就是 `-10 log10(2)`；相角是 `-atan(1) = -45°`。

**为什么很多例子的增益裕度是无穷？**  
二阶对象和这里的 PID 开环，高频相位只是趋近 -180°，有限频率上到不了负实轴。增益裕度要读在相位穿越上，没有穿越就是无穷。`textbook` 那一条相对阶是 3，相位会穿过 -180°，增益裕度才是有限的 6.0206 dB。

**`w_gc` 和 `w_pc` 会不会写反？**  
表上的 `w_gc` 是算相位裕度用的增益穿越，`w_pc` 是算增益裕度用的相位穿越。结果结构里的全名是 `phase_margin_rad_s` 和 `gain_margin_rad_s`。

**有好几个穿越时报哪一个？**  
每一个都在 `gain_crossover_rad_s` 和 `phase_crossover_rad_s` 里。表上的 PM、GM 取最小的那一个，也就是先碰到稳定边界的那一个。

**需要工具箱吗？**  
不需要。不要调用 `bode`、`margin` 或 `tf`。Python 的 `scipy.signal.freqs` 与 MATLAB 的 `polyval` 是同一个多项式。

## License

MIT，见仓库 [LICENSE](../../LICENSE)。

## Teaching disclaimer

教学辅助用途：帮助对照传递函数和 Bode 裕度，结果不作为工程整定、投运或考核依据。请勿把学生姓名、学号、成绩或未授权的现场数据放进示例或提交到仓库。
