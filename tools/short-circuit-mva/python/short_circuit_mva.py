"""Short-circuit MVA and impedance calculator for a classroom lab.

The formulas match ``matlab/short_circuit_mva.m``.

Three-phase (default). ``V`` is the line-to-line study voltage. ``S`` is the
three-phase short-circuit capacity. ``I`` is the bolted three-phase fault
current. ``Z`` is the per-phase equivalent impedance at that voltage::

    S = sqrt(3) * V * I = V^2 / |Z|
    I = S / (sqrt(3) * V)
    |Z| = V^2 / S
    Z_pu = S_base / S = |Z| / Z_base
    Z_base = V^2 / S_base

Single-phase drops the ``sqrt(3)`` in the current. ``|Z| = V^2 / S`` is
unchanged.

A transformer impedance given on its own rating becomes a short-circuit
capacity by ``S = S_rated / z_pu`` (``z_percent`` is ``100 * z_pu``, so 8
means 8 percent, not 0.08).

Stages fold left to right by the magnitude MVA method. The first row is the
seed. ``series`` uses ``1/S_eq = 1/S_run + 1/S_next``. ``parallel`` uses
``S_eq = S_run + S_next``. Ohmic ``R`` and ``X`` are interpreted at ``v_kv``;
this tool does not refer them across a winding.

When ``x_over_r`` is omitted the element is treated as pure +jX, which is
the usual MVA-method assumption. ``R`` and ``X`` are also combined as
phasors. ``S_complex = V^2 / |Z_phasor|``. That value matches the MVA method
when every element has the same X/R.
"""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from pathlib import Path

DEFAULT_V_KV = 10.0
DEFAULT_S_BASE_MVA = 100.0

_KEY_ALIAS = {
    "name": "name",
    "element": "name",
    "id": "name",
    "kind": "kind",
    "type": "kind",
    "combine": "combine",
    "connection": "combine",
    "smva": "s_mva",
    "s": "s_mva",
    "ssc": "s_mva",
    "sscmva": "s_mva",
    "mva": "s_mva",
    "sva": "s_va",
    "ika": "i_ka",
    "ka": "i_ka",
    "currentka": "i_ka",
    "ia": "i_a",
    "i": "i_a",
    "current": "i_a",
    "amp": "i_a",
    "amps": "i_a",
    "zohm": "z_ohm",
    "z": "z_ohm",
    "impedance": "z_ohm",
    "rohm": "r_ohm",
    "r": "r_ohm",
    "resistance": "r_ohm",
    "xohm": "x_ohm",
    "x": "x_ohm",
    "reactance": "x_ohm",
    "zpu": "z_pu",
    "pu": "z_pu",
    "perunit": "z_pu",
    "zpercent": "z_percent",
    "zpct": "z_percent",
    "uk": "z_percent",
    "ukpercent": "z_percent",
    "sratedmva": "s_rated_mva",
    "srated": "s_rated_mva",
    "sn": "s_rated_mva",
    "snmva": "s_rated_mva",
    "ratingmva": "s_rated_mva",
    "xoverr": "x_over_r",
    "xr": "x_over_r",
}

# (formula group, label stored on the result)
_KIND_ALIAS = {
    "source": ("source", "source"),
    "mva": ("source", "source"),
    "grid": ("source", "source"),
    "utility": ("source", "source"),
    "current": ("current", "current"),
    "impedance": ("impedance", "impedance"),
    "line": ("impedance", "line"),
    "cable": ("impedance", "line"),
    "feeder": ("impedance", "line"),
    "transformer": ("transformer", "transformer"),
    "tx": ("transformer", "transformer"),
    "trafo": ("transformer", "transformer"),
    "pu": ("pu", "pu"),
    "perunit": ("pu", "pu"),
}

_PARAM_NAMES = {
    "name",
    "kind",
    "combine",
    "s_mva",
    "s_va",
    "i_ka",
    "i_a",
    "z_ohm",
    "r_ohm",
    "x_ohm",
    "z_pu",
    "z_percent",
    "s_rated_mva",
    "x_over_r",
    "v_kv",
    "v_v",
    "s_base_mva",
    "system",
    "csv_path",
    "output_csv",
    "output_png",
    "show",
}

