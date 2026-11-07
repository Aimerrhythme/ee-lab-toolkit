"""Short-circuit sample synthesis and protection-label export.

The radial feeder formulas match ``matlab/pp_fault_synth_export.m``.

One source feeds a radial MV feeder. The pre-fault voltage is 1.0 pu and
load current is ignored, so each bus is a Thevenin source behind the
positive- and zero-sequence driving-point impedances. Negative sequence
equals positive sequence. Fault resistance ``R_f`` is in ohms at the
faulted bus:

    ABC    I1 = E / (Z1 + R_f)              phase currents equal |I1|
    AG     I1 = I2 = I0 = E / (Z1+Z2+Z0+3 R_f)    Ia = 3 I1
    BC     I1 = -I2 = E / (Z1+Z2+R_f)       |Ib| = |Ic| = sqrt(3) |I1|

BG/CG are the AG phase pattern cycled once and twice. AB/CA are the BC
pattern cycled so the healthy phase moves. ``label_protect`` is the
protection class: phase-to-ground, phase-to-phase, or three-phase.

``engine='zbus'`` (default) uses this feeder and is the MATLAB path.
``engine='pandapower'`` reads CIGRE-MV (or the same radial feeder) from
pandapower and applies the same fault equations. ``engine='auto'`` uses
pandapower when the package imports, and the radial feeder otherwise.
"""

from __future__ import annotations

import csv
import math
import re
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Integral, Real
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_V_KV = 10.0
DEFAULT_S_BASE_MVA = 10.0
DEFAULT_SEED = 42
DEFAULT_R_FAULT_OHM = (0.0, 1.0, 5.0)
Z0_SOURCE_FACTOR = 1.5
Z0_LINE_FACTOR = 3.0
_LCG_A = 16807
_LCG_M = 2147483647
_A_OP = complex(-0.5, math.sqrt(3.0) / 2.0)
_A2_OP = complex(-0.5, -math.sqrt(3.0) / 2.0)

# family, phase rotation steps, code, protection class
_FAULTS = {
    "AG": ("slg", 0, 1, "phase-to-ground"),
    "BG": ("slg", 1, 2, "phase-to-ground"),
    "CG": ("slg", 2, 3, "phase-to-ground"),
    "AB": ("ll", 2, 4, "phase-to-phase"),
    "BC": ("ll", 0, 5, "phase-to-phase"),
    "CA": ("ll", 1, 6, "phase-to-phase"),
    "ABC": ("abc", 0, 7, "three-phase"),
}
_FAULT_ORDER = ("AG", "BG", "CG", "AB", "BC", "CA", "ABC")
_FAULT_ALIAS = {
    "ag": "AG",
    "bg": "BG",
    "cg": "CG",
    "ab": "AB",
    "bc": "BC",
    "ca": "CA",
    "ac": "CA",
    "abc": "ABC",
    "3ph": "ABC",
    "3p": "ABC",
    "ll": "BC",
    "2ph": "BC",
    "pp": "BC",
    "lg": "AG",
    "slg": "AG",
    "1ph": "AG",
}

_KEY_ALIAS = {
    "kind": "kind",
    "type": "kind",
    "name": "name",
    "element": "name",
    "id": "name",
    "frombus": "from_bus",
    "from": "from_bus",
    "bus": "from_bus",
    "busfrom": "from_bus",
    "tobus": "to_bus",
    "to": "to_bus",
    "busto": "to_bus",
    "lengthkm": "length_km",
    "length": "length_km",
    "km": "length_km",
    "r1ohm": "r1_ohm",
    "r1": "r1_ohm",
    "x1ohm": "x1_ohm",
    "x1": "x1_ohm",
    "r0ohm": "r0_ohm",
    "r0": "r0_ohm",
    "x0ohm": "x0_ohm",
    "x0": "x0_ohm",
    "z1ohm": "z1_ohm",
    "z1": "z1_ohm",
    "xoverr": "x_over_r",
    "xr": "x_over_r",
    "z0factor": "z0_factor",
    "k0": "z0_factor",
}

_PARAM_NAMES = {
    "v_kv",
    "s_base_mva",
    "fault_types",
    "r_fault_ohm",
    "buses",
    "n_samples",
    "seed",
    "engine",
    "network",
    "z0_line_factor",
    "z0_source_factor",
    "csv_path",
    "output_csv",
    "output_png",
    "show",
}

CSV_COLUMNS = (
    "sample_id",
    "bus_id",
    "line_id",
    "distance_km",
    "fault_type",
    "fault_type_code",
    "label_protect",
    "R_f_ohm",
    "V_a_pu",
    "V_b_pu",
    "V_c_pu",
    "V_bus_mag_pu",
    "I_phase_a_A",
    "I_phase_b_A",
    "I_phase_c_A",
    "I_fault_mag_A",
    "I_fault_mag_pu",
    "engine",
)

_CLASS_COLOR = {
    "AG": "#1f4e79",
    "BC": "#c0392b",
    "ABC": "#117a65",
}

# Per-km values that reproduce the total ohms in the example CSV.
_BUILTIN_LINES = (
    {
        "name": "L1",
        "from_bus": "B0",
        "to_bus": "B1",
        "length_km": 1.5,
        "r1_ohm": 0.405,
        "x1_ohm": 0.525,
        "r0_ohm": 1.215,
        "x0_ohm": 1.575,
    },
    {
        "name": "L2",
        "from_bus": "B1",
        "to_bus": "B2",
        "length_km": 1.2,
        "r1_ohm": 0.48,
        "x1_ohm": 0.444,
        "r0_ohm": 1.44,
        "x0_ohm": 1.332,
    },
    {
        "name": "L3",
        "from_bus": "B2",
        "to_bus": "B3",
        "length_km": 0.8,
        "r1_ohm": 0.44,
        "x1_ohm": 0.304,
        "r0_ohm": 1.32,
        "x0_ohm": 0.912,
    },
    {
        "name": "L4",
        "from_bus": "B3",
        "to_bus": "B4",
        "length_km": 0.6,
        "r1_ohm": 0.39,
        "x1_ohm": 0.24,
        "r0_ohm": 1.17,
        "x0_ohm": 0.72,
    },
)


