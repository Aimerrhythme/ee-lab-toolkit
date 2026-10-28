# PWM 调制波形生成与演示

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Sine-triangle PWM: bipolar and unipolar bridge waveforms (Python + MATLAB).**

用正弦调制波和三角载波做单相全桥的正弦-三角 PWM，画出调制波、载波、两桥臂上管门极和桥口电压，并核对线性区的基波峰值。默认例子是 50 Hz、调制度 0.8、载波比 21、直流母线 100 V，双极性和单极性各一条。数字是合成的，不是某台逆变器的录波，也没有学生信息。

载波峰值是 ±1，一个载波周期从 -1 起，到半周期为 +1：

```text
phase = mod(k, samples_per_carrier) / samples_per_carrier
carrier = 1 - 4 * abs(phase - 0.5)
m(t) = m_a * sin(2*pi*f_m*t + phase)
```

调制波大于或等于载波时，该桥臂上管导通（`gate = 1`），桥臂电位为 `+V_dc/2`；否则下管导通，桥臂电位为 `-V_dc/2`。相等时算上管导通。

双极性 `bipolar`：两桥臂始终互补，没有零电平。

```text
gate_b = 1 - gate_a
v_out = +V_dc 或 -V_dc
```

单极性 `unipolar`：A 桥臂看 `m(t)`，B 桥臂看 `-m(t)`。桥口电压是两桥臂之差。

```text
v_out ∈ {+V_dc, 0, -V_dc}
```

线性区（`m_a <= 1`）里，自然采样的基波峰值是教材上的那条：

```text
V_1 = m_a * V_dc
```

这里在均匀时间网格上比较，每个载波周期 `samples_per_carrier` 个点。示例取 200 点时，测到的基波和这条公式只差约 0.04%。`m_a > 1` 仍按同一条比较做，但进入过调制：有的脉冲会消失，公式不再成立，基波会低于 `m_a*V_dc`，并向方波的 `4*V_dc/π` 靠近。

THD 用整段波形的交流能量，不在谐波表的最后一行截断。直流先去掉。峰值比和有效值比是同一个数：

```text
THD = sqrt(Vrms_ac^2 - V1_rms^2) / V1_rms
```

记录里必须放进整数个载波周期，也就是 `m_f * cycles` 为整数。这样频谱落在基波的整数倍上。谐波表对每个整数次做相关：

```text
A*sin(h*2*pi*f_m*t + phi),   phi = atan2(b_cos, b_sin)
```

`t = 0` 在第一个采样点。`above_floor` 只表示这一行不低于 `amp_floor_ratio`，不参与 THD 的定义。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`、`matplotlib`（见仓库 `requirements.txt`）。比较、相关和 THD 只用 numpy，不调用 SciPy |
| MATLAB R2021b+ | 基础 MATLAB 即可。三角载波按上式写出，不需要 Signal Processing Toolbox |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/pwm-waveform/examples/run_demo.py
```

脚本读取 `examples/data/pwm_cases.csv` 里的 `bipolar_ma08` 和 `unipolar_ma08`，把谐波表写到 `examples/output/pwm_waveform_demo_<name>.csv`，把三张子图写到同名的 `.png`（该目录已 gitignore）。

在自己的脚本里调用：

```python
import sys
sys.path.insert(0, "tools/pwm-waveform/python")
from pwm_waveform import format_table, pwm_waveform

result = pwm_waveform(
    "tools/pwm-waveform/examples/data/pwm_cases.csv",
    name="unipolar_ma08",
    output_png="tools/pwm-waveform/examples/output/pwm_waveform_demo_unipolar_ma08.png",
    output_csv="tools/pwm-waveform/examples/output/pwm_waveform_demo_unipolar_ma08.csv",
)
print(result.fundamental_amplitude, result.fundamental_analytic, result.thd_percent)
print(format_table(result))
```

不读 CSV 时，参数就是这一条波形。默认就是上面的双极性例子：

```python
result = pwm_waveform(mode="bipolar", f_m=50, m_f=21, m_a=0.8, v_dc=100)
```

只给载波频率、不给载波比也可以。`f_c=1050`、`f_m=50` 得到 `m_f=21`。两个都给时，必须满足 `f_c = m_f * f_m`。

### MATLAB

```matlab
cd('tools/pwm-waveform/matlab')
demo_pwm_waveform
```

或从仓库根目录：

```matlab
addpath('tools/pwm-waveform/matlab')
demo_pwm_waveform
```

图写到 `tools/pwm-waveform/examples/output/pwm_waveform_demo_matlab_<name>.png`，表写到同名的 `.csv`。要在 IDE 里留住窗口，把 demo 中的 `'show', false` 改成 `'show', true`。

单条波形：

