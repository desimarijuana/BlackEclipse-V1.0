---
title: Journal ↔ Broker Sync
status: Current
last-verified: 2026-11-02
---

# Journal ↔ Broker Sync

**Who this is for:** anyone connecting a broker account to the journal, or
changing how broker trades become journal trades.

## The rule that governs everything

> **The Python broker store is the source of truth for execution. `jdds.db`
> holds a projected copy that is safe to rebuild.**

The broker connection, its fills, its positions and its sync cursor live in the
Python harness (`agent-memory.db`, `python/harness/trade/store.py`). The journal
holds a *projection* of those facts in its own tables. No journal code ever
talks to MetaTrader, and no credential is copied into `jdds.db`.

This is deliberate: two independent writers to the same truth would drift. One
writer (the reconciler) plus one reader/projector (the journal) cannot.

## Ownership (guest vs authenticated)

`getOrCreateProfile()` resolves the request's auth session cookie
(`src/lib/journal/owner.ts`). When authentication is active, the profile id is
deterministic (`jp_<userId>`) and every trade, broker link, review, day and
account is scoped to it; two users never share journal rows. When auth is off
(the zero-config local app), the journal uses the oldest guest profile exactly
as before. If the deployment requires auth but a request reaches a journal route
without a live session, the journal **fails closed** rather than falling back to
the guest profile.

The first authenticated user **adopts the pre-auth guest journal** (the guest
profile is stamped with that `userId`) so enabling auth does not orphan existing
trades. A later user never inherits it. The boot demo seeder also skips when
auth is required (a signed-in user can still seed their own journal from the
UI). Broker **connections** remain
operator-level in the Python harness; the journal **link** and the projected
trades are per-profile. Making the connection itself per-user is a separate
change to the Python store and its operator routes.

## Data flow

```
MT5 terminal
   │  IPC (Python only)
   ▼
BrokerReconciler.sync()          python/harness/trade/reconcile.py
   │  BrokerFill / BrokerPositionSnapshot / BrokerSyncState
   ▼
GET /trading/connections/{id}/reconciliation      (operator-token route)
   │
   ▼
src/lib/journal/broker/source.ts    read-only mirror reader
   │
   ▼
src/lib/journal/broker/project.ts   pure grouping/mapping (tested)
   │
   ▼
src/lib/journal/broker/sync.ts      one-way upsert into jdds.db
   │
   ▼
Trade (source='broker', externalId='broker:<connection>:<position>')
```

`POST /api/journal/broker/sync` is the only path that writes projected trades.

## Identity and idempotency

One journal trade = **one broker position** (`positionTicket`), not one deal.
Scale-ins, partial closes and several fills collapse into weighted-average
entry/exit and summed costs.

- `Trade.externalId = "broker:<connectionId>:<positionTicket>"`
- unique per `(profileId, externalId)`
- a second sync updates the same row; it never creates a duplicate

Deals without a `positionTicket` (balance operations) and deals with no usable
price/volume/time are skipped and reported in `warnings`. They are never guessed.

## Field ownership (the conflict policy)

| Broker owns | User owns |
|---|---|
| symbol, direction, entry, exit, quantity | notes, emotion, confidence, grade |
| entry/exit time, status | checklist, screenshots, annotations |
| commission, swap/fee, net P&L | a strategy/setup they assigned themselves |
| position/deal tickets | tags they added |

A broker-owned field edited by hand is restored on the next sync, and a
`broker_reconciled` `TradeExecution` row records both values. A user's own
strategy/setup is never replaced (`existing.strategyId ?? projected.strategyId`).
Attribution rules only fill gaps and add tags; they never remove a tag.

Deleting a broker-sourced trade sets `ignoredAt` instead of destroying the row.
That is a tombstone: the externalId stays dead and sync will not resurrect it.
Manual and demo trades still delete normally.

## Concurrency and API hardening

- **Per-connection coalescing.** A manual sync, another tab and the auto-sync
  timer share one in-flight promise per `(profile, connection)`; a second caller
  receives the running sync instead of starting a second writer.
