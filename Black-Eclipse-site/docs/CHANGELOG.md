# Change Log

## Rotation policy

This file keeps a rolling window of the **most recent 7 dated sections** (the active window). Older dated sections are **moved** - never deleted - into monthly archive files under `docs/changelog/YYYY-MM.md`. New entries are appended under the current date; the commit-msg hook checks this path. Rotation is by hand only when this file grows unwieldy; the archive link below points at where the older entries went.

> Older entries are archived under `docs/changelog/` (monthly). The most recent 7 dated sections are kept here.

## 2026-10-02

- **Universal financial-fact engine, slice 6: point-in-time, research router and
  corporate-action ingestion — the remaining sections.** Closes the three gaps the
  audit named. `finance_facts/point_in_time.py` (§15) keeps period_end /
  publication / retrieval distinct and refuses a later report under an earlier
  cutoff (`latest_known_per_metric` returns the revision available THEN, not the
  newest that exists today). `finance_facts/router.py` (§24) classifies a question
  into an intent and returns the evidence areas it NEEDS — with sector-specific
  additions — so the agent plans retrieval instead of taking whatever JDdS holds.
  `finance_facts/corporate_actions.py::extract_from_series` (§17) derives splits and
  dividends from the price series the yfinance bridge already carried
  (`scripts/yfinance_bridge.py` now emits `Dividends`/`Stock Splits` per bar;
  `normalize_history` lifts them to `stock_split`/`dividend` observations). Tests:
  `test_finance_facts_pit_router.py` (10 cases). Full release gate: vitest 178 files
  / 2027 tests, pytest 2425, ALL GATES PASSED. Still no ticker-specific logic; no
  prisma/schema.prisma or jdds.db change.
  docs updated: `docs/CHANGELOG.md`, `docs/NAVIGATION.md`

- **Universal financial-fact engine, slice 5: the final-answer gate.** Closes the
  loop — the answer is now checked against the run's own validated facts, exactly
  as code claims are checked against the verification ledger. `finance_facts/enforce.py`
  (`enforce_finance_answer`) is deterministic and makes no model call: if the answer
  asserts a metric the run's analysis EXCLUDED (ambiguous definition, no period,
  superseded) or states one side of a cross-source conflict without saying so, it
  requires a disclosure — it never silently strips the number. An already-present
  in-sentence disclosure is honoured, so it never nags. `source_collector.py` now
  accumulates the per-retrieval analysis across the run (deduplicated, higher
  confidence wins) and carries it on the `research` blob's `financeAnalysis`;
  `graph.py` adds ONE guarded block that appends the disclosure to the completed
  answer and emits `finance.analysis`. Wiring is additive and exception-guarded.
  Tests: `test_finance_facts_enforce.py` (8 cases) plus the collected-blob path.
  Full release gate: vitest 178 files / 2026 tests, pytest 2413, ALL GATES PASSED.
  docs updated: `docs/CHANGELOG.md`, `docs/NAVIGATION.md`

- **Desktop-alert notifications — audit hardening.** A review of the new
  desktop-notification provider found a real de-dup defect: it tracked only the
  single last-seen event id, but the `/api/alerts/live` feed is capped at 50 rows
  (`take: 50`), so a burst of alerts could push the last-seen id out of the window
  and re-announce an already-seen event. Detection is extracted to a pure,
  framework-free `src/lib/alerts/event-diff.ts` (`selectNewEvents`/`seedSeen`, a
  bounded 200-id seen-set) and the provider now consumes it. Adds
  `event-diff.test.ts` (5 tests, incl. the scroll-out-of-window case). Full audit
  run: `tsc --noEmit` clean, eslint clean, vitest 2026 passed, Python 2413 passed,
  eval gates ALL PASS, `next build` succeeded.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Desktop (OS) notifications for fired price alerts.** Fired alerts can now
  rise as native OS notifications on the user's laptop, not just the in-app feed
  on the `/alerts` tab. New client lib `src/lib/alerts/browser-notifier.ts` wraps
  the Web Notification API (opt-in localStorage flag `be_alerts_browser_v1`,
  default OFF; permission requested only from an explicit gesture; `show()` is an
  honest no-op unless granted). New `AlertNotificationProvider`
  (`src/components/layout/alert-notification-provider.tsx`), mounted once in
  `src/app/layout.tsx`, polls the always-recorded `GET /api/alerts/live` stream
  (10s, first poll seeds history so nothing replays) and raises one notification
  per genuinely new event. Settings › Alerts/Notifications
  (`alert-notifications-settings.tsx`) gained a "Desktop notifications" toggle
  with honest `off`/`blocked`/`on` state and a test-notification button. No service
  worker, so notifications show only while a BlackEclipse page is open — stated in
  the UI. Additive; no schema/API contract change. Tests:
  `src/lib/alerts/browser-notifier.test.ts` (5). Full suite 2021 passed;
  `tsc --noEmit` clean.
  docs updated: `docs/ARCHITECTURE.md` (Alert delivery), `docs/NAVIGATION.md`

- **Universal financial-fact engine, slice 4b: self-review fixes.** A careful pass
  over the new engine found and fixed four real defects. (1) `conflicts.detect_conflict`
  flagged two time-series bars at different dates as a disagreement and a single
  source repeating itself as a conflict — it now requires the same period AND
  different sources, and compares by canonical concept so two labels of one
  definition are comparable. (2) `analysis.analyze_result` reported each conflict
  twice (once per direction) and grouped by raw label; it now detects each pair once
  (keyed by object identity, since fact_ids can collide across sources) and groups by
  canonical definition. (3) `sector.classify` labelled a conglomerate that contains a
  bank as `bank`; a holding/conglomerate is now a structural classification that
  outranks a sub-business keyword, while the bank ownership still sets
  `contains_financial`. (4) `retrieval_tools._finish`/`_summarize` ran the analysis
  twice per tool call; it is now computed once and shared, with `_summarize` keeping
  a guarded fallback for direct callers. Regression tests added for the conflict
  cases. Tests: `test_finance_facts.py` (53 across the two files).
  docs updated: `docs/CHANGELOG.md`

- **Universal financial-fact engine, slice 4: the enforcing gate.** Every
  retrieval tool result now carries a validated `analysis` block the answer layer
  must honor. `finance_facts/analysis.py::analyze_result` runs the full chain on a
  retrieval result: lift each value into a `FinancialFact`, run the ordered
  data-quality gates, compute evidence-based confidence, detect and explain
  cross-source conflicts, build the evidence graph and report orphans, and classify
  the entity. A fact is marked **admissible** (only disclosures — stale, soft
  source) or **excluded** (no entity/period/definition, superseded, unreproducible);
  `presentable` is false when anything is excluded, so an ambiguous `revenue` is
  withheld rather than presented as a clean figure. `retrieval_tools._finish`
  attaches `analysis` to the structured payload and `_summarize` prints the
  notes + the withheld list; both are exception-guarded and additive. The label
  resolver is now case/separator-normalized, so a provider's `marketCap`,
  `market_cap` and `market cap` all resolve to the same definition. Tests:
  `test_analysis_returns_validated_facts_and_gate_verdicts`,
  `test_analysis_excludes_an_ambiguous_revenue_from_a_clean_answer`. Still no
  ticker-specific logic; no schema/jdds.db change.
  docs updated: `docs/CHANGELOG.md`, `docs/NAVIGATION.md`

- **Universal financial-fact engine, slice 3: wired into the retrieval tool
  summary.** The deterministic fact engine now runs on live retrieval output.
  `finance_facts/adapter.py::annotate_result` lifts every normalized object of a
  retrieval result into a `FinancialFact` and produces the honesty notes the
  answer must carry — accounting-definition ambiguity, detected business type, the
  financial-framework warning for entities containing banks/insurers, cross-source
  definition differences vs real disagreements, and stale values.
  `retrieval_tools._summarize` appends a "Data-quality notes:" block when there is
  something to disclose (absent otherwise, so no existing text changed). Metadata
  fields (sector/industry/name) are never mistaken for ambiguous financial metrics.
  Additive and exception-guarded: analysis can never break a summary. Test:
  `test_summary_surfaces_definition_ambiguity_and_sector_but_not_metadata`. Still
  no ticker-specific logic; no schema/jdds.db change.
  docs updated: `docs/CHANGELOG.md`

- **Phase 14 — the code capability, reachable from chat.** A coding request typed
  in ordinary conversation is now served by the code capability that already
  existed, instead of refusing for lack of a tool. A deterministic, model-free
  classifier `python/harness/code/request_intent.py::classify_code_request`
  (reached over the read-only operator-gated `POST /code/intent`) decides
  `code_change` | `code_question` | `not_code`, with an AMBIGUOUS turn defaulting
  to `not_code` (the refusal path is the safe failure). `agents.CHAT_CODE_TOOLS`
  is a NARROWED profile applied per turn inside the existing
  `graph.resolve_surface`, after the autonomy narrowing: `code_change` →
  `edit_verify` (write/execute/verify), `code_question` → `plan_only` (read-only).
  The four external actions (`code_commit`/`code_push`/`code_open_pr`/
  `code_deploy`) are absent from the declared set — external actions stay on the
  Code Tasks surface. The front door gains additive `autonomy`
  (`plan_only`|`edit_verify` only, fail-closed on anything else) and
  `analysisEnabled` on `RunRequestPayload`; `startChatRun` resolves and sends them
  from the classifier. A new `src/components/chat/chat-capability-panel.tsx`
  composes the existing Phase-4 verification panel and is wired through
  `activity-feed.tsx`/`activity-item.tsx`/`chat-history.tsx`, so a coding turn
  shows what Eclipse did in plain words. The code task list gains "Build this"
  (existing `/api/code/tasks`) and "Schedule" (existing `/api/jobs`, created
  DISABLED with `agent_id="code-agent"`, `autonomy="edit_verify"`). The runtime's
  registered tool set is UNCHANGED — an allowlist and a payload, never a tool.
  Tests: `python/tests/test_code_request_intent.py`,
  `test_chat_code_profile.py`, `test_code_reachability.py`,
  `src/components/chat/chat-capability-panel.test.ts`; ADR-H117.
  docs updated: `docs/harness/decisions.md` (ADR-H117), this file,
  `docs/NAVIGATION.md`, `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-14-reachable-code-capability.md`,
  `docs/harness/roadmap/progress/phase-14-progress.md`
- **Phase 14 audit follow-up.** A self-review found and fixed four defects. (a)
  The ADR-H117 append introduced mixed CRLF/LF into `docs/harness/decisions.md`
  (caught by `gitignore-guard.test.ts`), normalized back to LF. (b) The first cut
  of "Build this" only appeared on existing task rows, so an empty task list still
  had no way to start a work order — the exact symptom the phase existed to
  remove; `task-list.tsx` now renders a "what should Eclipse build or fix?"
  composer above the list and the empty state. (c) The classifier returned
  `not_code` for the user's literal wish ("create a new application", "build
  algorithms", "build a Monte Carlo simulator"); the software-object vocabulary
  gained those artifacts, a homograph guard stops "test the market" / "build a
  portfolio" self-matching, and `what does…` questions plus reported symptoms and
  named errors now classify correctly. (d) A refused code step
  (`code.refused`/`code.patch.refused`) now renders its ONE plain refusal
  sentence, with the raw code behind "details", instead of a technical operation
  label. Tests: `test_code_request_intent.py` 22→43 cases, `events.test.ts` two
  refusal cases. (e) The §6.4 capability view is now a first-class
  `RunResult.capability` (`{kind, profile, headline, verification}`), derived in
  `python/harness/code/capability.py` from the run's verification blob (the
  profile rides inside that existing additive blob — no new column, `persistence.py`
  ratchet untouched) and mirrored client-side by `coerceChatCapability`; the panel
  prefers it and falls back to the flat fields for older rows. Gates: vitest
  **178/2027**, pytest **2415**, `npm run build` exit 0.
  docs updated: `docs/harness/roadmap/progress/phase-14-progress.md`, this entry.

