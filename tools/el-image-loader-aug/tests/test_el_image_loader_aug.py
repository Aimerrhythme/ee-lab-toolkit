"""Smoke tests for el-image-loader-aug."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))
sys.path.insert(0, str(TOOL / "examples"))

from el_image_loader_aug import OPS, apply_op, el_image_loader_aug  # noqa: E402

CSV = TOOL / "examples" / "data" / "labels.csv"


def test_ops_are_invertible_and_distinct():
    a = np.arange(16.0).reshape(4, 4)
    assert np.array_equal(apply_op(apply_op(a, "hflip"), "hflip"), a)
    assert np.array_equal(apply_op(apply_op(a, "rot90"), "rot270"), a)
    assert np.array_equal(apply_op(apply_op(a, "rot90"), "rot90"), apply_op(a, "rot180"))
    assert len({apply_op(a, o).tobytes() for o in OPS}) == 6


def test_demo_csv(tmp_path):
    res = el_image_loader_aug(CSV, output_dir=tmp_path / "o", output_png=tmp_path / "m.png")
    assert res.images.shape == (40, 32, 32)
    assert list(res.classes) == [0, 1, 2, 3]
    assert res.counts.sum() == 40 and res.counts.sum(axis=0)[0] > 0
    assert (res.counts.sum(axis=1) == [16, 8, 6, 10]).all()
    assert (res.counts[:, 0] > 0).all()                    # every class has train samples
    assert len(res.manifest) == 5 * res.counts[:, 0].sum()
    assert res.montage.shape == (4 * 32, 6 * 32)
    assert (tmp_path / "m.png").stat().st_size > 0
    for f in ("split.csv", "class_counts.csv", "aug_manifest.csv"):
        assert (tmp_path / "o" / f).exists()


def test_deterministic_and_seed():
    a = el_image_loader_aug(CSV)
    b = el_image_loader_aug(CSV)
    c = el_image_loader_aug(CSV, seed=3)
    assert a.split == b.split
    assert a.split != c.split


def test_regenerate_matches(tmp_path, monkeypatch):
    import make_synthetic

    monkeypatch.setattr(make_synthetic, "__file__", str(tmp_path / "x" / "make_synthetic.py"))
    (tmp_path / "x").mkdir()
    make_synthetic.main()
    assert (tmp_path / "x" / "data" / "labels.csv").read_text() == CSV.read_text()
