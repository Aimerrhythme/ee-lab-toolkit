"""Clean a timestamped load CSV and draw a standard load figure.

The pipeline matches ``matlab/load_csv_plot.m``:

1. Read the table and resolve the timestamp and load columns.
2. Parse timestamps, sort, and drop duplicate timestamps (keep the first).
3. Count missing load values.
4. Drop missing rows when ``fill_method`` is ``drop``.
5. Flag spike outliers (IQR or z-score).
6. Fill missing samples and, unless dropping, interpolate across spikes.
7. Optionally aggregate a daily mean on the cleaned series.
8. Plot a clean figure and optionally save a PNG.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

TIME_ALIAS_PRIORITY = (
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
LOAD_ALIAS_PRIORITY = (
    "load_kw",
    "power_kw",
    "p_kw",
    "demand_kw",
    "active_power",
    "load_power",
    "load",
    "power",
    "kw",
    "p",
    "负荷(kw)",
    "负荷kw",
    "有功功率",
    "有功",
    "负荷",
)

AGG_CHOICES = ("none", "mean", "daily_mean")
OUTLIER_CHOICES = ("iqr", "zscore", "none")
FILL_CHOICES = ("interpolate", "ffill", "drop")
MIN_OUTLIER_SAMPLES = 4
MAX_ANNOTATIONS = 8

_LINE = "#1f4e79"
_SPIKE = "#c0392b"
_MEAN = "#e67e22"
_DAILY = "#3d7a6a"


@dataclass
class LoadCsvPlotResult:
    """Cleaned load series and the optional daily mean.

    Fields match the struct returned by ``load_csv_plot.m``.
    ``daily_mean`` has columns ``date`` and ``mean_kw``. It is empty unless
    ``agg`` is ``daily_mean``. ``mean_kw`` is always the mean of ``load_kw``.
    """

    time: pd.Series
    load_kw: pd.Series
    load_raw_kw: pd.Series
    is_outlier: pd.Series
    n_rows: int
    n_missing: int
    n_outliers: int
    mean_kw: float
    daily_mean: pd.DataFrame
    agg: str
    output_png: str | None
    fig: object | None = None


def load_csv_plot(
    csv_path: str | Path,
    *,
    time_col: str | None = None,
    load_col: str | None = None,
    agg: str = "none",
    outlier_method: str = "iqr",
    z_thresh: float = 3.0,
    iqr_k: float = 1.5,
    fill_method: str = "interpolate",
    output_png: str | Path | None = None,
    show: bool = False,
) -> LoadCsvPlotResult:
    """Clean a load CSV and plot a standard figure.

    Parameters are the same keys the MATLAB function accepts as name-value
    arguments (``time_col``, ``agg``, ``outlier_method``, and so on).
    """

    agg_key = _choice("agg", agg, AGG_CHOICES)
    method_key = _choice("outlier_method", outlier_method, OUTLIER_CHOICES)
    fill_key = _choice("fill_method", fill_method, FILL_CHOICES)
    z_thresh = float(z_thresh)
    iqr_k = float(iqr_k)
    if z_thresh <= 0:
        raise ValueError("z_thresh must be positive")
    if iqr_k < 0:
        raise ValueError("iqr_k must be >= 0")

    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"CSV not found: {path}")

    time, load_raw, n_missing = _read_load_frame(path, time_col, load_col)
    if fill_key == "drop":
        keep = np.isfinite(load_raw)
        time = time.loc[keep].reset_index(drop=True)
        load_raw = load_raw.loc[keep].reset_index(drop=True)
    if len(time) == 0:
        raise ValueError("No load rows remain after cleaning.")

    outlier_mask = _flag_outliers(load_raw.to_numpy(dtype=float), method_key, z_thresh, iqr_k)
    load_kw = _cleaned_load(time, load_raw.to_numpy(dtype=float), outlier_mask, fill_key)
    mean_kw = float(np.nanmean(load_kw)) if np.isfinite(load_kw).any() else float("nan")
    if agg_key == "daily_mean":
        daily = _daily_mean(time, load_kw)
    else:
        daily = _empty_daily()

    png_text = None if output_png is None or str(output_png).strip() == "" else str(output_png)
    fig = _render_figure(
        time=pd.to_datetime(time),
        load_kw=load_kw,
        load_raw=load_raw.to_numpy(dtype=float),
        is_outlier=outlier_mask,
        mean_kw=mean_kw,
        daily=daily,
        agg=agg_key,
        output_png=png_text,
        show=bool(show),
    )
    return LoadCsvPlotResult(
        time=pd.Series(pd.to_datetime(time).to_numpy(), name="time"),
        load_kw=pd.Series(load_kw, name="load_kw"),
        load_raw_kw=pd.Series(load_raw.to_numpy(dtype=float), name="load_raw_kw"),
        is_outlier=pd.Series(outlier_mask, name="is_outlier"),
        n_rows=len(time),
        n_missing=int(n_missing),
        n_outliers=int(outlier_mask.sum()),
        mean_kw=mean_kw,
        daily_mean=daily,
        agg=agg_key,
        output_png=png_text,
        fig=fig,
    )


def _choice(name: str, value: object, allowed: tuple[str, ...]) -> str:
    key = str(value).strip().lower()
    if key not in allowed:
        joined = ", ".join(allowed)
        raise ValueError(f"{name} must be one of: {joined}")
    return key


def _normalize_name(name: object) -> str:
    text = str(name).strip().lower()
    return re.sub(r"[\s_\-()（）]", "", text)


def _resolve_column(columns: list[str], requested: str | None, priority: tuple[str, ...], kind: str) -> str:
    pairs = [(_normalize_name(column), column) for column in columns]
    if requested is not None and str(requested).strip() != "":
        req = str(requested).strip()
        for column in columns:
            if column == req:
                return column
        req_norm = _normalize_name(req)
        for norm, column in pairs:
            if norm == req_norm:
                return column
        known = ", ".join(columns)
        raise ValueError(f"Column {req!r} not found for {kind}. Available: {known}")

    for alias in priority:
        alias_norm = _normalize_name(alias)
        for norm, column in pairs:
            if norm == alias_norm:
                return column
    known = ", ".join(columns)
    raise ValueError(f"Could not find a {kind} column. Pass {kind}_col explicitly. Available: {known}")


def _read_load_frame(
    path: Path,
    time_col: str | None,
    load_col: str | None,
) -> tuple[pd.Series, pd.Series, int]:
    try:
        table = pd.read_csv(path, encoding="utf-8-sig", sep=None, engine="python", skipinitialspace=True)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"CSV is empty: {path}") from exc
    if table.empty or len(table.columns) == 0:
        raise ValueError(f"CSV is empty: {path}")

    columns = [str(column).strip() for column in table.columns]
    table.columns = columns
    resolved_time = _resolve_column(columns, time_col, TIME_ALIAS_PRIORITY, "time")
    resolved_load = _resolve_column(columns, load_col, LOAD_ALIAS_PRIORITY, "load")
    if resolved_time == resolved_load:
        raise ValueError("time and load columns resolved to the same field")

    time = pd.to_datetime(table[resolved_time], errors="coerce")
    load = pd.to_numeric(table[resolved_load], errors="coerce")
    valid_time = time.notna()
    time = time.loc[valid_time].reset_index(drop=True)
    load = load.loc[valid_time].reset_index(drop=True)
    if len(time) == 0:
        raise ValueError("No valid timestamps in CSV.")

    order = np.argsort(time.to_numpy(), kind="mergesort")
    time = time.iloc[order].reset_index(drop=True)
    load = load.iloc[order].reset_index(drop=True)
    frame = pd.DataFrame({"time": time, "load_raw_kw": load.to_numpy(dtype=float)})
    frame = frame.drop_duplicates(subset="time", keep="first").reset_index(drop=True)
    raw = np.array(frame["load_raw_kw"].to_numpy(), dtype=float, copy=True)
    raw[~np.isfinite(raw)] = np.nan
    n_missing = int(np.isnan(raw).sum())
    return frame["time"], pd.Series(raw, name="load_raw_kw"), n_missing


def _flag_outliers(values: np.ndarray, method: str, z_thresh: float, iqr_k: float) -> np.ndarray:
    mask = np.zeros(len(values), dtype=bool)
    finite = np.isfinite(values)
    if method == "none" or int(finite.sum()) < MIN_OUTLIER_SAMPLES:
        return mask
    sample = values[finite]
    if method == "iqr":
        q1, q3 = np.quantile(sample, [0.25, 0.75], method="linear")
        span = float(q3 - q1)
        if span == 0:
            return mask
        low = float(q1) - iqr_k * span
        high = float(q3) + iqr_k * span
        flagged = (sample < low) | (sample > high)
    else:
        std = float(np.std(sample, ddof=1))
        if std == 0:
            return mask
        center = float(np.mean(sample))
        flagged = np.abs((sample - center) / std) > z_thresh
    mask[finite] = flagged
    return mask


def _fill_linear_time(time: pd.Series, values: np.ndarray) -> np.ndarray:
    """Linear fill in time. Ends use the nearest finite sample (same as ``np.interp``)."""

    filled = np.asarray(values, dtype=float).copy()
    good = np.isfinite(filled)
    n_good = int(good.sum())
    if n_good == 0:
        return filled
    if n_good == 1:
        filled[~good] = filled[good][0]
        return filled
    origin = pd.Timestamp(pd.to_datetime(time).iloc[0])
    seconds = (pd.to_datetime(time) - origin).dt.total_seconds().to_numpy(dtype=float)
    filled[~good] = np.interp(seconds[~good], seconds[good], filled[good])
    return filled


def _cleaned_load(time: pd.Series, load_raw: np.ndarray, is_outlier: np.ndarray, fill_method: str) -> np.ndarray:
    if fill_method == "drop":
        return load_raw.copy()
    work = load_raw.copy()
    work[is_outlier] = np.nan
    if fill_method == "ffill":
        series = pd.Series(work)
        return series.ffill().bfill().to_numpy(dtype=float)
    return _fill_linear_time(time, work)


def _empty_daily() -> pd.DataFrame:
    return pd.DataFrame({"date": pd.to_datetime([]), "mean_kw": pd.Series(dtype=float)})


def _daily_mean(time: pd.Series, load_kw: np.ndarray) -> pd.DataFrame:
    frame = pd.DataFrame({"time": pd.to_datetime(time), "load_kw": load_kw})
    grouped = frame.groupby(frame["time"].dt.floor("D"), sort=True)["load_kw"].mean()
    daily = grouped.reset_index()
    daily.columns = ["date", "mean_kw"]
    return daily


def _format_kw(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return f"raw {value:.0f} kW"
    return f"raw {value:.1f} kW"


def _render_figure(
    *,
    time: pd.Series,
    load_kw: np.ndarray,
    load_raw: np.ndarray,
    is_outlier: np.ndarray,
    mean_kw: float,
    daily: pd.DataFrame,
    agg: str,
    output_png: str | None,
    show: bool,
) -> object | None:
    import matplotlib.dates as mdates
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
    use_daily = agg == "daily_mean"
    with plt.rc_context(style):
        if use_daily:
            fig, axes = plt.subplots(
                2,
                1,
                figsize=(10.2, 6.5),
                gridspec_kw={"height_ratios": [2.3, 1.0]},
            )
            ax = axes[0]
            ax_daily = axes[1]
        else:
            fig, ax = plt.subplots(figsize=(10.2, 4.4))
            ax_daily = None

        ax.plot(time, load_kw, color=_LINE, linewidth=1.6, label="Cleaned load", zorder=2)
        _mark_outliers(ax, time, load_kw, load_raw, is_outlier)
        if agg == "mean" and np.isfinite(mean_kw):
            ax.axhline(mean_kw, color=_MEAN, linestyle="--", linewidth=1.2, label="Mean", zorder=1)
        _style_time_axis(ax, mdates)
        ax.set_title("Load profile (cleaned)")
        ax.set_ylabel("Load (kW)")
        ax.set_xlabel("Time")
        ax.legend(loc="best", frameon=True, edgecolor="#cccccc")
        finite_clean = load_kw[np.isfinite(load_kw)]
        if len(finite_clean):
            low = float(np.min(finite_clean))
            high = float(np.max(finite_clean))
            span = max(high - low, 1.0)
            ax.set_ylim(low - 0.12 * span, high + 0.28 * span)

        if ax_daily is not None:
            if len(daily):
                ax_daily.plot(
                    daily["date"],
                    daily["mean_kw"],
                    "-o",
                    color=_DAILY,
                    linewidth=1.6,
                    markersize=7,
                    markerfacecolor=_DAILY,
                    label="Daily mean",
                )
                left = pd.Timestamp(daily["date"].iloc[0]) - pd.Timedelta(hours=12)
                right = pd.Timestamp(daily["date"].iloc[-1]) + pd.Timedelta(hours=12)
                ax_daily.set_xlim(left, right)
            ax_daily.set_title("Daily mean load")
            ax_daily.set_ylabel("Mean load (kW)")
            ax_daily.set_xlabel("Date")
            ax_daily.grid(True, color="#d0d0d0", linewidth=0.6)
            ax_daily.set_axisbelow(True)
            ax_daily.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))

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


def _style_time_axis(ax: object, mdates: object) -> None:
    locator = mdates.AutoDateLocator()
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    ax.grid(True, color="#d0d0d0", linewidth=0.6)
    ax.set_axisbelow(True)


def _mark_outliers(
    ax: object,
    time: pd.Series,
    load_kw: np.ndarray,
    load_raw: np.ndarray,
    is_outlier: np.ndarray,
) -> None:
    if not np.any(is_outlier):
        return
    idx = np.flatnonzero(is_outlier & np.isfinite(load_kw) & np.isfinite(load_raw))
    if len(idx) == 0:
        return
    finite_raw = load_raw[np.isfinite(load_raw)]
    center = float(np.median(finite_raw)) if len(finite_raw) else 0.0
    if len(idx) > MAX_ANNOTATIONS:
        deviation = np.abs(load_raw[idx] - center)
        idx = idx[np.argsort(deviation)[-MAX_ANNOTATIONS:]]
    times = pd.to_datetime(time).iloc[idx]
    ax.scatter(
        times,
        load_kw[idx],
        marker="x",
        s=42,
        color=_SPIKE,
        linewidths=1.4,
        label="Flagged spike",
        zorder=3,
    )
    finite_clean = load_kw[np.isfinite(load_kw)]
    span = max(float(np.max(finite_clean) - np.min(finite_clean)), 1.0) if len(finite_clean) else 1.0
    for stamp, cleaned, raw in zip(times, load_kw[idx], load_raw[idx], strict=True):
        ax.text(
            stamp,
            float(cleaned) + 0.08 * span,
            _format_kw(float(raw)),
            color=_SPIKE,
            fontsize=8,
            ha="center",
            va="bottom",
        )