```matlab
result = pwm_waveform('mode', 'unipolar', 'm_a', 0.8, 'm_f', 21, 'v_dc', 100);
result.fundamental_amplitude    % 接近 80
result.thd_percent
result.harmonics(21).amplitude  % 单极性时载波次谐波应接近 0
```

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。第一个位置参数是参数 CSV 的路径；不传就用下面的默认值。MATLAB 名值对不区分大小写。CSV 里写了的格子覆盖同名参数，空格子保留参数原值。多行 CSV 必须用 `name` 指定一行。

| Name | Default | Description |
|------|---------|-------------|
| `name` | 空 | 这一条的名字。读多行 CSV 时用来选行 |
| `mode` | `bipolar` | `bipolar`（可写 `bi`、`双极性`）或 `unipolar`（可写 `uni`、`单极性`） |
| `f_m` | `50` | 调制波频率，Hz |
| `f_c` | 空 | 载波频率，Hz。空着时由 `m_f * f_m` 得到 |
| `m_f` | `21` | 载波比 `f_c / f_m`。`f_c` 和 `m_f` 都空时用 21。`m_f * cycles` 必须是整数，且 `m_f >= 1` |
| `m_a` | `0.8` | 调制度，调制波峰值 / 载波峰值。范围 0 到 10。`<= 1` 为线性区 |
| `v_dc` | `100` | 直流母线电压，V。桥口在线性区的基波峰值目标是 `m_a * v_dc` |
| `phase_deg` | `0` | 调制波相位，度。正弦零点在 `t = 0` |
| `cycles` | `2` | 仿真包含的调制波周期数，整数 1 到 50 |
| `samples_per_carrier` | `200` | 每个载波周期的采样点数，整数 8 到 20000。总点数还不能超过 2e6 |
| `n_harmonics` | 自动 | 谐波表最高次数。自动值覆盖到约 `2*m_f + 4`，且不超过 150，高于奈奎斯特的次数会丢掉 |
| `amp_floor_ratio` | `0.01` | 不低于 `amp_floor_ratio * V_1` 的次数（从 2 次起）把 `above_floor` 标为 1。不改变 `thd` |
| `csv_path` | 空 | 参数 CSV。列见下方。和位置参数不要同时给 |
| `output_csv` | 不写 | 谐波表路径。父目录不存在时会创建 |
| `output_png` | 不保存 | 上图调制波与载波，中图门极，下图桥口电压。Python demo 使用无界面后端 |
| `show` | `false` | 为真时留下图窗 |

参数 CSV（逗号或分号）建议列：

| Column | Required | Meaning |
|--------|----------|---------|
| `name` | 多行时必填 | 行名，给 `name=` 用来选中这一行 |
| `mode` | 否 | `bipolar` 或 `unipolar` |
| `f_m`, `f_c`, `m_f` | 否 | 频率和载波比。`f_c` 可以空着 |
| `m_a`, `v_dc`, `phase_deg` | 否 | 调制度、直流母线、相位 |
| `cycles`, `samples_per_carrier` | 否 | 周期数和每载波点数 |
| `n_harmonics`, `amp_floor_ratio` | 否 | 谐波表长度和门槛 |

`examples/data/pwm_cases.csv` 是两条课堂参数，不是波形采样。

## API

两侧返回同一组字段。MATLAB 里的波形和时间是列向量，Python 里是一维数组。

| Field | Meaning |
|-------|---------|
| `name`, `mode` | 行名，以及实际使用的 `bipolar` 或 `unipolar` |
| `f_m`, `f_c`, `m_f` | 调制频率、载波频率、载波比。记录长度取整后，三者仍满足 `f_c = m_f * f_m` |
| `m_a`, `v_dc`, `phase_deg`, `phase_rad` | 调制度、直流母线、相位 |
| `cycles`, `samples_per_carrier`, `fs`, `n_samples`, `n_carrier` | 调制波周期数、每载波点数、采样率、总点数、载波周期数 |
| `linear_range` | `m_a <= 1` 时为真。为真时 `V_1 = m_a * V_dc` 才是对照公式 |
| `n_pulses_a`, `n_pulses_b` | 两条上管门极的脉冲个数（含从末点绕回首点的上升沿） |
| `dc` | 桥口电压的平均值 |
| `fundamental_amplitude`, `fundamental_rms` | 测到的基波峰值，以及峰值 `/ sqrt(2)` |
| `fundamental_phase_rad`, `fundamental_phase_deg` | 基波相位，约定同 `A*sin(wt + phi)` |
| `fundamental_analytic` | `m_a * v_dc`。过调制时它只是线性公式，不是预测值 |
| `fundamental_error`, `fundamental_error_percent` | 测量值减公式。公式为 0 时百分误差无定义 |
| `signal_rms` | 去掉直流后的桥口电压有效值 |
| `thd`, `thd_percent` | 全频带 THD。基波峰值近于 0 时为 NaN，文本里印 `undefined` |
| `n_harmonics`, `amp_floor_ratio` | 谐波表次数上限，以及门槛 |
| `harmonics` | 从 1 次排到实际列出的最高次 |
| `time`, `modulation`, `carrier` | 时间、调制波（峰值 `m_a`）、载波（峰值 1） |
| `gate_a`, `gate_b` | 上管门极，1 或 0 |
| `v_out`, `v_ref` | 桥口电压，以及 `m_a*V_dc*sin(...)` |
| `output_csv`, `output_png` | 写出的路径；未写时 Python 为 `None`，MATLAB 为 `''` |
| `fig` | `show` 为真时的图窗；否则为空 |

