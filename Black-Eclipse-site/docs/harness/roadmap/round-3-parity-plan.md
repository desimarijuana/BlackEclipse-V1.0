---
title: Round 3 — Harness Parity Plan (7.2 → 9.5)
status: Draft
last-verified: 2026-10-20
---

# Round 3 — Harness Parity Plan (7.2 → 9.5)

**What this is.** Rounds 1 and 2 (phases 0–20) built the *machinery* of a
harness and made it reachable and truthful about its sources. Round 3 is the
round that makes it **competitive as a coding harness** and **shippable as a
product**: a real context-management story, a real verify-and-repair loop, one
edit primitive instead of three, a repo map, live measurement, and a released,
shrink-wrapped, publicly evidenced harness.

**Who it is for.** Anyone executing a workstream. Each workstream states the
evidence, the exact files, the contract, the runnable gate, and the score it
moves. It is a plan, not a report: nothing here is done.

**Status.** `Draft` — written from a code-grounded audit on 2026-10-20, not yet
executed. Every gap in §2 was read out of the source, not recalled. Where a
number is a *target* rather than a measurement, it says so.

---

## 1. The scorecard

### 1.1 Where Eclipse stands

Scored on the seven dimensions that decide how a harness actually performs,
against the 2026 field (Claude Code, OpenHands, Codex CLI, Cursor, Devin,
OpenCode, GitHub Copilot, Cline, Goose, Aider). Field median = the median of
those ten on each dimension.

| Criterion | Weight | Eclipse | Field median | Δ | Points |
|---|---|---|---|---|---|
| Agent loop & robustness | 20 | 7.5 | 8.5 | −1.0 | −0.20 |
| Context management | 18 | **5.5** | 8.5 | **−3.0** | **−0.54** |
| Tool / agent-computer interface | 15 | 7.5 | 8.25 | −0.75 | −0.11 |
| Safety & permissions | 17 | **8.5** | 8.0 | **+0.5** | +0.09 |
| Extensibility (MCP, skills, hooks, subagents) | 12 | **8.5** | 8.25 | **+0.25** | +0.03 |
| Evaluation & measurability | 10 | **7.0** | 6.75 | **+0.25** | +0.03 |
| Operational maturity | 8 | **5.0** | 8.25 | **−3.25** | **−0.26** |
| **Weighted** | 100 | **7.18** | 8.15 | | **−0.97** |

**What this says.** Eclipse already **beats the field median on safety,
extensibility and the design of its evaluation system**. It loses on exactly
two dimensions — context management and operational maturity — and those two
carry **0.80 of the 0.97-point deficit**. There is no broad gap. There is a
deep one in two places.

### 1.2 The arithmetic of 9.5

This is the constraint that shapes the whole plan: **you cannot reach 9.5 by
fixing context alone.**

| Criterion | Now | Target | Δ needed | Points needed |
|---|---|---|---|---|
| Loop | 7.5 | 9.5 | +2.0 | +0.40 |
| Ctx | 5.5 | 9.5 | +4.0 | +0.72 |
| ACI | 7.5 | 9.5 | +2.0 | +0.30 |
| Safe | 8.5 | 9.5 | +1.0 | +0.17 |
| Ext | 8.5 | 9.5 | +1.0 | +0.12 |
| Eval | 7.0 | 9.5 | +2.5 | +0.25 |
| Ops | 5.0 | 9.5 | +4.5 | +0.36 |
| | **7.18** | **9.50** | | **+2.32** |

Two consequences follow, and they dictate the sequencing:

1. **Context is worth +0.72** — the single largest prize, because the gap is
   4.0 points wide.
2. **Operations is worth +0.36 at only 8% weight** — the second largest prize,
   because the gap is 4.5 points wide. It is also the cheapest: no new
   mechanism, only discipline.
3. **Everything else is worth +0.20 each.** Six of the seven dimensions are
   close. A plan that spends its energy on "make the harness more capable"
   instead of "make the harness *work* and *ship*" is the wrong plan.

### 1.3 The target scorecard

| Criterion | 9.5 target means | Verified by |
|---|---|---|
| Loop | Auto-compaction, verify→repair in the graph, parallel-safe tool calls, recovery in the chat path, budgets that fit the task | `code/eval` shape `failing-check-repair-in-graph`; a compaction eval; a budget table |
| Ctx | LLM compaction with a deterministic fallback, lazy tool loading, a repo map in the first turn, isolated child contexts, measured per-turn schema budget | `docs/harness/benchmarks.md` (ctx columns); a determinism test on the repo map |
| ACI | One edit primitive, mandatory stale guard, unambiguous-match refusal, path recovery, one search primitive, ripgrep-first | a new `code/eval` shape per edit contract; a search-engine test |
| Safe | Network enforced or refused, container backend, scrubbed env everywhere, secrets redacted from tool output | a new safety case per guarantee; a `SECRET_BLOCKED` test on `shell_run` |
| Ext | Public SDK, an open tool registry, ACP interop, a plugin path others can use | the package builds and installs; a second-host ACP smoke |
| Eval | Live model in CI, an external task suite, published numbers with provenance, every capability class measured | `docs/harness/benchmarks.md` generated, not written; 0 unmeasured classes |
| Ops | Tagged releases, a shrinking surface, clean ADRs, a second pair of eyes, no dirty tree | `git tag`; `scripts/size-budget.js`; `scripts/check-adr-numbers.js`; `CODEOWNERS` |

### 1.4 What "9.5" does **not** mean

- **It does not mean "more tools."** Eclipse already has ~450–550 native tools
  across 57 subpackages. The gap is *smaller, sharper* tool surface, not more.
- **It does not mean a bigger model.** The harness is provider-agnostic; the
  plan changes no default model.
- **It does not mean abandoning the honesty discipline.** `UNMEASURED` over
  `0`, `None` over a fake `0`, conflicts preserved over first-success — these
  are the harness's best feature and they stay. The plan makes them *visible*
  to a benchmark, which is what they were missing.
- **It does not mean a second runtime.** Every workstream below adds tools,
  nodes or contracts to the **existing** `ToolRegistry` and the **existing**
  `execute_run` graph. `README §3.1` (one runtime) is not negotiable.
- **It does not mean trading, order placement or broker mutation.** Still
  forbidden.

---

## 2. The gap ledger

Everything below was read out of the source on 2026-10-20. Line numbers are
the ones to open.

### 2.1 Coding — the harness can read and write, but it cannot *finish*

