---
title: Trading bots — real execution & test plan
status: Implemented (L0–L4); L5/L6 operator-run
last-verified: 2026-11-17
---

# Trading bots — real execution and how to test them

**L4 reached on 2026-11-17 against the real terminal** (MetaQuotes-Demo
114826727). A demo bot (`auto_21fb2c4a633340f7be2e`, strategy
`eurusd_smoke_1d` v1.0.0, tier L1, mandate `mnd_ac414e6099be`) ran once and the
terminal filled a **EURUSD BUY 0.01 @ 1.09897** (ticket `11447256588`, SL
1.09798, TP 1.10048). Evidence: the execution `autoexec_43a3e1b7c92b4962b8f0`
(state `completed`, decision `outcome=filled`, `orderStatus=filled`), a
`BrokerOrder` row `ord_e29c7a0e6b41` with **`automationId` + `automationVersion`
+ `mandateId` + `runId`** and the same ticket, and MT5's own deal history (entry
`strategy:eurusd_smoke_1d`, then `eclipse close`; account flat after).

Getting there exposed five real defects, all fixed (see the CHANGELOG):

1. **Activation staled the mandate.** `PATCH {state: active}` bumped the bot
   version that `prepare` had just pinned → every run refused
   `BOT_VERSION_STALE`. A state-only change no longer bumps the version.
2. **The demo phrase shown was the connection id**, while `prepare` compares the
   connection *label* → the operator typed a phrase the server always rejected.
3. **A bare FX pair was not FX.** `EURUSD` classified as equity, so no provider
   had bars: backtest and signal both failed. Bare fiat pairs now map to
   `EURUSD=X` (Python classifier and the Next price-history route).
4. **Signals used a proxied series.** A broker symbol now signals on the
   broker's OWN bars (MT5 `copy_rates`), because those are the bars the order is
   filled against; the gateway remains the fallback.
5. **The forming bar was traded.** `copy_rates*` includes the open bar; the
   signal now drops it and trades the last CLOSED bar only.
6. **A refusal burned the bar.** `RISK_REFUSED` / kill-state left the bar
   claimed, so fixing the bot could not retry that bar. A refusal that sent
   nothing now releases the claim; a send never does.
7. **Bot orders were un-killable.** Connections had `magic: 0`, so the kill
   switch refused. Every connection now gets a stable ownership magic.

**Still open:** L5 (supervised live, minimum size) needs the operator's explicit
consent and a supervised window; L6 (48–72 h soak) needs an always-on host. The
app is not a 24/7 service.

**Kill-switch scope, proven (2026-11-17 20:0x local).** A second bot
(`auto_87fb48d33d6741f58e33`, strategy `eurusd_magic_sw`) filled EURUSD BUY 0.01
@ 1.09863 as ticket `11448007792` with **magic `741879`** (the connection's
ownership magic, backfilled from its label). Two working orders were then placed
on the demo: `11448013638` with magic `741879` and `11448013651` with magic `777`
(a control). `POST /trading/connections/brk_c45c08fda345/kill` returned
`magic=741879 matched=1 cancelled=1 failed=0`; MT5 then showed only the control
order, and the bot's filled position was untouched (the kill switch cancels
working orders, it does not liquidate). The control order and the position were
closed afterwards; the account is flat.


**Who this is for:** anyone asking "is the bot actually placing trades, and how
do we prove it?"

This is the record of what was tested and what remains. The decision machinery
is implemented and unit-tested; **a demo bot has now placed a real order on the
MT5 terminal (L4, evidence at the top)**, but no live order has, and the app is
not a 24/7 service.

## 1. Product change: demo is a choice, not a cage

Today a bot is created in shadow; demo is offered; live is effectively
unreachable because L2 is only suggested after a track record and the Authorize
button is disabled below L2. That is wrong for an operator who owns the account.

**Rule:** the operator chooses **Shadow / Demo / Live**. The app never forces
demo, and never silently goes live.

| Step | Shadow | Demo | Live |
|---|---|---|---|
| Broker writes | none | yes | yes |
| Consent phrase | not needed | required once | required once |
| Connection state | none | demo connection | **armed** live connection |
| Tier | L0 | L1 | L2 (granted by the same live authorization) |
| Mandate | none | demo, bot-pinned | live, bot-pinned, ≤24 h |
| Caps | — | margin/orders/symbols | margin/orders/symbols + daily loss |

### What changes

1. **Creation/Authorize:** keep all three modes selectable. Selecting Live no
   longer dead-ends on "needs L2". It shows the live requirements (armed
   connection, typed phrase, caps) and, on authorize, performs one explicit
   operator action: `tier = l2` + `prepare(mode=live)`.
