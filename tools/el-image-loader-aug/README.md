# 光伏 EL 图像读取、划分与增强

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Load EL solar-cell images, split them by class, augment with flips/rotations, and export a montage (Python + MATLAB).**

建模之前先看懂图像数据集：按标签 CSV（格式参照公开的 [elpv-dataset](https://github.com/zae-bayern/elpv-dataset)：`path,proba,type`）读入 EL 电池片灰度图，类别 `class = round(proba*3)`（0 = 正常 … 3 = 明确缺陷）；按类别做**分层划分**（train / val / test）；只对 **train** 做 5 种固定增强（水平翻转、垂直翻转、旋转 90/180/270°）并写出清单；最后每类取一张 train 图，拼成「原图 + 5 种增强」的样例拼图。示例图像为脚本合成的 32×32 小图，不含任何真实数据；换成公开 elpv 数据时只需提供同格式的 `labels.csv`（图像须为同尺寸方图，真实数据 300×300，直接可用）。

## Dependencies

- Python 3.10+：`numpy`, `matplotlib`（用于读写 PNG；测试另需 `pytest`）
- MATLAB R2021b+：仅基础 MATLAB（`imread`/`imwrite`），无需工具箱

## Quick start

```bash
# Python (from repo root)
python tools/el-image-loader-aug/examples/run_demo.py
python -m pytest -q tools/el-image-loader-aug/tests
```

```matlab
% MATLAB: cd tools/el-image-loader-aug/matlab, then
demo_el_image_loader_aug
```

Python 输出写到 `examples/output/`（已被 gitignore）：`el_image_loader_aug/{split.csv,class_counts.csv,aug_manifest.csv}` 与 `el_montage_demo.png`；MATLAB 写到同目录 `*_matlab` 版本，划分与计数应完全一致。

## Input / API

```python
res = el_image_loader_aug(csv_path, output_dir=None, output_png=None,
                          fractions=(0.6, 0.2, 0.2), seed=0)
```

```matlab
res = el_image_loader_aug(csvPath, 'fractions', [0.6 0.2 0.2], 'seed', 0, ...
                          'output_dir', d, 'output_png', f)
```

| 参数 | 默认 | 含义 |
|---|---|---|
| `fractions` | 0.6/0.2/0.2 | train / val / test 比例，非负且和为 1 |
| `seed` | 0 | 划分偏移量；换一个整数得到另一种划分 |
| `output_dir` | 无 | 给定则写 `split.csv`、`class_counts.csv`、`aug_manifest.csv` |
| `output_png` | 无 | 给定则保存样例拼图 |

划分规则（确定性，Python 与 MATLAB 完全一致，不依赖随机数）：每个类别内按 `path` 排序，第 `j` 张（从 0 起）取 `u = mod((j+seed)*0.6180339887, 1)`，`u < f_train` 为 train，`u < f_train+f_val` 为 val，否则 test。黄金比例序列让各类在三个集合里都分得比较均匀。

返回值 `res`：`paths`、`types`、`proba`、`cls`、`split`、`images`（Python：N×H×W；MATLAB：H×W×N，取值 [0,1]）、`classes`、`counts`（每类 train/val/test 数）、`train_mean`、`train_std`（总体标准差，可作归一化参数，只用 train 算以避免泄漏）、`manifest`（train 图的增强副本清单）、`montage`。

## Example output

合成 40 张：正常 16、轻微 8、较重 6、明确缺陷 10；缺陷图含斜裂纹和暗斑，翻转/旋转后在拼图里一眼可辨。默认划分 train/val/test = 25/9/6（各类 train 为 10/5/4/6），增强清单 125 行（25 张 × 5 种）。

## Limitations

- 只做几何增强，不含亮度、噪声、裁剪；是否增强要在划分**之后**做（本工具已如此），否则验证集会泄漏
- 增强副本只写清单，不落盘整套图片；训练时按清单实时变换即可
- 要求图像为同尺寸方图；非方图请先自行裁剪或缩放
- 分层划分是确定性规则，不等同于随机抽样；严肃实验请另做多种子重复
- 仓库测试只覆盖 Python，MATLAB 版本逐项对应

## Disclaimer

教学辅助用途（MIT / 教学免责）：用于理解图像数据集的结构与预处理，结果不作为组件质量判定或验收依据。请勿把学生姓名、学号、成绩或未公开的真实电站数据放进示例或提交到仓库；使用公开数据集请遵守其许可。

## License

MIT — 见仓库根目录 [LICENSE](../../LICENSE)。
