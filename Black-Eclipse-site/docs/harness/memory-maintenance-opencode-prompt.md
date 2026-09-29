# OpenCode Prompt — Eclipse-Memory & Skills Maintenance Hardening

You are continuing work in the BlackEclipse repository. Implement **memory and
skills maintenance hardening** in the existing Python agentic runtime. The goal
is to close the capabilities Eclipse-Memory and the skill system are missing
relative to where they should be, and to remove one subsystem that costs more
than it returns.

Do not stop after proposing a plan. Audit first, then implement the milestones
below in small, reviewable steps, update progress docs as you go, run required
checks after each coherent change, and finish with a concise report of files,
behavior, checks, and limitations.

This is **maintenance, safety and subtraction work**. It is explicitly *not* a
rewrite of the memory architecture, and it adds no new storage engine, no
embeddings, no network dependency and no TypeScript agent runtime.

## Product and architecture context

- The agentic runtime is **Python** under `Black-Eclipse-site/python/harness/`
  (FastAPI + LangChain + LangGraph). Agents, tools, prompts, retrieval,
  persistence, and events are Python-authoritative. Next.js is a thin front
  door/proxy; do not implement agent decisions, memory policy, or maintenance
  logic in TypeScript.
- Eclipse-Memory is **one** SQLite database (`eclipse-memory.db`) owned solely
  by `python/harness/eclipse_memory/`. One `EclipseMemoryService`, one decision
  gate (`eclipse_memory/decision.py`), one retrieval seam
  (`eclipse_memory/retrieval.py`), one skill execution path
  (`skills/runtime.execute_skill`).
- Session history lives in `agent-memory.db` (`SessionMessage`), is redacted and
  bounded, is searched on demand, and is never injected every turn.
- Skills live in `eclipse-memory.db` as immutable versions with file-backed
  bundled definitions under `python/harness/skills/library/`.
- Reuse existing services, contracts, guards, UI components and bridge routes.
  Do not create a second memory engine, a second skill registry, a second
  scheduler, or a second maintenance daemon.

## Non-negotiable repository rules

1. Read root `AGENTS.md`, `docs/NAVIGATION.md`, `docs/harness/architecture.md`,
   `docs/harness/phase-3-memory-progress.md`,
   `docs/harness/memory-skills-evolution-plan.md`, `docs/DECISIONS.md`, and
   applicable skills under `Black-Eclipse-site/skills/` before edits.
2. Inspect `git status` and `git diff` first. Preserve unrelated user changes;
   never revert or overwrite them. Do not commit, push, or open a PR.
3. Read code before changing it. Keep files small; do not re-bloat large files
   (memory is the top constraint on this machine).
4. Never fabricate financial data, facts, citations, source authority, or
   confidence. Unknown metadata stays unknown.
5. No automatic skill promotion, no autonomous policy changes, and no autonomy
   over durable-memory writes. The decision gate stays the single authorization
   seam for every durable-memory write.
6. Append a dated entry to `docs/CHANGELOG.md` for every change, ending with
   `docs updated: <file(s)>` or `no doc change — <reason>`. Update owning docs
   when architecture, contracts, setup/operations, major modules, or decisions
   change; bump `last-verified` only on docs actually re-read against the code.
7. After each change, from `Black-Eclipse-site/`, run `npm run test` **and**
   `npx tsc --noEmit`. Also run the relevant Python suites and the memory eval
   gates (`python -m harness.eclipse_memory.eval`, `...eval.contradictions_cli`).
   Report failures honestly; never mask an unrelated baseline failure.

## Objective

Eclipse-Memory is strong at *capture correctness* and *governance*: typed and
scoped records, one authorization gate, deterministic contradiction handling,
retention with an authority rule, immutable evaluated skill versions.

It is weak at exactly four things:

1. **Maintenance** — nothing ever retires, ages out, or notices an unused skill.
2. **Pre-compression capture** — context is bounded, but nothing is extracted on
   the way through.
