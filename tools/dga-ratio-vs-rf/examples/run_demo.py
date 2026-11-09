"""Run the DGA ratio-vs-random-forest demo on the synthetic CSV."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from dga_ratio_vs_rf import dga_ratio_vs_rf  # noqa: E402


def main() -> None:
    out = TOOL / "examples" / "output"
    result = dga_ratio_vs_rf(
        TOOL / "examples" / "data" / "synthetic_dga_ppm.csv",
        n_trees=50, max_depth=6, mtry=2, seed=0,
        output_csv=out / "dga_demo.csv", output_png=out / "dga_demo.png",
    )
    for i, sid in enumerate(result.sample_ids):
        if result.split[i] == "test":
            print(f"dga: id={sid} true={result.true_label[i]} rule={result.rule_label[i]} "
                  f"rf={result.rf_label[i]} rf_prob={result.rf_prob[i]:.3f}")
    print(result.summary)
    print(f"saved {result.output_csv}")
    print(f"saved {result.output_png}")


if __name__ == "__main__":
    main()
