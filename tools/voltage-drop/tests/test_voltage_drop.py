"""Smoke tests for the voltage-drop Python tool."""

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

from voltage_drop import format_single_line, format_table, voltage_drop

CSV = TOOL / "examples" / "data" / "synthetic_feeder_sections.csv"
V_NOMINAL = 10_000.0


def _textbook_drop(current: float, resistance: float, reactance: float, pf: float) -> float:
    cos_phi = abs(pf)
    sin_phi = math.sqrt(1.0 - cos_phi * cos_phi)
    if pf < 0.0:
        sin_phi = -sin_phi
    return math.sqrt(3.0) * current * (resistance * cos_phi + reactance * sin_phi)


def test_current_formula_matches_power_formula_and_percent() -> None:
    result = voltage_drop(
        length_km=2.0,
        r_ohm_per_km=0.4,
        x_ohm_per_km=0.35,
        i_a=80.0,
        pf=0.8,
        v_nominal=V_NOMINAL,
    )
    row = result.sections[0]
    expected = _textbook_drop(80.0, 0.8, 0.7, 0.8)
    assert row.r_ohm == pytest.approx(0.8)
    assert row.x_ohm == pytest.approx(0.7)
    assert row.r_used_ohm == pytest.approx(0.8)
    assert row.delta_v == pytest.approx(expected)
    assert row.delta_v == pytest.approx(146.8779084818408)
    assert row.delta_v_percent == pytest.approx(100.0 * expected / V_NOMINAL)
    assert result.v_end == pytest.approx(V_NOMINAL - expected)
    assert row.i_a == pytest.approx(80.0)
    assert row.pf == pytest.approx(0.8)
    assert result.system == "three_phase"
    assert result.voltage_basis == "nominal"
    assert result.load_mode == "tap"
    assert format_single_line(result) == (
        "voltage-drop single: dV=146.8779 V (1.4688 %) I=80.000 A pf=0.8000 V_recv=9853.1221 V"
    )

    active = math.sqrt(3.0) * V_NOMINAL * 80.0 * 0.8
    reactive = math.sqrt(3.0) * V_NOMINAL * 80.0 * 0.6
    by_power = voltage_drop(r_ohm=0.8, x_ohm=0.7, p_w=active, q_var=reactive, v_nominal=V_NOMINAL)
    assert by_power.sections[0].delta_v == pytest.approx(expected)
    by_pf = voltage_drop(r_ohm=0.8, x_ohm=0.7, p_w=active, pf=0.8, v_nominal=V_NOMINAL)
    assert by_pf.sections[0].q_var == pytest.approx(reactive)
    assert by_pf.sections[0].delta_v == pytest.approx(expected)

    p_kw = active / 1000.0
    q_kvar = reactive / 1000.0
    percent = (p_kw * 0.8 + q_kvar * 0.7) / (10.0 * 10.0**2)
    assert row.delta_v_percent == pytest.approx(percent)


def test_leading_pf_reduces_the_drop() -> None:
    lagging = voltage_drop(r_ohm=0.8, x_ohm=0.7, i_a=80.0, pf=0.8, v_nominal=V_NOMINAL)
    leading = voltage_drop(r_ohm=0.8, x_ohm=0.7, i_a=80.0, pf=-0.8, v_nominal=V_NOMINAL)
    expected = _textbook_drop(80.0, 0.8, 0.7, -0.8)
    assert leading.sections[0].delta_v == pytest.approx(expected)
    assert leading.sections[0].delta_v < lagging.sections[0].delta_v
    assert leading.sections[0].q_var < 0.0
    assert leading.sections[0].pf == pytest.approx(-0.8)

    active = math.sqrt(3.0) * V_NOMINAL * 80.0 * 0.8
    reactive = -math.sqrt(3.0) * V_NOMINAL * 80.0 * 0.6
    by_q = voltage_drop(r_ohm=0.8, x_ohm=0.7, p_w=active, q_var=reactive, v_nominal=V_NOMINAL)
    assert by_q.sections[0].delta_v == pytest.approx(leading.sections[0].delta_v)


def test_unity_pf_ignores_reactance_and_pure_reactive_uses_x() -> None:
    with_x = voltage_drop(r_ohm=1.0, x_ohm=5.0, i_a=10.0, pf=1.0, v_nominal=1000.0)
    no_x = voltage_drop(r_ohm=1.0, x_ohm=0.0, i_a=10.0, pf=1.0, v_nominal=1000.0)
    assert with_x.sections[0].delta_v == pytest.approx(no_x.sections[0].delta_v)
    assert with_x.sections[0].delta_v == pytest.approx(math.sqrt(3.0) * 10.0 * 1.0)

    reactive = voltage_drop(x_ohm=1.0, q_var=10_000.0, v_nominal=V_NOMINAL)
    assert reactive.sections[0].p_w == pytest.approx(0.0)
    assert reactive.sections[0].delta_v == pytest.approx(1.0)
    pure_i = voltage_drop(x_ohm=1.0, i_a=10.0, pf=0.0, v_nominal=V_NOMINAL)
    assert pure_i.sections[0].delta_v == pytest.approx(math.sqrt(3.0) * 10.0)


