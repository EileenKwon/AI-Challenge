# 02 — Mathematical derivation

Notation. Data $x_{1:n}\stackrel{iid}{\sim}p(\cdot\mid\theta)$, $\theta\in\mathbb R^d$. Per-observation Fisher
information $I_1(\theta)$, total $I=nI_1$. Prior $\pi_0$ with (reference) precision $P$. A financial
functional $g:\mathbb R^d\to\mathbb R$ with gradient $\nabla g$. Loss $L=-r$. All functionals are
**physical-measure** quantities computed from return distributions; no risk-neutral / option-implied
parameters are used anywhere (requirement 2).

## 1. Models and functionals used

**Gaussian** $r\sim N(\mu,\mathrm{sd}^2)$, $\theta=(\mu,\log\mathrm{sd})$, $I_1=\mathrm{diag}(1/\mathrm{sd}^2,\,2)$.
$\mathrm{VaR}_\alpha=-\mu+\mathrm{sd}\,z_\alpha$, $\mathrm{ES}_\alpha=-\mu+\mathrm{sd}\,\varphi(z_\alpha)/(1-\alpha)$,
mean-variance weight $w^*=\mu/(\gamma\,\mathrm{sd}^2)$ with certainty-equivalent regret
$\tfrac12\gamma\,\mathrm{sd}^2(w-w^*)^2$.

**Student-t (main model)** $r=\sigma T$, $T\sim t_\nu$, location known. Canonical $(\sigma,\xi)$ with
tail index $\xi=1/\nu\in(0,0.45]$ ($\xi\to0$ is the Gaussian boundary). Per-observation Fisher in
$(\sigma,\nu)$ (Lange, Little & Taylor 1989):

$$I_{\sigma\sigma}=\frac{2\nu}{(\nu+3)\sigma^2},\quad I_{\sigma\nu}=\frac{-2}{(\nu+1)(\nu+3)\sigma},\quad
I_{\nu\nu}=\tfrac14\big[\psi'(\tfrac\nu2)-\psi'(\tfrac{\nu+1}2)\big]-\frac{\nu+5}{2\nu(\nu+1)(\nu+3)}.$$

Transformed with $d\nu/d\xi=-\nu^2$. The trigamma difference cancels catastrophically for large $\nu$; at
the Gaussian limit we derived $\log f_\nu(z)=\log\varphi(z)+\xi\,(z^4-2z^2-1)/4+O(\xi^2)$, which gives
$I_{\xi\xi}(0)=\mathrm{Var}\big((z^4-2z^2-1)/4\big)=56/16=3.5$, $I_{\sigma\xi}(0)=2/\sigma$, $I_{\sigma\sigma}(0)=2/\sigma^2$
(used for $\xi<0.002$; verified against Monte Carlo in `tests/test_tmodel.py`).
In $(\log\mathrm{sd},\xi)$ with $\mathrm{sd}=\sigma/\sqrt{1-2\xi}$ the Fisher matrix is **orthogonal at $\xi=0$**
(off-diagonal $2-2=0$, $I_{\xi\xi\mid\mathrm{sd}}=1.5$), whereas in $(\log\sigma,\xi)$ the correlation is
$2/\sqrt7=0.76$. "Strong parameter correlation" is therefore partly a coordinate artefact.

Functionals: $\mathrm{VaR}_\alpha=\sigma t_\nu^{-1}(\alpha)$, $\mathrm{ES}_\alpha=\sigma\frac{\nu+q^2}{\nu-1}\frac{f_\nu(q)}{1-\alpha}$,
variance $\sigma^2/(1-2\xi)$.

**Regime mixture (E4)** $r\sim(1-p)N(0,s_1^2)+pN(0,s_2^2)$, $s_1$ known, $\phi=(\mathrm{logit}\,p,\log s_2)$.
Two singular loci: $p\to0$ (then $s_2$ is not identified) and $s_2\to s_1$ (then $p$ is not identified).
These are the same structure as the GARCH weak-identification problem ($\alpha\to0$ leaves $\beta$
unidentified; Andrews & Cheng 2012; Ma, Nelson & Startz 2007).

## 2. Four different objects

| object | definition | coordinate-free? |
|---|---|---|
| parameter identifiability | $I(\theta)$ nonsingular; weak if small relative to prior precision | eigenvalues of $I$: **no**; generalized eigenvalues of $(I,P)$: yes |
| posterior approximation accuracy | distance between approximate and exact posterior | depends on the approximation's coordinates (Laplace, mean-field VI) |
| functional identifiability | locally: $\nabla g\in\mathrm{range}(I)$; globally: $g$ constant on likelihood-equivalence sets is identified | yes |
| decision sensitivity | change of expected score of the Bayes act per unit error in $g$ | yes |

