# Recurrence Keying Fix

## Old key

`aggregate_signals` used `lesson["signature"]` when present, otherwise
`signal_signature(kind, condition, action)`. For `successful_procedure` the
producer wrote a templated:

- condition: `A multi-step research procedure completed with no tool failures.`
- action: `This tool sequence is a reusable procedure for similar objectives.`

So every successful procedure collided regardless of the actual tools, while
failure lessons did include tool/error text. The review's null message
(`recurrence not met`) was also a generic text, not the aggregate result, so a
met recurrence could still be reported as unmet.

## New key

`self_improvement/lesson_contract.py:structural_lesson_signature`:

- `successful_procedure` → hash of the ordered `procedure` steps (the canonical
  tool sequence);
- `failure_recovery` → hash of `failedCall | precondition | recoveredCall`
  (failure class + tool + recovery);
- `user_correction` → condition/action (the correction itself);
- no title text, no run id, no timestamp, no args.

`aggregate_signals` always uses this structural key, even for old stored
lessons whose `signature` was derived from the templated text.

The producer now also writes structural condition/action and a title that
includes the full tool sequence:
`skills/learning.py` successful_procedure block.

## Replay of the last 26 reviews (read-only)

Live result: **4 distinct signals**, not 1:

| Occurrences | Eligible | Signal |
|---|---|---|
| 3 | yes | `get_agent` TOOL_ERROR retry |
| 3 | yes | 8-tool audit procedure |
| 1 | no | 4-tool audit procedure |
| 1 | no | 2-tool session procedure |

This is an honest correction to the brief's expected "five collapse to one":
the five text-identical successful-procedure lessons were **not the same
procedure**. The old text key would have falsely merged four distinct
procedures; the structural key separates them. The largest inferred lesson now
has recurrence 3 and is `eligible` (threshold 2).

## Explicit-correction fast path

`aggregate_signals` marks `user_correction` eligible at `distinct >= 1`; inferred
procedures still require ≥2. Test:
`test_explicit_correction_is_eligible_at_recurrence_one`.

## Tests

- `test_recurrence_key_is_structural_not_title_or_timestamp`
- `test_five_identical_lessons_collapse_to_one_recurring_signal`
- `test_explicit_correction_is_eligible_at_recurrence_one`
- `test_a_recurring_recovery_candidate_is_auto_drafted_but_never_enabled`
