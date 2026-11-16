"""
E7 analysis — regret / compute comparison, significance tests, trigger diagnostics

Primary comparisons (declared before the evaluation results were inspected), per model with
cell-normalized regrets (each cell divided by its Bayesian c-optimal mean):
  P1  adapt_cal vs copt            (does the adaptive design beat local Bayesian c-optimal?)
  P2  adapt_cal vs evsi_global     (non-inferiority, margin 10%: upper 95% CI of ratio < 1.10)
  P3  cpu(adapt_cal) / cpu(evsi_global)
  P4  evsi_global vs copt          (does global design help at all?)
Holm adjustment over P1 and P4 across models.

전제:
  results/e7_eval.csv, results/e7_eval_logs.csv, results/e7_thresholds.json
출력:
  results/e7_summary.csv
  figures/e7_cost_regret.png
  reports/e7_adaptive.md
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_id import plotstyle as ps  # noqa: E402
from decision_id import stats as st  # noqa: E402
from decision_id.utils import load_config  # noqa: E402

SEED = 42
POLICIES = ["uniform", "dopt", "copt", "copt_global", "evsi_global", "adapt", "adapt_cal"]


def auc(score: np.ndarray, label: np.ndarray) -> float:
    """ROC AUC via the Mann-Whitney statistic."""
    pos, neg = score[label], score[~label]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    r = sps.rankdata(np.concatenate([pos, neg]))
    return float((r[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def ratio_ci(a: np.ndarray, b: np.ndarray, rng, B: int = 4000) -> tuple[float, float, float]:
    """Ratio of means with paired-bootstrap 95% interval."""
    idx = rng.integers(0, len(a), (B, len(a)))
    r = a[idx].mean(1) / b[idx].mean(1)
    return float(a.mean() / b.mean()), float(np.quantile(r, 0.025)), float(np.quantile(r, 0.975))


def main() -> None:
    t0 = time.time()
    print("=== E7 analysis ===")
    cfg = load_config()
    R = cfg["paths"]["results"]
    for f in ("e7_eval.csv", "e7_eval_logs.csv", "e7_thresholds.json"):
        if not (R / f).exists():
            print(f"[ERR] missing results/{f}")
            sys.exit(1)
    rng = np.random.default_rng(SEED)
    df = pd.read_csv(R / "e7_eval.csv")
    logs = pd.read_csv(R / "e7_eval_logs.csv")
    th = json.loads((R / "e7_thresholds.json").read_text())
    df["cell"] = df.model + "/" + df.truth + "/" + df.target

    # per-cell table
    cell_rows = []
    for cell, s in df.groupby("cell"):
        piv = s.pivot_table(index="task", columns="policy", values="regret")
        cpu = s.groupby("policy").cpu_seconds.mean()
        row = {"cell": cell, "reps": len(piv)}
        for p in POLICIES:
            row[f"{p}/copt"] = piv[p].mean() / piv["copt"].mean()
        row["cpu_copt_s"] = cpu["copt"]
        row["cpu_evsi_s"] = cpu["evsi_global"]
        row["cpu_adapt_cal_s"] = cpu["adapt_cal"]
        row["global_frac_adapt_cal"] = (
            s[s.policy == "adapt_cal"].global_stages.mean() / cfg["e7"]["stages"]
        )
        cell_rows.append(row)
    cells = pd.DataFrame(cell_rows)

    # pooled per model, normalized by the cell's copt mean
    df["norm"] = df.regret / df.cell.map(df[df.policy == "copt"].groupby("cell").regret.mean())
    prim = []
    for model, s in df.groupby("model"):
        piv = s.pivot_table(index=["cell", "task"], columns="policy", values="norm")
        cpu = s.pivot_table(index=["cell", "task"], columns="policy", values="cpu_seconds")
        for a, b, tag in [
            ("adapt_cal", "copt", "P1"),
            ("adapt_cal", "evsi_global", "P2"),
            ("evsi_global", "copt", "P4"),
            ("adapt", "copt", "S"),
            ("copt_global", "copt", "S"),
            ("dopt", "copt", "S"),
            ("uniform", "copt", "S"),
            ("adapt_cal", "adapt", "S"),
        ]:
            r, lo, hi = ratio_ci(piv[a].values, piv[b].values, rng)
            pt = st.paired_tests(piv[a].values, piv[b].values, rng, B=1000)
            prim.append(
                {
                    "model": model,
                    "tag": tag,
                    "comparison": f"{a} / {b}",
                    "ratio": r,
                    "ci95": f"[{lo:.3f}, {hi:.3f}]",
                    "ci_hi": hi,
                    "p_t": pt["p_t"],
                    "p_wilcoxon": pt["p_wilcoxon"],
                    "ties": pt["frac_tie"],
                    "cpu_ratio": cpu[a].mean() / cpu[b].mean(),
                }
            )
    prim = pd.DataFrame(prim)
    fam = prim.tag.isin(["P1", "P4"])
    prim["p_holm_P1P4"] = np.nan
    prim.loc[fam, "p_holm_P1P4"] = st.holm(prim.loc[fam, "p_t"].values)
    prim["noninferior_10pct"] = np.where(prim.tag == "P2", prim.ci_hi < 1.10, np.nan)
    prim.to_csv(R / "e7_summary.csv", index=False)

    # MCS per model
    mcs_rows = []
    for model, s in df.groupby("model"):
        piv = s.pivot_table(index=["cell", "task"], columns="policy", values="norm")[POLICIES]
        surv, pv = st.mcs(piv.values, POLICIES, alpha=0.10, B=3000, rng=rng)
        mcs_rows.append(
            {"model": model, "MCS_90": ", ".join(surv), **{f"p_{k}": pv[k] for k in POLICIES}}
        )
    mcs = pd.DataFrame(mcs_rows)

    # trigger diagnostics on evaluation logs of the always-global run (out-of-sample)
    g = logs[logs.policy == "evsi_global"].copy()
    g["disagree"] = g.choice_local != g.choice_evsi
    trig = []
    for model, s in list(g.groupby("model")) + [("all", g)]:
        lab = s.disagree.values
        fk = s.kappa.values > th["tau_kappa"]
        fm = s.margin.values < th["tau_margin"]
        fire_cal = fk | fm
        fire_fix = (s.kappa.values > cfg["e7"]["tau_fixed"][0]) | (
            s.margin.values < cfg["e7"]["tau_fixed"][1]
        )
        trig.append(
            {
                "model": model,
                "stages": len(s),
                "disagree_rate": lab.mean(),
                "AUC_kappa": auc(s.kappa.values, lab),
                "AUC_neg_margin": auc(-s.margin.values, lab),
                "AUC_margin_over_kappa": auc(-s.margin.values / (1 + s.kappa.values), lab),
                "fire_rate_fixed": fire_fix.mean(),
                "recall_fixed": fire_fix[lab].mean() if lab.any() else np.nan,
                "fire_rate_cal": fire_cal.mean(),
                "recall_cal": fire_cal[lab].mean() if lab.any() else np.nan,
                "recall_margin_only_cal": fm[lab].mean() if lab.any() else np.nan,
                "recall_kappa_only_cal": fk[lab].mean() if lab.any() else np.nan,
            }
        )
    trig = pd.DataFrame(trig)
    agree_cvar = (g.choice_cvar == g.choice_evsi).mean()

    # figure: cost vs regret per model
    import matplotlib.pyplot as plt

    ps.apply()
    models = list(dict.fromkeys(df.model))
    fig, axes = plt.subplots(1, len(models), figsize=(4.2 * len(models), 3.8))
    for ax, model in zip(np.atleast_1d(axes), models, strict=True):
        s = df[df.model == model]
        agg = s.groupby("policy").agg(cpu=("cpu_seconds", "mean"), reg=("norm", "mean"))
        for c, p in zip(ps.SERIES, POLICIES, strict=False):
            ax.scatter(
                agg.loc[p, "cpu"],
                agg.loc[p, "reg"],
                color=c,
                s=60,
                label=p,
                zorder=3,
                edgecolor=ps.SURFACE,
                linewidth=1.5,
            )
        ax.set_xscale("log")
        ax.axhline(1.0, color=ps.TEXT2, lw=1, ls="--")
        ax.set_title(f"{model}: regret / c-opt vs CPU")
        ax.set_xlabel("CPU seconds per run (log)")
    np.atleast_1d(axes)[0].set_ylabel("mean regret relative to Bayesian c-opt")
    np.atleast_1d(axes)[0].legend(fontsize=7)
    ps.save(fig, cfg["paths"]["figures"] / "e7_cost_regret.png")

    md = [
        "# E7 — Failure-triggered adaptive design vs Bayesian c-optimal and global designs",
        "",
        f"{cfg['e7']['stages']} stages, equal data budget, {cfg['e7']['n_sims']} preposterior "
        f"simulations; {df.task.nunique()} evaluation replications in total. Calibrated "
        f"thresholds (from separate calibration seeds): tau_kappa = {th['tau_kappa']}, "
        f"tau_margin = {th['tau_margin']} (calibration recall {th['cal_recall']:.2f}, firing "
        f"rate {th['cal_fire_rate']:.2f}, {th['n_disagree']}/{th['n_stages']} disagreement "
        "stages).",
        "",
        "## Primary and secondary comparisons (regret normalized by the cell's c-opt mean)",
        "",
        prim.drop(columns=["ci_hi"]).to_markdown(index=False, floatfmt=".4g"),
        "",
        "## Model Confidence Set (alpha = 0.10)",
        "",
        mcs.to_markdown(index=False, floatfmt=".3f"),
        "",
        "## Per cell: mean regret relative to c-opt and CPU seconds per run",
        "",
        cells.to_markdown(index=False, floatfmt=".3f"),
        "",
        "## Trigger diagnostics (evaluation logs of the always-global run; out-of-sample)",
        "",
        "disagree = the local c-opt choice differs from the global EVSI choice.",
        "",
        trig.to_markdown(index=False, floatfmt=".3f"),
        "",
        f"Global c-opt (variance) and global EVSI choose the same source in {agree_cvar:.1%} of "
        "stages.",
        "",
        "Figure: `figures/e7_cost_regret.png`.",
    ]
    out = cfg["paths"]["reports"] / "e7_adaptive.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(prim.drop(columns=["ci_hi"]).to_string(index=False))
    print(mcs.to_string(index=False))
    print(cells.to_string(index=False))
    print(trig.to_string(index=False))
    print(f"RESULT_PATHS: {R / 'e7_summary.csv'}, {out}")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
