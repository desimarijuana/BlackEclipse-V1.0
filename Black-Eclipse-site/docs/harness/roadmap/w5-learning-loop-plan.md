---
title: W5 — Learning Loop Quality (Detailed Plan)
status: Implemented (core)
last-verified: 2026-11-12
owner: Agent runtime
parent: docs/harness/roadmap/hermes-inspired-improvement-plan.md
scope: core landed — see §13 for the live surface and deliberate gaps
---

# W5 — Learning Loop Quality

W5 closes the gap between "Eclipse can record a lesson" and "Eclipse can prove a
learned skill or memory is worth loading". Today the loop has a complete
candidate → draft → static-evaluate → promote path, but three pieces are dark:

1. **Skill evaluation is static.** `_run_cases` checks schema shape, never
   behaviour, so a learned skill can pass without ever executing.
2. **There is no curator.** The skill library only grows; consolidation is a
   manual report.
3. **Hybrid memory retrieval is unwired.** `eclipse_memory/hybrid.py` is
   explicitly not on the production path; `retrieve_memories` uses its own
   deterministic `_score`.

W5.4 (lesson feedback) is already substantially landed and is treated here as
**verify + harden**, not build from scratch.

**Duration:** 4–5 engineer-weeks.
**Flags:** `HARNESS_SKILL_EXEC_EVAL` (declared `on`, currently no consumer),
`HARNESS_SKILL_CURATOR` (declared `dry_run`, no consumer),
`HARNESS_MEMORY_HYBRID` (declared `off`, no consumer).
**Dependencies:** W0 flag discipline; the existing `evaluation/` graders and
`skills/runtime.py::execute_skill`; the existing startup maintenance hook.
**Rollback:** every slice is flag-off reversible; no slice deletes a skill,
memory, or evaluation row.

---

## 1. Goals

1. **Behaviour is the gate.** A learned skill cannot be enabled on schema shape
   alone; it must execute on real cases and pass graders.
2. **Provenance is checkable.** A promotion names the execution run ids that
   proved it, and those rows must exist.
3. **The library self-maintains without self-modifying silently.** A curator
   proposes duplicates/umbrella merges as inert drafts with diffs; an operator
   still promotes.
4. **Memory recall gets better without getting less safe.** Hybrid ranking may
   only reorder already-authorized, already-relevant memories; safety metrics
   (forbidden hits, scope leakage) must stay at zero.
5. **Zero-config keeps working.** No model/provider configured means execution
   eval is `needs_review` (honest), curator stays report-only, hybrid stays
   lexical. Nothing silently enables.

## 2. Non-goals

- No new daemon/thread. Curator and consolidation reuse the existing startup
  maintenance hook and the self-improvement cadence.
- No persistent vector index. Semantic scoring is an optional, bounded
  tie-break; BM25 is the default hybrid.
- No automatic deletion or automatic permission widening.
- No rewrite of `evaluation/runner.py` or the grader engine.
- No retroactive disabling of already-enabled built-in skills.

---

## 3. Current state (grounded)

| Area | Today | Evidence |
|---|---|---|
| W5 flags | Declared but no consumer reads them | `python/harness/config/flags.py:199-211` |
| Static eval | `evaluate_skill` has 10 dimensions; `_run_cases` only checks schema/shape; unknown kinds become `needs_review` | `skills/evaluation.py:243-376`, `:448-501` |
| Promotion gate | `promotion_gate` reads a stored status/dimensions; it cannot tell whether behaviour ran | `skills/evaluation.py:621-641` |
| Lifecycle | `request_promotion` falls back to the latest evaluation; `approve_promotion` re-runs `registry.validate` only | `skills/lifecycle.py:27-105` |
| Auto-enable | `_enable_skill` requires latest evaluation `status == passed`; it never checks run ids | `self_improvement/self_modification.py:333-389` |
| Draft/eval cadence | Boot drafts ready candidates then evaluates them statically | `skills/draft.py`, wired at `service.py:1132-1158` |
| `/learn` backend | `learn_from_source` + `POST /learning/from-source` exist; `skill-create` command already maps source workflows | `skills/learn.py:149-231`, `main.py:1044-1076`, `src/lib/harness/commands/command-registry.ts:515` |
| Curator | None. Deterministic maintenance exists: stale report, optional reversible archive, pinned exempt | `skills/maintenance.py`, `service.py:1114-1118` |
| Hybrid memory | `hybrid.py` says "NOT wired"; `retrieve_memories` ranks with `_score` | `eclipse_memory/hybrid.py:1-13`, `retrieval.py:89-159`, `:369-410` |
| Consolidation | Already runs on boot, `resolve_conflicts=False` | `service.py:1159-1171`, `eclipse_memory/consolidation.py:85-98` |
| Memory eval | Versioned labelled set with safety thresholds (forbidden hits = 0, scope leakage = 0, recall ≥ 0.9) | `eclipse_memory/eval/__init__.py:43-51`, `:171-280` |
| Lesson feedback | Injection event + matched injected/control cohort + lift + retirement ranking already exist | `graph_context.py:212-304`, `self_improvement/lesson_feedback.py`, `self_improvement/lessons.py` |

