"""Smoke tests for the pv-daily-features Python tool."""

from __future__ import annotations

import csv
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")

import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from pv_daily_features import format_table, pv_daily_features

CSV = TOOL / "examples" / "data" / "synthetic_pv_kw.csv"
DATES = ("2024-06-21", "2024-06-22", "2024-06-23")
KINDS = ("clear", "cloud", "flicker")
CLOUD_KNOTS = (
    (0.0, 1.0),
    (570.0, 1.0),
    (600.0, 0.25),
    (615.0, 0.25),
    (645.0, 1.0),
    (780.0, 1.0),
    (800.0, 0.15),
    (840.0, 0.15),
    (880.0, 1.0),
    (1440.0, 1.0),
)


def clear_kw(minute: float) -> float:
    if minute < 360.0 or minute > 1080.0:
        return 0.0
    return 80.0 * math.sin(math.pi * (minute - 360.0) / 720.0)


def cloud_factor(minute: float) -> float:
    for index in range(len(CLOUD_KNOTS) - 1):
        left_m, left_v = CLOUD_KNOTS[index]
        right_m, right_v = CLOUD_KNOTS[index + 1]
        if minute <= right_m or index == len(CLOUD_KNOTS) - 2:
            weight = 0.0 if right_m == left_m else (minute - left_m) / (right_m - left_m)
            return left_v + (right_v - left_v) * weight
    return 1.0


def flicker_factor(minute: float) -> float:
    if 660.0 <= minute < 780.0 and int(round(minute)) % 10 == 5:
        return 0.4
    return 1.0


def demo_power(kind: str, minute: float) -> float:
    base = clear_kw(minute)
    if kind == "clear":
        return base
    if kind == "cloud":
        return base * cloud_factor(minute)
    if kind == "flicker":
        return base * flicker_factor(minute)
    raise AssertionError(kind)


def demo_minutes() -> np.ndarray:
    return np.arange(0, 1440, 5, dtype=float)


def write_demo_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "power_kw"])
        for date, kind in zip(DATES, KINDS):
            for minute in demo_minutes():
                hour, mm = divmod(int(minute), 60)
                stamp = f"{date} {hour:02d}:{mm:02d}:00"
                writer.writerow([stamp, f"{demo_power(kind, float(minute)):.16g}"])


def _day_from_kind(kind: str, **kwargs):
    minute = demo_minutes()
    power = np.array([demo_power(kind, float(value)) for value in minute])
    stamps = [f"2024-06-21 {int(value) // 60:02d}:{int(value) % 60:02d}:00" for value in minute]
    result = pv_daily_features(stamps, power, p_rated_kw=100, ramp_minutes=10, **kwargs)
    return result.days[0]


def test_piecewise_day_matches_the_trapezoid_and_the_ramp_definitions() -> None:
    minute = [0, 10, 20, 30, 40]
    power = [0, 10, 10, 0, 0]
    result = pv_daily_features(minute, power, p_rated_kw=10, ramp_minutes=10, day="2024-06-21")
    day = result.days[0]

    assert result.n_rows == 5
    assert result.n_missing == 0
    assert result.n_duplicates == 0
    assert result.p_rated_kw == 10
    assert math.isnan(result.p_on_kw)
    assert day.date == "2024-06-21"
    assert day.n_samples == 5
    assert day.resampled is False
    assert day.step_minutes == pytest.approx(10)
    assert day.p_peak_kw == pytest.approx(10)
    assert day.t_peak == "00:10:00"
    assert day.energy_kwh == pytest.approx(10 / 3)
    assert day.hours_span == pytest.approx(40 / 60)
    assert day.p_mean_kw == pytest.approx(5)
    assert day.capacity_factor == pytest.approx((10 / 3) / 240)
    assert day.p_on_kw == pytest.approx(0.2)
    assert day.t_on == "00:10:00"
    assert day.t_off == "00:20:00"
    assert day.hours_window == pytest.approx(10 / 60)
    assert day.hours_above == pytest.approx(1 / 3)
    assert day.variability_index == pytest.approx(1)
    assert day.ramp_up_kw_per_min == pytest.approx(1)
    assert day.ramp_down_kw_per_min == pytest.approx(-1)
    assert day.ramp_up_span_min == pytest.approx(10)
    assert day.t_ramp_up == "00:00:00"
    assert day.t_ramp_down == "00:20:00"
    assert day.ramp_step_up_kw_per_min == pytest.approx(1)
    assert day.ramp_step_down_kw_per_min == pytest.approx(-1)
    assert day.t_step_down == "00:20:00"
    assert day.hour == pytest.approx(np.array(minute) / 60.0)
    text = format_table(result)
    assert text.startswith("rows=5  missing=0  duplicates=0  days=1  ramp_min=10")
    assert "date=2024-06-21" in text
    assert "VI=1" in text
    assert "CF=0.0138889" in text

    tied = pv_daily_features([0, 10, 20, 30], [0, 5, 5, 0], day="2024-06-21").days[0]
    assert tied.t_peak == "00:10:00"
    assert tied.p_peak_kw == pytest.approx(5)

    flat = pv_daily_features([0, 10, 20], [1, 2, 3], ramp_minutes=10, day="2024-06-21").days[0]
    assert flat.ramp_up_kw_per_min == pytest.approx(0.1)
    assert flat.ramp_down_kw_per_min == pytest.approx(0.1)
    assert flat.t_ramp_up == "00:00:00"
    assert flat.t_ramp_down == "00:00:00"


