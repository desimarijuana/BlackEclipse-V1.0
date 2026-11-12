---
title: Hermes vs Eclipse — Adoption Analysis
status: Current
last-verified: 2026-11-12
---

# Adoption Analysis

This document decides what to take from Hermes, how to take it, and what to
leave behind. "Adopt" does not mean "copy code". Most Hermes mechanisms are
entangled with Hermes' home layout, its 60-parameter `AIAgent`, its provider
stack and its session DB. The useful artifact is usually the **design**, not the
bytes.

---

## Licensing and dependency review

**Hermes Agent license:** MIT (`LICENSE`, "Copyright (c) 2025 Nous Research").
MIT permits use, modification, distribution and sublicensing provided the
copyright notice and permission notice are included. If Eclipse vendors any
Hermes source, it must:

- retain the MIT notice in the vendored file/directory,
- add a provenance note (repo URL, commit, original path),
- keep the Eclipse project's own license compatible (Eclipse's root `LICENSE`
  should be checked by the release owner before any vendoring), and
- avoid importing code whose transitive dependencies are incompatible.

**Dependency policy observed in Hermes:** direct dependencies are exact-pinned
`==X.Y.Z`, with provider-specific packages in extras (see `pyproject.toml`).
This is a supply-chain posture worth copying as a *policy*, not as a lockfile.

**No code copying is recommended for the following**, because the code is large,
path-coupled and would create a second ownership model:

- `agent/context_compressor.py` (328 KB) and `conversation_compression.py`
  (248 KB) — implement the algorithm against Eclipse's `history.py`,
  `context_budget.py` and `compaction.py`.
- `agent/error_classifier.py` (100 KB) — implement a smaller classifier over
  Eclipse's `model_runtime/errors.py` and `retry_policy.py`.
- `agent/tool_executor.py` (99 KB) — add a concurrent batch to Eclipse's
  `tools_node`; do not transplant the executor.
- `tools/delegate_tool.py` (58 KB) — extend Eclipse's `delegation.py` and
  `spawn/` with the missing semantics.

**Green-lit for direct reuse (with notice):**

- The shadow-git checkpoint *recipe* (single store, per-project refs, per-turn
  dedupe). Eclipse can implement it with `git` in `code/fs/`; no Hermes code is
  required.
- Small pure algorithms: BM25 tokenisation/stemming choices, compression
  cooldown ladder constants, tool-search tier thresholds. Eclipse already has
  its own BM25 in `eclipse_memory/hybrid.py`; prefer that.
- Hardline command patterns and the approval-card UX as a *requirements list*,
  not as code. Eclipse's policy gateway already has a stronger floor.

**Third-party:** `snowballstemmer` is BSD-3-Clause; `croniter` is MIT;
`openai` is Apache-2.0; `anthropic` is MIT. Eclipse already depends on
`croniter`-equivalent scheduling? It has its own `jobs/cron.py`; do not add a
second cron library. For stemming, Eclipse can use a small Snowball
implementation or keep its current normaliser.

**Hermes Code:** no official Nous repository exists (`NousResearch/hermes-code`
→ 404). The community `bobvane/hermes-code-agent` is MIT but is a *skill* that
wraps Hermes, not an official harness. Do not treat it as an authority for
architecture. The official coding surface is `_CODING_TOOLS` in `toolsets.py`
and the file/terminal/patch tools.

---

## Adoption table