**Data model available:** `SkillExecution` (runId, status, output, evidence,
metrics), `SkillEvaluation` (status, dimensions), `SkillEvaluationCase` (kind,
input, expected), `SkillVersion` (status, evaluationStatus, evalFingerprint,
nonActivation*), `SkillReview`, `SkillEvent`, `SkillMaintenance`,
`MaintenanceLease`, `LearningCandidate`. All skill state is in
`eclipse-memory.db` via `EclipseMemoryStore`; `skills/store.py` is an alias.

---

## 4. Target design

### 4.1 W5.1 — Behavioural skill evaluation

**New module:** `python/harness/skills/execution_eval.py`.

```python
@dataclass(frozen=True)
class ExecutionCaseResult:
    caseId: str
    passed: bool
    runId: str
    scores: dict[str, float]        # grader name -> score
    failures: tuple[str, ...]
    unmeasured: tuple[str, ...]     # graders that could not measure

@dataclass(frozen=True)
class ExecutionEvalResult:
    ok: bool
    cases: int
    passed: int
    failed: int
    runIds: tuple[str, ...]
    graderScores: dict[str, float]  # aggregate (mean over measured cases)
    reason: str
    fingerprint: str

def evaluate_skill_execution(
    manifest, cases, *,
    runner, graders,
    min_cases: int = 3,
    min_pass_rate: float = 0.8,
    model_key: str | None = None,
) -> ExecutionEvalResult
```

**Pipeline (inside `evaluate_skill`):**

```
static dimensions (unchanged, fast)
  → if any mandatory fails: blocked, never run execution
  → if flag HARNESS_SKILL_EXEC_EVAL off: current behaviour, mark static-only
  → execution tier:
       cases = stored cases whose kind is execution-capable
       if len(cases) < min_cases: needs_review (never passed)
       for each case: invoke the skill, grade, persist a SkillExecution row
       if pass_rate < threshold: failed
  → promotion_gate requires BOTH a passed static record and a passed execution record
```

**Case kinds.** Keep the deterministic kinds (`schema`, `input_validation`,
`output_shape`, `output_validation`). Add:

- `execution` — a payload plus `graders: [{name, config}]`; the default grader
  set follows the manifest category (finance → financial/citation/honesty;
  research → research/citation/honesty; quality → tool/state/honesty).
- `tool_trace` — expected tools / forbidden tools / max tool calls; graded by
  `evaluation/graders/tool.py` over the run trajectory.
- `artifact` / `citation` / `financial` / `honesty` — aliases that select a
  grader explicitly; unknown kinds remain `needs_review`.

**Invocation.** Reuse the real skill runtime, not a second executor:

- Extend nothing in `execute_skill` except the invocation wrapper. It already
  supports `ExecutionMode = "evaluation"` (`skills/manifest.py:59`) and
  `validated`/`testing` are executable (`:65`).
- `prepare_evaluation_version` moves `draft → testing` through the existing
  `set_version_status`/`save_review` path. `testing` is inert (non-interactive
  only) and is the intended evaluation state.
- `RuntimeSkillInvoker` supplies `SkillExecutionRequest(executionMode="evaluation",
  modelSettings=<resolved eval model>, runId="skileval_<uuid>")` and returns the
  `SkillExecutionResult`.
- Offline default: the same `ScriptedAgentInvoker` seam the evaluation runner
  already installs, so tests are deterministic. Live is opt-in.
