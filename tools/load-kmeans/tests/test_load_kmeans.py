"""Smoke tests for the load-kmeans Python tool."""

from __future__ import annotations

import csv
import math
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")

import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from load_kmeans import format_table, load_kmeans

CSV = TOOL / "examples" / "data" / "synthetic_load_kw.csv"
START = date(2024, 3, 4)
N_DAYS = 14


def commercial_kw(hour: int) -> float:
    """Flat office day with a small noon crown. Peak is hour 12."""

    if 8 <= hour <= 17:
        base = 92.0
    elif hour in (7, 18):
        base = 55.0
    elif hour in (6, 19):
        base = 30.0
    else:
        base = 16.0
    crown = 8.0 * math.exp(-((hour - 12) / 1.2) ** 2)
    return base + crown


def residential_kw(hour: int) -> float:
    """Evening peak at hour 19, plus a small morning bump."""

    morning = 22.0 * math.exp(-((hour - 7) / 1.4) ** 2)
    evening = 70.0 * math.exp(-((hour - 19) / 1.5) ** 2)
    return 16.0 + morning + evening


def weekend_kw(hour: int) -> float:
    """Broader, lower afternoon hump. Peak is hour 15."""

    return 14.0 + 34.0 * math.exp(-((hour - 15) / 3.2) ** 2)


def family(day: date) -> str:
    if day.weekday() >= 5:
        return "weekend"
    if day < date(2024, 3, 11):
        return "commercial"
    return "residential"


def shape_kw(kind: str, hour: int) -> float:
    if kind == "commercial":
        return commercial_kw(hour)
    if kind == "residential":
        return residential_kw(hour)
    if kind == "weekend":
        return weekend_kw(hour)
    raise AssertionError(kind)


def noise_kw(day_index: int, hour: int) -> float:
    state = (1664525 * ((day_index + 1) * 1000 + hour) + 1013904223) % 4294967296
    unit = state / 4294967296.0
    return (unit * 2.0 - 1.0) * 3.5


def demo_days() -> list[date]:
    return [START + timedelta(days=offset) for offset in range(N_DAYS)]


def demo_power(day_index: int, hour: int) -> float:
    return shape_kw(family(demo_days()[day_index]), hour) + noise_kw(day_index, hour)


def write_demo_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "power_kw"])
        for day_index, day in enumerate(demo_days()):
            for hour in range(24):
                stamp = f"{day.isoformat()} {hour:02d}:00:00"
                writer.writerow([stamp, f"{demo_power(day_index, hour):.10f}"])


def test_one_cluster_sse_is_the_sum_of_squared_distances() -> None:
    result = load_kmeans([[0, 0], [2, 0], [4, 0]], k=1, normalize="none", seed=0, n_init=3)

    assert result.n_days == 3
    assert result.labels.tolist() == [1, 1, 1]
    assert result.centroids.shape == (1, 2)
    assert result.centroids[0].tolist() == pytest.approx([2, 0])
    assert result.sse == pytest.approx(8)
    assert result.day_sse.tolist() == pytest.approx([4, 0, 4])
    assert math.isnan(result.silhouette)
    assert result.cluster_sizes.tolist() == [3]
    assert result.dates == ["day-01", "day-02", "day-03"]
    assert result.normalize == "none"
    assert result.resampled is False
    assert "k=1" in result.summary
    assert "silhouette=nan" in result.summary
    assert format_table(result) == result.summary


def test_separated_copies_have_zero_sse_and_unit_silhouette() -> None:
    profiles = [[0.0, 0.0], [0.0, 0.0], [10.0, 0.0], [10.0, 0.0]]
    result = load_kmeans(profiles, k=2, normalize="none", seed=0, n_init=5)

    assert result.sse == pytest.approx(0, abs=1e-10)
    assert result.silhouette == pytest.approx(1)
    assert result.labels[0] == result.labels[1]
    assert result.labels[2] == result.labels[3]
    assert result.labels[0] != result.labels[2]
    assert sorted(result.cluster_sizes.tolist()) == [2, 2]
    again = load_kmeans(profiles, k=2, normalize="none", seed=0, n_init=5)
    assert again.labels.tolist() == result.labels.tolist()
    assert again.centroids == pytest.approx(result.centroids)


