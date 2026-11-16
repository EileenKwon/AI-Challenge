# E7 — Failure-triggered adaptive design vs Bayesian c-optimal and global designs

6 stages, equal data budget, 16 preposterior simulations; 330 evaluation replications in total. Calibrated thresholds (from separate calibration seeds): tau_kappa = 1000000000.0, tau_margin = 0.5 (calibration recall 0.81, firing rate 0.61, 145/660 disagreement stages).

## Primary and secondary comparisons (regret normalized by the cell's c-opt mean)

| model   | tag   | comparison              |   ratio | ci95           |       p_t |   p_wilcoxon |     ties |   cpu_ratio |   p_holm_P1P4 |   noninferior_10pct |
|:--------|:------|:------------------------|--------:|:---------------|----------:|-------------:|---------:|------------:|--------------:|--------------------:|
| garch   | P1    | adapt_cal / copt        |  1.018  | [0.834, 1.229] | 0.8548    |    0.7067    | 0.3417   |      6.898  |       1       |                 nan |
| garch   | P2    | adapt_cal / evsi_global |  0.9346 | [0.814, 1.043] | 0.3187    |    0.9001    | 0.7417   |      0.8221 |     nan       |                   1 |
| garch   | P4    | evsi_global / copt      |  1.089  | [0.855, 1.381] | 0.4874    |    0.501     | 0.2417   |      8.391  |       1       |                 nan |
| garch   | S     | adapt / copt            |  0.9925 | [0.832, 1.175] | 0.9296    |    0.4101    | 0.375    |      6.372  |     nan       |                 nan |
| garch   | S     | copt_global / copt      |  1.078  | [0.842, 1.349] | 0.5328    |    0.648     | 0.2083   |      8.357  |     nan       |                 nan |
| garch   | S     | dopt / copt             |  0.8392 | [0.632, 1.110] | 0.2443    |    0.5708    | 0.09167  |      0.9777 |     nan       |                 nan |
| garch   | S     | uniform / copt          |  1.384  | [1.071, 1.808] | 0.0132    |    0.0001767 | 0.01667  |      1.13   |     nan       |                 nan |
| garch   | S     | adapt_cal / adapt       |  1.026  | [0.906, 1.134] | 0.6598    |    0.2995    | 0.6417   |      1.083  |     nan       |                 nan |
| mix     | P1    | adapt_cal / copt        |  0.9936 | [0.941, 1.049] | 0.8083    |    0.6507    | 0.8417   |      3.043  |       1       |                 nan |
| mix     | P2    | adapt_cal / evsi_global |  1      | [0.976, 1.026] | 0.9718    |  nan         | 0.9583   |      0.4977 |     nan       |                   1 |
| mix     | P4    | evsi_global / copt      |  0.9931 | [0.936, 1.052] | 0.8143    |    0.7469    | 0.8      |      6.114  |       1       |                 nan |
| mix     | S     | adapt / copt            |  0.9835 | [0.948, 1.014] | 0.3166    |    0.3258    | 0.8833   |      3.055  |     nan       |                 nan |
| mix     | S     | copt_global / copt      |  0.9934 | [0.936, 1.054] | 0.823     |    0.5988    | 0.7333   |      6.113  |     nan       |                 nan |
| mix     | S     | dopt / copt             |  1.02   | [0.841, 1.232] | 0.8372    |    0.883     | 0.3      |      1.001  |     nan       |                 nan |
| mix     | S     | uniform / copt          |  1.708  | [1.305, 2.262] | 0.0007275 |    0.001918  | 0.008333 |      1.238  |     nan       |                 nan |
| mix     | S     | adapt_cal / adapt       |  1.01   | [0.959, 1.070] | 0.7138    |    0.6257    | 0.8833   |      0.9961 |     nan       |                 nan |
| sv      | P1    | adapt_cal / copt        |  1.902  | [1.281, 3.060] | 0.01735   |    0.002836  | 0.2667   |     12.23   |       0.1215  |                 nan |
| sv      | P2    | adapt_cal / evsi_global |  0.8941 | [0.712, 1.068] | 0.2584    |    0.7819    | 0.5167   |      0.6933 |     nan       |                   1 |
| sv      | P4    | evsi_global / copt      |  2.127  | [1.379, 3.396] | 0.006851  |    0.004982  | 0.1833   |     17.64   |       0.05481 |                 nan |
| sv      | S     | adapt / copt            |  1.437  | [1.065, 2.042] | 0.04771   |    0.2746    | 0.5167   |      6.988  |     nan       |                 nan |
| sv      | S     | copt_global / copt      |  2.095  | [1.363, 3.401] | 0.008953  |    0.004459  | 0.1667   |     17.51   |     nan       |                 nan |
| sv      | S     | dopt / copt             |  1.863  | [1.208, 3.112] | 0.03869   |    0.1466    | 0.25     |      1.016  |     nan       |                 nan |
| sv      | S     | uniform / copt          |  0.7543 | [0.508, 1.038] | 0.1754    |    0.1767    | 0.03333  |      1.033  |     nan       |                 nan |
| sv      | S     | adapt_cal / adapt       |  1.324  | [0.899, 2.076] | 0.2301    |    0.02716   | 0.4      |      1.75   |     nan       |                 nan |
| t       | P1    | adapt_cal / copt        |  1.132  | [0.888, 1.647] | 0.4404    |  nan         | 0.9      |     18.31   |       1       |                 nan |
| t       | P2    | adapt_cal / evsi_global |  1      | [1.000, 1.000] | 1         |    1         | 1        |      0.8487 |     nan       |                   1 |
| t       | P4    | evsi_global / copt      |  1.132  | [0.889, 1.649] | 0.4404    |  nan         | 0.9      |     21.58   |       1       |                 nan |
| t       | S     | adapt / copt            |  1      | [1.000, 1.000] | 1         |    1         | 1        |      3.178  |     nan       |                 nan |
| t       | S     | copt_global / copt      |  0.9685 | [0.858, 1.015] | 0.3978    |  nan         | 0.9333   |     21.68   |     nan       |                 nan |
| t       | S     | dopt / copt             |  1.217  | [0.785, 1.682] | 0.3506    |  nan         | 0.8      |      0.9906 |     nan       |                 nan |
| t       | S     | uniform / copt          |  1.263  | [0.844, 2.172] | 0.3149    |    0.4771    | 0        |      1.102  |     nan       |                 nan |
| t       | S     | adapt_cal / adapt       |  1.132  | [0.896, 1.643] | 0.4404    |  nan         | 0.9      |      5.762  |     nan       |                 nan |

