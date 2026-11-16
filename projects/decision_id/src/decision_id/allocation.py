"""Observation allocation among heterogeneous data sources for the Student-t risk model.

Target asset: theta = (log sd, xi), location 0. Sources (cost per unit in config):
  own  : one more daily return of the target asset             -> informs (log sd, xi)
  peer : one unit-variance standardized residual of a peer asset sharing the tail index
                                                                 -> informs xi only
  rv   : one noisy variance proxy RV ~ sd^2 chi2_m / m           -> informs log sd only

Policies: uniform, own_only, dopt (Fisher-only), predictive (log-score, functional-blind),
dr_local (decision-weighted Bayesian c/L-optimality, Gaussian-linear preposterior) and
dr_prepost (decision-weighted preposterior EVSI computed with exact grid updates).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import special

from . import diagnostics as dg
from . import posterior as po
from . import tmodel as tm

SOURCES = ("own", "peer", "rv")


@dataclass
class Data:
    """Accumulated observations from all sources."""

    own: np.ndarray
    peer: np.ndarray = field(default_factory=lambda: np.empty(0))
    rv: np.ndarray = field(default_factory=lambda: np.empty(0))


def extra_loglik_fn(peer: np.ndarray, rv: np.ndarray, m: int):
    """Log-likelihood of peer and rv data on a (log sd, xi) mesh."""

    def f(L, X):
        out = np.zeros_like(L)
        if len(peer):
            xi_ax = X[0, :]
            s = np.sqrt(1 - 2 * xi_ax)
            nu = 1.0 / xi_ax
            ll = tm.logpdf_std(peer[None, :] / s[:, None], nu[:, None]).sum(axis=1) - len(
                peer
            ) * np.log(s)
            out = out + ll[None, :]
        if len(rv):
            k = m / 2
            theta = 2 * np.exp(2 * L[:, 0]) / m
            ll = (
                (k - 1) * np.log(rv).sum()
                - rv.sum() / theta
                - len(rv) * k * np.log(theta)
                - len(rv) * special.gammaln(k)
            )
            out = out + ll[:, None]
        return out

    return f


def fisher_source(src: str, phi: np.ndarray, m: int, xi_max: float) -> np.ndarray:
    """Per-unit Fisher information of a source in (log sd, xi)."""
    I_own = tm.fisher(phi, "logsd_xi", xi_max)
    if src == "own":
        return I_own
    if src == "peer":
        return np.array([[0.0, 0.0], [0.0, I_own[1, 1]]])
    if src == "rv":
        return np.array([[2.0 * m, 0.0], [0.0, 0.0]])
    raise ValueError(src)


def simulate_source(rng, src: str, size: int, sigma: float, xi: float, m: int) -> np.ndarray:
    """Draw `size` units from a source at canonical (sigma, xi)."""
    if src == "own":
        return sigma * rng.standard_t(1.0 / xi, size)
    if src == "peer":
        return rng.standard_t(1.0 / xi, size) * np.sqrt(1 - 2 * xi)
    if src == "rv":
        return tm.variance_(sigma, xi) * rng.chisquare(m, size) / m
    raise ValueError(src)


# ----------------------------------------------------------------------------------------
# targets
# ----------------------------------------------------------------------------------------
TARGETS = {
    "var975": ("var", 0.975),
    "fz975": ("fz", 0.975),
    "var999": ("var", 0.999),
}


def target_act(target: str, canon: np.ndarray, w: np.ndarray):
    """Bayes act (predictive functional) for a target."""
    kind, a = TARGETS[target]
    if kind == "var":
        return tm.predictive_var(canon, w, a)
    return tm.predictive_var(canon, w, a), tm.predictive_es(canon, w, a)


def target_regret(target: str, act, sigma, xi):
    """Expected score regret of an act under (sigma, xi) (vectorized over params)."""
    kind, a = TARGETS[target]
    if kind == "var":
        return tm.pinball_regret(act, a, sigma, xi)
    return tm.fz0_regret(act[0], act[1], a, sigma, xi)


def evpi(target: str, canon: np.ndarray, w: np.ndarray) -> float:
    """Posterior expected regret of the Bayes act (expected value of perfect information)."""
    act = target_act(target, canon, w)
    r = target_regret(target, act, canon[:, 0], canon[:, 1])
    return float(np.sum(w * np.where(np.isfinite(r), r, 0.0)))


def target_grad_curv(target: str, phi: np.ndarray, xi_max: float):
    """Gradient matrix G (2 x k) and score curvature K (k x k) at phi."""
    kind, a = TARGETS[target]
    sigma, xi = tm.canon_from(phi, "logsd_xi", xi_max)
    lv = f"var{str(a)[2:]}"
    gv = tm.grad_functional(lv, phi, "logsd_xi", xi_max)
    if kind == "var":
        return gv[:, None], np.array([[tm.pinball_curvature(a, sigma, xi)]])
    ge = tm.grad_functional(f"es{str(a)[2:]}", phi, "logsd_xi", xi_max)
    return np.column_stack([gv, ge]), tm.fz0_curvature(a, sigma, xi)


# ----------------------------------------------------------------------------------------
# policy criteria
# ----------------------------------------------------------------------------------------
def criteria_local(post: po.Posterior, units: dict, m: int, xi_max: float, target: str | None):
    """Gaussian-linear criteria for each source: D-opt, predictive, decision-weighted."""
    phi_bar, Sig = post.moments("logsd_xi", xi_max)
    phi_bar = phi_bar.copy()
    phi_bar[1] = np.clip(phi_bar[1], 1e-4, xi_max - 1e-4)
    I_pred = fisher_source("own", phi_bar, m, xi_max)
    out = {}
    for src in SOURCES:
        Ie = units[src] * fisher_source(src, phi_bar, m, xi_max)
        row = {"dopt": dg.dopt_value(Sig, Ie), "predictive": dg.predictive_value(Sig, Ie, I_pred)}
        if target is not None:
            G, K = target_grad_curv(target, phi_bar, xi_max)
            row["dr_local"] = dg.value_of_source(Sig, Ie, G, K)
        out[src] = row
    return out


def criterion_prepost(
    rng,
    grid: po.Grid,
    data: Data,
    units: dict,
    m: int,
    xi_max: float,
    target: str,
    n_sims: int,
    prior: po.TPrior,
) -> dict:
    """Preposterior EVSI for each source: EVPI(now) - E[EVPI(after batch)], exact grid updates."""
    w = grid.weights()
    canon = grid.canon(xi_max)
    cc, ww = tm.compress(canon, w, max_pts=1500)
    ev_now = evpi(target, cc, ww)
    L, X = np.meshgrid(grid.logsd, grid.xi, indexing="ij")
    sigma_mesh = np.exp(L) * np.sqrt(1 - 2 * X)
    area = grid.cell_area()
    out = {}
    idx = rng.choice(len(w), size=n_sims, p=w)
    for src in SOURCES:
        evs = []
        for k in range(n_sims):
            s0, x0 = canon[idx[k]]
            y = simulate_source(rng, src, units[src], s0, x0, m)
            if src == "own":
                add = tm.loglik_grid(y, sigma_mesh, X)
            elif src == "peer":
                add = extra_loglik_fn(y, np.empty(0), m)(L, X)
            else:
                add = extra_loglik_fn(np.empty(0), y, m)(L, X)
            lp = grid.logpost + add
            w2 = (np.exp(lp - lp.max()) * area).ravel()
            w2 /= w2.sum()
            c2, ww2 = tm.compress(canon, w2, max_pts=1500)
            evs.append(evpi(target, c2, ww2))
        out[src] = {"dr_prepost": ev_now - float(np.mean(evs)), "evpi_now": ev_now}
    return out


def fit_posterior(
    data: Data, prior: po.TPrior, m: int, n_l: int = 81, n_x: int = 101, xi_min: float = 5e-4
):
    """Two-pass adaptive grid posterior using all sources; returns (Posterior, Grid)."""
    extra = extra_loglik_fn(data.peer, data.rv, m)
    xm = prior.xi_max
    xi_ax = np.linspace(np.sqrt(xi_min), np.sqrt(xm), n_x) ** 2
    c = np.log(np.std(data.own))
    lsd_ax = np.linspace(c - 1.5, c + 1.5, n_l)
    for _ in range(2):
        g = po.grid_from_axes(lsd_ax, xi_ax, data.own, prior, extra)
        w = g.weights().reshape(g.logpost.shape)
        ml, mx_ = w.sum(axis=1), w.sum(axis=0)
        mu_l = ml @ g.logsd
        sd_l = np.sqrt(ml @ (g.logsd - mu_l) ** 2)
        mu_x = mx_ @ g.xi
        sd_x = np.sqrt(mx_ @ (g.xi - mu_x) ** 2)
        sd_l = max(sd_l, 3 * (g.logsd[1] - g.logsd[0]) / 8)
        lsd_ax = np.linspace(mu_l - 8 * sd_l, mu_l + 8 * sd_l, n_l)
        lo = max(xi_min, mu_x - 8 * sd_x)
        hi = min(xm, mu_x + 8 * sd_x)
        xi_ax = np.linspace(lo, hi, n_x)
    g = po.grid_from_axes(lsd_ax, xi_ax, data.own, prior, extra)
    return po.Posterior(g.canon(xm), g.weights(), "grid"), g
