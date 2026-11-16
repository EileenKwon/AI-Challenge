"""Posterior approximations for the 2-parameter Student-t model.

All approximations return a `Posterior` = weighted support points in canonical (sigma, xi).
  grid      : exact (up to quadrature) posterior on an adaptive (log sd, xi) grid
  laplace   : Gaussian at the MAP in a chosen parameterization, pushed forward by sampling
  vi        : Gaussian variational family (mean-field or full-rank) in unconstrained u-coords
  mcmc      : adaptive random-walk Metropolis in u-coords
  mle       : point mass at the (constrained) maximum likelihood estimate
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from scipy import optimize, special, stats
from scipy.interpolate import RegularGridInterpolator

from . import tmodel as tm
from .utils import num_hess, weighted_mean_var, weighted_quantile


@dataclass
class Posterior:
    """Weighted support points in canonical coordinates (sigma, xi)."""

    canon: np.ndarray
    w: np.ndarray
    method: str
    seconds: float = 0.0
    info: dict = field(default_factory=dict)

    def functional_samples(self, name: str) -> np.ndarray:
        """Functional values at the support points."""
        return tm.functional(name, self.canon)

    def summary(self, name: str, level: float = 0.9) -> dict:
        """Posterior mean, sd, and equal-tailed credible interval of a functional."""
        g = self.functional_samples(name)
        ok = np.isfinite(g)
        m, v = weighted_mean_var(g[ok], self.w[ok])
        lo, hi = weighted_quantile(g[ok], self.w[ok], [(1 - level) / 2, (1 + level) / 2])
        return {"mean": m, "sd": float(np.sqrt(v)), "lo": float(lo), "hi": float(hi)}

    def moments(self, kind: str = "logsd_xi", xi_max: float = 0.45):
        """Mean and covariance in parameterization `kind`."""
        phi = tm.phi_from(self.canon, kind, xi_max)
        w = self.w / self.w.sum()
        m = w @ phi
        d = phi - m
        return m, (d * w[:, None]).T @ d


# ----------------------------------------------------------------------------------------
# prior
# ----------------------------------------------------------------------------------------
@dataclass
class TPrior:
    """log sd ~ N(m, s^2); xi ~ Uniform(0, xi_max) or HalfNormal(xi_hn) truncated."""

    logsd_mean: float = 0.0
    logsd_sd: float = 1.0
    xi_max: float = 0.45
    xi_hn: float | None = None

    def logpdf_logsd_xi(self, logsd, xi):
        """Log prior density in (log sd, xi) coordinates (Jacobian to (log sigma, xi) is 1)."""
        lp = stats.norm.logpdf(logsd, self.logsd_mean, self.logsd_sd)
        inside = (xi > 0) & (xi <= self.xi_max)
        if self.xi_hn is None:
            lx = np.where(inside, -np.log(self.xi_max), -np.inf)
        else:
            lx = np.where(inside, -0.5 * (xi / self.xi_hn) ** 2, -np.inf)
        return lp + lx

    def precision_logsd_xi(self) -> np.ndarray:
        """Moment-matched prior precision matrix in (log sd, xi) coords (reference metric)."""
        if self.xi_hn is None:
            vx = self.xi_max**2 / 12
        else:
            xs = np.linspace(0, self.xi_max, 2001)
            p = np.exp(-0.5 * (xs / self.xi_hn) ** 2)
            p /= p.sum()
            vx = float(p @ xs**2 - (p @ xs) ** 2)
        return np.diag([1 / self.logsd_sd**2, 1 / vx])


def prior_from_cfg(cfg: dict, alt: bool = False) -> TPrior:
    """Build the default or alternative prior from configuration."""
    st = cfg["student_t"]
    if not alt:
        p = st["prior"]
        return TPrior(p["logsd_mean"], p["logsd_sd"], st["xi_max"], None)
    p = st["alt_prior"]
    return TPrior(p["logsd_mean"], p["logsd_sd"], st["xi_max"], p["xi_halfnormal_sd"])


def log_post_u(u, x, prior: TPrior) -> float:
    """Unnormalized log posterior density in unconstrained u = (log sd, logit(xi/xi_max))."""
    u = np.atleast_2d(u)
    canon = tm.canon_from(u, "u", prior.xi_max)
    sigma, xi = canon[:, 0], canon[:, 1]
    ll = tm.loglik_grid(x, sigma, xi)
    s = special.expit(u[:, 1])
    log_jac = np.log(prior.xi_max) + np.log(s) + np.log1p(-s)
    out = ll + prior.logpdf_logsd_xi(u[:, 0], xi) + log_jac
    return out if out.size > 1 else float(out[0])


def log_post_natural(phi, x, prior: TPrior) -> float:
    """Unnormalized log posterior in (log sd, xi) coordinates (-inf outside the support)."""
    phi = np.atleast_2d(phi)
    xi = phi[:, 1]
    ok = (xi > 0) & (xi <= prior.xi_max)
    out = np.full(phi.shape[0], -np.inf)
    if ok.any():
        canon = tm.canon_from(phi[ok], "logsd_xi", prior.xi_max)
        out[ok] = tm.loglik_grid(x, canon[:, 0], canon[:, 1]) + prior.logpdf_logsd_xi(
            phi[ok, 0], xi[ok]
        )
    return out if out.size > 1 else float(out[0])


# ----------------------------------------------------------------------------------------
# grid (reference) posterior
# ----------------------------------------------------------------------------------------
@dataclass
class Grid:
    """Rectangular grid in (log sd, xi) with log-posterior values."""

    logsd: np.ndarray
    xi: np.ndarray
    logpost: np.ndarray  # shape (n_logsd, n_xi)

    def cell_area(self) -> np.ndarray:
        """Trapezoid cell areas (the xi axis is non-uniform), shape (n_logsd, n_xi)."""

        def widths(a):
            d = np.diff(a)
            w = np.zeros_like(a)
            w[:-1] += d / 2
            w[1:] += d / 2
            return w

        return np.outer(widths(self.logsd), widths(self.xi))

    def weights(self) -> np.ndarray:
        """Normalized node masses = density x cell area, flattened."""
        lp = self.logpost - np.max(self.logpost)
        w = (np.exp(lp) * self.cell_area()).ravel()
        return w / w.sum()

    def canon(self, xi_max: float = 0.45) -> np.ndarray:
        """Canonical coordinates of all grid nodes, flattened."""
        L, X = np.meshgrid(self.logsd, self.xi, indexing="ij")
        return tm.canon_from(np.stack([L.ravel(), X.ravel()], -1), "logsd_xi", xi_max)


def _xi_axis(cfg_t: dict) -> np.ndarray:
    lo = cfg_t["xi_min_grid"]
    n = cfg_t["grid"]["n_xi"]
    # denser near zero (the Gaussian boundary) via a square-root spacing
    s = np.linspace(np.sqrt(lo), np.sqrt(cfg_t["xi_max"]), n)
    return s**2


def grid_posterior(x: np.ndarray, prior: TPrior, cfg_t: dict, extra_loglik=None) -> tuple:
    """Exact grid posterior; the log sd axis adapts until edge mass is negligible.

    `extra_loglik(logsd_mesh, xi_mesh)` adds log-likelihood terms of other data sources.
    Returns (Posterior, Grid).
    """
    t0 = time.time()
    xi_axis = _xi_axis(cfg_t)
    n = max(len(x), 1)
    center = np.log(np.std(x)) if len(x) > 1 else prior.logsd_mean
    half = cfg_t["grid"]["logsd_halfwidth_se"] * max(0.7 / np.sqrt(n), 0.01)
    for _attempt in range(6):
        logsd = np.linspace(center - half, center + half, cfg_t["grid"]["n_logsd"])
        L, X = np.meshgrid(logsd, xi_axis, indexing="ij")
        sigma = np.exp(L) * np.sqrt(1 - 2 * X)
        lp = tm.loglik_grid(x, sigma, X) if len(x) else np.zeros_like(L)
        lp = lp + prior.logpdf_logsd_xi(L, X)
        if extra_loglik is not None:
            lp = lp + extra_loglik(L, X)
        g = Grid(logsd, xi_axis, lp)
        w = g.weights().reshape(L.shape)
        edge = w[0, :].sum() + w[-1, :].sum()
        if edge < 1e-6:
            break
        marg = w.sum(axis=1)
        center = float(marg @ logsd)
        half *= 1.8
    canon = g.canon(prior.xi_max)
    post = Posterior(canon, g.weights(), "grid", time.time() - t0, {"edge_mass": float(edge)})
    return post, g


def grid_from_axes(logsd, xi_axis, x, prior: TPrior, extra_loglik=None) -> Grid:
    """Grid posterior on fixed axes (used for fast preposterior updates)."""
    L, X = np.meshgrid(logsd, xi_axis, indexing="ij")
    sigma = np.exp(L) * np.sqrt(1 - 2 * X)
    lp = tm.loglik_grid(x, sigma, X) if len(x) else np.zeros_like(L)
    lp = lp + prior.logpdf_logsd_xi(L, X)
    if extra_loglik is not None:
        lp = lp + extra_loglik(L, X)
    return Grid(np.asarray(logsd), np.asarray(xi_axis), lp)


def reweight(post: Posterior, logw_extra: np.ndarray, method: str) -> Posterior:
    """Importance-reweight a grid posterior (e.g., prior swap)."""
    lw = np.log(np.maximum(post.w, 1e-300)) + logw_extra
    lw -= lw.max()
    w = np.exp(lw)
    return Posterior(post.canon, w / w.sum(), method)


# ----------------------------------------------------------------------------------------
# MLE
# ----------------------------------------------------------------------------------------
def mle(x: np.ndarray, xi_max: float = 0.45) -> Posterior:
    """Constrained MLE over (log sd, xi in [1e-6, xi_max]) as a point mass."""
    t0 = time.time()

    def nll(p):
        c = tm.canon_from(p, "logsd_xi", xi_max)
        return -float(tm.loglik_grid(x, np.array([c[0]]), np.array([c[1]]))[0])

    best = None
    for xi0 in (0.02, 0.15, 0.3):
        r = optimize.minimize(
            nll,
            np.array([np.log(np.std(x)), xi0]),
            method="L-BFGS-B",
            bounds=[(None, None), (1e-6, xi_max)],
        )
        if best is None or r.fun < best.fun:
            best = r
    canon = tm.canon_from(best.x, "logsd_xi", xi_max)[None, :]
    on_boundary = bool(best.x[1] < 1e-4 or best.x[1] > xi_max - 1e-4)
    return Posterior(
        canon, np.ones(1), "mle", time.time() - t0, {"phi": best.x, "boundary": on_boundary}
    )


# ----------------------------------------------------------------------------------------
# Laplace
# ----------------------------------------------------------------------------------------
def laplace(
    x: np.ndarray, prior: TPrior, kind: str, rng: np.random.Generator, n_draws: int
) -> Posterior:
    """Laplace approximation in `kind` in {"u", "logsd_xi"}; draws are pushed forward.

    For "logsd_xi" the MAP may sit on the xi = 0 boundary, and Gaussian draws can leave
    the support; such draws are discarded (the fraction is recorded) — a known failure mode.
    """
    t0 = time.time()
    xm = prior.xi_max
    if kind == "u":

        def f(p):
            return -log_post_u(p, x, prior)

        start = np.array([np.log(np.std(x)), special.logit(0.15 / xm)])
        r = optimize.minimize(f, start, method="BFGS")
        mode = r.x
    else:

        def f(p):
            v = log_post_natural(p, x, prior)
            return 1e10 if not np.isfinite(v) else -v

        r = optimize.minimize(
            f,
            np.array([np.log(np.std(x)), 0.15]),
            method="L-BFGS-B",
            bounds=[(None, None), (1e-6, xm)],
        )
        mode = r.x
    H = num_hess(f, mode, rel=1e-4)
    try:
        cov = np.linalg.inv(H)
        np.linalg.cholesky(cov)
    except np.linalg.LinAlgError:
        # Hessian not positive definite (boundary MAP): fall back to diagonal curvature
        cov = np.diag(1.0 / np.maximum(np.abs(np.diag(H)), 1e-8))
    draws = rng.multivariate_normal(mode, cov, size=n_draws)
    if kind == "logsd_xi":
        ok = (draws[:, 1] > 0) & (draws[:, 1] < xm)
        frac_out = 1 - ok.mean()
        draws = (
            draws[ok]
            if ok.sum() > 10
            else np.column_stack([draws[:, 0], np.full(n_draws, mode[1])])
        )
    else:
        frac_out = 0.0
    canon = tm.canon_from(draws, kind if kind == "u" else "logsd_xi", xm)
    return Posterior(
        canon,
        np.ones(len(canon)),
        f"laplace_{kind}",
        time.time() - t0,
        {"mode": mode, "cov": cov, "frac_outside": float(frac_out)},
    )


# ----------------------------------------------------------------------------------------
# Gaussian VI (deterministic quadrature ELBO against the grid log-density)
# ----------------------------------------------------------------------------------------
def vi_gaussian(
    grid: Grid, prior: TPrior, full_rank: bool, rng: np.random.Generator, n_draws: int, n_gh=16
) -> Posterior:
    """Gaussian VI in u-coords maximizing a Gauss-Hermite ELBO.

    The target log density is the exact log posterior interpolated from the reference grid
    (a numerical shortcut: the target is the same posterior up to interpolation error).
    """
    t0 = time.time()
    xm = prior.xi_max
    interp = RegularGridInterpolator(
        (grid.logsd, grid.xi),
        grid.logpost - grid.logpost.max(),
        bounds_error=False,
        fill_value=None,
    )
    gh_x, gh_w = np.polynomial.hermite_e.hermegauss(n_gh)
    gh_w = gh_w / gh_w.sum()
    Z1, Z2 = np.meshgrid(gh_x, gh_x, indexing="ij")
    Z = np.stack([Z1.ravel(), Z2.ravel()], -1)
    W = np.outer(gh_w, gh_w).ravel()

    def logp_u(U):
        s = special.expit(U[:, 1])
        xi = xm * s
        pts = np.column_stack([U[:, 0], np.clip(xi, grid.xi[0], grid.xi[-1])])
        lp = interp(pts)
        # below the smallest grid xi, extrapolate flat in xi (posterior is smooth there)
        return lp + np.log(xm) + np.log(s) + np.log1p(-s)

    def unpack(p):
        m = p[:2]
        if full_rank:
            Lm = np.array([[np.exp(p[2]), 0.0], [p[4], np.exp(p[3])]])
        else:
            Lm = np.diag(np.exp(p[2:4]))
        return m, Lm

    def neg_elbo(p):
        m, Lm = unpack(p)
        U = m + Z @ Lm.T
        return -(W @ logp_u(U) + np.log(np.abs(np.diag(Lm))).sum())

    w = grid.weights().reshape(grid.logpost.shape)
    canon = grid.canon(xm)
    canon[:, 1] = np.clip(canon[:, 1], 1e-9, xm * (1 - 1e-6))
    u_nodes = tm.phi_from(canon, "u", xm)
    wf = w.ravel()
    m0 = wf @ u_nodes
    v0 = wf @ (u_nodes - m0) ** 2
    p0 = np.concatenate([m0, 0.5 * np.log(v0)] + ([np.zeros(1)] if full_rank else []))
    r = optimize.minimize(neg_elbo, p0, method="L-BFGS-B")
    m, Lm = unpack(r.x)
    draws = m + rng.standard_normal((n_draws, 2)) @ Lm.T
    canon_d = tm.canon_from(draws, "u", xm)
    return Posterior(
        canon_d,
        np.ones(n_draws),
        "vi_fr" if full_rank else "vi_mf",
        time.time() - t0,
        {"elbo": -r.fun, "mean_u": m, "chol_u": Lm},
    )


# ----------------------------------------------------------------------------------------
# MCMC
# ----------------------------------------------------------------------------------------
def mcmc_rwm(
    x: np.ndarray, prior: TPrior, rng: np.random.Generator, iters: int, burn: int
) -> Posterior:
    """Adaptive random-walk Metropolis in u-coords (Haario-style covariance adaptation)."""
    t0 = time.time()
    xm = prior.xi_max
    u = np.array([np.log(np.std(x)), special.logit(0.15 / xm)])
    lp = log_post_u(u, x, prior)
    cov = np.diag([0.05**2, 0.5**2])
    chain = np.empty((iters, 2))
    acc = 0
    mean = u.copy()
    C = cov.copy()
    for t in range(iters):
        prop_cov = (2.38**2 / 2) * C + 1e-8 * np.eye(2) if t > 500 else cov
        prop = rng.multivariate_normal(u, prop_cov)
        lpp = log_post_u(prop, x, prior)
        if np.log(rng.uniform()) < lpp - lp:
            u, lp = prop, lpp
            if t >= burn:
                acc += 1
        chain[t] = u
        if t < burn:  # adapt only during burn-in to keep the chain Markov afterwards
            k = t + 1
            delta = u - mean
            mean = mean + delta / k
            C = C + (np.outer(delta, u - mean) - C) / k if k > 1 else C
    kept = chain[burn:]
    canon = tm.canon_from(kept, "u", xm)
    return Posterior(
        canon,
        np.ones(len(kept)),
        "mcmc",
        time.time() - t0,
        {"accept": acc / max(len(kept), 1), "ess_xi": ess(kept[:, 1])},
    )


def ess(chain: np.ndarray) -> float:
    """Effective sample size via initial positive sequence of autocorrelations."""
    x = chain - chain.mean()
    n = len(x)
    if n < 10 or np.var(x) == 0:
        return float(n)
    f = np.fft.rfft(x, 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n] / (np.var(x) * n)
    s = 0.0
    for k in range(1, n - 1, 2):
        pair = ac[k] + ac[k + 1]
        if pair < 0:
            break
        s += pair
    return float(n / (1 + 2 * s))
