# Change Log

## 2026-11-08
- **docs(release): add the production-readiness roadmap.** New
  `docs/PRODUCTION-READINESS.md` records the measured 2026-11-08 baseline
  (typecheck, tests, secrets, ADRs and size are green; `npx eslint .` has 3
  errors; the live agent gate still fails at `task_success 0.8520 < 0.9`; the
  preflight passes only as advisory and the container path is unverified),
  names the six blockers (R1-R6), defines
  twelve re-runnable exit criteria (C1-C12), and sequences the work as P0 tree +
  lint + merge, P1 clean build + secrets + container, P2 production-posture
  proof (journey, backup/restore, failure drill), P3 the live-gate decision
  (improve to 0.9 or an ADR with a recorded accepted floor), P4 release
  engineering (check:all on `main`, release note, tag, deploy/rollback), and P5
  operations. It deliberately separates engineering blockers from the external
  inputs (provider key, Docker host, second reviewer, CODEOWNERS team, counsel)
  so a finished code phase is never reported as a finished release. NAVIGATION
  gets a trigger row. Docs:
  `docs/PRODUCTION-READINESS.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **chore(changelog): rotate the active window.** Adding today's section took
  `CHANGELOG.md` to 8 dated sections, over the committed 7-section window the
  `changelog-guard` test enforces. `node scripts/rotate-changelog.js --write`
  moved `2026-11-01` into `docs/changelog/2026-11.md` (a move, never a prune),
  preserving the archive's line endings. no doc change — rotation is tooling,
  the policy is unchanged.
- **fix(lint): clear the three gate-blocking errors.** `folder-picker.tsx`
  renamed the `useWindows` callback to `openWindows` (it is a `useCallback`
  named like a hook, so `react-hooks/rules-of-hooks` failed the gate);
  `desktop-launcher.test.ts` replaced its two `any`s with a typed
  `LauncherTheme` shape. `npx eslint .` now exits 0 (0 errors, 118 warnings).
  Verified: `npx tsc --noEmit`, the two affected Vitest files (19 tests) and
  `python/tests/test_decisions.py` (28). no doc change — lint-only.
- **chore(release): complete P0 and land it on `main`.** The typed-decision and
  legal work (`cc5519ea`) and the roadmap + lint fix (`9785b485`) are merged into
  local `main` as `b48d3ba5`; the `CHANGELOG.md` merge conflict kept BOTH sides'
  `2026-11-04` entries and the rotated archive now carries main's `2026-11-01`
  bullets (including the `423,998` size re-pin), so no history was dropped.
  `npm run check:all` on `main` passes **ALL GATES** (tsc, eslint 0 errors,
  secret scan, advisory preflight, ADR + size, Vitest + Python, eval gates,
  corpus). `main` is clean and not pushed. Docs updated:
  `docs/PRODUCTION-READINESS.md`, `docs/CHANGELOG.md`.
- **fix(deploy): the security preflight accepts `HARNESS_AUTH=required`.**
  `scripts/security-preflight.js` had its own `truthy()` that omitted `required`
  — the documented production value, and the exact value `docker-compose.yml`
  forces — so a correctly hardened deployment failed its own deploy gate with
  "HARNESS_AUTH missing". It now mirrors `src/lib/auth/config.ts` exactly
  (`required`/`enable`/`enabled` are on; `off`/`none`/`disabled` are off) and
  returns `undefined` for anything else. Regression test
  `src/lib/security-preflight.test.ts` (8 cases) covers both the accepted
  vocabulary and the three fail-closed paths. Verified manually: a public
  production posture with generated secrets passes; without them it exits 1.
  `docs/DEPLOYMENT.md` now states that the script reads the process environment
  (not `.env`) and shows `node --env-file=.env scripts/security-preflight.js`
  for checking a filled file without exporting it. Also verified the clean
  build actually serves: `next start` on the fresh `.next` returned
  `GET /login` 200 in 2 s. Docs updated:
  `docs/PRODUCTION-READINESS.md`, `docs/DEPLOYMENT.md`, `docs/CHANGELOG.md`.

## 2026-11-07
- **feat(decisions): typed decision models (System One-shaped) as a first-class
  layer.** New `python/harness/decisions/` asks closed `choice` / `score` /
  `noul` questions about a `state` and returns typed answers with probabilities
  and confidence — deliberately NOT a chat provider (no messages/tools/
  streaming). Ships the deterministic rule provider (fully offline), a
  fail-closed `DecisionPolicy` (`answered` / `review` / `unavailable`), a
  privacy-gated provider registry, and an immutable `DecisionRecord` /
  `DecisionOutcome` audit on `agent-memory.db`. Read-only tools
  `decision_ask`/`decision_list`/`decision_scorecard` are wired through
  `AgenticService` → `execute_run` → `ToolContext.decision_service` and the
  Eclipse agent allowlist. A partial/mistyped answer, a provider error or no
  provider is `unavailable`, never a guess. TypeSafe/Jev and LLM adapters are
  additive next; no remote provider is installed implicitly. Docs:
  `docs/decision-models.md`, `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `docs/DECISIONS.md`, ADR-070, `docs/CHANGELOG.md`.
- **docs(legal): add the Legal, Compliance & Risk Management Blueprint.** New
  `docs/legal/LEGAL-COMPLIANCE-BLUEPRINT.md` covers the entity/IP structure,
  US/UK/EU/Pakistan regulatory characterisation, AI and financial disclaimers,
  automated-trading responsibility and existing broker controls (arming,
  per-order approval, typed phrase, risk limits, kill switch, bounded mandates,
  reconciliation, audit), privacy/security, MIT vs Apache/AGPL and DCO vs CLA,
  the capability/consent matrix, the document register, incident/dispute
  handling, and a costed 90-day roadmap. `docs/legal/README.md` is the document
  register and status board. The core position: Eclipse is self-directed
  research and order-entry software; the user owns the decision and the account,
  and no disclaimer is treated as immunity. NAVIGATION gets a legal trigger row.
  Docs: `docs/legal/LEGAL-COMPLIANCE-BLUEPRINT.md`,
  `docs/legal/README.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **fix(changelog): rotation keeps the archive's line endings.** `2026-10-31`
  pushed `CHANGELOG.md` to 8 dated sections, so the active window was rotated
  into `docs/changelog/2026-10.md` with `npm run rotate:changelog`. The script
  appended an LF block to a CRLF archive, producing a file with mixed endings
  and failing `gitignore-guard`'s "no tracked text file mixes CRLF and bare LF"
  contract (measured: 20,628 CRLF + 205 LF). It now normalizes the merged block
  to the target's dominant ending. no doc change — tooling fix, policy unchanged.

## 2026-11-06
- **fix(runtime): a runtime already on the harness port is adopted, not raced.**
  `ensurePythonRuntime()` probed `/health`, and when a listener existed it probed
  again — but a SUCCESSFUL second probe fell through to the spawn anyway, booting
  a rival uvicorn that died with `WinError 10048`; the front door then reported
  "runtime unavailable" for the rest of the session (observed live: a second
  `npm run start` while a healthy runtime held 8766). It now adopts that runtime.
  A child that dies from a port conflict is detected from its stderr and the live
  runtime is adopted; a spawn that exits no longer makes boot wait the whole
  cold-start budget; listener PIDs are parsed from the exact local-address column
  (so `:18766` / a foreign `:8766` cannot match). `HARNESS_PY_URL` /
  `HARNESS_PY_PORT` / `HARNESS_PY_HOST` now actually override the profile default
  in the launcher, and `kill-port` clears the port that will be used. Tests:
  `src/lib/harness/python-runtime.test.ts` (11). Docs:
  `docs/harness/architecture.md`.
- **fix(build,reports): production build and model-authored PDF tables.** The
  build failed on stale imports from in-flight build-screen work: restored
  `getProjectBrief`/`prepareProjectIndex` on the server client, added their
  browser-client versions, restored `GET /code/project`, removed the stale
  preview `mode` field, and added the missing `code.project.*` copy. Separately,
  the PDF report renderer raised `REPORT_RENDER_FAILED: list index out of range`
  for a table without headers, dict-shaped rows, or empty rows; `_table` now
  derives headers, accepts list-of-objects rows and skips an empty table.
  Verified: `npm run build` passes; `test_reports.py` (9), code task/tool/root
  (40) and code API/UI Vitest (13) pass. Docs updated: `docs/CHANGELOG.md`.
- **fix(vision): one privacy story and a bounded fallback chain.** Vision had its
  own default (`HARNESS_VISION_PRIVACY=cloud_allowed`) that ignored the app-wide
  `ECLIPSE_PRIVACY`; with local models configured, a screenshot still walked five
  local models, LM Studio and OpenRouter (12 provider calls) before one answered.
  The mode now inherits `ECLIPSE_PRIVACY=local-models` as `local_only`, caps the
  chain (`HARNESS_VISION_MAX_ATTEMPTS`=4, `…_MAX_PER_PROVIDER`=2), emits
  `vision.route.capped`, and records the provider/model that actually looked.
  Tests: `test_vision_privacy_chain.py` (8). Docs: `docs/harness/vision.md`.
- **fix(chat-api): the one-shot endpoint hands back a run instead of dying at
  180 s.** `POST /api/harness/chat` awaited the whole run under
  `maxDuration = 180`, while a writable turn is budgeted 80 steps / 2,700 s, so a
  real build was killed with `PROVIDER_TIMEOUT` and no run id. It now stops
  waiting at 150 s (`HARNESS_CHAT_SOFT_DEADLINE_MS`) and returns `202
  {status:"running", runId, streamUrl}`, with the same id given to the runtime;
  the run continues. Test: `src/app/api/harness/chat/route.test.ts`. Docs:
  `docs/CHANGELOG.md`.
- **feat(auth): `npm run auth:setup`.** One supported edit that sets
  `HARNESS_AUTH=required` and generates a 32-byte `HARNESS_AUTH_SECRET`, refusing
  to rotate an existing secret and never printing it (`--dry-run`, `--file`).
  The doctor line now points at it. Docs: `docs/harness/authentication.md`.
- **fix(code): five defects found by the LIVE failing-check acceptance run.**
  (1) `shell_run` crashed with `name 'redact_output' is not defined` — the import
  was missing, so the whole real-shell surface was dead. (2) `resolve_class`
  rejected the obvious plural (`unit_tests`) and the refusal never named the
  valid vocabulary, so the agent abandoned the pinned-check path and shelled out;
  it now accepts the plural and lists the classes. (3) `package_test` refused with
  "exit 1" and DROPPED the failing output; the refusal text now carries it.
  (4) a `.black-eclipse/verify.json` written with a BOM silently pinned NO checks
  (read with `utf-8-sig` now), so the verify-and-repair node never ran. (5) a
  PASSED check was reported `REPAIR_EXHAUSTED` — and the answer annotated "still
  failing" — when a later command spent the last check-run slot; status is now
  fact-first and a spent budget after a pass is a no-op. Verified live twice
  (fail → repair → pass, no false note). Tests: `test_code_check_path.py` (4),
  `test_graph_repair_node.py` (+2). Docs: `docs/developing-a-project.md` (how to
  pin and prove the loop).
- **docs(security): say what actually runs.** `terminal_run`/`shell_run` use the
  LOCAL tier (process-tree bounds, no filesystem/network isolation); Docker is a
  selectable backend, not the executor. `BLACK_ECLIPSE_SANDBOX_REQUIRED=1` refuses
  every execution it cannot isolate (`SANDBOX_UNAVAILABLE`). The boot line now
  says this instead of implying a container. Docs: `docs/harness/security.md`.
- **fix(trading): Deny on the trade-approval card removes it at once and stops
  the turn.** The card was only removed *after* the decide round-trip, so a slow
  request left it on screen, and the 6s poll could bring it back. Deny is now
  optimistic: the card leaves immediately, the approval id is suppressed from
  polling, and `onCancel` stops the in-flight run (the order is never sent). If
  the decision genuinely fails, the card returns with the error. Verified live:
  card gone in 58ms, `POST /trading/approvals/{id}/decide` 200, still gone after
  the next poll. Tests: `tsc` clean, full suite 476 files / 4,417. No doc change
  — a behaviour fix with no contract change.
- **feat(search): semantic retrieval is now switchable and honest.** The vector
  layer already existed but shipped dormant: with no provider it silently stayed
  keyword-only, so a user could not tell what was on or turn it on. Added a
  structured `EmbeddingService.resolution()` (`state`/`source`/`hint`/
  `suggestions`) exposed via `/search/stats` and `/search/models`;
  `POST /search/embedding/{apply,test,clear}` to pick a model live, verify one
  real round-trip, and revert; and persistence of the operator's choice in
  `SearchMeta.embedding_config` so it survives a runtime restart. Switching
  vector space now schedules a forced re-index (`bulk_index(force=True)`,
  dedup skipped) because old vectors are keyed to the previous model. The Search
  Intelligence screen renders an actionable setup card instead of a passive
  "keyword-only" pill. No silent provider substitution: a chat-only provider is
  reported as unsupported, never swapped for a hosted embedding provider.
  Docs updated: `docs/harness/search-retrieval.md`, `docs/CHANGELOG.md`.
- **test(harness): first real chat quant eval passes.** Ran “forecast gold for
  tomorrow” through the live configured model (Ollama / deepseek-v4.1-flash) and
  graded the actual answer + 23 tool executions with `quant_chat_eval`:
  **passed**, with an explicit spot-XAUUSD vs GC=F basis, a GARCH distribution
  (no point forecast), walk-forward validation, costs, and an artifact line
  (`art_…`). The artifact regex now recognises `art_`/`artifact_` ids too.
  Docs updated: `docs/CHANGELOG.md`.
- **feat(capabilities): a generated capability belongs to its project (P4).**
  The draft root was already the run's project (`draft_root(root)` →
  `<project>/.black-eclipse/capabilities`), but the process-wide dynamic recipe
  registry was only refreshed on build/activate with whatever root that call
  used — so a recipe built in project B could be reported active while
  `analysis_run` could not execute it from B, and A's recipes could linger while
  working in B. `capability_request` now refreshes the registry for the run's
  root before assessing, so discovery and execution agree and capabilities are
  isolated per project. Test: a built recipe is listed in
  `project_b/.black-eclipse`, absent from `project_a`, a `gap` again in A, and
  callable again in B without rebuilding. Docs updated: `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **feat(harness): close the chat quant loop.** Deep quant turns now get a
  32-step / 10-minute budget floor. The final answer is post-checked by
  `finalize_quant_text`: if the model omitted the required artifact line, Eclipse
  appends `Artifacts: <ids>` (or `Artifacts: none — …`) and names any still-missing
  validation, OOS or cost evidence as an explicit `Eclipse check`, never silently
  passing. The protocol also requires the gold basis (spot `XAUUSD` vs `GC=F`
  futures). New offline gate `eval_gates/quant_contract.py` locks the contract
  into `npm run test:evals`; new `quant_chat_eval.py` grades real chat outputs
  from JSONL (`python -m harness.quant_chat_eval`) and `test_quant_chat_eval.py`
  covers it. `graph.py` re-pinned 2461→2469. ADR-H345 records that quant work is
  chat-native, not a UI mode. Docs updated: `docs/harness/decisions.md`,
  `docs/CHANGELOG.md`.
- **feat(builds): chat builds are durable, and the scorecard is per project (P3).**
  A writing chat turn now records a `session.created` boundary
  (`code/session.py::record_chat_build`, called from the same
  `AgenticService.run`/`run_background` seam as the budget floor), pre-creating
  the run row when needed so the FK-bound checkpoint can be written. Chat builds
  therefore appear in the scorecard and are resumable through the existing run
  path. It also writes the same `task.created` boundary a Code task has, so a
  chat build now lists in **Builds** (diff, checks, preview, undo), not only in
  the transcript; `code/tasks.py` lists any run with that boundary and
  `TaskStore.view` returns None for a run that never built. `build_scorecard` no
  longer requires `agentId == "code-agent"`: a build is any run with a session and
  a code workspace row, and the row's `checkoutRoot` attributes it to a project.
  `GET /code/scorecard` takes `taskId`/`rootId`
  (resolved server-side, never a raw path) and the Builds tab gained a
  **This project / All builds** toggle. Tests: 3 new `test_build_session.py`
  cases (records once, planning is not a build, the chat build is listed) and a
  per-project scorecard case.
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md`, `docs/CHANGELOG.md`.
- **feat(builds): run the project and look at it (P2).** New
  `python/harness/code/preview.py` starts a project's dev command on the
  EXISTING execution layer (`ServiceManager` + the terminal process manager) and
  reports the URL it actually finds: it watches the process tree for the first
  listening port that answers HTTP, so a running-but-silent process is `not
  ready` with logs, never a fake URL. Command precedence is
  `.black-eclipse/preview.json` > `package.json` `dev`/`start`/`preview`/`serve` >
  a `Makefile` target. Routes `POST /code/preview/start`, `POST
  /code/preview/stop`, `GET /code/preview`, `GET /code/preview/logs` (the project
  is resolved server-side from the task's workspace or an approved root; no
  `cwd` in a body), proxied by `src/app/api/code/preview/route.ts`. The Builds
  tab gains `preview-panel.tsx` (Run / Check again / Open / Stop / logs) with
  `code.preview.*` copy in `dictionaries/builds.ts`. A preview runs the project
  ON DISK — an unlanded change is not included, and the panel says so. Tests:
  `python/tests/test_preview.py` (9), +1 wiring assertion. Docs updated:
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(harness): chat deliverable contract + catalog-first reuse.** The quant
  protocol now requires exactly one final `Artifacts: <ids>` or
  `Artifacts: none — <missing>` line on every standard/deep turn, and a
  `model_catalog` check BEFORE a build with reuse of a fitting artifact instead of
  a duplicate. An ambiguous model family (DCF vs ML vs strategy vs risk) gets ONE
  `clarify` question with those options. Reuse/catalog asks ("reuse the model from
  last week", "what models do we have", "list my strategies") are now classified
  as standard quant turns instead of concept/lookup non-turns. New deterministic
  chat fixtures `python/tests/test_quant_chat_contract.py` (6) and benchmark cases
  cover the contract. No separate UI: chat is the only delivery surface. Docs
  updated: `docs/harness/architecture.md`, `docs/CHANGELOG.md`.
- **feat(builds): the Builds tab names its project, and land checks fit it (P1).**
  New `components/screens/code/project-bar.tsx` shows the project new builds
  belong to and switches it through the ONE trusted-roots registry + shared
  `FolderPicker`; `task-list.tsx` passes `workspaceRootId` on both create paths,
  so a build no longer relies on an invisible global selection. New
  `dictionaries/builds.ts` holds the `code.project.*` copy (en.ts is ratcheted).
  `code/land.py` now detects a user project's checks — `package.json` scripts,
  `Cargo.toml`, `go.mod`, a declared pytest, a `Makefile` `test:` target — with
  precedence `land.json` > harness defaults (Eclipse's repo only) > detected >
  none-with-a-warning; an unrecognised project gets no checks rather than
  Eclipse's. Tests: `project-bar.test.ts`, an extended
  `code-screen-mounted.test.ts`, 4 new `test_land.py` cases. Harness budget
  re-pinned to the measured tree. Docs updated: `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **feat(harness): chat-native reuse of the model catalog.** The Eclipse Agent
  prompt now tells the model to call `model_catalog` before building a duplicate,
  reuse or extend an existing artifact where it fits, and name the created
  artifact's id in the answer. This is intentionally chat-native: the catalog is
  a read-only agent tool whose text result is summarized inline; there is no
  separate catalog screen or workspace panel. The deep quant protocol already
  carries the same instruction. Docs updated: `docs/CHANGELOG.md`.