3. **Surface honesty** — a disabled store can still be advertised to the model.
4. **Measurement honesty** — self-authored labeled sets report perfect scores,
   which is a smell rather than evidence.

Close those, and remove one subsystem that measures as valueless.

## Milestone 0 — Audit before changing anything

Inspect at minimum:

- `python/harness/eclipse_memory/{service,decision,policy,retrieval,profile,compaction,skill_quality,store,schema}.py`
- `python/harness/{graph,service,agents,prompts,tools,memory_tools,session_index,learning_graph,learning_review}.py`
- `python/harness/skills/{registry,lifecycle,versioning,patches,evaluation,manifest,runtime,store}.py`
- `python/harness/memory_providers/*`
- `src/lib/harness/memory-files.ts`, `src/lib/harness/eclipse-memory-*.ts`
- `src/components/screens/eclipse-memory/*`, `src/components/screens/skills/*`
- `src/app/api/eclipse-memory/**`, `python/harness/routers/*`
- Existing tests under `python/tests/` and `src/**/*.test.ts`

Record current behavior, integration points and baseline results in
`docs/harness/memory-maintenance-progress.md` (create it). **Source code is
authoritative where this prompt disagrees with it.**

### Findings already established from reading the current tree

Treat these as verified starting points, but **re-confirm each against the exact
current code before acting** — the tree may have moved since this prompt was
written. If a finding is already fixed, preserve that fix and add regression
coverage instead of re-applying it.

| # | Finding | Evidence |
|---|---|---|
| A1 | `register_memory_tools(self.registry)` is called unconditionally in `AgenticService.__init__` (`python/harness/service.py`, ~line 79), and `"memory"` is an unconditional entry in `ECLIPSE_AGENT.tools` (`python/harness/agents.py`). The `memory_enabled` policy appears to have no effect on the tool schema or the prompt guidance block, so the model can be told about a tool whose store is off. | verified by reading `service.py`, `agents.py`, `memory_tools.py` |
| A2 | Context is **truncated, not compacted**, and silently. `graph.py` `_history_messages` keeps `history[-MAX_HISTORY_TURNS:]` (`MAX_HISTORY_TURNS = 20`, ~line 830) and then drops oldest turns while the running char total exceeds `MAX_HISTORY_CHARS = 40_000` (~lines 831, 843). No summary is produced and nothing is signalled to the model or the user. A grep for `compress`/`summariz`/`summary_of` across `graph.py`/`service.py` returns nothing. The bound is 40 lines above the function this prompt already names — it is **not** inside a dependency. | verified by reading `graph.py` |
| A3 | Nothing performs skill staleness or usage-based maintenance. A grep for `curator`, `stale_after`, `archive_after`, `skill_usage`, `usage_count` across `python/harness/` returns **zero** hits. Skills are versioned and evaluated but never aged, and `SkillExecution` rows are recorded without feeding any retirement decision. | verified by grep |
| A4 | `src/lib/harness/memory-files.ts` has `atomicWriteFile` (temp + fsync + rename), `backupMemoryFiles`, `restoreMemoryFiles`, and an `expectedVersion` stale-edit rejection — but **no** BOM handling, no refuse-to-write-an-unreadable-file guard, and no external-drift detection. Each of those is a real data-loss class on a file the user can hand-edit. | verified by reading the module |
| A5 | The compact prompt profile **already** materializes exactly once at run start (`graph.py` `_profile_context`, ~line 529–534) and a mid-run save appears only in later runs. This is **correct and must not be changed**; do not "fix" it into a live reload. | verified |
| A6 | There is no trivial-prompt gate. The only related behavior is `decision.py` returning an ignore for a bare greeting. Every trivial turn still walks the full decision path. | verified |
| A7 | An optional semantic candidate layer exists (`eclipse_memory/semantic.py`, ~433 LOC) with its own policy keys, typed candidates, tie-break and rebuild route, off by default. Its own documentation concludes it "adds no measurable recall at a safe threshold," and that deterministic normalization closed the entire measured gap. | verified by reading the module and `docs/harness/memory-contradiction-detection.md` |
| A8 | **Prompt caching is not at risk from this work** — do not let that instinct block Milestone 2. `graph.py` (~lines 573–580) rebuilds `profile_block`, `skill_manifest` and `memory_block` as **per-run** SystemMessages on every run, so the cross-run prefix was never byte-stable. `prompt_segments.build_prompt_plan` computes an identity-only `prompt_cache_key` (agent id + tool names) that the user message does not invalidate. Only the `SystemMessage(agent.systemPrompt)` head plus the tool schema are byte-stable, and those must stay untouched. | verified by reading `graph.py` + `prompt_segments.py` |
| A9 | **No skill pin flag exists.** `SkillVersion` carries `id`, `skillId`, `version`, `manifest`, `contentHash`, `status`, `evaluationStatus`, `riskLevel`, `author`, `origin`, `createdAt`, `updatedAt`, `publishedAt`, `deprecatedAt` — and no pin/lock column. Milestone 1 therefore needs new persisted state and an additive migration; "add or reuse a pin mechanism" resolves to *add*. | verified by reading `eclipse_memory/schema.py` |
| A10 | The user's **full** prior conversation arrives every turn as `request.input.history` (`schemas.py` `RunInput.history`), supplied by the chat client (`src/components/screens/stock-chat.tsx`, ~line 548), which sends every prior turn. The turns Python drops at the history bound are therefore **not destroyed** — they persist client-side. Extraction can read exactly the window being dropped. | verified by reading `schemas.py` + `stock-chat.tsx` |

