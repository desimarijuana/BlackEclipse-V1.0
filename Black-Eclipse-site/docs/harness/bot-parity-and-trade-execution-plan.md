---
title: Bot parity and trade execution — plan
status: Proposed
last-verified: 2026-11-13
---

# Bot parity and trade execution — plan

**Ask:** "bot mode should be able to do everything the Eclipse Agent does, and it
should execute trades."

That is two different problems and they must not be solved together:

- **Capability** — which tools a bot may *call*. Safe to grant; already almost
  complete.
- **Authority** — what a bot may *decide on its own*. Money. Must be an explicit,
  durable, revocable grant, never a sentence in a prompt.

This document records what is already true (verified against the code, not the
docs), the five gaps that actually matter, and a phased plan.

## Decision (2026-11-13)

**Live, not demo. Approval is per order by default; autonomy is a tier the bot
must earn.**

- **L0 (default, this deliverable).** The bot proposes via `order_preview`; the
  operator approves each live order and types the LIVE phrase. No new money
  authority.
- **L1 (rehearsal).** A demo mandate lets the bot submit unattended with no money
  at risk.
- **L2 (autonomy with a leash) — added later, gated.** A live mandate pinned to
  `botId` + `botVersion` on an armed connection, with caps. This is the "yolo"
  tier, and it is granted per bot **after** L0 has produced a scored track record
  in the advisory ledger. It is not a switch flipped at creation.

Sizing default is **risk-based with a stop required**: the bot computes size from
entry, invalidation and risk-per-trade, and states its inputs. A per-bot override
may pin a fixed size instead, in which case the bot may decline a trade but never
resize it. The mandate's `maxMargin` remains the hard ceiling in every mode,
enforced at submit rather than in the prompt.

The engineering risk therefore moves from "give a bot money" to "make a scheduled
run's proposal reachable when the operator is not sitting in a chat" — plus a
track-record gate before any bot is allowed to spend on its own.

---

## 1. What is already true

### 1.1 A bot already gets the interactive agent's full surface

`automation/dispatcher.py::_run_request` builds a `RunRequest` with
`agentId=action.agent_id or "eclipse-agent"` and **no tool narrowing**. Python
resolves the `AgentConfig` from its own presets, so a bot run gets the same
allowlist as a chat turn: market data, `get_orderbook`, `get_funding_rate`,
quant engine, stats, factor lab, portfolio construction/risk, `broker_*` reads,
`order_preview`, `order_submit`, advisory, decisions, guardrails, browser,
computer, video — plus `analysisEnabled=True` for the compute sandbox.

So "do everything the agent does" is **already ~true for read and compute tools**.
The real gaps are listed in §2.

### 1.2 Demo orders are already possible unattended

`order_submit` → `service.submit_order(..., mandate_id=...)`. The mandate is the
authorization: an operator-created, expiring grant with symbols, a margin cap,
an order count and a mode. `trade/authorizers.py` admits the call when a mandate
covers the symbol. **No approval card is involved.**

### 1.3 Unattended *live* orders exist, but only through Graph Studio

`graph_runtime/compiler.py` (lines ~233-266) requires, for a `trading.*` node in
live mode: the `allow_live_trading` grant on the run envelope, a `connectionId`,
and a **workflow-pinned live `mandateId`**. Together with an armed connection
(`trade/service.py::_assert_live_armed`) and `LIVE_MAX_TTL_SECONDS = 24h`
(`trade/mandates.py`), that is the one sanctioned unattended live path.

A bot has no equivalent: no grant field, and `order_submit` passes no
`workflow_id`, so a workflow-pinned live mandate fails `MANDATE_WORKFLOW_MISMATCH`.

---

## 2. The gaps that matter

### G1 — A bot has no approval channel (the biggest parity gap)

`graph.py` sets `pause_for_approval` only when `request.approvalMode == "ask"`.
Scheduled runs never set it. So an effectful tool in an unattended run is
**denied and retried**, where an interactive turn **pauses and asks**. The engine
already models the coarse version of this (`PermissionPolicy.requires_approval` →
execution `WAITING` → `POST /automations/executions/{id}/resume`), but the tool-level
card is not wired to it.

Consequence: a bot cannot do several things chat can, purely because nobody is
there to click. This is the gap that most deserves to be closed, and it is what
makes per-order live approval possible later.

### G2 — No workspace / autonomy on a bot → no code verbs

`Action` carries `workspace_root` and `autonomy`; the bot creation path never
sets either. The runtime's default-actor rule is "no workspace ⇒ no code
permission", so a `code-agent` bot gets refusals. Fine by default, but it means
"everything the agent does" is false for code work until the bot can be bound to
an approved workspace root.

### G3 — The create surface is narrower than the runtime

