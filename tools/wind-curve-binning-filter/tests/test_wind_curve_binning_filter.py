"""Smoke tests for the wind-curve binning filter."""

from __future__ import annotations

import csv
import math
import subprocess
import sys
from pathlib import Path

import matplotlib
import pytest

matplotlib.use("Agg")

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))
sys.path.insert(0, str(TOOL / "examples"))

from make_data import synthetic_rows, write_csv
from wind_curve_binning_filter import (
    empirical_quantile,
    format_summary,
    theoretical_power_kw,
    wind_curve_binning_filter,
)

CSV = TOOL / "examples" / "data" / "synthetic_wind_power.csv"
P_RATED = 2000.0
SPAN = 12.0**3 - 3.0**3


def test_quantile_is_type7_and_theory_is_the_nameplate_cubic() -> None:
    assert empirical_quantile([10, 20, 30, 40], 0.25) == pytest.approx(17.5)
    assert empirical_quantile([10, 20, 30, 40], 0.5) == pytest.approx(25)
    assert empirical_quantile([10, 20, 30, 40], 0.75) == pytest.approx(32.5)
    assert empirical_quantile([1100, 1120, 1160, 1180, 1200], 0.5) == pytest.approx(1160)
    assert math.isnan(empirical_quantile([], 0.5))
    with pytest.raises(ValueError, match="q must be in"):
        empirical_quantile([1.0], 1.5)

    assert theoretical_power_kw([0, 3, 25, 26], P_RATED, 3, 12, 25).tolist() == [0, 0, 0, 0]
    assert float(theoretical_power_kw([12, 24.5], P_RATED, 3, 12, 25)[0]) == pytest.approx(P_RATED)
    assert float(theoretical_power_kw([24.5], P_RATED, 3, 12, 25)[0]) == pytest.approx(P_RATED)
    at_ten = P_RATED * (10.0**3 - 27.0) / SPAN
    assert float(theoretical_power_kw([10], P_RATED, 3, 12, 25)[0]) == pytest.approx(at_ten)
    assert at_ten == pytest.approx(1144.0329218106996)


def test_rules_and_quartile_fence_on_a_hand_built_bin() -> None:
    wind = [10.10, 10.20, 10.30, 10.40, 10.45, 10.15, 10.25, 10.35, 8.0]
    power = [1100, 1120, 1160, 1180, 1200, 500, 0, 2000, -30]
    result = wind_curve_binning_filter(wind, power)
    assert result.flag == [
        "normal",
        "normal",
        "normal",
        "normal",
        "normal",
        "curtailment",
        "shutdown",
        "outlier",
        "negative",
    ]
    assert result.reason[7] == "iqr"
    assert result.n_keep == 5
    assert result.n_negative == 1
    assert result.n_shutdown == 1
    assert result.n_curtailment == 1
    assert result.n_outlier == 1
    bin_row = result.bins[int(result.bin_index[0])]
    assert bin_row.v_left == pytest.approx(10.0)
    assert bin_row.v_right == pytest.approx(10.5)
    assert bin_row.n_raw == 8
    assert bin_row.n_quartile == 6
    assert bin_row.n_clean == 5
    assert bin_row.fence_applied is True
    assert bin_row.q1_kw == pytest.approx(1130)
    assert bin_row.median_kw == pytest.approx(1170)
    assert bin_row.q3_kw == pytest.approx(1195)
    assert bin_row.iqr_kw == pytest.approx(65)
    assert bin_row.lower_kw == pytest.approx(1032.5)
    assert bin_row.upper_kw == pytest.approx(1292.5)
    assert bin_row.median_clean_kw == pytest.approx(1160)

    low = wind_curve_binning_filter(
        [3.10, 3.20, 3.30, 3.40],
        [10, 20, 30, 40],
        min_bin_count=4,
    )
    quiet = low.bins[int(low.bin_index[0])]
    assert quiet.n_quartile == 4
    assert quiet.median_kw == pytest.approx(25)
    assert quiet.q1_kw == pytest.approx(17.5)
    assert quiet.q3_kw == pytest.approx(32.5)
    assert quiet.lower_kw == pytest.approx(-5)
    assert quiet.upper_kw == pytest.approx(55)
    assert low.n_keep == 4

    unfenced = wind_curve_binning_filter(
        [3.10, 3.20, 3.30, 3.40],
        [10, 20, 30, 1000],
        min_bin_count=5,
    )
    assert unfenced.n_outlier == 0
    assert unfenced.bins[int(unfenced.bin_index[0])].fence_applied is False
    assert unfenced.flag == ["normal"] * 4


