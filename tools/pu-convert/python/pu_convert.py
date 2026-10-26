"""Convert between SI (named) values and per-unit values.

The formulas match ``matlab/pu_convert.m``.

Classroom three-phase bases (line-to-line ``V_base``, three-phase ``S_base``):

    I_base = S_base / (sqrt(3) * V_base)
    Z_base = V_base^2 / S_base

Single-phase bases drop the ``sqrt(3)`` in the current:

    I_base = S_base / V_base
    Z_base = V_base^2 / S_base

``V``, ``I``, and ``Z`` / ``R`` / ``X`` use the winding selected by ``side``.
``S``, ``P``, and ``Q`` always use ``S_base``. An ohmic impedance can be
referred to the other winding before the per-unit step:

    Z_dest = Z_src * (V_dest / V_src)^2

Both windings share one ``S_base``, so a correct referral does not change pu.
"""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from pathlib import Path

DEFAULT_S_BASE = 100e6
DEFAULT_V_BASE_HV = 220e3
DEFAULT_V_BASE_LV = 110e3

QUANTITIES = ("V", "I", "S", "P", "Q", "Z", "R", "X")
IMPEDANCE = ("Z", "R", "X")
POWER = ("S", "P", "Q")

_QUANTITY_ALIAS = {
    "v": "V",
    "voltage": "V",
    "u": "V",
    "i": "I",
    "current": "I",
    "s": "S",
    "power": "S",
    "apparent": "S",
    "p": "P",
    "active": "P",
    "q": "Q",
    "reactive": "Q",
    "z": "Z",
    "impedance": "Z",
    "r": "R",
    "resistance": "R",
    "x": "X",
    "reactance": "X",
}

_SI_UNIT = {
    "V": "V",
    "I": "A",
    "S": "VA",
    "P": "W",
    "Q": "var",
    "Z": "ohm",
    "R": "ohm",
    "X": "ohm",
}

# family, scale-to-SI, label. mva/mvar follow power-system habit (mega, not milli).
_UNITS: dict[str, tuple[str, float, str]] = {
    "v": ("V", 1.0, "V"),
    "kv": ("V", 1e3, "kV"),
    "a": ("I", 1.0, "A"),
    "ka": ("I", 1e3, "kA"),
    "va": ("S", 1.0, "VA"),
    "kva": ("S", 1e3, "kVA"),
    "mva": ("S", 1e6, "MVA"),
    "w": ("S", 1.0, "W"),
    "kw": ("S", 1e3, "kW"),
    "mw": ("S", 1e6, "MW"),
    "var": ("S", 1.0, "var"),
    "kvar": ("S", 1e3, "kvar"),
    "mvar": ("S", 1e6, "Mvar"),
    "ohm": ("Z", 1.0, "ohm"),
    "ohms": ("Z", 1.0, "ohm"),
    "pu": ("pu", 1.0, "pu"),
    "perunit": ("pu", 1.0, "pu"),
}

_Q_COLOR = {
    "V": "#1f4e79",
    "I": "#c0392b",
    "S": "#e67e22",
    "P": "#d68910",
    "Q": "#6c3483",
    "Z": "#3d7a6a",
    "R": "#1a5276",
    "X": "#117a65",
}

_PARAM_NAMES = {
    "value",
    "quantity",
    "direction",
    "name",
    "unit_hint",
    "unit_out",
    "side",
    "refer_to",
    "s_base",
    "v_base",
    "v_base_hv",
    "v_base_lv",
    "system",
    "csv_path",
    "output_csv",
    "output_png",
    "show",
}


@dataclass
class PuRow:
    """One SI / per-unit conversion.

    ``value_si`` is in ``si_unit`` on ``winding``. ``value_pu`` is
    ``value_si / base_used``. ``value_out`` is the number requested by
    ``direction``, expressed in ``unit_out``.
    """

    name: str
    quantity: str
    direction: str
    side: str
    refer_to: str
    winding: str
    value_in: float
    unit_in: str
    value_pu: float
    value_si: float
    si_unit: str
    value_out: float
    unit_out: str
    base_used: float