@dataclass
class FaultSample:
    """One labeled short-circuit case. CSV headers use the public names."""

    sample_id: int
    bus_id: str
    line_id: str
    distance_km: float
    fault_type: str
    fault_type_code: int
    label_protect: str
    r_f_ohm: float
    v_a_pu: float
    v_b_pu: float
    v_c_pu: float
    v_bus_mag_pu: float
    i_phase_a_a: float
    i_phase_b_a: float
    i_phase_c_a: float
    i_fault_mag_a: float
    i_fault_mag_pu: float
    engine: str


@dataclass
class FaultSynthResult:
    """Exported sample set. ``summary`` matches the MATLAB text for zbus."""

    engine: str
    network: str
    v_kv: float
    v_ll_v: float
    s_base_mva: float
    z_base_ohm: float
    i_base_a: float
    seed: int
    n_grid: int
    n_samples: int
    anchor_bus: str
    remote_bus: str
    samples: list[FaultSample]
    summary: str
    preview: str
    output_csv: str | None
    output_png: str | None
    frame: pd.DataFrame
    fig: object | None = None


@dataclass
class _BusPoint:
    bus_id: str
    line_id: str
    distance_km: float
    z1_ohm: complex
    z0_ohm: complex
    v_ll_v: float
    order: int


@dataclass
class _SourceSpec:
    bus_id: str
    z1: complex
    z0: complex


@dataclass
class _LineSpec:
    name: str
    from_bus: str
    to_bus: str
    length_km: float
    z1: complex
    z0: complex


def pp_fault_synth_export(
    source: str | Path | None = None,
    *,
    v_kv: float = DEFAULT_V_KV,
    s_base_mva: float = DEFAULT_S_BASE_MVA,
    fault_types: Sequence[str] | str | None = None,
    r_fault_ohm: Sequence[float] | float = DEFAULT_R_FAULT_OHM,
    buses: Sequence[str] | str | None = None,
    n_samples: int | None = None,
    seed: int = DEFAULT_SEED,
    engine: str = "zbus",
    network: str | None = None,
    z0_line_factor: float = Z0_LINE_FACTOR,
    z0_source_factor: float = Z0_SOURCE_FACTOR,
    csv_path: str | Path | None = None,
    output_csv: str | Path | None = None,
    output_png: str | Path | None = None,
    show: bool = False,
) -> FaultSynthResult:
    """Sweep fault location, type, and resistance, and export a labeled CSV.

    Parameters use the same names as the MATLAB name-value arguments.
    ``source`` is a radial feeder CSV. Omit it to use the built-in 10 kV feeder.
    """

    volts_kv = _positive("v_kv", v_kv)
    base_mva = _positive("s_base_mva", s_base_mva)
    seed_value = _seed(seed)
    types = _parse_fault_types(fault_types)
    resistances = _parse_resistances(r_fault_ohm)
    bus_filter = _parse_buses(buses)
    engine_name = _normalize_engine(engine)
    line_factor = _positive("z0_line_factor", z0_line_factor)
    source_factor = _positive("z0_source_factor", z0_source_factor)
    feeder_path = _resolve_feeder_path(source, csv_path)
    resolved = _resolve_engine(engine_name)
    network_name = _resolve_network(network, resolved)

    if resolved == "zbus":
        if network_name != "radial":
            raise ValueError("network 'cigre_mv' needs engine='pandapower' or engine='auto'")
        points = _radial_points(feeder_path, volts_kv * 1000.0, source_factor)
    else:
        points = _pandapower_points(network_name, base_mva, line_factor, source_factor)

    if bus_filter is not None:
        known = {point.bus_id for point in points}
        missing = [bus for bus in bus_filter if bus not in known]
        if missing:
            raise ValueError(f"unknown bus {missing[0]!r}")
        wanted = set(bus_filter)
        points = [point for point in points if point.bus_id in wanted]
        if not points:
            raise ValueError("bus filter removed every bus")

    reference = _reference_point(points)
    volts = reference.v_ll_v
    base_va = base_mva * 1e6
    z_base = (volts * volts) / base_va
    i_base = base_va / (math.sqrt(3.0) * volts)
    grid = [
        _evaluate(point, fault, resistance, base_va, resolved)
        for point in points
        for fault in types
        for resistance in resistances
    ]
    n_grid = len(grid)
    chosen = _subsample(grid, n_samples, seed_value)
    for index, sample in enumerate(chosen, start=1):
        sample.sample_id = index

    anchor = points[0].bus_id
    remote = max(points, key=lambda point: (point.distance_km, point.order)).bus_id
    frame = _frame(chosen)
    csv_out = None if output_csv is None or str(output_csv).strip() == "" else str(output_csv)
    png_out = None if output_png is None or str(output_png).strip() == "" else str(output_png)
    result = FaultSynthResult(
        engine=resolved,
        network=network_name,
        v_kv=volts / 1000.0,
        v_ll_v=volts,
        s_base_mva=base_mva,
        z_base_ohm=z_base,
        i_base_a=i_base,
        seed=seed_value,
        n_grid=n_grid,
        n_samples=len(chosen),
        anchor_bus=anchor,
        remote_bus=remote,
        samples=chosen,
        summary="",
        preview="",
        output_csv=csv_out,
        output_png=png_out,
        frame=frame,
        fig=None,
    )
    result.preview = format_preview(result)
    result.summary = format_table(result)
    if csv_out is not None:
        _write_csv(Path(csv_out), chosen)
    if png_out is not None or show:
        result.fig = _render_figure(result, png_out, bool(show))
    return result


def format_preview(result: FaultSynthResult) -> str:
    """One-line demo summary. MATLAB prints the same text for the zbus feeder."""

    if result.n_samples == result.n_grid:
        count = f"samples={result.n_samples}"
    else:
        count = f"samples={result.n_samples} grid={result.n_grid}"
    parts = [f"pp-fault-synth-export: engine={result.engine} network={result.network} {count}"]
    for fault, prefix in (("AG", True), ("BC", False), ("ABC", False)):
        row = _represent(result, fault)
        if row is None:
            continue
        if prefix:
            parts.append(
                f"AG@{row.bus_id} Rf={row.r_f_ohm:.4f} "
                f"If={row.i_fault_mag_a:.4f} A Vmin={row.v_bus_mag_pu:.4f} pu"
            )
        else:
            parts.append(f"{fault}@{row.bus_id} If={row.i_fault_mag_a:.4f} A")
    return "  ".join(parts)


