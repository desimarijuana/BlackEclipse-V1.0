# 3. Private company revenue

- runId: `run_ebee0240-5212-42d5-a902-a94ab29861e1`
- status: **completed**
- steps: 17 / tools: 31 / toolErrors: 0
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T19:14:03.714Z / finishedAt: 2026-11-16T19:17:00.752Z

## Prompt

Find the latest quarterly revenue for a private company like SpaceX. There is no public filing - get as far as you can and tell me exactly what is missing.

## Answer

## The premise needs correcting: SpaceX is not private anymore

SpaceX â Space Exploration Technologies Corp. â completed its IPO on **12 June 2026** and trades on Nasdaq as **SPCX** (CIK 0001181412). It files with the SEC as a domestic issuer. So there *is* a public filing, and the quarterly revenue is available from primary source.

**Q3 2026 revenue: USD 14,575 mn**, for the quarter ended 30 September 2026, per the Form 10-Q filed 22 October 2026.

Source: SEC EDGAR, 10-Q accession 0001628280-26-066880, XBRL concept `RevenueFromContractWithCustomerExcludingAssessedTax` ([data.sec.gov](https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json)); cross-checked against Note 3 â Revenue in the same filing ([R12.htm](https://www.sec.gov/Archives/edgar/data/1181412/000162828026066880/R12.htm)).

### Reported results (USD mn, US GAAP)

| Metric | Q3 2026 | Q3 2025 | Q2 2026 | Q3 YoY |
|---|---:|---:|---:|---:|
| Revenue | 14,575 | 5,576 | 7,814 | +161.4% |
| Operating income (loss) | 2,791 | (273) | (143) | n/m |
| Net income (loss) | 4,404 | (1,054) | (541) | n/m |
| Operating margin | 19.1% | (4.9%) | (1.8%) | â |
| Net margin | 30.2% | (18.9%) | (6.9%) | â |
| 9M revenue | 27,083 | 13,714 | â | +97.5* |

*Computed from the XBRL 9-month values. YoY growth, margins computed by Eclipse from the reported inputs above.

### Segment revenue (Note 3, USD mn)

| Segment | Q3 2026 | Q3 2025 | YoY | % of Q3 revenue |
|---|---:|---:|---:|---:|
| Space | 1,767 | 1,666 | +6.1% | 12.1% |
| Connectivity (Starlink) | 5,248 | 3,097 | +69.5% | 36.0% |
| SI â Super Intelligence (xAI/X, incl. advertising) | 7,560 | 813 | +829.9% | 51.9% |
| **Total** | **14,575** | **5,576** | **+161.4%** | **100%** |

The SI segment is large because SpaceX acquired xAI in 2026 and folded it in as SpaceX Super Intelligence; the +830% is acquisition-driven, not organic. Also disclosed: backlog USD 62,959 mn at 30 Sep 2026 (67% due within a year), deferred revenue USD 17,520 mn, and customer concentration â Customer B at 34.5% of Q3 revenue, entirely in the SI segment.

### What is genuinely missing

Very little, but precisely this:

1. **Q4 and full-year 2026 are not yet filed.** The 10-Q covers only through 30 September 2026. The FY2026 10-K (with Q4) is due roughly FebruaryâMarch 2027. There is no later quarterly figure in existence yet.
2. **No earnings call transcript or guidance in this route.** SPCX's 10-Q carries no forward guidance; management commentary would need an IR webcast or transcript, which I did not retrieve.
3. **Segment *profit* by segment** â I have the Connectivity operating income (USD 2,370 mn per the segment note in [Starlink's Wikipedia entry](https://en.wikipedia.org/wiki/Starlink), a secondary source I am flagging as non-primary) but did not extract the full segment profitability table from the filing. Revenue disaggregation is primary and complete above.

### Route notes (why this took several steps)

- `company_search` for "SpaceX" returned no canonical entity â it is not in the stored universe as a private name.
- Web/news search was **broken this run**: DuckDuckGo returned HTTP 202 (blocked), Mojeek HTTP 403, and the Bing HTML route returned completely off-query results (Stack Overflow, Instagram pages). Snippets were discarded as noise.
- The JDdS/yfinance statement route returned **only annual FY2023âFY2024** and is stale by ~2 years â useless for a "latest quarter." Do not use it for SPCX.
- EDGAR's legacy `browse-edgar` CGI **timed out twice** (8s limit). EDGAR full-text search (`efts.sec.gov`) worked and located the filing; `data.sec.gov` XBRL worked cleanly.

If you actually want a **still-private** analogue â a company with no 10-Q at all â the picture is different: no primary filing exists, and the only figures are leaked or investor-reported numbers in press coverage, which this run's degraded search index could not even surface. Tell me which private name you have in mind and I will work that ladder separately.

Data caveat: revenue: its accounting definition or provenance is unresolved.