- **Universal financial-fact engine, slice 2: derived metrics, corporate actions,
  evidence graph.** Completes the deterministic foundation. `finance_facts/metrics.py`
  derives P/E, P/B (COMMON equity, §7), EV/EBITDA, ROE (parent-attributable), growth
  and more, each returning a `DerivedMetric` with formula + inputs + input periods +
  input sources + timestamp, and REFUSING mixed currency/period or a negative-EPS
  P/E rather than fabricating a number. `finance_facts/corporate_actions.py` flags
  splits/buybacks/spin-offs/M&A that make a naive historical comparison invalid and
  adjusts a pre-split price only when the ratio is known. `finance_facts/evidence.py`
  builds the Question→Claim→Derived→Fact→Source graph and detects orphans (a claim
  with no fact, a fact with no source). Tests: `test_finance_facts_metrics.py` (14
  cases). Still no ticker-specific logic; still pure Python; no schema/jdds.db change.
  docs updated: `docs/CHANGELOG.md`, `docs/NAVIGATION.md`

- **Universal financial-fact foundation: every fact carries its meaning, not just
  its value.** New pure-Python package `python/harness/finance_facts/` — the
  deterministic layer the LLM reasons OVER (no prompts for rules). It EXTENDS the
  Phase-4 evidence machinery (`research/{claims,supersession,calculations,periods}.py`
  are reused, not rebuilt) and adds the dimensions they lacked: a
  `FinancialFact` model (metric/definition/value/unit/currency, period with a
  period TYPE, distinct publication/source/retrieved timestamps, accounting +
  reporting standard, consolidation + attribution + ownership level,
  reported/derived, freshness, confidence, supersedes); an accounting ontology
  (`semantics.py`) that keeps Revenue ≠ Net Sales ≠ Gross Revenue and separates
  net income / attributable-to-parent / NCI and gross/net/financial debt and the
  cash variants (an ambiguous label like "revenue" resolves to None, never a
  silent guess); a universal period model (`periods_ext.py`) where FY ≠ TTM and H1
  ≠ FY; an independent TTM engine (`ttm.py`) that sums four adjacent quarters and
  flags a material vendor difference as CONFLICT with an investigation checklist;
  per-metric freshness (`freshness.py`); an evidence-based confidence model
  (`confidence.py`); sector classification + sector metric sets (`sector.py`, bank
  CET1/NIM, insurance combined ratio, REIT FFO, crypto, …); currency/unit + FX-basis
  normalization (`fx.py`); a structured semantic conflict record (`conflicts.py`)
  where consolidated-vs-parent earnings is a definition difference, not an error;
  and the ordered data-quality gate chain with distinct N/A reasons (`quality.py`).
  Nothing is ticker-specific — KCHOL is one row in the diverse regression suite
  (`test_finance_facts.py`, 33 cases: US tech, bank, insurance, REIT, energy,
  mining, holding/conglomerate, crypto, NCI, negative earnings, restated, ADR,
  stale-vault — asserted on RULES, not symbols). No prisma/schema.prisma or jdds.db
  change. This is the foundation slice; wiring it into the retrieval/research path
  is the next phase.
  docs updated: `docs/NAVIGATION.md`, this file

- **Phase 13 follow-up 3 — general multi-source, not price-only: the vault is a
  cache, not a precondition.** The earlier fixes verified the price leg, but two
  data classes were still vault-bound and would fail or go stale for anything the
  committed snapshot lacks: `fundamentals` (company profile) and `market_snapshot`
  (a symbol absent from the universe, or a vault row with no stored price).
  `src/lib/harness/data-bridge.ts` now enriches the profile from the existing live
  fundamentals pipeline (SEC → FMP → Yahoo) when the vault lacks it — and says
  which one answered via `profileSource`; `live_quote`/`market_snapshot` resolve an
  instrument outside the vault for a known covered market (`resolveAnyInstrument`
  recovers a `not_found` the same way `financial_statements` already did), so a
  live quote serves a symbol the vault never stored and the snapshot is never
  `UNAVAILABLE` merely because JDdS is. The identity gate still refuses
  AMBIGUOUS / `not_covered` / wrong-currency answers — the vault is skipped, not
  bypassed. The yfinance bridge now also carries `marketCap`. Tests:
  `data-bridge.test.ts` (profile enrichment + vault-hit short-circuit),
  `data-bridge-phase2.test.ts` (live fallback for no-row and no-price);
  `data-bridge-health.test.ts` updated so a both-sources-fail route is recorded as
  a failure. ADR-H116 amended.
  docs updated: `docs/harness/decisions.md` (ADR-H116), this file,
  `docs/harness/roadmap/progress/phase-13-progress.md`

- **Phase 13 follow-up 2 — per-field provenance: a live price no longer launders a
  stale market cap.** The first follow-up routed `get_market_snapshot` through the
  arbitrated layer, but the live provider used for US equities (yfinance
  `fast_info`) returns a price and **no market cap**, so the cap always fell back to
  JDdS — and the whole payload was stamped "verified", repeating the original demo
  defect in a new form (a verified-looking badge on a months-old cap). Two fixes:
  (1) the yfinance bridge now carries `marketCap` when the provider exposes it
  (`scripts/yfinance_bridge.py`, `fetchers/yfinance.ts`, `data-bridge.ts`), so the
  cap is genuinely cross-checked when possible; (2) when it is not, the snapshot
  tool now labels **each field** by origin (`finance_tools.py`): a value from a
  source that answered now is live; a value that fell back to the stored snapshot is
  annotated `— saved snapshot` with its stored time and source, and the top-level
  `verified` flag is true only when the PRICE itself is live (each `*Origin` is
  exposed on the structured payload). Regression tests:
  `test_demo_live_price_but_no_live_cap_labels_the_cap_saved` (the real US-equity
  shape), plus the updated demo tests. ADR-H116 amended.
  docs updated: `docs/harness/decisions.md` (ADR-H116), this file,
  `docs/harness/roadmap/progress/phase-13-progress.md`

- **Background Solid mode — fully tunable gradient/pattern and wordmark
  typography.** The gradient/pattern styles were static (fixed angle, fixed tile
  size) and the wordmark only offered font + size. Added: gradient shape
  (`solidGradientType`: linear/radial) and `solidGradientAngle`; pattern tile
  size `solidPatternScale` (4–80px) beside strength; and wordmark typography
  controls `textWeight` (100–900), `textWidth` (font-stretch, 50–200%),
  `textLetterSpacing` (−0.1–0.5em), `textLineHeight` (0.7–2), `textItalic` and
  `textUppercase`. `ChatWordmark` applies them; `resolveBackgroundCss` uses the
  gradient type/angle and pattern pitch. All new fields are normalized/clamped
  (`textWeight` rounds to the nearest 100). Settings panel gains the matching
  sliders/toggles; the option constants `GRADIENT_TYPE_OPTIONS` added.
  docs updated: `docs/ARCHITECTURE.md`, this file; test:
  `src/lib/backgrounds.test.ts`

- **Phase 13 follow-up — the price/market-cap ROUTE the agent actually used now
  verifies across sources.** The Phase-13 arbitration fixed the retrieval layer,
  but the Eclipse Agent had a second market-cap tool, `get_market_snapshot`
  (`python/harness/finance_tools.py`), that went STRAIGHT to JDdS and never ran
  the layer at all — so a months-old market cap was returned as current (the
  reported demo: "market cap of AMD" showed stale data). `get_market_snapshot`
  now runs its price/change/market-cap leg through the same arbitrated
  `current_quote` path (`_verified_price_leg`): a fresh live reading beats the
  saved snapshot, a stale snapshot is not asserted as current, the observation
  time and its age are stated, and when two sources disagree beyond the tolerance
  every contested figure is shown instead of one value silently chosen (the
  headline no longer falls back to the stored value in that case). `normalize_quote`
  now dates a live payload from its `observationTime` so cross-source conflict
  grouping can see it. The tool description is corrected. Regression tests:
  `test_demo_stale_market_cap_is_not_returned_as_current`,
  `test_demo_disagreement_is_shown_when_sources_differ`; the tool-execution
  property in `test_context_overflow.py` is asserted on recorded tool executions,
  not bridge calls. ADR-H115 amended.
  docs updated: `docs/harness/decisions.md` (ADR-H115), this file,
  `docs/harness/roadmap/progress/phase-13-progress.md`

