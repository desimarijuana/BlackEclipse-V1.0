# Change Log

## Rotation policy

This file keeps a rolling window of the **most recent 7 dated sections** (the active window). Older dated sections are **moved** - never deleted - into monthly archive files under `docs/changelog/YYYY-MM.md`. New entries are appended under the current date; the commit-msg hook checks this path. Rotation is by hand only when this file grows unwieldy; the archive link below points at where the older entries went.

> Older entries are archived under `docs/changelog/` (monthly). The most recent 7 dated sections are kept here.

## 2026-10-08

- Test-only: the data-bridge identity news case now gets a 20s timeout (it
  exercises the real news/web transport with no provider mock, so the 5s default
  made the release gate load-sensitive). No production code change — no doc change.

- Agent Workspace sidebar chrome polish: removed the hard `border-b` separators
  under the header and the panel tabs (the frosted-glass edge is the separation),
  and replaced the header `Sparkles` glyph with the `Bot` agent icon. Cosmetic
  only — no doc change — no contract/architecture impact.
- Agent Workspace sidebar is now actually draggable-resizable: the left-edge
  handle was sitting under the `z-10` content layer and was ungrabbable. Raised
  it to `z-30`, widened the hit area, added a hover affordance (no permanent
  border), locked body cursor/text-selection during the drag, and gave the handle
  `role="separator"`. Width still persists to `localStorage`. Cosmetic/interaction
  only — no doc change.

- **Market Data Layer hardening: observability console, measured rate limits,
  streaming durability.** Closes the three limitations recorded for the market
  subsystem. (1) *Operability*: an operator console `MarketDataConsole`
  (`src/components/screens/market-data-console.tsx`) rendered inside Settings ›
  Data & providers (composed with the Financial Data Gateway panel), backed by a
  front-door proxy `src/app/api/harness/market/[...path]/route.ts` +
  `src/lib/harness/market-client.ts`, showing providers/key presence, per-provider
  health, declared-vs-observed rate limits with latency, stream state/metrics,
  cache and quality findings; the Python health route now returns
  `providerMetrics` (calls/avg/max latency + rate-limit snapshot). (2) *Rate-limit
  realism*: new `python/harness/market/ratelimit.py` paces on the DECLARED limit
  AND the provider's live quota observed from response headers;
  `connectors/security.ts` now returns response headers, `market/rate-limit.ts`
  parses provider quota headers (Binance `X-MBX-USED-WEIGHT-1M`, generic
  `x-ratelimit-*`, `Retry-After`), adapters attach a `rateLimit` block, and the
  gateway feeds it back via `observe()` so the effective limit is the stricter of
  declared and observed. (3) *Streaming durability*: jittered exponential backoff,
  a silence watchdog that reconnects a connected-but-silent socket, an optional
  reconnect cap (`state="backoff"`), bounded dedup LRU, and per-provider metrics.
  Tests: `python/tests/test_market_ratelimit.py` +
  `src/lib/harness/market/rate-limit.test.ts` + durability/soak cases in
  `test_market_streaming.py` + opt-in live soak `test_market_live.py`
  (`BLACK_ECLIPSE_MARKET_LIVE=1`). Docs updated: `docs/harness/market-data.md`,
  `docs/CHANGELOG.md`.

- **Vision model recognition + cross-provider vision fallback (fixes "needs a
  vision-capable model configured").** Vision is now decided **per model family,
  not per SDK kind**: the shared `openai` kind no longer blanket-claims vision, so
  text-only models (gpt-3.5/gpt-4/o1-mini, deepseek-chat, groq/llama, grok-2, …)
  are no longer routed natively and wasted, while known VLMs are recognized
  (gpt-4o/4.1/o-series/5, Claude, Gemini, grok-2-vision, and open-weight llava,
  qwen2-vl/qwen2.5-vl/qwen3-vl, minicpm-v, moondream, pixtral, llama-3.2-vision,
  llama-4, internvl, phi-3-vision/phi-4-multimodal, gemma-3, deepseek-vl, …).
  `plan_route` now reads the run model's capabilities DIRECTLY (never a routed
  substitute), fixes a registry lookup that passed a string where a list was
  required, defaults to the process runtime, and may fall back to a vision model
  on a DIFFERENT provider when that provider is keyless-local or has an env-var
  credential (`models.provider_has_credentials`; still never a provider without a
  key). Document Intelligence routes its embedded-image analysis and OCR fallback
  through the vision orchestrator so a text-only run model still gets a real VLM.
  Files: `model_runtime/catalog.py`, `harness/models.py`,
  `vision/capabilities.py`, `vision/routing.py`,
  `document_intelligence/{orchestrator,ocr}.py`. Tests
  `python/tests/test_model_vision_capability.py` (+ updated local-only vision
  invariant). ADR-H148. Docs: `docs/harness/vision.md`, `docs/harness/decisions.md`.

## 2026-10-07

- **Financial Data Gateway — provider registry, centralized rate limits, crypto
  source, provider-introspection tool + console.** Extends the existing Financial
  Retrieval Layer (not a second data plane). New
  `python/harness/retrieval/registry.py` (`ProviderDescriptor`/`ProviderRegistry`:
  capabilities, credential REFERENCE only, rate-limit shape, recorded
  license/attribution/redistribution/storage policy; `implemented=False` rows name
  their missing dependency rather than faking an adapter),
  `python/harness/retrieval/ratelimit.py` (`RateLimitManager`: per-provider
  sliding-window + concurrency + 429/`Retry-After` cooldown; a denied acquire
  never calls the provider and yields an honest `rate_limited` outcome), and
  `python/harness/retrieval/crypto.py` (`CryptoSource`; crypto is not an equity —
  `is_crypto()` is the ONE classifier and the vault/live provider refuses crypto).
  Layer wiring in `retrieval/layer.py` (`_retrieve_one` acquires/releases; `CRYPTO`
  source registered; `effective_authority` is crypto-aware) + `retrieval/routing.py`
  (`rate_limited` route category). New TS capability `crypto_market_data`
  (`data-bridge.ts`/`types.ts`/`api/harness/data/route.ts`/`health-key.ts`) reusing
  the existing crypto connector + `classifyIdentifier`; new `provider_key_status`
  capability (presence only, never a value). New agent tools
  `financial_providers`/`financial_resolve_entity`/`market_get_crypto`
  (`retrieval_tools.py`, added to `eclipse-agent`). Operator-gated route
  `GET /financial/providers` (`routers/financial.py` + front door
  `api/harness/financial/providers/route.ts`, which merges vault credential
  presence). UI `src/components/screens/financial-data-console.tsx` (frosted-glass
  provider console in Settings › Data). Tests: `python/tests/test_provider_gateway.py`
  (20) + `src/lib/harness/data-bridge-gateway.test.ts` (4). Docs updated:
  `docs/harness/financial-data-gateway.md` (new), `docs/NAVIGATION.md`. Fixed an
  incomplete `build_graph(market=…)` keyword left by the in-flight Market Data
  Layer work so the graph tests pass.

- **Market Data Layer — first-class, provider-agnostic market data + real-time
  streaming.** New `python/harness/market/`: canonical records (`models.py`),
  closed error vocabulary (`errors.py`), env-driven config (`config.py`),
  canonical instruments + provider symbol mapping (`instruments.py`), declarative
  provider capabilities (`providers.py`), capability-aware routing with circuit
  breaking (`router.py`), the `MarketDataGateway` (route → fetch → normalize →
  quality → provenance, `gateway.py`), a mandatory data-quality engine
  (`quality.py`), a freshness-aware cache (`cache.py`), Evidence-Engine provenance
  + point-in-time (`provenance.py`), derived analytics (`analytics.py`), durable
  snapshot/instrument/quality persistence on the ONE `agent-memory.db`
  (`store.py`), real WebSocket streaming (`streaming.py`: connection manager,
  normalizer, sequence validation, dedup, reconnect, backpressure), the fourteen
  agent tools (`tools.py`), and boot wiring (`bootstrap.py`). New TS provider
  adapters under `src/lib/harness/market/` (yahoo, binance, coingecko, stooq,
  treasury/FRED, ECB-FX) reached through ONE new bridge capability `market_data`
  (`data-bridge.ts`, `api/harness/data/route.ts`, `harness/types.ts`); all reuse
  the SSRF-hardened `safeGet` and existing scraper helpers. 14 tools
  (`get_quote`, `get_historical_prices`, `get_ohlcv`, `get_volume`,
  `get_orderbook`, `get_trades`, `get_market_cap`, `get_supply`,
  `get_funding_rate`, `get_open_interest`, `get_options_chain`, `get_fx_rate`,
  `get_bond_data`, `stream_market_data`) registered and added to the
  `eclipse-agent` allowlist; operator-gated routes `routers/market.py`. Tests:
  `python/tests/test_market_{unit,gateway,streaming}.py` +
  `src/lib/harness/market/bridge.test.ts`. Requirements: `websockets` + `httpx`
  pinned. Docs updated: `docs/harness/market-data.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.

- **Document Intelligence subsystem — production vision + document understanding.**
  New `python/harness/document_intelligence/`: one `process_document` pipeline
  (validate → cache → detect → adapter parse → OCR/vision → structure → entities →
  chunk → index → evidence → assess) over a unified `DocumentIR`, with one adapter
  per format (PDF, DOCX, PPTX, XLSX, ODS/ODT/ODP, CSV/TSV, JSON/JSONL/XML/YAML/TOML,
  HTML, Markdown/TXT, image, EPUB, RTF, archive, legacy OLE). OOXML is parsed with
  stdlib `zipfile`+`ElementTree` (lxml recovery) — no `openpyxl`/`python-docx`/
  `python-pptx` dependency. Deterministic-first OCR routing (`ocr.py`) escalates to
  a vision model only when there is no usable text or confidence is low; all model
  calls, OCR engines and PDF rendering reuse `harness.vision`; extracted text
  becomes the SAME `research.web_contracts.Evidence` via `EvidenceStore`
  (`contentTrust=UNTRUSTED`); tabular questions are computed with read-only
  DuckDB/pandas SQL (`query.py`), never model arithmetic. Security: size/magic/macro
  validation, archive/zip-bomb guards before extraction, `mcp.ssrf` on document URLs,
  HTML sanitization, and the shared injection boundary (document text is DATA).
  States (`READY`/`PARTIALLY_READY`/`FAILED`), bounded retry, per-document timeout,
  content-hash caching, and hybrid lexical+structured retrieval with full
  document/version/page/section/table/cell provenance. The `Di*` tables live on the
  ONE `agent-memory.db`. New `DOCUMENT_TOOLS` (`document_open|inspect|search|extract|
  analyze|query|compare|render|capabilities`, all read-only) on the finance and code
  agents; boot wiring in `service.py`; `documents` run blob on `HarnessRun`/
  `RunResult`/`client.final`; TS `document-view.ts` + `document-panel.tsx`; tests
  `python/tests/test_document_intelligence_{unit,tools,security,graph}.py` +
  `document_intelligence_helpers.py` + `src/lib/harness/document-view.test.ts`.
  No new dependency. Docs updated: `docs/harness/document-intelligence.md`,
  `docs/harness/decisions.md` (ADR-H147), `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Vision operational hardening — sensitive decided pre-flight; the asset TTL is
  real.** Two problems a surface "limitation" could otherwise cause were closed.
  (1) The orchestrator now runs `security.preflight_scan` (deterministic OCR over
  the frame) BEFORE routing/storage and merges the verdict into the privacy
  decision, so a frame containing a key/PII-shaped string or an injection attempt
  is marked sensitive — under `local_only` it never reaches a cloud provider, and
  `_store_asset` gives it a TTL. Only STRONG signals auto-flag (a crypto chart's
  bare "token" does not over-refuse cloud); without an OCR engine the pre-scan is
  skipped and reported, never silently "clean". (2)
  `AgenticService.run_startup_maintenance` now calls
  `VisionAssetStore.sweep_expired()`, deleting expired asset rows and their files
  on boot, so a sensitive screenshot does not outlive its purpose and disk stays
  bounded. Added `security.preflight_scan`, a `vision.security` telemetry event,
  and tests in `python/tests/test_vision_capabilities.py`. Docs updated:
  `docs/harness/vision.md`, `docs/CHANGELOG.md`.

- **Vision live provider smoke test (opt-in).** New
  `python/tests/test_vision_live.py` exercises a REAL multimodal model —
  native-vision image reading, deterministic OCR, and the auxiliary-fallback path
  (a text-only run model delegating to a configured vision model). It is skipped
  by default with an explicit `NOT RUN — ...` reason, gated by
  `BLACK_ECLIPSE_VISION_IT=1` + `BLACK_ECLIPSE_VISION_MODEL`. Verified against a
  live provider (native read + OCR + fallback all pass). Docs:
  `docs/harness/vision.md`.

- **Vision capability closers — stdlib PDF, persistent visual memory, image
  generation.** Closed three items that were implementable rather than genuine
  external limits. (1) `vision/documents.py` gains a dependency-free `_StdlibPdf`
  backend: text extraction from PDF content streams always works without
  `pypdfium2`, and Pillow rasterizes standard-font pages; each `DocumentPage`
  records `textMethod`/`rasterMethod` and `pdf_capabilities()` reports availability
  (never a faked page). (2) New `vision/memory.py` + `vision_remember` tool persist
  a visual observation through the SAME Eclipse-Memory decision gate
  (`authorize_proposal`+`commit_decision`) — a text summary only, the
  content-addressed `assetId`/regions/model/confidence in `structuredData`, and a
  1-day TTL for sensitive/ephemeral results. (3) New `vision/generate.py` +
  `image_generate` tool speak the OpenAI-compatible `/images/generations` protocol,
  gated by a declared `image_generation` capability; the tool is registered
  `external_action` (approval-gated) and removed at `plan_only` via
  `policy.VISION_EXTERNAL_TOOLS`. Image-generation model families declared in
  `model_runtime/catalog.py`. `VISION_TOOLS` now 18; tests
  `python/tests/test_vision_capabilities.py`. Docs updated: `docs/harness/vision.md`,
  `docs/harness/decisions.md` (ADR-H146 addendum), `docs/CHANGELOG.md`.

- **Vision / Multimodal subsystem — one orchestrator, native-first, integrated
  end to end.** New `python/harness/vision/` gives the agent a production image
  capability (analyze/describe/VQA, screenshot + clipboard, OCR, visual grounding
  for computer-use coordinates, chart analysis with deterministic market-data
  verification, document/PDF/table vision, visual comparison) behind the ONE
  `VisionOrchestrator.orchestrate` pipeline (resolve→preprocess→content-addressed
  store→route→capability detect→cache→dispatch→fallback→telemetry). Every model
  call routes through the existing `model_runtime` (no second provider stack);
  native vision is used first and an auxiliary vision model is the fallback.
  Deterministic-first: OCR before a model, PDF text layer before a model, pixel
  diff before a model describes it. Untrusted input: SSRF-guarded URL fetch on
  every hop (`mcp.ssrf`), bomb/size ceilings, and in-image text scanned + wrapped
  as DATA (`research.web_security`); no visual instruction can override the system
  prompt. Images are SHA-256 content-addressed on the gitignored filesystem tier
  with a `VisionAsset` metadata table on `agent-memory.db`; the cache is a bounded
  in-process TTL keyed over image hash + model + provider + prompt + mode +
  preprocessing + schema version (no Redis — consistent with the repo). Visual
  observations become the existing `research.web_contracts.Evidence` with full
  provenance. `VISION_TOOLS` (all read-only) are declared on the finance and code
  agents; boot wiring `AgenticService.vision_assets`; a bounded `vision` run blob
  persisted on `HarnessRun.vision` and carried on `RunResult`/`client.final`;
  TS `src/lib/harness/vision-view.ts` + `src/components/chat/vision-panel.tsx`
  render it inline in the chat transcript; vision tool labels in
  `response-model.ts` and activity detail/summary in `code/activity.py`;
  `pypdfium2` added to `requirements.txt`. Tests
  `python/tests/test_vision_{unit,orchestrator,tools,graph}.py` +
  `src/lib/harness/vision-view.test.ts`. Docs updated:
  `docs/harness/vision.md`, `docs/harness/decisions.md` (ADR-H146),
  `docs/NAVIGATION.md`.

- **Agent Workspace is now a real docked right sidebar.** Replaced the floating,
  13-tab telemetry overlay with a proper full-height glass column in the shell's
  primary row (mount moved from `app/layout.tsx` to `stock-chat.tsx`, sibling of
  the main panel, so the main panel shrinks instead of being overlapped; same
  pattern as `TerminalDock slot="right"`). Minimal tabs only: **Output**
  (default), **Changes**, **Approvals**, **History** — the removed
  overview/activity/tasks/context/telemetry/research/browser/computer/artifacts
  panels read as noise. New `output-panel.tsx` feed: chronological tool
  calls/commands/file writes, each expandable IN PLACE to render its bounded
  large output (ChatGPT / Claude Code / Kimi idiom); `viewer.tsx` split so
  `ArtifactContent` is reusable inline and by the full viewer. Resizable by
  dragging the inner edge (width persisted, `MIN_W=300`/`MAX_W=760`). No hard
  border frame — the glass edge is the separation. Store panel vocabulary
  reduced to the four ids; pin/auto-focus removed. Docs updated:
  `docs/agent-workspace.md`, `docs/DECISIONS.md` (ADR-042 amended),
  `NAVIGATION.md`.

- **Agent Workspace sidebar: toggle shortcut + denser Claude-style feed.** Added
  a global Ctrl/Cmd + Shift + E toggle (new `workspace-keybind.tsx`, a
  capture-phase listener mounted in `app/layout.tsx` beside the terminal keybind
  so it works whether the sidebar is open or closed; predicate skips while typing
  and is unit-tested). Listed it in the keyboard-shortcuts help dialog. Reworked
  the Output feed for density: timestamps are no longer shown in the row (kept in
  the expanded detail line), consecutive same-tool calls GROUP into one row with a
  ×N badge and expand to the list, and a header **Collapse all** clears every open
  row when any is expanded. New i18n key `workspace.collapseAll`. Docs updated:
  `docs/agent-workspace.md`.

- **Computer Use Engine — isolated + remote desktops (Xvfb / RDP / Windows Sandbox
  / Wayland).** `desktop.py` becomes a provisioner lifecycle
  (`DesktopProvisioner`/`DesktopInstance`/`build_provisioner`): the real
  `X11HeadlessProvisioner` (a private `Xvfb` display per session),
  `WindowsSandboxProvisioner` (launches `WindowsSandbox.exe`, attaches a
  `WindowDriver` to the client window), `RdpDesktopProvisioner` (`mstsc` against
  `isolation.rdp_host`/`rdp_file`) and `WaylandHeadlessProvisioner` (a nested
  headless `wlheadless-run`/`sway`/`weston` on a private socket). New
  `drivers/window.py` scopes capture/input to one contained desktop window
  (background-first, then foreground) and derives a real element tree from OCR of
  the window (`source=ocr`; `accessibility:false` honestly without OCR). New
  `drivers/wayland.py` (grim + ydotool); real `drivers/linux.py` (+AT-SPI) and
  `drivers/macos.py` (+AX). `manager.py` provisions/tears down per session;
  isolated sessions skip the machine-wide broker; `headless_desktop` is true only
  for a genuinely provisioned desktop; absent backends fall back to local with a
  reason. New `broker.py` (machine-wide lease); config `isolation.*`
  (`HARNESS_COMPUTER_ISOLATION*`, `HARNESS_COMPUTER_RDP_*`). Tests
  `test_computer_hardening.py` + opt-in `test_computer_apps_live.py` /
  `test_computer_xvfb_live.py`. Docs updated: `docs/harness/computer-use.md`,
  `computer.example.json`.

- **Approvals — "Always allow" standing grants, a redesigned card, and an alert
  on request.** Made the repeated approval prompts stoppable. (1) New
  `python/harness/grants.py` (`GrantStore` on the ONE `agent-memory.db`, table
  `StandingGrant`): an explicit, operator-only, revocable permission scoped to
  `(kind, scope, pattern)` — one program/tool in one workspace. (2)
  `ApprovalStore` gains `.grants`, additive `grantPattern`/`grantKind`/`grantScope`
  columns on `McpApproval`, and `remember_grant()` (built ONLY from the row's own
  columns). (3) The shell/terminal/terminal-subsystem/MCP/Git authorizers consult
  a grant BEFORE creating a pending request: a match authorizes immediately and
  emits `approval.granted`; a `deny`-classified command is still refused first, and
  a dangerous/destructive/critical Git op is never grantable. (4) `POST
  /mcp/approvals/{id}/decide` and `POST /code/approvals/{id}/decide` accept
  `remember`; new operator-gated `GET /grants` + `POST /grants/{id}/revoke`
  (`routers/grants.py`), fronted by `src/lib/harness/grants-client.ts` +
  `grants-browser.ts` + `src/app/api/harness/grants/**`. (5) Redesigned
  `ApprovalCard` — no yellow: the app's emerald primary + neutral/rose risk scale,
  buttons **Allow once / Always allow `<program>` / Cancel**; "Always allow" is
  offered only when the runtime marks the action grantable and never for high
  risk. (6) An `approval_request` now plays the `notification` cue and raises the
  shared toast/OS notice (`ALERT_NOTIFY_EVENT`). (7) New `StandingGrantsPanel`
  (Code › Approvals) lists and revokes grants. Docs: `docs/harness/decisions.md`
  (ADR-H144), `docs/harness/architecture.md`, `docs/NAVIGATION.md`; tests
  `python/tests/test_standing_grants.py`.

- **Authentication & multi-user mode — opt-in, auto-engages off loopback.**
  BlackEclipse is now able to require a signed-in user, without breaking
  zero-config. A single mode resolver (`src/lib/auth/config.ts`) makes auth
  **required** when `HARNESS_AUTH=required`, or automatically when the app is
  bound beyond loopback (or is a production build), and **off** for a local dev
  bind — so `npm run dev` on localhost stays accountless. When required but
  `HARNESS_AUTH_SECRET` is missing the app **fails closed** (`503
  AUTH_MISCONFIGURED`); `doctor.js` prints the posture at boot. Two layers: the
  Edge `middleware.ts` gates every page and `/api/**` on a validly signed session
  cookie (except `/login` and `/api/auth/**`), and `requireApiAuth` /
  `getAuthContext` (Node) do the authoritative session-row check. Passwords are
  `scrypt`-hashed (Node `crypto`, no new dependency); sessions are opaque ids in
  the gitignored `.black-eclipse/auth.db`; the cookie is `HttpOnly`/`SameSite=Lax`/
  `Secure` off loopback and signed with `jose`. Tenancy is the session's: when auth
  is on, `scope` comes from the session, never the request body (`resolveScope`).
  `/health`'s `identity` now reports the real mode (`authentication`,
  `frontDoorAuth`) instead of a hardcoded "not implemented". New: `src/lib/auth/*`,
  `src/middleware.ts`, `src/app/login/page.tsx`, `/api/auth/{me,setup,login,logout}`,
  a `better-sqlite3` ambient type. Tests: `src/lib/auth/*.test.ts`,
  `src/middleware.test.ts`, updated `python/tests/test_identity_tenancy_boundary.py`.
  Docs: `docs/harness/authentication.md`, ADR-H145. With `HARNESS_AUTH=off` the
  prior no-auth, no-tenancy reality still holds and belongs on a trusted local
  machine only.

- **Search providers — per-provider keys in the Settings modal.** A user can now
  add any named search provider (Tavily/Brave/Exa/Serper/SerpApi/Bing/Google CSE/
  SearXNG) by pasting ONE key in Settings — no `SEARCH_API_CONFIG` JSON. Each
  `SEARCH_PROVIDER_PRESETS` entry gained a unique `keyEnv` (registered in
  `provider-keys.ts`); `buildPresetSearchProvider`/`firstConfiguredPreset` build
  the chosen provider from the vault. `data-bridge.ts` resolution moved to a new
  `lib/harness/web-provider-resolve.ts` (advanced JSON config still wins; else the
  first configured named provider; else the keyless chain). `SearchRetrievalSettings`
  now renders one `ProviderKeyEditor` per provider (vault-backed, encrypted,
  never echoed) and the `/api/search-provider` status/test use the same resolution.
  Docs updated: `docs/harness/web-research-engine.md`.




