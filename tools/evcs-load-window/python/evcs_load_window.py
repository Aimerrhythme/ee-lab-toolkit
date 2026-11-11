"""Clean EV charging-session records, resample to a station load, cut windows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class EvcsWindowResult:
    time: pd.DatetimeIndex      # start of each bin
    load_kw: np.ndarray         # time-weighted mean station power per bin
    X: np.ndarray               # (n_windows, input_len) inputs
    y: np.ndarray               # (n_windows, horizon) targets
    window_start: pd.DatetimeIndex  # time of the first input bin per window
    n_sessions: int             # rows read
    n_dropped: int              # rows rejected by cleaning
    step_min: float
    output_csv: str = ""


def evcs_load_window(
    csv_path,
    step_min: float = 15.0,
    input_len: int = 8,
    horizon: int = 4,
    stride: int = 4,
    max_power_kw: float = 150.0,
    output_csv=None,
) -> EvcsWindowResult:
    """Read sessions (session_id,start_time,end_time,power_kw), return windows.

    A row is dropped if a field is missing/unparseable, end <= start, or
    power_kw is not in (0, max_power_kw]. Each kept session adds power_kw to
    every bin in proportion to its overlap with the bin, so a bin value is the
    mean station power (kW) over that bin.
    """
    if step_min <= 0 or input_len < 1 or horizon < 1 or stride < 1:
        raise ValueError("step_min, input_len, horizon, stride must be positive")
    df = pd.read_csv(csv_path)
    n_sessions = len(df)
    start = pd.to_datetime(df["start_time"], errors="coerce")
    end = pd.to_datetime(df["end_time"], errors="coerce")
    p = pd.to_numeric(df["power_kw"], errors="coerce").to_numpy(float)
    ok = (
        start.notna().to_numpy()
        & end.notna().to_numpy()
        & np.isfinite(p)
        & (p > 0)
        & (p <= max_power_kw)
    )
    ok &= (end > start).to_numpy()
    n_dropped = int((~ok).sum())
    if not ok.any():
        raise ValueError("no valid sessions after cleaning")
    start, end, p = start[ok], end[ok], p[ok]

    origin = start.min().floor(f"{int(round(step_min * 60))}s")
    s_min = ((start - origin).dt.total_seconds() / 60.0).to_numpy()
    e_min = ((end - origin).dt.total_seconds() / 60.0).to_numpy()
    nbins = int(np.ceil(e_min.max() / step_min))
    energy = np.zeros(nbins)  # kW * min
    for s, e, pw in zip(s_min, e_min, p):
        b0, b1 = int(s // step_min), int(np.ceil(e / step_min))
        for b in range(b0, min(b1, nbins)):
            lo, hi = max(s, b * step_min), min(e, (b + 1) * step_min)
            if hi > lo:
                energy[b] += pw * (hi - lo)
    load = energy / step_min
    time = origin + pd.to_timedelta(np.arange(nbins) * step_min, unit="min")

    span = input_len + horizon
    nwin = (nbins - span) // stride + 1 if nbins >= span else 0
    X = np.zeros((nwin, input_len))
    y = np.zeros((nwin, horizon))
    for k in range(nwin):
        i = k * stride
        X[k] = load[i : i + input_len]
        y[k] = load[i + input_len : i + span]
    wstart = time[[k * stride for k in range(nwin)]] if nwin else time[:0]
    res = EvcsWindowResult(time, load, X, y, wstart, n_sessions, n_dropped, step_min)
    if output_csv is not None:
        res.output_csv = write_windows_csv(res, output_csv)
    return res


def write_windows_csv(res: EvcsWindowResult, path) -> str:
    """Columns: window_start, x_0..x_{L-1}, y_0..y_{H-1} (kW, 3 decimals)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [f"x_{i}" for i in range(res.X.shape[1])] + [
        f"y_{i}" for i in range(res.y.shape[1])
    ]
    out = pd.DataFrame(np.hstack([res.X, res.y]), columns=cols).round(3)
    out.insert(0, "window_start", res.window_start.strftime("%Y-%m-%d %H:%M:%S"))
    out.to_csv(path, index=False)
    return str(path)
