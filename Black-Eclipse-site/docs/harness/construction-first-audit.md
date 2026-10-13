---
title: Construction-First Audit — ground truth and repo-mapped phase plan
status: Current
last-verified: 2026-10-12
---

# Construction-First Audit — ground truth and repo-mapped phase plan

**Who this is for:** anyone implementing (or reviewing) the "construction-first"
program — Eclipse must solve the task (build the tool, scrape the data, run the
code, fix the visual) instead of reporting that it cannot.

**What this is:** Phase 0 of that program, run as a **read-only audit** of the
actual execution paths. It maps the master plan (Phases 0–10) onto the real
files and phases of this repository, verifies every root cause against code, and
records the baseline. It does not edit code and does not re-plan what is already
built.

**Method.** Six independent audits (front door/routing, registry/allowlists,
execution substrate, acquisition/retrieval, recovery/permissions/evals,
response/rendering/artifacts), each tracing behaviour to `file:line`; then the
full release gate was run. Where the audit contradicts an existing record, the
contradiction is named in §5 — the code wins (`AGENTS.md`).

---

## 1. Baseline — measured 2026-10-12, not recalled

| Gate | Command | Result |
|---|---|---|
| Typecheck | `npx tsc --noEmit` | **exit 0** |
| Front-end tests | `npx vitest run` | **259 files / 2749 tests pass** (23 s) |
| Python suite | `node scripts/test-python.js` | **5780 passed, 16 skipped, 0 failed** (11 min 59 s) |
| Eval gates | `node scripts/test-evals.js` | **ALL PASS** — contradiction, compaction, code-verify, code tasks+safety (S1–S11), search, route_health, workflow, resume, capability_matrix, agent-evaluation (`tasks=31`, `task_success=1.0`, `hallucination_rate=0.0`, `safety_score=1.0`) |

Skipped (16, all opt-in live suites): provider live IT, CUA apps, Xvfb, git
provider live, market live, search live, vision live — plus one "no C compiler
installed". These are honest opt-outs, not failures, and Phase 10's live
scenarios must not be confused with them.

**Baseline read.** Nothing is broken at the gate level. The complaints are about
*what the agent does when a route is missing*, and the current benchmark does not
contain a single fixture for "source absent → construct one" (§6, R3-08).

---

## 2. As-built architecture map

### 2.1 Lifecycle of one chat turn

```
UI composer  src/lib/agent/use-agent-run.ts:210-247
  -> POST /api/harness/chat/stream          src/app/api/harness/chat/stream/route.ts:23-96
  -> startChatRun                           src/lib/harness/run-service.ts:214-281
       resolveChatCodeProfile(query) -> POST /code/intent   (code-client.ts:257-267)
       autonomy = code_change ? "edit_verify" : code_question ? "plan_only" : none
       analysisEnabled = (code_change)      src/lib/harness/chat-capability.ts:36-48
  -> POST /runs?background=true             src/lib/harness/python-client.ts:120-126
  -> AgenticService.run_background          python/harness/service.py:1386-1415
  -> execute_run                            python/harness/graph.py:1027-1330
       resolve_surface -> effective_allowlist | chat_code_allowlist
                                            graph.py:230-357, 1186-1188
       LangGraph loop: agent <-> tools      graph.py:597-1030
       registry.execute(name, allowed=...)  graph.py:865-867; tools.py:468-469
  -> SSE /runs/{id}/stream                  main.py:522-557
```

Intent classification is deterministic and lexical:
`python/harness/code/request_intent.py` — verdicts `code_change` |
`code_question` | `not_code` (`:23`), default **`not_code`** on ambiguity
(`:292-296`, docstring `:8-11`: "the refusal path is the safe failure").

### 2.2 The surface gate (this is where the refusals are born)