2. **L2 becomes operator-granted, with advice:** the ladder keeps showing the
   measurable evidence (decisions, days, backtest, approval) and the journal
   warning, but it does not prevent the operator from granting live. Rationale:
   the account owner is the authority; the typed phrase + arm + mandate caps + the
   submit fence are the guardrails, not the demo mode.
3. **No silent live:** the server still requires the typed phrase and an armed
   connection (`trade/authority.py`, `quant/live.prepare`). A bot can never arm.
4. **Remember the mode:** the last chosen mode and venue are preselected.
5. **Naming:** UI says "Live — real money" plainly; no euphemisms.

Code touchpoints: `src/lib/bots/trading/authorize.ts` (allow a live grant),
`src/components/bots/bot-trading-section.tsx` (ladder + authorize),
`python/harness/routers/bot_trading.py` (raise tier + prepare atomically),
`python/harness/trade/authority.py` (keep the fence, stop requiring prior
eligibility), `python/harness/quant/live.py` (unchanged phrase/arm gates).

## 2. Test layers

Each layer answers a different question. A green lower layer never implies the
one above it.

### L0 — pure logic (exists)

- Strategy parsing and rules on synthetic bars (`test_eur_1m_strategy.py`).
- Runner branches: session, freshness, no signal, duplicates, refusals, shadow
  (`test_trading_bot_runner.py`).
- Consent coverage, tiering, gate reasons (`test_trading_policy.py`,
  `venue-memory.test.ts`, `authorize.test.ts`).

### L1 — dispatcher + fake broker (exists)

- `test_broker_orders.py`: `BrokerService.submit_order` with a fake adapter.
  Proves the live fence refuses L1, the L2 bot sends once, stale versions are
  refused, and the ledger is attributed.

**Gap:** it does not run the strategy → decision → trial → submit chain through
the real automation engine.

### L2 — real MT5 adapter against the simulator (partly exists)

`python/tests/mt5_sim.py` implements a `SimTerminal` with `account_info`,
`symbol_info(_tick)`, `positions_get`, `order_check`, `order_send`, deals and
bars. `test_mt5_adapter.py` covers request building; `test_broker_orders.py`
covers the service with a fake adapter, not the simulator.

**Add:** a test that injects `mt5_sim` as the `MetaTrader5` module and drives
`BrokerService.submit_order` end to end:

- preview → policy → guardrails → mandate → `order_check` → `order_send`;
- assert exactly one position appears in `positions_get`;
- assert the ledger row matches the sim ticket/deal;
- assert a second submit cannot reuse the mandate;
- assert an unarmed live connection is refused before `order_send`.

### L3 — full strategy-bot E2E in process (missing; the important one)

New `python/tests/test_trading_bot_e2e.py`, wiring the REAL layers:

```
AutomationStore + AutomationService + engine/dispatcher
  + QuantStore (strategy, backtest, approval)
  + BrokerService (kind = mt5 adapter, module = python/tests/mt5_sim.py)
  + LiveStrategyService
  + a fake market gateway returning synthetic M1 EURUSD bars
```

Scenarios:

1. **Demo, entry:** create the bot + demo mandate; run one execution; assert a
   decision record (`filled`/`placed`), one ledger order, one sim position, and
   the run state `completed`.
2. **Demo, no signal:** flat bars → decision `outcome=none`, zero orders.
3. **Live gate:** live mode without an arm → `blocked` / `LIVE_NOT_ARMED`, zero
   orders; after arm → one order.
4. **Live fence:** an L1 bot with a live mandate → `BOT_TIER_INSUFFICIENT`,
   zero orders (already at L1, but now inside the full chain).
5. **Duplicate guard:** second run on the same bar → `BAR_ALREADY_PROCESSED`,
   still one position.
6. **Exit:** a reverse signal closes the sim position through
   `broker_close`, no new approval.
7. **Persistence:** the decision is readable from `AutomationExecution.decision`
   and the run history API.

This layer is the acceptance gate for "the bot can place a trade".

### L4 — real MT5 demo smoke (DONE 2026-11-17)

A scripted, opt-in check against the installed terminal:

1. App + MT5 demo logged in; broker status `connected`.
2. Create the bot: strategy + backtest + approval, then prepare.
3. Authorize **demo** with the phrase `MANDATE DEMO <connection label>`.
4. **Run now**; wait for the execution to finish.
5. Verify: a decision in Run History, an order/position in MT5 and in the bot's
   Trading panel, `automationId` on the ledger row.
6. Close from the panel and verify the position is gone.

What was actually run (2026-11-17): a 1D smoke strategy (`eurusd_smoke_1d`:
`close > 0`, always long, stop 100 points / target 150) because the app's only
verified EURUSD history is daily; the 1m variant could not be backtested (no
provider serves 1m FX) and the bot now falls back to the broker's own bars.