## Model Confidence Set (alpha = 0.10)

| model   | MCS_90                                                          |   p_uniform |   p_dopt |   p_copt |   p_copt_global |   p_evsi_global |   p_adapt |   p_adapt_cal |
|:--------|:----------------------------------------------------------------|------------:|---------:|---------:|----------------:|----------------:|----------:|--------------:|
| garch   | dopt, copt, copt_global, evsi_global, adapt, adapt_cal          |       0.004 |    1.000 |    1.000 |           1.000 |           0.403 |     1.000 |         1.000 |
| mix     | dopt, copt, copt_global, evsi_global, adapt, adapt_cal          |       0.001 |    0.988 |    1.000 |           1.000 |           1.000 |     1.000 |         1.000 |
| sv      | uniform, copt                                                   |       1.000 |    0.092 |    0.134 |           0.021 |           0.014 |     0.092 |         0.038 |
| t       | uniform, dopt, copt, copt_global, evsi_global, adapt, adapt_cal |       0.685 |    1.000 |    1.000 |           1.000 |           1.000 |     1.000 |         1.000 |

## Per cell: mean regret relative to c-opt and CPU seconds per run

| cell                  |   reps |   uniform/copt |   dopt/copt |   copt/copt |   copt_global/copt |   evsi_global/copt |   adapt/copt |   adapt_cal/copt |   cpu_copt_s |   cpu_evsi_s |   cpu_adapt_cal_s |   global_frac_adapt_cal |
|:----------------------|-------:|---------------:|------------:|------------:|-------------------:|-------------------:|-------------:|-----------------:|-------------:|-------------:|------------------:|------------------------:|
| garch/regular/qlike10 |     30 |          1.566 |       0.772 |       1.000 |              1.270 |              1.324 |        1.111 |            1.080 |        3.560 |       18.309 |            14.721 |                   0.767 |
| garch/regular/var99   |     30 |          1.568 |       0.855 |       1.000 |              1.146 |              1.176 |        0.991 |            1.137 |        4.113 |       43.027 |            33.187 |                   0.711 |
| garch/weak/qlike10    |     30 |          1.051 |       0.738 |       1.000 |              0.793 |              0.736 |        0.774 |            0.738 |        3.699 |       17.490 |            15.066 |                   0.794 |
| garch/weak/var99      |     30 |          1.353 |       0.992 |       1.000 |              1.105 |              1.119 |        1.094 |            1.116 |        4.898 |       57.693 |            49.262 |                   0.833 |
| mix/moderate/var99    |     30 |          0.956 |       0.899 |       1.000 |              0.909 |              0.993 |        0.923 |            1.038 |        1.764 |       10.526 |             5.857 |                   0.461 |
| mix/moderate/var999   |     30 |          1.384 |       0.968 |       1.000 |              1.015 |              0.995 |        0.995 |            0.995 |        1.776 |       10.810 |             5.244 |                   0.372 |
| mix/rare/var99        |     30 |          3.181 |       1.456 |       1.000 |              1.046 |              1.040 |        1.016 |            0.996 |        1.668 |       10.196 |             3.529 |                   0.211 |
| mix/rare/var999       |     30 |          1.309 |       0.756 |       1.000 |              1.004 |              0.945 |        1.000 |            0.945 |        1.650 |       10.394 |             6.238 |                   0.500 |
| sv/regular/var99      |     30 |          0.508 |       2.529 |       1.000 |              2.898 |              2.961 |        1.442 |            2.549 |        2.746 |       44.704 |            33.551 |                   0.728 |
| sv/weak/var99         |     30 |          1.001 |       1.197 |       1.000 |              1.293 |              1.293 |        1.432 |            1.254 |        2.603 |       49.680 |            31.886 |                   0.611 |
| t/nu3/var999          |     30 |          1.263 |       1.217 |       1.000 |              0.969 |              1.132 |        1.000 |            1.132 |        0.970 |       20.931 |            17.765 |                   0.861 |

