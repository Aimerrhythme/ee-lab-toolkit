"""Run the pu-convert demo on the synthetic quantity table."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from pu_convert import format_table, pu_convert

    csv_path = tool_dir / "examples" / "data" / "synthetic_quantities.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "pu_convert_demo.png"
    out_csv = out_dir / "pu_convert_demo.csv"
    result = pu_convert(
        csv_path,
        output_png=out_png,
        output_csv=out_csv,
        show=False,
    )
    print(
        "pu-convert: "
        f"system={result.system} S_base={result.s_base:.0f} VA "
        f"Z_hv={result.z_base_hv:.6g} ohm Z_lv={result.z_base_lv:.6g} ohm "
        f"rows={len(result.rows)}"
    )
    print(format_table(result))
    print(f"saved {out_png}")
    print(f"saved {out_csv}")


if __name__ == "__main__":
    main()
