"""Run the load-csv-plot demo on the synthetic CSV."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from load_csv_plot import load_csv_plot

    csv_path = tool_dir / "examples" / "data" / "synthetic_load_kw.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "load_csv_plot_demo.png"
    result = load_csv_plot(
        csv_path,
        agg="daily_mean",
        outlier_method="iqr",
        fill_method="interpolate",
        output_png=out_png,
        show=False,
    )
    print(
        "load-csv-plot: "
        f"rows={result.n_rows} missing={result.n_missing} "
        f"outliers={result.n_outliers} mean={result.mean_kw:.2f} kW"
    )
    print(
        "planted defects: 2024-06-01 04:00 missing, "
        "2024-06-02 12:00 = 950 kW, 2024-06-03 18:00 = 5 kW"
    )
    print(f"saved {out_png}")
    print(result.daily_mean.to_string(index=False))


if __name__ == "__main__":
    main()
