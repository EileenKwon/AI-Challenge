# DECISION-ID — Decision-Identifiable Bayesian Inference for Financial Risk Estimation

An independent research project. It does not touch the debt-recovery service in the rest of this
repository.

**Question.** Are statistically identifiable parameters necessarily the most important ones for
accurate financial decisions? The project separates four objects:

1. parameter identifiability,
2. posterior approximation accuracy,
3. functional identifiability,
4. downstream decision sensitivity.

It then tests whether a decision-relevant weak-identifiability diagnostic, and an allocation rule built
on it, adds anything beyond known methods.

<!-- RESULTS -->

## Documents

| file | content |
|---|---|
| `docs/01_research_plan.md` | hypotheses H1–H6 (stated before E3–E5), design safeguards, experiment map |
| `docs/02_derivation.md` | models, Fisher information (incl. the Gaussian-limit expansion), Propositions 1–3, regret weighting, allocation criterion, assumptions |
| `docs/03_novelty_check.md` | prior-art map (c-optimality, goal-oriented OED / Spantini et al., sloppy models, VOI, finance estimation risk) |
| `docs/04_results.md` | consolidated results of E1–E6 against each hypothesis |
| `docs/05_assessment.md` | failure analysis and the publishability verdict |
| `reports/*.md` | auto-generated tables per experiment |
| `figures/*.png` | auto-generated figures |

## Layout

```
src/decision_id/
  tmodel.py        Student-t model: parameterizations, Fisher info, VaR/ES, closed-form expected
                   quantile & FZ0 scores, predictive (Bayes-act) functionals, KL
  gaussian.py      Gaussian model with conjugate NIG posterior (exactness baseline)
  mixture.py       calm/crisis scale mixture with singular loci (local-vs-global failure case)
  posterior.py     grid (exact), MLE, Laplace (2 parameterizations), Gaussian VI (MF/FR), adaptive MCMC
  diagnostics.py   Fisher-eigen heuristic, R_g(lambda), prior-whitened decomposition, allocation values
  allocation.py    data sources, local and preposterior decision-value criteria
  npe.py           numpy Gaussian-head neural posterior estimation (no DL framework was available)
experiments/       e1..e6 scripts (+ e3_analyze, e5_analyze, run_all.sh)
tests/             23 tests: Fisher vs Monte Carlo, score properness/curvature, invariance identities,
                   posterior agreement (grid vs MCMC/Laplace/VI), NPE gradients, allocation sources
config.yaml        every path, seed, prior and experiment setting
```

## Reproduce

```bash
cd projects/decision_id
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                       # ~7 s
bash experiments/run_all.sh     # ~1.5-2 h on 4 cores; writes results/, reports/, figures/
```

Seeds are fixed (`SEED = 42`, `numpy.random.SeedSequence` per task). Returns are synthetic and in
percent units. Every decision is scored by its population (out-of-sample) regret under the true data
generating process, computed in closed form. A finite independent backtest is also reported as a
check.
