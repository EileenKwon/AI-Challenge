"""Minimal neural posterior estimation (NPE) in numpy (no deep-learning framework available).

Amortized conditional density q(u | s(x)) = N(m(s), L(s) L(s)^T) over the unconstrained
u = (log sd - log sd_hat(x), logit(xi / xi_max)); a 2-hidden-layer tanh MLP trained by
Adam on the Gaussian negative log-likelihood (Papamakarios & Murray 2016 style, Gaussian
head). The log sd shift by the data's sample sd is a data-dependent reparameterization.
"""

from __future__ import annotations

import numpy as np

from . import tmodel as tm

QS = (0.5, 0.75, 0.9, 0.95, 0.975, 0.99)


def summaries(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Scale-free summary statistics of each row of X; returns (S, log sd_hat)."""
    sd = X.std(axis=1)
    A = np.abs(X) / sd[:, None]
    qs = np.quantile(A, QS, axis=1).T
    kurt = np.log(np.mean(A**4, axis=1))
    mx = np.log(A.max(axis=1))
    mad = np.log(np.mean(A, axis=1))
    return np.column_stack([np.log(qs), kurt, mx, mad]), np.log(sd)


class GaussNPE:
    """Two-hidden-layer MLP with a bivariate Gaussian head."""

    def __init__(self, d_in: int, hidden: int, rng: np.random.Generator):
        def init(a, b):
            return rng.normal(0, np.sqrt(1.0 / a), (a, b))

        self.p = {
            "W1": init(d_in, hidden),
            "b1": np.zeros(hidden),
            "W2": init(hidden, hidden),
            "b2": np.zeros(hidden),
            "W3": init(hidden, 5) * 0.1,
            "b3": np.zeros(5),
        }
        self.mu_s = None
        self.sd_s = None

    def _forward(self, S):
        h1 = np.tanh(S @ self.p["W1"] + self.p["b1"])
        h2 = np.tanh(h1 @ self.p["W2"] + self.p["b2"])
        return h1, h2, h2 @ self.p["W3"] + self.p["b3"]

    @staticmethod
    def _nll_grad(o, U):
        m1, m2, a1, a2, b = o.T
        d1, d2 = U[:, 0] - m1, U[:, 1] - m2
        r1 = d1 * np.exp(-a1)
        r2 = (d2 - b * r1) * np.exp(-a2)
        nll = a1 + a2 + 0.5 * (r1**2 + r2**2)
        g_r1 = r1 - r2 * b * np.exp(-a2)
        go = np.column_stack(
            [
                -g_r1 * np.exp(-a1),
                -r2 * np.exp(-a2),
                1 - g_r1 * r1,
                1 - r2**2,
                -r2 * r1 * np.exp(-a2),
            ]
        )
        return nll, go

    def fit(self, S, U, epochs: int, lr: float, rng: np.random.Generator, batch: int = 256):
        """Adam training on (summaries, targets)."""
        self.mu_s, self.sd_s = S.mean(0), S.std(0) + 1e-8
        Z = (S - self.mu_s) / self.sd_s
        mom = {k: np.zeros_like(v) for k, v in self.p.items()}
        vel = {k: np.zeros_like(v) for k, v in self.p.items()}
        t = 0
        hist = []
        for ep in range(epochs):
            idx = rng.permutation(len(Z))
            lr_ep = lr * (0.5 ** (ep / max(epochs / 3, 1)))
            tot = 0.0
            for s in range(0, len(Z), batch):
                bi = idx[s : s + batch]
                h1, h2, o = self._forward(Z[bi])
                nll, go = self._nll_grad(o, U[bi])
                tot += nll.sum()
                go = go / len(bi)
                g = {"W3": h2.T @ go, "b3": go.sum(0)}
                dh2 = (go @ self.p["W3"].T) * (1 - h2**2)
                g["W2"], g["b2"] = h1.T @ dh2, dh2.sum(0)
                dh1 = (dh2 @ self.p["W2"].T) * (1 - h1**2)
                g["W1"], g["b1"] = Z[bi].T @ dh1, dh1.sum(0)
                t += 1
                for k in self.p:
                    mom[k] = 0.9 * mom[k] + 0.1 * g[k]
                    vel[k] = 0.999 * vel[k] + 0.001 * g[k] ** 2
                    mh = mom[k] / (1 - 0.9**t)
                    vh = vel[k] / (1 - 0.999**t)
                    self.p[k] -= lr_ep * mh / (np.sqrt(vh) + 1e-8)
            hist.append(tot / len(Z))
        return hist

    def sample(self, S: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
        """Draw n samples of u for a single summary vector S (1-D)."""
        _, _, o = self._forward(((S - self.mu_s) / self.sd_s)[None, :])
        m1, m2, a1, a2, b = o[0]
        L = np.array([[np.exp(a1), 0.0], [b, np.exp(a2)]])
        return np.array([m1, m2]) + rng.standard_normal((n, 2)) @ L.T


def simulate_training(rng, n: int, n_train: int, prior, xi_max: float):
    """Simulate (summaries, targets) from the prior predictive."""
    logsd = rng.normal(prior.logsd_mean, prior.logsd_sd, n_train)
    xi = rng.uniform(1e-4, xi_max, n_train)
    sigma = np.exp(logsd) * np.sqrt(1 - 2 * xi)
    X = sigma[:, None] * rng.standard_t(1.0 / xi[:, None], (n_train, n))
    S, lsd_hat = summaries(X)
    U = np.column_stack([logsd - lsd_hat, np.log(xi / xi_max) - np.log1p(-xi / xi_max)])
    return S, U


def posterior_canon(model: GaussNPE, x: np.ndarray, n_draws: int, rng, xi_max: float):
    """Canonical (sigma, xi) draws of the NPE posterior for one dataset."""
    S, lsd = summaries(x[None, :])
    u = model.sample(S[0], n_draws, rng)
    u[:, 0] += lsd[0]
    return tm.canon_from(u, "u", xi_max)