| # | Gap | Evidence | Severity |
|---|---|---|---|
| C1 | **No automatic verify→repair loop in production.** The module is correct and bounded; it has **zero production callers**. | `code/repair.py:84`; the only callers are `code/eval/tasks.py:276,290` and `code/eval/safety.py:133,144`; `graph.py:1578` passes `repair_outcome=None` | **Critical** |
| C2 | **The chat code turn has no plan/todo tool and no web access**, and `chat_code_allowlist` *replaces* the whole finance allowlist rather than narrowing it. | `agents.py:776-910` (no `*TASK_TOOLS`, no `*WEB_RESEARCH_TOOLS`, no `*SEARCH_TOOLS`); `graph.py:396-399` | **Critical** |
| C3 | **No repo map, file tree or outline reaches the model.** Grep for `repo_map|repomap|file_tree` returns nothing. CIUE is **pull-only** — the model must spend tool calls to ask. | `code/intel/manager.py:555-557` is the only path; `graph.py:1336-1343` `runtime_context` carries no repo content | **Critical** |
| C4 | **The stale-edit guard is optional.** `expectedHash` is accepted on every mutator but **nothing requires it**; only `edit_file` computes it for itself. The model can write to a file it never read. | `code/fs/editing.py:63-69` (`STALE_FILE` only fires *if* a hash is passed); `code/fs_tools.py:985` is the one automatic site | High |
| C5 | **Three overlapping write stacks.** `workspace_patch_apply` (5 ops), 15 FS mutators, and a natural-language `edit_file` intent parser. Three ways to change a file, three sets of error codes. | `code/tools.py:1113`; `code/fs_tools.py:1176`; `code/fs/intent.py:106` | High |
| C6 | **Two search implementations, and the one the chat profile leads with is the slow one.** `workspace_search` is *always* a naive Python scan; `search_text` is ripgrep-first. | `code/tools.py:428-489` (no `rg`); `code/fs/search.py:128-178` (rg-first, `engine_name()`) | High |
| C7 | **A wrong path returns a bare `NOT_FOUND`** with no candidates and no "did you mean". | `code/tools.py:402` | Medium |
| C8 | **The change-landing path is manual, per change.** A chat-originated edit lives in a disposable copy; it needs a separate preview + single-use approval to reach the user's tree. | `code/promotion.py:119,252`; `routers/code.py:421,455` | Medium |
| C9 | **`promotion` is an unmeasured capability class** — the landing path has no end-to-end fixture, only pieces. | `code/eval/capabilities.py:196-198` | High |
| C10 | **No OS-level isolation and no network enforcement.** `DockerSandbox.execute()` is never called; `RunSpec.network` is declarative with no consumer. | `construction-first-audit.md:90-98` | High |
| C11 | **`shell_run` inherits the full `os.environ`** — the one path that can hand a provider key to a subprocess. | `code/shell.py:69` | High |
| C12 | **The budgets fit a small task, not a coding task.** 24 model steps / 600 s for `code-agent`; `maxToolCalls` is `None` (unbounded) on every preset. | `agents.py:755-766`; `graph.py:493-498` | Medium |
| C13 | **`code-navigator` is mislabelled** — the "read-only" comment is stale; its allowlist contains every write and execute tool. | `agents.py:566-578` | Low |
| C14 | **`intel.is_fresh()` is hard-coded `return True`** — a freshness claim that is not measured. | `code/intel/runtime.py:158-159` | Medium |
| C15 | **Tree-sitter and the LSP servers are absent** from the vendored interpreter, so the semantic layer is effectively off. | `code/intel/treesitter.py:5-8`; `code/intel/lsp/providers.py:32-90` (the list of what *would* run) | Medium |
| C16 | **The capability registry has no class for the code-intelligence, search, shell-execution or chat-routing layers at all.** | `code/eval/capabilities.py:151-210` — 18 classes, none for CIUE / search / shell / routing | Medium |

### 2.2 Context and loop

| # | Gap | Evidence |
|---|---|---|
| X1 | **No LLM compaction.** History is truncated only; the module says so outright. | `context_budget.py:12` — *"no tokenizer dependency, no network call, no summarization"*; `history.py` `MAX_HISTORY_TURNS=20`, `MAX_HISTORY_CHARS=40_000` |
| X2 | The one model-assisted path is **off by default, additive-only, and extracts inert candidates — never a summary**. | `eclipse_memory/policy.py:190` `dropped_context_model_extraction: False`; `history.py:164-197`; `eclipse_memory/dropped_context.py` (*"Deterministic first… No model call is made here"*) |
| X3 | **~450–550 tool schemas are bound every turn.** There is no lazy/dynamic tool loading. | `tools.py:420` `ToolRegistry`; `agents.py:250-910` — `CODE_AGENT_TOOLS` is ~250 names alone |
| X4 | **Tool output is hard-bounded at 24,000 characters** with a truncation marker — a code read can be silently cut mid-file. | `tools.py:67` `MAX_TOOL_RESULT_CHARS = 24_000`; `bound_tool_text` |
| X5 | **The chat path is not driven through recovery at all** — only the task executor is. | `construction-first-audit.md:138-139`; `graph.py` has no recovery loop |

### 2.3 Safety

| # | Gap | Evidence |
|---|---|---|
| S1 | **`RunSpec.network` is declarative with no consumer** — no netns, firewall or proxy enforces it. | `construction-first-audit.md:90-91`; `code/sandbox.py` |
| S2 | **The container backend exists but is never invoked.** | `security/sandbox.py` `DockerSandbox`; `construction-first-audit.md:96-98` |
| S3 | **`shell_run` leaks the full environment**, contradicting the scrubbed-env posture of the sandbox path. | `code/shell.py:69` vs `code/sandbox.py:97-118` |
| S4 | **No secret redaction on command output** before it reaches the model. | `code/shell.py:27` `MAX_OUTPUT_CHARS = 200_000`; the redaction exists only on *file reads* (`code/tools.py:529` `redact_span`) |
| S5 | **Cluster/infra/deploy mutations have no authorizer branch.** | `construction-first-audit.md:344-345` |

### 2.4 Evaluation

| # | Gap | Evidence |
|---|---|---|
| E1 | **The offline tier replaces the model with a recorded program**, so `task_success = 1.0` measures the runtime, not the reasoning. | `evaluation/runner.py` `ScriptedAgentInvoker`; 29/31 benchmark tasks carry a `metadata.agent_script` |
| E2 | **The live tier exists and is not in CI.** | `evaluation/runner.py` `ServiceAgentInvoker`; the live team comparison is behind `HARNESS_TEAM_LIVE_IT=1` and is documented as *"never in CI"* |
| E3 | **No external task suite.** Grep for `swe.?bench` across the site returns **nothing**. | — |
| E4 | **Four capability classes are unmeasured** — `price_authority`, `promotion`, `scraping_breadth`, `messaging_gateway` (the last: *"Not built yet"*). | `code/eval/capabilities.py:193-204` |
| E5 | **`taskSuccessRate` is measured and printed but deliberately not gated.** | `code/eval/tasks.py:24` |
| E6 | **The phase-20 doc's own counts are stale** — it says 17 classes / `measured=13`; the registry holds 18 / 14. | `phase-20-measuring-all-of-it.md:14,23` vs `code/eval/capabilities.py` |
| E7 | **Latency/cost/tokens are measured per trial but not gated.** | `construction-first-audit.md:517-518` |

### 2.5 Operations and delivery

| # | Gap | Evidence |
|---|---|---|
| O1 | **No tags, no releases.** `version: 0.1.0`, `private: true`. | `package.json`; `git tag -l` empty |
| O2 | **~90% single-author history**, bursty rather than steady. | `git shortlog -sn --all` — 757 / 47 / 37 |
| O3 | **The working tree is dirty** (20+ modified files) at the time of writing. | `git status` |
| O4 | **The harness surface is 361,990 lines across 1,315 files and 57 subpackages** — with no size ratchet enforced in CI. | measured; `README §3.7` states the invariant but nothing enforces it |
| O5 | **7 duplicated ADR numbers** (H146, H160, H162, H242 ×3, H243, H244) — 282 headings for 275 distinct decisions. | `docs/harness/decisions.md` |
| O6 | **No CI check on doc counts** — hence E6. | — |
| O7 | **No second pair of eyes** on the harness; no `CODEOWNERS`. | — |
| O8 | **The harness is not distributable** — no package, no public SDK, no external protocol. | — |

