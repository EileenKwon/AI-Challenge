# R1 — Robustness re-runs and comparative backtests

## 0. E5 pooled over the original run and all 5 variants (6 independent runs, 2160 paired replications per target)

| target   | comparison             |   pooled_ratio |       p_t |   p_wilcoxon | runs_with_ratio<1   |   min_run_ratio |   max_run_ratio |    p_holm |
|:---------|:-----------------------|---------------:|----------:|-------------:|:--------------------|----------------:|----------------:|----------:|
| fz975    | dr_local vs dopt       |         0.9689 | 0.02782   |    0.2911    | 5/6                 |          0.9028 |          1.004  | 0.02782   |
| fz975    | dr_local vs predictive |         0.7884 | 2.07e-20  |    1.003e-13 | 6/6                 |          0.7565 |          0.8212 | 1.035e-19 |
| var975   | dr_local vs dopt       |         0.8648 | 4.749e-07 |    2.522e-10 | 6/6                 |          0.7737 |          0.918  | 1.425e-06 |
| var975   | dr_local vs predictive |         0.646  | 2.379e-33 |    2.058e-41 | 6/6                 |          0.549  |          0.7271 | 1.427e-32 |
| var999   | dr_local vs dopt       |         0.8283 | 1.423e-10 |    3.816e-07 | 6/6                 |          0.7526 |          0.9106 | 5.69e-10  |
| var999   | dr_local vs predictive |         0.9327 | 0.001279  |    0.02025   | 6/6                 |          0.845  |          0.9761 | 0.002558  |

## 1. E5 under design / seed variants (local policies only)

Ratio = mean regret of DR-local / comparison policy after normalizing each condition by its uniform mean; paired t and Wilcoxon over 360 paired replications; Holm across the 9 comparisons within each variant.

