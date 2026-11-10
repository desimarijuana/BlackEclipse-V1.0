---
title: Quant System Blueprint — the path to a 10/10 system
status: Proposed
last-verified: 2026-11-10
---

# Quant System Blueprint

**Who this is for:** the quant, engineer and operator who will turn Eclipse from
a strong research scaffold into an institutional-grade research and trading
system.

## 0. What 10/10 means

10/10 does **not** mean "always profitable". No system can promise that.

10/10 means:

- the data is clean, point-in-time and reconciled to the broker;
- every claim is traceable to a source, a trial and an artifact;
- every model is versioned, reproducible and staged;
- execution is idempotent, reconciled and measured;
- risk limits are hard, visible and enforced;
- the system runs unattended, recovers from failure and tells you when it is
  unhealthy;
- a live track record exists, and live results are compared with the backtest;
- an operator can see health, exposure, P&L, drift and the kill switch in one
  place.

A 10/10 system is **trustworthy, repeatable and operationally safe**. Profit is
the result of an edge that survives that process, not a feature you add.

## 0. Foundation shipped (2026-11-10)

The deterministic foundation for all 12 workstreams is now in code:

| Foundation | Module | What it enforces |
|---|---|---|
| Data quality | `quant/data_quality.py` | Duplicate/conflict detection, gap classification, broker parity, content hash, blocking gate |
| Lifecycle | `quant/lifecycle.py` | `draft → … → retired` with evidence and actor on every transition; illegal jumps refused |
| Risk | `quant/risk_engine.py` | Per-trade sizing, lot/notional/margin/spread/exposure checks, daily loss and drawdown kill |
| OMS | `quant/oms.py` | Idempotency key, legal state machine, bracket validation, partial fills, reconciliation, TCA |
| Automation | `quant/live_runner.py` | One claim per strategy/version/timeframe/bar; restart-safe; pause/resume |
| Monitoring | `quant/monitor.py` | Signal parity, drift tolerances, P&L attribution and concentration |
| Capital | `quant/capital.py` | Inverse-vol risk budgeting with a hard weight cap and portfolio checks |
| Health | `quant/system_health.py` | One operator view; a blocked system cannot send a new order |
| Routes | `routers/quant_system.py` | Data quality, parity, lifecycle, risk, allocation, runs, health |
| UI | `system-health-panel.tsx` | Health score, checks, blockers and unknown inputs |
| Live integration | `quant/live.py` | The live trial claims a run key, runs risk checks, enforces a stop/target, records durable OMS state and supports a `run-due` scheduler hook |
| Data gate enforcement | `routers/quant.py` | A backtest with critical data findings is refused unless `allowDirtyData` is explicit |
| Durable OMS | `quant/oms_store.py` | Order state survives a restart; the idempotency key is unique in SQLite |
| Cost calibration | `quant/cost_calibration.py` | Observed slippage and commission become explicit backtest assumptions |
| Monitoring report | `routers/quant_system.py` | Trial, runs, broker account, positions, orders and P&L in one report |
| Repair | `quant/data_quality.py` | Exact duplicates dropped; conflicts keep the first row and are counted; gaps are never filled silently |
| Persistent risk | `quant/risk_state.py` | Day-start and peak equity persist; a daily-loss/drawdown breach auto-kills the trial |
| Scheduler | `quant/live_scheduler.py` | `run-due` runs every active trial on its current bar; each run is idempotent |
| Monitoring memory | `quant/monitor_store.py` | Daily parity, drift and attribution snapshots are stored |
| Model card | `quant/model_card.py` | Human-readable evidence record: state, assumptions, experiments, limits, owner |
| Golden freeze | `quant/golden.py` | Repair then freeze an immutable, content-hashed golden dataset |
| Live data gate | `quant/live.py` | A live signal is refused on critical data findings |

Tests: `python/tests/test_quant_system_core.py` (19), `test_quant_live.py` (5),
`test_quant_research_routes.py` (system + research routes) and QuantBench
(51/51, including data quality, risk, OMS and lifecycle). The remaining phases in
this document are the operational evidence track and the deeper venue-specific
work (broker-calibrated costs, 90-day demo, live ramp).

---

## 1. Current score and target

