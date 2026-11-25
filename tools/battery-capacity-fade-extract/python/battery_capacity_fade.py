"""Per-cycle discharge capacity, SOH and early-cycle features from cycling data."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

FIELDS = ["cycle", "time_s", "current_a", "voltage_v"]


def load_cycles(path):
    """Read cycle,time_s,current_a,voltage_v. Discharge current is negative."""
    with open(path, newline="") as f:
        rd = csv.DictReader(f)
        if rd.fieldnames is None or any(c not in rd.fieldnames for c in FIELDS):
            raise ValueError("CSV needs columns: " + ",".join(FIELDS))
        rows = [[float(r[c]) for c in FIELDS] for r in rd]
    if not rows:
        raise ValueError("empty file")
    a = np.array(rows)
    if not np.all(np.isfinite(a)):
        raise ValueError("non-finite value in file")
    return a[:, 0].astype(int), a[:, 1], a[:, 2], a[:, 3]


def synthetic_rows(n_cycles=120, q0=1.10, dt=120.0):
    """Deterministic synthetic cell: ~0.05 %/cycle linear fade plus a small knee."""
    rows = []
    t = 0.0
    for k in range(1, n_cycles + 1):
        q = q0 * (1 - 0.0005 * (k - 1) - 0.00002 * max(0, k - 80) ** 1.5)
        q *= 1 + 0.002 * np.sin(k * 1.7)  # deterministic measurement ripple
        for sign, label in ((1, "chg"), (-1, "dis")):
            n = int(round(q * 3600 / (1.1 * dt)))
            for i in range(n + 1):
                soc = i / n
                v = 3.0 + 1.2 * soc if sign > 0 else 4.2 - 1.2 * soc
                rows.append((k, round(t, 1), round(sign * 1.1, 3), round(v, 4)))
                t += dt
            # the last sample of a segment covers a partial step; scale handled below
    return rows


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        w.writerows(rows)


def battery_capacity_fade_extract(csv_path, nominal_ah=None, n_early=100, eol_soh=0.8,
                                  output_csv=None, output_png=None):
    """Return dict: cycles, capacity_ah, soh, features, eol_cycle.

    Capacity = trapezoid integral of |I| dt over samples with I < 0 inside one cycle.
    SOH = capacity / nominal_ah (default: capacity of the first cycle).
    """
    if not 0 < eol_soh < 1:
        raise ValueError("eol_soh must be in (0,1)")
    if n_early < 3:
        raise ValueError("n_early must be >= 3")
    cyc, t, i, _ = load_cycles(csv_path)
    cycles, cap = [], []
    for k in np.unique(cyc):
        m = (cyc == k) & (i < 0)
        if m.sum() < 2:
            continue
        tk, ik = t[m], -i[m]
        if np.any(np.diff(tk) <= 0):
            raise ValueError(f"time not increasing in cycle {k}")
        cycles.append(int(k))
        cap.append(float(np.sum((ik[1:] + ik[:-1]) / 2 * np.diff(tk)) / 3600.0))
    if len(cycles) < 3:
        raise ValueError("need discharge data for at least 3 cycles")
    cycles = np.array(cycles)
    cap = np.array(cap)
    q_nom = float(nominal_ah) if nominal_ah else float(cap[0])
    soh = cap / q_nom
    e = cycles <= cycles[0] + n_early - 1
    x, y = cycles[e].astype(float), cap[e]
    slope = float(np.polyfit(x, y, 1)[0])
    feats = {"q_first": float(y[0]), "q_last_early": float(y[-1]), "delta_q": float(y[-1] - y[0]),
             "q_mean": float(y.mean()), "q_std": float(y.std()), "slope_ah_per_cycle": slope,
             "n_early": int(e.sum())}
    below = np.nonzero(soh <= eol_soh)[0]
    res = {"cycles": cycles, "capacity_ah": cap, "soh": soh, "nominal_ah": q_nom,
           "features": feats, "eol_cycle": int(cycles[below[0]]) if below.size else None}
    if output_csv:
        with open(output_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["cycle", "capacity_ah", "soh"])
            for a, b, c in zip(cycles, cap, soh):
                w.writerow([int(a), f"{b:.5f}", f"{c:.5f}"])
    if output_png:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.plot(cycles, cap, ".-", ms=3)
        ax.axvspan(x[0], x[-1], color="C1", alpha=0.12, label="early window")
        ax.set_xlabel("cycle")
        ax.set_ylabel("discharge capacity (Ah)")
        ax2 = ax.twinx()
        ax2.set_ylabel("SOH")
        ax2.set_ylim(ax.get_ylim()[0] / q_nom, ax.get_ylim()[1] / q_nom)
        ax.legend(loc="lower left")
        fig.tight_layout()
        fig.savefig(output_png, dpi=120)
        plt.close(fig)
    return res


def format_summary(r):
    f = r["features"]
    return (f"cycles={len(r['cycles'])} q0={r['capacity_ah'][0]:.3f}Ah "
            f"qEnd={r['capacity_ah'][-1]:.3f}Ah soh_end={r['soh'][-1]:.3f} "
            f"slope={f['slope_ah_per_cycle']:.5f}Ah/cycle eol={r['eol_cycle']}")