## Milestone 1 — Skill maintenance: staleness, usage, retirement

**Why.** Every skill Eclipse creates is permanent. There is lifecycle governance
(state machine, patch, canary, rollback) but no *maintenance*: no aging, no
usage signal feeding a decision, no retirement path, no exemption for pinned
skills. A library that only grows becomes noise in the skill manifest and
dilutes progressive disclosure.

**Requirements.**

1. Add `python/harness/skills/maintenance.py` (new module — do not append to
   `lifecycle.py` or `registry.py`). Implement a deterministic maintenance pass
   that derives staleness from **existing persisted data only**:
   `SkillExecution` rows, version history, `SkillEvaluation`, and skill
   `updatedAt`/activation timestamps. State the exact derivation in the module
   docstring; do not invent new tracking tables if existing rows suffice.
2. Add policy keys (validated, bounded, safe defaults, **off or
   report-only by default** — see rule 5 below): a staleness threshold, an
   archive threshold, and a maintenance-enabled flag. Mirror the existing policy
   key conventions in `eclipse_memory/policy.py`.
3. **Pinned skills are exempt from every automatic transition.** Finding A9: no
   pin column exists today, so this is *add*, not *reuse*. Add a `pinned` flag
   on `SkillVersion` (preferred — it is per-version state) or a small dedicated
   table, via an additive migration. A pinned skill must never be transitioned by
   any automatic path, pinning must survive a reopen, and the maintenance pass
   must not be able to bypass it. Do not reuse `status` to mean pinned — pinning
   is orthogonal to the lifecycle state machine.
4. **Archive, never delete.** A retired skill must remain restorable through the
   existing lifecycle/version machinery. Confirm the restore path works and is
   covered by a test.
5. **The default must be report-only.** The first delivery of this milestone
   computes and surfaces recommendations; it does **not** auto-transition
   anything unless the operator explicitly enables the corresponding policy key.
   This preserves the existing operator-gated lifecycle contract.
6. Trigger **without a new daemon or background thread**: run the pass at
   runtime startup through the existing FastAPI lifespan, exactly as
   `run_retention_maintenance` already does (`main._lifespan` →
   `AgenticService.run_startup_maintenance`). It must never block boot, must
   never raise, and must record its outcome observably (mirror the
   `MemoryMaintenance` pattern: operation, ranAt, ok, inspected, changed, error).
   It must be idempotent.
