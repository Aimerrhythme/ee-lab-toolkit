"""Export a network as graph tables and a positive-sequence bus admittance matrix.

The stamp matches ``matlab/grid_to_graph_export.m``.

Series impedance is ohms referred to the from-bus. ``b_siemens`` is the total
line charging susceptance and ``g_siemens`` is the total shunt conductance,
both in siemens at the from-bus voltage. The off-nominal tap and the phase
shift sit on the from side. A transformer whose winding voltages already
match the bus ``vn_kv`` values uses ``tap = 1`` at the neutral position.

    z_base = vn_from_kv^2 / s_base_mva          (ohm)
    y_base = s_base_mva / vn_from_kv^2          (siemens)
    Ys = 1 / (r_pu + j x_pu)
    a = tap * exp(j * shift_deg * pi / 180)
    Yff = (Ys + Ysh / 2) / |a|^2
    Yft = -Ys / conj(a)
    Ytf = -Ys / a
    Ytt = Ys + Ysh / 2

``Ysh = g_pu + j b_pu`` is the total shunt of that branch. A bus shunt is
added to the diagonal only. Out-of-service branches stay in the branch table
and stay out of the adjacency matrix and ``Ybus``. Parallel in-service
branches still set one adjacency entry and sum inside ``Ybus``.

``engine='builtin'`` reads the synthetic CSV and is the MATLAB path.
``engine='pandapower'`` is Python-only. It reduces lines, two-winding
transformers, shunts, and symmetric impedance elements to the same stamp.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from numbers import Integral, Real
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

DEFAULT_S_BASE_MVA = 10.0
_DIGITS = 10
_PREVIEW_DIGITS = 4
_TOOL_DIR = Path(__file__).resolve().parents[1]
_DEFAULT_CSV = _TOOL_DIR / "examples" / "data" / "synthetic_grid.csv"

_TYPE_CODE = {"pq": 1, "pv": 2, "slack": 3}
_TYPE_ALIAS = {
    "pq": "pq",
    "load": "pq",
    "pv": "pv",
    "generator": "pv",
    "gen": "pv",
    "slack": "slack",
    "ref": "slack",
    "reference": "slack",
    "swing": "slack",
    "vtheta": "slack",
}
_KIND_ALIAS = {
    "bus": "bus",
    "node": "bus",
    "line": "line",
    "branch": "line",
    "trafo": "trafo",
    "transformer": "trafo",
    "xfmr": "trafo",
    "shunt": "shunt",
    "capacitor": "shunt",
    "reactor": "shunt",
}

NODE_COLUMNS = (
    "bus_index",
    "bus_id",
    "bus_name",
    "bus_type",
    "bus_type_code",
    "vn_kv",
    "z_base_ohm",
    "y_base_s",
    "p_mw",
    "q_mvar",
    "vm_pu",
    "va_deg",
    "p_known",
    "q_known",
    "v_known",
    "theta_known",
    "degree",
    "in_service",
    "x",
    "y",
    "members",
)
BRANCH_COLUMNS = (
    "branch_index",
    "branch_id",
    "element",
    "from_bus",
    "to_bus",
    "from_index",
    "to_index",
    "r_ohm",
    "x_ohm",
    "b_siemens",
    "g_siemens",
    "r_pu",
    "x_pu",
    "b_pu",
    "g_pu",
    "g_series",
    "b_series",
    "tap",
    "shift_deg",
    "rate_mva",
    "length_km",
    "in_service",
)
EDGE_COLUMNS = (
    "edge_index",
    "branch_id",
    "element",
    "orientation",
    "from_bus",
    "to_bus",
    "from_index",
    "to_index",
    "r_pu",
    "x_pu",
    "b_pu",
    "g_pu",
    "g_series",
    "b_series",
    "tap",
    "shift_deg",
    "rate_mva",
    "length_km",
    "y_self_g",
    "y_self_b",
    "y_mutual_g",
    "y_mutual_b",
)
SHUNT_COLUMNS = (
    "shunt_index",
    "shunt_id",
    "bus_id",
    "bus_index",
    "g_siemens",
    "b_siemens",
    "g_pu",
    "b_pu",
    "in_service",
)


@dataclass
class BusOut:
    bus_index: int
    bus_id: str
    bus_name: str
    bus_type: str
    bus_type_code: int
    vn_kv: float
    z_base_ohm: float
    y_base_s: float
    p_mw: float | None
    q_mvar: float | None
    vm_pu: float
    va_deg: float
    p_known: int
    q_known: int
    v_known: int
    theta_known: int
    degree: int
    in_service: int
    x: float | None
    y: float | None
    members: str


@dataclass
class BranchOut:
    branch_index: int
    branch_id: str
    element: str
    from_bus: str
    to_bus: str
    from_index: int | None
    to_index: int | None
    r_ohm: float
    x_ohm: float
    b_siemens: float
    g_siemens: float
    r_pu: float
    x_pu: float
    b_pu: float
    g_pu: float
    g_series: float
    b_series: float
    tap: float
    shift_deg: float
    rate_mva: float | None
    length_km: float | None
    in_service: int
    yff: complex
    yft: complex
    ytf: complex
    ytt: complex


@dataclass
class ShuntOut:
    shunt_index: int
    shunt_id: str
    bus_id: str
    bus_index: int | None
    g_siemens: float
    b_siemens: float
    g_pu: float
    b_pu: float
    in_service: int


@dataclass
class EdgeOut:
    edge_index: int
    branch_id: str
    element: str
    orientation: str
    from_bus: str
    to_bus: str
    from_index: int
    to_index: int
    r_pu: float
    x_pu: float
    b_pu: float
    g_pu: float
    g_series: float
    b_series: float
    tap: float
    shift_deg: float
    rate_mva: float | None
    length_km: float | None
    y_self_g: float
    y_self_b: float
    y_mutual_g: float
    y_mutual_b: float


@dataclass
class GraphExport:
    engine: str
    network: str
    s_base_mva: float
    self_loop: bool
    n_bus: int
    n_branch: int
    n_branch_in_service: int
    n_edge: int
    n_shunt: int
    n_shunt_in_service: int
    bus_ids: list[str]
    buses: list[BusOut]
    branches: list[BranchOut]
    shunts: list[ShuntOut]
    edges: list[EdgeOut]
    adjacency: np.ndarray
    ybus: np.ndarray
    preview: str
    summary: str
    output_dir: str
    output_png: str
    fig: object


def grid_to_graph_export(
    csv_path: str | Path | None = None,
    *,
    s_base_mva: float | None = None,
    engine: str = "builtin",
    network: str = "",
    self_loop: bool | int | str = False,
    output_dir: str | Path | None = None,
    output_png: str | Path | None = None,
    show: bool | int | str = False,
) -> GraphExport:
    """Build adjacency, node/edge tables, and Ybus for one network.

    Parameters use the same names as the MATLAB name-value pairs. The first
    positional argument is the grid CSV. Omit it to read the packaged
    synthetic 4-bus file.
    """

    engine_name = _normalize_engine(engine)
    loop = _as_bool(self_loop, "self_loop")
    show_fig = _as_bool(show, "show")
    network_name = str(network).strip()
    if engine_name == "auto":
        engine_name = _resolve_auto(csv_path, network_name)

    if engine_name == "pandapower":
        if csv_path not in (None, ""):
            raise ValueError(
                "engine 'pandapower' reads a named case. Drop the CSV path, "
                "or use engine 'builtin' for the synthetic file"
            )
        case_name = network_name if network_name and network_name.lower() != "synthetic" else "cigre_mv"
        buses, branches, shunts, base, net_name = _load_pandapower(case_name, s_base_mva)
        resolved_engine = "pandapower"
    else:
        if network_name and network_name.lower() not in {"synthetic", "builtin"}:
            raise ValueError(
                f"network {network_name!r} needs engine 'pandapower'. "
                "The builtin engine reads the synthetic CSV"
            )
        path = _resolve_csv(csv_path)
        base = DEFAULT_S_BASE_MVA if s_base_mva is None else _positive("s_base_mva", s_base_mva)
        buses, branches, shunts = _load_csv(path, base)
        net_name = "synthetic" if path.resolve() == _DEFAULT_CSV.resolve() else path.stem
        resolved_engine = "builtin"

    result = _assemble(
        buses,
        branches,
        shunts,
        s_base_mva=base,
        engine=resolved_engine,
        network=net_name,
        self_loop=loop,
    )
    out_dir = "" if output_dir in (None, "") else str(output_dir)
    out_png = "" if output_png in (None, "") else str(output_png)
    if out_dir:
        _write_bundle(Path(out_dir), result)
    fig = None
    if out_png or show_fig:
        fig = _render(result, Path(out_png) if out_png else None, show_fig)
    result.output_dir = out_dir
    result.output_png = out_png
    result.fig = fig
    return result


def format_preview(result: GraphExport) -> str:
    return result.preview


def format_table(result: GraphExport) -> str:
    lines = [result.preview, _table_header()]
    for bus in result.buses:
        g = float(result.ybus[bus.bus_index, bus.bus_index].real)
        b = float(result.ybus[bus.bus_index, bus.bus_index].imag)
        lines.append(
            f"{bus.bus_id:<6} {bus.bus_type:<6} {bus.degree:3d} "
            f"{g:10.4f} {b:10.4f} "
            f"{_fmt_opt(bus.p_mw, 10)} {_fmt_opt(bus.q_mvar, 10)} "
            f"{bus.vm_pu:8.4f} {bus.va_deg:8.4f}  {_known_text(bus)}"
        )
    return "\n".join(lines)


def branch_stamp(
    r_pu: float,
    x_pu: float,
    g_pu: float,
    b_pu: float,
    tap: float,
    shift_deg: float,
) -> tuple[complex, complex, complex, complex, complex]:
    """Return ``Yff, Yft, Ytf, Ytt, Ys`` for one pi branch."""

    if tap <= 0.0 or not math.isfinite(tap):
        raise ValueError("tap must be positive")
    if not all(math.isfinite(v) for v in (r_pu, x_pu, g_pu, b_pu, shift_deg)):
        raise ValueError("branch pi parameters must be finite")
    series = complex(r_pu, x_pu)
    if series == 0:
        raise ValueError("zero series impedance")
    ys = 1.0 / series
    angle = math.radians(shift_deg)
    a = complex(tap * math.cos(angle), tap * math.sin(angle))
    ysh = complex(g_pu, b_pu)
    yff = (ys + ysh / 2.0) / (tap * tap)
    yft = -ys / a.conjugate()
    ytf = -ys / a
    ytt = ys + ysh / 2.0
    return yff, yft, ytf, ytt, ys


def transformer_pi_pu(
    *,
    vk_percent: float,
    vkr_percent: float,
    sn_mva: float,
    s_base_mva: float,
    vn_hv_kv: float,
    vn_lv_kv: float,
    bus_hv_kv: float,
    bus_lv_kv: float,
    tap_pos: float = 0.0,
    tap_neutral: float = 0.0,
    tap_step_percent: float = 0.0,
    tap_step_degree: float = 0.0,
    tap_side: str = "hv",
    tap_phase_shifter: bool = False,
    shift_degree: float = 0.0,
    pfe_kw: float = 0.0,
    i0_percent: float = 0.0,
    parallel: float = 1.0,
) -> dict[str, float]:
    """Two-winding pi data on ``s_base_mva``, tap on the HV side.

    This is the classroom reduction of pandapower's positive-sequence
    transformer: ``vk`` / ``vkr`` become series ``r_pu`` and ``x_pu``, the
    off-nominal step and the winding-to-bus voltage ratio become ``tap``,
    and iron loss plus magnetizing current become a total shunt ``g_pu``,
    ``b_pu`` (positive ``b_pu`` is capacitive).
    """

    if parallel <= 0.0 or not math.isfinite(parallel):
        raise ValueError("transformer parallel must be positive")
    if sn_mva <= 0.0 or s_base_mva <= 0.0:
        raise ValueError("transformer ratings must be positive")
    if min(vn_hv_kv, vn_lv_kv, bus_hv_kv, bus_lv_kv) <= 0.0:
        raise ValueError("transformer voltages must be positive")
    side = str(tap_side).strip().lower() or "hv"
    if side not in {"hv", "lv"}:
        raise ValueError("tap_side must be 'hv' or 'lv'")
    vn_hv = float(vn_hv_kv)
    vn_lv = float(vn_lv_kv)
    shift = float(shift_degree)
    diff = float(tap_pos) - float(tap_neutral)
    step_percent = 0.0 if tap_step_percent is None else float(tap_step_percent)
    step_degree = 0.0 if tap_step_degree is None else float(tap_step_degree)
    if tap_phase_shifter:
        if step_degree != 0.0 and step_percent != 0.0:
            raise ValueError("phase shifter sets tap_step_degree or tap_step_percent, not both")
        direction = 1.0 if side == "hv" else -1.0
        if step_degree != 0.0:
            shift += direction * diff * step_degree
        else:
            arg = diff * step_percent / 100.0 / 2.0
            if abs(arg) > 1.0:
                raise ValueError("phase-shifter tap step is outside asin domain")
            shift += direction * 2.0 * math.degrees(math.asin(arg))
    else:
        fraction = diff * step_percent / 100.0
        if side == "hv":
            vn_hv, extra = _apply_tap_step(vn_hv, fraction, step_degree, 1.0)
        else:
            vn_lv, extra = _apply_tap_step(vn_lv, fraction, step_degree, -1.0)
        shift += extra

    ratio = (vn_hv / vn_lv) / (bus_hv_kv / bus_lv_kv)
    if ratio <= 0.0 or not math.isfinite(ratio):
        raise ValueError("transformer tap must be positive")
    tap_lv = (vn_lv / bus_lv_kv) ** 2 * s_base_mva
    z_sc = (vk_percent / 100.0) / sn_mva * tap_lv
    r_sc = (vkr_percent / 100.0) / sn_mva * tap_lv
    disc = z_sc * z_sc - r_sc * r_sc
    if disc < -1e-9:
        raise ValueError("vkr_percent cannot exceed vk_percent")
    x_sc = math.copysign(math.sqrt(max(disc, 0.0)), z_sc)
    r_pu = r_sc / parallel
    x_pu = x_sc / parallel

    base_r = (bus_lv_kv ** 2) / s_base_mva
    pfe_mw = pfe_kw * 1e-3
    b_real = pfe_mw / (vn_lv_kv ** 2) * base_r
    b_img_sq = (i0_percent / 100.0 * sn_mva) ** 2 - pfe_mw ** 2
    b_img = math.sqrt(max(b_img_sq, 0.0)) * base_r / (vn_lv_kv ** 2)
    sign_i0 = 0.0 if i0_percent == 0.0 else math.copysign(1.0, i0_percent)
    y_encoded = complex(-b_real, 0.0) * 1j - b_img * sign_i0
    # y_encoded is pandapower's BR_B. makeYbus multiplies it by j.
    y_encoded = y_encoded / ((vn_lv / vn_lv_kv) ** 2) * parallel
    ysh = 1j * y_encoded
    return {
        "r_pu": r_pu,
        "x_pu": x_pu,
        "g_pu": float(ysh.real),
        "b_pu": float(ysh.imag),
        "tap": ratio,
        "shift_deg": shift,
    }


def _apply_tap_step(voltage: float, fraction: float, step_degree: float, direction: float) -> tuple[float, float]:
    du = voltage * fraction
    angle = math.radians(step_degree)
    adjusted = math.hypot(voltage + du * math.cos(angle), du * math.sin(angle))
    denom = voltage + du * math.cos(angle)
    extra = 0.0 if adjusted == 0.0 else math.degrees(math.atan2(direction * du * math.sin(angle), denom))
    return adjusted, extra


def _assemble(buses_in, branches_in, shunts_in, *, s_base_mva, engine, network, self_loop) -> GraphExport:
    if s_base_mva <= 0.0 or not math.isfinite(s_base_mva):
        raise ValueError("s_base_mva must be positive")
    kept = [bus for bus in buses_in if bus["in_service"]]
    if not kept:
        raise ValueError("no in-service bus")
    seen: set[str] = set()
    for bus in buses_in:
        if bus["bus_id"] in seen:
            raise ValueError(f"duplicate bus_id {bus['bus_id']}")
        seen.add(bus["bus_id"])
    index = {bus["bus_id"]: i for i, bus in enumerate(kept)}
    known = {bus["bus_id"]: bus for bus in buses_in}

    solved_branches: list[BranchOut] = []
    seen_branch: set[str] = set()
    for raw in branches_in:
        if raw["branch_id"] in seen_branch:
            raise ValueError(f"duplicate branch_id {raw['branch_id']}")
        seen_branch.add(raw["branch_id"])
        solved_branches.append(_solve_branch(raw, known, index, s_base_mva))
    for position, branch in enumerate(solved_branches):
        branch.branch_index = position

    solved_shunts: list[ShuntOut] = []
    seen_shunt: set[str] = set()
    for raw in shunts_in:
        if raw["shunt_id"] in seen_shunt:
            raise ValueError(f"duplicate shunt_id {raw['shunt_id']}")
        seen_shunt.add(raw["shunt_id"])
        solved_shunts.append(_solve_shunt(raw, known, index, s_base_mva))
    for position, shunt in enumerate(solved_shunts):
        shunt.shunt_index = position

    n_bus = len(kept)
    adjacency = np.zeros((n_bus, n_bus), dtype=int)
    ybus = np.zeros((n_bus, n_bus), dtype=complex)
    edges: list[EdgeOut] = []
    for branch in solved_branches:
        if not branch.in_service:
            continue
        i = branch.from_index
        j = branch.to_index
        assert i is not None and j is not None
        adjacency[i, j] = 1
        adjacency[j, i] = 1
        ybus[i, i] += branch.yff
        ybus[i, j] += branch.yft
        ybus[j, i] += branch.ytf
        ybus[j, j] += branch.ytt
        edges.append(_edge_from(branch, "forward", i, j, branch.yff, branch.yft, len(edges)))
        edges.append(_edge_from(branch, "reverse", j, i, branch.ytt, branch.ytf, len(edges)))
    for shunt in solved_shunts:
        if shunt.in_service and shunt.bus_index is not None:
            ybus[shunt.bus_index, shunt.bus_index] += complex(shunt.g_pu, shunt.b_pu)
    if self_loop:
        np.fill_diagonal(adjacency, 1)

    buses: list[BusOut] = []
    for bus in kept:
        i = index[bus["bus_id"]]
        z_base, y_base = _bases(bus["vn_kv"], s_base_mva)
        degree = int(adjacency[i].sum() - adjacency[i, i])
        masks = _masks(bus)
        buses.append(
            BusOut(
                bus_index=i,
                bus_id=bus["bus_id"],
                bus_name=bus["bus_name"],
                bus_type=bus["bus_type"],
                bus_type_code=_TYPE_CODE[bus["bus_type"]],
                vn_kv=bus["vn_kv"],
                z_base_ohm=z_base,
                y_base_s=y_base,
                p_mw=bus["p_mw"],
                q_mvar=bus["q_mvar"],
                vm_pu=bus["vm_pu"],
                va_deg=bus["va_deg"],
                p_known=masks[0],
                q_known=masks[1],
                v_known=masks[2],
                theta_known=masks[3],
                degree=degree,
                in_service=1,
                x=bus["x"],
                y=bus["y"],
                members=bus["members"],
            )
        )

    n_in = sum(1 for branch in solved_branches if branch.in_service)
    n_shunt_in = sum(1 for shunt in solved_shunts if shunt.in_service)
    preview = _preview_line(
        engine=engine,
        network=network,
        buses=buses,
        branches=solved_branches,
        n_branch=len(solved_branches),
        n_in=n_in,
        n_edge=len(edges),
        n_shunt_in=n_shunt_in,
        self_loop=self_loop,
        adjacency=adjacency,
        ybus=ybus,
    )
    result = GraphExport(
        engine=engine,
        network=network,
        s_base_mva=float(s_base_mva),
        self_loop=bool(self_loop),
        n_bus=n_bus,
        n_branch=len(solved_branches),
        n_branch_in_service=n_in,
        n_edge=len(edges),
        n_shunt=len(solved_shunts),
        n_shunt_in_service=n_shunt_in,
        bus_ids=[bus.bus_id for bus in buses],
        buses=buses,
        branches=solved_branches,
        shunts=solved_shunts,
        edges=edges,
        adjacency=adjacency,
        ybus=ybus,
        preview=preview,
        summary="",
        output_dir="",
        output_png="",
        fig=None,
    )
    result.summary = format_table(result)
    return result


def _preview_line(*, engine, network, buses, branches, n_branch, n_in, n_edge, n_shunt_in, self_loop, adjacency, ybus) -> str:
    ids = [bus.bus_id for bus in buses]
    y00 = _fmt_jb(ybus[0, 0])
    best_i = None
    best_j = None
    best_mag = -1.0
    n_bus = len(ids)
    for i in range(n_bus):
        for j in range(n_bus):
            if i == j:
                continue
            mag = abs(ybus[i, j])
            if mag > best_mag:
                best_mag = mag
                best_i, best_j = i, j
    if best_i is None:
        off_text = "off=none"
    else:
        off_text = f"off[{ids[best_i]},{ids[best_j]}]={_fmt_jb(ybus[best_i, best_j])}"
    tap_text = "tap=none"
    for branch in branches:
        if not branch.in_service:
            continue
        if abs(branch.tap - 1.0) > 1e-9 or abs(branch.shift_deg) > 1e-9:
            tap_text = (
                f"tap[{branch.branch_id}]={branch.tap:.4f} "
                f"Yfrom[{branch.from_bus}]={_fmt_jb(branch.yff)} "
                f"Yto[{branch.to_bus}]={_fmt_jb(branch.ytt)}"
            )
            break
    open_names = [branch.branch_id for branch in branches if not branch.in_service]
    open_text = ",".join(open_names) if open_names else "none"
    symmetric = 1 if np.array_equal(adjacency, adjacency.T) else 0
    return (
        f"grid-to-graph-export: engine={engine} network={network} buses={n_bus} "
        f"branches={n_branch} in_service={n_in} directed={n_edge} shunts={n_shunt_in} "
        f"self_loop={int(bool(self_loop))} Y[{ids[0]},{ids[0]}]={y00} {off_text} "
        f"{tap_text} open={open_text} adj_sym={symmetric}"
    )


def _solve_branch(raw: dict, known: dict, index: dict, s_base: float) -> BranchOut:
    from_id = raw["from_bus"]
    to_id = raw["to_bus"]
    label = raw["branch_id"]
    if from_id not in known:
        raise ValueError(f"branch {label} references unknown bus {from_id}")
    if to_id not in known:
        raise ValueError(f"branch {label} references unknown bus {to_id}")
    if from_id == to_id:
        raise ValueError(f"branch {label} connects {from_id} to itself")
    from_bus = known[from_id]
    _positive(f"{label} vn_kv", from_bus["vn_kv"])
    z_base, y_base = _bases(from_bus["vn_kv"], s_base)
    r_pu, x_pu, g_pu, b_pu, r_ohm, x_ohm, g_s, b_s = _branch_pu(raw, z_base, y_base, label)
    tap = 1.0 if raw["tap"] is None else float(raw["tap"])
    shift = 0.0 if raw["shift_deg"] is None else float(raw["shift_deg"])
    in_graph = bool(raw["in_service"]) and from_id in index and to_id in index
    yff = yft = ytf = ytt = ys = 0j
    try:
        yff, yft, ytf, ytt, ys = branch_stamp(r_pu, x_pu, g_pu, b_pu, tap, shift)
    except ValueError as exc:
        message = str(exc)
        if in_graph or "tap must" in message:
            raise ValueError(f"branch {label}: {message}") from exc
    return BranchOut(
        branch_index=0,
        branch_id=label,
        element=raw["element"],
        from_bus=from_id,
        to_bus=to_id,
        from_index=index.get(from_id),
        to_index=index.get(to_id),
        r_ohm=r_ohm,
        x_ohm=x_ohm,
        b_siemens=b_s,
        g_siemens=g_s,
        r_pu=r_pu,
        x_pu=x_pu,
        b_pu=b_pu,
        g_pu=g_pu,
        g_series=float(ys.real),
        b_series=float(ys.imag),
        tap=tap,
        shift_deg=shift,
        rate_mva=raw["rate_mva"],
        length_km=raw["length_km"],
        in_service=int(in_graph),
        yff=yff,
        yft=yft,
        ytf=ytf,
        ytt=ytt,
    )


def _branch_pu(raw: dict, z_base: float, y_base: float, label: str):
    has_pu = raw["r_pu"] is not None or raw["x_pu"] is not None
    has_ohm = raw["r_ohm"] is not None or raw["x_ohm"] is not None
    if has_pu and has_ohm:
        raise ValueError(f"branch {label} sets both ohm and pu series impedance")
    if has_pu:
        if raw["r_pu"] is None or raw["x_pu"] is None:
            raise ValueError(f"branch {label} needs both r_pu and x_pu")
        r_pu = float(raw["r_pu"])
        x_pu = float(raw["x_pu"])
        g_pu = 0.0 if raw["g_pu"] is None else float(raw["g_pu"])
        b_pu = 0.0 if raw["b_pu"] is None else float(raw["b_pu"])
        if raw["g_siemens"] is not None or raw["b_siemens"] is not None:
            raise ValueError(f"branch {label} sets both siemens and pu shunt values")
        return (
            r_pu,
            x_pu,
            g_pu,
            b_pu,
            r_pu * z_base,
            x_pu * z_base,
            g_pu * y_base,
            b_pu * y_base,
        )
    if not has_ohm:
        raise ValueError(f"branch {label} needs r_ohm and x_ohm, or r_pu and x_pu")
    r_ohm = 0.0 if raw["r_ohm"] is None else float(raw["r_ohm"])
    x_ohm = 0.0 if raw["x_ohm"] is None else float(raw["x_ohm"])
    g_s = 0.0 if raw["g_siemens"] is None else float(raw["g_siemens"])
    b_s = 0.0 if raw["b_siemens"] is None else float(raw["b_siemens"])
    if raw["g_pu"] is not None or raw["b_pu"] is not None:
        raise ValueError(f"branch {label} sets both siemens and pu shunt values")
    return r_ohm / z_base, x_ohm / z_base, g_s / y_base, b_s / y_base, r_ohm, x_ohm, g_s, b_s


def _solve_shunt(raw: dict, known: dict, index: dict, s_base: float) -> ShuntOut:
    bus_id = raw["bus_id"]
    label = raw["shunt_id"]
    if bus_id not in known:
        raise ValueError(f"shunt {label} references unknown bus {bus_id}")
    bus = known[bus_id]
    _positive(f"{label} vn_kv", bus["vn_kv"])
    _z, y_base = _bases(bus["vn_kv"], s_base)
    has_pu = raw["g_pu"] is not None or raw["b_pu"] is not None
    has_s = raw["g_siemens"] is not None or raw["b_siemens"] is not None
    if has_pu and has_s:
        raise ValueError(f"shunt {label} sets both siemens and pu values")
    if not has_pu and not has_s:
        raise ValueError(f"shunt {label} needs g_siemens or b_siemens")
    if has_pu:
        g_pu = 0.0 if raw["g_pu"] is None else float(raw["g_pu"])
        b_pu = 0.0 if raw["b_pu"] is None else float(raw["b_pu"])
        g_s = g_pu * y_base
        b_s = b_pu * y_base
    else:
        g_s = 0.0 if raw["g_siemens"] is None else float(raw["g_siemens"])
        b_s = 0.0 if raw["b_siemens"] is None else float(raw["b_siemens"])
        g_pu = g_s / y_base
        b_pu = b_s / y_base
    in_graph = bool(raw["in_service"]) and bus_id in index
    return ShuntOut(
        shunt_index=0,
        shunt_id=label,
        bus_id=bus_id,
        bus_index=index.get(bus_id),
        g_siemens=g_s,
        b_siemens=b_s,
        g_pu=g_pu,
        b_pu=b_pu,
        in_service=int(in_graph),
    )


def _edge_from(branch: BranchOut, orientation: str, i: int, j: int, y_self: complex, y_mutual: complex, edge_index: int) -> EdgeOut:
    return EdgeOut(
        edge_index=edge_index,
        branch_id=branch.branch_id,
        element=branch.element,
        orientation=orientation,
        from_bus=branch.from_bus if orientation == "forward" else branch.to_bus,
        to_bus=branch.to_bus if orientation == "forward" else branch.from_bus,
        from_index=i,
        to_index=j,
        r_pu=branch.r_pu,
        x_pu=branch.x_pu,
        b_pu=branch.b_pu,
        g_pu=branch.g_pu,
        g_series=branch.g_series,
        b_series=branch.b_series,
        tap=branch.tap,
        shift_deg=branch.shift_deg,
        rate_mva=branch.rate_mva,
        length_km=branch.length_km,
        y_self_g=float(y_self.real),
        y_self_b=float(y_self.imag),
        y_mutual_g=float(y_mutual.real),
        y_mutual_b=float(y_mutual.imag),
    )


def _masks(bus: dict) -> tuple[int, int, int, int]:
    if all(bus[key] is not None for key in ("p_known", "q_known", "v_known", "theta_known")):
        return (
            int(bus["p_known"]),
            int(bus["q_known"]),
            int(bus["v_known"]),
            int(bus["theta_known"]),
        )
    kind = bus["bus_type"]
    if kind == "slack":
        return 0, 0, 1, 1
    if kind == "pv":
        return 1, 0, 1, 0
    return 1, 1, 0, 0


def _load_csv(path: Path, s_base: float) -> tuple[list[dict], list[dict], list[dict]]:
    if not path.is_file():
        raise ValueError(f"grid CSV not found: {path}")
    _positive("s_base_mva", s_base)
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header")
        fields = {_norm_key(name): name for name in reader.fieldnames if name}
        buses: list[dict] = []
        branches: list[dict] = []
        shunts: list[dict] = []
        for line_no, raw in enumerate(reader, start=2):
            if raw is None or all(_blank(value) for value in raw.values()):
                continue
            kind_text = _cell(raw, fields, "kind")
            kind = _KIND_ALIAS.get(kind_text.strip().lower(), "")
            if not kind:
                raise ValueError(f"row {line_no}: kind must be bus, line, trafo, or shunt")
            name = _cell(raw, fields, "name")
            if kind == "bus":
                buses.append(_parse_bus_row(raw, fields, name, line_no))
            elif kind == "shunt":
                shunts.append(_parse_shunt_row(raw, fields, name, line_no, len(shunts) + 1))
            else:
                branches.append(_parse_branch_row(raw, fields, name, kind, line_no, len(branches) + 1))
    if not buses:
        raise ValueError(f"{path} has no bus rows")
    return buses, branches, shunts


def _parse_bus_row(raw, fields, name, line_no) -> dict:
    bus_id = _cell(raw, fields, "bus_id")
    if _blank(bus_id):
        raise ValueError(f"row {line_no}: bus_id is required")
    bus_type = _TYPE_ALIAS.get(_cell(raw, fields, "bus_type").strip().lower(), "")
    if not bus_type:
        raise ValueError(f"row {line_no}: bus_type must be slack, pv, or pq")
    vn = _require_float(raw, fields, "vn_kv", line_no)
    if vn <= 0.0:
        raise ValueError(f"row {line_no}: vn_kv must be positive")
    p_mw = _optional_float(raw, fields, "p_mw", line_no)
    q_mvar = _optional_float(raw, fields, "q_mvar", line_no)
    vm = _optional_float(raw, fields, "vm_pu", line_no)
    va = _optional_float(raw, fields, "va_deg", line_no)
    if bus_type == "slack":
        if vm is None or va is None:
            raise ValueError(f"row {line_no}: slack bus needs vm_pu and va_deg")
    elif bus_type == "pv":
        if p_mw is None or vm is None:
            raise ValueError(f"row {line_no}: pv bus needs p_mw and vm_pu")
        if va is None:
            va = 0.0
    else:
        if p_mw is None or q_mvar is None:
            raise ValueError(f"row {line_no}: pq bus needs p_mw and q_mvar")
        if vm is None:
            vm = 1.0
        if va is None:
            va = 0.0
    in_service = _flag(_cell(raw, fields, "in_service"), line_no, default=True)
    return {
        "bus_id": bus_id.strip(),
        "bus_name": bus_id.strip() if _blank(name) else name.strip(),
        "bus_type": bus_type,
        "vn_kv": vn,
        "p_mw": p_mw,
        "q_mvar": q_mvar,
        "vm_pu": vm,
        "va_deg": va,
        "p_known": None,
        "q_known": None,
        "v_known": None,
        "theta_known": None,
        "in_service": int(in_service),
        "x": _optional_float(raw, fields, "x", line_no),
        "y": _optional_float(raw, fields, "y", line_no),
        "members": bus_id.strip(),
    }


def _parse_branch_row(raw, fields, name, kind, line_no, ordinal) -> dict:
    from_bus = _cell(raw, fields, "from_bus").strip()
    to_bus = _cell(raw, fields, "to_bus").strip()
    if not from_bus or not to_bus:
        raise ValueError(f"row {line_no}: from_bus and to_bus are required")
    branch_id = f"branch_{ordinal}" if _blank(name) else name.strip()
    length = _optional_float(raw, fields, "length_km", line_no)
    rate = _optional_float(raw, fields, "rate_mva", line_no)
    if length is not None and length < 0.0:
        raise ValueError(f"row {line_no}: length_km cannot be negative")
    if rate is not None and rate < 0.0:
        raise ValueError(f"row {line_no}: rate_mva cannot be negative")
    return {
        "branch_id": branch_id,
        "element": kind,
        "from_bus": from_bus,
        "to_bus": to_bus,
        "r_ohm": _optional_float(raw, fields, "r_ohm", line_no),
        "x_ohm": _optional_float(raw, fields, "x_ohm", line_no),
        "b_siemens": _optional_float(raw, fields, "b_siemens", line_no),
        "g_siemens": _optional_float(raw, fields, "g_siemens", line_no),
        "r_pu": _optional_float(raw, fields, "r_pu", line_no),
        "x_pu": _optional_float(raw, fields, "x_pu", line_no),
        "b_pu": _optional_float(raw, fields, "b_pu", line_no),
        "g_pu": _optional_float(raw, fields, "g_pu", line_no),
        "tap": _optional_float(raw, fields, "tap", line_no),
        "shift_deg": _optional_float(raw, fields, "shift_deg", line_no),
        "rate_mva": rate,
        "length_km": length,
        "in_service": int(_flag(_cell(raw, fields, "in_service"), line_no, default=True)),
    }


def _parse_shunt_row(raw, fields, name, line_no, ordinal) -> dict:
    bus_id = _cell(raw, fields, "bus_id").strip()
    if not bus_id:
        raise ValueError(f"row {line_no}: shunt bus_id is required")
    return {
        "shunt_id": f"shunt_{ordinal}" if _blank(name) else name.strip(),
        "bus_id": bus_id,
        "g_siemens": _optional_float(raw, fields, "g_siemens", line_no),
        "b_siemens": _optional_float(raw, fields, "b_siemens", line_no),
        "g_pu": _optional_float(raw, fields, "g_pu", line_no),
        "b_pu": _optional_float(raw, fields, "b_pu", line_no),
        "in_service": int(_flag(_cell(raw, fields, "in_service"), line_no, default=True)),
    }


def _load_pandapower(network: str, s_base_override: float | None):
    try:
        import pandapower.networks as pn  # type: ignore
    except ImportError as exc:
        raise ValueError(
            "engine 'pandapower' needs the optional pandapower package. "
            "Install it with pip install pandapower. The builtin engine matches MATLAB."
        ) from exc
    net, net_name = _call_pandapower_case(pn, network)
    if s_base_override is None:
        base = float(net.sn_mva)
    else:
        base = _positive("s_base_mva", s_base_override)
    _refuse_unsupported(net)
    buses, branches, shunts = _rows_from_pandapower(net, base)
    return buses, branches, shunts, base, net_name


def _call_pandapower_case(pn, network: str):
    key = network.strip().lower().replace("-", "_")
    aliases = {
        "cigre": "cigre_mv",
        "cigre_mv": "cigre_mv",
        "ieee9": "case9",
        "ieee14": "case14",
        "ieee30": "case30",
        "ieee118": "case118",
        "oberrhein": "mv_oberrhein",
    }
    key = aliases.get(key, key)
    if key == "cigre_mv":
        fn = getattr(pn, "create_cigre_network_mv", None)
        if fn is None:
            from pandapower.networks.cigre_networks import create_cigre_network_mv as fn
        try:
            return fn(with_der=False), "cigre_mv"
        except TypeError:
            return fn(), "cigre_mv"
    if key == "mv_oberrhein":
        return pn.mv_oberrhein(), "mv_oberrhein"
    fn = getattr(pn, key, None)
    if not callable(fn):
        raise ValueError(
            f"unknown pandapower network {network!r}. "
            "Examples: cigre_mv, case14, case9, case30, case118"
        )
    return fn(), key


def _refuse_unsupported(net) -> None:
    blocked = (
        ("trafo3w", "three-winding transformers"),
        ("dcline", "DC lines"),
        ("tcsc", "TCSC branches"),
        ("xward", "extended ward equivalents"),
        ("motor", "motors"),
        ("svc", "SVCs"),
        ("ssc", "SSCs"),
        ("asymmetric_load", "asymmetric loads"),
        ("asymmetric_sgen", "asymmetric static generators"),
    )
    for key, label in blocked:
        frame = getattr(net, key, None)
        if frame is not None and _any_in_service(frame):
            raise ValueError(
                f"pandapower network has in-service {label}; this teaching export does not expand them"
            )
    trafo = getattr(net, "trafo", None)
    if trafo is not None and len(trafo) and "tap_dependent_impedance" in trafo.columns:
        flags = trafo["tap_dependent_impedance"]
        if flags.fillna(False).astype(bool).any():
            raise ValueError("tap-dependent impedance is not exported")


def _rows_from_pandapower(net, s_base: float):
    f_hz = float(getattr(net, "f_hz", 50.0) or 50.0)
    bus_index = list(net.bus.index)
    in_service = [idx for idx in bus_index if _frame_flag(net.bus, idx, "in_service", True)]
    labels = _unique_bus_labels(net, bus_index)
    links = []
    open_lines: set[int] = set()
    open_trafos: set[int] = set()
    switches = getattr(net, "switch", None)
    if switches is not None and len(switches):
        for idx, sw in switches.iterrows():
            et = str(sw["et"])
            closed = bool(sw["closed"])
            element = int(sw["element"])
            bus = int(sw["bus"])
            if et == "l" and not closed:
                open_lines.add(element)
            elif et == "t" and not closed:
                open_trafos.add(element)
            elif et == "b" and closed and bus in in_service and element in in_service:
                links.append((bus, element))
    rep = _fuse(in_service, links)
    vn = {idx: float(net.bus.at[idx, "vn_kv"]) for idx in in_service}
    for idx, root in rep.items():
        if abs(vn[idx] - vn[root]) > 1e-6:
            raise ValueError("closed bus-bus switch joins different vn_kv; this export does not fuse them")
    reps = sorted(set(rep.values()))
    members: dict[int, list[int]] = {root: [] for root in reps}
    for idx, root in rep.items():
        members[root].append(idx)
    for root in members:
        members[root].sort()

    p_acc = {root: 0.0 for root in reps}
    q_acc = {root: 0.0 for root in reps}
    touched_p: set[int] = set()
    touched_q: set[int] = set()
    _accumulate_injections(net, rep, p_acc, q_acc, touched_p, touched_q)

    types = {root: "pq" for root in reps}
    vm = {root: 1.0 for root in reps}
    va = {root: 0.0 for root in reps}
    gen = getattr(net, "gen", None)
    if gen is not None and len(gen):
        for idx, row in gen.iterrows():
            if not _series_flag(row, "in_service", True):
                continue
            bus = int(row["bus"])
            if bus not in rep:
                continue
            root = rep[bus]
            if types[root] == "pq":
                types[root] = "pv"
                vm[root] = float(row["vm_pu"])
            _add(p_acc, touched_p, root, _scaled(row, "p_mw"))
    ext = getattr(net, "ext_grid", None)
    if ext is not None and len(ext):
        ordered = []
        for idx, row in ext.iterrows():
            if not _series_flag(row, "in_service", True):
                continue
            bus = int(row["bus"])
            if bus not in rep:
                continue
            ordered.append((rep[bus], idx, row))
        ordered.sort(key=lambda item: (item[0], item[1]))
        seen_root: set[int] = set()
        for root, _idx, row in ordered:
            if root in seen_root:
                continue
            seen_root.add(root)
            types[root] = "slack"
            vm[root] = float(row["vm_pu"])
            va[root] = float(row["va_degree"]) if "va_degree" in row.index and not _missing(row["va_degree"]) else 0.0

    buses = []
    for root in reps:
        kind = types[root]
        if kind == "slack":
            p_mw = p_acc[root] if root in touched_p else None
            q_mvar = q_acc[root] if root in touched_q else None
        elif kind == "pv":
            p_mw = p_acc[root]
            q_mvar = None
        else:
            p_mw = p_acc[root]
            q_mvar = q_acc[root]
        x_pos, y_pos = _bus_xy(net, root)
        buses.append(
            {
                "bus_id": labels[root],
                "bus_name": labels[root],
                "bus_type": kind,
                "vn_kv": vn[root],
                "p_mw": p_mw,
                "q_mvar": q_mvar,
                "vm_pu": vm[root],
                "va_deg": va[root],
                "p_known": None,
                "q_known": None,
                "v_known": None,
                "theta_known": None,
                "in_service": 1,
                "x": x_pos,
                "y": y_pos,
                "members": ";".join(labels[idx] for idx in members[root]),
            }
        )

    used_names: set[str] = set()
    branches = []
    lines = getattr(net, "line", None)
    if lines is not None and len(lines):
        for idx, row in lines.iterrows():
            branch = _line_branch(net, row, idx, rep, labels, f_hz, open_lines, used_names)
            if branch is not None:
                branches.append(branch)
    trafos = getattr(net, "trafo", None)
    if trafos is not None and len(trafos):
        for idx, row in trafos.iterrows():
            branch = _trafo_branch(net, row, idx, rep, labels, vn, s_base, open_trafos, used_names)
            if branch is not None:
                branches.append(branch)
    impedances = getattr(net, "impedance", None)
    if impedances is not None and len(impedances):
        for idx, row in impedances.iterrows():
            branch = _impedance_branch(row, idx, rep, labels, s_base, used_names)
            if branch is not None:
                branches.append(branch)

    shunts = []
    shunt_frame = getattr(net, "shunt", None)
    if shunt_frame is not None and len(shunt_frame):
        for idx, row in shunt_frame.iterrows():
            item = _shunt_branch(net, row, idx, rep, labels, vn, s_base, used_names)
            if item is not None:
                shunts.append(item)
    wards = getattr(net, "ward", None)
    if wards is not None and len(wards):
        for idx, row in wards.iterrows():
            if not _series_flag(row, "in_service", True):
                continue
            bus = int(row["bus"])
            if bus not in rep:
                continue
            # pz/qz are constant-impedance MW/MVAr. GS = pz, BS = -qz on the system base.
            g_pu = float(row["pz_mw"]) / s_base
            b_pu = -float(row["qz_mvar"]) / s_base
            if g_pu == 0.0 and b_pu == 0.0:
                continue
            shunts.append(
                {
                    "shunt_id": _take_name(used_names, f"ward_{idx}", idx),
                    "bus_id": labels[rep[bus]],
                    "g_siemens": None,
                    "b_siemens": None,
                    "g_pu": g_pu,
                    "b_pu": b_pu,
                    "in_service": 1,
                }
            )
    return buses, branches, shunts


def _accumulate_injections(net, rep, p_acc, q_acc, touched_p, touched_q) -> None:
    specs = (
        ("load", -1.0, True),
        ("sgen", 1.0, True),
        ("storage", -1.0, True),
        ("ward", -1.0, False),
    )
    for key, sign, use_scaling in specs:
        frame = getattr(net, key, None)
        if frame is None or len(frame) == 0:
            continue
        p_col = "p_mw" if key != "ward" else "ps_mw"
        q_col = "q_mvar" if key != "ward" else "qs_mvar"
        for _idx, row in frame.iterrows():
            if not _series_flag(row, "in_service", True):
                continue
            bus = int(row["bus"])
            if bus not in rep:
                continue
            root = rep[bus]
            scale = _scaled_factor(row) if use_scaling else 1.0
            _add(p_acc, touched_p, root, sign * float(row[p_col]) * scale)
            _add(q_acc, touched_q, root, sign * float(row[q_col]) * scale)


def _line_branch(net, row, idx, rep, labels, f_hz, open_lines, used_names):
    from_idx = int(row["from_bus"])
    to_idx = int(row["to_bus"])
    if from_idx not in rep or to_idx not in rep:
        return None
    if rep[from_idx] == rep[to_idx]:
        return None
    length = float(row["length_km"])
    parallel = float(row["parallel"]) if "parallel" in row.index and not _missing(row["parallel"]) else 1.0
    if parallel <= 0.0:
        raise ValueError(f"line {idx} parallel must be positive")
    r_ohm = float(row["r_ohm_per_km"]) * length / parallel
    x_ohm = float(row["x_ohm_per_km"]) * length / parallel
    c_nf = float(row["c_nf_per_km"]) if "c_nf_per_km" in row.index else 0.0
    g_us = float(row["g_us_per_km"]) if "g_us_per_km" in row.index and not _missing(row["g_us_per_km"]) else 0.0
    b_s = 2.0 * math.pi * f_hz * c_nf * 1e-9 * length * parallel
    g_s = g_us * 1e-6 * length * parallel
    own = _series_flag(row, "in_service", True) and idx not in open_lines
    max_i = row["max_i_ka"] if "max_i_ka" in row.index else None
    rate = None
    if max_i is not None and not _missing(max_i):
        vn_from = float(net.bus.at[from_idx, "vn_kv"])
        rate = math.sqrt(3.0) * vn_from * float(max_i) * parallel
    raw_name = row["name"] if "name" in row.index else None
    name = _take_name(used_names, _text_name(raw_name, f"line_{idx}"), idx)
    return _empty_branch(
        branch_id=name,
        element="line",
        from_bus=labels[rep[from_idx]],
        to_bus=labels[rep[to_idx]],
        r_ohm=r_ohm,
        x_ohm=x_ohm,
        b_siemens=b_s,
        g_siemens=g_s,
        rate_mva=rate,
        length_km=length,
        in_service=int(own),
    )


def _pandapower_tap(row) -> tuple[float, bool, float, float]:
    """Return tap position, ideal-shifter flag, step percent, and step degree.

    Pandapower 3 applies ``tap_pos`` only when ``tap_changer_type`` is Ratio,
    Symmetrical, or Ideal. An empty type leaves the tap at neutral. Older nets
    without that column still use ``tap_pos`` and ``tap_phase_shifter``.
    """

    neutral = _series_float(row, "tap_neutral", 0.0)
    position = _series_float(row, "tap_pos", neutral)
    step_percent = _series_float(row, "tap_step_percent", 0.0)
    step_degree = _series_float(row, "tap_step_degree", 0.0)
    if "tap_changer_type" in row.index:
        kind = _text_name(row["tap_changer_type"], "").lower()
        if kind in {"ratio", "symmetrical"}:
            return position, False, step_percent, step_degree
        if kind == "ideal":
            return position, True, step_percent, step_degree
        return neutral, False, 0.0, 0.0
    phase = False
    if "tap_phase_shifter" in row.index and not _missing(row["tap_phase_shifter"]):
        phase = bool(row["tap_phase_shifter"])
    return position, phase, step_percent, step_degree


def _trafo_branch(net, row, idx, rep, labels, vn, s_base, open_trafos, used_names):
    hv = int(row["hv_bus"])
    lv = int(row["lv_bus"])
    if hv not in rep or lv not in rep or rep[hv] == rep[lv]:
        return None
    tap_pos, phase_shifter, step_percent, step_degree = _pandapower_tap(row)
    data = transformer_pi_pu(
        vk_percent=float(row["vk_percent"]),
        vkr_percent=float(row["vkr_percent"]),
        sn_mva=float(row["sn_mva"]),
        s_base_mva=s_base,
        vn_hv_kv=float(row["vn_hv_kv"]),
        vn_lv_kv=float(row["vn_lv_kv"]),
        bus_hv_kv=vn[hv],
        bus_lv_kv=vn[lv],
        tap_pos=tap_pos,
        tap_neutral=_series_float(row, "tap_neutral", 0.0),
        tap_step_percent=step_percent,
        tap_step_degree=step_degree,
        tap_side=_text_name(row["tap_side"], "hv") if "tap_side" in row.index else "hv",
        tap_phase_shifter=phase_shifter,
        shift_degree=_series_float(row, "shift_degree", 0.0),
        pfe_kw=_series_float(row, "pfe_kw", 0.0),
        i0_percent=_series_float(row, "i0_percent", 0.0),
        parallel=_series_float(row, "parallel", 1.0),
    )
    own = _series_flag(row, "in_service", True) and idx not in open_trafos
    raw_name = row["name"] if "name" in row.index else None
    name = _take_name(used_names, _text_name(raw_name, f"trafo_{idx}"), idx)
    branch = _empty_branch(
        branch_id=name,
        element="trafo",
        from_bus=labels[rep[hv]],
        to_bus=labels[rep[lv]],
        rate_mva=float(row["sn_mva"]) * _series_float(row, "parallel", 1.0),
        length_km=0.0,
        in_service=int(own),
    )
    branch["r_pu"] = data["r_pu"]
    branch["x_pu"] = data["x_pu"]
    branch["g_pu"] = data["g_pu"]
    branch["b_pu"] = data["b_pu"]
    branch["tap"] = data["tap"]
    branch["shift_deg"] = data["shift_deg"]
    return branch


def _impedance_branch(row, idx, rep, labels, s_base, used_names):
    from_idx = int(row["from_bus"])
    to_idx = int(row["to_bus"])
    if from_idx not in rep or to_idx not in rep or rep[from_idx] == rep[to_idx]:
        return None
    rft = float(row["rft_pu"])
    xft = float(row["xft_pu"])
    rtf = float(row["rtf_pu"])
    xtf = float(row["xtf_pu"])
    tol = 1e-8
    if abs(rft - rtf) > tol or abs(xft - xtf) > tol:
        raise ValueError(f"asymmetric impedance element {idx} is not a pi branch")
    sn = float(row["sn_mva"])
    if sn <= 0.0:
        raise ValueError(f"impedance {idx} sn_mva must be positive")
    name = _take_name(used_names, _text_name(row["name"] if "name" in row.index else None, f"z_{idx}"), idx)
    branch = _empty_branch(
        branch_id=name,
        element="line",
        from_bus=labels[rep[from_idx]],
        to_bus=labels[rep[to_idx]],
        in_service=int(_series_flag(row, "in_service", True)),
    )
    branch["r_pu"] = rft * s_base / sn
    branch["x_pu"] = xft * s_base / sn
    return branch


def _shunt_branch(net, row, idx, rep, labels, vn, s_base, used_names):
    bus = int(row["bus"])
    if bus not in rep or not _series_flag(row, "in_service", True):
        return None
    step = _series_float(row, "step", 1.0)
    vn_shunt = float(row["vn_kv"])
    if vn_shunt <= 0.0:
        raise ValueError(f"shunt {idx} vn_kv must be positive")
    v_ratio = (vn[bus] / vn_shunt) ** 2
    # pandapower writes GS = p * step * v_ratio and BS = -q * step * v_ratio, in MW/MVAr.
    g_pu = float(row["p_mw"]) * step * v_ratio / s_base
    b_pu = -float(row["q_mvar"]) * step * v_ratio / s_base
    name = _take_name(used_names, _text_name(row["name"] if "name" in row.index else None, f"shunt_{idx}"), idx)
    return {
        "shunt_id": name,
        "bus_id": labels[rep[bus]],
        "g_siemens": None,
        "b_siemens": None,
        "g_pu": g_pu,
        "b_pu": b_pu,
        "in_service": 1,
    }


def _empty_branch(**kwargs) -> dict:
    base = {
        "branch_id": "",
        "element": "line",
        "from_bus": "",
        "to_bus": "",
        "r_ohm": None,
        "x_ohm": None,
        "b_siemens": None,
        "g_siemens": None,
        "r_pu": None,
        "x_pu": None,
        "b_pu": None,
        "g_pu": None,
        "tap": 1.0,
        "shift_deg": 0.0,
        "rate_mva": None,
        "length_km": None,
        "in_service": 1,
    }
    base.update(kwargs)
    return base


def _add(store, touched, key, value) -> None:
    store[key] += value
    touched.add(key)


def _scaled(row, column: str) -> float:
    return float(row[column]) * _scaled_factor(row)


def _scaled_factor(row) -> float:
    if "scaling" not in row.index or _missing(row["scaling"]):
        return 1.0
    return float(row["scaling"])


def _fuse(nodes: list[int], links: list[tuple[int, int]]) -> dict[int, int]:
    parent = {node: node for node in nodes}

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for left, right in links:
        if left not in parent or right not in parent:
            continue
        a, b = find(left), find(right)
        if a == b:
            continue
        if a < b:
            parent[b] = a
        else:
            parent[a] = b
    return {node: find(node) for node in nodes}


def _unique_bus_labels(net, indices) -> dict[int, str]:
    raw = {idx: _text_name(_bus_raw_name(net, idx), f"Bus {idx}") for idx in indices}
    counts: dict[str, int] = {}
    for name in raw.values():
        counts[name] = counts.get(name, 0) + 1
    labels = {}
    for idx, name in raw.items():
        labels[idx] = name if counts[name] == 1 else f"{name}#{idx}"
    return labels


def _bus_raw_name(net, idx):
    if "name" not in net.bus.columns:
        return None
    return net.bus.at[idx, "name"]


def _bus_xy(net, idx) -> tuple[float | None, float | None]:
    if "x" in net.bus.columns and "y" in net.bus.columns:
        x = net.bus.at[idx, "x"]
        y = net.bus.at[idx, "y"]
        if not _missing(x) and not _missing(y):
            return float(x), float(y)
    geo = getattr(net, "bus_geodata", None)
    if geo is not None and idx in geo.index and "x" in geo.columns and "y" in geo.columns:
        x = geo.at[idx, "x"]
        y = geo.at[idx, "y"]
        if not _missing(x) and not _missing(y):
            return float(x), float(y)
    return None, None


def _text_name(value, fallback: str) -> str:
    if _missing(value):
        return fallback
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return fallback
    return text


def _take_name(used: set[str], raw: str, idx) -> str:
    name = raw if raw not in used else f"{raw}#{idx}"
    while name in used:
        name = f"{name}#{idx}"
    used.add(name)
    return name


def _any_in_service(frame) -> bool:
    if frame is None or len(frame) == 0:
        return False
    if "in_service" not in frame.columns:
        return True
    return bool(frame["in_service"].fillna(True).astype(bool).any())


def _frame_flag(frame, idx, column: str, default: bool) -> bool:
    if column not in frame.columns:
        return default
    value = frame.at[idx, column]
    if _missing(value):
        return default
    return bool(value)


def _series_flag(row, column: str, default: bool) -> bool:
    if column not in row.index or _missing(row[column]):
        return default
    return bool(row[column])


def _series_float(row, column: str, default: float) -> float:
    if column not in row.index or _missing(row[column]):
        return default
    return float(row[column])


def _missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == "" or value.strip().lower() == "nan"
    try:
        if value != value:
            return True
    except Exception:
        return False
    return False


def _write_bundle(directory: Path, result: GraphExport) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    _write_dicts(directory / "nodes.csv", NODE_COLUMNS, [_node_row(bus) for bus in result.buses])
    _write_dicts(directory / "branches.csv", BRANCH_COLUMNS, [_branch_row(i, branch) for i, branch in enumerate(result.branches)])
    _write_dicts(directory / "edges.csv", EDGE_COLUMNS, [_edge_row(edge) for edge in result.edges])
    _write_dicts(directory / "shunts.csv", SHUNT_COLUMNS, [_shunt_row(i, shunt) for i, shunt in enumerate(result.shunts)])
    _write_square(directory / "adjacency.csv", result.bus_ids, result.adjacency, integer=True)
    _write_square(directory / "ybus_g.csv", result.bus_ids, result.ybus.real, integer=False)
    _write_square(directory / "ybus_b.csv", result.bus_ids, result.ybus.imag, integer=False)


def _node_row(bus: BusOut) -> dict:
    return {
        "bus_index": str(bus.bus_index),
        "bus_id": bus.bus_id,
        "bus_name": bus.bus_name,
        "bus_type": bus.bus_type,
        "bus_type_code": str(bus.bus_type_code),
        "vn_kv": _csv_num(bus.vn_kv),
        "z_base_ohm": _csv_num(bus.z_base_ohm),
        "y_base_s": _csv_num(bus.y_base_s),
        "p_mw": _csv_num(bus.p_mw),
        "q_mvar": _csv_num(bus.q_mvar),
        "vm_pu": _csv_num(bus.vm_pu),
        "va_deg": _csv_num(bus.va_deg),
        "p_known": str(bus.p_known),
        "q_known": str(bus.q_known),
        "v_known": str(bus.v_known),
        "theta_known": str(bus.theta_known),
        "degree": str(bus.degree),
        "in_service": str(bus.in_service),
        "x": _csv_num(bus.x),
        "y": _csv_num(bus.y),
        "members": bus.members,
    }


def _branch_row(index: int, branch: BranchOut) -> dict:
    return {
        "branch_index": str(index),
        "branch_id": branch.branch_id,
        "element": branch.element,
        "from_bus": branch.from_bus,
        "to_bus": branch.to_bus,
        "from_index": "" if branch.from_index is None else str(branch.from_index),
        "to_index": "" if branch.to_index is None else str(branch.to_index),
        "r_ohm": _csv_num(branch.r_ohm),
        "x_ohm": _csv_num(branch.x_ohm),
        "b_siemens": _csv_num(branch.b_siemens),
        "g_siemens": _csv_num(branch.g_siemens),
        "r_pu": _csv_num(branch.r_pu),
        "x_pu": _csv_num(branch.x_pu),
        "b_pu": _csv_num(branch.b_pu),
        "g_pu": _csv_num(branch.g_pu),
        "g_series": _csv_num(branch.g_series),
        "b_series": _csv_num(branch.b_series),
        "tap": _csv_num(branch.tap),
        "shift_deg": _csv_num(branch.shift_deg),
        "rate_mva": _csv_num(branch.rate_mva),
        "length_km": _csv_num(branch.length_km),
        "in_service": str(branch.in_service),
    }


def _edge_row(edge: EdgeOut) -> dict:
    return {
        "edge_index": str(edge.edge_index),
        "branch_id": edge.branch_id,
        "element": edge.element,
        "orientation": edge.orientation,
        "from_bus": edge.from_bus,
        "to_bus": edge.to_bus,
        "from_index": str(edge.from_index),
        "to_index": str(edge.to_index),
        "r_pu": _csv_num(edge.r_pu),
        "x_pu": _csv_num(edge.x_pu),
        "b_pu": _csv_num(edge.b_pu),
        "g_pu": _csv_num(edge.g_pu),
        "g_series": _csv_num(edge.g_series),
        "b_series": _csv_num(edge.b_series),
        "tap": _csv_num(edge.tap),
        "shift_deg": _csv_num(edge.shift_deg),
        "rate_mva": _csv_num(edge.rate_mva),
        "length_km": _csv_num(edge.length_km),
        "y_self_g": _csv_num(edge.y_self_g),
        "y_self_b": _csv_num(edge.y_self_b),
        "y_mutual_g": _csv_num(edge.y_mutual_g),
        "y_mutual_b": _csv_num(edge.y_mutual_b),
    }


def _shunt_row(index: int, shunt: ShuntOut) -> dict:
    return {
        "shunt_index": str(index),
        "shunt_id": shunt.shunt_id,
        "bus_id": shunt.bus_id,
        "bus_index": "" if shunt.bus_index is None else str(shunt.bus_index),
        "g_siemens": _csv_num(shunt.g_siemens),
        "b_siemens": _csv_num(shunt.b_siemens),
        "g_pu": _csv_num(shunt.g_pu),
        "b_pu": _csv_num(shunt.b_pu),
        "in_service": str(shunt.in_service),
    }


def _write_dicts(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_square(path: Path, bus_ids: list[str], matrix, *, integer: bool) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["bus_id", *bus_ids])
        for i, bus_id in enumerate(bus_ids):
            if integer:
                values = [str(int(matrix[i, j])) for j in range(len(bus_ids))]
            else:
                values = [_csv_num(float(matrix[i, j])) for j in range(len(bus_ids))]
            writer.writerow([bus_id, *values])


def _render(result: GraphExport, output_png: Path | None, show: bool):
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.4))
    _draw_graph(axes[0], result)
    _draw_susceptance(axes[1], result)
    fig.suptitle(f"{result.network}: graph and Ybus susceptance", fontsize=12)
    fig.tight_layout()
    try:
        if output_png is not None:
            output_png.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_png, dpi=150)
        if show:
            plt.show()
            return fig
        plt.close(fig)
        return None
    except Exception:
        plt.close(fig)
        raise


def _draw_graph(ax, result: GraphExport) -> None:
    coords = _layout(result.buses)
    drawn = {"line": False, "trafo": False, "open": False}
    for branch in result.branches:
        i = branch.from_index
        j = branch.to_index
        if i is None or j is None:
            continue
        x0, y0 = coords[branch.from_bus]
        x1, y1 = coords[branch.to_bus]
        if not branch.in_service:
            ax.plot([x0, x1], [y0, y1], linestyle="--", color="#95a5a6", linewidth=1.2, zorder=1)
            drawn["open"] = True
        elif branch.element == "trafo" or abs(branch.tap - 1.0) > 1e-9:
            ax.plot([x0, x1], [y0, y1], color="#c0392b", linewidth=2.0, zorder=2)
            drawn["trafo"] = True
        else:
            ax.plot([x0, x1], [y0, y1], color="#1f4e79", linewidth=1.6, zorder=2)
            drawn["line"] = True
        if result.n_branch_in_service <= 12 and branch.in_service:
            ax.text((x0 + x1) / 2.0, (y0 + y1) / 2.0, branch.branch_id, fontsize=8, color="#333333")
    markers = {"slack": "s", "pv": "D", "pq": "o"}
    for bus in result.buses:
        x, y = coords[bus.bus_id]
        ax.scatter(
            [x],
            [y],
            s=80,
            marker=markers[bus.bus_type],
            color="#f4f1ea",
            edgecolors="#1f4e79",
            linewidths=1.4,
            zorder=3,
        )
        ax.annotate(bus.bus_id, (x, y), textcoords="offset points", xytext=(6, 6), fontsize=9)
    handles = []
    labels = []
    if drawn["line"]:
        handles.append(plt.Line2D([0], [0], color="#1f4e79", linewidth=1.6))
        labels.append("line")
    if drawn["trafo"]:
        handles.append(plt.Line2D([0], [0], color="#c0392b", linewidth=2.0))
        labels.append("transformer")
    if drawn["open"]:
        handles.append(plt.Line2D([0], [0], color="#95a5a6", linestyle="--", linewidth=1.2))
        labels.append("open")
    if handles:
        ax.legend(handles, labels, frameon=False, fontsize=8, loc="best")
    ax.set_title("Bus graph")
    ax.set_aspect("equal", adjustable="datalim")
    ax.tick_params(labelsize=8)
    ax.grid(True, alpha=0.25)


def _draw_susceptance(ax, result: GraphExport) -> None:
    data = np.array(result.ybus.imag, dtype=float)
    limit = float(np.max(np.abs(data))) if data.size else 1.0
    if limit == 0.0:
        limit = 1.0
    image = ax.imshow(data, cmap="coolwarm", vmin=-limit, vmax=limit)
    ax.set_xticks(range(result.n_bus))
    ax.set_yticks(range(result.n_bus))
    ax.set_xticklabels(result.bus_ids, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(result.bus_ids, fontsize=8)
    ax.set_title("B = imag(Ybus) (pu)")
    if result.n_bus <= 8:
        for i in range(result.n_bus):
            for j in range(result.n_bus):
                ax.text(j, i, f"{data[i, j]:.2f}", ha="center", va="center", fontsize=7, color="#1a1a1a")
    ax.figure.colorbar(image, ax=ax, fraction=0.046, pad=0.04)


def _layout(buses: list[BusOut]) -> dict[str, tuple[float, float]]:
    if any(bus.x is None or bus.y is None for bus in buses):
        coords = {}
        n_bus = len(buses)
        for i, bus in enumerate(buses):
            angle = 2.0 * math.pi * i / n_bus
            coords[bus.bus_id] = (math.cos(angle), math.sin(angle))
        return coords
    return {bus.bus_id: (float(bus.x), float(bus.y)) for bus in buses}


def _table_header() -> str:
    return (
        f"{'bus':<6} {'type':<6} {'deg':>3} {'G':>10} {'B':>10} "
        f"{'P_mw':>10} {'Q_mvar':>10} {'Vm':>8} {'Va':>8}  known"
    )


def _known_text(bus: BusOut) -> str:
    tokens = []
    if bus.p_known:
        tokens.append("P")
    if bus.q_known:
        tokens.append("Q")
    if bus.v_known:
        tokens.append("V")
    if bus.theta_known:
        tokens.append("theta")
    return ",".join(tokens)


def _fmt_jb(value: complex, digits: int = _PREVIEW_DIGITS) -> str:
    real = float(value.real)
    imag = float(value.imag)
    if abs(real) < 5e-13:
        real = 0.0
    if abs(imag) < 5e-13:
        imag = 0.0
    sign = "+" if imag >= 0.0 else "-"
    return f"{real:.{digits}f}{sign}j{abs(imag):.{digits}f}"


def _fmt_opt(value: float | None, width: int) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return f"{'-':>{width}}"
    return f"{value:{width}.4f}"


def _csv_num(value) -> str:
    if value is None:
        return ""
    number = float(value)
    if math.isnan(number):
        return ""
    return f"{number:.{_DIGITS}f}"


def _bases(vn_kv: float, s_base: float) -> tuple[float, float]:
    z_base = (vn_kv * vn_kv) / s_base
    y_base = s_base / (vn_kv * vn_kv)
    return z_base, y_base


def _resolve_csv(csv_path) -> Path:
    if csv_path in (None, ""):
        return _DEFAULT_CSV
    return Path(csv_path)


def _resolve_auto(csv_path, network_name: str) -> str:
    if csv_path not in (None, ""):
        return "builtin"
    if not network_name or network_name.lower() in {"synthetic", "builtin"}:
        return "builtin"
    return "pandapower"


def _normalize_engine(engine: str) -> str:
    name = str(engine).strip().lower()
    if name not in {"builtin", "pandapower", "auto"}:
        raise ValueError("engine must be builtin, pandapower, or auto")
    return name


def _as_bool(value, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, Integral) and not isinstance(value, bool) and int(value) in (0, 1):
        return bool(int(value))
    if isinstance(value, str) and value.strip().lower() in {"1", "0", "true", "false", "yes", "no"}:
        return value.strip().lower() in {"1", "true", "yes"}
    raise ValueError(f"{name} must be true or false")


def _positive(name: str, value) -> float:
    if not isinstance(value, Real) or isinstance(value, bool):
        raise ValueError(f"{name} must be a positive number")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be positive")
    return number


def _norm_key(name: str) -> str:
    return "".join(ch for ch in name.strip().lower() if ch.isalnum() or ch == "_")


def _cell(raw: dict, fields: dict, key: str) -> str:
    source = fields.get(key)
    if source is None:
        return ""
    value = raw.get(source)
    if value is None:
        return ""
    return str(value).strip()


def _blank(value) -> bool:
    return value is None or str(value).strip() == ""


def _optional_float(raw, fields, key: str, line_no: int) -> float | None:
    text = _cell(raw, fields, key)
    if _blank(text):
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(f"row {line_no}: {key} is not a number") from exc
    if not math.isfinite(value):
        raise ValueError(f"row {line_no}: {key} must be finite")
    return value


def _require_float(raw, fields, key: str, line_no: int) -> float:
    value = _optional_float(raw, fields, key, line_no)
    if value is None:
        raise ValueError(f"row {line_no}: {key} is required")
    return value


def _flag(text: str, line_no: int, default: bool) -> bool:
    if _blank(text):
        return default
    token = text.strip().lower()
    if token in {"1", "true", "yes", "y"}:
        return True
    if token in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"row {line_no}: in_service must be 0 or 1")
