"""Single-sided spectrum, harmonic table, and THD for a sampled waveform.

The calculations match ``matlab/fft_thd.m``.

1. Read a uniform record (CSV, or time and signal arrays).
2. Build the single-sided peak-amplitude spectrum. ``window='auto'`` uses a
   rectangular window when the record is within 0.02 cycle of an integer
   number of periods, and a periodic Hann window otherwise.
3. Use the supplied fundamental ``f0``, or detect it: Hann peak, log-magnitude
   parabolic interpolation, then a few Newton steps on the harmonic-model
   residual. A peak that already sits on a bin is kept on that bin.
4. Fit ``dc + sum Ah*sin(2*pi*h*f0*t + phih)`` by least squares. This is the
   harmonic table. It stays accurate when the period does not land on a bin;
   the window only changes the plotted spectrum.
5. THD is the RMS of the harmonic peaks over the fundamental peak. DC is not
   included. Peak or RMS ratios are the same number.

Phase is referenced to the first sample (``t = 0`` there), in the sine form
above. ``t`` in that expression is ``(0:N-1)/fs``, not an absolute timestamp.
"""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

BIN_TOL = 0.02
NEWTON_STEPS = 3
NEWTON_STEP_BINS = 0.2
NEWTON_SHIFT_BINS = 0.6
NEWTON_SHRINK = 0.2
PHASE_REL_TOL = 1e-8
MIN_SAMPLES = 16
MAX_HARMONICS = 500
MARKER_PERCENT = 0.2
DEFAULT_N_HARMONICS = 25
DEFAULT_F_SEARCH_MIN = 10.0

_TIME_ALIASES = ("times", "time", "timestamp", "t")
_SIGNAL_ALIASES = (
    "signal",
    "value",
    "voltage",
    "current",
    "waveform",
    "samples",
    "sample",
    "x",
    "v",
    "i",
)

_PARAM_NAMES = {
    "signal",
    "fs",
    "f0",
    "n_harmonics",
    "window",
    "remove_dc",
    "f_search_min",
    "f_search_max",
    "amp_floor_ratio",
    "output_csv",
    "output_png",
    "show",
}


@dataclass
class HarmonicRow:
    """One integer harmonic of ``f0``.

    ``amplitude`` is the sine peak. ``rms`` is ``amplitude / sqrt(2)``.
    ``percent`` is ``100 * amplitude / fundamental``. ``in_thd`` is true when
    this order is included in the THD numerator (order >= 2 and at or above
    ``amp_floor_ratio``).
    """

    order: int
    frequency_hz: float
    amplitude: float
    rms: float
    percent: float
    phase_rad: float
    phase_deg: float
    in_thd: bool


@dataclass
class FftThdResult:
    """Spectrum, harmonic table, and THD for one record.

    ``spectrum_frequency`` / ``spectrum_amplitude`` are the single-sided peak
    spectrum (DC bin included). ``harmonics`` starts at order 1. ``window`` is
    the window actually used for that spectrum (``rect`` or ``hann``).
    ``f0_source`` is ``given`` or ``detected``. ``signal_rms`` is the AC RMS
    about the fitted DC.
    """

    fs: float
    f0: float
    f0_source: str
    n_samples: int
    cycles: float
    window: str
    remove_dc: bool
    dc: float
    fundamental_amplitude: float
    fundamental_rms: float
    signal_rms: float
    thd: float
    thd_percent: float
    n_harmonics: int
    amp_floor_ratio: float
    spectrum_frequency: np.ndarray
    spectrum_amplitude: np.ndarray
    harmonics: list[HarmonicRow]
    time: np.ndarray
    signal: np.ndarray
    output_csv: str | None
    output_png: str | None
    fig: object | None = None