_CSV_FIELDS = (
    "name",
    "kind",
    "combine",
    "s_mva",
    "s_va",
    "z_ohm",
    "r_ohm",
    "x_ohm",
    "x_over_r",
    "z_pu",
    "z_spec_pu",
    "s_rated_mva",
    "i_a",
    "i_ka",
    "s_running_mva",
    "z_running_ohm",
    "i_running_a",
    "i_running_ka",
)

_KIND_COLOR = {
    "source": "#1f4e79",
    "current": "#e67e22",
    "impedance": "#1a5276",
    "line": "#117a65",
    "transformer": "#c0392b",
    "pu": "#6c3483",
}


@dataclass
class ElementResult:
    """One stage and the running equivalent after it is folded in.

    ``s_mva`` is this stage alone. ``s_running_mva`` is the MVA-method
    equivalent of this stage and everything before it. ``z_ohm`` is
    ``V^2 / S`` at the study voltage. ``z_spec_pu`` is the per-unit value
    that was entered (transformer rating base, or ``s_base`` for a pu
    element); it is NaN when the stage was not specified that way.
    ``s_rated_mva`` is NaN unless the stage is a transformer.
    """

    name: str
    kind: str
    combine: str
    s_mva: float
    s_va: float
    z_ohm: float
    r_ohm: float
    x_ohm: float
    x_over_r: float
    z_pu: float
    z_spec_pu: float
    s_rated_mva: float
    i_a: float
    i_ka: float
    s_running_mva: float
    z_running_ohm: float
    i_running_a: float
    i_running_ka: float


@dataclass
class ShortCircuitResult:
    """MVA-method equivalent at ``v_kv``.

    ``s_mva``, ``i_ka``, ``z_ohm``, and ``z_pu`` come from the magnitude
    method. ``r_ohm``, ``x_ohm``, ``x_over_r``, ``angle_deg``,
    ``s_mva_complex``, and ``z_complex_ohm`` come from folding the same
    stages as phasors. ``summary`` is the text MATLAB prints.
    """

    method: str
    system: str
    v_v: float
    v_kv: float
    s_base_va: float
    s_base_mva: float
    z_base_ohm: float
    i_base_a: float
    i_base_ka: float
    elements: list[ElementResult]
    s_va: float
    s_mva: float
    i_a: float
    i_ka: float
    z_ohm: float
    z_pu: float
    r_ohm: float
    x_ohm: float
    x_over_r: float
    angle_deg: float
    z_complex_ohm: float
    s_va_complex: float
    s_mva_complex: float
    i_a_complex: float
    i_ka_complex: float
    summary: str
    output_csv: str | None
    output_png: str | None
    fig: object | None = None


@dataclass
class _Draft:
    name: str
    kind: str
    combine: str
    s_mva: float
    s_va: float
    r_ohm: float
    x_ohm: float
    z_spec_pu: float
    s_rated_mva: float


