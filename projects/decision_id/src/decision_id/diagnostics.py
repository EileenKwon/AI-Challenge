"""Identifiability / decision-sensitivity diagnostics.

Notation: Itot = total Fisher information (n * I_1) in some coordinates, g = gradient of a
functional in the same coordinates, P = reference (prior) precision in the same coordinates.

  eigen_scores      : user-proposed Fisher eigen-heuristic (coordinate DEPENDENT)
  ridge_rg          : R_g(lambda) = g^T (Itot + lambda Id)^{-1} g (invariant only for lambda=0)
  whitened_decomp   : generalized eigenproblem Itot v = lam P v (invariant), giving
                        V_prior = sum s_j^2, V_post = sum s_j^2/(1+lam_j),
                        S2      = sum s_j^2/(1+lam_j)^2  (worst-case prior-mean sensitivity)
                        pi_g    = S2 / V_post           (prior-dominance ratio)
  value_of_source   : Laplace (Gaussian-linear) reduction in functional variance from
                      adding a data source with Fisher information Ie  (Bayesian c-optimality)
"""

from __future__ import annotations

import numpy as np
from scipy import linalg


def eigen_scores(Itot: np.ndarray, g: np.ndarray) -> dict:
    """Fisher eigen-decomposition with per-direction sensitivity |v_j^T g|.

    Returns eigenvalues (ascending), sensitivities, the weakest-direction score
    |v_min^T g| / sqrt(lam_min) and its share of R_g(0).
    """
    lam, V = np.linalg.eigh(Itot)
    sens = np.abs(V.T @ g)
    contrib = sens**2 / lam
    return {
        "lam": lam,
        "sens": sens,
        "weak_score": float(sens[0] / np.sqrt(lam[0])),
        "weak_share": float(contrib[0] / contrib.sum()),
        "cond": float(lam[-1] / lam[0]),
        "angle_weak_deg": float(np.degrees(np.arccos(min(1.0, sens[0] / np.linalg.norm(g))))),
    }


def ridge_rg(Itot: np.ndarray, g: np.ndarray, lam: float) -> float:
    """R_g(lambda) = g^T (Itot + lambda Id)^{-1} g."""
    return float(g @ np.linalg.solve(Itot + lam * np.eye(len(g)), g))


def whitened_decomp(Itot: np.ndarray, P: np.ndarray, g: np.ndarray) -> dict:
    """Prior-whitened generalized eigen-decomposition of functional uncertainty.

    Solves Itot v = lam P v with v^T P v = 1. Then s_j = v_j^T g and
      V_prior = sum s^2, V_post = sum s^2/(1+lam), S2 = sum s^2/(1+lam)^2, pi = S2/V_post.
    All quantities are invariant under (linear / locally linearized) reparameterization when
    P transforms as a metric tensor.
    """
    lam, V = linalg.eigh(Itot, P)  # V^T P V = I
    s = V.T @ g
    v_prior = float(np.sum(s**2))
    contrib = s**2 / (1 + lam)
    v_post = float(contrib.sum())
    s2 = float(np.sum(s**2 / (1 + lam) ** 2))
    return {
        "lam": lam,
        "s": s,
        "contrib": contrib,
        "v_prior": v_prior,
        "v_post": v_post,
        "s2": s2,
        "pi": s2 / max(v_post, 1e-300),
        "contraction": v_post / max(v_prior, 1e-300),
        "alloc_priority": s**2 / (1 + lam) ** 2,
    }


def value_of_source(Sigma: np.ndarray, Ie: np.ndarray, G: np.ndarray, K: np.ndarray) -> float:
    """Decision-weighted Laplace value: 0.5 tr(K G^T (Sigma - (Sigma^-1 + Ie)^-1) G).

    G: (d, k) gradients of k functionals; K: (k, k) curvature of the expected score.
    """
    Sig_new = np.linalg.inv(np.linalg.inv(Sigma) + Ie)
    D = Sigma - Sig_new
    return float(0.5 * np.trace(K @ G.T @ D @ G))


def dopt_value(Sigma: np.ndarray, Ie: np.ndarray) -> float:
    """D-optimal (Fisher-only) gain: log det(Sigma^-1 + Ie) - log det(Sigma^-1)."""
    A = np.linalg.inv(Sigma)
    return float(np.linalg.slogdet(A + Ie)[1] - np.linalg.slogdet(A)[1])


def predictive_value(Sigma: np.ndarray, Ie: np.ndarray, Ipred: np.ndarray) -> float:
    """Predictive (log-score) gain: 0.5 tr(Ipred (Sigma - Sigma_new)).

    0.5 tr(Ipred Sigma) is the second-order expected KL regret of the predictive density for
    a future observation with Fisher information Ipred; it is functional-blind.
    """
    Sig_new = np.linalg.inv(np.linalg.inv(Sigma) + Ie)
    return float(0.5 * np.trace(Ipred @ (Sigma - Sig_new)))


def exact_prior_sensitivity(phi: np.ndarray, w: np.ndarray, gvals: np.ndarray, P: np.ndarray):
    """Global analogue of S_g: sup_{|z|=1} Cov_post(g, z^T L^T phi), P = L L^T.

    This is the exact local sensitivity of the posterior mean of g to exponential tilting of
    the prior along prior-whitened linear directions (equals S_g in the Gaussian-linear case).
    """
    w = w / w.sum()
    gm = w @ gvals
    pm = w @ phi
    cov_pg = ((phi - pm) * (w * (gvals - gm))[:, None]).sum(axis=0)
    L = np.linalg.cholesky(P)
    return float(np.linalg.norm(L.T @ cov_pg))
