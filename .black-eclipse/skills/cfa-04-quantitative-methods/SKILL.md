# CFA Level I — Quantitative Methods

> **Not affiliated with CFA Institute.** These are original study notes, not CFA Institute materials. "CFA" is a trademark of CFA Institute. See `../CFA-NOTICE.md`.

**Weight 11-14% (was 6-9%) · 11 modules · fourth topic in the study order.**
Quantitative Methods roughly doubled in 2027. It now carries the second-heaviest
weight in the exam and a module that did not previously exist. A pre-2026 course
is materially incomplete for it.

## Learning modules (official 2027)

| # | Module | Focus |
|---|---|---|
| 1 | Returns of Financial Assets and Instruments | Describe and compare returns; required return, risk-free rate, risk premium, inflation |
| 2 | Types of Financial Returns | Calculate and compare different return types for assets, instruments and indicators |
| 3 | Benchmarking Returns | **Money-weighted vs time-weighted return**; index construction weighting choices; index value and return |
| 4 | The Time Value of Money in Finance | Present value of fixed-income and equity instruments from expected cash flows; implied return; **cash flow additivity** and why it underpins no-arbitrage, implied forward rates, forward FX rates and option values |
| 5 | Statistical Characteristics of Asset Returns | Central tendency and location; dispersion; **skewness and kurtosis**; covariance and correlation; semi-deviation and coefficient of variation |
| 6 | Statistical Distributions for Financial Asset Prices and Returns | Unconditional expected values for mean, variance, covariance; principal moments of key distributions; conditional expectations and variances; **Bayesian updating** |
| 7 | Estimation and Hypothesis Testing | Central limit theorem; confidence intervals; sampling; **hypothesis testing components: significance, Type I and Type II errors, power**; parametric vs non-parametric tests |
| 8 | The Return and Risk of a Financial Portfolio | Expected return, variance, standard deviation, covariance, correlation of portfolio returns; **minimum-variance portfolio and efficient frontier**; optimal portfolio under risk aversion, the capital allocation line, the market portfolio and the capital market line |
| 9 | Simulation of Financial Asset Prices and Returns | **Historical simulation; bootstrap resampling; Monte Carlo** — and how each is used in investment applications |
| 10 | Applications of Simple Linear Regression in Finance | Simple linear regression and least squares; assumptions and residual analysis; goodness of fit and ANOVA; predicted values, standard error of the estimate, prediction intervals; functional forms; **CAPM variable estimates** |
| 11 | **Introduction to Financial Data Science** | How **big data, machine learning and artificial intelligence** are used in financial data science, fintech and investment management |

**New in 2027:** module 11 (financial data science) is entirely new; modules 6, 8
and 9 were substantially expanded (Bayesian updating, portfolio optimisation, and
all three simulation methods).

## What to learn first

1. **Modules 1-4** (returns, benchmarking, TVM) — concrete and directly reused by
   Equities and Fixed Income.
2. **Modules 5-7** (statistics, distributions, estimation) — the inference core;
   needs the prerequisite maths (see the quant-foundations section inside
   `cfa.99.exam-preparation`).
3. **Module 8** (portfolio risk and return) — overlaps Portfolio Construction;
   learn them close together.
4. **Module 10** (regression) — calculable and reliably examined.
5. **Modules 9 and 11** (simulation, data science) — largely descriptive per the
   outcome verbs; do not over-invest in computation.

## Tier 1 — must memorise

- **Holding period return**; **geometric vs arithmetic mean** and when each is
  right.
- **Money-weighted (IRR) vs time-weighted return**, and which is appropriate when
  the manager does not control cash flows.
- **Effective annual rate** from a stated rate: (1 + stated/m)^m - 1.
- **Continuous compounding** and the role of *e*.
- **Cash flow additivity** and its use for implied forward rates.
- **Coefficient of variation** = standard deviation / mean.
- **Semi-deviation** definition (downside-only dispersion).
- **Skewness sign** (positive = long right tail) and **kurtosis** (excess kurtosis
  > 0 = fat tails).
- **Bayes:** posterior is proportional to likelihood x prior; know the two-state
  update.
- **Standard error** = standard deviation / square root of n; **t-statistic** =
  (estimate - hypothesised value) / standard error; **confidence interval** =
  estimate +/- (critical value x standard error).
- **Type I error** = rejecting a true null; **Type II** = failing to reject a
  false null; **power** = 1 - Type II.
- **Regression:** slope, intercept, R-squared, standard error of the estimate,
  prediction interval, and the **CAPM variable estimates**.
- **Portfolio expected return** and **portfolio variance** (shared with Portfolio
  Construction).

## Tier 2 — must understand

- Why time-weighted return is the fair measure of manager performance.
- The central limit theorem's practical implication for sample means.
- Parametric vs non-parametric: when normality fails, use the non-parametric test.
- The three simulation methods as a comparison — data-driven (historical,
  bootstrap) vs assumption-driven (Monte Carlo), and what each assumes.
- What regression assumptions are, and how residual analysis reveals violations.
- How to read an ANOVA table's regression and residual components.
- Conceptual machine learning and AI in investment management (supervised vs
  unsupervised, and the fintech applications) — descriptive only.

## Common traps

- **Money-weighted vs time-weighted confusion** — use the IRR when cash flows are
  the manager's, TWR when they are not.
- Reversing **Type I and Type II** errors under time pressure.
- Forgetting that **excess kurtosis** is what is reported (a normal distribution
  has zero excess).
- Mixing **population and sample** standard deviation denominators.
- Using the **wrong tail or wrong critical value** in a one- vs two-tailed test.
- Treating **Monte Carlo as data-driven** — it is assumption-driven, so its output
  is only as good as the assumed distribution.
- Assuming **bootstrap resampling creates new information** — it resamples what
  was observed.
- Reading **R-squared as a quality proof** rather than a share of variance
  explained.
- Over-studying module 11 (data science) computationally — the outcomes are
  descriptive.

## Typical question patterns

- Compute and compare money-weighted and time-weighted returns for the same fund.
- Calculate a confidence interval or run a one-sample t-test and interpret it.
- Given skewness and kurtosis, characterise the distribution.
- A two-state Bayesian update.
- Interpret regression output: is the slope significant, what is R-squared, what
  does the standard error imply.
- A comparison item on two simulation methods, or on parametric vs non-parametric.
- A conceptual item on AI/ML use in investment management.

## Free resources for this topic

- Official curriculum and topic questions: the Learning Ecosystem.
- Learning outcomes: the free 2027 Level I Topic Outlines PDF.
- Prerequisite maths and statistics: a free statistics/probability course and an
  open statistics textbook.
- Regression practice: a free Level I question bank.

## Practice target and revisits

- **220-280 questions** — the topic doubled in weight, so the volume should be
  higher than the pre-2027 material would suggest.
- Revisit before every mock from mock 2 onward, and again in revision.

## Dependencies

- Needs: the quantitative prerequisites (algebra, logarithms, descriptive
  statistics, probability) — see `cfa.99.exam-preparation`.
- Feeds: Equities (CAPM, required return), Portfolio Construction (portfolio maths,
  regression), Fixed Income (discounting, term structure).

## Failure handling

- If the user's statistics base is weak, do not start module 5+ — route to the
  prerequisites in `cfa.99.exam-preparation` first. A weak base here propagates
  through three topics.
