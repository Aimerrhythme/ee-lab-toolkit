"""Smoke tests for the load-curve DNN fit tool."""

from __future__ import annotations

import csv
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from load_curve_dnn_fit import format_table, load_curve_dnn_fit

CSV = TOOL / "examples" / "data" / "synthetic_daily_load_kw.csv"
DEMO_DAY = "2024-03-11"
N_SAMPLES = 96
NOISE_KW = 1.2


def base_kw(hour: float) -> float:
    """Residential day: morning shoulder, midday hump, evening peak."""

    morning = 28.0 * math.exp(-((hour - 7.5) / 1.6) ** 2)
    midday = 12.0 * math.exp(-((hour - 12.5) / 2.2) ** 2)
    evening = 62.0 * math.exp(-((hour - 19.2) / 1.8) ** 2)
    return 18.0 + morning + midday + evening


def noise_kw(index: int) -> float:
    state = (1664525 * (1000 + index) + 1013904223) % 4294967296
    return (2.0 * state / 4294967296.0 - 1.0) * NOISE_KW


def demo_power(index: int) -> float:
    return base_kw(index * 0.25) + noise_kw(index)


def demo_timestamp(index: int) -> str:
    minute = index * 15
    return f"{DEMO_DAY} {minute // 60:02d}:{minute % 60:02d}:00"


def write_demo_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "power_kw"])
        for index in range(N_SAMPLES):
            writer.writerow([demo_timestamp(index), f"{demo_power(index):.10f}"])


def test_degree_zero_and_straight_line_are_exact() -> None:
    flat = load_curve_dnn_fit([2.0, 4.0, 2.0, 4.0], degree=0, normalize="none", epochs=1, hidden=1)
    assert flat.poly_coeff.tolist() == pytest.approx([3.0])
    assert flat.poly_kw.tolist() == pytest.approx([3.0, 3.0, 3.0, 3.0])
    assert flat.poly_rmse == pytest.approx(1.0)
    assert flat.poly_mae == pytest.approx(1.0)
    assert flat.poly_max_abs == pytest.approx(1.0)
    assert flat.poly_mse == pytest.approx(1.0)
    assert flat.date == "day-01"
    assert flat.minute.tolist() == pytest.approx([0.0, 360.0, 720.0, 1080.0])
    assert flat.u.tolist() == pytest.approx([-1.0, -0.5, 0.0, 0.5])
    assert flat.n_samples == 4
    assert flat.averaged is False
    assert flat.activation == "tanh"
    assert format_table(flat) == flat.summary
    assert "degree=0" in flat.summary

    line = load_curve_dnn_fit([6.0, 8.0, 10.0, 12.0], degree=1, normalize="none", epochs=1, hidden=1, seed=0)
    assert line.poly_coeff.tolist() == pytest.approx([10.0, 4.0], abs=1e-10)
    assert line.poly_rmse == pytest.approx(0.0, abs=1e-10)
    assert line.poly_mse == pytest.approx(0.0, abs=1e-12)
    assert math.sqrt(line.poly_mse) * line.scale_kw == pytest.approx(line.poly_rmse, abs=1e-12)


def test_normalization_scales_and_time_units() -> None:
    peak = load_curve_dnn_fit(
        [0.0, 6.0, 12.0, 18.0],
        [10.0, 40.0, 20.0, 30.0],
        degree=0,
        normalize="peak",
        epochs=1,
        hidden=1,
        time_unit="hour",
    )
    assert peak.minute.tolist() == pytest.approx([0.0, 360.0, 720.0, 1080.0])
    assert peak.y.tolist() == pytest.approx([0.25, 1.0, 0.5, 0.75])
    assert peak.peak_kw == pytest.approx(40.0)
    assert peak.scale_kw == pytest.approx(40.0)
    assert peak.offset_kw == pytest.approx(0.0)
    assert peak.poly_kw.tolist() == pytest.approx([25.0, 25.0, 25.0, 25.0])
    assert math.sqrt(peak.poly_mse) * peak.scale_kw == pytest.approx(peak.poly_rmse, abs=1e-12)

    stretched = load_curve_dnn_fit([10.0, 20.0, 40.0], degree=1, normalize="minmax", epochs=1, hidden=1)
    assert stretched.y.tolist() == pytest.approx([0.0, 1.0 / 3.0, 1.0])
    assert stretched.min_kw == pytest.approx(10.0)
    assert stretched.scale_kw == pytest.approx(30.0)
    assert stretched.offset_kw == pytest.approx(10.0)
    assert stretched.poly_kw[0] == pytest.approx(stretched.poly_y[0] * 30.0 + 10.0)

    minutes = load_curve_dnn_fit([0.0, 15.0, 30.0, 45.0], [1.0, 2.0, 3.0, 4.0], degree=1, time_unit="minute", epochs=1, hidden=1)
    assert minutes.minute.tolist() == pytest.approx([0.0, 15.0, 30.0, 45.0])
    fractions = load_curve_dnn_fit([0.0, 0.25, 0.5], [5.0, 6.0, 7.0], degree=1, time_unit="dayfrac", normalize="none", epochs=1, hidden=1)
    assert fractions.hour.tolist() == pytest.approx([0.0, 6.0, 12.0])
    assert fractions.date == "day-01"

    labeled = load_curve_dnn_fit([1.0, 2.0, 3.0], degree=0, normalize="none", epochs=1, hidden=1, day="2024-03-11")
    assert labeled.date == "2024-03-11"
    assert labeled.dates == ["2024-03-11"]


