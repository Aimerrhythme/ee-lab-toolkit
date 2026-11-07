"""Smoke tests for the short-circuit sample export tool."""

from __future__ import annotations

import builtins
import csv
import math
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from pp_fault_synth_export import (  # noqa: E402
    CSV_COLUMNS,
    _builtin_feeder,
    _walk_radial,
    _ybus_points,
    format_preview,
    format_table,
    pp_fault_synth_export,
)

CSV = TOOL / "examples" / "data" / "synthetic_radial_feeder.csv"
FAULTS = ("AG", "BG", "CG", "AB", "BC", "CA", "ABC")
PREVIEW = (
    "pp-fault-synth-export: engine=zbus network=radial samples=105  "
    "AG@B0 Rf=0.0000 If=12371.7915 A Vmin=0.0000 pu  "
    "BC@B0 If=12500.0000 A  ABC@B0 If=14433.7567 A"
)


def _bolted(result, bus_id, fault):
    rows = [
        sample
        for sample in result.samples
        if sample.bus_id == bus_id and sample.fault_type == fault and sample.r_f_ohm == 0.0
    ]
    assert len(rows) == 1
    return rows[0]


def test_source_bus_closed_forms_and_protection_labels() -> None:
    result = pp_fault_synth_export(CSV, engine="zbus")
    assert result.engine == "zbus"
    assert result.network == "radial"
    assert result.n_samples == 105
    assert result.n_grid == 105
    assert result.anchor_bus == "B0"
    assert result.remote_bus == "B4"
    assert result.v_kv == pytest.approx(10.0)
    assert result.z_base_ohm == pytest.approx(10.0)
    assert result.i_base_a == pytest.approx(10e6 / (math.sqrt(3.0) * 10_000.0))
    assert result.seed == 42

    i_abc = 10_000.0 / (math.sqrt(3.0) * 0.4)
    abc = _bolted(result, "B0", "ABC")
    assert abc.i_fault_mag_a == pytest.approx(i_abc)
    assert abc.i_fault_mag_a == pytest.approx(14433.756729740645)
    assert abc.i_phase_a_a == pytest.approx(abc.i_phase_b_a)
    assert abc.i_phase_b_a == pytest.approx(abc.i_phase_c_a)
    assert abc.v_bus_mag_pu == pytest.approx(0.0)
    assert abc.v_a_pu == abc.v_b_pu == abc.v_c_pu == pytest.approx(0.0)
    assert abc.label_protect == "three-phase"
    assert abc.fault_type_code == 7
    assert abc.line_id == "source"
    assert abc.distance_km == pytest.approx(0.0)
    assert abc.i_fault_mag_pu == pytest.approx(abc.i_fault_mag_a / result.i_base_a)

    # Z1 = Z2 and |Z0| = 1.5 |Z1| with the same angle, so Ia = 6/7 of the three-phase current.
    ag = _bolted(result, "B0", "AG")
    assert ag.i_fault_mag_a == pytest.approx(i_abc * 6.0 / 7.0)
    assert ag.i_phase_a_a == pytest.approx(ag.i_fault_mag_a)
    assert ag.i_phase_b_a == pytest.approx(0.0)
    assert ag.i_phase_c_a == pytest.approx(0.0)
    assert ag.v_a_pu == pytest.approx(0.0)
    assert ag.v_b_pu == pytest.approx(math.sqrt(57.0) / 7.0)
    assert ag.v_c_pu == pytest.approx(ag.v_b_pu)
    assert ag.v_bus_mag_pu == pytest.approx(0.0)
    assert ag.label_protect == "phase-to-ground"
    assert ag.fault_type_code == 1

    bc = _bolted(result, "B0", "BC")
    assert bc.i_fault_mag_a == pytest.approx(12_500.0)
    assert bc.i_phase_a_a == pytest.approx(0.0)
    assert bc.i_phase_b_a == pytest.approx(12_500.0)
    assert bc.i_phase_c_a == pytest.approx(12_500.0)
    assert bc.v_a_pu == pytest.approx(1.0)
    assert bc.v_b_pu == pytest.approx(0.5)
    assert bc.v_c_pu == pytest.approx(0.5)
    assert bc.label_protect == "phase-to-phase"
    assert bc.fault_type_code == 5

    bg = _bolted(result, "B0", "BG")
    cg = _bolted(result, "B0", "CG")
    assert bg.i_phase_b_a == pytest.approx(ag.i_fault_mag_a)
    assert bg.i_phase_a_a == pytest.approx(0.0)
    assert bg.i_phase_c_a == pytest.approx(0.0)
    assert bg.v_b_pu == pytest.approx(0.0)
    assert cg.i_phase_c_a == pytest.approx(ag.i_fault_mag_a)
    assert cg.i_phase_a_a == pytest.approx(0.0)
    assert cg.v_c_pu == pytest.approx(0.0)

    ab = _bolted(result, "B0", "AB")
    ca = _bolted(result, "B0", "CA")
    assert ab.i_phase_c_a == pytest.approx(0.0)
    assert ab.i_phase_a_a == pytest.approx(ab.i_phase_b_a)
    assert ab.v_c_pu == pytest.approx(1.0)
    assert ca.i_phase_b_a == pytest.approx(0.0)
    assert ca.i_phase_a_a == pytest.approx(ca.i_phase_c_a)
    assert ca.v_b_pu == pytest.approx(1.0)

    assert {sample.fault_type for sample in result.samples} == set(FAULTS)
    assert {sample.label_protect for sample in result.samples} == {
        "phase-to-ground",
        "phase-to-phase",
        "three-phase",
    }
    assert format_preview(result) == PREVIEW
    assert format_table(result) == result.summary
    assert "If_ABC=2225.3058 A" in result.summary
    assert "1.0785" in result.summary


