"""Sine-triangle PWM waveforms for a single-phase full bridge.

The calculations match ``matlab/pwm_waveform.m``. No toolbox and no SciPy.

Carrier, sampled at ``samples_per_carrier`` points per period, peak ±1.
The period starts at -1 and reaches +1 halfway through:

    phase = mod(k, samples_per_carrier) / samples_per_carrier
    carrier = 1 - 4 * abs(phase - 0.5)

Modulation, with amplitude equal to the modulation index ``m_a``:

    m(k) = m_a * sin(2*pi*f_m*t_k + phase)
    t_k = k / fs
    fs = N * f_m / cycles
    N = samples_per_carrier * n_carrier

``n_carrier = m_f * cycles`` must be an integer, so the record contains an
integer number of carrier periods and an integer number of fundamental
cycles. A tie (``m == carrier``) turns the upper device on.

Bipolar (two-level full bridge, no zero state):

    gate_b = 1 - gate_a
    v_out = +V_dc when gate_a is on, else -V_dc

Unipolar (three-level full bridge): leg A follows ``m``, leg B follows
``-m``. Each leg is ±V_dc/2, and the bridge voltage is the difference:

    v_out ∈ {+V_dc, 0, -V_dc}

In the linear range ``m_a <= 1`` the naturally sampled fundamental peak is

    V_1 = m_a * V_dc

The discrete comparison approaches that value as ``samples_per_carrier``
grows. Above ``m_a = 1`` the same comparison runs into overmodulation:
pulses drop and the formula no longer holds.

THD uses every non-fundamental AC component (Parseval), not a truncated
harmonic sum. DC is removed first. Peak and RMS ratios match:

    THD = sqrt(Vrms_ac^2 - V1_rms^2) / V1_rms

The harmonic table is a separate integer-order correlation,

    A*sin(h*w*t + phi),  phi = atan2(b_cos, b_sin)

with ``t = 0`` at the first sample. ``amp_floor_ratio`` only sets
``above_floor`` on each row; it does not change ``thd``.
"""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from pathlib import Path

import numpy as np

DEFAULT_F_M = 50.0
DEFAULT_M_F = 21.0
DEFAULT_M_A = 0.8
DEFAULT_V_DC = 100.0
DEFAULT_CYCLES = 2
DEFAULT_SAMPLES_PER_CARRIER = 200
DEFAULT_AMP_FLOOR = 0.01
MAX_M_A = 10.0
MAX_CYCLES = 50
MIN_SAMPLES_PER_CARRIER = 8
MAX_SAMPLES_PER_CARRIER = 20000
MAX_SAMPLES = 2_000_000
MAX_HARMONICS = 500
AUTO_HARMONIC_CAP = 150
CARRIER_COUNT_TOL = 1e-6
FUND_REL_MIN = 1e-8
PHASE_ABS_TOL = 1e-9
PHASE_REL_TOL = 1e-8
PLOT_CYCLES = 2

_PARAM_NAMES = {
    "name",
    "mode",
    "f_m",
    "f_c",
    "m_f",
    "m_a",
    "v_dc",
    "phase_deg",
    "cycles",
    "samples_per_carrier",
    "n_harmonics",
    "amp_floor_ratio",
    "csv_path",
    "output_csv",
    "output_png",
    "show",
}

_CSV_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name",),
    "mode": ("mode",),
    "f_m": ("fm",),
    "f_c": ("fc",),
    "m_f": ("mf",),
    "m_a": ("ma",),
    "v_dc": ("vdc",),
    "phase_deg": ("phasedeg", "phase"),
    "cycles": ("cycles",),
    "samples_per_carrier": ("samplespercarrier",),
    "n_harmonics": ("nharmonics",),
    "amp_floor_ratio": ("ampfloorratio",),
}


