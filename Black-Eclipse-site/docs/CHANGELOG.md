# Change Log

Older entries are **moved, never deleted** into [`docs/changelog/`](./changelog/)
— one file per month. This file keeps the newest seven dated sections;
`npm run rotate:changelog -- --write` performs the move.

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

## 2026-11-13
- **fix(chat): the transcript cache write no longer freezes the composer on
  every turn.** Root cause of the "it stops for 10–15 s when I send, then stops
  again when the reply appears" report: `saveConversationsCache` removed ONE
  conversation per attempt and re-serialized the whole (barely smaller) list each
  time. It runs on the main thread 400 ms after every transcript change — i.e.
  exactly at send and at reply — so once the history passed the ~5 MB
  localStorage quota the eviction was O(n²) `JSON.stringify`: seconds of frozen
  UI, twice per turn, growing with history (this install holds 234 chats /
  19.3k messages). It now serializes each conversation once and binary-searches
  the smallest eviction that fits, so the cost is O(n) serialization + O(log n)
  `setItem` calls regardless of how far over quota the list is. Payload bytes are
  unchanged (`[` + pre-serialized rows + `]` is exactly `JSON.stringify(list)`),
  and the eviction order (trashed → archived → oldest unpinned) and return value
  are preserved. Test `chat-organization.test.ts` pins the write count to
  ≤ ceil(log2 n)+1 for a 2 000-chat over-quota list (the old loop made ~2 000 full
  re-serializations). `npx tsc --noEmit`, vitest 524 files / 4 831 tests.
  no doc change — behaviour-preserving performance fix; the cache contract is
  already described in `docs/chat-ui-audit.md`.
- **fix(skills): `/skills run` now sends the skill's input.** The command called
  `executeSkill` with no `input`, so every skill with a required input — including
  EVERY user-authored skill, whose schema requires `objective` — was blocked by the
  Python runtime with `INPUT_VALIDATION_FAILED` before it ran. `/skills` now opts
  into `passThroughFlags` and `run` forwards `--key value` flags (plus trailing free
  text as `objective`, and `--version` as a pin) into the execution request; an
  input-validation failure also renders a usage hint. Covered by
  `command-router.test.ts` (flags, free text, version) and the parser/registry hint
  tests. docs updated: `docs/harness/slash-commands.md`, `docs/CHANGELOG.md`.
- **feat(build): `npm run build` can no longer break the running app.**
  The last "I built it and the app broke" path: a raw build rewrites `.next`,
  deletes `BUILD_ID` and saturates the CPU while the desktop app is up, which
  starves the Python runtime's cold start (33–67 s idle, >5 min under a build)
  and leaves doctor reporting no available build. Policy now lives in
  `scripts/lib/build-guard.js` (pure, 9 tests in `src/lib/build-guard.test.ts`);
  `scripts/build-prod.js` probes channel ports + owner markers and **refuses**
  with the three alternatives (`desktop:refresh`, `black stop`, `desktop:dev`).
  The managed paths stay exempt via `BE_ALLOW_BUILD_WHILE_RUNNING=1` because they
  own the pin and restart: `scripts/desktop-build.js` (so `desktop:refresh` still
  works) and `scripts/update.js` (builds before refreshing). Advice strings in
  `desktop-server.js` / `desktop-promote.js` now point at `desktop:refresh`
  instead of a build that would be refused. Verified live: plain
  `npm run build` with the app up exits 1 naming Stable/3100/pid, and
  `npm run desktop:refresh` still builds + promotes + reopens.
  docs updated: `docs/environments.md`, `docs/QUICKSTART.md`, `docs/CHANGELOG.md`.
- **fix(voice): the Stop control fits inside the composer; stale builds cannot
  skip a rebuild.** The recording control grew to `■ Stop 0:12` but the call
  sites passed `w-8`/`w-9`, which won the cascade and squeezed the label so it
  spilled past the composer's right edge. The button now keeps the caller's
  height, drops its width while recording, and the composer chip is
  `min-w-0 flex-1 truncate` with the hint hidden below `md`, so nothing can
  overflow. Separately: `build()` recorded the source hash AFTER `next build`
  finished, so an edit made mid-build was marked "already built" and a stale
  chat chunk was promoted (the release missing the Stop UI). It now writes the
  hash taken at build START, and `scripts/mark-build.js` is a documented no-op.
  no doc change — layout fix plus build-tooling correctness.
