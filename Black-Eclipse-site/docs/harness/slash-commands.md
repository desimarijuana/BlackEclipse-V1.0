---
title: Slash Commands
status: Current
last-verified: 2026-10-17
---

# Slash Commands

**Who this is for:** anyone changing how a `/command` is defined, autocompleted,
routed, or executed in the chat surfaces.

## What this is (and why)

Eclipse's chat is chatbot-first. A leading `/` in the composer names a **slash
command**. There are three kinds, and the distinction is the whole design:

- **Profile commands** (e.g. `/eclipsesdk`) do **not** execute anything on their
  own; they force a deterministic run *profile* for the next agent turn. They are
  parsed in TS (`src/lib/harness/commands.ts`) and the runtime still enforces the
  actual grant.
- **Routed commands** (`/skills`, `/status`, `/market`, …) are executed by the
  **shared command router** and return a rendered result immediately. They never
  open an LLM turn.
- **Agent-turn commands** (`/skill`, `/anatomy`, `/visual`) rewrite the chat
  query into a directive and run as a **normal agent turn**, so the chatbot does
  the work (and streaming + conversation history are preserved). `/skill <name>
  <what it should do>` tells Eclipse to author a new reusable skill; `/anatomy
  <concept>` tells it to explain the concept as an interactive **3D model** — an
  orbitable machine composed from mechanism recipes, rendered inline as a
  `model3d` block with a numbered key, stages and `.glb` export; `/visual <what
  to chart>` tells it to render ONE inline data **`chart`** block, choosing from
  the full chart-type set and plotting only real values. The rewrites live in
  `src/lib/harness/command-agent.ts`.

Profile commands exist because the alternative — asking a classifier to infer "is
this a coding request?" from prose — is fuzzy. The set of profile commands is
deliberately tiny. Agent-turn commands run under the **default** profile (no
classifier narrowing) so the write-capable `skill_create` tool stays bound.

## The contract

Everything starts from **one canonical registry**:
`src/lib/harness/command-registry.ts`.

A `CommandSpec` describes a command declaratively: stable `id`, canonical `name`,
`aliases`, `summary`/`description`, `category`, `tags`, `version`, lifecycle
`status`, typed `args`, `flags`, a `handler` `{ type, target }`, `permissions`,
`risk`, `executionMode`, timeouts/retries/idempotency, `output`, and `examples`.

Invariants the registry enforces:

- **One registry, two consumers.** The composer palette and the router both read
  the same list, so they can never disagree about what exists.
- **Only handler-backed commands are `available`.** `isCommandAvailable()` is the
  single source of truth. `status: "unavailable"` commands are still registered
  (so `/help` and the palette are honest and complete) but a routed invocation
  returns an explicit, structured **unsupported** error — never a fake success.
- **No duplicate names/aliases.** `detectRegistryConflicts()` makes a collision
  visible to tests/CI; `resolveCommand()` is first-wins.

## Parse → Resolve → Validate → Authorize → Execute → Render → Audit

The router (`src/lib/harness/command-router.ts`) is the ONE execution path for
every routed command.

