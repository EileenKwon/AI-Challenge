# 05 — Failure analysis and publishability assessment

## Verdict (short)

**No publishable *methodological* contribution exists in the form proposed.**

* The Fisher-eigen "weak × sensitive" diagnostic and $R_g(\lambda)$ are either known or ill-defined:
  * $R_g(0)$ is the delta method / Cramér–Rao bound.
  * $R_g(\lambda)$ is Bayesian c-optimality under a coordinate-specific prior.
  * The invariant repair is the goal-oriented prior-whitened decomposition (Spantini et al. 2017).
  * The eigen split itself is coordinate-dependent (it moves from 0.5% to 54% for the same data).
* The allocation rule is goal-oriented Bayesian experimental design.
* Empirically, the allocation rule beats a functional-blind Fisher-only (D-optimal) design by a modest
  13–17% regret reduction for VaR targets. This holds pooled over six seed/design runs; single runs are
  underpowered. For the joint (VaR, ES) target the gain is ≈3%.
* Its global (preposterior) version is indistinguishable from the cheap local version in these models.

**What does exist** is a coherent *applied / expository* contribution on **tail-index estimation risk in
VaR/ES decisions**, with a few clean results that we did not find stated elsewhere. It suits a risk or
forecasting journal (*J. Risk*, *J. Risk Model Validation*, *Int. J. Forecasting*, a *Quantitative
Finance* note). It is not a JASA/AoS/NeurIPS methods paper unless one of the extensions in §5 succeeds.

## 0. Statistical status of the key claims (details: `06_significance_robustness.md`)

| claim | status after Holm-adjusted tests and robustness re-runs |
|---|---|
| tail-index recovery matters little for VaR95/97.5 and a lot for VaR99.9 (H2) | **significant** (contrast p = 2e-6, 20 cells). Robust to inference method (MLE, Laplace) and to swapping the prior |
| Fisher-eigen split is coordinate-dependent (H3) | **proven** (identity), and large in practice |
| local diagnostics add (almost) nothing beyond the exact functional variance (H4) | partial ρ ≈ +0.08–0.11. **Small, but significant for the whitened local variance** (Holm p = 0.044). Parameter-only metrics are significantly worse |
| π_g best predicts decision prior sensitivity (H4b) | beats posterior variance (p = 0.012). **Not distinguishable from the contraction ratio** (p = 0.52) |
| no approximation beats the exact posterior when truth ~ prior (E3b) | 0/30 better, 10/30 significantly worse |
| decision-targeted allocation beats D-opt (H5) | single run: significant only for VaR97.5 (0.83, Holm p = 0.03; MCS excludes D-opt). **Pooled over 6 independent seed/design runs (secondary analysis): VaR97.5 0.865 (p = 5e-7), VaR99.9 0.828 (p = 1e-10), 6/6 runs < 1; FZ0 0.97 (fragile, Wilcoxon n.s.).** Which target reaches significance in a single run is not stable |
| preposterior beats local allocation (H6) | **rejected**: n.s. in all targets. In the confirmatory run (32 simulations), 97% of final allocations are identical; the earlier disagreements were Monte Carlo noise |
| exact posterior intervals are reliable | true under the default prior. **Not robust to a prior that conflicts with the truth on ξ** (VaR99.9 coverage 0.37 at n = 100, ν = 3; MLE 0.80) |
| finite backtests | Kupiec over-rejects for *all* methods (15–34%). Diebold–Mariano reproduces the population-regret ordering with low power |

## 1. The central question

*Are statistically identifiable parameters necessarily the most important for decisions?* **No**, and
the project quantifies it:

| evidence | result |
|---|---|
| E2 (Gaussian) | μ has 145% median relative error at n = 250 yet contributes 27% of VaR99 uncertainty; it is 99% of portfolio-weight uncertainty, and the weight's regret exceeds the optimal CE gain (×2.1) |
| E3 H2 | tail-index error vs regret: ρ = 0.07 (VaR95), 0.21 (VaR97.5), 0.76 (VaR99.9) |
| E3 H4 | parameter-identifiability metrics (posterior sd(ξ), tr Cov, λ_min Fisher) predict the realized decision error worse than functional-specific variance (pooled ρ 0.47–0.51 vs 0.61) and have negative partial correlations |
| E4 | a grossly wrong parameter posterior (Laplace ellipse outside the support, L-shaped exact posterior) yields the same VaR99 decision regret to three digits |
| E5 | the regret-best allocation for VaR97.5 has *worse* tail-index recovery and *worse* log score than D-opt |
| E3/E3b | at a fixed truth, cruder approximations can beat the exact posterior on regret (prior–truth mismatch on the weak direction); averaged over the prior they cannot (E3b) |

