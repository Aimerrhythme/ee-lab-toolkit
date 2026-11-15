"""Smoke tests for meter-weekly-heatmap."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from meter_weekly_heatmap import fill_gaps, meter_weekly_heatmap  # noqa: E402

CSV = TOOL / "examples" / "data" / "synthetic_meters.csv"


def test_fill_gaps_interior_only():
    v = np.array([np.nan, 1.0, np.nan, np.nan, 4.0, np.nan, np.nan, np.nan, np.nan, 9.0, np.nan])
    out, mask = fill_gaps(v, 3)
    assert np.allclose(out[2:4], [2.0, 3.0])
    assert np.isnan(out[0]) and np.isnan(out[-1])       # edges untouched
    assert np.isnan(out[5:9]).all()                      # gap of 4 > max_gap
    assert mask.sum() == 2


def test_demo_csv(tmp_path):
    res = meter_weekly_heatmap(CSV, output_dir=tmp_path / "o", output_png=tmp_path / "a.png")
    assert res.n_weeks == 8 and len(res.customers) == 4
    m01, m02, m03, m04 = res.customers
    assert m01.n_filled == 3 and m01.n_missing == 0      # 2-day + 1-day gap
    assert m02.n_filled == 1                             # NaN text
    assert m03.n_filled == 1                             # negative = missing
    assert m04.n_missing > 0 and abs(m04.missing_rate - 0.2) < 1e-9
    assert m01.weekend_ratio < 0.6 < 1.0 < m02.weekend_ratio
    for c in res.customers:
        v = c.norm[~np.isnan(c.norm)]
        assert v.min() == 0.0 and v.max() == 1.0
    assert (tmp_path / "a.png").stat().st_size > 0
    assert (tmp_path / "o" / "matrix_long.csv").exists()
    assert (tmp_path / "o" / "summary.csv").exists()