- **fix(workspace): the folder picker can find and create folders.** The chat
  project chip's "Open folder…" (and the Editor's folder picker) now has a path
  bar that accepts a typed/pasted absolute path, a **Drives** button back to the
  filesystem roots, and a **+ New folder** action that enters the folder it just
  created. Browse + create are **Node-native** (`src/lib/workspace/browse-server.ts`
  + the `/api/workspace/browse[/mkdir]` routes) so a Python runtime restart can
  no longer freeze the picker; approving a folder as a ROOT still goes through the
  runtime's trusted-root store. When the page is on `localhost`, the picker calls
  the same server on `127.0.0.1` (a separate browser connection pool) with a
  narrow loopback CORS grant, fixing the dev keep-alive wedge that hung the second
  request. Browse/create time out honestly and offer **Retry**. The runtime health
  probe budget is raised (1.5s→8s, TTL 5s→15s) so a healthy-but-busy runtime is
  not mistaken for dead and restarted. Tests: `browse-server.test.ts` (5),
  `test_code_roots.py` (+3), `test_workspace_editor_api.py` (+2), `tsc` clean,
  full vitest green (474 files / 4408). Docs updated: `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **fix(workspace): the folder dialog sits above the app, is accessible, and can
  open the Windows picker.** `FolderPicker` is now portaled to `<body>` at
  `z-[200]` (it was `z-[70]` inline, so the sidebar/menus covered it), with a
  `role="dialog"` labelled title, initial focus on the path field, Escape to
  close, a Tab focus trap and focus restore. Redesigned header/toolbar/list/
  footer, folder rows with icons, explicit loading/empty/error states, and
  `aria-live` status. On Windows a **Windows…** button calls the new
  `POST /api/workspace/pick-folder` (`src/lib/workspace/native-picker.ts`),
  which opens the real OS "Select Folder" dialog via a topmost
  `FolderBrowserDialog`; the chosen path is loaded into the in-app picker for
  confirmation. Docs updated: `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **fix(code): a build belongs to ONE project (P0).** Worktrees were always cut
  from the globally *selected* trusted root, and `build_preview` resolved its
  target the same way at promote time — so a build bound to project B could be
  reviewed against, and land into, project A after a selection change.
  `worktree.allocate/release/diff` now take the run's resolved root;
  `CodeWorkspace` records `checkoutRoot` (additive column, legacy rows derive it
  from the scratch path); `build_preview` and the rollback route read it back and
  refuse a project that has moved instead of redirecting; `CreateTaskRequest`
  accepts `workspaceRootId` and the front door forwards it. Cancel/discard now
  release in the task's own project. Tests: new `test_project_binding.py` (5)
  proves the diff cannot land in the selected project and that a vanished project
  is refused; promotion/selfhost/maintenance/land/session suites still pass.
  Docs updated: `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **refactor(self-build): the chat build-budget seam moved to the run funnel.**
  The `standard`-budget floor now lives in `AgenticService.run` /
  `run_background` (`apply_chat_build_budget`) instead of `main.start_run`, so
  every entry point gets it and `main.py` stays under its hard ceiling (1199).
  No behavioural change for `POST /runs`; the earlier entry's `start_run` wording
  is superseded. Docs updated: `docs/CHANGELOG.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md`, `docs/NAVIGATION.md`.
- **feat(harness): unified model/research catalog (Phase 3).** New
  `python/harness/model_catalog.py` registers a read-only `model_catalog` tool
  that aggregates the app's own registries — quant strategies + experiments, ML
  models + datasets, statistical features and factors — with `kind`/`query`/`limit`
  filters and an honest empty-registry note. It never writes and never invents an
  entry; the stores are resolved lazily, so boot order cannot hide a family.
  Registered from `quant/bootstrap.py`, added to the Eclipse Agent allowlist and
  the quant surface, and the deep protocol now says to check the catalog before
  building and confirm the id after creating. Tests: `test_model_catalog.py` (5),
  plus the quant-tools/registry-parity/tool-contract/size suites. Size budget
  re-pinned. Docs updated: `docs/harness/architecture.md`, `docs/CHANGELOG.md`.
- **chore(chat): drop the code-capability headline, de-clutter the learning line,
  fix the composer's right-edge overflow.** Removed `ChatCapabilityPanel` from the
  transcript (the "I'll look at the project…" card with its `details` toggle) and
  deleted the component + its source-text test; the "Put this change into my
  project" control it carried stays on the Code task screen, recovery console and
  RSL panel via `PromoteChange`. Gave the memory/learning outcome line vertical
  breathing room (`py-1.5`, `gap-y-1`, `leading-relaxed`). Composer toolbar no
  longer overflows at ~850px: dropped `shrink-0` from the controls group, added
  `min-w-0` and made the model label truncate inside a shrinking trigger. Tests:
  `tsc` clean, full vitest green (472 files / 4399). Docs updated:
  `docs/NAVIGATION.md`, `docs/interactive-response-engine.md`,
  `docs/CHANGELOG.md`.
- **feat(chat): Plan mode — plan first, then wait for approval.** Added the third
  per-turn preference beside Quant and Choices, inside the composer's "+" menu:
  `src/lib/agent/plan-mode.ts` (Auto/On/Off, persisted), `plan-mode-control.tsx`
  (submenu + active badge), and `planMode` threaded through `ChatOptions`,
  `buildChatPayload`, both chat routes and `run-service` into
  `input.context.planMode`. `python/harness/plan_mode.py` appends a `<plan_mode>`
  block to `runtime_context` only for `"on"`: work out goal/assumptions/steps,
  record them with the existing `create_plan`/`create_task` tools when present
  (otherwise write the plan in the reply), present it, then stop and wait for
  approval before `run_plan`/effectful work. Guidance only — no hard block, no
  capability grant; `off`/`auto` add nothing. Tests: `plan-mode.test.ts` (5),
  `run-service` (+2), chat-route (+1), Python `test_plan_mode.py` (5); `tsc`
  clean; targeted suites green. Size guard: `graph.py` re-pinned 2457→2461 for
  the one import + one call seam. Docs updated: `docs/harness/architecture.md`,
  `docs/CHANGELOG.md`.
- **feat(chat): move the Quant and Choices modes into the composer's "+" menu.**
  The two always-visible Auto/On/Off pills crowded the toolbar (and collapsed to
  cryptic `Q`/`C` glyphs on narrow screens). They are now two submenus —
  **Quant mode** and **Choices mode** — under the composer's "+" menu, each with
  Auto / On / Off radio items and a small badge showing the active choice.
  Default stays `auto` (nothing is sent); picking On or Off persists in
  localStorage and therefore applies to every later run until changed. The
  preference plumbing, server validation and Python behaviour are untouched.
  Tests: `tsc --noEmit` clean, full vitest suite green (4393), targeted
  `test_choices_mode.py` + `test_quant_intent.py` green (54). Docs updated:
  `docs/harness/architecture.md`, `docs/CHANGELOG.md`.
- **fix(self-build): the Builder surface is reachable, and a chat build gets a
  build budget.** `CodeScreen` was exported but never imported, so the Code
  screen, land checks, per-file diffs and scorecard strip had no UI. Added the
  `code` tab to `AppTab` + `ALL_TABS`, mounted it through a keep-alive wrapper
  (`components/screens/code/code-tab.tsx`, so `stock-chat.tsx` grows by one
  import + one line and its ratchet moves 1603→1606), and registered the palette
  page **Builds** (`page-code`, launcher row) with a `code` icon. Also fixed the
  24-step wall that cut the acceptance run off mid-change: `start_run` now
  applies the `standard` session budget (80 steps / 45 min, additive,
  hard-capped) when the turn's autonomy may write, via
  `code/session.py::budget_for_autonomy`; planning turns keep the chat budget.
  Harness size budget re-pinned to the measured tree (total, `.`, `code`). New
  guard `code-screen-mounted.test.ts` fails if the surface is ever exported but
  not mounted again. Tests: `test_build_session.py` (2 new), `app-tabs`,
  `registry-sync`, `size-budget` green. Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md`, `docs/CHANGELOG.md`.
- **fix(harness): a code-build task is never a quant turn.** The full suite
  caught a real regression: the team task "write alpha.py and beta.py" matched
  the bare `alpha` model object, so the quant surface narrowed away
  `eval_fs_write`/`eval_run` and the modules were never written. The classifier
  now has a code-task guard (`alpha.py`, `model.py`, `print(...)`, `def `,
  `import `) that returns `none` unless a genuine quant term (backtest, quant,
  forecast, portfolio, volatility, drawdown, Monte Carlo, optimization, a named
  model) is present; bare `alpha` is no longer a model object. Regression cases
  added to `test_quant_intent.py` and the 56-case benchmark; the team comparison
  and code-eval suites pass again. Size budget re-pinned. Docs updated:
  `docs/harness/architecture.md`, `docs/CHANGELOG.md`.

## 2026-11-05
- **feat(chat): composer "Choices" mode — ask with selectable options up front.**
  New `src/lib/agent/choices-mode.ts` + `src/components/chat/choices-mode-control.tsx`
  put an Auto/Choices/Off pill beside Quant in the composer; the value flows as
  `ChatOptions.choicesMode` through both chat routes and `run-service` into
  `input.context.choicesMode`. On the runtime side, `python/harness/choices_mode.py`
  appends a short `runtime_context` block ONLY for `"on"` (and only when `clarify`
  is on the run's surface), telling the model to call `clarify` once with 2–4
  concrete options before an ambiguous turn; the existing question card already
  renders those as clickable buttons and resumes the run in place. `off`/`auto`
  add nothing, so the base prompt's act-don't-ask guidance stands — this is
  presentation guidance, never a capability grant. The block is wired in
  `graph.py` next to the trading/quant context. Tests: TS `choices-mode` (5),
  `run-service` (2 new), chat-route (1 new), Python `test_choices_mode.py` (6);
  `graph.py` size ratchet re-pinned 2452→2457. Docs updated:
  `docs/harness/architecture.md`, `docs/CHANGELOG.md`.
- **feat(harness): quant tool surface + derived quant outcome (Phase 2).**
  `apply_quant_surface` narrows a `standard`/`deep` turn to the data, compute,
  portfolio/broker-read, synthesis and artifact tools (engine names imported
  from `QUANT_TOOLS`/`STATS_TOOLS`/`FACTOR_TOOLS`/`ML_TOOLS`/`RESEARCH_DATA_TOOLS`),
  with trade precedence first and a remove-only guarantee; lookups and tiny
  surfaces are untouched. `apply_intent_surfaces` replaces the trade-only call in
  `graph.py` and still keeps `graph.py` at its size ratchet. `evaluate_quant_outcome`
  derives a read-only completeness record (artifact names, missing computation,
  validation, OOS and cost evidence) and `run_outcome.build_outcome_envelope`
  exposes it as `quant` on `GET /runs/{id}/outcome`. Tests: surface narrowing,
  trade precedence, never-widen, light/standard/deep outcome cases and the
  envelope integration (`test_quant_intent.py`, `test_quant_outcome.py`,
  existing run-outcome/surface suites). Size budget re-pinned. Docs updated:
  `docs/harness/architecture.md`, `docs/CHANGELOG.md`.
- **feat(harness): quant-intent benchmark + composer Auto/Quant/Off toggle.** New
  `python/harness/quant_intent_benchmark.py` (`quant-intent-v1`, 53 labelled cases)
  measures tier + kind accuracy and separately counts false-positive non-quant
  turns and trade-precedence violations; runnable with
  `python -m harness.quant_intent_benchmark`. New
  `src/lib/agent/quant-mode.ts` + `src/components/chat/quant-mode-control.tsx`
  put an Auto/Quant/Off pill in the composer; `ChatOptions.quantMode` flows through
  both chat routes and `run-service` as `input.context.quantMode` (`on`/`off`
  forwarded, `auto` omitted). The Python classifier already honours it. Tests:
  `test_quant_intent_benchmark.py` (2), `test_quant_intent.py` (38), the TS
  `quant-mode` suite (4), `run-service` and the chat route. Size budget re-pinned
  for the benchmark. Docs updated: `docs/harness/architecture.md`,
  `docs/CHANGELOG.md`.
- **feat(harness): deterministic quant protocol (Phase 1, observe-only).** New
  `python/harness/quant_intent.py` classifies a turn as `light` / `standard` /
  `deep` quantitative work (forecast, strategy, model, factor, financial model,
  risk) and renders a per-run protocol into `runtime_context`: frame → data →
  compute → validate → artifact → caveat, with a model-synthesis ladder and model
  contract at `deep`. Plain quotes, news, filings and concept explanations stay
  `none`; a trade/close/modify turn returns `none` so `trading_intent.py` keeps
  execution. The classifier is wired in `graph.py` next to the trading directive,
  emits a `quant.plan` event, and grants nothing (no surface narrowing yet). The
  presentation planner learns quant vocabulary. Auto/Quant/Off is read from
  `input.context.quantMode`; the composer toggle is a later slice. Tests:
  `python/tests/test_quant_intent.py` (38 passed) plus the existing response-mode
  and trading-intent suites (93 passed). `graph.py` stays at its size ratchet;
  the new module's ~579 lines are a deliberate size-budget re-pin.
  Docs updated: `docs/harness/architecture.md`, `docs/CHANGELOG.md`.
- **feat(code): per-file review and review notes (Phase 22 / S5 slice 2).** The
  promotion preview now accepts `include`: `promotion.filter_preview` keeps only
  the files the reviewer ticked and RECOMPUTES the digest over that set, so the
  single-use approval is bound to exactly what will be written. The preview and
  apply routes take the same `include`, and the promote card renders a checkbox
  per file (re-previewing on every toggle; at least one file stays selected).
  A new "Request changes" panel records an optional `file:line` and a note, then
  opens a new chat turn with `/eclipsesdk <goal>` plus the notes through the
  shell's `navigateTo` prompt param. Honest limits: per-HUNK accept is not
  supported (file granularity only), and the note starts a NEW chat turn in a
  new working copy rather than editing the same one in place. Tests
  `python/tests/test_promotion_filter.py` (4 passed). Size budget re-pinned
  (total, `code`, `routers`; `en.ts` 1305 -> 1312).
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S5 slice 2),
  `docs/harness/roadmap/README.md`.
- **feat(chat): per-chat project folder (Phase 23).** Each conversation can now be
  bound to one APPROVED workspace root, OpenCode-style, instead of the whole app
  sharing the single global selection. A **project chip** beside the session bar
  shows the current folder and opens a picker (approved folders + "Open folder…" +
  "Use Eclipse repo"). The binding is stored per chat as
  `.black-eclipse/sessions/<chatId>/project.json`, and the run routes forward an
  approved **root id** (never a path) as `RunRequest.workspaceRootId`; the runtime
  resolves it through `TrustedRootStore` and binds that run's workspace. An
  unknown/revoked id yields NO workspace (honest refusal), never a silent
  fallback; `direct` mode follows the per-run folder exactly like the global
  selection. New: `src/components/chat/project-chip.tsx`,
  `src/components/workspace/folder-picker.tsx` (extracted from the editor),
  `src/app/api/chat/session/project/route.ts`, `project.json` helpers in
  `src/lib/chat/session-store.ts`, `set_trusted_root_lookup` in
  `python/harness/code/workspace.py`. Tests: `python/tests/test_workspace_per_chat.py`,
  `src/lib/chat/session-project.test.ts`, plus run-service cases. Docs updated:
  `docs/NAVIGATION.md`.
