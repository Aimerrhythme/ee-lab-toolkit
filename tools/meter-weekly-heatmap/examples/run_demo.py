"""Run the meter weekly heatmap demo on the synthetic CSV."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from meter_weekly_heatmap import format_table, meter_weekly_heatmap

    out_dir = tool_dir / "examples" / "output"
    png = out_dir / "meter_weekly_heatmap_demo.png"
    res = meter_weekly_heatmap(tool_dir / "examples" / "data" / "synthetic_meters.csv",
                               output_dir=out_dir / "meter_weekly_heatmap", output_png=png)
    print(format_table(res))
    print(f"saved {png}")


if __name__ == "__main__":
    main()
