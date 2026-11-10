"""Smoke tests for the pmu-iforest-demo Python tool."""
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

from pmu_iforest import _c, pmu_iforest

CSV = TOOL / "examples" / "data" / "synthetic_pmu.csv"


def test_average_path_length() -> None:
    assert _c(1) == 0.0
    assert _c(2) == 1.0
    assert _c(256) == pytest.approx(10.2448, abs=1e-3)


def test_glitches_are_found_and_run_is_reproducible() -> None:
    a = pmu_iforest(CSV, contamination=0.03, seed=0)
    b = pmu_iforest(CSV, contamination=0.03, seed=0)
    assert np.array_equal(a.scores, b.scores)
    assert a.flags.sum() >= 17
    assert a.recall >= 0.7
    assert a.precision >= 0.7
    assert a.scores[90] > a.threshold and a.scores[210] > a.threshold


def test_outputs_and_bad_inputs(tmp_path: Path) -> None:
    r = pmu_iforest(CSV, output_csv=tmp_path / "o.csv", output_png=tmp_path / "o.png")
    assert (tmp_path / "o.png").stat().st_size > 1000
    assert (tmp_path / "o.csv").read_text().startswith("time_s,v_mag_pu,d_mag_pu")
    assert r.scores.min() > 0 and r.scores.max() < 1
    t = np.arange(100) / 30.0
    with pytest.raises(ValueError, match="contamination"):
        pmu_iforest((t, np.ones(100), np.zeros(100), np.full(100, 50.0)), contamination=0.9)
    with pytest.raises(ValueError, match="16"):
        pmu_iforest((t[:5], np.ones(5), np.zeros(5), np.full(5, 50.0)))


def test_run_demo_script() -> None:
    done = subprocess.run([sys.executable, str(TOOL / "examples" / "run_demo.py")],
                          check=True, capture_output=True, text=True)
    assert "pmu-iforest:" in done.stdout
    assert (TOOL / "examples" / "output" / "pmu_demo.png").is_file()
