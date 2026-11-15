"""Regenerate examples/data/synthetic_meters.csv (fixed seed, fully synthetic)."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np

START = date(2026, 3, 2)  # a Monday
N_DAYS = 56


def main() -> None:
    rng = np.random.default_rng(7)
    rows = []
    for cid, label in [("M01", "normal"), ("M02", "normal"), ("M03", "suspect"), ("M04", "normal")]:
        for d in range(N_DAYS):
            day = START + timedelta(days=d)
            wk = day.weekday()
            if cid == "M01":      # office-like: weekdays high
                v = (11.0 if wk < 5 else 5.0) + rng.normal(0, 0.6)
            elif cid == "M02":    # household: weekend higher
                v = (8.0 if wk < 5 else 12.0) + rng.normal(0, 0.8)
            elif cid == "M03":    # drops sharply after day 28
                v = (10.0 if d < 28 else 2.5) + rng.normal(0, 0.5)
            else:                 # normal, but many gaps
                v = 9.0 + 2.0 * np.sin(2 * np.pi * d / 7) + rng.normal(0, 0.5)
            val = f"{max(v, 0.0):.3f}"
            if cid == "M01" and d in (10, 11, 40):
                val = ""
            if cid == "M02" and d == 20:
                val = "NaN"
            if cid == "M03" and d == 33:
                val = "-1"        # sensor glitch (negative)
            if cid == "M04" and (d in (5, 6, 7, 8, 9, 30, 31) or d >= 52):
                val = ""
            if cid == "M04" and d == 0:
                continue          # record absent altogether
            rows.append(f"{cid},{label},{day.isoformat()},{val}")
    out = Path(__file__).resolve().parent / "data" / "synthetic_meters.csv"
    out.write_text("customer_id,label,date,kwh\n" + "\n".join(rows) + "\n")
    print(f"wrote {out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
