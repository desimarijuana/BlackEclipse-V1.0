---
title: Data Sources & Licensing
status: Current
last-verified: 2026-11-17
---

# Data Sources & Licensing

> Generated from `src/lib/setup/source-catalog.ts`. Do not edit by hand; run
> `npm run docs:data-sources`. This is an informational snapshot, not legal
> advice. Verify each provider's current terms before a paid launch.

## What the three tiers mean

- **Included** — ships with Eclipse, no account, redistributable with the stated condition.
- **Connect your own** — the user supplies their own key/account; the provider's terms apply to them.
- **Advanced / community** — personal-use sources. Off by default; never part of a commercial default.

## Included — open data, no account

| Source | Commercial | What it powers | Default | Terms |
|---|---|---|---|---|
| SEC EDGAR | You can use this in a commercial product. | Company research, Filings, Fundamentals | On | [terms](https://www.sec.gov/os/webmaster-faq) |
| FRED public series | You can use this in a commercial product if you display the attribution. | US macro, Rates & inflation | On | [terms](https://fred.stlouisfed.org/legal/) |
| BEA | You can use this in a commercial product. | GDP, National accounts | On | [terms](https://www.bea.gov/help/faq/) |
| BLS | You can use this in a commercial product. | Employment, CPI | On | [terms](https://www.bls.gov/developers/) |
| World Bank | You can use this in a commercial product if you display the attribution. | Global macro, Development indicators | On | [terms](https://datacatalog.worldbank.org/public-licenses) |
| Eurostat / ECB | You can use this in a commercial product if you display the attribution. | EU macro, Reference FX rates | On | [terms](https://ec.europa.eu/eurostat/about-us/policies/copyright) |
| GDELT | You can use this in a commercial product if you display the attribution. | Geopolitical events, Investor Eye | On | [terms](https://www.gdeltproject.org/about.html) |
| USGS | You can use this in a commercial product. | Seismic events, Investor Eye | On | [terms](https://www.usgs.gov/information-policies) |
| NASA FIRMS | Check the provider's current terms before using it commercially. | Fire detections, Investor Eye | On | [terms](https://firms.modaps.eosdis.nasa.gov/) |
| Official news feeds | Check the provider's current terms before using it commercially. | Headlines, Regulatory news | On | [terms](https://www.sec.gov/news/pressreleases.rss) |

## Connect your own — your key/account

| Source | Commercial | What it powers | Default | Terms |
|---|---|---|---|---|
| Polygon.io | You can use this in a commercial product. | Live prices, Charts, Screener | Off | [terms](https://polygon.io/legal/terms) |
| Twelve Data | You can use this in a commercial product. | Live prices, Charts | Off | [terms](https://twelvedata.com/terms) |
| Finnhub | You can use this in a commercial product. | News, Earnings, Quotes | Off | [terms](https://finnhub.io/terms-of-service) |
| Alpha Vantage | You can use this in a commercial product. | Live prices, FX, Technicals | Off | [terms](https://www.alphavantage.co/terms_of_service/) |
| Marketstack | You can use this in a commercial product. | Live prices, History | Off | [terms](https://marketstack.com/terms) |
| Financial Modeling Prep | You can use this in a commercial product. | Fundamentals, Ratios, Estimates | Off | [terms](https://site.financialmodelingprep.com/terms-of-service) |
| CoinMarketCap | Check the provider's current terms before using it commercially. | Crypto prices, Rankings | Off | [terms](https://coinmarketcap.com/api/terms/) |
| CoinGecko (paid) | You can use this in a commercial product if you display the attribution. | Crypto prices, Market data | Off | [terms](https://www.coingecko.com/en/api_terms) |
| Trading Economics | You can use this in a commercial product. | Global macro, Economic calendar | Off | [terms](https://tradingeconomics.com/api/terms-and-conditions.aspx) |
| Tavily | You can use this in a commercial product. | Research search | Off | [terms](https://tavily.com/terms) |
| Brave Search | You can use this in a commercial product. | Research search | Off | [terms](https://brave.com/search/api/) |
| Exa | You can use this in a commercial product. | Research search | Off | [terms](https://exa.ai/terms) |
| Serper | You can use this in a commercial product. | Research search | Off | [terms](https://serper.dev/terms) |

## Advanced / community — personal use only, off by default

| Source | Commercial | What it powers | Default | Terms |
|---|---|---|---|---|
| TradingView scanner | Personal use only. Do NOT use this if you are a company charging for this product. | Live prices, Screener | Off | [terms](https://www.tradingview.com/policies) |
| Yahoo Finance (yfinance) | Personal use only. Do NOT use this if you are a company charging for this product. | Live prices, History | Off | [terms](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html) |
| HTTP scraper | Check the provider's current terms before using it commercially. | Live prices | Off | — |
| Browser scraper | Check the provider's current terms before using it commercially. | Live prices | Off | — |
| Scrapling | Check the provider's current terms before using it commercially. | Live prices | Off | — |
| Binance public ticker | Personal use only. Do NOT use this if you are a company charging for this product. | Crypto prices | Off | [terms](https://www.binance.com/en/terms) |
| Kraken public API | Check the provider's current terms before using it commercially. | Crypto prices | Off | [terms](https://www.kraken.com/legal) |
| CoinGecko Demo / keyless | Personal use only. Do NOT use this if you are a company charging for this product. | Crypto prices | Off | [terms](https://www.coingecko.com/en/api_terms) |
| DuckDuckGo HTML search | Personal use only. Do NOT use this if you are a company charging for this product. | Research search | Off | [terms](https://duckduckgo.com/terms) |

## Attribution

The app displays provider attribution on the screens that use the data. Keep it visible:

- FRED — “Courtesy of FRED, Federal Reserve Bank of St. Louis”
- World Bank — CC BY 4.0
- Eurostat / ECB
- GDELT — The GDELT Project
- NASA FIRMS
- CoinGecko — “Data provided by CoinGecko” (paid plan)

## Changing a source

Add or edit it in `src/lib/setup/source-catalog.ts`, then run
`npm run docs:data-sources`. Enforcement lives in
`src/lib/data-source-preferences.ts`; a new toggle is not real until its
fetch path consults it.