- **Landing wordmark font list was all system fallbacks — now real,
  self-hosted faces.** Every `WORDMARK_FONT_OPTIONS` value was a font-family
  stack for a face the app never loaded (e.g. "Bodoni Moda", "Didot", "Playfair
  Display"), so all options rendered as the same system fallback and the choice
  felt broken. `src/app/layout.tsx` now loads 16 display faces via
  `next/font/google` (Bodoni Moda, Playfair, Cinzel, Cormorant, Orbitron,
  Audiowide, Michroma, Press Start 2P, Silkscreen, VT323, Major Mono Display,
  Space Mono, IBM Plex Mono, Bebas Neue, UnifrakturMaguntia, Rubik Glitch),
  self-hosted with no runtime request, exposed as `--font-*` CSS variables on
  `<html>`. `WORDMARK_FONT_OPTIONS` (`src/lib/backgrounds.ts`) now references
  those variables, adding pixel (Press Start, Silkscreen), ASCII/terminal
  (VT323, Major Mono, Space Mono, IBM Plex Mono) and stylised (Blackletter,
  Glitch, Bebas) choices; `DEFAULT_WORDMARK_FONT` becomes
  `var(--font-bodoni), Georgia, serif`. The Settings font picker is a clickable
  preview grid (each label rendered in its own face). Keep the option list in
  sync with the `layout.tsx` imports.
  docs updated: `docs/ARCHITECTURE.md`; app config: `src/app/layout.tsx`

- **Background: two types — Image or Solid (color/gradient/pattern + wordmark).**
  Reworked Settings › General › Background after removing the dead "Pattern"
  type. The type is now a real choice of two: **Image** (shipped/uploaded
  wallpaper, the default) or **Solid**. Solid has a `solidFill` of
  **Flat** / **Gradient** / **Pattern**: a `solidColor`, a two-color
  `solidColor`→`solidColor2` gradient (empty stops follow the theme background /
  brand tint), or a texture (`solidPattern`: grid / dots / diagonal / ASCII, at
  `solidPatternOpacity`) over the base fill — each with a customizable wordmark
  (text, font, color, size, strength, alignment, vertical). `BackgroundMode` is
  `image | solid`; `BackgroundPrefs` gains `solidFill`, `solidColor`,
  `solidColor2`, `solidPattern`, `solidPatternOpacity`, `textColor`. The
  wordmark paints via the new `isWordmarkVisible` helper: forced on in solid mode
  (it IS the backdrop), opt-in in image mode (the `textEnabled` toggle, disabled
  in solid since it is inherent). `resolveBackgroundCss` emits the solid stack
  (base fill + optional texture as a `background-image` list; brand-tinted ink);
  `ChatWordmark` applies `textColor`. The font picker is now a clickable
  preview grid (each option renders its own name in that typeface) instead of a
  Radix `Select` — more robust inside the modal and it actually shows the fonts.
  A saved `mode: 'pattern'` / `'none'` normalizes back to the default image.
  Tests updated; `resolveBackgroundCss`/`applyBackgroundToDocument` lost their
  now-unused `patternImage` parameter.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, this file; test:
  `src/lib/backgrounds.test.ts`

- **Phase 13 — source authority and freshness arbitration landed.** A price,
  series or macro answer is now chosen by freshness-then-strength across all
  eligible sources, with the disagreement preserved, instead of by the first
  source in a static table. Added `python/harness/retrieval/authority.py` — the
  ONE ordering table (`AUTHORITY`, one `DataTypeAuthority` row per data type) and
  a pure decision function (`decide_source`). `current_quote`,
  `historical_prices`, `macro_series` and `company_profile` become **arbitrated**:
  every eligible candidate runs through the existing `parallel.run_parallel` +
  `layer._resolve` + `conflicts.detect_conflicts` seam (no second conflict
  algorithm), so a fresh live reading is consulted alongside a saved snapshot and
  a vault-vs-live disagreement is surfaced as `CONFLICTING` instead of being
  unreachable. A candidate older than the type's freshness ceiling is rejected
  with `STALE_SOURCE` and the measured age; all-stale is `NO_FRESH_SOURCE`.
  `planner._PLAN` and `layer._SINGLE_BEST` are deleted and their readers
  repointed (one ordering in the tree, not three). `NormalizedFinancialObject`
  gains additive `observation_time`/`observation_source` (`provider_asof` |
  `snapshot_write` | `unknown`); `validate.validate_observations` flags ONE stale
  row inside an otherwise fresh payload and stamps a snapshot-write value `saved
  snapshot, not a live reading` (never worded as live). `data-bridge.ts`
  `marketSnapshot` supplies `observationSource: "snapshot_write"`; `liveQuote`
  supplies `provider_asof` only when the provider reports its own market time,
  else `unknown` — its old `asOf: new Date()` (the retrieval clock) is corrected.
  New `source.*` i18n keys and the extended plain-language gates. ADR-H115 and
  ADR-H116 written; `NAVIGATION.md` rows 149/150/352 updated. Tests:
  `test_source_authority.py` (15 cases, including the vault-vs-live disagreement
  that failed on the pre-change code) plus the retrieval regression suites.
  docs updated: `docs/harness/decisions.md`, `docs/harness/architecture.md`,
  `docs/NAVIGATION.md`, this file,
  `docs/harness/roadmap/progress/phase-13-progress.md`,
  `docs/harness/roadmap/phase-13-source-authority.md`, `docs/harness/roadmap/README.md`

- **Roadmap round 2 authored: phases 13–20 (reachability, source truth, and output)
  added to `docs/harness/roadmap/`.** Round 1 (phases 0–12) built the machinery of a
  harness; this round closes the six gaps a user reports against the *running* system,
  each traced to a measured cause and each with a paste-ready prompt. Added:
  `phase-13-source-authority.md` (the market-data vault is first for every
  price-shaped type and the first success wins, so a live provider is never
  consulted; measured from the live `jdds.db`: 0 of 55 195 price rows are fresh
  within 15 min and 22.2 % are older than 7 days, while `data-bridge.ts` hard-codes
  `cadenceSeconds: 24*60*60` and `validate.py` measures staleness only at dataset
  level — the phase adds one `AUTHORITY` table, arbitrated dispatch and
  per-observation age, and deletes `_PLAN`/`_SINGLE_BEST`), `phase-14-reachable-code-capability.md`
  (the code modules exist on the one registry, but `eclipse-agent`'s 27-tool
  allowlist has no code tool, `RunRequestPayload` has no `autonomy` field at all, and
  `analysisEnabled` is referenced **0** times in `src/` — the phase adds a
  deterministic request classifier, a narrow chat code profile and a chat capability
  panel), `phase-15-attachments-and-artifacts.md` (extract.ts is text+PDF only with a
  20 000-char silent truncation; the chat artifact surface prints a filename and a
  12-char hash and no route serves the file; `code_commit`'s handler performs **no git
  operation** yet returns `status: "approved"` — the phase adds office extractors,
  stated truncation, an artifact-serving route and a user-decided promotion with
  Option B recommended), `phase-16-bulk-acquisition.md` (the answer budget is 4
  searches / 8 fetches / 90 s, the analysis sandbox is `network=False` with 16 allowed
  imports, and the TS scraper layer is unreachable from the runtime — the phase adds a
  declared attributable source registry, an explicit acquisition budget and a new
  `data.collect` permission noun), `phase-17-working-on-a-cadence.md` (the job model,
  scheduler, delivery and seven templates exist; no tool can create a job — the phase
  adds a fixed catalogue, a default-off operator switch and an unattended-report
  honesty contract), `phase-18-visual-output.md` (no plotting library is importable and
  no artifact can be shown — the phase adds a deterministic renderer that the model's
  program never gains access to, plus a bootstrap Monte Carlo that records its seed),
  `phase-19-self-verification.md` (the ledger's claim classes cover commands only —
  the phase adds artifact checks, a data-driven change-review rule table and two claim
  classes), and `phase-20-measuring-all-of-it.md` (the generated capability statement
  covers seven code shapes and omits every new class — the phase registers all classes
  and publishes the unmeasured ones as unmeasured, with the eval step added inside the
  existing `test-evals.js`). The index gains the phase rows, the round-2 ordering
  rules, the measured six-gap ledger (§1.2), a supersede note on §2, and the
  ADR-H115…H125 assignments. Measured baseline re-established this session on the
  untouched tree: `npm run check:all` → `ALL GATES PASSED` (vitest 175 files / 1 995
  tests; pytest 2 278 passed). No runtime file was changed by this entry; the phase
  folders are proposals with no code behind them yet.
  docs updated: `harness/roadmap/README.md`, `harness/roadmap/phase-13…20`,
  `harness/roadmap/NAVIGATION` row 62 (trigger table), this file

- **ChatBot landing text is now opt-in (off by default).** The giant wordmark
  previously shipped ON (`DEFAULT_BACKGROUND.text = 'ECLIPSE AGENT'`), so every
  new user got text painted over their landing. Added a `textEnabled` boolean to
  `BackgroundPrefs` (`src/lib/backgrounds.ts`) defaulting **false**;
  `normalizeBackgroundPrefs` sets it true only when `textEnabled === true`, so
  the flag stays off for absent/junk input. `ChatWordmark`
  (`src/components/chat/chat-wordmark.tsx`) returns null unless the flag is on,
  and the Background panel (`src/components/screens/background-settings.tsx`)
  gained a `Landing text` Toggle (reusing the existing switch recipe) that
  reveals the Text/Font/Align/Size controls only when enabled. The authored
  `text` is retained while off, so toggling on restores it without retyping.
  Wallpaper (`mode: 'image'`, Eclipse I) is unchanged and still the default.
  docs updated: `docs/ARCHITECTURE.md`, this file; test:
  `src/lib/backgrounds.test.ts`

- **Main content panel is now a rounded floating card.** The right-hand content
  panel in `stock-chat.tsx` was a full-bleed rectangle flush against the square
  sidebar, so the top-left corner where they met was hard. It is now inset on
  desktop (`md:m-2`), gently rounded (`md:rounded-xl`) and bordered, so it reads
  as a card beside the sidebar and the shell/pattern shows through the corner
  notches. It stays TRANSPARENT on the chat tab so the Aurora glow and page
  pattern behind it are not hidden; non-chat tabs keep their existing frosted
  `glass-card` fill. Mobile keeps the full-bleed panel (sidebar is a drawer
  there). Sidebar unchanged.
  no doc change — presentational corner treatment, no architecture/contract/
  setup change (the content-panel host is already described in
  `docs/ARCHITECTURE.md` §Presentation).

## 2026-10-01

- **Fix the site-wide frosted-glass regression: `theme-glass-active` shipped with
  only `-webkit-backdrop-filter`.** `globals.css` wrote both `backdrop-filter`
  and `-webkit-backdrop-filter` on the token-driven glass rules; Next's
  lightningcss minifier collapses such a pair down to the `-webkit-` form alone,
  and modern Chrome no longer supports `-webkit-backdrop-filter`
  (`CSS.supports('-webkit-backdrop-filter')` is false). Because that rule also
  carries `!important`, the lower-specificity per-tier `.glass-card` rule could
  not win — so whenever the theme had been customized (which adds
  `theme-glass-active` to `<html>`), EVERY glass surface lost its blur and the
  background showed through sharply. Removed the `-webkit-` declarations in both
  the active and off blocks; the compiled CSS now emits the standard property (and
  lightningcss re-adds the needed suffix itself). docs updated:
  `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.

- **Restore the floating Assistant, give it a robot icon, and fix its frost.**
  The app-wide `ChatDock` assistant was never removed (still mounted at
  `stock-chat.tsx:1117`), but the minimized pill restored its persisted position
  (`be_chat_dock_pill_pos_v1`) without clamping it to the current viewport, so a
  pill saved on a larger window / second monitor came back fully off-screen and
  read as "gone". The clamp effect now also runs once on mount (deferred a frame)
  and returns the same state reference when nothing moved so it cannot loop. Its
  `Sparkles` glyph is replaced with `Bot` (robot) in the pill, transcript header
  and provider pill, and the pill/transcript/composer backgrounds switch from
  `.glass-card-strong` (tint 0.85 — above the frosted threshold, so the blur was
  invisible) to `.glass-card` (tint 0.55 + blur 18) so the frost actually renders.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.

- **Tighten the Command Center gaps and fix adding widgets to an emptied
  layout.** Two independent issues. (1) Density: added a `dense` prop to
  `CustomizableWorkspace`/`WorkspaceCanvas` (gutters only — inter-zone
  `gap-4→gap-1.5`, section stack `gap-3→gap-1.5`, column/card gaps
  `gap-2.5→gap-1.5`, section padding `p-1→p-0.5`, header/edit-bar margins
  `mb-3→mb-2`) and passed it from `DashboardScreen`; also cut the outer wrapper
  in `stock-chat.tsx` from `px-4 md:px-8 py-8` to `px-2 md:px-4 py-3`. Fund
  workspaces keep the original spacing. (2) Empty-centre add: after deleting
  every centre widget while the Watchlist/Market rails remained, `pruneLayout`
  left only rail sections so `mainSections` was empty, `computeTarget` returned
  `null`, and both drag-drop and library adds silently no-op'd. The canvas now
  renders an `EmptyMainZone` placeholder (`data-emptyzone`) that resolves to
  `columnId:'__newmain'`, backed by a new `ops.addWidgetToNewSection` that always
  creates a `main` section. Extracted the drop chrome into
  `src/lib/workspace/workspace-chrome.tsx` to keep `workspace-canvas.tsx` within
  its size budget. Added regression tests in `workspace.test.ts`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.

- **Fix the gitignore guard so it no longer requires `jdds.db` on disk.** The
  guard's own intent is "untracked, not deleted", but it asserted
  `existsSync(jdds.db)` — which fails on a fresh CI checkout, where the
  gitignored runtime vault is (correctly) absent. It now proves the real property:
  `jdds.db` is git-ignored AND not tracked (`git ls-files --error-unmatch`). This
  unblocks the root `.github/workflows/ci.yml` gate, which mirrors check-all.js.
  No doc change — test-only; the runtime and the DB posture are unchanged.

- **Surface closure follow-up — client-safe browser clients for the code and jobs
  surfaces.** Restarting the dev server revealed why the mounted screens had never
  worked: `jobs-screen.tsx` and the code panels (client components) imported the
  server-only `jobs-client.ts`/`code-client.ts`, which pull `python-runtime.ts`
  (`child_process`, `fs`) into the browser bundle, so `/` returned 500 with
  `Module not found: Can't resolve 'child_process'`. New client-safe
  `src/lib/harness/code-browser.ts` and `src/lib/harness/jobs-browser.ts` (fetch the
  existing `/api/code/**` and `/api/jobs/**` routes; type-only re-export of the wire
  types) follow the existing `skills-browser.ts`/`eclipse-memory-browser.ts` pattern.
  All eleven client components now import them; the server clients remain
  server-only. Verified: `GET /` and the four proxy routes return 200; no
  module-not-found errors remain.
  docs updated: `docs/harness/roadmap/progress/surface-closure-progress.md`,
  `docs/CHANGELOG.md`.

- **Front-door surface closure — mount the code and jobs surfaces.** The Python
  runtime for the code capability, jobs and the Phase-12 eval was complete and its
  gates green, but several finished UI surfaces existed as files nothing imported,
  so no user could reach them. New `src/components/screens/code/code-screen.tsx`
  (a thin container wiring the EXISTING Phase-5 panels to the existing
  `code-client` — no agentic logic) and the existing `JobsScreen` are now mounted
  from the shell: AppTab `code`/`jobs` in the new single source `src/lib/app-tabs.ts`
  (both `sidebar.tsx` and `search/types.ts` now re-export it, closing a drift),
  dynamic imports + keep-alive blocks in `stock-chat.tsx`, sidebar sections in
  `src/lib/sidebar/config.ts`, palette rows in `src/lib/search/registry.ts`, and the
  `nav.code`/`nav.jobs` (+ container) i18n keys with the `code`/`calendar` icon
  names. The two stale `status: In progress` progress logs are flipped to Done with
  an appended closure note; `docs/NAVIGATION.md` rows 65/70 are corrected. No Python
  runtime behaviour changed; the frozen four are byte-unchanged.
  docs updated: `docs/NAVIGATION.md`, `docs/CHANGELOG.md`,
  `docs/harness/roadmap/progress/phase-11-progress.md`,
  `docs/harness/roadmap/progress/phase-12-progress.md`,
  `docs/harness/roadmap/progress/surface-closure-progress.md`.

- **Eclipse-as-a-Harness Phase 12 — evaluation harness, safety cases and the standing gate.**
  Extends `python/harness/code/eval/` with a task + safety evaluation beside the
  Phase-4 verification eval, additively (the verification eval keeps its name/API):
  `dataset_tasks_v1.json` (seven labelled fixtures by difficulty, including a
  refusal case graded in the OPPOSITE direction), `safety_cases.py` (eleven
  adversarial cases as data), `tasks.py`/`safety.py`/`statement.py` (runners +
  the generated capability statement). A deterministic floor — never a blended
  score — gates `falseVerifiedRate == 0.0`, `refusalCorrectness == 1.0`,
  `refusalRecordedRate == 1.0`, `kitAcceptanceRate == 1.0` and an exact dataset
  checksum; `taskSuccessRate` is measured and printed, not a gate. The code eval
  is added inside `scripts/test-evals.js` (which `scripts/check-all.js` already
  runs), so the one honest release gate gains no step and the frozen files stay
  byte-unchanged. `docs/harness/capability-statement.md` is generated from the
  dataset + report (a byte-compare test proves it cannot drift); every cell is a
  `capability.*` i18n key. Tests `test_code_eval.py`/`test_code_eval_safety.py`;
  the injected-regression proof asserts the gate FAILS, then reverts. ADR-H114.
  docs updated: `docs/harness/decisions.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`, `docs/harness/capability-statement.md`,
  `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-12-evaluation-gate.md`,
  `docs/harness/roadmap/progress/phase-12-progress.md`.

- **Eclipse-as-a-Harness Phase 11 — surface and scale.**
  Delivery grows from two adapters to three behind the Phase-6 `DeliveryAdapter`
  protocol: new `python/harness/jobs/delivery.py` `messaging` adapter (a template
  KEY + params, never a composed sentence) and the `artifact` file contract
  (`.black-eclipse/artifacts/<runId>/{report.md,receipt.json,meta.json}`, path
  derived from the run id and confined by policy). Every configured target records
  its OWN `DeliveryOutcome` on the run row — no rolled-up boolean; a delivery
  failure never fails the run. Additive `JobDeliveryTarget` + `destination`/`targets`
  and a `scopeId` FILTER label on jobs, code tasks, artifacts and code workspaces
  (`test_surface_tenancy_isolation.py` mirrors the older tenancy boundary; a
  body-supplied scope never authorizes). New `python/harness/code/backends.py`
  `SandboxBackend` with `local`/`container`/`remote` declarations, the honest-failure
  rule absolute (an unavailable backend refuses with `SANDBOX_UNAVAILABLE`, never
  degrades). `scripts/doctor.js` gains four honest probes; three runbooks added
  (`runbook-add-a-job.md`, `runbook-add-a-kit.md`, `runbook-failed-code-task.md`).
  Front door `src/lib/harness/jobs-client.ts` + `src/app/api/jobs/**/artifact` +
  `src/lib/alerts/notifier.ts` (`renderJobMessage`); i18n `jobs.delivery.*` and the
  delivery `refusal.*` keys. Tests `test_delivery_adapters.py`/
  `test_surface_tenancy_isolation.py`/`test_sandbox_backends.py`. ADR-H113.
  docs updated: `docs/harness/decisions.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`, `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-11-surface-and-scale.md`,
  `docs/harness/roadmap/progress/phase-11-progress.md`,
  `docs/harness/runbook-{add-a-job,add-a-kit,failed-code-task}.md`.

- **Eclipse-as-a-Harness Phase 10 — self-improvement v2 (code as well as skills).**
  New `python/harness/code/evolution.py` (a recurrence bridge that consumes the
  existing `LearningRecurrence` counter, `propose_ops` with the FROZEN set and the
  `skills/patches.py` FORBIDDEN_FIELDS, a worktree evaluation recorded through the
  Phase-4 ledger, a `skills/versioning.py` subject adapter, and honest
  `archive_metrics` that render `UNKNOWN` never `0`) + `code/evolution_store.py`
  (additive `EvolutionCandidate`/`EvolutionAttempt`, nullable cost columns) +
  `code/evolution_service.py` (evaluate/activate/rollback). New
  `routers/evolution.py` (every route `require_operator`, reads included) +
  `include_router`; the existing learning journey is extended with
  `evolution_candidate`/`evolution_attempt` nodes. Front door
  `src/lib/harness/evolution-client.ts` + `src/app/api/evolution/**`; i18n
  `evolution.*`. `skills/versioning.py` and `skills/patches.py` are byte-unchanged.
  Tests `test_evolution_bridge.py`/`test_evolution_persistence.py`/
  `test_self_improvement_freeze.py`/`test_self_improvement_e2e.py`. ADR-H112.
  docs updated: `docs/harness/decisions.md`, `docs/NAVIGATION.md`,
  `docs/harness/roadmap/README.md`, `docs/harness/roadmap/phase-10-self-improvement.md`,
  `docs/harness/roadmap/progress/phase-10-progress.md`.

- **Eclipse-as-a-Harness Phase 9 — finance application scaffold kits.**
  New `python/harness/code/kits/` (a validated kit contract + loader that refuses
  a kit with no acceptance test or an undeclared output) and eight kits:
  `market_data_adapter`, `mcp_server`, `ratio_calculator`, `backtest_strategy`,
  `chart_indicator`, `portfolio_module`, `data_ingestion_pipeline`,
  `research_workflow`. The `scaffold_kit` tool (handler in the new
  `scaffold_tools.py`, registered in `code/tools.py` under its size ceiling, added
  to both agent allowlists and to `policy.WRITE_TOOLS`) renders a kit into the
  task's disposable workspace, runs its checks through the Phase 3 broker, and
  records them in the Phase 4 ledger; a failed check keeps the scaffold
  (`CHECK_FAILED`). The anti-fabrication generation rule is enforced by the
  templates (UNAVAILABLE, not a default; in-sample labelled; idempotent imports).
  Eight draft skill wrappers (`system.*`, all inert). i18n `kit.*`; tests
  `test_kits_{contract,scaffold,unavailability,skill_wrappers}.py` + one
  `test_kit_<id>.py` per kit. ADR-H111. docs updated:
  `docs/harness/decisions.md`, `docs/NAVIGATION.md`,
  `docs/harness/roadmap/README.md`, `docs/harness/roadmap/phase-09-scaffold-kits.md`,
  `docs/harness/roadmap/progress/phase-09-progress.md`.

- **Eclipse-as-a-Harness Phase 8 — analysis sandbox (computing, not just retrieving).**
  New `python/harness/code/execution.py` (bounded, reproducible analysis on the
  Phase 3 sandbox: AST import allowlist — never eval/exec — source/input/interpreter/
  package digests, artifact collection with SHA-256 identity, and the `Provenance`
  contract). The provenance rule is enforced in code: every execution output is
  `kind="computed"`, a computed number with no provenance renders `UNAVAILABLE`
  (fail-closed), and a computed number can never enter a research claim (the only
  legal path is `research/calculations.py`; the receipt is untouched). The
  `analysis_run` tool (handler in the new `analysis_tools.py`, registered in
  `code/tools.py` under its size ceiling) is OFF per run
  (`RunRequest.analysisEnabled`, default False). New `code/recipes.py` ships seven
  tested recipes, each failing honestly (asks) on a missing input. Additive
  `AnalysisRecord` table; front door `src/lib/harness/analysis-types.ts` +
  `src/components/chat/computed-result-panel.tsx`; i18n `analysis.*`; tests
  `test_analysis_{execution,provenance,recipes,tool}.py` + `analysis-types.test.ts`.
  ADR-H110. docs updated: `docs/harness/decisions.md`, `docs/NAVIGATION.md`,
  `docs/harness/roadmap/README.md`, `docs/harness/roadmap/phase-08-analysis-sandbox.md`,
  `docs/harness/roadmap/progress/phase-08-progress.md`.

- **Eclipse-as-a-Harness Phase 7 — delegation and child runs.**
  New `python/harness/delegation.py` (`DelegationChild`/`DelegationRequest`/`ChildOutcome`/
  `DelegationResult`, `VerifiableHandle`, `child_actor`, `narrow_tools`,
  `partition_claims`, `aggregate`, `run_delegation`; `MAX_CHILDREN=4`, `MAX_DEPTH=2`,
  bounded concurrency + per-child timeout + token budget). A child IS a normal run
  (`execute_run` with `parentRunId`); the module owns only the budget, the
  narrowing and the aggregation. `child_actor` intersects the parent's grants and
  NEVER inherits `operator` (the laundering guard); a wider workspace and an
  unheld tool are refused. Aggregation admits a child's check-claim only with a
  re-checkable `check_record_id` against the Phase 4 ledger; unbacked claims go to
  `droppedClaims` and render unconfirmed. The `delegate` tool (handler in the new
  `delegation_tools.py`, registered in `code/tools.py` under its size ceiling) is
  added to both the finance and code agent allowlists, with prompt guidance on
  when (and when not) to delegate. Additive, old-row-safe `HarnessRun.delegation`
  blob + `delegation.*` events on the existing emitter. Tests
  `test_delegation.py`/`_narrowing`/`_aggregation`/`_tool.py`; plain-language gate
  extended. ADR-H109. docs updated: `docs/harness/decisions.md`,
  `docs/NAVIGATION.md`, `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-07-delegation.md`,
  `docs/harness/roadmap/progress/phase-07-progress.md`.

- **Eclipse-as-a-Harness Phase 5 — coding agent, autonomy profiles, approvals.**
  New `code-agent` preset (`agents.py`) whose allowlist is the REAL Phase 1–3
  code tools and NO finance tool, and which does not set `allowMcpTools`;
  `CODE_AGENT_SYSTEM_PROMPT` in `prompts.py`. Autonomy is structural:
  `code/policy.allowed_tools(autonomy, declared)` is the ONE place a
  write/external tool is removed, and `graph.effective_allowlist` calls it before
  the model sees any schema (a code run with no autonomy resolves to `plan_only`).
  `RunRequest.workspaceId` + `RunResult.autonomy`/`workspaceId` added. The
  approval store is GENERALIZED: `mcp/approvals.py` gains `claim_guarded` (the ONE
  single-use primitive), `request_kind`/`consume_kind`/`list_kind`, and additive
  `kind`/`workspaceId` columns; `code/actions.py` binds an external action to the
  exact action + workspace; four external-action tools (`code_commit`,
  `code_push`, `code_open_pr`, `code_deploy`) are registered effectful and
  single-use approved. `code/tasks.py` is a CONSUMER of `run_lineage.py`
  (task.created/plan.accepted/patch.applied/command.executed/cancelled/discarded).
  New `routers/code.py` (`/code/*`, operator-gated) + two lines in `main.py`;
  front door `src/lib/harness/code-client.ts` task/approval functions +
  `src/app/api/code/**` proxies + `src/components/screens/code/**`; i18n
  `code.task.*`/`code.approvals.*` + extended jargon gate. ADR-H107 appended
  (H103/H104/H106 were taken concurrently). Baseline frozen in
  `docs/harness/roadmap/progress/phase-05-progress.md`. docs updated:
  `docs/harness/decisions.md`, `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-05-coding-agent.md`, `docs/NAVIGATION.md`

- **Prompt follow-up — navigator prompt correctness + guard coverage.** Fixed
  the Repository Navigator prompt (`CODE_NAVIGATOR_SYSTEM_PROMPT`) which
  contradicted its own allowlist: it claimed exactly five read tools and that it
  "cannot run any command" while `CODE_NAVIGATOR.tools` has nine (including
  `command_run`, `workspace_patch_apply`, `workspace_diff`,
  `workspace_revert`). `## What you can do` now names the surface by group and
  defers to the bound schemas; `## What you cannot do` states the true narrower
  set (no arbitrary shell/program, no install, no network). Removed the phantom
  `run instructions` authority rank from `# Inputs and authority` (never
  populated by any caller) and its `run_instructions` prompt segment
  (`python/harness/prompt_segments.py`). Removed the hardcoded surface
  enumeration from the identity sentence and disambiguated "valuation and
  modelling". Deleted two redundant restatements (the duplicate citation line
  and the duplicate bound-schemas sentence). Added generalised guard tests
  across both presets in `python/tests/test_memory_tools.py` +
  `test_prompt_segments.py`. Prompt 17,443 → 17,294 chars (~4,324 est. tokens),
  under the 17,500 ceiling. docs updated: `docs/harness/decisions.md`
  (ADR-H106), `docs/harness/architecture.md`,
  `docs/harness/prompt-followup-progress.md`.

