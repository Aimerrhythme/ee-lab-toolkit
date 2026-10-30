"""Daily PV output features: peak, ramp, energy, and a variability index.

The calculations match ``matlab/pv_daily_features.m``. No toolbox and no SciPy.

Each calendar day is taken from naive local timestamps. A uniform series is
kept as recorded. An uneven series, or an explicit ``step_minutes``, is
linearly resampled. The last grid step is shortened when that is what it
takes to keep the final sample.

On the series for one day, with time in minutes from midnight:

    E_kWh = sum_i 0.5 * (P_i + P_{i+1}) * (t_{i+1} - t_i) / 60
    CF = E_kWh / (P_rated * 24)          when a nameplate is given
    ramp_i = (P_j - P_i) / (t_j - t_i)   t_j is the first sample at or after
                                         t_i + ramp_minutes, in kW/min
    VI = sum_i |P_{i+1} - P_i| / (2 * P_peak)

A curve that leaves its minimum once, reaches a single peak, and returns to
that minimum has VI = 1. Extra rises and falls (clouds) push VI above 1.
``P_peak`` is the first sample that attains the maximum. Step ramps use
consecutive samples; window ramps use ``ramp_minutes``.
"""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from numbers import Real
from pathlib import Path

import numpy as np

DEFAULT_RAMP_MINUTES = 10.0
P_ON_FRAC_RATED = 0.02
P_ON_FRAC_PEAK = 0.05
DEFAULT_DAY = "1970-01-01"

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
    "pv_kw",
    "pv_power",
    "ac_power",
    "power",
    "p",
    "kw",
    "出力kw",
    "功率kw",
    "功率",
    "出力",
    "有功功率",
    "有功",
)
_PARAM_NAMES = {
    "time_col",
    "power_col",
    "p_rated_kw",
    "p_on_kw",
    "ramp_minutes",
    "step_minutes",
    "day",
    "csv_path",
    "output_csv",
    "output_png",
    "show",
}
_SUMMARY_FIELDS = (
    "date",
    "n_samples",
    "step_minutes",
    "resampled",
    "p_rated_kw",
    "p_on_kw",
    "p_peak_kw",
    "t_peak",
    "t_peak_min",
    "energy_kwh",
    "hours_span",
    "p_mean_kw",
    "capacity_factor",
    "t_on",
    "t_off",
    "t_on_min",
    "t_off_min",
    "hours_window",
    "hours_above",
    "ramp_minutes",
    "ramp_up_kw_per_min",
    "ramp_down_kw_per_min",
    "ramp_up_span_min",
    "ramp_down_span_min",
    "t_ramp_up",
    "t_ramp_down",
    "t_ramp_up_min",
    "t_ramp_down_min",
    "ramp_step_up_kw_per_min",
    "ramp_step_down_kw_per_min",
    "t_step_up",
    "t_step_down",
    "t_step_up_min",
    "t_step_down_min",
    "variability_index",
)
_TEXT_FIELDS = {
    "date",
    "t_peak",
    "t_on",
    "t_off",
    "t_ramp_up",
    "t_ramp_down",
    "t_step_up",
    "t_step_down",
}
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


@dataclass
class PvDay:
    """Features and the series used to compute them for one calendar day.

    Clock fields are ``HH:MM:SS`` in naive local time, or ``nan`` when the
    feature is undefined. ``capacity_factor`` is ``energy_kwh / (p_rated_kw * 24)``.
    ``variability_index`` is 1 for a single rise and fall that starts and ends
    at the minimum, and greater than 1 when the day reverses extra times.
    Curve arrays are one sample per kept or resampled point. ``ramp_kw_per_min``
    is the window ramp that starts at that sample; samples with no complete
    window are NaN.
    """

    date: str
    n_samples: int
    step_minutes: float
    resampled: bool
    p_rated_kw: float
    p_on_kw: float
    p_peak_kw: float
    t_peak: str
    t_peak_min: float
    energy_kwh: float
    hours_span: float
    p_mean_kw: float
    capacity_factor: float
    t_on: str
    t_off: str
    t_on_min: float
    t_off_min: float
    hours_window: float
    hours_above: float
    ramp_minutes: float
    ramp_up_kw_per_min: float
    ramp_down_kw_per_min: float
    ramp_up_span_min: float
    ramp_down_span_min: float
    t_ramp_up: str
    t_ramp_down: str
    t_ramp_up_min: float
    t_ramp_down_min: float
    ramp_step_up_kw_per_min: float
    ramp_step_down_kw_per_min: float
    t_step_up: str
    t_step_down: str
    t_step_up_min: float
    t_step_down_min: float
    variability_index: float
    minute: np.ndarray
    hour: np.ndarray
    power_kw: np.ndarray
    ramp_kw_per_min: np.ndarray