1. **Parse** — `command-parser.ts`. A real tokenizer (not `split(' ')`) that
   preserves quoted strings, Unicode, filenames with spaces, and backslash
   escapes, then binds tokens to the command's declared schema. Unknown flags are
   errors unless the command opts into `passThroughFlags` (how
   `/skill --asset BTC` builds a skill's input object).
2. **Resolve** — a leading `/token` that matches no command yields an `unknown`
   result. `/usr/bin` is not a command (the token must be followed by whitespace
   or end-of-text).
3. **Validate** — missing/invalid args produce a readable usage error.
4. **Authorize** — a command declaring `approval: "operator"` is denied unless the
   caller passed the operator gate (transport/token). This is defense in depth:
   the Python runtime re-enforces its own default-deny policy.
5. **Execute** — dispatch on `handler.target` to a handler in
   `src/lib/harness/command-handlers.ts` that calls the **existing** systems
   (skills-client, tasks-client, workflows-client, python-client, and loopback
   calls to the app's own `/api/...` front doors). The router owns no agent loop,
   task queue, or skill database.
6. **Render** — build validated `eclipse-response` blocks (`command-render.ts`);
   each block is checked against `src/lib/response/contract.ts` before it is
   emitted.
7. **Audit** — a structured, redacted audit event (command id, actor, operator,
   status, handler target, skill/run id, duration) is logged.

Handlers are injected through `CommandDeps`, so the router is fully
unit-testable without a live runtime.

## Where it is wired

- **Composer palette** — `src/components/chat/chat-input.tsx` renders
  `searchCommands()` results (category, argument hint, availability) with
  keyboard navigation. Typing `/` never executes; selection only inserts
  `/name `.
- **Chat surfaces** — both `/api/harness/chat` and `/api/harness/chat/stream`
  intercept a routed command *before* starting an agent run. The stream route
  emits a synthetic `client.run` / `client.final` / `stream.end` sequence, so the
  existing chat UI and renderer handle a command result with no special casing.
  Profile commands, agent-turn commands, and ordinary prose fall through to the
  normal agent path; unknown `/tokens` also fall through, so text that merely
  starts with a slash keeps working.
- **Direct entry** — `POST /api/harness/command` runs the same router for routed
  commands and the chat path for agent-turn commands.

## Commands implemented today

Backed by real handlers/endpoints:

- Runtime: `/help`, `/status` (alias `/health`), `/tasks` (alias `/plans`),
  `/workflows`, `/agents`, `/models` (alias `/providers`), `/tools`,
  `/usage` (alias `/cost`).
- Markets / portfolio / memory / MCP: `/market` (gateway providers + health),
  `/quote` (`/quotes` — JDdS quotes with honest freshness), `/portfolio` (real
  portfolios), `/memory` (overview + recent), `/mcp` (configured servers).
- Research / web: `/research`, `/deep-research` (alias `/deep`), `/web`
  (alias `/browse`), `/read` (alias `/summarize`) — all through the web research
  engine, returning the answer with its sources.
- Quant: `/backtest` — lists saved strategies, or backtests one by id.
- Dev: `/code` (start a code task), `/terminal` (aliases `/run`, `/sh` — run a
  shell command; operator- and effect-gated).
- Visual: `/anatomy` (aliases `/visualize`, `/mechanism`) — explain a concept as
  an interactive **3D model** (an orbitable `model3d` block with labelled parts,
  mechanism recipes and step-through stages); an agent-turn command that authors a
  declarative scene and never writes meshes or code (see
  `docs/interactive-response-engine.md`, "3D mechanism models").
- Visual: `/visual` (aliases `/chart`, `/plot`) — render a request as ONE inline
  data **`chart`** block. Eclipse picks the best of the sixteen chart types
  (line, area, bar, stacked_bar, grouped_bar, pie, scatter, bubble, histogram,
  heatmap, treemap, sunburst, funnel, gauge, radar, waterfall) and plots only
  real values it can source — never an invented curve. Agent-turn; see
  `docs/interactive-response-engine.md`, "Chart & diagram presentation".
- Skills: `/skills` (list/search/category/show/**run**/test/validate),
  `/skill` (**author a new skill** — agent turn), `/skill-explain`, `/skill-test`,
  `/skill-enable`, `/skill-disable`, `/skill-create` (learning-engine draft).
- Profile: `/app` (control the Eclipse app through the typed SDK; alias
  `/eclipse`) and `/eclipsesdk` (edit Eclipse's own source code; alias `/esdk`).
- Agent-turn: `/skill` (authors a skill for Eclipse; see Skill integration).

Every registered command has a real handler (the palette `soon` badge is gone).
Commands that call a subsystem (research, quant, code, terminal, quotes) reuse
the **same front-door APIs the UI uses** — the router makes a loopback call to
`/api/...`, so a command never re-implements an engine. `/terminal` requires the
operator gate; a non-operator is refused before anything runs.

## Skill integration

### Run a skill — `/skills run <id>`

Resolves the skill against the authoritative registry and calls the existing
`executeSkill`, which runs through the Python runtime's real executor (allowlist,
permissions, dependency DAG, and budget enforced in Python — the `SKILL.md` text
is prompt-delivered and can never widen authority). An unknown id returns
`SKILL_NOT_FOUND`; a disabled/incompatible skill is refused by Python.

### Author a skill — `/skill <name> <what it should do>`

Typing `/skill …` tells Eclipse to **make a skill for itself**. It is an
agent-turn command: the query is rewritten (`command-agent.ts`) into an authoring
directive, and the normal chat turn runs. The chatbot generates the skill (a
one-line description, concise steps, minimal tools/permissions, input schema) and
persists it with the existing `skill_create` tool — so it lands in the Python
skill library and **appears on the Skills page** (`src/components/screens/skills/`)
where the user can view, edit, enable, evaluate, or run it. Creation is gated by a
single-use operator approval (an approval card in the streaming chat), and the
agent is told never to claim a skill was created unless the tool result confirms
it. `/skill-create` remains available for the deterministic learning-engine path
(`--from-task`, `--from-workflow`, `--objective`).

### Automatic selection during normal chat

The user does not have to remember a skill name. The Python runtime already binds
`skill_list` / `skill_view` / `skill_invoke` to the `eclipse-agent` (see
`python/harness/agents.py`), and the system prompt instructs the agent to discover
a relevant ENABLED skill and run it as a controlled sub-run when a request
matches. Discovery is metadata-only (bounded context); execution re-enforces the
skill's allowlist/permissions and links the child run to the turn. This is the
existing runtime behaviour, not a second planner — the TS side only owns the
explicit command surfaces.

## Security notes

- Agent-generated text, skill descriptions, and user input are treated as
  untrusted data — the router does not evaluate them.
- Operator-only commands are gated at the front door AND re-enforced in Python.
- Command output is redacted (`redactSecrets`) before it is returned.
- The router cannot enable live trading or external side effects by adding a
  command; a handler still goes through the same authorization path as any tool.

## Tests

- `src/lib/harness/command-registry.test.ts` — resolution, aliases, conflicts,
  availability, search, argument hints.
- `src/lib/harness/command-parser.test.ts` — quoting, escapes, Unicode, enum and
  required-arg validation, pass-through flags.
- `src/lib/harness/command-agent.test.ts` — `/skill` rewrites into a skill-authoring
  directive, `/anatomy` into a 3D-model (`model3d`) directive, and `/visual` into a
  `chart` directive; non-agent commands and prose return null.
- `src/lib/harness/command-router.test.ts` — unknown/invalid/unavailable/denied
  paths, `/help`, `/status`, `/skills`, `/skills run`, operator gating,
  `/skill-create` requiring a real source.
- `src/app/api/harness/command/route.test.ts` — the direct route, including the
  agent-turn path.

## Known gaps / follow-ups

- `/skills`, `/research`, `/backtest`, `/code`, `/terminal`, `/market`,
  `/portfolio`, `/memory`, `/mcp` require the Python runtime up; without it they
  report a clean runtime-unavailable error (never a fabricated result).
- `/quote` reads JDdS directly (no runtime needed) and labels a stale price as
  stale.
- The direct `POST /api/harness/command` path runs `/skill` non-streaming, so the
  `skill_create` approval is deny-and-retry there; use the chat surfaces for the
  approval-card flow.
- `command-handlers.ts` is the largest module in the family (~860 lines); the next
  extraction candidate is the per-domain renderers (research/quant/dev).
- **Mentions (`@`).** The `@` sibling — naming a bot or group chat so the main
  chat delegates the turn to it — is a separate surface documented in
  `docs/harness/mentions.md`.
