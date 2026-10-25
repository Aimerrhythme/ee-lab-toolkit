"""Compare PID step responses for a simple SISO plant.

The closed-loop simulation matches ``matlab/pid_step_compare.m``:

1. Build a strictly proper plant (second-order, FOPDT, or numerator/denominator).
2. Place one parallel PID, with a filtered derivative, in unity negative feedback.
3. Integrate the loop with fixed-step RK4 from zero initial conditions.
4. Measure rise time, overshoot, settling time, and steady-state error.
5. Optionally draw the overlaid step responses and control efforts.

Controller (same as MATLAB's parallel ``pid`` form)::

    C(s) = Kp + Ki/s + Kd * (kd_n * s) / (s + kd_n)

Dead time is an integer number of input-delay steps (half away from zero).
"""

from __future__ import annotations

import csv
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PLANT_FORMS = ("second_order", "fopdt", "tf")
MAX_ORDER = 8
# RK4 stays accurate when dt * (fastest |pole| or kd_n) is below this.
_DT_RATE_LIMIT = 2.0
_TAIL_FRACTION = 0.05
_RISE_LOW = 0.10
_RISE_HIGH = 0.90

_COLORS = (
    "#1f4e79",
    "#c0392b",
    "#3d7a6a",
    "#e67e22",
    "#6c3483",
    "#1a5276",
)
_LINESTYLES = ("-", "--", "-.", ":")

# Classroom defaults. examples/data uses the same plant and PID rows.
DEFAULT_PLANT = {
    "form": "second_order",
    "k": 1.0,
    "wn": 1.0,
    "zeta": 1.0,
    "tau": 1.0,
    "theta": 0.0,
}
DEFAULT_PID_SETS = (
    {"name": "P", "kp": 2.0, "ki": 0.0, "kd": 0.0},
    {"name": "PI", "kp": 2.0, "ki": 1.5, "kd": 0.0},
    {"name": "PID", "kp": 2.0, "ki": 1.5, "kd": 0.8},
)


@dataclass
class PidMetrics:
    """Step-response metrics for one PID set.

    Fields match the struct array ``result.metrics`` from ``pid_step_compare.m``.
    ``tr`` is the 10%–90% rise time of the final value, ``mp_pct`` is percent
    overshoot, ``ts`` is the ±``settle_pct`` settling time, and ``ess`` is
    ``setpoint - y_final``.
    """

    name: str
    kp: float
    ki: float
    kd: float
    tr: float
    mp_pct: float
    ts: float
    ess: float
    y_final: float
    y_peak: float
    peak_time: float
    stable: bool


@dataclass
class PidStepCompareResult:
    """Overlaid step responses and one metrics record per PID set.

    ``y`` and ``u`` have shape ``(len(time), n_sets)``: column ``i`` belongs to
    ``names[i]`` and ``metrics[i]``. ``plant['num']`` and ``plant['den']`` are
    the coefficients that were simulated (highest power first).
    """

    time: np.ndarray
    y: np.ndarray
    u: np.ndarray
    setpoint: float
    names: list[str]
    metrics: list[PidMetrics]
    plant: dict
    t_final: float
    dt: float
    kd_n: float
    settle_pct: float
    output_png: str | None
    fig: object | None = None


