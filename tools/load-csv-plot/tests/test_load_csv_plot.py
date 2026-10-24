"""Smoke tests for the load-csv-plot Python tool."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pandas as pd
import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from load_csv_plot import load_csv_plot

DATA = TOOL / "examples" / "data" / "synthetic_load_kw.csv"
SPIKE = "2024-06-02 12:00:00"
DIP = "2024-06-03 18:00:00"
GAP = "2024-06-01 04:00:00"


def _row(result, stamp: str) -> int:
    hit = result.time == pd.Timestamp(stamp)
    assert int(hit.sum()) == 1
    return int(hit.to_numpy().nonzero()[0][0])


def test_synthetic_csv_cleans_flags_and_saves_png(tmp_path: Path) -> None:
    png = tmp_path / "load.png"
    result = load_csv_plot(DATA, agg="daily_mean", output_png=png, show=False)

    assert result.n_rows == 72
    assert result.n_missing == 1
    assert result.n_outliers == 2
    assert result.agg == "daily_mean"
    assert list(result.daily_mean.columns) == ["date", "mean_kw"]
    assert len(result.daily_mean) == 3
    assert result.load_kw.notna().all()
    assert png.is_file()
    assert png.stat().st_size > 1000
    assert Path(result.output_png) == png

    spike = _row(result, SPIKE)
    dip = _row(result, DIP)
    gap = _row(result, GAP)
    assert result.is_outlier.iloc[spike]
    assert result.is_outlier.iloc[dip]
    assert result.load_raw_kw.iloc[spike] == pytest.approx(950)
    assert result.load_raw_kw.iloc[dip] == pytest.approx(5)
    assert pd.isna(result.load_raw_kw.iloc[gap])
    assert result.load_kw.iloc[spike] < 200
    assert result.load_kw.iloc[dip] > 50

    means = result.daily_mean["mean_kw"].to_list()
    assert all(80 < value < 160 for value in means)
    assert means[2] < means[0] < means[1]

    plain = load_csv_plot(DATA, agg="none", show=False)
    assert plain.n_outliers == 2
    assert len(plain.daily_mean) == 0
    assert plain.mean_kw == pytest.approx(float(plain.load_kw.mean()))


def test_header_aliases_and_semicolon(tmp_path: Path) -> None:
    chinese = tmp_path / "cn.csv"
    chinese.write_text(
        "时间,负荷(kW)\n"
        "2024-01-01 00:00:00,100\n"
        "2024-01-01 01:00:00,110\n"
        "2024-01-01 02:00:00,120\n"
        "2024-01-01 03:00:00,130\n",
        encoding="utf-8",
    )
    aliased = load_csv_plot(chinese, outlier_method="none", show=False)
    assert aliased.n_rows == 4
    assert aliased.mean_kw == pytest.approx(115)

    semicolon = tmp_path / "semi.csv"
    semicolon.write_text(
        "Time;Load (kW)\n"
        "2024-01-02 00:00:00;80\n"
        "2024-01-02 01:00:00;90\n"
        "2024-01-02 02:00:00;100\n"
        "2024-01-02 03:00:00;110\n",
        encoding="utf-8",
    )
    parsed = load_csv_plot(semicolon, outlier_method="none", show=False)
    assert parsed.n_rows == 4
    assert parsed.mean_kw == pytest.approx(95)


def test_interpolate_gap_and_duplicate_timestamp(tmp_path: Path) -> None:
    gap = tmp_path / "gap.csv"
    gap.write_text(
        "timestamp,load_kw\n"
        "2024-01-01 00:00:00,100\n"
        "2024-01-01 01:00:00,\n"
        "2024-01-01 02:00:00,130\n",
        encoding="utf-8",
    )
    filled = load_csv_plot(gap, outlier_method="none", show=False)
    assert filled.n_missing == 1
    assert filled.n_rows == 3
    assert filled.load_kw.iloc[1] == pytest.approx(115)

    duplicate = tmp_path / "dup.csv"
    duplicate.write_text(
        "timestamp,load_kw\n"
        "2024-01-01 00:00:00,100\n"
        "2024-01-01 00:00:00,999\n"
        "2024-01-01 01:00:00,110\n"
        "2024-01-01 02:00:00,120\n"
        "2024-01-01 03:00:00,130\n",
        encoding="utf-8",
    )
    kept = load_csv_plot(duplicate, outlier_method="none", show=False)
    assert kept.n_rows == 4
    assert kept.load_raw_kw.iloc[0] == pytest.approx(100)


def test_zscore_flags_only_the_extreme_spike() -> None:
    result = load_csv_plot(DATA, outlier_method="zscore", show=False)
    assert result.n_outliers == 1
    assert result.is_outlier.iloc[_row(result, SPIKE)]
    assert not result.is_outlier.iloc[_row(result, DIP)]


def test_drop_and_bad_options(tmp_path: Path) -> None:
    csv_path = tmp_path / "drop.csv"
    csv_path.write_text(
        "timestamp,load_kw\n"
        "2024-01-01 00:00:00,100\n"
        "2024-01-01 01:00:00,\n"
        "2024-01-01 02:00:00,130\n"
        "2024-01-01 03:00:00,140\n",
        encoding="utf-8",
    )
    dropped = load_csv_plot(csv_path, fill_method="drop", outlier_method="none", show=False)
    assert dropped.n_missing == 1
    assert dropped.n_rows == 3
    assert dropped.load_kw.iloc[0] == pytest.approx(100)

    broken = tmp_path / "bad.csv"
    broken.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="time"):
        load_csv_plot(broken, show=False)
    with pytest.raises(ValueError, match="agg"):
        load_csv_plot(DATA, agg="weekly", show=False)


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "outliers=2" in completed.stdout
    png = TOOL / "examples" / "output" / "load_csv_plot_demo.png"
    assert png.is_file()
    assert png.stat().st_size > 1000
