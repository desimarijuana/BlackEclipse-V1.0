# 29. Retry after provider down

- runId: `run_db19884a-810a-4a62-883b-82e5c41864b0`
- status: **completed**
- steps: 6 / tools: 8 / toolErrors: 0
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T22:04:16.036Z / finishedAt: 2026-11-16T22:04:47.267Z

## Prompt

Try again - the first provider was down. Get me AAPL's latest quote using a backup route and tell me what you tried.

## Answer

**The first route that failed is Polygon â it has no API key. The quote itself came through fine on the backup route.**

AAPL closed at **352.78 USD** on the Nov 16, 2026 session, **-0.98%** (-3.46) on the day, retrieved live at 22:04 UTC from yfinance. The US market closed at 21:00 UTC (4:00 PM EST), so this is the official closing print, not an intraday tick. After-hours last was 352.50 (-0.09%) as of 4:06 PM EST.

| # | Route | Result |
|---|---|---|
| 1 | `get_quote` (Polygon) | â AUTHENTICATION_FAILED â `POLYGON_API_KEY` not configured |
| 2 | `market_get_quote` (unified layer â JDDS) | â Returned data â **but** the route is flagged as recorded-failing for US quotes |
| 3 | `get_market_snapshot` | â Cross-checked price, flagged P/E as a 1-hour-old saved snapshot |
| 4 | `broker_quote` (MT5 terminal) | â TERMINAL_NOT_RUNNING |
| 5 | `web_extract` stockanalysis.com | â Independent confirmation: 352.81 close, 352.50 after-hours, prev close 356.27 |

So two of the five routes are genuinely dead â Polygon (missing credential) and the MT5 broker feed (terminal not running). The yfinance-backed structured route is the one that works, and `get_provider_health` confirms it: yfinance live_quote is **HEALTHY** across every cohort (0â2 failures out of thousands), while **JDDS live_quote is FAILING** outright (0 successes, 1,604 failures) and `LIVE_STRUCTURED` along with it. That's why the successful quote still carried those "route is recorded as failing" warnings â it was served by the yfinance leg inside the wrapper, not by JDDS.

Two data-quality flags worth knowing before you use these numbers:

- **P/E disagrees across sources.** The saved snapshot says 36.37, stockanalysis says 39.29 (on EPS 8.98, TTM to the FY2026 period). These are different EPS bases and the 36.37 figure is roughly an hour stale â treat 39.29 as the better-supported reading, or recompute once you fix the EPS basis you want.
- **Volume differs** (45.01M from yfinance vs 43.60M on the web page). Usually consolidated-vs-primary-exchange tape, not a real conflict.

Other confirmed figures from the web cross-check [web: stockanalysis.com, as of Nov 16 2026 4:00 PM EST]: market cap 5.13T, open 357.13, day's range 351.31â357.13, 52-week range 243.42â360.83, dividend 1.08 (0.31%), ex-div Nov 12 2026.

If you want Polygon back online, the fix is adding `POLYGON_API_KEY` to the provider config â say the word and I'll note the exact gap for the operator.