@dataclass
class HarmonicRow:
    """One integer harmonic of ``f_m``.

    ``amplitude`` is the sine peak. ``rms`` is ``amplitude / sqrt(2)``.
    ``percent`` is ``100 * amplitude / fundamental``. ``above_floor`` is true
    when this order is at least ``amp_floor_ratio`` times the fundamental
    (order >= 2). The flag does not define ``thd``; ``thd`` keeps the whole
    residual, including orders past the end of this table.
    """

    order: int
    frequency_hz: float
    amplitude: float
    rms: float
    percent: float
    phase_rad: float
    phase_deg: float
    above_floor: bool


@dataclass
class PwmWaveformResult:
    """One sine-triangle PWM record and its fundamental check.

    ``gate_a`` and ``gate_b`` are 1 when that leg's upper device is on and 0
    when the lower device is on. ``v_out`` is the bridge voltage.
    ``v_ref`` is ``m_a * V_dc * sin(...)``, the linear-range fundamental.
    ``fundamental_amplitude`` is measured from the record. ``thd`` is the
    full-band ratio; NaN when the fundamental peak is numerically zero.
    """

    name: str
    mode: str
    f_m: float
    f_c: float
    m_f: float
    m_a: float
    v_dc: float
    phase_deg: float
    phase_rad: float
    cycles: int
    samples_per_carrier: int
    fs: float
    n_samples: int
    n_carrier: int
    linear_range: bool
    n_pulses_a: int
    n_pulses_b: int
    dc: float
    fundamental_amplitude: float
    fundamental_rms: float
    fundamental_phase_rad: float
    fundamental_phase_deg: float
    fundamental_analytic: float
    fundamental_error: float
    fundamental_error_percent: float
    signal_rms: float
    thd: float
    thd_percent: float
    n_harmonics: int
    amp_floor_ratio: float
    harmonics: list[HarmonicRow]
    time: np.ndarray
    modulation: np.ndarray
    carrier: np.ndarray
    gate_a: np.ndarray
    gate_b: np.ndarray
    v_out: np.ndarray
    v_ref: np.ndarray
    output_csv: str | None
    output_png: str | None
    fig: object | None = None


