"""Tests for diagnostics: invariance properties and Gaussian-linear identities."""

import numpy as np

from decision_id import diagnostics as dg
from decision_id import tmodel as tm
from decision_id.utils import num_jac


def _setup(kind, n=500):
    canon0 = np.array([0.8, 0.25])
    phi = tm.phi_from(canon0, kind)
    Itot = n * tm.fisher(phi, kind)
    g = tm.grad_functional("var99", phi, kind)
    return phi, Itot, g


def test_rg_lambda0_is_reparameterization_invariant():
    vals = [dg.ridge_rg(*_setup(k)[1:], 0.0) for k in tm.PARAMS]
    assert np.allclose(vals, vals[0], rtol=1e-4)


def test_ridge_and_eigen_scores_are_not_invariant():
    ridge = [dg.ridge_rg(*_setup(k)[1:], 50.0) for k in ("logsd_xi", "eta_xi", "sigma_nu")]
    weak = [
        dg.eigen_scores(*_setup(k)[1:])["weak_share"] for k in ("logsd_xi", "eta_xi", "sigma_nu")
    ]
    assert np.ptp(ridge) / np.mean(ridge) > 0.05
    assert np.ptp(weak) > 0.05


def test_whitened_decomposition_invariant_with_pulled_back_metric():
    P_ref = np.diag([1.0, 1 / (0.45**2 / 12)])  # metric in (log sd, xi)
    out = []
    for kind in ("logsd_xi", "eta_xi", "sigma_nu", "u"):
        phi, Itot, g = _setup(kind)
        # J = d(logsd, xi)/d(phi) at the point; pull back P_ref
        J = num_jac(lambda p, k=kind: tm.phi_from(tm.canon_from(p, k), "logsd_xi"), phi)
        P = J.T @ P_ref @ J
        d = dg.whitened_decomp(Itot, P, g)
        out.append([d["v_prior"], d["v_post"], d["s2"], d["pi"]])
    out = np.array(out)
    assert np.allclose(out, out[0], rtol=1e-3)


def test_whitened_identities_gaussian_linear():
    rng = np.random.default_rng(0)
    A = rng.normal(size=(3, 3))
    Itot = A @ A.T + 0.1 * np.eye(3)
    B = rng.normal(size=(3, 3))
    P = B @ B.T + 0.5 * np.eye(3)
    g = rng.normal(size=3)
    d = dg.whitened_decomp(Itot, P, g)
    Sig = np.linalg.inv(Itot + P)
    assert np.isclose(d["v_post"], g @ Sig @ g)
    assert np.isclose(d["v_prior"], g @ np.linalg.solve(P, g))
    # S2 equals the worst-case shift of the posterior mean of g per unit prior-sd shift
    L = np.linalg.cholesky(P)
    sens_vec = L.T @ Sig @ g  # d E[g] / d z where m -> m + L^{-T} z
    assert np.isclose(d["s2"], sens_vec @ sens_vec)
    # and the marginal variance reduction from adding eps * P information
    eps = 1e-6
    Sig2 = np.linalg.inv(Itot + (1 + eps) * P)
    assert np.isclose((g @ Sig @ g - g @ Sig2 @ g) / eps, d["s2"], rtol=1e-4)


def test_value_of_source_rank_one_sherman_morrison():
    rng = np.random.default_rng(1)
    A = rng.normal(size=(2, 2))
    Sig = A @ A.T + 0.2 * np.eye(2)
    a = rng.normal(size=2)
    g = rng.normal(size=2)
    v = dg.value_of_source(Sig, np.outer(a, a), g[:, None], np.array([[2.0]]))
    expected = 0.5 * 2.0 * (a @ Sig @ g) ** 2 / (1 + a @ Sig @ a)
    assert np.isclose(v, expected)


def test_exact_prior_sensitivity_matches_local_for_gaussian_posterior():
    rng = np.random.default_rng(2)
    Sig = np.array([[0.04, 0.01], [0.01, 0.02]])
    phi = rng.multivariate_normal([0, 0], Sig, size=200_000)
    g = np.array([1.0, -2.0])
    gv = phi @ g
    P = np.diag([4.0, 9.0])
    exact = dg.exact_prior_sensitivity(phi, np.ones(len(phi)), gv, P)
    L = np.linalg.cholesky(P)
    local = np.linalg.norm(L.T @ Sig @ g)
    assert abs(exact - local) / local < 0.02
