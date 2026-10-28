# Learning Loop Map

This map is anchored on the exact strings named in the task. Paths are relative
to `Black-Eclipse-site/python/harness/`.

## Anchor hits

| Anchor | Hit | Meaning |
|---|---|---|
| `only a \`detected\` candidate can be accepted` | `routers/sessions.py:330` (accept route) and `memory_tools.py:673` (dry-run) | The acceptance boundary used to reject the generator's `drafted` state. |
| `constant_confidence` | `self_improvement/lesson_contract.py:248` | Contract check that rejects a fixed confidence. |
| `missing_replayTest` / `missing_<field>` | `self_improvement/lesson_contract.py:223-232` | Contract fields required for `failure_recovery`. |
| `templated_title` | `self_improvement/lesson_contract.py:234` | Rejects the legacy `Recovery after X failure` title. |
| `recurrence not met` | `learning_review.py:318` | Review wording when a typed lesson is not promotable yet. |
| `nonconforming` | `self_improvement/loop_health.py:50` | Scans **detected** candidates against the contract. |

## (a) Candidate state machine

```
detected ──accept──> accepted
   │                    │
   ├──auto-draft──> drafted ──accept──> accepted
   │                    │
   └──quarantine──> rejected (retained, never deleted)
proposed (memory) ──recurrence>=2 + no conflict──> active
```

- Generator persistence: `eclipse_memory/service.py:analyze_run` (saves `detected`).
- Auto-draft: `skills/draft.py:propose_draft` (sets `drafted`, creates a
  `status=draft` skill; never enables it).
- Quarantine: `self_improvement/loop_health.py:quarantine_nonconforming_candidates`.
- Acceptance: `routers/sessions.py:accept_candidate`.

## (b) Candidate generator / detector

- `skills/learning.py:analyze_run` (drafts; failure→recovery pair, user
  correction, repeated procedure, source/provider improvements).
- `eclipse_memory/service.py:analyze_run` (persists only contract-clean drafts;
  updates `occurrenceCount`/confidence on a recurring signature; auto-drafts).
- Structural recurrence: `skills/learning.py:_candidate_recurrence_key`,
  `_record_recurrence`, `_recurrence_count` (tool sequence + failure signature,
  not the title).

## (c) Quarantine validator

- `self_improvement/lesson_contract.py:candidate_problems` (fields, templated
  title, constant confidence).
- `self_improvement/loop_health.py:nonconforming_candidates` scans only
  `status="detected"`; rejected legacy rows are not re-counted.
- `service.py:run_startup_maintenance` runs quarantine, then auto-draft, then
  evaluation.

## (d) Acceptance route

- `routers/sessions.py:accept_candidate` is operator-gated (`require_operator`
  plus `payload.operator`). It now accepts `detected` and `drafted`, re-validates
  the contract, creates the inert draft when needed, verifies the stored skill,
  and records `accepted`. It never enables.
- Read-only preview: `memory_tools.py:learning_candidate_validate_handler` mirrors
  the same rules (404/409/422/200).

## (e) Memory promotion (`proposed` → `active`)

- Write/conflict gate: `eclipse_memory/service.py:write_memory`,
  `eclipse_memory/conflicts.py:detect_conflict`.
- Promotion: `eclipse_memory/service.py:promote_confirmed_proposals`
  (recurrence ≥ 2 and no conflict; conflict rows stay `proposed`).
- Startup trigger: `service.py:run_startup_maintenance`; write trigger:
  `commit_decision` calls the same function.

## (f) Outcome scoring

- Skill evaluation: `skills/evaluation.py:evaluate_skill` (deterministic
  dimensions, including `discrimination`); retirement:
  `skills/evaluation.py:retire_non_discriminating` (deprecate, never delete).
- Startup: `skills/draft.py:evaluate_drafted_skills` and
  `evaluate_used_skills` (learned drafts; learned skills after N completed uses).
- Advice scoring: `advisory/service.py:auto_evaluate` and
  `advisory/tools.py:advisory_evaluate_outcomes`; unattended cadence in
  `advisory/cadence.py` (one bounded task, `HARNESS_ADVISORY_AUTO_EVALUATE`
  kill switch, `/advisory/cadence` + `/advisory/cadence/run`).

## Scoring / recurrence anchors (2026-10-28)

| Anchor | Hit | Role |
|---|---|---|
| `"recurrence not met" / "typed lesson observed"` | `learning_review.py:316-318` | Generic review null text; it is not the aggregate recurrence result. |
| `structural_lesson_signature` | `self_improvement/lesson_contract.py` | New keyer: procedure steps / failed-recovered-precondition; ignores stored templated signatures. |
| `aggregate_signals` | `self_improvement/lesson_contract.py` | Folds reviews by the structural key; explicit corrections eligible at 1, inferred at 2. |
| `advisory_evaluate_outcomes` | `advisory/tools.py:92` | Operator/trigger evaluation surface. |
| `auto_evaluate` | `advisory/service.py:209` | Skips no-price and not-due rows; evaluates only due+priced. |
| `skill_version_evaluate` / `skill_discrimination_check` | `skills/lifecycle_tools.py:245/183` | Existing operator evaluation surfaces; retirement helper is `skills/evaluation.py:retire_non_discriminating`. |
| `"unscored" / "need backfill"` | `advisory/scoring.py` | Canonical states; both gate and scorecard call `counts`. |

## Known gaps at map time

1. `drafted` is accepted now (`routers/sessions.py` accepts detected+drafted).
2. Legacy failure_recovery rows lacked contract fields (quarantined; new
   producer is contract-clean).
3. Constant-confidence legacy rows (quarantined; producer derives confidence).
4. Advisory outcome scoring has a trigger, but **no automatic cadence** was
   added; live `evaluated=0`, all 19 rows have no entry price.
5. 109 legacy reviews and 14 legacy recommendations are history; reviews are
   marked `legacyUnscored`, advisory rows get `legacyUnscored`; no scores are
   invented.
