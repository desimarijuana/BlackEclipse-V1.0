# 31. Investment memo no SEC filing

- runId: `run_87bd9424-914f-4fab-864a-58ee8bdea912`
- status: **completed**
- steps: 24 / tools: 41 / toolErrors: 1
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T22:04:52.965Z / finishedAt: 2026-11-16T22:11:26.959Z

## Prompt

Produce a one-page investment memo on a private company using its official IR page and one independent source; mark each claim's provenance.

## Answer

# Investment Memo â Huawei Investment & Holding Co., Ltd.

**Prepared:** 16 Nov 2026 Â· **Basis:** FY2025 (year ended 31 Dec 2025) Â· **Currency:** CNY millions unless stated Â· **Reporting:** IFRS consolidated [IR]

> **Selection note:** my clarifying question on the target company timed out with no answer. Revolut â the recommended default â returned HTTP 403 on every page, and both search providers plus `news_search` returned no results (degraded routes). I therefore selected **Huawei Investment & Holding**, which satisfied the brief cleanly: a server-rendered official annual-report page plus a fetchable independent trade-press source. If you want a different entity, the memo is rebuildable against the same method.

## Provenance legend

| Tag | Source |
|---|---|
| **[IR]** | Huawei Investment & Holding Co., Ltd., *2025 Annual Report* â official IR page, `huawei.com/en/annual-report/2025`, retrieved 16-Nov-2026; figures from IFRS consolidated statements; USD converted at CNY6.9906/USD (31-Dec-2025 closing rate) |
| **[LR]** | Light Reading (independent), Iain Morris, "Huawei sales growth plummeted in 2025 as it gained 5,000 workers," 1-Apr-2026 |
| **[LR/Omdia]** | Analyst data (Omdia) **quoted inside** [LR] â third-party, not independently retrieved |
| **[CALC]** | Eclipse deterministic calculation from [IR] inputs; formula shown |
| **[WEB]** | Wikipedia infobox, fetched 16-Nov-2026 â used **only** for corporate status |

## 1. What it is

Unlisted, privately held Chinese ICT conglomerate spanning carrier infrastructure, consumer devices, cloud, digital power and intelligent automotive systems [WEB]. It nonetheless publishes audited IFRS consolidated accounts with a five-year comparative series â unusually strong disclosure for a private company â which is what makes a financial memo possible at all [IR].

## 2. Financial summary

| Metric | FY2025 | FY2024 | Change | Source |
|---|---|---|---|---|
| Revenue | 880,941 | 862,072 | **+2.19%** | [IR]; growth [CALC] |
| Operating profit | 96,937 | 79,361 | **+22.15%** | [IR]; growth [CALC] |
| Operating margin | 11.0% | 9.2% | +1.8 pts | [IR] |
| Net profit | 68,036 | 62,574 | **+8.73%** | [IR]; growth [CALC] |
| Net margin | **7.72%** | â | â | [CALC]: 68,036 Ã· 880,941 |
| Cash flow from operations | 127,384 | 88,417 | â | [IR] |
| Cash & short-term investments | 361,426 | 372,232 | â | [IR] |
| Total borrowings | 239,284 | 264,871 | â | [IR] |
| Total equity | 600,120 | 544,619 | â | [IR] |
| Debt / equity | **0.40x** | â | â | [CALC]: 239,284 Ã· 600,120 |
| Liability ratio | 55.0% | 57.8% | â2.8 pts | [IR] |
| R&D spend | 192,300 | â | +7% | [IR] (level, 21.8% of revenue); +7% [LR] |

Five-year revenue CAGR FY2021âFY2025: **8.45%** [CALC: (880,941 Ã· 636,807)^(1/4) â 1], from CNY636,807m to CNY880,941m [IR].

**Segment mix, FY2025 (CNY m, YoY)** [IR]: ICT Infrastructure 375,014 (+2.6%) Â· Consumer 344,473 (+1.6%) Â· Digital Power 77,312 (+12.7%) Â· Intelligent Automotive 45,018 (+72.1% [CALC]) Â· Cloud 32,161 (â3.5%) Â· Other 6,963 (â76.4%).

**Geography, FY2025 (CNY m, YoY)** [IR]: China 616,249 (+0.2%) Â· EMEA 161,356 (+8.8%) Â· Asia-Pacific 50,113 (+15.7%) Â· Americas 37,184 (+2.4%) Â· Other 16,039 (â14.9%).

## 3. What the independent source adds â and where it changes the picture