def pwm_waveform(
    source: str | Path | None = None,
    *,
    name: str = "",
    mode: str = "bipolar",
    f_m: float = DEFAULT_F_M,
    f_c: float | None = None,
    m_f: float | None = None,
    m_a: float = DEFAULT_M_A,
    v_dc: float = DEFAULT_V_DC,
    phase_deg: float = 0.0,
    cycles: int = DEFAULT_CYCLES,
    samples_per_carrier: int = DEFAULT_SAMPLES_PER_CARRIER,
    n_harmonics: int | None = None,
    amp_floor_ratio: float = DEFAULT_AMP_FLOOR,
    csv_path: str | Path | None = None,
    output_csv: str | Path | None = None,
    output_png: str | Path | None = None,
    show: bool = False,
) -> PwmWaveformResult:
    """Generate one sine-triangle PWM waveform and check its fundamental.

    Parameters use the same names as the MATLAB name-value arguments.
    ``source`` or ``csv_path`` selects a row in a parameter CSV. A blank CSV
    cell keeps the corresponding argument. With no CSV, the arguments are
    the waveform.
    """

    picked = _resolve_case(
        source,
        csv_path=csv_path,
        name=name,
        mode=mode,
        f_m=f_m,
        f_c=f_c,
        m_f=m_f,
        m_a=m_a,
        v_dc=v_dc,
        phase_deg=phase_deg,
        cycles=cycles,
        samples_per_carrier=samples_per_carrier,
        n_harmonics=n_harmonics,
        amp_floor_ratio=amp_floor_ratio,
    )
    show = _as_bool("show", show)
    mode_used = _normalize_mode(picked["mode"])
    f_m_used = _positive("f_m", picked["f_m"])
    m_a_used = _finite("m_a", picked["m_a"])
    if m_a_used < 0 or m_a_used > MAX_M_A:
        raise ValueError(f"m_a must be between 0 and {MAX_M_A:g}")
    v_dc_used = _positive("v_dc", picked["v_dc"])
    phase_deg_used = _finite("phase_deg", picked["phase_deg"])
    cycles_used = _positive_int("cycles", picked["cycles"], maximum=MAX_CYCLES)
    samples_used = _positive_int(
        "samples_per_carrier",
        picked["samples_per_carrier"],
        minimum=MIN_SAMPLES_PER_CARRIER,
        maximum=MAX_SAMPLES_PER_CARRIER,
    )
    f_c_used, m_f_used, n_carrier = _resolve_carrier(f_m_used, picked["f_c"], picked["m_f"], cycles_used)
    n_samples = samples_used * n_carrier
    if n_samples > MAX_SAMPLES:
        raise ValueError("record is too long; lower samples_per_carrier, m_f, or cycles")
    floor_used = _finite("amp_floor_ratio", picked["amp_floor_ratio"])
    if floor_used < 0:
        raise ValueError("amp_floor_ratio must be >= 0")
    fs = n_samples * f_m_used / cycles_used
    if picked["n_harmonics"] is None:
        n_harm = _auto_harmonics(m_f_used, fs, f_m_used)
    else:
        n_harm = _positive_int("n_harmonics", picked["n_harmonics"], maximum=MAX_HARMONICS)

    phase_rad = phase_deg_used * math.pi / 180.0
    index = np.arange(n_samples, dtype=np.float64)
    theta = 2.0 * math.pi * (cycles_used * index / n_samples) + phase_rad
    modulation = np.ascontiguousarray(m_a_used * np.sin(theta), dtype=np.float64)
    carrier_phase = (np.arange(n_samples, dtype=np.int64) % samples_used) / np.float64(samples_used)
    carrier = np.ascontiguousarray(1.0 - 4.0 * np.abs(carrier_phase - 0.5), dtype=np.float64)
    gate_a_on = modulation >= carrier
    if mode_used == "bipolar":
        gate_b_on = ~gate_a_on
        v_out = np.where(gate_a_on, v_dc_used, -v_dc_used).astype(np.float64, copy=False)
    else:
        gate_b_on = (-modulation) >= carrier
        v_leg_a = np.where(gate_a_on, 0.5 * v_dc_used, -0.5 * v_dc_used)
        v_leg_b = np.where(gate_b_on, 0.5 * v_dc_used, -0.5 * v_dc_used)
        v_out = np.ascontiguousarray(v_leg_a - v_leg_b, dtype=np.float64)
    gate_a = gate_a_on.astype(np.float64)
    gate_b = gate_b_on.astype(np.float64)
    time = index / fs
    v_ref = modulation * v_dc_used

    dc = float(np.mean(v_out))
    harmonics = _harmonic_table(
        v_out,
        fs=fs,
        f_m=f_m_used,
        cycles=cycles_used,
        n_harmonics=n_harm,
        amp_floor_ratio=floor_used,
        v_dc=v_dc_used,
    )
    fundamental = harmonics[0]
    analytic = m_a_used * v_dc_used
    error = fundamental.amplitude - analytic
    if abs(analytic) <= 1e-15 * max(v_dc_used, 1.0):
        error_percent = math.nan
    else:
        error_percent = 100.0 * error / analytic
    ac = v_out - dc
    signal_rms = math.sqrt(float(np.dot(ac, ac)) / n_samples)
    thd = _thd_ratio(signal_rms, fundamental.amplitude, v_dc_used)

    csv_out = None if output_csv is None or str(output_csv).strip() == "" else str(output_csv)
    png_out = None if output_png is None or str(output_png).strip() == "" else str(output_png)
    result = PwmWaveformResult(
        name=_text(picked["name"]),
        mode=mode_used,
        f_m=f_m_used,
        f_c=f_c_used,
        m_f=m_f_used,
        m_a=m_a_used,
        v_dc=v_dc_used,
        phase_deg=phase_deg_used,
        phase_rad=phase_rad,
        cycles=cycles_used,
        samples_per_carrier=samples_used,
        fs=fs,
        n_samples=n_samples,
        n_carrier=n_carrier,
        linear_range=m_a_used <= 1.0 + 1e-12,
        n_pulses_a=_pulse_count(gate_a),
        n_pulses_b=_pulse_count(gate_b),
        dc=dc,
        fundamental_amplitude=fundamental.amplitude,
        fundamental_rms=fundamental.rms,
        fundamental_phase_rad=fundamental.phase_rad,
        fundamental_phase_deg=fundamental.phase_deg,
        fundamental_analytic=analytic,
        fundamental_error=error,
        fundamental_error_percent=error_percent,
        signal_rms=signal_rms,
        thd=thd,
        thd_percent=100.0 * thd if math.isfinite(thd) else math.nan,
        n_harmonics=n_harm,
        amp_floor_ratio=floor_used,
        harmonics=harmonics,
        time=time,
        modulation=modulation,
        carrier=carrier,
        gate_a=gate_a,
        gate_b=gate_b,
        v_out=v_out,
        v_ref=v_ref,
        output_csv=csv_out,
        output_png=png_out,
        fig=None,
    )
    if csv_out is not None:
        _write_csv(Path(csv_out), result.harmonics)
    if png_out is not None or show:
        result.fig = _render_figure(result, png_out, show)
    return result


