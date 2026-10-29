"""Torque-speed curves for a three-phase induction motor and a DC motor.

The calculations match ``matlab/motor_torque_speed.m``. No toolbox and no SciPy.

Induction motor
---------------
Per-phase equivalent circuit (parameters referred to the stator). ``poles`` is
the number of poles, not pole pairs.

    n_sync = 120 * f / poles
    omega_sync = 2 * pi * n_sync / 60

Star (``y``): phase voltage is ``V_line / sqrt(3)``. Delta (``d``): phase
voltage is ``V_line``. With core loss neglected, ``Rc`` is open.

    Zm = Rc || j Xm
    Z2 = R2/s + j X2          (rotor open when s = 0)
    Zf = Zm || Z2
    Zin = R1 + j X1 + Zf
    I1 = Vph / Zin
    P_ag = 3 * |I2|^2 * R2 / s
    T = P_ag / omega_sync
    P_mech = (1 - s) * P_ag

Thevenin constants seen by the rotor (exact for this circuit):

    Vth = Vph * Zm / (R1 + j X1 + Zm)
    Zth = (R1 + j X1) || Zm
    s_bd = R2 / sqrt(Rth^2 + (Xth + X2)^2)
    T_bd = 3/(2*omega_sync) * |Vth|^2 / (Rth + sqrt(Rth^2 + (Xth + X2)^2))

``T_bd`` does not depend on ``R2``. ``s_bd`` is proportional to ``R2``.
Developed torque scales with the square of the phase voltage. ``T`` is the
developed electromagnetic torque. Friction, windage, and stray loss are not
in the model.

DC motors
---------
Steady state, unsaturated, no brush drop. ``K_phi`` is in V·s/rad, which is
the same as N·m/A.

Separately excited (field fixed while the armature voltage changes):

    omega = V / K_phi - (Ra / K_phi^2) * T
    T_stall = K_phi * V / Ra

Shunt (field across the same terminals), ``K_phi = k_f * V / Rf``:

    omega_noload = Rf / k_f          (independent of V)
    T_stall = k_f * V^2 / (Rf * Ra)

Series, ``K_phi = k_f * I``:

    T = k_f * I^2
    omega = V / sqrt(k_f * T) - (Ra + Rs) / k_f

The no-load speed of the unsaturated series model is infinite, so the series
curve is swept between ``i_min`` and ``i_max`` instead of down to zero torque.
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

DEFAULT_INDUCTION_V = 380.0
DEFAULT_DC_V = 220.0
DEFAULT_F = 50.0
DEFAULT_POLES = 4
DEFAULT_R1 = 0.5
DEFAULT_X1 = 1.5
DEFAULT_R2 = 0.4
DEFAULT_X2 = 1.5
DEFAULT_XM = 40.0
DEFAULT_RA_SEPARATE = 1.0
DEFAULT_K_PHI = 1.5
DEFAULT_RA_SHUNT = 1.0
DEFAULT_RF = 220.0
DEFAULT_K_F_SHUNT = 1.5
DEFAULT_RA_SERIES = 0.4
DEFAULT_RS = 0.2
DEFAULT_K_F_SERIES = 0.08
DEFAULT_N_POINTS = 401
SCAN_POINTS = 200
BISECT_STEPS = 60
SLIP_OPEN = 1e-14
RATED_SCAN_FLOOR = 1e-8

_MOTORS = ("induction", "dc_shunt", "dc_separate", "dc_series")
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

_PARAM_NAMES = {
    "name",
    "motor",
    "v",
    "f",
    "poles",
    "connection",
    "r1",
    "x1",
    "r2",
    "x2",
    "xm",
    "rc",
    "p_rated",
    "s_rated",
    "t_rated",
    "ra",
    "rf",
    "rs",
    "k_phi",
    "k_f",
    "i_min",
    "i_max",
    "s_min",
    "s_max",
    "n_points",
    "csv_path",
    "output_csv",
    "output_png",
    "show",
}

_CSV_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name",),
    "motor": ("motor", "type", "kind"),
    "v": ("v", "vline", "vt", "voltage"),
    "f": ("f", "frequency", "freq"),
    "poles": ("poles",),
    "connection": ("connection", "conn"),
    "r1": ("r1",),
    "x1": ("x1",),
    "r2": ("r2",),
    "x2": ("x2",),
    "xm": ("xm",),
    "rc": ("rc",),
    "p_rated": ("prated",),
    "s_rated": ("srated",),
    "t_rated": ("trated",),
    "ra": ("ra",),
    "rf": ("rf",),
    "rs": ("rs",),
    "k_phi": ("kphi",),
    "k_f": ("kf",),
    "i_min": ("imin",),
    "i_max": ("imax",),
    "s_min": ("smin",),
    "s_max": ("smax",),
    "n_points": ("npoints",),
}

_SUMMARY_FIELDS = (
    "name",
    "motor",
    "connection",
    "v",
    "f",
    "poles",
    "n_sync_rpm",
    "v_phase",
    "v_th",
    "r_th",
    "x_th",
    "torque_start_nm",
    "slip_breakdown",
    "speed_breakdown_rpm",
    "torque_breakdown_nm",
    "s_rated",
    "speed_rated_rpm",
    "torque_rated_nm",
    "i_line_rated_a",
    "i2_rated_a",
    "power_mech_rated_w",
    "power_in_rated_w",
    "pf_rated",
    "efficiency_rated",
    "ra",
    "rf",
    "rs",
    "k_phi",
    "k_f",
    "i_field_a",
    "speed_noload_rpm",
    "torque_stall_nm",
    "i_stall_a",
)


@dataclass
class MotorCase:
    """One torque-speed curve and its characteristic points.

    Induction fields (``n_sync_rpm`` through ``torque_breakdown_nm``, and the
    Thevenin set) are NaN for a DC motor. DC fields (``ra`` through
    ``i_stall_a``) are NaN for an induction motor. ``speed_noload_rpm`` is
    infinite for the unsaturated series model. ``efficiency_rated`` is the
    fraction ``P_mech / P_in`` in the motoring region, not a percent.
    Curve arrays are one sample per slip or torque step. ``slip`` is NaN on
    a DC curve. ``i_phase_a`` is the stator phase current, or the DC armature
    current. ``i2_a`` is the rotor current referred to the stator.
    """

    name: str
    motor: str
    connection: str
    v: float
    f: float
    poles: float
    r1: float
    x1: float
    r2: float
    x2: float
    xm: float
    rc: float
    n_sync_rpm: float
    omega_sync_rad_s: float
    v_phase: float
    v_th: float
    r_th: float
    x_th: float
    torque_start_nm: float
    slip_breakdown: float
    speed_breakdown_rpm: float
    torque_breakdown_nm: float
    s_rated: float
    speed_rated_rpm: float
    torque_rated_nm: float
    i_line_rated_a: float
    i2_rated_a: float
    power_mech_rated_w: float
    power_in_rated_w: float
    pf_rated: float
    efficiency_rated: float
    p_rated_w: float
    ra: float
    rf: float
    rs: float
    k_phi: float
    k_f: float
    i_field_a: float
    speed_noload_rpm: float
    torque_stall_nm: float
    i_stall_a: float
    i_min: float
    i_max: float
    s_min: float
    s_max: float
    n_points: int
    n_samples: int
    slip: np.ndarray
    speed_rpm: np.ndarray
    speed_rad_s: np.ndarray
    torque_nm: np.ndarray
    i_line_a: np.ndarray
    i_phase_a: np.ndarray
    i2_a: np.ndarray
    power_in_w: np.ndarray
    power_mech_w: np.ndarray
    power_factor: np.ndarray
    efficiency: np.ndarray


@dataclass
class MotorTorqueSpeedResult:
    """One or more torque-speed cases, a text summary, and optional files.

    A CSV with several rows and no ``name`` returns every row so the figure
    can compare them. ``summary`` is the same text as ``format_table``.
    """

    cases: list[MotorCase]
    summary: str
    output_csv: str | None
    output_png: str | None
    fig: object | None = None


def motor_torque_speed(
    source: str | Path | None = None,
    *,
    name: str = "",
    motor: str = "induction",
    v: float | None = None,
    f: float = DEFAULT_F,
    poles: int = DEFAULT_POLES,
    connection: str = "y",
    r1: float = DEFAULT_R1,
    x1: float = DEFAULT_X1,
    r2: float = DEFAULT_R2,
    x2: float = DEFAULT_X2,
    xm: float = DEFAULT_XM,
    rc: float | None = None,
    p_rated: float | None = None,
    s_rated: float | None = None,
    t_rated: float | None = None,
    ra: float | None = None,
    rf: float | None = None,
    rs: float | None = None,
    k_phi: float | None = None,
    k_f: float | None = None,
    i_min: float | None = None,
    i_max: float | None = None,
    s_min: float = 0.0,
    s_max: float = 1.0,
    n_points: int = DEFAULT_N_POINTS,
    csv_path: str | Path | None = None,
    output_csv: str | Path | None = None,
    output_png: str | Path | None = None,
    show: bool = False,
) -> MotorTorqueSpeedResult:
    """Compute torque-speed curves and the starting, breakdown, and rated points.

    Parameters use the same names as the MATLAB name-value arguments.
    ``source`` or ``csv_path`` reads a parameter CSV. A blank cell keeps the
    corresponding argument. With no ``name``, every CSV row is computed and
    drawn together. With ``name``, that one row is computed.
    """

    specs = _resolve_specs(
        source,
        csv_path=csv_path,
        name=name,
        motor=motor,
        v=v,
        f=f,
        poles=poles,
        connection=connection,
        r1=r1,
        x1=x1,
        r2=r2,
        x2=x2,
        xm=xm,
        rc=rc,
        p_rated=p_rated,
        s_rated=s_rated,
        t_rated=t_rated,
        ra=ra,
        rf=rf,
        rs=rs,
        k_phi=k_phi,
        k_f=k_f,
        i_min=i_min,
        i_max=i_max,
        s_min=s_min,
        s_max=s_max,
        n_points=n_points,
    )
    show = _as_bool("show", show)
    cases = [_build_case(spec) for spec in specs]
    summary = _format_cases(cases)
    csv_out = None if output_csv is None or str(output_csv).strip() == "" else str(output_csv)
    png_out = None if output_png is None or str(output_png).strip() == "" else str(output_png)
    result = MotorTorqueSpeedResult(
        cases=cases,
        summary=summary,
        output_csv=csv_out,
        output_png=png_out,
        fig=None,
    )
    if csv_out is not None:
        _write_summary(Path(csv_out), cases)
    if png_out is not None or show:
        result.fig = _render_figure(cases, png_out, show)
    return result


def format_table(result: MotorTorqueSpeedResult) -> str:
    """Format the characteristic points of each case as text."""

    return result.summary


def _format_cases(cases: Sequence[MotorCase]) -> str:
    return "\n\n".join(_format_case(case) for case in cases)


def _format_case(case: MotorCase) -> str:
    head = f"name={case.name}  motor={case.motor}"
    if case.motor == "induction":
        lines = [
            (
                f"{head}  connection={case.connection}  V={_compact(case.v)}  "
                f"f={_compact(case.f)}  poles={_compact(case.poles)}  "
                f"n_sync={_compact(case.n_sync_rpm)}  N={case.n_samples}"
            ),
            (
                f"R1={_compact(case.r1)}  X1={_compact(case.x1)}  R2={_compact(case.r2)}  "
                f"X2={_compact(case.x2)}  Xm={_compact(case.xm)}  Rc={_compact(case.rc)}  "
                f"Vph={_compact(case.v_phase)}  Vth={_compact(case.v_th)}  "
                f"Rth={_compact(case.r_th)}  Xth={_compact(case.x_th)}"
            ),
            (
                f"T_start={_compact(case.torque_start_nm)}  s_bd={_compact(case.slip_breakdown)}  "
                f"n_bd={_compact(case.speed_breakdown_rpm)}  T_bd={_compact(case.torque_breakdown_nm)}"
            ),
            _rated_induction(case),
        ]
        return "\n".join(lines)
    if case.motor == "dc_shunt":
        identity = (
            f"{head}  V={_compact(case.v)}  Ra={_compact(case.ra)}  Rf={_compact(case.rf)}  "
            f"Kf={_compact(case.k_f)}  Kphi={_compact(case.k_phi)}  If={_compact(case.i_field_a)}  "
            f"N={case.n_samples}"
        )
    elif case.motor == "dc_series":
        identity = (
            f"{head}  V={_compact(case.v)}  Ra={_compact(case.ra)}  Rs={_compact(case.rs)}  "
            f"Kf={_compact(case.k_f)}  Imin={_compact(case.i_min)}  Imax={_compact(case.i_max)}  "
            f"N={case.n_samples}"
        )
    else:
        identity = (
            f"{head}  V={_compact(case.v)}  Ra={_compact(case.ra)}  "
            f"Kphi={_compact(case.k_phi)}  N={case.n_samples}"
        )
    return "\n".join(
        [
            identity,
            (
                f"n0={_compact(case.speed_noload_rpm)}  T_stall={_compact(case.torque_stall_nm)}  "
                f"I_stall={_compact(case.i_stall_a)}"
            ),
            _rated_dc(case),
        ]
    )


def _rated_induction(case: MotorCase) -> str:
    if not math.isfinite(case.s_rated):
        return "rated  undefined"
    return (
        f"rated  s={_compact(case.s_rated)}  n={_compact(case.speed_rated_rpm)}  "
        f"T={_compact(case.torque_rated_nm)}  I_line={_compact(case.i_line_rated_a)}  "
        f"I2={_compact(case.i2_rated_a)}  P_mech={_compact(case.power_mech_rated_w)}  "
        f"P_in={_compact(case.power_in_rated_w)}  pf={_compact(case.pf_rated)}  "
        f"eta={_eta_text(case.efficiency_rated)}"
    )


def _rated_dc(case: MotorCase) -> str:
    if not math.isfinite(case.torque_rated_nm):
        return "rated  undefined"
    return (
        f"rated  n={_compact(case.speed_rated_rpm)}  T={_compact(case.torque_rated_nm)}  "
        f"I_line={_compact(case.i_line_rated_a)}  P_mech={_compact(case.power_mech_rated_w)}  "
        f"P_in={_compact(case.power_in_rated_w)}  eta={_eta_text(case.efficiency_rated)}"
    )


def _eta_text(value: float) -> str:
    if not math.isfinite(value):
        return "nan"
    return f"{100.0 * value:.4f}%"


def _build_case(spec: Mapping[str, object]) -> MotorCase:
    motor = _normalize_motor(spec["motor"])
    name = _text(spec["name"])
    parsed = {key: spec[key] for key in spec}
    parsed["motor"] = motor
    parsed["name"] = name
    for key in (
        "v",
        "rc",
        "p_rated",
        "s_rated",
        "t_rated",
        "ra",
        "rf",
        "rs",
        "k_phi",
        "k_f",
        "i_min",
        "i_max",
    ):
        parsed[key] = _optional_number(key, spec[key])
    _reject_unused(motor, parsed)
    if motor == "induction":
        return _build_induction(parsed)
    if motor == "dc_series":
        return _build_series(parsed)
    return _build_dc_linear(parsed)


def _reject_unused(motor: str, spec: Mapping[str, object]) -> None:
    if motor == "induction":
        banned = ("t_rated", "ra", "rf", "rs", "k_phi", "k_f", "i_min", "i_max")
    elif motor == "dc_separate":
        banned = ("s_rated", "rc", "rf", "rs", "k_f", "i_min", "i_max")
    elif motor == "dc_shunt":
        banned = ("s_rated", "rc", "rs", "k_phi", "i_min", "i_max")
    else:
        banned = ("s_rated", "rc", "rf", "k_phi")
    for key in banned:
        if spec[key] is not None:
            raise ValueError(f"{key} does not apply to motor '{motor}'")


def _build_induction(spec: Mapping[str, object]) -> MotorCase:
    v_line = _positive("v", DEFAULT_INDUCTION_V if spec["v"] is None else spec["v"])
    frequency = _positive("f", spec["f"])
    poles = _positive_int("poles", spec["poles"], minimum=2, maximum=64)
    if poles % 2 != 0:
        raise ValueError("poles must be an even integer (2, 4, 6, ...)")
    connection = _normalize_connection(spec["connection"])
    r1 = _nonnegative("r1", spec["r1"])
    x1 = _nonnegative("x1", spec["x1"])
    r2 = _positive("r2", spec["r2"])
    x2 = _nonnegative("x2", spec["x2"])
    xm = _positive("xm", spec["xm"])
    rc = math.inf if spec["rc"] is None else spec["rc"]
    if not (isinstance(rc, float) and rc > 0):
        raise ValueError("rc must be a positive finite number or inf")
    if math.isfinite(rc) and rc <= 0:
        raise ValueError("rc must be a positive finite number or inf")
    s_min = _finite("s_min", spec["s_min"])
    s_max = _finite("s_max", spec["s_max"])
    _check_slip_window(s_min, s_max)
    n_points = _positive_int("n_points", spec["n_points"], minimum=1, maximum=5001)
    if n_points == 1 and s_min != s_max:
        raise ValueError("n_points=1 requires s_min == s_max")
    p_rated = None if spec["p_rated"] is None else _positive("p_rated", spec["p_rated"])
    s_rated_given = None if spec["s_rated"] is None else _finite("s_rated", spec["s_rated"])
    if s_rated_given is not None and (s_rated_given < -2.0 or s_rated_given > 3.0):
        raise ValueError("s_rated must lie in [-2, 3]")

    v_phase = v_line if connection == "d" else v_line / math.sqrt(3.0)
    n_sync = 120.0 * frequency / poles
    omega_sync = 2.0 * math.pi * n_sync / 60.0
    z_mag = _magnetizing(xm, rc)
    z1 = complex(r1, x1)
    v_th = v_phase * z_mag / (z1 + z_mag)
    z_th = z1 * z_mag / (z1 + z_mag)
    r_th = float(z_th.real)
    x_th = float(z_th.imag)
    machine = _Induction(
        v_phase=v_phase,
        connection=connection,
        r1=r1,
        x1=x1,
        r2=r2,
        x2=x2,
        xm=xm,
        rc=rc,
        n_sync=n_sync,
        omega_sync=omega_sync,
        v_th=v_th,
        r_th=r_th,
        x_th=x_th,
    )
    s_bd = _breakdown_slip(machine)
    t_bd = _breakdown_torque(machine, s_bd)
    t_start = _induction_point(machine, 1.0).torque_nm
    if s_rated_given is not None:
        s_rated = s_rated_given
    elif p_rated is not None:
        s_rated = _solve_induction_slip(machine, p_rated, s_bd)
    else:
        s_rated = math.nan
    rated = None if not math.isfinite(s_rated) else _induction_point(machine, s_rated)

    slip = np.linspace(s_min, s_max, n_points)
    slip = _insert_slip(slip, s_bd)
    points = [_induction_point(machine, float(value)) for value in slip]
    nan = math.nan
    return _pack_case(
        name=spec["name"],
        motor="induction",
        connection=connection,
        v=v_line,
        f=frequency,
        poles=float(poles),
        r1=r1,
        x1=x1,
        r2=r2,
        x2=x2,
        xm=xm,
        rc=rc,
        n_sync_rpm=n_sync,
        omega_sync_rad_s=omega_sync,
        v_phase=v_phase,
        v_th=abs(v_th),
        r_th=r_th,
        x_th=x_th,
        torque_start_nm=t_start,
        slip_breakdown=s_bd,
        speed_breakdown_rpm=(1.0 - s_bd) * n_sync,
        torque_breakdown_nm=t_bd,
        rated=rated,
        p_rated_w=nan if p_rated is None else p_rated,
        ra=nan,
        rf=nan,
        rs=nan,
        k_phi=nan,
        k_f=nan,
        i_field_a=nan,
        speed_noload_rpm=nan,
        torque_stall_nm=nan,
        i_stall_a=nan,
        i_min=nan,
        i_max=nan,
        s_min=s_min,
        s_max=s_max,
        n_points=n_points,
        points=points,
    )


def _build_dc_linear(spec: Mapping[str, object]) -> MotorCase:
    motor = str(spec["motor"])
    v = _positive("v", DEFAULT_DC_V if spec["v"] is None else spec["v"])
    n_points = _positive_int("n_points", spec["n_points"], minimum=2, maximum=5001)
    p_rated = None if spec["p_rated"] is None else _positive("p_rated", spec["p_rated"])
    t_rated_given = None if spec["t_rated"] is None else _positive("t_rated", spec["t_rated"])
    if motor == "dc_shunt":
        ra = _positive("ra", DEFAULT_RA_SHUNT if spec["ra"] is None else spec["ra"])
        rf = _positive("rf", DEFAULT_RF if spec["rf"] is None else spec["rf"])
        k_f = _positive("k_f", DEFAULT_K_F_SHUNT if spec["k_f"] is None else spec["k_f"])
        i_field = v / rf
        k_phi = k_f * i_field
    else:
        ra = _positive("ra", DEFAULT_RA_SEPARATE if spec["ra"] is None else spec["ra"])
        rf = math.nan
        k_f = math.nan
        i_field = math.nan
        k_phi = _positive("k_phi", DEFAULT_K_PHI if spec["k_phi"] is None else spec["k_phi"])
    i_stall = v / ra
    t_stall = k_phi * i_stall
    speed_noload = _rpm_from_omega(v / k_phi)
    if t_rated_given is not None:
        if t_rated_given > t_stall * (1.0 + 1e-12):
            raise ValueError("t_rated must be positive and at most the stall torque")
        t_rated = min(t_rated_given, t_stall)
    elif p_rated is not None:
        t_rated = _solve_linear_torque(v, ra, k_phi, p_rated, t_stall)
    else:
        t_rated = math.nan
    rated = None if not math.isfinite(t_rated) else _dc_linear_point(v, ra, k_phi, i_field, t_rated)
    torque = np.linspace(0.0, t_stall, n_points)
    points = [_dc_linear_point(v, ra, k_phi, i_field, float(value)) for value in torque]
    return _pack_case(
        name=spec["name"],
        motor=motor,
        connection="",
        v=v,
        f=math.nan,
        poles=math.nan,
        r1=math.nan,
        x1=math.nan,
        r2=math.nan,
        x2=math.nan,
        xm=math.nan,
        rc=math.nan,
        n_sync_rpm=math.nan,
        omega_sync_rad_s=math.nan,
        v_phase=math.nan,
        v_th=math.nan,
        r_th=math.nan,
        x_th=math.nan,
        torque_start_nm=math.nan,
        slip_breakdown=math.nan,
        speed_breakdown_rpm=math.nan,
        torque_breakdown_nm=math.nan,
        rated=rated,
        p_rated_w=math.nan if p_rated is None else p_rated,
        ra=ra,
        rf=rf,
        rs=math.nan,
        k_phi=k_phi,
        k_f=k_f,
        i_field_a=i_field,
        speed_noload_rpm=speed_noload,
        torque_stall_nm=t_stall,
        i_stall_a=i_stall,
        i_min=math.nan,
        i_max=math.nan,
        s_min=math.nan,
        s_max=math.nan,
        n_points=n_points,
        points=points,
    )


def _build_series(spec: Mapping[str, object]) -> MotorCase:
    v = _positive("v", DEFAULT_DC_V if spec["v"] is None else spec["v"])
    ra = _nonnegative("ra", DEFAULT_RA_SERIES if spec["ra"] is None else spec["ra"])
    rs = _nonnegative("rs", DEFAULT_RS if spec["rs"] is None else spec["rs"])
    k_f = _positive("k_f", DEFAULT_K_F_SERIES if spec["k_f"] is None else spec["k_f"])
    r_tot = ra + rs
    if r_tot <= 0:
        raise ValueError("ra + rs must be a positive finite number")
    n_points = _positive_int("n_points", spec["n_points"], minimum=2, maximum=5001)
    p_rated = None if spec["p_rated"] is None else _positive("p_rated", spec["p_rated"])
    t_rated_given = None if spec["t_rated"] is None else _positive("t_rated", spec["t_rated"])
    i_stall = v / r_tot
    t_stall = k_f * i_stall * i_stall
    i_min = 0.08 * i_stall if spec["i_min"] is None else _positive("i_min", spec["i_min"])
    i_max = 0.45 * i_stall if spec["i_max"] is None else _positive("i_max", spec["i_max"])
    if i_max <= i_min or i_max > i_stall * (1.0 + 1e-12):
        raise ValueError("i_max must be greater than i_min and at most the stall current")
    i_max = min(i_max, i_stall)
    if t_rated_given is not None:
        if t_rated_given > t_stall * (1.0 + 1e-12):
            raise ValueError("t_rated must be positive and at most the stall torque")
        t_rated = min(t_rated_given, t_stall)
    elif p_rated is not None:
        t_rated = _solve_series_torque(v, r_tot, k_f, p_rated)
    else:
        t_rated = math.nan
    rated = None if not math.isfinite(t_rated) else _series_point(v, r_tot, k_f, t_rated)
    current = np.linspace(i_min, i_max, n_points)
    torque = k_f * current * current
    points = [_series_point(v, r_tot, k_f, float(value)) for value in torque]
    return _pack_case(
        name=spec["name"],
        motor="dc_series",
        connection="",
        v=v,
        f=math.nan,
        poles=math.nan,
        r1=math.nan,
        x1=math.nan,
        r2=math.nan,
        x2=math.nan,
        xm=math.nan,
        rc=math.nan,
        n_sync_rpm=math.nan,
        omega_sync_rad_s=math.nan,
        v_phase=math.nan,
        v_th=math.nan,
        r_th=math.nan,
        x_th=math.nan,
        torque_start_nm=math.nan,
        slip_breakdown=math.nan,
        speed_breakdown_rpm=math.nan,
        torque_breakdown_nm=math.nan,
        rated=rated,
        p_rated_w=math.nan if p_rated is None else p_rated,
        ra=ra,
        rf=math.nan,
        rs=rs,
        k_phi=math.nan,
        k_f=k_f,
        i_field_a=math.nan,
        speed_noload_rpm=math.inf,
        torque_stall_nm=t_stall,
        i_stall_a=i_stall,
        i_min=i_min,
        i_max=i_max,
        s_min=math.nan,
        s_max=math.nan,
        n_points=n_points,
        points=points,
    )


@dataclass
class _Induction:
    v_phase: float
    connection: str
    r1: float
    x1: float
    r2: float
    x2: float
    xm: float
    rc: float
    n_sync: float
    omega_sync: float
    v_th: complex
    r_th: float
    x_th: float


@dataclass
class _Point:
    slip: float
    speed_rpm: float
    speed_rad_s: float
    torque_nm: float
    i_line_a: float
    i_phase_a: float
    i2_a: float
    power_in_w: float
    power_mech_w: float
    power_factor: float
    efficiency: float


def _magnetizing(xm: float, rc: float) -> complex:
    if not math.isfinite(rc):
        return complex(0.0, xm)
    return 1.0 / (1.0 / rc + 1.0 / complex(0.0, xm))


def _induction_point(machine: _Induction, slip: float) -> _Point:
    z1 = complex(machine.r1, machine.x1)
    z_mag = _magnetizing(machine.xm, machine.rc)
    if abs(slip) <= SLIP_OPEN:
        z_in = z1 + z_mag
        i1 = machine.v_phase / z_in
        e_gap = i1 * z_mag
        i2 = 0j
        p_ag = 0.0
        slip_used = 0.0
    else:
        z2 = complex(machine.r2 / slip, machine.x2)
        z_f = 1.0 / (1.0 / z_mag + 1.0 / z2)
        z_in = z1 + z_f
        i1 = machine.v_phase / z_in
        e_gap = i1 * z_f
        i2 = e_gap / z2
        p_ag = 3.0 * (abs(i2) ** 2) * machine.r2 / slip
        slip_used = slip
    p_in = 3.0 * machine.v_phase * float(i1.real)
    torque = p_ag / machine.omega_sync
    p_mech = (1.0 - slip_used) * p_ag
    i_phase = abs(i1)
    i_line = i_phase if machine.connection == "y" else math.sqrt(3.0) * i_phase
    apparent = 3.0 * machine.v_phase * i_phase
    power_factor = p_in / apparent if apparent > 0.0 else math.nan
    if 0.0 < slip_used < 1.0 and p_in > 0.0 and p_mech > 0.0:
        efficiency = p_mech / p_in
    else:
        efficiency = math.nan
    omega = (1.0 - slip_used) * machine.omega_sync
    return _Point(
        slip=slip_used,
        speed_rpm=(1.0 - slip_used) * machine.n_sync,
        speed_rad_s=omega,
        torque_nm=torque,
        i_line_a=i_line,
        i_phase_a=i_phase,
        i2_a=abs(i2),
        power_in_w=p_in,
        power_mech_w=p_mech,
        power_factor=power_factor,
        efficiency=efficiency,
    )


def _breakdown_slip(machine: _Induction) -> float:
    reactance = machine.x_th + machine.x2
    return machine.r2 / math.sqrt(machine.r_th * machine.r_th + reactance * reactance)


def _breakdown_torque(machine: _Induction, slip_breakdown: float) -> float:
    reactance = machine.x_th + machine.x2
    magnitude = math.sqrt(machine.r_th * machine.r_th + reactance * reactance)
    denominator = machine.r_th + magnitude
    if denominator <= 0.0:
        raise ValueError("breakdown torque is undefined for these impedances")
    # slip_breakdown is returned so a caller can see the pair; T_bd does not use R2.
    _ = slip_breakdown
    return (3.0 / (2.0 * machine.omega_sync)) * (abs(machine.v_th) ** 2) / denominator


def _solve_induction_slip(machine: _Induction, p_rated: float, slip_breakdown: float) -> float:
    s_hi = min(slip_breakdown, 1.0)
    if s_hi <= RATED_SCAN_FLOOR:
        raise ValueError("breakdown slip is too small to solve for p_rated")
    s_lo = min(1e-6, s_hi * 1e-4)
    slips = [s_lo + (s_hi - s_lo) * index / (SCAN_POINTS - 1) for index in range(SCAN_POINTS)]
    powers = [_induction_point(machine, slip).power_mech_w for slip in slips]
    peak_index = max(range(SCAN_POINTS), key=lambda index: powers[index])
    peak = powers[peak_index]
    if p_rated > peak and (p_rated - peak) > max(1e-6, 1e-8 * max(peak, 1.0)):
        raise ValueError("p_rated is above the developed power in the stable region")
    if powers[0] >= p_rated:
        lo = 0.0
        hi = slips[0]
    else:
        found = None
        for index in range(peak_index):
            if powers[index] <= p_rated <= powers[index + 1]:
                found = index
                break
        if found is None:
            if abs(peak - p_rated) <= max(1e-6, 1e-7 * p_rated):
                return slips[peak_index]
            raise ValueError("p_rated is above the developed power in the stable region")
        lo = slips[found]
        hi = slips[found + 1]
    for _ in range(BISECT_STEPS):
        mid = 0.5 * (lo + hi)
        if _induction_point(machine, mid).power_mech_w < p_rated:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _insert_slip(slip: np.ndarray, extra: float) -> np.ndarray:
    if slip.size == 0 or extra <= float(slip[0]) or extra >= float(slip[-1]):
        return np.ascontiguousarray(slip, dtype=float)
    if float(np.min(np.abs(slip - extra))) <= 1e-12 * max(1.0, abs(extra)):
        return np.ascontiguousarray(slip, dtype=float)
    return np.ascontiguousarray(np.sort(np.append(slip, extra)), dtype=float)


def _dc_linear_point(
    v: float,
    ra: float,
    k_phi: float,
    i_field: float,
    torque: float,
) -> _Point:
    i_armature = torque / k_phi
    omega = (v - i_armature * ra) / k_phi
    if abs(omega) <= 1e-12 * max(abs(v / k_phi), 1.0):
        omega = 0.0
    p_mech = torque * omega
    if math.isfinite(i_field):
        i_line = i_armature + i_field
    else:
        i_line = i_armature
    p_in = v * i_line
    if p_mech > 0.0 and p_in > 0.0:
        efficiency = p_mech / p_in
    elif p_in > 0.0 and p_mech == 0.0:
        efficiency = 0.0
    else:
        efficiency = math.nan
    return _Point(
        slip=math.nan,
        speed_rpm=_rpm_from_omega(omega),
        speed_rad_s=omega,
        torque_nm=torque,
        i_line_a=i_line,
        i_phase_a=i_armature,
        i2_a=math.nan,
        power_in_w=p_in,
        power_mech_w=p_mech,
        power_factor=math.nan,
        efficiency=efficiency,
    )


def _solve_linear_torque(v: float, ra: float, k_phi: float, p_rated: float, t_stall: float) -> float:
    omega0 = v / k_phi
    slope = ra / (k_phi * k_phi)
    # P = omega0*T - slope*T^2. The high-speed root is the smaller torque.
    discriminant = omega0 * omega0 - 4.0 * slope * p_rated
    if discriminant < -1e-9 * omega0 * omega0:
        raise ValueError("p_rated is above the maximum developed power")
    discriminant = max(discriminant, 0.0)
    torque = (omega0 - math.sqrt(discriminant)) / (2.0 * slope)
    if torque < 0.0 or torque > t_stall * (1.0 + 1e-9):
        raise ValueError("p_rated is above the maximum developed power")
    return min(max(torque, 0.0), t_stall)


def _series_point(v: float, r_tot: float, k_f: float, torque: float) -> _Point:
    if torque <= 0.0:
        raise ValueError("series torque must be positive")
    current = math.sqrt(torque / k_f)
    omega = v / (k_f * current) - r_tot / k_f
    p_mech = torque * omega
    p_in = v * current
    if p_mech > 0.0 and p_in > 0.0:
        efficiency = p_mech / p_in
    elif p_in > 0.0 and abs(p_mech) <= 1e-9 * p_in:
        efficiency = 0.0
    else:
        efficiency = math.nan
    return _Point(
        slip=math.nan,
        speed_rpm=_rpm_from_omega(omega),
        speed_rad_s=omega,
        torque_nm=torque,
        i_line_a=current,
        i_phase_a=current,
        i2_a=math.nan,
        power_in_w=p_in,
        power_mech_w=p_mech,
        power_factor=math.nan,
        efficiency=efficiency,
    )


def _solve_series_torque(v: float, r_tot: float, k_f: float, p_rated: float) -> float:
    # a*u^2 + b*u + p_rated = 0, with u = sqrt(T) and a = Rtot/k_f.
    a = r_tot / k_f
    b = -v / math.sqrt(k_f)
    discriminant = b * b - 4.0 * a * p_rated
    if discriminant < -1e-9 * b * b:
        raise ValueError("p_rated is above the maximum developed power")
    discriminant = max(discriminant, 0.0)
    sqrt_disc = math.sqrt(discriminant)
    # Smaller positive root: high-speed operating point.
    u = (-b - sqrt_disc) / (2.0 * a)
    if u <= 0.0:
        raise ValueError("p_rated is above the maximum developed power")
    return u * u


def _rpm_from_omega(omega: float) -> float:
    return omega * 60.0 / (2.0 * math.pi)


def _pack_case(
    *,
    name: object,
    motor: str,
    connection: str,
    v: float,
    f: float,
    poles: float,
    r1: float,
    x1: float,
    r2: float,
    x2: float,
    xm: float,
    rc: float,
    n_sync_rpm: float,
    omega_sync_rad_s: float,
    v_phase: float,
    v_th: float,
    r_th: float,
    x_th: float,
    torque_start_nm: float,
    slip_breakdown: float,
    speed_breakdown_rpm: float,
    torque_breakdown_nm: float,
    rated: _Point | None,
    p_rated_w: float,
    ra: float,
    rf: float,
    rs: float,
    k_phi: float,
    k_f: float,
    i_field_a: float,
    speed_noload_rpm: float,
    torque_stall_nm: float,
    i_stall_a: float,
    i_min: float,
    i_max: float,
    s_min: float,
    s_max: float,
    n_points: int,
    points: Sequence[_Point],
) -> MotorCase:
    def column(attr: str) -> np.ndarray:
        return np.ascontiguousarray([getattr(point, attr) for point in points], dtype=float)

    if rated is None:
        s_rated = math.nan
        speed_rated = math.nan
        torque_rated = math.nan
        i_line_rated = math.nan
        i2_rated = math.nan
        p_mech_rated = math.nan
        p_in_rated = math.nan
        pf_rated = math.nan
        eta_rated = math.nan
    else:
        s_rated = rated.slip
        speed_rated = rated.speed_rpm
        torque_rated = rated.torque_nm
        i_line_rated = rated.i_line_a
        i2_rated = rated.i2_a
        p_mech_rated = rated.power_mech_w
        p_in_rated = rated.power_in_w
        pf_rated = rated.power_factor
        eta_rated = rated.efficiency
    return MotorCase(
        name=_text(name),
        motor=motor,
        connection=connection,
        v=v,
        f=f,
        poles=poles,
        r1=r1,
        x1=x1,
        r2=r2,
        x2=x2,
        xm=xm,
        rc=rc,
        n_sync_rpm=n_sync_rpm,
        omega_sync_rad_s=omega_sync_rad_s,
        v_phase=v_phase,
        v_th=v_th,
        r_th=r_th,
        x_th=x_th,
        torque_start_nm=torque_start_nm,
        slip_breakdown=slip_breakdown,
        speed_breakdown_rpm=speed_breakdown_rpm,
        torque_breakdown_nm=torque_breakdown_nm,
        s_rated=s_rated,
        speed_rated_rpm=speed_rated,
        torque_rated_nm=torque_rated,
        i_line_rated_a=i_line_rated,
        i2_rated_a=i2_rated,
        power_mech_rated_w=p_mech_rated,
        power_in_rated_w=p_in_rated,
        pf_rated=pf_rated,
        efficiency_rated=eta_rated,
        p_rated_w=p_rated_w,
        ra=ra,
        rf=rf,
        rs=rs,
        k_phi=k_phi,
        k_f=k_f,
        i_field_a=i_field_a,
        speed_noload_rpm=speed_noload_rpm,
        torque_stall_nm=torque_stall_nm,
        i_stall_a=i_stall_a,
        i_min=i_min,
        i_max=i_max,
        s_min=s_min,
        s_max=s_max,
        n_points=n_points,
        n_samples=len(points),
        slip=column("slip"),
        speed_rpm=column("speed_rpm"),
        speed_rad_s=column("speed_rad_s"),
        torque_nm=column("torque_nm"),
        i_line_a=column("i_line_a"),
        i_phase_a=column("i_phase_a"),
        i2_a=column("i2_a"),
        power_in_w=column("power_in_w"),
        power_mech_w=column("power_mech_w"),
        power_factor=column("power_factor"),
        efficiency=column("efficiency"),
    )


def _check_slip_window(s_min: float, s_max: float) -> None:
    if s_min < -2.0 or s_max > 3.0:
        raise ValueError("s_min and s_max must lie in [-2, 3]")
    if s_max < s_min:
        raise ValueError("s_max must be greater than or equal to s_min")


def _resolve_specs(
    source: object,
    *,
    csv_path: str | Path | None,
    name: object,
    motor: object,
    v: object,
    f: object,
    poles: object,
    connection: object,
    r1: object,
    x1: object,
    r2: object,
    x2: object,
    xm: object,
    rc: object,
    p_rated: object,
    s_rated: object,
    t_rated: object,
    ra: object,
    rf: object,
    rs: object,
    k_phi: object,
    k_f: object,
    i_min: object,
    i_max: object,
    s_min: object,
    s_max: object,
    n_points: object,
) -> list[dict[str, object]]:
    defaults: dict[str, object] = {
        "name": name,
        "motor": motor,
        "v": v,
        "f": f,
        "poles": poles,
        "connection": connection,
        "r1": r1,
        "x1": x1,
        "r2": r2,
        "x2": x2,
        "xm": xm,
        "rc": rc,
        "p_rated": p_rated,
        "s_rated": s_rated,
        "t_rated": t_rated,
        "ra": ra,
        "rf": rf,
        "rs": rs,
        "k_phi": k_phi,
        "k_f": k_f,
        "i_min": i_min,
        "i_max": i_max,
        "s_min": s_min,
        "s_max": s_max,
        "n_points": n_points,
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
        return [defaults]
    rows = _read_csv_rows(Path(path_text))
    selected = _select_rows(rows, _text(name))
    specs: list[dict[str, object]] = []
    for row in selected:
        merged = dict(defaults)
        for key, aliases in _CSV_ALIASES.items():
            raw = _lookup(row, *aliases)
            if not _blank(raw):
                merged[key] = raw
        if _blank(merged["name"]):
            merged["name"] = ""
        specs.append(merged)
    return specs


def _select_rows(rows: Sequence[Mapping[str, str]], name: str) -> list[Mapping[str, str]]:
    if name == "":
        return list(rows)
    matches = [row for row in rows if _text(_lookup(row, "name")) == name]
    if not matches:
        raise ValueError(f"name {name!r} was not found in the CSV")
    if len(matches) > 1:
        raise ValueError(f"name {name!r} appears more than once in the CSV")
    return matches


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


def _normalize_motor(value: object) -> str:
    key = _norm_key(value)
    if key in {"induction", "im", "async", "asynchronous", "感应", "异步"}:
        return "induction"
    if key in {"dcshunt", "shunt", "并励"}:
        return "dc_shunt"
    if key in {"dcseparate", "separate", "separately", "sep", "他励"}:
        return "dc_separate"
    if key in {"dcseries", "series", "串励"}:
        return "dc_series"
    raise ValueError("motor must be 'induction', 'dc_shunt', 'dc_separate', or 'dc_series'")


def _normalize_connection(value: object) -> str:
    key = _norm_key(value)
    if key in {"y", "wye", "star", "星形"}:
        return "y"
    if key in {"d", "delta", "三角形"}:
        return "d"
    raise ValueError("connection must be 'y' (star) or 'd' (delta)")


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


def _optional_number(label: str, value: object) -> float | None:
    if _blank(value):
        return None
    if isinstance(value, str) and value.strip().lower() in {"inf", "+inf", "infinity"}:
        return math.inf
    return _finite(label, value)


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


def _positive_int(label: str, value: object, *, maximum: int, minimum: int = 1) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}")
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


def _csv_num(value: float) -> str:
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return f"{value:.12g}"


def _write_summary(path: Path, cases: Sequence[MotorCase]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_SUMMARY_FIELDS)
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "name": case.name,
                    "motor": case.motor,
                    "connection": case.connection,
                    "v": _csv_num(case.v),
                    "f": _csv_num(case.f),
                    "poles": _csv_num(case.poles),
                    "n_sync_rpm": _csv_num(case.n_sync_rpm),
                    "v_phase": _csv_num(case.v_phase),
                    "v_th": _csv_num(case.v_th),
                    "r_th": _csv_num(case.r_th),
                    "x_th": _csv_num(case.x_th),
                    "torque_start_nm": _csv_num(case.torque_start_nm),
                    "slip_breakdown": _csv_num(case.slip_breakdown),
                    "speed_breakdown_rpm": _csv_num(case.speed_breakdown_rpm),
                    "torque_breakdown_nm": _csv_num(case.torque_breakdown_nm),
                    "s_rated": _csv_num(case.s_rated),
                    "speed_rated_rpm": _csv_num(case.speed_rated_rpm),
                    "torque_rated_nm": _csv_num(case.torque_rated_nm),
                    "i_line_rated_a": _csv_num(case.i_line_rated_a),
                    "i2_rated_a": _csv_num(case.i2_rated_a),
                    "power_mech_rated_w": _csv_num(case.power_mech_rated_w),
                    "power_in_rated_w": _csv_num(case.power_in_rated_w),
                    "pf_rated": _csv_num(case.pf_rated),
                    "efficiency_rated": _csv_num(case.efficiency_rated),
                    "ra": _csv_num(case.ra),
                    "rf": _csv_num(case.rf),
                    "rs": _csv_num(case.rs),
                    "k_phi": _csv_num(case.k_phi),
                    "k_f": _csv_num(case.k_f),
                    "i_field_a": _csv_num(case.i_field_a),
                    "speed_noload_rpm": _csv_num(case.speed_noload_rpm),
                    "torque_stall_nm": _csv_num(case.torque_stall_nm),
                    "i_stall_a": _csv_num(case.i_stall_a),
                }
            )


def _panel_groups(cases: Sequence[MotorCase]) -> list[tuple[str, list[MotorCase]]]:
    groups: list[tuple[str, list[MotorCase]]] = []
    induction = [case for case in cases if case.motor == "induction"]
    linear = [case for case in cases if case.motor in {"dc_shunt", "dc_separate"}]
    series = [case for case in cases if case.motor == "dc_series"]
    if induction:
        groups.append(("Induction motor", induction))
    if linear:
        groups.append(("DC shunt / separately excited", linear))
    if series:
        groups.append(("DC series", series))
    return groups


def _case_label(case: MotorCase) -> str:
    if case.name:
        return case.name
    return case.motor


def _render_figure(cases: Sequence[MotorCase], output_png: str | None, show: bool) -> object | None:
    import matplotlib.pyplot as plt

    groups = _panel_groups(cases)
    height = {1: 5.4, 2: 8.6, 3: 12.2}[len(groups)]
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
        fig, axes = plt.subplots(len(groups), 1, figsize=(10.4, height), squeeze=False)
        for axis, (title, group) in zip(axes[:, 0], groups):
            speeds: list[float] = []
            torques: list[float] = []
            for index, case in enumerate(group):
                color = _PALETTE[index % len(_PALETTE)]
                axis.plot(
                    case.speed_rpm,
                    case.torque_nm,
                    color=color,
                    lw=1.7,
                    label=_case_label(case),
                )
                speeds.extend(float(value) for value in case.speed_rpm if math.isfinite(value))
                torques.extend(float(value) for value in case.torque_nm if math.isfinite(value))
                _draw_markers(axis, case, color, speeds, torques)
            _style_speed_axis(axis, title, speeds, torques)
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


def _draw_markers(
    axis: object,
    case: MotorCase,
    color: str,
    speeds: list[float],
    torques: list[float],
) -> None:
    if case.motor == "induction":
        if case.s_min <= 1.0 <= case.s_max and math.isfinite(case.torque_start_nm):
            axis.plot(
                [0.0],
                [case.torque_start_nm],
                marker="s",
                color=color,
                ms=6,
                ls="none",
            )
            speeds.append(0.0)
            torques.append(case.torque_start_nm)
        if case.s_min <= case.slip_breakdown <= case.s_max:
            axis.plot(
                [case.speed_breakdown_rpm],
                [case.torque_breakdown_nm],
                marker="v",
                color=color,
                ms=7,
                ls="none",
            )
            speeds.append(case.speed_breakdown_rpm)
            torques.append(case.torque_breakdown_nm)
    if math.isfinite(case.speed_rated_rpm) and math.isfinite(case.torque_rated_nm):
        axis.plot(
            [case.speed_rated_rpm],
            [case.torque_rated_nm],
            marker="o",
            color=color,
            ms=6,
            ls="none",
            markerfacecolor=color,
        )
        speeds.append(case.speed_rated_rpm)
        torques.append(case.torque_rated_nm)


def _style_speed_axis(axis: object, title: str, speeds: list[float], torques: list[float]) -> None:
    axis.set_title(title)
    axis.set_xlabel("Speed (rpm)")
    axis.set_ylabel("Torque (N·m)")
    axis.grid(True, color="#d0d0d0", linewidth=0.6)
    axis.legend(loc="upper right", frameon=True, edgecolor="#cccccc")
    if not speeds or not torques:
        return
    xmin = min(speeds)
    xmax = max(speeds)
    ymin = min(0.0, min(torques))
    ymax = max(torques)
    span = xmax - xmin if xmax > xmin else max(abs(xmax), 1.0)
    xpad = 0.04 * span
    ypad = 0.08 * (ymax - ymin if ymax > ymin else max(abs(ymax), 1.0))
    # Pin the axis at standstill when the curve actually reaches it. A series
    # sweep that stops well above zero speed keeps a tight window.
    if -1e-9 <= xmin <= 0.05 * max(xmax, 1.0):
        xmin = 0.0
        xpad_left = 0.0
    else:
        xpad_left = xpad
    axis.set_xlim(xmin - xpad_left, xmax + xpad)
    axis.set_ylim(ymin - (0.0 if ymin >= -1e-9 else ypad), ymax + ypad)