@dataclass
class PvDailyFeaturesResult:
    """One row of features per day, a text summary, and optional files.

    ``summary`` is the same text as ``format_table``. ``p_on_kw`` is the
    threshold passed by the caller; NaN means each day used its own default.
    ``n_rows`` counts samples after blank powers and duplicate timestamps are
    removed. ``n_missing`` counts blank or NaN power cells. ``n_duplicates``
    counts extra rows that shared a timestamp with an earlier row.
    """

    days: list[PvDay]
    summary: str
    n_rows: int
    n_missing: int
    n_duplicates: int
    ramp_minutes: float
    p_rated_kw: float
    p_on_kw: float
    output_csv: str | None
    output_png: str | None
    fig: object | None = None


def pv_daily_features(
    source: str | Path | Sequence | None = None,
    power: Sequence | None = None,
    *,
    time_col: str | None = None,
    power_col: str | None = None,
    p_rated_kw: float | None = None,
    p_on_kw: float | None = None,
    ramp_minutes: float = DEFAULT_RAMP_MINUTES,
    step_minutes: float | None = None,
    day: str | None = None,
    csv_path: str | Path | None = None,
    output_csv: str | Path | None = None,
    output_png: str | Path | None = None,
    show: bool = False,
) -> PvDailyFeaturesResult:
    """Extract daily peak, energy, daylight window, and ramp features.

    Parameters use the same names as the MATLAB name-value arguments.
    ``source`` is a CSV path, a vector of timestamps, or, together with
    ``power``, minutes from midnight of ``day``. Blank CSV power cells are
    dropped. Duplicate timestamps keep the first row.
    """

    ramp_minutes = _positive("ramp_minutes", ramp_minutes)
    if step_minutes is not None:
        step_minutes = _positive("step_minutes", step_minutes)
    if p_rated_kw is not None:
        p_rated_kw = _positive("p_rated_kw", p_rated_kw)
    if p_on_kw is not None:
        p_on_kw = _nonnegative("p_on_kw", p_on_kw)
    show = _as_bool("show", show)
    samples, n_missing, n_duplicates = _resolve_samples(
        source,
        power,
        time_col=time_col,
        power_col=power_col,
        day=day,
        csv_path=csv_path,
    )
    days = [
        _build_day(date, minutes, values, p_rated_kw, p_on_kw, ramp_minutes, step_minutes)
        for date, minutes, values in _group_days(samples)
    ]
    summary = _format_result(days, len(samples), n_missing, n_duplicates, ramp_minutes)
    csv_out = None if output_csv is None or str(output_csv).strip() == "" else str(output_csv)
    png_out = None if output_png is None or str(output_png).strip() == "" else str(output_png)
    rated_out = math.nan if p_rated_kw is None else p_rated_kw
    on_out = math.nan if p_on_kw is None else p_on_kw
    result = PvDailyFeaturesResult(
        days=days,
        summary=summary,
        n_rows=len(samples),
        n_missing=n_missing,
        n_duplicates=n_duplicates,
        ramp_minutes=ramp_minutes,
        p_rated_kw=rated_out,
        p_on_kw=on_out,
        output_csv=csv_out,
        output_png=png_out,
        fig=None,
    )
    if csv_out is not None:
        _write_summary(Path(csv_out), days)
    if png_out is not None or show:
        result.fig = _render_figure(days, rated_out, png_out, show)
    return result