- A `SkillInvoker` protocol keeps the module testable with a fake runner.

**Grading.** Convert a `SkillExecutionResult` into the existing
`evaluation/graders.GradeContext`:

- `final_output` = result output;
- `tool_calls` = tool events read from the run (`store.list_events(run_id)`);
- `env_state` = parsed output (when present);
- `outcome` = execution status + error code.
Reuse graders as-is. A grader that cannot measure returns `unmeasured`; an
unmeasured mandatory grader cannot count as a pass.

**Persistence (additive migration).** Append a migration to
`eclipse_memory/schema.py` (`SCHEMA_VERSION + 1`, `ALTER TABLE` pattern from
migration 9):

- `SkillEvaluation.executionRunIds TEXT` — JSON array.
- `SkillEvaluation.executionScores TEXT` — JSON object.
- `SkillEvaluation.executionFingerprint TEXT`.
- Index `SkillEvaluation(skillId, version, executionFingerprint)`.

No new evaluation table: an execution result is an evaluation record, exactly
like the static one.

**Cache.** Reuse `evaluation_fingerprint(manifest, registry, version)` and add
the runner version + model key + resolved case digests. A cached hit returns the
same `ExecutionEvalResult` and does not append a row.

**Gate wiring.**

- `promotion_gate(record, *, require_execution=False, execution=None)`.
  When required: `execution.ok` must be true, `passed >= min_cases`, and every
  `runId` must exist in `SkillExecution` for that skill/version.
- `lifecycle.request_promotion` passes `require_execution=flag_on` and the
  stored execution fields. A static-only evaluation produces
  `blocked: "execution evaluation required"`.
- `self_modification._enable_skill` requires `evaluations[0].executionRunIds`
  non-empty and valid when the flag is on. TTL/caps/read-only checks stay.
- `skills/draft.evaluate_drafted_skills` and `evaluate_used_skills` call the
  combined evaluator so the boot path produces execution evidence too.

**Migration policy for existing skills.**

- Built-in enabled skills: untouched. The gate applies to **new promotions of
  learned/draft versions** and to self-modification auto-enable.
- Existing learned skills with only static evaluations: marked
  `needs_review` on next evaluation, never silently disabled. The self-mod
  auto-enable path skips them with `evaluation_not_passed` /
  `execution_required`.
- A skill with no execution cases: `needs_review`, never `passed` (already the
  documented rule in the parent plan).

**Tests.**

- `test_skill_execution_gate.py`: no cases → needs_review; below min cases →
  needs_review; below pass rate → failed; pass → ok; cached fingerprint.
- `test_skill_execution_runtime.py`: fake invoker; draft→testing; execution
  rows persisted; run ids linked.
- `test_skills_evaluation.py` (extend): static dimensions unchanged; combined
  status; flag off preserves old behaviour.
- `test_self_modification.py` (extend): auto-enable refuses a static-only pass;
  accepts a proven pass.
- `test_skill_lifecycle_e2e.py` (extend): promotion blocked/allowed end-to-end.
- `test_skill_execution_cost.py`: min cases, cheap model key, cache hit makes
  zero model calls.

---

### 4.2 W5.2 — Skill curator

**New module:** `python/harness/skills/curator.py`.

**Trigger (no new daemon).**

- On startup, after `run_skill_maintenance` (`service.py:1114-1118`).
- On the existing self-improvement cadence (`self_improvement.run_once`) at most
  once per `curator_interval_hours` (default 24) and only when no run is active.
- A `MaintenanceLease` row guards against two passes; a `SkillCuratorRun` row
  records every attempt. Best-effort: failure never blocks boot.

**Inputs (existing data only).**

- `registry.list_summaries()` for id/name/description/tags/category/status.
- `skills/maintenance.py::_usage_index` for last-used/run counts (no new ledger).
- `SkillVersion` content hashes and instructions.
- Manifest permissions, required tools, origin, tags (`compliance`, `pinned`).
- `SkillEvent`/`SkillReview` for recency and prior curator decisions.

**Deterministic pass (always).**

1. **Exact duplicates** — identical normalized `content_hash` or identical
   name+description token set → one group.
2. **Near duplicates** — Jaccard over normalized name+description+tags ≥ 0.7,
   same category, intersecting tool sets. Report the group and a suggested
   keeper (highest usage, then newest).
