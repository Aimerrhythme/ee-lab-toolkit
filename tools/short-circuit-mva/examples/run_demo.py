"""Run the short-circuit MVA demo on one point, one transformer, and a feeder."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from short_circuit_mva import format_single_line, format_table, short_circuit_mva

    point = short_circuit_mva(s_mva=250.0, v_kv=10.0)
    print(format_single_line(point))

    from_current = short_circuit_mva(i_ka=10.0, v_kv=10.0)
    print(format_single_line(from_current))

    transformer = short_circuit_mva(
        kind="transformer",
        s_rated_mva=20.0,
        z_percent=8.0,
        x_over_r=10.0,
        v_kv=10.0,
    )
    print(format_single_line(transformer))

    csv_path = tool_dir / "examples" / "data" / "synthetic_short_circuit_stages.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "short_circuit_mva_demo.png"
    out_csv = out_dir / "short_circuit_mva_demo.csv"
    result = short_circuit_mva(
        csv_path,
        output_png=out_png,
        output_csv=out_csv,
        show=False,
    )
    print(format_table(result))
    print(f"saved {out_png}")
    print(f"saved {out_csv}")


if __name__ == "__main__":
    main()
