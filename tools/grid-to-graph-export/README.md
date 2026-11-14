# pandapower 电网拓扑转图结构导出

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Bus graph, directed edges, and positive-sequence Ybus (Python + MATLAB).**

把母线、线路和变压器收成 GNN 状态估计实验能直接读的三张表：节点特征、有向边特征，以及二进制邻接矩阵。同一套 π 型支路再叠成导纳矩阵，实部 `G`、虚部 `B` 分开写，用来对照「图」和课本里的节点导纳矩阵。默认数据是一条合成的 10 kV、4 母线网络，Python 和 MATLAB 用同一份 CSV。Python 还可以改读 pandapower 的 IEEE / CIGRE 算例，导出的列不变。示例阻抗是凑整的教学数字，不是某条线路的实测或设计资料。

## Formula

串联阻抗按 **from 母线** 的额定电压折成标幺。`b_siemens` 是整条线路的充电电纳，`g_siemens` 是整条线路的对地电导，单位都是西门子，也按 from 母线电压。分接头和移相放在 from 侧。绕组额定电压已经等于两侧母线 `vn_kv` 时，中性分接头就是 `tap = 1`，不要把变比再乘一次。

```text
z_base = vn_from_kv^2 / s_base_mva
y_base = s_base_mva / vn_from_kv^2
Ys = 1 / (r_pu + j x_pu)
a  = tap * exp(j * shift_deg * pi / 180)
Yff = (Ys + Ysh / 2) / |a|^2
Yft = -Ys / conj(a)
Ytf = -Ys / a
Ytt = Ys + Ysh / 2
```

`Ysh = g_pu + j b_pu` 是这条支路的总并联。母线并联只加在对角元上，`b_pu > 0` 表示电容。停运支路仍留在 `branches.csv`，但不进入邻接矩阵和 `Ybus`。两条并联且都在运行的支路，邻接矩阵只记 1，导纳矩阵里相加。

默认基准 `S_base = 10 MVA`，四台母线都是 10 kV，所以 `Z_base = 10 Ω`，`Y_base = 0.1 S`。

```text
L01  B0-B1   z = 0.5 + j0.5 Ω    Ys = 10 - j10    b = 0.002 S    b_pu = 0.02
L12  B1-B2   z = 0.2 + j0.6 Ω    Ys = 5 - j15
T20  B2-B0   z = 0.5 + j0.5 Ω    tap = 1.25
        Yff = Ys / tap^2 = 6.4 - j6.4
        Ytt = Ys = 10 - j10
        Yft = Ytf = -Ys / tap = -8 + j8
L23  B2-B3   z = 0.4 + j0.8 Ω    Ys = 5 - j10
L13  B1-B3   停运，不进 Ybus
C1   B1      b = 0.005 S         b_pu = 0.05
```

因此对角元是

```text
Y[B0,B0] = (10 - j9.99) + (10 - j10) = 20 - j19.99
Y[B1,B1] = (10 - j9.99) + (5 - j15) + j0.05 = 15 - j24.94
Y[B2,B2] = (5 - j15) + (6.4 - j6.4) + (5 - j10) = 16.4 - j31.4
Y[B3,B3] = 5 - j10
```

`T20` 的分接头不在 1，所以 `Y[B2,B2]` 上这条变压器的贡献和 `Y[B0,B0]` 上的不一样。`shift_deg ≠ 0` 时 `Yft ≠ Ytf`，导纳矩阵不再对称。邻接矩阵始终对称。

节点类型沿用 MATPOWER 编码：`pq = 1`，`pv = 2`，`slack = 3`。掩码按类型给：PQ 已知 P、Q；PV 已知 P、V；松弛母线已知 V 和相角。导出的 `bus_index`、`edge_index`、`from_index`、`to_index` 都从 0 起，方便直接送进 PyTorch Geometric 一类的接口。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`、`matplotlib`（见仓库 `requirements.txt`）。读 CSV 只用标准库 |
| pandapower | 可选。`pip install pandapower` 之后才能用 `engine="pandapower"`。不写入仓库的 `requirements.txt` |
| MATLAB R2021b+ | 基础 MATLAB。没有 pandapower，只读同一份合成 CSV |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/grid-to-graph-export/examples/run_demo.py
```