- **Eclipse-as-a-Harness Phase 4 — verify-and-repair trust spine.** New
  `python/harness/code/verify.py` (the per-run `VerificationLedger`; a
  deterministic, negation-aware sentence-level claim parser; `enforce_answer`
  marking/stripping an unbacked pass-claim with `UNVERIFIED`) and
  `python/harness/code/repair.py` (the bounded plan→edit→check→repair loop with a
  `RepairBudget` checked before every edit; `refused` for an unavailable check;
  `no_checks` when none). `execute_run` constructs/rehydrates the ledger, records
  every command execution as proof, enforces the final answer, and persists
  `HarnessRun.codeVerification` (DDL in `code/store.py`; `persistence.py` stayed
  within its ratchet). Six deterministic code categories added to
  `eclipse_memory/mistakes.py`. New `python/harness/code/eval/` runnable as
  `python -m harness.code.eval` (falseVerifiedRate floor 0) and wired into
  `scripts/test-evals.js`. Front door `src/lib/harness/code-client.ts` +
  `code-verification-panel.tsx` ("Proof it works"); i18n `code.proof.*` keys +
  extended jargon gate. ADR-H105 appended (ADR-H103/H104 were taken concurrently).
  Baseline frozen in `docs/harness/roadmap/progress/phase-04-progress.md`.
  docs updated: `docs/harness/decisions.md`, `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-04-verify-and-repair.md`, `docs/NAVIGATION.md`

