# Change Log

Older entries are **moved, never deleted** into [`docs/changelog/`](./changelog/)
— one file per month. This file keeps the newest seven dated sections;
`npm run rotate:changelog -- --write` performs the move.

## 2026-11-16

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

## 2026-11-11
- **feat(eval): process-level kill matrix in the conformance gate.** Four new
  cases spawn a separate worker and kill it before `begin`, after `begin`, after
  the external effect, and after `finish`; the parent resumes and asserts
  at-most-once semantics (0/0/1/1 effects, states None/unknown/unknown/done).
  Conformance is now 16/16. Docs: `conformance.md`, roadmap. no other doc change.
- **chore(release): v0.4.0 release bundle + `--quick` conformance fix.**
  `npm run release:bundle` writes `docs/harness/releases/v0.4.0/report.json`
  and `RELEASE.md` from the generated scorecard, tool registry, conformance
  result, SLO probe and wheel sha256 — no hand-typed release numbers. Quick
  conformance no longer reports its intentionally skipped contract check as a
  missing case. no doc change - release artifacts are generated; the release
  runbook already documents the operator tag/PyPI step.
- **fix(eval): the finance QA corpus joins the audited built-in corpus.** The
  nine `finance_qa_v1` tasks now carry an explicit oracle (the financial grader
  recomputation), except the unavailable-figure honesty task, which is a
  documented oracle exemption. Regenerated the committed corpus manifest
  (347 tasks, oracle coverage 0.781), the published benchmarks (agent 0.4.0) and
  the provenance counts (validation 253). no doc change - generated artifacts
  and test pins.
- **feat(release): C9 core — versioned API, wheel, ACP, core architecture.**
  `harness.__version__`, `harness.public.HARNESS_API_VERSION`,
  `package.json` and `pyproject.toml` are aligned at 0.4.0 and checked by
  `npm run release:check`; `npm run package:python` builds the wheel (pip
  fallback) and the installed wheel was smoke-tested (1091 tools, conformance
  11/11 quick, ACP self-test). A minimal JSON-RPC 2.0 ACP adapter
  (`initialize`, `session/new`, `session/prompt`, `session/cancel`, `shutdown`,
  typed errors) lives in `harness/acp/`. `core-architecture.md` states the five
  "ones" and the invariants; `external-quickstart.md` and `release.md` document
  install, proof and the operator tag/publish steps. ADR-H359. Tag + PyPI upload
  remain operator steps (credentials never in the repo).
- **feat(eval): every scorecard dimension is now measured from runs (C8.7).**
  `scorecard:from-runs` also consumes the conformance result, so all 8
  dimensions carry a numeric metric with `{value, unit, direction, source,
  runId, generatedAt}`: loop (reliability), context (tokens/task), aci
  (tool accuracy), safety, ext (misroute rate), eval (task success), ops
  (terminal correctness) and core_integrity (conformance pass ratio). The
  curated labels, weights, targets and evidence paths are preserved; nothing is
  hand-typed. Docs: `agent-evaluation.md`, roadmap. no other doc change - the
  scorecard files are regenerated from runs.
- **feat(eval): C8.2-C8.6 — external adapters, finance QA, comparability.**
  One `DatasetAdapter` protocol with four offline fixtures (SWE-bench Lite,
  GAIA, tau-bench, FinanceBench), each two license-labelled, provenance-tagged
  tasks; `npm run gate:external` passes and is wired into CI. `finance_qa_v1`
  adds nine deterministic QA tasks (margins, EPS, P/E, CAGR, percentage change,
  drawdown, position size, unavailable-figure honesty). `compare_release`
  refuses to blend incomparable reports (dataset set/version/checksum/tier/grader).
  Documented that the offline tier is already the real graph. Tests:
  `test_c8_{external,finance_qa,compare,offline_tier}.py`; ADR-H358. Docs:
  `agent-evaluation.md`, `conformance.md`, `decisions.md`.
- **feat: close the audit backlog — client recovery, per-run cost, versioned
  audit corpus.** The chat client now remembers the server-started `runId`; a
  dropped stream polls the run to terminal instead of submitting a second run,
  and a reload reattaches an in-flight run by `chatId` (completed runs are left
  to the persisted transcript, so no duplicate). `run_cost.py` prices a run from
  the one `observability.costs` registry and reports `costUsd`/`priced` (unknown
  model = `None`, never zero). The audit corpus is a versioned manifest
  (`evaluation/corpus/agent_audit_v1.json`, 9 areas) executed by
  `npm run audit:agent` as a `check-all` gate. Tests: 44 corpus checks, 3 cost, 3
  manifest; `tsc` clean.
- **feat(runtime): token budget, vault inventory, audit gate and the G1 soak.**
  `AgentConfig.maxTokens` is enforced: at the budget the graph stops binding
  tools and forces a final answer (`TOKEN_BUDGET_EXCEEDED` only if that answer is
  empty). New read-only `market/vault.py` + `data_inventory` tool report JDdS
  (`jdds.db`, SQLite `mode=ro`) and `history_cache` separately, and
  `resolve_series` labels both stores and flags count conflicts without merging.
  The 41-case independent-audit corpus runs as `npm run audit:agent` and is a
  `check-all` gate. `scripts/soak-runs.py` passes G1 at the mechanism level:
  100 sequential + 96 concurrent runs completed, 0 left running, 5 checkpointed
  orphans became `interrupted`. Tests: 41 audit + 4 vault + 1 budget + soak.
  No `jdds.db` write.
- **feat(runtime): terminal fencing, SSE resume and hard budgets.** Terminal
  `completed/failed/cancelled` writes now go through `fenced_update_run`, which
  requires this process to still own the live lease epoch; a stale worker can no
  longer finalize another owner's run. The SSE endpoint accepts `after` /
  `Last-Event-ID` and emits `id: <seq>` frames (the front door forwards both),
  so a reconnect resumes instead of replaying from zero. `eclipse-agent` gets a
  hard `maxToolCalls=48` (the audit saw 46–81-call loops). Evaluation adds a
  `delivery` dimension and `release_ready()`, which blocks release on an
  unmeasured/failed delivery, safety, task-success or provenance dimension even
  when the weighted mean is high. Tests: lease/effect/resume/graph (22),
  evaluation gate (4). No `jdds.db` change.
- **chore(repo): version the intended `main` ruleset as `.github/ruleset.json`.**
  The rules `repository-guards.md` already prescribed (restrict deletions, block
  force pushes, PR-gated merges, strict required check
  `typecheck · lint · unit · python · evals`) now exist as an importable file
  instead of prose only. No runtime behaviour changes: it is not applied on the
  Free plan (`403`) and does not affect the hooks. Updated
  `docs/repository-guards.md` to describe the import step and drop the now-false
  "nothing about it lives in git".
- **feat(runtime): at-most-once effect ledger at the tool seam.**
  New `python/harness/run_effects.py` (`RunEffect`). An effectful call (a
  declared tool `effect`, or a non-read permission) is marked `started` BEFORE
  dispatch and `done` after. On resume, `started` without `done` means the
  external outcome is unknown: the tool is **not** called again, the row becomes
  `unknown`, and the model is told to reconcile (broker terminal / git status /
  file hash). Read-only tools stay freely retryable. Tests:
  `test_run_effects.py` (confirmed → done; started-without-result → zero
  re-execution). Graph/resume/lease/recovery suites: 58 passed. Terminal writes
  still do not assert the lease epoch. No `jdds.db` change.
- **feat(runtime): durable run leases, environment ownership and heartbeat.**
  New `python/harness/run_lease.py`: `RunLease` + `RuntimeInstance` tables,
  atomic `BEGIN IMMEDIATE` claims, monotonic fencing epochs, a daemon heartbeat
  thread with its own SQLite connection, and per-process runtime identity.
  `service.run` / `run_background` claim the run before executing (a duplicate
  submission gets `RUN_LEASE_CONFLICT`, never a second execution); boot
  registers the runtime and passes its environment to recovery. Recovery now
  skips any run with a live lease and any run owned by another environment, so a
  second process can no longer orphan a live run. Epoch is issued but terminal
  writes are not yet fenced; the effect ledger remains open. Tests:
  `test_run_lease.py` + recovery/resume/watchdog/parity (25 passed). No
  `jdds.db` change.
- **feat(runtime): recoverable runs and partial answers.** Added the front-door
  `POST /api/harness/runs/[id]/resume` route + `resumeRunInRuntime` client
  (operator-gated, requires the original RunRequest payload; 409 on terminal,
  400 without a request). The stall watchdog now reconstructs the last assistant
  message from `RunMessage` and writes it as `output` with `error.partial` and a
  `run.partial` event, so a stalled run no longer discards produced text.
  Documented the `finance_series` price/return contract in
  `docs/harness/financial-analysis-engine.md`. Tests: 5 watchdog + 11 chat-route;
  `tsc` clean. No `jdds.db` change.
- **fix(finance): explicit price/return input contract for `finance_series`.**
  The series calculators difference their observations (they expect levels), so
  a returns input was differenced twice and, after the synthetic path, dropped
  the first return. `finance_series` now takes `input: prices|returns|auto`,
  compounds a returns series once (n+1 levels → exactly n returns) and records
  the interpretation. `auto` infers returns only for signed values within
  [-1, 1]. VaR/CVaR now use a float-safe nearest-rank tail
  (`ceil(alpha*n - 1e-9)`), so n=20 at 95% selects the single worst return.
  Prompt updated to require `input`. Tests: `test_finance_series_contract.py`
  (12) plus 112 calculation/quality tests pass. No change to percent outputs.
- **fix(advisory): stop metric/ML prose from becoming advice.** Expanded the
  symbol stop-list (`FCFF/FCF/ADV/WACC/EBITDA/CAGR/ROIC/…`, `AUC/ROC/RMSE/…`)
  and required a position/portfolio context for number-only directives. A
  ticker claim or a contextual weight claim still fires. Tests:
  `test_advisory_precision_audit.py` + gate tests (27) pass.
- **feat(market): name the store on cached-history payloads.** `coverage`,
  `list_series` and `history_catalog` now carry `store=history_cache` and the
  provider set; the tool description and agent comments state this is the
  provider cache, not JDdS. Tests: 26 market store/cache/gateway tests pass.
- **fix(runtime): checkpoint-aware orphan recovery.** A restart now marks a run
  with a checkpoint `interrupted` (`RUN_INTERRUPTED`) so the existing resume
  endpoint can accept it; only a run with nothing to resume is terminal
  `RUN_ORPHANED`. The terminal update is conditional (`status IN
  ('created','running')`), so a live worker is never overwritten. Boot now logs
  pid/env/port/db/schema/orphan count for forensics. Tests: 14
  recovery/resume/watchdog tests pass.
- **fix(chat): recoverable timeout contract.** A synchronous wait deadline maps
  to 504 (not 500), and every error response carries the run id/stream/events
  handles when a run exists; 202 adds `eventsUrl`/`pollAfterMs`. Unknown model
  timeouts no longer look like a server fault. Tests: 11 chat-route tests pass;
  `npx tsc --noEmit` clean.
- **docs(roadmap): record the implemented slice and its evidence** in
  `docs/harness/roadmap/agent-reliability-remediation-plan.md` (§0a). Remaining
  P0: lease/fencing, effect ledger, partial output/SSE replay/resume route,
  budgets, assurance expansion. No `jdds.db` change.
- **refactor(structure): group the flat `src/lib/harness` hot spots; freeze
  import-direction debt.** Mechanical, behaviour-preserving move of 107 modules:
  the 29 slash-command files → `src/lib/harness/commands/`; the 24
  `data-bridge-*` satellites (entry `data-bridge.ts` unchanged) →
  `src/lib/harness/data-bridge/`; the 54 `*-client.ts` / `*-browser.ts` pairs
  (tests included) → `src/lib/harness/clients/`; `app/alerts/alerts-client.tsx`
  → `src/components/screens/alerts/` so no component imports a route. Every
  `@/` alias, relative specifier and `vi.mock()` string was rewritten by a
  single-pass codemod; `npx tsc --noEmit` is clean. New
  `src/lib/import-boundaries.test.ts` enforces app → components → lib with a
  ratchet of the 23 pre-existing lib → components edges (tests exempt), so the
  boundary can only improve. Docs updated: `docs/NAVIGATION.md`,
  `docs/DATA-FLOW.md`, `docs/harness/slash-commands.md`,
  `docs/harness/task-plan-system.md`, `docs/voice.md`, `docs/video-pipeline.md`,
  `docs/ui-engineering.md`, `docs/trading.md`, `docs/portfolio-accounting.md`,
  `docs/CHANGELOG.md`. No runtime behaviour, API contract or data shape changed.
- **docs(roadmap): revise the agent-reliability remediation plan after an
  architecture review.** Verified the plan against the working tree and
  corrected four wrong assumptions: `HarnessRun` lives in `agent-memory.db`
  (migrations via `MigrationRunner`, not Prisma); resume currently refuses
  terminal `failed` runs, so orphan recovery needs an `interrupted` state;
  `series_store` is only the provider-cache half; and the ×100 calculation
  scales are intentional (the defect is the missing price/return input
  contract). Added lease fencing, an effect ledger with at-most-once semantics
  for irreversible tools, the full HTTP lifecycle, licensing boundaries,
  budget/token limits, prompt-provenance capture, evaluation hard gates and a
  realistic 11–15-week solo estimate. Updated:
  `docs/harness/roadmap/agent-reliability-remediation-plan.md`,
  `docs/harness/roadmap/README.md`. No source or database change.
