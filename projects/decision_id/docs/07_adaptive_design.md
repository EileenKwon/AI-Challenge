# 07 — Failure-triggered adaptive goal-oriented design (Stage 3, revised)

## Why this direction

After E1–E6 and the significance work (docs 04–06), three findings stood:

* **Negative.** The Fisher-based diagnostic carries almost no information beyond posterior variance
  propagation.
* **Positive.** Functional-specific allocation beats uniform and information-only (D-optimal)
  allocation.
* **Open.** In non-regular financial models where cheap local criteria may fail, when should the
  expensive global computation be paid for?

An important correction: the earlier "decision-targeted local" policy **is Bayesian c-optimal design**.
For a scalar functional the score curvature K only rescales the criterion. Beating D-optimality
therefore proves nothing new. The relevant bar is twofold:

* beat **local Bayesian c-optimal design**;
* match **always-global Bayesian design** (preposterior expected value of sample information, or the
  exact preposterior variance of g) at a fraction of its cost.

## Method

At every stage t of a multi-stage allocation:

1. Refit the grid posterior on all data acquired so far (posterior-preserving; nothing is reweighted by
   the decision).
2. **Local criterion.** Compute the Bayesian c-optimal score of each source e:
   $c_e=\nabla g^\top[\Sigma-(\Sigma^{-1}+I_e)^{-1}]\nabla g$. Here $\Sigma$ is the posterior covariance
   and $I_e$ is the expected information of one batch: closed form, or Monte Carlo observed information
   for GARCH/SV.
3. **Failure-risk indicators.** Both cost almost nothing beyond the local criterion.
   * **Approximation error proxy:** $\kappa_t=|\log(\mathrm{Var}_{\pi_t}(g)/\nabla g^\top\Sigma\nabla g)|$,
     the discrepancy between the exact posterior variance of g and its delta-method value.
   * **Decision fragility:** the relative margin $m_t=(c_{(1)}-c_{(2)})/c_{(1)}$ between the best and
     second-best sources.
4. **Gate.** If $\kappa_t>\tau_\kappa$ or $m_t<\tau_m$, compute the global decision-theoretic criterion
   and pick its maximizer:
   $$\mathrm{EVSI}_e=\mathrm{EVPI}(\pi_t)-E_{y_e\sim p(\cdot\mid\mathcal D_t)}\,\mathrm{EVPI}(\pi_t(\cdot\mid y_e)).$$
   It is evaluated with K exact grid updates. Otherwise take the local choice.
5. **Thresholds.** Either pre-specified, $(\tau_\kappa,\tau_m)=(\log 1.25,\,0.10)$, or **calibrated on
   separate calibration seeds**: the smallest firing rate with ≥ 80% recall of stages where the local
   and global choices disagree. One pooled threshold is used for all models.

**Proposition 6 (when the local choice is safe).** Let $L_e$ and $G_e$ be local and global scores on a
common scale. For a scalar g with fixed curvature, the local EVSI is $\tfrac12K c_e$. Suppose
$|L_e-G_e|\le\delta\,L_{(1)}$ for all e. If the local relative margin satisfies $m>2\delta$, then
$\arg\max_eL_e=\arg\max_eG_e$.

*Proof.* For any $e\ne e^*=\arg\max L$:
$G_{e^*}-G_e\ge L_{e^*}-L_e-2\delta L_{(1)}\ge(m-2\delta)L_{(1)}>0$. $\square$

The gate is the empirical version of this. κ is a proxy for the unknown approximation error δ
(heuristic: κ measures non-Gaussianity of g's posterior, not the error of the preposterior criterion
itself). The margin is exactly the quantity the proposition needs. Consequently:

* the adaptive policy's regret differs from always-global regret only at stages where the gate misses
  a disagreement;
* the per-stage loss is bounded by that stage's EVSI gap.

A tighter, assumption-free bound would need a model of δ as a function of κ. That is not available
(see Limitations).

## Baselines (equal data budget)

| policy | type | source |
|---|---|---|
| uniform | none | — |
| dopt | Bayesian D-optimal, local | Chaloner & Verdinelli (1995) |
| **copt** | **Bayesian c-optimal, goal-oriented, local** | Chaloner (1984); Attia et al. (2018) |
| copt_global | goal-oriented Bayesian design with exact preposterior variance of g | in the spirit of nonlinear goal-oriented BOED (Zhong et al. 2024) |
| evsi_global | decision-theoretic Bayesian design (always global) | Lindley (1956); Chaloner & Verdinelli (1995) |
| adapt | proposed, pre-specified thresholds | — |
| adapt_cal | proposed, thresholds calibrated out-of-sample | — |

## Models and sources

| model | non-regularity | sources (cost per batch = 50) | targets |
|---|---|---|---|
| Student-t (control) | none (regular) | own returns / peer tail residuals / variance proxies | VaR99.9 |
| calm/crisis mixture | p → 0 leaves s₂ unidentified; s₂ → s₁ leaves p unidentified | own returns / crisis-episode returns (s₂ only) / regime labels (p only) | VaR99, VaR99.9 |
| GARCH(1,1)-t6, variance targeting | α → 0 leaves β unidentified (Andrews & Cheng 2012; Ma, Nelson & Startz 2007) | realized variance m=10 (50 days) / realized variance m=50 (12 days) / peer asset sharing (α, β) (250 days) | 1-day VaR99 (quantile score), 10-day variance (QLIKE) |
| SV, log-AR(1) | σ_η → 0 leaves φ unidentified | log realized variance, noise sd 0.5 or 0.2 / peer asset sharing (φ, σ_η) | 1-day VaR99 |

SV uses the Harvey–Ruiz–Shephard QML Kalman quasi-likelihood. Its "posterior" is therefore a
generalized (quasi-) posterior, labelled as such. Regret is still computed against the true SV data
generating process, using the true latent volatility.

## Prior art (novelty check for this step)

Every ingredient exists:

* Laplace-based expected information gain: Long et al. (2013); Laplace importance sampling: Beck et al.
  (2018); multi-fidelity expected information gain: Coons & Huan (2025).
* Comparisons of Laplace vs nested MC: Englezou, Waite & Woods (2022).
* Laplace failure in multimodal posteriors: Long (2022).
* Linearized c-optimality failing for nonlinear goals: Neuberger, Alexanderian & van Bloemen Waanders
  (2025, quadratic G_q).
* Diagnose-then-escalate inference: PSIS k-hat (Yao et al. 2018).
* Value of computation: Russell & Wefald (1991); Hay et al. (2012).
* Laplace-based sequential design: Senarathne, Drovandi & McGree (2020).

What was **not found**:

* (i) a per-stage gate in sequential Bayesian design that decides whether to pay for a global
  criterion, rather than fusing fidelities;
* (ii) a gate combining an approximation-error proxy with decision fragility (margin);
* (iii) Bayesian design for data acquisition in weakly identified GARCH / SV / regime models with a VaR
  target.

Expected reviewer objections, which the experiment must answer:

* "engineering combination" unless calibration evidence and a regret analysis are given;
* missing comparisons with a quadratic (G_q) middle fidelity and with a pure value-of-computation gate.
  The margin-only gate is analysed below; G_q was not implemented.

<!-- E7RESULTS -->
