# 04 — Results (E1–E6)

All numbers come from `reports/*.md`, which the scripts in `experiments/` regenerate. Regret is always
the **population out-of-sample** expected score regret of the Bayes act under the true DGP: the
quantile score for VaR, FZ0 for (VaR, ES), and certainty equivalent for the portfolio weight.

## E1 — First experiment (2-parameter Student-t, ν = 4)

Figures: `figures/e1_contours_n250.png`, `e1_contours_n1000.png`, `e1_functional_posteriors.png`,
`e1_spectrum.png`.

* **Geometry.**
  * In $(\log\mathrm{sd},\xi)$ the posterior is a curved banana that runs toward larger sd and heavier
    tails.
  * The likelihood contours (dashed) are the same function in every panel. The HPD regions and the MAP
    are not: they are densities and move under reparameterization.
  * The Fisher eigenvectors at the MLE point in visibly different directions in the three panels.
* **Functional loading on the weak direction.** This is the share of the posterior variance of $g$ coming
  from the weakest prior-whitened direction (n = 250), checked against the exact posterior Sobol index of
  $\xi$:

  | functional | VaR95 | VaR97.5 | VaR99 | VaR99.9 | ES97.5 | ES99 | variance |
  |---|---|---|---|---|---|---|---|
  | whitened weak share | 0.18 | 0.47 | 0.74 | 0.94 | 0.84 | 0.91 | 0.81 |
  | exact Sobol(ξ) | 0.12 | 0.42 | 0.70 | 0.92 | 0.82 | 0.89 | 0.87 |
  | Fisher-eigen weak share, (log sd, ξ) / (log σ, ξ) / (σ, ν) | 0.54/0.00/0.20 | 0.84/0.07/0.50 | 0.98/0.25/0.76 | 0.99/0.51/0.94 | 1.00/0.36/0.85 | 1.00/0.45/0.91 | 0.99/0.33/0.82 |

  The invariant decomposition agrees with the exact global attribution. The user-proposed Fisher-eigen
  split can say "VaR95 is 54% weak-direction-driven" or "0.5%" depending only on the coordinates.
* **Tail-index-immune level.**
  * The relative sensitivity $\partial\log\mathrm{VaR}_\alpha/\partial\xi$ at fixed sd changes sign at
    α ≈ 0.987 for ν = 4. For ES it changes sign at α ≈ 0.94.
  * The analytic Gaussian-limit values are $\Phi(\sqrt3)=0.958$ for VaR and $\Phi(1)=0.841$ for ES
    (Proposition 5).
  * Because sd is itself poorly identified at ν = 4, the data-identified weak direction is not the
    fixed-sd direction. The functional least exposed to it is a *body* quantile (α ≈ 0.90), not 97.5%.
* **Variance vs regret.** From α = 0.90 to 0.999 the posterior variance of VaR grows **514×** (n = 250),
  but the quantile-score regret proxy $\tfrac12 f(q)\mathrm{Var}$ grows only **2.3×**, peaking near
  α ≈ 0.998. Under a proper quantile score, extreme-tail estimation error is heavily discounted.
* **Local vs exact.** The delta-method SD agrees with the exact posterior SD within ±6% for all
  quantiles and ES. It is too small by 31% for the **variance** functional (n = 250).

## E2 — Gaussian, exact conjugate posterior

* **Correctness.** Exact, Laplace, MCMC, mean-field VI and MLE-Wald all give 85–96% coverage of 90%
  intervals for every functional and n. Approximations are trustworthy in the orthogonal Gaussian model.
* **Decoupling.** At n = 250:

  | quantity | value |
  |---|---|
  | median relative error of μ | **145%** |
  | median relative error of VaR99 | 3.6% |
  | portfolio-weight CE regret / optimal CE | **2.1** (worse than holding cash) |

  The share of the delta-method variance due to μ is 27% for VaR99/ES97.5 and 99% for the portfolio
  weight. The poorly recovered parameter (μ) barely matters for VaR, and it is everything for the
  portfolio decision. This reproduces the known estimation-risk result (Merton 1980; Kan & Zhou 2007).

## E3 — Replicated Student-t study (20 cells × 100 replications, 7 methods)

