"""Write a synthetic aggregate/appliance power CSV (seed fixed, no real data)."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def synthetic_rows(n=900, dt=2, seed=7):
    rng = np.random.default_rng(seed)
    t = np.arange(n) * dt
    fridge = np.where((t // 240) % 2 == 0, 90.0, 0.0)
    kettle = np.zeros(n)
    for s in (200, 700, 1250):           # three kettle runs, 90 s each
        kettle[(t >= s) & (t < s + 90)] = 2000.0
    agg = 60.0 + fridge + kettle + rng.normal(0, 4, n)
    keep = np.ones(n, bool)
    keep[300:306] = False                 # 12 s gap: fillable at step 6, max_gap 3
    keep[600:660] = False                 # 120 s gap: stays missing
    return [(int(t[i]), round(float(agg[i]), 2), round(float(kettle[i]), 2))
            for i in range(n) if keep[i]]


def write_csv(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("timestamp_s,aggregate_w,appliance_w\n")
        for r in rows:
            f.write(f"{r[0]},{r[1]},{r[2]}\n")


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "data" / "synthetic_meter.csv"
    write_csv(out, synthetic_rows())
    print(out)
