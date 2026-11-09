---
title: Harness Phase 3 — Skill System Architecture
status: Current
last-verified: 2026-11-08
---

# Harness Phase 3 — Skill System Architecture

**Who this is for:** anyone extending or debugging the Skill System. Read
[`architecture.md`](./architecture.md) first — this document only covers what
Phase 3 adds and why it is shaped this way.

## What a "skill" is here

A skill is a **versioned, machine-readable procedure** that the existing Python
agent runtime executes. It is not a second runtime, not a second tool registry,
and not an autonomous agent. It is a reviewed, declared capability:

- metadata (`skill.json`) → discovery, permission/dependency validation;
- instructions (`SKILL.md`) → loaded **only** after a skill is selected;
- an input/output JSON schema → validated in code, not by prose;
- required tools/permissions → resolved against the **existing** registry and
  permission policy.

Skills run through `harness/graph.py`'s `execute_run` exactly like a chat turn.
The skill's `SKILL.md` is composed into an `AgentConfig.systemPrompt`, its
`requiredTools` become the run's tool allowlist, and its input is serialized
into the run input. There is deliberately no second execution engine.

## User-authored skills

Users can write their own skills from the **Skills Library** ("Add skill"). A
user skill is stored in **eclipse-memory** (`UserSkill` table, migration 3) —
not on disk, because the runtime has no filesystem-write path by design — and is
materialised into the same `Skill`/`SkillVersion` tables and the same
`SkillRegistry` as built-ins. It is therefore discovered, validated and executed
exactly like a built-in, and the agent can use it via `skill_list`/`skill_view`
once it exists.

Safety, enforced in code:

- The manifest is validated by the same pydantic `SkillManifest`.
- A user skill may declare **only the safe, read-only permission set**;
  operator-only and forbidden permissions are rejected at author time.
- Required tools must exist in the runtime registry.
- Authoring requires operator authorization (same gate as every mutation).
- Editing a skill always creates a **new version**; the enabled version is never
  mutated. Built-ins cannot be edited or deleted. A user skill with execution
  history is **deprecated, not deleted**, so history is preserved.

## Installed (GitHub) skills — the acquire loop

A user can point Eclipse at a public **GitHub repository** ("load this skill")
and the agent installs it through `skill_install` (`skills/install_tools.py` +
`skills/install.py`). The loop is staged and approval-gated end to end:

1. **Parse + fetch.** `parse_source` accepts `https://github.com/<owner>/<repo>`
   (`/tree/<ref>/<path>` and `owner/repo` shorthand included); anything else —
   another host, http, a traversal subpath — is refused before a byte moves. The
   zipball is fetched from `codeload.github.com` over https with a size cap and
   timeout (stdlib only; no shell, no git binary).
2. **Extract + discover.** Extraction enforces zip-slip / absolute-path /
   symlink / file-count / expanded-size guards. Two skill formats are accepted:
   this app's `skill.json` + `SKILL.md` folders and the cross-tool
   `SKILL.md`-with-frontmatter convention, scanned under `skills/`,
   `.black-eclipse/skills/`, `.agents/skills/`, `.opencode/skills/` or the repo
   root.
3. **Normalize + scan.** Every candidate is materialized under
   `<root>/.black-eclipse/skills/<id>/`, validated by the same pydantic
   `SkillManifest`, and content-scanned; a skill tripping a quarantine-severity
   rule is refused (per-skill failures are reported and skipped). Manifests
   declaring never-grantable permissions are refused outright.
4. **Approve + commit.** `make_skill_authorizer` (`code/authorizers.py`) requires
   a single-use, digest-bound operator approval (`skill_install` kind in the SAME
   `McpApproval` store every other capability uses; the streaming chat pauses on
   the approval card). On approval the install commits and the root is trusted
   through the SAME project-trust store (`trust_root`), so later content changes
   quarantine only the changed skills until re-approved.

Installed roots live under `<repo>/installed-skills/<owner>__<repo>/`
(`BLACK_ECLIPSE_SKILLS_DIR` override) and load as the **`external` tier**:
precedence `project > profile > external > bundled`, so an operator's own or
authored skill always wins while an installed skill may deliberately shadow a
bundled one. `skill_sources` lists sources + drift; `skill_uninstall` removes a
skill (re-baselining the root, removing it entirely with its last skill).
Installing is not privilege escalation: a skill still runs through the same
permission/execution gate, and fetched prose is untrusted data under the
skill-safety rule.