- **docs(roadmap): remediation programme for the pre-launch agent audit.**
  `docs/harness/roadmap/agent-reliability-remediation-plan.md` turns the 18-test
  audit findings into 7 workstreams (resume-first recovery, deadline/partial
  delivery, calculation units, store provenance, loop budgets/ergonomics,
  answer trust, assurance) with file-level tasks, effort estimates, 8 release
  gates and a first-week checklist. Indexed from
  `docs/harness/roadmap/README.md`. No source change — planning artifact only.
- **test(eval): independent pre-launch quantitative audit of the Eclipse agent.**
  17 primary tests plus 5 controlled retries against the live front door
  (statistics, DCF, portfolio, cointegration, backtest, reproducibility, ML,
  provenance, injection, fabrication, live-order safety), with every figure
  re-computed independently. Verdict **CONDITIONAL PASS, 82/100**: closed-form
  accuracy and trading safety are strong; run orphaning/timeouts, the
  `finance_series` unit defects, and JDdS-vs-provider-cache misattribution block
  an unconditional pass. Report added:
  `docs/quant-research/agent-evaluation-2026-11-11.md`. No source change —
  evaluation artifact only; no `jdds.db` change.
- **feat(eval): C8 conformance gate — retry faults, golden trace, contracts.**
  `python -m harness.evaluation.conformance` (npm `gate:conformance`) runs an
  offline five-class gate: 429/500/disconnect retries, no-retry 400/cancel,
  expired-deadline refusal, duplicate-effect idempotence, a golden
  `run → step → tool/LLM` trace, and contract checks for the hook vocabulary,
  portable tool manifest, release report and plugin SDK version.
  `docs/harness/conformance.json` is authoritative: a missing or undeclared case
  fails. Wired into `check-all.js` and CI; tests
  `test_c8_conformance.py`. Docs: `docs/harness/conformance.md`,
  `docs/harness/agent-evaluation.md`, ADR-H357. Remaining C8: external adapters,
  finance QA, real-agent offline tier, generated scorecard, comparability.
- **feat(harness): C7 observability that bites — step spans, SLO v2, release
  gate, dashboard.** The graph emits `step.started|completed`; the projector
  builds `eclipse.run → eclipse.step → eclipse.llm/eclipse.tool.*` with children
  parented to the step. `observability/failures.py` is a closed taxonomy
  (provider/timeout/transient/validation/tool/budget/policy/sandbox/persistence/
  cancel/internal) labelling spans, errors and `eclipse_failures_total`. Run and
  step cost are attributed (`eclipse_run_cost_usd`, `eclipse_step_cost_usd`);
  process CPU/memory/threads and worker utilization are sampled honestly.
  `slo.py` gains `ratio|percentile|rate` kinds and five objectives: terminal
  correctness, p95 latency, resume p95, orphan rate and cost per task.
  `observability/probe.py` runs a deterministic workload through the shipped
  projector; `gate.py` + `docs/harness/slo-budgets.json` + `slo-baseline.json`
  make `npm run gate:slo` fail CI on a breach or committed regression (wired into
  `check-all.js` and the workflow). `GET /observability/release-report` exposes
  the gate input and `/observability/dashboard` renders one escaped card per SLO.
  Tests: `test_c7_{spans,slo_gate,dashboard_api,usage}.py`; the `ops` scorecard
  dimension is now measured. Docs updated: `docs/harness/observability.md`,
  `docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H356),
  `docs/harness/roadmap/round-5-core-integrity.md`,
  `docs/harness/roadmap/README.md`, `docs/harness/scorecard.json`,
  `docs/harness/scorecard.md`, `docs/CHANGELOG.md`.
- **feat(harness): C6 completed — AppContainer, Ed25519 publisher signatures,
  computer-executor guard.** `security/appcontainer.py` adds the opt-in Windows
  native boundary (`BLACK_ECLIPSE_WINDOWS_APPCONTAINER=1`): a package SID, zero
  network capabilities, a workspace-only `icacls` grant, a scrubbed environment
  (plus the `LOCALAPPDATA` the AppContainer loader requires) and a
  `PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES` launch; every failure is a
  refusal. The live smoke proves a child runs and cannot read outside its
  granted workspace. `plugins/ed25519.py` implements RFC 8032 verify/sign with
  no new dependency (pinned by the standard test vector); `plugins/signing.py`
  accepts `ed25519:` publisher signatures verified against
  `HARNESS_PLUGIN_TRUSTED_KEYS` alongside the operator HMAC. `computer_use` now
  calls `executor_guard()` before input injection. New tests:
  `test_c6_appcontainer_live.py` (opt-in live), Ed25519 + unknown-key cases in
  `test_c6_plugin_signing.py`, computer refusal in `test_c6_executor_profile.py`;
  related suites 562 passed (2 opt-in skips), AppContainer live 2 passed. Docs
  updated: `docs/harness/security.md`, `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H355),
  `docs/harness/roadmap/round-5-core-integrity.md`,
  `docs/harness/scorecard.json`, `docs/harness/scorecard.md`,
  `docs/CHANGELOG.md`.
- **feat(harness): C6 safety envelope completed — executor enforcement, native
  backends, plugin install signing.** `terminal_run` and background-process
  spawn now call `executor_guard()` and refuse a configured profile the host
  cannot keep (`sandbox.profile.blocked`), below the gateway. `NativeSandbox`
  adds Linux bubblewrap and macOS Seatbelt with pure argv/policy builders and
  honest Windows-unavailable reporting; selection order is Docker → Native →
  Local. `plugins/signing.py` adds a `plugin.sig` sidecar (HMAC over canonical
  manifest + package digest, sidecar excluded from the digest),
  `HARNESS_PLUGIN_REQUIRE_SIGNATURE` (fails closed without a key) and
  `HARNESS_PLUGIN_REQUIRE_REVIEW` (operator acknowledgment), enforced on install
  and update with rollback. New tests: `test_c6_executor_profile.py`,
  `test_c6_native.py`, `test_c6_plugin_signing.py`; related terminal/plugin/
  security suites 420 passed. Remaining documented follow-ups: Windows
  AppContainer, public-key publisher signatures, computer-executor guard. Docs
  updated: `docs/harness/security.md`, `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H355),
  `docs/harness/roadmap/round-5-core-integrity.md`,
  `docs/harness/roadmap/README.md`, `docs/harness/scorecard.json`,
  `docs/harness/scorecard.md`, `docs/CHANGELOG.md`.
- **feat(harness): C6 safety envelope (core) — sandbox profiles, effect tokens,
  escape suite.** `security/profiles.py` defines `read-only | workspace-write |
  network-allowlist | full`; `resolve_profile()` reports `enforceable=False` with
  the exact missing guarantees instead of silently downgrading, and the gateway
  refuses an execution action when a configured profile is unenforceable
  (`security.sandbox.profile_blocked`). `network-allowlist` requires
  `BLACK_ECLIPSE_EGRESS_PROXY`; the allowlist is exact-or-`*.domain` and rejects
  suffix masquerades; `GET /sandbox` reports every profile. `security/
  effect_tokens.py` mints an HMAC token bound to `(run, tool, argsDigest, tenant,
  expiry)` at the authorizer ALLOW and the tool executor verifies it before the
  handler runs (modes `off | shadow (default) | enforce`); enforce mode refuses
  missing, expired, replayed, cross-run and widened-argument calls. New
  `test_c6_{auth,profiles,effect_tokens,escape}.py` pin auth-by-default outside
  loopback (loopback dev stays zero-config), the four escape classes and the
  token gate. Remaining: executor-level profile wiring, native
  AppContainer/bubblewrap/seatbelt backends, plugin install signing. Docs
  updated: `docs/harness/security.md`, `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H355),
  `docs/harness/roadmap/round-5-core-integrity.md`,
  `docs/harness/roadmap/README.md`, `docs/harness/scorecard.json`,
  `docs/harness/scorecard.md`, `docs/CHANGELOG.md`.
- **chore(git): a free guard for the unprotected `main` branch.** GitHub reports
  `main` as unprotected because both branch protection and rulesets answer `403`
  on a private repository (`Upgrade to GitHub Pro…`); nothing in-repo can change
  that. Added `.githooks/pre-push`, installed by the existing `postinstall`
  (`scripts/install-git-hooks.js` now chmods it too), which refuses to **delete**
  or **rewrite** (non-fast-forward) `main` — the exact two operations the banner
  warns about — while leaving normal fast-forward pushes alone. `SKIP_PUSH_GUARD=1`
  bypasses deliberately, `PUSH_GUARD_BRANCHES` adds branches. Server-side
  enforcement (required PR + the `ci` status check) still needs GitHub Pro; the
  exact ruleset is documented. Verified with simulated ref updates (fast-forward,
  delete, rewrite, other branch, multi-ref). docs updated:
  `docs/repository-guards.md` (new), `docs/NAVIGATION.md`.
- **feat(desktop): v0.3.4 release hardening.** Windows installer now checks for
  the WebView2 Runtime and silently installs the bundled Evergreen bootstrapper
  when missing, re-checks, and otherwise shows actionable manual instructions
  instead of finishing with an app that cannot open. Added
  `python/harness/pack_support.py`, a single catalogue of the five optional packs
  that turns a missing import into a sentence naming the pack, what it enables,
  and the install command; the browser provider uses it. The shell shows a
  one-time, dismissible notice naming the real data directory and stating that
  browser-version data was not imported and was not deleted. Added
  `scripts/desktop-python-test.js`: a packaged-Python integration test that
  imports the harness, exercises the tool registry, executes a deterministic tool
  (`finance_calc` -> 25.0%) and reads the packaged database (59 tables).
  Version -> 0.3.4.
- **feat(bots): per-bots text size + plain-language run-failure help.** The Bots
  workspace (sidebar, conversation, details drawer) now has its own text-size
  setting (90–150%), persisted in `be_bots_appearance_v1` and applied via the
  scoped `--bots-font-scale` CSS variable — independent of the app-wide theme
  text size. The run detail now explains the stable `errorClass` in plain
  language (what failed, the concrete next step, whether the runtime retries
  it) instead of only naming the class. No doc change — UI preference/copy only,
  no architecture, data shape or setup contract changed.
- **fix(sidebar): the brand logo no longer disappears.** Two causes.
  (1) In the collapsed rail the mark faded to `opacity-0` whenever the pointer
  entered ANYWHERE in the sidebar (a `group-hover/sidebar` rule), which read as
  the logo randomly vanishing; the mark now stays visible and Expand is a small
  corner button that appears on hover. (2) The shipped wordmark SVG is white
  artwork, so on a light theme it was white-on-white and invisible; the shipped
  asset gets `invert(1)` under `html:not(.dark)` (a user-uploaded `logoUrl`
  keeps its own colours).
- **fix(shell): the front door is now resident, so stopping Eclipse can never
  show the browser's `ERR_CONNECTION_REFUSED` page.** The branded offline card
  only helped when a service worker was already installed; the real gap was that
  the local proxy was a child of the launcher and died with the app, leaving
  nothing listening on the origin. `scripts/local-proxy.js` is now a long-lived
  process: launchers attach to a live one (`scripts/lib/proxy-state.js`,
  `.black-eclipse/proxy-state.json`) instead of spawning/killing their own, a
  per-user sign-in autostart (`scripts/lib/proxy-task.js` — a Task Scheduler
  entry, or a hidden Startup-folder launcher when the policy refuses;
  `black proxy on|off|status`) re-raises it after a reboot, and `black eclipse` /
  `npm run up` re-raise a missing door even when the app is already running. While the app is down it
  answers PAGE NAVIGATIONS with the themed, branded `/offline` card
  (`scripts/lib/proxy-offline.js`, cached from the app with a built-in fallback)
  and every other path with a plain `503`, so health probes and the page's
  reconnect check cannot read the card as "app up". The card's button now boots
  the app through `POST /__eclipse/start` (`BE_NO_PROXY=1`, guarded by loopback
  + a control header). The service worker stays as the second layer for the door
  itself being down, and `start-desktop.js` no longer stops the door on exit.
  Verified live on alternate ports: proxied page while up, cached themed card
  while down, `503` for assets/non-navigations, guarded control surface, stale
  state ignored. Docs updated: `docs/ARCHITECTURE.md` (Layer 0),
  `docs/local-hostname.md`, `docs/NAVIGATION.md`, `docs/DECISIONS.md` +
  `skills/ARCHITECT.md` (ADR-079), `docs/CHANGELOG.md`.
- **polish(desktop): smooth, cursor-gated tab dragging.** The pointer drag now
  animates with FLIP: each tab that changes slot slides from its old X to its
  new X (170ms, `cubic-bezier(0.2,0.8,0.2,1)`) instead of snapping, and a newer
  reorder cancels the older animation so rapid drags never stack transforms.
  Insertion is decided by crossing a neighbour's MIDPOINT (stable under reflow,
  no oscillation), the strip auto-scrolls near either edge, and the dragged tab
  is lifted (ring + shadow + slight fade). The grab cursor is applied only while
  a drag is active; hovering a tab shows the normal arrow, so there is no false
  drag affordance. Mouse/pen only — touch still scrolls the strip.
  Docs updated: `desktop/README.md`, `docs/CHANGELOG.md`.
