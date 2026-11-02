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

## P&L convention

Forex/CFD profit cannot be recomputed from `(exit − entry) × quantity` without
contract size, so broker trades use `pnlBasis = 'broker'`:

- `grossPnl` = Σ deal profit (before costs)
- `commission` = −Σ deal commission (positive cost; a rebate is negative)
- `fee` = −Σ swap (positive financing cost)
- `pnl` = Σ (profit + commission + swap) — the broker's own arithmetic

`rMultiple` is computed only when a stop is known: `pnl / ((entry − stop) × qty)`.
MT5 deal history does not carry SL/TP, so the projection takes them from the
open-position snapshot. A sync therefore preserves a previously captured SL/TP
when the position closes; it never erases it. A trade first seen after it already
closed has no R-multiple (0 / unavailable) until a snapshot is captured.

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
| UI | Journal → Settings → Broker Connection |

A preview reads the *current* mirror; it does not refresh it. A sync refreshes
the mirror first (`POST /trading/connections/{id}/sync`), then projects.

## Failure behaviour

- Python runtime down → link status `unavailable`, no writes, no fake rows.
- Broker disconnected → same, with the broker's reason.
- A failed sync keeps the last good projection; it never deletes history.
- Honest timeouts: the runtime request is bounded (45 s).

## Known limits (Phase 1)

- The broker mirror is fed by the reconciler's **7-day** deal window and the
  fills endpoint returns at most 500 deals. A first import therefore covers the
  recent window only. A wider historical backfill needs a read-only
  `/trading/connections/{id}/history` endpoint (Phase 2).
- Open positions are projected; their floating P&L is not written into `pnl`.
  Only realized P&L from closing deals is stored.
- SL/TP and therefore R-multiples are available only if a snapshot was captured
  while the position was open (see above).
- One profile per install today (the guest profile). Multi-user ownership of
  broker links is a later change, same as the rest of the journal.
- MT5 is the only live adapter. MT4/Binance/Coinbase remain CSV import until a
  Python adapter exists; the projection consumes the normalized `BrokerDeal`
  shape, so adding one does not touch the journal.

## Verification

- Pure projection tests: `npx vitest run src/lib/journal/broker/project.test.ts`
  (single fill, scale-in, partial close, open snapshot, closing-only deal,
  determinism, skipped deals, symbol map, attribution priority).
- `npx tsc --noEmit` from `Black-Eclipse-site/`.
- Manual: Settings → Broker Connection → Link → Preview → Sync. The trade list
  should show the same count as the preview's new+update total, with broker P&L.

## File map

| Concern | File |
|---|---|
| Pure projection | `src/lib/journal/broker/project.ts` |
| Broker mirror reader | `src/lib/journal/broker/source.ts` |
| Link + rule persistence | `src/lib/journal/broker/links.ts` |
| Sync orchestration | `src/lib/journal/broker/sync.ts` |
| API routes | `src/app/api/journal/broker/**` |
| UI | `src/components/journal/broker-sync-settings.tsx`, mounted in `journal-settings.tsx` |
| Schema | `JournalBrokerLink`, `BrokerAttributionRule`, broker fields on `Trade`/`TradingAccount` |
