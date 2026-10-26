# 有名值与标幺值互算

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Convert SI (named) values and per-unit values on a shared power base (Python + MATLAB).**

给定基准容量和基准电压，算出基准电流、基准阻抗，再把电压、电流、功率和阻抗在有名值与标幺值之间换算。默认是一套课堂用的双绕组基准：三相 `S_base = 100 MVA`，高压侧线电压 `220 kV`，低压侧线电压 `110 kV`。同一套 `S_base` 下，阻抗按变比归算到另一侧之后，标幺值不变。示例数字是凑整的教学值，不是某台真实变压器的铭牌或试验数据。

三相（默认）里 `V_base` 是线电压，`S_base` 是三相功率：

```text
I_base = S_base / (sqrt(3) * V_base)
Z_base = V_base^2 / S_base
```

`Z_base` 也可以按「千伏、兆伏安」心算：`Z_ohm = V_kV^2 / S_MVA`。220 kV、100 MVA 得到 484 Ω；110 kV、100 MVA 得到 121 Ω。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | 换算只用标准库。保存柱状图时用 `matplotlib`（见仓库 `requirements.txt`）。不需要 numpy |
| MATLAB R2021b+ | 基础 MATLAB 即可，不需要工具箱 |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/pu-convert/examples/run_demo.py
```

脚本读取 `examples/data/synthetic_quantities.csv`，把表写到 `examples/output/pu_convert_demo.csv`，把标幺值柱状图写到 `examples/output/pu_convert_demo.png`（该目录已 gitignore）。

在自己的脚本里调用：

```python
import sys
sys.path.insert(0, "tools/pu-convert/python")
from pu_convert import format_table, pu_convert

bases = pu_convert()
print(bases.z_base_hv, bases.i_base_hv)  # 484 ohm, about 262.432 A

result = pu_convert(48.4, quantity="X", unit_hint="ohm", side="hv", refer_to="lv")
print(result.rows[0].value_pu, result.rows[0].value_si)  # 0.1 pu, 12.1 ohm on LV

batch = pu_convert(
    "tools/pu-convert/examples/data/synthetic_quantities.csv",
    output_csv="tools/pu-convert/examples/output/pu_convert_demo.csv",
    output_png="tools/pu-convert/examples/output/pu_convert_demo.png",
)
print(format_table(batch))
```

不传数值、也不传 CSV 时，只返回默认基准。`220e3` 这样的位置参数表示一条电压（单位 V），默认 `quantity='V'`、`direction='to_pu'`。

### MATLAB

```matlab
cd('tools/pu-convert/matlab')
demo_pu_convert
```

或从仓库根目录：

```matlab
addpath('tools/pu-convert/matlab')
demo_pu_convert
```

图写到 `tools/pu-convert/examples/output/pu_convert_demo_matlab.png`，表写到同目录的 `pu_convert_demo_matlab.csv`。要在 IDE 里留住窗口，把 demo 中的 `'show', false` 改成 `'show', true`。

单条换算：

```matlab
result = pu_convert(48.4, 'quantity', 'X', 'unit_hint', 'ohm', ...
    'side', 'hv', 'refer_to', 'lv');
