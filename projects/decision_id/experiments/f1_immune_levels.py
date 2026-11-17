"""
F1 — Tail-index-immune VaR/ES levels as a function of the degrees of freedom (Proposition 5)

전제:
  none (analytic)
출력:
  results/f1_immune_levels.csv
  figures/f1_immune_levels.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import optimize, stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_id import plotstyle as ps  # noqa: E402
from decision_id import tmodel as tm  # noqa: E402
from decision_id.utils import load_config  # noqa: E402


def unit(f, a, xi):
    """Functional of the unit-variance t with tail index xi."""
    return f(np.sqrt(1 - 2 * xi), xi, a)


def dxi(f, a, xi, h=1e-6):
    return (unit(f, a, xi + h) - unit(f, a, xi - h)) / (2 * h)


def main() -> None:
    cfg = load_config()
    ps.apply()
    nus = np.exp(np.linspace(np.log(2.6), np.log(500), 60))
    rows = []
    for nu in nus:
        xi = 1 / nu
        rows.append(
            {
                "nu": nu,
                "var_immune": optimize.brentq(lambda a, xi=xi: dxi(tm.var_, a, xi), 0.9, 0.9999),
                "es_immune": optimize.brentq(lambda a, xi=xi: dxi(tm.es_, a, xi), 0.5, 0.999),
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(cfg["paths"]["results"] / "f1_immune_levels.csv", index=False)
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    ax = axes[0]
    ax.plot(df.nu, df.var_immune, color=ps.SERIES[0], label="VaR immune level")
    ax.plot(df.nu, df.es_immune, color=ps.SERIES[1], label="ES immune level")
    for y, lab, c in [
        (stats.norm.cdf(np.sqrt(3)), "Phi(sqrt 3) = 0.958", ps.SERIES[0]),
        (stats.norm.cdf(1.0), "Phi(1) = 0.841", ps.SERIES[1]),
        (0.975, "Basel ES 97.5% / Weir 97.5%", ps.TEXT2),
        (0.99, "Basel VaR 99%", ps.TEXT2),
    ]:
        ax.axhline(y, color=c, lw=0.9, ls="--")
        ax.text(480, y + 0.003, lab, ha="right", fontsize=8, color=ps.TEXT2)
    ax.set_xscale("log")
    ax.set_xlabel("degrees of freedom nu (log)")
    ax.set_ylabel("level alpha with d(risk)/d(tail index) = 0 at fixed variance")
    ax.set_title("Which risk level is immune to the tail index?")
    ax.legend(loc="lower left")
    ax = axes[1]
    for c, a in zip(ps.SERIES, (0.95, 0.975, 0.99, 0.999), strict=False):
        q = [unit(tm.var_, a, 1 / n) / stats.norm.ppf(a) for n in nus]
        ax.plot(nus, q, color=c, label=f"VaR {a:.1%}")
    ax.axhline(1.0, color=ps.TEXT2, lw=0.9, ls="--")
    ax.set_xscale("log")
    ax.set_ylim(0.85, 1.6)
    ax.set_xlabel("degrees of freedom nu (log)")
    ax.set_ylabel("unit-variance t quantile / normal quantile")
    ax.set_title("Unit-variance t quantiles relative to the normal")
    ax.legend()
    ps.save(fig, cfg["paths"]["figures"] / "f1_immune_levels.png")
    print(df.iloc[[0, 10, 20, 30, 45, 59]].round(4).to_string(index=False))
    print("[DONE]")


if __name__ == "__main__":
    main()
