# 09 — Highlights: the most interesting findings

Each item has a number, its evidence, and its statistical status. Synthetic data only; returns in
percent.

## Risk measures and identifiability

1. **Ask which risk level, not which parameter.** Tail-index estimation error barely matters for
   VaR95, but it drives VaR99.9.
   * Within-cell Spearman correlation with regret: 0.07 (VaR95) vs 0.76 (VaR99.9). The contrast is
     p = 2e-6 over 20 cells.
   * Robust to the inference method and to swapping the prior. (E3, S1, R1)
2. **Closed-form tail-index-immune levels** (`figures/f1_immune_levels.png`).
   * At fixed variance near normality, VaR is immune to the tail index exactly at
     α = Φ(√3) = 0.958, and ES at α = Φ(1) = 0.841.
   * The immune level rises with tail heaviness: VaR 0.976 and ES 0.897 at ν ≈ 6; VaR 0.999 at ν = 2.6.
   * The folklore "97.5% is ν-invariant" (Weir 1960) holds only globally, as a compromise.
   * Basel's ES 97.5% is never at its immune level.
   * The VaR99 / normal ratio is **non-monotone** in ν: it peaks around +14% at ν ≈ 3.5. (Prop. 5,
     unit test)
3. **Extreme-tail errors are cheap under a proper score.** From α = 0.90 to 0.999, the posterior
   variance of VaR grows 514×, but the expected quantile-score regret grows only 2.3×, because the
   density at the quantile collapses. (E1)
4. **One year of data makes the estimated mean-variance portfolio worse than cash.**
   * At n = 250 the expected-return error is 145%, while the VaR99 error is 3.6%.
   * The certainty-equivalent loss of the plug-in weight is 2.1× the optimal gain. (E2)

## Inference

5. **More data makes mean-field VI *worse* for tail risk.** Coverage of 90% intervals for VaR99.9 falls
   from 0.71 (n = 100) to 0.63 (n = 2500): the scale–tail posterior correlation never vanishes.
   (E3; significant under-coverage in 14 of 112 cells)
6. **"Wrong" posteriors can win, and why that is a trap.**
   * At fixed light-tailed truths, the plug-in MLE has 0.27× the regret of the exact Bayes act
     (ν = 50, n = 100). Laplace also wins at moderate tails.
   * When truths are drawn from the prior, 0 of 30 comparisons favour an approximation and 10 of 30
     are significantly worse.
   * Decision quality at a given truth is ruled by the prior on the weakly identified direction.
     (E3, E3b)
7. **A badly wrong parameter posterior can give the same decision.** In the calm/crisis mixture, the
   Laplace ellipse spills outside the support of an L-shaped exact posterior, yet VaR99 regret agrees
   to three digits (0.000638 vs 0.000639). (E4)
8. **A prior conflict on the tail collapses Bayesian coverage.** Under a light-tail prior at n = 100,
   ν = 3, exact-posterior VaR99.9 coverage is 0.37, while the prior-free Wald interval gives 0.80. (R1)

## Backtesting

9. **Standard backtests cannot tell estimators apart.** The Kupiec test rejects even the exact
   Bayesian posterior in 15–34% of 2,500-day windows (nominal 5%), because estimation risk alone
   shifts the exceedance rate. Diebold–Mariano tests reproduce the population ranking with low power.
   (R1)

## Data acquisition (design)

10. **Goal-oriented allocation beats information-maximizing allocation.**
    * Bayesian c-optimal allocation has 13–17% lower VaR regret than D-optimal allocation, pooled over
      6 independent seed/cost designs (p ≤ 5e-7). It is lower in 6 of 6 runs.
    * "Buy more own history" is 4–9× worse than a mixed allocation. (E5, R1)
11. **"Exact" global Bayesian design can hurt.**
    * In stochastic volatility under the usual QML quasi-likelihood, always-global preposterior design
      has 2.1× the regret of the cheap local criterion. This replicated on fresh seeds: ×2.13 in E7
      (p = 0.007) and ×2.04 in E10 (p = 0.0003).
    * With an exact likelihood it is still 1.26× worse.
    * Exactness is only as good as the model and the Monte Carlo precision. (E7, E8)
12. **Posterior non-Gaussianity does not tell you when to compute more; decision fragility does.**
    * The non-Gaussianity indicator has AUC ≈ 0.5 for predicting when global computation changes the
      decision.
    * The margin between the two best data sources has AUC 0.87 in the regular and mixture models.
      (E7)
13. **A small neural policy trained on simulated true regrets matches c-optimal design and halves the
    regret of global design.**
    * In SV it has 0.46× the regret of always-global design on fresh seeds (p = 0.0002) at ~5% of the
      CPU.
    * Its pre-registered advantage over c-opt did **not** confirm: 0.93, p = 0.13. Only the
      regular-volatility truth shows 0.81, p = 0.012, which is secondary.
    * It learned to buy precise realized variance rather than noisy proxies. (E9, E10)

## What did *not* hold

* The Fisher-eigenvector "weak × sensitive" score is not coordinate-free (it ranges 0.5%–54% for the
  same data).
* The GARCH weak-ID advantage of global design did not replicate (1.06 with 150 replications).
* "Longer horizons favour global design" is not supported.
* The learned policy's advantage over c-opt in SV (0.73 in E9) did not confirm on fresh seeds (0.93,
  p = 0.13).