### 2.6 The finance side (not coding, but "everywhere we are lacking")

| # | Gap | Evidence |
|---|---|---|
| F1 | **The Quant Research Studio UI is not built**, and neither is per-workspace authorization/quotas/isolation. | `docs/quant-research/IMPLEMENTATION_STATUS.md` |
| F2 | **The chat mock fallback** — "chat falls back to a keyword mock with no LLM" — is a known problem. | `skills/REMEMBER.md` → *Known Problems* |
| F3 | **Phase 15 (attachments/artifacts), Phase 18 (figure payload + inline renderer) and Phase 20 (remaining fixtures) are still in progress.** | `roadmap/README.md` index rows |
| F4 | **`messaging_gateway` is not built at all**, yet it is published as a capability class. | `code/eval/capabilities.py:202-204` |
| F5 | **The JdDS vault is first for every price-shaped type and the first success wins** — the live provider is never consulted, and the vault's age is the snapshot write time with no market as-of. | `roadmap/README.md` §1.2 row 1; `retrieval/layer.py::_SINGLE_BEST` |

---

## 3. The workstreams

Ten workstreams in three waves. **Wave A** removes defects. **Wave B** closes
the two dimensions that cap the score. **Wave C** is the last mile.

Every workstream ends with a **gate** — a command that must exit zero. A
workstream with a green gate and no measurable score movement is not done.

---

### W1 — Wire the verify→repair loop into the live graph

> **Closes:** C1 · **Moves:** Loop +0.20, Eval +0.10 · **ADR:** H281
> **Priority: 1 — this is a correctness hole, not a feature.**

**Why.** The harness has a correct, bounded, budgeted repair loop
(`code/repair.py:84` `run_verify_repair`: plan → check → edit → re-check, with
`DEFAULT_MAX_REPAIR_ATTEMPTS=2`, `DEFAULT_MAX_WALL_CLOCK_S=900`,
`DEFAULT_MAX_COST_USD=1.50`). Its own docstring says *"`execute_run` CALLS
`run_verify_repair`"*. **It does not.** The only two callers in the repository
are the eval harness. In production, `graph.py:1578` calls
`enforce_run_answer(output, code_ledger, repair_outcome=None, …)` — the repair
outcome is **always `None`**. The model is told a check failed and must drive
the retry itself, with no budget, no cost cap, and no recorded attempt.

**Work items.**

1. `python/harness/code/repair.py` — export a `RepairNodeResult` and make
   `run_verify_repair` return a value that distinguishes **not-run** from
   **run-and-passed** from **run-and-exhausted**. `None` must stop meaning
   "passed".
2. `python/harness/graph.py` — add a `verify_repair` node to the existing
   `StateGraph`, routed from `tools` when (a) autonomy is `edit_verify` or
   `approve_external`, (b) the workspace pins a check, and (c) the last
   tool result carried a failing check. Add `repair_outcome` to `GraphState`.
3. The node must **not** hand the model a free retry. It re-runs the check
   itself; the model sees the *result* of the check, not the ability to skip
   it. A repair that never ran must be visible in the answer seam.
4. `python/harness/graph.py:1577-1578` — pass the real outcome to
   `enforce_run_answer`. An answer that claims "tests pass" while the repair
   loop exhausted its budget must be marked, not accepted.
5. Emit `code.repair.attempt` / `code.repair.exhausted` on the canonical event
   bus (`event_system/`), with the attempt count, the check class, the exit
   code and the output digest.
6. `python/harness/code/tools.py:804-845` — the opt-in `_auto_verify` hook
   (`.black-eclipse/verify.json`) stays, but it must record into the same
   ledger the graph reads, so the two paths cannot disagree.

**Contracts.**

- A repair attempt is **bounded by `RepairBudget`** — attempts, wall clock and
  cost. Exhaustion is a **terminal, reported state**, never a silent stop.
- A repair **never widens authority**: it may not change the allowlist, the
  autonomy profile or the command class.
- The answer seam distinguishes `REPAIR_NOT_RUN` / `REPAIR_PASSED` /
  `REPAIR_EXHAUSTED` / `REPAIR_NOT_APPLICABLE`.

**Gates.**

- `python/tests/test_graph_repair_node.py` — new: a run whose check fails
  re-runs the check, records the attempt, and reports `REPAIR_EXHAUSTED` at
  budget exhaustion; a passing check produces `REPAIR_PASSED`.
- `python/harness/code/eval/dataset_tasks_v1.json` — add the shape
  `failing-check-repair-in-graph`, graded through the **real** graph, with
  `owningChecks: ["unit_test"]`.
- `python/harness/code/eval/capabilities.py` — add the class
  `code_verify_repair_loop` (kind `code_eval`) with a fixture.
- `node scripts/test-evals.js` — the `construction` gate must still pass with
  the new node in the graph.

---

### W2 — Narrow, don't replace: fix surface resolution

> **Closes:** C2 · **Moves:** Loop +0.08, Ctx +0.09, Ext +0.06 · **ADR:** H280 · ✅ **Done 2026-10-20** — the union landed; the measured defect was **441 lost tools**, and the crash it exposed (a fresh `agent-memory.db` had no `codeVerification` column, so every run died at the answer seam) is fixed too
> **Priority: 1 — it is a one-function change with a large blast radius.**

**Why.** `graph.py:396-399`:

```python
chat_profile = chat_code_allowlist(agent, registry, autonomy)
allowed = chat_profile if chat_profile is not None else effective_allowlist(agent, registry, effective_autonomy)
```

A chat code turn **replaces** the entire `eclipse-agent` allowlist with
`CHAT_CODE_TOOLS`. The agent loses every finance, retrieval and browser tool
*and* the task tools *and* web access. So a chat coding turn cannot plan, and
cannot look anything up — while the `code-agent` preset, which is never
selected for chat (`run-service.ts:128` always sends `agentId: "eclipse-agent"`),
has all of it.

**Work items.**

1. `python/harness/graph.py:309-329` — `chat_code_allowlist` returns a
   `SurfaceResolution` dataclass, not a list:
   `base`, `surface`, `intersection`, `additions`, `removed`.
2. The effective allowlist becomes
   `(base ∩ surface) ∪ additions`, where `additions` is the explicit
   *task/plan*, *web-research*, *search* and *memory* families the coding
   surface needs. Narrowing never silently removes a capability the user
   expects.
3. `python/harness/agents.py:776-910` — add `*TASK_TOOLS`, `*WEB_RESEARCH_TOOLS`
   and `*SEARCH_TOOLS` to the code surface's additions.
4. Publish `removedTools` on the run blob so the UI can say **why** a tool is
   missing, instead of the model guessing.
5. `python/harness/agents.py:566-578` — fix the stale "read-only" comment on
   `code-navigator`, and either trim its allowlist to read tools or rename it.
   A name that lies is a defect.

**Contracts.**

- The effective allowlist is always a **superset of the base allowlist minus
  an explicit, published removal list**. There is no silent removal.