@dataclass
class PuConvertResult:
    """Bases for the three labels (same / hv / lv) and any converted rows.

    ``same`` uses ``v_base`` when that argument is set, otherwise the HV base.
    ``hv`` and ``lv`` always use ``v_base_hv`` and ``v_base_lv``. ``S``, ``P``,
    and ``Q`` still divide by the shared ``s_base``.
    """

    s_base: float
    system: str
    v_base: float
    v_base_hv: float
    v_base_lv: float
    i_base: float
    i_base_hv: float
    i_base_lv: float
    z_base: float
    z_base_hv: float
    z_base_lv: float
    rows: list[PuRow]
    output_csv: str | None
    output_png: str | None
    fig: object | None = None


def pu_convert(
    source: Real | str | Path | Mapping | Sequence | None = None,
    *,
    value: Real | None = None,
    quantity: str = "V",
    direction: str = "to_pu",
    name: str = "",
    unit_hint: str = "",
    unit_out: str = "",
    side: str = "same",
    refer_to: str = "",
    s_base: float = DEFAULT_S_BASE,
    v_base: float | None = None,
    v_base_hv: float = DEFAULT_V_BASE_HV,
    v_base_lv: float = DEFAULT_V_BASE_LV,
    system: str = "three_phase",
    csv_path: str | Path | None = None,
    output_csv: str | Path | None = None,
    output_png: str | Path | None = None,
    show: bool = False,
) -> PuConvertResult:
    """Compute bases and convert named values to per-unit, or the reverse.

    Parameters use the same names as the MATLAB name-value arguments.
    ``source`` may be a number (one value), a CSV path, one mapping, or a
    sequence of mappings. Pass nothing to return the classroom bases only.

    Three-phase is the default: ``V_base`` is line-to-line and ``S_base`` is
    three-phase. ``system='single_phase'`` uses ``I_base = S_base / V_base``.
    """

    system_name = _normalize_system(system)
    s_base = _positive("s_base", s_base)
    v_base_hv = _positive("v_base_hv", v_base_hv)
    v_base_lv = _positive("v_base_lv", v_base_lv)
    if v_base is None:
        v_same = v_base_hv
    else:
        v_same = _positive("v_base", v_base)
    three_phase = system_name == "three_phase"
    i_same, z_same = _side_bases(s_base, v_same, three_phase)
    i_hv, z_hv = _side_bases(s_base, v_base_hv, three_phase)
    i_lv, z_lv = _side_bases(s_base, v_base_lv, three_phase)

    csv_text, scalar, mappings = _resolve_source(source, value=value, csv_path=csv_path)
    if csv_text is not None:
        raw_rows = _read_csv_rows(Path(csv_text))
    elif mappings is not None:
        raw_rows = mappings
    elif scalar is not None:
        raw_rows = [
            {
                "name": name,
                "quantity": quantity,
                "value": scalar,
                "unit_hint": unit_hint,
                "unit_out": unit_out,
                "direction": direction,
                "side": side,
                "refer_to": refer_to,
            }
        ]
    else:
        raw_rows = []

    ctx = {
        "s_base": s_base,
        "v_same": v_same,
        "v_hv": v_base_hv,
        "v_lv": v_base_lv,
        "three_phase": three_phase,
        "direction": direction,
        "side": side,
        "quantity": quantity,
        "unit_hint": unit_hint,
        "unit_out": unit_out,
        "refer_to": refer_to,
        "name": name,
        "from_scalar": scalar is not None and csv_text is None and mappings is None,
    }
    rows = [_convert_row(raw, ctx, index) for index, raw in enumerate(raw_rows, start=1)]

    csv_out = None if output_csv is None or str(output_csv).strip() == "" else str(output_csv)
    png_out = None if output_png is None or str(output_png).strip() == "" else str(output_png)
    if csv_out is not None:
        _write_csv(Path(csv_out), rows)
    fig = None
    if png_out is not None or show:
        if not rows:
            raise ValueError("output_png/show needs at least one converted row")
        fig = _render_figure(rows, png_out, bool(show))
    return PuConvertResult(
        s_base=s_base,
        system=system_name,
        v_base=v_same,
        v_base_hv=v_base_hv,
        v_base_lv=v_base_lv,
        i_base=i_same,
        i_base_hv=i_hv,
        i_base_lv=i_lv,
        z_base=z_same,
        z_base_hv=z_hv,
        z_base_lv=z_lv,
        rows=rows,
        output_csv=csv_out,
        output_png=png_out,
        fig=fig,
    )


