"""Smoke tests for the motor-torque-speed Python tool."""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")

import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from motor_torque_speed import format_table, motor_torque_speed

CSV = TOOL / "examples" / "data" / "motor_cases.csv"
OMEGA_SYNC = 2.0 * math.pi * 1500.0 / 60.0
V_PHASE = 380.0 / math.sqrt(3.0)


def _thevenin(v_phase: float, r1: float, x1: float, r2: float, x2: float, xm: float, rc: float = math.inf):
    z1 = complex(r1, x1)
    if math.isinf(rc):
        z_mag = complex(0.0, xm)
    else:
        z_mag = 1.0 / (1.0 / rc + 1.0 / complex(0.0, xm))
    v_th = v_phase * z_mag / (z1 + z_mag)
    z_th = z1 * z_mag / (z1 + z_mag)
    reactance = z_th.imag + x2
    magnitude = math.hypot(z_th.real, reactance)
    slip = r2 / magnitude
    torque = (3.0 / (2.0 * OMEGA_SYNC)) * (abs(v_th) ** 2) / (z_th.real + magnitude)
    return abs(v_th), z_th.real, z_th.imag, slip, torque


def _circuit_torque(slip: float, *, rc: float = math.inf, r2: float = 0.4, v_phase: float = V_PHASE) -> float:
    z1 = complex(0.5, 1.5)
    z_mag = complex(0.0, 40.0) if math.isinf(rc) else 1.0 / (1.0 / rc + 1.0 / complex(0.0, 40.0))
    z2 = complex(r2 / slip, 1.5)
    z_f = 1.0 / (1.0 / z_mag + 1.0 / z2)
    i1 = v_phase / (z1 + z_f)
    i2 = (i1 * z_f) / z2
    p_ag = 3.0 * (abs(i2) ** 2) * r2 / slip
    return p_ag / OMEGA_SYNC


def test_default_induction_matches_thevenin_and_circuit() -> None:
    case = motor_torque_speed().cases[0]
    v_th, r_th, x_th, slip, torque = _thevenin(V_PHASE, 0.5, 1.5, 0.4, 1.5, 40.0)

    assert case.name == ""
    assert case.motor == "induction"
    assert case.connection == "y"
    assert case.v == 380.0
    assert case.f == 50.0
    assert case.poles == 4
    assert case.n_sync_rpm == 1500.0
    assert case.omega_sync_rad_s == pytest.approx(OMEGA_SYNC)
    assert case.v_phase == pytest.approx(V_PHASE)
    assert case.v_th == pytest.approx(v_th, rel=1e-12)
    assert case.r_th == pytest.approx(r_th, rel=1e-12)
    assert case.x_th == pytest.approx(x_th, rel=1e-12)
    assert case.slip_breakdown == pytest.approx(slip, rel=1e-12)
    assert case.torque_breakdown_nm == pytest.approx(torque, rel=1e-12)
    assert case.torque_start_nm == pytest.approx(_circuit_torque(1.0), rel=1e-12)
    assert case.torque_start_nm < case.torque_breakdown_nm
    assert math.isnan(case.s_rated)
    assert "rated  undefined" in format_table(motor_torque_speed())
    assert "motor=induction" in format_table(motor_torque_speed())
    assert "n_sync=1500" in format_table(motor_torque_speed())

    assert case.slip[0] == pytest.approx(0.0)
    assert case.slip[-1] == pytest.approx(1.0)
    assert case.n_points == 401
    assert case.n_samples == 402
    assert np.any(np.isclose(case.slip, case.slip_breakdown, rtol=0.0, atol=1e-12))
    peak = int(np.argmin(np.abs(case.slip - case.slip_breakdown)))
    assert case.torque_nm[peak] == pytest.approx(case.torque_breakdown_nm, rel=1e-12)
    assert case.torque_nm.max() == pytest.approx(case.torque_breakdown_nm, rel=1e-12)
    assert case.torque_nm[0] == pytest.approx(0.0, abs=1e-12)
    assert case.i2_a[0] == pytest.approx(0.0, abs=1e-12)
    assert case.speed_rpm[0] == pytest.approx(1500.0)
    assert case.speed_rpm == pytest.approx((1.0 - case.slip) * 1500.0)
    assert case.i_line_a == pytest.approx(case.i_phase_a)
    assert case.power_factor[0] == pytest.approx(0.5 / math.hypot(0.5, 41.5), rel=1e-12)
    assert 0.0 < case.power_factor[peak] < 1.0

    point = motor_torque_speed(s_min=0.05, s_max=0.05, n_points=1).cases[0]
    assert point.n_samples == 1
    assert point.torque_nm[0] == pytest.approx(_circuit_torque(0.05), rel=1e-12)
    assert point.power_mech_w[0] == pytest.approx((1.0 - 0.05) * point.torque_nm[0] * OMEGA_SYNC, rel=1e-12)
    assert 0.0 < point.efficiency[0] < 1.0


