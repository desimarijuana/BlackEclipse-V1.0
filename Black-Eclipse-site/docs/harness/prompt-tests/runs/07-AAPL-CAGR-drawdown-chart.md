# 7. AAPL CAGR drawdown chart

- runId: `run_8412b8f5-edbe-4826-9241-0e38b7654122`
- status: **completed**
- steps: 20 / tools: 27 / toolErrors: 0
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T18:15:55.843Z / finishedAt: 2026-11-16T18:20:43.782Z

## Prompt

Pull AAPL's last 5 years of monthly prices, compute CAGR and max drawdown, and draw a chart. If the first provider fails, try another route before answering.

## Answer

## AAPL â 5 years of monthly prices, CAGR and maximum drawdown

**Headline:** over 2021-11-16 â 2026-11-16, AAPL compounded at **15.47% a year** (adjusted, dividends reinvested), for a **+104.05%** total return, with a worst peak-to-trough fall of **-26.40%** â fully recovered.

```eclipse-response
{"blocks":[{"type":"metric_grid","title":"AAPL â 5-year monthly statistics","asOf":"2026-11-16","source":"Yahoo Finance chart API (adjusted close, monthly)","columns":3,"metrics":[{"label":"5Y CAGR","value":15.47,"unit":"%","deltaTone":"up","hint":"((353.66/173.32)^(1/4.958)-1), dividend-adjusted"},{"label":"Max drawdown","value":-26.4,"unit":"%","deltaTone":"down","hint":"Dec-2021 peak â Dec-2022 trough; recovered"},{"label":"Total return","value":104.05,"unit":"%","deltaTone":"up","hint":"173.32 â 353.66"}]},{"type":"chart","chartType":"line","title":"AAPL monthly adjusted close, Nov 2021 â Nov 2026","description":"Dividend-adjusted monthly closes. Peak 173.32 (Dec-2021) to trough 127.55 (Dec-2022) is the -26.40% max drawdown.","source":"Yahoo Finance chart API","asOf":"2026-11-16","currency":"USD","xLabel":"Month","yLabel":"Adjusted close (USD)","categories":["2021-12","2022-01","2022-02","2022-03","2022-04","2022-05","2022-06","2022-07","2022-08","2022-09","2022-10","2022-11","2022-12","2023-01","2023-02","2023-03","2023-04","2023-05","2023-06","2023-07","2023-08","2023-09","2023-10","2023-11","2023-12","2024-01","2024-02","2024-03","2024-04","2024-05","2024-06","2024-07","2024-08","2024-09","2024-10","2024-11","2024-12","2025-01","2025-02","2025-03","2025-04","2025-05","2025-06","2025-07","2025-08","2025-09","2025-10","2025-11","2025-12","2026-01","2026-02","2026-03","2026-04","2026-05","2026-06","2026-07","2026-08","2026-09","2026-10","2026-11"],"series":[{"name":"Adjusted close","data":[173.32,170.59,161.37,170.65,154.07,145.67,133.81,159.05,154.09,135.45,150.29,145.32,127.55,141.65,144.94,162.13,166.83,174.52,190.98,193.42,185.22,168.8,168.36,187.52,190.07,182.04,178.66,169.5,168.37,190.29,208.47,219.82,226.93,230.89,223.87,235.44,248.43,234.12,240.18,220.6,211.04,199.73,204.03,206.41,231.11,253.5,269.17,277.88,270.92,258.58,263.51,253.15,270.66,311.55,288.89,308.41,316.61,332.77,344.37,356.27,353.66]}]}]}
```

### How each number was computed

| Metric | Value | Method / inputs |
|---|---|---|
| CAGR | **15.47%** | `finance_growth(kind=cagr)`: current 353.66, prior 173.31772, years 4.9583 â $((353.66/173.31772)^{1/4.9583}-1)\times100$ |
| Total return | **+104.05%** | `finance_calc(percentage_change)`: (353.66 â 173.31772) / 173.31772 |
| Max drawdown | **-26.40%** | `calculate_drawdown`: peak 2021-12 (173.32) â trough 2022-12 (127.55), 12 months down, recovered by 2023-06 (190.98) |
| Episodes | 6 drawdowns >0% | largest is the 2022 one; all recovered |

All figures are **computed by Eclipse** from the price series; they are not reported statistics from a provider.

### Data notes and the route that worked

- **First route:** `get_historical_prices` / `market_get_ohlcv` (yfinance) returned valid monthly bars, but the display truncated the middle years on every retry. Per your standing preference for verified data, I didn't compute CAGR off the visible head and tail â I re-fetched the whole series.
- **Failed routes, in order:** `analysis_run` sandbox â `ANALYSIS_NOT_ENABLED` for this session; Stooq CSV via `web_extract` (8s timeout) and via `scraper_run` (confirmed zero rows at that address); Nasdaq API (`dns_failure`); `stockanalysis.com` scrape returned **daily**, not monthly, rows.
- **Working route:** Yahoo's own chart endpoint `query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1mo&range=5y` â 61 monthly observations, `adjclose` field, retrieved in this run. Route health corroborates the diagnosis: `yfinance US equity price_history` is healthy (508/0), while `LIVE_STRUCTURED` is 0 ok / 186 fail.
- **Basis:** monthly bars, **dividend-adjusted close** (Yahoo `adjclose`), USD, NYSE/Nasdaq (NasdaqGS). Last observation is the partial month to 2026-11-16 (356.27 month-close on 2026-11-01; 353.66 last print). Note the **unadjusted** last close is also 353.66 â Yahoo's adjustment factor is ~1.0 here, so 353.66 serves both.
- **Frequency caveat:** a monthly sampling undersamples drawdowns. A daily series over the same window would likely show a deeper trough than -26.40% (intra-month lows in 2022 reached ~124 unadjusted). Treat -26.40% as the *month-end* max drawdown, which is the honest label for monthly data.
- Currency is USD, not your PKR reporting currency; I did not convert, since no FX rate was fetched in this run. Say the word and I'll restate both metrics in PKR.

Data caveat: low: its accounting definition or provenance is unresolved.

One more thing I can do: I can set it up for "Pull AAPL's last 5 years of monthly prices, compute CAGR and max drawdown, and draw a chart. If the first provider fails, try another route before answering." (analysis isn't turned on for this session). Want me to?
