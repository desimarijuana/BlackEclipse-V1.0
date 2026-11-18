---
title: Trading Bots — implementation plan
status: Implemented (demo proven end to end; live path open, unproven)
last-verified: 2026-11-17
---

# Trading Bots — implementation plan

**Status:** the foundation is implemented (see "Implemented" below). P3–P5 items
that remain are listed at the end.

## Implemented (2026-11-17)

| Area | Shipped |
|---|---|
| Action kind | `run_strategy` (Python model/validation/dispatcher + TS types) |
| Authority | `ExecutionAuthority` exposed at creation; `execution_authority` is patchable in both spellings |
| Runner | `automation/trading_runner.py`: consent → session → freshness → multi-symbol scan → `LiveStrategyService.run_once` |
| Trials | `prepare` is mode-aware (shadow/demo/live), bot-pinned, and idempotent per bot |
| Auto mode | Standing consent stored on the bot; `prepare` renews it without re-typing the phrase |
| Live fence | `check_live_order` moved inside `BrokerService.submit_order` when `automation_id` is present; tested at the broker seam (L1 refused before the adapter, L2 sends once, stale version rejected) |
| Demo/live choice | the operator's LIVE authorization grants L2 in the same action (`_grant_live_tier`), still requiring an armed connection + typed phrase + mandate; demo is a choice, not a forced default |
| Full-chain test | `python/tests/test_trading_bot_e2e.py`: real runner → trial → broker → one order + ledger + position; same-bar dedupe; disarmed live refused before the adapter |
| Real terminal proof | **2026-11-17 demo fill**: bot `auto_21fb2c4a633340f7be2e` → MT5 ticket `11447256588` (EURUSD BUY 0.01 @ 1.09897), ledger `ord_e29c7a0e6b41` with `automationId`; details + the seven defects it exposed in `docs/trading-bot-live-testing-plan.md` |
| Signal data source | the broker's OWN bars (`copy_rates`) for a broker symbol, the gateway as fallback; the forming bar is dropped; `is_fresh` tolerates up to 3 h of broker clock skew |
| Ownership magic | every broker connection gets a stable non-zero `magic` (`trade/ownership.py`, applied on create and backfilled on read), so the kill switch can match Eclipse orders; proven scoped on the demo (magic 741879 cancelled, control magic 777 kept) |
| Lifecycle | pause/disable/archive/delete revoke mandates and stop the trial |
| Decisions | persisted on `AutomationExecution.decision`; rendered in run history + the trading panel |
| Learning | `src/lib/bots/trading/learning.ts`: failure patterns → one concrete proposal → operator consent → apply + re-prepare; the digest is also injected into a trading bot's chat turn |
| Visual teaching | bounded image attachments sent as **real image parts** (chat + scheduled runs) plus a prompt block that treats them as guidance, never market data |
| Multi-symbol | per-bar scan of the universe; the trading panel's **Find trades** runs the same scan and can adopt the actionable symbols |
| Tier | `src/lib/bots/trading/tier.ts` earns L1 after 20 shadow decisions; L2 needs ≥30 closed demo trades, 14 days and a positive edge |
| UI | Trading tab in New bot, Trading section in the bot detail, run-history decisions, Find trades |
| Agent trading | an agent bot can be granted a bot-pinned demo/live mandate (no trial) and the same standing consent; L0 proposes, L1/L2 fill |
| EUR/USD 1m starter | one-click seed (`eur-1m-seed.ts`): strategy `eurusd_m1_ema_rsi`, a 90-day 1m backtest, a shadow approval, a 60s automation, a shadow trial, then activation; the Trading panel grants demo/live consent once |
| Tests | 121 TS domain tests, 37 plain-Python policy checks, 62 pytest cases (policy + runner + validation + visuals + agent prepare + scan + broker fence + the 1m starter) |

Known limits (deliberate, see phases): no per-bar portfolio netting across bots;
external screener integration is not wired — the bot's own last-bar scan is the
find-trades source (and the panel can adopt its actionable symbols).

**Read with:** `docs/bot-mode.md` (what a bot is), `docs/trading.md` (broker
layer), `docs/quant-live-strategy.md` (signal + trial), `docs/strategy-studio.md`.

## 0. Scope

**In scope (v1)**

- A bot whose brain is a saved quant strategy version, executed on its schedule.
- The same bot can instead be an agent with trading tools (the "GrokBot" flavour).
- A trading envelope at creation: venue, mode, universe, capital, risk, authority.
- Demo and live execution through the existing broker path; shadow (no broker).
- Per-bot attribution, decision records, "why didn't it trade", kill switch.

**Out of scope (v1)**

- Intra-bar execution. Every decision is on the **last closed bar**.
- New venues. MT5 is the only adapter that can send; Alpaca/IBKR stay read-only.
- Portfolio optimisation across bots. A single cross-bot exposure cap is enough.
- Options, futures rolls, multi-leg strategies.
- A second order path. Never.

## 1. The run path