def test_rotor_resistance_voltage_and_connection_scaling() -> None:
    base = motor_torque_speed().cases[0]
    high = motor_torque_speed(r2=1.2).cases[0]
    assert high.torque_breakdown_nm == pytest.approx(base.torque_breakdown_nm, rel=1e-12)
    assert high.slip_breakdown == pytest.approx(3.0 * base.slip_breakdown, rel=1e-12)
    assert high.torque_start_nm > base.torque_start_nm

    low = motor_torque_speed(v=304).cases[0]
    assert low.slip_breakdown == pytest.approx(base.slip_breakdown, rel=1e-12)
    assert low.torque_breakdown_nm == pytest.approx(0.64 * base.torque_breakdown_nm, rel=1e-12)
    assert low.torque_start_nm == pytest.approx(0.64 * base.torque_start_nm, rel=1e-12)

    delta = motor_torque_speed(connection="delta").cases[0]
    assert delta.connection == "d"
    assert delta.v_phase == pytest.approx(380.0)
    assert delta.torque_breakdown_nm == pytest.approx(3.0 * base.torque_breakdown_nm, rel=1e-12)
    assert delta.i_line_a[0] == pytest.approx(math.sqrt(3.0) * delta.i_phase_a[0])

    star = motor_torque_speed(connection="星形", motor="异步").cases[0]
    assert star.motor == "induction"
    assert star.connection == "y"
    assert star.torque_breakdown_nm == pytest.approx(base.torque_breakdown_nm, rel=1e-12)


def test_core_loss_power_balance_and_regions() -> None:
    case = motor_torque_speed(rc=200, s_min=0.04, s_max=0.04, n_points=1).cases[0]
    assert case.rc == 200.0
    assert case.torque_nm[0] == pytest.approx(_circuit_torque(0.04, rc=200), rel=1e-12)
    bare = _thevenin(V_PHASE, 0.5, 1.5, 0.4, 1.5, 40.0)
    with_core = _thevenin(V_PHASE, 0.5, 1.5, 0.4, 1.5, 40.0, rc=200)
    assert case.torque_breakdown_nm == pytest.approx(with_core[4], rel=1e-12)
    assert case.torque_breakdown_nm < bare[4]

    generating = motor_torque_speed(s_min=-0.05, s_max=-0.05, n_points=1).cases[0]
    assert generating.torque_nm[0] < 0.0
    assert generating.power_mech_w[0] < 0.0
    assert generating.power_in_w[0] < 0.0
    assert math.isnan(generating.efficiency[0])

    plugging = motor_torque_speed(s_min=1.2, s_max=1.2, n_points=1).cases[0]
    assert plugging.torque_nm[0] > 0.0
    assert plugging.power_mech_w[0] < 0.0


