"""
E5 — Stage 3/4: decision-targeted observation allocation across data sources

Sequential allocation of a fixed budget among three sources (own returns, peer standardized
residuals sharing the tail index, noisy variance proxies). Policies: uniform, own_only,
Fisher-only D-optimal, predictive (log-score), decision-weighted local (Bayesian
c/L-optimality with score curvature) and decision-weighted preposterior EVSI (exact grid
updates). Evaluation: out-of-sample (population) score regret of the final Bayes act under
the true DGP, functional coverage, tail-index error, log-score regret, cost.

전제:
  config.yaml (e5, student_t sections)
출력:
  results/e5_allocation.csv
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_id import allocation as al  # noqa: E402
from decision_id import posterior as po  # noqa: E402
from decision_id import tmodel as tm  # noqa: E402
from decision_id.utils import load_config  # noqa: E402

SEED = 42
CFG = load_config()
E5 = CFG["e5"]
XM = CFG["student_t"]["xi_max"]
M = E5["sources"]["rv"]["m"]
UNITS = {s: int(round(E5["batch_cost"] / E5["sources"][s]["cost"])) for s in al.SOURCES}
TARGET_FUNC = {"var975": "var975", "fz975": "es975", "var999": "var999"}
BASE_POLICIES = ["uniform", "own_only", "dopt", "predictive"]
DR_POLICIES = ["dr_local", "dr_prepost"]


def run_one(task):
    """One replicate: all policies share data pools (common random numbers)."""
    nu, n0, rep, seed = task
    t_start = time.time()
    rng = np.random.default_rng(seed)
    base = int(seed.generate_state(1)[0])
    xi0 = 1.0 / nu
    sigma0 = np.sqrt(1 - 2 * xi0)  # sd = 1
    B = E5["batches"]
    own0 = tm.sample(rng, n0, sigma0, xi0)
    pools = {s: al.simulate_source(rng, s, UNITS[s] * B, sigma0, xi0, M) for s in al.SOURCES}
    prior = po.prior_from_cfg(CFG)
    fits: dict = {}
    crit_cache: dict = {}
    timing = {"fit": 0.0, "prepost": 0.0, "local": 0.0}

    def data_for(prefix):
        k = {s: prefix.count(s) * UNITS[s] for s in al.SOURCES}
        return al.Data(
            own=np.concatenate([own0, pools["own"][: k["own"]]]),
            peer=pools["peer"][: k["peer"]],
            rv=pools["rv"][: k["rv"]],
        )

    def fit(prefix):
        if prefix not in fits:
            t = time.time()
            fits[prefix] = al.fit_posterior(data_for(prefix), prior, M)
            timing["fit"] += time.time() - t
        return fits[prefix]

    def choose(policy, prefix, step, target):
        if policy == "uniform":
            return al.SOURCES[step % 3]
        if policy == "own_only":
            return "own"
        post, grid = fit(prefix)
        ck = (policy, prefix, target if policy.startswith("dr") else None)
        if ck not in crit_cache:
            if policy == "dr_prepost":
                t = time.time()
                tidx = list(al.TARGETS).index(target)
                r2 = np.random.default_rng(
                    [base, step, tidx, len(prefix), *[al.SOURCES.index(c) for c in prefix]]
                )
                cr = al.criterion_prepost(
                    r2, grid, data_for(prefix), UNITS, M, XM, target, E5["preposterior_sims"], prior
                )
                crit_cache[ck] = {s: cr[s]["dr_prepost"] for s in al.SOURCES}
                timing["prepost"] += time.time() - t
            else:
                t = time.time()
                cr = al.criteria_local(post, UNITS, M, XM, target)
                crit_cache[ck] = {s: cr[s][policy] for s in al.SOURCES}
                timing["local"] += time.time() - t
        vals = crit_cache[ck]
        return max(al.SOURCES, key=lambda s: vals[s])

    runs = [(p, None) for p in BASE_POLICIES] + [(p, t) for p in DR_POLICIES for t in E5["targets"]]
    rows = []
    for policy, target in runs:
        prefix: tuple = ()
        for step in range(B):
            prefix = prefix + (choose(policy, prefix, step, target),)
        post, grid = fit(prefix)
        cc, ww = tm.compress(post.canon, post.w, max_pts=3000)
        m_, _ = post.moments("logsd_xi", XM)
        kl = tm.kl_truth_to_predictive(cc, ww, sigma0, xi0)
        for et in E5["targets"]:
            act = al.target_act(et, cc, ww)
            reg = float(al.target_regret(et, act, sigma0, xi0))
            s = post.summary(TARGET_FUNC[et], 0.9)
            g0 = float(tm.functional(TARGET_FUNC[et], np.array([sigma0, xi0])))
            rows.append(
                {
                    "nu": nu,
                    "n0": n0,
                    "rep": rep,
                    "policy": policy,
                    "policy_target": target or "-",
                    "eval_target": et,
                    "regret": reg,
                    "cover": float(s["lo"] <= g0 <= s["hi"]),
                    "width_rel": (s["hi"] - s["lo"]) / g0,
                    "err_xi": abs(m_[1] - xi0),
                    "err_logsd": abs(m_[0]),
                    "kl": kl,
                    "choices": "-".join(c[0] for c in prefix),
                    "n_own": prefix.count("own"),
                    "n_peer": prefix.count("peer"),
                    "n_rv": prefix.count("rv"),
                }
            )
    for r in rows:
        r.update(
            {
                "t_fit": timing["fit"],
                "t_prepost": timing["prepost"],
                "t_local": timing["local"],
                "t_total": time.time() - t_start,
            }
        )
    return rows


def main() -> None:
    t0 = time.time()
    print("=== E5 Decision-targeted observation allocation ===")
    print(f"  units per batch: {UNITS}")
    for d in CFG["paths"].values():
        d.mkdir(parents=True, exist_ok=True)
    ss = np.random.SeedSequence(SEED)
    conds = [(nu, n0) for nu in E5["nu_grid"] for n0 in E5["n0_grid"]]
    seeds = ss.spawn(len(conds) * E5["reps"])
    tasks = []
    k = 0
    for nu, n0 in conds:
        for rep in range(E5["reps"]):
            tasks.append((nu, n0, rep, seeds[k]))
            k += 1
    print(f"  [STAGE] {len(tasks):,} replicate tasks")
    rows = []
    with Pool(int(os.environ.get("DID_WORKERS", os.cpu_count() or 1))) as pool:
        for i, res in enumerate(pool.imap_unordered(run_one, tasks, chunksize=2)):
            rows.extend(res)
            if (i + 1) % 40 == 0:
                print(f"  done {i + 1:,}/{len(tasks):,} ({time.time() - t0:.0f}s)")
    df = pd.DataFrame(rows)
    out = CFG["paths"]["results"] / "e5_allocation.csv"
    df.to_csv(out, index=False)
    print(f"RESULT_PATHS: {out}")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