def format_table(result: PuConvertResult) -> str:
    """Format the bases and each converted row as a text table."""

    lines = [
        (
            f"system={result.system}  S_base={_compact(result.s_base)} VA "
            f"({_compact(result.s_base / 1e6)} MVA)"
        ),
        f"{'side':<6} {'V_base_V':>12} {'I_base_A':>12} {'Z_base_ohm':>12}",
    ]
    for label, volts, amps, ohms in (
        ("same", result.v_base, result.i_base, result.z_base),
        ("hv", result.v_base_hv, result.i_base_hv, result.z_base_hv),
        ("lv", result.v_base_lv, result.i_base_lv, result.z_base_lv),
    ):
        lines.append(f"{label:<6} {_num(volts)} {_num(amps)} {_num(ohms)}")
    lines.append("")
    lines.append(
        f"{'name':<18} {'qty':>3} {'dir':>6} {'side':>5} {'refer':>5} "
        f"{'value_in':>12} {'unit_in':>8} {'pu':>10} {'value_si':>12} "
        f"{'si_unit':>7} {'value_out':>12} {'unit_out':>8}"
    )
    for row in result.rows:
        refer = row.refer_to if row.refer_to else "-"
        if row.unit_out == "pu":
            value_out = f"{row.value_out:12.4f}"
        else:
            value_out = _num(row.value_out)
        lines.append(
            f"{row.name:<18} {row.quantity:>3} {row.direction:>6} {row.side:>5} {refer:>5} "
            f"{_num(row.value_in)} {row.unit_in:>8} {row.value_pu:10.4f} {_num(row.value_si)} "
            f"{row.si_unit:>7} {value_out} {row.unit_out:>8}"
        )
    return "\n".join(lines)


def _compact(value: float) -> str:
    """Short decimal text. Large integers stay in fixed point (100000000, not 1e+08)."""

    if not math.isfinite(value):
        return "nan"
    text = f"{value:.6g}"
    if "e" not in text and "E" not in text:
        return text
    if abs(value - round(value)) <= 1e-6 * max(abs(value), 1.0):
        return f"{value:.0f}"
    return f"{value:.4f}"


def _num(value: float) -> str:
    return _compact(value).rjust(12)


def _positive(label: str, value: object) -> float:
    number = _finite(label, value)
    if number <= 0:
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


def _normalize_system(system: object) -> str:
    key = re.sub(r"[\s_\-]", "", str(system).strip().lower())
    if key in {"threephase", "3phase", "3ph"}:
        return "three_phase"
    if key in {"singlephase", "1phase", "1ph"}:
        return "single_phase"
    raise ValueError("system must be 'three_phase' or 'single_phase'")


def _side_bases(s_base: float, v_base: float, three_phase: bool) -> tuple[float, float]:
    if three_phase:
        i_base = s_base / (math.sqrt(3.0) * v_base)
    else:
        i_base = s_base / v_base
    z_base = (v_base * v_base) / s_base
    return i_base, z_base