def test_threshold_edges_single_sample_and_negative_power() -> None:
    off = pv_daily_features([0, 10, 20, 30, 40], [0, 10, 10, 0, 0], p_on_kw=10.1, day="2024-06-21")
    assert off.days[0].t_on == "nan"
    assert math.isnan(off.days[0].hours_window)
    assert off.days[0].hours_above == pytest.approx(0)
    assert "on=undefined" in format_table(off)

    explicit = pv_daily_features(
        [0, 10, 20, 30, 40],
        [0, 10, 10, 0, 0],
        p_on_kw=0,
        day="2024-06-21",
    ).days[0]
    assert explicit.t_on == "00:00:00"
    assert explicit.t_off == "00:40:00"
    assert explicit.hours_above == pytest.approx(40 / 60)

    single = pv_daily_features([12 * 60], [3], day="2024-06-21").days[0]
    assert single.n_samples == 1
    assert single.energy_kwh == pytest.approx(0)
    assert math.isnan(single.step_minutes)
    assert single.resampled is False
    assert single.t_peak == "12:00:00"
    assert single.p_on_kw == pytest.approx(0.15)
    assert single.hours_window == pytest.approx(0)
    assert single.hours_above == pytest.approx(0)
    assert math.isnan(single.ramp_up_kw_per_min)
    assert math.isnan(single.variability_index)
    assert math.isnan(single.capacity_factor)

    dead = pv_daily_features([0, 10, 20], [0, 0, 0], day="2024-06-21").days[0]
    assert dead.p_peak_kw == pytest.approx(0)
    assert dead.p_on_kw == pytest.approx(0)
    assert math.isnan(dead.variability_index)
    assert dead.ramp_step_up_kw_per_min == pytest.approx(0)

    negative = pv_daily_features([0, 30, 60], [-2, -1, -2], p_rated_kw=10, day="2024-06-21").days[0]
    assert negative.p_peak_kw == pytest.approx(-1)
    assert negative.t_peak == "00:30:00"
    assert negative.energy_kwh < 0
    assert negative.capacity_factor == pytest.approx(negative.energy_kwh / 240)
    assert math.isnan(negative.variability_index)
    assert "on=undefined" in format_table(
        pv_daily_features([0, 30, 60], [-2, -1, -2], day="2024-06-21")
    )