def test_network_is_deterministic_and_changes_with_seed() -> None:
    left = load_curve_dnn_fit([1.0, 2.0, 4.0, 3.0], degree=1, hidden=3, epochs=2, seed=0, normalize="none")
    again = load_curve_dnn_fit([1.0, 2.0, 4.0, 3.0], degree=1, hidden=3, epochs=2, seed=0, normalize="none")
    other = load_curve_dnn_fit([1.0, 2.0, 4.0, 3.0], degree=1, hidden=3, epochs=2, seed=1, normalize="none")
    longer = load_curve_dnn_fit([1.0, 2.0, 4.0, 3.0], degree=1, hidden=3, epochs=3, seed=0, normalize="none")
    assert again.w1.tolist() == pytest.approx(left.w1.tolist())
    assert again.b2 == pytest.approx(left.b2)
    assert again.dnn_kw.tolist() == pytest.approx(left.dnn_kw.tolist())
    assert other.w1.tolist() != pytest.approx(left.w1.tolist())
    assert longer.dnn_kw.tolist() != pytest.approx(left.dnn_kw.tolist())
    assert left.w1.shape == (3,)
    assert left.w2.shape == (3,)
    assert left.b1.shape == (3,)
    assert left.poly_coeff.shape == (2,)
    assert all(math.isfinite(value) for value in left.dnn_kw)


