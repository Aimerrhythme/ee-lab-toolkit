"""Run the grid-to-graph demo on the synthetic 4-bus network."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from grid_to_graph_export import format_table, grid_to_graph_export

    csv_path = tool_dir / "examples" / "data" / "synthetic_grid.csv"
    out_dir = tool_dir / "examples" / "output"
    bundle = out_dir / "grid_to_graph_export"
    png = out_dir / "grid_to_graph_export_demo.png"
    result = grid_to_graph_export(
        csv_path,
        output_dir=bundle,
        output_png=png,
        show=False,
    )
    print(format_table(result))
    print(f"saved {png}")
    print(f"saved {bundle}")


if __name__ == "__main__":
    main()
