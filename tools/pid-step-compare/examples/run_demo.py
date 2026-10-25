"""Run the pid-step-compare demo on the sample plant and PID sets."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from pid_step_compare import format_metrics_table, pid_step_compare

    plant_csv = tool_dir / "examples" / "data" / "plant.csv"
    pid_csv = tool_dir / "examples" / "data" / "pid_sets.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "pid_step_compare_demo.png"
    result = pid_step_compare(
        plant_csv,
        pid_csv,
        t_final=20,
        dt=0.01,
        setpoint=1,
        output_png=out_png,
        show=False,
    )
    num = ", ".join(f"{value:g}" for value in result.plant["num"])
    den = ", ".join(f"{value:g}" for value in result.plant["den"])
    print(
        "pid-step-compare: "
        f"form={result.plant['form']} num=[{num}] den=[{den}] "
        f"setpoint={result.setpoint:g}"
    )
    print(format_metrics_table(result.metrics))
    print(f"saved {out_png}")


if __name__ == "__main__":
    main()
