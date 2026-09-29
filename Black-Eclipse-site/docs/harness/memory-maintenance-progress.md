---
title: Memory & Skills Maintenance Hardening — Progress
status: Current
last-verified: 2026-09-29
---

# Memory & Skills Maintenance Hardening — Progress

Implementation log for the seven milestones in
`docs/harness/memory-maintenance-opencode-prompt.md`. The runtime is Python
(`python/harness/`); Next.js is a thin front door.

## Milestone 0 — Audit (baseline)

Verified against the current tree. Source code was authoritative.

**Baseline checks (2026-09-29, vendored Python 3.12.8):**

| Check | Result |
|---|---|
| `npx tsc --noEmit` | pass |
| `npm run test` | pass |
| `python -m pytest python/tests -q` | pass (all) |
| `python -m harness.eclipse_memory.eval` | recall=1.0 precision=0.727 leakage=0 forbidden=0 gate PASS |
| `python -m harness.eclipse_memory.eval.contradictions_cli` | recall=1.0 falseConflict=0.0 unauthorizedSupersessions=0 gate PASS |

Findings A1–A10 re-confirmed:

- **A1** confirmed: `register_memory_tools(self.registry)` is unconditional in
  `AgenticService.__init__` (service.py:79); `"memory"`,
  `session_search`, `session_open`, `memory_search_external` are unconditional
  entries in `ECLIPSE_AGENT.tools` (agents.py:50–62). `memory_enabled` never
  removes a tool from the bound schema.
- **A2** confirmed: `graph.py` `_history_messages` silently truncates at
  `MAX_HISTORY_TURNS=20` / `MAX_HISTORY_CHARS=40_000`; no summary seam exists.
- **A3** confirmed: `rg` for curator/stale_after/archive_after/skill_usage/
  usage_count across `python/harness/` returns zero.
- **A4** confirmed: `memory-files.ts` has atomic write/backup/restore/
  `expectedVersion` but no BOM strip, no unreadable-refusal, no drift detection.
- **A5** confirmed: `_profile_context` materializes once per run (graph.py:534).
- **A6** confirmed: no trivial-prompt gate; only `decision.py`'s greeting ignore.
- **A7** confirmed: `semantic.py` (433 LOC) exists, off by default.
- **A8** confirmed: `profile_block`/`skill_manifest`/`memory_block` are rebuilt
  per run; `prompt_cache_key` is identity-only.
- **A9** confirmed: **no** `pinned` column on `SkillVersion`; migration needed.
- **A10** confirmed: `RunInput.history` carries the full prior conversation from
  the client each turn.

Note: the prompt's named `npx tsc --noEmit` and eval CLIs need the vendored
interpreter with `PYTHONPATH=python`; the `python` shim is not on PATH.

## Milestone reports

### Milestone 1 — Skill maintenance ✅

- New `python/harness/skills/maintenance.py` (deterministic staleness/usage/
  retirement from existing `SkillExecution`/version rows; report-only default;
  pinned versions exempt; archive-never-delete via the existing `deprecated`
  lifecycle state; `SkillMaintenance` ledger).
- Migration 22 adds `SkillVersion.pinned` (additive, survives reopen);
  migration 23 adds the `SkillMaintenance` ledger.
- Policy keys: `skill_maintenance_enabled` (false), `skill_stale_after_days`
  (90), `skill_archive_after_days` (180), `skill_maintenance_auto_archive`
  (false), all bounded.
- Wired into `AgenticService.run_startup_maintenance()` (existing lifespan; no
  daemon/thread). Routes `GET /skills/maintenance`, `POST /skills/maintenance/run`,
  `POST /skills/{id}/pin`. UI: Skills → Maintenance tab
  (`src/components/screens/skills/skill-maintenance.tsx`).
- Fixed a pre-existing registry bug: `resolve_dependencies` treated a skill's own
  stored status as a dependency, so a disabled/deprecated skill could never be
  re-enabled. The root's own status no longer gates its own enablement.
- Evidence: `python/tests/test_skill_maintenance.py` (12 tests, incl. pin-survives
  reopen, report-only default, idempotent re-run, reversible archive).

### Milestone 2 — Pre-compression capture ✅

- New `python/harness/eclipse_memory/dropped_context.py`. Deterministic-first
  (reuses `intent.detect_memory_intent` + `decision.decide_turn`); inert
  candidates only; bounded (40 turns / 8 items / 400-char item / 2.4k block);
  fail-closed (no lossy summary, honest event); fenced, sanitized data block.
- `graph.py`: `_bounded_history` splits kept/dropped; `_dropped_context_block`
  is the seam; a sub-bound history produces **no** block and is byte-identical to
  before. The block rides the same per-run SystemMessage slot; the system-prompt
  head and tool schema are untouched.
- Evidence: `python/tests/test_dropped_context.py` (17 tests).

### Milestone 3 — File-projection guards ✅

