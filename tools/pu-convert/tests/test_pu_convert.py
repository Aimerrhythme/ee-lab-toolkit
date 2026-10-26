"""Smoke tests for the pu-convert Python tool."""

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

from pu_convert import format_table, pu_convert

CSV = TOOL / "examples" / "data" / "synthetic_quantities.csv"
S_BASE = 100e6
V_HV = 220e3
V_LV = 110e3


def _by_name(result, name: str):
    hits = [row for row in result.rows if row.name == name]
    assert len(hits) == 1
    return hits[0]


def test_default_bases_and_rated_voltage_is_one_pu() -> None:
    bases = pu_convert()
    assert bases.system == "three_phase"
    assert bases.rows == []
    assert bases.s_base == S_BASE
    assert bases.v_base == V_HV
    assert bases.v_base_hv == V_HV
    assert bases.v_base_lv == V_LV
    assert bases.z_base == V_HV**2 / S_BASE
    assert bases.z_base_hv == 484.0
    assert bases.z_base_lv == 121.0
    assert bases.z_base == pytest.approx(bases.v_base / (math.sqrt(3.0) * bases.i_base))
    assert bases.i_base_hv == pytest.approx(S_BASE / (math.sqrt(3.0) * V_HV))
    assert bases.i_base_lv == pytest.approx(2.0 * bases.i_base_hv)
    assert bases.i_base_lv == pytest.approx(S_BASE / (math.sqrt(3.0) * V_LV))

    rated = pu_convert(V_HV, quantity="V", side="hv")
    row = rated.rows[0]
    assert row.value_pu == pytest.approx(1.0)
    assert row.value_out == pytest.approx(1.0)
    assert row.unit_out == "pu"
    assert row.base_used == pytest.approx(V_HV)
    assert "484" in format_table(bases)


def test_named_quantities_units_and_round_trip() -> None:
    voltage = pu_convert(231, quantity="V", unit_hint="kV", side="hv")
    assert voltage.rows[0].value_pu == pytest.approx(1.05)
    assert voltage.rows[0].value_si == pytest.approx(231e3)

    current = pu_convert(1.0, quantity="I", direction="to_si", side="hv", unit_out="A")
    assert current.rows[0].value_si == pytest.approx(S_BASE / (math.sqrt(3.0) * V_HV))
    assert current.rows[0].value_out == pytest.approx(current.rows[0].value_si)

    power = pu_convert(
        [
            {"name": "s", "quantity": "S", "value": 80, "unit_hint": "MVA"},
            {"name": "p", "quantity": "P", "value": 60, "unit_hint": "MW"},
            {"name": "q", "quantity": "Q", "value": -45, "unit_hint": "Mvar"},
        ]
    )
    assert [row.value_pu for row in power.rows] == pytest.approx([0.8, 0.6, -0.45])
    assert [row.base_used for row in power.rows] == pytest.approx([S_BASE, S_BASE, S_BASE])

    ohms = pu_convert(48.4, quantity="X", unit_hint="ohm", side="hv")
    assert ohms.rows[0].value_pu == pytest.approx(0.1)
    assert ohms.rows[0].base_used == pytest.approx(484.0)
    back = pu_convert(ohms.rows[0].value_pu, quantity="X", direction="to_si", side="hv")
    assert back.rows[0].value_si == pytest.approx(48.4)
    assert back.rows[0].unit_out == "ohm"
    assert back.rows[0].value_pu == pytest.approx(0.1)


def test_transformer_referral_keeps_pu_and_scales_ohms() -> None:
    on_hv = pu_convert(48.4, quantity="X", unit_hint="ohm", side="hv")
    on_lv = pu_convert(12.1, quantity="X", unit_hint="ohm", side="lv")
    referred = pu_convert(48.4, quantity="Z", unit_hint="ohm", side="hv", refer_to="lv")
    assert on_hv.rows[0].value_pu == pytest.approx(on_lv.rows[0].value_pu)
    assert referred.rows[0].value_pu == pytest.approx(0.1)
    assert referred.rows[0].value_si == pytest.approx(12.1)
    assert referred.rows[0].winding == "lv"
    assert referred.rows[0].refer_to == "lv"
    assert referred.z_base_lv == pytest.approx(referred.z_base_hv * (V_LV / V_HV) ** 2)

    back = pu_convert(0.1, quantity="Z", direction="to_si", side="hv", refer_to="lv")
    assert back.rows[0].value_si == pytest.approx(12.1)
    assert back.rows[0].value_pu == pytest.approx(0.1)


