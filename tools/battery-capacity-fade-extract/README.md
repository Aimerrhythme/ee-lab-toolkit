# battery-capacity-fade-extract

锂电循环数据容量衰减曲线提取：逐圈对放电电流积分得到容量，换算 SOH，并提取前 100 圈的简单统计特征。
*Per-cycle discharge capacity, SOH and early-cycle features from cycling data.*

## Dependencies

- Python >= 3.9: numpy, matplotlib (pytest for tests)
- MATLAB: base MATLAB only (readmatrix, polyfit; no toolboxes). The MATLAB version was not executed in the authoring environment (no MATLAB/Octave); it mirrors the Python logic.

## Quick start

```bash
python tools/battery-capacity-fade-extract/examples/run_demo.py
pytest tools/battery-capacity-fade-extract/tests
```

```matlab
cd tools/battery-capacity-fade-extract/matlab
demo_battery_capacity_fade_extract
```

```python
from battery_capacity_fade import battery_capacity_fade_extract
r = battery_capacity_fade_extract("cycles.csv", nominal_ah=1.1)
print(r["soh"][-1], r["features"]["slope_ah_per_cycle"])
```

## Input format

CSV columns `cycle,time_s,current_a,voltage_v`; discharge current is negative, time increases within a cycle. Convert public datasets (e.g. the Severson et al. data, https://www.nature.com/articles/s41560-019-0356-8) to this format first.

## Parameters

| Name | Default | Meaning |
|---|---|---|
| csv_path | - | cycling CSV |
| nominal_ah | first-cycle capacity | reference capacity for SOH |
| n_early | 100 | number of early cycles for features |
| eol_soh | 0.8 | SOH threshold for end-of-life cycle |
| output_csv / output_png | none | Python only: save table / figure |

Result fields: `cycles`, `capacity_ah`, `soh`, `nominal_ah`, `features` (q_first, q_last_early, delta_q, q_mean, q_std, slope_ah_per_cycle, n_early), `eol_cycle` (None / NaN if never reached).

Capacity = trapezoid integral of |I| dt over samples with I < 0 in each cycle, in Ah.

## Example output

The demo uses a deterministic synthetic 120-cycle cell (1.10 Ah, slow linear fade plus a late knee) and prints `cycles=120 q0=1.100Ah qEnd=1.027Ah soh_end=0.933 ...`. The figure shows capacity (left axis) and SOH (right axis) with the early window shaded.

## Limitations & disclaimer

- Only discharge samples with I < 0 are integrated; rest steps and charge are ignored; no temperature or rate correction.
- Synthetic data only; real cells need unit and format conversion first.
- For teaching and experiments only, not for battery safety or warranty decisions. MIT licensed.
