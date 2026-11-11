---
title: Capability Builder (generated recipes)
status: Current
last-verified: 2026-11-10
---

# Capability Builder

**Who this is for:** anyone changing how Eclipse detects a missing capability,
builds a reusable recipe, or decides whether it may activate.

## Behavior

Eclipse distinguishes four outcomes instead of refusing an unknown request:

| Case | Route |
|---|---|
| One-off computation | `analysis_run` with a short program; nothing is saved. |
| Reusable analysis / report | `capability_request` -> `capability_build` -> tested recipe. |
| External system (broker, API, MCP) | `capability_external` proposes the existing MCP preset / plugin / endpoint; `capability_adapter` can author a disabled broker/API plugin draft. Credentials and approval are operator-supplied. |
| UI or harness change | UI Engineering or the code agent/RSL; operator approval. |
| Impossible or unsafe | State the exact missing surface, test failure or permission. |

A capability exists only after a manifest validates, a contract test passes in
the sandbox, and an activation decision is recorded. "The model wrote code" is
not availability.

## Module map

New package `python/harness/capabilities/`:

| File | Responsibility |
|---|---|
| `manifest.py` | `CapabilityManifest` / `CapabilityPort`; slug, semver, import/permission/effect validation, protected-path refusal. |
| `request.py` | `CapabilityRequest`, deterministic classification, witness search over static recipes, active generated capabilities and the live tool registry. |
| `verifier.py` | AST/import/path checks, contract-test execution through the existing analysis sandbox, output-contract validation. |
| `builder.py` | Draft write, version choice, verification, auto-activation of a pure workspace recipe, effectful hand-off, rollback and retire. |
| `handoff.py` | The typed effectful hand-off (surface, next tool, arguments, acceptance, evidence, activation). |
| `registry.py` | Loads active generated recipes into the existing `code/recipes.py` dynamic registry; exposes descriptors to discovery. |
| `store.py` | `CapabilityRequest` / `CapabilityRecord` / `CapabilityUsage` on the one `agent-memory.db` connection, with an in-process fallback for runtimes without a store. |
| `adapter.py` | Authors a reviewable, DISABLED broker/API plugin draft (manifest, code, README) under `.black-eclipse/adapters/`; validates it with the real `PluginManifest`; never installs or enables. |
| `tools.py` | The eight agent tools and their schemas. |
| `__init__.py` | Public contracts. |

The builder reuses the existing sandbox (`code/execution.py::run_analysis`), the
existing recipe runner (`code/recipes.py`), the existing discovery index
(`recovery/discovery.py`) and the existing tool registry. It adds no second
agent loop, tool registry, sandbox or database.

## Generated layout

Workspace drafts (gitignored):

```
.black-eclipse/capabilities/<slug>/<version>/
  manifest.json
  capability.py
  test_capability.py
  README.md
```

Adapter drafts (gitignored, never installed from here):

```
.black-eclipse/adapters/<slug>/
  plugin.yaml    # validates with PluginManifest; permissions: [network]
  plugin.py      # one tool method per endpoint; bearer token from config
  README.md      # endpoint table + operator activation steps
```

Promoted global capabilities live under
`python/harness/generated/capabilities/<slug>/<version>/`. Promotion is an
explicit operator action (`builder.promote`, `POST /capabilities/{id}/promote`):
it copies a verified workspace recipe, rewrites the manifest `scope` to `global`
and points the record at the copy. The builder never promotes or writes there by
itself; the workspace copy stays for audit, and activation of a global record
still requires the operator (ADR-H232/H234).

## Manifest contract

The manifest declares `id`, `version`, `kind`, `title`, `description`, `scope`,
typed `inputs`/`outputs`, `permissions`, `effect`, `timeoutMs`, `imports`,
`tests` and `acceptance`. For `recipe` and `report_template`:

- `effect` must be `read`;
- at least one input is required;
- permissions are limited to the analysis verbs;
- imports must already be in `code.execution.IMPORT_ALLOWLIST`;
- `tests` cannot be empty.

## State machine

```
draft -> tested -> active
             \-> unverified
active -> disabled -> active (rollback)
active -> retired
```

- A pure workspace recipe auto-activates only after a passing contract test.
- A global recipe stops at `approval_required`; nothing self-enables.
- An effectful capability stops at `handoff_required` and is owned by its
  existing surface; it never enters this draft/test/activate state machine.
- A failed or missing contract test stays `unverified` and cannot activate.
- A verifier crash is recorded as a failed check on the version (not raised and
  lost), so the draft always has a `CapabilityRecord` and the next build
  increments the version instead of silently reusing it.
- Every version keeps its source/test digests and directory, so rollback
  restores a previously verified version.
- Three recorded failures in a row auto-disable the version and emit
  `capability.disabled`.

## Contract test

The builder writes `test_capability.py` as assertions over `inputs` and `result`.
The verifier prepends `capability.py` and runs the combined program through the
PTC/analysis sandbox. The test therefore exercises the real implementation, not
a mock. Static checks run first: manifest policy, import allowlist, forbidden
reflection, traversal/protected-path literals, and output kinds. The import
allowlist is the built-in set plus the top-level modules of approved packages in
the managed Python environment (`docs/harness/python-env.md`).

