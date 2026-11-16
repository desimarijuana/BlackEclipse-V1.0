# 10. DCF missing year

- runId: `run_697db3b3-cd70-4c4e-ba21-5aefc0e0ee35`
- status: **completed**
- steps: 24 / tools: 34 / toolErrors: 0
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T22:41:02.330Z / finishedAt: 2026-11-16T22:50:45.249Z

## Prompt

Run a DCF for a company using the last 5 years of FCF. If one year is missing, show the gap and compute with the years you have.

## Answer

## Headline

There is **no gap in the FCF history** â Apple's fiscal 2022â2026 give five complete years of free cash flow, so nothing had to be dropped. The DCF output is the interesting part: on a normalized base and a conventional 8% discount rate, intrinsic value lands around **USD 175/share (est.)** against a market price of **USD 352.41**. To justify today's price on the same assumptions, the market must be discounting roughly **22â23% annual FCF growth for five years (est.)**.

Company used: **Apple Inc. (AAPL, NASDAQ, USD)** â none was named; this follows your last valuation request today. Say the word if you meant a different name.

## 1. The five-year FCF series (gap check)

All figures USD millions, fiscal years ending late September, FCF = operating cash flow â capital expenditure.

| Fiscal year | Period end | Operating CF | CapEx | **FCF** | YoY |
|---|---|---|---|---|---|
| FY2022 | 2022-09-24 | 122,151 | (10,708) | **111,443** | +19.89% |
| FY2023 | 2023-09-30 | 110,543 | (10,959) | **99,584** | â10.64% |
| FY2024 | 2024-09-28 | 118,254 | (9,447) | **108,807** | +9.26% |
| FY2025 | 2025-09-27 | 111,482 | (12,715) | **98,767** | â9.23% |
| FY2026 | 2026-09-26 | 145,097 | (9,041) | **136,056** | +37.76% |

**Gap check â five for five, no missing year.** Every row reconciles: OCF â CapEx equals the reported FCF to the dollar in all five periods (e.g. 145,097 â 9,041 = 136,056). 5-year mean **110,931**, median **108,807**, 4-year CAGR from FY2022 **5.12% (est.)**.

The gap was upstream, not in the series: the JDDS vault's stored statements for AAPL stop at FY2019 (one old period), and SEC's XBRL `companyconcept` payload truncated around 2019 and the XBRL `frames` scrapes returned no usable Apple rows in this run. So the series above is **aggregator-standardised data (stockanalysis.com, "as reported", fiscal OctâSep), not a primary filing I read line by line** â treat it as strong secondary evidence, not audited extraction.

## 2. Why FY2026 is not the base case

FY2026 FCF jumped 37.8%, but it is not a working-capital artefact alone â net income rose to 132,175 from 112,010 and OCF rose 30.2%, helped by a 12,171 payables inflow. Using the single latest year would bake a peak into perpetuity, so I run **the 5-year average (110,931) as the primary base** and show the latest-year base as a sensitivity.

## 3. Assumptions (all labelled â these are mine, not reported facts)

| Input | Value | Basis |
|---|---|---|
| Base FCF (year 0) | 110,931 | 5-yr average, est. |
| Stage-1 growth, years 1â5 | 5.12% | Apple's own FY22âFY26 FCF CAGR, est. |
| Terminal growth | 3.0% | assumption, ~long-run nominal GDP |
| Discount rate | 8.0% base, 6â10% grid | **assumption â beta could not be computed, see limits** |
| Net cash added to EV | +42,456 | 56,722 cash & ST investments + 80,213 LT investments â 94,479 total debt |
| Shares | 14,532 mn | FY2026 10-K cover |
| Price | USD 352.41 | JDDS/Yahoo, 2026-11-16 21:43 UTC |
| US 10Y risk-free | 4.88% | FRED DGS10, 2026-11-09 |

## 4. The DCF at 8%

$$EV=\sum_{t=1}^{5}\frac{FCF_0(1+g_1)^t}{(1+r)^t}+\frac{FCF_5(1+g_T)}{(r-g_T)(1+r)^5}$$

| Year | FCF (est.) | PV at 8% |
|---|---|---|
| 1 | 116,611 | 107,973 |
| 2 | 122,566 | 105,081 |
| 3 | 128,858 | 102,271 |
| 4 | 135,444 | 99,556 |
| 5 | 142,401 | 96,915 |
| **PV of years 1â5** | | **511,796** |
| Terminal value (yr 5) | 2,933,460 | 1,996,463 |
| **Enterprise value** | | **2,508,259** |
| + net cash | | 42,456 |
| **Equity value** | | **2,550,715** |
| **Per share (est.)** | | **USD 175.52** |

Terminal value is **79.6% of EV** â high, which is normal for a mature compounder but means the answer is a growth-and-discount-rate statement more than a cash-flow statement.

## 5. Sensitivity â value per share (est.)

| Discount rate | 5-yr avg base (110,931) | FY2026 base (136,056) |
|---|---|---|
| 6% | 291.6 | â |
| 7% | 219.0 | â |
| **8%** | **175.5** | **214.6** |
| 9% | 146.5 | â |
| 10% | 125.8 | â |

At 3% terminal growth, **the 5-year-average base never reaches today's 352.41 at any discount rate from 6% up.** The FY2026 base at 8% gets to 214.6 â still 39% below the price.

## 6. Reverse DCF: what the price requires

Holding 8% / 3% terminal and the normalized 110,931 base, the market's 5,078,694 EV implies **stage-1 FCF growth of roughly 22â23% a year for five years (est.)** â 22% gives ~5,014,000 and 23% gives ~5,211,000, bracketing the target. Using the FY2026 base instead, the implied rate falls to roughly **17â18% (est.)**.

That is the real content of this valuation: Apple is not being priced on its delivered 5.1% FCF CAGR, but on a durable reacceleration. FY2026 was a step in that direction; four of the last five years were not.

## 7. Material limits

- **No WACC was computed.** Beta could not be estimated: the monthly OHLCV route returned an unusable slice (AAPL monthly returned daily bars starting 2022-11), SPY returned daily bars, and the sandbox `price_history` calls failed. With no beta, no cost of debt and no retrieved equity-risk premium, a CAPM WACC would have been invented. The 6â10% grid is the honest substitute; **8% is an assumption, not a derivation.**
- **Non-primary cash-flow data**, cross-checked only for internal consistency, not against the 10-K text.
- `get_market_cap` returned UNAVAILABLE and `get_quote` failed (polygon API key absent); market cap of ~USD 5.12 trn is 14,532 mn shares Ã 352.41, my own product.
- Net cash includes Apple's long-term marketable securities; on a cash-and-ST-investments-only basis net debt is â37,757, which would cut value per share by roughly USD 5.5.
- Not converted to PKR â no USD/PKR rate was retrieved this run.

**What would change the conclusion:** a verified beta plus a retrieved ERP putting WACC near 6.5â7% moves fair value to ~USD 230â260 â closer but still well below the price; or evidence that the FY2026 FCF step-up is structural (services mix, sustained 30%+ OCF growth) rather than a single strong year, which shifts the base toward the 214.6 column. Either would narrow the gap; neither closes it at 8%.

Sources: stockanalysis.com AAPL cash-flow statement and balance sheet (fiscal OctâSep, USD mn, as reported, retrieved 2026-11-16); JDDS/Yahoo quote and P/E 39.29, forward 33.37 (as of 2026-11-16T21:43Z); FRED DGS10 4.88% (2026-11-09). DCF outputs are Eclipse estimates from those inputs.

Data caveat: low: its accounting definition or provenance is unresolved.
