"""Smoke tests for the evcs-load-window Python tool."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from evcs_load_window import evcs_load_window

DATA = TOOL / "examples" / "data" / "synthetic_sessions.csv"


def _write(tmp_path, body):
    p = tmp_path / "s.csv"
    p.write_text("session_id,start_time,end_time,power_kw\n" + body)
    return p


def test_demo_data_cleaning_and_shapes(tmp_path):
    r = evcs_load_window(DATA, output_csv=tmp_path / "w.csv")
    assert r.n_sessions == 48 and r.n_dropped == 4
    assert r.X.shape == (39, 8) and r.y.shape == (39, 4)
    assert r.load_kw.max() < 900
    assert (tmp_path / "w.csv").read_text().startswith("window_start,x_0")


def test_overlap_weighting_and_windows(tmp_path):
    # 60 kW from 00:10 to 00:40 -> bin0 = 60*5/15, bin1 = 60*15/15, bin2 = 60*10/15
    p = _write(tmp_path, "a,2024-01-01 00:10:00,2024-01-01 00:40:00,60\n")
    r = evcs_load_window(p, input_len=1, horizon=1, stride=1)
    assert np.allclose(r.load_kw, [20, 60, 40])
    assert r.X.shape == (2, 1)
    assert np.allclose(r.X[:, 0], [20, 60]) and np.allclose(r.y[:, 0], [60, 40])
    assert np.isclose(r.load_kw.sum() * 15, 60 * 30)  # energy conserved
