"""Smoke tests for the dga-ratio-vs-rf Python tool."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")

import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from dga_ratio_vs_rf import CLASSES, dga_ratio_vs_rf, iec_rule, ratios

CSV = TOOL / "examples" / "data" / "synthetic_dga_ppm.csv"


def test_iec_rule_table() -> None:
    assert iec_rule(0.01, 0.05, 0.1) == "PD"
    assert iec_rule(2.0, 0.3, 1.5) == "D1"
    assert iec_rule(1.0, 0.5, 5.0) == "D2"
    assert iec_rule(0.0, 3.0, 0.3) == "T1"
    assert iec_rule(0.05, 5.0, 2.5) == "T2"
    assert iec_rule(0.05, 7.0, 10.0) == "T3"
    assert iec_rule(5.0, 5.0, 5.0) == "ND"
    r = ratios([[100, 50, 10, 20, 0]])
    assert r[0].tolist() == pytest.approx([0.1 / 20, 0.5, 2.0])


def test_demo_data_and_outputs(tmp_path: Path) -> None:
    out_csv, out_png = tmp_path / "o.csv", tmp_path / "o.png"
    res = dga_ratio_vs_rf(CSV, seed=0, output_csv=out_csv, output_png=out_png)
    assert res.n_train == 108 and res.n_test == 36
    assert res.confusion_rule.shape == (6, 7) and res.confusion_rf.shape == (6, 6)
    assert res.confusion_rf.sum() == 36 and res.confusion_rule.sum() == 36
    assert res.importance.sum() == pytest.approx(1.0)
    assert res.acc_rf > 0.9 and res.acc_rf > res.acc_rule
    assert 0 < res.rule_nd_fraction < 0.5
    assert set(res.rf_label) <= set(CLASSES)
    assert out_png.stat().st_size > 1000
    assert out_csv.read_text(encoding="utf-8").startswith("sample_id,split,true,rule,rf,rf_prob,r1,r2,r3\n")
    again = dga_ratio_vs_rf(CSV, seed=0)
    assert again.summary == res.summary
    assert np.allclose(again.importance, res.importance)


def test_bad_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="n_trees must be a positive integer"):
        dga_ratio_vs_rf(CSV, n_trees=0)
    with pytest.raises(ValueError, match="mtry must not exceed"):
        dga_ratio_vs_rf(CSV, mtry=9)
    with pytest.raises(ValueError, match="unknown parameter name"):
        dga_ratio_vs_rf(CSV, trees=3)
    with pytest.raises(FileNotFoundError):
        dga_ratio_vs_rf(tmp_path / "none.csv")
    bad = tmp_path / "bad.csv"
    bad.write_text("sample_id,h2_ppm\nS1,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        dga_ratio_vs_rf(bad)


def test_run_demo_script() -> None:
    done = subprocess.run([sys.executable, str(TOOL / "examples" / "run_demo.py")],
                          check=True, capture_output=True, text=True)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("dga:")]
    assert len(lines) == 36
    assert "accuracy_test  rule=" in done.stdout
    assert (TOOL / "examples" / "output" / "dga_demo.png").stat().st_size > 1000
