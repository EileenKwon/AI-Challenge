# E4 — Local vs global: near-redundant regime mixture

Truth p = 0.04, s2 = 3.5 (s1 = 1.0 known); 200 replications per n. Exact posterior on a 141x141 grid.

## Coverage of 90% intervals

|    n | functional   |   grid |   laplace_delta |   laplace_push |   mle_wald |
|-----:|:-------------|-------:|----------------:|---------------:|-----------:|
|  250 | es975        | 0.9100 |          0.8400 |         0.8750 |     0.8250 |
|  250 | var95        | 0.9600 |          0.9600 |         0.9550 |     0.9400 |
|  250 | var99        | 0.9000 |          0.8750 |         0.9350 |     0.8550 |
|  250 | var999       | 0.9350 |          0.7950 |         0.8050 |     0.7950 |
| 1000 | es975        | 0.9450 |          0.9100 |         0.9350 |     0.9100 |
| 1000 | var95        | 0.9350 |          0.9350 |         0.9450 |     0.9250 |
| 1000 | var99        | 0.9450 |          0.9350 |         0.9500 |     0.9100 |
| 1000 | var999       | 0.9100 |          0.8950 |         0.8900 |     0.8950 |

## Coverage split by 'hard' datasets (singular-locus mass > 5% or >1 local mode)

|    n | hard   |   grid |   laplace_delta |   laplace_push |   mle_wald |
|-----:|:-------|-------:|----------------:|---------------:|-----------:|
|  250 | False  | 0.9669 |          0.9213 |         0.9351 |     0.9033 |
|  250 | True   | 0.5395 |          0.3553 |         0.4868 |     0.3816 |
| 1000 | False  | 0.9334 |          0.9183 |         0.9296 |     0.9095 |
| 1000 | True   | 1.0000 |          1.0000 |         1.0000 |     1.0000 |

## Median ratio of local SD to exact posterior SD

|    n | functional   |   delta_over_exact |   wald_over_exact |
|-----:|:-------------|-------------------:|------------------:|
|  250 | es975        |             0.7746 |            0.7834 |
|  250 | var95        |             0.9882 |            1.0889 |
|  250 | var99        |             0.7825 |            0.8150 |
|  250 | var999       |             0.7025 |            0.7117 |
| 1000 | es975        |             0.9367 |            0.9438 |
| 1000 | var95        |             1.0018 |            1.0260 |
| 1000 | var99        |             0.9351 |            0.9525 |
| 1000 | var999       |             0.8906 |            0.8932 |

## Multimodality / singular-locus mass

|         n |   frac_multimodal |   mean_sing_mass |
|----------:|------------------:|-----------------:|
|  250.0000 |            0.0200 |           0.0166 |
| 1000.0000 |            0.0050 |           0.0000 |

## VaR99 Bayes-act quantile-score regret

|    n | method       |     mean |   median |
|-----:|:-------------|---------:|---------:|
|  250 | grid         | 0.000638 | 0.000255 |
|  250 | laplace_push | 0.000639 | 0.000254 |
|  250 | mle_wald     | 0.000667 | 0.000235 |
| 1000 | grid         | 0.000186 | 0.000098 |
| 1000 | laplace_push | 0.000184 | 0.000096 |
| 1000 | mle_wald     | 0.000193 | 0.000097 |

Figure: `figures/e4_mixture_example.png`.