## Trigger diagnostics (evaluation logs of the always-global run; out-of-sample)

disagree = the local c-opt choice differs from the global EVSI choice.

| model   |   stages |   disagree_rate |   AUC_kappa |   AUC_neg_margin |   AUC_margin_over_kappa |   fire_rate_fixed |   recall_fixed |   fire_rate_cal |   recall_cal |   recall_margin_only_cal |   recall_kappa_only_cal |
|:--------|---------:|----------------:|------------:|-----------------:|------------------------:|------------------:|---------------:|----------------:|-------------:|-------------------------:|------------------------:|
| garch   |      720 |           0.331 |       0.583 |            0.571 |                   0.585 |             0.742 |          0.798 |           0.768 |        0.824 |                    0.824 |                   0.000 |
| mix     |      720 |           0.086 |       0.532 |            0.876 |                   0.883 |             0.408 |          0.694 |           0.382 |        0.871 |                    0.871 |                   0.000 |
| sv      |      360 |           0.472 |       0.437 |            0.559 |                   0.544 |             0.397 |          0.376 |           0.653 |        0.706 |                    0.706 |                   0.000 |
| t       |      180 |           0.072 |       0.405 |            0.861 |                   0.856 |             0.100 |          0.308 |           0.861 |        1.000 |                    1.000 |                   0.000 |
| all     |     1980 |           0.244 |       0.577 |            0.674 |                   0.680 |             0.499 |          0.623 |           0.615 |        0.793 |                    0.793 |                   0.000 |

Global c-opt (variance) and global EVSI choose the same source in 96.0% of stages.

Figure: `figures/e7_cost_regret.png`.