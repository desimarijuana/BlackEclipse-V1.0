---
title: Harness — Memory Maturity Baseline
status: Current
last-verified: 2026-09-30
---

# Memory Maturity Baseline (Phase 0)

Written before any implementation change, as the reference point for the
memory-maturity work. Black Eclipse is an open-source, **single-user local**
application: `userId` and `scopeId` are local memory labels, not security
identities. Nothing here assumes hosted accounts or multi-tenant auth.

> **Post-implementation note (Phase 9).** The phases below were implemented
> without rewriting the architecture. The baseline metrics are retained here for
> comparison; the after metrics are in `phase-3-memory-progress.md` (Memory
> Maturity section). No semantic/embedding retrieval was added — the labeled
> evaluation is still the evidence, and the deterministic retriever now serves
> the synonym/typo slices it previously missed.

## Current architecture (as built)

* One SQLite file `eclipse-memory.db`, owned solely by
  `python/harness/eclipse_memory/` (`EclipseMemoryDb` → `EclipseMemoryStore` →
  `EclipseMemoryService`). Migrations are an append-only list in `schema.py`
  recorded in `SchemaMigration`.
* Writes go through `EclipseMemoryService.write_memory` only: validate type →
  content → source allowlist → force preferences into user scope → dedupe by
  signature → storage budget → persist → audit event.
* Every write path is authorized by the shared gate
  `eclipse_memory/decision.py` (`decide_turn` for a user turn,
  `authorize_proposal` for model/UI/analysis proposals): four outcomes
  `save | suggest | history_only | ignore`.
* **Verification is independent of `source` (by design).** `source=explicit_user`
  grants *authority* (never auto-expires, wins conflicts) but is stored
  `verification='unverified'`; only an explicit `verification="verified"`
  argument or a user-provided correction (`record_correction`) sets
  `verified`. So "most records are unverified" is expected, not a defect — the
  flag marks *evidence-backed*, not *user-stated*. The model `memory` tool
  refuses a self-initiated `save` unless the user turn requested it
  (`authorize_proposal`); that write gate is intended.
* Retrieval is `eclipse_memory/retrieval.py`: candidate search → scope/status/
  expiry/low-confidence filter → deterministic lexical ranking (word-boundary
  keyword, exact subject, importance, confidence, verification, access count) →
  character budget → `<memory-context>` block → access counters → audit row.
  Standing user rules (`preference`/`constraint`) are injected every turn; all
  other types require a lexical relevance signal.
* Skills share the same store (`Skill*`, `LearningCandidate`, …); promotion is
  evaluation + operator gated.
* APIs: Python FastAPI `/eclipse-memory/*` (`main.py`), Next.js proxies
  `src/app/api/eclipse-memory/**`, UI `src/components/screens/eclipse-memory/`.
* Measurement seam: `eclipse_memory/eval/` (`dataset_v1.json` + runner).

## Baseline retrieval evaluation

`python -m harness.eclipse_memory.eval` (dataset `memory-retrieval` v1):

| Metric | Baseline |
|---|---|
| recall | 0.900 |
| precision (topical) | 0.714 |
| paraphrase recall (`byKind.paraphrase`) | 1.000 (3/3) |
| synonym-paraphrase recall | 0.500 (1/2) |
| forbidden hits | 0 |
| scope leakage | 0 |
| no-match clean | true |
| context-budget violations | 0 |

Per-kind: negative 1.0, normal 1.0, paraphrase 1.0, scope 1.0, stale 1.0,
synonym-paraphrase 0.5. `recallSupported` (normal+paraphrase) = 1.0.

## Tests understood

`python/tests/`: `test_eclipse_memory.py`, `test_memory_policy.py`,
`test_memory_retrieval_eval.py`, `test_memory_selectivity.py`,
`test_memory_api_auth.py`, `test_suggestion_api_scope.py`, `test_memory_tools.py`,
`test_phase3m_reliability.py`. Baseline run of the memory-focused subset: **133
passed**.

## Gaps located in code (not speculation)

1. **Paraphrase retrieval** — ranking is lexical only (`retrieval._score` token
   match). The eval's `synonym-paraphrase` slice is 0.5: a query sharing no exact
   token ("which money should accounts be denominated in?") misses a memory
   ("reporting currency … PKR"). No normalization/synonyms/stemming exist.
2. **Contradiction handling** — there is no conflict detection. `write_memory`
   dedupes only on an *identical* signature; a re-stated preference with changed
   meaning ("I prefer concise answers" then "I prefer detailed answers now")
   creates a **second active memory**. `supersede_memory` exists but is only
   called by explicit correct/forget.
3. **Expiry & lifecycle** — `MemoryRecord` has `expiresAt`, `reviewedAt`,
   `lastAccessedAt`, `accessCount`, `supersededBy`, `status`, but no
   `lastConfirmedAt`, `lastUsedAt`, `lastReviewedAt`, or a persisted *reason* for
   a decision. `retention_days` policy exists but is **never applied**; an
   automatic memory never becomes stale for review. `record_access` writes only
   `lastAccessedAt`.
4. **Export / import / backup / reset** — none. There is no export, import,
   backup, restore, or reset route/UI, and no `delete_memory` (archive is the
   terminal action).
5. **Backup / recovery** — no migration backup; `reconcile_legacy` and
   `import_legacy_skills` are the only copy-forward paths. No health check beyond
   `PRAGMA integrity_check`.
6. **UI explanations** — retrieval diagnostics explain *recall* exclusions, but a
   memory record does not persist *why it was saved/excluded*; the Memory Control
   Room has no expired/superseded/never-used/frequently-recalled/conflict views.
7. **Memory category rules** — memory types are enumerated but policy has no
   per-category capture/recall control; there is no "memory completely off"
   distinct from `memory_mode=off` (explicit requests still write), no
   suggestions-only key beyond `ask_before_saving`, and no "appears in
   diagnostics" / "semantic indexing allowed" controls.

## Explicit non-goals (preserved)

* No hosted accounts, no multi-tenant authorization; `userId`/`scopeId` stay
  local labels.
* Current financial facts must never become durable memory.
* Semantic similarity, if ever added, may only find candidates — never authorize
  access; scope/status/privacy filtering stays authoritative.
* Automatic skill promotion stays impossible.
