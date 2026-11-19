"""Smoke tests for bearing-envelope-spectrum."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))
sys.path.insert(0, str(TOOL / "examples"))

from make_data import synthetic_signal, write_csv
from bearing_envelope_spectrum import (bandpass_fft, bearing_envelope_spectrum,
                                       bearing_fault_freqs, hilbert_envelope)


def test_fault_freqs_6205():
    f = bearing_fault_freqs(1797.0, 9, 7.94, 39.04)
    assert f["bpfo"] == pytest.approx(107.4, abs=0.2)
    assert f["bpfi"] == pytest.approx(162.2, abs=0.2)


def test_hilbert_envelope_of_am_signal():
    fs = 8000.0
    t = np.arange(8000) / fs
    x = (1 + 0.5 * np.cos(2 * np.pi * 20 * t)) * np.sin(2 * np.pi * 1000 * t)
    env = hilbert_envelope(x)
    assert env[500:-500].max() == pytest.approx(1.5, abs=0.02)
    assert env[500:-500].min() == pytest.approx(0.5, abs=0.02)


def test_bandpass_removes_out_of_band():
    fs = 1000.0
    t = np.arange(1000) / fs
    y = bandpass_fft(np.sin(2 * np.pi * 50 * t) + np.sin(2 * np.pi * 200 * t), fs, 150, 250)
    assert np.std(y) == pytest.approx(np.sqrt(0.5), abs=0.01)


def test_outer_fault_peak_dominates(tmp_path):
    t, x = synthetic_signal()
    p = tmp_path / "s.csv"
    write_csv(p, t, x)
    res = bearing_envelope_spectrum(p, output_csv=tmp_path / "f.csv", output_png=tmp_path / "f.png")
    assert res.features["snr_bpfo"] > 8
    assert res.features["snr_bpfo"] > 3 * res.features["snr_bpfi"]
    assert (tmp_path / "f.png").exists() and (tmp_path / "f.csv").exists()


def test_healthy_has_no_bpfo_peak(tmp_path):
    t, x = synthetic_signal(fault_hz=0.0)
    p = tmp_path / "h.csv"
    write_csv(p, t, x)
    res = bearing_envelope_spectrum(p)
    assert res.features["snr_bpfo"] < 6


def test_demo_runs():
    r = subprocess.run([sys.executable, str(TOOL / "examples" / "run_demo.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "snr_bpfo" in r.stdout
