"""Student-t location-scale return model with known location (default 0).

Returns r = mu + sigma * T, T ~ t_nu, in percent units. Loss L = -r.
Canonical parameters: sigma > 0 (t scale) and xi = 1/nu (tail index).

Parameterizations (2-vectors phi):
  "logsd_xi": (log sd, xi),  sd = sigma / sqrt(1 - 2 xi)          [grid coordinates]
  "eta_xi":   (log sigma, xi)
  "sigma_nu": (sigma, nu)
  "u":        (log sd, logit(xi / xi_max))                          [unconstrained]
  "eta_u":    (log sigma, logit(xi / xi_max))
"""

from __future__ import annotations

import numpy as np
from scipy import special, stats

from .utils import num_jac

LOG_PI = np.log(np.pi)
XI_SMALL = 0.002  # below this, Fisher entries are interpolated to the Gaussian limit
PARAMS = ("logsd_xi", "eta_xi", "sigma_nu", "u", "eta_u")


# ----------------------------------------------------------------------------------------
# densities
# ----------------------------------------------------------------------------------------
def logpdf_std(z: np.ndarray, nu: np.ndarray) -> np.ndarray:
    """Log density of the standard t_nu (broadcasting)."""
    nu = np.asarray(nu, float)
    c = special.gammaln(0.5 * (nu + 1)) - special.gammaln(0.5 * nu) - 0.5 * (np.log(nu) + LOG_PI)
    return c - 0.5 * (nu + 1) * np.log1p(z * z / nu)