3. **Stale/archive suggestions** — reuse `assess_versions` output; report only.
4. **Evaluation debt** — enabled learned skills with no execution evaluation.
5. **Tag/category drift** — same `tags` set on > N skills, or a skill whose
   description duplicates another's.

**Optional LLM pass.**

- Only in `propose`/`apply` modes and only when a model is configured.
- Input is bounded discovery metadata + short descriptions; never raw chat,
  never secrets. The prompt asks for an umbrella name/description/procedure
  that **merges**, not invents.
- Output must be a schema-valid draft body; `content_scan` and
  `verdict_guard` run before persisting.
- The LLM never emits a status, permission, tool, or enable decision.

**Hard rules (enforced in code, not prose).**

- Never delete or overwrite an existing version.
- Skip any skill/version that is pinned, has a `compliance` tag, has
  `origin == "external"`, or is a project skill requiring trust.
- Never widen permissions or required tools; the proposed set must be a subset
  of the members' intersection.
- Preserve support files (`references/`, templates, fixtures): copy, never
  re-synthesize.
- A merge always lands as an **inert draft**; operator promotion goes through
  the existing lifecycle. `apply` mode may only auto-apply deterministic
  non-destructive actions (e.g. archive *suggestion* hand-off to maintenance),
  never a prose merge.
- Every proposal carries a before/after diff and a rollback note.

**Persistence (additive migration).**

```
SkillCuratorRun(
  id, startedAt, finishedAt, mode, status, error,
  skillsScanned, groupsFound, proposalsCreated, applied, details
)
SkillCuratorProposal(
  id, runId, kind, skillIds, baseVersion, proposedDraftId,
  diff, reason, status, createdAt, decidedAt, decidedBy, decisionNotes
)
```

`kind ∈ {duplicate, near_duplicate, umbrella_merge, stale, eval_debt, tag_drift}`.
`status ∈ {reported, proposed, approved, rejected, applied, rolled_back}`.
No new "apply" machinery: approval creates a draft version via
`skills/draft.py`; rollback uses `skills/lifecycle.rollback`.

**Mode mapping.** `HARNESS_SKILL_CURATOR`:

| Mode | Behaviour |
|---|---|
| `off` | no scan |
| `dry_run` (default) | scan + persist `SkillCuratorRun`; proposals `reported`; no drafts |
| `propose` | scan + create inert drafts for merge proposals; `proposed` |
| `apply` | `propose` + auto-apply deterministic archive hand-offs and tag cleanups; merges still operator-approved |

**Routes / UI.** Add `POST /skills/curator/run`, `GET /skills/curator/report`,
`POST /skills/curator/proposals/{id}/approve|reject`. Surface in Skills >
Maintenance with the diff and the rollback action. All operator-authorized;
existing `guardMutation` conventions.

**`/learn` ergonomics.**

- Backend, client, and REST already exist (`skills/learn.py`,
  `src/lib/harness/clients/skills-client.ts:201`,
  `src/app/api/learning/from-source/route.ts`).
- Add a thin chat `/learn <source>` command that calls the existing
  `createLearnDraft` path, or document `skill create --from-task` as the
  supported entry. It must:
  - be operator-gated;
  - show the inert draft + lint/sanitized warnings;
  - never auto-evaluate/enable beyond the existing inert pipeline;
  - link to the learning queue.
- Do not build a second authoring path.

**Tests.**

- `test_skill_curator.py`: dry-run changes nothing; proposal diff; approval
  creates a draft version; rollback re-points; pinned/compliance/external
  skipped; permission widening rejected; support files preserved; mode matrix.
- `test_skill_curator_idle.py`: lease prevents overlap; interval respected;
  startup failure is swallowed.
- `test_guided_learning.py` (extend): `/learn` command path stays inert.

---

### 4.3 W5.3 — Hybrid memory retrieval

**New module:** `python/harness/eclipse_memory/bm25.py`.

- Corpus-level BM25 (`k1=1.2`, `b=0.75`) with real IDF over the eligible
  candidate set, not the current single-document collapse.
- Pure functions: `tokenize(text)`, `build_index(docs)`, `score(query, index)`.
- Deterministic, no dependency, bounded by candidate count (already ≤ 200 per
  query in `retrieve_memories`).
