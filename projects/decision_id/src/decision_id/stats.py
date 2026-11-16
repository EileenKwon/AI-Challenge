"""Statistical inference utilities for simulation studies and forecast comparison.

mcse_*            Monte Carlo standard errors (Morris, White & Crowther 2019, Stat. Med.)
wilson            binomial (Wilson) interval for coverage
paired_tests      paired t (= Diebold-Mariano with iid replicates), Wilcoxon signed-rank,
                  paired bootstrap CI for the mean difference
holm / bh         multiplicity adjustment (Holm 1979; Benjamini & Hochberg 1995)
dm_test           Diebold-Mariano (1995) test with Newey-West HAC variance for a loss series
kupiec_pof        Kupiec (1995) proportion-of-failures likelihood-ratio test
mcs               Model Confidence Set (Hansen, Lunde & Nason 2011), Tmax statistic, iid bootstrap
cluster_t         one-sample t-test treating independent clusters (cells) as the unit
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def mcse_mean(x: np.ndarray) -> float:
    """Monte Carlo standard error of a mean."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(np.std(x, ddof=1) / np.sqrt(len(x))) if len(x) > 1 else np.nan


def mcse_prop(p: float, n: int) -> float:
    """Monte Carlo standard error of a proportion (e.g., coverage)."""
    return float(np.sqrt(p * (1 - p) / max(n, 1)))


def wilson(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return np.nan, np.nan
    z = stats.norm.ppf(0.5 + level / 2)
    p = k / n
    den = 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    return float(c - h), float(c + h)


def binom_two_sided(k: int, n: int, p0: float) -> float:
    """Exact two-sided binomial test p-value."""
    return float(stats.binomtest(int(k), int(n), p0).pvalue)


def paired_tests(a: np.ndarray, b: np.ndarray, rng=None, B: int = 4000) -> dict:
    """Paired comparison of losses a vs b (negative mean_diff = a better).

    Returns mean difference, its MCSE, paired-t p, Wilcoxon p (ties dropped), bootstrap 95% CI
    of the mean difference and the ratio of means.
    """
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    d = a - b
    out = {
        "n": int(len(d)),
        "mean_a": float(a.mean()),
        "mean_b": float(b.mean()),
        "ratio": float(a.mean() / b.mean()) if b.mean() != 0 else np.nan,
        "mean_diff": float(d.mean()),
        "mcse_diff": mcse_mean(d),
    }
    if np.allclose(d, 0):
        out.update({"p_t": 1.0, "p_wilcoxon": 1.0, "ci_lo": 0.0, "ci_hi": 0.0, "frac_tie": 1.0})
        return out
    out["p_t"] = float(stats.ttest_1samp(d, 0.0).pvalue)
    nz = d[d != 0]
    out["p_wilcoxon"] = float(stats.wilcoxon(nz).pvalue) if len(nz) >= 10 else np.nan
    out["frac_tie"] = float(np.mean(d == 0))
    rng = rng or np.random.default_rng(0)
    idx = rng.integers(0, len(d), (B, len(d)))
    bm = d[idx].mean(1)
    out["ci_lo"], out["ci_hi"] = (float(v) for v in np.quantile(bm, [0.025, 0.975]))
    return out


def holm(p: np.ndarray) -> np.ndarray:
    """Holm step-down adjusted p-values."""
    p = np.asarray(p, float)
    m = len(p)
    order = np.argsort(p)
    adj = np.empty(m)
    run = 0.0
    for i, j in enumerate(order):
        run = max(run, (m - i) * p[j])
        adj[j] = min(1.0, run)
    return adj


def bh(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values (FDR)."""
    p = np.asarray(p, float)
    m = len(p)
    order = np.argsort(p)[::-1]
    adj = np.empty(m)
    run = 1.0
    for i, j in enumerate(order):
        rank = m - i
        run = min(run, p[j] * m / rank)
        adj[j] = run
    return adj


def newey_west_var(d: np.ndarray, lag: int | None = None) -> float:
    """Newey-West long-run variance of a series."""
    d = np.asarray(d, float) - np.mean(d)
    T = len(d)
    if lag is None:
        lag = int(np.floor(4 * (T / 100) ** (2 / 9)))
    v = d @ d / T
    for k in range(1, lag + 1):
        w = 1 - k / (lag + 1)
        v += 2 * w * (d[k:] @ d[:-k]) / T
    return float(v)


def dm_test(loss_a: np.ndarray, loss_b: np.ndarray, lag: int | None = None) -> tuple[float, float]:
    """Diebold-Mariano statistic and two-sided p-value (negative stat = a better)."""
    d = np.asarray(loss_a, float) - np.asarray(loss_b, float)
    v = newey_west_var(d, lag)
    if v <= 0:
        return 0.0, 1.0
    s = float(d.mean() / np.sqrt(v / len(d)))
    return s, float(2 * stats.norm.sf(abs(s)))


def kupiec_pof(exceed: np.ndarray, tail_prob: float) -> tuple[float, float]:
    """Kupiec POF likelihood-ratio statistic and p-value (chi2_1)."""
    x = int(np.sum(exceed))
    T = len(exceed)
    p = tail_prob
    phat = x / T
    ll1 = 0.0 if phat in (0.0, 1.0) else x * np.log(phat) + (T - x) * np.log(1 - phat)
    ll0 = x * np.log(p) + (T - x) * np.log(1 - p)
    lr = float(-2 * (ll0 - ll1))
    return lr, float(stats.chi2.sf(lr, 1))


def mcs(losses: np.ndarray, names: list[str], alpha: float = 0.10, B: int = 3000, rng=None):
    """Model Confidence Set with the T_max statistic and iid bootstrap over rows.

    losses: (n, M) per-replicate losses. Returns (list of surviving names, dict of MCS p-values).
    """
    rng = rng or np.random.default_rng(0)
    L = np.asarray(losses, float)
    n, M = L.shape
    alive = list(range(M))
    pvals = {}
    running = 0.0
    idx = rng.integers(0, n, (B, n))
    while len(alive) > 1:
        sub = L[:, alive]
        dbar_i = sub.mean(0) - sub.mean()  # loss relative to average of alive models
        boot = sub[idx].mean(1) - sub[idx].mean(axis=(1, 2))[:, None]
        var = ((boot - dbar_i) ** 2).mean(0)
        t = dbar_i / np.sqrt(np.maximum(var, 1e-300))
        tmax = t.max()
        tb = ((boot - dbar_i) / np.sqrt(np.maximum(var, 1e-300))).max(1)
        p = float(np.mean(tb >= tmax))
        worst = alive[int(np.argmax(t))]
        running = max(running, p)
        pvals[names[worst]] = running
        if p >= alpha:
            break
        alive.remove(worst)
    for j in alive:
        pvals.setdefault(names[j], 1.0)
    return [names[j] for j in alive], pvals


def cluster_t(values: np.ndarray, clusters: np.ndarray) -> dict:
    """Average within clusters, then one-sample t-test of the cluster means against 0."""
    v = np.asarray(values, float)
    c = np.asarray(clusters)
    ok = np.isfinite(v)
    means = np.array([v[ok & (c == k)].mean() for k in np.unique(c[ok])])
    t = stats.ttest_1samp(means, 0.0)
    return {
        "mean": float(means.mean()),
        "se": float(means.std(ddof=1) / np.sqrt(len(means))),
        "n_clusters": int(len(means)),
        "p": float(t.pvalue),
    }