- **Eclipse Agent Prompt v2 — finance-harness completion.** Added the
  finance-harness contract to `ECLIPSE_AGENT_SYSTEM_PROMPT`: `# Market data
  semantics` (session state, price/period basis, corporate actions,
  point-in-time vs restated, FX, staleness), `# Inputs and authority` (7-rank
  precedence table + attached-document rule with `[attached: <name>]`),
  `# Answer contract` (answer-first shape, `source: as-of` citations, numeric
  conventions, a contrastive worked example) and `## Runtime awareness`
  (bounded steps/timeout, stop rule, truncation, no redundant retrieval).
  Rewrote the identity preamble so its action surface is exactly the bound tool
  allowlist while the domain list stays competence-only. Removed the declared
  but never-populated `session_summary` prompt segment
  (`python/harness/prompt_segments.py`). Paid for the growth by tightening
  `# Investment Analysis`, `## MCP tools`, `## Tool calls`, the identity preamble
  and `# Tool-use enforcement`, retaining every rule. Prompt 15,302 → 17,443
  chars (~3,826 → ~4,361 est. tokens), under the 17,500 ceiling. Guard tests
  added in `python/tests/test_memory_tools.py` and
  `python/tests/test_prompt_segments.py`. docs updated:
  `docs/harness/decisions.md` (ADR-H104), `docs/harness/architecture.md`,
  `docs/harness/prompt-v2-finance-harness-progress.md`.

- **Harden the Eclipse Agent system prompt (reduction + accuracy).** Added a
  run-scoped `runtime_context` `PromptSegment` (`prompt_segments.runtime_context_block`)
  carrying the run's real date/time/UTC offset, wired in `graph.py` where settings
  are resolved and rendered as its own per-run `SystemMessage` after the
  byte-stable head (own content hash; excluded from `STATIC_SEGMENTS`). Fixed the
  cache key: `prompt_cache_key` now includes the content hash of the reusable
  segments, so a prompt edit changes the key (`runtime_context`/`run_instructions`/
  `user_message` stay excluded); split `STATIC_SEGMENTS` from a new
  `RUN_FROZEN_SEGMENTS` so run-frozen blocks no longer inflate
  `reusable_total_tokens`. Deduplicated the execution-discipline blocks to one
  statement per rule (39.7% of prior size) with finance-native examples, compacted
  the 52-bullet identity preamble to a bounded role statement, made the bound tool
  schemas authoritative (removed the dead `_TOOLS_LIST_SENTENCE` replacement), and
  added prompt guard tests. Prompt 18,826 → 15,302 chars (~4,707 → 3,826 est.
  tokens). Removed the now-redundant `'What time is it?' -> date` example.
  docs updated: `docs/harness/decisions.md` (ADR-H103),
  `docs/harness/architecture.md`, `docs/NAVIGATION.md`.

- **Eclipse-as-a-Harness Phase 3 — sandboxed command broker.** New
  `python/harness/code/commands.py` (the closed command-class TABLE: ArgSpec
  validation, a closed `EXECUTABLES` map, the vendored interpreter named once, a
  CLOSED `git_read` subcommand set, `dependency_install` off by default with
  `--ignore-scripts`, `CommandUnavailable`) and `python/harness/code/sandbox.py`
  (the ONE execution primitive: `RunSpec`, `build_env` scrubbed to
  `SECRET_ENV_ALLOWLIST`, `select_backend` with a Windows Job Object
  `KILL_ON_JOB_CLOSE` and a POSIX process group, wall-clock timeout + process-tree
  kill, honest output cap, cancellation, and a `SandboxUnavailable` refusal that
  never executes unsandboxed). `command_run` joins the registry
  (`permission="write"`, `effect="external_action"`), authorized by the run's
  autonomy profile; every attempt (including every refusal) is recorded as a
  `HarnessCommandExecution` row (in `code/store.py`) and a `command.*` event.
  Plain refusal copy with a recovery step added as data in `commands.py` and
  `src/lib/i18n`; `test_plain_language.py` + the jargon gate extended. ADR-H102
  appended (the series ended at H101). Baseline frozen in
  `docs/harness/roadmap/progress/phase-03-progress.md` (vitest 169/1966; pytest
  1841→1883; eval gates pass). docs updated: `docs/harness/decisions.md`,
  `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-03-command-broker.md`, `docs/NAVIGATION.md`

- **Eclipse-as-a-Harness Phase 2 — isolated worktree patch authoring.** New
  `python/harness/code/worktree.py` (allocate a disposable copy at
  `<root>/.black-eclipse/code-workspaces/<id>` via `git worktree add --detach`,
  bounded snapshot fallback reported honestly, `release` refusing anything outside
  the scratch root and idempotent, `diff`, `sweep_expired`), `code/patch.py`
  (closed op set create/replace/delete/move, structural validation before any
  write, content-hash base refusal, unique-span `replace`, ATOMIC — a refusal
  applies nothing, before/after hashes, `revert` newest-first), and
  `code/store.py` (the `CodeWorkspace` table bound to the ONE `AgentMemoryStore`
  connection; `persistence.py` untouched). Three tools added to
  `register_code_tools` — `workspace_patch_apply` (write), `workspace_diff`
  (read), `workspace_revert` (write) — authorized by the run's autonomy profile
  via a code authorizer composed into the single effect authorizer; `RunRequest`
  gains an optional `autonomy`; `code-navigator` gains the three tools.
  `sweep_expired` wired into startup maintenance. Front-door i18n `task.authoring.*`
  progress/result lines + authoring `refusal.*` codes + `plain-language.test.ts`
  extended; human tool labels added. ADR-H101 appended (the series ended at H100).
  Baseline frozen in `docs/harness/roadmap/progress/phase-02-progress.md` (vitest
  169/1966; pytest 1808→1839; eval gates pass). docs updated:
  `docs/harness/decisions.md`, `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-02-worktree-patching.md`, `docs/NAVIGATION.md`

- **Eclipse-as-a-Harness Phase 1 — read-only repository navigator.** Five
  read-only tools on the EXISTING `ToolRegistry` (`workspace_status`,
  `workspace_list`, `workspace_search`, `workspace_read`, `workspace_docs`; all
  `permission="read"`, `risk="low"`), registered once from `service.py`. New
  `python/harness/code/workspace.py` owns resolution + the ONE confinement seam
  (`confine` delegates to Phase 0 `policy.resolve_within`) + the fixed
  argument-free `git` probe + a bounded ignore-aware walker; `code/tools.py` owns
  the handlers and `emit_code_event`. `policy.resolve_within` now returns
  DISTINCT codes per escape vector (`PATH_TRAVERSAL` / `PATH_OUTSIDE_WORKSPACE` /
  `SYMLINK_ESCAPE`, plus `PROTECTED_PATH` / `IGNORED_PATH`); `jdds.db` reports
  `PROTECTED_PATH`, never `BINARY_FILE`. Reads are line-numbered with a
  continuation offset, refuse binary, and redact secret-shaped lines to
  `«redacted»` via `session_index.redact_span` (one pattern set). New
  `code-navigator` agent preset (only the five tools, no MCP); `RunRequest.workspace`
  (optional, additive; can only confirm the server root) wired through
  `ToolContext.workspace`; front-door `validateWorkspaceRef` + types; i18n
  `task.*`/`refusal.*` keys + a code→sentence map and the `plain-language.test.ts`
  jargon gate. ADR-H100 appended (the series ended at H99, not H92). Baseline
  frozen in `docs/harness/roadmap/progress/phase-01-progress.md` (vitest 168/1962;
  pytest 1777→1808; eval gates pass). docs updated: `docs/harness/decisions.md`,
  `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-01-repository-navigator.md`, `docs/NAVIGATION.md`

