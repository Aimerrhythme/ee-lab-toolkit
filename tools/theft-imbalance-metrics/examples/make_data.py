"""Generate the synthetic scored theft-detection CSV (fixed seed, no real data)."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def synthetic_rows(n=2000, prevalence=0.05, seed=0):
    """Return (y, plain, weighted).

    plain: scores of a model trained without class weights (positives rarely
    reach 0.5). weighted: same ranking shifted up in logit space, mimicking a
    class-weighted fit. Both are invented numbers, not a real detector.
    """
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < prevalence).astype(int)
    plain = np.where(y == 1, rng.beta(2.5, 6.0, n), rng.beta(1.0, 12.0, n))
    plain = np.clip(plain, 1e-4, 1 - 1e-4)
    logit = np.log(plain / (1 - plain))
    weighted = 1 / (1 + np.exp(-(logit + 1.8)))
    return y, plain, weighted


def write_csv(path, y, plain, weighted):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fh.write("y_true,score_plain,score_weighted\n")
        for a, b, c in zip(y, plain, weighted):
            fh.write(f"{int(a)},{b:.6f},{c:.6f}\n")


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "data" / "synthetic_theft_scores.csv"
    write_csv(out, *synthetic_rows())
    print(f"wrote {out}")