def format_table(result: PvDailyFeaturesResult) -> str:
    """Format one text block of features per day."""

    return result.summary


def _format_result(
    days: Sequence[PvDay],
    n_rows: int,
    n_missing: int,
    n_duplicates: int,
    ramp_minutes: float,
) -> str:
    header = (
        f"rows={n_rows}  missing={n_missing}  duplicates={n_duplicates}  "
        f"days={len(days)}  ramp_min={_compact(ramp_minutes)}"
    )
    blocks = [header, *(_format_day(day) for day in days)]
    return "\n\n".join(blocks)


def _format_day(day: PvDay) -> str:
    if math.isfinite(day.t_on_min):
        on_text = f"on={day.t_on}-{day.t_off}"
    else:
        on_text = "on=undefined"
    lines = [
        (
            f"date={day.date}  N={day.n_samples}  step={_compact(day.step_minutes)}  "
            f"resampled={1 if day.resampled else 0}"
        ),
        (
            f"Ppeak={_compact(day.p_peak_kw)}  t_peak={day.t_peak}  "
            f"E={_compact(day.energy_kwh)}  mean={_compact(day.p_mean_kw)}  "
            f"span={_compact(day.hours_span)}  CF={_compact(day.capacity_factor)}  "
            f"Prated={_compact(day.p_rated_kw)}  Pon={_compact(day.p_on_kw)}"
        ),
        (
            f"{on_text}  window={_compact(day.hours_window)}  "
            f"above={_compact(day.hours_above)}"
        ),
        (
            f"ramp_min={_compact(day.ramp_minutes)}  "
            f"up={_compact(day.ramp_up_kw_per_min)}  down={_compact(day.ramp_down_kw_per_min)}  "
            f"up_span={_compact(day.ramp_up_span_min)}  down_span={_compact(day.ramp_down_span_min)}  "
            f"t_up={day.t_ramp_up}  t_down={day.t_ramp_down}"
        ),
        (
            f"step_up={_compact(day.ramp_step_up_kw_per_min)}  t_step_up={day.t_step_up}  "
            f"step_down={_compact(day.ramp_step_down_kw_per_min)}  t_step_down={day.t_step_down}  "
            f"VI={_compact(day.variability_index)}"
        ),
    ]
    return "\n".join(lines)