| # | Hermes capability | How Hermes implements it | Eclipse equivalent | Gap | Proposed solution | Complexity | Priority | Expected impact |
|---|---|---|---|---|---|---|---|---|
| A1 | **Live model failover and credential pools** | `runtime_provider` + `error_classifier` (40+ reasons) + fallback chain + credential pool rotation; three API modes; interruptible calls | `model_runtime/runtime.py` has router/health/circuit/usage; `graph.py` bypasses `invoke` and calls `step.invoke_model_step` | Fallback/circuit/rate-limit logic is not applied to the real loop; one key per provider | Make `step.invoke_model_step` call a new `ModelRuntime.stream_for_graph` that owns candidate selection, retry, circuit, key rotation and usage; add `CredentialPool` per provider; unify retry knobs | High | P0 | Reliability, cost, uptime |
| A2 | **Usage-anchored context compression** | Provider `usage` + appended-delta anchor; 50%/85% gates; prune → summarise; protected tail; cooldown 60→300→900 s; deterministic fallback | `context_budget.py` 4-char estimate; `history.py` 20 turns/40k; `compaction.py` deterministic skeleton; overflow retry only step ≤ 1 | No provider anchor, no ladder, no cache-aware tail, overflow recovery only first step | Add `usage_anchor` table/field; compute `budget = provider_prompt_tokens + estimate(delta)`; implement ladder with cooldown and deterministic fallback; allow overflow recovery at any step if side effects are safe (or after a checkpoint) | High | P0 | Long-run reliability, token cost |
| A3 | **Parallel sibling tool execution** | ThreadPoolExecutor 8 workers, ordered results, interactive serialisation, batch timeout | `tools_node` sequential `for call in calls` (`graph.py:997`) | 6-source retrieval pays 6× latency; long tool turns risk the run deadline | Partition calls into read-only vs effectful; `asyncio.gather` read-only with `Semaphore(4–8)`; execute effectful in order; preserve result order; keep per-tool timeout/effect gates; add a batch deadline | Medium | P1 | Latency, success rate |
| A4 | **Default-on progressive tool disclosure** | BM25 + stemming, 3 tiers, listing budget 5% of context, `tool_search`/`tool_describe`/`tool_call`, bridge unwrapping, hooks on the real tool | `tool_surface.py` lexical, `HARNESS_LAZY_TOOLS` off; `tool_invoke` read-only | >1,000 tools inflate every prompt; long-tail tools undiscoverable | Reuse the existing `tool_search`; add a BM25 index over name/description/tags; make lazy mode default-on when advertised schema tokens exceed a threshold; allow `tool_invoke` for effectful tools only through the normal approval path; add tiered listing (names → descriptions → server summary) | Medium | P1 | Token cost, tool discovery |
| A5 | **Skill curator and `/learn` ergonomics** | Mandatory skill index; `skill_view`; `skill_manage`; `/learn`; background curator with deterministic prune + optional LLM umbrella consolidation; usage ledger | 91 skills, versioning, eval, learning drafts, `skill_list`/`skill_view`; keyword match; maintenance auto-archive off; no curator | Library grows without consolidation; discovery misses semantic matches; static eval gates auto-enable | Add a `skills/curator.py` that runs on idle (reuse `jobs/` or `self_improvement` cadence), proposes merges as **inert drafts**, requires operator approval, and records before/after diffs; add a `/learn` command handler that calls the existing `authoring.py`/`draft.py`; add usage-ranked + BM25/embedding matching | Medium | P1 | Skill quality, context cost |
| A6 | **Behavioural skill evaluation** | Hermes does not do this well; it relies on use-time patching. Treat this as an *improvement on Hermes*, not a copy. | `skills/evaluation.py` checks schema/permissions/tools/cases but never executes the skill; auto-enable of read-only learned skills is on by default | A learned skill can be enabled without ever running on a real task | Add an execution tier: run the skill's cases through `evaluation/runner.py` in a sandbox, score with existing graders, require ≥N cases and a pass threshold before `activate_version`; keep static checks as a fast pre-filter | Medium | P0 | Safety, quality |
| A7 | **Goal/loop/heartbeat autonomy** | `/goal` judge + completion contract + deterministic gates; `/loop` fixed/self-paced; `/heartbeat`; cron; kanban | `jobs/`, `automation/`, `tasks/`, `goals/`, `fabric/`; no judge, no in-session loop, no heartbeat | Users must re-prompt; no "keep going until done"; no standing objective | Add `autonomy/goal_runtime.py` on top of `tasks/` + `goals/`: objective + contract + gates + judge via a cheap model; continuation is a new run with the same goal; persist in `ChatSession`/`Goal` tables; add `/loop` and `/heartbeat` as thin gateways to the same engine; reuse `jobs` for durable schedules, not a second scheduler | High | P1 | Autonomy, usability |
| A8 | **Session search UX** | `session_search` shapes: discover/scroll/read/browse; FTS5 + trigram; lineage dedup; source demotion | Eclipse already has FTS5 `session_search`/`session_open` with rich filters (`memory_tools.py:301`, `persistence.py:963`) | Missing browse/scroll semantics and trigram/CJK; no "open whole session" shape | Add `mode` to the existing tool: `discover` (current), `scroll` (run_id + message_id + window), `read` (run id, head/tail), `browse` (recent); add trigram index for CJK; keep filters | Low | P2 | Recall, usability |
| A9 | **File checkpoint and `/rollback`** | Shadow-git store, per-project refs, per-turn dedupe, auto before write/patch/destructive terminal, list/diff/restore | `code/worktree.py`, `code/fs/transactions.py`, `git/` safety; no user-facing snapshot/rollback | A bad edit requires manual git recovery; no "undo agent changes" | Add `code/checkpoints.py` using one bare repo under `.black-eclipse/checkpoints`; snapshot before mutating tools; expose `checkpoint_list`, `checkpoint_diff`, `checkpoint_restore` (operator-approved); never replace run checkpoints | Medium | P1 | Safety, UX |
| A10 | **Delegation v2** | Async top-level completion, batch 10, `output_schema` + one repair turn, images, lifecycle API (status/wait/cancel/steer/result), per-child worktree | `delegation.py` (4 children, depth 2), `spawn/` (8, depth 2, 120k, blackboard), `a2a/`; synchronous merge; no schema repair/steering | Hard to fan out; parent must wait; no contract on child output; no steering | Add `delegate_async` / `delegate_status` / `delegate_steer` tools backed by Fabric jobs; add `output_schema` with one bounded repair; add per-child worktree option; keep deterministic claim merge; do not expose raw child transcripts | High | P2 | Throughput, quality |
| A11 | **Tool guardrails** | Identical-call threshold 3, cycle detection (period ≤ 4, history 64), result-stub detection, controlled halt, per-turn web/subagent caps | Per-turn duplicate suppression (`_stable_key`), recovery nudge, `TOOL_BUDGET_EXCEEDED`, anomaly loop detector | Repeated near-identical calls can burn the run; no cycle detection; no controlled halt | Port the *rules* into `tools.py`/`graph.py`: signature = canonical name+args+result hash; halt with a model-readable explanation after 3 identical / a detected cycle; emit a `tool.guardrail_halt` event; allow operator reset | Low | P1 | Cost, reliability |
| A12 | **Approval UX and hardline floor** | Approval cards, once/session/permanent, smart approval via aux model, user deny globs, hardline blocklist, unattended modes | `security/approval.py`, `mcp/approvals.py`, `grants.py`, `security/floor.py`; UI approval card exists | No session/permanent allowlist UX; hardline list is thinner; no "smart" low-risk auto-approve | Add approval scopes (`once|session|permanent`) to `ApprovalStore`; add `security/hardline.py` patterns from `approval_floors.py`; add optional smart-approve via a cheap model with a deny-by-default policy; keep digest binding | Medium | P2 | UX, safety |
| A13 | **Remote terminal backends** | local/docker/ssh/modal/daytona/vercel + plugin backends | local sandbox, Docker, AppContainer; no SSH/Modal/Daytona | Long-running cloud work cannot leave the host | Add an `execution/backends/` provider interface; implement SSH and one serverless backend first; require an explicit capability profile and no implicit host mounts | High | P2 | Scale, isolation |
| A14 | **Context/memory provider plugin SDK** | `MemoryProvider` ABC with prefetch/sync/session hooks; `ContextEngine` ABC | `memory_providers/protocol.py` exists; context engine is built-in | External memory is discovery-only; no context-engine plugin | Promote `memory_providers/protocol.py` to the public extension point; add a `ContextEngine` protocol; register both in `plugins/manifest.py`; keep native memory authoritative | Medium | P3 | Extensibility |

