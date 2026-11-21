"""Smoke tests for theft-imbalance-metrics."""

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
from theft_imbalance_metrics import (average_precision, best_f1_threshold,
                                     confusion_at, rates, roc_auc,
                                     theft_imbalance_metrics)


def test_confusion_and_rates_known_values():
    y = [1, 1, 0, 0, 0]
    s = [0.9, 0.2, 0.6, 0.1, 0.1]
    assert confusion_at(y, s, 0.5) == (1, 1, 1, 2)
    r = rates(1, 1, 1, 2)
    assert r["precision"] == 0.5 and r["recall"] == 0.5
    assert r["f1"] == pytest.approx(0.5)
    assert r["accuracy"] == pytest.approx(0.6)
    assert r["balanced_acc"] == pytest.approx((0.5 + 2 / 3) / 2)


def test_auc_ap_perfect_and_tied():
    y = [1, 1, 0, 0]
    assert roc_auc(y, [0.9, 0.8, 0.2, 0.1]) == pytest.approx(1.0)
    assert average_precision(y, [0.9, 0.8, 0.2, 0.1]) == pytest.approx(1.0)
    assert roc_auc(y, [0.5, 0.5, 0.5, 0.5]) == pytest.approx(0.5)  # all tied
    assert best_f1_threshold(y, [0.9, 0.8, 0.2, 0.1]) == pytest.approx(0.8)


def test_accuracy_misleads_on_imbalanced_data(tmp_path):
    y, plain, weighted = synthetic_rows()
    p = tmp_path / "s.csv"
    write_csv(p, y, plain, weighted)
    res = theft_imbalance_metrics(p, threshold=0.5, output_csv=tmp_path / "o.csv",
                                  output_png=tmp_path / "o.png")
    plain_fixed = res["metrics"]["score_plain"]["fixed"]
    # accuracy beats the do-nothing baseline while recall is tiny
    assert plain_fixed["accuracy"] > res["always_normal_accuracy"]
    assert plain_fixed["recall"] < 0.2
    # best-F1 threshold rescues F1; weighted fit moves recall up at 0.5
    assert res["metrics"]["score_plain"]["best_f1"]["f1"] > plain_fixed["f1"]
    assert res["metrics"]["score_weighted"]["fixed"]["recall"] > plain_fixed["recall"]
    # monotone shift leaves ranking metrics unchanged
    assert plain_fixed["roc_auc"] == pytest.approx(
        res["metrics"]["score_weighted"]["fixed"]["roc_auc"])
    assert (tmp_path / "o.png").stat().st_size > 0
    assert (tmp_path / "o.csv").read_text().startswith("model,operating_point")


def test_bad_inputs_raise(tmp_path):
    p = tmp_path / "b.csv"
    p.write_text("y_true,s\n1,0.5\n1,0.7\n")
    with pytest.raises(ValueError):
        theft_imbalance_metrics(p)
    p.write_text("y_true,s\n0,0.5\n1,\n")
    with pytest.raises(ValueError):
        theft_imbalance_metrics(p)
    p.write_text("y_true,s\n0,0.5\n1,0.9\n")
    with pytest.raises(ValueError):
        theft_imbalance_metrics(p, threshold=1.5)


def test_demo_script_runs():
    out = subprocess.run([sys.executable, str(TOOL / "examples" / "run_demo.py")],
                         capture_output=True, text=True, check=True).stdout
    assert out.splitlines()[0].startswith("n=2000 positives=")
    assert "score_weighted,best_f1" in out
