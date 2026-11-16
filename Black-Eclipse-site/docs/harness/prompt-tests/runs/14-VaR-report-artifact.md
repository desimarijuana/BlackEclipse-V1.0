# 14. VaR report artifact

- runId: `run_3830db2d-762e-4b86-832d-ae86995c4896`
- status: **completed**
- steps: 15 / tools: 16 / toolErrors: 1
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T18:51:05.713Z / finishedAt: 2026-11-16T18:55:59.760Z

## Prompt

Build a 60/40 SPY/TLT VaR report with a chart and a downloadable file. If one series is missing, use a labelled proxy and still deliver it.

## Answer

The document validates. One typo to fix ("portrait" â "portfolio") and then I'll deliver it.

Neither series was missing: SPY's first fetch timed out, but the gateway returned it on retry, so **no proxy was used** â this is a genuine 60/40 over 752 bars and 751 daily returns.

```eclipse-response
{"blocks":[
{"type":"markdown","markdown":"**Neither series went missing.** SPY's first route timed out, but the gateway returned it on retry â so this is a real 60/40, **no proxy used**. Over 751 daily returns (2023-11-16 â 2026-11-16), a 1-day 95% VaR is **1.00%** of portfolio value (USD 100,222 per USD 10m). The 99% figure is 1.77%; the average loss *given* you are in that tail is 1.56% at 95% and 2.54% at 99%.\n\nThe honest caveat sits in the measurement itself: excess kurtosis of 11.5 means the normal model is wrong in exactly the place that matters. Parametric 99% VaR (1.587%) falls *below* historical 99% (1.767%) â the model understates the tail it exists to describe."},
{"type":"metric_grid","title":"Headline risk â 60/40 SPY/TLT","asOf":"2026-11-16","source":"Computed by Eclipse from yfinance adjusted closes","columns":3,"metrics":[
{"label":"VaR 95% Â· 1-day","value":1.002,"unit":"%","hint":"Historical, 5th percentile of 751 returns","deltaTone":"flat"},
{"label":"VaR 99% Â· 1-day","value":1.767,"unit":"%","hint":"Historical, 1st percentile","deltaTone":"flat"},
{"label":"ES 95% Â· 1-day","value":1.558,"unit":"%","hint":"Mean loss beyond VaR"},
{"label":"Annualised vol","value":11.09,"unit":"%","hint":"SPY 15.49% Â· TLT 12.53%"},
{"label":"Max drawdown","value":-13.53,"unit":"%","hint":"Trough 2025-04-08"},
{"label":"CAGR","value":9.18,"unit":"%","hint":"3.0-year window, +30.2% cumulative"}]},
{"type":"chart","title":"60/40 SPY/TLT â equity, drawdown and rolling VaR","description":"Month-end observations. Equity indexed to 100 at 2023-11-16. Rolling VaR is a 60-day historical 95% 1-day estimate.","source":"Computed by Eclipse from yfinance adjusted daily closes","asOf":"2026-11-16","legend":true,"panels":[
{"title":"Portfolio equity (indexed, 100 = 2023-11-16)","xLabel":"Month end","yLabel":"Index","marks":[{"type":"line","name":"60/40 equity","x":["2023-11-30","2023-12-29","2024-01-31","2024-02-29","2024-03-28","2024-04-30","2024-05-31","2024-06-28","2024-07-31","2024-08-30","2024-09-30","2024-10-31","2024-11-29","2024-12-31","2025-01-31","2025-02-28","2025-03-31","2025-04-30","2025-05-30","2025-06-30","2025-07-31","2025-08-29","2025-09-30","2025-10-31","2025-11-28","2025-12-31","2026-01-30","2026-02-27","2026-03-31","2026-04-30","2026-05-29","2026-06-30","2026-07-31","2026-08-31","2026-09-30","2026-10-30","2026-11-16"],"y":[101.7,107.5,107.57,109.79,111.95,106.24,110.55,113.34,115.68,118.23,120.33,116.91,121.91,116.46,118.58,120.18,115.28,114.16,116.76,121.23,122.17,123.52,127.55,129.94,130.08,128.15,129.27,130.8,124.38,131.43,135.63,135.04,132.44,134.75,131.16,133.17,130.21]}]},
{"title":"Drawdown from peak (%)","xLabel":"Month end","yLabel":"%","valueFormat":"percent","marks":[{"type":"area","name":"Drawdown","x":["2023-11-30","2023-12-29","2024-01-31","2024-02-29","2024-03-28","2024-04-30","2024-05-31","2024-06-28","2024-07-31","2024-08-30","2024-09-30","2024-10-31","2024-11-29","2024-12-31","2025-01-31","2025-02-28","2025-03-31","2025-04-30","2025-05-30","2025-06-30","2025-07-31","2025-08-29","2025-09-30","2025-10-31","2025-11-28","2025-12-31","2026-01-30","2026-02-27","2026-03-31","2026-04-30","2026-05-29","2026-06-30","2026-07-31","2026-08-31","2026-09-30","2026-10-30","2026-11-16"],"y":[-0.23,-0.8,-0.73,0.0,-0.05,-5.14,-1.3,-1.65,-1.22,-0.61,-0.18,-3.01,0.0,-5.14,-3.41,-2.11,-6.1,-7.01,-4.9,-1.25,-0.48,-0.64,0.0,-1.19,-1.08,-2.55,-1.7,-0.54,-5.42,-0.11,0.0,-0.63,-2.54,-0.86,-3.51,-2.03,-4.21]}]},
{"title":"Rolling 60-day historical VaR (95%, 1-day, % of portfolio)","xLabel":"Month end","yLabel":"%","marks":[{"type":"line","name":"Rolling VaR95","x":["2024-02-29","2024-03-28","2024-04-30","2024-05-31","2024-06-28","2024-07-31","2024-08-30","2024-09-30","2024-10-31","2024-11-29","2024-12-31","2025-01-31","2025-02-28","2025-03-31","2025-04-30","2025-05-30","2025-06-30","2025-07-31","2025-08-29","2025-09-30","2025-10-31","2025-11-28","2025-12-31","2026-01-30","2026-02-27","2026-03-31","2026-04-30","2026-05-29","2026-06-30","2026-07-31","2026-08-31","2026-09-30","2026-10-30","2026-11-16"],"y":[0.807,0.807,1.296,0.995,0.996,0.836,0.874,0.875,0.845,0.845,0.879,0.968,1.132,1.182,2.16,2.16,2.16,0.766,0.648,0.573,0.655,0.764,0.916,0.918,0.7,1.25,1.07,1.245,0.832,1.072,0.88,0.834,0.825,0.895]}]}]},
{"type":"chart","title":"The VaR ladder and the shape of the tail","description":"Left: the same portfolio measured six ways. Right: distribution of all 751 daily portfolio returns â the fat left tail is why parametric 99% undercuts historical 99%.","source":"Computed by Eclipse from yfinance adjusted daily closes","asOf":"2026-11-16","panels":[
{"title":"VaR estimates (% of portfolio)","xLabel":"Estimate","yLabel":"%","valueFormat":"percent","marks":[{"type":"bar","name":"VaR %","x":["1d 95% hist","1d 95% param","1d 99% hist","1d 99% param","10d 95% hist","10d 99% hist"],"y":[1.002,1.111,1.767,1.587,3.169,5.589]}]},
{"title":"Daily portfolio return distribution (751 obs, % buckets)","xLabel":"Daily return bucket (%)","yLabel":"Days","marks":[{"type":"bar","name":"Days","x":[-3.8,-3.4,-3.0,-2.6,-2.2,-1.8,-1.4,-1.0,-0.6,-0.2,0.2,0.6,1.0,1.4,1.8,2.2,2.6,3.0,3.4,3.8],"y":[1,0,1,3,1,6,13,41,88,195,201,128,47,17,8,0,0,0,0,0]}]}]},
{"type":"data_table","title":"VaR and Expected Shortfall matrix","source":"Computed by Eclipse from yfinance adjusted closes","asOf":"2026-11-16","pageSize":12,"columns":[{"key":"method","label":"Method"},{"key":"cl","label":"Confidence","align":"center"},{"key":"h","label":"Horizon","align":"center"},{"key":"pct","label":"VaR % of portfolio","align":"right"},{"key":"usd","label":"VaR on USD 10m","align":"right"}],"rows":[
{"method":"Historical","cl":"95%","h":"1 day","pct":"1.002","usd":"100,222"},
{"method":"Historical","cl":"99%","h":"1 day","pct":"1.767","usd":"176,729"},
{"method":"Parametric normal","cl":"95%","h":"1 day","pct":"1.111","usd":"111,106"},
{"method":"Parametric normal","cl":"99%","h":"1 day","pct":"1.587","usd":"158,696"},
{"method":"Historical","cl":"95%","h":"10 day","pct":"3.169","usd":"316,929"},
{"method":"Historical","cl":"99%","h":"10 day","pct":"5.589","usd":"558,865"},
{"method":"Parametric normal","cl":"95%","h":"10 day","pct":"3.257","usd":"325,654"},
{"method":"Parametric normal","cl":"99%","h":"10 day","pct":"4.761","usd":"476,147"},
{"method":"Historical ES","cl":"95%","h":"1 day","pct":"1.558","usd":"155,810"},
{"method":"Historical ES","cl":"99%","h":"1 day","pct":"2.536","usd":"253,567"},
{"method":"Historical ES","cl":"95%","h":"10 day","pct":"4.927","usd":"492,713"},
{"method":"Historical ES","cl":"99%","h":"10 day","pct":"8.018","usd":"801,848"}]},
{"type":"artifact","title":"Deliverable","artifacts":[{"artifactId":"art_f5823698-6f76-4a29-81a0-0e155345e38f","name":"var-report-spy-tlt-6040.xlsx","description":"8-sheet workbook: Summary, VaR and ES, Component VaR, Yearly Returns, Worst Days, Rolling VaR, Monthly Returns, Method Notes.","category":"report","mimeType":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet","sizeBytes":11214}]}
]}
```