- Move/duplicate the tested logic from `hybrid.py`; keep `hybrid.py` as the
  explainable scorer or fold it into `bm25.py` + `ranking.py`. One implementation.

**Retrieval wiring.** In `retrieve_memories` (`retrieval.py:248`):

1. Scope/status/privacy/expiry/confidence filters and the contradiction guard
   stay **exactly** where they are. They remain authoritative.
2. When `HARNESS_MEMORY_HYBRID` is off: current `_score` ordering, byte-for-byte
   identical output. This is the rollback.
3. When on: compute `lexical` from `_score` (unchanged reasons), `bm25` over the
   eligible set, plus `recency`, `authority`, `access` components. Order by:
   `hybrid = 1.0*lexical_norm + 0.5*bm25 + 0.3*recency + 0.4*authority + 0.15*access`.
4. **Relevance gate unchanged.** A memory with no lexical signal is still
   excluded unless it is a standing rule. BM25 is term-overlap and may
   *strengthen* a signal, never create relevance for an unrelated memory. Do not
   let a vector score admit a memory with no term overlap.
5. Optional semantic component: only when a provider is configured and the flag
   is on; bounded `0.35 * cosine`; it can only reorder memories that already
   passed the lexical/subject signal gate. No persistent index; compute over the
   candidate set or skip when the provider is unavailable. Fail closed.
6. `profile_id` isolation: add an optional `profile_id` argument and filter
   candidates by it before ranking (the profile module already exists).

**Diagnostics.** Extend `RetrievalDiagnostics.reasons` / the persisted
`selectionReasons` with the component breakdown per selected memory. This is how
an operator sees why a memory outranked another. Never omit an excluded reason.

**Consolidation.** Already runs on boot (`service.py:1159-1171`) with
`resolve_conflicts=False`. Add only a bounded "every N runs" trigger using the
same startup/self-improvement seam, with the existing lease. Never auto-resolve
contradictions.

**Measurement.**

- Thread the flag through `EclipseMemoryService.retrieve` so the labelled eval
  exercises the real path.
- Add hybrid cases to `eclipse_memory/eval/dataset_v1.json` or a `v2` dataset:
  multi-term queries where BM25 should lift the right memory, and negative
  cases where it must not.
- Acceptance is measured against the existing thresholds: `forbiddenHits = 0`,
  `scopeLeakage = 0`, `noMatchClean = true`, `overBudgetCases = 0`, recall not
  below the current baseline, and `recallSupported` improved or equal.
- Record before/after JSON in `docs/harness/baselines/`.

**Tests.**

- `test_memory_bm25.py`: IDF, empty query, punctuation, determinism, ties.
- `test_memory_hybrid_rank.py`: hybrid reorders; off == old order; semantic
  cannot admit a no-signal memory; forbidden/scope stays zero.
- `test_memory_retrieval_eval.py`: run both modes; assert thresholds; snapshot
  the report.
- `test_memory_profile_isolation.py`: profile filter cannot leak across.

---

### 4.4 W5.4 — Lesson feedback (verify + harden)

Already present:

- `prompt.lesson_injected` event (`event_system/registry.py:281`,
  `graph_context.py:288`).
- Matched injected/control cohorts, lift, `unmeasured` discipline
  (`self_improvement/lesson_feedback.py`).
- Adoption requires a completed validation run and a resolvable artifact
  (`self_improvement/lessons.py`).

Remaining work is small and optional for the first release:

1. Verify `lesson.injected → run.outcome` is written on every terminal run
   path (success, failure, cancel).
2. Add retirement: a lesson with negative lift after ≥ N measured uses moves to
   `retired` (reversible), with an event and a review row.
3. Confirm `automatic_selective` adoption stays operator-gated unless recurrence
   ≥ 3 **and** an offline eval improvement exists. Do not enable RSL by default.

Tests: `test_lesson_feedback.py` (adoption/injection/retirement), extend
`test_learning_loop_closure.py`.

---

## 5. Slices and acceptance

