# Advisory Scoring Changes

## Root cause of the count mismatch

The gate and the scorecard answered different questions:

- `self_improvement/loop_health.py` `_bucket` counted `unscored` as
  `horizon in (None, "", "unscored")`.
- `advisory/service.py:scorecard` counted `needsBackfill` when **method OR
  horizon** was missing, and `unscored` only when horizon was missing.

After `backfill_scoring_fields` set a default horizon but left the method
`unclassified`, the scorecard reported `unscored=0, needsBackfill=14` while the
gate still looked at horizon/method differently. Two predicates, two answers.

## Canonical definition

`harness/advisory/scoring.py` is the ONE definition:

- `evaluated` — an `AdvisoryOutcome` row exists.
- `scorable` — entry price present, horizon stated, `dueAt` elapsed, not yet
  evaluated.
- `no_entry_price` — no stored `entry_price` basis; cannot be marked honestly.
- `unscored` — no stated horizon; nothing can ever be scored.
- `not_due` — entry price + horizon, but `dueAt` is in the future.
- `needsBackfill = no_entry_price + unscored`.
- `overdue = scorable`.

`AdvisoryService.scorecard` and `loop_health._bucket` now both call
`advisory.scoring.counts`. No duplicated counting remains.

## S2 — evaluation fires on the scorable set

`AdvisoryService.auto_evaluate` now:

1. skips rows with no outcome but no entry price (`skippedNoPrice`);
2. skips rows whose `dueAt` is missing or in the future (`skippedNotDue`);
3. evaluates only the due, priced rows;
4. returns counts and ids for each skip reason.

Test: `test_auto_evaluate_scores_only_due_rows_with_a_price` — exactly
`evaluated=1, skippedNoPrice=1, skippedNotDue=1`.

**Cadence (Phase 1):** `advisory/cadence.py` runs a bounded, unattended tick.

- `HARNESS_ADVISORY_AUTO_EVALUATE` — kill switch, default on (`0` disables).
- `HARNESS_ADVISORY_EVAL_INTERVAL_SECONDS` — default `900`.
- `HARNESS_ADVISORY_EVAL_MAX` — scan/tick cap, default `50`.
- `HARNESS_ADVISORY_BENCHMARK_RETURN` — optional scalar; empty means
  realized-vs-zero with an honest note, never an invented benchmark.
- `GET /advisory/cadence` and `POST /advisory/cadence/run` are operator-gated
  and expose the last tick.
- The tick first checks `due_decisions`; if nothing is due it makes **no market
  request**. It never overlaps with a running tick.

Tests: `test_advisory_cadence.py` (due+priced → 1 evaluated; no price and
future due counted separately; nothing due → zero gateway calls; kill switch).

## S3 — retire non-discriminating skills

`skills/evaluation.py:retire_non_discriminating` deprecates a skill whose
`discrimination` dimension is `failed` (identical or worse vs base). The row is
retained, never deleted. `skills/draft.py:evaluate_used_skills` evaluates
`learned.*` skills after ≥3 completed uses; `evaluate_drafted_skills` evaluates
drafts at startup.

Tests: `test_identical_metrics_retire_the_skill_not_keep_it`,
`test_loop_end_to_end_generate_accept_enable_score_retire`.

## S4 — legacy advisory debt

`AdvisoryDecision.legacyUnscored` is an additive column. Startup marks rows
created before `CONTRACT_SINCE` once; history is not rewritten and no score is
invented. `GET /advisory/legacy` explains each row, and
`POST /advisory/backfill-entry-prices` (dry-run first) can add a **real**
historical entry price with source/as-of provenance. See `LEGACY_DEBT.md`.

## Live report (read-only)

19 recommendations; 0 evaluated; 0 scorable. The gate's legacy bucket reports
**14 `unscored`** (no stated horizon) and the current bucket reports **5
`no_entry_price`**; the scorecard totals are `unscored=14, noEntryPrice=5,
needsBackfill=19` from the same `counts` function. All 14 legacy rows are
**genuinely unscorable**: no stated horizon and no stored entry-price basis.
None can be backfilled without inventing a price.

## Not fixed

- No retro-fill of legacy scores (no entry price or horizon exists). The 14
  rows stay `legacyUnscored`; the cadence cannot score them without inventing a
  mark.
- No per-decision benchmark series yet; the cadence uses one optional scalar
  benchmark return or realized-vs-zero with a note.
