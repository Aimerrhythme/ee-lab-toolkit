"""Fit one daily load curve with a polynomial and a shallow tanh MLP.

The algorithm matches ``matlab/load_curve_dnn_fit.m``. Both sides use the same
formulas, the same summation order, and the same 32-bit LCG, so a fixed
``seed`` can be compared across Python and base MATLAB. No scikit-learn
estimator and no Deep Learning Toolbox.

Time of day is scaled before either fit. With ``minute`` the minute-of-day in
``[0, 1440)``:

    u = 2 * (minute / 1440) - 1          in [-1, 1)

The load ``P`` (kW) is normalized to the training target ``y``:

    peak:    y = P / max(P)               scale = max(P),  offset = 0
    minmax:  y = (P - min(P)) / span      scale = span,    offset = min(P)
    none:    y = P                        scale = 1,       offset = 0

``span`` is ``max(P) - min(P)``. Predictions map back with
``P_hat = y_hat * scale + offset``. Reported RMSE, MAE, and maximum absolute
error are on that kilowatt residual (fit minus measured). ``poly_mse`` and
``dnn_mse`` stay on ``y``, which is the quantity both models actually fit:

    y_hat = c0 + c1 u + ... + c_d u^d
    h = tanh(w1 * u + b1)
    y_hat = sum_j w2_j h_j + b2
    MSE = mean((y_hat - y)^2)

The polynomial uses the normal equations and Gauss-Jordan elimination with
partial pivoting. The network is a 1-hidden-1 MLP (default hidden width 8),
trained with full-batch Adam for a fixed number of epochs. ``beta**t`` is a
running product of ``t`` multiplications. Hidden and output weights are drawn
from the shared LCG with Glorot uniform limits; biases start at 0. There is
no held-out hour: both residuals are in-sample.
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

DEFAULT_DEGREE = 5
DEFAULT_HIDDEN = 8
DEFAULT_EPOCHS = 2000
DEFAULT_LEARNING_RATE = 0.05
DEFAULT_BETA1 = 0.9
DEFAULT_BETA2 = 0.999
DEFAULT_EPSILON = 1e-8
DEFAULT_SEED = 0
DEFAULT_NORMALIZE = "peak"
DEFAULT_TIME_UNIT = "auto"
_LCG_A = 1664525
_LCG_C = 1013904223
_LCG_M = 4294967296
_NORMALIZE = ("peak", "minmax", "none")
_TIME_UNITS = ("auto", "hour", "minute", "dayfrac")
_PARAM_NAMES = {
    "degree",
    "hidden",
    "epochs",
    "learning_rate",
    "beta1",
    "beta2",
    "epsilon",
    "seed",
    "normalize",
    "time_unit",
    "time_col",
    "power_col",
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
_MEASURED_COLOR = "#1f4e79"
_POLY_COLOR = "#c0392b"
_DNN_COLOR = "#0e7c66"
_MONTH_DAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


@dataclass
class LoadCurveDnnFitResult:
    """In-sample polynomial and shallow-MLP fits of one daily load curve.

    ``u`` is scaled time of day and ``y`` is the normalized target. ``poly_coeff``
    is ascending powers of ``u``. ``w1``, ``b1``, ``w2``, and ``b2`` are the
    trained 1-hidden-1 tanh network. Kilowatt residuals are fit minus measured.
    RMSE, MAE, and maximum absolute error are in kW. ``poly_mse`` and ``dnn_mse``
    are mean squared error on ``y``. ``summary`` matches ``format_table``.
    """

    hour: np.ndarray
    minute: np.ndarray
    power_kw: np.ndarray
    u: np.ndarray
    y: np.ndarray
    poly_y: np.ndarray
    dnn_y: np.ndarray
    poly_kw: np.ndarray
    dnn_kw: np.ndarray
    poly_residual_kw: np.ndarray
    dnn_residual_kw: np.ndarray
    poly_coeff: np.ndarray
    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: float
    degree: int
    hidden: int
    epochs: int
    learning_rate: float
    beta1: float
    beta2: float
    epsilon: float
    seed: int
    normalize: str
    activation: str
    poly_rmse: float
    poly_mae: float
    poly_max_abs: float
    poly_mse: float
    dnn_rmse: float
    dnn_mae: float
    dnn_max_abs: float
    dnn_mse: float
    peak_kw: float
    min_kw: float
    scale_kw: float
    offset_kw: float
    date: str
    dates: list[str]
    n_samples: int
    n_days: int
    n_rows: int
    n_missing: int
    n_duplicates: int
    averaged: bool
    step_minutes: float
    summary: str
    output_csv: str | None
    output_png: str | None
    fig: object | None = None


def load_curve_dnn_fit(
    source: str | Path | Sequence | None = None,
    power: Sequence | None = None,
    *,
    degree: int = DEFAULT_DEGREE,
    hidden: int = DEFAULT_HIDDEN,
    epochs: int = DEFAULT_EPOCHS,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    beta1: float = DEFAULT_BETA1,
    beta2: float = DEFAULT_BETA2,
    epsilon: float = DEFAULT_EPSILON,
    seed: int = DEFAULT_SEED,
    normalize: str = DEFAULT_NORMALIZE,
    time_unit: str = DEFAULT_TIME_UNIT,
    time_col: str | None = None,
    power_col: str | None = None,
    day: str | None = None,
    csv_path: str | Path | None = None,
    output_csv: str | Path | None = None,
    output_png: str | Path | None = None,
    show: bool = False,
) -> LoadCurveDnnFitResult:
    """Fit a polynomial and a shallow MLP to one daily load curve.

    Parameters use the same names as the MATLAB name-value arguments.
    ``source`` is a CSV path, a power vector (uniform samples across the day),
    or, together with ``power``, timestamps or numeric time of day. Blank CSV
    power cells are dropped. Duplicate timestamps on the same day keep the
    first row. Several days that share a clock are averaged into one typical day.
    """

    degree = _integral("degree", degree, minimum=0, message="degree must be a non-negative integer")
    hidden = _integral("hidden", hidden, minimum=1, message="hidden must be a positive integer")
    epochs = _integral("epochs", epochs, minimum=1, message="epochs must be a positive integer")
    seed = _integral("seed", seed, minimum=0, message="seed must be a non-negative integer")
    learning_rate = _positive("learning_rate", learning_rate)
    beta1 = _unit_interval("beta1", beta1)
    beta2 = _unit_interval("beta2", beta2)
    epsilon = _positive("epsilon", epsilon)
    normalize = _normalize_name(normalize)
    time_unit = _time_unit_name(time_unit)
    show = _as_bool("show", show)
    minute, power_kw, date, dates, averaged, n_rows, n_missing, n_duplicates = _resolve(
        source,
        power,
        time_unit=time_unit,
        time_col=time_col,
        power_col=power_col,
        day=day,
        csv_path=csv_path,
    )
    n_samples = len(power_kw)
    if n_samples < 2:
        raise ValueError("a load curve needs at least 2 samples")
    if degree >= n_samples:
        raise ValueError(f"degree must be lower than the number of samples ({n_samples})")
    y, scale, offset, peak_kw, min_kw = _normalize_power(power_kw, normalize)
    u = [2.0 * (value / 1440.0) - 1.0 for value in minute]
    poly_coeff = _fit_polynomial(u, y, degree)
    poly_y = _eval_polynomial(u, poly_coeff)
    w1, b1, w2, b2 = _train_mlp(u, y, hidden, epochs, learning_rate, beta1, beta2, epsilon, seed)
    dnn_y = _predict_mlp(u, w1, b1, w2, b2)
    poly_kw = [value * scale + offset for value in poly_y]
    dnn_kw = [value * scale + offset for value in dnn_y]
    poly_residual = [poly_kw[index] - power_kw[index] for index in range(n_samples)]
    dnn_residual = [dnn_kw[index] - power_kw[index] for index in range(n_samples)]
    poly_rmse, poly_mae, poly_max_abs = _error_metrics(poly_residual)
    dnn_rmse, dnn_mae, dnn_max_abs = _error_metrics(dnn_residual)
    poly_mse = _mse(y, poly_y)
    dnn_mse = _mse(y, dnn_y)
    hour = [value / 60.0 for value in minute]
    step_minutes = _step_minutes(minute)
    summary = _format_result(
        n_samples=n_samples,
        degree=degree,
        hidden=hidden,
        epochs=epochs,
        learning_rate=learning_rate,
        seed=seed,
        normalize=normalize,
        date=date,
        averaged=averaged,
        step_minutes=step_minutes,
        poly_rmse=poly_rmse,
        poly_mae=poly_mae,
        poly_max_abs=poly_max_abs,
        poly_mse=poly_mse,
        dnn_rmse=dnn_rmse,
        dnn_mae=dnn_mae,
        dnn_max_abs=dnn_max_abs,
        dnn_mse=dnn_mse,
        n_rows=n_rows,
        n_missing=n_missing,
        n_duplicates=n_duplicates,
        n_days=len(dates),
        peak_kw=peak_kw,
        min_kw=min_kw,
    )
    csv_out = None if output_csv is None or str(output_csv).strip() == "" else str(output_csv)
    png_out = None if output_png is None or str(output_png).strip() == "" else str(output_png)
    result = LoadCurveDnnFitResult(
        hour=_as_array(hour),
        minute=_as_array(minute),
        power_kw=_as_array(power_kw),
        u=_as_array(u),
        y=_as_array(y),
        poly_y=_as_array(poly_y),
        dnn_y=_as_array(dnn_y),
        poly_kw=_as_array(poly_kw),
        dnn_kw=_as_array(dnn_kw),
        poly_residual_kw=_as_array(poly_residual),
        dnn_residual_kw=_as_array(dnn_residual),
        poly_coeff=_as_array(poly_coeff),
        w1=_as_array(w1),
        b1=_as_array(b1),
        w2=_as_array(w2),
        b2=float(b2),
        degree=degree,
        hidden=hidden,
        epochs=epochs,
        learning_rate=learning_rate,
        beta1=beta1,
        beta2=beta2,
        epsilon=epsilon,
        seed=seed,
        normalize=normalize,
        activation="tanh",
        poly_rmse=poly_rmse,
        poly_mae=poly_mae,
        poly_max_abs=poly_max_abs,
        poly_mse=poly_mse,
        dnn_rmse=dnn_rmse,
        dnn_mae=dnn_mae,
        dnn_max_abs=dnn_max_abs,
        dnn_mse=dnn_mse,
        peak_kw=peak_kw,
        min_kw=min_kw,
        scale_kw=scale,
        offset_kw=offset,
        date=date,
        dates=list(dates),
        n_samples=n_samples,
        n_days=len(dates),
        n_rows=n_rows,
        n_missing=n_missing,
        n_duplicates=n_duplicates,
        averaged=bool(averaged),
        step_minutes=step_minutes,
        summary=summary,
        output_csv=csv_out,
        output_png=png_out,
        fig=None,
    )
    if csv_out is not None:
        _write_curve(Path(csv_out), result)
    if png_out is not None or show:
        result.fig = _render_figure(result, png_out, show)
    return result


def format_table(result: LoadCurveDnnFitResult) -> str:
    """Format the shared one-curve residual summary."""

    return result.summary


class _LCG:
    """Numerical Recipes 32-bit LCG. The seed is the state before the first step."""

    def __init__(self, seed: int) -> None:
        self.state = int(seed) % _LCG_M

    def random(self) -> float:
        self.state = (_LCG_A * self.state + _LCG_C) % _LCG_M
        return self.state / _LCG_M


def _init_mlp(hidden: int, seed: int) -> tuple[list[float], list[float], list[float], float]:
    rng = _LCG(seed)
    limit = math.sqrt(6.0 / (1.0 + hidden))
    w1 = [(2.0 * rng.random() - 1.0) * limit for _ in range(hidden)]
    b1 = [0.0] * hidden
    w2 = [(2.0 * rng.random() - 1.0) * limit for _ in range(hidden)]
    return w1, b1, w2, 0.0


def _train_mlp(
    u: Sequence[float],
    y: Sequence[float],
    hidden: int,
    epochs: int,
    learning_rate: float,
    beta1: float,
    beta2: float,
    epsilon: float,
    seed: int,
) -> tuple[list[float], list[float], list[float], float]:
    w1, b1, w2, b2 = _init_mlp(hidden, seed)
    mw1 = [0.0] * hidden
    mb1 = [0.0] * hidden
    mw2 = [0.0] * hidden
    mb2 = 0.0
    vw1 = [0.0] * hidden
    vb1 = [0.0] * hidden
    vw2 = [0.0] * hidden
    vb2 = 0.0
    n_samples = len(u)
    inv_two_n = 2.0 / float(n_samples)
    one_minus_beta1 = 1.0 - beta1
    one_minus_beta2 = 1.0 - beta2
    # Running products, not libm pow, so Python and MATLAB apply the same beta^t.
    beta1_pow = 1.0
    beta2_pow = 1.0
    for _step in range(1, epochs + 1):
        beta1_pow *= beta1
        beta2_pow *= beta2
        gw1 = [0.0] * hidden
        gb1 = [0.0] * hidden
        gw2 = [0.0] * hidden
        gb2 = 0.0
        for index in range(n_samples):
            ui = float(u[index])
            yhat = b2
            hidden_out = [0.0] * hidden
            for unit in range(hidden):
                activated = math.tanh(w1[unit] * ui + b1[unit])
                hidden_out[unit] = activated
                yhat += w2[unit] * activated
            residual = inv_two_n * (yhat - float(y[index]))
            gb2 += residual
            for unit in range(hidden):
                activated = hidden_out[unit]
                gw2[unit] += residual * activated
                slope = residual * w2[unit] * (1.0 - activated * activated)
                gw1[unit] += slope * ui
                gb1[unit] += slope
        bias1 = 1.0 - beta1_pow
        bias2 = 1.0 - beta2_pow
        for unit in range(hidden):
            mw1[unit] = beta1 * mw1[unit] + one_minus_beta1 * gw1[unit]
            mb1[unit] = beta1 * mb1[unit] + one_minus_beta1 * gb1[unit]
            mw2[unit] = beta1 * mw2[unit] + one_minus_beta1 * gw2[unit]
            vw1[unit] = beta2 * vw1[unit] + one_minus_beta2 * gw1[unit] * gw1[unit]
            vb1[unit] = beta2 * vb1[unit] + one_minus_beta2 * gb1[unit] * gb1[unit]
            vw2[unit] = beta2 * vw2[unit] + one_minus_beta2 * gw2[unit] * gw2[unit]
            w1[unit] -= learning_rate * (mw1[unit] / bias1) / (math.sqrt(vw1[unit] / bias2) + epsilon)
            b1[unit] -= learning_rate * (mb1[unit] / bias1) / (math.sqrt(vb1[unit] / bias2) + epsilon)
            w2[unit] -= learning_rate * (mw2[unit] / bias1) / (math.sqrt(vw2[unit] / bias2) + epsilon)
        mb2 = beta1 * mb2 + one_minus_beta1 * gb2
        vb2 = beta2 * vb2 + one_minus_beta2 * gb2 * gb2
        b2 -= learning_rate * (mb2 / bias1) / (math.sqrt(vb2 / bias2) + epsilon)
    return w1, b1, w2, b2


def _predict_mlp(
    u: Sequence[float],
    w1: Sequence[float],
    b1: Sequence[float],
    w2: Sequence[float],
    b2: float,
) -> list[float]:
    hidden = len(w1)
    predicted = []
    for value in u:
        ui = float(value)
        yhat = b2
        for unit in range(hidden):
            yhat += w2[unit] * math.tanh(w1[unit] * ui + b1[unit])
        predicted.append(yhat)
    return predicted


def _fit_polynomial(u: Sequence[float], y: Sequence[float], degree: int) -> list[float]:
    width = degree + 1
    gram = [[0.0 for _ in range(width)] for _ in range(width)]
    moment = [0.0 for _ in range(width)]
    for index, value in enumerate(u):
        row = _powers(float(value), degree)
        target = float(y[index])
        for row_index in range(width):
            moment[row_index] += row[row_index] * target
            for col_index in range(width):
                gram[row_index][col_index] += row[row_index] * row[col_index]
    return _solve_linear(gram, moment)


def _eval_polynomial(u: Sequence[float], coeff: Sequence[float]) -> list[float]:
    return [_dot_powers(float(value), coeff) for value in u]


def _powers(value: float, degree: int) -> list[float]:
    row = [0.0] * (degree + 1)
    power = 1.0
    for index in range(degree + 1):
        row[index] = power
        power *= value
    return row


def _dot_powers(value: float, coeff: Sequence[float]) -> float:
    total = 0.0
    power = 1.0
    for weight in coeff:
        total += weight * power
        power *= value
    return total


def _solve_linear(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    width = len(rhs)
    aug = [matrix[row][:] + [rhs[row]] for row in range(width)]
    scale = 0.0
    for row in matrix:
        for value in row:
            magnitude = abs(value)
            if magnitude > scale:
                scale = magnitude
    if scale == 0.0:
        scale = 1.0
    tolerance = 1e-12 * scale
    for col in range(width):
        pivot = col
        best = abs(aug[col][col])
        for row in range(col + 1, width):
            magnitude = abs(aug[row][col])
            if magnitude > best:
                best = magnitude
                pivot = row
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        divisor = aug[col][col]
        if abs(divisor) <= tolerance:
            raise ValueError("polynomial design matrix is singular; try a lower degree")
        for index in range(width + 1):
            aug[col][index] /= divisor
        for row in range(width):
            if row == col:
                continue
            factor = aug[row][col]
            for index in range(width + 1):
                aug[row][index] -= factor * aug[col][index]
    return [aug[row][width] for row in range(width)]


def _normalize_power(
    power: Sequence[float],
    method: str,
) -> tuple[list[float], float, float, float, float]:
    peak = _max_value(power)
    trough = _min_value(power)
    if method == "none":
        return [float(value) for value in power], 1.0, 0.0, peak, trough
    if method == "peak":
        if not peak > 0.0:
            raise ValueError("peak normalization needs a positive peak")
        return [float(value) / peak for value in power], peak, 0.0, peak, trough
    span = peak - trough
    if not span > 0.0:
        raise ValueError("min-max normalization needs the load to vary")
    return [(float(value) - trough) / span for value in power], span, trough, peak, trough


def _error_metrics(residual: Sequence[float]) -> tuple[float, float, float]:
    total_sq = 0.0
    total_abs = 0.0
    max_abs = 0.0
    count = len(residual)
    for value in residual:
        magnitude = abs(float(value))
        total_sq += float(value) * float(value)
        total_abs += magnitude
        if magnitude > max_abs:
            max_abs = magnitude
    return math.sqrt(total_sq / float(count)), total_abs / float(count), max_abs


def _mse(target: Sequence[float], predicted: Sequence[float]) -> float:
    total = 0.0
    count = len(target)
    for index in range(count):
        gap = float(predicted[index]) - float(target[index])
        total += gap * gap
    return total / float(count)


def _resolve(
    source: object,
    power: object,
    *,
    time_unit: str,
    time_col: object,
    power_col: object,
    day: object,
    csv_path: object,
) -> tuple[list[float], list[float], str, list[str], bool, int, int, int]:
    if isinstance(source, str) and _is_parameter_name(source):
        raise ValueError(
            f"{source.strip()!r} is a parameter name. Pass the CSV path, a power vector, "
            "or time and power as the first argument."
        )
    if power is not None:
        return _from_series(source, power, time_unit, time_col, power_col, day, csv_path)
    if _is_numeric_vector(source):
        return _from_power_only(source, time_unit, time_col, power_col, day, csv_path)
    return _from_csv(source, time_unit, time_col, power_col, day, csv_path)


def _from_series(
    source: object,
    power: object,
    time_unit: str,
    time_col: object,
    power_col: object,
    day: object,
    csv_path: object,
) -> tuple[list[float], list[float], str, list[str], bool, int, int, int]:
    if _path_text(csv_path) is not None:
        raise ValueError("pass time and power, or a CSV path, not both")
    if _given(time_col) or _given(power_col):
        raise ValueError("time_col and power_col apply to a CSV, not to time and power vectors")
    values = _power_vector(power)
    if _is_numeric_vector(source):
        minutes, _basis = _numeric_minutes(_power_vector(source, "time"), time_unit)
        if len(minutes) != len(values):
            raise ValueError("time and power must have the same length")
        label = _vector_day(day)
        samples = [(label, minutes[index], values[index]) for index in range(len(values))]
        return _pack_samples(samples, 0)
    if time_unit != "auto":
        raise ValueError("time_unit applies to numeric time, not timestamps")
    if _given(day):
        raise ValueError("day applies to numeric time or a power vector, not to timestamps")
    stamped = _timestamp_samples(source, values)
    return _pack_samples(stamped, 0)


def _from_power_only(
    source: object,
    time_unit: str,
    time_col: object,
    power_col: object,
    day: object,
    csv_path: object,
) -> tuple[list[float], list[float], str, list[str], bool, int, int, int]:
    if _path_text(csv_path) is not None:
        raise ValueError("pass a power vector or a CSV path, not both")
    if time_unit != "auto":
        raise ValueError("time_unit applies when time is passed")
    if _given(time_col) or _given(power_col):
        raise ValueError("time_col and power_col apply to a CSV, not to a power vector")
    values = _power_vector(source)
    count = len(values)
    step = 1440.0 / float(count)
    label = _vector_day(day)
    samples = [(label, index * step, values[index]) for index in range(count)]
    return _pack_samples(samples, 0)


def _from_csv(
    source: object,
    time_unit: str,
    time_col: object,
    power_col: object,
    day: object,
    csv_path: object,
) -> tuple[list[float], list[float], str, list[str], bool, int, int, int]:
    if time_unit != "auto":
        raise ValueError("time_unit applies to numeric time, not a CSV")
    if _given(day):
        raise ValueError("day applies to numeric time or a power vector, not a CSV")
    path = _path_text(csv_path)
    if isinstance(source, (str, Path)) and str(source).strip() != "":
        if path is not None:
            raise ValueError("pass a CSV path once, either positionally or as csv_path=")
        path = str(source).strip()
    elif source is not None:
        raise TypeError("source must be a CSV path, a power vector, or time with power")
    if path is None:
        raise ValueError("pass a CSV path, a power vector, or time and power")
    rows, n_missing = _read_csv_rows(Path(path), time_col, power_col)
    samples = [(f"{year:04d}-{month:02d}-{day_number:02d}", minute, power) for year, month, day_number, minute, power in rows]
    return _pack_samples(samples, n_missing)


def _pack_samples(
    samples: Sequence[tuple[str, float, float]],
    n_missing: int,
) -> tuple[list[float], list[float], str, list[str], bool, int, int, int]:
    cleaned, n_duplicates = _drop_duplicates(samples)
    if not cleaned:
        raise ValueError("No power samples remain after cleaning")
    minute, power, date, dates, averaged = _curve_from_samples(cleaned)
    return minute, power, date, dates, averaged, len(cleaned), n_missing, n_duplicates


def _drop_duplicates(
    samples: Sequence[tuple[str, float, float]],
) -> tuple[list[tuple[str, float, float]], int]:
    ordered = sorted(enumerate(samples), key=lambda item: (item[1][0], item[1][1], item[0]))
    kept: list[tuple[str, float, float]] = []
    duplicates = 0
    for _index, item in ordered:
        if kept:
            previous = kept[-1]
            if previous[0] == item[0] and abs(previous[1] - item[1]) <= 1e-9:
                duplicates += 1
                continue
        kept.append(item)
    return kept, duplicates


def _curve_from_samples(
    samples: Sequence[tuple[str, float, float]],
) -> tuple[list[float], list[float], str, list[str], bool]:
    days: list[tuple[str, list[tuple[float, float]]]] = []
    for date, minute, power in samples:
        if not days or days[-1][0] != date:
            days.append((date, []))
        days[-1][1].append((minute, power))
    for date, bucket in days:
        if len(bucket) < 2:
            raise ValueError(f"each day needs at least 2 samples (date {date})")
        for index in range(1, len(bucket)):
            if bucket[index][0] <= bucket[index - 1][0]:
                raise ValueError(f"timestamps on {date} must be strictly increasing")
    dates = [date for date, _bucket in days]
    if len(days) == 1:
        bucket = days[0][1]
        return [minute for minute, _power in bucket], [power for _minute, power in bucket], dates[0], dates, False
    grid = [minute for minute, _power in days[0][1]]
    for date, bucket in days[1:]:
        if len(bucket) != len(grid):
            raise ValueError("each day must share the same minute-of-day grid to build a typical day")
        for index, (minute, _power) in enumerate(bucket):
            if abs(minute - grid[index]) > 1e-6:
                raise ValueError(
                    f"each day must share the same minute-of-day grid to build a typical day (date {date})"
                )
    total = [0.0] * len(grid)
    for _date, bucket in days:
        for index, (_minute, power) in enumerate(bucket):
            total[index] += power
    count = float(len(days))
    average = [value / count for value in total]
    return grid, average, "typical", dates, True


def _numeric_minutes(values: Sequence[float], time_unit: str) -> tuple[list[float], str]:
    if time_unit == "auto":
        time_unit = _infer_time_unit(values)
    if time_unit == "hour":
        for value in values:
            if value < 0.0 or value >= 24.0:
                raise ValueError("numeric hours must be in [0, 24)")
        return [float(value) * 60.0 for value in values], "hour"
    if time_unit == "minute":
        for value in values:
            if value < 0.0 or value >= 1440.0:
                raise ValueError("numeric minutes must be in [0, 1440)")
        return [float(value) for value in values], "minute"
    for value in values:
        if value < 0.0 or value >= 1.0:
            raise ValueError("day fractions must be in [0, 1)")
    return [float(value) * 1440.0 for value in values], "dayfrac"


def _infer_time_unit(values: Sequence[float]) -> str:
    lowest = _min_value(values)
    highest = _max_value(values)
    if lowest >= 0.0 and highest < 24.0:
        return "hour"
    if lowest >= 0.0 and highest < 1440.0:
        return "minute"
    raise ValueError("could not infer time_unit; pass hour, minute, or dayfrac")


def _timestamp_samples(time: object, power: Sequence[float]) -> list[tuple[str, float, float]]:
    stamps = _time_parts(time)
    if len(stamps) != len(power):
        raise ValueError("time and power must have the same length")
    samples = []
    for index, (year, month, day_number, minute) in enumerate(stamps):
        samples.append((f"{year:04d}-{month:02d}-{day_number:02d}", minute, float(power[index])))
    return samples


def _time_parts(time: object) -> list[tuple[int, int, int, float]]:
    if isinstance(time, np.ndarray) and np.issubdtype(time.dtype, np.datetime64):
        return [_parts_from_datetime(_datetime64_to_datetime(item)) for item in time.reshape(-1)]
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
            raise ValueError("time must be a vector of timestamps or numbers")
    return parts


def _as_list(value: object) -> list[object]:
    if isinstance(value, np.ndarray):
        if value.ndim > 2 or (value.ndim == 2 and 1 not in value.shape):
            raise ValueError("time must be a vector of timestamps or numbers")
        return [item for item in value.reshape(-1)]
    if isinstance(value, (str, datetime)):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    raise ValueError("time must be a vector of timestamps or numbers")


def _power_vector(value: object, name: str = "power") -> list[float]:
    if isinstance(value, (str, bytes, Path, datetime)):
        raise ValueError(f"{name} must be a numeric vector")
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be a numeric vector")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if any(isinstance(item, bool) for item in value):
            raise ValueError(f"{name} must be a numeric vector")
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a numeric vector") from exc
    if array.ndim == 2 and 1 in array.shape:
        array = array.reshape(-1)
    if array.ndim != 1:
        raise ValueError(f"{name} must be a numeric vector")
    if array.size == 0:
        raise ValueError(f"{name} must not be empty")
    values = [float(item) for item in array]
    for item in values:
        if not math.isfinite(item):
            raise ValueError(f"{name} must be finite")
    return values


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
        year, month, day_number, minute = _parse_timestamp(time_text)
        try:
            value = float(power_text)
        except ValueError as exc:
            raise ValueError("power must be finite") from exc
        if not math.isfinite(value):
            raise ValueError("power must be finite")
        rows.append((year, month, day_number, minute, value))
    if not rows and n_missing == 0:
        raise ValueError(f"CSV has no data rows: {path}")
    return rows, n_missing


def _resolve_column(
    columns: Sequence[str],
    requested: object,
    aliases: Sequence[str],
    kind: str,
) -> str:
    pairs = [(_norm_key(column), column) for column in columns if column != ""]
    if _given(requested):
        requested_text = str(requested).strip()
        for column in columns:
            if column == requested_text:
                return column
        requested_norm = _norm_key(requested_text)
        for norm, column in pairs:
            if norm == requested_norm:
                return column
        known = ", ".join(column for column in columns if column != "")
        raise ValueError(f"Column {requested_text!r} not found for {kind}. Available: {known}")
    for alias in aliases:
        alias_norm = _norm_key(alias)
        for norm, column in pairs:
            if norm == alias_norm:
                return column
    known = ", ".join(column for column in columns if column != "")
    raise ValueError(f"Could not find a {kind} column. Pass {kind}_col explicitly. Available: {known}")


def _vector_day(day: object) -> str:
    if not _given(day):
        return "day-01"
    return _parse_day(str(day))


def _step_minutes(minute: Sequence[float]) -> float:
    if len(minute) < 2:
        return math.nan
    first = float(minute[1]) - float(minute[0])
    limit = 1e-6 * max(abs(first), 1.0)
    for index in range(1, len(minute)):
        if abs((float(minute[index]) - float(minute[index - 1])) - first) > limit:
            return math.nan
    return first


def _format_result(
    *,
    n_samples: int,
    degree: int,
    hidden: int,
    epochs: int,
    learning_rate: float,
    seed: int,
    normalize: str,
    date: str,
    averaged: bool,
    step_minutes: float,
    poly_rmse: float,
    poly_mae: float,
    poly_max_abs: float,
    poly_mse: float,
    dnn_rmse: float,
    dnn_mae: float,
    dnn_max_abs: float,
    dnn_mse: float,
    n_rows: int,
    n_missing: int,
    n_duplicates: int,
    n_days: int,
    peak_kw: float,
    min_kw: float,
) -> str:
    header = (
        f"n={n_samples}  degree={degree}  hidden={hidden}  epochs={epochs}  "
        f"lr={_compact(learning_rate)}  seed={seed}  normalize={normalize}  "
        f"date={date}  averaged={1 if averaged else 0}  step_min={_compact(step_minutes)}"
    )
    poly = (
        f"poly_rmse={_compact(poly_rmse)}  poly_mae={_compact(poly_mae)}  "
        f"poly_max_abs={_compact(poly_max_abs)}  poly_mse={_compact(poly_mse)}"
    )
    dnn = (
        f"dnn_rmse={_compact(dnn_rmse)}  dnn_mae={_compact(dnn_mae)}  "
        f"dnn_max_abs={_compact(dnn_max_abs)}  dnn_mse={_compact(dnn_mse)}"
    )
    rows = (
        f"rows={n_rows}  missing={n_missing}  duplicates={n_duplicates}  "
        f"days={n_days}  peak_kw={_compact(peak_kw)}  min_kw={_compact(min_kw)}"
    )
    return "\n\n".join([header, poly, dnn, rows])


def _write_curve(path: Path, result: LoadCurveDnnFitResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["hour", "minute", "power_kw", "poly_kw", "dnn_kw", "poly_residual_kw", "dnn_residual_kw"]
        )
        for index in range(result.n_samples):
            writer.writerow(
                [
                    _csv_num(float(result.hour[index])),
                    _csv_num(float(result.minute[index])),
                    _csv_num(float(result.power_kw[index])),
                    _csv_num(float(result.poly_kw[index])),
                    _csv_num(float(result.dnn_kw[index])),
                    _csv_num(float(result.poly_residual_kw[index])),
                    _csv_num(float(result.dnn_residual_kw[index])),
                ]
            )


def _render_figure(result: LoadCurveDnnFitResult, output_png: str | None, show: bool) -> object | None:
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
        curve_axis, residual_axis = axes
        curve_axis.plot(result.hour, result.power_kw, color=_MEASURED_COLOR, lw=2.2, label="measured")
        curve_axis.plot(
            result.hour,
            result.poly_kw,
            color=_POLY_COLOR,
            lw=1.8,
            ls="--",
            label=f"polynomial (degree {result.degree})",
        )
        curve_axis.plot(
            result.hour,
            result.dnn_kw,
            color=_DNN_COLOR,
            lw=2.0,
            label=f"DNN (1-{result.hidden}-1 tanh)",
        )
        residual_axis.plot(
            result.hour,
            result.poly_residual_kw,
            color=_POLY_COLOR,
            lw=1.6,
            ls="--",
            label="polynomial residual",
        )
        residual_axis.plot(
            result.hour,
            result.dnn_residual_kw,
            color=_DNN_COLOR,
            lw=1.8,
            label="DNN residual",
        )
        residual_axis.axhline(0.0, color="#888888", lw=0.8, label=None)
        fig.suptitle(
            "Daily load fit    "
            f"poly RMSE={_compact(result.poly_rmse)} kW    "
            f"DNN RMSE={_compact(result.dnn_rmse)} kW",
            fontsize=13,
        )
        _style_axis(curve_axis, "Measured load and fits", "Power (kW)", result.hour)
        _style_axis(residual_axis, "Residual (fit - measured)", "Residual (kW)", result.hour)
        residual_axis.set_xlabel("Hour of day")
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
    if len(hour):
        span = float(hour[-1] - hour[0]) if len(hour) > 1 else 1.0
        pad = 0.04 * span if span > 0.0 else 0.5
        axis.set_xlim(float(hour[0]) - pad, float(hour[-1]) + pad)


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


def _parts_from_datetime(value: datetime) -> tuple[int, int, int, float]:
    if value.tzinfo is not None:
        raise ValueError("timestamps must be naive local time")
    minute = value.hour * 60.0 + value.minute + value.second / 60.0 + value.microsecond / 60_000_000.0
    if not _valid_date(value.year, value.month, value.day):
        raise ValueError("could not parse timestamp")
    return value.year, value.month, value.day, minute


def _datetime64_to_datetime(value: np.datetime64) -> datetime:
    converted = value.astype("datetime64[us]").item()
    if not isinstance(converted, datetime):
        raise ValueError("could not parse timestamp")
    return converted


def _is_numeric_vector(value: object) -> bool:
    if isinstance(value, (str, bytes, Path, datetime, bool)) or value is None:
        return False
    if isinstance(value, np.ndarray):
        if value.size == 0 or not np.issubdtype(value.dtype, np.number) or np.issubdtype(value.dtype, np.bool_):
            return False
        return value.ndim == 1 or (value.ndim == 2 and 1 in value.shape)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) > 0:
        return all(isinstance(item, Real) and not isinstance(item, bool) for item in value)
    return False


def _max_value(values: Sequence[float]) -> float:
    best = float(values[0])
    for value in values[1:]:
        number = float(value)
        if number > best:
            best = number
    return best


def _min_value(values: Sequence[float]) -> float:
    best = float(values[0])
    for value in values[1:]:
        number = float(value)
        if number < best:
            best = number
    return best


def _as_array(values: Sequence[float]) -> np.ndarray:
    return np.ascontiguousarray(values, dtype=float)


def _compact(value: float) -> str:
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
        raise ValueError("normalize must be peak, minmax, or none")
    name = value.strip().lower()
    if name not in _NORMALIZE:
        raise ValueError("normalize must be peak, minmax, or none")
    return name


def _time_unit_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("time_unit must be auto, hour, minute, or dayfrac")
    name = value.strip().lower()
    if name not in _TIME_UNITS:
        raise ValueError("time_unit must be auto, hour, minute, or dayfrac")
    return name


def _integral(name: str, value: object, *, minimum: int, message: str) -> int:
    del name
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


def _unit_interval(label: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be in [0, 1)")
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or number >= 1.0:
        raise ValueError(f"{label} must be in [0, 1)")
    return number


def _as_bool(label: str, value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, np.integer)) and int(value) in (0, 1):
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


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _valid_date(year: int, month: int, day: int) -> bool:
    if year < 1 or year > 9999 or month < 1 or month > 12:
        return False
    limit = _MONTH_DAYS[month]
    if month == 2 and _leap(year):
        limit = 29
    return 1 <= day <= limit
