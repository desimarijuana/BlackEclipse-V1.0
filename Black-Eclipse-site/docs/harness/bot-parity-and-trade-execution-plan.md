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

0. **The bot conversation is the surface.** No new editor, panel or review screen.
   You configure a bot by talking to it, and you approve what it proposes in the
   thread where it proposed it, using the same cards the main chat already
   renders.
1. **Authority is a record, not a sentence.** A bot's power to order is a row
   with a scope, a cap, an expiry and a revoker.
2. **Capability ≠ authority.** Granting the tool surface is safe. Granting money
   is a separate, per-bot, inspectable decision.
3. **Deny wins, fail closed, name the code.** A refusal carries a stable code —
   existing ones stay (`MANDATE_WORKFLOW_REQUIRED`, `MANDATE_MODE_MISMATCH`,
   `LIVE_NOT_ARMED`), and new paths add theirs (`LIVE_ORDER_REFUSED` today;
   `BOT_VERSION_STALE` when P5 lands).
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

### P1 — Capability parity — **contract half DONE (2026-11-13)**

- **The approval channel is NOT `approvalMode="ask"` for a bot (verified, and my
  first plan was wrong).** `pause_for_approval` is consumed inside the run by the
  computer/browser/MCP/guardrail tools, which *block until the run deadline*, and
  `clarify` returns `no_interactive_user`. Setting it on a scheduled run would
  convert "deny fast" into "hang, then fail". A bot's real ask channel is already
  two things: the **execution-level** `permissions.requiresApproval` (engine marks
  the execution `waiting`, delivers a waiting notice, and
  `POST /automations/executions/{id}/resume` continues it) and **durable approval
  rows raised by a tool**, which is exactly what `order_preview` does. Do not set
  `approvalMode` on bot runs; expose `permissions.requiresApproval` instead
  (below).
- **`bot_create` / `bot_update` parity — done.** Any installed `agentId` (validated
  against `AGENT_PRESETS`; an unknown id is refused with the known list), plus
  `workspaceRoot`, `autonomy`, and the `execution`, `retry`, `concurrency`,
  `limits`, `delivery`, `permissions` blocks the UI already exposes. Blocks not
  supplied are omitted, so stored defaults are unchanged. Because the chat agent
  owns these tools, a bot is configured by talking to it.
- **No new screens. The bot conversation IS the surface.** Everything a user needs
  to do with a bot — configure it, talk to it, approve what it proposes — happens
  in that chat, with the same cards the main chat uses. There is no editor
  dialog, no settings panel, no separate review screen. Configuration is a chat
  request (`bot_update`); a proposal is a card in the thread.
- **Bot chat carries the same in-thread cards as main chat — done.**
  `TradeApprovalBanner` is now mounted in the bot composer (it already was in the
  main chat composer), so a pending `order_preview` is approved in the
  conversation where the bot proposed it. The generic `ApprovalCard` and
  `ClarificationCard` were already there.
- Tests: `python/tests/test_automation_bot_parity.py` (every installed preset,
  unknown refused, blocks carried, omissions preserved, update parity).

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

### P3 — Bot live proposals with per-order approval — **DONE (2026-11-13)**

No standing authority **in this deliverable** (autonomy is P5, gated). The bot
decides *what* to propose; the operator decides *whether* it fills.

- **The proposal is bound to its run, not parsed from prose.** `order_preview`
  passes `ctx.run_id` → `preview_order(run_id=…)` → `request_approval(run_id=…)`
  → the approval row's `requestedByRunId`. `approval_view` now exposes it.
- **Delivery reports the order.** `Dispatcher._run_agent` collects the pending
  trade approvals whose `requestedByRunId` is this run, hands them to the engine,
  and `render_run_report` puts them first:
  `AWAITING APPROVAL — BUY 0.10 EURUSD market · SL 1.0800 (good for 5 minutes)`
  followed by the approval id. A completed run with a pending order is never
  reported as "produced no result".
- **The in-app delivery names the bot**: the `automation.delivered` event now
  carries `botId` and `approvalIds`, so the workspace can take the operator to the
  right conversation.
- **The composer banner already picks it up** (mounted in P1, store-driven), so
  approval happens in place — no new screen.
- **The window is stated, not implied.** This is the important finding: a trade
  approval's TTL is **300 seconds** (`APPROVAL_TTL_SECONDS`). A 03:00 bot's
  proposal is dead by 03:05, and that is correct — a nine-hour-old market order is
  worse than none. So the report says how long is left, and says so plainly when
  the window has closed ("run the bot again") instead of implying the order still
  waits. A bot meant to be approved in the morning should be scheduled near the
  operator's open, not overnight; that is a schedule choice, not a bug.
- One live order per approval, bounded by the single-use digest.
- Kill switch, guardrails, cooling-off and the daily-loss brake are unchanged;
  they apply at submit time, after approval.

Tests: `python/tests/test_automation_trade_report.py` (12) — pending order first
line, seconds/minutes window, expired and missing expiry, multiple orders, plain
contract unchanged, delivery carries `botId`/`approvalIds`, artifact report,
dispatcher filters by run id, missing/broken broker layer tolerated.

