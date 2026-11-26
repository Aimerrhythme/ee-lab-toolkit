"""Smoke tests for nilm-window-prep."""

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
from nilm_window_prep import fill_short_gaps, format_summary, nilm_window_prep


def test_fill_short_gaps_only_short_interior():
    x = np.array([np.nan, 1, np.nan, 3, np.nan, np.nan, np.nan, 7, np.nan])
    y, n = fill_short_gaps(x, 2)
    assert y[2] == pytest.approx(2.0) and n == 1
    assert np.isnan(y[4:7]).all() and np.isnan(y[0]) and np.isnan(y[8])


def test_clean_ramp_windows(tmp_path):
    csv = tmp_path / "r.csv"
    csv.write_text("timestamp_s,aggregate_w,appliance_w\n"
                   + "".join(f"{i},{i},{10 * i}\n" for i in range(20)))
    r = nilm_window_prep(csv, step_s=1, window=5, stride=1)
    assert r["n_windows"] == 16 and r["n_dropped"] == 0
    assert r["y"][0] == pytest.approx(20.0)      # midpoint index 2 -> 10*2
    assert r["X"][3].tolist() == [3, 4, 5, 6, 7]


def test_demo_gaps_and_outputs(tmp_path):
    csv = tmp_path / "s.csv"
    write_csv(csv, synthetic_rows())
    out = tmp_path / "o.csv"
    r = nilm_window_prep(csv, step_s=6, max_gap_steps=3, window=11, stride=3,
                         output_csv=out, output_png=tmp_path / "o.png")
    assert r["n_filled"] >= 1 and r["n_dropped"] > 0
    assert r["n_windows"] + r["n_dropped"] == r["n_candidates"]
    assert np.isfinite(r["X"]).all() and np.isfinite(r["y"]).all()
    assert r["y"].max() > 1000                    # kettle seen
    assert len(out.read_text().splitlines()) == r["n_windows"] + 1
    assert (tmp_path / "o.png").exists()
    assert "windows=" in format_summary(r)


def test_bad_inputs(tmp_path):
    csv = tmp_path / "b.csv"
    csv.write_text("timestamp_s,aggregate_w,appliance_w\n2,1,1\n1,1,1\n")
    with pytest.raises(ValueError):
        nilm_window_prep(csv)
    csv.write_text("timestamp_s,aggregate_w,appliance_w\n1,1,1\n2,1,1\n")
    with pytest.raises(ValueError):
        nilm_window_prep(csv, window=4)


def test_run_demo_script():
    r = subprocess.run([sys.executable, str(TOOL / "examples" / "run_demo.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "windows=" in r.stdout