| Area | Now | Target | Gap |
|---|---:|---:|---|
| Research and method discovery | 8 | 9.5 | More methods, better literature coverage, automated extraction |
| Backtesting and validation | 8 | 9.5 | Broker-calibrated costs, tick/bar fidelity, replay |
| Data quality | 5 | 9.5 | Dedupe, gap policy, broker parity, point-in-time store |
| Execution | 6 | 9.5 | Idempotent OMS, brackets, retries, reconciliation, TCA |
| Risk management | 5 | 9.5 | Per-trade risk, daily loss, portfolio risk, hard kill |
| Automation | 5 | 9.5 | Bar-close scheduler, durable jobs, recovery, replay |
| Evidence of edge | 2 | 9 | 100+ trades, multiple regimes, paper/demo track, live track |
| Audit and honesty | 9 | 9.5 | Model risk, approvals, immutable evidence |
| UX and operations | 6 | 9 | Health, risk, drift, P&L, alerts, kill switch |
| **Overall** | **6** | **9.5** | |

The target is not "more features". It is **fewer trusted paths, each hardened**.

---

## 2. Target architecture

```
                    ┌────────────────────────────────────────────┐
                    │  Operator surfaces (Strategy Studio, UI)   │
                    │  health · risk · P&L · drift · kill        │
                    └───────────────────┬────────────────────────┘
                                        │
   ┌────────────────────────────────────┼────────────────────────────────────┐
   │                                    │                                    │
   ▼                                    ▼                                    ▼
┌──────────────┐   ┌──────────────────────────┐   ┌──────────────────────────┐
│ Data plane   │   │ Research plane           │   │ Execution plane          │
│              │   │                          │   │                          │
│ ingest       │──▶│ methods · papers         │──▶│ signal → intent → order  │
│ validate     │   │ hypotheses · trials      │   │ OMS · brackets · retry   │
│ reconcile    │   │ specs · reproductions    │   │ fills · positions        │
│ point-in-time│   │ backtest · validation    │   │ reconcile · TCA          │
│ golden sets  │   │ edge verdict · dossier   │   │ kill switch              │
└──────┬───────┘   └────────────┬─────────────┘   └────────────┬─────────────┘
       │                        │                              │
       └────────────┬───────────┴──────────────┬───────────────┘
                    ▼                          ▼
          ┌──────────────────┐       ┌──────────────────────┐
          │ Risk plane       │       │ Ops plane            │
          │ pre/in/post      │       │ scheduler · jobs     │
          │ limits as data   │       │ alerts · audit       │
          │ VaR/ES · stress  │       │ recovery · replay    │
          └──────────────────┘       └──────────────────────┘
```

**Non-negotiable rule:** the LLM orchestrates and explains. The deterministic
engine computes. The broker is the source of truth for live state.

---

## 3. Workstreams

### W1. Data foundation (highest priority)

The EURUSD 1h backtest reported **10,897 duplicate bars and 482 gaps**. That is a
blocker. A model cannot be trusted on data that is not clean.

Build:

1. **Canonical bar store** with a strict schema: symbol, venue, interval,
   timestamp, timezone, open/high/low/close/volume, spread, source, retrievedAt,
   dataAvailableAt, revision.
2. **Duplicate policy**: exact duplicates dropped; conflicting duplicates
   quarantined, never averaged silently.
3. **Gap policy**: classify expected session gaps, holidays, provider gaps and
   true missing bars. Fill only by an explicit, tested rule. Never forward-fill a
   price into a backtest without a warning.
4. **Broker parity check**: compare the backtest series with MT5 bars for the same
   symbol and period. Report overlap, mismatch and timestamp skew.
5. **Point-in-time store**: keep the value that was knowable at the decision time.
   A later correction creates a new revision, not a rewrite.
6. **Golden datasets**: frozen, hashed datasets for tests and benchmarks.
7. **Data quality gate**: a backtest cannot run on a dataset with critical
   findings unless the caller explicitly accepts them.

Files: `python/harness/market/`, `python/harness/quant/data.py`,
`quant/datasets.py`, `quant/manifest.py`, `scripts/` importers, front-door
connectors.

Exit criteria:

- zero exact duplicates in a golden window;
- every gap is classified and reported;
- broker parity report exists for each live symbol;
- a backtest is reproducible from a dataset hash;
- a critical data finding blocks a promotion.

### W2. Research and knowledge

Build:

1. Expand the method matrix beyond 33 seeds. Add families and variants through
   data, not code branches.
2. Add a **method implementation registry** with tests and ownership.
3. Add **hypothesis pre-registration** before a run. Every hypothesis carries a
   test, acceptance rule and invalidation rule.
4. Make the **trial ledger** mandatory. Every parameter combination is recorded,
   including failures.
5. Connect every experiment to a **Deflated Sharpe**, PBO, OOS and regime
   attribution record.
6. Add **research reproducibility**: one command re-runs a dossier's evidence.

Exit criteria:

- 100% of experiments have a trial row and a manifest;
- a dossier can be re-run from stored ids;
- a failed method remains findable;
- no model can be promoted without an OOS and multiple-testing record.

### W3. Model lifecycle and registry

Define one state machine:

```
draft → specified → implemented → backtested → validated
      → paper → live_trial → live → monitored → retired
```

Every transition has a gate and an artifact:

| Transition | Gate |
|---|---|
| specified → implemented | tests pass in isolation |
| implemented → backtested | data quality gate + costs |
| backtested → validated | OOS, walk-forward, robustness, DSR/PBO |
| validated → paper | operator approval |
| paper → live_trial | paper record + approval + arm |
| live_trial → live | live trial record + drawdown/cost checks |
| live → retired | decay, breach or operator decision |

Files: `quant/live.py`, `quant/ops_tools.py`, new `quant/lifecycle.py`,
`quant/store.py` tables, UI state.

Exit criteria:

- an illegal transition is refused, not logged and ignored;
- every state has a timestamp, actor and evidence;
- a strategy cannot skip paper unless the operator explicitly accepts the risk.

### W4. Backtest realism

Build:

1. **Broker-calibrated costs**: spread, commission, swap, financing and borrow
   from the broker, not guessed percentages.
2. **Fill model**: next-bar open is the default; add latency, partial fill,
   volume participation and rejection.
3. **Bracket fidelity**: stop and target are evaluated with the same bar order as
   the live system.
4. **Session and calendar**: exchange holidays, market breaks, DST and symbol
   trading hours.
5. **Replay**: re-run a live day bar by bar and compare signal parity.
6. **Cost attribution**: show how much of the edge is eaten by spread, slippage,
   commission and swap.

Exit criteria:

- backtest and live use the same signal code;
- documented cost model matches broker statements within a tolerance;
- a replay of a live day reproduces the same signal.

### W5. Risk engine

Limits are data, not branches.

Build:

1. **Pre-trade**: per-trade risk, max lot, max notional, max margin, spread gate,
   correlation gate, session gate.
2. **In-trade**: stop-loss required, trailing stop, time stop, max adverse
   excursion.
3. **Daily**: daily loss limit, trade count, loss streak, cooldown.
4. **Portfolio**: gross/net exposure, concentration, factor exposure, VaR/ES,
   stress scenarios.
5. **Kill**: kill on daily loss, max drawdown, data failure, broker failure and
   operator command.
6. **Sizing**: volatility-target and risk-per-trade sizing, not fixed lots.

Files: `quant/risk.py`, `portfolio/risk.py`, `risk_model.py`, `scenario.py`,
new `trade/risk_guard.py`, `trade/kill.py`.

Exit criteria:

- every order is checked against a named limit;
- a breach stops new orders and flattens or blocks as configured;
- the kill switch is tested in a drill;
- no live order can skip the risk engine.

### W6. Execution and OMS

Build:

1. **Order state machine**: new → validated → sent → acknowledged → partial →
   filled / rejected / cancelled / expired.
2. **Idempotency**: a client order id prevents a double send after a retry.
3. **Brackets**: stop and target attached at submit, not added later.
4. **Reconciliation**: positions, orders and fills read back and compared.
5. **Retry policy**: safe retries only for idempotent states; never duplicate.
6. **TCA**: slippage vs arrival price, fill ratio, rejection rate, latency.
7. **Symbol mapping**: internal symbol ↔ broker symbol, contract size, tick size,
   lot step, stops level.