def _build_day(
    date: str,
    minute: np.ndarray,
    power: np.ndarray,
    p_rated_kw: float | None,
    p_on_kw: float | None,
    ramp_minutes: float,
    step_minutes: float | None,
) -> PvDay:
    grid, values, step, resampled = _prepare_series(minute, power, step_minutes)
    n = int(values.size)
    peak_index = int(np.argmax(values))
    p_peak = float(values[peak_index])
    t_peak = float(grid[peak_index])
    energy = _trapezoid_kwh(grid, values)
    if n < 2 or grid[-1] == grid[0]:
        hours_span = 0.0
        p_mean = float(values[0])
    else:
        hours_span = float(grid[-1] - grid[0]) / 60.0
        p_mean = energy / hours_span
    if p_rated_kw is None:
        rated = math.nan
        capacity = math.nan
    else:
        rated = p_rated_kw
        capacity = energy / (p_rated_kw * 24.0)
    if p_on_kw is None:
        if p_rated_kw is not None:
            p_on = P_ON_FRAC_RATED * p_rated_kw
        elif p_peak > 0.0:
            p_on = P_ON_FRAC_PEAK * p_peak
        else:
            p_on = 0.0
    else:
        p_on = p_on_kw
    on = values >= p_on
    on_index = np.flatnonzero(on)
    if on_index.size == 0:
        t_on = math.nan
        t_off = math.nan
        hours_window = math.nan
    else:
        t_on = float(grid[int(on_index[0])])
        t_off = float(grid[int(on_index[-1])])
        hours_window = (t_off - t_on) / 60.0
    hours_above = _hours_above(grid, on)
    window_ramp, window_span = _window_ramps(grid, values, ramp_minutes)
    ramp_up, up_span, t_up, up_clock = _pick_extreme(window_ramp, window_span, grid, "up")
    ramp_down, down_span, t_down, down_clock = _pick_extreme(window_ramp, window_span, grid, "down")
    step_up, step_down, t_step_up, t_step_down, step_up_clock, step_down_clock = _step_ramps(grid, values)
    if n >= 2 and p_peak > 0.0:
        variability = float(np.sum(np.abs(np.diff(values)))) / (2.0 * p_peak)
    else:
        variability = math.nan
    return PvDay(
        date=date,
        n_samples=n,
        step_minutes=step,
        resampled=resampled,
        p_rated_kw=rated,
        p_on_kw=p_on,
        p_peak_kw=p_peak,
        t_peak=_clock(t_peak),
        t_peak_min=t_peak,
        energy_kwh=energy,
        hours_span=hours_span,
        p_mean_kw=p_mean,
        capacity_factor=capacity,
        t_on=_clock(t_on),
        t_off=_clock(t_off),
        t_on_min=t_on,
        t_off_min=t_off,
        hours_window=hours_window,
        hours_above=hours_above,
        ramp_minutes=ramp_minutes,
        ramp_up_kw_per_min=ramp_up,
        ramp_down_kw_per_min=ramp_down,
        ramp_up_span_min=up_span,
        ramp_down_span_min=down_span,
        t_ramp_up=up_clock,
        t_ramp_down=down_clock,
        t_ramp_up_min=t_up,
        t_ramp_down_min=t_down,
        ramp_step_up_kw_per_min=step_up,
        ramp_step_down_kw_per_min=step_down,
        t_step_up=step_up_clock,
        t_step_down=step_down_clock,
        t_step_up_min=t_step_up,
        t_step_down_min=t_step_down,
        variability_index=variability,
        minute=np.ascontiguousarray(grid, dtype=float),
        hour=np.ascontiguousarray(grid / 60.0, dtype=float),
        power_kw=np.ascontiguousarray(values, dtype=float),
        ramp_kw_per_min=np.ascontiguousarray(window_ramp, dtype=float),
    )


def _prepare_series(
    minute: np.ndarray,
    power: np.ndarray,
    step_minutes: float | None,
) -> tuple[np.ndarray, np.ndarray, float, bool]:
    minute = np.ascontiguousarray(minute, dtype=float)
    power = np.ascontiguousarray(power, dtype=float)
    n = int(minute.size)
    if n == 0:
        raise ValueError("A day has no samples")
    if n == 1:
        return minute.copy(), power.copy(), math.nan, False
    dt = np.diff(minute)
    if np.any(dt <= 0.0):
        raise ValueError("timestamps in a day must be strictly increasing")
    med = _median(dt)
    uniform = bool(np.max(np.abs(dt - med)) <= 1e-6 * max(med, 1.0))
    if step_minutes is None:
        if uniform:
            return minute.copy(), power.copy(), float(med), False
        step = float(med)
    else:
        step = float(step_minutes)
        if uniform and abs(step - med) <= 1e-6 * max(step, 1.0):
            return minute.copy(), power.copy(), float(med), False
    span = float(minute[-1] - minute[0])
    if step > span:
        raise ValueError("step_minutes is longer than the series")
    n_grid = int(math.floor(span / step + 1e-9)) + 1
    grid = minute[0] + step * np.arange(n_grid, dtype=float)
    if float(minute[-1] - grid[-1]) > 1e-6:
        grid = np.append(grid, minute[-1])
    values = np.interp(grid, minute, power)
    return np.ascontiguousarray(grid, dtype=float), np.ascontiguousarray(values, dtype=float), step, True


def _trapezoid_kwh(minute: np.ndarray, power: np.ndarray) -> float:
    if minute.size < 2:
        return 0.0
    dt_h = np.diff(minute) / 60.0
    return float(np.sum(0.5 * (power[:-1] + power[1:]) * dt_h))


def _hours_above(minute: np.ndarray, on: np.ndarray) -> float:
    if minute.size < 2:
        return 0.0
    dt_h = np.diff(minute) / 60.0
    indicator = on.astype(float)
    return float(np.sum(0.5 * (indicator[:-1] + indicator[1:]) * dt_h))