def short_circuit_mva(
    source: str | Path | Mapping | Sequence | None = None,
    *,
    name: str = "",
    kind: str = "",
    combine: str = "",
    s_mva: float | None = None,
    s_va: float | None = None,
    i_ka: float | None = None,
    i_a: float | None = None,
    z_ohm: float | None = None,
    r_ohm: float | None = None,
    x_ohm: float | None = None,
    z_pu: float | None = None,
    z_percent: float | None = None,
    s_rated_mva: float | None = None,
    x_over_r: float | None = None,
    v_kv: float | None = None,
    v_v: float | None = None,
    s_base_mva: float = DEFAULT_S_BASE_MVA,
    system: str = "three_phase",
    csv_path: str | Path | None = None,
    output_csv: str | Path | None = None,
    output_png: str | Path | None = None,
    show: bool = False,
) -> ShortCircuitResult:
    """Convert short-circuit MVA, current, and impedance, or fold several stages.

    Parameters use the same names as the MATLAB name-value arguments.
    ``source`` may be a CSV path, one mapping, or a sequence of mappings.
    Omit it and pass one specification (``s_mva``, ``i_ka``, ``z_ohm``,
    ``r_ohm`` / ``x_ohm``, a transformer rating, or ``z_pu``) to describe
    a single element. Ohmic values and the reported current are at ``v_kv``.
    """

    system_name = _normalize_system(system)
    volts, volts_kv = _study_voltage(v_kv, v_v)
    base_mva = _positive("s_base_mva", s_base_mva)
    phase = math.sqrt(3.0) if system_name == "three_phase" else 1.0
    base_va = base_mva * 1e6
    z_base = (volts * volts) / base_va
    i_base = base_va / (phase * volts)

    raw_rows = _resolve_rows(
        source,
        csv_path=csv_path,
        direct={
            "name": name,
            "kind": kind,
            "combine": combine,
            "s_mva": s_mva,
            "s_va": s_va,
            "i_ka": i_ka,
            "i_a": i_a,
            "z_ohm": z_ohm,
            "r_ohm": r_ohm,
            "x_ohm": x_ohm,
            "z_pu": z_pu,
            "z_percent": z_percent,
            "s_rated_mva": s_rated_mva,
            "x_over_r": x_over_r,
        },
    )
    drafts = [
        _parse_element(raw, index, volts, phase, base_mva)
        for index, raw in enumerate(raw_rows, start=1)
    ]
    elements, r_eq, x_eq = _fold(drafts, volts, phase, base_mva)
    final = elements[-1]
    z_complex = math.hypot(r_eq, x_eq)
    if not z_complex > 1e-15:
        raise ValueError(
            "equivalent phasor impedance is zero (the reactances cancel). "
            "The magnitude MVA method ignores this; keep X signs consistent or drop x_over_r"
        )
    s_complex = (volts * volts) / z_complex
    i_complex = s_complex / (phase * volts)

    csv_out = None if output_csv is None or str(output_csv).strip() == "" else str(output_csv)
    png_out = None if output_png is None or str(output_png).strip() == "" else str(output_png)
    result = ShortCircuitResult(
        method="mva",
        system=system_name,
        v_v=volts,
        v_kv=volts_kv,
        s_base_va=base_va,
        s_base_mva=base_mva,
        z_base_ohm=z_base,
        i_base_a=i_base,
        i_base_ka=i_base / 1000.0,
        elements=elements,
        s_va=final.s_running_mva * 1e6,
        s_mva=final.s_running_mva,
        i_a=final.i_running_a,
        i_ka=final.i_running_ka,
        z_ohm=final.z_running_ohm,
        z_pu=base_mva / final.s_running_mva,
        r_ohm=r_eq,
        x_ohm=x_eq,
        x_over_r=_xr_of(r_eq, x_eq),
        angle_deg=math.degrees(math.atan2(x_eq, r_eq)),
        z_complex_ohm=z_complex,
        s_va_complex=s_complex,
        s_mva_complex=s_complex / 1e6,
        i_a_complex=i_complex,
        i_ka_complex=i_complex / 1000.0,
        summary="",
        output_csv=csv_out,
        output_png=png_out,
        fig=None,
    )
    result.summary = format_table(result)
    if csv_out is not None:
        _write_csv(Path(csv_out), elements)
    if png_out is not None or show:
        result.fig = _render_figure(result, png_out, bool(show))
    return result


def format_table(result: ShortCircuitResult) -> str:
    """Format the stage table. Python and MATLAB print this same text."""

    lines = [
        (
            f"method={result.method}  system={result.system}  V={result.v_kv:.4f} kV  "
            f"S_base={result.s_base_mva:.4f} MVA  "
            f"Z_base={result.z_base_ohm:.4f} ohm  I_base={result.i_base_ka:.4f} kA"
        ),
        (
            f"{'element':<10} {'kind':<12} {'combine':<8} "
            f"{'S_MVA':>10} {'Z_ohm':>9} {'X/R':>8} "
            f"{'Srun_MVA':>10} {'Irun_kA':>9}"
        ),
    ]
    for row in result.elements:
        lines.append(
            f"{row.name:<10} {row.kind:<12} {row.combine:<8} "
            f"{row.s_mva:10.4f} {row.z_ohm:9.4f} {_fmt_xr(row.x_over_r):>8} "
            f"{row.s_running_mva:10.4f} {row.i_running_ka:9.4f}"
        )
    lines.append(
        f"S_sc={result.s_mva:.4f} MVA  I_sc={result.i_ka:.4f} kA  "
        f"Z={result.z_ohm:.4f} ohm  z_pu={result.z_pu:.4f} pu  "
        f"X/R={_fmt_xr(result.x_over_r)}  angle={result.angle_deg:.4f} deg  "
        f"S_complex={result.s_mva_complex:.4f} MVA  "
        f"Z_complex={result.z_complex_ohm:.4f} ohm"
    )
    return "\n".join(lines)