def format_table(result: PwmWaveformResult) -> str:
    """Format the PWM summary and the harmonic table as text."""

    head = "" if result.name == "" else f"name={result.name}  "
    lines = [
        (
            f"{head}mode={result.mode}  f_m={_compact(result.f_m)} Hz  "
            f"f_c={_compact(result.f_c)} Hz  m_f={_compact(result.m_f)}  "
            f"m_a={_compact(result.m_a)}  Vdc={_compact(result.v_dc)}  "
            f"phase_deg={_compact(result.phase_deg)}"
        ),
        (
            f"fs={_compact(result.fs)} Hz  N={result.n_samples}  cycles={result.cycles}  "
            f"samples_per_carrier={result.samples_per_carrier}  linear={int(result.linear_range)}  "
            f"pulses_a={result.n_pulses_a}  pulses_b={result.n_pulses_b}"
        ),
        (
            f"dc={_compact(result.dc)}  V1={_compact(result.fundamental_amplitude)}  "
            f"V1_analytic={_compact(result.fundamental_analytic)}  "
            f"err={_percent_text(result.fundamental_error_percent)}  "
            f"THD={_percent_text(result.thd_percent)}  floor={_compact(result.amp_floor_ratio)}"
        ),
        (
            f"{'order':>5} {'frequency_Hz':>14} {'amplitude':>12} {'rms':>12} "
            f"{'percent':>10} {'phase_deg':>10} {'above_floor':>12}"
        ),
    ]
    for row in result.harmonics:
        percent = f"{row.percent:10.4f}" if math.isfinite(row.percent) else f"{'nan':>10}"
        lines.append(
            f"{row.order:5d} {row.frequency_hz:14.4f} {row.amplitude:12.4f} "
            f"{row.rms:12.4f} {percent} {row.phase_deg:10.3f} {int(row.above_floor):12d}"
        )
    return "\n".join(lines)


def _percent_text(value: float) -> str:
    if not math.isfinite(value):
        return "undefined"
    return f"{value:.4f}%"


def _thd_ratio(signal_rms: float, amplitude: float, v_dc: float) -> float:
    if amplitude <= FUND_REL_MIN * max(abs(v_dc), 1.0):
        return math.nan
    fund_rms = amplitude / math.sqrt(2.0)
    dist_ms = signal_rms * signal_rms - fund_rms * fund_rms
    if dist_ms < 0.0:
        if dist_ms < -1e-8 * max(signal_rms * signal_rms, 1.0):
            raise ValueError("THD residual is negative; the fundamental estimate is inconsistent")
        dist_ms = 0.0
    return math.sqrt(dist_ms) / fund_rms


def _pulse_count(gate: np.ndarray) -> int:
    previous = float(gate[-1])
    count = 0
    for value in gate:
        current = float(value)
        if previous < 0.5 <= current:
            count += 1
        previous = current
    return count