def _window_ramps(minute: np.ndarray, power: np.ndarray, ramp_minutes: float) -> tuple[np.ndarray, np.ndarray]:
    n = int(minute.size)
    ramp = np.full(n, np.nan)
    span = np.full(n, np.nan)
    if n < 2:
        return ramp, span
    for index in range(n - 1):
        target = float(minute[index]) + ramp_minutes
        end = int(np.searchsorted(minute, target - 1e-9, side="left"))
        if end <= index:
            end = index + 1
        if end >= n:
            break
        dur = float(minute[end] - minute[index])
        if dur <= 0.0:
            continue
        ramp[index] = (float(power[end]) - float(power[index])) / dur
        span[index] = dur
    return ramp, span


def _pick_extreme(
    ramp: np.ndarray,
    span: np.ndarray,
    minute: np.ndarray,
    which: str,
) -> tuple[float, float, float, str]:
    if not np.any(np.isfinite(ramp)):
        return math.nan, math.nan, math.nan, "nan"
    if which == "up":
        filled = np.where(np.isfinite(ramp), ramp, -math.inf)
        index = int(np.argmax(filled))
    else:
        filled = np.where(np.isfinite(ramp), ramp, math.inf)
        index = int(np.argmin(filled))
    return float(ramp[index]), float(span[index]), float(minute[index]), _clock(float(minute[index]))


def _step_ramps(minute: np.ndarray, power: np.ndarray) -> tuple[float, float, float, float, str, str]:
    if minute.size < 2:
        return math.nan, math.nan, math.nan, math.nan, "nan", "nan"
    step = np.diff(power) / np.diff(minute)
    up_index = int(np.argmax(step))
    down_index = int(np.argmin(step))
    return (
        float(step[up_index]),
        float(step[down_index]),
        float(minute[up_index]),
        float(minute[down_index]),
        _clock(float(minute[up_index])),
        _clock(float(minute[down_index])),
    )


def _group_days(samples: Sequence[tuple[int, int, int, float, float]]) -> list[tuple[str, np.ndarray, np.ndarray]]:
    groups: list[tuple[str, list[float], list[float]]] = []
    current_key = ""
    for year, month, day, minute, power in samples:
        key = f"{year:04d}-{month:02d}-{day:02d}"
        if not groups or key != current_key:
            groups.append((key, [], []))
            current_key = key
        groups[-1][1].append(minute)
        groups[-1][2].append(power)
    return [
        (key, np.ascontiguousarray(minutes, dtype=float), np.ascontiguousarray(values, dtype=float))
        for key, minutes, values in groups
    ]


def _resolve_samples(
    source: object,
    power: object,
    *,
    time_col: object,
    power_col: object,
    day: object,
    csv_path: object,
) -> tuple[list[tuple[int, int, int, float, float]], int, int]:
    path_text = None if csv_path is None or str(csv_path).strip() == "" else str(csv_path).strip()
    if isinstance(source, bool) or (isinstance(source, Real) and not isinstance(source, bool)):
        raise ValueError("pass a CSV path, timestamps, or minutes; the first argument is not a scalar")
    if isinstance(source, str) and source.strip() == "":
        source = None
    if isinstance(source, str) and _is_parameter_name(source):
        raise ValueError(
            f"{source.strip()!r} is a parameter name. Pass the CSV path as the first argument or as csv_path="
        )
    array_input = power is not None or _is_time_vector(source)
    if array_input:
        if path_text is not None or (isinstance(source, (str, Path)) and not _is_time_vector(source)):
            raise ValueError("pass time and power, or a CSV path, not both")
        if time_col not in (None, "") or power_col not in (None, ""):
            raise ValueError("time_col and power_col apply to a CSV, not to time and power vectors")
        if source is None:
            raise ValueError("pass time and power, or a CSV path")
        samples, n_duplicates = _samples_from_vectors(source, power, day)
        return samples, 0, n_duplicates
    if day is not None and str(day).strip() != "":
        raise ValueError("day applies to numeric minutes, not a CSV")
    if isinstance(source, (str, Path)):
        if path_text is not None:
            raise ValueError("pass a CSV path once, either positionally or as csv_path=")
        path_text = str(source).strip()
    elif source is not None:
        raise TypeError("source must be a CSV path, timestamps, or minutes from midnight")
    if path_text is None:
        raise ValueError("pass a CSV path, or time and power")
    rows, n_missing = _read_csv_rows(Path(path_text), time_col, power_col)
    samples, n_duplicates = _clean_samples(rows)
    if not samples:
        raise ValueError("No power samples remain after cleaning")
    return samples, n_missing, n_duplicates


