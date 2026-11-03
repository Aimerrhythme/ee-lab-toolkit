"""Bode magnitude, phase, and stability margins for a simple transfer function.

The calculations match ``matlab/bode_demo.m``.

1. Build one or more transfer functions from numerator/denominator
   coefficients, a first-order lag, a second-order prototype, or a filtered
   PID in series with a second-order plant.
2. Evaluate ``H(jw) = polyval(num, jw) / polyval(den, jw)`` on a logarithmic
   frequency grid. Python calls ``scipy.signal.freqs``, which is this
   polynomial evaluation; MATLAB uses ``polyval`` so no toolbox is required.
3. Unwrap the phase in degrees and locate 0 dB and negative-real-axis crossings.
4. Report the critical gain and phase margins, and optionally draw the Bode diagram.

Margins use the classical positive-frequency definitions. With the phase in
degrees after unwrapping::

    PM = wrap_180(phase_deg(w_gc) + 180)
    GM_dB = -magnitude_db(w_pc)

``w_gc`` is a gain crossover (magnitude crosses 0 dB). ``w_pc`` is a phase
crossover (unwrapped phase crosses ``-180 + 360*k`` degrees). When several
crossings exist, the reported margin is the smallest one. The full crossing
lists are returned as well.

If the magnitude stays negative on the grid, the phase margin is ``+inf``.
If the phase never meets the negative real axis, the gain margin is ``+inf``.
If the magnitude stays positive, the phase margin is NaN for this grid.
A pole at the origin is allowed (the grid starts at ``w > 0``). Any other
imaginary-axis pole is rejected.

Filtered PID, matching ``pid-step-compare``::

    C(s) = Kp + Ki/s + Kd * (kd_n * s) / (s + kd_n)

The loop example is the series open-loop ``L(s) = C(s) G(s)`` with

    G(s) = k * wn^2 / (s^2 + 2*zeta*wn*s + wn^2)
"""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import signal

# Keep these in sync with matlab/bode_demo.m.
MAX_ORDER = 8
DEFAULT_N_POINTS = 800
SPAN_FACTOR = 10.0
MAX_EXTEND = 4
POLE_ATOL = 1e-8
DEN_FLOOR_SCALE = 1e-12
PHASE_STEP_LIMIT_DEG = 150.0
PHASE_REFINE_DEPTH = 10
CROSS_ATOL_DB = 1e-12
CROSS_ATOL_DEG = 1e-9
BISECT_STEPS = 60
MAX_SPAN_RATIO = 1e12
DEFAULT_W_MIN = 1e-2
DEFAULT_W_MAX = 1e2

_FORMS = {
    "tf": "tf",
    "transferfunction": "tf",
    "firstorder": "first_order",
    "secondorder": "second_order",
    "pidloop": "pid_loop",
    "pid": "pid_loop",
}

_COLORS = (
    "#1f4e79",
    "#c0392b",
    "#3d7a6a",
    "#e67e22",
    "#6c3483",
    "#1a5276",
)
_LINESTYLES = ("-", "--", "-.", ":")


@dataclass
class BodeMargins:
    """Critical margins and every positive-frequency crossover of one system.

    ``phase_margin_rad_s`` is the gain-crossover frequency used for the
    reported phase margin. ``gain_margin_rad_s`` is the phase-crossover
    frequency used for the reported gain margin. Empty crossover lists and
    NaN frequencies mean that crossing was not observed. ``+inf`` margins
    mean the loop gain never reaches that crossing on this grid.
    """

    name: str
    form: str
    num: list[float]
    den: list[float]
    gain_crossover_rad_s: list[float]
    phase_crossover_rad_s: list[float]
    phase_margin_deg: float
    gain_margin_db: float
    phase_margin_rad_s: float
    gain_margin_rad_s: float


@dataclass
class BodeDemoResult:
    """Bode curves and one margin record per system.

    ``magnitude_db`` and ``phase_deg`` have shape ``(len(frequency_rad_s), n_systems)``.
    Column ``i`` belongs to ``names[i]`` and ``margins[i]``. Phase is unwrapped
    and stored in degrees. ``frequency_rad_s`` is 1-D, in rad/s, ascending.
    """

    frequency_rad_s: np.ndarray
    magnitude_db: np.ndarray
    phase_deg: np.ndarray
    names: list[str]
    margins: list[BodeMargins]
    w_min: float
    w_max: float
    n_points: int
    output_png: str | None
    fig: object | None = None


