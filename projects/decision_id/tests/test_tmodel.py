"""Correctness tests for the Student-t model: Fisher information, functionals, scores."""

import numpy as np
import pytest
from scipy import integrate, stats

from decision_id import tmodel as tm
from decision_id.utils import num_grad


def _mc_fisher(sigma, xi, n=400_000, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.standard_t(1 / xi, size=n)
    x = sigma * z

    def ll(p):
        return tm.logpdf_std(x / p[0], 1 / p[1]) - np.log(p[0])

    h = np.array([1e-5 * sigma, 1e-6])
    s1 = (ll([sigma + h[0], xi]) - ll([sigma - h[0], xi])) / (2 * h[0])
    s2 = (ll([sigma, xi + h[1]]) - ll([sigma, xi - h[1]])) / (2 * h[1])
    S = np.stack([s1, s2])
    return S @ S.T / n


@pytest.mark.parametrize("xi", [0.1, 0.25, 0.33])
def test_fisher_closed_form_matches_monte_carlo(xi):
    I_cf = tm.fisher_sigma_xi(1.3, xi)
    I_mc = _mc_fisher(1.3, xi)
    assert np.allclose(I_cf, I_mc, rtol=0.06, atol=0.02)


def test_fisher_gaussian_limit():
    I0 = tm.fisher_sigma_xi(1.0, 1e-5)
    assert np.allclose(I0, [[2, 2], [2, 3.5]], atol=0.02)
    # (log sd, xi) is orthogonal at the Gaussian limit
    Iu = tm.fisher(np.array([0.0, 1e-4]), "logsd_xi")
    assert abs(Iu[0, 1]) < 0.02 and abs(Iu[1, 1] - 1.5) < 0.05


def test_functionals_match_monte_carlo():
    rng = np.random.default_rng(1)
    sigma, xi = 0.8, 0.25
    L = -sigma * rng.standard_t(1 / xi, size=2_000_000)
    for a in (0.95, 0.99):
        q = np.quantile(L, a)
        assert abs(tm.var_(sigma, xi, a) - q) / q < 0.01
        es_mc = L[q <= L].mean()
        assert abs(tm.es_(sigma, xi, a) - es_mc) / es_mc < 0.02
    assert abs(tm.variance_(sigma, xi) - L.var()) / L.var() < 0.05


def test_pinball_and_fz0_minimized_at_truth():
    sigma, xi, a = 1.1, 0.2, 0.975
    v0, e0 = tm.var_(sigma, xi, a), tm.es_(sigma, xi, a)
    vs = v0 + np.linspace(-0.5, 0.5, 41)
    reg = tm.pinball_regret(vs, a, sigma, xi)
    assert np.all(reg >= -1e-12) and abs(reg[20]) < 1e-12
    for dv, de in [(0.1, 0), (-0.1, 0), (0, 0.2), (0, -0.2), (0.1, 0.1)]:
        assert tm.fz0_regret(v0 + dv, e0 + de, a, sigma, xi) > 0


def test_expected_pinball_matches_integral():
    sigma, xi, a, v = 1.0, 0.25, 0.99, 2.5
    nu = 1 / xi

    def integrand(loss):
        return (loss - v) * (a - (loss < v)) * stats.t.pdf(loss / sigma, nu) / sigma

    val = integrate.quad(integrand, -60, v)[0] + integrate.quad(integrand, v, 400)[0]
    assert abs(val - tm.expected_pinball(v, a, sigma, xi)) < 1e-4


def test_curvatures_match_numeric_hessian():
    sigma, xi, a = 1.0, 0.2, 0.975
    v0, e0 = tm.var_(sigma, xi, a), tm.es_(sigma, xi, a)
    h = 1e-3
    d2 = (
        tm.expected_pinball(v0 + h, a, sigma, xi)
        - 2 * tm.expected_pinball(v0, a, sigma, xi)
        + tm.expected_pinball(v0 - h, a, sigma, xi)
    ) / h**2
    assert abs(d2 - tm.pinball_curvature(a, sigma, xi)) < 1e-3
    K = tm.fz0_curvature(a, sigma, xi)

    def f(p):
        return float(tm.expected_fz0(p[0], p[1], a, sigma, xi))

    g = num_grad(f, np.array([v0, e0]))
    assert np.allclose(g, 0, atol=1e-5)
    from decision_id.utils import num_hess

    H = num_hess(f, np.array([v0, e0]), rel=1e-3)
    assert np.allclose(H, K, rtol=0.02, atol=1e-4)


def test_parameterization_roundtrip():
    canon = np.array([[0.9, 0.3], [1.2, 0.01]])
    for kind in tm.PARAMS:
        back = tm.canon_from(tm.phi_from(canon, kind), kind)
        assert np.allclose(back, canon)


def test_predictive_functionals_reduce_to_plugin_for_point_mass():
    canon = np.array([[1.0, 0.25]])
    w = np.ones(1)
    assert abs(tm.predictive_var(canon, w, 0.99) - tm.var_(1.0, 0.25, 0.99)) < 1e-8
    assert abs(tm.predictive_es(canon, w, 0.975) - tm.es_(1.0, 0.25, 0.975)) < 1e-6
    assert abs(tm.kl_truth_to_predictive(canon, w, 1.0, 0.25)) < 1e-6


def test_tail_index_immune_levels_at_gaussian_limit():
    """Proposition 5: at fixed variance and xi -> 0, VaR is immune at Phi(sqrt 3), ES at Phi(1)."""
    from scipy import optimize

    xi, h = 1e-3, 1e-6

    def unit(f, a, x):
        return f(np.sqrt(1 - 2 * x), x, a)

    def d(f, a):
        return (unit(f, a, xi + h) - unit(f, a, xi - h)) / (2 * h)

    a_var = optimize.brentq(lambda a: d(tm.var_, a), 0.9, 0.999)
    a_es = optimize.brentq(lambda a: d(tm.es_, a), 0.6, 0.99)
    assert abs(a_var - stats.norm.cdf(np.sqrt(3))) < 2e-3
    assert abs(a_es - stats.norm.cdf(1.0)) < 2e-3
