"""Smoke tests for the bess-tou-qlearn-toy Python tool."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from bess_tou_qlearn_toy import bess_tou_qlearn_toy

DATA = TOOL / "examples" / "data" / "tou_prices.csv"


def test_learned_beats_greedy_and_writes_csv(tmp_path):
    r = bess_tou_qlearn_toy(DATA, output_csv=tmp_path / "s.csv")
    assert r.q.shape == (24, 6, 3)
    assert r.learned_cost < r.greedy_cost < 0
    assert r.learned_soc.min() >= 0 and r.learned_soc.max() <= 5
    assert (tmp_path / "s.csv").read_text().startswith("hour,price,learned_action")


def test_flat_price_means_idle():
    r = bess_tou_qlearn_toy(np.full(6, 0.5), n_soc=3)
    assert (r.learned_action == 0).all() and abs(r.learned_cost) < 1e-9
