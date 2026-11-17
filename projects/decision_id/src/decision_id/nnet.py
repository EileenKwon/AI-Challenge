"""Small numpy MLP regressor (tanh, MSE, Adam, early stopping) for learned design policies."""

from __future__ import annotations

import numpy as np


class MLPRegressor:
    """y = MLP(x), two hidden tanh layers, scalar output; inputs standardized internally."""

    def __init__(self, d_in: int, hidden: int = 64, l2: float = 1e-4, seed: int = 0):
        rng = np.random.default_rng(seed)

        def init(a, b):
            return rng.normal(0, np.sqrt(1.0 / a), (a, b))

        self.p = {
            "W1": init(d_in, hidden),
            "b1": np.zeros(hidden),
            "W2": init(hidden, hidden),
            "b2": np.zeros(hidden),
            "W3": init(hidden, 1) * 0.1,
            "b3": np.zeros(1),
        }
        self.l2 = l2
        self.mu = np.zeros(d_in)
        self.sd = np.ones(d_in)

    def _fwd(self, Z):
        h1 = np.tanh(Z @ self.p["W1"] + self.p["b1"])
        h2 = np.tanh(h1 @ self.p["W2"] + self.p["b2"])
        return h1, h2, (h2 @ self.p["W3"] + self.p["b3"]).ravel()

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predictions for rows of X."""
        return self._fwd((np.atleast_2d(X) - self.mu) / self.sd)[2]

    def grads(self, Z, y):
        """MSE loss and parameter gradients."""
        h1, h2, out = self._fwd(Z)
        r = out - y
        loss = float(np.mean(r**2))
        go = (2 * r / len(y))[:, None]
        g = {"W3": h2.T @ go, "b3": go.sum(0)}
        dh2 = (go @ self.p["W3"].T) * (1 - h2**2)
        g["W2"], g["b2"] = h1.T @ dh2, dh2.sum(0)
        dh1 = (dh2 @ self.p["W2"].T) * (1 - h1**2)
        g["W1"], g["b1"] = Z.T @ dh1, dh1.sum(0)
        for k in ("W1", "W2", "W3"):
            g[k] = g[k] + 2 * self.l2 * self.p[k]
        return loss, g

    def fit(
        self,
        X,
        y,
        groups=None,
        epochs: int = 300,
        lr: float = 3e-3,
        batch: int = 256,
        val_frac: float = 0.2,
        patience: int = 30,
        seed: int = 0,
    ) -> dict:
        """Adam with early stopping on a validation split (split by `groups` if given)."""
        rng = np.random.default_rng(seed)
        X = np.asarray(X, float)
        y = np.asarray(y, float)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-8
        Z = (X - self.mu) / self.sd
        if groups is None:
            groups = np.arange(len(y))
        ug = np.unique(groups)
        val_g = set(rng.choice(ug, size=max(1, int(val_frac * len(ug))), replace=False))
        is_val = np.array([g in val_g for g in groups])
        Zt, yt, Zv, yv = Z[~is_val], y[~is_val], Z[is_val], y[is_val]
        m = {k: np.zeros_like(v) for k, v in self.p.items()}
        v = {k: np.zeros_like(w) for k, w in self.p.items()}
        best, best_p, wait, t, hist = np.inf, None, 0, 0, []
        for _ep in range(epochs):
            idx = rng.permutation(len(yt))
            for s in range(0, len(yt), batch):
                bi = idx[s : s + batch]
                _, g = self.grads(Zt[bi], yt[bi])
                t += 1
                for k in self.p:
                    m[k] = 0.9 * m[k] + 0.1 * g[k]
                    v[k] = 0.999 * v[k] + 0.001 * g[k] ** 2
                    self.p[k] -= (
                        lr * (m[k] / (1 - 0.9**t)) / (np.sqrt(v[k] / (1 - 0.999**t)) + 1e-8)
                    )
            vl = float(np.mean((self._fwd(Zv)[2] - yv) ** 2))
            hist.append(vl)
            if vl < best - 1e-6:
                best, best_p, wait = vl, {k: w.copy() for k, w in self.p.items()}, 0
            else:
                wait += 1
                if wait >= patience:
                    break
        self.p = best_p
        return {"val_mse": best, "epochs": len(hist), "val_var": float(np.var(yv))}
