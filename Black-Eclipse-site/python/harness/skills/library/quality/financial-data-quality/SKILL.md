# Financial Data Quality

## Purpose

Review retrieved financial data **before** it is analysed, so a downstream
calculation is not built on the wrong instrument, period, currency or unit. This
skill is the gate between retrieval and analysis.

## When to use

- After any financial data retrieval and before using it in analysis.
- When a retrieval result is `PARTIAL`, `degraded`, `incomplete` or carries
  warnings.
- When combining multiple sources or periods.

## When not to use

- Pure web research with no numeric payload.
- A qualitative news summary.

## Required inputs

| Input | Required | Meaning |
|---|---|---|
| `dataset` | yes | The retrieval result to review. |
| `expectedInstrument` | no | What the analysis expects the data to be about. |
| `expectedPeriod` | no | The period the analysis expects. |

## Required context

The retrieval result's `identity`, `dataType`, `freshness`, `quality`,
`warnings`, `provenanceVerified`, `degraded`/`degradation`, `incomplete`,
`conflicts`, and any per-object `unit`/`currency`/`period`/`dataTimestamp`.

## Procedure

1. **Instrument identity.** Confirm `market` + `symbol` are present and (when
   supplied) match `expectedInstrument`. A bare ticker with no venue is
   ambiguous — flag it, do not assume a default market.
2. **Reporting period.** Confirm each value carries a period. Flag values whose
   period differs from `expectedPeriod`.
3. **Units.** Confirm each metric's unit (`%`, shares, a currency amount). A
   bare number without a unit is a quality issue.
4. **Currency.** Confirm the currency is explicit. Flag a mix of currencies in
   one comparison; never apply a guessed FX rate.
5. **Missing values.** List absent expected metrics. Absence is a gap, not zero.
6. **Duplicates.** Detect repeated rows/observations (e.g. the same date twice).
7. **Freshness.** Compare the retrieval/data timestamps to the requirement.
   Mark stale data explicitly.
8. **Source reliability.** Use `get_source_health`; if no health is recorded,
   say so rather than assuming reliability.
9. **Historical vs current.** Keep an as-of value distinct from a current one.
   Do not call a value "current" unless timestamp and source support it.
10. **Reported vs derived.** Mark each value as reported (from a source) or
    derived (calculated here). Never present a derived figure as reported.

## Tool usage rules

- `get_source_health` and `get_coverage` are read-only context tools. Use them
  to state reliability/coverage honestly when it is `no_data`.

## Evidence requirements

- Every quality verdict cites the payload field it is based on.
- Do not invent a missing unit, currency, or period.

## Validation rules

- `usable` is true only when identity, period, unit and currency are all
  present and no blocking conflict exists.
- `missingValues` lists only genuinely absent expected metrics.
- A `CONFLICTING`/`degraded` dataset is either not usable or explicitly
  qualified in `limitations`.

## Output requirements

Return JSON matching `outputSchema`, with `reportedVsDerived` distinguishing the
two and `limitations` stating what could not be checked.

## Known limitations

- The skill cannot repair bad data; it can only flag it.
- Unit inference from a provider payload may be impossible when the provider
  omits it — that becomes a limitation, not a guess.

## Failure handling

- If the payload has no identity at all, set `usable: false` and say the
  instrument could not be confirmed. Never proceed to analysis of an
  unidentified dataset.

## Example

Dataset: financial_statements, identity PK:ACME, currency PKR, period FY23/FY24.
Issue: `eps` lacks a unit → flag. Issue: FY24 net income present, FY23 missing →
`missingValues: ["FY23 net income"]`, `usable: true` (partial) with a limitation.
