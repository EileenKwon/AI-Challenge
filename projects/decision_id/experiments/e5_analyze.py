"""
E5 analysis — allocation policy comparison

전제:
  results/e5_allocation.csv  (from e5_allocation.py)
출력:
  results/e5_summary.csv
  figures/e5_regret_ratio.png
  reports/e5_allocation.md
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_id import plotstyle as ps  # noqa: E402
from decision_id.utils import load_config  # noqa: E402

SEED = 42
POLICIES = ["uniform", "own_only", "dopt", "predictive", "dr_local", "dr_prepost"]


def boot_ratio(a: np.ndarray, b: np.ndarray, rng, B: int = 2000) -> tuple[float, float, float]:
    """Paired bootstrap of mean(a)/mean(b) with a 90% percentile interval."""
    n = len(a)
    idx = rng.integers(0, n, (B, n))
    r = a[idx].mean(1) / np.maximum(b[idx].mean(1), 1e-300)
    return (
        float(a.mean() / max(b.mean(), 1e-300)),
        float(np.quantile(r, 0.05)),
        float(np.quantile(r, 0.95)),
    )


def main() -> None:
    t0 = time.time()
    print("=== E5 analysis ===")
    cfg = load_config()
    raw = cfg["paths"]["results"] / "e5_allocation.csv"
    if not raw.exists():
        print(f"[ERR] missing {raw}; run e5_allocation.py first")
        sys.exit(1)
    ps.apply()
    rng = np.random.default_rng(SEED)
    df = pd.read_csv(raw)
    # keep target-matched DR runs; baselines are target-agnostic
    keep = (df.policy_target == "-") | (df.policy_target == df.eval_target)
    d = df[keep].copy()
    rows = []
    for (et, nu, n0), s in d.groupby(["eval_target", "nu", "n0"]):
        piv = s.pivot_table(index="rep", columns="policy", values="regret")
        base = piv["uniform"].values
        for p in POLICIES:
            r, lo, hi = boot_ratio(piv[p].values, base, rng)
            win = float(np.mean(piv[p].values < piv["dopt"].values)) if p != "dopt" else np.nan
            rows.append(
                {
                    "eval_target": et,
                    "nu": nu,
                    "n0": n0,
                    "policy": p,
                    "ratio_vs_uniform": r,
                    "lo90": lo,
                    "hi90": hi,
                    "mean_regret": float(piv[p].mean()),
                    "win_vs_dopt": win,
                }
            )
    summ = pd.DataFrame(rows)
    summ.to_csv(cfg["paths"]["results"] / "e5_summary.csv", index=False)
    pooled = []
    for et, s in d.groupby("eval_target"):
        piv = s.pivot_table(index=["nu", "n0", "rep"], columns="policy", values="regret")
        # normalize each condition by its uniform mean so conditions weigh equally
        norm = piv.groupby(level=["nu", "n0"]).transform(lambda c: c)  # placeholder copy
        cm = piv["uniform"].groupby(level=["nu", "n0"]).transform("mean")
        norm = piv.div(cm, axis=0)
        for p in POLICIES:
            r, lo, hi = boot_ratio(norm[p].values, norm["uniform"].values, rng)
            pooled.append(
                {
                    "eval_target": et,
                    "policy": p,
                    "ratio_vs_uniform": r,
                    "lo90": lo,
                    "hi90": hi,
                    "win_vs_dopt": float(np.mean(piv[p] < piv["dopt"])) if p != "dopt" else np.nan,
                    "win_vs_predictive": float(np.mean(piv[p] < piv["predictive"]))
                    if p != "predictive"
                    else np.nan,
                }
            )
    pooled = pd.DataFrame(pooled)
    sec = (
        d.groupby(["eval_target", "policy"])[["cover", "err_xi", "kl", "n_own", "n_peer", "n_rv"]]
        .mean()
        .reset_index()
    )
    h6 = []
    for (et, nu, n0), s in d.groupby(["eval_target", "nu", "n0"]):
        piv = s.pivot_table(index="rep", columns="policy", values="regret")
        r, lo, hi = boot_ratio(piv["dr_prepost"].values, piv["dr_local"].values, rng)
        same = s[s.policy.isin(["dr_local", "dr_prepost"])].pivot_table(
            index="rep", columns="policy", values="choices", aggfunc="first"
        )
        h6.append(
            {
                "eval_target": et,
                "nu": nu,
                "n0": n0,
                "prepost_over_local": r,
                "lo90": lo,
                "hi90": hi,
                "same_sequence_frac": float((same["dr_local"] == same["dr_prepost"]).mean()),
            }
        )
    h6 = pd.DataFrame(h6)
    cost = (
        df.groupby(["nu", "n0"])[["t_fit", "t_local", "t_prepost", "t_total"]].mean().reset_index()
    )

    import matplotlib.pyplot as plt

    targets = list(dict.fromkeys(pooled.eval_target))
    fig, axes = plt.subplots(1, len(targets), figsize=(5 * len(targets), 3.6), sharey=True)
    for ax, et in zip(np.atleast_1d(axes), targets, strict=True):
        s = pooled[pooled.eval_target == et].set_index("policy").loc[POLICIES]
        y = np.arange(len(POLICIES))
        ax.errorbar(
            s.ratio_vs_uniform,
            y,
            xerr=[s.ratio_vs_uniform - s.lo90, s.hi90 - s.ratio_vs_uniform],
            fmt="o",
            color=ps.SERIES[0],
            ms=6,
            capsize=3,
            lw=1.5,
        )
        ax.axvline(1.0, color=ps.TEXT2, lw=1, ls="--")
        ax.set_yticks(y, POLICIES)
        ax.set_title(f"{et}: mean regret / uniform (90% CI)")
        ax.set_xlabel("ratio (lower is better)")
    ps.save(fig, cfg["paths"]["figures"] / "e5_regret_ratio.png")

    fl = ".4f"
    md = [
        "# E5 — Decision-targeted observation allocation",
        "",
        f"Conditions nu x n0 = {sorted(df.nu.unique())} x {sorted(df.n0.unique())}; "
        f"{df.rep.max() + 1} replications each; {cfg['e5']['batches']} batches of cost "
        f"{cfg['e5']['batch_cost']}. Regret = population (out-of-sample) expected score regret of "
        "the final Bayes act under the true DGP. DR policies are evaluated on their own target.",
        "",
        "## Pooled over conditions (each condition normalized by its uniform mean)",
        "",
        pooled.to_markdown(index=False, floatfmt=fl),
        "",
        "## By condition",
        "",
        summ.to_markdown(index=False, floatfmt=".4g"),
        "",
        "## H6: preposterior vs local decision-targeted allocation",
        "",
        h6.to_markdown(index=False, floatfmt=fl),
        "",
        "## Secondary metrics and source mix (batches per source)",
        "",
        sec.to_markdown(index=False, floatfmt=fl),
        "",
        "## Cost per replicate (seconds, all policies)",
        "",
        cost.to_markdown(index=False, floatfmt=".2f"),
        "",
        "Figure: `figures/e5_regret_ratio.png`.",
    ]
    out_md = cfg["paths"]["reports"] / "e5_allocation.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(pooled.to_string(index=False))
    print(h6.to_string(index=False))
    print(sec.to_string(index=False))
    print(f"RESULT_PATHS: {out_md}")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
