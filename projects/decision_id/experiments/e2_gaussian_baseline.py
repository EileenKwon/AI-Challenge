"""
E2 — Gaussian baseline: exactness checks and location-vs-scale decoupling

Gaussian returns with conjugate NIG prior (exact posterior). Compares MLE/Wald, Laplace,
MCMC and mean-field VI against the exact posterior, and shows that the weakly identified
location parameter (relative to its size) matters for the portfolio weight but little
for VaR/ES.

전제:
  config.yaml (gaussian section)
출력:
  results/e2_gaussian.csv
  reports/e2_gaussian_baseline.md
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_id import gaussian as gm  # noqa: E402
from decision_id.utils import load_config  # noqa: E402

SEED = 42
FUNCS = ["var99", "es975", "weight", "variance"]
CI = 0.90


def pred_var_mix(draws: np.ndarray, alpha: float) -> float:
    """Loss VaR of a Gaussian mixture (posterior predictive) by bisection."""
    mu, sd = draws[:, 0], draws[:, 1]
    q = gm.var_(mu, sd, alpha)
    lo, hi = q.min(), q.max()
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if np.mean(stats.norm.cdf((mid + mu) / sd)) < alpha:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def evaluate(draws, name, mu0, sd0, gamma):
    """Coverage / interval of a functional from posterior draws."""
    g = gm.functional(name, draws[:, 0], draws[:, 1], gamma)
    lo, hi = np.quantile(g, [(1 - CI) / 2, (1 + CI) / 2])
    g0 = gm.functional(name, mu0, sd0, gamma)
    return {"cover": float(lo <= g0 <= hi), "width": float(hi - lo), "sd": float(np.std(g))}


def main() -> None:
    t0 = time.time()
    print("=== E2 Gaussian baseline ===")
    cfg = load_config()
    for d in cfg["paths"].values():
        d.mkdir(parents=True, exist_ok=True)
    gc = cfg["gaussian"]
    mu0, sd0, gamma = gc["truth"]["mu"], gc["truth"]["sd"], gc["gamma"]
    prior = gm.NIG(**gc["prior"])
    rng = np.random.default_rng(SEED)
    rows = []
    for n in gc["n_grid"]:
        print(f"  [STAGE] n={n}")
        for r in range(gc["reps"]):
            x = rng.normal(mu0, sd0, n)
            post = prior.update(x)
            methods = {
                "exact": post.sample(rng, 4000),
                "laplace": gm.laplace(x, prior, rng, 4000)[0],
                "vi_mf": gm.vi_meanfield(x, prior, rng, 4000),
            }
            if r < 50:
                methods["mcmc"] = gm.mcmc(x, prior, rng, 8000, 2000)
            th = gm.mle(x)
            # Wald (delta method) for the MLE, R_g with lambda = 0
            Itot = n * gm.fisher(*th)
            for name in FUNCS:
                g0 = gm.functional(name, mu0, sd0, gamma)

                def gfun(p, name=name):
                    return gm.functional(name, p[0], np.exp(p[1]), gamma)

                p = np.array([th[0], np.log(th[1])])
                grad = np.array([(gfun(p + e) - gfun(p - e)) / 2e-6 for e in np.eye(2) * 1e-6])
                rg = grad @ np.linalg.solve(Itot, grad)
                share_mu = (grad[0] ** 2 / Itot[0, 0]) / rg
                ghat = gm.functional(name, th[0], th[1], gamma)
                z = stats.norm.ppf(0.5 + CI / 2)
                rows.append(
                    {
                        "n": n,
                        "rep": r,
                        "method": "mle_wald",
                        "functional": name,
                        "cover": float(abs(ghat - g0) <= z * np.sqrt(rg)),
                        "width": 2 * z * np.sqrt(rg),
                        "share_mu": share_mu,
                        "regret": np.nan,
                    }
                )
                for mname, dr in methods.items():
                    ev = evaluate(dr, name, mu0, sd0, gamma)
                    ev.update(
                        {
                            "n": n,
                            "rep": r,
                            "method": mname,
                            "functional": name,
                            "share_mu": share_mu,
                            "regret": np.nan,
                        }
                    )
                    rows.append(ev)
            # decisions: Bayes acts under exact posterior vs MLE plug-in
            dr = methods["exact"]
            v_b = pred_var_mix(dr, 0.99)
            w_b = np.mean(dr[:, 0]) / (gamma * np.mean(dr[:, 1] ** 2))
            ce_opt = mu0**2 / (2 * gamma * sd0**2)
            ep0 = gm.pinball_regret(gm.var_(mu0, sd0, 0.99) + 0, 0.99, mu0, sd0)
            del ep0
            rows.append(
                {
                    "n": n,
                    "rep": r,
                    "method": "exact",
                    "functional": "decision",
                    "regret_var99": float(gm.pinball_regret(v_b, 0.99, mu0, sd0)),
                    "regret_w_rel": float(gm.weight_regret(w_b, mu0, sd0, gamma) / ce_opt),
                    "relerr_mu": abs(np.mean(dr[:, 0]) - mu0) / abs(mu0),
                    "relerr_sd": abs(np.mean(dr[:, 1]) - sd0) / sd0,
                    "relerr_var99": abs(v_b - gm.var_(mu0, sd0, 0.99)) / gm.var_(mu0, sd0, 0.99),
                }
            )
            vb_mle = gm.var_(th[0], th[1], 0.99)
            rows.append(
                {
                    "n": n,
                    "rep": r,
                    "method": "mle_wald",
                    "functional": "decision",
                    "regret_var99": float(gm.pinball_regret(vb_mle, 0.99, mu0, sd0)),
                    "regret_w_rel": float(
                        gm.weight_regret(gm.weight_(th[0], th[1], gamma), mu0, sd0, gamma) / ce_opt
                    ),
                    "relerr_mu": abs(th[0] - mu0) / abs(mu0),
                    "relerr_sd": abs(th[1] - sd0) / sd0,
                    "relerr_var99": abs(vb_mle - gm.var_(mu0, sd0, 0.99)) / gm.var_(mu0, sd0, 0.99),
                }
            )
    df = pd.DataFrame(rows)
    out_csv = cfg["paths"]["results"] / "e2_gaussian.csv"
    df.to_csv(out_csv, index=False)
    cov = (
        df[df.functional != "decision"]
        .groupby(["n", "functional", "method"])["cover"]
        .mean()
        .unstack("method")
        .reset_index()
    )
    share = (
        df[(df.functional != "decision") & (df.method == "exact")]
        .groupby(["n", "functional"])["share_mu"]
        .mean()
        .unstack("functional")
        .reset_index()
    )
    dec = (
        df[df.functional == "decision"]
        .groupby(["n", "method"])[
            ["relerr_mu", "relerr_sd", "relerr_var99", "regret_var99", "regret_w_rel"]
        ]
        .median()
        .reset_index()
    )
    md = [
        "# E2 — Gaussian baseline (exact conjugate posterior)",
        "",
        f"True mu = {mu0} %/day, sd = {sd0} %/day, risk aversion gamma = {gamma}; "
        f"{gc['reps']} replications per n (MCMC on 50).",
        "",
        f"## Coverage of {CI:.0%} intervals for functionals",
        "",
        cov.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Share of the delta-method variance due to the location direction (mu)",
        "",
        share.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Median parameter errors vs decision regrets",
        "",
        "regret_w_rel = certainty-equivalent loss of the estimated weight divided by the "
        "optimal certainty-equivalent gain (values > 1 mean worse than holding cash).",
        "",
        dec.to_markdown(index=False, floatfmt=".4f"),
    ]
    out_md = cfg["paths"]["reports"] / "e2_gaussian_baseline.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(cov.to_string(index=False))
    print(share.to_string(index=False))
    print(dec.to_string(index=False))
    print(f"RESULT_PATHS: {out_csv}, {out_md}")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
