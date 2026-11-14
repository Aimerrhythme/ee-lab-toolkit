"""Smoke tests for the grid-to-graph Python tool."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from grid_to_graph_export import (  # noqa: E402
    branch_stamp,
    format_table,
    grid_to_graph_export,
    transformer_pi_pu,
)

CSV = TOOL / "examples" / "data" / "synthetic_grid.csv"
PREVIEW = (
    "grid-to-graph-export: engine=builtin network=synthetic buses=4 branches=5 "
    "in_service=4 directed=8 shunts=1 self_loop=0 "
    "Y[B0,B0]=20.0000-j19.9900 off[B1,B2]=-5.0000+j15.0000 "
    "tap[T20]=1.2500 Yfrom[B2]=6.4000-j6.4000 Yto[B0]=10.0000-j10.0000 "
    "open=L13 adj_sym=1"
)


def _rebuild(result):
    built = np.zeros_like(result.ybus)
    for edge in result.edges:
        built[edge.from_index, edge.from_index] += edge.y_self_g + 1j * edge.y_self_b
        built[edge.from_index, edge.to_index] += edge.y_mutual_g + 1j * edge.y_mutual_b
    for shunt in result.shunts:
        if shunt.in_service and shunt.bus_index is not None:
            built[shunt.bus_index, shunt.bus_index] += shunt.g_pu + 1j * shunt.b_pu
    return built


def _write_grid(path: Path, rows: list[dict]) -> None:
    header = [
        "kind",
        "name",
        "bus_id",
        "bus_type",
        "vn_kv",
        "p_mw",
        "q_mvar",
        "vm_pu",
        "va_deg",
        "from_bus",
        "to_bus",
        "r_ohm",
        "x_ohm",
        "b_siemens",
        "g_siemens",
        "r_pu",
        "x_pu",
        "b_pu",
        "g_pu",
        "tap",
        "shift_deg",
        "in_service",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in header})


def test_synthetic_ybus_adjacency_and_preview() -> None:
    result = grid_to_graph_export(CSV)
    same = grid_to_graph_export()
    assert result.preview == same.preview == PREVIEW
    assert result.summary == format_table(result)
    assert result.engine == "builtin"
    assert result.network == "synthetic"
    assert result.s_base_mva == pytest.approx(10.0)
    assert result.bus_ids == ["B0", "B1", "B2", "B3"]
    assert [bus.bus_type for bus in result.buses] == ["slack", "pq", "pq", "pv"]
    assert [bus.bus_type_code for bus in result.buses] == [3, 1, 1, 2]
    assert [bus.degree for bus in result.buses] == [2, 2, 3, 1]
    assert [bus.p_known for bus in result.buses] == [0, 1, 1, 1]
    assert [bus.q_known for bus in result.buses] == [0, 1, 1, 0]
    assert [bus.v_known for bus in result.buses] == [1, 0, 0, 1]
    assert [bus.theta_known for bus in result.buses] == [1, 0, 0, 0]
    assert result.buses[0].p_mw is None
    assert result.buses[3].q_mvar is None
    assert result.buses[1].z_base_ohm == pytest.approx(10.0)
    assert result.buses[1].y_base_s == pytest.approx(0.1)

    assert result.adjacency.tolist() == [
        [0, 1, 1, 0],
        [1, 0, 1, 0],
        [1, 1, 0, 1],
        [0, 0, 1, 0],
    ]
    ybus = result.ybus
    assert ybus[0, 0] == pytest.approx(20 - 19.99j)
    assert ybus[0, 1] == pytest.approx(-10 + 10j)
    assert ybus[0, 2] == pytest.approx(-8 + 8j)
    assert ybus[0, 3] == pytest.approx(0j)
    assert ybus[1, 1] == pytest.approx(15 - 24.94j)
    assert ybus[1, 2] == pytest.approx(-5 + 15j)
    assert ybus[1, 3] == pytest.approx(0j)
    assert ybus[2, 2] == pytest.approx(16.4 - 31.4j)
    assert ybus[2, 3] == pytest.approx(-5 + 10j)
    assert ybus[3, 3] == pytest.approx(5 - 10j)
    assert _rebuild(result) == pytest.approx(ybus)

    assert [edge.branch_id for edge in result.edges] == [
        "L01",
        "L01",
        "L12",
        "L12",
        "T20",
        "T20",
        "L23",
        "L23",
    ]
    forward = result.edges[4]
    reverse = result.edges[5]
    assert forward.orientation == "forward"
    assert forward.from_bus == "B2" and forward.to_bus == "B0"
    assert complex(forward.y_self_g, forward.y_self_b) == pytest.approx(6.4 - 6.4j)
    assert complex(reverse.y_self_g, reverse.y_self_b) == pytest.approx(10 - 10j)
    assert complex(forward.y_mutual_g, forward.y_mutual_b) == pytest.approx(-8 + 8j)
    open_line = result.branches[4]
    assert open_line.branch_id == "L13"
    assert open_line.in_service == 0
    assert open_line.g_series == pytest.approx(10.0)
    assert result.shunts[0].shunt_id == "C1"
    assert result.shunts[0].b_pu == pytest.approx(0.05)
    assert "V,theta" in result.summary
    assert "P,Q" in result.summary
    assert "P,V" in result.summary


def test_self_loop_does_not_change_ybus() -> None:
    plain = grid_to_graph_export(CSV, self_loop=False)
    looped = grid_to_graph_export(CSV, self_loop=1)
    assert looped.ybus == pytest.approx(plain.ybus)
    assert np.trace(looped.adjacency) == 4
    assert [bus.degree for bus in looped.buses] == [bus.degree for bus in plain.buses]
    assert "self_loop=1" in looped.preview


def test_larger_base_scales_pu_admittance() -> None:
    scaled = grid_to_graph_export(CSV, s_base_mva=20)
    assert scaled.buses[0].z_base_ohm == pytest.approx(5.0)
    assert scaled.ybus[0, 0] == pytest.approx(10 - 9.995j)
    assert scaled.ybus[0, 2] == pytest.approx(-4 + 4j)


def test_shift_makes_ybus_unsymmetric(tmp_path: Path) -> None:
    path = tmp_path / "shift.csv"
    _write_grid(
        path,
        [
            {"kind": "bus", "name": "S", "bus_id": "A", "bus_type": "slack", "vn_kv": "10", "vm_pu": "1", "va_deg": "0"},
            {"kind": "bus", "name": "L", "bus_id": "B", "bus_type": "pq", "vn_kv": "10", "p_mw": "0", "q_mvar": "0"},
            {
                "kind": "line",
                "name": "Z",
                "from_bus": "A",
                "to_bus": "B",
                "r_pu": "0",
                "x_pu": "0.1",
                "tap": "1",
                "shift_deg": "30",
            },
        ],
    )
    result = grid_to_graph_export(path, network="synthetic")
    assert result.network == "shift"
    yff, yft, ytf, ytt, _ys = branch_stamp(0.0, 0.1, 0.0, 0.0, 1.0, 30.0)
    assert result.ybus[0, 0] == pytest.approx(yff)
    assert result.ybus[0, 1] == pytest.approx(yft)
    assert result.ybus[1, 0] == pytest.approx(ytf)
    assert result.ybus[1, 1] == pytest.approx(ytt)
    assert yft != pytest.approx(ytf)
    assert result.adjacency.tolist() == [[0, 1], [1, 0]]
    assert "tap[Z]=1.0000" in result.preview


def test_parallel_lines_stay_binary(tmp_path: Path) -> None:
    path = tmp_path / "parallel.csv"
    _write_grid(
        path,
        [
            {"kind": "bus", "bus_id": "A", "bus_type": "slack", "vn_kv": "10", "vm_pu": "1", "va_deg": "0"},
            {"kind": "bus", "bus_id": "B", "bus_type": "pq", "vn_kv": "10", "p_mw": "-1", "q_mvar": "0"},
            {"kind": "line", "name": "P1", "from_bus": "A", "to_bus": "B", "r_ohm": "0.5", "x_ohm": "0.5"},
            {"kind": "line", "name": "P2", "from_bus": "A", "to_bus": "B", "r_ohm": "0.5", "x_ohm": "0.5"},
        ],
    )
    result = grid_to_graph_export(path)
    assert result.adjacency.tolist() == [[0, 1], [1, 0]]
    assert result.n_branch_in_service == 2
    assert result.n_edge == 4
    assert result.ybus[0, 1] == pytest.approx(-20 + 20j)


def test_out_of_service_bus_drops_the_incident_branch(tmp_path: Path) -> None:
    path = tmp_path / "drop.csv"
    _write_grid(
        path,
        [
            {"kind": "bus", "bus_id": "A", "bus_type": "slack", "vn_kv": "10", "vm_pu": "1", "va_deg": "0"},
            {"kind": "bus", "bus_id": "B", "bus_type": "pq", "vn_kv": "10", "p_mw": "0", "q_mvar": "0", "in_service": "0"},
            {"kind": "line", "name": "AB", "from_bus": "A", "to_bus": "B", "r_ohm": "1", "x_ohm": "1"},
        ],
    )
    result = grid_to_graph_export(path)
    assert result.bus_ids == ["A"]
    assert result.n_branch == 1
    assert result.n_branch_in_service == 0
    assert result.branches[0].to_index is None
    assert "off=none" in result.preview
    assert "open=AB" in result.preview


def test_bad_inputs_raise(tmp_path: Path) -> None:
    zero = tmp_path / "zero.csv"
    _write_grid(
        zero,
        [
            {"kind": "bus", "bus_id": "A", "bus_type": "slack", "vn_kv": "10", "vm_pu": "1", "va_deg": "0"},
            {"kind": "bus", "bus_id": "B", "bus_type": "pq", "vn_kv": "10", "p_mw": "0", "q_mvar": "0"},
            {"kind": "line", "name": "Z0", "from_bus": "A", "to_bus": "B", "r_ohm": "0", "x_ohm": "0"},
        ],
    )
    with pytest.raises(ValueError, match="zero series impedance"):
        grid_to_graph_export(zero)

    bad_tap = tmp_path / "tap.csv"
    _write_grid(
        bad_tap,
        [
            {"kind": "bus", "bus_id": "A", "bus_type": "slack", "vn_kv": "10", "vm_pu": "1", "va_deg": "0"},
            {"kind": "bus", "bus_id": "B", "bus_type": "pq", "vn_kv": "10", "p_mw": "0", "q_mvar": "0"},
            {"kind": "trafo", "name": "T", "from_bus": "A", "to_bus": "B", "r_ohm": "1", "x_ohm": "1", "tap": "0"},
        ],
    )
    with pytest.raises(ValueError, match="tap must be positive"):
        grid_to_graph_export(bad_tap)

    with pytest.raises(ValueError, match="engine must be"):
        grid_to_graph_export(engine="matpower")
    with pytest.raises(ValueError, match="pandapower"):
        grid_to_graph_export(CSV, network="case14")
    with pytest.raises(ValueError, match="not found"):
        grid_to_graph_export(tmp_path / "missing.csv")


def test_transformer_pi_matches_the_classroom_reduction() -> None:
    neutral = transformer_pi_pu(
        vk_percent=10,
        vkr_percent=0,
        sn_mva=50,
        s_base_mva=100,
        vn_hv_kv=110,
        vn_lv_kv=10,
        bus_hv_kv=110,
        bus_lv_kv=10,
    )
    assert neutral["r_pu"] == pytest.approx(0.0)
    assert neutral["x_pu"] == pytest.approx(0.2)
    assert neutral["tap"] == pytest.approx(1.0)
    assert neutral["g_pu"] == pytest.approx(0.0)
    assert neutral["b_pu"] == pytest.approx(0.0)

    hv_tap = transformer_pi_pu(
        vk_percent=10,
        vkr_percent=0,
        sn_mva=50,
        s_base_mva=100,
        vn_hv_kv=110,
        vn_lv_kv=10,
        bus_hv_kv=110,
        bus_lv_kv=10,
        tap_pos=2,
        tap_neutral=0,
        tap_step_percent=1,
        tap_side="hv",
    )
    assert hv_tap["tap"] == pytest.approx(1.02)
    assert hv_tap["x_pu"] == pytest.approx(0.2)

    lv_tap = transformer_pi_pu(
        vk_percent=10,
        vkr_percent=0,
        sn_mva=50,
        s_base_mva=100,
        vn_hv_kv=110,
        vn_lv_kv=10,
        bus_hv_kv=110,
        bus_lv_kv=10,
        tap_pos=2,
        tap_neutral=0,
        tap_step_percent=1,
        tap_side="lv",
    )
    assert lv_tap["tap"] == pytest.approx(1.0 / 1.02)
    assert lv_tap["x_pu"] == pytest.approx(0.20808)

    iron = transformer_pi_pu(
        vk_percent=10,
        vkr_percent=0,
        sn_mva=50,
        s_base_mva=100,
        vn_hv_kv=110,
        vn_lv_kv=10,
        bus_hv_kv=110,
        bus_lv_kv=10,
        pfe_kw=50,
    )
    assert iron["g_pu"] == pytest.approx(0.0005)
    assert iron["b_pu"] == pytest.approx(0.0)

    magnetizing = transformer_pi_pu(
        vk_percent=10,
        vkr_percent=0,
        sn_mva=50,
        s_base_mva=100,
        vn_hv_kv=110,
        vn_lv_kv=10,
        bus_hv_kv=110,
        bus_lv_kv=10,
        i0_percent=1,
    )
    assert magnetizing["b_pu"] == pytest.approx(-0.005)
    assert magnetizing["g_pu"] == pytest.approx(0.0)


def test_bundle_and_demo(tmp_path: Path) -> None:
    png = tmp_path / "graph.png"
    result = grid_to_graph_export(CSV, output_dir=tmp_path / "bundle", output_png=png, show=False)
    assert result.fig is None
    assert png.stat().st_size > 0
    bundle = tmp_path / "bundle"
    adjacency = (bundle / "adjacency.csv").read_text(encoding="utf-8").splitlines()
    assert adjacency[0] == "bus_id,B0,B1,B2,B3"
    assert adjacency[1] == "B0,0,1,1,0"
    y_g = (bundle / "ybus_g.csv").read_text(encoding="utf-8").splitlines()
    assert y_g[1].startswith("B0,20.0000000000,")
    nodes = (bundle / "nodes.csv").read_text(encoding="utf-8")
    assert "bus_type_code" in nodes
    assert "slack" in nodes
    edges = list(csv.DictReader((bundle / "edges.csv").open(encoding="utf-8")))
    assert len(edges) == 8
    assert edges[0]["from_index"] == "0"
    assert edges[0]["to_index"] == "1"

    demo = TOOL / "examples" / "run_demo.py"
    proc = subprocess.run([sys.executable, str(demo)], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert PREVIEW in proc.stdout
    assert (TOOL / "examples" / "output" / "grid_to_graph_export_demo.png").is_file()
    assert (TOOL / "examples" / "output" / "grid_to_graph_export" / "adjacency.csv").is_file()


def test_pandapower_engine_is_optional() -> None:
    try:
        import pandapower  # noqa: F401
    except ImportError:
        with pytest.raises(ValueError, match="pandapower"):
            grid_to_graph_export(engine="pandapower", network="case14")
        return
    result = grid_to_graph_export(engine="pandapower", network="case14")
    assert result.engine == "pandapower"
    assert result.network == "case14"
    assert result.n_bus >= 4
    assert result.adjacency.shape == (result.n_bus, result.n_bus)
    assert np.array_equal(result.adjacency, result.adjacency.T)
    assert _rebuild(result) == pytest.approx(result.ybus)