脚本读 `examples/data/synthetic_grid.csv`。七个 CSV 写到 `examples/output/grid_to_graph_export/`，图写到 `examples/output/grid_to_graph_export_demo.png`（该目录已 gitignore）。

```python
import sys
sys.path.insert(0, "tools/grid-to-graph-export/python")
from grid_to_graph_export import format_table, grid_to_graph_export

result = grid_to_graph_export(
    "tools/grid-to-graph-export/examples/data/synthetic_grid.csv",
    output_dir="tools/grid-to-graph-export/examples/output/grid_to_graph_export",
    output_png="tools/grid-to-graph-export/examples/output/grid_to_graph_export_demo.png",
)
print(format_table(result))
print(result.ybus[0, 0])          # 20 - j19.99
print(result.edges[0].from_index) # 0
```

已安装 pandapower 时，同一组列可以改到算例：

```python
ieee = grid_to_graph_export(engine="pandapower", network="case14")
cigre = grid_to_graph_export(engine="pandapower")   # network 默认 cigre_mv
```

`engine="auto"` 在给了 CSV 时仍走 builtin。只有 `network` 写成 `case14`、`cigre_mv` 这类名字时才去找 pandapower。和 MATLAB 对答案时请不要改 engine。

### MATLAB

```matlab
cd('tools/grid-to-graph-export/matlab')
demo_grid_to_graph_export
```

或从仓库根目录：

```matlab
addpath('tools/grid-to-graph-export/matlab')
demo_grid_to_graph_export
```

表写到 `examples/output/grid_to_graph_export_matlab/`，图写到同级的 `grid_to_graph_export_demo_matlab.png`。要在 IDE 里留住窗口，把 demo 里的 `'show', false` 改成 `'show', true`。

```matlab
result = grid_to_graph_export('self_loop', false);
result.preview
result.ybus(1, 1)    % 20 - j19.99，MATLAB 下标从 1 起，导出的 bus_index 仍从 0 起
```

MATLAB 里 `'engine', 'auto'` 也是这条合成网络。`'engine', 'pandapower'` 会说明算例只在 Python 里。

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。第一个位置参数是电网 CSV。省略时用 `examples/data/synthetic_grid.csv`。MATLAB 名值对不区分大小写。

| Name | Default | Description |
|------|---------|-------------|
| `s_base_mva` | `10`，pandapower 用网络自己的 `sn_mva` | 系统基准容量，MVA。必须为正 |
| `engine` | `builtin` | `builtin`、`pandapower` 或 `auto`。MATLAB 只有 `builtin` |
| `network` | `synthetic` 或算例名 | builtin 只接受空、`synthetic`、`builtin`。pandapower 省略时为 `cigre_mv`，也可以写 `case14`、`case9`、`case30`、`case118` |
| `self_loop` | `false` | 为真时邻接矩阵对角元写成 1。不改变 `Ybus`，也不把自环算进 `degree` |
| `csv_path` | 空 | 与第一个位置参数二选一 |
| `output_dir` | 不写 | 写出 `nodes.csv`、`edges.csv`、`branches.csv`、`shunts.csv`、`adjacency.csv`、`ybus_g.csv`、`ybus_b.csv` |
| `output_png` | 不保存 | 左图是母线连接，右图是 `imag(Ybus)` |
| `show` | `false` | 为真时留下图窗。Python demo 使用无界面后端，只保存文件 |

电网 CSV 的 `kind` 取 `bus`、`line`、`trafo`、`shunt`。数值用小数点。