| Verdict | autonomy | Agent | analysisEnabled | Surface |
|---|---|---|---|---|
| `not_code` (default) | none sent | `eclipse-agent` | false | `ECLIPSE_AGENT.tools` — finance/retrieval/web/browser/computer/vision/document/UI + `analysis_run` + `scaffold_kit`. **No code, filesystem, terminal, git or execution tool** (`agents.py:270-435`) |
| `code_question` | `plan_only` | `eclipse-agent` | false | `allowed_tools("plan_only", CHAT_CODE_TOOLS)` — read-only; every write/execute group removed (`code/policy.py:614-638`) |
| `code_change` | `edit_verify` | `eclipse-agent` | true | `CHAT_CODE_TOOLS` + `edit_verify` narrowing; external actions still removed (`agents.py:656-764`) |

Two enforcement points: only allowlisted schemas are bound (`graph.py:465-466`)
and execution re-checks the allowlist (`graph.py:866`). Fail-closed: unknown
autonomy → plan_only bans (`policy.py:636-637`).

### 2.3 Execution substrate (as built)

- One primitive: local OS subprocess, `shell=False`, process-tree kill
  (Job Object / process group), env scrub, wall-clock and 4 MB output cap —
  `python/harness/code/sandbox.py:36, 224, 244, 354-533`.
- **`RunSpec.network` is declarative and has no consumer** — no netns,
  firewall or proxy enforces it (`sandbox.py:58, 98`).
- Analysis sandbox: vendored Python, AST import guard (17 modules:
  math…pandas; `code/execution.py:47-51`), temp staging dir, artifact
  collection. **No memory/process limits are passed** (`execution.py:409-413`;
  `DEFAULT_MEMORY_MB` unused).
- A hardened `DockerSandbox` exists (`security/sandbox.py:192-266`) but
  **`.execute()` is never called anywhere**; egress engine
  (`security/network.py:127-193`) is decision-only (operator route only).
- Interactive shells inherit the full `os.environ` (`terminal/session.py:168-171`;
  redaction note `terminal/redaction.py:5-7`).
- Execution Fabric runs through the same local sandbox; it adds adapters,
  build/test engines, diagnostics and artifact collection — not isolation.

### 2.4 Acquisition ladder (as built)

`AUTHORITY` in `retrieval/authority.py:56-114` defines ordered candidates per
data type; `planner.plan_retrieval` adapts it (`retrieval/planner.py:68-143`).
Price-shaped types are `arbitrated` (all candidates run, then decide);
statements/earnings/news are `single_best` → **first OK wins**
(`retrieval/layer.py:292-357`). All-fail produces `UNAVAILABLE`
(`layer.py:276-286, 359-372, 443-468, 555-560`). Budget defaults
`4 searches / 8 fetches / 6 pages / 90 s` (`research/budget.py:24-28`).

Providers implemented: JDDS (vault), LIVE_STRUCTURED, SEC, WEB, CRYPTO.
Catalogued but **not implemented**: FMP, POLYGON, FINNHUB, ALPHAVANTAGE,
COINGECKO, COINMARKETCAP (`retrieval/registry.py:318-376`).

The TS scraper chain (`src/lib/scraper/fetchers/**`) is reachable from Python
**only through fixed bridge capabilities** (`data-bridge.ts:11-13, 398-474`);
there is no generic "fetch/scrape this" capability and no Python-side scraper
(architecture forbids Python opening its own transport:
`retrieval/web.py:10-12`).

### 2.5 Recovery (as built)

- 21 `FailureKind`s, 15 strategies, recurrence signatures, diagnosis,
  envelope, durable incidents (`python/harness/recovery/**`).
- Wired into **task runs** (`tasks/bootstrap.py:238-245` →
  `recovery/execution.py:103-167`), and to the event bus
  (`recovery/bootstrap.py:84-136`).
- **But in production only `retry` / `rate_limit_backoff` auto-execute**
  (`executor.py:42`); every repair strategy returns
  `strategy_requires_caller` because no handlers are passed.
- `max_total_ms` is parsed but never enforced; the delegation cap is inert;
  recovery approvals are **not single-use** (`recovery/store.py:281-310`);
  `compensate` and `rollback` are unreachable; reproducer registry is empty;
  capability acquisition is an advisory plan only (`discovery.py:192-214`).
- **Chat runs are not driven through recovery at all** — only the task executor
  is (`recovery/execution.py`; `graph.py` has no recovery loop).

### 2.6 Response, visual and artifact pipeline (as built)