def test_induction_rated_power_and_given_slip() -> None:
    case = motor_torque_speed(p_rated=8000).cases[0]
    assert case.s_rated < case.slip_breakdown
    assert case.power_mech_rated_w == pytest.approx(8000.0, rel=1e-8)
    assert case.speed_rated_rpm == pytest.approx((1.0 - case.s_rated) * 1500.0)
    assert 0.0 < case.efficiency_rated < 1.0
    assert 0.0 < case.pf_rated < 1.0
    assert "eta=" in format_table(motor_torque_speed(p_rated=8000))

    given = motor_torque_speed(s_rated=0.05, p_rated=8000).cases[0]
    assert given.s_rated == pytest.approx(0.05)
    assert given.torque_rated_nm == pytest.approx(_circuit_torque(0.05), rel=1e-12)
    assert given.power_mech_rated_w != pytest.approx(8000.0, rel=0.01)

    with pytest.raises(ValueError, match="stable region"):
        motor_torque_speed(p_rated=1_000_000)


def test_separately_excited_and_shunt_lines() -> None:
    case = motor_torque_speed(motor="dc_separate").cases[0]
    omega0 = 220.0 / 1.5
    assert case.v == 220.0
    assert case.ra == 1.0
    assert case.k_phi == 1.5
    assert case.speed_noload_rpm == pytest.approx(omega0 * 60.0 / (2.0 * math.pi))
    assert case.torque_stall_nm == pytest.approx(330.0)
    assert case.i_stall_a == pytest.approx(220.0)
    assert case.speed_rpm[0] == pytest.approx(case.speed_noload_rpm)
    assert case.torque_nm[0] == pytest.approx(0.0)
    assert case.speed_rpm[-1] == pytest.approx(0.0, abs=1e-8)
    assert case.torque_nm[-1] == pytest.approx(330.0)
    assert math.isnan(case.power_factor[0])
    assert math.isnan(case.efficiency[0])
    assert case.efficiency[-1] == pytest.approx(0.0)

    torque = 100.0
    omega = omega0 - (1.0 / 1.5**2) * torque
    speed = omega * 60.0 / (2.0 * math.pi)
    mid = motor_torque_speed(motor="他励", t_rated=torque, p_rated=9999).cases[0]
    assert mid.motor == "dc_separate"
    assert mid.torque_rated_nm == pytest.approx(torque)
    assert mid.speed_rated_rpm == pytest.approx(speed, rel=1e-12)
    assert mid.power_mech_rated_w == pytest.approx(torque * omega, rel=1e-12)

    solved = motor_torque_speed(motor="dc_separate", p_rated=4000).cases[0]
    assert solved.power_mech_rated_w == pytest.approx(4000.0, rel=1e-12)
    assert solved.efficiency_rated == pytest.approx(solved.power_mech_rated_w / solved.power_in_rated_w)

    low = motor_torque_speed(motor="dc_separate", v=180).cases[0]
    weak = motor_torque_speed(motor="dc_separate", k_phi=1.2).cases[0]
    assert low.speed_noload_rpm == pytest.approx(case.speed_noload_rpm * 180.0 / 220.0)
    assert low.torque_stall_nm == pytest.approx(270.0)
    assert weak.speed_noload_rpm == pytest.approx(case.speed_noload_rpm * 1.5 / 1.2)
    assert weak.torque_stall_nm == pytest.approx(264.0)

    shunt = motor_torque_speed(motor="dc_shunt", n_points=11).cases[0]
    separate = motor_torque_speed(motor="dc_separate", n_points=11).cases[0]
    assert shunt.k_phi == pytest.approx(1.5)
    assert shunt.i_field_a == pytest.approx(1.0)
    assert shunt.speed_rpm == pytest.approx(separate.speed_rpm)
    assert shunt.torque_nm == pytest.approx(separate.torque_nm)
    assert shunt.i_line_a == pytest.approx(separate.i_phase_a + 1.0)
    assert shunt.power_in_w[0] == pytest.approx(220.0)
    assert shunt.efficiency[0] == pytest.approx(0.0)

    shunt_low = motor_torque_speed(motor="并励", v=180).cases[0]
    assert shunt_low.speed_noload_rpm == pytest.approx(shunt.speed_noload_rpm, rel=1e-12)
    assert shunt_low.torque_stall_nm == pytest.approx(330.0 * (180.0 / 220.0) ** 2, rel=1e-12)


