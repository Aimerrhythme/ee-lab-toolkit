"""Run the naive price baselines on the synthetic hourly price series."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from epf_naive_baselines import epf_naive_baselines, format_summary

    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = epf_naive_baselines(
        tool_dir / "examples" / "data" / "synthetic_day_ahead_price.csv",
        eval_start_day=7,
        output_csv=out_dir / "epf_naive_baselines_demo.csv",
        output_png=out_dir / "epf_naive_baselines_demo.png",
    )
    print(format_summary(result))
    print(f"outputs in {out_dir}")


if __name__ == "__main__":
    main()
