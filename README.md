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