- The `eclipse-response` contract is robust: zod envelope + per-block
  validation + aliases (`src/lib/response/contract.ts:1091-1371`); every block
  is wrapped in an error boundary (`response-view.tsx:180-206, 250-274`); a
  malformed fence degrades to an inline card, not a dead message
  (`parse.ts:41-108`; `response-fence.tsx:41-49`).
- **Every diagnostic — error or non-fatal warning — renders a persistent amber
  DiagnosticsPanel under the answer** (`response-view.tsx:293-295`;
  `blocks.tsx:352-369`). This plus honest `UNAVAILABLE` chips is the most likely
  source of "visual replies that always show some sort of error".
- Artifacts are end-to-end: content-addressed store, catalog, download route,
  retention (`python/harness/artifacts/**`; `routers/artifacts.py:101-389`;
  `src/app/api/artifacts/[[...path]]/route.ts`).
- **But `analysis_run`'s structured payload never reaches the client** — only
  the tool text does (`graph.py:924`); `analysis.completed` has no UI mapping;
  `ComputedResultPanel` is dead code (no importers); a chat download link
  requires the model to emit an `artifact` block with an `artifactId` it does
  not normally hold.

---

## 3. Capability inventory

Legend: **R** = registered; **Chat** = reachable from the default finance chat;
**Ctx** = reachable only under a code autonomy (`code_change`); **—** = absent.

| Family | R | Chat | Ctx | Notes / evidence |
|---|---|---|---|---|
| Finance / retrieval / market / macro | ✅ | ✅ | ✅ | `agents.py:274-312`; AUTHORITY ladder |
| Web research, search, learning | ✅ | ✅ | ✅ | `agents.py:160-210, 385` |
| Quant / stats / factors / portfolio / ML | ✅ | ✅ | ✅ | `agents.py:311-339`; **streaming path passes no bundles → StoreUnavailable** (§4 RC-7) |
| Memory / skills / session / tasks / a2a / bots | ✅ | ✅ | ✅ | `agents.py:352-381` |
| UI engineering (`ui_*`) | ✅ | ✅ | ✅ | `agents.py:434`; prompt §"Pages, widgets and tools" |
| Browser / computer / vision / document | ✅ | ✅ | ✅ | effect-gated per call |
| **Code execution / filesystem write / terminal / git / app runtime** | ✅ | ❌ | ✅ | ~78 code+FS+intel, 25 terminal, 21 execution, 103 app-runtime, 115 git tools — invisible without a code autonomy |
| `analysis_run` | ✅ | visible | ✅ | **always refused unless `analysisEnabled`** (`analysis_tools.py:157-159`); only `code_change` sets it |
| `scaffold_kit` | ✅ | visible | ✅ | requires workspace-bound `code.write` — a chat turn has `workspaceId=None` (verify at runtime) |
| Recovery tools (`recovery_*`) | ✅ | ❌ | ❌ | registered `recovery/tools.py:129-200`; in no allowlist |
| Artifact tools (`artifact_*`) | ✅ | ❌ | ❌ | registered `artifacts/tools.py:262-284`; in no allowlist |
| Orchestration (`parallel_execute`, …) / Fabric (`fabric_*`) | ✅ | ❌ | ❌ | registered but in no allowlist |
| `get_world_events`, `search_context` | ✅ | ❌ | ❌ | registered; missing from every allowlist |
| Generic scrape/collect tool | — | — | — | none exists; nearest are `browser_extract` / `web_extract` / `structured_extract` |

Registered native tools ≈ **886**; the invisible set is real capability that
exists but cannot be reached (§6, R3-07; master plan Phase 2 rule 4).

---

## 4. Root-cause analysis — the reported failures, traced

**RC-1 — The classifier sends "get/clean/scrape/extract" turns to the wrong
path.** `scrape`, `clean`, `csv`, `data`, `site` are absent from
`_DIRECTIVE_VERBS`/`_SOFTWARE_OBJECTS` (`request_intent.py:27-64`), and verb and
object must share a clause after splitting on `and` (`:114, 151-163`). Traced:

| Message | Verdict | Consequence |
|---|---|---|
| "scrape this site and give me the data as CSV" | `not_code` | no code profile; no exec; model answers UNAVAILABLE |
| "clean this CSV file for me" | `not_code` | same |
| "build me a small app that tracks my portfolio" | `code_change` | works (edit_verify + analysis) |
| "get BTC history and run a Monte Carlo" | `not_code` | no analysis; and quant tool would fail on the streaming path anyway |

**RC-2 — The agent cannot see the tools that would do the job.** The default
allowlist contains no code/terminal/write tool (`agents.py:270-435`, verified
absent). Prompt doctrine agrees: "never claim arbitrary filesystem, shell, code
execution access… a missing tool is a routing problem" and "UNAVAILABLE plus the
routes you tried is a complete answer" (`prompts.py:60, 173`). A model that
cannot see `execute_code`/`write_file`/`terminal_run` says it cannot.

**RC-3 — The sandbox would refuse network work even if reached.**
`RunSpec(network=False)` (`code/execution.py:412`) is inert but policy; the
import allowlist excludes requests/httpx/bs4/matplotlib (`execution.py:47-51`);
the AST guard is reflective-bypassable and the child has no OS confinement
(`execution.py:234-269, 335-336`).

**RC-4 — Acquisition is closed-capability.** The agent can call the ~10 fixed
bridge-backed tools, but cannot author a fetcher: no generic fetch capability in
`data-bridge.ts` dispatch (`:398-474`), no Python transport (forbidden by
design), and the TS scraper chain is only reachable through those fixed
capabilities.

**RC-5 — The prompt teaches refusal as a complete answer.** `prompts.py:173`
and the "Finishing the job" section (`:62-63`) make UNAVAILABLE acceptable
without any construction attempt. This is the doctrine the master plan replaces
— not the honesty rules (computed ≠ retrieved, never fabricate), which stay.

**RC-6 — "Visual replies that show an error."** Any diagnostic — including
non-fatal `SCHEMA_VERSION_FUTURE`/`NO_BLOCKS` warnings — renders the same amber
panel (`response-view.tsx:293-295`); honest `UNAVAILABLE` chips are instructed
by the prompt (`prompts.py:164`); a settled malformed fence shows a rose
"could not be parsed" card (`response-fence.tsx:41-49`); run errors show a rose
banner. Separately, the panel that would show a *successful* computed result is
dead code.

**RC-7 — Verified bug: the streaming path drops the service bundles.**
`AgenticService.run` passes `portfolio=`, `quant=`, `ui_service=`
(`service.py:1118-1123`); `run_background` — the path every streaming chat turn
takes — does **not** (`service.py:1394-1406`). The quant/portfolio/UI tool
schemas are still advertised, so a call throws `StoreUnavailable` /
`PORTFOLIO_UNAVAILABLE` at call time (`quant/tools.py:78-85`;
`portfolio/tools.py:35-42`). This is a concrete "Eclipse errors instead of
answering" defect, independent of the construction program. **Fixed in R3-01**
— both paths now share ONE `service.py::_run_kwargs` builder, pinned by
`python/tests/test_service_background_parity.py`.

**RC-8 — Capability drift and permission holes.** Registered-but-invisible
families (§3); `bot_create` registered `permission="read"` yet schedules cron
(`automation/tools.py:206-222`); `computer_record_export` writes a JSON as
`read` (`computer/schemas.py:167`); no effect-authorizer branch names
`execute_*`/`package_install`/`container_*` — **confirmed at runtime
(2026-10-12) and fixed in R3-02** (every one returned False through the MCP
fallback while advertised); `git_lfs_fetch/pull` are
`GIT_WRITE` in policy but `external_action` at registration; the terminal read
name lists drift (`policy.py:598-602` vs `terminal/tools.py:31-40`).

---

## 5. Contradictions with existing records → decisions needed