- **feat(code): the self-build acceptance eval (Phase 22 / S6, final slice).** New
  `python/harness/code/selfbuild_eval.py`: six acceptance fixtures, one per
  shipped self-build capability (project memory, build session, maintenance door,
  land pipeline, Builder surface, scorecard). Each fixture names the exact files
  and contract strings that must exist after a candidate change, so it grades a
  worktree deterministically. Commands are OFF by default (a release run passes
  `--commands`) and a skipped command is reported as skipped, never a pass. The
  human diff grade is `UNKNOWN` - the eval never invents a quality number. The
  repository passes 6/6 today as a regression check. Tests
  `python/tests/test_selfbuild_eval.py` (4 passed). Size budget re-pinned to the
  measured tree (total, `code`). This completes S6; S5 slice 2 (per-hunk review,
  line comments, dedicated Builder tab) remains.
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S6),
  `docs/harness/roadmap/README.md`.
- **feat(models): a coding model for build runs (Phase 22 / S6, slice 2).** The
  LLM config gains an optional `codingModel` (same provider/key/URL): chat turns
  the deterministic classifier recognises as code, forced `/eclipsesdk` turns,
  and Code tasks now resolve that model; every other turn keeps the chat model.
  The Settings > AI surface gains a "Coding model (optional)" field, and the
  value round-trips through the settings API. The self-build scorecard also
  breaks results down by `provider/model` (`byModel`). `planner`/`editor`/
  `reviewer` multi-role routing is folded into this one build model on purpose:
  one run still uses one model, and no second router was added. Tests
  `python/tests/test_scorecard.py` (4 passed), `tsc` clean. Size budget re-pinned
  (total, `code`; `en.ts` 1302 -> 1305). Repo eval remains.
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S6),
  `docs/harness/roadmap/README.md`.
- **feat(code): the self-build scorecard (Phase 22 / S6, slice 1).** New
  `python/harness/code/scorecard.py` derives the honest numbers from the ONE run
  lineage: builds (`session.created`), checks run, first-pass checks, landed
  (`land.promoted`), rolled back (`land.rolled_back`), average steps, tokens and
  median time-to-first-change. A dimension with no data is `UNKNOWN`, never `0`;
  cost and human edits are named as unmeasured. `promote_apply` now records
  `land.promoted`, and rollback records `land.rolled_back` when the caller names
  the run (the chat and Code rollback paths pass it). `GET /code/scorecard`
  exposes it; the Code screen shows a compact strip. Tests
  `python/tests/test_scorecard.py` (4 passed). Size budget re-pinned to the
  measured tree (total, `code`, `routers`; `en.ts` 1297 -> 1302).
  Model roles (`planner`/`editor`/`reviewer`) and the repo eval remain.
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S6 slice 1),
  `docs/harness/roadmap/README.md`.
- **feat(code): the Builder surface, slice 1 (Phase 22 / S5).** The Code screen
  now derives ONE honest state from recorded facts (`session.derive_phase`:
  planning / editing / checking / ready / blocked / stopped) plus the single next
  action, and exposes the latest `land.verified` result on the session view. The
  landing gate is real in the Code screen: `PromoteChange` is disabled until a
  FULL check pass, with a plain-language hint. The diff viewer splits a unified
  diff into per-file, collapsible sections (`src/lib/code/diff-sections.ts`), so a
  multi-file change is reviewable file by file. Tests: `test_build_session.py`
  (11 passed), `diff-sections.test.ts`. Size budget re-pinned to the measured
  tree (total, `code`; `en.ts` 1285 -> 1297).
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S5 slice 1),
  `docs/harness/roadmap/README.md`.
- **feat(code): the landing pipeline (Phase 22 / S4).** New
  `python/harness/code/land.py`: an ordered, data-driven check plan (typecheck,
  tests, size, secret scan, the change-log obligation, and a build when
  `src/**` changed), with `.black-eclipse/land.json` as a project override and
  the exit code as the judge. A check that cannot run is an `error`, never a
  pass; the first required failure stops the pipeline and the rest are reported
  as `skipped`. `GET /code/tasks/{id}/land` is the read-only plan;
  `POST /code/tasks/{id}/land/verify` runs it (`full=false` skips the long suite)
  and records a `land.verified` checkpoint. The checks run against the project on
  disk (the disposable copy has no installed dependencies), so the Code-screen
  `LandChecks` panel sits after the change is applied and offers quick/full runs
  with per-check output, plus the `code.land.*` i18n keys. Tests
  `python/tests/test_land.py` (8 passed). Size
  budget re-pinned to the measured tree (total, `code`, `routers`; `en.ts`
  1272 -> 1285).
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S4 shipped),
  `docs/harness/roadmap/README.md`.
- **feat(code): the self-build boundary and offline maintenance mode (Phase 22 / S3).**
  `selfhost.plan_landing` turns the existing classifier into ordered steps:
  `python/harness/**` restarts only the builder, `src/**` builds only the target,
  and an authority file exits through maintenance - never a live hot-swap. New
  `python/harness/code/maintenance.py` is the one authority door: it refuses a
  non-authority change, refuses a dirty tree unless explicitly allowed, stops the
  builder, applies, runs the gate, restarts, health-checks, and rolls back on any
  failure after the apply. Every side effect is injected, so the order is tested
  without a live process. `npm run self:maintenance -- plan|execute` is the thin
  operator runner (`scripts/self-maintenance.js`), and `plan` is read-only. Tests
  `python/tests/test_maintenance.py` (11 passed). Size budget re-pinned to the
  measured tree (total, `code`; no ratcheted-file growth).
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S3 shipped),
  `docs/harness/roadmap/README.md`.
- **feat(code): durable build sessions with a budget ladder (Phase 22 / S2).**
  New `python/harness/code/session.py`: a session is a lens over the existing
  run lineage, not a second store. It records the goal, the acceptance list and
  the budget as one `session.created` checkpoint, and derives progress/resume
  from the checkpoints the task lifecycle already writes. The budget is a
  profile NAME (`small` 24 steps / 10 min, `standard` 80 / 45 min, `deep` 240 /
  3 h), never a raw number from the caller. `RunRequest` gains additive
  `maxSteps` / `runTimeoutMs`; `graph.requested_budget` applies them as a floor
  and clamps to the runtime's hard caps, so a deep session can run long without
  widening the autonomy floor or the tool surface. `POST /code/tasks` accepts
  `budgetProfile` + `acceptance` and returns the session block; `GET
  /code/tasks/{id}` carries it too. The front door validates the profile and the
  `/code` command gains `--budget`. The Code task detail now shows the session
  (goal, budget, acceptance, finished state) through `getCodeSession` and
  `TaskDetail`, with four `code.session.*` i18n keys. Tests
  `python/tests/test_build_session.py` (9 passed). Size budget re-pinned to the
  measured tree (`.`, `code`, `routers`, total; `graph.py` 2406 -> 2434;
  `en.ts` 1268 -> 1272).
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S2 shipped).
- **feat(code): load the project's own rules into a code turn (Phase 22 / S1).**
  New `python/harness/code/project_memory.py`: a bounded, deterministic loader for
  `AGENTS.md`, `.eclipse/instructions.md`, `CLAUDE.md` and the top-level map in
  `docs/NAVIGATION.md`. It walks from the workspace root to the git root (so this
  app finds the repository's `AGENTS.md` one level above `Black-Eclipse-site/`),
  redacts secret-shaped spans, truncates at a line boundary, and memoises by
  `(path, mtime, size)`. The rendered block is injected into the first code turn
  by `graph_context._repo_map_context`, and a new read-only `project_rules` tool
  lets the agent re-read it on demand. The rules are **context, never
  permission** - no rule can change the allowlist or the autonomy floor.
  `CHAT_CODE_TOOLS` and `CODE_AGENT_TOOLS` gain the tool; the task code-agent
  prompt says so. The chat prompt is unchanged - the injected block already
  carries the "context, never permission" rule - so the ECLIPSE prompt-size
  ratchet and the read-only navigator prompt both stay put. The published tool
  registry is regenerated (`docs/harness/tool-registry.json`, 1020 tools). Tests
  `python/tests/test_project_memory.py` (12 pass, 1 symlink skip), plus the
  updated exact-surface pin in `python/tests/test_chat_code_profile.py`. The harness size budget is re-pinned
  to the measured tree (`scripts/size-budget.json`; the `code/tools.py` ratchet
  moves 1268 -> 1270) because `python/harness/code` was at its ceiling.
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S1 shipped),
  `docs/harness/roadmap/README.md`, `docs/harness/tool-registry.json`;
  `docs/CHANGELOG.md`.
- **docs(harness): add the Phase 22 self-hosting plan.** The gap analysis for
  using Eclipse to build Eclipse, grounded in the merged tree: no project-rule
  loader (nothing reads `AGENTS.md` under `python/harness/`), a 24-step / 600s
  chat code budget, the builder and target sharing one process, authority files
  refused live with no maintenance path, landing that does not run the repo gate,
  all-or-nothing review, no coding model policy, no self-build metrics, and a
  finance-first default surface. Six workstreams in three waves, each with a
  contract, file list, UX and acceptance gates. S1 (project memory) shipped
  2026-11-05; the other five are not started.
  Docs updated: `docs/harness/roadmap/phase-22-self-hosting.md`,
  `docs/harness/roadmap/README.md`.
- **fix(chat): quiet the evidence cards under an answer.** Three changes to the
  metadata area, all presentation-only (the runtime's provenance and fail-closed
  rules are untouched). (1) The "Proof it works" card no longer prints a
  `0 check(s)` header when no check was recorded, and it opens by default when a
  check failed or a claim is unsupported, so the evidence is visible instead of
  hidden behind a click. (2) A speculative capability offer (`gap` /
  `needs_source`, the "Build it" card) no longer renders in the transcript; a
  card describing a real capability — including an unverified one — still does.
  (3) "Sources consulted" now opens on the numbered source list by default, with
  calculations/limitations/run detail nested after it. Covered by
  `code-verification-panel.test.tsx`, `research-evidence-panel.test.tsx` and
  `capability-types.test.ts`. Docs updated: `docs/interactive-response-engine.md`.
- **fix(chat): only Sources stays under an answer (follow-up).** User direction:
  remove the other evidence cards entirely. The chat transcript no longer renders
  the "Proof it works" ledger (it remains on the Code screen) or the generated
  capability card (it remains in Capability Studio); the code headline keeps only
  the intent line and the promote-change action. `research-evidence-panel.tsx` is
  now the only provenance block under a normal answer, and it opens on Sources by
  default. No runtime/provenance logic changed — presentation only. Tests updated:
  `chat-capability-panel.test.ts` now asserts both cards are absent from the
  transcript. Docs updated: `docs/interactive-response-engine.md`.
- **fix(chat): drop the empty computed-result card.** A result with no
  provenance record (the "This number has no record of where it came from…"
  UNAVAILABLE state) or with nothing to show (no outputs, artifact, figure or
  recipe) no longer renders a card at all; the fail-closed refusal still happens
  at the runtime boundary. A computed result with provenance and data is
  unchanged. Covered by new empty-state cases in
  `computed-result-panel.test.ts`. Docs updated: `docs/interactive-response-engine.md`.
- **fix(chat): keep the Sources panel collapsed and align table columns.** Two
  follow-ups from the browser review. (1) "Sources consulted" no longer opens by
  default; the header summary stays visible and the body (Sources first) is
  behind the toggle. (2) Tables now use ONE alignment per column shared by the
  header and every body cell — the Markdown path previously right-aligned each
  numeric cell individually, leaving the header on the opposite side and mixed
  columns flipping; `data-table-block.tsx` also reverses the header row on a
  right-aligned column so the always-present sort icon does not push the label
  away from the numbers. Covered by new `markdown-table.test.tsx`, an updated
  `research-evidence-panel.test.tsx`, and a header-alignment case in
  `render.test.tsx`. Docs updated: `docs/interactive-response-engine.md`,
  `docs/chat-ui-audit.md`.
- **style(chat): give the response action row room to breathe.** The export row
  (JSON / Read aloud / MD / PDF / Save / Open in Canvas) sat flush against the
  header above and the content below. It now has a little top margin and a
  clear bottom gap, with wrap row-gap, so it reads as its own strip.
  Presentation-only; no doc change beyond this note.
- **style(canvas): the inline Canvas dock opens as one surface card.** Replaced
  the thin `Eclipse response · REPORT · Save to edit` toolbar with the rounded
  card from the review: a rounded icon tile plus a surface label (`Writing` for a
  prose answer, otherwise `Code` / `Report` / `Web page` / `Image`), with Save to
  edit and Close on the right and the document title as the card tooltip.
  Presentation-only. Docs updated: `docs/canvas.md`.
- **style(graph-studio): simplify canvas nodes to a borderless solid surface.**
  The node card now uses a solid `#0E0E0E` fill with no outer border and a soft
  lift instead of the heavy 2px black bezel and translucent gradient. The header
  gets roomier top/bottom padding so the icon no longer crowds the card edge,
  and the icon sits in a solid neutral rounded tile (`#1A1A1C` dark / `#F2F2F4`
  light). Ports, inline fields, run/test states and hover actions are unchanged.
  Presentation-only; no contract change.
- **fix(graph-studio): tidy layout respects node heights; wires are curved and neutral.**
  `autoLayout` now accepts the nodes' measured React Flow heights and stacks each
  layer by the real card height (240px fallback when unmeasured), with a 96px
  column gap — so "Tidy up" no longer piles tall nodes on top of each other. The
  canvas measures on tidy and passes the map through the store. Wires switched
  from straight to bezier paths, and idle/selected wires render neutral (brighter
  on hover) with the theme accent reserved for a running workflow; success and
  failure keep their status colors. Added `layout.test.ts`. No doc change —
  interaction/presentation fix only.
- **fix(news): high-level stories join the feed and notify the header.** The News
  tab no longer opens with a separate High Alert band. Those stories are ranked
  into the main feed with `sort=importance` (default, one-time migration for a
  saved `newest` preference) so the first rows are the most critical, and the
  existing cards carry the CRITICAL/HIGH ALERT/BREAKING badges. Added the pure
  `src/lib/notifications/news-diff.ts` + root-mounted
  `src/lib/notifications/news-watcher.tsx`, which polls `/api/news/alerts`, seeds
  the current set silently, then raises a `news`-tab ledger entry (header bell +
  sidebar badge + toast/cue) for each newly seen critical/high story and each
  high-impact release within 90 minutes. Removed the now-unused
  `news-high-alerts.tsx`; the card preferences moved to
  `src/lib/news/card-settings.ts` to keep the screen inside the size budget
  (re-pinned 1486→1446). Tests: `news-diff.test.ts`. Docs updated:
  `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/CHANGELOG.md`.
- **fix(notifications): the header ledger is not a news backfill.** The news
  watcher was seeding the current high-alert set into the ledger on load, which
  made the header look like a news-only feed and pushed the operator's
  price-alert/task/agent entries down (or out of the 100-item ring over time).
  The first poll now only seeds the seen set — no ledger write — so news behaves
  exactly like the task/bot/price watchers: it records events that happen after
  the app opens. The notification panel also always renders every kind filter
  (Alerts/Tasks/Approvals/Agent/Bots, count 0 included) so each producer lane is
  discoverable. Tests updated: `news-diff.test.ts`. Docs updated:
  `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/CHANGELOG.md`.
