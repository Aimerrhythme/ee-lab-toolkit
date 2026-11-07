# pandapower 短路样本合成与标签导出

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Short-circuit sample synthesis with protection labels (Python + MATLAB).**

在一条简易放射状中压馈线上，按母线、故障类型和过渡电阻批量做短路计算，把相电压、相电流和保护术语标签写成 CSV，给后面的分类实验当输入。默认引擎两边相同。Python 还可以改用 pandapower 里的 CIGRE MV 网络，导出的列不变。示例阻抗是凑整的教学数字，不是某条线路的实测或设计资料。

## Formula

故障前电压取 1.0 pu，不计负荷电流。负序阻抗等于正序阻抗。`E` 是故障前相电压，`Z1`、`Z0` 是故障母线的正序、零序驱动点阻抗，`R_f` 是故障点的过渡电阻，单位 Ω。

```text
ABC:  I1 = E / (Z1 + R_f)                         三相电流幅值都是 |I1|
AG:   I1 = I2 = I0 = E / (Z1 + Z2 + Z0 + 3 R_f)   Ia = 3 I1，Ib = Ic = 0
BC:   I1 = -I2 = E / (Z1 + Z2 + R_f)              Ia = 0，|Ib| = |Ic| = √3 |I1|
```

单相接地的 `3 R_f` 接在三个序网串联之后。两相短路的 `R_f` 是两相之间的那一个电阻，接在正序和负序之间。三相短路的 `R_f` 是每相到故障点的电阻。

BG、CG 把 AG 的三相模式轮换一次、两次。AB、CA 把 BC 的模式轮换，使健全相落到 C 或 B。`label_protect` 只保留保护分类用的三类：

| fault_type | fault_type_code | label_protect | 现场说法 |
|------------|-----------------|---------------|----------|
| AG, BG, CG | 1, 2, 3 | `phase-to-ground` | 单相接地 |
| AB, BC, CA | 4, 5, 6 | `phase-to-phase` | 相间短路 |
| ABC | 7 | `three-phase` | 三相短路 |

`fault_type` 是细标签，能区分哪一相。`label_protect` 是粗标签，对应保护里的接地、相间、三相。

默认馈线是 10 kV、基准 10 MVA。电源 `|Z1| = 0.4 Ω`、`X/R = 10`，零序是正序的 1.5 倍，角度相同。这 0.4 Ω 就是 250 MVA：`S = 10² / 0.4`。四段线路的零序电阻、电抗是正序的 3 倍，写在示例 CSV 里。

电源母线 `B0`、金属性故障：

```text
I_ABC = 10000 / (√3 · 0.4) = 14433.7567 A
I_BC  = 10000 / 0.8 = 12500 A          Va = 1 pu，Vb = Vc = 0.5 pu
I_AG  = 6/7 · I_ABC = 12371.7915 A     Va = 0，|Vb| = |Vc| = √57 / 7 = 1.0785 pu
```

`B0` 上 `Z0` 和 `Z1` 同角度，所以 AG 的两个健全相电压相等，而且高于 1 pu。离开电源以后，线路阻抗角和电源不一样，`Z0` 不再是 `Z1` 的实数倍，健全相电压会分开。金属性接地时故障相电压仍是 0，非故障相电流仍是 0。分类可以先看哪一相有电流。

Python 与 MATLAB 的 `zbus` 引擎使用同一套式子、同一套参数名，并打印同一段 summary。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`、`pandas`、`matplotlib`（见仓库 `requirements.txt`）。放射状馈线不需要 pandapower |
| pandapower | 可选。`pip install pandapower` 之后才能用 `engine="pandapower"` 或让 `engine="auto"` 走到 CIGRE-MV。不写入仓库的 `requirements.txt` |
| MATLAB R2021b+ | 基础 MATLAB。没有 pandapower，只做同一条放射状馈线 |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/pp-fault-synth-export/examples/run_demo.py
```

脚本用 `engine="zbus"` 读 `examples/data/synthetic_radial_feeder.csv`，扫 5 个母线、7 种故障、3 个过渡电阻，共 105 行。表写到 `examples/output/pp_fault_synth_export_demo.csv`，图写到 `examples/output/pp_fault_synth_export_demo.png`（该目录已 gitignore）。

