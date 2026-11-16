"""Run the EL image loader / split / augmentation demo on the synthetic data."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from el_image_loader_aug import el_image_loader_aug, format_table

    out_dir = tool_dir / "examples" / "output"
    png = out_dir / "el_montage_demo.png"
    res = el_image_loader_aug(tool_dir / "examples" / "data" / "labels.csv",
                              output_dir=out_dir / "el_image_loader_aug", output_png=png)
    print(format_table(res))
    print(f"saved {png}")


if __name__ == "__main__":
    main()