- **feat(shell): a branded "Eclipse is offline" page replaces the browser's
  `ERR_CONNECTION_REFUSED` screen.** When the local server stops, nothing is
  listening on the origin, so the browser painted its own error page with the
  browser's chrome and wording — a stopped Eclipse looked like a broken website.
  A service worker (`public/sw.js`, registered by `OfflineReady`) now handles
  **page navigations only**: a network error or the local proxy's `502` is
  answered with a cached `/offline` document rendered through the user's saved
  app-wide theme (`src/lib/offline/page.ts`, `src/app/offline/route.ts`), with
  the inlined shipped wordmark. The card says the local server stopped, shows
  `black eclipse`, probes a static asset every 2 s and reloads into the app when
  it answers. API calls, chunks, assets, POSTs and the app's own 4xx/5xx pages
  still pass through untouched; `/offline` is public and `sw.js` sits outside the
  middleware matcher so a signed-out tab still gets the page. Docs updated:
  `docs/ARCHITECTURE.md` (Layer 0), `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(desktop): cross-platform **runtime** verified — all three smoke tests
  pass.** CI run `43084460874` on `9180767`: Windows, Ubuntu and macOS all green,
  and each one launched its real artifact and answered HTTP 200 —
  `[smoke] PASS` after 15 s (Windows), 16 s (Linux, installed `.deb` under Xvfb)
  and 4 s (macOS `.app`). Two further defects were fixed to get there: runtime
  state moved out of the install directory into `<data>/.runtime` (a system
  `.deb` is root-owned, so the bootstrap could not create its lock directory),
  and the payload now copies **every top-level Next manifest** — standalone
  output omits `routes-manifest.json`, `prerender-manifest.json`,
  `export-marker.json`, `images-manifest.json`, `trace` and the `.nft.json`
  files, which killed the server at startup on both non-Windows platforms. Docs
  updated: `docs/desktop-cross-platform-plan.md` (runtime evidence + 7 defects),
  `docs/CHANGELOG.md`.
- **fix(desktop): payload carries the full set of Next build manifests.** Both the
  Linux and macOS smoke tests launched the installed app and it died with
  `ENOENT ... .next-desktop/routes-manifest.json`. Next's standalone output only
  includes a subset of the top-level manifests, so the payload was missing
  `routes-manifest.json`, `prerender-manifest.json`, `export-marker.json`,
  `images-manifest.json`, `trace` and the `.nft.json` files. The assembler now
  copies **every top-level file** from the build into the payload (never the
  directories, which are handled separately or are the multi-GB cache). The same
  run confirmed the runtime-state fix works: the shell log appeared under
  `<data>/.runtime` on Linux. Docs: no doc change — packaging fix.
- **fix(desktop): reordering tabs now uses pointer events, so it works in an
  already-installed shell.** The previous fix (`.disable_drag_drop_handler()`)
  only helps a *rebuilt* native window; any shell installed before it still
  swallows HTML5 drag-and-drop, so the tabs stayed stuck. The strip now tracks
  `pointerdown/move/up` directly (5px dead zone, live hit-test via
  `elementFromPoint`, click suppressed after a drag, mouse/pen only so touch
  still scrolls) and moves the tab through the same pure `moveTab` rule. The
  native opt-out remains for workspace widgets and chart symbol drops.
  Docs updated: `desktop/README.md`, `docs/CHANGELOG.md`.
- **fix(appearance): every page now paints the saved THEME, not a grey
  substitute.** Two causes. (1) The theme was hydrated only inside the app shell
  (`StockChatContent`), so standalone routes — `/events`, `/fabric`, `/recovery`,
  `/theses`, `/alerts`, `/terminal`, `/login`, `/app-view`, `/figure` — fell back
  to the shipped `:root` light tokens (a grey page) instead of the user's theme.
  New `src/components/layout/theme-hydrator.tsx` runs `useHydrateTheme` +
  `useHydrateBackground` once at the root in `app/layout.tsx`. (2) The desktop
  glass window forced `body`/`.app-page-bg` transparent and laid a fixed acrylic
  scrim over every page, ignoring the palette entirely; pages now paint
  `--background`, the page pattern and the landing wallpaper like the browser
  front door, while only the native window behind the app stays glassy.
  Docs updated: `desktop/README.md`, `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **fix(desktop): runtime state moves out of the install directory.** The Linux
  smoke test launched the app from the installed `.deb` and it never served:
  `/usr/lib/blackeclipse` is root-owned, so the bootstrap could not create its
  lock/stamp directory and exited. Runtime state (locks, guard stamps, log) now
  lives beside the user's data (`<data>/.runtime`), and the shell falls back to
  the data directory when the install directory is not writable — which keeps a
  per-user Windows install working exactly as before. The smoke test now reads
  the shell log from that fallback location too. Verified: `cargo check` clean,
  both scripts parse. Docs: no doc change — packaging fix.
