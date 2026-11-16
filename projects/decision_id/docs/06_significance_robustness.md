# 06 — Statistical significance and robustness

Full tables: `reports/s1_significance.md` (tests on all original results; every individual test is in
`results/s1_tests.csv`) and `reports/r1_robustness.md` (re-runs).

## Standards used (following the literature)

| practice | source | applied to |
|---|---|---|
| Monte Carlo standard errors for every performance measure; ADEMP-style reporting | Morris, White & Crowther (2019), *Stat. Med.* 38:2074 | all coverage / regret / exceedance numbers |
| exact binomial tests and Wilson intervals for coverage | standard | E2, E3 |
| paired tests on per-replicate losses under common random numbers: paired t (≡ Diebold–Mariano with iid replicates), Wilcoxon signed-rank, paired bootstrap CI | Diebold & Mariano (1995), *JBES* 13:253 | E3, E3b, E4, E5, E6 |
| Diebold–Mariano with Newey–West HAC on out-of-sample loss series for fixed estimated models | Diebold & Mariano (1995); Giacomini & White (2006), *Econometrica* 74:1545 | R1 §4 |
| Kupiec proportion-of-failures VaR backtest | Kupiec (1995), *J. Derivatives* 3:73 | R1 §4; E3 (exact population version) |
| Model Confidence Set (T_max, bootstrap) | Hansen, Lunde & Nason (2011), *Econometrica* 79:453 | E5 policies |
| comparative backtesting of (VaR, ES) with the FZ0 score | Fissler, Ziegel & Gneiting (2016); Nolde & Ziegel (2017), *Ann. Appl. Stat.* 11:1833 | R1 §4 |
| McNemar tests for paired binary outcomes | standard | E4, E6 coverage |
| cluster-level inference: cells (n × ν, independent seeds) as units for correlation hypotheses | standard | H2, H4, H4b |
| multiplicity: Holm within pre-declared families (BH also reported) | Holm (1979); Benjamini & Hochberg (1995) | all families |

## 1. Significance of the original findings

| claim | test | result |
|---|---|---|
| **H2** ξ-recovery error correlates with regret, weakly for VaR95 and strongly for VaR99.9 | cell-level t (20 cells), Holm over 6 functionals; Wilcoxon over cells for the contrast | all 6 ρ > 0 significant (VaR95: ρ = 0.066 ± 0.024, p = 0.007; VaR99.9: 0.757 ± 0.025, p = 6e-18). **Contrast VaR99.9 − VaR95 = 0.69, p = 2e-6.** Same pattern with MLE and Laplace errors (prior-free / approximate) |
| H2 contrast for VaR97.5: scale recovery matters more than tail recovery | Wilcoxon over cells | significant (Holm < 0.05) |
| **H4** local diagnostics add nothing beyond exact Var(g) | cell-level t of within-cell partial ρ, Holm over 10 diagnostics | whitened local $V_{\rm post}$: +0.11 ± 0.035 (Holm p = 0.044). $R_g(0)$: +0.075 (Holm p = 0.07). Eigen terms: n.s. Parameter-only metrics are **significantly negative** (post. sd(ξ): −0.21, Holm p = 0.001). The added signal is small but not exactly zero |
| functional-specific variance beats parameter-only metrics | cell-level t of ρ differences | significant for post. sd(ξ) and tr Cov (2 of 3, Holm) |
| **H4b** π_g best predicts prior sensitivity | cell-level t of ρ differences, Holm over 4 | beats exact Var(g) (+0.097, Holm p = 0.012), exact tilting π (p = 0.012) and sd(ξ) (p = 0.002). **Does not beat the contraction ratio $V_{\rm post}/V_{\rm prior}$ (+0.004 ± 0.006, p = 0.52).** |
| E3 coverage | exact binomial vs 0.90, Holm over 112 cells | 21/112 cells significantly off nominal: mean-field VI 14, Laplace (log sd, ξ) 4, MLE 2, full-rank VI 1. **Grid, MCMC and Laplace-u: none** |
| E3 VaR99 exceedance probability $P(L>\widehat{\mathrm{VaR}}\mid\theta_0)$ (exact Kupiec-type) | t-test vs 0.01 | MLE and Laplace-nat over-exceed (1.18%, 1.17% at n = 100, p < 1e-5). The exact posterior is conservative at n = 100 (0.92%). All methods are within ±0.02 pp of nominal by n = 2500 |
| **E3b** no approximation beats the exact posterior when truths come from the prior | paired t, Holm over 30 | 10/30 significantly *worse* (MLE, Laplace-nat, Laplace-u for ES at n = 100). **0/30 significantly better** |
| E4 local intervals under-cover near singular loci | McNemar, Holm over 24 | significant only for VaR99.9 at n = 250 (Laplace-delta / push / Wald, −13 to −14 pp) and Wald ES97.5 at n = 250. Not significant at n = 1000 |
| E6 NPE | McNemar + paired regret, Holm | at n = 250 NPE significantly over-covers (+2–5 pp) and has **5–6% higher regret** (p < 1e-3). At n = 1000 regret differences are n.s. after Holm |