`harmonics` 的每一行：

| Field | Meaning |
|-------|---------|
| `order`, `frequency_hz` | 次数，以及 `order * f_m` |
| `amplitude`, `rms` | 该次正弦的峰值和有效值 |
| `percent` | `100 * amplitude / V_1`。基波这一行是 100。基波近于 0 时为 NaN |
| `phase_rad`, `phase_deg` | 相位。幅值小到可以忽略时相位记 0 |
| `above_floor` | 次数 ≥ 2 且幅值不低于门槛。基波恒为假。它不决定 `thd` |

Python 另有 `format_table(result)`，demo 用它打表。MATLAB demo 打印同样的列。

## Example output

`examples/data/pwm_cases.csv` 的两条参数相同，只是 `mode` 不同：`f_m = 50` Hz，`m_f = 21`（`f_c = 1050` Hz），`m_a = 0.8`，`v_dc = 100` V，`phase_deg = 0`，`cycles = 2`，每个载波周期 200 点。`N = 8400`，`fs = 210000` Hz。线性公式给出的基波峰值是 `0.8 * 100 = 80` V。

双极性：

```text
pwm-waveform: name=bipolar_ma08 mode=bipolar m_a=0.8 m_f=21 V1=79.9658 V1_analytic=80.0000 THD=145.8655%
name=bipolar_ma08  mode=bipolar  f_m=50 Hz  f_c=1050 Hz  m_f=21  m_a=0.8  Vdc=100  phase_deg=0
fs=210000 Hz  N=8400  cycles=2  samples_per_carrier=200  linear=1  pulses_a=42  pulses_b=42
dc=0  V1=79.9658  V1_analytic=80  err=-0.0428%  THD=145.8655%  floor=0.01
```

单极性：

```text
pwm-waveform: name=unipolar_ma08 mode=unipolar m_a=0.8 m_f=21 V1=79.9641 V1_analytic=80.0000 THD=77.1481%
name=unipolar_ma08  mode=unipolar  f_m=50 Hz  f_c=1050 Hz  m_f=21  m_a=0.8  Vdc=100  phase_deg=0
fs=210000 Hz  N=8400  cycles=2  samples_per_carrier=200  linear=1  pulses_a=42  pulses_b=42
dc=0  V1=79.9641  V1_analytic=80  err=-0.0449%  THD=77.1481%  floor=0.01
```

Demo 会把 1 次到 46 次都打出来。偶次在这组参数下是 0.0000。下面只摘 `above_floor = 1` 的行，也就是不低于基波 1% 的次数。

双极性（载波次很大）：

```text
order   frequency_Hz    amplitude          rms    percent  phase_deg  above_floor
   17       850.0000       1.1719       0.8287     1.4655     95.424            1
   19       950.0000      21.8960      15.4828    27.3818     89.171            1
   21      1050.0000      81.8199      57.8554   102.3186     90.225            1
   23      1150.0000      21.7280      15.3640    27.1716     91.371            1
   25      1250.0000       0.8766       0.6199     1.0963     72.851            1
   37      1850.0000       1.6406       1.1601     2.0517      5.044            1
   39      1950.0000      13.7722       9.7384    17.2227     -0.572            1
   41      2050.0000      31.4552      22.2422    39.3359      0.291            1
   43      2150.0000      31.6684      22.3930    39.6025   -179.424            1
   45      2250.0000      13.9359       9.8542    17.4274   -177.644            1
```

单极性（21 次只剩 0.40%，不进上面这个门槛；能量在 2 倍载波附近）：

```text
order   frequency_Hz    amplitude          rms    percent  phase_deg  above_floor
   21      1050.0000       0.3218       0.2276     0.4025   -180.000            0
   37      1850.0000       1.6343       1.1556     2.0438      0.000            1
   39      1950.0000      13.7716       9.7380    17.2222      0.000            1
   41      2050.0000      31.4548      22.2419    39.3362      0.000            1
   43      2150.0000      31.6668      22.3918    39.6013   -180.000            1
   45      2250.0000      13.9241       9.8459    17.4130   -180.000            1
```