def format_single_line(result: ShortCircuitResult) -> str:
    """One-line summary of a single-element call. The demo prints this."""

    if len(result.elements) != 1:
        raise ValueError("format_single_line expects one element")
    return (
        "short-circuit-mva single: "
        f"S={result.s_mva:.4f} MVA  I={result.i_ka:.4f} kA  "
        f"Z={result.z_ohm:.4f} ohm  z_pu={result.z_pu:.4f} pu  "
        f"X/R={_fmt_xr(result.x_over_r)}"
    )


def _fmt_xr(value: float) -> str:
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "-inf" if value < 0.0 else "inf"
    return f"{value:.4f}"


def _study_voltage(v_kv: float | None, v_v: float | None) -> tuple[float, float]:
    if v_kv is not None and v_v is not None:
        raise ValueError("pass v_kv or v_v, not both")
    if v_v is not None:
        volts = _positive("v_v", v_v)
        return volts, volts / 1000.0
    if v_kv is None:
        v_kv = DEFAULT_V_KV
    volts_kv = _positive("v_kv", v_kv)
    return volts_kv * 1000.0, volts_kv


def _positive(label: str, value: object) -> float:
    number = _finite(label, value)
    if number <= 0.0:
        raise ValueError(f"{label} must be a positive finite number")
    return number


def _finite(label: str, value: object, *, allow_inf: bool = False) -> float:
    if isinstance(value, str):
        text = value.strip().lower()
        if allow_inf and text in {"inf", "+inf", "infinity", "+infinity"}:
            return math.inf
        if allow_inf and text in {"-inf", "-infinity"}:
            return -math.inf
        try:
            number = float(text)
        except ValueError as exc:
            raise ValueError(f"{label} must be a finite number") from exc
    elif isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite number")
    else:
        number = float(value)
    if allow_inf and math.isinf(number):
        return number
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _optional_number(label: str, value: object, *, allow_inf: bool = False) -> float | None:
    if _blank(value):
        return None
    return _finite(label, value, allow_inf=allow_inf)


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


def _normalize_combine(value: str, label: str) -> str:
    if value == "":
        return "series"
    key = _norm_key(value)
    if key in {"series", "serial", "cascade"}:
        return "series"
    if key in {"parallel", "shunt"}:
        return "parallel"
    raise ValueError(f"{label}: combine must be 'series' or 'parallel'")


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
            raise ValueError("pass a CSV path or one element's arguments, not both")
        csv_text = text
    elif isinstance(source, Mapping):
        if csv_text is not None or has_direct:
            raise ValueError(
                "pass a CSV path, row mappings, or one element's arguments, not more than one"
            )
        mappings = [source]
    elif isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
        if csv_text is not None or has_direct:
            raise ValueError(
                "pass a CSV path, row mappings, or one element's arguments, not more than one"
            )
        if len(source) == 0:
            raise ValueError("element list is empty")
        mappings = list(source)
    else:
        raise TypeError("source must be a CSV path, a mapping, or a sequence of mappings")

    if csv_text is not None and has_direct:
        raise ValueError("pass a CSV path or one element's arguments, not both")
    if csv_text is not None:
        return [_canonicalize(row) for row in _read_csv_rows(Path(csv_text))]
    if mappings is not None:
        rows: list[dict[str, object]] = []
        for item in mappings:
            if not isinstance(item, Mapping):
                raise TypeError("each element must be a mapping")
            rows.append(_canonicalize(item))
        return rows
    if has_direct:
        return [_canonicalize(dict(direct))]
    raise ValueError("pass a stage CSV or one element (S, I, Z, or a transformer/pu impedance)")


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


