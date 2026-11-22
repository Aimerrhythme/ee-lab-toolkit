# 绝缘子巡检图 VOC→YOLO 标注转换与框可视化 (insulator-yolo-label-convert)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)

**Convert Pascal-VOC XML boxes to YOLO txt, split 7:2:1, and overlay the written labels for a visual check (Python + MATLAB).**

目标检测实验的第一步往往不是训练，而是把别人给的 VOC 标注变成 YOLO 能读的格式。本工具读入 `annotations/*.xml` 与 `images/`，输出标准 YOLO 数据集目录：`images/{train,val,test}`、`labels/{train,val,test}`（每行 `class cx cy w h`，归一化，6 位小数）、`classes.txt` 和 `data.yaml`；按 7:2:1 划分；并取排序后的前若干张图，把**刚写出的 YOLO 标签**反向画回图上（往返核对），一眼发现类别错位或坐标写反。

示例是合成的绝缘子串小图（20 张 160×120，类别 `insulator` 与 `defect`），其中最后一张故意带一个退化框（宽为 0，会被跳过）和一个越界框（会被裁剪）。数据集思路参考公开绝缘子数据集（如 [InsulatorData/InsulatorDataSet](https://github.com/InsulatorData/InsulatorDataSet)）；本工具**不联网、不下载数据**，换成真实数据时按下面的目录约定摆放即可。

## Dependencies

- Python 3.10+：`numpy`、`matplotlib`（测试另需 `pytest`）；XML 解析用标准库
- MATLAB R2021b+：只用基础函数（`xmlread`、`imread`），无需工具箱

## Quick start

```bash
# Python
python examples/make_data.py   # 可选：重新生成合成 VOC 样例（固定种子）
python examples/run_demo.py
pytest tests
```

```matlab
% MATLAB (from the matlab/ folder)
demo_insulator_yolo_label_convert
```

两边打印相同摘要：`images=20 boxes=44 skipped=1 empty_images=0`、`split train=14 val=4 test=2`，以及每个类别的框数；输出写入 `examples/output/`（已 gitignore）。

## Input format

```text
<voc_dir>/annotations/xxx.xml   # <filename>, <size><width><height>, <object><name><bndbox>xmin ymin xmax ymax
<voc_dir>/images/<filename>     # XML 中 filename 找不到时，退回同名 stem 的任意扩展名
```

坐标按像素直接使用：`cx = (xmin+xmax)/2/W`，`w = (xmax-xmin)/W`（不做 ±1 修正）。越界框先裁剪到图内；裁剪后宽或高 ≤ 0 的框、以及不在类别表里的框一律跳过并计入 `skipped`。

## API

`insulator_yolo_label_convert(voc_dir, out_dir, classes=None, viz_n=6, output_png=None, show=False)`

MATLAB：`insulator_yolo_label_convert(vocDir, outDir, 'classes', {}, 'viz_n', 6, 'output_png', '', 'show', false)`

| 参数 | 默认 | 含义 |
|---|---|---|
| `classes` | 自动 | 类别名列表，顺序即类别 id；缺省取所有框名字的字母序去重 |
| `viz_n` | 6 | 核对图使用排序后前 N 张图 |
| `output_png` | 无 | 核对拼图路径；不给就不画 |
| `show` | false | 是否弹出图窗 |

返回：`n_images`、`n_boxes`、`n_skipped`、`n_empty_images`、`classes`、`class_counts`、`split_counts`、`items`、`out_dir`。

划分规则（与 MATLAB 完全一致，不依赖随机数）：把 XML 文件名排序，第 i 张（从 0 起）`i mod 10` 为 0–6 进 train，7–8 进 val，9 进 test。20 张 → 14/4/2。

## Example output

核对图 3 列网格：每张图画出绿/红框并标注类别名与所属划分；`defect`（id 0）是损坏的深色盘片小框，`insulator`（id 1）是整串外框；最后一张图的退化框不出现，越界框被裁到图边。

## Limitations

- 示例是合成的矩形"绝缘子串"，不代表真实巡检图的外观与难度
- 只处理轴对齐矩形框；不处理 `difficult`/`truncated` 标记、多边形或旋转框
- 划分按文件名顺序轮转，**不按类别分层、也不按同一场景/杆塔分组**；真实数据中同杆塔的相似图落到不同集合会造成泄漏，课堂上应让学生先讨论
- 不检查图像实际尺寸与 XML 中 `<size>` 是否一致
- MATLAB 版未在 MATLAB 环境实跑，仅按与 Python 相同语义人工核对

## FAQ

**YOLO 的坐标为什么是中心点加宽高？** 它与图像尺寸无关，缩放图像后标签仍然有效。

**为什么要把写出的标签再画回去？** 转换脚本最常见的错误是 x/y 或 w/h 写反，只看数字很难发现，画出来一眼就能看出。
