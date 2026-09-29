---
title: Change Log
status: Current
last-verified: 2026-09-28
---

# Change Log

## 2026-09-29

- **Tighten the landing composer's bottom gap.** `pb-6 md:pb-10`→`pb-2` on the
  empty-state wrapper. `src/components/chat/empty-state.tsx`. `tsc` clean;
  vitest 1837 pass. no doc change — visual only.
- **Slim down the chat composer.** The input bar read as oversized: textarea
  `text-base sm:text-lg`→`text-sm`, padding `py-3`→`py-2`; all round buttons
  `h-10/h-9`→`h-8`, icons 20/18→17/16; provider pill `h-8`→`h-7` and `text-sm`→
  `text-xs`; container padding `py-1.5`→`py-1`, `px-2 sm:px-4`→`px-1.5 sm:px-3`;
  `MAX_HEIGHT` 176→120 so the draft grows to ~4 lines before scrolling.
  `src/components/chat/chat-input.tsx`. `tsc` clean; vitest 1837 pass.
  no doc change — visual only.
- **Chat background is landing-only; composer pinned to bottom.** The eclipse
  artwork now paints the whole page (header + rail included) only while the chat
  thread is empty, and the app shell drops its `glass-card` on the chat tab so the
  transparent header shows it. As soon as a message exists the artwork unmounts and
  the surface falls back to solid/glass so the transcript stays legible. The
  landing composer is pinned to the bottom of the viewport. Background uses
  `bg-cover bg-center bg-no-repeat` (removed `bg-fixed` so it centers on the
  visible frame, not an oversized fixed canvas).
  `src/components/screens/stock-chat.tsx`, `src/components/chat/empty-state.tsx`.
  `tsc` clean; vitest 1837 pass. no doc change — visual/layout only.
- **Chat landing is composer-only, full width, on the eclipse background.**
  Removed the empty-state hero (wand icon, heading, description), the four
  suggestion tiles, and the "View Market Overview" button — the landing now shows
  only `ChatInput`, widened to `max-w-[1400px]`. The running-conversation composer
  uses the same width. The chat tab container paints
  `/backgrounds/eclipse bg.svg` (cover, centered, fixed). Landing is the first
  step of stripping the page's AI-generated look; transcript/history still render
  once a conversation starts.
  `src/components/chat/empty-state.tsx`, `src/components/screens/stock-chat.tsx`.
  `tsc` clean; vitest 1837 pass. no doc change — visual/layout only, no contract
  or data-shape change.
- **Chat message navigation rail.** A thin index on the right edge of the chat
  transcript, one tick per user turn. Clicking a tick scrolls that turn to the
  top, the tick nearest the reading position is highlighted, and hovering shows a
  short glassy preview popup. Ticks are hairline (`h-px w-3`) at rest and expand
  to a small pill (`h-[3px] w-5`) on hover/active. Shown only with 2+ user turns,
  on `md+`; scroll measurement is rAF-throttled and reads the already-rendered
  rows (`data-message-id`), so it is a pure view with no conversation state. New
  `src/components/chat/message-rail.tsx`; rows tagged in
  `src/components/chat/chat-history.tsx`. Checks: `tsc` clean; vitest 1837 pass.
  no doc change — UI presentation only, no contract or data-shape change.
- **Fix flat frosted glass in chat provenance surfaces.** The `Latest` jump
  button and the message-rail hover preview were rendering as solid fills, not
  frost. Two causes: (1) `glass-card-strong`'s near-opaque tint
  (`rgba(16,16,18,0.85)`) hides the blur — switched both to `.glass-card`
  (≤0.55); (2) both sat under a backdrop root (the app shell's own `.glass-card`
  for the button; the rail's `-translate-y-1/2` ancestor for the popup), so the
  `backdrop-filter` sampled an empty box — both are now `createPortal`ed to
  `document.body` and positioned from a `ResizeObserver`-tracked transcript rect.
  Added a canonical `.glass-tooltip` class (the exact chart-tooltip recipe:
  tint 0.5, blur 18 + saturate 1.35, radius 14) and applied it to both, so hover
  popups frost identically to the ECharts chart/HUD tooltips. Documented the tier
  and the "`-strong` is not for tooltips" pitfall in
  `.opencode/skills/black-eclipse-ui/SKILL.md`.
  `src/app/globals.css`, `src/components/chat/{chat-history,message-rail}.tsx`.
  `tsc` clean; vitest 1837 pass. docs updated:
  `.opencode/skills/black-eclipse-ui/SKILL.md`, `docs/CHANGELOG.md`.
- **Narrow the collapsed sidebar.** Collapsed rail is now `w-12` (48px), down
  from `w-16` (64px); the expanded sidebar stays `w-60` (240px). Icon buttons
  (`w-10`) still center. `src/components/layout/sidebar.tsx`.
  `tsc` clean; vitest 1837 pass. no doc change — styling only.

- **Sources panel for ordinary (non-gated) chat runs.** Previously only a gated
  research run produced a Sources panel; a normal chat run that consulted
  retrieval tools showed provenance only in its prose. New
  `python/harness/source_collector.py` (`SourceCollector`) collects each
  retrieval tool's `FinancialRetrievalResult` and emits a `research`-shaped blob
  with status `collected` (citations reused verbatim from
  `research.citations.build_citations`, plus consulted sources, failed routes and
  conflicts). Wired through a new `ToolContext.source_sink` (retrieval tools call
  it in `_finish`/`_record_fetched`), `build_graph(source_sink=...)`, and
  `execute_run`, which builds the collector and persists the blob on the completed
  run. The chat panel renders it with a new neutral `collected` status
  ("Sources consulted") — never a verification claim. Additive and best-effort:
  no sink ⇒ no collection, and a collector error can never break a tool. Tests:
  `python/tests/test_source_collector.py` (9). Checks: `tsc` clean; vitest 1837
  pass; pytest 1446 pass (+9). docs updated: `docs/CHANGELOG.md`,
  `docs/NAVIGATION.md`.

- **Chat "What influenced this run" panel redesign.** The run-explanation
  disclosure now spans the full transcript width, uses a magnifying-glass icon,
  and presents memory observability in plain language: stat tiles for memories
  used vs. filtered out, exclusions grouped by category with friendly reason
  text (`friendlyReason`), a memory-budget progress bar, and a compact
  "also shaping the prompt" section. Pure presentation over the existing
  `/api/harness/runs/[id]/explain` contract — no data-shape change.
  `src/components/chat/run-explanation-panel.tsx`. Checks: `tsc` clean.
  no doc change — UI presentation only, contract unchanged.

- **Operator-declared context windows + ModelSettings wire-contract fix.** Closes
  the "unknown window" limitation: `ModelSettings.context_window` (camelCase
  `contextWindow`, bounded 1…10M) carries an optional operator declaration used
  only when the catalog cannot resolve a window; the budget resolver prefers
  override → declared → catalog, and blank stays unknown (conservative ceiling,
  `windowKnown: false`). Settings › AI / LLM shows the resolved window and, when
  unknown, a numeric "Context window (optional)" field; an emptied field sends
  `null` and clears a prior declaration (`setLLMConfig` treats `null` as an
  explicit clear because JSON drops `undefined`). **Also fixed a pre-existing wire
  bug found tracing this channel:** `ModelSettings` declared `base_url`/`api_key`
  but the TS front door sends camelCase `baseUrl`/`apiKey`, so pydantic silently
  dropped both and the runtime fell back to the catalog default base URL with no
  key; `ModelSettings` now uses `to_camel` aliases + `populate_by_name` so both
  shapes work. Tests: new `python/tests/test_model_settings_contract.py` (5),
  `test_context_budget.py` (+2 declared-window), `run-service.test.ts` (+2
  contextWindow passthrough). Checks: `tsc` clean; vitest 1837 pass; pytest 1437
  pass; both eval gates PASS and unchanged. docs updated: `docs/CHANGELOG.md`,
  `docs/harness/context-budget-progress.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H66), `docs/DECISIONS.md`.
- **Close out the context-budget work.** (1) `docs/harness/context-budget-progress.md`
  status set to `Complete` after re-confirming all six milestones and re-running
  the Milestone 0 reproduction on this checkout. (2) Stale totals corrected to
  the **measured** values: vitest 148 files / 1831 tests, pytest 1430 (context
  suites 38: window 6, budget 8, repro 4, overflow 16, history_bounded 4). (3)
  `memory.retrieved` is now surfaced — mapped in `src/lib/agent/events.ts` to one
  activity item with a new distinct `kind: 'recall'` and a `Brain` icon
  (`src/components/chat/activity-item.tsx`, union in `response-model.ts`);
  `selected <= 0`/absent emits nothing; label/summary are counts and character
  budget only (no ids, excluded text or memory content); the line is expandable
  through the existing name-only detail rule, so no new variant and no run-result
  field (ADR-H65, mirrored into `docs/DECISIONS.md`). (4) The model picker is
  recorded as adjacent scope beyond the six milestones. (5) The deliberate
  omissions are confirmed documented. Tests: `src/lib/agent/events.test.ts` +4
  mirror cases. Checks: `tsc` clean; `vitest` 1835 pass (+4); `pytest` 1430
  pass; both eval gates PASS and unchanged. docs updated: `docs/CHANGELOG.md`,
  `docs/harness/context-budget-progress.md`, `docs/harness/decisions.md`,
  `docs/DECISIONS.md`, `docs/NAVIGATION.md`.
- **Add the context-budget close-out OpenCode prompt.** New
  `docs/harness/context-budget-closeout-opencode-prompt.md`. The six milestones of
  `context-budget-opencode-prompt.md` are implemented, committed (`df12d975`) and
  independently re-verified: `tsc` clean, `vitest` 148 files / 1831 tests,
  `pytest` 1430, both eval gates PASS and unchanged, and the Milestone 0
  reproduction **does** confirm all three defects (a 4096-token window rejects a
  18734-token request as a generic `PROVIDER_ERROR` with no `history_bounded`
  event, and a large-window model silently loses 20 of 40 turns). This prompt
  closes the four remaining loose ends rather than adding scope: (1) the progress
  doc still declares `status: In Progress` while every milestone is done — set it
  to Complete, but only after re-confirming that is true; (2) the same doc carries
  stale check figures (`147 files / 1828`, `1429 passed`) against the measured
  `148 / 1831`, `1430` — replace with freshly measured totals; (3) `memory.retrieved`
  is emitted by `_memory_context` with a real bounded payload but is never
  surfaced, so recall happens invisibly while trimming is visible — add the
  mirror activity mapping, a distinct `recall` kind, an icon, content-free
  count-only copy, and the `selected: 0 → null` no-op case, following the existing
  `memory.history_bounded` pattern rather than a second mechanism; (4) reconcile
  the scope delta — the commit bundled a model picker (`PROVIDER_MODELS` →
  `GET /api/harness/models` → `model-catalog.ts` → Settings › AI datalist) that no
  milestone requested and which accounts for the test-count movement — verify it,
  document it as adjacent scope, and give it a NAVIGATION entry. Also confirms the
  deliberate omissions (no compaction engine, unknown windows stay unknown,
  conservative floors, first-call-only recovery, approximate estimator) are each
  documented. docs updated: `docs/harness/context-budget-closeout-opencode-prompt.md`
  (new), `docs/CHANGELOG.md`, `docs/NAVIGATION.md`
- **No code, contract, schema or runtime behavior changed by this entry.** The
  prompt is a plan; the state it describes was measured directly on this checkout.
  `jdds.db` untouched.
- **Model picker in Settings › AI / LLM.** The Model field was a bare free-text
  input, so there was no way to *see* which models a provider offers. The Python
  catalog now declares a known-model list per provider (`PROVIDER_MODELS` in
  `python/harness/models.py`), exposed additively via `list_providers()` →
  `GET /api/harness/models` (`models` + `modelWindows`, each model → its resolved
  context window). A new client hook `src/lib/agent/model-catalog.ts`
  (`useModelCatalog`, `modelsForProvider`) feeds a native `<datalist>` on the
  Model field, which shows the declared ids **and still accepts a custom id**
  (never an allowlist), plus an honest context-window hint (`N-token window` or
  "Context window unknown"). The list is deliberately data in Python, not a
  second TS copy that would drift. Tests: `test_context_window.py` (declared
  models/windows), `src/lib/agent/model-catalog.test.ts`. Checks: `tsc` clean;
  vitest 1831 pass; pytest 1430 pass; eval gates unchanged. docs updated:
  `docs/CHANGELOG.md`, `docs/NAVIGATION.md`.
- **Model-aware context budget & honest overflow.** Fixed three defects sharing
  one root cause. **A (measured budgeting):** new
  `python/harness/context_budget.py::compute_history_budget` measures the real
  request (resolved system prompt, advertised tool schemas, the per-run profile /
  skill-manifest / memory / dropped-context blocks, the user turn, a reserved
  output allowance) and derives the history allowance from the **resolved
  model's declared window**; `graph.execute_run` builds it per run (never at
  import/`__init__`), keeping `MAX_HISTORY_CHARS` as an absolute ceiling.
  **B (classification):** `CONTEXT_OVERFLOW` added to `HarnessErrorCode`; a
  false-positive-guarded `classify_context_overflow` in `models.py` runs before
  the generic catch-all. **C (visibility):** `memory.history_bounded` is emitted
  on the success path (counts + estimates only, never content); a `bounded`
  activity line renders through the existing passthrough, and a `CONTEXT_OVERFLOW`
  failure surfaces its specific reason/remedy. **Registry:** `ProviderSpec.context_window`
  + `MODEL_CONTEXT_WINDOWS` + pure `resolve_context_window`; **unknown windows
  stay unknown** and fall back to today's conservative ceiling. **Recovery:** one
  tighter retry on a first-call overflow (no duplicated side effects, exactly one
  terminal status), then an honest failure. Additive `RunResult.context` /
  `RunRecord.context` (TS + Python) and the `HarnessRun.context` persistence
  column, absent for old rows. Tests: `test_context_window.py`,
  `test_context_budget.py`, `test_context_budget_repro.py`,
  `test_context_overflow.py`, `test_history_bounded.py`,
  `context-budget-contract.test.ts`, extended `events.test.ts`. Checks:
  `tsc --noEmit` clean; vitest 147 files / 1828 tests pass; pytest 1429 pass;
  both eval gates PASS and unchanged. docs updated: `docs/CHANGELOG.md`,
  `docs/harness/context-budget-progress.md` (new),
  `docs/harness/decisions.md` (ADR-H63/H64), `docs/NAVIGATION.md` (already had
  the row from the prompt entry).
- **OpenCode context-budget prompt (planning).** See the earlier entry below.- **Add the model-aware context-budget OpenCode prompt.** New
  `docs/harness/context-budget-opencode-prompt.md` — an implementation prompt in
  the same format as the maintenance and Phase-4 prompts, scoped to the last
  structural gap found by comparing Eclipse's context handling against a second
  agent's design. Three defects share one root cause. **A:** `graph.py` bounds
  history with hardcoded `MAX_HISTORY_TURNS = 20` / `MAX_HISTORY_CHARS = 40_000`
  constants while `ModelSettings` and `PROVIDER_CATALOG` carry no context size, so
  the request is never measured as a whole — a ~40 000-char history is roughly
  10–13k tokens, which overflows a small-context model and wastes most of a large
  one. **B:** `HarnessErrorCode` has fourteen codes and none for context overflow,
  so a provider's context-length rejection falls through to a generic
  `PROVIDER_ERROR`/`INTERNAL_ERROR` with no recovery and no explanation. **C:**
  `_bounded_history` computes the dropped turns precisely but emits an event on
  **failure only** — no success event, no count, no UI surface — so a user whose
  follow-up depends on a trimmed turn is told nothing. Six milestones: (0) a
  gating **reproduction** that must be recorded verbatim, with an explicit
  instruction to stop and report honestly if the premise does not reproduce and
  then implement only the registry + visibility work; (1) context-window
  knowledge as **catalog data** (`ProviderSpec.context_window` +
  `resolve_context_window`), reused by the existing `estimate_tokens`, with a
  documented unknown-window policy that falls back to today's conservative
  ceiling rather than guessing; (2) measured, model-aware budgeting — sum the
  real system prompt, tool schemas, per-run blocks and user turn, then derive the
  history allowance from what remains, keeping the char ceiling as an absolute
  cap, with the two halves required to land together so a raised bound cannot
  turn silent forgetting into a hard failure; (3) a `CONTEXT_OVERFLOW` code and a
  bounded classifier across the provider families with a false-positive guard;
  (4) one bounded tighter retry with no duplicated side effects and exactly one
  terminal status; (5) `memory.history_bounded` on the success path plus a chat
  surface reusing the existing event passthrough, and a specific overflow message
  instead of a generic failure; (6) verification against the Milestone 0 fixture,
  both eval gates, and the documentation obligations. Explicitly **not** a
  summarization/compaction engine, not a tokenizer dependency, not a second
  estimator, and no window guessing. docs updated:
  `docs/harness/context-budget-opencode-prompt.md` (new), `docs/CHANGELOG.md`,
  `docs/NAVIGATION.md`
- **No code, contract, schema or runtime behavior changed by this entry.** The
  prompt is a plan; the reproduction in its Milestone 0 is a required first step
  and the bug is stated as a premise to verify, not an established fact.
  `jdds.db` untouched.
- **Limitations Phase 4 (fix the remaining honest limitations).** (a) Cross-
  PROCESS maintenance lock: migration 25 adds a single-row `MaintenanceLease`
  table with a reclaimable TTL; `store.acquire_maintenance_lease` /
  `release_maintenance_lease` (SQLite-serialised, crash-safe) layered under the
  in-process lock, so two runtime PROCESSES against one database cannot sweep
  concurrently. (b) Trend honesty: the usage report's half-window trend now
  asserts a direction only when BOTH halves clear a minimum sample, else reports
  `insufficient`/`confident:false`; UI shows this. (c) Precision confidence: a
  Wilson 95% interval is reported alongside operator-labelled precision so a small
  sample is not mistaken for a precise estimate. (d) Model-assisted extraction
  now runs the SAME privacy/financial/override/dump guards as the decision gate
  (fail-closed), so a model cannot smuggle a secret, override, dump or current
  financial fact into a candidate. Tests extended across `test_skill_maintenance.py`,
  `test_usage_report.py`, `test_dropped_context.py`, `test_migration_matrix.py`.
  docs updated: `docs/CHANGELOG.md`, `docs/harness/memory-maintenance-progress.md`,
  `docs/NAVIGATION.md`.
- **Limitations Phase 3 (robustness/concurrency).** (P3.1) Skill maintenance is
  serialised by a process-wide non-blocking lock (a second pass reports
  `skipped` instead of racing), and every automatic retirement is a compare-and-set
  (`store.transition_version_status`, only firing when the version is still
  `enabled` and unpinned) so a concurrent pin/re-enable wins rather than being
  overwritten. (P3.2) Cross-cutting reopen matrix extended: agent-memory.db
  reopen, the transition CAS, and projection backup/restore round-trip. Fixed a
  real pre-existing bug found doing this: `restoreMemoryFiles`'s backup-dir
  filter rejected every real backup (the `Z` in the ISO timestamp), so restore
  silently never found its own backup. Tests: `test_migration_matrix.py`,
  `test_skill_maintenance.py`, `memory-files-guards.test.ts` extended.
  docs updated: `docs/CHANGELOG.md`, `docs/harness/memory-maintenance-progress.md`.
- **Limitations Phase 2 (measurement honesty).** (P2.1) Operator ground-truth
  conflict labels: `POST /eclipse-memory/memories/{id}/conflict-label`
  (`true_conflict` | `false_positive`), append-only as a bounded `MemoryEvent`;
  `service.label_conflict`. The usage report now reports REAL precision from these
  labels (latest judgement wins), with the dismissed-rate proxy kept as a
  clearly-labelled secondary signal. (P2.2) The usage report adds a half-window
  trend and a `smallSample` honesty flag; UI shows ground-truth precision and the
  small-sample warning. (P2.3) Skill maintenance adds a usage trend
  (active/dormant/never from a recent-execution window) and a content-free
  near-duplicate skill-id detector; surfaced in the Maintenance tab. Tests:
  `test_usage_report.py`, `test_skill_maintenance.py` extended.
  docs updated: `docs/CHANGELOG.md`, `docs/harness/memory-maintenance-progress.md`.
- **Limitations Phase 1 (correctness/clarity).** (1) Added a distinct, restorable
  `archived` skill lifecycle status (`manifest.SkillStatus`, TS `SkillStatus`,
  registry `set_status`, UI badge/filter); maintenance retirement now persists as
  `archived` instead of reusing `deprecated`, separating maintenance retirement
  from operator deprecation. (2) Surface honesty closed at the injection layer: a
  hard-off store (`memory_enabled=false`) no longer injects retrieved memory or
  the profile into the prompt (`graph._memory_context` / `_profile_context`).
  (3) Optional, policy-gated (`dropped_context_model_extraction`, default off)
  model-assisted dropped-context extraction: additive to the deterministic pass,
  inert, bounded, fail-closed, using the run's own model — no new dependency.
  (4) New `python/tests/test_migration_matrix.py` proves every historical schema
  version reopens cleanly at the latest, a pre-change database keeps its data, and
  the pin + maintenance ledger survive a reopen. Added tests for the injection
  guard and model-prompt parse. docs updated: `docs/CHANGELOG.md` (this entry),
  `docs/harness/memory-maintenance-progress.md`.
- **Memory & skills maintenance hardening — all seven milestones implemented.**
  (1) New `python/harness/skills/maintenance.py`: deterministic staleness/usage/
  retirement derived from existing `SkillExecution`/version rows, report-only by
  default, pinned versions exempt from every automatic transition, archive-never-
  delete via the existing `deprecated` lifecycle state, `SkillMaintenance` ledger,
  run through the existing startup lifespan (no new daemon). Migration 22 adds
  `SkillVersion.pinned`; migration 23 adds the ledger; policy keys
  `skill_maintenance_enabled`/`skill_stale_after_days`/`skill_archive_after_days`/
  `skill_maintenance_auto_archive`; routes `GET /skills/maintenance`,
  `POST /skills/maintenance/run`, `POST /skills/{id}/pin`; Skills → Maintenance
  tab. Fixed a pre-existing registry bug where `resolve_dependencies` treated a
  skill's own stored status as a dependency (a disabled skill could never be
  re-enabled). (2) New `python/harness/eclipse_memory/dropped_context.py` +
  `graph._dropped_context_block`: deterministic-first, inert, bounded, fail-closed
  extraction from the turns the history bound drops; a sub-bound history is
  byte-identical to before. (3) `src/lib/harness/memory-files.ts` now refuses to
  write an unreadable file, refuses externally-drifted content (snapshotting the
  raw bytes to a timestamped `.bak`), strips a leading UTF-8 BOM, decodes strictly
  and refuses a consolidation batch that would empty a non-empty entry file.
  (4) `prompts.filter_system_prompt` + `graph.resolve_surface` resolve the tool
  surface and system prompt FROM POLICY per run; a disabled store drops its tool
  and guidance. (5) New `eclipse_memory/is_trivial.py` gates bare greetings, slash
  commands and empty input out of the memory decision/retrieval path, never an
  explicit remember/forget/correct. (6) The optional semantic candidate layer was
  DELETED on its own recorded evidence: `eclipse_memory/semantic.py`, the semantic
  eval + CLI + fixture, the seven `semantic_conflict_*` and `semantic_recall_tiebreak`
  policy keys, the service candidate plumbing + `semantic_status`, the retrieval
  tie-break, the TS types/client/browser/UI controls and the rebuild route. The
  deterministic lexical path and the labeled contradiction eval remain; the
  semantic safety cases were repurposed as lexical regression cases in
  `contradictions_v1.json` (v3, 49 cases). `semantic-status` and `semantic/rebuild`
  remain as honest tombstones. (7) New `eclipse_memory/usage_report.py` +
  `GET /eclipse-memory/usage-report` + Memory Lifecycle "Real usage" panel: a
  bounded, read-only, content-free real-usage report (durable-write outcomes,
  conflict resolutions + dismissed-rate false-positive proxy, likely-missed
  conflicts) to replace reliance on perfect synthetic scores.
  docs updated: `docs/harness/memory-contradiction-detection.md`,
  `docs/harness/memory-maintenance-progress.md` (new), `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`. `jdds.db` untouched.
- **Add the Eclipse-Memory & skills maintenance hardening OpenCode prompt.**
  New `docs/harness/memory-maintenance-opencode-prompt.md` — an implementation
  prompt in the same format as the Phase-4 prompts, scoped to the gaps found by
  an external read of the memory/skill system against a second agent's memory
  design. Seven milestones: (1) skill staleness/usage/retirement maintenance with
  pinned-skills exemption, archive-never-delete and a report-only default, run
  through the existing startup lifespan with no new daemon; (2) a
  pre-compression extraction seam that is deterministic-first, inert-output-only
  and fail-closed (keeps the uncompressed transcript); (3) file-projection
  data-loss guards (refuse-to-write-unreadable, external-drift detection with
  `.bak`, BOM stripping, no batch that empties a non-empty store); (4) surface
  honesty so a disabled memory/session/external store drops its tool and its
  prompt guidance instead of advertising a tool the model cannot use; (5) a
  trivial-prompt gate that skips the decision path for greetings and slash
  commands while leaving the explicit remember/forget/correct path intact;
  (6) deletion of the semantic candidate layer on the evidence its own docs
  record, keeping the deterministic path and repurposing its safety cases as
  lexical regression cases; (7) a real-usage measurement report to replace the
  perfect scores the self-authored labeled sets report. Each milestone names the
  owning module, the exact finding it is grounded in, and the tests it requires.
  docs updated: `docs/harness/memory-maintenance-opencode-prompt.md` (new),
  `docs/CHANGELOG.md`, `docs/NAVIGATION.md`
- **No code, contract, schema or runtime behavior changed by this entry.** The
  prompt is a plan; every finding in it is tagged as verified-by-reading and
  carries an instruction to re-confirm against the current tree before acting.
  `jdds.db` untouched.
- **Amend the maintenance prompt with four verified findings and sharpen three
  milestones.** Amended in place (no second prompt file — `NAVIGATION.md` already
  points at this one). Added findings: (A8) prompt caching is **not** at risk from
  this work — `graph.py` rebuilds `profile_block`/`skill_manifest`/`memory_block`
  as per-run SystemMessages and `prompt_cache_key` is identity-only, so there is no
  byte-stable cross-run prefix; (A9) **no skill pin flag exists** on `SkillVersion`,
  so Milestone 1's pin mechanism is *add*, not *reuse*, and needs an additive
  migration; (A10) the user's full prior conversation arrives every turn from
  `stock-chat.tsx`, so turns dropped at the history bound are recoverable
  client-side. Sharpened: (A2/M2) the pre-compression seam is **already located** —
  `graph.py:_history_messages` with `MAX_HISTORY_TURNS = 20` /
  `MAX_HISTORY_CHARS = 40 000` — replacing the earlier "it may be inside a
  dependency, document the limitation" escape hatch with a seam table, a
  caching-settled section, and the rule that the summary rides the existing per-run
  SystemMessage slot and must not touch the system-prompt head; (M2) fail-closed
  restated as "never emit a lossy summary" (the turn bound is pre-existing
  behaviour and is not reverted) plus a requirement that a sub-bound history render
  byte-identically to today; (M1) the pin flag is per-version state, orthogonal to
  `status`, with a reopen-survival test; (M4) exact call sites
  (`service.py` ~line 79, `ECLIPSE_AGENT.tools`, `prompts.py`) and a per-run — never
  import-time — policy resolution requirement, following the existing
  `session_history_enabled` read in `graph.py`. docs updated:
  `docs/harness/memory-maintenance-opencode-prompt.md`, `docs/CHANGELOG.md`
- **No code, contract, schema or runtime behavior changed by the amendment
  either** — it is still a plan document. `jdds.db` untouched.
- **Investor Eye map: render all of Jammu & Kashmir as Pakistan (deliberate POV).**
  Reworked the committed `public/geo/world.geo.json` so the Kashmir Valley,
  Jammu, Ladakh and the LoC-administered tracts join Azad Kashmir and
  Gilgit-Baltistan under Pakistan, using Natural Earth's authoritative 10m
  `Kashmir` region polygon spliced with `martinez-polygon-clipping` (exact shared
  edge, no slivers or gaps; only the `India` and `Pakistan` features changed,
  Aksai Chin stays with China). Added a warning to
  `scripts/fetch-world-geo.mjs` because its regeneration path emits the default
  Natural Earth view and would silently revert this policy. docs updated:
  `docs/investor-eye-architecture.md`, `docs/CHANGELOG.md`

## 2026-09-28

- **Eclipse Memory: cut per-request runtime-probe and serial-fetch overhead.**
  Measured: Python memory endpoints answer in 6–12 ms, but the Next memory
  routes took ~100 ms cold and 1.7 s spikes; a 6-way parallel burst of the same
  route took 10.6 s. Two causes, both fixed. (1) `ensurePythonRuntime()` — called
  by *every* proxied request via the shared `request()` helpers — did a full
  `/health` round-trip **and** a synchronous `python/harness/*.py` directory scan
  on each call, with no caching or coalescing. It now has a 5 s success-TTL fast
  path and in-flight promise coalescing, so the several routes a Memory tab fans
  out share one probe instead of N probes. (2) The Lifecycle tab fetched
  lifecycle→retention→semantic sequentially and the Health tab fetched
  health→database-health sequentially; both now use `Promise.all`, removing the
  serial round-trip chain. The remaining ~65 ms per route is generic Next.js dev
  overhead (a non-Python route measures the same), not memory-specific. Checks:
  `tsc` clean; Vitest **1808 passed**; Python **1315 passed**; lint 0 errors.
  `jdds.db` untouched.
  no doc change — performance fix; contracts and architecture unchanged

## 2026-09-28

- **Command Center fullscreen: move the Exit control into the top bar.** The
  fullscreen overlay's Exit button floated at bottom-right over the board; it
  now sits in the TopBar row (top, trailing edge, next to the app chrome) and
  no longer overlaps widget content. Placement/style-only fix; no doc change —
  presentation change, no architecture/contract/setup impact.

## 2026-09-28

- **Eclipse Memory: fix overlapping overlays + structural pass.** (1) The
  Memory Control Room's six hand-rolled drawers/modals were rendered inline
  inside the screen root, which lives under the shell's `glass-card`
  (`backdrop-filter`) container — a containing block/backdrop root — so
  `position: fixed` was scoped to it and the surfaces clipped, sat under the
  header and overlapped the floating chat dock; they also used `z-50`, *below*
  the dock (`z-[90]`). Added one shared primitive
  (`eclipse-memory/memory-overlay.tsx`: `MemoryDrawer` + `MemoryModal`) portaled
  to `document.body`, with Escape/backdrop close, body scroll lock, a sticky
  header and consistent width tiers; migrated all six overlays to it.
  (2) Established the app z-index tiers (fullscreen 80–86 < dock 90 <
  drawers/dialogs 100 < toasts 110) and moved the Skills toast to `z-[110]`.
  (3) Responsive/structure pass: Lifecycle now shows the counts grid first and
  pairs retention + contradiction detection side-by-side instead of stacking
  full-width blocks ahead of the list; Files uses a `minmax(0,…)` grid so it no
  longer overflows on narrow widths. New ADR-037. Checks: `tsc` clean; Vitest
  **1808 passed**; Python **1315 passed**; lint 0 errors. `jdds.db` untouched.
  docs updated: DECISIONS.md (ADR-037)

## 2026-09-28

- **Memory & Skills: consistent, properly-centred loading states.** Loading
  placeholders were inconsistent — some sat left-aligned, some top-anchored, at
  differing heights, and `SkillQuality`/`Onboarding` rendered an inline spinner
  with no centering at all. Added one shared `LoadingState` atom to
  `skills/skill-ui.tsx` (flex column, both axes centred, `min-h-[40vh]`, optional
  hint) and a matching centered `Spinner` in `eclipse-memory/memory-ui.tsx`, then
  routed every Skills sub-page loader through it (library, learning queue,
  execution activity, evaluation, project skills, bundles, journey, quality,
  onboarding, skill detail). Removed the now-unused `Loader2` imports. UI-only;
  no contract/architecture change. Checks: `tsc` clean; Vitest **1808 passed**;
  Python **1315 passed**; `jdds.db` untouched.
  no doc change — UI-only tweak; NAVIGATION/ARCHITECTURE contracts unchanged

## 2026-09-28

- **Memory & Skills UI: unreachable Memory sub-tabs, full-width panels.** (1)
  Fixed a real bug in the Memory Control Room: the `History` (session-search)
  view and the `Sessions` view both existed in the `Tab` union but the tab bar
  only rendered `Sessions` — `History` was unreachable, and the subroute map
  wrongly aliased `sessions → "history"`, so selecting Sessions opened the
  buttonless search view. Added a distinct "Session Search" tab and corrected
  the map (`sessions → sessions`, `history → history`). (2) The Memory tab bar
  now passes `wrap` (like Skills) so the 15 tabs wrap instead of scrolling into
  a hidden-scrollbar clip. (3) Memory root gained `pb-24` so content clears the
  floating chat dock. (4) Removed the leftover `max-w-3xl` on the Skills
  `GuidedLearn` and `OnboardingPanel` roots so those sub-pages fill the width
  like the rest of the screen. UI-only; no contract/architecture change. Checks:
  Vitest **1808 passed**; Python **1315 passed**; `tsc` clean;
  `jdds.db` untouched.
  no doc change — UI-only fix; NAVIGATION/ARCHITECTURE contracts unchanged

## 2026-09-28

- **Skills UI: full-width layout, pagination, wrapping tabs.** (1) The Skills
  screen now uses the app's screen convention (`w-full`, `px-4 md:px-8`) with
  `pb-24`, so content fills the width and the last row is never hidden behind the
  floating chat dock. (2) Added a shared `Pagination` (`src/components/ui/
  pagination.tsx`: `usePagination` + `PaginationFooter`, client-side, page-size
  selector, auto-clamps when the list shrinks) and applied it to the unbounded
  lists — Learning Queue (25/page), Execution Activity (25/page), and Journey
  relations (25/page). This fixes long lists overflowing the page. (3) `TabBar`
  gained a `wrap` option (dense tab rows wrap instead of clipping the last tab
  behind a hidden scrollbar); the Skills tab bar uses it. UI-only; no
  contract/architecture change. Checks: Vitest **1808 passed**; Python **1315
  passed**; `tsc` clean; lint 0 errors. `jdds.db` untouched.
  docs updated: CHANGELOG.md

## 2026-09-28

- **Skills UI: journey force-graph + execution-list 404 fix.** (1) The Journey
  tab rendered two long text columns instead of a graph; it now shows an
  ECharts force-directed graph of the derived learning journey
  (`learning-graph.tsx`): node colour by `kind`, edge colour by `relation`, size
  by degree, hover tooltip, click-to-inspect (relations list), kind-filter
  highlight, and a full-page (Esc) mode — modelled on `investor-eye/graph-panel`.
  No backend change; the nodes/edges already came from `learning_graph.py`.
  (2) Fixed a real 404: `skills-browser.listSkillExecutions` called
  `GET /api/skill-executions`, but only the `[runId]` proxy existed, so the
  Execution Activity tab fetched nothing; added the list route. (3) The Library
  loading state is now a labelled spinner instead of empty skeleton cards that
  read as a broken page. Checks: Vitest **1808 passed**; Python **1315 passed**;
  `tsc` clean; lint 0 errors. `jdds.db` untouched.
  docs updated: CHANGELOG.md (UI-only change; no architecture/contract change)

## 2026-09-28

- **Engineering follow-up: lint, router split, frontend atoms, a11y.** (1) Fixed
  `eslint.config.mjs` to ignore `.next-dev/**` — the dev build output was being
  linted, producing all 400 reported "errors"; source now lints to **0 errors**,
  and the CI lint step is blocking (was `continue-on-error`). (2) Extracted the
  remaining front-door route groups from `python/harness/main.py` into
  `routers/memory.py` (46), `routers/skills.py` (18), `routers/sessions.py` (23)
  alongside `routers/mcp.py` (11); `main.py` shrank 2,604 → **919 lines** with no
  path/behavior change (one internal monkeypatch target in
  `test_memory_reliability.py` moved with it). (3) Extracted the Eclipse-Memory
  presentational atoms into `eclipse-memory/memory-ui.tsx` (screen 2,598 → 2,444
  lines). (4) Added a dependency-free a11y store test
  (`src/lib/i18n/store.a11y.test.ts`). (5) Verified `jdds.db` remains unstaged and
  uncommitted. Checks: Vitest **1808 passed** (145 files); Python **1315 passed**;
  `tsc` clean; lint 0 errors; retrieval/semantic/contradiction/compaction gates
  PASS. `jdds.db` untouched.
  docs updated: CHANGELOG.md, NAVIGATION.md, harness/architecture.md

- **Engineering hardening pass (CI, routing, honest errors, guards).** Seven
  focused items: (1) added a **CI workflow** (`.github/workflows/test.yml`) that
  runs `typecheck` + `test` (Vitest + Python) + the four eval gates, plus an
  `npm run typecheck` script; (2) triaged the TODO/FIXME markers — the only
  genuine one is a documented, deliberate deferral, left as-is; (3) added a
  route-level test for the honest **503 runtime-unavailable** path and fixed a
  real defect where `HarnessRuntimeUnavailable` was collapsed to `INTERNAL_ERROR`
  (`errors.py` now preserves `RUNTIME_UNAVAILABLE`); (4) extracted shared state +
  operator auth into `python/harness/deps.py` and the MCP routes into
  `python/harness/routers/mcp.py` (registered via `app.include_router`), shrinking
  `main.py` from 2604 → 1890 lines with no behavior/path change; (5) added a
  retrieval-layer **adversarial eval** (`test_research_adversarial.py`: no
  fabricated value, staleness surfaced, unresolvable conflict preserved, poisoning
  cannot beat a primary, identity never crosses); (6) added an i18n dictionary
  integrity test and a source-size budget guard; (7) full verification. Checks:
  Vitest **1804 passed** (144 files); Python **1315 passed**; `tsc` clean;
  retrieval/semantic/contradiction/compaction gates PASS. `jdds.db` untouched.
  docs updated: CHANGELOG.md, NAVIGATION.md, harness/architecture.md

- **Memory & Skills closure pass (verification only).** Read-only audit + full
  suite re-run. One defect fixed: the `import_payload` docstring still described a
  SQLite `SAVEPOINT` for atomicity while the implementation uses table
  snapshot/restore (a SAVEPOINT cannot survive `write_memory`'s per-write COMMIT).
  Corrected the docstring; no behavior change. All checks pass (Vitest 1795,
  Python 1305, `tsc` clean, retrieval/semantic/contradiction/compaction gates
  PASS). `jdds.db` untouched by this task.
  docs updated: CHANGELOG.md, python/harness/eclipse_memory/transfer.py (docstring)

- **Memory & Skills final hardening — all 11 phases (identity boundary → docs
  reconciliation).** Audited the already-implemented evolution work and closed
  only the remaining gaps: (1) identity/tenancy — documented + deployment-guarded
  (non-loopback bind without operator secret refused/flagged; `0.0.0.0` no longer
  a trusted local host); (2) per-skill project trust content identity + approval
  history + selective quarantine; (3) expanded contradiction eval
  (paraphrase/negation/numeric/subject-alias/temporal) with missed-conflict,
  scope-leakage, forbidden-hit, precision metrics + honest semantic
  interpretation; (4) skill-quality evidence states (no/insufficient/mixed/
  reliable/degraded), failure-cause trends, regression inside promotion
  evidence; (5) journey freshness (`watermark`, refresh state, execution nodes,
  session placeholder nodes); (6) provider reliability (timeout budget,
  `provider_failure` class, recovery-through-router, bounded event history,
  last-success age); (7) import/export hardening (v3, conflict/duplicate preview,
  atomic rollback, evaluation + audit preservation); (8) compaction preservation
  eval (temporal/authority, evidence/chain/reversibility floors); (9) bundle
  reproducibility (member content hashes, update preview, receipt, safe
  rollback, lock history); (10) adversarial/long-running eval (overlapping
  projects, provider poisoning/recovery, growth, repeated compaction, floors);
  (11) documentation reconciliation (historical labels + Current status table).
  Python **1305 passed**; Vitest **1795 passed**; `tsc` clean; contradiction and
  compaction gates PASS. No second memory engine, no TS agent runtime, no
  `jdds.db` change.
  docs updated: CHANGELOG.md, NAVIGATION.md, harness/memory-skills-evolution-plan.md

- **Memory & Skills remaining gaps — Phase 16 (orphan/inconsistency cleanup).**
  Fixed the stale `run_only` outcome docstring + downgrade comment (the outcome
  set is `save/suggest/history_only/ignore`; the defensive branch is retained);
  corrected the `explain_memory` `run_analysis` source mapping (that is a decision
  *path*, not a stored source — mapped to `execution_lesson`); marked
  `eclipse_memory/hybrid.py` explicitly **experimental/deferred** (it is not wired
  into retrieval); fixed the stale `eclipse_memory/__init__.py` DB-path docstring;
  and promoted Lifecycle + Activity to top-level tabs in the Memory screen (were
  deep-link-only). No behavior/authorization change.
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md

- **Memory & Skills remaining gaps — Phase 15 (adversarial evaluation + floors).**
  Added `python/tests/test_adversarial_evolution.py` (15): prompt injection in
  project/generated/bundle content, trusted-skill drift, cross-project/scope
  leakage, stale/contradictory facts, disabled-skill invocation via bundle,
  bundle permission escalation, import tampering, secret persistence,
  retention edge cases, low-sample quality claims, and a consolidated
  safety-floor test (zero scope leakage / unauthorized writes / forbidden
  retrieval / unapproved activation / permission escalation / secret
  persistence). Hardening found and fixed: `write_memory` now ALSO refuses a
  credential VALUE at the single persistence path (`looks_like_credential_value`)
  — defense in depth beyond the decision gate — without over-blocking a benign
  sentence that merely mentions "secret"/"token".
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md

- **Memory & Skills remaining gaps — Phase 14 (skill dependency visibility).**
  Added `SkillRegistry.dependency_graph` (version-rich nodes + per-edge status
  ok/optional/missing/disabled/incompatible, resolved order, cycles) exposed on
  `GET /skills/{id}`; a read-only `GET /skills/{id}/preflight` returns why a skill
  would be unavailable before a run. Dependencies are never auto-enabled. TS
  types + a resolved-dependency list in the skill detail. Tests +2 in
  `test_skills_registry.py`.
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md,
  NAVIGATION.md

- **Memory & Skills remaining gaps — Phase 13 (cold-start onboarding).** Added
  `python/harness/onboarding.py` (static, read-only explanation of Facts /
  Session History / Skills / trust / retention) + `GET /onboarding` returning
  bundled starter skills with visible `bundled` provenance. It writes NO durable
  memory, enables nothing, and changes no policy. TS + UI "Start Here" tab.
  Tests `python/tests/test_onboarding.py` (3).
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md

- **Memory & Skills remaining gaps — Phase 12 (import/export hardening).** Export
  documents now carry a content `checksum` (verified before ANY import write — a
  tampered/corrupted file is refused, never partially applied), bundle lifecycle
  fields round-trip (version/memberVersions/locked), and import supports
  `dry_run`, `scope_filter`/`type_filter`/`bundles_only` partial restore, and
  reports `checksumOk`/`importable`. The Health tab now has a Choose-file →
  Preview (dry run) → Apply flow. Tests +5 in `test_memory_transfer.py`.
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md

- **Memory & Skills remaining gaps — Phase 11 (freshness/retention UX).** Added a
  **stale** lifecycle state (active but not confirmed/used in a long time — still
  recalled) with a count + view; an expiry reason code
  (`expiry: retention_period_elapsed`); a `nextMaintenanceAction` on
  `retention_status`; and a non-destructive **retention preview**
  (`GET /eclipse-memory/retention/preview`, `preview_retention`) showing what a
  sweep would expire without sweeping. Durable-memory and session-retention keys
  remain separate. Tests `python/tests/test_retention_freshness.py` (6).
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md

- **Memory & Skills remaining gaps — Phase 10 (provider reliability).** Added
  `python/harness/memory_providers/reliability.py`: deterministic failure
  classification (transient/permanent/unauthorized/unsupported/rate_limited/
  unavailable), bounded retry (transient/rate-limited only, ≤2 attempts), an
  in-memory circuit breaker (opens after 3 consecutive failures for a 30s
  cooldown, then half-opens), and a bounded rolling latency/failure history with
  last-success. Wired into `registry.search_external` (an open circuit SKIPS the
  provider and reports it degraded — a failing provider cannot stall every run)
  and surfaced in `diagnostics` + the Providers UI. Native memory is never
  retried or held back. Tests `python/tests/test_provider_reliability.py` (16).
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md,
  NAVIGATION.md

- **Memory & Skills remaining gaps — Phase 9 (bundle lifecycle).** Bundles gained
  a semver `version` identity, optional member-version lock, and drift detection:
  `lock_bundle`/`unlock_bundle` pin the current resolved member versions, and
  `resolve_bundle` reports `drifted`/`incompatible` when a member changes after a
  lock — visible before execution. A bundle still never enables a disabled skill
  or widens a permission. Schema migration 18 (`SkillBundle.version`,
  `memberVersions`, `locked`); routes `POST/DELETE /skill-bundles/{id}/lock`;
  TS + UI (version/locked/drifted badges, Lock/Unlock). Tests +5 in
  `test_skill_bundles.py`.
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md,
  NAVIGATION.md

- **Memory & Skills remaining gaps — Phase 8 (journey freshness).** The learning
  journey now returns `generatedAt` + a source `watermark`, and the UI shows a
  "last updated" line and silently refreshes on tab/window refocus (the graph is
  derived and bounded; no second store or persisted graph DB). Tests +2 in
  `test_learning_graph.py`.
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md

- **Memory & Skills remaining gaps — Phase 7 (run observability).** The
  `memory.retrieved` event now records which memory ids were injected, a bounded
  sample of exclusions WITH their reason, and the budget used. Added
  `python/harness/run_observability.py` (`explain_run`) which derives a bounded,
  redacted run explanation from canonical retrieval/run events (injected facts,
  exclusions by category scope/status/expiry/permissions/relevance/budget/trust/
  drift, profile, prompt-plan segments, bundle resolution). Route
  `GET /runs/{id}/explain` + Next proxy + `getRunExplanationFromRuntime` + a
  collapsed "What influenced this run" panel in chat history. Derived read-only;
  changes nothing at runtime and redacts secrets. Tests
  `python/tests/test_run_observability.py` (6).
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md,
  NAVIGATION.md

- **Memory & Skills remaining gaps — Phase 6 (skill quality over time).** Extended
  `eclipse_memory/skill_quality.py` with per-day execution trends, a recency-
  weighted success rate, a 95% Wilson success interval, an explicit low-sample
  warning (`sampleReliable`; `<20` executions), deterministic failure-cause
  clustering (missing tool/invalid input/output validation/unsupported data/
  timeout/permission denied/user correction/provider failure/tool budget), a
  `version_quality_history` trend view, and same-evaluation-case comparison
  (`compare_evaluation_cases`, `caseRegressions`). Fixed `save_evaluation` to
  persist each case's `status` (it was dropped). Added the missing front-door
  routes `/skills/{id}/quality`, `/promotion-evidence`, `/quality/compare` +
  `/quality-history`, TS client/browser + Next proxies, and a Quality-over-time
  panel in the skill detail. Tests `test_skill_quality_trends.py` (8).
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md,
  NAVIGATION.md

- **Memory & Skills remaining gaps — Phase 5 (conservative compaction).** Added
  `python/harness/eclipse_memory/compaction.py`: deterministic near-duplicate
  detection over ACTIVE memories (same scope+subject+type, canonical-token
  overlap or subset) producing **inert** proposals. Acceptance creates one merged
  memory and supersedes the originals (linked + retained); rejection changes
  nothing; a lossy merge is refused by a preservation check; contradictions and
  cross-scope records are never grouped. Persisted in `CompactionProposal`
  (migration 17); routes `/eclipse-memory/compaction[/detect|/{id}/accept|/reject]`
  (operator-gated) + TS client/browser + proxy routes + a Compaction panel in the
  Lifecycle tab. Added a labeled preservation evaluation with absolute safety
  floors (`eval/compaction.py`, gate PASS). Tests `test_memory_compaction.py` (12).
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md,
  NAVIGATION.md

- **Memory & Skills remaining gaps — Phase 4 (conflict-resolution UX).** Added
  `EclipseMemoryService.conflict_review` (side-by-side comparable records:
  content/type/scope/authority/provenance/confidence/timestamps/expiry/access)
  and `resolve_conflict` with safe, auditable, reversible actions — keep,
  supersede, merge (new explicit fact, both superseded + linked), confirm-both,
  dismiss, defer. Semantic similarity never resolves automatically. Routes
  `GET /eclipse-memory/memories/{id}/conflict` and `POST .../resolve`
  (operator-gated) + TS client/browser + proxy routes + a ConflictReview panel
  in the Memory screen. Tests `python/tests/test_memory_conflict_review.py` (9).
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md

- **Memory & Skills remaining gaps — Phase 3 (skill content injection defense).**
  Added `python/harness/skills/content_scan.py`: an ADVISORY scanner over skill,
  project, bundle, and generated-draft prose. It detects instruction-override,
  secret-reveal, approval-bypass, self-enable, disable-safety, system/role
  impersonation, ignore-policy and exfiltration patterns, returning bounded
  findings with reason + a bounded snippet. A quarantine-severity finding holds
  back a **project/profile/generated/external** skill from the registry (bundled
  source is human-reviewed and only warned); the finding is recorded as
  `skill.content_quarantined`. Warnings cannot be suppressed by skill content. A
  clean scan is explicitly NOT proof of safety — the permission/execution gate is
  unchanged. Wired into registry `register`, `learn.build_learn_draft`, and
  `authoring.scan_manifest_content`; surfaced via `/skills`, `/skills/{id}`.
  Tests `python/tests/test_skill_content_scan.py` (16).
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md

- **Memory & Skills remaining gaps — Phase 2 (trusted project skill drift).**
  `ProjectSkillTrust` gained `trustedHash`/`revokedHash` (migration 16). Trust
  now records the root's content identity — `root_content_hash` now covers the
  manifest AND the instruction prose. When a trusted root's content changes, its
  skills are **quarantined** (not loaded), a `skill.project_drift` event is
  recorded, and the UI shows a Re-approve action; re-approving re-baselines the
  hash (`skill.project_reapproved`). Untrust remains immediate and records the
  revoked hash. Changed files: `python/harness/skills/project_skills.py`,
  `skills/registry.py`, `eclipse_memory/{schema,store}.py`, `main.py`; TS
  `skills-{types,client,browser}.ts`, `project-skills.tsx`, new
  `/api/skills/project/approve` route. Tests +6 in `test_project_skills.py`.
  docs updated: CHANGELOG.md, harness/memory-skills-evolution-plan.md,
  NAVIGATION.md

- **Memory & Skills Evolution — final delivery report.** Added the before/after
  architecture summary, memory-vs-session-history-vs-skills explanation, security
  & trust model, retrieval and skill-learning evaluation reports, provider
  behavior report, migration/rollback plan, remaining risks, and the
  no-secrets/no-jdds.db/no-authorization-bypass confirmations to
  `harness/memory-skills-evolution-plan.md`.
  docs updated: harness/memory-skills-evolution-plan.md, CHANGELOG.md

- **Memory & Skills Evolution — Phase 8 (hardening + backup compat).** Bumped
  the memory export schema to v2 to carry `bundles` and `projectTrust`, so a
  backup/restore or migration no longer loses composability or skill-trust
  provenance (v1 documents still import). Added cross-cutting regression tests
  `python/tests/test_evolution_hardening.py` (9) covering project trust/untrust,
  disabled-skill-in-bundle, generated-skill secret sanitization, inertness,
  export/import roundtrip, v1 compat, archive reversibility, scope isolation and
  bundle prompt-budget bounds. Added an Operations section (paths, trust model,
  configuration, provider setup, backup/import/reset/migration, recovery) to the
  evolution plan.
  docs updated: harness/memory-skills-evolution-plan.md,
  harness/phase-3-memory-progress.md, CHANGELOG.md

- **Memory & Skills Evolution — Phase 7 (provider diagnostics).** Enhanced
  `memory_providers/diagnostics.py`: per-provider capability summary, data-
  location warning (native local vs external), verified-by-Eclipse flag,
  freshness stamp, a process-wide privacy note, and a bounded non-destructive
  `provider_test` (health + capped search only). Route
  `POST /memory-providers/test` (operator-gated); the Providers tab shows the
  summary, data location, a Test button and the privacy note. Native-first
  routing and external fencing unchanged. Tests: +3 in
  `test_memory_providers.py`.
  docs updated: CHANGELOG.md, harness/phase-3-memory-progress.md

- **Memory & Skills Evolution — Phase 6 (learning journey).** Added
  `python/harness/learning_graph.py`, a derived read-only provenance graph
  projected from canonical rows (memories, skills/versions, candidates,
  corrections, mistakes, promotions, sessions). It never writes or stores a
  copy, is bounded (≤400 nodes / ≤800 edges), respects scope isolation, never
  exposes secrets, and keeps inactive items as status-tagged nodes. Fixed edge
  vocabulary. Route `GET /learning/journey` (kind/status/since filters); UI
  Skills › Journey. Tests `test_learning_graph.py` (6).
  docs updated: harness/decisions.md (ADR-H62), NAVIGATION.md,
  phase-3-memory-progress.md, CHANGELOG.md

- **Memory & Skills Evolution — Phase 5 (semantic measurement).** The optional
  semantic layer was verified to already satisfy the required safety/metadata
  contract (candidate-only, off by default, gated by labeled evals with
  recall/precision, false-candidate/-conflict rates, scope leakage, forbidden and
  no-match overreach, budget compliance). Added the one missing reported metric —
  **latency** (`metrics.latencyMs.mean|max`) — to the deterministic retrieval
  eval, so a future semantic layer can be compared against the lexical baseline.
  No behavior change; both eval gates pass.
  docs updated: CHANGELOG.md, harness/phase-3-memory-progress.md

- **Memory & Skills Evolution — Phase 4 (guided `/learn`).** Added
  `python/harness/skills/learn.py`: an explicit run/document/repository/repeated-
  workflow/correction request becomes a complete but **inert** skill draft
  through the existing `propose_draft` path. Content is sanitized (secrets, raw
  transcript lines, issue references removed) and advisory-linted (absolute
  dates, first-person narration flagged) before the draft is built; the draft
  defaults to the safe read-only permissions and existing tools and stays
  `draft`/`not_evaluated`. Operator-gated; one-off runs never auto-activate.
  Route `/learning/from-source`; UI Skills › Learn a Skill. Tests
  `test_guided_learning.py` (8).
  docs updated: harness/decisions.md (ADR-H61), NAVIGATION.md,
  phase-3-memory-progress.md, CHANGELOG.md

- **Memory & Skills Evolution — Phase 3 (skill bundles).** Added composable
  skill bundles (`python/harness/skills/bundles.py`; `SkillBundle` migration 15)
  that group existing skills under a stable id with optional instructions/
  constraints. A bundle is a reference: `resolve_bundle` is deterministic and
  reports missing/unavailable members; it never enables a disabled skill, widens
  a permission, or exceeds the bounded prompt manifest (≤12 skills, bounded
  content on write and read). `RunRequest.bundleId` expands a bundle instead of
  keyword discovery (emits `skill.bundle_resolved`). Routes `/skill-bundles`
  (+`/{id}`); UI Skills › Bundles. Tests `test_skill_bundles.py` (8).
  docs updated: harness/decisions.md (ADR-H60), NAVIGATION.md,
  phase-3-memory-progress.md, CHANGELOG.md

- **Memory & Skills Evolution — Phase 2 (project-local skills).** Added
  repository-carried skill roots under `.black-eclipse/skills/` and
  `.agents/skills/`, discovered by `python/harness/skills/project_skills.py` but
  **inert until an operator trusts the root** (`ProjectSkillTrust`, migration 14;
  names-only notice for untrusted roots; contents never read). Precedence is
  deterministic project > profile > bundled, with a project skill legally
  shadowing a same-id bundled skill (recorded separately, not an error).
  Trust/untrust is per absolute path and revocable; untrust stops injection on
  the next load. A project skill cannot grant a permission, enable itself, or
  bypass evaluation — it uses the existing `execute_skill` default-deny gate.
  Global opt-out policy `project_skill_discovery`. Routes `/skills/project`,
  `/skills/project/trust`, `/skills/project/untrust`; UI Skills › Project Skills;
  provenance surfaced in list/detail. Tests `test_project_skills.py` (9).
  docs updated: harness/decisions.md (ADR-H59), harness/architecture.md,
  NAVIGATION.md, phase-3-memory-progress.md, CHANGELOG.md

- **Memory & Skills Evolution — Phase 1 (simpler mental model).** Renamed the
  Control Room tabs to user-facing categories — Facts, Session History, Skills,
  Suggestions, Reviews, Health/Export — and promoted Suggestions to a top-level
  tab. Added a three-card legend explaining what belongs in Facts vs Session
  History vs Skills, an origin badge per fact (auto/explicit/imported/external/
  suggested) derived only from existing authority/source/status fields, and
  freshness/authority fields (last confirmed, expires) plus a competing-memory
  callout in the fact detail. No persistence, retrieval, authorization or scope
  behaviour changed; proposed items remain inert.
  docs updated: CHANGELOG.md

- **Memory & Skills Evolution — Phase 0 audit/design.** Wrote the design
  authority for the Hermes-inspired memory/skill work: target product model
  (always-available facts vs searchable session history vs task-specific
  skills), a gap analysis (G1–G14) with every proposed feature mapped to an
  owning module, the contracts that must not change, the new inert-by-default
  contracts, a concise data-flow and module map, safety/scope invariants, and an
  explicit deferred list. Confirmed the existing strengths (decision gate,
  scope isolation, contradiction/expiry, deterministic retrieval + eval, inert
  skill drafts, external-provider fences) are preserved; no second memory engine
  or TS agent runtime is proposed.
  docs updated: harness/memory-skills-evolution-plan.md (new), CHANGELOG.md

## 2026-09-27

- **UI sounds: reliable playback, new default voice, chat message cue.** Two
  long-standing defects and one feature:
  - *Intermittent silence fixed.* `sound-manager.ts` was a Howler singleton that
    unlocked the `AudioContext` only on the **first** gesture and did a
    fire-and-forget `ctx.resume()`; whenever the context later drifted to
    `suspended` (tab hidden, OS audio-focus change, first-gesture race), cues
    were silently dropped. Rewrote it on the raw **Web Audio API**: one
    persistent context, armed on *every* pointer/key gesture and on
    `visibilitychange`/`focus`, with `play()` awaiting `resume()` before
    starting the buffer and an `onstatechange` re-arm. Decoded buffers are
    cached by source URL. Dropped the `howler` + `@types/howler` dependencies.
  - *New default voice.* The `eclipse` pack was re-synthesised as a warm,
    harmonic, low-volume premium tick set; default master volume raised 8%→12%
    so cues are clearly present. Added a dedicated `message` cue for an
    incoming assistant reply and generated the missing per-pack
    `message.wav` for the other eight packs. Storage key bumped `_v2`→`_v3` so
    the refreshed cue set/pack applies for existing installs.
  - *Chat reply sound.* Both chat surfaces now fire `sound.message()` when an
    assistant turn **finishes** (streaming stays mute): `stock-chat.tsx`
    (was `sound.success()`) and `chat-dock.tsx` (previously sounded nothing).
  docs updated: CHANGELOG.md, ARCHITECTURE.md, NAVIGATION.md

- **Trading Calendar redesign (Journal › Calendar).** The month grid was a wall
  of flat raw-colour boxes with a black weekend overlay and an inconsistent
  header. Reworked onto the shared design system:
  - New theme-aware `.cal-cell` / `.cal-chip` classes in `globals.css` — a
    translucent tint + token-driven P&L colour (`--brand` / `--bearish`) with an
    inset highlight and **no per-cell backdrop blur** (35 blurred cells is a
    needless memory cost; the parent card already frosts the backdrop). Light
    mode gets its own override; the weekend "dim" is now a translucent opacity,
    not `bg-black/20`.
  - `month-calendar.tsx` now renders full Mon–Sun **week rows** with a per-row
    **weekly total column** (`W1…`, net R, trade count, tinted by sign), plus a
    per-day "best trade" hint and a month-total in the footer. Date number +
    day net R are on the top row with tabular numerals.
  - `calendar.tsx` header gained the shared icon tile and a richer 4-up summary
    strip: Trades, Win Rate (with progress bar), Net R (with a daily
    net-R sparkline) and Net P&L — each with sub-stats.
  - `month-calendar-card.tsx` (Overview embed) header restyled to match: icon
    tile, stat pills tinted with the same cell tokens, consistent nav pill.
  - Deleted `calendar-heatmap.tsx` — a 195-line component with no importer
    (dead duplicate of the mini strip; its fixed tooltip also lacked the portal
     fix). Updated the stale `intensity.ts` comment.
  docs updated: CHANGELOG.md

- **Trading Calendar — profit/loss tinted cells.** Day cells (and the weekly
  column) are tinted by result again — green brand wash for a profitable day,
  red bearish wash for a losing day, neutral for empty — but sitting on the
  darker `.cal-shell` and keeping the plain `symbol · R` rows with no chip
  background. Strengthened the `.cal-cell--pos` / `--neg` fill/border opacity so
  the sign reads clearly against the darker shell.
  no doc change — presentation-only, no architecture/contract/setup change.

- **Market screener — filters, sorting and taxonomy corrected across the whole
  universe.** A cluster of defects made the screens disagree with the data:
  - **Country filter / column.** JDDS stores `Asset.country` inconsistently
    ("US" vs "United States", plus foreign domiciles). `/api/stocks` normalizes
    it through `countryToMarketId`, the country dropdown is deduped, and the
    filter matches every raw form. The client hook no longer forces each row to
    equal the selected market's domicile — that hidden constraint dropped ~1,516
    US-listed names stored as "United States" and every cross-listing.
  - **Header sorting spans the full universe.** `/api/stocks` honours
    `sort`/`dir` (Asset + Price columns) so a header click orders the whole
    market before pagination; the page cache resets on sort change and the hook
    skips re-sorting a server-ordered slice. Nulls-last is applied only to
    nullable columns (`price`/`changePct` are non-nullable).
  - **Compounding OR filters.** `type` (multi-select) and `search` both wrote
    `where.OR`, so the later silently discarded the other; they are now collected
    into `where.AND`.
  - **Change filter boundaries** now exclude exactly 0 from Positive/Negative.
  - **Type multi-select** client matching splits the comma-joined value.
  - **Missing / broken controls.** Added Dividend Yield + Volume to the Stocks
    panel (server-side); the Funds "YTD Return" select was a duplicate bound to
    Change and is now a disabled "Not available" control; crypto category options
    come from JDDS sectors rather than a drifted hardcoded list.
  - **Sector/industry taxonomy repaired.** New `src/lib/screener/taxonomy.ts`
    collapses synonym labels across import sources ("Financials" → "Financial
    Services", "Consumer Discretionary" → "Consumer Cyclical", "Layer 1 (L1)" →
    "Layer 1", stablecoin sub-types → "Stablecoins"), applied on read, on filter
    (DB predicate matches every raw synonym) and on the option list. Sector/
    industry dropdown options are scoped to the active type filter (so ETF
    categories and the "Equity" asset class never leak into the Stocks dropdown),
    null classification is offered as "Unclassified" (matching the table cell,
    previously "Other" — a real crypto sector), and the combined Sector/Industry
    dropdown encodes its kind (`sector:` / `industry:`) because PK has names that
    are both. Every dropdown option now yields rows.
  docs updated: DATA-FLOW.md, ARCHITECTURE.md, CHANGELOG.md

- **Market screener — second pass (audit follow-up).**
  - **ATL distance used the ATH value.** `/api/stocks` mapped `atlChangePercent`
    from `athChangePct`; now uses the distinct `atlChangePct` column.
  - **Crypto supply/ATH columns sorted lexicographically** ("10.0B" < "2.0B").
    The client fallback sort uses a numeric accessor keyed on the raw values
    (`circulatingSupplyRaw`/`maxSupplyRaw`/`athChangePercent`), nulls-last.
  - **Small-cap boundary mismatch** (`>= 0` server vs `> 0` client) inflated the
    pagination total; the server now uses an exclusive lower bound.
  - **ETF/Fund directory silently capped at 100 rows** (asked for 500, API caps
    at 100, no footer). Both tabs are now genuinely server-paginated with a footer.
  - **ETF/Fund category dropdown collapsed** to the selected category; the full
    category list is fetched once and kept separate.
  - **Funds rendered fabricated zeros.** `ytdReturn`/`expenseRatio`/`rating` are
    now `null` and render `N/A` instead of `0.00%`/`0%`/zero stars (`FundItem`
    allows null).
  - **Markets-tab search box was dead** (bound to the unused stock search state);
    `useGlobalMarkets` now owns `gmSearch` and filters market cards.
  - **Country/Industry header sort** no longer uses the server (which ordered the
    raw, unnormalized column) — it falls back to client sorting so the visible
    order matches the displayed values.
  - Minor: Global Markets empty-state keeps the visible Forex/Commodities cards;
    `colSpan` and the "top N by …" caption reflect the active settings.
  docs updated: DATA-FLOW.md, CHANGELOG.md

- **Start commands fixed — `black eclipse` / `npm run up` no longer stall on a
  rebuild, and the doctor repairs in the right directory.** Two distinct bugs
  made the site *look* like it was not starting:
  - **Dev wiped the cached production build.** `next dev` deletes
    `.next/BUILD_ID` on start, which invalidated `scripts/lib/server.js`'s
    `needsBuild()` hash — so the next `black eclipse` / `npm run up` silently ran
    a full ~90s production build before serving (looked like a hang on the
    "site did not start" report). `next.config.ts` now sets `distDir` from
    `NODE_ENV` (dev → `.next-dev`, prod → `.next`, `NEXT_DIST_DIR` overrides), so
    a dev run can never clobber the production build. `.next-dev/` is gitignored.
  - **`doctor.js` ran its repairs with no cwd.** `root` was derived from
    `__dirname` for the checks, but `fix()`/`run()` exec'd `npm install`,
    `npx prisma generate`, pip installs, etc. in the caller's directory. Since
    `black eclipse` can be launched from anywhere via the global npm link, a
    repair triggered outside the site folder would fail or write in the wrong
    place. `run()` now pins `cwd: root` (matching `db-guard.js`).
  no doc change — start-script/config fix, no architecture or contract change.

## 2026-09-26

- **Memory Control Room + Skills patch panel UI polish (frosted-glass pass).**
  Brought the new M3/M4/M6/M8/M10 surfaces onto the shared frosted-glass system
  and added the missing interactions: the **Files** tab now has a side-by-side
  entry preview, a stale-safe inline **entry editor** (`expectedVersion` guard),
  a **revision history** list with one-click rollback and a colour-coded
  **diff**; the **Sessions** tab has a session **detail modal** (bounded summary
  with objectives/next-actions/instrument chips + the indexed transcript) and an
  explicit **Open** action; the **Providers** tab renders per-provider cards with
  health/latency/version and capability chips (native vs external), and states
  honestly when external search is policy-disabled; the Skill **patch version**
  panel gained an `EvalBadge`, active/canary chips, a colour-coded operation
  diff, evidence/regression chips, and action gating (canary → promote/rollback
  only; active/rolled-back → none). All new surfaces use `.glass-card` /
  `.glass-card-strong` / `.glass-card-subtle` (no raw `backdrop-blur`). Client
  file parsing is a small client-safe parser (the server keeps the authoritative
  one) so the screen never imports `node:fs`. Checks: Python **1067 passed**;
  `npx tsc --noEmit` clean; Vitest **1777 passed**.
  docs updated: CHANGELOG.md

- **Long-lived sessions, named profiles, file editing and the simplified Memory
  Control Room (spec milestones M3, M4, M6, M10).** Additive; no store merged,
  no dependency added, and isolation/safety invariants preserved.
  **M3 — named sessions.** New `ChatSession` table in `agent-memory.db`
  (id/profileId/userId/title/status/summary/sourceSessionId/createdAt/updatedAt/
  lastActivityAt/archivedAt); `HarnessRun` and `SessionMessage` gained
  `sessionId`/`profileId`/`projectId` (+ SessionMessage `market`/`skillId`/
  `memoryAction`). `RunRequest` gained `sessionId`/`profileId`/`projectId`; the
  front door forwards them. Session lifecycle: create/list/get/update
  (rename/pause/archive/restore)/fork/export/delete (archive default, hard
  clears only the search index, never the run trace). Session search ranking is
  now the documented hybrid (exact phrase > BM25 > decision/correction/
  skill-failure/memory-action > recency > prose) with filters for
  role/kind/session/profile/market/skill/memory-action. A bounded deterministic
  session summary (objective/decisions/unresolved/corrections/skills/memories/
  instruments/next actions) is built at run completion, persisted, and exposed —
  searchable but never auto-injected.
  **M4 — named profiles.** New `eclipse_memory/profiles.py`: a `ProfileRegistry`
  over `.black-eclipse/profiles/PROFILES.json` with per-namespace
  (memory/session/skill/provider), prompt profile, retention and settings, plus a
  directory projection (`PROFILE.json`, `sessions/`, `skills/`, `history/`,
  `exports/`). Explicit READ-ONLY inheritance (personal → project) with cycle and
  parent-delete guards. Cross-profile memory isolation is enforced on read.
  Routes `/profiles*`; TS client + a Profiles tab.
  **M6 — safe file editing.** `memory-files.ts` now writes `USER_PROFILE.md` /
  `MEMORY.md` / `PROJECT_MEMORY.md` / `SKILLS.md` (+ PROFILE/README), embeds a
  `version` in the stable entry marker, writes atomically (temp + fsync +
  rename) and backs up before a regenerate. New targeted-edit API with an
  `expectedVersion` stale-edit rejection and add/replace/merge/split/reorder/
  consolidate; new structured revision history (before/after/actor/sourceRun/
  reviewId/reason/affectedIds/parentRevision/timestamp) under
  `.black-eclipse/memory/.history/` with rollback and a bounded diff. Routes
  `/files/edit` and `/files/history` (GET history/diff, POST rollback).
  **M10 — Memory Control Room simplification.** Tabs are now Overview · Memory ·
  Sessions · Learning · Profile · Profiles · Providers · Files · Skills ·
  Policies · Diagnostics; Overview surfaces current profile, recent learning
  changes, pending reviews, active skills, recent sessions, provider health and
  rollback availability. Sessions/Providers/Files/Skills/Profiles tabs added.
  Tests: `test_sessions_profiles.py` (14), `test_sessions_profiles_api.py` (4),
  `memory-files-edit.test.ts` (8), plus browser-client additions. Checks: Python
  **1067 passed**; `npx tsc --noEmit` clean; Vitest **1777 passed**.
  docs updated: harness/architecture.md, harness/decisions.md (ADR-H56–H58),
  docs/DECISIONS.md (ADR-036), skills/ARCHITECT.md (ADR-035), NAVIGATION.md,
  harness/phase-3-memory-progress.md, CHANGELOG.md

- **Autonomous learning, memory-provider, skill-patch and prompt-cache upgrades
  (spec milestones M2, M7, M8, M9 + M1 scheduling).** All additive; no store
  merged, no dependency added, the Python harness stays authoritative, and no
  safety invariant was relaxed (the shared decision gate still governs every
  durable write; no skill is ever auto-activated; external results are never
  promoted to native).
  **M8 — first-class memory providers.** New package
  `python/harness/memory_providers/` (`protocol.py` = `MemoryProvider` contract +
  typed request/response with `provenance=external_provider`/`verified=false`
  defaults; `native.py` = the Eclipse-Memory provider; `mcp.py` = an MCP server
  as a read-only-first provider with L2 explicit-write gating and NO automatic
  writes; `registry.py`; `routing.py` = native-first routing that fences external
  results and never promotes them; `diagnostics.py` = bounded, secret-free
  provider health). Three new read-only tools `memory_search_native`,
  `memory_search_external`, `memory_provider_status`; policy keys
  `external_memory_search_enabled` (default off), `external_memory_write_enabled`,
  `external_memory_native_sufficiency`; routes `/memory-providers/status|search`
  + TS proxies/browser client.
  **M9 — prompt-cache segments.** New `python/harness/prompt_segments.py`: the
  prompt is split into immutable segments with content hash/version/source/token
  estimate, a stable `prompt_cache_key` composed only from identity (agent/
  policy/tool-schema versions + profile snapshot/skill manifest/session-summary
  ids — never the user message), selective bounded skill-manifest injection, and
  a `prompt.plan` observability event.
  **M2 — versioned self-improving skills.** New
  `python/harness/skills/patches.py` (JSON-pointer `replace|add|remove` patch
  parse/validate/apply; forbidden identity/permission/tool/risk fields; never-
  canary classification) and `skills/versioning.py` (propose → evaluate →
  canary → activate, atomic rollback preserving both versions, automatic
  rollback triggers). Migration 13 adds `baseVersion/patchSummary/reviewId/
  patchAuthor/activatedAt/rolledBackAt/canaryState/patch` to `SkillVersion`;
  new statuses `evaluating/canary/approved/active/superseded/rolled_back`; a
  stale-base patch is rejected. Routes `/skills/{id}/version-history`,
  `/skills/{id}/patch[/{version}/{evaluate|activate|promote|auto-rollback-check}]`
  + TS proxies and a patch-version UI panel.
  **M1 — idle-aware review scheduling.** `LearningReviewQueue` now supports
  priority ordering (critical→low), per-session coalescing, idle deferral while
  the user is active, and richer health; `LearningReview` gains
  `sessionId/profileId/priority/scheduling`. A `skill_patch` review outcome
  records a patch opportunity for a failed enabled skill (inert — no version is
  created).
  **M7 — hybrid ranking namespaces.** New `eclipse_memory/hybrid.py`: logical
  namespaces (preference/project_fact/correction/workflow/skill/session_summary),
  a bounded BM25 component, and a bounded hybrid score whose semantic term can
  only nudge an already-authorized memory. New labeled semantic cases (typo,
  profile-mismatch, temporal replacement).
  Tests: `test_memory_providers.py` (15), `test_prompt_segments.py` (12),
  `test_skill_patches.py` (13), `test_memory_hybrid.py` (7), plus scheduling
  tests and browser-client additions. Checks: Python **1050 passed**;
  `npx tsc --noEmit` clean; Vitest **1765 passed**.
  docs updated: harness/architecture.md, harness/decisions.md (ADR-H52–H55),
  skills/ARCHITECT.md, NAVIGATION.md, CHANGELOG.md

- **Memory Expansion — five Hermes-inspired capabilities on the existing
  architecture (M1 profile, M2 full-session recall, M3 automatic learning
  review, M4 file projection).** No store was merged, no dependency added, and
  the Python harness remains authoritative. **M1** adds
  `eclipse_memory/profile.py`, a deterministic, bounded materialized projection
  over active memory (USER/PROJECT sections; hard char/entry limits; excludes
  expired/superseded/rejected/archived, sensitive, financial-fact, other-user
  and mismatched task-scope content with reasons; memory text is sanitized and
  fenced as data). `graph.execute_run` builds the snapshot ONCE at run start and
  injects it as a separate non-authoritative `SystemMessage`, so a memory saved
  during a run is visible only to later runs. Migration 12 adds
  `MemoryProfileSnapshot` (reproducible metadata only — never content). Policy
  keys `profile_enabled` + the four `profile_*_budget_chars`/`_entries` keys.
  Endpoints `GET /eclipse-memory/profile`, `/profile/preview`, `POST
  /profile/rebuild` (operator-gated) + a Profile panel in the Control Room.
  **M2** adds a normalized, searchable `SessionMessage` table plus an FTS5
  mirror (`SessionMessageFts`) to `agent-memory.db`, an indexing helper
  (`session_index.py`) that redacts secrets and bounds content, read-only
  `session_search`/`session_open` tools in the default allowlist, prompt
  guidance ("historical content is context, not current evidence"), a
  deterministic LIKE fallback when FTS5 is unavailable, and
  `/session-search`, `/session-search/{runId}`, `/reindex`, `/health`,
  `/delete/{runId}` + a History tab. Policy keys `session_history_enabled`,
  `session_indexing_enabled`, `session_retention_days`,
  `session_search_max_results`, `session_search_include_tool_summaries`.
  **M3** adds `learning_review.py` (bounded in-process asyncio queue:
  1 concurrent, 20s timeout, one retry, duplicate coalescing, shutdown-safe;
  deterministic review reusing `analyze_run`; an optional bounded model review
  whose output is inert and re-checked by the shared gate) and a `LearningReview`
  audit table. No path bypasses the decision gate, activates a skill, or captures
  financial facts/secrets. Endpoints `/learning-review[/health|/run|/decide]` +
  a Reviews tab. **M4** adds `.black-eclipse/memory/{USER,MEMORY,PROFILE,README}.md`
  as an inspectable projection (render + parse in
  `src/lib/harness/memory-files.ts`), with explicit preview/apply/regenerate/
  backup/restore; imports reuse the existing gated `import_payload` pipeline.
  New tests: `python/tests/test_memory_profile.py`,
  `test_session_search.py`, `test_learning_review.py`,
  `src/lib/harness/memory-files.test.ts`. Checks: Python **989 passed**;
  `npx tsc --noEmit` clean; Vitest browser/file tests pass.
  docs updated: harness/phase-3-memory-progress.md, harness/architecture.md,
  harness/decisions.md (ADR-H51), NAVIGATION.md, CHANGELOG.md

## 2026-09-25

- **Memory: semantic-maturity pass — dedicated semantic evaluation, typed
  candidates, false-confirmation safety fix, optional stronger backend, review
  UX and operational controls.** Continued the memory work without changing the
  architecture (one `eclipse-memory.db`, one `EclipseMemoryService`, local
  single-user; `userId`/`scopeId` stay labels). **Phase 0** re-ran both evals and
  the focused suites, then found a real **false-confirmation bug**: two
  same-dimension statements that substituted a *value* ("reports as PDF" vs
  "reports as Excel", "quarterly" vs "monthly", "24-hour" vs "12-hour") were
  silently *confirmed* as the same statement, discarding the new value.
  **Phase 1** added a dedicated labeled set for cases lexical matching does not
  solve (`eclipse_memory/eval/semantic_v1.json`) plus a runner/CLI/release gate
  (`eval/semantic.py`, `eval/semantic_cli.py`) that reports lexical-only vs
  semantic-enabled vs combined, semantic candidate recall, false-candidate rate,
  confirmation/conflict-review accuracy, and absolute safety floors. **Phase 2**
  made the backend interface honest: `backend_status`/`backend_health`, an
  `auto` selector, and an optional `LocalEmbeddingBackend` that loads a
  sentence-transformer ONLY from an explicit local path (never downloads, never
  phones home) and falls back to the dependency-free `char-ngram` default (which
  the eval shows does not score unfamiliar paraphrases above a safe threshold).
  **Phase 3** typed candidates — `confirmation_candidate`, `conflict_candidate`,
  `replacement_candidate`, `unrelated_candidate`, `unavailable` — with only
  conflict/replacement actionable; similarity can never confirm, activate,
  supersede or archive. **Phase 4** fixed the confirmation safety bug with a
  deterministic `_value_changed` gate (same-dimension, both sides carry a
  distinctive token the other lacks, excluding reviewed synonym folds), tightened
  the `short`→`sell` synonym collision in `normalize.py`, and added the
  `same dimension, differing value requires review` reason. **Phase 5** added an
  optional (off-by-default) `semantic_recall_tiebreak` that reorders ONLY
  memories already carrying a lexical signal, preserving the lexical leader and
  never widening the eligible scope/status/expiry-filtered set. **Phase 6**
  extended `semantic_status` with bounded controls, backend health and bounded
  diagnostic counters, and added an operator-gated, honest
  `POST /eclipse-memory/semantic/rebuild` (v1 has no persistent index to clear).
  **Phase 7** distinguishes a semantic-candidate proposal from a saved memory in
  the chat panel. **Phase 8/9** added reliability coverage (missing/unavailable/
  timeout/exception backend, malformed score, bounds, reset/restore, disabled
  mode, no raw text in diagnostics, no network) and recorded that the
  deterministic lexical fix closed the measured semantic gap, so the optional
  backend stays off by default. Evidence: retrieval eval PASS (recall 1.0,
  precision 0.727, leakage 0, forbidden 0); contradiction eval PASS (recall 1.0,
  false-conflict 0.0, confirmation 1.0); semantic gate PASS (0 scope leak / 0
  unauthorized / 0 secret / 0 financial, lexical and enabled). Full Python suite
  and Vitest pass; `tsc` clean. No `jdds.db` change. docs updated:
  `harness/memory-contradiction-detection.md`, `harness/phase-3-memory-progress.md`,
  `NAVIGATION.md`, `CHANGELOG.md`.

- **Contradiction detection: deterministic normalization + optional local
  semantic candidates.** Closed the known lexical gap where a contradictory
  preference phrased with unfamiliar wording was missed. **Phase 1** added a
  human-labeled contradiction dataset + runner
  (`eclipse_memory/eval/contradictions_v1.json`, `eval/contradictions.py`,
  `contradictions_cli.py`) and recorded the baseline (recall 0.462, false-conflict
  0.111, confirmation 0.333; scope isolation/authority 1.0, zero unauthorized
  supersessions) in `harness/memory-contradiction-detection.md`. **Phase 2**
  improved the explainable lexical layer: `normalize.py` gained reviewed
  `CONCEPT_AXES` with polarity + negation windows, explicit-replacement reuse,
  temporary-instruction exclusion, and subject-identity authority (two explicitly
  different subjects never link, even sharing value words). This alone raised
  recall to 1.000 with **zero** false conflicts and confirmation 1.000, so
  **Phase 3** added the optional local semantic candidate layer
  (`eclipse_memory/semantic.py`) that is **off by default**, dependency-free
  (default `char-ngram` backend), bounded (threshold, max candidates, max index,
  timeout), fail-safe (falls back to lexical), and authorization-neutral — it can
  only surface a possible contradiction for review, never supersede, activate,
  archive, delete, or bypass scope/privacy/authority. **Phase 4** persistence:
  the candidate outcome stores the new record inert (`proposed`) and records
  detector/version/score/candidate-ids/reason/authority as an audit event (no raw
  embeddings). **Phase 5** policy controls (`semantic_conflict_enabled`,
  `_threshold`, `_max_candidates`, `_max_index`, `_timeout_ms`, `_diagnostics`)
  plus `EclipseMemoryService.semantic_status()` and
  `GET /eclipse-memory/semantic-status` reporting `lexical` /
  `lexical+semantic` / `lexical+semantic-unavailable`. **Phase 6** UI: Lifecycle
  tab shows the detection mode and a possible-contradiction panel (detector,
  similarity, authority, "not active truth until confirmed"); the chat panel
  already renders an ambiguous conflict as "Not saved — conflicts with an
  existing memory". **Phases 7–8** expanded coverage (paraphrase, negation, typo,
  different subjects/scopes, authority floors, semantic-unavailable/timeout/
  low-score/backend-crash fallbacks, migration/reopen/backup consistency) with a
  release gate (zero scope leakage, zero forbidden recalls, zero unauthorized and
  automatic-over-explicit supersessions). Full Python suite **927 passed**;
  Vitest **1754 passed**; `tsc` clean. Contradiction gate PASS (recall 1.0,
  false-conflict 0.0); retrieval eval unchanged. No `jdds.db` change. docs
  updated: `harness/memory-contradiction-detection.md` (new),
  `harness/architecture.md`, `NAVIGATION.md`, `CHANGELOG.md`.

- **Customization / blue themes carry a blue sidebar** — The blue-family theme
  presets now ship a coordinated blue-tinted sidebar instead of the neutral
  charcoal: **Ocean** `#0b1a2a`, **Blueprint** `#0a1826`, **Crystal** `#101a2e`,
  **Midnight** `#10142a` (each tuned to its palette). Presets only override
  `sidebar` when it differs from the shipped default, so the green Eclipse
  default stays charcoal. Test added asserting each blue preset's sidebar
  blue-channel exceeds its red and round-trips through `normalizeTheme`. Vitest
  **1753 passed**, `tsc` clean.
  no doc change — preset data only; the sidebar-surface architecture is already
  documented in `docs/ARCHITECTURE.md`.

- **Memory retention & contradiction hardening (phases 1–7).** Made the two
  least-production-ready memory areas safe for the local single-user product.
  **Phase 1** traced every retention/conflict path and recorded the audit +
  baseline pin in `harness/memory-retention-conflict-audit.md` /
  `python/tests/test_memory_retention_conflicts_baseline.py`. **Phase 2
  (retention):** the sweep now runs automatically at runtime startup through the
  existing FastAPI lifespan (`main._lifespan` → `AgenticService.run_startup_maintenance`
  → `EclipseMemoryService.run_retention_maintenance`) — no new daemon/thread —
  and can never block boot. It is idempotent and observable via a new
  `MemoryMaintenance` table (migration 11: operation/ranAt/ok/inspected/expired/
  skipped/error) surfaced on `/eclipse-memory/health` and
  `GET /eclipse-memory/retention`. Confirming/renewing now refreshes
  `lastConfirmedAt` and extends/clears an automatic memory's `expiresAt` from
  `retention_days`; explicit memories are never given a policy expiry. A
  retention-policy change no longer risks mutating existing rows, and a duplicate
  write can no longer revive an expired/superseded/archived/rejected record.
  **Phase 3 (conflicts):** `_resolve_conflict` now actually uses authority —
  explicit replacement and explicit-over-automatic supersede (with an auditable
  old→new link), automatic-vs-explicit and two ambiguous explicit statements
  store the new record inert (`proposed`). Each decision records a concrete
  reason. **Phase 4 (detection):** `conflicts.py` is authority-aware, uses
  subject identity + `SUBJECT_ALIASES` + normalized (synonym/stemmed) tokens, and
  the opposing-pair table was tightened (removed the broad `\bdo\b` arm). Negative
  cases (candlestick vs line, unrelated overlaps, scope/subject separation,
  observation vs preference, temporary instruction) are pinned. **Phase 5 (UI):**
  the Control Room Lifecycle tab shows retention policy/last-sweep, expiry/last-
  confirmed/last-used/last-reviewed, supersede links, and Confirm-&-renew /
  Restore / Approve / Archive actions; an ambiguous conflict renders as
  "Not saved — conflicts with an existing memory" and never as a save. Migration
  11 is additive and preserves v10 data (reopen tested). docs updated:
  `harness/memory-retention-conflict-audit.md` (new),
  `harness/architecture.md`, `NAVIGATION.md`, `CHANGELOG.md`.

- **Settings › General rebuilt** — Removed the light/dark toggle (the app is
  dark-first; nothing else in the app ever switched it) and replaced the tab with
  real preferences. Added a **Start screen** control (Last screen / ChatBot /
  Command Center / Portfolio / Chart Workspace) backed by a new
  `src/lib/general-prefs.ts` store (`be_general_prefs_v1` + `be_last_tab_v1`):
  `resolveStartTab()` seeds the shell's initial tab and an explicit deep link
  still overrides it; `recordLastTab()` feeds the "Last screen" option. Added a
  **Behavior & Safety** card with "Confirm before clearing data" (on by default),
  now gating the Data & Storage clears/watchlist/portfolio/reset actions that
  previously wiped local data instantly with no confirmation. Updated the General
  rail/search terms and dropped the stale theme aliases. Tests: Vitest **1750
  passed** (+10), `tsc` clean. docs updated: `docs/ARCHITECTURE.md`.

- **Memory maturity — local, single-user personal memory (phases 0–9).** Matured
  the existing Eclipse-Memory subsystem without rewriting its architecture (one
  `eclipse-memory.db`, one service, one decision gate, one retrieval seam; no
  hosted accounts; `userId`/`scopeId` stay local labels). **Phase 0:** baseline
  documented in `harness/memory-maturity-baseline.md`. **Phase 1 (lifecycle):**
  migration 10 adds `lastConfirmedAt`/`lastUsedAt`/`lastReviewedAt`/`authority`/
  `statusReason`; `expiresAt` is now actually persisted; re-stating a fact
  refreshes confirmation; retention (`expire_due_memories`) only ever expires
  **automatic** memory; add `restore_memory`/`renew_memory`/lifecycle views; no
  hard deletes. **Phase 2 (contradictions):** new `conflicts.py` — explicit
  replacement supersedes the old record (linked, retained), an ambiguous
  contradiction is stored inert (`proposed`), and two contradictory preferences
  never coexist as active truth; scope isolation is authoritative; a retrieval
  safety net recalls only the highest-authority truth. **Phase 3 (retrieval):**
  new `normalize.py` (human-reviewed synonyms, light plural stemming, subject
  aliases, bounded edit-distance-1 typo tolerance) behind the existing seam; the
  labeled set grew to 21 cases (typo, multi-turn, ambiguous, conflict, expired)
  with release thresholds (`check_thresholds`). Synonym recall 0.5→1.0, typo
  0→1.0, overall recall 0.9→1.0, forbidden 0, leakage 0. **Semantic/embedding
  retrieval deliberately deferred** (the eval shows no measured need; no new
  dependency/network service). **Phase 4 (Control Room):** `explain_memory` (why
  a memory exists + its recall disposition) on the memory detail API, a
  `/eclipse-memory/lifecycle` view endpoint, and a Lifecycle tab + explanation
  panels in the UI. **Phase 5 (transfer):** new `transfer.py` — readable JSON
  export, validated import through the same decision gate + write pipeline with
  `imported` provenance, atomic backup (never overwrites), stronger database
  health, and a memory-domain-only reset requiring explicit confirmation (skills
  and unrelated data survive). **Phase 6 (privacy):** policy gains
  `memory_enabled` (hard off), `memory_in_diagnostics`,
  `semantic_indexing_enabled` (recorded intent; no effect), and per-category
  `capture_policy`/`recall_policy` (can only tighten); safety floors hold.
  **Phase 7 (skill quality):** new `skill_quality.py` derives success/validation/
  tool-budget metrics, version regression, and advisory deprecation/promotion
  evidence from real executions; promotion stays evaluation + operator gated.
  **Phase 8 (reliability):** busy timeout, `integrity_ok`, honest 503/refusal
  outcomes, malformed-import reasons, atomic-interrupted-backup safety. **Phase
  9:** Python **841 passed**, Vitest **1742 passed** (136 files), `tsc` clean,
  eval threshold gate **PASS**. Migrations: 10 (additive, preserves v9 data). No
  `jdds.db` change. docs updated: `harness/phase-3-memory-progress.md`,
  `harness/memory-maturity-baseline.md`, `harness/architecture.md`,
  `harness/decisions.md` (ADR-H49), `NAVIGATION.md`.

- **Customization / dedicated sidebar surface** — The navigation rail no longer
  inherits the near-black `.glass-card-strong` fill. Added a `sidebar`
  `{tint,opacity,blur}` group to `EclipseTheme` (default dark charcoal `#1a1a1c`
  at 90% opacity — a touch lighter than the black page so the rail reads as
  separate chrome), emitted as `--sidebar-rgb/-opacity/-blur` structural tokens;
  `.sidebar-root` now has its own frosted recipe (with light-mode and
  `theme-glass-active/off` overrides so the generic glass rules can't win).
  A new **Sidebar** card in Customization › Theme offers five presets
  (Charcoal/Slate/Smoke/Crystal/Black), a tint swatch and opacity/blur sliders;
  `setSidebar` was added to the theme store. Tests: Vitest **1740 passed**
  (+4), `tsc` clean. docs updated: `docs/ARCHITECTURE.md`.

- **Reliability follow-up: close the operator-auth bypass, harden schema
  validation, fix retrieval word-matching.** Investigated the residual risks in
  the prior commit and fixed the confirmed defects. **(1) API authorization
  bypass (real):** memory/skill mutation endpoints in `main.py` trusted a
  caller-supplied body boolean `operator`, while only the MCP endpoints proved
  authorization by transport/token — so a directly reachable Python runtime (or a
  crafted proxied payload) could self-authorize memory writes, policy changes,
  suggestion accept/dismiss, skill author/enable/disable/deprecate/rollback and
  promotion. Added a `require_operator` FastAPI dependency (loopback or runtime
  secret, never the body) to every mutation endpoint; the Next.js clients now
  forward the runtime secret as `X-Harness-Operator`. **(2) Suggestion
  ownership:** API-level tests prove a caller guessing another scope's suggestion
  id is refused; listing supports `?scopeId=`. **(3) Schema fail-closed:**
  `jsonschema`-absent now fails closed (registration/evaluation/output) instead
  of a required-only fallback that reported partial validation as full; input
  validation stays pydantic/structural; `runtime-config.ts` + `doctor.js` probe
  the package and `GET /health` reports `skills.schemaValidation`. **(4)
  Retrieval:** `_score` matched substrings, so a query token `use` matched
  `User`; switched to word-boundary matching — eval precision 0.571 → **0.667**
  at recall 1.0, leakage 0, forbidden 0. Skill execution is not blanket-gated
  (a non-operator may run an enabled read-only skill), but the body `operator`
  flag that widens the actor is now honoured only with proven transport/token.
  **(5) Measured paraphrase gap:** the eval gained a labeled
  `synonym-paraphrase` slice (paraphrases sharing no lexical term) reported
  **per kind**, so a deterministic lexical retriever's limitation is measured
  rather than hidden; `recallSupported` (the exact+paraphrase slice it is built
  to serve) stays 1.0. No semantic dependency added — the eval is the evidence
  for whether one is ever warranted. Tests: Python **749 passed** (+20), Vitest
  **1736 passed**, `tsc` clean. No `jdds.db` change; existing data preserved.
  docs updated: `harness/architecture.md`, `harness/decisions.md` (ADR-H48),
  `harness/phase-3-memory-progress.md`, `NAVIGATION.md`

## 2026-09-25

- **Memory + runtime-skills reliability: enforced contracts, measured retrieval,
  isolated scopes.** Small, phased fixes on the existing architecture (no second
  loop, registry or database). **Contracts:** skill input/output are now validated
  as full JSON Schema (nested types, arrays, enums, `minimum`/`maximum`,
  `minLength`/`maxLength`, `pattern`, `additionalProperties`, required) via the
  already-present `jsonschema` (`skills/schema_validation.py`); schemas are
  self-validated at registration/evaluation with actionable errors; a run may
  `complete` while `outputValidated=false` and the violation is surfaced, never
  reported as validated. **Limits:** `manifest.limits.maxToolCalls` is carried
  into `AgentConfig.maxToolCalls` and enforced in `graph.tools_node` (refused
  with `TOOL_BUDGET_EXCEEDED`, audited, run finalizes) — no longer metadata/prose
  only. **Identity:** `SkillManifest.version_identity(instructions)` folds the
  procedure content into the persisted version identity; `registry.load_all`
  reports `skill.version_drift` when content changes without a bump (legacy
  manifest-only hashes accepted). **Retrieval:** added a versioned, human-labeled
  evaluation set + runner (`eclipse_memory/eval/`) recording baseline recall 1.0 /
  precision 0.5 / scope leakage 0 / forbidden hits 0; a deterministic lexical
  relevance gate stops off-domain/near-match queries from recalling unrelated
  topical memories (standing preferences exempt), with inclusion/exclusion
  diagnostics. **Isolation:** fixed a cross-user leak — `actor_scope="user"` with
  no `scope_id` returned every user's rows — and refused another user's
  suggestion accept/dismiss; `find_suggestion_by_signature` is scope-aware.
  **Docs:** corrected DB ownership drift (`eclipse-memory.db` = control memory +
  skill lifecycle; `agent-memory.db` = run/replay store) that several docs still
  attributed to `agent-memory.db`. No `jdds.db` change; existing user data
  preserved. Tests: Python 727 passed (+30), Vitest 1736 passed, `tsc` clean.
  docs updated: `harness/phase-3-architecture.md`, `harness/architecture.md`,
  `harness/decisions.md` (ADR-H45–H47), `DECISIONS.md` (ADR-026 + ADR-034),
  `NAVIGATION.md`
- **Memory + skills reliability — completion pass.** (1) Retrieval eval set
  expanded with topical exact/paraphrase, other-domain no-match and topical
  scope-boundary cases; added `python -m harness.eclipse_memory.eval` CLI and a
  pre/post measurable result — the lexical relevance gate lifts precision from
  0.125 (ungated baseline on the original set) to **0.571** at recall 1.0, with
  scope leakage and forbidden hits both 0. (2) Operator observability:
  `SkillExecution` (migration 9, additive) now persists `outputValidated`
  (tri-state) and bounded `metrics` (toolCalls/toolErrors/modelSteps/totalTokens);
  the Skills › Execution Activity panel shows the pinned version, manifest
  identity, validation result and tool usage alongside the existing warnings/
  missing data/limitations/evidence. Tests: Python 729 passed, Vitest 1736
  passed, `tsc` clean.
  docs updated: `harness/phase-3-memory-progress.md`, `NAVIGATION.md`

## 2026-09-24

- **Read-only-test findings - Issues 4, 5, 6 (plus 1 labelling)** - Fixed the
  defect-level findings from the reliability review. **Issue 6 (memory search
  `None`):** `eclipse-memory-screen.tsx` dereferenced `memory.confidence * 100`
  with no guard, so a row with a null confidence crashed the screen when the user
  typed in the search box; added `formatConfidence()` and used it in both render
  sites. `_score()` also formatted the raw importance/confidence (would raise
  `NoneType.__format__` for a partial dict); now formats the same defaulted values
  it scored with. **Issue 5 (news/evidence):** `WebResearchSource` now
  deduplicates results by a normalized URL (tracking params/fragment/trailing
  slash ignored) so the same article cannot inflate the evidence list; the tool
  summarizer now states the true total ("6 of N shown ... N-k more") so a bounded
  list never reads as silently dropped items. **Issue 4 (stale statements):** added
  `DEFAULT_CADENCE_SECONDS` (statements annual, earnings quarterly, macro monthly)
  and wired it through `layer.py`, so a currently-valid annual filing is
  DELAYED-by-design, not flagged stale by a 7-day window, while prices/quotes (no
  cadence) keep their strict windows. **Issue 1 (labelling):** workflow specs
  gained `requiresProvisioning` + `provisioningNote`; the four native-portfolio
  workflows now render as "unavailable" with the exact missing provisioning rather
  than a runnable job that cannot start. Tests:
  `python/tests/test_readonly_test_findings.py` (7) + updated `test_mcp_workflow.py`.
  1736 Vitest, tsc clean. (One unrelated Python failure remains from a concurrent
  `prompts.py` edit vs `test_graph.py`; not this change.)
  docs updated: `docs/CHANGELOG.md` - fixes restore declared behaviour; no
  contract/architecture change (new optional fields only).

## 2026-09-24

- **Retrieval health — one instrumentation seam for every capability** — Fixed
  the confirmed Issue 2 defect: health was recorded ONLY inside `liveQuote`, so a
  US-equity quote served via `market_snapshot` and every fundamentals / filings /
  news / price-history / macros route never reached the ledger (crypto/FX were
  recorded only because they route through `liveQuote`). `fetchCapability` now
  wraps `dispatchCapability` and records every data-fetching capability once at
  the boundary, deriving the canonical route key
  (`source × market × assetClass × capability`) from the result's provenance,
  an explicit `healthContext` on failure, or per-capability defaults; instrument-
  less routes (news/web) use the existing `*` wildcard. Introspection routes
  (health/coverage/capability_matrix/macro_resolve/secret) are excluded so they
  cannot record themselves. `liveQuote` no longer double-records. The report
  adds explicit `attempted`, `reliability`, `retryable` and `lastAttemptAt`
  while preserving `unknown` for zero-attempt routes. Deliberately did NOT add
  last-success/last-failure columns (would require a seed-DB migration); that is
  documented as a follow-up. New test `data-bridge-health.test.ts` proves a
  market_snapshot quote records, a failure records as failure, introspection
  routes do not self-record, and macro keys to its asset class. 1736 Vitest, tsc
  clean. (Python suite has one unrelated failure from a concurrent `prompts.py`
  edit vs `test_graph.py`; not this change.)
  docs updated: `docs/CHANGELOG.md` only — internal instrumentation; the health
  report fields are additive and the route-key scheme is unchanged.

## 2026-09-24

## 2026-09-24

- **MCP product layer — finance workflows, provenance, diagnostics, approval
  clarity** — Turned MCP from "servers and tools" into finance jobs an investor
  recognises. Added `python/harness/mcp/presets.py`: 11 finance **integrations**
  (Sheets, Excel, filings, web search, calendar, cloud docs, Canva/Figma/Office
  decks, Notion) with plain-language setup, `verified`/community flags and
  read/write tool-name hints, plus 7 **workflows** (Import Portfolio, Review
  Portfolio Risk, Prepare Earnings Brief, Compare Companies, Analyze Trade
  Journal, Create Investment Memo, Export Portfolio Report) with per-step
  integration, native-vs-MCP marking and approval steps. Added
  `python/harness/mcp/diagnostics.py` (command/Node/npx/Python availability,
  vault secret refs, endpoint safety+reachability, connection, discovery,
  selection, writable-temp-dir) each with an actionable `recovery`. Every MCP
  result now carries a machine-readable `provenance` block (`verification:
  external`, `eclipseVerified: false`, source, retrievedAt) and the text says
  "EXTERNAL … NOT Eclipse-verified"; native JDdS/portfolio data stays
  authoritative and workflow native steps are marked. Effectful approvals record
  a plain-language `actionSummary`, `affectedData` and `risk`; the UI shows them
  and uses "Approve this exact call". New runtime routes `/mcp/integrations`,
  `/mcp/workflows`, `/mcp/diagnostics` + TS proxies + a workflow wizard and
  diagnostics panel in Settings › MCP Servers. `mcp-servers.example.json`
  corrected (`powerpoint-mcp` did not exist → `@mindstone/mcp-server-office`) and
  unverified remote templates flagged. Added `_testtmp.py` (Windows temp-dir
  resilience) and `python/tests/test_mcp_workflow.py` proving import → native
  analysis → report → approved export → provenance, plus a changed payload
  requiring a new approval. 685 pytest, 1732 Vitest, `tsc` clean.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H43), `docs/NAVIGATION.md`

## 2026-09-24

- **Eclipse memory + skill learning — persisted recurrence (limitations
  closed)** — Follow-up to the unified-learning-mode fix. Closed the two known
  limitations: (1) recurrence for durable-sounding conventions was inferred only
  from the bounded chat-history window, so a convention repeated after the window
  (or in a later session) was never learned; (2) implicit skill-workflow
  recurrence scanned only the 40 most recent runs, so a workflow repeated after a
  long gap was missed and the scan was O(recent runs). Fixes: a bounded,
  **signature-only** recurrence ledger — `MemoryRecurrence` (migration 8,
  `eclipse-memory.db`; `store.record_recurrence`/`recurrence_count`, pruned) read
  and written by `EclipseMemoryService.decide_turn` — and `LearningRecurrence` +
  `LearningRecurrenceRun` (`agent-memory.db`;
  `store.record_learning_recurrence`/`learning_recurrence`) with a per-(run,
  signature) guard so re-analysing a run does not inflate the count. Skill
  recurrence is now one indexed lookup (`skills.learning._recurrence_count`),
  with the bounded scan only as a fallback combined via `max`. No raw text is
  ever stored (digests only). New tests: recurrence across separate runs with
  empty history, survival across a service reopen, ledger idempotency, and a
  repeated workflow yielding a candidate with no chat history. Python 697
  passed; Vitest 1732 passed; `tsc` clean. (One unrelated pre-existing
  `test_graph.py` failure from the concurrent `prompts.py` edit that removed
  "Black Orbit Technologies".)
  docs updated: `harness/decisions.md` (ADR-H44), `harness/architecture.md`,
  `harness/phase-3-memory-progress.md`, `NAVIGATION.md`

## 2026-09-24

- **Eclipse memory + skill learning — one selective lifecycle (root-cause fix)** —
  Fixed memory/skill learning end to end, not just prompts. **Verified root
  causes:** (1) automatic learning was governed by three independent booleans
  (`auto_capture_enabled`/`auto_suggest_enabled`/`auto_candidate_detection`) that
  all defaulted **off**, so nothing was ever learned automatically and the product
  could only prompt; there was no `automatic_selective`/`ask_before_saving`/`off`
  model and defaults were contradictory across code/docs/tests (ADR-H35 "on" vs
  ADR-H37 "off"). (2) The gate emitted `run_only` instead of a distinct
  `history_only`. (3) An explicit "turn this into a skill" only set a flag — no
  candidate/draft was created, forcing a second "Learn from this run" click. (4)
  Implicit skill learning fired on a single multi-step run (no recurrence
  evidence). (5) The chat panel prompted on every eligible run.
  **Fixes:** `policy.py` now defines two mode keys — `memory_mode` and
  `skill_learning_mode` (`automatic_selective` default | `ask_before_saving` |
  `off`); the legacy booleans are **derived** (`derived_flags`) and neither stored
  nor settable; migration 7 records and removes stored legacy rows so the mode
  defaults govern for new and existing installs. In `automatic_selective` a direct
  user preference saves on first statement, a project convention requires
  recurrence, and one-off/task/question/market content is `history_only`/`ignore`
  — no per-run prompt; `ask_before_saving` stages an inert suggestion; `off`
  creates nothing. Decision outcomes are now `save`/`suggest`/`history_only`/
  `ignore`. An explicit skill request creates a real inert candidate + draft via
  `capture_from_run`+`propose_draft` at run end; implicit `successful_procedure`
  candidates require recurrence (recovered failures/corrections remain strong
  single-run evidence); nothing is ever enabled (evaluation + operator approval
  gate promotion). The chat panel now shows a learning line only for a genuine
  automatic capture or explicit draft. Tests: `python/tests/` updated across
  memory-selectivity, policy, reliability, skills-learning and skills-scenarios
  (positive + negative: auto-save of a durable preference, explicit remember
  regardless of mode, one-off/market values not saved, recurrence saves without
  confirmation, duplicate/correction behaviour, sensitive refusal, scope
  isolation, eligible-run-is-not-a-skill, explicit request → pending draft,
  repeated workflow → controlled candidate, no repetitive prompt); TS
  `memory-action.test.ts` covers draft-ready presentation. Python 672 passed;
  Vitest 1732 passed; `tsc` clean.
  docs updated: `harness/decisions.md` (ADR-H43; ADR-H35/H37 corrected),
  `harness/phase-3-memory-progress.md`, `harness/architecture.md`, `NAVIGATION.md`

## 2026-09-24

- **Harness Phase 5D — remote MCP transport (Streamable HTTP + vault auth + SSRF
  guard)** — Users can now connect **remote** MCP servers, not just local stdio.
  `MCPServerConfig` gained `transport: "stdio"|"http"` (+ required `url` and
  optional `auth: {kind, name, prefix, secretRef}`); the HTTP path uses the MCP
  SDK's Streamable-HTTP client and shares the SAME connection lifecycle,
  discovery, effect/approval gating, output bounding and redaction as stdio
  (only the stream source differs). Auth is a **vault secret reference** resolved
  at connect time and added to the in-memory redaction set — never stored,
  returned, or logged. Every remote URL passes an **SSRF guard**
  (`python/harness/mcp/ssrf.py`, mirrored by `checkOutboundUrl`): https-only
  (loopback http allowed for local testing), embedded credentials refused,
  private/link-local/metadata hosts refused, checked BEFORE any outbound
  connection. Settings › MCP Servers gained a transport selector + URL/auth
  fields; `mcp-servers.example.json` gained a remote template. New offline
  end-to-end test `python/tests/test_mcp_http.py` (local Streamable-HTTP fixture
  requiring the vault-resolved bearer). Interactive OAuth, TLS/redirect knobs,
  resources/prompts (5I), MCP-aware source planning (5F) and Eclipse-as-server
  (5H) remain future work. MCP suite green; `tsc` clean.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H42), `docs/NAVIGATION.md`

## 2026-09-24

- **MCP — ready-to-use investor server examples** — Added
  `mcp-servers.example.json` (committable; no secrets) with verified installable
  local stdio servers investors can enable: `filesystem`, `notion`
  (`@notionhq/notion-mcp-server`), `sheets` (`mcp-google-sheets`, service-account
  or OAuth JSON), `excel` (`@negokaz/excel-mcp-server`), `tavily`
  (`tavily-mcp`), `brave` (`@modelcontextprotocol/server-brave-search`),
  `yahoo-finance` (`yahoo-finance-mcp`), `memory`
  (`@modelcontextprotocol/server-memory`). Credentials use `secret_refs`
  (vault-backed), never inline values; every server defaults to disabled with an
  empty selection. Documented in NAVIGATION + architecture. Note: Canva and
  hosted Google Workspace MCP are **remote/OAuth-only** and need the
  still-unimplemented remote transport (5D); Notion/Sheets are reachable today
  via their local stdio servers. `no doc change` beyond the rows below — this is
  a config example plus navigation pointers.
  docs updated: `docs/NAVIGATION.md`, `docs/harness/architecture.md`

## 2026-09-24

- **Harness Phase 5 MCP — vault secret references + effectful-tool approvals
  (5G)** — Closed the two follow-ups from the MCP audit. **Secrets:** added an
  encrypted named-secret vault (`src/lib/harness/mcp-secrets.ts`, AES-256-GCM in
  JDDS `SystemConfig` `mcp_secrets_v1`) exposed only as names/masked hints
  (`/api/harness/mcp/secrets`); a server references a secret by name
  (`MCPServerConfig.secret_refs`) and the Python runtime resolves the value at
  spawn over the authenticated bridge (`mcp_secret_resolve`), never persisting,
  logging, returning, or leaving it redaction-unaware (a resolved value joins the
  connection's in-memory redaction set). **Approvals (5G):** a `write`/
  `external_action` tool now needs (a) the operator to enable that effect for the
  server (`enabled_effects`, default `["read"]`) and (b) a valid APPROVED
  approval bound to the exact `(serverId, tool, argsDigest)`; enforcement is in
  the ONE `ToolRegistry` via a `ToolContext.authorize_effect` seam — with no
  authorizer, non-read tools stay refused. New `python/harness/mcp/approvals.py`
  (`McpApproval` table in `agent-memory.db`, no secret material, expiry,
  digest-change invalidation, terminal denial, `unknown` never approvable),
  `/mcp/approvals[/{id}/decide]` runtime routes + `/api/harness/mcp/approvals/*`
  proxies, and Vault + Approvals panels in Settings › MCP Servers. Remote
  HTTP/OAuth (5D), Eclipse-as-server (5H), MCP-aware native source planning (5F)
  and resources/prompts/subscriptions (5I) remain future work. 647 pytest, 1731
  Vitest, `tsc` clean.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H41), `docs/NAVIGATION.md`

## 2026-09-24

- **Harness Phase 5 MCP — audit & hardening** — Audited the shipped MCP slice
  and fixed five gaps. (1) **Default-agent reachability:** the Eclipse agent's
  exact allowlist omitted `mcp_*`, so selected MCP tools were registered but
  never bound; added a narrow `AgentConfig.allowMcpTools` opt-in
  (`schemas.py`/`agents.py`) expanded by `graph.effective_allowlist` to include
  only *currently registered* MCP tools — custom agents/skills keep exact
  allowlists. End-to-end graph test proves a selected tool is bound and callable,
  plus denial tests for unselected tools and restricted agents. (2) **Test-server
  teardown:** `MCPManager.test_server` now closes its temporary child in a
  `finally` (success/failure/cancellation); regression tests assert the child
  reaches `closed`. (3) **Credential security:** documented that scoped env
  values persist only in the gitignored `mcp-servers.json` (now written
  owner-only 0600 where supported) because the secure vault is a TS/Prisma store
  Python cannot read; added leak tests. (4) **Runtime auth:** replaced the
  body-`operator` boolean with a FastAPI dependency that authorizes MCP mutations
  by loopback or the runtime secret (`X-Harness-Operator`/Bearer), never a JSON
  field; the TS proxy sends the secret and no longer trusts a client boolean.
  Direct-API tests cover unauthorized/loopback/token paths. (5) **Effect trust:**
  a server's `readOnlyHint` is untrusted and no longer activates a tool on its
  own — activation requires an operator `tool_effects` declaration or an operator
  confirmation of the server's `catalogDigest` (`POST /mcp/servers/{id}/confirm`);
  a changed catalog invalidates the confirmation (ADR-H40). Also added stdio
  boundary tests, an MCP-awareness paragraph to the prompt, and reconciled the
  root `AGENTS.md` JDdS rule (JDdS is one fallible source; MCP is user-directed).
  Remote HTTP/OAuth, effectful approval, Eclipse-as-server, resources/prompts and
  MCP-aware native source planning remain future work (5D/5F–5I). 635 pytest,
  1724 Vitest, `tsc` clean.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H40), `docs/NAVIGATION.md`, `AGENTS.md`

## 2026-09-24

- **Live prices — read-through instead of 15-min scrape cadence (fix huge price
  delay)** — `/api/quote` served only the JDDS `Price` row, which the background
  scraper writes on a `DEFAULT_INTERVAL_MIN = 15` cycle, so every 30-second
  consumer poll (chart panels, header ribbon, portfolio) returned the same
  up-to-15-minute-old price. New `src/lib/scraper/live-quote.ts` adds a bounded
  read-through: for a non-index asset whose stored row is older than
  `STORED_QUOTE_FRESH_MS` (60s) it fetches the live price from Yahoo's chart
  `meta.regularMarketPrice` (one browser-UA HTTP request, no Python spawn), with
  a 15s shared cache + in-flight dedup so N clients share one upstream call; a
  failed fetch returns nothing and the stored row is served under its real
  `source`/`updatedAt` (never fabricated). The chart-fetch + ticker-candidate
  logic was extracted to `src/lib/scraper/yahoo-chart.ts` and shared with
  `/api/price-history`. Tests: `src/lib/scraper/live-quote.test.ts` (7). 1731
  Vitest, `tsc` clean.
  docs updated: `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`

- **Charts — timeframe-aware freshness (fix ~10–20 min intraday delay)** — Chart
  candles had two stacked flat 10-minute caches (client `DataSubscriptionManager`
  `BARS_TTL` and the server `HISTORY_TTL_MS`), and the client never re-fetched
  candles while a panel stayed open — only the live *last price* polled. Intraday
  series therefore lagged badly. Fix: a shared, pure `ttlForInterval`
  (`src/lib/chart/price-history-ttl.ts`) maps the Yahoo interval to a lifetime
  (1m→30s, 5m→60s, 15/30m→2m, 60m→5m, daily+→10m), used by both the route and
  the client; the client gains an intraday auto-refresh timer (`barsRefreshMs`,
  cleared when the last listener leaves) and silent background refreshes no
  longer flash a loading state. Tests: `price-history-ttl.test.ts` +
  `subscription-manager.test.ts` (intraday refresh). 1724 Vitest, `tsc` clean.
  docs updated: `docs/CHANGELOG.md` only — cache-lifetime tuning, no contract or
  architecture change.

- **Harness Phase 5E — MCP catalog selection & settings UX** — Added the
  front-door catalog for MCP servers. Python now exposes `GET /mcp/servers`,
  `POST /mcp/servers`, `POST /mcp/servers/test`, `DELETE /mcp/servers/{id}` and
  `POST /mcp/reload` (operator-gated, secret-free), with `public_configs()` +
  a versioned per-server `catalogDigest`; `MCPManager.test_server()` does a
  no-persist connect/discover, `reload()` re-registers in place (dropping only
  the MCP tools it added, so native tools and a running process are untouched),
  and `ToolRegistry.unregister` was added. `upsert_mcp_config` preserves scoped
  env values write-only (`envKeys` keeps secrets across an enable toggle), and
  `MCPServerConfig` accepts camelCase (TS) and snake_case (config file). The TS
  front door adds `src/lib/harness/mcp-types.ts` + `mcp-client.ts` and
  `/api/harness/mcp/*` proxy routes; a new Settings › MCP Servers panel
  (`src/components/screens/mcp-settings.tsx`) lets an operator add/test/enable/
  disable/remove servers, review discovered tools with their effect classes, and
  select the read-only tools to activate — non-read/unparseable tools render
  disabled with the reason. `mcp-servers.json` is now gitignored (it may hold
  scoped env values). New tests: `python/tests/test_mcp_api.py` + config/reload
  cases in `test_mcp.py`. 614 pytest, 1718 Vitest, `tsc` clean.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H39), `docs/NAVIGATION.md`

## 2026-09-24

- **Harness Phase 5A–5C — MCP integration (local stdio vertical slice)** —
  Added `python/harness/mcp/`: a typed stdio server contract + host threat
  boundary (`config.py`: id, argv command/args, per-server env allowlist, cwd
  resolution, enabled state, per-tool selection, declared effects, bounded
  startup/catalog/call/output/concurrency budgets, secret redaction),
  collision-resistant namespacing + JSON-schema validation + effect
  classification (`naming.py`), the local **stdio client over the maintained MCP
  Python SDK** with bounded timeouts/cancellation/clean process-tree shutdown
  (`client.py`), and a `ToolRegistry` adapter + lifecycle (`manager.py`).
  Selected **read-only** tools register into the ONE existing registry, so
  validation, agent allowlist, read-only enforcement, timeout, cancellation,
  persistence and tool events stay authoritative; discovery is not activation
  (`enabled`/`selected_tools` default off), only `read` effects activate, output
  is bounded/redacted, and results are attributed to their server/tool and never
  labelled Eclipse-verified. Wired into `AgenticService` (FastAPI lifespan
  start/stop), exposed non-secret counts on `/health`, added `mcp` to
  `requirements.txt` + `doctor.js`/`runtime-config.ts` probes, and a
  deterministic offline test suite (`python/tests/test_mcp.py`, fixtures in
  `python/tests/mcp_fixtures/`). Remote HTTP/OAuth, settings UI, effectful-tool
  approval, Eclipse-as-MCP-server, resources/prompts/subscriptions and broad
  source-planner changes remain future work (5D–5I). 601 pytest, 1718 Vitest,
  `tsc` clean.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H38), `docs/NAVIGATION.md`

## 2026-09-24

- **Agentic coding roadmap** — Expanded the root implementation plan's Phase 7
  into a bounded coding-agent contract and staged acceptance gates for repository
  inspection, isolated edits, sandboxed checks, diff review, product controls,
  and evaluation; added a navigation pointer.
  docs updated: `docs/NAVIGATION.md` (root roadmap remains the detailed plan).

## 2026-09-24

- **Eclipse capability check** — Reviewed the registered agent/tool boundary and
  app/runtime availability to answer whether Eclipse can perform coding and
  filesystem work; no live model run was possible because the app timed out and
  the Python runtime was stopped.
  no doc change — read-only capability assessment; architecture unchanged.

## 2026-09-24

- **Market Regime — palette-only, no header control** — Removed the Market
  Regime button from the top bar entirely. The panel is now headless
  (`MarketRegimeControl` renders only the dialog, no trigger) and is mounted once
  by the shell (`stock-chat.tsx`); it opens solely from the global search entry
  (`page-market-regime` → `action: 'open-regime'`, handled in the shell) and has
  an explicit close (X) button. Open state remains shared via
  `useRegimeScopeStore.panelOpen`.
  docs updated: `docs/CHANGELOG.md` only — navigation entry unchanged, no
  architecture/data-contract change.

## 2026-09-24

- **Market Regime — discoverability + close** — The Market Regime panel is now
  reachable from the global command palette: a `page-market-regime` entry
  (`market regime`, `risk on/off`, `sentiment`, `breadth`, `volatility`,
  `aurora`) whose destination carries `action: 'open-regime'`; the shell opens
  the panel and returns before any tab switch (`stock-chat.tsx`). Panel open
  state moved into the shared `useRegimeScopeStore` (`panelOpen`/`setPanelOpen`)
  so the palette and top-bar control agree, and the panel header gained an
  explicit close (X) button plus a refresh button.
  docs updated: `docs/NAVIGATION.md` (regime row already covers the model), no
  architecture/data-contract change — palette entry + UI affordance only.

## 2026-09-24

- **Aurora → Market Regime** — Replaced Aurora's decorative 60/40 market+news
  blend with an explainable, interactive Market Regime model. New
  `src/lib/regime/` (`types.ts` contract, `scoring.ts` pure scoring/confidence/
  classification, `client.ts` DataHub hook, `store.ts` persisted scope,
  `visuals.ts` regime→shader mapping) and a single new JDDS-only contract
  `GET /api/regime?scope=&market=`. Five components (price & breadth,
  volatility/options, macro/risk, news/narrative, positioning) each expose score,
  weight actually used, availability, timestamp, source and confidence. Missing/
  stale inputs are excluded (never neutral); a missing core price/breadth input
  makes the reading UNAVAILABLE. Transparent taxonomy: Risk-on broadening /
  Fragile rally / Mixed / Risk-off / Narrative shock / Unavailable. The glow
  (`aurora-glow.tsx`) now consumes the regime (scope = selected market / US /
  global) and gains a `dim` scalar for low-confidence reads; it stays decorative
  (`pointer-events-none`). A new accessible top-bar control
  (`market-regime-control.tsx`, mounted in `top-bar.tsx`) opens a frosted-glass
  panel with regime/score/confidence/freshness, per-component contribution
  breakdown, "what changed since last update", drivers, and actions (Market
  Overview, news, Ask Eclipse via `be:ask-eclipse`, regime-change alert via
  `createQuickAlert`). Tests: `src/lib/regime/scoring.test.ts` (28). 1716 Vitest,
  565 pytest, `tsc` clean.
  docs updated: `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/OVERVIEW.md`,
  `docs/NAVIGATION.md`, `docs/DECISIONS.md`

- **Harness Phase 3-M — Memory selectivity (stop over-saving)** — Audited every durable-memory write path and reproduced the over-saving: the deterministic intent classifier treated a casual "I prefer concise answers" / "Always use X" as an explicit save, `auto_capture_enabled` and `auto_candidate_detection` defaulted ON, and the model `memory` tool could write directly through `service.write_memory` with no check against the actual user turn (a temp-DB fixture saved 5/9 ordinary turns). Fixes: a new **shared decision gate** `eclipse_memory/decision.py` with exactly four outcomes (`save`/`suggest`/`run_only`/`ignore`) and a single authorization entry point used by the deterministic turn path, the model `memory` tool (`authorize_proposal` re-checks the proposal against the user message; a model cannot authorize its own write), the UI save, corrections, and post-run analysis. Explicit "remember/forget/correct" remain dependable through a separate always-on path; a casual durable mention is at most an inert **suggestion** (new `MemorySuggestion` table, migrations 5–6) surfaced with Save/Dismiss and never recalled; financial facts (prices/valuations/earnings/predictions) and tool/document content can never become durable memory. `intent.py` now requires a directive verb for a save (no bare "I prefer"/"my preference is"). Policy defaults flipped **off** (`auto_capture_enabled`, `auto_candidate_detection`, new `auto_suggest_enabled`) with migration 5 deleting any persisted unsafe `true` override (recorded in `MemoryPolicyMigration`, observable in health/policy UI); other overrides and all existing records preserved. Recall now labels type/scope/provenance/confidence/verification/time and excludes low-confidence unverified rows. New APIs `GET/POST /eclipse-memory/suggestions[/{id}/accept|dismiss]` + TS proxies + a Suggestions tab in the Memory Control Room, and a `suggested` chat action. Tests: `python/tests/test_memory_selectivity.py` (27, incl. decision-quality fixtures with false-save and missed-explicit-save reported separately, and ambiguous forget/correct asks rather than changing several records) plus updated policy/tool/reliability tests and TS `memory-action` tests. Also closed the storage-budget limitation: `max_memories` (default 0 = unlimited) caps ACTIVE memories and a new unique save fails truthfully as `memory_full` ("memory is full — not saved") instead of auto-deleting user memory; exposed via `memory_budget()` on health/`/policies` and the Policies tab. 572 pytest, 1716 Vitest, `tsc` clean in the changed files.
  docs updated: `docs/harness/phase-3-memory-progress.md`, `docs/harness/decisions.md` (ADR-H37), `docs/harness/architecture.md`, `docs/NAVIGATION.md`

## 2026-09-24

- **Harness Phase 3-M Reliability & Learning UX** — Made the memory→skill loop dependable. Verified root causes: (1) `eclipse-memory.db` defaulted to `<cwd>`, so the repo held two databases (root: memories+skills; `python/`: skills only, schema v3 vs v4) and a runtime launched from a different cwd read/wrote a different store; (2) memory capture relied on the model voluntarily calling `memory` and auto-capture was off by default; (3) auto candidate detection was off and "Learn from this run" only appeared around skill runs; (4) drafts were manifest-only (`instructions: None`); (5) chat could discover/view skills but not invoke one. Fixes: **stable path** repo-rooted (`eclipse_memory/config.py` `repo_root`/`db_identity`, `persistence.py`), `ECLIPSE_MEMORY_DB_PATH` override, non-secret identity on `/health`, non-destructive legacy reconciliation (`db.reconcile_legacy`, INSERT OR IGNORE, source never deleted). **Deterministic intent** (`eclipse_memory/intent.py`) wired pre-model in `graph.execute_run`: explicit save/forget/correct/skill detected regardless of model tool choice; secrets/sensitive IDs/raw dumps/policy-overrides refused, unclear scope asks confirmation, forget/correct archive/supersede (never hard-delete). **Ordinary-chat learning**: `learning_eligibility_for_run` + `GET /learning/eligibility/{runId}` + "Learn from this run" on the chat surface; explicit "turn this into a skill" always yields an inert candidate (`skills/learning.py` `explicit_skill_candidate`). **Usable inert drafts**: `skills/draft.py` generates a real procedure, typed I/O, safe tools only, provenance, limitations, evaluation cases — stays `draft`/`not_evaluated`; no-evidence drafts state manual authoring required. **Controlled skill invocation**: `skill_invoke` tool + `invoke_skill_from_run` runs enabled compatible skills through the existing `execute_skill` with `parentRunId` and enforced allowlist/permissions. **Automatic learning**: `auto_candidate_detection` is now ON by default (safe: inert candidates only, signature-deduplicated, promotion stays locked off), so a successful eligible run becomes a learning candidate without the user asking; the run's `memory` blob reports `autoCaptured`/`candidatesCreated`. **UI**: `memory` blob on `RunResult`/`client.final`, `MemoryActionPanel` (`src/lib/chat/memory-action.ts` + tests) shows automatic capture + the candidate count, Learning-Queue/Memory deep links. Prompt updated to be truthful about memory + skill invocation. New: `python/tests/test_phase3m_reliability.py` (32). 534 pytest, 1687 Vitest, `tsc` clean.
  docs updated: `docs/harness/phase-3-memory-progress.md`, `docs/harness/decisions.md` (ADR-H33…H36), `docs/harness/architecture.md`, `docs/NAVIGATION.md`

## 2026-09-23

- **Chat: Sources/provenance block is now muted and collapsed (reads as metadata, not the answer)** — The research panel previously used the same `text-foreground` colour and width as the answer prose and opened expanded, so it read as part of the answer. It is now a single collapsed disclosure: one always-visible header line (`status · N/N legs covered · N sources · N limitations`) with a chevron, expandable to Calculation → Limitations → numbered Sources → Research detail. Internals are greyed (`text-muted-foreground`/`-80`/`-70`), leaving the assistant prose the only full-brightness text; links keep the `text-primary` accent. Source numbering, tier/validation labels and `[n]` claim→source refs are unchanged. No evidence/retrieval logic touched.
  no doc change — presentation-only; the UI surface is already mapped in `docs/NAVIGATION.md`

- **Harness Phase 8 — reliability & global-research hardening** — Verified root causes from the international runs (SYS/RELIANCE/TATAMOTORS/TSMC/Petrobras/Samsung) against `agent-memory.db`. WS1: `get_capability_matrix`/`get_research_health` were registered but missing from `ECLIPSE_AGENT.tools`, so runs recorded `TOOL_FORBIDDEN` (`run_21c6307e…`) and fell back to `get_coverage` — added to the allowlist (read-only), and `get_coverage` now states recognised≠working, configured≠healthy, unknown/no-attempts≠failure, missing-JDdS≠stop. WS2: the graph passed its agent `toolTimeoutMs` as a hard override, so `research_search_news` (declared 30s) timed out at 20s (`run_7f5c48d5…`); a tool's own timeout is now authoritative with the agent value as a ceiling (`effective_timeout_ms`), news got a bounded 12s budget, and the timeout is recorded as a category. WS3: `SourceHealth` was keyed without capability, so a working quote shared a counter with an untested statement route; re-keyed `(source × market × assetClass × capability × probeKind)`, fixture probes labelled and excluded from live health, zero attempts stays `unknown`. WS4: new `retrieval/routing.py` gives the planner distinct categories (ineligible/not_implemented/unconfigured/provider_failure/no_instrument/no_data/…) and `capability.ts` now names each market's real regulator route instead of implying SEC. WS5: document handling distinguishes too_large/empty_response/javascript_only/unsupported_document/parse_failure, preserves title/document-id/publication/retrieval metadata, streams to a bounded 16MB, and refuses a value-less XBRL taxonomy. WS6: new `research/comparability.py` deterministically blocks incompatible comparisons (Tata demerger/ticker reuse, 9M-vs-12M, standalone-vs-consolidated, gross-vs-operations, unit/scale/currency, EPS restatement) with the exact reason. WS7: partial answers present every covered/qualified leg and name each blocked comparison. WS8: learning candidates carry the observed capability + a scoped regression case inside `scope`; still operator-gated. New: `python/harness/{retrieval/routing,research/comparability}.py`, `python/tests/test_phase8_reliability.py`, `src/lib/document-extraction.test.ts`, `src/lib/harness/phase8-health.test.ts`. Also fixed `scripts/test-python.js` to inject `PYTHONPATH` (the vendored interpreter ignores it) so `npm run test:smoke` resolves `harness`. 1678 Vitest + 498 pytest pass, tsc clean; live smoke: 3/3 routes reachable, SEC 8 NVDA periods.
  docs updated: `docs/harness/phase-4-progress.md`, `docs/NAVIGATION.md`

- **Chat: citations/provenance now render in a separate Sources section, not inside the answer** — The research answer prose no longer embeds an `Evidence cited:`/`Sources tried`/`Stopped because` footer or raw URLs; `_render_answer` returns the prose only, and citation/limitation/failed-route/stop-reason data is returned as structured fields (`metadata.citations`, `metadata.limitations`, `failedRoutes`, `stopReasonText`) carried on the `research` blob. The `ResearchEvidencePanel` was rebuilt into the requested order — answer, optional Calculation, always-visible Limitations, a collapsible numbered **Sources** list (`[1]` title · tier · period · currency · basis · published/retrieved · "View source"), then a collapsed Research-detail section (coverage/claims/conflicts/retrieval paths/receipt) with `[n]` cross-references from claims and coverage legs to their sources. Added `src/lib/chat/research-provenance.ts` (pure, unit-tested render model) and `build_citations` now emits period/basis/currency/unit/span — reporting a period only when the evidence states one unambiguously (a multi-period statement no longer labels its source with the oldest row's year). No evidence/retrieval logic changed.
  docs updated: `docs/NAVIGATION.md`

- **Fix: "No LLM provider is configured" after a server restart** — Root cause was NOT the LLM config (the `llm_config` row was intact): the native SQLite binding for `@prisma/adapter-better-sqlite3`'s NESTED `better-sqlite3@12.11.1` was missing, so every Prisma read failed and the settings vault in `jdds.db` was unreadable — which surfaced as "No LLM provider is configured" and blank startup diagnostics. Repaired with `prebuild-install` (the adapter's own install step) and hardened `scripts/doctor.js` to probe the exact nested package the adapter resolves and auto-repair that binding on boot, since `npm run dev`/`start` runs doctor but a direct `next start` does not. Verified: `[startup] LLM configured (ollama)`, `/api/settings` → provider ollama + hasApiKey true, `/api/harness/chat` → live reply.
  no doc change — operational fix; the boot/repair behavior is self-documenting in `doctor.js`

## 2026-09-23

- **Harness Phase 7 follow-up 2 — local official filing routes + bounded redirects** — Added a per-market `LOCAL_FILING_HINTS` registry (Taiwan MOPS, Korea DART, Japan TDnet, HKEXnews, India BSE/NSE, UK Companies House, Brazil CVM, Canada SEDAR, ASX, SGX, Bursa, SET, IDX, PSX, Tadawul …) used by the market-aware escalation query, and labelled those regulator/exchange hosts `primary`. Verified live: Korea DART fetches with `lang=ko` preserved. Fixed a transport gap where `safeGet` refused all redirects (official hosts commonly 301/302): added bounded, https-only redirect following that re-validates every hop through the same SSRF gate. Canada SEDAR is behind a ShieldSquare bot wall redirecting to an `http://` challenge, which the guard correctly refuses (documented limitation, not bypassed). 1648 Vitest + 464 pytest passed, tsc clean.
  docs updated: `docs/harness/phase-4-progress.md`

## 2026-09-23

- **Deep links: open pages in a new tab** — Added `src/lib/search/deep-link.ts` (every `Destination` ⇄ `?tab=…&sub=…&<params>` URL, with `/?symbol=AAPL` back-compat). The shell now boots from and keeps the URL in sync with the active tab and re-applies on back/forward. Sidebar nav items and command-palette rows are real anchors, so Ctrl/Cmd-click, middle-click and "open in new tab" work; the screener's new-tab pivot now uses the canonical chart link.
  docs updated: `docs/ARCHITECTURE.md`

## 2026-09-23

- **Harness Phase 7 follow-up — non-US financial statements are reachable** — `financial_statements` previously read only the committed `FundamentalsCache`, so a market without a snapshot returned `no_data` even though the keyless yfinance bridge serves it (verified: Samsung `005930.KS` returns full KRW statements). Added a live provider fallback that reuses the existing `getFundamentals` service (SEC → FMP → yfinance) and persists its result — no second pipeline. Corrected the capability matrix to report non-US fundamentals as `configured` when the keyless vendor is usable (it had understated real coverage), and made the JDDS source label the real provider instead of always "JDDS". Live-verified: `getFundamentals("005930","KR")` → yahoo/KRW 4 periods; `getFundamentals("2330","TW")` → yahoo/TWD 5 periods. 1633 Vitest + 460 pytest passed, tsc clean.
  docs updated: `docs/harness/phase-4-progress.md`

## 2026-09-23

- **Harness Phase 7 — global market research** — Made Eclipse non-US-centric. Verified root causes from real international runs (TSMC/Samsung/Petrobras): a spoofed browser User-Agent gets **403** from SEC, `www.sec.gov`, `data.sec.gov` and TSMC IR while a declared email-contact UA gets **200** (fixed in the shared fetch transport); the vault stores bare local codes (`2330`) while users type Yahoo suffixes (`2330.TW`), so non-US tickers returned `not_found` (fixed by suffix-aware identity); the retrieval planner attempted SEC for a non-US issuer (fixed by provider-eligibility gating); source-health collapsed runs to `(market, assetClass)` and duplicated rows (re-keyed by `source × market × assetClass`); `get_coverage` told the agent to stop when JDdS lacked a ticker (rewritten). Added a truthful capability matrix (`get_capability_matrix`), JSON/XML/XBRL passthrough + bounded text-PDF extraction (`unsupported_document`/`javascript_only` categories), market-aware escalation queries, and diagnostics/scope-linked learning candidates. New: `src/lib/harness/capability.ts`, `src/lib/global-research.test.ts`, `python/tests/test_phase7_{global,skill_feedback}.py`. 1630 Vitest + 460 pytest passed, tsc clean.
  docs updated: `docs/harness/phase-4-progress.md`, `docs/harness/architecture.md`, `docs/harness/decisions.md`, `docs/DECISIONS.md`, `docs/NAVIGATION.md`, `docs/GLOSSARY.md`, `skills/ARCHITECT.md`

- **Harness Phase 6 — resilient, multi-source research** — Structured failure diagnostics (`RetrievalDiagnostic`: provider/category/httpStatus/latency/timeout/resultCount/bytes/parse/retryable) replace opaque `UNAVAILABLE`; DuckDuckGo's HTTP 202 anti-bot page is now distinguished from a genuine zero-result search, and a valid `application/json` SEC response is accepted instead of rejected as "not HTML". Added independent routes behind the existing bridge: a direct, identity-gated SEC EDGAR statements source (`SecFilingsSource` → `sec_filings`) and an operator-configurable second search provider (vault keys `SEARCH_API_CONFIG`/`SEARCH_API_KEY`) beside the keyless DuckDuckGo default; `financial_statements` policy is `[SEC, JDDS, WEB]`. The research loop retries only transient failures with bounded backoff, switches providers, targets unresolved legs, preserves verified facts, and records a per-leg status + `stopReason`. Verified filing facts carry document identity into the receipt. Verified root cause of the NVDA web failures in the phase tracker. New: `src/lib/{retrieval-diagnostics,web-search}.ts`; `python/harness/retrieval/retry.py`; NVDA labeled eval (`research/eval/nvda.py` + `dataset_nvda_v1.json`); operator smoke (`research/smoke.py`, `npm run test:smoke`). 423 Python tests, 1617 Vitest, `tsc` clean; NVDA eval 5/5, 0 false accepts.
  docs updated: `docs/harness/phase-4-progress.md`, `docs/harness/architecture.md`, `docs/harness/decisions.md`, `docs/DECISIONS.md`, `docs/NAVIGATION.md`, `skills/ARCHITECT.md`

- **Command palette: stop surfacing registry actions in typed search** — The resolver no longer pushes registry actions (`Open Portfolio`, `Start new chat`, `Open Settings`, …) into ordinary results as `kind: 'action'`, which rendered a duplicate "Commands" group while typing. The top match is still exposed as `primaryAction` (Enter runs it) and action rows render only under the explicit `>` command scope. Follow-up to the earlier Commands-group removal.
  docs updated: `docs/ARCHITECTURE.md`

## 2026-09-23


- **Agent** — Expanded the implementation plan with the implemented evidence-grounded research flow and bounded web escalation, including validation, receipts, evaluation, and current limitations.
  docs updated: `agentic-plan-implementaion.md`

- **Agent** — Added the original financial harness implementation plan as a repository-root Markdown reference and linked it from navigation; retained the source plan as a vision document alongside the current harness docs.
  docs updated: `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Command palette: removed the executable Commands group; added agentic pages** — The ⌘K palette no longer renders static/fund/Settings "Commands" rows (`buildPaletteCommands`, `rankCommands`, `settingsCommands`, `fundOpenCommands`, `fundExportCommands`, `exportAllFundsCommand` removed; the `ExecutableCommand.run` side-effect path now covers only parameterized verbs like `alert AAPL`). Registered the agentic-mode pages `page-skills` and `page-memory` (with matching open actions, icons, and `skills`/`memory` AppTab) and included them in the palette's Pages launcher.
  docs updated: `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`

## 2026-09-23


- **Harness Phase 4 follow-up prompt** — Added a scoped OpenCode prompt for live-chat integration, coverage/hash hardening, receipt presentation, semantic evaluation, and source-backed restatement handling.
  docs updated: `docs/harness/phase-4-follow-up-opencode-prompt.md`

## 2026-09-23

- **Harness Phase 5 — bounded web escalation** — When structured sources are empty/stale/missing a requested fiscal period or lack required metadata, the research flow now escalates unsatisfied legs through a fixed hierarchy (structured → primary web → bounded secondary) via the existing `web_search`/`web_fetch` bridge, drawing from one `ResearchBudget`. Every numeric web fact must pass deterministic span-anchored validation; page text is untrusted. Fixed the NVDA failure root cause (evidence-packet truncation to the oldest fiscal year, missing-basis hard-fail, and WEB being unable to serve statements) generically for all entities. Coverage gained `qualified`/`no_matching_period`/`stale`; receipts carry escalation + budget; the evidence panel shows source tier/dates/period/span. Python 403 passed; escalation eval 8/8, precision 1.0, 0 false accepts; tsc clean.
  docs updated: `docs/harness/phase-4-progress.md`, `docs/harness/architecture.md`, `docs/harness/decisions.md`, `docs/DECISIONS.md`, `docs/NAVIGATION.md`
- **Harness Phase 4 follow-up — wire and harden in live chat** — Canonical period parsing (`research/periods.py`) replaces substring-of-digits matching; required unit/currency/basis/instrument metadata must be present to cover a leg; evidence/calculation ids are SHA-256 content digests (`research/ids.py`), reproducible across processes. A supported `financial_comparison` is routed into the evidence gate before the agent graph via a bounded, tool-less `ModelSynthesizer` (`research/{synthesis,run}.py`) and is never silently downgraded. Research metadata is additive on `HarnessRun`/`RunResult`, carried on `client.final`, rendered by `ResearchEvidencePanel`, and readable via `/api/harness/runs/[id]/receipt`. Versioned human-labeled semantic evaluation (`research/eval/`, accuracy 1.0, 0 false accepts) and source-grounded supersession chains (`research/supersession.py`, coverage `unavailable` until a provider supplies revision metadata). 371 Python tests, 1614 Vitest, tsc clean.
  docs updated: `docs/harness/phase-4-progress.md`, `docs/harness/architecture.md`, `docs/harness/decisions.md`, `docs/DECISIONS.md`, `docs/NAVIGATION.md`
- **Harness Phase 4 — evidence-grounded answering** — Added `python/harness/research/` (typed mandate + narrow classifier, per-leg coverage gate, structured claims + deterministic validator, pure-Python derived metrics, citations/response metadata, failure classes, durable receipt, orchestration engine) reusing the existing retrieval layer; additive `basis`/`publishedAt` and `asOf` on the retrieval contracts/cache; idempotent `ResearchReceipt` table in `agent-memory.db`; `/research/*` endpoints. 61 new tests; full suite 327 passed, tsc clean, Vitest 1613 passed.
  docs updated: `docs/harness/phase-4-progress.md`, `docs/harness/architecture.md`, `docs/harness/decisions.md`, `docs/NAVIGATION.md`
- **Harness Phase 4 plan** — Added the OpenCode implementation prompt and progress tracker for evidence-grounded research, coverage/citation gates, point-in-time evidence, deterministic metrics, and evaluation; mapped the phase in navigation.
  docs updated: `docs/harness/phase-4-opencode-prompt.md`, `docs/harness/phase-4-progress.md`, `docs/NAVIGATION.md`

**Who this is for:** anyone who wants to know *what changed, when, and whether
the docs were updated* — without reading git history.

This is a **required** artifact. Every task that changes the repository appends
an entry here, including changes that needed no doc update. It is the record that
proves the documentation obligation was considered rather than skipped.

## Rules

1. **Append, never rewrite.** Add new entries at the top of the log. Do not edit
   or delete past entries — a wrong entry gets a follow-up entry, not a rewrite.
2. **Newest first.** One `##` section per date, entries as bullets beneath it.
3. **Group by date**, not by commit. Multiple changes on the same day share a
   date section.
4. **Link the docs.** Each entry ends with either the doc files it updated or
   `no doc change — <reason>`.
5. **Keep it terse.** One bullet per change: what changed and why it mattered.
   The diff holds the detail; this holds the *narrative*.

## Entry format

```markdown
## YYYY-MM-DD

- **<Area>** — <what changed and why>.
  docs updated: `docs/<file>.md`
- **<Area>** — <what changed and why>.
  no doc change — internal refactor, contracts unchanged.
```

`<Area>` is a short label: `Docs`, `Scraper`, `Workspace`, `Journal`, `Agent`,
`UI`, `DB`, `Alerts`, `API`, `Search`, `Economics`, `News`, `Charts`, `Build`.

---

## 2026-09-22

- **UI / Navigation** — fixed a bug where switching menu modes would snap back
  immediately: the tab→mode sync effect now fires only when the active tab
  changes (tracked via a ref), so a manual Terminal/Agentic choice is respected.
  Swapped the Skills nav icon from `Sparkles` to `Blocks`.
  no doc change — bug fix + icon swap; the mode contract is unchanged.
- **UI / Navigation** — the collapsed sidebar now respects the selected
  Terminal/Agentic mode (previously it listed both modes' items); switch modes
  while collapsed with Alt+T / Alt+A.
  docs updated: `docs/OVERVIEW.md`, `docs/ARCHITECTURE.md`.
- **UI / Navigation** — reverted the Terminal/Agentic switcher to the original
  pill style (active `bg-primary/15 text-primary`, inactive muted with hover),
  removing the sliding gradient highlight.
  no doc change — presentation-only revert; the mode contract is unchanged.
- **Skills — user-authored skills** — users can now write their own skills from
  the Skills Library ("Add skill") and the agent can use them. A user skill is
  validated by the same pydantic manifest, may declare only the safe read-only
  permission set, must reference real tools, and is stored in eclipse-memory
  (`UserSkill`) then materialised into the same registry/`Skill`/`SkillVersion`
  tables as built-ins — so discovery, validation, execution and `skill_list`/
  `skill_view` all work unchanged. Editing creates a new version; built-ins are
  immutable; a skill with execution history is deprecated rather than deleted.
  New endpoints `GET /skills/authoring/tools`, `POST /skills/author`,
  `PUT/DELETE /skills/{id}/author` (+ TS routes) and an author form in the UI.
  docs updated: `docs/harness/phase-3-architecture.md`, `docs/NAVIGATION.md`.

- **UI / Navigation** — the sidebar now has two top-level modes, **Terminal**
  (market tools) and **Agentic** (ChatBot, Skills, Eclipse Memory), switched by a
  segmented control at the top of the menu and by **Alt+T / Alt+A**. The active
  mode lives in the shared sidebar store (`mode`) so the switcher, shortcut
  dispatch and palette/deep-link navigation stay in sync; ChatBot belongs to both
  modes. The switcher is hidden while the sidebar is collapsed, where all items
  stay reachable as icons. Made the Skills and Eclipse Memory screens full-width
  (dropped `max-w-6xl`) to match the other screens.
  docs updated: `docs/OVERVIEW.md`, `docs/ARCHITECTURE.md`.
- **Eclipse-Memory (Phase 3-M follow-up)** — added the configurable policy layer
  (`eclipse_memory/policy.py`, `MemoryPolicy` table) with validated bounds and
  locked safety values (automatic skill promotion can never be enabled);
  retrieval now honours policy budget/limit. Added a deterministic
  mistake-analysis service (`eclipse_memory/mistakes.py`) detecting tool
  failures, bad arguments, missing source, unsupported claims, undisclosed
  missing data, invalid schema, repeated failure, unresolved contradictions and
  timeouts. Added policy-gated automatic learning-candidate detection wired
  post-run (inert candidates only). New `/eclipse-memory/policies` and
  `/eclipse-memory/analyze/{runId}` endpoints + a Policies UI tab.
  docs updated: `docs/harness/phase-3-memory-progress.md`,
  `docs/NAVIGATION.md`, `docs/DECISIONS.md`.

- **Eclipse-Memory (Phase 3-M)** — built the dedicated memory subsystem. Added
  `eclipse-memory.db` + `python/harness/eclipse_memory/` (config, migrations,
  store, service, retrieval) as the one control layer for agent memory (typed,
  scoped, evidence-carrying, deduped, supersession-aware), corrections, mistakes
  and all skill/learning state. Added the `memory`, `skill_list`, `skill_view`
  tools on the existing registry (the tools the prompt had promised but that did
  not exist), and `graph.execute_run` now recalls scoped memory into every run.
  Migrated the Phase-3 skill tables out of `agent-memory.db` (idempotent import;
  `SkillStore` is now an alias for `EclipseMemoryStore` — one registry). Added
  `/api/eclipse-memory/**` + an **Eclipse Memory** UI tab. Rewrote the system
  prompt to name only real tools and state that skill creation/evaluation/
  promotion is operator-gated. No new runtime, registry, or DB driver.
  docs updated: `docs/harness/phase-3-memory-progress.md`,
  `docs/harness/architecture.md`, `docs/NAVIGATION.md`, `docs/DECISIONS.md`
  (ADR-026), `skills/ARCHITECT.md`.

- **Memory (Phase 3-M audit)** — completed Milestone 0 for the eclipse-memory
  rebuild: diagnosed why memory/skills don't work. Root causes: the harness
  system prompt (`python/harness/prompts.py`) describes a different product and
  promises `memory`/`skill_view`/`skill_manage`/`terminal`/`read_file` tools that
  are **not registered** (the registry has 13 retrieval/JDdS tools only); memory
  has no writer and is never recalled into a run (`graph.py:416` builds messages
  without memory); skills are not reachable from the agent runtime. No code
  changed — audit only.
  docs updated: `docs/harness/phase-3-memory-progress.md` (new).

- **Skills (Phase 3)** — added the Skill System: versioned `skill.json` +
  `SKILL.md` procedures executed through the **existing** Phase-1 `execute_run`
  graph. Python owns the registry, default-deny permissions, dependency
  resolution, execution, learning candidates, draft generation, deterministic
  evaluation, promotion gates and rollback; state persists in additive
  `agent-memory.db` tables. Added five initial skills, a Skills Control Room UI
  (library / detail / learning queue / evaluation center / execution activity /
  draft review), the workflow-ready `SkillExecutionRequest`/`Result` contract,
  and `/api/skills/**` + `/api/learning/**` proxies. Generated skills are inert
  until evaluated and explicitly promoted. No new runtime, tool registry,
  database, or schema library (pydantic reused).
  docs updated: `docs/harness/phase-3-architecture.md` (new),
  `docs/harness/phase-3-progress.md` (new), `docs/harness/architecture.md`,
  `docs/NAVIGATION.md`, `docs/DECISIONS.md`, `skills/ARCHITECT.md`.

- **Chat UI** — the transcript scroll container (`chat-history.tsx`) used
  `scrollbar-hide`, so a long thread gave no sign it could scroll. Added a
  visible, brand-coloured `.chat-transcript-scroll` scrollbar; it is hidden only
  while the viewport is pinned to the bottom (streaming follow), and revealed
  when the user scrolls up. Also added a floating "Latest" button that appears
  when scrolled away from the bottom and smooth-scrolls back down, and a
  `useLayoutEffect` that syncs the pinned/revealed state on first paint and on
  message changes.
  no doc change — UI affordance only; no architecture, contract, or data shape changed.

- **Retrieval — CPI/aliases, CME venue, FX self-consistency, statements class,
  source-health registry (#1–#6)** —
  • **#1 macro aliases**: `CPI`/`INFLATION` now AMBIGUOUS (headline vs core) with
    named candidates; every generic alias is enumerated by a test that asserts it
    resolves uniquely, is AMBIGUOUS, or is NOT_COVERED — never a silent
    single-measure pick. `PMI` etc. → NOT_COVERED. Index series carry `unitBase`;
    rows remain newest-first with `asOf`. The Python tool asks the TS
    `macro_resolve` (single alias table) before any local fallback.
  • **#2 unknown venue**: recognised-but-uncovered venues (`CME` → DERIV) return
    NOT_COVERED, not "unknown venue"; MIC carried on identity (`FFC/PSX` → XPSX,
    `SHEL/LSE` → XLON).
  • **#3 FX/crypto**: payload now says `served: live` and echoes the requested
    symbol (`EURUSD`, not `EURUSD=X`); quote direction preserved; no
    "not in the universe" warning beside a valid quote.
  • **#4 statements**: an instrument in the universe with no persisted statements
    is `no_data`, not `not_found` — agreeing with the quote path.
  • **#5 source health**: enumerates the full declared source registry
    (source × market × asset class) so a source with no runs reports `unknown`,
    not absent; 184 targets reported.
  • **#6**: warnings de-duplicated; a slow source cadence marks data "delayed"
    (a transformation, not a quality warning) so delayed ≠ stale.
  • TSM dropped from fixtures (Taiwan line is 2330; bare TSM → US is correct).
  Verified live: CPI→AMBIGUOUS, PMI→NOT_COVERED, ES/CME→NOT_COVERED,
  EURUSD→OK `served:live`, FFC/PSX statements→`no_data`, TSM→US.
  Tests: vitest 1593, pytest 170. tsc + eslint clean.
  docs updated: `docs/DECISIONS.md` (ADR-024), `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Retrieval — remove the residual US default in the agent tool path (#1/#2)** —
  The four retrieval tool handlers (`market_get_quote`, `market_get_ohlcv`,
  `fundamentals_get_company_profile`, `fundamentals_get_financials`) injected
  `market="US"` when the agent omitted it, so the bridge's ambiguity gate never
  saw an unqualified request — the real leak on the common agent path. They now
  pass `market=None`, and the tool descriptions no longer say "Default US."
  Regression test `test_no_tool_injects_a_default_market` asserts no resolving
  tool injects a market. Verified live: agent "price of FFC" returns both
  instruments and refuses to guess.
  docs updated: `docs/CHANGELOG.md`

- **Retrieval — unify resolution, remove every default, FX/crypto, source health,
  statements (#1–#9)** — The identity gate previously covered only the quote
  fallback path, so the defect survived on the common (unqualified) path and on
  a second, ungated resolution path. Now:
  • **One shared gate** (`resolveVaultInstrument`/`resolveAnyInstrument`):
  `market_snapshot`, `fundamentals`, `live_quote`, `price_history`,
  `financial_statements` all route through it; a tool-surface test fails if any
  resolving tool bypasses it (#1/#2).
  • **No default anywhere**: unqualified multi-listed tickers are AMBIGUOUS;
  `fundamentals("BHP")` can no longer silently return the US ADR; no
  `quality: valid` without identity (#1/#2).
  • **FX/crypto are first-class** (`classifyIdentifier`): `EURUSD` → FX with
  base/quote direction, `BTC-USD` → crypto spot; no country-universe error text
  (#5).
  • **Unknown venue → NOT_COVERED**, not AMBIGUOUS; identity carries exchange +
  MIC (`XPSX`, `XLON`, …) (#4).
  • **Macro**: generic `POLICY_RATE` is AMBIGUOUS even with a geography; rows are
  newest-first with explicit `asOf`; unit + currency + identity attached (#3).
  • **Freshness comparator** strict (`>`), unit-aware messages so a sub-day age
  is never "0 days" (#6).
  • **Source health populated** from the live path, per source × market ×
  asset class, with derived health/success-rate/staleness (#7).
  • **Financial statements persisted**: new `financial_statements` capability
  serves the `FundamentalsCache` snapshot (parse-once, deterministic) (#8).
  • **Conflict flag** exercised by a two-source fixture (#9).
  • Fixtures regenerated from the master (4160 cross-market, 289 cross-class,
  ADR lines, share classes, 28 exchanges).
  Verified live: `FFC`/`BHP` unqualified → AMBIGUOUS; `FFC/PSX` → Fauji
  Fertilizer PKR/XPSX; `EURUSD`/`BTC-USD` resolve; `macro POLICY_RATE` → AMBIGUOUS
  with candidates; `source_health` populated; `financial_statements AAPL` serves
  the persisted snapshot. Tests: vitest 1585, pytest 106.
  docs updated: `docs/DECISIONS.md` (ADR-023), `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Retrieval — deterministic replay, strict macro identity, top-level degradation
  (sections A4/A8, C4, D1–D3, E1)** —
  • **D1 determinism**: successful retrievals are persisted to a new
  `RetrievalRecord` table (`agent-memory.db`) keyed by request; an identical,
  non-realtime request replays the stored result — same figures, same citations,
  no read-time re-scrape. Realtime types are excluded by design. Added
  `save_retrieval`/`get_retrieval` and durable-replay logic in the layer.
  • **A8 macro identity**: `resolve_macro_series` (Python + TS) resolves a series
  to geography/institution/measure/adjustment/frequency. A generic measure
  (`POLICY_RATE`) without geography is AMBIGUOUS and never defaults to US;
  non-US series route to non-US sources (EA→ECB). New `macro_resolve` capability.
  • **C4 conflicts**: `_conflicts_payload` returns every candidate value with
  its source, not just a flag.
  • **D2 truncation**: `detect_incomplete` withholds partially parsed numerics
  (`1,23`), marking them invalid and the result `incomplete`/UNAVAILABLE.
  • **D3 top-level degradation**: `degraded`/`degradation`/`incomplete`/
  `conflicts`/`provenanceVerified` are result fields, never nested metadata.
  • **A4**: collision fixtures regenerated with share-class groups (distinct
  `ABR^D`/`ABR^E`/… lines) spanning 25 markets.
  • **E1 (report only)**: the store exposes `remember`/`recall`/`propose_skill`
  but NO tool registers them, so the agent cannot use them — a wiring gap, not
  a data defect; no code changed.
  Verified live: `macro_resolve POLICY_RATE` → AMBIGUOUS; `+geography=US` →
  DFEDTARU; `EA:ECB:DEPOSIT` → ECB source; FFC/PSX still PKR/PK.
  Tests: vitest 1582, pytest 104 (13 new). tsc clean.
  docs updated: `docs/DECISIONS.md` (ADR-022), `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Retrieval — uniform failure contract, declared coverage, terms-aware identity
  (sections A2–A8, B, C)** — The same underlying miss behaved differently across
  tools; a false "no news" shipped where the truth was an infrastructure miss.
  • **Failure taxonomy** (`lib/harness/failure.ts`): one vocabulary — ambiguous /
  market_unknown / not_found / currency_mismatch / venue_mismatch / terms_missing
  / not_covered / no_data / source_failure / incomplete / conflict /
  invalid_request — with message text *derived* from the class (B1/B2). `no_data`
  (covered-but-empty) is distinct from `source_failure` and `not_covered`.
  • **Venue is authoritative** (A2): `verifyProviderIdentity` rejects a currency
  OR venue mismatch; an unmappable provider venue is itself a failure. Fallback
  never crosses an identity boundary. • **Terms-aware identity** (A5/A6):
  derivatives need expiry/strike/right and fixed income needs maturity/coupon/
  seniority — otherwise `terms_missing` (UNAVAILABLE). • **Currency+units on every
  numeric payload** (A7). • **Declared coverage registry** (`lib/harness/
  coverage.ts`): queryable via a new `coverage` capability/tool; unregistered
  market/asset class → `not_covered` (C1). • **get_news fall-through** (C2): vault
  → shared web transport; source failure is never phrased as "no news".
  • **Source health derived** (C3): healthy/degraded/failing/unknown + success
  rate, so confidence is earned, not asserted. Verified live: `get_news("Pakistan
  fertilizer FFC")` now returns real web items (was "No news found"); agent flags
  a stale-vs-primary quote contradiction instead of picking one.
  Tests: vitest 1572, pytest 91; tsc clean.
  docs updated: `docs/DECISIONS.md` (ADR-021), `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Retrieval — canonical instrument identity + failure contract (fixes FFC/PSX
  returning a US fund's price)** — A ticker string was treated as an instrument
  identity. `market_get_quote("FFC", market="PSX")` returned a US closed-end
  fund's price stamped `realtime` because the live path discarded the market
  qualifier and fetched the bare ticker. The class is fixed, not the example:
  • **Identity layer** (`src/lib/instrument-identity.ts`): `resolveInstrument`
  resolves a ticker + qualifier against the master and returns a typed
  `{ market, symbol, currency (ISO 4217), assetClass }` — or a typed failure
  (`ambiguous` / `market_unknown` / `not_found` / `currency_mismatch`). It never
  guesses. • **Venue aliases** (`src/lib/markets.ts` `resolveMarketId`): `PSX`→PK,
  `LSE`→UK, `NASDAQ`→US, … so a venue qualifier is honored, and an unknown one
  fails loudly. • **No bare-ticker fallback**: `canResolveYahooSymbol` makes an
  unresolvable market fail instead of fetching a bare US ticker.
  • **Bridge** (`data-bridge.ts`) resolves identity first and returns
  `AMBIGUOUS` (with candidates) / `UNAVAILABLE`; it re-verifies the provider's
  currency/market and discards a mismatch. • **Python contract**: `AMBIGUOUS`
  status + `InstrumentIdentity` on objects/results; the layer treats it as
  terminal and the tool tells the agent to disambiguate, not guess.
  • **Permanent fixtures**: `instrument-collisions.json` generated from the real
  master (4160 cross-market tickers, 289 cross-class, multi-venue, share-class
  lines) with tests asserting the rule generalizes across countries/asset
  classes. Verified live: `FFC/PSX` → PKR/PK/`PK:FFC`; bare `FFC` → AMBIGUOUS;
  agent answers 540.51 PKR (was 15.54 USD).
  docs updated: `docs/DECISIONS.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Docs — add interactive architecture diagram for the agentic harness** — A
  self-contained, clickable HTML visualization of the front-door/runtime split,
  the LangGraph execution loop, and the retrieval pipeline, mirroring the
  frosted-glass UI recipe. Companion to `docs/harness/architecture.md`.
  docs updated: `docs/harness/architecture-diagram.html`, `docs/CHANGELOG.md`

- **Chat/UI — fix: duplicate React keys in the activity feed** — Console error
  `Encountered two children with the same key, retrieval:LIVE_STRUCTURED:macro_series`.
  The normalizer emits deterministic ids, so a run consulting the same source or
  tool twice produced duplicate activity ids and React duplicated/omitted rows.
  A new pure reducer (`lib/agent/activity-reducer.ts`) assigns each activity
  instance a unique id while a logical-id→instance stack preserves start→end
  correlation (LIFO, so overlapping runs resolve correctly); `use-agent-run`
  delegates to it. Five reducer tests added, including the exact duplicate case.
  docs updated: `docs/chat-ui-audit.md` §20, `docs/CHANGELOG.md`

- **Chat/Harness — fix: a failed turn bricked the conversation (400 on every
  send)** — Reported as "not getting output, something went wrong". The dev log
  showed repeated `POST /api/harness/chat[/stream] 400 INVALID_INPUT`. Phase 1
  changed failed/cancelled assistant turns to `content: ""` (with `status`), but
  the front door's history validator required non-empty content — so one failed
  turn made every following request in that conversation fail with 400.
  `validation.ts` now skips empty history turns (malformed roles still
  rejected), and `registry.buildPayload` + `stock-chat` omit empty turns client
  side. Verified live (200 on both chat paths with an empty turn in history);
  regression tests added.
  docs updated: `docs/chat-ui-audit.md` §20, `docs/CHANGELOG.md`

- **Harness — fix: retrieval source activity never reached the UI** — The chat
  activity feed could show tool steps but never the sources a retrieval tool
  consulted. Root cause: the run's `ToolContext` was built with a no-op
  `log` callback, so the retrieval layer's `retrieval.planned` / `source_start` /
  `source_ok` / `source_unavailable` events were discarded before reaching the
  emitter, trace or SSE stream. `ToolContext` now carries the run `emitter`,
  `retrieval_tools._event_logger` emits through it (falling back to `log` in
  unit tests), and an unused per-run layer in `service.run` was removed.
  Verified live: a quote query streams `retrieval.planned` + `source_start` +
  `source_ok`; a graph regression test asserts the events reach the bus.
  docs updated: `docs/chat-ui-audit.md` §20, `docs/CHANGELOG.md`

- **Chat/UI — Phase 6 performance, a11y & quality** — Found and fixed the
  hottest write in the chat: both surfaces serialized the whole transcript to
  localStorage on every streamed frame (~60×/s during a long answer). Streaming
  frames now update state only and persist once on the terminal turn (covering
  cancel/abort). Error turns are `role="alert"`; the status line stays
  per-phase (not per-token) so screen readers are not spammed; the activity
  disclosure gains `aria-controls`. Clean production build verified after
  clearing a `.next` that the running dev server had made flaky. Verified: tsc,
  eslint, vitest 1519, pytest 91, `npm run build`.
  docs updated: `docs/chat-ui-audit.md`, `docs/CHANGELOG.md`

- **Chat/UI — Phase 5 polish (touch-reachable controls, responsive toolbar)** —
  Audit found reduced-motion and frosted-glass already covered globally; the real
  gap was hover-only controls being unreachable on touch. Added a `.hover-reveal`
  utility (`@media (hover: none)` forces message actions, Edit, and code/table
  copy visible and tappable), made the Edit button always rendered instead of
  `hidden group-hover:flex`, let the action toolbar wrap on narrow bubbles, and
  gave the message row a stable `group` ancestor. No new animation; no global
  restyle. Verified: tsc, eslint, vitest 1519, dev reload.
  docs updated: `docs/chat-ui-audit.md`, `docs/CHANGELOG.md`

- **Chat/UI — Phase 4 financial-native rendering** — Improved how the agent's
  real Markdown output is presented (no fabricated structured blocks): numeric
  table columns are auto right-aligned with tabular figures and losses render in
  the loss colour; explicit unavailable markers (`UNAVAILABLE`, `n/a`, `—`)
  render as a muted chip rather than a value; headings like "Sources" read as
  quiet section labels and link-only lists render as a source list with the
  display host; external links gain a hover affordance + host tooltip. Scope
  decision recorded: the terminal output is plain Markdown and no evidence/url
  payload reaches the SSE stream, so metric cards/charts were not invented.
  Helpers are pure and unit-tested. Verified: tsc, eslint, vitest 1519.
  docs updated: `docs/chat-ui-audit.md`, `docs/CHANGELOG.md`

- **Chat/UI — Phase 3 agent activity & tool-execution UI** — Each assistant turn
  now shows what the agent did. A collapsible `ActivityFeed` renders every
  tool/retrieval step (human label, status, duration, result summary, failure
  code on expand); it auto-expands while the run is live and collapses to a
  summary line when done, with the expanded list capped so long tool runs cannot
  push the answer off screen. Retrieval result counts are shown only when the
  runtime reports them. The same components serve the dock (compact) and the
  full-page chat. No subagent/delegation card — the runtime emits no `agent.*`
  events (verified, not faked). Verified: tsc, eslint, vitest 1513, dev reload.
  docs updated: `docs/chat-ui-audit.md`, `docs/CHANGELOG.md`

- **Chat/UI — Phase 2 modern chat UX (copy, feedback, real provider, empty state)** —
  Code blocks now have a hover copy button and tables copy as TSV (spreadsheet-
  aligned). Assistant turns gained a persisted thumbs up/down. The composer's
  fake "Flash-Lite/Flash/Pro" model dropdown (it changed nothing) was replaced
  with the real configured provider label, and gained `aria-label`/`aria-busy`.
  The empty state is now financial-native example prompts (analyse a stock,
  compare fundamentals, sentiment, portfolio review) that fill the composer.
  Pure copy helpers moved to `lib/chat/markdown.ts` and unit-tested. Verified:
  tsc, eslint, vitest 1512, dev-server hot reload with live harness runs.
  docs updated: `docs/chat-ui-audit.md`, `docs/CHANGELOG.md`

- **Chat/UI — Phase 1 streaming foundation (typed lifecycle, activity, cancel)** —
  Built the shared response lifecycle the audit called for. A typed client model
  (`lib/agent/response-model.ts`) and one event normalizer (`lib/agent/events.ts`)
  now interpret the harness stream; a shared hook (`lib/agent/use-agent-run.ts`)
  owns status/streamed text/activities/cancel and is used by **both** chat
  surfaces, ending the duplicated streaming code. The UI now shows distinct
  states (planning / tool-running / streaming / completed / cancelled / error)
  instead of one "Thinking…", surfaces tool failures, and renders a recoverable
  error block with Retry. Text deltas are rAF-coalesced and assistant Markdown is
  memoized; auto-scroll only follows when the user is at the bottom. `Message`
  gained optional `status`/`activities`/`error` (legacy rows still load). No
  backend change — the runtime already emitted these events; the client stopped
  discarding them. Verified: tsc, eslint, vitest 1510, pytest 91.
  docs updated: `docs/chat-ui-audit.md`, `docs/CHANGELOG.md`

- **Chat/UI — Phase 0 audit & overhaul plan (no product code yet)** — Documented
  the current chat surfaces, the actual Python event vocabulary, the client
  status mapping, and the concrete UI problems with root causes. Key findings:
  only 5 of ~15 harness events reach the UI, tool failures are invisible, the
  `Message` model is too thin to express lifecycle, streaming rewrites the whole
  message array per token, and subagent/delegation events do not exist (Phase 3
  delegation is blocked on a backend capability — not fabricated). Proposed a
  typed response model + shared `use-agent-run` hook, normalizer, activity feed,
  and message actions, phased 1–6.
  docs updated: `docs/chat-ui-audit.md` (new), `docs/CHANGELOG.md`

- **Harness — the agent now streams its answer and always reaches one** — Two
  failures made the assistant look broken. (1) A research question returned
  `MAX_STEPS_EXCEEDED` after ~140s: local models loop on tools (even
  hallucinating a `terminal` tool) and never produce a final answer. The last
  allowed step now unbinds tools, appends an in-band "answer now" instruction,
  and strips residual tool calls; a forced turn with no text fails honestly
  instead of reporting a blank success. The same question now completes in
  ~44s with a full answer. (2) The chat was a blank spinner — the runtime now
  streams `model.astream` tokens as transient `model.delta` events over SSE
  (`/runs/{id}/stream` → `/api/harness/runs/[id]/stream` →
  `POST /api/harness/chat/stream`), and the UI shows live steps (`Thinking…`,
  `Using market_get_quote…`, `Writing…`) plus the answer as it is written.
  Verified live: 43 delta frames + a completed answer.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H13), `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Chat — conversation checkpoints (save/restore, like editor save points)** —
  You can snapshot a conversation at any point and roll back to it. Snapshots
  are JSON files under the session folder (gitignored), created/read/deleted via
  `/api/chat/checkpoints`; the chat state lives in the browser, so save/restore
  is client-driven. UI: a checkpoint control in both chat surfaces.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H14), `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Git — in-app plan → stage → commit → push** — Settings › Git reviews changes,
  stages individual files, drafts a commit message from the real staged diff,
  commits, and pushes — with push a separate, explicit action. The service runs
  git via `execFile` (argument arrays, never a shell string), resolves the real
  repo root so pathspecs are correct, refuses secret-looking staged paths
  (.env, keys, `*.db`, credentials), and never force-pushes.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H14), `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

## 2026-09-21

- **Analytics — daily consumption chart rendered no bars** — The bars used a
  percentage `height` inside an `items-end` flex row, whose columns are
  content-sized, so every bar collapsed to 0px. Columns are now full-height flex
  columns (`items-stretch` + `justify-end`) that give the percentage a definite
  parent, with a muted baseline for zero-token days.
  no doc change — layout bug fix, no contract or behavior change.

- **Investor Eye — big globe, country-name labels, 3D hover/click, new layers
  and skins** — Phase 17 presentation work plus source wiring. The globe camera
  is now derived from the live container box (`globeViewDistance`) instead of the
  hard-coded `globeRadius/distance`, so the sphere fills the shorter viewport
  dimension on any screen; `GLOBE_RADIUS` is the only modelling constant. Country
  names render as a shared label series (a `scatter3D`/`scatter` series at the
  curated `COUNTRIES` centroids) valid in both projections, toggled by a new
  persisted `showCountryLabels` flag (default on) with a `NAMES ON/OFF` control.
  The 3D globe gained per-country hover/click via a raycast onto the sphere
  (`countryIsoForPoint` + `countryOutlineRings`, `buildCountryIndex` bbox index),
  since echarts-gl's globe has no per-country geometry. Surface/emission textures
  are now 4096×2048 to kill zoom pixelation. Fires/shipping/commodities layers
  are wired to the layer route, the provider directory documents the keyless
  GDELT/USGS/FIRMS sources, quotes carry `Asset.sector` through to portfolio
  exposure, aggregated sources no longer report negative rejects, and two new
  theme presets (Bloomberg, Bubudoll) were added.
  docs updated: `docs/investor-eye-architecture.md`

- **Harness — restart a stale Python runtime on dev boot** — `ensurePythonRuntime`
  now reads `/health`'s `startedAtMs` and compares it to the newest mtime of
  `python/harness/*.py`. An orphaned uvicorn from a previous `npm run dev` (Windows
  child that survives the Next restart and holds the port) is detected only when
  the service identifies itself as `harness-runtime`, then killed via
  `netstat`/`taskkill` (or `lsof`/`kill` on POSIX) before respawn — so harness code
  changes take effect without clearing the port by hand. Unrelated services are
  never touched.
  no doc change — internal dev-runtime repair, contracts unchanged.

- **Chat — attach moved to "+", pause button mid-run, context meter, tighter
  footer** — Four fixes to the chat surfaces. (1) "Add docs" is no longer a
  separate button: the composer's "+" is the one attach affordance (both the
  full chat and the ChatDock), backed by a shared `use-session.ts` controller;
  the session bar is now display-only and hidden until files exist. (2) While
  the agent is running the submit arrow becomes a **pause** button: the client
  generates the run id and sends it with the request (the server only knows it
  after completion), then POSTs to `/api/harness/runs/[id]/cancel` for
  cooperative cancellation. (3) Added a **context-used meter** under the
  composer — `contextChars / contextLimitChars`, measured from real extraction
  (`measureContextChars`), never estimated. (4) Removed the extra bottom
  padding on the chat column so there is no dead gap under the session bar.
  Verified: `tsc`, eslint, 1478 TS + 89 Python tests pass.
  docs updated: `docs/ARCHITECTURE.md` (§ Chat session workspaces)

- **Chat — session workspaces, attached docs, full-width prompt bubbles and
  prompt editing** — Four linked changes to the Eclipse Agent chat surfaces.
  (1) User bubbles are now `w-fit max-w-full`, so a long prompt fills the
  column instead of wrapping early inside a fixed-size bubble. (2) Every user
  message gets an Edit affordance that truncates the thread at that turn and
  re-sends the edited prompt. (3) Each conversation now owns a real folder
  on disk (`.black-eclipse/sessions/<chatId>/{context,output}`): the new
  `session-bar.tsx` under the composer shows the path and a Context/Output
  file list with add/download/remove, backed by `api/chat/session` +
  `session-store.ts` (chat id validated as a path segment; traversal and
  dotfiles rejected). (4) "Add docs" is functional: `extract.ts` turns
  txt/md/csv/json/html/pdf into text, `/api/harness/chat` loads the
  conversation's context documents, injects them into `RunInput.documents`,
  and Python (`graph.py` `_user_message`) wraps them as attributed
  `<document>` blocks — the runtime stays read-only. The agent's answer is
  saved back as an output file. Root is gitignored. Verified: `tsc`, eslint,
  1477 TS + 89 Python tests pass.
  docs updated: `docs/ARCHITECTURE.md` (§ Chat session workspaces),
  `docs/NAVIGATION.md`

- **Harness Phase 2 — retrieval defect fixes (historical prices, macro, profile,
  warnings)** — End-to-end testing against the live bridge found four defects.
  (1) `market_get_ohlcv` passed its range ("6mo") to the bridge as an interval,
  so yfinance never ran the history path and every historical request returned
  UNAVAILABLE — fixed by classifying `quantity` into range vs interval in
  `retrieval/structured.py`. (2) The `fred-analytics` macro source emitted
  dynamic-header rows the normalizer could not read, yielding zero observations —
  now emits canonical `{ date, value }` (verified 318 rows). (3)
  `company_profile` returned an empty body because numeric-only conflict
  resolution dropped string facts — non-numeric objects now pass through. (4)
  Quality warnings were a blanket per-row staleness flag; staleness is now a
  dataset-level check and value warnings name the metric and reason. Verified
  live: AAPL history 126/251/1254 bars for 6mo/1y/5y. 98 Python + 1457 TS tests.
  docs updated: `docs/harness/phase-2-progress.md`, `docs/CHANGELOG.md`

- **Harness Phase 2 — Hybrid Financial Data & Web Research Layer** — Added a
  provider-agnostic `python/harness/retrieval/` layer: a unified
  request/result/evidence contract, a deterministic task-aware source-selection
  planner, structured sources (JDdS vault + live providers behind one
  `RetrievalSource` interface), first-class web research (search → rank →
  retrieve → provenanced evidence), normalization, a freshness-policy cache with
  in-flight deduplication, parallel retrieval with per-task timeout and error
  isolation, data-quality validation (negative earnings stay valid), explicit
  source-conflict preservation/resolution, and evidence aggregation. New tools
  (`market.get_quote`, `market.get_ohlcv`, `fundamentals.get_*`, `research.*`,
  `macro.get_series`) call the layer, never a provider. The TS bridge gained
  read-only `live_quote`/`price_history`/`macro_series`/`web_search`/`web_fetch`
  capabilities, and `src/lib/web-research.ts` is now the single shared
  search+fetch implementation (the legacy `search_web` tool delegates to it).
  Precise data (historical prices, macro series, derived metrics) is never
  web-sourced; the layer returns UNAVAILABLE instead of inventing a number. 83
  Python + 1456 TS tests pass; the 10 required scenarios are covered.
  docs updated: `docs/harness/phase-2-progress.md`,
  `docs/harness/architecture.md`, `docs/harness/decisions.md`,
  `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`

- **Chat — tables made minimal, header larger, no chrome** — The table
  rendered inside a glass container with an uppercase muted header, which read
  as a UI card bolted into the reply. Dropped the container/fill entirely: the
  table is now full-width and borderless except for a single hairline under a
  larger (`1.05em`), quieter header and faint row dividers — so it reads as
  part of the chat text. Verified: `tsc`, eslint, 1446 TS + 45 Python tests
  pass.
  no doc change — UI-only change, contracts unchanged.

- **Chat — GFM pipe tables now render, with a designed table surface** —
  Markdown tables were explicitly out of scope in the parser, so agent answers
  containing `| col | col |` rows showed as raw text. Added a GFM pipe-table
  branch to `src/lib/chat/markdown.ts` (header + `---|:---:` delimiter row,
  per-column left/center/right alignment, escaped `\|` support, inline
  formatting inside cells, and rows that stop at the first non-pipe line), 4
  new unit tests, and a styled renderer in `components/chat/markdown.tsx`
  (glass-card-subtle rounded container, uppercase muted header, row dividers,
  row hover, horizontal scroll for wide tables). Verified: `tsc`, eslint,
  1446 TS + 45 Python tests pass.
  no doc change — rendering change, contracts unchanged.

- **Chat — composer scrollbar restyled and shown only when needed** — The
  auto-growing composer revealed the global 6px thumb full-height against the
  text and action buttons as soon as content overflowed. Gave the composer its
  own `.chat-composer-scroll` treatment (5px, low-contrast brand tint, inset
  10px top/bottom margin, transparent track) and made the resize logic switch
  `overflow-y` to `auto` only when the content truly exceeds the cap, so no
  scrollbar flashes for content that fits. Verified: `tsc`, eslint, 1442 TS +
  45 Python tests pass.
  no doc change — UI-only change, contracts unchanged.

- **Chat — composer auto-grows and scrolls for long prompts** — The full-page
  `ChatInput` used a single-line `<input>`, so a long prompt stayed clipped with
  no way to review it. Replaced it with an auto-resizing `<textarea>` that grows
  with its content up to ~6 lines (`MAX_HEIGHT`), then scrolls; Enter sends,
  Shift+Enter inserts a newline, and the action buttons align to the bottom.
  The dock composer already behaved this way, so the two now match. Verified:
  `tsc`, eslint, 1442 TS + 45 Python tests pass.
  no doc change — UI-only change, contracts unchanged.

- **Agent / Analytics — token-consumption tracking + a Settings › Analytics page** —
  The harness discarded every LLM `usage` block, so token consumption was
  invisible. The Python runtime now reads usage per model call (`usage_metadata`,
  falling back to the OpenAI/Anthropic `response_metadata` blocks), sums
  `promptTokens`/`completionTokens`/`totalTokens` onto `HarnessRun` (new columns,
  added by an idempotent `_migrate()` on an existing DB), emits them on
  `model.completed`, and exposes `GET /usage` (totals, by-model, by-day, recent
  runs). A provider that omits usage records 0 and is counted in
  `totals.runsWithUsage` — never estimated (honesty rule). New Next.js proxy
  `/api/harness/usage` + `getUsageSummaryFromRuntime`, and a new Settings ›
  Analytics section (`analytics-settings.tsx`) showing windowed totals, a daily
  bar chart, per-model breakdown, and recent runs, with an explicit note when
  some runs did not report usage.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`, `docs/NAVIGATION.md`

- **Chat — assistant replies render Markdown instead of raw text** — The
  transcript printed `msg.content` verbatim (`whitespace-pre-wrap`), so the
  model's `**bold**`, `### headings`, lists and fenced code appeared literally;
  no Markdown renderer existed anywhere in the app. Added a dependency-free
  subset parser (`src/lib/chat/markdown.ts`, pure + unit-tested) and a view
  layer (`src/components/chat/markdown.tsx`) wired only for assistant messages
  in `chat-history.tsx` (user text stays raw). Handles headings, fenced /
  indented code, blockquotes, ordered/unordered lists, `hr`, links, and inline
  bold/italic/strikethrough/code. Degrades gracefully on partial streaming
  input (unclosed fences/markers stay text). Styled with the frosted-glass
  system, no new dependencies. Verified: `tsc`, eslint, 1442 TS + 45 Python
  tests pass.
  no doc change — UI/rendering change, no contract or architecture change.

- **Chat — the chatbot is now the Eclipse Agent (routed through the harness)** —
  The chat surfaces were calling `/api/agent/chat`, a bare completion passthrough
  (no system prompt, no tools), so replies were ungrounded and the Eclipse Agent
  was never used. Both chat surfaces (`stock-chat.tsx`, `chat-dock.tsx`) and the
  provider registry now route through the harness via a new `POST
  /api/harness/chat`, which runs the Eclipse Agent (prompt + JDdS tools + a
  persisted run) and returns its final text. The research-intent classifier and
  the separate `/api/agent/research` chat branch were removed for chat — the
  agent selects its own tools. Added multi-turn context: `RunInput.history`
  (TS + Python), bounded to 20 turns / 40k chars, threaded into the LangGraph
  message list; `chatWithAgent()` on the front door; a chat-appropriate rate
  limit (60/5min vs the run limit). Verified: "AAPL price" returned real JDdS
  data with provenance ($338.96, source JDdS/yfinance) via `get_market_snapshot`,
  and a follow-up recalled the prior turn. `tsc`, lint, 1426 TS + 38 Python
  tests pass.
  docs updated: `docs/harness/architecture.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`

- **ChatBot UI — wide layout, bubble-free assistant replies** — The Eclipse
  ChatBot page was a narrow centered `max-w-4xl` column and every assistant
  reply sat in a rounded glass bubble, unlike opencode/Hermes-style agents.
  Removed the width caps entirely: the transcript, composer and empty-state
  column now fill the full main-content width (only small edge padding), and in
  the full-page layout assistant text renders full-width with no bubble
  background/border (user messages keep their bubble). Compact ChatDock is
  unchanged. Follow-up: the composer is narrow (`max-w-3xl`, centered) in the
  empty state and goes full width once the conversation starts, while
  transcripts remain full width.
  Verified: `tsc`, 1426 TS tests, 38 pytest tests pass.
  no doc change — UI-only change, contracts unchanged.

- **Chat / Agent — fix "no LLM provider configured" for vault & local providers** —
  The chatbox (`POST /api/agent/chat`) always returned 503 when the LLM was
  configured through the Settings UI or was a keyless local server: both
  `OpenAICompatibleProvider.isConfigured()` and the startup flag in
  `instrumentation.ts` tested only `OPENAI_API_KEY`/`OLLAMA_BASE_URL`/
  `ANTHROPIC_API_KEY` env vars, ignoring the settings vault. Added
  `isConfiguredAsync()` (resolves the real config: vault key, env key, or a
  local base URL) and made the chat route use it; startup now resolves the
  actual config so the client picks the real provider instead of the mock.
  Verified: chat returns real completions and the research path runs against
  Ollama. No doc change — bug fix, contracts unchanged.

- **Harness — Eclipse Agent prompt installed; agents made Python-authoritative** —
  Added `python/harness/prompts.py` holding the full Eclipse Agent system prompt
  (Black Orbit Technologies identity; agent operating models, research,
  investment analysis, coding/financial engineering, execution discipline). The
  default agent is now `eclipse-agent` / "Eclipse Agent". Fixed a real defect:
  the front door previously sent its own `systemPrompt` copy, so the Python
  prompt was dead code and the two could drift — the front door now sends only
  `agentId`, and `resolve_agent()` in `graph.py` resolves the full `AgentConfig`
  (prompt + allowlist + limits) from Python presets. `GET /api/harness/agents`
  proxies the runtime; the TS side fetches + caches presets rather than defining
  them. Verified end-to-end that an `agentId`-only run delivers the
  23,687-character prompt to the model. `tsc`, lint, 1426 TS tests, 36 pytest
  tests and `next build` pass.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H8), `docs/harness/phase-1-progress.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`

- **Harness revised — agentic runtime moved to Python (LangChain + LangGraph)** —
  Retired the TypeScript Phase-1 kernel (`src/lib/harness/{types,models,tools,runtime,events,persistence,agents}`)
  and rebuilt the agentic side in `python/harness/` as a FastAPI service:
  LangGraph `StateGraph` agent⇄tools loop, a universal model factory covering
  native LangChain integrations (Anthropic/Gemini/Mistral/Groq) plus every
  OpenAI-compatible endpoint (Ollama/LM Studio/OpenRouter/DeepSeek/xAI/
  Perplexity/Together/Fireworks/custom), a pydantic-validated tool registry
  (permission/risk/timeout/duplicate-call), JDdS-backed read-only finance tools
  with honest UNAVAILABLE states, an event emitter + live bus, and
  `agent-memory.db` persistence (runs, events, tool executions, agent memory,
  skills). Next.js is now a thin front door: input validation, agent + LLM
  config resolution from the vault, a spawn/health-check launcher, a typed
  runtime client, and a guarded read-only JDdS **data bridge**
  (`/api/harness/data`) that keeps exactly one market-data layer. New routes:
  `/api/harness/{runs,runs/[id],runs/[id]/events,runs/[id]/cancel,models,agents,data}`.
  Zero-config preserved: `postinstall` + `doctor.js` install the Python stack;
  without it runs return 503 rather than a fake agent. `npm test` now also runs
  the pytest suite (skips cleanly if the stack is absent). Verified end-to-end:
  auto-spawned runtime served a 14-provider catalog, the data bridge returned
  real AAPL JDdS data, and a run completed with a 9-event trace and a real tool
  execution. `tsc`, lint, 1424 TS tests, 34 pytest tests and `next build` pass.
  docs updated: `AGENTS.md`, `docs/harness/architecture.md`,
  `docs/harness/decisions.md`, `docs/harness/phase-1-progress.md`,
  `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/DECISIONS.md`,
  `skills/ARCHITECT.md`, `docs/CHANGELOG.md`

- **Harness Phase 1 — execution kernel + separate agent-memory database** —
  Built the agentic harness kernel in `src/lib/harness/`: provider-agnostic
  contracts (`types/contracts.ts`), a model adapter over the existing
  `OpenAICompatibleProvider` (no second HTTP client), a tool registry with
  runtime input validation / permission / risk / timeout / duplicate-call
  protection that adapts the existing agent tools, a bounded execution loop
  (`runtime/run.ts` with max-step, run-tool timeout and one cooperative
  cancellation path), structured `run.*`/`model.*`/`tool.*` events + a live bus,
  and four guarded API routes under `/api/harness/`. Persistence lives in a
  **separate** SQLite `agent-memory.db` (runs, events, tool executions,
  `AgentMemory` for user/agent/market facts, `AgentSkill` for future
  self-improvement) — deliberately NOT JDdS, so harness writes never touch the
  committed market-data snapshot. Read-only only: `execute` refuses non-`read`
  tools. Vertical slice `get_market_snapshot` reads JDdS and returns explicit
  provenance/freshness or an `UNAVAILABLE` state. No new dependencies.
  `tsc`, lint, 1468 tests (74 new) and `next build` all pass.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`,
  `docs/harness/phase-1-progress.md`, `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `docs/DECISIONS.md`, `docs/CHANGELOG.md`

## 2026-09-20

- **Repo organization / module boundaries before the agentic harness** —
  Conservative, verified reorg of the terminal codebase with no feature changes:
  (1) removed four dead modules with zero references anywhere in `src`/`scripts`/
  `docs` — `lib/alerts-evaluator.ts` (stale `/api/portfolio-alerts` concept),
  `lib/chart-colors.ts` (superseded by `theme/bridge.ts`), `lib/numeric-tickers.ts`
  (never wired), and the duplicate `lib/yfinance.ts` wrapper;
  (2) moved misplaced pure modules out of the component tree —
  `components/screens/market-data.ts` → `lib/screener/data.ts` and
  `market-format.ts` → `lib/screener/format.ts` (a backend route, `/api/stocks`,
  was importing screener data straight out of `components/` — a boundary
  violation), and `components/screens/navigation-history.ts` →
  `lib/navigation-history.ts` (framework-free, no React);
  (3) moved root `check-browser.ts` / `check-gf.ts` into `scripts/` and dropped
  them from the eslint ignore list; updated every import to `@/` aliases; added a
  "Module boundaries" section documenting the terminal/shared/backend/harness
  zones and reserving the future harness homes (`lib/skills/`, `lib/workflows/`,
  `lib/orchestration/`; the existing `lib/agent/` seed stays authoritative). No
  harness code was built. `tsc`, lint (pre-existing `tokens.ts` error aside),
  1394 tests and `next build` all pass.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`,
  `skills/REMEMBER.md`, `skills/ARCHITECT.md`
- **Investor Eye / globe country hover + click, label styling, and zoom clarity** —
  The globe is a textured sphere with no per-country geometry, so it emitted no
  geo hover/click; the 2D map's country highlight/selection did not exist on the
  globe. Added raycast picking (`viewGL.castRay` → globe `pointToData` → GeoJSON
  point-in-polygon via new `countryIsoForPoint`) with a `lines3D` polyline
  outline on hover and country selection on click. Country labels were made small
  (9px) and light with a soft shadow instead of a hard text stroke; they had been
  rendering invisibly because `itemStyle.opacity: 0` and `symbol: 'none'` both
  drop the label. Globe surface/emission textures raised 2048×1024 → 4096×2048
  (power-of-two, stroke widths scaled) to remove coastline pixelation at zoom.
  Added a persisted `NAMES ON/OFF` toggle to the map view controls. New tests:
  `app-geo.test.ts`, extended `map-labels.test.ts`.
  docs updated: `docs/investor-eye-architecture.md`, `docs/CHANGELOG.md`
- **Investor Eye / globe now fills the map, and country names show on both
  projections** — The globe option hard-coded `globeRadius: 86` + `distance: 200`,
  so the sphere rendered at ~65% of the viewport regardless of size. The camera
  distance is now derived from the live container box via `globeViewDistance()`
  (sphere silhouette geometry: `R / (√(D²−R²)·tan(fov/2))` = target fill of the
  shorter dimension), fed from the existing `ResizeObserver`. Country names are a
  shared scatter/scatter3D label series at the gazetteer centroids (echarts-gl's
  globe has no component-level labels, so `geo.label` could not work on both) —
  `showCountryLabels` defaults true. New tests in `map-labels.test.ts`.
  docs updated: `docs/investor-eye-architecture.md`, `docs/CHANGELOG.md`
- **Investor Eye / single-layer API returned empty for hazard & flow layers** —
  `GET /api/investor-eye/layers/:layer` had no `fires`, `shipping` or
  `commodities` case, so it fell through to a false `UNAVAILABLE` ("Layer has no
  data in this window") even though `/state` carried the events — notably the
  FIRMS satellite fire clusters, which made it look like satellite data had
  stopped. Wired all three builders into `buildLayer` so the endpoint matches
  what the map already renders.
  no doc change — bug fix, layer contract unchanged (`buildAllLayers` already
  produced these layers).
- **Investor Eye / portfolio sector exposure was always empty** — the panel
  posted only `symbol/weight/country`, so `computeExposure` never saw a sector
  and the UI permanently read "Sector data unavailable". `/api/quote` now
  selects and returns `Asset.sector`, `QuoteRow` carries it, and
  `portfolio-panel.tsx` attaches it to each holding. Country + sector
  intersections now populate.
  no doc change — additive field on an existing response; portfolio exposure
  contract unchanged.
- **Investor Eye / FIRMS run accounting showed negative rejects** — FIRMS ships
  one CSV batch that `normalize` expands into up to 400 clusters, so accepted >
  received and `recordsRejected` went negative in the Data Sources panel.
  `runSource` now clamps rejected at zero.
  no doc change — observability bug fix, no contract change.
- **Settings / FIRMS and USGS now discoverable in the Investor Eye feature map** —
  the "Global event map" chips listed only GDELT + RSS, so the keyless USGS and
  NASA FIRMS event sources were not surfaced anywhere in Settings even though
  they power hazards and satellites. Added `usgs`/`firms` (+ `gdelt`) directory
  entries and wired them into the feature map.
  docs updated: `docs/CHANGELOG.md`

- **Customization / two new shipped themes** — Added **Bloomberg** (dense
  amber-on-black trading terminal with blue selection, flat surfaces, compact
  density, tight radius) and **Bubudoll** (soft candy-pink brand with a rounded
  ambient gradient glow and high border radius) to `THEME_PRESETS`. They appear in
  Settings › Customization › Themes and apply via the normal preset path.
  docs updated: `docs/CHANGELOG.md`
- **UI / color picker drag no longer stalls the app (throttled commits)** — The
  native `<input type="color">` fires `input` continuously while dragging, and
  each tick applied the whole theme (an app-wide style recalc/repaint of the
  glass-heavy UI plus a chart re-render), so events queued faster than frames and
  the picker appeared to hang. Added a shared `createThrottledCommit` /
  `useThrottledCommit` hook (`src/hooks/use-throttled-commit.ts`): leading-edge
  immediate apply, then at most one commit per 100 ms using the latest value, with
  a trailing flush and an unmount flush so the final color is never lost. Wired
  into the three color pickers in Customization — theme `ColorField`
  (`customization-settings.tsx`), Charts `ColorPicker` (`chart-settings.tsx`), and
  Aurora `ColorField` (`aurora-settings.tsx`). Also: `applyThemeToDocument` now
  skips the DOM write when the built CSS is unchanged, `setPreview` in
  `chart-palette-store` skips identical previews, and `patchColor` no-ops on an
  unchanged value. Measured on a high-frequency drag: app-wide style writes fell
  from ~126 to ~20 per 2 s and median event-loop lag dropped to ~1 ms. Verified
  all three pickers still apply the dragged final color on blur.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **UI / sound opt-in default now actually takes effect** — After the previous
  release the sound tab still opened enabled at the old volume because the
  persisted `be_sounds_v1` value (written while UI audio was on-by-default)
  overrode the new OFF/8% defaults, so existing browsers never picked them up.
  Bumped the storage key to `be_sounds_v2` to retire the stale value exactly
  once; verified in a browser that seeds the old key that the master toggle is
  OFF and volume reads 8%. Corrected the store header comment. `tsc` clean,
  1362 tests pass.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Customization / live preview no longer ignores charts & heatmaps; presets
  carry chart colors; brand generator seeds a preset; all color tokens editable**
  — Fixed three related gaps in Settings › Customization. (1) Live/draft preview
  only recolored chrome; charts and the market heatmap waited for Apply. Added a
  non-persisting `previewPalette` overlay to `chart-palette-store` (`setPreview`,
  effective-palette reads in `useChartPalette`/`getChartPalette`/
  `subscribeChartPalette`) plus `previewChartPaletteFromTheme` /
  `clearChartPalettePreview` in `bridge.ts`, wired into the panel's live-preview
  effect, so candles and heatmaps recolor as the draft changes and revert on
  Discard. (2) Selecting a preset now also stages its market colors, so the Charts
  tab and market heatmap reflect it immediately (live) and on Apply. (3) User
  presets now capture the in-effect chart palette (`UserThemePreset.chartPalette`,
  persisted/rehydrated; legacy presets stay theme-only), and `applyUserPreset`
  restores theme + charts together. Also: the Colors card now exposes the four
  optional derived tokens (`secondary`, `muted`, `mutedForeground`,
  `accentSurface`) via `deriveThemeColors()` — pinned values override the derived
  mix in `themeCssVars`; and generating from a brand color pre-fills a saveable
  preset name. Tests added: `bridge.test.ts`, plus derived-color, preview-overlay,
  and preset-chart cases.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

## 2026-09-19

- **UI / sound defaults off, quieter, more packs** — UI sounds are now
  **opt-in**: `DEFAULT_SOUND_PREFERENCES` flips `enabled` to `false` and drops
  the default master volume from 60% to **8%** (within the requested 5–10%
  subtle range). Added four more voice packs — `crisp` (ultra-short dry tick),
  `typewriter` (heavy key thock), `marimba` (warm wooden mallet) and `digital`
  (minimal electronic blip) — giving nine selectable packs total, each with all
  six cues. `tsc` clean, 1349 tests pass.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Customization / full-screen preview button disabled** — "Enter full-screen
  preview" was gated on `disabled={!active && !dirty}`, so on a fresh Settings
  open (no unsaved changes) the button was dead and the mode appeared broken.
  Removed the gate so it always launches; Escape now also exits preview (capture
  phase, since the hidden base-ui dialog's dismiss handler swallows the bubble).
  Verified live: enter, Escape, Apply, and reload persistence all work.
  no doc change — behavior fix, contracts unchanged.

- **UI / dedicated Sound tab + customizable sound packs** — Moved UI sounds out
  of the Customization card into their own Settings › **Sound** tab
  (`sound-settings.tsx`) with a full customisation surface: master on/off +
  volume, mode (`all` / `essential`), a **voice-pack** picker, and per-cue
  volume / mute / custom-upload / reset plus a "Test all" runner. Replaced the
  single flat cue set with five synthesized packs under
  `public/sounds/<pack>/` — `eclipse` (organic modal-synthesis ticks, new
  default), `mechanical`, `soft`, `glass`, `retro` — each with all six cues,
  generated by a modal-synthesis + filtered-noise-transient generator for a
  real physical click rather than a synth beep. The manager now caches Howls
  per cue, resolves a `custom` data-URL upload over the pack asset, and lazily
  rebuilds/unloads on source change. `config.ts` gained `SOUND_PACKS` /
  `packSoundSrc`; `store.ts` persists pack + per-cue settings; added a
  `settings.sound` palette subroute and a Sound rail entry. Removed the old
  flat `public/sounds/*.wav`. `tsc` clean, 1349 tests pass.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **UI / sound system audible fix + sound mode** — Fixed the first-pass sound
  system being inaudible. Root causes: (1) Howler was imported only *after* the
  first gesture, so its AudioContext-unlock listeners registered too late and
  the context stayed suspended — the provider now **preloads** Howler on mount
  and merely *arms playback* on the first gesture, explicitly resuming
  `Howler.ctx` before play; (2) the WAVs peaked at ~0.2 and were multiplied by
  the 0.35 default master — regenerated the cue assets (peak ~0.88) and raised
  the default volume to 60%. Added a **Sound mode** setting (`all` vs
  `essential`) in Settings › Customization › Language & Access; `essential`
  mutes confirmations (`success`/`error`/`notification`). Cue definitions gained
  an `essential` flag and `canPlay` gates per-cue. Verified in a real Chromium
  session: context `running`, buffers start on nav clicks, essential mode
  suppresses non-essential cues. `tsc` clean, 1349 tests pass.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **UI / sound cues for keyboard + volume drag** — `SoundProvider` now mirrors
  its pointer cues on keyboard activation (Enter/Space on focused buttons,
  switches, links, menu items, tabs) and the volume slider no longer fires a
  `tick` on every drag step, so adjusting volume stays silent until released.
  no doc change — internal behavior, cue contracts and API unchanged.

- **UI / subtle terminal sound system** — Added an optional Howler.js-backed UI
  feedback layer (`src/lib/sounds/`: cue catalogue, defensive manager, persisted
  pref store, delegated `SoundProvider` mounted once in `layout.tsx`) with six
  local cues (`click`, `tick`, `toggle`, `success`, `error`, `notification`)
  under `public/sounds/`. Sound fires only on meaningful interactions
  (navigation, tabs, buttons, switches, menus, command selections, settings
  saves, agent start/finish, new alert events) and is debounced/throttled;
  hover, typing and live price updates stay silent. Audio unlocks on first
  gesture and every failure path is a no-op. New "UI Sounds" card
  (on/off + volume, default ON at 35%) in Settings › Customization › Language &
  Access, persisted via `useSoundStore` (`be_sounds_v1`). Added `howler` +
  `@types/howler`. `tsc` clean, 1349 tests pass.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Customization / full-screen theme preview** — Replaced the tiny inline mock
  desktop in Settings › Customization with a **full-screen preview of the real
  app**. "Enter full-screen preview" sets a new `previewMode` in the theme store,
  which hides (without unmounting) the Settings dialog so the live-themed app is
  visible and interactive, with a portaled floating **Apply / Discard / Exit**
  bar. The panel keeps its draft (it stays mounted); dialog close is suppressed
  while previewing. Added `overlayClassName` to the shared `DialogContent` to
  hide the backdrop. `tsc` clean, 1349 tests pass.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Header / price ribbon frozen fix** — The ticker's marquee stopped moving
  because the global reduce-motion / animations-off rules (`.a11y-reduce-motion`,
  `.theme-no-anim`, and `prefers-reduced-motion`) blanket-set
  `animation-duration` on every element, freezing `.price-ribbon-track` despite
  the documented intent that the ticker always runs. Added a higher-specificity
  `!important` exemption so the track stays `infinite`. Motion is the ticker's
  whole purpose, so it is the one intentional exception. ARCHITECTURE.md was
  corrected (it previously claimed the marquee was disabled under
  `prefers-reduced-motion`).
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Charts / chart toolbar de-greened** — The selected timeframe, chart type,
  refresh cadence, active menu triggers, drawing-tool/menu selection, volume
  toggle and the provider dropdown were highlighted with the theme's green
  `primary`, which clashed with the dark chrome. Replaced those selection states
  with neutral greys (`bg-muted-foreground/20`, `bg-accent/60`, `bg-foreground/70`)
  and dropped the emerald/rose provider dots for muted grey. No contracts changed.
  no doc change — pure styling, contracts unchanged.

- **Assistant / app-wide ChatDock** — The floating `ChatDock` assistant was
  mounted only on the Command Center. Moved it to the app shell
  (`stock-chat.tsx`), where it now appears on every tab. It is suppressed (via a
  new `visible` prop, no unmount) on the ChatBot tab — it would duplicate the
  full chat composer — and while the Settings modal is open. The standalone
  `/alerts` route mounts its own dock; Command Center fullscreen is covered by
  the shell dock. `tsc` clean, 1349 tests pass.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Customization / live preview + draft editing** — The Customization panel now
  edits a local **draft theme**. A sticky bar offers **Live preview** (pushes the
  draft to the whole document without persisting) plus **Apply changes** /
  **Discard**, and dirty state is tracked so nothing commits by accident. Added an
  inline, isolated `ThemePreview` card (real app chrome rendered with the draft's
  own token values) so users can see a theme before applying it. All numeric
  controls now use a shared labelled `Slider` component. Fixed the **page
  background** treatment: the `gradient`/`grid` pattern was painted on `<body>`
  but covered by the app shell's opaque `bg-background`; it now layers on the
  shell via the `.app-page-bg` class. Preview support (`preview`/`cancelPreview`/
  `commitPreview`) added to the theme store, unpersisted and SSR-safe. 2 new
  store tests; 1349 tests pass, `tsc` clean, 0 lint errors.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Journal / Add Trade dialog width + spacing** — The add-trade dialog collapsed
  to 384px on desktop: `DialogContent`'s base `sm:max-w-sm` beat the passed
  `max-w-3xl` (unprefixed vs `sm:` variant), so it rendered in a tight box with
  cramped inputs. Passed `sm:max-w-5xl` and widened the form grid/spacing
  (`gap-x-5 gap-y-4`, roomier inputs, 2-column Tags/Mistakes, roomier footer).
  no doc change — UI layout fix, contracts unchanged.

- **Market Screener / hidden-section restore** — The "Sections" show/hide manager
  was gated behind `screenerTab !== 'markets'`, so on the default Global Market
  tab (where the Ticker Strip, Earnings, Sectors and Market Shifters sections are
  hideable) there was no way to bring hidden widgets back. Removed the gate so the
  manager button is always available.
  no doc change — UI bug fix, contracts unchanged.

- **Customization / user presets + surfaces visibility** — Made the theme
  designer usable end-to-end. Added **user-saved presets**: "Save as preset"
  stores the current theme by name (`be_theme_presets_v1`), with rename, update
  (overwrite with current), and delete per preset — shown alongside the shipped
  presets and matched for the active highlight. Added **theme Import/Export**
  (JSON download/upload, validated through `normalizeTheme`). Surfaced a compact
  **Glass & Surfaces** card directly in the main Theme tab (frosted on/off, blur,
  tint, glass presets) so the controls are discoverable without hunting the tab.
  Fixed the token-driven glass override so it only activates once the user
  actually changes glass/shadow (`theme-glass-active` marker class), preserving
  the shipped per-tier glass hierarchy by default; store now reads
  `window.localStorage` (SSR/test-safe). 6 new store tests; 1347 tests pass,
  `tsc` clean, 0 lint errors.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Customization / glass mode + theme designer** — Added a **Glass & Surfaces**
  tab and deeper theme-design controls. `EclipseTheme` gained `glass`
  (`enabled`, `blur`, `opacity`, `tint`), `shadow`
  (`none|soft|medium|dramatic`) and `background` (`solid|gradient|grid`). New
  tokens (`--glass-blur`, `--glass-opacity`, `--glass-tint`, `--glass-tint-light`,
  `--glass-shadow`, `--glass-enabled`, `--page-bg-image`, `--page-bg-size`) drive
  every `.glass-*` recipe from one place: `globals.css` overrides all glass tiers
  so users can retune blur/tint or turn frosted glass off entirely (opaque, no
  backdrop-filter; `theme-glass-off` class). Tint is a color token scoped to
  `html.dark` with a light-mode counterpart, so custom dark tints never leak into
  light mode. Added four glass presets (Frosted/Crystal/Smoked/Solid),
  shadow-depth and page-background treatments, and four new theme presets
  (Crystal, Blueprint, Smoked + glass variants). 5 new tests; 1341 tests pass,
  `tsc` clean, 0 lint errors.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Branding** — Collapsed sidebar now shows the brand **favicon glyph bare** (no
  circle/tile) in both the header and the footer settings button; the expanded
  state keeps the text-monogram tile. Mobile top-bar likewise shows the bare
  favicon. Fixes the "logo inside a circle" the user reported when collapsed.
  no doc change — presentation tweak, branding contract unchanged.
- **Branding** — Sidebar and mobile top-bar now use a **text monogram** (B / BE /
  custom `logoText`), never a logo image; the logo asset remains only as the
  favicon. Collapsed footer monogram became the clickable settings button, and the
  expanded footer was retidied into a stable `[mark] [name] …… [gear]` row.
  no doc change — presentation tweak, branding contract unchanged.
- **Branding** — Sidebar header no longer duplicates the mark: the shipped
  wordmark (`LOGO-WORDMARK.svg`, which already contains the mark) renders alone
  with no green-gradient tile behind it, and is larger (1.85rem, max-w 190px).
  The gradient tile/collapsed footer box now appear only for a custom logo or
  monogram.
  no doc change — presentation tweak, branding contract unchanged.
- **Customization / brand theming + embedded Aurora & Charts** — Extended the
  centralized theme into a full white-label flow. The `EclipseTheme` model gained
  `fontScale` (global text size) and `logoScale` (sidebar/header mark size), both
  clamped and emitted as `--font-scale` / `--logo-scale` structural tokens;
  `globals.css` scales the root font-size through `--font-scale`, composing with
  the a11y large-text class. Added `themeFromBrandColor()`, a ServiceNow-style
  generator deriving primary, accent and bullish from a single organisation brand
  color (bearish overridable) while keeping neutral surfaces. The Customization
  panel is now tabbed — **Theme · Aurora · Charts · Language & Access** — reusing
  the existing `AuroraSettingsPanel` and `ChartSettingsPanel` so glow and chart
  palettes live inside Customization. Added a Brand-color generator card plus
  Text size / Logo size sliders. 4 new tests; 1336 tests pass, `tsc` clean,
  0 lint errors.
  docs updated: `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Customization / IA cleanup** — Removed the now-redundant standalone
  **Aurora** and **Charts** Settings rail entries (sections, nav items, render
  branches, imports, and the `settings.aurora` / `settings.charts` palette
  sub-pages). Both remain fully reachable as tabs inside Customization, and their
  keywords moved onto the Customization rail entry / palette page so search still
  finds "aurora", "glow", "chart colors", etc. `SectionId` / `SETTINGS_SECTIONS`
  drop the two ids. 1336 tests pass, `tsc` clean, 0 lint errors.
  docs updated: `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Branding** — Added the official BlackEclipse logo assets (`public/branding/FAVICON.svg`
  mark, `public/branding/LOGO-WORDMARK.svg` lockup) and wired them in as the default
  brand: sidebar/header mark, expanded-sidebar wordmark, mobile top-bar wordmark, and
  the document favicon (`BRAND_MARK_SRC` / `BRAND_WORDMARK_SRC` in `src/lib/theme/`).
  A user-uploaded logo/favicon in Settings › Customization still overrides them.
  docs updated: `docs/ARCHITECTURE.md`
- **Customization / centralized theming** — The Settings › Customization page is
  now a full theme system, not just language/a11y. New `src/lib/theme/` holds a
  serializable `EclipseTheme` (branding: app name, logo, favicon; typography:
  UI/heading/mono fonts; colors: primary, accent, background, surface, border,
  text, bullish, bearish; radius; density; glow/animation toggles), six shipped
  Eclipse-family presets, and a persisted zustand store (`be_theme_v1`). The
  store flattens the theme to CSS design tokens and injects them through a managed
  `<style id="eclipse-theme-overrides">` — colors scoped to `html.dark` (so the
  General › Theme light/dark switch still works) and typography/shape global.
  `globals.css` now routes its hard-coded greens/reds (scrollbars, hover borders,
  legacy emerald/rose remaps, sliders, inputs) through `--brand`/`--bullish`/
  `--bearish` tokens, and `.dark` card surfaces use `var(--card)`. Sidebar,
  top-bar and document title read the custom app name/logo. A bridge syncs the
  theme's market colors into the native chart palette on explicit edits (never on
  hydration, so a saved chart palette survives reload). 10 new tests; 1332 tests
  pass, `tsc` clean, 0 lint errors.
  docs updated: `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **i18n / completeness pass** — Fixed the language layer so no locale silently
  falls back to English. All 21 registered languages now translate all 70 UI
  keys (previously 22 keys were missing or stale, and `nav.ts` was missing the
  `earnings` tab so that nav item never translated). Reworked the English source
  around the new Customization page (`settings.customization.*`), translated the
  Customization panel itself (it was hardcoded English), and added an
  `earnings` nav mapping. The translator test now asserts full coverage for every
  locale rather than allowing fallback. 1322 tests pass, `tsc` clean, 0 lint
  errors.
  docs updated: `docs/CHANGELOG.md`

- **i18n / Accessibility** — Added the interface-localization foundation and an
  accessibility layer. New `src/lib/i18n/` (locale registry with RTL metadata for
  Arabic/Urdu/Persian/Hebrew, a canonical English dictionary, translations for
  21 languages, a pure translator with English fallback, a persisted zustand
  store that also drives `<html lang/dir>` and a11y classes, and `useT`/`useLocale`
  hooks). Added a new **Customization** page to the Settings modal (Personalize
  group) that owns the language picker and the accessibility toggles, and
  registered it for ⌘K (`settings.customization`); translated sidebar nav,
  chat-history chrome, keyboard-shortcut dialog and the top-bar search
  placeholder. Added skip-to-content link + `<main>` landmark,
  `prefers-reduced-motion` support, and reduce-motion / high-contrast /
  larger-text toggles. Scope is UI chrome only — financial data, news and AI
  output are never translated. 9 new tests; `tsc` clean.
  docs updated: `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

## 2026-09-18

- **Earnings (fixed)** — The embedded Market Screener calendar was invisible:
  the `earnings:calendar` DataHub topic was only registered in the dashboard
  registry, which the Screener never imports, so `useTopic` hung on "Loading…"
  forever. The topic is now registered at module scope in
  `earnings-calendar.tsx` (idempotent), so any consumer works. Also redesigned
  the screener embed: a proper section header (CalendarClock icon + serif title
  + Hide) matching Sectors/Shifters, and the roomy layout splits into month grid
  (left) + selected-day detail (right) instead of one tall column. Removed the
  orphaned `earnings` i18n nav key. 1322 tests pass, `tsc` clean, build clean.
  docs updated: `docs/CHANGELOG.md`

- **Earnings (revised)** — Removed the standalone `earnings` tab/screen added

- **Journal / Quick Add Trade** — Added a single Add-Trade entry point on the
  Journal header (`QuickAddTrade`), reachable from every sub-tab, with a global
  `Shift+N` shortcut and pre-fill from a selected calendar day. It wraps the
  shared `TradeForm` in a glass dialog and owns the POST + refresh. The old
  divergent inline forms in the Trades and Calendar tabs were removed (Trades
  had a duplicated form/state type); both tabs now open the same dialog, and
  Overview's empty-state button opens it directly. 1312 tests pass, `tsc` clean,
  build clean.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Journal / Market Bubbles fixes** — (1) The MiniCalendar ("Last 39 Weeks")
  hover tooltip drifted down instead of following the cursor: `position: fixed`
  is relative to the nearest ancestor with a `backdrop-filter`, and the frosted
  glass-card wrapper set one. The tooltip is now rendered through a portal to
  `<body>`, restoring true viewport positioning. (2) Market Bubbles always
  opened on CRYPTO, ignoring the country the user selected elsewhere. Added
  `lib/user-market.ts` (one persisted market preference: last explicit choice →
  Settings default → browser locale → US); the Screener writes it, the Bubbles
  page and Settings seed from it. 1312 tests pass, `tsc` clean, build clean.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Settings / UX phase 4 (P2)** — Economics providers are now sub-grouped
  (Central banks / Multilateral / Official statistics / Market data) instead of
  one 44-row list. Added keyboard navigation (`/` focuses search, ↑/↓ switch
  sections, Esc blurs), deep-link anchors (`settings.market#priority` scrolls to
  a block), and honest error/retry states when the provider catalog fails to
  load (empty catalog no longer renders silently). File split of inline sections
  deferred with a TODO (needs state lifted to a context first). 1307 tests pass,
  `tsc` clean, production build clean.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Settings / UX phase 3 (P1)** — Added a provider status header
  (`N ready · M need a key`), amber attention dots on rail sections whose
  providers need keys, clickable "Used by" labels that navigate to the consuming
  page, a mobile horizontal pill row instead of the section dropdown, and a
  Reset-to-defaults control in General. Unified the LLM key: the AI section's
  key now lives in the provider-key vault (keyed by the selected preset's env
  var) and `getLLMConfig` falls back to it — no second `llm.apiKey` field to
  keep in sync; persistence merges over the raw config so a vault key is never
  copied into the plaintext row. 1307 tests pass, `tsc` clean.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Settings / UX phase 2** — Unified persistence: every Settings control now
  applies instantly (debounced POST for preferences/LLM, immediate for news
  toggles), the Save/Discard bar is replaced by a status strip that reports the
  real save state or error, and no section claims "changes take effect
  immediately" while requiring Save. Also: grouped rail under Personalize /
  Intelligence / System, added a settings search box (keyword `terms` per
  section), and provider registries now filter, sort configured-first, and
  collapse past 8 rows with "Show all N". 1307 tests pass, `tsc` clean.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Settings / UI polish** — Removed the section eyebrow labels, removed the
  "Powered by JDDS" rail footer, and aligned the Settings rail + section icons
  with the app's page-icon language (`rounded-2xl border border-primary/25
  bg-primary/15 shadow-lg shadow-primary/10`, `text-primary`). Rail header icon
  is now a gear. Presentation only.
  no doc change — cosmetic, contracts unchanged.

- **Settings / UX-IA (dedup)** — Fixed repeated providers across Settings: each
  provider now has exactly one `home` section, enforced by `providerHome()` in
  `lib/providers/directory.ts`. Investor Eye lists only its own keyless event
  sources (GDELT/USGS/FIRMS) + a deep-linking feature map; added a dedicated
  **Economics** section; Market Data lists prices/fundamentals/crypto/custom;
  News lists only Finnhub. The separate `ApiKeysPanel` was removed from sections
  (and `api-keys-panel.tsx` deleted) because the registry now manages keys
  inline — one list per section, not two. Buckets: AI 14, Economics 44, News 1,
  Market 15. 1307 tests pass, `tsc` clean.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Ops** — Dev server outage during the Settings/UX-IA work: running `next build`
  while `npm run dev` was live overwrote `.next` with production output, so the
  running dev server lost `routes-manifest.json` and its webpack chunks (all API
  routes errored with ENOENT / MODULE_NOT_FOUND). Fix: stop dev, delete `.next`,
  restart. Lesson: never build while `next dev` is live — they share `.next`.
  no doc change — operational fix, no code or contract change.

- **Settings / UX-IA** — Reorganized the Settings modal around *what the user is
  configuring* instead of backend concepts. The 12 overlapping sections
  (Appearance, Aurora, Charts, Sidebar, AI Agent, Market Data, News Feeds, API
  Keys, Data Sources, Integrations, Alerts, Data) became 11 purpose-first
  sections: **General · Aurora · AI / LLM · Investor Eye · Market Data · News ·
  Charts · Sidebar & Navigation · Alerts · Data & Storage · System**. New
  `src/lib/providers/directory.ts` gives every provider a purpose / used-by /
  free-or-paid tier; `provider-registry-panel.tsx` renders the
  Provider→Purpose→Features→Status→Key→Test registry and an Investor Eye
  feature→provider map. `ApiKeysPanel` is now category-filterable so LLM keys
  live only under AI / LLM and financial/data keys only under Investor Eye.
  Added `POST /api/agent/test` for a real LLM **Test Connection**. Catalog
  `configure.target` values renamed `agent`/`integrations` → `ai`/`investor-eye`.
  Visual glass system unchanged. 1307 tests pass, `tsc` clean, build clean.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **UI / Chat** — Shrank the floating assistant dock: width `760px` → `560px`
  and transcript max height `min(60vh,520px)` → `min(45vh,360px)` so the popup
  no longer dominates the dashboard. Pure sizing change.
  no doc change — cosmetic sizing, contracts unchanged.

- **Fundamentals / Screener** — Removed the standalone **Fundamentals** sidebar
  tab (`fundamentals.tsx`, `AppTab`, sidebar config, search registry, top-bar,
  shell keep-alive). Fundamentals now lives ONLY in the Market Screener stock
  popup, and its two tabs were merged: the old **All Metrics** and
  **Fundamentals** are a single **Fundamentals** tab showing the filings-backed
  snapshot (Overview/Statements/Valuation/Timeline) followed by the live price
  history, performance, core metrics and profile. Default sidebar shortcuts
  revert to the original unique F1–F11 (no more F12 dup). The shared panel in
  `src/components/screens/fundamentals/panel.tsx` is now the only UI surface.
  Verified live: NVDA popup Fundamentals tab renders fundamentals + live metrics
  together with 8 charts, 0 page errors. 1307 tests pass.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Fundamentals / Screener popup** — The Market Screener stock detail popup now
  has a **Fundamentals** tab that renders the same normalized analysis as the
  full page (Overview / Statements / Valuation / Timeline, metric tiles with
  value+period+YoY+source, charts). The presentational sections were extracted to
  `src/components/screens/fundamentals/panel.tsx` so the screen and popup share
  one implementation; the old "All Metrics" tab is preserved unchanged. New
  `countryToMarketId()` in `src/lib/markets.ts` normalizes JDDS's inconsistent
  country values ("United States" / "US") to a market id. Fixed a real SEC bug
  the popup surfaced: **tag families now union instead of stopping at the first
  tag with any data**, so a preferred revenue tag that stops being reported
  (NVIDIA after FY2022) no longer blanks the latest revenue; sub-annual windows
  sharing a fiscal end date are ignored. Verified live: NVDA popup → SEC + Yahoo,
  revenue $215.94B / +65.5% YoY, 6 charts. 3 new tests.
  docs updated: `docs/CHANGELOG.md`

- **Fundamentals** — New investor-focused **Fundamentals** sidebar tab backed by
  a multi-provider layer (`src/lib/fundamentals/`): `Provider → Normalization →
  JDDS → UI`, with the UI depending only on the Eclipse schema. Providers in
  authority order: **SEC EDGAR** (US, keyless, preferred XBRL filings; EBITDA
  derived and labelled), **Financial Modeling Prep** (optional key, first
  secondary vendor), **Yahoo Finance** (yfinance bridge, global fallback; new
  `scripts/yfinance_fundamentals.py` returns 5 years of real statements). New
  `FundamentalsCache` JDDS model + in-memory map (stale-while-revalidate; 24h
  fresh / 7d hard), `GET /api/fundamentals`, and a screen with Overview /
  Statements / Valuation / Timeline sections covering revenue, margins, ROE/ROA/
  ROIC, debt ratios, growth + 3Y/5Y CAGR, valuation multiples, dividends,
  earnings/ownership, charts (revenue, EPS, FCF, margins, debt vs cash, valuation
  history) and data-driven insights/risks. Every metric shows value, period, YoY,
  source and last-updated. Funds/ETFs with no statements still render their real
  profile + multiples rather than a blank page. Verified live: AAPL 8 periods /
  39 metrics / 6 insights from SEC+Yahoo; RELIANCE (IN) via Yahoo in INR; SPY
  profile + multiples; unknown symbols return an honest UNAVAILABLE. 16 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`
- **Scheduler / Sidebar** — Default sidebar shortcuts are now unique F1–F12
  (the old scheme folded every section past the tenth onto F12, which collided
  when the Fundamentals section was added); `doctor.js` already auto-applies the
  additive `FundamentalsCache` table on boot, so zero-config is preserved.
  no doc change — covered by the Fundamentals entry above.

- **Command Center / Earnings** — The Earnings Calendar widget now renders a
  **month grid calendar** instead of a list: 6×7 Sunday-first cells with per-day
  ticker chips (+N overflow), a highlighted today and selected day, month
  prev/next + Today, and a detail list for the selected day (company, BMO/AMC,
  EPS est; clicking opens the chart). The keyless Nasdaq fallback now fetches a
  bounded rolling window (last 7 → +35 days, weekends skipped, pooled ~6 at a
  time) so the calendar is actually populated — verified live: 605 rows across
  30 days. Widget frame raised to 420px.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Command Center / Earnings** — Fixed "no data" when no key is configured and
  added the keyless fallback. Alpha Vantage stays primary, but a zero-config
  install has no `ALPHAVANTAGE_API_KEY`, so `earnings.ts` now falls back to
  **Nasdaq's public earnings calendar** (no key) for the next 5 weekdays; the
  widget names the real source (`Nasdaq` / `Alpha Vantage`). Verified live: 77
  real rows. Nasdaq session values (`time-pre-market` / `time-after-hours`) and
  parenthesised negative EPS (`($1.08)`) are parsed. If a key exists but is
  rejected/limited, it also falls through to Nasdaq. 3 new tests.
- **Workspace** — Fixed being stuck in edit mode. The toolbar/Done buttons used
  `setEditMode(!workspace.editMode)` — a render-time closure, so two toggles
  before a re-render acted on a stale value and left edit mode on. Added
  `toggleEditMode()` which reads the store's current value at call time; the
  toolbar Done button now also shows a check icon. docs updated:
  `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Command Center / Earnings** — Added an **Earnings Calendar** widget.
  `src/lib/earnings.ts` (server-only) fetches Alpha Vantage
  `EARNINGS_CALENDAR?horizon=3month` using the existing provider-key vault
  (`ALPHAVANTAGE_API_KEY`); the key never reaches the browser. `getEarningsCalendar`
  caches 6h (shared in-flight, serve-stale-on-error) and returns an explicit
  `unavailable` state with a reason on a missing key, timeout, HTTP error, or a
  JSON rate-limit/notice body. New route `GET /api/earnings`; the widget
  (`widgets.tsx`, registered as `earnings-calendar`, topic `earnings:calendar`)
  shows company, ticker, date, BMO/AMC (maps `pre-market`/`post-market` too),
  EPS estimate, Today/Tomorrow/This Week/3-month filters, loading/empty/error
  states, source + last-updated, and opens a row's symbol on the chart via the
  command store. 5 parser tests. docs updated: `docs/ARCHITECTURE.md`,
  `docs/CHANGELOG.md`

- **Command Center** — ChatDock minimized pill is now draggable. It defaults to
  the viewport bottom-right corner (it was anchored to the centred column, so it
  sat mid-right) and can be dragged anywhere, with the position persisted
  (`be_chat_dock_pill_pos_v1`) and re-clamped on resize. Click restores; a drag
  moves it.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Command Center** — ChatDock float fix + minimize option. The visibility gate
  no longer uses an `IntersectionObserver` on a zero-size sentinel (which made the
  composer vanish mid-scroll — it looked like it scrolled with the page); it now
  reads the keep-alive panel's `display` via `MutationObserver`
  (`[data-keepalive-panel]`). The composer is a true viewport-fixed overlay (no
  reserved `pb-28`). Added a persisted **minimize/restore** pill
  (`be_chat_dock_minimized_v1`) separate from the transcript expand toggle, so
  the user decides small vs big.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Command Center** — Added the floating **ChatDock** assistant composer.
  `components/chat/chat-dock.tsx` is a Gemini-style bottom-centre bar: collapsed
  it is just the composer, and the transcript expands ABOVE it once there is a
  conversation. It reuses the existing chat stack (`ChatHistory`,
  `getAgentProvider()`, `/api/agent/research` for research intents) so there is
  one chat implementation. It owns its own localStorage conversation
  (`be_chat_dock_v1`), portals to `<body>` at `z-[90]` (above the fullscreen
  overlay), and is `data-nodrag` — but deliberately NOT `data-keyboard-overlay`
  (an always-on surface must not block page shortcuts; the focused input already
  suppresses them). A visibility sentinel gates it on the Command Center being
  the ACTIVE keep-alive tab (a body portal is not hidden by an ancestor
  `display:none`). The provider pill shows the REAL configured provider label,
  never a fabricated model. `ChatHistory` gained a `compact` variant.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Aurora / Fullscreen** — Fixed the missing Aurora glow in Command Center
  fullscreen. The overlay portals to `<body>` at `z-[80]`, above the app shell's
  Aurora (`z-0`), so it covered the glow. Extracted the glow into a reusable
  **`<AuroraGlow>`** (`components/layout/aurora-glow.tsx`) that owns the
  market+news sentiment subscription and user palette; the shell and the
  fullscreen overlay both mount it (fullscreen renders its own above the
  translucent backdrop). Removed the duplicated sentiment wiring from
  `stock-chat.tsx` and added a dedicated `aurora:news-score` topic so the glow no
  longer depends on the news screen emitting a callback.
- **Command Center** — Shipped-default board mechanism. `default-board.ts` holds
  `DEFAULT_BOARD_JSON` (paste a Command Center → Export layout) so a curated
  arrangement becomes what every new user downloads into and what Reset returns
  to; validated through `normalizeLayout` so a bad/unknown-widget paste falls
  back to the persona template instead of shipping holes.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Charts / Command Center** — Fixed blank charts, maps and heatmaps. A
  `defaultHeight` card was rendered as `min-height` only, so a frame widget's
  body (`flex-1` with `absolute inset-0` / `h-full` children) had no definite
  height and the ECharts canvas collapsed to **0px** (verified: 687×0 → 687×314
  after the fix). `cardStyle` now gives a `defaultHeight` card a definite
  `height`; `minHeight` stays a grow floor for tiles. Widgets added from the
  library now carry their intrinsic sizing too (`ops.addWidget` /
  `addWidgetToNewSectionAt` take a `sizing` hint), so a fresh chart/map is never
  added collapsed.
- **Command Center** — Added three personas (12 total): **Risk Desk**,
  **Trader Pro** (dual charts) and **The Research Desk**. Layout tabs are now
  **drag-to-reorder** (`TabBar` `onReorder` + `useMarketViews.reorder`), on top
  of the existing drag/click widget arrangement and double-click rename.
  2 new tests. docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`,
  `.opencode/skills/black-eclipse-workspace/SKILL.md`

- **Workspace / Command Center** — Fixed empty layouts after the persona rename.
  The nine personas got new ids (`trader` → `tape-reader` …) but stored v7
  dashboards/market layouts still carried the OLD `templateId`, so
  `getDashboardTemplate` returned `undefined`, `buildMarketViewLayout` received
  no centre base, and **only the side rails rendered**. Added
  `LEGACY_TEMPLATE_IDS` + `resolveTemplateId` so old ids resolve, a blank-layout
  self-heal in `use-workspace`, and bumped storage to **v8**
  (`be_dashboards_index_v8` / `be_ws_dashboard_v8_`) to reseed existing users.
  4 new tests cover every legacy alias building a non-empty centre.
  docs updated: `docs/ARCHITECTURE.md`

- **Workspace / Command Center** — Persona variety, resizable side panels, and
  the widget-fit fix.
  - **Widgets now fit.** Auto cards split into two sizing modes:
    `defaultHeight` (a FRAME whose body stretches — charts, maps, live video,
    scrollable tables/feeds) and `minHeight` (a floor under content that GROWS —
    tiles). The renderer keys its body class off this (`isDefiniteCard`), so
    frame widgets no longer collapse to a `flex-basis:0` body, and the hardcoded
    `minHeight:620` on the Eclipse chart is gone. `WidgetPlacement.defaultHeight`
    added; `normalizeLayout` preserves it.
  - **Personas redesigned + renamed.** The nine templates are now genuinely
    different SHAPES, not reshuffles: Tape Reader, The Desk (dense 4-track),
    The Allocator, Rates Desk, Chain Desk, FX Desk, The Screener, Map Room,
    Newsroom. Bands can override a widget's frame height (`{ id, h }`) for
    deliberate asymmetry.
  - **Resizable left/right panels.** Drag the vertical handle between a side
    zone and the centre to set its width (180–520px); persisted per layout in
    `WorkspaceLayout.zoneWidths` via `ops.setZoneWidth`. Works in normal and
    edit mode.
  - **Nine dead widgets wired to real data:** Agent Errors (agent runs),
    Candle Chart (ECharts candles on the market's lead symbol), Stock Screener
    (`/api/stocks`), Sparklines (real 1mo price history), Crypto Ticker + Trade
    Tape (`market:indices:CRYPTO`), Geopolitics + Maritime & Trade (Investor Eye
    events by lens), News by Category (`/api/news?category=`). Still honest
    UNAVAILABLE: Recent Files, Web Scraper, Notes, Polymarket.
  25 new/updated tests. docs updated: `docs/ARCHITECTURE.md`, `docs/GLOSSARY.md`,
  `.opencode/skills/black-eclipse-workspace/SKILL.md`

- **Workspace / Command Center** — Replaced the row-band layout grammar with the
  **masonry track board** to eliminate dead gaps. Every default placement now
  sizes to content (`height: null`) with a per-widget intrinsic floor
  (`WidgetDefinition.minHeight` / the composition `WIDGET_MIN_HEIGHT` map), so a
  short widget can no longer sit stranded beside a tall one. A new pure packer
  (`src/lib/workspace/pack.ts`, `rebalanceColumns`/`rebalanceLayout`) balances
  each multi-column section's cards into the shortest track at COMPOSE time;
  user edits commit exactly where dropped (no silent reshuffle). Added the
  removed "Fit height" control (auto is the default); `WorkspaceLayout.version`
  is now `2`. `buildMarketViewLayout`/`composeBoard` replace `composeRows`, and
  the eight persona templates + `defaultFundLayout` are track-board specs.
  Storage reset to **v7** dashboards / **v3** funds / `be_dashboards_index_v7`
  (old keys untouched). 20 new/updated tests. docs updated:
  `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`,
  `.opencode/skills/black-eclipse-workspace/SKILL.md`

- **Workspace / Command Center** — Removed compact mode, added fullscreen, and
  fixed the gappy look of the v4 layouts.
  - **Compact mode deleted** (prop, state, toggle, `Shift+C`, canvas plumbing).
    It forced every card to a fixed 40px height and crushed widget content.
    Cards now size to the widget (auto stretch) or a pinned per-placement height.
  - **Fullscreen mode** added to the Command Center (`Shift+F`, header button,
    `Esc` to exit). The overlay is **portaled to `<body>`** because the app
    shell's glass-card `backdrop-filter` creates a containing block that traps
    `position: fixed` — the same constraint the Chart Workspace already handles.
    Body scroll locks while open.
  - **Gaps fixed:** each side rail is now ONE STACKED section instead of one
    section per tile (the per-tile section padding/gap was the "too many gaps"
    problem). Persona bands were reworked to a short 4-up hero, a full-width
    pinned-height primary visual, and roomy TWO-UP analysis/context bands rather
    than four skinny columns. `composeRows` now also carries **pinned heights**
    and `stack` rows. Storage bumped to **v5** (deliberate reset).
  2 new tests (pinned heights + stacked rails). docs updated:
  `docs/ARCHITECTURE.md`, `docs/GLOSSARY.md`
- **Workspace / Command Center** — Rebuilt the default dashboard layouts. The
  old generator produced cross-zone duplicates (left/right builders were not
  deduped against the centre, so `watchlist`/`top-movers`/`news-feed` rendered
  twice) and a 5-widget "lead" row that `normalizeLayout` truncated to 4 columns
  on reload — layouts literally changed shape after a refresh. Fixes:
  extracted a pure, tested layout engine (`src/lib/dashboard/layout.ts`) with a
  single `composeRows` that enforces **global first-wins dedupe** and a
  **build-time 4-column cap**; rewrote persona templates as **widget-id specs**
  (no more fragile registry indices that silently repoint when a widget is
  inserted) using a **band grammar** (hero → primary → analysis → intelligence →
  context). Six genuinely distinct personas (Trader, Investor, Macro, Crypto,
  Forex, Quant), all with thin side rails (left = Watchlist only; right =
  asset-class `mp-*` stat tiles) and no widget shown twice. Bumped storage to
  **v4** as a deliberate reset — pre-v4 layouts are not carried forward (v3
  dropped from `LEGACY_INDEX_KEYS`), so everyone reopens into the clean defaults.
  23 new tests. docs updated: `docs/ARCHITECTURE.md`, `docs/GLOSSARY.md`
- **Live Intelligence** — The widget users actually found was still the OLD
  `UNAVAILABLE` stub. The `live-tv` ("Live TV / Streams") registry slot was a
  hardcoded `<Unavailable>` stub, and it was left in place when Live Intelligence
  was added as a separate `live-intelligence` entry — so anyone with the slot
  already placed (or finding it in the library first) saw "UNAVAILABLE — data
  source not connected yet." Fixed by **upgrading the `live-tv` slot in place** to
  render the real `LiveIntelligenceWidget` (keeping the id so existing saved
  layouts work), deleting the duplicate `live-intelligence` entry, removing the
  dead `LiveTVWidget` stub, and adding the slot to the Trader persona template
  (index 28, which no template referenced) so new users get it by default.
- **Live Intelligence** — Fixed a real first-paint bug this exposed: the widget
  embedded the unreliable `live_stream?channel=<handle>` fallback *before* the
  resolver answered, rendering a blank frame stuck at `CHECKING`. Built-in
  YouTube channels now **wait for the resolver** (a "Checking live status…"
  state) instead of mounting the fallback, so the first frame is always the
  playable `/embed/<resolved-id>`. Added a `COULD NOT CHECK STREAM` state for a
  resolver failure, distinct from a resolved `CHANNEL OFFLINE`.
  Verified in a real browser: `CHECKING → LIVE`, iframe
  `/embed/QB5BNdBFujE`, `<video>` present, and switching to Geo News swaps to
  `/embed/t3fvgmDDmdc` with chip `LIVE`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Workspace** — Added a **left side zone** to the widget workspace so the
  Command Center reads as a three-column dashboard instead of one wide grid. The
  zone model is now `left | main | right` (the old `rail` is mapped to `right` on
  read — no storage bump), rendered under the same `DndContext` and one Customize
  surface. New `setZoneHidden` op + **Left panel / Right panel** toggles in
  Customize let users *remove* a side panel without deleting its widgets
  (`hiddenZones` persists, so re-showing restores the exact arrangement). The
  left column ships populated (Watchlist / Top Movers / News Feed, asset-class
  aware) via `buildLeftSections` + `ASSET_LEFT`. Command Center is denser by
  default (compact rows, trimmed header). Existing layouts migrate automatically.
  5 new tests (legacy-rail mapping, hiddenZones normalization, setZoneHidden).
  docs updated: `docs/ARCHITECTURE.md`, `docs/GLOSSARY.md`
- **Live Intelligence** — Fixed the "STREAM UNAVAILABLE" bug. Root cause, verified
  in a real browser against live YouTube: the widget embedded
  `youtube-nocookie.com/embed/live_stream?channel=<UC>`, which YouTube renders as
  **"This video is unavailable"** for most channels that *do* have a live
  broadcast. Two independent findings, both load-bearing:
  - `/embed/<resolved-video-id>` plays correctly where `live_stream?channel=`
    fails (confirmed: Sky News, DW News, Geo News, Bloomberg all "unavailable"
    via live_stream, all playing via the resolved id). Live ids rotate, so they
    cannot be hardcoded.
  - YouTube's `/channel/<UC>/live` page silently omits the canonical live video
    for many channels whose `/@handle/live` resolves correctly — so resolution
    now tries the handle first.
  Added a **server-side, cached resolver** (`live-resolver.ts` +
  `GET /api/live-streams`, 3-min TTL, shared in-flight guard, globalThis-anchored
  like the Investor Eye cache) that reads YouTube's own page metadata
  (`canonical watch?v=` + `"isLive":true` + `playableInEmbed`) to classify
  `live` / `offline` / `unavailable` / `unknown`. The widget embeds the resolved
  id, exposes honest `LIVE`/`OFFLINE`/`CHECKING` status (never a fabricated
  LIVE), shows a `CHANNEL OFFLINE` state with Check Again, and surfaces live
  status dots in the channel manager. Registry corrected too: the old
  `al-jazeera` id was actually Al Jazeera *Arabic* (English now
  `UCNye-wNBqNL5ZzHSJj3l8Bg`); added `@handle` for every channel; added
  verified Moneycontrol, CNBC Awaaz, India Today, PTV News; removed unverified/
  permanently-offline entries from the default-on set. 26 new tests.
  docs updated: `docs/ARCHITECTURE.md` (Live Intelligence section),
  `docs/NAVIGATION.md`
- **Live Intelligence** — Verified source registry against live YouTube. 20
  channels resolved and played: Bloomberg Television, CNBC, Yahoo Finance,
  Moneycontrol, Sky News, Al Jazeera English, DW News, Euronews, NHK WORLD-JAPAN,
  CNA, ABC News (Australia), CNBC-TV18, ET Now, Zee Business, India Today, WION,
  CNBC Awaaz, Geo News, Samaa TV, PTV News. Five official channels were **not**
  broadcasting at test time and are shipped disabled with `lastKnownStatus:
  'offline'` (Fox Business, France 24 English, TRT World, NDTV Profit, ARY News,
  Dunya News) — they may return, and the resolver re-checks every 3 minutes.
  Not added at all: Sky News' old id, Bloomberg Technology, CGTN America (no
  live broadcast observed).
  no doc change — covered by the architecture section above.
- **Build** — Learned (again) not to run `next build` while `next dev` shares the
  same `.next` directory: it produced `Cannot find module './NNNN.js'` and an
  empty Command Center. Clearing `.next` and restarting dev fixed it; no source
  change.
  no doc change — local build-artifact contention.

## 2026-09-17

- **Investor Eye** — Fixed the `Cannot read properties of null (reading '0')`
  crash when the Investor Eye **map** is embedded in a dashboard widget. The
  ECharts geo `View` dereferences a null matrix when `setOption` runs against a
  **zero-size container**; the full-screen map always has an explicit height, but
  a widget card can mount a frame before flex layout resolves its height.
  `WorldMap` now initialises through a `hasDrawableBox()` guard and lets its
  ResizeObserver trigger init once the box is real (the previous observer only
  resized an already-created chart). Reproduced directly against echarts: 0×0,
  0×400 and 400×0 throw; 1×1 and any real size are fine.
  docs updated: `docs/CHANGELOG.md`; skill `.opencode/skills/black-eclipse-workspace/SKILL.md`
- **Command Center** — Added an **Investor Eye Map** widget: the same interactive
  world map / 3D globe the Investor Eye screen renders, embedded in the dashboard
  grid. It reuses the SAME DataHub state topics + `buildAllLayers()` (no second
  fetch path, no fabricated data) and the shared `useInvestorEyeStore`, so
  selection and layers stay in sync with the full screen. The map chunk is
  `next/dynamic`-split, so a dashboard without this widget never loads
  ECharts/`echarts-gl`. Configurable `range` (1H…30D); a header **Open** button
  navigates to the Investor Eye tab for the detail dossier. Registered beside
  `investor-eye` in `DASHBOARD_WIDGETS` (templates are index-based).
  docs updated: `docs/CHANGELOG.md`; skill `.opencode/skills/black-eclipse-workspace/SKILL.md`
- **Workspace** — Fixed two editor bugs. (1) Column width resize reverted to its
  pre-drag width: the handle rewrote a single column's weight, which the 1..6
  clamp saturated, and the height-resize commit measured a stale DOM value after
  clearing the preview style. The boundary handle now moves the shared edge —
  growing one column while shrinking its neighbour atomically via the new
  `setColumnWeights` op, so the section total is invariant and the drag is fully
  reversible left↔right; weight range widened to 0.3..12 for a usable aspect
  ratio; the height commit now uses the tracked pointer delta.
  (2) Adding a column to a section (`setColumnCount`) ran `pruneLayout`, which
  deleted the still-empty section the user had just created — so "add a
  three-column section" vanished. `setColumnCount` no longer prunes empty
  sections (they are legitimate user-created drop targets, as `createSectionAt`
  already preserved).
  no doc change — UI bug fixes and internal op addition, contracts unchanged
  (`setColumnWeights` is additive; `WorkspaceColumn.weight` still a number).
- **Live Intelligence** — Added a **Live Intelligence** Command Center widget: a
  terminal-style live news player for financial, market, business and
  geopolitical broadcasters, with an in-card channel manager (enable/disable,
  set default, filter, search, and advanced custom sources). New modules:
  `live-channels.ts` (23-channel registry — every YouTube id resolved from the
  network's own page, never invented — plus `channelEmbedUrl`/`safeEmbedUrl`
  host-allowlist and `parseCustomSource`), `live-intelligence-store.ts`
  (localStorage selection store reusing the ribbon/watchlist storage-event
  pattern), and `live-intelligence-widget.tsx` (player + loading/offline/error/
  empty states). Registered as a normal widget appended last in
  `DASHBOARD_WIDGETS`, so move/resize/config/persist come from the existing
  workspace kernel — no second framework, no new dependency (YouTube embed uses
  a plain iframe; HLS was deliberately not added since no verified source needs
  it). 27 tests.
  docs updated: `docs/ARCHITECTURE.md` (new "Live Intelligence" section),
  `docs/DECISIONS.md` (ADR-015), `skills/ARCHITECT.md` (ADR-012–015 backfilled
  from `DECISIONS.md`), `docs/NAVIGATION.md`
- **Live Intelligence** — Media widgets now own their teardown (ADR-015). The
  shell keeps visited tabs MOUNTED and hidden with `display:none`, and
  `WidgetDefinition.lazy` is declared but never read, so a playing iframe would
  stream forever on an unwatched tab. The widget uses an `IntersectionObserver`
  (catches `display:none` ancestors and scrolled-off cards) plus a
  `visibilitychange` listener (browser tab) to unmount the player, re-mounting
  on return. Neither signal alone is sufficient.
  docs updated: `docs/DECISIONS.md` (ADR-015), `skills/ARCHITECT.md`
- **Screener** — Split the `market-overview.tsx` monolith: 4,599 → 2,593 lines
  (273 KB → 140 KB). Extracted `use-global-markets.ts` (Global Markets fetch +
  persisted prefs + pointer drag engine), `market-overview-global-markets.tsx`,
  `use-market-tabs.ts` (forex/commodities), `market-stock-tables.tsx`,
  `market-fund-etf-tables.tsx`, `market-tables.tsx`, `market-format.ts`
  (price/cap/time formatting) and `market-loaders.tsx` (table loaders). Pure
  mechanical extraction — no behavior or contract change; `tsc`, all 1157 tests
  and `next build` pass.
  docs updated: `docs/NAVIGATION.md`, `skills/ARCHITECT.md`, `skills/REMEMBER.md`
- **News** — Rewrote the sentiment classifier (`src/lib/sentiment.ts`): phrase
  patterns now disambiguate context words (bare "record" is neutral, "record
  loss" is bearish, "record high" bullish), punctuation is normalized so
  "sell-off"/"record-breaking" reach their phrases, dead zero-weight lexicon
  entries were removed, and concessive connectors ("despite", "although") no
  longer negate (they inverted correct headlines). Negation now covers a
  dedicated negator set. 10 unit tests.
  no doc change — the `src/lib/sentiment.ts` reference already in `DATA-FLOW.md`
  is still correct; behavior improved, contract unchanged.
- **Symbols** — `getTradingViewSymbol()` fixes: the Yahoo suffix list is now one
  shared `stripExchangeSuffix()` helper (was duplicated with drift across the
  quote/price-history routes, with duplicate `.AS`/`.TO` branches), suffix-only
  resolution works without a `market` hint (`0001.HK`→`HKEX:0001`, `7203.T`→
  `TSE:7203`), the crypto branch no longer produces `BINANCE:BTC-USDT` for
  `BTC-USD`, and the explicit FX mappings (`EUR=X` etc.) are reachable again —
  the generic `=X` branch had turned them into a non-pair `FX_IDC:EUR`. 12 tests.
  no doc change — internal mapping correction; the contract is unchanged.
- **Docs** — `skills/ARCHITECT.md`: corrected stale relics against the code —
  ADR-001 "no DB" and ADR-002 "live news" claims, the missing Investor Eye /
  connector routes and DB models in the architecture map, the pre-JDDS
  "Yahoo Finance + HTML fallback" scraper description, and the ~1900-line
  screener note (now the current module split).
  docs updated: `skills/ARCHITECT.md`
- **Build** — Every page appeared dead: a stale/corrupt `.next` build cache made
  `next start` serve a 500 and left the boot overlay stuck at 1% (it failed to
  load `./6764.js`). Code was sound (`tsc` + all 1140 tests pass); removing
  `.next` and rebuilding restored all tabs with zero console errors.
  no doc change — stale local build artifact, not a source change.
- **Investor Eye** — The `black` globe was too dark to read (a near-black texture under `lambert` collapsed into a featureless ball). Its palette is now mid-grey — ocean `#1a1c20`, land `#4b5058`→`#5a606a`, brighter coastline — lit with a higher ambient (0.85) and no shadowing. Measured mean luminance 55 vs 14 before; land now reads 84–119 against an ocean of 38.
- **Investor Eye** — Added a **STARS ON/OFF** toggle to the map view controls (`showStars`, persisted and captured in saved views). The starfield is UNMOUNTED rather than hidden so its rAF loop actually stops; with stars off a skin-matched CSS backdrop paints the sky.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`
- **UI** — The header **price ribbon** is now wider, background-free, and fully
  customizable. It fills the middle of the header (search stays fixed at `38%`),
  drops the card/glass fill so it reads as bare market chrome, and scrolls
  **left→right** (`from -50% to 0`, still seamless, hover-pause, reduced-motion
  aware). A gear opens a portaled popover to add any symbol (same DB
  autocomplete as the pin inputs), remove chips, or reset to defaults; the list
  is persisted in `src/lib/ribbon/store.ts`. Data routing is split by family:
  catalog commodities/FX from `market:commodities`/`market:forex`, everything
  else from a dynamic `/api/quote` topic. Extracted `src/lib/market-catalog.ts`
  as the single source of truth for the commodity/forex symbol lists (now also
  consumed by both API routes).
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Investor Eye** — Added a **surface skin switch** (`MapSkin`: `black` | `glow`)
  beside the MAP/GLOBE toggle, in both the hero header and the full-page dock, via
  one shared `map-view-controls.tsx`. `glow` (default) is a blue lit planet —
  translucent blue continents over the starfield, cyan coastlines, blue globe
  ocean/land, emission aura + bloom; `black` restores the first-draft flat
  terminal surface (no glow, no aura, still sky). Persisted, and captured in saved
  views. Globe textures are now keyed by skin (the old cache guard silently kept
  the blue planet after a switch).
- **Investor Eye** — Fixed the **pin glyphs**: earthquake/portfolio/risk drew as
  solid blobs because their cut-outs wound the same way as their outer shape
  (nonzero fill rule) and circles were drawn as a single near-full arc (renders
  off-centre); the catch-all `events` dot sat above the category layers
  (`zIndex` 30 > 25) and buried them; `wave`/`exchange` subpaths overlapped.
  Regression tests now assert the winding and the z-order.
- **Investor Eye** — Made the starfield **actually alive**: meteors spawn from
  0.6s then every 3–8s (was 6–18s, so the sky looked static), and the loop uses
  real elapsed time instead of an assumed 60fps (clamped so a backgrounded tab
  cannot teleport stars).
  docs updated: `docs/investor-eye-architecture.md` (§5n new; §5m marked partly
  superseded), `docs/NAVIGATION.md`
- **UI** — Added a **live price ribbon** to the app header beside the global
  search trigger. It is a thin view over the existing DataHub topics
  (`market:indices:US`/`CRYPTO`, `market:commodities`, `market:forex`) — no new
  API, polling, or cache. Missing symbols are omitted rather than placeholder-
  priced; clicking a quote dispatches a chart destination on the command bus.
  Marquee styles live in `globals.css` (untransformed glass wrapper + two-copy
  `-50%` track, disabled under `prefers-reduced-motion`).
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Command Center** — Added an **Investor Eye** widget to the dashboard widget
  catalog, so the normalized world-state event feed is available on the Command
  Center without switching to the Investor Eye screen. It is a thin view over the
  SAME DataHub state topics the full screen consumes (`investor-eye:state:<hours>`)
  — no second cache and no fabricated data; a failed/unavailable topic renders
  `UNAVAILABLE`. Configurable `range` (1H…30D) + `lens` (all/conflict/energy/trade/
  hazards). Registered at the end of `DASHBOARD_WIDGETS` because the persona
  templates address widgets by array index.
  docs updated: `docs/CHANGELOG.md`; skill `.opencode/skills/black-eclipse-workspace/SKILL.md`
- **Command Center** — Fixed the Investor Eye widget reading as broken while the
  first world-state assembly runs: the header status chip showed a red
  `UNAVAILABLE` dot during the (up to ~15s) cold build even though the body said
  "Loading world state…". The chip now shows a neutral `LOADING` state until the
  topic settles, and only then reports LIVE/CACHED/UNAVAILABLE.
  no doc change — presentation-state fix, contracts unchanged.
- **Investor Eye** — The globe gets a real visual system, and fixing it exposed two
  bugs that were blocking the whole screen.
  - **Look.** The globe was a flat, washed-out blue sphere. The surface texture now
    carries the design: near-black gradient ocean, dark land, a blurred coastline
    bloom, and a deterministic city-light stipple. Added a canvas starfield (three
    depth tiers + two nebula washes), a cyan `atmosphere` rim, and much lower
    ambient lighting — a high ambient was what turned the planet into a bright blue
    ball. Pins on the globe are now drawn **three times** (wide faint halo, tight
    coloured halo, white-hot core); the first attempt used one colour for core and
    halo and rendered as dark-centred donuts. 2D pins got a dark contrast ring and
    a severity-sized glow; trade routes got a translucent glow pass. Auto-rotation
    is deliberately off — the pins are click targets.
  - **Bug: a map-local loader covered the entire app.** `WorldMap` used
    `TopLoader`, which portals to `document.body` at `z-[45]`, so a still-loading
    map froze the whole application on a `95%` overlay (sidebar included). It is
    now scoped to the map box, with a 20 s globe-init ceiling that falls back to
    the flat map. Recorded as ADR-014.
  - **Bug: `ReferenceError: TopLoader is not defined`.** Replacing the loader left
    one stale reference inside a `useMemo`; the error boundary then left the frozen
    frame on screen instead of surfacing an error.
  - **FIRMS reliability.** The 24h global CSV occasionally exceeded the transport's
    10 s cap, silently emptying the hazard layer for a whole cycle. Added one
    bounded retry, for transient transport errors only.
  - **Verified live:** all 4 sources healthy, 794 events / 21 markets, and the
    Shipping/Energy/Commodities layers toggling correctly.
  docs updated: `docs/investor-eye-architecture.md` (§5m), `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`, `docs/DECISIONS.md` (ADR-014)


- **Charts** — Replaced oversized Settings previews with fixed-height illustrative candles/volume, a restrained area line, and an ordered three-color treemap; all configured colors remain visible without changing widgets, palettes, or data. Removed redundant preview revision state.
  no doc change — visual-only Settings refinement, contracts unchanged.

- **Keyboard** — Fixed a real shortcut conflict: the Agentation visual-feedback
  toolbar registered a `document`-level handler that unconditionally claimed plain
  `L`, `P`, `H`, `C`, `X` and `S`, so `Shift+L` (focus layouts / grid menu),
  `Shift+C` (compact rows) and screen `S` (local search) never reached the app.
  It is now opt-in via `NEXT_PUBLIC_AGENTATION=1`. The widget library and widget
  config drawers now close with Escape, which they previously ignored while still
  blocking page shortcuts. Verified in Chrome against a running dev server: 20/20
  keyboard checks pass (function keys for every screen, `Ctrl+/` help, `Shift+E`,
  `Shift+W`, `Shift+N`, `Shift+L`, `S` local search, Escape layering).
  docs updated: `docs/QUICKSTART.md`, `docs/CHANGELOG.md`.

- **Keyboard** — Faster workflows, and the shortcut help panel now scrolls.
  - **Scroll fix.** The `Ctrl+/` help panel could list more shortcuts than fit,
    but the results region had no working scroll area (a grid child without
    `minmax(0,1fr)` cannot shrink), so lower entries were unreachable. The dialog
    is now an explicit grid with a `minmax(0,1fr)` scroll row; verified overflow
    scrolls in Chrome.
  - **Action palette.** `Ctrl+K` now *does* things, not just navigate. Real
    commands: set a price alert for a symbol, add a symbol to the watchlist,
    open a chart, open the Journal or Journal Calendar, show today's economic
    events, open/export a specific fund, export all portfolios, and jump to any
    Settings section. Every command reuses an existing handler — the previously
    dead `createQuickAlert` / `addToWatchlist` / param-command path is now wired,
    and results state their target. No delete/reset command exists by design.
  - **List navigation.** New shared `useListNavigation` hook (stable-ID selection,
    never index) wires `↑/↓` + `J/K`, `Home/End`, `Enter`, `Escape`, and `[`/`]`
    into news, screener stocks/crypto, alerts, journal trades, and the Investor
    Eye feed. Typing is never hijacked and only the visible screen responds.
  - **Chart keys.** Focused charts gain `V` volume, `0` reset zoom, `=`/`+`/`-`
    zoom, and `Alt+←/→` pan. Timeframe/indicator/compare pickers were skipped:
    their open-state is internal to toolbar menus, so there is no handler to call.
  - **Sub-tabs and back.** `Alt+1..Alt+8` select Journal sub-tabs, `Alt+1..3` the
    Economics modes (with `Alt+0` for the last), and `Alt+←` steps back through a
    bounded 20-entry screen history — the app has no router, so this is its only
    back affordance. History is in-memory and shell-tab only.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`, `docs/OVERVIEW.md`
  (keyboard-ownership section), `docs/QUICKSTART.md`.

## 2026-09-16

- **Chart Workspace** — Removed the green box that appeared around the whole page
  in full page / fullscreen mode. Root cause: `globals.css` sets
  `outline-color` on `*` (via `@apply outline-ring/50`), and the full-page and
  fullscreen overlays are keyboard FOCUS SINKS — they are programmatically
  `.focus()`ed so their shortcut scope is active. The moment `:focus-visible`
  matched (any keyboard interaction: Tab, Ctrl+Enter, or F11 as reported), the
  browser painted its default focus ring around the `fixed inset-0` element in
  that inherited colour. Added `outline-none` to both overlays and the workspace
  root; verified no viewport-sized outline remains.
  no doc change — bug fix, no contract or architecture change.

- **Portfolio** — Repaired `fund-manager.tsx`, which had been corrupted by a bad
  global `p`/`P` → `a` replacement (the file contained zero `p` characters, e.g.
  `import` → `imaort`), breaking `/` and every API route with 500s. Reconstructed
  from HEAD and re-applied the seven intentional edits layered underneath
  (chart-palette benchmark colours, `usePageShortcuts` + `Shift+N` create-fund
  shortcut, keyboard scope on the root), then fixed a real type error in that
  work: `palette.series` → `palette.lines.series`. Diff vs HEAD is exactly the
  15 insertions / 7 deletions of the intended change, with no corruption residue.
  no doc change — corruption repair, intent preserved.

- **Build** — `devIndicators: false` in `next.config.ts`. The Next.js dev-tools
  indicator floats over the bottom-left corner and intercepts pointer events,
  which blocked automated UI checks against the controls underneath it.
  no doc change — dev-only tooling.

- **Charts** — Palette is now sectioned per widget type (candles / lines / heatmap) so presets and edits no longer recolor everything at once. Settings → Charts shows a dedicated card per section with its own preview, swatch presets, and per-section reset; storage moves to `be_chart_palette_v2` (old v1 ignored). All consumers migrated to `palette.candles.*` / `palette.lines.*` / `palette.heatmap.*`.
  docs updated: `docs/CHANGELOG.md` (contract change noted here; no separate doc page covers palette internals)

- **Settings / Investor Eye** — A dedicated API-keys menu, working data layers, and
  readable map pins. Three separate problems, all reported against the real UI.
  - **API Keys menu.** Settings had no place to enter a credential — the connector
    wizard only accepts an arbitrary REST endpoint. New `provider-keys.ts` + a
    `settings.api-keys` section list all 24 credentials BlackEclipse can consume,
    grouped by what they power (AI / Market / Crypto / Economics). Keys are
    encrypted with the existing AES-256-GCM path and stored in `SystemConfig`;
    the value is never returned to the browser (only a masked hint). "Test" makes
    a real request and reports the real HTTP status — an invalid key returns 401,
    verified live, rather than a success inferred from the key existing. A key set
    by an environment variable is shown as authoritative and read-only, and
    `applyStoredKeysToEnv()` copies stored keys into `process.env` at boot so
    every existing consumer works unchanged. Removing a stored key only clears a
    variable this process populated from the vault, so a deployment env var can
    never be destroyed.
  - **Layers were showing a fraction of the data.** `classify.ts` assigns ONE
    event type but MANY channels, and the domain layers matched on type only, so
    an event typed `conflict` carrying the Shipping channel was invisible to the
    Shipping layer. Measured live in a 24h window: 11 shipping-typed vs 28 with
    the Shipping channel, 29 vs 46 for energy. Layers now match type **or**
    channel, and two new layers (`shipping`, `commodities`) plus channel-driven
    trade lines surface the physical-economy signal that was already in the
    database.
  - **Pins.** The old markers were 6–13px flat dots with a thin border and read as
    noise on the dark map. Pins are now larger (8–18px), carry a dark contrast
    ring so neighbours never bleed together, and a severity-sized coloured glow so
    urgency is visible before hovering.
  - **Also fixed:** the dev server had a stale Prisma client from before the
    `category` column existed, so FIRMS rows silently failed to persist while the
    map still showed them. Restarting is the fix; `persistEvents` swallowing the
    error is why it was invisible.
  docs updated: `docs/investor-eye-architecture.md` (§5l), `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`, `docs/DECISIONS.md` (ADR-013)

- **Workspace / Charts** — Add scoped workspace actions and chart focus ownership; prevent drawing keys from reaching other charts or deleting panels, guard typing and hidden screens, and confirm keyboard panel removal. no doc change — existing shortcut and workspace contracts reused.

- **Charts** — Fix broken palette integration left by interrupted edits: undefined `UP`/`DOWN`/`primary`/`colors`/`palette`/`GRADIENT`/`cn` references in journal charts, economics panel, Monte Carlo, and heatmap widgets crashed the build when selecting colors. Journal charts, economics panel, Monte Carlo, and heatmap treemap now consume the shared chart palette with live update dependencies; typecheck clean, 1,078 tests pass. no doc change — internal repair of in-flight feature, contracts unchanged.

- **UI** — Wire scoped screen shortcuts to existing creation forms, search, filters, customization and refresh; guard Investor Eye navigation against hidden screens, editing, dialogs and extra modifiers. no doc change — existing keyboard hook contract reused, no architecture or setup changes.

- **Keyboard** — Ship configurable function-key defaults, Ctrl/Cmd+/ searchable help and shared exact-match, visible-scope dispatch to prevent hidden-screen and typing conflicts; preserve customized sidebar settings and reserve F11. Tests and typecheck pass; lint reports warnings only. docs updated: `docs/ARCHITECTURE.md`, `docs/OVERVIEW.md`.

- **Charts** — Add eight palette presets (Black & white, Silver, Sunset, Arctic, Forest, Candy, Neon, Blue & orange) and preview swatches for more visual variety; monochrome uses charcoal instead of invisible black on dark charts. no doc change — presentation presets only, storage and chart contracts unchanged.

- **Charts** — Native Eclipse charts subscribe to palette changes and resolve indicator, structure, and comparison colors at render time without resetting zoom or rewriting saved drawings; remove the permanent brand-color cache. no doc change — existing provider and state contracts unchanged.

- **Investor Eye** — Data-source governance and NASA FIRMS. The spec's licensing
  requirement had no home, and the hazard layer had a single source.
  - **Source catalog.** New `source-catalog.ts` records licence, licence/terms
    URL, commercial-use, API-key requirement, attribution, rate limit and
    freshness per source. It is separate from the adapters on purpose — a licence
    question should not require constructing a fetcher. Tests assert every
    registered source has an entry (and vice versa) and that `requiresApiKey`
    agrees with the adapter, so a source cannot ship without declaring its terms.
  - **FIRMS connector.** Keyless global archive CSV (the Area API needs a
    `MAP_KEY`, which would break zero-config). ~25,600 raw single-pixel
    detections become ≤400 grid clusters at ingestion, carrying real detection
    counts and summed FRP. Three bugs fixed while building it: the grid needs a
    `cos(lat)` correction or polar fires fragment away; empty CSV cells must be
    rejected before `Number()` turns them into 0; and a feed URL must not be
    stamped as a source `url`, because `dedupKeyFor` treats source URLs as article
    identity and all 400 clusters collapsed to one event.
  - **Exact country attribution.** `admin-boundaries.ts` runs point-in-polygon
    against the same Natural Earth GeoJSON the map already ships. Centroid
    matching attributed 62/400 live fire clusters; point-in-polygon 167; using the
    boundary asset's own ISO2 when the curated gazetteer lacks the country, 397.
  - **Hazard split.** A provider-stated `category` (`earthquake`/`fire`)
    separates the `fires` layer from `weather`, refuses to merge different
    categories during clustering, and is exclude-based so pre-existing rows keep
    their original layer with no migration.
  - **Health UI.** `/api/investor-eye/health` joins governance onto `SourceRun`
    accounting and returns attribution lines; `SourceHealthPanel` renders the
    spec §19 columns and flags a runnable-but-undeclared source as a gap.
  docs updated: `docs/investor-eye-architecture.md`, `docs/ARCHITECTURE.md`,
  `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`, `docs/DECISIONS.md`

- **Journal** — Calendar follow-ups. The contribution heatmap was too small and
  the month grid only existed on the Calendar tab.
  - **Heatmap is now big.** `MiniCalendar` gained a `fill` mode: the grid spans
    the card, cells stay square via `aspect-ratio`, and a `maxCell` cap (30px)
    stops a very wide card from producing ~50px squares that dominated the page.
    Default widened to 39 weeks / nine months. Measured 30×30 cells across a
    1316px grid (was 11px cells in a 595px half-width grid).
  - **Month calendar now on the Overview too**, via a new `MonthCalendarCard`
    (its own prev/next + month stats) so both tabs show year AND month views.
  - **Fixed a timezone bug in the month label.** `toLocaleString` without a
    `timeZone` formats in the browser's local zone, so `Date.UTC(2026, 8, 1)`
    (Sept 1 UTC) rendered as **"August 2026"** west of Greenwich — the label sat
    a month behind the grid it described. New `src/lib/journal/dates.ts`
    (`formatMonthLabel` / `formatDayLabel` / `weekdayShort`) formats in UTC, and
    the month card now opens on the most recent trade's month rather than the
    local clock. 7 tests pin this across five timezones.
  docs updated: `docs/NAVIGATION.md`

- **Investor Eye** — Situation recurrence and honest corroboration.
  - **Situation timeline** (`situations.ts`, pure). A single event in isolation is
    not intelligence: an explosion near Hormuz means something different when it
    is the fourth incident there this week. Events are grouped into SITUATIONS by
    type + country, and the dossier shows the count, span, peak severity, a
    severity trend and whether it is escalating.
    - **Bucketed by COUNTRY, not place string.** Measured on live data, bucketing
      by raw place fragmented one situation four ways ("US", "United States",
      "Washington", "Washington, D.C.") because providers disagree on
      granularity.
    - **And then labelled by country, not by the top place.** With country
      bucketing the first working version labelled 147 US conflicts as
      "Washington, D.C.", which implied they were all there. The label is now the
      country (what the count actually covers), with the most-common place and
      the number of distinct places offered as separate context — "140x conflict
      in United States · across 61 places, most often Washington, D.C.".
    - "Escalating" requires **3+ occurrences and a genuinely rising trend** (two
      points is a comparison, not a trend) and is explicitly described as a
      description of the trend so far, not a forecast.
  - **Corroboration badge now counts distinct OUTLETS.** After the
    article-identity fix one article can legitimately back several captured
    sources, so a raw `sourceCount` overstated corroboration. The badge and the
    Sources block now report distinct outlets and distinct article URLs, and say
    "Multiple citations of the same article — one outlet" when that is the case.
  - `GET /api/investor-eye/situations` reads the same stored feed the map uses, so
    a situation can never disagree with the events on screen.
  - 16 new `situations` tests, including the two regressions above.
  - Verified: 952 tests pass, `tsc` + eslint clean, zero console errors in Chrome.
    `jdds.db` NOT committed — no schema change.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Journal** — The journal was empty on every tab. Root cause: it is DB-backed
  (unlike the localStorage portfolio demo), and although a seeder existed it had
  never been run or wired into boot — the committed `jdds.db` held **0 `Trade`
  rows** and two duplicate `JournalProfile` rows from a `getOrCreateProfile()`
  race. Fixed by making seeding real and honest:
  - **`src/lib/journal/demo.ts`** is now the single generator, invoked from boot
    (`instrumentation.ts`) and from `scripts/seed-journal.ts` (now a thin
    wrapper). It seeds ~90 days of deterministic trades so every tab has content.
  - **Provenance, not mystery data.** Added `Trade.source` (`'manual' | 'demo'`)
    and a journal banner that says how many rows are sample data, with a
    one-click "Remove demo data" that deletes ONLY `source: 'demo'` rows. A
    `SystemConfig` marker stops the seeder re-adding what was deliberately
    cleared — verified across a server restart.
  - **Fixed the profile race** so duplicates collapse to the oldest row instead of
    accumulating (2 → 1 in the existing DB).
  - **Coherent risk sizing.** Positions are now `riskTarget / stopDistance`
    against the profile's `accountSize × riskPerTrade`, so risk per trade varies
    gently (CV ≈ 0.10) instead of ~8× across symbols — without this the risk
    analytics (risk consistency, the 1% rule, expectancy in R) were noise.
  - **Mini calendar rebuilt** as a compact GitHub-style week grid: fixed 11×11
    cells with signed R-intensity buckets. Previously the cell had no width class,
    so `grid-cols-10` stretched each one to fill its column and the "squares"
    became large rectangles. Intensity is now shared with the year heatmap via
    `src/lib/journal/intensity.ts`.
  - Verified in-browser: all eight journal tabs render real derived content (e.g.
    "Best session: Asia +19.70R", "Behavioral leak: Revenge −4.03R", expectancy
    +0.26R), calendar cells measure 11×11, zero console errors. 9 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/OVERVIEW.md`

- **Investor Eye** — "Explain this event": the AI analyst, where the question is
  asked.
  - The 7 read-only Investor Eye agent tools already existed but were reachable
    only from the chat, so a user had to leave the event and re-describe it. The
    dossier now has an **Analyst** section that runs the world analyst against
    THIS event's structured record.
  - **Grounded, not generative.** `event-record.ts` renders the event as a
    compact briefing (headline, type, location AND its precision, coordinates,
    countries, actors with readable type codes, CAMEO/Goldstein, text-derived
    channels/commodities/sectors marked as derived, relevance, confidence labelled
    "NOT certainty", sources, description) and the model may also call the
    read-only tools. Absent fields are omitted rather than printed as
    placeholders, which would invite the model to fill the gap.
  - `POST /api/investor-eye/explain` is guarded and rate-limited (12 per 5 min)
    as it drives LLM calls. With no provider configured it returns **503**, and
    the panel says so — it never pretends to work offline (verified: HTTP 503 →
    "No AI provider is configured").
  - The route handler is thin; the prompt-building logic is pure and unit-tested
    (6 tests), because the SHAPE of what the model receives is a correctness
    concern — if actors or provenance silently vanished, the analyst would start
    guessing.
  - Verified: 927 tests pass, eslint clean, zero console errors in Chrome.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Investor Eye** — Where things are plotted is now right, and honest about it.
  - **Policy events were landing in Kansas.** `CountryDef.lon/lat` is a country's
    GEOGRAPHIC CENTROID, so "the Fed raises rates" plotted at the USA centre, and
    "Brazil's central bank cuts rates" landed in the Amazon. Policy, monetary and
    diplomatic news is reported FROM the capital, so `geo-resolve.ts` now prefers,
    in order: a named place → an exact provider coordinate → the CAPITAL (for
    policy event types only) → the country centroid. A new `CAPITALS` table (81
    entries) supplies the anchor without disturbing the centroid, which map fills
    and country highlighting still rely on. `conflict`, `military`,
    `natural_disaster`, `energy` and `shipping` are deliberately EXCLUDED — those
    have a real physical location that is usually not the capital.
  - **Measured on live data:** news-source country-centroid share fell **83% →
    34%**; across all events, `place` anchors rose 11 → 44, `centroid` fell 76 →
    67, and **88 events now correctly anchor to a capital**.
  - **A guess no longer looks like a fix.** Country-centroid points are drawn as
    hollow, dashed, slightly smaller markers, with a legend entry ("country-centre
    only") and a tooltip line stating the location is not a confirmed position.
    The dossier reports it too (`country capital (policy event)` etc.).
  - **Existing rows are upgraded on read.** `reResolveEventLocation` re-derives
    the anchor when an event is loaded, so historical rows pick up the capital
    rule without a database migration — resolution is deterministic and cheap.
    An exact provider coordinate is never second-guessed.
  - **Gazetteer extended** with ~120 places that appear in real headlines: ports
    (Alexandria, Aqaba, Mombasa, Djibouti, Port Harcourt, Novorossiysk,
    Vancouver…), rivers that shape logistics (Danube, Rhine, Yangtze, Mississippi,
    Paraná), and commodity regions (Antofagasta, Fort McMurray, Niger Delta,
    Ordos, Sudbury). The gazetteer test caught that **Djibouti, Somalia and
    Eritrea were missing from the country table entirely**, so Red Sea shipping
    events had nowhere to plot; all three added.
  - 15 new `geo-resolve` tests, incl. deliberate negative cases (a physical event
    must NOT be forced to the capital; a provider fix must never be overridden).
  - Verified: 921 tests pass, `tsc` + eslint clean, zero console errors in Chrome.
    `jdds.db` NOT committed — no schema change (coordinates are derived on read).
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Portfolio** — Added three risk widgets to the fund workspace: **Portfolio
  Heatmap** (treemap — area by position value, colour by day move on the shared
  ±3% gradient, with fullscreen), **Correlation Matrix** (ECharts heatmap of
  pairwise return correlation) and **Risk Matrix** (per-holding volatility, beta
  to the portfolio, and each position's contribution to total risk). All three
  register in `FUND_WIDGETS`, the icon map and the default layout.

  Accuracy work the widgets depend on — the matrix is only meaningful if these
  hold:
  - **Date alignment, not position alignment.** Different markets have different
    trading calendars, so `closes[i]` is not the same day across symbols;
    correlating position *i* against position *i* silently compares different
    calendar days. `src/lib/portfolio/matrix.ts` computes every statistic on the
    **intersection of dates** for the pair concerned. Pairs with <20 shared
    returns render `·`, never a plausible-looking `0.00`.
  - **Correlation is currency-neutral.** Returns are ratios, so native-currency
    closes give identical correlations to USD-converted ones — correct for a
    mixed USD/PKR/INR book with no FX step (documented, including the limitation
    that a currency's own move is a separate exposure).
  - **Risk decomposed properly.** Euler decomposition over the same Σ used for
    the matrix: σ_p=√(wᵀΣw), CTRᵢ=wᵢ(Σw)ᵢ/σ_p, shares sum to 100%. Variance is
    clamped at 0 (pairwise-complete correlation isn't guaranteed PSD) so a
    negative "risk" can never surface.
  - **Fixed a real desync bug** in `use-price-histories`: it filtered `closes`
    but mapped `dates` unfiltered, so any bar with a bad close shifted every
    later date onto the wrong close.
  - **Fixed market resolution.** `marketHintFor` defaulted everything unknown to
    US, so an Indian or UK holding was requested without its exchange suffix and
    returned no series at all. `/api/price-history` now treats the `market` param
    as a hint and, on a miss, asks JDDS which markets list the symbol (one
    indexed query) and retries with the real one.
  - **Fixed currency handling.** `useLiveQuotes` discarded `/api/quote`'s real
    `marketId` and re-derived a USD/PKR binary from a 16-symbol allowlist, so an
    INR holding was valued 1:1 against the dollar. The engine now converts any
    currency at its live `fxToUsd`, falls back to a documented approximation
    table when a rate is missing, and flags the holding `fxMissing` so the UI can
    call that USD value an estimate.

  Verified against an independent Pearson implementation on real series (values
  matched to 3dp) and in-browser on the seeded Core Growth fund: all three
  widgets render, zero console errors. 39 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/OVERVIEW.md`,
  `README.md`

- **Investor Eye** — Article metadata recovery, readable titles, and a
  correction to a claim in the entry below.

  - **Correction.** The entry below says the news-corpus enrichment gave events
    "real headlines" and cites 202 of 461. That number was the count of
    `news`-source events, which are articles and always had headlines — the
    enrichment itself contributed almost nothing. Measured against the live DB,
    the normalized-URL join matched **27 of 2,524 GDELT events (1.1%)**: the RSS
    corpus and GDELT's article set barely overlap. The claim was misleading and
    is superseded by this entry.
  - **The real fix: read the article.** `article-meta.ts` (pure parsing) +
    `article-meta-fetch.ts` (guarded network + cache) fetch a source URL through
    the shared `safeGet` and extract `og:title` / `og:description`, falling back
    to `twitter:title`, `<title>` and `<h1>`. Only the `<head>` is searched so a
    body quoting "og:title" can't masquerade as metadata; bot-walls, consent
    screens and site-name-only titles are rejected. `GET /api/investor-eye/article`
    is guarded (outbound I/O), tries up to 3 source URLs, and caches per URL in
    bucketed `SystemConfig` JSON so **any URL is read at most once, ever**.
    Lazy — fetched when the dossier opens, so the ~15s assembly is unchanged.
    Verified live: a GDELT event recovered
    *"Chinese Companies Used Crypto Exchange to Launder Iran's Black-Market Oil
    Sales"* (The Epoch Times) with a description and actors.
  - **Article-identity clustering (found while building the above).** GDELT codes
    **one row per actor dyad**, so a SINGLE article becomes many events — one
    produced **37**. Measured: **62.7% of events shared an article URL**. The
    signature gate (below) correctly stopped unrelated stories fusing, but left
    this fragmentation. Since two records citing the same article ARE the same
    story, `shouldCluster` and `dedupKeyFor` now treat a normalized article URL as
    definitive identity (scoped by event type, so one article read as both a
    `sanction` and a `trade` keeps both). Events in a 24h window **461 → 338**,
    and corroboration became real again (Seeking Alpha + Investing.com + CNBC on
    one story). 40 cluster/dedup tests.
  - **Readable titles** (`formatEventTitle`). GDELT's synthesized
    `ACTOR1 / ACTOR2 — City, Country` read as code fragments
    (`POLICE — Washington, District of Columbia, United States`). It is now
    restructured into a sentence — *"POLICE in Washington, District of Columbia,
    United States"* — from the same fields, inventing nothing. Applied in the
    dossier header and the live feed; a real headline passes through untouched,
    and a headline merely containing a "/" is not rewritten. 10 tests.
  - `article-meta.test.ts` (17 tests) covers entity decoding, attribute-order
    tolerance, body-meta rejection, bot-wall detection and suffix stripping.
  - Verified: 906 tests pass, `tsc` + eslint clean, zero console errors in Chrome.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Investor Eye** — Event dossiers, real headlines, and the clustering bug that
  was corrupting events. Includes a schema change (see the DB note below).
  - **Clustering was fusing unrelated stories.** A real event in the DB had 16
    "sources" including a bicycle-retailer article and a construction PR. Root
    cause: `shouldCluster` merged on `sameCountry && similarity >= 0.15`, and
    GDELT titles are synthesized as `ACTOR / ACTOR — City, Region, Country` — so
    every event from one city shared that tail and cleared the threshold for
    free. Three fixes: a new `clusterSignature` on the event contract (GDELT's
    GLOBALEVENTID, USGS's feature id) that forces merge-on-exact-match only; the
    location tail is stripped before tokenizing; the same-country floor moved to
    0.3. Measured on real data: **max sources 16 → 3**. `dedupKeyFor` now uses
    the signature too — without that, distinct signed events hashed identically
    and persisted as duplicates (22 of 473). Plus a `collapseDuplicateKeys`
    last-line-of-defence. 40 cluster/dedup tests.
  - **Real headlines** (`enrich.ts`). GDELT's bulk export carries no headline at
    all — only actor strings — which is why clicking a conflict showed a place
    name and nothing else. Events are now enriched from the ALREADY-ingested
    `NewsItem` corpus by normalized `host+path` key (raw URL matching recovered
    0/500; normalization recovers a real fraction). **202 of 461 events now have
    a genuine headline.** Never synthesized: an unmatched event says so.
  - **The dossier** (`event-panel.tsx`, rebuilt). Eight sections, each labelled
    with its own epistemic status: **What happened** (real headline/description,
    or an explicit "no headline available from this structured feed") · **Actors**
    (GDELT's Actor1/Actor2 with human-readable type codes — parsed and thrown
    away before) · **Where & when** (place, coordinates, and HOW precise:
    provider / named place / country centre) · **Detail** (per-type: magnitude,
    actor dyad, commodities) · **Observed** · **Why it matters** · **Potential
    exposure** · **Market reaction** · **Sources** · **Timeline** (source
    timestamps, earliest first). The header carries a corroboration badge
    (single source / corroborated / confirmed).
  - **Persisted details**: `headline`, `description`, `actors`, `providerCodes`,
    `placeName`, `geoMethod` columns on `GeopoliticalEvent`. `persistEvents` now
    backfills the row `id` onto the in-memory events — without it the state had
    no ids and the entity-links endpoint 404'd on every open.
  - Also fixed: `assembleState` with `refresh=1` returned stale cache instead of
    awaiting the rebuild, so the refresh button appeared to do nothing.
  - **Icon**: Investor Eye now uses `ScanEye` (sidebar, command palette, screen
    header, full-page map) instead of the generic `Earth`/`Globe`.
  - Verified: 840 tests pass, `tsc` + eslint clean, zero console errors in
    Chrome; dossier checked against live data.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Investor Eye** — Six capabilities: observed price reaction, event alerts,
  place-level geocoding, saved views, keyboard navigation, source health.
  - **Price reaction** (`lib/investor-eye/reaction.ts`, pure). Measures what the
    relevant instrument ACTUALLY did after an event — close-to-close returns at
    +1/+5/+20 sessions from real `Candles` rows, with the baseline date, the
    trading days of post-event history, and an explicit reason when it can't be
    measured. This is the observable counterpart to "potential exposure": the
    exposure block says what COULD matter, this says what the market did. Never
    predictive, never synthetic. `GET /api/investor-eye/reaction` +
    `ReactionPanel` in the event panel. Verified live: an 2026-09-11 Alaska
    quake returned `^GSPC +1=-0.483% +5=-0.535%`; events from today correctly
    return "not yet measurable" instead of a fake zero. 11 tests.
  - **Event alerts** (`lib/investor-eye/alert-rules.ts`, pure predicates).
    "Tell me when…" over the world feed: event types, severity floor, confidence
    /relevance floors, countries, commodities, keywords, and an optional
    lat/lon/radius fence. `matchRule()` returns the REASONS a rule fired (never
    a bare boolean), so an alert is always explainable. Persisted as
    `SystemConfig` JSON — no schema change — through a guarded
    POST/DELETE, with 5 preset rules. An empty rule refuses to match rather than
    firing on everything. `AlertsPanel` wired into the detail row. 22 tests.
  - **Place-level geocoding** (`lib/investor-eye/places.ts`, ~130 curated
    places). News-derived events only had a country, so they plotted at the
    COUNTRY CENTROID — "United States" pins landed in Kansas and made the map
    read as wrong. A curated gazetteer of financial centres, major ports,
    chokepoints (Hormuz/Suez/Malacca/Bab-el-Mandeb), and energy/industrial hubs
    now anchors the event where the headline says it happened; the country hint
    disambiguates, and matching is word-boundary so "china" never matches
    inside another word. Chokepoints are weighted highest because they drive the
    logistics story. 9 tests — which caught that `PA` and `PS` were missing from
    the country gazetteer, so Panama Canal / Gaza events had nowhere to plot;
    both added.
  - **Saved views** (`saved-views.tsx` + store): snapshot layers + window +
    projection + metric as a named posture ("Red Sea shipping watch") and
    restore in one click. Re-saving a name replaces it; restoring reconciles
    layer ids against the registry so a retired layer can't come back. View
    state only, never data.
  - **Keyboard navigation** (spec §34): `j`/`k` or ↓/↑ step through the
    newest-first event feed and open each one — the map is usable without a
    mouse. Ignored while typing or with a modifier held.
  - **Source health** (spec §15): `SourceHealthPanel` renders the real
    `SourceRun` accounting from `/api/investor-eye/health` — state, latency,
    last run, accepted/received — with a throttle shown as its own state, never
    folded into "error".
  - Verified: `npm run test` 816 passed, `tsc` + eslint clean, zero console
    errors in Chrome; reaction and alert APIs exercised against live data.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Investor Eye** — Removed the doubled close button on selection panels.
  `PanelShell` drew its own "×" while the Event/Country/Company panels already
  render one in their header, so the corner showed TWO overlapping crosses.
  `PanelShell` is now a pure frosted frame (documented as owning no dismiss
  affordance); the inline market card gained the close button it was relying on
  the shell for. Verified in Chrome: exactly one close button, still dismisses.
  no doc change — pure presentational fix, contracts unchanged.

- **Investor Eye** — Fixed the tooltip crash, added a loading state, and closed
  the dead gap in the analysis row.
  - **Crash on every map hover.** `tooltipFormatter` passed ECharts' own wrapper
    (`{name, value, severity, _datum}`) straight to `layer.tooltip()`, so
    `eventTooltip` read `undefined.eventType` — "Cannot read properties of
    undefined (reading 'eventType')". The click path already unwrapped `_datum`;
    the tooltip never did. Extracted `unwrapDatum()` (`map-echarts.ts`) and used
    it in both, plus a defensive guard in `eventTooltip` so a malformed datum
    degrades to a minimal tooltip instead of taking the map down. The bug was
    invisible to `tsc` (the payload is `unknown` at the ECharts boundary), so
    `map-echarts.test.ts` now drives the real formatter with wrapped payloads —
    8 tests, including the globe `[lon, lat]` altitude shape.
  - **Loading state.** The map now shows a centred dot-grid loader
    ("Loading world state · 24H window") over the canvas while the first
    world-state fetch is in flight, and the Live Event Stream shows its own
    loader. Previously the hero was simply blank for the ~15s cold assembly.
  - **Dead gap removed.** The analysis row was a 3-track grid, which reserves
    the height of its TALLEST child in every track — so the short
    "What Changed" column left ~300px of empty space. Replaced with CSS
    multi-column masonry (`lg:columns-3` + `break-inside-avoid`), so each panel
    packs directly under the previous one.
  - Verified in Chrome: hovering an event pin renders the tooltip, clicking it
    opens the Observed/tooltip detail panel, clicking a **conflict** pin works,
    zero console errors. `npm run test` 774 passed, `tsc` + eslint clean.
  docs updated: `docs/investor-eye-architecture.md`

- **Investor Eye** — Fixed the reported breakage (invisible globe, dead clicks,
  DATA UNAVAILABLE flapping, broken lower layout) and added conflict news.
  Diagnosed by loading the real page in Chrome, not by inspection:
  - **Globe was a blank sphere.** `echarts-gl`'s `globe` takes a raster
    `baseTexture`, not a `map`; the previous fix replaced the default bright
    texture with a 16×16 *solid dark* PNG — dark sphere on a dark page, so it
    read as floating dots. It now draws a real equirectangular world texture at
    runtime from the SAME GeoJSON the 2D map uses (`app-geo.worldGlobeTexture`:
    dark ocean `#0b1220`, lighter land `#2b3442`, cyan coastlines, graticule).
    Two bugs found while building it: `geometryRings` returned rings for a
    Polygon but polygons for a MultiPolygon (off by one nesting level, so
    nothing drew), and `scatter3D` reads a third coordinate as ALTITUDE — the
    2D-style `[lon, lat, value]` lifted pins into radiating spikes. 3D series
    now send exactly `[lon, lat]`.
  - **Clicking conflict/weather/energy pins did nothing.** `filterEventsLayer`
    (which builds all three category layers) set only a tooltip, never an
    `onClick`, so the category pins — the ones users click to ask "what is
    this?" — were inert. `buildTradeLayer` had the same gap. All now take an
    `onSelect` and `buildAllLayers` wires it.
  - **"DATA UNAVAILABLE" flapping.** `/api/investor-eye/state` awaited a cold
    assembly (~15–18s measured) even when a good previous state existed, and the
    client equated `data === null` with unavailable — including while the first
    fetch was still in flight. `assembleState` is now true stale-while-revalidate
    (fresh → stale + background rebuild → persisted last-known + rebuild → await
    only when there is genuinely nothing), labelled `CACHED` with a `refreshing`
    flag. The screen distinguishes LOADING / LAST KNOWN · REFRESHING /
    UNAVAILABLE. Confirmed in-browser: no flapping, banner reads
    "LAST KNOWN HH:MM UTC · REFRESHING".
  - **Lower layout rebuilt.** The selection panel used to render BELOW the fold,
    which is why a click appeared to "do nothing". The hero is now a map +
    360px right rail holding the selection panel and a new **Live Event Stream**
    (`live-feed.tsx`: time, type badge, severity dot, countries, source link,
    click-to-select, lens tabs with counts); "Explore the world" is gone. The
    map and rail share one bounded height so the rail no longer overflows.
  - **Conflict news.** Added five conflict-scoped wires (`gn-conflict-now`,
    `-mideast`, `-ukraine`, `-shipping`, `-coup`, tier 1, category `WAR`) so the
    Conflict lens is dense rather than relying on GDELT's CAMEO coding alone;
    the existing news adapter turns them into events unchanged.
  - 3 new tests (category-layer onClick wiring, trade-line selection, legend/
    registry consistency). Verified: `npm run test` 766 passed,
    `npx tsc --noEmit` clean, eslint clean, zero console errors in Chrome.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Investor Eye** — Full-page "map only" mode + a colour-coded layer system.
  - **Full-page mode** (`full-page-map.tsx`): an immersive presentation of the
    *same* surface — the world fills the viewport, with a top strip (identity,
    event/market counts, DATA UNAVAILABLE state, MAP/GLOBE, Esc-to-exit) and a
    bottom dock (colour-coded layer chips + time window + the selected event as a
    floating drawer). Reuses `MapLayer[]`, the store and `EventPanel`; it is a
    view, not a second screen. Portaled to `document.body`, page scroll locked,
    and `fullPage` is view state only — deliberately not persisted, so reopening
    never traps the user in full screen. Reachable from the header and from a
    "Map only" affordance on the map surface.
  - **Colour-coded tabs / layers**: `LAYER_META` now carries a group, accent
    colour, marker shape and one-line hint per layer, with a `LAYER_GROUPS`
    registry (Events · Hazards · Energy & Trade · Economy · Markets). The layer
    controller renders grouped, colour-coded chips plus a marker-shape legend;
    the timeline colours each time window by length and adds a severity rail
    legend. Point layers pass their registry symbol to ECharts, and
    `conflict`/`weather`/`energy`/`portfolio` are tinted by category instead of
    the old sign-based colouring — so categories no longer rely on colour alone
    (spec §8 / §34). `timeline.tsx` and the controller were rewritten.
  - 3 new registry tests; `.glass-card`/`-subtle`/`-drawer`/`-button` used
    throughout (no raw blur). Verified: `npm run test` 763 passed,
    `npx tsc --noEmit` clean, eslint clean.
  docs updated: `docs/investor-eye-architecture.md`, `docs/NAVIGATION.md`

- **Charts** — Fixed indices never rendering on charts (S&P 500, Dow, FTSE 100,
  Nifty 50, KSE 100, DAX and the rest). Four separate defects, all fixed:
  - **Wrong ticker.** The search registry registered indices under bare
    TradingView ids (`SPX`, `DJI`, `NDX`, `RUT`) and put those in the
    destination, but the data path only understands YAHOO tickers — Yahoo has no
    `SPX` instrument, so `/api/price-history` returned an empty series and the
    chart showed "Symbol not found". Added `src/lib/indices.ts`, a single index
    registry that maps both directions (`SPX` → `^GSPC`), and used it in
    `/api/price-history` and `/api/quote`. The palette's index entries are now
    GENERATED from it, so the two can never drift again.
  - **Chart ignored later symbol changes.** `ChartWidget` initialised its state
    from the `symbol` prop exactly once and never reconciled, so the chart tab
    (which passes only `symbol`) kept rendering whatever it first mounted with.
    Added a prop-sync effect, gated to the uncontrolled path so a controlled
    `state=` host keeps sole ownership.
  - **Dead source for PSX indices.** Yahoo delisted PSX (`^KSE100` 404s, as does
    `.PSX`/`.KA` for the index), and `INDEX_UNIVERSE.PK` was deliberately emptied
    — so KSE-100 had no data at all. Added `fetchers/psx-index.ts`, which reads
    the exchange's own `dps.psx.com.pk/historical` endpoint (true OHLC, one
    request per month, parallel) for KSE-100/30 and KMI-30, plus the `eod`
    endpoint for their live quote so the chart footer is populated.
  - **Palette ordering.** The command palette grouped results by entity kind, and
    `security` (JDDS ETFs) + `instrument` (indices) are both labelled
    "Instruments" — so the grouping split them into two same-named sections and
    re-sorted the second one, burying a top-scoring index under ETFs that merely
    matched the same words. Both now share one section key and keep the
    resolver's score order.
  - Indices also carry their own currency now (`^FTSE` charts in GBP, `^NSEI` in
    INR), instead of inheriting the caller's default. Verified in-browser: each
    of S&P 500 / Dow / FTSE / Nifty / KSE 100 / Nikkei / DAX loads real bars and
    paints a candlestick chart with no console errors. 22 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`

- **Investor Eye** — **Phase 4: made the feed actually useful, map-first layout,
  3D globe.** The previous pass was a correct pipeline pointed at a nearly empty
  input — 146 events, all USGS earthquakes, zero from GDELT — so the map showed
  an earthquake feed while ~1,000 news items/day sat unused in JDDS.
  - **GDELT was completely broken and is now fixed.** Root cause found by
    measurement, not assumption: the DOC API took >13s per request (the shared
    `safeGet` transport hard-caps at 10s) *and* returned 429 on short bursts, so
    it produced **zero** events every run. Replaced with GDELT's **bulk 15-minute
    Event export** (`data.gdeltproject.org`): ~120 KB, **2.2s**, not rate-limited,
    and far richer — CAMEO codes, actor names/countries, Goldstein scores,
    mention counts and exact action coordinates. Uses Node's built-in `zlib` (no
    new dependency) and reads the ZIP central directory because GDELT sets the
    data-descriptor flag. The DOC API is retained only as a best-effort fallback.
    Result: **1,790 raw events → 400 after relevance filtering, 2.2s.**
  - **`safeGet` gained an opt-in `binary: true`** so binary payloads survive the
    transport (its default UTF-8 decode replaces invalid bytes with U+FFFD and
    irreversibly corrupts a zip). Also fixed: `lastupdate.txt` advertises `http://`
    URLs that the https-only transport (correctly) refuses; the scheme is now
    upgraded rather than weakening security.
  - **New `cameo.ts`** decodes CAMEO root codes to event types, the Goldstein
    scale to severity, and — critically — **FIPS 10-4 to ISO2**. GDELT's action
    country is FIPS, which *conflicts* with ISO for important countries (FIPS
    `AS`=Australia, `CH`=China, `SZ`=Switzerland, `UK`=UK); using the codes
    directly would have placed events in the wrong countries.
  - **New `relevance.ts`** scores investor relevance from GDELT's structured
    fields (material conflict, economic type/channel, state-to-state dyad,
    actor type, Goldstein, reach) so the firehose becomes a feed. GDELT codes
    everything — local crime, sport, university meetings — and without this the
    map was noise ("POLICE / Arizona"). Now a typical file yields Ukraine/Russia
    military, US–Iran, Arab League, sanctions and trade events instead.
  - **New news-to-events source (`sources/news.ts`)**: converts the already-ingested
    `NewsItem` rows into events — no new feed, no credentials, ~0.3s. **571 rows
    to 158 real events** covering the Fed, oil, NATO/Russia, Ukraine refinery
    strikes, Saudi–Houthi and India trade deals. `relevance` + `relevanceReasons`
    are persisted and the feed is ranked by relevance.
  - **Fixed a pre-existing bug that made `Candles` permanently empty.** The
    Python bridge emits `date`, but `updateCandleCache` read `ts`, so every bar
    was stamped `new Date()` and the composite-key upsert collapsed 955 bars to
    11 rows. It now reads the real date and skips undated bars. With the new
    `history.ts` backfill (reusing that existing path), **^GSPC now has 131 real
    daily bars, BTC-USD 187, CL=F 131** (2026-03-16 to 2026-09-16), so historical
    analogues finally have real series. The backfill is fire-and-forget: awaiting
    30 markets took ~170s and blocked the first world-state response, which is
    why the map initially rendered "0 events".
  - **Layout is now map-first**: the world is a full-width hero (~55vh, 82% of
    viewport width) with the layer/timeline controls directly beneath, and every
    detail panel (selection, What Changed, risk, transmission, portfolio, graph)
    stacked below the fold so nothing squeezes the map.
  - **3D globe**: a MAP/GLOBE toggle lazy-loads `echarts-gl@2.1` (new dependency,
    justified: it is the maintained ECharts globe). Globe mode uses `scatter3D`/
    `lines3D` — plain `scatter` with `coordinateSystem: 'globe'` silently fell
    back to index positioning and clumped pins in a corner — and a generated
    inline dark PNG texture, because echarts-gl's globe has **no `map` property**
    and its default bright texture rendered a white sphere that hid the data.
    Any globe failure (chunk, WebGL) falls back to the flat map automatically.
  - New routes: `GET/POST /api/investor-eye/history`.
    docs updated: `docs/investor-eye-architecture.md`, `docs/ARCHITECTURE.md`,
    `docs/CHANGELOG.md`

- **Charts / Market Bubbles** — Rebuilt Market Bubbles on the same real JDDS data
  the Command Center heatmap uses, and made it an actual volume-measuring tool.
  The old screen pulled `/api/stocks` (max 100 assets) and, for ANY equity market
  that returned nothing, silently substituted a hardcoded 8-symbol **Pakistani**
  demo list — so most markets rendered invented data, which is what made it look
  random. It now reads `/api/heatmap`, drops all demo/seed constants, and offers
  every one of the 31 `HEATMAP_MARKETS` instead of a hardcoded country list.
  - **Honest unit handling.** `Price.volume` is quote-currency notional for crypto
    but a share count for equities, so summing it mixes units and multiplying it
    by price double-counts. Added `turnoverFor` / `isNotionalVolume` in
    `src/lib/heatmap.ts` to normalise both into **turnover** (traded value in the
    market's currency) — the metric bubbles and the panel now size by default.
  - **New Volume Analytics panel** (`src/components/screens/volume-analytics.tsx`):
    traded value, instrument coverage, mean/median/largest, top-10 share, an HHI
    concentration read, contribution bands, and ranked top contributors. Computed
    server-side by `summarizeVolume()` over EVERY priced instrument in the market
    (not just the ≤220 tiles) via the new opt-in `GET /api/heatmap?volume=1`, which
    adds `HeatmapPayload.volume: VolumeSummary`.
  - Verified live: CRYPTO 1,385/1,455 instruments, $187.4B turnover, HHI 2553
    ("highly concentrated"); US 6,314 instruments. 16 unit tests pin the unit
    semantics, banding, concentration and top-N truncation.
  docs updated: `docs/ARCHITECTURE.md` (volume-unit contract), `docs/NAVIGATION.md`
  (route/task rows), `docs/OVERVIEW.md`, `README.md`

- **Investor Eye** — Completed Phase 2 (spec §63). Closed four real gaps left by
  the previous pass and fixed three defects found while verifying in-browser:
  - **2.8 Market transmission** was computed and served but never rendered —
    added `TransmissionsPanel`, which draws each `Event → country → channel →
    asset` chain and labels every hop `OBSERVED`/`INFERRED`, so an inference is
    not read as a fact.
  - **2.9 Historical analogues** had an API with no caller — added
    `AnaloguesPanel` (inside the event panel) rendering real stored series,
    sample size, date range, and an honest `UNAVAILABLE` when history is
    missing, plus the non-prediction disclaimer verbatim.
  - **2.10 Relationship graph** was missing entirely — added the additive
    `Relationship` model (and `EventEntity` / `Country` rows are now actually
    written during ingestion), a pure `graph.ts` builder (per-kind caps, honest
    truncation, strongest-class preservation), `graph-data.ts` (edge derivation:
    event co-mention and stored attributes → `OBSERVED`),
    `GET /api/investor-eye/graph`, and a `GraphPanel` ECharts force layout whose
    edge colour and tooltips encode `relationClass`. Relational, not a graph DB
    (ADR-011).
  - **2.11 AI Analyst** was missing — added seven read-only agent tools
    (`src/lib/agent/investor-eye-tools.ts`, spread into `TOOLS`) plus a `world`
    research agent, so the model answers from structured data with provenance
    and never on the query path.
  - **Fixed:** the assembled-state cache was module-level, and Next evaluates
    each route in its own module instance, so `/state`, `/risk`, `/markets` and
    `/layers` each cold-ran the full GDELT/USGS ingestion — `/risk?hours=24`
    took 20–100s. The cache and its in-flight guard are now `globalThis`-anchored
    and keyed by window, so a route fan-out triggers one ingestion per window
    (measured ~6s once warm).
  - **Fixed:** company pins on the map were dead — they now open a
    `CompanyPanel` with profile + derived relationships.
  - **Fixed:** panel selection was not exclusive, so clicking an event from the
    country panel never rendered (the stale panel kept priority).
  - 42 new tests (relationship-graph builder, cache semantics, agent tools).
    docs updated: `docs/investor-eye-architecture.md`, `docs/ARCHITECTURE.md`,
    `docs/NAVIGATION.md`, `docs/DECISIONS.md`

- **Search** — Fixed a broken pre-existing working-tree change in
  `global-search.tsx`: `pinnedCommands` was removed but its render block
  remained, so the file did not typecheck (`tsc` reported a dangling reference).
  Removed the orphaned block, preserving the surrounding WIP intent.
  no doc change — restores a file to a compiling state; no contract changed.

## 2026-09-15

- **Search** — The palette's bottom group is now simply the app's 11 top-level
  tabs in sidebar order (ChatBot → Price Alerts, including Investor Eye), not a
  32-item sub-page dump. Removed the inline calculator, parameterized command
  rows, and their wiring (`calc.ts`, `commands.ts`, quick-alert and watchlist
  side effects). Typing still searches instruments, indicators, markets and
  actions via the resolver, so this only changed the pinned list.
  no doc change — palette presentation only; resolver/search contracts unchanged.
- **Investor Eye** — New **Investor Eye** world-state surface (Phase 1 + 2): a
  large interactive ECharts world map with a pluggable `MapLayer` system
  (events, markets, conflict, energy, trade, weather, economy, companies,
  portfolio, risk), a timeline (1H–30D), layer controller, country/event
  intelligence panels, "What Changed" summary, and honest data-freshness
  indicators. Backed by a new **additive** event tier `src/lib/investor-eye/`:
  `EventSource` adapters (GDELT DOC 2.0 + USGS, both free/keyless, fetched
  through the existing `connectors/security.safeGet`), pure normalization
  (classification, clustering/dedup, internal data-quality confidence, grid
  aggregation), a real country gazetteer, server SWR cache + persisted
  last-known, an in-process ingestion cron, and 13 `/api/investor-eye/*` routes
  (state, events, countries, markets, layers, economy, companies, portfolio,
  risk, analogues, query, health). Markets reuse the existing `IndexQuote` +
  yfinance path and portfolio exposure reuses `use-portfolio-engine` — no second
  market/portfolio/news stack. Phase 2 analytics are deterministic (risk
  decomposition, exposure, `OBSERVED|HISTORICAL|INFERRED` transmissions,
  historical analogues, keyword+gazetteer NL map search — no LLM on the query
  path). New JDDS models `Country`, `GeopoliticalEvent`, `EventEntity`,
  `SourceRun`; vendored `public/geo/world.geo.json` (Natural Earth, via
  `scripts/fetch-world-geo.mjs`); new `investor-eye` sidebar tab registered in
  sidebar config, search registry, top-bar and the shell. A failed source is
  `UNAVAILABLE`, never a fake zero. 106 new tests.
  docs updated: `docs/investor-eye-architecture.md` (new), `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`, `docs/DATA-FLOW.md`, `docs/DECISIONS.md`,
  `skills/ARCHITECT.md`
- **Build** — `scripts/doctor.js` now detects **schema drift** on an existing
  `jdds.db` and self-heals with `prisma db push`. Previously it only pushed when
  the DB file was *missing*, so an install carrying the old committed seed would
  never receive models added since (the connector + Investor Eye tables) and
  would 500 on every query against a missing table. Expected table names are
  parsed from `schema.prisma`, so the check cannot itself go stale; a locked or
  corrupt DB is left to the existing integrity guard.
  no doc change — self-healing boot fix; no documented contract changed.

- **Screener** — Fixed the broken glyphs on the Market Screener (the `□` boxes
  in the "Global Markets Overview" row and in the table headers). Root cause was
  a pre-existing encoding corruption, not a missing icon: commit `34d76fd`
  (frosted-glass pass) re-encoded `market-overview.tsx` and turned 80 non-ASCII
  characters — em dashes, middots, ellipses, en dashes — into `U+FFFD`
  replacement characters baked into the source. Recovered the original
  characters by matching each damaged line's ASCII skeleton against the last
  clean revision (`c8ec9d3`) and restored them; also fixed one instance in
  `src/app/globals.css`. Verified zero `U+FFFD` remains across all source files.
  no doc change — character-encoding repair, no contract or architecture change.

- **Connectors/UI** — De-duplicated and expanded the provider surface. The AI
  Agent screen previously showed a generic "Provider" **dropdown and** a
  provider **list** — the same choice twice, and the list's "Set up" button
  navigated back to the screen you were already on. It is now a single
  preset-grid picker: click a provider and it fills the base URL + model, leaving
  only the key. Added `src/lib/agent/presets.ts` with **14 working
  OpenAI-compatible presets** (OpenAI, Anthropic, Ollama, LM Studio, Groq,
  DeepSeek, Mistral, Google Gemini, xAI, OpenRouter, Together, Perplexity,
  Fireworks, Custom), and the catalog's AI entries are now **derived from that
  list** so a new preset appears in both places with one edit. Also fixed a real
  bug: `setLLMConfig` rejected any provider without a key, so **keyless local
  servers (Ollama/LM Studio) could not be saved** — it now allows local base URLs
  (`isLocalBaseUrl`) and stubs `"local"` since some clients require a non-empty
  string. Added 12 market/crypto providers (Finnhub, Polygon, Alpha Vantage,
  Twelve Data, Marketstack, CoinGecko, CoinMarketCap, Kraken, …) — **72 providers
  total**, up from 53. Env-var key status is now a single list
  (`CATALOG_ENV_VARS`) shared by `/api/providers` and `/api/settings`, so the two
  cannot disagree. 21 new tests.
  docs updated: `docs/ARCHITECTURE.md`

- **Connectors/UI** — Moved the provider catalog OUT of Data Sources and into
  the settings section that actually configures each provider, so APIs are no
  longer dumped in one place: **AI Agent** shows AI & LLM, **Market Data** shows
  Market Data + Crypto, **Integrations** shows all 44 Economics & Macro sources,
  and **Data Sources** now shows only "Your own data" (the wizard). The new
  `provider-list.tsx` renders a catalog slice in context with a module-level
  fetch cache, so appearing in four sections still costs one request. The
  Integrations section also dropped its hand-written rows (which listed
  `finnhub`/`binance`/`coingecko` — nothing consumes those) in favour of the
  derived list, leaving only AI Model + Database as genuine status rows.
  Long lists (economics) are collapsible with a filter box. 543 tests pass.
  docs updated: `docs/ARCHITECTURE.md`

- **Connectors/UI** — Added a browsable **provider catalog** to Settings → Data
  Sources, grouped by what each provider is for (AI & LLM, Economics & Macro,
  Market Data, Crypto, Your own data) instead of a flat connector list —
  53 providers across 5 collapsible categories with per-category counts.
  `src/lib/connectors/catalog.ts` builds it purely (`buildCatalog(env)`), and
  **Economics entries are derived from `ECON_SOURCES`**, so the catalog cannot
  drift from the fetch layer. Status is honest: `builtin`, `connected`,
  `not_configured`, or `available`, computed from the real environment — of 44
  economics sources only FRED is key-gated, and it shows `needs FRED_API_KEY`
  until set. Buttons never claim to have saved a key: built-ins show a status
  pill, Custom REST opens the wizard, and env-gated providers route to
  Settings → AI Agent / Integrations (via the destination bus, since Settings is
  a modal, not a tab). New `GET /api/providers`. 10 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`

- **UI** — Navigation icon and label pass. Renamed the **Market Workspace** tab
  to **Chart Workspace** (tab id and `src/lib/market-workspace/` folder unchanged)
  so the label says what the screen is, and gave it the candlestick icon that the
  screener was using. The screener now uses `ScanSearch` (magnifier over scan
  lines) to read as "screen the market" instead of duplicating the chart glyph,
  and Portfolio switched from `Briefcase` to `ChartPie` per request. Applied the
  same choices to every surface that carried a stale icon: sidebar config, the
  search registry (`page-market-workspace`, `page-screener`, `page-portfolio`,
  the screener sub-pages, and the three open actions), the palette's `NAME_ICON`
  map, and both page headers (Chart Workspace had no icon at all; Portfolio and
  Screener used the old glyphs). All `open …` action labels and the page title
  updated too; old labels kept as search aliases so muscle memory still resolves.
  docs updated: `docs/OVERVIEW.md`, `docs/GLOSSARY.md`, `docs/ARCHITECTURE.md`,
  `docs/DECISIONS.md`, `skills/ARCHITECT.md`, `skills/REMEMBER.md`

- **Search** — Tests + docs for sub-page navigation. Added
  `search/subroute.test.ts` (channel semantics: tab scoping, focus pass-through,
  seq re-fire, scoped clear) and registry assertions that sub-pages carry a
  `subroute`, nest under their parent `group`, and that only children are marked
  `child`. Documented the subroute channel and its two invariants in
  `docs/ARCHITECTURE.md`, and the "add a palette sub-page" recipe in
  `docs/NAVIGATION.md`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Search** — Sub-page navigation: `Destination.subroute` (previously emitted by
  the registry but ignored by the shell) is now honored. Added a `pendingSubroute`
  channel + `useSubroute(tab, handler)` hook so keep-alive screens react to
  `economics.calendar`, `journal.<tab>`, `discovery.<tab>`, `alerts.<view>`, and
  `settings.<section>`; the shell also routes `tab:'settings'` to the Settings
  modal (it previously switched to a tab that rendered nothing). Registered ~40
  sub-pages in the registry (grouped under their parent, rendered indented in the
  palette's "Go to"), added an Economics "Calendar" section with indicator focus
  highlighting, and removed the superseded `search/settings.ts`. New:
  `src/hooks/use-subroute.ts`, `getPageEntries()`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Charts** — Drawing toolbar rendered the same `MousePointer2` glyph for every
  tool, so the Lines/Shapes/Analysis grids were unreadable at a glance. Added a
  `TOOL_ICON` name→lucide map in `chart-widget.tsx` (unknown names fall back to
  the pointer, so a future tool never renders blank) and wired each button to its
  own glyph, with the active tool tinted `primary` for contrast. Also split the
  two colliding registry icons: `ray` now uses `move-diagonal` and `arrow` keeps
  `arrow-up-right`.
  no doc change — UI-only change, drawing contracts and tool registry shape unchanged.

- **Connectors** — Hardening pass on the custom REST connector after review.
  Fixed a silent URL bug: `new URL(path, base)` treats a leading `/` as
  root-relative, so a base like `https://api.example.com/v1` + `/quote`
  produced `…/quote` and **dropped the `/v1` prefix** — a very common API shape
  that would have 404'd with no explanation. Added `joinPaths()`, which joins
  the base pathname explicitly, and preserved any query string the operator put
  on the base URL (a common spot for a query-param key). Added `validateHeaders`
  so CRLF injection / empty header names fail with a clear config error instead
  of Node's opaque `ERR_INVALID_CHAR`. Anchored the connector registry on
  `globalThis` (same reason `lib/db.ts` anchors Prisma) so dev HMR cannot leave
  a second empty registry behind. Verified end-to-end against the live Binance
  API with a `/api/v3` base: multi-symbol pulls, records, and agent reads all
  correct. 9 new tests.
  docs updated: `docs/ARCHITECTURE.md`

- **Connectors** — Completed the connector loop end-to-end. Fixed a dishonest
  count: `ingestRecords` always returned `rejected: 0` even when `mapResponse`
  silently dropped rows, so an import could report success while losing records.
  Mapping now reports `extracted` / `rejectedRequired` / `rejectedIdentity` /
  `deduped` (`mapResponseDetailed` in `mapping.ts`) and every extracted row is
  accounted for. The Data Sources panel gained a **Datasets** browser with
  **Pull** (fetch through the connector and ingest), per-dataset parameter
  inputs, a records table showing provenance, delete-dataset, and a **Sample
  test value** field in the wizard (draft tests previously failed with "Missing
  required parameter" because no value was ever supplied). Pull errors now
  return 400 with the real message for a misconfigured connector instead of an
  opaque 502; connector fetch errors are classified (`invalid_config` /
  `blocked` / `timeout` / `too_large`) rather than all reported as `network`.
  New `DELETE /api/datasets?id=…`. 6 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`

- **Agent** — The research agent can now read operator-connected datasets via
  three read-only tools (`src/lib/agent/dataset-tools.ts`): `list_datasets`,
  `describe_dataset`, `query_dataset`. They are spread into `TOOLS`, so the
  existing tool loop picks them up with no loop change; the fundamentals and
  risk agent prompts were updated to use them. Every tool result states
  provenance (`CUSTOM` vs. canonical scraper data) so the LLM never invents a
  source. Added `queryRecords` / `datasetSummaries` / `findDatasetByName` to
  `connectors/store.ts`; filters are exact-match on mapped field names
  (case-insensitive), JS-evaluated because SQLite cannot query inside the JSON
  `values` column. 15 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/DECISIONS.md`

- **Connectors** — Introduced the Universal Data Connector Layer
  (`src/lib/connectors/`): a capability-addressed connector tier that sits
  *after* the existing scraper chain and before route-level demo fallbacks.
  Added hardened outbound security (`security.ts`: canonical IP
  classification, DNS validation + pinned lookup, `redirect: manual`, streamed
  5 MB cap, ≤10s timeout), AES-256-GCM credential encryption (`secrets.ts`,
  local auto-generated key vs. `CONNECTOR_SECRET_KEY` on hosted), a declarative
  `custom-rest.ts` connector (GET + percent-encoded `{{param}}` substitution),
  mapping/`recordPath`/`recordKey` dedup (`mapping.ts`), the crypto fetcher
  migrated as the Phase-2 proof (`providers/crypto.ts`, legacy facade retained),
  and server-side capability resolution (`GET /api/data/[capability]`).
  New JDDS models: `DataConnector`, `CustomDataset`, `CustomDatasetField`,
  `CustomDatasetRecord`, `ConnectorMapping` — custom data never writes to
  `Asset`/`Price`/`Candles`. New routes: `api/data-sources`,
  `api/data-sources/test`, `api/datasets`. DataHub gained an optional
  provenance envelope + `CUSTOM` tag and a `capabilityTopic` helper (no internal
  redesign). New Settings → Data Sources wizard (`data-sources-panel.tsx`).
  Deferred: webhooks, POST bodies, pagination, OAuth, `~` dataset search, agent
  `query_dataset`, AI connector generation.
  docs updated: `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`,
  `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`, `README.md`

- **Search** — The palette is now full navigation, not just search. The bottom
  group is generated from `getAllPages()` so every registered page is reachable
  (adding a `registerPage` entry adds a nav row automatically); it is labeled
  "Go to", collapsible, and part of the keyboard list. Added paging keys
  (PageUp/PageDown/Home/End), a conditional bottom scroll-fade so overflow is
  visible, and a `nameIcon` map for registry string icon names.
  docs updated: `docs/ARCHITECTURE.md`
- **Aurora** — Made the shipped bearish color a proper pure red (`#ff0000` core /
  `#3a0000` edge) instead of the yellowish `#ff3e3e`, so the default Eclipse
  preset's red no longer reads orange.
  no doc change — default color values only; palette model/contract unchanged.
- **Search** — Wired the command palette's cross-tab pivots and parameterized
  commands to real behavior (they were previously cosmetic). `alert SYMBOL` now
  creates a ±3% CHANGE_PCT watch via new `lib/alerts/quick-alert.ts` and opens
  the Alerts tab; `watch SYMBOL` calls new `addToWatchlist` /
  `removeFromWatchlist` / `isInWatchlist` exports in
  `lib/dashboard/watchlist-store.ts`; `chart SYMBOL` opens the chart. The
  misleading `compare` verb was removed, registry actions gained `requiresArg`
  so they never render as bare commands, failures surface an inline error
  instead of a fake recent, and the keep-alive Alerts screen re-lists on a
  `be:alerts-changed` event. `MarketNews` gained a `symbol` prop (seeds the
  `ticker:` operator); `MarketOverviewScreen` gained `initialSymbol`; the
  destination bus in `stock-chat.tsx` now routes `tab:news`/`tab:discovery`
  symbols.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Docs** — Documentation/skills audit before sharing with an external tool.
  The `docs/` set was already current; the agent *skills* had drifted badly and
  were corrected against code: `skills/ARCHITECT.md` §2–4 described a pre-JDDS app
  ("no database", "only `/api/news`", 6 tabs, SQLite listed as PLANNED) — rewritten
  to the JDDS/scheduler/agent reality; `skills/REMEMBER.md` (DB, tabs, agent,
  retired `src/lib/customize/`) and `skills/GOALS.md` (agentic research now
  active, not deferred) updated; `skills/README.md` skill list fixed (6 → 8);
  `CONTRIBUTING.md` "no database/demo data" claim corrected.
  docs updated: `docs/DECISIONS.md` (mirror), `docs/CHANGELOG.md`
- **Search** — Completed the command-center improvement phases. Phase 4:
  deterministic synonym/acronym expansion (`expandTerms`), visit-history
  personalized ranking, and cross-tab `related` pivots for a resolved
  instrument. Phase 5: offline in-palette calculator + indicative currency
  conversion (`calc.ts`) and parameterized commands with argument autocomplete
  (`commands.ts`). Phase 6: ARIA combobox/listbox semantics with a polite live
  region, memoized rows, and a mobile-sized palette. New store state: `visits`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Search** — Result UX pass on the command palette: groups now show per-kind
  counts and collapse on click, results can be pinned (persisted to
  `localStorage` and replayed from a serialized destination) or have their symbol
  copied, the footer shows "N of M results", and a zero-hit query offers a
  "did you mean" correction from the static registry (`suggestCorrection`).
  `ResolvedSearch` gained `total` + `suggestion`.
  docs updated: `docs/ARCHITECTURE.md`
- **Search** — Added a query grammar to the command center: scoped prefixes
  (`>` commands, `#` instruments, `@` indicators, `/` pages, `~` your data, `?`
  syntax help) and field operators (`kind:`, `class:`, `market:`, `symbol:`).
  `resolver.ts` now parses scope/filters before resolving, and the palette shows
  a scope chip, a syntax help card, a clear button, and scope-aware empty states.
  The header trigger gained a contextual per-tab placeholder, a platform-aware
  ⌘/Ctrl shortcut label, and a live index count.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`

- **Market Workspace** — Interactive drag placement now keeps a panel where it was
  dropped: added `placePanel` (absolute placement, pushes displaced panels down),
  `clampPanels` (bounds-only, row-preserving) and `packPanels` (full repack for
  templates/repair); `normalizePanels` is deprecated as an alias. Added
  `recomputeRows` so the grid ends at its content height instead of scrolling
  into empty space. New charts seed from the layout's lead instrument instead of
  hard-coded AAPL, and panels gained a `chrome: 'minimal'` full-page mode.
  Duplicate/remove moved into the panel menu (copy/trash icons).
  no doc change — no documented shape changed; `/lib/market-workspace/` is
  already mapped in `docs/NAVIGATION.md`.
- **Command Center** — New layouts can start from a persona preset:
  `MarketView` gained `templateId` (threaded `market-views.tsx` →
  `dashboard-screen.tsx`), and the new-layout flow was extracted into
  `new-layout-dialog.tsx`.
  no doc change — additive field; dashboard/workspace contract unchanged.
- **UI** — Added a `variant` prop to the shared `TabBar` (`glass` default,
  `subtle` for the new `.tab-bar-subtle` control-strip tier), applied to the
  Command Center market tabs.
  docs updated: `docs/ARCHITECTURE.md`, `.opencode/skills/black-eclipse-ui/SKILL.md`
- **Heatmap** — Tile sizes are compressed before grouping (sqrt for crypto,
  ^0.75 for equities) so a mega-cap no longer flattens the board; added
  `rawMarketCap` so tooltips and sector totals keep showing the true figure.
  no doc change — additive field on an internal heatmap shape.
- **Aurora** — `normalizePalette` now validates every color is real hex (guards
  the shader against malformed values); `setPalette` normalizes + clones so
  applying a preset never stores a shared module reference. Presets refactored
  through a compact `preset()` helper, swatches render a bearish→bullish ramp,
  and `theme.test.ts` covers every preset.
  no doc change — internal hardening, contract unchanged.
- **Docs** — Made the documentation obligation enforceable: every change must now
  append a `docs/CHANGELOG.md` entry (including changes needing no doc update),
  and an always-on rule was added in `AGENTS.md` so it applies to every session
  rather than only doc-keyed tasks.
  docs updated: `docs/CHANGELOG.md`, `docs/README.md`, `skills/DOCS.md`,
  `skills/REVIEW.md`, `.opencode/skills/black-eclipse-docs/SKILL.md`, `AGENTS.md`
- **Docs** — Established the documentation system: a flat canonical doc set in
  `docs/` plus an always-on obligation in `AGENTS.md`, the `black-eclipse-docs`
  skill, `skills/DOCS.md`, and the Documentation Review section in
  `skills/REVIEW.md`. Added a maintained change log (this file).
  docs updated: `docs/README.md`, `docs/OVERVIEW.md`, `docs/QUICKSTART.md`,
  `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`,
  `docs/DECISIONS.md`, `docs/GLOSSARY.md`, `docs/CHANGELOG.md`
- **Docs** — Corrected a pre-existing drift: `black-eclipse-workspace` skill and
  the new docs described a paper broker (`dashboard/paper-broker.ts`,
  `trading-widgets.tsx`, `broker/types.ts`) that does not exist. Trading widgets
  are `UNAVAILABLE` stubs in `src/lib/dashboard/registry.tsx`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/OVERVIEW.md`, `docs/GLOSSARY.md`,
  `.opencode/skills/black-eclipse-workspace/SKILL.md`
- **Agent prompt — finance-first, runtime-accurate guidance** — Tightened the Eclipse Agent prompt around dated/provenanced evidence, comparable financial metrics, risk and counter-theses, quantitative auditability, untrusted retrieved content, and honest tool boundaries; removed generic orchestration claims the registered agent cannot guarantee.
  docs updated: `docs/harness/architecture.md`
# 2026-09-24

- **Agentic roadmap — detailed MCP Phase 5 plan** — Defined user-controlled MCP integration across stdio/remote transports, tool governance, auth, approvals, source freshness and provenance; clarified JDdS as a fallible source, not the mandatory authority.
  docs updated: `agentic-plan-implementaion.md`, `docs/harness/architecture.md`
# 2026-09-28

- **Memory/skills system review** — Compared Eclipse-Memory with Hermes Agent to identify improvements in retrieval, procedural learning, discoverability, and provider ergonomics; no implementation changes were made. no doc change — analysis-only review

