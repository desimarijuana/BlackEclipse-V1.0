---
title: Quant Method Discovery — find, adapt and invent tradable methods
status: Current
last-verified: 2026-11-10
---

# Quant Method Discovery

**Who this is for:** anyone working on `python/harness/quant/discovery/`, the
`*_method*` tools, the method panel in Strategy Studio, or the quant-mode
protocol.

## The job

Quant mode has one job above all others: **help a user find quantitative methods
they can understand and trade, and help them create new ones that survive a fair
test.**

That is not the same as "run a backtest" and not the same as "pick a strategy".
The loop is:

```
understand the method family
        -> scan the actual data
        -> write a falsifiable hypothesis
        -> synthesize a spec
        -> test (IS/OOS, costs, walk-forward, robustness)
        -> grade the evidence
        -> keep or reject the method
        -> if it survives: turn it into a playbook / paper deployment
```

Discovery is the front half. The deterministic engine is the back half. Neither
is allowed to pretend to be the other.

## What lives where

| Concern | File |
|---|---|
| Method families, theses, failure modes, regime priors | `quant/discovery/taxonomy.py` |
| Method cards + fit-ranked recommendations | `quant/discovery/library.py` |
| Market-structure diagnostics (trend / reversion / vol clustering / seasonality) | `quant/discovery/diagnostics.py` |
| Testable hypotheses + acceptance / invalidation rules | `quant/discovery/hypotheses.py` |
| Method → valid `StrategySpec`, and method composition | `quant/discovery/synthesize.py` |
| Bounded IS/OOS search with a real trial count + Deflated Sharpe | `quant/discovery/miner.py` |
| Agent tools | `quant/discovery_tools.py` |
| Persisted discovered methods | `quant/store.py` (`QuantMethod`) |
| HTTP | `routers/quant_desk.py` (`/quant/methods/*`, `/quant/discovered-methods/*`) |
| UI | `src/components/screens/strategy-studio/method-discovery-panel.tsx` |

## The method taxonomy

Every family carries the same fields, because "a method" is four things at once:

1. **A thesis** — why might this work?
2. **An edge source** — who is on the other side, and why do they keep losing?
3. **A specification** — signals, parameters, entry/exit.
4. **A failure map** — regimes where it should not work, and the usual ways it
   breaks.

The library is deliberately *descriptive*: `best_regimes` is a prior, not a
promise. `evidence` is a literature/runtime judgement, not a result on the
user's data.

## Invariants

- **A method card is not evidence.** `get_method_card` and
  `recommend_methods` may say a method *fits* a user's constraints. They may
  never say it has an edge.
- **A recommendation is explainable.** Every fit score is the sum of printed
  factors (asset match, horizon, objective, data availability, complexity,
  regime, evidence). No hidden score.
- **Diagnostics are descriptive, not predictive.** `scan_market_structure`
  labels what the sample looks like and, when possible, whether that label
  survives an out-of-sample tail. A structure that changes OOS is named as a
  warning.
- **Hypotheses are falsifiable.** Every generated hypothesis carries a test, an
  acceptance rule and an invalidation condition. Pre-register it before running.
- **Synthesis refuses the wrong container.** Cross-sectional momentum, pairs,
  carry, ML and options income are not forced into the single-asset rule DSL;
  they return their `requires` (factor lab, stats/cointegration, ML lab, option
  chain, futures term structure).
- **Mining counts every trial.** `mine_methods` is bounded, records the real
  number of candidates tried, and deflates the selected Sharpe with that count.
  A candidate is still `candidate | weak | rejected`, never "validated".
- **A composition is new and valid.** `combine_methods` creates a conjunction
  of two entries (e.g. trend + volatility filter), names its `derivedFrom`, and
  must validate before it can be used.
- **Persistence does not promote.** Saving a method records it. Promotion to
  `validated | promoted` is a separate, explicit bookkeeping decision; it does
  not create evidence.
- **Current setups are conditions, not orders.** `scan_current_setups` evaluates
  the entry rule on the latest *closed* bar; `scan_universe_setups` repeats it
  across a bounded watchlist (max 12 symbols) and reports per-symbol failures
  instead of hiding them. Neither routes an order or ranks a setup as a
  recommendation.

## The discovery tools

| Tool | Job |
|---|---|
| `list_method_families` | What methods exist, filterable by asset/horizon/complexity |
| `get_method_card` | Thesis, edge source, signals, failure modes, validation, example spec |
| `recommend_methods` | Fit-rank families to the user's constraints, with reasons |
| `scan_market_structure` | Trend/reversion/vol-clustering/seasonality + candidate families |
| `generate_method_hypotheses` | Falsifiable hypotheses with acceptance and invalidation |
| `synthesize_method_strategy` | Method → valid spec with explicit costs/sizing/risk |
| `combine_methods` | Two methods → a new, validated conjunction |
| `mine_methods` | Bounded IS/OOS search, real trial count, Deflated Sharpe |
| `scan_current_setups` | Which validated methods have an entry condition now |
| `mine_universe_methods` | Mine the same families across a bounded universe and aggregate support |
| `scan_universe_setups` | The same scan across a bounded watchlist (max 12 symbols) |
| `generate_trading_playbook` | Plain-language entry/exit/sizing/risk/execution, invalidation and monitoring |
| `save_discovered_method` | Persist a method with its spec and evidence |
| `list_discovered_methods` | The local method catalogue |
| `promote_discovered_method` | Explicit status transition |

## The trading playbook

A method that survives is still not a set of instructions. `playbook.py` renders
the *actual spec* into a playbook: entry conditions, exits, protective legs,
sizing, risk limits, execution assumptions, the regimes it should work in, the
ways it fails, the invalidation conditions, and a monitoring checklist. It adds
no rule the spec does not contain and no claim the evidence does not support; it
always ends with the paper-first rule and the not-advice note.

## The UI

`MethodDiscoveryPanel` sits above the spec editor in Strategy Studio. It lets the
user pick asset/horizon/objective/risk, recommend methods, scan the series, see
current setups, mine candidates and load a synthesized spec into the editor.
"Mine" shows the trial count and the OOS result, and says plainly that a
candidate is not a validated strategy.

`ResearchJournalPanel` is where the user pre-registers hypotheses and records
trials, so the method that survives has a defensible history.

## Bringing your own data

Discovery does not bundle paid data. A provider adapter is expected to supply,
and label, the data each family declares:

- OHLCV + timestamps + adjustment basis (the minimum for the single-asset rules);
- volume for participation fills and the liquidity/capacity check;
- option-chain snapshots (date, spot, expiry, IV, strikes) for options income;
- multiple futures expiries + a roll schedule for carry;
- funding rates + perp/spot prices for crypto carry;
- point-in-time fundamentals, event dates and a survivorship-controlled universe
  for value/quality/event methods.

`recommend_methods` takes the user's `availableData` list and penalises families
whose requirements are not met, naming the missing data. A method is never run
on a proxy without saying so.

## Honest limits

- The library's edge sources and regime priors are informed summaries, not a
  meta-analysis. The user's own data decides.
- The miner searches a **bounded** grid of known families and one optional
  composition. It does not search an unbounded strategy space, and it does not
  discover a new economic mechanism.
- Diagnostics need at least 30 bars; a short sample is refused rather than
  labelled.
- Calendar effects are multiple-testing-prone and are flagged as such.
- A "setup now" is not a recommendation and never becomes an order; live routing
  remains disabled.
