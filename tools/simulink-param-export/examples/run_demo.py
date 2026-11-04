"""Round-trip the synthetic DC-motor parameter table and print it."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from simulink_param_export import param_rows_equal, simulink_param_export

    csv_path = tool_dir / "examples" / "data" / "dc_speed_params.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "simulink_param_export_demo.csv"
    result = simulink_param_export(csv_path, output_csv=out_csv, strict=True)
    again = simulink_param_export(out_csv, strict=True)
    if not param_rows_equal(result.rows, again.rows):
        raise SystemExit("round-trip mismatch")
    print(f"simulink-param-export: rows={result.n_rows} errors={result.n_errors}")
    print(result.table_text)
    print(result.assignment_text)
    print(f"round-trip ok: {result.n_rows} rows")
    print(f"saved {result.output_csv}")


if __name__ == "__main__":
    main()