- The task/plan tools are present in **every** coding surface, including chat.

**Gates.**

- `python/tests/test_surface_resolution.py` — new: the intersection is
  non-empty; `create_plan` and `web_search` are callable in a chat code turn;
  the removal list is published on the run.
- `python/tests/test_code_request_intent.py` — extend: the classifier's
  `code_change` route now surfaces a plan tool.

---

### W3 — One edit primitive, a mandatory stale guard, and a reviewable landing

> **Closes:** C4, C5, C8, C9 · **Moves:** ACI +0.15, Safe +0.08 · **ADR:** H282
> **Priority: 1 — three stacks become one.**

**Why.** The agent can change a file three ways, and none of them requires
proof that the model saw the file it is about to change. `expectedHash` is
accepted everywhere but **optional** (`code/fs/editing.py:63-69` only raises
`STALE_FILE` if a hash is supplied), and only `edit_file` supplies one for
itself. The good news: `replace_text` already refuses an ambiguous match
(`code/fs/editing.py:166-172` `AMBIGUOUS_PATCH`) — that behaviour should be
the default of the *one* edit tool, not a property of one of fifteen.

**Work items.**

1. **One canonical edit tool.** `code_edit` with
   `path`, `oldText`, `newText`, `expectedHash`, `expectedOccurrences`.
   It inherits `replace_text`'s refusal semantics and `patch.py`'s atomicity
   (all ops validated before any byte is written).
2. **Keep** `apply_unified_diff` (a different operation, genuinely used) and
   `write_file` (creating a new file). **Deprecate** the other 13 FS mutators
   behind a migration flag; they stay callable for one release, then are
   removed. `workspace_patch_apply` folds into `code_edit`.
3. **Make the guard mandatory.** The registry knows which files were read in
   this run. A mutation to a file that was read in this run **must** carry
   the hash the read returned; a mutation to a file that was never read is
   refused with `EDIT_NOT_READ` and the read path named.
4. **Path recovery.** On `NOT_FOUND`, run a bounded nearest-path search
   (basename similarity, suffix match, `rg` on the basename) and return up to
   five candidates with their paths. Wire it into `code/tools.py:402`.
5. **Landing.** Keep the promotion model (it is right), but close the UX gap:
   a single **Review & land** affordance in the chat that shows the diff, the
   checks that were run, the review-rule results and the rollback path — one
   approval for the change, not a per-file ritual. `promotion` becomes a
   measured capability class with an end-to-end fixture
   (preview → approve → apply → rollback → re-apply).

**Contracts.**

- `EDIT_STALE_FILE` — the file changed since the read.
- `EDIT_AMBIGUOUS_MATCH` — the span appears more than once; the tool names
  the count and asks for more context.
- `EDIT_NOT_READ` — the file was never read in this run; the tool names the
  read to make.
- `EDIT_PATH_AMBIGUOUS` — the path resolved to more than one file.
- A promotion preview is **hash-locked** (already true,
  `code/promotion.py:90-96`) and its **rollback is exact** (already true,
  `_capture_backup` `:296-299`). Both get a fixture.

**Gates.**

- `python/harness/code/eval/safety_cases.py` — add **S12** (edit a file that
  was never read → `EDIT_NOT_READ`), **S13** (edit a file changed since the
  read → `EDIT_STALE_FILE`), **S14** (edit an ambiguous span →
  `EDIT_AMBIGUOUS_MATCH`). A block with no recorded reason is a failure, as
  today.
- `python/harness/code/eval/capabilities.py` — `promotion` moves from
  `unmeasured` to a real fixture; add the class `code_edit_contract`.
- `python/tests/test_code_edit_tool.py` — new.

---

### W4 — A repo map, and context that arrives instead of being fetched

> **Closes:** C3, C14, C15 · **Moves:** Ctx +0.36, Loop +0.06 · **ADR:** H283
> **Priority: 1 — the cheapest large Ctx gain in the plan.**

**Why.** There is **no repo map anywhere in the harness.** The model must guess
which directory to list, and a wrong guess returns a bare `NOT_FOUND`. The
machinery to fix this already exists and is *good* — `code/intel/context.py`
`CodeContextEngine` extracts terms, expands symbols, finds callers/callees,
identifies related tests, and bounds the result to 12 files / 40 symbols / 30
ranges / 40 lines each. **It is reachable only if the model thinks to call
`code_get_relevant_context`.** The index is never used to seed the prompt.

**Work items.**

1. `python/harness/code/intel/repo_map.py` — new. A **deterministic, bounded**
   repo map: a directory tree (depth-bounded, ignore-aware) plus, per file, a
   symbol outline taken from the index when available and from a bounded AST
   scan when not. Deterministic ordering, a content hash, and a byte budget.
2. `python/harness/code/intel/runtime.py:158-159` — replace the hard-coded
   `is_fresh() → True` with a real comparison against the index mtime. A
   freshness claim that is not measured is the exact defect this harness
   exists to avoid.
3. `python/harness/code/intel/context.py` — expose `seed_context(request)`:
   when the user's request contains identifiers (a deterministic token
   heuristic, **no model call**), resolve the relevant slice **once per run**
   and add it to the run's context blocks.
4. `python/harness/graph_context.py` — inject the repo map + seeded context
   into the **first** turn. Because `prompt_segments.py` keys the prompt
   cache on segment **content hashes**, the map participates in the cache key
   correctly — a changed map invalidates the cache, an unchanged one does not.
5. `python/harness/code/intel/config.py:71-86` — resolve the tree-sitter and
   LSP absence honestly. Either vendor the parsers, or make the stdlib
   extractor the *documented, supported* path and publish which engine
   answered. An optional layer that silently no-ops is a false capability.
6. `python/harness/code/tools.py:402` — the path-recovery work of W3 applies
   here too; the repo map is the structural answer to "I don't know where
   things are", the candidates are the local answer to "I guessed wrong".

**Contracts.**

- The repo map is a **bounded, deterministic block** — same tree, same
  symbols, same bytes, every run. Two runs on the same tree produce an
  identical map and an identical cache key.
- The map is **data, not instruction**: fenced, sanitised, and never treated
  as a security boundary (`README §3.2`).
- Its size is bounded by a declared budget, and the budget is published on the
  run.

**Gates.**

- `python/tests/test_repo_map.py` — new: determinism (two builds → identical
  hash), bounded size, and the map appears in the first turn's prompt.
- `python/harness/code/eval/capabilities.py` — new class `code_repo_map`.
- `python/tests/test_code_intel_freshness.py` — new: a modified file makes
  `is_fresh()` false.

---

### W5 — One search primitive, ripgrep-first, with honest zero-hit guidance

> **Closes:** C6, C7 · **Moves:** Ctx +0.12, ACI +0.10 · **ADR:** H284
> **Priority: 2 — mostly a consolidation, not new code.**

**Why.** The chat code surface exposes **both** `workspace_search` (always a
naive Python scan, `code/tools.py:428-489`, capped at 5,000 files / 8 MB /
5 s) and `search_text` (ripgrep-first, `code/fs/search.py:128-178`, capped at
10,000 files / 32 MB / 8 s). The model reaches for whichever it sees first —
and the slower one has the friendlier name.

**Work items.**

