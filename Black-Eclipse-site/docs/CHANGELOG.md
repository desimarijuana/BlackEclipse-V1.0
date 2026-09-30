---
title: Change Log
status: Current
last-verified: 2026-09-28
---

# Change Log

## Rotation policy

This file keeps a rolling window of the **most recent 7 dated sections** (the active window). Older dated sections are **moved** - never deleted - into monthly archive files under docs/changelog/YYYY-MM.md. New entries are still appended to the top of this file under today's date; the commit-msg hook checks this exact path. Rotation is done by hand only when this file grows unwieldy; the archive link below always points at where the older entries went.

> Older entries are archived under docs/changelog/ (monthly). The most recent 7 dated sections are kept here.

## 2026-09-30

- **Engineering hardening — MCP leftovers closed or re-stated.** Non-text MCP
  results keep a metadata-only path but now state plainly that content exists and
  was not shown (the runtime has no binary channel). The supply-chain report is
  re-stated as offline-only (offlineOnly/upstreamChecked/generatedAt; the
  date is a review date, not a live check) and the UI says so. 
esource_schemes
  narrowing was verified reachable with the global allowlist as ceiling; the OAuth
  authorization-code leg keeps its named unblocking condition (a local https
  callback or hosted redirect) with the device flow as the documented default.
  docs updated: docs/harness/engineering-hardening-progress.md,
  docs/harness/mcp-ui-parity-progress.md

- **Engineering hardening — documentation reconciliation.** Updated
  gentic-plan-implementaion.md so MCP Phases 5D/5F/5H/5I reflect shipped
  reality (5F and 5H implemented, 5D/5I complete except the documented OAuth
  https and subscriptions non-goals). Completed the app-level ADR mirror:
  skills/ARCHITECT.md and docs/DECISIONS.md now both hold all 39 app ADRs
  (backfilled 11 existing + mirrored ADR-038/039); the harness ADR-HNN series
  stays only in docs/harness/decisions.md. Documented both series in AGENTS.md,
  skills/DOCS.md and NAVIGATION.md. Added a CHANGELOG rotation policy
  (rolling 7-section window + monthly docs/changelog/ archives, history moved
  not pruned). Fixed the two stale doc statuses.
  docs updated: gentic-plan-implementaion.md, AGENTS.md,
  skills/ARCHITECT.md, skills/DOCS.md, docs/DECISIONS.md,
  docs/NAVIGATION.md, docs/CHANGELOG.md, docs/changelog/2026-09.md,
  docs/harness/decisions.md, docs/harness/phase-3-architecture.md,
  docs/harness/phase-4-progress.md,
  docs/harness/engineering-hardening-progress.md