def _is_time_vector(value: object) -> bool:
    if value is None or isinstance(value, (str, Path, bool)):
        return False
    if isinstance(value, datetime):
        return False
    if isinstance(value, np.ndarray):
        return value.ndim == 1 and value.size > 0
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return len(value) > 0
    return False


def _is_parameter_name(value: str) -> bool:
    return value.strip().lower() in _PARAM_NAMES


def _samples_from_vectors(
    time: object,
    power: object,
    day: object,
) -> tuple[list[tuple[int, int, int, float, float]], int]:
    if power is None:
        raise ValueError("pass power together with time")
    stamps = _time_parts(time, day)
    values = _power_vector(power)
    if len(stamps) != len(values):
        raise ValueError("time and power must have the same length")
    paired = [(stamp[0], stamp[1], stamp[2], stamp[3], values[index]) for index, stamp in enumerate(stamps)]
    samples, n_duplicates = _clean_samples(paired)
    if not samples:
        raise ValueError("time must not be empty")
    return samples, n_duplicates


def _time_parts(time: object, day: object) -> list[tuple[int, int, int, float]]:
    if isinstance(time, np.ndarray) and np.issubdtype(time.dtype, np.datetime64):
        if day is not None and str(day).strip() != "":
            raise ValueError("day applies to numeric minutes, not to timestamps")
        return [_parts_from_datetime(_datetime64_to_datetime(item)) for item in time]
    items = _as_list(time)
    if not items:
        raise ValueError("time must not be empty")
    if _item_is_stamp(items[0]):
        if day is not None and str(day).strip() != "":
            raise ValueError("day applies to numeric minutes, not to timestamps")
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
    minutes = _power_vector(items)
    if np.any(minutes < 0.0):
        raise ValueError("time in minutes must be zero or a positive finite number")
    origin = _parse_day(DEFAULT_DAY if day is None or str(day).strip() == "" else str(day))
    parts = []
    for minute in minutes:
        offset = int(math.floor(float(minute) / 1440.0 + 1e-12))
        minute_of_day = float(minute) - offset * 1440.0
        if minute_of_day >= 1440.0 - 1e-9:
            offset += 1
            minute_of_day -= 1440.0
        year, month, day_number = _add_days(origin[0], origin[1], origin[2], offset)
        parts.append((year, month, day_number, minute_of_day))
    return parts


def _item_is_stamp(item: object) -> bool:
    return isinstance(item, (str, datetime, np.datetime64))


def _as_list(value: object) -> list[object]:
    if isinstance(value, np.ndarray):
        if value.ndim != 1:
            raise ValueError("time must be a vector")
        return [item for item in value]
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


def _parse_day(text: str) -> tuple[int, int, int]:
    raw = text.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ValueError("day must be YYYY-MM-DD")
    year, month, day = int(raw[0:4]), int(raw[5:7]), int(raw[8:10])
    if not _valid_date(year, month, day):
        raise ValueError("day must be a real calendar date")
    return year, month, day


