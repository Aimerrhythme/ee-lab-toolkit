"""Smoke tests for ett-window-loader, including a no-leakage check."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))
sys.path.insert(0, str(TOOL / "examples"))

from ett_window_loader import load_and_window, load_ett_csv, split_bounds
from make_data import synthetic_rows, write_csv

CSV = TOOL / "examples" / "data" / "synthetic_ett.csv"


def test_shapes_and_counts():
    r = load_and_window(CSV, 96, 24)
    assert r.bounds == (432, 576, 720)
    assert r.train.X.shape == (432 - 120 + 1, 96, 7)
    assert r.val.Y.shape == (144 - 120 + 1, 24)
    assert r.test.X.shape[0] == 25


def test_train_only_statistics():
    r = load_and_window(CSV, 48, 12)
    _, cols, data = load_ett_csv(CSV)
    b1 = r.bounds[0]
    assert np.allclose(r.mean, data[:b1].mean(axis=0))
    assert np.allclose(r.std, data[:b1].std(axis=0))
    flat = r.train.X[:, 0, :]
    assert abs(flat.mean()) < 0.2
    assert not np.allclose(r.val.X.reshape(-1, 7).mean(axis=0), 0, atol=1e-3)


def test_no_leakage_future_change_does_not_touch_train():
    """Corrupt val/test rows: train windows and train statistics must not change."""
    base = load_and_window(CSV, 48, 12)
    rows = synthetic_rows()
    b1 = base.bounds[0]
    for i in range(b1, len(rows)):
        rows[i][1:] = [f"{float(v) * 5 + 100:.3f}" for v in rows[i][1:]]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "mod.csv"
        write_csv(p, rows)
        mod = load_and_window(p, 48, 12)
    assert np.array_equal(base.mean, mod.mean)
    assert np.array_equal(base.std, mod.std)
    assert np.array_equal(base.train.X, mod.train.X)
    assert np.array_equal(base.train.Y, mod.train.Y)


def test_windows_stay_inside_their_split():
    r = load_and_window(CSV, 48, 12)
    b1, b2, b3 = r.bounds
    assert r.train.start.max() + 48 + 12 <= b1
    assert r.val.start.min() >= b1 and r.val.start.max() + 60 <= b2
    assert r.test.start.min() >= b2 and r.test.start.max() + 60 <= b3


def test_window_content_matches_raw():
    r = load_and_window(CSV, 10, 3, stride=5)
    _, cols, data = load_ett_csv(CSV)
    j = cols.index("OT")
    k = 4
    s = r.train.start[k]
    assert s == 20
    scaled = (data - r.mean) / r.std
    assert np.allclose(r.train.X[k], scaled[s : s + 10])
    assert np.allclose(r.train.Y[k], scaled[s + 10 : s + 13, j])
    assert np.allclose(r.inverse_target(r.train.Y[k]), data[s + 10 : s + 13, j])


def test_bad_arguments():
    with pytest.raises(ValueError):
        load_and_window(CSV, 10, 3, target="XX")
    with pytest.raises(ValueError):
        split_bounds(100, (0.5, 0.5, 0.5))
    with pytest.raises(ValueError):
        load_and_window(CSV, 0, 3)