| variant     | target   | comparison             |   ratio | ci_diff          |    p_t |   p_wilcoxon |   p_holm |
|:------------|:---------|:-----------------------|--------:|:-----------------|-------:|-------------:|---------:|
| batches16   | fz975    | dr_local vs dopt       |  0.9882 | [-0.053, 0.037]  | 0.7238 |       0.5300 |   1.0000 |
| batches16   | fz975    | dr_local vs predictive |  0.8002 | [-0.268, -0.078] | 0.0006 |       0.0065 |   0.0035 |
| batches16   | fz975    | dr_local vs uniform    |  0.6861 | [-0.432, -0.201] | 0.0000 |       0.0000 |   0.0000 |
| batches16   | var975   | dr_local vs dopt       |  0.9180 | [-0.161, 0.052]  | 0.2690 |       0.0977 |   0.8069 |
| batches16   | var975   | dr_local vs predictive |  0.7271 | [-0.389, -0.110] | 0.0006 |       0.0000 |   0.0035 |
| batches16   | var975   | dr_local vs uniform    |  0.6679 | [-0.495, -0.166] | 0.0001 |       0.0000 |   0.0007 |
| batches16   | var999   | dr_local vs dopt       |  0.8785 | [-0.191, -0.003] | 0.0538 |       0.0790 |   0.2153 |
| batches16   | var999   | dr_local vs predictive |  0.9683 | [-0.099, 0.048]  | 0.5523 |       0.4577 |   1.0000 |
| batches16   | var999   | dr_local vs uniform    |  0.6937 | [-0.435, -0.179] | 0.0000 |       0.0000 |   0.0000 |
| peer_cost05 | fz975    | dr_local vs dopt       |  1.0039 | [-0.037, 0.043]  | 0.8962 |       0.8734 |   0.8962 |
| peer_cost05 | fz975    | dr_local vs predictive |  0.7565 | [-0.311, -0.130] | 0.0000 |       0.0000 |   0.0000 |
| peer_cost05 | fz975    | dr_local vs uniform    |  0.6813 | [-0.420, -0.216] | 0.0000 |       0.0000 |   0.0000 |
| peer_cost05 | var975   | dr_local vs dopt       |  0.9086 | [-0.127, 0.015]  | 0.1335 |       0.0403 |   0.2671 |
| peer_cost05 | var975   | dr_local vs predictive |  0.6188 | [-0.457, -0.232] | 0.0000 |       0.0000 |   0.0000 |
| peer_cost05 | var975   | dr_local vs uniform    |  0.5548 | [-0.570, -0.327] | 0.0000 |       0.0000 |   0.0000 |
| peer_cost05 | var999   | dr_local vs dopt       |  0.7532 | [-0.360, -0.118] | 0.0002 |       0.0021 |   0.0006 |
| peer_cost05 | var999   | dr_local vs predictive |  0.8450 | [-0.213, -0.055] | 0.0010 |       0.0074 |   0.0031 |
| peer_cost05 | var999   | dr_local vs uniform    |  0.7247 | [-0.402, -0.148] | 0.0000 |       0.0001 |   0.0001 |
| rv_cost1    | fz975    | dr_local vs dopt       |  0.9028 | [-0.105, -0.009] | 0.0248 |       0.0558 |   0.0743 |
| rv_cost1    | fz975    | dr_local vs predictive |  0.7900 | [-0.213, -0.064] | 0.0005 |       0.0416 |   0.0025 |
| rv_cost1    | fz975    | dr_local vs uniform    |  0.5171 | [-0.608, -0.360] | 0.0000 |       0.0000 |   0.0000 |
| rv_cost1    | var975   | dr_local vs dopt       |  0.7737 | [-0.198, -0.056] | 0.0006 |       0.0000 |   0.0025 |
| rv_cost1    | var975   | dr_local vs predictive |  0.6653 | [-0.313, -0.129] | 0.0000 |       0.0000 |   0.0000 |
| rv_cost1    | var975   | dr_local vs uniform    |  0.4373 | [-0.702, -0.426] | 0.0000 |       0.0000 |   0.0000 |
| rv_cost1    | var999   | dr_local vs dopt       |  0.8896 | [-0.173, 0.010]  | 0.0742 |       0.0206 |   0.1484 |
| rv_cost1    | var999   | dr_local vs predictive |  0.9402 | [-0.128, 0.039]  | 0.3089 |       0.6037 |   0.3089 |
| rv_cost1    | var999   | dr_local vs uniform    |  0.6791 | [-0.447, -0.201] | 0.0000 |       0.0000 |   0.0000 |
| rv_m20      | fz975    | dr_local vs dopt       |  0.9505 | [-0.092, 0.023]  | 0.2633 |       0.8839 |   0.5265 |
| rv_m20      | fz975    | dr_local vs predictive |  0.7711 | [-0.274, -0.115] | 0.0000 |       0.0000 |   0.0000 |
| rv_m20      | fz975    | dr_local vs uniform    |  0.6521 | [-0.448, -0.249] | 0.0000 |       0.0000 |   0.0000 |
| rv_m20      | var975   | dr_local vs dopt       |  0.8892 | [-0.137, 0.004]  | 0.0688 |       0.1310 |   0.2065 |
| rv_m20      | var975   | dr_local vs predictive |  0.5490 | [-0.552, -0.326] | 0.0000 |       0.0000 |   0.0000 |
| rv_m20      | var975   | dr_local vs uniform    |  0.5310 | [-0.596, -0.350] | 0.0000 |       0.0000 |   0.0000 |
| rv_m20      | var999   | dr_local vs dopt       |  0.7526 | [-0.335, -0.093] | 0.0008 |       0.0529 |   0.0034 |
| rv_m20      | var999   | dr_local vs predictive |  0.9637 | [-0.084, 0.038]  | 0.4344 |       0.8824 |   0.5265 |
| rv_m20      | var999   | dr_local vs uniform    |  0.6348 | [-0.507, -0.228] | 0.0000 |       0.0001 |   0.0000 |
| seed2       | fz975    | dr_local vs dopt       |  0.9901 | [-0.043, 0.030]  | 0.7053 |       0.8166 |   1.0000 |
| seed2       | fz975    | dr_local vs predictive |  0.8212 | [-0.253, -0.059] | 0.0024 |       0.1242 |   0.0098 |
| seed2       | fz975    | dr_local vs uniform    |  0.7100 | [-0.419, -0.169] | 0.0000 |       0.0000 |   0.0000 |
| seed2       | var975   | dr_local vs dopt       |  0.8613 | [-0.186, -0.008] | 0.0322 |       0.0029 |   0.0967 |
| seed2       | var975   | dr_local vs predictive |  0.6664 | [-0.435, -0.176] | 0.0000 |       0.0000 |   0.0000 |
| seed2       | var975   | dr_local vs uniform    |  0.6170 | [-0.539, -0.227] | 0.0000 |       0.0000 |   0.0000 |
| seed2       | var999   | dr_local vs dopt       |  0.8051 | [-0.249, -0.070] | 0.0005 |       0.0060 |   0.0024 |
| seed2       | var999   | dr_local vs predictive |  0.9761 | [-0.083, 0.050]  | 0.6412 |       0.2261 |   1.0000 |
| seed2       | var999   | dr_local vs uniform    |  0.6555 | [-0.486, -0.217] | 0.0000 |       0.0000 |   0.0000 |

