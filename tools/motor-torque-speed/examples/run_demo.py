"""Run the motor torque-speed demo on the synthetic classroom cases."""

from __future__ import annotations

import math
import sys
from pathlib import Path


def _fixed(value: float) -> str:
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return f"{value:.4f}"


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from motor_torque_speed import format_table, motor_torque_speed

    csv_path = tool_dir / "examples" / "data" / "motor_cases.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "motor_torque_speed_demo.png"
    out_csv = out_dir / "motor_torque_speed_demo.csv"
    result = motor_torque_speed(
        csv_path,
        output_png=out_png,
        output_csv=out_csv,
        show=False,
    )
    for case in result.cases:
        if case.motor == "induction":
            print(
                "motor-torque-speed: "
                f"name={case.name} motor=induction "
                f"T_start={case.torque_start_nm:.4f} "
                f"T_bd={case.torque_breakdown_nm:.4f} "
                f"s_bd={case.slip_breakdown:.6f} "
                f"n_rated={_fixed(case.speed_rated_rpm)} "
                f"T_rated={_fixed(case.torque_rated_nm)}"
            )
        else:
            print(
                "motor-torque-speed: "
                f"name={case.name} motor={case.motor} "
                f"n0={_fixed(case.speed_noload_rpm)} "
                f"T_stall={case.torque_stall_nm:.4f} "
                f"I_stall={case.i_stall_a:.4f}"
            )
    print(format_table(result))
    print(f"saved {out_png}")
    print(f"saved {out_csv}")


if __name__ == "__main__":
    main()
