"""Demo: load the synthetic ETT-format CSV, window it, plot oil temperature vs load."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from ett_window_loader import load_and_window, load_ett_csv

CSV = TOOL / "examples" / "data" / "synthetic_ett.csv"
OUT = TOOL / "examples" / "output"


def main():
    res = load_and_window(CSV, input_len=96, pred_len=24, split=(0.6, 0.2, 0.2), target="OT")
    print(res.summary())
    for name in ("train", "val", "test"):
        ws = getattr(res, name)
        print(f"{name}: X{ws.X.shape} Y{ws.Y.shape} first_start_row={ws.start[0]}")
    print(f"train mean OT={res.mean[-1]:.3f} std OT={res.std[-1]:.3f}")

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available; figure skipped")
        return
    dates, cols, data = load_ett_csv(CSV)
    load = data[:, cols.index("HUFL")] + data[:, cols.index("MUFL")] + data[:, cols.index("LUFL")]
    ot = data[:, cols.index("OT")]
    b1, b2, _ = res.bounds
    x = np.arange(len(ot))
    fig, ax1 = plt.subplots(figsize=(10, 4))
    ax1.plot(x, ot, color="tab:red", lw=1, label="OT (oil temperature)")
    ax1.set_xlabel("hour index")
    ax1.set_ylabel("OT (deg C)", color="tab:red")
    ax2 = ax1.twinx()
    ax2.plot(x, load, color="tab:blue", lw=0.6, alpha=0.6, label="useful load (HUFL+MUFL+LUFL)")
    ax2.set_ylabel("useful load (synthetic units)", color="tab:blue")
    for b in (b1, b2):
        ax1.axvline(b, color="k", ls="--", lw=1)
    ax1.set_title("Synthetic ETT-format data: oil temperature vs load (dashed = train/val/test split)")
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / "ett_window_loader_demo.png"
    fig.tight_layout()
    fig.savefig(png, dpi=120)
    print(f"figure saved: {png}")


if __name__ == "__main__":
    main()