Source mix of DR-local:

| variant     | eval_target   |   n_own |   n_peer |   n_rv |
|:------------|:--------------|--------:|---------:|-------:|
| batches16   | fz975         |    0.00 |     5.80 |  10.20 |
| batches16   | var975        |    0.00 |     3.15 |  12.85 |
| batches16   | var999        |    0.00 |    10.74 |   5.26 |
| peer_cost05 | fz975         |    0.00 |     3.06 |   4.94 |
| peer_cost05 | var975        |    0.18 |     1.62 |   6.20 |
| peer_cost05 | var999        |    0.00 |     5.46 |   2.54 |
| rv_cost1    | fz975         |    0.00 |     2.24 |   5.76 |
| rv_cost1    | var975        |    0.06 |     1.18 |   6.77 |
| rv_cost1    | var999        |    0.00 |     4.96 |   3.04 |
| rv_m20      | fz975         |    0.00 |     4.43 |   3.57 |
| rv_m20      | var975        |    0.00 |     2.55 |   5.45 |
| rv_m20      | var999        |    0.00 |     6.38 |   1.62 |
| seed2       | fz975         |    0.00 |     2.96 |   5.04 |
| seed2       | var975        |    0.00 |     1.62 |   6.38 |
| seed2       | var999        |    0.00 |     5.29 |   2.71 |

## 2. H6 confirmatory test (nu=3, n0=100, VaR97.5, 32 preposterior sims)

| comparison       |   n |   ratio |   mean_diff |      ci_lo |     ci_hi |    p_t |   p_wilcoxon |   frac_tie |
|:-----------------|----:|--------:|------------:|-----------:|----------:|-------:|-------------:|-----------:|
| prepost vs local | 150 |   1.096 |   2.859e-06 |  1.91e-07  | 7.378e-06 | 0.1789 |     nan      |     0.9667 |
| prepost vs dopt  | 150 |   1.08  |   2.434e-06 | -5.662e-07 | 7.314e-06 | 0.2633 |       0.2036 |     0.92   |
| local vs dopt    | 150 |   0.986 |  -4.255e-07 | -1.801e-06 | 9.375e-07 | 0.5402 |       0.625  |     0.9333 |

## 3. E3 subset with swapped priors (xi ~ HalfNormal(0.1), log sd ~ N(0.3, 0.5^2))

| functional   |   mean_cell_rho(|err_xi|, regret) |     min |    max |
|:-------------|----------------------------------:|--------:|-------:|
| var95        |                            0.0622 | -0.0955 | 0.3399 |
| var975       |                            0.2100 | -0.1038 | 0.5853 |
| var99        |                            0.3804 | -0.0739 | 0.7154 |
| var999       |                            0.6865 |  0.2510 | 0.9119 |
| es975        |                            0.3849 | -0.0625 | 0.7780 |

Coverage of 90% intervals:

| functional   |   grid |   laplace_nat |   laplace_u |    mle |   vi_fr |   vi_mf |
|:-------------|-------:|--------------:|------------:|-------:|--------:|--------:|
| es975        | 0.7917 |        0.6833 |      0.7250 | 0.8472 |  0.7611 |  0.6194 |
| var975       | 0.8556 |        0.7917 |      0.8194 | 0.8778 |  0.8333 |  0.7944 |
| var999       | 0.7500 |        0.6361 |      0.6889 | 0.8611 |  0.7028 |  0.5556 |

## 4. Finite-sample comparative backtests (T = 2500 out-of-sample days)

Kupiec POF test of VaR99 exceedances (rejection rate at 5%; nominal 0.05 for a correct model), realized and population exceedance probabilities:

|    n |     nu | method    |   exceed_rate |   pop_exceed |   kupiec_reject_5pct |
|-----:|-------:|:----------|--------------:|-------------:|---------------------:|
|  250 | 3.0000 | exact     |        0.0106 |       0.0103 |               0.2400 |
|  250 | 3.0000 | laplace_u |        0.0120 |       0.0118 |               0.3400 |
|  250 | 3.0000 | mle       |        0.0108 |       0.0106 |               0.3300 |
|  250 | 6.0000 | exact     |        0.0094 |       0.0096 |               0.2800 |
|  250 | 6.0000 | laplace_u |        0.0100 |       0.0102 |               0.2600 |
|  250 | 6.0000 | mle       |        0.0105 |       0.0108 |               0.3200 |
| 1000 | 3.0000 | exact     |        0.0101 |       0.0100 |               0.1800 |
| 1000 | 3.0000 | laplace_u |        0.0107 |       0.0106 |               0.1800 |
| 1000 | 3.0000 | mle       |        0.0103 |       0.0102 |               0.1900 |
| 1000 | 6.0000 | exact     |        0.0104 |       0.0099 |               0.1500 |
| 1000 | 6.0000 | laplace_u |        0.0105 |       0.0101 |               0.1600 |
| 1000 | 6.0000 | mle       |        0.0107 |       0.0102 |               0.1800 |

Diebold-Mariano (Newey-West) tests, exact-posterior Bayes act vs competitor (negative = exact better); fraction of replications significant at 5%:

|    n |     nu | method                |   mean_dm_q99 |   frac_exact_better_q99 |   frac_exact_worse_q99 |   mean_dm_fz |   frac_exact_better_fz |   frac_exact_worse_fz |
|-----:|-------:|:----------------------|--------------:|------------------------:|-----------------------:|-------------:|-----------------------:|----------------------:|
|  250 | 3.0000 | dm_exact_vs_laplace_u |       -0.3358 |                  0.1500 |                 0.1100 |      -0.1465 |                 0.1900 |                0.1500 |
|  250 | 3.0000 | dm_exact_vs_mle       |       -1.1321 |                  0.2800 |                 0.0400 |      -0.9759 |                 0.3200 |                0.0600 |
|  250 | 6.0000 | dm_exact_vs_laplace_u |        0.6284 |                  0.0600 |                 0.2400 |       0.8101 |                 0.0800 |                0.3100 |
|  250 | 6.0000 | dm_exact_vs_mle       |        0.3948 |                  0.1100 |                 0.2200 |       0.6381 |                 0.1200 |                0.2900 |
| 1000 | 3.0000 | dm_exact_vs_laplace_u |        0.0098 |                  0.1000 |                 0.1100 |       0.1791 |                 0.0900 |                0.1500 |
| 1000 | 3.0000 | dm_exact_vs_mle       |       -0.1078 |                  0.1200 |                 0.0900 |       0.0838 |                 0.1000 |                0.1400 |
| 1000 | 6.0000 | dm_exact_vs_laplace_u |        0.0000 |                  0.0600 |                 0.1000 |       0.0987 |                 0.0600 |                0.1300 |
| 1000 | 6.0000 | dm_exact_vs_mle       |       -0.0762 |                  0.0800 |                 0.0900 |       0.0179 |                 0.0700 |                0.1200 |