**H2 (parameter recovery vs decisions): supported.** Within-cell Spearman correlation between
|ξ error| and regret:

| functional | VaR95 | VaR97.5 | VaR99 | VaR99.9 | ES97.5 | ES99 |
|---|---|---|---|---|---|---|
| ρ(\|ξ error\|, regret) | 0.07 | 0.21 | 0.46 | **0.76** | 0.45 | 0.58 |
| ρ(\|log sd error\|, regret) | 0.70 | **0.88** | 0.84 | 0.62 | 0.92 | 0.82 |

Better recovery of the weakly identified tail index buys almost nothing for VaR95/97.5. Scale recovery
dominates there. Tail recovery drives VaR99.9 regret. `figures/e3_param_vs_decision.png` shows the
contrast.

**H1 (fragility depends on (ν, n) and on what the data identify): supported.** Weak-direction share at
n = 1000:

| ν | VaR95 | VaR97.5 | VaR99.9 | variance |
|---|---|---|---|---|
| 3 | 0.24 | 0.55 | 0.96 | 0.89 |
| 10 | 0.01 | 0.19 | 0.87 | 0.12 |
| 50 | 0.00 | 0.09 | 0.81 | 0.01 |

**H3 (reparameterization): supported.**

* The Fisher-eigen weak share differs across the three coordinate systems by a median of 0.43–0.78 for
  the same dataset. For VaR97.5 the medians are 0.79 / 0.03 / 0.29.
* $R_g(\lambda=10)$ changes by a median factor of 1.05 (VaR95) to 5.4 (VaR99.9) across coordinates.
* The whitened $\pi_g$ is identical across coordinates (ratio 1.000).

**H4 (does the diagnostic add information beyond posterior variance?): mostly supported.** These are
Spearman correlations with the realized squared relative error of the exact Bayes act:

| diagnostic | within cell | partial, given exact Var(g) | pooled over cells & functionals |
|---|---|---|---|
| exact posterior Var(g) | 0.23 | 0 | 0.61 |
| $R_g(0)$ at MLE (delta) | 0.25 | 0.08 | 0.60 |
| whitened local $V_{\rm post}$ | 0.26 | 0.11 | 0.61 |
| Fisher-eigen weak-direction term, by coordinates | 0.21–0.24 | 0.05–0.07 | 0.52–0.57 |
| Fisher-eigen weak *share* | 0.06–0.20 | −0.11–0.02 | 0.25–0.35 |
| parameter-only: post. sd(ξ), tr Cov, −λ_min(Fisher) | 0.06–0.21 | −0.21 to −0.02 | 0.47–0.51 |

* Functional-specific measures beat parameter-identifiability measures.
* The eigen "weak share" is nearly useless as a risk predictor.
* Local delta quantities carry a small residual signal (partial ρ ≈ 0.1) but no material gain over the
  exact functional posterior variance.

**H4b (prior sensitivity): partly supported.** Correlation with |Bayes act under alt prior − default| /
posterior sd(g):

| predictor | within cell | pooled |
|---|---|---|
| whitened local $\pi_g$ | **0.89** | **0.75** |
| contraction $V_{\rm post}/V_{\rm prior}$ | 0.88 | 0.70 |
| exact Var(g) (relative) | 0.79 | 0.70 |
| exact $\pi_g$ (tilting) | 0.55 | 0.73 |
| posterior sd(ξ) | 0.38 | 0.47 |

$\pi_g$ is the best single predictor of decision prior-sensitivity, but only marginally better than the
simpler posterior-to-prior contraction ratio. This is the one place where the decomposition adds
information that posterior variance does not.

**Coverage of 90% intervals (averaged over ν):**

* grid ≈ MCMC ≈ 0.89–0.93.
* Laplace in u: 0.86–0.91. Laplace in (log sd, ξ): 0.82–0.91. Its Gaussian draws leave the support for
  up to 20% of draws at n = 100, and the MLE sits on the ξ = 0 boundary in 25–46% of light-tailed short
  samples.
* Full-rank VI: 0.84–0.93.
* **Mean-field VI: 0.63–0.74 for VaR99.9/ES97.5 even at n = 2500.** The (log sd, ξ) posterior
  correlation is ignored.