```
Automation (bot)                    existing scheduler / Run now
  trigger ─────────────────────────────┐
  action.type = "run_strategy"         │
  action.config = { strategy, venue }  ▼
                              automation/dispatcher
                                       │  (new branch)
                                       ▼
                            automation/trading_runner
      ┌────────────────────────────────┼────────────────────────────────┐
      │ 1. resolve pins (bot version, strategy version)                 │
      │ 2. session window + data freshness gate                         │
      │ 3. evaluate strategy on last closed bar  ──► quant/live.py      │
      │ 4. risk + sizing under band/caps         ──► quant/risk.py      │
      │ 5. submit / preview                       ──► trade/service.py  │
      └────────────────────────────────┼────────────────────────────────┘
                                       ▼
                    DecisionRecord ──► AutomationExecution.decision
                    Order/fill     ──► broker ledger (+ automationId)
                    Events         ──► run history, bot chat, notifications
```

Two invariants carried by the design:

1. **One order path.** The runner calls `BrokerService.submit_order` exactly like
   Quick Trade, the approval card and `trading.broker_order`.
2. **Every run leaves a decision.** No signal, closed session, stale quote, tier
   refusal — each is recorded with a code. A silent no-op is a bug.

## 2. Contracts (lock these before any code)

### 2.1 New action kind `run_strategy`

```jsonc
{
  "type": "run_strategy",
  "objective": "Trade the EMA trend on EURUSD, London session only.",
  "agentId": null,
  "config": {
    "strategyId": "ema_trend",
    "strategyVersion": "1.2.0",
    "mode": "shadow",                 // shadow | demo | live
    "connectionId": "",               // required for demo/live
    "symbols": ["EURUSD"],            // ⊆ strategy universe
    "timeframe": "H1",
    "volume": 0.10,
    "stopLossPoints": 150,
    "takeProfitPoints": 300,
    "maxOrdersPerDay": 4,
    "session": {
      "timezone": "Europe/London",
      "weekdays": [1, 2, 3, 4, 5],
      "start": "08:00",
      "end": "20:00"
    },
    "trialId": "live_ab12…",          // demo/live only, set at creation
    "dryRun": false                   // demo/live: preview only when true
  }
}
```

Field rules:

| Field | Rule |
|---|---|
| `strategyId` + `strategyVersion` | must resolve in the quant store; version is immutable |
| `mode` | `shadow` needs no connection; `demo`/`live` require a connection whose own mode matches |
| `symbols` | non-empty; every symbol must be tradable on the connection (broker symbol list) for demo/live |
| `timeframe` | one of the strategy's supported timeframes; v1 bar-close only |
| `maxOrdersPerDay` | 1–20; becomes the mandate's `maxOrders` |
| `session` | optional; closing the window never closes a position |
| `trialId` | `demo`/`live` only; the mandate lives on the trial |

Shared tooling (not new): `ExecutionAuthority` on the definition.

```jsonc
"executionAuthority": {
  "tier": "l1",                 // l0 propose | l1 demo fills | l2 live fills
  "appetite": "conservative",   // conservative | normal | aggressive
  "sizingMode": "risk_based",   // risk_based | user_fixed
  "requireStop": true,
  "maxOpenPositions": 1,
  "maxMarginPerOrder": 500,
  "cooldownS": 900
}
```

Who enforces what — this matrix is the safety contract:

| Limit | Lives on | Enforced by |
|---|---|---|
| tier / appetite / stop / positions / cooldown | `ExecutionAuthority` | `trade/authority.py` at submit + mandate creation |
| symbols / margin / order count / expiry / mode | mandate | `trade/mandates.py` |
| maxMargin / maxVolume / spread / allowlist / daily-loss | connection `TradePolicy` | `trade/policy.py` |
| money caps, crisis mode, cooling-off | guardrails | `finance_guardrails` |
| session window, freshness, one-position, bar idempotency | bot config + runner | `automation/trading_runner.py` |

The bot may only be **stricter** than the connection. It can never loosen a
policy, and the UI must render the effective minimum, not the bot's wish.

### 2.2 Decision record (new, persisted)

```jsonc
{
  "botId": "aut_…",
  "botVersion": 3,
  "strategyId": "ema_trend",
  "strategyVersion": "1.2.0",
  "mode": "demo",
  "tier": "l1",
  "barTs": "2026-11-17T09:00:00Z",
  "symbol": "EURUSD",
  "signal": "long_entry",           // long_entry|short_entry|long_exit|short_exit|none
  "action": "buy",                  // buy|sell|close|none
  "reason": "EMA(12) crossed above EMA(50) on the last closed bar",
  "indicators": { "ema_fast": 1.0841, "ema_slow": 1.0837, "atr": 0.0012 },
  "risk": { "allowed": true, "quantity": 0.1, "reasons": [] },
  "outcome": "filled",              // filled|placed|refused|skipped|failed|none
  "code": null,                     // refusal/skip code (see 2.5)
  "orderId": "ord_…",
  "orderStatus": "filled",
  "warnings": []
}
```