| Column | Required | Meaning |
|--------|----------|---------|
| `kind`, `name` | `kind` 必填 | `line` 与 `trafo` 都走同一套 π 型。`name` 空着时自动编号 |
| `bus_id`, `bus_type`, `vn_kv` | 母线必填 | `bus_type` 为 `slack`、`pv`、`pq` |
| `p_mw`, `q_mvar` | 按类型 | 注入功率，发电为正、负荷为负。松弛母线的 P、Q 留空 |
| `vm_pu`, `va_deg` | 松弛母线必填，PV 要 `vm_pu` | 设定值，不是潮流解 |
| `x`, `y` | 否 | 画图坐标。有母线缺坐标时，全部改放到单位圆上 |
| `from_bus`, `to_bus` | 支路必填 | 分接头在 `from_bus` 侧 |
| `r_ohm`, `x_ohm` | 与 `r_pu`, `x_pu` 二选一 | 串联阻抗，欧姆，已归算到 from 侧 |
| `b_siemens`, `g_siemens` | 否 | 支路总并联，或并联元件的导纳。不要和 `b_pu`、`g_pu` 同时给 |
| `tap`, `shift_deg` | 否 | 默认 `1` 和 `0`。`tap` 必须为正 |
| `rate_mva`, `length_km` | 否 | 只进边特征，不参加 `Ybus` |
| `in_service` | 否 | 默认 1。0 表示停运 |

## API

两侧返回同一组主要字段。未写出文件时，Python 为 `""`，MATLAB 为 `''`。

| Field | Meaning |
|-------|---------|
| `engine`, `network`, `s_base_mva` | 引擎、网络名、基准容量 |
| `n_bus`, `n_branch`, `n_branch_in_service` | 在运母线数、支路行数、在运支路数 |
| `n_edge` | 有向边数，等于 `2 * n_branch_in_service` |
| `n_shunt`, `n_shunt_in_service` | 并联行数，以及真正加进 `Ybus` 的个数。preview 里的 `shunts` 是后者 |
| `bus_ids` | 母线顺序，也是矩阵的行顺序 |
| `buses`, `branches`, `shunts`, `edges` | 与 CSV 同列的记录。支路另有复数 `yff`、`yft`、`ytf`、`ytt` |
| `adjacency` | `n_bus × n_bus`，0/1，对称 |
| `ybus` | 复数导纳矩阵，标幺 |
| `preview`, `summary` | 一行摘要，以及带母线表的全文 |
| `output_dir`, `output_png`, `fig` | 写出的路径。`show` 为假时 Python 的 `fig` 是 `None` |

`nodes.csv` 的列：`bus_index`、`bus_id`、`bus_name`、`bus_type`、`bus_type_code`、`vn_kv`、`z_base_ohm`、`y_base_s`、`p_mw`、`q_mvar`、`vm_pu`、`va_deg`、`p_known`、`q_known`、`v_known`、`theta_known`、`degree`、`in_service`、`x`、`y`、`members`。

`edges.csv` 每个在运支路两行，`orientation` 为 `forward` 或 `reverse`。`y_self_*` 是该方向起点的自导纳，`y_mutual_*` 是该方向的互导纳。把所有有向边按 `Y[from, from] += y_self`、`Y[from, to] += y_mutual` 加起来，再叠上在运并联，就回到 `ybus`。

## Example output

`examples/data/synthetic_grid.csv`，`s_base_mva=10`，`self_loop=false`。

```text
grid-to-graph-export: engine=builtin network=synthetic buses=4 branches=5 in_service=4 directed=8 shunts=1 self_loop=0 Y[B0,B0]=20.0000-j19.9900 off[B1,B2]=-5.0000+j15.0000 tap[T20]=1.2500 Yfrom[B2]=6.4000-j6.4000 Yto[B0]=10.0000-j10.0000 open=L13 adj_sym=1
bus    type   deg          G          B       P_mw     Q_mvar       Vm       Va  known
B0     slack    2    20.0000   -19.9900          -          -   1.0200   0.0000  V,theta
B1     pq       2    15.0000   -24.9400    -2.0000    -0.8000   1.0000   0.0000  P,Q
B2     pq       3    16.4000   -31.4000    -1.5000    -0.5000   1.0000   0.0000  P,Q
B3     pv       1     5.0000   -10.0000     1.2000          -   1.0100   0.0000  P,V
```

