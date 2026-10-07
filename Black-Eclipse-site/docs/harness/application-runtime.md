---
title: Application Runtime (DevOps) — Understand, Prepare, Run, Observe Apps
status: Current
last-verified: 2026-10-06
---

# Application Runtime (DevOps)

**Who this is for:** anyone changing how Eclipse discovers a project, installs
its dependencies, starts it (locally, in Docker, or with Docker Compose), checks
whether it is healthy, diagnoses why it isn't, recovers it, or reports its ports,
services and metrics.

## The one sentence

> Eclipse understands *applications*, not shell commands: one provider-agnostic
> registry, one lifecycle, and success claimed only from an actual passing health
> check — `RUNNING` is never conflated with `HEALTHY`.

## Where it lives

```
python/harness/execution/application/
  models.py           ApplicationDescriptor/RuntimeHandle/ServiceGraph/Health*/Diagnosis…
  registry.py         RuntimeRegistry (packages, containers, compose, orchestrators, infra, deployments)
  discovery.py        ApplicationDiscovery + discover_application + service graph + compose parser
  environment.py      EnvironmentDetector (local tools) + EnvironmentManager (.env, secret masking)
  package_managers.py 11 adapters: npm/pnpm/yarn/bun/pip/uv/poetry/cargo/go/maven/gradle
  container.py        ContainerRuntimeAdapter + DockerAdapter + PodmanAdapter
  compose.py          ComposeAdapter + DockerComposeAdapter + PodmanComposeAdapter
  cli_base.py         CliAdapter + CliOperation + CliResult (the shared closed-argv base)
  orchestrators.py    KubernetesAdapter + HelmAdapter + KustomizeAdapter
  infrastructure.py   TerraformAdapter
  cloud.py            AWS/Azure/GCP/Cloudflare/Vercel/Railway/Render adapters
  deployment.py       DeploymentEngine (validate→build→test→package→deploy→verify; promote)
  provisioning.py     provider readiness (installed + signed in, non-secret)
  managed_cli.py      long-running CLI ops (port-forward, logs -f) as managed processes
  app_graph.py        cross-application dependency graph (monorepo ordering)
  workspace_ops.py    start/stop MANY applications in dependency order
  observability.py    status/list/logs/events/metrics/metrics-history
  policy.py           RuntimePolicy (risk bands + ALLOW/ASK/DENY)
  ports.py            PortManager (check/find_free/identify/list; over the terminal port table)
  health.py           HealthCheckEngine (process/tcp/http/container/database/custom; backoff)
  diagnostics.py      RuntimeDiagnosticsEngine (classify → code location for CIUE)
  recovery.py         RecoveryEngine (bounded diagnose→strategy→act→verify; never a loop)
  state.py            ApplicationStateMachine (explicit states, validated transitions)
  store.py            ApplicationRuntimeStore (agent-memory.db tables)
  events.py           RuntimeEventEmitter + the closed event vocabulary
  cache.py            DiscoveryCache (mtime-keyed, bounded, invalidated)
  manager.py          ApplicationRuntimeManager (the ONE lifecycle) + RuntimePolicy
  tools.py            agent tools: runtime_*, package_*, environment_*, port_*, health_*
  container_tools.py  agent tools: container_*, compose_*
  k8s_infra_tools.py  agent tools: k8s_*, helm_*, kustomize_*, terraform_*, cloud_*, deploy_*
  _tool_common.py     shared refusal/root/actor helpers + pydantic input models
  runtime.py          process-wide singleton

python/harness/routers/application.py   /runtime/*  (operator-gated UI surface)
python/harness/cli.py                    the `eclipse` CLI
scripts/eclipse.js                       the CLI launcher (bin: eclipse)
```

Front door: `src/lib/harness/application-{client,browser}.ts`,
`src/app/api/runtime/[...path]/route.ts`, and the Applications tab in
`src/components/terminal/{runtime-panel,terminal-dock}.tsx`.

## Relationship to the other subsystems

