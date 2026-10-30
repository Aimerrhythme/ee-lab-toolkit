"""Run the PV daily-feature demo on the synthetic clear, cloud, and flicker days."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from pv_daily_features import format_table, pv_daily_features

    csv_path = tool_dir / "examples" / "data" / "synthetic_pv_kw.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "pv_daily_features_demo.png"
    out_csv = out_dir / "pv_daily_features_demo.csv"
    result = pv_daily_features(
        csv_path,
        p_rated_kw=100,
        ramp_minutes=10,
        output_png=out_png,
        output_csv=out_csv,
        show=False,
    )
    for day in result.days:
        print(
            "pv-daily-features: "
            f"date={day.date} "
            f"Ppeak={day.p_peak_kw:.4f} "
            f"t_peak={day.t_peak} "
            f"E={day.energy_kwh:.4f} "
            f"VI={day.variability_index:.6f} "
            f"ramp_up={day.ramp_up_kw_per_min:.4f} "
            f"ramp_down={day.ramp_down_kw_per_min:.4f}"
        )
    print(format_table(result))
    print(f"saved {out_png}")
    print(f"saved {out_csv}")


if __name__ == "__main__":
    main()
