"""Run the imbalanced-classification bench on the synthetic scored CSV."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from theft_imbalance_metrics import format_summary, theft_imbalance_metrics

    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = theft_imbalance_metrics(
        tool_dir / "examples" / "data" / "synthetic_theft_scores.csv",
        threshold=0.5,
        output_csv=out_dir / "theft_imbalance_metrics_demo.csv",
        output_png=out_dir / "theft_imbalance_metrics_demo.png",
    )
    print(format_summary(result))
    print(f"outputs in {out_dir}")


if __name__ == "__main__":
    main()
