"""Smoke tests for pv-clearsky-index."""

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
from pv_clearsky_index import classify, clearsky_ghi, format_summary, load_table, pv_clearsky_index


def test_clearsky_shape_and_night():
    h = np.arange(24.0)
    cs, cosz = clearsky_ghi(np.full(24, 172), h, 25.0)
    assert cs[0] == 0 and cs[23] == 0
    assert cs.argmax() == 12 and 900 < cs.max() < 1100


def test_synthetic_classes(tmp_path):
    csv = tmp_path / "s.csv"
    write_csv(csv, synthetic_rows())
    r = pv_clearsky_index(csv)
    assert r["n_days"] == 10
    assert r["counts"] == {"clear": 4, "cloudy": 4, "overcast": 2}
    assert r["sky_type"][0] == "clear" and r["sky_type"][4] == "overcast"


def test_perfect_clear_day_is_kt_one(tmp_path):
    rows = synthetic_rows()[:24]
    h = np.arange(24.0)
    cs, _ = clearsky_ghi(np.full(24, 152), h, 25.0)
    csv = tmp_path / "c.csv"
    write_csv(csv, [(rows[0][0], int(i), float(v)) for i, v in zip(h, cs)])
    r = pv_clearsky_index(csv)
    assert r["kt"][0] == pytest.approx(1.0, abs=1e-3) and r["sky_type"][0] == "clear"


def test_thresholds():
    assert classify(0.8) == "clear" and classify(0.5) == "cloudy" and classify(0.1) == "overcast"


def test_outputs_and_bad_inputs(tmp_path):
    csv = tmp_path / "s.csv"
    write_csv(csv, synthetic_rows())
    out = tmp_path / "o.csv"
    r = pv_clearsky_index(csv, output_csv=out, output_png=tmp_path / "o.png")
    assert len(out.read_text().splitlines()) == r["n_days"] + 1
    assert (tmp_path / "o.png").exists()
    assert "days=10 clear=4" in format_summary(r)
    with pytest.raises(ValueError):
        pv_clearsky_index(csv, clear_thr=0.3, overcast_thr=0.5)
    bad = tmp_path / "b.csv"
    bad.write_text("date,hour,ghi\n2026-06-01,0,-5\n")
    with pytest.raises(ValueError):
        load_table(bad)


def test_run_demo_script():
    r = subprocess.run([sys.executable, str(TOOL / "examples" / "run_demo.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "days=10 clear=4 cloudy=4 overcast=2" in r.stdout
