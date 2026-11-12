"""Tabular Q-learning for a battery on a time-of-use (TOU) tariff (toy).

State = (hour, SOC level); action = discharge / idle / charge one SOC level.
Training is a deterministic full sweep of all (hour, SOC, action) cells, so the
Python and MATLAB versions give the same numbers (no random exploration).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ACTIONS = (-1, 0, 1)  # discharge, idle, charge (SOC levels per hour)


@dataclass
class QResult:
    prices: np.ndarray        # (H,) price per hour
    q: np.ndarray             # (H, n_soc, 3) learned Q table
    learned_soc: np.ndarray   # (H+1,) SOC level trajectory
    learned_action: np.ndarray  # (H,) in {-1,0,1}
    greedy_soc: np.ndarray
    greedy_action: np.ndarray
    learned_cost: float       # net cost of the day (yuan), incl. terminal credit
    greedy_cost: float
    n_soc: int
    soc0: int
    output_csv: str | None = None


def read_prices(csv_path) -> np.ndarray:
    """Read ``hour,price`` rows (sorted by hour) into a price vector."""
    with open(csv_path, newline="") as f:
        rows = [(int(r["hour"]), float(r["price"])) for r in csv.DictReader(f)]
    rows.sort()
    return np.array([p for _, p in rows], dtype=float)


def _step_cost(price, a, e_step_kwh, eta):
    """Grid bill of one hour: charging draws e/eta, discharging returns e*eta."""
    grid = e_step_kwh / eta if a > 0 else (-e_step_kwh * eta if a < 0 else 0.0)
    return price * grid


def _rollout(policy, prices, soc0, n_soc, e_step_kwh, eta, term_value):
    H = len(prices)
    soc = np.zeros(H + 1, dtype=int)
    act = np.zeros(H, dtype=int)
    soc[0] = soc0
    cost = 0.0
    for t in range(H):
        a = policy(t, soc[t])
        act[t] = a
        soc[t + 1] = soc[t] + a
        cost += _step_cost(prices[t], a, e_step_kwh, eta)
    cost -= term_value * (soc[H] - soc0)
    return soc, act, cost


def bess_tou_qlearn_toy(csv_path, n_soc=6, soc0=0, e_step_kwh=10.0, eta=0.95,
                        alpha=0.5, n_iter=200, output_csv=None) -> QResult:
    """Train tabular Q-learning and compare with a threshold-greedy policy.

    ``csv_path`` may be an ``hour,price`` CSV path or a numpy price vector.
    Costs are in yuan for one day; negative means net profit. Leftover SOC at
    the end of the day is credited at ``mean(price) * eta * e_step_kwh`` per
    level (relative to ``soc0``) so that "empty the battery" is not free.
    """
    prices = csv_path if isinstance(csv_path, np.ndarray) else read_prices(csv_path)
    H = len(prices)
    term_value = float(prices.mean()) * eta * e_step_kwh

    # Terminal value of each SOC level (relative to the starting level).
    vT = term_value * (np.arange(n_soc) - soc0)
    q = np.zeros((H, n_soc, 3))
    valid = np.zeros((n_soc, 3), dtype=bool)
    for s in range(n_soc):
        for k, a in enumerate(ACTIONS):
            valid[s, k] = 0 <= s + a < n_soc

    for _ in range(n_iter):
        qn = q.copy()
        for t in range(H):
            vnext = vT if t == H - 1 else q[t + 1].max(axis=1, where=valid, initial=-np.inf)
            for s in range(n_soc):
                for k, a in enumerate(ACTIONS):
                    if not valid[s, k]:
                        continue
                    r = -_step_cost(prices[t], a, e_step_kwh, eta)
                    qn[t, s, k] += alpha * (r + vnext[s + a] - q[t, s, k])
        q = qn

    qm = np.where(valid[None, :, :], q, -np.inf)

    def learned(t, s):
        return ACTIONS[int(np.argmax(qm[t, s]))]

    lo = prices.min() + (prices.max() - prices.min()) / 3
    hi = prices.max() - (prices.max() - prices.min()) / 3

    def greedy(t, s):
        if prices[t] <= lo and s < n_soc - 1:
            return 1
        if prices[t] >= hi and s > 0:
            return -1
        return 0

    ls, la, lc = _rollout(learned, prices, soc0, n_soc, e_step_kwh, eta, term_value)
    gs, ga, gc = _rollout(greedy, prices, soc0, n_soc, e_step_kwh, eta, term_value)

    res = QResult(prices, q, ls, la, gs, ga, float(lc), float(gc), n_soc, soc0)
    if output_csv is not None:
        out = Path(output_csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="") as f:
            f.write("hour,price,learned_action,learned_soc_end,greedy_action,greedy_soc_end\n")
            for t in range(H):
                f.write(f"{t},{prices[t]:.2f},{la[t]},{ls[t+1]},{ga[t]},{gs[t+1]}\n")
        res.output_csv = str(out)
    return res
