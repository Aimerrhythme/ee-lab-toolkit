# 感应 / 直流电机转矩-转速曲线

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Torque-speed curves for a three-phase induction motor and a DC motor (Python + MATLAB).**

由三相感应电机的每相等效电路沿转差扫描转矩-转速曲线，给出起动转矩、最大转矩（breakdown）及其转差，以及额定运行点；直流电机覆盖他励、并励和串励，用来对比转子电阻、电压和磁场变化。默认例子是一组合成的课堂参数：380 V、50 Hz、4 极感应电机，以及 220 V 直流电机。数字不是某台电机的出厂数据，也没有学生信息。

`poles` 是极数，不是极对数。4 极、50 Hz 的同步转速是 1500 r/min。

感应电机（参数已折算到定子，星形或三角形）：

```text
n_sync = 120 * f / poles
omega_sync = 2 * pi * n_sync / 60
Zm = Rc || j Xm                 Rc 开路时忽略铁耗
Z2 = R2/s + j X2                s = 0 时转子支路开路
P_ag = 3 * |I2|^2 * R2 / s
T = P_ag / omega_sync
P_mech = (1 - s) * P_ag
```

转子端的戴维南等效（对这个电路是精确的）：

```text
Vth = Vph * Zm / (R1 + j X1 + Zm)
Zth = (R1 + j X1) || Zm
s_bd = R2 / sqrt(Rth^2 + (Xth + X2)^2)
T_bd = 3 / (2 * omega_sync) * |Vth|^2 / (Rth + sqrt(Rth^2 + (Xth + X2)^2))
```

最大转矩与 `R2` 无关，临界转差与 `R2` 成正比。同一转差下的转矩与相电压的平方成正比。这里的转矩是电磁转矩，机械功率是跨过气隙后的转换功率，没有摩擦、风阻和杂散损耗。

直流电机是稳态、不饱和、无电刷压降。`K_phi` 的单位是 V·s/rad，也就是 N·m/A。

```text
他励    omega = V / K_phi - (Ra / K_phi^2) * T
并励    K_phi = k_f * V / Rf，空载转速 = Rf / k_f，与 V 无关
串励    T = k_f * I^2
        omega = V / sqrt(k_f * T) - (Ra + Rs) / k_f
```

不饱和串励模型的空载转速是无穷大，所以串励曲线在 `i_min` 和 `i_max` 之间扫描，不从零转矩画起。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`、`matplotlib`（见仓库 `requirements.txt`）。等效电路和曲线只用 numpy，不调用 SciPy |
| MATLAB R2021b+ | 基础 MATLAB 即可，不需要工具箱。同一套 `.m` 也能在 GNU Octave 里算完并出图 |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/motor-torque-speed/examples/run_demo.py
```

脚本读取 `examples/data/motor_cases.csv` 的全部案例，把特征点表写到 `examples/output/motor_torque_speed_demo.csv`，把三张子图写到同名的 `.png`（该目录已 gitignore）。

在自己的脚本里调用：

```python
import sys
sys.path.insert(0, "tools/motor-torque-speed/python")
from motor_torque_speed import format_table, motor_torque_speed

result = motor_torque_speed(
    "tools/motor-torque-speed/examples/data/motor_cases.csv",
    output_png="tools/motor-torque-speed/examples/output/motor_torque_speed_demo.png",
    output_csv="tools/motor-torque-speed/examples/output/motor_torque_speed_demo.csv",
)
print(result.cases[0].torque_breakdown_nm, result.cases[0].slip_breakdown)
print(format_table(result))
```

不读 CSV 时，参数就是这一台电机。默认是下面的 380 V 感应电机：

```python
result = motor_torque_speed()
case = result.cases[0]
case.torque_start_nm, case.slip_breakdown, case.torque_breakdown_nm
```

只算一台直流他励电机，并标出 4 kW 的机械功率点：

```python
result = motor_torque_speed(motor="dc_separate", v=220, ra=1, k_phi=1.5, p_rated=4000)
```