def _is_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _resolve_source(
    source: object,
    *,
    value: object,
    csv_path: str | Path | None,
) -> tuple[str | None, float | None, list | None]:
    """Return ``(csv_path, scalar_value, mapping_rows)`` with only one set."""

    csv_text = None if csv_path is None or str(csv_path).strip() == "" else str(csv_path)
    scalar = None if value is None else _finite("value", value)
    mappings = None
    if source is None:
        pass
    elif _is_number(source):
        if scalar is not None:
            raise ValueError("pass the value once, either positionally or as value=")
        scalar = float(source)
    elif isinstance(source, (str, Path)):
        text = str(source).strip()
        if text.lower() in _PARAM_NAMES:
            raise ValueError(
                f"{text!r} is a parameter name. Pass the CSV path as csv_path= or as the first argument"
            )
        if csv_text is not None:
            raise ValueError("pass a CSV path once, either positionally or as csv_path=")
        csv_text = text
    elif isinstance(source, Mapping):
        if csv_text is not None or scalar is not None:
            raise ValueError("pass a CSV path, a single value, or row mappings, not more than one")
        mappings = [source]
    elif isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
        if csv_text is not None or scalar is not None:
            raise ValueError("pass a CSV path, a single value, or row mappings, not more than one")
        mappings = list(source)
    else:
        raise TypeError("source must be a number, a CSV path, a mapping, or a sequence of mappings")
    if csv_text is not None and scalar is not None:
        raise ValueError("pass a CSV path or a single value, not both")
    if csv_text is not None and mappings is not None:
        raise ValueError("pass a CSV path or row mappings, not both")
    return csv_text, scalar, mappings


def _norm_key(key: object) -> str:
    return re.sub(r"[\s_\-]", "", str(key).strip().lower())


def _lookup(row: Mapping[str, object], *keys: str) -> object | None:
    folded = {_norm_key(key): value for key, value in row.items() if key is not None}
    for key in keys:
        if key in folded:
            return folded[key]
    return None


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


def _normalize_quantity(value: object) -> str:
    if _blank(value):
        raise ValueError("quantity is required")
    key = _norm_key(value)
    if key not in _QUANTITY_ALIAS:
        joined = ", ".join(QUANTITIES)
        raise ValueError(f"quantity must be one of: {joined}")
    return _QUANTITY_ALIAS[key]


def _normalize_direction(value: object) -> str:
    key = _norm_key(value)
    if key in {"topu", "sitopu", "namedtopu"}:
        return "to_pu"
    if key in {"tosi", "putosi", "putonamed"}:
        return "to_si"
    raise ValueError("direction must be 'to_pu' or 'to_si'")


def _normalize_side(value: object, *, default: str) -> str:
    if _blank(value):
        value = default
    key = _norm_key(value)
    if key in {"same", "primary", "none"}:
        return "same"
    if key in {"hv", "high", "highside", "highvoltage"}:
        return "hv"
    if key in {"lv", "low", "lowside", "lowvoltage"}:
        return "lv"
    raise ValueError("side must be 'same', 'hv', or 'lv'")


def _normalize_refer(value: object) -> str:
    if _blank(value):
        return ""
    key = _norm_key(value)
    if key in {"same", "primary", "none", "na"}:
        return ""
    if key in {"hv", "high", "highside", "highvoltage"}:
        return "hv"
    if key in {"lv", "low", "lowside", "lowvoltage"}:
        return "lv"
    raise ValueError("refer_to must be 'hv', 'lv', or empty")


def _unit_key(value: object) -> str:
    text = str(value).strip()
    text = text.replace("Ω", "ohm").replace("Ω", "ohm").replace("ω", "ohm")
    return re.sub(r"[\s_\-./]", "", text.lower())


def _family(quantity: str) -> str:
    if quantity == "V":
        return "V"
    if quantity == "I":
        return "I"
    if quantity in POWER:
        return "S"
    return "Z"