1. `code/tools.py` — `workspace_search` delegates to `code/fs/search.py` and
   reports `engine: "ripgrep" | "python"` in the payload (the field already
   exists: `code/fs/search.py:52` `engine_name()`).
2. Collapse the search surface to **one** tool with `regex`, `glob`,
   `caseSensitive`, `contextLines`, `maxMatches` — ripgrep-first, bounded
   Python fallback, engine always reported. `search_text`, `search_files` and
   `find_files` fold into it (or become thin aliases).
3. Keep the existing zero-hit guidance — it is genuinely good and rare:
   *"0 matches means this exact literal text was not found — it does NOT prove
   the symbol/code is absent. For alternation (`a|b`) or any pattern, retry
   with regex: true."* (`code/fs_tools.py:742-746`). Promote it to every
   search surface.
4. `code/tools.py:392-395` — `_iter_scan_files` already accepts a single file
   as the search root, with a comment naming the incident that motivated it.
   Keep that behaviour; it is the right call.

**Contracts.**

- Search **always** reports its engine. A scan that fell back to Python says
  so, so a slow result is explainable.
- A zero-hit literal search never implies absence.

**Gates.**

- `python/tests/test_code_search_engine.py` — new: with `rg` on `PATH` the
  engine reports `ripgrep`; without it, `python`; both bounded.
- `python/tests/test_code_search_surface.py` — new: exactly one search tool
  is in the code surface.

---

### W6 — Compaction, and a tool surface that does not eat the context window

> **Closes:** X1, X2, X3, X4 · **Moves:** Ctx +0.15, Loop +0.06 · **ADR:** H285
> **Priority: 1 — the single largest Ctx prize (+0.72 needs this).**

**Why.** Every top-10 harness compacts; Eclipse does not. `context_budget.py:12`
says it outright: *"no tokenizer dependency, no network call, no
summarization."* History is truncated oldest-first (20 turns / 40,000 chars).
The one model-assisted path (`history.py:164-197`) is **off by default** and
extracts **inert candidate items — never a summary**. Meanwhile ~450–550 tool
schemas are bound on every turn, and each result is hard-bounded at 24,000
characters (`tools.py:67`).

**Work items.**

1. `python/harness/compaction.py` — new. `compact_history(messages, budget)`
   returns a **structured** summary: decisions taken, files touched, commands
   run and their outcomes, open questions, and the ids of the dropped turns.
   The dropped-turn ids are always present, so compaction is **lossless in
   structure** even when the prose is lossy.
2. The summary is produced by the run's own model (via `ModelRuntime`,
   `task="background_task"`, bounded timeout — the same seam
   `history.py::_model_extract_dropped` already uses). On **any** failure it
   falls back to the existing deterministic `dropped_context` block, and emits
   `memory.compaction.fallback`. The fallback is the *existing* block, not a
   new weaker one.
3. A compaction is **never presented as user content** — it is marked
   `computed` and fenced, exactly like every other computed artifact in this
   harness.
4. **Lazy tool loading.** Split the allowlist into `always` and `on_demand`,
   and add a `tool_search` tool that resolves a name/description query to
   schemas on demand (the `ToolSearch` idea). The always-bound set shrinks to
   the tools a turn plausibly needs; the rest is discovered.
5. A **per-turn schema budget** derived from the model's declared window
   (`context_budget.py` already resolves it). A turn that would exceed the
   budget fails loudly at bind time rather than overflowing at request time.
6. `MAX_TOOL_RESULT_CHARS` stays the single global bound, but a **read
   overflow must say so** — a truncated code read names the file, the line
   range returned and the continuation point, rather than ending mid-symbol.

**Contracts.**

- Compaction is **additive to the deterministic block**, never a replacement
  for it: the dropped-turn ids and the deterministic candidates survive
  compaction.
- A compaction is `computed`, never `retrieved`.
- The tool-schema budget is **measured before the request**, and a breach is
  a refusal, not a truncation.

**Gates.**

- `python/tests/test_compaction.py` — new: a 40-turn history compacts to the
  budget; the deterministic block is still present; the failure path uses the
  deterministic fallback and emits the fallback event.
- `python/tests/test_tool_schema_budget.py` — new: the bound schema set never
  exceeds the derived budget.
- `python/harness/code/eval/capabilities.py` — new class `context_compaction`.
- A compaction-quality eval: after compaction, a set of labelled decisions
  are still answerable from the context.

---

### W7 — Ship it, shrink it, clean the record

> **Closes:** O1–O7, E6 · **Moves:** Ops +0.36, Ext +0.06 · **ADR:** H286
> **Priority: 1 — the cheapest 0.36 in the plan, and it is pure discipline.**

**Why.** Ops is 5.0 against a field median of 8.25, and 8% weight turns that
into +0.36 — the second largest prize in the plan, for **zero new mechanism**.
Today: no tags, no releases, `0.1.0` private, ~90% one author, a dirty tree,
361,990 lines across 57 subpackages with nothing enforcing a ceiling, seven
duplicated ADR numbers, and a phase-20 doc whose own counts are stale.

**Work items — 7a. Shrink the surface.** This is the structural fix for Ops
5.0, and it is the *reason* Ops is 5.0.

1. `scripts/size-budget.js` — new. A committed budget file
   (`scripts/size-budget.json`) with a per-module line ceiling and a total
   `python/harness/` ceiling. CI fails when any module **grows** past its
   ceiling or the total grows. `README §3.7` states the file-size ratchet as
   an invariant; this makes it enforced rather than aspirational.
2. Delete or merge at least **30%** of `python/harness/`. The named
   candidates, all of which are *duplication* rather than capability:
   - the 15 FS mutators and `workspace_patch_apply` → **one** edit tool (W3);
   - `workspace_search` + `search_text` + `search_files` + `find_files` →
     **one** search tool (W5);
   - `terminal/` (5,334 lines) vs `code/terminal*` — two terminal
     subsystems;
   - `execution/` (17,872) vs `code/execution.py` — two execution planes;
   - `browser/` (10,025) vs `computer/` (12,679) — two UI-automation planes;
   - the ~115 `git_*`/`vcs_*` tools against the 8 `command_run` classes.
   **Deleting a capability is not in scope** — merging two implementations of
   one capability is.
3. Every merge keeps a **deprecation shim** for one release and a migration
   note in the CHANGELOG.

**Work items — 7b. Ship.**

4. Tag `v0.2.0` with a release note derived from the CHANGELOG. Adopt a
   monthly cadence. `package.json` stops being `private` for the SDK
   package (W10), not for the app.
5. `docs/CHANGELOG.md` rotation is enforced: the file keeps a rolling 7-day
   window and the archive step is a script, not a manual edit.

**Work items — 7c. Clean the record.**

6. `docs/harness/decisions.md` — renumber the duplicates (H146, H160, H162,
   H242, H243, H244), keeping the **old number as a redirect line** so no
   external reference breaks. 282 headings → 275 distinct, monotonic.
7. `scripts/check-adr-numbers.js` — new. Fails CI on a duplicate number, a
   gap in the sequence, or an ADR whose shape is not
   `## ADR-H<n> — Title` + `**Decision.**` / `**Why.**` / `**Consequences.**`.
