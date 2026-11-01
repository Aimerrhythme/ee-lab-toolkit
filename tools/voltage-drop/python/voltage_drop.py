"""Approximate line and feeder voltage drop for a classroom lab.

The formulas match ``matlab/voltage_drop.m``.

Three-phase (default). ``R`` and ``X`` are one phase, ohms. ``V`` is the
line-to-line voltage used in the denominator, volts. ``I`` is the line
current, amperes. ``P`` and ``Q`` are three-phase watts and vars. Lagging
(inductive) reactive power is positive::

    dV = sqrt(3) * I * (R cosφ + X sinφ) = (P R + Q X) / V
    dV_percent = 100 * dV / V_nominal

Single-phase two-wire. ``R`` and ``X`` are one conductor; the loop uses both
directions::

    dV = 2 * I * (R cosφ + X sinφ) = (P * 2R + Q * 2X) / V

``voltage_basis='nominal'`` puts ``V_nominal`` in the denominator of every
section (the textbook approximation). ``voltage_basis='sending'`` uses that
section's sending-end voltage instead. Percent is always relative to
``V_nominal``.

``load_mode='tap'`` treats each row as the load at the receiving bus and
adds downstream taps onto upstream sections. ``load_mode='through'`` uses
the row power or current as the flow already in that section. Rows are
ordered from the source outward. A current specification is converted to
``P`` and ``Q`` at ``V_nominal``, so on the nominal basis the current
formula and the power formula are the same number.
"""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from pathlib import Path

DEFAULT_V_NOMINAL = 10_000.0

_KEY_ALIAS = {
    "name": "name",
    "section": "name",
    "id": "name",
    "frombus": "from_bus",
    "from": "from_bus",
    "busfrom": "from_bus",
    "tobus": "to_bus",
    "to": "to_bus",
    "busto": "to_bus",
    "lengthkm": "length_km",
    "length": "length_km",
    "km": "length_km",
    "lkm": "length_km",
    "rohmperkm": "r_ohm_per_km",
    "rperkm": "r_ohm_per_km",
    "rkm": "r_ohm_per_km",
    "xohmperkm": "x_ohm_per_km",
    "xperkm": "x_ohm_per_km",
    "xkm": "x_ohm_per_km",
    "rohm": "r_ohm",
    "r": "r_ohm",
    "resistance": "r_ohm",
    "xohm": "x_ohm",
    "x": "x_ohm",
    "reactance": "x_ohm",
    "pkw": "p_kw",
    "p": "p_kw",
    "qkvar": "q_kvar",
    "q": "q_kvar",
    "pw": "p_w",
    "qvar": "q_var",
    "ia": "i_a",
    "i": "i_a",
    "current": "i_a",
    "amp": "i_a",
    "amps": "i_a",
    "pf": "pf",
    "cosphi": "pf",
    "powerfactor": "pf",
}

_PARAM_NAMES = {
    "length_km",
    "r_ohm_per_km",
    "x_ohm_per_km",
    "r_ohm",
    "x_ohm",
    "i_a",
    "pf",
    "p_kw",
    "q_kvar",
    "p_w",
    "q_var",
    "name",
    "from_bus",
    "to_bus",
    "v_nominal",
    "v_source",
    "system",
    "load_mode",
    "voltage_basis",
    "csv_path",
    "output_csv",
    "output_png",
    "show",
}

_CSV_FIELDS = (
    "name",
    "from_bus",
    "to_bus",
    "length_km",
    "r_ohm",
    "x_ohm",
    "r_used_ohm",
    "x_used_ohm",
    "p_w",
    "q_var",
    "p_through_w",
    "q_through_var",
    "i_a",
    "pf",
    "cos_phi",
    "sin_phi",
    "delta_v",
    "delta_v_percent",
    "v_send",
    "v_recv",
)


@dataclass
class SectionResult:
    """One feeder section after the approximate drop is applied.

    ``r_ohm`` / ``x_ohm`` are one phase (three-phase) or one conductor
    (single-phase). ``r_used_ohm`` / ``x_used_ohm`` are what the formula
    multiplies: the same numbers, or twice those numbers on a two-wire
    circuit. ``p_w`` / ``q_var`` are the local tap. ``p_through_w`` /
    ``q_through_var`` are the flow used in ``(P R + Q X) / V``.
    """

    name: str
    from_bus: str
    to_bus: str
    length_km: float
    r_ohm: float
    x_ohm: float
    r_used_ohm: float
    x_used_ohm: float
    p_w: float
    q_var: float
    p_through_w: float
    q_through_var: float
    i_a: float
    pf: float
    cos_phi: float
    sin_phi: float
    delta_v: float
    delta_v_percent: float
    v_send: float
    v_recv: float