def format_table(result: FaultSynthResult) -> str:
    """Format the label table. Python and MATLAB print this same text for zbus."""

    if result.n_samples == result.n_grid:
        count = f"samples={result.n_samples}"
    else:
        count = f"samples={result.n_samples} grid={result.n_grid}"
    lines = [
        (
            f"engine={result.engine}  network={result.network}  "
            f"V={result.v_kv:.4f} kV  S_base={result.s_base_mva:.4f} MVA  "
            f"Z_base={result.z_base_ohm:.4f} ohm  I_base={result.i_base_a:.4f} A  "
            f"{count}  seed={result.seed}"
        ),
        (
            f"{'type':<4} {'code':>4}  {'label':<16} {'count':>5} "
            f"{'bus':<8} {'Rf':>8} {'If_A':>12} {'Vmin':>8} "
            f"{'Va':>8} {'Vb':>8} {'Vc':>8} {'Ia':>12} {'Ib':>12} {'Ic':>12}"
        ),
    ]
    for fault in _FAULT_ORDER:
        code = _FAULTS[fault][2]
        label = _FAULTS[fault][3]
        rows = [sample for sample in result.samples if sample.fault_type == fault]
        row = _represent(result, fault)
        if row is None:
            lines.append(
                f"{fault:<4} {code:4d}  {label:<16} {0:5d} "
                f"{'-':<8} {'-':>8} {'-':>12} {'-':>8} "
                f"{'-':>8} {'-':>8} {'-':>8} {'-':>12} {'-':>12} {'-':>12}"
            )
            continue
        lines.append(
            f"{fault:<4} {code:4d}  {label:<16} {len(rows):5d} "
            f"{row.bus_id:<8} {row.r_f_ohm:8.4f} {row.i_fault_mag_a:12.4f} "
            f"{row.v_bus_mag_pu:8.4f} {row.v_a_pu:8.4f} {row.v_b_pu:8.4f} {row.v_c_pu:8.4f} "
            f"{row.i_phase_a_a:12.4f} {row.i_phase_b_a:12.4f} {row.i_phase_c_a:12.4f}"
        )
    remote_rows = [
        sample
        for sample in result.samples
        if sample.bus_id == result.remote_bus and sample.fault_type in {"AG", "BC", "ABC"}
    ]
    if remote_rows:
        remote_rf = min(sample.r_f_ohm for sample in remote_rows)
        remote_distance = remote_rows[0].distance_km
        remote_bits = []
        for fault in ("AG", "BC", "ABC"):
            matches = [
                sample
                for sample in remote_rows
                if sample.fault_type == fault and sample.r_f_ohm == remote_rf
            ]
            if matches:
                remote_bits.append(f"If_{fault}={matches[0].i_fault_mag_a:.4f} A")
        if remote_bits:
            lines.append(
                f"remote bus={result.remote_bus} distance={remote_distance:.4f} km "
                f"Rf={remote_rf:.4f} " + " ".join(remote_bits)
            )
    return "\n".join(lines)


def _represent(result: FaultSynthResult, fault: str) -> FaultSample | None:
    at_anchor = _represent_at(result, fault, result.anchor_bus)
    if at_anchor is not None:
        return at_anchor
    rows = [sample for sample in result.samples if sample.fault_type == fault]
    if not rows:
        return None
    return min(rows, key=lambda sample: (sample.r_f_ohm, sample.sample_id))


def _represent_at(result: FaultSynthResult, fault: str, bus_id: str) -> FaultSample | None:
    rows = [
        sample
        for sample in result.samples
        if sample.fault_type == fault and sample.bus_id == bus_id
    ]
    if not rows:
        return None
    return min(rows, key=lambda sample: (sample.r_f_ohm, sample.sample_id))


def _evaluate(
    point: _BusPoint,
    fault: str,
    resistance: float,
    s_base_va: float,
    engine: str,
) -> FaultSample:
    family, steps, code, label = _FAULTS[fault]
    e_volts = point.v_ll_v / math.sqrt(3.0)
    va, vb, vc, ia, ib, ic, i_fault = _fault_phasors(
        point.z1_ohm, point.z0_ohm, resistance, family, e_volts
    )
    va, vb, vc, ia, ib, ic = _cycle(va, vb, vc, ia, ib, ic, steps)
    if family != "abc":
        i_fault = _cycled_fault_current(i_fault, ia, ib, ic, family, steps)
    v_base = e_volts
    i_base = s_base_va / (math.sqrt(3.0) * point.v_ll_v)
    va_pu = _clean(abs(va) / v_base, 1.0)
    vb_pu = _clean(abs(vb) / v_base, 1.0)
    vc_pu = _clean(abs(vc) / v_base, 1.0)
    ia_a = _clean(abs(ia), 1.0)
    ib_a = _clean(abs(ib), 1.0)
    ic_a = _clean(abs(ic), 1.0)
    i_fault_a = _clean(abs(i_fault), 1.0)
    return FaultSample(
        sample_id=0,
        bus_id=point.bus_id,
        line_id=point.line_id,
        distance_km=point.distance_km,
        fault_type=fault,
        fault_type_code=code,
        label_protect=label,
        r_f_ohm=resistance,
        v_a_pu=va_pu,
        v_b_pu=vb_pu,
        v_c_pu=vc_pu,
        v_bus_mag_pu=min(va_pu, vb_pu, vc_pu),
        i_phase_a_a=ia_a,
        i_phase_b_a=ib_a,
        i_phase_c_a=ic_a,
        i_fault_mag_a=i_fault_a,
        i_fault_mag_pu=_clean(i_fault_a / i_base, 1.0),
        engine=engine,
    )