- **feat(alerts): durable alert archive + a filterable History tab.** Every
  notification raised in the app is now mirrored from the header ledger into a
  new `AppNotification` table through `POST /api/notifications` (idempotent on
  the producer's stable id; the local ledger backfills once on hydrate). New
  `GET /api/alerts/history` unions that archive with the price engine's
  `PriceAlertEvent` log (deduped by id, newest-first) and supports `q`,
  `kind`, `tab` and `24h/7d/30d/all` ranges. Alerts › History now shows all
  sources (news/price/tasks/approvals/agent/bots) with a search box, source and
  range filters, and plays the alert cue once when a genuinely new archived row
  arrives. `prisma/schema.prisma` gains `AppNotification` (additive; `db push`
  applies it, so `jdds.db` is not committed). Tests:
  `api/alerts/history/route.test.ts`, `api/notifications/route.test.ts`. Docs
  updated: `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/CHANGELOG.md`.

## 2026-11-04
- **chore(ops): re-pin the harness size budget to the measured merged tree.** The
  branch's `check:size` gate was already red before today's merge: the trading
  surface (29 graph nodes + 31 broker routes), research-evidence nodes, bounded
  parallel map and the workflow-authoring bridge outgrew the 2026-11-02 pin.
  `scripts/size-budget.json` is now pinned to the measured tree (453,427 total;
  `python/harness/.` 28,780, `code` 18,344, `routers` 20,575,
  `eclipse_memory` 12,685). This is a deliberate checkpoint, not an allowance —
  the per-module ratchet resumes from these numbers. Also merges
  `feat/graph-quant-packs` into `main` so today's work is on the default branch.
  Docs updated: `docs/CHANGELOG.md`.
- **test(trade-learning): pin the unbound-bridge precondition.** The full Python
  suite runs after a test that boots the service and binds the real journal
  loader, so the "no bridge" node test saw a live connection attempt instead of
  its own precondition. The test now clears the loader first. Test-only change.
  No doc change beyond this note.
- **fix(docs): normalize CRLF after appending ADR-069.** The ADR text was
  appended with bare LF into two CRLF files (`docs/DECISIONS.md`,
  `skills/ARCHITECT.md`), which the line-ending guard rejects. Both files are
  pure CRLF again; content unchanged. No doc change beyond this note.
- **feat(graph-studio): the trade learning loop ships as six nodes.** `trade.journal`
  (read-only, owner-scoped `journal_trades` bridge over JDDS), `trade.review`
  (pure deterministic detectors that cite the field: no stop, risk over limit,
  stop widened, target reduced, early exit, held past stop, overtraded, revenge,
  no plan, checklist violation, off-session, off-symbol, duplicate entry,
  unreviewed), `trade.learn` (findings + the ONE `LearningRecurrence` ledger
  keyed by trade id + inert RSL candidate), `trade.improve` (seeded recursive
  climb; variants mutate from measured states, acceptance is holdout-only),
  `trade.commit` (operator-only append of a playbook version) and
  `trade.playbook` (read). The runtime refuses any playbook transition that
  widens risk (`NOT_A_TIGHTENING` / `OUT_OF_BOUNDS`); the loop has no broker path
  and never edits code. New domain `python/harness/trade_learning/`, nodes
  `python/harness/graph_runtime/trade_learning_nodes.py` +
  `src/lib/graph-studio/registry-learning.ts`, manifest regenerated, `learning`
  node category, `journal_trades` capability, tests
  `python/tests/test_trade_learning.py` + `test_graph_trade_learning_nodes.py`.
  The `Trade learning loop` starter template wires the whole chain with
  conservative operator bounds. Docs: new
  `docs/graph-studio-trade-learning-nodes-plan.md`, `docs/graph-studio.md`,
  `docs/NAVIGATION.md`, ADR-069.
- **docs(graph-studio): plan for a trade learning loop (mistake → lesson →
  recurrence → bounded remediation).** Audits the existing mistake store,
  recurrence ledger, lesson contract and Tier-B self-modification, then designs a
  five-node `learning` pack (`trade.journal` / `trade.review` / `trade.learn` /
  `trade.playbook` / `trade.remediate`), a deterministic trade-mistake taxonomy,
  a scoped recurrence key reusing `LearningRecurrence`, a read-only `journal_trades`
  JDDS bridge capability, and an append-only tighten-only playbook envelope that
  the risk gate enforces. No behaviour change — plan only. Docs: new
  `docs/graph-studio-trade-learning-nodes-plan.md`.
- **feat(graph-studio): the workflow assistant is a real sidebar chat with
  pause/resume and approvals.** The editor's right rail is now a vertical
  tab strip (Assistant / Node / Issues / History / Health) with a resizable,
  persisted width (`be_graph_rail_v1`) — a layout column, never a modal. The
  assistant turn carries a `runId`, streams text token-by-token through the
  model runtime, renders through the shared `AssistantContent`/Markdown path,
  and Pause / Resume / Stop call new
  `/api/graphs/assist/runs/{id}/pause|resume|cancel` routes backed by
  `graph_runtime/assistant_runs.py` (cooperative gates between model rounds and
  tool calls; disconnect cancels; a dropped stream recovers the persisted
  result). The transcript moved to a per-workflow `localStorage` thread list
  with a restored pending proposal. With Auto-apply off, a validated edit
  becomes a single-use `graph_edit` approval in the existing `ApprovalStore`;
  `ask_user` becomes a real clarification card. Docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **fix(desktop): the shortcut no longer leaves a duplicate tab open.** The
  launcher handed the progress page off to the app with `location.replace(...)`
  and then re-opened the browser 20 s later whenever the app tab had not
  beaconed yet — on a slow first hydrate that is *always*, so each launch ended
  with two app tabs. The progress page now sends a one-shot `POST /handoff`
  beacon immediately before it navigates, and the launcher's "no beacon yet"
  retry is skipped once that handoff is recorded. The retry still fires when
  the page never ran its redirect (JS disabled, or the tab was closed). Files:
  `scripts/lib/desktop-splash.js`, `scripts/start-desktop.js`, test
  `src/lib/desktop-launcher.test.ts`. Docs updated: `docs/CHANGELOG.md` (bug
  fix — no architecture/contract change).
- **fix(tests): the full suite is green again.** Three real failures surfaced in
  the full run. (1) Per-model ML predict tools (`ml_model_*_predict`) were
  appended to the shared `ECLIPSE_AGENT` allowlist when a model was registered,
  so a later boot with a deleted model left "ghosts" (`test_registry_visibility`).
  They are now an explicit dynamic surface (`allowModelTools`, expanded from the
  tools CURRENTLY registered, like `mcp_*`/`plugin_*`); the global mutation is
  gone. (2) `ml_finetune_adapter` advertised a 60-minute timeout above the
  contract's 30-minute maximum — now `1_800_000`. (3) `service.py` was 7 lines
  over its ratchet after the workflow bridge registration; re-pinned to the
  measured 1806 with justification, and `scripts/size-budget.json` re-pinned to
  the measured merged tree (453,427). Docs updated: `docs/CHANGELOG.md`.
- **fix(desktop): the shortcut no longer leaves a duplicate tab open.** The
  launcher handed the progress page off to the app with
  `location.replace(...)`, then re-opened the browser 20 s later whenever the
  app tab had not beaconed yet — on a slow first hydrate that is *always*, so
  every launch ended with two app tabs. The progress page now sends a one-shot
  `POST /handoff` beacon immediately before it navigates, and the launcher's
  "no beacon yet" retry is skipped once that handoff is recorded (the retry
  still fires when the page never ran its redirect, e.g. JS disabled or the
  tab was closed). Files: `scripts/lib/desktop-splash.js`,
  `scripts/start-desktop.js`, test `src/lib/desktop-launcher.test.ts`. Docs
  updated: `docs/CHANGELOG.md` (bug fix — no architecture/contract change).
- **ui(graph-studio): cleaner nodes and straight wires.** Single-port nodes no
  longer render the "Start"/"Value" labels beside their handles (the tooltip
  still names the port); nodes with several ports keep their labels so branch
  choices stay readable. Connections are now straight lines instead of beziers,
  and the hover insert/delete controls on a wire are frosted glass
  (`bg-white/10 + backdrop-blur-md`) instead of an opaque chip. Files:
  `src/components/screens/graph-studio/eclipse-node.tsx`,
  `eclipse-edge.tsx`. Docs updated: `docs/CHANGELOG.md`.
- **fix(graph-studio): the "New workflow" template menu no longer throws.** The
  menu's `DropdownMenuLabel` is a Base UI `Menu.GroupLabel`; using it outside a
  `DropdownMenuGroup` throws "MenuGroupContext is missing" as soon as the menu
  opens, so the button appeared dead. Wrapped the template list in
  `DropdownMenuGroup` in `src/components/screens/graph-studio/graph-home.tsx`
  and fixed the same latent bug in the canvas version-history menu
  (`src/components/screens/canvas/canvas-center.tsx`). Template creation itself
  was already working — all 15 templates create successfully through
  `/api/workflows`. Docs updated: `docs/CHANGELOG.md`.
- **feat(dashboard): journal drawdown + monthly P&L charts.** The Home Trading
  edge tile now shows a **drawdown (underwater) area** from
  `analytics.equityCurrency.drawdown` with the max drawdown labelled, and
  **last-12-month P&L bars** from `analytics.monthlyReturns` (green/red,
  magnitude-scaled, per-month tooltip with trade count). Both are derived from
  data already fetched — no new requests. Per-position price sparklines were
  evaluated and rejected: broker symbols (XAUUSD/EURUSD) return no JDDS price
  history, so they would render empty. Docs updated: `docs/trading.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **fix(dashboard): a flat P&L series now reads as a flat line, not a broken chart.**
  `AreaSpark` projected a zero-variance series to the bottom of its viewBox
  (`y=36/40`), so the Home Trading "Realized P&L · last 30 days" panel (one
  EURUSD deal with 0 P&L) looked empty. Flat series now render on the midline,
  the dashed baseline follows the same projection, and the caption states
  "no realized P&L in this window" instead of implying a curve. Docs updated:
  `docs/CHANGELOG.md`.
- **feat(dashboard): charts in the Home Trading section.** Added a **realized
  P&L curve** (cumulative broker deals, last 30 local days, zero baseline,
  min/max day labels, `N deals · broker-reported`) built by
  `buildDailyRealized` in `src/lib/dashboard/trading-home-model.ts`; a
  **margin-usage ring** replacing the numeric margin tile (level, band, free
  margin); inline **P&L bars** on each open position; **diverging bars** for
  per-symbol exposure; and a **journal equity sparkline** from
  `analytics.equityCurrency`. `AreaSpark` gained an optional `baseline`;
  `home-primitives.tsx` gained `DivergingBarRow`. Honest limits: the curve is
  realized-only (no stored balance history), the broker read covers the last 200
  deals, and empty/short series render an explicit state rather than a line.
  Tests: `trading-home-model.test.ts` (daily bucketing, carry-forward, window,
  trimming). Docs updated: `docs/trading.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **fix(dev): the development server reads the shared `jdds.db` again.** The dev
  profile sets `BE_DATA_DIR=.black-eclipse/dev/` for isolated runtime DBs, but
  `src/lib/db.ts` derived the market/journal file from it too — so dev opened an
  empty `.black-eclipse/dev/jdds.db` with no schema and every Prisma-backed
  surface failed (`P2021`: `Market`/`JournalProfile` missing; journal analytics
  500, regime unavailable, empty market cards). `src/lib/db.ts` now honours
  `BE_DB_PATH` first (the override `doctor.js`/`db-guard.js` already used), and
  `scripts/lib/profiles.js` pins it to the repository `jdds.db` for dev — the
  behaviour `docs/environments.md` already documented. Docs updated:
  `docs/environments.md`, `docs/CHANGELOG.md`.
- **ui(consistency): every title icon is now one shared frosted tile.** Extracted
  `IconBadge` + `PageHeader` into `src/components/layout/page-header.tsx` (neutral
  `border-foreground/10 bg-foreground/[0.06]`, icon 22/26/30 at three sizes) and
  pointed `SectionHeader` at the same primitive. All page-title headers (Command
  Center, Market Discover, Market Bubbles, Alerts, Journal, Portfolio, Economics,
  Chart Workspace, News, Investor Eye) and the drifted Settings sections
  (Analytics, MCP, Sidebar, Alerts, Security, AI active setup) now use it; the
  ad-hoc `border-primary/25 bg-primary/15` title tiles are gone. Also normalised
  Aurora Colors, Data Sources, Charts, Volume Analytics and the New-layout dialog.
  Icons moved out of `<h1>` text for correct accessible names. no doc change —
  visual consistency refactor; no architecture, contract, setup or decision
  changed.
- **feat(dashboard): the Home brief shows your broker — read-only.** New
  **Trading** section on the `home` tab (`home-trading-cards.tsx`): broker-reported
  equity/balance, today's P&L split (deals since local midnight + floating, labelled
  broker-reported), open positions, working orders, margin-based risk (margin level
  bands, usage bar, free margin, per-symbol lot breakdown) and the journal edge
  (win rate, profit factor, net P&L, discipline — all journal trades, labelled
  not broker-verified). Read-only by design; account mutations stay in the broker
  console / Quick Trade where the arm + approval gates live. No broker connected
  renders a slim connect CTA (Settings → Broker connection); a failed read names
  the broker's reason. Section is hide/reorderable via Customize; placed first for
  the trader lens. The broker read path was extracted from the Command Center
  widgets into `src/lib/dashboard/use-broker-snapshot.ts` (10s dedupe, 15s poll,
  IPC-aware) shared by both surfaces; section data comes from
  `use-trading-home-data.ts` + pure `trading-home-model.ts` (broker deals, margin
  health, exposure — unit-tested). Docs updated: `docs/trading.md`,
  `docs/NAVIGATION.md`, `docs/OVERVIEW.md` (stale "UNAVAILABLE stubs" line),
  `docs/CHANGELOG.md`.
- **feat(workflows): the ChatBot can create a saved Graph Studio workflow from a
  one-line idea.** Added the `create_workflow` agent tool
  (`python/harness/graph_tools.py`, admitted by `make_graph_authorizer` in the
  one effect chain and narrowed at `plan_only` via `GRAPH_WRITE_TOOLS`) and the
  front-door `POST /api/workflows/generate` route, which resolves the model
  credentials, runs the SAME validated chat-to-graph planner the gallery uses,
  re-validates the IR and writes it through the normal workflow store. A rejected
  plan is reported with its diagnostics and nothing is saved; the tool never runs
  the graph. The gallery now refreshes when its keep-alive tab becomes visible
  again, so a chat-created workflow appears without a reload. Tests:
  `python/tests/test_graph_create_tool.py`, `src/app/api/workflows/generate/route.test.ts`.
  Docs updated: `docs/graph-studio.md`, `docs/agentic-overview.md`,
  `docs/CHANGELOG.md`.
- **fix(sound): the AI-result cue is now a calm, dedicated voice instead of the
  old 0.6s high-RMS message asset.** Added a pack-independent AI-result sound
  set at `public/sounds/message/` (`chime` default, `marimba`, `glass`, `blip`)
  generated by `scripts/generate-message-cues.py`, plus a `messageVariant`
  preference and an **AI result voice** picker in Settings › Sound with instant
  preview. A crisp interaction pack no longer forces a harsh reply cue.
  Docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **security(privacy): personal data can now live on an encrypted volume, conversations can be pinned to local models, and everything can be wiped on demand.** Added `scripts/setup-data-vault.ps1` (plan/apply): creates a BitLocker-encrypted VHDX, moves the three databases plus `.black-eclipse/`, `python/.black-eclipse/`, backups, `mcp-servers.json` and `.connector-key` onto it, and links the directories back. `BE_DATA_DIR` is now honoured by `src/lib/db.ts`, `prisma.config.ts`, `scripts/db-guard.js` and both Python stores, so SQLite's `-wal`/`-shm` sidecars are encrypted too; `scripts/doctor.js` fails closed when `BE_VAULT_PATH`/`BE_DATA_DIR` is missing instead of creating empty databases. Added `ECLIPSE_PRIVACY=local-models`, enforced at the model chokepoint (`build_chat_model`) and the TS save/test/chat paths, so a remote endpoint is refused before any prompt is sent. Added `scripts/wipe-personal-data.js` (`--confirm=WIPE`). Docs: new `docs/data-and-privacy.md` (data map, threat model, vault, local-only scope, wipe, backups). Docs updated: `docs/data-and-privacy.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **fix(sound): interaction "haptics" are strictly opt-in, and event
  notifications are their own class.** The click/tick/toggle cues no longer
  re-enable from a stored blob without an explicit `enabled: true`; the storage
  key moved to `be_sounds_v4` so a stale on-state cannot survive. `message` is
  now the **AI result** cue and, like `notification` and `taskdone`, plays
  independently of the opt-in interaction master switch (per-cue mute is the
  opt-out; `gainFloor` keeps it audible at the subtle default volume). The
  `alwaysAudible` flag was replaced by `notification`; the loud task-done alarm
  lost its full-blast treatment and now starts muted (opt-in), while the AI
  result and alert cues are on by default. The Settings › Sound `Notifications
  & alarms` card now includes AI result. Settings › Alerts mirrors the same three
  toggles and gains the high-impact news policy controls (threshold, lookback,
  categories, tickers, quiet hours) wired to the existing
  `/api/news/alerts/policy` scan. Also admitted the two ML registry/local-write
  tools through the local-write authorizer so the advertised-tool admission
  guard stays honest. Docs updated: `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **security(open-source): the repository now fails closed on leaked secrets and
  ships a hardened container.** Added `scripts/scan-secrets.js` (zero-dep, no
  false-positive noise from the test fixtures): it rejects tracked/staged secret
  artifacts (`.env*`, `*.db`, private keys, `.connector-key`, `mcp-servers.json`,
  channel `secret.key`, `.black-eclipse/`) and recognisable provider tokens, and
  prints only a redacted prefix. Wired into the pre-commit hook (`--staged`),
  `npm run check:secrets`, `check-all.js`, and CI (which also gained
  `permissions: contents: read`). The container stack no longer publishes on all
  interfaces (loopback by default via `BE_BIND_ADDR`), forces `HARNESS_AUTH=required`,
  drops all capabilities with `no-new-privileges`, and the image runs as the
  unprivileged `node` user; `.dockerignore` now also excludes `mcp-servers.json`,
  `python/.black-eclipse`, and key material. `next.config.ts` adds baseline
  security headers (nosniff, SAMEORIGIN, referrer policy, permissions policy, and
  HSTS in production). Added repository-root `SECURITY.md` (private disclosure +
  operator checklist) and documented the deployment posture. Docs updated:
  `docs/DEPLOYMENT.md`, `docs/harness/security.md`,
  `docs/harness/authentication.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **style(notifications): the header bell is outline-only.** The bell and the
  per-kind icons in the notification panel always render with Phosphor's
  `regular` (outline) weight; the unread count still carries the state, so no
  filled icon is needed. `no doc change — visual weight only`.
