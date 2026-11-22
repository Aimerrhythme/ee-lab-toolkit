"""Convert Pascal-VOC XML boxes to YOLO txt labels, split 7:2:1, and draw check boxes.

Input layout: <voc_dir>/annotations/*.xml and <voc_dir>/images/<filename>.
Box coordinates are taken as pixel values: cx = (xmin + xmax) / 2 / width, and so on.
"""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

SPLITS = ("train", "val", "test")


def split_of(index):
    """Round-robin 7:2:1 rule on the sorted position: i%10 in 0-6 train, 7-8 val, 9 test."""
    k = index % 10
    return "train" if k < 7 else ("val" if k < 9 else "test")


def parse_voc(xml_path):
    """Return dict(filename, width, height, objects=[(name, xmin, ymin, xmax, ymax)])."""
    root = ET.parse(xml_path).getroot()
    size = root.find("size")
    if size is None:
        raise ValueError(f"{xml_path}: missing <size>")
    width, height = int(float(size.findtext("width"))), int(float(size.findtext("height")))
    if width <= 0 or height <= 0:
        raise ValueError(f"{xml_path}: bad image size")
    objects = []
    for obj in root.findall("object"):
        bb = obj.find("bndbox")
        if bb is None:
            continue
        vals = [float(bb.findtext(k)) for k in ("xmin", "ymin", "xmax", "ymax")]
        objects.append((obj.findtext("name").strip(), *vals))
    return {"filename": (root.findtext("filename") or "").strip(),
            "width": width, "height": height, "objects": objects}


def box_to_yolo(box, width, height):
    """Clip a pixel box to the image and return (cx, cy, w, h) normalized, or None if empty."""
    xmin, ymin, xmax, ymax = box
    xmin, xmax = min(max(xmin, 0.0), width), min(max(xmax, 0.0), width)
    ymin, ymax = min(max(ymin, 0.0), height), min(max(ymax, 0.0), height)
    if xmax <= xmin or ymax <= ymin:
        return None
    return ((xmin + xmax) / 2 / width, (ymin + ymax) / 2 / height,
            (xmax - xmin) / width, (ymax - ymin) / height)


def read_yolo(label_path):
    rows = []
    text = Path(label_path).read_text(encoding="utf-8").strip()
    for line in text.splitlines():
        p = line.split()
        rows.append((int(p[0]), *[float(v) for v in p[1:]]))
    return rows


def insulator_yolo_label_convert(voc_dir, out_dir, classes=None, viz_n=6, output_png=None, show=False):
    """Convert a VOC folder to a YOLO dataset under out_dir and return a summary dict."""
    voc_dir, out_dir = Path(voc_dir), Path(out_dir)
    xmls = sorted((voc_dir / "annotations").glob("*.xml"))
    if not xmls:
        raise ValueError(f"no XML files in {voc_dir / 'annotations'}")
    ann = [(x.stem, parse_voc(x)) for x in xmls]
    if classes is None:
        classes = sorted({o[0] for _, a in ann for o in a["objects"]})
    classes = list(classes)
    cid = {c: i for i, c in enumerate(classes)}

    for s in SPLITS:
        (out_dir / "images" / s).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / s).mkdir(parents=True, exist_ok=True)

    split_counts = dict.fromkeys(SPLITS, 0)
    class_counts = dict.fromkeys(classes, 0)
    n_boxes = n_skipped = n_empty = 0
    items = []
    for i, (stem, a) in enumerate(ann):
        s = split_of(i)
        img_src = voc_dir / "images" / a["filename"]
        if not a["filename"] or not img_src.exists():
            cands = sorted((voc_dir / "images").glob(stem + ".*"))
            if not cands:
                raise FileNotFoundError(f"image for {stem} not found")
            img_src = cands[0]
        lines = []
        for name, *box in a["objects"]:
            yb = box_to_yolo(box, a["width"], a["height"]) if name in cid else None
            if yb is None:
                n_skipped += 1
                continue
            lines.append("%d %.6f %.6f %.6f %.6f" % (cid[name], *yb))
            class_counts[name] += 1
        n_boxes += len(lines)
        n_empty += not lines
        (out_dir / "labels" / s / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        shutil.copyfile(img_src, out_dir / "images" / s / f"{stem}{img_src.suffix}")
        split_counts[s] += 1
        items.append((stem, s, img_src.suffix))

    (out_dir / "classes.txt").write_text("\n".join(classes) + "\n", encoding="utf-8")
    yaml = ["path: .", "train: images/train", "val: images/val", "test: images/test",
            f"nc: {len(classes)}", "names: [" + ", ".join(classes) + "]"]
    (out_dir / "data.yaml").write_text("\n".join(yaml) + "\n", encoding="utf-8")

    result = {"n_images": len(ann), "n_boxes": n_boxes, "n_skipped": n_skipped,
              "n_empty_images": n_empty, "classes": classes, "class_counts": class_counts,
              "split_counts": split_counts, "items": items, "out_dir": out_dir}
    if output_png:
        draw_check(result, viz_n, output_png, show)
    return result


def draw_check(result, viz_n, output_png, show=False):
    """Overlay the *written* YOLO labels on the first viz_n images (round-trip check)."""
    import matplotlib.pyplot as plt
    from matplotlib import patches

    out_dir, classes = result["out_dir"], result["classes"]
    items = result["items"][:max(1, viz_n)]
    cols = min(3, len(items))
    rows = -(-len(items) // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(3.6 * cols, 2.9 * rows), squeeze=False)
    colors = ["tab:green", "tab:red", "tab:blue", "tab:orange"]
    for ax in axes.ravel():
        ax.axis("off")
    for ax, (stem, s, ext) in zip(axes.ravel(), items):
        img = plt.imread(out_dir / "images" / s / f"{stem}{ext}")
        h, w = img.shape[:2]
        ax.imshow(img)
        for c, cx, cy, bw, bh in read_yolo(out_dir / "labels" / s / f"{stem}.txt"):
            ax.add_patch(patches.Rectangle(((cx - bw / 2) * w, (cy - bh / 2) * h), bw * w, bh * h,
                                           fill=False, edgecolor=colors[c % 4], linewidth=1.6))
            ax.text((cx - bw / 2) * w, (cy - bh / 2) * h - 2, classes[c], color=colors[c % 4], fontsize=7)
        ax.set_title(f"{stem} [{s}]", fontsize=8)
    fig.tight_layout()
    Path(output_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=110)
    if show:
        plt.show()
    plt.close(fig)


def format_summary(result):
    sc = result["split_counts"]
    lines = [f"images={result['n_images']} boxes={result['n_boxes']} skipped={result['n_skipped']} empty_images={result['n_empty_images']}",
             f"split train={sc['train']} val={sc['val']} test={sc['test']}"]
    lines += [f"class {c} id={i} boxes={result['class_counts'][c]}" for i, c in enumerate(result["classes"])]
    return "\n".join(lines)
