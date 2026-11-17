"""
E8 — Confirmatory test of the GARCH weak-ID / multi-horizon trend, horizon exploration, and
the SV misspecification ablation (exact likelihood)

Pre-registered after E7 (where global EVSI / c-opt = 0.74, p = 0.12, 30 reps):
  primary A : garch/weak/qlike10 with 150 new replications, evsi_global vs copt
  primary B : SV with exact likelihood (observations y = h + N(QM, QV)), evsi_global vs copt
exploratory: horizons 5 and 22 days in the weak GARCH regime.

전제:
  config.yaml (e7, e8), results/e7_thresholds.json
출력:
  results/e8_eval.csv
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from multiprocessing import Pool  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import e7_adaptive as e7  # noqa: E402

from decision_id import adaptive as ad  # noqa: E402
from decision_id import dmodels as dm  # noqa: E402

SEED_CONF = 9400
CFG = e7.CFG
E8 = CFG["e8"]
RES = CFG["paths"]["results"]
FULL = ["uniform", "dopt", "copt", "evsi_global", "adapt_cal"]


def make_model(name: str):
    """'svx' = SV with exact (Gaussian log-square) observations."""
    return dm.SVDesign(exact=True) if name == "svx" else e7.make_model(name)


def task(args):
    """One replicate of one cell with the listed policies (common seeds)."""
    i, tag, (mname, truth, target), policies, tau = args
    seed = int(np.random.SeedSequence([SEED_CONF, i]).generate_state(1)[0])
    model = make_model(mname)
    s0 = model.init_state(np.random.default_rng(seed), truth, stages=e7.E7["stages"])
    rows = []
    for pol in policies:
        out = ad.run_policy(
            model,
            pol,
            target,
            s0,
            None,
            e7.E7["stages"],
            e7.E7["n_sims"],
            tau=tau if pol == "adapt_cal" else tuple(e7.E7["tau_fixed"]),
            seed=seed,
        )
        rows.append(
            {
                "tag": tag,
                "model": mname,
                "truth": truth,
                "target": target,
                "task": i,
                "policy": pol,
                "regret": out["regret"],
                "cpu_seconds": out["cpu_seconds"],
                "global_stages": out["global_stages"],
                "choices": out["choices"],
            }
        )
    return rows


def build_tasks(tau):
    """All E8 tasks with globally unique indices."""
    tasks = []
    cell = tuple(E8["confirm_cell"])
    tasks += [(r, "confirm", cell, FULL, tau) for r in range(E8["confirm_reps"])]
    for k, c in enumerate(E8["horizon_cells"]):
        tasks += [
            (10_000 * (k + 1) + r, "horizon", tuple(c), ["copt", "evsi_global"], tau)
            for r in range(E8["horizon_reps"])
        ]
    for k, c in enumerate(E8["sv_exact_cells"]):
        tasks += [
            (50_000 + 10_000 * k + r, "sv_exact", tuple(c), FULL, tau)
            for r in range(E8["sv_exact_reps"])
        ]
    return tasks


def main() -> None:
    t0 = time.time()
    print("=== E8 confirmation + SV ablation ===")
    th = json.loads((RES / "e7_thresholds.json").read_text())
    tasks = build_tasks((th["tau_kappa"], th["tau_margin"]))
    out = RES / "e8_eval.csv"
    out.unlink(missing_ok=True)
    with Pool(int(os.environ.get("DID_WORKERS", os.cpu_count() or 1))) as pool:
        for j, rows in enumerate(pool.imap_unordered(task, tasks, chunksize=1)):
            pd.DataFrame(rows).to_csv(out, mode="a", header=not out.exists(), index=False)
            if (j + 1) % 20 == 0:
                print(f"  {j + 1}/{len(tasks)} ({time.time() - t0:.0f}s)")
    print(f"RESULT_PATHS: {out}")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
