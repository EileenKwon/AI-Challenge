# 08 — Confirmation (E8) and a regret-trained neural design policy (E9)

## Pre-registration

This section was committed before the E8/E9 runs.

**Primary hypotheses.** All use paired tests on per-replicate regrets with common seeds: paired t,
Wilcoxon, and 95% paired-bootstrap CI of the ratio of means. Holm is applied over H8a, H8b, H9a, H9b
and H9c.

| id | hypothesis | data |
|---|---|---|
| H8a | In weakly identified GARCH with a 10-day variance target (QLIKE), always-global EVSI design has lower regret than local Bayesian c-optimal design | 150 new replications of garch/weak/qlike10 |
| H8b | With an **exact** SV likelihood, global EVSI design is no longer worse than c-optimal design; the E7 SV deterioration was caused by QML misspecification | SV with observations y = h + N(−1.27, π²/2) (QML exact), 2 truths × 40 replications |
| H9a | The regret-trained neural policy beats c-optimal design in GARCH | E7 GARCH evaluation seeds (4 cells × 30), pooled with cell-normalized regrets |
| H9b | The same holds in SV (QML), where global design failed | E7 SV evaluation seeds (2 × 30) |
| H9c | The same holds in the confirmatory GARCH cell | the 150 E8 seeds |

**Exploratory.** Horizons of 5 and 22 days in the weak GARCH regime (40 replications each): is any
global advantage increasing in the horizon, i.e. persistence-sensitive? Also the learned policy's CPU
cost relative to c-optimal and to global design.

**Neural policy design (fixed before training).**

* Features: posterior mean and log sd of φ, κ, margin, log EVPI, log Var(g), stage; and per source the
  relative c-opt and D-opt scores, batches already bought, and a one-hot source identity.
* Network: 2 × 64 tanh MLP, MSE, Adam, early stopping on held-out trajectories.
* Labels: log(one-step true regret + δ), centered within each state.
* Training data: 300 trajectories per model with a random behaviour policy. Truths are drawn from a broad
  prior: GARCH α ~ U(0.005, 0.15), β ~ U(0.80, 0.985 − α); SV φ ~ U(0.90, 0.99), log σ_η ~ U(−3.2, −1.05).
* Evaluation seeds are disjoint from training seeds. Evaluation truths are the fixed E7/E8 truths.

**Particle-filter SV** is not run. Exact particle-filter likelihoods on the full parameter grid at
every preposterior update are computationally out of reach here. H8b instead removes the
misspecification by making the data generating process match the working likelihood, which answers
the same causal question at feasible cost.

## Results

Full tables: `reports/e89_results.md`, `results/e89_tests.csv`; figure: `figures/e89_ratios.png`.

### Primary tests (Holm over the five)

| id | comparison | ratio [95% CI] | p (t) | p (Wilcoxon) | Holm | verdict |
|---|---|---|---|---|---|---|
| H8a | global EVSI / c-opt, GARCH weak, 10-day variance (150 new replications) | 1.06 [0.89, 1.26] | 0.51 | 0.69 | 1.00 | **not confirmed.** The E7 trend (0.74, 30 replications) was noise |
| H8b | global EVSI / c-opt, SV with exact likelihood | 1.26 [1.06, 1.68] | 0.024 | 0.061 | 0.12 | **partly.** The deterioration shrinks from ×2.13 (QML) to ×1.26, but global is still not better |
| H9a | learned / c-opt, GARCH (E7 seeds) | 0.99 [0.80, 1.23] | 0.95 | 0.38 | 1.00 | tie |
| H9b | learned / c-opt, SV-QML (E7 seeds) | **0.73 [0.48, 0.99]** | 0.13 | **0.044** | 0.50 | favourable, not significant after Holm |
| H9c | learned / c-opt, GARCH confirmatory cell (150) | 1.18 [0.94, 1.44] | 0.15 | 0.032 (worse) | 0.50 | slightly unfavourable, n.s. |

**No primary hypothesis survives multiplicity adjustment.**

### Secondary results

* **Learned policy vs always-global design, SV:** 0.34 [0.21, 0.55], p = 0.0016. Its CPU is about 5% of
  the global design's (2.1–2.4 s vs 45–50 s per run).
  * In SV-regular: mean 0.50× c-opt, median 0.36×, better than c-opt in 60% of replications.
  * Model Confidence Set for SV: {uniform, c-opt, learned}. Every global and adaptive design is excluded.
* **Learned policy vs always-global design, GARCH:** 0.91 n.s., at c-opt's CPU (3.2–4.3 s vs 17–58 s).
* **Horizons** (weak GARCH, global / c-opt):

  | horizon | ratio |
  |---|---|
  | 5 days | 0.93 |
  | 10 days | 1.06 |
  | 22 days | 1.24 |

  There is no increasing advantage with horizon, so the "persistence-sensitive target" explanation is
  not supported.
* **SV-exact, uniform / c-opt:** 0.21 in the regular cell by mean, but p = 0.18. This is driven by a few
  extreme c-opt regrets, and c-opt bought *more* peer data than uniform. Not a finding.
* **Training diagnostics (held-out trajectories).**
  * The network explains only 5–16% of the label variance; one-step realized regrets are very noisy.
  * Mean one-step regret of the source it chooses, relative to c-opt's choice:

    | model / target | network | c-opt | random | oracle-best |
    |---|---|---|---|---|
    | GARCH, 10-day variance | 0.00177 | 0.00188 | 0.00248 | 0.00093 |
    | GARCH, VaR99 | 2.75e-5 | 3.20e-5 | — | — |
    | SV, VaR99 | **3.79e-4** | **6.44e-4** | 7.59e-4 | 2.65e-4 |

## Interpretation

1. **The search for a regime where expensive global goal-oriented design pays off came up empty** in
   these financial models:
   * the GARCH weak-ID trend did not replicate;
   * horizon length does not create one;
   * removing likelihood misspecification in SV reduces global design's damage but does not make it
     useful.

   Local Bayesian c-optimal design stays the strong, cheap baseline.
2. **Why global design underperforms, even when exact.** The global criterion is a K-sample Monte Carlo
   estimate of a small difference between sources, computed under the model's own predictive. Under
   near-ties its choice is noisy (E7b: 21–25% self-disagreement), and its myopic optimum is not the
   true-regret optimum.
3. **The learned policy is the one constructive lead.**
   * It is trained on *true* simulated regrets rather than the working model's predictive, and it costs
     no more than c-opt.
   * It ties c-opt in GARCH, beats always-global design by ×3 in SV at 1/20 of the CPU, and beats c-opt
     in SV (Wilcoxon p = 0.044, not significant after Holm). One unfavourable signal: GARCH confirmatory
     cell 1.18, Wilcoxon p = 0.03.
   * This is the "AI in finance" component: an **amortized, simulation-trained decision policy for
     financial data acquisition**. It suits ICAIF or ML-for-finance workshops better than a
     statistics-methods venue. It is a lead, not a result: it needs more training data, multi-step
     (non-myopic) labels, and a confirmatory run in SV.

## What would make the learned-policy direction publishable

* **Confirm H9b** with ≥ 150 fresh SV seeds. This is its own pre-registered test.
* **Non-myopic labels**: final regret after following the policy for the remaining stages
  (rollout / fitted Q-iteration) instead of one-step regret.
* **Robustness to the training prior** (truths outside the training range) and to model
  misspecification. Learning from the true data generating process is the policy's advantage in SV, but
  in practice the simulator is itself a model.
* **Comparisons with amortized Bayesian design methods** (Deep Adaptive Design, RL-based Bayesian
  design), adapted to a decision loss, and a real-data rolling study.
