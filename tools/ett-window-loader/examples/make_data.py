"""Generate the SYNTHETIC ETT-format sample (not real ETT data)."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

COLUMNS = ["date", "HUFL", "HULL", "MUFL", "MULL", "LUFL", "LULL", "OT"]


def synthetic_rows(n=720, seed=7):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    day = 2 * np.pi * t / 24
    week = 2 * np.pi * t / (24 * 7)
    hufl = 8 + 4 * np.sin(day - 1.5) + 1.0 * np.sin(week) + rng.normal(0, 0.4, n)
    hull = 2 + 1.0 * np.sin(day - 1.5) + rng.normal(0, 0.2, n)
    mufl = 5 + 3 * np.sin(day - 1.2) + rng.normal(0, 0.3, n)
    mull = 1.5 + 0.8 * np.sin(day - 1.2) + rng.normal(0, 0.15, n)
    lufl = 3 + 1.2 * np.sin(day - 1.0) + rng.normal(0, 0.2, n)
    lull = 1.0 + 0.3 * np.sin(day - 1.0) + rng.normal(0, 0.1, n)
    load = hufl + mufl + lufl
    # oil temperature: slow first-order lag of load plus a slow seasonal drift
    ot = np.empty(n)
    ot[0] = 30.0
    for i in range(1, n):
        ot[i] = ot[i - 1] + 0.12 * (22 + 1.4 * load[i] - ot[i - 1]) + rng.normal(0, 0.15)
    ot += 3 * np.sin(2 * np.pi * t / n)
    start = datetime(2020, 1, 1)
    out = []
    for i in range(n):
        vals = [hufl[i], hull[i], mufl[i], mull[i], lufl[i], lull[i], ot[i]]
        out.append([(start + timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S")] + [f"{v:.3f}" for v in vals])
    return out


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)


if __name__ == "__main__":
    write_csv(Path(__file__).parent / "data" / "synthetic_ett.csv", synthetic_rows())
