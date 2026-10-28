"""Run the sine-triangle PWM demo on the two classroom cases."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from pwm_waveform import format_table, pwm_waveform

    csv_path = tool_dir / "examples" / "data" / "pwm_cases.csv"
    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("bipolar_ma08", "unipolar_ma08"):
        out_png = out_dir / f"pwm_waveform_demo_{name}.png"
        out_csv = out_dir / f"pwm_waveform_demo_{name}.csv"
        result = pwm_waveform(
            csv_path,
            name=name,
            output_png=out_png,
            output_csv=out_csv,
            show=False,
        )
        thd = "undefined" if result.thd_percent != result.thd_percent else f"{result.thd_percent:.4f}%"
        print(
            "pwm-waveform: "
            f"name={result.name} mode={result.mode} "
            f"m_a={result.m_a:.4g} m_f={result.m_f:.6g} "
            f"V1={result.fundamental_amplitude:.4f} "
            f"V1_analytic={result.fundamental_analytic:.4f} "
            f"THD={thd}"
        )
        print(format_table(result))
        print(f"saved {out_png}")
        print(f"saved {out_csv}")


if __name__ == "__main__":
    main()