- **test(desktop): runtime smoke test in CI for all three platforms.** A build
  that compiles is not an app that runs, so `scripts/desktop-smoke.js` launches
  the packaged binary from its real layout, waits for the local server to answer
  (`503` counts — it is the app's warm-up gate), and dumps the log tail on
  failure. The matrix runs it on Windows (dist), Linux (installs the `.deb`, runs
  under `xvfb-run` with software rendering) and macOS (the `.app` binary). Also
  added `xvfb` to the apt set and `npm run desktop:smoke`. Locally the smoke
  correctly rejected a **stale local payload** (missing
  `.next-desktop/prerender-manifest.json` from an interrupted concurrent build),
  which is exactly the class of defect it exists to catch. Docs: no doc change —
  CI/test-only.
- **fix(desktop): tabs can be dragged again; each tab owns its sidebar mode; the
  chat surface is no longer see-through.** Three desktop-only defects:
  (1) WebView2 replaced the page's HTML5 drag handler with Tauri's file-drop
  handler, so no `draggable` element worked (tab reorder, workspace widgets,
  chart symbol drops). The window now calls `.disable_drag_drop_handler()`; the
  shell never consumed Tauri `DragDropEvent`s, so nothing is lost.
  (2) The sidebar menu mode is one `sessionStorage` value shared by every
  in-page desktop tab, so a Bots tab and a Command Center tab fought over it.
  `DesktopTab` now carries `mode`, the strip records the mode into the active
  tab and restores it on switch (new pure `setTabMode`; new
  `applyTabMode` store action that never echoes to the app-wide nav store).
  (3) `html.glass-window` dropped the chat surface, leaving an existing
  conversation on translucent acrylic that read washed-out white over a bright
  desktop. The landing wallpaper is still dropped, but the conversation keeps
  its normal surface (`#0a0b0b` dark default) and the store's own opacity.
  Docs updated: `desktop/README.md`, `docs/CHANGELOG.md`.
- **chore: normalize one stray CRLF in `scripts/desktop-bundle.js`.** The file
  was committed with 236 bare-LF lines and a single CRLF blank line at EOF,
  which failed the working-tree line-ending guard. Content is unchanged (git
  sees no diff after normalization). No doc change — line-ending hygiene only.
- **feat(desktop): cross-platform builds verified — Windows, macOS and Linux all
  green.** CI run `43066805555` on `57e670e` produced three artifacts:
  `black-eclipse-windows` (364 MB), `black-eclipse-macos` (147 MB) and
  `black-eclipse-linux` (133 MB). That is the first proof the Tauri shell
  compiles against Linux's webkit2gtk and that `dpkg-deb`/`hdiutil` produce
  installable files. Five defects were found by running it: the Next build OOM'd
  on every runner (now `--max-old-space-size=6144`); `codesign --deep` failed on
  `node_modules/next/.../lodash.curry` (signing the binary and bundle separately
  now); `npm ci --ignore-scripts` skipped `python/requirements.txt` so four packs
  were empty (now runs `setup-python.js`); the offline NSIS edition hard-coded
  all five packs (list generated at build time); and a flaky Ubuntu mirror
  (retries added). C5 notarisation remains a gated skeleton. Docs updated:
  `docs/desktop-cross-platform-plan.md` (verified status + CI evidence),
  `docs/CHANGELOG.md`.
- **ci(desktop): retry apt on flaky runner mirrors.** The `ubuntu-latest` job
  failed in *Install Linux build dependencies* with
  `Temporary failure resolving 'security.ubuntu.com'` and a `404` from
  `azure.archive.ubuntu.com` — runner/mirror infrastructure, not our code. The
  step now retries `apt-get update` and `install` up to three times with
  `Acquire::Retries=5` and a 20-minute ceiling, so a transient outage does not
  fail the matrix. macOS **succeeded** in this run (first non-Windows artifact);
  Windows was still building installers. Docs: no doc change — CI-only.
- **fix(desktop): install Python requirements in CI, unblock apt, tolerate missing packs.**
  Three failures from the matrix run, each with a distinct cause:
  (1) the Windows payload was 503 MB instead of ~900 MB and the offline edition
  refused to build because four packs were empty — `npm ci --ignore-scripts` skips
  the postinstall that installs `python/requirements.txt`, so the packaged
  interpreter had no packages. The workflow now runs `setup-python.js` after
  provisioning the interpreter.
  (2) `ubuntu-latest` hung for 30+ minutes in *Install Linux build dependencies*;
  the apt step now sets `DEBIAN_FRONTEND=noninteractive` and a 15-minute timeout.
  (3) the offline NSIS edition hard-coded all five packs, so a platform missing
  one (winsdk has no Linux wheel) aborted the whole installer. The pack list is
  now generated at build time and the edition includes whatever exists.
  Docs: no doc change — CI/packaging fix.
- **fix(desktop): macOS bundling no longer uses `codesign --deep`.** The matrix
  run reached the bundle step and failed with *"bundle format unrecognized,
  invalid, or unsuitable. In subcomponent: ... app/node_modules/next/dist/
  compiled/lodash.curry"* — `--deep` descends into the payload and treats files
  like that as nested bundles. The executable and the `.app` are now signed
  individually, and a signing failure degrades to an unsigned `.dmg` instead of
  aborting the job. Also confirmed the heap fix worked: macOS cleared the payload
  build that previously OOM'd. Docs: no doc change — CI/packaging fix.
- **ci(desktop): raise the Node heap for the matrix build.** The first real
  matrix run (dispatch on `main`) failed `macos-latest` at *Build the standalone
  payload* with `FATAL ERROR: Reached heap limit — JavaScript heap out of memory`;
  the Next build exceeds Node's default ~4 GB heap on a runner. The build job now
  sets `NODE_OPTIONS=--max-old-space-size=6144` and disables Next telemetry.
  Windows and Linux were still running at the time of the fix. Docs: no doc
  change — CI-only.
- **test(desktop): cross-platform layouts verified off-platform.** Added
  `--dry-run` / `--target deb|mac` to `desktop-bundle.js` so the `.deb` and
  `.app` staging trees can be built and inspected on a machine that cannot run
  `dpkg-deb` or `hdiutil`. Verified here: the Debian tree (packages, launcher,
  desktop entry, `DEBIAN/control` at 0.3.3), the macOS bundle
  (`Contents/MacOS/{binary,app,runtime}`, valid `Info.plist`), every pinned
  download URL (python-build-standalone ×3 targets, Node ×3 targets — all
  HTTP 200), and the workflow YAML (2 jobs, 3-OS matrix, 17 steps). Also made the
  shell binary lookup platform-aware so a dry run on Windows finds
  `Black Eclipse.exe`. The shell compiling against Linux's webkit2gtk and the
  vendored interpreter booting on macOS remain unverified — that requires a real
  runner. Docs updated: `docs/desktop-cross-platform-plan.md`,
  `docs/CHANGELOG.md`.
- **feat(desktop): packaged installs show the Black Eclipse logo in Task Manager
  for the runtime processes too.** Windows takes a process's icon and display name
  from the executable it runs, so `runtime\node.exe` and
  `app\scripts\vendor\python\python.exe` used to appear as "Node.js JavaScript
  Runtime" and "Python" with the upstream logos. New `scripts/brand-runtime.js`
  rewrites their icon + `VERSIONINFO` strings (`resedit`, devDependency) and is
  called by `desktop:package`; `npm run desktop:brand` re-applies it to an existing
  `dist/BlackEclipse`. It also repairs the Resource/BaseRelocation data directories
  after `NtExecutable.generate()` moves a section (Python's `.reloc`), so the
  output re-parses cleanly and is idempotent. Behaviour is unchanged; upstream
  Authenticode signatures on those copies are invalidated (the install is unsigned
  anyway). `desktop:dev` / repository checkouts are untouched. Docs updated:
  `desktop/README.md` (Task Manager identity table, `desktop:brand`),
  `docs/CHANGELOG.md`.
- **feat(desktop): cross-platform shell (C0) and per-OS packaging (C1–C5).**
  C0: the six Windows-only call sites in the shell are now guarded — `taskkill`
  stays on Windows while Unix starts the bootstrap in its own session
  (`setsid`) and signals the process group, so the Next server and the Python
  harness still die together; the WebView2 probe and message box are
  `#[cfg(windows)]`; the bundled runtime is `runtime/node[.exe]`; the data
  directory resolves to `%LOCALAPPDATA%` / `~/Library/Application Support` /
  `$XDG_DATA_HOME`; Node install paths are per-OS. C1/C2: `desktop-runtime.js`
  fetches the **platform's** Node from nodejs.org and verifies
  `SHASUMS256.txt`, `setup-portable-python.js` provisions relocatable CPython
  for macOS/Linux (Windows keeps its working embed flow), and
  `desktop-bundle.js` builds a `.deb` via `dpkg-deb` or a `.app`+`.dmg` via
  `hdiutil` with an ad-hoc signature. C3: pack manifests carry `target`.
  C4: the release workflow is a Windows/Ubuntu/macOS matrix with one publish
  job. C5: `notarytool`+`stapler` steps are present but gated on Apple secrets,
  so they skip cleanly. Verified on Windows: `cargo check` clean, packaging
  succeeded with a checksum-verified Node download (901 MB app / 988 MB total).
  Linux and macOS builds need their own runners — that is what the matrix is
  for. Docs updated: `docs/desktop-cross-platform-plan.md` (status + call-site
  table), `docs/CHANGELOG.md`.
- **fix(desktop): stay on the loopback origin so Tauri IPC (glass/window chrome)
  keeps working.** When a browser-path server was already running, the shell
  attached to it and followed its `BE_CANONICAL_HOST` 307 to
  `https://blackeclipse`; that origin was not in the capability allowlist, so
  `window.__TAURI__` vanished and glass/window actions silently stopped. The
  spawned desktop server now strips `BE_CANONICAL_HOST`, and the capability also
  allows `https://blackeclipse/*` + `http://blackeclipse/*` for attach mode.
- **fix(desktop): let the acrylic blur show through.** The OS acrylic was working,
  but the page scrim at 55% opacity hid it, so the window read as flat grey. The
  scrim is now 20% (dark) / 46% (light), so the blurred desktop is visible while
  text stays readable; the left sidebar remains fully opaque. Windows
  `EnableTransparency` was OFF on this machine, which makes acrylic fall back to
  solid grey — it is now enabled.
- **docs(desktop): cross-platform plan.** Added
  `docs/desktop-cross-platform-plan.md`. Audit found the application is already
  portable — the whole Python harness has only five Windows imports (`msvcrt` ×2,
  `win32` ×2, `MetaTrader5` ×1) — and the Windows coupling is limited to six call
  sites in the Tauri shell (`taskkill`, `MessageBoxW`, the WebView2 registry
  probe, the Node path fallback, `CREATE_NO_WINDOW`, `%LOCALAPPDATA%`). Phases
  C0–C5: guard the shell for all targets, ship **Linux first** (free, no
  gatekeeper), then macOS (ad-hoc signed; notarisation costs $99/yr and is its
  own decision), per-platform packs, and a CI matrix. MT5 and the
  computer-control pack are recorded as permanently Windows-only rather than
  pretended otherwise. Docs updated: `docs/desktop-cross-platform-plan.md`,
  `docs/CHANGELOG.md`.
- **fix(desktop): no white flash on the glass window.** A reload painted the
  WebView's default white before `globals.css` arrived, which was very visible
  through the translucent window. `layout.tsx` now sets a critical pre-paint
  background (`#0a0b0b` dark / `#f5f5f7` light, transparent once
  `html.glass-window` is set), and the acrylic tint/scrim were deepened (tint
  alpha 175, scrim 0.55) so a bright desktop cannot wash the app out. Docs
  updated: `docs/CHANGELOG.md`.
- **fix(chat): the selected-text Quote chip sits above the passage, follows the
  cursor, and the selection highlight is continuous.** The chip was anchored to
  the middle of a multi-line range and used a 0.5-alpha glass fill, so it covered
  prose and the message text read through the pill; it now follows the release
  point horizontally, floats above the selected block (flipping below only when
  there is no room), uses the denser `.quote-chip` surface, and sits at
  `z-[150]`. Empty bands between selected lines/paragraphs (the browser only
  paints glyph boxes) are filled with the same `primary/30` accent via the new
  pure `lib/chat/selection-band.ts` (band merge + gap fillers, tested); they
  paint BEHIND the prose inside an isolated wrapper, so they never overlap or
  tint the selected text. Also
  handles touch/pen (`pointerup`), resets the anchor on a new gesture, and adds
  `selection:bg-primary/30` on the transcript so the filler always matches.
  No doc change — UX fix, contracts unchanged.
- **docs(harness): add the Round 5 core-integrity plan.** A code-level audit
  against OpenCode v2.2.7 found that the main agent loop bypasses the model
  retry/fallback runtime (`graph.py` calls `model_stream` directly), the run
  timeout is really a per-call timeout, foreground runs never register for
  SSE/cancel, and four execution planes duplicate scheduler semantics. The plan
  sets one loop, one scheduler, one event log, one tool contract and one policy
  seam, with fault-injection gates, measurable SLOs, a delete list and twelve
  ordered PRs. Docs updated: `docs/harness/roadmap/round-5-core-integrity.md`
  (new), `docs/harness/roadmap/README.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **fix(harness): the agent loop owns retries, the run deadline, and foreground
  run registration (Round 5 / C0–C2 core).** `graph.agent_node` now calls the
  new `step.invoke_model_step` instead of `model_stream` directly, so the shared
  `RetryPolicy` (3 attempts, jittered 1–10 s, 90 s budget, `Retry-After`
  honored) applies to the only path that matters; retries emit a durable
  `model.retry` event and are refused after text has streamed. `run_timeout_s`
  is now the run's wall clock (`RunDeadline`) with a separate per-call ceiling,
  checked before every model call and tool turn (`RUN_TIMEOUT`). `service.run`
  registers foreground runs in `_active` like `run_background`, ends its stream
  on completion, and an optional `HARNESS_MAX_CONCURRENT_RUNS` semaphore bounds
  admission. The LangChain tool fallback context moved from a registry class
  attribute to a `ContextVar`, so two concurrent runs can no longer overwrite
  each other. New tests: `python/tests/test_step_retry.py`,
  `python/tests/test_execution_registry.py`, plus the updated parity pin. The
  Python size ratchet is re-pinned on purpose (`graph.py` 2547→2573,
  `service.py` 1848→1915) for the deadline and registration seams.
  Docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H348), `docs/harness/roadmap/round-5-core-integrity.md`,
  `docs/CHANGELOG.md`.
- **feat(harness): an evidence-backed scorecard and strict gate (Round 5 / C0).**
  `scripts/harness-scorecard.js` reads `docs/harness/scorecard.json`, verifies
  every evidence path exists, refuses a `measured` dimension with no metric, and
  generates `docs/harness/scorecard.md`. `--check` fails on a stale report;
  `--strict` fails while any dimension is not measured. The current baseline is
  honest: **0 measured, 7 partial, 1 unmeasured (ops)**, so the strict gate is
  deliberately red until the remaining workstreams land. Scripts:
  `npm run harness:scorecard`, `harness:scorecard:check`,
  `harness:scorecard:gate`. Docs updated: `docs/harness/scorecard.json` (new),
  `docs/harness/scorecard.md` (generated),
  `docs/harness/roadmap/round-5-core-integrity.md`, `docs/CHANGELOG.md`.
- **feat(harness): C2 execution substrate — one vocabulary, one migration
  ledger, one checkpoint cursor.** `execution_plane.py` defines the canonical
  `ExecutionPhase`/`JobKind` and total adapters from `RunStatus`, `JobState`,
  `TaskStatus` and `graph_runtime.RunStatus` (unknown → `None`).
  `migrations.py` adds a per-namespace `SchemaMigration` ledger that applies each
  opted-in migration once, in order, transactionally (a failure rolls the batch
  back); `RunLineage` is its first user. `RunMessage` now stores the full
  conversation and `RunCheckpoint.payload.messageSeq` is a cursor into it, with
  the bounded legacy tail as a fallback — a long run no longer loses its early
  evidence on resume. `graph.py` is re-pinned 2573→2588 for the cursor seam.
  New tests: `test_execution_plane.py`, `test_migration_ledger.py`,
  `test_run_message_cursor.py`, plus the resume pin. The scheduler merge and the
  unified event log remain open. Docs updated: `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H349),
  `docs/harness/roadmap/round-5-core-integrity.md`,
  `docs/harness/scorecard.json`, `docs/harness/scorecard.md`,
  `docs/CHANGELOG.md`.
- **feat(harness): C2 completed — the Fabric owns task execution and
  `ExecutionEvent` is the one append-only log.** A `task` Fabric job + worker now
  runs each claimed task through the same `service.task_executor`; the task
  scheduler keeps its claim/lease/heartbeat/verification loop as the producer,
  falls back inline only when the submit itself fails, and never silently re-runs
  a submitted job. `execution_log.py` adds one per-entity-sequenced, bounded,
  fail-open `ExecutionEvent` log; the run emitter and the Fabric, graph-runtime,
  task and orchestration stores append to it while their legacy tables remain as
  projections. New tests: `test_execution_log.py`,
  `test_task_scheduler_fabric.py`, `test_fabric_task_worker.py`. Docs updated:
  `docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H350),
  `docs/harness/roadmap/round-5-core-integrity.md`,
  `docs/harness/scorecard.json`, `docs/harness/scorecard.md`,
  `docs/CHANGELOG.md`.
- **refactor(harness): a run is a `RunScope` + `RunSpec`, not 45 keywords
  (Round 5 / C2.1).** `build_graph(spec, scope)` replaces the ~45-keyword
  signature; `run_scope.py` holds the reusable services (`RunScope`) and the
  per-invocation facts (`RunSpec`), and the graph unpacks both at the top so node
  bodies and tools see the same locals. `RunSpec` copies the allowlist, so a run
  cannot mutate the caller's surface. A contract test pins the two-parameter
  signature. Docs updated: `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H351),
  `docs/harness/roadmap/round-5-core-integrity.md`,
  `docs/harness/scorecard.json`, `docs/harness/scorecard.md`,
  `docs/CHANGELOG.md`.
- **feat(harness): C3 tool economics — full-output handles, discovery, and a
  lazy surface.** A truncated tool result now stores its full text in
  `ToolOutput` (run-scoped, 2M-char ceiling) and returns `output_id`; the result
  names the handle and `read_tool_output` pages it (12k default, 24k max).
  `tool_search` returns matching tools with exact schemas; `tool_invoke` runs a
  discovered READ-ONLY tool and refuses effectful ones so the graph remains the
  only side-effect path. `HARNESS_LAZY_TOOLS=1` keeps effectful tools bound and
  routes the read-only long tail through discovery (default OFF until eval
  parity). **Code Mode is shipped** behind `HARNESS_CODE_MODE=1`: `tool_code`
  runs a short Python program in a `code/sandbox.py` child (process-tree kill,
  scrubbed env, no network, CPU/memory caps, fresh temp cwd) and bridges
  READ-ONLY tool calls over JSON lines; effectful tools are refused at the
  bridge, the call budget is 20, and a missing isolation primitive is a named
  refusal. New tests: `test_tool_output_offload.py`, `test_tool_surface.py`,
  `test_code_mode.py`; the published tool registry is regenerated (1086 tools).
  Token accounting/measured-window budgeting and always-on deterministic
  compaction were already present and are now covered under C3.
  Docs updated: `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H352),
  `docs/harness/roadmap/round-5-core-integrity.md`,
  `docs/harness/scorecard.json`, `docs/harness/scorecard.md`,
  `docs/harness/tool-registry.json`, `docs/CHANGELOG.md`.
- **feat(harness): C4 goal/plan/evidence — verify the work, not the prose.** A
  run may carry `input.context.c4Plan` (objective + acceptance + steps, or a
  `planId` to continue). `harness/goals/` stores the goal plan view, the
  `EvidenceClaim`/handle ledger and plan iterations on `agent-memory.db`. Tool
  results contribute handles (run record, file+sha, tool output, artifact,
  citation, record, computation); the answer seam records checkable sentences
  (numbers, finance shapes, URLs, test/build and produced-file claims) and a
  deterministic verifier registry rejects a finance number with no
  computation/report/citation/record, a URL with no citation, a pass claim with
  no check, or a file claim with no artifact. A rejection with budget left diverts
  through the bounded replan (max 2), supersedes the failed draft's answer claims
  but keeps its tool evidence; otherwise the step fails. The ledger/outcome
  always record the claims; the answer-text disclosure is opt-in
  (`HARNESS_EVIDENCE_ENFORCE=1`) until eval parity. The checkpoint carries `planId`/`planIteration`/`stepId`,
  so a later run continues the first non-verified step after a kill, and
  `GET /runs/{id}/outcome` exposes `goal` + `evidence` blocks. New tests:
  `test_c4_{goals,verifiers,plan_runtime,answer,replan,resume,outcome}.py`.
  Docs updated: `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H353),
  `docs/harness/roadmap/round-5-core-integrity.md`,
  `docs/harness/scorecard.json`, `docs/harness/scorecard.md`,
  `docs/CHANGELOG.md`.