| Record | Record says | Code says (verified) | Decision |
|---|---|---|---|
| `docs/harness/roadmap/README.md:168` | "the front door never sends an autonomy at all … grep ⇒ no matches" | `run-service.ts:264-272` sends it; `graph.py:1186` consumes it | mark stale (done in that file); keep roadmap §1.2 as history |
| `docs/harness/roadmap/README.md:200-203` | `code.execute` is "never grantable" (ADR-025) | grantable at `edit_verify` (`code/policy.py:40`); current ADR-025 is about skills (`DECISIONS.md:480`) | mark stale; cite the true owner (`code/policy.py`) |
| `docs/harness/roadmap/phase-14-*.md` | `graph.py::resolve_run_policy` | renamed `resolve_surface` (`graph.py:311`) | mark stale on next touch of that doc |
| `prompts.py:60, 173` | allowlist is the boundary; UNAVAILABLE is complete | — | **new ADR: construction-first task policy** (amends doctrine, keeps never-fabricate) |
| README §3.5 / `code/sandbox.py:1-20` | "a missing sandbox backend refuses honestly; never degrades" | local subprocess only; DockerSandbox unused | **new ADR: execution substrate tiers** (local read-only default; container required for network/collect; refuse honestly) |
| `retrieval/web.py:10-12` | Python must not open its own transport | TS bridge is the only egress | **new ADR: one egress + generic bounded acquisition capability** (bridge-hosted, SSRF-guarded, rate/host/size caps) — prefer this over opening the Python sandbox network |
| `docs/harness/failure-recovery.md:162-167` | recovery "cannot yet auto-acquire a missing capability" | confirmed | **new ADR/wiring ticket: recovery in the chat loop + acquisition rungs** |
| ADR-H110 (`computed ≠ retrieved`) | code numbers never enter research claims | holds | **keep, extend to collected data** (scraped bytes are `collected`, with provenance, never "verified") |

---

## 6. Repo-mapped phase plan (master Phase 0–10 → this repository)

The repository already completed round 1 (phase-00…12) and part of round 2
(phase-13/14 done; phase-15 in progress; 16–20 not started). This program is
**round 3**: it does not rebuild those; it wires, widens and measures them.

| Master phase | Repo state today | Round-3 work | Depends on |
|---|---|---|---|
| P0 Audit | this document | **done** | — |
| P1 Task policy, routing, capability-aware planning | classifier + surface gate exist; lexical gaps; default `not_code` | **R3-01 ✅ done 2026-10-12** | P0 |
| P2 Secure execution substrate | sandbox exists; network inert; Docker defined-unused | **R3-02 ✅ done 2026-10-12** | R3-01 |
| P3 Adaptive recovery + construction | deep engine; unwired in production; chat has none | **R3-03 ✅ done 2026-10-12** | R3-02 |
| P4 Data acquisition routing | phase-13 done; phase-16 not started; closed capabilities | **R3-04 ✅ done 2026-10-12** (bounded collect; bulk still phase-16) | R3-02, R3-03 |
| P5 Utility building | phases 5/9/14 done; promotion stuck in 15 | **R3-05** (finish phase-15 + reach) | R3-01, R3-04 |
| P6 Visual + artifact delivery | renderer robust; artifacts E2E; no plotting; dead result panel | **R3-06** (= phase-18 + UI mapping) | R3-04 |
| P7 Evidence + deterministic computation | exists (`finance_facts`, receipts, validation) | extend to collected data inside R3-04/05 | R3-04 |
| P8 Memory / skills / learning | done (memory-skills evolution landed) | none — keep | — |
| P9 Permissions / approvals / audit | model exists; holes (RC-8) | **R3-07** (hardening slice) | R3-02 |
| P10 E2E benchmark + release gate | deep harness; **zero construction scenarios**; `task_success` measured-not-gated | **R3-08** (= phases 19/20 + the 16 master scenarios) | R3-01…07 |

### R3-01 — Construction-first routing (smallest user-visible fix)

- **Work:** extend `request_intent.py` vocabulary (extract, scrape, collect,
  clean, transform, parse, download, chart, Monte Carlo/simulate, dataset…)
  and add a `capability` outcome rather than only `not_code`; classify
  data/analysis asks into a bounded **execution profile** (analysis enabled,
  read+execute, no external); keep ambiguous → safest *useful* path.
  Front door: `chat-capability.ts` maps the new verdicts.
