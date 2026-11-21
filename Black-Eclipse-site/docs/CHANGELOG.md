# Change Log

Older entries are **moved, never deleted** into [`docs/changelog/`](./changelog/)
— one file per month. This file keeps the newest seven dated sections;
`npm run rotate:changelog -- --write` performs the move.

## 2026-11-20

- **fix(ai): OpenCode Go and Zen are separate connections.** They shared
  `OPENCODE_API_KEY`, so connecting Go also marked Zen connected and the
  composer could keep showing Zen models. Go now uses `OPENCODE_GO_API_KEY`;
  Zen keeps `OPENCODE_API_KEY`. A stored per-chat choice is dropped when its
  provider has no key, so the composer follows the provider you actually
  connected. Docs updated: `docs/model-connections.md`.

- **fix(ai): the vault key test no longer uses a public endpoint.** OpenRouter
  serves `/models` without auth, so the vault Test reported success for any
  string; it now calls the authenticated `/auth/key` endpoint. OpenCode's
  public catalog advertises no GET test at all (the AI connect flow does a real
  chat probe instead). no doc change - test-endpoint correctness.

- **fix(ai): a public model list can no longer look like a connected provider.**
  OpenRouter serves /models without auth; an empty key passed the models probe,
  then the chat probe returned `Missing Authentication header` and the UI said
  the key was rejected. A keyed provider now returns MISSING_KEY before any
  request, Connect/Test stay disabled until a key is pasted, and a list-only
  probe is UNVERIFIED - `ok` requires a successful real chat request.
  Docs updated: `docs/model-connections.md`.

- **feat(ai): change the active model from the connection card.** The live
  catalog (31 OpenCode Go models) is now a dropdown on the active card instead of
  being hidden inside the collapsed Model & sampling section. no doc change -
  UI affordance for an existing setting.

- **feat(ai): replace or remove the active provider's key.** The active
  connection card now offers **Replace key** and **Remove key**, and an active
  provider row shows Disconnect. The old UI hid both for the active provider.
  no doc change - UI action over the existing key API.

- **fix(ai): provider tests use the selected endpoint.** A test for a provider
  other than the saved one now uses THAT provider's default endpoint/model instead
  of the saved base URL (which could be local Ollama). Model lists that carry a
  wire id plus a display name keep only the id, so OpenCode's 31 models are not
  doubled to 62. no doc change - probe/test bugfix.

- **fix(ai): OpenCode Go now sends the required session header (v0.4.20).**
  OpenCode Go rejects any request without a stable `x-opencode-session` id
  (HTTP 400 `MissingSessionID`), which is why a valid key failed to connect.
  Probes, model discovery and the runtime now send the header plus a real
  User-Agent; the runtime uses the run's conversation id with a process-stable
  fallback, and the gateway's catalog URL is declared explicitly. Verified
  against a live key: 31 models listed and a 200 chat completion. Bumped to
  0.4.20.

- **release: v0.4.19.** Version stamp for the one-step provider connection
  system (atomic connect, protocol-aware probes, named custom gateways with
  per-connection keys and auth styles). Docs unchanged; this is the release
  stamp for the entry above.

- **release: v0.4.18.** Published 2026-11-20: `BlackEclipse-Setup.exe` (188,482,315 bytes, sha256 `3c517b23…`), the offline `-full` edition and the feature packs; the offline-signed `stable.json` was uploaded to the draft and then promoted to latest. Ships the minutes-level detection/announcement and the CDN cache-buster above. Verified: `node scripts/update.js --check` reports *latest signed release v0.4.18 / already up to date*, `npm run check:downloads` resolves both buttons. Docs updated: `docs/UPDATES.md` (release state).

- **fix(updates): bypass the GitHub CDN cache when revalidating the manifest.** `releases/latest/download/stable.json` is edge-cached, so a just-published manifest kept serving the previous release even after the draft was promoted — `update.js --check` reported v0.4.16 while the same URL with a cache-buster returned v0.4.17. Both `scripts/lib/update-verify.js` and the Next `fetchManifest` now append a per-request `ts` query (a public static file; harmless) so a revalidation means "now". Verified: `node scripts/update.js --check` reports v0.4.17. tests: `tsc`, updates suite. docs updated: `docs/UPDATES.md` (manifest revalidation).

- **release: v0.4.17.** Version bump for the update-pipeline fix above; the tag drives `desktop-release.yml` (Windows installer) and `publish-harness.yml`, and the offline-signed `stable.json` is uploaded to the draft before publishing.

- **feat(team): bundled finance team library with evidence-gated subtasks
  (Phase 7).** `TeamSubtask.evidence_required` added (default false — existing
  teams unchanged); enforcement lives in `TeamService.finalize` via the pure
  `unevidenced_subtasks`: a completed gated subtask with no evidenced finding
  becomes a BLOCKING finding the reviewer must address (it cannot be approved
  silently). New `team/preset_library.py` loads
  validated YAML presets, substitutes declared `{variables}`, and rejects
  duplicate ids, unknown/cyclic dependencies, an assignee who is not a member,
  or a non-orchestrator lead who is not a member — at load time, naming the
  file. Three presets ship: `investment_committee` (bull, bear, risk review,
  chair verdict), `quant_strategy_desk` (screen, factor evidence, backtest,
  audit) and `portfolio_risk_review` (concentration, drawdown, correlation,
  decisions). YAML added to `pyproject` package-data so it ships. Tests:
  `test_team_presets.py` (11) plus 53 team service/graph/conflict/review/e2e
  regressions, all passing. Docs updated:
  `docs/harness/bot-team-orchestration.md`,
  `docs/harness/vibe-trading-analysis.md` (G9 partial).
  Not done in this phase: the other ~27 curated desks, broker breadth 4→8 and
  IM channel breadth 8→19 — those are product decisions, not ports.

- **feat(artifacts): deterministic revision comparison (Phase 6).** Checked the
  other two Phase 6 items first and they already existed — tool results are
  paged with `offset`/`nextOffset` in `tool_outputs.py`, and memory has a
  retention/expiry sweep with preview, maintenance lease and status. So the
  real gap was the artifact diff: `artifacts/compare.py` adds
  `compare_versions` / `compare_revisions` / `to_markdown`, reporting checksum
  and size change, provenance (`created_by`/`agent_id`/`task_id`/`run_id`),
  `change_note`, `mime_type`, and metadata split into added / removed / changed
  with bounded values. Bytes are compared by checksum, never line-diffed, and
  the doc says so. Tests: `test_artifact_compare.py` (9) plus 34 artifacts
  api/store/tools regressions, all passing. Docs updated:
  `docs/harness/artifact-center.md`, `docs/harness/vibe-trading-analysis.md`
  (G10/G11 already existed, G12 done).