- **MCP Phase 6.1 — round-trip integrity (fixes a silent authority downgrade).**
  `upsert_mcp_config` now implements "absent means preserve; explicitly present
  means replace" using the incoming model's `model_fields_set`, so a partial save
  (the old UI payload) can no longer reset `trust`, `lazy`, `tools`,
  `tool_effects`, `data_source_tools`, `confirmed_catalog_digest` or the
  keepalive/idle/lifetime/TLS fields. `install_mcp_integration` is now
  create-if-absent so re-installing never resets a user's changes. `public_dict()`
  also emits the raw operator-set bounds so the wire is lossless. A hard
  invariant is added: a save may never widen authority by omission. TS
  `MCPServerView`/`MCPServerInput` carry every field; the view↔draft mapping is a
  pure tested module `src/lib/harness/mcp-draft.ts`.
  docs updated: `docs/harness/mcp-ui-parity-progress.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H74)
- **MCP Phase 6.1 — full-fidelity editor and status surfaces.** The settings UI
  reaches every Phase-6 field: trust tier, include/exclude filters, per-tool
  effects, native data sources, capability toggles, lazy/keepalive/idle/lifetime,
  TLS/mTLS, limits, SSE transport and OAuth sign-in. The server editor is
  extracted to `src/components/screens/mcp/`; a lifecycle panel renders the
  runtime's retry/keepalive/recycle/metrics block honestly; approvals gain status
  filtering; the config load error is shown loudly.
  docs updated: `docs/NAVIGATION.md`, `docs/harness/mcp-ui-parity-progress.md`
- **MCP Phase 6.1 — product surface, leftovers and `manager.py` split.** New
  front-door routes `POST /api/harness/mcp/integrations/[id]/install` and
  `GET /api/harness/mcp/supply-chain`; the wizard installs a preset and the
  supply-chain panel renders offline. Non-text MCP content now reports MIME type +
  byte size instead of an opaque omission. `resource_schemes` adds an optional
  per-server narrowing with the global allowlist as a hard ceiling. `manager.py`
  is split by pure extraction into `runtime.py`, `introspection.py` and
  `oauth_flow.py` (1579 → 1226 lines), `MCPManager` facade unchanged.
  docs updated: `docs/NAVIGATION.md`, `docs/harness/architecture.md`,
  `docs/harness/mcp-ui-parity-progress.md`
## 2026-09-29

- **MCP Phase 6 — close the deferred seams.** Declared MCP data tools now flow
  into the REAL retrieval layer (`manager.mcp_sources()` →
  `ToolContext.mcp_manager` → `FinancialRetrievalLayer(mcp_sources=...)` →
  `plan_retrieval(additional_sources=...)`); server `sampling/createMessage` runs
  on the run's own model adapter via `AgenticService._sampling_model_factory`;
  a second offline MCP client (SSE) now exercises Eclipse-as-server alongside
  Streamable HTTP. `data_source_tools` surfaced in `mcp-types.ts` and the example
  config. The OAuth authorization-code interactive leg is documented as a manual
  https step (the SDK refuses plain-http OAuth URLs); the device flow is covered
  offline. `tsc` clean; vitest 1837 pass; Python 1566 pass (baseline 1446).
  `jdds.db` untouched. docs updated: `docs/harness/mcp-phase-6-progress.md`,
  `docs/harness/decisions.md` (ADR-H73), `docs/harness/architecture.md`,
  `python/harness/mcp/__init__.py`.

- **Focus mode for the ChatBot (Ctrl+Alt+X).** A presentation-only "zen" view:
  the shortcut hides the header (`TopBar`) and sidebar and centers the transcript
  and composer in a narrower (860px) column, with the composer kept pinned to the
  bottom. Scoped to the chat tab — it exits on any tab switch or when Settings
  opens, and is ignored while typing/in dialogs. Added `hidden` props to
  `Sidebar`/`TopBar` (unmount for a clean canvas), a `focus` prop to `EmptyState`,
  and a row in the global shortcuts help dialog.
  `tsc` clean; vitest 1837 pass; Python 1479 pass.
  no doc change — behavior-only UI affordance, no architecture/contract/setup change.

- **ChatBot "Sources" dropdown redesigned to match "What influenced this run".**
  `ResearchEvidencePanel` is now a SINGLE flat frosted dropdown in the
  run-explanation style (chevron + leading status icon + inline summary), instead
  of a panel wrapping nested boxes. The numbered Sources list lives in a bounded
  `max-h-56` scroll area so a long citation list stays manageable rather than
  spilling the transcript; `Research detail` became a borderless inline
  disclosure. Each source row is a tinted tile with a tier chip and a
  `View source` link. Presentation only; a right-hand sources rail concept was
  tried and removed. `src/components/chat/research-evidence-panel.tsx`.
  `tsc` clean; vitest 1837 pass. no doc change — presentation only.

- **MCP Phase 6 Milestones 3–8.** Remote auth (`oauth.py`; OAuth 2.1 via the MCP
  SDK + RFC 8628 device flow; tokens encrypted in the vault via
  `mcp-oauth-store.ts` and the `mcp_oauth_token_*` bridge capabilities; login/
  logout routes), TLS/mTLS/SSE + redirect/origin guard (`redirect_guard.py`),
  capability-aware resources/prompts and sampling/elicitation routed through the
  approval surface (`interactions.py`; subscriptions a documented non-goal),
  MCP-aware source planning (`mcp_retrieval.py`; conflict preservation; three
  freshness states), real presets + one-click install + supply-chain audit
  (`audit.py`), narrow read-only Eclipse-as-MCP-server (`server_exposure.py`;
  verified against Hermes: 3 tools discovered), an adversarial suite,
  context-growth numbers, graceful degradation when `mcp` is unimportable.
  `tsc` clean; vitest 1837 pass; Python 1561 pass (baseline 1446). `jdds.db`
  untouched. docs updated: `docs/harness/mcp-phase-6-progress.md`,
  `docs/harness/decisions.md` (ADR-H69–H72), `docs/harness/architecture.md`,
  `docs/NAVIGATION.md`, `python/harness/mcp/__init__.py`,
  `Black-Eclipse-site/skills/ARCHITECT.md`.

- **MCP Phase 6 Milestone 2 — lifecycle resilience.** Reconnect with jittered
  exponential backoff (separate initial/reconnect budgets, reported terminal
  state), a call-time reconnect seam that re-checks authority, session-expiry
  policy (a read replays once; a write returns `outcomeUncertain` and is never
  replayed), optional keepalive and stdio recycle, POSIX orphan reaping
  (stdlib-only supervisor; Windows relies on the SDK Job Object), and lazy
  startup with an on-disk schema cache keyed by connection fingerprint. New:
  `python/harness/mcp/{lifecycle,schema_cache,orphan_supervisor}.py`; tests
  `test_mcp_lifecycle.py`, `test_mcp_orphan_reaping.py`. `tsc` clean; vitest
  1837 pass; Python 1494 pass. docs updated:
  `docs/harness/mcp-phase-6-progress.md`, `docs/harness/decisions.md` (ADR-H68),
  `docs/harness/architecture.md`, `docs/NAVIGATION.md`,
  `Black-Eclipse-site/skills/ARCHITECT.md`.
- **MCP Phase 6 Milestone 1 — config contract, screening, honest surfaces.**
  Added `${VAR}`/`${env:VAR}` interpolation (`interpolation.py`) with a
  fail-closed remote rule (unresolved `url`/`auth` refuses by name; local stdio
  keeps the literal), `selected_tools` include/exclude fnmatch filters, a static
  server-entry screen (`screening.py`, refuse-not-sanitize, at load/save/spawn),
  a fail-closed `trust` tier (`full`/`untrusted`; untrusted needs approval for
  every non-read call and its annotations never activate a tool), the
  `mcp__<server>__<tool>` double-underscore naming (boundary disambiguation;
  digest only on a genuine collision), operator gating of the previously-open
  Python MCP read routes, and an explicit `httpx2` pin. Tests:
  `python/tests/test_mcp_config_hardening.py` + read-route gate cases in
  `test_mcp_api.py`. `tsc` clean; vitest 1837 pass; Python 1479 pass.
  docs updated: `docs/harness/mcp-phase-6-progress.md`,
  `docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H67),
  `docs/NAVIGATION.md`, `mcp-servers.example.json`, `Black-Eclipse-site/skills/ARCHITECT.md`.