def _parse_element(
    raw: Mapping[str, object],
    index: int,
    volts: float,
    phase: float,
    s_base_mva: float,
) -> _Draft:
    name = _text(raw.get("name"), "") or f"element{index}"
    label = name
    s_mva = _optional_number("s_mva", raw.get("s_mva"))
    s_va = _optional_number("s_va", raw.get("s_va"))
    i_ka = _optional_number("i_ka", raw.get("i_ka"))
    i_a = _optional_number("i_a", raw.get("i_a"))
    z_ohm = _optional_number("z_ohm", raw.get("z_ohm"))
    r_ohm = _optional_number("r_ohm", raw.get("r_ohm"))
    x_ohm = _optional_number("x_ohm", raw.get("x_ohm"))
    z_pu = _optional_number("z_pu", raw.get("z_pu"))
    z_percent = _optional_number("z_percent", raw.get("z_percent"))
    s_rated = _optional_number("s_rated_mva", raw.get("s_rated_mva"))
    x_over_r = _optional_number("x_over_r", raw.get("x_over_r"), allow_inf=True)
    combine = _text(raw.get("combine"), "")

    groups: list[str] = []
    if s_mva is not None or s_va is not None:
        groups.append("source")
    if i_ka is not None or i_a is not None:
        groups.append("current")
    if z_ohm is not None or r_ohm is not None or x_ohm is not None:
        groups.append("impedance")
    if s_rated is not None:
        groups.append("transformer")
    if s_rated is None and (z_pu is not None or z_percent is not None):
        groups.append("pu")
    if s_rated is not None and z_pu is None and z_percent is None:
        raise ValueError(f"{label}: transformer requires z_percent or z_pu")
    if len(groups) == 0:
        raise ValueError(
            f"{label}: a short-circuit specification is required "
            "(S, I, Z, or a transformer/pu impedance)"
        )
    if len(groups) > 1:
        raise ValueError(
            f"{label}: pass one short-circuit specification, not {' and '.join(groups)}"
        )
    if z_pu is not None and z_percent is not None:
        raise ValueError(f"{label}: pass z_percent or z_pu, not both")

    group = groups[0]
    kind = _resolve_kind(_text(raw.get("kind"), ""), group, label)
    if group == "source":
        s_va_out, r_out, x_out = _from_power(s_mva, s_va, volts, x_over_r, label)
        z_spec = math.nan
        rated = math.nan
    elif group == "current":
        s_va_out, r_out, x_out = _from_current(i_ka, i_a, volts, phase, x_over_r, label)
        z_spec = math.nan
        rated = math.nan
    elif group == "impedance":
        s_va_out, r_out, x_out = _from_impedance(z_ohm, r_ohm, x_ohm, x_over_r, volts, label)
        z_spec = math.nan
        rated = math.nan
    elif group == "transformer":
        z_spec = _spec_pu(z_percent, z_pu, label)
        rated = _positive(f"{label}: s_rated_mva", s_rated)
        s_va_out = (rated * 1e6) / z_spec
        r_out, x_out = _rx_from_magnitude((volts * volts) / s_va_out, x_over_r)
    else:
        z_spec = _spec_pu(z_percent, z_pu, label)
        rated = math.nan
        s_va_out = (s_base_mva * 1e6) / z_spec
        r_out, x_out = _rx_from_magnitude((volts * volts) / s_va_out, x_over_r)

    if not s_va_out > 0.0 or not math.isfinite(s_va_out):
        raise ValueError(f"{label}: short-circuit capacity must be positive")
    return _Draft(
        name=name,
        kind=kind,
        combine=combine,
        s_mva=s_va_out / 1e6,
        s_va=s_va_out,
        r_ohm=r_out,
        x_ohm=x_out,
        z_spec_pu=z_spec,
        s_rated_mva=rated,
    )