A functional can be identified when parameters are not (label switching; along the ridge of E1 a
moderate quantile is constant), and a well-identified parameter can matter little (Gaussian location
for VaR, E2).

## 3. Local (delta-method) quantities

Under Bernstein–von Mises and smooth $g$:
$$\mathrm{Var}_{\pi_n}(g)\approx\nabla g^\top(I+P)^{-1}\nabla g,\qquad
\mathrm{Var}(\hat g_{\mathrm{MLE}})\approx\nabla g^\top I^{-1}\nabla g .$$

**Proposition 1 (what $R_g$ is).** $R_g(\lambda)=\nabla g^\top(I+\lambda I_d)^{-1}\nabla g$ is exactly the
Laplace/delta-method posterior variance of $g$ under the prior $N(\cdot,\lambda^{-1}I_d)$ *in the chosen
coordinates*.

* $\lambda=0$: $R_g(0)$ is invariant under any smooth reparameterization $\theta=h(\phi)$:
  with $J=\partial\theta/\partial\phi$, $\nabla_\phi g=J^\top\nabla_\theta g$, $I_\phi=J^\top I_\theta J$, so
  $\nabla_\phi g^\top I_\phi^{-1}\nabla_\phi g=\nabla_\theta g^\top I_\theta^{-1}\nabla_\theta g$. It is the Cramér–Rao bound
  for $g$ and equals $\sup_v (\nabla g^\top v)^2/(v^\top I v)$: the largest squared change of $g$ per unit of
  (twice the) Kullback–Leibler divergence.
* $\lambda>0$: $\lambda I_d$ does not transform as a tensor, so $R_g(\lambda)$ depends on units and
  coordinates (rescaling $\sigma$ from percent to decimal changes it). It is **not** a posterior
  variance unless the prior really is $N(\cdot,\lambda^{-1}I_d)$ in those coordinates.
* It is the classical Bayesian c-optimality criterion (Chaloner 1984) — not new.

**Proposition 2 (the Fisher-eigenvector heuristic is not coordinate-free).** Eigenvalues of $I$ change
under non-orthogonal linear maps and under rescaling; hence "identifiability$_j=\lambda_j$" and
"sensitivity$_j=|v_j^\top\nabla g|$" are not well defined. The identity
$R_g(0)=\sum_j (v_j^\top\nabla g)^2/\lambda_j$ holds in every coordinate system, but the *split* into directions
does not. E1/E3 quantify this: the weakest-direction share of VaR$_{95}$ uncertainty is 0.54, 0.005 and
0.20 in $(\log\mathrm{sd},\xi)$, $(\log\sigma,\xi)$ and $(\sigma,\nu)$ for the same data.

**Proposition 3 (invariant decomposition and the principled "weak × sensitive" score).**
Solve $Iv=\lambda Pv$ with $V^\top PV=I_d$ (prior-whitened generalized eigenproblem) and set $s_j=v_j^\top\nabla g$.
Then
$$V_{\rm prior}=\sum_j s_j^2,\qquad V_{\rm post}=\sum_j\frac{s_j^2}{1+\lambda_j},\qquad
S_g^2=\sum_j\frac{s_j^2}{(1+\lambda_j)^2},\qquad \pi_g=S_g^2/V_{\rm post}\in[0,1].$$

*Proof.* With $P=LL^\top$ and $L^{-1}IL^{-\top}=U\Lambda U^\top$, $V=L^{-\top}U$ and
$(I+P)^{-1}=V(\Lambda+I)^{-1}V^\top$, $P^{-1}=VV^\top$. $\square$

Interpretations (all exact in the Gaussian-linear model, checked in `tests/test_diagnostics.py`):
1. **Invariance.** $\lambda_j$ and $s_j$ are unchanged under linear reparameterization (and under any
   smooth one at the linearization point) when $P$ is pulled back as a metric ($P_\phi=J^\top P_\theta J$).
2. **Prior sensitivity.** If the prior mean moves by $L^{-\top}z$ ($|z|=1$ prior standard deviation),
   the posterior mean of $g$ moves by $\nabla g^\top(I+P)^{-1}Lz$, whose maximum over $z$ is $S_g$. The
   exact (global) analogue is $S_g^{\rm ex}=\|L^\top\mathrm{Cov}_{\pi_n}(\theta,g)\|$, the sensitivity of
   $E_{\pi_n}[g]$ to exponential tilting of the prior. So $\pi_g$ is the **fraction of the decision's
   uncertainty that the data have not learned**: the ratio of prior sensitivity to posterior variance.