- **Eclipse-as-a-Harness Phase 0 — code capability becomes a tested policy
  decision (ships NO tools).** New `python/harness/code/policy.py` is the single
  policy authority: `AUTONOMY_PROFILES`, `PROTECTED_PATHS`, `IGNORED_DIRS`/
  `IGNORED_GLOBS`, `COMMAND_CLASSES`, `NETWORK_DEFAULT`, `SECRET_ENV_ALLOWLIST`,
  `PLAIN_LANGUAGE_DENYLIST`, `WorkspaceBinding`/`PolicyDecision`, and
  `is_protected`/`is_ignored`/`resolve_within` (real-path compare, refuses
  traversal, absolute-outside and link escapes)/`decide_write`/`decide_command`/
  `code_grants`. `skills/manifest.py` gains the seven code nouns and
  `CODE_PERMISSIONS`, and narrows `FORBIDDEN_PERMISSIONS` to
  trade/broker/production. `skills/permissions.py` `Actor` gains
  `workspace_id`/`autonomy`; `granted()` unions `code_grants` only when both are
  set (unknown profile → nothing, fail-closed), and a caller grant can no longer
  smuggle a code verb. New `python/tests/test_code_policy.py` (33 tests, incl.
  path-escape and command refusals and the plain-language seed gate). ADR-H97/
  H98/H99 appended (the series already ended at H96, not H92). Baseline gate
  frozen in `docs/harness/roadmap/progress/phase-00-progress.md` (vitest 168
  files / 1962 tests; pytest 1744; eval gates all pass). docs updated:
  `docs/harness/decisions.md`, `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-00-policy-and-baseline.md`, `docs/NAVIGATION.md`

- **ChatBot landing wordmark — user-authored giant text + font.** Settings ›
  General › Background gained a "Landing text" card: a text field, a curated
  display-font list (`WORDMARK_FONT_OPTIONS`), alignment, size (vw), strength and
  vertical position. A new presentational `ChatWordmark`
  (`src/components/chat/chat-wordmark.tsx`) paints the text behind the ChatBot
  landing only, above the wallpaper and below the transcript/composer
  (`z-0`/`pointer-events:none`); the default is a Didone-stack "ECLIPSE AGENT"
  wordmark. Six new `BackgroundPrefs` fields flow through the existing
  `backgrounds.ts` store/prefs (localStorage `be_background_v1`), so it applies
  instantly and persists. Tests cover normalization/clamping.
  no doc change — UI-only presentation preference; no architecture, contract or
  setup change.

- **Eclipse-as-a-Harness Phase 6 — harness-owned jobs and event triggers.**
  New `python/harness/jobs/` package: `model.py` (`JobDefinition`/`JobTarget`/
  `JobDelivery`, `enabled` defaults FALSE per ADR-H39), `store.py` (the
  `HarnessJob`/`HarnessJobRun` tables on the ONE `agent-memory.db` connection),
  `cron.py` (a stdlib-only 5-field matcher that refuses 6-field/`@macro`/name
  aliases), `guardrails.py` (save-time permission binding, workspace-required code
  jobs, operator-gated `approve_external`, `policy.resolve_within` watch-path
  confinement, skill-version pinning, unknown-adapter refusal), `scheduler.py`
  (`JobScheduler` — one lifespan task beside `start_mcp()`, injected clock, no
  overlap, bounded in-flight runs, `max_runtime_s` cooperative cancel, once-only
  missed-run reconciliation recorded with `missed=1`, the breaker reused from
  `mcp/circuit.py`), `triggers.py` (SHA-256 webhook tokens shown once; a bounded
  file-watch signature), `delivery.py` (`in_app` on the existing SSE bus +
  `artifact` reports), and `templates.py` (the seven disabled finance templates).
  A job run IS a normal `HarnessRun`. `routers/jobs.py` carries every route behind
  `require_operator` (reads included, ADR-H48) except the hashed-token webhook
  trigger; `main.py` grows by an import + `include_router` + lifespan
  `start_jobs`/`stop_jobs`. Front door `src/lib/harness/jobs-client.ts` +
  `src/app/api/jobs/**` + `src/components/screens/jobs/**`, i18n `jobs.*`. The
  three TS schedulers are byte-unchanged. ADR-H108. docs updated:
  `docs/harness/decisions.md`, `docs/NAVIGATION.md`,
  `docs/harness/roadmap/README.md`, `docs/harness/roadmap/phase-06-jobs-and-triggers.md`,
  `docs/harness/roadmap/progress/phase-06-progress.md`.

## 2026-09-30

- **Harness closeout Phases 8–9 — eval harness, rollout, docs.** `scripts/test-evals.js`
  runs four new OFFLINE gates: the capability-matrix gate
  (`scripts/eval-capability-matrix.ts`) and the Python route_health / workflow /
  resume gates (`python/harness/eval_gates/`), each failing non-zero on a floor
  violation. The workflow path and the route-probe schedule ship behind flags
  (`HARNESS_WORKFLOWS_ENABLED` / `HARNESS_ROUTE_PROBE_ENABLED`), both default OFF;
  a run with no `workflowId` is unchanged. Architecture, NAVIGATION and ADR-H93…H96
  documented. docs updated: `docs/harness/architecture.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md`, `docs/harness/harness-closeout-progress.md`

- **Harness closeout Phase 7 — observability: one source of truth.** Verified the
  retrieval planner's health index reads the same SourceHealth ledger as
  `get_source_health`, with a test asserting equal verdicts. `explain_run` now
  includes the workflow step tree, run lineage, and the resume point; workflow
  steps emit per-step events on the existing bus; `run-explanation-panel.tsx`
  renders them. docs updated: `docs/harness/harness-closeout-progress.md`

- **Harness closeout Phase 6 — permissions, sandboxing, egress.** `ToolDefinition`
  gained `version`/`deprecated`/`replacement`; the registry warns once per run
  when a deprecated tool is called (naming its replacement) and still executes it.
  Confirmed and tested the four egress guards (private-address, non-https hop,
  DNS-rebinding, over-size document). A sentinel-secret scan runs a real run with a
  sentinel credential and asserts it appears in no persisted row.
  docs updated: `docs/harness/harness-closeout-progress.md`

- **Harness closeout Phase 5 — the composable workflow graph.** New
  `python/harness/workflows/` (model/validate/store/compile) compiles a versioned,
  bounded `Workflow` onto the EXISTING `execute_run` graph — no second loop,
  registry or model adapter. A step's tool scope = agent allowlist ∩ step tools,
  enforced at the `ToolRegistry.execute(allowed=...)` seam (a denied call is a
  structured `TOOL_FORBIDDEN`); approval steps reuse the single-use `ApprovalStore`;
  parallel branches share the run cancel event/cache. Flag-gated
  (`HARNESS_WORKFLOWS_ENABLED`, default OFF); a run with no `workflowId` is
  unchanged. Front door `src/lib/harness/workflows-client.ts` + routes
  `src/app/api/harness/workflows/**`.
  docs updated: `docs/harness/harness-closeout-progress.md`

- **Harness closeout Phases 3–4 — matrix truthfulness + data-route gaps.**
  `buildCapabilityMatrix` now reconciles every axis and represents an impossible
  fact as `matrixInconsistent` (with a reason) instead of smoothing it over; CH/KW/QA
  gained real COVERAGE entries with correct ISO currencies (CHF/KWD/QAR) and the
  market count is asserted at 34; a declared provider-eligibility registry replaces
  an inferred quote route (AE/NG are not-configured and secondary). FX/crypto skip
  the JDdS vault (which holds no such row); statements resolve through the provider
  chain with the vault as a cache (never a vault identity failure); PK is declared
  secondary; thin markets gained symbol-candidate chains.  No jdds.db commit.
  docs updated: `docs/harness/harness-closeout-progress.md`

- **Harness closeout Phase 2 — one authoritative route-health ledger.**
  `sourceHealth()` now returns a compact recorded SUMMARY by default and withholds
  the ~1,200 declared-but-unrun routes (opt-in via `recordedOnly`/`includeDeclared`),
  so `get_source_health` is readable inside the 24k tool bound instead of showing
  only "unknown" rows. `capabilityMatrix()` canonicalises its market key to match;
  a migration folds legacy rows (incl. literal `unknown`) onto canonical keys.
  `SourceHealth` gained `lastSuccessAt`/`lastFailureAt`. A bounded cross-market
  probe records one attempt per (market × capability) into the same ledger, with a
  manual one-shot (`POST /api/harness/route-probe`, `scripts/probe-route-health.ts`)
  and a recurring schedule OFF by default behind `HARNESS_ROUTE_PROBE_ENABLED`.
  The ledger surface moved to `src/lib/harness/health-ledger.ts` to respect the
  size ratchet.
  docs updated: `docs/harness/harness-closeout-progress.md`

- **Harness closeout Phase 1 — run lineage, durable checkpoints, idempotent
  resume.** Each run can now survive a crash: `HarnessRun.parentRunId`/`workflowId`
  record lineage; a new `RunCheckpoint` table stores a bounded per-boundary
  reference (agent step / tool results / terminal), and `ToolExecutionIdempotency`
  makes a resume reuse an already-executed tool result instead of re-running it.
  New routes `POST /runs/{id}/resume` and `GET /runs/{id}/lineage`; a missing
  checkpoint returns `CHECKPOINT_NOT_FOUND` and a terminal run `RESUME_CONFLICT`.
  Persistence moves into a new `python/harness/run_lineage.py` (bound to the ONE
  store connection) so ratcheted `persistence.py` did not grow; per-run context
  helpers were extracted to `python/harness/graph_context.py`.
  docs updated: `docs/harness/harness-closeout-progress.md`

- **Tool-loop integrity Phase 1 — the release gate's one red test was a UTC
  month-rollover time bomb.** `weekly.test.ts`'s `buildMonthlyWrapped` test
  derived its period from `new Date()` while its fixtures were hardcoded to
  2026-09; after 20:00 EDT on Sep 30 (UTC already Oct 1) the prefix resolved to
  `2026-10` and zero rows matched. The test now passes `(year, month)` explicitly
  and asserts the zero-match branch (`trades === 0`, `bestMarket === null`)
  deliberately. A repo-wide sweep found no other live-clock/fixed-fixture test.
  A testing convention was added to `CONTRIBUTING.md`.
  docs updated: `CONTRIBUTING.md`, `docs/harness/tool-loop-integrity-progress.md`

- **Tool-loop integrity Phase 2 — duplicate tool-call suppression is scoped to
  one agent step, not the whole run (ADR-H90).** `seen_calls` now resets per
  `tools_node` invocation, so a legitimate re-issue in a later turn (next page,
  re-poll, retry) executes instead of being refused with a stale "use the earlier
  result". Intra-turn refusal is unchanged. Regression tests cover both
  directions; the retrieval cache still dedupes fetches per run.
  docs updated: `docs/harness/decisions.md` (ADR-H90),
  `docs/harness/architecture.md`, `docs/NAVIGATION.md`

