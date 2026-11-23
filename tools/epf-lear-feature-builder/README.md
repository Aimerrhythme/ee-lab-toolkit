# 日前电价 LEAR 特征矩阵构造器 (epf-lear-feature-builder)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Turn an hourly price (and optional load-forecast) CSV into the one-row-per-day LEAR input matrix (Python + MATLAB).**

LEAR（带 Lasso 的自回归）预测次日 24 小时电价时，输入是"按日一行"的特征向量。本工具把逐小时 CSV 整理成这个矩阵，让学生看清输入长什么样：

- 价格滞后块：D-1、D-2、D-3、D-7 各 24 列（默认，可改 `lags`）
- 外生块（可选）：目标日的负荷预测 24 列（CSV 有 `load_forecast` 列时才加入）
- 星期哑变量：Mon..Sun 共 7 列
- 目标 `y`：目标日 24 小时电价

思路参考 epftoolbox（Lago 等，[arXiv:2008.08004](https://arxiv.org/abs/2008.08004)）；本工具**只构造特征，不训练模型**，不联网，不依赖 epftoolbox。示例为合成数据。

## Dependencies

- Python 3.10+：`numpy`、`matplotlib`（测试另需 `pytest`）
- MATLAB R2021b+：仅基础函数，无需工具箱

## Quick start

```bash
# Python
python examples/run_demo.py
pytest tests
```

```matlab
% MATLAB (from the matlab/ folder)
demo_epf_lear_feature_builder
```

两边打印相同摘要行（`rows=35 features=127 ...`），输出写入 `examples/output/`（已 gitignore）。MATLAB 版未在本仓库 CI 中运行，请课前在机房试跑一次。

## Input format

`date,hour,price[,load_forecast]`：`date` 为 ISO `yyyy-mm-dd`（用于计算星期），`hour` 为 0–23，必须是连续整天，数值必须有限。

## API

`epf_lear_feature_builder(csv_path, lags=(1,2,3,7), output_csv=None, output_png=None, show=False)`

MATLAB：`epf_lear_feature_builder(csvPath, 'lags', [1 2 3 7], 'output_csv', '', 'output_png', '', 'show', false)`

| 参数 | 默认 | 含义 |
|---|---|---|
| `lags` | 1,2,3,7 | 价格滞后天数（正整数）；首个目标日序号 = 最大滞后 |
| `output_csv` | 无 | `date` + 特征列 + `y_h00..y_h23` |
| `output_png` | 无 | 左：特征矩阵热图；右：各星期行数 |
| `show` | false | 是否弹出图窗 |

返回：`X`、`y`、`names`、`target_dates`、`lags`、`n_rows`、`n_features`（Python 为 dict，MATLAB 为 struct）。

## Limitations & teaching disclaimer

不做缺失插补、不处理夏令时 23/25 小时日、不做标准化。星期哑变量不含节假日。教学辅助用途，结果不作为交易或工程依据。MIT License。
