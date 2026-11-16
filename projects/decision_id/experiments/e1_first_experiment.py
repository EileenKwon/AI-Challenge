"""
E1 — First experiment: weakly identified tail direction vs. financial functionals (Student-t)

Two-parameter Student-t return model (location known = 0), theta = (log sd, xi = 1/nu).
One dataset per sample length. Visualizes likelihood / posterior contours in three
parameterizations, Fisher eigenvectors, iso-functional curves, functional posteriors, and
the decision-relevance spectrum across VaR/ES levels.

전제:
  config.yaml (e1, student_t sections)
출력:
  figures/e1_contours_n{n}.png
  figures/e1_functional_posteriors.png
  figures/e1_spectrum.png
  results/e1_functional_table.csv
  reports/e1_first_experiment.md
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_id import diagnostics as dg  # noqa: E402
from decision_id import plotstyle as ps  # noqa: E402
from decision_id import posterior as po  # noqa: E402
from decision_id import tmodel as tm  # noqa: E402
from decision_id.utils import load_config, num_jac, weighted_mean_var  # noqa: E402

SEED = 42
FUNCS = ["var95", "var975", "var99", "var999", "es975", "es99", "variance"]
ISO_FUNCS = ["var95", "var975", "var99", "var999", "es975", "variance"]
COORDS = [
    ("logsd_xi", "log sd", "xi = 1/nu"),
    ("eta_xi", "log sigma", "xi = 1/nu"),
    ("sigma_nu", "sigma", "nu"),
]


def metric_in(kind: str, phi: np.ndarray, P_ref: np.ndarray, xi_max: float) -> np.ndarray:
    """Pull back the reference prior precision from (log sd, xi) to `kind` at phi."""
    J = num_jac(lambda p: tm.phi_from(tm.canon_from(p, kind, xi_max), "logsd_xi", xi_max), phi)
    return J.T @ P_ref @ J


def log_jac_density(kind: str, canon: np.ndarray) -> np.ndarray:
    """log |d(logsd, xi)/d(phi)| so that p_phi = p_(logsd,xi) * jac."""
    sigma, xi = canon[..., 0], canon[..., 1]
    if kind in ("logsd_xi", "eta_xi"):
        return np.zeros_like(sigma)
    if kind == "sigma_nu":
        return -np.log(sigma) + 2 * np.log(xi)  # 1/(sigma nu^2)
    raise ValueError(kind)


def hpd_levels(logdens: np.ndarray, mass: np.ndarray, probs) -> list[float]:
    """Density thresholds of HPD regions (masses are coordinate-invariant)."""
    order = np.argsort(logdens.ravel())[::-1]
    cm = np.cumsum(mass.ravel()[order])
    return [float(logdens.ravel()[order][np.searchsorted(cm, p)]) for p in probs]


def contour_figure(x, grid, post, mle_post, canon0, cfg, path):
    """Three-panel contour figure (one panel per parameterization)."""
    import matplotlib.pyplot as plt

    xm = cfg["student_t"]["xi_max"]
    prior = po.prior_from_cfg(cfg)
    L, X = np.meshgrid(grid.logsd, grid.xi, indexing="ij")
    canon = tm.canon_from(np.stack([L, X], -1), "logsd_xi", xm)
    loglik = grid.logpost - prior.logpdf_logsd_xi(L, X)
    loglik = loglik - np.nanmax(loglik[np.isfinite(loglik)])
    mass = grid.weights().reshape(L.shape)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    for ax, (kind, xl, yl) in zip(axes, COORDS, strict=True):
        P = tm.phi_from(canon, kind, xm)
        A, B = P[..., 0], P[..., 1]
        logdens = grid.logpost - grid.logpost.max() + log_jac_density(kind, canon)
        lv = hpd_levels(logdens, mass, [0.99, 0.9, 0.5])
        ax.contourf(
            A,
            B,
            logdens,
            levels=[lv[0], lv[1], lv[2], logdens.max() + 1],
            colors=[ps.SEQ[1], ps.SEQ[3], ps.SEQ[5]],
            alpha=0.85,
        )
        # likelihood contours: drops of 1.15, 3.0, 4.6 (approx. 68/95/99% for chi2_2 / 2)
        ax.contour(
            A,
            B,
            loglik,
            levels=[-4.6, -3.0, -1.15],
            colors=ps.TEXT2,
            linewidths=0.9,
            linestyles="--",
        )
        # iso-functional curves through the truth
        for c, name in zip(ps.SERIES, ISO_FUNCS, strict=False):
            gv = tm.functional(name, canon)
            g0 = tm.functional(name, canon0)
            ax.contour(A, B, gv, levels=[g0], colors=[c], linewidths=1.6)
            ax.plot([], [], color=c, label=f"iso-{name}")
        # Fisher eigenvectors at the MLE (scaled to 1-SE ellipse axes)
        phi_m = tm.phi_from(mle_post.canon[0], kind, xm)
        Itot = len(x) * tm.fisher(phi_m, kind, xm)
        lam, V = np.linalg.eigh(Itot)
        for j, lab in [(0, "weak"), (1, "strong")]:
            d = V[:, j] / np.sqrt(lam[j]) * 2.0
            ax.annotate(
                "",
                xy=phi_m + d,
                xytext=phi_m - d,
                arrowprops={"arrowstyle": "<->", "color": ps.TEXT, "lw": 1.4},
            )
            ax.text(*(phi_m + d * 1.08), f"Fisher {lab}", fontsize=8, color=ps.TEXT)
        p0 = tm.phi_from(canon0, kind, xm)
        ax.plot(
            *p0, marker="*", ms=12, color=ps.SERIES[7], mec=ps.SURFACE, ls="none", label="truth"
        )
        ax.plot(*phi_m, marker="o", ms=7, color=ps.TEXT, mec=ps.SURFACE, ls="none", label="MLE")
        ax.set_xlabel(xl)
        ax.set_ylabel(yl)
        # zoom to the 99.9% posterior region
        keep = logdens >= hpd_levels(logdens, mass, [0.999])[0]
        a_lo, a_hi = np.percentile(A[keep], [0, 100])
        b_lo, b_hi = np.percentile(B[keep], [0, 100])
        pad_a, pad_b = 0.15 * (a_hi - a_lo), 0.15 * (b_hi - b_lo)
        ax.set_xlim(a_lo - pad_a, a_hi + pad_a)
        ax.set_ylim(max(b_lo - pad_b, 0 if kind != "sigma_nu" else 2.0), b_hi + pad_b)
        if kind == "sigma_nu":
            ax.set_ylim(2.0, min(b_hi + pad_b, 40))
        ax.set_title(f"({xl}, {yl})")
    axes[0].legend(loc="upper center", bbox_to_anchor=(1.7, -0.13), fontsize=8, ncol=8)
    fig.suptitle(
        f"n = {len(x)}, true nu = {1 / canon0[1]:.0f}: posterior HPD 50/90/99% (blue), "
        "likelihood contours (dashed), iso-functional curves through truth",
        fontsize=10,
    )
    ps.save(fig, path)


def main() -> None:
    t0 = time.time()
    print("=== E1 First experiment (Student-t, weak tail direction) ===")
    cfg = load_config()
    for d in cfg["paths"].values():
        d.mkdir(parents=True, exist_ok=True)
    ps.apply()
    e1 = cfg["e1"]
    xm = cfg["student_t"]["xi_max"]
    xi0 = 1.0 / e1["nu"]
    sigma0 = e1["sd"] * np.sqrt(1 - 2 * xi0)
    canon0 = np.array([sigma0, xi0])
    prior = po.prior_from_cfg(cfg)
    P_ref = prior.precision_logsd_xi()
    rng = np.random.default_rng(SEED)
    rows = []
    store = {}
    for n in e1["n"]:
        print(f"  [STAGE] n={n}: simulate, grid posterior, MLE, Laplace")
        x = tm.sample(rng, n, sigma0, xi0)
        post, grid = po.grid_posterior(x, prior, cfg["student_t"])
        mle_post = po.mle(x, xm)
        lap = po.laplace(x, prior, "u", rng, 20000)
        store[n] = (x, post, grid, mle_post, lap)
        contour_figure(
            x, grid, post, mle_post, canon0, cfg, cfg["paths"]["figures"] / f"e1_contours_n{n}.png"
        )
        phi_post_mean = post.moments("logsd_xi", xm)[0]
        phi_mle = tm.phi_from(mle_post.canon[0], "logsd_xi", xm)
        Itot_ref = n * tm.fisher(phi_post_mean, "logsd_xi", xm)
        Itot_mle = n * tm.fisher(phi_mle, "logsd_xi", xm)
        # global Sobol index of xi under the exact posterior
        w2 = grid.weights().reshape(grid.logpost.shape)
        for name in FUNCS:
            s = post.summary(name)
            g0 = float(tm.functional(name, canon0))
            g_mle = tm.grad_functional(name, phi_mle, "logsd_xi", xm)
            rg0 = dg.ridge_rg(Itot_mle, g_mle, 0.0)
            gpm = tm.grad_functional(name, phi_post_mean, "logsd_xi", xm)
            wd = dg.whitened_decomp(Itot_ref, P_ref, gpm)
            weak_j = int(np.argmin(wd["lam"]))
            gv = tm.functional(name, grid.canon(xm)).reshape(w2.shape)
            m_all, v_all = weighted_mean_var(gv.ravel(), w2.ravel())
            cond_mean = (w2 * gv).sum(axis=0) / np.maximum(w2.sum(axis=0), 1e-300)
            sobol_xi = float(np.sum(w2.sum(axis=0) * (cond_mean - m_all) ** 2) / v_all)
            row = {
                "n": n,
                "functional": name,
                "true": g0,
                "post_mean": s["mean"],
                "post_sd_exact": s["sd"],
                "sd_delta_mle": np.sqrt(rg0),
                "sd_ratio_delta_exact": np.sqrt(rg0) / s["sd"],
                "lap_u_sd": lap.summary(name)["sd"],
                "whitened_lam_weak": float(wd["lam"][weak_j]),
                "whitened_weak_share": float(wd["contrib"][weak_j] / wd["v_post"]),
                "sobol_xi_exact": sobol_xi,
                "pi_g": wd["pi"],
                "contraction": wd["contraction"],
            }
            for kind, _, _ in COORDS:
                phi_k = tm.phi_from(mle_post.canon[0], kind, xm)
                es = dg.eigen_scores(
                    n * tm.fisher(phi_k, kind, xm), tm.grad_functional(name, phi_k, kind, xm)
                )
                row[f"eig_weak_share_{kind}"] = es["weak_share"]
            if name.startswith("var"):
                a = tm.level_of(name)
                kappa = tm.pinball_curvature(a, *canon0)
                v_b = tm.predictive_var(*tm.compress(post.canon, post.w), a)
                row["kappa"] = kappa
                row["regret_proxy"] = 0.5 * kappa * rg0
                cc, ww = tm.compress(post.canon, post.w)
                row["evpi_exact"] = float(ww @ tm.pinball_regret(v_b, a, cc[:, 0], cc[:, 1]))
            rows.append(row)
    df = pd.DataFrame(rows)
    out_csv = cfg["paths"]["results"] / "e1_functional_table.csv"
    df.to_csv(out_csv, index=False)

    # ---------------- functional posterior figure ----------------
    import matplotlib.pyplot as plt

    print("  [STAGE] functional posterior figure")
    n_show = e1["n"][0]
    x, post, grid, mle_post, lap = store[n_show]
    fig, axes = plt.subplots(1, len(FUNCS), figsize=(17, 2.9))
    phi_u = lap.info["mode"]
    for ax, name in zip(axes, FUNCS, strict=True):
        g0 = float(tm.functional(name, canon0))
        gv = post.functional_samples(name) / g0
        lo, hi = np.percentile(lap.functional_samples(name) / g0, [0.2, 99.8])
        bins = np.linspace(lo, hi, 60)
        # weighted KDE of the grid functional values (avoids grid aliasing in histograms)
        fine = np.linspace(lo, hi, 600)
        bw = 1.5 * (bins[1] - bins[0])
        h_f = np.array([np.sum(post.w * np.exp(-0.5 * ((gv - f) / bw) ** 2)) for f in fine])
        h_f /= np.trapezoid(h_f, fine)
        edges = bins
        ctr = 0.5 * (edges[1:] + edges[:-1])
        h = np.interp(ctr, fine, h_f)
        ax.plot(ctr, h, color=ps.SERIES[0], label="exact (grid)")
        gl = lap.functional_samples(name) / g0
        hl, _ = np.histogram(gl, bins=bins, density=True)
        ax.plot(ctr, hl, color=ps.SERIES[1], lw=1.4, label="Laplace-u push-fwd")
        gu = tm.grad_functional(name, phi_u, "u", xm)
        sd_d = np.sqrt(gu @ lap.info["cov"] @ gu) / g0
        mu_d = float(tm.functional(name, tm.canon_from(phi_u, "u", xm))) / g0
        ax.plot(
            ctr,
            np.exp(-0.5 * ((ctr - mu_d) / sd_d) ** 2) / (sd_d * np.sqrt(2 * np.pi)),
            color=ps.SERIES[2],
            lw=1.4,
            ls="--",
            label="delta method",
        )
        ax.axvline(1.0, color=ps.TEXT2, lw=1)
        ax.set_title(name)
        ax.set_yticks([])
        ax.set_xlabel("g / g_true")
    axes[0].legend(loc="upper left", fontsize=7)
    fig.suptitle(f"Functional posteriors, n = {n_show}, nu = {e1['nu']:.0f}", fontsize=10, y=1.06)
    ps.save(fig, cfg["paths"]["figures"] / "e1_functional_posteriors.png")

    # ---------------- spectrum figure ----------------
    print("  [STAGE] decision-relevance spectrum across levels")
    alphas = np.concatenate([np.linspace(0.90, 0.99, 37), np.linspace(0.9925, 0.999, 10)])
    phi0 = tm.phi_from(canon0, "logsd_xi", xm)
    fig, axes = plt.subplots(1, 3, figsize=(15, 3.9))
    for fam, col in (("var", ps.SERIES[0]), ("es", ps.SERIES[1])):
        sens = []
        for a in alphas:

            def f(c, a=a, fam=fam):
                return tm.var_(c[0], c[1], a) if fam == "var" else tm.es_(c[0], c[1], a)

            h = 1e-5

            def gx(p, f=f):
                return f(tm.canon_from(p, "logsd_xi", xm))

            d = (gx(phi0 + [0, h]) - gx(phi0 - [0, h])) / (2 * h)
            sens.append(d / gx(phi0))
        axes[0].plot(alphas, sens, color=col, label=fam.upper())
    axes[0].axhline(0, color=ps.TEXT2, lw=0.8)
    axes[0].set_title("Relative sensitivity d log g / d xi at fixed sd")
    axes[0].set_xlabel("level alpha")
    axes[0].legend()
    spec_rows = []
    for k, n in enumerate(e1["n"]):
        x, post, grid, mle_post, lap = store[n]
        w2 = grid.weights().reshape(grid.logpost.shape)
        phi_pm = post.moments("logsd_xi", xm)[0]
        Itot = n * tm.fisher(phi_pm, "logsd_xi", xm)
        share_loc, sobol, regret_px = [], [], []
        for a in alphas:
            name = f"var{str(a)[2:]}"
            gpm = tm.grad_functional(name, phi_pm, "logsd_xi", xm)
            wd = dg.whitened_decomp(Itot, P_ref, gpm)
            j = int(np.argmin(wd["lam"]))
            share_loc.append(wd["contrib"][j] / wd["v_post"])
            gv = tm.var_(*grid.canon(xm).T, a).reshape(w2.shape)
            m_all, v_all = weighted_mean_var(gv.ravel(), w2.ravel())
            cm = (w2 * gv).sum(axis=0) / np.maximum(w2.sum(axis=0), 1e-300)
            sobol.append(np.sum(w2.sum(axis=0) * (cm - m_all) ** 2) / v_all)
            kap = tm.pinball_curvature(a, *canon0)
            regret_px.append(0.5 * kap * v_all)
            spec_rows.append(
                {
                    "n": n,
                    "alpha": a,
                    "weak_share_local": share_loc[-1],
                    "sobol_xi_exact": sobol[-1],
                    "regret_proxy": regret_px[-1],
                    "post_var": v_all,
                }
            )
        c = ps.SERIES[2 * k]
        axes[1].plot(alphas, share_loc, color=c, label=f"local weak share, n={n}")
        axes[1].plot(alphas, sobol, color=c, ls="--", lw=1.4, label=f"exact Sobol(xi), n={n}")
        axes[2].plot(alphas, regret_px, color=c, label=f"n={n}")
    axes[1].set_title("Share of VaR posterior variance from weak (tail) direction")
    axes[1].set_xlabel("level alpha")
    axes[1].legend(fontsize=7)
    axes[2].set_title("Expected quantile-score regret proxy 0.5 f(q) Var(VaR)")
    axes[2].set_xlabel("level alpha")
    axes[2].set_yscale("log")
    axes[2].legend()
    ps.save(fig, cfg["paths"]["figures"] / "e1_spectrum.png")
    spec = pd.DataFrame(spec_rows)
    spec.to_csv(cfg["paths"]["results"] / "e1_spectrum.csv", index=False)

    # ---------------- report ----------------
    cols = [
        "n",
        "functional",
        "true",
        "post_mean",
        "post_sd_exact",
        "sd_ratio_delta_exact",
        "whitened_lam_weak",
        "whitened_weak_share",
        "sobol_xi_exact",
        "pi_g",
        "eig_weak_share_logsd_xi",
        "eig_weak_share_eta_xi",
        "eig_weak_share_sigma_nu",
    ]
    md = [
        "# E1 — First experiment (Student-t, weak tail direction)",
        "",
        f"True model: nu = {e1['nu']}, sd = {e1['sd']} (percent), location known = 0.",
        "Exact posterior on an adaptive (log sd, xi) grid; prior log sd ~ N(0,1), "
        f"xi ~ U(0, {xm}).",
        "",
        "## Functional table",
        "",
        df[cols].to_markdown(index=False, floatfmt=".4f"),
        "",
        "## VaR-level spectrum (selected levels)",
        "",
        spec[spec["alpha"].isin([0.9, 0.95, 0.975, 0.99, 0.999])].to_markdown(
            index=False, floatfmt=".4f"
        ),
        "",
        "Figures: `figures/e1_contours_n*.png`, `figures/e1_functional_posteriors.png`, "
        "`figures/e1_spectrum.png`.",
    ]
    out_md = cfg["paths"]["reports"] / "e1_first_experiment.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(
        df[
            [
                "n",
                "functional",
                "post_sd_exact",
                "sd_ratio_delta_exact",
                "whitened_weak_share",
                "sobol_xi_exact",
                "eig_weak_share_eta_xi",
            ]
        ].to_string(index=False)
    )
    print(f"RESULT_PATHS: {out_csv}, {out_md}")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