7. Expose the result: a read route (e.g. `GET /skills/maintenance`), an
   operator-gated run route, and a surface in the Skills UI showing stale skills,
   reasons, and recommended actions.
8. Add the migration for the pin flag (required by requirement 3, per A9) and
   for the maintenance ledger if you introduce one. Migrations are **additive and
   idempotent**; a pre-migration database must open with no data loss, covered by
   a reopen test — including that a *pinned* row's pin survives the reopen.

**Tests** (`python/tests/test_skill_maintenance.py`): staleness derivation from
real execution rows; pinned skills never transitioned; **the pin flag survives a
reopen (it is new persisted state, per A9)**; pinning is orthogonal to `status`
(a pinned `stale` skill stays `stale` and unpinned); archive is reversible;
idempotent re-run; report-only default changes nothing; the pass never raises and
never blocks boot; migration reopen preserves rows; scope isolation holds.

## Milestone 2 — Pre-compression capture

**Why.** When conversation context is compacted, everything not carried forward
is lost. If the transcript contained a durable preference, a correction, a
recurring workflow, or a mistake worth learning from, there is currently no
moment at which the runtime asks for it. Eclipse bounds context without
extracting from it: `_history_messages` silently drops turns past
`MAX_HISTORY_TURNS = 20` / `MAX_HISTORY_CHARS = 40_000` (finding A2).

### The seam — already located, do not hunt for it

| Fact | Where |
|---|---|
| The bound and the drop | `python/harness/graph.py` `_history_messages` (~lines 834–851); constants at ~830–831 |
| The exact window being dropped | `history[:-MAX_HISTORY_TURNS]` plus, for the char cap, the turns `_history_messages` peels off the front before returning |
| Where the full transcript comes from | `RunRequest.input.history` (`schemas.py` `RunInput.history`), supplied by the chat client every turn (`src/components/screens/stock-chat.tsx` ~line 548) — finding A10 |
| Where the run's messages are assembled | `graph.py` ~lines 573–580 |

Context management is **owned by this repository** in `graph.py`. It is *not*
inside LangGraph, the model adapter, or a dependency. Do **not** spend an audit
pass looking for another seam, and **do not** add a generic hook for a mechanism
that does not exist.

### Caching — settled, do not re-litigate

Finding A8 establishes that this work does **not** threaten prompt caching:
`profile_block`, `skill_manifest` and `memory_block` are already rebuilt per run
as their own SystemMessages, and `prompt_cache_key` is identity-only. There is no
byte-stable cross-run prefix to preserve. Two constraints still hold:

- The `SystemMessage(agent.systemPrompt)` head and the tool schema must stay
  untouched and byte-stable within a run.
- The extracted summary must ride the **same per-run message slot** the other
  per-run blocks already use (a SystemMessage after the history, before the user
  turn). It must **not** be added to `agent.systemPrompt` and must **not** be
  retro-fitted into an earlier turn.

### Requirements

1. Add an explicit pre-compression extraction seam at the `_history_messages`
   call in `graph.py`. It reads the window that is about to be dropped and
   produces a bounded, clearly labelled context block. Name it for what it is
   (dropped-context extraction), not "compaction" — `eclipse_memory/compaction.py`
   already means something else (near-duplicate memory proposals) and the two
   must not be confused.
2. The extraction must be **deterministic first**. Before reaching for a model,
   run the existing deterministic machinery over the dropped window:
   `decision.decide_turn` / `authorize_proposal`, `intent.py`, `mistakes.py`, and
   the learning analyzer. Reuse them.
3. Any output is **inert**: candidates, suggestions, or proposed records only.
   Never a direct durable write, never a skill activation. The decision gate
   remains the only authorization path.
