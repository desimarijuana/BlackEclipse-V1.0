---
title: Harness — Memory Retention & Conflict Audit
status: Current
last-verified: 2026-09-25
---

# Memory Retention & Conflict Handling — Audit

Code-traced audit of retention and contradiction behaviour before hardening.
Single-user local product: `userId`/`scopeId` are labels, not account
identities. Findings cite the code path, not assumptions.

> **Post-hardening.** The gaps below were then fixed (Phases 2–5). Current
> behaviour: the sweep runs at startup via the existing FastAPI lifespan
> (`run_startup_maintenance`), is idempotent/observable (`MemoryMaintenance`,
> migration 11), confirmation/renewal refresh automatic expiry, authority
> actually controls contradiction resolution, and detection uses subject aliases
> + normalized tokens. See "Resolved" at the end of this document.

## Retention

| Path | Actual behaviour | File |
|---|---|---|
| Automatic memory creation | `_derive_authority(source)` returns `automatic` for any source not in `EXPLICIT_SOURCES`; an automatic write with no caller `expires_at` gets `expires_at = _retention_expiry()` from `retention_days` (0 = never). | `service.py:76,180–186,371` |
| Explicit memory creation | `EXPLICIT_SOURCES = {explicit_user, user_correction, manual, imported}` → `explicit`; the retention branch is skipped, so **explicit memory never receives a policy expiry**. | `service.py:72,185` |
| `expiresAt` persistence | Persisted by `save_memory`; returned on read. | `store.py:66–84` |
| Retention policy change | `retention_days` is read **only at write time** (`_retention_expiry`). Changing it never mutates existing rows. | `service.py:371–383` |
| Retention sweep | `expire_due_memories()` marks due `active`+`automatic` rows `expired`. **Reachable ONLY through the manual endpoint `POST /eclipse-memory/retention/sweep`** — not at boot, not in instrumentation, not on retrieval. | `service.py:385–412`, `main.py:782` |
| Retrieval-time expiry exclusion | Authoritative and independent of the sweep: a candidate with `expiresAt < now` is excluded with reason `expired`. | `retrieval.py:292–294` |
| Explicit confirmation | `confirm_memory()` bumps `lastConfirmedAt` only — it does **not** clear or extend `expiresAt`. A duplicate re-save calls it. | `store.py:259–266`, `service.py:143–144` |
| Memory renewal | `renew_memory(days)` sets `expiresAt` (days>0) or clears it (days≤0) and bumps `lastConfirmedAt`/`lastReviewedAt`. Exposed as `POST /memories/{id}/renew`. | `service.py:414–430` |
| Sweep observability | Returns `{expired, ids}` only — no inspected count, no skipped count, no failure reason, no persisted "last successful sweep". | `service.py:385–412` |

### Retention gaps

1. **The sweep never runs automatically.** `_lifespan` calls only
   `service.start_mcp()`. Documentation (`harness/architecture.md`,
   `phase-3-memory-progress.md`) implies retention "is applied", which is
   misleading — it requires a manual operator call.
2. **No boot/recovery hook** invokes it, so due automatic memories stay `active`
   until an operator manually sweeps (retrieval still excludes them by
   timestamp, but their persisted status and lifecycle views are stale).
3. **Confirmation does not refresh expiry.** Restating an automatic memory keeps
   its original `expiresAt`, so a memory the user just re-affirmed can expire.
4. **No observable sweep result** (inspected/skipped/failed/lastSweepAt).
5. **Policy-change semantics are undocumented**: lowering `retention_days` has
   no effect on existing rows (including ones written while it was 0, which have
   `expiresAt = NULL`).

## Contradiction handling

| Path | Actual behaviour | File |
|---|---|---|
| Conflict detection | `detect_conflict` compares only same `memoryType`, same `scope`+`scopeId`, requires same subject **or** ≥2 shared raw content tokens, then requires replacement language **or** an opposing-polarity pair. | `conflicts.py:113–162` |
| Replacement | If `assessment.replacement`, supersede all related and write the new record active. | `service.py:306–313` |
| Ambiguous contradiction | No replacement language → new record written `proposed`; old stays active. | `service.py:314–319` |
| **Authority** | `_resolve_conflict(..., new_authority=...)` **accepts `new_authority` and never reads it** — a dead parameter. Explicit-vs-automatic without replacement wording is treated as ambiguous, so an **explicit statement does not override an automatic one** unless it contains "now"/"instead"/etc. | `service.py:290–319` |
| Correction / supersession | `apply_explicit_intent` correct path supersedes the target and links old→new. | `service.py:757–771` |
| Legacy active rows | Retrieval guard `_highest_authority_only` groups by exact subject + memoryType + scope and keeps explicit over automatic (then newest). | `retrieval.py:374–406` |
| Subject aliases | **Not consulted.** `normalize.SUBJECT_ALIASES` exists but `conflicts.py` ignores it, so the same dimension under a different subject key is a missed conflict. | `conflicts.py` |
| Normalized tokens | **Not used.** Overlap uses raw `[a-z0-9]+` minus a stopword list; no synonym/stem folding. | `conflicts.py:91–95` |
| Provenance | Not considered in conflict resolution. | `conflicts.py` |

