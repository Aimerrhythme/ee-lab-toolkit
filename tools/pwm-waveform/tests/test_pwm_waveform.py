"""Smoke tests for the pwm-waveform Python tool."""

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

from pwm_waveform import format_table, pwm_waveform

CSV = TOOL / "examples" / "data" / "pwm_cases.csv"


def _order(result, order: int):
    hits = [row for row in result.harmonics if row.order == order]
    assert len(hits) == 1
    return hits[0]


def test_default_bipolar_matches_the_linear_fundamental() -> None:
    result = pwm_waveform()

    assert result.name == ""
    assert result.mode == "bipolar"
    assert result.f_m == 50.0
    assert result.f_c == 1050.0
    assert result.m_f == 21.0
    assert result.m_a == 0.8
    assert result.v_dc == 100.0
    assert result.cycles == 2
    assert result.samples_per_carrier == 200
    assert result.n_samples == 8400
    assert result.n_carrier == 42
    assert result.fs == pytest.approx(210_000.0)
    assert result.linear_range is True
    assert result.dc == pytest.approx(0.0, abs=1e-12)
    assert result.fundamental_analytic == pytest.approx(80.0)
    assert result.fundamental_amplitude == pytest.approx(80.0, rel=0.002)
    assert result.fundamental_amplitude == pytest.approx(79.9658, abs=1e-3)
    assert result.fundamental_error_percent == pytest.approx(-0.0428, abs=0.02)
    assert result.fundamental_phase_deg == pytest.approx(0.0, abs=1.0)
    assert result.fundamental_rms == pytest.approx(result.fundamental_amplitude / math.sqrt(2.0))
    assert result.signal_rms == pytest.approx(100.0)
    assert result.thd_percent == pytest.approx(145.8655, abs=0.05)
    assert result.n_pulses_a == 42
    assert result.n_pulses_b == 42
    assert np.array_equal(result.gate_b, 1.0 - result.gate_a)
    assert set(np.unique(np.round(result.v_out, 8))) == {-100.0, 100.0}
    assert result.carrier[0] == pytest.approx(-1.0)
    assert result.carrier[100] == pytest.approx(1.0)
    assert result.modulation[0] == pytest.approx(0.0, abs=1e-12)

    carrier_group = _order(result, 21)
    assert carrier_group.frequency_hz == pytest.approx(1050.0)
    assert carrier_group.percent == pytest.approx(102.32, abs=0.2)
    assert carrier_group.above_floor is True
    assert _order(result, 19).percent == pytest.approx(27.38, abs=0.2)
    assert _order(result, 23).percent == pytest.approx(27.17, abs=0.2)
    even = _order(result, 2)
    assert even.amplitude == pytest.approx(0.0, abs=1e-6)
    assert even.phase_rad == 0.0
    assert even.above_floor is False
    assert _order(result, 3).above_floor is False
    assert "THD=145.8655%" in format_table(result)
    assert "mode=bipolar" in format_table(result)
    assert "linear=1" in format_table(result)

    repeated = result.n_samples // result.cycles
    assert np.allclose(result.v_out[:repeated], result.v_out[repeated:])


def test_unipolar_removes_the_carrier_and_lowers_thd() -> None:
    bipolar = pwm_waveform(mode="bipolar")
    result = pwm_waveform(mode="unipolar")

    assert result.mode == "unipolar"
    assert result.linear_range is True
    assert result.fundamental_amplitude == pytest.approx(80.0, rel=0.002)
    assert result.fundamental_phase_deg == pytest.approx(0.0, abs=1e-6)
    assert result.thd_percent == pytest.approx(77.15, abs=0.1)
    assert result.thd < bipolar.thd
    assert result.signal_rms < bipolar.signal_rms
    assert set(np.unique(np.round(result.v_out, 8))) == {-100.0, 0.0, 100.0}
    assert _order(result, 21).percent < 1.0
    assert _order(result, 21).above_floor is False
    assert _order(result, 41).percent == pytest.approx(39.34, abs=0.3)
    assert _order(result, 41).above_floor is True
    assert _order(result, 2).amplitude == pytest.approx(0.0, abs=1e-6)
    assert result.n_pulses_a == 42
    assert result.n_pulses_b == 42
    assert not np.array_equal(result.gate_a, result.gate_b)


def test_phase_shift_overmodulation_and_zero_reference() -> None:
    shifted = pwm_waveform(mode="bipolar", phase_deg=90)
    assert shifted.fundamental_phase_deg == pytest.approx(90.0, abs=0.5)
    assert shifted.fundamental_amplitude == pytest.approx(80.0, rel=0.005)

    over = pwm_waveform(mode="bipolar", m_a=1.2, n_harmonics=25)
    assert over.linear_range is False
    assert over.fundamental_analytic == pytest.approx(120.0)
    assert over.fundamental_amplitude == pytest.approx(110.39, abs=0.1)
    assert 100.0 < over.fundamental_amplitude < 4.0 * 100.0 / math.pi
    assert over.n_pulses_a == 26
    assert over.n_pulses_a < over.n_carrier
    assert "overmodulation" not in format_table(over)
    assert "linear=0" in format_table(over)

    silent = pwm_waveform(mode="bipolar", m_a=0, samples_per_carrier=40, n_harmonics=5)
    assert silent.fundamental_amplitude == pytest.approx(0.0, abs=1e-8)
    assert math.isnan(silent.thd)
    assert math.isnan(silent.thd_percent)
    assert math.isnan(silent.fundamental_error_percent)
    assert "THD=undefined" in format_table(silent)
    assert set(np.unique(np.round(silent.v_out, 8))) == {-100.0, 100.0}

    idle = pwm_waveform(mode="单极性", m_a=0, samples_per_carrier=40, cycles=1, m_f=9)
    assert idle.mode == "unipolar"
    assert np.all(idle.v_out == 0.0)
    assert math.isnan(idle.thd)


