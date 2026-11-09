# 三比值与随机森林 DGA 对照台

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**IEC 60599 three-ratio rule vs. random forest on dissolved-gas analysis samples (Python + MATLAB).**

同一批油色谱（DGA）样本并行跑两条路：一条是 IEC 三比值编码规则，一条是手写的随机森林多分类。输出测试集上的两张混淆矩阵和五种气体的特征重要度，方便运维课做“规则 vs 数据”对照。示例是合成数据，没有任何真实变压器记录，也没有学生信息。

```text
R1 = C2H2 / C2H4      R2 = CH4 / H2      R3 = C2H4 / C2H6      (每种气体先取 max(ppm, 0.1))
特征 x = log10(1 + ppm)，顺序 H2, CH4, C2H6, C2H4, C2H2
```

简化的三比值表（取第一条命中，都不命中记 `ND`，即规则给不出结论）：

| 类别 | 含义 | R1 | R2 | R3 |
|------|------|----|----|----|
| `PD` | 局部放电 | — | < 0.1 | < 0.2 |
| `D1` | 低能放电 | > 1 | 0.1–0.5 | > 1 |
| `D2` | 高能放电 | 0.6–2.5 | 0.1–1 | > 2 |
| `T1` | 低温热故障 | — | > 1 | < 1 |
| `T2` | 中温热故障 | < 0.1 | > 1 | 1–4 |
| `T3` | 高温热故障 | < 0.2 | > 1 | > 4 |

这张表是课堂简化版，边界请以现行 IEC 60599 / GB/T 7252 原文为准。

随机森林用 NumPy / 基础 MATLAB 手写：自助采样、每个节点随机选 `mtry` 个特征、基尼不纯度选阈值、叶节点存类别比例，森林对各树概率取平均，取第一个最大值。随机数是两边共用的 32 位 LCG（`state = (1664525·state + 1013904223) mod 2^32`），第 `t` 棵树的种子是 `seed + t`，所以同一个 `seed` 在两种语言里长出同一片森林（浮点并列时可能有极小差异）。

## Dependencies

| Runtime | Requirements |
|---------|--------------|
| Python 3.10+ | `numpy`、`matplotlib`（见仓库 `requirements.txt`），不调用 scikit-learn；测试用 `pytest` |
| MATLAB R2021b+ | 基础 MATLAB 即可，不需要 Statistics Toolbox |

## Quick start

在仓库根目录执行。

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/dga-ratio-vs-rf/examples/run_demo.py
pytest -q tools/dga-ratio-vs-rf
```

```python
import sys
sys.path.insert(0, "tools/dga-ratio-vs-rf/python")
from dga_ratio_vs_rf import dga_ratio_vs_rf

result = dga_ratio_vs_rf("tools/dga-ratio-vs-rf/examples/data/synthetic_dga_ppm.csv",
                         n_trees=50, seed=0, output_png="dga.png")
print(result.summary)
```

### MATLAB

```matlab
cd('tools/dga-ratio-vs-rf/matlab')
demo_dga_ratio_vs_rf
```

输出写到 `tools/dga-ratio-vs-rf/examples/output/`（已 gitignore）。直接调用：

```matlab
result = dga_ratio_vs_rf('../examples/data/synthetic_dga_ppm.csv', 'n_trees', 50, 'seed', 0);
disp(result.summary)
```

## Parameters

Python 关键字与 MATLAB 名值对同名（MATLAB 不区分大小写）。第一个参数是 CSV 路径。

| Name | Default | Description |
|------|---------|-------------|
| `n_trees` | `50` | 树的棵数，正整数 |
| `max_depth` | `6` | 最大深度，正整数 |
| `mtry` | `2` | 每个节点随机候选的特征数，1–5 |
| `min_samples_split` | `2` | 节点样本数小于它就不再分裂 |
| `seed` | `0` | 非负整数 |
| `output_csv` | 不写 | 逐样本表：`sample_id,split,true,rule,rf,rf_prob,r1,r2,r3` |
| `output_png` | 不保存 | 两张混淆矩阵与特征重要度柱状图 |
| `show` | `false` | 为真时保留图窗 |

输入 CSV 列：`sample_id,h2_ppm,ch4_ppm,c2h6_ppm,c2h4_ppm,c2h2_ppm,label,split`。`label` 是 `PD/D1/D2/T1/T2/T3`，`split` 是 `train` 或 `test`。森林只用 `train` 行训练，所有对比指标只统计 `test` 行。

结果字段（Python 属性 / MATLAB struct 字段同名）：`sample_ids, split, true_label, rule_label, rf_label, rf_prob, ratios, confusion_rule (6×7，最后一列是 ND), confusion_rf (6×6), importance, acc_rule, acc_rf, rule_nd_fraction, n_train, n_test, summary, output_csv, output_png`。混淆矩阵行是真实类，列是预测类。

## 示例数据

`examples/data/synthetic_dga_ppm.csv` 共 144 条（每类 24 条），由 `examples/make_data.py` 生成：每类取一组典型 ppm，再对每种气体乘上 `exp(0.45·z)` 的对数正态噪声（固定 LCG，可复现）。每类第 4、8、… 条标为 `test`，共 36 条。

## Example output

`n_trees=50`，`seed=0`，`max_depth=6`，`mtry=2`：

```text
train=108  test=36  n_trees=50  max_depth=6  mtry=2  seed=0
accuracy_test  rule=0.7500  rf=1.0000  rule_nd_fraction=0.1111

importance H2=0.1934  CH4=0.0469  C2H6=0.1014  C2H4=0.3149  C2H2=0.3434
```

图的左边是规则的混淆矩阵（多一列 `ND`），中间是森林的混淆矩阵，右边是气体重要度。可以讲三件事：

- **规则有“说不出”的情况。** 噪声把部分样本推出了比值边界，规则要么判错，要么落到 `ND`；森林总会给一个类。
- **森林在这里全对是因为数据是合成的。** 类别是按固定特征曲线生成的，分得开。真实油样类别重叠更多，不能把 1.0 当结论。
- **重要度回看气体含义。** C2H2、C2H4 贡献大，对应放电与高温的特征气体。

## Limitations & disclaimer

- 教学演示，**不得作为变压器故障诊断或投运依据**；三比值表是简化版
- 示例是合成数据，规则与森林的差距由数据生成方式决定，不代表真实优劣
- 森林很小（无袋外估计、无剪枝、无类别权重），也没有做交叉验证
- 气体低于检测限时统一取 0.1 ppm，会影响比值
- 不含学生信息或非公开真实数据；MIT 许可（见仓库 `LICENSE`）

## FAQ

**为什么特征用 `log10(1+ppm)`？**  
各气体浓度跨几个数量级，取对数后阈值更稳定；`+1` 避免 0 ppm 取对数。

**两种语言结果会完全一样吗？**  
LCG、分裂搜索顺序都一致，通常一样；浮点比较并列时可能有极小差异。MATLAB 版未在本环境实际运行过。
