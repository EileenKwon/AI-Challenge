"""
E9 — Regret-trained neural design policy (amortized, simulation-based)

A small MLP scores each candidate data source from posterior-state features. It is trained on
one-step TRUE regrets simulated from truths drawn from a broad prior: for each visited state
and each source, the batch is acquired, the posterior refit and the Bayes act scored under the
true DGP. Labels are log(regret + delta), centered within each state. Online, the policy picks
the source with the lowest predicted score. Its cost is that of the local c-opt features. It
needs no preposterior simulation, and it learns from the true DGP rather than from the working
likelihood (relevant for the QML stochastic-volatility model).

Usage: python e9_learned.py gen | train | eval

전제:
  config.yaml (e7, e8, e9); results/e7_eval.csv and results/e8_eval.csv for pairing (eval)
출력:
  results/e9_train.csv, results/e9_net_<model>_<target>.npz, results/e9_train_report.json,
  results/e9_eval.csv
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
import e8_confirm as e8  # noqa: E402

from decision_id import adaptive as ad  # noqa: E402
from decision_id import nnet  # noqa: E402

SEED_GEN = 9500
CFG = e7.CFG
E9 = CFG["e9"]
RES = CFG["paths"]["results"]
TARGETS = {"garch": ["qlike10", "var99"], "sv": ["var99"]}
STAGES = e7.E7["stages"]


def sample_truth(mname: str, rng) -> tuple:
    """Training truth from a broad prior (contains, but is not centered on, the E7 truths)."""
    if mname == "garch":
        g = E9["garch_truth"]
        a = rng.uniform(*g["alpha"])
        b = rng.uniform(g["beta_lo"], g["persist_max"] - a)
        return (1.0, a, b)
    s = E9["sv_truth"]
    return (0.0, rng.uniform(*s["phi"]), float(np.exp(rng.uniform(*s["log_sigma_eta"]))))


def gen_traj(args):
    """One training trajectory with a random behaviour policy; labels for every source."""
    mname, j = args
    seed = int(
        np.random.SeedSequence([SEED_GEN, {"garch": 1, "sv": 2}[mname], j]).generate_state(1)[0]
    )
    rng = np.random.default_rng(seed)
    model = e7.make_model(mname)
    truth = sample_truth(mname, rng)
    s = model.init_state(rng, truth, stages=STAGES)
    post = model.fit(s)
    rows = []
    for stage in range(STAGES):
        feats = {}
        for tg in TARGETS[mname]:
            loc = ad.local_criteria(model, tg, post, s, ad._state_rng(seed, 1, s))
            feats[tg] = ad.source_features(model, post, loc, s, stage, STAGES)
        nxt = {}
        for e_idx, src in enumerate(model.sources):
            s_e = model.consume(s, src)
            p_e = model.fit(s_e)
            nxt[src] = (s_e, p_e)
            for tg in TARGETS[mname]:
                ev = ad.target_eval(model, tg, p_e, p_e.w, s_e)
                reg = ad.truth_regret(model, tg, ev["act"], s_e)
                rows.append(
                    {
                        "model": mname,
                        "target": tg,
                        "traj": j,
                        "stage": stage,
                        "src": e_idx,
                        "regret": reg,
                        **{f"f{k}": v for k, v in enumerate(feats[tg][e_idx])},
                    }
                )
        s, post = nxt[model.sources[rng.integers(len(model.sources))]]
    return rows


def cmd_gen() -> None:
    t0 = time.time()
    tasks = [(m, j) for m in ("garch", "sv") for j in range(E9["n_traj"])]
    out = RES / "e9_train.csv"
    out.unlink(missing_ok=True)
    with Pool(int(os.environ.get("DID_WORKERS", os.cpu_count() or 1))) as pool:
        for k, rows in enumerate(pool.imap_unordered(gen_traj, tasks, chunksize=1)):
            pd.DataFrame(rows).to_csv(out, mode="a", header=not out.exists(), index=False)
            if (k + 1) % 50 == 0:
                print(f"  gen {k + 1}/{len(tasks)} ({time.time() - t0:.0f}s)")


def _labels(d: pd.DataFrame, delta: float) -> np.ndarray:
    y = np.log(d.regret.values + delta)
    grp = d.traj.astype(str) + "_" + d.stage.astype(str)
    return y - pd.Series(y).groupby(grp.values).transform("mean").values


def cmd_train() -> None:
    df = pd.read_csv(RES / "e9_train.csv")
    fcols = [c for c in df.columns if c.startswith("f")]
    report = {}
    rng = np.random.default_rng(SEED_GEN)
    for (mname, tg), d in df.groupby(["model", "target"]):
        d = d.sort_values(["traj", "stage", "src"]).reset_index(drop=True)
        delta = E9["label_delta_frac"] * float(np.median(d.regret))
        y = _labels(d, delta)
        trajs = d.traj.unique()
        test_t = set(rng.choice(trajs, size=int(0.2 * len(trajs)), replace=False))
        te = d.traj.isin(test_t).values
        net = nnet.MLPRegressor(len(fcols), hidden=E9["hidden"], seed=1)
        info = net.fit(
            d.loc[~te, fcols].values, y[~te], groups=d.loc[~te, "traj"].values, epochs=400, seed=2
        )
        # held-out decision quality: realized one-step regret of the chosen source
        dt = d[te].copy()
        dt["pred"] = net.predict(dt[fcols].values)
        n_src = int(d.src.max()) + 1
        copt_col = f"f{len(fcols) - n_src - 3}"  # relative c-opt score column
        stats_ = {"net": [], "copt": [], "best": [], "random": []}
        for _, g in dt.groupby(["traj", "stage"]):
            r = g.regret.values
            stats_["net"].append(r[np.argmin(g.pred.values)])
            stats_["copt"].append(r[np.argmax(g[copt_col].values)])
            stats_["best"].append(r.min())
            stats_["random"].append(r.mean())
        rep = {k: float(np.mean(v)) for k, v in stats_.items()}
        rep.update(
            {
                "val_mse": info["val_mse"],
                "val_var": info["val_var"],
                "epochs": info["epochs"],
                "delta": delta,
                "n_rows": int(len(d)),
                "test_states": int(len(stats_["net"])),
            }
        )
        report[f"{mname}/{tg}"] = rep
        np.savez(
            RES / f"e9_net_{mname}_{tg}.npz",
            mu=net.mu,
            sd=net.sd,
            **{k: v for k, v in net.p.items()},
        )
        print(mname, tg, rep)
    (RES / "e9_train_report.json").write_text(json.dumps(report, indent=2))


_NETS: dict = {}


def _scorer(mname: str, tg: str):
    key = (mname, tg)
    if key not in _NETS:
        z = np.load(RES / f"e9_net_{mname}_{tg}.npz")
        net = nnet.MLPRegressor(len(z["mu"]), hidden=E9["hidden"])
        net.mu, net.sd = z["mu"], z["sd"]
        net.p = {k: z[k] for k in ("W1", "b1", "W2", "b2", "W3", "b3")}
        _NETS[key] = net
    return _NETS[key].predict


def eval_task(args):
    """Run the learned policy on a seed shared with E7 or E8 (paired comparison)."""
    source, i, seed, (mname, truth, target) = args
    model = e8.make_model(mname)
    s0 = model.init_state(np.random.default_rng(seed), truth, stages=STAGES)
    out = ad.run_policy(
        model,
        "learned",
        target,
        s0,
        None,
        STAGES,
        e7.E7["n_sims"],
        seed=seed,
        scorer=_scorer(mname, target),
    )
    return {
        "source": source,
        "model": mname,
        "truth": truth,
        "target": target,
        "task": i,
        "policy": "learned",
        "regret": out["regret"],
        "cpu_seconds": out["cpu_seconds"],
        "choices": out["choices"],
    }


def cmd_eval() -> None:
    t0 = time.time()
    tasks = []
    for k, c in enumerate(tuple(x) for x in e7.E7["cells"]):
        if c[0] in TARGETS and c[2] in TARGETS[c[0]]:
            for r in range(e7.E7["reps_eval"]):
                i = k * 1000 + r
                tasks.append(("e7", i, e7._task_seed(e7.SEED_EVAL, i), c))
    cell = tuple(CFG["e8"]["confirm_cell"])
    for r in range(CFG["e8"]["confirm_reps"]):
        seed = int(np.random.SeedSequence([e8.SEED_CONF, r]).generate_state(1)[0])
        tasks.append(("e8", r, seed, cell))
    with Pool(int(os.environ.get("DID_WORKERS", os.cpu_count() or 1))) as pool:
        rows = list(pool.imap_unordered(eval_task, tasks, chunksize=2))
    pd.DataFrame(rows).to_csv(RES / "e9_eval.csv", index=False)
    print(f"  eval {len(rows)} runs ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "eval"
    t0 = time.time()
    print(f"=== E9 learned policy: {cmd} ===")
    {"gen": cmd_gen, "train": cmd_train, "eval": cmd_eval}[cmd]()
    print(f"[DONE] {time.time() - t0:.1f}s")
