# 12. Conflicting revenue sources

- runId: `run_41c859fa-3924-4723-9f22-35fb10636117`
- status: **completed**
- steps: 2 / tools: 2 / toolErrors: 0
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T21:27:36.551Z / finishedAt: 2026-11-16T21:28:12.102Z

## Prompt

A source says revenue is $100B and another says $90B. Which is right? Show the conflict, do not average incompatible figures.

## Answer

**Neither â yet.** On the evidence given, the two numbers aren't comparable, so there is no "right" one to pick and the midpoint is definitely wrong. Averaging two revenue figures computed on different bases produces a number that matches *neither* basis, and the error is systematic, not random â it just hides the discrepancy behind a plausible-looking third value.

The gap is 11.11% of the lower figure (and -10.0% of the higher) â large enough to be a basis difference, small enough to be invisible to a careless reader.

## The conflict, as stated

| | Source A | Source B | Gap |
|---|---|---|---|
| Reported revenue | 90 (USD bn) | 100 (USD bn) | 10 (USD bn) |
| Relative to the other | â | +11.11% vs A | -10.0% vs B |
| Basis stated | *none* | *none* | undetermined |

Both rows fail the first test of comparability: no as-of period, no fiscal-vs-calendar label, no currency/unit convention, no gross-vs-net definition, no consolidated-vs-segment scope, no "as originally reported vs restated" marker. Without those, "which is right" isn't a fact question â it's an incomplete-inputs question.

## The basis checks, in the order that actually explains an ~11% gap

| # | Suspect | Typical size of effect | How to test |
|---|---|---|---|
| 1 | Period mismatch â FY vs TTM vs calendar year, or different fiscal year-ends | 5â20% for a company growing ~10â20%/yr | Tie each figure to its exact period-end date; a TTM vs FY-close gap of ~6 months on a fast grower lands right at 11% |
| 2 | Revenue definition â gross vs net (principal vs agent, ASC 606 / IFRS 15), excise duties and sales taxes in or out | Can be an order of magnitude; 11% is common for mixed arrangements | Check the accounting policy note on principal-vs-agent and on excise/turnover taxes |
| 3 | Scope â consolidated group vs standalone parent vs one segment | 5â30%+ | Confirm "consolidated" and whether discontinued operations are in or out |
| 4 | Currency and scaling â USD vs local currency (you report in PKR), bn vs mn, truncated vs rounded | FX alone can be 10%+ year-on-year | Convert both to one currency at one dated rate; state the rate |
| 5 | As-originally-reported vs restated/reclassified | 2â15% | Check for a restatement or a segment recast in the later filing |
| 6 | Aggregator error â a vendor transcribing a half-year as a full year, or annualising one quarter | unbounded | Trace each to the filed line item |

A company on a non-December fiscal year, growing mid-teens, is the single most common way to manufacture exactly this gap: one source quotes FY, the other quotes TTM, and both are "correct" about different twelve-month windows.

## The decisive test

Do not rank the sources by reputation. Rank them by **traceability to a filed line item**:

1. Take each figure to its primary document â the income statement's revenue line for a named period in the annual report or 10-K/20-F, not a summary page.
2. If both trace to filed statements, the difference is a real basis difference: normalise both to one basis (same period-end, same currency and rate, consolidated, gross, as reported) and then compare. One of them will move; if neither moves, you have found a genuine restatement and the later filing governs.
3. If only one traces, the other isn't a competing figure â it's a lower-quality estimate and should be labelled as such, not reconciled against.

Only after that normalisation is any arithmetic between them legitimate. The 11.11% / -10.0% above is the size of the *unresolved* discrepancy; it is not a growth rate, a revision, or a restatement.

## What I need to resolve it

Name the company and the period (or paste the two source URLs) and I'll fetch each source, record its stated basis and as-of date, trace both to the filed revenue line, and report either the reconciled figure with its basis or a labelled unresolved conflict â without collapsing the two into one number. If it's a PSX name, note the standing limitation in this workspace: primary statements are often scanned image-only PDFs with no extractable text, so I'd have to label any figure from a secondary aggregator as non-primary rather than presenting it as filed.