def _resolve_kind(token: str, group: str, label: str) -> str:
    if token == "":
        return group
    mapped = _KIND_ALIAS.get(_norm_key(token))
    if mapped is None:
        raise ValueError(
            f"{label}: kind must be source, current, impedance, line, transformer, or pu"
        )
    expect, public = mapped
    if expect != group:
        raise ValueError(f"{label}: kind {public!r} does not match the fields for a {group} element")
    return public


def _spec_pu(z_percent: float | None, z_pu: float | None, label: str) -> float:
    if z_percent is not None:
        if not z_percent > 0.0:
            raise ValueError(f"{label}: z_percent must be a positive finite number (8 means 8%)")
        return z_percent / 100.0
    if z_pu is None or not z_pu > 0.0:
        raise ValueError(f"{label}: z_pu must be a positive finite number")
    return z_pu


def _from_power(
    s_mva: float | None,
    s_va: float | None,
    volts: float,
    x_over_r: float | None,
    label: str,
) -> tuple[float, float, float]:
    if s_mva is not None and s_va is not None:
        raise ValueError(f"{label}: pass s_mva or s_va, not both")
    if s_va is not None:
        power = _positive(f"{label}: s_va", s_va)
    else:
        power = _positive(f"{label}: s_mva", s_mva) * 1e6
    r_ohm, x_ohm = _rx_from_magnitude((volts * volts) / power, x_over_r)
    return power, r_ohm, x_ohm


def _from_current(
    i_ka: float | None,
    i_a: float | None,
    volts: float,
    phase: float,
    x_over_r: float | None,
    label: str,
) -> tuple[float, float, float]:
    if i_ka is not None and i_a is not None:
        raise ValueError(f"{label}: pass i_ka or i_a, not both")
    if i_ka is not None:
        current = _positive(f"{label}: i_ka", i_ka) * 1000.0
    else:
        current = _positive(f"{label}: i_a", i_a)
    power = phase * volts * current
    r_ohm, x_ohm = _rx_from_magnitude((volts * volts) / power, x_over_r)
    return power, r_ohm, x_ohm


def _from_impedance(
    z_ohm: float | None,
    r_ohm: float | None,
    x_ohm: float | None,
    x_over_r: float | None,
    volts: float,
    label: str,
) -> tuple[float, float, float]:
    if z_ohm is not None and (r_ohm is not None or x_ohm is not None):
        raise ValueError(f"{label}: pass z_ohm or r_ohm/x_ohm, not both")
    if z_ohm is not None:
        magnitude = _positive(f"{label}: z_ohm", z_ohm)
        resistance, reactance = _rx_from_magnitude(magnitude, x_over_r)
    else:
        resistance, reactance = _complete_rx(r_ohm, x_ohm, x_over_r, label)
    magnitude = math.hypot(resistance, reactance)
    if not magnitude > 0.0:
        raise ValueError(f"{label}: impedance magnitude must be positive")
    return (volts * volts) / magnitude, resistance, reactance


def _rx_from_magnitude(magnitude: float, x_over_r: float | None) -> tuple[float, float]:
    if x_over_r is None or (math.isinf(x_over_r) and x_over_r > 0.0):
        return 0.0, magnitude
    if math.isinf(x_over_r):
        return 0.0, -magnitude
    scale = math.sqrt(1.0 + x_over_r * x_over_r)
    resistance = magnitude / scale
    return resistance, resistance * x_over_r


def _complete_rx(
    r_ohm: float | None,
    x_ohm: float | None,
    x_over_r: float | None,
    label: str,
) -> tuple[float, float]:
    if r_ohm is not None and r_ohm < 0.0:
        raise ValueError(f"{label}: resistance must be >= 0")
    if r_ohm is not None and x_ohm is not None:
        if x_over_r is not None:
            _check_xr(r_ohm, x_ohm, x_over_r, label)
        return r_ohm, x_ohm
    if r_ohm is not None and x_ohm is None and x_over_r is None:
        return r_ohm, 0.0
    if x_ohm is not None and r_ohm is None and x_over_r is None:
        return 0.0, x_ohm
    if r_ohm is not None and x_over_r is not None:
        if math.isinf(x_over_r):
            raise ValueError(f"{label}: x_over_r is infinite; pass x_ohm instead of r_ohm")
        return r_ohm, x_over_r * r_ohm
    if x_ohm is not None and x_over_r is not None:
        if x_over_r == 0.0:
            if x_ohm != 0.0:
                raise ValueError(f"{label}: x_over_r is 0; x_ohm must be 0")
            return 0.0, 0.0
        if math.isinf(x_over_r):
            if (x_over_r > 0.0 and x_ohm < 0.0) or (x_over_r < 0.0 and x_ohm > 0.0):
                raise ValueError(f"{label}: x_over_r does not match x_ohm")
            return 0.0, x_ohm
        resistance = x_ohm / x_over_r
        if resistance < 0.0:
            raise ValueError(f"{label}: resistance must be >= 0")
        return resistance, x_ohm
    raise ValueError(f"{label}: resistance or reactance is required")