def test_radial_csv_accumulates_downstream_taps(tmp_path: Path) -> None:
    png = tmp_path / "feeder.png"
    out_csv = tmp_path / "feeder.csv"
    result = voltage_drop(CSV, output_png=png, output_csv=out_csv, show=False)

    assert len(result.sections) == 4
    assert [row.name for row in result.sections] == ["L1", "L2", "L3", "L4"]
    assert result.sections[0].from_bus == "B0"
    assert result.sections[-1].to_bus == "B4"
    assert result.sections[0].p_w == pytest.approx(800_000.0)
    assert result.sections[0].p_through_w == pytest.approx(1_780_000.0)
    assert result.sections[0].q_through_var == pytest.approx(700_000.0)
    assert result.sections[-1].p_through_w == pytest.approx(180_000.0)
    assert [row.delta_v for row in result.sections] == pytest.approx([108.84, 64.8, 27.2, 8.94])
    assert [row.v_recv for row in result.sections] == pytest.approx([9891.16, 9826.36, 9799.16, 9790.22])
    assert result.delta_v_total == pytest.approx(209.78)
    assert result.delta_v_percent_total == pytest.approx(2.0978)
    assert result.v_end == pytest.approx(9790.22)
    assert result.sections[0].r_ohm == pytest.approx(0.27 * 1.5)
    assert result.sections[0].x_ohm == pytest.approx(0.35 * 1.5)
    assert "total drop=209.7800 V (2.0978 %)  V_end=9790.2200 V" in result.summary
    assert "108.8400" in result.summary
    assert format_table(result) == result.summary
    assert png.is_file()
    assert png.stat().st_size > 1000
    assert result.fig is None
    text = out_csv.read_text(encoding="utf-8")
    assert "p_through_w" in text
    assert "1780000" in text
    assert "L1" in text


def test_through_mode_does_not_sum_taps_and_source_offset() -> None:
    through = voltage_drop(CSV, load_mode="through")
    assert through.sections[0].p_through_w == pytest.approx(800_000.0)
    assert through.sections[0].delta_v == pytest.approx(48.15)
    assert through.delta_v_total < 209.0

    offset = voltage_drop(CSV, v_source=10_200.0)
    assert offset.sections[0].delta_v == pytest.approx(108.84)
    assert offset.sections[0].v_send == pytest.approx(10_200.0)
    assert offset.sections[0].v_recv == pytest.approx(10_200.0 - 108.84)
    assert offset.v_end == pytest.approx(10_200.0 - 209.78)


def test_single_phase_uses_the_loop_and_sending_basis_updates_voltage() -> None:
    single = voltage_drop(
        r_ohm=0.8,
        x_ohm=0.7,
        i_a=80.0,
        pf=0.8,
        v_nominal=V_NOMINAL,
        system="1ph",
    )
    assert single.system == "single_phase"
    assert single.sections[0].r_used_ohm == pytest.approx(1.6)
    assert single.sections[0].x_used_ohm == pytest.approx(1.4)
    assert single.sections[0].delta_v == pytest.approx(2.0 * 80.0 * (0.8 * 0.8 + 0.7 * 0.6))
    assert single.sections[0].p_w == pytest.approx(V_NOMINAL * 80.0 * 0.8)

    rows = [
        {"name": "A", "r_ohm": 1.0, "x_ohm": 0.0, "p_w": 10_000.0, "q_var": 0.0},
        {"name": "B", "r_ohm": 1.0, "x_ohm": 0.0, "p_w": 10_000.0, "q_var": 0.0},
    ]
    nominal = voltage_drop(rows, load_mode="flow", v_nominal=V_NOMINAL, voltage_basis="nominal")
    sending = voltage_drop(rows, load_mode="through", v_nominal=V_NOMINAL, voltage_basis="sending")
    assert nominal.sections[0].delta_v == pytest.approx(1.0)
    assert nominal.sections[1].delta_v == pytest.approx(1.0)
    assert sending.sections[0].delta_v == pytest.approx(1.0)
    assert sending.sections[0].v_recv == pytest.approx(9999.0)
    assert sending.sections[1].v_send == pytest.approx(9999.0)
    assert sending.sections[1].delta_v == pytest.approx(10_000.0 / 9999.0)

    shifted = voltage_drop(
        r_ohm=0.8,
        x_ohm=0.7,
        i_a=80.0,
        pf=0.8,
        v_nominal=V_NOMINAL,
        v_source=9800.0,
        voltage_basis="send",
    )
    base = _textbook_drop(80.0, 0.8, 0.7, 0.8)
    assert shifted.sections[0].delta_v == pytest.approx(base * V_NOMINAL / 9800.0)