8. **Partial fills**: handle remaining volume explicitly.

Exit criteria:

- zero orphan orders in a chaos test;
- a retry cannot create a duplicate order;
- every fill is reconciled;
- TCA is visible per order.

### W7. Automation and scheduling

Build:

1. **Bar-close event** per strategy and timeframe.
2. **Durable live runner**: one job per strategy/timeframe, restart-safe.
3. **Idempotent run key**: strategy + bar timestamp + signal.
4. **Pause/resume/stop** from the UI.
5. **Recovery**: restart after a crash and reconcile before the next order.
6. **Dead-letter queue** for failed runs.
7. **Replay** of a failed run.

Exit criteria:

- the runner survives a restart without duplicate orders;
- a missed bar is visible and does not silently skip;
- an operator can pause a strategy in one click.

### W8. Monitoring, drift and attribution

Build:

1. **Live vs backtest parity**: signal count, entry timing, fill price, slippage.
2. **Performance attribution**: P&L by strategy, symbol, regime, session, cost.
3. **Drift**: rolling Sharpe, win rate, expectancy, turnover, spread regime.
4. **Alerts**: drawdown, loss streak, data gap, broker disconnect, order reject.
5. **Model decay**: auto-throttle or stop when drift passes a limit.

Exit criteria:

- a daily health report exists;
- drift is measured, not guessed;
- an alert reaches the operator on the same bar.

### W9. Portfolio and capital allocation

Build:

1. Multiple strategies with correlation and exposure.
2. Capital allocation by risk budget, not equal notional.
3. Portfolio VaR/ES and stress.
4. Rebalancing and turnover control.
5. Strategy retirement and capital release.

Exit criteria:

- one strategy failure cannot breach the portfolio limit;
- allocation is explainable;
- portfolio drawdown is monitored and capped.

### W10. Governance, audit and security

Build:

1. Model risk: model card, assumptions, limitations, owner, review date.
2. Separation of duties: research, approval, deployment.
3. Immutable audit for approvals, orders, fills and config changes.
4. Change management for code and model versions.
5. Secrets and broker credentials never enter the model context.
6. Data licensing and provenance.
7. Incident runbook and post-mortem.

Exit criteria:

- every live change is attributable;
- an approval cannot be bypassed by a tool;
- a security review is part of the release gate.

### W11. Operator UX

Build:

1. **System health**: data, broker, scheduler, risk, last bar.
2. **Risk panel**: exposure, margin, daily P&L, drawdown, limits.
3. **Strategy panel**: state, signal, last order, drift.
4. **Research panel**: matrix, search, extraction, comparison, figures.
5. **Dossier viewer** with sources and experiments.
6. **Kill switch** always visible.
7. **Alert center** with acknowledgement.

Exit criteria:

- an operator can answer "is it safe?" in under 10 seconds;
- a kill action takes one click and is confirmed;
- every number links to its source.

### W12. Testing and benchmarks

Build:

1. Unit and property tests for the engine, risk and OMS.
2. Golden-dataset regression tests.
3. Simulated venue for order-state chaos.
4. Replay tests: live day vs backtest.
5. Adversarial honesty tests: no fabricated data, no fake fill.
6. QuantBench expansion: data quality, risk, OMS, drift.
7. CI gates: test, typecheck, size, registry, eval.

Exit criteria:

- a change cannot merge if a risk or OMS invariant fails;
- every benchmark case is deterministic;
- the benchmark covers the live path, not only the backtest.

---

## 4. Phases and sequencing

| Phase | Weeks | Scope | Exit gate |
|---|---|---|---|
| 0. Data truth | 1–2 | Dedupe, gap policy, broker parity, golden datasets | A clean golden window and a blocking data gate |
| 1. Lifecycle | 2–4 | State machine, gates, model cards, trial ledger | Illegal transitions refused; 100% trials recorded |
| 2. Risk first | 4–6 | Per-trade, daily, portfolio limits; kill drills | No order without a limit check; kill drill passes |
| 3. Execution | 6–8 | OMS, idempotency, brackets, retries, reconciliation, TCA | Chaos test: zero orphan or duplicate orders |
| 4. Automation | 8–10 | Bar-close runner, durable jobs, pause/resume, replay | Restart test: no duplicate order, no missed bar |
| 5. Monitoring | 10–11 | Parity, drift, alerts, attribution | Daily health report; drift alert on the same bar |
| 6. Portfolio | 11–12 | Allocation, correlation, portfolio risk | One strategy failure cannot breach portfolio limit |
| 7. UX and governance | 12–13 | Health, risk, alert, kill, audit, model risk | Operator can answer "safe?" in 10 seconds |
| 8. Paper/demo track | 13–25 | 90 days, 3+ strategies, live-vs-backtest | 100+ trades, no unexplained drift |
| 9. Live ramp | 25+ | Small size, then scale | Clean live record and review |