* MLE-Wald: 0.85–0.91.
* The local SD / exact SD ratio at n = 100 is 0.52 (variance), 0.68 (VaR99.9), 0.70 (ES99) and 0.90
  (VaR95). It reaches ≥ 0.97 at n = 2500.

**Posterior accuracy ≠ decision quality.** The regret of Bayes acts relative to the exact posterior
depends on the truth. At n = 100:

| approximation | ν = 3 | ν = 6–50 |
|---|---|---|
| Laplace-u | 1.22× worse | 0.58–0.88× (lower regret) |
| plug-in MLE | 2.7× worse (VaR99.9) | 0.27× at ν = 50 (it sits on the Gaussian boundary, which is near the truth) |

The exact posterior is optimal on average over the prior, not at each fixed truth. Its predictive is
pulled toward heavier tails by the uniform prior on ξ. E3b checks this explanation.

**Distribution shift** (ν × 0.6, scale × 1.3): the exact posterior has the lowest regret.

| method | regret relative to exact, n = 100 | at n = 2500 |
|---|---|---|
| Laplace / VI-MF | 1.13–1.31× | ≈ 1.01× |
| MLE | 1.24–1.28× | ≈ 1.01× |

Integrating parameter uncertainty buys robustness to heavier-tailed shifts.

**Out-of-sample checks.** A finite 5,000-day backtest regret correlates with the population regret
(Spearman 0.70), and the two agree in mean (e.g. 0.000754 vs 0.000800 at n = 100). The predictive
log-score regret (KL) barely separates methods except MLE and Laplace-nat at n = 100.

## E3b — Sanity check: truths drawn from the prior

The tail index was drawn as ξ₀ ~ U(0, 0.45), 300 replications per n. Mean regret relative to the
exact Bayes act, with 90% paired-bootstrap intervals:

| method | n = 100 | n = 250 |
|---|---|---|
| plug-in MLE | 1.26–1.59 (all CIs > 1) | 1.18–1.30 (all > 1) |
| Laplace in (log sd, ξ) | 1.19–1.21 (> 1) | 1.08–1.23 (> 1) |
| Laplace in u | 1.03–1.12 | 1.03–1.12 (ES97.5 CI > 1) |
| mean-field VI | 1.01–1.12 | 1.03–1.10 |
| full-rank VI | 0.98–1.00 (CI ∋ 1) | 1.00–1.02 (CI ∋ 1) |

When the truth is drawn from the prior, no approximation beats the exact posterior, as decision theory
requires. The E3 "approximation wins" were a frequentist fixed-truth effect of prior–truth mismatch,
not evidence that cruder posteriors give better decisions. The lesson for the research question:
**decision quality at a particular truth is driven by the prior on the weakly identified direction at
least as much as by approximation accuracy.**

## E4 — Near-redundant regime mixture (local vs global)

`figures/e4_mixture_example.png`

* **Dataset mix.** The posterior hugs the two singular loci in an L-shape. 9.5% of n = 250 datasets
  are "hard" (singular-locus mass > 5% or > 1 mode); at n = 1000 it is 0.5%. True multimodality is rare
  (2% / 0.5%). The dominant global pathology is mass on singular loci, not separated modes.
* **Coverage of 90% intervals at n = 250:**

  | functional | exact | Laplace-delta | MLE-Wald |
  |---|---|---|---|
  | VaR99.9 | 0.94 | 0.80 | 0.80 |
  | ES97.5 | 0.91 | 0.84 | 0.83 |

  On hard datasets: exact 0.54, Laplace-delta 0.36, Laplace push-forward 0.49, Wald 0.38. Local SD /
  exact SD is 0.70 (VaR99.9) and 0.77 (ES97.5) at n = 250, and 0.89–0.94 at n = 1000.
* **Decisions.** The VaR99 Bayes-act regret is identical to three digits for exact, Laplace push-forward
  and MLE (0.000638 / 0.000639 / 0.000667). A badly wrong parameter posterior and under-covering
  functional intervals still gave the same decision, because the predictive quantile is insensitive to
  the mass the local approximation misplaces.

## E6 — Standard NPE (Gaussian head, numpy MLP)