def pid_step_compare(
    plant: Mapping | str | Path | None = None,
    pid_sets: Mapping | Sequence | np.ndarray | str | Path | None = None,
    *,
    t_final: float = 20.0,
    dt: float = 0.01,
    setpoint: float = 1.0,
    kd_n: float = 10.0,
    settle_pct: float = 2.0,
    output_png: str | Path | None = None,
    show: bool = False,
) -> PidStepCompareResult:
    """Simulate one plant under several PID sets and compare the step responses.

    Parameters use the same names as the MATLAB name-value arguments
    (``t_final``, ``dt``, ``setpoint``, ``kd_n``, ``settle_pct``,
    ``output_png``, ``show``). ``plant`` and ``pid_sets`` may be mappings or
    CSV paths. Pass ``None`` to use the classroom defaults.
    """

    spec = _normalize_plant(plant)
    sets = _normalize_pid_sets(pid_sets)
    t_final = float(t_final)
    dt = float(dt)
    setpoint = float(setpoint)
    kd_n = float(kd_n)
    settle_pct = float(settle_pct)
    _validate_simulation(t_final, dt, setpoint, kd_n, settle_pct)

    a_mat, b_vec, c_vec = _transfer_to_ss(spec["num"], spec["den"])
    for item in sets:
        _assert_step_size(a_mat, dt, item["kd"], kd_n)

    columns_y = []
    columns_u = []
    time = None
    for item in sets:
        time, y_col, u_col = _simulate_one(
            a_mat,
            b_vec,
            c_vec,
            spec["theta"],
            dt,
            t_final,
            item["kp"],
            item["ki"],
            item["kd"],
            kd_n,
            setpoint,
        )
        columns_y.append(y_col)
        columns_u.append(u_col)

    y = np.column_stack(columns_y)
    u = np.column_stack(columns_u)
    assert time is not None
    metrics = [
        _step_metrics(time, y[:, index], setpoint, settle_pct, sets[index])
        for index in range(len(sets))
    ]
    png_text = None if output_png is None or str(output_png).strip() == "" else str(output_png)
    labels = [
        _legend_label(item["name"], item["kp"], item["ki"], item["kd"], row.stable)
        for item, row in zip(sets, metrics, strict=True)
    ]
    fig = None
    if png_text is not None or show:
        fig = _render_figure(
            time=time,
            y=y,
            u=u,
            labels=labels,
            setpoint=setpoint,
            stable=[row.stable for row in metrics],
            output_png=png_text,
            show=bool(show),
        )
    return PidStepCompareResult(
        time=time,
        y=y,
        u=u,
        setpoint=setpoint,
        names=[item["name"] for item in sets],
        metrics=metrics,
        plant=spec,
        t_final=t_final,
        dt=dt,
        kd_n=kd_n,
        settle_pct=settle_pct,
        output_png=png_text,
        fig=fig,
    )


def format_metrics_table(metrics: Sequence[PidMetrics]) -> str:
    """Format rise time, overshoot, settling time, and steady-state error."""

    header = (
        f"{'name':<16} {'kp':>8} {'ki':>8} {'kd':>8} "
        f"{'tr':>8} {'Mp%':>8} {'ts':>8} {'ess':>8}"
    )
    lines = [header]
    for row in metrics:
        lines.append(
            f"{row.name:<16} {row.kp:8.3f} {row.ki:8.3f} {row.kd:8.3f} "
            f"{_fmt_num(row.tr)} {_fmt_num(row.mp_pct)} {_fmt_num(row.ts)} {_fmt_num(row.ess)}"
        )
    return "\n".join(lines)


def _fmt_num(value: float) -> str:
    if not np.isfinite(value):
        return f"{'nan':>8}"
    if abs(value) < 5e-4:
        value = 0.0
    return f"{value:8.3f}"


def _validate_simulation(t_final: float, dt: float, setpoint: float, kd_n: float, settle_pct: float) -> None:
    if not np.isfinite(t_final) or t_final <= 0:
        raise ValueError("t_final must be a positive finite number")
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("dt must be a positive finite number")
    if not np.isfinite(setpoint):
        raise ValueError("setpoint must be a finite number")
    if not np.isfinite(kd_n) or kd_n <= 0:
        raise ValueError("kd_n must be a positive finite number")
    if not np.isfinite(settle_pct) or not 0 < settle_pct <= 100:
        raise ValueError("settle_pct must be in the interval (0, 100]")
    n_steps = _round_half_away(t_final / dt)
    if n_steps < 2:
        raise ValueError("t_final must cover at least 2 steps")
    if n_steps > 2_000_000:
        raise ValueError("t_final/dt is too large; increase dt or shorten t_final")


def _round_half_away(value: float) -> int:
    """Round half away from zero so delay and grid counts match MATLAB ``round``."""

    if value >= 0:
        return int(np.floor(value + 0.5))
    return int(np.ceil(value - 0.5))


def _norm_key(key: object) -> str:
    return re.sub(r"[\s_\-]", "", str(key).strip().lower())


def _finite(name: str, value: object, default: float | None = None) -> float:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        if default is None:
            raise ValueError(f"{name} is required")
        value = default
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not np.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


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


def _lookup(row: Mapping[str, object], *keys: str) -> object | None:
    folded = {_norm_key(key): value for key, value in row.items()}
    for key in keys:
        if key in folded:
            return folded[key]
    return None


