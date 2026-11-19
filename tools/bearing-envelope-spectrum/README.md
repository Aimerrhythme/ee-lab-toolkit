# 电机轴承振动包络谱与特征提取 (bearing-envelope-spectrum)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Band-pass, Hilbert envelope and envelope spectrum of a bearing vibration signal, with BPFO/BPFI markers and classifier-ready features (Python + MATLAB).**

滚动轴承出现局部故障时，每次滚动体撞击缺陷都会激起一次高频共振，撞击周期就是故障特征频率。原始谱里这些低频成分常被噪声淹没，所以先带通取共振带、再取希尔伯特包络、最后看包络的频谱。本工具：

1. 由转速和轴承几何参数算出 `fr`、`bpfo`、`bpfi`、`bsf`、`ftf`
2. 带通（FFT 零相位）→ 希尔伯特包络 → Hann 窗幅值谱
3. 在 `fr / bpfo / bpfi` 附近 ±`tol_hz` 取峰值，并除以 10–`f_max` Hz 的谱中位数得到 `snr_*`
4. 导出时域（rms、peak、crest、kurtosis）和包络域（env_rms、env_kurtosis、amp_*、snr_*）特征，供分类器使用

思路参考：[arXiv:2407.14625](https://arxiv.org/abs/2407.14625)。本工具**不联网、不下载数据**；示例是合成信号。用 CWRU 等公开数据时，请自行下载后整理成下面的两列 CSV。

## Dependencies

- Python 3.10+：`numpy`、`matplotlib`（测试另需 `pytest`）；不需要 scipy
- MATLAB R2021b+：只用基础函数（`readmatrix`、`fft`、`xline`），无需工具箱

## Quick start

```bash
# Python
python examples/make_data.py   # optional: regenerate synthetic CSV
python examples/run_demo.py
pytest tests
```

```matlab
% MATLAB (from the matlab/ folder)
demo_bearing_envelope_spectrum
```

两边打印相同格式的摘要（首行 `fs=… fr=… bpfo=… bpfi=…`，随后是 `feature,value`）；输出写入 `examples/output/`（已 gitignore）。

## Input format

`t_s,accel`：时间（秒，严格递增、均匀采样）和加速度。采样率取 `1/median(diff(t_s))`；至少 16 个有限样本。

## API

`bearing_envelope_spectrum(csv_path, rpm=1797, n_balls=9, ball_d=7.94, pitch_d=39.04, contact_deg=0, band=(2000, 5000), tol_hz=3, f_max=500, output_csv=None, output_png=None, show=False)`

MATLAB：`bearing_envelope_spectrum(csvPath, 'rpm', 1797, 'band', [2000 5000], ...)`，名称相同。

| 参数 | 默认 | 含义 |
|---|---|---|
| `rpm` | 1797 | 转速 (r/min) |
| `n_balls`, `ball_d`, `pitch_d`, `contact_deg` | 9, 7.94, 39.04, 0 | 滚动体数、滚动体直径、节圆直径（同单位）、接触角 (°)；默认接近 6205 型轴承 |
| `band` | (2000, 5000) | 带通范围 (Hz)，须在 `fs/2` 内，应覆盖结构共振 |
| `tol_hz` | 3 | 取特征频率峰值的 ± 窗口 |
| `f_max` | 500 | 谱图上限，也是噪声底（中位数）的上界 |
| `output_csv` | 无 | 特征表 `feature,value` |
| `output_png` | 无 | 左：原始信号前 0.1 s；右：包络谱与 fr/bpfo/bpfi 虚线 |
| `show` | false | 是否弹出图窗 |

返回：`fs`、`freqs`、`features`、`f_env`、`amp_env`、`summary`。

故障频率（Hz，`c = d/D·cos(α)`）：

```text
BPFO = n/2 · fr · (1 - c)      BPFI = n/2 · fr · (1 + c)
BSF  = D/(2d) · fr · (1 - c²)  FTF  = fr/2 · (1 - c)
```

## Example output

合成信号 1 s、12 kHz、外圈故障（107.4 Hz 撞击、3.5 kHz 共振）。包络谱在 `bpfo` 处出现明显峰（`snr_bpfo` 约 20），`bpfi` 处接近噪声底；原始信号的峭度反而只有约 3，说明直接看原始统计量不如先做包络。

## Limitations

- 示例信号是合成的，不代表任何真实轴承或电机；结论不能外推
- 带通范围要靠经验或峭度图选取，本工具不自动选带
- 只标注 `fr/bpfo/bpfi`，没有 `bsf/ftf` 的峰值特征，也不含谐波、边频带或变转速（阶次）分析
- 理想矩形带通在边缘有吉布斯振铃，仅作教学
- MATLAB 版未在 MATLAB 环境实跑，仅按与 Python 相同语义人工核对

## FAQ

**为什么不直接看原始谱？** 故障冲击能量小、分布在共振带，低频谱里被转频和噪声盖住。

**峰值没出现在理论频率上？** 轴承有滑动，实际频率会偏差 1–2%；加大 `tol_hz`，并核对 `rpm` 与几何参数。

## Teaching disclaimer

教学演示用途（MIT License）：仅用合成数据，不含任何学生姓名、学号或真实私有数据；不可用于真实设备的安全或检修决策。