### Contradiction gaps

1. **Authority is inert** (`new_authority` unused). Requirements: explicit beats
   automatic even without replacement wording; automatic never overrides
   explicit. Only the second half currently holds.
2. **No aliases / normalization** in detection → same-dimension conflicts under
   different subject keys are missed; the raw-token overlap is simultaneously
   too broad (generic words) and too narrow (synonyms).
3. **One polarity pair is dangerously broad**: `(\balways|\bdo\b)` vs
   `(never|don't|avoid)` — `do` matches almost any sentence, creating false
   conflicts on same-subject/overlap items.
4. **`memoryType` is part of eligibility**, so a factual `observation` and a
   `preference` on the same topic never conflict (correct — must be preserved as
   a documented negative case).
5. The conflict **reason** is generic; requirement 12 wants concrete reasons
   (explicit replacement, authority override, needs review, ambiguous explicit,
   confirmation, unrelated scope, unrelated subject).

## Tests / UI / docs mismatch

- Tests assert the *current* ambiguous-vs-replacement split; they do **not**
  cover explicit-over-automatic-without-wording, aliases, or the polarity
  false-positive case.
- The Control Room Lifecycle tab shows status/authority/`lastUsedAt` and
  explanation text, but not expiry cause, confirmation/renewal actions, or the
  supersede link prominently.
- Docs state the sweep "is applied" without saying it is manual-only.

## Baseline tests added

`python/tests/test_memory_retention_conflicts_baseline.py` pins the traced
behaviour (automatic expiry, explicit exemption, manual-only sweep effect,
timestamp exclusion, authority-inert ambiguity, different-scope/subject
non-conflicts) so the hardening changes are measured against a recorded baseline.

## Resolved

### Retention

- The sweep now runs automatically at runtime startup through the existing
  FastAPI lifespan (`main._lifespan` → `AgenticService.run_startup_maintenance`
  → `EclipseMemoryService.run_retention_maintenance`). No new daemon or thread.
- The sweep never raises; a failure is recorded and reported, so it cannot stop
  the application from starting. Idempotent (re-running inspects 0 once done).
- Observable via `MemoryMaintenance` (migration 11): operation, ranAt, ok,
  inspected, expired, skipped, error. Exposed on `/eclipse-memory/health`
  (`retention`) and `GET /eclipse-memory/retention`. No content is exposed.
- Confirmation and renewal refresh `lastConfirmedAt`; an automatic memory's
  `expiresAt` is extended from the current `retention_days` on confirmation, and
  `renew_memory(days)` sets/clears it. Explicit memories never gain an expiry.
- A retention-policy change never mutates existing records (expiry is only
  stamped at write/confirm time).
- A duplicate write can no longer revive an inert (expired/superseded/archived/
  rejected) record — `_find_duplicate` searches all statuses and returns the
  inert record unchanged unless the new statement carries replacement intent.
- Retrieval keeps excluding a due memory by timestamp, independent of the sweep.

### Contradiction handling

- `_resolve_conflict` now uses `new_authority` (no dead parameter): explicit
  replacement and explicit-over-automatic supersede; automatic-vs-explicit and
  two ambiguous explicit statements store the new record inert (`proposed`).
- Detection uses subject identity + `normalize.SUBJECT_ALIASES` +
  normalized (synonym/stemmed) tokens, with a tightened opposing-pair table (the
  broad `\bdo\b` arm removed). Negative cases (candlestick vs line, unrelated
  overlaps, scope/subject separation, observation vs preference) are covered.
- Each decision records a concrete reason (explicit replacement, explicit
  authority overrides automatic, automatic conflict requires review, ambiguous
  explicit contradiction, same statement confirmation, unrelated scope/subject).
- The explicit-save path returns an honest `needs_review` outcome (never claims
  active truth) when a conflict stored the new record inert.