def test_series_hyperbola() -> None:
    case = motor_torque_speed(motor="dc_series", i_min=8, i_max=40, n_points=5).cases[0]
    assert math.isinf(case.speed_noload_rpm)
    assert case.i_stall_a == pytest.approx(220.0 / 0.6)
    assert case.torque_stall_nm == pytest.approx(0.08 * case.i_stall_a**2)
    current = np.sqrt(case.torque_nm / 0.08)
    omega = 220.0 / (0.08 * current) - 0.6 / 0.08
    assert case.i_phase_a == pytest.approx(current)
    assert case.speed_rad_s == pytest.approx(omega, rel=1e-12)
    assert case.torque_nm[0] == pytest.approx(0.08 * 8.0**2)
    assert case.torque_nm[-1] == pytest.approx(0.08 * 40.0**2)
    assert case.speed_rpm[0] > case.speed_rpm[-1]

    rated = motor_torque_speed(motor="series", i_min=8, i_max=40, p_rated=2000).cases[0]
    assert rated.power_mech_rated_w == pytest.approx(2000.0, rel=1e-12)
    assert rated.torque_nm[0] < rated.torque_rated_nm < rated.torque_nm[-1]

    low = motor_torque_speed(motor="dc_series", v=180, i_min=8, i_max=40, t_rated=32).cases[0]
    base = motor_torque_speed(motor="dc_series", i_min=8, i_max=40, t_rated=32).cases[0]
    assert low.speed_rated_rpm < base.speed_rated_rpm
    assert low.torque_rated_nm == pytest.approx(32.0)
    # T = k_f I^2, so I = 20 A and omega = V/(k_f I) - (Ra+Rs)/k_f.
    assert base.i_line_rated_a == pytest.approx(20.0)
    assert base.speed_rated_rpm == pytest.approx((220.0 / 1.6 - 7.5) * 60.0 / (2.0 * math.pi))


def test_csv_comparison_figure_and_summary(tmp_path: Path) -> None:
    png = tmp_path / "curves.png"
    out_csv = tmp_path / "summary.csv"
    result = motor_torque_speed(CSV, output_png=png, output_csv=out_csv, show=False)
    assert result.fig is None
    assert [case.name for case in result.cases] == [
        "im_base",
        "im_high_r2",
        "im_low_v",
        "dc_separate",
        "dc_separate_low_v",
        "dc_separate_weak_field",
        "dc_shunt_low_v",
        "dc_series",
        "dc_series_low_v",
    ]
    assert result.cases[0].torque_breakdown_nm == pytest.approx(result.cases[1].torque_breakdown_nm, rel=1e-12)
    assert result.cases[2].torque_breakdown_nm == pytest.approx(
        0.64 * result.cases[0].torque_breakdown_nm, rel=1e-12
    )
    assert result.cases[0].power_mech_rated_w == pytest.approx(8000.0, rel=1e-8)
    assert result.cases[3].power_mech_rated_w == pytest.approx(4000.0, rel=1e-12)
    assert result.cases[6].speed_noload_rpm == pytest.approx(result.cases[3].speed_noload_rpm)
    assert result.cases[6].torque_stall_nm < result.cases[4].torque_stall_nm
    assert png.is_file() and png.stat().st_size > 1000
    text = out_csv.read_text(encoding="utf-8")
    assert text.startswith("name,motor,connection,v,f,poles,n_sync_rpm,")
    assert "\nim_base,induction,y,380," in text
    assert "\ndc_series,dc_series," in text
    assert "im_base" in result.summary
    assert "T_bd=" in result.summary
    assert "n0=inf" in result.summary

    one = motor_torque_speed(CSV, name="im_low_v")
    assert len(one.cases) == 1
    assert one.cases[0].v == 304.0

    semicolon = tmp_path / "one.csv"
    semicolon.write_text(
        "name;motor;v;r2;p_rated\nlab;induction;380;0.4;8000\n",
        encoding="utf-8",
    )
    parsed = motor_torque_speed(semicolon)
    assert parsed.cases[0].name == "lab"
    assert parsed.cases[0].r2 == pytest.approx(0.4)
    assert parsed.cases[0].power_mech_rated_w == pytest.approx(8000.0, rel=1e-8)


