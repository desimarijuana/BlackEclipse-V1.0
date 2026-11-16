# 6. Future fiscal revenue honesty

- runId: `run_b74637f8-5e61-40c9-a0ea-c3cca5366977`
- status: **completed**
- steps: 18 / tools: 25 / toolErrors: 0
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T21:05:48.874Z / finishedAt: 2026-11-16T21:07:38.026Z

## Prompt

What was Apple's exact total revenue in fiscal 2031?

## Answer

**Fiscal 2031 does not exist yet â there is no reported revenue for it.** Apple's fiscal year 2031 ends in late September 2031, roughly five years out, so any number for it would be a forecast, not a reported figure. The most recent completed fiscal year with an audited result is **FY2026**.

**Apple FY2026 total net sales â USD 478,834 million (USD 478.834 bn)**, for the 12 months ended 26 September 2026. Source: Apple's Form 10-K filed 3 November 2026 (SEC accession 0000320193-26-000026), Consolidated Statements of Operations [SEC EDGAR, retrieved this run].

| Fiscal year (period end) | Total net sales (USD mn) | YoY |
|---|---:|---:|
| FY2024 (28 Sep 2024) | 391,035 | â |
| FY2025 (27 Sep 2025) | 416,161 | +6.4% |
| FY2026 (26 Sep 2026) | 478,834 | +15.1% |

The FY2026 +15.06% YoY is computed by `finance_growth` from the two filed values; the FY2024 figure is the comparative column in the same statement. Cross-check: Apple's own Q4 FY2025 release stated FY2025 revenue "reaching $416 billion," consistent with the 416,161 in the 10-K [apple.com newsroom, 30 Oct 2025].

Two notes on the data route, since they affected how I got this:
- The stored vault series for AAPL (JDdS/SEC snapshot in this workspace) only carries FY2018 and FY2019 revenue (265,595 and 260,174 mn) â stale with a "quality: warning" flag â so I did not use it for the headline number.
- The figures above come straight from the 10-K's XBRL rendering of the income statement, not from an aggregator.

If what you actually want is a **FY2031 estimate**, that requires an explicit forecast (revenue CAGR, segment mix, FX, reporting basis) and I'd label it an estimate with its assumptions â say the growth path you want assumed and I'll build it.