def bode_demo(
    num: Sequence | Mapping | str | Path | None = None,
    den: Sequence | None = None,
    *,
    systems: Mapping | Sequence | str | Path | None = None,
    form: str | None = None,
    name: str | None = None,
    names: Sequence[str] | str | None = None,
    k: float = 1.0,
    tau: float = 1.0,
    wn: float = 1.0,
    zeta: float = 0.5,
    kp: float = 1.0,
    ki: float = 0.0,
    kd: float = 0.0,
    kd_n: float = 10.0,
    w_min: float | None = None,
    w_max: float | None = None,
    n_points: int = DEFAULT_N_POINTS,
    frequency_rad_s: Sequence[float] | None = None,
    output_png: str | Path | None = None,
    show: bool = False,
) -> BodeDemoResult:
    """Evaluate Bode curves and gain/phase margins for one or more systems.

    Parameters use the same names as the MATLAB name-value arguments.
    Pass numerator and denominator coefficients (highest power first), a
    system mapping, a list of systems, or a CSV path. With no system at all,
    the call uses ``G(s) = 1 / (s^2 + s + 1)`` (``wn = 1``, ``zeta = 0.5``).

    ``names`` keeps a subset, in the requested order, after the systems are built.
    """

    if systems is not None:
        if num is not None or den is not None:
            raise ValueError("pass systems or num/den, not both")
        num = systems
        den = None
    specs = _collect_specs(
        num,
        den,
        form=form,
        name=name,
        k=k,
        tau=tau,
        wn=wn,
        zeta=zeta,
        kp=kp,
        ki=ki,
        kd=kd,
        kd_n=kd_n,
    )
    specs = _select_names(specs, names)
    n_points = _positive_int("n_points", n_points, 2, 20_000)
    frequency = _frequency_grid(specs, w_min, w_max, n_points, frequency_rad_s)

    columns_mag: list[np.ndarray] = []
    columns_phase: list[np.ndarray] = []
    margins: list[BodeMargins] = []
    for spec in specs:
        magnitude, phase = _response(spec["num"], spec["den"], frequency)
        columns_mag.append(magnitude)
        columns_phase.append(phase)
        margins.append(_margins(spec, frequency, magnitude, phase))

    magnitude_db = np.column_stack(columns_mag)
    phase_deg = np.column_stack(columns_phase)
    png_text = None if output_png is None or str(output_png).strip() == "" else str(output_png)
    labels = [
        _legend_label(row.name, row.phase_margin_deg, row.gain_margin_db) for row in margins
    ]
    fig = None
    if png_text is not None or show:
        fig = _render_figure(
            frequency=frequency,
            magnitude_db=magnitude_db,
            phase_deg=phase_deg,
            labels=labels,
            margins=margins,
            output_png=png_text,
            show=bool(show),
        )
    return BodeDemoResult(
        frequency_rad_s=frequency,
        magnitude_db=magnitude_db,
        phase_deg=phase_deg,
        names=[row.name for row in margins],
        margins=margins,
        w_min=float(frequency[0]),
        w_max=float(frequency[-1]),
        n_points=int(frequency.size),
        output_png=png_text,
        fig=fig,
    )


def format_margins_table(margins: Sequence[BodeMargins]) -> str:
    """Format the critical crossover frequencies and gain/phase margins.

    ``w_gc`` is the gain crossover used for ``PM_deg``. ``w_pc`` is the phase
    crossover used for ``GM_dB``.
    """

    header = (
        f"{'name':<16} {'form':<14} {'w_gc':>10} {'PM_deg':>10} {'w_pc':>10} {'GM_dB':>10}"
    )
    lines = [header]
    for row in margins:
        lines.append(
            f"{row.name:<16} {row.form:<14} "
            f"{_fmt_freq(row.phase_margin_rad_s)} {_fmt_margin(row.phase_margin_deg)} "
            f"{_fmt_freq(row.gain_margin_rad_s)} {_fmt_margin(row.gain_margin_db)}"
        )
    return "\n".join(lines)


def _fmt_special(value: float, width: int) -> str | None:
    if math.isnan(value):
        return f"{'nan':>{width}}"
    if math.isinf(value):
        return f"{('inf' if value > 0 else '-inf'):>{width}}"
    return None


def _fmt_freq(value: float, width: int = 10) -> str:
    special = _fmt_special(value, width)
    if special is not None:
        return special
    return f"{value:{width}.4g}"


def _fmt_margin(value: float, width: int = 10) -> str:
    special = _fmt_special(value, width)
    if special is not None:
        return special
    return f"{value:{width}.4f}"


def _legend_label(name: str, phase_margin_deg: float, gain_margin_db: float) -> str:
    return (
        f"{name} (PM={_legend_number(phase_margin_deg)} deg, "
        f"GM={_legend_number(gain_margin_db)} dB)"
    )


def _legend_number(value: float) -> str:
    special = _fmt_special(value, 0)
    if special is not None:
        return special.strip()
    return f"{value:.4g}"