Stored on `AutomationExecution.decision` (new additive column). Also rendered as
a short human line in `output`, so existing surfaces show something immediately:

```
EURUSD · BUY 0.10 · filled @ 1.0842 (EMA cross up, risk 0.4%)
EURUSD · skipped · session closed (20:00 Europe/London)
```

### 2.3 `ExecutionView` addition

```ts
/** Structured trading decision for a run. Null for non-trading bots. */
decision: DecisionRecordView | null;
```

Optional on the wire, so old runs and old clients are unaffected.

### 2.4 Endpoints

All Python routes stay operator-gated; the TS client goes through the existing
`/api/automations/**` proxy.

| Method | Path | Purpose |
|---|---|---|
| POST | `/automations/{id}/trading/prepare` | validate the trading pins and create the trial + mandate; returns the exact phrase to type |
| GET | `/automations/{id}/trading` | mode, tier, trial, account, positions, orders, open P&L, last N decisions |
| POST | `/automations/{id}/trading/panic` | revoke the bot's mandates, stop its trial, pause the bot (positions untouched) |
| POST | `/quant/live/trials` (extend) | accept `botId` + `botVersion`, and `mode: demo` |

`prepare` body:

```jsonc
{
  "strategyId": "ema_trend",
  "strategyVersion": "1.2.0",
  "mode": "demo",
  "connectionId": "brk_…",
  "symbols": ["EURUSD"],
  "timeframe": "H1",
  "volume": 0.1,
  "stopLossPoints": 150,
  "takeProfitPoints": 300,
  "maxOrders": 4,
  "maxMargin": 500,
  "ttlSeconds": 604800,
  "confirmation": "MANDATE DEMO MT5 demo"
}
```

### 2.5 Error / skip codes

New codes are additive to the existing `TradeRefused` vocabulary.

| Code | Meaning | Run state |
|---|---|---|
| `STRATEGY_UNAVAILABLE` | strategy/version missing or archived | failed |
| `STRATEGY_NOT_APPROVED` | no approved version | blocked |
| `STRATEGY_NO_BACKTEST` | no completed backtest | blocked |
| `SYMBOL_NOT_TRADABLE` | symbol absent from the broker's list | blocked |
| `SESSION_CLOSED` | outside the bot's window | skipped |
| `STALE_MARKET_DATA` | quote/bar older than N bars | skipped |
| `BAR_ALREADY_PROCESSED` | idempotency claim lost | skipped |
| `POSITION_ALREADY_OPEN` | one position per bot+symbol | skipped |
| `RISK_REFUSED` | risk engine said no | blocked |
| `BOT_VERSION_STALE` | objective/strategy edit since mandate grant | blocked |
| `BOT_TIER_INSUFFICIENT` | tier too low for the mode | blocked |
| `LIVE_NOT_ARMED` / `MANDATE_*` | broker layer refused | blocked |
| `BROKER_UNAVAILABLE` | connection/mirror down | failed |

## 3. Backend work packages

### WP1 — Action kind + patch plumbing

**Files:** `python/harness/automation/model.py`, `validation.py`, `service.py`,
`src/lib/harness/clients/automation-client.ts`, `automation-browser.ts`.

1. `ActionKind` gains `"run_strategy"` (and it joins `ACTION_KINDS`).
2. `service._PATCHABLE` gains `"execution_authority"`.
3. `service.update` becomes alias-tolerant for every patchable key:

```python
def _patched(patch, key):
    """Accept snake_case (Python callers) and camelCase (the TS front door)."""
    camel = to_camel(key)
    if key in patch and patch[key] is not None:
        return patch[key]
    if camel in patch and patch[camel] is not None:
        return patch[camel]
    return None
```

Today the UI patches only keys whose camel and snake spellings are identical
(`action`, `trigger`, `description`), which is why this has never mattered.
`executionAuthority` is the first key where it does. `_retype` already rebuilds
the whole model from `model_dump(by_alias=False)`, so nested authority types are
validated for free.

4. TS: `ActionKind` union, `ActionView` config stays `Record<string, unknown>`
   (typed helper in `src/lib/bots/state.ts`), `CreateAutomationInput` gains
   `executionAuthority?: ExecutionAuthorityView`, `AutomationView` gains it too.

**Done when:** a bot can be created and patched with an authority and a
`run_strategy` action; `npx tsc --noEmit` passes; no behaviour changes yet.

### WP2 — Validation

**Files:** `python/harness/automation/validation.py`.

`_ACTION_REQUIRES` cannot express config-based requirements, so add a block:

```python
if action.type == "run_strategy":
    cfg = action.config or {}
    for key, code in (("strategyId", "STRATEGY_ID_REQUIRED"),
                      ("strategyVersion", "STRATEGY_VERSION_REQUIRED")):
        if not str(cfg.get(key) or "").strip():
            issues.append(ValidationIssue(ERROR, code, f"action.config.{key}", ...))
    mode = str(cfg.get("mode") or "")
    if mode not in ("shadow", "demo", "live"):
        issues.append(ValidationIssue(ERROR, "INVALID_TRADING_MODE", ...))
    if mode != "shadow" and not str(cfg.get("connectionId") or "").strip():
        issues.append(ValidationIssue(ERROR, "CONNECTION_REQUIRED", ...))
    if mode != "shadow" and not str(cfg.get("trialId") or "").strip():
        issues.append(ValidationIssue(ERROR, "TRADING_NOT_PREPARED",
            "action.config.trialId", "prepare trading before enabling this bot"))
    if not cfg.get("symbols"):
        issues.append(ValidationIssue(ERROR, "SYMBOLS_REQUIRED", ...))
```

Plus two cross-cutting rules:

- **Misfire must be skip** for trading bots:
  `if action.type == "run_strategy" and definition.execution.misfire != "skip": ERROR MISTRADE_RISK`.
- **Tier vs mode**: `mode == "live" and authority.tier != "l2"` → `ERROR LIVE_TIER_REQUIRED`
  (the broker would refuse anyway; fail at save, with the field named).
- **Strategy existence**: `validate_automation` gains an optional
  `strategy_lookup: Callable[[str, str], Any]`; the service passes
  `service.quant_store.get_strategy`. A missing strategy is an error, not a warning
  (same rule as a missing workflow).

Note: activation calls `_assert_valid`, so a bot whose strategy was archived
cannot be re-enabled without fixing it. That is intended.

**Done when:** every misconfiguration is a field-level error, and a bot with a
deleted strategy cannot be activated.

### WP3 — The runner

**New file:** `python/harness/automation/trading_runner.py` (~350 lines, pure
functions + one async entry; no engine, no loop of its own).

```python
async def run_strategy(service, definition, *, run_id, execution_id) -> DispatchResult:
    cfg = definition.action.config
    # 1. pins
    store = getattr(service, "quant_store", None)
    if store is None: return failed("RUNTIME_UNAVAILABLE", ...)
    strategy = store.get_strategy(cfg["strategyId"], cfg["strategyVersion"])
    if not strategy: return failed("STRATEGY_UNAVAILABLE", ...)

    # 2. session + freshness (pure helpers, unit-tested)
    now = _now(cfg["session"]["timezone"])
    if not in_session(now, cfg["session"]):
        return skipped("SESSION_CLOSED", decision(...))

    # 3. signal
    gateway = service.server_market_gateway()
    evaluation = await evaluate_last_bar(store, strategy, cfg["symbols"],
                                         cfg["timeframe"], gateway)   # WP4b
    if evaluation["signal"] == "none":
        return completed(decision(outcome="none"), output="No signal …")

    # 4/5. execute (mode-aware)
    if cfg["mode"] == "shadow":
        return _shadow(service, definition, strategy, evaluation, cfg)
    trial = _trial_for(service, definition)     # trialId, status, pinned version
    result = await LiveStrategyService(store).run_once(
        cfg["trialId"], gateway=gateway,
        automation_id=definition.id, bot_version=definition.version,
        dry_run=bool(cfg.get("dryRun")),
    )
    return _to_dispatch(result, decision_from(result))
```

Rules the runner owns (not delegated):

- **One bot, one position, one symbol.** Read positions, filter by this bot's
  magic/automation, and skip with `POSITION_ALREADY_OPEN` before sizing.