def test_bad_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="induction"):
        motor_torque_speed(motor="svm")
    with pytest.raises(ValueError, match="even"):
        motor_torque_speed(poles=3)
    with pytest.raises(ValueError, match="poles"):
        motor_torque_speed(poles=4.5)
    with pytest.raises(ValueError, match="r2"):
        motor_torque_speed(r2=0)
    with pytest.raises(ValueError, match="xm"):
        motor_torque_speed(xm=-1)
    with pytest.raises(ValueError, match="connection"):
        motor_torque_speed(connection="mesh")
    with pytest.raises(ValueError, match="s_max"):
        motor_torque_speed(s_min=0.2, s_max=0.1)
    with pytest.raises(ValueError, match="s_min and s_max"):
        motor_torque_speed(s_max=4)
    with pytest.raises(ValueError, match="n_points"):
        motor_torque_speed(n_points=0)
    with pytest.raises(ValueError, match="n_points=1"):
        motor_torque_speed(n_points=1, s_min=0.0, s_max=1.0)
    with pytest.raises(ValueError, match="does not apply"):
        motor_torque_speed(t_rated=10)
    with pytest.raises(ValueError, match="does not apply"):
        motor_torque_speed(motor="dc_separate", s_rated=0.05)
    with pytest.raises(ValueError, match="does not apply"):
        motor_torque_speed(motor="dc_shunt", k_phi=1.2)
    with pytest.raises(ValueError, match="stall current"):
        motor_torque_speed(motor="dc_series", i_min=10, i_max=500)
    with pytest.raises(ValueError, match="stall torque"):
        motor_torque_speed(motor="dc_separate", t_rated=400)
    with pytest.raises(ValueError, match="maximum developed power"):
        motor_torque_speed(motor="dc_separate", p_rated=1_000_000)
    with pytest.raises(ValueError, match="show"):
        motor_torque_speed(show="yes")
    with pytest.raises(ValueError, match="was not found"):
        motor_torque_speed(CSV, name="missing")
    with pytest.raises(ValueError, match="more than once"):
        duplicate = tmp_path / "dup.csv"
        duplicate.write_text("name,motor\nsame,induction\nsame,induction\n", encoding="utf-8")
        motor_torque_speed(duplicate, name="same")
    with pytest.raises(ValueError, match="once"):
        motor_torque_speed(CSV, csv_path=CSV)
    with pytest.raises(ValueError, match="parameter name"):
        motor_torque_speed("motor")
    with pytest.raises(ValueError, match="by name"):
        motor_torque_speed(1)
    with pytest.raises(FileNotFoundError):
        motor_torque_speed(tmp_path / "missing.csv")
    with pytest.raises(ValueError, match="k_phi"):
        motor_torque_speed(motor="dc_separate", k_phi=0)


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "motor-torque-speed:" in completed.stdout
    assert "name=im_base motor=induction" in completed.stdout
    assert "name=im_high_r2 motor=induction" in completed.stdout
    assert "T_bd=123.6772" in completed.stdout
    assert "s_bd=0.133882" in completed.stdout
    assert "s_bd=0.401647" in completed.stdout
    assert "name=dc_separate motor=dc_separate" in completed.stdout
    assert "T_stall=330.0000" in completed.stdout
    assert "name=dc_shunt_low_v motor=dc_shunt" in completed.stdout
    assert "name=dc_series motor=dc_series" in completed.stdout
    assert "n0=inf" in completed.stdout
    assert "T_stall=10755.5556" in completed.stdout
    png = TOOL / "examples" / "output" / "motor_torque_speed_demo.png"
    out_csv = TOOL / "examples" / "output" / "motor_torque_speed_demo.csv"
    assert png.is_file() and png.stat().st_size > 1000
    assert "torque_breakdown_nm" in out_csv.read_text(encoding="utf-8")