def _reject_unused_scalars(
    k: float,
    tau: float,
    wn: float,
    zeta: float,
    kp: float,
    ki: float,
    kd: float,
    kd_n: float,
) -> None:
    provided = {
        "k": k,
        "tau": tau,
        "wn": wn,
        "zeta": zeta,
        "kp": kp,
        "ki": ki,
        "kd": kd,
        "kd_n": kd_n,
    }
    defaults = {"k": 1.0, "tau": 1.0, "wn": 1.0, "zeta": 0.5, "kp": 1.0, "ki": 0.0, "kd": 0.0, "kd_n": 10.0}
    extra = [key for key, value in provided.items() if value != defaults[key]]
    if extra:
        joined = ", ".join(extra)
        raise ValueError(
            "k, tau, wn, zeta, kp, ki, kd, and kd_n apply only when form builds one system; "
            f"got {joined}"
        )


def _positive_int(name: str, value: object, low: int, high: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if isinstance(value, (int, np.integer)):
        number = int(value)
    elif isinstance(value, (float, np.floating)) and float(value).is_integer():
        number = int(value)
    else:
        raise ValueError(f"{name} must be an integer")
    if not low <= number <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return number


def _collect_specs(
    num: Sequence | Mapping | str | Path | None,
    den: Sequence | None,
    *,
    form: str | None,
    name: str | None,
    k: float,
    tau: float,
    wn: float,
    zeta: float,
    kp: float,
    ki: float,
    kd: float,
    kd_n: float,
) -> list[dict]:
    keyword_fields = {
        "k": k,
        "tau": tau,
        "wn": wn,
        "zeta": zeta,
        "kp": kp,
        "ki": ki,
        "kd": kd,
        "kd_n": kd_n,
    }
    if isinstance(num, (str, Path)):
        if den is not None or form is not None or name is not None:
            raise ValueError("a CSV path does not take den, form, or name")
        _reject_unused_scalars(k, tau, wn, zeta, kp, ki, kd, kd_n)
        return _read_systems(Path(num))
    if isinstance(num, Mapping) or _is_system_list(num):
        if den is not None or form is not None or name is not None:
            raise ValueError("a system list does not take den, form, or name")
        _reject_unused_scalars(k, tau, wn, zeta, kp, ki, kd, kd_n)
        return _normalize_systems(num)
    if num is None and den is None:
        built = {"form": "second_order" if form is None else form, "name": name, **keyword_fields}
        return [_build_system(built, explicit_name=name is not None and str(name).strip() != "")]
    if _is_coeff(num) and _is_coeff(den):
        if form not in (None, "tf"):
            raise ValueError("num and den imply form 'tf'")
        _reject_unused_scalars(k, tau, wn, zeta, kp, ki, kd, kd_n)
        built = {"form": "tf", "name": name, "num": num, "den": den}
        return [_build_system(built, explicit_name=name is not None and str(name).strip() != "")]
    if _is_coeff(num) and den is None:
        raise ValueError("den is required when num is a coefficient vector")
    raise TypeError("num must be coefficients, a system, a list of systems, or a CSV path")


def _is_system_list(value: object) -> bool:
    if isinstance(value, (str, bytes, Mapping, np.ndarray)):
        return False
    if not isinstance(value, Sequence):
        return False
    return len(value) > 0 and all(isinstance(item, Mapping) for item in value)


def _is_coeff(value: object) -> bool:
    if value is None or isinstance(value, (str, bytes, Mapping)):
        return False
    if isinstance(value, np.ndarray):
        return value.ndim == 1 and np.issubdtype(value.dtype, np.number) and value.size > 0
    if isinstance(value, Sequence):
        if len(value) == 0:
            return False
        return all(isinstance(item, (int, float, np.integer, np.floating)) and not isinstance(item, bool) for item in value)
    return False


def _normalize_systems(systems: Mapping | Sequence) -> list[dict]:
    if isinstance(systems, Mapping):
        rows: Sequence = [systems]
    else:
        rows = list(systems)
    if len(rows) == 0:
        raise ValueError("systems must contain at least one transfer function")
    specs = []
    used: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise TypeError("each system must be a mapping")
        explicit = _lookup(row, "name")
        explicit_name = explicit is not None and str(explicit).strip() != ""
        spec = _build_system(row, explicit_name=explicit_name)
        spec["name"] = _claim_name(spec["name"], explicit_name, used)
        specs.append(spec)
    return specs


def _claim_name(name: str, explicit: bool, used: set[str]) -> str:
    if not explicit:
        base = name
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}-{suffix}"
            suffix += 1
        used.add(candidate)
        return candidate
    if name in used:
        raise ValueError(f"duplicate system name: {name}")
    used.add(name)
    return name


