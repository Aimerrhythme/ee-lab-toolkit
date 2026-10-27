"""Smoke tests for the fft-thd Python tool."""

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

from fft_thd import fft_thd, format_table

CSV = TOOL / "examples" / "data" / "synthetic_waveform.csv"
FS = 5000.0
F0 = 50.0
AMPS = {1: 100.0, 3: 8.0, 5: 5.0, 7: 2.0}
PHASES = {1: 0.0, 3: -math.pi / 6, 5: math.pi / 5, 7: math.pi / 2}
THD = math.sqrt(8.0**2 + 5.0**2 + 2.0**2) / 100.0


def synthesize(
    n: int,
    *,
    fs: float = FS,
    f0: float = F0,
    dc: float = 0.0,
    extra: dict[int, tuple[float, float]] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    time = np.arange(n, dtype=float) / fs
    values = np.full(n, dc, dtype=float)
    parts = dict(AMPS)
    phases = dict(PHASES)
    if extra:
        for order, (amplitude, phase) in extra.items():
            parts[order] = amplitude
            phases[order] = phase
    for order, amplitude in parts.items():
        values += amplitude * np.sin(2.0 * math.pi * order * f0 * time + phases[order])
    return time, values


def _by_order(result, order: int):
    hits = [row for row in result.harmonics if row.order == order]
    assert len(hits) == 1
    return hits[0]


def test_integer_cycles_match_analytic_thd_phase_and_rect_spectrum() -> None:
    time, values = synthesize(1000, dc=5.0)
    result = fft_thd(time, values, f0=50, n_harmonics=7, window="auto")

    assert result.f0_source == "given"
    assert result.fs == pytest.approx(FS)
    assert result.n_samples == 1000
    assert result.cycles == pytest.approx(10.0)
    assert result.window == "rect"
    assert result.dc == pytest.approx(5.0, abs=1e-8)
    assert result.fundamental_amplitude == pytest.approx(100.0, abs=1e-8)
    assert result.fundamental_rms == pytest.approx(100.0 / math.sqrt(2.0), abs=1e-8)
    assert result.thd == pytest.approx(THD, abs=1e-8)
    assert result.thd_percent == pytest.approx(100.0 * THD, abs=1e-6)
    assert result.signal_rms == pytest.approx(
        math.sqrt(sum(amplitude**2 for amplitude in AMPS.values()) / 2.0),
        rel=1e-8,
    )
    assert "THD=" in format_table(result)
    assert "9.6437%" in format_table(result)

    for order, amplitude in AMPS.items():
        row = _by_order(result, order)
        assert row.frequency_hz == pytest.approx(order * F0)
        assert row.amplitude == pytest.approx(amplitude, abs=1e-8)
        assert row.rms == pytest.approx(amplitude / math.sqrt(2.0), abs=1e-8)
        assert row.percent == pytest.approx(amplitude, abs=1e-6)
        assert row.phase_rad == pytest.approx(PHASES[order], abs=1e-8)
        assert row.in_thd is (order > 1)
    even = _by_order(result, 2)
    assert even.amplitude == pytest.approx(0.0, abs=1e-8)
    assert even.phase_rad == 0.0

    spectrum = result.spectrum_amplitude
    frequency = result.spectrum_frequency
    assert frequency.shape == spectrum.shape
    assert len(frequency) == 501
    assert spectrum[0] == pytest.approx(0.0, abs=1e-8)
    bin_50 = int(np.argmin(np.abs(frequency - 50.0)))
    assert frequency[bin_50] == pytest.approx(50.0)
    assert spectrum[bin_50] == pytest.approx(100.0, abs=1e-6)
    assert spectrum[bin_50 - 1] == pytest.approx(0.0, abs=1e-6)
    assert spectrum[bin_50 + 1] == pytest.approx(0.0, abs=1e-6)

    kept_dc = fft_thd(values, fs=FS, f0=50, n_harmonics=1, remove_dc=False, window="rect")
    assert kept_dc.spectrum_amplitude[0] == pytest.approx(5.0, abs=1e-6)
    assert kept_dc.thd == pytest.approx(0.0, abs=1e-10)
    assert kept_dc.harmonics[0].in_thd is False


def test_hann_on_bin_peak_keeps_amplitude_and_splits_shoulders() -> None:
    _, values = synthesize(1000)
    result = fft_thd(values, fs=FS, f0=50, n_harmonics=7, window="hann", remove_dc=True)
    frequency = result.spectrum_frequency
    spectrum = result.spectrum_amplitude
    bin_50 = int(np.argmin(np.abs(frequency - 50.0)))
    assert result.window == "hann"
    assert spectrum[bin_50] == pytest.approx(100.0, abs=1e-6)
    assert spectrum[bin_50 - 1] == pytest.approx(50.0, abs=1e-6)
    assert spectrum[bin_50 + 1] == pytest.approx(50.0, abs=1e-6)
    assert result.thd == pytest.approx(THD, abs=1e-8)
    assert _by_order(result, 3).amplitude == pytest.approx(8.0, abs=1e-8)


def test_non_integer_cycles_with_known_f0_match_analytic_thd() -> None:
    _, values = synthesize(1037, dc=5.0)
    result = fft_thd(values, fs=FS, f0=50, n_harmonics=15, window="auto")
    assert result.window == "hann"
    assert result.cycles == pytest.approx(1037 * 50.0 / FS)
    assert abs(result.cycles - round(result.cycles)) > 0.02
    assert result.dc == pytest.approx(5.0, abs=1e-6)
    assert result.fundamental_amplitude == pytest.approx(100.0, abs=1e-6)
    assert result.thd == pytest.approx(THD, abs=1e-8)
    assert _by_order(result, 5).phase_rad == pytest.approx(PHASES[5], abs=1e-6)
    assert _by_order(result, 7).amplitude == pytest.approx(2.0, abs=1e-6)


def test_detected_fundamental_recovers_thd_off_bin() -> None:
    _, coherent = synthesize(1000)
    on_bin = fft_thd(coherent, fs=FS, n_harmonics=7)
    assert on_bin.f0_source == "detected"
    assert on_bin.f0 == pytest.approx(50.0, abs=1e-9)
    assert on_bin.window == "rect"
    assert on_bin.thd == pytest.approx(THD, abs=1e-8)

    _, skewed = synthesize(1037)
    found = fft_thd(skewed, fs=FS, n_harmonics=7, f_search_min=10, f_search_max=100)
    assert found.f0_source == "detected"
    assert found.f0 == pytest.approx(50.0, abs=1e-3)
    assert found.thd == pytest.approx(THD, abs=1e-4)
    assert found.window == "hann"


def test_floor_drops_a_small_harmonic_from_the_thd_sum() -> None:
    _, values = synthesize(1000, extra={9: (0.1, 0.2)})
    excluded = fft_thd(values, fs=FS, f0=50, n_harmonics=9, amp_floor_ratio=0.002)
    included = fft_thd(values, fs=FS, f0=50, n_harmonics=9, amp_floor_ratio=0.0)
    assert _by_order(excluded, 9).in_thd is False
    assert _by_order(excluded, 9).percent == pytest.approx(0.1, abs=1e-6)
    assert excluded.thd == pytest.approx(THD, abs=1e-8)
    assert _by_order(included, 9).in_thd is True
    assert included.thd == pytest.approx(math.sqrt(93.01) / 100.0, abs=1e-8)


def test_demo_csv_is_close_to_the_analytic_waveform(tmp_path: Path) -> None:
    png = tmp_path / "fft.png"
    out_csv = tmp_path / "harmonics.csv"
    result = fft_thd(
        CSV,
        f0=50,
        n_harmonics=7,
        window="auto",
        amp_floor_ratio=0.002,
        output_png=png,
        output_csv=out_csv,
        show=False,
    )
    assert result.n_samples == 1000
    assert result.fs == pytest.approx(FS, rel=1e-6)
    assert result.window == "rect"
    assert result.dc == pytest.approx(5.0, abs=0.05)
    assert result.fundamental_amplitude == pytest.approx(100.0, abs=0.1)
    assert _by_order(result, 3).amplitude == pytest.approx(8.0, abs=0.1)
    assert _by_order(result, 5).amplitude == pytest.approx(5.0, abs=0.1)
    assert _by_order(result, 7).amplitude == pytest.approx(2.0, abs=0.1)
    assert _by_order(result, 2).in_thd is False
    assert result.thd == pytest.approx(THD, abs=5e-4)
    assert result.fig is None
    assert png.is_file()
    assert png.stat().st_size > 1000
    text = out_csv.read_text(encoding="utf-8")
    assert text.startswith("order,frequency_hz,amplitude,rms,percent,phase_rad,phase_deg,in_thd")
    assert "\n3," in text


def test_bad_inputs_and_semicolon_csv(tmp_path: Path) -> None:
    _, values = synthesize(1000)
    with pytest.raises(ValueError, match="at least 16"):
        fft_thd(values[:8], fs=FS, f0=50)
    with pytest.raises(ValueError, match="fundamental amplitude is zero"):
        fft_thd(np.full(200, 3.0), fs=FS, f0=50, n_harmonics=5)
    with pytest.raises(ValueError, match="window"):
        fft_thd(values, fs=FS, f0=50, window="kaiser")
    with pytest.raises(ValueError, match="n_harmonics"):
        fft_thd(values, fs=FS, f0=50, n_harmonics=0)
    with pytest.raises(ValueError, match="Nyquist"):
        fft_thd(values, fs=FS, f0=3000)
    with pytest.raises(ValueError, match="fs is required"):
        fft_thd(values)
    with pytest.raises(ValueError, match="not both"):
        fft_thd(CSV, values)
    with pytest.raises(FileNotFoundError):
        fft_thd(tmp_path / "missing.csv")
    with pytest.raises(ValueError, match="not uniform"):
        time = np.arange(1000, dtype=float) / FS
        time[500:] += 0.01
        fft_thd(time, values, f0=50)
    with pytest.raises(ValueError, match="does not match"):
        time, _ = synthesize(1000)
        fft_thd(time, values, fs=1000, f0=50)

    semicolon = tmp_path / "wave.csv"
    _, column = synthesize(64)
    lines = ["t;v"]
    lines.extend(f"{index / FS:.8f};{sample:.8f}" for index, sample in enumerate(column))
    semicolon.write_text("\n".join(lines) + "\n", encoding="utf-8")
    parsed = fft_thd(semicolon, f0=50, n_harmonics=7)
    assert parsed.thd == pytest.approx(THD, abs=1e-6)
    assert parsed.fs == pytest.approx(FS, rel=1e-6)

    signal_only = tmp_path / "samples.csv"
    signal_only.write_text(
        "voltage\n" + "\n".join(f"{sample:.8f}" for sample in column) + "\n",
        encoding="utf-8",
    )
    from_fs = fft_thd(signal_only, fs=FS, f0=50, n_harmonics=7, window="rect")
    assert from_fs.fundamental_amplitude == pytest.approx(100.0, abs=1e-5)


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "fft-thd:" in completed.stdout
    assert "THD=" in completed.stdout
    assert "window=rect" in completed.stdout
    assert "9.6437%" in completed.stdout
    png = TOOL / "examples" / "output" / "fft_thd_demo.png"
    out_csv = TOOL / "examples" / "output" / "fft_thd_demo.csv"
    assert png.is_file()
    assert png.stat().st_size > 1000
    assert "frequency_hz" in out_csv.read_text(encoding="utf-8")