- **fix(harness): a slow boot no longer becomes a permanent 503.** Root cause of
  the "runtime never came up after a relaunch" report: a **concurrent
  `npm run build`** (a stale session's `BE_FORCE_BUILD=1; npm run build`) held
  `.next-build.lock`, deleted `BUILD_ID` and saturated the CPU, so the Python
  cold start could not finish. The supervisor then made it permanent in two ways:
  (1) on timeout it called `killTrackedRuntime()`, killing a child that was still
  importing — measured boot is 33–67 s idle, but the budget is a timeout, not a
  verdict; (2) the boot pre-start was a single fire-and-forget attempt, so
  nothing retried and agent features 503'd until someone POSTed
  `/api/harness/runtime/restart` by hand. Now `python-runtime.ts` leaves a
  still-alive child running (a later `ensure()` sees `trackedRuntimeAlive()` and
  adopts it when `/health` answers) and only kills on a real exit or bind
  conflict, and `instrumentation.ts` retries with backoff (0/20/45/90 s) before
  reporting unavailable. Verified: idle boot 3100 +5 s / harness +33 s, and under
  the real contention the runtime came up +67 s with doctor all-PASS on build
  `rgxZzk8EB9QB7Juw14dr8`. Tests `src/lib/harness/python-runtime.test.ts` +
  `runtime-supervision.test.ts` (22), `npx tsc --noEmit`. docs updated:
  `docs/CHANGELOG.md`.
- **fix(voice): the Stop control is now labelled, and the field says what to do.**
  On-device transcription runs when the operator STOPS recording, but the only
  affordance was an unlabelled square in the composer — so a live mic stretched
  on and nothing was ever transcribed (the runtime log showed zero
  `/voice/transcribe` calls from dictation). Recording now renders an explicit
  **Stop** control with the elapsed time, the field reads "Listening — speak,
  then press Stop to transcribe", and the composer chip names the engine
  (On-device / Whisper / Browser) plus "stop to transcribe · esc cancels".
  no doc change — copy and affordance only.
- **feat(desktop): the last web surfaces are gone — service worker, offline
  page, container deployment.** Deleting the browser lane left three things that
  only made sense with a browser: (1) the PWA offline layer — `public/sw.js`,
  `src/app/offline/route.ts`, `src/lib/offline/page.ts`, its test and the
  `OfflineReady` registration in `src/app/layout.tsx`; (2) the container
  deployment — `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`,
  `.dockerignore`; (3) the `blackeclipse` dev-origin allowance in
  `next.config.ts` (`allowedDevOrigins`), now unreachable. The shell's own boot
  screen (`desktop/ui/index.html` + `desktop-server.js` markers) is the only
  pre-ready UI, so the fallback had nothing left to protect. Also removed the
  proxy TLS material under `.black-eclipse/certs/`. Verified end to end:
  `npm run desktop:refresh` built (build `_nujF-AUw8YudcJt6EaBs`), promoted,
  relaunched the window, `desktop:doctor` all-PASS, `npx tsc --noEmit` clean.
  docs updated: `docs/ARCHITECTURE.md` (Layer 0), `docs/environments.md`
  (Docker), `docs/NAVIGATION.md`, `docs/DEPLOYMENT.md` (Stale),
  `docs/harness/authentication.md`, `docs/PRODUCTION-READINESS.md`,
  `SECURITY.md`, `docs/CHANGELOG.md`.
  Also normalised `python/tests/test_transcription.py` to LF (one stray CRLF made
  `src/lib/gitignore-guard.test.ts` fail its mixed-line-ending scan).
- **feat(voice): dictation now runs on this machine — no API key, no setup.**
  WebView2 has no speech engine, so `auto` used to resolve to a dead browser
  recognizer (or to "not configured"). Transcription now has a first-class
  **local** provider: `python/harness/transcription/local.py` runs
  `faster-whisper` inside the Python runtime the app already ships, in a worker
  thread, with the model cached under `.black-eclipse/models/whisper` (downloads
  once, then offline). `auto` prefers a configured cloud key and otherwise uses
  the on-device engine, so plugging nothing in still works. pyav is pinned
  `>=12,<15` in `python/requirements.txt` — 15+ removed the `metadata_errors`
  keyword faster-whisper passes to `av.open()` and local transcription failed
  with "unexpected keyword argument". Measured: 4 s clip → 1.7 s, transcript
  correct. Also: `TranscriptionError` moved to
  `python/harness/transcription/errors.py` (local + HTTP paths share it without a
  cycle), the settings provider list gained "On this device", and the runtime
  client timeout is 300 s so a first-run model download is not mistaken for a
  hang. docs updated: `docs/voice.md`, `docs/CHANGELOG.md`.
- **feat(desktop): the browser lane is deleted — there is one front door.**
  Gating was not enough: `bin/black.js` still DEFAULTED to `black eclipse`, which
  booted the old Next site on 3105 behind the local proxy, and `setup:desktop`
  installed an icon whose target chain (`Black Eclipse.exe` shim →
  `start-eclipse.vbs` → `scripts/start-desktop.js`) exited silently because that
  launcher was already behind the web guard. So the product could still be
  started as a website, and a fresh checkout could get a dead shortcut. Fix: the
  CLI is desktop-first (`black`/`black app` open the installed Stable window,
  `dev`/`refresh`/`stop`/`status` drive channels, and the retired `eclipse` /
  `start` / `proxy` explain where they went and exit 1); the shortcut points only
  at the installed native exe and fails loudly when it is absent; `scripts/reset.js`,
  `scripts/update.js` (browser restart removed) and `scripts/smoke-onboarding.js`
  now read channel ports instead of the web profiles. Deleted:
  `start-eclipse.vbs`, `scripts/{start-desktop,local-host,up,local-proxy,local-proxy-stop,kill-port,web-guard}.js`,
  `scripts/lib/{profiles,proxy-state,proxy-task,proxy-offline,front-door,tls,desktop-splash}.js`,
  `scripts/setup-{tls,hostname}.ps1`, `src/lib/desktop-launcher.test.ts`, and the
  `dev`/`dev:next`/`dev:local`/`up`/`start`/`proxy*`/`setup:tls`/`tls:remove`/
  `setup:hostname` npm scripts. `channels.js#webLaneAllowed()` now always returns
  false and has no callers. Tests: `npm test` (4824 pass), `npx tsc --noEmit`.
  docs updated: `docs/environments.md`, `docs/QUICKSTART.md`, `docs/NAVIGATION.md`,
  `docs/ARCHITECTURE.md` (Layer 0), `docs/desktop-app-plan.md`,
  `docs/local-hostname.md` (Stale), `docs/DECISIONS.md` (ADR-079 superseded),
  `README.md`, `AGENTS.md`, `docs/CHANGELOG.md`.
- **feat(trading): the bot execution ladder (P5) — L0/L1/L2 with a real leash.**
  `AutomationDefinition` gains a typed, versioned `executionAuthority`
  (`tier l0|l1|l2`, `appetite`, `sizingMode`, `requireStop`, `maxOpenPositions`,
  `maxMarginPerOrder`, `cooldownS`). A NEW bot is always L0 (`bot_create` refuses a
  higher tier); raising to L1/L2 is a single-use operator approval
  (`bot_authority`), and L2 additionally requires ≥30 scored advisory calls for
  that bot (a new `conversation_id` filter on `AdvisoryStore.list_decisions`), so
  the request is refused before the operator is even asked. `trade/authority.py`
  is the ONE place that answers "may this bot place a live order?": armed live
  connection, a mandate pinned to `botId` + current `botVersion` (new columns;
  a workflow pin and a bot pin are now alternatives, and a workflow-pinned mandate
  cannot be borrowed), `STOP_REQUIRED`, Eclipse-owned position cap by magic
  (`POSITION_CAP_REACHED`, fail-closed `POSITIONS_UNAVAILABLE`), `COOLDOWN_ACTIVE`,
  and `MANDATE_ABOVE_BOT_CAP` at grant creation. `order_submit`/the authorizer now
  admit LIVE **only** from a bot run (`conversationId = bot-<id>`), never from
  ordinary chat. Appetite bands: conservative 0.25%/1 position/2 orders, normal
  0.5%/2/4, aggressive 1%/3/8, with `risk_amount()` for risk-based sizing. Tests
  `python/tests/test_bot_execution_authority.py` (18). docs updated:
  `docs/harness/bot-parity-and-trade-execution-plan.md` (§ P5, § 5),
  `docs/trading.md` (§ unattended live execution), `docs/harness/tool-registry.json`
  (regenerated), `docs/CHANGELOG.md`.
- **fix(voice): dictation ended after a breath — and on desktop it was never
  working at all.** WebView2 exposes `webkitSpeechRecognition` with no speech
  service behind it, so `describeVoiceEngine` picked the browser engine, the
  session started and ended a second later, and the composer honestly reported
  "BROWSER DICTATION". `/api/voice/config` also returns `provider: none,
  ready: false` on this machine, so the Whisper path was unavailable too.
  `browser-recognition.ts` now (a) reports `browserRecognitionAvailable()` false
  inside the Tauri shell and (b) for real browsers is patient: `continuous` plus
  an automatic restart on an unexpected `onend` (capped at 80), `no-speech` is
  treated as a pause rather than an error, and finals accumulate across
  restarts. The mic also only asks for consent when an engine can actually run,
  and the no-provider message is desktop-specific. Desktop dictation therefore
  needs a transcription provider (OpenAI/Groq key or a local whisper.cpp Custom
  endpoint); it no longer pretends the browser engine works there. docs updated:
  `docs/voice.md`, `docs/CHANGELOG.md`.
- **feat(trading): an order names the bot and the objective version that placed it
  (P4).** `BrokerOrder` gains additive `automationId` + `automationVersion`
  columns; `order_submit` derives the bot from the run's conversation
  (`bot-<automationId>`) and resolves the definition's version at submit time, so
  a later objective edit is visible on the orders the earlier one produced.
  `order_ledger` gains an `automationId` filter (a bot asking about itself may
  omit it) and its text names `bot <id>@v<version>`. Deliberately NOT added:
  `executionId` on the ledger (it duplicates `automation execution.runId`, one hop
  away, and two copies can disagree) and per-bot order metrics (the ledger makes
  them a query). The advisory half needed no new write: `AdvisoryDecision` already
  stores `runId` + `conversationId`, and an order stores `runId`, so the scored
  record P5 is gated on is already reachable by joining on the run. Tests
  `python/tests/test_trade_order_traceability.py` (6), including the legacy-DB
  migration path. docs updated:
  `docs/harness/bot-parity-and-trade-execution-plan.md` (§ P4, § 5),
  `docs/trading.md` (ledger traceability), `docs/harness/tool-registry.json`
  (regenerated), `docs/CHANGELOG.md`.
- **style(voice): the recording timer no longer sits in a pink bubble.** The mic
  control's recording state was `bg-rose-500/15` with a hover fill, which read as
  a circle drawn behind the stop square and the elapsed time. The fill is gone;
  the stop glyph and `m:ss` stay on the composer with the rose text tone only.
  no doc change — styling only.
- **feat(bots): a scheduled bot reports the live order it proposed, with the real
  window, into its own conversation (P3).** `order_preview` now passes the run id
  through `preview_order` → `request_approval`, so the approval row carries
  `requestedByRunId` (also exposed by `approval_view`). `Dispatcher._run_agent`
  collects this run's pending trade approvals and hands them to delivery;
  `render_run_report` puts them first as `AWAITING APPROVAL — <order> (good for N
  minutes)` plus the approval id, and a completed run with a pending order is no
  longer reported as "produced no result". The `automation.delivered` event
  carries `botId` + `approvalIds`, and the bot composer banner (mounted in the
  previous entry) picks them up, so approval happens in that chat. Important
  finding recorded in code and docs: a trade approval's window is 300 seconds
  (`APPROVAL_TTL_SECONDS`), so an overnight proposal is correctly dead by morning
  — the report says when the window closed and to re-run, rather than implying the
  order still waits. Tests `python/tests/test_automation_trade_report.py` (12).
  docs updated: `docs/harness/bot-parity-and-trade-execution-plan.md` (§ P3, § 5),
  `docs/harness/automation-engine.md` (unattended answer contract),
  `docs/trading.md` (manual approval path), `docs/CHANGELOG.md`.
- **fix(bots): a trade approval is completed in the bot conversation, like every
  other card.** The bot composer already mounted the generic `ApprovalCard` and
  `ClarificationCard` but not `TradeApprovalBanner`, which was only in the main
  chat composer — so a pending `order_preview` raised by a bot (or by one of its
  scheduled runs) could not be approved where it was proposed. The banner is now
  mounted in `bot-chat.tsx` above the composer: it is the same store-driven,
  self-polling component, bound to the same single-use digest and the same
  `/trading/.../orders/submit` route, so this is a mount, not a second surface.
  The plan drops the separate bot settings/review UI entirely and records "the
  bot conversation is the surface" as design principle 0: configuration is a chat
  request (`bot_update`), and a proposal is an in-thread card. docs updated:
  `docs/harness/bot-parity-and-trade-execution-plan.md` (§ 3.0, § P1, § P3, § 5),
  `docs/CHANGELOG.md`.
- **fix(voice): the field was frozen on this machine, and the mic prompt lived
  in the top-left corner.** Two real defects on the desktop: (1) Windows
  client-area animations are OFF, so WebView2 reported
  `prefers-reduced-motion: reduce` and `voice-fire-field.tsx` drew exactly ONE
  frame — the field looked dead while speaking. The OS signal now selects a calm
  8 fps breathing flame (no sparks); only the app's own reduce-motion /
  animations-off classes still freeze it. (2) WebView2's media consent dialog is
  drawn top-left and cannot be themed or moved, so the shell now suppresses it
  (`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--use-fake-ui-for-media-stream` in
  `main.rs`, merged with any existing value) and `VoiceInputButtonView` asks in
  the composer with an Allow / Not now card, remembered in
  `be_voice_consent_v1`. Also nudges a suspended `AudioContext` back to running
  on each meter read (a suspended analyser reads as silence). docs updated:
  `docs/voice.md`, `docs/CHANGELOG.md`.
- **feat(bots): `bot_create`/`bot_update` reach the Bots UI's configuration depth,
  and the approval channel is corrected.** An agent-created bot was narrower than
  a UI-created one: `agentId` was a three-item enum and the tool accepted none of
  `execution`, `retry`, `concurrency`, `limits`, `delivery`, `permissions`,
  `workspaceRoot` or `autonomy`, even though `AutomationDefinition` models all of
  them. `bot_create`/`bot_update` now accept every installed preset (validated
  against `AGENT_PRESETS`; an unknown id is refused with the known list) and pass
  those blocks through, omitting what was not supplied so stored defaults are
  unchanged. Separately, P1's planned `approvalMode="ask"` for bot runs was
  **wrong and is not implemented**: `pause_for_approval` is consumed inside the run
  by the computer/browser/MCP/guardrail tools, which block until the run deadline
  (`clarify` returns `no_interactive_user`), so setting it on a scheduled run would
  turn "deny fast" into "hang, then fail". A bot's ask channel is the
  execution-level `permissions.requiresApproval` (engine → execution `waiting` →
  `POST /automations/executions/{id}/resume`) plus durable approval rows raised by
  a tool (`order_preview`), and `permissions.requiresApproval` is now settable at
  creation. Tests `python/tests/test_automation_bot_parity.py` (7). docs updated:
  `docs/harness/bot-parity-and-trade-execution-plan.md` (§ P1, § 3.3),
  `docs/harness/tool-registry.json` (regenerated), `docs/CHANGELOG.md`.
- **docs(trading): correction to the P0 write-up — there was no exploitable live
  path, and `create_mandate` never allowed an unpinned live mandate.**
  `TradingMandateStore.create` already required `workflowId` **and**
  `workflowVersion` for a live mandate (`MANDATE_WORKFLOW_REQUIRED`), and because
  the agent tool passes no `workflow_id`, `submit_order` refused at
  `mandates.verify` (`MANDATE_WORKFLOW_MISMATCH`) before the phrase logic ran. The
  real defect was narrower: `wrap_trade_authorizer` checked mandate coverage but
  not the connection's mode, so the live refusal existed only as a side effect of
  the workflow pin, with a misleading error, one edit away from disappearing (a
  bot-pinned mandate in P5 would have reopened it silently). The redundant
  `LIVE_MANDATE_UNPINNED` check this session briefly added to `create_mandate` was
  removed — the store stays the single authority and the error code is unchanged.
  The mode check, `covers(mode=)`, the handler-level `LIVE_ORDER_REFUSED` and the
  corrected descriptions remain as defence in depth. docs updated:
  `docs/harness/bot-parity-and-trade-execution-plan.md` (§ G5, § P0),
  `docs/trading.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **fix(chat): the session-files row no longer collides with the project chip.**
  On the landing composer the row under it was full-width while the composer is
  `max-w-[80%]` centered, and `SessionBar` was `w-full` with an unconstrained
  absolute path, so the path spilled across the project chip and off the pane.
  The row now shares the composer's px/max-w column, `SessionBar` is a
  shrinkable flex item (`min-w-0 flex-1`, optional `className`) whose path
  truncates, and "Session 3" (which read like a session number) is now
  "Session files" with the count in a badge. no doc change — layout/copy fix,
  no contract change.
- **fix(charts): a drawn chart is never replaced by an error, and the chart
  stack is guaranteed on install.** Three failure paths were closed: (1) a
  chart whose Artifact Center registration failed was discarded by both chart
  surfaces as "drawn but could not be stored" — the render route now returns the
  PNG inline and `chartImageSrc()` shows it as a data URL; (2) the plotly
  library route was `force-static` and only looked in vendored paths, so
  macOS/Linux installs and any build performed before `postinstall` finished
  could cache a permanent 503 — it now resolves the library through the running
  interpreter and stays dynamic; (3) `plotly` was missing from the analysis
  requirements and from `setup-python`'s stack probe, so an install that already
  had `langgraph` never got it — it is now installed and probed by both
  `setup-python` and `doctor`. docs updated: `docs/chart-engine.md`,
  `docs/CHANGELOG.md`.
- **chore(desktop): ship the voice field to Stable (`UvJqNNf5nTphjUbd36d_I`).**
  Built, validated, promoted and relaunched through `desktop:refresh` only —
  the browser lane stayed off (`:3000` free, `web-guard` intact). Release
  `releases/stable/UvJqNNf5nTphjUbd36d_I` contains the field (verified by
  `speak naturally` + `esc to cancel` in `static/chunks/56648-*.js`), `:3100`
  serves that build id, and the desktop shell was relaunched. Also tuned the
  flame after the first render (per-column tongues, slower decay, tighter base
  glow, top-aligned transcript with a text shadow, softer pointer wind) and
  clamped the advected heat to 0..1. no doc change — build/promotion plus
  visual tuning, no contract change.
- **docs(trading): autonomy tiers for bots (L0/L1/L2) added to the parity plan.**
  Decision recorded: live is the target, per-order approval is the default (L0),
  and unattended execution (`order_submit` under a live mandate pinned to
  `botId` + `botVersion`) is tier L2 — granted per bot only after a scored
  advisory track record, and bounded by an armed connection, mandate caps
  (`maxOrders`/`maxMargin`), the daily-loss brake, the money guardrails, a
  per-bot position/cooldown limit and the magic-scoped kill switch. Sizing is
  `risk_based` by default with a stop required on every order; `user_fixed` is a
  per-bot override where the bot may decline but never resize. "Based on its
  mood" is replaced by a versioned risk-appetite band so a loss can be traced to
  a rule. Sequence is P0 → P1 → P3 → P4 → P5, because L2 is gated on the scored
  record P4 produces. No code change in this entry. docs updated:
  `docs/harness/bot-parity-and-trade-execution-plan.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **fix(chat): the composer crashed with `ModelSelector is not defined`.** After
  `ModelSelector` moved to `src/components/chat/model-selector.tsx`,
  `chat-input.tsx` kept only `export { ModelSelector } from './model-selector'`
  — a re-export does not create a local binding, so the JSX reference threw and
  the whole shell rendered "Something went wrong" (digest 938137588). The module
  now imports it for use and still re-exports it. no doc change — restoring
  intended behaviour, no contract change.
- **fix(trading): the "no agent path for live orders" rule is now enforced by code,
  not by prompt wording.** `wrap_trade_authorizer` checked mandate coverage without
  checking the connection's mode, and `submit_order` skips the typed LIVE phrase
  when a `mandateId` is present, so a live mandate with an empty `workflowId` on an
  armed connection could be submitted from any agent or bot run. Fixes: the
  authorizer now resolves the connection mode and refuses anything that is not
  `demo` (unknown/missing mode also refused, fail closed) and passes the mode to
  the mandate check; `TradingMandateStore.covers` matches the mandate's mode;
  `create_mandate` refuses an unpinned live mandate (`LIVE_MANDATE_UNPINNED`);
  `order_submit` re-checks the mode in the handler (`LIVE_ORDER_REFUSED`) so a
  missing wrapper cannot send one. Exits are untouched: `position_close` /
  `position_modify` stay allowed on a live connection so an expired grant never
  traps a position. Tests `python/tests/test_broker_agent_trade.py` (+5) and
  `python/tests/test_trade_mandate_mode.py` (4). docs updated: `docs/trading.md`
  (§ two operator-gated paths), `docs/harness/bot-parity-and-trade-execution-plan.md`
  (decision recorded: live with per-order approval; P3 rewritten, standing mandate
  out of scope), `docs/CHANGELOG.md`.
- **docs(harness): plan bot capability parity and governed trade execution.** New
  `docs/harness/bot-parity-and-trade-execution-plan.md` records what is already
  true (a bot run already inherits the interactive agent's full tool allowlist via
  `automation/dispatcher.py::_run_request`; demo orders already submit unattended
  under an operator mandate; unattended live exists only through Graph Studio's
  `allow_live_trading` + workflow-pinned mandate gate), the five real gaps
  (no tool-level approval channel for scheduled runs, no workspace/autonomy for
  code verbs, a narrower `bot_create` surface, unused `PermissionPolicy`, and a
  prose-only live gate), and a P0-P4 plan that reuses the mandate/guardrail/kill
  switch stack. It also flags a safety discrepancy found while writing it: the
  `order_submit` description and `trade/authorizers.py` docstring state that no
  agent path exists for live orders, but `wrap_trade_authorizer` does not check
  mandate mode and `submit_order` skips the typed phrase when a `mandateId` is
  present, so a live mandate with an empty `workflowId` on an armed connection can
  be submitted from an agent run. Closing that in code is P0. docs updated:
  `docs/harness/bot-parity-and-trade-execution-plan.md`, `docs/CHANGELOG.md`.
- **perf(chat): progressive Markdown parsing + a per-run latency record.** A
  streaming turn re-parsed and re-diffed the whole answer on every animation
  frame, so a long reply got slower the longer it streamed (O(n²) parse plus a
  new object for every block, which defeated memoization). `lib/chat/markdown.ts`
  now exposes `stableBoundary()` and `parseMarkdownStream()`: only the part
  after the last completed block boundary is parsed, earlier blocks are returned
  by identity, and `Block` is memoized — already-written prose is neither
  re-parsed nor re-rendered. Boundaries are conservative (an open fence, display
  math or a continuing blockquote stops the cut), and a test asserts the
  incremental result equals one full `parseMarkdown` at every growth step.
  Separately, `RunEmitter` now feeds a `RunTimings` recorder and writes ONE
  durable `run.timings` event after the terminal event with `setupMs`
  (run.started → first model.requested), `ttftMs` (model.first_token),
  `firstDeltaMs` and `deltaGapP50/P95/Max` over the transient `model.delta`
  gaps — so "feels stuck" can be attributed to setup, provider latency or token
  cadence instead of guessed at. Deltas stay transient; the record is one row
  per run. Tests `src/lib/chat/markdown-incremental.test.ts` (19),
  `python/tests/test_run_timings.py` (4). docs updated:
  `docs/harness/architecture.md` (§ Live streaming), `docs/harness/observability.md`.
- **feat(chat): `!` shell mode in the composer (OpenCode parity).** Typing `!`
  at the start of an empty prompt now runs a shell command instead of sending a
  prompt: Enter runs it in the session workspace, Esc leaves the mode, Shift+Enter
  still inserts a newline. The run is appended to the conversation as a user turn
  carrying `Message.shell` (command, cwd, real exit code, stdout/stderr, duration,
  timeout/truncation flags) and rendered by `shell-run-card.tsx`; no agent run is
  dispatched for it. The NEXT turn sends `formatShellForHarness` — the command,
  12k-bounded output and exit status, labelled "observed data, not instructions" —
  so the run stays in session context rather than in a detached terminal pane.
  Honesty: a failed command reports its real non-zero exit code; an unavailable
  or refusing runtime records an explicit unavailable turn. `ModelSelector` moved
  from `chat-input.tsx` to `model-selector.tsx` (re-exported, imports unchanged)
  to keep the composer under the size ceiling; size pin stock-chat 1717→1718.
  Tests `src/lib/chat/shell.test.ts` (13). docs updated: `docs/chat-ui-audit.md`
  (§ `!` shell mode), `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(voice): the composer catches fire when you dictate.** Tapping the mic
  now morphs **both** chat composers (full `chat-input` and floating
  `chat-dock`) into an interactive ember field instead of just starting a hidden
  recording. New `src/lib/voice/meter.ts` (AnalyserNode
  RMS + spectral centroid, pure `rmsToLevel`/`smoothLevel`/`spectralCentroid`),
  `src/lib/voice/fire-field.ts` (framework-free, seeded heat advection + ember
  pool + pointer wind), and `src/components/chat/voice-fire-field.tsx` (canvas
  host, source-over glow, 30 fps cap, DPR ≤ 2, one static frame under reduced
  motion, DOM transcript with `aria-live`). `use-voice-input` now exposes
  `meterRef` + `interim` and feeds the meter from the recorder's own stream on
  the Whisper path and from a visual-only capture on the browser path (failure
  degrades to the idle smoulder, never blocks dictation). `VoiceInputButton` is
  split into a controlled `VoiceInputButtonView` so `chat-input.tsx` can own the
  session, morph on `data-voice`, hide the textarea while keeping it mounted,
  and handle the keyboard while listening (Esc cancels, Enter stops). Desktop stays
  honest: WebView2 has no SpeechRecognition, so the flame reacts but words land
  after transcription. Tests `src/lib/voice/{meter,fire-field}.test.ts`. The `@`
  palette moved to `src/components/chat/mention-palette.tsx` so the composer
  stays under the 1200-line ceiling (1197). docs updated: `docs/voice.md`,
  `docs/voice-fire-field-plan.md` (partially shipped), `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`; `docs/voice-ascii-wave-plan.md` marked Superseded.
- **docs(voice): supersede the ASCII wave plan with an interactive fire field.**
  New `docs/voice-fire-field-plan.md` specifies the effect actually wanted: the
  mic tap morphs the composer into a canvas ember field — an advected heat field
  with a heat ramp, an additive ember pool, and pointer "wind" — driven by a new
  `VoiceMeter` (RMS + spectral centroid). Loudness drives height/ember rate, the
  centroid drives colour temperature, the cursor bends the flame, and Stop banks
  it down before the transcript inserts at the caret. Same plumbing as before
  (hook hoisted out of `VoiceInputButton`, `data-voice` morph, interim via the
  unused `onInterim`), plus a performance contract (no React per frame, 30 fps,
  particle budget, pause on hidden) and honest limits (desktop is Whisper-only,
  so no live text while speaking; reduced motion gets a static ember frame).
  `docs/voice-ascii-wave-plan.md` is marked Superseded, not deleted. docs
  updated: `docs/voice-fire-field-plan.md` (new),
  `docs/voice-ascii-wave-plan.md` (Superseded), `docs/CHANGELOG.md`.
- **feat(chat): Retry resumes a failed run instead of starting over.** A
  `failed` run is no longer terminal: Retry re-enters the SAME run at its last
  non-terminal checkpoint (completed tool calls are reused), clears the prior
  terminal error, and falls back to a fresh run only when the checkpoint cannot
  be resumed (completed/cancelled, or a terminal boundary). `graph.py` also
  routes `END` explicitly out of `verify_repair`/`tools`, refuses to overwrite a
  precise terminal status (e.g. `RUN_TIMEOUT`) with `INTERNAL_ERROR` when a late
  error escapes, and the default chat run timeout is 20 minutes (10 minutes
  killed real 20-step research turns just before the answer). The compression
  ladder is now ON by default (`HARNESS_COMPRESSION_LADDER=on`) so the extra wall
  clock is not extra prompt cost. Tests: `test_run_resume.py`,
  `run-manager.test.ts`. Size pin: `graph.py` 2763→2797. docs updated:
  `docs/CHANGELOG.md` (no architecture change — behavior and defaults only).
- **docs(voice): plan an ASCII-wave voice field for the composer.** New
  `docs/voice-ascii-wave-plan.md` (status: Proposed) specifies turning the chat
  composer into a live ASCII wave while dictating and adding a streaming
  transcript, without changing the dictation pipeline: a new
  `src/lib/voice/meter.ts` (AnalyserNode RMS, pure level maths),
  `src/lib/voice/wave-field.ts` (pure ring/ramp maths), a canvas
  `voice-wave-field.tsx`, the hook hoisted out of `VoiceInputButton` so the
  composer can morph on `data-voice`, interim text through the existing unused
  `onInterim`, and honest limits (desktop/WebView2 has no browser STT, so it
  gets amplitude + a post-stop reveal; reduced-motion gets a static frame).
  Phased P0–P3 with tests and risks. docs updated:
  `docs/voice-ascii-wave-plan.md` (new), `docs/CHANGELOG.md`.
- **test(accounting): hardcore cross-book accounting prompts + offline suite; 6
  real bugs fixed.** Added `docs/accounting-hardcore-tests.md` (20 chat prompts
  with pass rules for the double-entry General Ledger and the securities
  Portfolio Accounting Engine) and `python/tests/test_accounting_hardcore.py`
  (24 deterministic cases). Bugs found and fixed in the portfolio core:
  (1) a SELL carrying only a settled `net_amount` booked zero proceeds and a
  fabricated total loss (now uses the net amount; cash ledger follows); (2) an
  oversell clamped to available quantity divided the full gross by the reduced
  quantity, inflating proceeds (now prorated over the requested quantity);
  (3) the documented `acquired − disposed == remaining` invariant broke after
  every split — both rollups are now restated in post-split share units;
  (4) `SPECIFIC_ID` lot ids were random per recompute, so a lot id read from
  `tax_lots` could never be found when the sell posted (now deterministic
  `lot_<transaction id>` ids, deterministic match ids); (5) an unknown,
  duplicate or malformed lot designation silently fell back to FIFO (now
  `LOT_MISMATCH`/`INVALID_TRANSACTION`, and the service refuses the write); a
  `lot_selection` on a non-`SPECIFIC_ID` book is refused rather than ignored;
  (6) average-cost matches reported the sell date as the acquisition date,
  fabricating a 0-day holding period (now uses the earliest pooled shares
  consumed). Also: net-only deposits/withdrawals/dividends now report their
  settled cash, and `calculate_tax_lots` computes each symbol once. docs
  updated: `docs/accounting-hardcore-tests.md` (new),
  `docs/portfolio-accounting.md`, `docs/ledger.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **feat(desktop): desktop-only product with Stable and Dev channels; the
  website lane is retired.** One channel table (`scripts/lib/channels.js`):
  Stable 3100/harness 8767, Dev 3101/harness 8768, separate builds, pins,
  versioned releases and runtime data. `desktop:dev` builds `.next-desktop-dev`
  and launches a separate Dev shell (own Tauri identifier via `TAURI_CONFIG`,
  `target-dev`); `desktop:promote` stages + validates `releases/<channel>/<id>`,
  moves `current.json` (keeping `previous.json`) and restarts only that channel;
  `desktop:rollback` flips back; `desktop:doctor` reports window/port/build/
  harness/provider. `npm run dev/up/start/proxy` (and `start-eclipse.vbs`) are
  gated behind `BE_ALLOW_WEB=1`; `setup:desktop` now targets the installed
  native app. Dev data is isolated under `.black-eclipse/desktop-dev/` with a
  one-time `VACUUM INTO` copy of `jdds.db`. Two live-launch bugs found and fixed
  in QA: the bootstrap readiness budget was 90 s and Next measured 126 s under a
  concurrent build (a healthy child was left unowned and the window showed a
  failure panel) — now 300 s; and the Dev window lookup JSON-escaped a Windows
  path (`\\`), so `stopShell` matched nothing and single-instance silently kept
  the stale window — now a PowerShell single-quoted path. Also: harness readiness now probes a
  constant-time `/health/live` with a 30 s budget (the 20 s diagnostic `/health`
  under load made a healthy runtime look dead and restart-loop), and
  `isHarnessHealth` accepts `harness-runtime`. docs updated:
  `desktop/README.md`, `docs/environments.md`, `docs/QUICKSTART.md`,
  `docs/NAVIGATION.md`, `docs/local-hostname.md`, `docs/CHANGELOG.md`.
- **feat(updates): desktop-first release updates.** `black update` now re-pins
  and restarts the native desktop app (`scripts/desktop-refresh.js`) right after
  a successful build, before anything web-facing is considered. The browser
  production server on 3105 is secondary and only restarts with `--restart`;
  `--no-desktop` skips the app refresh for web-only machines. Encoded the rule
  as an always-on engineering rule and documented why desktop-only (3100 alone)
  is a supported configuration. docs updated: `AGENTS.md`, `docs/UPDATES.md`,
  `docs/environments.md`.
- **fix(agent): a portfolio question can no longer end with no answer.**
  Root cause (QA of 15 stored runs): `portfolio_get` fetched quotes one symbol
  at a time with no per-call timeout, so one slow PSX quote consumed the tool's
  20 s budget and returned `TOOL_TIMEOUT`. The agent then guessed app routes
  (`/api/journal/open`, `/api/broker/positions`, …); each 404 came back as a
  42 KB HTML page, `/api/journal/trades` ignored `?limit`/`?status` and returned
  104 KB every time, and the run hit its deadline with partial text only.
  Fixes: `MarketAdapter` bounds each quote/FX lookup
  (`PORTFOLIO_MARK_TIMEOUT_S`, default 8 s) and reports a MISSING mark;
  `PortfolioService.read` resolves symbols concurrently (bounded 6);
  `app_api_get` turns an HTML 404 into a short "no such API route — do not
  guess" result; `GET /api/journal/trades` honours `limit`/`take`, `status`,
  `symbol` (filters before limit, adds `count`/`total`). Verified end to end:
  the reported question ("look at my current trade…") now completes in 167 s
  with a full trade/risk answer. Tests: new
  `python/tests/test_portfolio_market_adapter.py`, extended
  `test_app_api_tools.py` and `route.test.ts`. docs updated:
  `docs/portfolio-accounting.md`, `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **feat(desktop): the window survives an in-flight `next build`.**
  3100 is now the desktop's own port and the app serves an immutable pinned copy
  of the last completed build (`.black-eclipse/desktop-dist/.next`); the
  website/agent production profile moved to 3105 (dev stays 3000). A checkout
  never attaches to a website server — only to its own owner-marked pinned
  server. `npm run desktop:refresh` builds, re-pins and reopens. docs updated:
  `desktop/README.md`, `docs/desktop-app-plan.md`, `docs/environments.md`,
  `docs/QUICKSTART.md`, `docs/local-hostname.md`, `docs/DEPLOYMENT.md`,
  `docs/NAVIGATION.md`.
- **fix(chat): dark bubble tuned one step darker.** A 30% foreground tint read
  too light next to the theme; the default is now `24%` (~#414141), which stays
  visibly grey while keeping the theme's contrast. docs updated:
  `docs/ARCHITECTURE.md`.
- **feat(desktop): one-command refresh for the dev-bridged desktop window.**
  Added `npm run desktop:refresh` (`scripts/desktop-refresh.js`): builds only
  when source is newer, restarts the 3100 server via `up.js --restart`, and
  reopens the shell — so a source edit no longer leaves the window serving a
  stale `.next` build. Leaves packaged (non-bridged) installs alone. docs
  updated: `desktop/README.md`.
- **fix(chat): the dark-mode prompt bubble reads grey, not black.** The default
  dark fill was a 20% foreground tint, which still composited to ~#303030 over
  the near-black chat surface. Bumped the default (CSS fallback, prefs resolver,
  and the Settings pick fallback) to a 30% tint (~#4c4c4c). docs updated:
  `docs/ARCHITECTURE.md`.
- **fix(chat): the "Eclipse has a question" prompt spans the composer width.**
  `ClarificationCard` was capped at 720px, so it floated as a narrower island
  above the full-width composer. It now uses the anchor's measured width.
  no doc change — visual fix.
- **fix(chat): a finished answer can no longer disappear from a conversation.**
  The transcript is written by the browser in two steps: an empty
  `status: "queued"` placeholder at send time, then the answer when the run
  resolves **in the same tab**. A reload / second tab / app restart mid-run left
  that empty placeholder as the last turn forever, while the answer sat safely in
  `HarnessRun.output` — the conversation looked erased. New
  `src/lib/chat/transcript-reconcile.ts` runs from `GET /api/chat/transcript`:
  it finds a stuck last turn, matches it to a COMPLETED run (the turn's `runId`,
  else the session's newest completed run that started after the prompt), fills
  the content, clears any stale error, and writes it back through
  `writeTranscript` (which keeps the fuller/terminal copy). Throttled to one pass
  per 5 minutes, no-op when nothing is stuck, never touches failed/cancelled or
  non-empty turns. `RunRecord` gained the runtime's `sessionId`. History was
  also restored once: 19 conversations were rebuilt from their run records (per-
  file backups kept as `transcript.json.bak-*`). Tests: new
  `transcript-reconcile.test.ts` (11 cases). Also: split the run-patch
  serializer into `harness/run_patch.py` (persistence was over its size pin) and
  re-pinned the size ratchet for the committed concurrency growth
  (`service.py` 2068→2072, new `model_runtime/runtime.py` entry). docs updated:
  `docs/chat-ui-audit.md`, `docs/harness/architecture.md`, `docs/CHANGELOG.md`.

## 2026-11-12
- **fix(harness): runs now reach their TRUE terminal status (the "every run
  fails / times out" bug).** `run_lease.fenced_update_run()` bound `error`,
  `context` and `research` dicts straight to SQLite parameters; that raises
  `ProgrammingError`, the writer swallowed it and returned `False`, and the
  graph ignored the boolean. Every terminal write (completed / failed /
  cancelled) was silently dropped: the run row stayed `running` after the answer
  streamed, the lease was released, and the stall watchdog relabelled the
  finished run `RUN_STALLED` with a ~100-char "partial" minutes later. Progress
  and flag writes that carried a dict were dropped the same way. Fixed with one
  shared serializer (`persistence.run_patch_sql`, used by `update_run` AND the
  fenced writer), loud error logging, and one retry for a transient lock. The
  watchdog now reconciles a non-terminal row from its durable terminal event
  instead of overwriting a finished run, and it self-heals history an older
  build already mislabelled (a completed run marked RUN_STALLED is corrected to
  completed, its bogus error cleared). Its silence budget floors on the 300s
  per-call ceiling (a 250s in-flight model call is healthy, not stalled).
  The default chat agent's RUN wall clock is now 600s
  (`ECLIPSE_CHAT_RUN_TIMEOUT_S`): `runTimeoutMs=120s` is the per-MODEL-CALL
  budget and was wrongly used as the whole-run deadline, so every real research
  turn died with RUN_TIMEOUT at 120s. Tests: `test_run_lease` (dict payload),
  `test_run_watchdog` (reconcile + resume), `test_chat_step_budget` (wall clock).
  docs updated: `docs/harness/architecture.md`, `docs/CHANGELOG.md`.
- **feat(desktop): one UI for the desktop shell and the web app
  (`desktop:dev-bridge`).** The installed Tauri shell preferred its frozen
  `<install>\app` payload over the repo, so it could show an old build while the
  web app was current. `scripts/desktop-dev-bridge.js` preserves the bundled
  payload as `app.bundled-<version>` and installs a small
  `app\scripts\desktop-server.js` bridge that runs the repo's
  `scripts/desktop-server.js`; both front doors now share one `.next` build and
  one data directory. Run `npm run desktop:dev-bridge` after a fresh installer.
  docs updated: `docs/desktop-app-plan.md`, `docs/CHANGELOG.md`.
- **fix(chat): solid busy-state controls and roomier error card.** While a turn
  runs, the Queue/Stop controls are now solid fills (no outline pill), and the
  "Something went wrong" card gets extra bottom padding plus spacing beneath it
  so the Retry action no longer hugs the card edge. no doc change — visual fix.
- **feat(chat): durable, shared, pausable prompt queue.** `queue-store.ts`
  persists each conversation's queue in `localStorage`, broadcasts changes over
  BroadcastChannel, and dequeues under a per-chat Web Lock so two tabs cannot
  run the same prompt. The queue panel gained pause/resume; the drain hook
  resumes persisted work on mount for idle, unpaused chats. In-memory fallback
  keeps private-mode sessions working. Tests: new `queue-store.test.ts`;
  `tsc` clean and size ratchets green. docs updated:
  `docs/harness/multi-session-concurrency.md`, `docs/CHANGELOG.md`.
- **fix(legal): stop the risk-notice banner overlapping chat and nagging every
  reload.** The local (non-hosted) reminder moved from a bottom-centre banner
  (which sat on top of the chat composer and crossed the sidebar column) to the
  top-right corner, and its dismissal now persists in `localStorage` instead of
  per-session `sessionStorage`. Consent is still only recorded by Review →
  Accept. no doc change — UI/UX bug fix, no contract change.
- **feat(model): quota-aware admission + cross-tab runs.** Provider capacity is
  now a shared, process-wide gate: `get_credential_pool()` shares 429 cooldowns
  and key rotation across runs, `RateLimitManager.acquire_slot()` queues on a
  FIFO semaphore plus cooldown/RPM/TPM windows, `HARNESS_MODEL_CONCURRENCY`
  (default 2) bounds parallel calls per provider/model/credential, and `Retry-After` is
  honored (it was previously ignored). Waiting emits `model.queued` and is bounded
  by `HARNESS_MODEL_COOLDOWN_WAIT_S` (default 60); past it the run fails honestly
  with `RATE_LIMITED`. Cross-tab: `tab-coordinator.ts` elects one owner per chat
  with Web Locks, shares `runId`/snapshots over BroadcastChannel +
  `localStorage`, lets followers attach/act by run id, and merges transcripts by
  message id in both the client cache and `writeTranscript()`; `GET /sessions/{id}`
  returns `activeRun` as server truth. Tests: new `test_model_admission.py`,
  `chat-organization` cross-tab merge; full Vitest 518 files / 4756 tests,
  affected Python suites green, `tsc` clean. docs updated:
  `docs/harness/multi-session-concurrency.md`, `docs/CHANGELOG.md`.
- **feat(chat): run multiple conversations concurrently.** The chat shell
  mounted one `useAgentRun` and refused a second run. A conversation-scoped
  `run-manager.ts` now owns one stream per `chatId` (many chats at once), the
  hook is a thin selector, each run has its own `onTurn` sink, queued prompts
  keep their originating chat (`use-chat-queue-drain.ts`), active-run recovery
  is a `chatId → run` map, and only the focused chat's run feeds the Agent
  Workspace. The runtime's process-wide market bridge/MCP sampling model are
  per-run `ContextVar`s (`run_binding.py`) instead of singleton fields, so
  concurrent runs cannot cross-wire transports or models. Tests: new
  `run-manager.test.ts`, `run-focus.test.ts`, queue chat-scope test,
  `test_run_binding.py`, and a concurrent-bridge service test; full Vitest +
  `tsc` green. docs updated: `docs/harness/multi-session-concurrency.md`,
  `docs/harness/architecture.md`, `docs/CHANGELOG.md`.
- **fix(bots): make user bubbles and the composer grey frosted glass.** The bot
  and group chat pages hardcoded `bg-white/[0.08]` prompt bubbles (which read as
  black over the dark conversation surface) and the bot composer used the
  near-black `.glass-card` tint. Both now use the shared `.chat-bubble` fill, and
  both composers use `.glass-composer` (neutral zinc tint + real backdrop blur),
  matching the Eclipse Agent page. The shared dark bubble default is now 20%
  foreground (clearly grey); the composer is back to its original near-transparent
  glass tint (`--card-rgb` at 0.16, blur 28px) so the transcript reads through it
  instead of a flat grey panel; the GoalBar
  now calls a client-safe `autonomy-browser.ts` front-door API instead of the
  server-only `autonomy-client` (which pulled `fs`/`child_process` into the
  browser bundle and failed the production build). docs updated:
  `docs/harness/autonomy.md`, `docs/CHANGELOG.md`.
- **test(security): hardline denial without a gateway.** Adds a regression test
  proving `make_security_authorizer` refuses a destructive command via the
  always-on hardline even when no gateway/policy is installed, while a benign
  command falls through to the permissive inner authorizer. docs updated:
  `docs/CHANGELOG.md`.
- **chore(harness): finalize W4 autonomy and land run-kernel hardening.** The
  goal judge now has a hard 120s timeout and the loop emits `goal.gate.started`
  before each deterministic gate; the gated research finisher carries the
  fenced `runtime_id`; W6 adds pre-tokenization hardline denial in the code
  terminal plus checkpoint/event-sequence hardening; touched files are
  LF-normalized and the size ratchets stay green. Tests: W4 (15+6), targeted
  goal/task/automation/session/checkpoint suites, full Vitest (516 files /
  4749 tests), eval gates ALL PASS, `tsc` clean. docs updated:
  `docs/harness/autonomy.md`, `docs/CHANGELOG.md`.
- **fix(harness): regenerate the tool registry and finish line-ending
  normalization.** `npm run eval:registry` now publishes 1,100 tools (digest
  `8e314b7245ccf458`), so `test_public_api` matches a fresh generation again;
  `code-browser.ts` and `i18n/dictionaries/builds.ts` are LF-only, so the
  gitignore guard sees no mixed-ending file. Docs:
  `docs/harness/tool-registry.json` (generated).
- **fix(harness): keep the tree green after the W4/checkpoint merge.** Passes the
  run's fenced `runtime_id` into `_finish_research` (a concurrent W6 change left
  it undefined, failing every gated research run), normalizes mixed CRLF/LF in
  `routers/recovery.py` and the touched command files, and extracts the
  `/rollback` + `/terminal` specs and the `/rollback` handler into
  `command-specs-dev.ts` / `command-handlers-dev.ts` so the size ratchets hold
  while the W4 command specs/handlers live in their own modules. Tests: full
  vitest (516 files / 4749 tests) green, targeted Python (208 + 1408 tail)
  green, eval gates ALL PASS, `tsc` clean. Docs: `docs/CHANGELOG.md`.
- **feat(harness): W3 tool execution (core).** Adds `tool_turn.py` (the ONE
  preflight/dispatch/postflight flow; contiguous `parallel_safe` batches,
  semaphore + batch deadline, per-call context clone, index-addressed results,
  effectful/interactive calls always serial), `tool_guardrails.py` (pure
  success-signature/cycle/failure-streak controller; warn-first, controlled
  halt, poller exemption, operator reset), `tool_bm25.py` + `tool_disclosure.py`
  (BM25 with tags/domain, tiered catalogue block, `auto` threshold over a
  known window, `availableSources`), and the matching `ToolDefinition` fields
  (`interactive`, `parallel_safe`, `tags`, `domain`). `graph.tools_node` is now
  wiring; the guardrail-halt route ends the run with a deterministic notice.
  Flags: parallel `off|shadow|on`, guardrails `warn|halt|off`, disclosure
  `auto|on|off`; `HARNESS_LAZY_TOOLS` is a deprecated alias. First audited
  parallel tools: `tool_search` + the response-contract read-backs; `clarify`
  is interactive. Tests: `test_parallel_tools.py`, `test_tool_guardrails.py`,
  `test_tool_disclosure_bm25.py`, extended `test_flags.py`,
  `test_run_effects.py`, `test_size_budget.py`. Harness gate: 1,250 passed /
  3 skipped (graph/context/tool/run/recovery) plus 2,046 passed / 4 skipped
  (agent/prompt/plugin/skill/evaluation/persistence group); `audit:agent`
  49/49, offline eval gate ALL PASS, `tsc --noEmit` clean. Docs:
  `docs/harness/roadmap/w3-tool-execution-plan.md` (status + §15),
  `docs/harness/roadmap/hermes-inspired-improvement-plan.md`,
  `docs/harness/roadmap/w0-flags-and-review.md`.
- **feat(harness): W8 observability, SLOs and conformance (implemented).** Adds
  `observability/signals.py` (bounded W8 aggregates + stable metric mapping),
  `observability/bridge.py` (the same projector for subsystems with no
  `RunEmitter`), eager objective registration with `measured:false` /
  `healthy:null` / `unmeasured` (and `ensure`, fixing the per-event counter
  reset), report schema v2 (`capabilities`, model/context/goals/learning/
  integrity/fileCheckpoints/delegation sections, TTFT, resume success), and
  projection for gateway attempts/TTFT/fallback, context pressure/compression,
  tool batches/guardrails, goal verdicts, skill evaluation, curator runs,
  effect-unknown, lease-loss, checkpoint writes, event-sequence collisions,
  hardline blocks, file checkpoints and delegation. The gate is now
  declarative (`path`/`kind`/`samplesPath`/`minSamples`/`requires`/
  `requireSamples`/`enforce`) with `skipped`/`unmeasured`/`observed`, path
  validation and zero-tolerance invariants; `slo-budgets.json` is version 2.
  The probe emits every W8 signal; the dashboard has a third `unmeasured`
  state and new model/context/integrity cards; the Prometheus rules file has
  real SLO + integrity rules; conformance grows to 28 cases including the
  alert-metric contract. Tests: `test_w8_observability.py` (14), conformance
  28/28, `gate:slo` 19/19. Docs:
  `docs/harness/observability.md`, `docs/harness/conformance.md`,
  `docs/DEPLOYMENT.md`, `docs/harness/decisions.md` (ADR-H360),
  `docs/harness/roadmap/w8-observability-and-slos-plan.md`,
  `docs/NAVIGATION.md`. Also re-pins `scripts/size-budget.json` to the measured
  landed tree (the W0–W8 runtime + W8 signals) so the size gate stays green;
  per-file ratchets unchanged. No schema change, no new dependency.
- **test(harness): W2 closeout verification.** W2-focused suite 159 passed; full
  tree vitest 4,749 passed and pytest 10,718 passed / 35 skipped. Seven pytest
  failures during the 42-minute shared-tree run were concurrent-edit artifacts
  (the other stream changed `eclipse_memory/*`, `main.py`, flags and the
  registry mid-run); each failed file passed on immediate rerun (30 passed).
  tsc clean, audit 46/46, conformance 16/16, SLO 8/8, live NOT MEASURED.
  Docs: `docs/harness/roadmap/w2-context-economics-plan.md` §15.
- **feat(harness): W7 async delegation, schema repair, steering, worktrees and
  file checkpoints.** `delegation_store.py` adds the durable
  `HarnessDelegation`/steer rows; `delegation_lifecycle.py` runs one child as a
  Fabric `delegation` job, validates `output_schema`, performs at most one
  tool-less repair, drains steering only at a step boundary, supports isolated
  per-child worktrees with diff handles, and persists one terminal outcome.
  `delegation_async_tools.py` adds `delegate_async/status/result/cancel/steer/
  wait`; `delegation_repair.py` implements bounded schema validation.
  `code/checkpoints.py` adds a shadow-git snapshot store (one per run/turn,
  protected-path excludes, size/retention caps, pre-restore snapshots), hooked
  into `FileSystemService`, `shell_run` and promotion, with `checkpoint_*`
  tools, `/code/checkpoints*` routes, `/rollback`, and a Code-screen panel.
  Flags: `HARNESS_FILE_CHECKPOINTS` is now `off|warn|enforce`; async/schema/
  steer/completion flags added. Tests: `test_delegation_lifecycle.py`,
  `test_file_checkpoints.py`. Docs: `docs/harness/code-filesystem.md`,
  `docs/harness/roadmap/w7-delegation-and-file-safety-plan.md`; the tool
  registry was regenerated (1,100 tools).
- **feat(harness): W6 run-kernel integrity and safety.** Adds
  `fenced_progress`/`LeaseLost` and threads `runtime_id` through
  `RunScope`/`execute_run` so every progress/terminal write proves the caller
  still owns the lease (`RUN_LEASE_LOST` otherwise); `RunLineage.save_boundary`
  commits the message cursor and checkpoint in one transaction
  (`CHECKPOINT_WRITE_FAILED` on a persistent failure); pre-dispatch
  `ToolExecutionIdempotency.state` (`started|done|unknown`) with
  `mark_tool_started`/`done`/`unknown` and guaranteed effect
  `finish`/`mark_unknown`; `event_sequence.EventSequence` for a durable
  per-run seq inside `BEGIN IMMEDIATE` plus a unique `(runId, seq)` index and
  legacy duplicate repair; a lease-aware watchdog; `security/hardline.py` for
  always-on destructive-command denial; `SECURITY_UNAVAILABLE` under enforce;
  and `code/shell.py` routed through `code/sandbox.run` /
  `terminal.spawn.spawn_process` (tree kill, scrubbed env, named refusal).
  Tests: `test_events_sequence.py`, `test_hardline.py`,
  `test_shell_sandbox_parity.py`, `test_run_kernel_faults.py` plus extensions
  to lease/lineage/watchdog/effect-token suites. Deliberate gap: effect-token
  default stays `shadow` pending ADR + canary. Also re-pins the Python size
  ratchet to the measured shared-tree lines (pre-existing W3/W5 growth). Docs:
  `docs/harness/roadmap/w6-run-kernel-integrity-plan.md`,
  `docs/NAVIGATION.md`.
- **fix(harness): W5 operational follow-ups.** The Next.js runtime launcher now
  publishes the saved app model as `ECLIPSE_SKILL_EVAL_MODEL` (plus key/base URL)
  so boot/draft execution evaluation works without a second credential; the
  evaluate client also sends per-request `modelSettings`. Failed/needs-review
  execution attempts are held for `HARNESS_SKILL_EVAL_RETRY_HOURS` (default 12)
  instead of re-running every boot. BM25 now ranks over the same canonical
  synonym/stem vocabulary as the lexical scorer. Curator `apply` hands archive
  suggestions to the one maintenance pass, and merged instructions are
  de-duplicated line-by-line. Docs:
  `docs/harness/roadmap/w5-learning-loop-plan.md` §13 update.
- **feat(harness): W5 learning loop (core).** Adds
  `skills/execution_eval.py` (real execution tier through
  `ExecutionMode="evaluation"`, existing graders, `ExecutionEvalResult`,
  `RuntimeSkillInvoker`) and wires `HARNESS_SKILL_EXEC_EVAL` into
  `evaluate_skill`, `promotion_gate`, `request_promotion`, `activate_version`,
  `_enable_skill` and the boot draft/usage sweeps: a learned skill cannot enable
  on a static-only pass, and the named execution run ids must exist. Adds
  `skills/curator.py` (deterministic duplicate/near-duplicate/eval-debt/tag-drift
  scan, pinned/compliance/external skips, intersection permissions, inert merge
  drafts, cadence + lock) with `SkillCuratorRun`/`SkillCuratorProposal` tables,
  startup hook, `/skills/curator*` routes and `HARNESS_SKILL_CURATOR` modes.
  Adds `eclipse_memory/bm25.py` (corpus IDF) and the
  `HARNESS_MEMORY_HYBRID` bounded ranking branch with unchanged safety gate;
  diagnostics expose component scores. `/learn` is an alias of the existing
  inert `skill-create` path. Additive migrations 36–37 (evaluation evidence,
  authored case spec, curator ledger). New tests: execution gate, curator,
  BM25, hybrid rank; docs: `docs/harness/roadmap/w5-learning-loop-plan.md`
  (§13 status/gaps), `docs/harness/architecture.md`.
- **feat(autonomy): W4 goals, deterministic gates, judge and loops.** Adds the
  `HARNESS_GOAL_LOOP` flag (off/shadow/on; `HARNESS_AUTONOMY=off` still vetoes),
  extends `GoalContract` with `verification`/`boundaries`/`stop_when` and adds
  `GoalGate`; migration `2026-11-12-006-goal-autonomy` adds the goal
  contract/turn/session columns plus `GoalVerdict`, `GoalGateRun` and
  `AutonomyLoop`. New `goals/gates.py` runs ONLY closed `COMMAND_CLASSES`
  through `build_argv` + `decide_command` + `sandbox.run` (tail-only output; a
  failing exit is definitive, infrastructure only is retried);
  `goals/judge.py` is advisory, strict-JSON, one repair, and never turns a red
  gate green; `goals/goal_runtime.py` creates a durable task per turn, evaluates
  gates before the judge, continues with a compact brief, and enforces
  turn/no-progress caps; `goals/loop_runtime.py` runs session loops/heartbeats
  on the EXISTING automation tick (idle-only, coalesced, digest-suppressed,
  capped); `goals/bootstrap.py` bridges terminal task events and health.
  Adds operator-gated `/goals` and `/loops` routes, the Next.js front door and
  typed client, `/goal` `/loop` `/heartbeat` commands, and the chat goal bar.
  Tests: `test_w4_autonomy.py`, `test_w4_autonomy_api.py`; existing
  goal/task/automation/flag suites stay green. Docs:
  `docs/harness/autonomy.md`, `docs/harness/roadmap/w4-autonomy-plan.md`,
  `docs/harness/roadmap/w0-flags-and-review.md`,
  `docs/harness/roadmap/hermes-inspired-improvement-plan.md`,
  `docs/NAVIGATION.md`, `.env.example`.
- **docs(roadmap): complete W8 observability, SLOs and conformance plan.** Adds
  `docs/harness/roadmap/w8-observability-and-slos-plan.md`: grounded
  current-state ledger (W1 attempt/TTFT and W2 context events are emitted but
  dropped by the projector; objectives are registered lazily so missing work is
  silently absent; `gate.py` hardcodes five checks), the normative per-workstream
  signal dictionary, the SLO vs invariant split with targets/minimum samples,
  report schema v2 + `capabilities`, eager objectives with an honest
  `unmeasured` state, the data-driven budgets/gate design, real Prometheus
  rules, twelve conformance cases (including an alert-metric contract), slices
  W8.0–W8.7, test matrix, rollout and exit criteria. Planning only — no
  production code changed. Docs:
  `docs/harness/roadmap/w8-observability-and-slos-plan.md`,
  `docs/harness/roadmap/hermes-inspired-improvement-plan.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **docs(roadmap): complete W7 delegation & file safety plan.** Adds
  `docs/harness/roadmap/w7-delegation-and-file-safety-plan.md`: grounded
  current-path evidence (synchronous `delegate`, no schema/steer, in-memory
  `FileTransaction`, direct writes), the Fabric-backed `delegate_async`/
  status/result/cancel/wait lifecycle with durable `HarnessDelegation`/steer
  rows, the bounded `output_schema` + one-repair contract, step-boundary
  steering, per-child worktrees with diff handles, the shadow-git checkpoint
  store with protected-path excludes, `checkpoint_*` tools and the operator-gated
  `/rollback`, slices W7.0–W7.6, fault matrix, flags, rollout and exit criteria.
  Parent plan, flag matrix and NAVIGATION now point at it. Planning only — no
  production code changed. Docs:
  `docs/harness/roadmap/w7-delegation-and-file-safety-plan.md`,
  `docs/harness/roadmap/hermes-inspired-improvement-plan.md`,
  `docs/harness/roadmap/w0-flags-and-review.md`, `docs/NAVIGATION.md`.
- **docs(roadmap): complete W6 run-kernel integrity plan.** Adds
  `docs/harness/roadmap/w6-run-kernel-integrity-plan.md`: grounded current-state
  audit (W6 flags have no consumers, progress counters unfenced, checkpoint and
  message cursor commit separately, idempotency is post-execution, event seq is
  per emitter with no unique constraint, watchdog ignores leases, no command
  hardline, `code/shell.py` bypasses the sandbox, effect tokens default to
  shadow), the contracts (`fenced_progress`/`RUN_LEASE_LOST`,
  `RunLineage.save_boundary`, `started|done|unknown` idempotency,
  `append_event_sequenced` + duplicate-seq repair, lease-aware `find_stalled`,
  `security/hardline.py`, shell via `code.sandbox`/`terminal.spawn`, staged
  effect-token enforce), slices W6.1–W6.7, fault matrix, test plan, rollout,
  risks and exit criteria. Planning only — no production code changed. Docs:
  `docs/harness/roadmap/w6-run-kernel-integrity-plan.md`,
  `docs/harness/roadmap/hermes-inspired-improvement-plan.md`,
  `docs/NAVIGATION.md`.
- **fix(harness): overflow recovery reaches the graph, and effect `unknown`
  blocks it.** `model_stream.ainvoke_streaming` used to catch every stream
  failure as "streaming unsupported" and silently re-invoke the model, which
  hid a provider `CONTEXT_OVERFLOW` and made an extra call; it now re-raises a
  classified overflow. `run_recovery.recoverable_state` uses
  `RunEffects.has_unconfirmed` (started **or** unknown), so a reconciled
  unknown effect cannot be replayed. Tests: `test_context_overflow.py` (17),
  `test_context_recovery.py` (4), `test_prompt_segments.py` cache-plan cases.
  Docs: `docs/harness/roadmap/w2-context-economics-plan.md` §15.
- **feat(harness): W2 closeout — unified ladder, cache markers, tool-bearing
  recovery.** `context/compression_ladder.py` now owns prune → summary →
  skeleton (protected tail/last user turn/assistant-tool pairs, persisted
  cooldown, `/compact` force, shadow/on/off) and is used by the tool turn, the
  hard/emergency pre-call gate and overflow recovery. `prompt_segments.py` adds
  `PromptCachePlan`/`build_cache_plan`/`apply_cache_markers`: one Anthropic
  `ephemeral` marker on the stable system block, prefix ordering for
  OpenAI-compatible providers, none elsewhere; `step.invoke_model_step` applies
  it at request time and `prompt.cache` is emitted. `run_recovery` accepts a
  completed-work (`tool_results`/`replan`) checkpoint with no
  `started`/`unknown` effect, so a tool-bearing step>1 overflow recovers once
  without re-running a tool. Tests: `test_compression_ladder.py`,
  `test_prompt_cache_plan.py`, updated `test_context_overflow.py`. Docs:
  `docs/harness/roadmap/w2-context-economics-plan.md`,
  `docs/harness/observability.md`.
- **docs(roadmap): complete W3 tool execution plan.** Adds
  `docs/harness/roadmap/w3-tool-execution-plan.md`: the current sequential
  loop, contiguous read-only batching (effectful/interactive never overlap),
  per-call context cloning, the success-signature guardrail contract (warn
  first, controlled halt, poller exemption), BM25 + tags/domain + tiered
  catalogue disclosure, the read-tool concurrency audit, slices W3.0–W3.4,
  fault matrix, rollback and exit criteria. Parent plan, flag matrix and
  NAVIGATION now point at it. Planning only — no production code changed.
  Docs: `docs/harness/roadmap/w3-tool-execution-plan.md`,
  `docs/harness/roadmap/hermes-inspired-improvement-plan.md`,
  `docs/harness/roadmap/w0-flags-and-review.md`, `docs/NAVIGATION.md`.
- **docs(roadmap): W4 autonomy detailed implementation plan.** Adds
  `docs/harness/roadmap/w4-autonomy-plan.md`: the goal contract extension
  (`verification`/`boundaries`/`stop_when`), additive `GoalRecord`/`GoalVerdict`/
  `GoalGateRun`/`AutonomyLoop` migration, the closed gate vocabulary over
  `code/commands.py` + `code/sandbox.py`, the advisory judge schema and
  gate-first ordering, continuation as a durable task per turn with a compact
  brief, no-progress and turn/budget caps, session loop/heartbeat rules
  (idle-only, coalescing, digest, max ticks), routes/commands/goal bar, the
  `HARNESS_GOAL_LOOP` flag split from the existing `HARNESS_AUTONOMY` kill
  switch, tests, risks and rollout. Planning only — no production code changed.
  Docs: `docs/harness/roadmap/w4-autonomy-plan.md`,
  `docs/harness/roadmap/hermes-inspired-improvement-plan.md`.
- **docs(roadmap): complete W5 learning-loop plan.** Adds
  `docs/harness/roadmap/w5-learning-loop-plan.md`: grounded current-state ledger
  (flags have no consumers, `_run_cases` is schema-only, no curator,
  `hybrid.py` unwired, W5.4 lesson feedback already landed), the execution-eval
  contract (`ExecutionEvalResult`, case kinds, `ExecutionMode="evaluation"`,
  additive evaluation columns, promotion/enable gates requiring existing run
  ids), the curator design (deterministic + optional LLM pass, new run/proposal
  tables, dry_run/propose/apply/off, pinned/compliance/external skips, inert
  drafts only), BM25 hybrid retrieval with unchanged safety gates and the
  labelled-eval acceptance, slices, test matrix, rollout, risks and file map.
  Planning only — no production code changed. Docs:
  `docs/harness/roadmap/w5-learning-loop-plan.md`, `docs/NAVIGATION.md`,
  `docs/harness/roadmap/hermes-inspired-improvement-plan.md`.
- **test(harness): W2 verification + baseline.** Full suite PASS (15,444 passed
  = 4,749 vitest + 10,696 pytest; 35 skipped; 0 failed; offline eval gates ALL
  PASS), `tsc` clean, audit 46/46, conformance 16/16, SLO 8/8; live evals NOT
  MEASURED (no provider). W2 baseline:
  `docs/harness/baselines/w2-8f79bed4-2026-11-12.json` / `.md` (74/74 terminal,
  962 events, same schema as W0/W1). Docs:
  `docs/harness/roadmap/w2-context-economics-plan.md`,
  `docs/harness/observability.md`, `docs/NAVIGATION.md`.
- **feat(harness): W2 context economics (core).** Adds `context/usage_anchor.py`
  (one provider-usage row per session, fingerprint + appended-history estimate),
  anchor-driven pressure/gates in `context_budget.py`
  (`continue|soft|hard|emergency|unknown`, 50/70/85 defaults),
  `context/pruning.py` (bounded old-tool-result pruning with evidence
  protection), `context/compression_state.py` (persisted 60/300/900 s cooldown
  for the model narrative), `context/retry.py` (tighter-budget retry moved out
  of `graph.py` for the size ratchet), and `run_recovery.recover_overflow_state`
  (one checkpoint retry only when no effect is `started` and no tool ran).
  `graph.py` wires the anchor into the budget, runs the prune stage in the tool
  node, and moves `runtime_context` after history so the reusable prefix stays
  cacheable. Dead `HARNESS_USAGE_ANCHOR`/`HARNESS_COMPRESSION_LADDER` flags now
  have live consumers; `HARNESS_CONTEXT_GATE_PCT` (default 50) is the single
  soft-gate knob. Tests: `test_usage_anchor.py`, `test_context_gates.py`,
  `test_context_prune.py`, updated `test_context_overflow.py`,
  `test_graph.py`, `test_size_budget.py`. Docs:
  `docs/harness/roadmap/w2-context-economics-plan.md` (status + §15 live
  surface and deliberate gaps).
- **docs(roadmap): complete W2 context economics plan.** Adds
  `docs/harness/roadmap/w2-context-economics-plan.md`: usage-anchor schema,
  50/70/85 budget gates, prune→summary→skeleton ladder, tail/evidence
  protection, cache-stable prompt tiers, any-step overflow recovery, slices
  W2.1–W2.7, fault matrix, rollout and exit criteria. Planning only — no
  production code changed. Docs: `docs/harness/roadmap/w2-context-economics-plan.md`,
  `docs/NAVIGATION.md`, `docs/harness/roadmap/hermes-inspired-improvement-plan.md`.
- **feat(harness): W1 live model gateway.** Adds `model_runtime/gateway.py`
  (candidate plan + stream), `model_runtime/credential_pool.py` (per-provider
  key rotation/cooldown), traced invocation in `ModelRuntime.invoke`
  (per-attempt `ModelRequest` + `model.attempt.*`), a first-token watchdog in
  `model_stream.py`, mode-aware `step.py` (`on`/`shadow`/`off`), per-run
  credential pool + fallback builder + token remainder in `graph.py`, and
  attempt-based cost in `run_cost.py`. Same-provider/keyless fallback is on by
  default; cross-provider fallback requires opt-in plus a declared-quality
  guard (`HARNESS_MODEL_FALLBACK_ALLOW_DEGRADED` to override). Default
  `HARNESS_MODEL_GATEWAY=on`. Opt-in live test:
  `test_model_gateway_live.py` (`HARNESS_LIVE_MODEL_TEST=1`).
  Tests: `test_model_gateway.py`, extended `test_model_runtime.py`,
  `test_step_retry.py`, `test_graph.py`, `test_run_cost.py`; opt-in
  `test_model_gateway_live.py`. Baseline:
  `docs/harness/baselines/w1-8f79bed4-2026-11-12.*` (74/74 terminal; full suite
  11,687 passed, 35 skipped; offline, SLO, audit, conformance, tsc PASS; live
  NOT MEASURED). No prompt/tool/schema/financial semantics changed.
- **test(harness): the context-budget assertion now targets the budget keys, not
  the whole blob.** `test_run_keeps_more_history_on_a_large_declared_window`
  asserted `result.context is None`, but every run result also carries the
  `flags`/`flagsHash` snapshot (flag registry), so the test failed on a committed
  tree even though no history was dropped. It now asserts that `keptTurns` /
  `droppedTurns` are absent — the contract the test actually describes.
  `python/tests/test_context_budget.py` (10 passed). Test-only; no app code,
  contract or runtime changed. `no doc change — stale assertion fix only`.
- **docs(roadmap): complete W1 model gateway plan.** Adds
  `docs/harness/roadmap/w1-model-gateway-plan.md`: live-path diagram, gateway
  contracts, candidate planning, retry/fallback matrix, credential pool,
  first-token watchdog, per-attempt accounting/cost/budget, observability
  events, slices W1.1–W1.6, fault matrix, rollout/rollback and exit criteria.
  Planning only — no production code changed. Docs:
  `docs/harness/roadmap/w1-model-gateway-plan.md`, `docs/NAVIGATION.md`,
  `docs/harness/roadmap/hermes-inspired-improvement-plan.md`.
- **feat(harness): W0 flag registry, run snapshot and baseline collector.**
  Adds `harness/config/flags.py` (typed W1–W7 flags, parsing/clamping/strict
  mode), `harness/run_flags.py` (`run.flags` event + `HarnessRun.context.flags`
  / `flagsHash`), `graph.execute_run` recording once per run/resume, boot strict
  validation (`HARNESS_FLAG_STRICT`), and
  `harness/evaluation/w0_baseline.py` + `scripts/w0-baseline.js` (read-only
  runtime metrics with honest UNKNOWN), `harness/evaluation/w0_soak.py` +
  `scripts/w0-soak.js` (50 sequential + 24 concurrent lifecycle soak), and the
  first committed baseline `docs/harness/baselines/w0-0a7ec906-2026-11-12.*`
  (74/74 terminal; offline/SLO/audit/conformance/tsc PASS; live NOT MEASURED).
  The context-blob helpers moved to
  `history.py` to keep `graph.py` at its size pin. Tests: `test_flags.py`,
  `test_run_flags.py`, `test_w0_baseline.py`; `test_graph.py` event order
  updated. No prompt, tool, schema or model behaviour changed. Docs:
  `docs/harness/roadmap/w0-*`, `docs/NAVIGATION.md`.
- **feat(desktop): taskbar presence completes — minimize, progress, and "unread
  means unseen".** Keep-warm now minimizes instead of hiding, so the taskbar
  button (and its badge/flash) survives closing the window. An indeterminate
  progress bar runs while an agent stream is doing work (approvals and
  clarifications pause it, because the run is blocked on the operator); the
  working count lives outside React in `src/lib/desktop/activity.ts` so several
  mounted run surfaces share one bar. The ledger now treats an item as unread
  when it arrives while the window is in the background — via the new shared
  `src/lib/notifications/focus.ts` — so alt-tabbing away mid-answer badges the
  Chat tab; returning marks the visible tab read. The completion alert in
  `use-agent-run.ts` uses the same rule (previously it stayed silent whenever
  Chat was selected, even unfocused). Settings › Window gains a "Taskbar
  activity" toggle (`be_taskbar_badge_v1`, default ON). The `be-taskbar` payload
  keeps `state`/`count`/`flash` and adds `working`, so an older shell degrades to
  the badge-only behaviour. Tests: `taskbar.test.ts` (11), `activity.test.ts`
  (5), two background cases in `notifications/store.test.ts`. Docs:
  `desktop/README.md`, `docs/desktop-app-plan.md` §20, `docs/CHANGELOG.md`.
- **docs(roadmap): W0 baseline and guardrails plan.** Adds
  `docs/harness/roadmap/w0-baseline-and-guardrails-plan.md`: metric dictionary
  with source tables, baseline artifact schema, isolated measurement protocol
  (offline/live/soak/gates), typed flag registry, kill-switch suite, "no second
  seam" review gate, day-by-day schedule and exit criteria. Planning only — no
  production code changed. Docs: `docs/harness/roadmap/w0-baseline-and-guardrails-plan.md`,
  `docs/harness/roadmap/hermes-inspired-improvement-plan.md`,
  `docs/NAVIGATION.md`.
- **docs(roadmap): detailed Hermes-inspired harness improvement plan.** Adds
  `docs/harness/roadmap/hermes-inspired-improvement-plan.md`: eight workstreams
  (model gateway, context economics, tool execution, autonomy, learning loop,
  run-kernel integrity/safety, delegation/file checkpoints, observability),
  with slice-level interfaces, feature flags, file seams, tests, rollout,
  risks, a 12-week schedule and first-10-days checklist. Planning only — no
  production code changed. Docs: `docs/harness/roadmap/hermes-inspired-improvement-plan.md`,
  `docs/NAVIGATION.md`, `docs/research/hermes-vs-eclipse/IMPLEMENTATION-ROADMAP.md`.
- **feat(desktop): the taskbar now carries the unread signal and an attention
  flash.** Windows draws a red overlay dot on the taskbar icon (`SetOverlayIcon`,
  rasterized in Rust so the shell needs no `image-png` feature) and issues one
  `FlashWindowEx` when a new item arrives while the window is unfocused;
  macOS/Linux use `set_badge_count`. Driven by the existing notification ledger
  through a new `be-taskbar` core event
  (`src/lib/desktop/taskbar.ts`, `src/lib/notifications/desktop-taskbar-badge.tsx`,
  mounted in `src/app/layout.tsx`): the page owns the state, the flash is
  edge-triggered, and the last count is kept in Rust and re-asserted after
  hide/show. Scope is M1 — keep-warm still hides the window, so there is no
  taskbar button to badge until the M2 decision (minimize instead of hide).
  Tests: `src/lib/desktop/taskbar.test.ts` (9) plus a Rust unit test for the
  badge geometry. Docs: `desktop/README.md`
  ("Taskbar presence"), `docs/desktop-app-plan.md` §20, `docs/CHANGELOG.md`.
- **docs(research): Hermes-vs-Eclipse architectural comparison.** Adds
  `docs/research/hermes-vs-eclipse/` (six files: executive summary, 25-subsystem
  comparison with source evidence, adoption analysis with MIT licensing review,
  target architecture with Mermaid flows, prioritized P0–P3 roadmap with
  acceptance/tests/regressions, and a feature-gap matrix). Read-only
  investigation: no production code, schema, runtime or setup changed. Hermes
  evidence is from `NousResearch/hermes-agent` @ `72c8803`; no official
  `hermes-code` repository exists. Docs: `docs/research/hermes-vs-eclipse/*`,
  `docs/NAVIGATION.md`.
- **docs(media): refine the harness launch script to a 30-second use-case cut.**
  Reworked `media/blackeclipse-launch/SCRIPT.md` around one market-research
  request and added clearer beats for mode selection, bot roles and limits,
  tool/source events, skills, Graph Studio, charts, and run inspection. No app
  code, data contract, or runtime changed. No doc change — content asset only;
  it lives outside the Next.js app and adds no runtime or setup surface.
- **docs(media): add the BlackEclipse harness launch-video script.** Added
  `media/blackeclipse-launch/SCRIPT.md` with a 45-second HyperFrames shot list
  covering bot modes, bounded agent presets, observable runs, skills, Graph
  Studio, charts, and observability, plus a real-UI capture checklist and
  anti-fabrication rules. No app code, data contract, or runtime changed.
  No doc change — content asset only; it lives outside the Next.js app and adds
  no runtime or setup surface.
- **feat(legal): the risk position is now visible where users act.** Bumped the
  risk notice to `2026-11-12` and made the copy carry one consistent position:
  Eclipse is self-directed research and order-entry software; the user owns the
  decision, the account, and the outcome. First-run now says "not my adviser or
  broker, every trade at my own risk"; the trade approval card shows an order
  preview and requires a "my decision / my own risk" checkbox; broker surfaces
  state that Eclipse never holds funds and the broker is the source of truth;
  every settled AI answer carries "Eclipse is an AI agent. It can be wrong —
  verify the facts and make the call yourself."; Settings gains a Risk & AI
  panel with the accepted version/date and a re-accept action. `/api/legal/risk-ack`
  now returns `acceptedAt` for the current version. Tests:
  `src/lib/legal/disclosure.test.ts` (4). Docs: `docs/legal/README.md`,
  `docs/CHANGELOG.md`.
- **docs(mobile): standalone Tauri 2 Bot Mode architecture package.** Adds
  `docs/mobile/` (12 files) for a separate iOS/Android app with no Node, Python,
  Next server, JDdS or host pairing: repository-aware reuse audit of the bot
  stores/transport/UI, a Rust-owned durable run/event/approval runtime, SQLite +
  FTS5 data model, iOS/Android compatibility and physical-device PoC checklist,
  honest best-effort scheduling limits, Rig-vs-custom dependency evaluation,
  phased roadmap (0–8), testing strategy, and decisions D1–D14 with a risk
  register and open questions. No production code, schema, runtime or setup
  changed; the planned roots are repository-root `mobile/` and
  `packages/agent-contracts/`. Docs updated: `docs/mobile/*`,
  `docs/NAVIGATION.md`.
- **docs(media): branded Round 5 harness report and LinkedIn post.** New
  `media/blackeclipse-harness-report/` with a three-page A4 branded report
  (`report.html` + rendered `report.pdf`), a 1080x1350 social card (`card.html`
  + `card.png`), the ready-to-post copy (`linkedin-post.md`) and a README. The
  report explains the C2/C4/C6/C7/C8 core-integrity work with a run-lifecycle
  diagram, failure-mode matrix, seam snippets, benchmark/SLO/category charts and
  the 2026-11-12 SLO probe (40/40 runs terminal, 0 orphans, 1.885 s p95,
  $0.0007/task, 5/5 SLOs) plus 12/12 conformance cases, keeping the open items
  (partial scorecard dimensions, C8 adapters, C9 packaging) visible. No app
  code, data contract or runtime changed. No doc change - content asset only,
  outside the Next.js app and adding no runtime or setup surface.
- **feat(media): BlackEclipse 30 s launch film (HyperFrames).** New
  `media/blackeclipse-launch/` project — six scenes at 1920×1080/30 fps, 30.0 s,
  built from real captures of the running app plus the vault's own values
  (AMD +8.00%, S&P 500 7,619.38, 28 markets, 56,516 instruments, 161 earnings
  reports) — with the rendered `out/blackeclipse-launch.mp4`. No app code or data
  contract changed. No doc change — content asset only; the project lives outside
  the Next.js app and adds no runtime or setup surface.
- **fix(chat): Eclipse Agent composer is neutral grey again.** The
  `.glass-composer` fill used the near-black `--card-rgb` tint, so the input
  bubble read as black over the dark conversation surface. It now uses a
  neutral zinc tint (alpha 0.30, keeping the real blur) with a light-mode
  override, and the composer is excluded from the theme glass tint overrides so
  a customized glass theme cannot repaint it black. `globals.css` only. No doc
  change — styling only, no contract or setup impact.
- **fix(sidebar): collapsed logo swaps to the expand chevron on hover.**
  Restored the previous affordance: at the collapsed width the brand mark fades
  out and a full-size `ChevronRight` button replaces it (instead of the tiny
  corner button that left the mark competing with it). No doc change — visual
  affordance only, no contract or setup impact.

