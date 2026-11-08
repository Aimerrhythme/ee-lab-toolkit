"""Fit the synthetic residential day with a polynomial and a shallow MLP."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from load_curve_dnn_fit import format_table, load_curve_dnn_fit

    csv_path = tool_dir / "examples" / "data" / "synthetic_daily_load_kw.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "load_curve_dnn_fit_demo.png"
    out_csv = out_dir / "load_curve_dnn_fit_demo.csv"
    result = load_curve_dnn_fit(
        csv_path,
        degree=5,
        hidden=8,
        epochs=2000,
        learning_rate=0.05,
        seed=0,
        normalize="peak",
        output_png=out_png,
        output_csv=out_csv,
        show=False,
    )
    print(
        "load-curve-dnn-fit: "
        f"poly_rmse={result.poly_rmse:.4f} poly_mae={result.poly_mae:.4f} "
        f"poly_max_abs={result.poly_max_abs:.4f} "
        f"dnn_rmse={result.dnn_rmse:.4f} dnn_mae={result.dnn_mae:.4f} "
        f"dnn_max_abs={result.dnn_max_abs:.4f}"
    )
    print(format_table(result))
    print(f"saved {out_png}")
    print(f"saved {out_csv}")


if __name__ == "__main__":
    main()
