"""Clear-sky index (kt) per day and clear / cloudy / overcast classification.

Input CSV: ``date,hour,ghi`` -- ``date`` ISO yyyy-mm-dd, ``hour`` local SOLAR time
in decimal hours (0..24), ``ghi`` measured global horizontal irradiance in W/m^2.
Clear-sky model: Haurwitz, GHI_cs = 1098 * cosz * exp(-0.057 / cosz), with
Cooper's declination and hour angle 15 deg * (hour - 12).  Only samples with
cosz >= min_cosz (default 0.2) are used.  Daily index kt = sum(ghi)/sum(ghi_cs).
Classes: kt >= clear_thr -> "clear"; kt >= overcast_thr -> "cloudy"; else "overcast".
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import numpy as np

CLASSES = ("clear", "cloudy", "overcast")


def clearsky_ghi(day_of_year, hour, lat_deg):
    """Return (ghi_cs, cosz) for arrays of day_of_year and solar hour."""
    n = np.asarray(day_of_year, dtype=float)
    h = np.asarray(hour, dtype=float)
    decl = np.radians(23.45) * np.sin(2 * np.pi * (284 + n) / 365)
    lat = np.radians(lat_deg)
    cosz = np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(np.radians(15 * (h - 12)))
    cz = np.maximum(cosz, 1e-3)
    ghi_cs = np.where(cosz > 1e-3, 1098.0 * cz * np.exp(-0.057 / cz), 0.0)
    return ghi_cs, cosz


def load_table(csv_path):
    """Return (dates list[str], hour array, ghi array)."""
    dates, hours, ghi = [], [], []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                d = row["date"].strip()
                date.fromisoformat(d)
                hr, g = float(row["hour"]), float(row["ghi"])
            except (KeyError, ValueError) as exc:
                raise ValueError(f"bad row {row}: {exc}") from exc
            if not (np.isfinite(hr) and np.isfinite(g)) or g < 0 or not 0 <= hr <= 24:
                raise ValueError(f"invalid hour/ghi in row {row}")
            dates.append(d)
            hours.append(hr)
            ghi.append(g)
    if not dates:
        raise ValueError("empty CSV")
    return dates, np.array(hours), np.array(ghi)


def classify(kt, clear_thr=0.75, overcast_thr=0.35):
    if not kt == kt:
        return "n/a"
    return "clear" if kt >= clear_thr else ("cloudy" if kt >= overcast_thr else "overcast")


def pv_clearsky_index(csv_path, lat=25.0, clear_thr=0.75, overcast_thr=0.35,
                      min_cosz=0.2, output_csv=None, output_png=None, show=False):
    """Compute daily clear-sky index and sky type; optionally write CSV / figure."""
    if not 0 < overcast_thr < clear_thr:
        raise ValueError("need 0 < overcast_thr < clear_thr")
    dates, hours, ghi = load_table(csv_path)
    doy = np.array([date.fromisoformat(d).timetuple().tm_yday for d in dates])
    ghi_cs, cosz = clearsky_ghi(doy, hours, lat)
    use = cosz >= min_cosz
    days = list(dict.fromkeys(dates))
    kt = np.full(len(days), np.nan)
    sums = np.zeros((len(days), 2))
    for i, d in enumerate(days):
        m = use & (np.array(dates) == d)
        sums[i] = ghi[m].sum(), ghi_cs[m].sum()
        if sums[i, 1] > 0:
            kt[i] = sums[i, 0] / sums[i, 1]
    types = [classify(k, clear_thr, overcast_thr) for k in kt]
    result = {"dates": days, "kt": kt, "sky_type": types, "ghi_sum": sums[:, 0],
              "clearsky_sum": sums[:, 1], "counts": {c: types.count(c) for c in CLASSES},
              "lat": lat, "n_days": len(days)}
    if output_csv:
        Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "ghi_sum", "clearsky_sum", "kt", "sky_type"])
            for i, d in enumerate(days):
                w.writerow([d, f"{sums[i, 0]:.2f}", f"{sums[i, 1]:.2f}", f"{kt[i]:.4f}", types[i]])
    if output_png or show:
        _plot(result, dates, hours, ghi, ghi_cs, output_png, show)
    return result


def _plot(res, dates, hours, ghi, ghi_cs, output_png, show):
    import matplotlib.pyplot as plt

    colors = {"clear": "tab:orange", "cloudy": "tab:gray", "overcast": "tab:blue", "n/a": "k"}
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    darr = np.array(dates)
    for d, t in zip(res["dates"], res["sky_type"]):
        m = darr == d
        ax[0].plot(hours[m], ghi[m], color=colors[t], alpha=0.7, lw=1)
    first = darr == res["dates"][0]
    ax[0].plot(hours[first], ghi_cs[first], "k--", lw=1.2, label="clear-sky (day 1)")
    ax[0].set(xlabel="solar hour", ylabel="GHI (W/m$^2$)", title="Daily curves by sky type")
    ax[0].legend()
    ax[1].bar(range(res["n_days"]), np.nan_to_num(res["kt"]), color=[colors[t] for t in res["sky_type"]])
    ax[1].set(xlabel="day index", ylabel="clear-sky index kt", title="Daily kt")
    fig.tight_layout()
    if output_png:
        Path(output_png).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_png, dpi=120)
    if show:
        plt.show()
    plt.close(fig)


def format_summary(r):
    c = r["counts"]
    return (f"days={r['n_days']} clear={c['clear']} cloudy={c['cloudy']} overcast={c['overcast']}\n"
            f"kt={','.join(f'{k:.3f}' for k in r['kt'])}\n"
            f"types={','.join(r['sky_type'])}")
