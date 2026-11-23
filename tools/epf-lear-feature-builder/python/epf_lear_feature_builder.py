"""Build the LEAR input matrix: one row per target day.

Input CSV: ``date,hour,price[,load_forecast]`` (date ISO yyyy-mm-dd, hour 0..23,
whole consecutive days).  For target day d (0-based, d >= max(lags)):
    price lags   : price(d-L, h) for L in lags (default 1,2,3,7), h = 0..23
    exogenous    : load_forecast(d, h) of the TARGET day, if the column exists
    weekday dummy: Mon..Sun one-hot (7 columns)
Columns are ordered lag blocks, then exogenous, then dummies.  Target y = price(d, :).
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import numpy as np

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def load_table(csv_path):
    """Return (dates, price (n,24), exog (n,24) or None)."""
    dates, hours, prices, loads = [], [], [], []
    has_load = False
    with open(csv_path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        has_load = "load_forecast" in (rd.fieldnames or [])
        for row in rd:
            dates.append(row["date"].strip())
            hours.append(int(row["hour"]))
            prices.append(float(row["price"]))
            if has_load:
                loads.append(float(row["load_forecast"]))
    n = len(prices)
    if n == 0 or n % 24 != 0:
        raise ValueError("row count must be a positive multiple of 24")
    if any(h != i % 24 for i, h in enumerate(hours)):
        raise ValueError("hours must run 0..23 consecutively in every day")
    p = np.asarray(prices, float)
    if not np.all(np.isfinite(p)):
        raise ValueError("prices must be finite")
    ex = None
    if has_load:
        ex = np.asarray(loads, float)
        if not np.all(np.isfinite(ex)):
            raise ValueError("load_forecast must be finite")
        ex = ex.reshape(-1, 24)
    return dates[::24], p.reshape(-1, 24), ex


def feature_names(lags, with_exog):
    names = [f"price_D-{L}_h{h:02d}" for L in lags for h in range(24)]
    if with_exog:
        names += [f"load_fc_D_h{h:02d}" for h in range(24)]
    names += [f"dow_{d}" for d in DAY_NAMES]
    return names


def epf_lear_feature_builder(csv_path, lags=(1, 2, 3, 7), output_csv=None, output_png=None, show=False):
    """Return dict with X, y, names, target_dates, lags, n_rows, n_features."""
    lags = tuple(int(L) for L in lags)
    if not lags or min(lags) < 1:
        raise ValueError("lags must be positive integers")
    dates, P, ex = load_table(csv_path)
    n = P.shape[0]
    first = max(lags)
    if n <= first:
        raise ValueError("need more days than the largest lag")
    rows = []
    for d in range(first, n):
        parts = [P[d - L] for L in lags]
        if ex is not None:
            parts.append(ex[d])
        dow = np.zeros(7)
        dow[date.fromisoformat(dates[d]).weekday()] = 1.0
        parts.append(dow)
        rows.append(np.concatenate(parts))
    X = np.vstack(rows)
    y = P[first:]
    names = feature_names(lags, ex is not None)
    result = {"X": X, "y": y, "names": names, "target_dates": dates[first:], "lags": lags,
              "n_rows": X.shape[0], "n_features": X.shape[1]}
    if output_csv:
        Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date"] + names + [f"y_h{h:02d}" for h in range(24)])
            for i in range(X.shape[0]):
                w.writerow([result["target_dates"][i]] + [f"{v:.4f}" for v in X[i]] + [f"{v:.4f}" for v in y[i]])
    if output_png:
        _plot(result, output_png, show)
    return result


def _plot(result, path, show):
    import matplotlib.pyplot as plt
    X = result["X"]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4), gridspec_kw={"width_ratios": [3, 1]})
    im = ax[0].imshow(X.T, aspect="auto", cmap="viridis")
    ax[0].set_xlabel("target day index")
    ax[0].set_ylabel("feature column")
    ax[0].set_title("LEAR feature matrix (transposed)")
    fig.colorbar(im, ax=ax[0])
    last = len(result["lags"]) * 24
    ax[1].bar(range(7), X[:, -7:].sum(axis=0))
    ax[1].set_xticks(range(7), [d[0] for d in DAY_NAMES])
    ax[1].set_title("rows per weekday")
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)
    if show:
        plt.show()
    plt.close(fig)


def format_summary(result):
    X = result["X"]
    return "\n".join([
        f"rows={result['n_rows']} features={result['n_features']} lags={','.join(str(L) for L in result['lags'])}",
        f"first_target={result['target_dates'][0]} last_target={result['target_dates'][-1]}",
        f"X_sum={X.sum():.4f} y_mean={result['y'].mean():.4f}",
        f"first_row_head={','.join(f'{v:.2f}' for v in X[0, :4])}",
    ])
