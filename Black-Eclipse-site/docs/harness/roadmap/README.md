---
title: Eclipse as a Harness — Roadmap Index
status: Current
last-verified: 2026-09-30
---

# Eclipse as a Harness — Roadmap

**Goal.** Turn Eclipse from a grounded *financial research agent* into a general
**agentic harness specialized for finance**: one that can navigate a repository,
write and modify code, run checks, repair its own failures, build finance
applications, run on its own schedule, delegate work, and improve itself under
review.

**This folder is the plan.** One file per phase; each is self-contained — goal,
scope, exact contracts, work items, runnable gates, and a **paste-ready
implementation prompt** you can hand straight to OpenCode. Start at the phase
file, not here.

## Phase index

| Phase | File | Depends on | Unlocks | Maps to |
|---|---|---|---|---|
| 0 — Recon, policy decision, baseline freeze | [phase-00](./phase-00-policy-and-baseline.md) ✅ Done | — | 1,2,3 | — |
| 1 — Repository navigator (read-only) | [phase-01](./phase-01-repository-navigator.md) ✅ Done | 0 | 2 | §15.3 **7A** |
| 2 — Isolated worktree patch authoring | [phase-02](./phase-02-worktree-patching.md) | 1 | 3 | §15.3 **7B** |
| 3 — Sandboxed command broker | [phase-03](./phase-03-command-broker.md) | 2 | 4 | §15.3 **7C** |
| 4 — Verify-and-repair trust spine | [phase-04](./phase-04-verify-and-repair.md) | 3 | 5 | §15.3 **7D** |
| 5 — Coding agent, autonomy profiles, approvals | [phase-05](./phase-05-coding-agent.md) | 4 | 6,7,8,9 | §15.3 **7E** |
| 6 — Harness-owned jobs and triggers | [phase-06](./phase-06-jobs-and-triggers.md) | 5 | 11 | new |
| 7 — Delegation and child runs | [phase-07](./phase-07-delegation.md) | 5 | 9,10 | new |
| 8 — Analysis sandbox (quant code execution) | [phase-08](./phase-08-analysis-sandbox.md) | 5 | 9 | §16 |
| 9 — Finance application scaffold kits | [phase-09](./phase-09-scaffold-kits.md) | 5,7,8 | 10 | §15 examples |
| 10 — Self-improvement v2 (code + skills) | [phase-10](./phase-10-self-improvement.md) | 4,9 | 11 | new |
| 11 — Surface and scale | [phase-11](./phase-11-surface-and-scale.md) | 6,10 | — | new |
| 12 — Evaluation harness and standing gate | [phase-12](./phase-12-evaluation-gate.md) | all | — | §15.3 **7F** |

`§15` / `§16` refer to `agentic-plan-implementaion.md` at the repository root —
this roadmap **builds on** those gates, it does not replace them.