def test_region_rules_do_not_call_cut_in_power_a_shutdown() -> None:
    # Theory at 4 m/s is about 43.5 kW, below the 10% rated shutdown gate.
    near_cut_in = wind_curve_binning_filter([4.0, 4.1], [0.0, 10.0])
    assert near_cut_in.flag == ["normal", "normal"]

    regions = wind_curve_binning_filter(
        [1.5, 25.5, 25.5, 14.0],
        [500.0, 900.0, 10.0, 450.0],
    )
    assert regions.flag == ["outlier", "outlier", "normal", "curtailment"]
    assert regions.reason[:3] == ["below_cut_in", "above_cut_out", ""]

    # n=5, Q1=20, Q3=40, IQR=20, upper fence=70. A point on the fence stays.
    closed = wind_curve_binning_filter(
        [3.1, 3.2, 3.3, 3.4, 3.45],
        [10, 20, 30, 40, 70],
        min_bin_count=5,
    )
    row = closed.bins[int(closed.bin_index[0])]
    assert row.upper_kw == pytest.approx(70)
    assert closed.flag[-1] == "normal"
    past = wind_curve_binning_filter(
        [3.1, 3.2, 3.3, 3.4, 3.45],
        [10, 20, 30, 40, 70.1],
        min_bin_count=5,
    )
    assert past.bins[int(past.bin_index[0])].upper_kw == pytest.approx(70)
    assert past.flag[-1] == "outlier"
    assert past.reason[-1] == "iqr"


def test_synthetic_labels_match_and_rated_bin_median_stays_on_the_curve() -> None:
    assert CSV.is_file()
    rows = synthetic_rows()
    assert len(rows) == 676
    with CSV.open(newline="", encoding="utf-8") as handle:
        loaded = list(csv.DictReader(handle))
    assert len(loaded) == len(rows)
    for loaded_row, (speed, power, name) in zip(loaded, rows, strict=True):
        assert loaded_row["label"] == name
        assert float(loaded_row["wind_mps"]) == pytest.approx(speed)
        assert float(loaded_row["power_kw"]) == pytest.approx(power)

    result = wind_curve_binning_filter(CSV)
    assert [result.flag[i] for i in range(result.n_rows)] == [name for _, _, name in rows]
    assert result.n_rows == 676
    assert result.n_keep == 624
    assert result.n_negative == 5
    assert result.n_shutdown == 10
    assert result.n_curtailment == 26
    assert result.n_outlier == 11
    assert result.summary == format_summary(result)
    assert result.summary == (
        "wind-curve-binning-filter: rows=676 keep=624 "
        "negative=5 shutdown=10 curtailment=26 outlier=11 "
        "bin_width=0.5 p_rated_kw=2000"
    )
    rated = next(row for row in result.bins if row.v_left == pytest.approx(12))
    assert rated.n_raw == 14
    assert rated.n_clean == 12
    assert rated.median_clean_kw == pytest.approx(2000)
    assert rated.q1_kw == pytest.approx(1960)
    assert rated.q3_kw == pytest.approx(2040)
    assert rated.theory_kw == pytest.approx(2000)
    assert rated.lower_kw == pytest.approx(1840)
    assert rated.upper_kw == pytest.approx(2160)


