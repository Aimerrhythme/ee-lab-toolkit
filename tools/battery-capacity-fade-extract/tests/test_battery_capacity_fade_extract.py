import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))
from battery_capacity_fade import (battery_capacity_fade_extract, format_summary,  # noqa: E402
                                   load_cycles, synthetic_rows, write_csv)


def test_constant_current_capacity(tmp_path):
    rows = [(1, s * 60.0, -1.0, 3.7) for s in range(61)] + [(2, s * 60.0, -0.5, 3.7) for s in range(61)]
    rows += [(3, s * 60.0, -0.5, 3.7) for s in range(61)] + [(1, 9999.0, 1.0, 4.0)]
    p = tmp_path / "c.csv"
    write_csv(p, rows)
    r = battery_capacity_fade_extract(p)
    assert r["capacity_ah"][0] == pytest.approx(1.0, abs=1e-6)
    assert r["capacity_ah"][1] == pytest.approx(0.5, abs=1e-6)
    assert r["soh"][1] == pytest.approx(0.5)


def test_synthetic_fade_is_monotone_trend(tmp_path):
    p = tmp_path / "s.csv"
    write_csv(p, synthetic_rows())
    r = battery_capacity_fade_extract(p)
    assert len(r["cycles"]) == 120
    assert r["capacity_ah"][-1] < r["capacity_ah"][0]
    assert r["features"]["slope_ah_per_cycle"] < 0
    assert r["features"]["n_early"] == 100


def test_eol_and_nominal(tmp_path):
    p = tmp_path / "s.csv"
    write_csv(p, synthetic_rows())
    r = battery_capacity_fade_extract(p, nominal_ah=1.10, eol_soh=0.95)
    assert r["eol_cycle"] is not None and r["soh"][r["eol_cycle"] - 1] <= 0.95
    assert battery_capacity_fade_extract(p, eol_soh=0.1)["eol_cycle"] is None


def test_outputs_and_bad_inputs(tmp_path):
    p = tmp_path / "s.csv"
    write_csv(p, synthetic_rows())
    o = tmp_path / "o.csv"
    battery_capacity_fade_extract(p, output_csv=o, output_png=tmp_path / "o.png")
    assert len(o.read_text().splitlines()) == 121 and (tmp_path / "o.png").exists()
    with pytest.raises(ValueError):
        battery_capacity_fade_extract(p, eol_soh=1.5)
    bad = tmp_path / "b.csv"
    bad.write_text("cycle,time_s\n1,0\n")
    with pytest.raises(ValueError):
        load_cycles(bad)


def test_run_demo_script():
    r = subprocess.run([sys.executable, str(TOOL / "examples" / "run_demo.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "cycles=120" in r.stdout