- **Dual-server tolerance.** Dev and production can share `jdds.db` and
  `agent-memory.db`. If the other process wins the unique `externalId` or
  `(tradeId, dealTicket)` insert, the collision is treated as success and the
  rows converge on the next sync — never as a failed import.
- **Broker-owned fields are refused on PATCH.** `entry/exit/stopLoss/
  takeProfit/quantity/times/commission/fee/symbol/direction` on a broker trade
  return `409` with the field names; only user-owned fields are written. This is
  enforced in `data.ts` via the shared list in
  `src/lib/journal/broker/ownership.ts`, and the UI hides Edit for broker trades.
- **No P&L recompute on a broker trade.** A user-field PATCH keeps the broker's
  `pnl`/`rMultiple` and writes only the user columns, so it cannot race a sync
  into a price-derived number.
- **Links are verified.** Creating a link validates the connection with the
  runtime first and rejects malformed ids; an unknown connection is a `400`, a
  down runtime a `503`. Linking stamps the chosen account's
  `brokerConnectionId`; re-linking or unlinking clears the previous binding. A
  unique `(profileId, accountId)` index (plus an app-level check) enforces one
  journal account per broker connection.
- **Ignored trades stay hidden.** Every trade lookup used by the journal
  (update, fills, executions, screenshots, annotations, market context) filters
  `ignoredAt: null`.
- **Bounded/guarded reads.** Preview is rate-limited (12/min/IP); sync is
  rate-limited (6/min); errors are logged server-side and returned as generic
  messages, never as Prisma/broker internals.

## P&L convention

Forex/CFD profit cannot be recomputed from `(exit − entry) × quantity` without
contract size, so broker trades use `pnlBasis = 'broker'`:

- `grossPnl` = Σ deal profit (before costs)
- `commission` = −Σ deal commission (positive cost; a rebate is negative)
- `fee` = −Σ swap (positive financing cost)
- `pnl` = Σ (profit + commission + swap) — the broker's own arithmetic

`rMultiple` is computed only when a stop is known: `pnl / riskAmount`, where
`riskAmount` is the stop distance **converted to account currency**. FX/CFD price
points are not money: one XAUUSD point is worth 100 per lot, one EURUSD point
100 000. The projection calibrates that factor per symbol from the broker's own
gross P&L —
`multiplier = Σ grossPnl / Σ (signed price move × quantity)` — and uses
`(entry − stop) × quantity × multiplier`. Without calibration (e.g. an open
position whose symbol has no closed trade yet) the trade has **no** risk amount
and no R, instead of a 100×-inflated one. MT5 deal history does not carry SL/TP,
so the projection takes them from the open-position snapshot. A sync therefore
preserves a previously captured SL/TP when the position closes; it never erases
it. A trade first seen after it already closed has no R-multiple until a snapshot
is captured.

`pnlPct` is a **price-relative move** — `sign × (exit − entry) / entry` — the same
unit manual trades store. It is deliberately not `pnl / notional`: FX/CFD contract
size is not modelled, so that ratio is meaningless (a 0.01-lot EURUSD trade once
reported −70.7).

### When R is unavailable

`rMultiple = 0` does **not** mean "breakeven" for a broker trade; it means the
risk was never measurable. The journal therefore:

- classifies each trade with `classifyTradeOutcome()` — R when
  `riskAmount > 0`, otherwise the sign of the realized P&L — so wins, losses,
  breakevens, win rate, streaks, dimension breakdowns, the calendar heatmap and
  psychology leaks stay truthful for imported trades;
- sets `PerformanceStats.rAvailable = false` when no closed trade has an R basis,
  and the UI renders Net R / Expectancy / Max Drawdown / R distribution as
  **UNAVAILABLE** rather than `+0.00R`;
- draws the equity and drawdown charts from the currency curve instead
  (`currencyEquity` = cumulative realized P&L, starting from the profile account
  size when set), which is always available;