def fft_thd(
    source: object = None,
    signal: object = None,
    *,
    fs: float | None = None,
    f0: float | None = None,
    n_harmonics: int = DEFAULT_N_HARMONICS,
    window: str = "auto",
    remove_dc: bool = True,
    f_search_min: float = DEFAULT_F_SEARCH_MIN,
    f_search_max: float | None = None,
    amp_floor_ratio: float = 0.0,
    output_csv: str | Path | None = None,
    output_png: str | Path | None = None,
    show: bool = False,
) -> FftThdResult:
    """Estimate harmonics and THD for one uniformly sampled waveform.

    Parameters use the same names as the MATLAB name-value arguments.
    ``source`` may be a CSV path, a signal array (pass ``fs``), or a time
    array when ``signal`` is also given. CSV columns: ``time_s`` and
    ``signal`` (see the README for accepted names).
    """

    time, values = _resolve_inputs(source, signal)
    n_harmonics = _positive_int("n_harmonics", n_harmonics, maximum=MAX_HARMONICS)
    remove_dc = _as_bool("remove_dc", remove_dc)
    show = _as_bool("show", show)
    f_search_min = _finite("f_search_min", f_search_min)
    if f_search_max is not None:
        f_search_max = _finite("f_search_max", f_search_max)
    amp_floor_ratio = _finite("amp_floor_ratio", amp_floor_ratio)
    if amp_floor_ratio < 0:
        raise ValueError("amp_floor_ratio must be >= 0")
    fs_used = _resolve_fs(time, values, fs)
    if f_search_min < 0 or f_search_min >= fs_used / 2.0:
        raise ValueError("f_search_min must be >= 0 and below the Nyquist frequency")
    search_max = fs_used / 2.0 if f_search_max is None else f_search_max
    if search_max <= f_search_min or search_max > fs_used / 2.0 + 1e-9:
        raise ValueError("f_search_max must be above f_search_min and at most the Nyquist frequency")

    f0_given = None if f0 is None else _finite("f0", f0)
    if f0_given is not None:
        if f0_given <= 0 or f0_given >= fs_used / 2.0:
            raise ValueError("f0 must be positive and below the Nyquist frequency")
        f0_used = f0_given
        f0_source = "given"
    else:
        f0_used = _detect_f0(
            values,
            fs_used,
            n_harmonics=n_harmonics,
            f_search_min=f_search_min,
            f_search_max=search_max,
        )
        f0_source = "detected"

    window_used = _resolve_window(window, len(values), fs_used, f0_used)
    spectrum_frequency, spectrum_amplitude = _single_sided(
        values, fs_used, window_used, remove_dc=remove_dc
    )
    dc, harmonics, signal_rms = _harmonic_table(
        values,
        fs_used,
        f0_used,
        n_harmonics=n_harmonics,
        amp_floor_ratio=amp_floor_ratio,
    )
    csv_out = None if output_csv is None or str(output_csv).strip() == "" else str(output_csv)
    png_out = None if output_png is None or str(output_png).strip() == "" else str(output_png)
    if time is None:
        time = np.arange(len(values), dtype=float) / fs_used
    result = FftThdResult(
        fs=fs_used,
        f0=f0_used,
        f0_source=f0_source,
        n_samples=len(values),
        cycles=float(len(values) * f0_used / fs_used),
        window=window_used,
        remove_dc=remove_dc,
        dc=dc,
        fundamental_amplitude=harmonics[0].amplitude,
        fundamental_rms=harmonics[0].rms,
        signal_rms=signal_rms,
        thd=_thd_fraction(harmonics),
        thd_percent=100.0 * _thd_fraction(harmonics),
        n_harmonics=n_harmonics,
        amp_floor_ratio=amp_floor_ratio,
        spectrum_frequency=spectrum_frequency,
        spectrum_amplitude=spectrum_amplitude,
        harmonics=harmonics,
        time=time,
        signal=values,
        output_csv=csv_out,
        output_png=png_out,
        fig=None,
    )
    if csv_out is not None:
        _write_csv(Path(csv_out), result.harmonics)
    if png_out is not None or show:
        result.fig = _render_figure(result, png_out, show)
    return result