| Slice | Change | Acceptance |
|---|---|---|
| W5.1a | `execution_eval.py` + case kinds + fake-invoker tests | A skill with no execution cases is `needs_review`; a passing one is `ok` with persisted run ids |
| W5.1b | Combined evaluator in `evaluate_skill` + additive columns | Flag off == today; flag on adds `execution_eval` dimension |
| W5.1c | Promotion/enable gates require execution | `request_promotion` and `_enable_skill` refuse a static-only pass |
| W5.1d | Boot/draft path runs execution eval | Boot on a fixture produces execution evidence without enabling |
| W5.2a | Deterministic curator + tables + dry-run | Dry-run writes a run + proposals and changes no skill |
| W5.2b | Propose mode creates inert drafts + diff + rollback | Approval creates a draft version; old version intact |
| W5.2c | `apply` for deterministic actions only | No prose merge auto-applies; pinned/compliance untouched |
| W5.2d | `/learn` chat entry | Operator gets an inert draft with lint warnings |
| W5.3a | `bm25.py` + hybrid ranking behind flag | Flag off output identical; flag on deterministic and explainable |
| W5.3b | Optional semantic tie-break + profile isolation | No forbidden hit, no scope leak, no no-signal admission |
| W5.3c | Labelled eval + baseline | Safety thresholds zero; recall not regressed; `recallSupported` ≥ baseline |
| W5.4 | Feedback hardening | Retirement reversible; adoption remains validation-gated |

---

## 6. Sequencing

1. **W5.1a → W5.1b** (execution evidence exists).
2. **W5.1c** (gate wired; the loop is now honest).
3. **W5.3a → W5.3b → W5.3c** (independent of the skill work; safe to parallelize
   in a second worktree).
4. **W5.2a → W5.2b** (curator reads stable evaluation fields).
5. **W5.2c → W5.2d**.
6. **W5.4** verification last (it depends on stable run/outcome semantics).

W5.1 and W5.2 share `skills/`; W5.3 touches only `eclipse_memory/` and its eval.
Run them in parallel only with separate worktrees.

---

## 7. Test matrix

| Layer | Command | What must hold |
|---|---|---|
| Skill eval unit | `pytest python/tests/test_skill_execution_gate.py test_skill_execution_runtime.py test_skills_evaluation.py test_self_modification.py test_skill_lifecycle_e2e.py` | static + execution + gates |
| Curator | `pytest python/tests/test_skill_curator.py test_skill_curator_idle.py` | no silent change; approval/rollback |
| Memory | `pytest python/tests/test_memory_bm25.py test_memory_hybrid_rank.py test_memory_retrieval_eval.py test_memory_profile_isolation.py` | safety thresholds; off == old |
| Learn | `pytest python/tests/test_guided_learning.py test_learning_loop_closure.py` | inert draft; no auto-enable |
| Full gates | `npm run test`, `npx tsc --noEmit`, `node scripts/test-evals.js`, `npm run audit:agent` | no regression; flags kill-switch |

Add one kill-switch test per new flag in `python/tests/test_kill_switches.py`
(the W0 contract): flag off restores the pre-W5 path exactly.

---

## 8. Rollout

1. **W5.1 ships with `HARNESS_SKILL_EXEC_EVAL=on`** but only affects learned /
   draft promotions and self-mod auto-enable. Built-ins are untouched. Publish
   the "existing static-only learned skills are `needs_review`, not disabled"
   note before enabling.
2. **W5.2 ships `dry_run`. ** Run it for one release, review proposal quality,
   then `propose`. `apply` is an explicit operator choice and never merges prose.
3. **W5.3 ships `off`.** Turn on in the offline eval first, compare the labelled
   report, then enable in the dev profile. Keep `off` as the documented rollback.
4. **W5.4** remains default-on but operator-gated.

---

## 9. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Execution eval cost/latency | Boot slows, model spend | fingerprint cache; min cases; cheap eval model; cap per boot (`limit`); no live tier in zero-config |
| Execution eval flakes | A good skill never promotes | deterministic scripted tier first; retries only on transport; `unmeasured` ≠ fail |
| A draft never becomes executable | Cannot evaluate | `testing` is the explicit evaluation status; `ExecutionMode="evaluation"` already exists |
| Curator merges compliance prose | Regulatory/trust damage | frozen fields; compliance/pinned/external skip; subset permissions; operator approval; never delete |
| Curator duplicates the authoring path | Two sources of truth | reuse `skills/draft.py` + `authoring.py`; no second writer |
| Hybrid surfaces an unrelated memory | Context pollution | lexical/subject signal gate stays; semantic is a tie-break only; labelled negatives |
| BM25 changes recall silently | Hard-to-debug regressions | flag off is byte-identical; diagnostics carry component scores; baseline JSON |
| Memory poisoning via external data | Wrong facts become "memory" | hybrid only over the native store; external remains fenced; no promotion |
| Lesson overfitting | Bad advice persists | recurrence + validation run + measured lift; reversible retirement |