- computes **profit factor in account currency** (gross winning P&L ÷ gross
  losing P&L) — the standard definition, and the one that survives missing stops;
- leaves the R cell blank in CSV exports and `—`/`UNAVAILABLE` in the PDF.

A day or month switches to P&L in the calendar only when **every** trade in that
group lacks an R basis; mixed groups keep R, because at least one trade has a
measurable risk.

An **open** position never renders an R-multiple (its risk is still unrealized),
even when the broker snapshot carries a stop: the trade shows `open` in the P&L
column and `—`/UNAVAILABLE for R until it closes.

## Deal-level fills

The aggregate trade is not the only record. Every projected deal is also stored
as a `TradeFill` row (unique by `(tradeId, dealTicket)`), so the trade detail can
show scale-ins, partial closes and multi-fill exits exactly as the broker
reported them. Deals are immutable: `syncFills` only inserts missing tickets and
never rewrites one. This is a projection of `BrokerFill`, not a second broker
store.

`GET /api/journal/trades/{id}/fills` returns them chronologically. A trade
first seen as an open snapshot has no fills until a deal appears; the next sync
fills the gap without touching the aggregate trade.

## Broker analytics and agent tools

`computeJournalAnalytics` gains `byAccount` (account name, or `Unassigned`) and
`byMagic` (broker magic only; manual/CSV trades are intentionally absent). They
render in the Analytics tab next to the existing dimensions.

The journal agent gains `get_broker_status` (which links exist, enabled/auto-sync,
last sync status) and `get_broker_performance` (performance computed **only**
from `source = 'broker'` trades, with per-account and per-magic splits). The
performance prompt tells the model never to mix broker and manual/demo trades
without saying so.

## Attribution

`BrokerAttributionRule` maps broker metadata to journal meaning:

| Matcher | Match |
|---|---|
| `magic` | exact MT5 magic number |
| `commentMatch` | case-insensitive substring |
| `symbolMatch` | case-insensitive glob (`XAU*`) |
| `connectionId` | exact connection, or null for all |

Highest `priority` wins, then insertion order. A rule can set `strategyId`,
`setupId` and `tagNames`. Rule ids are validated against the profile before use;
a stale rule cannot create a dangling foreign key.

Symbol suffixes are handled separately by the link's `symbolMap`
(`"XAUUSDm": "XAUUSD"`), because they are a broker naming convention, not an
analytical attribution.

## Surfaces

| Surface | Path |
|---|---|
| Links | `GET/POST /api/journal/broker/links`, `PATCH/DELETE /api/journal/broker/links/[id]` |
| Rules | `GET/POST /api/journal/broker/rules`, `DELETE /api/journal/broker/rules/[id]` |
| Dry run | `GET /api/journal/broker/preview?connectionId=…` (never writes) |
| Sync | `POST /api/journal/broker/sync` (rate-limited, idempotent) |
| Fills | `GET /api/journal/trades/[id]/fills` (read-only projected deals) |
| UI | Journal → Settings → Broker Connection; trade detail → Broker Fills |

A preview reads the *current* mirror; it does not refresh it. A sync refreshes
the mirror first (`POST /trading/connections/{id}/sync`), then projects.

## Historical backfill

The reconciler's ordinary pass reads a small rolling window — enough to keep a
recently-synced mirror current, not enough to recover months of history. The
journal therefore computes the window it actually needs:

| Situation | Window requested |
|---|---|
| Never synced | the link's `backfillDays` (default 90, bounds 7–3650) |
| Gap since `lastSyncedAt` ≤ 5 days | none (the rolling window covers it) |
| Long gap | `min(backfillDays, gapDays + 2)` |
| User pressed **Full backfill** | the link's `backfillDays` |

It sends `POST /trading/connections/{id}/sync` with `{ "days": N }`. The Python
`BrokerReconciler.sync(history_days=N)` calls the adapter's `deals_window(N)`
instead of the incremental `deals_since`, writes the mirror, and dedupes by
`(connectionId, dealTicket)`. The read is bounded and read-only: it never places
an order, and fills are paged 1,000 at a time by `(dealtAt, id)` so a large
backfill is complete rather than truncated.