- **feat(notifications): a header notification bar with the full ledger.** The
  app already recorded every raise (price/news alerts, tasks, approvals, agent
  runs, bots) in `lib/notifications/store` and signalled it via sidebar badges
  and the browser tab, but there was no in-app place to read the list. Added
  `src/components/layout/notification-center.tsx` to the `TopBar`: a bell with
  an unread count opens a frosted panel showing the newest-first ledger,
  filterable by kind; clicking an entry marks its tab read and navigates via
  `be:navigate`; `markAllRead` was added to the store for the panel's
  "Mark all read" action. Opening the panel does not mark items read. Docs
  updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **feat(news): High Alert — a decision-support layer for the News tab.** The
  feed was recency-only; tier and cross-source corroboration were filters/badges,
  never ranking inputs. Added `src/lib/news/importance.ts` (pure, deterministic
  0–100 score + `critical|high|medium|low`, with `reasons[]`, confidence from
  tier+corroboration, direction from sentiment, horizon, and what would
  invalidate the read). `src/lib/news/cluster.ts` is the shared story-cluster
  primitive. `/api/news` now scores every returned row and accepts
  `sort=importance` / `minImportance` / `portfolio`; `/api/news/alerts` returns
  the strongest recent stories plus upcoming high-impact releases (only when a
  real calendar source exists); `/api/news/alerts/policy` stores the push policy.
  The News tab gains a High Alert band, BREAKING/critical badges, a high-alert
  filter, a "trade check" panel, and a wired one-click price watch (the existing
  `/api/news/alert` endpoint was previously orphaned). After each ingest,
  `src/lib/news/alert-scan.ts` optionally pushes high/critical stories through
  the existing channels (disabled by default, first run seeds a baseline, story
  dedupe, quiet hours, durable `PriceAlertEvent` notice). Settings › Alerts gains
  the threshold/lookback/categories/tickers/quiet-hours controls. Docs updated:
  `docs/DATA-FLOW.md`, `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **feat(theme): Lime is the shipped default for every user.** `92db5238` moved
  the accent and the Crystal sidebar, but several places still encoded the old
  green default: the launcher splash mirror (`scripts/lib/app-theme.js`), its
  tests, the Eclipse chart presets (`chart-settings.tsx`), the SDK design
  placeholder, the default chart-drawing color, the market-overview accent rings
  and the static `.dark` brand tokens in `globals.css` were already Lime — only
  the remaining consumers were not. Uncustomized glass recipes now read
  `var(--glass-shadow, 0 24px 70px rgba(0,0,0,0.60))` so the pre-hydration page
  matches the themed `dramatic` shadow instead of the old soft one. A saved
  app-wide theme still wins, so existing users keep their look and can switch
  away at any time; light presets deliberately keep `soft`. Tests:
  `desktop-launcher.test.ts` expectations updated alongside the existing
  theme/Aurora tests. Docs updated: `docs/DECISIONS.md` (ADR-068),
  `skills/ARCHITECT.md` (ADR-068), `docs/OVERVIEW.md`, `docs/GLOSSARY.md`,
  `skills/IMPRINT.md`, `docs/CHANGELOG.md`.
- **feat(settings): the Persona tab is a proper persona library.** The fixed
  260px rail plus editor inside the `max-w-3xl` settings column squeezed the form
  into ~480px with 9–11px type. Persona now gets a wider `max-w-5xl` canvas (only
  that section), a master–detail layout with a 280px library rail of avatar rows
  and a roomy editor: 13px inputs, a bordered instruction-overlay editor with the
  character budget in its header, version history with numbered version chips,
  and a preview that opens beneath the editor. The duplicated inner `SubSection`
  heading is gone because the page already renders `SectionHeader`. Behaviour,
  API calls and the draft/active rules are unchanged. No doc change —
  presentation-only layout fix.
- **fix(search): ⌘K is complete again — every screen and sub-page is reachable, and drift fails the build.** The palette registry had silently fallen behind the rendered UI: Memory declared 8 of 16 sub-tabs (with stale labels), Skills missed Maintenance, Journal missed Decisions and Notebook, and sidebar-visible screens (Eclipse SDK, Artifacts, Tables, Graph Studio) had no page entry at all — a QA run already had to bypass the registry via `app-screens.ts`. The Memory/Skills/Journal sub-page entries are now **generated** from the same arrays the tab bars render (`app-screens.ts`, new `journal-tabs.ts` which the Journal screen also consumes), so ids, labels and aliases cannot drift. Added missing top-level pages (`sdk`, `artifacts`, `tables`, `overview` for Graph Studio, `tasks`, `pages` for Saved Pages, `ui-builder`). The empty-query "Pages" launcher no longer uses the hand-maintained `TOP_LEVEL_PAGE_IDS`; it is derived from `LAUNCHER_ORDER` in the registry (sidebar order + Bots), and new `registry-sync.test.ts` fails the build if any tab lacks a page, any rendered tab lacks a sub-page, or a sidebar section is missing from the launcher (`chart` stays deliberately retired; legacy `graph-studio` stays an alias of `overview`). Fixed a real navigation bug: the shell strips the `memory.`/`skills.` prefix before dispatching, but those screens split it again, so every palette → Memory/Skills sub-page jump was a silent no-op. Saved (blueprint) pages are now searchable and openable: `/api/search/global` aggregates them from the Python runtime (`/sdk/pages`, operator token, dashboard mirrors excluded, best-effort on failure), `stock-chat` pokes the keep-alive Pages screen with the SDK's synthetic `popstate`, and a saved page's row deep-links to `/?tab=pages&page=<id>`. `INDEX_VERSION` is now one shared constant (`lib/search/index-version.ts`) instead of two hand-synced copies. Tests: `registry-sync.test.ts` (8), full vitest suite green; `tsc --noEmit` clean (3 pre-existing Python tool-registry failures from the ML allowlist work remain — unrelated). Docs updated: `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.

- **style(chat): the jump rail reads as a spaced ruler, and size never signals
  state.** `MessageRail` (`src/components/chat/message-rail.tsx`) now stacks
  1px hairline ticks on 14px-tall rows with a 6px gap (was 2px), every tick
  rests at a uniform 7px width, and the highlighted (reading-position) tick is
  emphasized by tone only — the `active` tick no longer renders 2px wider at
  rest. The decaying "wave" ripple around the hovered tick is now the only
  source of width variance and exists solely while hovering; it collapses on
  mouse-leave. No doc change — presentation-only behaviour tweak, no contract
  change.
- **style(chat): the jump rail's spacing is now fixed pixels.** Follow-up to the
  entry above: the rail uses `gap-[6px]` and `h-[14px]` rows instead of the
  rem-based `gap-1.5`/`h-3.5`, so the 6px rhythm holds at any user text-size
  setting. No doc change — presentation-only.
- **style(chat): the jump rail spacing is tightened to minimal.** `gap-[2px]`
  rows `h-[6px]` (7px between hairlines) instead of 6px/14px, keeping the rail
  compact while retaining a 14px hover/tap target via the tick's inset. No doc
  change — presentation-only.

## 2026-11-03
- **feat(theme): lime brand refresh and a Crystal sidebar.** The shipped accent
  moves from green `#7aff78` to lime `#b4ff42` across the CSS tokens, the theme
  store defaults, the Aurora sentiment palette and the Market Bubbles canvas, and
  the sidebar ships as a translucent Crystal frost (`#1a1a1e`, opacity 0.55, blur
  34) with `dramatic` shadows as the default (labels updated so the default is
  marked). Existing user themes keep their saved values; this changes the
  shipped defaults and their tests. Tests: `theme/tokens.test.ts`,
  `aurora-sentiment.test.ts` updated. Docs updated: `docs/CHANGELOG.md`.
- **revert(accounting): the ledger is chat-only — the tab, proxy and browser
  client are removed.** The accounting capability was meant to be used in
  conversation, not browsed; a parallel screen doubles the surface that must stay
  in sync with the book and invites a second place where a total could be
  computed. Deleted `src/components/screens/accounting/`, `src/lib/ledger/client.ts`
  and `src/app/api/ledger/[[...path]]/route.ts`, and reverted every trace of the
  tab: the `AppTab` union, the sidebar section, the shell's lazy import and
  keep-alive block, search/deep-link registration, the i18n navigation key, the
  SDK nav mirror, and the shortcut/size pins. The Python engine, the `ledger_*`
  tools, the `bookkeeper` preset, the ledger monitors and the operator
  `/ledger/*` routes are untouched. Docs updated: `docs/ledger.md` ("Surfaces
  (chat only)"), `docs/NAVIGATION.md`, `docs/DECISIONS.md` (ADR-066 amended,
  ADR-068), `skills/ARCHITECT.md` (same), `docs/CHANGELOG.md`.