result.rows(1).value_pu    % 0.1
result.rows(1).value_si    % 12.1 ohm，已归算到低压侧
result.z_base_hv           % 484
```

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。第一个位置参数可以是一个数值、一条 CSV 路径，或一行 / 多行 struct（MATLAB）与 dict（Python）。MATLAB 名值对不区分大小写。

| Name | Default | Description |
|------|---------|-------------|
| `value` | 不换算 | 一条有名值或标幺值。和 CSV 不要同时给 |
| `quantity` | `V` | `V` `I` `S` `P` `Q` `Z` `R` `X`。也接受 `voltage`、`current`、`impedance` 等英文全称 |
| `direction` | `to_pu` | `to_pu`：有名值 → 标幺值。`to_si`：标幺值 → 有名值 |
| `name` | 数量符号或 `rowN` | 这一行的名字。CSV 里空着时用 `row1`、`row2` |
| `unit_hint` | 空 | **输入**的单位。`to_pu` 时说明 `value` 的单位；空着表示已经是 V、A、VA/W/var 或 ohm。`to_si` 时只能空着或写 `pu` |
| `unit_out` | 基本 SI 单位 | 只在 `to_si` 时生效，指定输出单位，例如 `kV`、`MVA`、`ohm` |
| `side` | `same` | `same`、`hv` 或 `lv`。`V` / `I` / `Z` / `R` / `X` 用这一侧的基准。`same` 使用 `v_base`，没写 `v_base` 时用高压基准 |
| `refer_to` | 空 | 只对 `Z` / `R` / `X`。把欧姆值从 `side` 归算到 `hv` 或 `lv`，再按目的侧的 `Z_base` 取标幺值 |
| `s_base` | `100e6` | 基准容量，单位 VA。高低压共用这一个值 |
| `v_base` | 空 | `side='same'` 的线电压（或单相电压），单位 V。空着时等于 `v_base_hv` |
| `v_base_hv` | `220e3` | 高压侧电压基准，单位 V |
| `v_base_lv` | `110e3` | 低压侧电压基准，单位 V |
| `system` | `three_phase` | `three_phase`（可写 `3ph`）或 `single_phase`（可写 `1ph`）。单相时 `I_base = S_base / V_base`，`Z_base` 公式不变 |
| `csv_path` | 空 | 批量 CSV。列见下方 |
| `output_csv` | 不写 | 结果 CSV 路径。父目录不存在时会创建 |
| `output_png` | 不保存 | 标幺值横向柱状图。没有换算行时不能出图 |
| `show` | `false` | 为真时留下图窗。Python demo 使用无界面后端，只保存文件 |

`S`、`P`、`Q` 都除以同一个 `S_base`（1 W 和 1 var 在数值上按 1 VA 计）。`side` 不改变功率的基准。

`unit_hint` / `unit_out` 接受：`V` `kV`，`A` `kA`，`VA` `kVA` `MVA`，`W` `kW` `MW`，`var` `kvar` `Mvar`，`ohm`。按电力系统习惯，`mva` 和 `mvar` 表示兆，不是毫。`pu` 只表示「这个输入已经是标幺值」。

批量 CSV 建议列（合成数据，逗号或分号）：

| Column | Required | Meaning |
|--------|----------|---------|
| `name` | 否 | 行名 |
| `quantity` | 是 | `V` `I` `S` `P` `Q` `Z` `R` `X` |
| `value` | 是 | 数值 |
| `unit_hint` | 否 | 输入单位 |
| `direction` | 否 | `to_pu` 或 `to_si`，缺省用函数参数 |
| `side` | 否 | `hv` `lv` `same`，缺省用函数参数 |
| `refer_to` | 否 | 阻抗归算的目的侧 |
| `unit_out` | 否 | `to_si` 的输出单位 |

## API

两侧返回同一组字段。

| Field | Meaning |
|-------|---------|
| `s_base` | 本次使用的基准容量，VA |
| `system` | `three_phase` 或 `single_phase` |
| `v_base`, `i_base`, `z_base` | `side='same'` 的电压、电流、阻抗基准 |
| `v_base_hv`, `i_base_hv`, `z_base_hv` | 高压侧基准 |
| `v_base_lv`, `i_base_lv`, `z_base_lv` | 低压侧基准 |
| `rows` | 每条换算一行。没有输入数值时为空 |
| `output_csv`, `output_png` | 写出的路径；未写时 Python 为 `None`，MATLAB 为 `''` |
| `fig` | `show` 为真时的图窗；否则为空 |

`rows` 的每一行：

| Field | Meaning |
|-------|---------|
| `name`, `quantity`, `direction`, `side` | 这一行的名字、物理量、方向、源侧 |
| `refer_to` | 归算目的侧。没有归算时为空 |
| `winding` | `value_si` 所在的绕组。有 `refer_to` 时就是目的侧 |
| `value_in`, `unit_in` | 输入数字和它的单位。`to_si` 时单位是 `pu` |
| `value_pu` | 标幺值。`value_pu = value_si / base_used` |
| `value_si`, `si_unit` | 有名值，单位是 V、A、VA、W、var 或 ohm |
| `value_out`, `unit_out` | `direction` 所要的结果。`to_pu` 时就是标幺值 |
| `base_used` | 这一行用的基准（V、A、VA 或 ohm） |

Python 另有 `format_table(result)`，demo 用它打表。MATLAB demo 打印同样的列。

## Example output

默认基准，`examples/data/synthetic_quantities.csv`：

```text
system=three_phase  S_base=100000000 VA (100 MVA)
side       V_base_V     I_base_A   Z_base_ohm
same         220000      262.432          484
hv           220000      262.432          484
lv           110000      524.864          121

