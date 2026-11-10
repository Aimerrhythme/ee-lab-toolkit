"""Run the PMU Isolation Forest demo on the synthetic CSV."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from pmu_iforest import pmu_iforest  # noqa: E402


def main() -> None:
    out = TOOL / "examples" / "output"
    r = pmu_iforest(TOOL / "examples" / "data" / "synthetic_pmu.csv",
                    n_trees=100, contamination=0.03, seed=0,
                    output_csv=out / "pmu_demo.csv", output_png=out / "pmu_demo.png")
    print("flagged times (s):", " ".join(f"{x:.3f}" for x in r.anomaly_times))
    print(r.summary)
    print(f"saved {r.output_csv}")
    print(f"saved {r.output_png}")


if __name__ == "__main__":
    main()