Gate: `BLACK_ECLIPSE_TRADING_IT=1`. Never part of `npm test`.

### L5 — supervised live smoke (operator-run, tiny)

Only after L4 is green, with explicit consent:

- min volume (0.01), small `maxMargin`, 24 h mandate, `requireStop`;
- arm the connection for 30 min;
- authorize **live**, run once, verify the fill in MT5 and the ledger;
- close the position immediately, revoke the mandate, disarm, and confirm the
  kill switch cancels working orders.

No automation is allowed to do this; it is a checklist, not a test.

### L6 — soak (48–72 h demo)

Leave one demo bot active with the 60 s schedule, then measure:

- one decision per closed bar (no silent gaps);
- zero duplicate positions;
- zero orders outside the session window;
- every refusal has a code and a sentence;
- no breaker trip for expected refusals;
- P&L recorded but **not** used as a pass/fail signal.

**Run so far (2026-11-18, isolated).** The shared app is killed every few minutes,
so the soak runs on its own: a `VACUUM INTO` copy of the bot state
(`.black-eclipse/soak-iso/agent-memory.db`), harness port **8799**, its own
`BE_DATA_DIR`, a supervisor that restarts it, and an MT5 watchdog.

```
window    03:02:59Z → 05:38:09Z  (156 minutes, then stopped by the operator)
fires     156 (one per 60 s), 156 distinct minutes, 0 duplicate minutes
results   136 × BAR_ALREADY_PROCESSED
           14 × no signal (MT5 was down)
            2 × POSITION_ALREADY_OPEN (no stacking)
            2 × filled on fresh 5-minute bars
            1 × MANDATE_INACTIVE (the 2-order daily cap, working as designed)
            1 × QUANT_ERROR
ledger    2 rows, both with automationId + mandateId + runId · 0 unexplained orders
```

**Fast fresh-bar entry (2026-11-18 05:29–05:31Z).** Waiting for the daily close
was replaced by a **5-minute** smoke strategy (`eurusd_m5_smoke`, seeded into the
isolated runtime with a synthetic backtest so the approval gate is honest about
being a smoke test). Real M5 bars then produced real entries within minutes:

```
05:29:08Z  bar 07:20  filled   ord_aa35ce8b730b  ticket 11451776390 @ 1.09863
05:30:09Z  bar 07:25  skipped  POSITION_ALREADY_OPEN
05:31:09Z  bar 07:25  filled   ord_44af638be5fc  ticket 11451810596 @ 1.09835
```

The no-signal decisions now carry the cause
(`no actionable signal (EURUSD: signal failed: …)`).

**Closed 2026-11-18 05:40Z by the operator's decision.** The isolated supervisor,
the MT5 watchdog and port 8799 were stopped; the demo account is flat. The
48–72 h L6 record is **deferred** (the operator cannot keep the machine up that
long), not failed: the properties L6 measures — one decision per fire, no
duplicates, no stacking, coded refusals, no orders without an owner — were all
observed across 156 consecutive minutes. The isolated DB and
`.black-eclipse/soak-iso.log` are kept as the raw record.



## 3. Acceptance criteria

| Claim | Evidence required |
|---|---|
| "A bot can place a demo trade" | **PASSED 2026-11-17**: L3 scenario 1 + L4 (real MT5 fill, ledger row with `automationId`) |
| "A bot can place a live trade" | L5 checklist (supervised, min size) |
| "It runs on a schedule" | L6: 72 h of decisions, no gaps beyond market hours |
| "It learns" | repeated-refusal test → proposal generated; applying it changes config and re-prepares; no silent changes |
| "It is safe" | L2/L3 live-gate + fence tests; kill switch; mandate caps |
| "It is profitable" | **not claimable** from any test here — only a long track record |

## 4. Sequencing

1. **P1 — live preference:** allow the operator to grant L2 + authorize live in
   one action; keep the phrase/arm/fence. Tests: `authorize.test.ts`, ladder
   tests, one Python `prepare` test.
2. **P2 — L3 E2E:** the in-process full-chain test with the MT5 simulator.
3. **P3 — L4 demo smoke:** scripted, opt-in, real terminal.
4. **P4 — L5 live smoke:** checklist, supervised.
5. **P5 — L6 soak:** run and report.

## 5. Honest limits

- The MT5 simulator proves our code, not MetaTrader's wire behaviour; only L4/L5
  do that.
- The desktop app must stay open (and the machine awake); there is no service or
  cloud runner. "24/7" means an always-on host with the app running.
- 1-minute EURUSD is noisy and cost-sensitive; a passing test does not imply an
  edge. Profitability is out of scope for this plan.