def format_table(result: FftThdResult) -> str:
    """Format the THD summary and the harmonic table as text."""

    lines = [
        (
            f"f0={_compact(result.f0)} Hz ({result.f0_source})  "
            f"fs={_compact(result.fs)} Hz  N={result.n_samples}  "
            f"cycles={result.cycles:.4f}  window={result.window}"
        ),
        (
            f"dc={_compact(result.dc)}  A1={_compact(result.fundamental_amplitude)}  "
            f"THD={result.thd_percent:.4f}%  floor={_compact(result.amp_floor_ratio)}"
        ),
        (
            f"{'order':>5} {'frequency_Hz':>14} {'amplitude':>12} {'rms':>12} "
            f"{'percent':>10} {'phase_deg':>10} {'in_thd':>6}"
        ),
    ]
    for row in result.harmonics:
        lines.append(
            f"{row.order:5d} {row.frequency_hz:14.4f} {row.amplitude:12.4f} "
            f"{row.rms:12.4f} {row.percent:10.4f} {row.phase_deg:10.3f} {int(row.in_thd):6d}"
        )
    return "\n".join(lines)


def _thd_fraction(harmonics: Sequence[HarmonicRow]) -> float:
    a1 = harmonics[0].amplitude
    total = 0.0
    for row in harmonics:
        if row.in_thd:
            total += row.amplitude * row.amplitude
    return math.sqrt(total) / a1


def _compact(value: float) -> str:
    if not math.isfinite(value):
        return "nan"
    text = f"{value:.6g}"
    if "e" not in text and "E" not in text:
        return text
    if abs(value - round(value)) <= 1e-6 * max(abs(value), 1.0):
        return f"{value:.0f}"
    return f"{value:.4f}"


def _resolve_inputs(source: object, signal: object) -> tuple[np.ndarray | None, np.ndarray]:
    if _is_path(source):
        text = str(source).strip()
        if text.lower() in _PARAM_NAMES:
            raise ValueError(
                f"{text!r} is a parameter name. Pass the CSV path as the first argument"
            )
        if signal is not None:
            raise ValueError("pass a CSV path or arrays, not both")
        return _read_waveform_csv(Path(text))
    if source is None and signal is None:
        raise ValueError("pass a CSV path, a signal array, or time and signal arrays")
    if source is not None and signal is not None:
        time = _as_signal("time", source)
        values = _as_signal("signal", signal)
        if time.shape != values.shape:
            raise ValueError("time and signal must have the same length")
        return time, values
    if source is not None:
        return None, _as_signal("signal", source)
    return None, _as_signal("signal", signal)


def _is_path(value: object) -> bool:
    return isinstance(value, (str, Path))


def _as_signal(label: str, value: object) -> np.ndarray:
    if isinstance(value, (str, bytes, Path)):
        raise ValueError(f"{label} must be a numeric array")
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a numeric array") from exc
    if array.ndim == 2 and 1 in array.shape:
        array = np.ravel(array)
    if array.ndim != 1:
        raise ValueError(f"{label} must be a one-dimensional array")
    if array.size < MIN_SAMPLES:
        raise ValueError(f"{label} must contain at least {MIN_SAMPLES} samples")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{label} contains a non-finite value")
    return np.ascontiguousarray(array, dtype=float)


def _resolve_fs(time: np.ndarray | None, values: np.ndarray, fs: float | None) -> float:
    inferred = None if time is None else _fs_from_time(time)
    given = None if fs is None else _positive("fs", fs)
    if inferred is None and given is None:
        raise ValueError("fs is required when the input has no time column")
    if inferred is not None and given is not None:
        if abs(inferred - given) > 1e-3 * inferred:
            raise ValueError("fs does not match the time step in the data")
        return inferred
    if inferred is not None:
        return inferred
    assert given is not None
    return given


