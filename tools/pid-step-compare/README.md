# PID 阶跃响应参数对比沙盒

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Compare PID step responses and basic transient metrics (Python + MATLAB).**

在同一个被控对象上叠几组 PID，直接看阶跃曲线和四个课堂指标：上升时间、超调百分比、调节时间、稳态误差。默认对象是两个相同的惯性环节 `G(s) = 1/(s+1)^2`（`wn = 1`，`zeta = 1`，`k = 1`）。示例只有 P、PI、PID 三组，比例增益相同，便于对照「加上积分」和「再加上微分」各改变了什么。示例参数是合成的，不含装置记录或学生信息。

两侧都用基础运算实现，Python 依赖 `numpy` 与 `matplotlib`，MATLAB 使用基础语言即可。控制器是并联 PID，微分带一阶滤波：

```text
C(s) = Kp + Ki/s + Kd * (kd_n * s) / (s + kd_n)
```

单位负反馈，零初值，固定步长 RK4。`kd_n` 就是 MATLAB `pid` 里的滤波系数 `N`，默认 10。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`、`matplotlib`（见仓库 `requirements.txt`）。本工具不调用 SciPy |
| MATLAB R2021b+ | 基础 MATLAB 即可，不需要 Control System Toolbox |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/pid-step-compare/examples/run_demo.py
```

脚本读取 `examples/data/plant.csv` 和 `examples/data/pid_sets.csv`，把图写到 `examples/output/pid_step_compare_demo.png`（该目录已 gitignore）。

在自己的脚本里调用：

```python
import sys
sys.path.insert(0, "tools/pid-step-compare/python")
from pid_step_compare import format_metrics_table, pid_step_compare

result = pid_step_compare(
    "tools/pid-step-compare/examples/data/plant.csv",
    "tools/pid-step-compare/examples/data/pid_sets.csv",
    t_final=20,
    dt=0.01,
    setpoint=1,
    output_png="tools/pid-step-compare/examples/output/pid_step_compare_demo.png",
)
print(format_metrics_table(result.metrics))
```

不传 `plant` 和 `pid_sets` 时，用的就是这两份示例里的默认对象和三组 PID。

### MATLAB

```matlab
cd('tools/pid-step-compare/matlab')
demo_pid_step_compare
```

或从仓库根目录：

```matlab
addpath('tools/pid-step-compare/matlab')
demo_pid_step_compare
```

图写到 `tools/pid-step-compare/examples/output/pid_step_compare_demo_matlab.png`。要在 IDE 里留住窗口，把 demo 中的 `'show', false` 改成 `'show', true`。

换一组参数可以直接传结构体：

```matlab
plant = struct('form', 'second_order', 'k', 1, 'wn', 1, 'zeta', 1);
pid_sets = repmat(struct('name', '', 'kp', 0, 'ki', 0, 'kd', 0), 1, 2);
pid_sets(1) = struct('name', 'P', 'kp', 1.5, 'ki', 0, 'kd', 0);
pid_sets(2) = struct('name', 'PI', 'kp', 1.5, 'ki', 0.8, 'kd', 0);
result = pid_step_compare(plant, pid_sets, 't_final', 20, 'dt', 0.01, 'show', true);
```

`pid_sets` 也可以是 `N×3` 的 `[kp ki kd]` 矩阵。

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。`plant`、`pid_sets` 是位置参数；MATLAB 里用 `[]` 表示「用默认」。

| Name | Default | Description |
|------|---------|-------------|
| `plant` | 见下表 | 结构体 / `dict`，或对象参数 CSV |
| `pid_sets` | P / PI / PID 三组 | 结构体数组、`dict` 列表、`N×3` 的 `[kp ki kd]`，或 PID CSV |
| `t_final` | `20` | 仿真时长，单位秒。时间网格是 `k*dt`，步数按 `round(t_final/dt)`（半数远离零取整） |
| `dt` | `0.01` | 固定步长，单位秒。需要盖住对象极点和 `kd_n`，经验上 `dt * 最快速率 < 2` |
| `setpoint` | `1` | 阶跃给定。`t = 0` 起为常数，初值为 0 |
| `kd_n` | `10` | 微分滤波系数 `N`。纯微分对应 `N → ∞`，步长会跟着变苛刻 |
| `settle_pct` | `2` | 调节时间带宽，取 `|y_final|` 的百分比。常用 2 或 5 |
| `output_png` | 不保存 | PNG 路径。父目录不存在时会创建。不保存且 `show` 为假时不画图 |
| `show` | `false` | 为真时留下图窗。Python demo 使用无界面后端，只保存文件 |