def test_peak_normalization_ignores_magnitude_and_keeps_shape_families() -> None:
    commercial = np.array([0.2, 1.0, 0.95, 0.3, 0.15], dtype=float)
    weekend = np.array([0.25, 0.55, 0.9, 1.0, 0.4], dtype=float)
    residential = np.array([0.2, 0.35, 0.25, 0.45, 1.0], dtype=float)
    rows = [commercial * scale for scale in (80, 100, 90, 110, 95)]
    rows += [weekend * scale for scale in (40, 42, 38, 45)]
    rows += [residential * scale for scale in (70, 75, 68, 72, 80)]
    result = load_kmeans(rows, k=3, normalize="peak", seed=1, n_init=8)

    assert len(set(result.labels[:5])) == 1
    assert len(set(result.labels[5:9])) == 1
    assert len(set(result.labels[9:])) == 1
    assert len(set(result.labels.tolist())) == 3
    assert result.profiles[0] == pytest.approx(result.profiles[1])
    assert result.profiles[0] == pytest.approx(commercial / commercial.max())
    assert result.sse == pytest.approx(0, abs=1e-8)
    assert result.centroid_peak_hour.tolist() == pytest.approx([1 * 24 / 5, 3 * 24 / 5, 4 * 24 / 5])
    assert result.labels[0] == 1
    assert result.labels[5] == 2
    assert result.labels[9] == 3


def test_mean_normalization_and_identical_rows() -> None:
    scaled = load_kmeans([[0, 10], [0, 4]], k=1, normalize="mean")
    assert scaled.profiles == pytest.approx(np.array([[0.0, 2.0], [0.0, 2.0]]))
    assert scaled.power_kw[1, 1] == pytest.approx(4)
    assert scaled.centroids_kw[0].tolist() == pytest.approx([0, 7])

    flat = load_kmeans(np.ones((6, 4)), k=3, normalize="none", seed=2)
    assert flat.sse == pytest.approx(0, abs=1e-10)
    assert flat.cluster_sizes.sum() == 6
    assert math.isnan(flat.silhouette)


def test_minutes_timestamps_and_duplicate_days() -> None:
    minutes = [0, 60, 120]
    power = [1, 3, 2]
    result = load_kmeans(minutes, power, k=1, normalize="none", day="2024-03-04")
    assert result.dates == ["2024-03-04"]
    assert result.minute.tolist() == pytest.approx([0, 60, 120])
    assert result.hour.tolist() == pytest.approx([0, 1, 2])
    assert result.peak_kw.tolist() == pytest.approx([3])
    assert result.n_rows == 3
    assert result.resampled is False

    stamps = ["2024-03-05 00:00:00", "2024-03-05 01:00:00", "2024-03-06 00:00:00", "2024-03-06 01:00:00"]
    values = [2, 4, 5, 1]
    two = load_kmeans(stamps, values, k=1, normalize="peak")
    assert two.dates == ["2024-03-05", "2024-03-06"]
    assert two.profiles[:, 0].tolist() == pytest.approx([0.5, 1.0])
    assert two.n_days == 2

    tied = load_kmeans(
        ["2024-03-04 01:00:00", "2024-03-04 01:00:00", "2024-03-04 02:00:00"],
        [4, 9, 1],
        k=1,
        normalize="none",
    )
    assert tied.n_duplicates == 1
    assert tied.n_rows == 2
    assert tied.power_kw[0].tolist() == pytest.approx([4, 1])

    stamped = load_kmeans(
        [datetime(2024, 3, 4, 8, 0, 0), datetime(2024, 3, 4, 12, 0, 0)],
        [10, 20],
        k=1,
        normalize="none",
    )
    assert stamped.dates == ["2024-03-04"]
    assert stamped.peak_kw.tolist() == pytest.approx([20])
    aware = datetime(2024, 3, 4, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="naive local time"):
        load_kmeans([aware, aware], [1, 2], k=1)