8. Fix the stale phase-20 counts (17 → 18; `measured=13` → 14) and add a
   `last-verified` ratchet: a doc whose front-matter predates the code it
   describes is flagged.
9. `CODEOWNERS` + **at least two external reviewers** on the harness. 90% of
   the history is one author; that is the single biggest risk to every claim
   in this document.

**Gates.**

- `node scripts/size-budget.js` — must pass at or under the committed budget.
- `node scripts/check-adr-numbers.js` — must pass.
- `npm run check:all` — must pass.
- `git tag -l` — must be non-empty.
- The working tree must be clean at the end of the wave.

---

### W8 — Live measurement, an external suite, and published numbers

> **Closes:** E1–E5, E7, F4 · **Moves:** Eval +0.15 · **ADR:** H287
> **Priority: 1 — the plan's credibility workstream.**

**Why.** The evaluation framework is genuinely first-rate: the **real**
`execute_run` graph, 53 labelled tasks across 4 datasets, 17 graders, 22
scoring dimensions with `task_success` and `safety_score` as un-averagable
criticals, `pass@k` with Wilson CIs, flakiness classification, frozen
baselines stamped with the git commit, per-dimension regression detection, a
worktree invoker, a canary split, a verdict-leak tripwire, and a team-vs-single
benchmark that returned a **negative verdict** (+53.6% wall clock) and
therefore did not ship. Almost nobody builds that.

And then: the offline tier **replaces the model with a recorded program**. The
live tier exists and is **not in CI**. There is no external suite. Four
capability classes are unmeasured, including `promotion` — the landing path.
**No number a stranger can check has ever been published.**

**Work items.**

1. **A live lane.** `evaluation/runner.py` `ServiceAgentInvoker` runs the
   production `AgenticService.run` with a real model. Add:
   - a **12-task live smoke** on every PR (cheap, catches a broken loop);
   - the **full 53-task live suite** nightly (the real number);
   - both write into the existing `EvaluationStore` with the provenance
     `evaluation/provenance.py` already requires (dataset checksum, agent
     version, git commit, config, model id, grader api version).
2. **Publish, generated.** `docs/harness/benchmarks.md` is **generated** by
   `python -m harness.evaluation.report` — never hand-edited, so a number
   cannot be quietly improved. Each entry carries model, commit, dataset
   checksum and grader version, or it is not a number, it is a rumour.
3. **An external suite.** Import SWE-bench Verified (or a bounded subset) as
   a dataset adapter, so the harness is comparable to anyone. Nothing in the
   repo matches `swe.?bench` today. This is the only route to a number that
   means anything outside this repository.
4. **Close the four unmeasured classes** with real fixtures:
   `price_authority`, `promotion`, `scraping_breadth`, `messaging_gateway`.
   The last one is *"Not built yet"* — either build it or **retire the class**
   and say so. A published class that does not exist is worse than an
   unmeasured one.
5. **Add the missing capability classes**: `code_intel`, `code_search`,
   `code_shell_exec`, `code_chat_routing`, `code_verify_repair_loop`,
   `code_repo_map`, `code_edit_contract`, `context_compaction`. C16 is the
   gap — a capability with no class is where the work goes silent.
6. **Gate `taskSuccessRate`.** `code/eval/tasks.py:24` deliberately does not
   gate it. Keep that until the live lane has proven it, then gate it.
7. Gate **latency, cost and tokens** (`evaluation/scoring.py` already measures
   them; `construction-first-audit.md:517-518` says they are not gated).

**Contracts.**

- A published number is **reproducible**: the command, the model, the commit,
  the dataset checksum and the grader version are all in the file.
- An unmeasured dimension stays `UNKNOWN`. It never becomes `0`.
- The capability statement and the benchmark file are **generated from the
  same run**.

**Gates.**

- `node scripts/test-evals.js` — a new `live_smoke` gate (skipped with exit 0
  when no provider key is configured, like the existing skip rules).
- `python -m harness.evaluation.report` — regenerates
  `docs/harness/benchmarks.md`; CI fails when the committed file differs.
- `python/harness/code/eval/capabilities.py` — **zero** classes in the
  `unmeasured` bucket.

---

### W9 — Isolation, secrets, and an enforced network

> **Closes:** S1–S5, C10, C11 · **Moves:** Safe +0.09 · **ADR:** H288
> **Priority: 2 — the safety score is already above the field median; this
> closes the remaining real holes, it is not where the points are.**

**Why.** `code/sandbox.py` is a good sandbox — Windows Job Object with
`KILL_ON_JOB_CLOSE`, POSIX process groups, a scrubbed environment
(`SECRET_ENV_ALLOWLIST` only, with proxies and the callback token popped),
a wall-clock timeout, an output cap and a process-tree kill. But:

- `RunSpec.network` is **declarative with no consumer** — nothing enforces
  default-deny network.
- The container backend exists (`security/sandbox.py` `DockerSandbox`) and
  **its `.execute()` is never called**.
- `shell_run` uses `env = dict(os.environ)` — the full environment, including
  provider keys, in the one tool that runs a real host shell.
- Command output is **not redacted** before it reaches the model (redaction
  exists only on file reads).

**Work items.**

1. `code/shell.py:69` — use the **same** scrubbed environment as
   `code/sandbox.py:97-118`. A shell must never see more of the environment
   than a sandboxed command does.
2. **Redact command output** before it reaches the model: secret-shaped output
   is masked, and a `code.output.redacted` event is emitted with the count.
3. **Make `RunSpec.network` mean something.** Either enforce it (an
   allowlist proxy, or a Windows Firewall / netns rule) or **refuse** the
   run that asked for it. `network=False` must be *true*, not *declared*.
4. **Wire the container backend.** `security/sandbox.py` `DockerSandbox`
   implements the same `RunSpec`; select it by availability, and when neither
   a container nor a job object is available, **refuse** — never degrade to
   unsandboxed execution (`README §3.5`).
5. `code/policy.py` — add an **authorizer branch for cluster/infra/deploy
   mutations** (`construction-first-audit.md:344-345`).

**Contracts.**

- `network=False` is **enforced or refused**, never ignored.
- A missing isolation primitive **refuses** the run. It never degrades.
- No tool output ever reaches the model with a secret in it.

**Gates.**

- `python/harness/code/eval/safety_cases.py` — add **S15**
  (network denied under `network=False` → `NETWORK_DENIED`) and **S16**
  (a secret in the environment is absent from a `shell_run` child's
  environment → `SECRET_BLOCKED`).
