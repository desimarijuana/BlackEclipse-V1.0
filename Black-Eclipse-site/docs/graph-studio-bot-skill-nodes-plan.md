---
title: Graph Studio — Bot, Skill and Agent Node Plan
status: Proposed
last-verified: 2026-11-01
---

# Bot, skill and agent node plan

**Scope:** what to add beyond the three existing agent nodes
(`agent.research`, `agent.plan`, `agent.delegate`); how a **saved bot** becomes
selectable (in Bots mode and as a graph node); how an installed **skill** becomes
a graph node.

**What this document is:** an implementation-ready plan — current inventory,
node contracts, the three bot-selectable surfaces, the skill execution sequence,
work breakdown, compatibility notes.

**What it is not:** a decision record. Items marked **DECISION** need an answer
before a ticket starts; accepted answers become an ADR in `skills/ARCHITECT.md`
plus a section in `docs/graph-studio.md`.

---

## 0. Current inventory (verified against the tree)

### Nodes

One declared catalog, rendered as a manifest and mirrored 1:1 by Python:

| Layer | File |
| --- | --- |
| TS contracts | `src/lib/graph-studio/registry.ts` + `registry-agents.ts` / `-market` / `-transform` / `-loops` / `-integration` / `-trading` / `-write` / `-quant-structure` |
| Presentation | `src/lib/graph-studio/config-fields.ts`, `node-ports.ts`, `node-examples.ts` |
| Manifest + parity | `src/lib/graph-studio/registry.manifest.json` (`npm run graph:manifest`), asserted by `registry.test.ts` and the Python registry tests |
| Runtime | `python/harness/graph_runtime/nodes.py` (`build_default_registry`) + one `*_nodes.py` per pack |
| Executor | `python/harness/graph_runtime/executor.py` → `_invoke` → `definition.executor(context)` |
| Boot wiring | `python/harness/graph_runtime/bootstrap.py` injects runners (`set_agent_runner`, `set_plan_runner`, …) |

The three agent nodes are declared in `registry-agents.ts` and implemented in
`agent_nodes.py`; both are thin adapters over the **existing** agent plane
(`AgenticService.run`), and `bootstrap._agent_runner` resolves either a built-in
agent or an `AgentPreset` (version-pinned). There is no second agent loop.

### Bots

A bot is an **Automation tagged `bot`** (or `monitor`, or id prefix `mon_`) — no
`Bot` model, no Prisma table. Storage is the `Automation*` tables on
`agent-memory.db` (`python/harness/automation/store.py`), read through
`/api/automations` (`src/lib/harness/automation-client.ts`, `listAutomations`).

Two gaps relevant to this plan:

1. **The create/edit dialog does not show real agents.** `create-bot-dialog.tsx`
   renders a static `BOT_AGENTS` array from `src/lib/bots/state.ts`
   (lines ~348-361). User presets from Settings › Agents are invisible there —
   even though the graph inspector already loads them correctly
   (`node-inspector.tsx` ~line 195: `listAgentPresets()` + `listBuiltInAgents()`).
2. **There is no "start from an existing bot" affordance.** Bots mode lists and
   opens bots, and `src/lib/bots/duplicate.ts` can clone one, but the create flow
   always starts from `emptyBotDraft()`.

### Skills

Skills live in `python/harness/skills/` and execute through `execute_skill`
(one runtime, permissions = default deny, allowlisted tools). Two existing entry
points matter here:

- `AgenticService.run_skill(SkillExecutionRequest)` (`service.py` ~1683) — the
  ready-made adapter a graph node should call.
- Automation `execute_task` with `skill_id` (`automation/dispatcher.py` `_run_skill`).

**There is currently zero `skill` reference in either node registry** — skills
cannot be placed on a canvas. `SkillExecutionRequest.executionMode` already has
a `"workflow"` value, and `list_invocable_skills()` / `listSkills()` already
return the metadata a picker needs.

---

## 1. Decisions to settle first

