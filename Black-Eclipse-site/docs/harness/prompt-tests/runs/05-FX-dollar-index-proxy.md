# 5. FX dollar index proxy

- runId: `run_61279efc-da2f-414b-83cf-070c1a325892`
- status: **completed**
- steps: 16 / tools: 23 / toolErrors: 1
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T19:38:56.749Z / finishedAt: 2026-11-16T19:43:38.131Z

## Prompt

Get EUR/USD, GBP/USD and USD/JPY and compute a dollar index. If one pair fails, use an ETF proxy and label it.

## Answer

## Answer

All three pairs returned live â **no ETF proxy was required for any leg**. Reconstructed on DXY weights renormalised over the three available currencies, the dollar index reads **103.72**, up **+0.23%** on the day.

```eclipse-response
{"blocks":[{"type":"metric_grid","title":"Reconstructed USD index","metrics":[{"label":"Index level (base 100 = 3 Nov 2025)","value":"103.72"},{"label":"Change, 1 day","value":"+0.23","unit":"%","deltaTone":"up"},{"label":"Change, 1 week","value":"+1.14","unit":"%","deltaTone":"up"},{"label":"Since base","value":"+3.72","unit":"%","deltaTone":"up"}]},{"type":"data_table","title":"Legs and contributions","source":"yahoo (FX mids, retrieved 2026-11-16 19:39 UTC)","columns":[{"key":"pair","label":"Pair"},{"key":"spot","label":"Spot","align":"right"},{"key":"d1","label":"1d move","align":"right"},{"key":"w","label":"Weight (renorm.)","align":"right"},{"key":"c","label":"Contribution","align":"right"}],"rows":[{"pair":"EUR/USD","spot":"1.1012","d1":"-0.35%","w":"69.31%","c":"+0.240 pp"},{"pair":"GBP/USD","spot":"1.3193","d1":"-0.29%","w":"14.32%","c":"+0.042 pp"},{"pair":"USD/JPY","spot":"159.37","d1":"+0.32% (JPY)","w":"16.37%","c":"-0.052 pp"}]}]}
```

**Method.** True DXY weights are EUR 0.576, JPY 0.136, GBP 0.119 (plus CAD 0.091, CHF 0.036, SEK 0.042). Renormalised across the three I hold: 69.31% / 16.37% / 14.32%. Level is geometric, oriented so the index *rises* when the dollar strengthens:

$$\text{Level}_t = 100 \times \exp\!\left(\sum_i w_i \ln\frac{S_{i,\text{base}}}{S_{i,t}}\right), \quad S_i = \text{USD per unit of foreign currency}$$

so EUR enters as 1.1012 and JPY as $1/159.37 = 0.006275$. Base 100 = 3 Nov 2025 close (EUR/USD 1.152804, GBP/USD 1.313474, USD/JPY 154.195007).

**Two things I corrected rather than report.**

1. **A sign inversion in my own first pass.** I initially built the basket rising with the *foreign* currencies â an anti-dollar index â which printed â0.23%. UUP at **+0.1017%** on the same day contradicted it; the index is now oriented correctly and gives **+0.23%**. The magnitude was right, the direction was backwards.
2. **A mislabelled window.** My first run used the 9 Nov close as "previous", reporting a one-*week* move (â1.13%) as one day. Recomputed against the 13 Nov close (EUR 1.105021, GBP 1.323136, USD/JPY 159.875).

**ETF proxy â used for validation, not substitution.** Since all three legs worked, UUP (Invesco DB US Dollar Index Bullish Fund, NYSE, **USD 29.53, +0.1017%**, retrieved 19:41 UTC) serves only as an independent sign check. Its smaller move is expected: it holds all six DXY legs, trades at a premium/discount to NAV, and carries the CAD/CHF/SEK exposure I omitted.

**Limits worth pricing in.**

- **The 103.72 level is not comparable to a published DXY quote.** Different base date and a three-currency subset, so the *level* is an index in its own right. Only the *percentages* travel. Direct validation against real DXY failed â `DX-Y.NYB` timed out and `market_get_quote DXY` returned UNAVAILABLE across both structured routes, so I could not anchor the level to the official index.
- **Missing 16.9% of DXY weight** (CAD 9.1%, CHF 3.6%, SEK 4.2%). I tested this: a five-leg build adding CAD (USD/CAD 1.42922, +0.22%) and CHF (USD/CHF 0.83932, +0.40%) â both dollar-positive, and both dollar-*negative* for the index â gave a 1-day move of **+0.235%** versus **+0.230%** for three legs. They largely offset via the renormalisation, so the three-leg version is a sound proxy for the daily move; it will drift more over longer horizons.
- **Quote timestamps read "As of: unknown"** despite a 60-second freshness request. I anchored on the 16 Nov daily close from the OHLCV series, which matches the quoted mids exactly (1.1012 / 1.319279 / 159.371002) â so these are the 16 Nov session closes, not intraday ticks.
- **Provider bar warnings:** eight EUR/USD and seven USD/JPY bars had closes printing outside their stated high/low â a vendor artifact. I used closes only, and the final two bars of each series were clean, so today's figures are unaffected.

The dollar is firm on the day and clearly stronger over the week: EUR and GBP both fell against it, and the JPY's +0.32% gain only partly offsets that at a 16% weight.