The chat classifier (`code/request_intent.py`) routes software acquisition
("install blender", "download and install X", "install this skill from github")
to the code profile, so pip/npm/git-clone/`package_install` actually run there.
The sibling `mcp_install` tool (`mcp/install_tools.py` + `mcp/install_ops.py`,
shared with the operator route) installs a preset MCP integration the same way —
approval-gated, and always as a DISABLED, nothing-selected config.

## Where it lives

```
python/harness/skills/
  __init__.py
  manifest.py      pydantic manifest + enums (status, risk, category, permission)
  permissions.py   centralized, default-deny permission policy
  registry.py      load/validate/search/filter/version/dependency resolution
  store.py         compatibility alias: SkillStore = EclipseMemoryStore (eclipse-memory.db)
  runtime.py       SkillExecutionRequest/Result + execution through execute_run
  install.py       GitHub acquire loop: parse/fetch/extract/discover/validate/scan/
                   install/trust + uninstall/list (staged, bounded, zip-slip-safe)
  install_tools.py the `skill_install`/`skill_uninstall`/`skill_sources` agent tools
                   + the single-use approval authorizer (`skill_install` kind)
  schema_validation.py  full JSON Schema validation of input/output + schema self-check
  learning.py      trace analysis → learning candidates (no auto-enable)
  draft.py         candidate → unvalidated draft (no auto-enable)
  evaluation.py    deterministic evaluation + promotion gates
  events.py        skill.* event vocabulary (thin, on top of RunEmitter)
  library/         the shipped skill files (SKILL.md + skill.json)
    research/research-planning/
    research/source-verification/
    quality/financial-data-quality/
    finance/fundamental-analysis/
    system/report-generation/
```

**Why under `python/harness/` and not the repo's `skills/` folder?** The
existing `Black-Eclipse-site/skills/` (and `.opencode/skills/`) is the *AI coding
agent's engineering operating system* — unrelated to runtime skills. Putting the
runtime skill library there would collide with that meaning and confuse two
different audiences. The agentic runtime owns its skills, so they live in the
agentic runtime. (ADR: see `docs/DECISIONS.md`.)

## Data model (one source of truth)

All Phase-3 skill state lives in **`eclipse-memory.db`**, the runtime's dedicated
control database — never in JDdS (`jdds.db`) and no longer in `agent-memory.db`.
`harness/skills/store.py` is now a thin alias (`SkillStore = EclipseMemoryStore`);
the canonical DDL is `harness/eclipse_memory/schema.py` (a list of idempotent
migrations applied by `eclipse_memory/db.py`). The one-time, idempotent,
non-destructive import of legacy `agent-memory.db` skill rows is
`EclipseMemoryService.import_legacy_skills`. (Earlier revisions of this doc said
`agent-memory.db`; the code has since moved — see ADR-026 and the table split in
`phase-3-memory-progress.md`.)

| Table | Database | Holds |
|---|---|---|
| `Skill` | `eclipse-memory.db` | identity + latest version pointer + lifecycle status |
| `SkillVersion` | `eclipse-memory.db` | one immutable manifest revision (hash, status, eval state) |
| `SkillDependency` | `eclipse-memory.db` | skill→skill edges + version constraints |
| `SkillToolRequirement` | `eclipse-memory.db` | required tool names per version |
| `SkillPermissionRequirement` | `eclipse-memory.db` | required permissions per version |
| `SkillExecution` | `eclipse-memory.db` | one skill run: status, runId, parentRunId, mode, metrics |
| `SkillEvaluation` | `eclipse-memory.db` | one evaluation run (per version) + per-dimension result |
| `SkillEvaluationCase` | `eclipse-memory.db` | test cases attached to a version |
| `LearningCandidate` | `eclipse-memory.db` | a captured lesson (never auto-published) |
| `SkillPromotionRequest` / `SkillReview` | `eclipse-memory.db` | review lifecycle + audit |
| `SkillEvent` | `eclipse-memory.db` | skill lifecycle events beyond the run trace |
| `HarnessRun` / `HarnessEvent` / `HarnessToolExecution` | `agent-memory.db` | run traces + tool executions |
| `RetrievalRecord` / `ResearchReceipt` | `agent-memory.db` | durable retrieval replay + research receipts |
| `LearningRecurrence` / `LearningRecurrenceRun` | `agent-memory.db` | signature-only skill-workflow recurrence ledger |

