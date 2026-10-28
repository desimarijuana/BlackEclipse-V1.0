# Class-Authorized Self-Modification (Tier B)

This is the deliberate step beyond "propose only". The loop may **accept** a
contract-clean, evaluated candidate and **enable** a read-only learned skill
without per-change human typing. It still cannot widen tools, enable effectful
skills, place financial actions, or edit this policy.

## Policy (operator-owned)

Environment / settings:

- `HARNESS_SELF_MODIFICATION` — `off` | `accept` | `enable` (default `enable`).
- `HARNESS_SELF_MODIFICATION_TTL_DAYS` — default `7`, 1–90.
- `HARNESS_SELF_MODIFICATION_MAX_SKILLS` — active learned-skill cap, default `3`.
- `HARNESS_SELF_MODIFICATION_MAX_ACTIONS` — per-day cap, default `10`.

The module lives under `python/harness/self_improvement/`, so the frozen RSL
target denylist prevents the loop from proposing a code change to it.

## What it may do

1. **Accept a candidate** only when:
   - `candidate_problems()` is empty;
   - a draft exists (or can be created);
   - `evaluate_skill()` returns `passed`.
2. **Enable a skill** only when:
   - id starts with `learned.`;
   - permissions are a subset of `{data.read, analysis.read, analysis.execute}`;
   - every required tool is registered;
   - the latest evaluation is `passed`;
   - under the active-skill cap and daily-action cap.
3. **Disable** a skill when its grant expires or is revoked.

It never enables an effectful skill. Skills are declarative; the permission set
is the effect boundary.

## Audit, expiry, revocation

Every action is a durable `SelfModificationAction` row:

`id, kind, subject, evidence, status, createdAt, expiresAt, revokedAt, detail`

- `expiresAt` is set on enablement; the executor disables the skill when due.
- `POST /evolution/self-modification/revoke/{action_id}` disables immediately.
- `POST /evolution/self-modification/pause` stops all Tier B actions.
- `GET /evolution/self-modification` shows mode, caps, last result, active grants.
- `POST /evolution/self-modification/run` runs one bounded tick.

## Tests

`test_self_modification.py`:

- accept mode accepts but does not enable;
- enable mode enables a read-only skill with audit + expiry;
- TTL expiry disables it;
- `off` and `max_active_skills=0` refuse enablement.

## Still operator-only

`skill_create`, `skill_update`, `skill_learning_set`, effectful/global capability
activation, tool widening, and every financial action.