def _auto_harmonics(m_f: float, fs: float, f_m: float) -> int:
    nyquist_order = int(math.floor((fs / 2.0) / f_m - 1e-9))
    want = int(math.ceil(2.0 * m_f + 4.0))
    return max(1, min(AUTO_HARMONIC_CAP, nyquist_order, want))


def _resolve_carrier(
    f_m: float,
    f_c: object,
    m_f: object,
    cycles: int,
) -> tuple[float, float, int]:
    m_f_set = m_f is not None and not (isinstance(m_f, str) and str(m_f).strip() == "")
    f_c_set = f_c is not None and not (isinstance(f_c, str) and str(f_c).strip() == "")
    m_f_value = None
    f_c_value = None
    if m_f_set:
        m_f_value = _finite("m_f", m_f)
        if m_f_value <= 0:
            raise ValueError("m_f must be a positive finite number")
    if f_c_set:
        f_c_value = _positive("f_c", f_c)
    if m_f_value is None and f_c_value is None:
        m_f_value = DEFAULT_M_F
    if m_f_value is not None and f_c_value is not None:
        expected = m_f_value * f_m
        if abs(f_c_value - expected) > 1e-6 * max(abs(expected), 1.0):
            raise ValueError("f_c does not match m_f * f_m")
    elif m_f_value is None:
        assert f_c_value is not None
        m_f_value = f_c_value / f_m
    if m_f_value < 1.0:
        raise ValueError("m_f must be >= 1 (carrier at least as fast as the modulation)")
    product = m_f_value * cycles
    nearest = round(product)
    if abs(product - nearest) > CARRIER_COUNT_TOL or nearest < 1:
        raise ValueError(
            "m_f * cycles must be an integer so the record holds an integer number of carrier periods"
        )
    n_carrier = int(nearest)
    m_f_used = n_carrier / cycles
    f_c_used = n_carrier * f_m / cycles
    return f_c_used, m_f_used, n_carrier


def _harmonic_table(
    v_out: np.ndarray,
    *,
    fs: float,
    f_m: float,
    cycles: int,
    n_harmonics: int,
    amp_floor_ratio: float,
    v_dc: float,
) -> list[HarmonicRow]:
    n = int(v_out.shape[0])
    index = np.arange(n, dtype=np.float64)
    coeffs: list[tuple[int, float, float]] = []
    for order in range(1, n_harmonics + 1):
        if order * f_m >= fs / 2.0 - 1e-9:
            break
        theta = 2.0 * math.pi * (order * cycles * index / n)
        b_sin = (2.0 / n) * float(np.dot(v_out, np.sin(theta)))
        b_cos = (2.0 / n) * float(np.dot(v_out, np.cos(theta)))
        coeffs.append((order, b_sin, b_cos))
    if not coeffs:
        raise ValueError("no harmonic fits under the Nyquist frequency; increase samples_per_carrier")
    a1 = math.hypot(coeffs[0][1], coeffs[0][2])
    defined = a1 > FUND_REL_MIN * max(abs(v_dc), 1.0)
    rows: list[HarmonicRow] = []
    for order, b_sin, b_cos in coeffs:
        amplitude = math.hypot(b_sin, b_cos)
        phase = math.atan2(b_cos, b_sin)
        if amplitude <= max(PHASE_ABS_TOL, PHASE_REL_TOL * max(a1, 1e-30)):
            phase = 0.0
        if defined:
            percent = 100.0 * amplitude / a1
            above_floor = order > 1 and amplitude >= amp_floor_ratio * a1
        else:
            percent = math.nan
            above_floor = False
        rows.append(
            HarmonicRow(
                order=order,
                frequency_hz=order * f_m,
                amplitude=amplitude,
                rms=amplitude / math.sqrt(2.0),
                percent=percent,
                phase_rad=phase,
                phase_deg=phase * 180.0 / math.pi,
                above_floor=above_floor,
            )
        )
    return rows


