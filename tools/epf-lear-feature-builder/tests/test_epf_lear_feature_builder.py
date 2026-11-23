"""Smoke tests for epf-lear-feature-builder."""

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
from epf_lear_feature_builder import epf_lear_feature_builder, format_summary, load_table


def test_shapes_and_lag_alignment(tmp_path):
    csv = tmp_path / "s.csv"
    write_csv(csv, synthetic_rows())
    _, P, ex = load_table(csv)
    r = epf_lear_feature_builder(csv)
    assert r["X"].shape == (35, 4 * 24 + 24 + 7)
    assert len(r["names"]) == r["n_features"]
    # row 0 is target day 7: D-1 block is day 6, D-7 block is day 0, load is day 7
    assert np.allclose(r["X"][0, :24], P[6])
    assert np.allclose(r["X"][0, 72:96], P[0])
    assert np.allclose(r["X"][0, 96:120], ex[7])
    assert np.allclose(r["y"][0], P[7])


def test_weekday_dummies_one_hot(tmp_path):
    csv = tmp_path / "s.csv"
    write_csv(csv, synthetic_rows())
    r = epf_lear_feature_builder(csv)
    dummies = r["X"][:, -7:]
    assert np.all(dummies.sum(axis=1) == 1)
    assert dummies[0].argmax() == 0  # 2026-02-09 is a Monday


def test_no_exog_column(tmp_path):
    csv = tmp_path / "n.csv"
    with open(csv, "w") as f:
        f.write("date,hour,price\n")
        for d in range(10):
            for h in range(24):
                f.write(f"2026-03-{d + 2:02d},{h},{d + h}\n")
    r = epf_lear_feature_builder(csv, lags=(1, 7))
    assert r["X"].shape == (3, 2 * 24 + 7)


def test_outputs_and_summary(tmp_path):
    csv = tmp_path / "s.csv"
    write_csv(csv, synthetic_rows())
    out = tmp_path / "o.csv"
    r = epf_lear_feature_builder(csv, output_csv=out, output_png=tmp_path / "o.png")
    assert len(out.read_text().splitlines()) == r["n_rows"] + 1
    assert (tmp_path / "o.png").exists()
    assert "rows=35" in format_summary(r)


def test_bad_inputs(tmp_path):
    csv = tmp_path / "b.csv"
    csv.write_text("date,hour,price\nd,0,1\n")
    with pytest.raises(ValueError):
        load_table(csv)
    good = tmp_path / "g.csv"
    write_csv(good, synthetic_rows(5))
    with pytest.raises(ValueError):
        epf_lear_feature_builder(good)  # 5 days <= max lag 7
    with pytest.raises(ValueError):
        epf_lear_feature_builder(good, lags=(0,))


def test_run_demo_script():
    r = subprocess.run([sys.executable, str(TOOL / "examples" / "run_demo.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "rows=35" in r.stdout
