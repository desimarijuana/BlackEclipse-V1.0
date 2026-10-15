---
title: Slash Commands
status: Current
last-verified: 2026-10-14
---

# Slash Commands

**Who this is for:** anyone changing how a `/command` is defined, autocompleted,
routed, or executed in the chat surfaces.

## What this is (and why)

Eclipse's chat is chatbot-first. A leading `/` in the composer names a **slash
command**. There are two kinds, and the distinction is the whole design:

- **Profile commands** (e.g. `/eclipsesdk`) do **not** execute anything on their
  own; they force a deterministic run *profile* for the next agent turn. They are
  parsed in TS (`src/lib/harness/commands.ts`) and the runtime still enforces the
  actual grant.
- **Routed commands** (`/skills`, `/skill`, `/status`, …) are executed by the
  **shared command router** and return a rendered result immediately. They never
  open an LLM turn.

Profile commands exist because the alternative — asking a classifier to infer "is
this a coding request?" from prose — is fuzzy. The set of profile commands is
deliberately tiny.

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
5. **Execute** — dispatch on `handler.target` to a handler that calls the
   **existing** systems (`skills-client`, `tasks-client`, `workflows-client`, the
   Python runtime). The router owns no agent loop, task queue, or skill database.
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
  Profile commands and ordinary prose fall through to the normal agent path;
  unknown `/tokens` also fall through, so text that merely starts with a slash
  keeps working.
- **Direct entry** — `POST /api/harness/command` runs the same router for
  external callers/tools.

## Commands implemented today

Backed by real handlers/endpoints:

- Runtime: `/help`, `/status` (alias `/health`), `/tasks` (alias `/plans`),
  `/workflows`, `/agents`, `/models` (alias `/providers`), `/tools`,
  `/usage` (alias `/cost`).
- Markets / portfolio / memory / MCP: `/market` (gateway providers + health),
  `/portfolio` (real portfolios), `/memory` (overview + recent), `/mcp`
  (configured servers).
- Skills (Phase 4 family): `/skills` (list/search/category/show/test/validate),
  `/skill`, `/skill-explain`, `/skill-test`, `/skill-enable`, `/skill-disable`,
  `/skill-create`.
- Profile: `/eclipsesdk` (alias `/esdk`).

Registered but **not yet wired** (return an explicit unsupported error; they are
listed so discovery is complete): `research`, `deep-research`, `quote`,
`backtest`, `web`, `read`, `code`, `terminal`, `run`. Wiring one means adding a
handler and flipping its `status` to `available` — nothing else changes.
(`/terminal` and `/run` are deliberately not exposed as chat commands: shell
execution stays in the code capability under approval.)

## Skill integration

`/skill <id>` validates the skill's inputs (`validateInput`) and then calls the
existing `executeSkill`, which runs through the Python runtime's real executor
(allowlist, permissions, dependency DAG, and budget enforced in Python — the
`SKILL.md` text is prompt-delivered and can never widen authority). The registry
is never queried by the client with a guessed id: an unknown id returns
`SKILL_NOT_FOUND`, and a disabled/incompatible skill is refused by Python.

### Automatic selection during normal chat

The user does not have to remember a skill name. The Python runtime already binds
`skill_list` / `skill_view` / `skill_invoke` to the `eclipse-agent` (see
`python/harness/agents.py`), and the system prompt instructs the agent to discover
a relevant ENABLED skill and run it as a controlled sub-run when a request
matches. Discovery is metadata-only (bounded context); execution re-enforces the
skill's allowlist/permissions and links the child run to the turn. This is the
existing runtime behaviour, not a second planner — the TS side only owns the
explicit `/skill` surface.

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
- `src/lib/harness/command-router.test.ts` — unknown/invalid/unavailable/denied
  paths, `/help`, `/status`, `/skills`, `/skill` execute, operator gating,
  `/skill-create` requiring a real source.

## Known gaps / follow-ups

- The remaining planned commands need handlers; each is currently honest about
  being unavailable.
- Skills list/execute require the Python runtime; without it the command reports
  a runtime-unavailable error (never a fabricated result).
- `/terminal` and `/run` are intentionally not chat commands.
