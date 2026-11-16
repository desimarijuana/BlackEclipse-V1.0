# 1. PSX thin history

- runId: `run_ce3f5024-0f99-45e8-8d51-8a2eefbbc189`
- status: **completed**
- steps: 24 / tools: 34 / toolErrors: 0
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T18:05:47.869Z / finishedAt: 2026-11-16T18:08:58.002Z

## Prompt

Get me the daily price history for a thinly traded PSX stock that is not in JDdS. If the vault misses it, use the exchange/IR page or a scraper, label it PARTIAL, and show the as-of date.

## Answer

## Answer: the vault misses BUXL â daily history is PARTIAL, and here is exactly how far it goes

**Vault status (confirmed miss):** `data_inventory` for BUXL returned *"No store holds BUXL 1d."* JDdS has no daily series for this name.

**What I could deliver:** a real daily OHLCV series from the market-data gateway, but it **stops at 2026-09-11** â a ~9-week hole before today. The exchange page supplies only the live session. So the series is **PARTIAL**, labelled as such below.

**Instrument:** Buxly Paints Limited, BUXL, PSX, Chemical sector. Currency **PKR**. Market cap PKR 461,217.6 thousand (~PKR 461.2 mn), 1,440,000 shares, free float 40% â genuinely thin.

### Latest session â exchange primary source

| Field | Value | Basis |
|---|---|---|
| Last / close | **PKR 320.29** | As of Mon, **Nov 16, 2026 3:42 PM PKT** â PSX closing session |
| Change | **â10.12 (â3.06%)** | vs prior close |
| Open / High / Low | 330.00 / 335.95 / 315.00 | same session |
| Volume | 18,937 shares | same session |
| LDCP (Nov 13 close) | 330.41 | prior session, PSX field |
| Circuit breaker | 297.37 â 363.45 | â |
| 52-week range | 137.00 â 1,196.86 | split-adjusted per PSX |

Source: PSX Data Portal company page, "Market data powered by capitalstake.com. Provided by PSX" â fetched this run, as-of Nov 16, 2026. Cross-checked against Sarmaaya (FactSet-sourced): 320.29, â10.12 (â3.06%), volume 18,937, day range 315.0â335.95 â **agrees on every field**.

### Daily closes â gateway series (PARTIAL, truncated 2026-09-11)

| Date | Close (PKR) | Volume |
|---|---:|---:|
| 2026-08-03 | 187.95 | 4,858 |
| 2026-08-06 | 208.65 | 62,064 |
| 2026-08-10 | 252.47 | 27,545 |
| 2026-08-13 | 336.04 | 117,382 |
| 2026-08-14 | 336.04 | 0 |
| 2026-08-19 | 447.26 | 21,165 |
| 2026-08-21 | 541.19 | 26,415 |
| 2026-08-24 | 595.31 | 6,712 |
| 2026-08-27 | 696.30 | 379,473 |
| 2026-08-31 | 842.52 | 54,279 |
| 2026-09-02 | 1,019.45 | 77,998 |
| 2026-09-03 | 917.51 | 76,721 |
| 2026-09-04 | 989.14 | 157,342 |
| 2026-09-07 | 1,088.05 | 33,684 |
| **2026-09-08** | **1,144.84** | 133,625 |
| 2026-09-09 | 1,030.36 | 67,684 |
| 2026-09-10 | 927.32 | 7,095 |
| **2026-09-11** | **834.59** | 6,158 |

Earlier, for the thin-trading baseline (shows why intraday gaps are normal): 2025-12-09 close 148.07 on **4 shares**; 2025-12-10 close 148.07 on **28 shares**; 2025-12-23 close 154.36 on 6,127.

**Every row above** also carries open/high/low in the raw record, but the gateway **withheld open, high and low from a clean answer** as "accounting definition unresolved / ambiguous" â so I am only asserting close and volume.

### Why I believe the series, and why it is still PARTIAL

One validation matters: PSX states BUXL's 52-week high as **1,196.86**. The gateway's 2026-09-08 intraday high is **1,196.85998â¦** â an exact match. That means the two sources sit on the **same split-adjusted basis**, so the series is not a mismatched-adjustment artifact despite the violent level change (834.59 â 320.29 across the gap).

But it is PARTIAL for three concrete reasons:

1. **The gap is real and named:** no daily bar exists in any route I completed for **2026-09-14 â 2026-11-13** (~43 sessions). The only bridge is PSX's LDCP of 330.41 for Nov 13.
2. **The gateway flagged itself:** *"route LIVE_STRUCTURED is recorded as failing for historical_prices (PK)."* The capability matrix similarly records PK history as TradingView-scan, **observed: failing**, and flags it a secondary route, not the primary venue route.
3. **One defective row:** 2026-08-20 repeats 2026-08-18's OHLC and volume (406.60 / 16,591) exactly â a duplicate, not a genuine session. Zero-volume days (08-14, 08-26) are no-trade days, not stale prices.

### Sources actually tried for the missing window

| Route | Result |
|---|---|
| JDdS vault | **No store holds BUXL 1d** |
| Provider chain (Yahoo, Stooq, Polygon) | no history / DNS fail / **needs POLYGON_API_KEY** |
| PSX `timeseries/eod`, `/int` endpoints | **HTTP 404** |
| PSX historical-data form | form loads, **returns no rows in HTML**; scripted query blocked pending approval |
| ksestocks.com | **DNS failure** |
| Web search | provider returned unrelated spam |
| PSX company page + Sarmaaya | **succeeded** â last session only |
| Analysis sandbox | **not enabled this session** |

Nothing here is fabricated: the gap is a gap. **To close it**, the one permitted next route is a browser-script approval on `dps.psx.com.pk/historical` (symbol BUXL, month/year, POST) â that is the only surface holding the SepâNov daily rows, and its query needs script execution the run refused without approval.

One thing worth flagging on the substance: PSX carries **"Unusual Movement in the Price of the Shares"** announcements dated **Jul 13, Sep 4 and Oct 16, 2026** â the Oct 16 notice falls inside the missing window, exactly where the price fell from 834.59 to ~330. Any analysis of this name needs those sessions before the move is trusted.

One more thing I can do: I can set it up for "Get me the daily price history for a thinly traded PSX stock that is not in JDdS. If the vault misses it, use the exchange/IR page or a scraper, label it PARTIAL, and show the as-of date." (analysis isn't turned on for this session). Want me to?