name               qty    dir  side refer     value_in  unit_in         pu     value_si si_unit    value_out unit_out
hv_rated_voltage     V  to_pu    hv     -          220       kV     1.0000       220000       V       1.0000       pu
hv_voltage_105       V  to_pu    hv     -          231       kV     1.0500       231000       V       1.0500       pu
lv_rated_voltage     V  to_pu    lv     -          110       kV     1.0000       110000       V       1.0000       pu
hv_current           I  to_si    hv     -            1       pu     1.0000      262.432       A      262.432        A
lv_current           I  to_si    lv     -            1       pu     1.0000      524.864       A      524.864        A
load_s               S  to_pu  same     -           80      MVA     0.8000     80000000      VA       0.8000       pu
load_p               P  to_pu  same     -           60       MW     0.6000     60000000       W       0.6000       pu
load_q               Q  to_pu  same     -           45     Mvar     0.4500     45000000     var       0.4500       pu
hv_reactance         X  to_pu    hv     -         48.4      ohm     0.1000         48.4     ohm       0.1000       pu
lv_reactance         X  to_pu    lv     -         12.1      ohm     0.1000         12.1     ohm       0.1000       pu
x_referred           X  to_pu    hv    lv         48.4      ohm     0.1000         12.1     ohm       0.1000       pu
hv_resistance        R  to_pu    hv     -         24.2      ohm     0.0500         24.2     ohm       0.0500       pu
x_to_si              Z  to_si    hv     -          0.1       pu     0.1000         48.4     ohm         48.4      ohm
hv_v_back            V  to_si    hv     -         1.05       pu     1.0500       231000       V          231       kV
```

可以顺着这张表讲四件事：

- **额定电压就是 1 pu。** 高压 220 kV、低压 110 kV 各自除以自己的 `V_base`。231 kV 是 1.05 pu，再换回去仍是 231 kV。
- **电流基准和电压成反比。** 低压线电压是高压的一半，所以 `I_base` 正好大一倍：262.432 A 和 524.864 A。1 pu 电流就是这一侧的 `I_base`。
- **功率只认 `S_base`。** 80 MVA、60 MW、45 Mvar 分别是 0.800、0.600、0.450 pu。有功、无功和视在功率用同一个分母。
- **归算不改变标幺阻抗。** 高压 48.4 Ω / 484 Ω = 0.1 pu。归到低压：`48.4 * (110/220)^2 = 12.1 Ω`，再除以 121 Ω 仍是 0.1 pu。`x_referred` 这一行把两步都留下了：输入 48.4 Ω，`value_si` 是低压侧的 12.1 Ω。

柱状图把每一行的标幺值画在同一根横轴上，颜色按 `V` / `I` / `S` / `P` / `Q` / `R` / `X` 区分，第一行在最上面。0.1 pu 的电抗和 1.05 pu 的电压可以并排看，但它们不是同一种量，读的时候要看行名。坐标和标题是英文。

## Limitations

- 高低压共用一个 `S_base`。系统容量变了，先在旧基准上 `to_si` 得到欧姆（或伏、安），再在新基准上 `to_pu`
- 只做有效值的幅值，不带相角，也不做波形
- 双绕组、一个变比。三绕组、分接头偏离基准电压时，把实际要用的电压直接写成 `v_base_hv` / `v_base_lv`，这里不另设抽头系数
- `refer_to` 只接受阻抗。电压和电流要换侧，请改 `side`
- `mva`、`mvar` 按兆处理，不是毫
- 示例是凑整的教学数字，不能当作设备参数或短路计算书

## FAQ

**为什么电流要除以 √3，阻抗却是 V²/S？**  
默认 `V_base` 是线电压，`S_base` 是三相功率，线电流基准是 `S_base / (√3 V_base)`。基准阻抗用的是相电压除以线电流：`Z_base = (V_base / √3) / I_base = V_base^2 / S_base`。单相实验把 `system` 设为 `single_phase`，电流基准改成 `S_base / V_base`，阻抗公式仍是 `V_base^2 / S_base`。

**48.4 Ω 和 12.1 Ω 为什么都是 0.1 pu？**  
两侧基准电压之比就是归算变比。欧姆值乘 `(V_低压 / V_高压)^2`，基准阻抗也乘同一个数，标幺值不动。这是「在自己的额定电压下取标幺值」和「先归算再取标幺值」结果相同的原因。

**有功、无功用哪一个基准？**  
用 `S_base`。60 MW / 100 MVA = 0.6 pu，45 Mvar / 100 MVA = 0.45 pu。负的无功会得到负的标幺值。

**标幺值是百分数吗？**  
不是。1 pu = 100%。表里的 1.05 表示 1.05 pu，也就是 105%。

**`to_si` 时 `unit_hint` 写成 kV 为什么会报错？**  
`unit_hint` 描述的是输入。`to_si` 的输入已经是标幺值，所以 `unit_hint` 留空或写 `pu`，输出单位写到 `unit_out`。例如 1.05 pu 要回到 kV：`unit_out='kV'`，得到 231。

**需要工具箱吗？**  
不需要。Python 换算不依赖 numpy；只有画柱状图时用 matplotlib。MATLAB 不调用任何工具箱。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助对照有名值和标幺值，结果不作为工程计算、整定或考核依据。请勿把学生姓名、学号、成绩或未公开的厂站数据放进示例或提交到仓库。