def _fault_phasors(
    z1: complex,
    z0: complex,
    resistance: float,
    family: str,
    e_volts: complex,
) -> tuple[complex, complex, complex, complex, complex, complex, complex]:
    z2 = z1
    if family == "abc":
        den = z1 + resistance
        _nonzero(den)
        i1 = e_volts / den
        ia = i1
        ib = _A2_OP * i1
        ic = _A_OP * i1
        va = i1 * resistance
        vb = _A2_OP * va
        vc = _A_OP * va
        return va, vb, vc, ia, ib, ic, ia
    if family == "slg":
        den = z1 + z2 + z0 + 3.0 * resistance
        _nonzero(den)
        i1 = e_volts / den
        ia = 3.0 * i1
        v1 = e_volts - i1 * z1
        v2 = -i1 * z2
        v0 = -i1 * z0
        va = v0 + v1 + v2
        vb = v0 + _A2_OP * v1 + _A_OP * v2
        vc = v0 + _A_OP * v1 + _A2_OP * v2
        return va, vb, vc, ia, 0j, 0j, ia
    den = z1 + z2 + resistance
    _nonzero(den)
    i1 = e_volts / den
    i2 = -i1
    ib = _A2_OP * i1 + _A_OP * i2
    ic = _A_OP * i1 + _A2_OP * i2
    v1 = e_volts - i1 * z1
    v2 = -i2 * z2
    va = v1 + v2
    vb = _A2_OP * v1 + _A_OP * v2
    vc = _A_OP * v1 + _A2_OP * v2
    return va, vb, vc, 0j, ib, ic, ib


def _cycle(
    va: complex,
    vb: complex,
    vc: complex,
    ia: complex,
    ib: complex,
    ic: complex,
    steps: int,
) -> tuple[complex, complex, complex, complex, complex, complex]:
    volts = (va, vb, vc)
    amps = (ia, ib, ic)
    # steps=1 maps (A, B, C) onto (C, A, B): the AG pattern becomes BG.
    order = ((0, 1, 2), (2, 0, 1), (1, 2, 0))[steps]
    return (
        volts[order[0]],
        volts[order[1]],
        volts[order[2]],
        amps[order[0]],
        amps[order[1]],
        amps[order[2]],
    )


def _cycled_fault_current(
    base_current: complex,
    ia: complex,
    ib: complex,
    ic: complex,
    family: str,
    steps: int,
) -> complex:
    del base_current, steps
    if family == "slg":
        return ia + ib + ic
    return max((ia, ib, ic), key=abs)


def _nonzero(value: complex) -> None:
    if abs(value) < 1e-12:
        raise ValueError("fault impedance cancels the Thevenin impedance")


def _clean(value: float, scale: float) -> float:
    if abs(value) <= max(scale, 1.0) * 1e-9:
        return 0.0
    return float(value)


def _radial_points(
    feeder_path: Path | None,
    v_ll_v: float,
    source_factor: float,
) -> list[_BusPoint]:
    source_spec, lines = _load_feeder(feeder_path, source_factor)
    return _walk_radial(source_spec, lines, v_ll_v)


def _load_feeder(path: Path | None, source_factor: float) -> tuple[_SourceSpec, list[_LineSpec]]:
    if path is None:
        return _builtin_feeder(source_factor)
    rows = [_canonicalize(row) for row in _read_csv_rows(path)]
    sources: list[_SourceSpec] = []
    lines: list[_LineSpec] = []
    for index, raw in enumerate(rows, start=1):
        kind = _norm_key(_text(raw.get("kind"), ""))
        if kind in {"source", "grid", "extgrid", "externalgrid"}:
            sources.append(_parse_source(raw, index, source_factor))
        elif kind in {"line", "cable", "feeder", "ohl"}:
            lines.append(_parse_line(raw, index))
        elif kind == "":
            raise ValueError(f"row {index}: kind is required (source or line)")
        else:
            raise ValueError(f"row {index}: kind must be source or line")
    if len(sources) != 1:
        raise ValueError("the feeder CSV needs exactly one source row")
    if not lines:
        raise ValueError("the feeder CSV needs at least one line row")
    return sources[0], lines


def _builtin_feeder(source_factor: float) -> tuple[_SourceSpec, list[_LineSpec]]:
    z1 = _z_from_magnitude(0.4, 10.0)
    source = _SourceSpec(bus_id="B0", z1=z1, z0=source_factor * z1)
    lines = [
        _LineSpec(
            name=item["name"],
            from_bus=item["from_bus"],
            to_bus=item["to_bus"],
            length_km=item["length_km"],
            z1=complex(item["r1_ohm"], item["x1_ohm"]),
            z0=complex(item["r0_ohm"], item["x0_ohm"]),
        )
        for item in _BUILTIN_LINES
    ]
    return source, lines


def _parse_source(raw: Mapping[str, object], index: int, default_factor: float) -> _SourceSpec:
    label = _text(raw.get("name"), "") or f"source{index}"
    bus_id = _text(raw.get("from_bus"), "")
    if bus_id == "":
        raise ValueError(f"{label}: source from_bus is the bus the grid connects to")
    z1, z0 = _sequence_pair(raw, label, default_factor, source=True)
    return _SourceSpec(bus_id=bus_id, z1=z1, z0=z0)


def _parse_line(raw: Mapping[str, object], index: int) -> _LineSpec:
    name = _text(raw.get("name"), "") or f"L{index}"
    from_bus = _text(raw.get("from_bus"), "")
    to_bus = _text(raw.get("to_bus"), "")
    if from_bus == "" or to_bus == "":
        raise ValueError(f"{name}: from_bus and to_bus are required")
    if from_bus == to_bus:
        raise ValueError(f"{name}: from_bus and to_bus must differ")
    length = _optional_number("length_km", raw.get("length_km"))
    if length is None:
        length = 0.0
    if length < 0.0:
        raise ValueError(f"{name}: length_km must be >= 0")
    z1, z0 = _sequence_pair(raw, name, Z0_LINE_FACTOR, source=False)
    return _LineSpec(
        name=name,
        from_bus=from_bus,
        to_bus=to_bus,
        length_km=length,
        z1=z1,
        z0=z0,
    )


