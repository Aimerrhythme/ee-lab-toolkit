# 分时电价储能 Q-learning 玩具环境

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Tabular Q-learning for a battery on a time-of-use tariff, compared with a greedy threshold policy (Python + MATLAB).**

在「小时 × SOC 网格」上实现表格 Q-learning：每小时可放电、空闲或充电一档 SOC，奖励为负的电网电费（含充放效率），并与「低价充、高价放」的阈值贪心策略比较一日电费。后续 DQN 短文可沿用同一奖励定义。训练采用确定性的全表扫描（无随机探索），因此 Python 与 MATLAB 结果一致。示例电价为合成数据。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`, `matplotlib`（见仓库 `requirements.txt`）；测试需 `pytest` |
| MATLAB R2021b+ | 基础 MATLAB 即可，无需额外工具箱（`readtable` 为基础函数） |

## Quick start

在仓库根目录执行。

### Python

```bash
pip install -r requirements.txt
python tools/bess-tou-qlearn-toy/examples/run_demo.py
pytest tools/bess-tou-qlearn-toy -q
```

```python
import sys
sys.path.insert(0, "tools/bess-tou-qlearn-toy/python")
from bess_tou_qlearn_toy import bess_tou_qlearn_toy

r = bess_tou_qlearn_toy("tools/bess-tou-qlearn-toy/examples/data/tou_prices.csv", n_soc=6)
print(r.greedy_cost, r.learned_cost)
```

### MATLAB

```matlab
cd('tools/bess-tou-qlearn-toy/matlab')
demo_bess_tou_qlearn_toy
```

输出写到 `tools/bess-tou-qlearn-toy/examples/output/`（已 gitignore）。

## Input CSV

列：`hour,price`，每行一小时（0–23），电价单位元/kWh。也可直接传入数值价格向量。

## Parameters

Python 关键字与 MATLAB 名值对同名。

| Name | Default | Description |
|------|---------|-------------|
| `csv_path` | — | 电价 CSV 路径（或价格向量） |
| `n_soc` | `6` | SOC 档位数（0…n_soc−1） |
| `soc0` | `0` | 初始 SOC 档位 |
| `e_step_kwh` | `10` | 每档对应电量（kWh） |
| `eta` | `0.95` | 单向充/放效率：充电取电 e/η，放电回馈 e·η |
| `alpha` | `0.5` | 学习率 |
| `n_iter` | `200` | 全表扫描轮数 |
| `output_csv` | 不保存 | 调度结果 CSV，列 `hour,price,learned_action,learned_soc_end,greedy_action,greedy_soc_end` |

## API

| Field | Meaning |
|-------|---------|
| `prices` | 每小时电价 |
| `q` | Q 表，维度 `小时 × SOC × 3`（动作顺序：放电、空闲、充电） |
| `learned_soc` / `learned_action` | 学得策略的 SOC 轨迹（H+1）与动作（−1/0/1） |
| `greedy_soc` / `greedy_action` | 阈值贪心策略的对应结果 |
| `learned_cost` / `greedy_cost` | 一日净电费（元，负值为净收益），已扣除日末剩余电量的终端估值 |
| `n_soc`, `soc0` | 实际使用的网格参数 |
| `output_csv` | 写出的路径；未保存为空 |

奖励 = −price × 电网电量。终端估值：日末每多于 `soc0` 一档，按 `mean(price)·η·e_step_kwh` 抵扣，避免「把电放空」变成免费午餐。贪心策略：价格 ≤ min+(max−min)/3 时充电，≥ max−(max−min)/3 时放电，其余空闲。

## Example output

`examples/data/tou_prices.csv` 是合成 24 小时分时电价：0–7 时 0.30、10–11 与 18–21 时 1.00、其余 0.60。默认参数下 demo 输出贪心电费约 −31.71 元、Q-learning 约 −34.89 元：学得策略会在午后平段补充一档电，赶上晚高峰，而贪心在晚高峰后段已无电可放。图为电价阶梯与两种策略的 SOC 曲线。

## Limitations

- 表格方法、动作离散、一小时一档，没有功率上限、容量衰减、需量电费或负荷约束
- 电价已知且确定，未做价格预测或随机性；全表扫描不等于现场采样式探索
- 平价时段存在并列最优动作，学得轨迹在并列时取第一个（放电、空闲、充电顺序）
- MATLAB 版需 `hour` 列表头，使用 `readtable`

## FAQ

**为什么不用 ε-greedy 随机探索？** 为了让两种语言可复现且结果一致；换成随机探索只需把全表扫描改成采样转移。

**和 DQN 的关系？** 奖励、状态、动作定义相同，网格变大后用神经网络替代 Q 表即可。

## Teaching disclaimer

教学辅助用途：帮助理解强化学习在储能调度中的最小形式，结果不作为工程投运、调度或结算依据。请勿把学生姓名、学号或未授权的电价/场站数据放进示例或提交到仓库。License: MIT.
