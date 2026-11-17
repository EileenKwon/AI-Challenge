# E8/E9 — Confirmation, SV misspecification ablation, regret-trained neural policy

## All tests (Holm over the five pre-registered primary tests)

| test                                                | family    |   n |   ratio |   ci_lo |   ci_hi |      p_t |   p_wilcoxon |    ties |   p_holm_primary |
|:----------------------------------------------------|:----------|----:|--------:|--------:|--------:|---------:|-------------:|--------:|-----------------:|
| H8a evsi_global/copt (garch weak qlike10, 150 reps) | primary   | 150 |  1.064  |  0.8854 |  1.257  | 0.5123   |    0.6919    | 0.2333  |           1      |
| confirm adapt_cal/copt                              | secondary | 150 |  1.037  |  0.865  |  1.221  | 0.6868   |    0.4535    | 0.3     |         nan      |
| confirm dopt/copt                                   | secondary | 150 |  1.15   |  0.9168 |  1.46   | 0.2758   |    0.6532    | 0.18    |         nan      |
| confirm uniform/copt                                | secondary | 150 |  1.344  |  1.137  |  1.656  | 0.001436 |    0.003444  | 0.01333 |         nan      |
| H8b evsi_global/copt (SV exact likelihood, pooled)  | primary   |  80 |  1.26   |  1.058  |  1.677  | 0.02384  |    0.06114   | 0.2     |           0.1192 |
| SV-exact adapt_cal/copt                             | secondary |  80 |  1.143  |  0.958  |  1.489  | 0.165    |    0.4064    | 0.2625  |         nan      |
| SV-exact dopt/copt                                  | secondary |  80 |  0.9519 |  0.5408 |  1.715  | 0.8771   |    0.002488  | 0.175   |         nan      |
| SV-exact uniform/copt                               | secondary |  80 |  0.7161 |  0.4101 |  1.22   | 0.3457   |    0.9131    | 0.0375  |         nan      |
| H9a learned/copt (garch, E7 seeds)                  | primary   | 120 |  0.9927 |  0.7984 |  1.226  | 0.9458   |    0.378     | 0.2583  |           1      |
| garch learned/evsi_global                           | secondary | 120 |  0.9115 |  0.6861 |  1.23   | 0.5405   |    0.8635    | 0.1667  |         nan      |
| H9b learned/copt (sv, E7 seeds)                     | primary   |  60 |  0.728  |  0.4785 |  0.9945 | 0.1261   |    0.04393   | 0.06667 |           0.5046 |
| sv learned/evsi_global                              | secondary |  60 |  0.3423 |  0.2082 |  0.5515 | 0.00162  |    0.0001789 | 0       |         nan      |
| H9c learned/copt (garch weak qlike10, 150 reps)     | primary   | 150 |  1.179  |  0.9408 |  1.445  | 0.1468   |    0.03239   | 0.2     |           0.5046 |
| confirm learned/evsi_global                         | secondary | 150 |  1.108  |  0.8746 |  1.433  | 0.4183   |    0.2833    | 0.1667  |         nan      |

## Horizon exploration in the weak GARCH regime (global EVSI / c-opt)

| horizon_target        |   n |   ratio |   ci_lo |   ci_hi |    p_t |
|:----------------------|----:|--------:|--------:|--------:|-------:|
| qlike22               |  40 |  1.238  |  0.9472 |   1.588 | 0.1517 |
| qlike5                |  40 |  0.9308 |  0.7148 |   1.245 | 0.6101 |
| qlike10 (E8 confirm)  | 150 |  1.064  |  0.8854 |   1.257 | 0.5123 |
| qlike10 (E7, 30 reps) |  30 |  0.7365 |  0.5163 |   1.033 | 0.1177 |

## SV: exact likelihood (E8) vs QML quasi-likelihood (E7)

| truth   |   exact: evsi/copt |   QML (E7): evsi/copt |   exact: uniform/copt |   QML (E7): uniform/copt |
|:--------|-------------------:|----------------------:|----------------------:|-------------------------:|
| regular |              1.097 |                 2.961 |                 0.207 |                    0.508 |
| weak    |              1.423 |                 1.293 |                 1.225 |                    1.001 |

Pooled evsi/copt: exact 1.260 vs QML 2.127

## Learned policy per cell (E7 seeds) and CPU seconds per run

| cell                  |   learned/copt |   evsi/copt |   uniform/copt |   cpu_learned |   cpu_copt |   cpu_evsi |
|:----------------------|---------------:|------------:|---------------:|--------------:|-----------:|-----------:|
| garch/regular/qlike10 |          1.311 |       1.324 |          1.566 |         3.418 |      3.560 |     18.309 |
| garch/regular/var99   |          0.885 |       1.176 |          1.568 |         4.240 |      4.113 |     43.027 |
| garch/weak/qlike10    |          0.699 |       0.736 |          1.051 |         3.245 |      3.699 |     17.490 |
| garch/weak/var99      |          1.076 |       1.119 |          1.353 |         4.264 |      4.898 |     57.693 |
| sv/regular/var99      |          0.498 |       2.961 |          0.508 |         2.083 |      2.746 |     44.704 |
| sv/weak/var99         |          0.958 |       1.293 |          1.001 |         2.377 |      2.603 |     49.680 |

## Model Confidence Set incl. the learned policy (E7 seeds, alpha = 0.10)

| model   | MCS_90                                                          |   p_uniform |   p_dopt |   p_copt |   p_copt_global |   p_evsi_global |   p_adapt |   p_adapt_cal |   p_learned |
|:--------|:----------------------------------------------------------------|------------:|---------:|---------:|----------------:|----------------:|----------:|--------------:|------------:|
| garch   | dopt, copt, copt_global, evsi_global, adapt, adapt_cal, learned |       0.005 |    1.000 |    1.000 |           1.000 |           0.560 |     1.000 |         1.000 |       1.000 |
| sv      | uniform, copt, learned                                          |       1.000 |    0.074 |    0.131 |           0.019 |           0.015 |     0.074 |         0.033 |       1.000 |

## Training report (held-out trajectories: mean one-step true regret of the chosen source)

|               |       net |      copt |      best |    random |   val_mse |   val_var |   epochs |     delta |   n_rows |   test_states |
|:--------------|----------:|----------:|----------:|----------:|----------:|----------:|---------:|----------:|---------:|--------------:|
| garch/qlike10 | 0.001768  | 0.001884  | 0.0009296 | 0.002478  |    1.27   |     1.331 |       39 | 9.686e-06 |     5400 |           360 |
| garch/var99   | 2.751e-05 | 3.203e-05 | 1.583e-05 | 4.238e-05 |    1.165  |     1.203 |       33 | 1.749e-07 |     5400 |           360 |
| sv/var99      | 0.0003787 | 0.0006442 | 0.0002646 | 0.0007589 |    0.9565 |     1.133 |       42 | 1.526e-06 |     5400 |           360 |

CPU in the confirmatory cell: adapt_cal 13.4s, copt 2.7s, dopt 2.7s, evsi_global 15.3s, uniform 3.2s

Figure: `figures/e89_ratios.png`.