## Safety

- Generated code executes only in the sandbox subprocess, never in the harness
  process.
- It has no network, no `open`, no `os`/`subprocess`, and no workspace path.
- The builder writes only inside `.black-eclipse/capabilities/<slug>/<version>/`.
- Effectful kinds, global scope and protected core paths are refused.
- Activation is a separate decision; the agent cannot supply `operator=true`.
- A missing test is reported as `unverified`, never treated as a pass.

## Retry and learning

A capability requested during a scheduled task carries that task id
(`ToolContext.task_id` from `input.context.taskId`). The id is stored on the
versioned `CapabilityRecord` (`taskId`) and on the effectful hand-off. When the
capability is activated — operator route, agent tool or rollback — the runtime
resumes the original task from its latest durable checkpoint **only if the task
is parked** (`WAITING`/`ASKING_USER`). A running or `TODO` task is never rewound;
the scheduler owns it.

A failed generated-recipe invocation records a `capability_failure` recurrence in
the ONE learning ledger. The same self-improvement pass that reads other
recurrences can therefore turn repeated capability failures into an inert
candidate. Repeated runtime failures still auto-disable the version and emit
`capability.disabled`; activation stays operator-gated.

## Effectful hand-offs (tool / skill / bot / UI / harness / plugin)

A reusable recipe is built here. An **effectful** capability is not: it already
has an owner with its own approval gate and its own proof. `capabilities/handoff.py`
turns the request into one typed `EffectfulHandoff` and stores it on the same
durable request (`status: handoff_required`). Nothing is executed or activated.

| Kind | Surface | Next tool | Proof the owner must record |
|---|---|---|---|
| `tool` with a matching kit | `scaffold_kit` | `scaffold_kit` | the declared files + the kit's checks/acceptance test |
| `tool` without a kit | code agent | `create_goal` (`taskType: code`) | durable task acceptance + tests + review |
| `skill` | `skill_create` | `skill_create` | a validated draft, then evaluation + promotion |
| `bot` (persistent scheduled agent) | `bot_create` | `bot_create` | the stored bot + a proven `bot_run`; the handler's single-use `bot_schedule` approval |
| `ui_widget` / `ui_page` | `ui_start_engineering` | `ui_start_engineering` | engineering-task criteria + catalog registration/page revision |
| `harness_change` | code agent / RSL | `create_goal` | tests + review; authority files stay protected |
| `plugin` | external lane | `capability_external` | credential/approval proposal, disabled install, operator enable |

A **bot** is a durable scheduled agent, not a file artefact: it is never routed
to `scaffold_kit`. Its trigger is a cron expression plus an explicit IANA
timezone (the engine computes the wall clock in that zone; UTC is not a safe
default across DST). The hand-off names the schedule as the missing input when
the request did not supply one.

The hand-off carries the arguments the owner needs (with missing inputs named),
the acceptance lines, the evidence list and a checkpoint-resume note. `capability_build`
returns it; the agent then calls the named tool **in the same turn**. Both
`capability_request` and the hand-off response say so explicitly, because a
hand-off describes the route — it is not a refusal and not the build.
`capability_build` no longer requires the analysis sandbox for an effectful kind
— only a pure recipe does. The target surface is the sole writer and the sole
source of verification.

**Multiple deliverables.** A request may name more than one thing ("turn this
into a skill and then a bot"). `detect_kinds` returns every deliverable in the
order the request names them; the first is the primary `kind`, and the
assessment's `deliverables` list carries each one's `nextTool`. Nothing is
dropped, and the agent is expected to call each surface. `classify()` remains
the single-kind compatibility wrapper.

**When the run is blocked.** A failure that has a permitted route is recorded as
a `CapabilityGap` and offered to the user once; see
[`no-dead-ends.md`](no-dead-ends.md). A safety denial is explained and never
offered as a bypass.

## External lane (broker / API / MCP)

`capabilities/external.py` is the ONE proposal contract for an external system.
It is read-only: it never installs, enables or stores a credential value, and it
adds no second install path.

The proposal takes credential **names** (vault secret names), never values, and
resolves to exactly one surface:

| Supplied fact | Surface | Install route | Activation |
|---|---|---|---|
| `integrationId` matching an MCP preset | `mcp_preset` | single-use `mcp_install` approval; writes a DISABLED config with no tools selected | operator enables and selects tools in Settings → MCP |
| `pluginPath` | `plugin` | the plugin platform's operator install (enabled false) | operator enables explicitly |
| `serverUrl` / `serverCommand` | `mcp_server` | none; the operator adds the custom server in Settings → MCP | operator enables explicitly |
| nothing | `operator` (honest gap) | none | none |

`MCPManager.secret_presence` reports only whether each name resolves to a value.
It never returns the value. The acquisition step refuses to install while a
required credential is explicitly missing or presence cannot be verified. The
proposal's `nextAction` names the exact next tool (`mcp_install` for a preset,
otherwise the operator transport).

