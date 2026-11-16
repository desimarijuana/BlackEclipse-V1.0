# CFA Level I — Portfolio Construction

> **Not affiliated with CFA Institute.** These are original study notes, not CFA Institute materials. "CFA" is a trademark of CFA Institute. See `../CFA-NOTICE.md`.

**Weight 8-12% · 6 modules · second topic in the study order.** Only six modules
but a high weight — the best marks-per-module topic on the exam. It also carries
the risk and performance machinery (beta, CAPM, Sharpe, Treynor) that Equities and
Quantitative Methods reuse.

## Learning modules (official 2027)

| # | Module | What it demands |
|---|---|---|
| 1 | Portfolio Risk and Return: Part I | Major asset class characteristics; risk aversion; optimal portfolio with utility and the capital allocation line; calculate mean, variance, covariance from historical data; **portfolio standard deviation**; effect of imperfect correlation; minimum-variance and efficient frontiers |
| 2 | Portfolio Risk and Return: Part II | Risk-free asset combined with risky assets; **CAL and CML**; systematic vs nonsystematic risk; return-generating models including the market model; calculate beta; **CAPM and the SML**; Sharpe ratio, Treynor ratio, M-squared, Jensen's alpha |
| 3 | Portfolio Management: An Overview | The portfolio approach; the steps in the portfolio management process; types of investors; defined contribution vs defined benefit plans; the asset management industry; mutual funds and pooled products |
| 4 | Basics of Portfolio Planning and Construction | Why a written **IPS**; its components; risk and return objectives; **willingness vs ability to take risk**; constraints (liquidity, time horizon, tax, legal/regulatory, unique); asset classes and asset allocation; ESG integration |
| 5 | The Behavioral Biases of Individuals | **Cognitive errors vs emotional biases**; the recognised biases and their implications; how biases create market characteristics traditional finance cannot explain |
| 6 | Introduction to Risk Management | Risk management definition and framework; risk governance; risk tolerance; risk budgeting; financial and non-financial sources of risk; measuring and modifying exposures |

## What to learn first

1. **Module 1** — the maths foundation. Portfolio variance needs covariance, so
   pair it with the Quantitative Methods statistical work.
2. **Module 2** — the examinable core. CAL, CML, SML, beta, CAPM and the four
   performance measures all live here and all get asked.
3. **Modules 3-4** — the descriptive IPS material; high marks for low effort.
4. **Module 5** — behavioural biases: pure memorisation, reliably examined.
5. **Module 6** — risk management framework; mostly descriptive.

## Tier 1 — must memorise

- **Expected portfolio return:** E(Rp) = sum of (weight x expected return).
- **Two-asset portfolio variance:** the w1^2-sigma1^2 + w2^2-sigma2^2 +
  2-w1-w2-rho-sigma1-sigma2 form. Know it in both the covariance and correlation
  versions.
- **Correlation from covariance:** rho = covariance / (sigma1 x sigma2).
- **Beta:** beta = covariance(asset, market) / variance(market).
- **CAPM:** E(R) = Rf + beta x (E(Rm) - Rf) — the same formula as in Equities.
- **Capital allocation line:** E(Rp) = Rf + [(E(Ri) - Rf) / sigma-i] x sigma-p. Its
  slope is the **Sharpe ratio**.
- **Four performance measures:** Sharpe = (Rp - Rf) / sigma-p; Treynor = (Rp - Rf)
  / beta; M-squared; Jensen's alpha = Rp - [Rf + beta(Rm - Rf)].
- **Utility:** U = E(R) - 0.5 x A x sigma-squared; higher A means more risk-averse.
- **SML vs CML:** the CML plots total risk (standard deviation) and applies only to
  efficient portfolios; the SML plots beta and applies to any asset.

## Tier 2 — must understand

- Why nonsystematic risk earns no additional return.
- The distinction between the CAL, the CML and the SML (a classic item).
- Willingness vs ability to take risk — **ability wins** when they conflict;
  willingness may be educated, ability cannot be created.
- Cognitive errors vs emotional biases, and how the remedy differs (education vs
  adaptation).
- Risk budgeting and the risk-governance chain.

## Common traps

- **Confusing the CML and the SML.** The CML uses standard deviation and holds
  only for efficient portfolios; the SML uses beta and holds for all assets.
- Using **beta where standard deviation belongs** (or the reverse) in Sharpe vs
  Treynor.
- Forgetting the **risk-free rate** in Jensen's alpha, or mismatching the beta.
- Treating **systematic and nonsystematic risk as interchangeable** — only
  systematic is priced.
- Getting **willingness/ability backwards** when a client is risk-averse but has a
  long horizon and high capacity.
- Assuming zero correlation removes all portfolio risk — variance still contains
  the two squared terms.
- Calling a **cognitive error** an emotional bias when the scenario describes a
  reasoning mistake.

## Typical question patterns

- Compute portfolio expected return or standard deviation from weights and inputs.
- Compute and compare Sharpe, Treynor, M-squared and Jensen's alpha for two funds
  and state which performed better under a given measure.
- Identify the missing IPS component in a scenario.
- Classify a described behaviour as a specific bias, then as cognitive or
  emotional.
- "Least appropriate" items on the steps in the portfolio management process.

## Free resources for this topic

- Official curriculum plus topic questions: the Learning Ecosystem.
- Learning outcomes: the free 2027 Level I Topic Outlines PDF.
- Portfolio maths practice: a free Level I question bank.
- Video supplement: a free Level I video course.

## Practice target and revisits

- **150-200 questions** — only six modules, so the per-module volume is high.
- Revisit alongside Equities: the beta/CAPM material is shared and one pass
  reinforces the other.

## Dependencies

- Needs: the statistical work (covariance, variance, regression) from
  Quantitative Methods; returns from Equities.
- Feeds: nothing downstream, but it shares its formulas with Equities and Fixed
  Income, which is what makes it the natural second topic.

## Failure handling

- A performance-measure question that does not state which risk measure applies ->
  say so; Sharpe uses total risk, Treynor and Jensen's alpha use systematic risk.
