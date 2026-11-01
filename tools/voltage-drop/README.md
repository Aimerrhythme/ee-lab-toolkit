# 线路压降估算小工具

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Approximate feeder voltage drop for one section or a radial line (Python + MATLAB).**

用课堂里那条近似公式，由线路电阻、电抗和负荷估算电压降，并给出相对额定电压的百分数。可以只算一段，也可以把若干段接成一条从电源向外的放射状馈线，逐段累加母线电压。示例是凑整的 10 kV 教学数字，不是某条真实线路的实测或设计资料。

## Formula

三相（默认）。`R`、`X` 是一相阻抗，单位 Ω。`V` 是代入分母的线电压，单位 V。`I` 是线电流，单位 A。`P`、`Q` 是三相有功、无功，单位 W、var。滞后（感性）无功为正，超前（容性）为负。

```text
ΔV = √3 · I · (R cosφ + X sinφ) = (P · R + Q · X) / V
ΔV% = 100 · ΔV / V_n
```

给出每千米阻抗时，`R = r · L`，`X = x · L`，`L` 的单位是 km。`pf` 的绝对值是功率因数，符号表示方向：`pf = 0.8` 表示 cosφ = 0.8、sinφ = +0.6；`pf = -0.8` 表示超前，sinφ = −0.6。

若手算时用 kW、kvar、Ω 和 kV，百分数可以写成教材里的形式，和上面是同一件事：

```text
ΔV% = (P_kW · R + Q_kvar · X) / (10 · U_kV²)
```

分母里的 10 来自单位换算，不是「这条线是 10 kV」这几个字。10 kV 线路把 `U_kV = 10` 代进去，分母是 `10 × 100 = 1000`。

单相两线。`R`、`X` 按单根导线给出，来回两根都计入：

```text
ΔV = 2 · I · (R cosφ + X sinφ) = (P · 2R + Q · 2X) / V
```

单相功率是 `P = V · I · cosφ`。三相是 `P = √3 · V · I · cosφ`，`Q` 把 cosφ 换成 sinφ。

电流输入会先按额定电压 `V_n` 换成 `P`、`Q`。因此在默认的 `voltage_basis='nominal'` 下，电流公式和功率公式得到同一个 ΔV。`sending` 时分母改用该段首端电压，两种输入仍然走同一套 `P`、`Q`。

放射状馈线按表格从上到下、从电源向外。`load_mode='tap'`（默认）时，每一行的 `P/Q` 或 `I/pf` 是受端母线的负荷，本段通过功率等于这一母线加上全部下游。`through` 时，行里的功率或电流已经是本段通过量，不再相加。

`voltage_basis='nominal'`（默认）每一段都用 `V_n` 作分母，这是课堂近似。`sending` 用该段首端电压，并从电源递推：`V_recv = V_send − ΔV`。百分数始终相对 `V_n`，不相对首端电压。

Python 与 MATLAB 使用同一套式子、同一套参数名，并打印同一段 summary 文本。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | 计算只用标准库。保存电压剖面图时用 `matplotlib`（见仓库 `requirements.txt`）。不需要 numpy |
| MATLAB R2021b+ | 基础 MATLAB 即可，不需要工具箱 |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/voltage-drop/examples/run_demo.py
```

脚本先算一段「80 A、功率因数 0.8、2 km」的线路，再读 `examples/data/synthetic_feeder_sections.csv`。表写到 `examples/output/voltage_drop_demo.csv`，电压剖面写到 `examples/output/voltage_drop_demo.png`（该目录已 gitignore）。

在自己的脚本里调用：

```python
import sys
sys.path.insert(0, "tools/voltage-drop/python")
from voltage_drop import format_single_line, format_table, voltage_drop

single = voltage_drop(
    length_km=2.0,
    r_ohm_per_km=0.4,
    x_ohm_per_km=0.35,
    i_a=80,
    pf=0.8,
    v_nominal=10_000,
)
print(format_single_line(single))
# voltage-drop single: dV=146.8779 V (1.4688 %) I=80.000 A pf=0.8000 V_recv=9853.1221 V