def test_synthetic_csv_recovers_three_shape_families(tmp_path: Path) -> None:
    assert CSV.is_file()
    loaded = list(csv.DictReader(CSV.open(encoding="utf-8")))
    assert len(loaded) == N_DAYS * 24
    days = demo_days()
    counts = {"commercial": 0, "weekend": 0, "residential": 0}
    for day_index, day in enumerate(days):
        counts[family(day)] += 1
        for hour in range(24):
            row = loaded[day_index * 24 + hour]
            assert row["timestamp"] == f"{day.isoformat()} {hour:02d}:00:00"
            assert float(row["power_kw"]) == pytest.approx(demo_power(day_index, hour), abs=1e-8)
            assert demo_power(day_index, hour) > 0
    assert counts == {"commercial": 5, "weekend": 4, "residential": 5}

    png = tmp_path / "clusters.png"
    out_csv = tmp_path / "clusters.csv"
    result = load_kmeans(CSV, k=3, seed=0, normalize="peak", output_png=png, output_csv=out_csv)
    assert result.n_days == 14
    assert result.n_rows == 336
    assert result.n_missing == 0
    assert result.n_duplicates == 0
    assert result.resampled is False
    assert result.step_minutes == pytest.approx(60)
    assert result.k == 3
    assert result.centroid_peak_hour.tolist() == pytest.approx([12, 15, 19])
    assert result.cluster_sizes.tolist() == [5, 4, 5]
    assert result.mean_peak_kw[0] > result.mean_peak_kw[2] > result.mean_peak_kw[1]
    assert result.silhouette > 0.7
    assert result.sse < 0.5
    by_date = dict(zip(result.dates, result.labels))
    commercial = {by_date[day.isoformat()] for day in days if family(day) == "commercial"}
    weekend = {by_date[day.isoformat()] for day in days if family(day) == "weekend"}
    residential = {by_date[day.isoformat()] for day in days if family(day) == "residential"}
    assert commercial == {1}
    assert weekend == {2}
    assert residential == {3}
    assert png.is_file() and png.stat().st_size > 1000
    text = out_csv.read_text(encoding="utf-8")
    assert text.startswith("date,label,peak_kw,day_sse\n")
    assert "2024-03-04,1," in text
    assert "2024-03-09,2," in text
    assert "2024-03-11,3," in text
    assert "days=14" in result.summary
    assert "normalize=peak" in result.summary
    assert result.fig is None

    repeat = load_kmeans(CSV, k=3, seed=0, normalize="peak")
    assert repeat.labels.tolist() == result.labels.tolist()
    assert repeat.sse == pytest.approx(result.sse)
    assert repeat.summary == result.summary


def test_csv_aliases_gaps_and_resampling(tmp_path: Path) -> None:
    semicolon = tmp_path / "semi.csv"
    semicolon.write_text(
        "timestamp;power_kw\n"
        "2024-03-04 00:00:00;1\n"
        "2024-03-04 12:00:00;4\n"
        "2024-03-05 00:00:00;2\n"
        "2024-03-05 12:00:00;2\n",
        encoding="utf-8",
    )
    parsed = load_kmeans(semicolon, k=1, normalize="peak", step_minutes=720)
    assert parsed.dates == ["2024-03-04", "2024-03-05"]
    assert parsed.resampled is False
    assert parsed.profiles[0].tolist() == pytest.approx([0.25, 1])

    chinese = tmp_path / "cn.csv"
    chinese.write_text(
        "时间,功率\n2024-03-04 08:00,10\n2024-03-04 09:00,12\n",
        encoding="utf-8",
    )
    named = load_kmeans(chinese, k=1, normalize="none", time_col="时间", power_col="功率")
    assert named.peak_kw.tolist() == pytest.approx([12])
    assert named.minute.tolist() == pytest.approx([8 * 60, 9 * 60])

    gap_lines = ["timestamp,power_kw"]
    for hour in range(24):
        if hour == 1:
            gap_lines.append(f"2024-03-04 {hour:02d}:00:00,")
        elif hour == 2:
            gap_lines.append(f"2024-03-04 {hour:02d}:00:00,10")
        else:
            gap_lines.append(f"2024-03-04 {hour:02d}:00:00,0")
        gap_lines.append(f"2024-03-05 {hour:02d}:00:00,1")
    missing = tmp_path / "gap.csv"
    missing.write_text("\n".join(gap_lines) + "\n", encoding="utf-8")
    gap = load_kmeans(missing, k=1, normalize="none")
    assert gap.n_missing == 1
    assert gap.resampled is True
    assert gap.step_minutes == pytest.approx(60)
    assert gap.power_kw.shape == (2, 24)
    assert gap.power_kw[0, 0] == pytest.approx(0)
    assert gap.power_kw[0, 1] == pytest.approx(5)
    assert gap.power_kw[0, 2] == pytest.approx(10)
    assert gap.power_kw[1].tolist() == pytest.approx([1] * 24)

    duplicate = tmp_path / "dup.csv"
    duplicate.write_text(
        "timestamp,power_kw\n"
        "2024-03-04 02:00:00,1\n"
        "2024-03-04 01:00:00,4\n"
        "2024-03-04 01:00:00,9\n",
        encoding="utf-8",
    )
    kept = load_kmeans(duplicate, k=1, normalize="none")
    assert kept.n_duplicates == 1
    assert kept.power_kw[0].tolist() == pytest.approx([4, 1])


