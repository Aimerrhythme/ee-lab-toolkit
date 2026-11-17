"""Write the synthetic wind–power CSV used by the demo and the smoke test.

Each 0.5 m/s bin holds four wind speeds. At each speed the power is the
nameplate cubic plus {-40, 0, +40} kW, clipped at 0 so the normal band stays
nonnegative. Planted rows use the labels ``negative``, ``shutdown``,
``curtailment``, and ``outlier``. Those speeds lie on a 0.25 m/s grid and do
not coincide with the normal samples. No random generator.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from wind_curve_binning_filter import theoretical_power_kw

P_RATED_KW = 2000.0
V_CUT_IN = 3.0
V_RATED = 12.0
V_CUT_OUT = 25.0
BIN_WIDTH = 0.5
V_MAX = 26.0
SPEEDS_PER_BIN = 4
POWER_OFFSETS_KW = (-40.0, 0.0, 40.0)
CURTAIL_KW = 450.0
HIGH_EXTRA_KW = 700.0
LOW_SCATTER_KW = 1500.0

OUT_CSV = TOOL / "examples" / "data" / "synthetic_wind_power.csv"


def _theory(speed: float) -> float:
    return float(
        theoretical_power_kw([speed], P_RATED_KW, V_CUT_IN, V_RATED, V_CUT_OUT)[0]
    )


def synthetic_rows() -> list[tuple[float, float, str]]:
    """Return ``(wind_mps, power_kw, label)`` in file order."""

    rows: list[tuple[float, float, str]] = []
    n_bins = int(round(V_MAX / BIN_WIDTH))
    for bin_id in range(n_bins):
        left = bin_id * BIN_WIDTH
        for sample in range(SPEEDS_PER_BIN):
            speed = left + (sample + 0.5) / SPEEDS_PER_BIN * BIN_WIDTH
            base = _theory(speed)
            for offset in POWER_OFFSETS_KW:
                rows.append((speed, max(0.0, base + offset), "normal"))

    for speed, power in (
        (5.5, -40.0),
        (8.5, -15.0),
        (12.5, -80.0),
        (16.5, -5.0),
        (20.5, -120.0),
    ):
        rows.append((speed, power, "negative"))

    for speed, power in (
        (7.0, 0.0),
        (9.0, 5.0),
        (11.0, 10.0),
        (13.0, 0.0),
        (15.0, 15.0),
        (18.0, 8.0),
        (21.0, 0.0),
        (23.0, 20.0),
        (14.5, 35.0),
        (17.5, 40.0),
    ):
        rows.append((speed, power, "shutdown"))

    for step in range(26):
        rows.append((9.25 + 0.5 * step, CURTAIL_KW, "curtailment"))

    for speed in (8.0, 10.5, 14.0, 16.0, 19.0):
        rows.append((speed, _theory(speed) + HIGH_EXTRA_KW, "outlier"))
    for speed in (12.0, 18.5):
        rows.append((speed, LOW_SCATTER_KW, "outlier"))
    for speed, power in ((1.0, 500.0), (2.0, 800.0), (25.25, 1500.0), (25.75, 900.0)):
        rows.append((speed, power, "outlier"))
    return rows


def write_csv(path: Path = OUT_CSV) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["wind_mps", "power_kw", "label"])
        for speed, power, label in synthetic_rows():
            writer.writerow([f"{speed:.16g}", f"{power:.16g}", label])
    return path


def main() -> None:
    path = write_csv()
    print(f"wrote {path} rows={len(synthetic_rows())}")


if __name__ == "__main__":
    main()