def _build_system(raw: Mapping, *, explicit_name: bool) -> dict:
    form_value = _lookup(raw, "form")
    form = "tf" if form_value is None else _canonical_form(form_value)
    k_gain = _finite_number("k", _lookup(raw, "k", "gain"), 1.0)
    tau = _finite_number("tau", _lookup(raw, "tau"), 1.0)
    wn = _finite_number("wn", _lookup(raw, "wn", "omegan"), 1.0)
    zeta = _finite_number("zeta", _lookup(raw, "zeta"), 0.5)
    kp = _finite_number("kp", _lookup(raw, "kp"), 1.0)
    ki = _finite_number("ki", _lookup(raw, "ki"), 0.0)
    kd = _finite_number("kd", _lookup(raw, "kd"), 0.0)
    kd_n = _finite_number("kd_n", _lookup(raw, "kdn", "n"), 10.0)

    if form == "first_order":
        if tau <= 0:
            raise ValueError("tau must be positive")
        num = np.array([k_gain], dtype=float)
        den = np.array([tau, 1.0], dtype=float)
    elif form == "second_order":
        if wn <= 0:
            raise ValueError("wn must be positive")
        num = np.array([k_gain * wn * wn], dtype=float)
        den = np.array([1.0, 2.0 * zeta * wn, wn * wn], dtype=float)
    elif form == "pid_loop":
        if wn <= 0:
            raise ValueError("wn must be positive")
        plant_num = np.array([k_gain * wn * wn], dtype=float)
        plant_den = np.array([1.0, 2.0 * zeta * wn, wn * wn], dtype=float)
        ctrl_num, ctrl_den = _pid_coefficients(kp, ki, kd, kd_n)
        num = np.convolve(ctrl_num, plant_num)
        den = np.convolve(ctrl_den, plant_den)
    else:
        num_value = _lookup(raw, "num", "numerator")
        den_value = _lookup(raw, "den", "denominator")
        if num_value is None or den_value is None:
            raise ValueError("form 'tf' requires num and den coefficients")
        num = np.asarray(_coeff_list(num_value, "num"), dtype=float)
        den = np.asarray(_coeff_list(den_value, "den"), dtype=float)

    num, den = _prepare_coefficients(num, den)
    _reject_jw_poles(den)
    name_value = _lookup(raw, "name")
    if explicit_name and name_value is not None and str(name_value).strip() != "":
        built_name = str(name_value).strip()
    else:
        built_name = _default_name(form, tau, zeta, kp, ki, kd)
    return {"name": built_name, "form": form, "num": num, "den": den, "explicit_name": explicit_name}


def _default_name(form: str, tau: float, zeta: float, kp: float, ki: float, kd: float) -> str:
    if form == "first_order":
        return f"tau={tau:g}"
    if form == "second_order":
        return f"zeta={zeta:g}"
    if form == "pid_loop":
        return _pid_kind(kp, ki, kd)
    return "tf"


def _pid_kind(kp: float, ki: float, kd: float) -> str:
    del kp
    if ki == 0.0 and kd == 0.0:
        return "P"
    if kd == 0.0:
        return "PI"
    if ki == 0.0:
        return "PD"
    return "PID"


def _pid_coefficients(kp: float, ki: float, kd: float, kd_n: float) -> tuple[np.ndarray, np.ndarray]:
    if kd != 0.0 and (not math.isfinite(kd_n) or kd_n <= 0.0):
        raise ValueError("kd_n must be a positive finite number when kd is nonzero")
    if ki == 0.0 and kd == 0.0:
        return np.array([kp], dtype=float), np.array([1.0], dtype=float)
    if kd == 0.0:
        return np.array([kp, ki], dtype=float), np.array([1.0, 0.0], dtype=float)
    num = np.array([kp + kd * kd_n, kp * kd_n + ki, ki * kd_n], dtype=float)
    den = np.array([1.0, kd_n, 0.0], dtype=float)
    return num, den


def _canonical_form(value: object) -> str:
    key = re.sub(r"[\s_\-]", "", str(value).strip().lower())
    if key not in _FORMS:
        raise ValueError("form must be one of: tf, first_order, second_order, pid_loop")
    return _FORMS[key]