def test_carrier_formula_frequency_ratio_and_csv(tmp_path: Path) -> None:
    small = pwm_waveform(cycles=1, samples_per_carrier=20, m_f=3, n_harmonics=5, v_dc=10)
    phase = (np.arange(20) % 20) / 20.0
    expected = 1.0 - 4.0 * np.abs(phase - 0.5)
    assert small.carrier[:20] == pytest.approx(expected)
    assert small.n_carrier == 3
    assert small.fs == pytest.approx(20 * 3 * 50.0)

    from_fc = pwm_waveform(f_c=1050, m_f=None)
    assert from_fc.m_f == 21.0
    assert from_fc.f_c == 1050.0
    both = pwm_waveform(f_m=50, f_c=1050, m_f=21)
    assert both.fundamental_amplitude == pytest.approx(from_fc.fundamental_amplitude)

    half = pwm_waveform(m_f=21.5, cycles=2, samples_per_carrier=40, n_harmonics=8, mode="uni")
    assert half.mode == "unipolar"
    assert half.n_carrier == 43
    assert half.m_f == pytest.approx(21.5)

    png = tmp_path / "pwm.png"
    out_csv = tmp_path / "harmonics.csv"
    from_csv = pwm_waveform(CSV, name="bipolar_ma08", output_png=png, output_csv=out_csv, show=False)
    direct = pwm_waveform()
    assert from_csv.name == "bipolar_ma08"
    assert from_csv.fundamental_amplitude == pytest.approx(direct.fundamental_amplitude, abs=1e-12)
    assert from_csv.thd == pytest.approx(direct.thd, abs=1e-12)
    assert from_csv.fig is None
    assert png.is_file() and png.stat().st_size > 1000
    text = out_csv.read_text(encoding="utf-8")
    assert text.startswith(
        "order,frequency_hz,amplitude,rms,percent,phase_rad,phase_deg,above_floor"
    )
    assert "\n21," in text

    single = tmp_path / "one.csv"
    single.write_text(
        "name;mode;f_m;m_f;m_a;v_dc;cycles;samples_per_carrier\n"
        "lab;bipolar;50;15;0.8;200;1;80\n",
        encoding="utf-8",
    )
    parsed = pwm_waveform(single)
    assert parsed.name == "lab"
    assert parsed.m_f == 15.0
    assert parsed.v_dc == 200.0
    assert parsed.n_samples == 80 * 15
    assert parsed.fundamental_amplitude == pytest.approx(160.0, rel=0.01)


def test_bad_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bipolar"):
        pwm_waveform(mode="svm")
    with pytest.raises(ValueError, match="m_a"):
        pwm_waveform(m_a=-0.2)
    with pytest.raises(ValueError, match="m_a"):
        pwm_waveform(m_a=11)
    with pytest.raises(ValueError, match="v_dc"):
        pwm_waveform(v_dc=0)
    with pytest.raises(ValueError, match="cycles"):
        pwm_waveform(cycles=0)
    with pytest.raises(ValueError, match="samples_per_carrier"):
        pwm_waveform(samples_per_carrier=4)
    with pytest.raises(ValueError, match="m_f must be >= 1"):
        pwm_waveform(m_f=0.5, cycles=2)
    with pytest.raises(ValueError, match="integer number of carrier"):
        pwm_waveform(m_f=21.5, cycles=1)
    with pytest.raises(ValueError, match="does not match"):
        pwm_waveform(f_c=1000, m_f=21)
    with pytest.raises(ValueError, match="n_harmonics"):
        pwm_waveform(n_harmonics=0)
    with pytest.raises(ValueError, match="amp_floor_ratio"):
        pwm_waveform(amp_floor_ratio=-0.1)
    with pytest.raises(ValueError, match="show"):
        pwm_waveform(show="yes")
    with pytest.raises(ValueError, match="multiple rows"):
        pwm_waveform(CSV)
    with pytest.raises(ValueError, match="was not found"):
        pwm_waveform(CSV, name="missing")
    with pytest.raises(ValueError, match="once"):
        pwm_waveform(CSV, csv_path=CSV, name="bipolar_ma08")
    with pytest.raises(ValueError, match="parameter name"):
        pwm_waveform("m_a")
    with pytest.raises(ValueError, match="by name"):
        pwm_waveform(1)
    with pytest.raises(FileNotFoundError):
        pwm_waveform(tmp_path / "missing.csv")
    with pytest.raises(ValueError, match="too long"):
        pwm_waveform(m_f=500, cycles=50, samples_per_carrier=200)


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "pwm-waveform:" in completed.stdout
    assert "name=bipolar_ma08" in completed.stdout
    assert "name=unipolar_ma08" in completed.stdout
    assert "mode=bipolar" in completed.stdout
    assert "mode=unipolar" in completed.stdout
    assert "THD=145.8655%" in completed.stdout
    assert "THD=77.1481%" in completed.stdout
    assert "V1_analytic=80" in completed.stdout
    for name in ("bipolar_ma08", "unipolar_ma08"):
        png = TOOL / "examples" / "output" / f"pwm_waveform_demo_{name}.png"
        out_csv = TOOL / "examples" / "output" / f"pwm_waveform_demo_{name}.csv"
        assert png.is_file()
        assert png.stat().st_size > 1000
        assert "frequency_hz" in out_csv.read_text(encoding="utf-8")