def test_single_phase_current_base_and_custom_voltage() -> None:
    result = pu_convert(system="single_phase", v_base=10e3, side="same")
    assert result.system == "single_phase"
    assert result.i_base == pytest.approx(S_BASE / 10e3)
    assert result.z_base == pytest.approx((10e3) ** 2 / S_BASE)
    assert result.i_base_hv == pytest.approx(S_BASE / V_HV)
    row = pu_convert(10e3, quantity="V", system="1ph", v_base=10e3).rows[0]
    assert row.value_pu == pytest.approx(1.0)
    assert row.side == "same"


def test_batch_csv_matches_the_classroom_story(tmp_path: Path) -> None:
    png = tmp_path / "pu.png"
    out_csv = tmp_path / "pu.csv"
    result = pu_convert(CSV, output_png=png, output_csv=out_csv, show=False)

    assert len(result.rows) == 14
    assert _by_name(result, "hv_rated_voltage").value_pu == pytest.approx(1.0)
    assert _by_name(result, "hv_voltage_105").value_pu == pytest.approx(1.05)
    assert _by_name(result, "lv_rated_voltage").value_pu == pytest.approx(1.0)
    assert _by_name(result, "load_s").value_pu == pytest.approx(0.8)
    assert _by_name(result, "load_p").value_pu == pytest.approx(0.6)
    assert _by_name(result, "load_q").value_pu == pytest.approx(0.45)
    assert _by_name(result, "hv_reactance").value_pu == pytest.approx(0.1)
    assert _by_name(result, "lv_reactance").value_pu == pytest.approx(0.1)
    assert _by_name(result, "x_referred").value_si == pytest.approx(12.1)
    assert _by_name(result, "hv_resistance").value_pu == pytest.approx(0.05)
    assert _by_name(result, "x_to_si").value_out == pytest.approx(48.4)
    assert _by_name(result, "hv_v_back").value_out == pytest.approx(231.0)
    assert _by_name(result, "hv_v_back").unit_out == "kV"
    assert _by_name(result, "hv_current").value_si == pytest.approx(result.i_base_hv)
    assert _by_name(result, "lv_current").value_si == pytest.approx(result.i_base_lv)
    assert png.is_file()
    assert png.stat().st_size > 1000
    assert result.fig is None
    text = out_csv.read_text(encoding="utf-8")
    assert "hv_reactance" in text
    assert "value_pu" in text


def test_bad_options_and_semicolon_csv(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="quantity"):
        pu_convert(1.0, quantity="angle")
    with pytest.raises(ValueError, match="refer_to"):
        pu_convert(220.0, quantity="V", unit_hint="kV", side="hv", refer_to="lv")
    with pytest.raises(ValueError, match="s_base"):
        pu_convert(s_base=0)
    with pytest.raises(ValueError, match="unit_hint"):
        pu_convert(1.0, quantity="I", unit_hint="kV")
    with pytest.raises(ValueError, match="to_si"):
        pu_convert(231.0, quantity="V", direction="to_si", unit_hint="kV", side="hv")
    with pytest.raises(ValueError, match="not both"):
        pu_convert(1.0, csv_path=CSV)
    with pytest.raises(FileNotFoundError):
        pu_convert(tmp_path / "missing.csv")
    with pytest.raises(ValueError, match="converted row"):
        pu_convert(output_png=tmp_path / "empty.png")

    semicolon = tmp_path / "quantities.csv"
    semicolon.write_text(
        "name;quantity;value;unit_hint;direction;side\n"
        "v_hv;V;220;kV;to_pu;hv\n"
        "x_hv;X;48.4;ohm;to_pu;hv\n",
        encoding="utf-8",
    )
    parsed = pu_convert(semicolon)
    assert parsed.rows[0].value_pu == pytest.approx(1.0)
    assert parsed.rows[1].value_pu == pytest.approx(0.1)
    assert parsed.rows[1].name == "x_hv"


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "system=three_phase" in completed.stdout
    assert "hv_reactance" in completed.stdout
    assert "Z_hv=484" in completed.stdout
    png = TOOL / "examples" / "output" / "pu_convert_demo.png"
    out_csv = TOOL / "examples" / "output" / "pu_convert_demo.csv"
    assert png.is_file()
    assert png.stat().st_size > 1000
    assert "x_referred" in out_csv.read_text(encoding="utf-8")
