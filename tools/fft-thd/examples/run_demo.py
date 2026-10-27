"""Run the fft-thd demo on the synthetic 50 Hz waveform."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from fft_thd import fft_thd, format_table

    csv_path = tool_dir / "examples" / "data" / "synthetic_waveform.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "fft_thd_demo.png"
    out_csv = out_dir / "fft_thd_demo.csv"
    result = fft_thd(
        csv_path,
        f0=50,
        n_harmonics=7,
        window="auto",
        amp_floor_ratio=0.002,
        output_png=out_png,
        output_csv=out_csv,
        show=False,
    )
    print(
        "fft-thd: "
        f"f0={result.f0:.6g} Hz fs={result.fs:.6g} Hz "
        f"N={result.n_samples} window={result.window} "
        f"THD={result.thd_percent:.4f}%"
    )
    print(format_table(result))
    print("analytic noise-free THD for 8%, 5%, and 2% harmonics: 9.6437%")
    print(f"saved {out_png}")
    print(f"saved {out_csv}")


if __name__ == "__main__":
    main()
