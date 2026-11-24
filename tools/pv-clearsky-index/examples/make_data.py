"""Write the synthetic hourly GHI CSV (deterministic, no random numbers)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from datetime import date, timedelta

from pv_clearsky_index import clearsky_ghi

# (factor, wobble) per day: clear ~0.95, cloudy ~0.55 with swings, overcast ~0.2
PATTERN = [(0.96, 0.0), (0.97, 0.02), (0.60, 0.30), (0.55, 0.35), (0.20, 0.05),
           (0.95, 0.03), (0.15, 0.04), (0.65, 0.30), (0.98, 0.0), (0.50, 0.30)]


def synthetic_rows(start="2026-06-01", lat=25.0):
    d0 = date.fromisoformat(start)
    rows = []
    for i, (f, w) in enumerate(PATTERN):
        d = d0 + timedelta(days=i)
        hrs = np.arange(24, dtype=float)
        cs, _ = clearsky_ghi(np.full(24, d.timetuple().tm_yday), hrs, lat)
        ghi = cs * np.clip(f + w * np.sin(2.7 * hrs + i), 0.05, 1.05)
        rows += [(d.isoformat(), int(h), round(float(g), 1)) for h, g in zip(hrs, ghi)]
    return rows


def write_csv(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("date,hour,ghi\n")
        for d, h, g in rows:
            f.write(f"{d},{h},{g}\n")


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "data" / "synthetic_ghi.csv"
    write_csv(out, synthetic_rows())
    print(f"wrote {out}")
