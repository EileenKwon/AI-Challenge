# E7 — Failure-triggered adaptive design vs Bayesian c-optimal and global designs

6 stages, equal data budget, 16 preposterior simulations; 156 evaluation replications in total. Calibrated thresholds (from separate calibration seeds): tau_kappa = 1000000000.0, tau_margin = 0.5 (calibration recall 0.81, firing rate 0.61, 145/660 disagreement stages).

## Primary and secondary comparisons (regret normalized by the cell's c-opt mean)

| model   | tag   | comparison              |   ratio | ci95           |       p_t |   p_wilcoxon |     ties |   cpu_ratio |   p_holm_P1P4 |   noninferior_10pct |
|:--------|:------|:------------------------|--------:|:---------------|----------:|-------------:|---------:|------------:|--------------:|--------------------:|
| garch   | P1    | adapt_cal / copt        |  1.086  | [0.245, 3.108] | 0.7874    |   nan        | 0.3333   |      8.813  |             1 |                 nan |
| garch   | P2    | adapt_cal / evsi_global |  1      | [1.000, 1.006] | 0.1883    |   nan        | 0.6667   |      0.8034 |           nan |                   1 |
| garch   | P4    | evsi_global / copt      |  1.086  | [0.244, 3.103] | 0.7879    |   nan        | 0        |     10.97   |             1 |                 nan |
| garch   | S     | adapt / copt            |  0.8696 | [0.477, 1.000] | 0.3178    |   nan        | 0.3333   |      5.22   |           nan |                 nan |
| garch   | S     | copt_global / copt      |  1.086  | [0.244, 3.152] | 0.7879    |   nan        | 0        |     11.13   |           nan |                 nan |
| garch   | S     | dopt / copt             |  0.3716 | [0.110, 2.350] | 0.3862    |   nan        | 0.1667   |      1.016  |           nan |                 nan |
| garch   | S     | uniform / copt          |  1.177  | [0.373, 5.755] | 0.5924    |   nan        | 0        |      1.169  |           nan |                 nan |
| garch   | S     | adapt_cal / adapt       |  1.249  | [0.513, 3.793] | 0.3801    |   nan        | 0.1667   |      1.689  |           nan |                 nan |
| mix     | P1    | adapt_cal / copt        |  0.9936 | [0.940, 1.049] | 0.8083    |     0.6507   | 0.8417   |      3.043  |             1 |                 nan |
| mix     | P2    | adapt_cal / evsi_global |  1      | [0.975, 1.027] | 0.9718    |   nan        | 0.9583   |      0.4977 |           nan |                   1 |
| mix     | P4    | evsi_global / copt      |  0.9931 | [0.934, 1.055] | 0.8143    |     0.7469   | 0.8      |      6.114  |             1 |                 nan |
| mix     | S     | adapt / copt            |  0.9835 | [0.948, 1.014] | 0.3166    |     0.3258   | 0.8833   |      3.055  |           nan |                 nan |
| mix     | S     | copt_global / copt      |  0.9934 | [0.934, 1.056] | 0.823     |     0.5988   | 0.7333   |      6.113  |           nan |                 nan |
| mix     | S     | dopt / copt             |  1.02   | [0.842, 1.236] | 0.8372    |     0.883    | 0.3      |      1.001  |           nan |                 nan |
| mix     | S     | uniform / copt          |  1.708  | [1.292, 2.306] | 0.0007275 |     0.001918 | 0.008333 |      1.238  |           nan |                 nan |
| mix     | S     | adapt_cal / adapt       |  1.01   | [0.956, 1.071] | 0.7138    |     0.6257   | 0.8833   |      0.9961 |           nan |                 nan |
| t       | P1    | adapt_cal / copt        |  1.132  | [0.892, 1.629] | 0.4404    |   nan        | 0.9      |     18.31   |             1 |                 nan |
| t       | P2    | adapt_cal / evsi_global |  1      | [1.000, 1.000] | 1         |     1        | 1        |      0.8487 |           nan |                   1 |
| t       | P4    | evsi_global / copt      |  1.132  | [0.888, 1.640] | 0.4404    |   nan        | 0.9      |     21.58   |             1 |                 nan |
| t       | S     | adapt / copt            |  1      | [1.000, 1.000] | 1         |     1        | 1        |      3.178  |           nan |                 nan |
| t       | S     | copt_global / copt      |  0.9685 | [0.864, 1.015] | 0.3978    |   nan        | 0.9333   |     21.68   |           nan |                 nan |
| t       | S     | dopt / copt             |  1.217  | [0.781, 1.695] | 0.3506    |   nan        | 0.8      |      0.9906 |           nan |                 nan |
| t       | S     | uniform / copt          |  1.263  | [0.830, 2.125] | 0.3149    |     0.4771   | 0        |      1.102  |           nan |                 nan |
| t       | S     | adapt_cal / adapt       |  1.132  | [0.892, 1.650] | 0.4404    |   nan        | 0.9      |      5.762  |           nan |                 nan |

