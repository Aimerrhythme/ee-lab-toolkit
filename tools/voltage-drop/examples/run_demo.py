"""Run the voltage-drop demo on one section and the synthetic feeder."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from voltage_drop import format_single_line, format_table, voltage_drop

    single = voltage_drop(
        length_km=2.0,
        r_ohm_per_km=0.4,
        x_ohm_per_km=0.35,
        i_a=80.0,
        pf=0.8,
        v_nominal=10_000.0,
    )
    print(format_single_line(single))

    csv_path = tool_dir / "examples" / "data" / "synthetic_feeder_sections.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "voltage_drop_demo.png"
    out_csv = out_dir / "voltage_drop_demo.csv"
    result = voltage_drop(
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
