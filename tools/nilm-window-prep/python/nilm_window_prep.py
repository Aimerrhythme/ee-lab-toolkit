"""Align aggregate / appliance power, resample, fill short gaps, cut windows.

Input CSV columns: `timestamp_s,aggregate_w,appliance_w` (epoch or relative
seconds, sorted, may be irregular or have missing rows).
Steps:
 1. bin to a regular grid of `step_s` seconds (bin mean; empty bin = NaN);
    bin k covers [t0 + k*step_s, t0 + (k+1)*step_s)
 2. linearly fill interior NaN runs of length <= max_gap_steps (longer runs stay NaN)
 3. cut windows of odd length `window` every `stride` bins; keep a window only
    if every aggregate sample AND the appliance value at its midpoint are finite.
    Sample pair: X = aggregate window, y = appliance at the window midpoint.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np


def load_series(csv_path):
    """Return (t, aggregate, appliance) float arrays."""
    t, a, b = [], [], []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t.append(float(row["timestamp_s"]))
            a.append(float(row["aggregate_w"]))
            b.append(float(row["appliance_w"]))
    t, a, b = (np.asarray(v, float) for v in (t, a, b))
    if t.size == 0:
        raise ValueError("empty input")
    if np.any(np.diff(t) <= 0):
        raise ValueError("timestamps must be strictly increasing")
    return t, a, b


def bin_mean(t, v, t0, step_s, n_bins):
    """Mean of v per bin; bins with no finite sample are NaN."""
    k = np.floor((t - t0) / step_s).astype(int)
    ok = np.isfinite(v) & (k >= 0) & (k < n_bins)
    cnt = np.bincount(k[ok], minlength=n_bins).astype(float)
    sm = np.bincount(k[ok], weights=v[ok], minlength=n_bins)
    out = np.full(n_bins, np.nan)
    nz = cnt > 0
    out[nz] = sm[nz] / cnt[nz]
    return out


def fill_short_gaps(x, max_gap_steps):
    """Linear interpolation of interior NaN runs no longer than max_gap_steps."""
    x = x.copy()
    n, i, filled = len(x), 0, 0
    while i < n:
        if np.isnan(x[i]):
            j = i
            while j < n and np.isnan(x[j]):
                j += 1
            if i > 0 and j < n and (j - i) <= max_gap_steps:
                x[i:j] = np.interp(np.arange(i, j), [i - 1, j], [x[i - 1], x[j]])
                filled += j - i
            i = j
        else:
            i += 1
    return x, filled


def nilm_window_prep(csv_path, step_s=6, max_gap_steps=3, window=11, stride=1,
                     output_csv=None, output_png=None, show=False):
    """Run the pipeline; return dict with X, y, starts and counters."""
    if window < 1 or window % 2 == 0:
        raise ValueError("window must be a positive odd integer")
    if step_s <= 0 or stride < 1 or max_gap_steps < 0:
        raise ValueError("step_s > 0, stride >= 1, max_gap_steps >= 0 required")
    t, a, b = load_series(csv_path)
    t0 = t[0]
    n_bins = int(np.floor((t[-1] - t0) / step_s)) + 1
    agg = bin_mean(t, a, t0, step_s, n_bins)
    app = bin_mean(t, b, t0, step_s, n_bins)
    n_empty = int(np.sum(np.isnan(agg)))
    agg, f1 = fill_short_gaps(agg, max_gap_steps)
    app, f2 = fill_short_gaps(app, max_gap_steps)
    half = window // 2
    starts_all = np.arange(0, n_bins - window + 1, stride)
    keep = [s for s in starts_all
            if np.all(np.isfinite(agg[s:s + window])) and np.isfinite(app[s + half])]
    starts = np.asarray(keep, dtype=int)
    X = np.array([agg[s:s + window] for s in starts]).reshape(-1, window)
    y = np.array([app[s + half] for s in starts])
    res = {"X": X, "y": y, "starts": starts, "t_mid": t0 + (starts + half + 0.5) * step_s,
           "agg": agg, "app": app, "n_bins": n_bins, "n_empty_bins": n_empty,
           "n_filled": f1 + f2, "n_candidates": len(starts_all),
           "n_windows": len(starts), "n_dropped": len(starts_all) - len(starts),
           "window": window, "step_s": step_s}
    if output_csv:
        Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["start_bin", "t_mid_s", "y_w"] + [f"x{i}" for i in range(window)])
            for i, s in enumerate(starts):
                w.writerow([int(s), f"{res['t_mid'][i]:.1f}", f"{y[i]:.3f}"]
                           + [f"{v:.3f}" for v in X[i]])
    if output_png or show:
        _plot(res, output_png, show)
    return res


def format_summary(res):
    return "\n".join([
        f"bins={res['n_bins']}", f"empty_bins={res['n_empty_bins']}",
        f"filled={res['n_filled']}", f"candidates={res['n_candidates']}",
        f"windows={res['n_windows']}", f"dropped={res['n_dropped']}",
        f"y_mean_w={res['y'].mean():.3f}" if res['n_windows'] else "y_mean_w=nan"])


def _plot(res, output_png, show):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 1, figsize=(10, 6))
    x = np.arange(res["n_bins"])
    ax[0].plot(x, res["agg"], lw=1, label="aggregate")
    ax[0].plot(x, res["app"], lw=1, label="appliance")
    gap = np.isnan(res["agg"])
    for i in np.where(gap)[0]:
        ax[0].axvspan(i - 0.5, i + 0.5, color="red", alpha=0.2, lw=0)
    ax[0].set_xlabel("bin"); ax[0].set_ylabel("W"); ax[0].legend()
    ax[0].set_title("resampled series (red = unfilled gap)")
    if res["n_windows"]:
        for i in np.linspace(0, res["n_windows"] - 1, min(4, res["n_windows"])).astype(int):
            ax[1].plot(range(res["window"]), res["X"][i], lw=1)
            ax[1].plot(res["window"] // 2, res["y"][i], "ko")
    ax[1].set_xlabel("position in window"); ax[1].set_ylabel("W")
    ax[1].set_title("sample windows (dot = midpoint appliance target)")
    fig.tight_layout()
    if output_png:
        Path(output_png).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_png, dpi=120)
    if show:
        plt.show()
    plt.close(fig)