- `src/lib/harness/memory-files.ts`: `readMemoryFileStrict` (strict UTF-8 decode,
  BOM strip, ENOENT→null), `detectExternalDrift`, `safeWriteProjection` (refuses
  unreadable, refuses drift with a timestamped `.bak`), `applyFileEdit` refuses
  unreadable files and a batch that would empty a non-empty entry file.
  `regenerateMemoryFiles` and `previewMemoryImport` use the guarded read.
- Evidence: `src/lib/harness/memory-files-guards.test.ts` (11 tests); existing
  `memory-files*.test.ts` still pass.

### Milestone 4 — Surface honesty ✅

- `prompts.filter_system_prompt` (pure) and `graph.resolve_surface` /
  `surface_disabled_tools`, resolved PER RUN in `execute_run` from policy. A
  disabled store drops `memory` / `memory_search_native` / `memory_search_external`
  / `session_search` / `session_open` from the allowlist and its guidance from the
  prompt. Prompt is byte-stable for fixed settings.
- Evidence: `python/tests/test_surface_honesty.py` (9 tests).

### Milestone 5 — Trivial-prompt gate ✅

- New `python/harness/eclipse_memory/is_trivial.py` (pure; anchored greetings,
  slash commands, empty; explicit memory directives never trivial). Used in
  `_apply_memory_intent` and `_memory_context`; writes nothing, changes no reply.
- Evidence: `python/tests/test_trivial_prompt_gate.py` (parameterized table).

### Milestone 6 — Retire the semantic layer ✅

- Deleted `eclipse_memory/semantic.py`, `eval/semantic.py`, `eval/semantic_cli.py`,
  `eval/semantic_v1.json`; the seven `semantic_conflict_*` +
  `semantic_recall_tiebreak` policy keys; `service._semantic_conflict_candidate` /
  `_record_semantic_diagnostics` / `semantic_status` / `_semantic_stats`; the
  retrieval `_semantic_reorder` + `semantic_tiebreak`; TS types/client/browser/UI
  controls; the rebuild route. Migration 24 removes any stored dead
  semantic policy overrides (recorded in `MemoryPolicyMigration`).
- Kept: `contradictions` eval + thresholds; tombstones for
  `/eclipse-memory/semantic-status` and `/semantic/rebuild`.
- Repurposed the semantic safety cases into `contradictions_v1.json` (v3, now 49
  cases) as lexical regression cases (kinds `numeric-value`/`paraphrase-conflict`).
- Evidence: `contradictions_cli` gate PASS (recall 1.0, false-conflict 0.0,
  unauthorizedSupersessions 0); no dangling references (rg + tsc clean).

### Milestone 7 — Measurement honesty ✅

- New `python/harness/eclipse_memory/usage_report.py` + `service.usage_report` +
  `GET /eclipse-memory/usage-report`. Bounded, read-only, content-free: durable-write
  outcomes, real conflict resolutions + dismissed-rate false-positive proxy, and
  likely-missed conflicts for human review. Empty data → honest empty report.
- UI: Memory Lifecycle → "Real usage" panel. Honest interpretation added to the
  contradiction doc and the eval's interpretation block.
- Evidence: `python/tests/test_usage_report.py` (7 tests).

## Limitation fixes

### Phase 1 — correctness/clarity ✅

- **P1.1** distinct, restorable `archived` skill status (manifest + TS + registry
  + UI); maintenance retirement now uses it instead of `deprecated`.
- **P1.2** surface honesty at the injection layer: `memory_enabled=false` no
  longer injects retrieved memory or the profile.
- **P1.3** optional, policy-gated model-assisted dropped-context extraction
  (default off; injectable model; inert/bounded/fail-closed).
- **P1.4** `python/tests/test_migration_matrix.py` (full reopen matrix) + hygiene.

### Phase 2 — measurement honesty ✅

- **P2.1** operator ground-truth conflict labels (`label_conflict`, route, UI
  wiring) → real precision in the usage report (proxy kept as secondary).
- **P2.2** usage report half-window trend + `smallSample` flag; UI surfacing.
- **P2.3** skill usage trend (active/dormant/never) + content-free near-duplicate
  skill detector.

### Phase 3 — robustness/concurrency ✅

- **P3.1** single-writer maintenance lock + compare-and-set retirement
  (`store.transition_version_status`); concurrent pass reports `skipped`.
- **P3.2** cross-cutting reopen matrix (both DBs + projection backup/restore).
  Fixed a real pre-existing bug: `restoreMemoryFiles` rejected every real backup
  dir (ISO `Z`), so restore never found its own backup.

## Checks (after all milestones)

| Check | Result |
|---|---|
| `npx tsc --noEmit` | pass |
| `npx vitest run` | 146 files / 1818 tests pass |
| `python -m pytest python/tests -q` | all pass |
| `python -m harness.eclipse_memory.eval` | gate PASS (recall 1.0, precision 0.727, leakage 0, forbidden 0) |
| `python -m harness.eclipse_memory.eval.contradictions_cli` | gate PASS (recall 1.0, false-conflict 0.0, unauthorized 0) |
| `jdds.db` | untouched by this work (was pre-modified in the working tree) |