- **feat(factors): academic Alpha Zoo (14 factors) + strict bench protocol
  (Phase 5).** `factors/zoo/academic.py` adds documented price/volume factors
  (overnight gap, intraday momentum, close-location value, Bollinger position,
  RSI reversal, price-volume correlation, Amihud illiquidity, volume shock,
  drawdown proximity, up-day ratio, high-low spread, price-volume trend), each
  with `zoo`/`source`/`reference` provenance and an expression on the ONE safe
  formula engine (no `eval`). Merged by name into
  `factors.library.BUILTIN_FACTORS` (18 → 32) with no shadowing and no
  duplicates. `factors/strict_bench.py` adds the anti-search-luck protocol:
  chronological `split_index`, seeded per-date `random_control` (preserves each
  date's distribution and missingness), and `strict_bench` reporting train IC,
  held-out test IC, **control IC on the held-out window**, `oosDecay` and
  `beatsControl`, reusing `factors.engine` so there is one IC implementation.
  Tests: `test_alpha_zoo_strict_bench.py` (13) + 45 factor-service/engine
  regression tests, all passing. Also fixed a stale vitest mock
  (`workflows/generate/route.test.ts` did not provide `modelAuthFields`, which
  the pre-existing uncommitted `route.ts`/`settings.ts` work imports) — 4/4
  pass; that was the only vitest failure in the full gate. Docs updated:
  `docs/quant-engine.md` (Alpha Zoo + strict bench),
  `docs/harness/vibe-trading-analysis.md` (G7 partial, G8 done).

- **feat(context): zero-cost turn fold + iterative compaction summaries
  (Phase 4), both opt-in.** `compaction.py` gains `collapse_text/turn/turns`: a
  turn over `COLLAPSE_MIN_CHARS` is reduced to head+tail plus a marker naming
  the omitted character count and the **sha256 of the full original** (no model
  call, idempotent, never a summary), wired into `history._bounded_history`
  BEFORE the character cap. Measured consequence: folding makes previously
  dropped turns fit, so 6 existing trimming/overflow tests changed behaviour and
  failed; rather than rewrite their expectations the fold is **OFF by default**
  (`BE_HISTORY_COLLAPSE=1` enables it) and the default path is byte-identical.
  Iterative summaries: `build_compaction_prompt(prior=…)` asks the model to
  UPDATE the prior briefing (keep true facts, correct wrong ones) instead of
  writing anew; `CompactionResult.iterated` records it and `compact_history`
  accepts `prior_summary`. Tests: `test_compaction_collapse.py` (15) plus 50
  history/compaction/overflow and 65 context-budget/graph regression tests, all
  passing. Docs updated: `docs/harness/architecture.md`,
  `docs/harness/vibe-trading-analysis.md` (G2 → done, opt-in).

- **feat(tools): `load_tool_schema` — see a catalogued tool's parameters before
  invoking it (Phase 3).** The Phase 3 premise was wrong, and checking first
  mattered: Eclipse already defers tool *binding* through `tool_disclosure.py`
  (BM25-ranked, tiered catalogue, `tool_search`/`tool_invoke`, absolute schema
  budget). Vibe-Trading's `load_tools` is a second, weaker copy of that
  mechanism, so building it would have duplicated an existing subsystem. The
  real missing step was schema *visibility*: `tool_invoke` executes directly, so
  a model that only knew a catalogued name had to guess argument names. Added
  `harness/tool_schema_load.py` (`load_tool_schema`, read-only, `risk="none"`,
  ≤5 tools/call, 8k-char bound, allowlist-checked — it can never widen
  authority), registered at boot in `service.py`, added to
  `tool_disclosure.CORE_TOOLS` so it stays bound exactly when narrowing is
  active, and added to the `eclipse-agent` / `CODE_NAVIGATOR_TOOLS` allowlists.
  Tests: `test_tool_schema_load.py` (9) plus 62 disclosure/tools/surface and 41
  graph/execution regression tests, all passing. Docs updated:
  `docs/harness/architecture.md`, `docs/harness/vibe-trading-analysis.md`
  (G1 → already existed).

- **feat(quant): the event engine enforces market mandates (Phase 2).**
  `BacktestEngine` now resolves `MarketRules` per symbol (from
  `StrategySpec.market`, overridable by `BacktestConfig.market`) and applies
  three gates the engine previously only declared: (1) entry quantity is floored
  to the market lot (`MARKET_LOT_BELOW_ONE` when a sub-lot size becomes no
  trade); (2) a fill outside the previous-close price band is cancelled
  (`MARKET_LIMIT_BAND`) with the board from `board_for_code`; (3) sells are
  clamped to the quantity acquired on an earlier calendar day
  (`MARKET_T1_UNSETTLED`). FIFO lot bookkeeping in `_apply_fill`;
  `BacktestConfig.market` added. Tests: `test_market_enforcement.py` (10) plus
  87 regression tests across engine/orders/realism/vector/costs/market-rules,
  all passing. The end-of-run forced liquidation intentionally bypasses T+1 and
  the docs say so. Docs updated: `docs/quant-engine.md`,
  `docs/harness/vibe-trading-analysis.md` (G6 → Phase 2 done).

- **feat(quant): market execution rules + `StrategySpec.market`; broker
  capability matrix with a drift gate; charts in exported reports.** Phase 1 of
  the Vibe-Trading gap plan. `quant/market_rules.py` declares settlement, lot
  rounding, board price limits, stamp/transfer taxes and short permissions for
  `us_equity` / `a_share` / `hk_equity` / `crypto` as pure, unit-tested
  functions; `StrategySpec.market` (default `us_equity`) is serialized with the
  spec, and `validate_strategy` now rejects an unknown market
  (`UNKNOWN_MARKET`) and a retail short where the market bans it
  (`MARKET_SHORT_NOT_PERMITTED`). Per-bar enforcement (T+1, limits) is NOT yet
  wired and the docs say so. `trade/capability_matrix.py` renders the four
  declared broker kinds into `docs/trading.md` between markers with
  `npm run docs:brokers` / `docs:brokers:check` (the check exits 1 on drift).
  `quant/report_export.py` now embeds the run's `core`+`risk` figures as inline
  base64 PNGs rendered by the one chart engine (no JS, no external asset;
  best-effort with a named fallback). Tests: `test_market_rules.py` (22),
  `test_capability_matrix.py` (9), `test_report_export_figures.py` (3). Docs
  updated: `docs/quant-engine.md` (market rules + export figures),
  `docs/trading.md` (generated matrix),
  `docs/harness/vibe-trading-analysis.md` (charts comparison + status).

- **docs(analysis): external Vibe-Trading implementation analysis + gap
  register.** Read-only study of `HKUDS/Vibe-Trading` v0.1.19 (`1dbe5d5`) to
  identify capabilities Eclipse lacks: measured inventory of all 33
  `agent/src` packages (472,123 LOC; 126-tool AST extraction; 460 alphas; 19
  broker connectors; 19 IM channels; 45 loaders; 15 venue engines), module-level
  mechanics, and 13 numbered gaps each mapped to the exact Eclipse file and a
  before/after contract (deferred tool exposure, zero-cost context collapse,
  router probe budget, generated capability matrix, endpoint DNS pinning, venue
  rule matrix, alpha zoo, strict bench, team presets, result paging, memory
  lifecycle, artifact revision diff, scheduled-prompt capability rule). Three
  earlier verbal claims were corrected (Vibe does ship a hash-chained ledger and
  a run manifest; its eval harness is 43 files, not "22 cases"). No production
  code changed — this is analysis plus a contract proposal. Docs updated:
  `docs/harness/vibe-trading-analysis.md` (new).

- **perf(test): `npm run verify` gates by domain, and the measured cost of the
  old gate.** `npm run test` is vitest 158 s + Python 953 s + eval floors 226 s,
  i.e. ~22 min, and 80% of it is a runtime a UI change cannot touch. `verify`
  runs the **full** suite for each domain the working tree entered (`src/` →
  vitest, `python/` → pytest, `python/harness/eclipse_memory/` → eval floors)
  and always typechecks; `--all` (or no git) runs everything, so it cannot pass
  by assuming nothing changed. Python collection alone is 607 s of its 953 s.
  `scripts/lib/pytest-parallel.js` shards the suite across N pytest processes
  (`BE_TEST_WORKERS`), but it is **opt-in and defaults to 1**: four workers took
  1333 s against 953 s serial on this 12-core/16 GB box because each worker holds
  the whole harness import graph. Changed-file detection is shared by `verify`
  and `test:fast` in `scripts/lib/changed-files.js`.
  Docs updated: `docs/QUICKSTART.md`, `docs/environments.md`. Measured: 212 s
  for a `src/`-only change against 22 min for the old gate.

- **chore(test): a `test:fast` lane for the iteration loop.** `npm run test` is
  ~160 s of vitest (554 files) plus the Python suite and eval floors, and the
  measured breakdown is `import 1325 s` vs `tests 67 s` (summed across workers):
  the cost is re-importing the agent tool registry for tests a change cannot
  affect. `scripts/test-fast.js` runs `tsc --noEmit` (16 s) and then
  `vitest related` on the working-tree's changed `src/` files, and maps a changed
  Python module to the tests named after it (`harness/market/yahoo.py` →
  `test_yahoo*.py`); it never runs the whole Python suite, which was measured at
  26 min when one dirty `.py` triggered it. The eval floors run only when
  `python/harness/eclipse_memory/` changed. Broad changes (>40 files) fall back
  to the full suite. Measured on this repo: 45 s for a 9-file change, with 4
  test files reached. It is explicitly **not** the gate - the full
  `npm run test` + `tsc --noEmit` is still required before a change is reported
  complete.
  Docs updated: `docs/environments.md` (validation commands).

- **fix(updates): a checkout whose repository root is above the app no longer reads as a packaged install.** `isSourceCheckout()` (server) and `isGitCheckout()` (runner) only tested `<app>/.git`, but this app lives in `Black-Eclipse-site/` inside a repo rooted one directory up. Both returned false, so `/api/updates` reported `canSelfUpdate: false` and `POST /api/updates/apply` refused with "This installed build cannot update in place" — i.e. the window could not download an update. Both now walk up to the enclosing work tree (finding a `.git` file or directory) and still treat a payload containing `server.js` as packaged, via the shared helper `scripts/lib/git-root.js` (mirrored in `src/lib/updates/core.ts`). `src/lib/updates/core.test.ts` pins the parent-root, packaged-marker and real-layout cases for **both** implementations, including a canary asserting this repository's actual app directory is classified as a checkout, so the bare-`.git` regression fails the suite rather than shipping. Docs updated: `docs/UPDATES.md` (new "Checkout detection" invariant + file map).

- **chore(release): regenerate the SBOM for v0.4.17.** `npm run sbom` refreshes `sbom.cdx.json` / `THIRD-PARTY-NOTICES.md` to the current lockfiles and version; `src/lib/oss/sbom-artifact.test.ts` was the only failing test in the full suite (`0.4.15` vs `0.4.17`). no doc change — generated artifact.

- **release: v0.4.17.** Version bump for the update-pipeline fix above; the tag drives `desktop-release.yml` (Windows installer) and `publish-harness.yml`, and the offline-signed `stable.json` is uploaded to the draft before publishing.

- **fix(updates): a freshly published release is detected within minutes, announced, and installable from the window.** The verified manifest was cached for 6 hours and the client polled every 6 hours, so v0.4.16 stayed invisible to a window whose last check was 44 minutes before the publish. The server TTL is now **5 minutes**, and the client checks after 2 s, every **10 minutes**, and on focus / visibility / `online` (throttled) — a release published while the window is open surfaces within minutes. A newer version raises a **one-time toast** through the shared `be:alert-notify` channel (transient: no ledger badge) alongside the title-bar dot. Packaged installs can now update in place: the verified manifest's `installers[<platform>-<arch>]` is exposed as `installer` on `/api/updates`; *Update now* runs the shell's installer runner (download → SHA-256 + size verify → open), and the fallback download button points at that signed installer instead of the release page. Tests: `src/lib/updates/core.test.ts` (platform installer selection); `tsc` clean, updates/notifications suites pass. docs updated: `docs/UPDATES.md` (cadence + packaged installer path).

- **feat(news): a real News control surface in Settings.** Settings › News now
  opens with two panels: **News cards** (per-page, sort, columns, density,
  summary lines, auto-refresh interval, and the show-on-card toggles — the same
  `be_news_card_settings` the inline Customize panel edits, with a
  `be:news-card-settings` event so a mounted News tab updates live) and
  **Pop-ups & notifications** (background watch, in-app pop-up card, desktop
  notification, alert sound, upcoming macro releases, watchlist-only and
  minimum importance score, plus Send test / Reset). The root news watcher now
  honours those prefs (`be_news_notify_v1`), and `NotificationRequest` gained
  independent `toast`/`desktop` lanes while still writing the ledger entry.
  Server-side channel policy (Telegram/Discord/ntfy/email/webhook) stays in
  Settings › Alerts, which now points here for the in-app lanes.
  Docs updated: `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`.

- **feat(onboarding): a Look & feel step with live theme picking.** First-run
  setup now has a theme step between Welcome and AI. It shows every shipped
  `THEME_PRESETS` look plus any themes the user already saved, and selecting a
  tile applies it immediately (the wizard recolors) and persists it app-wide
  through the theme store, so the app opens with the chosen look instead of the
  default. Docs updated: `docs/onboarding-plan.md`, `docs/NAVIGATION.md`.

- **fix(ai): provider connections now test and save correctly, in one step.**
  Selecting a provider (or editing its base URL) used to POST `/api/settings`
  while no key existed; `setLLMConfig` rejected the write, but the UI had already
  changed, so the screen said "Connected" while chat kept the old provider.
  Saving the key afterwards only wrote the vault — the selection was never
  re-saved. `setLLMConfig` now persists a configuration before its credential
  exists (chat then fails honestly with `PROVIDER_NOT_CONFIGURED`), and a failed
  probe never replaces a working connection. A new atomic
  `POST /api/llm/connect` validates → probes with the provider's REAL auth →
  discovers models → saves the key and active config. The probe used to send
  `Authorization: Bearer` to every provider, so valid Anthropic (`x-api-key`) and
  Gemini (`x-goog-api-key`) keys were reported as rejected; it is now
  protocol/auth aware and makes one tiny real chat request (`probeChat` retries
  without probe-only `max_tokens`/`temperature` when a reasoning model rejects
  them). One provider registry (`src/lib/providers/registry.ts`) now feeds the
  UI presets, with a parity test against `python/harness/models.py`; a named
  provider keeps its own vault key when its base URL is edited. Onboarding and
  Settings share one paste-first `ProviderConnect` panel (auto-detect the key,
  one Connect button, plain-language errors, model auto-discovery, advanced
  fields collapsed). Deleted the old preset grid/key-editor/test dance.
  Custom gateways are now **multiple named connections**
  (`llm_custom_connections_v1`), each with its own encrypted vault key
  (`CUSTOM_LLM_KEY_<ID>`), endpoint, model and auth style — Bearer / `x-api-key`
  / `api-key` / custom header+prefix. The style is used by the probe AND threaded
  through `ModelSettings` to `python/harness/models.py`
  (`ChatOpenAI(default_headers=…)`), so a non-Bearer gateway actually runs, not
  just tests. Settings lists, edits, switches and deletes them independently;
  onboarding's custom flow creates one too.
  Docs updated: `docs/model-connections.md` (new), `docs/NAVIGATION.md`,
  `docs/ARCHITECTURE.md`.

## 2026-11-19

- **fix(build): the standalone payload build imported a `buildEnv` that was never defined.** `scripts/desktop-payload.js` gained `const { buildEnv } = require("./lib/server")` with the 6cfe77e7 changes, but `scripts/lib/server.js` never exported it, so `npm run desktop:payload` — and therefore every desktop release after v0.4.15 — died with `TypeError: buildEnv is not a function`. Restored the helper alongside `buildNodeOptions`: it merges the caller's overrides over `process.env` and applies the production heap. Verified locally; the v0.4.16 tag is re-cut onto this commit. no doc change — the bug and its fix are the code.

- **release: v0.4.16.** Ships the AI-provider batch below (Ollama roots, auto model detection, custom-endpoint keys, OpenCode Go) plus the desktop data-dir/stop fixes and the restored payload `buildEnv`. Version bumped in `package.json`, `pyproject.toml` and `python/harness/__init__.py`; the `v0.4.16` tag (`7db57bb5`) drove `desktop-release.yml` for the Windows installer. Published 2026-11-20: `BlackEclipse-Setup.exe` (188,457,151 bytes, sha256 `1f5e1d74…`), the offline `-full` edition and the feature packs; the offline-signed `stable.json` was uploaded to the draft and then promoted to latest. Verified: `node scripts/update.js --check` reports *latest signed release v0.4.16 / already up to date*, `npm run check:downloads` resolves both buttons. docs updated: `docs/UPDATES.md` (release state).

- **chore(git): ignore the packaging artifacts that were dirtying the worktree.**
  `scripts/desktop-package.js` writes `config/packs.json` at package time (it
  landed with a stale `version: 0.4.6` and was never tracked), and a packaging
  run had left a runaway nested build in `dist-local/`
  (`app/dist/BlackEclipse/app/dist/...`, 38 files). `.gitignore` now covers
  `/dist-local/` and `/config/packs.json`; the nested build directory was
  deleted. No source or release behaviour changed.
  No doc change - the ignore rules are the artifact.

- **feat(ai): model detection is automatic, and any API's key now reaches its probe.** The picker probes on mount and whenever the endpoint or the provider's key state changes (debounced, once per provider+endpoint), instead of requiring a manual Discover click and locking a provider out for six hours; the chat composer does the same for the selected provider. Two gaps made "connect any API" fail: a hand-typed endpoint's probe resolved no vault key (it now falls back to `CUSTOM_LLM_API_KEY` exactly as the LLM config does), and `llmKeyEnvVar` treated Ollama's `OLLAMA_BASE_URL` (a base URL, not a key) as a credential for keyless presets. OpenCode Go is now also offered in the setup wizard and its shared Console key is labelled "OpenCode Zen / Go" — the provider itself already existed in Settings, the runtime catalog and the model probe (`https://opencode.ai/inference/go/v1/models`, verified live); the running window was simply an older install. Tests: `src/lib/settings.test.ts`, `src/lib/agent/presets.test.ts`. no doc change — no data shape, setup step or architecture changed.

- **fix(ai): an Ollama endpoint pasted as its documented root (`http://localhost:11434`) now lists and selects models.** Two gaps combined to leave the picker empty with no Discover action: the model probe requested `{root}/models` (404 — the OpenAI surface is `/v1/models`, the native list is `/api/tags`), and no preset matched a base URL without a `/v1` suffix, so the settings panel resolved no provider id at all. Discovery now tries `{base}/models` first, then `{root}/v1/models`, then Ollama's native `{root}/api/tags` (a 404 or non-JSON reply falls through; the first real error is still reported), and a keyless local preset also matches its `/v1`-less root. Works for local Ollama, `ollama.com` (with or without `/v1`) and LM Studio. Tests: `python/tests/test_model_discovery.py`, `src/lib/agent/presets.test.ts`; verified against the running local Ollama (`kimi-k3:cloud`) and `ollama.com`. no doc change — discovery is an implementation detail of the model-runtime contract; no data shape, setup or architecture changed.

- **fix(ai): a hand-typed endpoint now gets its key, its model list and its
  Discover action.** A custom API entered as a base URL matched no preset, so
  `llmKeyEnvVar` resolved no vault entry — saving refused with "API key is
  required", and the runtime ran with an empty key even when the vault held one.
  The active-setup panel also showed no key field and no model catalog because
  the provider id stayed `auto`. Any hosted URL that is not a preset now resolves
  to `CUSTOM_LLM_API_KEY`, and the panel treats it as the generic `custom`
  provider (key editor, declared catalog, Discover). Verified end to end against
  a stub OpenAI-compatible server (discovery + chat + Bearer key) and by building
  a model for all 17 catalog providers; the local runtime was missing
  `langchain-openai` and the sibling SDKs, now installed from
  `python/requirements.txt`.
  No doc change — provider contract and data shapes are unchanged.

- **fix(desktop): `black app` / `desktop:refresh` no longer open the window
  against an empty checkout database.** `channelLaunchEnv` forced
  `BE_DATA_DIR` to the repository root for the Stable channel too, overriding the
  packaged install's own `%LOCALAPPDATA%\BlackEclipse\data`. The checkout's
  `jdds.db` has no schema until `prisma db push`, so every DB-backed screen
  failed with `P2021: table ... does not exist` and the Node server eventually
  died of OOM. `BE_DATA_DIR` is now set only for the isolated Dev channel; Stable
  keeps its packaged data directory (verified: window boots, `/api/setup`,
  `/api/alerts/live`, `/api/settings` all 200 against the 11 MB database).
  Two consequences handled in the same pass: the owner marker is now read from
  the same directory it is written to, and `black stop` clears the channel's app
  port, because a packaged install pins no build and therefore writes no owner
  marker — stopping the window used to leave its server behind and the next
  launch showed "port 3100 is in use by another application".
  docs updated: `docs/desktop-app-plan.md` (§4 data-directory resolution).
  `operator-secret` (a per-install signing secret that the broken launches wrote
  into the checkout) is now gitignored.

- **release: v0.4.15 is published, with its signed manifest.** Signed
  `stable.json` offline with key `3e5f4f12096f06ac` for commit `b18e7e7b`, uploaded
  it to the draft, rewrote the release body to the Windows-only template (the
  old body still linked a `.dmg` that was never attached), then promoted the
  draft. Verified end to end: `node scripts/update.js --check` reports
  *latest signed release v0.4.15 / already up to date*, and
  `npm run check:downloads` resolves `BlackEclipse-Setup.exe` and
  `SHA256SUMS.txt`.
  Docs updated: `docs/UPDATES.md` (release state).

- **chore(size): re-pin the harness budget for the settled tree.** `check:size`
  was red on `main` (521969 lines vs a 521545 ceiling) from the chart-engine,
  bots and provider-spec work that landed after the 2026-11-18 pin. Re-pinned to
  the measured tree — total 521969, `.` 40246, routers 24145 — per ADR-H288's
  rule that a ceiling may be raised only by a deliberate edit.
  No doc change — the budget file is the artifact.

- **fix(release): a blank `only` no longer rebuilds all three OSes, and the
  release body stops describing downloads that do not exist.** `e6c21adc`
  removed the macOS/Linux download links but left two traps: a manual
  `workflow_dispatch` with `only` blank still built `ubuntu-latest` and
  `macos-latest` (the slow path the Windows-first lane was meant to remove), and
  the generated release body still told macOS/Linux users how to open an app
  they cannot download. Blank `only` now resolves to `windows-latest` (name an OS
  to backfill), and the body's **First open** paragraph is Windows-only. Same
  semantics on a tag push, so no release path changed behaviour.
  Docs updated: `docs/UPDATES.md` (backfill table, iterate note).

- **fix(ci): regenerate the published benchmark page for 0.4.15.** Every push
  since v0.4.13 failed `test_published_benchmarks` because
  `docs/harness/benchmarks.md` still said `agent version: 0.4.12` (and pointed at
  the v0.4.12 commit), so the generated-file guard read the page as stale or
  hand-edited. Ran `npm run eval:benchmarks`; only the run id, version, commit
  and latency line changed.
  No doc change — the benchmark page is the artifact itself.

- **feat(updates): a packaged install can finally update itself.** Every
  update path was git-only (`fetch` → `checkout` → `npm ci` → build), so the
  window shipped by `BlackEclipse-Setup.exe` had no way to apply an update: its
  `app` directory has no `.git`. `scripts/update-apply.js` now branches on that:
  a source tree keeps the checkout+build path, a packaged tree downloads the
  platform installer named in the signed manifest, verifies its SHA-256 and size
  **while streaming** to `<BE_DATA_DIR>/.runtime/updates/`, and only then opens
  it. A mismatch deletes the file and installs nothing. The handoff runs through
  a detached PowerShell helper so closing the window/server cannot kill the step
  that starts the installer. The manifest gains a signed `installers` map
  (`<platform>-<arch>` → `{url,sha256,size}`), validated by both verifier
  mirrors and host-checked like every other URL; `update-sign.js` builds it from
  `--installer-file` (streaming hash, no 200 MB read) + `--installer-url`. Jobs
  carry `mode` and the verified `artifact`, and installer mode tells the user to
  follow the installer instead of offering a restart that would do nothing.
  v0.4.15's manifest predates the field, so packaged 0.4.15 falls back to an
  honest "open the release page" message; the next signed release can use it.
  `desktop-package.js` now ships `update-apply.js` and `update.js` in
  `app/scripts` — it copied only the bootstrap before, so a packaged install had
  no updater to run at all. Docs updated: `docs/UPDATES.md`.

- **perf(boot): a page request waits 3 s for a cold Python runtime, not 45 s.**
  The browser allows six concurrent HTTP/1.1 connections per origin; six boot
  API calls parked on the 45 s runtime budget held every socket, so even
  Python-free routes (the chat transcript among them) queued for 45–55 s on a
  cold start. `DEFAULT_REQUEST_WAIT_MS` is now 3 s: the background spawn keeps
  going, the route answers an honest 503, and the next poll succeeds.
  `HARNESS_PY_REQUEST_WAIT_MS` still overrides it. Files:
  `src/lib/harness/runtime-supervision.ts` (+ test). Docs updated:
  `docs/ARCHITECTURE.md`.

- **fix(build): the production payload builds with Turbopack.** The webpack
  production compile of the current graph exceeded a 15 GB live heap and died
  with "Ineffective mark-compacts near heap limit" on this 16 GB host — at both
  the 12 GB and 15 GB ceilings — so `desktop:refresh` and the in-app updater
  could never finish their `building` phase (the same tree built in ~2.5 min
  under Turbopack). `scripts/lib/server.js` (stable / `npm run build`) and
  `scripts/desktop-build.js` (dev channel) now pass `--turbopack`;
  `BE_BUILD_WEBPACK=1` is the fallback. Also removed the 3.7 GB stale webpack
  cache that made rebuilds slower. Docs updated: `docs/UPDATES.md`.

- **chore(marketing): Windows is the only advertised platform.** Removed the
  macOS and Linux download buttons from the README and the macOS/Linux rows from
  the release body and the install/requirements tables. Nothing links to an
  artifact that is not published yet. The builds are not gone: the workflow
  still produces `.dmg`/`.deb` on request (`only: macos-latest` /
  `ubuntu-latest`). `check:downloads` now checks the Windows button by default
  and takes `--all` to include the backfilled ones. `docs/install.md` records how
  to turn macOS on later (Apple Developer membership + notarisation secrets,
  backfill run, restore the button) and the shorter Linux path.
  Docs: `README.md`, `docs/install.md`, `docs/public-readme.md`,
  `docs/UPDATES.md`.

- **feat(release): tag builds are Windows-first, and macOS/Linux attach
  later.** A tag push now builds only `windows-latest`, so the draft release
  exists in ~15 minutes instead of waiting for the slowest runner — Windows is
  where the installed user base is, and a packaged install can only receive a
  fix by installing a new build (the in-app updater needs a git checkout and
  `node_modules`, which a packaged payload does not ship). The other platforms
  attach to the same release from a manual run (`tag: vX.Y.Z`,
  `only: macos-latest|ubuntu-latest`, `upload_release: true`); that run preserves
  the release's existing draft/published state, because `action-gh-release`
  updates with `draft: existingRelease.draft`. The workflow also gains `tag`
  (a dispatch otherwise builds the branch ref) and `publish` (promote a draft)
  inputs, and a blank `only` still builds all three on demand.
  Docs updated: `docs/UPDATES.md` (Windows-first tags, backfill, and why packaged
  installs need an installer).

- **perf(chat): opening the app no longer serializes the entire chat archive.**
  `GET /api/chat/transcript` returned every message body of every conversation;
  on the reference host that was 16 MB / 177 conversations, parsed, stringified,
  gzipped and parsed again in the WebView on every boot — a multi-second block
  on the single Node thread that queued the page's other API calls behind it
  (measured 5–10 s boot requests). The boot path now asks for `?summary=1`
  (metadata + `messageCount`, `messages: []`) and hydrates one conversation with
  `?chatId=…` when it is opened; the full list remains the default for
  migrations/external callers. Files: `src/app/api/chat/transcript/route.ts`,
  `src/lib/chat/session-store.ts` (`summarizeTranscript`),
  `src/lib/chat/chat-organization.ts` (`messageCount` survives merges),
  `src/lib/chat/transcript-client.ts`, `src/lib/chat/use-conversation-persistence.ts`
  (`hydrateConversation`), `src/components/screens/stock-chat.tsx`.
  The route also stops hand-gzipping: the Turbopack production build dropped the
  `content-encoding` header, so the browser parsed raw gzip as JSON and the
  hydration failed silently. Plain JSON now, and the boot payload is ~50 KB.
  Docs updated: `docs/ARCHITECTURE.md` (conversation persistence).

- **perf(desktop): the Tauri shell no longer builds with the slowest Rust
  settings available.** `desktop/src-tauri/Cargo.toml` had `lto = true` with
  `codegen-units = 1`, so the final binary was code-generated and linked
  single-threaded on every release — tens of minutes for a thin WebView wrapper
  whose Next payload is two orders of magnitude larger than the few MB those
  settings saved. It is now `lto = "thin"` with the default parallel codegen
  units, still stripped. The release workflow also pins the Rust toolchain
  (`1.99.0`) instead of floating `stable`, because a toolchain bump invalidates
  every fingerprint in the cached `target` dir and quietly turns a warm build
  cold, and adds a `smoke_tests` dispatch input (a tag push always runs the
  smoke test).
  Docs updated: `docs/UPDATES.md` (iterating on a release build).

- **fix(updates): the in-app updater compares against the window that is
  actually running, not the checkout on disk.** The runner read
  `package.json` from the working tree to decide "already up to date". On a
  bridged/pinned install the checkout can be ahead of the served build (here:
  running **0.4.12**, checkout **0.4.15**, signed release **0.4.14**), so every
  click on *Update now* exited with "already up to date (v0.4.15)" without
  building anything. Worse, the job recorded `fromVersion: 0.4.15`, which
  `readUpdateJob` correctly treated as a spent receipt for an app running
  0.4.12 and hid — the panel silently returned to "Update available", a loop
  with no error. The running version now travels with the request
  (`be-update {currentVersion}` → `--running-version`; the HTTP fallback passes
  `BE_UPDATE_RUNNING_VERSION`) into `update.js` and `update-apply.js`; the
  no-op branch records the running version as `toVersion` so a finished job can
  never claim a build that was not made. `black update` is unchanged (no flag →
  disk version). Docs updated: `docs/UPDATES.md`.

- **fix(build): lower the production build's peak heap so an in-app build fits on
  a 16 GB machine.** `experimental.webpackMemoryOptimizations` is on (a little
  slower, less heap). The in-app updater runs `npm run build` on the user's own
  machine at the 12 GB old-space ceiling, so a build that OOMs is a stalled
  update, not just a slow one. The observed `Ineffective mark-compacts near heap
  limit` was also reproducible by two simultaneous builds (a raw `npx next build`
  skips `.next-build.lock`), so the failure mode and the check for a second
  `next build` are documented. Docs updated: `docs/environments.md`.

- **perf(release): a tag build stops paying for work it already did.** The
  `only` fast-lane input was dead — it is accepted by `workflow_dispatch` and
  never read, so the "one OS, ~20 minutes" lane silently built all three. It now
  filters `strategy.matrix` (an `include` filter would add the skipped OSes back;
  a job-level `if` cannot see `matrix`). The build job also:
  caches `scripts/vendor/python` + the pip download dir per OS, keyed on the
  requirement files and provisioning scripts, so a repeat release skips the
  multi-minute install of playwright/sklearn/xgboost/lightgbm/duckdb/whisper/av;
  restores the Rust `target` dir across a `Cargo.lock` change
  (`restore-keys`), where a dependency bump used to force a cold ~15-25 minute
  build; and skips the `-full` Windows installer on a manual run
  (`offline_installer`, default false) because compressing every pack is the
  slowest step — a tag still always builds it. `scripts/setup-python.js` now
  targets the vendored interpreter on macOS/Linux too (it is what the app
  resolves and what ships), which removes a duplicate full Python install on
  every non-Windows runner; `scripts/setup-portable-python.js` writes a
  requirements digest marker so a restored runtime skips pip. A tag push still
  builds and publishes all three platforms unchanged.
  Docs updated: `docs/UPDATES.md` (iterating on a release build).

- **release: cut v0.4.15.** Ships the chart-engine readiness fix, per-tab chat
  sessions, the `desktop:refresh` bridge and the 12 GB default build heap
  (entries below). Regenerates `sbom.cdx.json` / `THIRD-PARTY-NOTICES.md` —
  v0.4.14 shipped while the SBOM still said 0.4.13, which failed
  `sbom-artifact.test.ts` on every run after it. Bumps `pyproject.toml` and
  `harness.__version__` to 0.4.15 (they had stayed at 0.4.12 since v0.4.12, so
  the PyPI tag check failed on 0.4.13 and 0.4.14). The signed `stable.json` is
  produced offline with key `3e5f4f12` and uploaded before the draft release is
  published. Docs updated: `docs/UPDATES.md` (release state).
- **fix(charts): a missing drawing library is now a named, testable failure
  instead of a silent 503.** The vendored interpreter can boot the agent stack
  (`langgraph`) while `matplotlib`/`plotly` are absent, so every chat chart
  returned `503 "install the Python runtime"` — pointing at a runtime that was
  already installed. `PYTHON_RUNTIME_PACKAGES` now enumerates `matplotlib`,
  `plotly`, `numpy` and `pydantic`; `PYTHON_CHART_PACKAGES` +
  `chartEngineReadiness()` define "can draw"; `probeChartEngine()` checks the
  SAME interpreter `findPython()` selects and the charts route distinguishes
  `RUNTIME_UNAVAILABLE` from `CHART_RENDER_UNAVAILABLE` (with the interpreter
  path and missing modules); `scripts/setup-python.js` verifies by importing and
  exits non-zero when the stack is missing, force-reinstalling a corrupt
  distribution; `scripts/doctor.js` verifies after a repair;
  `scripts/test-python.js` refuses to run without the chart stack;
  `python/harness/charts/render.py` names `sys.executable`; the runtime
  exposes `GET /charts/health`; `response-chart.tsx` shows the cause instead of
  italic prose; and a source-scanning regression test fails the build when the
  charts package imports a module the install list does not cover. Docs updated:
  `docs/chart-engine.md`, `docs/harness/python-runtime.md`.
- **fix(desktop): each tab now owns its chat session.** The tab strip recorded
  only the page (plus sidebar mode), so the single shell-wide
  `activeConversationId`/transcript was shared by every Chat tab: pressing `+`
  ran the global "new chat" reset and the old tab then showed the new (or empty)
  session. `DesktopTab` now carries `conversationId` (`null` = that tab's own
  fresh chat), the strip captures the live session into the tab on
  switch/new/close, restores the selected tab's conversation, names Chat tabs
  after their session, and persists the front tab
  (`be_desktop_tabs_v2_active`) so a relaunch returns to the session that was
  open. Selecting a conversation also clears a stale transcript when the id is
  not loaded yet. Docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `desktop/README.md`.
- **fix(desktop): `desktop:refresh` bridges a stale install instead of leaving
  the old UI on screen.** A packaged Stable shell serves its bundled payload
  under `<install>\app`; promoting `releases/stable/<buildId>/.next` therefore
  did not change what the window loaded, and refresh only printed a warning the
  user could miss. Refresh now stops the window and its owned server after the
  build, runs `desktop-dev-bridge.js` (reversible; keeps
  `app.bundled-<version>`), then promotes and relaunches. Docs updated:
  `docs/environments.md`.
- **fix(build): default the production build to a 12 GB V8 heap.** A local
  `desktop:refresh` died at Node 22's ~4 GB default (`JavaScript heap out of
  memory`), then again at 6.05 GB and 8.07 GB as the cap was raised. The repo's
  release history already established that the Windows payload build needs
  12 GB (v0.4.10). `scripts/lib/server.js` now supplies
  `--max-old-space-size=12288` for the managed Stable build (and
  `scripts/desktop-build.js` for Dev), keeping any explicit caller value and
  allowing `BE_BUILD_HEAP_MB` to override. Docs updated: `docs/environments.md`.
- **fix(updates): a packaged install no longer offers an in-place update it cannot
  perform.** The title-bar button and banner ran the git-based updater inside the
  installed app, whose `<install>\app` payload has no `.git` (and current packages
  do not even ship `update.js`), so *Update now* failed with "the updater did not
  report back". `/api/updates` now carries `canSelfUpdate` (`<root>/.git` exists);
  a packaged install gets **Download vX** to the signature-checked release page
  instead, and `POST /api/updates/apply` + `scripts/update-apply.js` refuse with an
  explicit message. `npm run desktop:refresh` now **fails** when the installed
  shell is not bridged instead of warning, building, promoting and reopening a
  window that still serves its bundled payload. Manifest fetches get 20 s instead
  of 8 s (a cold GitHub redirect measured 6.4 s, so checks failed spuriously).
  Test: `src/lib/updates/core.test.ts`.
  Docs updated: `docs/UPDATES.md`, `docs/environments.md`.

- **fix(ai): the model list could load empty, stay empty, or point at a model the
  endpoint does not serve.** Four defects behind "I can't see my models":
  (1) `loadModelCatalog` memoised a FAILED fetch as `{}` for the whole page load —
  the AI/LLM panel mounts while the Python runtime is still cold-starting, so one
  503 left the Model dropdown holding only the current value *and* hid the
  **Discover models** action, which was gated on that same missing catalog row
  (only a relaunch recovered it); the failed promise is no longer cached and
  `useModelCatalog` re-probes up to 3× (1.5 s apart) without ever replacing a
  loaded catalog with an empty one. (2) `canDiscover` now falls back to "the
  runtime decides" when the catalog has no row, so Discover is always available
  for a configured provider. (3) The auto-discovery throttle stamped the attempt
  BEFORE probing, so one cold-start failure locked that provider out for six
  hours; it now stores the next-allowed time and waits 6 h on success but only
  60 s on failure (new `be_model_autodiscover_v2` key, which also releases anyone
  still held by v1). (4) A successful Discover that does not list the saved model
  now adopts the newest served id and says so (the "model 'qwen3' not found" 404);
  the silent background probe only warns and never rewrites the saved config.
  The picker also prints "no models loaded yet — use Discover models" instead of
  a bare empty dropdown. Regression test: `src/lib/agent/model-catalog.test.ts`.
  No doc change — bug fixes, contracts unchanged.

- **fix(ai): the missing provider paths — Ollama Cloud, OpenCode Go, and any
  custom endpoint.** Three "I can't add my API" dead ends, all in the AI/LLM
  screen: (1) the Ollama preset is keyless, so a user whose Ollama only holds
  cloud models (`kimi-k3:cloud`) had no field for an ollama.com key —
  `OLLAMA_API_KEY` was not even in the vault registry; (2) only the OpenCode Zen
  (pay-as-you-go) base URL existed, so a Go subscriber's key was sent to the
  wrong gateway; (3) a custom endpoint could never hold a key — the key editor
  was resolved from the *base URL* matching a preset, which a custom URL never
  does, so the field disappeared exactly when it was needed and the save failed
  with "An API key is required for a remote LLM provider". Added `ollama-cloud`
  (`https://ollama.com/v1`) and `opencode-go`
  (`https://opencode.ai/inference/go/openai/v1`) presets + `OLLAMA_API_KEY` in
  `PROVIDER_KEYS` + `ProviderSpec`s in the Python catalog (a preset id the
  runtime does not know fails every run), made `ProviderKeyEditor` fall back to
  the saved provider id (`custom` → `CUSTOM_LLM_API_KEY`), and surfaced
  OpenCode/OpenCode Go/Custom in the Popular group. New test asserts every
  `LLM_PRESETS` id exists in `PROVIDER_CATALOG` so the two lists cannot drift.
  Docs updated: `docs/ARCHITECTURE.md` (AI/LLM provider invariant),
  `docs/NAVIGATION.md` (key-registry row pointed at a deleted file).

- **fix(search): the boot warm-index can no longer freeze the agent runtime.**
  A packaged install indexes its own payload (`python/harness` under
  `<install>\app`), so the first boot walked ~1,500 files / 19k chunks while
  `bulk_index` ran synchronously on the event loop; `/health` never answered,
  the front door waited 45 s per call and reported "runtime unavailable", and
  every runtime-backed action (agent, broker/MCP tests) hung until it finished.
  `documents_from_repository` now skips a payload marked by
  `scripts/vendor/python` (a packaged install, never the user's project),
  repository collection runs via `asyncio.to_thread`, and `index_documents`
  yields to the event loop every 50 ms. Verified with `py-spy` (stack pinned in
  `save_chunks`) and by a healthy `/health` after a fresh boot.
  Docs updated: `docs/harness/search-retrieval.md`.

- **fix(release): rotate the update-signing key and ship v0.4.13, the first
  release with a signed manifest since v0.4.1.** The in-app update check polls
  `releases/latest/download/stable.json`; v0.4.2 and v0.4.3 shipped without one,
  so every user got "couldn't check" (verified: `node scripts/update.js --check`
  → `HTTP 404`) and no notice could reach them. The old private key
  (`7a08848038457e37`) is gone, so `npm run update:keys` generated
  `3e5f4f12096f06ac`; `config/update-signing-key.pub` now carries it and the
  private half stays gitignored in `.black-eclipse/update-keys/`. Anyone on
  0.4.12 or older trusts the old key and must install 0.4.13 manually once, then
  updates resume normally. Version bumped 0.4.12 → 0.4.13.
  Published with the signed manifest attached: `node scripts/update.js --check`
  now verifies and reports *up to date* on 0.4.13 (it printed `HTTP 404` before),
  and `npm run check:downloads` serves all three installer aliases.
  Docs updated: `docs/UPDATES.md` (release state, key id, rotation cost).

- **chore(repo): the project now lives at `dumbpabloo/BlackEclipse-V1.0`.** Every
  live reference was repointed: `package.json` (`repository`/`homepage`/`bugs`),
  `config/updates.json` (the update check would otherwise poll a redirect),
  both installer scripts and their `-Repo` defaults, the README
  download/install/source links, `.github/ISSUE_TEMPLATE/config.yml`, the release
  workflow's install table, `desktop-package.js` and `check-downloads.js`.
  Left alone deliberately: historical entries in `docs/changelog/`, and the
  pre-commit commit identity (`121116805+desimarijuana@users.noreply.github.com`),
  whose numeric user id must not be guessed.
  Docs: `docs/install.md`, `docs/UPDATES.md`, `docs/repository-guards.md`,
  `docs/OPEN-SOURCE-READINESS.md`.

## 2026-11-18

- **feat(bots): desks — a saved team run, so a monitor bot and an executor bot can
  work one question.** A desk is an automation with `action.type = "run_team"`
  and its `TeamDefinition` in `action.config.team` (tagged `bot` + `desk`), so
  schedules, triggers, versions, pause/delete and run history are the automation's
  own and no new store exists. `dispatcher._run_team` now runs `config.team` and
  keeps the Institution preset as the fallback; create-time validation refuses a
  malformed graph, a one-member "team", an unroutable stage, and any `order_submit`
  in a member (a team has no mandate; a demo submit could otherwise spend an
  unrelated active mandate). `TeamService._team_tools` strips order-submitting
  tools from the delegated surface even when an agent's tools are inherited, and
  `read_run_output` moves to the team layer.
  The Bots empty state gets **New desk**: a builder (role templates, stages,
  instructions, tools, dependencies, review) whose Save is gated by
  `POST /team/validate`; a selected desk opens a room with the live stage timeline,
  the deterministic result and run history (not the agent composer). Desks are
  excluded from group-room members. A desk can run manually, on an interval, or
  **when a bot finishes**: the engine now publishes the previously-declared
  `automation.completed` / `automation.failed` events (ids and state only, never
  the output), `bot_create`/`bot_update` accept event/condition triggers, and the
  schedule editor authors them. A desk may name a `contextAutomationId`; its last
  result is injected into the starting stages as an **unverified lead** and is never
  written into findings. Duplicating a desk re-issues the team and member agent ids,
  so a copy never shares the original's registered agents. A desk's `order_preview`
  approval is surfaced in the desk room (the same self-polling trade banner the bot
  composer uses) and is matched in the execution's delivery by the subtask's run id
  (`Task.assignedRunId`), not only the team root. Fixed a latent
  `AutomationEngine.wait_idle` busy loop (a done task was drained only by a callback
  that needed one loop turn).
  Docs: `docs/harness/desks-plan.md` (now Current, with phase status),
  `docs/harness/bot-team-orchestration.md`, `docs/harness/automation-engine.md`,
  `docs/bot-mode.md`, `docs/NAVIGATION.md`.

- **always-on: bots keep running with the window closed, and a scheduled run is
  no longer a shorter/narrower agent.** The desktop tray now has one **Run in
  background** switch: it registers the `HKCU` `Run` value with
  `"<exe>" --background` and sets keep-warm together (autostart without
  keep-warm still quits on close; keep-warm without autostart does not survive
  reboot). `--background` starts the window minimized; a failed registry write
  turns the switch back off and logs why.
  The automation default `execution.maxRuntimeS` rises 900 → 1200 s so a
  scheduled bot gets the same 20-minute floor as one chat turn (UI bot draft
  matches; cap stays 24 h). Parity is now pinned by
  `python/tests/test_automation_bot_parity.py` (a scheduled run carries the bot
  brain, analysis sandbox, private memory, model pin and images) and a
  `registry.test.ts` case (agentId, chatId, memoryScope, model, images are
  forwarded), with the shared vs deliberately-different contract written down.
  Docs: `docs/bot-mode.md`, `docs/harness/automation-engine.md`,
  `desktop/README.md`, `docs/CHANGELOG.md`.

- **plan(desks): user-authored bot teams, end to end.** A design for the
  monitor-bot → desk → executor topology: a desk is a `run_team` automation whose
  `config.team` is the `TeamDefinition` (so durability, versioning, triggers,
  delivery and history are reused), roles are team members rather than bot rows,
  the desk may only `order_preview`, and a trading bot keeps the mandate and the
  one submit path. The plan sequences five independently shippable phases
  (generalize `_run_team`; builder; runner view; wire `automation.completed` +
  context hand-off; execution bridge) with the exact files, validation rules,
  tests, risks and non-goals. No code changed; the current gaps it closes are now
  named in the team doc's known limitations.
  Docs: `docs/harness/desks-plan.md` (new, status `Proposed`),
  `docs/harness/bot-team-orchestration.md`, `docs/NAVIGATION.md`.

- **release: cut v0.4.12.** The shared-payload release build: one Next compile
  on Ubuntu, package jobs only do the platform half. Ships the first-run setup
  fix (the reason this release chain exists) plus the vendored-Python fix for
  macOS/Linux; the macOS smoke is advisory so the Windows and Linux installers
  publish even if it is slow. Version bump across `package.json`,
  `package-lock.json`, `pyproject.toml` and `harness.__version__`;
  `sbom.cdx.json`, `THIRD-PARTY-NOTICES.md` and `docs/harness/benchmarks.md`
  regenerated. Docs: `docs/CHANGELOG.md` only.

- **perf(release): build the Next payload once, on Ubuntu, for every platform.**
  This supersedes the `cpus: 1` + low-memory experiment above (not viable: one
  worker took >16 minutes locally and still needed >6 GB, and raising
  `NODE_OPTIONS` multiplied by the build's worker pool is what exhausted the
  16 GB Windows runner). The release workflow now has a `payload` job that
  builds `.next-desktop` once and uploads it; the Windows/macOS/Linux jobs
  download it and only do the platform-specific half (Python provisioning,
  Tauri shell, packaging, installers, smoke). Windows never runs a Next build,
  so its OOM cannot recur, and each release does one compile instead of three.
  Docs updated: `docs/CHANGELOG.md`.

- **fix(build): bound the build's memory instead of raising one process's cap.**
  v0.4.9–v0.4.11 all died in the Windows payload build (`FATAL ERROR: Reached
  heap limit`, then killed outright at 12 GB). `NODE_OPTIONS` applies to every
  Node child, so a large `--max-old-space-size` multiplied by Next's build
  worker pool exhausted a 16 GB runner. With `BE_BUILD_LOW_MEMORY=1` (set for CI
  only) `next.config.ts` uses one build worker and webpack's low-memory mode,
  and the per-process cap goes back to 6 GB. Local builds keep the fast
  defaults. Docs updated: `docs/CHANGELOG.md`.

- **perf(release): publish what builds, and make a Windows-only run cheap.**
  A red macOS job used to block the Windows and Linux installers from
  publishing, and every attempt paid for three full payload builds. The release
  workflow now:
  - runs the `release` job with `always()` and refuses only when there is **no**
    installer at all, so a failing platform no longer withholds the others;
  - treats the macOS smoke as advisory (`continue-on-error`) with a 15-minute
    step timeout — the run still records it, and the smoke prints the runtime's
    own log lines;
  - caches `Black-Eclipse-site/.next/cache` per runner, so a tag build reuses
    the previous compile (the payload build is the 6–8 minute step);
  - accepts a `workflow_dispatch` `only` input (`windows-latest` etc.) to build
    one platform in ~20 minutes while iterating, while tag pushes still build
    all three (`!inputs.only`).
  Docs updated: `docs/CHANGELOG.md`.

- **release: cut v0.4.11.** Build budgets only: 12 GB heap for the Windows
  payload build and the runtime's 600 s cold-start budget with a 420 s smoke
  wait (plus first-harness-line evidence). The runtime itself is unchanged;
  Ubuntu has passed its smoke on every attempt since the vendored-Python fix.
  Version bump across `package.json`, `package-lock.json`, `pyproject.toml` and
  `harness.__version__`; `sbom.cdx.json`, `THIRD-PARTY-NOTICES.md` and
  `docs/harness/benchmarks.md` regenerated. Docs: `docs/CHANGELOG.md` only.

- **fix(release): finish the build-budget fix for the packaged release.** v0.4.10
  still failed on Windows at the standalone payload (`Reached heap limit` with
  the 8 GB cap) and on macOS at the runtime smoke (the agent runtime was still
  starting when the smoke's 300 s budget expired). The workflow now uses a
  12 GB heap and gives the runtime its documented 600 s cold-start budget with a
  420 s smoke wait. The smoke also prints the FIRST harness lines (resolved
  interpreter + spawn command), not only the tail, so a macOS failure names its
  own cause. Docs updated: `docs/CHANGELOG.md`.

- **release: cut v0.4.10.** The Linux job of v0.4.9 proved the vendored-Python
  fix (smoke passed); this release adds the Windows heap fix (8 GB) so the
  standalone payload builds on every runner. Version bump across `package.json`,
  `package-lock.json`, `pyproject.toml` and `harness.__version__`;
  `sbom.cdx.json`, `THIRD-PARTY-NOTICES.md` and `docs/harness/benchmarks.md`
  regenerated. Docs: `docs/CHANGELOG.md` only.

- **fix(release): give the Windows payload build the heap it actually needs.**
  v0.4.9's Linux job passed (including the smoke — the vendored-Python fix
  works), its macOS job failed fetching the Rust toolchain (transient), and its
  Windows job died in `Build the standalone payload` with
  `FATAL ERROR: Reached heap limit … 6064 MB` against the 6144 MB cap. The
  release workflow's `NODE_OPTIONS` is raised to 8192 MB (runners have 14–16 GB).
  Docs updated: `docs/CHANGELOG.md`.

- **release: cut v0.4.9.** Fixes the reason v0.4.4–v0.4.8 could not publish:
  a packaged macOS/Linux install could not find its own vendored Python, so the
  release smoke (correctly) refused to ship a build whose agent runtime never
  became healthy. Version bump across `package.json`, `package-lock.json`,
  `pyproject.toml` and `harness.__version__`; `sbom.cdx.json`,
  `THIRD-PARTY-NOTICES.md` and `docs/harness/benchmarks.md` regenerated.
  Docs: `docs/CHANGELOG.md` only.

- **fix(runtime): a packaged macOS or Linux install can find its own Python.**
  `findPython()` only ever considered the vendored interpreter on Windows
  (`scripts/vendor/python/python.exe`); everywhere else it fell straight through
  to a SYSTEM `python3`, which rarely has `langgraph`. The release smoke said it
  plainly — `[harness] Python with agent dependencies not found` — while the
  portable runtime provisioned by `setup-portable-python.js` sat unused at
  `scripts/vendor/python/bin/python3`. It is now the preferred interpreter on
  every platform, so Linux/macOS installs get working agent features instead of
  a permanent "runtime unavailable". The spawn path also logs the resolved
  interpreter and port, a held cross-context spawn lock, and a spawn `error`
  event, and the packaged smoke prints the log's harness/spawn/traceback lines
  instead of a raw tail — the missing evidence that hid this for three releases.
  Docs updated: `docs/CHANGELOG.md`, `docs/ARCHITECTURE.md`.

- **release: cut v0.4.8.** Ships the first-run setup fix (no app shell behind
  the wizard, bounded and recoverable finish, plain-language database errors)
  and the release-gate fix (Python warm-up on every boot, smoke budget matching
  the runtime's 300 s, app-log tail on failure) so the packaged installers can
  finally publish. Version bump across `package.json`, `package-lock.json`,
  `pyproject.toml` and `harness.__version__`; `sbom.cdx.json`,
  `THIRD-PARTY-NOTICES.md` and `docs/harness/benchmarks.md` regenerated.
  Docs: `docs/CHANGELOG.md` only (no behaviour change beyond the two entries
  below).

- **feat(quant): a backtest can run on the operator's own declared dataset.**
  The Custom REST API connector (Settings → Data Sources) already let an
  operator bring any endpoint with their own key; the backtester could not read
  it, so "backtest my model on my data" silently ran on the built-in providers.
  `quant/custom_source.py` now resolves a named dataset through the existing
  `custom_dataset_records` bridge capability, and `quant/datasets.py` treats it
  as exclusive — no gateway call, no cache, no fallback; a failure is
  `CUSTOM_SOURCE_UNAVAILABLE` / `MISSING_DATA`. The requested window is
  re-applied to returned rows, records are mapped from
  `timestamp/open/high/low/close/volume` (common aliases accepted), and the
  result carries `metadata.dataSource` + a `CUSTOM_DATA_SOURCE` warning so a
  user-data run is never mistaken for Eclipse-verified market data. New
  `dataSource` argument on `run_backtest`, `run_portfolio_backtest`,
  `run_python_strategy`, `optimize_parameters`, `run_walk_forward`,
  `run_monte_carlo`, `run_sensitivity_analysis`, `run_robustness_analysis`.
  The Backtest screen gains a **Data source** selector (declared datasets with a
  connector attached), typed in `src/lib/backtest/backtest-client.ts` and
  forwarded by `POST /quant/backtest` / `portfolio-backtest`.
  Docs updated: `docs/quant-engine.md`, `docs/harness/tool-registry.json`
  (regenerated), `docs/CHANGELOG.md`.

- **fix(release): the packaged smoke gate now waits as long as the runtime is
  allowed, and reports why.** v0.4.4–v0.4.7 could not publish: the Windows and
  macOS builds failed `Smoke test` with "the Python runtime never became healthy
  within 180s" while the runtime log showed uvicorn up. The gate's budget (180 s)
  was shorter than the runtime's own cold-start budget (300 s), and a cold first
  import from a freshly written 2.3 GB payload measured over three minutes. On a
  first run the runtime is warmed during setup again (see the entry above), which
  removes the cold start from the first chat; `scripts/desktop-smoke.js` now
  defaults to 300 s and prints the packaged app's log tail on a harness failure
  instead of only "never healthy" (the shell's stdout does not carry it).
  Packaging tooling: `desktop-package.js --link` used `unlinkSync` on a
  directory (so local linked packaging always died with EEXIST), a PE layout
  `pe-library` cannot parse aborted the whole package at the branding step —
  branding is cosmetic, so it now warns and continues — and `BE_PACKAGE_OUT`
  lets a local test package build beside the real `dist/BlackEclipse` instead
  of fighting a stale file handle there.
  Verified locally on a full-copy Windows package: uvicorn answers
  `/health/live` 200 and `/api/harness/model-runtime/health` returns 200.
  Docs updated: `docs/ARCHITECTURE.md`, `docs/onboarding-plan.md`,
  `docs/CHANGELOG.md`.

- **chore(issues): backlog triaged on the renamed remote.** Filed six issues on
  `dumbpabloo/BlackEclipse-V1.0` (#15–#20) from an audit of the tree: Eclipse
  as an MCP server is implemented and tested but no transport is ever mounted
  (`mcp/server_exposure.py::build_asgi_app` has no caller); non-text MCP results
  are flattened to metadata; the MCP authorization-code OAuth leg still needs a
  manual https step; the per-run call budget falls back to one shared
  `"anonymous"` bucket and truncation names no tools; five stale PRs (#10–#14)
  need triage; and `screens/settings.tsx` (1,023 lines) still holds its tab
  bodies inline. No code changed — `npx tsc --noEmit` was clean before filing.
  no doc change — issue tracker only.

- **release: cut v0.4.6.** Carries the first-run setup fix: a new install no
  longer mounts the streaming app shell behind the wizard (the cause of the
  permanent "Saving…"), the boot pipeline and every app-wide poller wait for
  setup to finish, finishing is bounded and retryable, busy-database writes are
  retried and explained in plain language, and the wizard gets Copy diagnostics.
  Version bump across `package.json`, `package-lock.json`, `pyproject.toml` and
  `harness.__version__`; `sbom.cdx.json` / `THIRD-PARTY-NOTICES.md` and
  `docs/harness/benchmarks.md` regenerated for the new version.
  Docs: `docs/CHANGELOG.md` only (no behaviour change beyond the fix already
  documented below).

- **fix(setup): a new install can no longer get stuck on "Saving…".** The
  wizard is a full-screen overlay mounted over the *live* app shell, so a
  first run had the whole terminal running behind it: two permanent SSE streams
  (`/api/ui/stream`, `/api/sdk/app/stream`) plus ~30 boot requests. Browsers
  allow six concurrent HTTP/1.1 connections per origin and an SSE holds its slot
  for the life of the page, so `POST /api/setup` queued behind them and was
  never dispatched — reproduced by holding the connection slots open, which
  leaves the footer spinning indefinitely (the reported screenshot). Two fixes,
  one structural and one defensive:
  - `src/app/page.tsx` now asks `src/lib/setup/gate.ts` (server-side, per
    request) whether this is a brand-new install and renders a light
    placeholder instead of `StockChat`. The wizard then owns the connection
    budget; the app mounts on the reload after finish. The gate answers
    `incomplete` only for a definite new install and `unknown` (render the app)
    if the read fails, so a DB problem can never hide the product behind a
    wizard. The whole app-wide activity stack (`AppActivity`) is not rendered
    while setup is pending, so the loader's six warm-ups never fire.
  - The finish request now has a 30 s deadline. On timeout/error the wizard
    re-reads `/api/setup`: if `completed` is true it enters the app (the save
    landed; only the reply was lost), otherwise it shows an error and stays
    retryable. `POST /api/setup` also records the setup *before* reporting an
    AI/key step failure (`{ok:true, warning}`), so a provider-vault error can
    neither undo nor block the completed setup; the Review step explains the
    warning and offers Back or "Enter Eclipse".
  - Tests: `src/lib/setup/gate.test.ts` (6 cases: recorded, unfinished,
    corrupt flag, new vs upgraded probe, unreadable DB) and
    `src/app/api/setup/route.test.ts` (AI failure still completes setup and
    returns a warning; skip needs no AI; stale risk ack and an unacknowledged
    advanced source are still refused before any write). `npx vitest run`
    5069 pass; `npx tsc --noEmit` clean. Verified end-to-end on a throwaway
    `BE_DATA_DIR`: the wizard opens with **zero** SSE streams and the save
    posts immediately; the app mounts after finish.
  Docs updated: `docs/onboarding-plan.md` (§4.6 mounting invariant, §7
  failure table), `docs/CHANGELOG.md`.

- **feat(setup): the first run now competes with nothing, and every failure is
  actionable.** Follow-up to the fix above, so a cold or loaded machine cannot
  reproduce a setup stall through a different door:
  - `instrumentation.ts` defers the heavy half of the background boot pipeline
    (universe seed, market warm-up, news/Investor-Eye ingests, schedules, daily
    backup) until `onboarding_v1.completed` is set (2 s poll, 30 min cap), after
    the cheap essentials. The Python runtime warm-up deliberately still runs
    during setup: its first import from a cold payload measured over three
    minutes, and deferring it moved that cold start onto the first chat after
    setup (and failed the packaged release smoke). A new install can only see
    the wizard, so the deferred jobs were only competing for CPU, SQLite and
    network.
  - `src/components/layout/app-activity.tsx` holds back every app-wide poller,
    stream, update check and shell guard while `page.tsx` withholds the shell;
    the wizard is the only client traffic on a first run.
  - A forced re-run (`?setup=1`) still overlays the live shell, so the wizard
    announces itself via `src/lib/setup/overlay.ts` and the stream owners
    (`useAppShellSync`, `SavedPagesNav`, dashboard, pages) close their SSE and
    stop polling while it is open.
  - The native "Where your data lives" notice no longer covers the footer's
    "Finish setup": the shell source puts it top-right, skips it while the
    dialog is open and marks it shown from the webview; `OnboardingShell` moves
    it out of the way (`pointer-events: none` except its button) for builds
    that predate that.
  - `db.ts` gives the SQLite adapter a 5 s busy timeout (the retried upserts still finish inside the 30 s deadline); `completeOnboarding`
    retries its three idempotent upserts; `describeSetupWriteError` turns a
    busy/read-only database into plain language, and the wizard adds a
    "Copy diagnostics" action. A save that takes longer than 6 s says so in the
    footer ("the local database is taking longer than usual") instead of leaving
    an unexplained spinner.
  - `scripts/smoke-onboarding.js` gains `SMOKE_FINISH=1`: it clicks Finish and
    asserts the wizard unmounts and the app mounts (run it against a throwaway
    `BE_DATA_DIR`).
  - Tests: `npx vitest run` 5074 pass; `npx tsc --noEmit` clean.
  - Verified end-to-end on a throwaway `BE_DATA_DIR` (production build):
    wizard visible in 0.9 s with **0 SSE streams** and only
    `GET theme` + `GET setup` + `GET provider-keys`; Finish → app in 1.4 s; a
    forced re-run over the live shell holds 0 open streams; a deliberately
    locked database showed the slow-save hint at 6.1 s, the plain-language busy
    message at 21.2 s (wizard still retryable, no raw Prisma text), and the
    retry after the lock cleared entered the app in 0.8 s.
  Docs updated: `docs/onboarding-plan.md`, `docs/ARCHITECTURE.md`,
  `docs/CHANGELOG.md`.

- **release: cut v0.4.3.** Version bump across `package.json`,
  `package-lock.json`, `pyproject.toml` and `harness.__version__` so the first
  release built from `main` after the installer-branding commit carries the
  eclipse icon on the downloadable setup `.exe` (v0.4.2 predated it).
  Docs: `docs/CHANGELOG.md` only (no behaviour change).

- **test(guard): the line-ending guard no longer reads installer BMPs as text.**
  The branding commit added `welcome.bmp`/`header.bmp`; the guard scanned the
  first as text and failed on pixel bytes that happen to contain CRLF and bare
  LF. `.gitattributes` now marks `*.bmp binary` and the guard's extension list
  skips it.
  Docs: `docs/CHANGELOG.md` (no contract change).

- **fix(installer): fail the build when the setup `.exe` is not branded.** The
  published v0.4.2 setup still drew NSIS's stock globe/disk because its tag
  pointed at a commit that forked before `MUI_ICON` landed; `main` had the fix,
  but the release workflow builds the tagged commit, so downloaders never got
  it. `scripts/verify-installer-icon.js` now reads the finished exe's
  `RT_GROUP_ICON` and compares it with `public/branding/black-eclipse.ico`
  (16/24/32/48/64/128/256px, all 32bpp); `desktop-installer.js` runs it after
  `makensis` and exits 7 on a mismatch. `npm run installer:verify` checks an
  existing file by hand.
  Docs: `docs/desktop-app-plan.md`, `docs/UPDATES.md`, `docs/CHANGELOG.md`.

- **feat(installer): the setup `.exe` now shows the eclipse mark, and the wizard
  carries the product identity.** `MUI_ICON` / `MUI_UNICON` replace NSIS's stock
  globe icon; a committed 164x314 dark brand sidebar (Welcome, Finish, Uninstall)
  and a 150x57 header are generated from `public/branding/LOGO-WORDMARK.svg` by
  `scripts/make-installer-assets.js` (`npm run installer:assets`). The stock
  Directory page is gone (the per-user location is fixed; `/D=` still overrides
  it for silent installs), Next reads "Install", and the uninstaller explains
  that user data survives removal. `scripts/desktop-installer.js` preflights the
  assets before `makensis` so a missing bitmap fails with an actionable message.
  Docs: `docs/desktop-app-plan.md`, `docs/CHANGELOG.md`.

- **docs(updates): document the lock-safe update path.** `docs/UPDATES.md` now
  describes the `stopping` phase, the spent-job rule, the non-destructive
  rollback, and corrects the release state to v0.4.1.
  Docs: `docs/UPDATES.md`, `docs/CHANGELOG.md`.

- **test(trading): demo soak closed at 156 minutes — properties proven, 48–72 h
  deferred by the operator.** Final measured record (isolated runtime :8799,
  copied state): 03:02:59Z→05:38:09Z, **156 fires, 156 distinct minutes, 0
  duplicate minutes**, 136 `BAR_ALREADY_PROCESSED`, 2 filled on fresh 5-minute
  bars (`ord_aa35ce8b730b` / `ord_44af638be5fc`), 2 `POSITION_ALREADY_OPEN`, 14
  no-signal (MT5 down), 1 `MANDATE_INACTIVE` (the 2-order daily cap), 1
  `QUANT_ERROR`; **2 ledger rows, 0 unexplained orders**. Supervisor, MT5
  watchdog and :8799 stopped; demo account flat. A 48–72 h record is explicitly
  deferred (needs a host that stays up), not failed.
  Docs: `docs/trading-bot-live-testing-plan.md`, `docs/CHANGELOG.md`.

- **feat(trading): fresh-bar entries captured in minutes, not a day.** The soak
  bot was switched to a **5-minute** smoke strategy (`eurusd_m5_smoke`, synthetic
  backtest for the approval gate, real M5 broker bars at runtime). Isolated
  runtime (:8799) at 05:29–05:31Z: `ord_aa35ce8b730b` (ticket 11451776390,
  1.09863) on bar 07:20, a `POSITION_ALREADY_OPEN` skip on the next fire, then
  `ord_44af638be5fc` (ticket 11451810596, 1.09835) on bar 07:25 — all with
  `automationId`, `mandateId`, `runId`, magic 741879. Soak to 05:32Z: **150
  fires, 150 distinct minutes, 0 duplicate minutes**, 132
  `BAR_ALREADY_PROCESSED`, 2 filled, 2 not-stacked, 14 no-signal (MT5 down), and
  **no unexplained order**. Docs: `docs/trading-bot-live-testing-plan.md`,
  `docs/CHANGELOG.md`.

- **fix(updates): an update can no longer break the install on a locked
  `node_modules`.** Windows keeps a loaded `.node` binary locked for the life of
  the process that loaded it, and `npm ci` empties `node_modules` before it
  installs, so a running app's `next-swc`/`skia` left the tree with no
  dependencies at all. The runner now probes by rename, waits, and either stops
  the app it owns (new `stopping` phase) or fails with the install intact; the
  staged job is also read against the installed version so a stale job cannot
  read as pending. The trading runner now names the first no-signal reason
  instead of only counting symbols.

- **chore(sbom): regenerate the SBOM and notices for v0.4.1.** The 0.4.1 version
  bump left `sbom.cdx.json` / `THIRD-PARTY-NOTICES.md` at 0.4.0, so
  `sbom-artifact.test.ts` failed on a clean tree. Regenerated from the lockfiles
  (1335 components); no product behaviour changes.

- **feat(autonomy): a running goal shows its activity steps in the chat.** The
  verdict line was only the end of a turn; a goal turn runs as a background
  task, so nothing filled the transcript while it worked. `useGoalWatch` polls
  the session's goals and, for each, resolves the turn's live run and reads its
  persisted tool trace (`GET /api/harness/runs/{runId}/events`), mapping rows to
  the SAME `ActivityItem` shape the live chat feed renders
  (`lib/harness/goal-activity.ts`). One message per goal turn is created and
  updated in place, then finalised by the verdict
  (`lib/harness/goal-transcript.ts`, pure builders), so steps and the verdict
  share a bubble and a late step cannot reopen a closed turn; the card persists
  so a reload keeps it. Two gaps the live check exposed and this closes: a turn
  that ENDS a goal records its verdict and flips status in the same instant (so
  open-only polling missed `done` — each goal is now swept once as it closes),
  and a running task exposes no run id (it is derived from
  `taskrun_<taskId>_<attempt>`). Tests: mapping, watch-target sweep, run-id
  candidates, transcript builders, size ratchet re-pinned, plus an opt-in live
  check (`goal-watch.live.test.ts`, `BE_LIVE_GOAL=<goalId>`). Verified in the
  running app: "**Goal · turn 1** — working" with its steps, closing to "**done**"
  with the steps retained. Docs: `docs/harness/autonomy.md`.

- **test(trading): the demo soak runs isolated and has 119 clean minutes.** The
  shared app is killed every few minutes, so the soak was moved to a copy of the
  bot state (`VACUUM INTO .black-eclipse/soak-iso/agent-memory.db`), harness
  port **8799**, its own `BE_DATA_DIR`, a restarting supervisor (25 h horizon)
  and an MT5 watchdog. Measured 03:02→05:01Z: 119 unattended fires, **119 distinct
  minutes, 0 duplicate minutes**, 106 `BAR_ALREADY_PROCESSED` + 13 no-signal fires
  while MT5 was down, **0 orders, 0 ledger rows, 0 positions**. The runner now
  carries the failed symbol's reason into the decision
  (`no actionable signal (EURUSD: signal failed: …)`).
  Note: a concurrent session committed the tree and a later restore discarded the
  uncommitted doc edits; the code fix and this entry were re-applied on top of
  `76f87305`. Tests: 32 runner/e2e/size/phase. Docs:
  `docs/trading-bot-live-testing-plan.md` (L6), `docs/CHANGELOG.md`.


- **release: v0.4.1.** `v0.4.0` was published from a commit that predates the
  update system, feature packs, the alternative-intelligence signal engine and the
  trading-bot work, so anyone downloading it got an older app than the source.
  Rather than silently re-cut a published version, the version is bumped
  (`package.json` + `pyproject.toml`, both 0.4.1) and a new release is built from
  the current `main`; `v0.4.0` stays as history and the download links move on
  their own once the new release is published.
  Doc change: `docs/CHANGELOG.md`, `README.md`.

- **fix(test): the watcher test was time-dependent, not broken.** The test wrote
  `two\n` over `one\n` — the same length — and then called `os.utime(target,
  None)`, which can land on the same timestamp on a filesystem with coarse mtime
  resolution. The watcher diffs mtime+size, so the "modified" event was simply
  invisible and the assertion failed intermittently (it passed on the branch and
  failed on the merged `main` with identical code). The fixture now writes
  different-length content AND sets a strictly newer mtime, so the event is
  deterministic. Verified: 34 passed, three consecutive runs.
  Doc change: `docs/CHANGELOG.md`.

- **fix(desktop): v0.4.4 restores the SQLite binding guard that v0.4.3 shipped
  without, and makes a failed database check impossible to get stuck on.** v0.4.3
  was cut from `main`, which never received v0.4.2's packaging fix: `scripts/lib/native-modules.js`
  and the `desktop-package`/`desktop-installer`/`desktop-bundle` probes were absent
  from that tree, so the release went out with Prisma's nested `better-sqlite3@12`
  copy and no loadable binding for the bundled runtime. Every query then failed,
  `db-guard` threw "Could not locate the bindings file", classified it as
  corruption, wrote `<data>/.runtime/db-guard.failed`, and every later launch
  short-circuited with "The server stopped before the app was ready" — a dead end,
  because the marker was only cleared by the successful guard run it was blocking.
  Fixes: the binding guard is restored, and it now probes under the payload's
  *bundled* Node (`ensureRuntimeSqlite` fetches the prebuilt for that ABI) instead
  of the build machine's, so a version skew between CI and the shipped runtime
  cannot silently produce an unloadable binary; `db-guard.js` exits **2**
  (environment) rather than **1** (corruption) when it cannot inspect the file, so
  a missing binding or a lock can no longer trigger a rebuild that replaces
  healthy data, and it opens read-write so a hot journal rolls back instead of
  reading as corrupt; `desktop-server.js` re-runs the guard for a stored failure
  and clears it on success, and names the real backups directory instead of
  `Black-Eclipse-site/backups/` plus `npm run doctor`, neither of which exists in
  an install. The release smoke test — which runs the packaged binary in CI and
  previously asserted only that `/` answered, so an unusable binding passed the
  gate and published — now also requires `/api/alerts` to answer 200 (a plain
  table read: 200 with an empty list on a fresh install, 500 without the binding).
  `/api/setup` is deliberately not the probe: with no database yet it returns 200
  from defaults without ever touching SQLite.
  Test: `src/lib/desktop/db-guard.test.ts` pins "missing binding ⇒ exit 2, never
  corruption". Verified on a real 0.4.3 install: the guard reports healthy and the
  app boots with the user's data intact; the `/api/alerts` gate was verified to
  return 200 on a healthy payload and 500 with the binding removed.
  Version bumped to 0.4.4 in `package.json`, `package-lock.json` and
  `pyproject.toml`. Note for support: an already-installed broken build cannot
  self-update (it cannot start), so affected users must reinstall; their data
  lives in the platform data directory and survives.
  Doc change: `desktop/README.md` (Database guard section: exit-code contract,
  the runtime-ABI packaging invariant and the release smoke gate).

- **fix(release): the packaged-app smoke test now fails when the Python runtime
  never becomes healthy.** A build whose agent runtime hangs still serves `/` and
  still passes the database probe, so it published — and every chat, agent and
  research page then waits on a runtime that never answers while the window looks
  fine. `scripts/desktop-smoke.js` (already run by the release workflow on the
  real packaged binary) now requires
  `GET /api/harness/model-runtime/health` to answer 200 within
  `BE_SMOKE_HARNESS_MS` (default 180 s), retrying while the runtime warms. That
  route is the same one the UI uses to decide the runtime is available, so it
  exercises the real path rather than a synthetic probe; verified against a live
  install: 200 while uvicorn answers, 500 once the harness process is killed, and
  a timeout when the runtime never comes up. A build that regresses this now goes
  red before an installer is published instead of reaching users. Version bumped
  to 0.4.5 (`package.json`, `package-lock.json`, `pyproject.toml`,
  `harness.__version__`, regenerated `sbom.cdx.json` + `THIRD-PARTY-NOTICES.md`)
  so the gate is inside the artifact that ships — `v0.4.4` was built before it.
  Doc change: `desktop/README.md` (release-gate bullet now names the runtime
  assertion).

- **fix(harness): a request no longer waits the runtime's whole cold-start
  budget.** `DEFAULT_START_TIMEOUT_MS` is 5 minutes on purpose — the interpreter
  imports langchain, browser, quant and ML, and a constrained host genuinely
  needs minutes. But `ensurePythonRuntime()` let a *page request* inherit that
  budget, so a stalled runtime made every agent/chat/research page spin silently
  for five minutes with no reason shown: the user's "other pages are not
  working". The budget is now split: the background spawn keeps its 5-minute
  allowance, while a request waits at most `DEFAULT_REQUEST_WAIT_MS` (45 s,
  `HARNESS_PY_REQUEST_WAIT_MS`) and then returns `false`, which the routes already
  turn into a 503 with a reason. The spawn is NOT cancelled — the next request
  hits the healthy TTL fast path, so a slow first launch recovers without a
  restart. Test: `runtime-supervision.test.ts` pins the relationship
  (`DEFAULT_REQUEST_WAIT_MS < DEFAULT_START_TIMEOUT_MS / 2`) and the override /
  fallback behaviour. Checks: vitest 547 files / 5061 tests, `tsc --noEmit` clean.
  Doc change: `desktop/README.md` (new *Agent runtime readiness* section).

- **fix(harness): a stale cold-start lock left by one crash no longer kills the
  agent runtime for five minutes.** Symptom seen on a real install: the window
  served pages, the log repeated `[harness] Python runtime still starting (Ns)`
  for minutes, and **no Python process existed at all** — so every chat/agent/
  research page failed with nothing to talk to. Cause: `acquireSpawnLock()` wrote
  an EMPTY lock file and only took it over after the whole cold-start budget plus
  margin (315 s). The context that loses the lock does not spawn; it calls
  `waitForHealth()` and waits. One crash or force-quit therefore left a file that
  made every later launch wait five minutes and spawn nothing, and relaunching
  re-read the same file. The lock now records the owner pid, and
  `isSpawnLockStale()` takes it over **immediately** when that process is gone
  (`process.kill(pid, 0)`), while still respecting a live owner; locks written by
  older builds fall back to the age rule. Verified on the live install: the lock
  was 301 s old (window 315 s) with zero harness processes; after it was removed
  and the in-flight wait expired, the runtime spawned and
  `/health/live`, `/api/harness/model-runtime/health` and `/api/alerts` all
  returned 200. Tests: 4 new cases in `python-runtime.test.ts` pin
  dead-owner-immediate / live-owner-respected / legacy-age-fallback.
  **Also: a lock owned by the CURRENT process is taken over, not waited on.**
  The lock lives in the install tree (`<install>/app/.black-eclipse/`), not the
  data dir, so one leftover poisoned every later launch including the release
  smoke run's fresh profile. Waiting on our own lock was a deadlock: the process
  held the file and then waited the full start budget for the start the file was
  blocking. That is why `v0.4.5`'s release run failed the new runtime gate on
  Windows and macOS (step "Smoke test", `[smoke] FAIL - the app served but its
  Python runtime never became healthy ... within 180s`) — the gate blocked the
  release instead of shipping it, which is what it exists for. `isSpawnLockMine()`
  closes that case; 2 more tests. Version bumped to 0.4.7 so the released artifact
  carries the fix.
  Doc change: `desktop/README.md` (Agent runtime readiness).


## 2026-11-17

- **chore(release): regenerate the SBOM for v0.4.1.** The version bump changed the
  SBOM's component version, so the CI "SBOM drift check" (and `check:oss`, which
  also gates on it) went red on `main`. Regenerated: 1,335 components, version
  0.4.1. `generate-sbom.js --check` is clean again.
  Doc change: `docs/CHANGELOG.md`.


- **chore(legal): adopt a CLA and publish a trademark notice.** Added root
  `CLA.md` (plain-English, signed by one PR comment; grants relicensing and a
  patent licence while the contributor keeps copyright) and root `TRADEMARK.md`
  ("code is MIT, the name and logo are not"), wired into both `CONTRIBUTING.md`
  files, the PR template, the README licensing table, the legal register, and
  `scripts/oss-preflight.js` as required files. The blueprint's §1.4
  "DCO, not a CLA" recommendation is superseded: the strategy is MIT + adoption,
  monetising additive surfaces (pro features, marketplace, live data) instead of
  the licence, and the CLA is cheap only while the repo is single-author.
  Trademark placeholders in `docs/legal/TRADEMARK-POLICY.md` resolved to Rafay
  Ghauri / BlackEclipse; the long-form policy stays Draft pending counsel.
  Doc change: `docs/legal/README.md`, `docs/legal/LEGAL-COMPLIANCE-BLUEPRINT.md`,
  `docs/legal/TRADEMARK-POLICY.md`, `docs/OPEN-SOURCE-READINESS.md`, `README.md`,
  `docs/CHANGELOG.md`.


- **docs(legal): write down the monetization position.** Added
  `docs/monetization.md`: MIT core, revenue from additive surfaces (pro features,
  marketplace, live data, support), with the rejected models (noncommercial,
  BUSL, whole-app AGPL, phone-home paywall) and why each was refused. Added to
  `docs/NAVIGATION.md` so a future session finds the policy before proposing a
  licence change.
  Doc change: `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **fix(trading): the ownership magic now reaches existing connections, and the
  kill switch is proven scoped.** Connections created before the magic existed
  were still `magic: 0`, so their bot orders were un-killable. `_connection` /
  `list_connections` now backfill a stable per-connection magic from the label
  (pure helpers in `python/harness/trade/ownership.py`; an explicit magic is
  never overridden). Proven on the demo: a second bot filled EURUSD BUY 0.01 @
  1.09863 (ticket `11448007792`, **magic `741879`**); two working orders were
  placed, one with `741879` and a control with `777`; the connection kill switch
  returned `matched=1 cancelled=1 failed=0`, MT5 kept only the control order, and
  the filled position was left intact (by design). Account flat afterwards.
  Tests: 57 broker/size/phase (incl. backfill + last-line magic guard).
  Docs: `docs/trading-bot-live-testing-plan.md`, `docs/CHANGELOG.md`.

- **feat(install): a slim install can now actually obtain its optional packs —
  plus an honest failure screen.** Four gaps were closing the install story
  short. (1) **Feature packs were unreachable.** The slim installer ships the
  core only; browser/ml/documents/computer/charts were built into
  `dist/packs/*.zip` and published, but nothing in the shipped app could fetch
  them, so a capability failed inside a lazy import with no action to take. New
  `src/lib/desktop/packs.ts` reads the manifest the build now writes into the
  payload (`app/config/packs.json` — version, release repo, per-pack
  `sha256`/`zipBytes`), pins the archive to the app's OWN release tag, refuses
  any host outside the allowlist, downloads with live received/total progress,
  verifies SHA-256, extracts into a private staging directory and moves only the
  manifest-named package directories into `site-packages`; Remove is the
  reverse. Exposed by `GET/POST /api/desktop/packs` (guardMutation + rate limit)
  and **Settings → Data & Storage → Feature packs**
  (`src/components/settings/feature-packs-settings.tsx`, frosted-glass `Panel`,
  per-pack Download/Remove, progress bar, honest "no manifest in this build"
  state). `scripts/desktop-package.js` writes that manifest and uses the *asset*
  basename for the URL, since release assets are flat; `npm run desktop:doctor`
  now prints an `installed/total · missing …` line for the installed app so a
  "feature does nothing" report has an answer. (2) **The failure screen
  named a log instead of opening it.** The splash now shows the log path inline,
  with **Copy details** (message + log path, for a bug report) and **Open log
  folder** (`desktop_log_path` / `desktop_open_log` in the Tauri shell), and the
  messages say what to do next. (3) **SmartScreen was undocumented at the moment
  it appears** — the installer's welcome page now explains *More info → Run
  anyway* and points at `SHA256SUMS.txt`. (4) **The boot screen was off-spec**:
  it used a 0.72-alpha panel and 22px blur (a flat panel per the glass rules) and
  an opaque title strip; it now uses the exact `.glass-card` recipe and a
  transparent strip. Also corrected the WebView2 message, which still told users
  to run `npm start` (deleted with the browser lane). Pack archives are now named
  per target (`browser-win32-x64.zip`) because all three OS builds write
  `dist/packs/*.zip` into ONE flat release namespace — a bare `browser.zip` was
  uploaded three times and the last platform won. Tests:
  `src/lib/desktop/packs.test.ts` + `src/app/api/desktop/packs/route.test.ts`
  (23 cases — manifest junk, allowlist, version pinning, mirror rules, installed
  detection, unsupported states, a real local-mirror download → SHA-256 → unpack
  → install run, a corrupt archive that must install nothing, remove, and the
  route's validation/guard); `tsc` clean; full `npm run test` suite green. Docs:
  `docs/install.md`, `docs/desktop-size-plan.md` (S2 + Settings half of S3
  marked shipped), `docs/NAVIGATION.md`, `README.md`.

- **fix(ci): `test_rsl_verifier` needs the vendored interpreter too.** It builds a
  throwaway git repo and asks the verifier to run the owning test, but the
  verifier resolves `python_test` through `code/execution.py::interpreter_path()`
  - the VENDORED interpreter. A runner has none, so the check returned
  `{"exitCode": None, "reason": "COMMAND_EXECUTABLE_MISSING"}` and the candidate
  reported `passed: false, refused: false, code: null`. That is a provisioning
  gap, not a verifier regression, so it now skips at module level with the same
  hint as the other sandbox suites. Passes locally (2 tests) where the
  interpreter exists. Doc change: `docs/CHANGELOG.md`.


- **fix(ci): declare `xgboost` and pin the two ratchets the feature commit moved.**
  `2876f894` grew `python/harness/service.py` to 2,098 (pinned at 2,089) and
  `trade/service.py` to 1,214 (pinned at 1,205) without moving their ratchets, so
  `test_size_budget.py` failed; and the ML acceptance workflow grades an `xgboost`
  family that was never declared, so it failed with "requires an optional
  dependency". Both ratchets are pinned to the measured values with the reason,
  `xgboost` is declared (3.4.1) and the SBOM regenerated (1,335 components).
  Verified locally: `test_size_budget.py`, `test_ml_acceptance.py` and
  `test_rsl_verifier.py` all pass. Doc change: `docs/CHANGELOG.md`.


- **feat(trading): a bot placed a real demo order on MT5 — and the seven things
  that stopped it.** L4 of the live-test plan passed against MetaQuotes-Demo
  114826727: bot `auto_21fb2c4a633340f7be2e` (strategy `eurusd_smoke_1d` v1.0.0,
  tier L1, mandate `mnd_ac414e6099be`) filled **EURUSD BUY 0.01 @ 1.09897**
  (MT5 ticket `11447256588`, SL 1.09798, TP 1.10048; closed at 1.0989). Evidence:
  execution `autoexec_43a3e1b7c92b4962b8f0` → decision `filled` with `orderId`;
  `BrokerOrder ord_e29c7a0e6b41` carrying `automationId`, `automationVersion`,
  `mandateId`, `runId` and the same ticket. Fixes found by doing it:
  (1) a state-only `PATCH` no longer bumps the bot version, so activating a
  prepared bot stops invalidating its mandate (`BOT_VERSION_STALE`);
  (2) `requiredPhrase` is built from the connection LABEL, matching what
  `prepare` compares; (3) a bare FX pair (`EURUSD`) classifies as FX→`EURUSD=X`
  in the Python classifier and the Next price-history route, so the app can
  backtest/chart the symbol its broker quotes; (4) a broker symbol signals on the
  broker's own `copy_rates` bars (gateway fallback), (5) the still-forming bar is
  dropped so the signal is on the last CLOSED bar, (6) a refusal that sent
  nothing releases the bar claim (`LiveRunner.release`) while a send never does,
  and (7) every broker connection gets a stable non-zero ownership `magic`
  (`_default_magic`) so the kill switch can match Eclipse orders. Tests: 191
  targeted Python (incl. the L3 E2E), 11 size/phase (service.py pin 1205→1214),
  `tsc` clean. Docs: `docs/trading-bot-live-testing-plan.md`,
  `docs/trading-bots-plan.md`, `docs/harness/market-data.md`, `docs/CHANGELOG.md`.
  L5 (supervised live) and L6 (soak) remain operator-run.

- **docs(legal): write down the monetization position.** Added
  `docs/monetization.md`: MIT core, revenue from additive surfaces (pro features,
  marketplace, live data, support), with the rejected models (noncommercial,
  BUSL, whole-app AGPL, phone-home paywall) and why each was refused. Added to
  `docs/NAVIGATION.md` so future sessions find the policy before proposing a
  licence change. Also normalized two tracked docs whose working-tree CRLF/LF mix
  turned `gitignore-guard` red (`docs/DECISIONS.md`, `skills/ARCHITECT.md`) —
  index was already LF, so this is a no-op diff.
  Doc change: `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **chore(updates): publish the first signed manifest and ship the listener
  shell.** `config/updates.json` now points at the real public repository
  (`desimarijuana/BlackEclipse-V1.0`) with `published: true`; the v0.4.0
  `stable.json` was signed offline with the committed key's counterpart and
  attached to the existing release, so a live check verifies and reports *up to
  date*. The installed shell was rebuilt with the `be-update` listener and
  swapped in (previous exe kept as `.bak-20261117`), so *Restart Eclipse* is now
  seamless instead of "quit and reopen". Doc change: `docs/UPDATES.md`,
  `docs/CHANGELOG.md`.

- **feat(updates): in-app update button in the window chrome.** A download icon
  now sits left of Minimize, dot-lit when a newer signed release exists. Panel
  shows the honest check result and can **stage** the release in-app
  (`be-update` event → the shell spawns `scripts/update-apply.js`, with
  `POST /api/updates/apply` as the fallback for shells without that listener;
  the runner executes the verified `update.js --yes --no-desktop`: signature, DB
  backup, checkout, `npm ci`, build) and then **restart** onto it. Promotion runs
  with `--no-restart` while
  the window keeps its current build (atomic pointer, previous release kept); the
  restart itself is a Tauri `be-update` event handled in `main.rs`, which spawns
  `desktop-refresh --no-build` outside the server tree that the same script
  `taskkill /T`s. Reopening the app is the equivalent fallback for shells that
  predate the listener. Progress travels through
  `.runtime/update-job.json`; a heartbeat-less `running` job reads as failed.
  The banner now shares `useUpdateStatus` with the button, so both surfaces agree
  and two consumers cost one cached upstream check. No new network path, no
  auto-apply, no unsigned code. Doc change: `docs/UPDATES.md`,
  `docs/CHANGELOG.md`.

- **chore(legal): adopt a CLA and publish a trademark notice.** Added root
  `CLA.md` (plain-English, signed by one PR comment; grants relicensing and a
  patent licence while the contributor keeps copyright) and root `TRADEMARK.md`
  ("code is MIT, the name and logo are not"), wired into both `CONTRIBUTING.md`
  files, the PR template, the README licensing table, the legal register, and
  `scripts/oss-preflight.js` as required files. The blueprint's §1.4
  "DCO, not a CLA" recommendation is superseded: the strategy is MIT + adoption,
  monetising extras (pro features, marketplace, live data) instead of the
  licence, and the CLA is cheap only while the repo is single-author. Trademark
  placeholders in `docs/legal/TRADEMARK-POLICY.md` resolved to Rafay Ghauri /
  BlackEclipse; the full policy stays Draft pending counsel.
  Doc change: `docs/legal/README.md`, `docs/legal/LEGAL-COMPLIANCE-BLUEPRINT.md`,
  `docs/legal/TRADEMARK-POLICY.md`, `docs/OPEN-SOURCE-READINESS.md`,
  `docs/CHANGELOG.md`.

- **chore(size): re-pin for the alternative-intelligence signal engine.** The new
  `python/harness/intel/` package (engine, sec, attention, service, contracts)
  moved the harness to 520,773 lines and the `python/harness/.` seam to 40,239.
  Re-pinned from a clean clone of the release tree, as the ratchet requires;
  verified `Size budget passed` there. Doc change: `docs/CHANGELOG.md`.


- **fix(ci): the last four Windows-suite causes.** (1) `scikit-learn` was never
  declared, so `lightgbm.sklearn` failed with "scikit-learn is required" - now in
  `requirements.txt` and locked (1.9.1). (2) The `python` job had no
  `node_modules`, so the capability-matrix check fell back to `npx`, which is not
  a runnable executable name on Windows; it now runs `npm ci --ignore-scripts`.
  (3) That job also had no git identity, which the worktree/commit tests need.
  (4) `test_analysis_guard.py` and `test_capability_classes.py` exercise the
  vendored analysis interpreter and now skip with the provisioning hint when it
  is absent, like the other sandbox suites. SBOM regenerated: 1,333 components.
  Doc change: `docs/CHANGELOG.md`.


- **chore(registry): regenerate the published tool manifest.** `npm run eval:registry`
  after adding the six `intel_*` tools — `docs/harness/tool-registry.json` now
  lists 1,106 tools (digest `03177dd0162122b4`), which is what
  `test_public_api.py::test_the_published_manifest_matches_a_fresh_generation`
  asserts. no doc change — generated artefact, and the neighbouring intel entry
  above records the change itself.

- **fix(ci): the trading-bot commit left three gates red.** `bot-model-picker.tsx`
  rendered `app's` in JSX text, which `react/no-unescaped-entities` rejects (the
  only real lint error in the new feature); `eslint .` also walked `dist/`, the
  installer payload assembled by `npm run desktop:package`, and reported 21k
  errors inside vendored plotly bundles, so `dist/**` is now ignored; and the size
  ratchet moves to the measurement taken on a clean clone of the release tree
  (total 518,087, `.` 40,215, quant 26,984, routers 24,040). Verified: `eslint .`
  0 errors / 119 warnings, and the size budget passes on a clean clone of HEAD.
  Doc change: `docs/CHANGELOG.md`.


- **feat(trading): live is a choice, and the full order chain is tested.** The
  operator's explicit LIVE authorization now grants L2 in the same action
  (`_grant_live_tier` on the server; the UI no longer disables Live or requires a
  prior track record), while the real gates stay: typed phrase, armed connection,
  bot-pinned mandate and the submit fence. Refusals from the trial now keep their
  code (`LIVE_NOT_ARMED`, `RISK_REFUSED`, `BAR_ALREADY_PROCESSED`,
  `POSITION_ALREADY_OPEN`, broker codes) instead of being mislabelled as
  “position already open”. Added the missing **full-chain test**
  (`python/tests/test_trading_bot_e2e.py`): a demo bot places exactly one order
  through the real runner → trial → `BrokerService` (ledger row + position +
  `automationId`), the same bar cannot place a second, and a disarmed live bot is
  refused before the adapter. The size pin for in-flight `service.py` moved
  2089→2098 (shared-tree intel work; no trading code there). Tests: 120 targeted
  Python (including 3 E2E), 5015 TS, `tsc` clean. Docs:
  `docs/trading-bot-live-testing-plan.md`, `docs/trading-bots-plan.md`,
  `docs/CHANGELOG.md`.

- **feat(intel): alternative-intelligence signal engine (free, keyless, deterministic).**
  New `python/harness/intel/` lane answering "what did a public record measure
  that the price may not have absorbed yet". Four signals over two no-auth
  sources: `insider_conviction` (EDGAR Form 4 open-market purchases, with grants,
  option exercises, tax withholding and every Rule 10b5-1/planned sale excluded
  so the number means discretionary conviction), `activist_stake` (Schedule 13D),
  `filing_heat` (8-K/4 pace vs the company's own baseline) and
  `attention_velocity` (Wikimedia daily pageviews, redirect-resolved, robust
  median/MAD z). Pure parsers + injected fetch, so the pipeline is fully
  fixture-testable. Scoring is deterministic: gated per signal, weights
  renormalised over what fired, direction only from directional signals, and
  conviction = corroboration (one loud signal stays `low`). Six read-only tools
  (`intel_scan|entity|series|cards|watch|catalog`) registered on the SAME
  registry and advertised on `ECLIPSE_AGENT`, so a scheduled bot inherits them
  with no parity work. Observations, watchlist and immutable card snapshots
  persist on the ONE `agent-memory.db`. Unmeasurable signals report
  `UNAVAILABLE` with a reason and are never zero. Live-verified against EDGAR
  and Wikipedia (AAPL/NVDA/MRNA). Deliberately no paid imagery: 10 m Sentinel-2
  cannot count cars or resolve tank fill, so the shadow/occupancy lane is left
  for a future licensed-imagery collector behind the same contract.
  Docs: `docs/harness/intel-signals.md` (new), `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`. Tests: `python/tests/test_intel_{sec,attention,engine,service}.py`.

- **docs(plan): trading bots — real execution and the test ladder.** Added
  `docs/trading-bot-live-testing-plan.md`: (a) demo must be an operator choice,
  not a cage — Live is selectable and the live authorization grants L2 in one
  action while keeping the typed phrase, armed connection, bot-pinned mandate
  and the submit fence; (b) how to prove a bot places a trade, layer by layer:
  L0 pure, L1 runner/fake broker, L2 the real MT5 adapter against
  `python/tests/mt5_sim.py`, L3 a full in-process chain (automation engine +
  strategy + broker + simulator), L4 a real MT5 demo smoke, L5 a supervised
  min-size live smoke, L6 a 48–72 h soak. Includes acceptance criteria and the
  honest limits (no 24/7 service, no profitability claim).

- **fix(ci): the last environment gaps in the Windows suite.** Four more causes,
  none a product change. (1) `lightgbm` was never declared, so the two ML
  acceptance tests failed honestly with "requires an optional dependency" - it is
  now in `requirements.txt` and locked (4.7.0). (2) `docs/harness/benchmarks.md`
  is generated and had drifted; regenerated with `npm run eval:benchmarks`. (3)
  `test_code_check_path.py` and `test_kits_scaffold.py` need the vendored
  interpreter, so they skip at module level with the provisioning hint - the same
  guard the sandbox suites already use. (4) The size budget is re-pinned by 49
  lines for the SQLite serialisation fix. SBOM regenerated: 1,329 components.
  Doc change: `docs/CHANGELOG.md`.


- **feat(autonomy): goal verdicts stream into the chat transcript; a slow
  `price_history` serves its last good read.** Each new verdict from a session's
  open goals is appended as a transcript line (`useGoalVerdictWatch`, 5s poll,
  idempotent by `goalId:turn`, first poll primes so reopening a chat never
  replays history). `HttpDataBridge` keeps the last successful `price_history`
  response (bounded 32) and returns it as `STALE`/`cached` when the live route
  times out, instead of UNAVAILABLE; a different query never borrows another
  series. Tests: bridge cache fallback, goal transcript wiring, loop controls.
  Docs: `docs/harness/autonomy.md`.

- **feat(bots): authorization gate, tier ladder, venue memory, library sort.**
  **Gate:** `authorizeBlockReason` (pure, used by both the create panel and the
  bot's Trading section) blocks Authorize when the selected broker is
  `unavailable` — showing the terminal reason — when live is below L2, or when a
  live connection is not armed; the button is disabled and the sentence is the
  same in both surfaces. **Ladder:** an explicit L0/L1/L2 panel shows the current
  tier, one-click **Enable L1** (demo), and **Request L2** only after the
  measurable gates (`l2Eligibility`: 50 decisions, 14 days, backtest/approval when
  known) plus an explicit acknowledgement; the journal P&L/win-rate review is
  stated as a warning, never faked. **Venue memory:** the last demo/live venue is
  remembered in `localStorage` and preselected only when the bot has none, still
  exists in that mode, and never overrides an explicit choice. **Sort:** the
  strategy library sorts by newest or name A→Z. Tests: 16 new TS cases (authorize
  gate, venue memory, L2 eligibility, catalog sort); full suite 5015 pass,
  `tsc --noEmit` clean, 33 targeted pytest pass. Release
  `8DTXGoP3SAiSwhsFZXuUc` promoted and relaunched. Docs:
  `docs/bot-mode.md`, `docs/CHANGELOG.md`.

- **feat(autonomy): `/loop status|pause|resume|cancel`, and artifact-write
  resilience.** A loop could only be started from chat; control now lives in the
  same command (`/loop status`, `/loop pause|resume|cancel [id]`, defaulting to
  the active loop), matching the GoalBar. `LocalArtifactStorage.import_file` /
  `_atomic_write` retry once when the store path disappears between the temp
  write and `os.replace` (the live `WinError 3` seen during artifact discovery),
  and `analysis_run.purpose` accepts up to 1000 characters so a long purpose no
  longer costs a failed sandbox call. Tests: loop status/cancel handler, artifact
  retry. Docs: `docs/harness/autonomy.md`.

- **fix(harness): serialise every code-index statement — a read raced a write
  and crashed the process.** `CodeIndex` opens SQLite with
  `check_same_thread=False` and only guarded *writes* with its lock. The docs
  require the caller to serialise access regardless, so a background indexer
  thread computing a file signature while another thread read the same connection
  died inside libsqlite3 instead of raising: the Windows CI run ended with
  `Windows fatal exception: access violation` in
  `intel/persistence/index.py::file_signature`. The connection is now wrapped in
  a proxy that takes the store's re-entrant lock for every call (reads, writes,
  transactions, `close`, and any call added later), with `__setattr__` forwarded
  so `row_factory` still lands on the connection. 65 code-index tests pass,
  including `test_intel_index_concurrency.py`. Doc change: `docs/CHANGELOG.md`.


- **feat(bots): the strategy catalog and the settings fixes.** One shared
  catalog (`src/lib/strategies/catalog.ts`) now backs both surfaces, with the
  newest backtest/approval/paper run per strategy from a single call
  (`GET /quant/strategies?includeEvidence=true`). **Strategy Studio** shows
  evidence badges, a Refresh control, an archived toggle, and stays fresh on
  focus/visibility and after any agent turn (`useAgentRun` invalidates it) — so
  a strategy the Eclipse agent just made appears without a reload. **New bot**
  replaces its 46-option `<select>` with a searchable `StrategyPicker` (evidence,
  archived toggle, Refresh, “Open in Strategy Studio” through a typed in-app
  navigation intent, no browser reload). Settings fixes: the agent preset and
  model are visible without opening Advanced, the model picker has
  loading/“runtime starting”/error+Retry/“no provider” states, broker venues show
  `unavailable` with the terminal reason and a Refresh, a mode with no connection
  explains itself, the Create button explains what is missing
  (name/objective/workflow) instead of silently disabling, and the bot detail can
  now change its **workflow** (with an Open Graph Studio link), **agent preset**,
  **model**, and pinned **strategy** (re-prepared under the standing consent).
  Tests: 3 Python catalog cases, 11 new TS cases (catalog store, navigation
  intents, evidence badges); full TS suite 4996 pass, `tsc --noEmit` clean.
  Docs: `docs/bot-mode.md`, `docs/strategy-studio.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.

- **fix(autonomy): a goal turn can bind the finance tools and compute.**
  Live finance goals could only describe a backtest: the run query contains the
  rule words **“entry”/“exit”** and the acceptance word **“all”**, and
  `trading_intent` read “exit … all” as *“close all positions”*. That narrowed the
  run to the 18-tool **trade** surface, so `get_historical_prices` and
  `analysis_run` were not bound and the goal correctly blocked. The classifier now
  recognizes a backtest/simulation as research (word-bounded nouns, analysis
  markers before the close/trade heuristics), and `apply_intent_surfaces` skips the
  trade surface entirely for task runs so a quoted previous verdict cannot
  re-classify the run. Task runs also set `context.taskRun`
  so they keep the agent's own surface instead of the chat-code profile, and
  `RunRequest.analysisEnabled=True` so the sandbox is available. The goal brief
  for `finance`/`data` names the data + compute route. Tests: the backtest query is
  not a close request, the task surface keeps the agent's tools, `analysisEnabled`
  reaches the run. Docs: `docs/harness/autonomy.md`.

- **fix(code): `search_text` crashed on every scan with `AttributeError`.**
  `harness/code/fs/search.py` read the size cap from `metadata.MAX_TEXT_BYTES`,
  but the constant moved to `encoding.py` and `metadata` never re-exported it, so
  the size check raised before a single file was searched (7 `search_text` tests
  plus the workspace-search tool tests). It now imports `encoding` and uses
  `enc.MAX_TEXT_BYTES`, and the function-local duplicate import is gone.
  Doc change: `docs/CHANGELOG.md`.

- **fix(ci): run the Python suite on Windows, where it is actually green.**
  Making CI run for the first time exposed 100 Linux-only failures across 32
  files - MCP fixtures that spawn the interpreter, PowerShell-backed terminal
  sessions, kit scaffolding, git-hook assertions. They are a real platform
  backlog, but running that suite on ubuntu reported environment differences as
  product failures. The `python` job now runs on `windows-latest` (the platform
  the suite is written for) and is a **required** status check alongside the
  Linux job, so it cannot silently rot. The Linux backlog is named here on
  purpose: triage it before claiming Linux test parity. Doc change:
  `docs/CHANGELOG.md`.

- **feat(trading): one-click EUR/USD 1-minute bot.** The Bots empty state now
  seeds a complete 1m vertical (`src/lib/bots/trading/eur-1m.ts` +
  `eur-1m-seed.ts`): strategy `eurusd_m1_ema_rsi` (EMA 9/21 cross, RSI veto, ATR
  1.5 stop, 1.5R target, spread/slippage modelled on 1m bars), a **90-day 1m
  backtest** as evidence, a shadow-only approval, a 60-second automation
  (`misfire: skip`, one position, 4 orders/day, 5-minute cooldown, London hours,
  L1 leash) and a **shadow** trial, then activation. Idempotent by bot name;
  every gate failure names the gate. The Trading panel gained a one-time
  **Authorize demo/live** form: the seeded shadow bot becomes a trading bot with
  the phrase typed once (standing consent), and live stays gated by L2 + an
  armed connection. Tests: 15 TS starter/seed cases, 6 Python engine cases
  (real parser + signals on synthetic 1m bars + the real automation validator +
  the real shadow-trial creation), 2 runner M1 freshness cases. `tsc --noEmit`
  clean. Docs: `docs/bot-mode.md`, `docs/trading-bots-plan.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **fix(deps): declare `yfinance` so CI installs the runtime the app installs.**
  `scripts/setup-python.js` pip-installed yfinance as an extra, so the lock never
  contained it: CI installed the lock, had no yfinance, and every market-data
  test died with `ModuleNotFoundError: No module named 'yfinance'` (including a
  collection error in `test_yfinance_bridge_window.py`). It is now declared in
  `python/requirements.txt` and locked (1.8.0), so the lock is the single source
  of truth for the runtime. SBOM regenerated: 1,327 components.
  Doc change: `docs/CHANGELOG.md`.


- **fix(autonomy): judge schema tolerance, re-judge recovery, and a multi-goal
  strip.** Two live goals (document, finance) completed their runs but `blocked`
  because the judge answered `status: completed` / `explanation: ...` instead of
  `verdict` / `reason`. The judge now normalizes near-miss JSON before validation
  (alias keys, enum synonyms, snake_case, fenced JSON, null/extra fields) while
  still validating the VALUE, and the system prompt names the exact keys.
  `POST /goals/{id}/reevaluate` + `/goal retry` re-judge the last finished turn
  without paying for a new run. The status strip now lists every active goal,
  labels `queued` vs `running` from the turn task, and offers a Re-judge action on
  blocked goals. Also normalized one stray CRLF line in
  `python/tests/test_broker_orders.py` that failed the repo-wide line-ending
  guard, and re-pinned the in-flight shared-tree size ratchets (`graph.py`,
  `main.py`, `trade/service.py`). Tests: judge alias/fenced parsing, re-judge,
  multi-goal handler. Docs: `docs/harness/autonomy.md`.

- **fix(trading): the live bot fence could not read an EMPTY position list.**
  `trade/authority.py::_eclipse_open_positions` treated `{"available": true,
  "data": []}` as unreadable (`[] or {}` is falsy), so an L2 bot with no open
  positions was refused `POSITIONS_UNAVAILABLE` on every live order. It now
  accepts the adapter-list shape (`data: [...]`) and only reports unavailable for
  a genuinely unreadable payload. **Proof at the broker seam:** three new tests in
  `python/tests/test_broker_orders.py` drive `BrokerService.submit_order` with a
  counting fake adapter and a bot-pinned live mandate — an L1 bot is refused
  before `order_preview`/`submit` are called, an L2 bot sends exactly once and
  records `automationId`/`mandateId` on the ledger (a second submit is refused
  without a new send), and a stale bot version is rejected `BOT_VERSION_STALE`.
  Also extracted the human-turn builder into `harness/turn_content.py` to keep
  `graph.py` under its size ratchet, re-pinned `main.py` 1270→1272 for the two
  router lines, and trimmed `trade/service.py` back under 1200. Two full Python
  runs: **11114 passed / 1 failed** (`test_learning_review`) and **11117 passed /
  1 failed** (`test_w4_autonomy`); each failure passes alone (15 and 30) and both
  are in-flight autonomy/learning code, not trading. Docs:
  `docs/trading.md`, `docs/trading-bots-plan.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.

- **fix(ci): the job needed more than 30 minutes, not a code change.**
  The last run was `cancelled` at exactly 30:15 with **every** step before the
  tests green - the `timeout-minutes: 30` cap was itself the failure. One vitest
  worker plus 11k+ Python tests plus the eval, quant and corpus gates takes ~45
  minutes on a runner. Raised to 90. Doc change: `docs/CHANGELOG.md`.


- **fix(tests): skip the sandbox suites when the vendored toolchain is absent.**
  Both files resolved `scripts/vendor/python` at import time, which exists in a
  packaged app and locally after `npm run setup:python` but not on a CI runner
  that only pip-installed the requirements - collection died with
  `CommandUnavailable: the tool for 'python_test' is not installed here` before a
  single test ran. They now `pytest.skip(..., allow_module_level=True)` with the
  provisioning hint, the same "expected skip" shape the suite already reports for
  opt-in lanes. 33 tests still pass locally, where the toolchain exists.
  Doc change: `docs/CHANGELOG.md`.


- **feat(trading): the four remaining gaps — real image parts, find-trades scan,
  agent live path tested, lessons in chat.** (1) **Images**: `RunInput.images`
  (bounded PNG/JPEG/WebP data URLs) becomes native `image_url` content blocks on
  the human turn, both on a bot chat (`ChatOptions.images` → payload → both chat
  routes) and on a scheduled agent run (the dispatcher forwards the bot's
  visuals); a text block still marks them as guidance, never market data.
  (2) **Find trades**: `POST /automations/{id}/trading/scan` evaluates the
  strategy on the last closed bar and returns actionable symbols; the trading
  panel can adopt them and re-prepares under the standing consent. The runner's
  ranking moved to the pure `trading_policy.rank_evaluations` (exits first, no
  re-entry of a held symbol). (3) **Agent live path**: new tests prove an agent
  `prepare` creates a bot-pinned mandate + standing consent, requires the phrase
  unless a grant covers it, and that the live fence refuses L1 / a missing stop
  while accepting L2. (4) **Learning in chat**: a trading bot's turn carries a
  ledger-derived lesson digest as a system message, so it can discuss repeated
  failures and its proposed fix; applying still needs the operator. Tests: 51
  new Python cases (policy, runner, validation, visuals, agent prepare, scan)
  and 3 new TS bot-turn cases; `tsc --noEmit` clean. Docs:
  `docs/bot-mode.md`, `docs/trading.md`, `docs/trading-bots-plan.md`.

- **fix(ci): run the pipeline on Node 22, the version the app actually ships.**
  This was the real cause of the two "worker exited unexpectedly" crashes: the
  only two test files that open a database load `better-sqlite3@13`, which
  requires Node >= 22 (`npm warn EBADENGINE ... better-sqlite3@13.0.3`), while CI
  pinned Node 20 - so the binding could never load and killed the worker instead
  of failing an assertion. Five workflows move to Node 22 (matching the vendored
  runtime and `desktop-release.yml`) and `package.json` now declares
  `engines.node >= 22` instead of claiming 20. Doc change: `docs/CHANGELOG.md`.


- **fix(autonomy): `/goal` turns actually run (and a finance goal is not typed
  as code).** The live DB showed every goal turn stranded: `start_turn` called
  `start_task`, which moves a task to `IN_PROGRESS` without a claim token or
  lease, and the scheduler only claims `TODO` — so the goal sat `active` with a
  turn that never ran (no execution row, no run). Goal turns now stay `TODO` for
  the scheduler's atomic claim, and `start_tasks` repairs rows the old path left
  behind (`repair_orphaned_goal_tasks`, scoped to `metadata.goalId`). Separately,
  the classifier treated any mention of "app" as code ("data available in this
  app"), so a backtest/research goal was verified as a code task a `plan_only`
  run can never satisfy; inference now requires a code *action* before a code
  noun, and `/goal --type finance|research|code|...` pins the verifier
  explicitly. `/api/harness/command` also accepts a `chatId`, so the explicit
  command entry point can run session-scoped goals. A goal plan that auto-completed
  when its turn finished is also **reopened** for the next turn (`resume_plan_for_work`,
  plus a boot repair), because the scheduler only runs tasks in a RUNNING plan —
  otherwise the loop stalled after turn 1. Tests: stranded-turn, boot-repair,
  plan-reopen, explicit-type, finance-vs-app classification. Docs:
  `docs/harness/autonomy.md`.

- **fix(ci): build the `better-sqlite3` binding that `--ignore-scripts` skipped.**
  The last runner failure was not memory at all: the same two files never
  reported, and both are the only tests that actually open a database
  (`src/lib/auth/*.test.ts` -> `new AuthStore(":memory:")`). `npm ci
  --ignore-scripts` also skips better-sqlite3's install step, so the native
  binding is absent and the worker process dies instead of failing an assertion.
  CI now runs `npm rebuild better-sqlite3` right after the install. The previous
  attempt's single worker and lower heap stay - they are still the right shape for
  a 527-file suite on a 4-vCPU runner. Doc change: `docs/CHANGELOG.md`.


- **fix(ci): one vitest worker, a lower heap ceiling, and npm retries.** Two more
  runner failures, neither a failing assertion. (1) `Worker exited unexpectedly`
  killed the run twice even with two forks: 527 files each import the agent tool
  registry, so each fork's resident memory grows with the files it hosts. CI now
  runs a single worker (`maxWorkers: 1`, local runs unaffected) and the job's heap
  ceiling drops to 4096 MB - raising it to 6144 only let a worker grow further
  before being killed. (2) `npm ci` died on `ECONNRESET` mid-fetch; `.npmrc` now
  sets retry/timeout hints (no registry or auth is configured there).
  Doc change: `docs/CHANGELOG.md`.


- **fix(ci): stop vitest workers from being killed on a 4-vCPU runner.** The
  suite reported `4832 passed | 3 skipped` and then exited 1 anyway: two worker
  forks died mid-run ("Worker exited unexpectedly") because 527 test files each
  import the agent tool registry and the default one-fork-per-core fan-out
  exhausted runner memory. `vitest.config.ts` now caps `maxWorkers` at 2 **on CI
  only** (local runs keep the default), and the job gets
  `NODE_OPTIONS=--max-old-space-size=6144` - the same headroom the desktop
  release build already needed. Doc change: `docs/CHANGELOG.md`.


- **feat(trading): strategy bots with standing consent, live execution and
  failure learning.** A bot can now use a saved quant strategy version as its
  brain (`action.type = "run_strategy"`). One execution = one decision on the
  last closed bar: the runner checks standing consent, the session window, data
  freshness and the symbol universe, then calls the existing
  `LiveStrategyService.run_once` → `BrokerService.submit_order` path. Every run
  persists a structured decision (no-signal and refusals included) on the
  execution, so "why didn't it trade?" is answerable in Run History and in the
  new Trading section. **Auto mode:** the operator types the consent phrase once;
  `action.config.consent` is a bounded standing grant and `prepare` renews the
  mandate without asking while it still covers the request. Widening a limit,
  expiry or revocation asks again. **Live:** `check_live_order` now runs inside
  `submit_order` whenever `automation_id` is present, so no caller can skip the
  L0/L1/L2 ladder; demo mandates may pin an L1 bot (the code was stricter than
  `docs/trading.md`), live still needs L2 + arm + a bot-pinned mandate.
  **Learning:** repeated failures become one concrete proposal with a chat-ready
  explanation; applying it patches config/authority and re-prepares under the
  consent, and the bot can only tighten by itself. **Visual teaching:** up to
  four bounded images with captions, injected as pattern guidance that can never
  be cited as market data. Pause/disable/archive/delete revoke mandates and stop
  the trial; positions are never auto-closed. An **agent** bot can be granted a
  bot-pinned demo/live mandate (no trial) plus the same standing consent, so it
  can propose at L0 and fill at L1/L2 with its own tools. Tests: 106 TS domain
  tests (plus 2 persona cases), 37 plain-Python policy checks, 33 new pytest
  cases (policy, runner, validation); full suite 4965 TS tests + 138 touched
  Python tests green; `tsc --noEmit` clean. Docs:
  `docs/trading-bots-plan.md`, `docs/bot-mode.md`, `docs/trading.md`,
  `docs/NAVIGATION.md`, ADR-080 in `docs/DECISIONS.md` + `skills/ARCHITECT.md`.

- **feat(autonomy): the goal loop is ON by default.** `/goal` is user-initiated,
  so requiring an env edit before it can work was friction, not safety:
  `HARNESS_GOAL_LOOP` now defaults to `on` (`shadow` and `off` remain explicit
  choices). The global `HARNESS_AUTONOMY=off` kill switch still vetoes the engine,
  and an explicit `off` still makes `POST /goals` refuse with
  `GOAL_ENGINE_OFF`. Updated the flag test, `.env.example`, and the autonomy
  flag table.

- **fix(ci): the wheel guard no longer rejects source modules named `seed`.**
  `publish-harness.yml` failed every `v*` tag at "The package must carry no
  data": it treated any filename containing `seed` as a data leak, which matches
  `harness/a2a/agents_seed.py` - a source module. The check now tests data
  suffixes (`.db`, `.sqlite`, `.parquet`, `.csv`, `.xlsx`), `jdds`, `.env`, and
  `seed` only when it is NOT attached to a source/document file, so a real seeded
  database still fails the release. Doc change: `docs/CHANGELOG.md`.


- **chore(release): regenerate the SBOM after the `av` re-lock.** `check:oss` and
  the CI "SBOM drift check" both gate on `sbom.cdx.json` matching the lockfiles,
  so the av 14.4.0 -> 13.1.0 change failed both. Regenerated with `npm run sbom`
  (1,320 components); `node scripts/generate-sbom.js --check` is clean again.
  Doc change: `docs/CHANGELOG.md`.


- **fix(deps): pin `av` to a range that ships wheels.** PyAV 14.4.0 publishes
  an sdist only, so every `pip install -r python/requirements.lock` tried to
  compile it - and failed on Linux even with the FFmpeg headers installed. The
  stack now needs no C toolchain: `av>=12,<14` resolves to 13.1.0, which has
  cp312 wheels for manylinux, macOS and Windows. Re-locked; the only change in
  `requirements.lock` is av 14.4.0 -> 13.1.0. Doc change: `docs/CHANGELOG.md`.

- **chore(eval): regenerate the published benchmarks.** The guard
  (`test_published_benchmarks`) caught `docs/harness/benchmarks.md` stale against
  the current deterministic runtime: task_success 0.9940→0.9970, adversarial
  14/14 (100%), latency 0.1384→0.1124. Generated with `npm run eval:benchmarks`;
  no hand-editing, and the guard was green on re-run. Doc change: the generated
  file itself.

- **fix(ci): the pipeline could not install the Python stack on Linux.** `av`
  (PyAV 14.4.0) publishes an sdist only - no wheels on any platform - so
  `pip install -r python/requirements.lock` builds it and needs the FFmpeg
  development headers; the job died at `pkg-config could not find libraries
  [avformat, avcodec, ...]` before running a single test. That only became
  visible once the repository went public and Actions could finally start. CI
  now installs `pkg-config`, `ffmpeg` and the `libav*-dev` packages first.

- **chore(repo): remove the GitHub Actions deploy lane.** `.github/workflows/deploy.yml`
  pushed on every commit to `main` and could only fail: this is a desktop-only
  product, every `DEPLOY_*` secret is absent, and it was the TOFU
  `StrictHostKeyChecking=accept-new` SSH path flagged as H-08 in the audit. It
  fired a red X on the first public push. Self-hosting is still manual
  (`scripts/deploy.sh` + the systemd timer); `docs/DEPLOYMENT.md` records why
  the workflow is gone. Docs updated: `docs/DEPLOYMENT.md`, `docs/CHANGELOG.md`.

- **feat(autonomy): `/goal` is now a real, verified loop.** The command existed
  but could not be trusted: it sent no `sessionId` (so a goal was invisible to
  its own session and "the user always wins" could not see it), goal turns ran
  with no `workspaceId` (so the agent edited nothing while the gates checked the
  goal's workspace), and with `HARNESS_GOAL_LOOP=off` it created a zombie goal
  that was never evaluated. All three are fixed: the handler binds the session
  and resolves the session's newest live workspace, the task executor forwards
  `workspaceId` to `RunRequest`, and `POST /goals` returns 409
  `GOAL_ENGINE_OFF` instead of creating a goal the engine will not evaluate.
  A judge `done` must now pass `verify_task` and the task completes before the
  goal does; a failed run skips gates + judge; the no-progress digest excludes
  the judge's wording; cancel targets the live run (`currentRunId`, migration
  `2026-11-17-007-goal-live-turn`); a refused task start no longer burns a turn;
  the turn cap is an honest `blocked` with `/goal extend <turns>` as the bounded
  way out; one active goal per session is enforced. `/goal` also gains
  `show <id>`, bounded `extend`, repeatable `--gate` (the parser kept only the
  last one), `--gate unit_test=path` scoping, workspace autodetect, `--autonomy`,
  and an actionable off-engine message. The status strip is i18n'd, polls at 5s
  while active, exposes `extend`, shows the live run and an expandable
  per-gate/per-verdict detail panel, and shows an off-engine chip;
  `/api/autonomy/health` backs it. Docs: `docs/harness/autonomy.md`.

- **chore(size): re-pin for the evaluation-harness fix (+11 lines).** The
  `ScriptedModel` fallback added 11 lines to `python/harness/evaluation`, putting
  both the total (515,473 vs 515,462) and that module's ratchet (13,060 vs
  13,049) over. Re-pinned to the measured values; the next line over fails.
  Doc change: `docs/CHANGELOG.md`.

- **docs(plan): trading bots.** Added `docs/trading-bots-plan.md` — how a bot
  becomes a trading agent: a saved strategy version (or agent brain) bound to an
  Automation, executed through the existing quant signal + broker path under the
  existing L0/L1/L2 authority ladder and mandates. Records the reuse map (most
  of the substrate already ships), eight decisions, phases P0–P5, a test matrix
  and open questions. No code changed. `docs/NAVIGATION.md` gained a trigger row
  pointing at it.
- **docs(plan): trading bots — implementation spec.** Expanded
  `docs/trading-bots-plan.md` from an overview into an implementation plan:
  locked contracts (action config, `ExecutionAuthority` matrix, decision record,
  endpoints, refusal codes), backend work packages WP1–WP8 with file-level
  changes and pseudo-code, frontend WP9–WP13, create/run/promote/pause
  sequences, phases P0–P5 with exit criteria, a named test matrix, compatibility
  notes and risks. Two design corrections landed in the plan: **shadow mode needs
  no broker** (signal on JDdS + order preview), and **demo mandates may pin an L1
  bot** — the code currently demands L2 for any bot pin, which is stricter than
  `docs/trading.md` says. No code changed.

- **fix(ui): a malformed `/api/setup` reply no longer white-screens the app.**
  `OnboardingGate` renders the full-screen wizard unless `state.completed` is
  truthy, and `OnboardingShell` builds its draft from `state.sources.map(...)`.
  A reply that is not a setup state (any other JSON body) therefore crashed the
  whole shell with "Cannot read properties of undefined (reading 'map')" instead
  of being ignored. The gate now treats a reply without a `sources` array as a
  failed state read, which its own contract already says must never block the
  app. `drift-app-smoke.mjs` also mocks `/api/setup` so the wizard cannot cover
  the Skills screen it is testing - the smoke had been failing on exactly this
  crash. Both drift smokes: PASS. Doc change: `docs/CHANGELOG.md`.

- **fix(eval): a scripted agent repeats its answer instead of scoring a
  placeholder.** The answer guard (added 2026-11-16) asks for another turn when
  a reply looks like a bare refusal after a blocked tool route. A scripted
  evaluation agent cannot improvise, so `ScriptedModel` ran out of script and
  returned `(evaluation script exhausted)` - which is what the `exact` grader
  then scored. `adversarial.unavailable.001` (the task asserting an unavailable
  quote service stays unavailable) regressed from passing to failing that way,
  and the committed-corpus gate correctly flagged it: task_success 0.9958 →
  0.9919. The scripted model now repeats its final answer on exhaustion, so the
  guard's extra turn lands on the same honest reply. Corpus gate: PASS, no
  regressions; 62 evaluation tests pass. Doc change: `docs/CHANGELOG.md`.

- **fix(ci): three gates that could not pass on a working machine.** (1)
  `npx eslint .` walked `.next-desktop/`, `.next-desktop-dev/` and `releases/` -
  all gitignored build output - reporting 152,862 errors inside vendored
  Next.js and plotly files to anyone who had run the desktop app; those paths are
  now ignored, leaving six genuine source errors. (2)
  `docs:data-sources:check` compared the `last-verified` stamp, which the
  generator sets to *today*, so it failed on any day the page was not
  regenerated; the date is normalised on both sides and real drift still fails.
  (3) The six source errors are fixed: a `useCallback` named `useMethod` renamed
  `applyMethod` (the hooks rule cannot tell it from a hook), an `interface
  extends` with no members (now a type alias), two non-null assertions on
  optional chains, and one justified `require()` in a test that loads a shared
  CommonJS script by absolute path. Docs updated: `docs/CHANGELOG.md`,
  `docs/data-sources.md`.

- **security(release): the installer no longer carries the build machine's
  runtime state.** `scripts/desktop-package.js` copies whole source trees
  (`python/`, `config/`, `skills/`) with `fs.cpSync`, so a release built from a
  used checkout shipped `python/.black-eclipse/channels/secret.key` (the channel
  encryption key — every install would share one), `python/csess_*/trajectory.json`
  (the author's own agent sessions), Python caches and any stray vault. A new
  `scripts/lib/scrub-app-state.js` strips those paths right after the copy and
  `assertNoLocalState()` fails the build if any survive; `seed/jdds.db` (schema +
  demo journal, generated fresh) is the only database allowed in the payload.
  Onboarding was re-verified end-to-end on a throwaway `BE_DATA_DIR`: schema-only
  and demo-seeded databases both read `isNew: true` with no `onboarding_v1` row,
  so a new user lands on the setup wizard. Docs updated:
  `docs/data-and-privacy.md`, `docs/CHANGELOG.md`.

## 2026-11-16
- **fix(readme): space the three download buttons apart.** Four `&nbsp;` between the
  links (≈24px total with the SVGs' own 8px edge gap) so the row reads as three
  buttons rather than one segmented control. Row measures 748px, still one line
  inside GitHub's ~880px column. Markdown gaps had been a single space (~4px).
  docs updated: `docs/CHANGELOG.md` (no doc change needed beyond the log — spacing
  only).
- **fix(readme): download glyph back on the left, hairline border on the dark
  buttons.** Final button pass: the download glyph (arrow into a tray) sits left of
  the label again, the secondaries keep a **1px** `#2b2f33` border so they hold an
  edge on a dark page, and the row measures 249 + 220 + 231 = 716px so all three stay
  on one line well inside GitHub's column. Widths are now **measured with
  `sharp().trim()`** rather than estimated — the previous two attempts clipped the
  label and collided the chevron, and the generator also caught a `<rect>` emitted
  without a `height`, which rendered the primary button as dark-on-dark. docs
  updated: `docs/public-readme.md` (measured-width rule, border rule),
  `docs/CHANGELOG.md`.
- **fix(readme): cleaner download buttons.** Full labels ("Download for Windows"),
  a chevron instead of the download-tray glyph, **no border** (fill only) and no
  sublabel — `141 MB · x64 · no admin` and the architecture notes are gone from the
  button and left in the Install table where they belong. Secondary buttons stay
  visible on a dark page through their fill (`#16181a`), not a hairline. Widths
  recut to 300 + 272 + 272 (860px) so the row still fits GitHub's column without
  wrapping, and the first attempt at 260px was rejected on render because the label
  clipped in the fallback font. The note under the row is now one honest line:
  unsigned, verify the SHA-256, Linux/macOS not notarised, all releases. docs
  updated: `docs/public-readme.md` (button contract), `docs/CHANGELOG.md`.
- **docs(readme): merge the tagline into one sentence.** Heading is now
  **"The open-source financial agentic harness that grows with you"** with the four
  verbs underneath, instead of a category line plus a separate growth line. One
  sentence, so the category still arrives before the promise, and "grows with you"
  keeps the category as its subject ("harness") rather than becoming a bare agent
  tagline. Social card regenerated: three lines, "grows with you" in the accent,
  verbs in the mono strip. docs updated: `docs/public-readme.md` (rule 6),
  `docs/CHANGELOG.md`.
- **docs(readme): the harness now says it grows with you - backed, not borrowed.**
  Heading moved from "The Open-Source Financial AI Harness" / "Research. Analyze.
  Build. Automate. Trade." to **"The Open-Source Financial Agentic Harness"** /
  **"Grows with you - research, analyze, build, automate, trade."** The growth claim
  was checked before it shipped: memory accumulates context and accepts corrections
  (`eclipse_memory/`, contradiction gate recall 1.0), skills are versioned and
  evaluated, and learning candidates arrive **inert** until a review promotes them -
  so "grows" means it compounds under review, not that it rewrites itself. Hermes
  Agent's README opens with "The agent that grows with you", so the phrase is kept
  subordinate to the category line, and `docs/public-readme.md` records why it must
  never be the identity line on its own. Social card regenerated (agentic harness +
  GROWS WITH YOU + the five verbs). docs updated: `docs/public-readme.md` (rule 6 +
  evidence row), `docs/CHANGELOG.md`.

- **fix(oss): a contributor's own email address no longer blocks the gate.** The
  namespace audit treated any non-noreply author reachable from an orphaned
  `refs/pull/*` as a leak. Since a required status check runs on every pull
  request, the first outside contributor would have failed it for signing their
  own commits - an address GitHub publishes anyway. Banned paths stay blocking;
  non-noreply authors on PR refs are reported as a warning. Doc change:
  `docs/CHANGELOG.md`.

- **fix(oss): "could not check the remote" is now a warning, not a silent pass.**
  The first version of the namespace audit returned an empty list when
  `git ls-remote` failed, so a machine with no network or a missing `origin`
  reported a clean history it had never looked at - the same failure mode the
  audit exists to catch. The JSON now carries `remoteChecked`; `check:oss` warns
  when it is false, and says plainly that an empty list means "not checked".
  Ancestry probes also stop leaking git's own `fatal:` lines to stderr.
  Doc change: `docs/CHANGELOG.md`.

- **chore(size): re-pin the harness budget to the measured tree before release.**
  `npm run check:size` failed on `main` (515,462 lines against a 512,280 ceiling;
  `.` +1,404, routers +59, portfolio +7, quant +5) because work landed after the
  2026-11-12 pin. Re-pinned to the measured values with the dated note the file
  requires - the total is the binding constraint and the next line over 515,462
  fails. This is a measurement, not padding; splitting the `.` seam is the real
  fix when someone has the appetite. Doc change: `docs/CHANGELOG.md`.

- **docs(oss): the publication readme now records what actually unblocked it.**
  `docs/OPEN-SOURCE-READINESS.md` still described eleven stale remote branches
  as the blocker and treated branch deletion as sufficient. Branches were only
  half of it: GitHub's server-side `refs/pull/*` kept 11 PRs' worth of
  pre-rewrite commits, including the 38 MB `jdds.db`, reachable no matter what a
  client deleted. O1/O4 are marked resolved, §2 names the PR-ref mechanism and
  the new repository / private archive split. Docs updated:
  `docs/OPEN-SOURCE-READINESS.md`, `docs/CHANGELOG.md`.

- **chore(ci): a tag no longer turns red when `PYPI_API_TOKEN` is absent.**
  `publish-harness.yml` uploaded to PyPI on every `v*` tag, so a fresh public
  repository - which has no secrets at all - failed its release workflow with an
  empty twine password. The token is now surfaced as a job-level `PYPI_TOKEN`
  (the `secrets` context is not readable from a step `if`), the upload skips
  when it is empty, and a one-line notice step says the wheel was built but not
  uploaded. Doc change: `docs/CHANGELOG.md`.

- **chore(repo): the branch ruleset no longer locks a solo maintainer out of
  `main`.** `.github/ruleset.json` asked for one approving review with no bypass
  actor; GitHub never counts a self-approval, so the only account able to merge
  would have been a second person who does not exist. The ruleset keeps what
  actually protects the branch - no deletion, no force-push, PR required, the
  `typecheck · lint · unit · python · evals` check required in strict mode - and
  drops the approval count to 0. Raise it to 1 the day there is a second
  maintainer; `docs/` unchanged because this is repository policy, not system
  behaviour. Doc change: `docs/CHANGELOG.md`.

- **fix(test): the news identity test no longer fails when the live transport is
  blocked.** `data-bridge-identity.test.ts` exercises the real web path on
  purpose, but asserted `status === 'OK'` - so a machine that cannot reach the
  news provider failed the release gate with `UNAVAILABLE/source_failure`, which
  is an honest answer, not the false negative C2 forbids. The test now accepts
  either outcome and still requires that a failure carries a `failureClass` and
  smuggles no items. Doc change: `docs/CHANGELOG.md`.

- **fix(oss): the PR-ref audit no longer blocks on home-path placeholders.** The
  first version of the namespace probe also failed a PR ref whose history
  mentions `C:\Users\<name>\...` - which this repository's own docs legitimately
  do - so every future squash-merged PR would have been a permanent publication
  blocker. Banned paths (`*.db`, `.env*`, connector keys) and personal author
  addresses stay blocking; home paths remain a HEAD-level warning, where they
  can be judged instead of guessed. Doc change: `docs/CHANGELOG.md`.

- **chore(oss): the public-release gate now sees server-side `refs/pull/*`.** A
  history rewrite can leave `main`, the tags and every branch clean while
  GitHub still serves `refs/pull/N/head` for each closed or squash-merged PR;
  those refs reached the old 38 MB `jdds.db`, so `check:oss` reported
  "0 warnings" against a repository that would have republished it on going
  public. `scripts/prune-stale-refs.js` now lists remote `refs/pull/*`, fetches
  an orphaned PR head only when no live branch/tag accounts for it, and reports
  the banned path or personal author it still reaches (`--no-remote` skips the
  network pass; JSON gains `pullRequests`). `scripts/oss-preflight.js` consumes
  that audit as a blocker, and also fails when `.github/ruleset.json`'s required
  status check is not byte-identical to the `ci.yml` job name - the committed
  blob was correct UTF-8, but the working copy on this machine had been
  rewritten in CP1252, and applying that copy would have required a status check
  that never matches (branch protection then blocks every merge). Docs updated:
  `docs/CHANGELOG.md`.

- **fix(desktop): an orphaned channel server can no longer leave the app stuck on
  the "leftover server" Retry screen.** A window crash/force-close (or a
  promotion racing the old tree's exit) left port 3100 bound by this install's
  own `desktop-server.js`; the next launch either refused to attach or spawned
  `next start` into `EADDRINUSE`. The bootstrap now (a) compares the owner's
  build against the **promoted release** rather than only the ad-hoc pin, so a
  healthy own server attaches after every promotion, (b) reclaims the port by
  killing that owner only when the recorded pid is re-verified as a
  `desktop-server.js` bootstrap, and (c) detects a bound-but-unresponsive
  listener before spawning, so it starts fresh instead of dying with
  `EADDRINUSE`. Foreign listeners are still never killed. Docs updated:
  `docs/environments.md`, `docs/CHANGELOG.md`.

- **feat(chat): multi-select bulk actions in the sidebar chat history.** The
  history header now has a select-mode toggle: rows grow checkboxes, click or
  Shift-click selects a range, and a bulk bar offers Select all / Clear, Pin or
  Unpin, and Delete (one themed confirmation, then the existing delete path so
  live runs and queues are reset). Escape leaves select mode. This exposes the
  already-present `bulkPin`/`bulk*` organization API; no doc change — UI-only
  behaviour over an unchanged data layer.

- **chore(repo): a junk sweep that cannot be re-broken by the test suite.** The
  checkout had accumulated ~9.6 GB of dead code-index scratch — thousands of
  `ws_tools_*.db` per-run test indexes and `.corrupt-*` snapshots — because
  tests that build a real workspace index wrote into
  `.black-eclipse/code-index/`. `HARNESS_CODE_INTEL_INDEX_DIR` now really
  relocates that store (it previously only reached the reported config), and
  the new `HARNESS_WORKSPACE_INDEX_DIR` does the same for
  `.black-eclipse/workspace-index/`; `python/tests/conftest.py` points both at
  one temp dir for the session and removes it at exit, so a test run no longer
  writes per-workspace DBs into the checkout. Added `npm run clean:junk`
  (`scripts/clean-junk.js`): it removes corrupt index snapshots, test-created
  `ws_tools_*` DBs, index caches older than 7 days with no live WAL, dev/prod
  logs, `.tmp-tests`/`.pytest_cache`/`%SystemDrive%` litter, and with `--build`
  the regenerable build output; it never touches DB vaults, credentials, pinned
  `.black-eclipse/desktop-dist-*`/`.next-desktop*`/`.next-live-*` builds or
  `releases/`. Docs updated: `docs/QUICKSTART.md`,
  `docs/harness/code-intelligence.md`, `docs/CHANGELOG.md`.

- **feat(install): a one-command install lane that downloads and checksum-verifies
  the published release, instead of only offering a button or a git clone.**
  `scripts/install-release.ps1` (Windows: resolves `releases/latest` or an
  explicit tag, requires the SHA-256 from `SHA256SUMS.txt` when published, runs
  the NSIS installer with `/S`, per-user, no admin) and
  `scripts/install-release.sh` (Linux `.deb` through `apt-get`/`dpkg`; macOS
  `.dmg` to `/Applications` with the quarantine flag cleared). Both take a
  version tag, an out-of-band `--sha256` pin, `--dry-run` and `--repo`, print the
  computed digest unconditionally, and refuse anything that is not an
  `https://github.com/<repo>/releases/...` URL. Neither compiles anything nor
  reads the git tree: the artifact is exactly the one
  `.github/workflows/desktop-release.yml` publishes. Authenticity is unchanged
  and is NOT claimed by these scripts (the Ed25519 manifest stays
  `published: false`, and the README's "every release publishes SHA256SUMS.txt"
  claim is corrected to Windows-only). Docs updated: new `docs/install.md`;
  `README.md` §Install now leads with the installer and keeps the source build
  as a contributor sub-section; `docs/QUICKSTART.md` disambiguates install vs
  checkout; `docs/UPDATES.md` drops the "users clone the repo" premise;
  `docs/NAVIGATION.md` gains the delivery row.

- **feat(install): `npm run check:downloads` probes whether the README download
  buttons actually serve a file.** `scripts/check-downloads.js` HEADs (then GETs)
  the three `releases/latest/download/<asset>` aliases plus `SHA256SUMS.txt`,
  prints status and size, and on failure names WHICH of the three invisible
  causes applies: the repository is not publicly readable (a private repo 404s
  anonymously), no published release is visible (the release workflow publishes
  **drafts**, and `/releases/latest` ignores drafts and prereleases, so a green
  CI run still leaves the button dead), or the asset was renamed (it lists what
  the release actually carries via the API). Optional `--version`, `--repo`,
  `--assets`. Network-dependent, so it is NOT in `npm run check:all`; it is a
  pre-announce check. Docs: `docs/install.md` (delivery section).

- **chore(repo): removed ~32.6 GB of dead runtime/scratch artefacts.** Deleted
  the seven `.corrupt-*.db` code-index snapshots (`CodeIndex.recover` never
  re-reads them), 11,927 empty `ws_tools_*.db` pytest leftovers and 13,710 stale
  per-workspace index caches (the index is a cache and rebuilds on demand, so
  the live `ws_c58…db` and WAL were kept), all 205 dev/prod logs, the literal
  `%SystemDrive%` directory (Windows cache DBs from an unexpanded path),
  `.tmp-tests/`, empty root `eclipse-memory.db`, regenerable build output
  (`.next`, `.next-dev`, `dist`, `build`, `src-tauri/target{,-dev}`,
  `rust/fframes-worker/target`, `.pytest_cache`, `*.tsbuildinfo`), old rolling
  JDdS copies (newest kept), the 1.9 GB `blackeclipse-*.tar.gz`, `_backups/`
  working copies and stale clone, and the search-index cache. Live pinned
  builds, `releases/stable`, `.next-desktop*`, `.next-live-stable`, the live
  index, all `*.db` vaults, `.env`, `.connector-key` and the Nov-15 pre-rewrite
  git bundle were preserved on purpose. Also untracked the committed
  HyperFrames `.thumbnails/` and `.waveform-cache/` caches (now ignored by
  `media/blackeclipse-launch/.gitignore`) and removed a duplicate harness-report
  PDF. no doc change — runtime/scratch cleanup only, no architecture, data
  shape, or setup contract changed.

- **style(desktop): remove the last browser tells from the app window.** The
  WebView was still inheriting its localhost-page defaults: a bright blue
  `::selection` highlight, light-mode native widgets (`color-scheme` was
  `normal`, so `<select>` lists / date pickers / checkbox gutters painted
  light), selectable-and-draggable UI chrome, anchor/image drag ghosts,
  rubber-band overscroll, Chromium's autofill wash, and the WebView context
  menu (Reload / Save as / Print / View source / Inspect) plus Ctrl+R / Ctrl+P
  / Ctrl+S / Ctrl+U / Ctrl+±/0 / ctrl+wheel page zoom and file-drop
  navigation. A new unlayered "Desktop shell chrome" block in
  `src/app/globals.css` themes the UA surface and a new
  `DesktopShellGuards` (`src/components/layout/desktop-shell-guards.tsx`,
  mounted in the root layout) suppresses the browser chrome — text fields
  keep the platform undo/cut/copy/paste menu, and a text selection on content
  gets an Eclipse-glass Copy menu instead of the WebView menu. Sidebar links
  no longer honour Ctrl/Cmd-click "open in a new browser tab"; the desktop
  shell has one window and its own tab strip. Helpers live in
  `src/lib/desktop/shell-guards.ts` with unit tests. no doc change — UI
  behaviour only, no architecture/data/setup contract changed.

- **fix(ui): destructive confirmations use an Eclipse-themed centred dialog, not
  the browser's OS pop-up.** Every `window.confirm/alert/prompt` call site
  (deleting a chat, bot memory, theses, tables, artifacts, journal records,
  skills/bundles, workspaces, graph workflows, broker actions, settings resets,
  renames/link prompts) now goes through one queued primitive —
  `confirmDialog`/`alertDialog`/`promptDialog` in `src/lib/ui/confirm-dialog.ts`
  — rendered by `ConfirmDialogHost`
  (`src/components/ui/confirm-dialog-host.tsx`, mounted in `src/app/layout.tsx`)
  as a `.glass-card-strong` dialog centred in the window. The helper is UI-free
  so `src/lib` widgets can use it without breaking the import boundary.
  Docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.

- **test(harness): the hardcore prompt suite has published run evidence.**
  Added `docs/harness/prompt-tests/README.md` plus one file per run under
  `docs/harness/prompt-tests/runs/`: 31 of the 38 prompts completed with full
  prompt + answer + run id/steps/tools/errors; `#28/#32/#33` stopped at real
  approval gates (browser action / portfolio write), `#13/#16/#18` were skipped
  as mutating, `#19` needs a scanned-PDF attachment. `#10` was rerun to
  completion after a restart. No runtime behavior changed by the export itself.
  Docs: `docs/harness/prompt-tests/`.
- **style(chat): dark prompt bubble defaults to `#2e2e2e`.** The user's own
  messages (Eclipse Agent) now paint a dedicated charcoal instead of a 24%
  foreground tint (~#414141), so the bubble separates from the near-black
  conversation surface without reading light. Updated `DEFAULT_CHAT_BUBBLE_BG_DARK`,
  the `.chat-bubble` CSS fallback, and the Prompt-bubble settings defaults.
  Docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **test(oss): pin the public SBOM artifact.** New
  `src/lib/oss/sbom-artifact.test.ts` (3 tests) asserts the committed
  `sbom.cdx.json` / `THIRD-PARTY-NOTICES.md` pair is current (`--check`),
  is CycloneDX 1.5 with a **unique** `bom-ref` per component (the dedupe bug
  produced 23 duplicates), every component carries type/name/version/purl/
  licence, the app version matches `package.json`, and the notices keep the
  AGPL carve-out and the Python `NOASSERTION` caveat. no doc change - test-only.
- **docs(readiness): point the production roadmap at `v0.4.0` without re-baselining.**
  `PRODUCTION-READINESS.md` still described `v0.3.2` as the current release. It
  now names `v0.4.0` as the latest tag and states plainly that the C-gate
  baseline was measured at `v0.3.2` and has not been re-measured, so no gate is
  silently carried forward. Docs updated: `docs/PRODUCTION-READINESS.md`,
  `docs/CHANGELOG.md`.
- **docs(contributing): name the public-release checks where contributors look.**
  `Black-Eclipse-site/CONTRIBUTING.md` now documents `check:oss`,
  `oss:prune-refs` and `sbom` next to the release gate, with the reason they are
  not part of `check:all` (a private tree legitimately fails them). The
  publication checklist also covers the GitHub Discussions link and the issue
  template URL, which break if the public repository URL changes. Docs updated:
  `CONTRIBUTING.md`, `docs/OPEN-SOURCE-READINESS.md`, `docs/CHANGELOG.md`.
- **chore(oss): a dry-run-by-default tool to prune the stale history refs.**
  New `scripts/prune-stale-refs.js` (`npm run oss:prune-refs`) finds the branches
  whose history still contains a `.db` snapshot or a personal author address,
  refuses to touch `main`/the checked-out branch/tags, prints the exact
  `git push origin --delete` command, and only executes with `--apply` (then
  `git fetch --prune`). On this tree it identifies exactly the 12 stale remote
  branches, 0 local branches and 0 tags, with `main` clean. `check:oss` now also
  requires `sbom.cdx.json` and `THIRD-PARTY-NOTICES.md` to exist and match the
  lockfiles. Docs updated:
  `docs/OPEN-SOURCE-READINESS.md`, `docs/CHANGELOG.md`.
- **ci(oss): make the public-release preflight automatic once the repository is
  public.** New `.github/workflows/oss-preflight.yml` runs `check:oss` with full
  history on every push/PR, but the job is skipped while
  `github.event.repository.private` is true - a private working repository
  legitimately fails it. It becomes a real gate at the moment of publication and
  can be dispatched by hand first. README licensing now links the generated
  `THIRD-PARTY-NOTICES.md` and `sbom.cdx.json`. Docs updated:
  `docs/OPEN-SOURCE-READINESS.md`, `docs/CHANGELOG.md`.
- **chore(oss): generate an SBOM and third-party notices from the locked trees.**
  New `scripts/generate-sbom.js` (`npm run sbom`) writes `sbom.cdx.json`
  (CycloneDX 1.5, 1,320 components: 1,185 npm + 135 Python) and
  `THIRD-PARTY-NOTICES.md` at the repository root from `package-lock.json` and
  `python/requirements.lock`. Licences use SPDX ids where the lockfile declares
  one, SPDX expressions for compound values, and `NOASSERTION` for packages that
  declare none (all Python entries) instead of guessing; `--check` fails on
  drift, CI enforces it, and `npm run release:bundle` regenerates it. This
  closes the SBOM gap in the open-source release checklist. Docs
  updated: `docs/OPEN-SOURCE-READINESS.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **docs(release): add the missing v0.4.0 product release note.**
  `docs/releases/v0.4.0.md` documents the C2-C9 core-integrity work and uses the
  generated `docs/harness/releases/v0.4.0/report.json` numbers (1,091 tools,
  scorecard 8/8, conformance 12/12, wheel sha256) rather than hand-typed claims.
  The tag existed with no note in the release index. Docs updated:
  `docs/releases/v0.4.0.md`, `docs/OPEN-SOURCE-READINESS.md`,
  `docs/CHANGELOG.md`.
- **chore(oss): CFA trademark notice, a 1-approval ruleset, and honest residual
  risks.** Added `.black-eclipse/skills/CFA-NOTICE.md` and a one-line "not
  affiliated with CFA Institute" notice to all 12 `cfa-*` skills; changed
  `.github/ruleset.json` to require 1 approval (the public posture) and recorded
  the solo-maintainer consequence in `docs/repository-guards.md`; corrected the
  `CODEOWNERS` comment that already claimed the repository was public; fixed
  `SECURITY.md`'s stale claim that Python dependencies are not locked and added
  the residual risks accepted for the source release. Docs updated:
  `docs/repository-guards.md`, `docs/OPEN-SOURCE-READINESS.md`,
  `docs/legal/README.md`, `SECURITY.md`.
- **fix(charts): type the Plotly layout so `tsc --noEmit` passes.** The dual-axis
  work wrote `layout.scene` on an inferred `{ autosize, height }` literal, which
  failed the release gate. The layout is now annotated as
  `Record<string, unknown>`; no runtime change. no doc change - type-only fix.
- **chore(oss): `check:oss` names the refs that still expose old history.**
  The history checks previously reported only the offending path or address,
  which after a rewrite reads like "redo everything". They now use
  `git for-each-ref --contains` to list the exact branches/tags, and say when
  `main` and the tags are already clean. On this tree it proves the remaining
  `jdds.db` exposure is eleven stale remote branches and the personal address
  survives only on `origin/backup-before-email-rewrite`. No doc change beyond
  this entry (the readiness doc already owns the deletion runbook).
- **fix(charts): a chart can no longer paint over text, and dual-axis charts use
  a real second scale.** Two defects from the six-chart stress session.
  (1) `plotly-chart.tsx`: the zoom/reset/save controls were overlaid in the
  chart's bottom-left corner, on top of the x-axis labels of short charts, and
  the plot wrapper had no paint boundary, so a legend/hover/3-D element could
  spill over the caption or the next block. The wrapper is now
  `relative isolate overflow-hidden` and the controls are their own row under
  the plot; the focus view height drops 0.82 -> 0.78 to leave room for them.
  (2) `python/harness/charts/plotly_figure.py`: a mark's `yAxis: "right"` was
  accepted by the contract and then ignored, so both series shared one scale
  (the index line flattened under the turnover bars). Scene panels now create
  an overlaying right axis (`yaxis2...`), route the mark's trace to `y2...`, and
  reserve a 64 px right margin for its ticks. (3) 3-D scenes inherited the 2-D
  `dragmode: "pan"`, so dragging only panned and the chart never orbited: the
  engine now states `scene.dragmode: "turntable"` and the browser enforces it
  for any 3-D figure (on first draw AND on reset view, via the tested
  `layoutWithSceneOrbit` helper). Tests: 74 Python chart tests; 4 client tests
  for the orbit guard; `npx tsc --noEmit`. Docs updated: `docs/chart-engine.md`.
- **fix(desktop): live mode sets itself up, and names the one change it cannot
  hot-reload.** `desktop:live` no longer refuses on an unbridged Stable install:
  it runs `scripts/desktop-dev-bridge.js` itself (bundled payload preserved as
  `app.bundled-<version>`) and builds the Dev shell once when it is missing, so
  the command is the only thing to run. It also compares `desktop/src-tauri`
  mtimes with the window binary and prints the exact rebuild command
  (`desktop:build:dev-shell` / `desktop:installer`) when the Rust shell is stale
  - a compiled binary still cannot hot-reload, so the caveat is surfaced instead
  of discovered. The live splash now says "compiling the UI for this window"
  rather than "Starting the server…", matching the one-minute first compile.
  Docs updated: `docs/environments.md`, `docs/QUICKSTART.md`.
- **fix(desktop): live relaunch waits for the old window to exit.** Verified end
  to end (shell up, `next dev` on 3100, `.next` untouched). The first attempt
  left the app on the splash: `stopShell` returned as soon as taskkill was
  issued, and Tauri's single-instance plugin handed the new launch to the OLD
  process while it was still exiting, so no bootstrap ran. `desktop-process.js`
  now exposes `waitForShellExit(channel)` and `desktop-live.js` blocks on it
  before relaunching. No doc change beyond this entry — the behaviour is what
  `docs/environments.md` already describes.
- **fix(desktop): `npm run desktop:live` actually exists now.** The live-mode
  note above landed the bootstrap half (`.next-live-<channel>` + `next dev`)
  but no entry point: `package.json` had no `desktop:live`, no script set
  `BE_DESKTOP_LIVE`, and a live server left no owner marker, so a second live
  launch would have been refused as a port conflict. Added
  `scripts/desktop-live.js` (verify the channel runs THIS checkout — Stable
  refuses without the dev bridge, Dev refuses without its shell — then stop the
  channel window + owned server and relaunch with `BE_DESKTOP_LIVE=1`),
  `launchShell(channel, extraEnv)`, the npm script, and
  `.next-live-stable/types/**/*.ts` / `.next-live-dev/types/**/*.ts` in
  `tsconfig.json` plus `.next-live-*/**` in the eslint ignores, so a live
  session cannot make Next rewrite `tsconfig.json` or lint generated output.
  Docs updated: `docs/QUICKSTART.md`.
- **feat(desktop): live mode — the window updates on every save.** The desktop
  serves an immutable pinned build, so a `src/` edit was invisible until
  `desktop:refresh` rebuilt, promoted and reopened the app (Python changes were
  live immediately, which is how a chart could be coloured in the PNG and grey
  in the window). Added `npm run desktop:live` (`scripts/desktop-live.js`):
  it closes the channel window/server and relaunches it with
  `BE_DESKTOP_LIVE=1`, which makes `scripts/desktop-server.js` run `next dev`
  against its own `.next-live-<channel>` dist dir instead of `next start`
  against a pin. Saving under `src/` now hot-reloads the open window; leaving
  live mode is the ordinary `desktop:refresh` / `desktop:dev`. Also added the
  npm script, the gitignore entry, a standing AGENTS rule ("a UI change is not
  done until the window serves it") and docs. Docs updated:
  `docs/environments.md`.
- **fix(charts): charts are coloured by default again; an untouched greyscale
  palette is migrated.** The shipped default palette (`src/lib/chart-palette.ts`)
  and the Python chart theme (`python/harness/charts/theme.py`) had become a
  near-white/grey ramp, so every chart Eclipse drew - the live Plotly figure, the
  drawn PNG fallback and the artifact/PDF export - read as black and white. The
  default is now a categorical colour set (ocean blue, amber, violet, rose, teal,
  fuchsia) with the conventional green/red market pair, and the Settings presets
  (`chart-settings.tsx`) lead with "Eclipse" while "Black & white" stays one
  click away. `chart-palette-store.ts` migrates a stored palette that is exactly
  one of the pre-colour greyscale defaults once (revision marker
  `be_chart_palette_rev`, written on explicit saves), so existing installs get
  colour without losing a later deliberate choice. The desktop had also been
  serving a Nov-13 pinned UI bundle, so `npm run desktop:refresh` was required to
  ship the palette change to the app window. Tests:
  `src/lib/chart-palette-store.test.ts`. Docs updated:
  `docs/chart-engine.md`, `docs/interactive-response-engine.md`.
- **fix(runtime): Eclipse no longer ends a run on the first blocked route.** Four
  linked changes. (1) `tool_disclosure.py`: `auto` now narrows an oversized
  schema even when the model's context window is unknown (`ABSOLUTE_SCHEMA_BUDGET_TOKENS`
  = 20k), and the read-only tail is query-focused (`FOCUS_READ_TOOLS` +
  `rank_tools`, 32 extras) instead of all-or-nothing. Measured on the live
  registry: 853 bound tools / 103,265 schema tokens → 142–174 bound / 20–26k
  (≈77–82k saved per step). (2) `answer_guard.py` + `graph.py`: a bare,
  route-specific refusal is sent back for at most 2 extra turns with a
  deterministic directive naming the untried permitted routes; a substantive
  partial answer, a policy refusal and an explicitly source-restricted request
  are never recovered. (3) `retrieval_tools.py`: every UNAVAILABLE result names
  concrete next routes and returns `nextRoutes`; an explicit `webFallback`
  (series/macro only) adds WEB as the LAST route and labels the result `PARTIAL`.
  (4) the static prompt's contradictory "one attempt per route" guidance is
  replaced with one ladder and one stop condition. The final-answer branch moved
  to `final_answer.py` (graph.py stays under its ratchet); `RunSpec.dispatch_allowed`
  keeps the pre-disclosure surface for dispatch, so hiding a tool's schema is an
  advertising choice, never a revocation. Events
  `answer.recovery_started`/`answer.recovered`/`answer.recovery_exhausted`;
  outcome `answerRecovery`. Tests: `python/tests/test_answer_guard.py`,
  `test_disclosure_dispatch.py` (a hidden read tool still dispatches),
  `test_tool_disclosure_bm25.py`, `test_retrieval.py`, `test_replan.py`,
  `test_size_budget.py`. Docs: `docs/harness/no-dead-ends.md`,
  `docs/harness/failure-recovery.md`, `docs/harness/architecture.md`,
  `docs/harness/tool-registry.json`, `docs/harness/benchmarks.md` (regenerated).
- **docs(readme): say which data sources are commercial, which are not, and how to
  add your own.** New "Data sources and commercial use" section, built from the
  generated catalogue (`docs/data-sources.md`) rather than from memory: the three
  tiers (included / connect your own / advanced), the commercial statuses
  (`ok` / `attribution` / `personal-only` / `verify`), and an explicit
  **personal-use-only** list - TradingView scanner, Yahoo Finance (`yfinance`),
  Binance public ticker, CoinGecko keyless, DuckDuckGo HTML - with the reason they
  are off by default. States that a source that is off cannot serve a screen because
  `data-source-preferences.ts` is consulted at the fetch path, and that adding a
  source is an entry in `source-catalog.ts` plus `npm run docs:data-sources`.
  Carries the two qualifiers the catalogue itself carries: the table is an
  informational snapshot of published terms, not legal advice or a licence grant;
  and language models are separate (bring your own key, or Ollama locally).
  docs updated: `docs/public-readme.md` (evidence row), `docs/CHANGELOG.md`.
- **docs(readme): ship the Bots and Workflows screenshots, both captured from the
  installed app.** The two surfaces that carry the product argument are now the
  hero and the first grid row: **Bots** (13 agents with `Active`/`Completed` state,
  the Investment Committee and Markets Desk rooms, and a real Data Quality Auditor
  report that marks unreachable sources `UNAVAILABLE` and names the next permitted
  route) and **Workflows** (20 typed, versioned, tagged graphs with `Open editor`
  and *generate from prompt*). Neither came from the dev server: five earlier
  attempts there produced `LOADING` panes and a blank canvas, so the captures were
  taken from the **installed** desktop app - the only lane with a warm harness and a
  live catalogue. Toast and first-run tour dismissed before capture, no machine
  paths in frame. The bot image is deliberately shown mid-report because the
  refusals are the product. Dashboard and Journal remain staged pending fresh
  prices. docs updated: `docs/public-readme.md` (capture lane + staged list),
  `docs/CHANGELOG.md`.
 **feat(response): answers are figure-first — a backtest is drawn, not tabulated.**
  Added a top-level "Show the result, don't table it" section to the Eclipse agent
  prompt (`python/harness/prompts.py`): data and computations (backtests, equity
  curves, drawdowns, series, distributions, comparisons, allocations) are shown as
  `chart`/`panels`/`interactive` blocks, and `data_table` is only for rows the user
  asked to see. Added `FIGURE_FIRST` to the deterministic response orchestrator
  (`python/harness/response_mode.py`) so every mode's directive carries the bias,
  reordered the `simulation`/`visualization` suggested blocks to lead with `chart`,
  and rewrote the simulation directive around a backtest's equity curve, drawdown
  and metrics instead of a trade table. The JIT design modules
  (`python/harness/response_style.py`) now say `data_table` is never the default for
  a series. Paid for the prompt guidance by trimming redundant wording elsewhere,
  so the static prompt stays under its 47371-char ratchet. Tests:
  `python/tests/test_response_mode.py`. Docs updated:
  `docs/interactive-response-engine.md`.
- **fix(runtime): a finished run's SSE stream can no longer hang after the answer
  arrives.** `GET /runs/{id}/stream` waited only for the event-bus sentinel when
  the run looked active. `end_stream()` runs in a `finally` BEFORE the task is
  marked done, so a stream opened in that window never got the sentinel and held
  the connection open forever — the UI showed the full answer and stayed
  "writing". The frame producer moved to the new `python/harness/run_stream.py`
  (out of the size-ratcheted `main.py`) and now closes on a terminal event, on an
  inactive run, and re-checks the durable trace on each keep-alive tick.
  `EventBus.end_stream` also makes room for the sentinel when a slow client's
  queue is full instead of silently dropping it. Tests:
  `python/tests/test_run_stream_close.py`. no doc change — behavioral bug fix,
  contracts unchanged.

## 2026-11-15
- **security(audit): close drive-by CSRF and DNS-rebinding paths; add a full
  audit report set.** The default desktop runs `HARNESS_AUTH=off`, and 59
  mutating API routes had no same-origin guard, so a malicious page could reach
  `/api/code/shell` and workspace writes (verified: a cross-origin `text/plain`
  POST created a folder). Added a central cross-site gate in
  `src/middleware.ts` before the auth-mode branch (mutations must pass the
  shared same-origin/loopback/secret policy; `Sec-Fetch-Site: cross-site` is
  refused; HMAC webhooks exempt). Added loopback `Host` validation in
  `python/harness/deps.py` and `security/identity.py` so DNS rebinding cannot
  impersonate an operator. Also: artifact ownership from the verified identity
  instead of `x-eclipse-user`, `x-forwarded-host` honoured only under
  `BE_TRUST_PROXY=1`, destructive-command hardline on the HTTP terminal/shell
  routes, payload pruning of `python/.black-eclipse` and databases (plus removal
  of leaked `dist` channel keys), `userId` from verified identity on `/runs`, and
  `permissions: contents: read` on the deploy/live-evals workflows. Upgraded
  `next` 15.5.18 -> 15.5.29 for the Critical Windows/image RCE advisories, pinned
  `dompurify`/`proxy-addr`, and removed every production Critical from
  `npm audit`. Also added a 40 MB API body cap, redacted tool output before
  persistence, dropped capabilities + `no-new-privileges` on the quant sandbox,
  corrected the stale "trading is read-only" comments, and added a production
  Critical audit gate to CI. Every GitHub Action is now pinned to a commit SHA,
  the Python stack has a universal hash-locked `python/requirements.lock`
  (`npm run lock:python`), `/runs` + cancel/resume require the operator token,
  and the privileged route families now enforce the DB-backed session check
  (`requireApiAuth`). Login and the desktop's `HARNESS_AUTH=off` path were
  deliberately left unchanged: the app is local-only and has no sign-in screen. Audit deliverables under `security/audit/` (kept out of the
  public tree). Git history was rewritten on 2026-11-15: every `jdds.db`,
  `dev_output.log` and `dev-server.log` blob was removed and the personal author
  email was mapped to the public noreply handle, after a full bundle backup;
  `oss-preflight.js` now passes with 0 warnings. Release remains **CONDITIONAL**:
  session revocation / dependency / multi-tenant items still need a fix or an
  explicit local-only accept. Docs updated:
  `docs/harness/security.md`, `docs/harness/authentication.md`, `SECURITY.md`,
  `.env.example`, `docs/CHANGELOG.md`.
- **docs(readme): ship the Bots and Workflows screenshots, both captured from the
  installed app.** The two surfaces that carry the product argument are now the
  hero and the first grid row: **Bots** (13 agents with `Active`/`Completed` state,
  the Investment Committee and Markets Desk rooms, and a real Data Quality Auditor
  report that marks unreachable sources `UNAVAILABLE` and names the next permitted
  route) and **Workflows** (20 typed, versioned, tagged graphs with `Open editor`
  and *generate from prompt*). Neither came from the dev server: five earlier
  attempts there produced `LOADING` panes and a blank canvas, so the captures were
  taken from the **installed** desktop app - the only lane with a warm harness and a
  live catalogue. Toast and first-run tour dismissed before capture, no machine
  paths in frame. The bot image is deliberately shown mid-report because the
  refusals are the product. Dashboard and Journal remain staged pending fresh
  prices. docs updated: `docs/public-readme.md` (capture lane + staged list),
  `docs/CHANGELOG.md`.
- **docs(readme): state the install prerequisites the installer actually removes.**
  Added a "One download, nothing to install first" block to Install, because the
  page implied a prerequisite-free install without saying which ones or proving it.
  Verified in the code, not the plan doc: `desktop-installer.js` builds the payload
  with `runtime/node.exe` and `scripts/vendor/python`, so Node/Python/SQLite are
  bundled; the NSIS manifest is `RequestExecutionLevel user` with
  `InstallDir $LOCALAPPDATA\Programs\BlackEclipse`, so no administrator rights;
  `desktop-packs.js` imports feature packs lazily, so a missing pack degrades one
  capability rather than blocking install; and only `--full` bundles those packs,
  which is why the stable `BlackEclipse-Setup.exe` alias intentionally mirrors the
  slim build. Internet and a model key are the two real prerequisites, and both are
  now stated as such. docs updated: `docs/public-readme.md` (three new evidence
  rows), `docs/CHANGELOG.md`.
- **fix(readme): the three download buttons now fit one line.** At 340px each the
  row wrapped, leaving Windows alone with Linux and macOS stranded underneath. The
  trio is resized to 300 + 210 + 210 (736px inside GitHub's ~880px column) with
  short labels (Windows / Linux / macOS) and the arch moved into the sublabel, so
  the primary button leads and the other two sit beside it instead of below.
  Sizing rationale recorded so a fourth platform shrinks the row instead of
  re-wrapping it. docs updated: `docs/public-readme.md`, `docs/CHANGELOG.md`.
- **feat(readme): Linux and macOS download buttons.** The page had one button for
  Windows plus a table nobody scrolls to. It now carries three, each pinned to the
  version-independent alias from the download contract (`BlackEclipse-Setup.exe`,
  `BlackEclipse-linux-amd64.deb`, `BlackEclipse-mac-arm64.dmg`) with a one-line
  platform/signing note and an "all releases" fallback. Windows stays lime; the
  other two are dark so the default path still reads as the default. macOS keeps
  the architecture in the name on purpose - only one arch is built per runner and
  handing an Intel Mac an arm64 build is worse than making the choice visible.
  Both SVGs are shape-only (no fonts, no network refs) so they render through an
  `<img>` on GitHub. `desktop-release.yml` now asserts each exact alias exists and
  fails the release instead of publishing a button that 404s; it previously only
  globbed `BlackEclipse-linux-*.deb` while the button was pinned to `-amd64`.
  docs updated: `docs/public-readme.md` (three-button contract table),
  `docs/CHANGELOG.md`.
- **docs(launch): record the four blocked launch items with an owner each.**
  `docs/public-readme.md` §6 went from "two things that are not finished" to a
  four-row table naming who can actually close each one (social preview: web UI
  only, GitHub has no API for it; the four screenshots: one command against a
  running install; PyPI: a token; public repo: a decision plus the history
  rewrite) - so the next person does not re-litigate or re-attempt them. Also
  recorded the five rejected capture attempts with their measured causes (a
  290-second US refresh that blocks the Node event loop for ~100s afterwards,
  `?tab=` deep links landing on the wrong tab on a cold dev load, bots threads
  fetching from a 1.8 GB store, Graph Studio stopping at the gallery), so the
  constraint is documented as "the dev lane cannot serve a warm app" rather than
  "the screenshot script is flaky". docs updated: `docs/public-readme.md`,
  `docs/CHANGELOG.md`.
- **docs(readme): gate the four state-dependent screenshots, drop the empty
  dashboard shot.** Tried four times to capture Dashboard, Journal, Graph Studio
  and Bots from a dev server pointed at a copy of a real vault (55,714 prices,
  20 workflows, 13 automations, 76 demo trades seeded after scrubbing 121 broker
  trades). What was actually reproducible: the Dashboard and Journal correctly
  render `LIVE PRICES UNAVAILABLE` / `LOADING` because the copied prices are days
  old, the Bots list populates (13 automations including the full Institution cast)
  but its conversation pane stays on `LOADING`, and `?tab=graph-studio` opens the
  Workflows gallery yet never a canvas. None of that is shippable, so the empty
  Dashboard figure was **removed** rather than kept, leaving three real populated
  captures, and all four remaining shots are staged behind an HTML comment in the
  README with the exact blocking reason for each. `scripts/capture-readme-shots.js`
  waits for real content and refuses to write a figure that is still loading.
  docs updated: `docs/public-readme.md` (per-surface blocking table + the
  stale-vault and personal-vault rules), `docs/CHANGELOG.md`.
- **docs(readme): stage the Graph Studio and Bots figures behind a capture gate.**
  Tried to capture the workflow editor and the bots workspace for the README. Both
  tabs open (`?tab=graph-studio`, `?tab=bots`), but on a dev server with no seeded
  harness they render `BOTS · 0 / Loading` and a blank canvas, so neither was
  added - an empty workspace photograph is worse than none. Instead:
  `scripts/capture-readme-shots.js` captures both from a seeded install at
  1920x1080, crops to 1600, and **refuses to write a figure whose expected content
  never appears**; the README carries the two table rows behind an HTML comment so
  the wiring is one edit away. `docs/public-readme.md` section 3 records the recipe,
  the refusal rule, and that the headless/empty attempt was rejected. docs updated:
  `docs/public-readme.md`, `docs/CHANGELOG.md`.
- **docs(readme): close the launch-review gaps - screenshots, methodology,
  licensing, signing, limits.** Applied the README review. Added four real
  captures of the running app (`docs/figures/readme/`, 1600x868), a six-step
  research-to-execution workflow, a five-persona "who it is for" table, a
  methodology table beside the benchmark numbers (347 tasks / 15 datasets / 78.1%
  oracle coverage / 278 trials / how `financial_accuracy` is graded / what it does
  NOT measure), an explicit two-license table, a platform + signing-status table
  with `SHA256SUMS.txt` verification, and a three-row troubleshooting table. The
  install copy now says a hosted provider needs a key instead of implying none
  ever are. Cropping the captures was not cosmetic: the composer status strip
  renders `C:\Users\<name>\AppData\Local\Temp\...`, so uncropped shots would have
  published a user profile (the O3 leak class). Two claims were dropped during
  verification - `npm run doctor` does not exist (it is `desktop:doctor`) and the
  "good first issue" label does not exist (now plain Issues). docs updated:
  `docs/public-readme.md` (new section order, screenshot policy, six new evidence
  rows), `docs/CHANGELOG.md`.
- **docs(readme): adopt the launch copy and make it checkable.** The README now
  runs on the product copy: the harness positioning ("The Open-Source Financial AI
  Harness" / *Research. Analyze. Build. Trade.*), the five problems each paired
  with what Eclipse does about it, nine capabilities, and seven architecture areas.
  Everything that could be a dead end got a destination: each capability and
  architecture row links to the package or doc that implements it (verified: all 12
  relative links resolve); the problems became a two-column table so a problem
  never appears without an answer; the architecture list became a "what exists
  today + source" table. Analysis, plan, install, benchmarks, documentation and
  open-source sections were kept so the page still works as a repository front
  door. The MetaTrader 5 claim was verified before it shipped
  (`python/harness/trade/`, `MT5Adapter`) and the provider list was checked against
  `models.py` + the packaging extras. docs updated: `docs/public-readme.md`
  (structure + evidence rows for MT5 and providers), `docs/CHANGELOG.md`.
- **docs(readme): rewrite the public copy from slogans to mechanisms.** The first
  pass read as generic because its section headings were metaphors ("a door that
  doesn't open", "survives Tuesday", "colleagues, not macros") that could have
  described any product. The README is now task-first and checkable: *what it is*
  (the runtime, and the enforced rule that nothing outside `quant/` and
  `finance_facts/` may compute a trading statistic), *what you can do* (six tasks
  with their real mechanisms - schedule kinds, the six committee seats and their
  concurrency numbers, the sandbox flags), *what it refuses to do* (the six named
  refusal codes, the hardest block to copy honestly), and *how a run works*. Two
  copy rules were added so the next edit does not drift back: no slogan as a
  section heading, and concrete over clever. Social preview regenerated to match
  ("the model plans / python computes / the gate refuses"). docs updated:
  `docs/public-readme.md` (structure, two new copy rules, three new evidence
  rows), `docs/CHANGELOG.md`.
- **feat(launch): reposition the public page from the terminal to the harness.**
  The launch argument is now the agentic/quant substrate, not market data or the
  terminal UI: harness durability (leases, fencing, at-most-once effects, crash
  resume), one policy gateway with a hash-chained audit, source-authority
  evidence, generated evaluation scorecards, bots (schedules, teams, the
  Institution preset, goals/loops/heartbeats), quant research (anti-lookahead,
  walk-forward, Deflated Sharpe/PBO, sandboxed Python, gated live trials), and the
  research/execution boundary. The root `README.md` is the single public front
  door and was rewritten on that spine (no separate landing page and no Pages
  build - a reader decides on the repo page), keeping the download button, the
  two-tier benchmark and every existing link; the heading now states the category
  first ("an agent harness for trading research") instead of leading with a hook
  that only lands if you already know the product. Social preview is generated
  from `.github/assets/social-card.svg` (sharp), not hand-edited. The install
  block deliberately leads with the source install and
  labels PyPI as pending, because `black-eclipse-harness` is still not published
  (round-4 gap O6) - `pip install black-eclipse-harness` would be a false claim
  today. Added `.github/workflows/publish-harness.yml` (tag/version match gate, a
  no-data-in-package check, `twine upload` on a tag, `dry_run` by default). docs
  updated: `docs/public-readme.md` (new: the argument in order, claim-to-evidence
  table, copy rules, deliberate omissions, the two open items),
  `docs/NAVIGATION.md` (task row + the root README as the only public front
  door), `docs/README.md`, `docs/CHANGELOG.md`.
- **feat(release): one-click Download button that never breaks.** The README now
  leads with a "Download for Windows" button linking to
  `releases/latest/download/BlackEclipse-Setup.exe`, sourced from a local SVG
  (`.github/assets/download-windows.svg`, no shields.io dependency).
  `scripts/desktop-installer.js` writes that version-independent alias as a copy
  of the slim installer, removes it on an offline-only (`--full`) build so a
  stale installer can never be published, and includes it in `SHA256SUMS.txt`;
  `desktop-release.yml` uploads it as a release asset and fails the build when it
  is missing. The release body now leads with the direct link (the winget line is
  gone — those manifests still point at a repository that does not exist). The
  README's source instructions moved under "Build from source" so a downloader is
  not told to run `npm install` first. docs updated:
  `docs/desktop-size-plan.md` (the alias is the public download contract),
  `docs/CHANGELOG.md`.
- **feat(release): the download row covers every desktop platform.** Windows
  stays the primary button; `download-macos.svg` and `download-linux.svg` sit
  beside it (dark fill, accent outline — secondary weight). `desktop-bundle.js`
  now also writes stable aliases, `BlackEclipse-linux-<arch>.deb` (from
  `buildDeb`) and `BlackEclipse-mac-<arch>.dmg` (from `buildMac`), so the macOS
  and Linux buttons never break on a version bump. The macOS alias keeps the
  arch in its name on purpose: one arch is produced per runner and a Mac cannot
  run the other, so the button links `arm64` explicitly instead of handing an
  Intel Mac a binary it can never launch. `desktop-release.yml` asserts each
  alias exists, and the release body is now a platform → file table with the
  first-open step for each OS. docs updated: `docs/desktop-size-plan.md`
  (three-row name table), `docs/CHANGELOG.md`.
- **fix(desktop): closing the window now quits instead of only minimizing.**
  `Prefs::default()` shipped `keep_warm: true`, so every close (`X` in the
  tab strip, taskbar close, Alt+F4) hit `prevent_close()` + `minimize()` and the
  app looked like it never closed; the tray checkbox was the only way out.
  Keep-warm is now opt-in (`false` by default) and the shell logs
  `window closed — quitting`, hides the window, stops the owned server tree and
  exits. `desktop-prefs.json` gained a `version` field and a one-time
  `migrate_prefs` reset (v1) so installs that inherited the old default do not
  keep minimizing forever; the tray checkbox now reads its own checked state
  instead of flipping a mirror. Verified on the Dev shell: `CloseMainWindow()`
  → process exits, `[shell] server tree <pid> stopped`, no leftover node or
  python. docs updated: `desktop/README.md`, `docs/desktop-app-plan.md`.

## 2026-11-14
- **fix(desktop): installers ship a populated seed, not an empty one.** The
  packaged `app/seed/jdds.db` was schema-only, so a first run opened an empty
  journal until the boot hook fired. `scripts/lib/seed-db.js` (new) generates the
  schema, runs the *shared* demo seeder (`scripts/seed-journal.ts` →
  `src/lib/journal/demo.ts`), checkpoints WAL, and verifies `source:'demo'` rows
  before copying — packaged installs now open with ~88 labelled demo trades. It
  also regenerates a stale schema-only seed left by an earlier build (early-exit
  only when demo rows already exist) and clears an inherited `BE_DB_PATH` so the
  developer's own vault can never be baked into a release. No database is
  committed; real `source:'broker'` data still never ships. docs updated:
  `docs/QUICKSTART.md`, `docs/GLOSSARY.md`, `docs/harness/decisions.md` (ADR-H5
  rationale), `AGENTS.md`, `.opencode/skills/black-eclipse-db/SKILL.md`,
  `docs/CHANGELOG.md`.
- **security(oss): remove the remaining machine-local paths and personal
  address.** Deleted the generated `media/blackeclipse-launch/.hyperframes/`
  tree (29 tracked capture/cache files that embedded absolute user-profile paths) and
  gitignored `**/.hyperframes/`; replaced the absolute temp path in three
  `docs/harness/baselines/*.json` evidence files with `<tmp>`; removed the
  personal address from `install-git-hooks.js` (extra addresses now come from
  `GIT_COMMIT_BAD_EMAILS`); widened the `check:oss` path detector to catch
  JSON-escaped backslashes. The history scrub replacements now cover the old
  personal paths as well. docs updated: `docs/CHANGELOG.md`.
- **security(oss): scan and scrub leaked tokens from public history.** A
  `gitleaks 8.30.1` scan over `--all` on the scrubbed mirror found two real
  hardcoded service tokens in old commits (neither is present at HEAD). Both
  were removed with `git-filter-repo --replace-text`; `git log -S` now returns
  nothing and the history scan is green with the new reviewed `.gitleaks.toml`
  allowlist (test fixtures, `STORAGE_KEY` constants, eval `"key"` fields, a
  cache hash, the fake `AKIA...EXAMPLE`). **The two tokens still need to be
  rotated — scrubbing history does not revoke them.** docs updated:
  `docs/OPEN-SOURCE-READINESS.md`, `docs/CHANGELOG.md`.
- **test(fs): make the polling-modified check deterministic.** The watcher
  fingerprints `(st_mtime_ns, st_size)`; the test rewrote `one\n` as the
  same-sized `two\n` and used `os.utime(..., None)`, which can land in the same
  Windows timestamp tick. It now sets mtime +5 s explicitly. Passes 20/20 alone.
  no doc change — test-isolation fix.
- **test(automation): make the singleton-wired assertion self-contained.**
  `test_service_singleton_is_wired` now takes the module `ctx` fixture, so a
  prior module's app shutdown can no longer clear the process-wide automation
  singleton between tests (it passed alone, failed late in the full run). The
  file passes 8/8 alone. no doc change — test-isolation fix.
- **docs(readiness): record that the soak has no evidence on this host.** There
  is no `BlackEclipse App` or `Black Eclipse Backup` scheduled task, and
  `%LOCALAPPDATA%\BlackEclipse\health.log` is absent, so
  `scripts/soak-report.ps1` exits 2. The 7-day gate cannot close until the tasks
  are reinstalled and the clock is restarted; `ALERT_WEBHOOK_URL` is still unset.
  docs updated: `docs/PRODUCTION-READINESS.md`, `docs/CHANGELOG.md`.
- **docs(oss): public-release readiness surface and preflight.** Added the root
  community files a public repository needs (`CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, issue/PR templates), `repository`/`homepage`/`bugs` in
  `package.json`, a free `CodeQL` workflow, and `scripts/oss-preflight.js`
  (`npm run check:oss`). The preflight is deliberately **not** in `check:all`:
  it fails on history hygiene, and this tree still carries `jdds.db` blobs in old
  commits. Added `docs/OPEN-SOURCE-READINESS.md` as the owning doc for the
  history scrub, publication-day checklist and legal/IP review, and updated the
  root README to `v0.4.0` with the measured `task_success 0.9748` gate.
  Added `scripts/scrub-public-history.ps1`, a mirror-only wrapper for the
  `git-filter-repo` history scrub (supports `--replace-text` and `--mailmap`).
  Produced and verified a clean mirror: no DB blobs in any commit, 79.9 -> 40.3
  MiB, and `check:oss` PASS with 0 warnings in a clone of it. Not pushed; the
  live private history is untouched.
  Also removed the personal absolute paths from the bulk importers: they now
  resolve through `scripts/lib/import-paths.js` and `BE_IMPORT_ROOT`
  (default `/data/imports/`, which is gitignored), and the roadmap/media docs
  use `<repo>` / `%LOCALAPPDATA%` placeholders. docs updated:
  `docs/OPEN-SOURCE-READINESS.md`, `docs/NAVIGATION.md`, `docs/README.md`,
  `docs/PRODUCTION-READINESS.md`, `docs/legal/README.md`, `README.md` (both
  roots), `CONTRIBUTING.md` (both roots), `docs/CHANGELOG.md`.
- **brand(desktop): new app icon.** Replaced the desktop shell icon with the
  refreshed BlackEclipse mark (`ICON-LOGO-DESKTOP.svg`: dark radial tile,
  silver-gradient eclipse glyph, rounded card edge). Regenerated
  `desktop/src-tauri/icons/icon.ico` (16/24/32/48/64/128/256, 32-bit DIB entries)
  and `desktop/src-tauri/icons/icon.png` (512) — the pair Tauri embeds in
  `Black Eclipse.exe` and uses for the window/tray icon — plus
  `public/branding/black-eclipse.ico`, which `scripts/brand-runtime.js` stamps
  onto the packaged Node/Python runtime executables. Rasterised from the SVG with
  `sharp`; no dependency added. The installed shell only picks the new resource
  up after a Rust rebuild (`npm run desktop:build`) and a reinstall/shortcut
  refresh (`npm run setup:desktop` re-runs the icon-cache flush).
  **Gotcha found while applying it:** `cargo build` recompiled the crate but did
  not rerun `tauri-build`'s resource step, so the "new" exe was byte-different
  and still embedded the OLD RT_ICON blobs (confirmed by decoding them, not by
  trusting the timestamp). Touching `src-tauri/tauri.conf.json` forced the
  resource rebuild and the embedded icons then decoded to the new artwork.
  docs updated: `desktop/README.md` (icon-change procedure), `docs/CHANGELOG.md`.
- **refactor(importers): no hard-coded personal paths in the bulk importers.**
  The `scripts/import-*.js` one-offs defaulted to an absolute path on one
  developer's machine, which was useless elsewhere and leaked a personal
  directory into a tree headed public. They now resolve through
  `scripts/lib/import-paths.js`: `BE_IMPORT_ROOT` (set it to a directory that
  mirrors the documented layout) or `./data/imports` under the app directory.
  no doc change — one-off tooling; the helper's header documents the layout and
  the env var.