def test_downstream_bus_adds_every_section_and_fault_resistance_reduces_current() -> None:
    result = pp_fault_synth_export(engine="zbus")
    z_source = 0.4 / math.sqrt(101.0) + 1j * 4.0 / math.sqrt(101.0)
    z_lines = (
        complex(0.405, 0.525)
        + complex(0.48, 0.444)
        + complex(0.44, 0.304)
        + complex(0.39, 0.24)
    )
    expected = abs((10_000.0 / math.sqrt(3.0)) / (z_source + z_lines))
    remote = _bolted(result, "B4", "ABC")
    assert remote.distance_km == pytest.approx(4.1)
    assert remote.line_id == "L4"
    assert remote.i_fault_mag_a == pytest.approx(expected)
    assert remote.i_fault_mag_a < _bolted(result, "B0", "ABC").i_fault_mag_a

    currents = [
        _bolted(result, bus, "ABC").i_fault_mag_a for bus in ("B0", "B1", "B2", "B3", "B4")
    ]
    assert currents == sorted(currents, reverse=True)

    with_rf = pp_fault_synth_export(buses="B0", fault_types="AG", r_fault_ohm=(0.0, 5.0))
    bolted = with_rf.samples[0]
    resistive = with_rf.samples[1]
    assert resistive.r_f_ohm == pytest.approx(5.0)
    assert resistive.i_fault_mag_a < bolted.i_fault_mag_a
    assert resistive.v_a_pu > 0.0

    # Off the source bus, Z0 is no longer a real multiple of Z1, so the healthy
    # phase voltages split while the faulted phase stays at zero for Rf = 0.
    mid = _bolted(result, "B1", "AG")
    assert mid.v_a_pu == pytest.approx(0.0)
    assert mid.i_phase_b_a == pytest.approx(0.0)
    assert mid.i_phase_c_a == pytest.approx(0.0)
    assert mid.v_b_pu != pytest.approx(mid.v_c_pu)