### E5 allocation (pooled, 360 paired replications per target; Holm within the H5 family of 12)

| target | DR-local vs D-opt | DR-local vs predictive | DR-local vs uniform | MCS(90%) |
|---|---|---|---|---|
| VaR97.5 | **0.83, Holm p = 0.032** | 0.66, p = 9e-5 | 0.54, p = 1e-8 | {DR-local, DR-prepost}: D-opt excluded (p = 0.002) |
| FZ0 (VaR, ES)97.5 | 0.97, n.s. (48% exact ties) | 0.79, p = 0.002 | 0.64, p = 6e-8 | {D-opt, DR-local, DR-prepost} |
| VaR99.9 | 0.91, n.s. | 0.93, n.s. | 0.76, p = 0.002 | {D-opt, predictive, DR-local, DR-prepost} |

H6 (preposterior vs local): ratios 0.96–1.00, all n.s. (Holm p = 1).

## 2. Robustness re-runs (R1)

### 2.1 Prior swap

The E3 subset (n ∈ {100, 1000} × ν ∈ {3, 6, 50}, 60 replications) was rerun with a prior that favours
light tails: ξ ~ HalfNormal(0.1) and log sd ~ N(0.3, 0.5²).

* **H2 is robust.** Mean cell ρ(|ξ err|, regret) rises from 0.06 (VaR95) through 0.21, 0.38 to 0.69
  (VaR99.9). This is the same ordering as the original prior.
* **Coverage is not robust.** The exact-posterior coverage of VaR99.9 collapses where the prior conflicts
  with the truth on the weakly identified direction. In that cell the prior-free MLE is the more reliable
  procedure, and its VaR99.9 regret is 0.72× that of the Bayes act.

  | n, ν | exact | Laplace-u | MLE-Wald |
  |---|---|---|---|
  | 100, ν = 3 | 0.37 | 0.17 | 0.80 |
  | 1000, ν = 3 | 0.78 | 0.62 | 0.90 |

  This is the decision-relevant face of weak identification: the posterior along a prior-dominated
  direction inherits the prior's error. It is what $\pi_g$ is designed to flag (H4b).

### 2.2 Finite-sample comparative backtests

T = 2500 out-of-sample days, 100 replications × {250, 1000} × ν ∈ {3, 6}.

* **Kupiec POF.** Rejection rates at 5% are **15–34% for every method, including the exact posterior**.
  Realized exceedance rates are 0.94–1.20%. This reproduces Escanciano & Olmo (2010): standard backtests
  that ignore estimation risk are oversized, so a Kupiec rejection cannot tell estimation methods apart.
* **Diebold–Mariano (HAC).**
  * n = 250, ν = 3: exact beats MLE significantly in 28% of windows, versus 4% the other way (q99). For
    FZ0 the split is 32% vs 6%.
  * ν = 6: the direction reverses (exact worse in 22–29%). This is the prior–truth effect seen in E3.
  * n = 1000: about 6–15% significant in each direction, i.e. no systematic difference.
* Finite backtests reproduce the population-regret conclusions but with much less power. This supports
  using closed-form population regret as the primary metric.

### 2.3 E5 under seed and design variants (local policies; 60 replications × 6 conditions each)

The variants are:

* `seed2`: new seed.
* `rv_cost1`: variance proxy twice as expensive.
* `peer_cost05`: peer data twice as expensive.
* `rv_m20`: precise proxy, m = 20.
* `batches16`: 16 batches of half the size.