def _check_xr(r_ohm: float, x_ohm: float, x_over_r: float, label: str) -> None:
    if r_ohm == 0.0:
        positive = x_ohm > 0.0 and math.isinf(x_over_r) and x_over_r > 0.0
        negative = x_ohm < 0.0 and math.isinf(x_over_r) and x_over_r < 0.0
        if not (positive or negative):
            raise ValueError(f"{label}: x_over_r does not match r_ohm and x_ohm")
        return
    if math.isinf(x_over_r) or not math.isclose(x_ohm / r_ohm, x_over_r, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError(f"{label}: x_over_r does not match r_ohm and x_ohm")


def _xr_of(r_ohm: float, x_ohm: float) -> float:
    if r_ohm == 0.0:
        if x_ohm > 0.0:
            return math.inf
        if x_ohm < 0.0:
            return -math.inf
        return math.nan
    return x_ohm / r_ohm


def _parallel(r1: float, x1: float, r2: float, x2: float) -> tuple[float, float]:
    real_num = r1 * r2 - x1 * x2
    imag_num = r1 * x2 + x1 * r2
    real_den = r1 + r2
    imag_den = x1 + x2
    denom = real_den * real_den + imag_den * imag_den
    if denom == 0.0:
        raise ValueError("parallel combination is undefined (the two impedances are opposite)")
    resistance = (real_num * real_den + imag_num * imag_den) / denom
    reactance = (imag_num * real_den - real_num * imag_den) / denom
    return resistance, reactance


def _clean_rx(r_ohm: float, x_ohm: float) -> tuple[float, float]:
    magnitude = math.hypot(r_ohm, x_ohm)
    if magnitude == 0.0:
        return 0.0, 0.0
    tol = magnitude * 1e-12
    if abs(r_ohm) <= tol:
        r_ohm = 0.0
    if abs(x_ohm) <= tol:
        x_ohm = 0.0
    if r_ohm < 0.0 and abs(r_ohm) <= magnitude * 1e-9:
        r_ohm = 0.0
    return r_ohm, x_ohm


def _fold(
    drafts: Sequence[_Draft],
    volts: float,
    phase: float,
    s_base_mva: float,
) -> tuple[list[ElementResult], float, float]:
    s_run = drafts[0].s_mva
    r_complex = drafts[0].r_ohm
    x_complex = drafts[0].x_ohm
    rows: list[ElementResult] = []
    for index, draft in enumerate(drafts):
        if index == 0:
            if draft.combine != "":
                _normalize_combine(draft.combine, draft.name)
            combine = "seed"
        else:
            combine = _normalize_combine(draft.combine, draft.name)
            if combine == "series":
                s_run = (s_run * draft.s_mva) / (s_run + draft.s_mva)
                r_complex += draft.r_ohm
                x_complex += draft.x_ohm
            else:
                s_run = s_run + draft.s_mva
                r_complex, x_complex = _parallel(r_complex, x_complex, draft.r_ohm, draft.x_ohm)
        z_own = (volts * volts) / draft.s_va
        i_own = draft.s_va / (phase * volts)
        z_run = (volts * volts) / (s_run * 1e6)
        i_run = (s_run * 1e6) / (phase * volts)
        rows.append(
            ElementResult(
                name=draft.name,
                kind=draft.kind,
                combine=combine,
                s_mva=draft.s_mva,
                s_va=draft.s_va,
                z_ohm=z_own,
                r_ohm=draft.r_ohm,
                x_ohm=draft.x_ohm,
                x_over_r=_xr_of(draft.r_ohm, draft.x_ohm),
                z_pu=s_base_mva / draft.s_mva,
                z_spec_pu=draft.z_spec_pu,
                s_rated_mva=draft.s_rated_mva,
                i_a=i_own,
                i_ka=i_own / 1000.0,
                s_running_mva=s_run,
                z_running_ohm=z_run,
                i_running_a=i_run,
                i_running_ka=i_run / 1000.0,
            )
        )
    return rows, *_clean_rx(r_complex, x_complex)


def _csv_number(value: float) -> str:
    if math.isnan(value):
        return ""
    if math.isinf(value):
        return "-inf" if value < 0.0 else "inf"
    return f"{value:.12g}"


def _write_csv(path: Path, rows: Sequence[ElementResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "name": row.name,
                    "kind": row.kind,
                    "combine": row.combine,
                    "s_mva": _csv_number(row.s_mva),
                    "s_va": _csv_number(row.s_va),
                    "z_ohm": _csv_number(row.z_ohm),
                    "r_ohm": _csv_number(row.r_ohm),
                    "x_ohm": _csv_number(row.x_ohm),
                    "x_over_r": _csv_number(row.x_over_r),
                    "z_pu": _csv_number(row.z_pu),
                    "z_spec_pu": _csv_number(row.z_spec_pu),
                    "s_rated_mva": _csv_number(row.s_rated_mva),
                    "i_a": _csv_number(row.i_a),
                    "i_ka": _csv_number(row.i_ka),
                    "s_running_mva": _csv_number(row.s_running_mva),
                    "z_running_ohm": _csv_number(row.z_running_ohm),
                    "i_running_a": _csv_number(row.i_running_a),
                    "i_running_ka": _csv_number(row.i_running_ka),
                }
            )


def _render_figure(result: ShortCircuitResult, output_png: str | None, show: bool) -> object | None:
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
    names = [row.name for row in result.elements]
    own = [row.s_mva for row in result.elements]
    running = [row.s_running_mva for row in result.elements]
    colors = [_KIND_COLOR.get(row.kind, "#333333") for row in result.elements]
    steps = list(range(1, len(result.elements) + 1))
    with plt.rc_context(style):
        fig, axes = plt.subplots(2, 1, figsize=(10.2, 7.4))
        bars = axes[0]
        bars.bar(names, own, color=colors, width=0.72, zorder=2)
        bars.set_ylabel("Short-circuit MVA")
        bars.set_xlabel("Element")
        bars.set_title("Element short-circuit capacity")
        bars.grid(True, axis="y", color="#d0d0d0", linewidth=0.6)
        bars.set_axisbelow(True)
        high_own = max(own) if own else 1.0
        bars.set_ylim(0.0, high_own * 1.18)

        profile = axes[1]
        profile.plot(
            steps,
            running,
            color="#1f4e79",
            marker="o",
            linewidth=2.0,
            label="running equivalent",
        )
        profile.axhline(
            result.s_mva,
            color="#c0392b",
            linestyle="--",
            linewidth=1.0,
            label="final S_sc",
        )
        for step, value in zip(steps, running):
            profile.annotate(
                f"{value:.1f}",
                (step, value),
                textcoords="offset points",
                xytext=(0, 8),
                ha="center",
                fontsize=9,
                color="#333333",
            )
        profile.set_xticks(steps, names)
        profile.set_xlabel("Step")
        profile.set_ylabel("Running S_sc (MVA)")
        profile.set_title(
            f"MVA method at {result.v_kv:.4g} kV    "
            f"I_sc = {result.i_ka:.4f} kA    Z = {result.z_ohm:.4f} ohm"
        )
        high_run = max([*running, result.s_mva, 1.0])
        profile.set_ylim(0.0, high_run * 1.22)
        profile.grid(True, color="#d0d0d0", linewidth=0.6)
        profile.legend(loc="best", frameon=True, edgecolor="#cccccc")
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
