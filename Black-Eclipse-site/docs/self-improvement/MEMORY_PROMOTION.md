# Memory Promotion

## Rule

`EclipseMemoryService.promote_confirmed_proposals` promotes a `proposed` row to
`active` iff:

1. its `statusReason` does **not** record a conflict;
2. `recurrence_count(content_signature(content)) >= 2`;
3. `detect_conflict` against active memory returns no conflict;
4. dedup/conflict runs **before** the update.

Triggered at startup (`run_startup_maintenance`) and on `commit_decision`, so a
second confirming observation can promote without a human. Conflicting rows stay
`proposed` with their explicit conflict reason.

## Gate order

```
proposed row
  -> conflict reason?        yes -> keep proposed
  -> recurrence < 2?          yes -> keep proposed
  -> detect_conflict?         yes -> keep proposed
  -> update status=active + memory.promoted event
```

## Tests

- `test_proposed_memory_promotes_after_recurrence_but_not_on_conflict`
  covers one observation (stays proposed), two observations (active), and a
  conflict-flagged row (stays proposed).

## The existing stuck row (analysed, not hand-promoted)

Live row: `mem_7b14413c-8eb9-4560-97b4-276a0db4cca5`

- content: `I prefer short comparison tables with a one-line takeaway after each table`
- status: `proposed`
- statusReason: `conflict: automatic conflict requires review`
- createdAt: `2026-10-28T05:45:41.779Z`
- content signature `a58fce5952c759dc15aa8016`, `seenCount = 0`

It fails **two** conditions: recurrence is 0 (<2), and the row is explicitly
conflict-flagged (it overlaps the existing answer-format preference). It is not
hand-promoted. A second confirming observation would satisfy recurrence, but the
conflict flag still keeps it reviewable until the operator resolves the
dimension collision.