```python
import sys
sys.path.insert(0, "tools/pp-fault-synth-export/python")
from pp_fault_synth_export import format_preview, format_table, pp_fault_synth_export

result = pp_fault_synth_export(
    "tools/pp-fault-synth-export/examples/data/synthetic_radial_feeder.csv",
    engine="zbus",
    output_csv="tools/pp-fault-synth-export/examples/output/pp_fault_synth_export_demo.csv",
    output_png="tools/pp-fault-synth-export/examples/output/pp_fault_synth_export_demo.png",
)
print(format_preview(result))
print(result.frame.head())
```

已安装 pandapower 时，同一组列可以改到 CIGRE MV：

```python
cigre = pp_fault_synth_export(engine="pandapower")          # network 默认 cigre_mv
same = pp_fault_synth_export(engine="pandapower", network="radial")  # 与 zbus 同一条馈线
```

`engine="auto"` 在能导入 pandapower 时走 CIGRE-MV，否则走放射状 `zbus`。课堂对照 MATLAB 时请显式写 `engine="zbus"`。

### MATLAB

```matlab
cd('tools/pp-fault-synth-export/matlab')
demo_pp_fault_synth_export
```

或从仓库根目录：

```matlab
addpath('tools/pp-fault-synth-export/matlab')
demo_pp_fault_synth_export
```

图写到 `tools/pp-fault-synth-export/examples/output/pp_fault_synth_export_demo_matlab.png`，表写到同目录的 `pp_fault_synth_export_demo_matlab.csv`。要在 IDE 里留住窗口，把 demo 里的 `'show', false` 改成 `'show', true`。

```matlab
result = pp_fault_synth_export('engine', 'zbus', 'seed', 42);
result.samples(1).fault_type    % AG
result.preview
```

MATLAB 里 `'engine', 'auto'` 也是这条放射状馈线。`'engine', 'pandapower'` 会说明 CIGRE-MV 只在 Python 里。

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。第一个位置参数是馈线 CSV。省略时用内置的 10 kV 四段馈线，数字与示例 CSV 相同。MATLAB 名值对不区分大小写。

| Name | Default | Description |
|------|---------|-------------|
| `v_kv` | `10` | 放射状馈线的线电压，kV。pandapower 引擎改用网络里每个母线的 `vn_kv` |
| `s_base_mva` | `10` | 基准容量，MVA。用来算 `I_fault_mag_pu` 和表头的 `Z_base`、`I_base` |
| `fault_types` | 七种全要 | `AG` `BG` `CG` `AB` `BC` `CA` `ABC`。`1ph` 表示 AG，`2ph` 表示 BC，`3ph` 表示 ABC |
| `r_fault_ohm` | `0, 1, 5` | 过渡电阻，Ω。可以是一个数或一组数。不能为负 |
| `buses` | 全部母线 | 只保留这些 `bus_id` |
| `n_samples` | 全网格 | 小于全网格时，用下面的种子做可重复抽样 |
| `seed` | `42` | 抽样种子。全网格时不改变顺序，仍写进 summary |
| `engine` | `zbus` | `zbus`、`pandapower` 或 `auto`。MATLAB 只有 `zbus` |
| `network` | 见引擎 | `radial` 或 `cigre_mv`。`cigre_mv` 需要 Python 的 pandapower |
| `z0_source_factor` | `1.5` | 电源零序 / 正序。CSV 里写了 `z0_factor` 或 `r0/x0` 时以 CSV 为准 |
| `z0_line_factor` | `3` | 线路没给零序时用的倍数。示例 CSV 已经写出 3 倍零序 |
| `csv_path` | 空 | 馈线 CSV。列见下方 |
| `output_csv` | 不写 | 样本 CSV。父目录不存在时会创建 |
| `output_png` | 不保存 | `R_f` 最小的一组：AG、BC、ABC 的故障电流和最低相电压对距离 |
| `show` | `false` | 为真时留下图窗。Python demo 使用无界面后端，只保存文件 |

馈线 CSV 列（合成数据，逗号或分号）：

