"""Load EL (electroluminescence) cell images, stratified split, flip/rotate augmentation, montage.

Mirrors ``matlab/el_image_loader_aug.m``.

Input CSV (elpv-dataset style): ``path,proba,type``
  path  : image path relative to the CSV's folder (square, same size, PNG/JPG)
  proba : defect probability in {0, 1/3, 2/3, 1}  -> class = round(proba * 3)
  type  : cell type text (e.g. mono / poly); kept for reporting only

Steps (all deterministic, so Python and MATLAB agree exactly):
  1. load images as float grayscale in [0, 1] (RGB -> mean of channels)
  2. stratified split per class: sort by path, rank j = 0..n-1,
     u = mod((j + seed) * PHI, 1);  u < f_train -> train, < f_train + f_val -> val, else test
  3. augment TRAIN only with 5 fixed ops: hflip, vflip, rot90 (CCW), rot180, rot270
  4. export split.csv / class_counts.csv / aug_manifest.csv and a montage PNG
     (one train sample per class; columns = orig + 5 ops)
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PHI = 0.6180339887498949
OPS = ("orig", "hflip", "vflip", "rot90", "rot180", "rot270")
SPLITS = ("train", "val", "test")


@dataclass
class ELResult:
    paths: list
    types: list
    proba: np.ndarray        # (N,)
    cls: np.ndarray          # (N,) int 0..3
    split: list              # (N,) 'train' | 'val' | 'test'
    images: np.ndarray       # (N, H, W) float in [0, 1]
    classes: np.ndarray      # sorted unique class ids
    counts: np.ndarray       # (K, 3) train / val / test counts per class
    train_mean: float
    train_std: float
    manifest: list           # [(path, op)] augmented copies of train images
    montage: np.ndarray      # (K*H, 6*W)


def apply_op(img: np.ndarray, op: str) -> np.ndarray:
    if op == "orig":
        return img
    if op == "hflip":
        return img[:, ::-1]
    if op == "vflip":
        return img[::-1, :]
    if op == "rot90":
        return np.rot90(img, 1)
    if op == "rot180":
        return np.rot90(img, 2)
    if op == "rot270":
        return np.rot90(img, 3)
    raise ValueError(f"unknown op {op!r}")


def read_gray(path) -> np.ndarray:
    from matplotlib import image as mpimg

    a = np.asarray(mpimg.imread(str(path)), dtype=float)
    if a.ndim == 3:
        a = a[:, :, :3].mean(axis=2)
    if a.max() > 1.0:                       # JPEG via some backends: 0..255
        a = a / 255.0
    return a


def read_labels(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("empty label CSV")
    return ([r["path"].strip() for r in rows],
            np.array([float(r["proba"]) for r in rows]),
            [r["type"].strip() for r in rows])


def split_labels(paths, cls, fractions=(0.6, 0.2, 0.2), seed=0):
    """Deterministic stratified split; returns list of split names."""
    ft, fv = fractions[0], fractions[1]
    if min(fractions) < 0 or abs(sum(fractions) - 1.0) > 1e-9:
        raise ValueError("fractions must be non-negative and sum to 1")
    out = [""] * len(paths)
    for k in np.unique(cls):
        idx = sorted(np.flatnonzero(cls == k), key=lambda i: paths[i])
        for j, i in enumerate(idx):
            u = ((j + seed) * PHI) % 1.0
            out[i] = "train" if u < ft else ("val" if u < ft + fv else "test")
    return out


def el_image_loader_aug(csv_path, output_dir=None, output_png=None,
                        fractions=(0.6, 0.2, 0.2), seed=0) -> ELResult:
    csv_path = Path(csv_path)
    paths, proba, types = read_labels(csv_path)
    cls = np.round(proba * 3).astype(int)
    imgs = [read_gray(csv_path.parent / p) for p in paths]
    h, w = imgs[0].shape
    if h != w or any(im.shape != (h, w) for im in imgs):
        raise ValueError("all images must be square and the same size")
    images = np.stack(imgs)
    split = split_labels(paths, cls, fractions, seed)

    classes = np.unique(cls)
    counts = np.array([[sum(1 for i in np.flatnonzero(cls == k) if split[i] == s)
                        for s in SPLITS] for k in classes])
    tr = np.array([s == "train" for s in split])
    mean, std = float(images[tr].mean()), float(images[tr].std())
    manifest = [(paths[i], op) for i in np.flatnonzero(tr) for op in OPS[1:]]

    rows = []
    for k in classes:
        i = sorted(np.flatnonzero((cls == k) & tr), key=lambda i: paths[i])
        base = images[i[0]] if i else np.zeros((h, w))
        rows.append(np.hstack([apply_op(base, op) for op in OPS]))
    montage = np.vstack(rows)

    res = ELResult(paths, types, proba, cls, split, images, classes, counts,
                   mean, std, manifest, montage)
    if output_dir is not None:
        _write(res, Path(output_dir))
    if output_png is not None:
        from matplotlib import image as mpimg

        Path(output_png).parent.mkdir(parents=True, exist_ok=True)
        mpimg.imsave(str(output_png), montage, cmap="gray", vmin=0, vmax=1)
    return res


def _write(res: ELResult, d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "split.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["path", "proba", "type", "class", "split"])
        for i, p in enumerate(res.paths):
            wr.writerow([p, f"{res.proba[i]:.4f}", res.types[i], res.cls[i], res.split[i]])
    with open(d / "class_counts.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["class", "train", "val", "test"])
        for k, c in zip(res.classes, res.counts):
            wr.writerow([k, *c])
    with open(d / "aug_manifest.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["path", "op"])
        wr.writerows(res.manifest)


def format_table(res: ELResult) -> str:
    lines = [f"{len(res.paths)} images, size {res.images.shape[1]}x{res.images.shape[2]}",
             "class  train  val  test"]
    for k, c in zip(res.classes, res.counts):
        lines.append(f"{k:>5d}  {c[0]:>5d}  {c[1]:>3d}  {c[2]:>4d}")
    lines.append(f"train mean={res.train_mean:.4f} std={res.train_std:.4f}; "
                 f"augmented copies={len(res.manifest)}")
    return "\n".join(lines)