@dataclass
class VoltageDropResult:
    """Radial feeder result. ``summary`` is the same text MATLAB prints."""

    system: str
    load_mode: str
    voltage_basis: str
    v_nominal: float
    v_source: float
    sections: list[SectionResult]
    v_end: float
    delta_v_total: float
    delta_v_percent_total: float
    summary: str
    output_csv: str | None
    output_png: str | None
    fig: object | None = None


@dataclass
class _Draft:
    name: str
    from_bus: str
    to_bus: str
    length_km: float
    r_ohm: float
    x_ohm: float
    p_w: float
    q_var: float
    p_through_w: float = 0.0
    q_through_var: float = 0.0


def voltage_drop(
    source: str | Path | Mapping | Sequence | None = None,
    *,
    length_km: float | None = None,
    r_ohm_per_km: float | None = None,
    x_ohm_per_km: float | None = None,
    r_ohm: float | None = None,
    x_ohm: float | None = None,
    i_a: float | None = None,
    pf: float | None = None,
    p_kw: float | None = None,
    q_kvar: float | None = None,
    p_w: float | None = None,
    q_var: float | None = None,
    name: str = "",
    from_bus: str = "",
    to_bus: str = "",
    v_nominal: float = DEFAULT_V_NOMINAL,
    v_source: float | None = None,
    system: str = "three_phase",
    load_mode: str = "tap",
    voltage_basis: str = "nominal",
    csv_path: str | Path | None = None,
    output_csv: str | Path | None = None,
    output_png: str | Path | None = None,
    show: bool = False,
) -> VoltageDropResult:
    """Estimate the approximate voltage drop of one section or a radial feeder.

    Parameters use the same names as the MATLAB name-value arguments.
    ``source`` may be a CSV path, one mapping, or a sequence of mappings.
    Omit it and pass ``r_ohm`` / ``r_ohm_per_km`` together with a load to
    describe a single section.
    """

    system_name = _normalize_system(system)
    mode_name = _normalize_load_mode(load_mode)
    basis_name = _normalize_basis(voltage_basis)
    volts_nominal = _positive("v_nominal", v_nominal)
    if v_source is None:
        volts_source = volts_nominal
    else:
        volts_source = _positive("v_source", v_source)
    three_phase = system_name == "three_phase"

    raw_rows = _resolve_rows(
        source,
        csv_path=csv_path,
        direct={
            "length_km": length_km,
            "r_ohm_per_km": r_ohm_per_km,
            "x_ohm_per_km": x_ohm_per_km,
            "r_ohm": r_ohm,
            "x_ohm": x_ohm,
            "i_a": i_a,
            "pf": pf,
            "p_kw": p_kw,
            "q_kvar": q_kvar,
            "p_w": p_w,
            "q_var": q_var,
            "name": name,
            "from_bus": from_bus,
            "to_bus": to_bus,
        },
    )
    drafts = [
        _parse_section(raw, index, volts_nominal, three_phase)
        for index, raw in enumerate(raw_rows, start=1)
    ]
    _assign_buses(drafts)
    _accumulate(drafts, mode_name)
    sections = _solve(drafts, volts_nominal, volts_source, basis_name, three_phase)
    v_end = sections[-1].v_recv
    delta_total = volts_source - v_end
    percent_total = 100.0 * delta_total / volts_nominal

    csv_out = None if output_csv is None or str(output_csv).strip() == "" else str(output_csv)
    png_out = None if output_png is None or str(output_png).strip() == "" else str(output_png)
    result = VoltageDropResult(
        system=system_name,
        load_mode=mode_name,
        voltage_basis=basis_name,
        v_nominal=volts_nominal,
        v_source=volts_source,
        sections=sections,
        v_end=v_end,
        delta_v_total=delta_total,
        delta_v_percent_total=percent_total,
        summary="",
        output_csv=csv_out,
        output_png=png_out,
        fig=None,
    )
    result.summary = format_table(result)
    if csv_out is not None:
        _write_csv(Path(csv_out), sections)
    if png_out is not None or show:
        result.fig = _render_figure(result, png_out, bool(show))
    return result


