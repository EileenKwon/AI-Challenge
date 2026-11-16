# 01 — Research plan and hypotheses

**Question.** Are statistically identifiable parameters necessarily the most important ones for
accurate financial decisions? We keep four objects separate: parameter identifiability, posterior
approximation accuracy, functional identifiability, and decision sensitivity.

## Hypotheses

These were stated before E3–E5 were run. E1 was exploratory.

| id | hypothesis | test |
|---|---|---|
| H1 | Which functionals are fragile to the weakly identified tail direction cannot be read off parameter-wise intuition. It requires the data-identified direction. | E1 contours/spectrum, E3 |
| H2 | Tail-index recovery error correlates weakly with regret for moderate-level VaR and strongly for extreme VaR/ES. | E3 §2 |
| H3 | The Fisher-eigen "weak × sensitive" score and $R_g(\lambda>0)$ are not reparameterization invariant. $R_g(0)$ and the whitened decomposition are. | tests, E3 §4 |
| H4 | For predicting the realized error of the Bayes act, local diagnostics add nothing beyond the exact posterior variance of $g$, and are worse where Bernstein–von Mises fails. | E3 §3, §7, E4 |
| H4b | The whitened prior-dominance ratio $\pi_g$ predicts prior sensitivity of the decision better than the posterior variance does. | E3 §5 |
| H5 | Decision-targeted allocation lowers the targeted regret compared with uniform, Fisher-only (D-opt) and predictive (log-score) allocation at equal cost. It does not dominate on parameter recovery or log score. | E5 |
| H6 | Preposterior (global) decision-targeted allocation beats the local version when the posterior is non-Gaussian (short samples, heavy tails), and the two coincide in long samples. | E5 |

## Design choices that guard against self-deception

* Every decision is scored by its **population (out-of-sample) regret under the true DGP**: the closed
  form of the expected quantile / FZ0 score difference. A finite independent backtest sample is also
  reported, and its agreement with the population regret is checked (E3 §8). Nothing is tuned on a
  backtest.
* The **exact posterior** (grid; conjugate for the Gaussian model) is the reference. MCMC is checked
  against it.
* Common random numbers: in E5 all policies use the same data pools within a replicate.
* Distribution shift: decisions are also scored under a heavier-tailed, higher-volatility DGP (E3 §6).
* The decision-targeted procedure changes only *which data are collected*. The Bayesian posterior
  itself is never modified.

## Experiment map

| exp | content | stage |
|---|---|---|
| E1 | 2-parameter Student-t: likelihood/posterior contours in three parameterizations, Fisher eigenvectors, iso-functional curves, functional posteriors, level spectrum | 1 |
| E2 | Gaussian, conjugate exact posterior: method correctness, location-vs-scale decoupling, portfolio regret | 1 |
| E3 | Student-t, 4 sample sizes × 5 tail indices × 100 replications; 7 inference methods; diagnostics vs realized loss; invariance; prior sensitivity; shift; backtest | 1–2 |
| E4 | Regime mixture with singular loci: local vs exact | 2 (failure analysis) |
| E5 | Allocation across own returns / peer tail data / variance proxies; 6 policies | 3–4 |
| E6 | Standard NPE (Gaussian head, numpy) vs exact | baseline |
