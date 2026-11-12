"""Run the bess-tou-qlearn-toy demo on the synthetic TOU tariff."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tool_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tool_dir / "python"))
    from bess_tou_qlearn_toy import bess_tou_qlearn_toy

    out_dir = tool_dir / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = bess_tou_qlearn_toy(tool_dir / "examples" / "data" / "tou_prices.csv",
                            output_csv=out_dir / "schedule.csv")
    print(f"bess-tou-qlearn-toy: hours={len(r.prices)} n_soc={r.n_soc} "
          f"greedy_cost={r.greedy_cost:.2f} learned_cost={r.learned_cost:.2f} yuan")
    h = range(len(r.prices) + 1)
    fig, ax = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    ax[0].step(range(len(r.prices)), r.prices, where="post")
    ax[0].set_ylabel("price (yuan/kWh)")
    ax[1].step(h, r.greedy_soc, where="post", label="greedy")
    ax[1].step(h, r.learned_soc, where="post", label="Q-learning")
    ax[1].set_xlabel("hour")
    ax[1].set_ylabel("SOC level")
    ax[1].legend()
    fig.tight_layout()
    png = out_dir / "bess_tou_qlearn_toy_demo.png"
    fig.savefig(png, dpi=120)
    print(f"saved {png}")
    print(f"saved {r.output_csv}")


if __name__ == "__main__":
    main()