def format_table(result: VoltageDropResult) -> str:
    """Format the feeder table. Python and MATLAB print this same text."""

    lines = [
        (
            f"system={result.system}  load_mode={result.load_mode}  "
            f"basis={result.voltage_basis}  "
            f"V_nominal={result.v_nominal:.4f} V  V_source={result.v_source:.4f} V"
        ),
        (
            f"{'section':<8} {'from':<6} {'to':<6} {'km':>7} {'R_ohm':>8} {'X_ohm':>8} "
            f"{'Ptap_kW':>8} {'Qtap_kvar':>9} {'Pthru_kW':>9} {'Qthru_kvar':>11} "
            f"{'I_A':>8} {'pf':>7} {'dV_V':>9} {'dV_pct':>8} "
            f"{'V_send':>10} {'V_recv':>10}"
        ),
    ]
    for row in result.sections:
        lines.append(
            f"{row.name:<8} {row.from_bus:<6} {row.to_bus:<6} {_km(row.length_km)} "
            f"{row.r_ohm:8.4f} {row.x_ohm:8.4f} "
            f"{row.p_w / 1000.0:8.3f} {row.q_var / 1000.0:9.3f} "
            f"{row.p_through_w / 1000.0:9.3f} {row.q_through_var / 1000.0:11.3f} "
            f"{row.i_a:8.3f} {row.pf:7.4f} {row.delta_v:9.4f} {row.delta_v_percent:8.4f} "
            f"{row.v_send:10.4f} {row.v_recv:10.4f}"
        )
    lines.append(
        f"total drop={result.delta_v_total:.4f} V ({result.delta_v_percent_total:.4f} %)  "
        f"V_end={result.v_end:.4f} V"
    )
    return "\n".join(lines)


def format_single_line(result: VoltageDropResult) -> str:
    """One-line summary of a single-section call. The demo prints this."""

    if len(result.sections) != 1:
        raise ValueError("format_single_line expects one section")
    row = result.sections[0]
    return (
        "voltage-drop single: "
        f"dV={row.delta_v:.4f} V ({row.delta_v_percent:.4f} %) "
        f"I={row.i_a:.3f} A pf={row.pf:.4f} V_recv={row.v_recv:.4f} V"
    )


def _km(length_km: float) -> str:
    if not math.isfinite(length_km):
        return "      -"
    return f"{length_km:7.3f}"


def _positive(label: str, value: object) -> float:
    number = _finite(label, value)
    if number <= 0.0:
        raise ValueError(f"{label} must be a positive finite number")
    return number


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


def _optional_number(label: str, value: object) -> float | None:
    if _blank(value):
        return None
    return _finite(label, value)


def _blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _text(value: object, default: str = "") -> str:
    if _blank(value):
        return default
    return str(value).strip()


def _norm_key(key: object) -> str:
    return re.sub(r"[\s_\-]", "", str(key).strip().lower())


def _normalize_system(system: object) -> str:
    key = _norm_key(system)
    if key in {"threephase", "3phase", "3ph"}:
        return "three_phase"
    if key in {"singlephase", "1phase", "1ph"}:
        return "single_phase"
    raise ValueError("system must be 'three_phase' or 'single_phase'")


def _normalize_load_mode(load_mode: object) -> str:
    key = _norm_key(load_mode)
    if key in {"tap", "bus", "load", "tapped"}:
        return "tap"
    if key in {"through", "flow", "section", "series"}:
        return "through"
    raise ValueError("load_mode must be 'tap' or 'through'")


def _normalize_basis(voltage_basis: object) -> str:
    key = _norm_key(voltage_basis)
    if key in {"nominal", "vn", "rated", "un"}:
        return "nominal"
    if key in {"sending", "send", "actual", "upstream"}:
        return "sending"
    raise ValueError("voltage_basis must be 'nominal' or 'sending'")


def _has_direct(direct: Mapping[str, object]) -> bool:
    for value in direct.values():
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        return True
    return False


