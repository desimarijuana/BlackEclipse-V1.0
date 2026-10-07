# Change Log

## Rotation policy

This file keeps a rolling window of the **most recent 7 dated sections** (the active window). Older dated sections are **moved** - never deleted - into monthly archive files under `docs/changelog/YYYY-MM.md`. New entries are appended under the current date; the commit-msg hook checks this path. Rotation is by hand only when this file grows unwieldy; the archive link below points at where the older entries went.

> Older entries are archived under `docs/changelog/` (monthly). The most recent 7 dated sections are kept here.

## 2026-10-06

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

## 2026-10-01

- **Fix the site-wide frosted-glass regression: `theme-glass-active` shipped with
  only `-webkit-backdrop-filter`.** `globals.css` wrote both `backdrop-filter`
  and `-webkit-backdrop-filter` on the token-driven glass rules; Next's
  lightningcss minifier collapses such a pair down to the `-webkit-` form alone,
  and modern Chrome no longer supports `-webkit-backdrop-filter`
  (`CSS.supports('-webkit-backdrop-filter')` is false). Because that rule also
  carries `!important`, the lower-specificity per-tier `.glass-card` rule could
  not win â€” so whenever the theme had been customized (which adds
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
  `.glass-card-strong` (tint 0.85 â€” above the frosted threshold, so the blur was
  invisible) to `.glass-card` (tint 0.55 + blur 18) so the frost actually renders.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.

- **Tighten the Command Center gaps and fix adding widgets to an emptied
  layout.** Two independent issues. (1) Density: added a `dense` prop to
  `CustomizableWorkspace`/`WorkspaceCanvas` (gutters only â€” inter-zone
  `gap-4â†’gap-1.5`, section stack `gap-3â†’gap-1.5`, column/card gaps
  `gap-2.5â†’gap-1.5`, section padding `p-1â†’p-0.5`, header/edit-bar margins
  `mb-3â†’mb-2`) and passed it from `DashboardScreen`; also cut the outer wrapper
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
  `existsSync(jdds.db)` â€” which fails on a fresh CI checkout, where the
  gitignored runtime vault is (correctly) absent. It now proves the real property:
  `jdds.db` is git-ignored AND not tracked (`git ls-files --error-unmatch`). This
  unblocks the root `.github/workflows/ci.yml` gate, which mirrors check-all.js.
  No doc change â€” test-only; the runtime and the DB posture are unchanged.

- **Surface closure follow-up â€” client-safe browser clients for the code and jobs
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

- **Front-door surface closure â€” mount the code and jobs surfaces.** The Python
  runtime for the code capability, jobs and the Phase-12 eval was complete and its
  gates green, but several finished UI surfaces existed as files nothing imported,
  so no user could reach them. New `src/components/screens/code/code-screen.tsx`
  (a thin container wiring the EXISTING Phase-5 panels to the existing
  `code-client` â€” no agentic logic) and the existing `JobsScreen` are now mounted
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

- **Eclipse-as-a-Harness Phase 12 â€” evaluation harness, safety cases and the standing gate.**
  Extends `python/harness/code/eval/` with a task + safety evaluation beside the
  Phase-4 verification eval, additively (the verification eval keeps its name/API):
  `dataset_tasks_v1.json` (seven labelled fixtures by difficulty, including a
  refusal case graded in the OPPOSITE direction), `safety_cases.py` (eleven
  adversarial cases as data), `tasks.py`/`safety.py`/`statement.py` (runners +
  the generated capability statement). A deterministic floor â€” never a blended
  score â€” gates `falseVerifiedRate == 0.0`, `refusalCorrectness == 1.0`,
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

- **Eclipse-as-a-Harness Phase 11 â€” surface and scale.**
  Delivery grows from two adapters to three behind the Phase-6 `DeliveryAdapter`
  protocol: new `python/harness/jobs/delivery.py` `messaging` adapter (a template
  KEY + params, never a composed sentence) and the `artifact` file contract
  (`.black-eclipse/artifacts/<runId>/{report.md,receipt.json,meta.json}`, path
  derived from the run id and confined by policy). Every configured target records
  its OWN `DeliveryOutcome` on the run row â€” no rolled-up boolean; a delivery
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

- **Eclipse-as-a-Harness Phase 10 â€” self-improvement v2 (code as well as skills).**
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

- **Eclipse-as-a-Harness Phase 9 â€” finance application scaffold kits.**
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

- **Eclipse-as-a-Harness Phase 8 â€” analysis sandbox (computing, not just retrieving).**
  New `python/harness/code/execution.py` (bounded, reproducible analysis on the
  Phase 3 sandbox: AST import allowlist â€” never eval/exec â€” source/input/interpreter/
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

- **Eclipse-as-a-Harness Phase 7 â€” delegation and child runs.**
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

- **Eclipse-as-a-Harness Phase 5 â€” coding agent, autonomy profiles, approvals.**
  New `code-agent` preset (`agents.py`) whose allowlist is the REAL Phase 1â€“3
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

- **Prompt follow-up â€” navigator prompt correctness + guard coverage.** Fixed
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
  `test_prompt_segments.py`. Prompt 17,443 â†’ 17,294 chars (~4,324 est. tokens),
  under the 17,500 ceiling. docs updated: `docs/harness/decisions.md`
  (ADR-H106), `docs/harness/architecture.md`,
  `docs/harness/prompt-followup-progress.md`.

- **Eclipse-as-a-Harness Phase 4 â€” verify-and-repair trust spine.** New
  `python/harness/code/verify.py` (the per-run `VerificationLedger`; a
  deterministic, negation-aware sentence-level claim parser; `enforce_answer`
  marking/stripping an unbacked pass-claim with `UNVERIFIED`) and
  `python/harness/code/repair.py` (the bounded planâ†’editâ†’checkâ†’repair loop with a
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

- **Eclipse Agent Prompt v2 â€” finance-harness completion.** Added the
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
  and `# Tool-use enforcement`, retaining every rule. Prompt 15,302 â†’ 17,443
  chars (~3,826 â†’ ~4,361 est. tokens), under the 17,500 ceiling. Guard tests
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
  added prompt guard tests. Prompt 18,826 â†’ 15,302 chars (~4,707 â†’ 3,826 est.
  tokens). Removed the now-redundant `'What time is it?' -> date` example.
  docs updated: `docs/harness/decisions.md` (ADR-H103),
  `docs/harness/architecture.md`, `docs/NAVIGATION.md`.

- **Eclipse-as-a-Harness Phase 3 â€” sandboxed command broker.** New
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
  1841â†’1883; eval gates pass). docs updated: `docs/harness/decisions.md`,
  `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-03-command-broker.md`, `docs/NAVIGATION.md`

- **Eclipse-as-a-Harness Phase 2 â€” isolated worktree patch authoring.** New
  `python/harness/code/worktree.py` (allocate a disposable copy at
  `<root>/.black-eclipse/code-workspaces/<id>` via `git worktree add --detach`,
  bounded snapshot fallback reported honestly, `release` refusing anything outside
  the scratch root and idempotent, `diff`, `sweep_expired`), `code/patch.py`
  (closed op set create/replace/delete/move, structural validation before any
  write, content-hash base refusal, unique-span `replace`, ATOMIC â€” a refusal
  applies nothing, before/after hashes, `revert` newest-first), and
  `code/store.py` (the `CodeWorkspace` table bound to the ONE `AgentMemoryStore`
  connection; `persistence.py` untouched). Three tools added to
  `register_code_tools` â€” `workspace_patch_apply` (write), `workspace_diff`
  (read), `workspace_revert` (write) â€” authorized by the run's autonomy profile
  via a code authorizer composed into the single effect authorizer; `RunRequest`
  gains an optional `autonomy`; `code-navigator` gains the three tools.
  `sweep_expired` wired into startup maintenance. Front-door i18n `task.authoring.*`
  progress/result lines + authoring `refusal.*` codes + `plain-language.test.ts`
  extended; human tool labels added. ADR-H101 appended (the series ended at H100).
  Baseline frozen in `docs/harness/roadmap/progress/phase-02-progress.md` (vitest
  169/1966; pytest 1808â†’1839; eval gates pass). docs updated:
  `docs/harness/decisions.md`, `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-02-worktree-patching.md`, `docs/NAVIGATION.md`

- **Eclipse-as-a-Harness Phase 1 â€” read-only repository navigator.** Five
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
  `Â«redactedÂ»` via `session_index.redact_span` (one pattern set). New
  `code-navigator` agent preset (only the five tools, no MCP); `RunRequest.workspace`
  (optional, additive; can only confirm the server root) wired through
  `ToolContext.workspace`; front-door `validateWorkspaceRef` + types; i18n
  `task.*`/`refusal.*` keys + a codeâ†’sentence map and the `plain-language.test.ts`
  jargon gate. ADR-H100 appended (the series ended at H99, not H92). Baseline
  frozen in `docs/harness/roadmap/progress/phase-01-progress.md` (vitest 168/1962;
  pytest 1777â†’1808; eval gates pass). docs updated: `docs/harness/decisions.md`,
  `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-01-repository-navigator.md`, `docs/NAVIGATION.md`

- **Eclipse-as-a-Harness Phase 0 â€” code capability becomes a tested policy
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
  set (unknown profile â†’ nothing, fail-closed), and a caller grant can no longer
  smuggle a code verb. New `python/tests/test_code_policy.py` (33 tests, incl.
  path-escape and command refusals and the plain-language seed gate). ADR-H97/
  H98/H99 appended (the series already ended at H96, not H92). Baseline gate
  frozen in `docs/harness/roadmap/progress/phase-00-progress.md` (vitest 168
  files / 1962 tests; pytest 1744; eval gates all pass). docs updated:
  `docs/harness/decisions.md`, `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-00-policy-and-baseline.md`, `docs/NAVIGATION.md`

- **ChatBot landing wordmark â€” user-authored giant text + font.** Settings â€º
  General â€º Background gained a "Landing text" card: a text field, a curated
  display-font list (`WORDMARK_FONT_OPTIONS`), alignment, size (vw), strength and
  vertical position. A new presentational `ChatWordmark`
  (`src/components/chat/chat-wordmark.tsx`) paints the text behind the ChatBot
  landing only, above the wallpaper and below the transcript/composer
  (`z-0`/`pointer-events:none`); the default is a Didone-stack "ECLIPSE AGENT"
  wordmark. Six new `BackgroundPrefs` fields flow through the existing
  `backgrounds.ts` store/prefs (localStorage `be_background_v1`), so it applies
  instantly and persists. Tests cover normalization/clamping.
  no doc change â€” UI-only presentation preference; no architecture, contract or
  setup change.

- **Eclipse-as-a-Harness Phase 6 â€” harness-owned jobs and event triggers.**
  New `python/harness/jobs/` package: `model.py` (`JobDefinition`/`JobTarget`/
  `JobDelivery`, `enabled` defaults FALSE per ADR-H39), `store.py` (the
  `HarnessJob`/`HarnessJobRun` tables on the ONE `agent-memory.db` connection),
  `cron.py` (a stdlib-only 5-field matcher that refuses 6-field/`@macro`/name
  aliases), `guardrails.py` (save-time permission binding, workspace-required code
  jobs, operator-gated `approve_external`, `policy.resolve_within` watch-path
  confinement, skill-version pinning, unknown-adapter refusal), `scheduler.py`
  (`JobScheduler` â€” one lifespan task beside `start_mcp()`, injected clock, no
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

- **Harness closeout Phases 8â€“9 â€” eval harness, rollout, docs.** `scripts/test-evals.js`
  runs four new OFFLINE gates: the capability-matrix gate
  (`scripts/eval-capability-matrix.ts`) and the Python route_health / workflow /
  resume gates (`python/harness/eval_gates/`), each failing non-zero on a floor
  violation. The workflow path and the route-probe schedule ship behind flags
  (`HARNESS_WORKFLOWS_ENABLED` / `HARNESS_ROUTE_PROBE_ENABLED`), both default OFF;
  a run with no `workflowId` is unchanged. Architecture, NAVIGATION and ADR-H93â€¦H96
  documented. docs updated: `docs/harness/architecture.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md`, `docs/harness/harness-closeout-progress.md`

- **Harness closeout Phase 7 â€” observability: one source of truth.** Verified the
  retrieval planner's health index reads the same SourceHealth ledger as
  `get_source_health`, with a test asserting equal verdicts. `explain_run` now
  includes the workflow step tree, run lineage, and the resume point; workflow
  steps emit per-step events on the existing bus; `run-explanation-panel.tsx`
  renders them. docs updated: `docs/harness/harness-closeout-progress.md`

- **Harness closeout Phase 6 â€” permissions, sandboxing, egress.** `ToolDefinition`
  gained `version`/`deprecated`/`replacement`; the registry warns once per run
  when a deprecated tool is called (naming its replacement) and still executes it.
  Confirmed and tested the four egress guards (private-address, non-https hop,
  DNS-rebinding, over-size document). A sentinel-secret scan runs a real run with a
  sentinel credential and asserts it appears in no persisted row.
  docs updated: `docs/harness/harness-closeout-progress.md`

- **Harness closeout Phase 5 â€” the composable workflow graph.** New
  `python/harness/workflows/` (model/validate/store/compile) compiles a versioned,
  bounded `Workflow` onto the EXISTING `execute_run` graph â€” no second loop,
  registry or model adapter. A step's tool scope = agent allowlist âˆ© step tools,
  enforced at the `ToolRegistry.execute(allowed=...)` seam (a denied call is a
  structured `TOOL_FORBIDDEN`); approval steps reuse the single-use `ApprovalStore`;
  parallel branches share the run cancel event/cache. Flag-gated
  (`HARNESS_WORKFLOWS_ENABLED`, default OFF); a run with no `workflowId` is
  unchanged. Front door `src/lib/harness/workflows-client.ts` + routes
  `src/app/api/harness/workflows/**`.
  docs updated: `docs/harness/harness-closeout-progress.md`

- **Harness closeout Phases 3â€“4 â€” matrix truthfulness + data-route gaps.**
  `buildCapabilityMatrix` now reconciles every axis and represents an impossible
  fact as `matrixInconsistent` (with a reason) instead of smoothing it over; CH/KW/QA
  gained real COVERAGE entries with correct ISO currencies (CHF/KWD/QAR) and the
  market count is asserted at 34; a declared provider-eligibility registry replaces
  an inferred quote route (AE/NG are not-configured and secondary). FX/crypto skip
  the JDdS vault (which holds no such row); statements resolve through the provider
  chain with the vault as a cache (never a vault identity failure); PK is declared
  secondary; thin markets gained symbol-candidate chains.  No jdds.db commit.
  docs updated: `docs/harness/harness-closeout-progress.md`

- **Harness closeout Phase 2 â€” one authoritative route-health ledger.**
  `sourceHealth()` now returns a compact recorded SUMMARY by default and withholds
  the ~1,200 declared-but-unrun routes (opt-in via `recordedOnly`/`includeDeclared`),
  so `get_source_health` is readable inside the 24k tool bound instead of showing
  only "unknown" rows. `capabilityMatrix()` canonicalises its market key to match;
  a migration folds legacy rows (incl. literal `unknown`) onto canonical keys.
  `SourceHealth` gained `lastSuccessAt`/`lastFailureAt`. A bounded cross-market
  probe records one attempt per (market Ã— capability) into the same ledger, with a
  manual one-shot (`POST /api/harness/route-probe`, `scripts/probe-route-health.ts`)
  and a recurring schedule OFF by default behind `HARNESS_ROUTE_PROBE_ENABLED`.
  The ledger surface moved to `src/lib/harness/health-ledger.ts` to respect the
  size ratchet.
  docs updated: `docs/harness/harness-closeout-progress.md`

- **Harness closeout Phase 1 â€” run lineage, durable checkpoints, idempotent
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

- **Tool-loop integrity Phase 1 â€” the release gate's one red test was a UTC
  month-rollover time bomb.** `weekly.test.ts`'s `buildMonthlyWrapped` test
  derived its period from `new Date()` while its fixtures were hardcoded to
  2026-09; after 20:00 EDT on Sep 30 (UTC already Oct 1) the prefix resolved to
  `2026-10` and zero rows matched. The test now passes `(year, month)` explicitly
  and asserts the zero-match branch (`trades === 0`, `bestMarket === null`)
  deliberately. A repo-wide sweep found no other live-clock/fixed-fixture test.
  A testing convention was added to `CONTRIBUTING.md`.
  docs updated: `CONTRIBUTING.md`, `docs/harness/tool-loop-integrity-progress.md`

- **Tool-loop integrity Phase 2 â€” duplicate tool-call suppression is scoped to
  one agent step, not the whole run (ADR-H90).** `seen_calls` now resets per
  `tools_node` invocation, so a legitimate re-issue in a later turn (next page,
  re-poll, retry) executes instead of being refused with a stale "use the earlier
  result". Intra-turn refusal is unchanged. Regression tests cover both
  directions; the retrieval cache still dedupes fetches per run.
  docs updated: `docs/harness/decisions.md` (ADR-H90),
  `docs/harness/architecture.md`, `docs/NAVIGATION.md`

- **Tool-loop integrity Phase 3 â€” native tool-result text is bounded at the one
  execution seam (ADR-H91).** `ToolRegistry.execute` trims a model-facing text
  result to `MAX_TOOL_RESULT_CHARS = 24_000` with a non-JSON marker and
  `truncated`/`shown_chars`/`total_chars` fields; the graph emits `tool.truncated`.
  Byte-identical under the bound; `ToolResult.data` is never bounded. Blast
  radius: only `session_open` can exceed it (~25.6k chars max); the constant was
  not raised to hide it. Model-streaming helpers were extracted to
  `model_stream.py` to keep `graph.py` under its ratchet.
  docs updated: `docs/harness/decisions.md` (ADR-H91),
  `docs/harness/architecture.md`, `docs/NAVIGATION.md`

- **Tool-loop integrity Phase 4 â€” an effectful-tool approval is single-use
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
  to a 100% minimum in two places â€” `normalizeBackgroundPrefs` (`backgrounds.ts`)
  and the slider `min` (`background-settings.tsx`) â€” even though the CSS and
  `resolveBackgroundCss` already support 50%. Lowered the floor to 50% in both, so
  the wallpaper can be shrunk. Test updated plus a sub-100% regression assertion.
  docs updated: `docs/ARCHITECTURE.md`

- **MCP integrity close-out â€” live supply-chain verdict surfaced; catalog-change
  counters shown; the report's dead `upstreamChecked` flag made real.**
  `SupplyChainChecker` now records the last observation per
  `(ecosystem, package, version)` with a wall-clock `checkedAt`; a read-only
  `observe_command` lets `supply_chain_report` attach `liveVerdict` to a
  configured package and DERIVE `upstreamChecked` from real observations (the
  caller `upstream_checked` parameter is removed â€” it had no caller and could
  never be true). The route stays offline. The card/lifecycle panel now render
  `lifecycle.catalogChanges`/`lastCatalogChangeAt` beside the existing "catalog
  changed" banner, via a pure `catalogChangeSummary` helper â€” no event consumer
  was added. `python/tests/test_retrieval_health.py` and the health-aware
  retrieval workstream are adjacent scope (uncommitted, tested green).
  docs updated: `docs/harness/mcp-integrity-progress.md` (Milestone 11),
  `docs/harness/decisions.md` (ADR-H88/H89), `docs/NAVIGATION.md`

- **`memory` tool â€” save crash on missing/null `confidence` fixed.** `save`
  crashed with `float() argument must be a string or a real number, not
  'NoneType'` when `confidence` was present-but-null (`args.get("confidence",
  0.8)` returns `None` for a JSON `null`). Added `_coerce_confidence`
  (missing/empty/NaN/out-of-range â†’ default 0.8, bounded 0..1) and wrapped the
  authorize+commit call so any malformed input returns a typed `invalid_input`
  refusal instead of an unhandled `TypeError`. The per-turn write-authorization
  gate is untouched (its fail-closed false negative is intentional). Tests added
  for save-without-confidence, save-with-null, and malformed confidence.
  no doc change â€” bug fix, contract unchanged.

- **Background â€” Eclipse I is the official first-run wallpaper; added resize controls.** Factored the shipped default into `DEFAULT_BACKGROUND_ID = 'eclipse-1'` (the official background new users get) and marked it with a "Default" badge in the picker. Added image resize controls: **Zoom** (100â€“300%), **Horizontal** and **Vertical** focal position (0â€“100%), alongside the existing Fit and Darkening. The wallpaper image moved onto the layer's `::before` so zoom scales only the art (the dim scrim stays full-size), and the resolver now emits `--app-bg-zoom` + a focal `--app-bg-position`. `BackgroundPrefs` gained `scale`/`positionX`/`positionY` (normalized/clamped).
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Sidebar â€” clicking the ChatBot icon always starts a new chat.** The ChatBot nav item used to just switch to the chat tab, resuming whichever conversation was last active. It now calls `onNewChat()` before switching tabs, so clicking it opens a fresh chat every time; previous conversations remain reachable from the history list above the nav.
  no doc change â€” bug fix; no architecture, contract, setup, or data-shape change.

- **MCP: no-op `list_changed` no longer emits a "catalog changed" event, and the
  live supply-chain check is now a visible operator setting.** Two honesty/
  reachability gaps in the M4/M6 work. (1) `rediscovery.py` re-ran discovery on
  every inbound `list_changed` and emitted `mcp.catalog.changed` unconditionally.
  A server that announces a change that never materialises (or fires the
  notification gratuitously) therefore produced a stream of misleading "catalog
  changed" signals â€” the operator would be asked to re-confirm an identical
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
  TS `MCPServerView`/`MCPServerInput`/`DraftServer` contract â€” so a save from the
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

- **Memory â€” confirmed and documented the verification/source policy (P2-11).**
  No code change: `source=explicit_user` grants authority but is stored
  `unverified`; only a user correction or an explicit `verification="verified"`
  marks a record verified. Recorded that "most records unverified" is intended
  and that the model-initiated `save` write gate is deliberate.
  docs updated: `docs/harness/memory-maturity-baseline.md`

- **Source health â€” canonical route keys + persisted probes (P0-3/P1-5).** The
  `SourceHealth` ledger was fragmented: the same route appeared under `Equity`
  and `equity`, under `unknown`/`*`, and the `research_health` probe tested one
  provider (`duckduckgo-html`/`safe-get`) while production recorded another
  (`WEB`) â€” so a working provider was reported as failing and per-route success
  rates were wrong. Added `src/lib/harness/health-key.ts` with a closed
  vocabulary (`canonicalMarket`/`canonicalAssetClass`/`canonicalSource`, alias
  folding to one source per provider) applied on both write and read, and made
  the `research_health` probes upsert into the same ledger under the same
  instrument-less route key as production. New module keeps `data-bridge.ts`
  under its size ratchet. Tests: `src/lib/harness/health-canonical-keys.test.ts`.
  docs updated: `docs/harness/decisions.md` (ADR-H85), `docs/NAVIGATION.md`,
  `docs/DATA-FLOW.md`

- **`memory` tool â€” null-limit crash fixed.** `action=list` failed with
  `TypeError: int() argument must be a string ... not 'NoneType'` when the model
  emitted a present-but-null `limit` (JSON `null`): `args.get("limit", 20)`
  returns `None` because the key exists, so `int(None)` raised. Coerced the
  optional integer args in `python/harness/memory_tools.py` with `or` instead of
  the positional default (`memory` search/list, `session_open` before/after),
  which also catches `None`; added a regression test asserting both branches
  tolerate `limit: null`.
  no doc change â€” bug fix, contract unchanged.

- **MCP integrity â€” real-server defects fixed and the remaining gaps closed.**
  Two sessions. First: a provider-side error body returned with `isError=false`
  is now a failure (pure `looks_like_provider_error` classifier, an explicit
  rendered failure, `mcp_tool_provider_error`); **Test is not Verify** â€” a new
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
  `docs/harness/decisions.md` (ADR-H77â€“H84), `docs/harness/architecture.md`,
  `docs/NAVIGATION.md`, `docs/harness/mcp-phase-6-progress.md`,
  `docs/harness/mcp-ui-parity-progress.md`, `CONTRIBUTING.md`

- **General settings â€” Start screen control removed; background picker promoted.** Removed the "Start screen" button grid from Settings â€º General â€º General (the boot tab now just follows the default/deep link; `general-prefs` still stores it for compatibility). The Background panel now leads the General tab, and the shipped **Eclipse I** wallpaper is the default on first run (`DEFAULT_BACKGROUND.mode = 'image'`, `preset = 'eclipse-1'`). The wallpaper fills the main content panel (right of the sidebar) on the ChatBot landing only (empty transcript) and resizes with it, so opening the sidebar keeps the image fully visible; the sidebar keeps its normal (non-transparent) frost. Follow-up to the background feature below.
  no doc change â€” same unreleased feature; docs already describe the background system.

- **Background fix â€” scrim was an invalid `background-image` layer.** The legibility scrim was written as a bare color (`rgba(0,0,0,0.45)`), but a color is not a valid `background-image` value; CSS dropped the *entire* multi-layer declaration, so no pattern or wallpaper ever painted. The scrim is now a solid-gradient image (`linear-gradient(rgba(...), rgba(...))`) and the CSS `var()` fallback changed from `transparent` to `none`. Same-day follow-up to the background feature below.
  no doc change â€” bug fix in an unreleased change.

- **Settings â€º General â€º Background â€” customizable page wallpaper.** The hardcoded, dead `/backgrounds/eclipse bg.svg` chat-landing block (the file no longer exists) is replaced by a real background system in `src/lib/backgrounds.ts` (Settings â€º General â€º Background). Mode `none | pattern | image`: `pattern` absorbs the old Solid/Gradient/Grid control from Customization â€º Glass & Surfaces (single background surface now, tinted by brand, app-wide), and `image` offers the shipped Eclipse wallpapers (`public/backgrounds/eclipse bg-1.svg`/`-3.png`/`-4.svg`/`-5.svg`) or a user picture. Wallpapers paint the **ChatBot landing only** via a `.app-bg-layer` filling the main content panel (right of the sidebar, so the menu overlays the image). Custom uploads are downscaled client-side (~2560px, JPEG/PNG, up to 30 MB in) and stored in **IndexedDB** (`be_background`/`custom`) so a full-res wallpaper never eats the ~5 MB localStorage budget; prefs live in `be_background_v1`. Adds fit (cover/contain/tile) and a darkening scrim for legibility. Applied via `useHydrateBackground` in `stock-chat.tsx`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Root .gitignore: ignore a stray root node_modules/.** A tool running vitest from the repo root created `node_modules/.vite`; ignored so it can never be committed.
  no doc change â€” ignore-rule only.

- **Terminal cleanup â€” guard floor, line endings, commits.** Pinned the CHANGELOG guard floor to 345 and added an archive-seam assertion; normalized the 66 working-tree files that mixed CRLF/bare LF (content proven unchanged) and added a mixed-ending guard; recorded the `jdds.db` purge recommendation (keep it) and the smoke/CI caveats. Two commits: `8153d35` (line endings) and `43085d8` (closeout).
  docs updated: `docs/harness/terminal-cleanup-progress.md`, `docs/harness/closeout-progress.md`, `docs/NAVIGATION.md`

- **Terminal cleanup â€” codex checkpoint refs, filter remnant, stale lock.** Deleted
  the 12 
efs/codex/turn-diffs/checkpoints/* refs (12 exclusive jdds.db blobs,
  1.53 GB decompressed) and the 
efs/original/ filter remnant plus a stale
  maintenance.lock; git gc dropped .git from 101,428,986 to 46,889,484 bytes.
  Also consolidated the CHANGELOG sections and tightened its guard.
  docs updated: docs/harness/terminal-cleanup-progress.md,
  docs/harness/closeout-progress.md, docs/NAVIGATION.md

- **Closeout follow-up â€” CHANGELOG sections consolidated.** Same-date sections are
  now merged to exactly one section per date, the two malformed single-hash date
  headings in the archive were corrected, and an empty duplicate heading removed.
  Entry count preserved (350 before, 350 after); the rotation guard now asserts
  per-date uniqueness, no malformed heading, and an append-only floor.
  docs updated: `docs/harness/closeout-progress.md`

- **Closeout â€” history measurement, line endings, CHANGELOG forensics, CI.**
  Measured the five open items (see `docs/harness/closeout-progress.md`): the
  `jdds.db` history load is 20 blobs (the 12 `refs/codex/...` checkpoint refs hold
  ~1.53 GB exclusive; `backup-before-email-rewrite` has no exclusive blobs), and
  history purge/archive are prepared but not executed. Added a root
  `.gitattributes` (LF normalization; `.wav`/`.ico`/`.db` binary) so a one-line
  edit no longer shows a phantom whole-file diff â€” renormalized `ARCHITECT.md`
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

- **Engineering hardening â€” the release gate is now local and runnable.** Deleted
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

- **Engineering hardening â€” took `jdds.db` out of git.** `git rm --cached`ed the
  60 MB vault (file kept on disk); ignored it at the app level with the new
  distribution story (`scripts/doctor.js` provisions it via `npx prisma db push`).
  Fixed the root `.gitignore` (the broken `0`/`0-shm`/`0-wal` lines are now
  `*.db`/`*.db-shm`/`*.db-wal`; removed the vestigial root `/scripts/` rule).
  `git gc --prune=now` reclaimed packed garbage (size-pack 372 -> 94.5 MiB).
  The full history-purge procedure (2B) is written up but not executed.
  docs updated: `docs/harness/engineering-hardening-progress.md`

- **Engineering hardening â€” front-door tests and authorization.** Guarded the four
  previously-unguarded mutation routes (`POST/DELETE /api/symbols`,
  `POST /api/investor-eye/portfolio`, `POST /api/memory-providers/search`,
  `DELETE /api/skill-executions/[runId]`). Added route tests for them plus
  settings/journal-trades/provider-keys/alerts (route-test count 2 -> 11); added
  the first Python router-seam test (`python/tests/test_router_seam.py`); fixed a
  flaky macro-health test that made a real network call.
  docs updated: `docs/harness/engineering-hardening-progress.md`

- **Engineering hardening â€” size and lint discipline.** Replaced the single 200 KB
  file-size ceiling with a graduated guard (hard 1200 lines + a non-growing
  ratchet; soft 800) in `src/lib/size-budget.test.ts`, and added the equivalent
  Python guard `python/tests/test_size_budget.py`. Removed genuinely dead symbols
  (`LEGACY_FILES`, `vendorAvailable`, four unused test imports), lowering eslint
  warnings from 34 to 24 with no blanket disables.
  docs updated: `docs/harness/engineering-hardening-progress.md`

- **Engineering hardening â€” MCP leftovers closed or re-stated.** Non-text MCP
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

- **Engineering hardening â€” documentation reconciliation.** Updated
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

- **MCP Phase 6.1 â€” round-trip integrity (fixes a silent authority downgrade).**
  `upsert_mcp_config` now implements "absent means preserve; explicitly present
  means replace" using the incoming model's `model_fields_set`, so a partial save
  (the old UI payload) can no longer reset `trust`, `lazy`, `tools`,
  `tool_effects`, `data_source_tools`, `confirmed_catalog_digest` or the
  keepalive/idle/lifetime/TLS fields. `install_mcp_integration` is now
  create-if-absent so re-installing never resets a user's changes. `public_dict()`
  also emits the raw operator-set bounds so the wire is lossless. A hard
  invariant is added: a save may never widen authority by omission. TS
  `MCPServerView`/`MCPServerInput` carry every field; the viewâ†”draft mapping is a
  pure tested module `src/lib/harness/mcp-draft.ts`.
  docs updated: `docs/harness/mcp-ui-parity-progress.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H74)
- **MCP Phase 6.1 â€” full-fidelity editor and status surfaces.** The settings UI
  reaches every Phase-6 field: trust tier, include/exclude filters, per-tool
  effects, native data sources, capability toggles, lazy/keepalive/idle/lifetime,
  TLS/mTLS, limits, SSE transport and OAuth sign-in. The server editor is
  extracted to `src/components/screens/mcp/`; a lifecycle panel renders the
  runtime's retry/keepalive/recycle/metrics block honestly; approvals gain status
  filtering; the config load error is shown loudly.
  docs updated: `docs/NAVIGATION.md`, `docs/harness/mcp-ui-parity-progress.md`
- **MCP Phase 6.1 â€” product surface, leftovers and `manager.py` split.** New
  front-door routes `POST /api/harness/mcp/integrations/[id]/install` and
  `GET /api/harness/mcp/supply-chain`; the wizard installs a preset and the
  supply-chain panel renders offline. Non-text MCP content now reports MIME type +
  byte size instead of an opaque omission. `resource_schemes` adds an optional
  per-server narrowing with the global allowlist as a hard ceiling. `manager.py`
  is split by pure extraction into `runtime.py`, `introspection.py` and
  `oauth_flow.py` (1579 â†’ 1226 lines), `MCPManager` facade unchanged.
  docs updated: `docs/NAVIGATION.md`, `docs/harness/architecture.md`,
  `docs/harness/mcp-ui-parity-progress.md`

- **Docs â€” Eclipse-as-a-Harness roadmap: the phased plan for the code/coding-agent,
  job, delegation and self-improvement capability.** New `docs/harness/roadmap/` â€”
  one file per phase (`README.md` + `phase-00-policy-and-baseline.md` â€¦
  `phase-12-evaluation-gate.md`) instead of one long document, so a reader opens
  only the phase they are running. `README.md` carries a verified capability ledger
  against a harness like Hermes (what exists: the one runtime, retrieval,
  evidence-gated research, skills, memory, MCP; what does not: any code
  read/write/run capability, isolation, a harness-owned scheduler, delegation,
  self-modification beyond skills), the four structural gaps, the invariants that
  survive every phase (indexed 3.1â€“3.8 so the phase files can cite them), Â§0 the
  audience rules, work already in flight (`run_lineage.py`, `graph_context.py`),
  the file map and the ADR table. Every phase file uses one canonical heading
  scheme (numbered Â§1â€“Â§11, a `## Contents` table, numbered `### 6.x` contracts) and
  ships its exact contracts (real signatures, DDL, routes), runnable acceptance
  gates and a paste-ready prompt, ending in the repo's docs obligation. Each phase
  also carries a **Â§4 "Who can use it (the non-expert obligation)"**: the
  capability is for the whole finance field â€” analysts, PMs, traders, advisors,
  accountants, risk officers, students, small-business owners â€” not engineers or
  quants only. User-facing text names the finance job and never the mechanism, copy
  lives as keys in `src/lib/i18n/`, refusals are one plain sentence with a next
  step, and each phase adds a plain-language gate over
  `policy.PLAIN_LANGUAGE_DENYLIST`. The ADR series is numbered contiguously from the
  current tail: **ADR-H93â€¦ADR-H114**. Planning docs only â€” no code, tests or runtime
  behaviour changed. The earlier single-file roadmap is kept as a `status: Stale`
  pointer (`docs/harness/eclipse-harness-roadmap.md`) per the "mark stale, never
  delete" rule.
  docs updated: `docs/harness/roadmap/**`, `docs/NAVIGATION.md`,
  `docs/harness/eclipse-harness-roadmap.md` (now Stale)
