"""
E7 — Failure-triggered adaptive goal-oriented design vs Bayesian c-optimal and global designs

Equal-budget multi-stage allocation in four models (Student-t control, calm/crisis mixture,
GARCH(1,1)-t6, stochastic volatility). Policies: uniform, D-optimal, Bayesian c-optimal
(local), global goal-oriented c-optimal (exact preposterior variance), global decision-
theoretic Bayesian design (EVSI), and the failure-triggered adaptive design with a
pre-specified threshold and with a threshold calibrated on separate calibration seeds.

Usage: python e7_adaptive.py calibrate | evaluate

전제:
  config.yaml (e7 section)
출력:
  results/e7_cal_logs.csv, results/e7_thresholds.json      (calibrate)
  results/e7_eval.csv, results/e7_eval_logs.csv            (evaluate)
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_id import adaptive as ad  # noqa: E402
from decision_id import dmodels as dm  # noqa: E402
from decision_id.utils import load_config  # noqa: E402

SEED_CAL, SEED_EVAL = 9100, 9200
CFG = load_config()
E7 = CFG["e7"]
RES = CFG["paths"]["results"]
POLICIES = ["uniform", "dopt", "copt", "copt_global", "evsi_global", "adapt", "adapt_cal"]
TAU_K_GRID = [0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, np.inf]
TAU_M_GRID = [0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5]


def make_model(name: str):
    """Instantiate a design model."""
    return {
        "t": lambda: dm.TDesign(CFG),
        "mix": dm.MixDesign,
        "garch": dm.GarchDesign,
        "sv": dm.SVDesign,
    }[name]()


def _task_seed(base: int, i: int) -> int:
    return int(np.random.SeedSequence([base, i]).generate_state(1)[0])


def cal_task(args):
    """One calibration replicate: always-global EVSI run with local choices logged."""
    i, (mname, truth, target) = args
    seed = _task_seed(SEED_CAL, i)
    model = make_model(mname)
    s0 = model.init_state(np.random.default_rng(seed), truth, stages=E7["stages"])
    out = ad.run_policy(
        model, "evsi_global", target, s0, None, E7["stages"], E7["n_sims"], log_both=True, seed=seed
    )
    return [{"model": mname, "truth": truth, "target": target, "task": i, **r} for r in out["logs"]]


def eval_task(args):
    """One evaluation replicate: all policies on common data pools and common seeds."""
    i, (mname, truth, target), tau_cal = args
    seed = _task_seed(SEED_EVAL, i)
    model = make_model(mname)
    s0 = model.init_state(np.random.default_rng(seed), truth, stages=E7["stages"])
    rows, logs = [], []
    for pol in POLICIES:
        tau = tuple(E7["tau_fixed"]) if pol != "adapt_cal" else tau_cal
        out = ad.run_policy(
            model, pol, target, s0, None, E7["stages"], E7["n_sims"], tau=tau, seed=seed
        )
        rows.append(
            {
                "model": mname,
                "truth": truth,
                "target": target,
                "task": i,
                "policy": pol,
                "regret": out["regret"],
                "evpi_final": out["evpi_final"],
                "cpu_seconds": out["cpu_seconds"],
                "posterior_updates": out["posterior_updates"],
                "global_stages": out["global_stages"],
                "choices": out["choices"],
            }
        )
        if pol in ("evsi_global", "adapt", "adapt_cal"):
            logs += [
                {"model": mname, "truth": truth, "target": target, "task": i, "policy": pol, **r}
                for r in out["logs"]
            ]
    return rows, logs


def calibrate_thresholds(logs: pd.DataFrame) -> dict:
    """Smallest firing rate with recall >= cal_recall of local/global disagreements (pooled)."""
    d = (logs.choice_local != logs.choice_evsi).values
    best = None
    for tk in TAU_K_GRID:
        for tm_ in TAU_M_GRID:
            fire = (logs.kappa.values > tk) | (logs.margin.values < tm_)
            recall = fire[d].mean() if d.any() else 1.0
            rate = fire.mean()
            key = (recall < E7["cal_recall"], rate, -recall)
            if best is None or key < best[0]:
                best = (key, tk, tm_, recall, rate)
    _, tk, tm_, recall, rate = best
    return {
        "tau_kappa": float(tk) if np.isfinite(tk) else 1e9,
        "tau_margin": float(tm_),
        "cal_recall": float(recall),
        "cal_fire_rate": float(rate),
        "n_stages": int(len(logs)),
        "n_disagree": int(d.sum()),
    }


def main() -> None:
    phase = sys.argv[1] if len(sys.argv) > 1 else "evaluate"
    t0 = time.time()
    print(f"=== E7 adaptive design: {phase} ===")
    cells = [tuple(c) for c in E7["cells"]]
    workers = int(os.environ.get("DID_WORKERS", os.cpu_count() or 1))
    if phase == "calibrate":
        tasks = [(k * 1000 + r, c) for k, c in enumerate(cells) for r in range(E7["reps_cal"])]
        rows = []
        with Pool(workers) as pool:
            for j, res in enumerate(pool.imap_unordered(cal_task, tasks, chunksize=1)):
                rows.extend(res)
                if (j + 1) % 20 == 0:
                    print(f"  cal {j + 1}/{len(tasks)} ({time.time() - t0:.0f}s)")
        logs = pd.DataFrame(rows)
        logs.to_csv(RES / "e7_cal_logs.csv", index=False)
        th = calibrate_thresholds(logs)
        (RES / "e7_thresholds.json").write_text(json.dumps(th, indent=2))
        print(th)
    else:
        thf = RES / "e7_thresholds.json"
        if not thf.exists():
            print("[ERR] run `calibrate` first (results/e7_thresholds.json missing)")
            sys.exit(1)
        th = json.loads(thf.read_text())
        tau_cal = (th["tau_kappa"], th["tau_margin"])
        order = {"t": 0, "mix": 1, "garch": 2, "sv": 3}
        tasks = sorted(
            [
                (k * 1000 + r, c, tau_cal)
                for k, c in enumerate(cells)
                for r in range(E7["reps_eval"])
            ],
            key=lambda x: order[x[1][0]],
        )
        out_rows, out_logs = RES / "e7_eval.csv", RES / "e7_eval_logs.csv"
        for f in (out_rows, out_logs):
            f.unlink(missing_ok=True)
        with Pool(workers) as pool:
            for j, (rows, logs) in enumerate(pool.imap_unordered(eval_task, tasks, chunksize=1)):
                pd.DataFrame(rows).to_csv(
                    out_rows, mode="a", header=not out_rows.exists(), index=False
                )
                pd.DataFrame(logs).to_csv(
                    out_logs, mode="a", header=not out_logs.exists(), index=False
                )
                if (j + 1) % 10 == 0:
                    print(f"  eval {j + 1}/{len(tasks)} ({time.time() - t0:.0f}s)")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