def _parse_input_unit(quantity: str, unit_hint: str) -> tuple[float, str]:
    si_unit = _SI_UNIT[quantity]
    if unit_hint == "":
        return 1.0, si_unit
    key = _unit_key(unit_hint)
    spec = _UNITS.get(key)
    if spec is None:
        raise ValueError(f"unit_hint {unit_hint!r} is not a supported unit")
    family, scale, label = spec
    if family == "pu":
        raise ValueError("unit_hint 'pu' is not a named unit; direction to_pu expects a SI value")
    if family != _family(quantity):
        raise ValueError(f"unit_hint {label!r} does not match quantity {quantity}")
    return scale, label


def _parse_output_unit(quantity: str, unit_out: str) -> tuple[float, str]:
    si_unit = _SI_UNIT[quantity]
    if unit_out == "":
        return 1.0, si_unit
    key = _unit_key(unit_out)
    spec = _UNITS.get(key)
    if spec is None:
        raise ValueError(f"unit_out {unit_out!r} is not a supported unit")
    family, scale, label = spec
    if family == "pu":
        return 1.0, si_unit
    if family != _family(quantity):
        raise ValueError(f"unit_out {label!r} does not match quantity {quantity}")
    return scale, label


def _voltage_for(side: str, ctx: dict) -> float:
    if side == "hv":
        return float(ctx["v_hv"])
    if side == "lv":
        return float(ctx["v_lv"])
    return float(ctx["v_same"])


def _convert_row(raw: Mapping[str, object], ctx: dict, index: int) -> PuRow:
    from_scalar = bool(ctx["from_scalar"])
    quantity_value = _lookup(raw, "quantity", "qty", "type")
    if _blank(quantity_value):
        if from_scalar:
            quantity_value = ctx["quantity"]
        else:
            raise ValueError("quantity is required")
    quantity = _normalize_quantity(quantity_value)

    direction_value = _lookup(raw, "direction", "dir")
    if _blank(direction_value):
        direction_value = ctx["direction"]
    direction = _normalize_direction(direction_value)

    side_value = _lookup(raw, "side")
    if _blank(side_value):
        side_value = ctx["side"]
    side = _normalize_side(side_value, default="same")

    refer_value = _lookup(raw, "referto", "refer", "refertowinding")
    if _blank(refer_value):
        refer_value = ctx["refer_to"] if from_scalar else ""
    refer = _normalize_refer(refer_value)
    if refer == side:
        refer = ""
    if refer and quantity not in IMPEDANCE:
        raise ValueError("refer_to applies only to Z, R, and X")

    value_raw = _lookup(raw, "value", "val")
    if _blank(value_raw):
        raise ValueError("value is required")
    value = _finite("value", value_raw)

    name = _text(_lookup(raw, "name"), "")
    if name == "" and from_scalar:
        name = _text(ctx["name"], "")
    if name == "":
        name = quantity if from_scalar else f"row{index}"

    hint = _text(_lookup(raw, "unithint", "unit", "units"), "")
    if hint == "" and from_scalar:
        hint = _text(ctx["unit_hint"], "")
    out_hint = _text(_lookup(raw, "unitout"), "")
    if out_hint == "" and from_scalar:
        out_hint = _text(ctx["unit_out"], "")

    if direction == "to_si" and hint != "" and _unit_key(hint) not in {"pu", "perunit"}:
        raise ValueError(
            "for direction to_si the input is per-unit; leave unit_hint blank or 'pu', "
            "and set unit_out for a scaled SI result"
        )

    src_v = _voltage_for(side, ctx)
    dst_side = refer if refer else side
    dst_v = _voltage_for(dst_side, ctx)
    i_src, z_src = _side_bases(float(ctx["s_base"]), src_v, bool(ctx["three_phase"]))
    _, z_dst = _side_bases(float(ctx["s_base"]), dst_v, bool(ctx["three_phase"]))
    si_unit = _SI_UNIT[quantity]
    if quantity == "V":
        base_used = src_v
        dst_side = side
    elif quantity == "I":
        base_used = i_src
        dst_side = side
    elif quantity in POWER:
        base_used = float(ctx["s_base"])
        dst_side = side
    else:
        base_used = z_dst

    if direction == "to_pu":
        scale, unit_in = _parse_input_unit(quantity, hint)
        value_si_src = value * scale
        if quantity in IMPEDANCE and refer:
            value_si = value_si_src * (dst_v / src_v) ** 2
        else:
            value_si = value_si_src
        value_pu = value_si / base_used
        value_out = value_pu
        unit_out_label = "pu"
    else:
        value_pu = value
        if quantity in IMPEDANCE:
            value_si_src = value_pu * z_src
            if refer:
                value_si = value_si_src * (dst_v / src_v) ** 2
            else:
                value_si = value_si_src
        else:
            value_si = value_pu * base_used
        scale, unit_out_label = _parse_output_unit(quantity, out_hint)
        value_out = value_si / scale
        unit_in = "pu"

    return PuRow(
        name=name,
        quantity=quantity,
        direction=direction,
        side=side,
        refer_to=refer,
        winding=dst_side,
        value_in=value,
        unit_in=unit_in,
        value_pu=value_pu,
        value_si=value_si,
        si_unit=si_unit,
        value_out=value_out,
        unit_out=unit_out_label,
        base_used=base_used,
    )


