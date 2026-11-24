"""Classify the synthetic days by clear-sky index and save the CSV + figure."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from pv_clearsky_index import format_summary, pv_clearsky_index

    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = pv_clearsky_index(tool_dir / "examples" / "data" / "synthetic_ghi.csv", lat=25.0,
                          output_csv=out_dir / "clearsky_index_demo.csv",
                          output_png=out_dir / "clearsky_index_demo.png")
    print(format_summary(r))
    print(f"outputs in {out_dir}")


if __name__ == "__main__":
    main()
