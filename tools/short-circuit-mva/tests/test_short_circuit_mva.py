"""Smoke tests for the short-circuit MVA Python tool."""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from short_circuit_mva import format_single_line, format_table, short_circuit_mva

CSV = TOOL / "examples" / "data" / "synthetic_short_circuit_stages.csv"
V = 10_000.0
SQRT3 = math.sqrt(3.0)


def test_mva_current_and_impedance_round_trip() -> None:
    point = short_circuit_mva(s_mva=250.0, v_kv=10.0)
    expected_i = 250e6 / (SQRT3 * V)
    expected_z = (V * V) / 250e6
    assert point.system == "three_phase"
    assert point.method == "mva"
    assert point.v_kv == pytest.approx(10.0)
    assert point.s_base_mva == pytest.approx(100.0)
    assert point.z_base_ohm == pytest.approx(1.0)
    assert point.i_base_a == pytest.approx(100e6 / (SQRT3 * V))
    assert point.s_mva == pytest.approx(250.0)
    assert point.s_va == pytest.approx(250e6)
    assert point.i_a == pytest.approx(expected_i)
    assert point.i_ka == pytest.approx(expected_i / 1000.0)
    assert point.z_ohm == pytest.approx(expected_z)
    assert point.z_ohm == pytest.approx(0.4)
    assert point.z_pu == pytest.approx(0.4)
    assert point.r_ohm == pytest.approx(0.0)
    assert point.x_ohm == pytest.approx(0.4)
    assert math.isinf(point.x_over_r) and point.x_over_r > 0.0
    assert point.angle_deg == pytest.approx(90.0)
    assert point.s_mva_complex == pytest.approx(250.0)
    assert point.elements[0].kind == "source"
    assert point.elements[0].combine == "seed"
    assert format_single_line(point) == (
        "short-circuit-mva single: "
        "S=250.0000 MVA  I=14.4338 kA  Z=0.4000 ohm  z_pu=0.4000 pu  X/R=inf"
    )

    from_current = short_circuit_mva(i_ka=point.i_ka, v_kv=10.0)
    assert from_current.s_mva == pytest.approx(250.0)
    assert from_current.z_ohm == pytest.approx(0.4)
    from_amps = short_circuit_mva(i_a=expected_i, v_v=V)
    assert from_amps.s_mva == pytest.approx(250.0)
    from_z = short_circuit_mva(z_ohm=0.4, v_kv=10.0)
    assert from_z.s_mva == pytest.approx(250.0)
    assert from_z.i_ka == pytest.approx(expected_i / 1000.0)
    from_va = short_circuit_mva(s_va=250e6, v_kv=10.0)
    assert from_va.s_mva == pytest.approx(250.0)

    ten_ka = short_circuit_mva(i_ka=10.0, v_kv=10.0)
    assert ten_ka.s_mva == pytest.approx(100.0 * SQRT3)
    assert ten_ka.z_ohm == pytest.approx(1.0 / SQRT3)
    assert ten_ka.z_pu == pytest.approx(1.0 / SQRT3)
    assert format_single_line(ten_ka) == (
        "short-circuit-mva single: "
        "S=173.2051 MVA  I=10.0000 kA  Z=0.5774 ohm  z_pu=0.5774 pu  X/R=inf"
    )