def _read_csv_rows(
    path: Path,
    time_col: object,
    power_col: object,
) -> tuple[list[tuple[int, int, int, float, float]], int]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        if sample.strip() == "":
            raise ValueError(f"CSV is empty: {path}")
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError(f"CSV is empty: {path}")
        columns = ["" if name is None else str(name).strip() for name in reader.fieldnames]
        time_name = _resolve_column(columns, time_col, _TIME_ALIASES, "time")
        power_name = _resolve_column(columns, power_col, _POWER_ALIASES, "power")
        if time_name == power_name:
            raise ValueError("time and power columns must be different")
        rows: list[tuple[int, int, int, float, float]] = []
        n_missing = 0
        for raw in reader:
            if raw is None:
                continue
            cleaned = {
                ("" if key is None else str(key).strip()): "" if value is None else str(value).strip()
                for key, value in raw.items()
            }
            if all(item == "" for item in cleaned.values()):
                continue
            time_text = cleaned.get(time_name, "")
            power_text = cleaned.get(power_name, "")
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
    ordered = sorted(rows, key=lambda item: (item[0], item[1], item[2], item[3]))
    kept: list[tuple[int, int, int, float, float]] = []
    duplicates = 0
    for item in ordered:
        if kept:
            previous = kept[-1]
            same_day = previous[0] == item[0] and previous[1] == item[1] and previous[2] == item[2]
            if same_day and abs(previous[3] - item[3]) <= 1e-9:
                duplicates += 1
                continue
        kept.append(item)
    return kept, duplicates


def _resolve_column(
    columns: Sequence[str],
    requested: object,
    aliases: Sequence[str],
    kind: str,
) -> str:
    pairs = [(_norm_key(column), column) for column in columns if column != ""]
    if requested is not None and str(requested).strip() != "":
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


def _norm_key(value: object) -> str:
    return re.sub(r"[\s_\-()（）]", "", str(value).strip().lower())


def _clock(minutes: float) -> str:
    if not math.isfinite(minutes):
        return "nan"
    # Half away from zero, matching MATLAB round for a non-negative value.
    total = int(math.floor(minutes * 60.0 + 0.5)) % 86400
    hour = total // 3600
    minute = (total % 3600) // 60
    second = total % 60
    return f"{hour:02d}:{minute:02d}:{second:02d}"


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