## Model Confidence Set (alpha = 0.10)

| model   | MCS_90                                                          |   p_uniform |   p_dopt |   p_copt |   p_copt_global |   p_evsi_global |   p_adapt |   p_adapt_cal |
|:--------|:----------------------------------------------------------------|------------:|---------:|---------:|----------------:|----------------:|----------:|--------------:|
| garch   | uniform, dopt, copt, copt_global, evsi_global, adapt, adapt_cal |       0.310 |    1.000 |    1.000 |           1.000 |           1.000 |     1.000 |         1.000 |
| mix     | dopt, copt, copt_global, evsi_global, adapt, adapt_cal          |       0.000 |    0.985 |    1.000 |           1.000 |           1.000 |     1.000 |         1.000 |
| t       | uniform, dopt, copt, copt_global, evsi_global, adapt, adapt_cal |       0.696 |    1.000 |    1.000 |           1.000 |           1.000 |     1.000 |         1.000 |

## Per cell: mean regret relative to c-opt and CPU seconds per run

| cell                |   reps |   uniform/copt |   dopt/copt |   copt/copt |   copt_global/copt |   evsi_global/copt |   adapt/copt |   adapt_cal/copt |   cpu_copt_s |   cpu_evsi_s |   cpu_adapt_cal_s |   global_frac_adapt_cal |
|:--------------------|-------:|---------------:|------------:|------------:|-------------------:|-------------------:|-------------:|-----------------:|-------------:|-------------:|------------------:|------------------------:|
| garch/regular/var99 |      6 |          1.177 |       0.372 |       1.000 |              1.086 |              1.086 |        0.870 |            1.086 |        4.153 |       45.561 |            36.605 |                   0.667 |
| mix/moderate/var99  |     30 |          0.956 |       0.899 |       1.000 |              0.909 |              0.993 |        0.923 |            1.038 |        1.764 |       10.526 |             5.857 |                   0.461 |
| mix/moderate/var999 |     30 |          1.384 |       0.968 |       1.000 |              1.015 |              0.995 |        0.995 |            0.995 |        1.776 |       10.810 |             5.244 |                   0.372 |
| mix/rare/var99      |     30 |          3.181 |       1.456 |       1.000 |              1.046 |              1.040 |        1.016 |            0.996 |        1.668 |       10.196 |             3.529 |                   0.211 |
| mix/rare/var999     |     30 |          1.309 |       0.756 |       1.000 |              1.004 |              0.945 |        1.000 |            0.945 |        1.650 |       10.394 |             6.238 |                   0.500 |
| t/nu3/var999        |     30 |          1.263 |       1.217 |       1.000 |              0.969 |              1.132 |        1.000 |            1.132 |        0.970 |       20.931 |            17.765 |                   0.861 |

## Trigger diagnostics (evaluation logs of the always-global run; out-of-sample)

disagree = the local c-opt choice differs from the global EVSI choice.

| model   |   stages |   disagree_rate |   AUC_kappa |   AUC_neg_margin |   AUC_margin_over_kappa |   fire_rate_fixed |   recall_fixed |   fire_rate_cal |   recall_cal |   recall_margin_only_cal |   recall_kappa_only_cal |
|:--------|---------:|----------------:|------------:|-----------------:|------------------------:|------------------:|---------------:|----------------:|-------------:|-------------------------:|------------------------:|
| garch   |       36 |           0.306 |       0.411 |            0.509 |                   0.491 |             0.500 |          0.455 |           0.639 |        0.636 |                    0.636 |                   0.000 |
| mix     |      720 |           0.086 |       0.532 |            0.876 |                   0.883 |             0.408 |          0.694 |           0.382 |        0.871 |                    0.871 |                   0.000 |
| t       |      180 |           0.072 |       0.405 |            0.861 |                   0.856 |             0.100 |          0.308 |           0.861 |        1.000 |                    1.000 |                   0.000 |
| all     |      936 |           0.092 |       0.538 |            0.830 |                   0.843 |             0.353 |          0.605 |           0.484 |        0.860 |                    0.860 |                   0.000 |

Global c-opt (variance) and global EVSI choose the same source in 94.7% of stages.

Figure: `figures/e7_cost_regret.png`.