`bot_create` accepts `agentId` from a three-item enum while the UI and runtime
support every installed preset. It also has no fields for `execution`, `retry`,
`concurrency`, `limits`, `delivery` or `permissions`, even though
`AutomationDefinition` models all of them. Agent-created bots are therefore
under-configured relative to UI-created ones.

### G4 — Per-bot authority is modelled but unused

`PermissionPolicy` has `allowed`, `denied`, `requires_approval`,
`approval_scope`. The Bots UI exposes none of it, so there is no way to say "this
bot may read but never write" other than by choosing a different preset.

### G5 — The live gate is implicit, not explicit (corrected)

My first reading of this was wrong in one important way, and the correction
matters more than the original claim.

What is true:

- `order_submit`'s tool description says *"LIVE orders are never submitted by
  this tool"*, and `trade/authorizers.py` says *"There is no agent path for live
  orders"*. Neither statement was enforced by the authorizer: it resolved a
  mandate and called `mandates.covers(...)`, which checks connection, expiry and
  symbol **but not mode**.
- `service.submit_order` skips the typed phrase when a `mandateId` is present
  (`required = not bool(mandate_id)`), by design, because a mandate is the
  standing authorization.

What I initially got wrong:

- `create_mandate` does **not** accept an unpinned live mandate.
  `TradingMandateStore.create` requires both `workflowId` and `workflowVersion`
  (`MANDATE_WORKFLOW_REQUIRED`). The Trading Settings field is a hint because the
  store is the validator.
- Because every live mandate is therefore workflow-pinned, and the agent tool
  passes no `workflow_id`, `submit_order` reached `mandates.verify(...)` and
  refused with `MANDATE_WORKFLOW_MISMATCH` **before** the phrase logic ran.

So there was **no exploitable agent path for live orders** — but only as a side
effect of the workflow pin, not because anything checked the mode. The gate was
real and implicit rather than stated and explicit. That is worth fixing for two
reasons: a future edit that loosens the pin (a bot-pinned mandate, P5) would
silently open the path, and the refusal the model saw (`MANDATE_WORKFLOW_MISMATCH`)
did not say "live is not allowed here".

The fix, therefore, is defence in depth and clarity, not plugging a hole:

- the authorizer resolves the connection's `mode` and refuses non-demo outright;
- `mandates.covers` takes the mode, so a mandate cannot authorize the wrong mode;
- `order_submit` re-checks the mode in the handler (`LIVE_ORDER_REFUSED`), so the
  handler does not depend on the wrapper being installed;
- the two descriptions now match what the code actually does.

The lesson recorded for P5: when a bot-pinned live mandate is introduced, the
mode check in the authorizer is the thing that must change — deliberately, in one
place — instead of a pin check failing for the wrong reason somewhere else.

---

## 3. Design principles

1. **Authority is a record, not a sentence.** A bot's power to order is a row
   with a scope, a cap, an expiry and a revoker.
2. **Capability ≠ authority.** Granting the tool surface is safe. Granting money
   is a separate, per-bot, inspectable decision.
3. **Deny wins, fail closed, name the code.** Every refusal has a stable code
   (`LIVE_GRANT_MISSING`, `BOT_MANDATE_UNPINNED`, `BOT_VERSION_STALE`, …).
4. **Exits are never blocked.** `position_close` / `position_modify` stay
   arm-free and mandate-free. An expired grant must never trap a bot in a
   position.
5. **Every order is traceable** to (bot id, definition version, execution id,
   run id). `BrokerOrder` already records `runId`; it must record the automation
   too.
6. **Reuse, don't rebuild.** The mandate table, guardrails, daily-loss brake,
   cooling-off, order-count, margin cap and kill switch already exist. No second
   order path.
7. **Live is a layer**, not a switch: arm + live mandate + bot pin + version pin
   + cap, all at once, any one missing → refusal.

---

## 4. Phases

### P0 — Make the live gate explicit — **DONE (2026-11-13)**

Small, urgent, testable. Defence in depth plus truthful descriptions; see the
corrected G5 for why this was not an exploitable hole.

- `trade/authorizers.py`: resolves the connection's `mode` and refuses anything
  that is not `demo`, so the agent/bot tool path has no live route by
  construction. The mandate check now receives the mode.
- `trade/mandates.py::covers`: takes `mode` and refuses a mandate whose mode does
  not match. Omission is not a bypass on the trade path.
- `trade/tools.py::order_submit`: refuses a non-demo connection in the handler as
  well (`LIVE_ORDER_REFUSED`), so a missing authorizer wrapper cannot send one.
- The mandate store already required a live pin
  (`MANDATE_WORKFLOW_REQUIRED`, id + version); `create_mandate` does not restate
  that rule with a weaker one — the store stays the single authority.