def test_short_record_has_step_ramps_but_no_window_and_resample_keeps_the_endpoint() -> None:
    short = pv_daily_features([0, 5], [0, 4], ramp_minutes=10, day="2024-06-21").days[0]
    assert math.isnan(short.ramp_up_kw_per_min)
    assert short.ramp_step_up_kw_per_min == pytest.approx(0.8)
    assert short.t_step_up == "00:00:00"
    assert np.all(np.isnan(short.ramp_kw_per_min))

    resampled = pv_daily_features([0, 10, 40], [0, 10, 0], step_minutes=10, day="2024-06-21").days[0]
    assert resampled.resampled is True
    assert resampled.step_minutes == pytest.approx(10)
    assert resampled.n_samples == 5
    assert resampled.minute == pytest.approx([0, 10, 20, 30, 40])
    assert resampled.power_kw == pytest.approx([0, 10, 20 / 3, 10 / 3, 0])
    energy = 0.5 * (
        (0 + 10) * 10 + (10 + 20 / 3) * 10 + (20 / 3 + 10 / 3) * 10 + (10 / 3 + 0) * 10
    ) / 60
    assert resampled.energy_kwh == pytest.approx(energy)

    uneven = pv_daily_features([0, 5, 10, 20], [0, 1, 2, 0], day="2024-06-21").days[0]
    assert uneven.resampled is True
    assert uneven.step_minutes == pytest.approx(5)
    assert uneven.minute[-1] == pytest.approx(20)

    with pytest.raises(ValueError, match="longer than the series"):
        pv_daily_features([0, 10], [0, 1], step_minutes=15, day="2024-06-21")


def test_calendar_rollover_duplicates_and_datetimes() -> None:
    result = pv_daily_features([1430, 1440, 1450], [1, 2, 4], day="2024-06-21", ramp_minutes=10)
    assert [day.date for day in result.days] == ["2024-06-21", "2024-06-22"]
    assert result.days[0].n_samples == 1
    assert result.days[0].t_peak == "23:50:00"
    assert result.days[1].t_peak == "00:10:00"
    assert result.days[1].energy_kwh == pytest.approx(0.5)
    assert result.days[1].ramp_step_up_kw_per_min == pytest.approx(0.2)

    new_year = pv_daily_features([1440], [1], day="2024-12-31").days[0]
    assert new_year.date == "2025-01-01"
    assert new_year.t_peak == "00:00:00"
    leap = pv_daily_features(["2024-02-29 00:30:00"], [1]).days[0]
    assert leap.date == "2024-02-29"
    assert leap.t_peak == "00:30:00"

    stamps = ["2024-06-21 01:00:00", "2024-06-21 01:00:00", "2024-06-21 02:00:00"]
    kept = pv_daily_features(stamps, [4, 9, 1])
    assert kept.n_duplicates == 1
    assert kept.n_rows == 2
    assert kept.days[0].p_peak_kw == pytest.approx(4)
    assert kept.days[0].power_kw == pytest.approx([4, 1])

    stamped = pv_daily_features(
        [datetime(2024, 6, 21, 6, 0, 0), datetime(2024, 6, 21, 12, 0, 0)],
        [0, 80],
    ).days[0]
    assert stamped.date == "2024-06-21"
    assert stamped.t_peak == "12:00:00"
    assert stamped.energy_kwh == pytest.approx(0.5 * 80 * 6)

    aware = datetime(2024, 6, 21, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="naive local time"):
        pv_daily_features([aware], [1])


def test_clear_cloud_and_flicker_days_separate_peak_ramp_and_variability() -> None:
    assert cloud_factor(570) == pytest.approx(1)
    assert cloud_factor(600) == pytest.approx(0.25)
    assert cloud_factor(800) == pytest.approx(0.15)
    assert demo_power("clear", 720) == pytest.approx(80)
    assert demo_power("cloud", 720) == pytest.approx(80)
    assert demo_power("flicker", 720) == pytest.approx(80)
    assert demo_power("flicker", 725) == pytest.approx(0.4 * clear_kw(725))

    clear = _day_from_kind("clear")
    cloud = _day_from_kind("cloud")
    flicker = _day_from_kind("flicker")
    for day in (clear, cloud, flicker):
        assert day.p_peak_kw == pytest.approx(80, abs=1e-8)
        assert day.t_peak == "12:00:00"
        assert day.n_samples == 288
        assert day.step_minutes == pytest.approx(5)
        assert day.resampled is False
        assert day.p_on_kw == pytest.approx(2)
        assert day.p_rated_kw == pytest.approx(100)
        assert day.capacity_factor == pytest.approx(day.energy_kwh / 2400)
        assert 480 < day.energy_kwh < 960
    assert clear.variability_index == pytest.approx(1, abs=1e-9)
    assert clear.t_on == "06:10:00"
    assert clear.t_off == "17:50:00"
    assert clear.hours_window == pytest.approx(700 / 60)
    assert cloud.variability_index > 1.2
    assert cloud.energy_kwh < clear.energy_kwh
    assert abs(cloud.ramp_down_kw_per_min) > 5 * abs(clear.ramp_down_kw_per_min)
    assert abs(flicker.ramp_step_down_kw_per_min) > abs(flicker.ramp_down_kw_per_min)
    assert abs(flicker.ramp_step_down_kw_per_min) > 5 * abs(clear.ramp_step_down_kw_per_min)
    assert flicker.variability_index > cloud.variability_index

    no_rated = pv_daily_features(demo_minutes(), [demo_power("clear", float(v)) for v in demo_minutes()], day="2024-06-21")
    assert no_rated.days[0].p_on_kw == pytest.approx(4)
    assert math.isnan(no_rated.days[0].capacity_factor)


