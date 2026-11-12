---
title: Hermes vs Eclipse — Executive Summary
status: Current
last-verified: 2026-11-12
evidence-window: Eclipse working tree + NousResearch/hermes-agent @ 72c8803 (2026-11-12)
---

# Hermes vs Eclipse — Executive Summary

## Scope and method

This is a read-only architecture investigation. No production code, schema, or
runtime setting was changed. Evidence was taken from the working tree of
`Black-Eclipse-site/` and from a sparse clone of the official
`NousResearch/hermes-agent` repository at commit `72c8803` (2026-11-12).

Two limitations are stated up front:

1. **There is no official `NousResearch/hermes-code` repository.** GitHub
   returns 404 for that name. "Hermes Code" in public usage is either (a) the
   coding posture inside Hermes Agent (`_CODING_TOOLS` in `toolsets.py`:
   file/terminal/patch/search/browser/vision minus messaging, TTS, image
   generation, cron, kanban and computer use), or (b) third-party community
   skills such as `bobvane/hermes-code-agent` (MIT, not affiliated with Nous).
   This report compares against **Hermes Agent**, and treats its coding posture
   as the "Hermes Code" surface of record.
2. Hermes is a very large, fast-moving codebase (2,109 Python files / ~664k
   lines in the core directories inspected; 8,137 Python test files in the
   repository tree). Claims below are tied to the files cited. Where a claim is
   inferred from a doc rather than code, it is labelled as such.

## Overall verdict

**Eclipse is the stronger financial system and the stronger reliability
system. Hermes is the stronger general-purpose agent harness.**

That split is not a wash. Hermes has spent years hardening the things that make
an agent pleasant and resilient in daily use: provider failover, credential
pools, usage-anchored context compression, parallel tool calls, progressive
skill disclosure, background delegation, and a coherent autonomy surface
(`/goal`, `/loop`, `/heartbeat`, cron, kanban). Eclipse has spent its effort on
the things that make an agent *trustworthy in finance*: source authority,
evidence obligations, deterministic calculations, run leases and fencing,
at-most-once effects, a policy gateway, audit chains, and a measured
evaluation gate.

The correct strategic move is **not** to rebuild Eclipse as Hermes. It is to
graft the best general-purpose harness mechanics onto Eclipse's financial
substrate, while keeping Eclipse's run kernel, policy seam, evidence model, and
domain engines exactly where they are.

## Where Hermes is materially better

| Area | What Hermes actually does | Why it matters to Eclipse |
|---|---|---|
| **Provider resilience** | A 40+ reason `FailoverReason` classifier (`agent/error_classifier.py:35-68`), mid-session fallback providers, credential pools, three API modes (`chat_completions`, `codex_responses`, `anthropic_messages`), interruptible calls, and per-task auxiliary models (`agent/auxiliary_client.py`). | Eclipse's `ModelRuntime.invoke` implements circuit breakers and fallbacks (`model_runtime/runtime.py:454`), but the live graph calls `step.invoke_model_step` and only `record_step`; `_FALLBACK_CLASSES` and `stream_for_graph` are effectively unused on the path that matters. This is the single largest reliability gap. |
| **Context economics** | Two compression layers (85% gateway hygiene, 50% in-loop), provider usage anchors, tool-result pruning before summarisation, cache-stable three-tier system prompt, compression failure cooldown ladder (60s→300s→900s), deterministic fallback summaries, prepared-ahead compaction, session lineage. | Eclipse uses a 4-chars/token estimate, 20 turns / 40k chars, deterministic compaction by default, and one overflow retry only at step ≤ 1 (`graph.py:2553-2611`). Long financial research runs hit this wall. |
| **Tool concurrency** | Up to 8 concurrent tool workers per batch, ordered result insertion, interactive-tool serialisation, per-batch timeout, start-order gate (`agent/tool_executor.py:136`, `_ConcurrentBatch` at `:1336`). | Eclipse's `tools_node` executes sibling tool calls sequentially (`graph.py:997`). A 6-source financial retrieval turn pays 6× latency. |
| **Tool disclosure** | Default-on progressive disclosure with BM25/stemming search, tiered listings, batch `tool_call`, bridge unwrapping, and normal hooks/approvals on the underlying tool (`tools/tool_search.py`, `website/docs/user-guide/features/tool-search.md`). | Eclipse has `tool_search`/`tool_invoke`, but it is lexical, read-only for `tool_invoke`, and **off by default** (`HARNESS_LAZY_TOOLS=1` required; `tool_surface.py:39-44`). With >1,000 tool definitions, schema cost is a real tax. |
| **Skills ergonomics** | A mandatory skill index in the volatile prompt band, `skill_view` progressive disclosure, agent-managed create/patch/write_file/delete, `/learn`, a background LLM **curator** that consolidates narrow skills into umbrellas, and a Skills Hub (`agent/prompt_builder.py:1240+`, `agent/curator.py:292-475`). | Eclipse has 91 skills, versioning, evaluation, learning candidates, and `skill_list`/`skill_view`; but matching is keyword-only (`registry.discover:682`), evaluation is static rather than behavioural, and maintenance auto-archive is off by default. Hermes closes the loop more often. |
| **Autonomy UX** | `/goal` with a judge model, completion contracts, deterministic quality gates, `/loop` with self-pacing, `/heartbeat`, event-triggered cron, no-agent script jobs, and a kanban board (`website/docs/user-guide/features/goals.md`, `loops.md`, `heartbeat.md`, `cron.md`). | Eclipse has jobs, automations, tasks, goals and a Fabric, but no in-session "keep working until this is done" loop. Users must re-prompt. This is the biggest product-level gap. |
| **Delegation ergonomics** | `delegate_task` batch (up to 10), async top-level completion, `output_schema` validation with one bounded repair turn, image forwarding, lifecycle API with steer/cancel/reconnect (`tools/delegate_tool.py`, `website/docs/user-guide/features/delegation.md`, `subagent-lifecycle-api.md`). | Eclipse's delegation/spawn/Fabric is more durable and more governance-heavy, but less pleasant: no schema-repair handshake, no steering, no background completion into the chat. |
| **Filesystem safety net** | A shared shadow-git checkpoint store, automatic snapshots before `write_file`, `patch` and destructive terminal commands, `/rollback`, diff and single-file restore (`tools/checkpoint_manager.py`, `website/docs/user-guide/checkpoints-and-rollback.md`). | Eclipse has worktrees, fs transactions and git safety, but no user-facing "undo the agent's file changes" surface. |
| **Channel reach** | 20+ messaging platforms from one gateway process with pairing, delivery obligations, cross-platform session continuity. | Eclipse has Slack/Discord/Telegram/Teams/Lark/email/webhooks, but not the same breadth or delivery durability. |