| # | Decision | Recommendation |
| --- | --- | --- |
| D1 | What `agent.bot` does with a **workflow** bot | Run the bot's agent turn; for a workflow bot, fail honestly and point at `flow.subworkflow`. Running a workflow *inside* a graph run nests scheduler runs and is not worth it. |
| D2 | Skill node capability | Reuse `agent.run` (a skill call is a model call on the agent plane, already narrowed for test runs). Adding `skill.run` is honest but touches grants, `TEST_RUN_CAPABILITIES`, `run-authorization.ts` and the consent UI for no additional safety. |
| D3 | Category for the skill node | New `skills` category in `NodeCategory` + one `CATEGORY_LABELS` entry. Cost: one union member. Benefit: "Skills" is its own library group, which is what was asked for. |
| D4 | New port types | None. Reuse `string` / `object` / `array`. A `skill_result` port type would touch TS `PortType`, Python `PortType`, `ports_compatible`, the manifest and every saved IR. |
| D5 | A bot's per-run model override inside a graph run | Ignore it. The run's resolved model settings win (credentials are front-door-resolved and in-memory only). Document it in the node docs string. |
| D6 | One `agent.*` node per verb vs one configurable node | One per verb. Each verb has a different prompt contract, different ports, and a different failure shape; folding them into one node makes the inspector a mode switch. |

---

## 2. Tier 1 — ship first (6 nodes)

All six are adapters: no new loop, no new store, no new scheduler. Every one is
added to **both** registries at `1.0.0` (additive; saved graphs are unaffected).

| Node | Purpose | Inputs | Outputs | Config | Capability / effect |
| --- | --- | --- | --- | --- | --- |
| `agent.bot` | Run a **saved bot** as one bounded turn | `query` (string, opt), `context` (object, opt) | `finding`, `evidence` | `botId`, `agentVersion` (0 = latest), `objective` (prefix, opt), `maxSteps` | `agent.run` / `model` |
| `skill.invoke` | Run an installed **skill** | `input` (object, opt) | `output` (string), `result` (object), `evidence` (array) | `skillId`, `version` ('' = latest), `inputJson`, `timeoutMs` | `agent.run` / `model` (D2) |
| `agent.classify` | One label from a fixed set; pairs with `logic.switch` | `text` (string) | `label` (string), `confidence` (number), `scores` (object) | `labels` (comma list), `instructions`, `agent`, `maxSteps` | `agent.run` / `model` |
| `agent.extract` | Structured extraction to a declared JSON shape | `text` (string), `schema` (object, opt) | `data` (object), `raw` (string), `valid` (boolean) | `schemaJson`, `instructions`, `agent`, `maxSteps` | `agent.run` / `model` |
| `agent.summarize` | Compress a long text/array for the next node | `text` (string or array) | `summary` (string), `keyPoints` (array) | `maxWords`, `style` (`bullets`\|`prose`), `agent`, `maxSteps` | `agent.run` / `model` |
| `agent.critique` | Review a finding against its evidence; never edits it | `finding` (research_finding), `evidence` (evidence, opt), `rubric` (string, opt) | `verdict` (`supported`\|`weak`\|`contradicted`), `issues` (array), `score` (number) | `rubric`, `agent`, `maxSteps` | `agent.run` / `model` |

Notes that keep these honest:

- `maxSteps` keeps the existing bound (1-32). Timeout: 600 s for `agent.*`,
  900 s for `skill.invoke` (skills may run dependencies).
- `agent.extract` **validates** `data` against `schemaJson` and reports
  `valid: false` rather than pretending the model answered the shape.
- `agent.critique` must return `verdict` only from the declared set; a model
  answer outside it fails the node instead of being coerced to `weak`.
- `agent.summarize` must not fabricate: when the input is empty it fails by name.

### 2a. `agent.bot` execution

```
node inputs/config
  → automation_store().get(botId)
  → assert bot is a bot automation (tags contain bot/monitor, or id starts mon_)
  → if action.type == "run_agent": run one bounded turn with action.agentId
  → else (execute_workflow): fail with "this bot runs a workflow; use flow.subworkflow"
  → return agent_result_payload(result)   # the existing projection
```

It reuses `bootstrap._agent_runner`, so resume/checkpoint, dry-run narrowing and
`agent_result_payload` all behave exactly as `agent.research` does. It **never**
registers a trigger and **never** runs the bot's schedule.

### 2b. `skill.invoke` execution

```
node inputs/config
  → merge inputJson ← (input port overrides individual keys)
  → inject _skill_runner at boot:
       asyncio.run(service.run_skill(SkillExecutionRequest(
         skillId, version or None, input=merged,
         runId=f"graph:{run_id}:{node_id}",
         executionMode="workflow",
         operator=<run is an operator run>,
         grants=<run's granted capabilities>,
         userId, modelSettings=context.model_settings,
         callbackBaseUrl, callbackToken, timeoutMs)))
  → status mapping:
       completed                     → outputs
       failed / denied / blocked /
       cancelled / unavailable       → raise ValueError(code + message)
```