def test_csv_round_trip_figure_and_aliases(tmp_path: Path) -> None:
    assert CSV.is_file()
    loaded = []
    with CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            loaded.append((row["timestamp"], float(row["power_kw"])))
    assert len(loaded) == 288 * 3
    for index, minute in enumerate(demo_minutes()):
        stamp, power = loaded[index]
        assert stamp == f"2024-06-21 {int(minute) // 60:02d}:{int(minute) % 60:02d}:00"
        assert power == pytest.approx(demo_power("clear", float(minute)), abs=1e-9)

    png = tmp_path / "pv.png"
    out_csv = tmp_path / "pv.csv"
    result = pv_daily_features(CSV, p_rated_kw=100, ramp_minutes=10, output_png=png, output_csv=out_csv)
    assert result.fig is None
    assert [day.date for day in result.days] == list(DATES)
    assert result.n_rows == 864
    assert result.days[0].variability_index == pytest.approx(1, abs=1e-9)
    assert result.days[0].p_peak_kw == pytest.approx(_day_from_kind("clear").p_peak_kw, abs=1e-8)
    assert result.days[1].energy_kwh == pytest.approx(_day_from_kind("cloud").energy_kwh, abs=1e-6)
    assert png.is_file() and png.stat().st_size > 1000
    text = out_csv.read_text(encoding="utf-8")
    assert text.startswith(
        "date,n_samples,step_minutes,resampled,p_rated_kw,p_on_kw,p_peak_kw,t_peak,"
    )
    assert "\n2024-06-21,288,5,0,100,2,80," in text or "\n2024-06-21,288,5,0,100,2,80.0," in text
    assert "variability_index" in text.splitlines()[0]
    assert "VI=1" in result.summary

    semicolon = tmp_path / "semi.csv"
    semicolon.write_text(
        "timestamp;power_kw\n2024-06-21 12:00:00;80\n2024-06-21 12:10:00;70\n",
        encoding="utf-8",
    )
    parsed = pv_daily_features(semicolon, ramp_minutes=10)
    assert parsed.days[0].p_peak_kw == pytest.approx(80)
    assert parsed.days[0].t_peak == "12:00:00"
    assert parsed.days[0].ramp_down_kw_per_min == pytest.approx(-1)

    chinese = tmp_path / "cn.csv"
    chinese.write_text("时间,功率\n2024-06-21 08:00,10\n2024-06-21 08:05,12\n", encoding="utf-8")
    named = pv_daily_features(chinese, time_col="时间", power_col="功率")
    assert named.days[0].p_peak_kw == pytest.approx(12)
    assert named.days[0].t_peak == "08:05:00"

    duplicate = tmp_path / "dup.csv"
    duplicate.write_text(
        "timestamp,power_kw\n"
        "2024-06-21 01:00:00,4\n"
        "2024-06-21 01:00:00,9\n"
        "2024-06-21 02:00:00,1\n",
        encoding="utf-8",
    )
    kept = pv_daily_features(duplicate)
    assert kept.n_duplicates == 1
    assert kept.days[0].power_kw[0] == pytest.approx(4)

    missing = tmp_path / "gap.csv"
    missing.write_text(
        "timestamp,power_kw\n"
        "2024-06-21 00:00:00,0\n"
        "2024-06-21 00:10:00,\n"
        "2024-06-21 00:20:00,10\n",
        encoding="utf-8",
    )
    gap = pv_daily_features(missing, step_minutes=10)
    assert gap.n_missing == 1
    assert gap.days[0].minute == pytest.approx([0, 10, 20])
    assert gap.days[0].power_kw == pytest.approx([0, 5, 10])


