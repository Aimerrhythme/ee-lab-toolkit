"""IEC 60599 three-ratio rules versus a small random forest on DGA samples.

The algorithm matches ``matlab/dga_ratio_vs_rf.m``. NumPy only: no scikit-learn,
no Statistics Toolbox. Randomness comes from a shared 32-bit LCG, so a fixed
``seed`` gives the same forest in both runtimes.

Features for the forest are log10(1 + ppm) of H2, CH4, C2H6, C2H4, C2H2.
The rule uses ratios R1 = C2H2/C2H4, R2 = CH4/H2, R3 = C2H4/C2H6 with each
gas floored at 0.1 ppm (a detection-limit stand-in).

Teaching tool only; the ratio table is a simplified classroom version.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

CLASSES = ["PD", "D1", "D2", "T1", "T2", "T3"]
GASES = ["H2", "CH4", "C2H6", "C2H4", "C2H2"]
ND = "ND"
GAS_FLOOR = 0.1
_COLS = ["h2_ppm", "ch4_ppm", "c2h6_ppm", "c2h4_ppm", "c2h2_ppm"]
_LCG_A, _LCG_C, _LCG_M = 1664525, 1013904223, 4294967296
_PARAMS = {"n_trees", "max_depth", "mtry", "min_samples_split", "seed",
           "output_csv", "output_png", "show"}


class _Lcg:
    def __init__(self, seed: int) -> None:
        self.state = int(seed) % _LCG_M

    def randint(self, n: int) -> int:
        self.state = (_LCG_A * self.state + _LCG_C) % _LCG_M
        return int(math.floor(self.state / _LCG_M * n))


def ratios(gas_ppm) -> np.ndarray:
    """Return rows of [R1, R2, R3] for gas rows [H2, CH4, C2H6, C2H4, C2H2]."""
    g = np.maximum(np.atleast_2d(np.asarray(gas_ppm, dtype=float)), GAS_FLOOR)
    return np.column_stack([g[:, 4] / g[:, 3], g[:, 1] / g[:, 0], g[:, 3] / g[:, 2]])


def iec_rule(r1: float, r2: float, r3: float) -> str:
    """Simplified IEC 60599 ratio table; first match wins, else ``ND``."""
    if r2 < 0.1 and r3 < 0.2:
        return "PD"
    if r1 > 1 and 0.1 <= r2 <= 0.5 and r3 > 1:
        return "D1"
    if 0.6 <= r1 <= 2.5 and 0.1 <= r2 <= 1 and r3 > 2:
        return "D2"
    if r2 > 1 and r3 < 1:
        return "T1"
    if r1 < 0.1 and r2 > 1 and 1 <= r3 <= 4:
        return "T2"
    if r1 < 0.2 and r2 > 1 and r3 > 4:
        return "T3"
    return ND


def _gini_sum(counts: np.ndarray) -> float:
    n = 0.0
    sq = 0.0
    for c in counts:
        n += c
        sq += c * c
    return 0.0 if n == 0 else n - sq / n


@dataclass
class _Tree:
    feature: list = field(default_factory=list)
    thr: list = field(default_factory=list)
    left: list = field(default_factory=list)
    right: list = field(default_factory=list)
    prob: list = field(default_factory=list)

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        node = 0
        while self.feature[node] >= 0:
            node = self.left[node] if x[self.feature[node]] <= self.thr[node] else self.right[node]
        return self.prob[node]


def _grow(x, y, idx, depth, tree, rng, max_depth, mtry, min_split, importance, k):
    node = len(tree.feature)
    counts = np.array([np.sum(y[idx] == c) for c in range(k)], dtype=float)
    tree.feature.append(-1)
    tree.thr.append(0.0)
    tree.left.append(-1)
    tree.right.append(-1)
    tree.prob.append(counts / counts.sum())
    n = len(idx)
    parent = _gini_sum(counts)
    if parent == 0 or n < min_split or depth >= max_depth:
        return node
    nf = x.shape[1]
    order = list(range(nf))
    for i in range(mtry):
        j = i + rng.randint(nf - i)
        order[i], order[j] = order[j], order[i]
    best = (math.inf, -1, 0.0)
    for f in order[:mtry]:
        srt = idx[np.argsort(x[idx, f], kind="stable")]
        vals = x[srt, f]
        lc = np.zeros(k)
        rc = counts.copy()
        for p in range(n - 1):
            lab = y[srt[p]]
            lc[lab] += 1
            rc[lab] -= 1
            if vals[p] == vals[p + 1]:
                continue
            score = _gini_sum(lc) + _gini_sum(rc)
            if score < best[0]:
                best = (score, f, (vals[p] + vals[p + 1]) / 2)
    if best[1] < 0:
        return node
    score, f, thr = best
    importance[f] += parent - score
    mask = x[idx, f] <= thr
    tree.feature[node] = f
    tree.thr[node] = thr
    tree.left[node] = _grow(x, y, idx[mask], depth + 1, tree, rng, max_depth, mtry, min_split, importance, k)
    tree.right[node] = _grow(x, y, idx[~mask], depth + 1, tree, rng, max_depth, mtry, min_split, importance, k)
    return node


def fit_forest(x, y, n_trees=50, max_depth=6, mtry=2, min_samples_split=2, seed=0, n_classes=len(CLASSES)):
    """Fit a bootstrap random forest. Returns (trees, importance summing to 1)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=int)
    n = len(y)
    importance = np.zeros(x.shape[1])
    trees = []
    for t in range(n_trees):
        rng = _Lcg(seed + t)
        boot = np.array([rng.randint(n) for _ in range(n)], dtype=int)
        tree = _Tree()
        _grow(x, y, boot, 0, tree, rng, max_depth, mtry, min_samples_split, importance, n_classes)
        trees.append(tree)
    total = importance.sum()
    return trees, importance / total if total > 0 else importance