def test_transformer_percent_and_same_base_pu_add_in_series() -> None:
    transformer = short_circuit_mva(
        kind="transformer",
        s_rated_mva=20.0,
        z_percent=8.0,
        x_over_r=10.0,
        v_kv=10.0,
    )
    assert transformer.elements[0].kind == "transformer"
    assert transformer.elements[0].s_rated_mva == pytest.approx(20.0)
    assert transformer.elements[0].z_spec_pu == pytest.approx(0.08)
    assert transformer.s_mva == pytest.approx(250.0)
    assert transformer.z_ohm == pytest.approx(0.4)
    assert transformer.x_over_r == pytest.approx(10.0)
    assert transformer.angle_deg == pytest.approx(math.degrees(math.atan(10.0)))
    scale = math.sqrt(1.0 + 100.0)
    assert transformer.r_ohm == pytest.approx(0.4 / scale)
    assert transformer.x_ohm == pytest.approx(10.0 * transformer.r_ohm)
    assert format_single_line(transformer) == (
        "short-circuit-mva single: "
        "S=250.0000 MVA  I=14.4338 kA  Z=0.4000 ohm  z_pu=0.4000 pu  X/R=10.0000"
    )

    # z_pu on a shared base adds in series: 0.2 + 0.4 = 0.6, S = 100/0.6.
    series = short_circuit_mva(
        [
            {"name": "a", "z_pu": 0.2},
            {"name": "b", "z_pu": 0.4, "combine": "series"},
        ],
        v_kv=10.0,
    )
    assert [row.kind for row in series.elements] == ["pu", "pu"]
    assert [row.s_mva for row in series.elements] == pytest.approx([500.0, 250.0])
    assert series.s_mva == pytest.approx(100.0 / 0.6)
    assert series.z_pu == pytest.approx(0.6)
    assert series.z_ohm == pytest.approx(0.6)
    assert series.s_mva_complex == pytest.approx(series.s_mva)

    on_rating = short_circuit_mva(s_rated_mva=20.0, z_pu=0.08, v_kv=10.0)
    assert on_rating.s_mva == pytest.approx(250.0)


def test_network_csv_matches_the_hand_mva_fold(tmp_path: Path) -> None:
    png = tmp_path / "network.png"
    out_csv = tmp_path / "network.csv"
    result = short_circuit_mva(CSV, output_png=png, output_csv=out_csv, show=False)

    assert [row.name for row in result.elements] == ["grid", "tx", "cable", "motor"]
    assert [row.kind for row in result.elements] == ["source", "transformer", "line", "transformer"]
    assert [row.combine for row in result.elements] == ["seed", "series", "series", "parallel"]
    assert [row.s_mva for row in result.elements] == pytest.approx([500.0, 250.0, 500.0, 25.0])
    assert [row.z_ohm for row in result.elements] == pytest.approx([0.2, 0.4, 0.2, 4.0])
    assert [row.s_running_mva for row in result.elements] == pytest.approx(
        [500.0, 500.0 / 3.0, 125.0, 150.0]
    )
    assert result.elements[1].z_spec_pu == pytest.approx(0.08)
    assert result.elements[1].s_rated_mva == pytest.approx(20.0)
    assert result.elements[3].z_spec_pu == pytest.approx(0.2)
    assert result.elements[3].s_rated_mva == pytest.approx(5.0)
    assert result.s_mva == pytest.approx(150.0)
    assert result.z_ohm == pytest.approx(2.0 / 3.0)
    assert result.z_pu == pytest.approx(100.0 / 150.0)
    assert result.i_a == pytest.approx(150e6 / (SQRT3 * V))
    assert result.i_ka == pytest.approx(8.660254037844386)
    assert result.x_over_r == pytest.approx(10.0)
    assert result.s_mva_complex == pytest.approx(150.0)
    assert result.z_complex_ohm == pytest.approx(result.z_ohm)
    assert "S_sc=150.0000 MVA  I_sc=8.6603 kA" in result.summary
    assert "Z=0.6667 ohm  z_pu=0.6667 pu" in result.summary
    assert "X/R=10.0000" in result.summary
    assert "S_complex=150.0000 MVA" in result.summary
    assert "166.6667" in result.summary
    assert format_table(result) == result.summary
    assert png.is_file() and png.stat().st_size > 1000
    assert result.fig is None
    text = out_csv.read_text(encoding="utf-8")
    assert "s_running_mva" in text
    assert "motor" in text
    assert "150" in text


