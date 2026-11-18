"""Smoke tests for epf-naive-baselines."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))
sys.path.insert(0, str(TOOL / "examples"))

from make_data import synthetic_rows, write_csv
from epf_naive_baselines import (epf_naive_baselines, format_summary, load_prices,
                                 smape_pct)


def test_smape_known_values():
    assert smape_pct([100], [50]) == pytest.approx(200 / 3)  # 50/75 -> 66.67%
    assert smape_pct([0, 10], [0, 10]) == 0.0  # 0/0 counts as 0


def test_weekly_periodic_series_is_perfect_for_prev_week(tmp_path):
    base = np.arange(7 * 24, dtype=float) + 10.0
    p = np.tile(base, 4)
    csv = tmp_path / "p.csv"
    with open(csv, "w") as f:
        f.write("date,hour,price\n")
        for i, v in enumerate(p):
            f.write(f"d{i // 24},{i % 24},{v}\n")
    r = epf_naive_baselines(csv)
    assert r["metrics"]["naive_prev_week"]["mae"] == pytest.approx(0.0)
    assert r["metrics"]["naive_prev_day"]["mae"] > 0
    assert r["n_eval_days"] == 21


def test_demo_data_and_outputs(tmp_path):
    csv = tmp_path / "s.csv"
    write_csv(csv, synthetic_rows())
    dates, P = load_prices(csv)
    assert P.shape == (56, 24)
    out = tmp_path / "o.csv"
    r = epf_naive_baselines(csv, output_csv=out, output_png=tmp_path / "o.png")
    assert r["n_eval_days"] == 49
    assert len(out.read_text().splitlines()) == 49 * 24 + 1
    assert (tmp_path / "o.png").exists()
    assert "naive_prev_day" in format_summary(r)
    assert r["forecasts"]["naive_prev_week"][0] == pytest.approx(P[0])


def test_bad_inputs(tmp_path):
    csv = tmp_path / "b.csv"
    csv.write_text("date,hour,price\nd,0,1\n")
    with pytest.raises(ValueError):
        load_prices(csv)
    good = tmp_path / "g.csv"
    write_csv(good, synthetic_rows(10))
    with pytest.raises(ValueError):
        epf_naive_baselines(good, eval_start_day=3)
    with pytest.raises(ValueError):
        epf_naive_baselines(good, eval_start_day=10)


def test_run_demo_script():
    r = subprocess.run([sys.executable, str(TOOL / "examples" / "run_demo.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "naive_prev_week" in r.stdout
