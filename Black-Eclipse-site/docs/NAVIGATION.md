---
title: Navigation — Where Things Live
status: Current
last-verified: 2026-09-26
---

# Navigation — Where Things Live

**Who this is for:** anyone asking "which file do I open to change X?"

This doc is also the **update trigger table**: when you add, move, or rename a
top-level folder or a major module, update the relevant row here in the same
change. That is the mechanism that keeps docs from drifting.

## Top-level map

```
Black-Eclipse-site/
  src/
    app/            Next.js App Router: page.tsx + api/**/route.ts
    components/     UI — screens, layout, chat, ui primitives, workspaces
    lib/            All logic: data, scraper, agent, domains
    hooks/          Shared React hooks
    types/          Shared TypeScript types
    generated/      Prisma client output (gitignored — do not edit)
  prisma/           schema.prisma (the JDDS schema)
  scripts/          Importers, bridge, doctor, db-guard, QA
  skills/           The engineering operating system (ARCHITECT/REMEMBER/…)
  docs/             This folder
  jdds.db           SQLite data vault (committed as a seed snapshot)
```

## By task

| I want to… | Open |
|---|---|
| Change the app shell / add a tab | `src/components/screens/stock-chat.tsx`, `src/components/layout/sidebar.tsx` |
| Change sidebar defaults / shortcuts | `src/lib/sidebar/config.ts` |
| Add a language / translate UI chrome | `src/lib/i18n/` (`locales.ts` = registry + RTL, `dictionaries/en.ts` = canonical keys, `dictionaries/index.ts` = translations, `translate.ts` = lookup, `store.ts` = persisted choice + `<html lang/dir>`, `use-t.ts` = hook) |
| Add an accessibility option | `src/lib/i18n/store.ts` (`A11yPreferences` + document classes), `src/app/globals.css` (`a11y-*` rules), `src/components/screens/customization-settings.tsx` |
| Change UI sounds / add a cue / add a voice pack | `src/lib/sounds/` (`config.ts` = cues + `SOUND_PACKS` + asset path helper, `sound-manager.ts` = Howler singleton with per-source cache, `store.ts` = persisted prefs incl. pack + per-cue volume/mute/custom, `sound-provider.tsx` = delegated listener), assets `public/sounds/<pack>/<cue>.wav`, UI `src/components/screens/sound-settings.tsx`; opt in with `data-sound="…"` or `sound.*()` |
| Work on the screener | `src/components/screens/market-overview.tsx` (shell: state, fetches, filters), `use-screener-filters.ts` (pure filter/sort), `use-global-markets.ts` + `market-overview-global-markets.tsx` (Global Markets tab), `use-market-tabs.ts` (forex/commodities state), `market-stock-tables.tsx` / `market-fund-etf-tables.tsx` / `market-tables.tsx` (tables), `market-loaders.tsx` (table loaders); shared screener logic/types/placeholders live in `src/lib/screener/` (`data.ts`, `format.ts`) |
| Work on heatmaps / volume analytics | `src/lib/heatmap.ts` (turnover math + payload contract), `src/app/api/heatmap/route.ts`, `src/lib/dashboard/heatmap-widget.tsx`, `src/components/screens/volume-analytics.tsx` |
| Work on Market Bubbles | `src/components/screens/market-bubbles.tsx` (consumes `/api/heatmap?volume=1`) |
| Work on the Earnings calendar | `src/components/screens/earnings-calendar.tsx` (shared grid + day detail), embedded at the top of the Market Screener (`market-overview.tsx`, `earnings` section key) and as the `EarningsCalendarWidget` (`src/lib/dashboard/widgets.tsx`); `src/lib/earnings.ts` + `src/app/api/earnings/route.ts` (Alpha Vantage → Nasdaq). No standalone page |
| Work on Fundamentals | `src/lib/fundamentals/` (`types`=Eclipse schema, `providers/`=SEC/FMP/Yahoo, `normalize`, `compute`=metrics+risks, `format`), `src/components/screens/fundamentals/` (`panel.tsx`=presentational sections, `use-fundamentals.ts`=data hook), route `src/app/api/fundamentals/route.ts`; Yahoo bridge `scripts/yfinance_fundamentals.py`. Rendered ONLY as the Market Screener popup's **Fundamentals** tab (`src/components/screens/tradingview-chart.tsx`) — there is no standalone page |
| Add a fundamentals provider | One `FundamentalsProvider` file in `src/lib/fundamentals/providers/` + a line in `PROVIDER_ORDER` (`providers/index.ts`); add its key to `PROVIDER_KEYS` if it needs one |
| Work on portfolio | `src/components/screens/portfolio/`, `src/lib/portfolio/`, `src/hooks/use-portfolio-engine.ts` |
| Work on portfolio risk/correlation math | `src/lib/portfolio/matrix.ts` (date-aligned correlation + Euler risk decomposition), `src/lib/portfolio/risk.ts` |
| Work on portfolio widgets | `src/components/screens/portfolio/widgets.tsx` (registry + renderers), `use-fund-data.ts` (data bundle) |
| Work on the journal | `src/components/journal/`, `src/lib/journal/` |
| Journal date formatting | `src/lib/journal/dates.ts` — journal dates are UTC everywhere, so format month/day labels in UTC or they render a month off |
| Seed / clear journal demo data | `src/lib/journal/demo.ts` (generator + marker), `src/app/api/journal/demo/route.ts` (seed/clear), `scripts/seed-journal.ts` (CLI wrapper) |
| Work on the dashboard widgets | `src/lib/dashboard/`, `src/components/screens/dashboard/` |
| Work on Live Intelligence (live news streams) | `src/lib/dashboard/live-intelligence-widget.tsx` (player + states + channel manager), `live-channels.ts` (channel registry + embed/safety helpers), `live-intelligence-store.ts` (persisted selection), `live-resolver.ts` + `src/app/api/live-streams/route.ts` (server-side cached current-live-id resolver) |
| Add/edit a dashboard widget | `src/lib/dashboard/registry.tsx` + `widgets.tsx` (and `widget-def.ts` contract) |
| Work on the widget-grid engine | `src/lib/workspace/`, `src/components/workspace/` |
| Work on the agentic runtime (agents, tools, providers, events) | `python/harness/` (`agents.py`, `tools.py`, `models.py`, `graph.py`, `events.py`); architecture: `docs/harness/architecture.md`; evidence-grounded answering: `docs/harness/phase-4-progress.md` and `phase-4-opencode-prompt.md` |
| Work on MCP (connect local stdio servers, select tools) | `python/harness/mcp/` (`config.py` = server/effect contract + threat boundary, `naming.py` = namespacing/schema validation/effect trust, `client.py` = stdio client, `manager.py` = registry adapter + lifecycle + catalog confirmation); config `<repo root>/mcp-servers.json` (`HARNESS_MCP_CONFIG` override); catalog API `python/harness/main.py` (`/mcp/*`, operator auth via loopback/token); front door `src/lib/harness/mcp-{client,types}.ts` + `src/app/api/harness/mcp/`; UI Settings › MCP Servers (`src/components/screens/mcp-settings.tsx`); default-agent reachability `allowMcpTools` in `agents.py` + `graph.effective_allowlist`; architecture `docs/harness/architecture.md` (MCP boundary), ADR-H38/H39/H40 in `docs/harness/decisions.md`; tests `python/tests/test_mcp*.py` + fixtures `python/tests/mcp_fixtures/` |
| Install / repair the MCP client dependency | `python/requirements.txt` (`mcp`), `scripts/setup-python.js`, `scripts/doctor.js` (probes `import mcp`), `src/lib/harness/runtime-config.ts` (`PYTHON_MCP_DEPS`) |
| Review the agentic-coding roadmap | Repository root `agentic-plan-implementaion.md` §15 (capability contract + Phase 7 delivery gates); current runtime boundaries: `docs/harness/architecture.md` |
| Review the original agentic harness implementation vision | Repository root `agentic-plan-implementaion.md` (planning reference; current architecture is in `docs/harness/`) |
| Work on skills (manifest, registry, permissions, execution) | `python/harness/skills/` (`manifest.py`, `registry.py`, `permissions.py`, `store.py`, `runtime.py`, `schema_validation.py`, `learning.py`, `draft.py`, `evaluation.py`, `lifecycle.py`); library `python/harness/skills/library/`; architecture: `docs/harness/phase-3-architecture.md` |
| Change skill input/output contract validation or execution limits | `python/harness/skills/schema_validation.py` (full JSON Schema + self-check), `runtime.py` (`_validate_output`, `validate_input`, `maxToolCalls`), `python/harness/graph.py` (`tools_node` budget enforcement), `python/harness/schemas.py` (`AgentConfig.maxToolCalls`, `TOOL_BUDGET_EXCEEDED`) |
| Change a skill's persisted version identity / drift detection | `python/harness/skills/manifest.py` (`version_identity`), `registry.py` (`load_all` drift check, `_materialise_manifest`) |
| Run/read the memory retrieval evaluation | `python/harness/eclipse_memory/eval/` (`dataset_v1.json` = labeled set, `__init__.py` = runner + metrics + `THRESHOLDS`/`check_thresholds` + `format_report`, `__main__.py` = `python -m harness.eclipse_memory.eval`); baseline `recallSupported` 1.0 / precision 0.727 / leakage 0 / forbidden 0; per-kind slices include paraphrase, synonym, typo, multi-turn, conflict, stale, no-match. Deterministic normalization (synonyms/stemming/typo) is used; semantic retrieval is deliberately deferred |
| Run/read the dedicated semantic evaluation (cases lexical misses) | `python/harness/eclipse_memory/eval/semantic_v1.json` (labeled set), `eval/semantic.py` (runner + metrics + `SEMANTIC_THRESHOLDS`/`check_semantic_thresholds` + `format_semantic_report`), `eval/semantic_cli.py` = `python -m harness.eclipse_memory.eval.semantic_cli`; reports lexical-only vs semantic-enabled vs combined, candidate recall/false-candidate rate, confirmation/conflict-review accuracy, absolute safety floors. Honest result: deterministic normalization closed the gap; semantic stays off by default |
| Change the optional local semantic backend / candidate types | `python/harness/eclipse_memory/semantic.py` (`SemanticBackend`, `CharNgramBackend`, optional `LocalEmbeddingBackend`, `backend_health`, `classify_candidate`, `strongest_actionable`, `find_candidates` bounds); policy `semantic_conflict_backend`; service `_semantic_conflict_candidate`/`semantic_status`; route `/eclipse-memory/semantic-status` + `/eclipse-memory/semantic/rebuild` |
| Change memory value-substitution / confirmation safety | `python/harness/eclipse_memory/conflicts.py` (`_value_changed`, `_distinctive`, `REASON_VALUE_CHANGED`, confirmation branch), `normalize.py` (synonym groups, numeric tokens); tests `test_memory_semantic_eval.py`, `test_memory_contradiction_expanded.py` |
| Change skill execution observability (validation result, tool usage, pinned version) | `python/harness/eclipse_memory/schema.py` (migration 9: `SkillExecution.outputValidated`/`metrics`), `store.py` (`finish_execution`, `_execution_row`), `skills/runtime.py` (persists them), `src/lib/harness/skills-types.ts` (`SkillExecutionRecord`), `src/components/screens/skills/execution-activity.tsx` |
| Work on Eclipse-Memory (memory DB, retrieval, corrections, mistakes) | `python/harness/eclipse_memory/` (`config.py`, `schema.py`, `db.py`, `store.py`, `service.py`, `retrieval.py`, `profile.py`); tools `python/harness/memory_tools.py`; architecture + audit: `docs/harness/phase-3-memory-progress.md` |
| Work on the compact prompt profile (always-available personalization) | `python/harness/eclipse_memory/profile.py` (`build_profile`, `render_prompt_block`, bounds), service `profile_preview`/`profile_history`, injection in `python/harness/graph.py` (`_profile_context`), migration 12 `MemoryProfileSnapshot`, routes `src/app/api/eclipse-memory/profile*`, UI Profile tab |
| Work on full-session historical recall | `python/harness/session_index.py` (redact + index a run), `python/harness/persistence.py` (`SessionMessage`, `SessionMessageFts`, `search_session_messages`, `open_session`, `fts5_available`), tools in `python/harness/memory_tools.py`, routes `src/app/api/session-search/**`, UI History tab, prompt "Prior sessions" |
| Work on automatic learning review | `python/harness/learning_review.py` (`LearningReviewQueue`, `review_run`), `python/harness/persistence.py` (`LearningReview`), queue wired in `python/harness/service.py` + `main._lifespan`, routes `/learning-review*` + `src/app/api/learning-review/**`, UI Reviews tab |
| Work on the file-based memory projection | `src/lib/harness/memory-files.ts` (render/parse/backup/restore), routes `src/app/api/eclipse-memory/files/**` + `/import/markdown`; projection root `.black-eclipse/memory/`; UI Health tab Markdown section |
| Change the memory DB location / migrations | `python/harness/eclipse_memory/config.py` (`ECLIPSE_MEMORY_DB_PATH`, `repo_root`, `db_identity`, `legacy_candidate_paths`), `schema.py` (append a migration tuple), `db.py` (runner + `reconcile_legacy`) |
| Change explicit memory-intent detection | `python/harness/eclipse_memory/intent.py` (`detect_memory_intent`) wired in `python/harness/graph.py` (`_apply_memory_intent`, `_learning_eligibility`); service apply in `eclipse_memory/service.py` (`apply_explicit_intent`) |
| Change memory decision/authorization rules (save/suggest/history_only/ignore) | `python/harness/eclipse_memory/decision.py` (`decide_turn`, `authorize_proposal`); every write path routes through `EclipseMemoryService.decide_turn`/`commit_decision` |
| Change memory/skill API operator authorization (transport/token, not a body boolean) | `python/harness/main.py` (`require_operator` FastAPI dependency on every mutation endpoint), front-door token forwarding in `src/lib/harness/{eclipse-memory-client,skills-client}.ts` (`X-Harness-Operator` via `runtimeCallbackToken`); tests `python/tests/test_memory_api_auth.py`, `test_mcp_api.py` |
| Change memory retrieval ranking / relevance / scope isolation | `python/harness/eclipse_memory/retrieval.py` (`_score` relevance signal, `_STANDING_TYPES`, scope-owner filter, `_highest_authority_only`, diagnostics), `normalize.py` (synonyms/stemming/typo tolerance/subject aliases), `service.py` (`retrieve`), `store.py` (`find_suggestion_by_signature` scope-aware) |
| Change memory lifecycle / expiry / contradiction handling | `python/harness/eclipse_memory/schema.py` (migration 10 lifecycle columns, migration 11 maintenance state), `store.py` (`restore_memory`, `supersede_memory`, `confirm_memory`, `record_access`, `list_lifecycle_memories`, `record_maintenance`/`maintenance_status`), `service.py` (`write_memory` conflict branch, `run_retention_maintenance`/`expire_due_memories`/`retention_status`, `renew_memory`, `explain_memory`), `conflicts.py` (`detect_conflict`, authority-aware decisions), `normalize.py` (`CONCEPT_AXES`/`axis_polarity`/`axes_contradict`, `is_temporary_instruction`) |
| Change contradiction detection (lexical normalization or optional semantic candidates) | `python/harness/eclipse_memory/conflicts.py` (authority-aware `detect_conflict`), `normalize.py` (concept axes + polarity/negation + temporary detection), `semantic.py` (optional local candidate backend + bounds), `service.py` (`_semantic_conflict_candidate`, `semantic_status`), policy keys `semantic_conflict_*`; eval `python/harness/eclipse_memory/eval/contradictions*.py`; docs `harness/memory-contradiction-detection.md` |
| Change memory retention behaviour (when the sweep runs, expiry rules) | `python/harness/eclipse_memory/service.py` (`_retention_expiry`, `renewal_expiry`, `expire_due_memories`, `run_retention_maintenance`, `retention_status`), `schema.py` (migration 11 `MemoryMaintenance`), `python/harness/main.py` (`_lifespan` startup hook + `/eclipse-memory/retention`), `python/harness/service.py` (`run_startup_maintenance`); UI `eclipse-memory-screen.tsx` Lifecycle tab |
| Export / import / backup / reset local memory | `python/harness/eclipse_memory/transfer.py` (`export_payload`/`import_payload`/`create_backup`/`database_health`/`reset_memory`), endpoints `/eclipse-memory/{export,import,backup,database-health,reset}`, UI `eclipse-memory-screen.tsx` Health tab |
| Change skill usefulness metrics / promotion evidence | `python/harness/eclipse_memory/skill_quality.py` (`skill_quality_metrics`/`compare_versions`/`promotion_evidence`), endpoints `/skills/{id}/quality|promotion-evidence|quality/compare` |
| Work with memory suggestions (Save/Dismiss, inert proposals) | `python/harness/eclipse_memory/{schema,store,service}.py` (`MemorySuggestion`, `create_suggestion`/`accept_suggestion`/`dismiss_suggestion`), routes `src/app/api/eclipse-memory/suggestions/`, UI `src/components/screens/eclipse-memory/eclipse-memory-screen.tsx` (Suggestions tab) |
| Work on ordinary-chat learning / "Create skill draft" | `python/harness/graph.py` (`_create_explicit_skill_draft`, `_is_recurring_statement`, `_learning_eligibility`, `memory` blob), `python/harness/skills/learning.py` (`analyze_run` recurrence gate, `_record_recurrence`, `explicit_skill_candidate`), route `/learning/eligibility/{runId}`, UI `src/components/chat/memory-action-panel.tsx` + `src/lib/chat/memory-action.ts` |
| Work on recurrence evidence (when a repeated convention/workflow is learned) | `python/harness/eclipse_memory/store.py` (`record_recurrence`/`recurrence_count`, `MemoryRecurrence` migration 8), `python/harness/eclipse_memory/service.py` (`decide_turn`), `python/harness/persistence.py` (`record_learning_recurrence`/`learning_recurrence`, `LearningRecurrence`/`LearningRecurrenceRun`), `python/harness/skills/learning.py` (`_candidate_recurrence_key`, `_recurrence_count`) |
| Invoke an enabled skill from chat | `python/harness/memory_tools.py` (`skill_invoke`), `python/harness/skills/runtime.py` (`invoke_skill_from_run`, `list_invocable_skills`); prompt in `python/harness/prompts.py` |
| Change memory policy / defaults / bounds | `python/harness/eclipse_memory/policy.py` (`DEFAULTS`, `BOUNDS`, `LOCKED_VALUES`, `MODE_KEYS`/`derived_flags`); UI `eclipse-memory-screen.tsx` Policies tab |
| Change mistake detection | `python/harness/eclipse_memory/mistakes.py` (categories + heuristics) |
| Work on the Eclipse Memory UI / API | `src/components/screens/eclipse-memory/`, `src/lib/harness/eclipse-memory-{browser,client,types}.ts`, routes `src/app/api/eclipse-memory/` |
| Add/edit a runtime skill | A folder under `python/harness/skills/library/<category>/<name>/` with `skill.json` + `SKILL.md` (+ optional `tests/cases.json`); it is loaded at runtime boot by `skills/loader.py` |
| Work on the Skills UI | `src/components/screens/skills/` (`skills-screen.tsx` shell + library/detail/learning/evaluation/activity/draft panels), browser client `src/lib/harness/skills-browser.ts` |
| Work on user-authored skills | Python `python/harness/skills/authoring.py` (validation) + `registry.py` (`create/update/delete_user_skill`) + `eclipse_memory/store.py` (`UserSkill`); UI `src/components/screens/skills/skill-author-form.tsx`; routes `src/app/api/skills/author/` |
| Work on the skill front door / API | `src/lib/harness/skills-client.ts` (server), routes `src/app/api/skills/`, `src/app/api/learning/`, `src/app/api/skill-executions/`, `src/app/api/skill-drafts/`, `src/app/api/evaluations/` |
| Change an agent's system prompt / identity | `python/harness/prompts.py` (e.g. `ECLIPSE_AGENT_SYSTEM_PROMPT`), composed in `agents.py` — authoritative in Python |
| Add a harness tool / agent / model provider | `python/harness/finance_tools.py` (or a new `register_*`), `python/harness/agents.py`, `python/harness/models.py` (`PROVIDER_CATALOG`) — see `docs/harness/architecture.md` → Extension points |
| Work on hybrid financial retrieval / source selection | `python/harness/retrieval/` (`planner.py` = source selection, `layer.py` = orchestrator, `structured.py`/`web.py` = providers, `cache.py`, `parallel.py`, `validate.py`, `conflicts.py`, `aggregate.py`); tools in `python/harness/retrieval_tools.py` |
| Add/edit a retrieval data type or provider | `retrieval/contract.py` (`DataType`), `retrieval/planner.py` (`_PLAN`), `retrieval/policies.py` (freshness + TTL) — new provider implements `retrieval/sources.py` `RetrievalSource` |
| Work on evidence-grounded answering (Phase 4) | `python/harness/research/` (`mandate.py` = typed mandate + narrow classifier, `coverage.py` = per-leg evidence gate, `claims.py` = structured claims + deterministic validator, `calculations.py` = derived metrics, `citations.py` = citations + response metadata, `failures.py` = failure classes, `periods.py` = canonical period parsing, `ids.py` = stable content digests, `synthesis.py` = bounded model synthesizer, `supersession.py` = restatement chains, `run.py` = live-chat integration, `receipt.py` = durable receipt, `engine.py` = orchestration); progress `docs/harness/phase-4-progress.md` |
| Work on web escalation when structured data is empty/stale/missing a period (Phase 5) | `python/harness/research/escalation.py` (bounded primary→secondary source hierarchy), `web_facts.py` (span-anchored deterministic fact extraction/validation), `budget.py` (search/fetch/page/time/token caps); `retrieval/web.py` (`WebResearchSource` now serves `financial_statements`) |
| Run/read the semantic-support evaluation | `python/harness/research/eval/` (`dataset_v1.json` = human-labeled set, `dataset_escalation_v1.json` = source-hierarchy set, `escalation.py` = runner, `__init__.py` = runner, `__main__.py` = CLI); `PYTHONPATH=python python -m harness.research.eval` |
| Work on the chat evidence/receipt surface | `src/components/chat/research-evidence-panel.tsx` (answer → calculations → limitations → numbered Sources → run detail), `src/lib/chat/research-provenance.ts` (pure render model + tests), `src/app/api/harness/runs/[id]/receipt/route.ts`, `getRunReceiptFromRuntime` in `src/lib/harness/python-client.ts`, `ResearchRunInfo` in `src/lib/harness/types.ts` |
| Change what the research answer PROSE contains vs the Sources area | `_render_answer` in `python/harness/research/run.py` (prose only — citations/limitations/failedRoutes are structured fields), `python/harness/research/citations.py` (`build_citations` provenance), `failedRoutes`/`stopReasonText` on the `research` blob in `python/harness/graph.py` |
| Add a deterministic derived metric | `python/harness/research/calculations.py` (one function + a `MIN_OBSERVATIONS`/`CALCULATORS` entry), tests `python/tests/test_research_calculations.py` |
| Add/edit a research mandate fact leg or task type | `python/harness/research/mandate.py` (`KNOWN_METRICS`, `parse_mandate`, `TaskType`) |
| Change the research answer validator or coverage rules | `python/harness/research/{coverage,claims}.py` |
| Work on the research receipt / API | `python/harness/research/receipt.py`, `python/harness/persistence.py` (`ResearchReceipt`, `save_receipt`/`get_receipt`), endpoints in `python/harness/main.py` (`/research/*`) |
| Work on truthful global coverage / capability | `src/lib/harness/capability.ts` (`buildCapabilityMatrix`), `get_coverage`/`get_capability_matrix` in `python/harness/finance_tools.py` |
| Add/adjust a local regulator/exchange filing route | `LOCAL_FILING_HINTS` + `local_filing_hint` in `python/harness/retrieval/web.py` (used by `research/escalation.py` `_build_query`); primary-host labels in the same file |
| Change redirect handling for official hosts | `safeGet` `maxRedirects` in `src/lib/connectors/security.ts` (bounded, https-only, re-validates every hop); enabled in `web-research.ts` `fetchWebPageDetailed` |
| Change web search / page retrieval | `src/lib/web-research.ts` (page fetch + diagnostic facade + PDF/JSON/XML extraction) + `src/lib/web-search.ts` (ordered, independent search providers) + `src/lib/retrieval-diagnostics.ts` |
| Resolve a global ticker (Yahoo suffix, local code) | `src/lib/markets.ts` (`EXCHANGE_SUFFIX_ALIASES`, `splitExchangeSuffix`), `resolveVaultInstrument` in `data-bridge.ts`; mirrored `infer_market_from_symbol` in `python/harness/retrieval/structured.py` |
| Gate a provider by market eligibility (e.g. SEC non-US) | `python/harness/retrieval/structured.py` (`SecFilingsSource.eligible`), `secFilings` in `data-bridge.ts` |
| Work on source-health keying/aggregation | `sourceHealth` in `src/lib/harness/data-bridge.ts` (keyed `source × market × assetClass`) |
| Link learning candidates to run diagnostics/scope | `python/harness/skills/learning.py` (`_diagnostic_summary`, `_infer_scope`), `eclipse_memory/{schema,store}.py` (migration 4), UI `src/components/screens/skills/learning-queue.tsx` |
| Update a provider-eligibility rule from a run | `python/harness/skills/learning.py` (`provider_eligibility_improvement` candidate; operator-gated) |
| Configure an extra web-search provider | Settings vault keys `SEARCH_API_CONFIG` (public JSON: url/authKind/authParam/field paths) + `SEARCH_API_KEY` (secret); resolved in `data-bridge.ts` (`resolveCustomSearchProvider`) |
| Work on retrieval failure diagnostics / health | `src/lib/retrieval-diagnostics.ts`; `research_health` capability in `data-bridge.ts`; probe tool `get_research_health` in `python/harness/finance_tools.py` |
| Work on the direct SEC filings route | `src/lib/harness/data-bridge.ts` (`secFilings`, identity-gated), `src/lib/fundamentals/providers/sec-edgar.ts` (`fetchSecCompanyFacts`), `python/harness/retrieval/structured.py` (`SecFilingsSource`) |
| Work on the resilient research loop / retry / stop reason | `python/harness/retrieval/retry.py`, `python/harness/research/engine.py` (`legStatus`, `stopReason`), `research/run.py` (final-answer builder) |
| Run the Phase 6 NVDA labeled regression / live smoke | `python/harness/research/eval/nvda.py` + `dataset_nvda_v1.json`; smoke `python/harness/research/smoke.py` (`npm run test:smoke`) |
| Change route eligibility / skip vs failure categories | `python/harness/retrieval/routing.py` (`classify_skip`, `classify_outcome`); used in `retrieval/layer.py` |
| Change identity/comparability validation (demerger, 9M vs 12M, basis, scale, currency) | `python/harness/research/comparability.py` (`LegDescriptor`, `check_comparability`); wired in `research/engine.py`, receipt `comparability`, metadata `blockedComparisons` |
| Add a country-aware official filing route | `FILING_ROUTES` in `src/lib/harness/capability.ts` + `LOCAL_FILING_HINTS` in `python/harness/retrieval/web.py` |
| Change per-capability provider health | `python/harness/data-bridge.ts` (`encodeHealthKey`/`decodeHealthKey`, `recordHealth`, `sourceHealth`), `src/lib/harness/coverage.ts` (`capabilityHealthTargets`) |
| Change document extraction categories / metadata | `src/lib/web-research.ts` (`fetchWebPageDetailed`, `_documentIdFromUrl`, `_looksLikeValueLessXbrl`), `src/lib/retrieval-diagnostics.ts` (`RetrievalFailureCategory`) |
| Give the retrieval layer a new data source | `src/lib/harness/data-bridge.ts` capability + `DataCapability` in `src/lib/harness/types.ts` + the route whitelist |
| Change the harness front door / API proxy | `src/lib/harness/` (`run-service.ts`, `python-client.ts`, `python-runtime.ts`), routes `src/app/api/harness/` |
| Work on live streaming (SSE) | `python/harness/{events,graph,main}.py` (`model.delta` + `/runs/{id}/stream`), `src/app/api/harness/runs/[id]/stream/route.ts`, `src/app/api/harness/chat/stream/route.ts`, `src/lib/agent/registry.ts` |
| Work on conversation checkpoints | `src/lib/chat/checkpoint-store.ts`, `src/app/api/chat/checkpoints/route.ts`, `src/components/chat/checkpoint-bar.tsx` |
| Work on the git workflow (commit/push) | `src/lib/git/service.ts`, `src/lib/git/client.ts`, `src/app/api/git/route.ts`, `src/components/screens/git-panel.tsx` (Settings › Git) |
| Work on chat session workspaces (attached docs, agent output folders) | `src/lib/chat/session-store.ts` (server fs), `session-types.ts`, `extract.ts`, `session-client.ts`; routes `src/app/api/chat/session/`; UI `src/components/chat/session-bar.tsx`; context injection `python/harness/graph.py` (`_user_message`) — see `docs/ARCHITECTURE.md` § Chat session workspaces |
| Work on token usage / analytics | capture in `python/harness/graph.py` (`_extract_usage`), columns + `usage_summary()` in `python/harness/persistence.py`, `GET /usage` in `main.py`; proxy `src/app/api/harness/usage/route.ts` + `getUsageSummaryFromRuntime`; UI `src/components/screens/analytics-settings.tsx` (Settings › Analytics) |
| Give a Python tool JDdS data | `src/lib/harness/data-bridge.ts` (capability) + `DataCapability` in `src/lib/harness/types.ts`; the Python tool calls `ctx.data_bridge.fetch(...)` |
| Work on instrument identity / symbol resolution | `src/lib/instrument-identity.ts` (`resolveInstrument`, `verifyProviderIdentity`, `missingContractTerms`), market/venue aliases in `src/lib/markets.ts` (`resolveMarketId`, `MARKET_EXCHANGE_ALIASES`); collision fixtures + tests `src/lib/instrument-collisions.json` / `.test.ts`; bridge resolution in `src/lib/harness/data-bridge.ts` |
| Work on the failure contract / coverage | `src/lib/harness/failure.ts` (failure classes + derived messages), `src/lib/harness/coverage.ts` (declared country→asset-class registry, `coverage` capability), bridge `src/lib/harness/data-bridge.ts` (`unavailableClass`); Python `finance_tools.py` (`get_coverage`) |
| Work on macro series identity (A8) | `src/lib/harness/macro-identity.ts` (`resolveMacroSeries`, `macro_resolve` capability), mirrored in `python/harness/macro_identity.py`; tool `python/harness/retrieval_tools.py` (`macro_get_series`) |
| Work on retrieval determinism / degradation (D1–D3) | `python/harness/persistence.py` (`RetrievalRecord`, `save_retrieval`/`get_retrieval`), `python/harness/retrieval/layer.py` (durable replay, `_degradation`, `_conflicts_payload`), `python/harness/retrieval/validate.py` (`detect_incomplete`), `python/harness/retrieval/contract.py` (`degraded`/`incomplete`/`conflicts`/`provenanceVerified`) |
| Shared instrument resolution (the ONE gate) | `src/lib/harness/data-bridge.ts` — `resolveVaultInstrument` / `resolveAnyInstrument`; every resolving capability (`market_snapshot`, `fundamentals`, `live_quote`, `price_history`, `financial_statements`) calls it. FX/crypto classification in `src/lib/instrument-identity.ts` (`classifyIdentifier`); MIC map `micForExchange`. Test guard: `python/tests/test_identity_hardening.py` |
| Work on macro alias resolution | `src/lib/harness/macro-identity.ts` (`resolveMacroSeries`, single alias table + `unitBase`), mirrored/consulted by `python/harness/macro_identity.py`; `macro_resolve`/`macro_series` capabilities in `data-bridge.ts` |
| Work on source health / coverage | `src/lib/harness/coverage.ts` (`COVERAGE`, `healthTargets`), `sourceHealth()` in `data-bridge.ts`, recorded from `recordHealth` in `liveQuote` |
| Change harness persistence / the agent-memory DB | `python/harness/persistence.py` — separate `agent-memory.db`, NOT `prisma/schema.prisma` |
| Install / repair the Python runtime | `python/requirements.txt`, `scripts/setup-python.js` (`npm run setup:python`), `scripts/doctor.js`, `scripts/test-python.js` |
| Work on the market-panel grid | `src/lib/market-workspace/`, `src/components/market-workspace/` |
| Work on Investor Eye (world-state globe) | `src/lib/investor-eye/`, `src/components/investor-eye/`; audit + contract: `docs/investor-eye-architecture.md` |
| Add an Investor Eye source (GDELT/USGS/…) | `src/lib/investor-eye/sources/` (`registry.ts` + one `EventSource` adapter) **and** a governance entry in `src/lib/investor-eye/source-catalog.ts` (a test fails without one) |
| Declare a source's licence / attribution | `src/lib/investor-eye/source-catalog.ts` (surfaced by `/api/investor-eye/health` → `source-health-panel.tsx`) |
| Resolve a coordinate to a country (no place text) | `src/lib/investor-eye/admin-boundaries.ts` (`countryAtPoint`/`boundaryAtPoint`, point-in-polygon over `public/geo/world.geo.json`); centroid fallback is in `sources/firms.ts` |
| Add an Investor Eye map layer | `src/lib/investor-eye/layers.ts` (`MapLayer` builder + `LAYER_META` colour/group/symbol) + `store.ts` `DEFAULT_LAYERS`. Domain layers match event TYPE **or** economic CHANNEL (`buildDomainLayer`) — never type alone |
| Change Investor Eye colours / layer groups / legend | `src/lib/investor-eye/layers.ts` (`LAYER_GROUPS`, `LayerMeta`, `SEVERITY_COLORS`) — consumed by the controller, timeline, map adapter and full-page dock |
| Work on the full-page "map only" mode | `src/components/investor-eye/full-page-map.tsx` (+ `store.fullPage`); reuses `WorldMap`/`EventPanel`, portaled to body |
| Work on the live event stream / conflict feed | `src/components/investor-eye/live-feed.tsx`; conflict RSS wires in `DEFAULT_NEWS_FEEDS` (`src/lib/settings.ts`) |
| Change the 3D globe surface or the 2D map geometry | `src/lib/investor-eye/app-geo.ts` (`worldGlobeTexture(skin)` draws the globe texture from `public/geo/world.geo.json` — `GLOBE_PALETTES` holds the blue `glow` and plain `black` surfaces; `ensureWorldMapRegistered()` for 2D) |
| Change the map look (globe rim, pin glow, starfield) | `src/lib/investor-eye/map-echarts.ts` (`PIN_SIZE`/`PIN_GLOW`, `GLOBE_CORE_SIZE`/`GLOBE_HALO_SIZE`, `GEO_BY_SKIN`, light/atmosphere/emission) + `src/components/investor-eye/starfield.tsx` |
| Add or fix a map marker SHAPE | `src/lib/investor-eye/layers.ts` (`SYMBOL_PATHS`). A cut-out must wind OPPOSITE to its outer shape (nonzero fill rule) and a circle must be TWO 180° arcs — see §5n of `investor-eye-architecture.md` |
| Change which projection / surface skin is offered | `src/components/investor-eye/map-view-controls.tsx` (the only place; rendered by the hero header AND the full-page dock) + `MAP_SKINS`/`mapSkin`/`showStars` in `store.ts` (the STARS toggle unmounts `starfield.tsx`) |
| Debug a stuck full-screen loader on a map tab | `src/components/investor-eye/world-map.tsx` — its loader must stay SCOPED; `TopLoader` portals to `document.body` and will cover the whole app |
| Work on event→market price reaction | `src/lib/investor-eye/reaction.ts` (pure measurement) + `src/app/api/investor-eye/reaction/route.ts` + `reaction-panel.tsx` |
| Add/edit event alert rules | `src/lib/investor-eye/alert-rules.ts` (predicates + presets) + `src/app/api/investor-eye/alerts/route.ts` + `alerts-panel.tsx` |
| Fix where an event is plotted (city/port) | `src/lib/investor-eye/places.ts` (curated gazetteer + `resolvePlace()`); used by `sources/news.ts` |
| Fix where a POLICY event is plotted (capital vs centroid) | `src/lib/investor-eye/geo-resolve.ts` (`resolveEventLocation`, `reResolveEventLocation`) + `CAPITALS` in `countries.ts`; hollow markers are styled in `map-echarts.ts` |
| Work on saved views | `src/components/investor-eye/saved-views.tsx` + `store.ts` (`saveView`/`applyView`) |
| Work on data-source health / governance | `src/app/api/investor-eye/health/route.ts` + `source-health-panel.tsx` (reads `SourceRun` rows, joins `source-catalog.ts`) |
| Fix events merging into nonsense clusters | `src/lib/investor-eye/cluster.ts` (`shouldCluster` + `clusterSignature`) and `dedup.ts` (`dedupKeyFor`); never let synthesized title text score similarity |
| Surface real article headlines on events | `src/lib/investor-eye/enrich.ts` (news-corpus URL join, ~1% hit rate) and `article-meta.ts` / `article-meta-fetch.ts` (reads `og:title` from the linked page — the effective path); route `src/app/api/investor-eye/article/route.ts` |
| Make provider-synthesized event titles readable | `formatEventTitle` in `src/lib/investor-eye/format.ts` (used by the dossier header + live feed) |
| Work on the event detail dossier | `src/components/investor-eye/event-panel.tsx` (What happened / Actors / Where & when / Detail / Observed / exposure / reaction / Sources / Timeline) |
| Work on "Explain this event" (AI analyst) | `src/lib/investor-eye/event-record.ts` (prompt + honesty rules), `explain-panel.tsx`, `src/app/api/investor-eye/explain/route.ts` |
| Work on situation recurrence ("4th incident this week") | `src/lib/investor-eye/situations.ts` (pure grouping by type+country), `situation-panel.tsx`, `src/app/api/investor-eye/situations/route.ts` |
| Work on the relationship graph | `src/lib/investor-eye/graph.ts` (pure builder) + `graph-data.ts` (edges/persistence) + `graph-panel.tsx` |
| Add an AI Analyst tool (Investor Eye) | `src/lib/agent/investor-eye-tools.ts` (spread into `TOOLS`) |
| Change scraping / scheduling | `src/lib/scraper/` (`scheduler.ts`, `price-scraper.ts`, `fetchers/`) |
| Live quote freshness / read-through | `src/lib/scraper/live-quote.ts` (`getLiveQuote(s)`, TTL + dedup), `src/lib/scraper/yahoo-chart.ts` (shared chart fetch + ticker candidates), route `src/app/api/quote/route.ts` |
| Change news ingestion | `src/lib/news/ingest.ts`, `src/app/api/news/` |
| Change economics/macro | `src/lib/economics/`, `src/components/screens/economics/` |
| Change alerts | `src/lib/alerts/`, `src/app/api/alerts/`, `src/app/alerts/` |
| Change the AI agent / research | `src/lib/agent/` (`registry.ts`, `loop.ts`, `research.ts`, `tools.ts`) |
| Work on the chat response lifecycle / streaming UI state | `src/lib/agent/` — `response-model.ts` (typed status/activity), `events.ts` (`normalizeHarnessEvent`), `use-agent-run.ts` (shared hook); UI `src/components/chat/response-status.tsx`, `chat-history.tsx`, `activity-feed.tsx` + `activity-item.tsx` (tool/retrieval steps); plan/audit `docs/chat-ui-audit.md` |
| Change the chart | `src/lib/chart/`, `src/components/chart/`, `src/components/screens/tradingview-chart.tsx` |
| Add/fix a chartable index | `src/lib/indices.ts` (registry + providers), `src/lib/scraper/fetchers/psx-index.ts` (non-Yahoo source); `HEATMAP_MARKETS` in `src/lib/heatmap.ts` for heatmap labels || Change global search (⌘K) | `src/lib/search/` (query grammar: `grammar.ts`; commands: `commands.ts`; calculator: `calc.ts`), `src/components/layout/global-search.tsx` |
| Change the header price ribbon | `src/components/layout/price-ribbon.tsx` (render + customization popover), `src/lib/ribbon/store.ts` (persisted symbol list, routing helpers); catalog symbols `src/lib/market-catalog.ts`; marquee styles `.price-ribbon`/`.price-ribbon-track` in `src/app/globals.css` |
| Add a palette sub-page / make a view reachable | `registerPage` in `src/lib/search/registry.ts` (`subroute`, `group`, `child`) + `useSubroute(<tab>, …)` in the screen; hook: `src/hooks/use-subroute.ts` |
| Change deep links / "open in new tab" | `src/lib/search/deep-link.ts` (`destinationToHref`/`parseDeepLink`), URL boot + sync in `src/components/screens/stock-chat.tsx`; anchors in `sidebar.tsx` + `global-search.tsx` |
| Add a symbol to the watchlist outside React | `addToWatchlist` in `src/lib/dashboard/watchlist-store.ts` |
| Create a price alert programmatically | `src/lib/alerts/quick-alert.ts` → `POST /api/alerts` |
| Change the Aurora glow | `src/components/ui/Aurora.tsx`, `src/lib/aurora-sentiment.ts`, `src/lib/aurora/` |
| Change the Market Regime model / components / taxonomy | `src/lib/regime/` (`types.ts` contract, `scoring.ts` scoring+confidence+classifier, `client.ts` DataHub hook, `store.ts` scope + panel-open, `visuals.ts` shader mapping), route `src/app/api/regime/route.ts`, UI `src/components/layout/market-regime-control.tsx` (headless panel, mounted in `stock-chat.tsx`; opened from global search) |
| Change app theming / branding / design tokens | `src/lib/theme/` (`tokens.ts` model + presets + `themeFromBrandColor` + `deriveThemeColors`, `store.ts` persisted overrides + user presets, `bridge.ts` chart sync/preview) → tabbed panel `src/components/screens/customization-settings.tsx` (embeds `aurora-settings.tsx` + `chart-settings.tsx`); chart palette store/preview `src/lib/chart-palette-store.ts`; token defaults in `src/app/globals.css` |
| Change API protection / rate limits | `src/lib/api-guard.ts` |
| Add a data provider / work on connectors | `src/lib/connectors/` (`catalog`, `types`, `registry`, `resolver`, `custom-rest`, `security`, `secrets`, `mapping`, `refresh`, `store`); settings UI `src/components/screens/data-sources-panel.tsx` |
| Add/change a provider API key | `src/lib/provider-keys.ts` (`PROVIDER_KEYS` registry + encrypted vault) → `/api/provider-keys` → `src/components/screens/api-keys-panel.tsx` (filtered by `categories` prop); LLM keys render under `settings.ai`, financial/data keys under `settings.investor-eye` |
| Change Settings information architecture / sections | `src/components/screens/settings.tsx` (`SectionId`, `NAV`), sub-pages in `src/lib/search/registry.ts` (`settings.*`) |
| Explain why a provider exists / which feature uses it | `src/lib/providers/directory.ts` (`providerMeta`, `INVESTOR_EYE_FEATURES`) → registry UI `src/components/screens/provider-registry-panel.tsx` |
| Test an LLM connection | `POST /api/agent/test` (real endpoint request) |
| Pull/ingest custom dataset records | `PUT /api/datasets` → `pullDataset` in `src/lib/connectors/refresh.ts` |
| Scheduled connector refresh | `src/lib/connectors/refresh-scheduler.ts` (started in `src/instrumentation.ts`) |
| Change the DB schema | `prisma/schema.prisma` → `prisma db push` |
| Change the DB client | `src/lib/db.ts` |
| Change boot behavior / start a worker | `src/instrumentation.ts` |
| Change styling / glass classes | `src/app/globals.css` (see the `black-eclipse-ui` skill) |
| Change boot diagnostics | `scripts/doctor.js`, `scripts/up.js` |
| Change DB durability/backup | `scripts/db-guard.js` |

