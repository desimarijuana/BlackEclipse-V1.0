---
title: Harness Phase 1 Progress
status: Current
last-verified: 2026-09-21
---

# Harness Phase 1 — Progress

**Phase:** 1 — Harness Kernel & Execution Runtime
**Status:** Complete (revised: Python/LangGraph runtime)
**Last updated:** 2026-09-21

## What was implemented

A complete agent execution path where the **agentic runtime is Python** and
Next.js is a thin front door.

- **Agent identity (Eclipse Agent)** — the default agent is `eclipse-agent`,
  "Eclipse Agent" by Black Orbit Technologies. Its full system prompt lives in
  `python/harness/prompts.py` and is authoritative: the front door sends only an
  `agentId`, and the runtime resolves the prompt + tool allowlist from its own
  presets (ADR-H8). Verified end-to-end — a run started with `agentId` alone
  delivered the 23,687-character prompt to the model.
- **Agentic runtime (Python, `python/harness/`)** — FastAPI service;
  LangGraph `StateGraph` agent ⇄ tools loop; universal model factory
  (LangChain native integrations + all OpenAI-compatible endpoints); tool
  registry with pydantic validation, permission/risk/timeout/duplicate-call
  enforcement; financial tools (JDdS-backed, honest `UNAVAILABLE` states);
  event emitter + live bus; `agent-memory.db` persistence (runs, events, tool
  executions, agent memory, skills); agent presets authored in Python.
- **Front door (Next.js, `src/lib/harness/`)** — input validation, agent/LLM
  config resolution from the settings vault, run-id assignment, lazy Python
  sidecar launcher with health checks, typed runtime client, and the read-only
  JDdS capability bridge. **No agent loop, registry, or model adapter in TS.**
- **API** — `/api/harness/runs` (POST/GET), `/runs/[id]`,
  `/runs/[id]/events`, `/runs/[id]/cancel`, `/models`, `/agents`, and the
  guarded `/data` bridge. All mutation-guarded + rate limited where they act.
- **Setup** — `python/requirements.txt`; `scripts/setup-python.js`
  (`npm run setup:python`, also in `postinstall`); `doctor.js` repair check;
  `scripts/test-python.js` wired into `npm test`.
- **Tests** — 34 pytest tests (tools, persistence, models, graph) and 30 Vitest
  tests (front door: validation, data bridge, run service, errors, presets).

## Files created or changed

**Created — Python runtime (`python/`):**
`requirements.txt`, `conftest.py`, `pytest.ini`,
`harness/{__init__,schemas,prompts,models,agents,tools,finance_tools,events,persistence,graph,service,main}.py`,
`tests/{test_tools,test_persistence,test_models,test_graph}.py`

**Created — TS front door (`src/lib/harness/`):**
`types.ts`, `errors.ts`, `validation.ts`, `ids.ts`, `agent-presets.ts`,
`run-service.ts`, `python-runtime.ts`, `python-client.ts`, `data-bridge.ts`,
`runtime-config.ts`, `runtime-auth.ts`, `index.ts` + 5 test files.

**Created — API (`src/app/api/harness/`):**
`runs/`, `runs/[id]/`, `runs/[id]/events/`, `runs/[id]/cancel/`, `models/`,
`agents/`, `data/`.

**Changed:**
`package.json` (setup:python, test:py, test), `scripts/setup-python.js`,
`scripts/doctor.js` (new `scripts/test-python.js`), `.gitignore`, `AGENTS.md`
(agentic-runtime-is-Python rule + zero-config nuance), `docs/ARCHITECTURE.md`,
`docs/NAVIGATION.md`, `docs/DECISIONS.md`, `docs/CHANGELOG.md`.

**Retired:** the Phase-1 TypeScript kernel — `harness/types/`, `models/`,
`tools/`, `runtime/`, `events/`, `persistence/`, `agents/`, `logger.ts`, plus
their tests. Replaced by the Python runtime; the TS tests were rewritten to
cover the front door and data bridge.

## Dependencies installed and reasons

**Python** (`python/requirements.txt`): `fastapi`, `uvicorn[standard]`,
`pydantic`, `langchain`, `langchain-core`, `langgraph`, `langchain-openai`,
`langchain-anthropic`, `langchain-google-genai`, `langchain-mistralai`,
`langchain-groq`, `pytest`, `pytest-asyncio`. Reason: the agentic runtime, its
universal provider coverage, and its tests. Installed via pip (not npm).

**npm:** none added. The front door uses existing fetch/Prisma/api-guard.

## Tests and validation results

| Check | Command | Result |
|---|---|---|
| Typecheck | `npx tsc --noEmit` | Pass (0 errors) |
| Lint | `npx eslint src/lib/harness src/app/api/harness` | Pass |
| TS tests | `npx vitest run src/lib/harness` | Pass — 32 tests |
| Python tests | `npm run test:py` | Pass — 36 tests |
| Full TS suite | `npx vitest run` | Pass — 1426 tests |
| Build | `npm run build` | Pass; 7 harness routes |
| Live E2E | production server + auto-spawned runtime | Pass — `/models` served 14 providers from Python; `/data` returned real JDdS AAPL data; a run produced a completed status with a 9-event trace and a real tool execution |

## Known limitations

- **The runtime must be installed.** Without the Python stack, runs return 503.
  This is deliberate (no fake agent), but it means the agentic feature is not
  available on a machine where pip cannot reach the network.
- **Single-process, in-process cancellation.** The runtime tracks active tasks
  in memory; a cancel from another process cannot reach a run.
- **No streaming.** Events are persisted/emitted per step, but there is no SSE
  endpoint yet for live UI consumption.
- **Capability bridge is request/response.** Fine for the current read tools; a
  tool needing paginated or high-volume data would want a different shape.
- **Memory/skills are stored, not yet *used*.** Tables and repositories exist
  and are tested; prompts do not yet load recalled memory, and skills are not
  activated.
- **Provider coverage is catalog-deep, not verified-per-key.** Each provider
  builds a LangChain model; only the OpenAI-compatible path and the local
  keyless path were exercised offline.
- **Cancellation/timeout of an in-flight LangGraph node** relies on asyncio task
  cancellation; a provider that ignores cancellation may still run to its own
  timeout.

## Recommended next step for Phase 2

1. **Ground prompts in memory.** Load `store.recall()` into the system prompt
   with provenance labels before the first model call.
2. **SSE streaming.** Expose the event bus over SSE so the existing chat UI can
   render live steps without a rewrite.
3. **Approval path for write tools** (ADR-H6) — record a human confirmation as
   an event before any non-read tool can run.
4. **Verify providers with real keys.** Add a connection test per catalog entry
   (`langchain` client construction + a minimal ping) surfaced in Settings.
5. **Skill promotion loop.** Use `record_skill_outcome` reliability to promote
   `proposed` → `active`, keeping self-modification gated.