| Column | Required | Meaning |
|--------|----------|---------|
| `kind` | 是 | `source` 或 `line` |
| `name` | 否 | 元件名。线路名会进入 `line_id` |
| `from_bus` | 是 | 电源所在母线，或线路首端。电源行也可写 `bus` |
| `to_bus` | 线路必填 | 线路末端 |
| `length_km` | 否 | 线路长度，km。电源母线的距离记 0 |
| `r1_ohm`, `x1_ohm` | 与 `z1_ohm` 二选一 | 这一段的正序阻抗，Ω |
| `r0_ohm`, `x0_ohm` | 否 | 零序阻抗，Ω。缺省时用 `z0_factor` |
| `z1_ohm`, `x_over_r` | 与电阻电抗二选一 | 正序阻抗模和 `X/R`。不写 `X/R` 时按纯电抗 |
| `z0_factor` | 否 | `Z0 / Z1`。与 `r0/x0` 不要同时给 |

## API

两侧返回同一组主要字段。未写出文件时，Python 为 `None`，MATLAB 为 `''`。Python 另有 `frame`，是与 CSV 同列的 pandas 表。

| Field | Meaning |
|-------|---------|
| `engine` | `zbus` 或 `pandapower` |
| `network` | `radial` 或 `cigre_mv` |
| `v_kv`, `v_ll_v` | 表头用的线电压。放射状馈线就是 `v_kv`。CIGRE-MV 取母线里最常见的电压，即 20 kV |
| `s_base_mva`, `z_base_ohm`, `i_base_a` | 表头基准。`I_fault_mag_pu` 用的是该行母线自己的电压 |
| `seed`, `n_grid`, `n_samples` | 种子、全网格行数、导出的行数 |
| `anchor_bus`, `remote_bus` | summary 里代表最近端和最远端的母线 |
| `samples` | 每一行一个样本 |
| `summary`, `preview` | 多行表和 demo 的一行摘要 |
| `output_csv`, `output_png`, `fig` | 写出的路径和图窗 |

`samples` 的每一行，也是 CSV 的列：

| Column | Meaning |
|--------|---------|
| `sample_id` | 从 1 起 |
| `bus_id` | 故障母线，如 `B0` 或 CIGRE 的 `Bus 3` |
| `line_id` | 走到该母线的支路名。电源母线为 `source` |
| `distance_km` | 从电源沿线路的千米数。变压器长度记 0 |
| `fault_type`, `fault_type_code`, `label_protect` | 上表 |
| `R_f_ohm` | 这一行的过渡电阻 |
| `V_a_pu`, `V_b_pu`, `V_c_pu` | 故障母线相电压幅值，相对该母线的相电压基准 |
| `V_bus_mag_pu` | 三相里最低的一个 |
| `I_phase_a_A`, `I_phase_b_A`, `I_phase_c_A` | 流入故障的三相电流幅值，A |
| `I_fault_mag_A` | AG/BG/CG 为接地电流；AB/BC/CA 为故障相电流；ABC 为每相电流 |
| `I_fault_mag_pu` | `I_fault_mag_A` 除以该母线的基准电流 |
| `engine` | 产生这一行的引擎 |

抽样用固定的乘数 `16807`、模 `2147483647`。同一个 `seed` 和 `n_samples`，两边抽出的行相同。

## Example output

`examples/data/synthetic_radial_feeder.csv`，`engine=zbus`，种子 42，105 行。表中的电流和电压是电源母线、`R_f = 0` 的那一行；`count` 是该类型在全部样本里的行数。

```text
pp-fault-synth-export: engine=zbus network=radial samples=105  AG@B0 Rf=0.0000 If=12371.7915 A Vmin=0.0000 pu  BC@B0 If=12500.0000 A  ABC@B0 If=14433.7567 A
engine=zbus  network=radial  V=10.0000 kV  S_base=10.0000 MVA  Z_base=10.0000 ohm  I_base=577.3503 A  samples=105  seed=42
type code  label            count bus            Rf         If_A     Vmin       Va       Vb       Vc           Ia           Ib           Ic
AG      1  phase-to-ground     15 B0         0.0000   12371.7915   0.0000   0.0000   1.0785   1.0785   12371.7915       0.0000       0.0000
BG      2  phase-to-ground     15 B0         0.0000   12371.7915   0.0000   1.0785   0.0000   1.0785       0.0000   12371.7915       0.0000
CG      3  phase-to-ground     15 B0         0.0000   12371.7915   0.0000   1.0785   1.0785   0.0000       0.0000       0.0000   12371.7915
AB      4  phase-to-phase      15 B0         0.0000   12500.0000   0.5000   0.5000   0.5000   1.0000   12500.0000   12500.0000       0.0000
BC      5  phase-to-phase      15 B0         0.0000   12500.0000   0.5000   1.0000   0.5000   0.5000       0.0000   12500.0000   12500.0000
CA      6  phase-to-phase      15 B0         0.0000   12500.0000   0.5000   0.5000   1.0000   0.5000   12500.0000       0.0000   12500.0000
ABC     7  three-phase         15 B0         0.0000   14433.7567   0.0000   0.0000   0.0000   0.0000   14433.7567   14433.7567   14433.7567
remote bus=B4 distance=4.1000 km Rf=0.0000 If_AG=1385.9253 A If_BC=1927.1714 A If_ABC=2225.3058 A
```