**How the numbers were produced.** Data: yfinance daily adjusted closes for SPY and TLT, retrieved 2026-11-16 via the Eclipse gateway â 752 bars each, 752 common dates, 751 returns. Portfolio return $r_p(t) = 0.60\,r_{SPY}(t) + 0.40\,r_{TLT}(t)$, rebalanced to target daily. Historical VaR is the empirical percentile; parametric VaR is $\mu - z\sigma$ with $z = 1.645$ (95%) and $2.326$ (99%); ES is the mean of returns at or below the VaR percentile; 10-day figures scale by $\sqrt{10}$.

**Three things worth your attention:**

1. **Risk is concentrated in equities beyond what the weights suggest.** SPY is 60% of capital but **74.95%** of parametric 95% VaR (component 1.435% vs TLT's 0.719%). Bond diversification is doing real work â TLT standalone VaR is 1.314%, nearly SPY's, yet contributes a quarter of portfolio VaR because correlation is only 0.122.
2. **The VaR model is slightly under-calibrated.** A rolling 250-day VaR95 backtest over 501 out-of-sample days produced 30 breaches (5.99%) against 5.00% expected. Combined with the 99% inversion, this argues for the ES numbers as the working risk budget, not VaR.
3. **The 60/40 hedge fails when both legs fall.** The worst day (2025-04-10, -3.73%) had SPY -4.38% *and* TLT -2.76%. April 2024, December 2024, March 2025, March 2026 and November 2026 repeat the pattern. A 0.122 correlation is an average, not a guarantee.

**Limits.** The window is 3.0 years and contains the April 2025 selloff, so this is not a calm-period estimate; a longer history would give a higher, more conservative 99% figure. $\sqrt{10}$ scaling ignores volatility clustering and can understate multi-day risk. No transaction costs are deducted. USD notional figures assume exactly USD 10m deployed â scale linearly. Nothing here is a recommendation.

`no doc change â analysis-only run; no repository code, contract or configuration altered.`

Artifacts: art_f5823698-6f76-4a29-81a0-0e155345e38f (Eclipse check).

Data caveat: high: its accounting definition or provenance is unresolved; low: its accounting definition or provenance is unresolved.

Advisory note: the following recommendation(s) are not backed by a portfolio calculation or a consulted source, so they are unverified advice, not verified analysis: hedge SPY TLT to 3.73%.
