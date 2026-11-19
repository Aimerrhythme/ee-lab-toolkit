"""Bearing envelope spectrum: band-pass, Hilbert envelope, fault-frequency markers, features.

Teaching tool. Uses numpy only for signal processing (FFT band-pass, FFT Hilbert).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


def bearing_fault_freqs(rpm, n_balls, ball_d, pitch_d, contact_deg=0.0):
    """Return dict fr, bpfo, bpfi, bsf, ftf in Hz."""
    fr = rpm / 60.0
    c = (ball_d / pitch_d) * np.cos(np.deg2rad(contact_deg))
    return {
        "fr": fr,
        "bpfo": n_balls / 2.0 * fr * (1 - c),
        "bpfi": n_balls / 2.0 * fr * (1 + c),
        "bsf": pitch_d / (2.0 * ball_d) * fr * (1 - c ** 2),
        "ftf": fr / 2.0 * (1 - c),
    }


def load_signal(csv_path):
    """Read `t_s,accel`; return (fs, x). fs = 1 / median(dt)."""
    t, x = [], []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t.append(float(row["t_s"]))
            x.append(float(row["accel"]))
    t = np.asarray(t)
    x = np.asarray(x)
    if len(x) < 16 or not np.all(np.isfinite(x)) or not np.all(np.isfinite(t)):
        raise ValueError("need >= 16 finite samples")
    dt = np.diff(t)
    if np.any(dt <= 0):
        raise ValueError("t_s must be strictly increasing")
    return 1.0 / float(np.median(dt)), x


def bandpass_fft(x, fs, f_lo, f_hi):
    """Zero-phase ideal band-pass by zeroing FFT bins outside [f_lo, f_hi]."""
    if not (0 <= f_lo < f_hi <= fs / 2):
        raise ValueError("need 0 <= f_lo < f_hi <= fs/2")
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / fs)
    spec[(f < f_lo) | (f > f_hi)] = 0.0
    return np.fft.irfft(spec, n=len(x))


def hilbert_envelope(x):
    """|analytic signal| via the FFT method."""
    n = len(x)
    spec = np.fft.fft(x)
    h = np.zeros(n)
    if n % 2 == 0:
        h[0] = h[n // 2] = 1.0
        h[1:n // 2] = 2.0
    else:
        h[0] = 1.0
        h[1:(n + 1) // 2] = 2.0
    return np.abs(np.fft.ifft(spec * h))


def amplitude_spectrum(x, fs):
    """Single-sided amplitude spectrum with Hann window (mean removed); returns (f, amp)."""
    x = np.asarray(x, float) - np.mean(x)
    w = np.hanning(len(x))
    amp = np.abs(np.fft.rfft(x * w)) * 2.0 / np.sum(w)
    return np.fft.rfftfreq(len(x), 1.0 / fs), amp


def _kurtosis(x):
    d = x - np.mean(x)
    s2 = np.mean(d ** 2)
    return float(np.mean(d ** 4) / s2 ** 2) if s2 > 0 else 0.0


def _peak_near(f, amp, f0, tol):
    m = (f >= f0 - tol) & (f <= f0 + tol)
    if not np.any(m):
        return float("nan")
    return float(np.max(amp[m]))


@dataclass
class EnvelopeResult:
    fs: float
    freqs: dict
    features: dict
    f_env: np.ndarray = field(repr=False)
    amp_env: np.ndarray = field(repr=False)
    summary: str = ""


def bearing_envelope_spectrum(csv_path, rpm=1797.0, n_balls=9, ball_d=7.94,
                              pitch_d=39.04, contact_deg=0.0, band=(2000.0, 5000.0),
                              tol_hz=3.0, f_max=500.0, output_csv=None,
                              output_png=None, show=False):
    """Run the pipeline on a `t_s,accel` CSV. Returns EnvelopeResult."""
    fs, x = load_signal(csv_path)
    freqs = bearing_fault_freqs(rpm, n_balls, ball_d, pitch_d, contact_deg)
    xb = bandpass_fft(x, fs, band[0], band[1])
    env = hilbert_envelope(xb)
    f_env, a_env = amplitude_spectrum(env, fs)
    sel = (f_env >= 10.0) & (f_env <= f_max)
    floor = float(np.median(a_env[sel]))
    feats = {
        "rms": float(np.sqrt(np.mean(x ** 2))),
        "peak": float(np.max(np.abs(x))),
        "crest": float(np.max(np.abs(x)) / np.sqrt(np.mean(x ** 2))),
        "kurtosis": _kurtosis(x),
        "env_rms": float(np.sqrt(np.mean((env - env.mean()) ** 2))),
        "env_kurtosis": _kurtosis(env),
        "floor": floor,
    }
    for name in ("fr", "bpfo", "bpfi"):
        feats[f"amp_{name}"] = _peak_near(f_env, a_env, freqs[name], tol_hz)
        feats[f"snr_{name}"] = feats[f"amp_{name}"] / floor if floor > 0 else float("nan")
    res = EnvelopeResult(fs, freqs, feats, f_env, a_env)
    res.summary = format_summary(res)
    if output_csv:
        Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
        with open(output_csv, "w", encoding="utf-8", newline="\n") as f:
            f.write("feature,value\n")
            for k, v in feats.items():
                f.write(f"{k},{v:.6f}\n")
    if output_png or show:
        _plot(res, x, fs, band, f_max, output_png, show)
    return res


def format_summary(res):
    fr = res.freqs
    ft = res.features
    lines = [
        f"fs={res.fs:.1f} Hz fr={fr['fr']:.2f} bpfo={fr['bpfo']:.2f} bpfi={fr['bpfi']:.2f}",
        "feature,value",
    ]
    lines += [f"{k},{v:.4f}" for k, v in ft.items()]
    return "\n".join(lines)


def _plot(res, x, fs, band, f_max, output_png, show):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    n = min(len(x), int(0.1 * fs))
    ax[0].plot(np.arange(n) / fs, x[:n], lw=0.6)
    ax[0].set(title=f"Raw signal (first {n / fs:.2f} s)", xlabel="t (s)", ylabel="accel")
    m = res.f_env <= f_max
    ax[1].plot(res.f_env[m], res.amp_env[m], lw=0.8)
    for name, c in (("fr", "gray"), ("bpfo", "red"), ("bpfi", "green")):
        ax[1].axvline(res.freqs[name], color=c, ls="--", lw=0.8, label=f"{name} {res.freqs[name]:.1f} Hz")
    ax[1].set(title=f"Envelope spectrum (band {band[0]:.0f}-{band[1]:.0f} Hz)",
              xlabel="Hz", ylabel="amplitude")
    ax[1].legend()
    fig.tight_layout()
    if output_png:
        Path(output_png).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_png, dpi=120)
    if show:
        plt.show()
    plt.close(fig)
