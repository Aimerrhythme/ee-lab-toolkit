"""Naive day-ahead price baselines and their MAE / sMAPE table.

Input: hourly CSV with columns ``date,hour,price`` (hour 0..23, whole days,
consecutive).  Forecast for day d, hour h:
    naive_prev_day  = price(d-1, h)    ("same hour yesterday")
    naive_prev_week = price(d-7, h)    ("same weekday last week")
Both are scored on the SAME days (day index >= eval_start_day, default 7).
sMAPE is in percent: mean(|e| / ((|y|+|yhat|)/2)) * 100, with 0/0 counted as 0.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

MODELS = ("naive_prev_day", "naive_prev_week")
LAGS = {"naive_prev_day": 1, "naive_prev_week": 7}


def load_prices(csv_path):
    """Return (dates list[str], prices ndarray shape (n_days, 24))."""
    dates, hours, prices = [], [], []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            dates.append(row["date"].strip())
            hours.append(int(row["hour"]))
            prices.append(float(row["price"]))
    n = len(prices)
    if n == 0 or n % 24 != 0:
        raise ValueError("row count must be a positive multiple of 24")
    if any(h != i % 24 for i, h in enumerate(hours)):
        raise ValueError("hours must run 0..23 consecutively in every day")
    p = np.asarray(prices, dtype=float)
    if not np.all(np.isfinite(p)):
        raise ValueError("prices must be finite (no blank/NaN)")
    return dates[::24], p.reshape(-1, 24)


def smape_pct(y, yhat):
    """Symmetric MAPE in percent; a 0/0 pair contributes 0."""
    y = np.asarray(y, float)
    yhat = np.asarray(yhat, float)
    den = (np.abs(y) + np.abs(yhat)) / 2.0
    ratio = np.where(den == 0, 0.0, np.abs(y - yhat) / np.where(den == 0, 1.0, den))
    return float(np.mean(ratio) * 100.0)


def mae(y, yhat):
    return float(np.mean(np.abs(np.asarray(y, float) - np.asarray(yhat, float))))


def rmse(y, yhat):
    d = np.asarray(y, float) - np.asarray(yhat, float)
    return float(np.sqrt(np.mean(d * d)))


def epf_naive_baselines(csv_path, eval_start_day=7, output_csv=None,
                        output_png=None, show=False):
    """Run both baselines; return dict with metrics, forecasts and hourly MAE."""
    dates, P = load_prices(csv_path)
    n_days = P.shape[0]
    if eval_start_day < 7:
        raise ValueError("eval_start_day must be >= 7 so both baselines exist")
    if eval_start_day >= n_days:
        raise ValueError("eval_start_day must be < number of days")
    days = np.arange(eval_start_day, n_days)
    actual = P[days]
    forecasts = {m: P[days - LAGS[m]] for m in MODELS}
    metrics = {m: {"mae": mae(actual, forecasts[m]),
                   "smape_pct": smape_pct(actual, forecasts[m]),
                   "rmse": rmse(actual, forecasts[m])} for m in MODELS}
    hourly_mae = {m: np.mean(np.abs(actual - forecasts[m]), axis=0) for m in MODELS}
    result = {"dates": [dates[d] for d in days], "actual": actual,
              "forecasts": forecasts, "metrics": metrics,
              "hourly_mae": hourly_mae, "n_eval_days": len(days)}
    if output_csv:
        Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "hour", "actual", *MODELS])
            for i, d in enumerate(result["dates"]):
                for h in range(24):
                    w.writerow([d, h, f"{actual[i, h]:.4f}",
                                *[f"{forecasts[m][i, h]:.4f}" for m in MODELS]])
    if output_png or show:
        _plot(result, output_png, show)
    return result


def format_summary(result):
    lines = [f"eval_days={result['n_eval_days']}",
             "model,mae,smape_pct,rmse"]
    for m in MODELS:
        s = result["metrics"][m]
        lines.append(f"{m},{s['mae']:.4f},{s['smape_pct']:.4f},{s['rmse']:.4f}")
    return "\n".join(lines)


def _plot(result, output_png, show):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    actual = result["actual"].reshape(-1)
    k = min(len(actual), 24 * 7)
    x = np.arange(k)
    ax[0].plot(x, actual[:k], "k", lw=1.5, label="actual")
    for m in MODELS:
        ax[0].plot(x, result["forecasts"][m].reshape(-1)[:k], lw=1, label=m)
    ax[0].set_xlabel("hour (first 7 evaluated days)")
    ax[0].set_ylabel("price")
    ax[0].legend()
    for m in MODELS:
        ax[1].plot(range(24), result["hourly_mae"][m], marker="o", label=m)
    ax[1].set_xlabel("hour of day")
    ax[1].set_ylabel("MAE")
    ax[1].legend()
    fig.tight_layout()
    if output_png:
        Path(output_png).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_png, dpi=120)
    if show:
        plt.show()
    plt.close(fig)