上图是金属性故障的电流对距离，下图是最低相电压。AG 蓝、BC 红、ABC 绿。末端 `B4` 距电源 4.1 km，三相电流降到 2225.3058 A。

CIGRE-MV 在 pandapower 3.x 里是 15 个母线。联络开关 S1、S2、S3 按算例保持打开。同一公式下，110 kV 母线 `Bus 0` 的金属性三相电流是 `5000 MVA` 对应的 26243.1941 A；20 kV 母线经过变压器后更小。这个网络的基准文件没有零序参数，工具补的是：线路 `Z0 = 3 Z1`，外部电网 `Z0 = 1.5 Z1`，变压器零序等于正序漏抗。

## Parity

- 函数名都是 `pp_fault_synth_export`；demo 为 `demo_pp_fault_synth_export.m` 与 `examples/run_demo.py`
- 默认都打印 `AG@B0 ... If=12371.7915 A`、`BC@B0 If=12500.0000 A`、`ABC@B0 If=14433.7567 A`
- 都打印 `remote bus=B4 distance=4.1000 km` 和 `If_ABC=2225.3058 A`
- 示例馈线共用 `examples/data/synthetic_radial_feeder.csv`
- CSV 列名、故障编码和 `label_protect` 相同
- `n_samples=6`、`seed=42` 时，第一行都是 `B3 CG R_f=1`

## Limitations

- 这是经典戴维南短路，故障前电压 1.0 pu，不计负荷、电容和非周期分量。它不是 IEC 60909，没有电压系数 c
- 负序等于正序。放射状模型要求单电源树状网络，出现环路时停止
- 过渡电阻按上面的序网接法计入。接地故障用 `3 R_f`，相间故障用一个 `R_f`
- CIGRE-MV 的零序是教学假设。算例文件本身没有线路和外部电网的零序数据，变压器绕组的零序也没有按接线组别展开
- pandapower 引擎读取网络参数后，仍用本页的序网公式，以便得到分相电压和分相电流
- 电流是流入故障点的相电流。放射状单电源下，它也就是首端看到的故障分量；这里没有再算沿线分布的负荷电流
- 示例阻抗、长度和 250 MVA 电源都是凑整的教学数字

## FAQ

**AG 的健全相电压为什么会高于 1 pu？**  
`B0` 上 `Z0 = 1.5 Z1`，而且角度相同。序网算完后 `|Vb| = |Vc| = √57 / 7 ≈ 1.0785 pu`。故障相被金属性接地拉到 0，健全相的电压由零序和正序叠加抬高。

**为什么 B1 上两个健全相电压不相等？**  
电源阻抗角约 `arctan(10)`，第一段线路的阻抗角约 `arctan(0.525/0.405)`。叠到 `B1` 以后，`Z0` 和 `Z1` 不再同角度，AG 的 `|Vb|` 和 `|Vc|` 会分开。电流仍只有 A 相。

**`label_protect` 和 `fault_type` 用哪一个做分类标签？**  
细标签用 `fault_type`（AG 到 ABC）。只区分接地、相间、三相时用 `label_protect`。编码 `fault_type_code` 是 1 到 7，顺序固定。

**需要安装 pandapower 才能跑 demo 吗？**  
不需要。demo 和 MATLAB 都走放射状 `zbus`。装了 pandapower 之后，用 `engine="pandapower"` 换 CIGRE-MV，列保持不变。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助对照短路序网和保护术语，结果不作为整定、开关选型或考核依据。请勿把学生姓名、学号、成绩或未公开的电网数据放进示例或提交到仓库。
