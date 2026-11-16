"""Shared utilities: configuration, numerical derivatives, weighted statistics."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path | None = None) -> dict:
    """Load config.yaml and resolve output paths relative to the project root."""
    cfg_path = Path(path) if path else PROJECT_ROOT / "config.yaml"
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    cfg["paths"] = {k: (PROJECT_ROOT / v) for k, v in cfg["paths"].items()}
    return cfg


def num_grad(f: Callable[[np.ndarray], float], x: np.ndarray, rel: float = 1e-5) -> np.ndarray:
    """Central-difference gradient of a scalar function."""
    x = np.asarray(x, float)
    g = np.zeros_like(x)
    for k in range(x.size):
        h = rel * max(1.0, abs(x[k]))
        e = np.zeros_like(x)
        e[k] = h
        g[k] = (f(x + e) - f(x - e)) / (2 * h)
    return g


def num_jac(f: Callable[[np.ndarray], np.ndarray], x: np.ndarray, rel: float = 1e-6) -> np.ndarray:
    """Central-difference Jacobian J[i, k] = d f_i / d x_k."""
    x = np.asarray(x, float)
    f0 = np.atleast_1d(f(x))
    J = np.zeros((f0.size, x.size))
    for k in range(x.size):
        h = rel * max(1.0, abs(x[k]))
        e = np.zeros_like(x)
        e[k] = h
        J[:, k] = (np.atleast_1d(f(x + e)) - np.atleast_1d(f(x - e))) / (2 * h)
    return J


def num_hess(f: Callable[[np.ndarray], float], x: np.ndarray, rel: float = 1e-4) -> np.ndarray:
    """Central-difference Hessian of a scalar function."""
    x = np.asarray(x, float)
    d = x.size
    H = np.zeros((d, d))
    hs = np.array([rel * max(1.0, abs(v)) for v in x])
    for i in range(d):
        for j in range(i, d):
            ei = np.zeros(d)
            ej = np.zeros(d)
            ei[i] = hs[i]
            ej[j] = hs[j]
            val = (f(x + ei + ej) - f(x + ei - ej) - f(x - ei + ej) + f(x - ei - ej)) / (
                4 * hs[i] * hs[j]
            )
            H[i, j] = H[j, i] = val
    return H


def weighted_quantile(values: np.ndarray, weights: np.ndarray, qs) -> np.ndarray:
    """Quantiles of a discrete weighted distribution (linear interpolation of the CDF)."""
    order = np.argsort(values)
    v = values[order]
    w = weights[order] / weights.sum()
    cdf = np.cumsum(w) - 0.5 * w
    return np.interp(np.atleast_1d(qs), cdf, v)


def weighted_mean_var(values: np.ndarray, weights: np.ndarray) -> tuple[float, float]:
    """Weighted mean and variance."""
    w = weights / weights.sum()
    m = float(np.sum(w * values))
    return m, float(np.sum(w * (values - m) ** 2))


def logsumexp_normalize(logw: np.ndarray) -> np.ndarray:
    """Return normalized weights from unnormalized log weights."""
    m = np.max(logw)
    w = np.exp(logw - m)
    return w / w.sum()


def safe_div(num, den):
    """Ratio with zero-denominator protection (denominator floored at 1e-300 in magnitude)."""
    den = np.asarray(den, float)
    return np.asarray(num, float) / np.where(np.abs(den) < 1e-300, 1e-300, den)
