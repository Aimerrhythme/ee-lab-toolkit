"""Run the bode-demo examples: first-order, damping sweep, PID loop, textbook margins."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from bode_demo import bode_demo, format_margins_table

    csv_path = tool_dir / "examples" / "data" / "systems.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    groups = (
        (
            "first-order",
            ["tau=1", "tau=0.2"],
            out_dir / "bode_demo_first_order.png",
        ),
        (
            "damping sweep",
            ["zeta=0.2", "zeta=0.5", "zeta=0.707", "zeta=1", "zeta=1.5"],
            out_dir / "bode_demo_damping.png",
        ),
        (
            "PID/plant open loop",
            ["P", "PI", "PID"],
            out_dir / "bode_demo_pid_loop.png",
        ),
        (
            "textbook margins",
            ["textbook"],
            out_dir / "bode_demo_textbook.png",
        ),
    )
    for title, names, png in groups:
        result = bode_demo(csv_path, names=names, output_png=png, show=False)
        print(
            f"bode-demo {title}: n={result.n_points} "
            f"w=[{result.w_min:.6g}, {result.w_max:.6g}]"
        )
        for row in result.margins:
            num = ", ".join(f"{value:g}" for value in row.num)
            den = ", ".join(f"{value:g}" for value in row.den)
            print(f"  {row.name}: num=[{num}] den=[{den}]")
        print(format_margins_table(result.margins))
        print(f"saved {png}")


if __name__ == "__main__":
    main()
