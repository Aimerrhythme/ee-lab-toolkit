"""Generate synthetic bearing vibration (no real data). Deterministic."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def synthetic_signal(fs=12000.0, duration=1.0, rpm=1797.0, fault_hz=107.4,
                     f_res=3500.0, snr_noise=0.5, seed=7):
    """Shaft harmonics + resonance ringing at each impact (period 1/fault_hz) + noise."""
    rng = np.random.default_rng(seed)
    n = int(round(fs * duration))
    t = np.arange(n) / fs
    fr = rpm / 60.0
    x = 0.8 * np.sin(2 * np.pi * fr * t) + 0.3 * np.sin(2 * np.pi * 2 * fr * t)
    if fault_hz > 0:
        tau = np.arange(0, 0.02, 1 / fs)
        ring = np.exp(-tau * 900.0) * np.sin(2 * np.pi * f_res * tau)
        k = 0
        while True:
            t0 = k / fault_hz
            i0 = int(round(t0 * fs))
            if i0 >= n:
                break
            m = min(len(ring), n - i0)
            x[i0:i0 + m] += 2.0 * ring[:m]
            k += 1
    x += snr_noise * rng.standard_normal(n)
    return t, x


def write_csv(path, t, x):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("t_s,accel\n")
        for a, b in zip(t, x):
            f.write(f"{a:.8f},{b:.6f}\n")


if __name__ == "__main__":
    t, x = synthetic_signal()
    write_csv(Path(__file__).parent / "data" / "synthetic_bearing_vibration.csv", t, x)
