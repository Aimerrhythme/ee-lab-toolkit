# 日前电价朴素基线评估 (epf-naive-baselines)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Score "same hour yesterday" and "same weekday last week" day-ahead price forecasts with MAE / sMAPE / RMSE (Python + MATLAB).**

任何电价预测模型都应先打败朴素基线。本工具读入逐小时电价 CSV，实现两种朴素预测并在**同一批评估日**上输出 MAE、sMAPE、RMSE 表和分时 MAE 图：

- `naive_prev_day`：第 d 天第 h 小时 = 第 d−1 天第 h 小时
- `naive_prev_week`：第 d 天第 h 小时 = 第 d−7 天第 h 小时

思路参考 epftoolbox 论文（Lago 等，[arXiv:2008.08004](https://arxiv.org/abs/2008.08004)）里的朴素基准；本工具**不联网、不下载数据**，也不依赖 epftoolbox。示例是合成电价。若要用公开基准（如 epftoolbox 的 PJM/EPEX 数据），请自行下载后整理成下面的三列 CSV。

## Dependencies

- Python 3.10+：`numpy`、`matplotlib`（测试另需 `pytest`）
- MATLAB R2021b+：只用基础函数，无需工具箱

## Quick start

```bash
# Python
python examples/run_demo.py
pytest tests
```

```matlab
% MATLAB (from the matlab/ folder)
demo_epf_naive_baselines
```

两边打印相同的摘要行（`eval_days=49`，随后是 `model,mae,smape_pct,rmse` 表），输出写入 `examples/output/`（已 gitignore）。

## Input format

`date,hour,price`：`hour` 为 0–23，必须是连续的整天（行数为 24 的倍数），价格必须有限（不能空/NaN）。`date` 只当标签，不解析、不校验日历。

## API

`epf_naive_baselines(csv_path, eval_start_day=7, output_csv=None, output_png=None, show=False)`

MATLAB：`epf_naive_baselines(csvPath, 'eval_start_day', 7, 'output_csv', '', 'output_png', '', 'show', false)`

| 参数 | 默认 | 含义 |
|---|---|---|
| `eval_start_day` | 7 | 第一个评估日的 0 起始序号，必须 ≥ 7（保证两种基线都有数据），且小于总天数 |
| `output_csv` | 无 | 评估日逐小时 `date,hour,actual,naive_prev_day,naive_prev_week` |
| `output_png` | 无 | 左：前 7 个评估日实际与预测；右：分时 MAE |
| `show` | false | 是否弹出图窗 |

返回：`metrics`（每个模型 `mae`、`smape_pct`、`rmse`）、`forecasts`、`hourly_mae`、`actual`、`dates`、`n_eval_days`。

指标定义（价格单位沿用输入）：

```text
MAE   = mean(|y - yhat|)
RMSE  = sqrt(mean((y - yhat)^2))
sMAPE = mean(|y - yhat| / ((|y| + |yhat|)/2)) * 100   (百分数；0/0 记 0)
```

## Example output

示例 56 天、评估 49 天时 `naive_prev_week` 的 MAE 小于 `naive_prev_day`（合成数据里周末价格偏低，周一和周末后的第一天"昨天"最不准）。图左是预测对比，右是分时 MAE。

## Limitations

- 示例电价是合成的，不代表任何电力市场；结论不能外推到真实市场
- sMAPE 在价格接近 0 或为负时会失真，这是该指标的已知问题
- 只做点预测的朴素基线，不含概率预测、节假日处理或 DST 的 23/25 小时日
- 两种基线共用评估日，所以前 7 天没有被评分
- MATLAB 版未在 MATLAB 环境实跑，仅按与 Python 相同语义人工核对

## FAQ

**为什么评估从第 7 天开始？** 这样两种基线在同一批天上比较，指标才可比。

**价格有负值怎么办？** 计算照常，sMAPE 分母用绝对值；负价多时请更看重 MAE。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助理解"先跑朴素基线"的实验习惯，结果不作为交易、报价或成绩评定依据。请勿把学生姓名、学号、成绩或未公开的真实市场数据放进示例或提交到仓库。本工具随仓库以 MIT 许可证发布，见根目录 [LICENSE](../../LICENSE)。