def test_csv_round_trip_figure_and_aliases(tmp_path: Path) -> None:
    png = tmp_path / "curve.png"
    points = tmp_path / "points.csv"
    bins = tmp_path / "bins.csv"
    result = wind_curve_binning_filter(
        CSV, output_png=png, output_csv=points, output_bins_csv=bins
    )
    assert result.fig is None
    assert png.is_file() and png.stat().st_size > 1000
    point_text = points.read_text(encoding="utf-8")
    assert point_text.startswith(
        "wind_mps,power_kw,theory_kw,bin_index,v_left,flag,reason,keep\n"
    )
    assert ",curtailment,curtailment,0\n" in point_text
    bin_lines = bins.read_text(encoding="utf-8").splitlines()
    assert bin_lines[0].startswith("bin_index,v_left,v_right,v_center,")
    rated_line = next(line for line in bin_lines if line.startswith("24,"))
    assert ",12,12," in rated_line or rated_line.startswith("24,12,12.5,")
    assert ",1960," in rated_line
    assert rated_line.endswith(",2000") or ",2000\n" in rated_line + "\n"

    semicolon = tmp_path / "semi.csv"
    semicolon.write_text(
        "wind_mps;power_kw\n10;1100\n10.2;1120\n10.3;1160\n10.4;1180\n10.45;1200\n",
        encoding="utf-8",
    )
    parsed = wind_curve_binning_filter(semicolon)
    assert parsed.n_rows == 5
    assert parsed.n_keep == 5

    chinese = tmp_path / "cn.csv"
    chinese.write_text("风速,功率\n4,10\n4.1,12\n", encoding="utf-8")
    named = wind_curve_binning_filter(chinese, wind_col="风速", power_col="功率")
    assert named.n_rows == 2
    assert named.flag == ["normal", "normal"]

    missing = tmp_path / "gap.csv"
    missing.write_text(
        "wind_mps,power_kw\n1,10\n\n2,\n3,30\n",
        encoding="utf-8",
    )
    gap = wind_curve_binning_filter(missing, min_bin_count=5)
    assert gap.n_missing == 1
    assert gap.n_rows == 2
    assert gap.wind_mps.tolist() == pytest.approx([1, 3])


def test_bad_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bin_width"):
        wind_curve_binning_filter([1, 2], [0, 0], bin_width=0)
    with pytest.raises(ValueError, match="v_cut_in < v_rated < v_cut_out"):
        wind_curve_binning_filter([1, 2], [0, 0], v_rated=3, v_cut_out=3)
    with pytest.raises(ValueError, match="same length"):
        wind_curve_binning_filter([1, 2], [0])
    with pytest.raises(ValueError, match="finite"):
        wind_curve_binning_filter([1, 2], [0, math.inf])
    with pytest.raises(ValueError, match="v_min"):
        wind_curve_binning_filter([-0.1, 1], [0, 0])
    with pytest.raises(ValueError, match="show must be true or false"):
        wind_curve_binning_filter([1, 2], [0, 0], show="yes")
    with pytest.raises(ValueError, match="not both"):
        wind_curve_binning_filter(CSV, [1, 2])
    with pytest.raises(ValueError, match="CSV input"):
        wind_curve_binning_filter([1, 2], [0, 0], wind_col="wind_mps")
    with pytest.raises(FileNotFoundError):
        wind_curve_binning_filter(tmp_path / "missing.csv")
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty csv"):
        wind_curve_binning_filter(empty)
    with pytest.raises(ValueError, match="not found"):
        wind_curve_binning_filter(CSV, wind_col="missing")


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "wind-curve-binning-filter: rows=676 keep=624" in completed.stdout
    assert "negative=5 shutdown=10 curtailment=26 outlier=11" in completed.stdout
    assert "median_clean_kw=2000.0000" in completed.stdout
    assert "q1_kw=1960.0000" in completed.stdout
    png = TOOL / "examples" / "output" / "wind_curve_binning_filter_demo.png"
    out_csv = TOOL / "examples" / "output" / "wind_curve_binning_filter_demo.csv"
    assert png.is_file() and png.stat().st_size > 1000
    assert out_csv.read_text(encoding="utf-8").startswith("wind_mps,power_kw,")


def test_writer_matches_generator() -> None:
    """The committed CSV is the generator output, not a hand-edited table."""

    generated = synthetic_rows()
    with CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(generated)
    for loaded_row, (speed, power, name) in zip(rows, generated, strict=True):
        assert loaded_row["label"] == name
        assert float(loaded_row["wind_mps"]) == pytest.approx(speed)
        assert float(loaded_row["power_kw"]) == pytest.approx(power)
    assert write_csv(CSV) == CSV