def test_same_xr_matches_complex_and_different_angles_do_not() -> None:
    same = short_circuit_mva(
        [
            {"z_ohm": 0.2, "x_over_r": 10.0},
            {"z_ohm": 0.4, "x_over_r": 10.0, "combine": "series"},
        ],
        v_kv=10.0,
    )
    assert same.s_mva == pytest.approx(500.0 * 250.0 / 750.0)
    assert same.s_mva_complex == pytest.approx(same.s_mva)
    assert same.z_complex_ohm == pytest.approx(same.z_ohm)

    mixed = short_circuit_mva(
        [
            {"name": "a", "r_ohm": 0.1, "x_ohm": 0.1},
            {"name": "b", "combine": "series", "x_ohm": 0.2},
        ],
        v_kv=10.0,
    )
    z_mag = math.hypot(0.1, 0.1) + 0.2
    z_phasor = math.hypot(0.1, 0.3)
    assert mixed.elements[0].x_over_r == pytest.approx(1.0)
    assert math.isinf(mixed.elements[1].x_over_r)
    assert mixed.s_mva == pytest.approx(100.0 / z_mag)
    assert mixed.s_mva_complex == pytest.approx(100.0 / z_phasor)
    assert mixed.s_mva_complex > mixed.s_mva
    assert mixed.r_ohm == pytest.approx(0.1)
    assert mixed.x_ohm == pytest.approx(0.3)

    resistive = short_circuit_mva(r_ohm=0.3, x_ohm=0.4, v_kv=10.0)
    assert resistive.z_ohm == pytest.approx(0.5)
    assert resistive.s_mva == pytest.approx(200.0)
    assert resistive.x_over_r == pytest.approx(0.4 / 0.3)
    assert resistive.elements[0].kind == "impedance"


def test_parallel_sum_single_phase_and_custom_base() -> None:
    parallel = short_circuit_mva(
        [
            {"name": "a", "s_mva": 100.0, "combine": "parallel"},
            {"name": "b", "s_mva": 50.0, "combine": "shunt"},
        ],
        v_kv=10.0,
    )
    assert parallel.elements[0].combine == "seed"
    assert parallel.elements[1].combine == "parallel"
    assert parallel.s_mva == pytest.approx(150.0)
    assert parallel.s_mva_complex == pytest.approx(150.0)

    pair = short_circuit_mva(
        [
            {"s_mva": 10.0},
            {"s_mva": 10.0, "combine": "series"},
        ]
    )
    assert pair.s_mva == pytest.approx(5.0)

    single = short_circuit_mva(s_mva=250.0, v_kv=10.0, system="1ph")
    assert single.system == "single_phase"
    assert single.i_a == pytest.approx(250e6 / V)
    assert single.i_ka == pytest.approx(25.0)
    assert single.z_ohm == pytest.approx(0.4)
    assert single.i_base_ka == pytest.approx(10.0)
    assert single.z_base_ohm == pytest.approx(1.0)

    shifted = short_circuit_mva(s_mva=250.0, v_kv=10.0, s_base_mva=50.0)
    assert shifted.z_pu == pytest.approx(0.2)
    assert shifted.z_base_ohm == pytest.approx(2.0)
    assert shifted.s_mva == pytest.approx(250.0)

    named = short_circuit_mva(z_ohm=0.2, v_kv=10.0, kind="cable", x_over_r=10.0)
    assert named.elements[0].kind == "line"
    assert named.s_mva == pytest.approx(500.0)


