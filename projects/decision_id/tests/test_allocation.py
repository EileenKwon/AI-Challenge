"""Allocation sources: Fisher information matches simulation; criteria behave sensibly."""

import numpy as np

from decision_id import allocation as al
from decision_id import posterior as po
from decision_id import tmodel as tm
from decision_id.utils import load_config

CFG = load_config()


def test_rv_fisher_matches_simulation():
    rng = np.random.default_rng(0)
    m, logsd = 5, 0.1
    y = al.simulate_source(rng, "rv", 200_000, np.exp(logsd) * np.sqrt(1 - 0.4), 0.2, m)
    # score of log sd for Gamma(m/2, 2 sd^2 / m): -m + y m / sd^2
    sd2 = np.exp(2 * logsd)
    score = -m + y * m / sd2
    assert abs(score.var() - 2 * m) / (2 * m) < 0.03


def test_peer_source_informs_only_xi():
    info = al.fisher_source("peer", np.array([0.0, 0.2]), 5, 0.45)
    assert info[0, 0] == 0 and info[0, 1] == 0 and info[1, 1] > 0


def test_fit_posterior_concentrates_with_more_data():
    rng = np.random.default_rng(1)
    prior = po.prior_from_cfg(CFG)
    xi0, s0 = 0.2, np.sqrt(0.6)
    d1 = al.Data(own=tm.sample(rng, 200, s0, xi0))
    d2 = al.Data(
        own=d1.own,
        peer=al.simulate_source(rng, "peer", 2000, s0, xi0, 5),
        rv=al.simulate_source(rng, "rv", 500, s0, xi0, 5),
    )
    _, c1 = al.fit_posterior(d1, prior, 5)[0].moments()
    _, c2 = al.fit_posterior(d2, prior, 5)[0].moments()
    assert c2[0, 0] < c1[0, 0] / 4 and c2[1, 1] < c1[1, 1] / 2
