# 短路容量/阻抗速算

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Short-circuit MVA, fault current, and impedance quick calculator (Python + MATLAB).**

用课堂里的短路容量法，在短路容量、短路电流和等值阻抗之间换算，并把电源、变压器、线路（以及电动机等并联贡献）折成一个等值。串联用容量的倒数相加，并联用容量直接相加，再给出考察点的三相短路电流。示例是凑整的 10 kV 教学数字，不是某座变电站的实测或设计资料。

## Formula

三相（默认）。`V` 是线电压，`S` 是三相短路容量，`I` 是三相金属性短路的线电流，`Z` 是折到这个电压下的一相等值阻抗。

```text
S = √3 · V · I = V² / |Z|
I = S / (√3 · V)
|Z| = V² / S
Z_pu = S_base / S = |Z| / Z_base
Z_base = V² / S_base
```

手算时用 kV 和 MVA，和上面是同一件事：

```text
S_MVA = V_kV² / Z_ohm
I_kA = S_MVA / (√3 · V_kV)
Z_ohm = V_kV² / S_MVA
Z_base_ohm = V_kV² / S_base_MVA
```

10 kV、100 MVA 的基准阻抗是 `10² / 100 = 1 Ω`。250 MVA 在这个电压下是 `10² / 250 = 0.4 Ω`，对应 `100 / 250 = 0.4 pu`。

单相去掉电流里的 √3：`I = S / V`。`|Z| = V² / S` 和 `Z_base` 不变。

变压器短路阻抗如果给在自身额定容量上：

```text
S_tx = S_rated / z_pu = S_rated · 100 / z_percent
```

`z_percent = 8` 表示 8%，不是 0.08。20 MVA、8% 的变压器，从无穷大系统看过去的短路容量是 `20 / 0.08 = 250 MVA`。

多段按表格从上到下、从左向右折叠。第一行是种子，它自己的 `combine` 只做检查，结果里记为 `seed`。

```text
series:    1/S_eq = 1/S_run + 1/S_next     （两段时 S_eq = S1·S2/(S1+S2)）
parallel:  S_eq = S_run + S_next
```

欧姆值都按考察电压 `v_kv` 理解。工具不把阻抗归算到另一侧绕组；线路若在别的电压等级，先自己归算，或直接填已经归算好的短路容量。

没写 `x_over_r` 时，这一段按纯电抗 `+j|Z|` 处理，这是容量法常用的假定。写了 `X/R`，或直接给了 `R` 和 `X` 时，程序同时用相量把阻抗串并联一遍：

```text
|Z| = V² / S
R = |Z| / √(1 + (X/R)²)
X = (X/R) · R
S_complex = V² / |Z_相量和|
```

各段 `X/R` 相同时，`S_complex` 和容量法的 `S_sc` 是同一个数。角度不同时，相量和的模小于模的和，`S_complex` 会大于 `S_sc`。表上的 `S_sc`、`I_sc`、`Z` 始终是容量法的结果。

Python 与 MATLAB 使用同一套式子、同一套参数名，并打印同一段 summary 文本。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | 计算只用标准库。保存容量图时用 `matplotlib`（见仓库 `requirements.txt`）。不需要 numpy |
| MATLAB R2021b+ | 基础 MATLAB 即可，不需要工具箱 |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/short-circuit-mva/examples/run_demo.py
```

脚本先算「250 MVA、10 kV」和「10 kA、10 kV」，再算一台 20 MVA、8% 的变压器，然后读 `examples/data/synthetic_short_circuit_stages.csv`。表写到 `examples/output/short_circuit_mva_demo.csv`，图写到 `examples/output/short_circuit_mva_demo.png`（该目录已 gitignore）。

在自己的脚本里调用：

```python
import sys
sys.path.insert(0, "tools/short-circuit-mva/python")
from short_circuit_mva import format_single_line, format_table, short_circuit_mva

point = short_circuit_mva(s_mva=250, v_kv=10)
print(format_single_line(point))
# short-circuit-mva single: S=250.0000 MVA  I=14.4338 kA  Z=0.4000 ohm  z_pu=0.4000 pu  X/R=inf