## 2. Critical requirements

1. **No optimization on backtests.** Every decision is scored by closed-form population regret under the
   known DGP. Finite backtests are reported only as a check (Spearman 0.70 with population regret, means
   agree). No method was tuned on outcomes. All E3–E5 hypotheses were written down before those runs.
2. **Physical vs risk-neutral.** All functionals are physical-measure (return-distribution) quantities.
   No option-implied or risk-neutral parameter is used. Peer data are physical-measure returns.
3. **Beyond posterior variance propagation?**
   * For *predicting the decision error*: no. Partial ρ ≈ 0.05–0.11 given the exact functional variance.
   * For *prior sensitivity of the decision*: slightly. The whitened $\pi_g$ is the best predictor (ρ 0.89
     within cell, 0.75 pooled) but only marginally ahead of the plain contraction ratio
     $V_{\rm post}/V_{\rm prior}$ (0.88 / 0.70).
   * For *allocation*: yes, but this is exactly what goal-oriented design already uses.
4. **Reparameterization.**
   * Proven: Propositions 1–3, unit tests.
   * Measured: E1, E3 §4.
   * Only $R_g(0)$, generalized eigenvalues with a pulled-back metric, and the regret-weighted criteria
     are invariant.
   * Laplace and mean-field VI are coordinate-dependent and visibly so. Laplace in (log sd, ξ) puts up to
     20% of its draws outside the support. Mean-field VI covers 63–74% for tail functionals even at
     n = 2500.
5. **Local vs global.**
   * Local SD / exact SD at n = 100 is 0.52 (variance), 0.68 (VaR99.9) and 0.90 (VaR95). It reaches
     ≥ 0.97 at n = 2500.
   * The ξ = 0 boundary traps the MLE in 25–46% of light-tailed short samples.
   * Near singular loci (E4, analogous to weakly identified GARCH) local intervals cover 0.36–0.49 on
     hard datasets versus 0.54 exact. True multimodality was rare (≤ 2%); mass on singular loci was the
     dominant global pathology.

## 3. Failure analysis of the proposed method

| component | failure | evidence |
|---|---|---|
| Fisher-eigen identifiability_j = λ_j | not coordinate-free; changes with units and correlation structure | Prop. 2; E1 table; E3 §4 (median range 0.43–0.78) |
| decision_sensitivity_j = \|v_jᵀ∇g\| | same problem; its "weak share" is nearly useless as a failure predictor | E3 §3 (pooled ρ 0.25–0.35 vs 0.61) |
| $R_g(\lambda>0)$ | equals a posterior variance only for one coordinate-specific prior; changes ×1.05–5.4 across coordinates | Prop. 1; E3 §4 |
| local diagnostics in general | underestimate uncertainty for tail/moment functionals in short samples, at boundaries and near singular loci | E3 §7, §9; E4 |
| decision-targeted allocation (local) | myopic one-batch criterion. Gains over D-opt are modest (13–17% for VaR, ≈3% for FZ0) and need about 2,000 paired replications to establish; individual conditions can favour D-opt (VaR99.9 at ν = 3, n₀ = 100) | E5, R1 §2.3 |
| preposterior EVSI | ~150× the cost, no gain. With 32 simulations it reproduces the local choice in 97% of cases | E5 H6, R1 §2.4 |
| exact Bayesian intervals under a conflicting prior | VaR99.9 coverage 0.37 (n = 100, ν = 3) when ξ ~ HalfNormal(0.1); prior-free Wald 0.80 | R1 §2.1 |
| decision gains at a fixed truth | can reverse with the truth because the prior on the weak direction matters; a claim must be averaged over the prior or over a truth grid | E3 vs E3b |
| design dependence | E5 gains depend on the chosen costs and sources. Own-history-only looks 4–9× worse than uniform because the variance proxy is cheap by design | E5 setup |

