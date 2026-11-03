"""Smoke tests for the bode-demo Python tool."""

from __future__ import annotations

import cmath
import math
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from bode_demo import bode_demo, format_margins_table

CSV = TOOL / "examples" / "data" / "systems.csv"
FIRST = {"form": "first_order", "k": 1.0, "tau": 1.0, "name": "lag"}


def _wrap180(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def test_first_order_corner_is_minus_3db_and_minus_45deg() -> None:
    frequency = np.array([0.1, 1.0, 10.0])
    result = bode_demo([1.0], [1.0, 1.0], frequency_rad_s=frequency, show=False)
    mag = result.magnitude_db[:, 0]
    phase = result.phase_deg[:, 0]
    for index, w_value in enumerate(frequency):
        expected_mag = 20.0 * math.log10(1.0 / math.sqrt(1.0 + w_value**2))
        expected_phase = -math.degrees(math.atan(w_value))
        assert mag[index] == pytest.approx(expected_mag, abs=1e-8)
        assert phase[index] == pytest.approx(expected_phase, abs=1e-8)
    assert mag[1] == pytest.approx(-10.0 * math.log10(2.0), abs=1e-8)
    assert phase[1] == pytest.approx(-45.0, abs=1e-8)
    assert result.margins[0].phase_margin_deg == pytest.approx(math.inf)
    assert result.margins[0].gain_margin_db == pytest.approx(math.inf)

    fast = bode_demo(form="first_order", k=1.0, tau=0.2, frequency_rad_s=[5.0], show=False)
    assert fast.magnitude_db[0, 0] == pytest.approx(-10.0 * math.log10(2.0), abs=1e-8)
    assert fast.phase_deg[0, 0] == pytest.approx(-45.0, abs=1e-8)
    assert fast.margins[0].den == pytest.approx([0.2, 1.0])


def test_second_order_half_damping_has_90_degree_phase_margin() -> None:
    result = bode_demo(w_min=0.05, w_max=20.0, n_points=200, show=False)
    row = result.margins[0]
    assert result.names == ["zeta=0.5"]
    assert row.form == "second_order"
    assert row.num == pytest.approx([1.0])
    assert row.den == pytest.approx([1.0, 1.0, 1.0])
    assert row.phase_margin_rad_s == pytest.approx(1.0, abs=1e-8)
    assert row.phase_margin_deg == pytest.approx(90.0, abs=1e-6)
    assert row.gain_margin_db == pytest.approx(math.inf)
    assert row.gain_crossover_rad_s == pytest.approx([1.0], abs=1e-8)
    assert row.phase_crossover_rad_s == []

    zeta = 0.2
    wn = 1.0
    w_peak = wn * math.sqrt(1.0 - 2.0 * zeta * zeta)
    mr_db = 20.0 * math.log10(1.0 / (2.0 * zeta * math.sqrt(1.0 - zeta * zeta)))
    frequency = np.array([0.2, w_peak, wn])
    peak = bode_demo(form="second_order", zeta=zeta, wn=wn, frequency_rad_s=frequency, show=False)
    assert peak.frequency_rad_s.tolist() == pytest.approx(sorted(frequency))
    by_w = {float(w_value): index for index, w_value in enumerate(peak.frequency_rad_s)}
    assert peak.magnitude_db[by_w[w_peak], 0] == pytest.approx(mr_db, abs=1e-8)
    assert peak.phase_deg[by_w[wn], 0] == pytest.approx(-90.0, abs=1e-8)
    assert peak.magnitude_db[by_w[w_peak], 0] > peak.magnitude_db[by_w[0.2], 0]


def test_textbook_margins_match_the_cubic_and_a_coarse_grid() -> None:
    # L(s) = 1 / (s (s+1)^2). den(jw) = -2 w^2 + j w (1-w^2).
    # Phase crosses -180 deg at w = 1, where |L| = 1/2.
    # |L| = 1 when u = w^2 satisfies u^3 + 2 u^2 + u - 1 = 0.
    roots = [complex(value) for value in np.roots([1.0, 2.0, 1.0, -1.0])]
    positive = [value.real for value in roots if abs(value.imag) < 1e-10 and value.real > 0]
    assert len(positive) == 1
    w_gc = math.sqrt(positive[0])
    response = 1.0 / (1j * w_gc * (1j * w_gc + 1.0) ** 2)
    expected_pm = _wrap180(math.degrees(cmath.phase(response)) + 180.0)
    expected_gm = -20.0 * math.log10(0.5)

    fine = bode_demo([1.0], [1.0, 2.0, 1.0, 0.0], w_min=0.05, w_max=20.0, n_points=400, show=False)
    coarse = bode_demo([1.0], [1.0, 2.0, 1.0, 0.0], w_min=0.05, w_max=20.0, n_points=30, show=False)
    for result in (fine, coarse):
        row = result.margins[0]
        assert row.den == pytest.approx([1.0, 2.0, 1.0, 0.0])
        assert row.gain_margin_rad_s == pytest.approx(1.0, abs=1e-8)
        assert row.gain_margin_db == pytest.approx(expected_gm, abs=1e-6)
        assert row.phase_margin_rad_s == pytest.approx(w_gc, abs=1e-8)
        assert row.phase_margin_deg == pytest.approx(expected_pm, abs=1e-6)
        assert row.phase_margin_deg > 0.0
    assert "GM_dB" in format_margins_table(fine.margins)
    assert "textbook" not in format_margins_table(fine.margins)


def test_pid_loop_coefficients_and_p_only_margin() -> None:
    proportional = bode_demo(
        form="pid_loop",
        k=1.0,
        wn=1.0,
        zeta=1.0,
        kp=2.0,
        ki=0.0,
        kd=0.0,
        w_min=0.05,
        w_max=20.0,
        show=False,
    )
    row = proportional.margins[0]
    assert proportional.names == ["P"]
    assert row.num == pytest.approx([2.0])
    assert row.den == pytest.approx([1.0, 2.0, 1.0])
    assert row.phase_margin_rad_s == pytest.approx(1.0, abs=1e-8)
    assert row.phase_margin_deg == pytest.approx(90.0, abs=1e-6)
    assert row.gain_margin_db == pytest.approx(math.inf)

    loop = bode_demo(
        form="pid_loop",
        k=1.0,
        wn=1.0,
        zeta=1.0,
        kp=2.0,
        ki=1.5,
        kd=0.8,
        kd_n=10.0,
        name="PID",
        show=False,
    )
    pid = loop.margins[0]
    assert pid.num == pytest.approx([10.0, 21.5, 15.0])
    assert pid.den == pytest.approx(np.convolve([1.0, 10.0, 0.0], [1.0, 2.0, 1.0]))
    # Relative degree 2: phase approaches -180 deg and the gain margin stays infinite.
    assert math.isfinite(pid.phase_margin_deg)
    assert pid.phase_margin_deg > 0.0
    assert pid.gain_margin_db == pytest.approx(math.inf)
    assert pid.phase_margin_rad_s > 0.0
    w_gc = pid.phase_margin_rad_s
    response = np.polyval(pid.num, 1j * w_gc) / np.polyval(pid.den, 1j * w_gc)
    assert abs(response) == pytest.approx(1.0, abs=1e-8)
    assert pid.phase_margin_deg == pytest.approx(_wrap180(math.degrees(cmath.phase(response)) + 180.0), abs=1e-6)


def test_integrator_crossover_and_constant_gain() -> None:
    integrator = bode_demo([0.001], [1.0, 0.0], show=False)
    row = integrator.margins[0]
    assert row.phase_margin_rad_s == pytest.approx(0.001, rel=1e-6)
    assert row.phase_margin_deg == pytest.approx(90.0, abs=1e-6)
    assert integrator.frequency_rad_s[0] < 0.001

    flat = bode_demo([2.0], [1.0], frequency_rad_s=[0.1, 1.0, 10.0], show=False)
    assert flat.magnitude_db[:, 0] == pytest.approx(20.0 * math.log10(2.0), abs=1e-8)
    assert flat.phase_deg[:, 0] == pytest.approx(0.0, abs=1e-8)
    assert math.isnan(flat.margins[0].phase_margin_deg)
    assert flat.margins[0].gain_margin_db == pytest.approx(math.inf)

    negative = bode_demo([-1.0], [1.0, 1.0], frequency_rad_s=[1.0], show=False)
    assert negative.magnitude_db[0, 0] == pytest.approx(-10.0 * math.log10(2.0), abs=1e-8)
    assert negative.phase_deg[0, 0] == pytest.approx(135.0, abs=1e-8)


def test_csv_overlay_png_and_grid(tmp_path: Path) -> None:
    png = tmp_path / "nested" / "bode.png"
    result = bode_demo(
        CSV,
        names=["tau=1", "zeta=0.5", "P", "textbook"],
        output_png=png,
        show=False,
    )
    assert result.names == ["tau=1", "zeta=0.5", "P", "textbook"]
    assert result.magnitude_db.shape == (result.frequency_rad_s.size, 4)
    assert result.phase_deg.shape == result.magnitude_db.shape
    assert result.n_points == result.frequency_rad_s.size
    ratio = result.frequency_rad_s[1:] / result.frequency_rad_s[:-1]
    assert np.allclose(ratio, ratio[0])
    assert png.is_file()
    assert png.stat().st_size > 1000
    assert result.fig is None
    assert result.output_png == str(png)

    stripped = bode_demo([0.0, 0.0, 1.0], [0.0, 1.0, 1.0], frequency_rad_s=[1.0], show=False)
    assert stripped.margins[0].num == pytest.approx([1.0])
    assert stripped.margins[0].den == pytest.approx([1.0, 1.0])


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "first-order" in completed.stdout
    assert "damping sweep" in completed.stdout
    assert "PID/plant open loop" in completed.stdout
    assert "textbook margins" in completed.stdout
    assert "PM_deg" in completed.stdout
    assert "6.0206" in completed.stdout
    for name in (
        "bode_demo_first_order.png",
        "bode_demo_damping.png",
        "bode_demo_pid_loop.png",
        "bode_demo_textbook.png",
    ):
        png = TOOL / "examples" / "output" / name
        assert png.is_file()
        assert png.stat().st_size > 1000


def test_bad_options(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="imaginary axis"):
        bode_demo([1.0], [1.0, 0.0, 1.0], show=False)
    with pytest.raises(ValueError, match="tau"):
        bode_demo(form="first_order", tau=-0.2, show=False)
    with pytest.raises(ValueError, match="order"):
        bode_demo([1.0], [1.0] * 10, show=False)
    with pytest.raises(ValueError, match="w_max"):
        bode_demo([1.0], [1.0, 1.0], w_min=10.0, w_max=1.0, show=False)
    with pytest.raises(ValueError, match="frequency_rad_s"):
        bode_demo([1.0], [1.0, 1.0], frequency_rad_s=[1.0, -2.0], show=False)
    with pytest.raises(ValueError, match="not both"):
        bode_demo([1.0], [1.0, 1.0], frequency_rad_s=[1.0, 2.0], w_min=0.1, show=False)
    with pytest.raises(ValueError, match="duplicate"):
        bode_demo(
            [{"name": "A", "form": "first_order"}, {"name": "A", "form": "second_order"}],
            show=False,
        )
    with pytest.raises(ValueError, match="unknown system"):
        bode_demo(CSV, names=["missing"], show=False)
    with pytest.raises(FileNotFoundError):
        bode_demo(tmp_path / "missing.csv", show=False)
    with pytest.raises(ValueError, match="form"):
        bode_demo(form="state-space", show=False)
