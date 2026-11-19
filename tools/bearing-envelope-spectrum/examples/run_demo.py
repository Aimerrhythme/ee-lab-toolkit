"""Run the envelope-spectrum pipeline on the synthetic outer-race-fault signal."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from bearing_envelope_spectrum import bearing_envelope_spectrum

    out = tool_dir / "examples" / "output"
    out.mkdir(parents=True, exist_ok=True)
    res = bearing_envelope_spectrum(
        tool_dir / "examples" / "data" / "synthetic_bearing_vibration.csv",
        rpm=1797.0, band=(2000.0, 5000.0),
        output_csv=out / "bearing_envelope_demo.csv",
        output_png=out / "bearing_envelope_demo.png")
    print(res.summary)
    print(f"outputs in {out}")


if __name__ == "__main__":
    main()
