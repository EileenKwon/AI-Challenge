"""Two-regime scale mixture of normals (calm/crisis) with a near-redundant parameter pair.

r ~ (1 - p) N(0, s1^2) + p N(0, s2^2), s1 known, s2 > s1. Parameters phi = (logit p, log s2).
Singular (non-identified) loci: p -> 0 makes s2 unidentified; s2 -> s1 makes p unidentified.
"""

from __future__ import annotations

import numpy as np
from scipy import special, stats

from .utils import num_grad


def canon(phi, s1: float = 1.0) -> np.ndarray:
    """phi=(logit p, log s2) -> (p, s2)."""
    phi = np.asarray(phi, float)
    return np.stack([special.expit(phi[..., 0]), np.exp(phi[..., 1])], -1)


def loglik_nodes(x: np.ndarray, p: np.ndarray, s2: np.ndarray, s1: float = 1.0) -> np.ndarray:
    """Log-likelihood of iid data at each node (p_k, s2_k)."""
    pf, sf = np.ravel(p), np.ravel(s2)
    out = np.empty(pf.size)
    chunk = max(1, int(4e6 // max(len(x), 1)))
    l1 = stats.norm.logpdf(x, 0, s1)
    for s in range(0, pf.size, chunk):
        sl = slice(s, s + chunk)
        l2 = stats.norm.logpdf(x[None, :], 0, sf[sl, None])
        a = np.log1p(-pf[sl, None]) + l1[None, :]
        b = np.log(pf[sl, None]) + l2
        out[sl] = np.logaddexp(a, b).sum(axis=1)
    return out.reshape(np.shape(p))


def cdf_loss(v, p, s2, s1: float = 1.0):
    """CDF of the loss L = -r (symmetric) at v."""
    return (1 - p) * stats.norm.cdf(v / s1) + p * stats.norm.cdf(v / s2)


def var_(p, s2, alpha, s1: float = 1.0):
    """Mixture VaR by vectorized bisection."""
    p, s2 = np.broadcast_arrays(np.asarray(p, float), np.asarray(s2, float))
    z = stats.norm.ppf(alpha)
    lo = np.full(p.shape, s1 * z * 0.999)
    hi = np.maximum(s2, s1) * z * 1.001
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        below = cdf_loss(mid, p, s2, s1) < alpha
        lo = np.where(below, mid, lo)
        hi = np.where(below, hi, mid)
    return 0.5 * (lo + hi)


def es_(p, s2, alpha, s1: float = 1.0):
    """Mixture ES: E[L | L > VaR]."""
    v = var_(p, s2, alpha, s1)
    tail = (1 - p) * s1 * stats.norm.pdf(v / s1) + p * s2 * stats.norm.pdf(v / s2)
    return tail / (1 - alpha)


def functional(name: str, c: np.ndarray, s1: float = 1.0):
    """Named functional of canonical (p, s2)."""
    p, s2 = c[..., 0], c[..., 1]
    digits = "".join(ch for ch in name if ch.isdigit())
    a = float("0." + digits)
    return var_(p, s2, a, s1) if name.startswith("var") else es_(p, s2, a, s1)


def expected_pinball(v, alpha, p, s2, s1: float = 1.0):
    """E[rho_alpha(L - v)] under the mixture (L symmetric, mean 0)."""

    def upper(sig):
        c = v / sig
        return sig * (stats.norm.pdf(c) - c * stats.norm.sf(c))

    return (1 - p) * upper(s1) + p * upper(s2) + (1 - alpha) * v


def pinball_regret(v, alpha, p, s2, s1: float = 1.0):
    """Quantile-score regret of a VaR report."""
    return expected_pinball(v, alpha, p, s2, s1) - expected_pinball(
        var_(p, s2, alpha, s1), alpha, p, s2, s1
    )


def predictive_var(c: np.ndarray, w: np.ndarray, alpha: float, s1: float = 1.0) -> float:
    """VaR of the posterior predictive (mixture of mixtures)."""
    p, s2 = c[:, 0], c[:, 1]
    lo, hi = s1 * stats.norm.ppf(alpha) * 0.99, float(np.max(s2)) * stats.norm.ppf(alpha) * 1.01
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if np.sum(w * cdf_loss(mid, p, s2, s1)) < alpha:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def fisher(phi: np.ndarray, s1: float = 1.0, n_y: int = 4001) -> np.ndarray:
    """Per-observation Fisher information in phi by quadrature of score outer products."""
    s2 = np.exp(phi[1])
    y = np.linspace(-12 * max(s2, s1), 12 * max(s2, s1), n_y)
    dy = y[1] - y[0]

    def logf(ph):
        pp, ss = special.expit(ph[0]), np.exp(ph[1])
        return np.logaddexp(
            np.log1p(-pp) + stats.norm.logpdf(y, 0, s1), np.log(pp) + stats.norm.logpdf(y, 0, ss)
        )

    h = 1e-5
    S = np.stack([(logf(phi + e) - logf(phi - e)) / (2 * h) for e in np.eye(2) * h])
    f = np.exp(logf(phi))
    return (S * f) @ S.T * dy


def grad_functional(name: str, phi: np.ndarray, s1: float = 1.0) -> np.ndarray:
    """Gradient of a functional in phi."""
    return num_grad(lambda ph: float(functional(name, canon(ph)[None, :], s1)[0]), phi, rel=1e-5)