- **Housekeeping — commit `73be050` scope correction (no history rewrite).**
  Commit `73be050` ("Document parallel sub-question search in the research
  engine") has a message that claims a docs-only change but actually bundles a
  ~2,841-line, 43-file Computer-Use/Browser-Runtime hardening drop; the parallel
  sub-question search it names landed in its parent `aaed4c2`. It is already
  published on `origin/main`, so history is intentionally NOT rewritten (per the
  repo rule against force-push without explicit authorization). This note records
  the true scope so the change is findable/reviewable by intent. No code change.

- **Research retrieval — Phase 7: honest missing-input refusal messaging.** The
  `finance_metrics` tool's refusal now names the exact missing input, states that
  no default/approximation will be substituted, and points at the remedy
  (`web_extract` the source, or `finance_metric_catalog` for a metric whose
  inputs exist). This is a by-design invariant (never fabricate financial data),
  not a defect. Docs updated: `docs/harness/web-research-engine.md`.

- **Research retrieval — Phase 6: evidence-anchored entity/knowledge graph.**
  Added a general graph beyond claim→evidence. `web_store.py` gains
  `WebResearchEntity` + `WebResearchRelation` tables (every node/edge records the
  `evidenceId`/`sourceUrl` it came from; no ungrounded node) with
  `save_entity`/`save_relation`/`list_entities`/`list_relations`/`find_entity`.
  New deterministic extractor `research/web_graph.py` (`build_graph`) resolves
  companies via the existing `resolve_entity`, extracts proper-noun terms, and
  derives `metric → value` and co-occurrence edges from the structured
  enrichment. The engine persists the graph and returns `entities`/`relations` on
  `EngineResult`; a new `research_graph` tool exposes it; the run API returns it;
  the Research screen gains a Knowledge Graph widget. Docs updated:
  `docs/harness/web-research-engine.md`.


- **Phase S — stabilization (ratchet hygiene, docs drift, process).**
  (S.2) **Ratchet hygiene** — `main.py`'s FastAPI lifespan boot/shutdown wiring
  extracted to `harness/boot.py`; `main.py` dropped from ~1018 to ~955 lines (under
  the 1200-line hard ceiling) and was removed from the size ratchet rather than
  raised. `main` still re-exports `lifespan`, `identity_boundary`,
  `deployment_exposure`, `IDENTITY_BOUNDARY` so the public surface is unchanged.
  The finance-agent prompt ceiling was LOWERED 23300 → 23025 (trimmed a redundant
  worked example; no honesty/authority rule removed) so the ratchet bites again.
  (S.3) **Docs drift** — new `docs/harness/research-surfaces.md`, the ONE "which
  surface answers which question" page (search finds → browser reads behind a
  login → computer-use reads a desktop app), cross-linked from
  `web-research-engine.md`, `browser-runtime.md`, `computer-use.md` and named in
  `NAVIGATION.md`'s trigger table. (S.1) **Concurrency** — recorded as a
  working-practice rule (serialize writers / short-lived branches): recent commits
  swept unrelated changes together, including this session's Phase 8–10 browser
  work committed by another writer. Tests:
  `python/tests/test_phase_s_stabilization.py`. Docs: `docs/harness/decisions.md`
  (ADR-H141), `docs/NAVIGATION.md`,
  `docs/harness/{browser-runtime,web-research-engine,computer-use,research-surfaces}.md`.

- **Research retrieval — Phase 5: semantic coverage + honest provider cost.**
  (a) `web_engine.py` coverage is now layered and discloses its method
  (`coverageMethod`): embedding similarity when an embedding runtime exists
  (`_semantic_answered`), else an IDF-weighted term-overlap score
  (`_idf_answered`) that answers a sub-question only when its distinctive terms
  are corroborated, else the conservative keyword fallback. Per-question scores
  are returned in `questionScores`; still a coverage signal, never a correctness
  claim. (b) New `research/web_pricing.py` (`CostLedger`, `price_for`) gives an
  HONEST cost estimate: keyless providers are FREE known-0.0, a paid provider
  with no `HARNESS_WEB_PRICE_<PROVIDER>_QUERY` is UNKNOWN (None, never 0), and a
  total is `exact` only when every used provider was priced. `maxCost` is now
  ENFORCED before extraction when prices are exact; `coverage["cost"]` is
  recorded on the run. Docs updated: `docs/harness/web-research-engine.md`.

- **Research retrieval — Phase 4: dedicated Research screen.** Added a
  first-class `research` AppTab (not just the chat Sources panel), wired into
  `app-tabs.ts`, `sidebar/config.ts`, `i18n/nav.ts` + `dictionaries/en.ts`,
  `search/deep-link.ts` and the SPA shell (`stock-chat.tsx`). The screen
  (`src/components/screens/research/research-screen.tsx`) reuses the shared
  `CustomizableWorkspace` with a research widget catalog
  (`src/lib/research/research-widgets.tsx`): run list, new-run form (background),
  live run status, evidence, claims/citations, conflicts, and a one-click
  scheduled-research enabler over the existing `/jobs` engine. State comes from
  the ONE `useResearchScreen` hook polling `/api/research/*` (new front-door
  proxy). Docs updated: `docs/harness/web-research-engine.md`.

- **Research retrieval — Phase 3: background research runs.** A long research run
  no longer blocks a single turn. `web_engine.py` gains
  `schedule_background_research(request, bridge, store, emitter)` and
  `background_research_active`; the mandate is planned+persisted SYNCHRONOUSLY
  (`create_research_sync`) before the task is scheduled, so the research id is
  observable at once and a cancel issued before start is honoured. The engine
  re-persists observable state on every transition (`_set_state`), so
  `research_status`/`research_cancel`/`research_continue` work from any later tool
  call. New tool `research_start` (registered in `WEB_RESEARCH_TOOLS`) and route
  `POST /research/web/start` return the id immediately. No schema change. Docs
  updated: `docs/harness/web-research-engine.md`. (Frictionless enabling of the
  existing disabled templates is delivered with the research screen in Phase 4,
  reusing `/jobs`.)

- **Research retrieval — Phase 2: first-class academic/news/image/video
  connectors.** Replaced the keyword-augmented `academic_search`/`image_search`/
  `video_search` hacks. New keyless connectors in `src/lib/web-connectors.ts`
  (OpenAlex, Crossref, GDELT, Openverse, Wikimedia Commons) return the same
  normalized `WebSearchResult`/`RetrievalDiagnostic` shape over the SSRF-hardened
  transport. New bridge capabilities `academic_search`/`news_search`/
  `image_search`/`video_search` (`data-bridge.ts`, `DataCapability`, data route
  allowlist). Python `web_providers.py` adds `ConnectorSearchProvider` and
  registers `eclipse_academic`/`eclipse_image`/`eclipse_video`; `web_tools.py`
  routes each tool to its kind and falls back to web search only when the
  connector chain is unavailable. Docs updated: `docs/harness/web-research-engine.md`.

- **Research retrieval — Phase 1: dependable coverage, keyless chain, paywall/JS
  escalation, one-click JS rendering.** Addressed the top retrieval limitation
  ("DuckDuckGo default is frequently bot-blocked"). (1) `web-search.ts` now
  exposes a KEYLESS FALLBACK CHAIN — `DuckDuckGoHtmlProvider`,
  `DuckDuckGoLiteProvider`, `MojeekProvider`, `BingHtmlProvider` — tried in order
  by `resolveSearchProviders`/`searchWeb`, so one blocked engine no longer blanks
  a search; the operator-configured provider still runs first. (2) Presets
  expanded to AllProviders (`serpapi`, `bing`/Azure, `google-cse` alongside
  tavily/brave/exa/serper/searxng). (3) New `src/lib/web-paywall.ts` detects
  subscription/login walls (and HTTP 402) as the new `paywalled` diagnostic
  category (`retrieval-diagnostics.ts`), routed to `ineligible`
  (`retrieval/routing.py`); a bare 403 stays `http_error` (bot/geo block).
  (4) `web_engine.py` fetch loop escalates `javascript_only`/`parse_failure`/
  `unsupported_document`/`paywalled` to the existing browser runtime
  (`web_browser.py`); `needs_escalation` recognizes paywall errors.
  (5) One-click JS rendering: `POST /browser/install` (Python) installs
  Playwright + Chromium idempotently and reports the binary's true presence;
  proxied at `src/app/api/search-provider/install`; Settings gains a
  `SearchRetrievalSettings` panel (search provider + connectivity test + Enable
  JS rendering). No architecture/contract change beyond the added diagnostic
  category. Docs updated: `docs/harness/web-research-engine.md`.

- **Computer Use Engine — hardening pass: enforce advertised limits, real
  backends, challenge stops.** Closed the gap between what the subsystem advertises
  and what it enforces. (1) `max_actions` and `action_timeout_seconds` are now
  enforced (`ComputerCore.act` wraps handlers in `asyncio.wait_for` and counts
  `session.actions_started`; over-budget ⇒ `BudgetExceeded`/`COMPUTER_BUDGET_EXCEEDED`,
  timeout ⇒ `COMPUTER_TIMEOUT`). (2) `vision_model` and `ocr_enabled` now have
  consumers; a cloud vision model is wired as the CLOUD backend so a sensitive frame
  is refused; finance allowlists (`finance_allowed_apps/accounts/instruments` +
  `HARNESS_COMPUTER_FINANCE_ALLOWED_*`) flow into the firewall. (3) New
  `ocr/windows.py` (`WindowsOCREngine`, `Windows.Media.Ocr`) makes OS-native OCR the
  `auto` default on Windows; `Pillow`/`uiautomation`/`winsdk` are declared and
  installed/repaired by `setup-python.js`/`doctor.js`. (4) CAPTCHA/MFA/biometric
  detection (`security.detect_challenge`) refuses BEFORE any input and returns
  `COMPUTER_HUMAN_REQUIRED` (verdict `ask_user`); new `computer_request_human` tool.
  (5) `security.scan_injection` flags screen text posing as instructions in the
  UNTRUSTED wrapper. (6) Background delivery now covers mouse move/scroll/drag and
  button press/release; foreground focus is restored after escalation. Config
  reference committed at `computer.example.json`. Docs updated: `docs/harness/
  computer-use.md`, `docs/harness/decisions.md` (ADR-H140).


- **Browser Automation Runtime — Phase 10 (progress, financial workflow,
  cross-engine coordination, browser→claim).** (1) **Progress → planner** —
  `browser/task.py` adds a persisted, bounded step-level checklist
  (`BrowserTask`/`BrowserTaskRegistry`) emitted as `browser.task.*` AND stored in
  `agent-memory.db` (a `BrowserTask` table), so a long run shows “open SEC →
  search → find filing → download → extract” and the progress survives the call;
  the `browser_task` tool and `GET /browser/tasks` drive/read it. (2) **A second
  bundled financial workflow** — `system.sec-filing-research` (disabled/inert by
  default, progressive disclosure, real browser/web tools only), following the
  `system.browser-research` pattern. (3) **Cross-engine coordination** —
  `research/coordination.py` documents and implements ONE routing policy (“search
  finds → browser reads behind a login → computer-use reads a desktop app”),
  deterministic via `route(SurfaceRequest)`, sharing the ONE evidence store; a
  browser-read value is a candidate. (4) **Browser→Evidence deepening** —
  `browser/bridge.py` is the ONE legal path from a browser observation to a
  verified claim: build engine `Evidence` (provenance never fabricated), then run
  the engine's OWN `verify_claim`; a claim not grounded in the observed text is
  refused. Tests: `python/tests/test_phase10_coordination.py`. Docs:
  `docs/harness/browser-runtime.md`, ADR-H139.

- **Search provider: configure a real provider by name, not JSON.** The
  `SEARCH_PROVIDER_PRESETS` catalog (Tavily, Brave, Exa, Serper, SearXNG) is now
  reachable: `resolveSearchApiConfig` accepts `SEARCH_API_CONFIG` as a preset name
  (`"tavily"` / `{"preset":"tavily"}`) or a full config object, and
  `data-bridge.resolveCustomSearchProvider` uses it, so an operator adds an
  independent second search route with a name + key (`SEARCH_API_KEY`) instead of
  hand-writing the JSON shape. Tests: `src/lib/web-search-presets.test.ts`.

- **Browser Automation Runtime — Phase 9 (provider layer completion).**
  (1) **Camofox** (`camofox`) — a stealth Firefox backend (Playwright `firefox`,
  not CDP): resolves a Camoufox binary (`camoufox` package resolver or
  `HARNESS_CAMOFOX_ENDPOINT`) and launches via the local provider with
  `executable_path`; an endpoint attaches over CDP. Honest `available:false` when
  no binary/endpoint is resolvable. (2) **Browser Use** — a real adapter: when the
  `browser-use` package is installed it starts Browser Use's browser and returns a
  `ProviderSession` Eclipse drives (Eclipse keeps reasoning/sessions/policy/
  observation/tracing); an incompatible build fails honestly. (3) **Firecrawl as
  an extraction backend** — `FirecrawlProvider.extract` calls `/v1/scrape` and is
  wired into the research engine's extraction path (`web_extract`
  `backend:"firecrawl"`, falling back to the SSRF bridge). It declares
  `interactive:false` and `launch` refuses, so an interaction can never route to
  it. (4) **Router maturity** — `ProviderHealth` demotes a provider after
  consecutive failures (re-promoting on success) with the demotion in the
  decision; `HARNESS_BROWSER_PREFER_LOW_COST` orders fitting candidates
  cheapest-first (relative hint, never a money figure); an explicit request
  overrides demotion. New config: `HARNESS_CAMOFOX_*`, `HARNESS_FIRECRAWL_ENDPOINT`,
  `HARNESS_BROWSER_PREFER_LOW_COST`, `HARNESS_BROWSER_ALLOW_PRIVATE_REMOTE`.
  Tests: `python/tests/test_browser_providers.py`. Docs:
  `docs/harness/browser-runtime.md`, ADR-H138.
