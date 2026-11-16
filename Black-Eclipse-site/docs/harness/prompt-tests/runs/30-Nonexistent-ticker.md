# 30. Nonexistent ticker

- runId: `run_d9e384cb-5e41-4973-bb6e-48b87d518b8a`
- status: **completed**
- steps: 3 / tools: 4 / toolErrors: 0
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T20:49:47.317Z / finishedAt: 2026-11-16T20:49:59.955Z

## Prompt

What's the current price of a ticker that does not exist, ZZZZQ?

## Answer

**ZZZZQ has no price â it isn't a real ticker.** Every route came back empty:

| Route | Result |
|---|---|
| Entity resolution (`financial_resolve_entity`) | UNAVAILABLE â not in the instrument universe |
| Unified quote retrieval (`market_get_quote`) | UNAVAILABLE â no eligible source answered |
| Market snapshot (`get_market_snapshot`) | UNAVAILABLE â not in the instrument universe |
| Web search (`web_search`, as-of 2026-11-16) | No securities page anywhere; results were unrelated noise, which is itself consistent with the symbol being fictitious |

The last rung (web) returned nothing that even purports to quote ZZZZQ, so there is no page left to extract â this is a genuine "no such instrument" outcome, not a data gap I can route around. I'm not going to emit a placeholder or illustrative price for it.

Two things worth noting:

- **`Q` is a valid Nasdaq ticker suffix** (it denotes a Chapter 11 bankruptcy filing â e.g. `BBBYQ`, `WEQ`), which is presumably why the format looks plausible. But a valid format is not a valid listing: `ZZZZQ` fails resolution entirely, so it's not a delisted-bankruptcy shell either.
- **`ZZZZ` (four Z's) does historically exist** as a placeholder/test symbol on some exchanges and data feeds, and some vendors use all-letter-extreme tickers as test fixtures. If you're testing how this runtime handles unknown symbols, the behaviour is as intended: refuse rather than invent.

If you meant a real name â a delisted or bankrupt ticker, an OTC micro-cap, or a non-US listing â give me the company or ISIN and I'll resolve it properly.