The proposal carries the same `AcquisitionProposal` vocabulary the recovery lane
uses (`install` then operator `enable`, plus the retry checkpoint note). The
production recover handler now accepts an `integrationId` fact and consumes the
SAME single-use `mcp_install` approval as the agent tool; it writes a disabled
config and never enables the server. `pluginPath` keeps the existing plugin
platform path (`operator=true`, `enable=false`). The original task still resumes
through the task/checkpoint flow after activation (ADR-H230).

## Adapter authoring (draft only)

`capabilities/adapter.py` is the ONE from-scratch adapter author. When the
operator supplies an HTTPS base URL, a tool list and credential **names**,
`capability_adapter` writes a disabled plugin draft into
`.black-eclipse/adapters/<slug>/` and validates the manifest with the same
`PluginManifest` contract the plugin loader uses. It rejects a non-HTTPS URL, an
embedded userinfo, an MCP kind (that is the MCP surface), invalid/duplicate tool
names, credential-shaped values and an existing draft directory.

Mapping rules: `GET` tools become `read` permission tools that send arguments as
query parameters; `POST` tools become `external_action` tools that send a JSON
body. The draft declares only the `network` permission, `authentication: none`,
and a `secret` config field per credential name. The generated code assumes a
bearer token and says so; the README tells the operator to review the auth
scheme, install the folder (disabled) through the plugin platform, set the
secrets and enable it explicitly. The agent cannot install or enable anything,
and no credential value is accepted or stored.

## Tools

`capability_request`, `capability_build`, `capability_status`,
`capability_external`, `capability_adapter`, `capability_activate`,
`capability_rollback`, `capability_remove`.

They are `read`-permission tools because their writes are confined to generated
capability drafts and their execution is sandboxed; `capability_build` still
requires the run's analysis gate and the `analysis.execute` grant for a pure
recipe. An effectful kind returns a hand-off without needing the sandbox.

## Chat card and Settings

The runtime emits `capability.requested`, `capability.built`,
`capability.activated`, `capability.verification_failed`,
`capability.disabled` and `capability.retired`. `src/lib/agent/events.ts` maps
them to one typed `capability` event; `src/lib/harness/capability-types.ts`
coerces and merges the lifecycle view; `src/components/chat/capability-card.tsx`
renders the need, surface, version, test counts, failed checks and the exact
verification stderr. A later event updates the SAME card; it never replaces it
with a fresh, less-informative view. The card is persisted as
`Message.capabilityBuild`, so it survives a transcript reload. An effectful
hand-off renders as `handoff_required` with its `nextTool` and evidence list; it
shows no contract-test checks because the target surface owns verification.

Settings › Capability Studio › **Generated** is a read/operator surface over the
same records (`GET /capabilities`, `GET /capabilities/{id}`), plus the read-only
built-in recipe catalogue (`GET /capabilities/builtins`, declared before the id
route; static `code/recipes.RECIPES` only, never the dynamic/generated ones).
Activation, deactivation, rollback, retire and promote are `POST` routes gated by
`require_operator`; the server re-checks the operator transport, and the agent
cannot call them. The UI shows version, status, scope, test status, usage counts
and the source/test digests, and lists built-ins read-only with a built-in
badge. It adds no second store, registry or enable path.

The chat card carries the next action when the runtime recorded one: **Build it**
and **Show plan** for a `gap`/`needs_source` proposal, **Continue** for a
`handoff_required` (calls the named `nextTool` through the chat), **Rebuild with
RSL** for an `unverified`/`disabled` version, and **Not now** to dismiss locally.
Every button sends a prompt through the one chat path; nothing activates from the
card. The Studio row offers the same **Rebuild with RSL** (opens chat with the
rebuild prompt) and **Promote to global** for a verified workspace recipe. A
computed result carries `recipe` (the runtime's own name for the recipe that
ran), rendered as an ordinary provenance-adjacent line, never as evidence.

## Read-only data tools (2026-10-19)

A generated or ad-hoc analysis program can `import eclipse_tools` and call
exactly three read-only bindings: `market_snapshot`, `live_quote` and
`price_history`. The sandbox still has no live channel: the call writes one
pending request and stops; the host validates it against the allowlist, resolves
it through the existing DataBridge, memoizes the reply and replays the same
program. Fetched payloads stay in the sandbox; only final outputs and audit
metadata (tool name, argument/result digests, status, round) enter the model
context. The import is refused unless the run has a host resolver, and the AST
gate accepts only `import eclipse_tools` (no aliases, no `from` imports, no
unknown attributes). The separate terminal `execute_code` service is unchanged;
this mechanism belongs to the analysis/recipe lane. ADR-H235.

## Not yet implemented

- Generic from-scratch broker/API adapter authoring. The external lane proposes
  the existing MCP/plugin surface but never writes a new adapter from scratch.
- A built-in + generated listing in Capability Studio (built-in recipes/kits are
  not enumerated there yet).
- A resolved gap becoming a `successful_procedure` candidate automatically.
  Failures already feed the recurrence ledger; procedure promotion remains a
  separate review step.