def _resolve_rows(
    source: object,
    *,
    csv_path: str | Path | None,
    direct: Mapping[str, object],
) -> list[dict[str, object]]:
    csv_text = None if csv_path is None or str(csv_path).strip() == "" else str(csv_path)
    has_direct = _has_direct(direct)
    mappings: list | None = None
    if source is None:
        pass
    elif isinstance(source, (str, Path)):
        text = str(source).strip()
        if text.lower() in _PARAM_NAMES:
            raise ValueError(
                f"{text!r} is a parameter name. Pass the CSV path as csv_path= or as the first argument"
            )
        if csv_text is not None:
            raise ValueError("pass a CSV path once, either positionally or as csv_path=")
        if has_direct:
            raise ValueError("pass a CSV path or one section's arguments, not both")
        csv_text = text
    elif isinstance(source, Mapping):
        if csv_text is not None or has_direct:
            raise ValueError(
                "pass a CSV path, row mappings, or one section's arguments, not more than one"
            )
        mappings = [source]
    elif isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
        if csv_text is not None or has_direct:
            raise ValueError(
                "pass a CSV path, row mappings, or one section's arguments, not more than one"
            )
        if len(source) == 0:
            raise ValueError("section list is empty")
        mappings = list(source)
    else:
        raise TypeError("source must be a CSV path, a mapping, or a sequence of mappings")

    if csv_text is not None and has_direct:
        raise ValueError("pass a CSV path or one section's arguments, not both")
    if csv_text is not None:
        return [_canonicalize(row) for row in _read_csv_rows(Path(csv_text))]
    if mappings is not None:
        rows: list[dict[str, object]] = []
        for item in mappings:
            if not isinstance(item, Mapping):
                raise TypeError("each section must be a mapping")
            rows.append(_canonicalize(item))
        return rows
    if has_direct:
        return [_canonicalize(dict(direct))]
    raise ValueError("pass a feeder CSV or one section (R/X and a load)")


def _canonicalize(raw: Mapping[str, object]) -> dict[str, object]:
    folded: dict[str, object] = {}
    for key, value in raw.items():
        if key is None:
            continue
        norm = _norm_key(key)
        if norm == "":
            continue
        canon = _KEY_ALIAS.get(norm)
        if canon is None:
            raise ValueError(f"unknown column {key!r}")
        if canon in folded and not _blank(folded[canon]) and not _blank(value):
            raise ValueError(f"duplicate column {canon}")
        if canon not in folded or not _blank(value):
            folded[canon] = value
    return folded


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


def _pf_parts(pf: float, label: str) -> tuple[float, float]:
    if pf < -1.0 or pf > 1.0:
        raise ValueError(f"{label}: pf must be between -1 and 1 (a fraction, not a percent)")
    cos_phi = abs(pf)
    sin_mag = math.sqrt(max(0.0, 1.0 - cos_phi * cos_phi))
    sin_phi = -sin_mag if pf < 0.0 else sin_mag
    return cos_phi, sin_phi


def _parse_section(raw: Mapping[str, object], index: int, v_nominal: float, three_phase: bool) -> _Draft:
    name = _text(raw.get("name"), "") or f"section{index}"
    label = name
    length_km, r_ohm, x_ohm = _impedance(raw, label)
    p_w, q_var = _load_pq(raw, v_nominal, three_phase, label)
    return _Draft(
        name=name,
        from_bus=_text(raw.get("from_bus"), ""),
        to_bus=_text(raw.get("to_bus"), ""),
        length_km=length_km,
        r_ohm=r_ohm,
        x_ohm=x_ohm,
        p_w=p_w,
        q_var=q_var,
    )


def _impedance(raw: Mapping[str, object], label: str) -> tuple[float, float, float]:
    length = _optional_number("length_km", raw.get("length_km"))
    if length is not None and length < 0.0:
        raise ValueError(f"{label}: length_km must be >= 0")
    r_total = _optional_number("r_ohm", raw.get("r_ohm"))
    x_total = _optional_number("x_ohm", raw.get("x_ohm"))
    r_km = _optional_number("r_ohm_per_km", raw.get("r_ohm_per_km"))
    x_km = _optional_number("x_ohm_per_km", raw.get("x_ohm_per_km"))
    has_total = r_total is not None or x_total is not None
    has_km = r_km is not None or x_km is not None
    if has_total and has_km:
        raise ValueError(f"{label}: pass total r_ohm/x_ohm or per-km values, not both")
    if has_total:
        r_ohm = 0.0 if r_total is None else r_total
        x_ohm = 0.0 if x_total is None else x_total
    elif has_km:
        if length is None:
            raise ValueError(f"{label}: length_km is required when r/x are given per km")
        r_ohm = 0.0 if r_km is None else r_km * length
        x_ohm = 0.0 if x_km is None else x_km * length
    else:
        raise ValueError(f"{label}: resistance or reactance is required")
    if r_ohm < 0.0:
        raise ValueError(f"{label}: resistance must be >= 0")
    length_out = math.nan if length is None else length
    return length_out, r_ohm, x_ohm