3. **Marginal value of information.** Adding information $\kappa\,Pv_jv_j^\top P$ along direction $j$
   reduces $V_{\rm post}$ at rate $-\partial V_{\rm post}/\partial\kappa=s_j^2/(1+\lambda_j)^2=:a_j$. Adding
   prior-shaped information $\varepsilon P$ reduces it at rate $S_g^2=\sum_ja_j$. The user's
   heuristic "large sensitivity, weak identifiability" thus has a principled form: $a_j$, which is large
   only when **both** $s_j^2$ is large and $\lambda_j$ is small.

This decomposition is the goal-oriented, prior-whitened analysis of Spantini et al. (2017) and the
likelihood-informed-subspace literature specialized to $g$; the prior-sensitivity reading (item 2) is
standard local robustness (Gustafson 1996). None of it is new by itself (see `03_novelty_check.md`).

## 4. Decision weighting (from variance to regret)

Let $S(a,y)$ be a strictly consistent scoring function for a functional $T$ (pinball loss for VaR,
FZ0 for (VaR, ES); quadratic CE loss for a portfolio weight). Write $\bar S(a;\theta)=E_\theta S(a,Y)$,
minimized at $a^*(\theta)=g(\theta)$.

* **Bayes act.** $E_{\pi_n}\bar S(a;\theta)=E_{Y\sim p(\cdot\mid x)}S(a,Y)$ (Fubini), so the Bayes act is the
  functional of the **posterior predictive**, e.g. its $\alpha$-quantile — not $E_{\pi_n}[g]$. It is more
  conservative by $O(1/n)$ (an estimation-risk-adjusted VaR, cf. Gourieroux & Zakoian 2013).
* **Regret expansion.** $\bar S(a;\theta_0)-\bar S(g_0;\theta_0)=\tfrac12(a-g_0)^\top K(a-g_0)+o(|a-g_0|^2)$ with
  $K=\partial^2_a\bar S$ at the optimum. Hence expected regret $\approx\tfrac12\mathrm{tr}(K\,\mathrm{Cov}(\hat a))\approx
  \tfrac12\mathrm{tr}(K\,G^\top\Sigma G)$, with $\Sigma=(I+P)^{-1}$ and $G$ the stacked functional gradients.
  * quantile score: $K=f_L(\mathrm{VaR}_\alpha)$ (loss density at the quantile);
  * FZ0 (return scale $v=-\mathrm{VaR}$, $e=-\mathrm{ES}<0$, tail $a_t=1-\alpha$):
    $K=\mathrm{diag}\big(f_L(\mathrm{VaR})/(a_t\,\mathrm{ES}),\,1/\mathrm{ES}^2\big)$ (derived and checked numerically);
  * portfolio: $K=\gamma\,\mathrm{sd}^2$.
* **Consequence 1 (tail compression).** For VaR, $\mathrm{Var}(\widehat{\mathrm{VaR}}_\alpha)$ grows by two orders of
  magnitude from $\alpha=0.90$ to $0.999$ (E1), but $f_L(\mathrm{VaR}_\alpha)$ falls almost as fast, so the
  regret proxy rises only about 2.5-fold. Under a proper quantile score the extreme-tail functional is
  *not* where most decision value lies.
* **Consequence 2 (the log score is blind to weak directions).** For the predictive log score,
  $\mathrm{KL}(p_{\theta_0}\|p_{\hat\theta})\approx\tfrac12(\hat\theta-\theta_0)^\top I_1(\hat\theta-\theta_0)$, so expected regret
  $\approx\tfrac1{2n}\sum_j\lambda_j/(1+\lambda_j)$: weakly identified directions ($\lambda_j\ll1$) contribute
  **least**, because they are by definition the directions in which the data density changes least. Tail
  functionals can still change a lot along them (large $R_g/\text{KL}$). Predictive-uncertainty criteria
  therefore cannot target decision-relevant weak directions. This is the formal reason a decision-specific
  criterion can differ from a predictive one.

## 4b. Which VaR/ES level is immune to the tail index?

**Proposition 5.** Hold the variance fixed and perturb a Gaussian toward Student-t. To first order in
$\xi$ the density is $\varphi(x)[1+\tfrac{\kappa}{24}He_4(x)]$ with excess kurtosis $\kappa=6\xi/(1-4\xi)$. Then
$$\partial_\kappa\mathrm{VaR}_\alpha\propto He_3(z_\alpha)=z_\alpha^3-3z_\alpha,\qquad
\partial_\kappa\mathrm{ES}_\alpha\propto\varphi(z_\alpha)(z_\alpha^2-1)$$
(the ES derivative uses $\int_q^\infty He_n\varphi=He_{n-1}(q)\varphi(q)$ and the induced shift of the quantile). So
at the Gaussian limit **VaR is first-order tail-index-immune exactly at $\alpha^*=\Phi(\sqrt3)=0.9584$ and
ES at $\alpha^*=\Phi(1)=0.8413$.** Numerically the immune level moves with $\nu$:

| $\nu$ | ∞ | 50 | 10 | 6 | 4 | 3 |
|---|---|---|---|---|---|---|
| VaR $\alpha^*$ | 0.958 | 0.960 | 0.969 | 0.977 | 0.987 | 0.995 |
| ES $\alpha^*$ | 0.841 | 0.847 | 0.874 | 0.900 | 0.938 | 0.976 |

Weir's (1960) observation that the unit-variance 97.5% $t$-quantile is ≈1.96–2.0 for all $\nu\ge4$ is a
*global* statement: the curve rises and comes back. Locally, 97.5% is immune only near $\nu\approx6$.
Basel's ES$_{97.5}$ is far from its immune level for every $\nu$. Two further caveats: (i) "fixed variance"
is the right direction only if the data identify the variance; for $\nu\le4$ they do not (the fourth
moment does not exist), and the data-identified weak direction tilts toward "fixed body quantiles"; (ii)
which functional is fragile is therefore a property of $(\nu,n)$ *and* of what the likelihood identifies,
not of the parameterization (E1 Fig. `e1_spectrum.png`, E3 §H1). We did not find Proposition 5 stated in
this form; it follows directly from Cornish–Fisher-type expansions and is likely folklore.

## 5. Allocation criterion (Stage 3)

Sources $e$ with per-unit Fisher $I_e(\theta)$ and cost $c_e$; a batch buys $m_e=B/c_e$ units.

* **Local (Gaussian-linear) decision value** — Bayesian c/L-optimality with score curvature:
  $$\Delta^{\rm loc}_e=\tfrac12\mathrm{tr}\big(K\,G^\top[\Sigma-(\Sigma^{-1}+m_eI_e)^{-1}]G\big).$$
  For a rank-one $I_e=aa^\top$: $\tfrac12K(a^\top\Sigma\nabla g)^2/(1+a^\top\Sigma a)$ (Sherman–Morrison).
* **Preposterior decision value (posterior-preserving, global)** — expected value of sample information
  $$\Delta^{\rm pre}_e=\mathrm{EVPI}(\pi_n)-E_{y_e\sim p(\cdot\mid x)}\mathrm{EVPI}(\pi_n(\cdot\mid y_e)),\qquad
  \mathrm{EVPI}(\pi)=E_\pi[\bar S(a_\pi;\theta)-\bar S(g(\theta);\theta)],$$
  computed with exact grid updates. The identity $E_{y}E_{\theta\mid y}\bar S(g(\theta);\theta)=E_\theta\bar S(g(\theta);\theta)$
  shows this equals the reduction in Bayes risk while having lower Monte Carlo variance. The **posterior is
  never modified**: only which data are collected depends on the decision. No decision-weighted
  objective is added to the likelihood, so no generalized posterior is involved.
* **Baselines.** D-optimal ("Fisher-only"): $\log\det(\Sigma^{-1}+m_eI_e)-\log\det\Sigma^{-1}$ (invariant,
  functional-blind). Predictive: $\tfrac12\mathrm{tr}(I_{\rm own}[\Sigma-\Sigma_e'])$ (log-score regret reduction of
  the next own return; functional-blind). Uniform and own-history-only.

## 6. Assumptions and where they break

| assumption | used by | breaks when | checked in |
|---|---|---|---|
| posterior ≈ Gaussian in the chosen coordinates | $R_g$, Laplace, $\Delta^{\rm loc}$ | short samples, heavy tails, the $\xi=0$ boundary, curved ridges | E1, E3 (§7, §9) |
| unimodal, away from singular loci | all local quantities | mixtures and GARCH-type models near $p\to0$ / $s_2\to s_1$ | E4 |
| $g$ approximately linear over the posterior | delta method | moment functionals (variance) under heavy tails | E1, E3 §7 |
| $P$ is a fixed metric | invariance of Prop. 3 | non-Gaussian priors (we use moment matching), nonlinear reparameterization away from the linearization point | E3 §4 |
| curvature $K$ known | regret weighting | plug-in error in $f_L(\mathrm{VaR})$ is second order | — |
| well-specified model | everything | distribution shift: posterior variance ignores bias | E3 §6 (shift) |