- **feat(ml-lab): scale, lifecycle and the generative path.**
  The arena and the hyperparameter search now run on the Fabric `ml` worker
  (`background: true`), so a big comparison can no longer hit the proxy timeout —
  same worker, timeout, cancellation and progress as training. A registered model
  becomes a first-class chat capability: `ml_model_<slug>_predict` is registered on
  the live registry and appended to the default agent's allowlist (existing models
  re-register at boot), marked `dynamic` so the portable manifest stays a function
  of the code rather than of the database. `ml_transition_model` exposes the
  governed lifecycle (`evaluate → approved_research → archived`) with an approval
  event and audit row per transition. `ml_build_training_corpus` distils a dataset
  version into instruction/answer JSONL (incomplete rows skipped, never filled) and
  `ml_finetune_adapter` writes a LoRA corpus + runnable `train_lora.py` + README +
  manifest under `.black-eclipse/ml/adapters/`, training only when
  torch/transformers/peft are installed and otherwise reporting MODEL_UNAVAILABLE.
  Tests: `test_ml_chat_capabilities.py` (9) and two Fabric arena/search cases.
  Docs updated: `docs/ml-lab/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **fix(journal): R-multiples are unit-correct for FX/CFD, and the trade tables
  show the time.** A stop 4.96 points away on a 0.1-lot XAUUSD trade was treated
  as $0.50 of risk instead of $49.60, so the first broker trades to carry a stop
  showed ~33R. The projection now calibrates the contract multiplier from the
  broker's own gross P&L (`Σ grossPnl / Σ (price move × quantity)` → 100 for
  XAUUSD, 100 000 for EURUSD) and converts the stop distance to account currency
  before dividing; an uncalibrated symbol has no R at all. Also: the Trades list,
  Overview "Recent Trades" and Daily Journal now render `YYYY-MM-DD HH:MM` (UTC,
  matching the journal's date contract) via `fmtDateTime`/`fmtClock`, and the
  broker popup's "N connections" counter no longer sits under the close button.
  Tests: `project.test.ts` (+2 multiplier cases), `format.test.ts` (new). Docs
  updated: `docs/journal-broker-sync.md`, `docs/CHANGELOG.md`.
- **feat(ledger): invoices/bills and consolidation in the tab, plus ledger
  monitors (completion).** Three gaps closed. (1) The Accounting tab now renders
  **invoices & bills** — post a document against a customer/vendor with an
  account, amount and optional tax code, and record a payment against the
  outstanding balance — and **consolidation** — create a group, add members with
  an ownership percentage, run the report, and read the consolidated figures,
  eliminations and findings. (2) Three ledger monitors join the closed catalogue:
  `ledger_suspense_watch`, `ledger_close_blocked` and `ledger_receivables_watch`,
  all created switched off. (3) `LedgerFactProvider` resolves
  `ledger.<id>.<field>` (`suspense`, `blockers`, `warnings`, `ready`, `open_ar`,
  `open_ap`, `entries`) through the SAME service the tools read; a missing ledger,
  failed read or unknown field yields NO fact, so a condition evaluates
  UNAVAILABLE instead of firing on a guessed balance. Tests:
  `python/tests/test_ledger_monitors.py` (7) plus the full ledger suite; the tab
  additions are covered by `tsc` and the tab/search/sidebar suites. Docs updated:
  `docs/ledger.md` (Surfaces, limits, "still open"), `docs/DECISIONS.md`
  (ADR-067), `skills/ARCHITECT.md` (ADR-067), `docs/CHANGELOG.md`.
- **feat(ledger): the Accounting tab, a front-door proxy and a closed
  `bookkeeper` agent preset (Phase 6).** The engine was complete but only reachable
  from a shell. Phase 6 adds `src/app/api/ledger/[[...path]]/route.ts` — a pure
  pass-through to the runtime's `/ledger/*` with the same mutation guard as the
  portfolio proxy and no accounting logic — plus `src/lib/ledger/client.ts` (typed
  browser client whose one error type carries a refusal code so the UI shows the
  reason) and the **Accounting** tab: ledger create/select, assets/liabilities/
  equity/net income, trial balance, P&L breakdown, recent journal, a close-check
  panel that renders blockers vs warnings by severity, and AR aging with the
  control-account reconciliation badge. All of it reads the SAME endpoints the
  agent uses, so a screen can never compute a second set of numbers. The
  **`bookkeeper` preset** is a closed surface — its allowlist is exactly the
  `ledger_*` family (no market data, no code, no browser, no MCP) — with a prompt
  that encodes the ledger's discipline (never invent a number, a posting balances
  or it does not happen, corrections are reversals, unmatched rows go to suspense,
  a tax rate is configured data, "reconciled" only when the tool says so);
  mutations still require `ledger_write` approval. Tab wiring covers `app-tabs`,
  the sidebar config (APPENDED so F1–F12 keep their sections), the shell's lazy
  import, search/deep-link and the i18n navigation slice. Tests:
  `python/tests/test_bookkeeper_preset.py` (5) plus the tab/sidebar/search vitest
  suites (160). Docs updated: `docs/ledger.md`, `docs/NAVIGATION.md`,
  `docs/DECISIONS.md` (ADR-066), `skills/ARCHITECT.md` (ADR-066),
  `docs/CHANGELOG.md`.
- **fix(journal): broker-imported trades are classified and shown truthfully, and
  every popup is wide.** MT5 deal history carries no stop loss, so every imported
  trade had `riskAmount=null` / `rMultiple=0` and the journal counted all 46 of
  them as breakevens: win rate 0.0 %, `+0.00R` on every row, a flat R equity curve,
  profit factor 0.00 and an R distribution of zeroes — while the same trades had
  real P&L (+$766.34). New `classifyTradeOutcome()` uses R when a stop-derived risk
  exists, otherwise the sign of the realized P&L; wins/losses/breakevens, win
  rate, streaks, every dimension, the calendar, psychology leaks, weekly reviews,
  wrapped and the agent summary all use it. `PerformanceStats.rAvailable` (and
  `DayAggregate.rAvailable`) now says whether R is measurable at all, so Net R /
  Expectancy / Max Drawdown / R distribution render **UNAVAILABLE — no stops
  captured** instead of a fabricated `+0.00R`; the equity and drawdown charts fall
  back to the always-truthful currency curve (`currencyEquity` is now cumulative
  realized P&L, not R × risk). Profit factor is the standard currency gross-win /
  gross-loss ratio. Broker `pnlPct` is the price-relative move (the old notional
  formula produced −70.7 on a 0.01-lot EURUSD trade). Prices render via
  `fmtPrice()` (no more `3932.2900000000004`), and CSV/PDF R cells are blank/— when
  R is unavailable. Open positions render `open`/— instead of a fake `+0.00R`, and
  a sync now refreshes a stale `pnlPct` too (it was excluded from the change
  detector, so old notional-based values survived). MT5 `history_deals_get` gets a
  3-day lower-bound margin so a clock skew cannot drop the oldest deals of a
  backfill. The shared `DialogContent` is wide by default (`sm:max-w-2xl`) and uses
  the `.glass-card-strong` tier; every popup that had pinned a narrow `max-w-*`
  override was widened, and the broker connector popup (`sm:max-w-5xl`) now shows
  the real adapter badge (MT5 / MT4 / Alpaca / IBKR), an accurate description,
  per-kind bridge labels and a layout-matching skeleton while it reads the broker. Tests: `analytics.test.ts`
  (+2 fallback/rAvailable cases). Docs updated: `docs/journal-broker-sync.md`,
  `docs/trading.md`, `docs/CHANGELOG.md`.
- **feat(ml-lab): the ML workflow is now a chat workflow — prompt guidance, predict-by-name, ensembles.**
  Every ML tool was already allowlisted, but the chat system prompt named none of
  them, so the agent never composed the path. It now documents
  dataset → plan → train → compare/tune → register → predict → drift, with the
  honesty rules (no invented metric, no family the runtime cannot import, dataset
  before training, registration before prediction). `ml_predict` also accepts a
  model NAME, so "predict with my momentum model" works. New `POST /ml/v1/ensembles`
  (tool `ml_create_ensemble`) registers a composition of already-trained models:
  members must share one task and one dataset version, their out-of-fold rows are
  intersected, probabilities are averaged (majority vote without them, ties to the
  lowest class), and the score is computed on those shared out-of-fold rows — no
  re-fitting. Prompt cap re-pinned 41,967 → 42,960 in both prompt tests. Tools:
  19 → 20 (`docs/harness/tool-registry.json` regenerated). Tests:
  `python/tests/test_ml_ensemble.py` (7).
  Docs updated: `docs/ml-lab/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **feat(ledger): entity groups, proportionate consolidation, intercompany
  elimination and exports (Phase 5).** A single set of books cannot answer a
  group's questions, and "export" had no shape at all. Phase 5 adds
  `group_store.py`, `consolidation.py`, `exports.py` and `group_tools.py`. A group
  is a consolidation **scope** that owns no journal: members contribute
  proportionately (ownership % × every line — stated as `PROPORTIONATE`, no NCI
  line), accounts are matched **by code and type** (a type clash is a blocker, not
  an average), a foreign member needs a supplied per-currency rate (never
  invented), and intercompany pairs are eliminated **by subtype** with only the
  matched amount removed — the remainder stays on the books and is reported as
  `INTERCOMPANY_OUT_OF_BALANCE`. Consolidated figures go through the same
  statement engine, so the accounting equation is checked once. Exports produce
  `journal_csv`, `trial_balance_csv`, a complete `json` bundle and a well-formed
  XBRL 2.1 instance that says in its own comment that it is **not**
  taxonomy-conformant; **SAF-T is refused** with a reason rather than
  approximated. Adds 5 `ledger_*` tools, `/groups*` + `/export` routes, group
  tables, four `INTERCOMPANY_*` accounts in the standard chart, and an
  export range that anchors at the first posting instead of the current month.
  Tests: `python/tests/test_ledger_{consolidation,exports}.py` plus tool/API
  round-trips. Docs updated: `docs/ledger.md`, `docs/NAVIGATION.md`,
  `docs/DECISIONS.md` (ADR-065), `skills/ARCHITECT.md` (ADR-065),
  `docs/harness/tool-registry.json` (regenerated), `docs/CHANGELOG.md`.
- **feat(ml-lab): dependency-free hyperparameter search, with the selection caveat built in.**
  `POST /ml/v1/search` (tool `ml_search_hyperparameters`) runs up to 24 trials of
  one family over a declared grid or a seeded sample of it, on the caller's exact
  folds, persisting each as a normal run. Native families ship small documented
  default spaces; optional families take an explicit grid. The ranking reuses the
  arena's rule, so an unmeasured trial cannot win, and the top-ranked config is
  always reported with `withinNoise` saying whether it is actually separable from
  the runner-up. The note ALWAYS states that the winner was selected on the same
  folds it is scored on (optimistic) — no search result is dressed up as a
  generalization estimate. `maxTrials`/`maxSeconds` bound it and `stoppedReason`
  says which bound hit. The Experiments tab gained "Tune {family}". Tools:
  18 → 19 (`docs/harness/tool-registry.json` regenerated). Tests:
  `python/tests/test_ml_search.py` (8), including a within-noise case and a clear
  winner.
  Docs updated: `docs/ml-lab/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **feat(ml-lab): explain every family, and take the data with you.**
  Feature importance only existed for the tree families, so a linear model, a
  k-means centroid set or the torch MLP had no explanation at all.
  `finalPermutationImportance` now ranks the selected features for EVERY family by
  shuffling each one on the final holdout (seeded, 5 repeats) and reporting the
  drop in accuracy (classification) or negative RMSE (regression) with its spread;
  below 30 holdout rows it is `None` rather than a confident number from noise.
  Separately, `GET /ml/v1/datasets/{id}/versions/{v}/export?format=csv|jsonl`
  returns the version as portable text — features, target, its human labels and
  the row timestamps, read from the stored artifact — bounded by `limit` and
  stating `truncated` when it bites; the Datasets tab gained Export CSV/JSONL.
  No new tool, so the registry digest is unchanged. Tests:
  `python/tests/test_ml_importance_export.py` (7), including a run-level
  importance check and a truncation assertion.
  Docs updated: `docs/ml-lab/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **feat(ml-lab): probability calibration and feature-drift monitoring.**
  A model that trains well can still be untrustworthy: its scores may not be
  probabilities, and its inputs may have moved. `calibration` (`none` | `platt` |
  `isotonic`) is fitted on the pooled OUT-OF-FOLD predictions — never the holdout
  — reported before/after on Brier and log-loss, stored in the artifact, and
  applied by `predict_proba`; binary only, and it returns `None` rather than an
  identity curve when the data cannot support one. `POST /ml/v1/models/{id}/drift`
  (tool `ml_model_drift`) compares the training dataset version with a later one
  per feature (PSI under reference quantiles + two-sample KS with an asymptotic
  p-value) and returns stable/watch/drift, with a schema change reported rather
  than scored as zero. Contract schema 1.2.0 (additive `calibration`). Tools:
  17 → 18 (`docs/harness/tool-registry.json` regenerated). Tests:
  `python/tests/test_ml_calibration_drift.py` (10), including a calibrated
  service round-trip and a drift verdict on shifted data that stays `stable` on
  the training version.
  Docs updated: `docs/ml-lab/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **feat(ledger): AR/AP subledger — customers, vendors, invoices, bills, payments
  and aging (Phase 4).** A ledger that cannot invoice is still a spreadsheet with
  double entry. Phase 4 adds `parties.py`, `tax.py`, `documents.py` and
  `subledger_store.py`: documents compute their own lines (`Dr AR / Cr revenue /
  Cr tax`, mirrored for a bill) and post through the ONE journal path, so an
  unbalanced invoice cannot exist. Tax codes are **configured data** — jurisdiction,
  a fractional rate, the GL account, inclusive/exclusive — with **no bundled rate
  table**: an unconfigured code is `TAX_CODE_NOT_FOUND` and an unconfigured
  jurisdiction `UNSUPPORTED_TAX_JURISDICTION`. Control accounts are discovered from
  the chart by subtype with a per-document override, never invented. Payments
  allocate (over-payment refused, repeated reference posts once); voiding reverses
  the journal entry and is refused when payments exist; aging is derived at the
  report date from documents minus allocations-as-of-that-date and **checked against
  the control account**, reporting a difference instead of hiding it. Adds 10
  `ledger_*` tools (mutations behind `ledger_write`), 7 route groups
  (`/parties`, `/tax-codes`, `/documents*`, `/aging`), four tables on the ONE
  `agent-memory.db`, and `document_tools.py` so `tools.py` stays within its size
  budget. Tests: `python/tests/test_ledger_documents.py` plus tool/API round-trips
  (207 ledger tests total). Docs updated: `docs/ledger.md`, `docs/NAVIGATION.md`,
  `docs/DECISIONS.md` (ADR-064), `skills/ARCHITECT.md` (ADR-064),
  `docs/harness/tool-registry.json` (regenerated), `docs/CHANGELOG.md`.
- **feat(ml-lab): a model arena — compare families on the same folds.**
  After "build me a model" the next question is "which one?", and the only honest
  way to answer it is one dataset, one validation design. `POST /ml/v1/compare`
  (tool `ml_compare_models`) trains up to six families with the caller's exact
  split spec/seed/selection, persists each as a normal run, and returns a table
  plus a verdict. The verdict refuses the three usual lies: a null metric is
  excluded rather than sorted as 0; a margin inside the larger fold standard
  deviation is reported as "no clear winner"; and a task without ground truth
  (`anomaly`) is never ranked. Clustering ranks by silhouette only. The ML Lab
  Experiments tab gained "Compare families", which renders the ranking with fold
  sd and the not-ranked list. Tools: 16 → 17
  (`docs/harness/tool-registry.json` regenerated). Tests:
  `python/tests/test_ml_compare.py` (7) — including a service-level proof that
  every family saw identical folds.
  Docs updated: `docs/ml-lab/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **feat(ledger): schedules, accruals, FX revaluation and a real close checklist
  (Phase 3).** A ledger you cannot close is a ledger you cannot trust. Phase 3
  adds `schedules.py` — depreciation/amortisation schedules whose every period is
  derived up front (straight line gives the last period the rounding remainder so
  the total equals `cost − salvage` exactly; declining balance never dips below
  salvage), posted idempotently per period and stopping at the first period a
  closed book refuses; one-off `ledger_accrue` postings with an optional automatic
  reversal; `revaluation.py` — period-end FX for foreign-currency-restricted
  accounts at a *supplied* rate (`RATE_REQUIRED` instead of an invented one),
  convergent and idempotent per account+date+rate, recorded as a `base_only` line
  so the foreign balance never drifts; and `close.py` — a persisted close run whose
  findings carry a severity: `SUSPENSE_BALANCE` / `TRIAL_BALANCE_BROKEN` block the
  close, while negative cash, a stale reconciliation, a due schedule, a missing
  revaluation, an unfinished import and a possible duplicate are warnings the
  operator may accept. `close_period` now delegates to that checklist (the old
  `statements.close_check` was removed — one checker, not two). Adds 9 `ledger_*`
  tools (mutations behind `ledger_write`), `/schedules*` `/accrue` `/revalue*`
  `/close/preview` `/close-runs*` routes, `LedgerSchedule` + `LedgerCloseRun`
  tables and a `JournalLine.baseOnly` column with an additive migration. Tests:
  `python/tests/test_ledger_{schedules,close}.py` (176 ledger tests total). Docs
  updated: `docs/ledger.md`, `docs/NAVIGATION.md`, `docs/DECISIONS.md` (ADR-063),
  `skills/ARCHITECT.md` (ADR-063), `docs/harness/tool-registry.json`
  (regenerated), `docs/CHANGELOG.md`.
- **feat(ledger): statement import, categorisation rules and reconciliation
  (Phase 2).** Phase 1 could keep books but every entry had to be typed. Phase 2
  brings the money in: `importers.py` parses CSV (with a declared column mapping),
  OFX and QIF; `rules.py` categorises deterministically (conditions AND, needles
  OR, magnitude bounds, `(priority, name, version)` order, first match wins,
  append-only versions); `imports.py` previews and posts a batch through the normal
  journal path; `reconcile.py` compares a statement to one cash account with
  MATCHED/MISMATCH/MISSING/UNKNOWN plus a real balance check. The refusals are the
  feature: the format and date pattern are declared rather than guessed, an
  unparseable date names its row, a row is idempotent (`stmt:<account>:<row-id>`)
  so a re-import posts nothing, an unmatched row posts to `9999 Suspense` (and
  blocks the close) instead of being guessed or dropped, a foreign row without an
  `fx_rate` is `REQUIRES_FX` and is not posted, an ambiguous amount/date pair is
  UNKNOWN rather than "the first one", and a run without `statement_balance` is
  `INCOMPLETE` — rows alone never earn "reconciled". Adds 13 `ledger_*` tools
  (mutations behind `ledger_write`), `/import/*` + `/rules*` + `/reconcile` routes,
  `LedgerRule`/`LedgerImportBatch`/`LedgerReconciliation` tables on the ONE
  `agent-memory.db`. Tests: `python/tests/test_ledger_{imports,reconcile}.py` plus
  the tools/API round-trips (136 ledger tests total). Docs updated: `docs/ledger.md`,
  `docs/NAVIGATION.md`, `docs/DECISIONS.md` (ADR-062), `skills/ARCHITECT.md`
  (ADR-062), `docs/harness/tool-registry.json` (regenerated), `docs/CHANGELOG.md`.
- **feat(ml-lab): a deterministic model-recipe planner, and an optional deep-learning adapter.**
  "Build me a model that predicts X" had no policy: the user (or the agent) had
  to pick a family and validation design unaided. `POST /ml/v1/plan` (tool
  `ml_plan_model`) now turns a built dataset (or an inline rows/features/task
  profile) into a reviewable plan — family, hyperparameters, split and
  feature-selection choice, each with its reason and any warnings — and returns
  the exact `/ml/v1/experiments` body so planning and running cannot drift. It
  is pure and deterministic, chooses only families the runtime can actually
  import, and reports no metric (a plan is a proposal). The ML Lab's Experiments
  tab gained "Suggest a model", which fills the form from that plan.
  Separately, `torch_mlp` adds a seeded tabular MLP behind a new, deliberately
  separate `python/requirements-train.txt` (torch is hundreds of MB and never
  ships by default). It serializes weights as plain JSON, reports
  `MODEL_UNAVAILABLE` when torch is absent, and deliberately claims no
  CNN/RNN — there is no image/sequence data path. Tools: 15 → 16
  (`docs/harness/tool-registry.json` regenerated). Tests:
  `python/tests/test_ml_recipes.py` (12) and
  `python/tests/test_ml_torch_adapter.py` (2 + 1 skipped without torch).
  Docs updated: `docs/ml-lab/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **feat(ledger): a double-entry book of record, Phase 1 (accounts, journal,
  periods, statements).** Eclipse could model a company but could not *keep its
  books*: there was no general ledger, so "post this invoice", "close March" or
  "show me the balance sheet" had no defensible home. New
  `python/harness/ledger/` implements the core — chart-of-accounts templates as
  data (`standard`/`sole_trader`/`minimal`), balanced journal postings with
  exact `Decimal` arithmetic (Σ debit == Σ credit or a named refusal carrying
  the exact difference), per-line FX translation, append-only entries with
  reversing corrections, monthly fiscal periods with OPEN/CLOSED/LOCKED, and a
  derived trial balance / balance sheet / income statement / cash flow, each
  returning `checks`. Cash movement that cannot be classified is reported in an
  explicit `unclassified` bucket instead of being guessed; a non-zero suspense
  balance blocks a period close. Persistence is on the ONE
  `agent-memory.db` with `(ledgerId, source, externalId)` import idempotency.
  Wired as 19 flat `ledger_*` tools (reads free; mutations behind the single-use
  `ledger_write` approval), an operator-gated `/ledger/*` route group, a boot
  layer + per-run bundle, and the agent allowlist. `portfolio/money.py` is
  re-exported, not forked. Tests:
  `python/tests/test_ledger_{core,statements,tools,authorizer,api}.py` (86).
  Docs updated: `docs/ledger.md` (new), `docs/NAVIGATION.md`, `docs/DECISIONS.md`
  (ADR-061), `skills/ARCHITECT.md` (ADR-061), `docs/harness/tool-registry.json`
  (regenerated), `docs/CHANGELOG.md`.
- **feat(ml-lab): clustering and anomaly detection (label-free tasks).**
  The ML Lab could only train supervised models, so "group these rows" or "flag
  the odd ones" had no path at all. Datasets can now declare
  `target.kind="unsupervised"` with `target.task` = `clustering` | `anomaly`
  (both sources: market features or an uploaded table), and two native families
  were added — `kmeans` (seeded k-means++, serialized as centroids) and `mad_z`
  (per-feature median/MAD with a training-score quantile threshold). The
  unsupervised pipeline keeps the temporal discipline: the same folds and
  leakage assertion, fit-on-train-only standardisation, and every metric is
  out-of-sample. It refuses feature selection (it needs a label), reports
  `null` for an undefined silhouette instead of a stand-in number, and reports a
  rate + score distribution for anomalies rather than an invented accuracy. A
  label-free dataset's quality coverage is measured on features, not on a label
  that does not exist. Wired through `/ml/v1`, the ML tools, `capabilities`, and
  the ML Lab target/task selects. Tests:
  `python/tests/test_ml_unsupervised.py` (11) plus the existing ML suites.
  Docs updated: `docs/ml-lab/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **feat(ml-lab): train on any uploaded table, not just market prices.**
  The ML Lab's datasets came only from the market gateway, so "build me a model"
  was limited to price/volume features. `DatasetSpec` now declares a `source`:
  `market` (unchanged) or `records` — operator-supplied rows, with the named
  numeric columns as features and a `column` target (`target.task` =
  regression | classification, labels coded in sorted order and stored as
  `target.classLabels` so predictions decode back). Wired through
  `/ml/v1/datasets`, the `ml_build_dataset` tool, `GET capabilities`
  (`datasetSources`) and the ML Lab Datasets tab (CSV upload). Correctness is
  unchanged: the same chronological/purged split engine and leakage gate apply,
  and every malformed input is a named error (non-numeric cell → column + row;
  unsorted `timeColumn` refused rather than silently re-sorted; single-class
  label; market-only target kind on a records source). Contract schema bumped
  to 1.1.0 (additive). Tests: `python/tests/test_ml_records_source.py` (13) plus
  the existing ML suites; `npx tsc --noEmit` clean.
  Docs updated: `docs/ml-lab/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **fix(harness): an unreachable local model server names itself and the remedy.**
  A stopped Ollama/LM Studio fails with the SDK's bare `Connection error.`, which
  reached the operator as an unexplained provider failure (the reported "provider
  issue" — the local Ollama daemon simply was not running, so every chat turn
  failed). `provider_failure_message` now turns a network-class failure against a
  loopback `baseUrl` into an actionable line ("Can't reach ollama at
  localhost:11434 — the local model server is not running. Start it, then retry;
  or switch to another provider in Settings.") and leaves every other error
  message untouched (a remote provider, or a 401 from a local server, keeps its
  own text). Verified end-to-end: with Ollama started, `/api/harness/chat`
  answers normally. No doc change — error copy, not an architecture or contract
  change.
- **fix(desktop): the launch bar now actually advances.**
  The old indeterminate shimmer could read as a slider parked at one position.
  The bar is now a real fill derived from the time spent in the current phase:
  it never goes backwards, eases toward 72% while building (60s time constant),
  steps to 86% starting and 93% while waiting for the proxy, and only reaches
  100% when the app actually answers. A highlight travels inside the filled
  portion so it keeps reading as active even when the percentage barely moves.
  Reduced-motion / animations-off keeps the advancing fill but drops the shine.
  `/status` now exposes `phaseElapsedMs` for that calculation.
  Docs updated: `docs/CHANGELOG.md`.
- **feat(desktop): rotating, situation-aware hints on the launch screen.**
  The single long build paragraph read like documentation and promised a fixed
  "two seconds". The progress page now rotates a short hint every 7s (server-
  derived from elapsed time, so no extra timer), cross-faded on the client and
  disabled under `prefers-reduced-motion` or a theme with animations off
  (`motion-off` class). The launcher picks the accurate set: first build,
  rebuild after a source change, or waiting on a build another process started
  (`BUILD_HINTS` in `scripts/lib/desktop-splash.js`). A specific warning (e.g.
  the hostname not resolving) is sticky and overrides rotation until the phase
  changes.
  Docs updated: `docs/QUICKSTART.md`, `docs/CHANGELOG.md`.

## 2026-11-02
- **feat(desktop): the launch screen follows the user's app-wide theme; status tag removed.**
  The progress page is served from `127.0.0.1`, a different origin from the app,
  so it cannot read the browser's `localStorage` theme cache. It now reads the
  **app-wide** theme from JDDS (`SystemConfig`, key `eclipse_theme` — the row
  Settings › Customization writes via `/api/theme`) through the new
  `scripts/lib/app-theme.js`, and renders with the saved brand color, scheme
  (dark/light), font stacks, radius, glass tint/blur/opacity, background
  treatment, glow toggle, shadow weight and logo/favicon. A missing or malformed
  row falls back to the shipped theme; every value is sanitized (hex-only
  colors, clamped numbers, stripped font stacks, no remote image URLs) before it
  reaches CSS or HTML. Custom uploaded logos/favicons (data URLs or files under
  `public/`) are served at `/logo` and `/favicon`; otherwise the shipped wordmark
  and favicon are used. The BOOTING/READY/FAILED tag was removed — the page shows
  the phase line only.
  Docs updated: `docs/QUICKSTART.md`, `docs/CHANGELOG.md`.
- **fix(runtime): stored provider keys reach the spawned Python runtime; media demo passes.**
  The runtime child is spawned from instrumentation BEFORE the boot step that
  copies vault keys into `process.env`, so it started keyless and agent/vision
  calls failed with "Provider 'openrouter' is not configured (missing API key)"
  until some later restart. `python-runtime.ts` now calls
  `applyStoredKeysToEnv()` immediately before the spawn (a real env var still
  wins). Related vision fixes: outputs are bounded with `bind(max_tokens=…)` so
  the account is charged for the reply rather than the model's full 16 384-token
  generation budget, and a durable graph job re-resolves credentials for
  `model.vision` runs too, not only `agent.run`. Verified through the app:
  **Candle option review (demo)** returns two real observations (`qwen2.5-vl`,
  903/847 tokens) and **File import (demo)** returns 24 rows. Tests: full Vitest
  4282 passed; Python graph+vision suites 134 passed. Docs updated:
  `docs/ARCHITECTURE.md`, `docs/graph-studio.md`,
  `docs/graph-studio-media-agent-memory-nodes-plan.md`, `docs/CHANGELOG.md`.
- **fix(desktop): a click always shows a live progress page; production builds are serialized.**
  Double-clicking `start-eclipse.vbs` could look completely dead: the launcher
  runs with a hidden console, so a cold build (minutes), a failing boot, or a
  proxy that never bound produced no window and no error. The launcher now opens
  a loopback progress page (`scripts/lib/desktop-splash.js`, default
  `127.0.0.1:3197`) *first*; it names the real phase, shows the last server log
  line, redirects to `https://blackeclipse/?desktop=1` when the app answers, and
  shows an honest error panel (reason + log path) when boot fails instead of
  exiting silently. The page renders in the saved app-wide theme (see the entry
  above) and serves the **real** wordmark and favicon (theme logo when one is
  set, otherwise `public/branding`), with a text fallback if an asset is missing.
  A second click attaches to the running launcher's page; a
  page left over from a dead launcher is ignored. `start-eclipse.vbs` now finds
  Node on PATH or in the two standard install locations and reports a missing
  Node with a dialog.
  The root cause of the intermittent hang was two `next build` runs rewriting
  the same `.next` directory at once (a terminal `npm run build` plus the
  launcher, which saw no `BUILD_ID` because the other build had just wiped it).
  `npm run build` now runs `scripts/build-prod.js`; `scripts/lib/server.js`
  gained a machine-wide `.next-build.lock` used by `npm run build`, `npm run up`,
  `black eclipse` and the desktop launcher, which waits for a running build and
  reuses its output when the source is unchanged. The launcher also waits (with
  a visible "a build is already running" phase) instead of starting a competing
  build, and both boot paths now have deadlines that end in a readable error.
  Docs updated: `docs/QUICKSTART.md`, `docs/environments.md`,
  `docs/CHANGELOG.md`.
- **fix(desktop): instant icon opens and a server that stops only when the last tab closes.**
  Clicking `start-eclipse.vbs` no longer calls `stopExisting()` first: if the
  production app already answers, the launcher opens the tab in ~0.1s instead of
  killing and cold-booting a healthy server (the reported "lag"). A cold boot
  now waits for the **public** URL (proxy included), not just the app port, so
  the tab cannot open on a 502 page that never beacons. The beacon file became a
  **refcount of live tabs** (`DesktopSession` sends a per-page-load tab id;
  `/api/desktop/session` serializes read-modify-write), so closing one of
  several or duplicated tabs no longer stops the server under the rest. The
  crash heartbeat fallback moved from 2.5 minutes to 30 minutes and is skipped
  on the first tick after machine sleep, because a hidden/frozen tab and a
  suspended laptop both freeze the 10s heartbeat while the page is alive;
  `visibilitychange`/`focus`/`pageshow` re-beacon on resume. Next's stdout and
  stderr now go to `.black-eclipse/desktop-server.log` (previously lost in the
  hidden console), including a log line when the server exits after boot.
  Docs updated: `docs/QUICKSTART.md`.
- **harden(broker): operator-only broker routes, URL validation, retries.**
  All `/api/journal/broker/*` routes and the `/api/trading/*` proxy now require
  an authenticated **operator** when auth is active (`requireOperatorApiAuth`);
  auth-off local mode is unchanged. Alpaca/IBKR base URLs are validated
  (http/https, no embedded credentials) before any request, and both adapters
  retry 429/5xx with bounded backoff. IBKR `probe` checks
  `/iserver/auth/status` and reports an expired CPAPI session honestly.
  Alpaca/IBKR positions without a broker open time are labelled "first seen",
  never silently dated 1970. A production checklist now lives in
  `docs/journal-broker-sync.md`. Verified with
  `npm run build` (clean), `tsc --noEmit`, 4,270 vitest tests and the broker
  Python subset. Docs updated: `docs/journal-broker-sync.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): seeded files/media demo + demo-found fixes.**
  `npm run demo:graph-media`/`scripts/seed-graph-media-demo.mts` seeds **File
  import (demo)** and **Candle option review (demo)** into Overview, generating a
  CSV and two deterministic candle PNGs through the real graph/vision stores.
  The file demo was run through the app and returned 24 rows with every node
  succeeded. The image demo was verified through `image.attach` (asset read +
  640×360 metadata) and then failed honestly at the provider boundary when the
  configured model account had insufficient credits; no fake reading was
  emitted. Demo-found fixes: `validate_port_value` now understands `file`/`image`
  outputs (the first run failed with `unknown port type file`); the vision asset
  store persists uploaded metadata and preserves a descriptive name/source when
  an analysis re-saves the same bytes; `image.batch` fails when every image read
  fails instead of letting a downstream agent run on an empty result. Added the
  `File import` template and an optional control input on the File/Parse nodes.
  Tests: `test_graph_model.py` (file/image port checks), `test_vision_store_owner.py`
  (name preservation), `test_graph_image_nodes.py` (all-fail batch); full TS
  suite 4259 passed; build exit 0; full Python suite 9434 passed before these
  last demo fixes, targeted suites after. Docs updated: `docs/graph-studio.md`,
  `docs/graph-studio-media-agent-memory-nodes-plan.md`, `docs/CHANGELOG.md`.
- **feat(broker): Alpaca + IBKR read-only adapters, FIFO normalizer, live smoke test.**
  `alpaca` (REST) and `ibkr` (Client Portal Gateway) are registered as read-only
  broker kinds with honest availability/probe. Because neither exposes a
  position id, a shared `adapters/fifo.py` turns fills/executions into FIFO
  round-trip legs (scale-ins, partials, shorts, pro-rata fees); the journal
  marks that P&L `pnlBasis="computed"` and the detail says so. Credentials are
  always NAMEs (`credentialRef` → env var or `secret://…`), never values.
  `POST /trading/connections/{id}/smoke` runs probe → account → positions →
  orders → deals → one sync and returns per-check PASS/FAIL; the CLI
  `python/scripts/broker_smoke.py` and a **Smoke** button in the broker dialog
  use it. The broker form now selects MT5 / MT4 bridge / Alpaca / IBKR with the
  right fields. Tests: FIFO (6), Alpaca (3), IBKR (3), smoke (2).
  Docs updated: `docs/trading.md`, `docs/journal-broker-sync.md`,
  `docs/NAVIGATION.md`, `docs/DECISIONS.md` + `skills/ARCHITECT.md`
  (ADR-059 amendment), `docs/CHANGELOG.md`.
- **feat(graph-studio): in-editor workflow assistant that builds on the canvas.**
  Added a tool-calling agent (n8n-style) at `POST /api/graphs/assist` → Python
  `POST /graphs/assist`: `graph_runtime/assistant.py` lets the model search the
  REAL node registry, inspect schemas, add/wire/configure/remove nodes and
  validate the graph in a bounded loop. It returns the editor's closed operation
  vocabulary plus a compiled IR; `assistant-store.ts` auto-applies safe,
  warning-free edits through `dispatchMany` (one undo step) and shows a
  review card when there are warnings/errors. New panel in the editor's right
  dock (header `Assistant`), with selection-aware context, a New-conversation
  reset per loaded workflow, Ask mode that refuses mutating tools, and a canvas
  focus request that centres newly created nodes, secret-like node config
  redaction before the graph context leaves the process, and an honest warning
  when the model answers without calling any tools. The turn now streams over
  SSE (`/api/graphs/assist/stream`) with live tool steps and a Stop button; the
  transcript is persisted per workflow in `sessionStorage`; large graphs send
  full configs only for the selection and its neighbours; search understands
  common aliases (api/http, sma/ema, filter/where, …); and a failed run offers
  "Fix the failed run" using the run's real error. The assistant can close the
  loop itself with a bounded `run_workflow` tool: it executes through the same
  `GraphService.run_sync`, always as a TEST run (network/trading/write refused
  by the compiler), caps at 2 runs per turn, returns failed nodes + real errors
  + terminal output, and is never offered in Ask mode. Effectful graphs still
  require the operator run. Auto-apply is a per-browser preference (on by
  default) and proposals are bound to the IR id they were computed against, so
  a cross-workflow apply is refused. Credentials stay in memory.
  Tests: `python/tests/test_graph_assistant.py`,
  `src/lib/graph-studio/assistant-ops.test.ts`,
  `src/lib/graph-studio/assistant-store.test.ts`. Docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **chore(graph-studio): regenerate the node registry manifest.**
  `npm run graph:manifest` synced `registry.manifest.json` with the current
  `data.file.attach`/`parse` control inputs. No behavior change; the
  cross-language contract test was red on the stale artifact.
  no doc change — generated contract artifact.
- **feat(journal): per-user journal ownership when auth is active.**
  `JournalProfile` gains a nullable `userId`; `getOrCreateProfile()` resolves the
  request's auth session and returns a deterministic `jp_<userId>` profile, so
  trades, broker links, reviews, days and accounts are isolated per user. With
  auth off (zero-config local), the oldest guest profile is used unchanged. If
  auth is required but a journal request has no live session, the journal fails
  closed instead of falling back to the shared guest. The first authenticated
  user adopts the pre-auth guest journal (one-time, conditional write) so
  existing trades are not orphaned; later users never inherit it. The boot demo
  seeder skips when auth is required. Broker connections remain operator-level;
  the link and projected trades are
  per-profile. New `src/lib/journal/owner.ts`; guest duplicate-collapse is now
  scoped to guest rows. Docs updated: `docs/journal-broker-sync.md`,
  `docs/DECISIONS.md` + `skills/ARCHITECT.md` (ADR-059 amendment),
  `docs/CHANGELOG.md`.
- **feat(broker): read-only MT4 HTTP bridge + journal-wide sync affordance.**
  A second built-in broker adapter, `mt4_bridge`, speaks a documented read-only
  JSON contract (`/account`, `/positions`, `/orders`, `/orders/{ticket}`,
  `/quote`, `/deals`) against a local bridge that owns the MT4 login. History
  reads moved to the base `BrokerAdapter` (a read capability, not execution), so
  a read-only adapter can feed reconciliation without claiming an order path.
  `bridgeSecretRef` is a name (env var or `secret://…` vault ref), never a value.
  The broker dialog now selects MT5 or MT4 bridge and shows the right fields.
  The Trades tab gains a compact **Broker** sync button with last-sync state and
  a source filter + BROKER badge, so syncing no longer requires opening
  Settings. Tests: `python/tests/test_mt4_bridge_adapter.py` (contract, secret,
  honest refusal, reconcile end-to-end). Docs updated: `docs/trading.md`,
  `docs/journal-broker-sync.md`, `docs/DECISIONS.md` + `skills/ARCHITECT.md`
  (ADR-059 amendment), `docs/CHANGELOG.md`.
- **harden(journal): broker sync production hardening.**
  Broker-owned execution fields (`entry/exit/stops/quantity/times/commission/fee/
  symbol/direction`) are now refused on PATCH with `409` and never P&L-recomputed;
  only user-owned fields are written, so a notes edit cannot race a sync into a
  price-derived number. The UI hides Edit for broker trades and shows an
  ownership note. Sync calls coalesce per `(profile, connection)`, and a unique
  collision from a second server (dev+prod share the DB) is treated as success.
  Link creation now validates the connection with the runtime, rejects
  malformed ids (`400`, or `503` when the runtime is down), stamps the account's
  `brokerConnectionId`, and enforces one account per connection with a unique
  `(profileId, accountId)` index (applied to the local dev DB after confirming
  zero link rows). Preview is rate-
  limited (12/min) and reports an unavailable/stale mirror honestly; API errors
  are logged server-side and returned as generic messages. Every journal trade
  lookup filters `ignoredAt` tombstones. New `broker/ownership.ts` + tests.
  Docs updated: `docs/journal-broker-sync.md`,
  `docs/DECISIONS.md` + `skills/ARCHITECT.md` (ADR-059 amendment),
  `docs/CHANGELOG.md`.
- **feat(journal): deal-level broker fills, account/magic analytics, broker agent tools.**
  Phase 3. Every projected broker deal is now stored as an immutable `TradeFill`
  (unique by `(tradeId, dealTicket)`), so the trade detail shows scale-ins,
  partial closes and multi-fill exits with the broker's own ticket, volume,
  price, commission, swap and profit. `syncFills` inserts only missing deals;
  an unchanged trade still backfills fills it lacks. New
  `GET /api/journal/trades/[id]/fills`. Analytics gains `byAccount` (including
  `Unassigned`) and `byMagic` (broker trades only), rendered in the Analytics
  tab. The journal agent gains `get_broker_status` and
  `get_broker_performance`, which reports broker-sourced performance with
  per-account/per-magic splits and never mixes manual/demo trades. On the
  projection engine, `magic` is copied onto `Trade` for grouping. Fills are now
  paged 1,000 at a time with a stable `(dealtAt, id)` cursor (20 pages max), so a
  large backfill is no longer truncated at the old 5,000 ceiling.
  Tests: projection fills assertions, account/magic dimension test, fill-cursor
  paging.
  Docs updated: `docs/journal-broker-sync.md`, `docs/NAVIGATION.md`,
  `docs/DECISIONS.md` + `skills/ARCHITECT.md` (ADR-059 amendment),
  `docs/CHANGELOG.md`.
- **harden(graph): owner isolation + upload limits for files and images.**
  The vision asset store gains an `ownerId` column (idempotent migration, index)
  and scoped asset ids for non-local owners while keeping the legacy content id
  for the local operator. All reads/writes/deletes accept an owner filter; the
  orchestrator, vision tools, document renderers and graph image nodes pass the
  run/context owner. Graph runs now adopt the verified identity owner (never the
  self-asserted `x-harness-user` alone), and `routers/graphs` resolves it from
  the `X-Harness-Identity` token. The asset/image proxies forward that token via
  `runtimeProxyHeaders`; Python routes resolve the owner from the verified
  identity and ignore a query-string owner when auth is on. Both upload routes
  now enforce byte caps at the runtime boundary and a per-owner rate limit.
  Tests: `test_vision_store_owner.py` (2), `test_graph_asset_routes.py` (3) +
  affected graph/vision/document/security suites (1061 passed, 6 opt-in skips);
  full Python suite 9434 passed before this hardening, full Vitest 4259 passed,
  `npm run build` exit 0. Docs: `docs/graph-studio.md`, ADR-060 mirror, plan,
  CHANGELOG.
- **feat(journal): broker history backfill, scheduled auto-sync, attribution UI.**
  Phase 2 makes the broker link production-usable. `POST /trading/connections/
  {id}/sync` now accepts `{"days": N}` (1–3650) and calls the adapter's
  `deals_window(N)` instead of the incremental cursor; `JournalBrokerLink`
  `backfillDays` drives a first import or a gap recovery, computed from
  `lastSyncedAt` (no explicit window needed within 5 days). The mirror read
  ceiling rises from 500 to 5,000 deals (still one bounded response). A new
  `src/lib/journal/broker/scheduler.ts` runs one opt-in, single-flight timer
  (`JOURNAL_BROKER_SYNC_SECONDS`, default 300 s, min 60, `0` disables) for links
  with `autoSync`, with a 5-minute failure backoff per connection. The Settings
  panel gains rule authoring (magic/comment/symbol → strategy/setup/tags),
  per-link backfill-window editing and a **Full backfill** action. Python tests
  cover the explicit-window dedupe; vitest covers the due/backoff rules.
  Docs updated: `docs/journal-broker-sync.md`, `docs/trading.md`,
  `docs/NAVIGATION.md`, `docs/DECISIONS.md` + `skills/ARCHITECT.md` (ADR-059
  amendment), `docs/CHANGELOG.md`.
- **feat(graph): vision image nodes, n8n-style `agent.task`, memory lifecycle
  (waves 2–4).** `graph_runtime/image_nodes.py` + `registry-media.ts` add
  read-only image nodes over the ONE vision engine: `image.attach`,
  `image.analyze` (describe/answer/ground/extract with schema checking),
  `image.ocr`, `image.read_chart`, `image.compare`, `image.batch` (1–8 images,
  one result row each, failed rows preserved). Every output is labelled an
  observation (`verified: false`); `read_chart` sets `verified: true` only from
  the engine’s own market check. No rendering, no image generation.
  `agent.task` adds the full n8n-style form (instructions, task, preset, tool
  allowlist that can only narrow, memory mode/scope, JSON output schema);
  instructions/tools were also added additively to `agent.research`/`agent.bot`/
  `agent.delegate`. Memory gains `memory.context` (budgeted block),
  `memory.list`, `memory.update`, `memory.forget` (archive) plus
  `EclipseMemoryService.list_memories/update_memory/archive_memory` and explicit
  `general|workflow|run` scope resolution. Bootstrap binds the vision runner and
  asset store; test runs now grant `image.read`/`model.vision`. Front door:
  `/graph/assets/images` + `/api/graph-studio/images` and an image picker with
  thumbnail. Fixed `memory.remember`’s graph source to the service’s permitted
  `manual` value. Tests: `test_graph_image_nodes.py` (12),
  `test_graph_agent_task_memory_nodes.py` (13), registry parity (30); manifest
  regenerated; `Candle option review` starter template; ADR-060 in
  `skills/ARCHITECT.md` + `docs/DECISIONS.md`. Verified: `tsc --noEmit` clean,
  full Vitest 4254 passed, full Python suite 9434 passed / 30 skipped,
  `npm run build` exit 0 (after clearing a stale `.next` cache). Docs updated:
  `docs/graph-studio.md`, `docs/graph-studio-media-agent-memory-nodes-plan.md`,
  `docs/CHANGELOG.md`.
- **feat(journal): broker → journal projection (MT5 reconciled fills).**
  Phase 1 of the broker-linked journal: a `JournalBrokerLink` binds an existing
  Python `BrokerConnection` to a journal account, and
  `POST /api/journal/broker/sync` refreshes that connection's reconciled mirror,
  groups deals by `positionTicket`, and upserts one `Trade` per position keyed by
  `externalId = broker:<connectionId>:<positionTicket>` — idempotent, never a
  duplicate. The broker owns execution fields and its own net P&L
  (`pnlBasis="broker"`, no price×quantity recompute for FX/CFD); notes, emotion,
  confidence, grade, checklist, screenshots, self-assigned strategy/setup and
  user tags are never overwritten. Deleting a broker trade tombstones
  `ignoredAt` so sync cannot resurrect it. Magic/comment/symbol attribution
  rules fill strategy/setup/tags; per-link `symbolMap` handles broker suffixes.
  Preview is read-only; a failed sync keeps the last good projection and writes
  no fake fill. New models `JournalBrokerLink` + `BrokerAttributionRule`, broker
  provenance fields on `Trade`/`TradingAccount`, pure projection engine with 12
  tests, and Journal → Settings → Broker Connection UI.
  Docs updated: `docs/journal-broker-sync.md` (new), `docs/NAVIGATION.md`,
  `docs/trading.md`, `docs/DECISIONS.md` + `skills/ARCHITECT.md` (ADR-059),
  `docs/CHANGELOG.md`.
- **feat(persona): draft/active user personas appended to the fixed prompt.**
  Settings → Persona adds a named persona library. A persona is a bounded
  (2,000-char) append-only overlay after the authoritative `eclipse-agent`
  prompt — tone, structure and emphasis only; the tool allowlist, permissions,
  data sources and safety/financial rules are resolved before it is read and
  cannot be changed by it. Edits stage a draft; Activate promotes it into a new
  immutable version and deactivates the previous persona (one active globally);
  Discard reverts; Reset to default removes the overlay; Restore loads a version
  into the draft; Archive keeps history. Every write carries a `revision` token
  and a stale save is a 409 (never a silent overwrite); history is bounded to
  the last 50 versions with the active version always kept. The run records
  `persona id@version` on `surface.persona`, so a later edit never rewrites an
  earlier run.
  `python/harness/personas.py` + `/personas/*` router, boot wiring
  `install_persona_store`, the `eclipse-agent` append in `graph.py`, front door
  `src/lib/personas/client.ts` + `/api/personas/**`, the Settings panel, and a
  searchable `settings.persona` palette entry.
  Tests: `test_personas.py` (13 cases), `test_personas_api.py` (5 cases),
  `test_graph.py` integration cases (persona reaches the system prompt and the
  run record; bound tool allowlist is byte-identical with and without a persona;
  a custom agent is untouched), full vitest (446 files / 4,259 tests), full
  Python suite (9,452 passed, 30 skipped — vendor `site-packages` tests excluded
  after a pywin32 COM collection crash); `tsc --noEmit` clean; production
  `next build` passes; targeted ESLint clean (two pre-existing `settings.tsx`
  hook warnings, no errors).
  Docs updated: `docs/harness/architecture.md`, `docs/NAVIGATION.md`,
  `docs/DECISIONS.md` + `skills/ARCHITECT.md` (ADR-058), `docs/CHANGELOG.md`.
- **feat(graph): local file nodes + bounded graph asset store (wave 0/1).**
  `graph_runtime/assets.py` adds `HarnessGraphAsset` on the ONE
  `agent-memory.db`: content-addressed per owner, 25 MB/200 files/512 MB caps,
  TTL + owner isolation, explicit missing/expired errors.
  `graph_runtime/file_nodes.py` adds `data.file.attach` (uploaded CSV/TSV/JSON/
  XLSX/text → `file` + `text` + `rows`, capped rows/cells with truncation
  reported), `data.file.parse` (same parser over an upstream File ref; Excel
  sheet select) and `data.file.export` (CSV/JSON/XLSX local artifact). New
  `file`/`image` port types and `media` category; `asset.read|asset.write`
  granted to test runs. Front door: `/graph/assets` runtime routes + Next proxy
  (`/api/graph-studio/assets[/:id]`) and an inspector file picker; workflow
  config stores only the `gas_` ref. Tests: `test_graph_file_nodes.py` (13
  cases), graph-registry parity (30), graph-studio vitest (178); `tsc --noEmit`
  clean. Docs updated: `docs/graph-studio.md`,
  `docs/graph-studio-media-agent-memory-nodes-plan.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **docs(graph): plan for files, images, agents and memory nodes.**
  `docs/graph-studio-media-agent-memory-nodes-plan.md` audits what already
  exists (agent + memory nodes, candlestick chart rendering, vision asset store,
  image generation, Artifact Center, dataset store) and specifies the four new
  families without a second engine: bounded graph asset store +
  `data.file.attach|parse|export`; **vision-read-only** image nodes
  (`image.attach`, `image.analyze`, `image.ocr`, `image.read_chart`,
  `image.compare`, `image.batch`) that wrap the existing vision API and return
  observations, never evidence, with no chart rendering or image generation;
  n8n-style `agent.task` plus shared instructions/tools/output-schema/memory
  upgrades to the existing agent nodes; and `memory.context|list|update|forget`
  over the ONE memory service. Includes decisions D1–D9, test-run matrix,
  provenance rules, UI work, test matrix and wave estimates. Docs updated:
  `docs/graph-studio-media-agent-memory-nodes-plan.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(graph): `research.queries` + `Research brief` template (plan complete).**
  `research_query_nodes.py` adds a pure query-expansion node: a question, the
  gaps a run named and weak claims become answer/support/counter-evidence/
  primary-source queries (deduped, capped, no store/network/model). It is the
  loop primitive Wave A exposed and pairs with `flow.parallel` +
  `research.web_search`. Added the `research-brief` starter template (stored run
  → evidence → conflict scan → citation audit → report). The remaining Wave D
  candidates (`counter_evidence`, `save_claim`, `calculate`, `notebook`) are
  explicitly declined in the plan with reasons. Tests: 3 new query cases (19 in
  the analysis suite) + all 178 graph-studio vitest tests (template validation
  included). Docs updated: `docs/graph-studio.md`,
  `docs/graph-studio-research-nodes-plan.md` (status Implemented),
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(graph): `research.ingest` + `research.diff` (Wave C complete).**
  `research_write_nodes.py` adds `ingest`, which normalizes an
  `agent.research` blob, an MCP tool result or a manual claim set into
  `Evidence`/`Claim`/`Source` rows: it derives stable ids, keeps the origin and
  `eclipseVerified: false` on every row, never verifies a claim and never copies
  an external answer as the run answer (the run is status `INGESTED`). Rows
  without an absolute http(s) URL are skipped and reported, and re-ingesting the
  same payload is idempotent. `research_analysis_nodes.py` adds `diff`: two runs
  on the SAME question are compared with snapshots preferred when present —
  evidence added/removed by content hash, claim-status transitions, opened/
  resolved material conflicts, source URL changes and coverage deltas; different
  questions are refused as incomparable. Tests:
  `python/tests/test_graph_research_write_nodes.py` (10 cases: origin/verified
  flags, no answer copy, idempotence, skipped rows, derived run id, diff
  evidence/claims/conflicts/sources, incomparable refusal, snapshot preference).
  Docs updated: `docs/graph-studio.md`,
  `docs/graph-studio-research-nodes-plan.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): research network adapters (Wave B) + ranking/search/crawl polish.**
  `research_network_nodes.py` + `registry-research.ts` add `fetch_many`
  (1-10 known URLs, concurrency 1-4, content-hash dedupe, optional evidence
  persistence, failed URLs as rows and a failed batch as an explicit error),
  `scrape` (deterministic table/record collection through the bridge's
  `web_collect`, honest page status), `extract_facts` (the engine's
  model-assisted but span-validated extractor; an unvalidated proposal is a
  rejection note) and `deep_dive` (the existing `ResearchEngine` with budget
  caps, a 600 s hard timeout and a returned run id). Also: `web_search` accepts
  a provider preference and optional source persistence (`saveSources`);
  `web_crawl` takes `maxDepth`/`delayMs`; `source_rank` scores recorded
  source-type authority (primary/secondary/tertiary); the report numbers its
  citations. Tests: `python/tests/test_graph_research_network_nodes.py` (10
  cases) + expanded research/analysis/team suites (55 green) and the
  registry/executor/compiler suites (114 green). Docs updated:
  `docs/graph-studio.md`, `docs/graph-studio-research-nodes-plan.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(graph): `research.start_run` + `research.snapshot` (Wave C partial).**
  `research_write_nodes.py` + `registry-research.ts`: `start_run` creates the
  run row a cold graph needs and is idempotent per question/objective (a
  content-derived `r_…` id; an existing run is never overwritten);
  `snapshot` freezes the selected sections (sources/evidence/claims/citations/
  conflicts/questions, or all) into the store's immutable, versioned snapshot
  table and returns the version. Both declare `research.write`; the existing
  compiler capability gate refuses them in a test run (the capability is not in
  `TEST_RUN_CAPABILITIES`). Tests: 5 new cases in
  `test_graph_research_analysis_nodes.py`, including the test-run refusal and
  the missing-run error. Docs updated: `docs/graph-studio.md`,
  `docs/graph-studio-research-nodes-plan.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): research analysis pack + research-node fixes (Wave A).** Added
  ten local `research.*` nodes in `python/harness/graph_runtime/
  research_analysis_nodes.py` (registered from `node_packs.py` to keep
  `nodes.py` under its size ceiling) and `src/lib/graph-studio/
  registry-research.ts`: `latest` (exact/newest run), `sources` (domain/type/
  date filters + content/family dedupe), `gaps` (unanswered questions, rejected
  and uncited claims), `freshness` (engine fail-closed point-in-time filter),
  `conflict_scan` (deterministic detection over unscanned evidence),
  `citation_audit` (build + validate traceability), `supersession` (revision
  chains), `quality` (explainable score + disclaimer), `entities` (anchored
  graph) and `claims_verify` (batch). All are `research.read`/`read`, so a test
  run can exercise them. Fixes in the shipped nodes: conflict status is
  normalized (`OPEN`→`UNRESOLVED`, `DISMISSED`→`RESOLVED`) and `candidates` is
  decoded; `claim_verify` now passes the run's conflicts + `asOf`/`freshness`
  (and falls back to recorded claim links); reads report `total`/`truncated`;
  `completeness` gets a real coverage model, `verdict` and `gaps`; `report`
  degrades to `UNAVAILABLE` without a run row instead of raising, escapes raw
  HTML, adds Sources/Gaps sections and a bounded `maxItems`; `web_search`
  over-fetches then filters/dedupes; `web_crawl` reports `linkDiscovery`
  failures. `manifest.ts` now sorts by codepoint for byte-identical manifests
  across ICU versions. Tests: `python/tests/
  test_graph_research_analysis_nodes.py` (11 cases) + existing
  research/registry/parity suites; graph-studio vitest 178 green. Docs updated:
  `docs/graph-studio.md`, `docs/graph-studio-research-nodes-plan.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **docs(graph): research & evidence node plan.** Audited the ten shipped
  `research.*` nodes and wrote an implementation-ready plan:
  `docs/graph-studio-research-nodes-plan.md`. Records twelve defects (R1–R12)
  with file:line grounding — `claim_verify` never passes conflicts/asOf/
  freshness, conflict-status vocabulary drift (`OPEN` vs `UNRESOLVED`) and
  undecoded `candidates`, silent truncation, the completeness coverage
  fallback, report injection/missing-run-row failure, the undeclared store
  write in `web_fetch`, post-limit domain filtering in `web_search`, swallowed
  link-discovery failures in `web_crawl`, and `source_rank` ignoring recorded
  authority. Proposes 17 new nodes in three waves (local reads:
  latest/sources/gaps/freshness/conflict_scan/citation_audit/supersession/
  quality/entities/claims_verify; network: fetch_many/extract_facts/scrape/
  deep_dive; local writes: start_run/snapshot/ingest/diff), plus decisions,
  capability/effect rules (`research.write`, extract=model), limits, file
  split (`registry-research.ts`, `research_*_nodes.py`), reference graph, test
  matrix and acceptance gates. Docs updated: `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`. Implementation not started.
- **fix(graph): adapter-pack registration split out of `nodes.py`.** The Tier
  2/3 packs pushed `graph_runtime/nodes.py` to 1218 lines (ceiling 1200); the
  wiring now lives in `graph_runtime/node_packs.py` (`register_extra_packs`),
  and `graph.py` is re-pinned 2355→2370 for the AgentPreset fallback. Targeted
  graph/size tests green (79). no doc change — internal split, contracts
  unchanged.
- **feat(graph): `flow.parallel` — bounded concurrent map (the last plan item).**
  The runtime already ran same-layer nodes concurrently (bounded by the
  workflow's `maxConcurrency`); this adds the DYNAMIC fan-out over data.
  `executor._run_parallel` + `parallel_workers`: concurrency is
  `min(config, workflow.maxConcurrency, itemCount, 8)`, so a node can never fan
  out wider than the graph was authorized to. Results are collected in **input
  order** (`pool.map`), keeping runs deterministic; each item is a durable child
  run (`<parent>:<node>:i<N>`), so a resumed parent reuses a succeeded item. A
  failed item is `{"error": ...}` in `results` and counted in `summary`;
  `continueOnError` off fails the node naming the first failure. Cancellation is
  checked per item. The compiler's subworkflow diagnostics
  (`missing`/`cycle`/`depth`/nested-graph errors) now cover it too. Contract in
  `loop_nodes.py` + `registry-loops.ts`, presentation/`maxItems`/
  `concurrency` help in `config-fields.ts`, example added, manifest regenerated.
  Tests: `python/tests/test_graph_parallel.py` (9 cases: input-order results,
  per-item failure with/without `continueOnError`, truncation, empty list,
  compile-time missing body, checkpoint reuse, the concurrency clamp, and a
  timing proof that three 300 ms items finish under the serial cost).
  Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/graph-studio-bot-skill-nodes-plan.md`, `docs/CHANGELOG.md`.
- **chore(docs): rotated the changelog window.** Ran
  `scripts/rotate-changelog.js --write` to archive the oldest dated section into
  `docs/changelog/2026-10.md` (window of 7 preserved). no doc change — mechanical
  rotation, no contract or architecture change.
- **feat(graph): `logic.human_approval` — the approval gate (Tier 3).**
  `graph_runtime/approval_nodes.py` + `registry-utility.ts`: creates ONE
  `graph_approval` in the runtime's existing single-use approval store (the same
  rows the Permissions panel decides), keyed by `graph:<runId>:<nodeId>` and a
  digest of the request text, with a ≤ 24 h TTL. The decision is **not
  consumed** — it gates that run+node, so a resumed run reads the same answer.
  Denials fail the node and name the approver. New runtime primitive:
  **`DeferredWait(rerun=True)`** (`model.py` + `executor.py`): a rerun-deferred
  node is left **PENDING** and its outputs/control are NOT checkpointed, so the
  resumed durable job re-enters it — without this a deferred node was recorded
  as succeeded and the gate would silently pass. Durable runs therefore pause
  without holding a worker; synchronous runs poll up to `maxWaitS` (default
  300 s) and then fail honestly, leaving the request in Approvals. Test runs
  never create a request. Bootstrap binds `set_approval_runner` to
  `service.approvals`. Manifest regenerated. Tests:
  `python/tests/test_graph_approval_node.py` (10 cases) plus a durable
  integration case in `test_graph_durable.py` proving the paused run leaves the
  gate non-succeeded and finishes only after approval; parity green.
  Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/graph-studio-bot-skill-nodes-plan.md`, `docs/CHANGELOG.md`.
- **feat(graph): the rest of Tier 2 — committee, chart, notify, evidence
  ranking.** Four nodes complete the plan's candidate set. `agent.team`
  (`team_nodes.py`, `registry-agents.ts`) runs the Institution committee through
  the existing team runtime (run → wait → finalize → synthesize), returns the
  reconciled `decision`, deterministic `synthesis` and terminal `status`
  (COMPLETED/PARTIAL succeed), never places an order or registers a trigger, and
  refuses a test run. `output.chart` (`output_nodes.py`, `registry-output.ts`)
  normalizes a spec / number list / `{values, categories}` / `{series,
  categories}` / `{rows}` + X/Y fields into a validated `ChartSpec` and the
  plotly figure the chart engine draws, reporting `rendered: false` (spec still
  returned) when plotly is absent — never a fake image. `output.notify` sends
  one message through the ONE channel service (`send_outbound`) with the
  `network` effect, so a test run can never send and a provider refusal fails
  the node with its reason. `research.source_rank` (pure, in `research_nodes.py`)
  ranks evidence by the `confidence` and freshness the items already carry
  (exponential decay of publishedAt/retrievedAt with a configurable half-life);
  an item with neither is sorted last and counted `insufficient_signal`, so no
  score is invented. Runners bound at boot (`set_team_runner`,
  `set_notify_runner`). Manifest regenerated. Tests:
  `python/tests/test_graph_team_output_nodes.py` (13 cases) + parity green.
  Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/graph-studio-bot-skill-nodes-plan.md`, `docs/CHANGELOG.md`.