def _resolve_case(
    source: object,
    *,
    csv_path: str | Path | None,
    name: object,
    mode: object,
    f_m: object,
    f_c: object,
    m_f: object,
    m_a: object,
    v_dc: object,
    phase_deg: object,
    cycles: object,
    samples_per_carrier: object,
    n_harmonics: object,
    amp_floor_ratio: object,
) -> dict[str, object]:
    defaults: dict[str, object] = {
        "name": name,
        "mode": mode,
        "f_m": f_m,
        "f_c": f_c,
        "m_f": m_f,
        "m_a": m_a,
        "v_dc": v_dc,
        "phase_deg": phase_deg,
        "cycles": cycles,
        "samples_per_carrier": samples_per_carrier,
        "n_harmonics": n_harmonics,
        "amp_floor_ratio": amp_floor_ratio,
    }
    path_text = None if csv_path is None or str(csv_path).strip() == "" else str(csv_path).strip()
    if isinstance(source, bool) or (isinstance(source, Real) and not isinstance(source, bool)):
        raise ValueError("pass parameters by name; the first argument is a CSV path")
    if source is not None and not isinstance(source, (str, Path)):
        raise TypeError("source must be a CSV path or omitted")
    if isinstance(source, (str, Path)) and str(source).strip() == "":
        source = None
    if isinstance(source, (str, Path)):
        text = str(source).strip()
        if text.lower() in _PARAM_NAMES:
            raise ValueError(
                f"{text!r} is a parameter name. Pass the CSV path as the first argument or as csv_path="
            )
        if path_text is not None:
            raise ValueError("pass a CSV path once, either positionally or as csv_path=")
        path_text = text
    if path_text is None:
        return defaults
    rows = _read_csv_rows(Path(path_text))
    selected = _select_row(rows, _text(name))
    merged = dict(defaults)
    for key in defaults:
        raw = _lookup(selected, *_CSV_ALIASES[key])
        if not _blank(raw):
            merged[key] = raw
    if _blank(merged["name"]):
        merged["name"] = ""
    return merged


def _select_row(rows: Sequence[Mapping[str, str]], name: str) -> Mapping[str, str]:
    if name == "":
        if len(rows) == 1:
            return rows[0]
        raise ValueError("CSV has multiple rows; pass name to select one")
    matches = [row for row in rows if _text(_lookup(row, "name")) == name]
    if not matches:
        raise ValueError(f"name {name!r} was not found in the CSV")
    return matches[0]


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


def _lookup(row: Mapping[str, object], *keys: str) -> object | None:
    folded = {_norm_key(key): value for key, value in row.items() if key is not None}
    for key in keys:
        if key in folded:
            return folded[key]
    return None


def _normalize_mode(value: object) -> str:
    key = _norm_key(value)
    if key in {"bipolar", "bi", "双极性"}:
        return "bipolar"
    if key in {"unipolar", "uni", "单极性"}:
        return "unipolar"
    raise ValueError("mode must be 'bipolar' or 'unipolar'")


def _norm_key(key: object) -> str:
    return re.sub(r"[\s_\-]", "", str(key).strip().lower())


def _blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _text(value: object) -> str:
    if _blank(value):
        return ""
    return str(value).strip()


def _compact(value: float) -> str:
    if not math.isfinite(value):
        return "nan"
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


def _positive_int(label: str, value: object, *, maximum: int, minimum: int = 1) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    number = _finite(label, value)
    if abs(number - round(number)) > 1e-9:
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}")
    integer = round(number)
    if integer < minimum or integer > maximum:
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}")
    return integer


def _as_bool(label: str, value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool) and int(value) in (0, 1):
        return bool(int(value))
    raise ValueError(f"{label} must be true or false")


_CSV_FIELDS = (
    "order",
    "frequency_hz",
    "amplitude",
    "rms",
    "percent",
    "phase_rad",
    "phase_deg",
    "above_floor",
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
                    "percent": "nan" if not math.isfinite(row.percent) else f"{row.percent:.12g}",
                    "phase_rad": f"{row.phase_rad:.12g}",
                    "phase_deg": f"{row.phase_deg:.12g}",
                    "above_floor": int(row.above_floor),
                }
            )