多行 CSV 不写 `name` 时，每一行都算，画在同一张图里。写了 `name` 就只取那一行。

### MATLAB

```matlab
cd('tools/motor-torque-speed/matlab')
demo_motor_torque_speed
```

或从仓库根目录：

```matlab
addpath('tools/motor-torque-speed/matlab')
demo_motor_torque_speed
```

图写到 `tools/motor-torque-speed/examples/output/motor_torque_speed_demo_matlab.png`，表写到同名的 `.csv`。要在 IDE 里留住窗口，把 demo 中的 `'show', false` 改成 `'show', true`。

单台电机：

```matlab
result = motor_torque_speed('motor', 'dc_shunt', 'v', 180, 'p_rated', 4000);
result.cases(1).speed_noload_rpm
result.cases(1).torque_stall_nm
```

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。第一个位置参数是参数 CSV 的路径；不传就用下面的默认值。MATLAB 名值对不区分大小写。CSV 里写了的格子覆盖同名参数，空格子保留参数原值。用不到的参数留空即可；显式传入一台电机用不到的量会报错，避免把并励的 `k_phi` 和他励的磁场混在一起。

| Name | Default | Description |
|------|---------|-------------|
| `name` | 空 | 这一条的名字。读 CSV 时用来选中一行；留空则计算每一行 |
| `motor` | `induction` | `induction`（可写 `im`、`异步`）、`dc_separate`（`他励`）、`dc_shunt`（`并励`）、`dc_series`（`串励`） |
| `v` | 感应 380，直流 220 | 感应电机线电压，或直流机端电压，V |
| `f` | `50` | 定子频率，Hz。只用于感应电机 |
| `poles` | `4` | 极数，偶数，2 到 64。4 极不是 2 对极的另一种写法，同步转速用 `120*f/poles` |
| `connection` | `y` | `y`（`star`、`星形`）或 `d`（`delta`、`三角形`）。只用于感应电机 |
| `r1`, `x1` | `0.5`, `1.5` | 定子每相电阻、漏抗，Ω |
| `r2`, `x2` | `0.4`, `1.5` | 折算到定子的转子每相电阻、漏抗，Ω。`r2` 必须大于 0 |
| `xm` | `40` | 励磁电抗，Ω |
| `rc` | 开路 | 铁耗电阻，Ω。空或 `inf` 表示忽略铁耗 |
| `p_rated` | 空 | 额定机械功率，W。感应电机在稳定区（`s < min(s_bd, 1)`）里求对应转差；直流电机求高速侧的转矩 |
| `s_rated` | 空 | 直接指定感应电机额定转差。和 `p_rated` 同时给时以它为准 |
| `t_rated` | 空 | 直接指定直流电机额定转矩，N·m。和 `p_rated` 同时给时以它为准，且不能超过堵转转矩 |
| `ra` | 他励/并励 `1`，串励 `0.4` | 电枢电阻，Ω |
| `rf` | 并励 `220` | 并励磁场电阻，Ω |
| `rs` | 串励 `0.2` | 串励磁场电阻，Ω |
| `k_phi` | 他励 `1.5` | 他励磁通常数，V·s/rad |
| `k_f` | 并励 `1.5`，串励 `0.08` | 并励：`K_phi = k_f * V / Rf`。串励：`K_phi = k_f * I` |
| `i_min`, `i_max` | 串励堵转电流的 8% 和 45% | 串励电流扫描范围，A。`i_max` 不能超过堵转电流 `V/(Ra+Rs)` |
| `s_min`, `s_max` | `0`, `1` | 感应电机转差扫描。允许落到 `[-2, 3]`，用来看发电或能耗制动 |
| `n_points` | `401` | 曲线点数。感应电机可以是 1，此时 `s_min` 必须等于 `s_max`。直流至少 2 点。临界转差落在扫描区间内时会多插入 1 个点 |
| `csv_path` | 空 | 参数 CSV。和位置参数不要同时给 |
| `output_csv` | 不写 | 特征点表路径。父目录不存在时会创建 |
| `output_png` | 不保存 | 转矩-转速图。感应、直流他励/并励、串励分面板。Python demo 使用无界面后端 |
| `show` | `false` | 为真时留下图窗 |

