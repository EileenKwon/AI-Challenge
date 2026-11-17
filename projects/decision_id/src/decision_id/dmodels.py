"""Design models for the adaptive-design engine (`adaptive.py`).

  TDesign       Student-t (regular control): own returns / peer tail data / variance proxies
  MixDesign     calm/crisis mixture with singular loci: own returns / crisis-episode returns /
                regime labels
  GarchDesign   GARCH(1,1) with standardized t6 innovations and variance targeting
                (alpha -> 0 leaves beta unidentified): realized variance (two precisions) /
                peer-asset returns sharing (alpha, beta)
  SVDesign      log-AR(1) stochastic volatility (sigma_eta -> 0 leaves phi unidentified),
                QML Kalman quasi-likelihood: realized variance (two precisions) / peer returns

Every model provides: sources, units, targets, init_state, copy_state, consume, fit,
lossmix, truth_lossmix, (gvals, truth_gval for QLIKE targets), grad_g, local_info,
simulate, update_lw. Posteriors are grid posteriors (`adaptive.NodePost`); preposterior
updates are exact on the grid (for SV: exact for the QML quasi-likelihood).
"""

from __future__ import annotations

import copy

import numpy as np
from scipy import special, stats

from . import allocation as al
from . import mixture as mx
from . import posterior as po
from . import tmodel as tm
from .adaptive import LossMix, NodePost, node_var

GH_X, GH_W = np.polynomial.hermite.hermgauss(12)
GH_W = GH_W / np.sqrt(np.pi)


