"""Extract capacity fade from the synthetic cycling CSV; save CSV + figure."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from battery_capacity_fade import battery_capacity_fade_extract, format_summary

    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = battery_capacity_fade_extract(tool_dir / "examples" / "data" / "synthetic_cycles.csv",
                                      output_csv=out_dir / "capacity_fade_demo.csv",
                                      output_png=out_dir / "capacity_fade_demo.png")
    print(format_summary(r))
    print(f"outputs in {out_dir}")


if __name__ == "__main__":
    main()