def test_csv_schema_and_builtin_feeder_match(tmp_path: Path) -> None:
    out_csv = tmp_path / "samples.csv"
    from_file = pp_fault_synth_export(CSV, output_csv=out_csv, show=False)
    builtin = pp_fault_synth_export()
    assert [sample.i_fault_mag_a for sample in from_file.samples] == pytest.approx(
        [sample.i_fault_mag_a for sample in builtin.samples]
    )
    with out_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == list(CSV_COLUMNS)
        rows = list(reader)
    assert len(rows) == 105
    assert {row["fault_type"] for row in rows} == set(FAULTS)
    assert {row["label_protect"] for row in rows} == {
        "phase-to-ground",
        "phase-to-phase",
        "three-phase",
    }
    assert rows[0]["engine"] == "zbus"
    assert rows[0]["sample_id"] == "1"
    assert "R_f_ohm" in rows[0]
    assert "I_phase_a_A" in rows[0]
    assert "V_bus_mag_pu" in rows[0]
    assert from_file.frame.columns.tolist() == list(CSV_COLUMNS)
    assert len(from_file.frame) == 105


def test_numpy_ybus_matches_the_series_walk() -> None:
    source, lines = _builtin_feeder(1.5)
    walked = _walk_radial(source, lines, 10_000.0)
    ids = {point.bus_id: index for index, point in enumerate(walked)}
    names = {index: point.bus_id for point, index in ((item, ids[item.bus_id]) for item in walked)}
    v_ll = {ids[point.bus_id]: point.v_ll_v for point in walked}
    shunts = [(ids[source.bus_id], source.z1, source.z0)]
    series = [
        (ids[line.from_bus], ids[line.to_bus], line.z1, line.z0, line.length_km, line.name, False)
        for line in lines
    ]
    inverted = _ybus_points(names, v_ll, shunts, series, 10.0)
    by_bus = {point.bus_id: point for point in inverted}
    for point in walked:
        other = by_bus[point.bus_id]
        assert other.z1_ohm.real == pytest.approx(point.z1_ohm.real, rel=1e-9, abs=1e-9)
        assert other.z1_ohm.imag == pytest.approx(point.z1_ohm.imag, rel=1e-9, abs=1e-9)
        assert other.z0_ohm.real == pytest.approx(point.z0_ohm.real, rel=1e-9, abs=1e-9)
        assert other.distance_km == pytest.approx(point.distance_km)
        assert other.line_id == point.line_id


def test_subsample_is_repeatable_and_keeps_major_types() -> None:
    first = pp_fault_synth_export(n_samples=40, seed=42)
    second = pp_fault_synth_export(n_samples=40, seed=42)
    assert first.n_grid == 105
    assert first.n_samples == 40
    assert [sample.fault_type for sample in first.samples] == [
        sample.fault_type for sample in second.samples
    ]
    assert [sample.bus_id for sample in first.samples] == [
        sample.bus_id for sample in second.samples
    ]
    assert {sample.fault_type for sample in first.samples} == set(FAULTS)
    assert "samples=40 grid=105" in first.preview

    six = pp_fault_synth_export(n_samples=6, seed=42)
    assert [(sample.bus_id, sample.fault_type, sample.r_f_ohm) for sample in six.samples] == [
        ("B3", "CG", 1.0),
        ("B0", "BG", 1.0),
        ("B4", "BC", 5.0),
        ("B0", "ABC", 1.0),
        ("B2", "BC", 0.0),
        ("B4", "AG", 5.0),
    ]
    other = pp_fault_synth_export(n_samples=6, seed=7)
    assert [sample.fault_type for sample in other.samples] != [
        sample.fault_type for sample in six.samples
    ]


