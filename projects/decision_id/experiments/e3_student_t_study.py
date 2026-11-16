"""
E3 — Replicated Student-t study (Stages 1-2): identifiability vs decision quality

Factors: sample length n x tail heaviness nu (config e3). Per replicate: exact grid
posterior, MLE (+Wald), Laplace in two parameterizations, mean-field / full-rank VI, MCMC
(subset). Records functional coverage, Bayes-act regrets under proper scores (quantile
score for VaR, FZ0 for (VaR, ES)), log-score regret, regrets under distribution shift, a
finite out-of-sample backtest, parameter errors, cost, and all diagnostics.

전제:
  config.yaml (e3, student_t sections)
출력:
  results/e3_raw.csv
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import sys  # noqa: E402
import time  # noqa: E402
from multiprocessing import Pool  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_id import diagnostics as dg  # noqa: E402
from decision_id import posterior as po  # noqa: E402
from decision_id import tmodel as tm  # noqa: E402
from decision_id.utils import load_config, num_jac  # noqa: E402

SEED = 42
FUNCS = ["var95", "var975", "var99", "var999", "es975", "es99", "variance"]
COORDS = ["logsd_xi", "eta_xi", "sigma_nu"]
CFG = load_config()


def shifted_truth(sigma0: float, xi0: float, sh: dict) -> tuple[float, float]:
    """Distribution-shift DGP: heavier tail and larger scale."""
    nu1 = max(sh["nu_factor"] / xi0, 2.1)
    return sigma0 * sh["sd_factor"], 1.0 / nu1


def acts(canon: np.ndarray, w: np.ndarray) -> dict:
    """Bayes acts under the posterior predictive (= predictive functionals)."""
    out = {}
    for name in FUNCS:
        if name.startswith("var"):
            out[name] = tm.predictive_var(canon, w, tm.level_of(name))
        elif name.startswith("es"):
            a = tm.level_of(name)
            out[name] = (tm.predictive_var(canon, w, a), tm.predictive_es(canon, w, a))
    return out


def regrets(act: dict, sigma: float, xi: float) -> dict:
    """Expected score regret of each act under (sigma, xi)."""
    out = {}
    for name, a in act.items():
        lvl = tm.level_of(name)
        if name.startswith("var"):
            out[name] = float(tm.pinball_regret(a, lvl, sigma, xi))
        else:
            out[name] = float(tm.fz0_regret(a[0], a[1], lvl, sigma, xi))
    return out


def run_one(task: tuple) -> list[dict]:
    """One replicate of one (n, nu) cell."""
    n, nu, rep, seed = task
    cfg = CFG
    e3 = cfg["e3"]
    st = cfg["student_t"]
    xm = st["xi_max"]
    rng = np.random.default_rng(seed)
    xi0 = 1.0 / nu
    sigma0 = e3["sd"] * np.sqrt(1 - 2 * xi0)
    canon0 = np.array([sigma0, xi0])
    sig1, xi1 = shifted_truth(sigma0, xi0, e3["shift"])
    x = tm.sample(rng, n, sigma0, xi0)
    L_bt = -tm.sample(rng, e3["backtest_len"], sigma0, xi0)
    prior = po.prior_from_cfg(cfg)
    alt = po.prior_from_cfg(cfg, alt=True)
    P_ref = prior.precision_logsd_xi()
    nd = e3["n_draws"]
    rows: list[dict] = []
    key = {"n": n, "nu": nu, "rep": rep}

    post, grid = po.grid_posterior(x, prior, st)
    posts = {"grid": post}
    phi_nodes = tm.phi_from(post.canon, "logsd_xi", xm)
    lw_alt = alt.logpdf_logsd_xi(phi_nodes[:, 0], phi_nodes[:, 1]) - prior.logpdf_logsd_xi(
        phi_nodes[:, 0], phi_nodes[:, 1]
    )
    post_alt = po.reweight(post, lw_alt, "grid_alt")
    posts["mle"] = po.mle(x, xm)
    posts["laplace_u"] = po.laplace(x, prior, "u", rng, nd)
    posts["laplace_nat"] = po.laplace(x, prior, "logsd_xi", rng, nd)
    posts["vi_mf"] = po.vi_gaussian(grid, prior, False, rng, nd)
    posts["vi_fr"] = po.vi_gaussian(grid, prior, True, rng, nd)
    if rep < e3["mcmc_reps"]:
        posts["mcmc"] = po.mcmc_rwm(x, prior, rng, e3["mcmc_iters"], e3["mcmc_burn"])

    phi_mle = posts["mle"].info["phi"]
    Itot_mle = n * tm.fisher(phi_mle, "logsd_xi", xm)
    z90 = 1.6448536269514722
    grid_act = None
    for mname, p in posts.items():
        cc, ww = tm.compress(p.canon, p.w, max_pts=3000)
        act = acts(cc, ww)
        if mname == "grid":
            grid_act = act
        reg = regrets(act, sigma0, xi0)
        reg_sh = regrets(act, sig1, xi1)
        m, _ = p.moments("logsd_xi", xm)
        q99 = act["var99"]
        q99_0 = tm.var_(sigma0, xi0, 0.99)
        bt = float(
            np.mean((L_bt - q99) * (0.99 - (L_bt < q99)))
            - np.mean((L_bt - q99_0) * (0.99 - (L_bt < q99_0)))
        )
        rows.append(
            {
                **key,
                "method": mname,
                "functional": "__method__",
                "err_xi": float(m[1] - xi0),
                "err_logsd": float(m[0] - np.log(e3["sd"])),
                "kl": tm.kl_truth_to_predictive(cc, ww, sigma0, xi0),
                "seconds": p.seconds,
                "bt_regret_var99": bt,
                "frac_outside": p.info.get("frac_outside", np.nan),
                "boundary": float(p.info.get("boundary", False)),
            }
        )
        for name in FUNCS:
            g0 = float(tm.functional(name, canon0))
            if mname == "mle":
                gr = tm.grad_functional(name, phi_mle, "logsd_xi", xm)
                sd = float(np.sqrt(dg.ridge_rg(Itot_mle, gr, 0.0)))
                ghat = float(tm.functional(name, p.canon[0]))
                lo, hi = ghat - z90 * sd, ghat + z90 * sd
            else:
                s = p.summary(name, e3["ci_level"])
                sd, lo, hi = s["sd"], s["lo"], s["hi"]
            a = act.get(name)
            point = a[1] if isinstance(a, tuple) else a
            rows.append(
                {
                    **key,
                    "method": mname,
                    "functional": name,
                    "cover": float(lo <= g0 <= hi),
                    "width_rel": (hi - lo) / g0,
                    "post_sd": sd,
                    "act": point,
                    "sqerr_rel": ((point - g0) / g0) ** 2 if point is not None else np.nan,
                    "regret": reg.get(name, np.nan),
                    "regret_shift": reg_sh.get(name, np.nan),
                }
            )

    # ---------------- diagnostics (data-only quantities) ----------------
    phi_pm, cov_pm = post.moments("logsd_xi", xm)
    Itot_pm = n * tm.fisher(phi_pm, "logsd_xi", xm)
    lam_fisher = np.linalg.eigvalsh(Itot_mle)
    cc_alt, ww_alt = tm.compress(post_alt.canon, post_alt.w, max_pts=3000)
    act_alt = acts(cc_alt, ww_alt)
    for name in FUNCS:
        g0 = float(tm.functional(name, canon0))
        d = {**key, "method": "__diag__", "functional": name}
        gr_mle = tm.grad_functional(name, phi_mle, "logsd_xi", xm)
        d["rg0_mle"] = dg.ridge_rg(Itot_mle, gr_mle, 0.0)
        for kind in COORDS:
            phk = tm.phi_from(posts["mle"].canon[0], kind, xm)
            Ik = n * tm.fisher(phk, kind, xm)
            gk = tm.grad_functional(name, phk, kind, xm)
            es = dg.eigen_scores(Ik, gk)
            d[f"eig_share_{kind}"] = es["weak_share"]
            d[f"eig_score_{kind}"] = es["weak_score"]
            d[f"ridge10_{kind}"] = dg.ridge_rg(Ik, gk, 10.0)
            J = num_jac(lambda p, k=kind: tm.phi_from(tm.canon_from(p, k, xm), "logsd_xi", xm), phk)
            wdk = dg.whitened_decomp(Ik, J.T @ P_ref @ J, gk)
            d[f"wh_pi_{kind}"] = wdk["pi"]
        gpm = tm.grad_functional(name, phi_pm, "logsd_xi", xm)
        wd = dg.whitened_decomp(Itot_pm, P_ref, gpm)
        d.update(
            {
                "wh_vpost": wd["v_post"],
                "wh_pi": wd["pi"],
                "wh_contraction": wd["contraction"],
                "wh_lam_min": float(wd["lam"].min()),
                "wh_weak_share": float(wd["contrib"][np.argmin(wd["lam"])] / wd["v_post"]),
                "fisher_lam_min": float(lam_fisher[0]),
                "post_tr_cov": float(np.trace(cov_pm)),
                "post_xi_sd": float(np.sqrt(cov_pm[1, 1])),
            }
        )
        gv = post.functional_samples(name)
        ok = np.isfinite(gv)
        wv = post.w[ok] / post.w[ok].sum()
        gm_ = wv @ gv[ok]
        d["exact_var"] = float(wv @ (gv[ok] - gm_) ** 2)
        d["exact_S"] = dg.exact_prior_sensitivity(phi_nodes[ok], wv, gv[ok], P_ref)
        d["exact_pi"] = d["exact_S"] ** 2 / max(d["exact_var"], 1e-300)
        d["delta_vs_exact_sd"] = float(np.sqrt(d["rg0_mle"] / max(d["exact_var"], 1e-300)))
        if name in act_alt:
            a0 = grid_act[name]
            a1 = act_alt[name]
            p0 = a0[1] if isinstance(a0, tuple) else a0
            p1 = a1[1] if isinstance(a1, tuple) else a1
            d["prior_sens"] = abs(p1 - p0) / np.sqrt(d["exact_var"])
        d["g0"] = g0
        rows.append(d)
    return rows


def main() -> None:
    t0 = time.time()
    print("=== E3 Student-t replicated study ===")
    cfg = CFG
    for d in cfg["paths"].values():
        d.mkdir(parents=True, exist_ok=True)
    e3 = cfg["e3"]
    ss = np.random.SeedSequence(SEED)
    tasks = []
    cells = [(n, nu) for n in e3["n_grid"] for nu in e3["nu_grid"]]
    seeds = ss.spawn(len(cells) * e3["reps"])
    k = 0
    for n, nu in cells:
        for rep in range(e3["reps"]):
            tasks.append((n, nu, rep, seeds[k]))
            k += 1
    print(f"  [STAGE] {len(cells)} cells x {e3['reps']} reps = {len(tasks):,} tasks")
    rows = []
    workers = int(os.environ.get("DID_WORKERS", os.cpu_count() or 1))
    with Pool(workers) as pool:
        for i, res in enumerate(pool.imap_unordered(run_one, tasks, chunksize=4)):
            rows.extend(res)
            if (i + 1) % 200 == 0:
                print(f"  done {i + 1:,}/{len(tasks):,}  ({time.time() - t0:.0f}s)")
    df = pd.DataFrame(rows)
    out = cfg["paths"]["results"] / "e3_raw.csv"
    df.to_csv(out, index=False)
    print(f"  rows: {len(df):,}")
    print(f"RESULT_PATHS: {out}")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