---

## 10. File map

**New**

- `python/harness/skills/execution_eval.py`
- `python/harness/skills/curator.py`
- `python/harness/eclipse_memory/bm25.py`
- `python/tests/test_skill_execution_gate.py`
- `python/tests/test_skill_execution_runtime.py`
- `python/tests/test_skill_curator.py`
- `python/tests/test_skill_curator_idle.py`
- `python/tests/test_memory_bm25.py`
- `python/tests/test_memory_hybrid_rank.py`
- `python/tests/test_memory_profile_isolation.py`

**Changed**

- `python/harness/skills/evaluation.py` — combined evaluator, gate signature.
- `python/harness/skills/lifecycle.py` — pass execution evidence.
- `python/harness/self_improvement/self_modification.py` — execution-required.
- `python/harness/skills/draft.py` — boot/draft path uses the combined evaluator.
- `python/harness/skills/maintenance.py` — expose the usage index/assessment to
  the curator (no duplicate derivation).
- `python/harness/eclipse_memory/retrieval.py` — hybrid branch, profile filter,
  diagnostics.
- `python/harness/eclipse_memory/hybrid.py` — one implementation, no "unwired"
  status; explainable components.
- `python/harness/eclipse_memory/schema.py` — one additive migration (evaluation
  columns + curator tables).
- `python/harness/eclipse_memory/service.py` — thread the hybrid flag.
- `python/harness/service.py` — curator hook + consolidation cadence.
- `python/harness/routers/skills.py` — curator routes.
- `python/harness/config/flags.py` — flag read helpers (no new flags).
- `src/lib/harness/clients/skills-client.ts` / `skills-browser.ts` — curator API.
- `src/lib/harness/commands/command-registry.ts` + handler — `/learn` entry.
- `src/components/screens/skills/**` — curator report/diff (if the surface exists).
- `python/harness/eclipse_memory/eval/**` — hybrid cases + report mode.

**No change**

- `evaluation/runner.py`, `evaluation/graders/**` — reused as-is.
- `skills/learn.py` — already the authoring entry.
- `eclipse_memory/consolidation.py` — already the consolidation engine.

---

## 11. Exit criteria

W5 is done when:

1. A learned skill cannot be enabled without a passed execution evaluation that
   names existing run ids (proven by a test).
2. A curator dry-run produces a report and proposals, and changes no skill
   (proven by a test and a committed sample report).
3. An approved curator merge creates a new inert version, preserves support
   files, and rolls back via the existing lifecycle (proven by a test).
4. Hybrid retrieval passes the labelled eval with `forbiddenHits = 0`,
   `scopeLeakage = 0`, `noMatchClean = true`, and recall not below baseline;
   flag off reproduces today's ordering exactly.
5. Every new flag has a kill-switch test and an entry in
   `docs/harness/roadmap/w0-flags-and-review.md`.
6. `npm run test`, `npx tsc --noEmit`, the offline eval gate and
   `npm run audit:agent` pass.
7. The changelog records each slice and the docs' `last-verified` moves only on
   the docs actually re-read.

---

## 12. Open decisions

1. **Where does execution eval get its model in zero-config?** Proposal: the
   existing resolved eval model; when absent, the skill stays `needs_review`
   (honest, never fabricated). Do not ship a fake model.
2. **Does execution eval block *bundled* promotion?** Proposal: no — only
   learned/draft/self-modification paths. A bundled skill is already trusted and
   enabled; forcing re-execution on upgrade would break zero-config.
3. **Is `apply` mode ever allowed to create a merged version?** Proposal: no for
   prose merges. It may hand archive suggestions to maintenance, which is already
   reversible and pinned-exempt.
4. **BM25 vs the existing `_score`.** Proposal: keep `_score` as the lexical
   signal and BM25 as an additive component, so the relevance gate and its
   explanations do not change meaning.
