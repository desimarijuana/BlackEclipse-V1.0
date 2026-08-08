# RECOVER.md — Failure Recovery & Safe Coding Protocol

> When an implementation starts failing: **STOP → INSPECT → IDENTIFY → RECOVER → VERIFY**.
> Do not blindly keep modifying code. The goal is to make a bad situation better, not worse.

---

## Core Principle

Never keep piling changes onto a broken state. Stop, understand, then take the **smallest safe recovery path**.

## Recovery Process

1. **Identify what changed** — what did you just edit/run?
2. **Identify when the problem started** — was it working before this change?
3. **Inspect logs/errors** — check the terminal output, browser console, `npm run build`, `npx tsc --noEmit`.
4. **Compare against the previous working state** — use Git (`git status`, `git diff`, `git log`) to see exactly what changed.
5. **Determine the smallest safe recovery** — revert only the broken change, preserve unrelated working changes.
6. **Re-run tests/builds** — `npm run test`, `npx tsc --noEmit`, `npm run build`.
7. **Verify the system returns to a known-good state** — run the dev server and confirm.
8. **Document the failure in REMEMBER.md** if it contains useful future knowledge.

## Never Do This

- ❌ Randomly rewrite large portions of the application.
- ❌ Delete working code just to make an error disappear.
- ❌ Change multiple unrelated systems simultaneously.
- ❌ Modify database schemas without understanding existing data (if a DB exists).
- ❌ Remove dependencies without checking usage.
- ❌ Disable validation to hide errors.
- ❌ Suppress errors instead of fixing the root cause.
- ❌ Replace an existing architecture with a new one without justification.
- ❌ Claim a fix worked without verification.

## Recovery Levels

Use the **smallest** level necessary to restore function.

| Level | Scope | Actions |
|---|---|---|
| **L1 — Local Fix** | A single function/expression | Fix the specific bug, re-verify |
| **L2 — Component Recovery** | One component | Revert/replace the broken component, keep others |
| **L3 — Service Recovery** | An API route or module | Restore the route/module to its last known-good state |
| **L4 — Database/Data Recovery** | Data integrity | Inspect schema/deps first; prefer migrations; back up before destructive changes |
| **L5 — Full System Recovery** | The whole app | Rebuild from a known-good commit; never reset data casually |

## Database Safety

- Never blindly delete production-like data.
- Inspect schema and dependencies first.
- Prefer migrations over destructive changes.
- Back up important data when appropriate.
- Never reset the database simply because a query failed.

## Git Safety

- Inspect `git status`, `git log --oneline`, and `git diff` before acting.
- Use commits as recovery points.
- Never overwrite unrelated user changes.
- Never perform destructive Git operations (`reset --hard`, `force-push`) without explicit authorization.
- **Never commit, push, or create branches/PRs unless the user explicitly asks.**

## Memory-Specific Guidance

This machine has limited RAM (7.9GB). If a build fails with a `memory allocation ... bytes failed` error:
- Close heavy apps (Edge, Zoom) to free RAM.
- Do **not** try to compile the huge `market-overview.tsx` with low free memory.
- Consider further splitting large files into hooks/modules rather than fighting the compiler.

## Failure Documentation

If a significant failure occurs, record:

```
## Problem:
## Root Cause:
## What Was Tried:
## What Worked:
## What Did Not Work:
## Future Prevention:
```

Add this to REMEMBER.md so the same mistake isn't repeated.
