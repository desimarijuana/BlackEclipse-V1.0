# CFA Level I — Equities

> **Not affiliated with CFA Institute.** These are original study notes, not CFA Institute materials. "CFA" is a trademark of CFA Institute. See `../CFA-NOTICE.md`.

**Weight 11-14% · 12 modules · first topic in the study order.** Equities is the
largest topic block alongside Fixed Income and Financial Statement Analysis, and
it supplies the vocabulary (returns, risk, beta, valuation) the rest of the exam
reuses.

## Learning modules (official 2027)

| # | Module | What it demands |
|---|---|---|
| 1 | Equity Instrument Features | Describe features/types of equity; listed vs private (contrast) |
| 2 | Equity Jurisdictions, Classes, and the Voting Process | Economic vs voting rights; classes; the voting process and its actors |
| 3 | Equity Issuance and Trading | Primary vs secondary markets; exchange/OTC/off-exchange; float and average daily volume (calculate); liquidity measures; index types |
| 4 | Sources of Equity Returns | Dividends, buybacks, splits and reverse splits; **dividend payment chronology**; calculate price and total return |
| 5 | Introduction to Equity Valuation | Price vs value; book value vs market cap vs enterprise value; model categories and their advantages/disadvantages |
| 6 | Discounted Cash Flow (DCF) and Growth Models | DDM, FCFE, FCFF, residual income inputs; constant and multistage growth **computation**; shortcomings of growth assumptions; preferred stock valuation |
| 7 | Relative Value Equity Valuation Approaches | Method of comparables vs forecasted fundamentals; price and enterprise-value multiples (calculate); peer-group selection |
| 8 | Financial Statement Forecasting in Equity Valuation | Sales-based forecast models; how to evaluate a model's construction; estimate value from model outputs |
| 9 | Industry and Competitive Analysis | Industry classification; size, growth, profitability, market share; **Porter's Five Forces and PESTLE** |
| 10 | Company Analysis: Past, Present, and Future | Competitive strategy and position; revenue drivers, operating profitability, pricing power; working capital, capital investment, capital structure |
| 11 | Equity Analyst Research Reports | Report elements; sell-side vs buy-side; why the same model yields different value estimates |
| 12 | The Capital Asset Pricing Model, Market Model, and Other Factor-Based Equity Models | CAPM and market model to estimate required return on equity; arbitrage pricing theory and multi-factor models |

**New in 2027:** modules 8-11 (forecasting, industry analysis, company analysis,
analyst reports) and the multi-factor content in module 12 are the expansion — a
pre-2026 course will not cover them.

## What to learn first

1. **Modules 1-4** (instruments, issuance, returns) — concrete, low calculation,
   builds vocabulary.
2. **Module 12 (CAPM / required return)** next, before valuation: every DCF model
   needs a discount rate, and `r` comes from here.
3. **Modules 5, 6 and 7** (valuation) — the calculation-heavy core.
4. **Modules 8-11** (forecasting, industry, company, reports) — descriptive and
   applied; read fast, they reward recognition over computation.

## Tier 1 — must memorise

- **Total return** = (P1 - P0 + dividends) / P0. **Price return** excludes income.
- **Gordon growth (constant growth DDM):** V0 = D1 / (r - g), where r > g.
- **Multistage:** discount each explicit-period dividend, then a terminal value at
  the horizon using the constant-growth formula.
- **Preferred stock:** V0 = D / r.
- **CAPM required return:** r = Rf + beta x (Rm - Rf).
- **Justified trailing P/E** = payout ratio x (1 + g) / (r - g); **justified
  forward P/E** = payout ratio / (r - g).
- **Enterprise value (EV)** = market value of equity + market value of debt -
  cash and short-term investments.
- **EV/EBITDA**, **P/E, P/B, P/S** definitions and what each suits.
- **Average daily volume** and **float** calculations (module 3).

## Tier 2 — must understand

- Which model suits which company (dividend-paying or not; stable or high growth).
- Why price and intrinsic value differ, and what that implies.
- The advantages/disadvantages of each valuation model category (module 5 is
  examined on this directly).
- How book value, market cap and EV differ as "value" indicators.
- Free cash flow to equity vs to the firm inputs (overlaps Fixed Income and FSA).
- The difference between sell-side and buy-side research.

## Common traps

- **Using D0 instead of D1** in the Gordon growth formula — the numerator is the
  *next* period's dividend.
- Applying Gordon growth when **g >= r** — the model is undefined; the question
  tests whether you notice.
- Confusing **price return with total return** (forgetting dividends).
- Mixing **trailing and forward P/E** — the payout-ratio form differs by (1+g).
- Forgetting to net **cash** out of EV, and to include short-term investments.
- Treating a **stock split** as a return event — it changes price per share, not
  the investor's wealth.
- Assuming a multi-factor model replaces CAPM rather than extending it.
- Selecting a peer group by industry label only when the question stresses
  "drivers of expected return".

## Typical question patterns

- Calculate intrinsic value under constant growth, then state whether the stock is
  over- or undervalued versus price.
- Calculate a justified multiple and compare it with the actual multiple.
- Convert a required return into a discount rate for a multistage problem.
- Classify a dividend/split/buyback event under "sources of equity returns".
- "Most likely" items on model selection and on the shortcomings of growth
  assumptions.
- Identify whether a described practice is sell-side or buy-side research.

## Free resources for this topic

- Official curriculum and topic questions: the Learning Ecosystem (included with
  registration).
- Learning outcomes per module: the free 2027 Level I Topic Outlines PDF.
- Video: a free topic-by-topic Level I video course (use as a supplement).
- Question volume: a free third-party Level I question bank.

## Practice target and revisits

- **180-240 questions** across the topic.
- Revisit after Fixed Income (duration and beta reinforce each other) and once
  more in the revision phase — valuation formulas decay fastest.

## Dependencies

- Needs: CAPM and portfolio maths (module 12 here, and Quantitative Methods);
  ratio work from Financial Statement Analysis for the multiple-based methods.
- Feeds: Portfolio Construction (beta, required return) and Fixed Income (the same
  discounting discipline).

## Failure handling

- A valuation question missing either the discount rate or the growth assumption
  -> state what is missing rather than assuming a default.
