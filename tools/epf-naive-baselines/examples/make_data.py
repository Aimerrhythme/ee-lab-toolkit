"""Generate the synthetic hourly price CSV (8 weeks, fully synthetic)."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np


def synthetic_rows(n_days=56, seed=7):
    rng = np.random.default_rng(seed)
    h = np.arange(24)
    shape = (8 * np.exp(-0.5 * ((h - 8) / 2.0) ** 2)
             + 12 * np.exp(-0.5 * ((h - 19) / 2.5) ** 2) - 6 * (h < 5))
    start = date(2026, 1, 5)  # a Monday
    rows = []
    level = 45.0
    for d in range(n_days):
        day = start + timedelta(days=d)
        level += rng.normal(0, 1.5)
        weekend = day.weekday() >= 5
        base = level - (8 if weekend else 0)
        spike = 25 if d == 40 else 0
        for hh in range(24):
            price = base + (0.6 if weekend else 1.0) * shape[hh] + rng.normal(0, 2.0)
            if spike and hh in (18, 19, 20):
                price += spike
            rows.append((day.isoformat(), hh, round(float(price), 2)))
    return rows


def write_csv(path, rows=None):
    rows = rows if rows is not None else synthetic_rows()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "hour", "price"])
        w.writerows(rows)


if __name__ == "__main__":
    write_csv(Path(__file__).parent / "data" / "synthetic_day_ahead_price.csv")