参数 CSV（逗号或分号）建议列：

| Column | Required | Meaning |
|--------|----------|---------|
| `name` | 多行且要单选时必填 | 行名 |
| `motor` | 否 | 见上表。空着则用函数参数，默认 `induction` |
| `v`, `f`, `poles`, `connection` | 否 | 电压、频率、极数、接法 |
| `r1`, `x1`, `r2`, `x2`, `xm`, `rc` | 否 | 感应电机每相参数。`rc` 可写 `inf` |
| `p_rated`, `s_rated`, `t_rated` | 否 | 额定功率或额定点 |
| `ra`, `rf`, `rs`, `k_phi`, `k_f` | 否 | 直流电机参数 |
| `i_min`, `i_max`, `s_min`, `s_max`, `n_points` | 否 | 扫描范围和点数 |

`examples/data/motor_cases.csv` 是九条课堂参数，不是试验记录。

## API

两侧返回同一组字段。`result.cases` 是每台电机一条。MATLAB 里的曲线是列向量，Python 里是一维数组。不适用的标量是 NaN；串励的 `speed_noload_rpm` 是 `inf`。`efficiency_rated` 是分数 `P_mech / P_in`，不是百分数。

| Field | Meaning |
|-------|---------|
| `name`, `motor`, `connection` | 行名、电机种类、感应电机接法（直流为空） |
| `v`, `f`, `poles` | 电压、频率、极数 |
| `r1`, `x1`, `r2`, `x2`, `xm`, `rc` | 感应电机每相参数。忽略铁耗时 `rc` 为 inf |
| `n_sync_rpm`, `omega_sync_rad_s` | 同步转速，r/min 和 rad/s |
| `v_phase`, `v_th`, `r_th`, `x_th` | 相电压，以及转子端戴维南电压幅值和阻抗 |
| `torque_start_nm` | `s = 1` 的起动转矩 |
| `slip_breakdown`, `speed_breakdown_rpm`, `torque_breakdown_nm` | 电动状态最大转矩、对应转速和转差 |
| `s_rated`, `speed_rated_rpm`, `torque_rated_nm` | 额定点。没给 `p_rated` / `s_rated` / `t_rated` 时为 NaN |
| `i_line_rated_a`, `i2_rated_a` | 额定线电流，以及感应电机折算后的转子电流 |
| `power_mech_rated_w`, `power_in_rated_w`, `pf_rated`, `efficiency_rated` | 额定机械功率、输入功率、功率因数、效率 |
| `p_rated_w` | 调用时请求的机械功率；没请求则为 NaN |
| `ra`, `rf`, `rs`, `k_phi`, `k_f`, `i_field_a` | 直流参数。并励的 `k_phi` 由 `k_f` 和励磁电流算出来 |
| `speed_noload_rpm`, `torque_stall_nm`, `i_stall_a` | 空载转速、堵转转矩、堵转电流 |
| `i_min`, `i_max` | 串励电流扫描端点 |
| `s_min`, `s_max`, `n_points`, `n_samples` | 请求的扫描范围和点数，以及实际点数（可能比 `n_points` 多 1） |
| `slip`, `speed_rpm`, `speed_rad_s`, `torque_nm` | 曲线。直流的 `slip` 为 NaN |
| `i_line_a`, `i_phase_a`, `i2_a` | 线电流；感应电机定子相电流或直流电枢电流；折算转子电流 |
| `power_in_w`, `power_mech_w`, `power_factor`, `efficiency` | 曲线上每个点的功率、功率因数和效率。直流功率因数为 NaN |
| `summary` | 与 `format_table` 相同的文本。只在结果上，不在每一条 case 里 |
| `output_csv`, `output_png` | 写出的路径；未写时 Python 为 `None`，MATLAB 为 `''` |
| `fig` | `show` 为真时的图窗；否则为空 |

