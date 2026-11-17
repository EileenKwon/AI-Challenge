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

<!-- RESULTS -->
