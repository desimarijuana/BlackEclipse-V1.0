---
title: Pine — running a TradingView script on Eclipse's own bars
status: Current
last-verified: 2026-11-17
---

# Pine — running a TradingView script on Eclipse's own bars

**Who this is for:** anyone working on `python/harness/quant/pine.py` or
`Black-Eclipse-site/pine-engine/`, or anyone asking "can I run the Pine
strategy I already have on my own data?"

**The one rule:** a Pine script is evaluated **on the bars the caller already
holds**, by an engine that **never reaches the network**, in a **separate
program** the app spawns rather than imports.

## What it is

Pine is the lingua franca of TradingView. A trader who has a Pine strategy
usually cannot run it anywhere else — the script is bound to TradingView's
data and their broker's fills. This subsystem runs it **here**, against the
data Eclipse already holds, and returns the script's plots and the trades its
strategy made.

| Piece | Where | What it does |
|---|---|---|
| the engine program | `Black-Eclipse-site/pine-engine/` | a separate Node program: JSON request in, JSON response out |
| the Python seam | `python/harness/quant/pine.py` | spawns the engine, bounds it, and refuses honestly |
| the tool | `quant/advanced_tools.py` → `run_pine_script` | the agent's door onto it |
| the route | `python/harness/routers/pine.py` → `POST /quant/pine` | the API's door onto it (no app screen calls it — the agent is the entry point) |

## The licence boundary

The Pine Script runtime is **`pinets`** (PineTS, by LuxAlgo), AGPL-3.0-only.
It is **not** a dependency of the app and **not** imported by it. It lives in
its own program with its own `package.json`, and Eclipse spawns it as a child
process and talks to it over files: a JSON request in, a JSON response out.
Nothing but data crosses the boundary.

That is the "separate programs communicating at arm's length" pattern from the
GPL FAQ, and it is what keeps the AGPL work in its own component instead of
reaching into the MIT app. The consequences are stated in `pine-engine/NOTICE.md`:

- this folder is the **corresponding source** of the AGPL-covered work here,
  and it is public with the app;
- nothing from `pinets` is copied into this repository — it ships with the
  npm package it came from;
- if you change `runner.mjs`, you change the corresponding source.

## The protocol

```
request   { source, bars: [{time,o,h,l,c,v}], symbol, timeframe, limit, maxLoops, responsePath }
response  { status: "ok", plots, trades, warnings, diagnostics }
          | { status: "error", code, message, name, stack }
```

`plots` maps a name to `{ title, points: [{time, value}] }`, where `value` is
`null` while the indicator warms up. `trades` are the strategy's closed and
open trades, with entry and exit prices, bar indexes, sizes and P&L.

The engine's internal drawing helpers (`__labels__`, `__lines__`, …) are
filtered out: they are not the script's plots.

## The rules the runtime keeps

- **The engine never reaches the network.** The bars come in the request, so a
  Pine script is always evaluated against the data the caller already has.
- **A missing engine is a named refusal.** `PINE_ENGINE_UNAVAILABLE` names
  the command to run (`npm run setup:pine`) — never an empty result that looks
  like a script that plotted nothing.
- **A Pine runtime error is the script's error**, reported with its own
  message — never swallowed, never replaced with a zero.
- **The child is bounded**: a timeout (`PINE_TIMEOUT`), a bar cap, a source
  cap, and a **scrubbed environment**. The child never inherits the runtime's
  API keys, tokens or database paths; it gets a PATH, a temp dir and nothing
  else.

## Data sources

The tool and the route accept either:

- `bars` — an explicit OHLCV list; or
- `datasetId` (+ `version`, `symbol`) — a stored research dataset, read back
  out of the quant dataset store.

Both paths land in the same place: the bars go into the request, and the
engine evaluates against them.

## Surfaces

| Surface | Entry point |
|---|---|
| The agent | `run_pine_script` — the source, the bars (or a dataset), and the result |
| The runtime | `POST /quant/pine` (run) and `GET /quant/pine` (is the engine installed?) |
| The picture | the first plot is drawn through the ONE chart engine and recorded in the Artifact Center |