_CSV_FIELDS = (
    "name",
    "quantity",
    "direction",
    "side",
    "refer_to",
    "winding",
    "value_in",
    "unit_in",
    "value_pu",
    "value_si",
    "si_unit",
    "value_out",
    "unit_out",
    "base_used",
)


def _write_csv(path: Path, rows: Sequence[PuRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "name": row.name,
                    "quantity": row.quantity,
                    "direction": row.direction,
                    "side": row.side,
                    "refer_to": row.refer_to,
                    "winding": row.winding,
                    "value_in": f"{row.value_in:.12g}",
                    "unit_in": row.unit_in,
                    "value_pu": f"{row.value_pu:.12g}",
                    "value_si": f"{row.value_si:.12g}",
                    "si_unit": row.si_unit,
                    "value_out": f"{row.value_out:.12g}",
                    "unit_out": row.unit_out,
                    "base_used": f"{row.base_used:.12g}",
                }
            )


def _render_figure(rows: Sequence[PuRow], output_png: str | None, show: bool) -> object | None:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    style = {
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#444444",
    }
    names = [row.name for row in rows]
    values = [row.value_pu for row in rows]
    colors = [_Q_COLOR[row.quantity] for row in rows]
    with plt.rc_context(style):
        fig_h = max(4.2, 0.42 * len(rows) + 1.6)
        fig, ax = plt.subplots(figsize=(10.2, fig_h))
        positions = list(range(len(rows)))
        ax.barh(positions, values, color=colors, height=0.72, zorder=2)
        ax.set_yticks(positions)
        ax.set_yticklabels(names)
        ax.invert_yaxis()
        ax.axvline(0.0, color="#666666", linewidth=0.8, zorder=1)
        ax.set_xlabel("Per-unit value")
        ax.set_title("Per-unit values (mixed quantities)")
        ax.grid(True, axis="x", color="#d0d0d0", linewidth=0.6)
        ax.set_axisbelow(True)
        finite = [item for item in values if math.isfinite(item)]
        if finite:
            low = min(0.0, min(finite))
            high = max(0.0, max(finite))
            span = max(high - low, 0.5)
            ax.set_xlim(low - 0.08 * span, high + 0.18 * span)
        seen: list[str] = []
        for row in rows:
            if row.quantity not in seen:
                seen.append(row.quantity)
        ax.legend(
            handles=[Patch(facecolor=_Q_COLOR[item], edgecolor=_Q_COLOR[item], label=item) for item in seen],
            loc="best",
            frameon=True,
            edgecolor="#cccccc",
            title="quantity",
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
