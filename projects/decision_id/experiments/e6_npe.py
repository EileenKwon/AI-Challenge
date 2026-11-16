"""
E6 — Standard neural posterior estimation (NPE) baseline vs exact grid posterior

Trains an amortized Gaussian-head NPE (numpy MLP) on prior-predictive simulations for each
sample length, then compares functional coverage, Bayes-act regrets and log-score regret
with the exact grid posterior on held-out datasets at fixed tail indices.

전제:
  config.yaml (e6, student_t sections)
출력:
  results/e6_npe.csv
  reports/e6_npe.md
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_id import npe  # noqa: E402
from decision_id import posterior as po  # noqa: E402
from decision_id import tmodel as tm  # noqa: E402
from decision_id.utils import load_config  # noqa: E402

SEED = 42
FUNCS = ["var975", "var99", "var999", "es975"]


def main() -> None:
    t0 = time.time()
    print("=== E6 NPE baseline ===")
    cfg = load_config()
    for d in cfg["paths"].values():
        d.mkdir(parents=True, exist_ok=True)
    e6 = cfg["e6"]
    xm = cfg["student_t"]["xi_max"]
    prior = po.prior_from_cfg(cfg)
    rng = np.random.default_rng(SEED)
    rows = []
    train_info = []
    for n in e6["n"]:
        print(f"  [STAGE] n={n}: simulate {e6['n_train']:,} training sets")
        t1 = time.time()
        S, U = npe.simulate_training(rng, n, e6["n_train"], prior, xm)
        t_sim = time.time() - t1
        model = npe.GaussNPE(S.shape[1], e6["hidden"], rng)
        t1 = time.time()
        hist = model.fit(S, U, e6["epochs"], e6["lr"], rng)
        t_train = time.time() - t1
        train_info.append(
            {"n": n, "sim_seconds": t_sim, "train_seconds": t_train, "final_nll": hist[-1]}
        )
        print(f"    train nll {hist[0]:.3f} -> {hist[-1]:.3f}  ({t_train:.0f}s)")
        for nu in e6["nu_test"]:
            xi0 = 1 / nu
            s0 = np.sqrt(1 - 2 * xi0)
            for rep in range(e6["n_test"]):
                x = tm.sample(rng, n, s0, xi0)
                post, _ = po.grid_posterior(x, prior, cfg["student_t"])
                t1 = time.time()
                c_npe = npe.posterior_canon(model, x, 2000, rng, xm)
                t_inf = time.time() - t1
                for mname, (cc, ww) in {
                    "grid": tm.compress(post.canon, post.w, max_pts=3000),
                    "npe": (c_npe, np.ones(len(c_npe)) / len(c_npe)),
                }.items():
                    p = po.Posterior(cc, ww, mname)
                    kl = tm.kl_truth_to_predictive(cc, ww, s0, xi0)
                    xi_mean = float(ww @ cc[:, 1])
                    for name in FUNCS:
                        g0 = float(tm.functional(name, np.array([s0, xi0])))
                        sm = p.summary(name)
                        a = tm.level_of(name)
                        if name.startswith("var"):
                            reg = float(tm.pinball_regret(tm.predictive_var(cc, ww, a), a, s0, xi0))
                        else:
                            reg = float(
                                tm.fz0_regret(
                                    tm.predictive_var(cc, ww, a),
                                    tm.predictive_es(cc, ww, a),
                                    a,
                                    s0,
                                    xi0,
                                )
                            )
                        rows.append(
                            {
                                "n": n,
                                "nu": nu,
                                "rep": rep,
                                "method": mname,
                                "functional": name,
                                "cover": float(sm["lo"] <= g0 <= sm["hi"]),
                                "width_rel": (sm["hi"] - sm["lo"]) / g0,
                                "regret": reg,
                                "kl": kl,
                                "err_xi": abs(xi_mean - xi0),
                                "infer_seconds": t_inf if mname == "npe" else post.seconds,
                            }
                        )
    df = pd.DataFrame(rows)
    out_csv = cfg["paths"]["results"] / "e6_npe.csv"
    df.to_csv(out_csv, index=False)
    tab = (
        df.groupby(["n", "nu", "functional", "method"])[["cover", "width_rel", "regret"]]
        .mean()
        .unstack("method")
        .reset_index()
    )
    tab.columns = ["_".join(c).strip("_") for c in tab.columns]
    gen = (
        df[df.functional == "var99"]
        .groupby(["n", "nu", "method"])[["kl", "err_xi", "infer_seconds"]]
        .mean()
        .unstack("method")
        .reset_index()
    )
    gen.columns = ["_".join(c).strip("_") for c in gen.columns]
    md = [
        "# E6 — Standard NPE (Gaussian head, numpy) vs exact grid posterior",
        "",
        f"Training: {e6['n_train']:,} prior-predictive simulations per n, {e6['epochs']} epochs.",
        "",
        pd.DataFrame(train_info).to_markdown(index=False, floatfmt=".3f"),
        "",
        "## Functional coverage (90%), relative width, Bayes-act regret",
        "",
        tab.to_markdown(index=False, floatfmt=".5f"),
        "",
        "## Log-score regret (KL), tail-index error, inference seconds per dataset",
        "",
        gen.to_markdown(index=False, floatfmt=".5f"),
    ]
    out_md = cfg["paths"]["reports"] / "e6_npe.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(tab.to_string(index=False))
    print(gen.to_string(index=False))
    print(f"RESULT_PATHS: {out_csv}, {out_md}")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
