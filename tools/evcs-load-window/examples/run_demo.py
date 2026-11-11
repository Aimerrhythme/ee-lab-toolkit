"""Run the evcs-load-window demo on the synthetic session CSV."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from evcs_load_window import evcs_load_window

    csv_path = tool_dir / "examples" / "data" / "synthetic_sessions.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = evcs_load_window(csv_path, output_csv=out_dir / "windows.csv")
    print(
        f"evcs-load-window: sessions={r.n_sessions} dropped={r.n_dropped} "
        f"bins={len(r.load_kw)} windows={r.X.shape[0]} "
        f"X={r.X.shape} y={r.y.shape} peak={r.load_kw.max():.2f} kW"
    )
    print("planted defects: 4 bad rows (end<=start, missing power, 0 kW, 900 kW)")
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.step(r.time, r.load_kw, where="post")
    ax.set_xlabel("time")
    ax.set_ylabel("station load (kW)")
    ax.set_title("Synthetic EVCS load, 15-min bins")
    fig.autofmt_xdate()
    fig.tight_layout()
    png = out_dir / "evcs_load_window_demo.png"
    fig.savefig(png, dpi=120)
    print(f"saved {png}")
    print(f"saved {r.output_csv}")


if __name__ == "__main__":
    main()