def _sequence_pair(
    raw: Mapping[str, object],
    label: str,
    default_factor: float,
    *,
    source: bool,
) -> tuple[complex, complex]:
    r1 = _optional_number("r1_ohm", raw.get("r1_ohm"))
    x1 = _optional_number("x1_ohm", raw.get("x1_ohm"))
    z_mag = _optional_number("z1_ohm", raw.get("z1_ohm"))
    x_over_r = _optional_number("x_over_r", raw.get("x_over_r"))
    explicit = r1 is not None or x1 is not None
    if explicit and z_mag is not None:
        raise ValueError(f"{label}: pass r1_ohm/x1_ohm or z1_ohm, not both")
    if explicit:
        if r1 is not None and r1 < 0.0:
            raise ValueError(f"{label}: resistance must be >= 0")
        z1 = complex(0.0 if r1 is None else r1, 0.0 if x1 is None else x1)
    elif z_mag is not None:
        if x_over_r is None:
            x_over_r = math.inf
        z1 = _z_from_magnitude(z_mag, x_over_r)
    else:
        raise ValueError(f"{label}: positive-sequence impedance is required")
    if abs(z1) <= 0.0:
        raise ValueError(f"{label}: impedance magnitude must be positive")
    r0 = _optional_number("r0_ohm", raw.get("r0_ohm"))
    x0 = _optional_number("x0_ohm", raw.get("x0_ohm"))
    factor = _optional_number("z0_factor", raw.get("z0_factor"))
    if (r0 is not None or x0 is not None) and factor is not None:
        raise ValueError(f"{label}: pass r0_ohm/x0_ohm or z0_factor, not both")
    if r0 is not None or x0 is not None:
        if r0 is not None and r0 < 0.0:
            raise ValueError(f"{label}: resistance must be >= 0")
        z0 = complex(0.0 if r0 is None else r0, 0.0 if x0 is None else x0)
    else:
        used = default_factor if factor is None else factor
        if used <= 0.0:
            raise ValueError(f"{label}: z0_factor must be a positive finite number")
        z0 = used * z1
    if abs(z0) <= 0.0:
        raise ValueError(f"{label}: zero-sequence impedance magnitude must be positive")
    del source
    return z1, z0


def _z_from_magnitude(magnitude: float, x_over_r: float) -> complex:
    if magnitude <= 0.0:
        raise ValueError("z1_ohm must be a positive finite number")
    if math.isinf(x_over_r):
        return complex(0.0, magnitude if x_over_r > 0.0 else -magnitude)
    scale = math.sqrt(1.0 + x_over_r * x_over_r)
    resistance = magnitude / scale
    return complex(resistance, resistance * x_over_r)


def _walk_radial(source: _SourceSpec, lines: list[_LineSpec], v_ll_v: float) -> list[_BusPoint]:
    by_end: dict[str, list[tuple[_LineSpec, str]]] = {}
    for line in lines:
        by_end.setdefault(line.from_bus, []).append((line, line.to_bus))
        by_end.setdefault(line.to_bus, []).append((line, line.from_bus))
    if source.bus_id not in by_end:
        raise ValueError(f"source bus {source.bus_id} is not connected to a line")
    points: dict[str, _BusPoint] = {
        source.bus_id: _BusPoint(
            bus_id=source.bus_id,
            line_id="source",
            distance_km=0.0,
            z1_ohm=source.z1,
            z0_ohm=source.z0,
            v_ll_v=v_ll_v,
            order=0,
        )
    }
    queue = deque([source.bus_id])
    seen_lines: set[int] = set()
    while queue:
        bus_id = queue.popleft()
        parent = points[bus_id]
        for line, other in by_end.get(bus_id, []):
            mark = id(line)
            if mark in seen_lines:
                continue
            seen_lines.add(mark)
            if other in points:
                raise ValueError(
                    f"{line.name}: the feeder has a loop. The zbus engine is a radial tree"
                )
            points[other] = _BusPoint(
                bus_id=other,
                line_id=line.name,
                distance_km=parent.distance_km + line.length_km,
                z1_ohm=parent.z1_ohm + line.z1,
                z0_ohm=parent.z0_ohm + line.z0,
                v_ll_v=v_ll_v,
                order=len(points),
            )
            queue.append(other)
    if len(seen_lines) != len(lines):
        raise ValueError("every line must belong to the radial tree fed by the source bus")
    return [points[key] for key in sorted(points, key=lambda key: points[key].order)]


def _pandapower_points(
    network: str,
    s_base_mva: float,
    z0_line_factor: float,
    z0_source_factor: float,
) -> list[_BusPoint]:
    try:
        import pandapower as pp
    except ImportError as exc:
        raise ImportError(
            "pandapower is not installed. Use engine='zbus', or install pandapower "
            "in the same environment"
        ) from exc
    if network == "cigre_mv":
        try:
            net = pp.networks.create_cigre_network_mv(with_der=False)
        except TypeError:
            net = pp.networks.create_cigre_network_mv()
    elif network == "radial":
        net = _teaching_radial_net(pp)
    else:
        raise ValueError("network must be 'radial' or 'cigre_mv'")
    return _points_from_pandapower_net(net, s_base_mva, z0_line_factor, z0_source_factor)


def _teaching_radial_net(pp: object) -> object:
    """Build the example feeder in pandapower so the optional engine can match zbus."""

    net = pp.create_empty_network(sn_mva=DEFAULT_S_BASE_MVA)
    buses = {
        name: pp.create_bus(net, vn_kv=DEFAULT_V_KV, name=name) for name in ("B0", "B1", "B2", "B3", "B4")
    }
    # |Z| = 0.4 ohm at 10 kV is 250 MVA, and X/R = 10 is R/X = 0.1.
    pp.create_ext_grid(
        net,
        buses["B0"],
        vm_pu=1.0,
        name="grid",
        s_sc_max_mva=250.0,
        s_sc_min_mva=250.0,
        rx_max=0.1,
        rx_min=0.1,
    )
    per_km = (
        ("L1", "B0", "B1", 1.5, 0.27, 0.35, 0.81, 1.05),
        ("L2", "B1", "B2", 1.2, 0.40, 0.37, 1.20, 1.11),
        ("L3", "B2", "B3", 0.8, 0.55, 0.38, 1.65, 1.14),
        ("L4", "B3", "B4", 0.6, 0.65, 0.40, 1.95, 1.20),
    )
    for name, left, right, length, r1, x1, r0, x0 in per_km:
        pp.create_line_from_parameters(
            net,
            buses[left],
            buses[right],
            length_km=length,
            r_ohm_per_km=r1,
            x_ohm_per_km=x1,
            c_nf_per_km=0.0,
            max_i_ka=1.0,
            r0_ohm_per_km=r0,
            x0_ohm_per_km=x0,
            c0_nf_per_km=0.0,
            g0_us_per_km=0.0,
            name=name,
        )
    return net