**The margin story is partly non-operating.** Light Reading attributes the operating-margin expansion (9.2% â 11.0%) *"mainly to a revaluation linked to an asset disposal"* [LR]. Read against [IR], that reframes the headline: operating profit grew 22.15% [CALC] on revenue growth of 2.19% [CALC] â a 10x gap that organic cost leverage cannot plausibly explain. **Treat the FY2025 margin as flattered, and do not capitalise it.**

**Growth has stalled, structurally.** Revenues "inched up just 2.2%" [LR], matching the official +2.19% [CALC]. Operating costs including R&D rose 7.2% to ~CNY334bn [LR] â faster than sales. China is ~70% of revenue [LR] and Chinese-customer sales "did not grow at all" [LR], consistent with the official China line at +0.2% [IR].

**Headcount and R&D are being expanded into a slowdown.** ~213,000 employees in 2025, ~5,000 added during the year (1,000 in R&D), ~18,000 added since 2021 [LR]. This cross-checks against the official disclosure of 114,000 R&D staff at 53.7% of the workforce [IR] â the two are internally consistent.

**Consumer is fragile at the margin.** Huawei reclaimed the top spot in China's smartphone market with 17% of units, but FY shipments rose only 2% to 46.8m while Q4 fell 14% YoY to 11.1m against Apple's +26% to 16.5m [LR/Omdia].

## 4. Assessment

The balance sheet and cash engine are the durable part: operating cash flow of CNY127,384m [IR] against borrowings of CNY239,284m, cash and short-term investments of CNY361,426m [IR], D/E of 0.40x [CALC] and a liability ratio down to 55.0% [IR]. That is a genuinely de-risked capital structure.

The earnings *trajectory* is the weak part. Net profit of CNY68,036m [IR] remains **below** the FY2023 level of CNY86,950m, and operating margin of 11.0% [IR] is well under FY2023's 14.8% [IR] â so three years of revenue growth have not restored peak profitability. Growth is now ~2%, the domestic market is flat, cloud is subscale and shrinking (â3.5% [IR]; "negligible presence" [LR]), and the one fast-growing segment (Intelligent Automotive, +72.1% [CALC]) is still only ~5% of revenue.

**Watch item that would change the view:** evidence of *organic* operating leverage in FY2026 â operating profit growth decelerating toward revenue growth while margins hold â would confirm the business is compounding rather than being propped by one-offs. Conversely, a second consecutive year of margin expansion attributed to disposals or revaluations would argue the FY2025 profit base is not repeatable.

## 5. Conflicts, gaps, and what I could not do

- **FX conflict:** Light Reading states 2025 revenue of "about 881 billion Chinese yuan (US$128 billion)" [LR]; the official report converts the same CNY880,941m to **USD126,018m** at CNY6.9906/USD [IR]. These are not reconcilable at one rate â [LR] appears to use a different (likely average) rate. **I report the official USD figure and do not average the two.**
- **Cloud definitional gap:** [LR] cites cloud at ~CNY35bn; the official segment table shows 32,161 with an all-in cloud figure (including inter-segment) of CNY72,075m [IR]. Different boundaries, not a contradiction â but not comparable either.
- **No valuation is possible.** Huawei is unlisted [WEB] with no traded price, no disclosed share count and no disclosed valuation [IR]. P/E, EV/EBITDA and any fair-value range are therefore **UNAVAILABLE** â I have not estimated them.
- **One independent source only,** as instructed; [LR] is a single trade-press view, and its Omdia smartphone data is second-hand within it [LR/Omdia]. A second independent source (a wire service or the audited PDF itself) would strengthen Â§3 â both were unreachable this run: Revolut and multiple outlets returned HTTP 403/404, and `web_search`, `news_search` and `research_search_news` were all degraded or timed out.
- **No audit opinion reviewed:** I retrieved the annual-report *summary page*, not the full audited PDF. The "audited" characterisation rests on that page's own statement that figures come from IFRS consolidated statements [IR]; I did not read the auditor's report.

## Sources retrieved this run

- Huawei Investment & Holding Co., Ltd., 2025 Annual Report (official IR): https://www.huawei.com/en/annual-report/2025
- Huawei, 2024 Annual Report (prior-year comparatives): https://www.huawei.com/en/annual-report/2024
- Light Reading, 1-Apr-2026: https://www.lightreading.com/5g/huawei-sales-growth-plummeted-in-2025-as-it-gained-5-000-workers
- Wikipedia, *Huawei* (corporate status only): https://en.wikipedia.org/wiki/Huawei

Advisory note: the following recommendation(s) are not backed by a portfolio calculation or a consulted source, so they are unverified advice, not verified analysis: short IR CALC to 55.0%.
