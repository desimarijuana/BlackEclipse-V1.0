# 25. Ambiguous ABC

- runId: `run_618249af-82b9-4d49-9cb8-2046e362876e`
- status: **completed**
- steps: 16 / tools: 31 / toolErrors: 1
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T18:34:57.387Z / finishedAt: 2026-11-16T18:40:17.164Z

## Prompt

What's ABC trading at? If the ticker is ambiguous, resolve the real intended listing before pricing it; only ask me if identity genuinely cannot be resolved.

## Answer

**ABC = Absolutely Critical Resources Corp. (TSXV: ABC), last traded at C$0.01** â that's roughly **PKR 1.93** at the CAD/PKR mid of 193.091 retrieved today.

The ticker is genuinely shared by several listed companies, but both resolvers in this run agreed on the Canadian listing, so I priced that one rather than asking:

| Field | Value | Basis |
|---|---|---|
| Last price | C$0.0100, 0.00% | Live structured (TradingView via JDdS), retrieved 2026-11-16 18:36 UTC |
| Last recorded print | Nov 12, 2026, 15:50 EST | StockAnalysis delayed quote â no trade since |
| Day volume | 146,000 | Same live quote |
| Market cap | C$488,101 | 48.81M shares Ã C$0.01 (both sources agree) |
| 52-week range | C$0.0050 â C$0.0600 | StockAnalysis |
| Beta (5Y) | -1.11 | StockAnalysis |
| EPS (ttm) | -0.00, net income -C$127,444 | StockAnalysis; JDdS P/E is -1.15 on a near-zero denominator, so not meaningful |

Three things that matter more than the price itself:

1. **The exchange tag is inconsistent.** JDdS/vault says "TSX"; StockAnalysis identifies it as **TSX Venture Exchange**. The company's own description (Mary Ann's Lake, Nova Scotia; Massey property, Timmins) matches the TSXV shell profile, so I'd treat TSXV as the likely correct venue â but confirm against SEDAR+ before acting on it.
2. **C$0.01 is a tick, not a valuation.** On a one-cent stock a single tick is 100% of the price; the bid-ask spread alone makes any entry or exit cost enormous in percentage terms. Average 20-day volume is ~121,000 shares â about C$1,210 of turnover a day.
3. **The balance sheet is negative.** Book value is -C$37,948 against C$62,808 cash and C$122,879 debt, current ratio 0.36, TTM free cash flow -C$427,429, and share count up 32% year over year. This is an exploration-stage issuer funding itself with equity and debt, not an operating business. P/E, P/B and EV/EBITDA are all n/a for that reason.

What I could not verify: no historical OHLCV series was served for this listing (structured routes returned UNAVAILABLE, and the TMX and Yahoo page fetches timed out or returned no symbol), so I have **no independent price series** â only the single quote from two sources and the last-print timestamp. The vault quote also carries a warning that the live route is recorded as failing for Canadian quotes, so even the C$0.01 carries a thin-provider caveat, notwithstanding that the two sources reconcile on market cap.

If you meant a different ABC â e.g. ABC Co. Ltd (Taiwan, 1590), ABC arbitrage (Euronext Paris, ABCA), or a US OTC shell â say which and I'll re-price it.

One more thing I can do: I can set it up for "What's ABC trading at? If the ticker is ambiguous, resolve the real intended listing before pricing it; only ask me if identity genuinely cannot be resolved." (analysis isn't turned on for this session). Want me to?