---

## Categorisation

### Directly reusable code

Only small, self-contained pieces are safe:

- The **shadow-git checkpoint algorithm** (commands and ref layout) — reimplement
  in `code/checkpoints.py`; no need to vendor 79 KB of `checkpoint_manager.py`.
- The **hardline command pattern list** — treat as requirements for
  `security/hardline.py`; Eclipse's existing floor is stronger structurally.
- The **compression cooldown ladder** constants and the idea of a deterministic
  fallback summary.
- The **tool-search tier thresholds** and the BM25 field weighting, if Eclipse's
  own `hybrid.py` BM25 is not sufficient.

### Adaptable architectural patterns

- Provider gateway with classified errors, candidate selection, credential
  rotation and a streaming watchdog.
- Usage-anchored budget with a bounded appended delta.
- Parallel tool batch with ordered results and interactive serialisation.
- Progressive disclosure with a listing budget proportional to context.
- Curator as a scheduled, ledgered, reversible job.
- Goal judge + completion contract + deterministic gates.
- Lifecycle API for subagents (status/wait/cancel/steer/result).
- Tool guardrail controller.
- Approval scopes and unattended modes.

### Ideas worth independently implementing

- **Behavioural skill evaluation** — Hermes is weak here; Eclipse's evaluation
  harness makes it feasible.