def test_bad_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="k must be a positive integer"):
        load_kmeans([[1, 2], [3, 4]], k=0)
    with pytest.raises(ValueError, match="k must not exceed"):
        load_kmeans([[1, 2], [3, 4]], k=3)
    with pytest.raises(ValueError, match="seed must be a non-negative integer"):
        load_kmeans([[1, 2], [3, 4]], k=1, seed=-1)
    with pytest.raises(ValueError, match="normalize must be peak, mean, or none"):
        load_kmeans([[1, 2], [3, 4]], k=1, normalize="max")
    with pytest.raises(ValueError, match="positive daily peak"):
        load_kmeans([[0, 0], [1, 2]], k=1, normalize="peak")
    with pytest.raises(ValueError, match="positive daily mean"):
        load_kmeans([[-2, -4], [1, 3]], k=1, normalize="mean")
    with pytest.raises(ValueError, match="at least 2 samples"):
        load_kmeans([[1], [2]], k=1)
    with pytest.raises(ValueError, match="finite"):
        load_kmeans([[1, math.inf], [0, 1]], k=1)
    with pytest.raises(ValueError, match="step_minutes applies"):
        load_kmeans([[1, 2, 3], [0, 1, 2]], k=1, step_minutes=60)
    with pytest.raises(ValueError, match="dates must have one entry"):
        load_kmeans([[1, 2], [3, 4]], k=1, dates=["only"])
    with pytest.raises(ValueError, match="parameter name"):
        load_kmeans("seed")
    with pytest.raises(ValueError, match="pass a CSV path"):
        load_kmeans()
    with pytest.raises(ValueError, match="same length"):
        load_kmeans([0, 60], [1], k=1, day="2024-03-04")
    with pytest.raises(ValueError, match=r"\[0, 1440\)"):
        load_kmeans([0, 1440], [1, 2], k=1, day="2024-03-04")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        load_kmeans([0, 60], [1, 2], k=1, day="04-03-2024")
    with pytest.raises(ValueError, match="divide 24 hours"):
        load_kmeans([0, 60], [1, 2], k=1, step_minutes=7, day="2024-03-04")
    with pytest.raises(ValueError, match="show must be true or false"):
        load_kmeans([[1, 2], [3, 4]], k=1, show="yes")
    with pytest.raises(FileNotFoundError, match="CSV not found"):
        load_kmeans(tmp_path / "missing.csv")
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_kmeans(empty)
    blank = tmp_path / "blank.csv"
    blank.write_text("timestamp,power_kw\n2024-03-04 00:00:00,\n2024-03-04 01:00:00,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No power samples"):
        load_kmeans(blank)
    broken = tmp_path / "bad.csv"
    broken.write_text("timestamp,power_kw\n2024-03-04 00:00:00,abc\n2024-03-04 01:00:00,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="finite"):
        load_kmeans(broken)
    with pytest.raises(ValueError, match="could not parse timestamp"):
        load_kmeans(["2024-02-30 00:00:00", "2024-03-04 01:00:00"], [1, 2], k=1)
    short = tmp_path / "short.csv"
    short.write_text(
        "timestamp,power_kw\n2024-03-04 08:00:00,1\n2024-03-04 09:00:00,2\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not cover"):
        load_kmeans(short, k=1, step_minutes=120)


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line for line in completed.stdout.splitlines() if line.startswith("load-kmeans:")]
    assert len(lines) == 14
    assert "date=2024-03-04 label=1" in lines[0]
    assert "date=2024-03-09 label=2" in lines[5]
    assert "date=2024-03-11 label=3" in lines[7]
    assert "date=2024-03-16 label=2" in lines[12]
    assert "days=14" in completed.stdout
    assert "peak_hour=12" in completed.stdout
    assert "peak_hour=15" in completed.stdout
    assert "peak_hour=19" in completed.stdout
    png = TOOL / "examples" / "output" / "load_kmeans_demo.png"
    out_csv = TOOL / "examples" / "output" / "load_kmeans_demo.csv"
    assert png.is_file() and png.stat().st_size > 1000
    assert out_csv.read_text(encoding="utf-8").startswith("date,label,peak_kw,day_sse")


if __name__ == "__main__":
    write_demo_csv(CSV)
    print(f"wrote {CSV}")