## What it is not

- **Not a second backtest engine.** The quant engine still owns Eclipse's own
  strategies, fills, costs and metrics. Pine is a **language** front end: the
  script's trades come from the Pine engine's own broker model, and they are
  reported as the engine produced them, not re-accounted by ours.
- **Not a TradingView replacement.** No Pine-to-quant-engine translation, no
  fill-model equivalence claim, no data from TradingView.
- **Not a live-trading path.** A Pine run is a bounded, historical evaluation.

## Grading a Pine run with Eclipse's own machinery

`python/harness/quant/pine_report.py` is the adapter that lets a Pine run be
judged by the same engines that judge an Eclipse strategy. It does three things
and nothing else:

1. **Translate** the Pine engine's trades into the engine's own trade shape.
2. **Rebuild** the equity and drawdown curves the metrics engine needs, from
   the bars the script was actually run on.
3. **Hand over** to the existing engines: `metrics` computes the numbers,
   `regime` classifies the conditions, `montecarlo` resamples the sequence,
   `verdict` grades it, `edge_report` writes the document.

So a TradingView script gets an **Eclipse-native A-F grade**, with the same
regime attribution, the same Monte-Carlo fan and the same downloadable report
as a strategy written in Eclipse.

The Monte-Carlo needed one small generalisation to serve this: the families
that resample a *recorded* trade sequence (the reshuffle and the regime-block
methods) now work on any recorded run
(`MonteCarloEngine.from_recorded`). The families that re-run the *strategy*
(parameter and execution perturbation) cannot ? a Pine script is not ours to
re-run ? and they refuse with a named reason instead of pretending.

### What the adapter does not do

It does **not** re-account the trades. The Pine engine's own fills, sizes and
P&L are taken as produced, and the report says so in two warnings that travel
with the artifact:

- `PINE_EQUITY_MARKED_AT_EXIT` ? the equity curve is marked at each trade's
  exit bar, because the Pine engine reports fills, not a mark-to-market curve.
  Per-bar volatility is therefore understated and the risk-adjusted ratios are
  optimistic relative to a mark-to-market curve.
- `PINE_FILLS_ARE_THE_ENGINES_OWN` ? the fills are the Pine broker model's, so
  they are not comparable to an Eclipse backtest's fills.

Both warnings appear in the Edge Report's "Warnings from the run" section, so
a reader cannot miss them.

Surfaces: the tool `grade_pine_script`; the route `POST /quant/pine/report`.

## The fix loop

`python/harness/quant/pine_repair.py` is the loop QuantPad demonstrates: the
script fails, the model reads the failure and rewrites the script, and the
engine runs it again.

The policy is **reused, not reinvented**: the budget (`RepairBudget`), the
outcome vocabulary and the output digest all come from the code verify-and-
repair subsystem (`code/repair.py`, `code/verify.py`), so a Pine fix loop and
a code fix loop are bounded the same way and report the same way.

```
source ??? engine ??ok??? done
   ?            ?
   ?         failed
   ?            ?
   ????? the model rewrites the script (bounded, fenced)
```

Two rules the loop keeps:

- **The failure text is DATA, not instruction.** A Pine error can contain
  anything the script put in it, so it is fenced (`<pine-error>`), labelled
  and bounded to 4,000 characters before it reaches the model.
- **A failed patch is not a pass.** A reply without a fenced script is not a
  patch - the loop stops rather than guessing where the script starts in a
  wall of prose - and a script that still fails is reported as still failing.

The model's reply must be a single fenced ```pine block; the loop runs the
patched script before anything is claimed, so the engine is always the judge.

Surfaces: `run_pine_script` with `autoFix` and `maxFixAttempts`; the loop is
also callable directly (`repair_pine_script`).

## What it is not

Tests: `python/tests/test_quant_pine.py` (the engine tests skip when Node or
the engine is absent — the Python side must never pretend it is there).