- `python/tests/test_shell_env_scrub.py` — new: `shell_run` cannot see
  `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `HARNESS_CALLBACK_TOKEN`.

---

### W10 — Distribution: a package, a registry, and a protocol

> **Closes:** O8 · **Moves:** Ext +0.06, ACI +0.05 · **ADR:** H289
> **Priority: 3 — the score is close; this is about reach.**

**Why.** Eclipse's extensibility is already above the field median: 14 hook
points, a 9,432-line skills system (versioned, contract-validated,
inert-until-promoted), 9,468 lines of hardened MCP with per-call
digest-bound approvals, a plugin system with a closed permission vocabulary,
a `delegate` tool, A2A, and an SDK. None of it is reachable by anyone outside
this repository.

**Work items.**

1. **Publish the harness as a package** — `black-eclipse-harness` on PyPI,
   with a small public API (`AgenticService`, `ToolRegistry`, the run
   contract). The app stays private; the runtime does not.
2. **Publish the tool schemas as an open registry.** Eclipse's finance tools —
   retrieval, research verification, comparability, receipts — are genuinely
   useful to other harnesses. Export them in a portable form (the same shape
   as an MCP tool manifest) so another harness can consume them.
3. **Speak ACP** (Agent Client Protocol) so Eclipse can be driven by Goose,
   OpenHands' Agent Canvas or a Claude Code session, and can drive them back.
   The 2026 field is converging on ACP; Eclipse should not be the only agent
   that cannot join.
4. **Ship a plugin** for at least one major host (opencode / Claude Code /
   Codex) that exposes Eclipse's finance tools to that host.

**Contracts.**

- The published package carries **no** app data, no vault, no credentials.
- The published tool schemas declare their own permission and effect class —
  a consumer inherits Eclipse's honesty, or it does not get the tool.

**Gates.**

- The package builds, installs into a clean virtualenv, and `import
  black_eclipse_harness` works.
- A second host can load the exported schemas and call one tool end to end.
- An ACP smoke: two hosts, one session.

---

## 4. Sequencing

```
WAVE A — remove the defects (parallel-safe, no new surface)
  W1  verify→repair in the graph      ─┐
  W2  narrow, don't replace            ─┼─ all three touch graph.py/agents.py
  W3  one edit primitive + landing     ─┘   → W1/W2 first (graph.py), W3 parallel
  W5  one search primitive                 (independent)
        │
        ▼
WAVE B — close the two dimensions that cap the score
  W4  repo map + auto context          ─┐
  W6  compaction + lazy tool loading   ─┴─ W6 needs W2's tool-set shape
        │
        ▼