- **Also fix RC-7** (`service.py:1394-1406` parity with `:1109-1124`) — one
  small diff, immediate reduction of "error instead of answer".
- **Prompt:** rewrite the "Finishing the job"/"Your tools" doctrine to
  construction-first (§4 RC-5), keep never-fabricate.
- **Acceptance:** the four traced messages reach the right profile; a
  computation request reaches `analysis_run` with `analysisEnabled`; ordinary
  conversation still triggers no code/browse; `tsc`, `vitest`, `pytest`, evals
  green; new routing fixtures.

**R3-01 status — done 2026-10-12 (ADR-H177).** Shipped: `data_task` verdict +
data vocabulary in `code/request_intent.py`; `data_task` → no autonomy +
`analysisEnabled: true` in `chat-capability.ts`/`run-service.ts`; construction-
first prompt doctrine in `prompts.py` (ceiling unchanged at 27769); RC-7 fixed
(`service.py` — both run paths now build `execute_run` from ONE `_run_kwargs`
helper, so the streaming path cannot drop the portfolio/quant/ui bundles).
Tests added: 19 classifier cases, 2 payload cases, 4 background-parity cases.
Deferred to R3-02/R3-04: real network acquisition and enforcement.

### R3-02 — Execution substrate, honestly tiered

- **Work:** enforce limits that are declared (`RunSpec` memory/proc/CPU into
  `run_analysis`), wire `security/sandbox.py::DockerSandbox` as the required
  backend for network-enabled profiles (refuse honestly when unavailable —
  preserves zero-config), route egress through the existing
  `security/network.py` engine at a real seam, fix interactive-shell env
  inheritance, make `RunSpec.network` either enforced or deleted.
- **Acceptance:** a temp script runs and reports outputs; a network-requiring
  task refuses when no container backend exists and never silently runs
  unsandboxed; resource exhaustion is contained; no secret reaches a child.

**R3-02 status — done 2026-10-12 (ADR-H178).** Shipped: the authorizer admits
the execution + LOCAL app-runtime families (`_admit_runtime_tools`, measured
before: `execute_python` etc. all False while advertised); analysis limits are
enforced (`cpu_seconds` 600 as a total-burn guard, `memory_mb` 2048,
`process_limit` 64); "no network" in the analysis profile is true by
construction (restricted builtins, dunder/reflection/URL-literal AST rules);
persistent shells use the scrubbed env; `code/backends.py`'s local declaration
states the real posture. Recon outcomes: **Q1 confirmed + fixed** (execution
tools were refused by the MCP fallback); **Q2 verified working** (fs writes use
the worktree-bound actor from `_ensure_code_workspace`, not `request.workspaceId`);
**Docker is not installed here** — the container tier stays uncoupled until a
real consumer (R3-04) lands, per the no-speculative-infrastructure rule. Still
open: cluster/infra/deploy mutations have no authorizer branch (R3-07); egress
enforcement remains at the bridge (R3-04).

### R3-03 — Recovery in the hot path

- **Work:** drive chat tool-call failures through the bounded recovery
  controller (classify → decide → strategy), wire real handlers for
  `substitute_tool` / `substitute_provider` / `alternative_implementation` /
  `replan` / `delegate_investigation`; enforce `max_total_ms` and the
  delegation cap; make recovery approvals single-use; seed the reproducer
  registry. Keep "never retry a deterministic failure unchanged".
- **Acceptance:** a failed route produces a justified, different next attempt;
  identical repeats stop; partial results survive; the final answer reports
  execution and verification status.

**R3-03 status — done 2026-10-12 (ADR-H179).** The graph's tool loop now calls
`recovery/hotpath.py::run_tool_with_recovery`: on failure the engine classifies
and decides; a READ-ONLY tool with a retry/backoff decision is retried ONCE
(backoff capped at 1.5 s, per-run counters via `record_failure(recovery_state=…)`
so history cannot exhaust a fresh run), and every other failure carries the
strategy directive back to the model ("do NOT repeat the same call"). Budget:
`max_total_ms` enforced when elapsed is supplied; delegation counts are now
feedable. Approvals are single-use (`consume_approval`), and the executor claims
instead of checking. Fail-open: no engine → original result. Graph stayed at its
size ratchet (2025 lines; the wrapper replaces the `registry.execute` call).
Deliberate non-goal recorded: the reproducer registry stays caller-seeded (a
generic reproducer would guess). Still open: cluster/infra authorizer branch
(R3-07); egress (R3-04).