Status mapping is the whole contract: **a skill that is not enabled, is missing
a tool, or is denied permission fails the node.** It never returns an empty
success.

Small prerequisite: `NodeExecContext` (registry.py) needs two fields —
`operator: bool = False` and `granted_capabilities: frozenset[str] = frozenset()`
— filled by `executor._invoke` from `self._grants`. Without them the skill actor
is constructed from guesses.

Input schema: the node stays one generic type. The inspector fetches the chosen
skill's `inputSchema` (already on `listSkills`) and renders the JSON editor plus
a read-only field summary; runtime validation stays in `execute_skill`, which
already rejects a bad payload with a named error.

---

## 3. Tier 2 — next wave (candidates, each independent)

| Node | Why | Effort |
| --- | --- | --- |
| `agent.team` | Wrap the institution team runtime (`team` service, `build_team`) into a committee decision node. Terminal decision only, never an order. | M-L (async wait, bounded runtime budget) |
| `memory.recall` | Read Eclipse memory (`memory.search` tools already exist) into the graph as evidence. | M (verify the graph-safe entry point) |
| `memory.remember` | Write a durable note from a run. Needs a new effect class; default-deny. | M |
| `logic.assert` | Fail the run with a named message when a condition is false. Governance primitive for unattended runs. | S |
| `logic.fallback` | First non-empty value wins across N wired inputs. Pure, replaces stacked `logic.merge` + `condition`. | S |
| `output.notify` | Delivery via the existing `DeliveryPolicy` adapters (`in_app`/`artifact`/`messaging`). | S-M |
| `output.chart` | Turn a series into a chart artifact using the existing chart tools. | M |
| `data.extract` | Dotted-path / index extraction from an object, replacing a `transform.formula` dance. | S |
| `research.source_rank` | Rank evidence items by source quality + freshness (pure, local). | S-M |
| `quant.regime` / `quant.align` / `quant.position_size` | **Already shipped** (`registry-quant-structure.ts`, `quant_structure_nodes.py`). Do not re-plan. | — |

Tier 2 order matters less than Tier 1, but `logic.assert` and `logic.fallback`
are cheap and unlock better unattended graphs, so they are the best next pair.

## 4. Tier 3 — needs runtime work, keep separate

| Item | Blocker |
| --- | --- |
| `flow.parallel` | `executor.py` schedules layers sequentially; a bounded fan-out needs a concurrency budget in the plan and in `RunGrants`. Do not bolt threads onto a node. |
| `logic.human_approval` | Needs durable pause/resume plus the approvals plane (`service.approvals`). High value for live trading, but it is a project, not a node. |
| `output.video` | `video.render` exists; a second video node adds nothing. |

## 5. Rejected

- **One node type per installed skill.** Skills are runtime data; the registry is
  a static contract with a generated manifest and Python parity. Per-skill nodes
  would make the manifest depend on disk state and churn on every install.
  (Rejected in favour of one `skill.invoke` with a dynamic picker.)
- **`agent.synthesize` / `agent.report`.** `research.report` already produces the
  deterministic report; a second model-written report is a duplicate surface.
- **`agent.tool` (arbitrary tool call).** Expands the effect surface with no
  contract, and `integration.http` + the typed nodes already cover the real cases.

---

## 6. Making saved bots selectable — three surfaces

### B1. Create/edit bot: show real agents (bug-level fix, do first)

`src/components/bots/create-bot-dialog.tsx` + `src/lib/bots/state.ts`:

- Load `listAgentPresets()` and `listBuiltInAgents()` (same pattern as
  `node-inspector.tsx`), merge with the built-in defaults, and render them in the
  Brain › Agent picker.
- `BOT_AGENTS` stays only as the offline fallback while the request is in flight
  or fails — never as the list.
- If an existing bot points at a preset that is now archived/missing, still show
  and preserve it (labelled "archived") so editing cannot silently retarget it.
- Validate on save: an unknown `agentId` is a field error, not a silent default.

### B2. Bots mode: start from an existing bot

In the Bots screen, add a **"Reuse a bot"** entry point next to "New bot":

- Picker lists existing bots (`listAutomations` filtered by `isBotAutomation`)
  with name, objective, brain (agent/workflow) and schedule.
- Selecting one opens the create dialog pre-filled from that bot's definition
  (reuse the mapping already in `src/lib/bots/duplicate.ts`; do not hand-roll a
  second copy), with the name suffixed so the original is untouched.
- The original bot keeps its own schedule; the clone is created **disabled** if
  its trigger is scheduled, so two bots never fire at the same minute by accident.