def _normalize_plant(plant: Mapping | str | Path | None) -> dict:
    if plant is None:
        raw: Mapping[str, object] = DEFAULT_PLANT
    elif isinstance(plant, (str, Path)):
        rows = _read_csv_rows(Path(plant))
        raw = rows[0]
    elif isinstance(plant, Mapping):
        raw = plant
    else:
        raise TypeError("plant must be a mapping or a CSV path")

    form = str(_lookup(raw, "form") or "second_order").strip().lower()
    if form not in PLANT_FORMS:
        joined = ", ".join(PLANT_FORMS)
        raise ValueError(f"form must be one of: {joined}")

    k_gain = _finite("k", _lookup(raw, "k", "gain"), 1.0)
    wn = _finite("wn", _lookup(raw, "wn", "omegan"), 1.0)
    zeta = _finite("zeta", _lookup(raw, "zeta"), 1.0)
    tau = _finite("tau", _lookup(raw, "tau"), 1.0)
    theta = _finite("theta", _lookup(raw, "theta", "delay", "l"), 0.0)
    if theta < 0:
        raise ValueError("theta must be >= 0")

    if form == "second_order":
        if wn <= 0:
            raise ValueError("wn must be positive")
        num = [k_gain * wn * wn]
        den = [1.0, 2.0 * zeta * wn, wn * wn]
    elif form == "fopdt":
        if tau <= 0:
            raise ValueError("tau must be positive")
        num = [k_gain]
        den = [tau, 1.0]
    else:
        num_value = _lookup(raw, "num", "numerator")
        den_value = _lookup(raw, "den", "denominator")
        if num_value is None or den_value is None:
            raise ValueError("form 'tf' requires num and den coefficients")
        num = _coeff_list(num_value, "num")
        den = _coeff_list(den_value, "den")

    num_arr, den_arr = _prepare_coefficients(num, den)
    return {
        "form": form,
        "k": float(k_gain),
        "wn": float(wn),
        "zeta": float(zeta),
        "tau": float(tau),
        "theta": float(theta),
        "num": [float(value) for value in num_arr],
        "den": [float(value) for value in den_arr],
    }


def _coeff_list(value: object, name: str) -> list[float]:
    if isinstance(value, str):
        text = value.replace(",", " ").replace(";", " ")
        parts = [part for part in text.split() if part]
        if not parts:
            raise ValueError(f"{name} must be a coefficient vector")
        return [_finite(name, part) for part in parts]
    array = np.asarray(value, dtype=float).ravel()
    if array.size == 0 or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite coefficient vector")
    return [float(item) for item in array]


