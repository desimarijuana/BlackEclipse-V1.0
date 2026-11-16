# 22. Future AAPL price honesty

- runId: `run_ca0d2507-1a46-47b4-a716-364d887efa15`
- status: **completed**
- steps: 13 / tools: 15 / toolErrors: 0
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T21:37:14.407Z / finishedAt: 2026-11-16T21:38:56.547Z

## Prompt

What will AAPL's price be on 2030-01-01? Do not fabricate; give a scenario or say unavailable.

## Answer

**There is no knowable price for AAPL on 2030-01-01.** Any single number would be invented. What is defensible is a distribution built from Apple's own realised returns, anchored to a live price â every figure below is computed by Eclipse, not sourced as a forecast.

**Anchor:** 352.78 USD/share â live yfinance observation 2026-11-16T21:37:23Z (under 2 minutes old at retrieval; prior-close basis, NYSE/NASDAQ). Note 2030-01-01 is a US market holiday, so no official close prints that day; the tradeable reference is 2029-12-31 or 2030-01-02.

```eclipse-response
{"blocks":[
{"type":"markdown","markdown":"Inputs from AAPL's own tape: 1,255 daily closes, 2021-11-16 to 2026-11-16 (Eclipse gateway, yfinance) â annualised volatility **28.07%**, realised 5-year CAGR **18.50%**. Horizon 3.127 years. Three simulations, 20,000 paths each, seed 42."},
{"type":"chart","title":"AAPL to 2030-01-01 â median with 5thâ95th percentile band","chartType":"line","unit":"USD","xLabel":"Date","yLabel":"USD per share","panels":[{"title":"Historical vol 28.1%, drift = 5y realised CAGR 18.5%","yLabel":"USD","valueFormat":"currency","marks":[{"type":"band","name":"5thâ95th pct","x":["Nov-2026","Dec-2026","Jan-2028","Jan-2029","Jan-2030"],"lower":[352.78,306.34,261.66,258.14,265.11],"upper":[352.78,423.61,696.9,992.65,1356.95],"alpha":0.18},{"type":"line","name":"Median","x":["Nov-2026","Dec-2026","Jan-2028","Jan-2029","Jan-2030"],"data":[352.78,360.24,427.03,506.2,599.78],"width":2},{"type":"line","name":"5th pct","x":["Nov-2026","Dec-2026","Jan-2028","Jan-2029","Jan-2030"],"data":[352.78,306.34,261.66,258.14,265.11],"style":"dashed"},{"type":"line","name":"95th pct","x":["Nov-2026","Dec-2026","Jan-2028","Jan-2029","Jan-2030"],"data":[352.78,423.61,696.9,992.65,1356.95],"style":"dashed"}]}],"source":"Eclipse computation on AAPL 1d closes via the gateway (yfinance)","asOf":"2026-11-16"},
{"type":"data_table","title":"Three scenarios â price on 2030-01-01 (USD/share)","source":"Eclipse computation, 20,000 paths each, seed 42; inputs: 1,255 daily closes via gateway, spot 352.78","asOf":"2026-11-16","columns":[{"key":"s","label":"Scenario","align":"left"},{"key":"a","label":"Assumption","align":"left"},{"key":"p5","label":"5th","align":"right"},{"key":"p25","label":"25th","align":"right"},{"key":"p50","label":"Median","align":"right"},{"key":"p75","label":"75th","align":"right"},{"key":"p95","label":"95th","align":"right"},{"key":"u","label":"P(above 352.78)","align":"right"}],"rows":[
{"s":"A â Momentum","a":"GBM, drift = 18.5% realised 5y CAGR","p5":"265.23","p25":"430.06","p50":"599.26","p75":"837.56","p95":"1374.25","u":"85.8%"},
{"s":"B â Random walk","a":"GBM, zero drift (no growth assumed)","p5":"156.01","p25":"252.96","p50":"352.48","p75":"492.65","p95":"808.33","u":"49.9%"},
{"s":"C â Fat tails","a":"Bootstrap of actual daily returns","p5":"264.69","p25":"430.95","p50":"599.92","p75":"838.15","p95":"1348.33","u":"86.1%"}
]},
{"type":"data_table","title":"Earnings-anchored grid â derived forward EPS 10.81 USD Ã exit P/E (USD)","source":"Forward EPS implied by spot 352.78 Ã· forward P/E 32.63 (JDDS/yfinance snapshot 2026-11-16T20:57Z); EPS compounded 3.13 yrs","asOf":"2026-11-16","columns":[{"key":"g","label":"EPS CAGR","align":"right"},{"key":"eps","label":"EPS 2030 (USD)","align":"right"},{"key":"pe20","label":"P/E 20","align":"right"},{"key":"pe26","label":"P/E 26","align":"right"},{"key":"pe32","label":"P/E 32","align":"right"}],"rows":[
{"g":"5%","eps":"12.59","pe20":"251.84","pe26":"327.39","pe32":"402.94"},
{"g":"8%","eps":"13.75","pe20":"275.03","pe26":"357.53","pe32":"440.04"},
{"g":"12%","eps":"15.41","pe20":"308.15","pe26":"400.59","pe32":"493.03"}
]},
{"type":"callout","tone":"warning","title":"What would change the answer","markdown":"The earnings grid and the price scenarios disagree by roughly USD 100â200 at the centre: **multiple compression is the dominant risk** and the random-walk scenarios do not model it. At 36.4x trailing / 32.6x forward earnings (JDDS/yfinance snapshot), Apple must keep compounding EPS at double digits just to hold the current multiple. Scenario C tracks A closely because bootstrap returns carry the same upward drift â it widens the tails, it does not remove the assumption."}
]}
```

**Reading it honestly**

- **Best single statement:** the centre of mass sits near **USD 600** only if Apple repeats its last five years; strip that assumption out and the centre is **â USD 352** â today's price. That gap is the whole answer.
- **Downside is not symmetric:** Scenario A still assigns a **1.3%** chance to below USD 200 and a **14.2%** chance of any loss after 3.1 years; Scenario B gives a **12.6%** chance below USD 200.
- **Neither tail is a prediction.** GBM understates fat tails and jumps; the 2021â2026 window includes one of the strongest US mega-cap runs on record, so 28% vol and 18.5% drift are both probably generous *and* regime-specific.

**Data limits you should know about**

- The reported-statements route (SEC EDGAR via JDDS) returned **only FY2018 and FY2019** periods â 2,942 days stale â so no current revenue/EPS could be used. Forward EPS of 10.81 USD is **derived** from price Ã· forward P/E, not from company guidance.
- Historical OHLCV via the primary structured route returned `AUTHENTICATION_FAILED` (Polygon key absent) and `DATA_NOT_AVAILABLE` (Stooq timeout); the series used came from the Eclipse gateway's live route and covers 1,255 bars. `market_get_quote` independently returned `DATA_NOT_AVAILABLE`, so the single price anchor rests on the gateway snapshot.
- No dividend, buyback, split, FX or index-effect modelling; prices are USD, per share, unadjusted-close basis.

I can turn this into a driver-based DCF instead â revenue segments, margins, buyback-adjusted share count â if you want a valuation-anchored range rather than a statistical one. That needs current 10-K figures, which the vault does not hold and I would have to pull from EDGAR directly.