对象字段（`form` 决定用哪些数；其余字段仍会原样记在结果里）：

| Field | Default | Used by | Description |
|-------|---------|---------|-------------|
| `form` | `second_order` | 全部 | `second_order`、`fopdt` 或 `tf` |
| `k` | `1` | 前两种 | 增益。二阶对象是 `k*wn^2 / (s^2 + 2*zeta*wn*s + wn^2)`；FOPDT 是 `k*exp(-theta*s) / (tau*s + 1)` |
| `wn` | `1` | `second_order` | 自然频率，rad/s，必须为正 |
| `zeta` | `1` | `second_order` | 阻尼比，可为 0 或负数（不稳定对象） |
| `tau` | `1` | `fopdt` | 时间常数，秒，必须为正 |
| `theta` | `0` | 全部 | 输入纯滞后，秒。按 `round(theta/dt)` 个采样保持，负数会报错 |
| `num`, `den` | — | `tf` | 分子、分母系数，高次在前。必须严格真（分子次数更低），阶数 1 到 8 |

PID 每一组的字段是 `name`、`kp`、`ki`、`kd`。缺省 `name` 时按 P / PI / PD / PID 自动命名；重名会报错。`ki`、`kd` 缺省为 0。

## API

两侧返回同一组字段。`y`、`u` 的第 `i` 列对应 `names(i)` 和 `metrics(i)`（MATLAB 从 1 起，Python 从 0 起）。

| Field | Meaning |
|-------|---------|
| `time` | 时间向量，秒 |
| `y` | 输出。形状为「时间 × 组数」 |
| `u` | 控制量，同一形状 |
| `setpoint` | 阶跃给定 |
| `names` | 每组名字 |
| `metrics` | 每组一条记录，字段见下表 |
| `plant` | 规范化后的对象，含实际使用的 `num`、`den` |
| `t_final`, `dt`, `kd_n`, `settle_pct` | 本次仿真用的设置 |
| `output_png` | 写出的路径；未保存时 Python 为 `None`，MATLAB 为 `''` |
| `fig` | `show` 为真时的图窗；否则为空 |

`metrics` 字段：

| Field | Meaning |
|-------|---------|
| `name`, `kp`, `ki`, `kd` | 这一组的名字和增益 |
| `tr` | 上升时间：输出从终值的 10% 到 90% 的时间，线性插值。终值过小或没有跨过这两档时为 NaN |
| `mp_pct` | 超调百分比：`(峰值 - 终值) / |终值| * 100`。峰值取采样点上沿终值方向的极值；不超过终值时为 0 |
| `ts` | 调节时间：`|y - y_final|` 进入并保持在 `settle_pct` 带宽内的最后一次进入时刻。结束时仍在带外则为 NaN |
| `ess` | 稳态误差：`setpoint - y_final` |
| `y_final` | 记录最后 5% 采样的平均（至少 5 点），当作终值 |
| `y_peak`, `peak_time` | 峰值及其时刻 |
| `stable` | 全程有限，且末尾没有相对中点明显甩开。不稳定时图例加 `diverging` |

Python 另有 `format_metrics_table(metrics)`，demo 用它打表。MATLAB demo 用同样的列：`name kp ki kd tr Mp% ts ess`。

## Example output

默认对象 `G(s) = 1/(s+1)^2`，给定为 1，`t_final = 20`，`dt = 0.01`，`kd_n = 10`。三组增益来自 `examples/data/pid_sets.csv`：