def _days_from_civil(year: int, month: int, day: int) -> int:
    year2 = year - (1 if month <= 2 else 0)
    era = year2 // 400 if year2 >= 0 else (year2 - 399) // 400
    yoe = year2 - era * 400
    month_part = month - 3 if month > 2 else month + 9
    doy = (153 * month_part + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _civil_from_days(z: int) -> tuple[int, int, int]:
    z += 719468
    era = z // 146097 if z >= 0 else (z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    year = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    day = doy - (153 * mp + 2) // 5 + 1
    month = mp + (3 if mp < 10 else -9)
    if month <= 2:
        year += 1
    return year, month, day


def _add_days(year: int, month: int, day: int, offset: int) -> tuple[int, int, int]:
    return _civil_from_days(_days_from_civil(year, month, day) + offset)


def _compact(value: float) -> str:
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        value = float(value)
    if not isinstance(value, float):
        value = float(value)
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    text = f"{value:.6g}"
    if "e" not in text and "E" not in text:
        return text
    if abs(value - round(value)) <= 1e-6 * max(abs(value), 1.0):
        return f"{value:.0f}"
    return f"{value:.4f}"


def _finite(label: str, value: object) -> float:
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError as exc:
            raise ValueError(f"{label} must be a finite number") from exc
    elif isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite number")
    else:
        number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _positive(label: str, value: object) -> float:
    number = _finite(label, value)
    if number <= 0:
        raise ValueError(f"{label} must be a positive finite number")
    return number


def _nonnegative(label: str, value: object) -> float:
    number = _finite(label, value)
    if number < 0:
        raise ValueError(f"{label} must be zero or a positive finite number")
    return number


def _as_bool(label: str, value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool) and int(value) in (0, 1):
        return bool(int(value))
    raise ValueError(f"{label} must be true or false")


def _csv_num(value: float) -> str:
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return f"{value:.12g}"


def _write_summary(path: Path, days: Sequence[PvDay]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_SUMMARY_FIELDS)
        writer.writeheader()
        for day in days:
            row: dict[str, str] = {}
            for field in _SUMMARY_FIELDS:
                value = getattr(day, field)
                if field in _TEXT_FIELDS:
                    row[field] = str(value)
                elif field == "n_samples":
                    row[field] = str(int(value))
                elif field == "resampled":
                    row[field] = "1" if value else "0"
                else:
                    row[field] = _csv_num(float(value))
            writer.writerow(row)


def _render_figure(
    days: Sequence[PvDay],
    p_rated_kw: float,
    output_png: str | None,
    show: bool,
) -> object | None:
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
        fig, axes = plt.subplots(2, 1, figsize=(10.4, 8.4), sharex=True)
        power_axis, ramp_axis = axes
        hours: list[float] = []
        powers: list[float] = []
        ramps: list[float] = []
        for index, day in enumerate(days):
            color = _PALETTE[index % len(_PALETTE)]
            power_axis.plot(day.hour, day.power_kw, color=color, lw=1.7, label=day.date)
            ramp_axis.plot(day.hour, day.ramp_kw_per_min, color=color, lw=1.5, label=day.date)
            power_axis.plot(day.t_peak_min / 60.0, day.p_peak_kw, marker="o", color=color, ms=6, ls="none")
            if math.isfinite(day.t_ramp_up_min):
                ramp_axis.plot(
                    day.t_ramp_up_min / 60.0,
                    day.ramp_up_kw_per_min,
                    marker="^",
                    color=color,
                    ms=7,
                    ls="none",
                )
            if math.isfinite(day.t_ramp_down_min):
                ramp_axis.plot(
                    day.t_ramp_down_min / 60.0,
                    day.ramp_down_kw_per_min,
                    marker="v",
                    color=color,
                    ms=7,
                    ls="none",
                )
            hours.extend(float(value) for value in day.hour)
            powers.extend(float(value) for value in day.power_kw if math.isfinite(value))
            ramps.extend(float(value) for value in day.ramp_kw_per_min if math.isfinite(value))
            if math.isfinite(day.ramp_up_kw_per_min):
                ramps.append(day.ramp_up_kw_per_min)
            if math.isfinite(day.ramp_down_kw_per_min):
                ramps.append(day.ramp_down_kw_per_min)
        if math.isfinite(p_rated_kw):
            power_axis.axhline(p_rated_kw, color="#888888", ls="--", lw=1.0, label="rated")
            powers.append(p_rated_kw)
        _style_power_axis(power_axis, hours, powers)
        _style_ramp_axis(ramp_axis, hours, ramps)
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


def _style_power_axis(axis: object, hours: Sequence[float], powers: Sequence[float]) -> None:
    axis.set_title("PV power")
    axis.set_ylabel("Power (kW)")
    axis.grid(True, color="#d0d0d0", linewidth=0.6)
    axis.legend(loc="upper right", frameon=True, edgecolor="#cccccc")
    _pad_time_axis(axis, hours)
    if not powers:
        return
    ymin = min(0.0, min(powers))
    ymax = max(powers)
    span = ymax - ymin if ymax > ymin else max(abs(ymax), 1.0)
    pad = 0.08 * span
    axis.set_ylim(ymin - (0.0 if ymin >= -1e-9 else pad), ymax + pad)


def _style_ramp_axis(axis: object, hours: Sequence[float], ramps: Sequence[float]) -> None:
    axis.set_title("Ramp over the window")
    axis.set_xlabel("Hour of day")
    axis.set_ylabel("Ramp (kW/min)")
    axis.axhline(0.0, color="#888888", lw=0.8)
    axis.grid(True, color="#d0d0d0", linewidth=0.6)
    axis.legend(loc="upper right", frameon=True, edgecolor="#cccccc")
    _pad_time_axis(axis, hours)
    if not ramps:
        return
    span = max(abs(min(ramps)), abs(max(ramps)), 1e-6)
    pad = 0.12 * span
    axis.set_ylim(min(ramps) - pad, max(ramps) + pad)


def _pad_time_axis(axis: object, hours: Sequence[float]) -> None:
    if not hours:
        return
    xmin = min(hours)
    xmax = max(hours)
    span = xmax - xmin if xmax > xmin else 1.0
    pad = 0.04 * span
    axis.set_xlim(xmin - pad, xmax + pad)