def test_several_days_average_and_csv_cleaning(tmp_path: Path) -> None:
    path = tmp_path / "days.csv"
    path.write_text(
        "timestamp,power_kw\n"
        "2024-03-11 00:00:00,10\n"
        "2024-03-11 06:00:00,12\n"
        "2024-03-11 12:00:00,30\n"
        "2024-03-12 00:00:00,20\n"
        "2024-03-12 12:00:00,50\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="same minute-of-day grid"):
        load_curve_dnn_fit(path, degree=0, epochs=1, hidden=1, normalize="none")

    matched = tmp_path / "matched.csv"
    matched.write_text(
        "timestamp;power_kw\n"
        "2024-03-11 00:00:00;10\n"
        "2024-03-11 12:00:00;30\n"
        "2024-03-12 00:00:00;20\n"
        "2024-03-12 12:00:00;50\n",
        encoding="utf-8",
    )
    averaged = load_curve_dnn_fit(matched, degree=0, epochs=1, hidden=1, normalize="none")
    assert averaged.averaged is True
    assert averaged.date == "typical"
    assert averaged.dates == ["2024-03-11", "2024-03-12"]
    assert averaged.n_days == 2
    assert averaged.n_rows == 4
    assert averaged.power_kw.tolist() == pytest.approx([15.0, 40.0])
    assert averaged.poly_kw.tolist() == pytest.approx([27.5, 27.5])
    assert averaged.poly_rmse == pytest.approx(12.5)

    duplicate = tmp_path / "dup.csv"
    duplicate.write_text(
        "timestamp,power_kw\n"
        "2024-03-11 12:00:00,30\n"
        "2024-03-11 00:00:00,10\n"
        "2024-03-11 00:00:00,99\n",
        encoding="utf-8",
    )
    kept = load_curve_dnn_fit(duplicate, degree=0, epochs=1, hidden=1, normalize="none")
    assert kept.n_duplicates == 1
    assert kept.n_rows == 2
    assert kept.power_kw.tolist() == pytest.approx([10.0, 30.0])
    assert kept.hour.tolist() == pytest.approx([0.0, 12.0])

    chinese = tmp_path / "cn.csv"
    chinese.write_text("时间,功率\n2024-03-11 08:00,10\n2024-03-11 09:00,12\n", encoding="utf-8")
    named = load_curve_dnn_fit(chinese, degree=0, normalize="none", epochs=1, hidden=1, time_col="时间", power_col="功率")
    assert named.power_kw.tolist() == pytest.approx([10.0, 12.0])
    assert named.n_missing == 0

    gap = tmp_path / "gap.csv"
    gap.write_text(
        "timestamp,power_kw\n"
        "2024-03-11 00:00:00,4\n"
        "2024-03-11 01:00:00,\n"
        "2024-03-11 02:00:00,8\n"
        "2024-03-11 05:00:00,6\n",
        encoding="utf-8",
    )
    missing = load_curve_dnn_fit(gap, degree=0, normalize="none", epochs=1, hidden=1)
    assert missing.n_missing == 1
    assert missing.n_rows == 3
    assert missing.minute.tolist() == pytest.approx([0.0, 120.0, 300.0])
    assert math.isnan(missing.step_minutes)
    assert "step_min=nan" in missing.summary


def test_synthetic_curve_dnn_beats_the_polynomial(tmp_path: Path) -> None:
    assert CSV.is_file()
    loaded = list(csv.DictReader(CSV.open(encoding="utf-8")))
    assert len(loaded) == N_SAMPLES
    for index, row in enumerate(loaded):
        assert row["timestamp"] == demo_timestamp(index)
        assert float(row["power_kw"]) == pytest.approx(demo_power(index), abs=1e-8)
        assert demo_power(index) > 0.0

    png = tmp_path / "fit.png"
    out_csv = tmp_path / "fit.csv"
    result = load_curve_dnn_fit(
        CSV,
        degree=5,
        hidden=8,
        epochs=2000,
        learning_rate=0.05,
        seed=0,
        normalize="peak",
        output_png=png,
        output_csv=out_csv,
    )
    assert result.n_samples == 96
    assert result.n_rows == 96
    assert result.n_days == 1
    assert result.n_missing == 0
    assert result.n_duplicates == 0
    assert result.date == DEMO_DAY
    assert result.normalize == "peak"
    assert result.step_minutes == pytest.approx(15.0)
    assert result.degree == 5
    assert result.hidden == 8
    assert result.epochs == 2000
    assert result.poly_rmse == pytest.approx(10.25219531760178, rel=1e-9)
    assert result.dnn_rmse == pytest.approx(2.495601026087696, rel=1e-4)
    assert result.poly_rmse > 9.0
    assert result.dnn_rmse < result.poly_rmse
    assert result.dnn_rmse < 4.0
    assert result.dnn_mae < result.poly_mae
    assert result.dnn_max_abs < result.poly_max_abs
    assert math.sqrt(result.poly_mse) * result.scale_kw == pytest.approx(result.poly_rmse, rel=1e-9)
    assert math.sqrt(result.dnn_mse) * result.scale_kw == pytest.approx(result.dnn_rmse, rel=1e-9)
    assert result.poly_residual_kw.tolist() == pytest.approx((result.poly_kw - result.power_kw).tolist())
    assert result.dnn_residual_kw.tolist() == pytest.approx((result.dnn_kw - result.power_kw).tolist())
    assert png.is_file() and png.stat().st_size > 1000
    text = out_csv.read_text(encoding="utf-8")
    assert text.startswith("hour,minute,power_kw,poly_kw,dnn_kw,poly_residual_kw,dnn_residual_kw\n")
    assert "normalize=peak" in result.summary
    assert "hidden=8" in result.summary
    assert "date=2024-03-11" in result.summary
    assert "poly_rmse=10.2522" in result.summary
    assert "dnn_rmse=2.4956" in result.summary
    assert "poly_max_abs=27.0413" in result.summary
    assert "dnn_max_abs=6.5276" in result.summary
    assert result.fig is None

    repeat = load_curve_dnn_fit(CSV, degree=5, hidden=8, epochs=2000, learning_rate=0.05, seed=0, normalize="peak")
    assert repeat.dnn_rmse == pytest.approx(result.dnn_rmse, abs=0.0)
    assert repeat.w1.tolist() == pytest.approx(result.w1.tolist())
    assert repeat.poly_coeff.tolist() == pytest.approx(result.poly_coeff.tolist())
    assert repeat.summary == result.summary


def test_bad_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="degree must be a non-negative integer"):
        load_curve_dnn_fit([1.0, 2.0, 3.0], degree=-1)
    with pytest.raises(ValueError, match="degree must be lower than"):
        load_curve_dnn_fit([1.0, 2.0, 3.0], degree=3, epochs=1, hidden=1)
    with pytest.raises(ValueError, match="hidden must be a positive integer"):
        load_curve_dnn_fit([1.0, 2.0, 3.0], hidden=0)
    with pytest.raises(ValueError, match="epochs must be a positive integer"):
        load_curve_dnn_fit([1.0, 2.0, 3.0], epochs=0)
    with pytest.raises(ValueError, match="seed must be a non-negative integer"):
        load_curve_dnn_fit([1.0, 2.0, 3.0], seed=-1)
    with pytest.raises(ValueError, match="learning_rate must be a positive finite number"):
        load_curve_dnn_fit([1.0, 2.0, 3.0], learning_rate=0)
    with pytest.raises(ValueError, match="beta1 must be in"):
        load_curve_dnn_fit([1.0, 2.0, 3.0], beta1=1)
    with pytest.raises(ValueError, match="epsilon must be a positive finite number"):
        load_curve_dnn_fit([1.0, 2.0, 3.0], epsilon=-1)
    with pytest.raises(ValueError, match="normalize must be peak, minmax, or none"):
        load_curve_dnn_fit([1.0, 2.0, 3.0], normalize="max")
    with pytest.raises(ValueError, match="time_unit must be auto, hour, minute, or dayfrac"):
        load_curve_dnn_fit([0.0, 1.0], [1.0, 2.0], time_unit="second")
    with pytest.raises(ValueError, match="positive peak"):
        load_curve_dnn_fit([-2.0, -1.0, -4.0], normalize="peak", degree=1, epochs=1, hidden=1)
    with pytest.raises(ValueError, match="load to vary"):
        load_curve_dnn_fit([3.0, 3.0, 3.0], normalize="minmax", degree=1, epochs=1, hidden=1)
    with pytest.raises(ValueError, match="at least 2 samples"):
        load_curve_dnn_fit([1.0], epochs=1, hidden=1)
    with pytest.raises(ValueError, match="finite"):
        load_curve_dnn_fit([1.0, math.inf], epochs=1, hidden=1)
    with pytest.raises(ValueError, match="same length"):
        load_curve_dnn_fit([0.0, 1.0], [4.0], epochs=1, hidden=1)
    with pytest.raises(ValueError, match=r"\[0, 24\)"):
        load_curve_dnn_fit([0.0, 24.0], [1.0, 2.0], time_unit="hour", epochs=1, hidden=1)
    with pytest.raises(ValueError, match=r"\[0, 1440\)"):
        load_curve_dnn_fit([0.0, 1440.0], [1.0, 2.0], time_unit="minute", epochs=1, hidden=1)
    with pytest.raises(ValueError, match="day fractions"):
        load_curve_dnn_fit([0.0, 1.0], [1.0, 2.0], time_unit="dayfrac", epochs=1, hidden=1)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        load_curve_dnn_fit([1.0, 2.0], day="11-03-2024", epochs=1, hidden=1)
    with pytest.raises(ValueError, match="parameter name"):
        load_curve_dnn_fit("degree")
    with pytest.raises(ValueError, match="pass a CSV path"):
        load_curve_dnn_fit()
    with pytest.raises(ValueError, match="time_unit applies when time is passed"):
        load_curve_dnn_fit([1.0, 2.0, 3.0], time_unit="hour", epochs=1, hidden=1)
    with pytest.raises(ValueError, match="show must be true or false"):
        load_curve_dnn_fit([1.0, 2.0], show="yes")
    with pytest.raises(FileNotFoundError, match="CSV not found"):
        load_curve_dnn_fit(tmp_path / "missing.csv")
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_curve_dnn_fit(empty)
    blank = tmp_path / "blank.csv"
    blank.write_text("timestamp,power_kw\n2024-03-11 00:00:00,\n2024-03-11 01:00:00,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No power samples"):
        load_curve_dnn_fit(blank)
    aware = datetime(2024, 3, 11, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="naive local time"):
        load_curve_dnn_fit([aware, datetime(2024, 3, 11, 13, 0, tzinfo=timezone.utc)], [1.0, 2.0], epochs=1, hidden=1)
    with pytest.raises(ValueError, match="could not parse timestamp"):
        load_curve_dnn_fit(["2024-02-30 00:00:00", "2024-03-11 01:00:00"], [1.0, 2.0], epochs=1, hidden=1)


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "load-curve-dnn-fit:" in completed.stdout
    assert "poly_rmse=" in completed.stdout
    assert "dnn_rmse=" in completed.stdout
    assert "normalize=peak" in completed.stdout
    assert "date=2024-03-11" in completed.stdout
    png = TOOL / "examples" / "output" / "load_curve_dnn_fit_demo.png"
    out_csv = TOOL / "examples" / "output" / "load_curve_dnn_fit_demo.csv"
    assert png.is_file() and png.stat().st_size > 1000
    assert out_csv.read_text(encoding="utf-8").startswith("hour,minute,power_kw,poly_kw,dnn_kw,")


if __name__ == "__main__":
    write_demo_csv(CSV)
    print(f"wrote {CSV}")