`JOURNAL_BROKER_SYNC_SECONDS` does not affect the window; it only controls the
auto-sync cadence.

## Auto-sync

`startJournalBrokerSync()` starts one timer from the Next instrumentation boot
pipeline. It only considers links with `enabled` **and** `autoSync` set, and only
when `lastSyncedAt` is older than the cadence (default 300 s, minimum 60 s,
`JOURNAL_BROKER_SYNC_SECONDS=0` disables it).

- Single-flight: a slow terminal cannot stack ticks.
- Sequential across links, so two brokers do not fight for one terminal.
- A failed sync backs that connection off for 5 minutes instead of retrying
  every tick.
- It calls the same `syncJournalBroker` path as the button; there is no second
  import path.

## Failure behaviour

- Python runtime down → link status `unavailable`, no writes, no fake rows.
- Broker disconnected → same, with the broker's reason. Preview reports the
  stale-mirror state as unavailable instead of presenting old rows as current.
- A failed sync keeps the last good projection; it never deletes history.
- Concurrent syncs coalesce; a cross-process unique collision is success, not a
  failed import.
- Honest timeouts: the runtime request is bounded (45 s).

## Known limits (Phase 2)

- Fills are paged at 1,000 per request with a `(dealtAt, id)` cursor, hard
  bounded at 20 pages (**20,000 deals** per sync). A larger history needs a
  different storage strategy, not a bigger response.
- Open positions are projected; their floating P&L is not written into `pnl`.
  Only realized P&L from closing deals is stored.
- SL/TP and therefore R-multiples are available only if a snapshot was captured
  while the position was open (see above). When no trade has a basis, R metrics
  render UNAVAILABLE instead of `0R`.
- The MT5 deal window widens its lower bound by 3 days and its upper bound by 2
  days because `history_deals_get` reads terminal/server time and the process
  clock can be hours off; the mirror dedupes by deal ticket, so the extra deals
  are harmless.
- A backfill only covers what the broker's `history_deals_get` can still return;
  brokers expire history on their own schedule. Eclipse never fabricates a deal
  it cannot read.
- One profile per install today (the guest profile). Multi-user ownership of
  broker links is a later change, same as the rest of the journal.
- Built-in adapters are MT5, a read-only MT4 HTTP bridge, Alpaca and IBKR
  (read-only). Alpaca/IBKR executions are normalized by `adapters/fifo.py` into
  FIFO round-trips, so their journal rows carry `pnlBasis="computed"` and the
  trade detail says the P&L is computed, not broker-reported. Binance/Coinbase
  remain CSV import. The projection consumes the normalized `BrokerDeal` shape,
  so adding one does not touch the journal.

## Upgrading an existing database

The broker tables and columns are additive, so a fresh install just works. The
one exception is the unique `(profileId, accountId)` index on
`JournalBrokerLink`: Prisma treats adding an index to an existing table as a
data-loss warning. The journal link table is new, so in practice it is empty.
Verify and apply once:

```bash
# expect [] (no duplicates)
sqlite3 jdds.db "SELECT profileId, accountId, COUNT(*) c FROM JournalBrokerLink
                 WHERE accountId IS NOT NULL
                 GROUP BY profileId, accountId HAVING c > 1;"
npx prisma db push --accept-data-loss
```

The app also enforces one account per connection in `links.ts`, so a missed
index is a defense-in-depth gap, not a correctness hole.

## Production checklist

Run this once per deployment, before trusting the sync with money data.

1. **Clean, reviewed commit.** Production must build from a clean commit, not a
   mixed working tree.
2. **Checks.** `npm run build`, `npx tsc --noEmit`, the full `npm run test`, and
   `python scripts/broker_smoke.py --connection <id> --days 30`.
