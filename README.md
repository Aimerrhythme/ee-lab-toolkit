# EE Lab Toolkit

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
[![Tools](https://img.shields.io/badge/tools-growing-brightgreen.svg)](./tools)

面向电气工程教学与实验的 **Matlab + Python 双版本**小工具集：负荷处理、PID 演示、标幺换算、波形分析等。每个工具目录结构统一，课堂可直接跑示例。

> 教学辅助用途；结果不作为工程投运依据。请勿提交学生隐私或未授权数据。

## Features

- **Dual runtime** — 同一功能同时提供 `matlab/` 与 `python/` 实现，输入输出约定尽量一致
- **One tool, one folder** — `tools/<slug>/` 自带 README、示例与最小测试
- **Classroom-ready** — 示例数据与一键出图，降低机房环境摩擦
- **Daily growth** — 工作日自动从主题队列选题并新增工具（见 `themes.md`）

## Repository layout

```text
ee-lab-toolkit/
├── README.md
├── LICENSE
├── CHANGELOG.md
├── CONTRIBUTING.md
├── themes.md                 # 待做 / 已做工具主题队列
├── pyproject.toml            # Python 项目元数据
├── requirements.txt
├── docs/
│   ├── getting-started.md
│   └── tool-convention.md    # 单工具目录约定（高星仓风格）
├── tools/
│   └── <slug>/
│       ├── README.md
│       ├── python/
│       ├── matlab/
│       ├── examples/
│       └── tests/
└── .github/
    └── workflows/ci.yml      # Python 语法/测试冒烟
```

## Quick start

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/<slug>/examples/run_demo.py
```

### MATLAB

1. 打开 MATLAB，把仓库根目录加入路径，或 `cd` 到 `tools/<slug>/matlab`
2. 运行对应 `demo_*.m`（见各工具 README）

## Tool index

| Slug | Status | Summary |
|------|--------|---------|
| [load-csv-plot](./tools/load-csv-plot/) | done | 负荷 CSV 清洗与标准出图：时间解析、缺失填补、尖峰标记、可选日均，并保存标准曲线 |
| [pid-step-compare](./tools/pid-step-compare/) | done | PID 阶跃响应参数对比沙盒：叠加多组 Kp/Ki/Kd 阶跃曲线，并计算上升时间、超调、调节时间与稳态误差 (PID step-response sandbox) |
| [pu-convert](./tools/pu-convert/) | done | 有名值与标幺值互算：由 S_base、V_base 求 I_base、Z_base，并在 V/I/S/P/Q/Z/R/X 与 pu 之间换算，含双绕组阻抗归算 (SI and per-unit conversion) |
| [fft-thd](./tools/fft-thd/) | done | 波形傅里叶与 THD 速算：单边幅度谱、基波检测、各次谐波幅值/百分比与 THD；非整周期用窗函数和最小二乘拟合 (FFT spectrum and THD) |
| [pwm-waveform](./tools/pwm-waveform/) | done | PWM 调制波形生成与演示：正弦-三角载波的单极性/双极性 SPWM，门极与桥口电压，并核对线性区基波峰值和 THD (sine-triangle PWM waveforms) |
| [motor-torque-speed](./tools/motor-torque-speed/) | done | 感应/直流电机转矩-转速曲线：由三相感应电机每相等效电路扫转差，给出起动转矩、最大转矩及临界转差和额定点，并对比直流他励/并励/串励及电压、转子电阻、磁场变化 (induction and DC torque-speed curves) |
| [pv-daily-features](./tools/pv-daily-features/) | done | 光伏日出力特征提取：按日给出峰值功率与时刻、发电量与容量因子、开机窗口、步长/窗口爬坡和波动指数 (PV daily peak, ramp, and variability) |
| [load-kmeans](./tools/load-kmeans/) | done | 典型日负荷曲线聚类：按日峰值归一化后做 k-means，给出每日簇标签、典型日质心、簇内平方和与轮廓系数 (k-means on peak-normalized daily load profiles) |
| [voltage-drop](./tools/voltage-drop/) | done | 线路压降估算小工具：用教材近似公式由线路 R/X 与负荷 P/Q 或 I/pf 估算三相或单相压降和百分数，并可沿放射状馈线逐段累加母线电压 (approximate feeder voltage drop) |
| [short-circuit-mva](./tools/short-circuit-mva/) | done | 短路容量/阻抗速算：由短路容量、短路电流或阻抗互算，并用容量法把电源、变压器和线路按串联倒数、并联相加折成三相短路电流，同时给出 X/R 相量校核 (short-circuit MVA and impedance) |
| [bode-demo](./tools/bode-demo/) | done | 简单传递函数 Bode 图演示：由分子/分母系数在对数频率网格上计算幅值 (dB) 与相位 (deg)，并给出增益/相位裕度及穿越频率；示例含一阶、二阶阻尼扫描和 PID 回路 (Bode plot, margins, and crossover frequencies) |
| [simulink-param-export](./tools/simulink-param-export/) | done | 参数表 CSV 导出约定与示例脚本：用 name/value/unit/description 等列读写块、模型和工作区参数，检查类型与范围并做 CSV 往返；核心不依赖 Simulink (parameter-table CSV round trip) |
| [pp-fault-synth-export](./tools/pp-fault-synth-export/) | done | pandapower 短路样本合成与标签导出：在放射状馈线上按母线、故障类型和过渡电阻批量计算相电压与相电流，导出保护术语标签 CSV；可选用 pandapower 的 CIGRE-MV，列与简化模型相同 (short-circuit sample synthesis and protection labels) |
| [load-curve-dnn-fit](./tools/load-curve-dnn-fit/) | done | 典型日负荷曲线 DNN 拟合小工具：峰值或最小-最大归一化后，用可调次数的多项式和一层 tanh 的浅层 MLP 拟合负荷对时刻的函数，并比较 RMSE、MAE 与最大绝对误差 (polynomial and shallow DNN fit of a daily load curve) |
| [dga-ratio-vs-rf](./tools/dga-ratio-vs-rf/) | done | 三比值与随机森林 DGA 对照台：同一批合成油色谱样本并行跑简化 IEC 60599 三比值规则和手写随机森林多分类，输出测试集混淆矩阵与气体特征重要度 (IEC three-ratio rule vs random forest on DGA) |
| [pmu-iforest-demo](./tools/pmu-iforest-demo/) | done | 同步相量毛刺 Isolation Forest 演示：合成 30 帧/秒 PMU 流，手写 Isolation Forest 按帧间变化和频率偏差打分，输出异常时标与三联图 (Isolation Forest on PMU glitches) |
| [evcs-load-window](./tools/evcs-load-window/) | done | 充电桩负荷清洗与特征窗切分：清洗充电会话记录，按重叠时间折算成固定步长站级功率，再切成输入窗 X 与预测窗 y 导出 CSV (EV charging sessions to forecasting windows) |
| [bess-tou-qlearn-toy](./tools/bess-tou-qlearn-toy/) | done | 分时电价储能 Q-learning 玩具环境：在小时×SOC 网格上做表格 Q-learning，与阈值贪心策略比较一日电费并导出调度表 (tabular Q-learning for battery TOU arbitrage) |
| [grid-to-graph-export](./tools/grid-to-graph-export/) | done | pandapower 电网拓扑转图结构导出：把母线、线路和变压器写成 0 起始的节点/有向边特征、二进制邻接矩阵和导纳矩阵 G/B；课堂默认走同一份合成 4 母线 CSV，Python 可选 pandapower 算例 (grid topology to graph and Ybus CSV) |
| [meter-weekly-heatmap](./tools/meter-weekly-heatmap/) | done | 电表日用电周矩阵热图与缺失处理：缺失（空/NaN/负数）标记，仅对中间短缺口线性插值，按户 min-max 后折成「周×星期」矩阵并出热图 (smart-meter weekly heatmap with gap handling) |
| [el-image-loader-aug](./tools/el-image-loader-aug/) | done | 光伏 EL 图像读取、划分与增强：按 elpv 风格标签 CSV 读入灰度图，按类别确定性分层划分 train/val/test，仅对 train 做翻转/旋转增强并出清单与样例拼图 (EL image loader, stratified split and flip/rotate augmentation) |
| [wind-curve-binning-filter](./tools/wind-curve-binning-filter/) | done | 风速—功率分箱曲线与离群点过滤：按风速分箱求中位数与四分位距，标记负功率、停机、限电和围栏离群点，输出清洗前后散点与三次方铭牌曲线 (binned wind-power curve with IQR fences) |
| [epf-naive-baselines](./tools/epf-naive-baselines/) | done | 日前电价朴素基线评估：对逐小时电价实现「昨日同时刻」「上周同日」两种预测，在同一批评估日上输出 MAE/sMAPE/RMSE 表与分时 MAE 图 (naive day-ahead price baselines) |
| [epf-lear-feature-builder](./tools/epf-lear-feature-builder/) | done | 日前电价 LEAR 特征矩阵构造器：把逐小时电价/负荷预测整理成按日一行的特征矩阵（D-1/2/3/7 滞后价格 + 负荷 + 星期哑变量） (LEAR input feature matrix builder) |
| [bearing-envelope-spectrum](./tools/bearing-envelope-spectrum/) | done | 电机轴承振动包络谱与特征提取：带通、希尔伯特包络和 Hann 窗幅值谱，按转速与轴承几何算 BPFO/BPFI 并标注，导出时域与包络域特征及信噪比 (bearing envelope spectrum with fault-frequency markers) |
| [theft-imbalance-metrics](./tools/theft-imbalance-metrics/) | done | 窃电检测不平衡分类评估台：对带标签的检测分数在固定阈值与最佳 F1 阈值两个工作点输出混淆矩阵、精确率/召回率/F1、ROC-AUC 与 AP，并对比"全判正常"基线 (imbalanced-classification bench for theft detection) |
| [insulator-yolo-label-convert](./tools/insulator-yolo-label-convert/) | done | 绝缘子巡检图 VOC→YOLO 标注转换与框可视化：裁剪越界框、跳过退化框，按排序位置确定性 7:2:1 划分，输出 classes.txt/data.yaml，并把写出的标签画回图上核对 (VOC to YOLO labels with split and overlay check) |
| [pv-clearsky-index](./tools/pv-clearsky-index/) | done | 光伏晴空指数计算与晴/多云/阴天划分：Haurwitz 晴空模型算理论辐照，与实测相除得日 kt，按阈值分晴/多云/阴并出图 (clear-sky index and sky-type classification) |
| [battery-capacity-fade-extract](./tools/battery-capacity-fade-extract/) | done | 锂电循环数据容量衰减曲线提取：逐圈积分放电容量、换算 SOH、提取前 100 圈统计特征 (capacity fade and SOH extraction) |
| [nilm-window-prep](./tools/nilm-window-prep/) | done | 非侵入式负荷分解数据对齐与滑窗切分：总表与分项功率按时间戳分箱对齐、补短缺口，并切出「总功率窗→中点电器功率」样本对 (aggregate/appliance alignment and seq2point windowing for NILM) |

更多主题见 [`themes.md`](./themes.md)。完成后继续追加本表。

## Design principles

1. **Small & focused** — 一个工具只做一件课堂用得到的事  
2. **Parity** — Python / Matlab 同输入字段、同主要输出图/表含义  
3. **Reproducible** — 示例数据进仓；随机种子固定  
4. **Documented** — 每个工具 README 含：用途、依赖、运行、参数、截图位、常见问题  

## Automation

工作日定时：读取 `themes.md` 第一条 `todo` → 按 `docs/tool-convention.md` 生成双版本工具 → 更新索引与 changelog → 推送到本仓库 → 在对话中通知。

## License

MIT — 见 [LICENSE](./LICENSE)。
