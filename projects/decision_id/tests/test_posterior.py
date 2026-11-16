"""Posterior approximations agree with the grid reference where they should."""

import numpy as np

from decision_id import posterior as po
from decision_id import tmodel as tm
from decision_id.utils import load_config

CFG = load_config()


def _data(n=800, xi=0.25, seed=3):
    rng = np.random.default_rng(seed)
    return tm.sample(rng, n, sigma=np.sqrt(1 - 2 * xi), xi=xi)


def test_grid_mass_and_mcmc_agreement():
    x = _data()
    prior = po.prior_from_cfg(CFG)
    post, grid = po.grid_posterior(x, prior, CFG["student_t"])
    assert post.info["edge_mass"] < 1e-6
    assert np.isclose(post.w.sum(), 1.0)
    rng = np.random.default_rng(0)
    mc = po.mcmc_rwm(x, prior, rng, iters=12000, burn=3000)
    for name in ("var975", "var99", "es975"):
        a, b = post.summary(name), mc.summary(name)
        assert abs(a["mean"] - b["mean"]) < 0.25 * a["sd"] + 1e-3
        assert abs(a["sd"] - b["sd"]) / a["sd"] < 0.25


def test_laplace_and_vi_close_to_grid_for_long_sample():
    x = _data(n=2500, seed=5)
    prior = po.prior_from_cfg(CFG)
    post, grid = po.grid_posterior(x, prior, CFG["student_t"])
    rng = np.random.default_rng(1)
    lap = po.laplace(x, prior, "u", rng, 4000)
    vi = po.vi_gaussian(grid, prior, True, rng, 4000)
    g = post.summary("var99")
    for approx in (lap, vi):
        s = approx.summary("var99")
        assert abs(s["mean"] - g["mean"]) < 0.3 * g["sd"]
        assert abs(s["sd"] - g["sd"]) / g["sd"] < 0.2


def test_grid_weights_account_for_nonuniform_xi_axis():
    # flat likelihood (no data) => xi marginal equals the uniform prior
    prior = po.prior_from_cfg(CFG)
    g = po.grid_from_axes(
        np.linspace(-3, 3, 61), po._xi_axis(CFG["student_t"]), np.array([]), prior
    )
    w = g.weights().reshape(g.logpost.shape).sum(axis=0)
    mean_xi = w @ g.xi
    assert abs(mean_xi - prior.xi_max / 2) < 0.01


def test_npe_gaussian_head_gradient():
    from decision_id import npe

    rng = np.random.default_rng(0)
    o = rng.normal(size=(4, 5))
    U = rng.normal(size=(4, 2))
    nll, go = npe.GaussNPE._nll_grad(o, U)
    eps = 1e-6
    num = np.zeros_like(o)
    for i in range(4):
        for j in range(5):
            op, om = o.copy(), o.copy()
            op[i, j] += eps
            om[i, j] -= eps
            fp = npe.GaussNPE._nll_grad(op, U)[0][i]
            fm = npe.GaussNPE._nll_grad(om, U)[0][i]
            num[i, j] = (fp - fm) / (2 * eps)
    assert np.allclose(num, go, rtol=1e-5, atol=1e-5)