This is roughly **13 weeks of build + a 90-day evidence track** for a small team.
A solo engineer should expect 5–6 months.

---

## 5. Measurable definition of done

| Area | 10/10 gate |
|---|---|
| Data | 0 exact duplicates; 100% gaps classified; broker parity within tolerance |
| Reproducibility | 100% of promoted models re-run to the same result |
| Trials | 100% recorded, including failures |
| Validation | OOS + walk-forward + DSR + PBO for every promoted model |
| Risk | 0 orders without a limit check; kill drill passes |
| Execution | 0 orphan orders; 100% fills reconciled; TCA per order |
| Automation | Restart test passes; no duplicate order; no silent missed bar |
| Monitoring | Daily health report; drift alert; live-vs-backtest parity |
| Governance | Every live change approved and audited |
| Live evidence | 100+ trades, 3+ regimes, 90-day paper/demo, clean review |

### Strategy promotion thresholds (example, tune per market)

| Metric | Minimum |
|---|---|
| Trades in sample | 100 |
| Trades out of sample | 30 |
| OOS Sharpe | > 1.0 |
| Deflated Sharpe | > 0.95 |
| PBO | < 0.20 |
| Max drawdown | Within the mandate |
| Cost coverage | Edge survives 2× modelled costs |
| Regime coverage | At least 3 regimes |
| Live/paper divergence | Within a pre-set tolerance |

Do not treat these as magic numbers. They are **screens**, not guarantees.

---

## 6. Team and effort

| Role | Scope |
|---|---|
| Quant researcher | Edge, data, validation, model design |
| Backend engineer | Data, OMS, risk, scheduler, broker adapters |
| Frontend engineer | Health, risk, research, alert, kill UI |
| DevOps/security (part-time) | Deploy, secrets, backup, audit, incident |

One senior generalist can do it, but slower. Two engineers plus a quant is the
right shape.

---

## 7. What not to do

1. Do not add indicators to chase a backtest.
2. Do not optimize on the out-of-sample set.
3. Do not trade without a stop and a size rule.
4. Do not use fixed lots for every volatility regime.
5. Do not skip the trial ledger.
6. Do not let the LLM compute a statistic.
7. Do not enable live without arm, mandate, cap and kill.
8. Do not treat a 3-trade backtest as evidence.
9. Do not hide a data gap.
10. Do not call a paper result a live result.

---

## 8. First 10 days (start here)

1. **Freeze a golden dataset** for EURUSD and XAUUSD. Record duplicates, gaps,
   sessions and broker parity.
2. **Fix the data gate**: a backtest on a critical-gap dataset is refused unless
   accepted.
3. **Add per-trade risk and brackets** to the live trial: ATR stop, risk percent,
   max lot, daily loss.
4. **Add a bar-close runner** with an idempotent run key and pause/resume.
5. **Add a health panel**: last bar, broker state, open orders, exposure, daily
   P&L, drawdown, limits.
6. **Run a 30-day demo track** with three simple strategies. Record every signal,
   order, fill and rejection.
7. **Add a daily drift report**: signal parity, slippage, expectancy and cost.

If these seven items are done, the system is no longer a scaffold. It becomes a
system that can earn the right to trade.

---

## 9. The honest path to 10/10

A 10/10 system is not the system with the most features. It is the system where:

- the data is trusted;
- the model is reproducible;
- the risk is enforced;
- the execution is reconciled;
- the operation is boring;
- the evidence is honest.

Profit is not a score you assign. It is the outcome of doing these things long
enough to find and keep an edge.
