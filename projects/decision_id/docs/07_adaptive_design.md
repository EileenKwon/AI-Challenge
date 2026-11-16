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

## Results (E7; full tables in `reports/e7_adaptive.md`, `reports/e7b_noise.md`)

**Setup.** 11 cells (model × truth × target), 30 evaluation replications each, 6 stages, equal data
budget, K = 16 preposterior simulations. All policies share data pools and state-determined random
numbers. Thresholds were calibrated on 110 separate calibration replications. Regret is normalized by
the cell's c-opt mean and pooled per model; 95% intervals are paired bootstrap; Holm is applied over
P1 and P4 (8 tests).

### Pre-declared comparisons

| model | P1 adapt_cal / copt | P2 adapt_cal / evsi_global (non-inferior if upper CI < 1.10) | P3 CPU adapt_cal / evsi_global | P4 evsi_global / copt |
|---|---|---|---|---|
| Student-t (control) | 1.13 [0.89, 1.65], n.s. | 1.00 [1.00, 1.00] ✓ | 0.85 | 1.13 [0.89, 1.65], n.s. |
| regime mixture | 0.99 [0.94, 1.05], n.s. | 1.00 [0.98, 1.03] ✓ | 0.50 | 0.99 [0.94, 1.05], n.s. |
| GARCH(1,1)-t6 | 1.02 [0.83, 1.23], n.s. | 0.93 [0.81, 1.04] ✓ | 0.82 | 1.09 [0.86, 1.38], n.s. |
| SV (QML) | **1.90 [1.28, 3.06]**, p = 0.017 (Holm 0.12) | 0.89 [0.71, 1.07] ✓ | 0.69 | **2.13 [1.38, 3.40]**, p = 0.007 (Holm 0.055) |

### Secondary comparisons and the MCS

| model | uniform / copt | D-opt / copt | global c-opt / copt | MCS (90%) |
|---|---|---|---|---|
| Student-t | 1.26, n.s. | 1.22, n.s. | 0.97, n.s. | all 7 |
| mixture | **1.71, p = 7e-4** | 1.02 | 0.99 | all except uniform |
| GARCH | **1.38, p = 0.013** | 0.84, n.s. | 1.08 | all except uniform |
| SV | 0.75, n.s. | 1.86, p = 0.04 | 2.10, p = 0.009 | {uniform, copt} |

### By cell: global EVSI / copt

* **GARCH weak / 10-day variance (QLIKE): 0.74**, p = 0.12. This is the only cell where global
  design looks helpful.
* GARCH regular cells: 1.18–1.32.
* SV regular: **2.96**, p = 0.014. SV weak: 1.29, n.s.

### Trigger diagnostics

These are measured out-of-sample, on the evaluation logs of the always-global run. "Disagreement"
means the local c-opt and global EVSI choices differ.

| model | disagreement rate | AUC κ | AUC margin | calibrated gate: firing rate / recall |
|---|---|---|---|---|
| Student-t | 7% | 0.41 | **0.86** | 0.86 / 1.00 |
| mixture | 9% | 0.53 | **0.88** | 0.38 / 0.87 |
| GARCH | 33% | 0.58 | 0.57 | 0.77 / 0.82 |
| SV | 47% | 0.44 | 0.56 | 0.65 / 0.71 |

* Calibration set the κ threshold to ∞: **the approximation-error proxy carries no information about
  when the global choice differs**.
* The decision margin is informative where disagreements are rare (t, mixture), but not in GARCH/SV.

### Monte Carlo noise of the global criterion (E7b)

| model | K=16 vs K=16 | K=16 vs K=64 | local vs K=64 |
|---|---|---|---|
| Student-t | 0% | 0% | 0% |
| mixture | 12.5% | 6% | 8% |
| GARCH | 21% | 15% | 33% |
| SV | 25% | 21% | 42% |

In GARCH/SV the local choice differs from the reference global choice more often than the noisy global
choice differs from itself. These disagreements are therefore partly systematic, not only noise.

## Interpretation

1. **The premise did not hold.** Always-global Bayesian design (EVSI or exact preposterior variance of g)
   never beat local Bayesian c-optimal design significantly in any model:
   * Student-t and mixture: indistinguishable.
   * GARCH: heterogeneous. It helps only in the weakly identified, persistence-sensitive cell (0.74,
     n.s.) and is worse in the regular cells.
   * SV: **significantly worse** (×2.1).

   A gate can only interpolate between c-opt and always-global, so the adaptive design could not beat
   c-opt (P1). It did match always-global regret (P2) at 15–50% lower CPU (P3). That is a saving on a
   computation that was not worth paying for in the first place.
2. **Why global hurt in SV: working-model misspecification.** The SV posterior is a QML quasi-posterior.
   The preposterior simulations (FFBS under the QML Gaussian approximation) and the exact
   quasi-posterior updates take the misspecified working model at face value.
   * Global policies bought more noisy realized variance (4.3 of 6 batches) and fewer peer series (0.8,
     versus 1.7 for c-opt).
   * Uniform allocation, which buys 2 peer series, had the lowest SV regret.

   "Exact global computation" is only as good as the likelihood it is exact for. The cheap local
   criterion relies less on the working model's details, which made it more robust here.
3. **What predicts a changed decision is fragility, not non-Gaussianity.**
   * κ (non-Gaussianity of g's posterior) is large in every non-regular model, but it does not predict
     where the global choice differs (AUC 0.41–0.58).
   * The margin between the two best sources does predict it where disagreements are genuine and rare
     (AUC 0.86–0.88).
   * In GARCH/SV, disagreements mix systematic working-model effects with K = 16 Monte Carlo noise, and
     neither indicator separates them.
4. **Refined open problem.** "When should one pay for global inference?" turns out to have three
   separate requirements:
   * (a) a well-specified likelihood, so the preposterior is trustworthy;
   * (b) enough Monte Carlo precision to resolve near-ties. Many disagreements are between nearly
     equivalent sources, where regret consequences are small;
   * (c) a target that depends on the weakly identified direction non-locally. Only the GARCH
     weak-ID / 10-day variance cell showed this, and only as a non-significant trend.

## Limitations of E7

* **Power.** 30 replications per cell detect only large effects. The GARCH weak/QLIKE trend (−26%)
  needs a confirmatory run.
* **Myopia and precision.** K = 16 and a myopic one-batch criterion. Non-myopic (multi-step) planning
  was not tried.
* **Fixed model components.** GARCH innovation df fixed at 6; SV only through QML. A particle-filter SV
  likelihood would remove the misspecification confound.
* **Missing comparisons.** No quadratic (G_q) middle fidelity; no regret bound beyond Proposition 6.

## Verdict on this step

The failure-triggered adaptive design is **not** a demonstrated methodological advance. In four
financial models it neither beats Bayesian c-optimal design nor needs to. The useful outputs are
negative and diagnostic:

* local Bayesian c-optimal design is a strong, cheap baseline in non-regular financial models;
* global preposterior design can hurt under quasi-likelihoods;
* posterior non-Gaussianity is the wrong trigger; decision fragility is the right quantity, but it is
  confounded by Monte Carlo noise.

These results narrow where a positive result could still be found: correctly specified latent-variable
likelihoods (particle-filter SV, GARCH with estimated tails), persistence-sensitive multi-horizon
targets, and non-myopic designs with variance-controlled preposterior estimators.