def test_bad_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ramp_minutes"):
        pv_daily_features([0, 10], [0, 1], ramp_minutes=0, day="2024-06-21")
    with pytest.raises(ValueError, match="p_rated_kw"):
        pv_daily_features([0, 10], [0, 1], p_rated_kw=0, day="2024-06-21")
    with pytest.raises(ValueError, match="p_on_kw"):
        pv_daily_features([0, 10], [0, 1], p_on_kw=-1, day="2024-06-21")
    with pytest.raises(ValueError, match="step_minutes"):
        pv_daily_features([0, 10], [0, 1], step_minutes=0, day="2024-06-21")
    with pytest.raises(ValueError, match="show"):
        pv_daily_features([0, 10], [0, 1], show="yes", day="2024-06-21")
    with pytest.raises(ValueError, match="not a scalar"):
        pv_daily_features(1)
    with pytest.raises(ValueError, match="parameter name"):
        pv_daily_features("ramp_minutes")
    with pytest.raises(ValueError, match="pass a CSV path"):
        pv_daily_features()
    with pytest.raises(ValueError, match="same length"):
        pv_daily_features([0, 10], [1], day="2024-06-21")
    with pytest.raises(ValueError, match="time_col"):
        pv_daily_features([0, 10], [1, 2], time_col="time", day="2024-06-21")
    with pytest.raises(ValueError, match="numeric minutes"):
        pv_daily_features(["2024-06-21 00:00:00"], [1], day="2024-06-21")
    with pytest.raises(ValueError, match="not a CSV"):
        pv_daily_features(CSV, day="2024-06-21")
    with pytest.raises(ValueError, match="once"):
        pv_daily_features(CSV, csv_path=CSV)
    with pytest.raises(ValueError, match="finite"):
        pv_daily_features([0, 10], [1, math.inf], day="2024-06-21")
    with pytest.raises(ValueError, match="minutes"):
        pv_daily_features([-5, 0], [1, 2], day="2024-06-21")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        pv_daily_features([0, 10], [1, 2], day="21-06-2024")
    with pytest.raises(ValueError, match="could not parse timestamp"):
        pv_daily_features(["2024-02-30 00:00:00"], [1])
    with pytest.raises(ValueError, match="could not parse timestamp"):
        pv_daily_features(["1900-02-29 00:00:00"], [1])
    with pytest.raises(ValueError, match="could not parse timestamp"):
        pv_daily_features(["2024-06-21"], [1])
    with pytest.raises(FileNotFoundError):
        pv_daily_features(tmp_path / "missing.csv")
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        pv_daily_features(empty)
    blank = tmp_path / "blank.csv"
    blank.write_text("timestamp,power_kw\n2024-06-21 00:00:00,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No power samples"):
        pv_daily_features(blank)
    broken = tmp_path / "bad.csv"
    broken.write_text("timestamp,power_kw\n2024-06-21 00:00:00,abc\n", encoding="utf-8")
    with pytest.raises(ValueError, match="finite"):
        pv_daily_features(broken)
    no_time = tmp_path / "notime.csv"
    no_time.write_text("timestamp,power_kw\n,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing its timestamp"):
        pv_daily_features(no_time)
    with pytest.raises(ValueError, match="not found"):
        pv_daily_features(CSV, time_col="missing")


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line for line in completed.stdout.splitlines() if line.startswith("pv-daily-features:")]
    assert len(lines) == 3
    assert "date=2024-06-21" in lines[0]
    assert "date=2024-06-22" in lines[1]
    assert "date=2024-06-23" in lines[2]
    assert lines[0].count("Ppeak=80.0000") == 1
    assert "t_peak=12:00:00" in lines[0]
    assert "VI=1.000000" in lines[0]
    assert "Ppeak=80.0000" in lines[1]
    assert "Ppeak=80.0000" in lines[2]
    assert "rows=864" in completed.stdout
    png = TOOL / "examples" / "output" / "pv_daily_features_demo.png"
    out_csv = TOOL / "examples" / "output" / "pv_daily_features_demo.csv"
    assert png.is_file() and png.stat().st_size > 1000
    assert "variability_index" in out_csv.read_text(encoding="utf-8")


if __name__ == "__main__":
    write_demo_csv(CSV)
    print(f"wrote {CSV}")
