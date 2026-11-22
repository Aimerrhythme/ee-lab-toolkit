"""Smoke tests for insulator-yolo-label-convert."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import matplotlib
import pytest

matplotlib.use("Agg")

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from insulator_yolo_label_convert import (box_to_yolo, insulator_yolo_label_convert,
                                          read_yolo, split_of)

VOC = TOOL / "examples" / "data" / "voc"


def test_box_to_yolo_known_values():
    cx, cy, w, h = box_to_yolo((10, 10, 50, 30), 100, 50)
    assert (round(cx, 6), round(cy, 6), round(w, 6), round(h, 6)) == (0.3, 0.4, 0.4, 0.4)


def test_box_clipped_and_degenerate():
    cx, cy, w, h = box_to_yolo((90, 40, 130, 70), 100, 50)
    assert w == pytest.approx(0.1) and h == pytest.approx(0.2)
    assert box_to_yolo((5, 5, 5, 20), 100, 50) is None


def test_split_rule():
    assert [split_of(i) for i in range(10)] == ["train"] * 7 + ["val"] * 2 + ["test"]


def test_convert_sample(tmp_path):
    res = insulator_yolo_label_convert(VOC, tmp_path / "y", output_png=tmp_path / "c.png")
    assert res["n_images"] == 20
    assert res["split_counts"] == {"train": 14, "val": 4, "test": 2}
    assert res["n_skipped"] == 1
    assert res["classes"] == ["defect", "insulator"]
    assert (tmp_path / "c.png").stat().st_size > 0
    total = sum(len(read_yolo(p)) for p in (tmp_path / "y" / "labels").rglob("*.txt") if p.read_text().strip())
    assert total == res["n_boxes"]
    for p in (tmp_path / "y" / "labels").rglob("*.txt"):
        for row in (read_yolo(p) if p.read_text().strip() else []):
            assert all(0 <= v <= 1 for v in row[1:])


def test_unknown_class_skipped(tmp_path):
    res = insulator_yolo_label_convert(VOC, tmp_path / "y", classes=["insulator"])
    assert res["classes"] == ["insulator"]
    assert res["n_skipped"] > 1


def test_run_demo_script():
    out = subprocess.run([sys.executable, str(TOOL / "examples" / "run_demo.py")],
                         capture_output=True, text=True, check=True).stdout
    assert out.startswith("images=20 boxes=")
