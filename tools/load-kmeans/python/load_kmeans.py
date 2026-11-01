"""Cluster typical daily load shapes with Lloyd k-means.

The algorithm matches ``matlab/load_kmeans.m``. It uses NumPy only: no
scikit-learn estimator and no Statistics Toolbox, so a fixed ``seed`` gives
the same labels in both runtimes.

Each day is one row. Peak normalization (the default) divides that row by its
own maximum, so clustering follows the shape and ignores the kilowatt level.
Mean normalization divides by the daily mean. ``normalize='none'`` keeps kW.

Centers are chosen with k-means++ and refined with Lloyd updates. ``n_init``
restarts keep the lowest within-cluster sum of squares. After that, clusters
are renumbered from 1 by the hour of each centroid's peak, earliest first.
Ties keep the lower index from before the sort. Squared distances use a
sequential sum so the two languages walk the samples in the same order.

    x_d = P_d / max(P_d)                         peak normalization
    SSE = sum_d || x_d - c_{label(d)} ||^2
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from numbers import Real
from pathlib import Path

import numpy as np

DEFAULT_K = 3
DEFAULT_SEED = 0
DEFAULT_N_INIT = 10
DEFAULT_MAX_ITER = 100
DEFAULT_NORMALIZE = "peak"
DEFAULT_DAY = "1970-01-01"
_LCG_A = 1664525
_LCG_C = 1013904223
_LCG_M = 4294967296
_NORMALIZE = ("peak", "mean", "none")
_PARAM_NAMES = {
    "k",
    "seed",
    "normalize",
    "n_init",
    "max_iter",
    "step_minutes",
    "time_col",
    "power_col",
    "dates",
    "day",
    "csv_path",
    "output_csv",
    "output_png",
    "show",
}
_TIME_ALIASES = (
    "timestamp",
    "datetime",
    "date_time",
    "datestamp",
    "time",
    "date",
    "ts",
    "时间戳",
    "时间",
    "时刻",
    "日期",
)
_POWER_ALIASES = (
    "power_kw",
    "p_kw",
    "load_kw",
    "load",
    "power",
    "p",
    "kw",
    "负荷kw",
    "功率kw",
    "功率",
    "负荷",
    "有功功率",
    "有功",
)
_PALETTE = (
    "#1f4e79",
    "#c0392b",
    "#0e7c66",
    "#e67e22",
    "#6c3483",
    "#1a5276",
    "#922b21",
    "#1b4f72",
)
_MONTH_DAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_Y_LABEL = {
    "peak": "Power / daily peak",
    "mean": "Power / daily mean",
    "none": "Power (kW)",
}


@dataclass
class LoadKMeansResult:
    """Labels, typical-day centroids, and the curves that were clustered.

    ``labels`` are 1 … k. ``profiles`` and ``centroids`` live in the normalized
    space that Lloyd saw. ``power_kw`` and ``centroids_kw`` stay in kW: the
    second is the mean of the raw member days, which is not the same thing as
    undoing peak normalization. ``centroid_peak_hour`` is the hour of the first
    maximum of each normalized centroid. ``attempt`` is the winning restart,
    counting from 0, and that restart was seeded with ``seed + attempt``
    modulo 2^32. ``silhouette`` is NaN when k < 2 or a cluster is empty.
    ``summary`` is the same text as ``format_table``.
    """

    labels: np.ndarray
    centroids: np.ndarray
    centroids_kw: np.ndarray
    profiles: np.ndarray
    power_kw: np.ndarray
    dates: list[str]
    hour: np.ndarray
    minute: np.ndarray
    k: int
    seed: int
    n_init: int
    max_iter: int
    normalize: str
    sse: float
    silhouette: float
    cluster_sizes: np.ndarray
    n_iter: int
    attempt: int
    day_sse: np.ndarray
    peak_kw: np.ndarray
    centroid_peak_hour: np.ndarray
    mean_peak_kw: np.ndarray
    step_minutes: float
    resampled: bool
    summary: str
    n_rows: int
    n_missing: int
    n_duplicates: int
    n_days: int
    output_csv: str | None
    output_png: str | None
    fig: object | None = None


def load_kmeans(
    source: str | Path | Sequence | None = None,
    power: Sequence | None = None,
    *,
    k: int = DEFAULT_K,
    seed: int = DEFAULT_SEED,
    normalize: str = DEFAULT_NORMALIZE,
    n_init: int = DEFAULT_N_INIT,
    max_iter: int = DEFAULT_MAX_ITER,
    step_minutes: float | None = None,
    time_col: str | None = None,
    power_col: str | None = None,
    dates: Sequence[str] | None = None,
    day: str | None = None,
    csv_path: str | Path | None = None,
    output_csv: str | Path | None = None,
    output_png: str | Path | None = None,
    show: bool = False,
) -> LoadKMeansResult:
    """Cluster daily load profiles.

    Parameters use the same names as the MATLAB name-value arguments.
    ``source`` is a CSV path, a profile matrix with one day per row, or, together
    with ``power``, timestamps or minutes from midnight of ``day``. Minutes must
    lie in ``[0, 1440)``. Blank CSV power cells are dropped. Duplicate timestamps
    keep the first row.
    """

    k = _integral("k", k, minimum=1, message="k must be a positive integer")
    seed = _integral("seed", seed, minimum=0, message="seed must be a non-negative integer")
    n_init = _integral("n_init", n_init, minimum=1, message="n_init must be a positive integer")
    max_iter = _integral("max_iter", max_iter, minimum=1, message="max_iter must be a positive integer")
    normalize = _normalize_name(normalize)
    if step_minutes is not None:
        step_minutes = _positive("step_minutes", step_minutes)
    show = _as_bool("show", show)
    raw, dates_out, minute, step, resampled, n_rows, n_missing, n_duplicates = _resolve(
        source,
        power,
        time_col=time_col,
        power_col=power_col,
        dates=dates,
        day=day,
        csv_path=csv_path,
        step_minutes=step_minutes,
    )
    n_days = int(raw.shape[0])
    if k > n_days:
        raise ValueError(f"k must not exceed the number of days ({n_days})")
    profiles = _normalize(raw, normalize, dates_out)
    labels0, centroids, n_iter, attempt = _best_fit(profiles, k, seed, n_init, max_iter)
    hour = np.ascontiguousarray(minute / 60.0, dtype=float)
    peak_kw = np.max(raw, axis=1).astype(float)
    day_sse = _row_sse(profiles, centroids, labels0)
    sse = float(_sum_1d(day_sse))
    silhouette = _silhouette(profiles, labels0, k)
    cluster_sizes = np.bincount(labels0, minlength=k).astype(int)
    centroid_peak_hour = hour[np.argmax(centroids, axis=1)]
    centroids_kw = np.full((k, raw.shape[1]), np.nan, dtype=float)
    mean_peak_kw = np.full(k, np.nan, dtype=float)
    for cluster in range(k):
        member = np.flatnonzero(labels0 == cluster)
        if member.size == 0:
            continue
        centroids_kw[cluster] = _mean_rows(raw[member])
        mean_peak_kw[cluster] = _mean_1d(peak_kw[member])
    labels = labels0 + 1
    summary = _format_result(
        dates_out,
        labels,
        peak_kw,
        day_sse,
        cluster_sizes,
        centroid_peak_hour,
        mean_peak_kw,
        k=k,
        seed=seed,
        n_init=n_init,
        normalize=normalize,
        sse=sse,
        silhouette=silhouette,
        n_iter=n_iter,
        attempt=attempt,
        step_minutes=step,
        resampled=resampled,
        n_rows=n_rows,
        n_missing=n_missing,
        n_duplicates=n_duplicates,
    )
    csv_out = None if output_csv is None or str(output_csv).strip() == "" else str(output_csv)
    png_out = None if output_png is None or str(output_png).strip() == "" else str(output_png)
    result = LoadKMeansResult(
        labels=np.ascontiguousarray(labels, dtype=int),
        centroids=np.ascontiguousarray(centroids, dtype=float),
        centroids_kw=np.ascontiguousarray(centroids_kw, dtype=float),
        profiles=np.ascontiguousarray(profiles, dtype=float),
        power_kw=np.ascontiguousarray(raw, dtype=float),
        dates=list(dates_out),
        hour=hour,
        minute=np.ascontiguousarray(minute, dtype=float),
        k=k,
        seed=seed,
        n_init=n_init,
        max_iter=max_iter,
        normalize=normalize,
        sse=sse,
        silhouette=silhouette,
        cluster_sizes=np.ascontiguousarray(cluster_sizes, dtype=int),
        n_iter=n_iter,
        attempt=attempt,
        day_sse=np.ascontiguousarray(day_sse, dtype=float),
        peak_kw=np.ascontiguousarray(peak_kw, dtype=float),
        centroid_peak_hour=np.ascontiguousarray(centroid_peak_hour, dtype=float),
        mean_peak_kw=np.ascontiguousarray(mean_peak_kw, dtype=float),
        step_minutes=float(step),
        resampled=bool(resampled),
        summary=summary,
        n_rows=n_rows,
        n_missing=n_missing,
        n_duplicates=n_duplicates,
        n_days=n_days,
        output_csv=csv_out,
        output_png=png_out,
        fig=None,
    )
    if csv_out is not None:
        _write_assignments(Path(csv_out), result)
    if png_out is not None or show:
        result.fig = _render_figure(result, png_out, show)
    return result


def format_table(result: LoadKMeansResult) -> str:
    """Format cluster sizes and one row of assignments per day."""

    return result.summary


class _LCG:
    """Numerical Recipes 32-bit LCG. The seed is the state before the first step."""

    def __init__(self, seed: int) -> None:
        self.state = int(seed) & 0xFFFFFFFF

    def next_u32(self) -> int:
        self.state = (_LCG_A * self.state + _LCG_C) & 0xFFFFFFFF
        return self.state

    def random(self) -> float:
        return self.next_u32() / _LCG_M

    def randbelow(self, n: int) -> int:
        return self.next_u32() % n


def _best_fit(
    profiles: np.ndarray,
    k: int,
    seed: int,
    n_init: int,
    max_iter: int,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    best_sse = math.inf
    best: tuple[np.ndarray, np.ndarray, int, int] | None = None
    for attempt in range(n_init):
        labels, centroids, n_iter = _fit_once(profiles, k, (seed + attempt) & 0xFFFFFFFF, max_iter)
        sse = float(_sum_1d(_row_sse(profiles, centroids, labels)))
        if sse < best_sse:
            best_sse = sse
            best = (labels.copy(), centroids.copy(), n_iter, attempt)
    assert best is not None
    return _relabel(best[1], best[0], best[2], best[3])


def _fit_once(x: np.ndarray, k: int, seed: int, max_iter: int) -> tuple[np.ndarray, np.ndarray, int]:
    centroids = _kmeans_pp(x, k, _LCG(seed))
    labels = _assign(x, centroids)
    n_iter = 0
    for _ in range(max_iter):
        centroids = _update(x, labels, centroids)
        n_iter += 1
        updated = _assign(x, centroids)
        if np.array_equal(updated, labels):
            return updated, centroids, n_iter
        labels = updated
    return labels, centroids, n_iter


def _kmeans_pp(x: np.ndarray, k: int, rng: _LCG) -> np.ndarray:
    n = int(x.shape[0])
    chosen = [rng.randbelow(n)]
    chosen_set = set(chosen)
    for _ in range(1, k):
        d2 = _sqdist_to_centers(x, x[np.asarray(chosen, dtype=int)])
        total = float(_sum_1d(d2))
        if not total > 0.0:
            pick = next(index for index in range(n) if index not in chosen_set)
        else:
            target = rng.random() * total
            cumulative = 0.0
            pick = n - 1
            for index in range(n):
                cumulative += float(d2[index])
                if cumulative >= target:
                    pick = index
                    break
            if pick in chosen_set:
                pick = _farthest_unused(d2, chosen_set)
        chosen.append(pick)
        chosen_set.add(pick)
    return x[np.asarray(chosen, dtype=int)].copy()


def _farthest_unused(d2: np.ndarray, used: set[int]) -> int:
    best = -1
    best_d = -math.inf
    for index in range(int(d2.size)):
        if index in used:
            continue
        value = float(d2[index])
        if value > best_d:
            best = index
            best_d = value
    if best < 0:
        raise ValueError("k exceeds the number of distinct profiles")
    return best


def _assign(x: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    n = int(x.shape[0])
    k = int(centroids.shape[0])
    labels = np.empty(n, dtype=int)
    for row in range(n):
        best = 0
        best_d = math.inf
        for cluster in range(k):
            value = _sqdist(x[row], centroids[cluster])
            if value < best_d:
                best = cluster
                best_d = value
        labels[row] = best
    return labels


def _update(x: np.ndarray, labels: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    k = int(centroids.shape[0])
    new = np.empty_like(centroids)
    empties: list[int] = []
    for cluster in range(k):
        member = np.flatnonzero(labels == cluster)
        if member.size:
            new[cluster] = _mean_rows(x[member])
        else:
            empties.append(cluster)
    if not empties:
        return new
    d2_own = np.empty(x.shape[0], dtype=float)
    for row in range(int(x.shape[0])):
        d2_own[row] = _sqdist(x[row], centroids[int(labels[row])])
    picked = np.zeros(x.shape[0], dtype=bool)
    for cluster in empties:
        best = -1
        best_d = -math.inf
        for row in range(int(x.shape[0])):
            if picked[row]:
                continue
            value = float(d2_own[row])
            if value > best_d:
                best = row
                best_d = value
        picked[best] = True
        new[cluster] = x[best]
    return new


def _relabel(
    centroids: np.ndarray,
    labels: np.ndarray,
    n_iter: int,
    attempt: int,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    k = int(centroids.shape[0])
    peak = [int(np.argmax(centroids[cluster])) for cluster in range(k)]
    order = sorted(range(k), key=lambda cluster: (peak[cluster], cluster))
    remap = np.empty(k, dtype=int)
    for new, old in enumerate(order):
        remap[old] = new
    return remap[labels], centroids[np.asarray(order, dtype=int)].copy(), n_iter, attempt


def _row_sse(x: np.ndarray, centroids: np.ndarray, labels: np.ndarray) -> np.ndarray:
    out = np.empty(x.shape[0], dtype=float)
    for row in range(int(x.shape[0])):
        out[row] = _sqdist(x[row], centroids[int(labels[row])])
    return out


def _silhouette(x: np.ndarray, labels: np.ndarray, k: int) -> float:
    n = int(x.shape[0])
    if k < 2 or n < 2:
        return math.nan
    sizes = np.bincount(labels, minlength=k)
    if np.any(sizes == 0):
        return math.nan
    scores = np.empty(n, dtype=float)
    members = [np.flatnonzero(labels == cluster) for cluster in range(k)]
    for row in range(n):
        own = int(labels[row])
        others = members[own]
        if others.size <= 1:
            scores[row] = 0.0
            continue
        a_sum = 0.0
        for other in others:
            if int(other) == row:
                continue
            a_sum += _euclidean(x[row], x[int(other)])
        a = a_sum / float(others.size - 1)
        b = math.inf
        for cluster in range(k):
            if cluster == own:
                continue
            b_sum = 0.0
            group = members[cluster]
            for other in group:
                b_sum += _euclidean(x[row], x[int(other)])
            b = min(b, b_sum / float(group.size))
        denom = max(a, b)
        scores[row] = 0.0 if denom == 0.0 else (b - a) / denom
    return _mean_1d(scores)


def _normalize(raw: np.ndarray, method: str, dates: Sequence[str]) -> np.ndarray:
    if method == "none":
        return np.array(raw, dtype=float, copy=True)
    if method == "peak":
        scale = np.max(raw, axis=1)
        bad = np.flatnonzero(scale <= 0.0)
        if bad.size:
            raise ValueError(
                f"peak normalization needs a positive daily peak (date {dates[int(bad[0])]})"
            )
    else:
        scale = np.array([_mean_1d(raw[row]) for row in range(raw.shape[0])], dtype=float)
        bad = np.flatnonzero(scale <= 0.0)
        if bad.size:
            raise ValueError(
                f"mean normalization needs a positive daily mean (date {dates[int(bad[0])]})"
            )
    return raw / scale[:, None]


def _resolve(
    source: object,
    power: object,
    *,
    time_col: object,
    power_col: object,
    dates: object,
    day: object,
    csv_path: object,
    step_minutes: float | None,
) -> tuple[np.ndarray, list[str], np.ndarray, float, bool, int, int, int]:
    if isinstance(source, str) and _is_parameter_name(source):
        raise ValueError(
            f"{source.strip()!r} is a parameter name. Pass the CSV path as the first argument or as csv_path="
        )
    if power is not None:
        return _from_series(source, power, dates, day, csv_path, time_col, power_col, step_minutes)
    if _is_profile_input(source):
        return _from_matrix(source, dates, day, csv_path, time_col, power_col, step_minutes)
    return _from_csv(source, dates, day, csv_path, time_col, power_col, step_minutes)


def _from_series(
    source: object,
    power: object,
    dates: object,
    day: object,
    csv_path: object,
    time_col: object,
    power_col: object,
    step_minutes: float | None,
) -> tuple[np.ndarray, list[str], np.ndarray, float, bool, int, int, int]:
    if _path_text(csv_path) is not None:
        raise ValueError("pass time and power, or a CSV path, not both")
    if dates is not None:
        raise ValueError("dates applies to a profile matrix, not a time series")
    if _given(time_col) or _given(power_col):
        raise ValueError("time_col and power_col apply to a CSV, not to time and power vectors")
    samples, n_duplicates = _samples_from_vectors(source, power, day)
    return _pack_days(_group_days(samples), step_minutes, len(samples), 0, n_duplicates)


def _from_matrix(
    source: object,
    dates: object,
    day: object,
    csv_path: object,
    time_col: object,
    power_col: object,
    step_minutes: float | None,
) -> tuple[np.ndarray, list[str], np.ndarray, float, bool, int, int, int]:
    if _path_text(csv_path) is not None:
        raise ValueError("pass a profile matrix or a CSV path, not both")
    if _given(day):
        raise ValueError("day applies to numeric minutes, not a profile matrix")
    if _given(time_col) or _given(power_col):
        raise ValueError("time_col and power_col apply to a CSV, not to a profile matrix")
    if step_minutes is not None:
        raise ValueError("step_minutes applies to a time series, not a profile matrix")
    raw = _coerce_matrix(source)
    n_days, n_times = int(raw.shape[0]), int(raw.shape[1])
    labels = _matrix_dates(dates, n_days)
    step = 1440.0 / n_times
    minute = np.arange(n_times, dtype=float) * step
    return raw, labels, minute, step, False, n_days * n_times, 0, 0


def _from_csv(
    source: object,
    dates: object,
    day: object,
    csv_path: object,
    time_col: object,
    power_col: object,
    step_minutes: float | None,
) -> tuple[np.ndarray, list[str], np.ndarray, float, bool, int, int, int]:
    if dates is not None:
        raise ValueError("dates applies to a profile matrix, not a CSV")
    if _given(day):
        raise ValueError("day applies to numeric minutes, not a CSV")
    path = _path_text(csv_path)
    if isinstance(source, (str, Path)) and str(source).strip() != "":
        if path is not None:
            raise ValueError("pass a CSV path once, either positionally or as csv_path=")
        path = str(source).strip()
    elif source is not None:
        raise TypeError("source must be a CSV path, a profile matrix, or time with power")
    if path is None:
        raise ValueError("pass a CSV path, a profile matrix, or time and power")
    rows, n_missing = _read_csv_rows(Path(path), time_col, power_col)
    samples, n_duplicates = _clean_samples(rows)
    if not samples:
        raise ValueError("No power samples remain after cleaning")
    return _pack_days(_group_days(samples), step_minutes, len(samples), n_missing, n_duplicates)


def _pack_days(
    days: list[tuple[str, np.ndarray, np.ndarray]],
    step_minutes: float | None,
    n_rows: int,
    n_missing: int,
    n_duplicates: int,
) -> tuple[np.ndarray, list[str], np.ndarray, float, bool, int, int, int]:
    if not days:
        raise ValueError("No power samples remain after cleaning")
    for date, minute, _power in days:
        if minute.size < 2:
            raise ValueError(f"each day needs at least 2 samples (date {date})")
        if np.any(np.diff(minute) <= 0.0):
            raise ValueError(f"timestamps on {date} must be strictly increasing")
    minute, raw, step, resampled = _align(days, step_minutes)
    return raw, [date for date, _, _ in days], minute, step, resampled, n_rows, n_missing, n_duplicates


def _align(
    days: list[tuple[str, np.ndarray, np.ndarray]],
    step_minutes: float | None,
) -> tuple[np.ndarray, np.ndarray, float, bool]:
    grid0 = days[0][1]
    same = all(
        minute.shape == grid0.shape and np.allclose(minute, grid0, rtol=0.0, atol=1e-6)
        for _date, minute, _power in days
    )
    if same and _step_matches(grid0, step_minutes):
        grid = np.array(grid0, dtype=float, copy=True)
        raw = np.vstack([np.array(power, dtype=float, copy=True) for _date, _minute, power in days])
        return grid, raw, _reported_step(grid, step_minutes), False
    step = _median_step(days) if step_minutes is None else float(step_minutes)
    grid = _full_day_grid(step)
    raw = np.vstack([_interp_day(date, minute, power, grid) for date, minute, power in days])
    return grid, raw, step, True


def _step_matches(grid: np.ndarray, step_minutes: float | None) -> bool:
    if step_minutes is None:
        return True
    if grid.size < 2:
        return False
    return bool(np.max(np.abs(np.diff(grid) - step_minutes)) <= 1e-6 * max(step_minutes, 1.0))


def _reported_step(grid: np.ndarray, step_minutes: float | None) -> float:
    if step_minutes is not None:
        return float(step_minutes)
    return _median(np.diff(grid))


def _median_step(days: list[tuple[str, np.ndarray, np.ndarray]]) -> float:
    parts = [np.diff(minute) for _date, minute, _power in days if minute.size >= 2]
    if not parts:
        raise ValueError("each day needs at least 2 samples")
    return _median(np.concatenate(parts))


def _full_day_grid(step: float) -> np.ndarray:
    n_steps = int(round(1440.0 / step))
    if n_steps < 2 or abs(n_steps * step - 1440.0) > 1e-6 * max(step, 1.0):
        raise ValueError("step_minutes must divide 24 hours into at least 2 samples")
    return step * np.arange(n_steps, dtype=float)


def _interp_day(date: str, minute: np.ndarray, power: np.ndarray, grid: np.ndarray) -> np.ndarray:
    if float(minute[0]) > float(grid[0]) + 1e-6 or float(minute[-1]) < float(grid[-1]) - 1e-6:
        raise ValueError(
            f"day {date} does not cover the daily grid ({_clock(float(grid[0]))} through {_clock(float(grid[-1]))})"
        )
    return np.interp(grid, minute, power)


def _is_profile_input(source: object) -> bool:
    if source is None or isinstance(source, (str, bytes, Path, datetime)):
        return False
    if isinstance(source, np.ndarray) and source.ndim in (1, 2) and source.dtype != object:
        return np.issubdtype(source.dtype, np.number)
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes)) and len(source) > 0:
        return _is_numeric_vector(source) or _is_matrix(source)
    return False


def _is_matrix(value: object) -> bool:
    if isinstance(value, np.ndarray):
        return value.ndim == 2
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) > 0:
        row = value[0]
        if isinstance(row, datetime):
            return False
        if isinstance(row, np.ndarray) and row.ndim == 1:
            return True
        if isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
            return len(row) > 0 and not isinstance(row[0], str)
    return False


def _is_numeric_vector(value: object) -> bool:
    if isinstance(value, (str, bytes, Path, datetime)):
        return False
    if isinstance(value, np.ndarray):
        return value.ndim == 1 and np.issubdtype(value.dtype, np.number)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) > 0:
        return all(isinstance(item, Real) and not isinstance(item, bool) for item in value)
    return False


def _coerce_matrix(source: object) -> np.ndarray:
    if _is_numeric_vector(source):
        array = np.asarray(source, dtype=float).reshape(1, -1)
    else:
        try:
            array = np.asarray(source, dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError("profile matrix must have shape (days, times)") from exc
    if array.ndim != 2:
        raise ValueError("profile matrix must have shape (days, times)")
    if array.shape[0] < 1 or array.shape[1] < 2:
        raise ValueError("a daily profile needs at least 2 samples")
    if not np.all(np.isfinite(array)):
        raise ValueError("profiles must be finite")
    return np.ascontiguousarray(array, dtype=float)


def _matrix_dates(dates: object, n_days: int) -> list[str]:
    if dates is None:
        return [f"day-{index + 1:02d}" for index in range(n_days)]
    if isinstance(dates, (str, bytes)):
        raise ValueError("dates must have one entry per day")
    if not isinstance(dates, Sequence):
        raise ValueError("dates must have one entry per day")
    labels = [str(item).strip() for item in dates]
    if len(labels) != n_days:
        raise ValueError("dates must have one entry per day")
    if any(item == "" for item in labels):
        raise ValueError("dates must not be blank")
    return labels


def _samples_from_vectors(
    time: object,
    power: object,
    day: object,
) -> tuple[list[tuple[int, int, int, float, float]], int]:
    stamps = _time_parts(time, day)
    values = _power_vector(power)
    if len(stamps) != len(values):
        raise ValueError("time and power must have the same length")
    paired = [
        (stamp[0], stamp[1], stamp[2], stamp[3], float(values[index])) for index, stamp in enumerate(stamps)
    ]
    samples, n_duplicates = _clean_samples(paired)
    if not samples:
        raise ValueError("time must not be empty")
    return samples, n_duplicates


def _time_parts(time: object, day: object) -> list[tuple[int, int, int, float]]:
    if isinstance(time, np.ndarray) and np.issubdtype(time.dtype, np.datetime64):
        if _given(day):
            raise ValueError("day applies to numeric minutes, not to timestamps")
        return [_parts_from_datetime(_datetime64_to_datetime(item)) for item in time]
    if _is_numeric_vector(time):
        minutes = _power_vector(time)
        if np.any((minutes < 0.0) | (minutes >= 1440.0)):
            raise ValueError("numeric minutes must be in [0, 1440)")
        label = _parse_day(DEFAULT_DAY if not _given(day) else str(day))
        year, month, day_number = int(label[0:4]), int(label[5:7]), int(label[8:10])
        return [(year, month, day_number, float(minute)) for minute in minutes]
    if _given(day):
        raise ValueError("day applies to numeric minutes, not to timestamps")
    items = _as_list(time)
    if not items:
        raise ValueError("time must not be empty")
    parts: list[tuple[int, int, int, float]] = []
    for item in items:
        if isinstance(item, datetime):
            parts.append(_parts_from_datetime(item))
        elif isinstance(item, np.datetime64):
            parts.append(_parts_from_datetime(_datetime64_to_datetime(item)))
        elif isinstance(item, str):
            parts.append(_parse_timestamp(item))
        else:
            raise ValueError("timestamp entries must be strings or datetimes")
    return parts


def _as_list(value: object) -> list[object]:
    if isinstance(value, np.ndarray):
        if value.ndim != 1:
            raise ValueError("time must be a vector")
        return [item for item in value]
    if isinstance(value, (str, datetime)):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    raise ValueError("time must be a vector of timestamps or minutes")


def _power_vector(value: object) -> np.ndarray:
    if isinstance(value, (str, bytes, Path)):
        raise ValueError("power must be a numeric vector")
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("power must be a numeric vector") from exc
    if array.ndim != 1:
        raise ValueError("power must be a numeric vector")
    if array.size == 0:
        raise ValueError("power must not be empty")
    if not np.all(np.isfinite(array)):
        raise ValueError("power must be finite")
    return np.ascontiguousarray(array, dtype=float)


def _datetime64_to_datetime(value: np.datetime64) -> datetime:
    converted = value.astype("datetime64[us]").item()
    if not isinstance(converted, datetime):
        raise ValueError("could not parse timestamp")
    return converted


def _parts_from_datetime(value: datetime) -> tuple[int, int, int, float]:
    if value.tzinfo is not None:
        raise ValueError("timestamps must be naive local time")
    minute = value.hour * 60.0 + value.minute + value.second / 60.0 + value.microsecond / 60_000_000.0
    if not _valid_date(value.year, value.month, value.day):
        raise ValueError("could not parse timestamp")
    return value.year, value.month, value.day, minute


def _parse_timestamp(text: str) -> tuple[int, int, int, float]:
    raw = text.strip()
    if len(raw) not in (16, 19) or raw[4] not in "-/" or raw[7] != raw[4] or raw[10] not in " T":
        raise ValueError(f"could not parse timestamp {text!r}")
    if not (raw[0:4].isdigit() and raw[5:7].isdigit() and raw[8:10].isdigit()):
        raise ValueError(f"could not parse timestamp {text!r}")
    year = int(raw[0:4])
    month = int(raw[5:7])
    day = int(raw[8:10])
    clock = raw[11:]
    if len(clock) == 5:
        if clock[2] != ":" or not (clock[0:2].isdigit() and clock[3:5].isdigit()):
            raise ValueError(f"could not parse timestamp {text!r}")
        hour = int(clock[0:2])
        minute = int(clock[3:5])
        second = 0
    elif len(clock) == 8:
        if clock[2] != ":" or clock[5] != ":" or not (
            clock[0:2].isdigit() and clock[3:5].isdigit() and clock[6:8].isdigit()
        ):
            raise ValueError(f"could not parse timestamp {text!r}")
        hour = int(clock[0:2])
        minute = int(clock[3:5])
        second = int(clock[6:8])
    else:
        raise ValueError(f"could not parse timestamp {text!r}")
    if hour > 23 or minute > 59 or second > 59 or not _valid_date(year, month, day):
        raise ValueError(f"could not parse timestamp {text!r}")
    return year, month, day, hour * 60.0 + minute + second / 60.0


def _parse_day(text: str) -> str:
    raw = str(text).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ValueError("day must be YYYY-MM-DD")
    year, month, day = int(raw[0:4]), int(raw[5:7]), int(raw[8:10])
    if not _valid_date(year, month, day):
        raise ValueError("day must be a real calendar date")
    return f"{year:04d}-{month:02d}-{day:02d}"


def _read_csv_rows(
    path: Path,
    time_col: object,
    power_col: object,
) -> tuple[list[tuple[int, int, int, float, float]], int]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    if text.strip() == "":
        raise ValueError(f"CSV is empty: {path}")
    first = next((line for line in text.splitlines() if line.strip()), "")
    delimiter = ";" if first.count(";") > first.count(",") else ","
    table = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter) if any(cell.strip() for cell in row)]
    if not table:
        raise ValueError(f"CSV is empty: {path}")
    columns = [cell.strip() for cell in table[0]]
    time_name = _resolve_column(columns, time_col, _TIME_ALIASES, "time")
    power_name = _resolve_column(columns, power_col, _POWER_ALIASES, "power")
    if time_name == power_name:
        raise ValueError("time and power columns must be different")
    time_index = columns.index(time_name)
    power_index = columns.index(power_name)
    rows: list[tuple[int, int, int, float, float]] = []
    n_missing = 0
    for raw in table[1:]:
        if all(cell.strip() == "" for cell in raw):
            continue
        padded = list(raw) + [""] * (len(columns) - len(raw))
        time_text = padded[time_index].strip()
        power_text = padded[power_index].strip()
        if time_text == "":
            raise ValueError("a row is missing its timestamp")
        if power_text == "" or power_text.lower() == "nan":
            n_missing += 1
            continue
        parts = _parse_timestamp(time_text)
        try:
            value = float(power_text)
        except ValueError as exc:
            raise ValueError("power must be finite") from exc
        if not math.isfinite(value):
            raise ValueError("power must be finite")
        rows.append((parts[0], parts[1], parts[2], parts[3], value))
    if not rows and n_missing == 0:
        raise ValueError(f"CSV has no data rows: {path}")
    return rows, n_missing


def _clean_samples(
    rows: Sequence[tuple[int, int, int, float, float]],
) -> tuple[list[tuple[int, int, int, float, float]], int]:
    ordered = sorted(enumerate(rows), key=lambda item: (item[1][0], item[1][1], item[1][2], item[1][3], item[0]))
    kept: list[tuple[int, int, int, float, float]] = []
    duplicates = 0
    for _index, item in ordered:
        if kept:
            previous = kept[-1]
            same_day = previous[0] == item[0] and previous[1] == item[1] and previous[2] == item[2]
            if same_day and abs(previous[3] - item[3]) <= 1e-9:
                duplicates += 1
                continue
        kept.append(item)
    return kept, duplicates


def _group_days(
    samples: Sequence[tuple[int, int, int, float, float]],
) -> list[tuple[str, np.ndarray, np.ndarray]]:
    groups: list[tuple[str, list[float], list[float]]] = []
    current = ""
    for year, month, day, minute, power in samples:
        key = f"{year:04d}-{month:02d}-{day:02d}"
        if not groups or key != current:
            groups.append((key, [], []))
            current = key
        groups[-1][1].append(minute)
        groups[-1][2].append(power)
    return [
        (key, np.ascontiguousarray(minutes, dtype=float), np.ascontiguousarray(values, dtype=float))
        for key, minutes, values in groups
    ]


def _resolve_column(
    columns: Sequence[str],
    requested: object,
    aliases: Sequence[str],
    kind: str,
) -> str:
    pairs = [(_norm_key(column), column) for column in columns if column != ""]
    if _given(requested):
        req = str(requested).strip()
        for column in columns:
            if column == req:
                return column
        req_norm = _norm_key(req)
        for norm, column in pairs:
            if norm == req_norm:
                return column
        known = ", ".join(column for column in columns if column != "")
        raise ValueError(f"Column {req!r} not found for {kind}. Available: {known}")
    for alias in aliases:
        alias_norm = _norm_key(alias)
        for norm, column in pairs:
            if norm == alias_norm:
                return column
    known = ", ".join(column for column in columns if column != "")
    raise ValueError(f"Could not find a {kind} column. Pass {kind}_col explicitly. Available: {known}")


def _format_result(
    dates: Sequence[str],
    labels: np.ndarray,
    peak_kw: np.ndarray,
    day_sse: np.ndarray,
    cluster_sizes: np.ndarray,
    centroid_peak_hour: np.ndarray,
    mean_peak_kw: np.ndarray,
    *,
    k: int,
    seed: int,
    n_init: int,
    normalize: str,
    sse: float,
    silhouette: float,
    n_iter: int,
    attempt: int,
    step_minutes: float,
    resampled: bool,
    n_rows: int,
    n_missing: int,
    n_duplicates: int,
) -> str:
    header = (
        f"days={len(dates)}  k={k}  seed={seed}  n_init={n_init}  normalize={normalize}  "
        f"sse={_compact(sse)}  silhouette={_compact(silhouette)}  n_iter={n_iter}  "
        f"attempt={attempt}  step_min={_compact(step_minutes)}  resampled={1 if resampled else 0}"
    )
    rows = f"rows={n_rows}  missing={n_missing}  duplicates={n_duplicates}"
    clusters = [
        (
            f"cluster={index + 1}  n={int(cluster_sizes[index])}  "
            f"peak_hour={_compact(float(centroid_peak_hour[index]))}  "
            f"mean_peak_kw={_compact(float(mean_peak_kw[index]))}"
        )
        for index in range(k)
    ]
    days = [
        (
            f"date={dates[index]}  label={int(labels[index])}  "
            f"peak_kw={_compact(float(peak_kw[index]))}  day_sse={_compact(float(day_sse[index]))}"
        )
        for index in range(len(dates))
    ]
    return "\n\n".join([header, rows, "\n".join(clusters), "\n".join(days)])


def _write_assignments(path: Path, result: LoadKMeansResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "label", "peak_kw", "day_sse"])
        for index, date in enumerate(result.dates):
            writer.writerow(
                [
                    date,
                    str(int(result.labels[index])),
                    _csv_num(float(result.peak_kw[index])),
                    _csv_num(float(result.day_sse[index])),
                ]
            )


def _render_figure(result: LoadKMeansResult, output_png: str | None, show: bool) -> object | None:
    import matplotlib.pyplot as plt

    style = {
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#444444",
    }
    with plt.rc_context(style):
        fig, axes = plt.subplots(2, 1, figsize=(10.4, 8.2), sharex=True)
        profile_axis, centroid_axis = axes
        for cluster in range(result.k):
            color = _PALETTE[cluster % len(_PALETTE)]
            member = np.flatnonzero(result.labels == cluster + 1)
            legend = f"cluster {cluster + 1} (n={int(result.cluster_sizes[cluster])})"
            for order, row in enumerate(member):
                profile_axis.plot(
                    result.hour,
                    result.profiles[row],
                    color=color,
                    lw=1.15,
                    alpha=0.45,
                    label=legend if order == 0 else None,
                )
            centroid_axis.plot(result.hour, result.centroids[cluster], color=color, lw=2.3, label=legend)
            profile_axis.plot(
                result.hour,
                result.centroids[cluster],
                color=color,
                lw=2.4,
                solid_capstyle="round",
            )
        silhouette = _compact(result.silhouette)
        fig.suptitle(
            f"k-means daily load    k={result.k}    SSE={_compact(result.sse)}    silhouette={silhouette}",
            fontsize=13,
        )
        ylabel = _Y_LABEL[result.normalize]
        _style_axis(profile_axis, "Normalized daily profiles", ylabel, result.hour)
        _style_axis(centroid_axis, "Typical day centroids", ylabel, result.hour)
        centroid_axis.set_xlabel("Hour of day")
        fig.tight_layout()
        if output_png is not None:
            destination = Path(output_png)
            destination.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(destination, dpi=150, bbox_inches="tight")
        if show:
            plt.show()
            return fig
        plt.close(fig)
        return None


def _style_axis(axis: object, title: str, ylabel: str, hour: np.ndarray) -> None:
    axis.set_title(title)
    axis.set_ylabel(ylabel)
    axis.grid(True, color="#d0d0d0", linewidth=0.6)
    axis.legend(loc="upper left", frameon=True, edgecolor="#cccccc")
    if hour.size:
        span = float(hour[-1] - hour[0]) if hour.size > 1 else 1.0
        pad = 0.04 * span if span > 0.0 else 0.5
        axis.set_xlim(float(hour[0]) - pad, float(hour[-1]) + pad)


def _sqdist_to_centers(x: np.ndarray, centers: np.ndarray) -> np.ndarray:
    d2 = np.full(x.shape[0], np.inf)
    for center in centers:
        for row in range(int(x.shape[0])):
            value = _sqdist(x[row], center)
            if value < d2[row]:
                d2[row] = value
    return d2


def _sqdist(left: np.ndarray, right: np.ndarray) -> float:
    acc = 0.0
    for index in range(int(left.shape[0])):
        diff = float(left[index]) - float(right[index])
        acc += diff * diff
    return acc


def _euclidean(left: np.ndarray, right: np.ndarray) -> float:
    return math.sqrt(_sqdist(left, right))


def _mean_rows(block: np.ndarray) -> np.ndarray:
    acc = np.zeros(block.shape[1], dtype=float)
    for row in block:
        for index in range(int(row.shape[0])):
            acc[index] += float(row[index])
    return acc / float(block.shape[0])


def _mean_1d(values: np.ndarray | Sequence[float]) -> float:
    acc = 0.0
    count = 0
    for value in values:
        acc += float(value)
        count += 1
    if count == 0:
        return math.nan
    return acc / float(count)


def _sum_1d(values: np.ndarray) -> float:
    acc = 0.0
    for value in values:
        acc += float(value)
    return acc


def _median(values: np.ndarray) -> float:
    ordered = np.sort(np.asarray(values, dtype=float))
    count = int(ordered.size)
    mid = count // 2
    if count % 2 == 1:
        return float(ordered[mid])
    return float(0.5 * (ordered[mid - 1] + ordered[mid]))


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _valid_date(year: int, month: int, day: int) -> bool:
    if year < 1 or year > 9999 or month < 1 or month > 12:
        return False
    limit = _MONTH_DAYS[month]
    if month == 2 and _leap(year):
        limit = 29
    return 1 <= day <= limit


def _clock(minutes: float) -> str:
    if not math.isfinite(minutes):
        return "nan"
    total = int(math.floor(minutes * 60.0 + 0.5)) % 86400
    hour = total // 3600
    minute = (total % 3600) // 60
    second = total % 60
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _compact(value: float) -> str:
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        value = float(value)
    value = float(value)
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    text = f"{value:.6g}"
    if "e" not in text and "E" not in text:
        return text
    if abs(value) >= 1.0 and abs(value - round(value)) <= 1e-6 * max(abs(value), 1.0):
        return f"{value:.0f}"
    return text


def _csv_num(value: float) -> str:
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return f"{value:.12g}"


def _norm_key(value: object) -> str:
    return re.sub(r"[\s_\-()（）]", "", str(value).strip().lower())


def _normalize_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("normalize must be peak, mean, or none")
    name = value.strip().lower()
    if name not in _NORMALIZE:
        raise ValueError("normalize must be peak, mean, or none")
    return name


def _integral(name: str, value: object, *, minimum: int, message: str) -> int:
    if isinstance(value, bool):
        raise ValueError(message)
    if isinstance(value, (int, np.integer)):
        number = int(value)
    elif isinstance(value, (float, np.floating)) and math.isfinite(float(value)) and float(value).is_integer():
        number = int(value)
    else:
        raise ValueError(message)
    if number < minimum:
        raise ValueError(message)
    return number


def _positive(label: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a positive finite number")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be a positive finite number")
    return number


def _as_bool(label: str, value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool) and int(value) in (0, 1):
        return bool(int(value))
    raise ValueError(f"{label} must be true or false")


def _given(value: object) -> bool:
    return value is not None and str(value).strip() != ""


def _path_text(value: object) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def _is_parameter_name(value: str) -> bool:
    return value.strip().lower() in _PARAM_NAMES
