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

## Bottom line

* **Identifiable ≠ decision-relevant, and the reverse.**
  * Gaussian location: 145% median relative error, yet only 27% of VaR99 uncertainty.
  * Tail-index error vs regret: ρ = 0.07 for VaR95 and 0.76 for VaR99.9.
  * In the regime mixture, a badly wrong parameter posterior gives the same VaR99 decision.
* **The proposed diagnostic is not new in its valid form, and not valid in its new form.**
  * $R_g(0)$ is the delta method; $R_g(\lambda)$ is Bayesian c-optimality.
  * The Fisher-eigen "weak × sensitive" split depends on coordinates: 0.5% vs 54% for the same data.
  * The invariant repair is the goal-oriented prior-whitened decomposition (Spantini et al. 2017).
* **Beyond posterior variance?**
  * Not for predicting decision error (partial ρ ≈ 0.1).
  * Marginally for prior sensitivity ($\pi_g$: ρ 0.89 vs 0.88 for the contraction ratio).
* **Decision-targeted allocation.**
  * It beats uniform, own-history-only and predictive (log-score) allocation.
  * It beats Fisher-only D-optimal design only for VaR97.5 (regret 0.52 vs 0.66 of uniform). FZ0 is a
    tie and VaR99.9 is inconclusive.
  * The global preposterior version adds nothing over the local one, at ~150× the cost.
* **New-ish, applied results.**
  * At fixed variance, VaR is tail-index-immune at α = Φ(√3) = 0.958 and ES at Φ(1) = 0.841 near the
    Gaussian limit. The immune level rises to 0.987 / 0.938 at ν = 4.
  * Quantile-score regret compresses tail risk: VaR posterior variance grows ~500× from α = 0.90 to
    0.999, but regret grows only ~2.3×.
  * Log-score criteria are misaligned with tail decisions.
* **Verdict.** No publishable *methods* contribution as proposed. There is a plausible applied paper on
  tail-index estimation risk in VaR/ES decisions. See `docs/05_assessment.md` for the failure analysis and
  the extensions that could change this.

| figure | shows |
|---|---|
| `figures/e1_contours_n250.png` | likelihood vs posterior contours in 3 parameterizations, Fisher eigenvectors, iso-functional curves |
| `figures/e1_spectrum.png` | ξ-sensitivity sign change, weak-direction share and regret proxy across VaR levels |
| `figures/e3_coverage.png` | functional coverage of 7 inference methods vs n |
| `figures/e3_param_vs_decision.png` | tail-index error vs regret, VaR97.5 vs VaR99.9 |
| `figures/e4_mixture_example.png` | singular-locus posterior, Laplace failure in parameter space vs agreement in functional space |
| `figures/e5_regret_ratio.png` | allocation policies vs uniform for three decision targets |

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
tests/             24 tests: Fisher vs Monte Carlo, score properness/curvature, invariance identities,
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