feeder = voltage_drop(
    "tools/voltage-drop/examples/data/synthetic_feeder_sections.csv",
    output_csv="tools/voltage-drop/examples/output/voltage_drop_demo.csv",
    output_png="tools/voltage-drop/examples/output/voltage_drop_demo.png",
)
print(format_table(feeder))
print(feeder.v_end, feeder.delta_v_percent_total)  # 9790.22 V, 2.0978 %
```

不读 CSV 时，用关键字描述一段。读 CSV、传入一组 dict，或只传一段的关键字，三者只取一种。

### MATLAB

```matlab
cd('tools/voltage-drop/matlab')
demo_voltage_drop
```

或从仓库根目录：

```matlab
addpath('tools/voltage-drop/matlab')
demo_voltage_drop
```

图写到 `tools/voltage-drop/examples/output/voltage_drop_demo_matlab.png`，表写到同目录的 `voltage_drop_demo_matlab.csv`。要在 IDE 里留住窗口，把 demo 中馈线那次调用的 `'show', false` 改成 `'show', true`。

单段：

```matlab
single = voltage_drop('length_km', 2, 'r_ohm_per_km', 0.4, ...
    'x_ohm_per_km', 0.35, 'i_a', 80, 'pf', 0.8, 'v_nominal', 10000);
