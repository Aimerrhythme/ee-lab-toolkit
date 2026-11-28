# ETT 变压器油温数据加载与滑窗切分

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Load ETT-format transformer data, split by time, scale with training statistics only, and cut input-window → forecast-window samples (Python + MATLAB).**

读取 ETTh1/ETTm1 格式的 CSV（列：`date,HUFL,HULL,MUFL,MULL,LUFL,LULL,OT`，`OT` 是油温，其余六列是三档负荷的有功/无功），按时间先后切成训练/验证/测试三段，**只用训练段**的均值和标准差做标准化，再在每一段内部切出「输入窗 → 预测窗」样本，并画一张油温—负荷对照图。课堂重点是避开"未来信息泄露"：

1. 不打乱顺序，按行号切分，训练段在前、测试段在最后；
2. 均值/标准差只由训练段算出，验证和测试段用同一组数去变换（所以它们的标准化结果均值不必是 0）；
3. 窗口不跨越分段边界，训练窗口的输入和标签都不会用到验证或测试行。

数据集与 Informer 论文见 [ETDataset](https://github.com/zhouhaoyi/ETDataset) 和 [arXiv:2012.07436](https://arxiv.org/abs/2012.07436)。**本仓库不含真实 ETT 数据**；示例是脚本生成的合成数据（720 小时，固定种子），格式相同，没有任何私人信息。使用真实文件时请自行从上述项目下载，并遵守其许可。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | `numpy`；示例出图用 `matplotlib`（没有也能跑，只是跳过图）；测试用 `pytest` |
| MATLAB R2021b+ | 基础 MATLAB，不需要工具箱 |

## Quick start

在仓库根目录执行。

### Python

```bash
pip install -r requirements.txt
python tools/ett-window-loader/examples/run_demo.py
python -m pytest tools/ett-window-loader -q
```

```python
import sys
sys.path.insert(0, "tools/ett-window-loader/python")
from ett_window_loader import load_and_window

r = load_and_window("tools/ett-window-loader/examples/data/synthetic_ett.csv",
                    input_len=96, pred_len=24, split=(0.6, 0.2, 0.2), target="OT")
r.train.X.shape      # (313, 96, 7)
r.train.Y.shape      # (313, 24)  标准化后的油温
r.inverse_target(r.test.Y)   # 还原成摄氏度
```

### MATLAB

```matlab
cd tools/ett-window-loader/matlab
demo_ett_window_loader
res = ett_window_loader('../examples/data/synthetic_ett.csv', 96, 24, ...
                        'split', [0.6 0.2 0.2], 'target', 'OT');
size(res.train.X)    % 313 x 96 x 7
```

MATLAB 版没有在本仓库的自动流程里实际运行过，语义按 Python 版对齐写成；如发现差异请以 Python 版和测试为准。

## 参数

| 参数 | 默认 | 含义 |
|------|------|------|
| `csv_path` | — | ETT 格式 CSV，首列 `date`，时间升序，不含缺失值 |
| `input_len` | — | 输入窗长度（步数），输入含全部 7 个特征列 |
| `pred_len` | — | 预测窗长度（步数），标签只含目标列 |
| `split` | `(0.6, 0.2, 0.2)` | 训练/验证/测试比例，三个正数且和为 1；行数取下整 |
| `target` | `'OT'` | 目标列名 |
| `stride` | `1` | 相邻窗口起点间隔 |

返回值：`train`、`val`、`test` 三组，各含 `X`（样本×输入窗×特征）、`Y`（样本×预测窗）、`start`（输入窗第一步在整个文件里的行号，Python 从 0 起，MATLAB 从 1 起）；另有 `columns`、`target`、`mean`、`std`（训练段统计量，总体标准差，标准差为 0 时按 1 处理）、`bounds`（训练末行、验证末行、总行数）。Python 里还有 `inverse_target()`，摘要用 `r.summary()`；MATLAB 的摘要是字符串字段 `res.summary`。

## Example output

默认参数 `input_len=96, pred_len=24`，合成数据 720 行。分段为 432 / 144 / 144 行；每段窗口数是 `n - 96 - 24 + 1`：

```text
ett-window-loader: rows=720 target=OT train=313 val=25 test=25 windows, train_OT_mean=45.6510
train: X(313, 96, 7) Y(313, 24) first_start_row=0
val: X(25, 96, 7) Y(25, 24) first_start_row=432
test: X(25, 96, 7) Y(25, 24) first_start_row=576
train mean OT=45.651 std OT=4.098
```

图 `examples/output/ett_window_loader_demo.png`（该目录已 gitignore）：红线是油温，蓝线是三档有功负荷之和，竖虚线是训练/验证与验证/测试的分界。油温像负荷的慢速滞后响应，可以顺着图讲为什么"用整段数据算均值"会把未来信息带进训练。

可以做的小实验：把验证/测试段的数据整体放大再重新加载，训练段的均值、标准差和训练窗口完全不变（见 `tests/` 里的无泄露检查）；再试试故意用全表统计量标准化，比较训练集均值的变化。

## Limitations

- 示例是合成数据，数值规律简单，不代表真实变压器；真实 ETT 的行数、季节性和异常值都更复杂
- 只支持无缺失值、时间升序的文件，不做插值、不检查采样间隔是否均匀
- 窗口不跨分段，所以验证/测试段的前 `input_len` 行不能作为它们之前历史的上下文；有些论文会让验证/测试窗口回看训练段的尾部，这里为了讲清楚泄露而选了更保守的做法
- 只做标准化（z-score），没有归一化到 [0,1]、没有时间戳特征，也不是任何模型的训练代码
- 仅供教学演示，不能用于变压器状态评估或运维决策

## License

MIT — 见仓库根目录 [LICENSE](../../LICENSE)。教学示例，不构成工程建议。
