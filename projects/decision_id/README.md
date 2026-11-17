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
  * It beats Fisher-only D-optimal design by a modest 13–17% for VaR targets: pooled over 6 seed/design
    runs, p ≤ 5e-7, all 6 runs < 1. The gain for FZ0 is ≈3% and fragile.
  * Single-run significance is underpowered and target-unstable.
  * The global preposterior version reproduces the local choice in 97% of cases, at ~150× the cost.
* **Significance and robustness** (doc 06).
  * MCSE, paired and cell-clustered tests, Holm adjustment, Model Confidence Set.
  * Re-runs over seed, cost design and prior.
  * Kupiec and Diebold–Mariano backtests.
  * H2, H3 and E3b are robust. "π_g beats the contraction ratio" is **not** significant.
  * Exact-posterior coverage collapses under a prior that conflicts with the truth on ξ (0.37 for
    VaR99.9).
* **Failure-triggered adaptive design (E7, doc 07).**
  * Tested in Student-t, regime-mixture, GARCH(1,1)-t6 and SV models, against uniform, D-opt, Bayesian
    c-optimal (key baseline) and always-global Bayesian designs.
  * It does **not** beat c-optimal design: 0.99–1.13, n.s.; worse in SV.
  * Always-global design is itself never better than c-optimal: n.s. in t, mixture and GARCH; ×2.1
    worse in SV under the QML quasi-likelihood. The only trend is GARCH weak-ID / 10-day variance, 0.74
    (n.s.).
  * Posterior non-Gaussianity does not predict when global changes the decision (AUC ≈ 0.5). The
    decision margin does in t / mixture (AUC 0.87).
  * Net result: local Bayesian c-optimal design is a strong, cheap baseline in non-regular financial
    models.
* **Confirmation and AI extension (E8/E9, doc 08).**
  * The GARCH weak-ID trend did not replicate (1.06 with 150 replications).
  * With an exact SV likelihood, global design's deterioration shrinks from ×2.13 to ×1.26, but global
    is still not better than c-opt.
  * A **regret-trained neural design policy** (numpy MLP trained on simulated true regrets) ties c-opt
    in GARCH. In SV it beats always-global design (×0.34, p = 0.002, at ~5% of the CPU) and c-opt
    (×0.73, Wilcoxon p = 0.044).
  * No pre-registered primary test survives Holm. The learned policy is a lead that still needs a
    confirmatory run.
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
| `docs/07_adaptive_design.md` | failure-triggered adaptive goal-oriented design vs Bayesian c-optimal and global Bayesian designs in Student-t, regime-mixture, GARCH and SV models (E7) |
| `docs/08_confirmation_and_learned_policy.md` | pre-registered confirmation (E8), SV misspecification ablation, regret-trained neural design policy (E9, the AI-in-finance component) |
| `docs/06_significance_robustness.md` | significance tests (MCSE, paired/cluster tests, Holm, MCS) and robustness re-runs (seed, design, prior, finite backtests with Kupiec/DM) |
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
tests/             39 tests: Fisher vs Monte Carlo, score properness/curvature, invariance identities,
                   posterior agreement (grid vs MCMC/Laplace/VI), NPE gradients, allocation sources
config.yaml        every path, seed, prior and experiment setting
```

## Reproduce

```bash
cd projects/decision_id
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                       # ~7 s
bash experiments/run_all.sh     # ~8 h on 4 cores; writes results/, reports/, figures/
```

Seeds are fixed (`SEED = 42`, `numpy.random.SeedSequence` per task). Returns are synthetic and in
percent units. Every decision is scored by its population (out-of-sample) regret under the true data
generating process, computed in closed form. A finite independent backtest is also reported as a
check.