# ----------------------------------------------------------------------------------------
# shared helpers
# ----------------------------------------------------------------------------------------
def hess_stencil(m: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Points for a central-difference Hessian (1 + 2d + 2d(d-1) points)."""
    d = len(m)
    pts = [m.copy()]
    for i in range(d):
        for s in (1, -1):
            p = m.copy()
            p[i] += s * h[i]
            pts.append(p)
    for i in range(d):
        for j in range(i + 1, d):
            for si, sj in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                p = m.copy()
                p[i] += si * h[i]
                p[j] += sj * h[j]
                pts.append(p)
    return np.array(pts)


def hess_from_vals(f: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Hessian from values on `hess_stencil` points."""
    d = len(h)
    H = np.zeros((d, d))
    f0 = f[0]
    for i in range(d):
        H[i, i] = (f[1 + 2 * i] - 2 * f0 + f[2 + 2 * i]) / h[i] ** 2
    k = 1 + 2 * d
    for i in range(d):
        for j in range(i + 1, d):
            fpp, fpm, fmp, fmm = f[k : k + 4]
            H[i, j] = H[j, i] = (fpp - fpm - fmp + fmm) / (4 * h[i] * h[j])
            k += 4
    return H


def psd(M: np.ndarray) -> np.ndarray:
    """Project a symmetric matrix onto the PSD cone."""
    M = 0.5 * (M + M.T)
    lam, V = np.linalg.eigh(M)
    return (V * np.maximum(lam, 0)) @ V.T


def fd_grad(f, m: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Central-difference gradient of a scalar function."""
    g = np.zeros(len(m))
    for i in range(len(m)):
        e = np.zeros(len(m))
        e[i] = h[i]
        g[i] = (f(m + e) - f(m - e)) / (2 * h[i])
    return g


def var_of_lossmix_point(lm: LossMix, alpha: float) -> float:
    """VaR of a single-node loss mixture."""
    return float(node_var(lm, alpha)[0])


def adaptive_axes(lw_fn, axes0, n_pts, bounds, n_pass=2):
    """Two-pass adaptive rectangular grid: refocus each axis on +-7 posterior sd."""
    axes = [np.asarray(a, float) for a in axes0]
    for _ in range(n_pass):
        mesh = np.meshgrid(*axes, indexing="ij")
        pts = np.stack([m.ravel() for m in mesh], -1)
        lw = lw_fn(pts)
        w = np.exp(lw - np.max(lw[np.isfinite(lw)]))
        w = np.where(np.isfinite(w), w, 0)
        w /= w.sum()
        new = []
        for i, a in enumerate(axes):
            mu = w @ pts[:, i]
            sd = np.sqrt(max(w @ (pts[:, i] - mu) ** 2, 1e-12))
            sd = max(sd, 1.5 * (a[1] - a[0]) / 7)
            lo = max(bounds[i][0], mu - 7 * sd)
            hi = min(bounds[i][1], mu + 7 * sd)
            new.append(np.linspace(lo, hi, n_pts[i]))
        axes = new
    mesh = np.meshgrid(*axes, indexing="ij")
    pts = np.stack([m.ravel() for m in mesh], -1)
    area = np.prod([a[1] - a[0] for a in axes])
    return pts, np.log(area)


class _Base:
    """Common state handling: state = dict(data..., ptr=dict(source -> units consumed))."""

    sources: tuple = ()
    units: dict = {}
    targets: dict = {}

    def copy_state(self, s: dict) -> dict:
        """Shallow-safe copy (arrays are never modified in place)."""
        return {**s, "ptr": dict(s["ptr"]), "data": {k: copy.copy(v) for k, v in s["data"].items()}}

    def _truth(self, truth):
        """Named truth or an explicit parameter tuple (used for training-truth sampling)."""
        return self.truths[truth] if isinstance(truth, str) else truth

    def grad_g(self, target, m, post, state):
        """Gradient of the target functional at a parameter point."""
        return fd_grad(lambda p: self.g_point(target, p, state), m, self.fd_step(m))

    def fd_step(self, m):
        """Finite-difference steps."""
        return np.full(len(m), 1e-4)


# ----------------------------------------------------------------------------------------
# Student-t (regular control)
# ----------------------------------------------------------------------------------------
class TDesign(_Base):
    """phi = (log sd, xi). Sources as in E5."""

    sources = ("own", "peer", "rv")
    units = {"own": 50, "peer": 200, "rv": 100}
    targets = {"var975": ("var", 0.975), "var999": ("var", 0.999)}
    M = 5
    truths = {"nu3": 3.0, "nu6": 6.0}

    def __init__(self, cfg):
        self.prior = po.prior_from_cfg(cfg)
        self.xm = self.prior.xi_max

    def init_state(self, rng, truth: str, n0: int = 200, stages: int = 6) -> dict:
        xi0 = 1 / self._truth(truth)
        s0 = np.sqrt(1 - 2 * xi0)
        pools = {
            s: al.simulate_source(rng, s, self.units[s] * stages, s0, xi0, self.M)
            for s in self.sources
        }
        return {
            "truth": (s0, xi0),
            "pools": pools,
            "ptr": {s: 0 for s in self.sources},
            "data": {"own": tm.sample(rng, n0, s0, xi0), "peer": np.empty(0), "rv": np.empty(0)},
        }

    def consume(self, s, src):
        s = self.copy_state(s)
        k = s["ptr"][src]
        u = self.units[src]
        s["data"][src] = np.concatenate([s["data"][src], s["pools"][src][k : k + u]])
        s["ptr"][src] = k + u
        return s

    def fit(self, s):
        d = s["data"]
        post, grid = al.fit_posterior(al.Data(d["own"], d["peer"], d["rv"]), self.prior, self.M)
        L, X = np.meshgrid(grid.logsd, grid.xi, indexing="ij")
        phi = np.column_stack([L.ravel(), X.ravel()])
        lw = np.log(np.maximum(post.w, 1e-300))
        return NodePost(phi, lw, {"canon": post.canon})

    def lossmix(self, post, s):
        c = post.cache["canon"]
        return LossMix(c[:, :1], np.ones((len(c), 1)), 1 / c[:, 1])

    def truth_lossmix(self, s):
        s0, xi0 = s["truth"]
        return LossMix(np.array([[s0]]), np.ones((1, 1)), np.array([1 / xi0]))

    def g_point(self, target, p, s):
        c = tm.canon_from(p, "logsd_xi", self.xm)
        return float(tm.var_(c[0], np.clip(c[1], 1e-5, self.xm), self.targets[target][1]))

    def fd_step(self, m):
        return np.array([1e-4, min(1e-4, 0.5 * m[1])])

    def local_info(self, src, m, post, s, rng):
        mm = m.copy()
        mm[1] = np.clip(mm[1], 1e-4, self.xm - 1e-4)
        return self.units[src] * al.fisher_source(src, mm, self.M, self.xm)

    def simulate(self, rng, src, k, post, s):
        sig, xi = post.cache["canon"][k]
        return al.simulate_source(rng, src, self.units[src], sig, xi, self.M)

    def update_lw(self, src, y, post, s):
        c = post.cache["canon"]
        sig, xi = c[:, 0], c[:, 1]
        if src == "own":
            inc = tm.loglik_grid(y, sig, xi)
        elif src == "peer":
            sc = np.sqrt(1 - 2 * xi)
            inc = tm.logpdf_std(y[None, :] / sc[:, None], 1 / xi[:, None]).sum(1) - len(y) * np.log(
                sc
            )
        else:
            k = self.M / 2
            theta = 2 * tm.variance_(sig, xi) / self.M
            inc = (
                (k - 1) * np.log(y).sum()
                - y.sum() / theta
                - len(y) * k * np.log(theta)
                - len(y) * special.gammaln(k)
            )
        return post.lw + inc


# ----------------------------------------------------------------------------------------
# calm/crisis mixture with singular loci
# ----------------------------------------------------------------------------------------
class MixDesign(_Base):
    """phi = (logit p, log s2), s1 = 1 known."""

    sources = ("own", "stress", "label")
    units = {"own": 50, "stress": 25, "label": 500}
    targets = {"var99": ("var", 0.99), "var999": ("var", 0.999)}
    truths = {"moderate": (0.04, 3.5), "rare": (0.01, 5.0)}
    LS2MAX = np.log(12.0)

    def init_state(self, rng, truth: str, n0: int = 250, stages: int = 6) -> dict:
        p0, s20 = self._truth(truth)

        def own(n):
            c = rng.uniform(size=n) < p0
            return np.where(c, rng.normal(0, s20, n), rng.normal(0, 1, n))

        pools = {
            "own": own(self.units["own"] * stages),
            "stress": rng.normal(0, s20, self.units["stress"] * stages),
            "label": (rng.uniform(size=self.units["label"] * stages) < p0).astype(float),
        }
        return {
            "truth": (p0, s20),
            "pools": pools,
            "ptr": {s: 0 for s in self.sources},
            "data": {"own": own(n0), "stress": np.empty(0), "label": np.empty(0)},
        }

    def consume(self, s, src):
        s = self.copy_state(s)
        k = s["ptr"][src]
        u = self.units[src]
        s["data"][src] = np.concatenate([s["data"][src], s["pools"][src][k : k + u]])
        s["ptr"][src] = k + u
        return s

    @staticmethod
    def _loglik(src, y, p, s2):
        if len(y) == 0:
            return np.zeros_like(p)
        if src == "own":
            return mx.loglik_nodes(y, p, s2)
        if src == "stress":
            return -len(y) * np.log(s2) - np.sum(y**2) / (2 * s2**2)
        k = y.sum()
        return k * np.log(p) + (len(y) - k) * np.log1p(-p)

    def _lw(self, pts, d):
        p, s2 = special.expit(pts[:, 0]), np.exp(pts[:, 1])
        lp = stats.norm.logpdf(pts[:, 0], -3.0, 1.5)
        lp = np.where((pts[:, 1] >= 0) & (pts[:, 1] <= self.LS2MAX), lp, -np.inf)
        for src in self.sources:
            lp = lp + self._loglik(src, d[src], p, s2)
        return lp

    def fit(self, s):
        d = s["data"]
        pts, la = adaptive_axes(
            lambda q: self._lw(q, d),
            [np.linspace(-9, 1, 61), np.linspace(0, self.LS2MAX, 61)],
            [81, 81],
            [(-12, 3), (0, self.LS2MAX)],
        )
        lw = self._lw(pts, d) + la
        ok = np.isfinite(lw)
        pts, lw = pts[ok], lw[ok]
        return NodePost(pts, lw, {"p": special.expit(pts[:, 0]), "s2": np.exp(pts[:, 1])})

    def lossmix(self, post, s):
        p, s2 = post.cache["p"], post.cache["s2"]
        return LossMix(np.column_stack([np.ones_like(s2), s2]), np.column_stack([1 - p, p]))

    def truth_lossmix(self, s):
        p0, s20 = s["truth"]
        return LossMix(np.array([[1.0, s20]]), np.array([[1 - p0, p0]]))

    def g_point(self, target, q, s):
        p, s2 = special.expit(q[0]), np.exp(q[1])
        return var_of_lossmix_point(
            LossMix(np.array([[1.0, s2]]), np.array([[1 - p, p]])), self.targets[target][1]
        )

    def fd_step(self, m):
        return np.array([1e-3, 1e-3])

    def local_info(self, src, m, post, s, rng):
        p = special.expit(m[0])
        if src == "own":
            return self.units[src] * mx.fisher(np.array([m[0], max(m[1], 1e-3)]))
        if src == "stress":
            return self.units[src] * np.diag([0.0, 2.0])
        return self.units[src] * np.diag([p * (1 - p), 0.0])

    def simulate(self, rng, src, k, post, s):
        p, s2 = post.cache["p"][k], post.cache["s2"][k]
        u = self.units[src]
        if src == "own":
            c = rng.uniform(size=u) < p
            return np.where(c, rng.normal(0, s2, u), rng.normal(0, 1, u))
        if src == "stress":
            return rng.normal(0, s2, u)
        return (rng.uniform(size=u) < p).astype(float)

    def update_lw(self, src, y, post, s):
        return post.lw + self._loglik(src, y, post.cache["p"], post.cache["s2"])


# ----------------------------------------------------------------------------------------
# GARCH(1,1)-t6 with variance targeting
# ----------------------------------------------------------------------------------------
NU_G = 6.0
C_T6 = np.sqrt((NU_G - 2) / NU_G)


def _t6_logpdf(z):
    """Log density of the unit-variance t6."""
    return tm.logpdf_std(z / C_T6, NU_G) - np.log(C_T6)


def garch_path(r, v, a, b):
    """Conditional variances sigma2[t], t = 0..T (last = one-step forecast); vectorized params."""
    v, a, b = (np.atleast_1d(x).astype(float) for x in (v, a, b))
    om = v * (1 - a - b)
    T = len(r)
    s2 = np.empty((len(v), T + 1))
    s2[:, 0] = v
    for t in range(T):
        s2[:, t + 1] = om + a * r[t] ** 2 + b * s2[:, t]
    return s2


def garch_loglik(r, s2):
    """Sum of t6 log densities given the variance path s2 (N, T+1)."""
    return np.sum(_t6_logpdf(r[None, :] / np.sqrt(s2[:, :-1])) - 0.5 * np.log(s2[:, :-1]), axis=1)


def garch_simulate(rng, n, v, a, b, burn=300):
    """Simulate a GARCH(1,1)-t6 path; returns returns and the variance path (len n+1)."""
    z = rng.standard_t(NU_G, n + burn) * C_T6
    s2 = v
    r = np.empty(n + burn)
    path = np.empty(n + burn + 1)
    path[0] = s2
    om = v * (1 - a - b)
    for t in range(n + burn):
        r[t] = np.sqrt(s2) * z[t]
        s2 = om + a * r[t] ** 2 + b * s2
        path[t + 1] = s2
    return r[burn:], path[burn:]


class GarchDesign(_Base):
    """phi = (log v, alpha, beta); prior log v ~ N(0,1), (alpha, beta) uniform on
    {0 <= alpha <= 0.2, 0.6 <= beta, alpha + beta <= 0.995}."""

    sources = ("rv", "rv_hf", "peer")
    units = {"rv": 50, "rv_hf": 12, "peer": 250}
    M = {"rv": 10, "rv_hf": 50}
    targets = {
        "var99": ("var", 0.99),
        "qlike10": ("qlike", 10),
        "qlike5": ("qlike", 5),
        "qlike22": ("qlike", 22),
    }
    truths = {"regular": (1.0, 0.08, 0.88), "weak": (1.0, 0.02, 0.96)}
    N0 = 500

    def init_state(self, rng, truth: str, stages: int = 6) -> dict:
        v0, a0, b0 = self._truth(truth)
        r, path = garch_simulate(rng, self.N0, v0, a0, b0)
        n_rv = {k: self.units[k] * stages for k in ("rv", "rv_hf")}
        pools = {
            k: path[:-1][::-1][: n_rv[k]] * rng.gamma(self.M[k] / 2, 2 / self.M[k], n_rv[k])
            for k in ("rv", "rv_hf")
        }  # most recent day first
        pools["peer"] = [
            garch_simulate(rng, self.units["peer"], 1.0, a0, b0)[0] for _ in range(stages)
        ]
        return {
            "truth": (v0, a0, b0),
            "s2_next": path[-1],
            "pools": pools,
            "ptr": {s: 0 for s in self.sources},
            "data": {"r": r, "rv": np.empty(0), "rv_hf": np.empty(0), "peer": []},
        }

    def consume(self, s, src):
        s = self.copy_state(s)
        k = s["ptr"][src]
        if src == "peer":
            s["data"]["peer"] = s["data"]["peer"] + [s["pools"]["peer"][k]]
            s["ptr"][src] = k + 1
        else:
            u = self.units[src]
            s["data"][src] = np.concatenate([s["data"][src], s["pools"][src][k : k + u]])
            s["ptr"][src] = k + u
        return s

    # -- likelihood pieces ---------------------------------------------------------------
    def _rv_ll(self, src, vals, s2_rev):
        """vals[i] measures the variance of day T-1-i; s2_rev = s2[:, :-1][:, ::-1]."""
        if len(vals) == 0:
            return 0.0
        m = self.M[src]
        sv = s2_rev[:, : len(vals)]
        return np.sum(stats.gamma.logpdf(vals[None, :], m / 2, scale=2 * sv / m), axis=1)

    @staticmethod
    def _peer_ll(series, a, b):
        tot = 0.0
        for y in series:
            s2 = garch_path(y, np.full(len(a), np.var(y)), a, b)
            tot = tot + garch_loglik(y, s2)
        return tot

    def _lw(self, pts, d, keep_path=False):
        lv, a, b = pts[:, 0], pts[:, 1], pts[:, 2]
        ok = (a >= 0) & (a <= 0.2) & (b >= 0.6) & (a + b <= 0.995)
        lw = np.full(len(pts), -np.inf)
        idx = np.flatnonzero(ok)
        s2 = garch_path(d["r"], np.exp(lv[idx]), a[idx], b[idx])
        ll = garch_loglik(d["r"], s2) + stats.norm.logpdf(lv[idx], 0, 1)
        rev = s2[:, :-1][:, ::-1]
        for src in ("rv", "rv_hf"):
            ll = ll + self._rv_ll(src, d[src], rev)
        if d["peer"]:
            ll = ll + self._peer_ll(d["peer"], a[idx], b[idx])
        lw[idx] = ll
        return (lw, idx, s2) if keep_path else lw

    def fit(self, s):
        d = s["data"]
        lv0 = np.log(np.var(d["r"]))
        axes0 = [
            np.linspace(lv0 - 1.0, lv0 + 1.0, 9),
            np.linspace(0, 0.2, 21),
            np.linspace(0.6, 0.995, 21),
        ]
        # adapt only the log v axis; alpha and beta keep fixed full-support axes
        pts0 = np.stack([m.ravel() for m in np.meshgrid(*axes0, indexing="ij")], -1)
        lw0 = self._lw(pts0, d)
        w0 = np.exp(lw0 - lw0[np.isfinite(lw0)].max())
        w0 = np.where(np.isfinite(w0), w0, 0)
        w0 /= w0.sum()
        mu = w0 @ pts0[:, 0]
        sd = max(np.sqrt(w0 @ (pts0[:, 0] - mu) ** 2), 0.03)
        axes = [
            np.linspace(mu - 6 * sd, mu + 6 * sd, 11),
            np.linspace(0, 0.2, 41),
            np.linspace(0.6, 0.995, 41),
        ]
        pts = np.stack([m.ravel() for m in np.meshgrid(*axes, indexing="ij")], -1)
        lw, idx, s2 = self._lw(pts, d, keep_path=True)
        la = np.log(np.prod([ax[1] - ax[0] for ax in axes]))
        pts, lw = pts[idx], lw[idx] + la
        cache = {
            "v": np.exp(pts[:, 0]),
            "a": pts[:, 1],
            "b": pts[:, 2],
            "s2_rev": s2[:, :-1][:, ::-1].astype(np.float32),
            "s2_next": s2[:, -1],
        }
        return NodePost(pts, lw, cache)

    # -- functionals -------------------------------------------------------------------
    @staticmethod
    def _vh(v, a, b, s2n, h):
        """Expected sum of the next h conditional variances (h-day variance forecast)."""
        pi = a + b
        return h * v + (s2n - v) * (1 - pi**h) / (1 - pi)

    def lossmix(self, post, s):
        sc = np.sqrt(post.cache["s2_next"])[:, None] * C_T6
        return LossMix(sc, np.ones_like(sc), np.full(len(sc), NU_G))

    def truth_lossmix(self, s):
        return LossMix(
            np.array([[np.sqrt(s["s2_next"]) * C_T6]]), np.ones((1, 1)), np.array([NU_G])
        )

    def gvals(self, target, post, s):
        c = post.cache
        return self._vh(c["v"], c["a"], c["b"], c["s2_next"], self.targets[target][1])

    def truth_gval(self, target, s):
        v0, a0, b0 = s["truth"]
        return float(self._vh(v0, a0, b0, s["s2_next"], self.targets[target][1]))

    def g_point(self, target, p, s):
        v, a, b = np.exp(p[0]), p[1], p[2]
        s2n = garch_path(s["data"]["r"], v, a, b)[0, -1]
        if self.targets[target][0] == "qlike":
            return float(self._vh(v, a, b, s2n, self.targets[target][1]))
        return float(np.sqrt(s2n) * C_T6 * stats.t.ppf(self.targets[target][1], NU_G))

    def fd_step(self, m):
        return np.array(
            [
                1e-3,
                min(1e-3, 0.4 * max(m[1], 1e-6)),
                min(1e-3, 0.4 * max(0.995 - m[1] - m[2], 1e-6)),
            ]
        )

    # -- design operations -------------------------------------------------------------
    def local_info(self, src, m, post, s, rng):
        h = self.fd_step(m)
        pts = hess_stencil(m, h)
        v, a, b = np.exp(pts[:, 0]), pts[:, 1], pts[:, 2]
        H = np.zeros((3, 3))
        n_rep = 2
        for _ in range(n_rep):
            if src == "peer":
                y = garch_simulate(rng, self.units["peer"], 1.0, m[1], m[2])[0]
                f = self._peer_ll([y], a, b)
            else:
                k = s["ptr"][src]
                s2c = garch_path(s["data"]["r"], np.exp(m[0]), m[1], m[2])[0, :-1][::-1]
                days = s2c[k : k + self.units[src]]
                vals = days * rng.gamma(self.M[src] / 2, 2 / self.M[src], len(days))
                s2 = garch_path(s["data"]["r"], v, a, b)[:, :-1][:, ::-1][:, k : k + len(days)]
                mm = self.M[src]
                f = np.sum(stats.gamma.logpdf(vals[None, :], mm / 2, scale=2 * s2 / mm), axis=1)
            H += -hess_from_vals(f, h) / n_rep
        return psd(H)

    def simulate(self, rng, src, k, post, s):
        c = post.cache
        if src == "peer":
            return garch_simulate(rng, self.units["peer"], 1.0, c["a"][k], c["b"][k])[0]
        j = s["ptr"][src]
        days = c["s2_rev"][k, j : j + self.units[src]].astype(float)
        return days * rng.gamma(self.M[src] / 2, 2 / self.M[src], len(days))

    def update_lw(self, src, y, post, s):
        c = post.cache
        if src == "peer":
            return post.lw + self._peer_ll([y], c["a"], c["b"])
        j = s["ptr"][src]
        sv = c["s2_rev"][:, j : j + len(y)].astype(float)
        m = self.M[src]
        return post.lw + np.sum(stats.gamma.logpdf(y[None, :], m / 2, scale=2 * sv / m), axis=1)


# ----------------------------------------------------------------------------------------
# stochastic volatility (QML Kalman quasi-likelihood)
# ----------------------------------------------------------------------------------------
QM, QV = -1.2704, np.pi**2 / 2  # mean and variance of log chi2_1


def sv_simulate(rng, n, mu, ph, se, burn=300):
    """Simulate SV returns; returns (r, h) with h of length n+1 (last = h_{T+1} unused)."""
    h = np.empty(n + burn + 1)
    h[0] = mu + se / np.sqrt(1 - ph**2) * rng.standard_normal()
    for t in range(n + burn):
        h[t + 1] = mu + ph * (h[t] - mu) + se * rng.standard_normal()
    r = np.exp(h[:-1] / 2) * rng.standard_normal(n + burn)
    return r[burn:], h[burn:]


def sv_filter(y, rv_lists, mu, ph, se, return_states=False):
    """QML Kalman filter vectorized over parameters.

    y: log r^2 series (T,); rv_lists: list of (vals_rev, s) where vals_rev[i] is log RV of day
    T-1-i with lognormal noise sd s. Returns log-lik (N,), predictive (m, P) for h_{T+1}.
    """
    mu, ph, se = (np.atleast_1d(x).astype(float) for x in (mu, ph, se))
    T = len(y)
    meas = [[] for _ in range(T)]
    for vals, sd in rv_lists:
        for i, z in enumerate(vals):
            meas[T - 1 - i].append((z, sd))
    m = mu.copy()
    P = se**2 / (1 - ph**2)
    ll = np.zeros(len(mu))
    states = None
    for t in range(T):
        if t > 0:
            m = mu + ph * (m - mu)
            P = ph**2 * P + se**2
        S = P + QV
        e = y[t] - (m + QM)
        ll -= 0.5 * (np.log(2 * np.pi * S) + e**2 / S)
        K = P / S
        m = m + K * e
        P = P * (1 - K)
        for z, sd in meas[t]:
            S = P + sd**2
            e = z - (m - sd**2 / 2)
            ll -= 0.5 * (np.log(2 * np.pi * S) + e**2 / S)
            K = P / S
            m = m + K * e
            P = P * (1 - K)
    mp = mu + ph * (m - mu)
    Pp = ph**2 * P + se**2
    return (ll, mp, Pp, states) if return_states else (ll, mp, Pp)


def sv_ffbs(rng, y, rv_lists, mu, ph, se):
    """Forward-filter backward-sample a latent path h_0..h_{T-1} for one parameter point."""
    T = len(y)
    meas = [[] for _ in range(T)]
    for vals, sd in rv_lists:
        for i, z in enumerate(vals):
            meas[T - 1 - i].append((z, sd))
    mf = np.empty(T)
    Pf = np.empty(T)
    m, P = mu, se**2 / (1 - ph**2)
    for t in range(T):
        if t > 0:
            m = mu + ph * (m - mu)
            P = ph**2 * P + se**2
        S = P + QV
        K = P / S
        m = m + K * (y[t] - (m + QM))
        P = P * (1 - K)
        for z, sd in meas[t]:
            S = P + sd**2
            K = P / S
            m = m + K * (z - (m - sd**2 / 2))
            P = P * (1 - K)
        mf[t], Pf[t] = m, P
    h = np.empty(T)
    h[-1] = mf[-1] + np.sqrt(Pf[-1]) * rng.standard_normal()
    for t in range(T - 2, -1, -1):
        Pp = ph**2 * Pf[t] + se**2
        J = Pf[t] * ph / Pp
        mean = mf[t] + J * (h[t + 1] - (mu + ph * (mf[t] - mu)))
        var = Pf[t] - J**2 * Pp
        h[t] = mean + np.sqrt(max(var, 1e-12)) * rng.standard_normal()
    return h


class SVDesign(_Base):
    """phi = (mu, phi, log sigma_eta); prior mu ~ N(0, 1.5^2), phi ~ U(0.8, 0.995),
    log sigma_eta ~ N(log 0.2, 0.6^2). Quasi-posterior from the QML Kalman likelihood."""

    sources = ("rv", "rv_hf", "peer")
    units = {"rv": 50, "rv_hf": 12, "peer": 250}
    SD = {"rv": 0.5, "rv_hf": 0.2}
    targets = {"var99": ("var", 0.99)}
    truths = {"regular": (0.0, 0.95, 0.25), "weak": (0.0, 0.97, 0.06)}
    N0 = 500

    def __init__(self, exact: bool = False):
        # exact=True: observations y_t = h_t + N(QM, QV), so the QML likelihood is the exact
        # likelihood (misspecification ablation); exact=False: y_t = log r_t^2 (true SV)
        self.exact = exact

    def _y(self, rng, r, h):
        """Observation series from returns r and aligned log-variances h."""
        if self.exact:
            return h + rng.normal(QM, np.sqrt(QV), len(h))
        return np.log(r**2 + 1e-12)

    def _sim_peer(self, rng, ph, se):
        r, h = sv_simulate(rng, self.units["peer"], 0.0, ph, se)
        return self._y(rng, r, h[:-1])

    def init_state(self, rng, truth: str, stages: int = 6) -> dict:
        mu0, ph0, se0 = self._truth(truth)
        r, h = sv_simulate(rng, self.N0, mu0, ph0, se0)
        pools = {}
        for k in ("rv", "rv_hf"):
            n = self.units[k] * stages
            sd = self.SD[k]
            hv = h[:-1][::-1][:n]
            pools[k] = hv + rng.normal(-(sd**2) / 2, sd, n)  # log RV, most recent day first
        pools["peer"] = [self._sim_peer(rng, ph0, se0) for _ in range(stages)]
        return {
            "truth": (mu0, ph0, se0),
            "hT": h[-2],
            "pools": pools,
            "ptr": {s: 0 for s in self.sources},
            "data": {
                "y": self._y(rng, r, h[:-1]),
                "rv": np.empty(0),
                "rv_hf": np.empty(0),
                "peer": [],
            },
        }

    def consume(self, s, src):
        return GarchDesign.consume(self, s, src)

    def _rv_lists(self, d, extra=None):
        out = [(d[k], self.SD[k]) for k in ("rv", "rv_hf") if len(d[k])]
        if extra is not None:
            out.append(extra)
        return out

    @staticmethod
    def _peer_ll(series, ph, se):
        tot = 0.0
        for yp in series:
            mup = np.mean(yp) - QM
            tot = tot + sv_filter(yp, [], np.full(len(ph), mup), ph, se)[0]
        return tot

    def _prior(self, pts):
        ok = (pts[:, 1] >= 0.8) & (pts[:, 1] <= 0.995)
        lp = stats.norm.logpdf(pts[:, 0], 0, 1.5) + stats.norm.logpdf(pts[:, 2], np.log(0.2), 0.6)
        return np.where(ok, lp, -np.inf)

    def _lw(self, pts, d, extra=None):
        lp = self._prior(pts)
        idx = np.flatnonzero(np.isfinite(lp))
        out = np.full(len(pts), -np.inf)
        mu, ph, se = pts[idx, 0], pts[idx, 1], np.exp(pts[idx, 2])
        ll, mp, Pp = sv_filter(d["y"], self._rv_lists(d, extra), mu, ph, se)
        if d["peer"]:
            ll = ll + self._peer_ll(d["peer"], ph, se)
        out[idx] = lp[idx] + ll
        return out, idx, mp, Pp

    def fit(self, s):
        d = s["data"]
        mu0 = np.mean(d["y"]) - QM
        pts, la = adaptive_axes(
            lambda q: self._lw(q, d)[0],
            [
                np.linspace(mu0 - 1.5, mu0 + 1.5, 9),
                np.linspace(0.8, 0.995, 14),
                np.linspace(np.log(0.01), np.log(0.8), 14),
            ],
            [11, 30, 26],
            [(-10, 10), (0.8, 0.995), (np.log(0.005), np.log(1.0))],
        )
        lw, idx, mp, Pp = self._lw(pts, d)
        pts = pts[idx]
        return NodePost(pts, lw[idx] + la, {"mp": mp, "Pp": Pp, "la": la})

    def lossmix(self, post, s):
        h = post.cache["mp"][:, None] + np.sqrt(2 * post.cache["Pp"])[:, None] * GH_X[None, :]
        return LossMix(np.exp(h / 2), np.tile(GH_W, (len(h), 1)))

    def truth_lossmix(self, s):
        mu0, ph0, se0 = s["truth"]
        h = mu0 + ph0 * (s["hT"] - mu0) + np.sqrt(2) * se0 * GH_X
        return LossMix(np.exp(h / 2)[None, :], GH_W[None, :])

    def g_point(self, target, p, s):
        d = s["data"]
        _, mp, Pp = sv_filter(d["y"], self._rv_lists(d), p[0], p[1], np.exp(p[2]))
        h = mp[0] + np.sqrt(2 * Pp[0]) * GH_X
        return var_of_lossmix_point(
            LossMix(np.exp(h / 2)[None, :], GH_W[None, :]), self.targets[target][1]
        )

    def fd_step(self, m):
        return np.array([1e-3, min(1e-3, 0.4 * (0.995 - m[1])), 1e-3])

    def local_info(self, src, m, post, s, rng):
        d = s["data"]
        h = self.fd_step(m)
        pts = hess_stencil(m, h)
        H = np.zeros((3, 3))
        n_rep = 2
        for _ in range(n_rep):
            if src == "peer":
                y = self._sim_peer(rng, m[1], np.exp(m[2]))
                f = self._peer_ll([y], pts[:, 1], np.exp(pts[:, 2]))
                H += -hess_from_vals(f, h) / n_rep
            else:
                z = self._sim_rv(rng, src, m, s)
                with_ = sv_filter(
                    d["y"],
                    self._rv_lists(d, (z, self.SD[src])),
                    pts[:, 0],
                    pts[:, 1],
                    np.exp(pts[:, 2]),
                )[0]
                without = sv_filter(
                    d["y"], self._rv_lists(d), pts[:, 0], pts[:, 1], np.exp(pts[:, 2])
                )[0]
                H += -(hess_from_vals(with_, h) - hess_from_vals(without, h)) / n_rep
        return psd(H)

    def _sim_rv(self, rng, src, p, s):
        """Simulate the next batch of log RV (most recent unpurchased days first)."""
        d = s["data"]
        hp = sv_ffbs(rng, d["y"], self._rv_lists(d), p[0], p[1], np.exp(p[2]))
        j = s["ptr"][src]
        hv = hp[::-1][j : j + self.units[src]]
        sd = self.SD[src]
        return hv + rng.normal(-(sd**2) / 2, sd, len(hv))

    def simulate(self, rng, src, k, post, s):
        p = post.phi[k]
        if src == "peer":
            return self._sim_peer(rng, p[1], np.exp(p[2]))
        return self._sim_rv(rng, src, p, s)

    def update_lw(self, src, y, post, s):
        d = s["data"]
        if src == "peer":
            return post.lw + self._peer_ll([y], post.phi[:, 1], np.exp(post.phi[:, 2]))
        d2 = dict(d)
        d2[src] = np.concatenate([d[src], y])
        return self._lw(post.phi, d2)[0] + post.cache["la"]