* **Setup.** 40,000 prior-predictive simulations, 9 summary statistics. Simulation plus training takes
  about 6 s per n; inference takes 0.6 ms per dataset, against 0.2–0.9 s for the grid.
* **Coverage.** NPE intervals are 2–12% wider and over-cover (0.93–0.975 vs 0.88–0.93 exact at
  n = 250). They are close to nominal at n = 1000.
* **Decisions.** Bayes-act regret is within about ±10% of the exact posterior. KL is within 1–7%.
* Simulation-budget allocation for NPE was **not** studied (see `05_assessment.md`).

## E5 — Decision-targeted observation allocation (Stages 3–4)

**Setup.**

* Six conditions: ν ∈ {3, 5, 10} × n₀ ∈ {100, 400}; 60 replications each.
* Budget: 8 batches × cost 50. Per batch that buys 50 own returns, 200 peer standardized residuals
  (these carry information about ξ only), or 100 noisy variance proxies (log sd only).
* All policies share the same data pools (common random numbers).
* Regret is measured for the final Bayes act under the true DGP.
* Pooled ratio = mean regret / uniform, with 90% paired-bootstrap CI. `figures/e5_regret_ratio.png`.

| target | own_only | predictive (log score) | D-opt (Fisher-only) | DR-local | DR-preposterior |
|---|---|---|---|---|---|
| VaR97.5 (quantile score) | 4.14 [3.54, 4.88] | 0.82 [0.73, 0.93] | 0.66 [0.57, 0.76] | 0.54 [0.46, 0.63] | **0.52 [0.45, 0.60]** |
| (VaR, ES)97.5 (FZ0) | 5.72 | 0.81 [0.73, 0.90] | 0.67 [0.59, 0.75] | **0.64 [0.57, 0.72]** | 0.64 [0.57, 0.72] |
| VaR99.9 (quantile score) | 8.91 | 0.82 [0.73, 0.91] | 0.83 [0.74, 0.94] | **0.76 [0.67, 0.86]** | 0.76 [0.67, 0.85] |

**Head-to-head against D-opt** (DR rarely chooses the same sequence: 1–17% of replications):

| target | win / loss | mean-regret ratio when sequences differ |
|---|---|---|
| VaR97.5 | 44–46% / 35–37% | 0.79–0.83 |
| VaR99.9 | 44–45% / 44% | 0.85 |
| FZ0 | 28–30% / 23–24% | 0.96 |

By condition, DR loses to D-opt for VaR99.9 at (ν = 3, n₀ = 100) (0.78 vs 0.61) and at
(ν = 5, n₀ = 400). It wins clearly at ν = 10.

**Source mix** (batches out of 8, own/peer/rv):

| policy | own | peer | rv |
|---|---|---|---|
| DR for VaR97.5 | 0 | 1.6 | 6.4 |
| DR for VaR99.9 | 0 | 5.3 | 2.7 |
| DR for FZ0 | 0 | 2.9 | 5.1 |
| D-opt | 0 | 3.4 | 4.6 |
| predictive | 0.1 | 5.0 | 2.9 |

The allocation moves with the functional's sensitivity, as the theory says. VaR97.5 is scale-dominated;
VaR99.9 is tail-dominated.

**What the policies give up.**

* DR-VaR97.5 has worse ξ recovery (|ξ error| 0.026 vs 0.018 for D-opt) and a worse log score (KL 0.0011
  vs 0.0007), yet lower VaR97.5 regret. This is a direct instance of "better parameter recovery ≠ better
  decisions".
* The predictive (log-score) criterion over-buys tail information for the scale-dominated target.

**H5: partly supported.**

* Decision-targeted allocation clearly beats uniform, own-history-only and predictive allocation.
* Against Fisher-only D-optimal design it is clearly better only for VaR97.5. It is a tie for FZ0 and
  inconclusive for VaR99.9.

**H6: not supported.**

* Preposterior / local regret ratios lie in 0.84–1.06; every 90% CI except one contains 1.
* The suggestive cell is ν = 3, n₀ = 100, VaR97.5: 0.84 [0.65, 1.01].
* The preposterior EVSI costs about 20 s per replicate versus 0.1–0.2 s for the local criterion
  (≈ 150×).
