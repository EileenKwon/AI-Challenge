#!/usr/bin/env bash
# Reproduce every DECISION-ID result from scratch (about 1.5-2 h on 4 cores).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python}
$PY -m pytest -q tests
$PY -u experiments/e1_first_experiment.py
$PY -u experiments/e2_gaussian_baseline.py
$PY -u -W ignore experiments/e3_student_t_study.py
$PY -u experiments/e3_analyze.py
$PY -u -W ignore experiments/e3b_prior_truth.py
$PY -u -W ignore experiments/e4_mixture_multimodal.py
$PY -u -W ignore experiments/e5_allocation.py
$PY -u experiments/e5_analyze.py
$PY -u -W ignore experiments/e6_npe.py
$PY -u experiments/s1_significance.py
$PY -u -W ignore experiments/r1_robustness.py backtest_dm
$PY -u -W ignore experiments/r1_robustness.py e3_prior_swap
$PY -u -W ignore experiments/r1_robustness.py e5_variants
$PY -u -W ignore experiments/r1_robustness.py h6_confirm
$PY -u experiments/r1_robustness.py analyze
$PY -u -W ignore experiments/e7_adaptive.py calibrate
$PY -u -W ignore experiments/e7_adaptive.py evaluate
$PY -u experiments/e7_analyze.py
$PY -u -W ignore experiments/e7b_noise.py
$PY -u -W ignore experiments/e8_confirm.py
$PY -u -W ignore experiments/e9_learned.py gen
$PY -u -W ignore experiments/e9_learned.py train
$PY -u -W ignore experiments/e9_learned.py eval
$PY -u experiments/e89_analyze.py
$PY -u -W ignore experiments/e10_sv_confirm.py run
$PY -u experiments/e10_sv_confirm.py analyze
$PY -u experiments/f1_immune_levels.py