**Why the split:** `agent-memory.db` is the *run* store (high-volume traces and
replayable retrieval receipts); `eclipse-memory.db` is the *control* store
(durable memory + the skill lifecycle). Keeping them separate means a large run
history never bloats the small, carefully-bounded control database. `SkillStore`
aliasing `EclipseMemoryStore` keeps a single implementation with no second
registry.

Immutable execution history is kept (a `SkillExecution` row is never mutated
after terminal status; a `SkillVersion` row is never edited — a new version is
inserted). Enabled behavior cannot change without a new `SkillVersion` row, and
the persisted version identity (`SkillManifest.version_identity`) covers the
instruction content as well as the manifest.

## Execution flow

```
SkillExecutionRequest (skillId, version, input, runId, parentRunId,
                       executionMode, actor/permissions, timeout, metadata)
      │
      ▼  registry.resolve + status + version + permission + dependency checks
      ▼  input schema validation (pydantic)
      ▼  compose AgentConfig (instructions + requiredTools allowlist)
      ▼  execute_run()  ← the EXISTING Phase-1 runtime (no new loop)
      ▼  output schema validation + evidence/warnings extraction
      ▼  persist SkillExecution + SkillEvent; emit skill.* lifecycle events
SkillExecutionResult (status, output, evidence, warnings, missingData,
                      limitations, traceId, runId, skillId, version, metrics)
```

The same contract serves every execution mode (`interactive`, `workflow`,
`scheduled`, `agent`, `evaluation`) — a skill never needs a mode-specific
implementation. Parent/child trace linkage is `parentRunId`; a nested skill call
is just a `SkillExecutionRequest` with the parent's run id.

## Dependencies and composition

Acyclic by construction. `registry.resolve_dependencies()` does a DFS with a
visiting-set; a cycle is a hard `CIRCULAR_DEPENDENCY` failure. Version
constraints are simple exact/`^`/`~`/`>=` comparators over semver. Missing
dependency, disabled dependency, or insufficient permission blocks before any
tool runs — the run is never partially executed.

## Permissions — enforced in code

`permissions.py` is the single authority. There is **no** scattered check.

- Default-deny: anything not explicitly granted is denied.
- Phase-3 safe set (granted to the default local actor): `data.read`,
  `research.read`, `analysis.execute`, `report.generate`, `skill.invoke`.
- Never granted: `trade.execute`, `broker.modify`, `production.modify`,
  `code.write` (and `code.execute`).
- `skill.create`, `skill.review`, `skill.enable`, `skill.disable` require
  **explicit authorization** (an operator secret / admin actor), not the default
  actor.

Markdown instructions are **not** a security boundary. Web/retrieved content is
data: it cannot change the system prompt, permissions, or policy. Skill
instructions can *describe* a procedure but can never *widen* a permission; the
allowlist and permission check are applied to the composed `AgentConfig` in
Python regardless of what the instructions say.

## Learning (controlled)

`learning.py` inspects a persisted run trace and **may** create a
`LearningCandidate` when explicit criteria are met (repeated failure solved by a
reusable procedure, a generalizable validation correction, a repeatedly
successful multi-step procedure, a verified fallback for missing data). It does
**not** create a skill. A candidate is inert until:

1. an operator generates a **draft** (`draft.py`) — always `status: draft`,
   always `evaluationStatus: not_evaluated`;
2. the draft is **evaluated** (`evaluation.py`);
3. evaluation passes the promotion gates;
4. an authorized actor **promotes** it.

At no point does a model-generated artifact become active automatically.
User-specific preferences stay in `AgentMemory`, not in a universal skill;
one-off market events are rejected as non-reusable.

## Evaluation

Deterministic checks first (manifest validation, schema validity,
dependency/permission resolution, attached test cases, regression comparison,
evidence/reporting-shape checks). An LLM judge is never the *only* mechanism and
never gates promotion. Results are stored per dimension — no single misleading
score. A failed mandatory dimension blocks promotion.

## Front door (Next.js)

The front door stays thin: it validates/proxies and renders. Python owns skills.
Routes added under `src/app/api/skills/**` and `src/app/api/learning/**` proxy to
the runtime's `/skills/**` endpoints with the same `api-guard` policy as
`/api/harness/*`. The UI is a new "Skills" tab in the existing sidebar, using the
existing frosted-glass system.

## Control Room information architecture

The Skills screen renders **five primary destinations**, not one tab per panel.
The grouping lives in `src/lib/app-screens.ts`:

| Primary | Sub-tabs |
| --- | --- |
| Library | Skills Library (`library`) — detail is a drill-down inside it |
| Learning | Learn a Skill (`learn`), Learning Queue (`learning`) |
| Journey | Learning Journey (`journey`) |
| Collections | Project Skills (`project`), Bundles (`bundles`) |
| Operations | Evaluation Center (`evaluation`), Execution Activity (`activity`), Maintenance (`maintenance`), Experiments (`experiments`) |

Two invariants matter when editing this screen:

- **`SKILLS_TABS` is still the whole inventory** (deep links + the agent surface
  map in `app-surfaces.ts`). `SKILLS_GROUPS` only decides what the primary tab
  bar shows. A visible tab must belong to exactly one group.
- **`hidden: true` means deep-link-only.** `start` (Start Here) is no longer a
  tab; its content is reachable from the Library's first-run state and at
  `/?tab=skills&sub=skills.start`. `app-surfaces.ts` filters hidden tabs so the
  agent map matches what is rendered.

Every panel uses the shared `PanelHeader` from
`src/components/screens/skills/skill-ui.tsx` (plus `EmptyState`/`ErrorState`),
and every bounded list uses the shared `PaginationFooter`/`usePagination` from
`src/components/ui/pagination.tsx`. RSL experiments were moved out of Journey
into Operations so the provenance graph is not buried under experimental
controls.

### URL state

The SPA keeps screens mounted, so the URL is the only durable view state. Two
shapes are used:

- **Library view** — `?tab=skills&sub=skills.library&q=…&cat=…&status=…&risk=…&sort=…`.
  `src/lib/skills/library-view.ts` is the single parse/serialize pair (covered by
  `library-view.test.ts`). The Library writes it with `replaceState`, so typing
  in search does not create history entries.
- **Skill detail** — `?tab=skills&sub=skills.detail&focus=<skillId>` (plus the
  Library filters). The shell already passes `focus` through the command store,
  so `useSubroute('skills', …)` handles `detail` specially and calls `openSkill`.
  Opening a skill from the grid pushes a history entry; closing it (or pressing
  Back) returns to the Library URL and restores the filters.
- **Execution run** — `?tab=skills&sub=skills.activity&focus=<runId>`.
  `ExecutionActivity` expands and highlights that row; if the run is older than
  the 100-row list window it fetches it by id (and shows "Run not found" when it
  genuinely does not exist). The Learning Queue's "View run" pushes this URL;
  collapsing the focused row or switching tabs clears the param.

`detail` is deliberately **not** a `SKILLS_TABS` entry: it is a drill-down, not a
tab, and must never appear in the primary or sub-tab bars. Adding a real view
still means adding a `SKILLS_TABS` entry plus a `SKILLS_GROUPS` membership.

The primary tab bar stays visible while a drill-down is open, and choosing any
group closes it (the URL is replaced, not pushed). This keeps the drill-down
escapable without hunting for the Back button. Interactive toggles expose
`aria-pressed`/`aria-expanded`, the toast is a polite live region, and the
author drawer closes on Escape (`aria-modal`).

The Library supports **bulk enable/disable**: a per-card selection checkbox and
a toolbar that calls the existing `setSkillLifecycle` endpoint once per skill
(batches of five), counting successes and failures. Bulk actions are limited to
reversible transitions (enable/disable); deprecate/delete stay single-skill.

### List query contract (scale path)

`GET /skills` accepts the Library's query, so the registry never has to ship an
unbounded list:

| Param | Meaning |
| --- | --- |
| `q` | whitespace-separated terms, all required, matched against id/name/description/tags |
| `category`, `status`, `risk` | exact facet match; `all`/absent means no filter |
| `sort` | `name` (default), `status`, `risk`, `updated` |
| `limit`, `offset` | optional paging; omit `limit` for the historical "all skills" response |

Filtering and sorting run **before** paging, and the response carries the exact
envelope: `registryTotal` (before filters), `total` (filtered), `limit`,
`offset`, `hasMore`. The pure logic lives in
`python/harness/skills/listing.py` (`filter_summaries`, `sort_summaries`,
`page_summaries`) and is covered by `python/tests/test_skills_listing.py`.
`updatedAt` is included in each summary for the "Updated" sort.

The UI deliberately stays on the **client-side** path while the filtered list is
small (currently ~91 skills): filters feel instant, and there is no round-trip
per keystroke. The documented switch point is ~500 rows; above it the same
params can drive server paging without an API change. `PaginationFooter` already
shows the exact `from–to of total`, so the client view and a future server view
read the same.