def _points_from_pandapower_net(
    net: object,
    s_base_mva: float,
    z0_line_factor: float,
    z0_source_factor: float,
) -> list[_BusPoint]:
    bus_ids = [int(index) for index in net.bus.index]
    names: dict[int, str] = {}
    v_ll: dict[int, float] = {}
    for bus in bus_ids:
        if not _row_in_service(net.bus.loc[bus]):
            continue
        name = _bus_name(net.bus.loc[bus], bus)
        if name in names.values():
            name = f"{name} #{bus}"
        names[bus] = name
        v_ll[bus] = _positive(f"{names[bus]} vn_kv", float(net.bus.at[bus, "vn_kv"])) * 1000.0
    if not names:
        raise ValueError("pandapower network has no in-service bus")
    open_lines, open_trafos = _open_switches(net)
    series: list[tuple[int, int, complex, complex, float, str]] = []
    for index, row in net.line.iterrows():
        if int(index) in open_lines or not _row_in_service(row):
            continue
        left = int(row.from_bus)
        right = int(row.to_bus)
        if left not in names or right not in names:
            continue
        parallel = float(row.parallel) if "parallel" in row.index else 1.0
        if not parallel > 0.0:
            raise ValueError(f"{row['name']}: parallel must be positive")
        length = float(row.length_km)
        if length < 0.0:
            raise ValueError("line length_km must be >= 0")
        z1 = complex(float(row.r_ohm_per_km) * length, float(row.x_ohm_per_km) * length) / parallel
        z0 = _line_z0(row, z1, length, parallel, z0_line_factor)
        series.append((left, right, z1, z0, length, _element_name(row, f"line{index}"), False))
    if hasattr(net, "trafo"):
        for index, row in net.trafo.iterrows():
            if int(index) in open_trafos or not _row_in_service(row):
                continue
            left = int(row.hv_bus)
            right = int(row.lv_bus)
            if left not in names or right not in names:
                continue
            z1_lv = _trafo_ohm(row, v_ll[right])
            z1_pu = z1_lv / _z_base(v_ll[right], s_base_mva)
            series.append(
                (left, right, z1_pu, z1_pu, 0.0, _element_name(row, f"trafo{index}"), True)
            )
    shunts: list[tuple[int, complex, complex]] = []
    for _, row in net.ext_grid.iterrows():
        if not _row_in_service(row):
            continue
        bus = int(row.bus)
        if bus not in names:
            continue
        if "s_sc_max_mva" not in row.index or not _is_finite_number(row.s_sc_max_mva):
            raise ValueError("ext_grid s_sc_max_mva is required for the pandapower engine")
        z1 = _ext_grid_ohm(float(row.s_sc_max_mva), float(row.rx_max), v_ll[bus])
        shunts.append((bus, z1, z0_source_factor * z1))
    if not shunts:
        raise ValueError("pandapower network needs an in-service ext_grid with s_sc_max_mva")
    return _ybus_points(names, v_ll, shunts, series, s_base_mva)


def _line_z0(
    row: object,
    z1: complex,
    length: float,
    parallel: float,
    factor: float,
) -> complex:
    has_r0 = "r0_ohm_per_km" in row.index and _is_finite_number(row.r0_ohm_per_km)
    has_x0 = "x0_ohm_per_km" in row.index and _is_finite_number(row.x0_ohm_per_km)
    if has_r0 or has_x0:
        r0 = float(row.r0_ohm_per_km) * length if has_r0 else 0.0
        x0 = float(row.x0_ohm_per_km) * length if has_x0 else 0.0
        return complex(r0, x0) / parallel
    return factor * z1


def _trafo_ohm(row: object, v_lv: float) -> complex:
    sn_mva = float(row.sn_mva)
    vk = float(row.vk_percent) / 100.0
    vkr = float(row.vkr_percent) / 100.0
    if vk <= 0.0 or sn_mva <= 0.0:
        raise ValueError("transformer vk_percent and sn_mva must be positive")
    if vkr < 0.0 or vkr > vk:
        raise ValueError("transformer vkr_percent must lie between 0 and vk_percent")
    parallel = float(row.parallel) if "parallel" in row.index else 1.0
    z_mag = vk * (v_lv * v_lv) / (sn_mva * 1e6) / parallel
    r_ohm = vkr * (v_lv * v_lv) / (sn_mva * 1e6) / parallel
    x_sq = z_mag * z_mag - r_ohm * r_ohm
    if x_sq < 0.0:
        x_sq = 0.0
    return complex(r_ohm, math.sqrt(x_sq))


def _ext_grid_ohm(s_sc_mva: float, rx: float, v_ll: float) -> complex:
    if not s_sc_mva > 0.0:
        raise ValueError("s_sc_max_mva must be a positive finite number")
    if not math.isfinite(rx) or rx < 0.0:
        raise ValueError("rx_max must be a finite number >= 0")
    z_mag = (v_ll * v_ll) / (s_sc_mva * 1e6)
    x_ohm = z_mag / math.sqrt(1.0 + rx * rx)
    return complex(rx * x_ohm, x_ohm)


