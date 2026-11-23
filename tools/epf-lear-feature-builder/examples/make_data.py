"""Generate the synthetic hourly price + load-forecast CSV (6 weeks, fully synthetic)."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np


def synthetic_rows(n_days=42, seed=11):
    rng = np.random.default_rng(seed)
    h = np.arange(24)
    shape = 8 * np.exp(-0.5 * ((h - 8) / 2.0) ** 2) + 12 * np.exp(-0.5 * ((h - 19) / 2.5) ** 2)
    start = date(2026, 2, 2)  # a Monday
    rows, level = [], 42.0
    for d in range(n_days):
        day = start + timedelta(days=d)
        level += rng.normal(0, 1.2)
        weekend = day.weekday() >= 5
        load = 900 + (-120 if weekend else 0) + 150 * shape / shape.max() + rng.normal(0, 15, 24)
        for hh in range(24):
            price = level - (7 if weekend else 0) + shape[hh] + 0.02 * (load[hh] - 900) + rng.normal(0, 1.5)
            rows.append((day.isoformat(), hh, round(float(price), 2), round(float(load[hh]), 1)))
    return rows


def write_csv(path, rows=None):
    rows = rows if rows is not None else synthetic_rows()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "hour", "price", "load_forecast"])
        w.writerows(rows)


if __name__ == "__main__":
    write_csv(Path(__file__).parent / "data" / "synthetic_price_load.csv")
