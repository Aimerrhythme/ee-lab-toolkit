# Tool theme queue

Status: `todo` → `doing` → `done`

Format: `- [status] slug | Chinese title | keywords`

## Seed themes (classroom EE lab)

- [done] load-csv-plot | 负荷 CSV 清洗与标准出图 | load, csv, plot, pandas, matlab
- [done] pid-step-compare | PID 阶跃响应参数对比沙盒 | pid, step, control
- [done] pu-convert | 有名值与标幺值互算 | per-unit, transformer, base
- [done] fft-thd | 波形傅里叶与 THD 速算 | fft, thd, harmonics
- [done] pwm-waveform | PWM 调制波形生成与演示 | pwm, carrier, modulation
- [done] motor-torque-speed | 感应/直流电机转矩-转速曲线 | motor, torque, speed
- [done] pv-daily-features | 光伏日出力特征提取 | pv, ramp, peak
- [done] load-kmeans | 典型日负荷曲线聚类 | kmeans, load-profile
- [done] voltage-drop | 线路压降估算小工具 | voltage-drop, feeder
- [done] short-circuit-mva | 短路容量/阻抗速算 | short-circuit, mva
- [done] bode-demo | 简单传递函数 Bode 图演示 | bode, tf, control
- [done] simulink-param-export | 参数表 CSV 导出约定与示例脚本 | simulink, csv, params

## Custom themes

（在下方追加；自动化优先取本文件第一条 `todo`。）

- [done] pp-fault-synth-export | pandapower 短路样本合成与标签导出 | pandapower, 故障样本, 标签, csv
  - 课堂角度：在 CIGRE-MV 或简易馈线上批量扫短路位置与类型，导出电压/电流特征与标签 CSV，作为后续分类实验的标准数据源，强调仿真标签如何对应现场保护术语。
  - 参考：https://github.com/e2nIEE/pandapower · https://arxiv.org/abs/2510.00831

- [done] load-curve-dnn-fit | 典型日负荷曲线 DNN 拟合小工具 | 负荷曲线, DNN, 拟合, 归一化
  - 课堂角度：用公开日负荷做函数逼近，对比多项式与浅层 DNN 的拟合残差，作为进入「代理模型/潮流代理」前的最小可运行模板。
  - 参考：https://arxiv.org/abs/2608.02599 · https://github.com/enliten/IEEE-course_AI-for-Power-Energy-Systems

- [todo] dga-ratio-vs-rf | 三比值与随机森林 DGA 对照台 | DGA, 三比值, 随机森林, 变压器
  - 课堂角度：同一批油色谱样本并行跑 IEC 三比值编码与随机森林多分类，输出混淆矩阵与气体特征重要度，方便运维课做「规则 vs 数据」对照实验。
  - 参考：https://arxiv.org/abs/2110.11467

- [todo] pmu-iforest-demo | 同步相量毛刺 Isolation Forest 演示 | PMU, Isolation Forest, 异常, 可视化
  - 课堂角度：生成含毛刺与短时频率偏移的合成相量流，调 contamination 观察告警灵敏度，输出异常时标与幅值图，对接广域监测导论。
  - 参考：https://arxiv.org/abs/2509.25612

- [todo] evcs-load-window | 充电桩负荷清洗与特征窗切分 | 充电桩, 特征窗, csv, 预处理
  - 课堂角度：把原始充电会话功率清洗、重采样并切成固定窗，导出给 LSTM/基线预测脚本共用，专升本实验强调数据管线先于模型调参。
  - 参考：https://arxiv.org/abs/2510.16719

- [todo] bess-tou-qlearn-toy | 分时电价储能 Q-learning 玩具环境 | 储能, Q-learning, 分时电价, 调度
  - 课堂角度：实现离散电价—SOC 网格上的表格 Q-learning，对比贪心与学习策略的一日电费，为后续 DQN 短文预留同一奖励定义。
  - 参考：https://arxiv.org/abs/2608.02599 · https://github.com/enliten/IEEE-course_AI-for-Power-Energy-Systems