Python 另有 `format_table(result)`，demo 用它打表。MATLAB 的 `result.summary` 是同一段文字。

图上的标记：方块是起动点（`s = 1`），倒三角是最大转矩，圆点是额定点。

## Example output

`examples/data/motor_cases.csv` 的九条参数。感应电机三台都是 50 Hz、4 极、星形，`R1 = 0.5 Ω`，`X1 = X2 = 1.5 Ω`，`Xm = 40 Ω`，忽略铁耗。`im_base` 的 `R2 = 0.4 Ω`、线电压 380 V、额定机械功率 8 kW；`im_high_r2` 只把 `R2` 改成 1.2 Ω；`im_low_v` 只把线电压改成 304 V（0.8 倍），额定功率改成 5 kW。

直流他励：`Ra = 1 Ω`，`K_phi = 1.5`，额定机械功率 4 kW。对比是 180 V 电枢电压，以及 `K_phi = 1.2` 的弱磁。并励在 180 V 下取 `Rf = 220 Ω`、`k_f = 1.5`，所以 220 V 时会和他励基例重合，这里只保留降压后的差别。串励：`Ra = 0.4 Ω`，`Rs = 0.2 Ω`，`k_f = 0.08`，电流从 8 A 扫到 40 A，额定机械功率 2 kW，另外一条是 180 V。

```text
motor-torque-speed: name=im_base motor=induction T_start=36.1138 T_bd=123.6772 s_bd=0.133882 n_rated=1459.4038 T_rated=52.3463
motor-torque-speed: name=im_high_r2 motor=induction T_start=89.2503 T_bd=123.6772 s_bd=0.401647 n_rated=1368.8091 T_rated=55.8108
motor-torque-speed: name=im_low_v motor=induction T_start=23.1129 T_bd=79.1534 s_bd=0.133882 n_rated=1460.5285 T_rated=32.6912
motor-torque-speed: name=dc_separate motor=dc_separate n0=1400.5635 T_stall=330.0000 I_stall=220.0000
motor-torque-speed: name=dc_separate_low_v motor=dc_separate n0=1145.9156 T_stall=270.0000 I_stall=180.0000
motor-torque-speed: name=dc_separate_weak_field motor=dc_separate n0=1750.7044 T_stall=264.0000 I_stall=220.0000
motor-torque-speed: name=dc_shunt_low_v motor=dc_shunt n0=1400.5635 T_stall=220.9091 I_stall=180.0000
motor-torque-speed: name=dc_series motor=dc_series n0=inf T_stall=10755.5556 I_stall=366.6667
motor-torque-speed: name=dc_series_low_v motor=dc_series n0=inf T_stall=7200.0000 I_stall=300.0000
name=im_base  motor=induction  connection=y  V=380  f=50  poles=4  n_sync=1500  N=402
R1=0.5  X1=1.5  R2=0.4  X2=1.5  Xm=40  Rc=inf  Vph=219.393  Vth=211.448  Rth=0.464441  Xth=1.45138
T_start=36.1138  s_bd=0.133882  n_bd=1299.18  T_bd=123.677
rated  s=0.0270641  n=1459.4  T=52.3463  I_line=14.9978  I2=13.6179  P_mech=8000  P_in=8559.94  pf=0.86716  eta=93.4586%

name=im_high_r2  motor=induction  connection=y  V=380  f=50  poles=4  n_sync=1500  N=402
R1=0.5  X1=1.5  R2=1.2  X2=1.5  Xm=40  Rc=inf  Vph=219.393  Vth=211.448  Rth=0.464441  Xth=1.45138
T_start=89.2503  s_bd=0.401647  n_bd=897.53  T_bd=123.677
rated  s=0.0874606  n=1368.81  T=55.8108  I_line=15.9473  I2=14.594  P_mech=8000  P_in=9148.22  pf=0.871575  eta=87.4487%

name=im_low_v  motor=induction  connection=y  V=304  f=50  poles=4  n_sync=1500  N=402
R1=0.5  X1=1.5  R2=0.4  X2=1.5  Xm=40  Rc=inf  Vph=175.514  Vth=169.158  Rth=0.464441  Xth=1.45138
T_start=23.1129  s_bd=0.133882  n_bd=1299.18  T_bd=79.1534
rated  s=0.0263144  n=1460.53  T=32.6912  I_line=11.7249  I2=10.6116  P_mech=5000  P_in=5341.34  pf=0.865183  eta=93.6095%

name=dc_separate  motor=dc_separate  V=220  Ra=1  Kphi=1.5  N=401
n0=1400.56  T_stall=330  I_stall=220
rated  n=1273.24  T=30  I_line=20  P_mech=4000  P_in=4400  eta=90.9091%

name=dc_separate_low_v  motor=dc_separate  V=180  Ra=1  Kphi=1.5  N=401
n0=1145.92  T_stall=270  I_stall=180
rated  n=980.593  T=38.9531  I_line=25.9688  P_mech=4000  P_in=4674.38  eta=85.5729%

name=dc_separate_weak_field  motor=dc_separate  V=220  Ra=1  Kphi=1.2  N=401
n0=1750.7  T_stall=264  I_stall=220
rated  n=1591.55  T=24  I_line=20  P_mech=4000  P_in=4400  eta=90.9091%

name=dc_shunt_low_v  motor=dc_shunt  V=180  Ra=1  Rf=220  Kf=1.5  Kphi=1.22727  If=0.818182  N=401
n0=1400.56  T_stall=220.909  I_stall=180
rated  n=1198.5  T=31.8707  I_line=26.7869  P_mech=4000  P_in=4821.65  eta=82.9592%

name=dc_series  motor=dc_series  V=220  Ra=0.4  Rs=0.2  Kf=0.08  Imin=8  Imax=40  N=401
n0=inf  T_stall=10755.6  I_stall=366.667
rated  n=2743.55  T=6.96126  I_line=9.32822  P_mech=2000  P_in=2052.21  eta=97.4559%

name=dc_series_low_v  motor=dc_series  V=180  Ra=0.4  Rs=0.2  Kf=0.08  Imin=8  Imax=40  N=401
n0=inf  T_stall=7200  I_stall=300
rated  n=1787.62  T=10.6838  I_line=11.5563  P_mech=2000  P_in=2080.13  eta=96.1479%
```