- **Tool-loop integrity Phase 3 — native tool-result text is bounded at the one
  execution seam (ADR-H91).** `ToolRegistry.execute` trims a model-facing text
  result to `MAX_TOOL_RESULT_CHARS = 24_000` with a non-JSON marker and
  `truncated`/`shown_chars`/`total_chars` fields; the graph emits `tool.truncated`.
  Byte-identical under the bound; `ToolResult.data` is never bounded. Blast
  radius: only `session_open` can exceed it (~25.6k chars max); the constant was
  not raised to hide it. Model-streaming helpers were extracted to
  `model_stream.py` to keep `graph.py` under its ratchet.
  docs updated: `docs/harness/decisions.md` (ADR-H91),
  `docs/harness/architecture.md`, `docs/NAVIGATION.md`

- **Tool-loop integrity Phase 4 — an effectful-tool approval is single-use
  (ADR-H92).** `ApprovalStore.consume` atomically claims an approved, unexpired
  approval (guarded `UPDATE` + rowcount) and moves it to a terminal `consumed`
  state with `usedAt`; a second identical call is refused and creates a fresh
  PENDING request. The double authorization seam (registry + manager re-assert) is
  resolved via a per-call-scope digest marker on `ToolContext`. `consumed`/`usedAt`
  ride the round-trip through `MCPApprovalView` and the approvals UI (extracted to
  `mcp/approvals-panel.tsx` to keep `mcp-settings.tsx` under its ratchet).
  docs updated: `docs/harness/decisions.md` (ADR-H92),
  `docs/harness/architecture.md`, `docs/NAVIGATION.md`

- **ChatBot: new Ctrl+N (Cmd+N on Mac) shortcut for a new chat page.**
  The chat tab's "New chat" page shortcut was `Shift+N`, colliding with the
  `Shift+N` "new layout"/new-item convention used across other screens (Command
  Center layouts, trades, alerts). It is now `mod+n` (Ctrl on Windows/Linux, Cmd
  on Mac) so the two never blur. Added `formatShortcutKeys` in `src/lib/keyboard.ts`
  and used it in the keyboard-help dialog so specs like `mod+n` render as
  `Ctrl / Cmd + N` (previously page/sidebar keys showed raw). Tests added for the
  formatter.
  docs updated: `docs/OVERVIEW.md`

- **Background zoom could not go below 100%.** The Zoom control was hard-clamped
  to a 100% minimum in two places — `normalizeBackgroundPrefs` (`backgrounds.ts`)
  and the slider `min` (`background-settings.tsx`) — even though the CSS and
  `resolveBackgroundCss` already support 50%. Lowered the floor to 50% in both, so
  the wallpaper can be shrunk. Test updated plus a sub-100% regression assertion.
  docs updated: `docs/ARCHITECTURE.md`

- **MCP integrity close-out — live supply-chain verdict surfaced; catalog-change
  counters shown; the report's dead `upstreamChecked` flag made real.**
  `SupplyChainChecker` now records the last observation per
  `(ecosystem, package, version)` with a wall-clock `checkedAt`; a read-only
  `observe_command` lets `supply_chain_report` attach `liveVerdict` to a
  configured package and DERIVE `upstreamChecked` from real observations (the
  caller `upstream_checked` parameter is removed — it had no caller and could
  never be true). The route stays offline. The card/lifecycle panel now render
  `lifecycle.catalogChanges`/`lastCatalogChangeAt` beside the existing "catalog
  changed" banner, via a pure `catalogChangeSummary` helper — no event consumer
  was added. `python/tests/test_retrieval_health.py` and the health-aware
  retrieval workstream are adjacent scope (uncommitted, tested green).
  docs updated: `docs/harness/mcp-integrity-progress.md` (Milestone 11),
  `docs/harness/decisions.md` (ADR-H88/H89), `docs/NAVIGATION.md`

- **`memory` tool — save crash on missing/null `confidence` fixed.** `save`
  crashed with `float() argument must be a string or a real number, not
  'NoneType'` when `confidence` was present-but-null (`args.get("confidence",
  0.8)` returns `None` for a JSON `null`). Added `_coerce_confidence`
  (missing/empty/NaN/out-of-range → default 0.8, bounded 0..1) and wrapped the
  authorize+commit call so any malformed input returns a typed `invalid_input`
  refusal instead of an unhandled `TypeError`. The per-turn write-authorization
  gate is untouched (its fail-closed false negative is intentional). Tests added
  for save-without-confidence, save-with-null, and malformed confidence.
  no doc change — bug fix, contract unchanged.

- **Background — Eclipse I is the official first-run wallpaper; added resize controls.** Factored the shipped default into `DEFAULT_BACKGROUND_ID = 'eclipse-1'` (the official background new users get) and marked it with a "Default" badge in the picker. Added image resize controls: **Zoom** (100–300%), **Horizontal** and **Vertical** focal position (0–100%), alongside the existing Fit and Darkening. The wallpaper image moved onto the layer's `::before` so zoom scales only the art (the dim scrim stays full-size), and the resolver now emits `--app-bg-zoom` + a focal `--app-bg-position`. `BackgroundPrefs` gained `scale`/`positionX`/`positionY` (normalized/clamped).
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Sidebar — clicking the ChatBot icon always starts a new chat.** The ChatBot nav item used to just switch to the chat tab, resuming whichever conversation was last active. It now calls `onNewChat()` before switching tabs, so clicking it opens a fresh chat every time; previous conversations remain reachable from the history list above the nav.
  no doc change — bug fix; no architecture, contract, setup, or data-shape change.