## By domain folder (`src/lib/`)

| Folder | Owns |
|---|---|
| `agent/` | Provider abstraction, tool loop, multi-agent research, journal tools |
| `src/lib/harness/` | Harness **front door**: input validation, vault/agent resolution, Python-runtime client + launcher, read-only JDdS data bridge |
| `python/harness/` (repo root) | The **agentic runtime**: agents, tools, model providers, LangGraph loop, events, `agent-memory.db` persistence |
| `alerts/` | Condition evaluator, feeds, notifier, alert monitor |
| `aurora/` | Aurora palette store + theme |
| `theme/` | Centralized customization: `EclipseTheme` model + presets + brand-color generator + derived-color resolution + validation (`tokens.ts`), persisted zustand store + CSS-token injection + user presets w/ chart palette (`store.ts`), chart-palette bridge + preview (`bridge.ts`) |
| `chart/` | Chart types, data hooks, indicators, drawings, structure, providers |
| `connectors/` | Universal Data Connector Layer: provider catalog, capability resolver, custom REST connectors, SSRF/secret security, custom datasets, scheduled refresh |
| `provider-keys.ts` (`lib/`) | The API-key vault: registry of every operator credential + AES-GCM encrypted storage + env resolution/apply |
| `navigation-history.ts` (`lib/`) | Capped in-memory tab-visit stack (`recordVisit`/`backTarget`) backing `Alt+←`; framework-free, no React |
| `providers/` | Provider directory: purpose / used-by / tier metadata + the Investor Eye feature→provider map (client-safe) |
| `dashboard/` | Widget catalog/definitions, renderers, market views, intelligence, dashboard + portfolio stores |
| `i18n/` | Interface localization: locale registry + RTL, dictionaries, translator, persisted language/accessibility store |
| `economics/` | Macro fetching, sources, calendar, snapshot |
| `fundamentals/` | Investor financial-analysis tier: provider abstraction (SEC/FMP/Yahoo), Eclipse schema normalization, derived metrics + data-driven risks, JDDS cache — see `ARCHITECTURE.md` › Fundamentals |
| `investor-eye/` | World-state tier: event sources (GDELT/USGS/FIRMS/news), normalization/clustering, map layers, source governance catalog, geographic boundary lookup, risk/exposure/transmission analytics, ingestion + cache |
| `journal/` | Journal data access, trade math, analytics suite, CSV import |
| `market-workspace/` | The market-panel workspace engine |
| `news/` | Background RSS ingestion |
| `portfolio/` | Portfolio types + risk math |
| `scraper/` | Price/universe scraping, scheduler, fetchers, CSV |
| `search/` | Global search registry, intent, query grammar/operators, ranking, resolver, calculator/commands, stores |
| `screener/` | Market-screener shared logic: instrument record types + zero-valued demo/placeholder rows (`data.ts`), price/cap/time formatting (`format.ts`). Consumed by the screener UI **and** `/api/stocks` |
| `sidebar/` | Sidebar config + store |
| `sounds/` | Terminal-style UI audio feedback: cue catalogue, Howler manager, persisted pref store, delegated listener provider |
| `workspace/` | The widget workspace kernel (DataHub, ops, persistence, canvas) |

