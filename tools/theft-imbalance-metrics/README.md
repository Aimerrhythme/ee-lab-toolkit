# 窃电检测不平衡分类评估台 (theft-imbalance-metrics)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Why accuracy lies on imbalanced theft data: confusion matrix, ROC, PR, F1 and threshold moving (Python + MATLAB).**

窃电样本通常只占几个百分点，"全判正常"的准确率就能到 94% 以上。本工具读入「真实标签 + 一个或多个检测分数」的 CSV，对每个分数列在**固定阈值**和**最佳 F1 阈值**两个工作点上输出混淆矩阵计数、准确率、精确率、召回率、F1、平衡准确率，以及与阈值无关的 ROC-AUC 和平均精度 AP，并与"全判正常"基线对比，同时画 ROC、PR、F1-阈值曲线和混淆矩阵。

示例 CSV 里有两列分数：`score_plain`（不加类别权重训练的检测器，正样本很少过 0.5）和 `score_weighted`（同一排序整体上移，模拟加类别权重）。因为只是整体单调平移，两者 AUC/AP 完全相同，只有阈值对应的工作点不同——这正是课堂想让学生看到的："类别权重"和"移动阈值"在排序层面是一回事。

数据思路参考公开窃电数据集（如 [henryRDlab/ElectricityTheftDetection](https://github.com/henryRDlab/ElectricityTheftDetection)）的正负样本悬殊现象；本工具**不联网、不下载数据**，示例分数为合成。若要用公开数据，请自行训练出分数后整理成下面的 CSV。

## Dependencies

- Python 3.10+：`numpy`、`matplotlib`（测试另需 `pytest`）
- MATLAB R2021b+：只用基础函数，无需工具箱（`yline`/`xline` 需 R2018b+）

## Quick start

```bash
# Python
python examples/make_data.py   # 可选：重新生成示例 CSV（固定种子）
python examples/run_demo.py
pytest tests
```

```matlab
% MATLAB (from the matlab/ folder)
demo_theft_imbalance_metrics
```

两边打印相同的摘要行（`n=2000 positives=110 ...`、`always_normal_accuracy=0.9450`，随后是表头 `model,operating_point,threshold,...` 的 5 行结果），输出写入 `examples/output/`（已 gitignore）。

## Input format

`y_true,<score1>,<score2>,...`：`y_true` 为 0（正常）/1（窃电），必须两类都有；分数列越大越可疑，必须是有限数字（不能空/NaN）。规则：分数 `>= threshold` 判为窃电。列名即模型名。

## API

`theft_imbalance_metrics(csv_path, threshold=0.5, output_csv=None, output_png=None, show=False)`

MATLAB：`theft_imbalance_metrics(csvPath, 'threshold', 0.5, 'output_csv', '', 'output_png', '', 'show', false)`

| 参数 | 默认 | 含义 |
|---|---|---|
| `threshold` | 0.5 | 固定工作点阈值，范围 [0, 1] |
| `output_csv` | 无 | 结果表：`model,operating_point,threshold,tp,fp,fn,tn,accuracy,precision,recall,f1,balanced_acc,roc_auc,ap` |
| `output_png` | 无 | 2×2：ROC、PR（虚线为患病率）、F1 随阈值变化、第一个模型在固定阈值的混淆矩阵 |
| `show` | false | 是否弹出图窗 |

返回：`n`、`n_pos`、`prevalence`、`always_normal_accuracy`、`models`、`rows`（Python 为字典列表，MATLAB 为结构体数组）及曲线数据。

指标定义：

```text
precision = TP/(TP+FP)  (无人被标记时记 0)      recall = TP/(TP+FN)
F1 = 2TP/(2TP+FP+FN)                            balanced_acc = (recall + TNR)/2
ROC-AUC：对每个不同分数取一点，梯形积分（并列分数一并处理）
AP = sum (R_k - R_{k-1}) * P_k                   (阶梯式，不做插值)
best_f1 工作点 = 使 F1 最大的最高阈值
```

## Example output

示例 2000 条、窃电 110 条（5.5%）：全判正常的准确率 0.9450；`score_plain` 在 0.5 阈值准确率 0.9515（看似更好）但召回仅 0.1273；把阈值移到约 0.30 后 F1 从 0.2240 升到 0.5978；`score_weighted` 在 0.5 阈值召回 0.8364 但精确率只有 0.2377，其最佳 F1 工作点与 `score_plain` 的相同。

## Limitations

- 示例分数是合成的，不代表任何真实检测器或数据集；结论不能外推
- 只做二分类的点评估；没有交叉验证、置信区间或代价敏感的阈值选择
- "最佳 F1 阈值"在同一份数据上选取并评估，会偏乐观；课堂上应让学生另分验证集
- MATLAB 版未在 MATLAB 环境实跑，仅按与 Python 相同语义人工核对

## FAQ

**为什么 AUC 看起来很高 PR 却很低？** 负样本很多时，少量误报对 FPR 影响小，但会明显拉低精确率。

**类别权重和移动阈值有什么区别？** 本例只做了 logit 平移，所以排序指标不变；真实训练中类别权重还会改变模型本身。

## Teaching disclaimer

教学辅助用途（MIT / 教学免责）：帮助理解不平衡分类评估，结果不作为稽查、处罚或成绩评定依据。请勿把学生姓名、学号、成绩、用户用电信息或未公开的真实数据放进示例或提交到仓库。本工具随仓库以 MIT 许可证发布，见根目录 [LICENSE](../../LICENSE)。