5. **Embeddings.** Proposal: no persistent index; compute per candidate set only
   when a provider is configured; otherwise skip. Revisit only if the labelled
   eval shows a measured gain that BM25 cannot reach.

---

## 13. Implementation status (2026-11-12)

### Landed

- **W5.1 — behavioural execution tier.**
  `python/harness/skills/execution_eval.py` adds `ExecutionEvalResult`,
  `ExecutionCaseResult`, a `SkillInvoker` protocol and the production
  `RuntimeSkillInvoker` (real `execute_skill` in `ExecutionMode="evaluation"`).
  `evaluate_skill(require_execution=..., execution_invoker=...)` runs the tier
  only for learned/author-origin skills (`execution_gate_applies`), persists
  `executionRunIds` / `executionScores` / `executionFingerprint`, and adds an
  `execution_eval` dimension. `promotion_gate(require_execution=True, store=...)`
  refuses an evaluation with no run ids or with ids that do not exist.
  `lifecycle.request_promotion`, `versioning.activate_version`,
  `self_modification._enable_skill`, the `/skills/{id}/evaluate` route and the
  boot draft/usage sweeps all pass the flag. Schema migration 36 (evaluation
  evidence + curator tables) and 37 (authored case spec) are additive.
  `skills/draft.py` now authors three execution cases for a learned draft.
  The production runner is opt-in via `ECLIPSE_SKILL_EVAL_MODEL=provider:model`
  (plus `ECLIPSE_SKILL_EVAL_API_KEY` / `ECLIPSE_SKILL_EVAL_BASE_URL`); without
  it the tier is an honest `needs_review`.
- **W5.2 — curator.** `python/harness/skills/curator.py` implements the
  deterministic scan (exact/near duplicates, evaluation debt, tag drift),
  protected-skill rules (pinned/compliance/external/quarantined), intersection
  permissions, support-file listing, a cadence guard and a process lock. Modes
  `off|dry_run|propose|apply` come from `HARNESS_SKILL_CURATOR`; it is hooked
  into startup maintenance and exposes `/skills/curator`,
  `/skills/curator/run`, and proposal approve/reject routes. Merge drafts are
  always inert (`status: draft`, `baseVersion` set); the active version is never
  edited.
- **W5.3 — hybrid memory retrieval.**
  `python/harness/eclipse_memory/bm25.py` provides corpus-level BM25 (real IDF,
  length normalization, normalized scores). `retrieve_memories` adds it behind
  `HARNESS_MEMORY_HYBRID` as a bounded `+3.0 * bm25` tie-break over the SAME
  eligible set; the lexical relevance gate, scope/status/privacy filters and the
  contradiction guard are unchanged. Diagnostics expose `hybrid` and
  `bm25ByMemory`. Flag off is the original ordering.
- **W5.4 — lesson feedback.** Verified: `retire_unhelpful` and the matched
  injected/control lift already exist and are tested in
  `test_lesson_feedback.py`.
- **`/learn`.** Added as an alias of the existing `skill-create` command; it
  reuses the existing inert-draft backend (`skills/learn.py`,
  `POST /learning/from-source`).
- **Tests added:** `test_skill_execution_gate.py`, `test_skill_curator.py`,
  `test_memory_bm25.py`, `test_memory_hybrid_rank.py`; legacy
  `test_self_modification.py` now explicitly turns the execution gate off
  because it tests TTL/audit, not W5.

### Deliberate gaps (do not report these as landed)

- **No semantic/embedding component.** W5.3 is BM25 + the existing lexical
  score. A semantic tie-break remains future work and is not needed to pass the
  labelled eval.
- **No LLM curator pass.** The deterministic scan and merge-draft assembly are
  implemented; an optional LLM umbrella writer is not. The merge is faithful
  concatenation, never invented prose.
- **No automatic archive in `apply` mode.** Curator `apply` creates proposals
  and inert drafts; archive suggestions are handed to the existing maintenance
  pass, which remains report-only unless its own policy enables it.
- **Execution eval needs a configured eval model.** That is intentional: with no
  model, a learned skill stays `needs_review` and cannot enable. The
  zero-config app still boots and serves; it just does not fabricate a pass.
- **Per-profile memory isolation** is unchanged: profiles already use separate
  namespaces/databases, so retrieval does not add a redundant `profile_id`
  filter.