### P5 — Autonomy tiers (the "yolo" tier, gated) — **DONE (2026-11-13)**

A bot's authority is a level, not a boolean. It lives on the definition as
`executionAuthority` (`automation/model.py::ExecutionAuthority`), so it is
versioned with the objective: an edit bumps the version and the live grant dies.

| Tier | May do | Human gate |
|---|---|---|
| **L0** (default) | `order_preview` only — exact intent, size, bracket | one approval per live order |
| **L1** | `order_submit` on a **demo** mandate | none; no money at risk |
| **L2** | `order_submit` on a **live** mandate pinned to this bot | none until a cap trips |

**The leash, as built** (`trade/authority.py` is the ONE place that answers
"may this bot place a live order?"; the handler and the authorizer both call it):

1. a **new bot is always L0** — `bot_create` refuses a tier above it;
2. raising to L1/L2 is a **single-use operator approval** (`bot_authority`), and
   **L2 additionally requires ≥30 scored advisory calls** for that bot's
   conversation — refused before the operator is even asked;
3. connection `mode=live` and **armed** (existing `arm_connection`: magic,
   `maxMargin`, Algo Trading, TTL ≤ 8h);
4. live mandate pinned to `botId` **and** the bot's current `botVersion`; a stale
   version is `BOT_VERSION_STALE`, and a workflow-pinned mandate cannot be
   borrowed (`MANDATE_BOT_MISMATCH`);
5. the mandate's `maxOrders`/`maxMargin` **and** the bot's own
   `maxMarginPerOrder` ceiling — a mandate above it is refused at creation
   (`MANDATE_ABOVE_BOT_CAP`);
6. `requireStop` (default on) — no stop, no order (`STOP_REQUIRED`);
7. position cap counting **only Eclipse's own** positions by magic
   (`POSITION_CAP_REACHED`), and a cooldown between entries (`COOLDOWN_ACTIVE`);
   an unreadable position book fails closed (`POSITIONS_UNAVAILABLE`);
8. daily-loss brake, money guardrails, cooling-off and the magic-scoped kill
   switch unchanged — they run at submit;
9. appetite band (`conservative 0.25%/1 pos/2 orders`, `normal 0.5%/2/4`,
   `aggressive 1%/3/8`) — the bot chooses inside it, never outside.

**Sizing.** `sizingMode: risk_based | user_fixed` (default `risk_based`),
`risk_amount(equity, appetite)` in `trade/authority.py`. `risk_based` requires a
stop on every order; `user_fixed` lets the bot decline but never resize.

**Why not "based on its mood".** A mood is not debuggable. After a loss the only
useful question is "which rule admitted this trade?", and the band answers it.

**Honest limits of L2.** Guardrails bound size, exposure, rate and loss — they do
not judge whether the trade is *good*. A stale quote, a misread symbol or a
degraded model still passes every cap. That is why the tier is gated on a scored
record and why the kill switch is one click.

**Creating the grant.** The mandate is created through the existing trading
surface/API with `botId` + `botVersion` on an armed live connection (the mandate
store requires a workflow OR a bot pin). No new screen: the tier change is a
one-click approval card in the bot's chat.

Tests: `python/tests/test_bot_execution_authority.py` (18) — defaults, every named
refusal, position cap counting only Eclipse's positions, cooldown, L0/L1 refusal,
new-bot refusal, approval gate, L2 record gate, tier lowering, mandate caps and
version pin, risk bands.

### P4 — Traceability — **core DONE (2026-11-13)**

- **`BrokerOrder` carries `automationId` + `automationVersion`** (additive columns
  with the existing `runId`/`nodeId`). `order_submit` derives the bot from the
  run's conversation (`bot-<automationId>`) and records the objective version at
  submit time, so a version bump is visible on the orders it produced.
- **`order_ledger` can be read per bot** (`automationId` filter; a bot asking about
  itself may omit it) and its text names `bot <id>@v<version>`.
- **The advisory link already existed** and needed no new write: `AdvisoryDecision`
  stores `runId` and `conversationId`, and an order stores `runId`, so
  "which recommendation produced this position?" is a join on the run. What P5
  needs from this — a per-bot scored record — is therefore readable today.
- **Not added: `executionId` on the ledger.** It would duplicate a fact that is
  one hop away (`automation execution.runId` → order.runId) and a bot's execution
  is 1:1 with its run. Recording it twice invites the two copies to disagree.
- **Not built: per-bot order metrics** (`submitted`/`refused` counts, refusal
  codes, remaining mandate capacity). The ledger makes them a query, not a new
  store; `GET /automations/metrics` is the place to add them when the Bots
  dashboard needs them.

Tests: `python/tests/test_trade_order_traceability.py` (6).

---

## 5. Order of work

**P0, P1, P3, P4 and P5 are done.** The full ladder exists: a bot proposes (L0),
may rehearse on demo (L1), and may fill live (L2) only under a bot- and
version-pinned mandate, behind an operator-approved tier and a scored track record,
with position/cooldown/margin caps and the kill switch.

Sequence: **P0 ✓ → P1 ✓ → P3 ✓ → P4 ✓ → P5 ✓**, with P2 (demo rehearsal mechanics)
covered by L1.

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