```text
name                   kp       ki       kd       tr      Mp%       ts      ess
P                   2.000    0.000    0.000    1.040   10.845    3.404    0.333
PI                  2.000    1.500    0.000    1.094   19.394    5.812    0.000
PID                 2.000    1.500    0.800    1.417    6.063    5.053    0.000
```

可以顺着这张表讲三件事：

- **P**（`Kp = 2`）稳态停在约 `2/3`，误差约 `1/3`。对这个直流增益为 1 的对象，比例控制的静差就是 `1/(1+Kp)`。超调大约 11%，是相对它自己的终值，不是相对给定 1。
- **PI** 把 `Ki` 加上之后静差消失，超调升到约 19%，调节时间变长。
- **PID** 保持同一组 `Kp`、`Ki`，加上 `Kd = 0.8` 后超调降到约 6%，调节时间也比 PI 短；上升时间略增，因为阻尼更大。

图有上下两栏，坐标和标题都是英文。上栏是输出和给定（点线）；下栏是控制量。PID 在 `t = 0` 的控制量大约是 10：误差阶跃同时打进比例项 `Kp` 和滤波微分 `Kd*kd_n`，也就是 `2 + 0.8*10`。这是微分对误差的「踢」，不是对象先动了。颜色按组循环，线型按实线、虚线、点划线、点线循环，打印成灰度也能分开。

开环 `zeta = 1` 时对象本身没有超调，闭环里看到的超调来自反馈。把 `form` 改成 `fopdt` 可以换成带纯滞后的一阶对象；`form = 'tf'` 时直接给 `num`、`den`。

## Limitations

- 只做单输入单输出、单位负反馈、零初值的一次阶跃。没有饱和，也没有抗积分饱和
- 微分是滤波后的，不是理想 `Kd*s`。`kd_n` 越大，越接近理想微分，也越要求小步长
- 固定步长 RK4。对象极点或 `kd_n` 太快而 `dt` 太大时会直接报错；增益很高时闭环会比开环更快，仍可能需要再把 `dt` 改小
- 纯滞后取整到整数个采样，对象在这段时间里保持初值
- 传递函数必须严格真，阶数不超过 8。有直接项时比例和微分会形成代数环，这里不支持
- `y_final` 用的是记录末尾 5%。`t_final` 太短时，静差、超调和调节时间都会偏
- 示例曲线是选定的教学参数，不是整定结果，也不能代替装置上的调试

## FAQ

**比例控制为什么到不了给定？**  
默认对象直流增益是 1，闭环静差是 `1/(1+Kp*k)`。P 那一组 `Kp = 2`，所以停在约 0.667，`ess` 约 0.333。积分项不为 0 且闭环稳定时，阶跃静差会回到 0 附近。

**PID 的控制量为什么一上来就很大？**  
微分作用在误差上。`t = 0` 误差从 0 跳到给定，滤波微分的初值是 `Kd*kd_n*setpoint`。默认一组大约是 8，再加比例项 2。把 `kd_n` 减小，尖峰会变矮，滤波也更慢。

**上升时间为什么按终值而不是按给定？**  
按终值的 10%–90%，比例控制即使到不了 0.9 也有确定的上升时间。调节带宽同样相对 `|y_final|`。想改成 5% 带宽，把 `settle_pct` 设为 5。

**需要 Control System Toolbox 吗？**  
不需要。`tf`、`pid`、`step` 都没有调用。对象写成可控标准型，和 PID 的积分、滤波状态一起用 RK4 积分。Python 与 MATLAB 使用同一套公式。

**曲线发散或变成 NaN 怎么办？**  
先看图例里有没有 `diverging`。增益符号反了会不稳定；`dt` 相对极点太大时，函数会提示把步长减小到 `2 / 最快速率` 以下。记录里出现非有限数时，四个指标记为 NaN。

## Teaching disclaimer

教学辅助用途：帮助对照 PID 参数和阶跃指标，结果不作为工程整定、投运或考核依据。请勿把学生姓名、学号、成绩或未授权的现场数据放进示例或提交到仓库。