| Subsystem | Owns | How the runtime uses it |
|---|---|---|
| **Terminal** (`terminal/`) | persistent processes, process trees, ports | local services start through `TerminalManager.start_process`; ports via `PortManager` over the terminal port table |
| **Sandbox** (`code/sandbox.py`) | the ONE bounded execution primitive | every package-manager/container/compose argv runs through it (no shell) |
| **Policy** (`code/policy.py`) | autonomy profiles, command vocabulary, path safety | `APP_RUNTIME_WRITE_TOOLS` are removed at `plan_only`; env-file writes are operator-only |
| **Execution** (`execution/`) | one-shot run/build/test/diagnose | shares the diagnostic parser and telemetry sampler; the runtime adds the *application* lifecycle above it |
| **Persistence** (`agent-memory.db`) | runtime tables | `ApplicationRuntimeStore` owns `Application`/`AppRuntime`/… on the shared connection |

The terminal and execution layers are **not** replaced. The runtime is a layer
*above* them: it discovers the application and drives the existing primitives.

## The lifecycle

`ApplicationRuntimeManager.start()` follows one path:

```
DISCOVER → VALIDATE → PREPARE (ports) → [INSTALL] → [BUILD] → START
         → HEALTH CHECK → RUNNING (or DEGRADED) → OBSERVE → STOP → CLEANUP
```

`ApplicationStateMachine` (`state.py`) validates every transition; a terminal
state (`STOPPED`, `FAILED`) has no outgoing edges.

- **`RUNNING` means the processes/containers exist.**
- **`HEALTHY` is a separate assertion** made only by a passing check.
- A service that starts but never answers a health check becomes `DEGRADED`.

## Discovery

`discover_application(root)` returns a normalized `ApplicationDescriptor`:
language, framework, runtime, package manager + lockfile, install/build/dev/
start/test/lint commands, Docker/Compose support, env files, required variables,
databases/caches, services and ports. It reuses `ProjectDetector` and never
guesses (an absent manifest is absent). `build_service_graph` turns a compose
file into a normalized `ServiceGraph` with a deterministic `startup_order()`
(dependencies before dependents; a cycle breaks honestly).

## Package managers

`PackageManagerAdapter` declares capabilities; `BasePackageManager` builds argv
from validated arguments and runs it through the sandbox. A **declared/lockfile
manager is authoritative**: if a project ships `pnpm-lock.yaml` but pnpm is
absent, the caller gets the honest "pnpm is unavailable" — never a silent switch
to npm.

## Containers and Compose

`ContainerRuntimeAdapter` is one abstraction; `DockerAdapter` and `PodmanAdapter`
are two configurations. Every argv is built from validated arguments (names,
images, port maps, volumes, env keys), never string concatenation. `ComposeAdapter`
is a front end keyed by the engine it drives (`docker compose`,
`podman compose`/`podman-compose`); it understands the service graph.

**Destructive operations** (`container.remove`, `container.rmi`,
`container.volume rm`, `compose.down`, `compose.rm`) are `external_action` tools
removed at `plan_only`, and `RuntimePolicy` requires explicit authorization for
them.

## Environment and secrets

`EnvironmentManager` reads/merges `.env*` and **never returns a secret value** to
the model: a secret is `[SECRET]`, and only its existence/emptiness/source is
exposed. `EnvironmentDetector` probes the local machine for tool versions
(non-sensitive only). `.env` writes require an operator.

## Health checks

`HealthCheckEngine` runs `process`/`tcp`/`http`/`container`/`database`/`custom`
checks with a bounded timeout and retry count. `process_running != healthy`.
A check that never passes reports `UNHEALTHY` with the reason, never a fake OK.

## Diagnostics

`RuntimeDiagnosticsEngine.classify()` maps output/exit/health/port/env to a
`RuntimeDiagnosis` with a category (`port_conflict`, `dependency_failure`,
`environment_missing`, `database_unavailable`, …), severity, evidence, suggested
recovery strategies and — when the output names one — a `{file,line,column}`
**location** that connects the runtime error to the code-intelligence layer for
autonomous debugging. It reuses the execution layer's output parser.

## Bounded recovery