## By API route group

`stocks` · `quote` · `price-history` · `asset-details` · `symbols` ·
`markets`(+`global`) · `indices` · `regime` · `forex` · `commodities` · `heatmap` ·
`earnings` (embedded calendar, no tab) · `news`(+`status`,`alert`) ·
`economics`(+`snapshot`,`calendar`) ·
`search`(+`global`,`index`) · `agent`(+`chat`,`research`,`activity`,`test`) ·
`journal/*` · `alerts/*` · `scraper`(+`import`) · `refresh` · `settings` ·
`cron`(+`run`,`refresh-news`) · `data-sources`(+`test`) · `datasets` ·
`data/[capability]` · `providers` · `provider-keys` · `fundamentals` ·
`harness/*` (runs, chat, models, agents, data, usage) ·
`investor-eye/*` (state, events, countries,
markets, layers, economy, companies, portfolio, risk, analogues, query, graph,
health).

## Key contracts (read before changing)

| Contract | File |
|---|---|
| Widget definition | `src/lib/workspace/widget-def.ts` |
| Widget registry (dashboard) | `src/lib/dashboard/registry.tsx` |
| DataHub topic/entry | `src/lib/workspace/data-hub.ts` |
| Connector contract | `src/lib/connectors/types.ts` |
| Fundamentals provider contract | `src/lib/fundamentals/types.ts` (`FundamentalsProvider`) |
| Fundamentals Eclipse schema | `src/lib/fundamentals/types.ts` (`FundamentalsSnapshot`, `FundamentalPeriod`, `FundamentalMetric`) |
| Investor Eye event-source contract | `src/lib/investor-eye/types.ts` (`EventSource`) |
| Investor Eye source-governance contract | `src/lib/investor-eye/source-catalog.ts` (`SourceCatalogEntry`) |
| Investor Eye map-layer contract | `src/lib/investor-eye/types.ts` (`MapLayer`) + `layers.ts` |
| Investor Eye relationship-graph contract | `src/lib/investor-eye/types.ts` (`RelationshipEdge`/`GraphNode`/`GraphLink`) |
| Investor Eye server cache | `src/lib/investor-eye/cache.ts` (globalThis-anchored, window-keyed) |
| Workspace layout ops | `src/lib/workspace/ops.ts` |
| Market workspace ops | `src/lib/market-workspace/ops.ts` |
| Agent provider interface | `src/lib/agent/types.ts` |
| Agent tool contract | `src/lib/agent/tools.ts` (`ToolDefinition`) |
| Harness front-door contracts | `src/lib/harness/types.ts` (proxy shapes + `DataCapability`) |
| Financial retrieval contract | `python/harness/retrieval/contract.py` (`FinancialRetrievalRequest`/`Result`, `NormalizedFinancialObject`, `EvidenceSet`) |
| Retrieval provider contract | `python/harness/retrieval/sources.py` (`RetrievalSource`, `SourceOutcome`) |
| Research mandate contract | `python/harness/research/mandate.py` (`ResearchMandate`, `FactLeg`, `parse_mandate`) |
| Evidence coverage contract | `python/harness/research/coverage.py` (`CoverageReport`, `LegCoverage`, `build_coverage`) |
| Claim + validation contract | `python/harness/research/claims.py` (`Claim`, `Synthesis`, `ValidationOutcome`, `validate_claims`) |
| Derived-calculation contract | `python/harness/research/calculations.py` (`CalculationResult`, `CALCULATORS`) |
| Research receipt contract | `python/harness/research/receipt.py` (`ResearchReceipt`) |
| Research response metadata / citations | `python/harness/research/citations.py` (`ResponseMetadata`, `Citation`, `build_response_metadata`) |
| Research synthesis contract | `python/harness/research/synthesis.py` (`ModelSynthesizer`, `parse_synthesis`) |
| Supersession chain contract | `python/harness/research/supersession.py` (`SupersessionChain`, `build_chain`) |
| Stable-identifier contract | `python/harness/research/ids.py` (`stable_digest`, `evidence_digest`, `calculation_digest`) |
| Web-escalation contract | `python/harness/research/escalation.py` (`escalate_web`, `EscalationResult`) |
| Web-fact validation contract | `python/harness/research/web_facts.py` (`validate_fact`, `WebFactExtractor`, `ExtractedFact`) |
| Research budget contract | `python/harness/research/budget.py` (`ResearchBudget`) |
| Retrieval diagnostic contract | `src/lib/retrieval-diagnostics.ts` (`RetrievalDiagnostic`, `RetrievalFailureCategory`) |
| Search provider contract | `src/lib/web-search.ts` (`SearchProvider`, `SearchAttempt`) |
| SEC filings source contract | `python/harness/retrieval/structured.py` (`SecFilingsSource`) |
| Retrieval retry policy | `python/harness/retrieval/retry.py` (`retrieve_with_retry`, `is_retryable`) |
| Source-selection policy | `python/harness/retrieval/planner.py` (`_PLAN`) |
| Harness agent contract | `python/harness/agents.py` + `python/harness/schemas.py` (`AgentConfig`) |
| Harness agent system prompts | `python/harness/prompts.py` (authoritative; the TS side sends only an `agentId`) |
| Harness tool contract | `python/harness/tools.py` (`ToolDefinition`, `ToolRegistry`) |
| MCP server/effect contract | `python/harness/mcp/config.py` (`MCPServerConfig`, `EffectClass`) |
| MCP client / adapter | `python/harness/mcp/client.py` (`MCPConnection`), `python/harness/mcp/manager.py` (`MCPManager`) |
| MCP default-agent reachability | `python/harness/agents.py` (`allowMcpTools`), `python/harness/graph.py` (`effective_allowlist`) |
| Work on MCP secret vault | `src/lib/harness/mcp-secrets.ts` (encrypted `SystemConfig` `mcp_secrets_v1`), routes `src/app/api/harness/mcp/secrets/route.ts`, bridge capability `mcp_secret_resolve` in `data-bridge.ts`; Python resolution `python/harness/mcp/client.py` (`secret_resolver`) |
| Work on finance MCP presets / workflows / diagnostics | `python/harness/mcp/presets.py` (integrations + workflow templates, pure data), `python/harness/mcp/diagnostics.py` (actionable setup checks), routes `/mcp/integrations` `/mcp/workflows` `/mcp/diagnostics`; TS proxies `src/app/api/harness/mcp/{meta,diagnostics}/` + client `src/lib/harness/mcp-client.ts`; UI `FinanceWorkflowWizard`/`MCPDiagnosticsPanel` in `src/components/screens/mcp-settings.tsx`; tests `python/tests/test_mcp_workflow.py` |
| Work on MCP test-env resilience (Windows temp dirs) | `python/harness/mcp/_testtmp.py` (`resolve_tmp_base`/`make_temp_dir`, honours `BLACK_ECLIPSE_TMP`) |
| Add a ready-made MCP server (Notion, Sheets, search, files) | Copy `mcp-servers.example.json` → `mcp-servers.json` (gitignored), store the referenced secrets in Settings › MCP Servers › Secret vault, then enable + select tools. Example entries: `filesystem`, `notion`, `sheets`, `excel`, `tavily`, `brave`, `yahoo-finance`, `memory`. |
| Work on remote MCP transport (HTTP) + SSRF guard | `MCPServerConfig.transport/url/auth` in `python/harness/mcp/config.py`, HTTP path `python/harness/mcp/client.py` (`_http_transport`), SSRF `python/harness/mcp/ssrf.py` (mirrors `checkOutboundUrl` in `src/lib/api-guard.ts`); UI transport selector in `src/components/screens/mcp-settings.tsx`; tests `python/tests/test_mcp_http.py` |
| Work on effectful-tool approvals (5G) | `python/harness/mcp/approvals.py` (`ApprovalStore`, `make_effect_authorizer`), enforcement `python/harness/tools.py` (`authorize_effect`), wiring `python/harness/graph.py`/`service.py`; routes `/mcp/approvals` + `src/app/api/harness/mcp/approvals/`; UI panel in `src/components/screens/mcp-settings.tsx` |
| MCP catalog front door | `src/lib/harness/mcp-types.ts` (`MCPServerView`), `src/lib/harness/mcp-client.ts`, routes `src/app/api/harness/mcp/` |
| Harness model-provider contract | `python/harness/models.py` (`ProviderSpec`, `PROVIDER_CATALOG`) |
| Harness run persistence | `python/harness/persistence.py` (`agent-memory.db`) |
| Harness usage analytics | `src/lib/harness/types.ts` (`UsageSummary`), route `src/app/api/harness/usage/route.ts` |
| Streaming status labels | `src/lib/agent/registry.ts` (`statusFromEvent`) |
| Checkpoint wire shapes | `src/lib/chat/session-types.ts` (`Checkpoint`, `CheckpointSnapshot`) |
| Git service contracts | `src/lib/git/service.ts` (`GitStatus`, `GitFileChange`, `GitCommitInfo`) |
| Mutation guard | `src/lib/api-guard.ts` |
| Tab ids | `AppTab` in `src/components/layout/sidebar.tsx` |