3. **Database.** Back up `jdds.db`; run `prisma db push`; confirm the
   `JournalBrokerLink` unique indexes and `TradeFill` table exist. Keep the
   rolling backup from `scripts/db-guard.js` healthy.
4. **Auth.** Set `HARNESS_AUTH_SECRET` and `CRON_SECRET`; put the app behind
   HTTPS; create the first operator. Broker routes are operator-only when auth
   is on.
5. **Broker.** Compare the smoke test's deal tickets and P&L against the
   broker's own statement for the same window. Alpaca/IBKR P&L is
   Eclipse-computed FIFO — reconcile it before relying on it.
6. **Failure drills.** Close the terminal / expire the IBKR cookie / stop the
   Python runtime. The UI must show `UNAVAILABLE`, no fake trades may appear,
   and the last good projection must remain.
7. **Automation.** Set `JOURNAL_BROKER_SYNC_SECONDS`, enable `autoSync` on one
   link, and confirm exactly one pass runs.
8. **Topology.** One app instance per `jdds.db`/`agent-memory.db` pair. SQLite
   and the in-process locks/rate limits are not a multi-instance design.

## Verification

- Pure projection tests: `npx vitest run src/lib/journal/broker/project.test.ts`
  (single fill, scale-in, partial close, open snapshot, closing-only deal,
  determinism, skipped deals, symbol map, attribution priority).
- Auto-sync due/backoff rules: `src/lib/journal/broker/scheduler.test.ts`.
- Deal-level fills in the projection: `project.test.ts` asserts the exact deal
  tickets/prices, not just the aggregate.
- Account/magic dimensions: `src/lib/journal/analytics.test.ts`
  (`groups broker trades by account and magic…`).
- Field ownership and connection-id validation:
  `src/lib/journal/broker/ownership.test.ts`.
- Backfill window + dedupe: `python/tests/test_broker_reconcile.py`
  (`test_history_backfill_uses_an_explicit_window_and_dedupes`) and fill-cursor
  paging (`test_fills_page_with_a_stable_dealt_at_cursor`).
- FIFO normalizer: `python/tests/test_fifo_normalizer.py` (single, scale-in,
  partial, short, fees, flip).
- Alpaca/IBKR contracts: `python/tests/test_alpaca_adapter.py`,
  `python/tests/test_ibkr_adapter.py`.
- Smoke report: `python/tests/test_broker_smoke.py`; live CLI
  `python/scripts/broker_smoke.py`.
- `npx tsc --noEmit` from `Black-Eclipse-site/`.
- Manual: Settings → Broker Connection → Link → Preview → Sync. The trade list
  should show the same count as the preview's new+update total, with broker P&L.
  **Full backfill** re-requests the configured window; it does not duplicate.

## File map

| Concern | File |
|---|---|
| Ownership resolution | `src/lib/journal/owner.ts` (auth session → profile id) |
| Pure projection | `src/lib/journal/broker/project.ts` |
| Broker mirror reader | `src/lib/journal/broker/source.ts` |
| Link + rule persistence | `src/lib/journal/broker/links.ts` |
| Field ownership + id validation | `src/lib/journal/broker/ownership.ts` |
| Sync orchestration | `src/lib/journal/broker/sync.ts` |
| Auto-sync timer | `src/lib/journal/broker/scheduler.ts`, started in `src/instrumentation.ts` |
| API routes | `src/app/api/journal/broker/**`, `src/app/api/journal/trades/[id]/fills` |
| UI | `src/components/journal/broker-sync-settings.tsx` (settings), `trade-detail.tsx` (fills), `analytics-view.tsx` (by account/magic) |
| Agent tools | `src/lib/agent/journal-tools.ts` (`get_broker_status`, `get_broker_performance`) |
| Schema | `JournalBrokerLink`, `BrokerAttributionRule`, `TradeFill`, broker fields on `Trade`/`TradingAccount` |
| Broker side | `python/harness/trade/reconcile.py` (`history_days`), `adapters/mt5.py` (`deals_window`), `routers/trading.py` (`POST /sync {days}`) |
