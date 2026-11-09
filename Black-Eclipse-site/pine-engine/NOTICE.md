# The Pine engine — licence boundary

This folder is a **separate program**. Eclipse does not import it; it spawns it
as a child process, hands it a JSON request file, and reads back a JSON
response file. The only thing that crosses the boundary is data.

## Why it is separate

The Pine Script runtime this program uses is **`pinets`** (PineTS, by LuxAlgo),
licensed **AGPL-3.0-only**. Running it inside the Eclipse app would arguably
make the app a derivative work of an AGPL program. Keeping it in its own
program, communicating only through files, follows the "separate programs
communicating at arm's length" pattern from the GPL FAQ.

## What that means for you

- **The Eclipse app is MIT-licensed** (see the repository `LICENSE`). It never
  links against `pinets`; it executes a separate program that does. This folder
  is AGPL-3.0-only, so treat it as its own component, not as MIT code.
- **This folder is the corresponding source of the AGPL-covered work here.**
  It is public, in this repository, and it is the exact source of the program
  the app runs. If you change `runner.mjs`, you change the corresponding
  source — keep it that way.
- **The engine's own corresponding source ships with the package it came
  from.** `pinets` is distributed on npm under AGPL-3.0 with its source and
  licence included; nothing from it is copied into this repository.
- **The engine never reaches the network.** The bars arrive in the request, so
  a Pine script is always evaluated against the data the caller already has.

## Installing it

```
npm run setup:pine
```

That installs `pinets` into `pine-engine/node_modules` (gitignored). Until it
is installed, the runtime refuses honestly: the agent tool and the route both
answer with `PINE_ENGINE_UNAVAILABLE` and the command to run — never an empty
result that looks like a script that plotted nothing.

## The protocol

```
request   { source, bars: [{time,o,h,l,c,v}], symbol, timeframe, limit, maxLoops, responsePath }
response  { status: "ok", plots, trades, warnings, diagnostics }
          | { status: "error", code, message, name, stack }
```

`plots` maps a plot name to `{ title, points: [{time, value}] }`; `value` is
`null` while the indicator is warming up. `trades` are the strategy's closed
and open trades, with their entry and exit prices, sizes and P&L.