可以顺着这张表讲六件事：

- **转子电阻不改变最大转矩。** `R2` 从 0.4 Ω 增到 1.2 Ω，`T_bd` 仍是 123.677 N·m，临界转差从 0.1339 增到 0.4016，正好三倍。起动转矩从 36.1 N·m 升到 89.3 N·m，最大转矩点从 1299 r/min 挪到 898 r/min。
- **转矩按电压平方变化。** 304 V 是 380 V 的 0.8 倍，`T_bd` 和起动转矩都变成 0.64 倍（79.15 N·m 和 23.11 N·m），临界转差不变。
- **他励降压和弱磁不是一回事。** 电枢电压改成 180 V，空载转速从 1401 r/min 降到 1146 r/min，堵转转矩从 330 N·m 降到 270 N·m。`K_phi` 从 1.5 降到 1.2，空载转速升到 1751 r/min，堵转转矩降到 264 N·m。
- **并励降压几乎不改变空载转速。** 180 V 并励的空载转速仍是 1401 r/min，堵转转矩按电压平方降到 220.9 N·m。同样 180 V 的他励堵转转矩是 270 N·m，因为磁场没有跟着电源一起减弱。
- **同样的机械功率，他励弱磁并不增加电枢铜耗。** 4 kW 在 220 V、`Ra = 1 Ω` 下的高速工作点电流只由电压和电枢电阻决定，基例和弱磁都是 20 A，效率都是 90.91%。弱磁把转矩从 30 N·m 降到 24 N·m，转速从 1273 r/min 升到 1592 r/min。
- **串励是一条双曲线，而且没有有限的空载转速。** 8 A 到 40 A 之间，220 V 的转速从约 3211 r/min 降到约 585 r/min。同一条 2 kW 功率，电压从 220 V 降到 180 V，转速从 2744 r/min 降到 1788 r/min。