## 4. What *is* new or at least not found stated (candidate contributions)

1. **Tail-index-immune risk levels (Proposition 5).**
   * At fixed variance, near the Gaussian limit, VaR$_\alpha$ is first-order immune to the tail index
     exactly at $\alpha^*=\Phi(\sqrt3)=0.958$ and ES$_\alpha$ at $\Phi(1)=0.841$.
   * The immune level rises with tail heaviness (VaR: 0.969 at ν = 10, 0.987 at ν = 4, 0.995 at ν = 3).
   * Weir's 97.5% "invariance" is a global compromise. Basel's ES97.5 is never near its immune level.
   * Caveat: for ν ≤ 4 the variance is not data-identified, so the relevant weak direction is the
     likelihood ridge, not "fixed variance".
   * Likely folklore in Cornish–Fisher circles; not found stated in this form.
2. **Regret compression across levels.** Under the quantile score, the posterior variance of VaR grows
   ~500× from α = 0.90 to 0.999, but expected regret grows only ~2.3× because the density at the
   quantile falls. Allocation and model-validation effort aimed at extreme quantiles is therefore worth
   much less, in proper-score units, than variance-based reasoning suggests.
3. **Log-score blindness to weakly identified directions.** Log-score (KL) regret weights directions by
   $\lambda_j/(1+\lambda_j)$, and its information-gain criterion is largest for intermediately identified
   directions. Tail functionals load on directions with large $R_g$ per unit KL. Predictive-uncertainty
   allocation is therefore misaligned with tail decisions in both directions. In E5 it over-buys tail
   information for the scale-dominated VaR97.5 target.
4. **$\pi_g$ as a prior-sensitivity index for decisions.** The identity "worst-case prior-mean
   sensitivity / posterior variance = $\sum c_j/(1+\lambda_j)/\sum c_j$" unifies local robustness with the
   "weak × sensitive" intuition. Empirically it is only marginally better than the contraction ratio.
5. **A sober result on allocation.** In low-dimensional financial risk models, decision-targeted
   allocation beats a functional-blind D-optimal design by 13–17% for VaR targets. The gain is robust
   across seeds and cost designs, but it needs ~2,000 paired replications to detect, and it is ≈3% for
   the joint (VaR, ES) target. Global preposterior evaluation reproduces the local choice (97%
   agreement) despite non-Gaussian posteriors. This is what goal-oriented design theory predicts, not a
   new phenomenon.

Items 1–3 combined with E1/E3 would make a solid applied paper ("Which risk measures are robust to
tail-index estimation risk, and where should the next data come from?"). Items 4–5 are supporting
material.

## 5. What would be needed for a methods paper

* **A regime where global beats local.** Singular-locus models such as GARCH with α → 0, regime
  mixtures with rare crises, or SV with weakly identified persistence, under *non-myopic* (batch or
  multi-step) decision-targeted design. E4 shows local intervals failing there. E5's boundary-only
  non-Gaussianity was not enough to separate preposterior from local allocation.
* **Goal-chosen integration subspace in higher dimensions.** This is the one gap found in the novelty
  check: an INLA/LIS-type hybrid whose exactly integrated subspace is chosen by regret-weighted functional
  relevance, tested where exact integration is costly (multi-asset t-copula, SV with latent states). It
  could not be evaluated meaningfully in 2-parameter models.
* **Simulation-budget allocation for amortized inference (NPE).** Not studied here. A proposal
  concentrating simulations where the regret-weighted functional is sensitive *and* the NPE is uncertain
  would have to be compared with sequential NPE and truncated proposals.
* **Real data.** A rolling out-of-sample study with peer pooling of the tail index (e.g., equity
  cross-sections) to check that the synthetic source model (unit-variance peer residuals, Gamma variance
  proxies) is not doing the work.

## 6. Limitations of this study

* Location fixed at 0 in the Student-t experiments (the 3-parameter case was not run).
* No GARCH/SV model; the regime mixture stands in for singular-locus weak identification.
* Synthetic, stylized data sources. Fixed priors (one alternative prior for sensitivity).
* 60–100 replications per cell. Preposterior EVSI with 12 simulations.
* NPE with a Gaussian head only. A flow or mixture head would fit the banana posteriors better.
* The torch-based NPE was not possible in this environment.