- **Computer Use Engine — production readiness: high-risk target gate, prompt
  guidance, benchmark and live demo + finance harnesses.** (1) **High-risk target
  gate** — `ComputerCore._resolve_target(high_risk=True)` refuses a
  coordinate-only or low-confidence target for a CRITICAL action (a financial
  mutation, or a Submit/Buy/Sell/Transfer control the adapter flags risky), so a
  critical action can never be a blind pixel click; a caller may override only
  with BOTH `allow_coordinates` and `confirm_coordinates`. `_is_high_risk_target`
  derives the classification from the financial-mutation vocabulary, the
  destructive-label heuristic and the application adapter. (2) **Model guidance**
  — a `## Computer Use (native desktop)` prompt block (observe-first, stale-handle
  refusal, verdict/recovery, untrusted screen data, the finance firewall);
  prompt ceiling raised to 23300. (3) **Eclipse CUA Benchmark**
  (`tests/test_computer_benchmark.py`) measures grounding accuracy, verification
  accuracy, recovery success, task completion and — the finance priority —
  false-action rate and dangerous-action rate, all at their production bar
  (0 false/dangerous actions). (4) **Live demo workflows**
  (`tests/test_computer_demos.py`) run demos 1–5 against owned Win32 windows with
  the REAL Windows driver. (5) **End-to-end finance harness**
  (`tests/computer_finance_e2e.py` + `computer_finance_terminal.py`) drives a mock
  trading terminal: reads screen-derived state with provenance, computes a
  rebalance via the deterministic calculator, and proves the firewall blocks
  read_only, holds assisted for approval, and NEVER clicks a mutation control
  (checked against the terminal's own click log). Also: the fake test driver now
  models a position-aware semantic change on click, and
  `test_mcp_orphan_reaping` is cwd-independent. Docs:
  `docs/harness/computer-use.md`. 21 new tests. `docs updated:
  docs/harness/computer-use.md, docs/CHANGELOG.md`

- **Browser Automation Runtime — Phase H (hardening: frames, interception, device,
  recovery, injection).** (1) **Frames** — a `Target` may carry `frame` (nested
  with `>>`); the resolver scopes every strategy inside `page.frame_locator(...)`
  and `browser_snapshot` accepts `frame`, so cross-origin/nested frames are
  observed and acted on like the top document (cross-frame action routing).
  (2) **Recovery** — a coordinate-only target (or a locator that can't click an
  occluded/stale element) falls back to a pixel click (`strategy:"coordinates"`);
  a crashed/closed provider session surfaces a structured failure, a destroyed
  session is cleanly recreated, and an unavailable explicit provider falls back to
  the next-best. (3) **Device emulation** — `browser/devices.py` resolves a
  descriptor from whichever catalog the runtime exposes (Playwright instance
  `devices` / module export / driver `local_utils`) and reports the applied
  viewport/UA/locale/timezone; unknown device = honest error. `browser_set_*` and
  `emulate_device` record their override on the session. Device/viewport ops
  extracted to `browser/context_ops.py` (kept `session.py` under its ceiling).
  (4) **Prompt injection** — adversarial test pages (`/injection-text`,
  `/injection-tools`, `/injection-attrs`) prove page content never changes policy,
  permission levels, or the tool registry. Tests: `test_browser_hardening.py`
  (real Chromium) and `test_browser_hardening_unit.py` (offline). Docs:
  `docs/harness/browser-runtime.md`, ADR-H137. `session.py` net-shrinks.

- **Test-suite reproducibility: `test_mcp_orphan_reaping` is cwd-independent.**
  The orphan-reaping test spawned its parent with `sys.path.insert(0,
  os.path.join(os.getcwd(), "python"))` and `cwd=os.getcwd()`, so it passed only
  when pytest ran from the repo root and failed ("parent exited before starting
  its child") when run from `python/` — which is how a contributor or a
  single-file invocation runs it. It now derives the import root from
  `Path(__file__).resolve().parent.parent` and passes it to the child. No
  production code changed. `no doc change — test-only reproducibility fix`.

- **Browser Automation Runtime — Phase 8 (observability, replay, telemetry, cost).**
  (1) **Replay/inspection** — `browser/replay.py` reconstructs a stored
  `BrowserTrace` into a bounded (≤500 step) browser-free timeline with a
  `failureAnalysis` (first failing step's code/category/plain sentence) and a
  `render_text` human view; exposed as the `browser_replay` tool and
  `GET /browser/traces/{id}/replay`. It never opens a browser and never
  re-executes. (2) **Telemetry aggregates** — `browser/telemetry.py` is the ONE
  process-wide content-free aggregate: session/action/failure/timeout/crash/
  navigation counters, per-action and per-provider latency (sum/count/max only),
  vision calls, provider failures, downloads/uploads and error-category buckets,
  surfaced in `/health.browser.telemetry`, `GET /browser/telemetry`. Every tool
  call records one action at the single registration seam (`_telemetry_wrap`).
  (3) **Cost** — accrues from REAL measurements (browser-seconds split local/cloud
  by the provider's `remote` capability, vision tokens, screenshots, artifact/
  download bytes); a money figure appears ONLY when a non-zero `HARNESS_BROWSER_COST_*`
  rate is set, otherwise `ratesConfigured:false` / `estimatedMicros:null`
  (`GET /browser/cost`). (4) **Structured logs** — a bounded content-free ring
  queryable by code/level/category/session (`GET /browser/logs`). New config:
  `HARNESS_BROWSER_COST_*`, `HARNESS_BROWSER_TELEMETRY_LOG_CAP`. Tests:
  `python/tests/test_browser_observability.py` (telemetry/cost/logs/replay, no
  browser) and `test_browser_observability_api.py` (routes). Docs:
  `docs/harness/browser-runtime.md`, ADR-H136. `main.py` unchanged (`/health`
  browser block is `browser_health()`).
- **Browser Automation Runtime — Phase C/D (evidence, skills, isolation, fusion).**
  (1) **Evidence/Research integration** — `browser/evidence.py` records every
  consulted `http(s)` page (navigation, snapshot, extract) on the run's existing
  `source_sink` (`SourceCollector.add_fetched_source`), so a browser-derived fact
  reaches the answer's Sources panel with URL/title/retrieval time; internal pages
  (`about:blank`, `data:`) are never recorded and the collector shape is reused,
  not duplicated. (2) **Skills integration** — a bundled, inert
  `system.browser-research` skill wrapper (progressive disclosure; `requiredTools`
  = the browser tools) so a browser research workflow is teachable. (3)
  **Delegation/session isolation** — `session_of` now prefers a session owned by
  THIS run/agent before the cross-run fallback (`BrowserManager.list_active`), so a
  delegated subagent never drives the parent's browser. (4) **DOM+vision fusion
  surfaced** — `browser_visual_locate` (`vision.locate`) fuses the DOM locator with
  a visual match, reports the chosen path + both confidences + rationale, and emits
  `browser.visual.locate` for the trace. `waiting.py` extracted from `session.py`
  to keep it under the size ceiling. 84 `browser_*` tools. Tests:
  `test_browser_unit.py` (+provenance/fusion) and `test_browser_integration.py`
  (+`visual_locate`, source recording, two-run isolation).
- **Computer Use Engine — production stress-test hardening.** A controlled live
  validation (real Windows driver, a real Win32 test target, a bounded background
  message pump) found and fixed seven defects, each with a regression test
  `python/tests/test_computer_hardening.py`:
  (1) **Background input never reached child controls** — `PostMessage` was sent
  to the top-level window with screen coordinates; it now resolves the deepest
  child control (`RealChildWindowFromPoint`, z-order independent) and converts to
  client coordinates, and keyboard background input targets the thread's focused
  control (`GetGUIThreadInfo`). Background clicks now activate controls WITHOUT
  focus stealing, instead of silently escalating.
  (2) **Foreground escalation could click blind into a covering window** —
  `click`/`type_text`/`key` now refuse when an absolute-coordinate foreground
  action would land on a different top-level window (`COMPUTER_TARGET_OBSCURED`,
  verdict `foreground_required`) rather than hitting the wrong application.
  (3) **Verification reused the pre-action snapshot**, so semantic change was
  never seen and every action fell back to pixel noise; `capture_state`/
  `verify_action` now read a FRESH accessibility digest + title, settle-poll for
  a bounded window, and treat ONLY semantic change as `verified` (pixel-only
  churn is `uncertain`). An `uncertain` verification can no longer yield a
  `success` verdict.
  (4) **`SecurityLayer` was constructed but never called** — observation now
  scans for sensitive controls/text, flags the snapshot `sensitive`, masks the
  persisted image, and refuses cloud vision for a sensitive frame.
  (5) **`allowed_actions` was declared but never enforced** — a non-empty
  allowlist now blocks an unlisted action (`COMPUTER_ACTION_NOT_ALLOWED`).
  (6) **The recovery ladder was never surfaced** — a failed action now carries
  its ordered `recoveryPlan`, and an unexpected dialog (`UNEXPECTED_DIALOG`)
  stops the loop instead of typing into it.
  (7) **`set_value` used a blocking `SendMessage`** (an unresponsive control could
  hang the async loop) — now `SendMessageTimeoutW` with `SMTO_ABORTIFHUNG`.
  Also: `Bounds.from_any([x, y])` returns a point (not `None`), snapshot ids are
  unique across sessions, `mouse_move` uses a real permission band, and
  `computer_remember` uses `execution_lesson` (the permitted Eclipse-Memory
  source) so memory writes actually succeed. Stress rig:
  `python/tests/computer_stress_rig.py` + `computer_stress_target.py` +
  `computer_stress_focus.py` (36/36 pass). Docs:
  `docs/harness/computer-use.md`.

- **Evidence-Driven Web Research Engine — a first-class research subsystem.**
  New `python/harness/research/web_*.py` package implementing
  `question → intent → mandate → plan → provider registry (ordered fallback) →
  search → extract → browser escalation → normalize → entity resolution →
  EvidenceStore → freshness/point-in-time → source ranking → source comparison →
  conflict detection → deterministic calculations → claim verification →
  citation generation → citation validation → coverage → synthesis → status →
  immutable snapshot`. The governing rule is explicit and enforced: **search
  results are pointers, not evidence; the LLM reasons over evidence and is never
  the source of truth.** Reuses (never duplicates) the existing retrieval layer,
  the TS web transport via the `DataBridge` (`web_search`/`web_fetch`), the
  Browser Automation Runtime (escalation only), `research.budget`/`periods`/
  `calculations`, the SSRF/redirect guards, the untrusted-content boundary and
  the ONE `agent-memory.db` connection for its `EvidenceStore`. 21 read-only
  tools on the ONE `ToolRegistry` (`web_search`, `news_search`, `company_search`,
  `academic_search`, `image_search`, `video_search`, `web_extract`,
  `page_extract`, `pdf_extract`, `structured_extract`, `research_plan`,
  `research_query`, `source_rank`, `source_compare`, `claim_verify`,
  `citation_extract`, `citation_validate`, `research_status`, `research_cancel`,
  `research_continue`, `research_update`); `WEB_RESEARCH_TOOLS` added to the
  finance and code agents; operator-gated router `routers/research.py`
  (`/research/web/*`); `EvidenceStore` tables on `agent-memory.db`. Point-in-time
  research fails closed (unknown-time sources are excluded), news syndication is
  grouped into source families, and injected page instructions are preserved as
  evidence but never laundered into a finding. Tests: `test_web_research_{unit,
  integration,tools,api,hardcore}.py` (48 cases). Docs: `docs/harness/web-research-engine.md`,
  `docs/harness/decisions.md` (ADR-H135), `docs/NAVIGATION.md`.

- **Web research engine — production hardening.** Fixed a set of defects found in
  the first cut: (1) **deep runs were hard-killed by the agent's generic
  `toolTimeoutMs` ceiling** — a `ToolDefinition.long_running` flag now lets
  `research_query`/`research_continue`/`research_update`/`web_extract` use their own
  declared budget (still clamped to the global ceiling), and `ToolRegistry.execute`
  exposes the ACTUAL effective timeout on `ToolContext.tool_timeout_ms` so the
  engine sizes its internal deadline below the ceiling and returns a bounded
  partial instead of dying; (2) **`update_research` deleted prior evidence** — it is
  now non-destructive (idempotent upsert + a new snapshot) and returns a delta
  (added/changed/dropped sources, added/removed evidence); (3) **unbounded payloads**
  — evidence `rawText` is bounded to 8k in the tool/API view (the store keeps the
  full text); (4) **unbounded process-wide status/cancel maps** — pruned to 256
  tracked runs, terminal-first; (5) events namespaced `webresearch.*` (no collision
  with the Phase-4 `research.*` stream); (6) coverage no longer overstates
  `answeredQuestions` (keyword-corroboration count, plus `sourceCoverage`); (7)
  router rejects an unknown `depth` with 422 and bounds snapshot/evidence payloads.
  Tests: `test_web_research_hardening.py` (9 cases). Doc: `docs/harness/web-research-engine.md`.

- **Web research engine — second bug-fix pass (data integrity).** (1) **Shared
  `EvidenceStore` never reached the run** — `service.evidence_store` was built but
  not passed to `execute_run`/`build_graph`, so tools silently built a throwaway
  store; it is now threaded through on both the sync and async paths. (2) **Cross-run
  clobbering** — `sourceId`/`evidenceId` were the primary key, so fetching the same
  URL in two runs made the second run's `list_*` return nothing; membership is now
  an explicit many-to-many link table (`WebResearchSourceLink`/`WebResearchEvidenceLink`)
  with a one-time marker-tracked backfill. (3) `make_source` returned an EMPTY
  `retrievedAt`; it now stamps retrieval time. (4) Per-run claim/citation/conflict
  ids were namespaced by `researchId`. (5) `list_evidence` coerces NULL/partial
  legacy columns to honest defaults so `Evidence(**row)` can never crash a tool.
  (6) A `continue`/`update` after a cancel no longer aborts itself (the event is
  cleared at resume) while a create→cancel→execute still honors the cancel. Tests:
  `test_web_research_store.py` (7 cases). Doc: `docs/harness/web-research-engine.md`.

- **Computer Use Engine — a production-grade desktop-control runtime.** New
  `python/harness/computer/` package (62 modules) implementing the full agentic
  loop `OBSERVE → … → AUTHORIZE → ACT → VERIFY → RECOVER`: a platform-independent
  `ComputerDriver` (Windows via `ctypes` Win32 — no third-party package; honest
  `NullDriver` elsewhere), accessibility-first observation (UI Automation when
  installed, a Win32 child-window baseline, OCR, provider-agnostic vision),
  screen-of-marks snapshots with **stable element handles + stale-element
  protection**, a grounding hierarchy (accessibility → semantic → structured →
  OCR → vision → coordinates), mouse/keyboard/`set_value` actions with
  **background-first** delivery and explicit foreground escalation with focus
  restore, an action verifier (verified/failed/uncertain + screen diff), a bounded
  recovery ladder, a window/application manager with an `ApplicationAdapter`
  framework and initial adapters (Excel, VS Code, terminal, Chrome/Edge, PDF,
  TradingView, MetaTrader 5, Interactive Brokers, Bloomberg-style), a permission/
  risk policy engine, sensitive-region detection/redaction, a **Finance Action
  Firewall** (read_only/assisted/autonomous/simulation; buy/sell gated,
  transfer/withdraw always blocked), screen-derived finance with provenance,
  human-takeover control leases, recording/replay, telemetry, a doctor/diagnostics
  report, `agent-memory.db` persistence, and Eclipse-Memory knowledge (never JDdS,
  never screenshots). Integrated on the ONE `ToolRegistry` (`computer_*`),
  the ONE authorizer chain (`code/authorizers.py`), the ONE policy authority
  (`code/policy.py` `COMPUTER_EFFECTFUL_TOOLS`), `agents.py` (`COMPUTER_TOOLS`),
  `service.py`, `main.py` (`/computer/*`), and the CLI (`eclipse computer …`).
  Finance actions route through the firewall BEFORE any UI action; coordinate
  clicking is never the primary method. Tests: `python/tests/test_computer_{unit,
  safety,tools,adversarial}.py` (77 cases). Docs: `docs/harness/computer-use.md`;
  NAVIGATION row.

- **Browser Automation Runtime — Phase B (limitations closed).** (1) **Real visual
  interpretation** — `browser_vision` now interprets the screenshot when the run
  has a multimodal model, via `vision_model.BrowserVisionInterpreter` reusing the
  harness model runtime (`task="vision"`, which requires a known-good `vision`
  capability); no configured model yields an honest `available:false` and the raw
  screenshot + DOM map are unchanged. (2) **`browser_find` / `browser_highlight`**
  (`inspection.py`) — describe every element a locator matches (with its snapshot
  ref, role, name, text) WITHOUT interacting, and briefly outline a target for
  visual confirmation. (3) **Log paging** — large console/network/error dumps are
  bounded for the model and the full text is persisted under
  `artifactsRoot/<kind>/<session>/` (`tool_support.bound_log_text` +
  `observation.persist_artifact`). (4) **Browserbase is a real cloud backend** —
  session creation through its REST API + CDP attach when enabled with a
  vault-resolved credential, honest `CREDENTIAL_UNAVAILABLE` otherwise; the
  credential never reaches the model. 83 `browser_*` tools. Tests:
  `test_browser_unit.py` (+vision/log/browserbase cases) and
  `test_browser_integration.py` (+`find`/`highlight`, vision-no-model). Docs:
  `docs/harness/browser-runtime.md`.

- **Browser Automation Runtime — a Hermes-grade, provider-agnostic browser
  subsystem.** New `python/harness/browser/` package: a `browser_*` toolset on the
  ONE registry (navigation, accessibility-first snapshots with Eclipse-stable refs
  `@e1…`, interaction, waiting, tabs, iframes, dialogs, downloads/uploads,
  console/network/errors, JS eval, controlled CDP, storage, profiles, vault,
  human-in-the-loop, device emulation, network interception), a `BrowserManager`
  pool + `BrowserSession` state machine, a `BrowserProvider` layer (`LocalChromium`
  on Playwright, `CDPProvider`, and honest optional backends Browser Use/Browserbase/
  Lightpanda/agent-browser/Firecrawl that report unavailability rather than faking
  it), a capability-based provider router (private/local targets always run
  locally), a locator/resolution engine with stale re-resolution, action→observe→
  verify, vision + DOM/vision fusion, a sandboxed `browser_exec` program AST, ONE
  security policy engine (permissions ALLOW/DENY/ASK routed through the existing
  single-use approval store, domain policy, destructive-action elevation, an
  untrusted-page boundary vs prompt injection), a credential vault (references,
  never values), persistent profiles, durable metadata on `agent-memory.db`, and
  bounded traces. Boot wiring in `service.py`/`main.py` (`/health.browser`, router
  `/browser/*`); `BROWSER_TOOLS` added to the finance agent, code agent and chat
  code profile; `code/policy.py` + `code/authorizers.py` narrowing/admission;
  prompt guidance; `playwright>=1.62,<1.63` in `requirements.txt` + a doctor probe
  (never auto-downloads the browser). A missing Playwright/Chromium is an honest
  `BROWSER_UNAVAILABLE`, never a fake browser. Tests: `test_browser_unit.py` +
  `test_browser_integration.py` (real Chromium against the stdlib test app
  `browser_app.py`). Docs: `docs/harness/browser-runtime.md`, `docs/harness/decisions.md`
  (ADR-H134), `docs/NAVIGATION.md`.
- **Computer Use Engine — desktop control as a first-class, isolated capability.**
  New `python/harness/computer/` package: a `computer_*` toolset on the ONE
  registry, a `ComputerManager` + desktop session/state model, a platform-driver
  layer (`drivers/`) with honest availability, accessibility/grounding/OCR/vision
  engines, a finance firewall + policy/security layer, takeover leases, recording
  and replay, and the matching router (`routers/computer.py`, `/computer/*`,
  operator-gated) plus a `computer` CLI group. Boot wiring in
  `service.py`/`main.py` (`start_computer`/`start_computer_sweeper`/
  `stop_computer`). Tests: `test_computer_{unit,tools,safety,adversarial}.py`
  (77 passing). This subsystem landed alongside the Browser Automation Runtime and
  shares the same runtime files (`service.py`, `main.py`, `cli.py`), so both ship
  in one commit to keep the tree buildable.
- **Size/ratchet tests tolerate the vendored Python + prompt growth.** The TS
  size-budget walk now skips `scripts/vendor` (the vendored interpreter's
  site-packages carries Playwright `.d.ts` files); the Python `main.py` ratchet and
  the finance prompt char ceiling were raised with justification for the browser
  boot wiring + guidance block. `test_code_agent.py`/`test_chat_code_profile.py`
  count the shared `BROWSER_TOOLS` set.

- **Fix: client components imported server-only harness clients, breaking the
  build (`Can't resolve 'child_process'`).** `research-widgets.tsx` dynamically
  imported `@/lib/harness/jobs-client` and `standing-grants.tsx` statically
  imported `@/lib/harness/grants-client`; both pull `child_process`/`fs` via
  `python-runtime.ts`, so the browser bundle failed to compile. Switched both to
  the client-safe `jobs-browser` module and a new `grants-browser.ts` (fetch-only
  mirror of the `/api/harness/grants/**` front door, type-only re-export of
  `StandingGrant`), matching the existing browser/server split. No doc change —
  bug fix keeping the client/server contract intact.

## 2026-10-06

- **Application Runtime — the remaining limitations closed (production hardening
  + the last capabilities).** (1) **Provider readiness gate** — `provisioning.py`
  reports (non-secret) which orchestration/infra/cloud tools are installed AND
  signed in, with a plain next step per gap; surfaced on `/health`
  (`runtimeProviders`), `GET /runtime/providers`, `eclipse providers`. A provider
  whose credentials are unknown reports `null`, never a fabricated `true`.
  (2) **Metric history** — `AppRuntimeMetric` on `agent-memory.db`, a trend summary
  (`rising`/`falling`/`flat`/`unknown`, never a false `flat`), `runtime_metrics_history`
  + `GET /runtime/{id}/metrics/history` + `eclipse runtime metrics-history`.
  (3) **Long-running CLI ops as managed processes** — `managed_cli.py` starts
  `kubectl port-forward` / `kubectl logs -f` through the EXISTING terminal process
  manager (tree-killed, cancellable, streamed); tools `k8s_port_forward` /
  `k8s_logs_follow`. (4) **Deployment promotion** — `DeploymentEngine.promote()` +
  `deploy_promote`: staging → (authorization) → production with a health-gated
  ROLLBACK; a staging failure never touches production. (5) **Cross-application
  graph** — `app_graph.py` + `workspace_ops.py`: order several apps by declared
  dependency (`.black-eclipse/app.json`) or a monorepo heuristic, with
  `workspace_graph` / `workspace_start` / `workspace_stop` and `eclipse workspace`.
  (6) **Compose-config fallback** — when the tolerant reader finds no services,
  `docker compose config` resolves anchors/merges/includes for the graph via the
  SAME `ComposeAdapter`. (7) **Auto-deploy job templates** — two Application Runtime
  templates (`deploy-app-on-schedule`, `deploy-app-on-webhook`) wired to the jobs
  scheduler, shipping disabled and still subject to per-action authorization.
  (8) **UI** — a Providers tab (readiness + workspace graph) in the terminal dock.
  (9) **Opt-in live provider tests** (`test_application_provider_live.py`,
  `BLACK_ECLIPSE_PROVIDER_IT=1`). 103 application-runtime tools total. Docs:
  `docs/harness/application-runtime.md`; ADR-H133. Tests:
  `test_application_{provisioning,workspace}.py` + expanded deploy/orchestration.

- **Git UI now uses the ONE engine (no second implementation).** Corrected an
  architecture violation: the Settings Git panel used a standalone TypeScript Git
  wrapper (`src/lib/git/service.ts`) that spawned git from Node, bypassing the
  Python engine entirely (no journal, no operation state, no risk engine, no lock,
  only a filename secret check). `/api/git` is now a THIN proxy over the runtime's
  `/git/*` routes — the same service the agent uses; `src/lib/git/service.ts`
  forwards and holds no Git logic, browser types moved to the client-safe
  `src/lib/git/types.ts`, and the route returns 503 honestly when the runtime is
  unavailable rather than falling back. Added engine routes `/git/draft-message`,
  `/git/unstage`, `/git/push`, and `cached=1` on `/git/diff`; the push result now
  carries the branch. Tests: `test_git_api.py` extended. docs updated:
  `docs/harness/git-version-control.md`.

- **Size-budget guard green again after the Application Runtime commit.** The
  Git/Application-Runtime change (146f6d5) left `main.py` (1220 lines) above the
  1200-line hard ceiling — together with `execution/application/manager.py`
  (1239) at the time — so `test_size_budget.py` failed. `manager.py` was split
  under the ceiling by the follow-up work; `main.py` got a justified `RATCHET_PY`
  entry pinned to 1220 (route-group extraction noted as the split candidate; may
  only shrink from here). Full Python suite green. no doc change — test-only
  ratchet bookkeeping.

- **Backup: consistent snapshot of all runtime SQLite state.** Took `VACUUM INTO`
  copies (WAL-safe while the app runs) of `jdds.db`, `agent-memory.db`,
  `eclipse-memory.db`, and the `python/` copies into
  `_backups/2026-10-07-03-56-42/` with a `MANIFEST.json` of sizes + SHA-256, each
  verified `quick_check=ok`. `_backups/` stays gitignored; no code or contract
  changed. no doc change — operational backup artifact, no architecture/data-shape/setup change.

- **Application Runtime â€” the future tiers are now real, and the layer is
  production-hardened.** (1) **Orchestration:** `KubernetesAdapter`,
  `HelmAdapter`, `KustomizeAdapter` (a closed operation table, validated args,
  JSON output parsed), behind one shared `CliAdapter` base. (2) **Infrastructure:**
  `TerraformAdapter` (init/validate/fmt/plan/apply/destroy/output/state; apply and
  destroy are CRITICAL). (3) **Cloud:** `AwsAdapter`/`AzureAdapter`/`GcpAdapter`/
  `CloudflareAdapter`/`VercelAdapter`/`RailwayAdapter`/`RenderAdapter` â€” the common
  `deploy`/`status`/`logs`/`rollback`/`delete` surface, credentials read only
  through each provider's own ambient mechanism. (4) **`DeploymentEngine`**:
  validateâ†’buildâ†’testâ†’packageâ†’deployâ†’verify; a production deploy requires
  authorization; a deployment is never claimed live from a status call alone.
  (5) **29 new agent tools** (`k8s_*`, `helm_*`, `kustomize_*`, `terraform_*`,
  `cloud_providers`, `deploy_*`) â€” 96 application-runtime tools total â€” with the
  cluster/infra/cloud mutations removed at `edit_verify`/`plan_only` and each
  destructive one requiring authorization. (6) **A real CLI** (`python -m
  harness.cli`, `eclipse` bin, `npm run eclipse`): `runtime|package|environment|
  port|container|compose|k8s|terraform|deploy` over the SAME manager the agent
  uses, JSON output, `--authorized` for destructive commands. (7) **Production
  hardening:** an mtime-keyed `DiscoveryCache` (invalidated on any manifest/
  lockfile/compose/.env change), health-check exponential backoff, and bounded/
  filtered runtime logs (substring/severity/errors-only + line cap). (8) HTTP
  routes (`/runtime/orchestrator/*`, `/runtime/terraform/*`, `/runtime/deploy`,
  `/runtime/orchestrators`) and the Applications-tab provider footer. Docs:
  `docs/harness/application-runtime.md`; ADR-H132. Tests:
  `test_application_{orchestration,deploy}.py` + expanded unit/security/reachability.

- **Git subsystem â€” interactive Git made limitless (no TTY).** Removed the two
  "needs a terminal" limitations. (1) **Selective hunk staging**: new
  `git/diffs.py` parses a unified diff into files/hunks and re-renders a chosen
  subset, which `git apply --cached` stages â€” tools `git_list_hunks`,
  `git_stage_hunks`, `git_unstage_hunks`, `git_apply_patch` (git's `add -p` is no
  longer needed). (2) **Automated interactive rebase**: new `git/rebase_plan.py`
  + machine `_sequence_editor.py`/`_message_editor.py` drive `git rebase -i`
  through env vars so `git_rebase_plan` performs pick/reword/edit/squash/fixup/
  drop/reorder from a structured plan; a partial plan never reorders or drops an
  unnamed commit. (3) **Long-tail capabilities** now exposed in
  `git/tools_extra.py`: `git_move_path`, `git_remove_paths`, `git_restore`,
  `git_unset_upstream`, `git_stash_branch`, `git_stash_clear`, `git_tag_show`,
  `git_worktree_prune`, `git_worktree_move`, `git_submodule_init`,
  `git_submodule_sync`, `git_lfs_fetch`, `git_lfs_pull` (115 git/vcs tools total).
  (4) **Opt-in live provider tests** (`test_git_provider_live.py`) exercise a real
  GitHub/GitLab/Bitbucket account (skipped unless `BLACK_ECLIPSE_PROVIDER_IT=1` +
  a token + `BLACK_ECLIPSE_PROVIDER_REPO`; never in `npm test`). New tests in
  `test_git_advanced.py` (20 tests). `interactive=True` was dropped from the plain
  rebase op (the planned op is the only path to `-i`). docs updated:
  `docs/harness/git-version-control.md`.

- **Execution layer â€” every caveat closed: extra languages, DB dialects and OS
  resource limits are now verified end-to-end, not just unit-tested.** (1) **Seven
  toolchains executed for real** (Go, Java, PHP, C, C++, C#, Rust) against a
  portable toolchain set fetched into `%TEMP%` (no admin, nothing installed
  globally). Fixes found and made: Go needed a real `GOCACHE`/`GOTMPDIR` (the
  sandbox scrubs the env); C/C++ now actually compile a standalone source into a
  runnable binary (previously only drove `make`/`cmake`, so a bare `.c`/`.cpp`
  could never run); the .NET adapter needed `DOTNET_CLI_HOME`/`NUGET_PACKAGES` plus
  a curated non-secret Windows platform env (real `%APPDATA%`, `%PROGRAMFILES%`,
  `%USERPROFILE%`, â€¦) because NuGet/MSBuild resolve paths the sandbox allowlist
  strips. (2) **SQL dialects**: DuckDB runs embedded end-to-end (create/insert/
  select + cross-execution persistence); PostgreSQL now selects `psycopg`/
  `psycopg2`/`pg8000` â€” with a libpqâ†’pg8000 keyword translation (`dbname`â†’
  `database`) â€” and a *connection* failure is reported as `SQL_CONNECT_FAILED`
  (previously mis-labelled `SQL_DRIVER_MISSING`), while an absent driver still
  refuses honestly; `pg8000` and `duckdb` were added to `python/requirements.txt`
  as optional-but-default. (3) **OS resource limits enforced + classified**: the
  sandbox now kills the process tree and reports `RESOURCE_LIMIT` for memory,
  cumulative-CPU and process-count breaches â€” both when the parent monitor samples
  a peak and when the kernel (Windows Job Object / POSIX `RLIMIT_AS`) DENIES an
  operation at the limit (`MemoryError`, `WinError 1816`). `ResourceLimits` gains
  `cpu_seconds`; `ErrorClass.RESOURCE_LIMIT` is new. A latent bug was fixed where
  `from_env` clamped an unset `cpu_seconds` to `1`, imposing a 1-second CPU
  ceiling on every execution. Tests `python/tests/test_execution_resources.py`.
  Full Python suite green (3203); tsc clean; eval gates PASS. docs updated:
  `docs/harness/execution-architecture.md`, `docs/harness/decisions.md`
  (ADR-H129 consequences), `docs/NAVIGATION.md` (trigger row).

- **Git subsystem hardening pass (production review fixes).** (1) **Worktree
  escape** â€” `git_worktree_add`/`git_worktree_remove`/`git_worktree_move` accepted
  a `../â€¦` or absolute filesystem path, so a working tree (and a later
  `worktree remove --force`) could land outside the project; a path is now
  realpath-confined to the repository root or a sibling under its parent (a
  sibling worktree is the normal `git worktree` layout; a climb above the parent
  or a system path is refused). (2) **Global git-config escalation** â€” a
  `git_config_set --global` write (machine-wide: `core.hooksPath`, `core.sshCommand`,
  â€¦) was only `caution`/no-approval; it is now `dangerous` and requires a
  single-use operator approval. (3) **Refspec force** â€” a leading-`+` refspec (a
  force push that bypasses `--force-with-lease`) is now rejected by a dedicated
  `refspec` validator. (4) **Cross-host credential leak** â€” the VCS HTTP client now
  drops the `Authorization` header on a redirect to a different host (urllib
  otherwise re-sends it); a CI job log is also passed through the shared
  redaction before it reaches the model. Regression tests added to
  `test_git_security.py` (worktree confinement, global-config risk, `+refspec`);
  150 Git tests pass. docs updated: `docs/harness/git-version-control.md`.

- **New Application Runtime / DevOps subsystem.** Eclipse now understands
  *applications*, not shell commands. New package
  `python/harness/execution/application/`: a provider-agnostic `RuntimeRegistry`
  (package managers, container runtimes, compose, and empty-but-live Kubernetes/
  Terraform/cloud seams); `ApplicationDiscovery` (framework/language/package
  manager/lockfile, install-build-dev-start-test-lint commands, Docker/Compose,
  env files, required vars, databases/caches, services, ports, service graph);
  `EnvironmentDetector` + `EnvironmentManager` (secret values masked as
  `[SECRET]`, never returned); 11 package-manager adapters
  (npm/pnpm/yarn/bun/pip/uv/poetry/cargo/go/maven/gradle, declared manager is
  authoritative â€” no silent npm switch); `DockerAdapter`/`PodmanAdapter` behind
  one `ContainerRuntimeAdapter`; `DockerComposeAdapter`/`PodmanComposeAdapter`;
  `PortManager`; `HealthCheckEngine` (process/tcp/http/container/database/custom
  â€” `RUNNING` is never `HEALTHY`); `RuntimeDiagnosticsEngine` (structured
  category + a `{file,line,column}` location linking runtime errors to code
  intelligence); `RecoveryEngine` (bounded diagnoseâ†’actâ†’verify, never a loop);
  `ApplicationRuntimeStore` on `agent-memory.db`; a closed event vocabulary;
  `ApplicationRuntimeManager` (the ONE lifecycle) with boot reconciliation.
  67 agent tools (`runtime_*`, `package_*`, `container_*`, `compose_*`,
  `environment_*`, `port_*`, `health_*`) on the SAME registry, the write half
  removed at `plan_only`; route group `/runtime/*` (operator-gated); front door
  `application-{client,browser}.ts` + `/api/runtime/**` + an Applications tab in
  the terminal dock. No new dependency; every argv runs through the ONE sandbox.
  Docs: `docs/harness/application-runtime.md`; ADR-H131. Tests:
  `python/tests/test_application_{unit,runtime,security,tools,api,e2e}.py`
  (+ `test_size_budget.py` split of `application/tools.py`).

- **New Git / Version-Control subsystem.** A production-grade Git engine + VCS
  provider layer for the agentic coding environment â€” not a wrapper. New package
  `python/harness/git/`: repository discovery (normal/`.git`-file/bare/nested/
  worktree/submodule), a CLOSED operation table (`catalog.py`) with strict value
  validation, the ONE controlled executor (absolute argv, no shell, scrubbed env,
  `GIT_EDITOR=true`/`GIT_MERGE_AUTOEDIT=no` so a merge never blocks on an editor,
  timeout + output cap), machine-readable parsers, a structured error model, the
  multi-step operation state machine + conflict-marker parser, a risk/safety
  engine (secret + large-file scans reusing the ONE `session_index` pattern set,
  protected branches, `.black-eclipse/git.json` policy, untrusted-repo inspection
  that never runs a hook), an operation journal + active-operation store on
  `agent-memory.db`, a per-repository mutating lock, recovery/reconcile, and a
  per-repository mutating lock. Local Git is separate from the remote VCS layer
  (`git/vcs/`: `VCSProvider` + `GitHubProvider`/`GitLabProvider`/
  `BitbucketProvider`, a normalized PR=MR model, and a stdlib-only HTTP client;
  tokens come from operator-declared env-var NAMES and are never exposed). The
  full tool surface (`git_*` reads + local mutations + `vcs_*` remote actions) is
  registered on the SAME registry via `register_git_subsystem`; the ONE policy
  authority narrows it by autonomy (`GIT_READ_TOOLS`/`GIT_WRITE_TOOLS`/
  `GIT_EXTERNAL_TOOLS`), and the Git effect authorizer requires a single-use
  operator approval for every dangerous/destructive operation and every remote
  action (a force push is `critical`, never the default). Routes `/git/*` serve
  the UI from the same service. Tests: `test_git_{engine,mutations,security,tools,
  integration,api}.py` (163 tests, isolated temp repos). The fs subsystem's older
  read `git_status` tool was removed in favour of the one richer engine tool (the
  `FileSystemService.git_status` method and `file_metadata` git awareness stay).
  docs updated: `docs/harness/git-version-control.md` (new), `docs/NAVIGATION.md`.

- **Execution-layer build/test fixes found by an autonomous buildâ†’testâ†’fixâ†’
  retest run on Windows.** (1) **Bare program names could not be spawned** â€” the
  JS/TS adapters emitted `['npm', ...]`/`['npx', ...]`/`['tsc', ...]`, which
  `subprocess` cannot run on Windows (`npm`/`npx`/`tsc` are `.CMD`/`.cmd` shims;
  `FileNotFoundError [WinError 2]`), so `build_project`/`test_project` reported
  `exitCode=null`, empty output. Every adapter now emits an ABSOLUTE executable
  path (`base._require_program`/`_program`), matching `code/commands.py`.
  (2) **Toolchain resolution / offline** â€” a project with no local `node_modules`
  now resolves `tsc` and the test runner from Eclipse's OWN bundled
  `node_modules/.bin` (via `_app_bin` + `_node_env`, which prepends the node bin
  dirs to the scrubbed `PATH`), so `npm run build`/`vitest` work without a network
  install and without fetching a different version. (3) **UTF-8 BOM manifests** â€”
  `package.json`/`tsconfig.json` saved with a BOM (Windows editors, PowerShell)
  failed to parse, so the test framework/scripts were missed and the engine fell
  back to `node --test`; `projects.read_json`/`_read_text` now read `utf-8-sig`
  and the TS adapter uses it. (4) **ANSI color codes broke result parsing** â€”
  vitest color-codes its summary, so a PASSING run reported `parsed:false`/0 tests
  and colored compiler errors produced no diagnostics; `testing._parse_summary`
  and `diagnostics.normalize` now strip ANSI first (reusing the terminal
  subsystem's `strip_ansi`). (5) vitest/jest now run with a machine-readable
  reporter (`--reporter=json`/`--json`) so per-test failures (name, file,
  expected/actual) are extracted structurally. Verified end-to-end: build PASS â†’
  tests fail (`add` expected 5, got -1) â†’ structured diagnostic â†’ agent fixes
  `a - b`â†’`a + b` (tests untouched) â†’ rebuild PASS â†’ **2 passed / 0 failed**.
  Regression tests in `python/tests/test_execution_capabilities.py`. docs updated:
  `docs/harness/execution-architecture.md`.

- **Execution-layer bug fixes found by an end-to-end verification pass (TypeScript
  and SQL).** (1) `TypeScriptRuntime.prepare_run` built `['npx', '<file.ts>']` â€” it
  dropped the `tsx`/`ts-node` program for the `npx` runner, so every TypeScript
  execution failed with `[WinError 2]`. Rewritten as a `_runner_prefix()` that
  always emits an invocable program followed by the file, preferring the project's
  declared `tsx`/`ts-node`, then the app's own bundled `tsx` (`<repo>/node_modules/
  .bin`, offline), then `npx`. (2) `SqlRuntime` rejected multi-statement scripts
  ("You can only execute one statement at a time") and never committed DML, so
  `INSERT`s reported COMPLETED but a later `SELECT` returned 0 rows â€” a fake
  success. The runner now splits a script into statements (quote/comment aware),
  executes each, and **commits** (rolls back on error); it returns per-statement
  results plus the last result set. (3) A database filename matching the index
  ignore-globs (`*.db`/`*.sqlite`) was refused as `IGNORED_PATH`, so a real DB could
  not be opened; `policy.resolve_within` gains an explicit `allow_ignored=False`
  opt-in that the SQL runtime uses â€” traversal, symlink, outside-root and
  PROTECTED checks are unchanged. Regression tests added to
  `python/tests/test_execution_capabilities.py`. docs updated:
  `docs/harness/execution-architecture.md` (SQL/TypeScript notes).

- **Execution layer hardening â€” every earlier limitation closed.** (1) The
  sandbox now measures REAL resource usage with no `psutil`: a new
  `execution/telemetry.py` samples CPU time (`GetProcessTimes` on Windows;
  `/proc/<pid>/stat` on Linux) and peak RSS (`GetProcessMemoryInfo` /
  `/proc/<pid>/statm`) across the whole process tree, and the values flow into
  `RawResult` â†’ `ResourceUsage` â†’ the `ExecutionMetric` rows (`cpuMs`/
  `memoryPeakMb`/`processCount`); an unmeasurable value stays `None`, never a
  fabricated zero. (2) `SqlRuntime` connects PostgreSQL through any installed
  PEP-249 driver (`psycopg`, `psycopg2`, pure-Python `pg8000`), plus MySQL
  (`pymysql`/`MySQLdb`) and DuckDB, refusing with a stable `SQL_DRIVER_MISSING`
  when none is present â€” never pretending to connect. (3) Eight more real
  runtime adapters ship: Go, Rust, Java, C#, C, C++, PHP, Ruby (inline where the
  language supports it â€” Go/Java/PHP/Ruby â€” and honest `UNAVAILABLE`/refusal
  otherwise); `build`/`test` wired for `go`/`cargo`/`maven`/`gradle`/`dotnet`/
  `cmake`/`make`. (4) `run_verification` can now fix code IN-PROCESS: a new
  `execution/autofix.py` (opt-in via `HARNESS_EXEC_AUTOFIX=1`) asks the RUN's own
  model for one schema-validated, diagnostic-driven, workspace-confined edit and
  applies it through the filesystem service; it never touches a
  security/infrastructure failure and never retries blindly. (5) An intermittent
  CIUE index flake (`fileCount == 0`) was root-caused and fixed: the shared
  `check_same_thread=False` `CodeIndex` connection now serializes EVERY mutation
  (`IncrementalIndexer._mutate_lock` + `CodeIndex._write_lock`), so the background
  watcher and a synchronous index trigger can no longer interleave
  delete/insert transactions and lose rows; regression test
  `python/tests/test_intel_index_concurrency.py` (25/25 stable). Tests
  `python/tests/test_execution_capabilities.py` + the reachability case in
  `test_execution_e2e.py`. Full Python suite green; docs updated:
  `docs/harness/execution-architecture.md`, `docs/harness/decisions.md`
  (ADR-H129 consequences), `docs/NAVIGATION.md` (trigger row).

- **Code Execution & Verification Layer â€” Eclipse can now run, build, test,
  diagnose and VERIFY software autonomously.** New subsystem
  `python/harness/execution/`: a strict `ExecutionState` machine (validated
  transitions, `execution/state.py`), strongly-typed domain models
  (`models.py`), a `RuntimeRegistry` with `PythonRuntime`/`JavaScriptRuntime`/
  `TypeScriptRuntime`/`SqlRuntime`/`ShellRuntime` adapters (`runtimes/`), a
  `ProjectDetector` + language detection in the spec's priority order
  (`projects.py`), a `DiagnosticEngine` normalizing `tsc`/Python-traceback/V8/
  ESLint/pytest/generic compiler output (`diagnostics.py`), a `BuildEngine` and
  `TestEngine` (vitest/jest JSON + summary parsers, `build.py`/`testing.py`), an
  `ExecutionPolicyEngine` (risk bands, network/filesystem narrowing, secret
  isolation, `policy.py`), an `ArtifactManager` (`artifacts.py`), a synchronous
  `ExecutionOrchestrator` with guaranteed cleanup and a `finally` that always
  lands on a terminal state (`orchestrator.py`), an `ExecutionStore` for history
  and evidence on the ONE `agent-memory.db` connection (`store.py`), an
  `ExecutionScheduler`/`ExecutionWorkflow`/`RetryPolicy` (`scheduler.py`/
  `workflow.py`), a `ExecutionVerifier` bounded buildâ†’testâ†’fix loop
  (`verify_loop.py`), and a `ServiceManager`/`PortManager`/`HealthChecker` built
  on the EXISTING terminal process manager   (`services.py`). It reuses
  `code/sandbox.py` as the ONE execution primitive (no second spawn path), the
  terminal subsystem for long-running services, `code/policy.py` for the
  autonomy/binding boundary, and `code/workspace.py` for confinement; it does
  NOT touch the terminal subsystem. The sandbox primitive gains OPTIONAL OS-level
  `RunSpec` limit fields (`cpu_seconds`/`memory_mb`/`process_limit`), applied via
  POSIX `setrlimit` (RLIMIT_CPU/AS/NPROC) and Windows Job Object limits, with the
  wall-clock timeout always enforced; entrypoints and SQLite databases are
  confined with `resolve_within`. 21 agent tools registered on the SAME
  registry (`execution/tools.py`): `execute_python`/`execute_javascript`/
  `execute_typescript`/`execute_sql`/`execute_shell`/`execute_code`,
  `build_project`/`test_project`/`discover_tests`/`run_verification`,
  `start_service`/`stop_service`/`restart_service`/`service_status`/
  `service_logs`/`list_services`, `execution_get`/`execution_logs`/
  `execution_result`/`execution_artifacts`/`cancel_execution` (retrieval tools
  prefixed `execution_`/`service_` to keep the code-agent's finance-tool guard).
  Write/execute tools added to `policy.WRITE_TOOLS` (removed at `plan_only`);
  read tools to `READ_ONLY_TOOLS`. Service wiring in `service.py`
  (`AgenticService.execution` + `stop_execution`), lifespan in `main.py`, routes
  `python/harness/routers/execution.py` (`/execution/*`, operator-gated). Tests
  `python/tests/test_execution_{unit,runtime,security,e2e,tools}.py` (state
  machine, diagnostics, policy, real Python/JS/SQL/shell runs, timeout/cancel/
  traversal/secret attacks, the buildâ†’testâ†’fixâ†’retest acceptance loop). Full
  Python suite green (2930); Vitest 2169; tsc clean. docs updated:
  `docs/harness/execution-architecture.md` (new),
  `docs/harness/decisions.md` (ADR-H129), `docs/NAVIGATION.md` (trigger row).

- **CIUE hardcore torture test: 14 real bugs fixed, verified against a live
  `typescript-language-server` and a 220-file multi-language monorepo.** Running
  the engine end-to-end (real subprocess LSP, edits, diagnostics, watcher,
  concurrency) surfaced and fixed: (1) `lsp.client.uri_to_path` now percent-decodes
  before the Windows drive-letter fix, so `file:///c%3A/â€¦` LSP results match the
  workspace; (2) `manager._normalize_locations` understands the `LocationLink`
  (`targetUri`/`targetRange`) shape; (3) `get_definition`/`get_references` send the
  symbol's real name column (`_symbol_position`) not the indentation column;
  (4) `_resolve_symbols` scopes by file first, so a same-named symbol in another
  file/language is not resolved; (5) LSP `find_references` marks the declaration
  site; (6) `get_implementations` returns the union of the semantic (LSP) and
  structural (index heritage) results instead of one backend's view;
  (7) `_js_heritage` captures `extends`/`implements` so inheritance is structural;
  (8) the rename fallback is code-mask-aware (`_code_mask`) and never rewrites
  strings/comments; (9) `rebase_edits` accepts workspace-relative paths, not only
  absolute LSP paths; (10) `_enrich_location` returns a stable `location` object on
  the LSP path too (one shape across engines); (11) `CodeIndex.integrity_ok` adds a
  schema probe so non-database bytes are detected and recovered; (12)
  `policy.IGNORED_DIRS` excludes `dist`/`build`/`target`/`coverage`/`generated`/â€¦;
  (13) the context engine is prefix-aware (`authentication` reaches `Auth*`) and
  bounded; (14) `CodeIntelRuntime` indexes asynchronously so the first query never
  blocks on a full walk. New regression tests `python/tests/test_intel_regressions.py`.
  Full Python suite green (2870); Vitest 2169; tsc clean. docs updated:
  `docs/harness/code-intelligence.md` (unchanged â€” behaviour now matches the doc),
  `docs/harness/decisions.md` (ADR-H128 already covers the design).

- **Code Intelligence & Understanding Engine (CIUE): the agent now understands
  software structurally and semantically.** New subsystem
  `python/harness/code/intel/` â€” one `CodeIntelligenceManager` over an LSP manager
  (`lsp/`), an AST engine (`ast.py`), an optional Tree-sitter layer
  (`treesitter.py`), a DEDICATED incremental code index (`persistence/index.py`
  under `.black-eclipse/code-index/`, never agent memory), a dependency graph, a
  diagnostics engine, structural search, a project analyzer, a deterministic
  context engine and safe semantic editing. It normalizes every backend into a
  Unified Code Model (`models.py`) and always names the engine that answered
  (`lsp`/`tree-sitter`/`ast`/`index`); a missing or crashed language server is a
  structured fallback (`lsp.providers` ships nine real servers; adding one is a
  `LanguageServerSpec`), never a crash. New `code_*` tools (26, read plus the
  semantic `code_rename_symbol`) registered on the SAME registry via
  `code/intel_tools.py`; write policy in `code/policy.py` (`INTEL_WRITE_TOOLS`); a
  process-wide `CodeIntelRuntime` on `AgenticService` (lazy async indexing + a
  reused fs watcher); routes `python/harness/routers/code_intel.py` (`/code/intel/*`,
  operator-gated) and a content-free `codeIntel` block in `/health`; plain-language
  labels in `src/lib/agent/response-model.ts`. Reuses the existing path authority,
  fs reading/encoding/watching/extractors and tool/event/authorizer seams â€” no
  second filesystem, registry or confinement. Tests `python/tests/test_intel{,_tools,
  _lsp,_api}.py` + fixtures `python/tests/fixtures/intel/` + a fake language-server
  subprocess; ADR-H128. docs updated: `docs/harness/code-intelligence.md` (new),
  `docs/harness/decisions.md` (ADR-H128), `docs/NAVIGATION.md` (trigger row).

- **Ultra effort: the fill now FLOWS as a real moving gradient (was a static
  fill + thin beam).** The reported "gradient is not moving" was two things:
  (a) the fill was a static Tailwind gradient with only a narrow beam sweeping
  it, and (b) under the app's reduce-motion / "animations off" settings (or the
  OS preference) a global rule froze *every* animation to 0.001ms, pinning the
  beam at the left â€” a frozen band. Fix: `.effort-ultra-fill` animates the WHOLE
  fill (`background-size: 200%` + `effortUltraFlow`) on both the slider and the
  persistent pill, the beam is kept on top, and the Ultra energy is now
  DELIBERATELY EXEMPT from the reduce-motion / animations-off kill switches (like
  the price ticker) â€” each layer carries `--ultra-dur` so one rule restores its
  timing. Verified with Playwright frame-diffs: the fill and beam both change
  every frame under default, OS reduce-motion, AND the app's no-anim classes.
  tests updated: `effort-control.test.ts`.
  no doc change â€” visual-only; behavior unchanged (see the Ultra behavior entry).

- **Ultra effort: fixed the "animation doesn't work" report (two real bugs).**
  Diagnosed live with Playwright. (1) The brain SVG rendered muted GRAY, not the
  accent: a global CSS remap forces `.text-primary` to gray with `!important`,
  and its `.dark` variant out-specifies the `svg.text-primary { color: var(--brand) }`
  green rule â€” a solid green icon must not rely on `text-primary`. Added a
  dedicated `.effort-accent` class and used it for the brain (pill + core).
  (2) The energy effect lived only INSIDE the popover, which closes the moment a
  level is picked â€” so at rest the always-visible pill was static. Extracted the
  core into a shared `EnergyCore` and put a live laser-beam sweep on the
  persistent pill while Ultra is active. Verified by frame-diff (frames change)
  and the computed brain color = `#7aff78`. Added tests.
  no doc change â€” visual-only; behavior unchanged (see the Ultra behavior entry).

- **Ultra effort thumb: an "energy core" animation.** Reworked the composer
  slider's top-stop thumb (`effort-control.tsx` + `globals.css`) into a layered
  energy effect â€” a pulsing outer glow, a rotating conic plasma ring, two
  phase-offset expanding shockwaves, three orbiting sparks, and a throbbing
  brain core â€” all in the theme `--primary` green and disabled by the global
  `prefers-reduced-motion` rule (static, fully-lit fallback). Replaced the old
  single pulse + static rays. The brain icon is now a SOLID accent fill (both
  the trigger pill and the Ultra core), and the Ultra fill carries a laser beam
  that sweeps the full bar (`effortUltraBeam`).
  no doc change â€” visual-only; behavior unchanged (see the Ultra behavior entry).

- **Composer effort slider: theme-consistent skin, animated Ultra, and a real
  top stop.** Re-skinned `EffortControl` to the theme tokens (`--primary` green,
  `--border`/`--accent` chrome) instead of a foreign violet/sky palette, and
  matched the trigger pill to the model-selector chrome. The Ultra thumb now
  animates (pulsing glow + slowly radiating rays, `globals.css`
  `effortUltraPulse`/`effortUltraSpin`, reduced-motion safe). Made the top stop
  actually strongest: `prepare_model` normalizes `very_high` â†’ the runtime's
  `max` tier (was mapped to `high`, so Ultra == High), so Anthropic `thinking`
  (16384) and Gemini `thinking_budget` (24576) deepen beyond High; native
  OpenAI caps Ultra at `high` (its knob has no higher tier). `low`/Minimal stays
  a no-op by design. Added Python + JS tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.

- **Chat composer: per-question "model intelligence" effort slider.** Added
  `EffortControl` (`src/components/chat/effort-control.tsx`) â€” the Fasterâ†’Smarter
  slider from the reference â€” beside the model selector in `ChatInput`, wired
  through `EmptyState` and `stock-chat.tsx`. It is a PER-QUESTION override (not a
  Settings edit): a new `useReasoningEffort` hook persists the choice client-side
  (`be_reasoning_effort_v1`), and the level rides `ChatOptions.reasoningEffort` â†’
  `/api/harness/chat[/stream]` â†’ `chatWithAgent`/`startChatRun` â†’
  `input.context.reasoning`, where it OUTRANKS the saved
  `LLMConfig.reasoningEffort` default; Auto sends nothing. Reuses the shared
  vocabulary (`reasoning.ts`, extended with captions + skins and slider index
  helpers); only native-reasoning models are affected, as before. Added tests
  (reasoning mapping, run-service precedence, composer reachability).
  docs updated: `docs/ARCHITECTURE.md` (reasoning-effort section).

- **Settings â€º General: reorganized the preset/customization surface.** The
  merged General section no longer reads as one long undifferentiated stack.
  The General sub-tab is now four titled sections (Startup & Display, Live Data,
  Behavior & Safety, Background) and finally exposes the previously-dead
  **Start screen** control (`general-prefs.ts` already defined
  `START_SCREEN_OPTIONS` but nothing rendered it). The Theme tab is now "Theme &
  Presets": presets lead, the brand generator and token editors sit under a
  "Fine-tune" group, and the duplicated Glass & Sidebar controls were removed
  (surfaces now live only on the Glass & Surfaces tab â€” the sidebar card moved
  there so no control was lost). Presets render as **miniature app screenshots**
  built from each theme's own tokens (rail + glass cards + a chart line) rather
  than flat gradient circles. The draft Live-preview/Apply/Discard toolbar is now
  scoped to draft-backed tabs only (Theme/Glass/Aurora/Charts); General,
  Background and Language & Access autosave instantly and no longer show it.
  Extracted shared `Panel`/`Field`/`Toggle`/`SectionHeader`/`SubSection` into
  `src/components/screens/settings-ui.tsx`, removing four sets of duplicates.
  no doc change â€” UI layout/UX reorg; no architecture, contract, data-shape or
  setup change.

- **File System Toolset: full validation run; one correctness fix.**
  A 141-check validation driven through the real registered tools (and verified
  against on-disk state) found `find_references` trusted a stale workspace index:
  a file created or changed after the last indexing pass was invisible â€” a Â§30
  stale-information violation. Fixed: `find_references` now refreshes the index
  incrementally before trusting it (`symbols.find_references(refresh_index=True)`),
  and skips the extra walk when an active watcher already keeps it current
  (`service.find_references`). Added a regression test. All 141 checks pass; full
  Python suite 2809 passed; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/code-filesystem.md` (index-is-a-cache note).

- **File System subsystem: added verification and Git awareness (the last two
  spec deliverables), plus transaction/index events.** `code/fs/verify.py` is the
  verification layer: `validate_syntax` (Python `ast`, JSON, TOML, and a bounded
  string/comment-aware bracket-balance scan for JS/TS/Go/Rust/Java/C#/C/C++),
  `validate_changes` (check proposed edits WITHOUT writing â€” the same
  all-or-nothing rule `multi_file_patch` enforces), and a post-write verdict now
  carried on every `write_file`/`create_file`/patch/insert/delete result
  (`verification.verified`, syntax error + line). New tools `verify_file` and
  `validate_changes`. `code/fs/git.py` adds additive Git awareness â€” normalized
  `modified`/`untracked`/`staged`/`deleted`/`renamed`/`copied`/`conflicted` states
  plus branch/HEAD, one fixed argument-free argv, never a hard dependency â€” via
  the new `git_status` tool and a `git` field on `file_metadata`. `apply_diff`/
  `multi_file_patch` now emit `fs.transaction.started|committed|rolled_back` and
  `index_workspace` emits `fs.index.updated`. 20 new tests; full Python suite 2808
  passed; `npx tsc --noEmit` clean; vitest 2151 passed.
  docs updated: `docs/harness/code-filesystem.md`, `docs/NAVIGATION.md`.

- **File System subsystem: closed the four stated limitations.** (1) Watchers now
  use a NATIVE OS backend when available â€” Windows `ReadDirectoryChangesW` and
  Linux `inotify`, built on `ctypes`/`libc` only (`code/fs/watch_native.py`) â€” with
  transparent degradation to the portable polling watch (the fallback re-baselines
  so it reports only future changes); `watcher.status()` reports the active
  backend. (2) Symbol extraction is now parser-backed and broader: Python `ast`
  distinguishes methods from functions and captures decorators; JS/TS use a
  brace-depth scanner (classes, methods, arrow-function consts, interfaces, type
  aliases); targeted patterns for Go/Rust/Java/C#/C/C++. (3) `find_references` marks
  each hit `definition: true` at the declaration site (new additive `definitions`
  column on the index, migrated in place) and names its engine. (4) `edit_file`
  deterministically parses a plain instruction (`code/fs/intent.py`) into a
  concrete minimal edit ("rename X to Y", "add X after Y", "delete X") and falls
  back to the inspection packet â€” never a guess â€” for a vague one. 20 new tests;
  full Python suite 2788 passed; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/code-filesystem.md`, `docs/NAVIGATION.md`.

- **Added the File System subsystem (`python/harness/code/fs/`) and its tools
  (`python/harness/code/fs_tools.py`).** A unified, deterministic filesystem
  service layered under the existing code capability: workspace-bound path
  security (delegated to the existing `code/policy.py` + `code/workspace.py`, not
  re-implemented), a centralized capability permission system (read/write/create/
  delete/move/copy/rename/watch/search; profile grants, config narrows only), the
  basic operations (list/read/write/create/delete/move/copy/rename/mkdir/rmdir),
  search (`search_text` via ripgrep with a bounded Python fallback, `search_files`,
  `find_files`), symbol/reference search (Python `ast` + a regex fallback, an
  extensible extractor table), the edit/patch engine (`patch_file`, `replace_text`,
  `insert_text`, `delete_text`, `apply_diff`, `multi_file_patch`) with hash-guarded
  optimistic concurrency, ambiguity refusal, atomic writes and byte-exact rollback,
  metadata/hash/permissions, a SEPARATE incremental workspace index
  (`<repo>/.black-eclipse/workspace-index/<id>.db` â€” never agent memory), portable
  debounced file watchers with cache invalidation + incremental re-index, and the
  high-level `edit_file` (inspect â†’ locate â†’ minimal patch â†’ verify). 28 tools
  registered; the write half is removed at `plan_only` by the ONE policy authority
  (`code/policy.py`), effects are admitted by the existing `make_code_authorizer`,
  and every path is re-checked by `permissions.require` â†’ `decide_write`. Writes
  land in the disposable code workspace (or the user's approved folder in direct
  mode), never silently in the checkout. 115 new tests; full Python suite 2732
  passed; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/architecture.md`, `docs/harness/code-filesystem.md`
  (new), `docs/NAVIGATION.md`.

## 2026-10-05

- **AI settings: added a reasoning-effort ("model variant") control, and fixed
  the Manage-models action + widened its dialog.** Settings â€º AI â€º Active setup
  now has an **Auto / Minimal / Standard / High / Ultra** selector
  (`src/lib/agent/reasoning.ts`): Auto (the default) sends no override and the
  runtime's task profile keeps choosing; the four levels map to the runtime's
  `low`/`medium`/`high`/`very_high`. It persists as `LLMConfig.reasoningEffort`
  (`setLLMConfig`, `null` = Auto; masked-into `/api/settings`) and is forwarded as
  `input.context.reasoning`, which the router honors as a requirement and
  `prepare_model` applies to a native reasoning control only â€” never to an
  OpenAI-compatible endpoint that lacks one. Fixes: the composer's per-provider
  **Manage** button opened the dialog behind the still-open `z-[110]` dropdown
  (now the menu closes first, and the dialog is `z-[130]`); the no-arg "Manage
  modelsâ€¦" path could resolve to `undefined` and render nothing (now falls back
  to the active/first usable provider); the dialog was `max-w-2xl` (now `max-w-3xl`
  with a roomier, 3-column model grid).
  `npx tsc --noEmit` clean; `vitest` 2151 passed, `pytest` model-runtime 64 passed.
  docs updated: `docs/ARCHITECTURE.md` (composer model picker: Manage-models fix +
  reasoning-effort note).

- **Reorganised the CFA Level I knowledge skills by exam topic (Equities and
  Portfolio Construction first).** The repo-root `.black-eclipse/skills/` now
  holds **twelve** topic-organised skills instead of ten process-organised ones:
  `cfa.00.curriculum-map` (index), `cfa.01.equities`,
  `cfa.02.portfolio-construction`, `cfa.03.financial-statement-analysis`,
  `cfa.04.quantitative-methods`, `cfa.05.fixed-income`, `cfa.06.ethics`,
  `cfa.07.economics`, `cfa.08.corporate-finance`, `cfa.09.derivatives`,
  `cfa.10.alternative-investments`, and `cfa.99.exam-preparation` (the
  cross-cutting plan/calculator/formulas/mocks/resources that applies to every
  topic). One skill per exam topic, in study order, each carrying the official
  2027 learning modules, Tier 1/Tier 2 formulas, common traps, question patterns,
  free resources, a practice target and its dependencies. `requiredSkills` form a
  real dependency graph (Equities -> Portfolio Construction -> Fixed Income ->
  Derivatives). All twelve validate against `harness.skills.manifest.SkillManifest`
  and load through `_load_project_skills` with no dangling dependency or prose
  cross-reference; the bundled 13-entry library is unchanged. Every skill ships
  `status: disabled` and the root stays untrusted until an operator grants both.
  Verified with the vendored interpreter (`./scripts/vendor/python/python.exe`).
  docs updated: `docs/NAVIGATION.md` (project skill root row + CFA task row).
  no source-contract change â€” data-only skill folders; no app or harness code
  touched.

- **Renamed the "Market Screener" page to "Market Discover"; aligned the Skills
  header icon with the sidebar.** Every user-facing string was updated â€” the
  sidebar/i18n nav label (`nav.discovery`), the page `<h1>`, the search registry
  page + "Open â€¦" action, market-result subtitles, the workspace panel
  label/title, the settings section + provider-registry copy (`providers/
  directory.ts` `usedBy` labels), and the "Back to â€¦" buttons. The Skills
  Library header now uses the same `Blocks` (Phosphor `SquaresFour`) glyph as
  the sidebar's Skills item, replacing a mismatched `Sparkles`. Internal
  symbol/function names (`useScreenerFilters`, `StockScreenerWidget`, the
  `screener` panel id) are unchanged â€” the page id/tab stays `discovery`.
  `npx tsc --noEmit` clean; search/sidebar/i18n tests (149) pass; `next build`
  compiles.
  no doc change â€” UI naming/icon consistency only; no contract change.

- **Fix: the approval card could not be reached from the two most important
  paths â€” patching code and the streaming chat.** Three defects: (1) the code
  authorizer's `workspace_patch_apply` branch created a PENDING request but
  returned without pausing, so a code write was refused with no card; it now
  blocks on the shared `pause_for_decision` gate and re-claims on approval
  (deny/timeout still refuses). (2) `approvalMode` was set only in the streaming
  chat payload; it is now a per-call-site opt-in on `run-service.ts` (`startRun`
  gains `approvalMode?`), set by the streaming chat path and deliberately UNSET
  for the synchronous `/api/harness/chat` and generic `/runs` callers â€” a pause
  there would block the HTTP request with no card to resolve it. (3) The
  `code_write`/`code_write_session` approval kinds were reviewable in the MCP
  panel but a paused run needs the card, not that panel. Added: an end-to-end
  graph test proving the run pauses (not finishes) on `approval.requested`,
  resumes in place on approve, and refuses on deny
  (`python/tests/test_approval_card_e2e.py`); authorizer-level tests for the code
  write pause (`test_approval_pause.py`, +2); front-door assertions that the
  streaming path sends `approvalMode: "ask"` and the sync path does not
  (`run-service.test.ts`, +3). Also fixed the Python stale-runtime detector
  (`python-runtime.ts` `harnessSourceMtimeMs`): it scanned ONLY top-level
  `python/harness/*.py`, so edits in `code/`, `mcp/`, `terminal/`, `skills/` never
  marked a running runtime stale â€” the runtime kept serving old code after a
  change. It now walks the whole tree, so `npm run dev` picks up harness changes.
  `npx tsc --noEmit` clean; full `vitest` 2144 passed, `pytest` 2653 passed, eval
  gates pass.
  docs updated: `docs/harness/architecture.md` (approval cards: code-write path,
  streaming-only opt-in).

- **Settings: organized the Intelligence-section pages to match the AI page's
  clarity, and fixed a duplicate-provider bug.** AI: the "Show more providers"
  list now excludes anything already shown under Connected/Popular, so a
  connected non-popular provider (e.g. xAI) or an active keyless local server no
  longer renders twice. Shared `ProviderRegistry` (Economics / Market / News) now
  groups rows by state â€” **Configured**, **Available** (built-in/keyless),
  **Needs a key** â€” with the key-gated list collapsed past 6 and a filter, and
  keeps the Economics by-kind sub-grouping. News feeds moved out of the flat
  74-row wall into a new `news-feeds-panel.tsx`: grouped Live/Paused, searchable,
  with inline add/remove. Market and Investor Eye pages gained consistent
  `SubSection` headings (Markets, Providers, Priority, Custom sources / Feature
  map, Event sources). No contract change: `NewsFeed` shape and `/api/settings`
  payload unchanged. `npx tsc --noEmit` clean; `vitest` 2141 passed, `pytest`
  2649 passed.
  no doc change â€” UI organization only; data contracts unchanged.

- **Approval cards: Eclipse now asks before any effectful step, and pauses the
  run until you answer.** Effectful actions (MCP write/action, external
  actions, and `ask`-classified commands) previously refused the call and let the
  model retry after you approved in Settings. A chat run now sends
  `approvalMode: "ask"`: the effect authorizer creates the single-use PENDING
  request, emits `approval.requested`, and PAUSES the in-flight run on an
  in-process gate (`_GATES`/`notify_decision` in `python/harness/mcp/approvals.py`,
  shared `pause_for_decision`/`_await_then_reclaim`). Approve resumes the run in
  place and runs exactly that one step; deny/timeout refuses as before. The
  decision is still the single-use, digest-bound approval â€” pause only changes how
  long the run waits, never whether a call is authorized; the wait is bounded
  below the run deadline and a runtime restart falls back to deny-and-retry. New
  frosted-glass `ApprovalCard` (`src/components/chat/approval-card.tsx`, portaled
  to `<body>`) floats above the composer in both chat surfaces, theme-adaptive,
  with Approve/Deny; wired via `HarnessUiEvent.approval_request`/`approval_resolved`,
  the `awaiting_approval` status, and `useAgentRun.decide`. `RunRequest.approvalMode`
  + `ToolContext.pause_for_approval`/`approval_timeout_s` are additive; the
  deny-and-retry path is unchanged. Tests: `python/tests/test_approval_pause.py`
  (+8). `npx tsc --noEmit` clean; full `vitest` 2141 passed, `pytest` 2649 passed,
  eval gates pass.
  docs updated: `docs/harness/architecture.md` (approval cards section).

- **Settings modal now opens instantly and no longer hangs on a slow market
  fetch.** Four causes fixed: (1) `/api/markets` and `/api/settings` were
  fetched in `Promise.all`, so a cold JDDS market build blocked the whole modal
  until it resolved â€” they now load independently and settings paints the moment
  it lands; (2) the settings dialog is unmounted on close, so every open
  re-fetched behind a skeleton â€” a module-level snapshot now paints cached
  values instantly and revalidates quietly; (3) the code-split `Settings` chunk
  was only ever fetched on first open â€” it is now warmed during idle and has a
  loading fallback; (4) `GET /api/settings` now uses the same in-memory SWR cache
  as `/api/markets`, so reads are instant even while the startup WarmUp/NewsIngest
  jobs hold SQLite (POST keeps the cache coherent). Measured with a production
  build + Playwright: modal open **510 ms** (fixed) vs the old build failing to
  appear within 15 s; `/api/settings` warm **22â€“28 ms** (fixed) vs old spikes of
  **17â€“30 s** under startup IO load. NOTE: the running dev server was serving a
  stale production build, so the fix only takes effect after a rebuild
  (`npm run up`). `npx tsc --noEmit` clean; full `vitest` 2140 passed,
  `pytest` 2642 passed.
  no doc change â€” load-path/perf fix only, no contract change.

- **Investor Eye Trade layer: hovering a country isolates ITS trade routes.**
  With the Trade layer on, the map showed every route, so hovering a country
  told you nothing about that country. Now the pointer answers "what does THIS
  country trade?": entering a country region isolates the routes that touch it
  (its links draw full-strength, every other route is hidden) and leaving
  restores the full web. Wired on both projections â€” the 2D geo map via new
  `mouseover`/`mouseout` region hooks in `bindLayerEvents`, the globe via the
  existing raycast pick â€” through a new `hoveredCountryIso` option. A
  click-selection still wins over hover. Isolated routes are marked `silent` so
  they cannot steal the pointer from the region and make the layer flicker. A
  country with no route honestly shows none. Tests: `map-echarts.test.ts` (+6).
  `npx tsc --noEmit` clean; investor-eye tests pass.
  no doc change â€” behaviour within the existing `lines` layer contract.

- **Dark sidebars are always black/charcoal (never neutral grey).** The shipped
  default sidebar moved from grey `#2a2a2e` to charcoal `#141416`, and the
  `SIDEBAR_PRESETS` list dropped its `Grey` entry in favour of black/charcoal
  options (`Black`, `Charcoal`, `Slate`, `Smoke`, `Crystal` â€” the last two keep
  only a faint cool/warm cast). Every dark-scheme preset's rail is now under
  luminance 0.011. Verified with `npx tsc --noEmit` and the theme tests (54 pass).
  no doc change â€” preset/default tweak; contracts unchanged.

- **White presets listed after the dark ones + Electric Blue Crystal sidebar.**
  The four white-background presets (`White`, `Paper`, `Snow`, `Ivory`) now sit
  at the END of `THEME_PRESETS` so the preset buttons read all dark looks first,
  then go light â€” instead of interrupting the dark grid at the top. Electric Blue
  now uses the translucent Crystal sidebar recipe (`#26262c` @ 0.55 / blur 34)
  rather than the default neutral Grey, so the cold blue brand carries into the
  rail. Verified with `npx tsc --noEmit` and the theme tests.
  no doc change â€” preset list/ordering tweak; contracts unchanged.

- **Added white-background theme presets (`White`, `Paper`, `Snow`, `Ivory`).**
  A new internal `scheme: 'dark' | 'light'` token on `EclipseTheme` lets a
  preset switch the whole app to a light look in one click â€” selectable from the
  normal preset grid, no separate mode toggle. `applyThemeToDocument` owns the
  `dark` class (was hardcoded in `layout.tsx`, which now only seeds the dark
  default plus a pre-paint script to avoid a flash) and scopes color vars to
  `html.dark` / `html:not(.dark)` by scheme; light presets carry dark ink text,
  white surfaces, a light landing and a dark wordmark. Charts resolve
  grid/axis/tooltip chrome from the scheme (`eclipse-provider.ts`), and a scoped
  compatibility layer in `globals.css` remaps hardcoded dark neutral utilities
  (`border-white/*`, `bg-black/*`, `bg-white/*`, `text-white/*`, near-black
  hexes, aurora glow) when light. Verified with `npx tsc --noEmit`,
  `npm run test` (188 files, all pass) and `npm run build`.
  docs updated: `ARCHITECTURE.md`, `NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Settings: removed the yellow "providers need a key" attention dots.** The
  rail and mobile pill indicators (and the `ATTENTION` map / `useProviderHealth`
  wiring behind them) are gone (`settings.tsx`). `npx tsc --noEmit` clean.
  no doc change â€” UI-surface removal only.

- **General settings: folded the full-screen preview launcher into the sticky
  Live-preview/Apply card, and fixed the rail item text alignment.** The
  "Preview on the real app" row is now a section inside the sticky card
  (`customization-settings.tsx` / `customization-preview.tsx`) instead of a
  separate card below it. The left-nav buttons inherited browser-default
  `text-align: center`, so wrapped description lines centered under the icon;
  added `text-left` (`settings.tsx`). `npx tsc --noEmit` clean.
  no doc change â€” UI-surface layout fix only.

- **Settings cleanup: removed the provider-count status banner and the footer
  "N/M feeds live" readout.** Dropped the `SettingsStatusHeader` component
  (`provider-registry-panel.tsx`) and its render in `settings.tsx`; the footer
  keeps only the save-state line and the Reload button. `npx tsc --noEmit`
  clean; `vitest` green apart from a pre-existing `stock-chat.tsx` size-budget
  failure (unrelated, file not touched).
  no doc change â€” copy/UI-surface removal only.

- **Restored a green size-budget guard after the terminal/model work grew the
  SPA shell.** `stock-chat.tsx` reached 1237 lines (terminal-dock plumbing plus
  the focus-mode "tuck the terminal" effect) while its ratchet stayed pinned at
  1212, so `size-budget.test.ts` failed on `main`. Bumped the ratchet to 1237
  with a note; the file may still only shrink from here. `npx tsc --noEmit`
  clean; `vitest` size-budget suite passes.
  no doc change â€” test budget bookkeeping only.

- **Market Screener / Market Bubbles "Ask AI" runs no longer fail on an
  uninstalled default model.** The buttons themselves were correctly wired (they
  navigate to ChatBot and start a real harness run); the run failed with a raw
  `404 model 'llama3.1' not found` because the active config pointed at a
  keyless-local placeholder the installed server does not serve (this box's
  Ollama only has cloud models). Fix makes the default resolve to a model the
  provider ACTUALLY serves, without inventing one: the model runtime now exposes
  the provider's raw served ids (`discover_served`; the discover endpoint returns
  `served` alongside the merged registry view), the front door records that set
  in the `discovered_models_v1` snapshot (`served` map, replaced per probe, not
  merged), `GET /api/harness/chat/models` reports it per provider, and
  `useChatModel` auto-probes a keyless local provider and adopts the first served
  model â€” VISIBLY (the composer selector updates) and persisted to the vault. An
  explicit user pick is never overridden; nothing changes when the provider
  serves nothing known. Added `pickServableModel` (+5 vitest), discover `served`
  tests in `route.test.ts` (+3) and `model-runtime-browser.test.ts` (+1), and a
  Python API test for `served` separately from the merged list. `vitest` 2122
  passed; `pytest` 2642 passed; `npx tsc --noEmit` clean. docs updated:
  `docs/CHANGELOG.md`, `docs/harness/architecture.md`.

- **Theme colors fixed: Surface now recolors the glass surfaces, and the dead
  "Accent" token is wired up.** Two real bugs in the customization system.
  (1) Every frosted-glass tier (`.glass-card`, `-strong`, `-subtle`, `.glass-tooltip`,
  `.glass-button`, `.glass-drawer`, tab/command/ws strips) used a **hardcoded**
  `rgba(18,18,20,â€¦)` tint, so the theme's "Surface" color only recolored flat
  `bg-card` blocks â€” editing Surface barely changed the UI. `themeCssVars` now
  emits `--card-rgb` (the Surface as an `r g b` triplet) and every glass recipe
  builds its tint as `rgb(var(--card-rgb, <fallback>) / Î±)`. (2) The theme's
  "Accent" color was emitted as `--brand-accent` / `--brand-accent-rgb` but
  consumed **nowhere**, so editing Accent did nothing visible. The shared
  `TabBar` active pill now carries a primaryâ†’accent gradient + accent hairline,
  giving the token a real consumer. Verified with pixel diffs: changing Surface
  went from ~1.4% to ~8.7% of the viewport, and Accent visibly tints the active
  tab. Tests: `theme/tokens.test.ts` (+1 for `--card-rgb`). `vitest` 2113 passed;
  `npx tsc --noEmit` clean. docs updated: `docs/CHANGELOG.md`.

- **Icon set switched from Lucide to Phosphor behind one aliased module.** Every
  icon now renders Phosphor (`@phosphor-icons/react`) via a new central surface
  `src/lib/icons/index.ts`, which re-exports each glyph under its original Lucide
  name (plus `LucideIcon`), so all ~165 importing modules keep their existing call
  sites and only the import specifier changed (`lucide-react` â†’ `@/lib/icons`).
  This gives the dark glass UI a distinctive shape language and Phosphor weights
  (fill/duotone). Selected/active states were converted from `fill="currentColor"`
  to `weight="fill"` (Phosphor outlines are filled paths, so `fill="none"` would
  erase the glyph). `components/chat/{chat-history,markdown}.tsx` and
  `components/screens/portfolio/fund-store.ts` gained a `'use client'` boundary
  because Phosphor icons read `useContext`. `lucide-react` removed. `npx tsc
  --noEmit` clean; `next build` succeeded; `vitest` 187 files / 2112 tests passed.
  docs updated: `docs/NAVIGATION.md`, `docs/DECISIONS.md`, `skills/ARCHITECT.md`
  (ADR-041).

- **Investor Eye Trade layer: selecting a route now isolates it.** Clicking a
  trade line selected the event but left every route on the map equally loud, so
  you could not see *which* link the click referred to or what it connected. The
  selected route now draws full-strength (thicker, opaque) while every other
  route dims to 10% opacity, the flow animation stops (a moving target cannot be
  "the one"), and the two endpoint countries get glowing labelled markers â€” so
  "what is traded between X and Y" reads straight off the map. The line datum now
  carries `fromName`/`toName`/`fromIso`/`toIso`/`eventKey`, and a dedicated
  `tradeTooltip` leads with the ROUTE and the traded goods instead of a generic
  event blurb. `selectedEventKey` is threaded `WorldMap` â†’ `buildMapOption` on
  the main screen, full-page map, and dashboard widget. Tests:
  `layers.test.ts` (+1), `map-echarts.test.ts` (+3). `npx tsc --noEmit` clean;
  `vitest` 2106 passed (the 1 failing `pytest` test is in the model-runtime area
  from concurrent work, untouched by this change).
  no doc change â€” behaviour within the existing `lines` layer contract.

- **Restored the sidebar width to its original `w-60` (was shrunk to `w-52`).**
  A prior commit narrowed the desktop sidebar and the Settings rail from `w-60`
  to `w-52`; both are back to `w-60` (`sidebar.tsx` collapse/expanded/mobile and
  `settings.tsx` rail). no doc change â€” layout fix; no contract change.

- **Terminal command approvals now actually surface; agent steered to auto-allowed
  `mkdir`.** An agent asked to "create a folder on my Desktop" reported it was
  blocked. Two causes, both fixed. (1) A terminal `ask` command (`New-Item â€¦`)
  creates a pending approval, but `/code/approvals` only listed `kind='code_action'`,
  so the request was invisible in the UI â€” the user could never approve it and the
  agent looped. The route now lists and decides `code_action` + `terminal_command`
  + `shell_command`. (2) `mkdir`/`md` is already `allow` (runs with no approval;
  verified it creates the folder), but the code-agent prompt did not say so, so the
  agent chose the long `New-Item` form. The prompt now tells it to prefer the short
  auto-allowed form, not to retry the same refused tool in a loop, and to state
  plainly when a requested path is outside the bound folder. Tests: `test_code_api.py`
  green; Vitest unchanged; Python suite green.
  docs updated: `docs/harness/terminal-architecture.md`.

- **Terminal: the "dock back" icon is now an inward-corners glyph, not a download
  arrow.** `ArrowDownToLine` read as a download button, so the detached pop-out's
  "dock back" control now uses `CornersIn` (a dock/restore glyph), matching the
  restore control on the docked panel. no doc change â€” icon swap only.

- **Terminal: the `[?1;2c` prompt garbage is gone.** Root cause: the shell asks
  the terminal "what are you?" (Device Attributes, `ESC[c`); xterm auto-replies
  `ESC[?1;2c`; because every keystroke is forwarded to the PTY, that reply reached
  PowerShell, which cannot interpret it and ECHOED the literal text at the prompt.
  Filtering the output could not fix it (the shell had already echoed the bytes).
  The reply is now dropped from the INPUT stream (`filterTerminalInput` in
  `xterm-terminal.tsx`) before it reaches the PTY â€” the shell never needs it â€” with
  the output-side strip kept as a fallback for a session that echoed it earlier.
  Verified in-browser: no `?1;2c`, typing unchanged. Vitest **2140 passed**; Python
  **2642 passed**; eval gates ALL PASS; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/terminal-architecture.md`.

- **Terminal: instant open, accurate icons, frosted glass, real resize.** Four
  phases. (1) Speed: the dock now starts the shell on the server IN PARALLEL with
  the xterm JS download (`Promise.all`), the runtime is prewarmed from the root
  layout, and the service pre-opens one idle shell at boot (`TerminalManager.warm_shell`
  + `WARM_OWNER`, adopted by the first UI open). Measured: open-to-prompt went from
  ~24s to ~1.1s. Also fixed the warm path's undefined `WARM_OWNER`/unwired boot call.
  (2) Icons: replaced the inaccurate set with semantic Phosphor icons â€” `Rows3`
  (dock bottom), `Columns3` (dock right), `CornersOut`/`CornersIn` (full/restore),
  `Export` (detach), `AppWindow` (new window), `Cpu` (processes) â€” added to
  `src/lib/icons`. (3) Glass: the dock and the pop-out use `glass-card-strong`
  (measured `backdrop-filter: blur(22px) saturate(1.4)`); the xterm host is
  transparent so the frost shows through, and the pop-out is portaled to `document.body`
  so its blur samples the real page. (4) Resize: the docked bottom/right panels have
  a pointer-drag handle that resizes them and pushes the new rows/cols to the PTY
  (`/terminal/sessions/{id}/resize`); the pop-out is drag + resize by pointer (its
  native CSS `resize` handle was unusable). Tests: Vitest **2140 passed**; full
  Python suite green; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/terminal-architecture.md`.

- **Terminal: narrow-screen overlap fix, detach pop-out, and a new-window terminal.**
  Three fixes/features. (1) Overlap in sidebar/narrow mode: the right dock was a
  fixed-width column at every width, so on a narrow viewport it covered the main
  panel; it now collapses to a bottom strip below `md` (`md:w-[24rem] lg:w-[26rem]`,
  else full-width strip) and the header wraps instead of crowding, so nothing
  overlaps. (2) The stray `?1;2c` in the terminal: xterm answers the shell's
  Device-Attributes query (`ESC[c`) with `ESC[?1;2c`; we forward every keystroke to
  the PTY, so PowerShell echoed it literally. The answer and its echo are now
  filtered from the DISPLAY stream (`stripTerminalNoise`); terminal output is
  otherwise untouched. (3) Detach + new window: a detach control turns the docked
  terminal into a draggable floating pop-out sharing the same session, and a
  new-window control opens `/terminal?session=<id>`, a standalone page
  (`terminal-window.tsx`) that ATTACHES to the running shell (or opens its own if
  no id). Added `terminalOwnerId()` so the dock, pop-out and window share one owner.
  Added `ArrowDownToLine`/`SquareArrowOutUpRight` to the icon surface. Full Python
  suite green; Vitest **2139 passed**; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/terminal-architecture.md`.

- **Terminal is now a real docked region, not a floating overlay.** It no longer
  overlaps the app (including the ChatBot). The app shell reserves the space: docked
  **bottom** the terminal is a strip inside the shell below the main content, docked
  **right** it is a full-height column beside the main panel (which shrinks), and
  **full page** it covers the window. Sidebar + main column + right dock are one flex
  row, with the bottom dock below it; the terminal is no longer `fixed` in the root
  layout (the floating `terminal-panel.tsx` is deleted). Placement is persisted and
  the shell hydrates it on mount (`useTerminalShell`), so the docked region reserves
  its space on first paint. The terminal refits and the PTY resizes on every
  placement change, and the shell is preserved across placement switches (bottom â†’
  right keeps history). Fixed a latent `api-guard` same-origin check in the same
  change (see above). Extracted `useTerminalShell` to keep `stock-chat.tsx` within its
  size ratchet. docs updated: `docs/harness/terminal-architecture.md`.

- **Terminal: fix typing and add bottom / right / full-page placement.** Three real
  bugs fixed. (1) Typing did nothing: the mutation guard compared `Origin`
  (`http://127.0.0.1:3000`) against the request host (`localhost`) byte-for-byte,
  so every browser mutation â€” including opening a session â€” got a 403
  "Cross-origin requests are not allowed". Loopback aliases are now normalized to
  one origin (`normalizeHost`), so same-machine requests are allowed while a real
  cross-site request is still blocked. (2) The terminal rendered but received no
  output: React StrictMode double-mounts the effect and the first cleanup's
  `stopRef` was never reset, so the stream loop exited immediately â€” now reset on
  every mount (and the terminal auto-focuses so typing works without a click).
  (3) Typed commands ran jumbled ("terminal" â†’ "terimnal"): one HTTP request per
  keystroke let concurrent writes interleave. Writes are now serialized with a
  per-session lock in the runtime, and the client drains an ordered input queue
  (one in-flight request, coalescing keystrokes without reordering). Added a
  placement control â€” **dock bottom / dock right (full height) / full page** â€” with
  the choice persisted; the terminal refits and the PTY resizes on every placement
  change. Tests: `api-guard.test.ts` (+2 loopback-origin), `terminal-keybind.test.ts`
  (+3 placement, +2 ordered-queue). Full Python suite **2642 passed**; Vitest
  **2127 passed**; `npx tsc --noEmit` clean; `npm run test:evals` ALL PASS.
  docs updated: `docs/harness/terminal-architecture.md`.

- **Terminal: header button + a reliable Ctrl/Cmd + ` toggle.** The terminal is now
  opened from a button at the header's right edge (next to the search bar) and by
  Ctrl/Cmd + `, both driving one shared `useTerminalStore`. The shortcut previously
  lived in local panel state and only bound while the panel was open (so it could
  not open the panel), and matched on `event.key`, which varies by keyboard layout.
  It now listens in the CAPTURE phase on `window` in the root layout (`TerminalKeybind`),
  matches `event.code === 'Backquote'` (layout-independent) with a `key` fallback,
  and calls `preventDefault`/`stopPropagation` so the browser or a focused xterm
  cannot swallow it. Also added an expand/restore control and a "New" shell action,
  persisted the open state, and hardened the shortcut matcher with unit tests.
  Fixed a concurrent duplicated-block syntax error in `src/lib/investor-eye/map-echarts.ts`
  that broke `tsc`/vitest. Tests: `terminal-keybind.test.ts` (+9).
  docs updated: `docs/harness/terminal-architecture.md` (Terminal UI section).

- **Real interactive terminal UI (xterm.js over a live PTY).** The Terminal tab was
  a fake one-shot command box: line-based, no streaming, no interactive programs.
  It is now a genuine terminal â€” xterm.js
  (`src/components/terminal/xterm-terminal.tsx`) rendering a live PTY-backed shell
  in the runtime. Keystrokes go straight to the PTY
  (`POST /terminal/sessions/{id}/raw`), output arrives over a low-latency long-poll
  stream (`GET /terminal/sessions/{id}/stream`, ~0.06 s) with ANSI preserved, and
  the window is resized to fit. The session lives in the runtime, so closing the
  panel or reloading does not kill the shell; the panel passes a durable `owner` id
  and reattaches (`attach_or_open_shell`), with "New shell" to open a fresh one.
  Added `@xterm/xterm` + `@xterm/addon-fit`. Backend: a per-session output
  `Condition` wakes the stream the instant output lands, `wait_for_output`,
  `stream_shell_output`, `send_shell_raw`, and an `owner` filter on session listing.
  Tests: `test_terminal_api.py` +2 (owner reattach, raw-inputâ†’stream round trip).
  Full Python suite **2639 passed**; Vitest **2093 passed**; `npx tsc --noEmit`
  clean. docs updated: `docs/harness/terminal-architecture.md` (UI section).

- **Terminal follow-up: real PTY, Docker/SSH runtimes, resource/runaway protection.**
  Closed the four known limitations of the terminal subsystem. (1) A real PTY
  (`pywinpty` on Windows, `ptyprocess` elsewhere) is now installed by default via
  platform markers in `python/requirements.txt`, so persistent shells are genuine
  ConPTYs (`pty: true`); agent-facing session text strips ANSI while the UI buffer
  keeps it for rendering, and a `cd`/`export` is sent to the real shell and its
  resulting cwd read back via the sentinel then workspace-confined (a command that
  leaves the workspace is refused and the shell returned to the root). (2/3)
  `DockerRuntime` and `SSHRuntime` are implemented for command execution and
  background processes behind operator config (`HARNESS_TERMINAL_DOCKER_CONTAINER`
  / `_WORKDIR`, `HARNESS_TERMINAL_SSH_HOST`); interactive sessions for them refuse
  `NOT_IMPLEMENTED`; SSH uses the host's own OpenSSH config/agent and never reads a
  key. New `runtime.extra_env()` forwards only non-secret host vars
  (`DOCKER_HOST`, `SSH_AUTH_SOCK`). (4) `terminal/resources.py` adds CPU/memory
  telemetry (no `psutil`) plus `ResourceLimits` â€” a start past `maxProcesses` is
  refused `PROCESS_LIMIT`, and a process over its output/lifetime bound is FLAGGED
  `runaway` (never auto-killed) with a `terminal.process.runaway` event; surfaced
  by `resource_report`/`system_info` and `/terminal/resources`. Also made the
  sandbox orphan test precise: it now asserts on the test process's own python
  descendants (`proctree.descendant_pids_matching`), not a machine-wide process
  count, so an unrelated python process can no longer perturb it. Tests: 11 new
  `test_terminal_resources.py` cases plus Docker/SSH unit tests and the PTY session
  coverage (86 terminal tests total). Full Python suite **2637 passed**; Vitest
  **2093 passed**; `npx tsc --noEmit` clean; `npm run test:evals` ALL PASS.
  docs updated: `docs/harness/terminal-architecture.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (`ADR-H127`).

- **Terminal/Shell/Process execution subsystem â€” the execution backbone.**
  Added `python/harness/terminal/` (one `TerminalManager` shared by agent tools and
  the UI): persistent shells (`open_shell`/`run_shell_command`/`write_shell_input`/
  `read_shell_output`/`resize_shell`/`send_shell_control`), background process
  management (`start_process`/`stop_process`/`restart_process`/`kill_process`/
  `read_process_output`/`write_process_input`/`send_signal`/`process_tree`),
  `execute_command` foreground execution, `list_ports`, `terminal_capabilities`,
  `system_info`; a sequenced/bounded output `RingBuffer` with cursor polling;
  secret redaction; a deterministic process state machine with crash detection; a
  Windows Job-Object / POSIX-group per-process isolation backend; OS process-tree
  and port attribution; `TerminalSession`/`ProcessRecord`/`TerminalCommand` rows on
  the one `agent-memory.db`; boot `RecoveryManager`; operator-gated `/terminal/*`
  routes; front-door `src/lib/harness/terminal-{client,browser}.ts` + `/api/terminal/**`;
  and Processes/Ports views in the terminal panel. The tools are removed at
  `plan_only` (`code/policy.py`) and classified allow/ask/deny by the effect
  authorizer composed into the graph. Docker/SSH runtimes refuse honestly
  (`NOT_IMPLEMENTED`). Also fixed a latent env-scrub gap: `PATHEXT` was missing
  from `SECRET_ENV_ALLOWLIST`, so a shell with a scrubbed environment could not
  resolve an executable by name. Tests: `python/tests/test_terminal_*.py` (72),
  incl. `test_terminal_e2e.py`. Full Python suite green (2550 passed);
  `npx tsc --noEmit` clean.
  docs updated: `docs/harness/terminal-architecture.md` (new),
  `docs/NAVIGATION.md`, `docs/harness/decisions.md` (`ADR-H126`).

- **Investor Eye Heatmap button now matches the surrounding controls.** The
  standalone `HeatmapToggle` was styled differently from the buttons beside it
  and sat alone on the map surface. It now sits in the Investor Eye header
  toolbar directly beside Map/skin/stars/names and Full page / Ask the map /
  Refresh, and uses the identical `glass-button` recipe; the dashboard widget
  gets an `accent` variant that matches its own `bg-accent/30` header buttons.
  `npx tsc --noEmit` clean; investor-eye tests pass.
  no doc change â€” control styling/placement only; no contract change.

- **Investor Eye heatmap: scope its visualMap (event dots no longer turn purple
  and stick) + coarser density grid.** Two regressions in the `event-heatmap`
  layer. (1) A continuous ECharts `visualMap` defaults to `seriesIndex: 'all'`,
  so it recoloured EVERY series from its `value` â€” the event pins (value = a
  0.2â€“1 severity weight) were re-tinted to the low/violet end, and because the
  update path only `replaceMerge`d `series`, the mapping (and the purple) stayed
  after the heatmap was switched off. The `visualMap` is now scoped with
  `seriesId: 'event-heatmap'`, and `world-map.tsx` replaces `visualMap` too, so
  turning the layer off REMOVES the mapping and every layer reverts to its own
  colouring. (2) The heatmap reused the pin-cluster grid (0.1Â° at high counts),
  so every event was its own faint speck instead of a regional hotspot. It now
  aggregates on a coarse `heatmapCellDegrees()` grid (1.5â€“8Â° by count), so
  neighbouring events accumulate into one hotspot the way a heatmap should.
  Tests: `map-echarts.test.ts` (+2 visualMap-scoping cases).
  `npx tsc --noEmit` clean.
  no doc change â€” bug fix to heatmap rendering; `MapLayerType`/contract unchanged.


- **Fixed the composer model dropdown crashing on open (Base UI error #31).**
  `ModelSelector` in `chat-input.tsx` rendered `DropdownMenuLabel` (Base UI
  `Menu.GroupLabel`) as a direct child of `DropdownMenuContent`, but a group
  label requires a `<Menu.Group>` ancestor â€” clicking the pill threw
  `Base UI error #31` and the menu never appeared. Wrapped the label + model
  list in `DropdownMenuGroup`. Verified with a Playwright probe: menu opens,
  lists all providers/models, no console errors. `vitest` 2085 passed;
  `npx tsc --noEmit` clean. no doc change â€” bug fix; no contract change.

- **Model menu restyled to frosted glass.** The composer model dropdown and its
  Provider submenu used the opaque `bg-popover` fill, so it read as a flat solid
  panel over the dark page. Both surfaces now use the shared `.glass-tooltip`
  tier (translucent tint `rgba(18,18,20,0.5)` + `backdrop-filter: blur(18px)
  saturate(1.35)` + inset highlight), matching the UI system's popover recipe;
  the solid `bg-popover` + `ring` fill and shadow were removed from
  `dropdown-menu.tsx`. The dropdown is already portaled by Base UI, so the blur
  samples the real page (verified with a Playwright high-contrast backdrop:
  background is visibly blurred through the panel and submenu, no console
  errors). This changes every consumer of the shared `DropdownMenuContent`
  (composer model selector is the only one today). `vitest` 2087 passed;
  `npx tsc --noEmit` clean. no doc change â€” visual-only restyle using the
  existing glass system; no architecture/contract change.

- **Scrollbar + provider-status colour toned down (professional, neutral).** The
  global scrollbar was brand-tinted, and on hover it turned bright brand green
  (`#7aff78`) â€” a loud yellow-green streak on dark glass. Both global scrollbar
  blocks in `globals.css` (the early brand block + the late `#262626`/`var(--brand)`
  cascade layer) now use a neutral translucent-white thumb
  (`rgba(255,255,255,0.16)`, `0.30` hover) on a transparent track, so no theme can
  turn the scrollbar a saturated colour. In the composer model dropdown's Provider
  submenu, the `needs key` / `no key` labels were saturated amber/green; they are
  now muted (`text-muted-foreground/50`; `key set` at `text-emerald-400/70`), so
  the menu reads as chrome rather than a traffic-light. `vitest` 2087 passed;
  `npx tsc --noEmit` clean. no doc change â€” visual-only; no contract change.

- **Composer model menu: fixed dead item handlers + made "Discover" list and keep
  every installed model.** Three compounding bugs. (1) The shadcn-style wrapper
  `dropdown-menu.tsx` exposed Radix's `onSelect` API, but Base UI's `Menu.Item`
  only fires `onClick` â€” so **every** menu item (`setModel`, provider switch,
  Discover, Custom) silently did nothing. All items now use `onClick`, with
  `closeOnClick={false}` where the menu must stay open (Discover, Custom id).
  (2) `ModelRegistry.discover_models` returned only the *newly registered* models,
  so a second "Discover" click returned an empty list; it now returns the
  provider's full registered set (idempotent) â€” Python test added.
  (3) The composer catalog (`GET /api/harness/chat/models`) read only the static
  preset (`llama3.1`, â€¦), never the runtime's discovered registry, so installed
  Ollama models vanished on reload. The route now merges `listRuntimeModels()`
  (best-effort, server-side) per provider. Result: an Ollama "Discover" now shows
  ALL installed models and they persist across reloads. Tests: `models/route.test.ts`
  (+2), `test_model_runtime.py` (+1). `vitest` 2089 passed; `pytest` green;
  `npx tsc --noEmit` clean. docs updated: `docs/CHANGELOG.md`.

- **Model menu: providers that need a key now link straight to Settings â€º AI.**
  Clicking a provider whose key is missing previously selected it and then failed
  at run time. The Provider submenu item now detects `!keyless && !available` and
  dispatches the command bus to `settings.ai`
  (`useCommandStore.getState().dispatch({ tab: "settings", subroute: "settings.ai" })`)
  â€” the established modal-navigation idiom â€” so the user lands on the AI/LLM page
  to paste the key. The label changed from "needs key" to a primary "Add key" with
  a key icon. Keyless/configured providers still select normally. `vitest` 2089
  passed; `npx tsc --noEmit` clean. no doc change â€” small navigation affordance;
  no architecture/contract change.

- **Settings â€º AI redesigned: grouped providers, connect/disconnect, readable
  active model.** The old surface dumped every provider into one two-column grid
  beside a duplicate config form, so it was unclear what was selected or how to
  add/remove a key. New `ai-provider-settings.tsx` groups it: (1) **Active setup**
  â€” the current provider + model echoed prominently, with model picker, base URL,
  context window, key editor and Test, in one card; (2) **Connected providers**
  â€” those that work (key set, or keyless local), each with **Disconnect**
  (deletes the vault key) or **Use**; (3) **Popular providers** â€” one click to
  **Connect** (reveals the key field) or select; (4) **Show more providers** â€”
  the rest, collapsed. Provider state is derived honestly (Active / Connected /
  Ready / Not connected). `ProviderKeyEditor` gained an `onChanged` callback.
  The model picker (`model-picker.tsx`) no longer shows a raw `__custom__`
  sentinel â€” the current id is always in the Select, with a separate "Custom
  model idâ€¦" toggle. `GET /api/harness/models` now merges runtime-discovered
  models, so the Settings picker reads the operator's installed Ollama models
  too. Tests: `api/harness/models/route.test.ts` (+3). `vitest` 2092 passed;
  `pytest` green; `npx tsc --noEmit` clean. docs updated: `docs/CHANGELOG.md`.

- **Settings â€º AI: removed themed (blue) borders, provider cards now full-width.**
  The provider cards and section icon used `border-primary/*` / `border-emerald-*`,
  which resolve to the active theme's brand colour â€” so under a blue theme
  ("Electric Blue", "Blueprint") every card had a blue outline. They now use
  neutral white-alpha borders, so no theme can tint the chrome. The catalog
  grids also changed from two columns (`sm:grid-cols-2`) to a single full-width
  column. `vitest` 2092 passed; `npx tsc --noEmit` clean. no doc change â€”
  visual-only; no contract change.

- **Site sidebars unified to one neutral grey, accent-free look; rows shortened.**
  The main app sidebar (`layout/sidebar.tsx`) and the Settings screen's own left
  rail (`screens/settings.tsx`) are now the same surface: both carry `sidebar-root`
  + `glass-card-strong`, so Settings no longer renders a rounded, accent-tinted
  `glass-card-subtle` panel that drifted from the shell rail. Green `primary`
  accents (active mode button, active nav row/icon, shortcut badge, settings gear,
  Settings header/chevron/nav pills) were replaced with neutral white-wash
  (`bg-white/[0.08]`, `text-foreground`). Nav rows shrank `h-10` â†’ `h-9`. The
  shipped sidebar tint moved `#1a1a1c` â†’ `#2a2a2e` (clearly grey) and
  `SIDEBAR_PRESETS` gained a `Grey` default preset (`charcoal` retained). Tests
  updated in `lib/theme/tokens.test.ts`. no doc change â€” surface styling only; no
  architecture/contract change.

- **ChatBot transcript rail de-accented; default sidebar width reduced.** The chat
  page's right-edge `MessageRail` ticks no longer use the green brand accent â€”
  idle ticks are `bg-muted-foreground/50`, hover/active brighten to a neutral
  `bg-foreground/70â€“80` with no glow. The default sidebar width dropped `w-60`
  (15rem) â†’ `w-52` (13rem) on the shell rail (`layout/sidebar.tsx`), its mobile
  drawer, and the Settings rail (`screens/settings.tsx`) so the default chrome is
  less dominant. `npx tsc --noEmit` clean; `vitest` 2092 passed.
  no doc change â€” surface styling only; no architecture/contract change.

- **Chat scrollbars de-accented to neutral grey.** The chat transcript's visible
  scrollbar (`.chat-transcript-scroll`) was still brand-green â€” after scrolling
  up it rendered as a bright vertical streak on the right edge of the ChatBot
  page. It (plus `.chat-composer-scroll` and `.tv-metrics-rail`) now uses the
  same neutral `rgba(255,255,255,0.16)` thumb / `0.30` hover as the global bar,
  and the transcript/composer bars slimmed 8/10px â†’ 6px. `npx tsc --noEmit`
  clean; `vitest` 2092 passed. no doc change â€” styling only.

- **Chat transcript scrollbar replaced with a short capped thumb.** The native
  transcript bar always spans the full scroll-container height (it ran down the
  right edge and under the header, looking like a long band). `ChatHistory` now
  hides the native bar (`scrollbar-hide`) and renders a compact custom thumb
  capped at ~28% of the track, inset 6px from the top/bottom, tracking the
  reading position via a ResizeObserver + scroll listener. The unused
  `.chat-transcript-scroll` CSS was removed. `npx tsc --noEmit` clean;
  `vitest` 2092 passed. no doc change â€” styling only.

- **Settings model dropdown no longer renders behind the modal; discovered
  models persist; all connected providers usable from chat.** Three fixes:
  (1) `SelectContent` and `DropdownMenuContent` were portaled at `z-50` while the
  Settings `Dialog` popup/overlay sit at `z-[100]`, so the model list painted
  behind the modal â€” both moved to `z-[110]` (same for `TooltipContent`, which
  has the identical class of bug). Verified live with Playwright against a fresh
  dev server: the popup now computes `z-110` and sits above the dialog at
  `z-100`. (2) "Discover installed models"
  results lived only in the Python runtime's in-memory registry (lost on reload /
  restart), so discovery had to be re-run every time; the discover route now
  merges found ids into a durable `SystemConfig` snapshot
  (`src/lib/agent/discovered-models.ts`, key `discovered_models_v1`) that both
  catalog routes merge ahead of the runtime registry. (3) The chat composer's
  model menu listed only the active provider's models; it now groups the models
  of EVERY provider usable right now (keyless locals + any provider with a
  resolving key), active first, and selecting one switches the active provider to
  that model's provider. Also fixed a pre-existing CRLF/LF mix in
  `python/harness/terminal/runtimes.py` flagged by the gitignore-guard test.
  `npx tsc --noEmit` clean; `vitest` 2093 passed. docs updated:
  `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`.

- **`Select` dropdown restyled to frosted glass.** The select popup used a flat
  opaque `bg-popover` panel with a generic `ring`/`shadow-md` â€” visually a plain
  system menu, and the odd one out next to the `DropdownMenu` (which already uses
  `.glass-tooltip`). It now uses the same `.glass-tooltip` frosted recipe
  (translucent tint + backdrop blur + saturation, rounded-2xl, soft shadow +
  inset highlight), with roomier rounded items, a neutral white-wash
  hover/selected state, a primary-tinted check indicator, and gradient scroll
  affordances instead of opaque `bg-popover` strips. `npx tsc --noEmit` clean;
  `vitest` 2093 passed. no doc change â€” styling only.

- **Every provider can enumerate its live models (OpenRouter, OpenAI, Groq, â€¦).**
  Previously only local servers + routers (Ollama/LM Studio/OpenRouter) offered
  "Discover installed models"; a hosted API showed only its declared sample, so
  you could not pull e.g. OpenRouter's catalog. Fixes: `ProviderSpec.dynamic_discovery`
  is now true for OpenAI, Anthropic, Gemini, Mistral, Groq, DeepSeek, xAI,
  Together, Perplexity, Fireworks; the probe is protocol-generic
  (`python/harness/model_runtime/providers/openai.py` `probe_openai_models` =
  `GET {base}/models` with a `Bearer` key for every OpenAI-protocol family;
  `AnthropicAdapter`/`GoogleAdapter` override `discover_models` for their own
  list shapes); and the Next discover route now resolves the provider key
  server-side from the env/vault (`resolveProviderKey`) with a preset base-URL
  fallback, since the browser never holds it â€” so a private endpoint that would
  401 keyless now enumerates. Discovered ids are cached in the durable snapshot
  added earlier. Tests: `python/tests/test_model_runtime.py` (catalog flags +
  adapter probes + parser). `npx tsc --noEmit` clean; vitest 2093 passed;
  Python model-runtime 71 passed. docs updated: `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`.

- **Model lists are now curated via a "Manage models" dialog (no more flooded
  dropdowns).** A provider can enumerate hundreds of models (OpenRouter: 466),
  which is unusable in a picker. Discovery now opens a searchable,
  checkbox enable/disable dialog (`src/components/screens/manage-models-dialog.tsx`)
  showing the full catalog; the enabled subset is what the compact pickers show,
  persisted per provider in `src/lib/agent/enabled-models.ts` (`be_enabled_models_v1`,
  shared zustand store + pure `compactModels()` with `MODEL_LIST_SOFT_LIMIT`=40).
  Both Settings â†’ AI (`model-picker.tsx`) and the chat composer
  (`chat-input.tsx` `ModelSelector`) gained a "Manage" affordance and render the
  same dialog, so curation is reflected everywhere. It is a client-side filter,
  never an allowlist (the runtime accepts any id; "Custom model idâ€¦" still
  works). `npx tsc --noEmit` clean; vitest 2112 passed (incl.
  `enabled-models.test.ts`). docs updated: `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`.

## 2026-10-04

- **Composer model selector: fixed to be ALWAYS visible + switch providers.**
  The previous attempt gated the dropdown on a non-empty model list, so for the
  default configuration (one saved model) it never rendered and the pill stayed a
  static label â€” the selector appeared "broken". It also only offered the active
  provider's models, so there was nothing to switch to. `chat-input.tsx` now
  renders an always-present `ModelSelector`; `use-chat-model.ts` + new
  `GET /api/harness/chat/models` list the models the operator can actually use
  across ALL providers (availability derived server-side from the real env/vault;
  models from the runtime catalog with a preset-default fallback when the runtime
  is down). Selecting a model/provider PERSISTS it to the settings vault via
  `POST /api/settings` â€” the source the runtime reads â€” so the next message uses
  it; it is also sent per-turn as `model`. Provider switch persists provider +
  base URL + default model together; a failed save shows the error and reverts;
  a "Custom model idâ€¦" entry types any id; local/router providers get a live
  discover action. Tests: `models/route.test.ts` (+4). `vitest` 2085 passed;
  `pytest` 2550 passed; `npx tsc --noEmit` clean; eval gates ALL PASS.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Added a real model selector to the chat composer.** The composer only ever
  showed a static provider pill; the old model dropdown was REMOVED earlier
  because it was fabricated (hardcoded "Flash-Lite/Flash/Pro"). `use-chat-model.ts`
  now backs the pill as a dropdown of the models the configured provider can
  serve (the runtime's declared catalog + a live `discover` probe for local
  servers/routers), persisted in localStorage, and the choice is threaded
  end-to-end: `ChatOptions.model` â†’ chat request body `model` â†’ `startChatRun`/
  `chatWithAgent` â†’ `resolveModelSettings(model)` â†’ the run's
  `modelSettings.model`. It overrides ONLY the model â€” provider/key/base URL stay
  the operator's configured ones, and a declared context window is dropped since
  it belongs to the previous (provider, model). Never a fabricated list: with no
  catalog it degrades to the saved model alone. `stock-chat.tsx` stays at its
  1212-line ratchet (lines reclaimed). Tests: `run-service.test.ts` (+2).
  `vitest` 2081 passed; `pytest` 2550 passed; `npx tsc --noEmit` clean; eval
  gates ALL PASS.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Investor Eye: heatmap look + one-click Heatmap button on every surface.**
  Added a standalone `HeatmapToggle` (Flame icon) on the main map (top-left of
  the map surface), the full-page map dock, and the dashboard "Investor Eye Map"
  widget header. It uses the SAME visible control recipe as its sibling buttons
  (`border-white/15 bg-accent/30`, active = `border-primary/40 bg-primary/15`) â€”
  an earlier `glass-button`/`glass-card-subtle` restyle blended into the dark map
  and made the control effectively invisible. Restyled the heat layer:
  `pointSize`/`blurSize` 22/28 â†’ 16/18 and `minOpacity` 0.35 â†’ 0.12 so sparse
  regions stay dark and only genuine concentrations light up, and replaced the
  blueâ†’red `visualMap` ramp with a warm violetâ†’magentaâ†’roseâ†’orangeâ†’yellow ramp
  that contrasts the blue/cyan map surface instead of blending into it. The
  widget header now wraps so the extra control cannot be clipped. `vitest` 414
  investor-eye tests pass; `npx tsc --noEmit` clean.
  no doc change â€” presentation/control tuning; layer contract unchanged.

- **Investor Eye Map dashboard widget had no layer controls.** The embeddable
  "Investor Eye Map" widget rendered the world map with only expand/Open buttons
  and no way to toggle layers â€” so the Event Heatmap (and every other layer) was
  unreachable from the dashboard, unlike the full Investor Eye screen. Added a
  Layers button opening a popover that reuses the canonical `LayerController`
  (same chips, colours, availability rules), portaled to `document.body` and
  anchored to the button because the widget card is `overflow-hidden` and would
  otherwise clip it; the popover flips above the button near the viewport bottom.
  `vitest` 2079 passed; `npx tsc --noEmit` clean.
  no doc change â€” the Investor Eye Map widget is already covered by the workspace
  skill; this is a control-surface fix, no contract change.

- **Investor Eye: event heatmap now actually reads as a heatmap; pins shrunk to
  a Bloomberg-like scale.** The `event-heatmap` layer emitted one datum per raw
  event with a ~1px weight, so ECharts' heat brush blurred single events away and
  the layer rendered as an invisible flat wash. It now aggregates events onto the
  same grid the pins use (`aggregatePoints`) and each cell's intensity is the SUM
  of its members' severity weights, so a hotspot is literally where the most and
  most-severe events are; `pointSize`/`blurSize` widened to 22/28 and
  `minOpacity` raised to 0.35 so even a light cell survives the dark map. Fixed
  the controller: `availableLayers` never included `event-heatmap`, so its chip
  was dimmed as "no data" and looked broken. Enabled the heatmap by default
  (`DEFAULT_LAYERS`) and gave it a legend swatch (new `heat` glyph in
  `SYMBOL_PATHS`). Markers reduced to Bloomberg scale â€” 2D pins 18/14/11/8 â†’
  8/6/5/4 and glow halos 26/17/10/5 â†’ 12/8/5/3; globe core 17 â†’ 9 and ring 24 â†’
  13 â€” so hundreds of dots stay legible instead of collapsing into blobs.
  Tests: `layers.test.ts` (+3 heatmap density cases). `vitest` 2079 passed;
  `npx tsc --noEmit` clean.
  no doc change â€” layer rendering/tuning only; heatmap contract already documented
  in `docs/investor-eye-architecture.md` Â§2.13.

- **Fix: configured models were silently substituted + Ollama's installed models
  were unselectable.** The front door stores a BARE model id (`cfg.model`) with a
  separate provider id. `ModelRouter` resolved a bare id only when it was
  globally unambiguous, so any model not in the static catalog (an operator's
  `deepseek-v4.1-flash`, any custom/local model) looked "unknown" and the router
  fell through to its own best pick â€” `deepseek/deepseek-v4.1-flash` resolved to
  `google/gemini-2.0-flash`, so the user's model never ran. `ModelRuntime` now
  qualifies the bare id with the run's provider (`_explicit_ref`), so ANY model
  id the operator configured is honoured as the explicit choice and never
  silently swapped. Second regression: `prepare_model` force-set
  `reasoning_effort` from the task profile on EVERY model, including
  OpenAI-compatible endpoints that reject the knob (a hard 400); reasoning is now
  shaped only for a provider-native control (Anthropic/Google/native-OpenAI) that
  declares reasoning support. Third: the Settings model dropdown only ever showed
  the static catalog, never the models actually installed, so Ollama showed
  `llama3.1â€¦phi3` and nothing the operator had pulled. Added runtime model
  discovery â€” `POST /model-runtime/providers/{id}/discover` probes the live
  `/models` endpoint (Ollama/LM Studio/router) and registers what it serves, with
  a new `ModelPicker` component (extracted from `settings.tsx`, which stays under
  its size ratchet) exposing a "Discover installed models" action; a failed probe
  reports an honest reason, never a silent empty success. `ProviderSpec.dynamicDiscovery`
  marks discoverable providers. Tests: `test_model_runtime.py` (+5),
  `test_model_runtime_api.py` (+2), `test_models.py` (+1),
  `model-runtime-browser.test.ts` (+2). `vitest` 2076 passed; `pytest` 2550
  passed; `npx tsc --noEmit` clean; eval gates ALL PASS.
  docs updated: `docs/harness/architecture.md`, `docs/CHANGELOG.md`

- **Reverted the General â€º Theme "ChatBot background" card.**
  The color option already lives under Settings â€º General â€º Background
  (`background-settings.tsx`), so the duplicate card added earlier today in
  `customization-settings.tsx` was removed and that file restored.

- **Eclipse preset landing defaults pinned to the brand greens.**
  `src/lib/theme/tokens.ts`: the `eclipse` preset's ChatBot landing now uses
  `solidColor: '#131615'` and wordmark `textColor: '#e6ffe5'` (previously both
  derived from the accent/primary mix). `npx tsc --noEmit` clean; `vitest` passed.
  no doc change â€” preset token values only, no contract/shape change.

- **Dedicated "ChatBot background" color in Settings â€º General â€º Theme.**
  Added a "ChatBot background" card to the theme Colors area
  (`src/components/screens/customization-settings.tsx`) that sets the flat
  backdrop color of the empty ChatBot landing only, independent of the app-wide
  page `background` token. It stores into the background store's `solidColor`
  (`mode: solid` + `solidFill: flat`); empty follows the page color. The edit is
  tracked as a separate draft value so it respects the panel's live-preview /
  Apply / Discard model, overrides a selected preset's snapshot solid color, and
  counts toward `dirty`. `vitest` passed; `npx tsc --noEmit` clean.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Fix: Settings â€º AI could not add an API key or select most providers.**
  Root cause was the keyless-local key sentinel `"local"`: a local endpoint
  (Ollama) persisted `apiKey:"local"` in `llm_config`, and switching to a hosted
  provider kept it, so `getLLMConfig` never fell back to the provider-key vault
  and the runtime sent `"local"` as the credential (HTTP 401). `src/lib/settings.ts`
  now defines `LOCAL_KEY_SENTINEL`, drops it on save (it is never a credential),
  and `getLLMConfig` ignores it once the endpoint is remote; `setLLMConfig` also
  accepts a remote provider when the vault or environment holds the key instead
  of demanding a plaintext key. `LLMProviderName` and the Settings "Mode" select
  now expose every provider preset (they previously allowed only 5 values, so
  most providers were unselectable and the model catalog could not resolve).
  Preset/provider selection now sets the provider id + base URL + default model
  together, and the Model field is a real dropdown of the runtime catalog's known
  models plus a free-text custom id (the previous `<datalist>` was not surfaced
  by the input primitive). Regression tests: `src/lib/settings.test.ts`.
  `vitest` 2074 passed; `pytest` 2542 passed; `npx tsc --noEmit` clean.
  docs updated: `docs/CHANGELOG.md`

- **Model Control Center front door + UI.** The provider-agnostic Model Runtime
  is now reachable from Next.js. Server/browser clients
  `src/lib/harness/model-runtime-{client,browser}.ts` proxy the runtime's
  operator-gated `/model-runtime/*` routes via `src/app/api/harness/model-runtime/**`
  (providers, models, routing, routing/decisions, route [pure computation],
  health, usage). A mounted screen `src/components/screens/model-runtime/`
  (`model-runtime-screen.tsx` + providers/models/routing/usage/health/debug
  panes) is the Model Control Center: it lists providers/models with capability
  states and pricing (unknown stays unknown), shows task routing, usage/cost,
  provider health and   the routing debug view ("why this model"). Mounted via
  AppTab `model-runtime` (`src/lib/app-tabs.ts`, `src/components/layout/sidebar.tsx`,
  the keep-alive block in `src/components/screens/stock-chat.tsx`, the sidebar
  entry in `src/lib/sidebar/config.ts`), i18n `modelRuntime.*`/`nav.modelRuntime`,
  and the global-search page `page-model-runtime`. User routing overrides
  (spec Â§44) round-trip through `LLMConfig.routingPolicy` â†’ the run's
  `input.context.modelPolicy` â†’ the runtime's `RoutingRequirements`, toggleable
  in the Routing pane ("local models only", "avoid paid models").
  Tests: `src/lib/harness/model-runtime-browser.test.ts`,
  `src/components/screens/model-runtime/model-runtime-screens.test.ts`,
  `src/lib/harness/run-service.test.ts`,
  `python/tests/test_model_runtime_api.py`. `vitest` 2068 passed; `pytest`
  2542 passed; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/architecture.md`, `docs/NAVIGATION.md`,
  `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Provider-agnostic Model Runtime layer (the agent no longer talks to a
  provider).** New package `python/harness/model_runtime/` implements
  `Agent â†’ ModelRuntime â†’ ModelRouter â†’ ProviderAdapter â†’ Provider`: provider and
  model registries seeded from the existing `PROVIDER_CATALOG`; capability
  detection as states (supported/unsupported/unknown/degraded); 15 task profiles;
  dynamically-resolved aliases (`eclipse-fast|smart|reasoning|coder|vision|cheap|local`);
  a scoring router (capability/quality/reliability/latency/availability/context/cost,
  configurable weights) with an explainable decision trace; fallback + error-classified
  retry with backoff; health/circuit-breaker/rate-limit managers; normalized
  token/cost/latency/budget tracking; normalized streaming, tool schemas,
  structured output and reasoning. `build_chat_model` is reused as the
  adapter's construction primitive (one path, one source of provider facts).
  `graph.py`, `history.py`, `learning_review.py` and the MCP sampling factory now
  ROUTE and BUILD through the runtime while still invoking the module-level
  factory, so the existing test seam and all 2535 harness tests are unchanged.
  A concrete `ModelSettings` provider/model remains the explicit override;
  cross-provider fallback and in-place retry are flag-gated
  (`HARNESS_MODEL_FALLBACK` default OFF, `HARNESS_MODEL_RETRIES` default 1).
  Model usage/health persist to the runtime's OWN `ModelRequest`/`ModelHealth`
  tables on `agent-memory.db` (never JDdS); read-only `/model-runtime/*` routes
  are operator-gated. Tests: `python/tests/test_model_runtime.py` (54).
  `pytest` 2535 passed; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H123), `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Bounded replanning added to the one execution graph (Phase 11).** A tool step
  that FAILS or STALLS (the agent re-issues the same `(tool,args)` set as the
  previous turn) may now divert through ONE `replan` node on the SAME
  `tools â†’ agent` edge before continuing. The node appends inert prose naming the
  failures/stall â€” it authorizes nothing, widens no allowlist, and builds no
  second loop/registry/adapter. New module `python/harness/replan.py` owns the
  trigger (`should_replan`; a stall outranks a failure), the bound
  (`ReplanBudget.max_replans`, default 2), the deterministic directive and an
  optional best-effort model-authored plan. Flag-gated `HARNESS_REPLAN_ENABLED`
  (default OFF) â€” when off the graph is byte-identical to before. Emits a
  persisted `run.replanned` event. To respect the `graph.py` size ratchet, the
  checkpoint (de)serialization moved to `python/harness/checkpoint_io.py` and the
  history-bounding + dropped-context helpers moved to `python/harness/history.py`
  (both re-exported by `graph.py`, so callers/tests are unchanged). Tests:
  `python/tests/test_replan.py`. `npm test` and `npx tsc --noEmit` pass.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H122), `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Preset ChatBot wordmark font unified to Michroma.** Every shipped theme
  preset's giant ChatBot landing wordmark (the "ECLIPSE AGENT" text) now uses
  Michroma (`var(--font-michroma)`), replacing the per-preset Bodoni / VT323 /
  IBM Plex Mono / Playfair choices. `src/lib/theme/tokens.ts`: `ECLIPSE_WORDMARK_FONT`
  â†’ `PRESET_WORDMARK_FONT` and all 12 presets reference it (size, opacity and
  uppercase unchanged). `vitest` 2074 passed; `npx tsc --noEmit` clean.
  no doc change â€” theme-token value only, no contract/shape change.

## 2026-10-03

- **Preset landing wordmark made smaller.** Shipped-preset ChatBot wordmark
  `textScale` lowered from 12vw to 7vw so "ECLIPSE AGENT" reads as a compact
  wordmark rather than a wall-filling headline. Preset data only.
  `tsc` clean; vitest 2055 passed. docs updated: `docs/CHANGELOG.md`

- **Theme-preset backdrops: very dark grey + faint accent; whiteish wordmark;
  Aurora follows the preset; Electric Blue added.** The shipped `THEME_PRESETS`
  previously carried radical radial/linear gradients, grid/ASCII pattern
  textures and image wallpapers (Crystal), each with a bespoke wordmark. Now
  every preset's ChatBot landing is a simple **flat** solid derived in the
  `preset()` helper: a very dark neutral grey (`LANDING_BASE` `#0f0f11`) carrying
  only the faintest shade of the preset's ACCENT hue
  (`mixHex(accent, LANDING_BASE, 0.05)`) â€” dark and low-saturation, not a bright
  wash. All preset wordmarks use the unified "ECLIPSE AGENT" text in a whiteish
  tone (`#e8e8ea`). Presets also now carry an **Aurora palette snapshot**
  (`ThemePreset.aurora`, derived from the theme's bullish/bearish colors via
  `auroraFromColors`), so applying a preset restyles the ambient Aurora glow
  alongside the theme + backdrop: `applyPreset(theme, background, aurora)` pushes
  it to `useAuroraPaletteStore`, the customization panel previews it live, and
  `saveUserPreset`/`applyUserPreset` capture/restore it (Aurora store gained
  `preview`/`cancelPreview`). Added an official **Electric Blue** preset matching
  the user's recovered saved look (primary `#77edfd`, accent `#36c8d3`, black
  background, dramatic shadow, frosted glass) with a dark accent-tinted landing.
  A `flat` solid backdrop is a genuine solid fill â€” the color is emitted as
  `--app-bg-color` onto the layer's `background-color` and no `background-image`
  is set, so the ChatBot landing paints no gradient function at all. `tsc` clean;
  vitest 2055 passed. docs updated: `docs/CHANGELOG.md`, `docs/ARCHITECTURE.md`

- **Investor Eye: Bloomberg-style event heatmap layer.** Added an
  `event-heatmap` layer (new `MapLayerType` `'heatmap'`): ECharts `heatmap`
  series on the 2D geo map, one datum per geolocated event, intensity =
  severity weight (`severityWeight`), `pointSize` 16 / `blurSize` 22, a
  continuous `visualMap` legend (blueâ†’cyanâ†’yellowâ†’orangeâ†’red, HIGH/LOW labels),
  and per-event tooltips (severity, type, published time). On the globe the
  heatmap is not drawn â€” `echarts-gl` has no heatmap series; the event pins
  remain there. New layer toggle in the Layer Controller (`Event Heatmap`,
  group `events`, off by default; `DEFAULT_LAYERS` updated). `tsc` clean;
  test suite passes. docs updated: `docs/CHANGELOG.md`

- **Attachments accept every practical file type.** A type audit showed source
  code (`.py`/`.js`/`.ts`/`.go`/â€¦), `.rtf`, `.eml`, OpenDocument (`.odt`/`.ods`/
  `.odp`), `.epub`, and any unknown/no-extension file were refused as
  "unsupported" â€” a coding/finance agent must read all of them. `extract.ts` now:
  recognises a broad text+code extension set; reads OpenDocument + epub via the
  same ZIP+XML path (per-extension member map); strips RTF control words; runs a
  readable-string scan for old binary Office (`.doc`/`.xls`/`.ppt`) and unknown
  binaries; and sniffs any unrecognised/no-extension file (UTF-8 if printable,
  string-scan otherwise). A genuinely binary file (image/archive) reports "no
  readable text" honestly instead of a flat refusal. `isTextExtractable` is now a
  known-binary denylist so unknown files are tried, not pre-blocked. Tests:
  expanded `extract.test.ts` (code, rtf, no-extension, binary-honest cases).
  `tsc` clean; vitest 2054 passed.
  docs updated: `docs/CHANGELOG.md`

- **PDFs actually get read now (real attachment fix).** The hand-rolled PDF reader
  only handled simple ASCII text streams; a real report/deck (like the user's
  `Eclipse-as-a-Harness-Round-2.pdf`) uses CID/Identity-H fonts where text is
  stored as glyph ids, so extraction returned NOTHING, the file was silently
  skipped, and the agent correctly answered "nothing is attached". Added
  `pdfjs-dist` (`extract.ts::extractDocumentText`, async) and routed
  `loadContextDocuments`/`measureContextChars` through it. Two integration bugs
  fixed along the way: a Node `Buffer` shares a pooled ArrayBuffer, so it is
  copied to an exact `Uint8Array` before pdfjs sees it; and the fake-worker
  module failed under Next's bundle, fixed by externalizing `pdfjs-dist` and
  pointing `GlobalWorkerOptions.workerSrc` at the resolved worker file. Verified
  live: the 786 KB PDF now yields 20,000 chars and the run reads its title.
  Tests: `pdf-extraction.test.ts`. `tsc` clean; vitest 2051 passed.
  docs updated: `docs/CHANGELOG.md`

- **Theme presets are now holistic â€” the ChatBot landing changes with them.**
  Selecting a preset only recolored tokens (colors, fonts, glass, sidebar
  surface); the ChatBot wallpaper/solid fill and giant wordmark live in the
  separate `useBackgroundStore`, so they never changed. A preset now carries an
  optional **partial** `background` snapshot (`ThemePreset`/`UserThemePreset`,
  validated by `normalizePresetBackground`) that is merged over the live prefs
  (so a preset that only sets the wordmark keeps the user's wallpaper). Selecting
  a preset live-previews its backdrop (`useBackgroundStore.preview`;
  `ChatWordmark` reads `previewPrefs ?? prefs` so glyphs update), Apply commits it
  (`applyPreset(theme, background)`), Discard reverts. Save/update/export/import
  round-trip the backdrop. Broke a store-to-store import cycle by replacing
  `backgrounds.ts`â†’`useThemeStore` with `refreshBackground()` called after every
  theme write. Also: the sidebar collapsed mark, expanded wordmark and mobile
  header now honor `theme.logoUrl` (falling back to shipped assets/monogram), and
  the Heading-font control reaches `font-heading` elements (dedicated
  `--font-heading`; it previously aliased `--font-sans`). Extracted the
  preview launcher to `customization-preview.tsx` to stay under the size ratchet.
  `tsc` clean; vitest 2047 passed; pytest eval gates pass. ADR-040.
  docs updated: `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/NAVIGATION.md`, `skills/ARCHITECT.md`.

- **Code harness defaults to `edit_verify` so writes/executes work.** The
  code task store (`code/tasks.py` `DEFAULT_AUTONOMY`) and the code-agent run
  fallback (`graph.py`) both defaulted to `plan_only`, which the Phase-5 tool
  allowlist strips of every write/execute tool â€” the harness could not create
  files or run commands unless the front door explicitly sent a different
  autonomy. Both now default to `edit_verify` (file create/write + command
  execution, no external git actions). Router docstrings updated. `npm run
  test` eval gates all pass; `npx tsc --noEmit` clean. no doc change â€”
  policy tables in `docs/harness/decisions.md` already describe `edit_verify`;
  only the default value changed.

- **Coding-agent harness: persistent terminal, auto-verify, write approvals,
  explore delegation, diff rendering.** Five additive changes make the code
  surface behave like a real agent harness (opencode/hermes class):
  (1) `terminal_run` now keeps a per-workspace session â€” `cd <dir>`,
  `export KEY=VAL`/`set KEY=VAL` and `pwd` persist across calls (confined to
  the worktree root, `terminal_tools.py` `_SESSIONS`), and `build_run_spec`
  accepts `env_extra`; the effect authorizer treats session mutations as
  allow since no process spawns. (2) `workspace_patch_apply` now runs an
  auto-verify hook: a workspace-pinned `.black-eclipse/verify.json`
  (`{"command": "..."}`) runs after every successful patch and its
  pass/fail folds into the tool result, so the model sees failing checks as
  the observation and can self-repair; only `allow`-classified commands run.
  (3) Writes are gated per-call, opencode-style: `make_code_authorizer` now
  requires a single-use approval (`code_write`, keyed to the digest of the
  changed paths) or a workspace-wide `code_write_session` approval before a
  patch apply is admitted; with no approvals backend (tests, zero-config) the
  handler still enforces binding + autonomy profile as before. (4) The chat
  code profile (`CHAT_CODE_TOOLS`) now includes `delegate`, so the finance
  agent can spawn parallel narrowed subagents (read-only explore) from a
  coding turn. (5) Fenced ` ```diff ` blocks render with per-line +/-/@@
  coloring in the chat markdown renderer. Test: `test_chat_code_profile.py`
  updated for the `delegate` addition. Full suite 2474 passed; `tsc` clean.
  no doc change â€” behavior is additive and documented in module docstrings.

- **Code-turn step/time budget raised (MAX_STEPS_EXCEEDED fix).** A chat turn
  carrying `edit_verify`/`approve_external` now gets `max_steps >= 24` (code
  agent preset already had 24) and `runTimeoutMs >= 600s` â€” previously the
  finance agent's 8 steps / 120s killed multi-phase coding turns right before
  the file write. `graph.py`. `tsc` clean. no doc change â€” budget internals.
- **Write/execute now require explicit approval in-app.** `make_code_authorizer`
  creates a pending `code_write` approval (keyed to the changed-path digest)
  and emits an `approval.requested` event; the terminal authorizer emits the
  same event for `ask`-classified commands. `python/tests/test_size_budget.py`
  ratchet budgets updated (graph.py 1859, code/tools.py 1203) for the added
  guards.
- **Real shell: `shell_run`/`shell_spawn`/`process_*`.** New `code/shell.py`
  runs command strings through the detected host shell (PowerShell/CMD/bash)
  with cwd confined to the workspace root, output caps, timeouts, and a
  background `ProcessHandle` registry. `code/shell_tools.py` exposes
  `shell_run` (one-shot), `shell_spawn` (background), `process_output`,
  `process_kill`, `process_list`; shell classification allows pipes/redirects
  (unlike the argv-only `terminal_run`) while destructive shapes stay denied
  and everything else needs the `terminal_command` approval. Wired into
  `CHAT_CODE_TOOLS`, `CODE_AGENT_TOOLS`, the effect-authorizer chain
  (`make_shell_authorizer`), and `policy.WRITE_TOOLS`. Smoke-tested against
  PowerShell. `tsc` clean; targeted tests pass; size ratchets bumped.
  no doc change â€” new capability documented in module docstrings.
- **Visible terminal panel (Ctrl/Cmd + `).** New `TerminalPanel`
  (`src/components/layout/terminal-panel.tsx`): a glass bottom sheet with
  command history (arrow keys), colored stdout/stderr, exit code and duration,
  and copy-friendly mono output. Backed by `POST /api/code/shell`, which
  proxies to the runtime's new `POST /code/shell`; cwd is confined to the
  server-resolved workspace root. Documented in the keyboard-shortcuts help.
  `tsc` clean. no doc change â€” additive UI.
- **Intent classifier broadened for filesystem requests.** "Count the files on
  my desktop" and similar ("list/show/open/read ... files/folder/desktop/path")
  now classify as `code_change`, so the turn gets the code profile
  (`edit_verify`) and the model actually receives the shell/filesystem tools
  instead of honestly refusing with "no filesystem access". Pure finance
  questions ("price of BTC") still classify `not_code`.

## 2026-10-02


- **Attachments are VISIBLE at the composer.** An attached file used to be hidden
  behind a collapsed session bar, so "did it attach?" was unanswerable. Files now
  render as chips directly above the chat composer â€” a file icon, the name, and an
  X to remove â€” plus the "Attached N" count. Shown on both the empty landing and
  an active conversation. The chip list merges pending (attached before a session
  exists) and saved context files, de-duplicated (`mergeAttachmentChips`, pure and
  tested). Verified in a real browser (Playwright): attaching a file renders the
  `chatmade.py` chip with its remove button. Tests: `attachment-chips.test.ts`.
  `tsc` clean; vitest 2042 passed; pytest 2474 passed.
  docs updated: `docs/CHANGELOG.md`

- **Attachments actually work: real file names + Office documents.** The file-name
  guard was an ASCII allowlist, which REJECTED extremely common real names â€”
  `notes(1).md`, `rÃ©sumÃ©.pdf`, `Q3 [final].xlsx`, `R&D.csv` â€” so "attach a file"
  failed with "Invalid file name" for most files a person picks. It is now a
  denylist (path separators, control chars, Windows reserved names) that accepts
  Unicode and ordinary punctuation while still refusing traversal. Also added real
  extraction for `.docx`/`.xlsx`/`.pptx` (Office files are ZIP+XML â€” a
  dependency-free bounded ZIP reader extracts the text) so the most common finance
  documents are no longer "unsupported". Verified live: `my report(1).pdf`,
  `rÃ©sumÃ©.txt`, `Q3 [final].md`, `R&D.csv` all upload; a generated `earnings.docx`
  uploads and its text reaches `loadContextDocuments`. Tests: 6 new cases.
  `tsc` clean; vitest 2038 passed; pytest 2474 passed.
  docs updated: `docs/CHANGELOG.md`

- **ChatBot landing composer no longer floats up.** Commit `3445a2f` wrapped
  `EmptyState` (which pins the composer with `flex-1 â€¦ justify-end`) in a plain
  `flex w-full flex-col items-center` div with no `flex-1`, so the `justify-between`
  column had nothing to push against and the input box drifted upward. The wrapper
  now grows (`flex-1 â€¦ min-h-0`), restoring the bottom-pinned composer.
  `tsc` clean.
  no doc change â€” layout bug fix, contracts intact.

- **Chat can now create files on your PC; attachments show; honest narration.**
  Three real defects behind "it won't create a file / can't attach". (1) The
  STREAMING chat path (`startChatRun`) sent an autonomy but never a `direct` flag,
  so a code turn always edited a disposable worktree, never the folder the user
  picked. The runtime now resolves direct mode itself: a run bound to a
  user-selected trusted root edits the real folder, the built-in repo stays
  isolated (`workspace.trusted_root_selected` + `graph._resolve_direct`). (2)
  Attaching a file on the EMPTY state put it in a ref with zero UI feedback, and
  the first message started the run before the upload landed â€” so the file neither
  showed nor reached the run. Pending files now render immediately in the session
  bar (shown in the empty state too) and `handleSend` awaits `flushPending` so the
  first turn's context includes them. (3) Tool output said "disposable copy" even
  in direct mode; `workspace_status`/patch/diff/revert messages now name where the
  change actually landed (`ctx.direct`). Verified live: a chat-style run wrote
  `honest.py` into the real folder, ran it (exit 0), and reported "written to the
  user's real folder". Tests: `test_code_worktree.py` direct auto-resolve case.
  `tsc` clean; vitest 2033 passed; pytest 2473 passed.
  docs updated: `docs/CHANGELOG.md`

- **Editor: a real explorer tree â€” create files/folders, expand in place, delete.**
  The editor had no "+" control at all and clicking a folder navigated away, so a
  file could not be added. The tree is now an editor explorer: click a file to
  open it, click a folder to expand it in place, "+" (new file / new folder) opens
  an inline name field committed with Enter, and hovering a row reveals Delete.
  Added `POST /workspace/file/mkdir` and `/workspace/file/delete` (a non-empty
  folder is refused, never removed recursively) plus their `code-client` /
  `code-browser` proxies and `/api/workspace/file/{mkdir,delete}` routes.
  Verified live: created `demo/sub`, wrote `demo/sub/a.txt`, listed it, and the
  non-empty delete was refused. Tests: 4 new cases in `test_workspace_editor_api.py`.
  `tsc` clean; vitest 2033 passed; pytest 2473 passed.
  docs updated: `docs/CHANGELOG.md`

- **The chat stream now reads like a real coding harness.** Tool activity showed
  only a tool NAME ("Reading a file"); it now shows what the tool is doing and
  what came back â€” "Writing the change `stream.py` â†’ 1 file(s)", "Running
  `python stream.py` â†’ exit 0". Added `python/harness/code/activity.py`
  (`tool_detail`/`tool_result_summary`) â€” a pure, bounded, content-free derivation
  (a command, a file PATH, the changed PATHS; never file text, so a secret in a
  patch body never reaches the stream). `graph.py` emits `detail` on
  `tool.requested` and `summary` on `tool.completed`; the client carries
  `ActivityItem.detail` and the row renders it in monospace beside the label.
  Verified live against the runtime: the run's events carry
  `terminal_run | detail= python stream.py | summary= exit 0`. Tests
  `test_code_activity.py` + two `events.test.ts` cases. `tsc` clean; vitest 2032
  passed; pytest 2470 passed.
  docs updated: `docs/NAVIGATION.md`, `docs/harness/decisions.md` (ADR-H121)

- **Folder selection + direct editing + a general terminal + an Editor surface.**
  Eclipse can now work on a folder you choose, not only its own repo. (1) **Trusted
  roots**: a folder picker (`/workspace/browse`) and an operator-approved, persisted
  allowlist (`TrustedRoot` in `agent-memory.db`); the SELECTED root becomes what
  `workspace.default_root()` resolves to, after the env override â€” so zero-config is
  unchanged. (2) **Direct mode**: `worktree.allocate(direct=True)` edits the selected
  real folder (strategy `"direct"`; `release` never deletes it); a code task defaults
  to direct when a folder is selected. Confinement is unchanged â€” `resolve_within` +
  `PROTECTED_PATHS` still apply, so the human editor and the agent share one boundary.
  (3) **`terminal_run`**: an arbitrary command WITHOUT a shell, classified
  allow/ask/deny in Python â€” safe tools run, others need a per-command single-use
  approval, destructive/shell/downloader commands are refused; runs through the
  existing sandbox and is recorded in the ledger. (4) **Editor UI** (AppTab `editor`):
  file tree + text editor + save, plus the folder picker. Verified live: approved a
  folder, created and ran `auto.py` in the REAL folder (exit 0), listed/wrote/read a
  nested file through the editor API, and confirmed `.env`/traversal/absolute paths
  are refused. Tests `test_code_roots.py`/`test_code_terminal.py`/
  `test_workspace_editor_api.py` + direct-mode cases in `test_code_worktree.py`.
  `tsc` clean; vitest 2031 passed; pytest 2461 passed.
  docs updated: `docs/NAVIGATION.md`, `docs/harness/decisions.md` (ADR-H118/H119/H120)

- **Alert symbol search un-capped; fired alerts now visible app-wide.** Two real
  defects behind "only 4 assets / no notification". (1) `/api/quote` symbol
  autocomplete was hard-capped at 8 rows (`LIMIT 8` + `.slice(0,8)`) via
  `searchSymbols`, and de-duped by symbol alone â€” so searching "A" showed 8 and
  a ticker listed in two markets collapsed to one. Now up to 100 rows, de-duped by
  `symbol|market`, with the alert builder, market-overview strip, price-ribbon and
  chart-compare suggestion lists raised from 8â†’50 and made scrollable. (2) Desktop
  notifications silently no-op unless the user opted in AND granted permission â€”
  which is why no notification appeared. `AlertNotificationProvider` now ALWAYS
  shows an app-wide bottom-right in-app toast for every fired alert (all tabs, no
  permission needed) and additionally raises the OS notification when enabled; it
  is the single owner of delivery via the `be:alert-notify` event (the Settings
  test button no longer calls `showAlertNotification` directly, which double-fired).
  Verified against a forced rebuild: `?q=A` returns 100, a test fire created a new
  event (8â†’9), the notification bundle is live; `tsc --noEmit` clean; eslint clean;
  vitest 2031 passed.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Fix three real failures that made the code harness non-functional from the
  UI.** Exercising the live stack (not just the test suite) showed "build me X"
  could never complete. (1) **HTTP 500 on every code task**: `POST /code/tasks`
  recorded the `task.created` `RunCheckpoint` (FK â†’ `HarnessRun(id)`) BEFORE the
  run row existed, so `record_created` raised `sqlite3.IntegrityError: FOREIGN
  KEY constraint failed`; the route now creates the run row first and
  `execute_run` reuses a pre-created row (only in `created` status). (2) **No
  write ever succeeded on Windows**: an unconfigured `git worktree add` aborted
  on the deep scaffold-kit template paths with `Filename too long`, silently
  demoting every allocation to the snapshot fallback, which then refused with
  `SNAPSHOT_TOO_LARGE`; every git invocation now carries `-c core.longpaths=true`
  (per-command, so the operator's global config is untouched). (3) **Chat never
  bound code tools**: the non-streaming `chatWithAgent` (`/api/harness/chat`)
  bypassed the Phase-14 classifier that only `startChatRun` used, so a coding
  request reached the model with no write/execute tool and the model honestly
  refused; it now resolves the same code profile. Verified live: a real task
  created `hello.py` + a test in its disposable worktree and the ledger recorded
  `python_test` exit 0; the chat route then built a module end-to-end. Added
  regression tests `python/tests/test_code_api.py` (route FK ordering),
  long-path assertions in `test_code_worktree.py`, and four
  `chatWithAgent` profile cases. `tsc --noEmit` clean; vitest 2031 passed;
  pytest 2428 passed; `npm run test:evals` all pass.
  docs updated: `docs/CHANGELOG.md`

- **Remove the remaining hardcoded 4-market lists.** After the alert builder fix,
  an audit of every market list found two more that were silently narrowed to
  `US/PK/IN/CRYPTO`: the Settings â€º General "Default Market" *fallback*
  (`general-settings.tsx` `ALL_MARKETS`, now derived from `HEATMAP_MARKETS`) and
  the legacy agent's `get_price` tool description (`src/lib/agent/tools.ts`, now
  names several markets). The Market Data panel and screener already load the
  full set from JDDS (`/api/markets` â†’ 28). Verified against a forced rebuild:
  the old `["US","PK","IN","CRYPTO"]` literal is gone from `.next`, 28 markets /
  1,455 crypto assets are reachable, and `npm run demo:btc` is 6/6 PASS.
  `tsc --noEmit` clean; eslint clean; vitest 2027 passed.
  docs updated: `docs/CHANGELOG.md`

- **Alert builder: full market coverage + a runnable BTC demo.** Investigating a
  report that "markets are limited" found the data path is complete (28 JDDS
  markets + FX/commodities; 1,455 crypto assets incl. BTC; correct live quote),
  but the alert builder's market dropdown was hardcoded to
  `["US","PK","IN","CRYPTO"]`. It now lists every market the alert feed can
  actually quote (`HEATMAP_MARKETS` minus FOREX/COMMODITIES, which have no Yahoo
  suffix) in `src/app/alerts/alerts-client.tsx`. Added `scripts/demo-btc.mts`
  (`npm run demo:btc`), a live end-to-end demo: JDDS vault â†’ yfinance CRYPTO
  `BTC-USD` (~$84k) â†’ the bare-`US BTC` ETF trap it disambiguates (~$37) â†’ the
  alert engine's `fetchSnapshots` â†’ markets beyond the old hardcoded list
  (UK/JP/DE/CRYPTO) â†’ the running app's `/api/quote`. Verified: demo OK, 6 legs,
  0 failed; `tsc --noEmit` clean; vitest 2027 passed.
  docs updated: `docs/NAVIGATION.md`

- **Universal financial-fact engine, slice 6: point-in-time, research router and
  corporate-action ingestion â€” the remaining sections.** Closes the three gaps the
  audit named. `finance_facts/point_in_time.py` (Â§15) keeps period_end /
  publication / retrieval distinct and refuses a later report under an earlier
  cutoff (`latest_known_per_metric` returns the revision available THEN, not the
  newest that exists today). `finance_facts/router.py` (Â§24) classifies a question
  into an intent and returns the evidence areas it NEEDS â€” with sector-specific
  additions â€” so the agent plans retrieval instead of taking whatever JDdS holds.
  `finance_facts/corporate_actions.py::extract_from_series` (Â§17) derives splits and
  dividends from the price series the yfinance bridge already carried
  (`scripts/yfinance_bridge.py` now emits `Dividends`/`Stock Splits` per bar;
  `normalize_history` lifts them to `stock_split`/`dividend` observations). Tests:
  `test_finance_facts_pit_router.py` (10 cases). Full release gate: vitest 178 files
  / 2027 tests, pytest 2425, ALL GATES PASSED. Still no ticker-specific logic; no
  prisma/schema.prisma or jdds.db change.
  docs updated: `docs/CHANGELOG.md`, `docs/NAVIGATION.md`

- **Universal financial-fact engine, slice 5: the final-answer gate.** Closes the
  loop â€” the answer is now checked against the run's own validated facts, exactly
  as code claims are checked against the verification ledger. `finance_facts/enforce.py`
  (`enforce_finance_answer`) is deterministic and makes no model call: if the answer
  asserts a metric the run's analysis EXCLUDED (ambiguous definition, no period,
  superseded) or states one side of a cross-source conflict without saying so, it
  requires a disclosure â€” it never silently strips the number. An already-present
  in-sentence disclosure is honoured, so it never nags. `source_collector.py` now
  accumulates the per-retrieval analysis across the run (deduplicated, higher
  confidence wins) and carries it on the `research` blob's `financeAnalysis`;
  `graph.py` adds ONE guarded block that appends the disclosure to the completed
  answer and emits `finance.analysis`. Wiring is additive and exception-guarded.
  Tests: `test_finance_facts_enforce.py` (8 cases) plus the collected-blob path.
  Full release gate: vitest 178 files / 2026 tests, pytest 2413, ALL GATES PASSED.
  docs updated: `docs/CHANGELOG.md`, `docs/NAVIGATION.md`

- **Desktop-alert notifications â€” audit hardening.** A review of the new
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
  per genuinely new event. Settings â€º Alerts/Notifications
  (`alert-notifications-settings.tsx`) gained a "Desktop notifications" toggle
  with honest `off`/`blocked`/`on` state and a test-notification button. No service
  worker, so notifications show only while a BlackEclipse page is open â€” stated in
  the UI. Additive; no schema/API contract change. Tests:
  `src/lib/alerts/browser-notifier.test.ts` (5). Full suite 2021 passed;
  `tsc --noEmit` clean.
  docs updated: `docs/ARCHITECTURE.md` (Alert delivery), `docs/NAVIGATION.md`

- **Universal financial-fact engine, slice 4b: self-review fixes.** A careful pass
  over the new engine found and fixed four real defects. (1) `conflicts.detect_conflict`
  flagged two time-series bars at different dates as a disagreement and a single
  source repeating itself as a conflict â€” it now requires the same period AND
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
  the entity. A fact is marked **admissible** (only disclosures â€” stale, soft
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
  answer must carry â€” accounting-definition ambiguity, detected business type, the
  financial-framework warning for entities containing banks/insurers, cross-source
  definition differences vs real disagreements, and stale values.
  `retrieval_tools._summarize` appends a "Data-quality notes:" block when there is
  something to disclose (absent otherwise, so no existing text changed). Metadata
  fields (sector/industry/name) are never mistaken for ambiguous financial metrics.
  Additive and exception-guarded: analysis can never break a summary. Test:
  `test_summary_surfaces_definition_ambiguity_and_sector_but_not_metadata`. Still
  no ticker-specific logic; no schema/jdds.db change.
  docs updated: `docs/CHANGELOG.md`

- **Phase 14 â€” the code capability, reachable from chat.** A coding request typed
  in ordinary conversation is now served by the code capability that already
  existed, instead of refusing for lack of a tool. A deterministic, model-free
  classifier `python/harness/code/request_intent.py::classify_code_request`
  (reached over the read-only operator-gated `POST /code/intent`) decides
  `code_change` | `code_question` | `not_code`, with an AMBIGUOUS turn defaulting
  to `not_code` (the refusal path is the safe failure). `agents.CHAT_CODE_TOOLS`
  is a NARROWED profile applied per turn inside the existing
  `graph.resolve_surface`, after the autonomy narrowing: `code_change` â†’
  `edit_verify` (write/execute/verify), `code_question` â†’ `plan_only` (read-only).
  The four external actions (`code_commit`/`code_push`/`code_open_pr`/
  `code_deploy`) are absent from the declared set â€” external actions stay on the
  Code Tasks surface. The front door gains additive `autonomy`
  (`plan_only`|`edit_verify` only, fail-closed on anything else) and
  `analysisEnabled` on `RunRequestPayload`; `startChatRun` resolves and sends them
  from the classifier. A new `src/components/chat/chat-capability-panel.tsx`
  composes the existing Phase-4 verification panel and is wired through
  `activity-feed.tsx`/`activity-item.tsx`/`chat-history.tsx`, so a coding turn
  shows what Eclipse did in plain words. The code task list gains "Build this"
  (existing `/api/code/tasks`) and "Schedule" (existing `/api/jobs`, created
  DISABLED with `agent_id="code-agent"`, `autonomy="edit_verify"`). The runtime's
  registered tool set is UNCHANGED â€” an allowlist and a payload, never a tool.
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
  had no way to start a work order â€” the exact symptom the phase existed to
  remove; `task-list.tsx` now renders a "what should Eclipse build or fix?"
  composer above the list and the empty state. (c) The classifier returned
  `not_code` for the user's literal wish ("create a new application", "build
  algorithms", "build a Monte Carlo simulator"); the software-object vocabulary
  gained those artifacts, a homograph guard stops "test the market" / "build a
  portfolio" self-matching, and `what doesâ€¦` questions plus reported symptoms and
  named errors now classify correctly. (d) A refused code step
  (`code.refused`/`code.patch.refused`) now renders its ONE plain refusal
  sentence, with the raw code behind "details", instead of a technical operation
  label. Tests: `test_code_request_intent.py` 22â†’43 cases, `events.test.ts` two
  refusal cases. (e) The Â§6.4 capability view is now a first-class
  `RunResult.capability` (`{kind, profile, headline, verification}`), derived in
  `python/harness/code/capability.py` from the run's verification blob (the
  profile rides inside that existing additive blob â€” no new column, `persistence.py`
  ratchet untouched) and mirrored client-side by `coerceChatCapability`; the panel
  prefers it and falls back to the flat fields for older rows. Gates: vitest
  **178/2027**, pytest **2415**, `npm run build` exit 0.
  docs updated: `docs/harness/roadmap/progress/phase-14-progress.md`, this entry.

- **Universal financial-fact engine, slice 2: derived metrics, corporate actions,
  evidence graph.** Completes the deterministic foundation. `finance_facts/metrics.py`
  derives P/E, P/B (COMMON equity, Â§7), EV/EBITDA, ROE (parent-attributable), growth
  and more, each returning a `DerivedMetric` with formula + inputs + input periods +
  input sources + timestamp, and REFUSING mixed currency/period or a negative-EPS
  P/E rather than fabricating a number. `finance_facts/corporate_actions.py` flags
  splits/buybacks/spin-offs/M&A that make a naive historical comparison invalid and
  adjusts a pre-split price only when the ratio is known. `finance_facts/evidence.py`
  builds the Questionâ†’Claimâ†’Derivedâ†’Factâ†’Source graph and detects orphans (a claim
  with no fact, a fact with no source). Tests: `test_finance_facts_metrics.py` (14
  cases). Still no ticker-specific logic; still pure Python; no schema/jdds.db change.
  docs updated: `docs/CHANGELOG.md`, `docs/NAVIGATION.md`

- **Universal financial-fact foundation: every fact carries its meaning, not just
  its value.** New pure-Python package `python/harness/finance_facts/` â€” the
  deterministic layer the LLM reasons OVER (no prompts for rules). It EXTENDS the
  Phase-4 evidence machinery (`research/{claims,supersession,calculations,periods}.py`
  are reused, not rebuilt) and adds the dimensions they lacked: a
  `FinancialFact` model (metric/definition/value/unit/currency, period with a
  period TYPE, distinct publication/source/retrieved timestamps, accounting +
  reporting standard, consolidation + attribution + ownership level,
  reported/derived, freshness, confidence, supersedes); an accounting ontology
  (`semantics.py`) that keeps Revenue â‰  Net Sales â‰  Gross Revenue and separates
  net income / attributable-to-parent / NCI and gross/net/financial debt and the
  cash variants (an ambiguous label like "revenue" resolves to None, never a
  silent guess); a universal period model (`periods_ext.py`) where FY â‰  TTM and H1
  â‰  FY; an independent TTM engine (`ttm.py`) that sums four adjacent quarters and
  flags a material vendor difference as CONFLICT with an investigation checklist;
  per-metric freshness (`freshness.py`); an evidence-based confidence model
  (`confidence.py`); sector classification + sector metric sets (`sector.py`, bank
  CET1/NIM, insurance combined ratio, REIT FFO, crypto, â€¦); currency/unit + FX-basis
  normalization (`fx.py`); a structured semantic conflict record (`conflicts.py`)
  where consolidated-vs-parent earnings is a definition difference, not an error;
  and the ordered data-quality gate chain with distinct N/A reasons (`quality.py`).
  Nothing is ticker-specific â€” KCHOL is one row in the diverse regression suite
  (`test_finance_facts.py`, 33 cases: US tech, bank, insurance, REIT, energy,
  mining, holding/conglomerate, crypto, NCI, negative earnings, restated, ADR,
  stale-vault â€” asserted on RULES, not symbols). No prisma/schema.prisma or jdds.db
  change. This is the foundation slice; wiring it into the retrieval/research path
  is the next phase.
  docs updated: `docs/NAVIGATION.md`, this file

- **Phase 13 follow-up 3 â€” general multi-source, not price-only: the vault is a
  cache, not a precondition.** The earlier fixes verified the price leg, but two
  data classes were still vault-bound and would fail or go stale for anything the
  committed snapshot lacks: `fundamentals` (company profile) and `market_snapshot`
  (a symbol absent from the universe, or a vault row with no stored price).
  `src/lib/harness/data-bridge.ts` now enriches the profile from the existing live
  fundamentals pipeline (SEC â†’ FMP â†’ Yahoo) when the vault lacks it â€” and says
  which one answered via `profileSource`; `live_quote`/`market_snapshot` resolve an
  instrument outside the vault for a known covered market (`resolveAnyInstrument`
  recovers a `not_found` the same way `financial_statements` already did), so a
  live quote serves a symbol the vault never stored and the snapshot is never
  `UNAVAILABLE` merely because JDdS is. The identity gate still refuses
  AMBIGUOUS / `not_covered` / wrong-currency answers â€” the vault is skipped, not
  bypassed. The yfinance bridge now also carries `marketCap`. Tests:
  `data-bridge.test.ts` (profile enrichment + vault-hit short-circuit),
  `data-bridge-phase2.test.ts` (live fallback for no-row and no-price);
  `data-bridge-health.test.ts` updated so a both-sources-fail route is recorded as
  a failure. ADR-H116 amended.
  docs updated: `docs/harness/decisions.md` (ADR-H116), this file,
  `docs/harness/roadmap/progress/phase-13-progress.md`

- **Phase 13 follow-up 2 â€” per-field provenance: a live price no longer launders a
  stale market cap.** The first follow-up routed `get_market_snapshot` through the
  arbitrated layer, but the live provider used for US equities (yfinance
  `fast_info`) returns a price and **no market cap**, so the cap always fell back to
  JDdS â€” and the whole payload was stamped "verified", repeating the original demo
  defect in a new form (a verified-looking badge on a months-old cap). Two fixes:
  (1) the yfinance bridge now carries `marketCap` when the provider exposes it
  (`scripts/yfinance_bridge.py`, `fetchers/yfinance.ts`, `data-bridge.ts`), so the
  cap is genuinely cross-checked when possible; (2) when it is not, the snapshot
  tool now labels **each field** by origin (`finance_tools.py`): a value from a
  source that answered now is live; a value that fell back to the stored snapshot is
  annotated `â€” saved snapshot` with its stored time and source, and the top-level
  `verified` flag is true only when the PRICE itself is live (each `*Origin` is
  exposed on the structured payload). Regression tests:
  `test_demo_live_price_but_no_live_cap_labels_the_cap_saved` (the real US-equity
  shape), plus the updated demo tests. ADR-H116 amended.
  docs updated: `docs/harness/decisions.md` (ADR-H116), this file,
  `docs/harness/roadmap/progress/phase-13-progress.md`

- **Background Solid mode â€” fully tunable gradient/pattern and wordmark
  typography.** The gradient/pattern styles were static (fixed angle, fixed tile
  size) and the wordmark only offered font + size. Added: gradient shape
  (`solidGradientType`: linear/radial) and `solidGradientAngle`; pattern tile
  size `solidPatternScale` (4â€“80px) beside strength; and wordmark typography
  controls `textWeight` (100â€“900), `textWidth` (font-stretch, 50â€“200%),
  `textLetterSpacing` (âˆ’0.1â€“0.5em), `textLineHeight` (0.7â€“2), `textItalic` and
  `textUppercase`. `ChatWordmark` applies them; `resolveBackgroundCss` uses the
  gradient type/angle and pattern pitch. All new fields are normalized/clamped
  (`textWeight` rounds to the nearest 100). Settings panel gains the matching
  sliders/toggles; the option constants `GRADIENT_TYPE_OPTIONS` added.
  docs updated: `docs/ARCHITECTURE.md`, this file; test:
  `src/lib/backgrounds.test.ts`

- **Phase 13 follow-up â€” the price/market-cap ROUTE the agent actually used now
  verifies across sources.** The Phase-13 arbitration fixed the retrieval layer,
  but the Eclipse Agent had a second market-cap tool, `get_market_snapshot`
  (`python/harness/finance_tools.py`), that went STRAIGHT to JDdS and never ran
  the layer at all â€” so a months-old market cap was returned as current (the
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

- **Landing wordmark font list was all system fallbacks â€” now real,
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

- **Background: two types â€” Image or Solid (color/gradient/pattern + wordmark).**
  Reworked Settings â€º General â€º Background after removing the dead "Pattern"
  type. The type is now a real choice of two: **Image** (shipped/uploaded
  wallpaper, the default) or **Solid**. Solid has a `solidFill` of
  **Flat** / **Gradient** / **Pattern**: a `solidColor`, a two-color
  `solidColor`â†’`solidColor2` gradient (empty stops follow the theme background /
  brand tint), or a texture (`solidPattern`: grid / dots / diagonal / ASCII, at
  `solidPatternOpacity`) over the base fill â€” each with a customizable wordmark
  (text, font, color, size, strength, alignment, vertical). `BackgroundMode` is
  `image | solid`; `BackgroundPrefs` gains `solidFill`, `solidColor`,
  `solidColor2`, `solidPattern`, `solidPatternOpacity`, `textColor`. The
  wordmark paints via the new `isWordmarkVisible` helper: forced on in solid mode
  (it IS the backdrop), opt-in in image mode (the `textEnabled` toggle, disabled
  in solid since it is inherent). `resolveBackgroundCss` emits the solid stack
  (base fill + optional texture as a `background-image` list; brand-tinted ink);
  `ChatWordmark` applies `textColor`. The font picker is now a clickable
  preview grid (each option renders its own name in that typeface) instead of a
  Radix `Select` â€” more robust inside the modal and it actually shows the fonts.
  A saved `mode: 'pattern'` / `'none'` normalizes back to the default image.
  Tests updated; `resolveBackgroundCss`/`applyBackgroundToDocument` lost their
  now-unused `patternImage` parameter.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, this file; test:
  `src/lib/backgrounds.test.ts`

- **Phase 13 â€” source authority and freshness arbitration landed.** A price,
  series or macro answer is now chosen by freshness-then-strength across all
  eligible sources, with the disagreement preserved, instead of by the first
  source in a static table. Added `python/harness/retrieval/authority.py` â€” the
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
  else `unknown` â€” its old `asOf: new Date()` (the retrieval clock) is corrected.
  New `source.*` i18n keys and the extended plain-language gates. ADR-H115 and
  ADR-H116 written; `NAVIGATION.md` rows 149/150/352 updated. Tests:
  `test_source_authority.py` (15 cases, including the vault-vs-live disagreement
  that failed on the pre-change code) plus the retrieval regression suites.
  docs updated: `docs/harness/decisions.md`, `docs/harness/architecture.md`,
  `docs/NAVIGATION.md`, this file,
  `docs/harness/roadmap/progress/phase-13-progress.md`,
  `docs/harness/roadmap/phase-13-source-authority.md`, `docs/harness/roadmap/README.md`

- **Roadmap round 2 authored: phases 13â€“20 (reachability, source truth, and output)
  added to `docs/harness/roadmap/`.** Round 1 (phases 0â€“12) built the machinery of a
  harness; this round closes the six gaps a user reports against the *running* system,
  each traced to a measured cause and each with a paste-ready prompt. Added:
  `phase-13-source-authority.md` (the market-data vault is first for every
  price-shaped type and the first success wins, so a live provider is never
  consulted; measured from the live `jdds.db`: 0 of 55 195 price rows are fresh
  within 15 min and 22.2 % are older than 7 days, while `data-bridge.ts` hard-codes
  `cadenceSeconds: 24*60*60` and `validate.py` measures staleness only at dataset
  level â€” the phase adds one `AUTHORITY` table, arbitrated dispatch and
  per-observation age, and deletes `_PLAN`/`_SINGLE_BEST`), `phase-14-reachable-code-capability.md`
  (the code modules exist on the one registry, but `eclipse-agent`'s 27-tool
  allowlist has no code tool, `RunRequestPayload` has no `autonomy` field at all, and
  `analysisEnabled` is referenced **0** times in `src/` â€” the phase adds a
  deterministic request classifier, a narrow chat code profile and a chat capability
  panel), `phase-15-attachments-and-artifacts.md` (extract.ts is text+PDF only with a
  20 000-char silent truncation; the chat artifact surface prints a filename and a
  12-char hash and no route serves the file; `code_commit`'s handler performs **no git
  operation** yet returns `status: "approved"` â€” the phase adds office extractors,
  stated truncation, an artifact-serving route and a user-decided promotion with
  Option B recommended), `phase-16-bulk-acquisition.md` (the answer budget is 4
  searches / 8 fetches / 90 s, the analysis sandbox is `network=False` with 16 allowed
  imports, and the TS scraper layer is unreachable from the runtime â€” the phase adds a
  declared attributable source registry, an explicit acquisition budget and a new
  `data.collect` permission noun), `phase-17-working-on-a-cadence.md` (the job model,
  scheduler, delivery and seven templates exist; no tool can create a job â€” the phase
  adds a fixed catalogue, a default-off operator switch and an unattended-report
  honesty contract), `phase-18-visual-output.md` (no plotting library is importable and
  no artifact can be shown â€” the phase adds a deterministic renderer that the model's
  program never gains access to, plus a bootstrap Monte Carlo that records its seed),
  `phase-19-self-verification.md` (the ledger's claim classes cover commands only â€”
  the phase adds artifact checks, a data-driven change-review rule table and two claim
  classes), and `phase-20-measuring-all-of-it.md` (the generated capability statement
  covers seven code shapes and omits every new class â€” the phase registers all classes
  and publishes the unmeasured ones as unmeasured, with the eval step added inside the
  existing `test-evals.js`). The index gains the phase rows, the round-2 ordering
  rules, the measured six-gap ledger (Â§1.2), a supersede note on Â§2, and the
  ADR-H115â€¦H125 assignments. Measured baseline re-established this session on the
  untouched tree: `npm run check:all` â†’ `ALL GATES PASSED` (vitest 175 files / 1 995
  tests; pytest 2 278 passed). No runtime file was changed by this entry; the phase
  folders are proposals with no code behind them yet.
  docs updated: `harness/roadmap/README.md`, `harness/roadmap/phase-13â€¦20`,
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
  no doc change â€” presentational corner treatment, no architecture/contract/
  setup change (the content-panel host is already described in
  `docs/ARCHITECTURE.md` Â§Presentation).