def _prepare_coefficients(num: np.ndarray, den: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    num = _strip_leading(np.asarray(num, dtype=float).ravel(), "num")
    den = _strip_leading(np.asarray(den, dtype=float).ravel(), "den")
    if den[0] == 0.0:
        raise ValueError("denominator leading coefficient must be nonzero")
    if num.size - 1 > MAX_ORDER or den.size - 1 > MAX_ORDER:
        raise ValueError(f"transfer-function order must be <= {MAX_ORDER}")
    return num, den


def _strip_leading(coeff: np.ndarray, name: str) -> np.ndarray:
    if coeff.size == 0 or not np.all(np.isfinite(coeff)):
        raise ValueError(f"{name} must be a finite coefficient vector")
    index = 0
    while index < coeff.size - 1 and coeff[index] == 0.0:
        index += 1
    return coeff[index:]


def _coeff_list(value: object, name: str) -> list[float]:
    if isinstance(value, str):
        text = value.replace(",", " ").replace(";", " ")
        parts = [part for part in text.split() if part]
        if not parts:
            raise ValueError(f"{name} must be a coefficient vector")
        return [_finite_number(name, part) for part in parts]
    array = np.asarray(value, dtype=float).ravel()
    if array.size == 0 or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite coefficient vector")
    return [float(item) for item in array]


def _reject_jw_poles(den: np.ndarray) -> None:
    if den.size <= 1:
        return
    for root in np.roots(den):
        if not np.isfinite(root):
            continue
        radius = abs(complex(root))
        if radius <= POLE_ATOL:
            continue
        if abs(float(np.real(root))) <= POLE_ATOL * max(1.0, radius):
            raise ValueError(
                "denominator has a pole on the imaginary axis; "
                "Bode magnitude is unbounded there. A pole at the origin is allowed."
            )


def _select_names(specs: list[dict], names: Sequence[str] | str | None) -> list[dict]:
    if names is None:
        if not specs:
            raise ValueError("systems must contain at least one transfer function")
        used: set[str] = set()
        for spec in specs:
            spec["name"] = _claim_name(spec["name"], bool(spec.get("explicit_name")), used)
        return specs
    if isinstance(names, str):
        wanted = [names]
    else:
        wanted = [str(item) for item in names]
    if len(wanted) == 0:
        raise ValueError("names must contain at least one system")
    # Name claims for a CSV happen here, before the filter, so duplicates error first.
    used = set()
    for spec in specs:
        spec["name"] = _claim_name(spec["name"], bool(spec.get("explicit_name")), used)
    by_name = {spec["name"]: spec for spec in specs}
    missing = [item for item in wanted if item not in by_name]
    if missing:
        available = ", ".join(spec["name"] for spec in specs)
        raise ValueError(f"unknown system name: {missing[0]}. Available: {available}")
    return [by_name[item] for item in wanted]


def _read_systems(path: Path) -> list[dict]:
    rows = _read_csv_rows(path)
    specs = []
    for row in rows:
        explicit = _lookup(row, "name")
        explicit_name = explicit is not None and str(explicit).strip() != ""
        spec = _build_system(row, explicit_name=explicit_name)
        specs.append(spec)
    if not specs:
        raise ValueError(f"CSV has no data rows: {path}")
    return specs


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
            if all(value == "" for value in cleaned.values()):
                continue
            rows.append(cleaned)
    if not rows:
        raise ValueError(f"CSV has no data rows: {path}")
    return rows


def _norm_key(key: object) -> str:
    return re.sub(r"[\s_\-]", "", str(key).strip().lower())


def _lookup(row: Mapping[str, object], *keys: str) -> object | None:
    folded = {_norm_key(key): value for key, value in row.items()}
    for key in keys:
        if _norm_key(key) in folded:
            return folded[_norm_key(key)]
    return None


def _finite_number(name: str, value: object, default: float | None = None) -> float:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        if default is None:
            raise ValueError(f"{name} is required")
        return float(default)
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _frequency_grid(
    specs: Sequence[dict],
    w_min: float | None,
    w_max: float | None,
    n_points: int,
    frequency_rad_s: Sequence[float] | None,
) -> np.ndarray:
    if frequency_rad_s is not None:
        if w_min is not None or w_max is not None:
            raise ValueError("pass frequency_rad_s or w_min/w_max, not both")
        freq = np.asarray(frequency_rad_s, dtype=float).ravel()
        if freq.size == 0 or not np.all(np.isfinite(freq)) or np.any(freq <= 0):
            raise ValueError("frequency_rad_s must contain positive finite values")
        return np.unique(freq)

    spans = [_auto_span(spec["num"], spec["den"]) for spec in specs]
    auto_lo = min(lo for lo, _hi in spans)
    auto_hi = max(hi for _lo, hi in spans)
    lo = auto_lo if w_min is None else float(w_min)
    hi = auto_hi if w_max is None else float(w_max)
    if not math.isfinite(lo) or not math.isfinite(hi) or lo <= 0 or hi <= 0:
        raise ValueError("w_min and w_max must be positive finite numbers")
    if w_min is None:
        lo = _extend_low(specs, lo)
    if w_max is None:
        hi = _extend_high(specs, hi)
    if not hi > lo:
        raise ValueError("w_max must be greater than w_min")
    if hi / lo > MAX_SPAN_RATIO:
        raise ValueError("frequency span is too wide; set w_min and w_max")
    return np.logspace(math.log10(lo), math.log10(hi), n_points)


def _auto_span(num: np.ndarray, den: np.ndarray) -> tuple[float, float]:
    mags: list[float] = []
    for coeff in (num, den):
        if coeff.size <= 1:
            continue
        for root in np.roots(coeff):
            if not np.isfinite(root):
                continue
            radius = abs(complex(root))
            if radius > POLE_ATOL:
                mags.append(radius)
    if not mags:
        return DEFAULT_W_MIN, DEFAULT_W_MAX
    return min(mags) / SPAN_FACTOR, max(mags) * SPAN_FACTOR


def _extend_high(specs: Sequence[dict], hi: float) -> float:
    for _ in range(MAX_EXTEND):
        if not any(_needs_higher(spec, hi) for spec in specs):
            break
        hi *= SPAN_FACTOR
    return hi


def _extend_low(specs: Sequence[dict], lo: float) -> float:
    for _ in range(MAX_EXTEND):
        if not any(_needs_lower(spec, lo) for spec in specs):
            break
        lo /= SPAN_FACTOR
    return lo


def _needs_higher(spec: dict, w_value: float) -> bool:
    relative = (spec["den"].size - 1) - (spec["num"].size - 1)
    if relative <= 0:
        return False
    magnitude = _mag_db_scalar(spec["num"], spec["den"], w_value)
    return math.isfinite(magnitude) and magnitude >= 0.0


def _needs_lower(spec: dict, w_value: float) -> bool:
    if _origin_excess_poles(spec["num"], spec["den"]) <= 0:
        return False
    magnitude = _mag_db_scalar(spec["num"], spec["den"], w_value)
    return math.isfinite(magnitude) and magnitude <= 0.0


def _origin_excess_poles(num: np.ndarray, den: np.ndarray) -> int:
    return _trailing_zeros(den) - _trailing_zeros(num)


def _trailing_zeros(coeff: np.ndarray) -> int:
    count = 0
    for value in reversed(coeff):
        if float(value) == 0.0:
            count += 1
        else:
            break
    return count


def _eval_h(num: np.ndarray, den: np.ndarray, frequency: np.ndarray) -> np.ndarray:
    freq = np.asarray(frequency, dtype=float).ravel()
    _w, response = signal.freqs(np.asarray(num, dtype=float), np.asarray(den, dtype=float), worN=freq)
    response = np.asarray(response, dtype=complex).ravel()
    den_abs = np.abs(np.polyval(den, 1j * freq))
    scale = max(float(np.max(np.abs(den))), 1.0)
    response = np.array(response, dtype=complex, copy=True)
    response[den_abs <= DEN_FLOOR_SCALE * scale] = np.nan
    return response


def _mag_db_scalar(num: np.ndarray, den: np.ndarray, w_value: float) -> float:
    value = _eval_h(num, den, np.asarray([w_value], dtype=float))[0]
    if not np.isfinite(value):
        return float("nan")
    amplitude = abs(complex(value))
    if amplitude == 0.0:
        return float("-inf")
    return 20.0 * math.log10(amplitude)


def _response(num: np.ndarray, den: np.ndarray, frequency: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    response = _eval_h(num, den, frequency)
    magnitude = np.empty(frequency.size, dtype=float)
    phase = np.empty(frequency.size, dtype=float)
    for index, value in enumerate(response):
        if not np.isfinite(value) or complex(value) == 0:
            magnitude[index] = float("-inf") if np.isfinite(value) and complex(value) == 0 else float("nan")
            phase[index] = float("nan")
            continue
        amplitude = abs(complex(value))
        magnitude[index] = 20.0 * math.log10(amplitude)
        raw = float(np.degrees(np.angle(value)))
        if index == 0 or math.isnan(phase[index - 1]):
            phase[index] = raw
        else:
            phase[index] = _carry_phase(
                num,
                den,
                float(frequency[index - 1]),
                float(phase[index - 1]),
                float(frequency[index]),
                raw,
                0,
            )
    return magnitude, phase


def _carry_phase(
    num: np.ndarray,
    den: np.ndarray,
    w0: float,
    phase0: float,
    w1: float,
    raw1: float,
    depth: int,
) -> float:
    candidate = raw1 + 360.0 * _round_half_away((phase0 - raw1) / 360.0)
    if abs(candidate - phase0) <= PHASE_STEP_LIMIT_DEG or depth >= PHASE_REFINE_DEPTH:
        return candidate
    midpoint = math.sqrt(w0 * w1)
    value = _eval_h(num, den, np.asarray([midpoint], dtype=float))[0]
    if not np.isfinite(value) or complex(value) == 0:
        return candidate
    raw_mid = float(np.degrees(np.angle(value)))
    phase_mid = _carry_phase(num, den, w0, phase0, midpoint, raw_mid, depth + 1)
    return _carry_phase(num, den, midpoint, phase_mid, w1, raw1, depth + 1)


def _round_half_away(value: float) -> int:
    """Match MATLAB ``round`` (half away from zero) for branch selection."""

    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def _wrap180(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def _margins(spec: dict, frequency: np.ndarray, magnitude: np.ndarray, phase: np.ndarray) -> BodeMargins:
    num = spec["num"]
    den = spec["den"]
    gain_cross = _level_crossings(
        frequency,
        magnitude,
        0.0,
        CROSS_ATOL_DB,
        lambda w_value: _mag_db_scalar(num, den, w_value),
    )
    phase_cross: list[float] = []
    for level in _phase_levels(phase):
        phase_cross.extend(
            _level_crossings(
                frequency,
                phase,
                level,
                CROSS_ATOL_DEG,
                lambda w_value, level=level: _phase_near(num, den, w_value, level),
            )
        )
    phase_cross = _dedupe_frequencies(phase_cross)

    pm_candidates: list[tuple[float, float]] = []
    for w_value in gain_cross:
        phase_value = _phase_at(num, den, frequency, phase, w_value)
        if not math.isfinite(phase_value):
            continue
        pm_candidates.append((_wrap180(phase_value + 180.0), w_value))
    if pm_candidates:
        phase_margin_deg, phase_margin_rad_s = min(pm_candidates, key=lambda item: (item[0], item[1]))
    else:
        usable = magnitude[~np.isnan(magnitude)]
        if usable.size and float(np.max(usable)) < 0.0:
            phase_margin_deg, phase_margin_rad_s = float("inf"), float("nan")
        else:
            phase_margin_deg, phase_margin_rad_s = float("nan"), float("nan")

    gm_candidates: list[tuple[float, float]] = []
    for w_value in phase_cross:
        mag_value = _mag_db_scalar(num, den, w_value)
        if math.isnan(mag_value):
            continue
        gm_candidates.append((-mag_value, w_value))
    if gm_candidates:
        gain_margin_db, gain_margin_rad_s = min(gm_candidates, key=lambda item: (item[0], item[1]))
    else:
        gain_margin_db, gain_margin_rad_s = float("inf"), float("nan")

    return BodeMargins(
        name=str(spec["name"]),
        form=str(spec["form"]),
        num=[float(value) for value in num],
        den=[float(value) for value in den],
        gain_crossover_rad_s=gain_cross,
        phase_crossover_rad_s=phase_cross,
        phase_margin_deg=float(phase_margin_deg),
        gain_margin_db=float(gain_margin_db),
        phase_margin_rad_s=float(phase_margin_rad_s),
        gain_margin_rad_s=float(gain_margin_rad_s),
    )


def _phase_levels(phase: np.ndarray) -> list[float]:
    usable = [float(value) for value in phase if not math.isnan(float(value))]
    if not usable:
        return []
    low = min(usable)
    high = max(usable)
    k_min = math.ceil((low + 180.0) / 360.0 - 1e-12)
    k_max = math.floor((high + 180.0) / 360.0 + 1e-12)
    if k_max < k_min:
        return []
    return [-180.0 + 360.0 * k for k in range(k_min, k_max + 1)]


def _level_crossings(
    frequency: np.ndarray,
    values: np.ndarray,
    level: float,
    tol: float,
    evaluate,
) -> list[float]:
    found: list[float] = []
    exact = [False] * int(values.size)
    for index in range(int(values.size)):
        value = float(values[index])
        if math.isnan(value):
            continue
        if abs(value - level) <= tol:
            if index == 0 or not exact[index - 1]:
                found.append(float(frequency[index]))
            exact[index] = True
    for index in range(int(values.size) - 1):
        if exact[index] or exact[index + 1]:
            continue
        left = float(values[index])
        right = float(values[index + 1])
        if math.isnan(left) or math.isnan(right):
            continue
        if (left - level) * (right - level) < 0.0:
            found.append(
                _bisect(
                    float(frequency[index]),
                    float(frequency[index + 1]),
                    left,
                    right,
                    level,
                    tol,
                    evaluate,
                )
            )
    return _dedupe_frequencies(found)


def _bisect(
    w0: float,
    w1: float,
    v0: float,
    v1: float,
    level: float,
    tol: float,
    evaluate,
) -> float:
    lo, hi = w0, w1
    f_lo, f_hi = v0 - level, v1 - level
    for _ in range(BISECT_STEPS):
        mid = math.sqrt(lo * hi)
        value = float(evaluate(mid))
        if math.isnan(value):
            break
        f_mid = value - level
        if abs(f_mid) <= tol:
            return mid
        if f_lo * f_mid <= 0.0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return math.sqrt(lo * hi)


def _dedupe_frequencies(frequencies: Sequence[float]) -> list[float]:
    ordered = sorted(float(value) for value in frequencies if math.isfinite(value) and value > 0)
    unique: list[float] = []
    for value in ordered:
        if not unique or abs(value - unique[-1]) / value > 1e-6:
            unique.append(value)
    return unique


def _phase_near(num: np.ndarray, den: np.ndarray, w_value: float, reference: float) -> float:
    value = _eval_h(num, den, np.asarray([w_value], dtype=float))[0]
    if not np.isfinite(value) or complex(value) == 0:
        return float("nan")
    raw = float(np.degrees(np.angle(value)))
    return raw + 360.0 * _round_half_away((reference - raw) / 360.0)


def _phase_at(
    num: np.ndarray,
    den: np.ndarray,
    frequency: np.ndarray,
    phase: np.ndarray,
    w_value: float,
) -> float:
    finite = np.isfinite(phase)
    if not np.any(finite):
        return float("nan")
    log_freq = np.log(frequency[finite])
    target = math.log(w_value)
    nearest = int(np.argmin(np.abs(log_freq - target)))
    reference = float(phase[finite][nearest])
    return _phase_near(num, den, w_value, reference)


def _render_figure(
    *,
    frequency: np.ndarray,
    magnitude_db: np.ndarray,
    phase_deg: np.ndarray,
    labels: Sequence[str],
    margins: Sequence[BodeMargins],
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
        fig, axes = plt.subplots(2, 1, figsize=(10.2, 6.8), sharex=True)
        ax_mag, ax_phase = axes
        for index, label in enumerate(labels):
            color = _COLORS[index % len(_COLORS)]
            linestyle = _LINESTYLES[index % len(_LINESTYLES)]
            mag = np.array(magnitude_db[:, index], dtype=float, copy=True)
            ph = np.array(phase_deg[:, index], dtype=float, copy=True)
            mag[~np.isfinite(mag)] = np.nan
            ph[~np.isfinite(ph)] = np.nan
            ax_mag.semilogx(frequency, mag, color=color, linestyle=linestyle, linewidth=1.8, label=label)
            ax_phase.semilogx(frequency, ph, color=color, linestyle=linestyle, linewidth=1.8)
            for w_value in margins[index].gain_crossover_rad_s:
                ax_mag.plot(w_value, 0.0, marker="o", color=color, markersize=5.5, linestyle="none")
            for w_value in margins[index].phase_crossover_rad_s:
                marker_phase = _interp_log(frequency, phase_deg[:, index], w_value)
                if math.isfinite(marker_phase):
                    ax_phase.plot(
                        w_value,
                        marker_phase,
                        marker="s",
                        color=color,
                        markersize=5.5,
                        linestyle="none",
                    )
        ax_mag.axhline(0.0, color="#666666", linestyle=":", linewidth=1.0)
        for level in _reference_phase_levels(phase_deg):
            ax_phase.axhline(level, color="#666666", linestyle=":", linewidth=1.0)
        _set_padded_ylim(ax_mag, magnitude_db, reference=0.0, include_within=12.0, minimum_span=10.0)
        _set_padded_ylim(ax_phase, phase_deg, reference=-180.0, include_within=25.0, minimum_span=20.0)
        ax_mag.set_title("Bode diagram")
        ax_mag.set_ylabel("Magnitude (dB)")
        ax_mag.grid(True, which="both", color="#d0d0d0", linewidth=0.6)
        ax_mag.set_axisbelow(True)
        ax_mag.legend(loc="best", frameon=True, edgecolor="#cccccc")
        ax_phase.set_xlabel("Frequency (rad/s)")
        ax_phase.set_ylabel("Phase (deg)")
        ax_phase.grid(True, which="both", color="#d0d0d0", linewidth=0.6)
        ax_phase.set_axisbelow(True)
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


def _interp_log(frequency: np.ndarray, values: np.ndarray, w_value: float) -> float:
    mask = np.isfinite(values) & np.isfinite(frequency) & (frequency > 0)
    if np.count_nonzero(mask) < 2:
        return float("nan")
    return float(np.interp(math.log(w_value), np.log(frequency[mask]), values[mask]))


def _reference_phase_levels(phase_deg: np.ndarray) -> list[float]:
    levels = {-180.0}
    for column in range(phase_deg.shape[1]):
        levels.update(_phase_levels(phase_deg[:, column]))
    return sorted(levels)


def _set_padded_ylim(ax: object, values: np.ndarray, *, reference: float, include_within: float, minimum_span: float) -> None:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return
    low = float(np.min(finite))
    high = float(np.max(finite))
    if low - include_within <= reference <= high + include_within:
        low = min(low, reference)
        high = max(high, reference)
    span = max(high - low, minimum_span)
    ax.set_ylim(low - 0.12 * span, high + 0.22 * span)