**Status tracker.** Update the phase file's frontmatter (`status: Not started →
In progress → Done / Blocked`) and the one-line row here when a phase closes.

---

## 0. Who this is for — the whole finance field, not just engineers

**This is a first-class design constraint, not a nicety.** The harness must be
usable by everyone who works in finance, including people who will never open a
terminal:

| Who | What they need from Eclipse |
|---|---|
| Research analyst / journalist | build a screening pipeline, pull filings, verify a number before publishing |
| Portfolio manager / advisor | a scheduled risk brief, an earnings digest, a client-ready report |
| Trader / risk officer | a backtest, a drawdown check, a correlation matrix — and proof of how it was computed |
| Accountant / controller | a reconciliation helper, a period-comparison tool, an audit trail |
| Student / teacher | learn by asking for something real and reading the plain explanation |
| Small-business owner | a cash-flow view, an invoice analysis, a cost dashboard |
| Software engineer in finance | the full power: scaffolds, jobs, MCP integrations, code review |

Nobody should need to know **git, Python, "worktrees", terminals, allowlists or
autonomy profiles** to get value. The harness absorbs the mechanism.

### The seven rules that make this true

1. **Job vocabulary, never mechanism vocabulary.** Every user-visible string names
   the *finance job* — "Check my portfolio for risks overnight", "Run the test
   suite", "Build me a report generator". Mechanism words (`sandbox`, `worktree`,
   `allowlist`, `policy engine`, `digest`, `exit code`, `verification ledger`,
   `autonomy profile`) appear in the trace and logs, never in the UI.
2. **Plain defaults, expert opt-in.** Every phase's capability ships with the
   safest defaults already chosen, so the non-expert path is the *only* path they
   meet. Depth is reached by asking, not by configuring.
3. **One-click jobs.** The job library (Phase 6) ships ready templates the user
   parameterizes ("which tickers?"), not definitions they author.
4. **Refusals in one plain sentence.** A blocked action says what was blocked and
   what the user can do next; the technical reason lives behind a "details"
   affordance (the event already carries the code).
5. **Honesty, not silence.** "I could not check this" is a first-class answer to a
   non-expert, in the same way `UNAVAILABLE` already is for market data.
6. **Strings live in the i18n layer.** `src/lib/i18n/` owns them —
   `dictionaries/en.ts` (canonical keys), `dictionaries/index.ts` (translations),
   `translate.ts` (lookup), `use-t.ts` (hook). New user-facing copy is a **key**
   there, never a hardcoded string in a component. That is also what makes the
   next language cheap.
7. **A gate, not a promise.** Every phase that ships user-facing copy adds a
   **plain-language gate**: no new user-facing string may contain a word from the
   mechanism denylist. Implement it as a small test over the new strings + i18n
   keys (`src/lib/i18n/plain-language.test.ts` for the front door,
   `python/tests/test_plain_language.py` for runtime-produced text).

**Mechanism denylist** (the plain-language gate's word list):

```
sandbox  worktree  workspace  allowlist  autonomy  digest  argv  cwd  stderr
stdout  patch  diff  manifest  operator  policy engine  tool registry
exit code  verification ledger  repo  repository  commit  branch  HEAD
```

A **developer** reading this roadmap still gets the full depth — every phase keeps
its exact contracts in §6. The plain-language rule governs the *surface*, not the
engineering.

---

## 1. Capability ledger (verified 2026-09-30, not recalled)

| Capability | Hermes does | Eclipse today | Evidence |
|---|---|---|---|
| Tool-calling agent loop | yes | **yes** — LangGraph `agent ⇄ tools`, bounded steps, forced final answer, SSE streaming | `python/harness/graph.py` |
| Universal model coverage | yes | **yes** — native integrations + OpenAI-compatible protocol, `PROVIDER_CATALOG` as data | `python/harness/models.py` |
| Persistent memory | MEMORY.md/USER.md + session search | **yes, deeper** — `eclipse-memory.db`, one write gate, contradictions, retention, profile projection, session FTS | `python/harness/eclipse_memory/` |
| Skills (progressive, versioned) | SKILL.md + curator | **yes** — manifest/registry/permissions/runtime/evaluation/lifecycle, 5 bundled skills, patch + canary + rollback | `python/harness/skills/` |
| MCP client | yes | **yes, unusually hardened** — 3 transports, effect classes, single-use approvals, circuit breaker, OSV spawn check | `python/harness/mcp/` |
| Web search / fetch / evidence | yes | **yes, stronger for finance** — span-anchored fact validation, escalation ladder, comparability gate | `research/`, `retrieval/` |
| Observability & persistence | sessions, traces | **yes** — `agent-memory.db`, event bus, receipts, usage aggregates, `explain_run` | `persistence.py`, `run_observability.py` |
| Mistake detection | lessons → skills | **partial** — 9 deterministic categories from a run trace | `eclipse_memory/mistakes.py` |
| Self-improvement | agent writes its own skills | **gated for skills only** — candidate → draft → evaluation → operator promotion | `skills/{learning,draft,evaluation,versioning}.py` |
| **Read/write/run code** | terminal, patch, write_file | **NO** — no filesystem, shell, patch or exec tool | 18 registered tools, none code-related |
| **Execute code (analysis)** | `execute_code` + tool RPC | **NO** | no sandbox module exists |
| **Delegate subagents** | `delegate_task` | **NO** — `parentRunId` exists for skill sub-runs only | `skills/runtime.py` |
| **Scheduled autonomous work** | cron, heartbeats, goals | **partial, wrong side of the split** — TS schedulers only | `src/lib/{scraper,connectors,investor-eye}/*scheduler*` |
| **Self-build new tools/agents** | plugins, dynamic toolsets | **NO** — adding a tool is a human code change | `architecture.md` → Extension points |
| Event triggers | webhooks | **NO** harness-level inbound trigger | — |

All 18 tools are read-only: the `get_*` finance/capability family, the retrieval
family (`market.get_quote`, `market.get_ohlcv`, `fundamentals.get_*`,
`research.*`, `macro.get_series`), and the memory/session/skill-read tools.

## 2. The four structural gaps

1. **No code capability at all.** Every "build me X" ends at *prose about X*.
2. **No isolation primitive.** Even with code tools, there is no worktree, no
   sandbox, no path allowlist, no command allowlist, no resource/network policy.
   This must exist **before** gap 1 is opened.
3. **No independent verification of its own output.** Market claims are verified
   rigorously (retrieval → coverage → validator → receipt); code claims have no
   equivalent. "The command I say passed" has no executor to back it.
4. **No autonomous cadence.** Nothing runs without a human clicking.

The permission model already anticipates the fix — and is the reason Phase 0
exists. From `python/harness/skills/permissions.py`:

- `SAFE_PERMISSIONS` (default actor): `data.read`, `research.read`,
  `analysis.execute`, `report.generate`, `skill.invoke`, `portfolio.read`,
  `external.network`.
- `OPERATOR_PERMISSIONS`: `skill.create`, `skill.review`, `skill.enable`,
  `skill.disable`, `portfolio.modify`.
- `BLOCKED_PERMISSIONS`: `FORBIDDEN_PERMISSIONS` **+ `code.execute`** — never
  grantable. `FORBIDDEN_PERMISSIONS` also blocks `code.write`.

So the code capability is blocked **in code, deliberately** (ADR-025). Phase 0
reverses that under control, with tests, rather than letting a coding agent delete
a constant to make a test pass.

## 3. Invariants that survive every phase

From `AGENTS.md`, `docs/DECISIONS.md` (ADR-025) and the harness ADR series:

1. **One runtime.** No second agent loop, tool registry, or model adapter. New
   capability = new tools on the existing `ToolRegistry`, driven by the existing
   `execute_run`.
2. **Prose is not a security boundary.** Permissions, path policy, command
   allowlists and budgets are enforced in Python, whatever a `SKILL.md` says.
3. **Generated artifacts stay inert** until evaluation + an operator decision.
4. **Never fabricate financial data.** A computed number never masquerades as a
   retrieved fact.
5. **Zero-config keeps working.** A missing sandbox backend refuses honestly —
   it never degrades to unsandboxed execution.
6. **Never commit, push, or open a PR unless the user explicitly asks.**
7. **File size ratchets.** `graph.py`, `persistence.py`,
   `eclipse_memory/store.py`, `main.py` are at their limits. New logic goes in new
   modules; `main.py` grows by `include_router`.
8. **The release gate is definition of done:** `npm run check:all` from
   `Black-Eclipse-site/`. Baseline 2026-09-30: 164 vitest files / 1 941 tests
   green, ~1 700 pytest nodes green, all eval gates pass.

### Index of the invariants in §3 (cited by the phase files as `README §3.N`)

| # | Short name | Meaning |
|---|---|---|
| 3.1 | One runtime | No second agent loop, tool registry or model adapter. New capability = new tools on the existing registry, driven by the existing run graph. |
| 3.2 | Prose is not a boundary | Permissions, path rules, command allowlists and budgets are enforced in Python, whatever a SKILL.md says. |
| 3.3 | Artifacts stay inert | Nothing a model authored — skill, patch or code — activates without evaluation and an operator decision. |
| 3.4 | Never fabricate | A computed number never masquerades as a retrieved fact. |
| 3.5 | Zero-config | A missing safety mechanism refuses honestly; it never degrades to a less safe path. |
| 3.6 | No unasked-for git | Never commit, push, or open a PR unless the user explicitly asks. |
| 3.7 | File size ratchets | The big core files are at their limits; new logic goes in new modules. |
| 3.8 | The release gate | `npm run check:all` is the definition of done. |

## 4. Work already in flight (reconciled)

Two untracked modules landed in the tree at 2026-09-30 22:21–22:22 from a
concurrent agent:

- `python/harness/run_lineage.py` — `HarnessRun.parentRunId`/`workflowId`, a
  bounded `RunCheckpoint` per durable boundary, and `ToolExecutionIdempotency`
  per `(runId, stepIndex, toolCallId)` so a resume **reuses** a recorded result
  instead of re-running a side-effecting call.
- `python/harness/graph_context.py` — per-run context blocks extracted from
  `graph.py`.

**Consequences:** Phase 5's resume is a *consumer* of those primitives, not a
builder; Phase 7 uses the existing `parentRunId` lineage; check whether a workflow
concept landed alongside `workflowId` before Phase 6/7 and reuse it.

**Concurrency rule.** OpenCode edits this tree concurrently. If a gate fails,
compare the failing file's **mtime against the start of your run** before calling
it a regression, and never write to a file modified in the last few seconds.

## 5. How to run one phase (the operating loop)

1. **Write the progress log** `docs/harness/roadmap/progress/<phase>-progress.md`
   (create the folder on first use) with the phase's gate commands listed as
   checkboxes, unchecked.
2. **Hand over the prompt** — §11 of the phase file is a complete, paste-ready
   implementation prompt. Give it to OpenCode verbatim.
3. **Verify independently.** Re-run every gate yourself against the working tree.
   Never accept the progress log's claims. Record the numbers you observed.
4. **Check for contamination** (mtime rule above) before calling anything a
   regression.
5. **Close the docs** per `AGENTS.md`: append a dated `docs/CHANGELOG.md` entry
   and update the owning doc via `docs/NAVIGATION.md`'s trigger table. Flip the
   phase's `status:` and the index row.

**Ordering rules.**

- Phases **1 → 2 → 3 are strictly serial.** Never open a write or command tool
  before isolation exists.
- Phase **4 must land before** any autonomy beyond `plan_only` is offered.
- Phases **6, 7, 8 are independent** once 5 is green and can be parallelized
  (each in its own worktree).
- Phase **10 requires 4 + 9**. Phase **12 requires everything**.
- A gate that cannot pass produces an **honest partial report** naming what is
  blocked — never a weakened gate.

## 6. Deliberate non-goals (whole roadmap)

- **Trading, order placement, broker mutation.** `trade.execute`, `broker.modify`,
  `production.modify` stay forbidden. Nothing here changes that.
- **A visual workflow editor** (named not-built in `phase-3-progress.md`).
- **A second runtime in TypeScript.** The front door stays thin.
- **Unsupervised autonomous self-modification.** Every activation is evaluated and
  operator-decided; ADR-025 is extended, never repealed.
- **A new vector DB / second indexer.** Reuse existing retrieval and FTS.
- **Multi-node distributed scheduling.** Phase 6 is single-process and durable.
- **Replacing the existing TS schedulers.** Phase 6 adds the harness job model
  beside them and says so in its ADR.

## 7. File map added by this roadmap

```
Black-Eclipse-site/python/harness/
  code/
    __init__.py
    policy.py          Phase 0  — the ONE code-policy authority
    workspace.py       Phase 1  — binding + path confinement
    tools.py           Phase 1  — register_code_tools(registry)
    worktree.py        Phase 2  — allocate / release / diff
    patch.py           Phase 2  — structured patch ops + hashes
    commands.py        Phase 3  — the command-class TABLE
    sandbox.py         Phase 3  — one bounded execution primitive
    verify.py          Phase 4  — the verification ledger
    repair.py          Phase 4  — plan→edit→check→repair
    execution.py       Phase 8  — analysis sandbox + artifacts
    kits/              Phase 9  — scaffold kits (data)
    evolution.py       Phase 10 — code+skill evolution bridge
    eval/              Phase 12 — labelled tasks + safety cases + runner
  jobs/
    model.py store.py scheduler.py triggers.py      Phase 6
  routers/
    code.py  jobs.py                                 registered by main.py
  delegation.py                                      Phase 7

Black-Eclipse-site/src/
  app/api/code/**  app/api/jobs/**        thin proxies
  lib/harness/code-client.ts  jobs-client.ts
  components/screens/code/**  jobs/**
  components/chat/code-verification-panel.tsx       Phase 4
```

**ADRs to write** (harness series continues from **ADR-H96** in
`docs/harness/decisions.md`; app series continues from the current max in
`docs/DECISIONS.md`):

| ADR | Subject | Phase |
|---|---|---|
| ADR-H97 | The code capability is tools on the one registry, not a second runtime | 0 |
| ADR-H98 | `code/policy.py` is the single policy authority; autonomy profiles enforced in code | 0 |
| ADR-H99 | Protected paths, command classes, default-deny network and secret posture | 0 |
| ADR-H100 | Read-only repository navigation is path-confined, bounded and citable | 1 |
| ADR-H101 | Workspace isolation: disposable worktrees, snapshot fallback, never the user's own checkout | 2 |
| ADR-H102 | Commands are a closed table; a missing isolation primitive refuses rather than degrades | 3 |
| ADR-H103 | A check is passing only when the executor recorded it; unbacked claims are marked | 4 |
| ADR-H104 | One approval store, generalized; a code action is single-use, digest- and workspace-bound | 5 |
| ADR-H105 | Harness-owned jobs; the TS refresh loops stay as they are | 6 |
| ADR-H106 | Child runs are narrowed, never widened; self-reports require verifiable handles | 7 |
| ADR-H107 | Computed ≠ retrieved: a code-produced number carries its code digest and never enters research claims | 8 |
| ADR-H108 | Scaffold kits are data; a generated artefact stays inert until evaluated | 9 |
| ADR-H109 | Self-improvement covers code as well as skills; the policy engine and the release gate are frozen | 10 |
| ADR-H110 | Delivery adapters behind one interface; scope-aware surfaces; an honest sandbox backend | 11 |
| ADR-H111 | The code eval gate is part of the one honest release gate | 12 |

**ADR shape:** `docs/harness/decisions.md` uses `## ADR-Hnn — Title` followed by
**Decision.** / **Why.** / **Consequences.** — match that. The harness closeout
of 2026-09-30 already landed ADR-H93–H96 (run lineage, route health, capability
matrix, workflows), so Phase 0 appended the next free numbers — **ADR-H97,
ADR-H98, ADR-H99** — and Phase 1 appended **ADR-H100**, rather than duplicating
those headers. Later phases take the numbers after H100.
