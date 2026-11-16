"""Regenerate the synthetic EL-like cell images and labels.csv (deterministic)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from matplotlib import image as mpimg

N = 32
PROBAS = [0.0] * 16 + [1 / 3] * 8 + [2 / 3] * 6 + [1.0] * 10


def make_cell(rng, proba, poly):
    y, x = np.mgrid[0:N, 0:N] / (N - 1)
    img = 0.55 + 0.15 * x + 0.05 * rng.standard_normal((N, N))      # brighter to the right
    img -= 0.18 * (np.abs(((x * 3) % 1) - 0.5) < 0.04)               # busbar-like dark lines
    if poly:
        img += 0.08 * np.sin(8 * x + 5 * y)                          # grain texture
    if proba > 0.9:                                                  # crack: diagonal dark line + dead blob
        img -= 0.45 * (np.abs(y - 0.8 * x - 0.1) < 0.03)
        img -= 0.40 * (((x - 0.75) ** 2 + (y - 0.25) ** 2) < 0.01)
    elif proba > 0.5:                                                # shorter crack
        img -= 0.40 * ((np.abs(y - 0.8 * x - 0.1) < 0.03) & (x < 0.5))
    elif proba > 0.2:                                                # faint dark spot
        img -= 0.25 * (((x - 0.3) ** 2 + (y - 0.7) ** 2) < 0.012)
    return np.clip(img, 0, 1)


def main() -> None:
    root = Path(__file__).resolve().parent / "data"
    (root / "images").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    lines = ["path,proba,type"]
    for i, p in enumerate(PROBAS):
        poly = i % 2 == 1
        name = f"images/cell_{i:03d}.png"
        mpimg.imsave(str(root / name), make_cell(rng, p, poly), cmap="gray", vmin=0, vmax=1)
        lines.append(f"{name},{p:.4f},{'poly' if poly else 'mono'}")
    (root / "labels.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