`off[B1,B2]` 是非对角元里模最大的一个，来自 `L12`。左图里 `L13` 是灰色虚线，`T20` 是红色。右图是电纳 `B`，色标对零对称。

邻接矩阵是

```text
    B0 B1 B2 B3
B0   0  1  1  0
B1   1  0  1  0
B2   1  1  0  1
B3   0  0  1  0
```

## Parity

- 函数名都是 `grid_to_graph_export`；demo 为 `demo_grid_to_graph_export.m` 与 `examples/run_demo.py`
- 默认都打印 `Y[B0,B0]=20.0000-j19.9900`、`off[B1,B2]=-5.0000+j15.0000`、`tap[T20]=1.2500`、`open=L13`
- 示例电网共用 `examples/data/synthetic_grid.csv`
- 七个 CSV 的列名、0 起始下标和 `Ybus` 数值一致
- `self_loop=true` 时两边都只改邻接矩阵的对角元

## Limitations

- 这是正序 π 型导纳，不是潮流解，也不是状态估计结果。`vm_pu`、`va_deg` 是设定值
- 串联阻抗必须已经归算到 from 侧。母线 `vn_kv` 不同只用来取基准，不会自动再乘一个额定变比
- 零阻抗支路会停下来。闭合的母线—母线开关在 pandapower 引擎里并成一个节点，不建成 `r = x = 0` 的边
- 停运支路和被打开的线路开关不进入图。pandapower 潮流里为开断开关另加的辅助母线，这里不生成
- pandapower 3 只在 `tap_changer_type` 为 `Ratio`、`Symmetrical` 或 `Ideal` 时使用 `tap_pos`。类型空着时分接头留在中性位置，和该版本的内部支路一致
- 变压器铁耗按 π 型分到两端。`pfe_kw` 和 `i0_percent` 都为 0 时，支路导纳与 pandapower 的 `makeYbus` 一致；两者都有数值时，差的是 T 型励磁支路再化成 π 的那一步
- 不展开三绕组变压器、直流线路、TCSC、扩展 Ward、电动机和不对称阻抗。遇到在运的这些元件会停下来并说明原因
- 负荷按恒功率注入导出，不把 `const_z_percent` 改写成并联
- IEEE / CIGRE 算例只在 Python 的 pandapower 引擎里。MATLAB 用合成 CSV 与之对列、对公式
- 示例里的欧姆、分接头和功率都是凑整的教学数字

## FAQ

**邻接矩阵为什么不是导纳？**  
邻接矩阵只回答「连没连」。并联支路也只记 1。导纳在 `ybus_g.csv`、`ybus_b.csv` 和边特征的 `y_self_*`、`y_mutual_*` 里。

**为什么 `Y[B2,B2]` 上变压器的贡献不是 10 - j10？**  
`T20` 的 from 侧是 B2，`tap = 1.25`，自导纳要除以 `tap^2`，所以是 `6.4 - j6.4`。B0 在 to 侧，仍是 `10 - j10`。互导纳两边都是 `-8 + j8`。

**`degree` 和自环是什么关系？**  
`degree` 是相邻母线的个数。`self_loop=true` 只把 `A_ii` 写成 1，度数不变，`Ybus` 也不变。

**需要安装 pandapower 才能跑 demo 吗？**  
不需要。demo 和 MATLAB 都读合成 CSV。装了 pandapower 之后，用 `engine="pandapower"` 换 `case14` 或 `cigre_mv`，列保持不变。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助对照图数据和节点导纳矩阵，结果不作为保护整定、状态估计投运或考核依据。请勿把学生姓名、学号、成绩或未公开的电网数据放进示例或提交到仓库。