def _load_pq(
    raw: Mapping[str, object],
    v_nominal: float,
    three_phase: bool,
    label: str,
) -> tuple[float, float]:
    p_kw = _optional_number("p_kw", raw.get("p_kw"))
    q_kvar = _optional_number("q_kvar", raw.get("q_kvar"))
    p_watts = _optional_number("p_w", raw.get("p_w"))
    q_vars = _optional_number("q_var", raw.get("q_var"))
    i_a = _optional_number("i_a", raw.get("i_a"))
    pf = _optional_number("pf", raw.get("pf"))
    has_p = p_kw is not None or p_watts is not None
    has_q = q_kvar is not None or q_vars is not None
    if has_p and i_a is not None:
        raise ValueError(f"{label}: pass P/Q or I/pf, not both")
    if p_kw is not None and p_watts is not None:
        raise ValueError(f"{label}: pass p_kw or p_w, not both")
    if q_kvar is not None and q_vars is not None:
        raise ValueError(f"{label}: pass q_kvar or q_var, not both")
    if i_a is not None:
        if i_a < 0.0:
            raise ValueError(f"{label}: i_a must be >= 0")
        cos_phi, sin_phi = _pf_parts(1.0 if pf is None else pf, label)
        scale = math.sqrt(3.0) if three_phase else 1.0
        return scale * v_nominal * i_a * cos_phi, scale * v_nominal * i_a * sin_phi
    if not has_p and not has_q:
        raise ValueError(f"{label}: a load is required (p_kw/q_kvar or i_a/pf)")
    if p_kw is not None:
        active = p_kw * 1000.0
    elif p_watts is not None:
        active = p_watts
    else:
        active = 0.0
    if has_q:
        if pf is not None:
            raise ValueError(f"{label}: pass q or pf, not both")
        reactive = q_kvar * 1000.0 if q_kvar is not None else float(q_vars)
        return active, reactive
    cos_phi, sin_phi = _pf_parts(1.0 if pf is None else pf, label)
    if cos_phi == 0.0:
        raise ValueError(f"{label}: pf is 0; pass q_kvar for a pure reactive load")
    return active, active * sin_phi / cos_phi


def _assign_buses(rows: list[_Draft]) -> None:
    for index, row in enumerate(rows):
        if row.to_bus == "":
            row.to_bus = f"B{index + 1}"
    for index, row in enumerate(rows):
        if row.from_bus == "":
            row.from_bus = "source" if index == 0 else rows[index - 1].to_bus


def _accumulate(rows: list[_Draft], load_mode: str) -> None:
    if load_mode == "through":
        for row in rows:
            row.p_through_w = row.p_w
            row.q_through_var = row.q_var
        return
    active = 0.0
    reactive = 0.0
    for row in reversed(rows):
        active += row.p_w
        reactive += row.q_var
        row.p_through_w = active
        row.q_through_var = reactive


def _signed_pf(active: float, reactive: float, apparent: float) -> tuple[float, float, float]:
    if apparent == 0.0:
        return 1.0, 1.0, 0.0
    cos_phi = active / apparent
    sin_phi = reactive / apparent
    if reactive < 0.0:
        pf = -abs(cos_phi)
    elif reactive > 0.0:
        pf = abs(cos_phi)
    else:
        pf = cos_phi
    return pf, cos_phi, sin_phi


def _solve(
    rows: list[_Draft],
    v_nominal: float,
    v_source: float,
    voltage_basis: str,
    three_phase: bool,
) -> list[SectionResult]:
    phase = math.sqrt(3.0) if three_phase else 1.0
    loop = 1.0 if three_phase else 2.0
    v_send = v_source
    solved: list[SectionResult] = []
    for row in rows:
        v_formula = v_nominal if voltage_basis == "nominal" else v_send
        if not v_formula > 0.0:
            raise ValueError(
                f"{row.name}: sending voltage is not positive; "
                "the approximate drop exceeds the upstream voltage"
            )
        r_used = row.r_ohm * loop
        x_used = row.x_ohm * loop
        delta = (row.p_through_w * r_used + row.q_through_var * x_used) / v_formula
        apparent = math.hypot(row.p_through_w, row.q_through_var)
        if apparent == 0.0:
            current = 0.0
            pf, cos_phi, sin_phi = 1.0, 1.0, 0.0
        else:
            current = apparent / (phase * v_formula)
            pf, cos_phi, sin_phi = _signed_pf(row.p_through_w, row.q_through_var, apparent)
        v_recv = v_send - delta
        solved.append(
            SectionResult(
                name=row.name,
                from_bus=row.from_bus,
                to_bus=row.to_bus,
                length_km=row.length_km,
                r_ohm=row.r_ohm,
                x_ohm=row.x_ohm,
                r_used_ohm=r_used,
                x_used_ohm=x_used,
                p_w=row.p_w,
                q_var=row.q_var,
                p_through_w=row.p_through_w,
                q_through_var=row.q_through_var,
                i_a=current,
                pf=pf,
                cos_phi=cos_phi,
                sin_phi=sin_phi,
                delta_v=delta,
                delta_v_percent=100.0 * delta / v_nominal,
                v_send=v_send,
                v_recv=v_recv,
            )
        )
        v_send = v_recv
    return solved


