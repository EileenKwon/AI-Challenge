"""Gaussian location-scale return model with a conjugate Normal-Inverse-Gamma prior.

Returns r ~ N(mu, sd^2) in percent; loss L = -r. Parameters theta = (mu, log sd).
Used for exactness tests and for the location-vs-scale decoupling experiment (E2).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import optimize, stats

from .utils import num_hess


@dataclass
class NIG:
    """mu | s2 ~ N(m, s2/k), s2 ~ InvGamma(a, b)."""

    m: float
    k: float
    a: float
    b: float

    def update(self, x: np.ndarray) -> NIG:
        """Exact conjugate update."""
        n = len(x)
        xb = float(np.mean(x))
        ss = float(np.sum((x - xb) ** 2))
        kn = self.k + n
        mn = (self.k * self.m + n * xb) / kn
        an = self.a + n / 2
        bn = self.b + 0.5 * ss + 0.5 * self.k * n * (xb - self.m) ** 2 / kn
        return NIG(mn, kn, an, bn)

    def sample(self, rng: np.random.Generator, size: int) -> np.ndarray:
        """Draw (mu, sd) pairs."""
        s2 = self.b / rng.gamma(self.a, 1.0, size)
        mu = rng.normal(self.m, np.sqrt(s2 / self.k))
        return np.column_stack([mu, np.sqrt(s2)])

    def logpdf(self, mu, logsd) -> np.ndarray:
        """Log density in (mu, log sd) coordinates."""
        s2 = np.exp(2 * logsd)
        lp_s2 = stats.invgamma.logpdf(s2, self.a, scale=self.b)
        lp_mu = stats.norm.logpdf(mu, self.m, np.sqrt(s2 / self.k))
        return lp_s2 + lp_mu + np.log(2 * s2)  # d s2 / d log sd = 2 s2


def var_(mu, sd, alpha):
    """Loss VaR."""
    return -np.asarray(mu) + np.asarray(sd) * stats.norm.ppf(alpha)


def es_(mu, sd, alpha):
    """Loss ES."""
    z = stats.norm.ppf(alpha)
    return -np.asarray(mu) + np.asarray(sd) * stats.norm.pdf(z) / (1 - alpha)


def weight_(mu, sd, gamma):
    """Mean-variance optimal risky weight w* = mu / (gamma sd^2)."""
    return np.asarray(mu) / (gamma * np.asarray(sd) ** 2)


def functional(name: str, mu, sd, gamma: float = 3.0):
    """Named functional."""
    if name == "weight":
        return weight_(mu, sd, gamma)
    if name == "variance":
        return np.asarray(sd) ** 2
    digits = "".join(ch for ch in name if ch.isdigit())
    a = float("0." + digits)
    return var_(mu, sd, a) if name.startswith("var") else es_(mu, sd, a)


def fisher(mu: float, sd: float) -> np.ndarray:
    """Per-observation Fisher information in (mu, log sd)."""
    return np.diag([1 / sd**2, 2.0])


def pinball_regret(v, alpha, mu, sd):
    """Expected quantile-score regret of a loss-VaR report v."""

    def ep(vv):
        c = (vv + mu) / sd  # L = -mu + sd Z
        upper = sd * (stats.norm.pdf(c) - c * stats.norm.sf(c))
        return upper + (1 - alpha) * (vv + mu)

    return ep(np.asarray(v)) - ep(var_(mu, sd, alpha))


def weight_regret(w, mu, sd, gamma):
    """Certainty-equivalent loss of weight w versus the optimal weight."""
    return 0.5 * gamma * sd**2 * (np.asarray(w) - weight_(mu, sd, gamma)) ** 2


def mle(x: np.ndarray) -> np.ndarray:
    """MLE of (mu, sd)."""
    return np.array([np.mean(x), np.std(x)])


def laplace(x: np.ndarray, prior: NIG, rng: np.random.Generator, n_draws: int):
    """Laplace approximation in (mu, log sd) using the exact log posterior."""
    post = prior.update(x)

    def f(p):
        return -float(post.logpdf(p[0], p[1]))

    r = optimize.minimize(f, np.array([np.mean(x), np.log(np.std(x))]), method="BFGS")
    cov = np.linalg.inv(num_hess(f, r.x))
    d = rng.multivariate_normal(r.x, cov, size=n_draws)
    return np.column_stack([d[:, 0], np.exp(d[:, 1])]), r.x, cov


def mcmc(x: np.ndarray, prior: NIG, rng: np.random.Generator, iters: int, burn: int):
    """Random-walk Metropolis in (mu, log sd)."""
    post = prior.update(x)
    p = np.array([np.mean(x), np.log(np.std(x))])
    lp = post.logpdf(*p)
    step = np.array([np.std(x) / np.sqrt(len(x)), 1 / np.sqrt(2 * len(x))]) * 2.4 / np.sqrt(2)
    out = np.empty((iters, 2))
    for t in range(iters):
        q = p + step * rng.standard_normal(2)
        lq = post.logpdf(*q)
        if np.log(rng.uniform()) < lq - lp:
            p, lp = q, lq
        out[t] = p
    out = out[burn:]
    return np.column_stack([out[:, 0], np.exp(out[:, 1])])


def vi_meanfield(x: np.ndarray, prior: NIG, rng: np.random.Generator, n_draws: int, n_gh=12):
    """Mean-field Gaussian VI in (mu, log sd) with a Gauss-Hermite ELBO."""
    post = prior.update(x)
    gx, gw = np.polynomial.hermite_e.hermegauss(n_gh)
    gw = gw / gw.sum()
    Z1, Z2 = np.meshgrid(gx, gx, indexing="ij")
    W = np.outer(gw, gw).ravel()

    def neg(p):
        mu = p[0] + np.exp(p[2]) * Z1.ravel()
        ls = p[1] + np.exp(p[3]) * Z2.ravel()
        return -(W @ post.logpdf(mu, ls) + p[2] + p[3])

    p0 = np.array(
        [
            np.mean(x),
            np.log(np.std(x)),
            np.log(np.std(x) / np.sqrt(len(x))),
            np.log(1 / np.sqrt(2 * len(x))),
        ]
    )
    r = optimize.minimize(neg, p0, method="L-BFGS-B")
    mu = r.x[0] + np.exp(r.x[2]) * rng.standard_normal(n_draws)
    ls = r.x[1] + np.exp(r.x[3]) * rng.standard_normal(n_draws)
    return np.column_stack([mu, np.exp(ls)])