DR-local vs D-opt, mean-regret ratio (Holm p within each variant's 9 comparisons):

| run | VaR97.5 | (VaR, ES)97.5 FZ0 | VaR99.9 |
|---|---|---|---|
| original | **0.83 (0.032)** | 0.97 (n.s.) | 0.91 (n.s.) |
| seed2 | 0.86 (0.097) | 0.99 (n.s.) | **0.81 (0.002)** |
| rv_cost1 | **0.77 (0.002)** | 0.90 (0.074) | 0.89 (n.s.) |
| peer_cost05 | 0.91 (n.s.) | 1.00 (n.s.) | **0.75 (6e-4)** |
| rv_m20 | 0.89 (n.s.) | 0.95 (n.s.) | **0.75 (0.003)** |
| batches16 | 0.92 (n.s.) | 0.99 (n.s.) | 0.88 (n.s.) |

* **Within single runs.** DR-local's point estimate is better than D-opt in 17 of 18 comparisons, but it
  is significant in only 5. *Which* target reaches significance changes with seed and design, so
  single-run target-level claims are fragile.
* **Against the other baselines.** DR-local beats uniform in all 18 comparisons (Holm p ≤ 2e-3). It
  beats predictive allocation in all 12 VaR97.5 / FZ0 comparisons, but only in 1 of 6 for VaR99.9.
* **Pooled over all 6 runs.** This is a secondary analysis, not pre-declared: 2,160 paired replications
  per target, normalized by the uniform mean of each run × condition.

  | target | DR-local / D-opt | p (t) | p (Wilcoxon) | runs with ratio < 1 |
  |---|---|---|---|---|
  | VaR97.5 | **0.865** | 5e-7 | 3e-10 | 6/6 |
  | VaR99.9 | **0.828** | 1e-10 | 4e-7 | 6/6 |
  | FZ0 97.5 | 0.969 | 0.028 | 0.29 | 5/6 |

  DR-local / predictive: 0.79 (FZ0), 0.65 (VaR97.5) and 0.93 (VaR99.9), all p < 3e-3.

**Revised H5 conclusion.**

* For VaR targets, decision-targeted allocation beats Fisher-only D-optimal design by a **modest but
  robust 13–17% regret reduction** across seeds and cost designs. The original single run was
  underpowered to show this for VaR99.9.
* For the joint (VaR, ES) FZ0 target the gain is ≈3% and not robust (Wilcoxon n.s.). Its curvature
  weights both scale and tail, so the decision-weighted information matrix is close to D-optimality's
  balanced design.

### 2.4 H6 confirmatory test

Setup: the suggestive cell ν = 3, n₀ = 100, VaR97.5; 150 new replications; 32 preposterior simulations
instead of 12.

| comparison | regret ratio | p (t) | identical final allocation |
|---|---|---|---|
| preposterior / local | 1.10 | 0.18 | **97%** (145/150) |
| preposterior / D-opt | 1.08 | 0.26 | 92% |
| local / D-opt | 0.99 | 0.54 | 93% |

With less Monte Carlo noise, the preposterior criterion almost always picks the same allocation as the
Gaussian-linear local criterion. The earlier 0.84 ratio and the 40% disagreement rate came from
preposterior Monte Carlo noise (12 simulations), not from non-Gaussianity. **H6 is rejected for this
model class.** Global evaluation would only matter where the posterior geometry changes the ranking of
sources, e.g. the singular-locus models of E4. This remains untested for allocation.

## 3. What changed after significance testing

| original statement | after S1 + R1 |
|---|---|
| "DR beats D-opt only for VaR97.5" | single-run significance was underpowered and target-specific. Pooled over 6 runs: DR beats D-opt for **both** VaR targets (−13 to −17%, p ≤ 5e-7). FZ0 gain ≈ 3% (fragile) |
| "preposterior ≈ local" | strengthened: 97% identical allocations once MC noise is reduced |
| "π_g is the best prior-sensitivity predictor" | **weakened**: not distinguishable from the plain contraction ratio (p = 0.52) |
| "local diagnostics add nothing beyond Var(g)" | refined: a small (ρ ≈ 0.1) but significant residual signal for the whitened local variance |
| "exact posterior intervals are near nominal" | true under the default prior; **fails under a conflicting prior on ξ** (0.37 coverage for VaR99.9 at n = 100, ν = 3) |
| H2, H3, E3b | unchanged, significant, robust |
