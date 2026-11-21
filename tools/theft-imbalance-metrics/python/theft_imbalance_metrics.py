"""Confusion matrix, ROC, PR, F1 and threshold sweep for imbalanced theft detection.

CSV: first column ``y_true`` (0 = normal, 1 = theft), then one or more score
columns (higher = more suspicious). Rule: predict theft when score >= threshold.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

COLUMNS = ["model", "operating_point", "threshold", "tp", "fp", "fn", "tn",
           "accuracy", "precision", "recall", "f1", "balanced_acc", "roc_auc", "ap"]


def load_scores(csv_path):
    """Return (y, names, S): y int 0/1 (n,), names list, S float (n, m)."""
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    header = [h.strip() for h in rows[0]]
    if len(header) < 2 or header[0] != "y_true":
        raise ValueError("first column must be y_true, followed by >=1 score column")
    body = rows[1:]
    if not body:
        raise ValueError("no data rows")
    try:
        data = np.array([[float(v) for v in r] for r in body], dtype=float)
    except ValueError as exc:
        raise ValueError("all cells must be numeric (no blank/text)") from exc
    if data.shape[1] != len(header) or not np.all(np.isfinite(data)):
        raise ValueError("ragged rows or non-finite values")
    y = data[:, 0]
    if not np.all((y == 0) | (y == 1)):
        raise ValueError("y_true must be 0 or 1")
    y = y.astype(int)
    if y.sum() == 0 or y.sum() == len(y):
        raise ValueError("y_true needs both classes")
    return y, header[1:], data[:, 1:]


def confusion_at(y, score, threshold):
    pred = np.asarray(score) >= threshold
    y = np.asarray(y).astype(bool)
    return (int(np.sum(pred & y)), int(np.sum(pred & ~y)),
            int(np.sum(~pred & y)), int(np.sum(~pred & ~y)))


def rates(tp, fp, fn, tn):
    """accuracy, precision (0 if nothing flagged), recall, f1, balanced accuracy."""
    n = tp + fp + fn + tn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
    tnr = tn / (tn + fp) if tn + fp else 0.0
    return {"accuracy": (tp + tn) / n, "precision": precision, "recall": recall,
            "f1": f1, "balanced_acc": (recall + tnr) / 2}


def curve_points(y, score):
    """One point per distinct score value, thresholds descending.

    Returns dict with thresholds, tp, fp, tpr, fpr, precision, f1.
    """
    y = np.asarray(y).astype(int)
    s = np.asarray(score, dtype=float)
    order = np.argsort(-s, kind="stable")
    ys, ss = y[order], s[order]
    last = np.append(np.flatnonzero(np.diff(ss) != 0), len(ss) - 1)
    tp = np.cumsum(ys)[last].astype(float)
    npred = (last + 1).astype(float)
    fp = npred - tp
    pos = float(y.sum())
    neg = float(len(y) - y.sum())
    return {"thresholds": ss[last], "tp": tp, "fp": fp, "tpr": tp / pos,
            "fpr": fp / neg, "precision": tp / npred, "f1": 2 * tp / (npred + pos)}


def roc_auc(y, score):
    c = curve_points(y, score)
    fpr = np.concatenate(([0.0], c["fpr"]))
    tpr = np.concatenate(([0.0], c["tpr"]))
    return float(np.sum(np.diff(fpr) * (tpr[1:] + tpr[:-1]) / 2))


def average_precision(y, score):
    """AP = sum (R_k - R_{k-1}) * P_k over distinct thresholds (step-wise)."""
    c = curve_points(y, score)
    recall = np.concatenate(([0.0], c["tpr"]))
    return float(np.sum(np.diff(recall) * c["precision"]))


def best_f1_threshold(y, score):
    """Highest threshold that attains the maximum F1 on this data."""
    c = curve_points(y, score)
    k = int(np.argmax(c["f1"]))  # first max = highest threshold
    return float(c["thresholds"][k])


def _row(model, point, thr, y, s, auc, ap):
    tp, fp, fn, tn = confusion_at(y, s, thr)
    r = rates(tp, fp, fn, tn)
    return {"model": model, "operating_point": point, "threshold": float(thr),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn, **r, "roc_auc": auc, "ap": ap}


def theft_imbalance_metrics(csv_path, threshold=0.5, output_csv=None,
                            output_png=None, show=False):
    """Evaluate every score column at a fixed and at the best-F1 threshold."""
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be in [0, 1]")
    y, names, S = load_scores(csv_path)
    n, npos = len(y), int(y.sum())
    rows = [_row("always_normal", "fixed", 1.0 + 1e-12, y, np.zeros(n), 0.5, npos / n)]
    curves, metrics = {}, {}
    for j, name in enumerate(names):
        s = S[:, j]
        auc, ap = roc_auc(y, s), average_precision(y, s)
        curves[name] = curve_points(y, s)
        metrics[name] = {
            "fixed": _row(name, "fixed", threshold, y, s, auc, ap),
            "best_f1": _row(name, "best_f1", best_f1_threshold(y, s), y, s, auc, ap)}
        rows += [metrics[name]["fixed"], metrics[name]["best_f1"]]
    # always_normal: never flags anyone; report threshold as NaN-free 1.0 for CSV
    rows[0]["threshold"] = 1.0
    result = {"n": n, "n_pos": npos, "prevalence": npos / n, "threshold": threshold,
              "models": names, "rows": rows, "metrics": metrics,
              "always_normal_accuracy": 1 - npos / n, "curves": curves,
              "y": y, "scores": S}
    if output_csv:
        write_rows(output_csv, rows)
    if output_png or show:
        plot_all(result, output_png, show)
    return result


def write_rows(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fh.write(",".join(COLUMNS) + "\n")
        for r in rows:
            fh.write(_fmt_row(r) + "\n")


def _fmt_row(r):
    out = []
    for c in COLUMNS:
        v = r[c]
        if c in ("model", "operating_point"):
            out.append(str(v))
        elif c in ("tp", "fp", "fn", "tn"):
            out.append(str(int(v)))
        else:
            out.append(f"{v:.4f}")
    return ",".join(out)


def format_summary(result):
    lines = [f"n={result['n']} positives={result['n_pos']} "
             f"prevalence={result['prevalence']:.4f} threshold={result['threshold']:.2f}",
             f"always_normal_accuracy={result['always_normal_accuracy']:.4f}",
             ",".join(COLUMNS)]
    lines += [_fmt_row(r) for r in result["rows"]]
    return "\n".join(lines)


def plot_all(result, output_png=None, show=False):
    import matplotlib.pyplot as plt

    y, names = result["y"], result["models"]
    fig, ax = plt.subplots(2, 2, figsize=(10, 8))
    for name in names:
        c = result["curves"][name]
        m = result["metrics"][name]["fixed"]
        ax[0, 0].plot(np.r_[0, c["fpr"]], np.r_[0, c["tpr"]],
                      label=f"{name} (AUC {m['roc_auc']:.3f})")
        ax[0, 1].plot(c["tpr"], c["precision"], label=f"{name} (AP {m['ap']:.3f})")
        ax[1, 0].plot(c["thresholds"], c["f1"], label=name)
    ax[0, 0].plot([0, 1], [0, 1], "k:", lw=1)
    ax[0, 0].set(title="ROC (looks good even when imbalanced)", xlabel="FPR", ylabel="TPR")
    ax[0, 1].axhline(result["prevalence"], color="k", ls=":", lw=1, label="prevalence")
    ax[0, 1].set(title="PR curve", xlabel="Recall", ylabel="Precision")
    ax[1, 0].axvline(result["threshold"], color="k", ls=":", lw=1)
    ax[1, 0].set(title="F1 vs threshold", xlabel="threshold", ylabel="F1")
    for a in (ax[0, 0], ax[0, 1], ax[1, 0]):
        a.legend(fontsize=8)
        a.grid(alpha=0.3)
    first = result["metrics"][names[0]]["fixed"]
    cm = np.array([[first["tn"], first["fp"]], [first["fn"], first["tp"]]])
    ax[1, 1].imshow(cm, cmap="Blues")
    for (i, j), v in np.ndenumerate(cm):
        ax[1, 1].text(j, i, str(v), ha="center", va="center")
    ax[1, 1].set(title=f"confusion: {names[0]} @ {result['threshold']:.2f}",
                 xticks=[0, 1], yticks=[0, 1], xticklabels=["pred 0", "pred 1"],
                 yticklabels=["true 0", "true 1"])
    fig.tight_layout()
    if output_png:
        Path(output_png).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_png, dpi=120)
    if show:
        plt.show()
    plt.close(fig)
