"""Convert the synthetic VOC sample to YOLO format and draw a check figure."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from insulator_yolo_label_convert import format_summary, insulator_yolo_label_convert

    out_dir = tool_dir / "examples" / "output" / "yolo"
    result = insulator_yolo_label_convert(
        tool_dir / "examples" / "data" / "voc", out_dir,
        output_png=tool_dir / "examples" / "output" / "insulator_check.png")
    print(format_summary(result))
    print(f"outputs in {out_dir.parent}")


if __name__ == "__main__":
    main()
