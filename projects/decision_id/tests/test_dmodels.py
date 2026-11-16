"""Design models: exact preposterior updates, PSD local information, engine runs."""

import numpy as np
import pytest

from decision_id import adaptive as ad
from decision_id import dmodels as dm
from decision_id.utils import load_config

CFG = load_config()


def _models():
    return {
        "t": (dm.TDesign(CFG), "nu6", "var999"),
        "mix": (dm.MixDesign(), "rare", "var99"),
        "garch": (dm.GarchDesign(), "weak", "qlike10"),
        "sv": (dm.SVDesign(), "weak", "var99"),
    }


@pytest.mark.parametrize("name", ["mix", "garch", "sv"])
def test_update_lw_matches_refit_on_same_nodes(name):
    model, truth, _ = _models()[name]
    rng = np.random.default_rng(0)
    s = model.init_state(rng, truth, stages=2)
    post = model.fit(s)
    for src in model.sources:
        s2 = model.consume(s, src)
        y = s2["data"][src][-1] if src == "peer" else s2["data"][src][len(s["data"][src]) :]
        upd = model.update_lw(src, y, post, s)
        direct = model._lw(post.phi, s2["data"])
        direct = direct[0] if isinstance(direct, tuple) else direct
        diff = upd - direct
        ok = np.isfinite(diff)
        assert ok.mean() > 0.99
        assert np.ptp(diff[ok]) < 1e-6 * max(1.0, np.abs(direct[ok]).max())


@pytest.mark.parametrize("name", ["t", "mix", "garch", "sv"])
def test_local_info_psd_regret_nonnegative_and_run(name):
    model, truth, target = _models()[name]
    rng = np.random.default_rng(1)
    s = model.init_state(rng, truth, stages=2)
    post = model.fit(s)
    m, _ = post.moments()
    for src in model.sources:
        info = model.local_info(src, m, post, s, rng)
        assert np.all(np.linalg.eigvalsh(info) >= -1e-9)
    ev = ad.target_eval(model, target, post, post.w, s)
    assert ev["evpi"] >= -1e-10
    assert ad.truth_regret(model, target, ev["act"], s) >= -1e-10
    out = ad.run_policy(model, "adapt", target, s, rng, n_stages=2, n_sims=3, log_both=True)
    assert np.isfinite(out["regret"]) and len(out["logs"]) == 2
