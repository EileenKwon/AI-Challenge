# 03 — Novelty check (prior-art map)

Method: a literature search done before the experiments, verified through bibliographic records,
abstracts and repository pages. Full texts on arxiv.org could not be opened from this environment, so
the descriptions below come from abstracts and snippets. Items marked UNVERIFIED could not be confirmed.
The decision on novelty uses the five ingredients of the proposal:

1. Fisher eigen-directions × functional sensitivity, $|v_j^\top\nabla g|$ against $\lambda_j$.
2. $R_g=\nabla g^\top(I+\lambda I_d)^{-1}\nabla g$.
3. Prior-whitened (invariant) attribution of functional uncertainty to directions.
4. Weighting by the curvature of the expected proper score, so that variance becomes regret.
5. Allocating data, simulation or inference effort by that criterion.

## Closest prior work

| ingredient | prior work | overlap |
|---|---|---|
| 2 | Elfving (1952, *Ann. Math. Stat.* 23:255) c-optimality; **Chaloner (1984, *Ann. Stat.* 12:283)** Bayesian design $\mathrm{tr}\,\psi(R+X^\top X)^{-1}$, with $R$ the prior precision. With $R=\lambda I$ and $\psi=\nabla g\nabla g^\top$ this **is** $R_g$. Also Chaloner & Verdinelli (1995, *Stat. Sci.*). | **full** |
| 3 | **Spantini, Cui, Willcox, Tenorio & Marzouk (2017, *SISC* 39:S167)**: goal-oriented optimal low-rank posterior approximations. Spantini et al. (2015): prior-whitened generalized eigenproblem with variance ratio $1/(1+\lambda_j)$. Cui et al. (2014): likelihood-informed subspaces. Baptista, Marzouk & Zahm: gradient-based goal-oriented reduction. | **full** (linear-Gaussian / Laplace) |
| 1 | Gutenkunst et al. (2007, *PLoS Comput. Biol.*): "sloppy" FIM spectra and tight predictions. Transtrum, Machta & Sethna (2011). Kreutz et al. (2012): prediction profile likelihood, the global check of prediction identifiability. Claeskens & Hjort (2003, *JASA*): focused information criterion, which uses $\partial\mu/\partial\theta$ and $I^{-1}$. | partial–full |
| 4 | Brennan & Kharroubi (2007): Laplace approximations of EVSI. Kan & Zhou (2007, *JFQA*): analytic utility loss of an estimated portfolio, $\tfrac12\gamma\mathrm{Var}(w)$. Huang, Bickford Smith & Rainforth (2026, AISTATS): loss-driven active learning. Lacoste-Julien et al. (2011) and Kuśmierczyk et al. (2019): loss-calibrated inference. No single source was found that writes $\tfrac12 f(q)\mathrm{Var}(\widehat{\mathrm{VaR}})$ / FZ0 curvature as the allocation weight for VaR/ES. | partial |
| 5 | Goal-oriented OED: Attia, Alexanderian & Saibaba (2018); Wu, Chen & Ghattas (2023); Neuberger et al. (2024, quadratic goal); Zhong et al. (2024, nonlinear QoI, MCMC). Input-uncertainty allocation in stochastic simulation: Ng & Chick (2006); Freimer & Schruben; Song & Nelson (2015); Ungredda, Pearce & Branke. EPIG (Bickford Smith et al. 2023). Lindley (1956). | partial–full |
| finance | Christoffersen & Gonçalves (2005, *J. Risk*): estimation risk in VaR/ES, larger for ES. Gourieroux & Zakoian (2013): estimation-adjusted VaR. Escanciano & Olmo (2010): backtests with estimation risk. Danielsson & Zhou; Kellner & Rösch (2016): ES carries more model risk. Fissler & Ziegel (2016) and Patton, Ziegel & Chen (2019): (VaR, ES) scoring. Merton (1980): drift is weakly identified. | context |
| weak ID | Andrews & Cheng (2012, *Econometrica*). Ma, Nelson & Startz (2007): information-matrix SEs are far too small in weakly identified GARCH. Poirier (1998), Gustafson, Moon & Schorfheide (2012): non-identified Bayesian inference. | threat / context |
| hybrid | INLA (Rue, Martino & Chopin 2009); MCMC-within-INLA and IS-INLA (Gómez-Rubio & Rue 2018; Berild et al.). These pick the subspace by model structure, not by goal. | tangential |
| t-quantile fact | Weir (1960, *Nature* 185:558): for a unit-variance $t$ the 97.5% quantile stays between 1.96 and 2.0 for $\nu\ge4$. Basel's ES97.5 ≈ VaR99 equivalence under normality. | context |

## Verdict before experiments

* Ingredients 1–3 are known mathematics: delta method, c-optimality, and goal-oriented whitened
  decomposition. The proposal's raw form (ingredient 1, and ingredient 2 with arbitrary $\lambda$) is also
  coordinate-dependent, which makes it weaker than the known invariant forms.
* Ingredient 4 is a textbook second-order value-of-information expansion. Its explicit form for VaR
  (pinball) and (VaR, ES) (FZ0) was not found as an allocation weight, but this is an application rather
  than a method.
* Ingredient 5 is goal-oriented Bayesian experimental design.
* Directions that looked open: (i) choosing an INLA-type exactly integrated subspace by goal relevance;
  (ii) a systematic account of *which* financial risk functionals are fragile to weak tail
  identification, and why; (iii) a quantified account of *when* local decision diagnostics fail under weak
  identification, with global/preposterior alternatives. The experiments (E1–E6) were designed to test
  (ii) and (iii). Item (i) was not pursued: for 2–3 parameter models exact integration is already cheap,
  so it cannot be evaluated meaningfully here.

Reviewers should be expected to describe the core diagnostic as "c-optimality / goal-oriented OED applied
to finance". Any contribution has to rest on (ii)–(iii) and on what is found empirically. The final
assessment is in `05_assessment.md`.