- Both stale statements corrected.
- Tests: `python/tests/test_broker_agent_trade.py` (live refused, unknown mode
  refused, demo unchanged, exits still allowed on live) and
  `python/tests/test_trade_mandate_mode.py` (mode is part of coverage).

### P1 — Capability parity

- `automation/dispatcher.py`: pass `approvalMode="ask"` for bot runs whose
  definition opts in; map the run's pause onto the engine's existing `WAITING`
  execution state so it resumes with `POST /automations/executions/{id}/resume`.
  Verify the mapping end-to-end before exposing it — do not assume it.
- Bot definition + dialog: `workspaceRoot` (chosen from `TrustedRoot`) and
  `autonomy`. No workspace keeps the current fail-closed behaviour.
- `bot_create` / `bot_update` parity: any installed `agentId` (validated against
  `AGENT_PRESETS`), plus `execution`, `retry`, `concurrency`, `limits`,
  `delivery`, `permissions`.
- Bot detail: per-bot tool deny list + limits + delivery, over `PermissionPolicy`.
- Tests: same tool names resolve for a bot run and a chat run; a `code-agent` bot
  with no workspace still refuses code verbs; a denied tool stays denied even if
  allowed.

### P2 — Bot demo execution (optional rehearsal, not the deliverable)

Only if you want a safe dry run of the same objective before pointing it at live.
No new authority is introduced: it is the existing demo mandate path, so the only
work is making it explicit for a bot.

- `TradingMandate` may gain `botId` + `botVersion` if we want a mandate that only
  one bot can use; otherwise any demo mandate already works.
- Pre-trade invariants worth having regardless of mode: sizing from the risk
  engine, a stop when configured, no market order without a quote this run.
- Delivery: `render_run_report` first line states `filled` / `refused` + ticket.
- Tests: mandate covers the symbol; per-run cap; kill switch cancels; ledger row
  carries the automation id.

### P3 — Bot live proposals with per-order approval (**the deliverable**)

No standing authority **in this deliverable** (autonomy is P5, gated). The bot
decides *what* to propose; the operator decides *whether* it fills.

- The bot's objective is allowed to call `order_preview` on a live connection. It
  already can (READ, never sends), so this is mostly policy text and guardrails,
  not new plumbing.
- **Reachability is the real work.** A scheduled run must surface its proposal
  where the operator will see it:
  - the run report's first line says `AWAITING APPROVAL` with the approval id and
    the exact intent, via `render_run_report`;
  - the in-app notification deep-links to the approval (`/trading/approvals`,
    or the existing trade approval surface);
  - the approval stays valid after the run ends — it is a durable row, not a
    chat-local card. Verify the expiry window is long enough to survive an
    overnight bot; if not, make it explicit in the report.
- One live order per approval, bounded by the existing single-use digest. A
  stale approval dies with the digest.
- The bot may prepare the bracket (stop/target) and the size, but the size is
  computed by the risk engine and stated in the approval summary, so the
  operator approves numbers, not prose.
- Kill switch, guardrails, cooling-off and the daily-loss brake are unchanged;
  they apply at submit time, after approval.
- Optional later, only if asked: a "prepare and approve" flow that lets the
  operator approve from the notification without opening chat.

Tests: a scheduled run creates an approval and sends nothing; the report names
it; approving later fills it; a changed intent digest cannot reuse the approval;
a refused preview never creates an approval; a bot cannot reach `order_submit`
on a live connection (P0 regression).

### P5 — Autonomy tiers (the "yolo" tier, gated)

A bot's authority is a level, not a boolean. The level is a property of the
*definition*, versioned, and shown on the bot.

| Tier | May do | Human gate |
|---|---|---|
| **L0** | `order_preview` only — exact intent, size, bracket | one approval per live order |
| **L1** | `order_submit` on a **demo** mandate | none; no money at risk |
| **L2** | `order_submit` on a **live** mandate pinned to this bot | none until a cap trips |

**The leash on L2** (every item required, all enforced in code):

1. connection `mode=live`, **armed** (typed phrase, magic > 0, `maxMargin` > 0,
   Algo Trading on, TTL ≤ 8h — `arm_connection` already enforces this);
2. live mandate pinned to `botId` **and** the bot's current `botVersion`; an
   objective edit bumps the version and invalidates the grant;
3. `maxOrders` and `maxMargin` on the mandate; a per-run order cap on the bot;
4. daily-loss brake and money guardrails unchanged (they run at submit);
5. max open positions per bot, and a cooldown between entries;
6. risk appetite band (`conservative | normal | aggressive`) mapping to
   risk-per-trade, position count and orders/day. The bot may choose inside the
   band, never outside it;
7. kill switch covers the bot's orders by magic, and revoking the mandate stops
   the next order immediately.