def _csv_number(value: float) -> str:
    if not math.isfinite(value):
        return ""
    return f"{value:.12g}"


def _write_csv(path: Path, rows: Sequence[SectionResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "name": row.name,
                    "from_bus": row.from_bus,
                    "to_bus": row.to_bus,
                    "length_km": _csv_number(row.length_km),
                    "r_ohm": _csv_number(row.r_ohm),
                    "x_ohm": _csv_number(row.x_ohm),
                    "r_used_ohm": _csv_number(row.r_used_ohm),
                    "x_used_ohm": _csv_number(row.x_used_ohm),
                    "p_w": _csv_number(row.p_w),
                    "q_var": _csv_number(row.q_var),
                    "p_through_w": _csv_number(row.p_through_w),
                    "q_through_var": _csv_number(row.q_through_var),
                    "i_a": _csv_number(row.i_a),
                    "pf": _csv_number(row.pf),
                    "cos_phi": _csv_number(row.cos_phi),
                    "sin_phi": _csv_number(row.sin_phi),
                    "delta_v": _csv_number(row.delta_v),
                    "delta_v_percent": _csv_number(row.delta_v_percent),
                    "v_send": _csv_number(row.v_send),
                    "v_recv": _csv_number(row.v_recv),
                }
            )


def _render_figure(result: VoltageDropResult, output_png: str | None, show: bool) -> object | None:
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
    lengths = [row.length_km for row in result.sections]
    if all(math.isfinite(item) for item in lengths):
        xs = [0.0]
        distance = 0.0
        for length in lengths:
            distance += length
            xs.append(distance)
        xlabel = "Distance from source (km)"
    else:
        xs = [float(index) for index in range(len(result.sections) + 1)]
        xlabel = "Bus index from source"
    volts = [result.v_source, *[row.v_recv for row in result.sections]]
    labels = [result.sections[0].from_bus, *[row.to_bus for row in result.sections]]
    names = [row.name for row in result.sections]
    drops = [row.delta_v_percent for row in result.sections]
    colors = ["#1f4e79" if item >= 0.0 else "#117a65" for item in drops]
    with plt.rc_context(style):
        fig, axes = plt.subplots(2, 1, figsize=(10.2, 7.4))
        profile = axes[0]
        profile.plot(xs, volts, color="#1f4e79", marker="o", linewidth=2.0, label="bus voltage")
        profile.axhline(
            result.v_nominal,
            color="#c0392b",
            linestyle="--",
            linewidth=1.0,
            label="nominal",
        )
        for x_pos, y_pos, bus_name in zip(xs, volts, labels):
            profile.annotate(
                bus_name,
                (x_pos, y_pos),
                textcoords="offset points",
                xytext=(0, 7),
                ha="center",
                fontsize=9,
                color="#333333",
            )
        low = min([*volts, result.v_nominal])
        high = max([*volts, result.v_nominal])
        pad = max((high - low) * 0.22, abs(result.v_nominal) * 0.004, 1.0)
        profile.set_ylim(low - pad * 0.35, high + pad)
        profile.set_xlabel(xlabel)
        profile.set_ylabel("Voltage (V)")
        profile.set_title("Feeder voltage profile")
        profile.grid(True, color="#d0d0d0", linewidth=0.6)
        profile.legend(loc="best", frameon=True, edgecolor="#cccccc")
        bars = axes[1]
        bars.bar(names, drops, color=colors, width=0.72, zorder=2)
        bars.axhline(0.0, color="#666666", linewidth=0.8, zorder=1)
        bars.set_xlabel("Section")
        bars.set_ylabel("Voltage drop (%)")
        bars.set_title("Section voltage drop vs nominal")
        bars.grid(True, axis="y", color="#d0d0d0", linewidth=0.6)
        bars.set_axisbelow(True)
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
