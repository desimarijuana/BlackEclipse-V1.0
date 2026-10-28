# Class-Authorized Self-Modification (Tier B)

This is the deliberate step beyond "propose only". The loop may **accept** a
contract-clean, evaluated candidate and **enable** a read-only learned skill
without per-change human typing. It still cannot widen tools, enable effectful
skills, place financial actions, or edit this policy.

## Policy (operator-owned)

Environment / settings:

- `HARNESS_SELF_MODIFICATION` — `off` | `shadow` | `accept` | `enable`
  (default `enable`). `shadow` records what it *would* accept/enable as
  `shadow_*` audit rows but changes no candidate or skill.
- `HARNESS_SELF_MODIFICATION_TTL_DAYS` — default `7`, 1–90.
- `HARNESS_SELF_MODIFICATION_MAX_SKILLS` — active learned-skill cap, default `3`.
- `HARNESS_SELF_MODIFICATION_MAX_ACTIONS` — per-day cap, default `10`.

The module lives under `python/harness/self_improvement/`, so the frozen RSL
target denylist prevents the loop from proposing a code change to it.

## What it may do

1. **Accept a candidate** only when:
   - `candidate_problems()` is empty;
   - `draft_ready()` accepts its recurrence/evidence (a single-occurrence
     `failure_recovery` is not enough);
   - a draft exists (or can be created);
   - `evaluate_skill()` returns `passed`.
2. **Enable a skill** only when:
   - id starts with `learned.`;
   - permissions are a subset of `{data.read, analysis.read, analysis.execute}`;
   - every required tool is registered;
   - the latest evaluation is `passed`;
   - under the active-skill cap and daily-action cap.
3. **Disable** a skill when its grant expires or is revoked.
4. **Keep the loop moving without a restart**: every tick runs
   `auto_draft_ready_candidates()` and then `evaluate_used_skills()` for learned
   skills with at least 3 successful executions.

The generated draft output schema carries an `evidence` field; quality
procedure drafts may also report `limitations` and `missingData`. That makes the
evidence contract pass without weakening the mandatory checks.

An unchanged **passed** version is evaluated once: the version stores the
manifest/version/evaluator/tool-set fingerprint, and a later evaluation with the
same fingerprint is skipped without writing a `SkillEvaluation` row. A manifest,
version, evaluator, or registered-tool change produces a new fingerprint and a
new evaluation.

A version that is not enabled records a machine-readable
`nonActivationCause` (`active_skill_cap`, `daily_action_cap`, `evaluation_not_passed`,
`effectful`, `tool_unavailable`, `shadow_mode`, `auto_enable_off`,
`manifest_unreadable`, `not_learned`). `skill_version_history` prints it as
`notActivated=<cause>`.

`skill_version_history` materialises store-only learned skills with
`registry.load_stored()` before declaring one missing.

It never enables an effectful skill. Skills are declarative; the permission set
is the effect boundary.

## Audit, expiry, revocation

Every action is a durable `SelfModificationAction` row:

`id, kind, subject, evidence, status, createdAt, expiresAt, revokedAt, detail`

- `expiresAt` is set on enablement; the executor disables the skill when due.
- Canary: on every tick, an active grant whose latest evaluation is no longer
  `passed` (or whose skill is no longer enabled) is disabled and revoked.
- `POST /evolution/self-modification/revoke/{action_id}` disables immediately.
- `POST /evolution/self-modification/pause` stops all Tier B actions.
- `GET /evolution/self-modification` shows mode, caps, last result, active grants.
- `GET /evolution/capabilities` is the truthful autonomy matrix used by the
  prompt and marketing: read-only skill creation, memory policy, and recall are
  autonomous; effects, widening, code merge, and policy changes are not.
- `GET /evolution/learning-loop` shows candidate/learned-skill counts, active
  grants, and whether the autonomous tick is running.
- `POST /evolution/self-modification/run` runs one bounded tick.

## Tests

`test_self_modification.py`:

- accept mode accepts but does not enable;
- enable mode enables a read-only skill with audit + expiry;
- TTL expiry disables it;
- `off` and `max_active_skills=0` refuse enablement;
- `shadow` records `shadow_enable_skill` but leaves the skill `draft`;
- a later failed evaluation disables the granted skill and revokes the grant;
- a single-occurrence recovery candidate is not auto-accepted.

`test_skill_lifecycle_tools.py` pins the store-only history fallback;
`test_learning_loop_closure.py` pins the quality evidence shape.

## Still operator-only

`skill_create`, `skill_update`, `skill_learning_set`, effectful/global capability
activation, tool widening, and every financial action.
