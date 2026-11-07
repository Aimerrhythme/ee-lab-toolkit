"""Sweep the synthetic radial feeder and export protection-labeled samples."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from pp_fault_synth_export import format_preview, format_table, pp_fault_synth_export

    csv_path = tool_dir / "examples" / "data" / "synthetic_radial_feeder.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "pp_fault_synth_export_demo.png"
    out_csv = out_dir / "pp_fault_synth_export_demo.csv"
    result = pp_fault_synth_export(
        csv_path,
        engine="zbus",
        output_png=out_png,
        output_csv=out_csv,
        show=False,
    )
    print(format_preview(result))
    print(format_table(result))
    print(f"saved {out_png}")
    print(f"saved {out_csv}")


if __name__ == "__main__":
    main()