WAVE C — make it real
  W7  ship, shrink, clean the record  (7a depends on W3 + W5 having merged
                                       the duplicates; 7b/7c are independent)
  W8  live evals + published numbers   (depends on W1 for the repair shape)
  W9  isolation + secrets              (independent of everything; do it
                                       anyway — it is a real hole)
  W10 distribution                     (depends on W7b's release process)
```

**Critical path:** `W2 → W6 → W8` for the Ctx/Eval points, and `W3 + W5 → W7a`
for the Ops points. **W3 and W5 must land before W7a's size budget can be
set** — merging the duplicates is what makes the ceiling meaningful.

**Do not start W7a before W3 and W5.** A size budget written against a
duplicated surface freezes the duplication in place.

**Parallelism.** W1, W3, W5, W9 and W10 touch disjoint files and can run in
separate worktrees. W2 and W4 both touch `graph.py` and `graph_context.py` —
serialise them.

---

## 5. The release gate

Every wave ends with the **one** gate (`README §3.8`):

```bash
cd Black-Eclipse-site
npm run check:all
```

which is: `prisma generate` → `tsc --noEmit` → `eslint .` →
`scripts/security-preflight.js` → `npm test` (vitest + pytest + the 14 eval
gates) → `npm run test:evals`.

Plus the wave-specific gates:

| Wave | Extra gates |
|---|---|
| A | `node scripts/test-evals.js`; the new `code/eval` shapes and safety cases |
| B | `node scripts/test-evals.js`; the compaction and schema-budget tests |
| C | `node scripts/size-budget.js`; `node scripts/check-adr-numbers.js`; `npm run test:smoke`; `npm run test:presets` (both are network-bound and are **never** in `npm test` — a human runs them before a tag) |

---

## 6. ADRs to write

The harness series continues from the highest number in use. **First read
`docs/harness/decisions.md` and take the numbers after the highest used** —
the series currently reaches **H279** (H280 is W2's), and seven numbers below it are
duplicated (see W7c-6).

| ADR | Subject | Workstream |
|---|---|---|
| ADR-H280 | A surface EXTENDS the agent's declared tools; it never silently REPLACES them | W2 (DONE 2026-10-20) |
| ADR-H281 | The verify→repair loop runs in the graph, and its outcome is a first-class state | W1 |
| ADR-H282 | One edit primitive, a mandatory stale guard, and an exact landing with a rollback | W3 |
| ADR-H283 | A repo map is deterministic, bounded and seeded into the first turn; freshness is measured | W4 |
| ADR-H284 | One search primitive, ripgrep-first, always reporting its engine | W5 |
| ADR-H285 | History is compacted by the model with a deterministic fallback; a tool surface is loaded on demand | W6 |
| ADR-H286 | The harness shrinks under a CI-enforced budget, and every decision number is unique | W7 |
| ADR-H287 | A published number is generated, reproducible and carries its provenance | W8 |
| ADR-H288 | `network=False` is enforced or refused; a shell sees no more environment than a sandbox | W9 |
| ADR-H289 | The harness ships as a package and speaks a protocol | W10 |

**ADR shape** (match `docs/harness/decisions.md`): `## ADR-H<n> — Title`
followed by **Decision.** / **Why.** / **Consequences.**

---

## 7. Explicit non-goals for Round 3

Inherits the roadmap's §6 and adds three of its own:

- **No new capability domain.** Round 3 makes the existing capability work.
  It does not add a domain.
- **No model change.** The provider-agnostic runtime stays; no default model
  moves; no provider is removed.
- **No weakening of the honesty rules to win a benchmark.** `UNMEASURED` stays
  `UNMEASURED`. If a harness that refuses to guess scores worse than one that
  guesses, **that is a scoring artifact to be published, not a rule to be
  broken.**

---

## 8. Definition of done

Round 3 is done when **all** of the following are true, and each is checked by
a command, not by a claim:

1. `npm run check:all` passes.
2. `node scripts/size-budget.js` passes at or under the committed budget, and
   `python/harness/` is at least **30% smaller** than on 2026-10-20.
3. `node scripts/check-adr-numbers.js` passes — no duplicate ADR number.
4. `docs/harness/benchmarks.md` exists, is **generated**, and contains a live
   number with model, commit, dataset checksum and grader version.
5. `code/eval/capabilities.py` reports **zero** classes in the `unmeasured`
   bucket, or names the class as retired.
6. A live run of the 53-task suite completes, and the repair loop fires
   inside the real graph.
7. `git tag -l` is non-empty; the tree is clean.
8. The scorecard in §1.1 has been **re-measured** by an outside reviewer
   against the same rubric — and if it did not reach 9.5, this document says
   so, with the number.

> Point 8 is the one that matters. Every other item in this plan is a
> *mechanism*. Point 8 is the only one that can falsify the plan.

---

## 9. Operating loop for a workstream

Same as `roadmap/README.md` §5:

1. Write the progress log `docs/harness/roadmap/progress/<workstream>-progress.md`
   with the gate commands as unchecked checkboxes.
2. Hand over the paste-ready prompt (§10) to OpenCode verbatim.
3. **Verify independently** — re-run every gate against the working tree.
   Never accept the progress log's claims. Record the numbers you observed.
4. Check for contamination (mtime vs. the start of your run) before calling a
   failure a regression.
5. Close the docs per `AGENTS.md`: append a dated `docs/CHANGELOG.md` entry,
   update the owning doc via `docs/NAVIGATION.md`'s trigger table, flip the
   workstream status, and update §1.1 if a score moved.

---

## 10. Paste-ready implementation prompts

One per wave. The workstream text above is the specification; these are the
instructions to hand to an agent.

### Wave A

> Work through workstreams **W1, W2, W3, W5** from
> `Black-Eclipse-site/docs/harness/roadmap/round-3-parity-plan.md`.
> Read §3 in full before touching code.
>
> Hard rules, from `AGENTS.md` and the roadmap invariants:
> - **One runtime.** New capability = new tools on the **existing**
>   `ToolRegistry`, driven by the **existing** `execute_run`. No second agent
>   loop, no second registry, no second model adapter.
> - **Prose is not a security boundary.** Permissions, path rules, command
>   allowlists and budgets are enforced in Python.
> - **File size ratchets.** `graph.py`, `persistence.py`, `main.py` are at
>   their limits. New logic goes in **new modules**; `graph.py` grows by
>   import, not by body.
> - **Never fabricate.** A number that was not measured is `UNMEASURED`.
> - **Zero-config keeps working.** A missing mechanism refuses honestly; it
>   never degrades to a less safe path.
> - Do **not** change the honesty invariants to make a gate pass.
>
> Order: W2 first (it is one function and everything else depends on the tool
> set shape), then W1, then W3 and W5 (they touch disjoint files and may run
> in parallel worktrees).
>
> For each workstream, implement the work items, add the named tests, and
> make the named gate pass. Then stop and report — do not start the next
> workstream without a report.
>
> Before reporting, run `npm run check:all` from `Black-Eclipse-site/` and
> `node scripts/test-evals.js`. Record the actual output. If a gate cannot
> pass, produce an **honest partial report** naming what is blocked — never a
> weakened gate.

### Wave B

> Work through workstreams **W4 and W6** from
> `Black-Eclipse-site/docs/harness/roadmap/round-3-parity-plan.md`.
>
> Preconditions: Wave A is merged and `npm run check:all` is green.
>
> Both workstreams change **what the model sees**. Two rules govern them:
> 1. **Deterministic or declared.** The repo map is deterministic — the same
>    tree produces the same bytes and the same hash. The compaction summary
>    is model-produced, so it is marked `computed`, fenced, and **never**
>    presented as user content; the deterministic fallback block is always
>    present alongside it.
> 2. **Bounded or refused.** Every budget is measured before the request. A
>    breach is a refusal, not a truncation. Never silently drop a tool
>    schema, a file read or a turn — if it does not fit, say so in the run
>    payload.
>
> The prompt-cache contract matters: `prompt_segments.py` keys the cache on
> segment **content hashes**. A repo map that changes must invalidate the
> cache; one that does not change must not. Add a test for both directions.
>
> Add the named tests, make the named gates pass, run `npm run check:all`,
> and report the actual output. If the compaction model call fails, the
> deterministic fallback must take over and the run must say so — that path
> is the important one, so test it by forcing the failure.

### Wave C

> Work through workstreams **W7, W8, W9, W10** from
> `Black-Eclipse-site/docs/harness/roadmap/round-3-parity-plan.md`.
>
> Preconditions: Waves A and B are merged; `npm run check:all` is green; the
> tree is clean.
>
> W7a (**shrink**) is the one that needs discipline: merge the duplicate
> implementations W3 and W5 identified, keep a deprecation shim for one
> release, and **do not delete a capability** — only a second implementation
> of a capability. Set `scripts/size-budget.json` from the *post-merge*
> tree, never from the pre-merge tree, and never raise a ceiling to make a
> commit pass.
>
> W8 (**publish**) has one rule: a published number is **generated**, never
> hand-edited, and carries its model, commit, dataset checksum and grader
> version or it is not published. A dimension that was not measured stays
> `UNKNOWN`.
>
> W9 (**isolate**) is independent of everything else and should be done even
> if the rest slips: `network=False` must be enforced or refused, a shell
> must see no more environment than a sandboxed command, and no tool output
> may reach the model with a secret in it.
>
> W10 (**distribute**) must not publish anything that carries app data, the
> vault, or a credential.
>
> Each workstream ends with its own gate. Run `npm run check:all` and report
> the actual output. Tag `v0.2.0` only after every gate in §5 of the plan is
> green, including the two network-bound ones (`npm run test:smoke` and
> `npm run test:presets`) that CI never runs.

---

## 11. Known risks

| Risk | Why it is real | Mitigation |
|---|---|---|
| **Deleting 30% of the harness breaks something nobody measured.** | The eval suite scripts the model out, so a broken path can still pass every gate. | The live lane (W8) must land **before or with** the first big deletion, not after. Reorder if needed. |
| **Compaction loses a decision the model needed.** | Compaction is inherently lossy in prose. | The dropped-turn ids and the deterministic candidates always survive; the compaction-quality eval asserts labelled decisions are still answerable. |
| **One edit tool is less capable than fifteen.** | The long tail of mutators covers real cases. | Keep `apply_unified_diff` and `write_file`; deprecate the rest with shims for one release; the `code_edit_contract` capability class must cover the shapes the old tools covered. |
| **A container backend cannot be assumed.** | Docker is not installed on this machine. | Selection by availability; refusal when neither backend exists (`README §3.5`). The default local path keeps the job-object sandbox. |
| **The live lane costs money on every PR.** | Real model calls. | A 12-task smoke on PRs, the full suite nightly; a documented budget; a provider-agnostic switch. |
| **The scorecard is self-assessed.** | The author is 90% of the history. | §8 point 8 requires an **outside** re-measurement. Until then, 7.18 stands as the published number, not 9.5. |
| **The plan is too big for one author.** | Ten workstreams, ~362k lines. | Waves are independent; W3, W5, W9 and W10 can run in parallel worktrees; the two points that need the most context (W6 compaction, W8 publication) are last, when the surface is smaller. |

---

## 12. Where the numbers came from

- **Harness surface** — measured: 1,315 Python files / 361,990 lines in
  `python/harness/`; 715 test files / ~7,001 test functions in `python/tests/`;
  1,382 TS/TSX files / 250,339 lines in `src/`; 365 vitest files / ~3,548
  tests. 961 FastAPI route decorators across 54 routers; 61 Next.js harness
  route handlers.
- **Git** — 551 commits on `main`, 841 across all refs, 757/47/37 by author,
  first commit 2026-06-22, no tags, `0.1.0`, `private: true`.
- **ADRs** — 282 `## ADR-H<n>` headings, 275 distinct, max H277; duplicates
  at H146, H160, H162, H242 (×3), H243, H244.
- **Tool surface** — 174 explicit `ToolDefinition(...)` sites plus ~312 names
  in shared constants across 61 `register_*_tools()` functions, plus dynamic
  MCP/plugin/skill tools; ≈450–550 distinct tools.
- **The coding-side audit** — every §2.1 and §2.3 line reference was read
  from the source on 2026-10-20. Where a doc and the code disagreed, the
  code was used (e.g. `phase-20` counts).
- **The field comparison** — 2026 leaderboards (SWE-rebench's agent column,
  SWE-bench Verified, OpenHands Index) and practitioner rankings
  (Alice Labs, Apr 2026; the OpenHands 9-agent ranking) for field selection;
  a six-project code-level harness study for the architectural comparison;
  the arXiv 2610.02001 result that the harness, not only the model, drives
  measured agent performance, for the weighting.