`RecoveryEngine.run()` is a bounded loop (`HARNESS_APP_RECOVERY_MAX_ATTEMPTS`,
default 3, hard-capped at 10): diagnose → pick one strategy → act → re-verify.
It records EVERY attempt and **never acts on an irrecoverable diagnosis**
(a permission denial, a security block). There is no `while true`.

## Persistence and reconciliation

`ApplicationRuntimeStore` owns `Application`, `AppRuntime`, `AppService`,
`AppPort`, `AppHealthCheck`, `AppRuntimeEvent`, `AppDeployment` on the shared
`agent-memory.db`. On boot, `ApplicationRuntimeManager.reconcile()` re-examines
the runtimes left by a previous process: a persisted `RUNNING` is only believed
when the live terminal still knows its process; otherwise the runtime becomes
`DEGRADED` — never a fabricated `RUNNING`.

## Events

`events.py` owns the closed vocabulary (`application.discovered`, `build.*`,
`process.*`, `container.*`, `health_check.*`, `runtime.*`, `deployment.*`). Each
event is persisted and published on the harness `EventBus`.

## Agent tools

`runtime_detect/inspect/start/stop/restart/status/health/logs/cleanup/reconcile/
diagnose/recover/metrics/capabilities`; `package_detect/version/install/add/
remove/update/list/run/build/test/audit`; `container_build/run/start/stop/
restart/exec/logs/inspect/stats/list/remove/pull/rmi/network/volume`;
`compose_validate/config/build/up/down/start/stop/restart/ps/logs/exec/pull/rm`;
`environment_inspect/validate/load/compare/set/unset`; `port_check/find_free/
list/identify_process`; `health_check/status`. All register on the SAME
`ToolRegistry`; the write half is removed at `plan_only` via
`code/policy.APP_RUNTIME_WRITE_TOOLS`. The read-only subset is also on the
finance agent so "inspect this project" / "is it healthy" need no coding turn.

## Configuration

| Variable | Meaning | Default |
|---|---|---|
| `HARNESS_APP_RECOVERY_MAX_ATTEMPTS` | bounded recovery attempts | `3` (max 10) |
| `HARNESS_EXEC_*` | the sandbox limits every argv inherits | see execution doc |

Docker/Podman absence is reported honestly (`ENGINE_UNAVAILABLE`), never faked.

## Adding a provider

- **Package manager** — subclass `BasePackageManager`, declare
  `name`/`language`/`capabilities`/`lockfiles`/`manifests`/`executables`, add the
  argv builders, register in `build_package_manager_registry()`.
- **Container engine / Compose** — subclass `ContainerRuntimeAdapter` (set
  `binary`) or `ComposeAdapter` (set `engine`), register in
  `build_runtime_registry()`.
- **Orchestration / infrastructure / cloud** — subclass `CliAdapter`, declare
  `kind` (`orchestrator`/`infrastructure`/`deployment`), `binary`,
  `capabilities` and a CLOSED `operations` table (each a `CliOperation` with an
  `argv` builder and a `validator`), and register in the matching
  `build_*_adapters()`. The core lifecycle does not change.

## CLI

`eclipse <group> <action> [args] [--json] [--authorized]` — a real, structured
surface over the SAME manager the agent tools use:

```
eclipse runtime detect|capabilities|inspect|start|status|health|stop|restart|cleanup|logs|diagnose|recover|reconcile|list
eclipse package detect|version|list|install|add|remove|update|build|test|audit|run
eclipse environment inspect|validate|load|compare|set|unset
eclipse port list|check|find-free|identify
eclipse container ps|logs|exec|images|inspect
eclipse compose up|down|ps|logs
eclipse providers [--root PATH]
eclipse workspace graph|start|stop
eclipse k8s get|pods|logs|describe|apply|delete|scale|exec
eclipse terraform init|validate|fmt|plan|apply|destroy|output|state
eclipse deploy run|status|logs|rollback
```

The deploy line also supports `eclipse deploy run --environment production --authorized`
and (`promote`) the staging→production promotion with rollback.

Run it as `npm run eclipse -- <args>` or `node scripts/eclipse.js <args>`. A
destructive command refuses unless `--authorized` is passed. Output is JSON with
`--json`, a one-line summary otherwise.

## Kubernetes / Terraform / cloud

