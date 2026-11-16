"""
S1 — Statistical significance of all reported results (simulation-study standards)

Follows Morris, White & Crowther (2019, Stat. Med.): Monte Carlo standard errors for every
performance measure, exact binomial tests for coverage, paired tests for regret comparisons
(paired t = Diebold-Mariano with iid replicates; Wilcoxon signed-rank; bootstrap CI), cell-
clustered tests for correlation-based hypotheses (cells are the independent units), McNemar
tests for paired coverage, the Model Confidence Set (Hansen, Lunde & Nason 2011) for
allocation policies, and Holm adjustment within each pre-declared family of hypotheses.

전제:
  results/e2_gaussian.csv, results/e3_raw.csv, results/e3b_prior_truth.csv,
  results/e4_mixture.csv, results/e5_allocation.csv, results/e6_npe.csv
출력:
  results/s1_tests.csv
  reports/s1_significance.md
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_id import stats as st  # noqa: E402
from decision_id import tmodel as tm  # noqa: E402
from decision_id.utils import load_config  # noqa: E402

SEED = 42
ALL_TESTS: list[dict] = []


def rho(a, b) -> float:
    """Spearman correlation (NaN-safe)."""
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 8 or np.ptp(a[ok]) == 0 or np.ptp(b[ok]) == 0:
        return np.nan
    return float(sps.spearmanr(a[ok], b[ok])[0])


def partial_rho(a, b, c) -> float:
    """Rank partial correlation of a, b given c."""
    ok = np.isfinite(a) & np.isfinite(b) & np.isfinite(c)
    if ok.sum() < 10:
        return np.nan
    ra, rb, rc = (sps.rankdata(v[ok]) for v in (a, b, c))
    X = np.column_stack([np.ones_like(rc), rc])
    ea = ra - X @ np.linalg.lstsq(X, ra, rcond=None)[0]
    eb = rb - X @ np.linalg.lstsq(X, rb, rcond=None)[0]
    return float((ea * eb).sum() / np.sqrt((ea**2).sum() * (eb**2).sum()))


def record(family: str, name: str, estimate: float, p: float, extra: str = "") -> None:
    """Collect a test for the global table (Holm applied per family at the end)."""
    ALL_TESTS.append(
        {"family": family, "test": name, "estimate": estimate, "p": p, "detail": extra}
    )


def mcnemar(x: np.ndarray, y: np.ndarray) -> float:
    """Exact McNemar p-value for paired binary outcomes."""
    b = int(np.sum((x == 1) & (y == 0)))
    c = int(np.sum((x == 0) & (y == 1)))
    if b + c == 0:
        return 1.0
    return float(sps.binomtest(b, b + c, 0.5).pvalue)


def main() -> None:
    t0 = time.time()
    print("=== S1 significance ===")
    cfg = load_config()
    R = cfg["paths"]["results"]
    need = [
        "e2_gaussian.csv",
        "e3_raw.csv",
        "e3b_prior_truth.csv",
        "e4_mixture.csv",
        "e5_allocation.csv",
        "e6_npe.csv",
    ]
    for f in need:
        if not (R / f).exists():
            print(f"[ERR] missing results/{f}")
            sys.exit(1)
    rng = np.random.default_rng(SEED)
    md = [
        "# S1 — Statistical significance",
        "",
        "Units of inference: replications (independent) for coverage and paired regret tests; "
        "**cells** (n x nu combinations, independent seeds) for correlation-based hypotheses, so "
        "that dependence between functionals of the same dataset does not inflate significance. "
        "Holm adjustment is applied within each family listed in the final table.",
        "",
    ]

    # ---------------------------------------------------------------- E3 ------------
    df = pd.read_csv(R / "e3_raw.csv")
    meth = df[df.functional == "__method__"].dropna(axis=1, how="all")
    func = df[(df.functional != "__method__") & (df.method != "__diag__")].dropna(axis=1, how="all")
    diag = df[df.method == "__diag__"].dropna(axis=1, how="all")

    # coverage: MCSE, Wilson CI, exact binomial vs 0.90
    cov_rows = []
    for (n, f, m), s in func[
        func.functional.isin(["var975", "var999", "es975", "variance"])
    ].groupby(["n", "functional", "method"]):
        k, N = int(s.cover.sum()), len(s)
        lo, hi = st.wilson(k, N)
        p = st.binom_two_sided(k, N, 0.90)
        cov_rows.append(
            {
                "n": n,
                "functional": f,
                "method": m,
                "coverage": k / N,
                "mcse": st.mcse_prop(k / N, N),
                "wilson95": f"[{lo:.3f}, {hi:.3f}]",
                "p_vs_0.90": p,
            }
        )
    cov = pd.DataFrame(cov_rows)
    cov["p_holm"] = (
        st.holm(cov.p_vs_0_90.values) if "p_vs_0_90" in cov else st.holm(cov["p_vs_0.90"].values)
    )
    for _, r in cov.iterrows():
        record(
            "E3 coverage = 0.90", f"{r.method} {r.functional} n={r.n}", r.coverage, r["p_vs_0.90"]
        )
    sig_under = cov[(cov.p_holm < 0.05) & (cov.coverage < 0.9)]
    cov_piv = (
        cov.assign(
            cell=lambda d: d.coverage.map("{:.3f}".format) + np.where(d.p_holm < 0.05, "*", "")
        )
        .pivot_table(index=["functional", "n"], columns="method", values="cell", aggfunc="first")
        .reset_index()
    )
    md += [
        "## E3 coverage (MCSE <= 0.014 at 500 replications; * = differs from 0.90 after Holm "
        "over all 112 cells)",
        "",
        cov_piv.to_markdown(index=False),
        "",
        f"Significant under-coverage (Holm < 0.05): {len(sig_under)} of {len(cov)} cells; "
        "by method: " + ", ".join(f"{m}={c}" for m, c in sig_under.method.value_counts().items()),
        "",
    ]

    # H2 with cells as units, and robustness across inference methods
    h2_rows = []
    for m in ["grid", "mle", "laplace_u"]:
        g = func[func.method == m].merge(
            meth[meth.method == m][["n", "nu", "rep", "err_xi", "err_logsd"]], on=["n", "nu", "rep"]
        )
        per_cell = {}
        for fn in ["var95", "var975", "var99", "var999", "es975", "es99"]:
            rr = []
            for _, c in g[g.functional == fn].groupby(["n", "nu"]):
                rr.append(
                    (
                        rho(np.abs(c.err_xi.values), c.regret.values),
                        rho(np.abs(c.err_logsd.values), c.regret.values),
                    )
                )
            rr = np.array(rr)
            per_cell[fn] = rr
            t = sps.ttest_1samp(rr[:, 0], 0.0)
            h2_rows.append(
                {
                    "method": m,
                    "functional": fn,
                    "mean_rho_xi": rr[:, 0].mean(),
                    "se": rr[:, 0].std(ddof=1) / np.sqrt(len(rr)),
                    "p_rho_xi>0": t.pvalue / 2 if t.statistic > 0 else 1 - t.pvalue / 2,
                    "mean_rho_logsd": rr[:, 1].mean(),
                    "cells": len(rr),
                }
            )
            if m == "grid":
                record(
                    "H2 rho(|xi err|, regret) > 0", fn, rr[:, 0].mean(), h2_rows[-1]["p_rho_xi>0"]
                )
        d = per_cell["var999"][:, 0] - per_cell["var95"][:, 0]
        w = sps.wilcoxon(d)
        h2_rows.append(
            {
                "method": m,
                "functional": "var999 - var95",
                "mean_rho_xi": d.mean(),
                "se": d.std(ddof=1) / np.sqrt(len(d)),
                "p_rho_xi>0": w.pvalue,
                "mean_rho_logsd": np.nan,
                "cells": len(d),
            }
        )
        if m == "grid":
            record(
                "H2 contrast", "rho_var999 - rho_var95 (Wilcoxon over cells)", d.mean(), w.pvalue
            )
            d2 = per_cell["var975"][:, 1] - per_cell["var975"][:, 0]
            record(
                "H2 contrast",
                "VaR97.5: rho_logsd - rho_xi (Wilcoxon over cells)",
                d2.mean(),
                sps.wilcoxon(d2).pvalue,
            )
    h2 = pd.DataFrame(h2_rows)
    md += [
        "## H2 — tail-index recovery vs regret (20 cells as units; robustness across methods)",
        "",
        h2.to_markdown(index=False, floatfmt=".4g"),
        "",
    ]

    # H4 partial correlations with cell clustering
    g = func[func.method == "grid"][["n", "nu", "rep", "functional", "sqerr_rel"]]
    dj = diag.merge(g, on=["n", "nu", "rep", "functional"])
    dj = dj[dj.functional != "variance"].copy()
    dj["exact_var_rel"] = dj.exact_var / dj.g0**2
    dj["rg0_rel"] = dj.rg0_mle / dj.g0**2
    dj["wh_vpost_rel"] = dj.wh_vpost / dj.g0**2
    for k in ("logsd_xi", "eta_xi", "sigma_nu"):
        dj[f"eigterm_{k}"] = dj[f"eig_score_{k}"] ** 2 / dj.g0**2
    cands = [
        "rg0_rel",
        "wh_vpost_rel",
        "eigterm_logsd_xi",
        "eigterm_eta_xi",
        "eigterm_sigma_nu",
        "eig_share_logsd_xi",
        "eig_share_eta_xi",
        "eig_share_sigma_nu",
        "post_xi_sd",
        "post_tr_cov",
    ]
    h4 = []
    for c in cands:
        vals, clus = [], []
        for (n, nu, _f), cell in dj.groupby(["n", "nu", "functional"]):
            vals.append(
                partial_rho(cell[c].values, cell.sqerr_rel.values, cell.exact_var_rel.values)
            )
            clus.append(f"{n}-{nu}")
        ct = st.cluster_t(np.array(vals), np.array(clus))
        h4.append(
            {
                "diagnostic": c,
                "mean_partial_rho": ct["mean"],
                "se": ct["se"],
                "p": ct["p"],
                "clusters": ct["n_clusters"],
            }
        )
        record("H4 partial rho given exact Var(g) = 0", c, ct["mean"], ct["p"])
    h4 = pd.DataFrame(h4)
    h4["p_holm"] = st.holm(h4.p.values)
    # functional-specific vs parameter-only (within-cell rho difference)
    diff_rows = []
    for c in ["post_xi_sd", "post_tr_cov", "eig_share_eta_xi"]:
        vals, clus = [], []
        for (n, nu, _f), cell in dj.groupby(["n", "nu", "functional"]):
            vals.append(
                rho(cell.exact_var_rel.values, cell.sqerr_rel.values)
                - rho(cell[c].values, cell.sqerr_rel.values)
            )
            clus.append(f"{n}-{nu}")
        ct = st.cluster_t(np.array(vals), np.array(clus))
        diff_rows.append(
            {
                "contrast": f"rho(exact Var g) - rho({c})",
                "mean": ct["mean"],
                "se": ct["se"],
                "p": ct["p"],
            }
        )
        record("H4 functional-specific beats parameter-only", c, ct["mean"], ct["p"])
    md += [
        "## H4 — added information beyond the exact functional posterior variance",
        "",
        h4.to_markdown(index=False, floatfmt=".4g"),
        "",
        pd.DataFrame(diff_rows).to_markdown(index=False, floatfmt=".4g"),
        "",
    ]

    # H4b: prior sensitivity
    hb = []
    for c in ["wh_contraction", "exact_var_rel", "exact_pi", "post_xi_sd"]:
        vals, clus = [], []
        for (n, nu, _f), cell in dj.groupby(["n", "nu", "functional"]):
            vals.append(
                rho(cell.wh_pi.values, cell.prior_sens.values)
                - rho(cell[c].values, cell.prior_sens.values)
            )
            clus.append(f"{n}-{nu}")
        ct = st.cluster_t(np.array(vals), np.array(clus))
        hb.append(
            {"contrast": f"rho(pi_g) - rho({c})", "mean": ct["mean"], "se": ct["se"], "p": ct["p"]}
        )
        record("H4b pi_g beats alternative", c, ct["mean"], ct["p"])
    hb = pd.DataFrame(hb)
    hb["p_holm"] = st.holm(hb.p.values)
    md += [
        "## H4b — prior-sensitivity prediction (difference of within-cell Spearman, cells as "
        "units)",
        "",
        hb.to_markdown(index=False, floatfmt=".4g"),
        "",
    ]

    # regret vs exact, and population exceedance probability (Kupiec-type, exact)
    rr_rows = []
    for (n, f), s in func[func.functional.isin(["var99", "var999", "es975"])].groupby(
        ["n", "functional"]
    ):
        piv = s.pivot_table(index=["nu", "rep"], columns="method", values="regret")
        for m in ["laplace_u", "laplace_nat", "vi_mf", "vi_fr", "mle"]:
            r = st.paired_tests(piv[m].values, piv["grid"].values, rng, B=1000)
            rr_rows.append(
                {
                    "n": n,
                    "functional": f,
                    "method": m,
                    "ratio": r["ratio"],
                    "p_t": r["p_t"],
                    "p_wilcoxon": r["p_wilcoxon"],
                }
            )
    rr = pd.DataFrame(rr_rows)
    rr["p_holm"] = st.holm(rr.p_t.values)
    ex = func[func.functional == "var99"].copy()
    xi0 = 1 / ex.nu
    sig0 = np.sqrt(1 - 2 * xi0)
    ex["exceed_prob"] = tm.stats.t.sf(ex.act / sig0, ex.nu)
    ext = ex.groupby(["n", "method"]).exceed_prob.agg(["mean", st.mcse_mean]).reset_index()
    ext["p_vs_0.01"] = [
        sps.ttest_1samp(ex[(ex.n == a) & (ex.method == b)].exceed_prob, 0.01).pvalue
        for a, b in zip(ext.n, ext.method, strict=True)
    ]
    md += [
        "## E3 regret vs exact posterior at fixed truths (pooled over nu; paired tests)",
        "",
        rr.to_markdown(index=False, floatfmt=".4g"),
        "",
        "## E3 VaR99 population exceedance probability P(L > VaR_hat | truth) (Kupiec-type, "
        "exact; nominal 0.01)",
        "",
        ext.to_markdown(index=False, floatfmt=".5f"),
        "",
    ]

    # ---------------------------------------------------------------- E3b -----------
    b = pd.read_csv(R / "e3b_prior_truth.csv")
    br = []
    for (n, f), s in b.groupby(["n", "functional"]):
        piv = s.pivot_table(index="rep", columns="method", values="regret")
        for m in [c for c in piv.columns if c != "grid"]:
            r = st.paired_tests(piv[m].values, piv["grid"].values, rng, B=1000)
            br.append(
                {
                    "n": n,
                    "functional": f,
                    "method": m,
                    "ratio": r["ratio"],
                    "p_t": r["p_t"],
                    "p_wilcoxon": r["p_wilcoxon"],
                }
            )
            record("E3b approx vs exact (prior truths)", f"{m} {f} n={n}", r["ratio"], r["p_t"])
    br = pd.DataFrame(br)
    br["p_holm"] = st.holm(br.p_t.values)
    md += [
        "## E3b — truths from the prior: approximation regret vs exact (paired)",
        "",
        br.to_markdown(index=False, floatfmt=".4g"),
        "",
        f"Any approximation significantly *better* than exact (Holm < 0.05)? "
        f"{bool(((br.p_holm < 0.05) & (br.ratio < 1)).any())}",
        "",
    ]

    # ---------------------------------------------------------------- E4 ------------
    e4 = pd.read_csv(R / "e4_mixture.csv")
    c4 = []
    f4 = e4[e4.functional != "decision_var99"]
    for (n, f), s in f4.groupby(["n", "functional"]):
        piv = s.pivot_table(index="rep", columns="method", values="cover")
        for m in ["laplace_delta", "laplace_push", "mle_wald"]:
            p = mcnemar(piv["grid"].values, piv[m].values)
            c4.append(
                {
                    "n": n,
                    "functional": f,
                    "method": m,
                    "cover_exact": piv["grid"].mean(),
                    "cover_method": piv[m].mean(),
                    "p_mcnemar": p,
                }
            )
            record(
                "E4 coverage local vs exact (McNemar)",
                f"{m} {f} n={n}",
                piv[m].mean() - piv["grid"].mean(),
                p,
            )
    c4 = pd.DataFrame(c4)
    c4["p_holm"] = st.holm(c4.p_mcnemar.values)
    d4 = []
    dd = e4[e4.functional == "decision_var99"].pivot_table(
        index=["n", "rep"], columns="method", values="regret"
    )
    for n in dd.index.get_level_values(0).unique():
        for m in ["laplace_push", "mle_wald"]:
            r = st.paired_tests(dd.loc[n][m].values, dd.loc[n]["grid"].values, rng, B=1000)
            d4.append(
                {
                    "n": n,
                    "method": m,
                    "ratio": r["ratio"],
                    "p_t": r["p_t"],
                    "p_wilcoxon": r["p_wilcoxon"],
                }
            )
    md += [
        "## E4 — paired coverage (McNemar) and decision regret",
        "",
        c4.to_markdown(index=False, floatfmt=".4g"),
        "",
        pd.DataFrame(d4).to_markdown(index=False, floatfmt=".4g"),
        "",
    ]

    # ---------------------------------------------------------------- E5 ------------
    e5 = pd.read_csv(R / "e5_allocation.csv")
    keep = (e5.policy_target == "-") | (e5.policy_target == e5.eval_target)
    e5 = e5[keep]
    t5, mcs_rows = [], []
    for et, s in e5.groupby("eval_target"):
        piv = s.pivot_table(index=["nu", "n0", "rep"], columns="policy", values="regret")
        norm = piv.div(piv["uniform"].groupby(level=["nu", "n0"]).transform("mean"), axis=0)
        for a, bb in [
            ("dr_local", "dopt"),
            ("dr_local", "predictive"),
            ("dr_local", "uniform"),
            ("dr_prepost", "dopt"),
            ("dr_prepost", "dr_local"),
        ]:
            r = st.paired_tests(norm[a].values, norm[bb].values, rng)
            fam = "E5 H6 prepost vs local" if bb == "dr_local" else "E5 H5 DR vs baselines"
            t5.append(
                {
                    "target": et,
                    "comparison": f"{a} vs {bb}",
                    "ratio": r["ratio"],
                    "ci95_diff": f"[{r['ci_lo']:.3f}, {r['ci_hi']:.3f}]",
                    "p_t": r["p_t"],
                    "p_wilcoxon": r["p_wilcoxon"],
                    "ties": r["frac_tie"],
                    "family": fam,
                }
            )
            record(fam, f"{et}: {a} vs {bb}", r["ratio"], r["p_t"])
        names = ["uniform", "own_only", "dopt", "predictive", "dr_local", "dr_prepost"]
        surv, pv = st.mcs(norm[names].values, names, alpha=0.10, B=3000, rng=rng)
        mcs_rows.append(
            {"target": et, "MCS_90": ", ".join(surv), **{f"p_{k}": pv[k] for k in names}}
        )
    t5 = pd.DataFrame(t5)
    t5["p_holm_family"] = np.nan
    for _fam, idx in t5.groupby("family").groups.items():
        t5.loc[idx, "p_holm_family"] = st.holm(t5.loc[idx, "p_t"].values)
    md += [
        "## E5 — allocation (pooled over 6 conditions, 360 paired replications per target)",
        "",
        t5.to_markdown(index=False, floatfmt=".4g"),
        "",
        "Model Confidence Set (Hansen, Lunde & Nason 2011), alpha = 0.10, T_max statistic, "
        "condition-normalized regrets; MCS p-values per policy:",
        "",
        pd.DataFrame(mcs_rows).to_markdown(index=False, floatfmt=".3f"),
        "",
    ]

    # ---------------------------------------------------------------- E6 / E2 -------
    e6 = pd.read_csv(R / "e6_npe.csv")
    r6 = []
    for (n, f), s in e6.groupby(["n", "functional"]):
        cv = s.pivot_table(index=["nu", "rep"], columns="method", values="cover")
        rg = s.pivot_table(index=["nu", "rep"], columns="method", values="regret")
        r = st.paired_tests(rg["npe"].values, rg["grid"].values, rng, B=1000)
        r6.append(
            {
                "n": n,
                "functional": f,
                "cover_exact": cv["grid"].mean(),
                "cover_npe": cv["npe"].mean(),
                "p_mcnemar": mcnemar(cv["grid"].values, cv["npe"].values),
                "regret_ratio": r["ratio"],
                "p_regret": r["p_t"],
            }
        )
    r6 = pd.DataFrame(r6)
    r6["p_holm_cov"] = st.holm(r6.p_mcnemar.values)
    r6["p_holm_regret"] = st.holm(r6.p_regret.values)
    e2 = pd.read_csv(R / "e2_gaussian.csv")
    e2 = e2[e2.functional != "decision"]
    r2 = []
    for (m, f), s in e2.groupby(["method", "functional"]):
        k, N = int(s.cover.sum()), len(s)
        r2.append(
            {
                "method": m,
                "functional": f,
                "coverage": k / N,
                "n": N,
                "p_vs_0.90": st.binom_two_sided(k, N, 0.9),
            }
        )
    r2 = pd.DataFrame(r2)
    r2["p_holm"] = st.holm(r2["p_vs_0.90"].values)
    md += [
        "## E6 — NPE vs exact (McNemar for coverage, paired test for regret)",
        "",
        r6.to_markdown(index=False, floatfmt=".4g"),
        "",
        "## E2 — Gaussian coverage vs 0.90 (pooled over n)",
        "",
        r2.to_markdown(index=False, floatfmt=".4g"),
        "",
    ]

    # ---------------------------------------------------------------- summary -------
    T = pd.DataFrame(ALL_TESTS)
    T["p_holm"] = np.nan
    T["p_bh"] = np.nan
    for _fam, idx in T.groupby("family").groups.items():
        T.loc[idx, "p_holm"] = st.holm(T.loc[idx, "p"].values)
        T.loc[idx, "p_bh"] = st.bh(T.loc[idx, "p"].values)
    T.to_csv(R / "s1_tests.csv", index=False)
    summ = (
        T.groupby("family")
        .apply(
            lambda d: pd.Series(
                {
                    "tests": len(d),
                    "significant_holm_0.05": int((d.p_holm < 0.05).sum()),
                    "significant_bh_0.05": int((d.p_bh < 0.05).sum()),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    md += ["## Summary of test families", "", summ.to_markdown(index=False), ""]
    out = cfg["paths"]["reports"] / "s1_significance.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(summ.to_string(index=False))
    print(h2[h2.method == "grid"].to_string(index=False))
    print(h4.to_string(index=False))
    print(hb.to_string(index=False))
    print(t5.to_string(index=False))
    print(pd.DataFrame(mcs_rows).to_string(index=False))
    print(f"RESULT_PATHS: {R / 's1_tests.csv'}, {out}")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