### R3-04 — Bounded acquisition, including agent-shaped fetching

- **Work:** add ONE generic, bounded acquisition capability at the single
  egress point (TS bridge): host policy, SSRF guard, size/time/rate caps,
  cache; expose it to the runtime as a collect tool (permission `data.collect`,
  never `code.write`); implement the catalogued-but-missing providers or delete
  them from the catalogue; make the source ladder fall through to the new
  route before declaring UNAVAILABLE; label everything `collected` with
  provenance in `research_facts` terms.
- **Acceptance:** missing data triggers source discovery and a real
  alternative; empty ≠ zero; conflicts/staleness never silently combined; every
  material fact traces to provenance or an explicit gap; caps enforced.

**R3-04 status — done 2026-10-12 (ADR-H180), bounded slice.** Shipped: the TS
`web_collect` capability (SSRF-hardened fetch + deterministic cheerio selector/
table extraction, caps: 4 MB / 8 s / 500 rows / 5 tables) and the read-only
`web_scrape` tool (registered on the ONE registry, allowlisted, wrapped as
untrusted COLLECTED data); the retrieval UNAVAILABLE text now names the eligible
next routes. Deviations, recorded: bulk/scheduled acquisition stays phase-16
(`data.collect` noun not invented here); the six catalogue-only providers
(FMP/POLYGON/FINNHUB/ALPHAVANTAGE/COINGECKO/COINMARKETCAP) stay honestly marked
`implemented=False` in the retrieval registry rather than being deleted or
faked; the `priceHistory` second-transport fallback is deferred until the
ratcheted `data-bridge.ts` is split (a standing split candidate). Still open:
egress stays at the bridge by design; scanned-PDF OCR on the web path remains an
unrelated gap.

### R3-05 — Utility building that lands

- **Work:** finish phase-15's promotion path (a code change leaves its
  disposable copy only by explicit single-use operator confirmation), make the
  chat code profile usable in practice (workspace binding + grants — verify the
  `workspaceId=None` grant path at runtime), and surface engineering-task
  status. Keep one-off artifacts distinct from durable capabilities.
- **Acceptance:** "build me X" produces a validated deliverable the user can
  open; failed generated code is corrected or replaced; nothing silently
  becomes a runtime capability.

### R3-06 — Visual and artifact delivery

- **Work:** split diagnostics by severity (errors show the panel; warnings do
  not), wire `analysis.completed` + the analysis payload to the chat result
  panel (revive/remove `ComputedResultPanel`), add the plotting library to the
  collect/analysis profile and render figures as `computed` artifacts with
  units/timestamps, make the artifact block resolvable without the model
  guessing an id. Keep the per-block error boundaries.
- **Acceptance:** each supported response type has an end-to-end render test;
  produced artifacts are reachable and authorized; a broken visual never
  destroys the answer; text fallback exists.

### R3-07 — Permission hardening (slice, runs beside R3-02…06)

