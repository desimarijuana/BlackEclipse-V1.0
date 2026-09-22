# Fundamental Analysis

## Purpose

Analyse a company's financial performance from **verified structured data** and
produce reported figures, clearly-labelled derived figures, period comparisons,
and an honest limitations list. Never fabricate a metric the data does not
contain.

## When to use

- The user asks whether a company is profitable, growing, indebted, or how it is
  valued.
- A comparison of reporting periods is needed.
- A fundamental summary is a deliverable.

## When not to use

- Pure price/technical questions (use market data tools).
- Macro questions (use macro series).
- Qualitative "why did it move" questions (use news/web research).

## Required inputs

| Input | Required | Meaning |
|---|---|---|
| `symbol` | yes | Ticker. |
| `market` | no* | Venue. *Required when the ticker is multi-listed. |
| `periods` | no | Specific reporting periods. |
| `focus` | no | The aspect the user cares about. |

## Required context

The company's canonical instrument identity (market + symbol + currency), and
whether the required data is covered by a source.

## Procedure

1. **Resolve identity first** via `fundamentals_get_company_profile` +
   `market_get_quote`. If the ticker is ambiguous, stop and ask — never pick a
   default venue.
2. **Retrieve statements** via `fundamentals_get_financials`. Note the retrieval
   status; `UNAVAILABLE` is a valid, honest answer, not a prompt to estimate.
3. **Run the data-quality skill** (declared dependency) on the retrieved
   dataset. If it is not `usable`, report the limitation and stop the affected
   analysis rather than computing on bad data.
4. Extract **reported** values: revenue, earnings, margins, cash flow, balance
   sheet items, debt, and any valuation inputs the source actually provides.
   Carry each with its period, unit and currency.
5. Compute **derived** values only from reported inputs (growth rates, margin
   ratios, net-debt/equity). Label each as derived and show the inputs used.
6. Build period `comparisons`. Align periods explicitly; a fiscal-year mismatch
   must be stated, not silently compared.
7. List `limitations`: missing metrics, currency issues, unaligned periods,
   single-period data, unverified sources.
8. Attach `evidence`: source references with retrieval timestamps.

## Tool usage rules

- Only the declared tools; each is read-only.
- Do not use web search to obtain a number that a structured source should
  provide. If the structured source is empty, the metric is **unavailable** —
  not web-guessed.
- Web context may explain a company, never supply a financial figure silently.

## Evidence requirements

- Every reported number carries a source reference.
- Every derived number carries the reported inputs it was computed from.
- Distinguish reported / derived / estimated / assumption / missing /
  conflicting / unverified explicitly.
- Include instrument, identifier, period, retrieval timestamp, publication
  timestamp, currency, units, source and source URL where available.

## Validation rules

- `instrument` has a market and symbol.
- `reported` and `derived` are separate arrays.
- No metric without a period and unit.
- `limitations` is non-empty when any expected metric is missing.

## Output requirements

Return JSON matching `outputSchema`. Never state a metric is "current" unless
the retrieval timestamp and source support it. Never convert currencies for a
historical comparison without documenting the method and its limitation.

## Known limitations

- Depends on the availability and coverage of the structured financial source.
- Derived metrics depend entirely on reported inputs; a missing input makes the
  derived metric unavailable, not zero.

## Failure handling

- Retrieval `AMBIGUOUS` → ask for the venue/share class.
- Retrieval `UNAVAILABLE` → report the metric as unavailable with the source
  status; do not estimate.
- Data-quality `usable: false` → report the blocking issue; do not compute.

## Example

Input: `{ "symbol": "ACME", "market": "PK" }`.
Output: reported revenue FY23/FY24 with currency; derived YoY growth labelled
derived; limitation "FY22 statements unavailable"; evidence with the retrieval
timestamp. No web-sourced figure appears anywhere.