### B3. Graph Studio: an `agent.bot` node with a bot picker

- `node-inspector.tsx` gets the same "load options" effect it already has for
  datasets, broker connections and agent presets: when
  `node.type === 'agent.bot'`, load bots and render a picker over `config.botId`.
- The picker shows the brain badge (agent vs workflow). Inert workflow bots are
  shown disabled with the reason (D1), not hidden — a user should see that the
  bot exists and why it cannot be used here.
- Because the node stores only `botId`, renaming a bot does not break the graph;
  deleting one makes the node fail by name at run time.

### B4. Optional: "Open in Graph Studio"

From a bot detail view, scaffold a new workflow containing `agent.bot`
(pre-selected) or `agent.research` (pre-filled with that bot's agent/objective).
Nice, small, and it makes the two surfaces feel like one product. Not required
for the first cut.

---

## 7. Work breakdown

Each milestone is independently shippable and testable.

| Milestone | Deliverable | Files |
| --- | --- | --- |
| **M1** | Bots show real agent presets (B1) | `create-bot-dialog.tsx`, `lib/bots/state.ts`, maybe a shared `useAgentChoices` hook reused by the inspector |
| **M2** | `skill.invoke` end to end (node + picker + runner) | `registry-skills.ts` (new), `registry.ts`, `config-fields.ts`, `types.ts` (category), `node-inspector.tsx`, `graph_runtime/skill_nodes.py` (new), `nodes.py`, `registry.py` (context fields), `executor.py`, `bootstrap.py`, manifest + tests |
| **M3** | `agent.bot` + B2/B3 pickers | `registry-agents.ts`, `agent_nodes.py`, `bootstrap.py`, `node-inspector.tsx`, `bots-screen.tsx` / `bots-sidebar-panel.tsx`, `lib/bots/duplicate.ts` reuse |
| **M4** | `agent.classify` + `agent.extract` | `registry-agents.ts`, `agent_nodes.py` (+ a small prompt/parse helper shared with `agent_plan.py`), `config-fields.ts` |
| **M5** | `agent.summarize` + `agent.critique` | same files as M4 |
| **M6+** | Tier 2 pairs as capacity allows | per-node |

### Test plan (every node)

- **TS:** registry test extension — type/version uniqueness, declared config
  keys have presentation entries, manifest regenerated.
- **Python:** a fake runner test per node (success, one honest failure, bounds),
  plus a parity assertion that the Python registry matches the manifest.
- **`skill.invoke` specifically:** completed → outputs; `blocked`/`denied` →
  node failure carrying the code; missing skill id → failure naming the id;
  input port overriding `inputJson` keys.
- **`agent.bot` specifically:** agent bot → one turn; workflow bot → named
  failure; unknown/deleted bot → named failure; no schedule/trigger side effect.
- **B1/B2/B3:** picker shows presets and bots; archived preset preserved; clone
  of a scheduled bot is created disabled.

Run `npm run test` and `npx tsc --noEmit` from `Black-Eclipse-site/` after each
milestone.

---

## 8. Compatibility, risks, invariants

- **Additive only.** New node types at `1.0.0`; no IR migration, no change to
  saved workflows. The manifest must be regenerated (`npm run graph:manifest`)
  or the parity test fails.
- **No second execution plane.** `agent.bot` → agent turn; `skill.invoke` →
  `run_skill`. Neither touches the automation scheduler, and neither runs a
  workflow inline (D1).
- **Test runs stay safe.** `agent.run` is already in `TEST_RUN_CAPABILITIES` and
  the agent runner narrows the tool surface; a test run therefore cannot reach
  web/write/trade through a bot or skill node either. A skill that asks for a
  denied permission fails — it does not silently downgrade.
- **Credentials stay in memory.** Both nodes read `context.model_settings`; no key
  reaches the durable Fabric payload.
- **Timeouts are declared** (`NodeDef.timeout_ms`), so a slow model or skill
  cannot hold a worker indefinitely.
- **Bots are not nodes.** `agent.bot` references a bot by id; the bot's trigger,
  policies and schedule remain owned by the automation plane.

---

## 9. Documentation obligation on ship

- `docs/graph-studio.md` — the node catalog section (new types, ports, semantics).
- `docs/harness/bot-team-orchestration.md` or `docs/harness/automation-engine.md`
  — bot selection surfacing, if the create/clone behaviour changes (it does, B2).
- `docs/NAVIGATION.md` — this plan's trigger row, then update it to point at the
  shipped contracts.
- `docs/CHANGELOG.md` — one entry per milestone.