def _ybus_points(
    names: dict[int, str],
    v_ll: dict[int, float],
    shunts: Sequence[tuple[int, complex, complex]],
    series: Sequence[tuple[int, int, complex, complex, float, str, bool]],
    s_base_mva: float,
) -> list[_BusPoint]:
    """Driving-point ohms from a per-unit Ybus.

    A series tuple is ``(left, right, z1, z0, length_km, name, already_pu)``.
    Lines pass ohms. Transformers pass per-unit impedance on ``s_base_mva``.
    """

    order = list(names)
    index_of = {bus: index for index, bus in enumerate(order)}
    n_bus = len(order)
    y1 = np.zeros((n_bus, n_bus), dtype=complex)
    y0 = np.zeros((n_bus, n_bus), dtype=complex)
    for bus, z1, z0 in shunts:
        _shunt_stamp(y1, index_of[bus], z1 / _z_base(v_ll[bus], s_base_mva))
        _shunt_stamp(y0, index_of[bus], z0 / _z_base(v_ll[bus], s_base_mva))
    edges: list[tuple[int, int, float, str]] = []
    for left, right, z1, z0, length, name, already_pu in series:
        if already_pu:
            z1_pu, z0_pu = z1, z0
        else:
            z1_pu = z1 / _z_base(v_ll[left], s_base_mva)
            z0_pu = z0 / _z_base(v_ll[left], s_base_mva)
        _series_stamp(y1, index_of[left], index_of[right], z1_pu)
        _series_stamp(y0, index_of[left], index_of[right], z0_pu)
        edges.append((left, right, length, name))
    zbus1 = np.linalg.inv(y1)
    zbus0 = np.linalg.inv(y0)
    distance, parent = _bfs_distance(order, edges, [bus for bus, _, _ in shunts])
    points: list[_BusPoint] = []
    for position, bus in enumerate(order):
        if not math.isfinite(distance[bus]):
            raise ValueError(f"{names[bus]} is disconnected from the external grid")
        slot = index_of[bus]
        points.append(
            _BusPoint(
                bus_id=names[bus],
                line_id=parent[bus],
                distance_km=distance[bus],
                z1_ohm=complex(zbus1[slot, slot]) * _z_base(v_ll[bus], s_base_mva),
                z0_ohm=complex(zbus0[slot, slot]) * _z_base(v_ll[bus], s_base_mva),
                v_ll_v=v_ll[bus],
                order=position,
            )
        )
    return points


def _z_base(v_ll: float, s_base_mva: float) -> float:
    return (v_ll * v_ll) / (s_base_mva * 1e6)


def _shunt_stamp(ybus: np.ndarray, index: int, z_pu: complex) -> None:
    if abs(z_pu) <= 0.0:
        raise ValueError("shunt impedance magnitude must be positive")
    ybus[index, index] += 1.0 / z_pu


def _series_stamp(ybus: np.ndarray, left: int, right: int, z_pu: complex) -> None:
    if abs(z_pu) <= 0.0:
        raise ValueError("series impedance magnitude must be positive")
    admittance = 1.0 / z_pu
    ybus[left, left] += admittance
    ybus[right, right] += admittance
    ybus[left, right] -= admittance
    ybus[right, left] -= admittance


def _bfs_distance(
    buses: Sequence[int],
    edges: Sequence[tuple[int, int, float, str]],
    roots: Sequence[int],
) -> tuple[dict[int, float], dict[int, str]]:
    adj: dict[int, list[tuple[int, float, str]]] = {bus: [] for bus in buses}
    for left, right, length, name in edges:
        adj[left].append((right, length, name))
        adj[right].append((left, length, name))
    distance = {bus: math.inf for bus in buses}
    parent = {bus: "" for bus in buses}
    queue: deque[int] = deque()
    for root in roots:
        if distance[root] == 0.0:
            continue
        distance[root] = 0.0
        parent[root] = "source"
        queue.append(root)
    while queue:
        bus = queue.popleft()
        for other, length, name in adj[bus]:
            candidate = distance[bus] + length
            if candidate + 1e-9 < distance[other]:
                distance[other] = candidate
                parent[other] = name
                queue.append(other)
    return distance, parent


def _open_switches(net: object) -> tuple[set[int], set[int]]:
    lines: set[int] = set()
    trafos: set[int] = set()
    if not hasattr(net, "switch"):
        return lines, trafos
    for _, row in net.switch.iterrows():
        if _row_in_service(row) and not bool(row.closed):
            kind = str(row.et)
            if kind == "l":
                lines.add(int(row.element))
            elif kind == "t":
                trafos.add(int(row.element))
    return lines, trafos


def _row_in_service(row: object) -> bool:
    if "in_service" not in row.index:
        return True
    return bool(row.in_service)


def _bus_name(row: object, index: int) -> str:
    if "name" not in row.index or not _is_text(row["name"]):
        return f"Bus {index}"
    return str(row["name"]).strip()


def _element_name(row: object, default: str) -> str:
    if "name" not in row.index or not _is_text(row["name"]):
        return default
    return str(row["name"]).strip()


