# 17. Bloomberg terminal capability

- runId: `run_120294c0-5433-4c0e-a458-d8fe68f2533e`
- status: **completed**
- steps: 22 / tools: 43 / toolErrors: 1
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T21:32:53.128Z / finishedAt: 2026-11-16T21:36:52.263Z

## Prompt

Use my Bloomberg terminal to pull XYZ.

## Answer

**I can't reach a Bloomberg terminal â there isn't one on this desktop.** I checked: the desktop-control session is live (`csess_3569f9cfb0f54474`) but sees only a Brave browser and its windows; no Bloomberg application or Terminal window exists, and there is no Bloomberg preset in the MCP catalog (the 12 presets are Google Sheets, Excel, filesystem, SEC EDGAR, Twelve Data, Tavily, Jira/Confluence, Notion Ã2, Canva, Figma, Office). So nothing was pulled from Bloomberg, and I won't present anything as if it were a BLPAPI field.

What I did instead: resolved the ticker and pulled it through the data routes I do have. **XYZ = Block, Inc. (Class A), NYSE, USD** â Jack Dorsey's Square/Cash App fintech, not a placeholder ticker.

## Block, Inc. (XYZ) â as of close 2026-11-16

| Item | Value | Basis |
|---|---|---|
| Last price | **USD 82.96** | NYSE close 16:00 ET, 2026-11-16 (â1.62, â1.92%); after-hours 82.10 at 16:15 ET |
| Session | Closed | after-hours print shown separately |
| Market cap | **USD 50.15 bn** â PKR 13,887 bn | 82.96 Ã 604.52 mn shares; PKR at 276.91 |
| 52-week range | 48.21 â 89.40 | â |
| Beta | 2.56 | 5-yr â high sensitivity |
| P/E (TTM GAAP) | 108.8Ã (site) / 109.2Ã (my calc) | 82.96 Ã· TTM EPS 0.76 |
| Forward P/E | **16.37Ã** | consensus forward EPS |
| P/S (TTM) | 1.96Ã | see below |
| Consensus | Buy (48 analysts), target 101.36 (+22.8%) | â |

**TTM fundamentals â Q4 FY2025 + Q1âQ3 FY2026 (fiscal = calendar year), USD mn**

| Metric | TTM | Margin |
|---|---|---|
| Revenue | 25,646 (25.65 bn) | â |
| Gross profit | 12,234 | **47.70%** |
| Operating income | 1,248.9 | 4.87% |
| Net income | 461.15 | 1.80% |
| EPS | 0.76 | â |
| Cash & investments / total debt / net cash (30 Sep 26) | 8,245 / 7,535 / **+709** | â |
| Q3 FY26 FCF | 971 | FCF margin 14.46% |

These are my sums of the four reported quarters (margins via the deterministic margin tool: gross 12234/25646 = 47.7033%, operating 1248.94/25646 = 4.8699%, net 461.15/25646 = 1.7981%; P/S via price Ã· sales-per-share = 82.96/42.4223 = 1.9556Ã), sourced from stockanalysis.com's quarterly table, not from a filing.

**Why the P/E looks absurd and the forward P/E doesn't:** GAAP trailing earnings are depressed by stock-based comp and one-offs â Q1 FY2026 was a â308.7 mn loss, and the â85.3% YoY net-income decline is against Q4 FY2024's 1,946 mn quarter (a tax-valuation-allowance release). Strip that out and the operating picture is materially better: Q3 FY2026 gross profit +22% YoY, adjusted operating income +92%, and management guided FY2026 up with a preliminary FY2027 target of â¥15% gross-profit growth at a ~32% adjusted operating margin.

**Recent catalysts (last ~2 weeks):** Q3 beat on 3 Nov, stock +16% to ~88; a wave of target raises (Bernstein 110, Wells Fargo 110, TD Cowen 109, Freedom 115, RBC 103, Cantor 102, Barclays/Argus 105, Truist 95, Scotiabank 89); Square made merchant Bitcoin payments free; a **second round of 2026 layoffs** (Cash App roles, after >4,000 cuts in February); and a **preliminary DOJ settlement**. Segment mix in Q3: Commerce Enablement 3,476 mn, Financial solutions 1,440 mn, Bitcoin ecosystem 1,804 mn (down from 2,462 mn in Q4 FY2024 â bitcoin revenue is shrinking).

## What's weak in this evidence â read before acting on it
- **No Bloomberg fields at all**: no BDP/BEST consensus detail, no BLPAPI estimates, no ownership, no intraday. Everything above is a public aggregator or my arithmetic on it.
- **The OHLCV provider is broken**: every date range I asked for (MayâNov, AugâNov, SepâNov) returned the *same* cached series ending 12 June 2026. I therefore have **no trustworthy multi-month price path** and did not chart one â that's why there's a table and not a curve.
- **The SEC/JDDS fundamentals route is stale**: `fundamentals_get_financials` returned **FY2018 and FY2019** only (revenue 3.30 bn / 4.71 bn, flagged "2,877 days old"). Historically right, useless now. I did not use those figures.
- **Ratio bases disagree**: the vault snapshot said P/E 141.07 at 82.48; the aggregator says 108.78 at 82.52; my price/EPS gives 109.16. Different EPS bases and timestamps â I'm quoting the aggregator's P/E with the basis stated rather than blending them.
- **USD/PKR** came from exchangerate-api (276.9118, fixing 2026-11-16 00:02 UTC), not the State Bank of Pakistan. PKR figures are indicative.

## To actually get Bloomberg data
Two viable routes, both needing you to act:

1. **Terminal on this machine** â if Bloomberg Terminal is installed and logged in on the desktop I can drive it read-only via Computer Use (type `XYZ US Equity DES`, `<GO>`, capture the screen). Right now it isn't installed/logged in. If it's on a different host, that host needs to be the one I'm controlling.
2. **BLPAPI service** â a local MCP/plugin wrapper around `blpapi` (needs a running Terminal or B-PIPE entitlement plus `BLOOMBERG_*` credential names). I called `capability_external` for this and it needs you to name the endpoint/command and credential names before anything is proposed; nothing was installed or enabled.

Tell me which route you want â or if "XYZ" was meant as a different security (there are non-US listings and a defunct ETF using that string), say which market and I'll re-resolve rather than assume the NYSE Block line.