- **MCP: no-op `list_changed` no longer emits a "catalog changed" event, and the
  live supply-chain check is now a visible operator setting.** Two honesty/
  reachability gaps in the M4/M6 work. (1) `rediscovery.py` re-ran discovery on
  every inbound `list_changed` and emitted `mcp.catalog.changed` unconditionally.
  A server that announces a change that never materialises (or fires the
  notification gratuitously) therefore produced a stream of misleading "catalog
  changed" signals — the operator would be asked to re-confirm an identical
  catalog. The handler now snapshots `rt.catalog_digest` before the refresh and
  suppresses the event when the digest is unchanged; discovery, the registry
  reconcile and a real digest change all still run and emit. Regression:
  `python/tests/test_mcp_notifications.py::test_a_gratuitous_list_changed_emits_no_catalog_event`
  and a new `list_changed_noop` fixture mode. The `list_changed_all` fixture now
  actually changes its TOOL list too (it only changed resources/prompts), so the
  `tools` event it asserts is no longer a false positive. (2)
  `MCPServerConfig.live_supply_chain_check` defaulted to **true** and did an
  outbound 8s OSV query on every `npx`/`uvx` spawn, but no operator surface
  mentioned it: not in the editor, not in the example config, and absent from the
  TS `MCPServerView`/`MCPServerInput`/`DraftServer` contract — so a save from the
  editor would have DROPPED an operator's explicit `false` and silently
  re-enabled the network call. Added the view/input/draft fields with a
  `!== false` default (absent = the documented default), the round-trip mapping,
  the lifecycle checkbox in `server-editor.tsx`, and the example-config
  documentation. Regression: `mcp-draft.test.ts` "round-trips the live
  supply-chain toggle". Also documented the six manager mixins that the
  `NAVIGATION.md` MCP row did not name (`verify.py`, `execution.py`,
  `lifecycle_mixin.py`, `utilities.py`, `rediscovery.py`, `circuit.py`,
  `supply_chain.py`). Checks: `npx tsc --noEmit` exit 0; `mcp-draft.test.ts` 16
  passed; `test_mcp_notifications.py` 6 passed.
  docs updated: `docs/NAVIGATION.md`, `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H87), `docs/CHANGELOG.md`,
  `mcp-servers.example.json`

- **Retrieval planning is health-aware (P0-2).** The static source order could
  prefer a route recorded as failing (e.g. `LIVE_STRUCTURED` 0/8) over an
  equally-eligible healthy one (`yfinance` 4/0). Added
  `python/harness/retrieval/health.py` (`build_health_index`/`rank_sources`) and
  wired it in `retrieval/layer.py`: the layer now reads the SAME `SourceHealth`
  ledger `get_source_health` reports (via the bridge `source_health` capability)
  and promotes a healthy route ahead of a failing one. It only REORDERS among
  already-available sources, is stable for equal health, never demotes a failing
  route below an unobserved one, fetches the index at most once (after the D1
  durable-replay check), and fails open. Tests:
  `python/tests/test_retrieval_health.py`.
  docs updated: `docs/harness/decisions.md` (ADR-H86), `docs/NAVIGATION.md`

- **Memory — confirmed and documented the verification/source policy (P2-11).**
  No code change: `source=explicit_user` grants authority but is stored
  `unverified`; only a user correction or an explicit `verification="verified"`
  marks a record verified. Recorded that "most records unverified" is intended
  and that the model-initiated `save` write gate is deliberate.
  docs updated: `docs/harness/memory-maturity-baseline.md`

- **Source health — canonical route keys + persisted probes (P0-3/P1-5).** The
  `SourceHealth` ledger was fragmented: the same route appeared under `Equity`
  and `equity`, under `unknown`/`*`, and the `research_health` probe tested one
  provider (`duckduckgo-html`/`safe-get`) while production recorded another
  (`WEB`) — so a working provider was reported as failing and per-route success
  rates were wrong. Added `src/lib/harness/health-key.ts` with a closed
  vocabulary (`canonicalMarket`/`canonicalAssetClass`/`canonicalSource`, alias
  folding to one source per provider) applied on both write and read, and made
  the `research_health` probes upsert into the same ledger under the same
  instrument-less route key as production. New module keeps `data-bridge.ts`
  under its size ratchet. Tests: `src/lib/harness/health-canonical-keys.test.ts`.
  docs updated: `docs/harness/decisions.md` (ADR-H85), `docs/NAVIGATION.md`,
  `docs/DATA-FLOW.md`

- **`memory` tool — null-limit crash fixed.** `action=list` failed with
  `TypeError: int() argument must be a string ... not 'NoneType'` when the model
  emitted a present-but-null `limit` (JSON `null`): `args.get("limit", 20)`
  returns `None` because the key exists, so `int(None)` raised. Coerced the
  optional integer args in `python/harness/memory_tools.py` with `or` instead of
  the positional default (`memory` search/list, `session_open` before/after),
  which also catches `None`; added a regression test asserting both branches
  tolerate `limit: null`.
  no doc change — bug fix, contract unchanged.

- **MCP integrity — real-server defects fixed and the remaining gaps closed.**
  Two sessions. First: a provider-side error body returned with `isError=false`
  is now a failure (pure `looks_like_provider_error` classifier, an explicit
  rendered failure, `mcp_tool_provider_error`); **Test is not Verify** — a new
  operator-triggered `POST /mcp/servers/{id}/verify` makes one bounded read call
  and records a content-free verdict; the un-launchable `sec-edgar-mcp` preset is
  replaced with the launched `@pipeworx/mcp-edgar`; `notion`/`dropbox` ids become
  `notion_local`/`notion_remote`; a `read` tool with a write-shaped name is inert
  until explicitly acknowledged; a per-run MCP call budget, a `maxTools`
  truncation diagnostic, and a stale-lazy-cache signal were added. Continuation:
  inbound `notifications/tools/list_changed` now triggers rediscovery of one
  server (re-engaging the confirmation gate), and a `resources`/`prompts`
  list-changed notification refreshes that listing so the utility tools serve the
  current snapshot rather than the stale connect-time one, each with a
  content-free `mcp.catalog.changed` event (ADR-H81); a per-server circuit breaker stops futile
  calls to a server that connects but fails every call, with an operator reset
  (ADR-H82); a spawn-path OSV supply-chain check fails closed on a confirmed
  malware advisory and open on a network error (ADR-H83); a sampling model
  allowlist and a 64-char tool-name clamp (ADR-H84); `python/pytest.ini` prints a
  passing summary line; the test-only `_testtmp.py` moved to
  `python/tests/_tmp_helper.py` and is adopted by `python/conftest.py`.
  docs updated: `docs/harness/mcp-integrity-progress.md` (new + continuation),
  `docs/harness/decisions.md` (ADR-H77–H84), `docs/harness/architecture.md`,
  `docs/NAVIGATION.md`, `docs/harness/mcp-phase-6-progress.md`,
  `docs/harness/mcp-ui-parity-progress.md`, `CONTRIBUTING.md`

- **General settings — Start screen control removed; background picker promoted.** Removed the "Start screen" button grid from Settings › General › General (the boot tab now just follows the default/deep link; `general-prefs` still stores it for compatibility). The Background panel now leads the General tab, and the shipped **Eclipse I** wallpaper is the default on first run (`DEFAULT_BACKGROUND.mode = 'image'`, `preset = 'eclipse-1'`). The wallpaper fills the main content panel (right of the sidebar) on the ChatBot landing only (empty transcript) and resizes with it, so opening the sidebar keeps the image fully visible; the sidebar keeps its normal (non-transparent) frost. Follow-up to the background feature below.
  no doc change — same unreleased feature; docs already describe the background system.

- **Background fix — scrim was an invalid `background-image` layer.** The legibility scrim was written as a bare color (`rgba(0,0,0,0.45)`), but a color is not a valid `background-image` value; CSS dropped the *entire* multi-layer declaration, so no pattern or wallpaper ever painted. The scrim is now a solid-gradient image (`linear-gradient(rgba(...), rgba(...))`) and the CSS `var()` fallback changed from `transparent` to `none`. Same-day follow-up to the background feature below.
  no doc change — bug fix in an unreleased change.

- **Settings › General › Background — customizable page wallpaper.** The hardcoded, dead `/backgrounds/eclipse bg.svg` chat-landing block (the file no longer exists) is replaced by a real background system in `src/lib/backgrounds.ts` (Settings › General › Background). Mode `none | pattern | image`: `pattern` absorbs the old Solid/Gradient/Grid control from Customization › Glass & Surfaces (single background surface now, tinted by brand, app-wide), and `image` offers the shipped Eclipse wallpapers (`public/backgrounds/eclipse bg-1.svg`/`-3.png`/`-4.svg`/`-5.svg`) or a user picture. Wallpapers paint the **ChatBot landing only** via a `.app-bg-layer` filling the main content panel (right of the sidebar, so the menu overlays the image). Custom uploads are downscaled client-side (~2560px, JPEG/PNG, up to 30 MB in) and stored in **IndexedDB** (`be_background`/`custom`) so a full-res wallpaper never eats the ~5 MB localStorage budget; prefs live in `be_background_v1`. Adds fit (cover/contain/tile) and a darkening scrim for legibility. Applied via `useHydrateBackground` in `stock-chat.tsx`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Root .gitignore: ignore a stray root node_modules/.** A tool running vitest from the repo root created `node_modules/.vite`; ignored so it can never be committed.
  no doc change — ignore-rule only.

- **Terminal cleanup — guard floor, line endings, commits.** Pinned the CHANGELOG guard floor to 345 and added an archive-seam assertion; normalized the 66 working-tree files that mixed CRLF/bare LF (content proven unchanged) and added a mixed-ending guard; recorded the `jdds.db` purge recommendation (keep it) and the smoke/CI caveats. Two commits: `8153d35` (line endings) and `43085d8` (closeout).
  docs updated: `docs/harness/terminal-cleanup-progress.md`, `docs/harness/closeout-progress.md`, `docs/NAVIGATION.md`

- **Terminal cleanup — codex checkpoint refs, filter remnant, stale lock.** Deleted
  the 12 
efs/codex/turn-diffs/checkpoints/* refs (12 exclusive jdds.db blobs,
  1.53 GB decompressed) and the 
efs/original/ filter remnant plus a stale
  maintenance.lock; git gc dropped .git from 101,428,986 to 46,889,484 bytes.
  Also consolidated the CHANGELOG sections and tightened its guard.
  docs updated: docs/harness/terminal-cleanup-progress.md,
  docs/harness/closeout-progress.md, docs/NAVIGATION.md

- **Closeout follow-up — CHANGELOG sections consolidated.** Same-date sections are
  now merged to exactly one section per date, the two malformed single-hash date
  headings in the archive were corrected, and an empty duplicate heading removed.
  Entry count preserved (350 before, 350 after); the rotation guard now asserts
  per-date uniqueness, no malformed heading, and an append-only floor.
  docs updated: `docs/harness/closeout-progress.md`

- **Closeout — history measurement, line endings, CHANGELOG forensics, CI.**
  Measured the five open items (see `docs/harness/closeout-progress.md`): the
  `jdds.db` history load is 20 blobs (the 12 `refs/codex/...` checkpoint refs hold
  ~1.53 GB exclusive; `backup-before-email-rewrite` has no exclusive blobs), and
  history purge/archive are prepared but not executed. Added a root
  `.gitattributes` (LF normalization; `.wav`/`.ico`/`.db` binary) so a one-line
  edit no longer shows a phantom whole-file diff — renormalized `ARCHITECT.md`
  alone, content proven unchanged by SHA. Reconciled the CHANGELOG rotation
  forensically (0 entries lost; 4 hardening entries re-filed from `2026-09-15` to
  `2026-09-30`; "347" corrected) and added a rotation guard. Restored CI at the
  true root (`.github/workflows/ci.yml`, ADR-H76) mirroring `check:all`, dropped
  the obsolete `backup.yml`, and gave `test:smoke` a documented release-tag
  trigger in `CONTRIBUTING.md`.
  docs updated: `docs/harness/closeout-progress.md`,
  `docs/harness/decisions.md` (ADR-H76), `docs/NAVIGATION.md`,
  `docs/harness/engineering-hardening-progress.md`, `CONTRIBUTING.md`,
  `.gitattributes`, `.github/workflows/ci.yml`

- **Engineering hardening — the release gate is now local and runnable.** Deleted
  the unreachable `Black-Eclipse-site/.github/workflows/` (GitHub reads only root
  `/.github/workflows`, and the git root is above the app dir). Added
  `npm run check:all` (`scripts/check-all.js`) as the one honest gate, and moved
  the three surviving eval gates (retrieval/contradiction/compaction) into
  `npm test` via `npm run test:evals` (`scripts/test-evals.js`, offline, ~0.7s).
  Removed the dead `semantic_cli` reference. Added a `.githooks/commit-msg` guard
  that enforces the CHANGELOG obligation for non-doc changes.
  docs updated: `docs/harness/engineering-hardening-progress.md`,
  `docs/harness/decisions.md` (ADR-H75), `skills/ARCHITECT.md` (ADR-039),
  `docs/NAVIGATION.md`

- **Engineering hardening — took `jdds.db` out of git.** `git rm --cached`ed the
  60 MB vault (file kept on disk); ignored it at the app level with the new
  distribution story (`scripts/doctor.js` provisions it via `npx prisma db push`).
  Fixed the root `.gitignore` (the broken `0`/`0-shm`/`0-wal` lines are now
  `*.db`/`*.db-shm`/`*.db-wal`; removed the vestigial root `/scripts/` rule).
  `git gc --prune=now` reclaimed packed garbage (size-pack 372 -> 94.5 MiB).
  The full history-purge procedure (2B) is written up but not executed.
  docs updated: `docs/harness/engineering-hardening-progress.md`

- **Engineering hardening — front-door tests and authorization.** Guarded the four
  previously-unguarded mutation routes (`POST/DELETE /api/symbols`,
  `POST /api/investor-eye/portfolio`, `POST /api/memory-providers/search`,
  `DELETE /api/skill-executions/[runId]`). Added route tests for them plus
  settings/journal-trades/provider-keys/alerts (route-test count 2 -> 11); added
  the first Python router-seam test (`python/tests/test_router_seam.py`); fixed a
  flaky macro-health test that made a real network call.
  docs updated: `docs/harness/engineering-hardening-progress.md`

- **Engineering hardening — size and lint discipline.** Replaced the single 200 KB
  file-size ceiling with a graduated guard (hard 1200 lines + a non-growing
  ratchet; soft 800) in `src/lib/size-budget.test.ts`, and added the equivalent
  Python guard `python/tests/test_size_budget.py`. Removed genuinely dead symbols
  (`LEGACY_FILES`, `vendorAvailable`, four unused test imports), lowering eslint
  warnings from 34 to 24 with no blanket disables.
  docs updated: `docs/harness/engineering-hardening-progress.md`

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

- **Docs — Eclipse-as-a-Harness roadmap: the phased plan for the code/coding-agent,
  job, delegation and self-improvement capability.** New `docs/harness/roadmap/` —
  one file per phase (`README.md` + `phase-00-policy-and-baseline.md` …
  `phase-12-evaluation-gate.md`) instead of one long document, so a reader opens
  only the phase they are running. `README.md` carries a verified capability ledger
  against a harness like Hermes (what exists: the one runtime, retrieval,
  evidence-gated research, skills, memory, MCP; what does not: any code
  read/write/run capability, isolation, a harness-owned scheduler, delegation,
  self-modification beyond skills), the four structural gaps, the invariants that
  survive every phase (indexed 3.1–3.8 so the phase files can cite them), §0 the
  audience rules, work already in flight (`run_lineage.py`, `graph_context.py`),
  the file map and the ADR table. Every phase file uses one canonical heading
  scheme (numbered §1–§11, a `## Contents` table, numbered `### 6.x` contracts) and
  ships its exact contracts (real signatures, DDL, routes), runnable acceptance
  gates and a paste-ready prompt, ending in the repo's docs obligation. Each phase
  also carries a **§4 "Who can use it (the non-expert obligation)"**: the
  capability is for the whole finance field — analysts, PMs, traders, advisors,
  accountants, risk officers, students, small-business owners — not engineers or
  quants only. User-facing text names the finance job and never the mechanism, copy
  lives as keys in `src/lib/i18n/`, refusals are one plain sentence with a next
  step, and each phase adds a plain-language gate over
  `policy.PLAIN_LANGUAGE_DENYLIST`. The ADR series is numbered contiguously from the
  current tail: **ADR-H93…ADR-H114**. Planning docs only — no code, tests or runtime
  behaviour changed. The earlier single-file roadmap is kept as a `status: Stale`
  pointer (`docs/harness/eclipse-harness-roadmap.md`) per the "mark stale, never
  delete" rule.
  docs updated: `docs/harness/roadmap/**`, `docs/NAVIGATION.md`,
  `docs/harness/eclipse-harness-roadmap.md` (now Stale)

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
- **Command Center fullscreen: move the Exit control into the top bar.** The
  fullscreen overlay's Exit button floated at bottom-right over the board; it
  now sits in the TopBar row (top, trailing edge, next to the app chrome) and
  no longer overlaps widget content. Placement/style-only fix; no doc change —
  presentation change, no architecture/contract/setup impact.
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
- **Memory/skills system review** — Compared Eclipse-Memory with Hermes Agent to identify improvements in retrieval, procedural learning, discoverability, and provider ergonomics; no implementation changes were made. no doc change — analysis-only review

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