图分三行，坐标和标题是英文。上图是感应电机，横轴转速、纵轴转矩，方块、倒三角和圆点分别是起动、最大转矩和额定点。中图是他励和并励的直线。下图是串励在有限电流范围内的一段，不画到堵转，否则堵转转矩会把纵轴撑到一万牛·米以外。

## Limitations

- 感应电机是正弦稳态等效电路。没有集肤效应、没有饱和、没有定子电阻随温度的变化，也没有谐波转矩
- 转矩是电磁转矩。铭牌上的轴输出还要再减去摩擦、风阻和杂散损耗，所以示例里 93% 的“效率”会高于同参数电机的铭牌效率
- 额定功率点取稳定区里机械功率等于 `p_rated` 的那个转差（`s` 较小的一侧）。功率超过稳定区里的最大转换功率时会报错，而不是悄悄交到不稳定区
- 直流模型不饱和、无电刷压降、无电枢反应。串励在小电流下的效率因此偏高，空载转速也是无穷大；真实串励机会饱和，仍然不允许空载起动
- 并励按长并励、无串励绕组处理：励磁跨在端电压上，`I_line = I_a + I_f`
- 他励的输入功率只算电枢。励磁电源单独供电，不进 `P_in`
- 只画电动状态的直流曲线。感应电机可以把 `s_min` 放到负数或把 `s_max` 放到 1 以上，分别看发电和反接
- 示例是合成参数，不能当作某台电机的出厂曲线或选型依据

## FAQ

**为什么最大转矩和转子电阻无关？**  
戴维南电路里，`dT/ds = 0` 的条件是 `R2/s = sqrt(Rth^2 + (Xth + X2)^2)`。代回转矩公式后 `R2` 消掉，只留在临界转差里。示例里两台电机的 `T_bd` 印出来是同一个数。

**`s_bd ≈ R2 / (X1 + X2)` 为什么对不上？**  
那是 `R1 = 0` 而且 `Xm` 很大时的近似。本工具用完整的戴维南阻抗。基例里 `Rth = 0.464 Ω`，`Xth = 1.451 Ω`，所以分母不是 `1.5 + 1.5`。

**星形和三角形差多少？**  
同一线电压下，三角形的相电压是星形的 `sqrt(3)` 倍，转矩按相电压平方，所以是 3 倍。参数仍然是每相值。

**并励降压后空载转速为什么几乎不动？**  
`K_phi` 正比于励磁电流，励磁电流正比于端电压，两者在 `omega = V / K_phi` 里约掉，空载转速变成 `Rf / k_f`。堵转转矩则按 `V^2` 下降。这是不饱和假设；饱和以后空载转速会跟着电压变。

**串励的堵转转矩为什么有一万牛·米？**  
不饱和时 `T = k_f * I^2`，堵转电流是 `V / (Ra + Rs) = 366.7 A`，转矩就是 `0.08 * 366.7^2`。真实磁路早饱和了，这条数只用来说明模型，不表示一台小电机真能发出这个转矩。图上故意停在 40 A。

**效率怎么算？**  
电动状态、`0 < s < 1` 时，`eta = P_mech / P_in`。直流他励在空载时输入和输出都是 0，效率无定义；并励空载仍有励磁损耗，效率是 0。功率因数只对感应电机有定义，电压为相位参考。

**需要工具箱吗？**  
不需要。Python 用复数除法；MATLAB 用 `1i`。两边的扫描、60 步二分和串励/他励的闭式额定点一致。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助对照感应电机等效电路和直流电机转矩-转速关系，结果不作为电机选型、起动校验或考核依据。请勿把学生姓名、学号、成绩或未公开的试验数据放进示例或提交到仓库。本工具随仓库以 MIT 许可证发布，见根目录 [LICENSE](../../LICENSE)。
