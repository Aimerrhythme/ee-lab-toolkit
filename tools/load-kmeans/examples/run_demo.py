"""Cluster the synthetic commercial, residential, and weekend load days."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from load_kmeans import format_table, load_kmeans

    csv_path = tool_dir / "examples" / "data" / "synthetic_load_kw.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "load_kmeans_demo.png"
    out_csv = out_dir / "load_kmeans_demo.csv"
    result = load_kmeans(
        csv_path,
        k=3,
        seed=0,
        normalize="peak",
        output_png=out_png,
        output_csv=out_csv,
        show=False,
    )
    for date, label, peak_kw, day_sse in zip(result.dates, result.labels, result.peak_kw, result.day_sse):
        print(
            "load-kmeans: "
            f"date={date} label={int(label)} "
            f"peak_kw={peak_kw:.4f} day_sse={day_sse:.6f}"
        )
    print(format_table(result))
    print(f"saved {out_png}")
    print(f"saved {out_csv}")


if __name__ == "__main__":
    main()