- **Evidence-aware goal judge** — the judge should consume Eclipse's
  `EvidenceLedger` and verifier registry, not just prose.
- **Financial heartbeat** — a heartbeat that watches a portfolio/thesis and
  triggers research only when a source or price crosses a declared condition.
- **Skill curator with financial guardrails** — never merge a skill that
  carries a compliance rule or a permission requirement without operator review.

### Deliberately avoid

| Hermes feature | Why not |
|---|---|
| **Replace run kernel with Hermes loop** | Eclipse's lease/fencing/checkpoint/effect ledger is strictly safer for money-adjacent work. |
| **2,200-char `MEMORY.md` as primary memory** | Eclipse's structured memory with conflicts, authority and evidence is better for finance. |
| **Command-regex security as the primary boundary** | Eclipse's gateway/floor/capability/effect-token chain is stronger. Use containers/OS isolation, not pattern matching, as the boundary. |
| **YOLO / `approvals.mode: off`** | Unacceptable for an agent that can reach a broker or a ledger. |
| **70+ always-on tools** | Eclipse's contract/effect metadata is an asset; fix disclosure instead. |
| **Monolithic 300 KB modules** | Violates Eclipse's size budget and makes audit harder. |
| **In-process subagent threads as the durability model** | Fabric jobs already exist and are more correct. |
| **Hermes' built-in memory extraction** | It is model-discipline-based; Eclipse's deterministic decision gate is better. |
| **Third-party `hermes-code-agent` skill** | Not official, narrow, and duplicates Eclipse's own code tools. |

---

## Mapping to Eclipse's existing seams

| Adoption | Eclipse seam to extend | Do not create |
|---|---|---|
| A1 model gateway | `step.py`, `model_runtime/runtime.py`, `retry_policy.py` | A second model client |
| A2 context | `context_budget.py`, `history.py`, `compaction.py`, `prompt_segments.py` | A second compressor |
| A3 parallel tools | `graph.py:tools_node`, `tools.py` | A second tool dispatcher |
| A4 tool disclosure | `tool_surface.py` | A second registry |
| A5/A6 skills | `skills/registry.py`, `draft.py`, `evaluation.py`, `self_improvement/` | A second skill store |
| A7 autonomy | `goals/`, `tasks/`, `jobs/`, `automation/` | A second scheduler |
| A8 session search | `session_index.py`, `memory_tools.py` | A second session DB |
| A9 file checkpoints | `code/fs/`, `git/` | A second VCS |
| A10 delegation | `delegation.py`, `spawn/`, `fabric/` | A second child runtime |
| A11 guardrails | `tools.py`, `graph.py`, `observability/anomaly.py` | A second tool loop |
| A12 approvals | `security/approval.py`, `grants.py`, `security/floor.py` | A second approval store |
| A13 backends | `terminal/`, `code/sandbox.py` | A second sandbox |
| A14 providers | `memory_providers/`, `plugins/` | A second memory service |

The rule is simple: **every adoption lands on an existing seam**. If a proposal
requires a new store, a new scheduler, a new loop or a new approval path, it is
not an adoption — it is a redesign, and it needs an ADR.

---

## Cost and risk summary

| Adoption | Main risk | Mitigation |
|---|---|---|
| A1 | Failover hides a persistent provider fault; cost blow-up | Health/circuit + per-run budget + explicit `fallback` event + cost cap |
| A2 | A bad summary loses evidence | Keep deterministic skeleton; protect tail; never compact an evidence ledger; record what was dropped |
| A3 | Effectful calls racing | Only read-only concurrent by default; effectful serialised; per-call effect token |
| A4 | Tool discovery misses a tool | Tiered listing + `available_sources` + a "no match is not a missing capability" hint |
| A5/A6 | Curator merges a compliance rule | Inert diff + operator approval + frozen paths + no deletions |
| A7 | Runaway token spend | Turn budget + wall clock + gates + pause on no-progress |
| A8 | Search recall leak across users | Keep scope filters; never drop `user_id`; redact |
| A9 | Snapshot store grows unbounded | Size cap + retention + excludes + prune |
| A10 | Children duplicate effects | Fabric idempotency + child budget + no operator inheritance |
| A11 | Guardrail false positive | Repeatable tools allowlist + operator reset + model-readable halt |
| A12 | Permanent allowlist too broad | Scope by program + args digest; expiry; audit |
| A13 | Remote host compromise | Explicit capability profile; no host mounts; network allowlist |
| A14 | External memory poisons prompts | Fence external results; native-first; `allow_external` default false |