可以顺着这张表讲四件事：

- **线性区基波就是 `m_a * V_dc`。** 80 V 的公式值，网格比较得到 79.97 V 左右，相对差约 -0.04%。3 次只有 0.5% 上下，是离散比较留下的，不是一条新的低次谐波。
- **双极性的 THD 可以超过 100%。** 输出始终是 ±100 V，有效值就是 100 V，基波有效值只有约 56.5 V，剩下的都在开关谐波里。这不是滤波器后的电流 THD。
- **单极性把载波次消掉。** 21 次从基波的 102% 降到 0.40%。桥口多了 0 电平，有效值降到约 71.41 V，THD 从 145.87% 降到 77.15%。大的边带改在 39–45 次，也就是 `2*m_f` 附近。
- **奇数载波比、相位 0 时偶次抵消。** `m_f = 21`，2、4、6… 次幅值印出来是 0。每个载波周期一个脉冲，两条记录都是 42 个脉冲（21 × 2 个调制周期）。

图分三行，坐标和标题是英文。上图是调制波和三角载波，两个 50 Hz 周期里能数出 21 个三角波。中图是两条上管门极；`gate_b` 向上平移 1.35，避免和 `gate_a` 叠在一起。双极性两条门极互补，单极性一条跟着正弦、一条跟着反相正弦。下图是桥口电压和红色虚线 `m_a*Vdc*sin`。双极性只有 ±100 V，单极性在过零附近出现 0 V 的平台。文本框写 `V1`、公式值和 THD。记录比 2 个调制周期更长时，图只画前 2 个周期，谐波仍用整段。

## Limitations

- 单相全桥。没有空间矢量、没有三次谐波注入、没有死区、没有管压降，直流母线也当成理想电压源
- 在采样点上比较，不是连续时间的自然采样闭式解。`samples_per_carrier` 小的时候，基波和 80 V 会差得更明显
- `m_f * cycles` 必须是整数。载波比不是整数时，把 `cycles` 选成能凑满整数个载波周期的值，例如 `m_f = 21.5`、`cycles = 2`
- `m_a > 1` 时仍会出波形，但 `fundamental_analytic` 不再是基波的预测值
- THD 含载波及其边带。LC 滤波器后的电流畸变要另算，本工具不代滤波
- 基波峰值近于 0（例如 `m_a = 0`）时 THD 无定义。双极性这时仍是 ±V_dc 的载波方波；单极性两桥臂动作相同，桥口电压为 0
- 半桥如果输出只有 ±V_dc/2，把这里的 `v_dc` 理解成直流母线的一半，或者把算出来的电压再除以 2
- 示例是合成参数，不能当作某台装置的调制结果或并网谐波报告

## FAQ

**为什么双极性 THD 有 146%？**  
桥口电压的有效值是 `V_dc`，基波有效值大约是 `0.8 * V_dc / √2`。THD 的分母是基波，分子是其余所有交流分量，载波边带比基波还大，所以百分数超过 100。要看“低频像不像正弦”，去读 3、5、7 次那几行，不要只看这一个 THD。

**79.97 V 和 80 V 为什么不完全一样？**  
80 V 是连续时间自然采样的公式。本工具每个载波周期只比 200 次，脉冲沿落在采样点上，基波会偏零点几个百分点。把 `samples_per_carrier` 加大，差会再小一点。

**单极性为什么能消掉 21 次？**  
两个桥臂的参考波反相，载波相同。桥口电压是两者之差，奇数倍载波附近的共模分量互相抵消，剩下的开关谐波集中在偶数倍载波附近。示例里 21 次约 0.40%，41 次和 43 次各约 39%。

**`above_floor` 是不是已经加进 THD 了？**  
不是。`thd` 用时域有效值减掉基波，谐波表以外的次数也算在里面。`above_floor` 只是把不低于 1%（默认）的行标出来，方便在长表里找边带。

**过调制怎么看？**  
`m_a = 1.2`、其余参数同示例时，`linear_range` 为假，脉冲从 42 个减到 26 个，测到的基波约 110.4 V，低于公式值 120 V，仍低于方波极限 `4*100/π ≈ 127.3` V。图上的虚线会超出 ±V_dc，文本框会多写一行 `overmodulation`。

**需要工具箱吗？**  
不需要。Python 用 numpy 的正弦和点积；MATLAB 用 `sin`、`sum` 和 `stairs`。两边的三角载波都是 `1 - 4*abs(phase - 0.5)`。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助对照正弦-三角 PWM 的门极、桥口电压和线性区基波，结果不作为装置调试、谐波合格判定或考核依据。请勿把学生姓名、学号、成绩或未公开的录波放进示例或提交到仓库。本工具随仓库以 MIT 许可证发布，见根目录 [LICENSE](../../LICENSE)。