def predict_forest(trees, x):
    """Mean leaf probabilities over trees; label is the first arg-max."""
    x = np.atleast_2d(np.asarray(x, dtype=float))
    prob = np.zeros((len(x), len(trees[0].prob[0])))
    for tree in trees:
        for i in range(len(x)):
            prob[i] += tree.predict_proba(x[i])
    prob /= len(trees)
    return prob.argmax(axis=1), prob


def read_samples(path):
    """Read the CSV schema: sample_id,h2_ppm,ch4_ppm,c2h6_ppm,c2h4_ppm,c2h2_ppm,label,split."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"CSV not found: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError("CSV has no data rows")
    need = ["sample_id", *_COLS, "label", "split"]
    missing = [c for c in need if c not in rows[0]]
    if missing:
        raise ValueError(f"CSV missing columns: {', '.join(missing)}")
    ids = [r["sample_id"] for r in rows]
    gas = np.array([[float(r[c]) for c in _COLS] for r in rows])
    if not np.all(np.isfinite(gas)) or np.any(gas < 0):
        raise ValueError("gas concentrations must be finite and non-negative")
    labels = []
    for r in rows:
        if r["label"] not in CLASSES:
            raise ValueError(f"unknown label {r['label']!r}; expected one of {CLASSES}")
        labels.append(CLASSES.index(r["label"]))
    split = [r["split"] for r in rows]
    if any(s not in ("train", "test") for s in split):
        raise ValueError("split must be train or test")
    return ids, gas, np.array(labels, dtype=int), split


def confusion(true_idx, pred_idx, n_cols):
    m = np.zeros((len(CLASSES), n_cols), dtype=int)
    for t, p in zip(true_idx, pred_idx):
        m[t, p] += 1
    return m


@dataclass
class DgaResult:
    sample_ids: list
    split: list
    true_label: list
    rule_label: list
    rf_label: list
    rf_prob: np.ndarray
    ratios: np.ndarray
    confusion_rule: np.ndarray
    confusion_rf: np.ndarray
    importance: np.ndarray
    acc_rule: float
    acc_rf: float
    rule_nd_fraction: float
    n_train: int
    n_test: int
    n_trees: int
    max_depth: int
    mtry: int
    seed: int
    summary: str = ""
    output_csv: str | None = None
    output_png: str | None = None
    fig: object = None


def dga_ratio_vs_rf(csv_path, **kwargs):
    """Compare the IEC three-ratio rule and a random forest on the test split."""
    bad = set(kwargs) - _PARAMS
    if bad:
        raise ValueError(f"unknown parameter name: {sorted(bad)[0]}")
    n_trees = kwargs.get("n_trees", 50)
    max_depth = kwargs.get("max_depth", 6)
    mtry = kwargs.get("mtry", 2)
    min_split = kwargs.get("min_samples_split", 2)
    seed = kwargs.get("seed", 0)
    show = kwargs.get("show", False)
    for name, val in (("n_trees", n_trees), ("max_depth", max_depth), ("mtry", mtry),
                      ("min_samples_split", min_split)):
        if not isinstance(val, int) or isinstance(val, bool) or val < 1:
            raise ValueError(f"{name} must be a positive integer")
    if mtry > len(GASES):
        raise ValueError("mtry must not exceed 5")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if not isinstance(show, bool):
        raise ValueError("show must be true or false")

    ids, gas, y, split = read_samples(csv_path)
    tr = np.array([s == "train" for s in split])
    te = ~tr
    if not tr.any() or not te.any():
        raise ValueError("need at least one train and one test sample")
    feats = np.log10(1.0 + gas)
    trees, importance = fit_forest(feats[tr], y[tr], n_trees, max_depth, mtry, min_split, seed)
    pred, prob = predict_forest(trees, feats)
    rat = ratios(gas)
    rule_names = [iec_rule(*r) for r in rat]
    rule_idx = np.array([len(CLASSES) if r == ND else CLASSES.index(r) for r in rule_names])

    conf_rule = confusion(y[te], rule_idx[te], len(CLASSES) + 1)
    conf_rf = confusion(y[te], pred[te], len(CLASSES))
    acc_rule = float(np.mean(rule_idx[te] == y[te]))
    acc_rf = float(np.mean(pred[te] == y[te]))
    nd = float(np.mean(rule_idx[te] == len(CLASSES)))

    res = DgaResult(
        sample_ids=ids, split=split,
        true_label=[CLASSES[i] for i in y], rule_label=rule_names,
        rf_label=[CLASSES[i] for i in pred], rf_prob=prob.max(axis=1), ratios=rat,
        confusion_rule=conf_rule, confusion_rf=conf_rf, importance=importance,
        acc_rule=acc_rule, acc_rf=acc_rf, rule_nd_fraction=nd,
        n_train=int(tr.sum()), n_test=int(te.sum()), n_trees=n_trees,
        max_depth=max_depth, mtry=mtry, seed=seed,
    )
    res.summary = format_table(res)
    out_csv = kwargs.get("output_csv")
    if out_csv:
        out_csv = Path(out_csv)
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with out_csv.open("w", newline="", encoding="utf-8") as fh:
            fh.write("sample_id,split,true,rule,rf,rf_prob,r1,r2,r3\n")
            for i in range(len(ids)):
                fh.write(f"{ids[i]},{split[i]},{res.true_label[i]},{rule_names[i]},"
                         f"{res.rf_label[i]},{res.rf_prob[i]:.4f},"
                         f"{rat[i, 0]:.4f},{rat[i, 1]:.4f},{rat[i, 2]:.4f}\n")
        res.output_csv = str(out_csv)
    out_png = kwargs.get("output_png")
    if out_png or show:
        res.fig = _plot(res)
        if out_png:
            Path(out_png).parent.mkdir(parents=True, exist_ok=True)
            res.fig.savefig(out_png, dpi=120)
            res.output_png = str(out_png)
        if not show:
            import matplotlib.pyplot as plt
            plt.close(res.fig)
            res.fig = None
    return res


def format_table(res: DgaResult) -> str:
    lines = [
        f"train={res.n_train}  test={res.n_test}  n_trees={res.n_trees}  max_depth={res.max_depth}  "
        f"mtry={res.mtry}  seed={res.seed}",
        f"accuracy_test  rule={res.acc_rule:.4f}  rf={res.acc_rf:.4f}  rule_nd_fraction={res.rule_nd_fraction:.4f}",
        "",
        "importance " + "  ".join(f"{g}={v:.4f}" for g, v in zip(GASES, res.importance)),
        "",
        "confusion_rule (rows true, cols " + ",".join(CLASSES + [ND]) + ")",
    ]
    lines += ["  " + CLASSES[i] + " " + " ".join(f"{v:3d}" for v in row) for i, row in enumerate(res.confusion_rule)]
    lines += ["", "confusion_rf (rows true, cols " + ",".join(CLASSES) + ")"]
    lines += ["  " + CLASSES[i] + " " + " ".join(f"{v:3d}" for v in row) for i, row in enumerate(res.confusion_rf)]
    return "\n".join(lines)


def _plot(res: DgaResult):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    for ax, mat, cols, title in (
        (axes[0], res.confusion_rule, CLASSES + [ND], f"IEC ratio rule (acc={res.acc_rule:.2f})"),
        (axes[1], res.confusion_rf, CLASSES, f"Random forest (acc={res.acc_rf:.2f})"),
    ):
        ax.imshow(mat, cmap="Blues")
        ax.set_xticks(range(len(cols)), cols)
        ax.set_yticks(range(len(CLASSES)), CLASSES)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("True")
        ax.set_title(title)
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                ax.text(j, i, str(mat[i, j]), ha="center", va="center", fontsize=8)
    axes[2].bar(GASES, res.importance, color="tab:green")
    axes[2].set_ylabel("Gini importance (sum = 1)")
    axes[2].set_title("Gas feature importance")
    fig.tight_layout()
    return fig