4. **Fail closed — never emit a lossy summary.** If a required extraction
   cannot be completed, the caller keeps today's behaviour: the turns are still
   dropped from the prompt (that bound is the pre-existing, deliberate
   behaviour), but the run must **not** proceed on a summary that claims to
   represent them. Prefer: emit no summary block at all, carry on, and emit an
   honest event. The turns remain recoverable client-side (finding A10), so
   nothing is destroyed by doing this. Model the posture on the fail-closed
   checkpoint contract: a provider that cannot durably checkpoint makes the
   *caller* refuse the lossy path rather than continue silently.
5. Extraction failures never block or fail the run. Record them honestly.
6. Bound everything: a max extraction size, a timeout, and a cap on items
   produced. An oversized or pathological transcript must degrade, not hang. The
   extraction cost must be bounded independently of the 40 000-char budget.
7. Privacy rules apply with full force: secrets, credentials, sensitive
   identifiers, raw dumps and current financial facts are refused for this path
   exactly as for every other path.
8. The summary block is **data, not instructions**: label it as
   non-authoritative recalled context, sanitize it so it cannot escape its fenced
   block, and never let it authorize anything. It is never financial evidence.
9. A run whose history is under the bound must produce **no** summary block and
   must not change behaviour at all — the common short-conversation path stays
   byte-identical to today.

**Tests**: extraction produces inert candidates only; nothing is enabled;
fail-closed emits no lossy summary and does not fail the run; secrets/financial
facts refused; bounded size and timeout; a failure does not fail the run;
determinism (same transcript → same result); a short history produces no block
and is byte-identical to the pre-change behaviour; the system-prompt head and
tool schema are unchanged within a run.

## Milestone 3 — File-projection data-loss guards

**Why.** `.black-eclipse/memory/*.md` is an inspectable Markdown projection the
user can hand-edit, and a shell script or another tool can append to. The
projection already writes atomically and versions entries, but three known
data-loss classes are unguarded.

**Requirements.** Implement in `src/lib/harness/memory-files.ts` (and its
Python-side counterpart if one exists — audit first).

1. **Refuse to write an existing-but-unreadable file.** Treating an unreadable
   file as empty and then saving silently wipes it. The write must be refused
   with a truthful error; nothing is changed.
2. **Detect external drift.** If the on-disk content would not round-trip
   through the projection's own parser (a hand edit, a shell append, a foreign
   tool), refuse the flush, snapshot the raw bytes to a timestamped `.bak`, and
   return a remediation instruction. Never discard content the projection did
   not write.
3. **BOM handling.** Strip a leading UTF-8 BOM on read (Notepad and some editors
   add one on Windows) so it does not glue itself to the first entry and
   permanently corrupt matching, dedup and version identity for that entry. Keep
   decoding strict otherwise — a lossy decode followed by a save persists the
   loss.
4. **Do not let a consolidation batch empty a previously non-empty file.** A
   batch that removes the last entry must be rejected; a deliberate single
   removal is the only wipe path.
5. Preserve the existing `expectedVersion` stale-edit rejection and backup
   behavior. Do not regress them.

**Tests** (`src/lib/harness/memory-files.test.ts` additions): unreadable file
refused and untouched; drift refused with a `.bak` containing the raw bytes;
BOM-prefixed file round-trips and dedups correctly; batch cannot empty a
non-empty store; single removal still works; strict decoding still refuses
undecodable bytes.

## Milestone 4 — Surface honesty when memory is disabled

**Why.** Finding A1. The model must never be told about a tool it cannot use,
and must never be given guidance for a store that is off.

**Requirements.** Finding A1 gives the exact call sites. Confirm the current
behavior first, then fix it at the source.

- Tool surface: `register_memory_tools(self.registry)` in
  `AgenticService.__init__` (`python/harness/service.py`, ~line 79). Registration
  is currently unconditional.
- Agent tool list: `"memory"` is an unconditional entry in `ECLIPSE_AGENT.tools`
  (`python/harness/agents.py`).
- Prompt guidance: the memory guidance block in `python/harness/prompts.py`.

1. Confirm the actual current behavior before changing anything: does
   `memory_enabled=false` (or the equivalent hard-off policy, e.g.
   `memory_mode=off`) remove the `memory` tool from the schema the model
   receives, and remove the memory guidance from the system prompt?