- **feat(harness): C5 one agent fabric — spawn, blackboard, deterministic
  synthesis.** The `spawn` tool submits a normal Fabric `agent` job with
  `parentRunId`, a clamped budget (`maxSteps`/`runTimeoutMs`), depth 2, fanout 8
  and a 120k total child-token allocation reconciled as
  `allocated = used + returned`; no operator/autonomy inheritance; refusals are typed
  (`DEPTH_EXCEEDED`/`CHILD_LIMIT`/`BUDGET_EXCEEDED`). A child returns a typed
  `ChildOutcome` (output, claims, handles, usage); its evidence is copied into
  the parent ledger with a `child:<runId>` verifier. `board_write`/`board_read`/
  `board_search` share one bounded blackboard per ROOT run (200 entries / 200k
  chars), reached by walking `parentRunId`; unrelated trees are isolated.
  Multi-child spawns return deterministic synthesis (dedupe, conflict,
  provenance), never a model merge. New tests: `test_c5_spawn.py`,
  `test_c5_blackboard.py`. A2A/team keep their planned task rows, but their
  execution attempt is routed through `spawn` (`tasks/spawn_bridge.py`) when the
  Fabric is available, with an inline fallback; `delegate` is the legacy entry
  point. Docs updated:
  `docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H354),
  `docs/harness/roadmap/round-5-core-integrity.md`,
  `docs/harness/scorecard.json`, `docs/harness/scorecard.md`,
  `docs/harness/tool-registry.json`, `docs/CHANGELOG.md`.
- **fix(charts): 3D marks are discoverable and draw from a flat `z` grid; an
  unsupported mark is named, not silently drawn as a line.** The live
  `response_block_schema` digest (and the injected prompt digest) now includes
  the nested `panels[].marks[]` fields, so the 3D mark vocabulary
  (`scatter3d`/`surface`, `z`, `matrix`) is visible instead of guessed; `kind`/
  `markType` are normalized to the canonical mark `type`, and a 2D `z` is read
  as the surface `matrix`. A `surface` now accepts the natural sweep shape
  (`x` + `y` + flat row-major `z`) in both Plotly and the matplotlib fallback.
  An unknown/missing mark primitive is preserved by the contract and reported
  by name in `response_validate` and the chart surface instead of falling back
  to an unrequested line. Docs updated: `docs/chart-engine.md`,
  `docs/CHANGELOG.md`.

## 2026-11-10
- **feat(desktop): glass window with an opaque sidebar.** The frameless shell now
  builds a transparent window and applies OS **acrylic** blur behind the WebView
  (`window-vibrancy`, with a legacy blur fallback), so the desktop shows through a
  real blur instead of a flat fill. The app paints only a contrast scrim; the
  landing wallpaper/chat surface are dropped and the left sidebar is forced
  opaque. New **Settings › General › Window › Glass window** switch (desktop
  only) persists in `be_window_glass_v1` and in `desktop-prefs.json`, applying
  live through the `be-window` event (`set-glass`). The browser front door is
  unchanged.
  Docs updated: `desktop/README.md`, `docs/CHANGELOG.md`.
- **feat(desktop): keyboard tab reordering.** The tab strip could be reordered by
  dragging; it now also moves the ACTIVE tab with `Ctrl/Cmd+Shift+Home` (first),
  `Ctrl/Cmd+Shift+End` (last), and `Ctrl/Cmd+Shift+PageUp/PageDown` (or ←/→, one
  slot). Chords are skipped while typing or behind a modal via
  `canHandleKeyboardEvent`, the moved tab is scrolled into view, and the four
  chords are listed in the shortcuts dialog (`src/lib/shortcuts.ts`). Pure
  `moveTabBy` / `moveTabToEdge` helpers keep the reorder rules testable.
  Docs updated: `desktop/README.md`, `docs/CHANGELOG.md`.
- **fix(desktop): sidebar spans the full page; tabs start to its right.** The
  full-width tab strip sat ABOVE the sidebar+content row, and the sidebar's
  `h-full` resolved against the root height, so it overflowed by exactly the tab
  bar (measured live: sidebar 43.2→851.2 in an 808px viewport) and its bottom
  entries — broker/settings — were clipped. `DesktopTabBar` moved inside the
  content column, so the sidebar owns the full height at the window's left edge
  and the tab strip begins after it, aligned with the content. Verified via CDP:
  sidebar `top=0`, `height=808`; tab strip starts at `x = sidebar width`.
- **fix(desktop): maximize keeps the taskbar visible; the full sidebar opens by
  default.** Native `maximize()` on a `decorations(false)` window fills the whole
  monitor, so the bottom of the app sat under the Windows taskbar no matter what
  bounds were restored. Maximize is now emulated by sizing the inner area to the
  monitor's work area (`fill_work_area`, with the windowed bounds preserved for
  restore and `persist_bounds` skipping emulated-maximize resizes), re-asserted
  after first paint because Windows can apply the initial size asynchronously.
  The desktop store hydrates expanded: `readStoredCollapsed` returns false when
  the Tauri bridge is present, so an earlier collapsed session no longer leaves
  the shell with only the icon rail (runtime Ctrl/Cmd+B still works). Docs
  updated: `desktop/README.md`, `docs/CHANGELOG.md`.
- **chore: revert build pollution in `tsconfig.json`.** A payload build appends
  `.next-desktop/types` to `include`, and it was committed by mistake. Removed.
  The restore guard in `desktop-payload.js` already prevents this at build time;
  this only fixes the tracked file. Docs: no doc change — build hygiene only.
- **build(desktop): publish packs as archives with hashes.** The five optional
  packs were assembled as folders, which a browser or a stub installer cannot
  fetch. `desktop-package.js` now writes `dist/packs/<name>.zip` (via the
  Windows-shipped `tar -a`), records `zipBytes` and the SHA-256 in
  `dist/packs/manifest.json`, and the release workflow uploads the archives plus
  the manifest and attaches them to the release. Nothing in the installed app
  changed. Docs: no doc change beyond this entry — the pack catalogue in
  `docs/desktop-size-plan.md` is unchanged.
- **fix(desktop): real tab instances, and the window no longer hides under the
  taskbar.** `+` used to re-select the single Chat page; tabs are now instances
  (`{ id, page }`, v2 storage with a v1 migration), so `+` appends a real tab
  that starts on a fresh Chat session and later follows whatever page the user
  opens in it — duplicates like two Chat or two Portfolio tabs are allowed,
  drag-reorder and close are id-based. Saved window bounds are clamped to the
  monitor's work area on launch (`clamped_bounds`), fixing a 1924×1092 restore
  on a 1920×1080 screen whose bottom sat behind the Windows taskbar. Docs
  updated: `desktop/README.md`, `docs/CHANGELOG.md`.
- **ci(desktop): install only what packaging needs on the runner.** The
  `npm ci` postinstall hook also performs global link wiring and git-hook
  installation — developer-machine concerns that can fail on a clean runner and
  would break the release workflow before the payload is ever built. The workflow
  now runs `npm ci --ignore-scripts` plus `prisma generate` and
  `setup-python.js` explicitly. No app behaviour changed. Docs: no doc change —
  CI-only.
- **polish(setup): no star glyph, rail strictly behind the step discs, wider
  notice.** The Welcome step icon is a rocket (mode cards use a user and a
  briefcase) instead of the sparkle star the user rejected. The stepper
  connector is now one continuous line behind opaque, tinted discs, so it can
  neither show through an icon glyph nor run past the last step (the list is
  `mb-auto`, not `flex-1`). Step glyph colours follow their disc: near-black on
  the light accent disc, accent lime on the dark completed disc (inline, because
  `globals.css` greys any span class containing `text-primary` with
  `!important`). The full risk notice paragraph spans its card instead of being
  clamped by `max-w-prose`. Docs: no doc change beyond this
  entry — layout contract in `docs/onboarding-plan.md` is unchanged.
- **fix(desktop): window chrome works, `+` starts a session, tab bar matches the
  app.** The frameless title bar's controls and drag depended entirely on the
  injected `be-window-action` event script, which silently no-ops when the
  global Tauri API is absent; the buttons now call the core window API
  (`minimize` / `toggleMaximize` / `close` / `startDragging`) with the event
  bridge as fallback, and `capabilities/default.json` grants those four window
  permissions plus an internals-based `plugin:event|emit` fallback in the init
  script. Tabs can be dragged to reorder (new pure `moveTab`), the strip paints
  from the same resolved page-background vars as the ChatBot landing
  (`--app-bg-color` / dark variant, falling back to `--background`) instead of a
  flat `#0D0D0D`, and the `+` button immediately opens a fresh Chat session
  instead of a page-picker menu. Until the next payload build ships
  `.desktop-tab-bar`, the shell's init script injects that one rule so the
  installed chrome matches immediately.
  Docs updated: `desktop/README.md` (window chrome + bridge fallback),
  `docs/CHANGELOG.md`.
- **feat(setup): redesigned first-run onboarding as a two-column stepper.** The
  single 580px card became a 1060px setup card with a left rail (wordmark +
  clickable numbered/iconed step list: active, completed, locked) and a right
  panel (icon, 22px step title, one-line description, scrollable body, pinned
  footer with Skip/Back and Continue/Finish). Copy was raised from the dense
  8–10px scale to 11.5–13px so the questions are readable, and `Finish setup`
  moved from the Review body into the pinned footer. No change to the setup
  contract, state, API or defaults. Docs updated:
  `docs/onboarding-plan.md` (§2.2 shared frame, §5 UI spec); `docs/CHANGELOG.md`.
- **fix(chat): typing in the composer can no longer fire shell shortcuts.** The
  Ctrl/Cmd+Alt+N (new chat) and Ctrl+Alt+X (focus mode) handlers checked only
  blocking dialogs, and both accept the physical key `code` because AltGr
  reports Ctrl+Alt — so typing an AltGr character such as `ń` (AltGr+N) wiped the
  draft and `ż` (AltGr+X) toggled focus mode mid-word. Both now use
  `canHandleKeyboardEvent`, the same editable/composition guard as every other
  chord, so all shortcuts skip the chat input (and every text field) while it has
  focus. No doc change — bug fix, no contract or architecture change.
- **test(prompt): re-pin the agent-prompt ratchet to the measured size.** Commit
  `93aebd01` (quant research intelligence) added the “never end with a bare
  refusal” rule and the Quant research guidance but did not update the ceiling,
  so `test_memory_tools.py::test_prompt_char_ceiling` and
  `test_phase_s_stabilization.py::test_prompt_ceiling_was_lowered_not_raised`
  failed on an unchanged prompt (47,121 chars vs the 45,694 pin). Re-pinned
  45,694 → 47,121 in both files with the reason recorded; both pass.
  No doc change — test ratchet only.
- **feat(desktop): browser-style page tabs replace the native title bar.** The
  window is now frameless. A `#0D0D0D` tab strip above the app shows the open
  top-level pages (icon, label, close, `+` page picker), restores the open set
  from `localStorage`, and owns the drag region plus
  minimize/maximize/close. Window actions cross the existing `be-window` event
  bridge, so the remote app origin needs no new command ACL; the bundled splash
  gained a minimal drag/close strip. The browser front door is unchanged —
  `DesktopTabBar` renders nothing without the Tauri bridge. The size guard now
  skips `dist/` build artifacts (they were failing the source budget after a
  packaging run). Docs updated: `desktop/README.md`, `docs/CHANGELOG.md`.
- **feat(desktop): offline (full) edition, and a real regression caught by it.**
  `npm run desktop:installer -- --full` now builds
  `BlackEclipse-Setup-<v>-full.exe` (258 MB) containing core **plus all five
  packs**, for machines with no network; the slim edition (141 MB) stays the
  default download. `SHA256SUMS.txt` now covers every installer present, and the
  release workflow builds both. **Regression found and fixed:** pruning
  `*.dist-info` (7 MB) broke `plotly`, which calls
  `importlib.metadata.version(__name__)` at import time and died with
  `PackageNotFoundError` — proven by importing every pack from the installed full
  edition. The metadata is kept; the 7 MB is not worth it. Verified: full install
  is 1,253 MB and `sklearn`, `xgboost`, `playwright`, `fitz` all import from the
  installed copy. Docs updated: `docs/desktop-size-plan.md` (two editions, S2–S4
  blocked-on-hosting note), `docs/CHANGELOG.md`.
- **chore(data): removed four leftover “ZZ …” test pages.** The saved-pages
  navigation showed `ZZ Verify Live Swap Spreads`, `ZZ Temp Field A`,
  `ZZ Temp Bare Check` and `ZZ Temp Swap Spread Check` — all personal pages
  owned by `operator`, created 2026-11-09 while testing swap-spread widgets.
  They were runtime data (UI blueprints), not source routes, so they were
  deleted through `DELETE /api/sdk/pages/{id}` with `x-eclipse-user: operator`
  (the SDK proxy maps that to `X-Harness-User`). Afterwards
  `GET /api/sdk/pages` returns `total: 0`. No code or contract changed.
  No doc change — runtime data cleanup.
