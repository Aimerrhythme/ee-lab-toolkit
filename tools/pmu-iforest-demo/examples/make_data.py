"""Generate the synthetic PMU stream (30 frames/s, 20 s, 50 Hz nominal)."""
from pathlib import Path
import numpy as np

rng = np.random.default_rng(7)
fs = 30.0
n = 600
t = np.arange(n) / fs
mag = 1.0 + 0.004 * np.sin(2 * np.pi * 0.2 * t) + 0.0008 * rng.standard_normal(n)
ang = 3.0 + 0.5 * np.sin(2 * np.pi * 0.1 * t) + 0.02 * rng.standard_normal(n)
freq = 50.0 + 0.01 * np.sin(2 * np.pi * 0.15 * t) + 0.002 * rng.standard_normal(n)
label = np.zeros(n, dtype=int)
for k in (90, 210, 400):                     # single-frame glitches
    mag[k] += (-1) ** k * 0.12
    ang[k] += 6.0
    label[k] = 1
for k in range(300, 312):                    # short frequency excursion
    freq[k] += 0.25 * np.sin(np.pi * (k - 300) / 11)
    label[k] = 1
for k in (500, 501):                         # two-frame magnitude sag
    mag[k] -= 0.08
    label[k] = 1
out = Path(__file__).parent / "data" / "synthetic_pmu.csv"
with open(out, "w", encoding="utf-8") as f:
    f.write("time_s,v_mag_pu,v_angle_deg,freq_hz,true_anomaly\n")
    for i in range(n):
        f.write(f"{t[i]:.5f},{mag[i]:.5f},{ang[i]:.4f},{freq[i]:.5f},{label[i]}\n")
print("wrote", out)
