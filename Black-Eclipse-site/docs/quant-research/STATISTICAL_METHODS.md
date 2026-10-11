# Statistical Methods

> `last-verified: 2026-10-10`
> Owner code: `python/harness/stats/`

The engine is pure NumPy + the Python standard library. Every method records its
parameters, window, missing-data policy and version in the response envelope; no
method fabricates a value — a computation that cannot be performed honestly
raises a structured `StatsError`.

## Shared contract

- **Envelope** (`base.make_response`): `status, tool, toolVersion, parameters,
  summary, results, diagnostics, warnings, errors, provenance, executionMetadata,
  artifactReferences`.
- **Errors**: `INVALID_INPUT`, `INSUFFICIENT_DATA`, `NUMERICAL_ERROR`,
  `SINGULAR_MATRIX`, `NOT_CONVERGED`, `UNSUPPORTED_METHOD`, `MISSING_DATA`.
- **Missing data** is preserved as `NaN` (never silently zero-filled); policies
  are `reject` / `drop` / `fill_zero` / pairwise, chosen explicitly per call.

## Distributions (`dist.py`)

Implemented from first principles (Numerical Recipes incomplete gamma/beta
continued fractions; normal CDF from the standard library). Verified against
published critical values in `test_stats_dist.py`:
normal, Student-t (cdf/sf/ppf/two-sided p), chi-square (sf), F (sf).

## The fourteen tools

| Tool | Method | Key formulas / conventions |
| --- | --- | --- |
| `calculate_returns` | simple/log/cumulative/rolling/lagged/excess | `r_t = P_t/P_{t-1}-1`; `r_t = ln(P_t/P_{t-1})` (positive prices); wealth `∏(1+r)` |
| `calculate_volatility` | rolling std/var, EWMA, Parkinson, Garman–Klass, GARCH(1,1) | annualize ×√periods; EWMA `σ²_t = λσ²_{t-1}+(1-λ)r²_{t-1}`; GARCH MLE (Gaussian) |
| `calculate_correlation` | Pearson, Spearman, Kendall τ-b; covariance; matrices; rolling | pairwise/listwise/reject missing policy; t-test (Pearson), Fisher-z (rank) |
| `calculate_beta` | market-model OLS | `β=Σ(x-x̄)(y-ȳ)/Σ(y-ȳ)²`; alpha per-period and annualized; HC0/HC1/HC3/HAC SEs |
| `calculate_drawdown` | episodes | `DD_t = P_t/peak_t - 1`; start/trough/recovery; duration in observations + elapsed time |
| `calculate_stationarity` | ADF, KPSS | ADF: Δy on lagged level + lagged Δy, AIC/BIC lag selection; KPSS: LM with Bartlett long-run variance. MacKinnon / Kwiatkowski critical values |
| `calculate_cointegration` | Engle–Granger, Johansen | EG residual ADF with cointegration critical values; Johansen trace test from the generalized eigenvalue problem |
| `calculate_autocorrelation` | ACF, PACF, Ljung–Box | ACF via autocovariance; PACF via Durbin–Levinson; `Q = n(n+2)Σ r_k²/(n-k) ~ χ²_h` |
| `calculate_regression` | OLS/WLS/HC/HAC/ridge/lasso | ridge closed form (intercept unpenalized); lasso coordinate descent; chronological OOS split (never shuffled) |
| `calculate_regime` | volatility, trend/range, change-point, 2-state HMM | quantile vol regimes; slope/vol trend; variance binary segmentation; Baum–Welch + Viterbi |
| `build_features` | framework + formula | causal transforms only; each feature reports lookback, warm-up, missingness, PIT safety |
| `detect_outliers` | z-score, MAD, IQR, isolation forest | modified z `0.6745(x-μ̃)/MAD`; IQR fences; isolation forest path-length score |
| `analyze_lead_lag` | cross-correlation, lagged regression, Granger | positive lag k ⇒ predictor leads target by k; Granger F-test with Bonferroni control |
| `calculate_information_coefficient` | cross-sectional, time-series, decay | per-date correlation averaged; mean IC, std, IR, hit rate, t/p; forward target `P_{t+h}/P_t-1` |

## Integrity rules

- **Point-in-time**: every built-in feature transform is causal (value at `t`
  uses only data up to `t`). Forward-return targets start at `t` and are used
  only as the evaluation target, never as a feature.
- **Frequency-aware annualization**: `periodsPerYear` is explicit (252 equities,
  365 crypto daily, intraday scaled); 252 is never assumed for every instrument.
- **No causal overreach**: correlation ≠ causation; cointegration ≠ correlation;
  a fitted IC is not evidence of out-of-sample value. These are stated in the
  response warnings and `docs/quant-research/IMPLEMENTATION_STATUS.md`.

## Regression / inference robustness

Standard errors support classical, HC0/HC1/HC3 and Newey–West (HAC) covariance.
`calculate_regression` separates in-sample fit from a chronological out-of-sample
evaluation; time order is never shuffled.