- **Investor Eye map: draw the Gaza Strip as Palestine.** Natural Earth's 110m
  admin-0 layer omits Gaza entirely, so the strip rendered as unclaimed blank and
  matched no country (Gaza city, Khan Yunis, Rafah fell outside every polygon).
  Spliced Natural Earth's 10m `Gaza Strip` polygon into the `Palestine` (`PS`)
  feature — now a `MultiPolygon` of West Bank + Gaza — and subtracted it from
  Israel's coarse polygon (overlap was ~0.001 of Gaza's area). Only `IL` and `PS`
  changed; verified by point-in-polygon (Gaza/Ramallah/Nablus → PS; Tel Aviv/
  Beersheba → IL) with no unclosed rings. Extended the regeneration warning in
  `scripts/fetch-world-geo.mjs` (a plain re-fetch reverts this, same as the
  Kashmir POV). docs updated: `docs/investor-eye-architecture.md`,
  `docs/CHANGELOG.md`
- **Chat background anchored to the panel, not the viewport.** The eclipse
  artwork was `fixed inset-0`, so it centered on the whole window and the opaque
  sidebar (when open) covered its left half — the image appeared to disappear/
  shift. It is now an `absolute inset-0` layer inside the chat content panel with
  the shell kept `relative`, so it recenters with the panel as the sidebar
  collapses/expands.
  `src/components/screens/stock-chat.tsx`. `tsc` clean; vitest 1837 pass.
  no doc change — visual only.
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
- **Message navigation rail now shows with one user turn and on phones.**
  The rail was gated on 2+ user turns and `hidden md:flex` (<768px), so a
  one-exchange chat or any narrow window showed nothing — it read as missing.
  Lowered the threshold to 1 user turn and dropped the `hidden md:flex` pair so
  the rail renders at every width. Inactive ticks were also brightened from
  `bg-foreground/25` to `bg-muted-foreground/70` so they are legible against the
  dark chat background. Also corrected the changelog tick description below
  (ticks are `h-[2px] w-2.5`, growing to `w-3.5` on hover, not the earlier
  `h-px w-3`→`h-[3px] w-5`). `src/components/chat/message-rail.tsx`. `tsc` clean.
  no doc change — UI visibility only, no contract or data-shape change.

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