- **Bar idempotency** through `LiveRunner.claim(..., scope=definition.id)`.
- **Session window** in the bot's IANA zone, evaluated with `zoneinfo`; weekdays
  as 0=Sunday (matches the repo's cron vocabulary).
- **Freshness**: the last bar must be within 2× the timeframe of now; the broker
  quote must be < 60 s old. Otherwise skip; never trade on a stale price.
- **Mapping** of every failure to a typed code and a run state.

`_shadow` computes the signal, sizes it, and runs `BrokerService.preview_order`
when a connection exists (or a synthetic preview from the last close when not),
recording `outcome="none", code="SHADOW"`. It never submits.

**Done when:** a scheduled shadow bot produces one decision per bar, with no
broker writes, and every branch is covered by a unit test.

### WP4 — Trial + mandate binding

**Files:** `python/harness/quant/live.py`, `routers/quant_live.py`,
`trade/service.py`, `trade/mandates.py`, `trade/authority.py`.

**(a) `prepare` becomes mode-aware and bot-aware**

```python
def prepare(self, *, strategy_id, version, connection_id, symbols,
            mode="live", bot_id="", bot_version=None, ...):
    spec = self.store.get_strategy(strategy_id, version)
    self._approval(strategy_id, version)          # both modes
    self._backtest(strategy_id, version)          # both modes
    connection = self.broker.get_connection(connection_id)
    if connection["mode"] != mode: raise LiveGateError("MODE_MISMATCH", ...)
    expected = (f"LIVE TRIAL {strategy_id} {version}" if mode == "live"
                else f"MANDATE DEMO {connection['label']}")
    ...
    mandate = self.broker.create_mandate(connection_id, {
        "mode": mode, "symbols": symbols, "maxOrders": max_orders,
        "maxMargin": max_margin, "ttlSeconds": ttl,
        "confirmation": f"MANDATE {mode.upper()} {connection['label']}",
        # exactly ONE pin: a bot pin for bot execution, workflow pin otherwise
        **({"botId": bot_id, "botVersion": bot_version} if bot_id else
           {"workflowId": pin, "workflowVersion": 1}),
    })
```

`QuantLiveTrial` gains `botId TEXT`, `botVersion INTEGER` (additive `ALTER`,
same pattern as `TradingMandate`). `_row()` exposes them.

**(b) Extract the pure evaluation**

`LiveStrategyService.signal` currently owns "read series → calculate → pick last
bar". Extract that into a module-level async function
`evaluate_last_bar(store, strategy, symbols, timeframe, gateway)`; `signal` calls
it and keeps its exact return shape. Shadow mode and tests use it directly. No
behaviour change; `test_quant_live.py` must stay green.

**(c) `run_once` accepts bot attribution**

```python
async def run_once(self, trial_id, *, gateway=None, volume=None, symbol=None,
                   dataset=None, automation_id="", bot_version=None,
                   dry_run=False):
    ...
    order = self.broker.submit_order(
        trial["connectionId"], payload,
        mandate_id=trial["mandateId"] or "",
        run_id=trial_id, workflow_id=trial["pin"],
        node_id="quant_strategy",
        automation_id=automation_id,
        automation_version=bot_version,
        bot_id=automation_id, bot_version=bot_version,
    )
```
`dry_run` replaces the submit with `preview_order` and reports
`status: "PREVIEW_ALLOWED" | "PREVIEW_REFUSED"`.

**(d) Idempotency scope**

`LiveRunner.claim(..., scope="")` → `runKey = f"{scope}|{strategy}@{version}|{timeframe}|{barTs}"`.
Default `""` keeps today's global key for trials. The runner passes the bot id,
so two bots on the same strategy with **different symbol universes** do not block
each other; two bots on the same strategy+symbol do, by design.

**(e) Demo mandates may be pinned to L1 bots**

`trade/service.py:create_mandate` currently calls `check_mandate_creation` for
any `botId`, and that requires L2 unconditionally. Split it:

```python
check_mandate_creation(mode=mode, ...)  # live → tier l2; demo → tier l1
```
Live keeps every existing rule (version pin, margin ceiling). Demo gains the
version pin + ceiling only. This matches `docs/trading.md` ("l1 may fill a demo
mandate") — the code was stricter than the doc.

**Done when:** a demo bot can be prepared with a typed phrase, a demo mandate
pinned to it, and `run_once` records `automationId` on the order.

### WP5 — Centralize the live-ring fence

**Files:** `python/harness/trade/service.py`.

`check_live_order` is currently called from `trade/tools.py` (the agent path) and
relied on indirectly for graphs. The strategy runner is a third caller; put it
inside the one seam so no caller can forget it:

```python
# submit_order, after the connection/mode is resolved and before the adapter
if automation_id and execution_mode == "live":
    refusal = check_live_order(self, automation_id=automation_id,
                              connection_id=connection.id, mode=execution_mode,
                              intent=intent.to_dict())
    if refusal:
        message, detail = refusal
        raise TradeRefused(detail.get("reason", "BOT_REFUSED"), message, status_code=409)
```

Graph runs pass no `automation_id`, so they are unaffected (their fence is the
workflow-pinned mandate + compiler). The agent tool keeps its earlier check for a
better message; the duplicate is harmless.

**Done when:** an L1 bot cannot reach a live account even if a live mandate
somehow exists.

### WP6 — Lifecycle coupling

**Files:** `python/harness/automation/service.py`, `trade/service.py`,
`quant/live.py`, `automation/model.py` (no schema change).

A new helper `python/harness/automation/trading_lifecycle.py`:

```python
def stop_bot_trading(service, automation_id, *, reason) -> dict:
    """Revoke every active mandate pinned to this bot and stop its trial.
    Positions are NEVER closed here — closing is an operator decision."""
    revoked = service.brokers.revoke_mandates_for_bot(automation_id)  # new
    stopped = service.quant_live.stop_by_bot(automation_id)           # new
    return {"revoked": revoked, "stopped": stopped, "reason": reason}
```

Call sites:

| Trigger | Call |
|---|---|
| `set_state` → paused / disabled / archived | `stop_bot_trading` |
| `delete` | `stop_bot_trading` **before** the row is removed |
| `update` where `action` or `execution_authority` changed | version already bumps; leave the mandate alone so the next run reports `BOT_VERSION_STALE`, and surface a "re-grant" action |
| strategy archived (quant store) | next run reports `STRATEGY_UNAVAILABLE`; no cascade needed |

`trade/mandates.py` gains `list_by_bot(bot_id, active_only=True)` and
`revoke_by_bot(bot_id)`; `quant/live.py` gains `stop_by_bot(bot_id)` (status
`stopped` + revoke the trial's mandate, same as `stop`).

**Done when:** pausing a trading bot leaves zero usable mandates and its trial
stops reporting; the positions are still there and visible.

### WP7 — Run recording

**Files:** `python/harness/automation/store.py`, `engine.py`, `dispatcher.py`,
`src/lib/harness/clients/automation-client.ts`,
`src/components/bots/run-history.tsx`.

1. `AutomationExecution` gains `decision TEXT` via `_ensure_column` (the file
   already uses that helper for `output`).
2. `finish_execution(..., decision: str | None = None)` writes it;
   `_row()` parses it into `decision`.
3. `engine` passes `(result.detail or {}).get("decision")`.
4. `DispatchResult.detail["decision"]` is the runner's decision dict.
5. TS `ExecutionView.decision?: DecisionRecordView | null`.
6. `run-history.tsx` renders a compact decision row (signal · action · outcome ·
   code) expanding to indicators and reasons.

**Done when:** every trading run shows its decision in Run History, including
the runs that did nothing.

### WP8 — Performance read

**Files:** `python/harness/routers/automation.py` (new route),
`src/app/api/automations/[...path]/route.ts` (add `trading`), client.

```
GET /automations/{id}/trading?limit=50
→ {
    botId, version, mode, tier, dryRun,
    trial: { id, status, ordersUsed, maxOrders, expiresAt } | null,
    account: { balance, equity, currency, mode } | null,     // broker truth
    positions: [...],                                        // filtered by magic
    openPnl: number,
    orders: [ { id, symbol, side, volume, status, createdAt, code } ],
    decisions: [ DecisionRecord… ],
    refusals: [ { code, count } ],
    unavailable: []                                          // honest gaps
  }
```

Every value is read from the broker or the ledger. If the broker is down the
route returns `available: false` with the reason — never zeros passed off as
data.

**Done when:** the bot detail panel can render P&L, positions and refusal counts
without touching the strategy studio.

## 4. Frontend work packages

### WP9 — Draft model (`src/lib/bots/state.ts`)

```ts
export interface TradingDraft {
  enabled: boolean;
  mode: "shadow" | "demo" | "live";
  strategyId: string;
  strategyVersion: string;
  connectionId: string;
  symbols: string;              // comma-separated in the form, array on save
  timeframe: string;
  volume: number;
  stopLossPoints: number;
  takeProfitPoints: number;
  maxOrdersPerDay: number;
  allocationMode: "percent_equity" | "fixed_notional";
  allocationValue: number;
  sessionEnabled: boolean;
  sessionTimezone: string;
  sessionStart: string;
  sessionEnd: string;
  sessionWeekdays: number[];
  dryRun: boolean;
  // authority
  tier: "l0" | "l1" | "l2";
  appetite: "conservative" | "normal" | "aggressive";
  requireStop: boolean;
  maxOpenPositions: number;
  maxMarginPerOrder: number;
  cooldownS: number;
}

export type BotKind = "agent" | "workflow" | "strategy";
```

Additions, all pure and tested:

- `emptyTradingDraft()`, `buildTradingConfig(draft)`, `buildAuthority(draft)`.
- `validateTradingDraft(draft, ctx)` → `DraftIssue[]`; mirrors WP2 codes so the
  user sees the same message the server would return.
- `draftFromBot` reads `action.type === "run_strategy"` and the authority back
  into the draft (round-trip test).
- `buildAction(draft)`: `strategy` → `run_strategy`; agent/workflow unchanged.
- Defaults when trading is enabled: H1, `maxOrdersPerDay 2`, `maxOpenPositions 1`,
  `cooldownS 900`, `requireStop true`, tier `l0`, mode `shadow`.
- Trading bots force `misfire: "skip"` in `buildPolicies`.

### WP10 — Creation: the Trading tab

**Files:** `src/components/bots/create-bot-dialog.tsx` (split, keep it small) +
new `src/components/bots/trading/`:

| File | Responsibility |
|---|---|
| `trading-tab.tsx` | the switch, mode, and section order |
| `strategy-picker.tsx` | `backtestClient.listStrategies()` + evidence badges |
| `venue-picker.tsx` | broker connections (`getConnections`) with demo/live/armed badges |
| `risk-envelope.tsx` | allocation, risk, positions, orders/day, cooldown |
| `session-window.tsx` | timezone + weekdays + start/end |
| `guardrail-summary.tsx` | the effective minimums, read-only |
| `consent-phrase.tsx` | exact phrase field for prepare (demo/live) |
| `authority-picker.tsx` | tier + appetite, with the eligibility note |

Flow:

1. User picks **Strategy** as the brain (third option beside agent/workflow) or
   enables **Trading** on an agent bot.
2. Strategy picker shows name · version · backtest verdict · approval · last
   paper run. A strategy with no backtest can be selected but the summary says
   it will be refused (`STRATEGY_NO_BACKTEST`) — honest, not hidden.
3. Venue list is filtered by mode. Live connections appear only for tier `l2`,
   and only when the connection is armed.
4. `guardrail-summary` computes the effective limits as
   `min(bot, connection policy, mandate)` and renders them.
5. On save: create the automation **first** (state `draft`), then call
   `prepareTrading`. If prepare fails, the bot stays a draft, the error is shown
   with a Retry button. Partial failure is visible, never silent.
6. On success: enable the bot (if the user chose a schedule), set the trial id
   on `action.config`, and open the bot.

The consent phrase is required exactly as the server computes it. For live that
is `LIVE TRIAL <strategyId> <version>`; for demo `MANDATE DEMO <connection label>`.
Do not pre-fill it — typing it is the point.

### WP11 — Detail: Trading section

**New:** `src/components/bots/bot-trading-section.tsx`, mounted in
`bot-detail.tsx` (only when `action.type === "run_strategy"` or the bot has an
authority above `l0`).

Shows: strategy + version pin (link to Studio), mode + tier, trial status and
expiry, account equity, open positions with P&L, today's orders, the last
decision, refusal counts, and three actions:

- **Run now** (existing) — one bar decision immediately.
- **Pause trading** — pause the bot + revoke the mandate (WP6).
- **Panic** — connection-wide kill switch link when live; bot-scoped panic here.

Plus a two-step **Re-grant authority** flow when the version is stale:
show what changed (`versions` endpoint already exists), then re-prepare.

### WP12 — Run history + chat

`run-history.tsx`: decision row (WP7). Empty runs say *why* ("no signal",
"session closed"), never just "Completed".

`bot-chat.tsx`: when the bot is a trading bot, prepend a compact "last decision"
context block to the turn so "why didn't you trade?" is answered from real data,
not invented. The bot may explain; it may not place an order from chat unless it
is an agent bot at L1+ on a demo mandate.

### WP13 — Packs and templates

`src/lib/bots/trading-bots.ts`, modelled on `institution-bots.ts`: idempotent by
name, creates **shadow** bots only. Seed three: trend-follow (EMA), mean
reversion (RSI), breakout (Donchian) on a symbol the user's venue actually has.
If no strategy exists yet, seed nothing and explain why — never fabricate a
strategy.

## 5. Sequences

### 5.1 Create a demo strategy bot

```
UI  POST /api/automations { action: run_strategy, config(mode=demo, trialId=""), … }
Py  validate (WP2) → save draft
UI  POST /api/automations/{id}/trading/prepare { …, confirmation }
Py  prepare → gates (approval, backtest, mode, arm if live, tier)
    → create mandate (bot-pinned) → insert trial
UI  PATCH /api/automations/{id} { action.config.trialId, state: active }
Py  scheduler picks it up; next bar → run → decision
```

### 5.2 One scheduled run

```
engine → dispatcher → run_strategy
  session open?  no → skipped SESSION_CLOSED
  fresh bar?     no → skipped STALE_MARKET_DATA
  signal none?      → completed, outcome none
  exit signal?      → close this bot's position (risk-reducing, no approval)
  entry signal?     → position exists → skipped POSITION_ALREADY_OPEN
                    → claim bar (scope=botId) → risk → submit (mandate, bot pin)
  record decision + output + events
```

### 5.3 Promote to live

```
1. Strategy has approval + backtest + paper run (already required by prepare)
2. Operator raises tier to l2 (single-use approval, ≥30 scored advisory calls)
3. Operator arms the connection (typed ARM LIVE <login>)
4. UI: mode=live → server returns the required phrase LIVE TRIAL <id> <ver>
5. prepare → live mandate (bot + version pin, ≤24 h, margin cap)
6. Run: check_live_order (WP5) → policy → guardrails → mandate → submit
7. Expiry or pause → mandate dead; positions stay; operator decides
```

### 5.4 Edit / pause / delete

- **Edit objective, strategy version, universe, authority** → version bump →
  next run `BOT_VERSION_STALE` → UI offers re-grant.
- **Pause** → `stop_bot_trading` → mandates revoked, trial stopped, positions
  untouched, chat says what happened.
- **Delete** → revoke first, then remove the row. Never delete the broker
  history; never close positions.

## 6. Phases

### P0 — Contracts and plumbing (1–2 days)

- [ ] WP1 (action kind, authority patch, TS types)
- [ ] WP2 (validation + strategy lookup)
- [ ] WP6 skeleton (`stop_bot_trading`, `list_by_bot`, `stop_by_bot`) with tests
- [ ] Detail section read-only (WP11 shell)
- **Exit:** a bot stores a trading config + authority; nothing executes.

### P1 — Shadow (3–4 days)

- [ ] WP4b (`evaluate_last_bar` extraction)
- [ ] WP3 shadow branch (no trial, no broker writes)
- [ ] WP7 decision column + Run History card
- [ ] WP9 + WP10 shadow path
- **Exit:** a scheduled shadow bot logs one typed decision per bar for a week.

### P2 — Demo execution (4–5 days)

- [ ] WP4a/c/d/e (mode-aware prepare, bot attribution, scope, demo tier)
- [ ] WP3 demo branch + position/duplicate guards
- [ ] WP8 read route + WP11 live panel
- [ ] WP10 consent + prepare sequence
- **Exit:** a demo bot opens/closes on schedule under a bot-pinned mandate, and
  every refusal is explainable from the UI.

### P3 — Agent trading bots (3 days)

- [ ] `trader` agent preset (`agent_presets.py`) + prompt contract
- [ ] Authority picker for agent bots (L0/L1), tool surface respects tier
- [ ] Chat "why" context block
- **Exit:** an agent bot proposes (L0) and fills demo (L1) with reasons.

### P4 — Live (4–5 days)

- [ ] WP5 central fence
- [ ] L2 escalation flow + eligibility from the advisory ledger
- [ ] Live prepare + re-grant UI
- [ ] cross-bot exposure cap (portfolio sum per connection)
- [ ] performance route fields + journal link
- **Exit:** one live strategy bot runs under a 24 h mandate, fully attributed,
  and stops cleanly on expiry, pause or kill.

### P5 — Polish (2–3 days)

- [ ] WP13 starter pack, duplicate-a-trading-bot
- [ ] evaluation cases (trading bot refusal reasons, no fabricated fills)
- [ ] docs: `bot-mode.md`, `trading.md`, `strategy-studio.md`

Every phase: `npm run test` + `npx tsc --noEmit` from `Black-Eclipse-site/`.

## 7. Tests

**Python**

- `tests/test_strategy_bot_runner.py` — one case per branch: no signal, entry,
  exit, duplicate position, stale bar, session closed, stale quote, symbol not
  tradable, strategy missing, version stale, tier refusal, bar already claimed,
  misfire skipped, broker down.
- `tests/test_bot_trading_authority.py` — tier × mode matrix, position cap,
  cooldown, stop required, margin ceiling, demo-l1 mandate allowed, live-l1
  refused.
- `tests/test_trading_mandates.py` (extend) — bot pin, version bump invalidates,
  revoke on pause, exactly-one-pin rule.
- `tests/test_quant_live.py` (extend) — `prepare` demo/live, bot pin, `run_once`
  attribution, dry-run preview, `evaluate_last_bar` extraction parity.
- `tests/test_automation_trading_validation.py` — every WP2 code.

**TypeScript**

- `src/lib/bots/state.test.ts` — trading draft round-trip, validation mirror,
  `buildAction`/`buildAuthority`, misfire forced to skip.
- `src/lib/bots/trading-bots.test.ts` — pack idempotency.
- Existing automation-client tests: `decision` optional on old payloads.

**Manual/e2e** — with `python/tests/mt5_sim.py`: create shadow → demo → pause →
re-grant → panic.

## 8. Compatibility and migration

- Additive only: new action kind, optional fields, `_ensure_column` for
  `decision`, `botId`/`botVersion`.
- Existing bots, trials and mandates are untouched; `executionAuthority` already
  defaults to `l0` for every stored definition.
- Old clients: `decision` and `executionAuthority` are optional on the wire.
- No route is renamed. `prepare` keeps its live behaviour by default
  (`mode="live"`), so the existing Studio panel keeps working.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Strategy symbol (e.g. `BTC-USD`) is not tradable on MT5 | validate against the broker's symbol list → `SYMBOL_NOT_TRADABLE` at prepare |
| Gateway bar series and broker prices disagree | v1 reads bars from the same gateway the backtest uses, and the quote from the broker; both are recorded in the decision so an operator can see the basis |
| Two bots double-trade one symbol | one position per bot+symbol check + scoped bar claim; optional exclusive ownership later |
| A missed run fires late | misfire forced to `skip` |
| Live tier is clicked through without understanding | typed phrase + arm + L2 eligibility + mandate TTL ≤ 24 h |
| Partial creation leaves a broken bot | create draft → prepare → enable; failures keep the draft and show Retry |
| A refused order looks like a bug | every refusal is a code in the run + a sentence in the chat |
| Deleting a bot leaves a live mandate | delete revokes first (WP6), tested |

## 10. Open decisions

1. **Shadow mode without a broker** — recommended, and it needs no venue: it
   evaluates the strategy on JDdS data and previews the order. Confirm.
2. **Typed phrase at creation** — recommended (one field) instead of silently
   auto-creating a mandate. Confirm.
3. **Default tier on creation** — `l0` (propose) everywhere; the user raises it.
4. **One bot per symbol** — recommended for v1; netting later.
5. **Agent trading bots in P3 vs after live** — recommended before live, because
   they share the same fence and prove the UI.