- **fix(desktop): a 307 from the browser path is attachable, not a conflict.**
  With `npm start` already running on 3100, `/` answers 307 to the canonical
  `https://blackeclipse` hostname and carries no HTML, so the shape check failed
  and the shell reported a port conflict — the desktop refused to open while the
  same app was healthy behind the local TLS proxy. Classification now treats any
  3xx as "no document to shape-check" and lets `/api/updates` decide identity
  (API routes are never canonical-redirected); the asset probe runs only when
  there is HTML to inspect. Verified: `@@BE:ATTACH@@v0.3.2` against the live
  `npm start` server, and `/`, `/alerts`, `/terminal`, `/theses`, `/events`,
  `/app-view`, `/fabric`, `/figure` plus CSS/JS all return 200 through
  `https://blackeclipse`. Docs updated: `desktop/README.md`, `docs/CHANGELOG.md`.
- **feat(desktop): S0 + S1 — junk pruning and optional packs cut the core to
  819 MB.** Removed 114 MB of pure junk (harness tests 52 MB, site-package tests
  47 MB, `.dist-info` 6 MB, `node_modules/typescript` 9 MB) and moved the five
  lazily-imported heavypackages out of the core into separate packs: `ml`
  (xgboost/sklearn/scipy, 168 MB), `charts` (plotly/matplotlib, 53 MB),
  `documents` (pymupdf, 48 MB), `computer` (winsdk, 41 MB), `browser`
  (playwright, ~104 MB). `comtypes` stays in core because it is imported during
  the boot sweep. Core folder **1,258 → 731 MB**; with bundled Node and the shell,
  **1,345 → 819 MB**. Verified the core-only build serves `HTTP 200` with zero
  `ModuleNotFoundError`/`ImportError`. Added `scripts/desktop-packs.js`
  (`npm run desktop:packs`) to list/install/remove packs into a target app, and
  `scripts/desktop-bench.js` (`npm run desktop:bench`) which measured startup:
  window **1.4 s**, server answering **6.0 s** cold — the app's own boot, not the
  shell, holds the first response. The installer build now strips runtime state
  (`app/.black-eclipse`) before compressing, after a leftover lock file broke the
  NSIS build. Docs updated: `docs/desktop-size-plan.md` (§ S0/S1 results + speed
  baseline), `docs/CHANGELOG.md`.
- **docs(desktop): size-reduction plan — small download, optional packs.** Added
  `docs/desktop-size-plan.md`. Measured the installed copy (1,411 MB; installer
  268 MB; 5:1 compression) and found every heavy optional package is a **lazy
  import** (`# noqa: PLC0415`), so the harness already survives their absence —
  removing them is a packaging change, not a code change. Plan: prune ~115 MB of
  pure junk (harness tests 52, site-package tests 47, dist-info 7, `typescript` 9,
  caches); split the payload into a required **core** plus five optional packs
  (browser 105, ML 189, documents 48, computer-control 58, charts 54); ship a
  ~12 MB stub installer that fetches core (~130–150 MB) with resume + SHA-256 and
  lets onboarding choose packs, installable later from Settings › Components via
  `PYTHONPATH` — no reinstall. Tier 3 (hand-built minimal Python) explicitly
  rejected as too risky. Projected: 268 MB → ~12 MB download → ~140 MB core fetch
  → ~540 MB installed. Docs updated: `docs/desktop-size-plan.md`,
  `docs/CHANGELOG.md`.
- **fix(desktop): do not attach to a server whose build files are gone.**
  A leftover `next start` (its release directory had been deleted) still answered
  `/` with a full HTML document and still passed the identity probe at
  `v0.3.2`, so the shell attached to it. Every `/_next/static/*` request then
  failed with 400, leaving the window unstyled and non-interactive — the reported
  "the rest of the pages do not work" state. The bootstrap now fetches one of the
  JS chunks the served HTML references before trusting the server; failure is
  reported as a conflict with actionable text (stop the leftover Node process,
  then Retry), and the server is still never killed because the ownership rule is
  unchanged. Verified against the live broken listener (reported conflict) and
  the healthy payload (`@@BE:ATTACH@@`), then a fresh owned boot served `/`,
  `/alerts`, `/terminal` and its JS chunk with 200. Docs updated:
  `docs/desktop-app-plan.md` §3.2, `desktop/README.md`, `docs/CHANGELOG.md`.
- **fix(desktop): no sign-in screen, and a first run has a working database.**
  Two defects that only existed in the packaged build, both caused by the pruned
  `.env`. (1) `src/lib/auth/config.ts` treats a production build as public and
  **requires auth by default**, so the installed app opened on
  *"Create your operator account"*. The bootstrap now sets `HARNESS_AUTH=off`,
  matching what the repository's `.env` already declares — the desktop app is
  single-user and loopback-only, so there is nothing to sign in to. Verified:
  `/` serves the application (90,904 bytes) instead of the login page (38,375).
  (2) A first run created an **empty 4 KB database with no schema**, so every
  Prisma query failed with "table does not exist". The package now ships a
  schema-only seed (`app/seed/jdds.db`, generated from `prisma/schema.prisma` at
  package time — no binary committed) and the bootstrap copies it on first run.
  `CRON_SECRET` is likewise generated per install. Signing guidance removed from
  the docs: the project is free and unsigned by choice, with checksums plus
  `winget` as the distribution answer. Docs updated:
  `docs/desktop-app-plan.md` (§6, distribution), `desktop/README.md`,
  `docs/CHANGELOG.md`.
- **fix(desktop): identity check no longer depends on the update config, and the
  package ships no runtime state.** `/api/updates` reports
  `repository: "unknown"` when `config/updates.json` cannot be read (observed on
  the live server), which made a legitimate install attach as "unverified". The
  probe now also accepts the response's app-specific shape (`currentVersion` +
  `channel` + `ok`), so an unrelated config problem cannot masquerade as a
  foreign process. `desktop-package.js` also clears `app/.black-eclipse` before
  finishing — a local test run had written its log into the installer payload.
  Docs updated: `docs/CHANGELOG.md`.
- **test(desktop): the installer was installed, run, and uninstalled for real.**
  `BlackEclipse-Setup-0.3.2.exe` (259 MB from a 1,302 MB payload) installs
  silently in 43 s to `%LOCALAPPDATA%\Programs\BlackEclipse`, creates the Start
  Menu shortcut and Add/Remove entry, and the **installed** binary serves
  `HTTP 200`. Silent uninstall removes the program, shortcut and registry key
  while **preserving `%LOCALAPPDATA%\BlackEclipse\data`**. Checksum verified
  against `SHA256SUMS.txt` and matches the hash baked into the winget manifest.
  Running the installed copy exposed one more packaging gap: `@napi-rs/canvas`
  (a runtime `optionalDependency`) is not traced by Next, so PDF rendering
  silently degraded with `Cannot load "@napi-rs/canvas"` / `Cannot polyfill
  DOMMatrix`. `desktop-package.js` now copies `@napi-rs` and `@img` explicitly.
  Docs updated: `docs/desktop-app-plan.md` §13, `docs/CHANGELOG.md`.
- **feat(desktop): Windows installer, checksums, winget manifests and a release
  pipeline.** `desktop/installer/BlackEclipse.nsi` builds a **per-user** NSIS
  installer (no admin, no prerequisites) that keeps user data in
  `%LOCALAPPDATA%\BlackEclipse\data` and deliberately does not delete it on
  uninstall. Per-user is a correctness requirement, not a preference: the app
  resolves `python/harness` and its `.black-eclipse` locks from `process.cwd()`,
  so the install directory must be writable — Program Files is not.
  `scripts/desktop-installer.js` compiles it, writes `dist/SHA256SUMS.txt` and
  generates the three `winget` manifests with the real hash. Two Windows-specific
  fixes were required: NSIS cannot resolve paths over 260 characters, so the build
  goes through a short junction, and the payload now drops `__pycache__`
  directories (regenerable, the deepest paths, and 256 MB of the payload).
  `.github/workflows/desktop-release.yml` builds payload → shell → package →
  installer on a `v*` tag, asserts the payload carries no local configuration, and
  uploads a draft release. Also caught and fixed: `desktop-package.js` had a
  comment merged onto a `fs.mkdirSync` line, silently disabling the runtime
  directory. Docs updated: `desktop/README.md` (install layout, release chain,
  distribution, updating), `docs/desktop-app-plan.md` §10, `docs/CHANGELOG.md`.
- **fix(desktop): packaged app now generates its own harness secret instead of
  inheriting `.env`.** Pruning local config from the payload (correct) removed
  `HARNESS_AUTH_SECRET`, and the Python front door fails closed with
  `503 AUTH_MISCONFIGURED` in production — the packaged app booted and served
  nothing. `scripts/desktop-server.js` now creates a 64-char secret on first run
  at `<data dir>/harness-auth.secret` (mode 0600) and exports it to the child;
  repository checkouts keep `.env` authority. Also in this round, from real
  packaged-run evidence: the payload no longer carries `.env` / `mcp-servers.json`
  / source trees (with a build-time assertion that refuses to emit one),
  `.next` is renamed to the distDir baked into `server.js`, `BUILD_ID` is copied
  (Next omits it from standalone output), the traced server tree is overlaid with
  the authoritative one (`_not-found/page.js` was missing), readiness accepts the
  app's honest `503` warm-up gate while still failing on a real 5xx, and a
  non-canonical `BE_DESKTOP_PORT` now logs that notifications will not work
  (Tauri cannot wildcard the port in its IPC allowlist). Docs updated:
  `docs/desktop-app-plan.md` §6, `docs/CHANGELOG.md`.
- **fix(desktop): the payload build no longer rewrites `tsconfig.json`.** Next
  adds the new `distDir` (`.next-desktop/types`) to `include`, which would dirty a
  tracked file shared with every contributor. `scripts/desktop-payload.js` now
  snapshots `tsconfig.json` before the build and restores it byte-for-byte after.
  Also verified for open-source readiness: `node scripts/scan-secrets.js` clean
  over 5826 tracked files; `.env`, `.connector-key`, `mcp-servers.json` and
  `jdds.db` are untracked and `.env` has never been in history (only
  `.env.example`); the 1 GB vendored Python is gitignored; no GPL/AGPL in the
  Python core dependencies. Docs updated: `docs/CHANGELOG.md` (licence and
  distribution notes already live in `docs/desktop-app-plan.md` §6).
