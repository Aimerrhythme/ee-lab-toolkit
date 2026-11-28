"""Load ETT-format CSV, split chronologically, scale with TRAIN statistics, cut windows.

Teaching tool. Layout of the CSV: date,HUFL,HULL,MUFL,MULL,LUFL,LULL,OT.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field

import numpy as np

__all__ = ["WindowSet", "ETTWindows", "load_ett_csv", "split_bounds", "make_windows", "load_and_window"]


@dataclass
class WindowSet:
    """X: (n, input_len, n_features), Y: (n, pred_len) target in scaled units."""

    X: np.ndarray
    Y: np.ndarray
    start: np.ndarray  # row index (in the full file) of the first input step


@dataclass
class ETTWindows:
    train: WindowSet
    val: WindowSet
    test: WindowSet
    columns: list
    target: str
    mean: np.ndarray  # TRAIN-only mean per column
    std: np.ndarray   # TRAIN-only std (ddof=0) per column
    bounds: tuple     # (n_train, n_train + n_val, n_rows)
    dates: list = field(default_factory=list)

    def inverse_target(self, y):
        """Convert scaled target values back to the original unit (deg C for OT)."""
        j = self.columns.index(self.target)
        return np.asarray(y) * self.std[j] + self.mean[j]

    def summary(self) -> str:
        return (
            f"ett-window-loader: rows={self.bounds[2]} target={self.target} "
            f"train={len(self.train.X)} val={len(self.val.X)} test={len(self.test.X)} "
            f"windows, train_{self.target}_mean={self.mean[self.columns.index(self.target)]:.4f}"
        )


def load_ett_csv(csv_path):
    """Return (dates, columns, data) with data a float array (rows, columns); date column dropped."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        if header[0].lower() != "date":
            raise ValueError("first column must be 'date'")
        dates, rows = [], []
        for r in reader:
            if not r:
                continue
            dates.append(r[0])
            rows.append([float(v) for v in r[1:]])
    data = np.asarray(rows, dtype=float)
    if np.isnan(data).any():
        raise ValueError("NaN found; clean the file first")
    if list(dates) != sorted(dates):
        raise ValueError("dates must be in ascending order")
    return dates, header[1:], data


def split_bounds(n_rows, split=(0.6, 0.2, 0.2)):
    """Chronological row boundaries (n_train, n_train + n_val, n_rows)."""
    s = np.asarray(split, dtype=float)
    if s.shape != (3,) or (s <= 0).any() or abs(s.sum() - 1.0) > 1e-9:
        raise ValueError("split must be 3 positive fractions summing to 1")
    n_train = int(np.floor(n_rows * s[0]))
    n_val = int(np.floor(n_rows * s[1]))
    return n_train, n_train + n_val, n_rows


def make_windows(data, target_idx, input_len, pred_len, stride=1, offset=0):
    """Cut windows inside ONE segment. X = all columns over input_len steps,
    Y = target over the next pred_len steps. offset = row index of data[0] in the file."""
    n = data.shape[0]
    n_win = (n - input_len - pred_len) // stride + 1 if n >= input_len + pred_len else 0
    X = np.empty((n_win, input_len, data.shape[1]))
    Y = np.empty((n_win, pred_len))
    start = np.empty(n_win, dtype=int)
    for k in range(n_win):
        s = k * stride
        X[k] = data[s : s + input_len]
        Y[k] = data[s + input_len : s + input_len + pred_len, target_idx]
        start[k] = offset + s
    return WindowSet(X, Y, start)


def load_and_window(csv_path, input_len, pred_len, split=(0.6, 0.2, 0.2), target="OT", stride=1):
    """Load an ETT CSV and return train/val/test windows scaled with TRAIN-only mean/std.

    Windows never straddle a split boundary, so no val/test row is ever used as
    input or label of a train window (and vice versa).
    """
    if input_len < 1 or pred_len < 1 or stride < 1:
        raise ValueError("input_len, pred_len and stride must be >= 1")
    dates, columns, data = load_ett_csv(csv_path)
    if target not in columns:
        raise ValueError(f"target {target!r} not in columns {columns}")
    b1, b2, b3 = split_bounds(len(data), split)
    train_raw = data[:b1]
    mean = train_raw.mean(axis=0)
    std = train_raw.std(axis=0)
    std[std == 0] = 1.0
    scaled = (data - mean) / std
    j = columns.index(target)
    segs = {"train": (0, b1), "val": (b1, b2), "test": (b2, b3)}
    sets = {
        k: make_windows(scaled[a:b], j, input_len, pred_len, stride, offset=a)
        for k, (a, b) in segs.items()
    }
    return ETTWindows(sets["train"], sets["val"], sets["test"], columns, target, mean, std, (b1, b2, b3), dates)
