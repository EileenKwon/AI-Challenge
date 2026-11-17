# E10 — Pre-registered confirmation: learned design policy in SV

Frozen E9 networks, fresh seeds, 150 replications per truth (evsi_global on 50 per truth).

| test                                 | family    |   n |   ratio |   median_ratio |   frac_first_better |   ci_lo |   ci_hi |       p_t |   p_wilcoxon |
|:-------------------------------------|:----------|----:|--------:|---------------:|--------------------:|--------:|--------:|----------:|-------------:|
| H10 learned/copt (SV pooled, 300)    | primary   | 300 |  0.9253 |         0.8338 |              0.4833 |  0.8373 |  1.026  | 0.1329    |    0.5998    |
| learned/copt (regular)               | secondary | 150 |  0.8059 |         0.8609 |              0.52   |  0.6809 |  0.9386 | 0.01247   |    0.1385    |
| learned/copt (weak)                  | secondary | 150 |  1.045  |         0.9848 |              0.4467 |  0.9432 |  1.188  | 0.467     |    0.4776    |
| learned/evsi_global (SV pooled, 100) | secondary | 100 |  0.4564 |         0.3983 |              0.57   |  0.3422 |  0.6021 | 0.0001994 |    0.0005219 |
| copt/evsi_global (SV pooled, 100)    | secondary | 100 |  0.4899 |         0.4437 |              0.54   |  0.3639 |  0.6426 | 0.0003247 |    0.0001317 |
| uniform/copt (SV pooled, 300)        | secondary | 300 |  0.9315 |         0.7613 |              0.4567 |  0.844  |  1.025  | 0.1485    |    0.9119    |

CPU seconds per run: copt 2.8, evsi_global 49.3, learned 2.8, uniform 2.8

Batches bought per source:

| truth   | policy      |   peer |   rv |   rv_hf |
|:--------|:------------|-------:|-----:|--------:|
| regular | copt        |   2.34 | 2.59 |    1.07 |
| regular | evsi_global |   1.20 | 4.20 |    0.60 |
| regular | learned     |   1.47 | 1.57 |    2.96 |
| regular | uniform     |   2.00 | 2.00 |    2.00 |
| weak    | copt        |   0.48 | 3.93 |    1.59 |
| weak    | evsi_global |   0.24 | 4.98 |    0.78 |
| weak    | learned     |   1.62 | 1.70 |    2.68 |
| weak    | uniform     |   2.00 | 2.00 |    2.00 |