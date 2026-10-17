---
title: Fiduciary Advice (the Advisory Gate)
status: Current
last-verified: 2026-10-16
---

# The Fiduciary Gate

**Who this is for:** anyone changing how an agent's answer is verified before
release, or reasoning about where an action recommendation's trust label comes
from.

BlackEclipse makes a promise no chat window makes: **it does not hand you an
actionable recommendation it cannot stand behind.** The Fiduciary Gate is the
deterministic check that enforces it at the answer seam.

```
final answer ──▶ extract actionable claims ──▶ match against the run's
                                              portfolio computations / consulted
                                              sources ──▶ COMPUTED | SOURCED
                                                       | UNVERIFIED (+disclosure)
```

## What an "actionable claim" is

A sentence in the final answer that carries an **actionable directive**
(`buy`, `sell`, `add`, `trim`, `reduce`, `exit`, `rebalance`, `allocate`,
`hedge`, `harvest`, `short`, `increase`) **and** a tradable token — a symbol
(`AAPL`, `BRK.B`) or a numeric target (`5%`, `$10k`, `100 shares`, `60/40`).

An opinion with neither (`"I'd avoid the sector"`), or ordinary prose
(`"Revenue grew this quarter"`), is never flagged. The gate stays silent unless
there is a concrete recommendation to verify.

## The three truth labels

| label | meaning |
|---|---|
| **COMPUTED** | A portfolio computation the run actually performed backs it (re-run the engine, get the same numbers). |
| **SOURCED** | The recommendation names a symbol the run consulted through the portfolio, with no numeric target. Grounded in your own ledger. |
| **UNVERIFIED** | Neither. The advice rests on nothing the run produced and is disclosed, never presented as clean. |

A `COMPUTED` verdict is only possible because the run's `portfolio_*` tool calls
are recorded as it works (the `AdvisoryCollector`), including the exact symbols,
target weights/amounts and the tool that produced them. A numeric target that
*contradicts* the computation (the answer says 90%, the engine said 60%) is
**UNVERIFIED**, not silently corrected.

## Where it runs and what it never does

- **Seam:** `graph.execute_run`, at the same answer seam as the finance-fact gate
  (`finance_facts/enforce.py`) and the citation release gate
  (`research/release_gate.py`). The two gates are siblings: one verifies *figures*,
  one verifies *advice*, one verifies *citations*.
- **Deterministic:** no model call, so it works with any provider or none.
- **Additive:** wrapped so it can never fail a run; a claim-free answer is
  returned byte-for-byte.
- **Honest:** it never rewrites or deletes the advice — it appends a disclosure
  naming the unverified recommendation(s).
- **Proposal-only:** it never places a trade. Every recommendation stays a
  proposal, consistent with the portfolio engine (`docs/portfolio-accounting.md`).

On an `UNVERIFIED` verdict the answer gains:

> `Advisory note: the following recommendation(s) are not backed by a portfolio
> calculation or a consulted source, so they are unverified advice, not verified
> analysis: <claims>.`

The verdict is emitted as an `advisory.gate` event and attached to the run's
blob as `metadata.advisoryIntegrity`, so a surface can render which claims were
computed/sourced vs. disclosed.

## Where it lives

- **Runtime:** `python/harness/advisory/` — `model.py` (claim + verdict vocab),
  `claims.py` (deterministic extractor), `collector.py` (`AdvisoryCollector`),
  `gate.py` (`enforce_advisory_answer` + `apply`).
- **Wiring:** `python/harness/graph.py` (the `advisory_sink` on `ToolContext`, the
  per-tool recording, and the answer-seam gate) + `python/harness/tools.py`.
- **Tests:** `python/tests/test_advisory_gate.py`.

## The Advisory Ledger

The gate's verdict is not thrown away. Every actionable claim becomes a durable
**decision** in the Advisory Ledger (`agent-memory.db`), recorded once (idempotent
on a deterministic id, so a resumed run never double-counts) with:

- **what** was recommended (action, symbols, target, the thesis),
- **on what basis** — a `computation` reference (the `portfolio_*` tool that
  backed it) and/or `source` references (the URLs the run consulted), or `none`
  when unverified,
- **how it turned out** — an appended `AdvisoryOutcome` (realized vs benchmark
  return, right/wrong/neutral).

Read it back through the `advisory_list` / `advisory_get` / `advisory_scorecard`
agent tools, or the operator-gated `/advisory/*` routes, or the **Decisions** view
in the Journal screen (`advisory-decisions.tsx`). The scorecard is a deterministic
summary (counts by status, evaluated count, hit rate, average realized vs
benchmark).

**Outcomes evaluate deterministically.** When a decision is recorded, the run
captures the entry price it observed (from its portfolio computations, stored as
an `entry_price` basis row). `AdvisoryService.evaluate_decisions` /
`evaluate_outcome` compute the realized return from a caller-supplied mark;
`auto_evaluate(gateway)` fetches the marks itself. A decision with no entry price
or no quote is skipped, never fabricated. Exposed via the
`advisory_evaluate_outcomes` tool and `POST /advisory/evaluate`. Nothing here
places a trade.

## Proactive monitors ("works while you're gone")

The ledger's outcomes and the gate's discipline extend to work that runs with no
chat open. The Automation Engine already schedules condition-triggered
automations; Phase 3 gives its conditions a **portfolio** lens:

- **`PortfolioFactProvider`** (`automation/facts.py`) resolves
  `pf.<portfolioId>.<field>` variables — `weight.<SYM>`, `unrealized.<SYM>`,
  `cash_pct`, `concentration_hhi`, `total_value`, `position_count` — through the
  ONE portfolio engine. A failed read or unpriced position yields **no fact**, so
  the three-valued condition engine evaluates `UNAVAILABLE` and never fires on a
  guess. It runs behind a `CompositeFactProvider` alongside the market provider.
- **A closed monitor catalogue** (`advisory/monitors.py`):
  `position_weight_breach`, `tax_loss_harvest`, `cash_buffer_watch`,
  `concentration_watch`. Each builds an ordinary `condition` automation with a
  `run_agent` action. A monitor is **created switched off** (`state="disabled"`);
  only the operator arms it. Exposed via `GET/POST /automations/monitors`.
- **`portfolio_harvest_candidates`** (`portfolio/harvest.py`) is the deterministic,
  proposal-only raw material a tax-loss decision is made from; it states the
  wash-sale limitation rather than pretending to enforce a rule it cannot see.

Monitors explain a trigger and propose a response — they never execute a trade.

## Related

- [`portfolio-accounting.md`](./portfolio-accounting.md) — the engine whose
  computations make a claim `COMPUTED`.
- [`DECISIONS.md`](./DECISIONS.md) and `docs/harness/decisions.md`
  (ADR-H196 the gate, ADR-H197 the ledger, ADR-H198 the monitors) — the decision
  record.
- `docs/harness/automation-engine.md` — the engine the monitors build on.
- [`NAVIGATION.md`](./NAVIGATION.md) — the trigger row for this surface.
