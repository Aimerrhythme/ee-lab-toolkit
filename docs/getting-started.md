# Getting started

## Clone

```bash
git clone https://github.com/Aimerrhythme/ee-lab-toolkit.git
cd ee-lab-toolkit
```

## Python environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## MATLAB path

```matlab
addpath(genpath('tools'));   % from repo root
```

## Run the first demo

```bash
python tools/load-csv-plot/examples/run_demo.py
```

MATLAB: `cd` to `tools/load-csv-plot/matlab` and run `demo_load_csv_plot`. Details are in that tool's README.
