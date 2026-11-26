"""Run the NILM window preparation on the synthetic meter CSV."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from nilm_window_prep import format_summary, nilm_window_prep

    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    res = nilm_window_prep(
        tool_dir / "examples" / "data" / "synthetic_meter.csv",
        step_s=6, max_gap_steps=3, window=11, stride=3,
        output_csv=out_dir / "nilm_windows_demo.csv",
        output_png=out_dir / "nilm_window_prep_demo.png",
    )
    print(format_summary(res))
    print(f"outputs in {out_dir}")


if __name__ == "__main__":
    main()