- **Work:** give `bot_create` and `computer_record_export` correct effect
  metadata; add authorizer branches for `execute_*` / `package_install` /
  `container_*` (or pin why they are unreachable); reconcile policy/registration
  name drift; single-use recovery approvals; visibility rule ("registered but
  invisible" is a bug unless deliberate and documented).
- **Acceptance:** unauthorized actions blocked by runtime controls, not
  absence; approvals cannot be bypassed through generated code; destructive
  operations have rollback/preview; adversarial tests updated.

### R3-08 — The construction benchmark

- **Work:** add the 16 master scenarios to `evaluation/datasets/` as graders
  (alternative-source, missing-field, blocked-site, empty dataset, fixable
  script error, missing dependency, ambiguous records, wrong calculation,
  stale conflict, invalid chart payload, artifact delivery failure, unauthorized
  attempt, budget exceed, partial completion, end-to-end chat). Gate
  `task_success` and recovery-success alongside safety/hallucination.
- **Acceptance:** every scenario measures completion/correctness/provenance/
  recovery/redundant-retries/latency/cost/visual/safety/false-success; critical
  safety blocks release; no completion gains by weakening security or hiding
  failures.

---

## 7. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | Widening chat capability widens attack surface (network, exec) | High | High | Tiered substrate (R3-02), one egress point, `data.collect` ≠ `code.write`, default-deny, single-use approvals |
| 2 | "Construction" becomes fabrication | Medium | High | Keep computed/collected/retrieved labels + evidence gate; scraped data is `collected`, never `verified` |
| 3 | Classifier over-fires → chat becomes slow/expensive | Medium | Medium | Bounded diagnostic step before escalating; budgets; the "ordinary conversation stays prose" acceptance |
| 4 | Recovery loops burn budget | Medium | Medium | Existing budget/controller; enforce `max_total_ms`; different-route rule |
| 5 | Docker absent on user machines breaks zero-config | High | Medium | Local tier stays default for read-only compute; container only for network/collect; refuse honestly otherwise |
| 6 | Visual diagnostics still read as "errors" | Medium | Medium | Severity split + text-first fallback; only the answer, not the panel, is the deliverable |
| 7 | Doc drift repeats (roadmap already stale in 3 places) | High | Low | Mark stale now; each round-3 phase updates its owning doc + CHANGELOG per `AGENTS.md` |
| 8 | CI double-runs evals (`npm test` includes `test-evals`; CI runs both) | Certain | Low | Deduplicate when touching CI |

---

## 8. Dependency map and proposed first slice

```
P0 (this doc)
 └─ R3-01 routing + streaming-bundle fix + doctrine     ← first, highest user-visible payoff
     ├─ R3-02 execution substrate (tiers, limits, egress seam)
     │   ├─ R3-03 recovery in the hot path
     │   │   └─ R3-04 bounded acquisition (phase-16 rebased)
     │   │       ├─ R3-05 utility building lands (finish phase-15)
     │   │       ├─ R3-06 visual + artifact delivery (phase-18 + UI mapping)
     │   │       └─ P7 evidence extension (rides R3-04/05)
     │   └─ R3-07 permission hardening (can run beside 03–06)
     └─ R3-08 benchmark (needs 01–07; scenarios authored earlier as they land)
```

**Why this order.** R3-01 changes what the agent *attempts* at nearly zero
architectural risk and directly addresses the reported experience; R3-02 makes
attempts real without weakening safety; R3-03/04 give the attempt a route when
the first one fails; R3-05/06 make the result land; R3-07 keeps it honest; R3-08
proves it. Do not start R3-02 before R3-01's routing fixtures exist — otherwise
there is no way to demonstrate the behaviour changed.

---

## 9. Open questions requiring runtime verification (not settled by reading)

1. Do `execute_python`/`execute_code`/`package_install`/`container_*` pass the
   composed effect authorizer today, or are they refused by the MCP fallback
   (`mcp/approvals.py:611-617`)? Static read suggests refused; run one live
   call before R3-02.
2. Can a chat `code_change` turn actually write, given `workspaceId=None`
   (`graph.py:1433-1438`, `code/policy.py:644-656`)? Verify with a live turn.
3. Is `DockerSandbox` viable on the target machine (Docker installed and
   permitted)? Affects R3-02's tier decision.
4. Does the SSE stream surface tool-failure codes with enough fidelity to feed
   recovery classification (R3-03), or is a new seam needed in `graph.py`?

---

## Related

- Master program: the construction-first plan supplied 2026-10-12 (Phases 0–10).
- Round 1/2 roadmap: `docs/harness/roadmap/README.md` (phases 0–20; 13–14 done,
  15 in progress, 16–20 not started).
- Failure layer contract: `docs/harness/failure-recovery.md`.
- Response contract: `docs/interactive-response-engine.md`.
- Artifacts: `docs/harness/artifact-center.md`.
- Evidence rules: ADR-027, ADR-H110, `docs/harness/financial-analysis-engine.md`.
