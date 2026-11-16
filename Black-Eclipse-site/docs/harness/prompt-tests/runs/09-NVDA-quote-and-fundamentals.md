# 9. NVDA quote and fundamentals

- runId: `run_51519729-6e85-49da-aed6-5cf933096c21`
- status: **completed**
- steps: 21 / tools: 47 / toolErrors: 0
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T21:07:44.734Z / finishedAt: 2026-11-16T21:10:45.089Z

## Prompt

Get NVDA's quote and fundamentals. If JDdS has no fundamentals, use the latest filing and label what is missing.

## Answer

## NVDA â quote and fundamentals (as of 2026-11-16)

**The headline gap first: JDdS has no usable fundamentals for NVDA.** Its stored statements stop at FY2020 (period ended 2020-01-26) â 2,819 days stale. So current fundamentals come from reported results below, labelled by source. The one SEC filing I could read end-to-end is an 8-K from 4 days ago, and it explains today's drop.

### Quote

| | |
|---|---|
| Price | **USD 156.14** (also 155.655 on a second read; 155.39 on a third) |
| Change | **-4.12%** |
| Volume | 309.6 mn |
| Market cap | USD 3.770 trn |
| As-of | 2026-11-16 21:07:53 UTC â Nasdaq, market open, realtime |
| Source | retrieval layer â yfinance (route warnings: LIVE_STRUCTURED and JDDS both recorded as *failing* for current_quote/US, yet returned data) |

The three price reads in this run differ by ~USD 0.7 â intraday ticks at different seconds, not a data conflict.

### Why it's down â primary source

NVIDIA filed an 8-K on **2026-11-12** (accession 0001045810-26-000082) whose Exhibit 99.1 reads: *"Jensen Huang has resigned as President, Chief Executive Officer, and a member of the Board, effective immediately."* Colette Kress (CFO since 2013) is **Interim CEO** while also remaining CFO; Harvey C. Jones became first-ever Board Chair. The release confirms **Q3 FY2027 results will still be reported Tuesday, November 17, 2026** â i.e. tomorrow. `[SEC EDGAR 8-K, filed 2026-11-12]`

Separately, today's wires carry Scott Bessent pressing Nvidia over China chip sales, and commentary framing the leadership vacuum as an opening for AMD â that context is press, not filing.

### Reported fundamentals â TTM through Q2 FY2027 (quarter ended 2026-07-26)

| Metric | Value | Basis |
|---|---|---|
| Revenue | USD 302.97 bn | TTM, 4 quarters |
| Gross profit | USD 226.24 bn | TTM |
| Operating income | USD 197.58 bn | TTM |
| Net income | USD 192.88 bn | TTM |
| Diluted EPS | USD 7.91 | TTM |
| Operating cash flow | USD 134.36 bn | TTM |
| Free cash flow | USD 127.01 bn | TTM (capex -7.35 bn) |
| Cash & investments | USD 62.47 bn | 2026-07-26 |
| Total debt | USD 38.86 bn | 2026-07-26 |
| Net cash | USD 23.61 bn | 2026-07-26 |
| Book equity | USD 228.98 bn | 2026-07-26 |

*Source: stockanalysis.com consensus-standardised quarterly statements â a **WEB aggregator, non-primary**. I could not read these figures out of the filing text itself: SEC's per-concept XBRL endpoints in this environment truncate around FY2022, so the FY2024âFY2027 periods never surfaced. Treat the table as reliable-but-secondary.*

### Valuation and quality â computed by Eclipse from those inputs

| Metric | Result | Formula |
|---|---|---|
| P/E | **19.74x** | 156.14 / 7.91 |
| P/S | **12.44x** | 3.770 trn / 302.97 bn |
| P/B | **16.47x** | 3.770 trn / 228.98 bn |
| EV/EBITDA | **18.62x** | (3.770 trn â 23.61 bn net cash) / 201.27 bn |
| FCF yield | **3.37%** | 127.01 bn / 3.770 trn |
| Gross margin | **74.67%** | 226.24 / 302.97 |
| Net margin | **63.66%** | 192.88 / 302.97 |
| Q2 FY27 revenue growth | **+105.85% YoY** | 96.221 bn vs 46.743 bn |

ROE and ROIC are **not** shown: the calculator refuses both without a named `parent_equity` / `taxRate` input I did not hold from a primary source, and I won't substitute the aggregator's 117.21% ROE / 92.03% ROIC as if computed.

### What's inconsistent, and what's missing

- **JDdS's own P/E of 33.31x is wrong for the current book.** Against TTM EPS of USD 7.91 and a ~USD 156 price, the multiple is ~19.7x. A 33.3x reading implies an EPS near USD 4.70 â an older earnings base. Its forward P/E of 16.67x also sits far from the aggregator's 13.15x. Do not use the JDdS ratio block.
- **Sector/industry from JDdS**: Technology / Semiconductors, US, USD, Nasdaq. Consistent with SEC's SIC 3674 (Semiconductors & Related Devices). `[SEC submissions API]`
- **Filing text gap**: NVDA's latest periodic report (10-Q for Q2 FY2027) exists â SEC's submissions index confirms it â but its XBRL facts are unreachable through this runtime's SEC mirror. Statement-line detail beyond the table above is unavailable until that route is fixed; the FY2022-and-earlier data JDdS holds is 2,819 days stale and must not be used as current.
- **Q2 FY2027 free-cash-flow margin fell to 22.24% from 59.53%** the prior quarter on operating cash flow of USD 24.08 bn vs 50.34 bn â a genuine sequential deterioration in the reported data, and the single number I'd want the 10-Q to explain (working capital? prepayments?) before drawing conclusions.

Tomorrow's Q3 print and the permanent-CEO search are the two things that will reprice this. Want me to pull the FY2027 quarterly series into a chart once the Q3 release lands?

Data caveat: revenue: its accounting definition or provenance is unresolved.