network = short_circuit_mva(
    "tools/short-circuit-mva/examples/data/synthetic_short_circuit_stages.csv",
    output_csv="tools/short-circuit-mva/examples/output/short_circuit_mva_demo.csv",
    output_png="tools/short-circuit-mva/examples/output/short_circuit_mva_demo.png",
)
print(format_table(network))
print(network.s_mva, network.i_ka)  # 150.0 MVA, 8.6603 kA
```

不读 CSV 时，用关键字描述一段。读 CSV、传入一组 dict，或只传一段的关键字，三者只取一种。

### MATLAB

```matlab
cd('tools/short-circuit-mva/matlab')
demo_short_circuit_mva
```

或从仓库根目录：

```matlab
addpath('tools/short-circuit-mva/matlab')
demo_short_circuit_mva
```

图写到 `tools/short-circuit-mva/examples/output/short_circuit_mva_demo_matlab.png`，表写到同目录的 `short_circuit_mva_demo_matlab.csv`。要在 IDE 里留住窗口，把 demo 中网络那次调用的 `'show', false` 改成 `'show', true`。

单点：

```matlab
point = short_circuit_mva('s_mva', 250, 'v_kv', 10);
point.i_ka          % 14.4338
point.z_ohm         % 0.4000
point.z_pu          % 0.4000，基准 100 MVA

tx = short_circuit_mva('kind', 'transformer', 's_rated_mva', 20, ...
    'z_percent', 8, 'x_over_r', 10, 'v_kv', 10);
tx.s_mva            % 250
tx.elements(1).z_spec_pu   % 0.08，在变压器自身容量上
```

多段用一个 struct 数组，或一个 cell。cell 不要求每个 struct 的字段完全一样：

```matlab
stages = { ...
    struct('name', 'grid', 's_mva', 500, 'x_over_r', 10), ...
    struct('name', 'tx', 's_rated_mva', 20, 'z_percent', 8, ...
        'combine', 'series', 'x_over_r', 10)};
