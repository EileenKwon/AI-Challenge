"""
E3 analysis — tables, hypothesis tests and figures from the replicated Student-t study

전제:
  results/e3_raw.csv  (from e3_student_t_study.py)
출력:
  results/e3_coverage.csv, results/e3_diag_corr.csv, results/e3_regret_ratio.csv
  figures/e3_coverage.png, figures/e3_param_vs_decision.png
  reports/e3_student_t_study.md
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_id import plotstyle as ps  # noqa: E402
from decision_id.utils import load_config  # noqa: E402

KEYF = ["var95", "var975", "var99", "var999", "es975", "es99", "variance"]
METHODS = ["grid", "mcmc", "laplace_u", "laplace_nat", "vi_fr", "vi_mf", "mle"]


def spearman(a, b) -> float:
    """Spearman correlation ignoring NaNs."""
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 8 or np.ptp(a[ok]) == 0 or np.ptp(b[ok]) == 0:
        return np.nan
    return float(stats.spearmanr(a[ok], b[ok])[0])


def partial_spearman(a, b, c) -> float:
    """Spearman partial correlation of a and b given c (rank residuals)."""
    ok = np.isfinite(a) & np.isfinite(b) & np.isfinite(c)
    if ok.sum() < 10:
        return np.nan
    ra, rb, rc = (stats.rankdata(v[ok]) for v in (a, b, c))

    def resid(y):
        X = np.column_stack([np.ones_like(rc), rc])
        return y - X @ np.linalg.lstsq(X, y, rcond=None)[0]

    ea, eb = resid(ra), resid(rb)
    den = np.sqrt((ea**2).sum() * (eb**2).sum())
    return float((ea * eb).sum() / den) if den > 0 else np.nan


def main() -> None:
    t0 = time.time()
    print("=== E3 analysis ===")
    cfg = load_config()
    raw = cfg["paths"]["results"] / "e3_raw.csv"
    if not raw.exists():
        print(f"[ERR] missing {raw}; run e3_student_t_study.py first")
        sys.exit(1)
    ps.apply()
    df = pd.read_csv(raw)
    meth = df[df.functional == "__method__"].dropna(axis=1, how="all")
    func = df[~df.functional.isin(["__method__"]) & (df.method != "__diag__")].drop(
        columns=["err_xi", "err_logsd", "kl", "seconds", "bt_regret_var99", "frac_outside",
                 "boundary"]
    )
    diag = df[df.method == "__diag__"].dropna(axis=1, how="all").copy()
    R = cfg["paths"]["results"]

    # 1. coverage --------------------------------------------------------------------
    cov = (
        func.groupby(["n", "nu", "functional", "method"])["cover"]
        .mean()
        .unstack("method")
        .reset_index()
    )
    cov.to_csv(R / "e3_coverage.csv", index=False)
    cov_n = (
        func[func.functional.isin(["var975", "var999", "es975", "variance"])]
        .groupby(["functional", "n", "method"])["cover"]
        .mean()
        .unstack("method")[[m for m in METHODS if m in func.method.unique()]]
        .reset_index()
    )
    cov_nu = (
        func[func.functional.isin(["var999", "variance"]) & (func.n <= 250)]
        .groupby(["functional", "nu", "method"])["cover"]
        .mean()
        .unstack("method")[[m for m in METHODS if m in func.method.unique()]]
        .reset_index()
    )

    # 2. parameter recovery vs decision quality (H2) -----------------------------------
    g = func[func.method == "grid"].merge(
        meth[meth.method == "grid"][["n", "nu", "rep", "err_xi", "err_logsd"]],
        on=["n", "nu", "rep"],
    )
    h2 = []
    for f in [x for x in KEYF if x != "variance"]:
        sub = g[g.functional == f]
        rx, rl = [], []
        for _, c in sub.groupby(["n", "nu"]):
            rx.append(spearman(np.abs(c.err_xi.values), c.regret.values))
            rl.append(spearman(np.abs(c.err_logsd.values), c.regret.values))
        h2.append(
            {
                "functional": f,
                "rho(|err_xi|, regret)": np.nanmean(rx),
                "rho(|err_logsd|, regret)": np.nanmean(rl),
            }
        )
    h2 = pd.DataFrame(h2)

    # 3. diagnostics vs realized loss (H4) ---------------------------------------------
    gl = g[["n", "nu", "rep", "functional", "sqerr_rel", "regret"]]
    dj = diag.merge(gl, on=["n", "nu", "rep", "functional"])
    dj["exact_var_rel"] = dj.exact_var / dj.g0**2
    for c in ["rg0_mle", "wh_vpost"] + [f"ridge10_{k}" for k in ("logsd_xi", "eta_xi", "sigma_nu")]:
        dj[c + "_rel"] = dj[c] / dj.g0**2
    for k in ("logsd_xi", "eta_xi", "sigma_nu"):
        dj[f"eig_score2_{k}_rel"] = dj[f"eig_score_{k}"] ** 2 / dj.g0**2
    dj["neg_fisher_lam_min"] = -dj.fisher_lam_min
    cands = [
        "exact_var_rel",
        "rg0_mle_rel",
        "wh_vpost_rel",
        "ridge10_logsd_xi_rel",
        "ridge10_eta_xi_rel",
        "ridge10_sigma_nu_rel",
        "eig_score2_logsd_xi_rel",
        "eig_score2_eta_xi_rel",
        "eig_score2_sigma_nu_rel",
        "eig_share_logsd_xi",
        "eig_share_eta_xi",
        "eig_share_sigma_nu",
        "post_xi_sd",
        "post_tr_cov",
        "neg_fisher_lam_min",
    ]
    corr_rows = []
    for c in cands:
        within, part = [], []
        for _, cell in dj[dj.functional != "variance"].groupby(["n", "nu", "functional"]):
            within.append(spearman(cell[c].values, cell.sqerr_rel.values))
            part.append(
                partial_spearman(cell[c].values, cell.sqerr_rel.values, cell.exact_var_rel.values)
            )
        pooled = spearman(dj[c].values, dj.sqerr_rel.values)
        corr_rows.append(
            {
                "diagnostic": c,
                "within_cell_rho": np.nanmean(within),
                "within_partial_rho_given_exact_var": np.nanmean(part),
                "pooled_rho_all_cells_functionals": pooled,
            }
        )
    corr = pd.DataFrame(corr_rows)
    corr.to_csv(R / "e3_diag_corr.csv", index=False)

    # 4. reparameterization (H3) -------------------------------------------------------
    inv_rows = []
    for f in KEYF:
        s = dj[dj.functional == f]
        es = s[[f"eig_share_{k}" for k in ("logsd_xi", "eta_xi", "sigma_nu")]].values
        rd = s[[f"ridge10_{k}" for k in ("logsd_xi", "eta_xi", "sigma_nu")]].values
        pi = s[[f"wh_pi_{k}" for k in ("logsd_xi", "eta_xi", "sigma_nu")]].values
        inv_rows.append(
            {
                "functional": f,
                "eig_weak_share range (median)": float(np.median(es.max(1) - es.min(1))),
                "eig_weak_share logsd/eta/sigma_nu (median)": "/".join(
                    f"{v:.2f}" for v in np.median(es, 0)
                ),
                "ridge10 max/min (median)": float(np.median(rd.max(1) / rd.min(1))),
                "whitened pi max/min (median)": float(np.median(pi.max(1) / pi.min(1))),
            }
        )
    inv = pd.DataFrame(inv_rows)

    # 5. prior sensitivity (H4b) -------------------------------------------------------
    ps_rows = []
    for c in ["wh_pi", "exact_pi", "exact_var_rel", "wh_contraction", "post_xi_sd"]:
        within = [
            spearman(cell[c].values, cell.prior_sens.values)
            for _, cell in dj[dj.functional != "variance"].groupby(["n", "nu", "functional"])
        ]
        ps_rows.append(
            {
                "predictor": c,
                "within_cell_rho": np.nanmean(within),
                "pooled_rho": spearman(dj[c].values, dj.prior_sens.values),
            }
        )
    psens = pd.DataFrame(ps_rows)
    loc_vs_exact_pi = spearman(dj.wh_pi.values, dj.exact_pi.values)

    # 6. regrets relative to the exact posterior --------------------------------------
    rr = (
        func[func.functional != "variance"]
        .pivot_table(index=["n", "nu", "rep", "functional"], columns="method", values="regret")
        .reset_index()
    )
    rat_rows = []
    for (n, f), s in rr.groupby(["n", "functional"]):
        row = {"n": n, "functional": f}
        for m in METHODS:
            if m in s and m != "grid":
                ok = s[m].notna() & s["grid"].notna()
                row[m] = s.loc[ok, m].mean() / max(s.loc[ok, "grid"].mean(), 1e-300)
        rat_rows.append(row)
    rat = pd.DataFrame(rat_rows)
    rat.to_csv(R / "e3_regret_ratio.csv", index=False)
    sh = func[func.functional.isin(["var99", "es975"])].pivot_table(
        index=["n", "functional"], columns="method", values="regret_shift", aggfunc="mean"
    )
    sh = sh.div(sh["grid"], axis=0).reset_index()

    # 7. other method-level metrics ----------------------------------------------------
    mm = meth.groupby(["n", "method"])[["kl", "seconds"]].mean().unstack("method")
    mm.columns = [f"{a}_{b}" for a, b in mm.columns]
    mm = mm.reset_index()
    bt = meth[meth.method == "grid"].merge(
        func[(func.method == "grid") & (func.functional == "var99")][["n", "nu", "rep", "regret"]],
        on=["n", "nu", "rep"],
    )
    bt_rho = spearman(bt.bt_regret_var99.values, bt.regret.values)
    bt_means = bt.groupby("n")[["bt_regret_var99", "regret"]].mean().reset_index()
    loc = dj.groupby(["functional", "n"])["delta_vs_exact_sd"].median().unstack("n").reset_index()
    lapnat = meth[meth.method == "laplace_nat"].groupby(["n", "nu"])["frac_outside"].mean()
    mle_bd = meth[meth.method == "mle"].groupby(["n", "nu"])["boundary"].mean()

    # figures ----------------------------------------------------------------------------
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15, 3.8), sharey=True)
    for ax, f in zip(axes, ["var975", "var999", "variance"], strict=True):
        s = func[(func.functional == f)].groupby(["n", "method"])["cover"].mean().unstack()
        for c, m in zip(ps.SERIES, [m for m in METHODS if m in s], strict=False):
            ax.plot(s.index, s[m], marker="o", ms=5, color=c, label=m)
        ax.axhline(0.9, color=ps.TEXT2, lw=1, ls="--")
        ax.set_xscale("log")
        ax.set_title(f"{f}: coverage of 90% intervals (avg over nu)")
        ax.set_xlabel("n")
    axes[0].legend(fontsize=7, ncol=2)
    ps.save(fig, cfg["paths"]["figures"] / "e3_coverage.png")
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharex=True)
    cell = g[(g.n == 250) & (g.nu == 4.0)]
    for ax, f in zip(axes, ["var975", "var999"], strict=True):
        s = cell[cell.functional == f]
        ax.scatter(np.abs(s.err_xi), s.regret, s=12, color=ps.SERIES[0], alpha=0.7)
        ax.set_yscale("log")
        rho = spearman(np.abs(s.err_xi.values), s.regret.values)
        ax.set_title(f"{f}: regret vs |xi error|  (rho={rho:.2f})")
        ax.set_xlabel("|posterior mean xi - true xi|")
    axes[0].set_ylabel("quantile-score regret")
    ps.save(fig, cfg["paths"]["figures"] / "e3_param_vs_decision.png")

    fl = ".4f"
    md = [
        "# E3 — Replicated Student-t study",
        "",
        f"{df[['n', 'nu']].drop_duplicates().shape[0]} cells (n x nu), "
        f"{df.rep.max() + 1} replications per cell; MCMC on the first replications of each cell.",
        "",
        "## 1. Coverage of 90% intervals (averaged over nu)",
        "",
        cov_n.to_markdown(index=False, floatfmt=fl),
        "",
        "### Short samples (n <= 250) by tail index",
        "",
        cov_nu.to_markdown(index=False, floatfmt=fl),
        "",
        "## 2. Parameter recovery vs decision regret (within-cell Spearman, averaged)",
        "",
        h2.to_markdown(index=False, floatfmt=fl),
        "",
        "## 3. Diagnostics vs realized squared relative error of the exact Bayes act",
        "",
        "within_cell_rho: data-dependent variation only; partial: given exact posterior "
        "variance of g; pooled: across cells and functionals.",
        "",
        corr.to_markdown(index=False, floatfmt=fl),
        "",
        "## 4. Reparameterization sensitivity of diagnostics",
        "",
        inv.to_markdown(index=False, floatfmt=fl),
        "",
        "## 5. Prior sensitivity of the Bayes act vs diagnostics",
        "",
        "prior_sens = |act(alt prior) - act(default prior)| / posterior sd of g.",
        "",
        psens.to_markdown(index=False, floatfmt=fl),
        "",
        f"Spearman(local pi_g, exact pi_g) pooled = {loc_vs_exact_pi:.4f}",
        "",
        "## 6. Mean Bayes-act regret relative to the exact posterior (ratio)",
        "",
        rat.to_markdown(index=False, floatfmt=fl),
        "",
        "### Under distribution shift (ratio to exact posterior)",
        "",
        sh.to_markdown(index=False, floatfmt=fl),
        "",
        "## 7. Local delta-method SD / exact posterior SD (median)",
        "",
        loc.to_markdown(index=False, floatfmt=fl),
        "",
        "## 8. Log-score regret (KL) and seconds per method",
        "",
        mm.to_markdown(index=False, floatfmt=".5f"),
        "",
        f"Finite out-of-sample backtest vs population regret (VaR99, exact posterior): "
        f"Spearman = {bt_rho:.4f}",
        "",
        bt_means.to_markdown(index=False, floatfmt=".6f"),
        "",
        "## 9. Boundary diagnostics",
        "",
        "Laplace (log sd, xi): fraction of Gaussian draws outside xi in (0, xi_max); "
        "MLE: fraction of fits on the xi boundary.",
        "",
        pd.concat([lapnat, mle_bd], axis=1).reset_index().to_markdown(index=False, floatfmt=fl),
    ]
    out_md = cfg["paths"]["reports"] / "e3_student_t_study.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    for t in (cov_n, h2, corr, inv, psens, rat, loc):
        print(t.to_string(index=False))
    print("loc_vs_exact_pi", loc_vs_exact_pi, "bt_rho", bt_rho)
    print(f"RESULT_PATHS: {out_md}")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