def test_zbus_fallback_does_not_need_pandapower(tmp_path: Path) -> None:
    real_import = builtins.__import__

    def blocked(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pandapower" or name.startswith("pandapower."):
            raise ImportError("blocked for test")
        return real_import(name, globals, locals, fromlist, level)

    builtins.__import__ = blocked
    try:
        fallback = pp_fault_synth_export(engine="auto", buses="B0", fault_types="ABC", r_fault_ohm=0.0)
        assert fallback.engine == "zbus"
        assert fallback.network == "radial"
        assert _bolted(fallback, "B0", "ABC").i_fault_mag_a == pytest.approx(14433.756729740645)
        with pytest.raises(ImportError, match="pandapower"):
            pp_fault_synth_export(engine="pandapower")
    finally:
        builtins.__import__ = real_import

    png = tmp_path / "samples.png"
    drawn = pp_fault_synth_export(CSV, output_png=png, show=False)
    assert drawn.fig is None
    assert png.is_file() and png.stat().st_size > 1000


def test_bad_options(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="r_fault_ohm"):
        pp_fault_synth_export(r_fault_ohm=-1.0)
    with pytest.raises(ValueError, match="fault_types"):
        pp_fault_synth_export(fault_types="LLG")
    with pytest.raises(ValueError, match="v_kv"):
        pp_fault_synth_export(v_kv=0.0)
    with pytest.raises(ValueError, match="engine"):
        pp_fault_synth_export(engine="iec")
    with pytest.raises(ValueError, match="n_samples"):
        pp_fault_synth_export(n_samples=200)
    with pytest.raises(ValueError, match="unknown bus"):
        pp_fault_synth_export(buses="B9")
    with pytest.raises(FileNotFoundError):
        pp_fault_synth_export(tmp_path / "missing.csv")
    with pytest.raises(ValueError, match="cigre_mv"):
        pp_fault_synth_export(engine="zbus", network="cigre_mv")

    looped = tmp_path / "loop.csv"
    text = CSV.read_text(encoding="utf-8")
    looped.write_text(
        text + "line,L5,B4,B1,0.2,0.1,0.1,0.3,0.3,,,\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="loop"):
        pp_fault_synth_export(looped)

    only = pp_fault_synth_export(buses=["B4"], fault_types=["3ph", "1ph"], r_fault_ohm=0)
    assert [sample.fault_type for sample in only.samples] == ["AG", "ABC"]
    assert only.samples[0].fault_type_code == 1
    assert only.samples[1].fault_type_code == 7


def test_pandapower_cigre_and_radial_mirror() -> None:
    pytest.importorskip("pandapower")
    cigre = pp_fault_synth_export(engine="pandapower", network="cigre_mv")
    assert cigre.engine == "pandapower"
    assert cigre.n_samples == 15 * 7 * 3
    assert {sample.fault_type for sample in cigre.samples} == set(FAULTS)
    assert list(cigre.frame.columns) == list(CSV_COLUMNS)
    bus0 = _bolted(cigre, "Bus 0", "ABC")
    assert bus0.i_fault_mag_a == pytest.approx(5000e6 / (math.sqrt(3.0) * 110e3))
    assert bus0.line_id == "source"
    bus1 = _bolted(cigre, "Bus 1", "ABC")
    bus7 = _bolted(cigre, "Bus 7", "ABC")
    assert bus1.i_fault_mag_a < bus0.i_fault_mag_a
    assert bus7.line_id == "Line 7-8"
    assert all(sample.line_id != "Line 6-7" for sample in cigre.samples)
    assert all(math.isfinite(sample.i_fault_mag_a) and sample.i_fault_mag_a > 0.0 for sample in cigre.samples)

    mirror = pp_fault_synth_export(engine="pandapower", network="radial")
    radial = pp_fault_synth_export(engine="zbus")
    assert mirror.n_samples == radial.n_samples
    assert [sample.i_fault_mag_a for sample in mirror.samples] == pytest.approx(
        [sample.i_fault_mag_a for sample in radial.samples],
        rel=1e-9,
        abs=1e-6,
    )
    assert [sample.v_b_pu for sample in mirror.samples] == pytest.approx(
        [sample.v_b_pu for sample in radial.samples],
        rel=1e-9,
        abs=1e-8,
    )

    auto = pp_fault_synth_export(engine="auto", buses="Bus 1", fault_types="ABC", r_fault_ohm=0.0)
    assert auto.engine == "pandapower"
    assert auto.network == "cigre_mv"


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert PREVIEW in completed.stdout
    assert "remote bus=B4 distance=4.1000 km" in completed.stdout
    assert "phase-to-ground" in completed.stdout
    png = TOOL / "examples" / "output" / "pp_fault_synth_export_demo.png"
    out_csv = TOOL / "examples" / "output" / "pp_fault_synth_export_demo.csv"
    assert png.is_file() and png.stat().st_size > 1000
    text = out_csv.read_text(encoding="utf-8")
    for fault in FAULTS:
        assert fault in text
    assert "label_protect" in text
