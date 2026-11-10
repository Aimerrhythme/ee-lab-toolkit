# 同步相量毛刺 Isolation Forest 演示

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Isolation Forest anomaly flagging on a synthetic PMU stream (Python + MATLAB).**

读入一段 30 帧/秒的合成 PMU 数据（电压幅值、相角、频率），含单帧毛刺、12 帧短时频率偏移和 2 帧幅值跌落。算法是手写的 Isolation Forest：用帧间变化量（幅值差、相角步长）和频率偏差做特征，打分后按 `contamination` 取最高那一部分标为异常，输出异常时标和三联图。调 `contamination` 就能直观看到告警灵敏度的取舍。数据全部合成，没有真实量测，也没有学生信息。

特征（每帧）：`v_mag_pu`、`d_mag_pu`（幅值帧间差）、`d_angle_deg`（相角帧间差，已解卷绕）、`df_hz`（频率减 `f_nom`）。先做中位数/MAD 稳健缩放，再建树。得分 `s = 2^(-E[h(x)]/c(psi))`，越接近 1 越异常。

## Dependencies

| Runtime | Requirements |
|---------|--------------|
| Python 3.10+ | `numpy`、`matplotlib`（见仓库 `requirements.txt`），不需要 scikit-learn |
| MATLAB R2021b+ | 基础 MATLAB 即可（`readtable`、`yline` 随基础包），不需要 Statistics Toolbox |

## Quick start

在仓库根目录执行。

### Python

```bash
pip install -r requirements.txt
python tools/pmu-iforest-demo/examples/run_demo.py
```

结果写到 `examples/output/pmu_demo.csv` 和 `pmu_demo.png`（已 gitignore）。自己调用：

```python
import sys
sys.path.insert(0, "tools/pmu-iforest-demo/python")
from pmu_iforest import pmu_iforest
r = pmu_iforest("tools/pmu-iforest-demo/examples/data/synthetic_pmu.csv", contamination=0.03)
print(r.anomaly_times, r.precision, r.recall)
```

### MATLAB

```matlab
cd('tools/pmu-iforest-demo/matlab')
demo_pmu_iforest
```

## Parameters

Python 关键字与 MATLAB 名值对同名。

| Name | Default | Description |
|------|---------|-------------|
| `n_trees` | `100` | 树的数量 |
| `max_samples` | `256` | 每棵树的子样本数，树高上限为 `ceil(log2(max_samples))` |
| `contamination` | `0.02` | 预期异常比例，取得分最高的这部分帧为异常，范围 (0, 0.5) |
| `f_nom` | `50` | 标称频率，Hz |
| `seed` | `0` | 随机种子 |
| `output_csv` / `output_png` | 不写 | 逐帧特征、得分、标志；三联图（幅值、频率、得分） |
| `show` | `false` | 为真时留下图窗 |

输入 CSV 列：`time_s, v_mag_pu, v_angle_deg, freq_hz`，可选 `true_anomaly`（0/1，用来算 precision/recall）。重新生成示例数据：`python tools/pmu-iforest-demo/examples/make_data.py`。

## API

返回字段两侧一致：`time_s`、`features`、`feature_names`、`scores`、`threshold`、`flags`、`anomaly_times`、`precision`、`recall`、`summary`、`output_csv`、`output_png`。

## Example output

示例（`contamination=0.03`，`seed=0`，Python）：标出 18 帧，precision 0.778、recall 0.824；3 个单帧毛刺全部命中，频率偏移段大部分命中。上图幅值带红点，中图频率带红点，下图得分和阈值虚线。

## Limitations

- MATLAB 版未在本次自动化中实际运行验证（环境无 MATLAB）；MATLAB 与 NumPy 的随机数也不同，两边得分接近但不逐位相同。
- 逐帧特征不考虑上下文，持续多帧的缓慢漂移不容易被发现；毛刺紧邻的后一帧可能因帧间差也被标记。
- `contamination` 是你替它定的比例，不是自动估计的；真实系统请结合保护与数据质量标志。
- 教学演示，不用于现场告警或保护决策。MIT 许可。
