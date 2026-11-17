"""Failure-triggered adaptive goal-oriented sequential design (and its baselines).

A design model exposes a grid (node) posterior and the operations below; the engine runs a
multi-stage allocation: at each stage the posterior is refit on all data acquired so far and
the next batch source is chosen by a policy.

Policies (equal data budget):
  uniform       round-robin over sources
  dopt          Bayesian D-optimal (Laplace / Gaussian-linear): log det gain
  copt          Bayesian c-optimal for the target functional (Laplace / Gaussian-linear):
                reduction of grad(g)^T Sigma grad(g)   <- core goal-oriented baseline
  copt_global   preposterior expected reduction of the exact posterior variance of g
                (goal-oriented Bayesian design with exact posterior updates)
  evsi_global   decision-theoretic Bayesian design: expected value of sample information of the
                target decision (expected reduction of posterior expected regret / EVPI)
  adapt         proposed: copt by default; evsi_global only when a cheap failure-risk indicator
                fires: kappa = |log Var_exact(g) / Var_delta(g)| > tau_k  or  relative margin
                between the two best copt scores < tau_m
  adapt_cal     same with thresholds calibrated on separate calibration seeds

Loss-mixture representation used for VaR targets: for node k the one-period loss is a finite
mixture  L = sum_j cw[k,j] * scale[k,j] * Z  with Z ~ kernel (normal or standard t_nu).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from scipy import special, stats

from . import tmodel as tm


# ----------------------------------------------------------------------------------------
# loss-mixture utilities
# ----------------------------------------------------------------------------------------
@dataclass
class LossMix:
    """Per-node loss mixture: scales (N, J), component weights (N, J), kernel df (N,) or None."""

    scales: np.ndarray
    cw: np.ndarray
    df: np.ndarray | None = None  # None = normal kernel; else Student-t df per node

    def subset(self, idx) -> LossMix:
        """Rows `idx`."""
        return LossMix(self.scales[idx], self.cw[idx], None if self.df is None else self.df[idx])


def _cdf(c, df):
    return special.ndtr(c) if df is None else special.stdtr(df, c)


def _upper(c, df):
    """E[(Z - c)^+] for the kernel."""
    if df is None:
        return stats.norm.pdf(c) - c * special.ndtr(-c)
    return tm._upper_partial(c, df)


def node_cdf(lm: LossMix, v) -> np.ndarray:
    """P(L <= v) per node; v scalar or (N,)."""
    v = np.asarray(v, float)
    vv = v[:, None] if v.ndim == 1 else v
    df = None if lm.df is None else lm.df[:, None]
    return np.sum(lm.cw * _cdf(vv / lm.scales, df), axis=1)


def node_var(lm: LossMix, alpha: float) -> np.ndarray:
    """VaR per node by vectorized bisection."""
    n = lm.scales.shape[0]
    lo = np.zeros(n)
    hi = np.max(lm.scales, axis=1) * (60.0 if lm.df is not None else 12.0)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        below = node_cdf(lm, mid) < alpha
        lo = np.where(below, mid, lo)
        hi = np.where(below, hi, mid)
    return 0.5 * (lo + hi)


def mix_var(lm: LossMix, w: np.ndarray, alpha: float) -> float:
    """VaR of the posterior predictive sum_k w_k L_k by bisection."""
    lo, hi = 0.0, float(np.max(lm.scales)) * (60.0 if lm.df is not None else 12.0)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if np.sum(w * node_cdf(lm, mid)) < alpha:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def node_pinball(lm: LossMix, v, alpha: float) -> np.ndarray:
    """Expected quantile score of report v under each node (losses have mean 0)."""
    v = np.asarray(v, float)
    vv = v[:, None] if v.ndim == 1 else v
    df = None if lm.df is None else lm.df[:, None]
    up = np.sum(lm.cw * lm.scales * _upper(vv / lm.scales, df), axis=1)
    return up + (1 - alpha) * np.asarray(v, float)


def pinball_regret_nodes(lm: LossMix, v, alpha: float, gk: np.ndarray | None = None):
    """Regret of report v under each node (gk = node VaRs, computed if not given)."""
    if gk is None:
        gk = node_var(lm, alpha)
    return node_pinball(lm, v, alpha) - node_pinball(lm, gk, alpha)


# ----------------------------------------------------------------------------------------
# posterior container
# ----------------------------------------------------------------------------------------
@dataclass
class NodePost:
    """Grid posterior: nodes phi (N, d), log weights lw (incl. cell area), model caches."""

    phi: np.ndarray
    lw: np.ndarray
    cache: dict = field(default_factory=dict)

    @property
    def w(self) -> np.ndarray:
        """Normalized weights."""
        x = np.exp(self.lw - np.max(self.lw))
        return x / x.sum()

    def moments(self) -> tuple[np.ndarray, np.ndarray]:
        """Posterior mean and covariance of phi."""
        w = self.w
        m = w @ self.phi
        d = self.phi - m
        return m, (d * w[:, None]).T @ d


def normalize(lw: np.ndarray) -> np.ndarray:
    """Weights from log weights."""
    x = np.exp(lw - np.max(lw))
    return x / x.sum()


# ----------------------------------------------------------------------------------------
# target evaluation shared by models
# ----------------------------------------------------------------------------------------
def target_eval(model, target: str, post: NodePost, w: np.ndarray, state) -> dict:
    """Bayes act, EVPI and node functional values for a target under weights w."""
    keep = w > 1e-10 * w.max()
    idx = np.flatnonzero(keep)
    ww = w[idx] / w[idx].sum()
    kind, alpha = model.targets[target]
    if kind == "var":
        lm = model.lossmix(post, state).subset(idx)
        gk = node_var(lm, alpha)
        act = mix_var(lm, ww, alpha)
        reg = pinball_regret_nodes(lm, act, alpha, gk)
        return {"act": act, "evpi": float(ww @ reg), "g": gk, "w": ww, "idx": idx}
    if kind == "qlike":
        gk = model.gvals(target, post, state)[idx]
        act = float(ww @ gk)
        r = gk / act - np.log(gk / act) - 1
        return {"act": act, "evpi": float(ww @ r), "g": gk, "w": ww, "idx": idx}
    raise ValueError(kind)


def truth_regret(model, target: str, act: float, state) -> float:
    """Population (out-of-sample) regret of the act under the true DGP."""
    kind, alpha = model.targets[target]
    if kind == "var":
        lm = model.truth_lossmix(state)
        return float(pinball_regret_nodes(lm, np.array([act]), alpha)[0])
    v0 = model.truth_gval(target, state)
    return float(v0 / act - np.log(v0 / act) - 1)


# ----------------------------------------------------------------------------------------
# criteria
# ----------------------------------------------------------------------------------------
def local_criteria(model, target: str, post: NodePost, state, rng) -> dict:
    """Laplace / Gaussian-linear D-opt and c-opt scores per source, and kappa."""
    m, S = post.moments()
    S = S + 1e-12 * np.eye(len(m))
    G = model.grad_g(target, m, post, state)
    A = np.linalg.inv(S)
    out = {"dopt": {}, "copt": {}}
    for src in model.sources:
        Ie = model.local_info(src, m, post, state, rng)
        Snew = np.linalg.inv(A + Ie)
        out["dopt"][src] = float(np.linalg.slogdet(A + Ie)[1] - np.linalg.slogdet(A)[1])
        out["copt"][src] = float(G @ (S - Snew) @ G)
    ev = target_eval(model, target, post, post.w, state)
    gk, ww = ev["g"], ev["w"]
    var_exact = float(ww @ (gk - ww @ gk) ** 2)
    var_delta = float(G @ S @ G)
    out["kappa"] = abs(np.log(max(var_exact, 1e-300) / max(var_delta, 1e-300)))
    sc = sorted(out["copt"].values(), reverse=True)
    out["margin"] = (sc[0] - sc[1]) / max(abs(sc[0]), 1e-300) if len(sc) > 1 else 1.0
    out["evpi_now"] = ev["evpi"]
    out["var_now"] = var_exact
    return out


def global_criteria(model, target: str, post: NodePost, state, rng, n_sims: int) -> dict:
    """Preposterior EVSI and expected exact-variance reduction per source (exact updates)."""
    w = post.w
    ev0 = target_eval(model, target, post, w, state)
    var0 = float(ev0["w"] @ (ev0["g"] - ev0["w"] @ ev0["g"]) ** 2)
    nodes = rng.choice(len(w), size=n_sims, p=w)
    out = {"evsi": {}, "cvar": {}, "updates": 0}
    for src in model.sources:
        evs, vs = [], []
        for k in nodes:
            y = model.simulate(rng, src, k, post, state)
            lw2 = model.update_lw(src, y, post, state)
            w2 = normalize(lw2)
            e2 = target_eval(model, target, post, w2, state)
            evs.append(e2["evpi"])
            vs.append(float(e2["w"] @ (e2["g"] - e2["w"] @ e2["g"]) ** 2))
            out["updates"] += 1
        out["evsi"][src] = ev0["evpi"] - float(np.mean(evs))
        out["cvar"][src] = var0 - float(np.mean(vs))
    return out


# ----------------------------------------------------------------------------------------
# engine
# ----------------------------------------------------------------------------------------
def _state_rng(seed: int, kind: int, state) -> np.random.Generator:
    """RNG determined by (seed, purpose, data state): identical states give identical criteria
    across policies (common random numbers for Monte Carlo local information and preposterior
    simulations)."""
    return np.random.default_rng([int(seed), kind, *[int(v) for v in state["ptr"].values()]])


def source_features(model, post: NodePost, loc: dict, state, stage: int, n_stages: int):
    """Per-source feature matrix (n_sources, F) for learned design policies.

    Common: posterior mean and log sd of phi, kappa, margin, log EVPI, log Var(g), stage.
    Per source: relative c-opt and D-opt scores, batches already bought, one-hot identity.
    """
    m, S = post.moments()
    common = np.concatenate(
        [
            m,
            0.5 * np.log(np.maximum(np.diag(S), 1e-300)),
            [
                loc["kappa"],
                loc["margin"],
                np.log(max(loc["evpi_now"], 1e-300)),
                np.log(max(loc["var_now"], 1e-300)),
                stage / n_stages,
            ],
        ]
    )
    cmax = max(abs(v) for v in loc["copt"].values()) + 1e-300
    dmax = max(abs(v) for v in loc["dopt"].values()) + 1e-300
    rows = []
    for j, src in enumerate(model.sources):
        pool = state["pools"][src]
        bought = (
            state["ptr"][src] if isinstance(pool, list) else state["ptr"][src] / model.units[src]
        )
        onehot = np.zeros(len(model.sources))
        onehot[j] = 1.0
        rows.append(
            np.concatenate(
                [
                    common,
                    [loc["copt"][src] / cmax, loc["dopt"][src] / dmax, bought / n_stages],
                    onehot,
                ]
            )
        )
    return np.array(rows)


def run_policy(
    model,
    policy: str,
    target: str,
    state0,
    rng,
    n_stages: int,
    n_sims: int,
    tau: tuple[float, float] = (0.223, 0.10),
    log_both: bool = False,
    seed: int = 0,
    scorer=None,
) -> dict:
    """Run one multi-stage allocation; returns final regret, costs and per-stage logs."""
    state = model.copy_state(state0)
    t0 = time.process_time()
    n_updates = 0
    n_global = 0
    logs = []
    for stage in range(n_stages):
        post = model.fit(state)
        n_updates += 1
        loc = local_criteria(model, target, post, state, _state_rng(seed, 1, state))
        choice_local = max(model.sources, key=lambda s: loc["copt"][s])
        glob = None
        fire = (loc["kappa"] > tau[0]) or (loc["margin"] < tau[1])
        need_global = (
            policy in ("copt_global", "evsi_global")
            or (policy.startswith("adapt") and fire)
            or log_both
        )
        if need_global:
            glob = global_criteria(model, target, post, state, _state_rng(seed, 2, state), n_sims)
            n_updates += glob["updates"]
            n_global += 1
        if policy == "uniform":
            src = model.sources[stage % len(model.sources)]
        elif policy == "dopt":
            src = max(model.sources, key=lambda s: loc["dopt"][s])
        elif policy == "copt":
            src = choice_local
        elif policy == "copt_global":
            src = max(model.sources, key=lambda s: glob["cvar"][s])
        elif policy == "evsi_global":
            src = max(model.sources, key=lambda s: glob["evsi"][s])
        elif policy.startswith("adapt"):
            src = max(model.sources, key=lambda s: glob["evsi"][s]) if fire else choice_local
        elif policy == "learned":
            pred = scorer(source_features(model, post, loc, state, stage, n_stages))
            src = model.sources[int(np.argmin(pred))]
        else:
            raise ValueError(policy)
        rec = {
            "stage": stage,
            "src": src,
            "kappa": loc["kappa"],
            "margin": loc["margin"],
            "fire": bool(fire),
            "choice_local": choice_local,
        }
        if glob is not None:
            rec["choice_evsi"] = max(model.sources, key=lambda s: glob["evsi"][s])
            rec["choice_cvar"] = max(model.sources, key=lambda s: glob["cvar"][s])
        logs.append(rec)
        state = model.consume(state, src)
    post = model.fit(state)
    n_updates += 1
    ev = target_eval(model, target, post, post.w, state)
    regret = truth_regret(model, target, ev["act"], state)
    return {
        "regret": regret,
        "evpi_final": ev["evpi"],
        "cpu_seconds": time.process_time() - t0,
        "posterior_updates": n_updates,
        "global_stages": n_global,
        "logs": logs,
        "choices": "-".join(r["src"] for r in logs),
    }
