"""
R1 — Robustness re-runs (seed, design, prior) and literature-style comparative backtests

Subcommands (run in order; `analyze` only reads the CSVs):
  e5_variants   E5 with local policies only under 5 variants: new seed, expensive variance proxy
                (rv cost 1.0), expensive peer data (peer cost 0.5), precise proxy (m = 20),
                finer batches (16 x 25)
  h6_confirm    confirmatory preposterior-vs-local test in the suggestive cell (nu=3, n0=100,
                VaR97.5) with 32 preposterior simulations and 150 replications
  e3_prior_swap E3 subset with default and alternative priors swapped
  backtest_dm   finite-sample comparative backtests: Kupiec POF and Diebold-Mariano (HAC)
                tests of exact-posterior vs MLE vs Laplace VaR/ES forecasts
  analyze       tests + report

전제:
  config.yaml; experiments/e3_student_t_study.py; experiments/e5_allocation.py
출력:
  results/r1_e5_variants.csv, results/r1_h6_confirm.csv, results/r1_e3_prior_swap.csv,
  results/r1_backtest_dm.csv
  reports/r1_robustness.md
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import copy  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from multiprocessing import Pool  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import e3_student_t_study as e3  # noqa: E402
import e5_allocation as e5  # noqa: E402

from decision_id import posterior as po  # noqa: E402
from decision_id import stats as st  # noqa: E402
from decision_id import tmodel as tm  # noqa: E402
from decision_id.utils import load_config  # noqa: E402

SEED = 7001
CFG = load_config()
RES = CFG["paths"]["results"]
WORKERS = int(os.environ.get("DID_WORKERS", os.cpu_count() or 1))


# ----------------------------------------------------------------------------------------
# E5 variants
# ----------------------------------------------------------------------------------------
def _configure_e5(variant: str) -> dict:
    """Mutate e5 module globals for a variant (inherited by forked workers)."""
    cfg5 = copy.deepcopy(CFG["e5"])
    if variant == "rv_cost1":
        cfg5["sources"]["rv"]["cost"] = 1.0
    elif variant == "peer_cost05":
        cfg5["sources"]["peer"]["cost"] = 0.5
    elif variant == "rv_m20":
        cfg5["sources"]["rv"]["m"] = 20
    elif variant == "batches16":
        cfg5["batches"], cfg5["batch_cost"] = 16, 25.0
    e5.E5 = cfg5
    e5.M = cfg5["sources"]["rv"]["m"]
    e5.UNITS = {
        s: int(round(cfg5["batch_cost"] / cfg5["sources"][s]["cost"])) for s in e5.al.SOURCES
    }
    e5.BASE_POLICIES = ["uniform", "own_only", "dopt", "predictive"]
    e5.DR_POLICIES = ["dr_local"]
    return cfg5


def _run_e5(variant: str, seed: int, conds, reps: int) -> pd.DataFrame:
    _configure_e5(variant)
    ss = np.random.SeedSequence(seed)
    seeds = ss.spawn(len(conds) * reps)
    tasks = [
        (nu, n0, r, seeds[i * reps + r]) for i, (nu, n0) in enumerate(conds) for r in range(reps)
    ]
    rows = []
    with Pool(WORKERS) as pool:
        for res in pool.imap_unordered(e5.run_one, tasks, chunksize=2):
            rows.extend(res)
    df = pd.DataFrame(rows)
    df["variant"] = variant
    return df


def cmd_e5_variants() -> None:
    t0 = time.time()
    conds = [(nu, n0) for nu in CFG["e5"]["nu_grid"] for n0 in CFG["e5"]["n0_grid"]]
    out = []
    for k, v in enumerate(["seed2", "rv_cost1", "peer_cost05", "rv_m20", "batches16"]):
        print(f"  [STAGE] variant {v}")
        out.append(_run_e5(v, SEED + k, conds, CFG["e5"]["reps"]))
        print(f"    done ({time.time() - t0:.0f}s)")
    pd.concat(out).to_csv(RES / "r1_e5_variants.csv", index=False)


def cmd_h6_confirm() -> None:
    _configure_e5("base")
    e5.E5["preposterior_sims"] = 32
    e5.E5["targets"] = ["var975"]
    e5.BASE_POLICIES = ["dopt"]
    e5.DR_POLICIES = ["dr_local", "dr_prepost"]
    ss = np.random.SeedSequence(SEED + 100)
    reps = 150
    seeds = ss.spawn(reps)
    tasks = [(3.0, 100, r, seeds[r]) for r in range(reps)]
    rows = []
    with Pool(WORKERS) as pool:
        for res in pool.imap_unordered(e5.run_one, tasks, chunksize=1):
            rows.extend(res)
    pd.DataFrame(rows).to_csv(RES / "r1_h6_confirm.csv", index=False)


# ----------------------------------------------------------------------------------------
# E3 with swapped priors
# ----------------------------------------------------------------------------------------
def cmd_e3_prior_swap() -> None:
    orig = po.prior_from_cfg

    def swapped(cfg, alt=False):
        return orig(cfg, alt=not alt)

    po.prior_from_cfg = swapped  # inherited by forked workers
    cells = [(n, nu) for n in (100, 1000) for nu in (3.0, 6.0, 50.0)]
    reps = 60
    ss = np.random.SeedSequence(SEED + 200)
    seeds = ss.spawn(len(cells) * reps)
    tasks = [
        (n, nu, 1000 + r, seeds[i * reps + r])
        for i, (n, nu) in enumerate(cells)
        for r in range(reps)
    ]
    rows = []
    with Pool(WORKERS) as pool:
        for res in pool.imap_unordered(e3.run_one, tasks, chunksize=2):
            rows.extend(res)
    pd.DataFrame(rows).to_csv(RES / "r1_e3_prior_swap.csv", index=False)
    po.prior_from_cfg = orig


# ----------------------------------------------------------------------------------------
# finite-sample comparative backtests
# ----------------------------------------------------------------------------------------
def _bt_one(task):
    n, nu, rep, seed = task
    rng = np.random.default_rng(seed)
    xm = CFG["student_t"]["xi_max"]
    xi0 = 1 / nu
    s0 = np.sqrt(1 - 2 * xi0)
    x = tm.sample(rng, n, s0, xi0)
    T = 2500
    L = -tm.sample(rng, T, s0, xi0)  # out-of-sample losses
    r = -L
    prior = po.prior_from_cfg(CFG)
    post, _ = po.grid_posterior(x, prior, CFG["student_t"])
    meth = {"exact": tm.compress(post.canon, post.w, max_pts=3000), "mle": None, "laplace_u": None}
    m = po.mle(x, xm)
    meth["mle"] = (m.canon, np.ones(1))
    lap = po.laplace(x, prior, "u", rng, 2000)
    meth["laplace_u"] = (lap.canon, np.ones(len(lap.canon)) / len(lap.canon))
    losses = {}
    rows = []
    for name, (c, w) in meth.items():
        v99 = tm.predictive_var(c, w, 0.99)
        v975 = tm.predictive_var(c, w, 0.975)
        e975 = tm.predictive_es(c, w, 0.975)
        exc = v99 < L
        lr, p_k = st.kupiec_pof(exc, 0.01)
        q99 = (L - v99) * (0.99 - (v99 > L))
        a = 0.025
        vr, er = -v975, -e975
        fz = -((vr - r) * (r <= vr)) / (a * er) + vr / er + np.log(-er) - 1
        losses[name] = (q99, fz)
        rows.append(
            {
                "n": n,
                "nu": nu,
                "rep": rep,
                "method": name,
                "exceed_rate": exc.mean(),
                "pop_exceed_prob": float(tm.stats.t.sf(v99 / s0, 1 / xi0)),
                "kupiec_p": p_k,
            }
        )
    for other in ("mle", "laplace_u"):
        s99, p99 = st.dm_test(losses["exact"][0], losses[other][0])
        sfz, pfz = st.dm_test(losses["exact"][1], losses[other][1])
        rows.append(
            {
                "n": n,
                "nu": nu,
                "rep": rep,
                "method": f"dm_exact_vs_{other}",
                "dm_q99": s99,
                "p_q99": p99,
                "dm_fz975": sfz,
                "p_fz975": pfz,
            }
        )
    return rows


def cmd_backtest_dm() -> None:
    cells = [(n, nu) for n in (250, 1000) for nu in (3.0, 6.0)]
    reps = 100
    ss = np.random.SeedSequence(SEED + 300)
    seeds = ss.spawn(len(cells) * reps)
    tasks = [
        (n, nu, r, seeds[i * reps + r]) for i, (n, nu) in enumerate(cells) for r in range(reps)
    ]
    rows = []
    with Pool(WORKERS) as pool:
        for res in pool.imap_unordered(_bt_one, tasks, chunksize=4):
            rows.extend(res)
    pd.DataFrame(rows).to_csv(RES / "r1_backtest_dm.csv", index=False)


# ----------------------------------------------------------------------------------------
# analysis
# ----------------------------------------------------------------------------------------
def _e5_tests(df: pd.DataFrame, rng) -> pd.DataFrame:
    keep = (df.policy_target == "-") | (df.policy_target == df.eval_target)
    d = df[keep]
    rows = []
    for (var, et), s in d.groupby(["variant", "eval_target"]):
        piv = s.pivot_table(index=["nu", "n0", "rep"], columns="policy", values="regret")
        norm = piv.div(piv["uniform"].groupby(level=["nu", "n0"]).transform("mean"), axis=0)
        for other in ("dopt", "predictive", "uniform"):
            r = st.paired_tests(norm["dr_local"].values, norm[other].values, rng)
            rows.append(
                {
                    "variant": var,
                    "target": et,
                    "comparison": f"dr_local vs {other}",
                    "ratio": r["ratio"],
                    "ci_diff": f"[{r['ci_lo']:.3f}, {r['ci_hi']:.3f}]",
                    "p_t": r["p_t"],
                    "p_wilcoxon": r["p_wilcoxon"],
                }
            )
    out = pd.DataFrame(rows)
    out["p_holm"] = np.nan
    for _var, idx in out.groupby("variant").groups.items():
        out.loc[idx, "p_holm"] = st.holm(out.loc[idx, "p_t"].values)
    return out


def cmd_analyze() -> None:
    t0 = time.time()
    print("=== R1 analysis ===")
    rng = np.random.default_rng(SEED)
    md = ["# R1 — Robustness re-runs and comparative backtests", ""]
    f = RES / "r1_e5_variants.csv"
    if f.exists():
        ev = pd.read_csv(f)
        tab = _e5_tests(ev, rng)
        mix = (
            ev[(ev.policy == "dr_local") & (ev.policy_target == ev.eval_target)]
            .groupby(["variant", "eval_target"])[["n_own", "n_peer", "n_rv"]]
            .mean()
            .reset_index()
        )
        base = pd.read_csv(RES / "e5_allocation.csv")
        base = base[base.policy != "dr_prepost"].assign(variant="original")
        both = pd.concat([base, ev], ignore_index=True)
        keep = (both.policy_target == "-") | (both.policy_target == both.eval_target)
        pooled = []
        for et, s in both[keep].groupby("eval_target"):
            piv = s.pivot_table(
                index=["variant", "nu", "n0", "rep"], columns="policy", values="regret"
            )
            norm = piv.div(
                piv["uniform"].groupby(level=["variant", "nu", "n0"]).transform("mean"), axis=0
            )
            for other in ("dopt", "predictive"):
                r = st.paired_tests(norm["dr_local"].values, norm[other].values, rng)
                per_run = norm.groupby(level="variant").apply(
                    lambda d, o=other: d["dr_local"].mean() / d[o].mean()
                )
                pooled.append(
                    {
                        "target": et,
                        "comparison": f"dr_local vs {other}",
                        "pooled_ratio": r["ratio"],
                        "p_t": r["p_t"],
                        "p_wilcoxon": r["p_wilcoxon"],
                        "runs_with_ratio<1": f"{int((per_run < 1).sum())}/{len(per_run)}",
                        "min_run_ratio": per_run.min(),
                        "max_run_ratio": per_run.max(),
                    }
                )
        pooled = pd.DataFrame(pooled)
        pooled["p_holm"] = st.holm(pooled.p_t.values)
        md += [
            "## 0. E5 pooled over the original run and all 5 variants (6 independent runs, "
            "2160 paired replications per target)",
            "",
            pooled.to_markdown(index=False, floatfmt=".4g"),
            "",
        ]
        print(pooled.to_string(index=False))
        md += [
            "## 1. E5 under design / seed variants (local policies only)",
            "",
            "Ratio = mean regret of DR-local / comparison policy after normalizing each condition "
            "by its uniform mean; paired t and Wilcoxon over 360 paired replications; Holm across "
            "the 9 comparisons within each variant.",
            "",
            tab.to_markdown(index=False, floatfmt=".4f"),
            "",
            "Source mix of DR-local:",
            "",
            mix.to_markdown(index=False, floatfmt=".2f"),
            "",
        ]
        print(tab.to_string(index=False))
    f = RES / "r1_h6_confirm.csv"
    if f.exists():
        h6 = pd.read_csv(f)
        piv = h6.pivot_table(index="rep", columns="policy", values="regret")
        r1 = st.paired_tests(piv["dr_prepost"].values, piv["dr_local"].values, rng)
        r2 = st.paired_tests(piv["dr_prepost"].values, piv["dopt"].values, rng)
        r3 = st.paired_tests(piv["dr_local"].values, piv["dopt"].values, rng)
        t = pd.DataFrame(
            [
                {
                    "comparison": k,
                    **{
                        kk: v[kk]
                        for kk in (
                            "n",
                            "ratio",
                            "mean_diff",
                            "ci_lo",
                            "ci_hi",
                            "p_t",
                            "p_wilcoxon",
                            "frac_tie",
                        )
                    },
                }
                for k, v in [
                    ("prepost vs local", r1),
                    ("prepost vs dopt", r2),
                    ("local vs dopt", r3),
                ]
            ]
        )
        md += [
            "## 2. H6 confirmatory test (nu=3, n0=100, VaR97.5, 32 preposterior sims)",
            "",
            t.to_markdown(index=False, floatfmt=".4g"),
            "",
        ]
        print(t.to_string(index=False))
    f = RES / "r1_e3_prior_swap.csv"
    if f.exists():
        ps_ = pd.read_csv(f)
        meth = ps_[ps_.functional == "__method__"].dropna(axis=1, how="all")
        func = ps_[(ps_.functional != "__method__") & (ps_.method != "__diag__")].dropna(
            axis=1, how="all"
        )
        g = func[func.method == "grid"].merge(
            meth[meth.method == "grid"][["n", "nu", "rep", "err_xi", "err_logsd"]],
            on=["n", "nu", "rep"],
        )
        h2 = []
        for fn in ["var95", "var975", "var99", "var999", "es975"]:
            s = g[g.functional == fn]
            rhos = [
                st_rho(np.abs(c.err_xi.values), c.regret.values) for _, c in s.groupby(["n", "nu"])
            ]
            h2.append(
                {
                    "functional": fn,
                    "mean_cell_rho(|err_xi|, regret)": np.nanmean(rhos),
                    "min": np.nanmin(rhos),
                    "max": np.nanmax(rhos),
                }
            )
        cov = (
            func[func.functional.isin(["var975", "var999", "es975"])]
            .groupby(["functional", "method"])["cover"]
            .mean()
            .unstack()
            .reset_index()
        )
        md += [
            "## 3. E3 subset with swapped priors (xi ~ HalfNormal(0.1), log sd ~ N(0.3, 0.5^2))",
            "",
            pd.DataFrame(h2).to_markdown(index=False, floatfmt=".4f"),
            "",
            "Coverage of 90% intervals:",
            "",
            cov.to_markdown(index=False, floatfmt=".4f"),
            "",
        ]
        print(pd.DataFrame(h2).to_string(index=False))
        print(cov.to_string(index=False))
    f = RES / "r1_backtest_dm.csv"
    if f.exists():
        bt = pd.read_csv(f)
        k = bt[~bt.method.str.startswith("dm_")]
        kt = (
            k.groupby(["n", "nu", "method"])
            .agg(
                exceed_rate=("exceed_rate", "mean"),
                pop_exceed=("pop_exceed_prob", "mean"),
                kupiec_reject_5pct=("kupiec_p", lambda p: float(np.mean(p < 0.05))),
            )
            .reset_index()
        )
        dm = bt[bt.method.str.startswith("dm_")]
        dmt = (
            dm.groupby(["n", "nu", "method"])
            .agg(
                mean_dm_q99=("dm_q99", "mean"),
                frac_exact_better_q99=("dm_q99", lambda s: float(np.mean(s < -1.96))),
                frac_exact_worse_q99=("dm_q99", lambda s: float(np.mean(s > 1.96))),
                mean_dm_fz=("dm_fz975", "mean"),
                frac_exact_better_fz=("dm_fz975", lambda s: float(np.mean(s < -1.96))),
                frac_exact_worse_fz=("dm_fz975", lambda s: float(np.mean(s > 1.96))),
            )
            .reset_index()
        )
        md += [
            "## 4. Finite-sample comparative backtests (T = 2500 out-of-sample days)",
            "",
            "Kupiec POF test of VaR99 exceedances (rejection rate at 5%; nominal 0.05 for a "
            "correct model), realized and population exceedance probabilities:",
            "",
            kt.to_markdown(index=False, floatfmt=".4f"),
            "",
            "Diebold-Mariano (Newey-West) tests, exact-posterior Bayes act vs competitor "
            "(negative = exact better); fraction of replications significant at 5%:",
            "",
            dmt.to_markdown(index=False, floatfmt=".4f"),
            "",
        ]
        print(kt.to_string(index=False))
        print(dmt.to_string(index=False))
    out = CFG["paths"]["reports"] / "r1_robustness.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"RESULT_PATHS: {out}")
    print(f"[DONE] {time.time() - t0:.1f}s")


def st_rho(a, b):
    """Spearman correlation (NaN-safe)."""
    from scipy import stats as sps

    ok = np.isfinite(a) & np.isfinite(b)
    return float(sps.spearmanr(a[ok], b[ok])[0]) if ok.sum() > 8 else np.nan


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "analyze"
    t0 = time.time()
    print(f"=== R1 {cmd} ===")
    {
        "e5_variants": cmd_e5_variants,
        "h6_confirm": cmd_h6_confirm,
        "e3_prior_swap": cmd_e3_prior_swap,
        "backtest_dm": cmd_backtest_dm,
        "analyze": cmd_analyze,
    }[cmd]()
    print(f"[DONE] {time.time() - t0:.1f}s")
