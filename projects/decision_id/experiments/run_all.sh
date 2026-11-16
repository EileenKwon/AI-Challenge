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
