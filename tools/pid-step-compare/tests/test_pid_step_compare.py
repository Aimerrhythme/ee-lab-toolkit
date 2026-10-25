"""Smoke tests for the pid-step-compare Python tool."""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from pid_step_compare import format_metrics_table, pid_step_compare

PLANT_CSV = TOOL / "examples" / "data" / "plant.csv"
PID_CSV = TOOL / "examples" / "data" / "pid_sets.csv"
PLANT = {"form": "second_order", "k": 1.0, "wn": 1.0, "zeta": 1.0}


def test_default_sets_have_finite_metrics_and_a_teaching_story(tmp_path: Path) -> None:
    png = tmp_path / "step.png"
    result = pid_step_compare(output_png=png, show=False)

    assert result.plant["form"] == "second_order"
    assert result.plant["num"] == pytest.approx([1.0])
    assert result.plant["den"] == pytest.approx([1.0, 2.0, 1.0])
    assert result.y.shape == (result.time.size, 3)
    assert result.u.shape == result.y.shape
    assert np.all(np.isfinite(result.y))
    assert np.all(np.isfinite(result.u))
    assert [row.name for row in result.metrics] == ["P", "PI", "PID"]
    assert png.is_file()
    assert png.stat().st_size > 1000
    assert result.output_png == str(png)
    assert result.fig is None

    proportional, integral, full = result.metrics
    for row in result.metrics:
        assert row.stable
        assert math.isfinite(row.tr)
        assert math.isfinite(row.mp_pct)
        assert math.isfinite(row.ts)
        assert math.isfinite(row.ess)
    assert proportional.ess == pytest.approx(1.0 / 3.0, abs=1e-3)
    assert abs(integral.ess) < 1e-3
    assert abs(full.ess) < 1e-3
    assert integral.mp_pct > proportional.mp_pct
    assert full.mp_pct < integral.mp_pct
    assert "Mp%" in format_metrics_table(result.metrics)

    from_csv = pid_step_compare(PLANT_CSV, PID_CSV, show=False)
    assert np.allclose(result.y, from_csv.y)
    assert np.allclose(result.u, from_csv.u)


def test_kp_changes_the_response_and_matches_second_order_formula() -> None:
    low = pid_step_compare(PLANT, [{"name": "low", "kp": 0.5, "ki": 0, "kd": 0}], show=False)
    high = pid_step_compare(PLANT, [{"name": "high", "kp": 4.0, "ki": 0, "kd": 0}], show=False)
    assert np.max(np.abs(low.y[:, 0] - high.y[:, 0])) > 0.2
    assert high.metrics[0].ess < low.metrics[0].ess

    kp = 2.0
    checked = pid_step_compare(
        PLANT,
        [{"name": "P", "kp": kp, "ki": 0, "kd": 0}],
        t_final=20,
        dt=0.001,
        show=False,
    )
    zeta_cl = 1.0 / math.sqrt(1.0 + kp)
    expected_mp = math.exp(-math.pi * zeta_cl / math.sqrt(1.0 - zeta_cl**2)) * 100.0
    row = checked.metrics[0]
    assert row.ess == pytest.approx(1.0 / (1.0 + kp), abs=1e-4)
    assert row.y_final == pytest.approx(kp / (1.0 + kp), abs=1e-4)
    assert row.mp_pct == pytest.approx(expected_mp, abs=0.05)
    assert row.peak_time == pytest.approx(math.pi / (math.sqrt(1.0 + kp) * math.sqrt(1.0 - zeta_cl**2)), abs=0.01)


def test_first_order_p_control_matches_the_closed_form() -> None:
    result = pid_step_compare(
        {"form": "fopdt", "k": 1.0, "tau": 1.0, "theta": 0.0},
        {"name": "P", "kp": 1.0, "ki": 0.0, "kd": 0.0},
        t_final=12,
        dt=0.001,
        show=False,
    )
    row = result.metrics[0]
    assert row.y_final == pytest.approx(0.5, abs=1e-8)
    assert row.ess == pytest.approx(0.5, abs=1e-8)
    assert row.tr == pytest.approx(math.log(9.0) / 2.0, abs=1e-4)
    assert row.ts == pytest.approx(-math.log(0.02) / 2.0, abs=1e-4)
    assert row.mp_pct == pytest.approx(0.0, abs=1e-4)


def test_tf_matches_second_order_and_delay_holds_the_output() -> None:
    gains = [{"name": "PI", "kp": 1.0, "ki": 0.2, "kd": 0.1}]
    by_wn = pid_step_compare(
        {"form": "second_order", "k": 1.5, "wn": 2.0, "zeta": 0.4},
        gains,
        t_final=8,
        dt=0.01,
        show=False,
    )
    by_tf = pid_step_compare(
        {"form": "tf", "num": [1.5 * 4.0], "den": [1.0, 1.6, 4.0]},
        gains,
        t_final=8,
        dt=0.01,
        show=False,
    )
    assert np.allclose(by_wn.y, by_tf.y, atol=1e-10)
    assert by_tf.plant["num"] == pytest.approx([6.0])
    assert by_tf.plant["den"] == pytest.approx([1.0, 1.6, 4.0])

    fast = pid_step_compare(
        {"form": "fopdt", "k": 1.0, "tau": 1.0, "theta": 0.0},
        [{"kp": 1.0, "ki": 0.0, "kd": 0.0}],
        t_final=4,
        dt=0.01,
        show=False,
    )
    slow = pid_step_compare(
        {"form": "fopdt", "k": 1.0, "tau": 1.0, "theta": 0.5},
        [{"kp": 1.0, "ki": 0.0, "kd": 0.0}],
        t_final=4,
        dt=0.01,
        show=False,
    )
    assert np.all(slow.y[slow.time <= 0.5, 0] == 0.0)
    assert fast.y[np.argmin(np.abs(fast.time - 0.2)), 0] > 0.1
    assert slow.names == ["P"]


def test_bad_options_and_semicolon_csv(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="form"):
        pid_step_compare({"form": "state-space"}, [{"kp": 1}], show=False)
    with pytest.raises(ValueError, match="strictly proper"):
        pid_step_compare({"form": "tf", "num": [1, 1], "den": [1, 1]}, [{"kp": 1}], show=False)
    with pytest.raises(ValueError, match="dt"):
        pid_step_compare({"form": "second_order", "wn": 80, "zeta": 0.5}, [{"kp": 1}], dt=0.1, show=False)
    with pytest.raises(ValueError, match="theta"):
        pid_step_compare({"form": "fopdt", "theta": -0.2}, [{"kp": 1}], show=False)
    with pytest.raises(ValueError, match="at least one"):
        pid_step_compare(PLANT, [], show=False)
    with pytest.raises(FileNotFoundError):
        pid_step_compare(tmp_path / "missing.csv", PID_CSV, show=False)

    semicolon = tmp_path / "pid.csv"
    semicolon.write_text("name;kp;ki;kd\nP;1;0;0\nPI;1;0.4;0\n", encoding="utf-8")
    parsed = pid_step_compare(PLANT, semicolon, t_final=5, dt=0.02, show=False)
    assert parsed.names == ["P", "PI"]
    assert parsed.metrics[0].kp == pytest.approx(1.0)
    assert parsed.metrics[1].ki == pytest.approx(0.4)


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "form=second_order" in completed.stdout
    assert "Mp%" in completed.stdout
    assert "PID" in completed.stdout
    png = TOOL / "examples" / "output" / "pid_step_compare_demo.png"
    assert png.is_file()
    assert png.stat().st_size > 1000
