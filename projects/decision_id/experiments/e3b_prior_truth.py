"""
E3b — Sanity check: truths drawn from the prior (tail index xi0 ~ prior)

E3 uses fixed tail indices, under which approximate posteriors can beat the exact posterior
on regret (prior-truth mismatch). When xi0 is drawn from the prior, the exact Bayes act
minimizes Bayes risk, so no approximation should beat it on average.
The scale is fixed at sd = 1 (the problem is scale-equivariant up to the broad log-sd prior).

전제:
  config.yaml; experiments/e3_student_t_study.py
출력:
  results/e3b_prior_truth.csv
  reports/e3b_prior_truth.md
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import e3_student_t_study as e3  # noqa: E402

SEED = 4242
N_GRID = [100, 250]
REPS = 300
FUNCS = ["var99", "var999", "es975"]


def task(args):
    """Run one E3 replicate with xi0 drawn from the prior; MCMC skipped (rep >= mcmc_reps)."""
    n, rep, seed = args
    rng = np.random.default_rng(seed)
    xi0 = rng.uniform(e3.CFG["student_t"]["xi_min_grid"], e3.CFG["student_t"]["xi_max"])
    rows = e3.run_one((n, 1.0 / xi0, 10_000 + rep, seed.spawn(1)[0]))
    for r in rows:
        r["xi0"] = xi0
    return [r for r in rows if r["functional"] in FUNCS and r["method"] != "__diag__"]


def boot(a, b, rng, B=2000):
    """Paired bootstrap ratio of means with 90% interval."""
    idx = rng.integers(0, len(a), (B, len(a)))
    r = a[idx].mean(1) / b[idx].mean(1)
    return a.mean() / b.mean(), np.quantile(r, 0.05), np.quantile(r, 0.95)


def main() -> None:
    t0 = time.time()
    print("=== E3b truths from the prior ===")
    cfg = e3.CFG
    ss = np.random.SeedSequence(SEED)
    seeds = ss.spawn(len(N_GRID) * REPS)
    tasks = [(n, r, seeds[i * REPS + r]) for i, n in enumerate(N_GRID) for r in range(REPS)]
    rows = []
    with Pool(int(os.environ.get("DID_WORKERS", os.cpu_count() or 1))) as pool:
        for res in pool.imap_unordered(task, tasks, chunksize=4):
            rows.extend(res)
    df = pd.DataFrame(rows)
    out_csv = cfg["paths"]["results"] / "e3b_prior_truth.csv"
    df.to_csv(out_csv, index=False)
    rng = np.random.default_rng(SEED)
    out = []
    for (n, f), s in df.groupby(["n", "functional"]):
        piv = s.pivot_table(index="rep", columns="method", values="regret")
        cov = s.groupby("method")["cover"].mean()
        for m in [c for c in piv.columns if c != "grid"]:
            r, lo, hi = boot(piv[m].values, piv["grid"].values, rng)
            out.append(
                {
                    "n": n,
                    "functional": f,
                    "method": m,
                    "regret_ratio_vs_exact": r,
                    "lo90": lo,
                    "hi90": hi,
                    "coverage": cov[m],
                    "coverage_exact": cov["grid"],
                }
            )
    tab = pd.DataFrame(out)
    md = [
        "# E3b — Truths drawn from the prior (sanity check)",
        "",
        f"xi0 ~ U(xi_min, xi_max), sd = 1; {REPS} replications per n. Ratio > 1 means the "
        "approximation has higher mean regret than the exact Bayes act.",
        "",
        tab.to_markdown(index=False, floatfmt=".4f"),
    ]
    out_md = cfg["paths"]["reports"] / "e3b_prior_truth.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(tab.to_string(index=False))
    print(f"RESULT_PATHS: {out_csv}, {out_md}")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