def _fs_from_time(time: np.ndarray) -> float:
    if np.any(np.diff(time) <= 0):
        raise ValueError("time must be strictly increasing")
    dt = np.diff(time)
    median = float(np.median(dt))
    if median <= 0 or not math.isfinite(median):
        raise ValueError("time step must be a positive finite number")
    span = float(np.max(dt) - np.min(dt))
    if span > 1e-4 * median:
        raise ValueError("time step is not uniform; resample before calling fft_thd")
    return 1.0 / median


def _read_waveform_csv(path: Path) -> tuple[np.ndarray | None, np.ndarray]:
    rows = _read_csv_rows(path)
    header = list(rows[0].keys())
    folded = {_norm_key(name): name for name in header}
    time_alias = _first_present(folded, _TIME_ALIASES)
    signal_alias = _first_present(folded, _SIGNAL_ALIASES)
    time_key = None if time_alias is None else folded[time_alias]
    if signal_alias is not None:
        signal_key = folded[signal_alias]
    else:
        numeric = [name for name in header if name != "" and name != time_key]
        if len(numeric) != 1:
            raise ValueError("CSV needs a signal column (signal, value, voltage, current, ...)")
        signal_key = numeric[0]
    if time_key == signal_key:
        time_key = None
    times: list[float] = []
    values: list[float] = []
    for index, row in enumerate(rows, start=1):
        raw_value = row.get(signal_key, "")
        if str(raw_value).strip() == "":
            raise ValueError(f"signal is missing on CSV row {index}")
        values.append(_finite(f"signal row {index}", raw_value))
        if time_key is not None:
            raw_time = row.get(time_key, "")
            if str(raw_time).strip() == "":
                raise ValueError(f"time is missing on CSV row {index}")
            times.append(_finite(f"time row {index}", raw_time))
    signal = _as_signal("signal", values)
    if time_key is None:
        return None, signal
    return _as_signal("time", times), signal


def _first_present(folded: dict[str, str], aliases: Sequence[str]) -> str | None:
    for alias in aliases:
        if alias in folded:
            return alias
    return None


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
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
        rows: list[dict[str, str]] = []
        for raw in reader:
            if raw is None:
                continue
            cleaned = {
                ("" if key is None else str(key).strip()): "" if value is None else str(value).strip()
                for key, value in raw.items()
            }
            if all(item == "" for item in cleaned.values()):
                continue
            rows.append(cleaned)
    if not rows:
        raise ValueError(f"CSV has no data rows: {path}")
    return rows


def _norm_key(key: object) -> str:
    return re.sub(r"[\s_\-]", "", str(key).strip().lower())


