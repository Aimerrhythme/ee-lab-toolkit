"""Run the wind-curve binning demo on the synthetic turbine scatter."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from wind_curve_binning_filter import wind_curve_binning_filter

    csv_path = tool_dir / "examples" / "data" / "synthetic_wind_power.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "wind_curve_binning_filter_demo.png"
    out_csv = out_dir / "wind_curve_binning_filter_demo.csv"
    out_bins = out_dir / "wind_curve_binning_filter_demo_bins.csv"
    result = wind_curve_binning_filter(
        csv_path,
        bin_width=0.5,
        v_min=0.0,
        v_cut_in=3.0,
        v_rated=12.0,
        v_cut_out=25.0,
        p_rated_kw=2000.0,
        output_csv=out_csv,
        output_bins_csv=out_bins,
        output_png=out_png,
        show=False,
    )
    print(result.summary)
    rated = next(row for row in result.bins if row.v_left == 12.0)
    print(
        "bin v=[12,12.5) "
        f"n_raw={rated.n_raw} n_clean={rated.n_clean} "
        f"median_clean_kw={rated.median_clean_kw:.4f} "
        f"q1_kw={rated.q1_kw:.4f} q3_kw={rated.q3_kw:.4f} "
        f"theory_kw={rated.theory_kw:.4f}"
    )
    print(f"saved {out_png}")
    print(f"saved {out_csv}")
    print(f"saved {out_bins}")


if __name__ == "__main__":
    main()