2. If it does not: make the tool surface and the prompt guidance derive from
   policy. When the store is off, the tool is dropped and its guidance block is
   dropped. When only part of the surface is on, advertise only the part that
   works — mirror the existing pattern where a partially-enabled store narrows
   the advertised surface rather than advertising everything.
3. **Resolve the policy per run, not at import time.** `AgenticService` is
   constructed once; an import-time or `__init__`-time decision would freeze the
   first policy read for the process lifetime and would also be wrong under
   multiple profiles. The surface must be computed where the run's settings are
   already being read (`graph.py`), exactly as `session_history_enabled` and
   `session_indexing_enabled` are already read there. There is a working example
   in the tree — follow it rather than inventing a second mechanism.
4. **Do not break prompt caching.** The `SystemMessage(agent.systemPrompt)` head
   must remain byte-stable for the life of a run; a policy change takes effect on
   the next run. This matches the existing convention that mutating
   slash-style state is deferred by default.
5. The same honesty rule applies to the other memory-adjacent tools:
   `session_search`/`session_open` must not be advertised when
   `session_history_enabled` is off, and `memory_search_external` must not be
   advertised when external search is disabled by policy. Audit all of them, not
   just `memory`.

**Tests**: with the store off, the tool is absent from the resolved schema and
the prompt carries no memory guidance; with it on, both are present; partial
enablement advertises only the working surface; the prompt stays byte-stable
within a run; a policy flip takes effect on the next run and not mid-run.

## Milestone 5 — Trivial-prompt gate

**Why.** Finding A6. Every "hi", "ok", "thanks" or slash command walks the full
decision path. It is wasted work on the hot path, and stale context can
occasionally attach itself to a one-word reply.

**Requirements.**

1. Add a small, pure, well-tested predicate (e.g.
   `eclipse_memory/is_trivial.py` or an addition beside the existing intent
   classifier) that returns true for: empty input, slash commands, and bare
   greetings/acknowledgements — anchored so real content does not match (`hi`
   matches, `history` does not; `ok` matches, `okx` does not).
2. Use it to skip the memory decision and retrieval path for a trivial turn.
   Do **not** use it to skip an explicit `remember`/`forget`/`correct` — those
   remain handled by the always-on explicit-intent path.
3. It must not change any stored state and must not affect the user's reply.

**Tests**: the table of matching and non-matching inputs, both directions,
including near-miss tokens; an explicit remember still works on a turn whose
text is otherwise trivial; no state is written for a skipped turn.

## Milestone 6 — Retire the semantic candidate layer

**Why.** Finding A7. The layer is off by default and its own documentation
concludes it delivers no measurable benefit at a safe threshold: the
dependency-free backend scores genuine paraphrases at roughly 0.0–0.38, and the
deterministic normalization work closed the entire measured gap. It carries
~433 LOC, seven policy keys, typed candidate machinery, a retrieval tie-break,
a rebuild route, its own eval set and a UI surface, all in service of a feature
that is deliberately never enabled. That is review surface and refactor cost for
no return.

**Requirements.**

1. **Delete, do not disable.** Remove `eclipse_memory/semantic.py` and its policy
   keys, the service-side candidate plumbing, the tie-break, the rebuild route,
   the TS types/client methods, and the UI controls. Preserve the deterministic
   lexical + normalization path fully — that is the part that actually works.
2. **Keep the labeled evaluation harness** for the contradiction detector; it is
   the evidence that justifies the deletion and should stay runnable. Only the
   *semantic-backend* eval goes.
3. Keep the semantic eval fixture (`semantic_v1.json`) and its cases if they can
   be repurposed as **lexical regression cases** — those value-substitution and
   paraphrase cases guard a real, previously-shipped safety bug. Fold them into
   the deterministic contradiction set rather than deleting them.