def test_bad_options_and_semicolon_csv(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="one short-circuit specification"):
        short_circuit_mva(s_mva=10.0, i_ka=1.0)
    with pytest.raises(ValueError, match="not both"):
        short_circuit_mva(CSV, s_mva=10.0)
    with pytest.raises(ValueError, match="v_kv or v_v"):
        short_circuit_mva(s_mva=10.0, v_kv=10.0, v_v=10_000.0)
    with pytest.raises(ValueError, match="v_kv"):
        short_circuit_mva(s_mva=10.0, v_kv=0.0)
    with pytest.raises(ValueError, match="s_base_mva"):
        short_circuit_mva(s_mva=10.0, s_base_mva=-1.0)
    with pytest.raises(ValueError, match="system"):
        short_circuit_mva(s_mva=10.0, system="dc")
    with pytest.raises(ValueError, match="stage CSV"):
        short_circuit_mva()
    with pytest.raises(ValueError, match="z_percent or z_pu"):
        short_circuit_mva(s_rated_mva=20.0, z_percent=8.0, z_pu=0.08)
    with pytest.raises(ValueError, match="transformer requires"):
        short_circuit_mva(kind="transformer", s_rated_mva=20.0)
    with pytest.raises(ValueError, match="8 means 8%"):
        short_circuit_mva(s_rated_mva=20.0, z_percent=0.0)
    with pytest.raises(ValueError, match="resistance"):
        short_circuit_mva(r_ohm=-0.2, x_ohm=0.4)
    with pytest.raises(ValueError, match="does not match"):
        short_circuit_mva(r_ohm=0.1, x_ohm=0.2, x_over_r=10.0)
    with pytest.raises(ValueError, match="kind"):
        short_circuit_mva(kind="line", s_mva=100.0)
    with pytest.raises(ValueError, match="combine"):
        short_circuit_mva(
            [{"s_mva": 10.0}, {"s_mva": 10.0, "combine": "mesh"}],
        )
    with pytest.raises(ValueError, match="specification"):
        short_circuit_mva(name="bare")
    with pytest.raises(ValueError, match="cancel"):
        short_circuit_mva(
            [{"x_ohm": 0.4}, {"x_ohm": -0.4, "combine": "series"}],
        )
    with pytest.raises(ValueError, match="parallel"):
        short_circuit_mva(
            [{"x_ohm": 1.0}, {"x_ohm": -1.0, "combine": "parallel"}],
        )
    with pytest.raises(ValueError, match="unknown column"):
        short_circuit_mva([{"s_mva": 10.0, "student": "x"}])
    with pytest.raises(FileNotFoundError):
        short_circuit_mva(tmp_path / "missing.csv")
    with pytest.raises(ValueError, match="one element"):
        format_single_line(short_circuit_mva([{"s_mva": 1.0}, {"s_mva": 1.0}]))

    empty = tmp_path / "empty.csv"
    empty.write_text("name,s_mva\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no data"):
        short_circuit_mva(empty)

    semicolon = tmp_path / "stages.csv"
    semicolon.write_text(
        "name;kind;combine;s_mva;x_over_r\n"
        "grid;source;series;500;10\n"
        "feeder;source;series;250;10\n",
        encoding="utf-8",
    )
    parsed = short_circuit_mva(semicolon, v_kv=10.0)
    assert parsed.elements[0].name == "grid"
    assert parsed.s_mva == pytest.approx(500.0 * 250.0 / 750.0)
    assert parsed.x_over_r == pytest.approx(10.0)

    aliased = short_circuit_mva([{"uk": 8.0, "sn": 20.0, "xr": 10.0}], v_kv=10.0)
    assert aliased.s_mva == pytest.approx(250.0)
    assert aliased.elements[0].kind == "transformer"


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert (
        "short-circuit-mva single: "
        "S=250.0000 MVA  I=14.4338 kA  Z=0.4000 ohm  z_pu=0.4000 pu  X/R=inf"
        in completed.stdout
    )
    assert "S=173.2051 MVA  I=10.0000 kA" in completed.stdout
    assert "X/R=10.0000" in completed.stdout
    assert "S_sc=150.0000 MVA  I_sc=8.6603 kA" in completed.stdout
    assert "Srun_MVA" in completed.stdout
    png = TOOL / "examples" / "output" / "short_circuit_mva_demo.png"
    out_csv = TOOL / "examples" / "output" / "short_circuit_mva_demo.csv"
    assert png.is_file() and png.stat().st_size > 1000
    assert "motor" in out_csv.read_text(encoding="utf-8")