- **feat(desktop): zero-config defaults, and a free signing path for GitHub.** The
  shell now turns OS notifications **on** for a first run (the injected script
  writes `be_alerts_browser_v1=1` only when the key is absent, so an explicit OFF
  is respected; the app's own source and its browser opt-in are unchanged) —
  verified as `pref:1` in the probe. Added `npm run desktop:payload`
  (`scripts/desktop-payload.js`): builds a self-contained Next payload into
  `.next-desktop` with `output: "standalone"`, then copies `static` and `public`
  next to `server.js` and reports real sizes. The live server is never touched
  because the build uses its own `distDir`. `next.config.ts` gained one
  conditional line — `output` is only `standalone` when `BE_STANDALONE=1`, so the
  browser build is unchanged. Distribution/signing recorded in the plan: **no
  paid certificate** (the project is free on GitHub Releases), so the documented
  path is SignPath Foundation (free for OSS, apply early because approval takes
  time) plus the industry-standard mitigations while unsigned — per-asset SHA-256
  checksums, a `winget` manifest (strips the Mark-of-the-Web, so the installer
  usually runs without the SmartScreen wall), and an explicit README note. A
  self-signed certificate is recorded as **never ship**: an untrusted root adds
  its own warning. Docs updated: `docs/desktop-app-plan.md` (§6 distribution +
  signing, §19), `desktop/README.md`, `docs/CHANGELOG.md`.
- **fix(desktop): OS notifications now actually work — Tauri 2 denies app
  commands to remote origins.** The injected `Notification` shim called
  `invoke('desktop_notify')`, which fails with *"not allowed. Plugin not found"*
  because the window loads `http://127.0.0.1:3100`, a remote origin for the ACL.
  The shim had been silently no-oping inside a `try/catch`, so the app saw a
  `Notification` global that could never deliver. Two fixes: `remote.urls` added
  to `capabilities/default.json` (without it `window.__TAURI__` is absent
  entirely), and the transport moved from commands to **core events**
  (`be-notify`, `be-shortcut`), which a capability-listed remote origin *is*
  allowed to emit. `src/lib/alerts/browser-notifier.ts` is untouched. Added
  `npm run desktop:selftest` (`scripts/desktop-selftest.js`): a gated probe that
  reports through the webview URL rather than IPC, so a broken IPC cannot be
  mistaken for a working one. Result: `hn:1~perm:granted~sec:1~
  ctor:NativeNotification~shimcall:dispatched~direct:ok`, with two
  `[notify] sent` entries. The app-origin capability stays `core:default` only —
  no filesystem, no shell, no process control. Docs updated:
  `desktop/README.md`, `docs/desktop-app-plan.md` (§5, §12.15, §13),
  `docs/CHANGELOG.md`.
- **test(desktop): P1 acceptance evidence.** With a shell-owned server on port
  3111: `next start` reported `Local` **and** `Network` as `127.0.0.1` and
  `Get-NetTCPConnection` agreed; `Ready in 1068ms`; identity confirmed `v0.3.2`;
  killing the server produced `owned server exited after readiness` (failure
  panel path); the start lock was created and released; a second launch exited
  while one instance stayed; ports 3111/8766 were free after teardown, so the
  Python harness died with the tree. WebView2 probe reported `157.0.4341.42`.
  `npx tsc --noEmit` clean, `vitest` 507 files / 4676 tests passed. No doc change
  beyond the plan's measurement and acceptance tables.
- **feat(desktop): P1 hardening — the shell now meets the security and
  ownership requirements.** `scripts/desktop-server.js` rewritten: identity is
  verified before attaching (`/api/updates` reports `repository:
  black-eclipse/black-eclipse` + `currentVersion`, so no app route was added),
  the child is spawned as `next start -H 127.0.0.1` instead of the shared
  `startServer()` helper that binds every interface (**verified**
  `LocalAddress 127.0.0.1`; the previous build printed
  `Network: http://192.168.1.14:3111`), `BE_DATA_DIR` is resolved to an absolute
  path before any service starts and passed explicitly (the same variable
  `db.ts`, `persistence.py` and `eclipse_memory/config.py` read, so the single
  database is now constructed rather than incidental), `killPort` is gone — a
  live listener is never killed — a `desktop-server.lock` with pid + TTL
  serializes starts, and a non-BlackEclipse occupant produces a `CONFLICT`
  marker that explains itself instead of taking another port. A failed
  `db-guard` now writes `db-guard.failed` and the next launch refuses to serve
  with recovery instructions. Rust side: WebView2 registry probe before the
  window (message box with the download link *and* the browser fallback), an
  in-place failure panel when an owned server dies after readiness, `BE_DESKTOP_PORT`
  honoured by both halves, and the retry button resets the supervisor flag.
  **Bug fixed:** the log reader used `BufReader::lines().map_while(Result::ok)`,
  which silently ends the stream at the first invalid UTF-8 byte — the Python
  harness and Next can emit that on a Windows console, so a live server could be
  treated as gone. Now byte-wise with lossy conversion. Verified: attach as
  `v0.3.2`, conflict exit 5, loopback-only bind, `tsc` clean. Docs updated:
  `docs/desktop-app-plan.md` (§0, §5, §12, §15 resolved states, §18 decisions
  taken), `desktop/README.md`, `docs/CHANGELOG.md`.
- **docs(desktop): plan hardened; P0 snapshot rebuilt after a real defect.**
  Rewrote `docs/desktop-app-plan.md` around the locked architecture (Rust carries
  no domain logic, one child process, the existing Python supervisor is not
  wrapped) and integrated the normative requirements for process ownership,
  single `BE_DATA_DIR`, loopback security, runtime packaging, WebView2, crash
  behaviour, keep-warm, updates and scope, plus an 18-item acceptance checklist
  and a severity-ranked gap analysis. Grounded findings from source: `next start`
  binds **all** interfaces (the prototype's own test printed
  `Network: http://192.168.1.14:3111`), and `src/lib/db.ts` defaults the data
  directory to `process.cwd()` while `python/harness/persistence.py` defaults to
  its package-relative root — so the single database is incidental, not
  constructed. P0 snapshot rebuilt in `.black-eclipse/p0-snapshot/`: the original
  was `git diff` only (missing **14 untracked files of in-progress work**, incl.
  all of `python/harness/gaps/`) and was UTF-16 with a BOM, which `git apply`
  cannot read. Now: raw UTF-8 `--binary` patches (staged + unstaged + combined),
  `untracked.tar.gz` with 26/26 paths, `RESTORE.md`, `RESTORE-TEST.txt`; a
  round-trip restore into a clean clone reproduced every hash, and reverse-apply
  validates the patch against the live tree. Protected files
  (`start-eclipse.vbs`, `bin/black.js`, `scripts/local-host.js`,
  `scripts/start-desktop.js`) verified untouched. No commit, index unmodified.
  The prototype built earlier today is documented as **frozen pending
  authorization**; the earlier entry below referring to "§8 as built" is
  superseded by the renumbered document. Docs updated:
  `docs/desktop-app-plan.md`, `docs/CHANGELOG.md`.
- **feat(desktop): native Tauri shell around the existing app.** Added
  `desktop/` (Tauri 2 window, tray, keep-warm, window-bounds prefs, one-child
  lifecycle) and `scripts/desktop-server.js` (emits `@@BE:ATTACH/READY/ERROR@@`
  for the shell; attaches instead of starting a rival server, never builds at
  launch, and runs `db-guard` in the background behind a 12-hour
  `.black-eclipse/db-guard.stamp` because the synchronous guard costs >20 s on a
  338 MB `jdds.db`). The window loads `http://127.0.0.1:3100` — loopback is
  already a secure context, so the desktop boot skips the TLS reverse proxy and
  the `setup:tls` prerequisite entirely. WebView2 has no `Notification` API, so
  an init script maps the standard constructor onto a native toast. `db-guard`
  stays synchronous on the browser path (`npm start` → `prestart`). Additive:
  `start-eclipse.vbs`, `scripts/local-host.js`, `scripts/start-desktop.js` and
  `bin/black.js` are unchanged; rollback is deleting `desktop/` plus the five
  `desktop:*` script lines. Docs updated: `docs/desktop-app-plan.md` (§8 as
  built + measurements), `docs/NAVIGATION.md`, `desktop/README.md`,
  `docs/CHANGELOG.md`.
- **docs(desktop): native app plan.** Added `docs/desktop-app-plan.md`: the
  Tauri 2 shell architecture over the existing server, the loopback-origin
  decision (127.0.0.1 is already a secure context, so the TLS proxy is not part
  of the desktop boot), the speed lever table with measurable targets, the
  one-day work breakdown (P0 safety → P1 shell → P2 speed → P3 polish), the
  data-safety rules (one `BE_DATA_DIR`, additive-only, attach-if-running) and
  the risk register. Planning only — no code changed, browser path untouched.
  Docs updated: `docs/desktop-app-plan.md`, `docs/CHANGELOG.md`.
- **feat(bots): full chat parity with the Eclipse Agent.** Bot and group-member
  turns now forward the bot's own `agentId` (brain) and provider/model pin to the
  chat run instead of silently answering as `eclipse-agent`; an unpinned bot
  still defaults to the full agent, while a specialist preset now applies in
  chat exactly as it does on a schedule. The bot and group threads render
  `ApprovalCard` / `ClarificationCard` and decide through the existing approvals
  routes, so approval-gated tools and `clarify` questions can finish in Bots
  mode. Both composers attach documents to the same session folders the chat run
  reads (a group upload is mirrored into every member's session). Scheduled and
  manual agent runs now also set `analysisEnabled`, so the read-only computation
  sandbox is available off-schedule too. Caller-chosen models still win and drop
  the bot provider pin. Tests: `invoke.test.ts` (brain + pin forwarding),
  `state.test.ts` (`botModelPin`), `test_automation_engine.py` (analysis parity),
  full vitest (4676).
  `tsc` clean. Docs updated: `docs/bot-mode.md`, `docs/NAVIGATION.md`,
  `docs/harness/automation-engine.md`, `docs/CHANGELOG.md`.
- **feat(quant): closed the operational code gaps in the 10/10 foundation.**
  Live signals now refuse critical data findings; `risk_state.py` persists
  day-start/peak equity and auto-kills a trial on a daily-loss or drawdown
  breach; `live_scheduler.py` adds an idempotent `run-due` batch over active
  trials; `monitor_store.py` persists daily parity/drift/attribution snapshots;
  `model_card.py` renders the evidence record; `golden.py` repairs then freezes a
  content-hashed golden dataset. New routes cover golden freeze, monitor
  snapshots, model cards and the scheduler hook. Tests: 550 quant passes,
  QuantBench 51/51, `tsc`, evals and size pass. Docs updated:
  `docs/quant-system-blueprint.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(bots): durable conversations, manual runs for paused bots, and consistent model pins.**
  Bots mode now mirrors per-bot threads and group rooms to a durable `BotState`
  document in JDdS (`src/app/api/bots/state/[key]/route.ts`,
  `src/lib/bots/state-sync.ts`). localStorage remains the instant/offline copy;
  the newest client timestamp wins, and other tabs adopt changes through a
  `storage` listener, so clearing browser storage no longer erases
  conversations. "Run now" now works on a paused bot — pause stops the
  scheduler, not an explicit run (the operator run route opts into
  `allow_paused`; `engine.fire`/`_launch` honour it for manual triggers only,
  while webhook/agent-tool/event/condition/fabric paths still require
  `active`). The `agent.bot` graph node now applies a saved bot's
  provider/model pin (credentials and base URL still come from the graph run),
  matching its scheduled runs. Tests: `state-sync.test.ts`,
  `test_automation_engine.py`, `test_graph_agent_node.py`; `tsc` clean. Docs
  updated: `docs/bot-mode.md` (new), `docs/NAVIGATION.md`,
  `docs/harness/automation-engine.md`, `docs/graph-studio.md`,
  `docs/graph-studio-bot-skill-nodes-plan.md`, `docs/CHANGELOG.md`.
- **feat(quant): closed the remaining code gaps in the 10/10 foundation.**
  The backtest route now refuses critical data findings unless
  `allowDirtyData` is explicit; `data-quality/repair` drops exact duplicates and
  counts conflicts without filling gaps. Added a durable `QuantOrder` OMS store
  (restart-safe, unique idempotency key), enforced stop/target on live-trial
  orders (the risk engine now requires a stop), a `run-due` scheduler hook,
  broker cost calibration from fills (`slippageBps`, commission per lot and
  explicit backtest assumptions), and a trial report route (runs, broker
  account, positions, orders, P&L). The health panel now reports data, broker,
  risk, runner and lifecycle. Tests: `test_quant_system_core.py` (14),
  `test_quant_live.py` (5), routes; QuantBench 51/51; `tsc` and size pass.
  Docs updated: `docs/quant-system-blueprint.md`, `docs/quant-engine.md`,
  `docs/CHANGELOG.md`.
- **feat(quant): shipped the 10/10 foundation across all 12 workstreams.**
  Added `quant/data_quality.py` (duplicate/conflict detection, gap
  classification, broker parity, content hash, blocking gate),
  `quant/lifecycle.py` (evidence-gated model state machine),
  `quant/risk_engine.py` (per-trade sizing, lot/notional/margin/spread/exposure
  checks, daily-loss and drawdown kill), `quant/oms.py` (idempotency, legal
  state machine, brackets, partial fills, reconciliation, TCA),
  `quant/live_runner.py` (one claim per strategy/version/timeframe/bar,
  restart-safe, pause/resume), `quant/monitor.py` (signal parity, drift,
  attribution), `quant/capital.py` (risk-budget allocation with caps) and
  `quant/system_health.py` (one operator view). The live trial now claims a run
  key, runs the risk engine before submit and records OMS state. Added
  `routers/quant_system.py` (data quality, parity, lifecycle, risk, allocation,
  runs, health) and the Strategy Studio `system-health-panel.tsx`. Tests:
  `test_quant_system_core.py` (11) + live (5) + routes; `tsc` clean; size
  re-pinned deliberately. Docs updated: `docs/quant-system-blueprint.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **docs(quant): added the Quant System Blueprint** (`docs/quant-system-blueprint.md`).
  It defines a measurable 10/10 target (data truth, research rigor, model
  lifecycle, broker-calibrated backtests, a hard risk engine, an idempotent OMS,
  bar-close automation, drift monitoring, portfolio allocation, governance and
  operator UX), 12 workstreams with exit criteria, a 13-week build plus 90-day
  evidence track, strategy promotion thresholds and a first-10-days checklist.
  Plan only; no runtime code changed. Docs updated:
  `docs/quant-system-blueprint.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(quant): added governed live strategy trials.** New `quant/live.py` +
  `routers/quant_live.py` promote an approved, backtested strategy version to a
  live broker trial. Gates: approved review, completed backtest, typed phrase,
  live connection, future arm and a positive maxMargin. The trial creates a live
  mandate pinned to `strategy:<id>:<version>`, evaluates the strategy on the last
  closed bar with the same causal engine, submits ONE order under the mandate,
  refuses to stack a position, closes on an exit signal, reads broker results
  (account/positions/orders/open P&L) and stops by revoking the mandate. The
  existing broker layer, money guardrails, reconciliation and kill switch are
  reused; no second order path. Strategy Studio gained a live-trial panel.
  Tests: `test_quant_live.py` (5) + route registration; docs
  `docs/quant-live-strategy.md`, `docs/quant-engine.md`, `docs/NAVIGATION.md`.
- **feat(quant): widened Quant Research Intelligence to a horizon-wide, visual
  research system.** The method catalog grew from 17 to 33 methods across
  intraday, swing, position and long-term horizons (ARIMA, VECM, Kalman, carry,
  crypto funding, low-vol, seasonality, options income, volatility breakout,
  event drift, risk parity, Black-Litterman, value, quality, long-term trend,
  equal weight), and it is explicitly open: literature extraction and
  `quant_register_method` add methods at runtime. Added
  `quant_attach_implementation` so any method can receive a tested Python
  implementation; open-access PDF links and citation pointers are stored, and
  the generic worker uses Docker when configured.
  Added `research_method_matrix` (coverage by horizon) and `research_visualize`
  (method coverage, suitability, price, rolling volatility, return distribution,
  reproduction fit) with computed chart blocks. Reproduction grew to 12 built-in
  estimators (GJR-GARCH, EGARCH, HAR-RV, Engle-Granger, HMM, EVT/GPD, CAPM/FF,
  Almgren-Chriss) plus a generic registered-code path that runs in a separate
  process with a scrubbed environment, timeout and output cap. Extraction now
  accepts an optional model proposal only when each field's quote exists
  verbatim in the document. Academic search now merges OpenAlex, Semantic
  Scholar, Crossref and arXiv; SSRN/NBER/RePEc are scoped pointers. Added the
  Research Intelligence panel to Strategy Studio, an open-method matrix view,
  computed figures, and a figures section in the dossier. Tests:
  `test_quant_research_intel.py` (26), routes (5), connectors (11), QuantBench
  47/47; `tsc` clean; size budget re-pinned deliberately. Docs updated:
  `docs/quant-research-intelligence-plan.md`, `docs/quant-engine.md`,
  `docs/quant-research-prompts.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(quant): shipped Quant Research Intelligence.** New
  `python/harness/quant/research_intel/` adds a formal method-spec contract with
  sourced equations, a 17-method seeded knowledge base, deterministic research
  query planning, scholarly search over the EXISTING OpenAlex/Crossref/arXiv
  connectors with DOI/arXiv/title dedupe, section/equation extraction with page
  provenance, explained suitability scoring, a reproduction harness separated
  from trading adaptation (OU/AR(1), EWMA, realized variance, GARCH(1,1)), a
  validation matrix, and a Quant Research Dossier registered in the Artifact
  Center. 14 agent tools (`research_*` + `quant_*_method`/dossier) are added to
  `QUANT_TOOLS`; `routers/quant_research.py` exposes the operator-gated routes;
  `quant/bootstrap.py` seeds the catalog; `model_catalog` gained `method` and
  `dossier` kinds. Reproduction is honest: an unregistered implementation
  returns `inconclusive`, and a validated lifecycle requires a passing
  validation record. New intent kinds: literature_review, method_comparison,
  method_reproduction, research_discovery, quant_model_development,
  research_extension. Tests: `test_quant_research_intel.py`,
  `test_quant_research_intent.py`, `test_quant_research_routes.py` + four
  QuantBench cases (routing and math); registry regenerated; size budget
  re-pinned deliberately. Added reusable research prompts
  (`docs/quant-research-prompts.md`) and a "Quant research" block in the base
  system prompt. Docs updated:
  `docs/quant-research-intelligence-plan.md`, `docs/quant-engine.md`,
  `docs/quant-research-prompts.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **docs(quant): added the Quant Research Intelligence implementation
  specification** (`docs/quant-research-intelligence-plan.md`). It defines the
  research-to-model evolution on top of the existing engine — scholarly search,
  paper/method extraction with page provenance, a method knowledge base,
  reproduction separated from trading adaptation, validation and a research
  dossier — with mandatory repository-inspection steps, a reuse map, proposed
  module responsibilities, tool/route contracts, additive `agent-memory.db`
  schema, phased acceptance tests and explicit no-rebuild guardrails. Plan only;
  no runtime code changed. Docs updated:
  `docs/quant-research-intelligence-plan.md`, `docs/CHANGELOG.md`.
- **feat(quant): method discovery, realism, portfolio risk and a measurable
  benchmark.** Quant mode now centres on finding, adapting and inventing
  tradable methods. New `quant/discovery/` (14-family taxonomy with thesis/edge
  source/failure modes; method cards; deterministic fit recommendations;
  market-structure diagnostics; falsifiable hypotheses; method→spec synthesis and
  two-method composition; bounded IS/OOS mining with the real trial count and
  Deflated Sharpe) plus `quant/discovery_tools.py` and the `/quant/methods/*`,
  `/quant/discovered-methods/*` routes and persisted `QuantMethod` rows. Quant
  intent now recognises discovery turns and the per-turn protocol drives
  library → scan → hypothesis → synthesize/mine → validate. Realism added:
  borrow/locate fees, financing, maintenance margin + liquidation, participation
  partial fills, corporate actions (all opt-in and zero by default), plus
  `quant/manifest.py` run manifests and `reproduce_experiment`. Portfolio layer:
  `risk_model.py` (sample/EWMA/Ledoit-Wolf covariance, Euler risk contributions,
  factor exposures), `portfolio_optimizer.py` (MV/min-var/max-Sharpe/risk
  parity/HRP/Black-Litterman + constraints), `scenario.py` (VaR/ES, historical,
  scenarios, reverse stress). Derivatives: `options_backtest.py` (dated
  chain-marked multi-leg backtest) and futures term-structure/roll-cost helpers.
  Research sessions + hypothesis/trial ledger, HTML/notebook export, QuantBench
  (`python -m harness.quant_bench`), and new Strategy Studio panels (method
  discovery, research journal, portfolio stress) + shared manifest panel.
  Trading playbook (`quant/playbook.py`, `generate_trading_playbook`) renders
  the actual spec into entry/exit/sizing/risk/execution/invalidation/monitoring
  instructions with the paper-first rule. Added `scan_universe_setups` +
  `/quant/methods/universe-setups` and a "Scan watchlist" action so a user can
  find which validated methods have an entry condition across several symbols
  now (bounded to 12; per-symbol failures are reported, never hidden). Added
  `mine_universe_methods` + `/quant/methods/mine-universe`: the same bounded
  mining across up to 5 symbols, aggregated per method family with support and
  mean OOS Sharpe, so a one-symbol fluke is visible instead of averaged away. Fixed the `sources` screen's stale
  `lucide-react` import (now the repo icon set) so `tsc` is clean.
  Tests: `test_quant_realism.py`, `test_quant_discovery.py`,
  `test_quant_portfolio.py`, `test_quant_desk.py`; `tsc` clean. Added
  `npm run test:quant-bench` (`scripts/quant-bench.js`), wired into
  `.github/workflows/ci.yml`, so the scorecard is a real CI gate. Regenerated
  `docs/harness/tool-registry.json` for the new tool surface and re-pinned
  `scripts/size-budget.json` for the measured discovery subsystem. Docs updated:
  `docs/quant-engine.md`, `docs/strategy-studio.md`,
  `docs/quant-method-discovery.md` (new), `docs/NAVIGATION.md`,
  `docs/DECISIONS.md` (ADR-078), `skills/ARCHITECT.md` (ADR-078),
  `docs/CHANGELOG.md`.
- **perf(chat): make send instant on Enter.** `saveConversations` wrote the
  entire transcript list to `localStorage` synchronously inside the send
  handler, so the new bubble could not paint until a full `JSON.stringify` +
  `setItem` finished (the cost grows with every saved chat). The in-memory store
  still updates immediately; the cache write is now coalesced and deferred
  400 ms, with an early flush on `pagehide`/`visibilitychange`. no doc change —
  bug fix; the storage contract is unchanged.

- **feat(quant): quant mode is figure-first.** Added the deterministic Quant
  Figure Kit (`python/harness/quant/visuals.py`) that builds equity, underwater,
  monthly returns, exposure, trade distribution/scatter, rolling risk, cost
  waterfall, Monte-Carlo, regime attribution, walk-forward and a 3D parameter
  surface from stored artifacts. Added the `render_quant_figures` tool
  (`quant/visual_tools.py`) and
  `GET /quant/experiments/{id}/figures[/{figure}]`; a chart block may now name
  `quant: {experimentId, figure}` and the browser resolves the computed spec, so
  a long series never travels through the model. The quant protocol now carries
  a visual contract and figure budget, `evaluate_quant_outcome` reports a missing
  figure after a series-producing run, response mode is upgraded to
  `visualization`, 3D panels get real matplotlib axes for the PNG copy, and the
  Backtest bench reuses the same kit through `QuantFigurePanel`. Docs updated:
  `docs/quant-engine.md`, `docs/chart-engine.md`,
  `docs/interactive-response-engine.md`, `docs/NAVIGATION.md`,
  `docs/DECISIONS.md` (ADR-076), `skills/ARCHITECT.md`, `docs/CHANGELOG.md`.

- **feat(sources): open, search and query folders/drives of any size in place.**
  New `python/harness/sources/` layer: a dedicated SQLite catalog
  (`.black-eclipse/sources/sources.db`) with an incremental, batched, resumable
  scanner that stats files without opening them; a bounded probe that reads at
  most 4 KB head + 1 KB tail and returns a *card* (magic/format, schema, page
  count, image size, archive entries, preview) whatever the file size; windowed
  byte/line reads; a streaming text extractor with content-defined chunks and
  FTS5; read-only DuckDB over CSV/TSV/JSONL/Parquet bound as view `t` with a
  statement allowlist, memory limit and spill directory; and a query router that
  derives candidates from the catalog and chooses metadata / FTS / DuckDB /
  bounded parallel scan, with time, byte, result and cancellation budgets plus
  honest partial reporting. Adaptive background indexing makes the second query
  fast; optional semantic reranking (`HARNESS_SOURCES_SEMANTIC=1`) embeds chunks
  through the existing `search.embeddings.EmbeddingService` and scores a bounded
  candidate subset, never the whole corpus. Agent tools `source_roots/list/open/
  read/lines/search/sql/index/stats` (read-only; adding a root is operator-only)
  register on the ONE registry and are advertised on the Eclipse and Code agents;
  routes live in `python/harness/routers/sources.py` and are proxied by
  `/api/sources/*`, with a new Sources tab (roots, scan progress, routed search,
  bounded preview, SQL runner). Tests: `python/tests/test_sources_core.py`,
  `test_sources_query_tools.py`. Docs updated: `docs/harness/large-sources.md`
  (new), `docs/NAVIGATION.md`, `docs/DECISIONS.md` (ADR-077),
  `skills/ARCHITECT.md`, `docs/CHANGELOG.md`. `no doc change` — n/a.
- **fix(capabilities): a "bot" request can no longer dead-end in the code
  builder.** `capability_request` had no automation vocabulary, so "turn this
  into a skill and then a bot" classified only the skill (or fell through to
  `scaffold_kit`), and a chat/code turn without `code.write` then answered
  `PROFILE_DENIED` — which reads as "Eclipse won't let me". Added `detect_kinds`
  (ordered, multi-deliverable), a `bot` kind → `bot_create` in the surface/next-tool
  maps, and a `_bot` hand-off whose notes explicitly forbid `scaffold_kit` and
  name the cron + IANA timezone as required input. `CODE_AGENT_TOOLS` now carries
  the Automation tools so a code task can create the same bot; `bot_create`
  refuses a cron/interval trigger with a plain-language reason instead of an
  exception. Hand-off responses now say "call the tool NOW in this turn" rather
  than "nothing was activated"; `scaffold_kit`'s `PROFILE_DENIED` /
  `WORKSPACE_UNBOUND` refusals name `skill_create` / `bot_create` / a code task.
  The verifier's `output-contract` failure now says which output had the wrong
  kind and what it got, so one build fixes it; a verifier crash is recorded as a
  failed version instead of leaving orphan draft files with no record. Tests:
  added bot/multi-deliverable routing, hand-off, tool-text and scaffold-refusal
  cases; `test_code_agent`, `test_automation_tools`; isolated the dynamic recipe
  registry in `test_capabilities_builder` and made the public-manifest drift gate
  generate in a clean subprocess (it was order-dependent). Docs updated:
  `docs/harness/capability-builder.md`, `docs/CHANGELOG.md`.
- **feat(runtime): no dead ends — every offerable block becomes a durable gap
  and a user offer.** Added `python/harness/gaps/` (`taxonomy.py` = 8 classes,
  only capability/context/setup are offerable; `store.py` = durable
  `CapabilityGap` on `agent-memory.db` with stable signatures, suppression and
  resolution; `service.py` = the one-route offer + accept/decline/suppress;
  `runtime.py` = the fail-open graph glue). `graph.py` records refused tool
  payloads (a handler refusal is `ok=True` with `status:refused`), closes a gap
  on a later success, catches one narrow prose-only refusal, and at the answer
  seam emits `capability.offer` plus one visible sentence. `run_outcome` reads
  the offer into `capabilityGap`. Operator API `/capabilities/gaps*` (accept also
  asks the existing parked-task resume path); chat card wired through
  `events.ts` → `capability-card.tsx` → `chat-history.tsx` with
  `actionPrompt`/`actionLabel`; Capability Studio queue `gaps-section.tsx`;
  prompt rule "never end with a bare refusal"; safety denials never offer a
  bypass. Tests: `test_capability_gaps.py`, `test_no_dead_ends.py`,
  gaps API + event/card cases. Docs: `docs/harness/no-dead-ends.md` (new),
  `docs/harness/capability-builder.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.

- **feat(investor-eye): retire the glowing surface; the simple black map is the
  only skin.** Removed the BLACK/GLOW skin switch from the map view controls and
  the `mapSkin` state from the store, saved views and localStorage persistence.
  The simple terminal surface is now the default everywhere (full screen,
  full-page map, dashboard widget); the MAP/GLOBE projection switch and the
  stars/name toggles are unchanged. `map-echarts.ts` keeps the `glow` variant as
  an internal, non-UI option and now defaults `skin` to `black`; the globe loads
  only the black/light texture and no glow/bloom pass. `map-echarts.test.ts`
  asserts the new default. Docs updated: `docs/investor-eye-architecture.md`
  (§5n), `docs/CHANGELOG.md`.

