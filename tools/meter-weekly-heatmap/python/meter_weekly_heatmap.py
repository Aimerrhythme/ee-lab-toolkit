"""Fold daily smart-meter kWh into week x weekday matrices (fill gaps, normalize, plot).

Mirrors ``matlab/meter_weekly_heatmap.m``.

Input CSV columns: ``customer_id,label,date,kwh`` (date = YYYY-MM-DD; blank,
NaN, or negative kwh counts as missing; duplicate dates keep the first row).

Pipeline per customer on a shared grid (Monday on/before the global first date
to Sunday on/after the global last date):
  1. status: observed / missing
  2. fill: linear interpolation of INTERIOR gaps of at most ``max_gap`` days
     (status -> filled); longer gaps and edge gaps stay missing (NaN)
  3. normalize: min-max to [0, 1] over observed+filled days (flat -> 0)
Weekday index 0 = Monday. Day ordinal = datetime.date.toordinal (Mon -> %7 == 1).
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

OBSERVED, FILLED, MISSING = "observed", "filled", "missing"


@dataclass
class CustomerResult:
    customer_id: str
    label: str
    kwh: np.ndarray       # (n_weeks, 7) filled kWh, NaN where missing
    norm: np.ndarray      # (n_weeks, 7) min-max normalized, NaN where missing
    status: list          # (n_weeks*7) strings in row-major order
    n_observed: int
    n_filled: int
    n_missing: int
    missing_rate: float   # raw missing share of grid days in the customer's own span
    weekend_ratio: float  # mean weekend / mean weekday kWh (NaN if undefined)


@dataclass
class HeatmapResult:
    start_ordinal: int
    n_weeks: int
    customers: list = field(default_factory=list)


def _parse_kwh(text: str) -> float:
    text = text.strip()
    if text == "":
        return math.nan
    try:
        v = float(text)
    except ValueError:
        return math.nan
    return math.nan if (math.isnan(v) or v < 0) else v


def read_records(path):
    """Return ordered dict: customer_id -> (label, {ordinal: kwh})."""
    out: dict = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            cid = row["customer_id"].strip()
            ordn = date.fromisoformat(row["date"].strip()).toordinal()
            label, days = out.setdefault(cid, (row["label"].strip(), {}))
            if ordn not in days:
                days[ordn] = _parse_kwh(row["kwh"])
    return out


def fill_gaps(values: np.ndarray, max_gap: int):
    """Linear-interpolate interior NaN runs of length <= max_gap. Returns (out, filled_mask)."""
    out = values.copy()
    filled = np.zeros(values.shape, dtype=bool)
    n = len(values)
    i = 0
    while i < n:
        if np.isnan(values[i]):
            j = i
            while j < n and np.isnan(values[j]):
                j += 1
            if i > 0 and j < n and (j - i) <= max_gap:
                a, b = values[i - 1], values[j]
                for k in range(i, j):
                    out[k] = a + (b - a) * (k - i + 1) / (j - i + 1)
                    filled[k] = True
            i = j
        else:
            i += 1
    return out, filled


def meter_weekly_heatmap(csv_path, output_dir=None, output_png=None, max_gap=3, show=False):
    """Build week x weekday matrices for every customer; optionally export CSV/PNG."""
    records = read_records(csv_path)
    all_days = [d for _, (_, days) in records.items() for d in days]
    first, last = min(all_days), max(all_days)
    start = first - ((first - 1) % 7)            # Monday on/before first
    end = last + (6 - ((last - 1) % 7))          # Sunday on/after last
    n_days = end - start + 1
    n_weeks = n_days // 7
    res = HeatmapResult(start_ordinal=start, n_weeks=n_weeks)

    for cid, (label, days) in records.items():
        raw = np.full(n_days, np.nan)
        for ordn, v in days.items():
            raw[ordn - start] = v
        span = np.arange(min(days) - start, max(days) - start + 1)
        missing_in_span = int(np.isnan(raw[span]).sum())
        filled_vals, fmask = fill_gaps(raw, max_gap)
        status = [FILLED if fmask[k] else (MISSING if np.isnan(filled_vals[k]) else OBSERVED)
                  for k in range(n_days)]
        ok = ~np.isnan(filled_vals)
        norm = np.full(n_days, np.nan)
        if ok.any():
            lo, hi = filled_vals[ok].min(), filled_vals[ok].max()
            norm[ok] = 0.0 if hi == lo else (filled_vals[ok] - lo) / (hi - lo)
        wk = np.arange(n_days) % 7
        wkday = filled_vals[ok & (wk < 5)]
        wkend = filled_vals[ok & (wk >= 5)]
        ratio = (wkend.mean() / wkday.mean()) if len(wkday) and len(wkend) and wkday.mean() > 0 else math.nan
        res.customers.append(CustomerResult(
            cid, label, filled_vals.reshape(n_weeks, 7), norm.reshape(n_weeks, 7), status,
            status.count(OBSERVED), status.count(FILLED), status.count(MISSING),
            missing_in_span / len(span), float(ratio)))

    if output_dir is not None:
        _write_outputs(res, Path(output_dir))
    if output_png is not None or show:
        _plot(res, output_png, show)
    return res


def _write_outputs(res: HeatmapResult, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "matrix_long.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["customer_id", "label", "week", "weekday", "date", "kwh", "norm", "status"])
        for c in res.customers:
            for k in range(res.n_weeks * 7):
                wk, dy = divmod(k, 7)
                v, nv = c.kwh[wk, dy], c.norm[wk, dy]
                w.writerow([c.customer_id, c.label, wk, dy,
                            date.fromordinal(res.start_ordinal + k).isoformat(),
                            "" if np.isnan(v) else f"{v:.4f}",
                            "" if np.isnan(nv) else f"{nv:.4f}", c.status[k]])
    with open(out / "summary.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["customer_id", "label", "n_observed", "n_filled", "n_missing",
                    "missing_rate", "weekend_ratio"])
        for c in res.customers:
            w.writerow([c.customer_id, c.label, c.n_observed, c.n_filled, c.n_missing,
                        f"{c.missing_rate:.4f}", f"{c.weekend_ratio:.4f}"])


def format_table(res: HeatmapResult) -> str:
    lines = [f"meter-weekly-heatmap: customers={len(res.customers)} weeks={res.n_weeks}",
             "id    label    observed filled missing miss_rate wkend/wkday"]
    for c in res.customers:
        lines.append(f"{c.customer_id:<5} {c.label:<8} {c.n_observed:>8d} {c.n_filled:>6d} "
                     f"{c.n_missing:>7d} {c.missing_rate:>9.3f} {c.weekend_ratio:>11.3f}")
    return "\n".join(lines)


def _plot(res: HeatmapResult, png, show: bool) -> None:
    import matplotlib.pyplot as plt

    n = len(res.customers)
    fig, axes = plt.subplots(1, n, figsize=(2.6 * n + 1, 4.2), squeeze=False)
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("lightgray")
    for ax, c in zip(axes[0], res.customers):
        im = ax.imshow(np.ma.masked_invalid(c.norm), aspect="auto", cmap=cmap, vmin=0, vmax=1)
        ax.set_title(f"{c.customer_id} ({c.label})")
        ax.set_xticks(range(7))
        ax.set_xticklabels(list("MTWTFSS"))
        ax.set_ylabel("week")
    fig.colorbar(im, ax=list(axes[0]), label="min-max kWh (gray = missing)")
    if png is not None:
        Path(png).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(png, dpi=120)
    if show:
        plt.show()
    plt.close(fig)