single.sections(1).delta_v          % 146.8779 V
single.sections(1).delta_v_percent  % 1.4688
```

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。第一个位置参数可以是一条 CSV 路径、一个 struct / dict，或一组区段。MATLAB 名值对不区分大小写。

| Name | Default | Description |
|------|---------|-------------|
| `length_km` | 空 | 本段长度，km。用每千米阻抗时必填。只给总阻抗时可以空着 |
| `r_ohm_per_km` | 空 | 一相（三相）或单根导线（单相）的电阻，Ω/km |
| `x_ohm_per_km` | 空 | 同上，电抗，Ω/km。只给了电阻时按 0 |
| `r_ohm` | 空 | 本段总电阻，Ω。和每千米阻抗不要同时给 |
| `x_ohm` | 空 | 本段总电抗，Ω。可以为负（串联电容） |
| `i_a` | 空 | 线电流，A。与 `P/Q` 不要同时给 |
| `pf` | 电流输入时为 `1`；只给有功时为 `1` | 功率因数，范围 −1 到 1，不是百分数。正数滞后，负数超前 |
| `p_kw` | 空 | 有功，kW。与 `p_w` 不要同时给 |
| `q_kvar` | 空 | 无功，kvar。正数滞后。与 `q_var`、`pf` 不要同时给 |
| `p_w` | 空 | 有功，W |
| `q_var` | 空 | 无功，var |
| `name` | `section1`、`section2`… | 区段名。CSV 列名也可以叫 `section` |
| `from_bus` | 首段 `source`，其后接上一段的受端 | 首端母线 |
| `to_bus` | `B1`、`B2`… | 受端母线 |
| `v_nominal` | `10000` | 额定电压，V。三相为线电压，单相为两端电压。百分数的分母 |
| `v_source` | 等于 `v_nominal` | 电源母线电压，V。近似公式的分母仍按 `voltage_basis` 取 |
| `system` | `three_phase` | `three_phase`（可写 `3ph`）或 `single_phase`（可写 `1ph`） |
| `load_mode` | `tap` | `tap`：行内负荷在受端，向上游累加。`through`（可写 `flow`）：行内已经是通过功率 |
| `voltage_basis` | `nominal` | `nominal`：每段分母都是 `V_n`。`sending`：分母是该段首端电压 |
| `csv_path` | 空 | 批量 CSV。列见下方 |
| `output_csv` | 不写 | 结果 CSV。父目录不存在时会创建 |
| `output_png` | 不保存 | 电压剖面（上）和各段压降百分数（下） |
| `show` | `false` | 为真时留下图窗。Python demo 使用无界面后端，只保存文件 |

批量 CSV 建议列（合成数据，逗号或分号，小数点用 `.`）：

| Column | Required | Meaning |
|--------|----------|---------|
| `section` 或 `name` | 否 | 区段名 |
| `from_bus`, `to_bus` | 否 | 首端、受端母线。空着时按行序自动衔接 |
| `length_km` | 用每千米阻抗时必填 | 长度，km |
| `r_ohm_per_km`, `x_ohm_per_km` | 与总阻抗二选一 | 也可写 `r_per_km`、`x_per_km` |
| `r_ohm`, `x_ohm` | 与每千米阻抗二选一 | 本段总阻抗。也可写 `r`、`x` |
| `p_kw`, `q_kvar` | 与电流二选一 | 也可写 `p`、`q`，单位仍是 kW、kvar |
| `p_w`, `q_var` | 同上 | 单位 W、var |
| `i_a`, `pf` | 与功率二选一 | 也可写 `i`、`current`。不写 `pf` 时按 1 |

`tap` 模式下，这些负荷是受端母线的负荷，不是已经累加过的通过功率。

## API

两侧返回同一组字段。

| Field | Meaning |
|-------|---------|
| `system` | `three_phase` 或 `single_phase` |
| `load_mode` | `tap` 或 `through` |
| `voltage_basis` | `nominal` 或 `sending` |
| `v_nominal`, `v_source` | 额定电压和电源电压，V |
| `sections` | 每一段一行，顺序与输入相同 |
| `v_end` | 最末母线电压，V |
| `delta_v_total` | `v_source − v_end`，V |
| `delta_v_percent_total` | `100 · delta_v_total / v_nominal` |
| `summary` | 与 `format_table` 相同的文本。MATLAB demo 打印这一段 |
| `output_csv`, `output_png` | 写出的路径；未写时 Python 为 `None`，MATLAB 为 `''` |
| `fig` | `show` 为真时的图窗；否则为空 |

`sections` 的每一行：

| Field | Meaning |
|-------|---------|
| `name`, `from_bus`, `to_bus` | 区段名和两端母线 |
| `length_km` | 长度，km。未给出时为 NaN |
| `r_ohm`, `x_ohm` | 一相或单根导线的阻抗，Ω |
| `r_used_ohm`, `x_used_ohm` | 公式里实际相乘的阻抗。三相等于上面两列；单相是它们的 2 倍 |
| `p_w`, `q_var` | 这一行自己的负荷（tap）或通过功率（through），W、var |
| `p_through_w`, `q_through_var` | 代入 `(P R + Q X) / V` 的通过功率 |
| `i_a` | 通过电流，A。由通过功率和公式所用电压求出 |
| `pf` | 通过功率的功率因数。符号与无功相同：滞后为正 |
| `cos_phi`, `sin_phi` | `P/S` 与 `Q/S`。无通过功率时记为 1 和 0 |
| `delta_v`, `delta_v_percent` | 本段电压降，V 和相对 `V_n` 的百分数 |
| `v_send`, `v_recv` | 本段首端、受端电压，V |

Python 另有 `format_table(result)` 和 `format_single_line(result)`。后者只接受恰好一段的结果，demo 用它打单行。

## Example output

单段：`L = 2 km`，`r = 0.40 Ω/km`，`x = 0.35 Ω/km`，`I = 80 A`，`pf = 0.8` 滞后，`V_n = 10 kV`。

```text
R = 0.80 Ω，X = 0.70 Ω
ΔV = √3 · 80 · (0.80·0.8 + 0.70·0.6) = √3 · 80 · 1.06 = 146.8779 V
ΔV% = 1.4688 %
V_recv = 9853.1221 V
```

```text
voltage-drop single: dV=146.8779 V (1.4688 %) I=80.000 A pf=0.8000 V_recv=9853.1221 V
```

馈线：`examples/data/synthetic_feeder_sections.csv`，10 kV 三相，四段负荷接在受端。`L1` 的通过功率是四段负荷之和：`800+500+300+180 = 1780 kW`，`300+200+120+80 = 700 kvar`。`L1` 的阻抗是 `R = 0.27×1.5 = 0.405 Ω`，`X = 0.35×1.5 = 0.525 Ω`。

```text
ΔV% = (1780·0.405 + 700·0.525) / (10 · 10²) = 1088.4 / 1000 = 1.0884
ΔV = 108.84 V
```

四段加起来是 209.78 V，即 2.0978%。电源 10000 V，末端 `B4` 为 9790.22 V。

```text
system=three_phase  load_mode=tap  basis=nominal  V_nominal=10000.0000 V  V_source=10000.0000 V
section  from   to          km    R_ohm    X_ohm  Ptap_kW Qtap_kvar  Pthru_kW  Qthru_kvar      I_A      pf      dV_V   dV_pct     V_send     V_recv
L1       B0     B1       1.500   0.4050   0.5250  800.000   300.000  1780.000     700.000  110.429  0.9306  108.8400   1.0884 10000.0000  9891.1600
L2       B1     B2       1.200   0.4800   0.4440  500.000   200.000   980.000     400.000   61.112  0.9258   64.8000   0.6480  9891.1600  9826.3600
L3       B2     B3       0.800   0.4400   0.3040  300.000   120.000   480.000     200.000   30.022  0.9231   27.2000   0.2720  9826.3600  9799.1600
L4       B3     B4       0.600   0.3900   0.2400  180.000    80.000   180.000      80.000   11.372  0.9138    8.9400   0.0894  9799.1600  9790.2200
total drop=209.7800 V (2.0978 %)  V_end=9790.2200 V
```

表里的 `Ptap` 是这一行自己的负荷，`Pthru` 才进入公式。`L4` 没有下游，所以两列相同。`I_A` 和 `pf` 对的是通过功率。

上图是沿馈线的电压，横轴为距电源的千米数，红虚线是额定电压，点旁标了母线名。下图是各段电压降占额定电压的百分数。坐标和标题是英文。没有长度时，横轴改成从电源数起的母线序号。

## Parity

- 函数名都是 `voltage_drop`；demo 为 `demo_voltage_drop.m` 与 `examples/run_demo.py`
- 参数名、CSV 列名、结果字段和 summary 文本一致
- 单段示例都打印 `dV=146.8779 V (1.4688 %)`；馈线都打印 `total drop=209.7800 V` 和 `V_end=9790.2200 V`
- 示例 CSV 共用 `examples/data/synthetic_feeder_sections.csv`
- 出图都是电压剖面加各段百分数，不依赖工具箱

## Limitations

- 只算纵分量近似，忽略横分量 `I (X cosφ − R sinφ)`，也不计对地电容、互感和三相不平衡
- 默认每段都用额定电压作分母。负荷很大、末端电压已经明显偏离额定值时，这个近似会偏
- 电流输入先在 `V_n` 上换成恒定功率，再参加累加。它不是恒电流负荷模型
- 行必须按从电源向外的顺序排列。这里不求解环网，也不做潮流迭代
- 电阻不能为负。电抗可以为负，用来表示串联电容使电压上升
- 通过功率为 0 时，`pf` 记为 1，只是占位
- 示例阻抗和负荷是凑整的教学数字，不能当作线缆样本或工程计算书

## FAQ

**为什么三相有 √3，而 `(P R + Q X) / V` 里又没有？**  
线电压降是相电压降的 √3 倍：`ΔV = √3 · I · (R cosφ + X sinφ)`。三相功率 `P = √3 · V · I · cosφ`，所以 `I cosφ = P / (√3 V)`。代回去之后 √3 约掉，得到 `(P R + Q X) / V`。两条式子在额定电压下是同一个数。

**百分数公式里的 10 是什么？**  
`ΔV% = 100 · (P_W R) / V²`。把 W 写成 kW（除以 1000）、V 写成 kV（除以 1000，平方是 10⁶）之后，系数变成 `100 / 1000 = 1/10`，所以分母是 `10 · U_kV²`。

**`tap` 和 `through` 差在哪里？**  
`tap` 把每一行当成接在受端的负荷。上游区段要带上后面所有负荷，所以示例里 `L1` 的 800 kW 会变成通过功率 1780 kW。`through` 认为你已经把通过功率写进行里了，程序不再相加。

**超前功率因数为什么有时压降变小，甚至电压升高？**  
`Q` 为负时，`Q X` 为负，会抵消 `P R`。电抗上的压降反向之后，`ΔV` 可以接近 0 或变成负数，末端电压高于首端。表里的 `pf` 用负号表示超前。

**单相为什么乘 2？**  
单相两线的电流要走去又走回。`R`、`X` 若按单根导线填写，回路阻抗是 `2R`、`2X`。三相没有「返回导线」这一项，一相阻抗直接进入公式。

**需要工具箱吗？**  
不需要。Python 计算不依赖 numpy；只有画剖面时用 matplotlib。MATLAB 不调用任何工具箱。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助对照线路电压降的近似算法，结果不作为工程设计、调压或考核依据。请勿把学生姓名、学号、成绩或未公开的电网数据放进示例或提交到仓库。