part = short_circuit_mva(stages, 'v_kv', 10);
part.s_mva          % 166.6667
```

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。第一个位置参数可以是一条 CSV 路径、一个 struct / dict，或一组元件。MATLAB 名值对不区分大小写。

| Name | Default | Description |
|------|---------|-------------|
| `s_mva` | 空 | 这一段的三相短路容量，MVA。与 `s_va`、电流、阻抗、变压器参数不要同时给 |
| `s_va` | 空 | 同一容量，单位 VA |
| `i_ka` | 空 | 这一段单独存在时的短路电流，kA。需要 `v_kv` |
| `i_a` | 空 | 同一电流，单位 A。与 `i_ka` 不要同时给 |
| `z_ohm` | 空 | 阻抗模，Ω，已经在 `v_kv` 下。与 `r_ohm` / `x_ohm` 不要同时给 |
| `r_ohm` | 空 | 电阻，Ω。不能为负 |
| `x_ohm` | 空 | 电抗，Ω。可以为负，表示容性 |
| `z_pu` | 空 | 标幺阻抗。有 `s_rated_mva` 时在变压器自身容量上；否则在 `s_base_mva` 上。与 `z_percent` 不要同时给 |
| `z_percent` | 空 | 百分阻抗。`8` 表示 8%。基准规则与 `z_pu` 相同 |
| `s_rated_mva` | 空 | 变压器额定容量，MVA。有这一项时按变压器计算 `S = S_rated / z_pu` |
| `x_over_r` | 空 | `X/R`。空着表示纯正电抗。`0` 表示纯电阻。可以为负 |
| `name` | `element1`、`element2`… | 元件名 |
| `kind` | 按所给字段推断 | `source`、`current`、`impedance`、`line`（可写 `cable`）、`transformer`（可写 `tx`）、`pu`。必须和字段一致 |
| `combine` | `series` | 这一行相对当前等值如何合并：`series`（可写 `serial`）或 `parallel`（可写 `shunt`）。第一行结果里固定为 `seed` |
| `v_kv` | `10` | 考察点线电压，kV。单相时是两端电压。与 `v_v` 不要同时给 |
| `v_v` | 空 | 同一电压，单位 V |
| `s_base_mva` | `100` | 报告 `z_pu` 和 `Z_base` 用的基准容量，MVA。`pu` 类元件的 `z_pu` 也在这个基准上 |
| `system` | `three_phase` | `three_phase`（可写 `3ph`）或 `single_phase`（可写 `1ph`） |
| `csv_path` | 空 | 批量 CSV。列见下方 |
| `output_csv` | 不写 | 结果 CSV。父目录不存在时会创建 |
| `output_png` | 不保存 | 各元件容量（上）和折叠后的运行容量（下） |
| `show` | `false` | 为真时留下图窗。Python demo 使用无界面后端，只保存文件 |

批量 CSV 建议列（合成数据，逗号或分号，小数点用 `.`）：

| Column | Required | Meaning |
|--------|----------|---------|
| `name` 或 `element` | 否 | 元件名 |
| `kind` 或 `type` | 否 | 见上表。空着时按字段推断 |
| `combine` 或 `connection` | 否 | `series` 或 `parallel`。空着按串联 |
| `s_mva` 或 `s` | 与其他规格四选一 | 短路容量，MVA |
| `s_va` | 同上 | 短路容量，VA |
| `i_ka` 或 `i_a` / `i` | 同上 | 短路电流 |
| `z_ohm` 或 `z` | 同上 | 阻抗模，Ω。`line` / `cable` 用这一列 |
| `r_ohm`, `x_ohm` | 同上 | 也可写 `r`、`x` |
| `s_rated_mva` 或 `sn` | 变压器时必填 | 额定容量，MVA |
| `z_percent` 或 `uk` | 与 `z_pu` 二选一 | 百分阻抗，8 表示 8% |
| `z_pu` 或 `pu` | 与 `z_percent` 二选一 | 标幺阻抗 |
| `x_over_r` 或 `xr` | 否 | `X/R`。可以写 `inf` |

`v_kv`、`s_base_mva`、`system` 是函数参数，不是 CSV 列。

## API

两侧返回同一组字段。未写出文件时，Python 为 `None`，MATLAB 为 `''`。

| Field | Meaning |
|-------|---------|
| `method` | 固定为 `mva`。`S_sc` 来自容量法 |
| `system` | `three_phase` 或 `single_phase` |
| `v_v`, `v_kv` | 考察电压 |
| `s_base_va`, `s_base_mva` | 基准容量 |
| `z_base_ohm` | `V² / S_base` |
| `i_base_a`, `i_base_ka` | 基准电流 |
| `elements` | 每一段一行，顺序与输入相同 |
| `s_va`, `s_mva` | 容量法折完后的短路容量 |
| `i_a`, `i_ka` | `I_sc = S_sc / (√3 · V)`，单相没有 √3 |
| `z_ohm` | 容量法等值阻抗模，`V² / S_sc` |
| `z_pu` | `S_base / S_sc` |
| `r_ohm`, `x_ohm` | 相量折叠后的等值电阻、电抗 |
| `x_over_r` | 等值 `X/R`。纯电抗时为 `inf` 或 `-inf` |
| `angle_deg` | `atan2(X, R)`，度 |
| `z_complex_ohm` | 相量和的模 |
| `s_va_complex`, `s_mva_complex` | `V² / \|Z_相量\|` |
| `i_a_complex`, `i_ka_complex` | 与 `S_complex` 对应的电流 |
| `summary` | 与 `format_table` 相同的文本。MATLAB demo 打印这一段 |
| `output_csv`, `output_png` | 写出的路径 |
| `fig` | `show` 为真时的图窗；否则为空 |

`elements` 的每一行：

| Field | Meaning |
|-------|---------|
| `name`, `kind`, `combine` | 名字、种类、合并方式。第一行的 `combine` 是 `seed` |
| `s_mva`, `s_va` | 这一段自己的短路容量 |
| `z_ohm`, `r_ohm`, `x_ohm` | 折到 `v_kv` 的阻抗。变压器的欧姆值不是铭牌绕组电阻 |
| `x_over_r` | 这一段的 `X/R` |
| `z_pu` | 这一段在 `s_base_mva` 上的标幺阻抗，`S_base / S` |
| `z_spec_pu` | 输入里写过的标幺值。变压器是自身容量上的 `z_pu`；没写过则为 NaN |
| `s_rated_mva` | 变压器额定容量。不是变压器时为 NaN |
| `i_a`, `i_ka` | 只有这一段时的短路电流 |
| `s_running_mva` | 折叠到这一行之后的容量法短路容量 |
| `z_running_ohm` | `V² / S_running` |
| `i_running_a`, `i_running_ka` | 折叠到这一行之后的短路电流 |

Python 另有 `format_table(result)` 和 `format_single_line(result)`。后者只接受恰好一段的结果，demo 用它打单行。

## Example output

单点：`S = 250 MVA`，`V = 10 kV`，基准 `100 MVA`。没有给 `X/R`，按纯电抗。

```text
I_kA = 250 / (√3 · 10) = 14.4338
Z = 10² / 250 = 0.4000 Ω
z_pu = 100 / 250 = 0.4000
```

```text
short-circuit-mva single: S=250.0000 MVA  I=14.4338 kA  Z=0.4000 ohm  z_pu=0.4000 pu  X/R=inf
```

由电流反推：`I = 10 kA`，`V = 10 kV`。

```text
S_MVA = √3 · 10 · 10 = 173.2051
Z = 1/√3 = 0.5774 Ω
```

```text
short-circuit-mva single: S=173.2051 MVA  I=10.0000 kA  Z=0.5774 ohm  z_pu=0.5774 pu  X/R=inf
```

变压器：`S_rated = 20 MVA`，`z_percent = 8`，`X/R = 10`。容量和 250 MVA 的电源相同，角度不同。

```text
S = 20 / 0.08 = 250 MVA
short-circuit-mva single: S=250.0000 MVA  I=14.4338 kA  Z=0.4000 ohm  z_pu=0.4000 pu  X/R=10.0000
```

网络：`examples/data/synthetic_short_circuit_stages.csv`，10 kV，基准 100 MVA，四段的 `X/R` 都是 10。

| 元件 | 来源 | 本段 S |
|------|------|--------|
| grid | 直接给 500 MVA | 500 MVA，`Z = 10²/500 = 0.2 Ω` |
| tx | 20 MVA、8% | `20/0.08 = 250 MVA`，`Z = 0.4 Ω` |
| cable | 线路 `0.2 Ω` | `10²/0.2 = 500 MVA` |
| motor | 5 MVA、20%，并联在考察母线 | `5/0.20 = 25 MVA` |

折叠顺序是 `((grid series tx) series cable) parallel motor`：

```text
1/S = 1/500 + 1/250 + 1/500 = 0.008    →    125 MVA
S = 125 + 25 = 150 MVA
I_kA = 150 / (√3 · 10) = 8.6603
Z = 10² / 150 = 0.6667 Ω
z_pu = 100 / 150 = 0.6667
```

因为四段 `X/R` 相同，`S_complex` 也是 150.0000 MVA。角度是 `atan(10) = 84.2894°`。

```text
method=mva  system=three_phase  V=10.0000 kV  S_base=100.0000 MVA  Z_base=1.0000 ohm  I_base=5.7735 kA
element    kind         combine       S_MVA     Z_ohm      X/R   Srun_MVA   Irun_kA
grid       source       seed       500.0000    0.2000  10.0000   500.0000   28.8675
tx         transformer  series     250.0000    0.4000  10.0000   166.6667    9.6225
cable      line         series     500.0000    0.2000  10.0000   125.0000    7.2169
motor      transformer  parallel    25.0000    4.0000  10.0000   150.0000    8.6603
S_sc=150.0000 MVA  I_sc=8.6603 kA  Z=0.6667 ohm  z_pu=0.6667 pu  X/R=10.0000  angle=84.2894 deg  S_complex=150.0000 MVA  Z_complex=0.6667 ohm
```

`S_MVA` 是这一段自己的容量，`Srun_MVA` 才是折叠到这里的等值。`tx` 之后是 `500·250/(500+250) = 166.6667 MVA`。

上图是各元件自己的短路容量，颜色按种类区分：电源蓝、变压器红、线路绿。下图是每折叠一段之后的运行容量，点旁标了数值，红虚线是最终 `S_sc`。标题给出考察电压、`I_sc` 和容量法阻抗。坐标和标题是英文。

## Parity

- 函数名都是 `short_circuit_mva`；demo 为 `demo_short_circuit_mva.m` 与 `examples/run_demo.py`
- 参数名、CSV 列名、结果字段和 summary 文本一致
- 单点示例都打印 `S=250.0000 MVA  I=14.4338 kA  Z=0.4000 ohm`
- 10 kA 示例都打印 `S=173.2051 MVA  I=10.0000 kA`
- 网络示例都打印 `S_sc=150.0000 MVA  I_sc=8.6603 kA`，并且 `S_complex=150.0000 MVA`
- 示例 CSV 共用 `examples/data/synthetic_short_circuit_stages.csv`
- 出图都是元件容量加运行容量，不依赖工具箱

## Limitations

- 只做容量法（模）和同一电压下的 R、X 相量校核，不组装节点阻抗矩阵，也不算单相接地、两相短路或非周期分量
- 行的顺序就是折叠顺序。`(A 串联 B) 再并联 C` 和 `A 串联 (B 并联 C)` 不是同一个数。两条支路各自还有串联元件时，先把每条支路折成一个容量，再并列两行
- 欧姆和电流都在 `v_kv` 上。这里不会按变比把高压侧欧姆归算到低压侧
- 默认 `X/R` 为无穷大。角度不一致时，容量法把 `|Z|` 直接相加，会低估短路容量；这时看 `S_complex`
- `+X` 与 `−X` 在相量上完全抵消时，程序停止并说明原因，避免给出无穷大电流。容量法本身不会做这种抵消
- 电动机只当作一个恒定的并联短路容量，没有衰减曲线
- 电阻不能为负。电抗可以为负
- 示例容量、百分阻抗和线路欧姆都是凑整的教学数字，不能当作设备样本或工程计算书

## FAQ

**为什么串联用 1/S，并联用 S 相加？**  
同一基准下 `Z_pu = S_base / S_sc`。串联时标幺阻抗相加，所以短路容量的倒数相加，基准被约掉。并联时阻抗并联，容量直接相加。因此 0.2 pu 与 0.4 pu 串联就是 0.6 pu，对应 `S = 100/0.6 MVA`（基准 100 MVA）。

**变压器为什么是 `S_n / u_k%`？**  
百分阻抗定义在自身额定容量上：`z_pu = u_k% / 100 = S_n / S_sc`。所以 `S_sc = S_n / z_pu`。这是变压器接到无穷大母线时的穿越短路容量。

**`z_percent = 8` 和 `0.08` 有什么差别？**  
`8` 是 8%。若写成 `0.08`，程序会把它当成 0.08%，短路容量会大一百倍。标幺值请用 `z_pu=0.08`。

**线路欧姆要不要归算？**  
要。本工具把 `z_ohm`、`r_ohm`、`x_ohm` 都当作考察电压下的欧姆。高压侧的线路可以先乘 `(V_考察 / V_线路)²`，或直接填这一段的短路容量。

**`S_complex` 什么时候和 `S_sc` 不同？**  
容量法把阻抗的模相加，相量法把 `R+jX` 相加。各段 `X/R` 相同（或都没写，因而都是纯电抗）时两者一致。角度差得越多，真实的 `|Z|` 越小，短路电流越大。示例网络的 `X/R` 都是 10，所以两列都是 150.0000 MVA。

**第一行的 `combine` 为什么变成 `seed`？**  
折叠必须先有一个等值。第一行就是这个起点，它还没有「和前面的结果」合并。从第二行起，`series` 或 `parallel` 才作用在当前等值上。

**需要工具箱吗？**  
不需要。Python 计算不依赖 numpy；只有画图时用 matplotlib。MATLAB 不调用任何工具箱。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助对照短路容量法的手算步骤，结果不作为工程设计、开关选型或考核依据。请勿把学生姓名、学号、成绩或未公开的电网数据放进示例或提交到仓库。