def _render_figure(result: PwmWaveformResult, output_png: str | None, show: bool) -> object | None:
    import matplotlib.pyplot as plt

    n_show = result.n_samples
    if result.cycles > PLOT_CYCLES:
        n_show = int(round(result.n_samples * PLOT_CYCLES / result.cycles))
        n_show = max(2, min(result.n_samples, n_show))
    time = result.time[:n_show]
    t_end = n_show / result.fs
    style = {
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#444444",
    }
    title_suffix = "" if n_show == result.n_samples else f" (first {PLOT_CYCLES} cycles)"
    with plt.rc_context(style):
        fig, axes = plt.subplots(3, 1, figsize=(10.6, 8.8), sharex=True)
        ax_mod, ax_gate, ax_out = axes
        ax_mod.plot(time, result.modulation[:n_show], color="#1f4e79", lw=1.25, label="modulation")
        ax_mod.plot(time, result.carrier[:n_show], color="#c0392b", lw=0.9, label="carrier")
        ax_mod.set_ylabel("Amplitude")
        ax_mod.set_title(f"Modulation and carrier{title_suffix}")
        ax_mod.set_ylim(-1.35, 1.45)
        ax_mod.grid(True, color="#d0d0d0", linewidth=0.6)
        ax_mod.legend(loc="upper right", frameon=True, edgecolor="#cccccc")

        ax_gate.plot(
            time,
            result.gate_a[:n_show],
            color="#1f4e79",
            lw=1.05,
            drawstyle="steps-post",
            label="gate_a",
        )
        ax_gate.plot(
            time,
            result.gate_b[:n_show] + 1.35,
            color="#0e7c66",
            lw=1.05,
            drawstyle="steps-post",
            label="gate_b (+1.35)",
        )
        ax_gate.set_ylabel("Gate")
        ax_gate.set_title("Upper-device gates")
        ax_gate.set_yticks([0.0, 1.0, 1.35, 2.35])
        ax_gate.set_yticklabels(["0", "1", "0", "1"])
        ax_gate.set_ylim(-0.25, 2.7)
        ax_gate.grid(True, color="#d0d0d0", linewidth=0.6)
        ax_gate.legend(loc="upper right", frameon=True, edgecolor="#cccccc")

        ax_out.plot(
            time,
            result.v_out[:n_show],
            color="#1f4e79",
            lw=1.0,
            drawstyle="steps-post",
            label="v_out",
        )
        ax_out.plot(
            time,
            result.v_ref[:n_show],
            color="#c0392b",
            lw=1.2,
            ls="--",
            label="m_a*Vdc*sin",
        )
        ax_out.set_xlabel("Time (s)")
        ax_out.set_ylabel("Voltage")
        ax_out.set_title("Bridge output")
        y_peak = max(result.v_dc, float(np.max(np.abs(result.v_ref[:n_show]))), 1e-9)
        ax_out.set_ylim(-1.25 * y_peak, 1.45 * y_peak)
        ax_out.set_xlim(float(time[0]), t_end)
        ax_out.grid(True, color="#d0d0d0", linewidth=0.6)
        ax_out.legend(loc="upper right", frameon=True, edgecolor="#cccccc")
        if math.isfinite(result.thd_percent):
            thd_line = f"THD = {result.thd_percent:.2f}%"
        else:
            thd_line = "THD undefined"
        note = "\n".join(
            [
                result.mode,
                f"m_a = {result.m_a:.2f}    m_f = {_compact(result.m_f)}",
                f"V1 = {result.fundamental_amplitude:.2f}",
                f"m_a*Vdc = {result.fundamental_analytic:.2f}",
                thd_line,
            ]
        )
        if not result.linear_range:
            note += "\novermodulation"
        ax_out.text(
            0.02,
            0.04,
            note,
            transform=ax_out.transAxes,
            va="bottom",
            ha="left",
            fontsize=10,
            color="#1f4e79",
            bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": "#cccccc", "alpha": 0.92},
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
