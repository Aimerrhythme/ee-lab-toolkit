"""Generate the tiny synthetic insulator VOC dataset (fixed seed, 20 images)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

W, H, N = 160, 120, 20


def make_image(rng):
    sky = np.linspace(0.75, 0.55, H)[:, None] * np.ones((1, W))
    img = np.stack([sky * 0.8, sky * 0.9, sky], axis=-1) + rng.normal(0, 0.02, (H, W, 3))
    objs = []
    for x0 in sorted(rng.choice([30, 70, 110], size=int(rng.integers(1, 3)), replace=False)):
        n_disc = int(rng.integers(5, 9))
        top = int(rng.integers(8, 30))
        bottom = top + n_disc * 9
        img[top:bottom, x0 + 8:x0 + 12] = [0.35, 0.25, 0.2]  # string rod
        for k in range(n_disc):
            y = top + k * 9
            img[y:y + 6, x0:x0 + 20] = [0.65, 0.4, 0.2]  # disc
        objs.append(("insulator", x0 - 2, top - 2, x0 + 22, bottom + 1))
        if rng.random() < 0.35:
            k = int(rng.integers(0, n_disc))
            y = top + k * 9
            img[y:y + 6, x0:x0 + 20] = [0.1, 0.1, 0.1]  # broken disc
            objs.append(("defect", x0, y - 1, x0 + 20, y + 7))
    return np.clip(img, 0, 1), objs


def voc_xml(filename, objs):
    rows = "".join(
        f"  <object><name>{n}</name><bndbox><xmin>{a}</xmin><ymin>{b}</ymin><xmax>{c}</xmax><ymax>{d}</ymax></bndbox></object>\n"
        for n, a, b, c, d in objs)
    return (f"<annotation>\n  <filename>{filename}</filename>\n"
            f"  <size><width>{W}</width><height>{H}</height><depth>3</depth></size>\n{rows}</annotation>\n")


def main(out_dir=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = Path(out_dir) if out_dir else Path(__file__).resolve().parent / "data" / "voc"
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "annotations").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    for i in range(N):
        img, objs = make_image(rng)
        if i == N - 1:
            objs.append(("insulator", 50, 40, 50, 80))   # degenerate box: skipped by the converter
            objs.append(("insulator", 150, 100, 175, 130))  # runs off the image: clipped
        name = f"ins_{i:03d}.png"
        plt.imsave(out / "images" / name, img)
        (out / "annotations" / f"ins_{i:03d}.xml").write_text(voc_xml(name, objs), encoding="utf-8")


if __name__ == "__main__":
    main()