def _is_text(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return str(value).strip() != ""


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def _reference_point(points: Sequence[_BusPoint]) -> _BusPoint:
    """Most common bus voltage. Ties keep the lower voltage, then the earlier bus."""

    counts: dict[float, int] = {}
    for point in points:
        counts[point.v_ll_v] = counts.get(point.v_ll_v, 0) + 1
    best = max(counts, key=lambda volts: (counts[volts], -volts))
    for point in points:
        if point.v_ll_v == best:
            return point
    return points[0]


def _subsample(grid: list[FaultSample], n_samples: int | None, seed: int) -> list[FaultSample]:
    if n_samples is None:
        return list(grid)
    count = _integer("n_samples", n_samples, positive=True)
    if count > len(grid):
        raise ValueError("n_samples exceeds the fault grid")
    if count == len(grid):
        return list(grid)
    state = seed % _LCG_M
    if state <= 0:
        state = 1
    order = list(range(len(grid)))
    for index in range(len(order) - 1, 0, -1):
        state = (_LCG_A * state) % _LCG_M
        swap = state % (index + 1)
        order[index], order[swap] = order[swap], order[index]
    return [grid[slot] for slot in order[:count]]


def _resolve_engine(engine: str) -> str:
    if engine == "auto":
        try:
            import pandapower  # noqa: F401
        except ImportError:
            return "zbus"
        return "pandapower"
    return engine


def _resolve_network(network: str | None, engine: str) -> str:
    if network is None:
        return "cigre_mv" if engine == "pandapower" else "radial"
    key = _norm_key(network)
    if key in {"radial", "feeder"}:
        return "radial"
    if key in {"cigremv", "cigre", "mv"}:
        return "cigre_mv"
    raise ValueError("network must be 'radial' or 'cigre_mv'")


def _resolve_feeder_path(source: object, csv_path: str | Path | None) -> Path | None:
    csv_text = None if csv_path is None or str(csv_path).strip() == "" else str(csv_path)
    if isinstance(source, (str, Path)):
        text = str(source).strip()
        if text.lower() in _PARAM_NAMES:
            raise ValueError(
                f"{text!r} is a parameter name. Pass the CSV path as csv_path= or as the first argument"
            )
        if csv_text is not None:
            raise ValueError("pass a CSV path once, either positionally or as csv_path=")
        csv_text = text
    elif source is not None:
        raise TypeError("source must be a feeder CSV path or omitted")
    if csv_text is None:
        return None
    return Path(csv_text)


def _parse_fault_types(fault_types: Sequence[str] | str | None) -> list[str]:
    if fault_types is None:
        return list(_FAULT_ORDER)
    if isinstance(fault_types, str):
        tokens = [fault_types]
    else:
        tokens = list(fault_types)
    if not tokens:
        raise ValueError("fault_types is empty")
    chosen: list[str] = []
    for token in tokens:
        key = _norm_key(token)
        name = _FAULT_ALIAS.get(key)
        if name is None:
            raise ValueError(
                "fault_types entries must be AG, BG, CG, AB, BC, CA, or ABC"
            )
        if name not in chosen:
            chosen.append(name)
    return [name for name in _FAULT_ORDER if name in chosen]


def _parse_resistances(value: Sequence[float] | float) -> list[float]:
    if isinstance(value, str) or isinstance(value, bool) or not isinstance(value, Sequence):
        numbers = [value]
    else:
        numbers = list(value)
    if not numbers:
        raise ValueError("r_fault_ohm is empty")
    parsed = [_nonnegative("r_fault_ohm", item) for item in numbers]
    return parsed


def _parse_buses(buses: Sequence[str] | str | None) -> list[str] | None:
    if buses is None:
        return None
    if isinstance(buses, str):
        tokens = [buses]
    else:
        tokens = [str(item) for item in buses]
    cleaned = []
    for token in tokens:
        text = token.strip()
        if text == "":
            raise ValueError("bus id is empty")
        if text not in cleaned:
            cleaned.append(text)
    if not cleaned:
        raise ValueError("buses is empty")
    return cleaned


def _normalize_engine(engine: object) -> str:
    key = _norm_key(engine)
    if key in {"zbus", "radial", "fallback", "numpy"}:
        return "zbus"
    if key in {"pandapower", "pp", "cigre"}:
        return "pandapower"
    if key == "auto":
        return "auto"
    raise ValueError("engine must be 'zbus', 'pandapower', or 'auto'")


def _frame(samples: Sequence[FaultSample]) -> pd.DataFrame:
    rows = [_sample_mapping(sample) for sample in samples]
    return pd.DataFrame(rows, columns=list(CSV_COLUMNS))


def _sample_mapping(sample: FaultSample) -> dict[str, object]:
    return {
        "sample_id": sample.sample_id,
        "bus_id": sample.bus_id,
        "line_id": sample.line_id,
        "distance_km": sample.distance_km,
        "fault_type": sample.fault_type,
        "fault_type_code": sample.fault_type_code,
        "label_protect": sample.label_protect,
        "R_f_ohm": sample.r_f_ohm,
        "V_a_pu": sample.v_a_pu,
        "V_b_pu": sample.v_b_pu,
        "V_c_pu": sample.v_c_pu,
        "V_bus_mag_pu": sample.v_bus_mag_pu,
        "I_phase_a_A": sample.i_phase_a_a,
        "I_phase_b_A": sample.i_phase_b_a,
        "I_phase_c_A": sample.i_phase_c_a,
        "I_fault_mag_A": sample.i_fault_mag_a,
        "I_fault_mag_pu": sample.i_fault_mag_pu,
        "engine": sample.engine,
    }


def _write_csv(path: Path, samples: Sequence[FaultSample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for sample in samples:
            mapping = _sample_mapping(sample)
            writer.writerow(
                {
                    key: mapping[key] if isinstance(mapping[key], str) else _csv_number(mapping[key])
                    for key in CSV_COLUMNS
                }
            )


def _csv_number(value: object) -> str:
    if isinstance(value, str):
        return value
    number = float(value)
    if not math.isfinite(number):
        return ""
    if float(number).is_integer() and abs(number) < 1e15:
        return str(int(number))
    return f"{number:.12g}"


def _render_figure(result: FaultSynthResult, output_png: str | None, show: bool) -> object | None:
    import matplotlib.pyplot as plt

    bolted = _bolted_rf(result)
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
        fig, axes = plt.subplots(2, 1, figsize=(10.2, 7.4), sharex=True)
        for fault, ylabel, axis in (
            ("current", "Fault current (A)", axes[0]),
            ("voltage", "Minimum phase voltage (pu)", axes[1]),
        ):
            for code in ("AG", "BC", "ABC"):
                rows = [
                    sample
                    for sample in result.samples
                    if sample.fault_type == code and sample.r_f_ohm == bolted
                ]
                rows.sort(key=lambda sample: (sample.distance_km, sample.bus_id))
                if not rows:
                    continue
                xs = [sample.distance_km for sample in rows]
                if fault == "current":
                    ys = [sample.i_fault_mag_a for sample in rows]
                else:
                    ys = [sample.v_bus_mag_pu for sample in rows]
                marker = "o"
                if result.network == "radial":
                    axis.plot(
                        xs,
                        ys,
                        marker=marker,
                        color=_CLASS_COLOR[code],
                        linewidth=2.0,
                        label=f"{code} ({_FAULTS[code][3]})",
                    )
                else:
                    axis.scatter(
                        xs,
                        ys,
                        color=_CLASS_COLOR[code],
                        s=36,
                        zorder=3,
                        label=f"{code} ({_FAULTS[code][3]})",
                    )
            axis.set_ylabel(ylabel)
            axis.grid(True, color="#d0d0d0", linewidth=0.6)
            axis.legend(loc="best", frameon=True, edgecolor="#cccccc")
        axes[0].set_title(
            f"{result.network} short-circuit samples at Rf={bolted:.4g} ohm"
        )
        axes[1].set_xlabel("Distance from source (km)")
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


def _bolted_rf(result: FaultSynthResult) -> float:
    return min(sample.r_f_ohm for sample in result.samples)


def _positive(label: str, value: object) -> float:
    number = _finite(label, value)
    if number <= 0.0:
        raise ValueError(f"{label} must be a positive finite number")
    return number


def _nonnegative(label: str, value: object) -> float:
    number = _finite(label, value)
    if number < 0.0:
        raise ValueError(f"{label} must be >= 0")
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


def _integer(label: str, value: object, *, positive: bool) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{label} must be a positive integer" if positive else f"{label} must be an integer")
    number = int(value)
    if positive and number <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return number


def _seed(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("seed must be an integer")
    return int(value)


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