## Where Eclipse is materially better

| Area | Evidence | Why it is a durable advantage |
|---|---|---|
| **Run durability** | `run_lease.py` (claim/epoch/heartbeat/fencing), `run_lineage.py` (checkpoints, durable message cursor, tool idempotency), `run_effects.py` (at-most-once effect ledger with `unknown` as a first-class outcome), `run_recovery.py`, `run_watchdog.py`. | Hermes persists before tool side effects and has session admission ledgers, but it has no run-level lease/fencing/effect ledger and no resumable agent run. Eclipse can survive a crash mid-tool and avoid duplicate irreversible effects. |
| **Policy and security** | `security/gateway.py` (risk → floor → policy → capability → approval), `security/effect_tokens.py`, `security/audit.py` hash-chain, sandbox profiles that refuse an unenforceable promise, tenant isolation. | Hermes' security is command-pattern approval plus optional container isolation; `approvals.mode: off` / `/yolo` disable prompts. That is appropriate for a personal coding agent, not for money movement. |
| **Evidence and provenance** | `retrieval/authority.py`, `market/verification.py` (authority scores, lineage-independent cross-checks, never average conflicts), `research/claims.py`, `research/receipt.py`, `research/release_gate.py`, `finance_facts/enforce.py`. | Hermes has web search/extract and generic memory; it has no notion of an unmet fact leg, a data-type authority row, or a finance number that must trace to a handle. |
| **Deterministic finance and quant** | `quant/engine.py` (anti-lookahead event loop), `walkforward.py`, `multiple_testing.py` (Deflated Sharpe/PBO), `montecarlo.py`, `verdict.py` (grade caps), `portfolio/`, `ledger/`, `modeling/`. | Hermes would write Python per task; Eclipse guarantees the same inputs and seed produce the same statistic. |
| **Broker execution gate** | `trade/authorizer.py` (digest-bound single-use approval, typed phrase, cooling-off), `trade/service.py:447` live arming, magic-scoped kill switch, `trade/reconcile.py`. | Hermes' approvals are generic tool confirmations, not order-bound execution controls. |
| **Observability and evaluation** | `observability/` span tree, SLO gate, failure taxonomy, `evaluation/` (real-runtime runner, 17 graders, critical dimensions, contamination controls, baselines, replay), generated `scorecard.md` tied to run IDs. | Hermes has logs, product metrics, insights and trace upload; no OpenTelemetry/Langfuse/Sentry exporter was found in the inspected modules, and its `evals/` are 33 scenario scripts rather than a scored corpus with statistical gates. |

## The ten best ideas to take from Hermes

Ranked by expected value to Eclipse, not by how easy they are:

1. **A live model gateway with classified failover, credential pools, and a
   streaming watchdog.** Use Eclipse's existing `ModelRuntime` instead of
   bypassing it.
