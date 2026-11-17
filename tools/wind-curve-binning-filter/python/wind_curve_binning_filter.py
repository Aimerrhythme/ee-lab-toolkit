"""Bin a wind-turbine power curve, then mark shutdown, curtailment, and scatter.

The calculations match ``matlab/wind_curve_binning_filter.m``. No toolbox and
no SciPy. The abnormal-point names follow the taxonomy in Long, Sang, Wu, and
Gu, arXiv:2307.08539 (negative, scattered, and stacked points). This tool is
the classroom quartile method, not their image-morphology detector.

Theoretical power is the textbook cubic between cut-in and rated speed::

    P = 0                         v < v_cut_in or v >= v_cut_out
    P = P_rated                   v_rated <= v < v_cut_out
    P = P_rated * (v**3 - v_cut_in**3) / (v_rated**3 - v_cut_in**3)
                                  v_cut_in <= v < v_rated

Bins are half-open intervals ``[v_min + i*bin_width, v_min + (i+1)*bin_width)``.
Quartiles use the Hyndman–Fan type-7 linear rule (the default of NumPy
``quantile`` and MATLAB ``quantile``): with ``h = (n - 1) * q`` and ``x``
sorted,

    Q = x[floor(h)]                         when h is an integer
      = x[floor(h)] * (1 - f) + x[ceil(h)] * f    otherwise

``IQR = Q3 - Q1``. A bin with at least ``min_bin_count`` points still unmarked
by the rules below rejects power outside the closed fence
``[Q1 - iqr_k*IQR, Q3 + iqr_k*IQR]``.

Rules run in this order, and the first match wins:

1. ``negative`` — power < 0 and wind speed >= cut-in (sensor or stop below zero).
2. ``shutdown`` — power <= ``p_shutdown_kw`` while theoretical power is at least
   ``p_shutdown_theory_frac * P_rated`` and wind speed < cut-out.
3. ``curtailment`` — power is above the shutdown band but below
   ``curtail_ratio`` times theoretical power, and theoretical power is at least
   ``curtail_theory_frac * P_rated``, inside ``[cut-in, cut-out)``.
4. ``outlier`` / ``below_cut_in`` or ``above_cut_out`` — power above the
   shutdown band where the theoretical curve is already zero.
5. ``outlier`` / ``iqr`` — outside the bin fence. The fence is fit on the
   points that rules 1–4 left unmarked, so a curtailment stack does not pull
   the quartiles down.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FLAG_NORMAL = "normal"
FLAG_NEGATIVE = "negative"
FLAG_SHUTDOWN = "shutdown"
FLAG_CURTAILMENT = "curtailment"
FLAG_OUTLIER = "outlier"

REASON_IQR = "iqr"
REASON_BELOW_CUT_IN = "below_cut_in"
REASON_ABOVE_CUT_OUT = "above_cut_out"

_WIND_ALIASES = (
    "wind_mps",
    "wind_speed_mps",
    "wind_speed",
    "wind",
    "v_mps",
    "v",
    "风速",
)
_POWER_ALIASES = (
    "power_kw",
    "p_kw",
    "active_power_kw",
    "active_power",
    "power",
    "p",
    "功率kw",
    "功率",
    "有功功率",
    "有功",
)

_POINT_HEADER = (
    "wind_mps,power_kw,theory_kw,bin_index,v_left,flag,reason,keep"
)
_BIN_HEADER = (
    "bin_index,v_left,v_right,v_center,n_raw,n_quartile,n_clean,"
    "median_kw,q1_kw,q3_kw,iqr_kw,lower_kw,upper_kw,fence_applied,"
    "median_clean_kw,theory_kw"
)


@dataclass
class BinRow:
    """One wind-speed bin. Empty statistic fields are NaN."""

    bin_index: int
    v_left: float
    v_right: float
    v_center: float
    n_raw: int
    n_quartile: int
    n_clean: int
    median_kw: float
    q1_kw: float
    q3_kw: float
    iqr_kw: float
    lower_kw: float
    upper_kw: float
    fence_applied: bool
    median_clean_kw: float
    theory_kw: float


@dataclass
class WindCurveResult:
    """Point flags plus the bin table. ``keep`` is true only for ``normal``."""

    wind_mps: np.ndarray
    power_kw: np.ndarray
    theory_kw: np.ndarray
    bin_index: np.ndarray
    flag: list[str]
    reason: list[str]
    keep: np.ndarray
    bins: list[BinRow]
    n_rows: int
    n_keep: int
    n_negative: int
    n_shutdown: int
    n_curtailment: int
    n_outlier: int
    n_missing: int
    bin_width: float
    v_min: float
    v_cut_in: float
    v_rated: float
    v_cut_out: float
    p_rated_kw: float
    p_shutdown_kw: float
    summary: str
    output_csv: str | None = None
    output_bins_csv: str | None = None
    output_png: str | None = None
    fig: object | None = None


def theoretical_power_kw(
    wind_mps,
    p_rated_kw: float,
    v_cut_in: float,
    v_rated: float,
    v_cut_out: float,
) -> np.ndarray:
    """Nameplate cubic power curve, kW, same shape as ``wind_mps``."""

    wind = np.asarray(wind_mps, dtype=float)
    power = np.zeros(wind.shape, dtype=float)
    rising = (wind >= v_cut_in) & (wind < v_rated)
    flat = (wind >= v_rated) & (wind < v_cut_out)
    span = v_rated**3 - v_cut_in**3
    power[rising] = p_rated_kw * (wind[rising] ** 3 - v_cut_in**3) / span
    power[flat] = p_rated_kw
    return power


def empirical_quantile(values, q: float) -> float:
    """Hyndman–Fan type-7 quantile of a 1-D sample. Empty input is NaN."""

    if isinstance(q, bool) or not isinstance(q, (int, float, np.floating, np.integer)):
        raise ValueError("q must be in [0, 1]")
    probability = float(q)
    if not math.isfinite(probability) or probability < 0.0 or probability > 1.0:
        raise ValueError("q must be in [0, 1]")
    data = np.asarray(values, dtype=float).reshape(-1)
    if data.size == 0:
        return float("nan")
    if not np.all(np.isfinite(data)):
        raise ValueError("quantile sample must be finite")
    ordered = np.sort(data)
    count = int(ordered.size)
    if count == 1:
        return float(ordered[0])
    position = (count - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return float(ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction)


def format_summary(result: WindCurveResult) -> str:
    """One-line counts. MATLAB prints the same sentence."""

    return (
        "wind-curve-binning-filter: "
        f"rows={result.n_rows} keep={result.n_keep} "
        f"negative={result.n_negative} shutdown={result.n_shutdown} "
        f"curtailment={result.n_curtailment} outlier={result.n_outlier} "
        f"bin_width={result.bin_width:.4g} p_rated_kw={result.p_rated_kw:.6g}"
    )


def wind_curve_binning_filter(
    source,
    power_kw=None,
    *,
    bin_width: float = 0.5,
    v_min: float = 0.0,
    v_cut_in: float = 3.0,
    v_rated: float = 12.0,
    v_cut_out: float = 25.0,
    p_rated_kw: float = 2000.0,
    p_shutdown_kw: float | None = None,
    p_shutdown_theory_frac: float = 0.10,
    curtail_ratio: float = 0.60,
    curtail_theory_frac: float = 0.30,
    iqr_k: float = 1.5,
    min_bin_count: int = 5,
    wind_col: str | None = None,
    power_col: str | None = None,
    output_csv=None,
    output_bins_csv=None,
    output_png=None,
    show: bool = False,
) -> WindCurveResult:
    """Flag abnormal wind–power points and bin the points that remain.

    ``source`` is a CSV path or a wind-speed array in m/s. With an array, pass
    ``power_kw`` as well. CSV power is kW. See the module docstring for the
    rule order.
    """

    width = _positive("bin_width", bin_width)
    origin = _nonnegative("v_min", v_min)
    cut_in = _nonnegative("v_cut_in", v_cut_in)
    rated = _positive("v_rated", v_rated)
    cut_out = _positive("v_cut_out", v_cut_out)
    if not (cut_in < rated < cut_out):
        raise ValueError("require v_cut_in < v_rated < v_cut_out")
    rated_kw = _positive("p_rated_kw", p_rated_kw)
    if p_shutdown_kw is None:
        shutdown_kw = 0.02 * rated_kw
    else:
        shutdown_kw = _nonnegative("p_shutdown_kw", p_shutdown_kw)
    shutdown_frac = _fraction("p_shutdown_theory_frac", p_shutdown_theory_frac)
    ratio = _open_fraction("curtail_ratio", curtail_ratio)
    curtail_frac = _fraction("curtail_theory_frac", curtail_theory_frac)
    fence_k = _nonnegative("iqr_k", iqr_k)
    minimum = _positive_int("min_bin_count", min_bin_count)
    if not isinstance(show, bool):
        raise ValueError("show must be true or false")
    wind_name = _optional_text("wind_col", wind_col)
    power_name = _optional_text("power_col", power_col)

    wind, power, n_missing = _resolve_samples(
        source, power_kw, wind_name, power_name
    )
    _check_series(wind, power, origin)

    theory = np.asarray(
        theoretical_power_kw(wind, rated_kw, cut_in, rated, cut_out), dtype=float
    ).reshape(-1)
    index = _bin_index(wind, origin, width)
    flag, reason = _rule_flags(
        wind,
        power,
        theory,
        cut_in,
        cut_out,
        rated_kw,
        shutdown_kw,
        shutdown_frac,
        ratio,
        curtail_frac,
    )
    n_bins = int(index.max()) + 1
    bins = _quartile_flags(
        index,
        power,
        flag,
        reason,
        n_bins,
        origin,
        width,
        fence_k,
        minimum,
        rated_kw,
        cut_in,
        rated,
        cut_out,
    )
    keep = np.array([item == FLAG_NORMAL for item in flag], dtype=bool)
    result = WindCurveResult(
        wind_mps=wind,
        power_kw=power,
        theory_kw=theory,
        bin_index=index,
        flag=flag,
        reason=reason,
        keep=keep,
        bins=bins,
        n_rows=int(wind.size),
        n_keep=int(keep.sum()),
        n_negative=flag.count(FLAG_NEGATIVE),
        n_shutdown=flag.count(FLAG_SHUTDOWN),
        n_curtailment=flag.count(FLAG_CURTAILMENT),
        n_outlier=flag.count(FLAG_OUTLIER),
        n_missing=n_missing,
        bin_width=width,
        v_min=origin,
        v_cut_in=cut_in,
        v_rated=rated,
        v_cut_out=cut_out,
        p_rated_kw=rated_kw,
        p_shutdown_kw=shutdown_kw,
        summary="",
    )
    result.summary = format_summary(result)
    if output_csv:
        result.output_csv = _write_points(output_csv, result)
    if output_bins_csv:
        result.output_bins_csv = _write_bins(output_bins_csv, result)
    if output_png or show:
        result.fig = _render(result, output_png, show)
        if output_png:
            result.output_png = str(output_png)
    return result


def _rule_flags(
    wind,
    power,
    theory,
    cut_in,
    cut_out,
    rated_kw,
    shutdown_kw,
    shutdown_frac,
    ratio,
    curtail_frac,
):
    count = int(wind.size)
    flag = [FLAG_NORMAL] * count
    reason = [""] * count
    shutdown_level = shutdown_frac * rated_kw
    curtail_level = curtail_frac * rated_kw
    for i in range(count):
        speed = float(wind[i])
        watts = float(power[i])
        expected = float(theory[i])
        if watts < 0.0 and speed >= cut_in:
            flag[i] = FLAG_NEGATIVE
            reason[i] = FLAG_NEGATIVE
        elif (
            watts <= shutdown_kw
            and expected >= shutdown_level
            and speed >= cut_in
            and speed < cut_out
        ):
            flag[i] = FLAG_SHUTDOWN
            reason[i] = FLAG_SHUTDOWN
        elif (
            speed >= cut_in
            and speed < cut_out
            and expected >= curtail_level
            and watts > shutdown_kw
            and watts < ratio * expected
        ):
            flag[i] = FLAG_CURTAILMENT
            reason[i] = FLAG_CURTAILMENT
        elif speed < cut_in and watts > shutdown_kw:
            flag[i] = FLAG_OUTLIER
            reason[i] = REASON_BELOW_CUT_IN
        elif speed >= cut_out and watts > shutdown_kw:
            flag[i] = FLAG_OUTLIER
            reason[i] = REASON_ABOVE_CUT_OUT
    return flag, reason


def _quartile_flags(
    index,
    power,
    flag,
    reason,
    n_bins,
    origin,
    width,
    fence_k,
    minimum,
    rated_kw,
    cut_in,
    rated,
    cut_out,
):
    rows: list[BinRow] = []
    for bin_id in range(n_bins):
        members = [i for i in range(power.size) if int(index[i]) == bin_id]
        quartile_ids = [i for i in members if flag[i] == FLAG_NORMAL]
        sample = power[quartile_ids] if quartile_ids else np.array([], dtype=float)
        left = origin + bin_id * width
        center = left + 0.5 * width
        if sample.size == 0:
            median = q1 = q3 = iqr = lower = upper = float("nan")
            applied = False
        else:
            median = empirical_quantile(sample, 0.5)
            q1 = empirical_quantile(sample, 0.25)
            q3 = empirical_quantile(sample, 0.75)
            iqr = q3 - q1
            lower = q1 - fence_k * iqr
            upper = q3 + fence_k * iqr
            applied = int(sample.size) >= minimum
            if applied:
                for i in quartile_ids:
                    if power[i] < lower or power[i] > upper:
                        flag[i] = FLAG_OUTLIER
                        reason[i] = REASON_IQR
        clean = [float(power[i]) for i in members if flag[i] == FLAG_NORMAL]
        theory = float(
            theoretical_power_kw(np.array([center]), rated_kw, cut_in, rated, cut_out)[0]
        )
        rows.append(
            BinRow(
                bin_index=bin_id,
                v_left=left,
                v_right=left + width,
                v_center=center,
                n_raw=len(members),
                n_quartile=len(quartile_ids),
                n_clean=len(clean),
                median_kw=median,
                q1_kw=q1,
                q3_kw=q3,
                iqr_kw=iqr,
                lower_kw=lower,
                upper_kw=upper,
                fence_applied=applied,
                median_clean_kw=empirical_quantile(clean, 0.5),
                theory_kw=theory,
            )
        )
    return rows


def _render(result: WindCurveResult, output_png, show: bool):
    import matplotlib.pyplot as plt

    colors = {
        FLAG_NORMAL: "#4C78A8",
        FLAG_NEGATIVE: "#B279A2",
        FLAG_SHUTDOWN: "#7F7F7F",
        FLAG_CURTAILMENT: "#F58518",
        FLAG_OUTLIER: "#E45756",
    }
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.4), sharex=True, sharey=True)
    _scatter_flags(axes[0], result, colors)
    _plot_theory(axes[0], result)
    axes[0].set_title("Before cleaning")
    kept = result.keep
    axes[1].scatter(
        result.wind_mps[kept],
        result.power_kw[kept],
        s=12,
        c=colors[FLAG_NORMAL],
        alpha=0.75,
        linewidths=0,
        label="kept",
        zorder=2,
    )
    _plot_bins(axes[1], result)
    _plot_theory(axes[1], result)
    axes[1].set_title("After cleaning")
    for axis in axes:
        axis.set_xlabel("Wind speed (m/s)")
        axis.grid(True, alpha=0.3)
    axes[0].set_ylabel("Power (kW)")
    axes[0].legend(loc="upper left", fontsize=8, frameon=False)
    axes[1].legend(loc="upper left", fontsize=8, frameon=False)
    fig.tight_layout()
    if output_png:
        path = Path(output_png)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=120)
    if show:
        plt.show()
        return fig
    plt.close(fig)
    return None


def _scatter_flags(axis, result: WindCurveResult, colors: dict[str, str]) -> None:
    order = (
        FLAG_NORMAL,
        FLAG_SHUTDOWN,
        FLAG_CURTAILMENT,
        FLAG_NEGATIVE,
        FLAG_OUTLIER,
    )
    wind = result.wind_mps
    power = result.power_kw
    for name in order:
        mask = np.array([item == name for item in result.flag], dtype=bool)
        if not np.any(mask):
            continue
        axis.scatter(
            wind[mask],
            power[mask],
            s=12,
            c=colors[name],
            alpha=0.75,
            linewidths=0,
            label=name,
            zorder=3 if name != FLAG_NORMAL else 2,
        )


def _plot_theory(axis, result: WindCurveResult) -> None:
    right = max(result.v_cut_out, float(result.wind_mps.max()) if result.n_rows else result.v_cut_out)
    grid = np.linspace(result.v_min, right, 400)
    curve = theoretical_power_kw(
        grid, result.p_rated_kw, result.v_cut_in, result.v_rated, result.v_cut_out
    )
    axis.plot(grid, curve, color="black", lw=1.2, label="theoretical", zorder=4)


def _plot_bins(axis, result: WindCurveResult) -> None:
    labeled_band = False
    labeled_median = False
    for row in result.bins:
        if row.n_quartile == 0 or math.isnan(row.q1_kw):
            continue
        axis.fill_between(
            [row.v_left, row.v_right],
            [row.q1_kw, row.q1_kw],
            [row.q3_kw, row.q3_kw],
            color="#F2C14E",
            alpha=0.35,
            linewidth=0,
            label="Q1-Q3" if not labeled_band else None,
            zorder=1,
        )
        labeled_band = True
        if row.fence_applied and not math.isnan(row.lower_kw):
            axis.plot(
                [row.v_left, row.v_right],
                [row.lower_kw, row.lower_kw],
                color="#F2C14E",
                lw=0.6,
                ls="--",
            )
            axis.plot(
                [row.v_left, row.v_right],
                [row.upper_kw, row.upper_kw],
                color="#F2C14E",
                lw=0.6,
                ls="--",
            )
        if not math.isnan(row.median_clean_kw):
            axis.plot(
                [row.v_left, row.v_right],
                [row.median_clean_kw, row.median_clean_kw],
                color="#E45756",
                lw=1.6,
                solid_capstyle="butt",
                label="bin median" if not labeled_median else None,
                zorder=3,
            )
            labeled_median = True


def _resolve_samples(source, power_kw, wind_col: str | None, power_col: str | None):
    if _is_path(source):
        if power_kw is not None:
            raise ValueError("pass a CSV path or wind and power, not both")
        return _read_csv(source, wind_col, power_col)
    if power_kw is None:
        raise ValueError("pass a CSV path or wind and power")
    if wind_col is not None or power_col is not None:
        raise ValueError("wind_col and power_col apply to CSV input")
    wind = _as_vector("wind_mps", source)
    power = _as_vector("power_kw", power_kw)
    if wind.size != power.size:
        raise ValueError("wind and power must have the same length")
    if wind.size == 0:
        raise ValueError("need at least one finite sample")
    return wind, power, 0


def _read_csv(path, wind_col: str | None, power_col: str | None):
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(str(file_path))
    text = file_path.read_text(encoding="utf-8-sig")
    if text.strip() == "":
        raise ValueError("empty csv")
    delimiter = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
    rows = list(csv.DictReader(text.splitlines(), delimiter=delimiter))
    if not rows:
        raise ValueError("empty csv")
    raw_headers = list(rows[0].keys())
    wind_key = _pick_column(raw_headers, wind_col, _WIND_ALIASES, "wind")
    power_key = _pick_column(raw_headers, power_col, _POWER_ALIASES, "power")
    wind_values: list[float] = []
    power_values: list[float] = []
    missing = 0
    for line_number, row in enumerate(rows, start=2):
        wind_text = (row.get(wind_key) or "").strip()
        power_text = (row.get(power_key) or "").strip()
        if wind_text == "" and power_text == "":
            continue
        if wind_text == "" or power_text == "":
            missing += 1
            continue
        try:
            wind_values.append(float(wind_text))
            power_values.append(float(power_text))
        except ValueError as exc:
            raise ValueError(
                f"row {line_number} is not a finite wind_mps, power_kw pair"
            ) from exc
    if not wind_values:
        raise ValueError("need at least one finite sample")
    return (
        np.asarray(wind_values, dtype=float),
        np.asarray(power_values, dtype=float),
        missing,
    )


def _pick_column(headers, requested, aliases, kind: str) -> str:
    if requested is not None:
        for header in headers:
            if header is not None and header.strip() == requested:
                return header
        raise ValueError(f"{kind} column {requested!r} not found")
    normalized = {header.strip().lower(): header for header in headers if header}
    for alias in aliases:
        if alias.lower() in normalized:
            return normalized[alias.lower()]
    raise ValueError(f"{kind} column not found")


def _check_series(wind: np.ndarray, power: np.ndarray, origin: float) -> None:
    if wind.size == 0:
        raise ValueError("need at least one finite sample")
    if not np.all(np.isfinite(wind)) or not np.all(np.isfinite(power)):
        raise ValueError("wind_mps and power_kw must be finite")
    if np.any(wind < origin):
        raise ValueError("wind_mps must be >= v_min")


def _bin_index(wind: np.ndarray, origin: float, width: float) -> np.ndarray:
    scaled = (wind - origin) / width
    return np.floor(scaled).astype(int)


def _write_points(path, result: WindCurveResult) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        handle.write(_POINT_HEADER + "\n")
        for i in range(result.n_rows):
            row = result.bins[int(result.bin_index[i])]
            handle.write(
                ",".join(
                    (
                        _num(result.wind_mps[i]),
                        _num(result.power_kw[i]),
                        _num(result.theory_kw[i]),
                        str(int(result.bin_index[i])),
                        _num(row.v_left),
                        result.flag[i],
                        result.reason[i],
                        "1" if result.keep[i] else "0",
                    )
                )
                + "\n"
            )
    return str(destination)


def _write_bins(path, result: WindCurveResult) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        handle.write(_BIN_HEADER + "\n")
        for row in result.bins:
            handle.write(
                ",".join(
                    (
                        str(row.bin_index),
                        _num(row.v_left),
                        _num(row.v_right),
                        _num(row.v_center),
                        str(row.n_raw),
                        str(row.n_quartile),
                        str(row.n_clean),
                        _num(row.median_kw),
                        _num(row.q1_kw),
                        _num(row.q3_kw),
                        _num(row.iqr_kw),
                        _num(row.lower_kw),
                        _num(row.upper_kw),
                        "1" if row.fence_applied else "0",
                        _num(row.median_clean_kw),
                        _num(row.theory_kw),
                    )
                )
                + "\n"
            )
    return str(destination)


def _num(value) -> str:
    number = float(value)
    if math.isnan(number):
        return "nan"
    return format(number, ".16g")


def _is_path(value) -> bool:
    return isinstance(value, (str, Path))


def _as_vector(name: str, value) -> np.ndarray:
    if isinstance(value, (str, bytes, Path)):
        raise ValueError(f"{name} must be a numeric vector")
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a numeric vector") from exc
    if array.ndim == 0:
        raise ValueError(f"{name} must be a numeric vector")
    return array.reshape(-1)


def _optional_text(name: str, value):
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{name} must be a column name")
    return value.strip()


def _finite_number(name: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _positive(name: str, value) -> float:
    number = _finite_number(name, value)
    if number <= 0.0:
        raise ValueError(f"{name} must be positive")
    return number


def _nonnegative(name: str, value) -> float:
    number = _finite_number(name, value)
    if number < 0.0:
        raise ValueError(f"{name} must be >= 0")
    return number


def _fraction(name: str, value) -> float:
    number = _finite_number(name, value)
    if number < 0.0 or number > 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return number


def _open_fraction(name: str, value) -> float:
    number = _finite_number(name, value)
    if number <= 0.0 or number >= 1.0:
        raise ValueError(f"{name} must be in (0, 1)")
    return number


def _positive_int(name: str, value) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer >= 1")
    number = _finite_number(name, value)
    if not number.is_integer() or number < 1.0:
        raise ValueError(f"{name} must be an integer >= 1")
    return int(number)