`kubectl`, `helm`, `kustomize`, `terraform` and the cloud CLIs
(`aws`/`az`/`gcloud`/`wrangler`/`vercel`/`railway`/`render`) are all `CliAdapter`
configurations: a CLOSED operation table, validated arguments, no shell, one
sandbox, JSON output parsed into structured data. A missing binary is
`ENGINE_UNAVAILABLE`. A mutation (`apply`/`delete`/`scale`/`exec`/`destroy`/`deploy`)
is removed at `edit_verify`/`plan_only` and additionally requires authorization.
Cloud credentials reach a provider CLI only through its OWN ambient mechanism;
this layer never passes or reads a secret.

## Deployment

`DeploymentEngine.deploy()` runs validate → build → test → package → deploy →
verify and delegates the deploy to a cloud adapter. A `production` deploy requires
explicit authorization. A deployment is `deployed` only when the provider accepts
it; it is never claimed live from a status call alone.

## Production hardening

- **Discovery cache** — `DiscoveryCache` memoizes the descriptor for a short TTL,
  keyed on the size+mtime signature of every watched manifest/lockfile/compose/
  `.env` file, so any change (or a new file) invalidates it. A dependency
  install/build invalidates it explicitly.
- **Health backoff** — a retrying check grows its interval (2× per attempt, capped
  at 8s) so a slow-booting service is polled, not hammered.
- **Bounded logs** — `manager.logs()` filters by substring/severity/errors-only and
  caps the returned lines (`max_lines`), so a chatty service cannot flood the
  caller. Each stream keeps its own process id and status.
- **Bounded recovery** — `HARNESS_APP_RECOVERY_MAX_ATTEMPTS` (default 3, cap 10).

## Provider readiness (provisioning)

`manager.readiness(root)` / `eclipse providers` / `GET /runtime/providers` report,
without any secret value, which orchestration/infra/cloud tools are **installed**
and **signed in**, plus a plain next step per gap. `/health` carries a summary
(`runtimeProviders`) so a missing tool is a boot-time instruction, not a runtime
surprise. A provider whose credentials are unknown reports `authenticated: null`,
never a fabricated `true`.

## Long-running CLI operations

`kubectl port-forward` and `kubectl logs -f` are not one-shot: `ManagedCli` starts
them through the EXISTING terminal process manager (tree-killed, cancellable,
streamed, visible in the Processes UI with `purpose="port-forward"`). The same
closed-argv validation applies, so an injected resource name is a structured
refusal.

## Deployment promotion

`eclipse deploy` / `DeploymentEngine.promote()` runs staging → (authorization) →
production, with a **health-gated rollback**: a staging failure never touches
production, and a production failure rolls back to the previous good release.

## Multi-application workspaces

`ApplicationGraph` (`app_graph.py`) orders several applications by declared
dependency (`.black-eclipse/app.json` `dependsOn`), with a monorepo heuristic
(`apps/*`, `packages/*`, `services/*`). `workspace_graph` / `workspace_start` /
`workspace_stop` (and `eclipse workspace`) start dependencies first and stop
dependents first. A cycle breaks honestly rather than looping.

## Testing

- Deterministic adapter tests use `CliAdapter(runner=…)` (a canned runner), so no
  real CLI is needed (`test_application_orchestration.py`).
- Live provider tests are **opt-in** (`BLACK_ECLIPSE_PROVIDER_IT=1` +
  `BLACK_ECLIPSE_PROVIDER=<name>`), never in `npm test`.

## Troubleshooting

- **`PACKAGE_MANAGER_UNAVAILABLE`** — the project requires a manager that isn't
  installed. This is intentional (no silent switch). Install it or set
  `install=False` when dependencies are already present.
- **`ENGINE_UNAVAILABLE`** — no Docker/Podman on this machine; container/compose
  operations refuse, they do not run unsandboxed.
- **A runtime is `DEGRADED`** — its processes exist but a health check failed.
  Read `runtime_logs` + `runtime_diagnose`; run `runtime_recover` for the bounded
  fix loop.
- **A persisted runtime became `DEGRADED` after a restart** — its process is
  gone; that is the honest reconciliation, not a bug.