def loglik_grid(x: np.ndarray, sigma: np.ndarray, xi: np.ndarray, mu: float = 0.0) -> np.ndarray:
    """Log-likelihood of iid data x at each (sigma_k, xi_k) pair (arrays of equal shape)."""
    sig = np.ravel(sigma)
    nu = 1.0 / np.ravel(xi)
    out = np.empty(sig.size)
    xs = np.asarray(x, float) - mu
    chunk = max(1, int(4e6 // max(xs.size, 1)))
    for s in range(0, sig.size, chunk):
        sl = slice(s, s + chunk)
        z = xs[None, :] / sig[sl, None]
        out[sl] = logpdf_std(z, nu[sl, None]).sum(axis=1) - xs.size * np.log(sig[sl])
    return out.reshape(np.shape(sigma))


def sample(rng: np.random.Generator, n: int, sigma: float, xi: float, mu: float = 0.0):
    """Draw n returns."""
    return mu + sigma * rng.standard_t(1.0 / xi, size=n)


# ----------------------------------------------------------------------------------------
# parameterizations
# ----------------------------------------------------------------------------------------
def canon_from(phi, kind: str, xi_max: float = 0.45) -> np.ndarray:
    """Map phi (..., 2) in parameterization `kind` to canonical (sigma, xi)."""
    phi = np.asarray(phi, float)
    a, b = phi[..., 0], phi[..., 1]
    if kind == "logsd_xi":
        xi = b
        sigma = np.exp(a) * np.sqrt(1 - 2 * xi)
    elif kind == "eta_xi":
        sigma, xi = np.exp(a), b
    elif kind == "sigma_nu":
        sigma, xi = a, 1.0 / b
    elif kind == "u":
        xi = xi_max * special.expit(b)
        sigma = np.exp(a) * np.sqrt(1 - 2 * xi)
    elif kind == "eta_u":
        xi = xi_max * special.expit(b)
        sigma = np.exp(a)
    else:
        raise ValueError(kind)
    return np.stack([sigma, xi], axis=-1)


def phi_from(canon, kind: str, xi_max: float = 0.45) -> np.ndarray:
    """Inverse of canon_from."""
    canon = np.asarray(canon, float)
    sigma, xi = canon[..., 0], canon[..., 1]
    logsd = np.log(sigma) - 0.5 * np.log(1 - 2 * xi)
    if kind == "logsd_xi":
        out = (logsd, xi)
    elif kind == "eta_xi":
        out = (np.log(sigma), xi)
    elif kind == "sigma_nu":
        out = (sigma, 1.0 / xi)
    elif kind == "u":
        out = (logsd, special.logit(xi / xi_max))
    elif kind == "eta_u":
        out = (np.log(sigma), special.logit(xi / xi_max))
    else:
        raise ValueError(kind)
    return np.stack(out, axis=-1)


def sd_of(sigma, xi):
    """Standard deviation of the t location-scale distribution."""
    return sigma / np.sqrt(1 - 2 * np.asarray(xi))


# ----------------------------------------------------------------------------------------
# Fisher information (per observation)
# ----------------------------------------------------------------------------------------
def _fisher_sigma_xi_raw(sigma: float, xi: float) -> np.ndarray:
    nu = 1.0 / xi
    i_ss = 2 * nu / ((nu + 3) * sigma**2)
    i_sn = -2 / ((nu + 1) * (nu + 3) * sigma)
    i_nn = 0.25 * (special.polygamma(1, nu / 2) - special.polygamma(1, (nu + 1) / 2)) - (nu + 5) / (
        2 * nu * (nu + 1) * (nu + 3)
    )
    dnu = -(nu**2)
    return np.array([[i_ss, i_sn * dnu], [i_sn * dnu, i_nn * dnu**2]])


def fisher_sigma_xi(sigma: float, xi: float) -> np.ndarray:
    """Per-observation Fisher information in canonical (sigma, xi) coordinates.

    Closed form (Lange, Little & Taylor 1989) transformed to xi = 1/nu; for xi < XI_SMALL
    the entries are linearly interpolated to the Gaussian limit (2/s^2, 2/s, 3.5), which
    avoids catastrophic cancellation in the trigamma difference.
    """
    if xi >= XI_SMALL:
        return _fisher_sigma_xi_raw(sigma, xi)
    lim = np.array([[2 / sigma**2, 2 / sigma], [2 / sigma, 3.5]])
    at = _fisher_sigma_xi_raw(sigma, XI_SMALL)
    w = xi / XI_SMALL
    return (1 - w) * lim + w * at


def fisher(phi, kind: str, xi_max: float = 0.45) -> np.ndarray:
    """Per-observation Fisher information in parameterization `kind` (I_phi = J^T I J)."""
    phi = np.asarray(phi, float)
    sigma, xi = canon_from(phi, kind, xi_max)
    J = num_jac(lambda p: canon_from(p, kind, xi_max), phi)
    return J.T @ fisher_sigma_xi(sigma, xi) @ J


# ----------------------------------------------------------------------------------------
# financial functionals (loss scale, L = -r, mu known)
# ----------------------------------------------------------------------------------------
def var_(sigma, xi, alpha, mu=0.0):
    """Value-at-Risk of the loss at level alpha."""
    return -mu + sigma * stats.t.ppf(alpha, 1.0 / np.asarray(xi))


def es_(sigma, xi, alpha, mu=0.0):
    """Expected Shortfall of the loss at level alpha (requires nu > 1)."""
    nu = 1.0 / np.asarray(xi)
    q = stats.t.ppf(alpha, nu)
    return -mu + sigma * (nu + q**2) / (nu - 1) * stats.t.pdf(q, nu) / (1 - alpha)


def variance_(sigma, xi):
    """Return variance."""
    return np.asarray(sigma) ** 2 / (1 - 2 * np.asarray(xi))


def functional(name: str, canon) -> np.ndarray:
    """Evaluate a named functional ('var975', 'es99', 'variance', ...) at canonical params."""
    canon = np.asarray(canon, float)
    sigma, xi = canon[..., 0], canon[..., 1]
    if name == "variance":
        return variance_(sigma, xi)
    if name.startswith("var"):
        return var_(sigma, xi, level_of(name))
    if name.startswith("es"):
        return es_(sigma, xi, level_of(name))
    raise ValueError(name)


def level_of(name: str) -> float:
    """'var975' -> 0.975, 'es99' -> 0.99, 'var999' -> 0.999, 'var95' -> 0.95."""
    digits = "".join(ch for ch in name if ch.isdigit())
    return float("0." + digits)


def grad_functional(name: str, phi, kind: str, xi_max: float = 0.45) -> np.ndarray:
    """Gradient of a functional with respect to phi (central differences)."""
    phi = np.asarray(phi, float)
    out = np.zeros(2)
    for k in range(2):
        h = 1e-5 * max(1.0, abs(phi[k]))
        if kind in ("logsd_xi", "eta_xi") and k == 1:
            h = min(h, 0.25 * phi[1])
        e = np.zeros(2)
        e[k] = h
        fp = functional(name, canon_from(phi + e, kind, xi_max))
        fm = functional(name, canon_from(phi - e, kind, xi_max))
        out[k] = (fp - fm) / (2 * h)
    return out


# ----------------------------------------------------------------------------------------
# expected scores under a t distribution (closed form)
# ----------------------------------------------------------------------------------------
def _upper_partial(c, nu):
    """E[(T - c)^+] for T ~ t_nu."""
    with np.errstate(invalid="ignore", over="ignore"):
        return (nu + c**2) / (nu - 1) * stats.t.pdf(c, nu) - c * stats.t.sf(c, nu)


def _lower_partial(c, nu):
    """E[(c - T)^+] for T ~ t_nu."""
    return c * stats.t.cdf(c, nu) + (nu + c**2) / (nu - 1) * stats.t.pdf(c, nu)


def expected_pinball(v, alpha, sigma, xi, mu=0.0):
    """E[rho_alpha(L - v)] for loss L = -mu + sigma T (quantile score of a VaR report v)."""
    nu = 1.0 / np.asarray(xi)
    c = (np.asarray(v) + mu) / sigma
    return sigma * _upper_partial(c, nu) + (1 - alpha) * (np.asarray(v) + mu)


def pinball_regret(v, alpha, sigma, xi, mu=0.0):
    """Expected quantile-score regret of reporting VaR v instead of the true VaR."""
    q0 = var_(sigma, xi, alpha, mu)
    return expected_pinball(v, alpha, sigma, xi, mu) - expected_pinball(q0, alpha, sigma, xi, mu)


def expected_fz0(var_l, es_l, alpha, sigma, xi, mu=0.0):
    """Expected FZ0 score (Patton, Ziegel & Chen 2019) of a loss-scale (VaR, ES) report.

    Uses return-scale v = -VaR, e = -ES (< 0) and tail probability a = 1 - alpha.
    """
    nu = 1.0 / np.asarray(xi)
    a = 1 - alpha
    v = -np.asarray(var_l, float)
    e = -np.asarray(es_l, float)
    c = (v - mu) / sigma
    lp = sigma * _lower_partial(c, nu)
    return -lp / (a * e) + v / e + np.log(-e) - 1


def fz0_regret(var_l, es_l, alpha, sigma, xi, mu=0.0):
    """Expected FZ0 regret of a (VaR, ES) report relative to the true pair."""
    v0 = var_(sigma, xi, alpha, mu)
    e0 = es_(sigma, xi, alpha, mu)
    return expected_fz0(var_l, es_l, alpha, sigma, xi, mu) - expected_fz0(
        v0, e0, alpha, sigma, xi, mu
    )


def pinball_curvature(alpha, sigma, xi, mu=0.0):
    """Second derivative of the expected quantile score at the optimum = density at VaR."""
    q = stats.t.ppf(alpha, 1.0 / xi)
    return stats.t.pdf(q, 1.0 / xi) / sigma


def fz0_curvature(alpha, sigma, xi, mu=0.0):
    """Hessian of the expected FZ0 score in loss-scale (VaR, ES) at the optimum."""
    nu = 1.0 / xi
    a = 1 - alpha
    e0 = es_(sigma, xi, alpha, mu)
    f_at = stats.t.pdf(stats.t.ppf(alpha, nu), nu) / sigma
    # return scale: d2/dv2 = -f/(a e), d2/de2 = 1/e^2 with e = -ES < 0; sign flips cancel
    return np.diag([f_at / (a * e0), 1.0 / e0**2])


# ----------------------------------------------------------------------------------------
# predictive (mixture) functionals — the Bayes acts under consistent scoring functions
# ----------------------------------------------------------------------------------------
def compress(canon: np.ndarray, w: np.ndarray, mass: float = 1 - 1e-7, max_pts: int = 6000):
    """Drop negligible-weight support points of a weighted posterior."""
    w = w / w.sum()
    order = np.argsort(w)[::-1]
    cum = np.cumsum(w[order])
    k = min(int(np.searchsorted(cum, mass)) + 1, max_pts, w.size)
    idx = order[:k]
    return canon[idx], w[idx] / w[idx].sum()


def predictive_var(canon: np.ndarray, w: np.ndarray, alpha: float, mu: float = 0.0) -> float:
    """VaR of the posterior predictive (mixture of t's) by bisection."""
    sigma, xi = canon[:, 0], canon[:, 1]
    nu = 1.0 / xi
    qs = var_(sigma, xi, alpha, mu)
    lo, hi = float(np.min(qs)) - 1e-9, float(np.max(qs)) + 1e-9
    for _ in range(70):
        mid = 0.5 * (lo + hi)
        cdf = np.sum(w * special.stdtr(nu, (mid + mu) / sigma))
        if cdf < alpha:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return 0.5 * (lo + hi)


def predictive_es(canon: np.ndarray, w: np.ndarray, alpha: float, mu: float = 0.0) -> float:
    """ES of the posterior predictive (mixture of t's)."""
    sigma, xi = canon[:, 0], canon[:, 1]
    nu = 1.0 / xi
    v = predictive_var(canon, w, alpha, mu)
    c = (v + mu) / sigma
    tail = sigma * (nu + c**2) / (nu - 1) * stats.t.pdf(c, nu) - mu * stats.t.sf(c, nu)
    return float(np.sum(w * tail) / (1 - alpha))


def predictive_logpdf(y: np.ndarray, canon: np.ndarray, w: np.ndarray, mu: float = 0.0):
    """Log density of the posterior predictive at points y."""
    sigma, xi = canon[:, 0], canon[:, 1]
    lp = logpdf_std((y[:, None] - mu) / sigma[None, :], 1.0 / xi[None, :]) - np.log(sigma)[None, :]
    lp = lp + np.log(w)[None, :]
    m = lp.max(axis=1, keepdims=True)
    return (m + np.log(np.exp(lp - m).sum(axis=1, keepdims=True))).ravel()


def kl_truth_to_predictive(canon: np.ndarray, w: np.ndarray, sigma0: float, xi0: float, n_y=801):
    """KL(p_true || posterior predictive) = expected log-score regret, by quadrature."""
    sd0 = sd_of(sigma0, xi0)
    t = np.linspace(-9.0, 9.0, n_y)
    y = sd0 * np.sinh(t)
    dy = sd0 * np.cosh(t) * (t[1] - t[0])
    lp0 = logpdf_std(y / sigma0, 1.0 / xi0) - np.log(sigma0)
    lpp = predictive_logpdf(y, canon, w)
    return float(np.sum(np.exp(lp0) * (lp0 - lpp) * dy))
