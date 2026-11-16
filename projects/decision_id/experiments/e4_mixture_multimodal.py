"""
E4 — Local vs global: near-redundant regime-mixture model

Calm/crisis scale mixture with two singular loci (p -> 0, s2 -> s1). Compares the exact grid
posterior with local approximations (Laplace + delta method, Laplace push-forward, MLE +
Wald = R_g(0)) for VaR/ES functionals, and records multimodality / singular-locus mass.

전제:
  config.yaml (e4 section)
출력:
  results/e4_mixture.csv
  figures/e4_mixture_example.png
  reports/e4_mixture_multimodal.md
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import sys  # noqa: E402
import time  # noqa: E402
from multiprocessing import Pool  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import optimize, stats  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_id import mixture as mx  # noqa: E402
from decision_id import plotstyle as ps  # noqa: E402
from decision_id.utils import load_config, num_hess, weighted_quantile  # noqa: E402

SEED = 42
CFG = load_config()
E4 = CFG["e4"]
FUNCS = [f"var{str(a)[2:]}" for a in E4["levels_var"]] + [
    f"es{str(a)[2:]}" for a in E4["levels_es"]
]
Z90 = 1.6448536269514722


def axes():
    """Grid axes in (logit p, log s2)."""
    g = E4["grid"]
    a = np.linspace(g["logit_p_lo"], g["logit_p_hi"], g["n_logit_p"])
    b = np.linspace(0.0, E4["prior"]["log_s2_max"], g["n_log_s2"])
    return a, b


def log_prior(A, B):
    """logit p ~ N(m, s^2); log s2 ~ U(0, log_s2_max)."""
    pr = E4["prior"]
    inside = (B >= 0) & (pr["log_s2_max"] >= B)
    return stats.norm.logpdf(A, pr["logit_p_mean"], pr["logit_p_sd"]) + np.where(inside, 0, -np.inf)


def n_local_max(dens: np.ndarray, rel: float = 0.01) -> int:
    """Number of strict local maxima (8-neighbourhood) above rel * max."""
    d = np.pad(dens, 1, constant_values=-np.inf)
    c = d[1:-1, 1:-1]
    is_max = np.ones_like(c, bool)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            if di == 0 and dj == 0:
                continue
            is_max &= c > d[1 + di : d.shape[0] - 1 + di, 1 + dj : d.shape[1] - 1 + dj]
    return int(np.sum(is_max & (c > rel * c.max())))


def run_one(task):
    """One replicate."""
    n, rep, seed = task
    rng = np.random.default_rng(seed)
    p0, s20, s1 = E4["truth"]["p"], E4["truth"]["s2"], E4["sigma1"]
    crisis = rng.uniform(size=n) < p0
    x = np.where(crisis, rng.normal(0, s20, n), rng.normal(0, s1, n))
    a, b = axes()
    A, B = np.meshgrid(a, b, indexing="ij")
    C = mx.canon(np.stack([A, B], -1))
    lp = mx.loglik_nodes(x, C[..., 0], C[..., 1], s1) + log_prior(A, B)
    w = np.exp(lp - lp.max())
    w /= w.sum()
    wf = w.ravel()
    Cf = C.reshape(-1, 2)
    rows = []
    key = {"n": n, "rep": rep}
    nmax = n_local_max(w)
    sing_mass = float(wf[(A.ravel() < -6) | (B.ravel() < 0.2)].sum())
    keep = wf > 1e-10 * wf.max()

    # MAP (Laplace) and MLE
    def nlp(ph):
        v = mx.loglik_nodes(x, np.array([mx.canon(ph)[0]]), np.array([mx.canon(ph)[1]]), s1)[0]
        return -(v + float(log_prior(np.array(ph[0]), np.array(ph[1]))))

    def nll(ph):
        return -mx.loglik_nodes(x, np.array([mx.canon(ph)[0]]), np.array([mx.canon(ph)[1]]), s1)[0]

    i0 = np.argmax(wf)
    start = np.array([A.ravel()[i0], max(B.ravel()[i0], 0.05)])
    bnds = [(-12, 3), (1e-4, E4["prior"]["log_s2_max"])]
    r_map = optimize.minimize(nlp, start, method="L-BFGS-B", bounds=bnds)
    r_mle = optimize.minimize(nll, start, method="L-BFGS-B", bounds=bnds)
    H = num_hess(nlp, r_map.x, rel=1e-4)
    try:
        cov = np.linalg.inv(H)
        np.linalg.cholesky(cov)
        lap_ok = True
    except np.linalg.LinAlgError:
        cov = np.diag(1 / np.maximum(np.abs(np.diag(H)), 1e-6))
        lap_ok = False
    if not np.all(np.isfinite(cov)):
        cov = np.diag([1e-6, 1e-6])
        lap_ok = False
    try:
        draws = rng.multivariate_normal(r_map.x, cov, size=2000, method="cholesky")
    except np.linalg.LinAlgError:
        draws = np.tile(r_map.x, (2000, 1))
        lap_ok = False
    inside = (draws[:, 1] >= 0) & (draws[:, 1] <= E4["prior"]["log_s2_max"])
    cd = mx.canon(draws[inside]) if inside.sum() > 20 else mx.canon(r_map.x)[None, :]
    I1 = mx.fisher(r_mle.x, s1)
    Itot = n * I1
    try:
        Iinv = np.linalg.inv(Itot)
    except np.linalg.LinAlgError:
        Iinv = np.full((2, 2), np.nan)

    for name in FUNCS:
        g0 = float(mx.functional(name, np.array([[p0, s20]]), s1)[0])
        gv = mx.functional(name, Cf[keep], s1)
        lo, hi = weighted_quantile(gv, wf[keep], [0.05, 0.95])
        mean_e = float(wf[keep] @ gv / wf[keep].sum())
        sd_e = float(np.sqrt(wf[keep] @ (gv - mean_e) ** 2 / wf[keep].sum()))
        rows.append(
            {
                **key,
                "method": "grid",
                "functional": name,
                "cover": float(lo <= g0 <= hi),
                "sd": sd_e,
                "n_local_max": nmax,
                "sing_mass": sing_mass,
            }
        )
        gm_ = mx.grad_functional(name, r_map.x, s1)
        sd_d = float(np.sqrt(max(gm_ @ cov @ gm_, 0.0)))
        gmap = float(mx.functional(name, mx.canon(r_map.x)[None, :], s1)[0])
        rows.append(
            {
                **key,
                "method": "laplace_delta",
                "functional": name,
                "cover": float(abs(gmap - g0) <= Z90 * sd_d),
                "sd": sd_d,
                "n_local_max": nmax,
                "sing_mass": sing_mass,
                "lap_ok": float(lap_ok),
            }
        )
        gd = mx.functional(name, cd, s1)
        lo2, hi2 = np.quantile(gd, [0.05, 0.95])
        rows.append(
            {
                **key,
                "method": "laplace_push",
                "functional": name,
                "cover": float(lo2 <= g0 <= hi2),
                "sd": float(np.std(gd)),
                "n_local_max": nmax,
                "sing_mass": sing_mass,
            }
        )
        gml = mx.grad_functional(name, r_mle.x, s1)
        sd_w = float(np.sqrt(max(gml @ Iinv @ gml, 0))) if np.all(np.isfinite(Iinv)) else np.nan
        gmle = float(mx.functional(name, mx.canon(r_mle.x)[None, :], s1)[0])
        rows.append(
            {
                **key,
                "method": "mle_wald",
                "functional": name,
                "cover": float(abs(gmle - g0) <= Z90 * sd_w) if np.isfinite(sd_w) else 0.0,
                "sd": sd_w,
                "n_local_max": nmax,
                "sing_mass": sing_mass,
            }
        )
    # decision: VaR99 Bayes act regret
    cc = Cf[keep]
    ww = wf[keep] / wf[keep].sum()
    for mname, (c_, w_) in {
        "grid": (cc, ww),
        "laplace_push": (cd, np.ones(len(cd)) / len(cd)),
        "mle_wald": (mx.canon(r_mle.x)[None, :], np.ones(1)),
    }.items():
        v = mx.predictive_var(c_, w_, 0.99, s1)
        rows.append(
            {
                **key,
                "method": mname,
                "functional": "decision_var99",
                "regret": float(mx.pinball_regret(v, 0.99, p0, s20, s1)),
                "n_local_max": nmax,
                "sing_mass": sing_mass,
            }
        )
    return rows


def example_figure(cfg):
    """Contour + functional-posterior figure for one hard n=250 dataset."""
    import matplotlib.pyplot as plt

    rng = np.random.default_rng(SEED + 7)
    p0, s20, s1 = E4["truth"]["p"], E4["truth"]["s2"], E4["sigma1"]
    best = None
    for _ in range(40):
        n = E4["n_grid"][0]
        crisis = rng.uniform(size=n) < p0
        x = np.where(crisis, rng.normal(0, s20, n), rng.normal(0, s1, n))
        a, b = axes()
        A, B = np.meshgrid(a, b, indexing="ij")
        C = mx.canon(np.stack([A, B], -1))
        lp = mx.loglik_nodes(x, C[..., 0], C[..., 1], s1) + log_prior(A, B)
        w = np.exp(lp - lp.max())
        w /= w.sum()
        sm = float(w[(A < -6) | (B < 0.2)].sum())
        if best is None or abs(sm - 0.3) < abs(best[0] - 0.3):
            best = (sm, x, A, B, C, w)
    sm, x, A, B, C, w = best
    wf = w.ravel()

    def nlp(ph):
        v = mx.loglik_nodes(x, np.array([mx.canon(ph)[0]]), np.array([mx.canon(ph)[1]]), s1)[0]
        return -(v + float(log_prior(np.array(ph[0]), np.array(ph[1]))))

    i0 = np.argmax(wf)
    r = optimize.minimize(
        nlp,
        [A.ravel()[i0], max(B.ravel()[i0], 0.05)],
        method="L-BFGS-B",
        bounds=[(-12, 3), (1e-4, E4["prior"]["log_s2_max"])],
    )
    cov = np.linalg.inv(num_hess(nlp, r.x))
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.3))
    order = np.argsort(wf)[::-1]
    cm = np.cumsum(wf[order])
    lv = [wf[order][np.searchsorted(cm, q)] for q in (0.99, 0.9, 0.5)]
    ax[0].contourf(
        A,
        B,
        w,
        levels=[lv[0], lv[1], lv[2], w.max() * 1.01],
        colors=[ps.SEQ[1], ps.SEQ[3], ps.SEQ[5]],
    )
    t = np.linspace(0, 2 * np.pi, 200)
    Lc = np.linalg.cholesky(cov)
    for k, c in ((1, ps.SERIES[1]), (2, ps.SERIES[1])):
        e = r.x[:, None] + k * Lc @ np.vstack([np.cos(t), np.sin(t)])
        ax[0].plot(
            e[0],
            e[1],
            color=c,
            lw=1.4 if k == 1 else 1.0,
            ls="-" if k == 1 else "--",
            label="Laplace 1/2-sd" if k == 1 else None,
        )
    for c, name in zip(ps.SERIES[2:], FUNCS, strict=False):
        g0 = float(mx.functional(name, np.array([[p0, s20]]), s1)[0])
        ax[0].contour(A, B, mx.functional(name, C, s1), levels=[g0], colors=[c], linewidths=1.5)
        ax[0].plot([], [], color=c, label=f"iso-{name}")
    ax[0].plot(
        np.log(p0 / (1 - p0)),
        np.log(s20),
        "*",
        color=ps.SERIES[7],
        ms=12,
        mec=ps.SURFACE,
        label="truth",
    )
    ax[0].set_xlabel("logit p (crisis probability)")
    ax[0].set_ylabel("log s2 (crisis vol)")
    ax[0].set_title(f"Posterior HPD 50/90/99%, n={len(x)}; singular-locus mass {sm:.2f}")
    ax[0].legend(fontsize=7, loc="upper right")
    draws = rng.multivariate_normal(r.x, cov, size=4000)
    draws = draws[(draws[:, 1] >= 0)]
    for axi, name in zip(ax[1:], ["var99", "es975"], strict=True):
        g0 = float(mx.functional(name, np.array([[p0, s20]]), s1)[0])
        keep = wf > 1e-10 * wf.max()
        gv = mx.functional(name, C.reshape(-1, 2)[keep], s1)
        gd = mx.functional(name, mx.canon(draws), s1)
        lo, hi = weighted_quantile(gv, wf[keep], [0.001, 0.995])
        lo, hi = lo - 0.1 * (hi - lo), hi + 0.1 * (hi - lo)
        fine = np.linspace(lo, hi, 400)
        bw = (hi - lo) / 80
        dens = np.array([np.sum(wf[keep] * np.exp(-0.5 * ((gv - f) / bw) ** 2)) for f in fine])
        dens /= np.trapezoid(dens, fine)
        axi.plot(fine, dens, color=ps.SERIES[0], label="exact (grid)")
        hd, ed = np.histogram(gd, bins=60, range=(lo, hi), density=True)
        axi.plot(0.5 * (ed[1:] + ed[:-1]), hd, color=ps.SERIES[1], lw=1.4, label="Laplace push-fwd")
        axi.axvline(g0, color=ps.TEXT2, lw=1)
        axi.set_title(f"{name} posterior")
        axi.set_yticks([])
        axi.legend(fontsize=7)
    ps.save(fig, cfg["paths"]["figures"] / "e4_mixture_example.png")


def main() -> None:
    t0 = time.time()
    print("=== E4 Mixture: local vs global ===")
    cfg = CFG
    for d in cfg["paths"].values():
        d.mkdir(parents=True, exist_ok=True)
    ps.apply()
    ss = np.random.SeedSequence(SEED)
    tasks = []
    seeds = ss.spawn(len(E4["n_grid"]) * E4["reps"])
    k = 0
    for n in E4["n_grid"]:
        for rep in range(E4["reps"]):
            tasks.append((n, rep, seeds[k]))
            k += 1
    rows = []
    with Pool(int(os.environ.get("DID_WORKERS", os.cpu_count() or 1))) as pool:
        for res in pool.imap_unordered(run_one, tasks, chunksize=4):
            rows.extend(res)
    df = pd.DataFrame(rows)
    out_csv = cfg["paths"]["results"] / "e4_mixture.csv"
    df.to_csv(out_csv, index=False)
    example_figure(cfg)
    f = df[df.functional != "decision_var99"]
    cov = f.groupby(["n", "functional", "method"])["cover"].mean().unstack("method").reset_index()
    f2 = f.assign(hard=(f.sing_mass > 0.05) | (f.n_local_max > 1))
    cov_h = f2.groupby(["n", "hard", "method"])["cover"].mean().unstack("method").reset_index()
    sdr = (
        f[f.method.isin(["grid", "laplace_delta", "mle_wald"])]
        .pivot_table(index=["n", "rep", "functional"], columns="method", values="sd")
        .reset_index()
    )
    sdr["delta_over_exact"] = sdr["laplace_delta"] / sdr["grid"]
    sdr["wald_over_exact"] = sdr["mle_wald"] / sdr["grid"]
    sdr_t = sdr.groupby(["n", "functional"])[["delta_over_exact", "wald_over_exact"]].median()
    dec = (
        df[df.functional == "decision_var99"]
        .groupby(["n", "method"])["regret"]
        .agg(["mean", "median"])
        .reset_index()
    )
    hard_frac = (
        f[f.method == "grid"]
        .groupby("n")
        .apply(
            lambda d: pd.Series(
                {
                    "frac_multimodal": (d.n_local_max > 1).mean(),
                    "mean_sing_mass": d.sing_mass.mean(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    md = [
        "# E4 — Local vs global: near-redundant regime mixture",
        "",
        f"Truth p = {E4['truth']['p']}, s2 = {E4['truth']['s2']} (s1 = {E4['sigma1']} known); "
        f"{E4['reps']} replications per n. Exact posterior on a "
        f"{E4['grid']['n_logit_p']}x{E4['grid']['n_log_s2']} grid.",
        "",
        "## Coverage of 90% intervals",
        "",
        cov.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Coverage split by 'hard' datasets (singular-locus mass > 5% or >1 local mode)",
        "",
        cov_h.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Median ratio of local SD to exact posterior SD",
        "",
        sdr_t.reset_index().to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Multimodality / singular-locus mass",
        "",
        hard_frac.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## VaR99 Bayes-act quantile-score regret",
        "",
        dec.to_markdown(index=False, floatfmt=".6f"),
        "",
        "Figure: `figures/e4_mixture_example.png`.",
    ]
    out_md = cfg["paths"]["reports"] / "e4_mixture_multimodal.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(cov.to_string(index=False))
    print(cov_h.to_string(index=False))
    print(sdr_t.to_string())
    print(hard_frac.to_string(index=False))
    print(dec.to_string(index=False))
    print(f"RESULT_PATHS: {out_csv}, {out_md}")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