def _finite(label: str, value: object) -> float:
    if isinstance(value, (bool, str, bytes)):
        try:
            number = float(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be a finite number") from exc
    elif isinstance(value, (int, float, np.floating, np.integer)):
        number = float(value)
    else:
        raise ValueError(f"{label} must be a finite number")
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _positive(label: str, value: object) -> float:
    number = _finite(label, value)
    if number <= 0:
        raise ValueError(f"{label} must be a positive finite number")
    return number


def _positive_int(label: str, value: object, *, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    number = _finite(label, value)
    if abs(number - round(number)) > 1e-9:
        raise ValueError(f"{label} must be a positive integer")
    integer = round(number)
    if integer < 1 or integer > maximum:
        raise ValueError(f"{label} must be an integer from 1 to {maximum}")
    return integer


def _as_bool(label: str, value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool) and int(value) in (0, 1):
        return bool(int(value))
    raise ValueError(f"{label} must be true or false")


def _resolve_window(window: object, n: int, fs: float, f0: float) -> str:
    key = _norm_key(window)
    if key == "auto":
        cycles = n * f0 / fs
        if abs(cycles - round(cycles)) <= BIN_TOL:
            return "rect"
        return "hann"
    if key in {"rect", "rectangular", "boxcar", "none"}:
        return "rect"
    if key in {"hann", "hanning"}:
        return "hann"
    raise ValueError("window must be 'auto', 'rect', or 'hann'")


def _window(n: int, kind: str) -> np.ndarray:
    if kind == "rect":
        return np.ones(n, dtype=float)
    # Periodic Hann. sum(w) = n/2 for n > 1, so an on-bin sine still reads
    # its true peak after coherent-gain scaling. Shoulders sit on the
    # adjacent bins.
    k = np.arange(n, dtype=float)
    return 0.5 - 0.5 * np.cos(2.0 * math.pi * k / n)


def _single_sided(
    values: np.ndarray,
    fs: float,
    window: str,
    *,
    remove_dc: bool,
) -> tuple[np.ndarray, np.ndarray]:
    x = values - float(np.mean(values)) if remove_dc else values
    weights = _window(len(x), window)
    spectrum = np.fft.fft(x * weights)
    n = len(x)
    n_half = n // 2
    amplitude = np.abs(spectrum[: n_half + 1]) / float(np.sum(weights))
    if n > 1:
        amplitude[1:] *= 2.0
        if n % 2 == 0:
            amplitude[-1] *= 0.5
    frequency = np.arange(n_half + 1, dtype=float) * (fs / n)
    return frequency, amplitude


def _detect_f0(
    values: np.ndarray,
    fs: float,
    *,
    n_harmonics: int,
    f_search_min: float,
    f_search_max: float,
) -> float:
    frequency, amplitude = _single_sided(values, fs, "hann", remove_dc=True)
    band = np.where((frequency >= f_search_min) & (frequency <= f_search_max) & (frequency > 0))[0]
    if band.size == 0:
        raise ValueError("no spectrum bin falls inside the fundamental search band")
    local = int(band[int(np.argmax(amplitude[band]))])
    if amplitude[local] <= 1e-15:
        raise ValueError("no spectral peak in the search band; pass f0 or widen f_search_min/f_search_max")
    delta = _log_parabolic_delta(amplitude, local)
    df = fs / len(values)
    if abs(delta) <= BIN_TOL:
        # Shoulders are symmetric: the tone is already on this bin.
        return local * df
    fhat = (local + delta) * df
    orders = _orders_for(fs, fhat, n_harmonics)
    step = NEWTON_STEP_BINS * df
    f_cap = (fs / 2.0) / orders[-1] - 1e-9
    f_floor = max(f_search_min, df)
    for _ in range(NEWTON_STEPS):
        center = min(max(fhat, f_floor), f_cap)
        plus = min(max(center + step, f_floor), f_cap)
        minus = min(max(center - step, f_floor), f_cap)
        half = min(center - minus, plus - center)
        if half <= 0:
            fhat = center
            break
        plus = center + half
        minus = center - half
        energy_plus = _residual_energy(values, fs, plus, orders)
        energy_minus = _residual_energy(values, fs, minus, orders)
        energy_center = _residual_energy(values, fs, center, orders)
        denom = energy_plus - 2.0 * energy_center + energy_minus
        slope = (energy_plus - energy_minus) / (2.0 * half)
        curvature = denom / (half * half)
        if not math.isfinite(curvature) or curvature <= 0 or not math.isfinite(slope):
            fhat = center
            break
        shift = slope / curvature
        limit = NEWTON_SHIFT_BINS * df
        if abs(shift) > limit:
            shift = math.copysign(limit, shift)
        fhat = min(max(center - shift, f_floor), f_cap)
        step = max(step * NEWTON_SHRINK, 1e-6 * max(fhat, 1.0))
    return float(fhat)


def _log_parabolic_delta(amplitude: np.ndarray, local: int) -> float:
    if local <= 0 or local >= len(amplitude) - 1:
        return 0.0
    left = float(amplitude[local - 1])
    center = float(amplitude[local])
    right = float(amplitude[local + 1])
    if left <= 0 or center <= 0 or right <= 0:
        return 0.0
    log_left = math.log(left)
    log_center = math.log(center)
    log_right = math.log(right)
    denom = log_left - 2.0 * log_center + log_right
    if abs(denom) < 1e-18:
        return 0.0
    delta = 0.5 * (log_left - log_right) / denom
    if not math.isfinite(delta):
        return 0.0
    return float(max(-0.5, min(0.5, delta)))


def _orders_for(fs: float, f0: float, n_harmonics: int) -> list[int]:
    nyquist = fs / 2.0
    orders: list[int] = []
    for order in range(1, n_harmonics + 1):
        if order * f0 >= nyquist - 1e-9:
            break
        orders.append(order)
    if not orders or orders[0] != 1:
        raise ValueError("fundamental frequency is not below the Nyquist frequency")
    return orders


def _design(n: int, fs: float, f0: float, orders: Sequence[int]) -> np.ndarray:
    t = np.arange(n, dtype=float) / fs
    columns = [np.ones(n, dtype=float)]
    for order in orders:
        omega = 2.0 * math.pi * order * f0
        columns.append(np.sin(omega * t))
        columns.append(np.cos(omega * t))
    return np.column_stack(columns)


def _residual_energy(values: np.ndarray, fs: float, f0: float, orders: Sequence[int]) -> float:
    phi = _design(len(values), fs, f0, orders)
    if phi.shape[0] <= phi.shape[1]:
        return math.inf
    beta, _, rank, _ = np.linalg.lstsq(phi, values, rcond=None)
    if int(rank) < phi.shape[1]:
        return math.inf
    residual = values - phi @ beta
    energy = float(residual @ residual)
    if not math.isfinite(energy):
        return math.inf
    return energy


def _harmonic_table(
    values: np.ndarray,
    fs: float,
    f0: float,
    *,
    n_harmonics: int,
    amp_floor_ratio: float,
) -> tuple[float, list[HarmonicRow], float]:
    orders = _orders_for(fs, f0, n_harmonics)
    phi = _design(len(values), fs, f0, orders)
    if phi.shape[0] <= phi.shape[1]:
        raise ValueError("harmonic fit needs more samples than coefficients; lower n_harmonics or use a longer record")
    beta, _, rank, _ = np.linalg.lstsq(phi, values, rcond=None)
    if int(rank) < phi.shape[1]:
        raise ValueError("harmonic fit is rank deficient; lower n_harmonics or use a longer record")
    dc = float(beta[0])
    peaks: list[tuple[int, float, float]] = []
    for index, order in enumerate(orders):
        b_sin = float(beta[1 + 2 * index])
        b_cos = float(beta[2 + 2 * index])
        amplitude = math.hypot(b_sin, b_cos)
        phase = math.atan2(b_cos, b_sin)
        peaks.append((order, amplitude, phase))
    a1 = peaks[0][1]
    scale = float(np.max(np.abs(values)))
    if not math.isfinite(a1) or a1 <= 1e-8 * max(scale, 1e-30):
        raise ValueError("fundamental amplitude is zero; THD is undefined")
    rows: list[HarmonicRow] = []
    for order, amplitude, phase in peaks:
        if amplitude <= max(1e-12, PHASE_REL_TOL * a1):
            phase = 0.0
        in_thd = order > 1 and amplitude >= amp_floor_ratio * a1
        rows.append(
            HarmonicRow(
                order=order,
                frequency_hz=order * f0,
                amplitude=amplitude,
                rms=amplitude / math.sqrt(2.0),
                percent=100.0 * amplitude / a1,
                phase_rad=phase,
                phase_deg=phase * 180.0 / math.pi,
                in_thd=in_thd,
            )
        )
    residual = values - dc
    signal_rms = float(math.sqrt(float(np.dot(residual, residual)) / len(values)))
    return dc, rows, signal_rms


_CSV_FIELDS = (
    "order",
    "frequency_hz",
    "amplitude",
    "rms",
    "percent",
    "phase_rad",
    "phase_deg",
    "in_thd",
)


def _write_csv(path: Path, harmonics: Sequence[HarmonicRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for row in harmonics:
            writer.writerow(
                {
                    "order": row.order,
                    "frequency_hz": f"{row.frequency_hz:.12g}",
                    "amplitude": f"{row.amplitude:.12g}",
                    "rms": f"{row.rms:.12g}",
                    "percent": f"{row.percent:.12g}",
                    "phase_rad": f"{row.phase_rad:.12g}",
                    "phase_deg": f"{row.phase_deg:.12g}",
                    "in_thd": int(row.in_thd),
                }
            )


def _render_figure(result: FftThdResult, output_png: str | None, show: bool) -> object | None:
    import matplotlib.pyplot as plt

    n = result.n_samples
    n_limit = round(10.0 * result.fs / result.f0)
    n_show = n if n_limit < 8 else min(n, n_limit)
    t_rel = np.arange(n_show, dtype=float) / result.fs
    recon = np.full(n_show, result.dc, dtype=float)
    mark_f: list[float] = []
    mark_a: list[float] = []
    for row in result.harmonics:
        recon += row.amplitude * np.sin(2.0 * math.pi * row.frequency_hz * t_rel + row.phase_rad)
        if row.order == 1 or (row.in_thd and row.percent >= MARKER_PERCENT):
            mark_f.append(row.frequency_hz)
            mark_a.append(row.amplitude)
    max_order = result.harmonics[-1].order
    x_max = min(result.fs / 2.0, max(8.0 * result.f0, (max_order + 1) * result.f0) * 1.02)
    visible = result.spectrum_amplitude[result.spectrum_frequency <= x_max + 1e-12]
    y_top = max(float(np.max(visible)) if visible.size else 1.0, result.fundamental_amplitude, 1e-12)

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
        fig, (ax_wave, ax_spec) = plt.subplots(2, 1, figsize=(10.2, 7.4))
        ax_wave.plot(result.time[:n_show], result.signal[:n_show], color="#1f4e79", lw=1.1, label="signal")
        ax_wave.plot(result.time[:n_show], recon, color="#c0392b", lw=1.15, ls="--", label="harmonic fit")
        ax_wave.set_xlabel("Time (s)")
        ax_wave.set_ylabel("Signal")
        ax_wave.set_title("Waveform" if n_show == n else "Waveform (first 10 cycles)")
        ax_wave.grid(True, color="#d0d0d0", linewidth=0.6)
        ax_wave.legend(loc="upper right", frameon=True, edgecolor="#cccccc")

        ax_spec.plot(
            result.spectrum_frequency,
            result.spectrum_amplitude,
            color="#1f4e79",
            lw=1.0,
            label="spectrum",
        )
        if mark_f:
            ax_spec.plot(mark_f, mark_a, "o", color="#c0392b", ms=5.5, ls="none", label="harmonics")
        ax_spec.set_xlim(0.0, x_max)
        ax_spec.set_ylim(0.0, y_top * 1.18)
        ax_spec.set_xlabel("Frequency (Hz)")
        ax_spec.set_ylabel("Peak amplitude")
        ax_spec.set_title("Single-sided amplitude spectrum")
        ax_spec.grid(True, color="#d0d0d0", linewidth=0.6)
        ax_spec.legend(loc="upper right", frameon=True, edgecolor="#cccccc")
        ax_spec.text(
            0.02,
            0.95,
            f"f1 = {result.f0:.2f} Hz\nTHD = {result.thd_percent:.2f}%",
            transform=ax_spec.transAxes,
            va="top",
            ha="left",
            fontsize=11,
            color="#1f4e79",
            bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": "#cccccc"},
        )
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