4. If any persisted column, policy row or export field exists purely for the
   semantic layer, remove it **additively**: a pre-change database must still
   open, and the export/import schema must negotiate the removal (a v3 document
   must still import into the new shape, and a new document must not fail to
   import into an older reader in a way that loses data). Verify the actual
   version negotiation before deciding.
5. Update `docs/harness/memory-contradiction-detection.md` and the
   contradiction eval's honest-conclusion section to state that the layer was
   removed on the evidence, not merely left off. Mark the affected docs rather
   than leaving them describing a module that no longer exists.

**Tests**: the deterministic contradiction gate still passes at its recorded
metrics (recall 1.000, false-conflict 0.000, unauthorized supersessions 0); the
repurposed value-substitution cases still pass; no dangling reference to a
removed symbol or policy key remains (the test suite plus `tsc` will catch most
of this — fix every one, do not suppress).

## Milestone 7 — Measurement honesty

**Why.** The contradiction and compaction evaluations report perfect scores
(1.000 recall, 0.000 false-conflict, 1.000 confirmation accuracy) on
self-authored labeled sets. A perfect score on a self-authored set is a smell,
not evidence: it means the set was authored by the same reasoning that produced
the detector, so it cannot fail in a way the author did not anticipate.

**Requirements.**

1. Add a **real-usage measurement**, not another synthetic set: a bounded,
   read-only report over actual persisted rows that counts, over a stated
   window:
   - how many durable writes were saved / suggested / history-only / ignored
     (and the explicit-request rate),
   - how many candidate conflicts the detector raised, how many were accepted,
     dismissed, or left pending, and how many were false positives as judged by
     the operator's actual resolution,
   - how many conflicts were likely **missed** — two active same-scope,
     same-type records on the same dimension that did not conflict, which a
     human can review.
   This is derived data, read-only, bounded, content-free where it can be, and
   must never expose memory text wholesale.
2. State the honest interpretation in the doc: a synthetic set proves the
   detector implements its rules; it does not prove the rules match reality.
   Real-usage numbers are the evidence, and early numbers will be small and
   should be reported as such.
3. Re-run all existing gates after the deletion in Milestone 6 and record
   before/after numbers in the progress doc. If a metric moves, explain why.

**Tests**: the report is read-only and writes nothing; it is bounded and
idempotent; it never emits raw memory content; empty data yields an honest empty
report rather than a zero-filled fake.

## Checks

From `Black-Eclipse-site/`:

```bash
npx tsc --noEmit
npm run test                       # vitest + python
python -m harness.eclipse_memory.eval
python -m harness.eclipse_memory.eval.contradictions_cli
python -m pytest python/harness -q  # or the project's documented invocation
```

Report exact pass counts and every gate result. If a failure is pre-existing and
unrelated to this work, say so explicitly with the evidence — never silently
exclude it.

Confirm `jdds.db` is untouched by this work.

## Final report

Report:

- Per milestone: what changed, the files touched, and the evidence it works.
- The deletion list for Milestone 6, and confirmation that no dangling
  reference remains.
- Before/after eval numbers for every gate, with gates that had to be updated
  called out.
- Every honest limitation: anything you could not implement, anything where the
  real seam did not exist, anything you had to approximate, and anything you
  measured as small or inconclusive.
- Confirmation that every safety invariant still holds: one decision gate, one
  memory store, one skill execution path, default-deny permissions, operator
  transport/token auth, scope isolation, inert proposals/drafts/bundles/trust,
  no automatic promotion, no fabricated facts.
- `docs updated: <file(s)>` / `no doc change — <reason>` for each change.

## Explicit non-goals

- No embeddings, no vector store, no network call added at runtime.
- No second memory engine, second skill registry, second scheduler, or new
  daemon/thread.
- No auto-compaction of durable memory that is not inert-until-accepted.
- No TypeScript agent runtime, memory policy, or maintenance logic.
- No multi-user auth or tenancy work.
- No new dependency.
- No auto-promotion of any skill, and no relaxation of any existing operator
  gate.