2. **Usage-anchored context compression and cache-stable prompt tiers.**
   Replace the 4-chars/token guess with the provider's reported usage plus a
   bounded delta; make compaction a ladder, not a single attempt.
3. **Parallel sibling tool execution with ordered results and effect-safe
   scheduling.** Keep Eclipse's policy seam; add concurrency at the tool node.
4. **Default-on, tiered tool disclosure with real search.** Turn
   `tool_search` into the primary long-tail surface, not an opt-in.
5. **A skill curator plus behavioural skill evaluation.** Eclipse already has
   the ledger, versions and candidates; add consolidation and execution-based
   promotion.
6. **An in-session goal/loop/heartbeat engine with deterministic quality
   gates.** This is the autonomy layer Eclipse lacks, and it can sit on top of
   existing jobs/tasks rather than adding a second scheduler.
7. **A shadow-git checkpoint and `/rollback` surface for file mutations.**
   Complementary to Eclipse's run checkpoints, not a replacement.
8. **Delegation v2: background completion, `output_schema` repair, steering,
   and per-child worktrees.** Keep Fabric as the execution plane.
9. **Tool guardrails: identical-call, cycle and stall detection with a
   controlled halt.** Eclipse has per-turn duplicate suppression and recovery
   nudges; this is stronger.
10. **A memory/context provider plugin contract.** Eclipse's memory is deeper
    than Hermes' built-in memory, but Hermes' provider boundary is cleaner and
    would let Eclipse plug external memory without touching the core.

## What not to copy

- **Do not replace Eclipse's run kernel with Hermes' loop.** Eclipse's
  lease/fencing/checkpoint/effect ledger is strictly more correct for
  long-running, money-adjacent work.
- **Do not replace Eclipse's security gateway with Hermes' approval regexes.**
  Adopt the approval UX and hardline floor ideas only.
- **Do not copy Hermes' monolithic module style.** `agent/context_compressor.py`
  (328 KB), `agent/conversation_compression.py` (248 KB),
  `agent/error_classifier.py` (100 KB) and `agent/agent_init.py` (118 KB) are
  the opposite of Eclipse's size-budget discipline.
- **Do not copy the 2,200-char `MEMORY.md` model.** Eclipse's structured
  memory with conflict resolution, authority, evidence links and retention is
  better for finance.
- **Do not copy Hermes' 70+ always-on tool surface.** Eclipse's contract and
  effect metadata are stronger; fix disclosure rather than duplicating tools.

## Most important opportunities (next 90 days)

1. **Make the live model path use the runtime that already exists** — failover,
   circuit breakers, credential pools, cost accounting (P0).
2. **Fix context economics** — usage anchor, prompt-cache-stable tiers,
   compression ladder, parallel tool calls (P0/P1).
3. **Ship an autonomy spine** — `/goal`-style judge loop with deterministic
   gates, plus `/loop` and heartbeat, reusing jobs/tasks (P1).
4. **Close the learning loop** — behavioural skill evaluation, curator,
   memory retrieval upgrade (BM25/hybrid), lesson injection feedback (P1).
5. **Harden the run kernel edges** — lease-aware watchdog, atomic checkpoints,
   pre-write effect ledger, event sequence ownership (P0).

## The strategic answer

If Eclipse takes the ten ideas above and keeps its financial intelligence, it
becomes something Hermes cannot easily become: **an auditable, self-improving
investment research and execution operating system**.

Hermes can browse a 10-K and write a plausible summary. Eclipse can retrieve the
filing under a declared authority and freshness policy, reconcile it against
other sources without averaging conflicts, compute the ratio deterministically,
attach the citation and the receipt to the claim, refuse an unsupported number
at the answer seam, grade a strategy with walk-forward and Deflated Sharpe, and
place an order only through a digest-bound, typed-confirmation, cooling-off
gate with reconciliation.

Add Hermes' harness mechanics and the result is an agent that can **run a
standing investment thesis for weeks**, monitor the portfolio, re-run the
evidence when a filing lands, learn which research procedures actually produced
correct answers, and stop itself when the evidence is insufficient — without
ever fabricating a number or duplicating an order.

The five engineering investments that matter most over the next 90 days are:

1. **Live model gateway** — failover, credential pools, streaming health.
2. **Context and tool economics** — usage anchors, cache-stable prompts,
   parallel tools.
3. **Autonomy spine** — goal judge + deterministic gates + loop/heartbeat.
4. **Learning loop quality** — curator, behavioural skill eval, hybrid memory
   retrieval, lesson outcome feedback.
5. **Run-kernel hardening** — lease-aware watchdog, atomic checkpoints,
   pre-write effects, event sequence ownership.

Everything else is secondary to these five.
