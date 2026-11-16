"""Tests for the statistical-inference utilities."""

import numpy as np

from decision_id import stats as st


def test_holm_and_bh_known_values():
    p = np.array([0.01, 0.04, 0.03, 0.20])
    assert np.allclose(st.holm(p), [0.04, 0.09, 0.09, 0.20])
    assert np.allclose(st.bh(p), [0.04, 0.0533333, 0.0533333, 0.20])


def test_wilson_contains_truth_and_binomial():
    lo, hi = st.wilson(90, 100)
    assert lo < 0.9 < hi
    assert st.binom_two_sided(90, 100, 0.9) > 0.5


def test_dm_matches_t_for_iid_and_detects_difference():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 1, 4000)
    b = a + rng.normal(0.1, 1, 4000)
    s, p = st.dm_test(a, b)
    assert s < 0 and p < 1e-6
    s0, p0 = st.dm_test(a, a + rng.normal(0, 1, 4000))
    assert p0 > 0.001


def test_kupiec_nominal_not_rejected():
    rng = np.random.default_rng(1)
    exc = rng.uniform(size=20000) < 0.01
    assert st.kupiec_pof(exc, 0.01)[1] > 0.01
    assert st.kupiec_pof(rng.uniform(size=20000) < 0.02, 0.01)[1] < 1e-6


def test_mcs_eliminates_worse_models():
    rng = np.random.default_rng(2)
    base = rng.normal(1, 0.2, (400, 1))
    L = np.hstack([base, base + 0.001 * rng.normal(size=(400, 1)), base + 0.3])
    surv, pv = st.mcs(L, ["a", "b", "bad"], alpha=0.1, rng=rng)
    assert "bad" not in surv and pv["bad"] < 0.1


def test_paired_tests_and_cluster_t():
    rng = np.random.default_rng(3)
    a = rng.exponential(1, 300)
    b = a * 1.2
    r = st.paired_tests(a, b, rng)
    assert r["mean_diff"] < 0 and r["p_wilcoxon"] < 1e-6 and r["ci_hi"] < 0
    out = st.cluster_t(rng.normal(0.5, 1, 200), np.repeat(np.arange(20), 10))
    assert out["n_clusters"] == 20 and out["p"] < 0.01
