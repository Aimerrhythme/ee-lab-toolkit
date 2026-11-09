"""Write the synthetic DGA CSV (deterministic LCG; no real transformer data)."""

from __future__ import annotations

import math
from pathlib import Path

CLASSES = ["PD", "D1", "D2", "T1", "T2", "T3"]
# Typical ppm [H2, CH4, C2H6, C2H4, C2H2] per fault family (classroom values).
PROFILE = {
    "PD": [800, 60, 60, 10, 1],
    "D1": [300, 90, 20, 40, 80],
    "D2": [200, 100, 25, 150, 150],
    "T1": [50, 150, 200, 60, 0.5],
    "T2": [40, 200, 100, 250, 5],
    "T3": [40, 300, 60, 600, 30],
}
PER_CLASS = 24
SIGMA = 0.45
OUT = Path(__file__).resolve().parent / "data" / "synthetic_dga_ppm.csv"


def write_csv(path: Path = OUT) -> None:
    state = 12345

    def uniform() -> float:
        nonlocal state
        state = (1664525 * state + 1013904223) % 4294967296
        return state / 4294967296

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["sample_id,h2_ppm,ch4_ppm,c2h6_ppm,c2h4_ppm,c2h2_ppm,label,split"]
    n = 0
    for k in range(PER_CLASS):
        for name in CLASSES:
            n += 1
            gases = []
            for base in PROFILE[name]:
                z = (uniform() + uniform() + uniform() - 1.5) * 2  # roughly N(0, 1)
                gases.append(max(0.1, round(base * math.exp(SIGMA * z), 1)))
            split = "test" if k % 4 == 3 else "train"
            lines.append(f"S{n:03d}," + ",".join(f"{g:.1f}" for g in gases) + f",{name},{split}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_csv()
    print(f"wrote {OUT}")