**Sizing.** `sizingMode: risk_based | user_fixed` (default `risk_based`).
`risk_based` requires a stop on every order and states the inputs it used
(entry, invalidation, risk amount, contract size). `user_fixed` lets the bot
decline a trade but never resize it.

**Earning L2.** L0 runs first. The advisory ledger already records each
recommendation with its method, horizon and `dueAt`, and scores the outcome. L2
is offered only when that scored record exists for the bot — the UI states the
window it used. A bot with no track record cannot be granted L2; a bot whose
score degrades can be demoted to L0.

**Why not "based on its mood".** A mood is not debuggable. After a loss the only
useful question is "which rule admitted this trade?", and a risk-appetite band in
a versioned definition can answer it. A prompt-derived feeling cannot.

**Honest limits of L2.** Guardrails bound size, exposure, rate and loss — they do
not judge whether the trade is *good*. A stale quote, a misread symbol or a
degraded model still passes every cap. That is exactly why the tier is gated on a
scored record rather than granted at creation, and why the kill switch is one
click.

Tests: each precondition missing → named refusal; version bump invalidates; disarm
blocks mid-day; cap trip stops the next order; a demoted bot cannot submit;
`risk_based` refuses an order without a stop; `user_fixed` cannot be resized.

### P4 — Observability and reconciliation

- `BrokerOrder` + execution timeline carry `automationId`, `executionId`,
  `automationVersion` (extends the existing `runId`/`nodeId` traceability).
- Advisory Ledger records the recommendation that produced the order, so a bot's
  hit rate is scoreable, not asserted.
- Metrics: orders submitted/refused per bot, refusals by code, remaining mandate
  capacity.

---

## 5. Order of work

P0 is done. P1 (approval channel + capability parity) is next because P3's
reachability depends on a scheduled run being able to surface something the
operator can act on. P3 then makes a bot's live *proposal* reachable. P4
(traceability) is what makes P5 grantable at all — **L2 is gated on the scored
advisory record that P4 produces**, so P5 cannot precede it. P2 (demo rehearsal)
supports both and can land in any order.

Sequence: **P0 → P1 → P3 → P4 → P5**, with P2 opportunistic.

---

## 6. Non-goals

- No market-wide LLM screener (unchanged; see `automation-engine.md` cost note).
- No second order engine, mandate table or guardrail stack.
- No unattended live order **without a leash**: L2 always has an armed connection,
  a version-pinned mandate, caps, a daily-loss brake and a kill switch. There is
  no un-capped autonomy tier and no "mood" input.
- No claim that a bot is 24/7 without a resident host (`docs/DEPLOYMENT.md`).
- No retry of an ambiguous `order_send` (unchanged).
- No change to the interactive manual path: `order_preview` card still fills.

## 7. Decisions

Resolved 2026-11-13:

1. **Scope** — live, not demo. Demo stays as rehearsal only.
2. **Default live authorization** — per-order approval (L0). The bot proposes,
   the operator approves and types the LIVE phrase.
3. **Autonomy** — added as P5 with three tiers (L0/L1/L2). L2 is granted per bot
   only after a scored advisory track record, and is bounded by a version-pinned
   live mandate, caps, the daily-loss brake and the kill switch.
4. **Sizing** — `risk_based` by default with a stop required on every order;
   `user_fixed` as a per-bot override where the bot may decline but never resize.

Still open:

5. **Approval lifetime** — how long an L0 proposal stays approvable when the
   operator is away (a bot at 03:00, read at 09:00)? Drives the approval expiry
   and the notification copy.
6. **Risk basis** — account equity on the connected broker, or the portfolio
   engine's measured portfolio? They can disagree; the proposal must state which
   one produced the size.
7. **Track-record threshold** — how many scored decisions, over what window, at
   what success rate, before L2 is offered.
8. **Caps** — default max loss per approved order, max open positions per bot,
   and the numbers behind conservative/normal/aggressive.

## 8. Evidence index

| Claim | Where |
|---|---|
| Bot inherits the agent's allowlist | `python/harness/automation/dispatcher.py::_run_request` |
| Approval pause needs `approvalMode="ask"` | `python/harness/graph.py` (~L677) |
| Demo mandate is the unattended authorization | `python/harness/trade/authorizers.py`, `trade/tools.py::order_submit` |
| Live needs grant + pinned mandate | `python/harness/graph_runtime/compiler.py` (~L233-266) |
| Arm requirements | `python/harness/trade/service.py::arm_connection` |
| Mandate scope + TTLs | `python/harness/trade/mandates.py` |
| Guardrails / daily brake / cooling | `python/harness/trade/service.py::submit_order` |
| Current doc stance | `docs/trading.md` (P2/P6), `docs/fiduciary-advice.md` |