def test_missing_bus_names_chain_from_the_source() -> None:
    result = voltage_drop(
        [
            {"r_ohm": 1.0, "p_kw": 1.0, "q_kvar": 0.0},
            {"r_ohm": 1.0, "p_kw": 1.0, "q_kvar": 0.0},
        ],
        v_nominal=V_NOMINAL,
    )
    assert [row.name for row in result.sections] == ["section1", "section2"]
    assert result.sections[0].from_bus == "source"
    assert result.sections[0].to_bus == "B1"
    assert result.sections[1].from_bus == "B1"
    assert result.sections[1].to_bus == "B2"
    assert result.sections[0].p_through_w == pytest.approx(2000.0)
    assert result.sections[1].p_through_w == pytest.approx(1000.0)
    assert math.isnan(result.sections[0].length_km)


def test_bad_options_and_semicolon_csv(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="pf"):
        voltage_drop(r_ohm=1.0, i_a=10.0, pf=80.0)
    with pytest.raises(ValueError, match="length_km"):
        voltage_drop(length_km=-1.0, r_ohm_per_km=0.2, i_a=10.0)
    with pytest.raises(ValueError, match="resistance or reactance"):
        voltage_drop(i_a=10.0, pf=0.9)
    with pytest.raises(ValueError, match="load"):
        voltage_drop(r_ohm=1.0)
    with pytest.raises(ValueError, match="not both"):
        voltage_drop(r_ohm=1.0, i_a=10.0, p_kw=5.0, pf=0.8)
    with pytest.raises(ValueError, match="not both"):
        voltage_drop(CSV, i_a=10.0)
    with pytest.raises(ValueError, match="v_nominal"):
        voltage_drop(r_ohm=1.0, i_a=1.0, v_nominal=0.0)
    with pytest.raises(ValueError, match="system"):
        voltage_drop(r_ohm=1.0, i_a=1.0, system="dc")
    with pytest.raises(ValueError, match="resistance"):
        voltage_drop(r_ohm=-0.2, i_a=1.0)
    with pytest.raises(ValueError, match="feeder CSV"):
        voltage_drop()
    with pytest.raises(FileNotFoundError):
        voltage_drop(tmp_path / "missing.csv")
    with pytest.raises(ValueError, match="unknown column"):
        voltage_drop([{"r_ohm": 1.0, "i_a": 1.0, "student": "x"}])

    empty = tmp_path / "empty.csv"
    empty.write_text("section,r_ohm,i_a\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no data"):
        voltage_drop(empty)

    semicolon = tmp_path / "feeder.csv"
    semicolon.write_text(
        "section;length_km;r_per_km;x_per_km;i;pf\n"
        "S1;2;0.4;0.35;80;0.8\n",
        encoding="utf-8",
    )
    parsed = voltage_drop(semicolon, v_nominal=V_NOMINAL)
    assert parsed.sections[0].name == "S1"
    assert parsed.sections[0].delta_v == pytest.approx(_textbook_drop(80.0, 0.8, 0.7, 0.8))

    no_length = voltage_drop(r_ohm=0.405, x_ohm=0.525, p_kw=1780, q_kvar=700, v_nominal=V_NOMINAL)
    assert math.isnan(no_length.sections[0].length_km)
    assert no_length.sections[0].delta_v == pytest.approx(108.84)
    profile = tmp_path / "index.png"
    voltage_drop(
        r_ohm=0.405,
        x_ohm=0.525,
        p_kw=1780,
        q_kvar=700,
        v_nominal=V_NOMINAL,
        output_png=profile,
    )
    assert profile.is_file()
    assert profile.stat().st_size > 1000


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "voltage-drop single: dV=146.8779 V (1.4688 %) I=80.000 A pf=0.8000" in completed.stdout
    assert "total drop=209.7800 V (2.0978 %)  V_end=9790.2200 V" in completed.stdout
    assert "Pthru_kW" in completed.stdout
    png = TOOL / "examples" / "output" / "voltage_drop_demo.png"
    out_csv = TOOL / "examples" / "output" / "voltage_drop_demo.csv"
    assert png.is_file()
    assert png.stat().st_size > 1000
    assert "L4" in out_csv.read_text(encoding="utf-8")