## Documentation trigger table

When a change touches one of these, update the listed doc in the same change:

| Changed path | Update |
|---|---|
| `src/instrumentation.ts`, `src/lib/scraper/`, `src/lib/news/` | `DATA-FLOW.md` |
| `prisma/schema.prisma`, `src/lib/db.ts` | `ARCHITECTURE.md` (JDDS section), `DATA-FLOW.md` |
| `src/lib/workspace/`, `src/lib/market-workspace/`, `src/lib/customize/` | `ARCHITECTURE.md` (workspaces), `DECISIONS.md` |
| `src/lib/api-guard.ts`, auth/env behavior | `ARCHITECTURE.md`, `QUICKSTART.md` |
| `src/lib/connectors/`, `src/lib/provider-keys.ts`, `src/app/api/data-sources/`, `src/app/api/provider-keys/`, `src/app/api/data/`, `src/app/api/datasets/`, `src/app/api/providers/` | `ARCHITECTURE.md` (connector layer + operator credentials), `DATA-FLOW.md`, `DECISIONS.md` |
| `src/lib/investor-eye/`, `src/components/investor-eye/`, `src/app/api/investor-eye/` | `ARCHITECTURE.md` (Investor Eye), `investor-eye-architecture.md`, `DATA-FLOW.md`, `DECISIONS.md` |
| `src/lib/fundamentals/`, `src/components/screens/fundamentals/`, `src/app/api/fundamentals/`, `scripts/yfinance_fundamentals.py` | `ARCHITECTURE.md` (Fundamentals), `DATA-FLOW.md` |
| `src/lib/harness/`, `src/app/api/harness/`, `python/`, `scripts/setup-python.js`, `scripts/test-python.js` | `harness/architecture.md`, `harness/decisions.md`, `harness/phase-2-progress.md`, `DECISIONS.md`, `QUICKSTART.md` |
| `python/harness/retrieval/`, `python/harness/retrieval_tools.py`, `src/lib/web-research.ts` | `harness/architecture.md` (retrieval layer), `harness/phase-2-progress.md`, `ARCHITECTURE.md`, `DECISIONS.md` |
| `python/harness/research/`, `/research/*` endpoints in `python/harness/main.py` | `harness/phase-4-progress.md`, `harness/architecture.md`, `harness/decisions.md`, `DECISIONS.md` |
| `python/harness/skills/`, `src/lib/harness/skills-*.ts`, `src/components/screens/skills/`, `src/app/api/skills/`, `src/app/api/learning/` | `harness/phase-3-architecture.md`, `harness/phase-3-progress.md`, `harness/architecture.md`, `DECISIONS.md` |
| `python/harness/eclipse_memory/`, `python/harness/memory_tools.py`, `src/lib/harness/eclipse-memory-*.ts`, `src/components/screens/eclipse-memory/`, `src/app/api/eclipse-memory/` | `harness/phase-3-memory-progress.md`, `harness/architecture.md`, `DECISIONS.md` |
| `src/components/screens/stock-chat.tsx`, `src/lib/sidebar/config.ts` | `OVERVIEW.md`, `ARCHITECTURE.md` |
| `src/lib/regime/`, `src/app/api/regime/` | `ARCHITECTURE.md` (Market Regime), `DATA-FLOW.md`, `OVERVIEW.md` |
| Setup/scripts/`package.json` scripts | `QUICKSTART.md` |
| A new top-level folder or major module | this file |
| A new architectural decision | `DECISIONS.md` |

## Retired / do not build on

- `src/lib/customize/` — superseded customization kernel (ADR-005).
- The old JDdS daemon and its PostgreSQL provider system — removed.
- `MarketSidePanel` as a separate page — its widgets are now the workspace right
  zone (legacy name: "rail").
