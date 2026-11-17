"""
E10 — Pre-registered confirmation of the learned design policy in stochastic volatility

Frozen networks from E9 (no retraining). Fresh seeds (disjoint from E7/E8/E9).
  primary H10 : SV (QML), pooled over truths {regular, weak}, 150 replications each:
                learned / c-opt < 1  (paired t and Wilcoxon, two-sided, alpha = 0.05)
  secondary   : learned / evsi_global on the first 50 replications per truth; uniform / c-opt

Usage: python e10_sv_confirm.py run | analyze

전제:
  results/e9_net_sv_var99.npz (from e9_learned.py train)
출력:
  results/e10_eval.csv
  reports/e10_sv_confirm.md
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

import e7_adaptive as e7  # noqa: E402
import e9_learned as e9  # noqa: E402

from decision_id import adaptive as ad  # noqa: E402
from decision_id import stats as st  # noqa: E402

SEED_C10 = 9600
REPS = 150
GLOBAL_REPS = 50
RES = e7.CFG["paths"]["results"]


def task(args):
    """One replicate: copt, uniform, learned (+ evsi_global for the first GLOBAL_REPS)."""
    i, truth = args
    seed = int(np.random.SeedSequence([SEED_C10, i]).generate_state(1)[0])
    model = e7.make_model("sv")
    s0 = model.init_state(np.random.default_rng(seed), truth, stages=e7.E7["stages"])
    pols = ["copt", "uniform", "learned"] + (["evsi_global"] if i % 1000 < GLOBAL_REPS else [])
    rows = []
    for pol in pols:
        out = ad.run_policy(
            model,
            pol,
            "var99",
            s0,
            None,
            e7.E7["stages"],
            e7.E7["n_sims"],
            seed=seed,
            scorer=e9._scorer("sv", "var99") if pol == "learned" else None,
        )
        rows.append(
            {
                "truth": truth,
                "task": i,
                "policy": pol,
                "regret": out["regret"],
                "cpu_seconds": out["cpu_seconds"],
                "choices": out["choices"],
            }
        )
    return rows


def cmd_run() -> None:
    t0 = time.time()
    tasks = [(k * 1000 + r, tr) for k, tr in enumerate(("regular", "weak")) for r in range(REPS)]
    tasks.sort(key=lambda x: (x[0] % 1000 >= GLOBAL_REPS, x[0]))  # expensive tasks first
    out = RES / "e10_eval.csv"
    out.unlink(missing_ok=True)
    with Pool(int(os.environ.get("DID_WORKERS", os.cpu_count() or 1))) as pool:
        for j, rows in enumerate(pool.imap_unordered(task, tasks, chunksize=1)):
            pd.DataFrame(rows).to_csv(out, mode="a", header=not out.exists(), index=False)
            if (j + 1) % 25 == 0:
                print(f"  {j + 1}/{len(tasks)} ({time.time() - t0:.0f}s)")


def cmd_analyze() -> None:
    rng = np.random.default_rng(42)
    df = pd.read_csv(RES / "e10_eval.csv")
    ref = df[df.policy == "copt"].groupby("truth").regret.mean()
    df["norm"] = df.regret / df.truth.map(ref)
    piv = df.pivot_table(index=["truth", "task"], columns="policy", values="norm")
    raw = df.pivot_table(index=["truth", "task"], columns="policy", values="regret")
    rows = []

    def add(name, a, b, fam):
        idx = rng.integers(0, len(a), (4000, len(a)))
        r = a.values[idx].mean(1) / b.values[idx].mean(1)
        pt = st.paired_tests(a.values, b.values, rng, B=1000)
        rows.append(
            {
                "test": name,
                "family": fam,
                "n": len(a),
                "ratio": a.mean() / b.mean(),
                "median_ratio": float(np.median(a.values) / np.median(b.values)),
                "frac_first_better": float(np.mean(a.values < b.values)),
                "ci_lo": float(np.quantile(r, 0.025)),
                "ci_hi": float(np.quantile(r, 0.975)),
                "p_t": pt["p_t"],
                "p_wilcoxon": pt["p_wilcoxon"],
            }
        )

    add("H10 learned/copt (SV pooled, 300)", piv["learned"], piv["copt"], "primary")
    for tr in ("regular", "weak"):
        add(f"learned/copt ({tr})", raw.loc[tr, "learned"], raw.loc[tr, "copt"], "secondary")
    g = piv.dropna(subset=["evsi_global"])
    add("learned/evsi_global (SV pooled, 100)", g["learned"], g["evsi_global"], "secondary")
    add("copt/evsi_global (SV pooled, 100)", g["copt"], g["evsi_global"], "secondary")
    add("uniform/copt (SV pooled, 300)", piv["uniform"], piv["copt"], "secondary")
    T = pd.DataFrame(rows)
    cpu = df.groupby("policy").cpu_seconds.mean()
    mix = (
        df.assign(
            peer=df.choices.str.count("peer"),
            rv=df.choices.str.count("rv(?!_)"),
            rv_hf=df.choices.str.count("rv_hf"),
        )
        .groupby(["truth", "policy"])[["peer", "rv", "rv_hf"]]
        .mean()
        .reset_index()
    )
    md = [
        "# E10 — Pre-registered confirmation: learned design policy in SV",
        "",
        "Frozen E9 networks, fresh seeds, 150 replications per truth (evsi_global on 50 per "
        "truth).",
        "",
        T.to_markdown(index=False, floatfmt=".4g"),
        "",
        "CPU seconds per run: " + ", ".join(f"{k} {v:.1f}" for k, v in cpu.items()),
        "",
        "Batches bought per source:",
        "",
        mix.to_markdown(index=False, floatfmt=".2f"),
    ]
    out = e7.CFG["paths"]["reports"] / "e10_sv_confirm.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(T.to_string(index=False))
    print(cpu.to_string())
    print(mix.to_string(index=False))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "analyze"
    t0 = time.time()
    print(f"=== E10 SV confirmation: {cmd} ===")
    {"run": cmd_run, "analyze": cmd_analyze}[cmd]()
    print(f"[DONE] {time.time() - t0:.1f}s")