def _prepare_coefficients(num: Sequence[float], den: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    num_arr = np.asarray(num, dtype=float).ravel()
    den_arr = np.asarray(den, dtype=float).ravel()
    if num_arr.size == 0 or den_arr.size == 0:
        raise ValueError("num and den must be non-empty")
    if not np.all(np.isfinite(num_arr)) or not np.all(np.isfinite(den_arr)):
        raise ValueError("num and den must be finite")
    while den_arr.size > 1 and den_arr[0] == 0:
        den_arr = den_arr[1:]
    while num_arr.size > 1 and num_arr[0] == 0:
        num_arr = num_arr[1:]
    if den_arr[0] == 0:
        raise ValueError("denominator leading coefficient must be nonzero")
    if num_arr.size >= den_arr.size:
        raise ValueError("plant must be strictly proper (numerator degree < denominator degree)")
    if den_arr.size - 1 > MAX_ORDER:
        raise ValueError(f"plant order must be <= {MAX_ORDER}")
    if den_arr.size < 2:
        raise ValueError("plant order must be at least 1")
    return num_arr, den_arr


def _transfer_to_ss(num: Sequence[float], den: Sequence[float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Controllable canonical form for a strictly proper transfer function."""

    num_arr = np.asarray(num, dtype=float).ravel().copy()
    den_arr = np.asarray(den, dtype=float).ravel().copy()
    num_arr = num_arr / den_arr[0]
    den_arr = den_arr / den_arr[0]
    order = den_arr.size - 1
    b_coeff = np.zeros(order, dtype=float)
    b_coeff[order - num_arr.size :] = num_arr
    a_mat = np.zeros((order, order), dtype=float)
    a_mat[0, :] = -den_arr[1:]
    if order > 1:
        a_mat[1:, :-1] = np.eye(order - 1)
    b_vec = np.zeros(order, dtype=float)
    b_vec[0] = 1.0
    return a_mat, b_vec, b_coeff


def _auto_name(kp: float, ki: float, kd: float, used: set[str]) -> str:
    if ki == 0 and kd == 0:
        base = "P"
    elif kd == 0:
        base = "PI"
    elif ki == 0:
        base = "PD"
    else:
        base = "PID"
    name = base
    suffix = 2
    while name in used:
        name = f"{base}{suffix}"
        suffix += 1
    used.add(name)
    return name


def _normalize_pid_sets(pid_sets: Mapping | Sequence | np.ndarray | str | Path | None) -> list[dict]:
    if pid_sets is None:
        rows: Sequence = DEFAULT_PID_SETS
    elif isinstance(pid_sets, (str, Path)):
        rows = _read_csv_rows(Path(pid_sets))
    elif isinstance(pid_sets, np.ndarray) and pid_sets.ndim == 2 and pid_sets.shape[1] == 3:
        rows = [{"kp": float(item[0]), "ki": float(item[1]), "kd": float(item[2])} for item in pid_sets]
    elif isinstance(pid_sets, Mapping):
        rows = [pid_sets]
    elif isinstance(pid_sets, Sequence) and not isinstance(pid_sets, (str, bytes)):
        rows = list(pid_sets)
    else:
        raise TypeError("pid_sets must be a list of PID mappings, an N-by-3 array, or a CSV path")
    if len(rows) == 0:
        raise ValueError("pid_sets must contain at least one controller")

    parsed: list[dict] = []
    used: set[str] = set()
    for row in rows:
        if isinstance(row, Mapping):
            kp = _finite("kp", _lookup(row, "kp"))
            ki = _finite("ki", _lookup(row, "ki"), 0.0)
            kd = _finite("kd", _lookup(row, "kd"), 0.0)
            name_value = _lookup(row, "name")
            name = "" if name_value is None else str(name_value).strip()
        elif isinstance(row, (Sequence, np.ndarray)) and len(row) == 3 and not isinstance(row, (str, bytes)):
            kp = _finite("kp", row[0])
            ki = _finite("ki", row[1])
            kd = _finite("kd", row[2])
            name = ""
        else:
            raise TypeError("each PID set must be a mapping with kp, ki, kd or a 3-vector")
        if name == "":
            name = _auto_name(kp, ki, kd, used)
        elif name in used:
            raise ValueError(f"duplicate PID name: {name}")
        else:
            used.add(name)
        parsed.append({"name": name, "kp": kp, "ki": ki, "kd": kd})
    return parsed


def _assert_step_size(a_mat: np.ndarray, dt: float, kd: float, kd_n: float) -> None:
    poles = np.linalg.eigvals(a_mat)
    rate = float(np.max(np.abs(poles))) if poles.size else 0.0
    if kd != 0.0:
        rate = max(rate, float(kd_n))
    if rate > 0 and dt * rate > _DT_RATE_LIMIT:
        raise ValueError(
            "dt is large for this plant or derivative filter. "
            f"Fastest rate is about {rate:.4g} rad/s; use dt < {_DT_RATE_LIMIT / rate:.4g} s."
        )


def _simulate_one(
    a_mat: np.ndarray,
    b_vec: np.ndarray,
    c_vec: np.ndarray,
    theta: float,
    dt: float,
    t_final: float,
    kp: float,
    ki: float,
    kd: float,
    kd_n: float,
    setpoint: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_steps = _round_half_away(t_final / dt)
    time = np.arange(n_steps + 1, dtype=float) * dt
    order = a_mat.shape[0]
    state = np.zeros(order + 2, dtype=float)
    n_delay = _round_half_away(theta / dt)
    buffer = np.zeros(n_delay, dtype=float)
    y = np.empty(time.size, dtype=float)
    u = np.empty(time.size, dtype=float)

    for index in range(time.size):
        y[index], u[index] = _output(state, c_vec, kp, ki, kd, kd_n, setpoint)
        if index == n_steps:
            break
        if n_delay > 0:
            u_hold: float | None = float(buffer[0])
            buffer[:-1] = buffer[1:]
            buffer[-1] = u[index]
        else:
            u_hold = None
        state = _rk4(state, dt, a_mat, b_vec, c_vec, kp, ki, kd, kd_n, setpoint, u_hold)
    return time, y, u


def _output(
    state: np.ndarray,
    c_vec: np.ndarray,
    kp: float,
    ki: float,
    kd: float,
    kd_n: float,
    setpoint: float,
) -> tuple[float, float]:
    order = c_vec.size
    y_now = float(c_vec @ state[:order])
    error = setpoint - y_now
    u_now = kp * error
    if ki != 0.0:
        u_now += ki * float(state[order])
    if kd != 0.0:
        u_now += kd * kd_n * (error - float(state[order + 1]))
    return y_now, u_now


def _rhs(
    state: np.ndarray,
    a_mat: np.ndarray,
    b_vec: np.ndarray,
    c_vec: np.ndarray,
    kp: float,
    ki: float,
    kd: float,
    kd_n: float,
    setpoint: float,
    u_hold: float | None,
) -> np.ndarray:
    order = c_vec.size
    y_now = float(c_vec @ state[:order])
    error = setpoint - y_now
    u_now = kp * error
    if ki != 0.0:
        u_now += ki * float(state[order])
    if kd != 0.0:
        u_now += kd * kd_n * (error - float(state[order + 1]))
    u_plant = u_now if u_hold is None else u_hold
    deriv = np.zeros_like(state)
    deriv[:order] = a_mat @ state[:order] + b_vec * u_plant
    if ki != 0.0:
        deriv[order] = error
    if kd != 0.0:
        deriv[order + 1] = kd_n * (error - float(state[order + 1]))
    return deriv


def _rk4(
    state: np.ndarray,
    dt: float,
    a_mat: np.ndarray,
    b_vec: np.ndarray,
    c_vec: np.ndarray,
    kp: float,
    ki: float,
    kd: float,
    kd_n: float,
    setpoint: float,
    u_hold: float | None,
) -> np.ndarray:
    k1 = _rhs(state, a_mat, b_vec, c_vec, kp, ki, kd, kd_n, setpoint, u_hold)
    k2 = _rhs(state + 0.5 * dt * k1, a_mat, b_vec, c_vec, kp, ki, kd, kd_n, setpoint, u_hold)
    k3 = _rhs(state + 0.5 * dt * k2, a_mat, b_vec, c_vec, kp, ki, kd, kd_n, setpoint, u_hold)
    k4 = _rhs(state + dt * k3, a_mat, b_vec, c_vec, kp, ki, kd, kd_n, setpoint, u_hold)
    return state + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def _step_metrics(
    time: np.ndarray,
    y: np.ndarray,
    setpoint: float,
    settle_pct: float,
    pid: Mapping[str, float | str],
) -> PidMetrics:
    name = str(pid["name"])
    kp = float(pid["kp"])
    ki = float(pid["ki"])
    kd = float(pid["kd"])
    if not np.all(np.isfinite(y)):
        return _blank_metrics(name, kp, ki, kd)

    n_tail = max(5, _round_half_away(_TAIL_FRACTION * y.size))
    n_tail = min(n_tail, y.size)
    y_final = float(np.mean(y[-n_tail:]))
    stable = _response_is_stable(y, setpoint)
    if abs(y_final) < 1e-9:
        direction = 1.0 if setpoint >= 0 else -1.0
        tr = float("nan")
        mp_pct = float("nan")
        peak_idx = int(np.argmax(y) if direction > 0 else np.argmin(y))
    else:
        direction = 1.0 if y_final >= 0 else -1.0
        t_low = _first_reach(time, y, _RISE_LOW * y_final, direction)
        t_high = _first_reach(time, y, _RISE_HIGH * y_final, direction)
        if np.isfinite(t_low) and np.isfinite(t_high) and t_high >= t_low:
            tr = float(t_high - t_low)
        else:
            tr = float("nan")
        peak_idx = int(np.argmax(y) if direction > 0 else np.argmin(y))
        y_ext = float(y[peak_idx])
        overshoot = (y_ext - y_final) * direction
        mp_pct = float(max(overshoot, 0.0) / abs(y_final) * 100.0)

    band = (settle_pct / 100.0) * max(abs(y_final), 1e-12)
    inside = np.abs(y - y_final) <= band
    if bool(inside[-1]):
        outside = np.flatnonzero(~inside)
        if outside.size == 0:
            ts = float(time[0])
        else:
            ts = _enter_band(time, y, y_final, band, int(outside[-1]))
    else:
        ts = float("nan")

    return PidMetrics(
        name=name,
        kp=kp,
        ki=ki,
        kd=kd,
        tr=tr,
        mp_pct=mp_pct,
        ts=ts,
        ess=float(setpoint - y_final),
        y_final=y_final,
        y_peak=float(y[peak_idx]),
        peak_time=float(time[peak_idx]),
        stable=stable,
    )


def _blank_metrics(name: str, kp: float, ki: float, kd: float) -> PidMetrics:
    nan = float("nan")
    return PidMetrics(
        name=name,
        kp=kp,
        ki=ki,
        kd=kd,
        tr=nan,
        mp_pct=nan,
        ts=nan,
        ess=nan,
        y_final=nan,
        y_peak=nan,
        peak_time=nan,
        stable=False,
    )


def _response_is_stable(y: np.ndarray, setpoint: float) -> bool:
    if not np.all(np.isfinite(y)):
        return False
    mid = float(y[y.size // 2])
    end = float(y[-1])
    scale = max(abs(setpoint), 1.0)
    if abs(end) > 8.0 * scale and abs(end) > 3.0 * abs(mid) + scale:
        return False
    return True


def _first_reach(time: np.ndarray, y: np.ndarray, level: float, direction: float) -> float:
    hit = np.flatnonzero(y >= level) if direction > 0 else np.flatnonzero(y <= level)
    if hit.size == 0:
        return float("nan")
    index = int(hit[0])
    if index == 0:
        return float(time[0])
    y0 = float(y[index - 1])
    y1 = float(y[index])
    if y1 == y0:
        return float(time[index])
    frac = (level - y0) / (y1 - y0)
    frac = min(max(frac, 0.0), 1.0)
    return float(time[index - 1] + frac * (time[index] - time[index - 1]))


def _enter_band(time: np.ndarray, y: np.ndarray, y_final: float, band: float, outside_index: int) -> float:
    """Interpolate the last time the response enters the settling band."""

    nxt = outside_index + 1
    if nxt >= y.size:
        return float(time[-1])
    y0 = float(y[outside_index])
    y1 = float(y[nxt])
    t0 = float(time[outside_index])
    t1 = float(time[nxt])
    if y1 == y0:
        return t1
    candidates = []
    for level in (y_final - band, y_final + band):
        if (y0 - level) * (y1 - level) <= 0:
            frac = (level - y0) / (y1 - y0)
            if 0.0 < frac <= 1.0:
                candidates.append(t0 + frac * (t1 - t0))
    if not candidates:
        return t1
    return float(min(candidates))


def _legend_label(name: str, kp: float, ki: float, kd: float, stable: bool) -> str:
    label = f"{name} (Kp={kp:.4g}, Ki={ki:.4g}, Kd={kd:.4g})"
    if not stable:
        return label + " diverging"
    return label


def _render_figure(
    *,
    time: np.ndarray,
    y: np.ndarray,
    u: np.ndarray,
    labels: Sequence[str],
    setpoint: float,
    stable: Sequence[bool],
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
        ax_y, ax_u = axes
        for index, label in enumerate(labels):
            color = _COLORS[index % len(_COLORS)]
            linestyle = _LINESTYLES[index % len(_LINESTYLES)]
            y_plot = np.array(y[:, index], dtype=float, copy=True)
            u_plot = np.array(u[:, index], dtype=float, copy=True)
            y_plot[~np.isfinite(y_plot)] = np.nan
            u_plot[~np.isfinite(u_plot)] = np.nan
            ax_y.plot(time, y_plot, color=color, linestyle=linestyle, linewidth=1.8, label=label)
            ax_u.plot(time, u_plot, color=color, linestyle=linestyle, linewidth=1.5, label=label)
        ax_y.axhline(setpoint, color="#666666", linestyle=":", linewidth=1.1, label="Setpoint")
        _focus_ylim(ax_y, y, setpoint, stable, include_zero=True)
        _focus_ylim(ax_u, u, 0.0, stable, include_zero=True)
        ax_y.set_title("PID step response comparison")
        ax_y.set_ylabel("Output y")
        ax_y.grid(True, color="#d0d0d0", linewidth=0.6)
        ax_y.set_axisbelow(True)
        ax_y.legend(loc="best", frameon=True, edgecolor="#cccccc")
        ax_u.set_title("Control effort")
        ax_u.set_xlabel("Time (s)")
        ax_u.set_ylabel("Control u")
        ax_u.grid(True, color="#d0d0d0", linewidth=0.6)
        ax_u.set_axisbelow(True)
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


def _focus_ylim(
    ax: object,
    series: np.ndarray,
    reference: float,
    stable: Sequence[bool],
    include_zero: bool,
) -> None:
    kept = []
    for index, is_stable in enumerate(stable):
        column = series[:, index]
        if is_stable and np.all(np.isfinite(column)):
            kept.append(column)
    if not kept:
        return
    stacked = np.concatenate(kept)
    low = float(np.min(stacked))
    high = float(np.max(stacked))
    if include_zero:
        low = min(low, 0.0, reference)
        high = max(high, 0.0, reference)
    span = max(high - low, 0.5)
    ax.set_ylim(low - 0.08 * span, high + 0.22 * span)
