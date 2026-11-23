"""Build the LEAR feature matrix from the synthetic price/load CSV."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from epf_lear_feature_builder import epf_lear_feature_builder, format_summary

    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = epf_lear_feature_builder(
        tool_dir / "examples" / "data" / "synthetic_price_load.csv",
        lags=(1, 2, 3, 7),
        output_csv=out_dir / "lear_features_demo.csv",
        output_png=out_dir / "lear_features_demo.png",
    )
    print(format_summary(result))
    print(f"outputs in {out_dir}")


if __name__ == "__main__":
    main()
