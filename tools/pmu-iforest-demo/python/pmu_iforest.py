"""Isolation Forest (from scratch, numpy only) for PMU phasor glitch detection."""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

EULER = 0.5772156649015329


def _c(n: float) -> float:
    """Average path length of an unsuccessful BST search over n points."""
    if n <= 1:
        return 0.0
    if n == 2:
        return 1.0
    return 2.0 * (math.log(n - 1.0) + EULER) - 2.0 * (n - 1.0) / n


def _grow(X: np.ndarray, depth: int, limit: int, rng: np.random.Generator):
    n = X.shape[0]
    if depth >= limit or n <= 1:
        return ("leaf", n)
    lo, hi = X.min(axis=0), X.max(axis=0)
    cols = np.flatnonzero(hi > lo)
    if cols.size == 0:
        return ("leaf", n)
    q = int(rng.choice(cols))
    p = rng.uniform(lo[q], hi[q])
    mask = X[:, q] < p
    return ("node", q, p, _grow(X[mask], depth + 1, limit, rng),
            _grow(X[~mask], depth + 1, limit, rng))


def _path(tree, x: np.ndarray) -> float:
    depth = 0
    while tree[0] == "node":
        tree = tree[3] if x[tree[1]] < tree[2] else tree[4]
        depth += 1
    return depth + _c(tree[1])


@dataclass
class IForestResult:
    time_s: np.ndarray
    features: np.ndarray
    feature_names: list
    scores: np.ndarray
    threshold: float
    flags: np.ndarray
    anomaly_times: np.ndarray
    contamination: float
    n_trees: int
    max_samples: int
    seed: int
    precision: float | None = None
    recall: float | None = None
    summary: str = ""
    output_csv: str | None = None
    output_png: str | None = None


def build_features(v_mag, v_angle_deg, freq_hz, f_nom=50.0):
    """Per-frame features: |V|, frame-to-frame |V| change, angle step (deg), freq deviation (Hz)."""
    v_mag = np.asarray(v_mag, float)
    ang = np.degrees(np.unwrap(np.radians(np.asarray(v_angle_deg, float))))
    d_mag = np.r_[0.0, np.diff(v_mag)]
    d_ang = np.r_[0.0, np.diff(ang)]
    df = np.asarray(freq_hz, float) - f_nom
    X = np.column_stack([v_mag, d_mag, d_ang, df])
    return X, ["v_mag_pu", "d_mag_pu", "d_angle_deg", "df_hz"]


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    col = lambda k: np.array([float(r[k]) for r in rows])
    truth = col("true_anomaly") if rows and "true_anomaly" in rows[0] else None
    return col("time_s"), col("v_mag_pu"), col("v_angle_deg"), col("freq_hz"), truth


def pmu_iforest(source, *, n_trees=100, max_samples=256, contamination=0.02,
                f_nom=50.0, seed=0, output_csv=None, output_png=None, show=False):
    """Score each PMU frame with an Isolation Forest and flag the top `contamination` share.

    `source` is a CSV path (time_s, v_mag_pu, v_angle_deg, freq_hz[, true_anomaly]) or a
    tuple (time_s, v_mag_pu, v_angle_deg, freq_hz).
    """
    truth = None
    if isinstance(source, (str, Path)):
        t, mag, ang, fr, truth = _read_csv(source)
    else:
        t, mag, ang, fr = [np.asarray(a, float) for a in source[:4]]
    if not 0.0 < contamination < 0.5:
        raise ValueError("contamination must be in (0, 0.5)")
    if len(t) < 16:
        raise ValueError("need at least 16 frames")
    X, names = build_features(mag, ang, fr, f_nom)
    # robust scaling so no feature dominates by unit alone
    med = np.median(X, axis=0)
    mad = np.median(np.abs(X - med), axis=0)
    mad[mad == 0] = 1.0
    Z = (X - med) / mad
    n = Z.shape[0]
    psi = min(max_samples, n)
    limit = int(math.ceil(math.log2(psi)))
    rng = np.random.default_rng(seed)
    trees = [_grow(Z[rng.choice(n, psi, replace=False)], 0, limit, rng) for _ in range(n_trees)]
    mean_path = np.array([np.mean([_path(tr, z) for tr in trees]) for z in Z])
    scores = 2.0 ** (-mean_path / _c(psi))
    threshold = float(np.quantile(scores, 1.0 - contamination))
    flags = scores >= threshold
    res = IForestResult(t, X, names, scores, threshold, flags, t[flags], contamination,
                        n_trees, psi, seed)
    if truth is not None:
        tp = int(np.sum(flags & (truth > 0)))
        res.precision = tp / max(int(flags.sum()), 1)
        res.recall = tp / max(int((truth > 0).sum()), 1)
    res.summary = (f"pmu-iforest: frames={n} flagged={int(flags.sum())} "
                   f"threshold={threshold:.4f} contamination={contamination}")
    if res.precision is not None:
        res.summary += f" precision={res.precision:.3f} recall={res.recall:.3f}"
    if output_csv:
        p = Path(output_csv)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["time_s", *names, "score", "flag"])
            for i in range(n):
                w.writerow([f"{t[i]:.5f}", *[f"{v:.6g}" for v in X[i]],
                            f"{scores[i]:.6f}", int(flags[i])])
        res.output_csv = str(p)
    if output_png or show:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(3, 1, figsize=(9, 7), sharex=True)
        ax[0].plot(t, X[:, 0], lw=0.8)
        ax[0].scatter(t[flags], X[flags, 0], c="r", s=14, zorder=3)
        ax[0].set_ylabel("|V| (pu)")
        ax[1].plot(t, fr, lw=0.8)
        ax[1].scatter(t[flags], fr[flags], c="r", s=14, zorder=3)
        ax[1].set_ylabel("f (Hz)")
        ax[2].plot(t, scores, lw=0.8)
        ax[2].axhline(threshold, color="r", ls="--", lw=0.8)
        ax[2].set_ylabel("anomaly score")
        ax[2].set_xlabel("time (s)")
        fig.tight_layout()
        if output_png:
            Path(output_png).parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_png, dpi=120)
            res.output_png = str(output_png)
        if show:
            plt.show()
        else:
            plt.close(fig)
    return res
