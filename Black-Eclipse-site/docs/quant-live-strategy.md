---
title: Live Strategy Trials — from tested model to broker execution
status: Current
last-verified: 2026-11-10
---

# Live Strategy Trials

**Who this is for:** anyone promoting a tested quant strategy to a live broker,
or working on `python/harness/quant/live.py`.

## The one rule

> A backtest is evidence, not permission. A live order needs an armed connection,
> a capped live mandate, and a recorded trial.

The live path does not bypass the broker layer. It uses the SAME connection,
arm, mandate, margin cap, order count, expiry, money guardrails, reconciliation
and kill switch as every other live order.

## Lifecycle

```
approved strategy version
  + completed backtest
        ↓
operator arms the live connection
        ↓
operator creates a live trial (typed phrase)
        ↓
live mandate pinned to the strategy version
        ↓
last closed bar → signal → one order under the mandate
        ↓
broker fills / positions / P&L
        ↓
stop → revoke the mandate
```

## Gates

| Gate | Check | Refusal |
|---|---|---|
| Review | an approved `QuantStrategyApproval` exists for the version | `APPROVAL_REQUIRED` |
| Evidence | a completed backtest is recorded for the version | `BACKTEST_REQUIRED` |
| Typed phrase | `LIVE TRIAL <strategyId> <version>` | `CONFIRMATION_REQUIRED` |
| Connection | broker mode is `live` | `LIVE_CONNECTION_REQUIRED` |
| Arm | `armedUntil` is in the future | `LIVE_NOT_ARMED` |
| Cap | a positive `maxMargin` is supplied | `MAX_MARGIN_REQUIRED` |
| Mandate | the broker layer creates a live mandate | broker refusal |
| Paper | a paper run is recorded | warning, not a hard block |

A missing paper run is a warning. It is visible in the trial's `warnings` field.
It is not silent.

## The strategy pin

A live mandate normally pins a Graph Studio workflow id and version. A strategy
trial uses the same field with a strategy pin:

```
strategy:<strategyId>:<version>
```

The broker layer does not need a new order path. `submit_order` receives
`workflow_id` = that pin, so the existing mandate verification applies. The
margin cap, order count, expiry and symbol allowlist are enforced by the
mandate.

## Signal

`LiveStrategyService.signal` evaluates the strategy on the **last closed bar**
with the SAME causal indicator and rule engine as a backtest. It returns:

- `signal`: `long_entry | short_entry | long_exit | short_exit | none`
- `action`: `buy | sell | close | none`
- `reason`, `bar`, `indicators`, `warnings`

A signal is a condition. It is not an order until `run_once` checks the existing
positions and the mandate.

## Execution

`run_once` does one of three things:

1. **No signal**: no order.
2. **Exit signal**: closes the matching symbol's open positions. A close is
   risk-reducing and needs no new approval.
3. **Entry signal**: if no open position exists for the symbol, it submits one
   market order under the mandate. A second run does not stack a position.

The order is a normal `OrderIntent`. The broker layer reports the exact status:
`filled`, `placed`, `REFUSED`, `CONFIRMATION_REQUIRED`, or a typed refusal.

## Results

`results` reads the broker and returns:

- account
- positions
- working orders
- open position count
- open P&L (profit + swap + commission)

The broker is the source of truth. A result is not a backtest.

## Routes

All routes are operator-gated:

```
POST /quant/live/trials
GET  /quant/live/trials
GET  /quant/live/trials/{id}
POST /quant/live/trials/{id}/signal
POST /quant/live/trials/{id}/run
GET  /quant/live/trials/{id}/results
POST /quant/live/trials/{id}/stop
```

Front door: `/api/backtest/live/trials/...`.

## UI

Strategy Studio has a **Live strategy trial** panel. It:

1. lists live broker connections;
2. takes the confirmation phrase, max margin, max orders, TTL and volume;
3. prepares the trial;
4. checks the last closed-bar signal;
5. runs once;
6. shows broker results;
7. stops the trial and revokes the mandate.

The panel does not arm the connection. Arming stays a separate operator action in
the broker surface. That is intentional: arm and decision are separate.

## What a bot or skill can do

A bot or skill can prepare the setup and call the signal check. It does not get a
standing live key. A live order still needs the trial's mandate and the broker
layer's checks. If a bot run is used, the trial must already exist and the
connection must already be armed.

## Kill switch

The broker layer's kill switch cancels working Eclipse orders and disarms the
connection. `stop` revokes the trial's mandate. Closing positions remains an
explicit risk-reducing action.

## Tests

`python/tests/test_quant_live.py` covers the gates, typed phrase, arm check,
signal, one order, duplicate-position refusal, broker results and stop.
`python/tests/test_quant_research_routes.py` asserts the routes are registered.
