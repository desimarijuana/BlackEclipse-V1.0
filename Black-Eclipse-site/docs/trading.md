---
title: Broker Connectivity
status: Current
last-verified: 2026-10-29
---

# Broker Connectivity

**Who this is for:** anyone connecting a broker to Eclipse, adding a broker
adapter, or wondering why a trading widget says `UNAVAILABLE`.

This is **P4: demo + armed live execution with reconciliation**. Eclipse can attach
to a broker, report its account, positions, working orders and quotes, submit orders
for a **demo** account or an **armed live** account, and durably reconcile fills,
positions and order state. Live is off by default: arming requires a typed phrase, a
non-zero magic, a positive maxMargin and a time box, and every live order needs its
own typed phrase. Graph Studio can submit demo orders under a bounded mandate. The
internal simulator (`trading.paper_order`) remains available.

## The one rule

> The broker is the source of truth. Eclipse never invents a fill, a position, a
> balance or a connection.

A broker that is missing, logged out, disconnected or unsupported returns a named
reason (`PACKAGE_MISSING`, `TERMINAL_NOT_FOUND`, `NOT_LOGGED_IN`, `NO_IPC`, …),
never an empty account that looks real.

## Connection model

A **connection** is a durable row, not a credential bag:

```
BrokerConnection
  id, kind, label, mode (demo | live | unknown)
  config  { terminalPath?, magic?, symbolMap?, bridgeUrl?, baseUrl?, ... }
  status  (unconfigured | connected | unavailable) + statusReason
  account (last account snapshot)
  lastSeenAt, createdAt, updatedAt
```

- Config keys are allowlisted (`model.ALLOWED_CONFIG_KEYS`).
- Anything shaped like a password/token is **refused at write time**
  (`model.validate_config`); it is never stored and redacted later.
- `BrokerConnectionEvent` is an append-only audit of tests/reads/failures.

The preferred MetaTrader path is **attach**: the operator logs into
`terminal64.exe` once, and Eclipse calls `mt5.initialize(path=...)` with no
credentials. Nothing secret enters the app, the database or model context.

## Broker kinds and how each connects

| Kind | Transport | Auth | Eclipse path |
|---|---|---|---|
| **MetaTrader 5** (`mt5`) | Local IPC to `terminal64.exe` | attach to a logged-in terminal | `adapters/mt5.py` |
| MetaTrader 4 (`mt4_bridge`, planned) | MQL4 EA mailbox on localhost | bridge secret | EA + adapter |
| Alpaca (`alpaca`, planned) | HTTPS REST | API key in the vault | REST adapter |
| IBKR (`ibkr`, planned) | TWS/Gateway socket | gateway session | socket adapter |
| Any plugin broker | plugin host | per-plugin encrypted secrets | `plugins/` |

A new broker is a **registration**, not a refactor. It implements
`BrokerAdapter` and is declared in `trade/registry.py`:

```python
class MyBrokerAdapter(BrokerAdapter):
    kind = "mybroker"

    @classmethod
    def availability(cls) -> tuple[bool, str | None]:
        return (True, None) if sdk_installed() else (False, "the SDK is not installed")

    def probe(self) -> dict: ...        # honest status, never a fake success
    def account(self) -> dict: ...
    def positions(self) -> list[dict]: ...
    def orders(self) -> list[dict]: ...
    def quote(self, symbol: str) -> dict: ...

register_kind(BrokerKind(id="mybroker", label="My broker", auth="credentials"),
              MyBrokerAdapter)
```

Then the existing routes (`/trading/connections/{id}/...`), the read-only tools
(`broker_account`, `broker_positions`, …) and the UI work unchanged.

## MetaTrader 5 setup (demo first)

1. Install **MetaTrader 5** (Windows x64) and log the terminal into a **demo**
   account. Leave the terminal running.
2. Enable **Algo Trading** in the terminal toolbar. Reads work without it; the
   probe warns when it is off because execution will need it.
3. Install the Python package in the Eclipse runtime:
   `pip install MetaTrader5` (Windows x64; now pinned in `python/requirements.txt`
   with a Windows-x64 marker, so `npm run setup:python` installs it; the terminal
   remains a separate manual install).
4. Open **Settings › Broker connection** and click **Add & test connection** (kind `mt5`,
   mode `demo`, terminal path prefilled). The panel shows the account, server,
   balance/equity, margin mode and warnings. The API equivalent is
   `POST /trading/connections`:
   ```json
   { "kind": "mt5", "label": "MT5 demo", "mode": "demo",
     "config": { "terminalPath": "C:\\Program Files\\MetaTrader 5\\terminal64.exe" } }
   ```
   `terminalPath` is optional; common install paths and `MT5_TERMINAL_PATH` are
   probed. `portable: true` is supported.
5. The panel probes automatically (`POST /trading/connections/{id}/test`) and
   shows exactly what is wrong if it is not connected. **Test** and **Sync** remain
   available on the connection card.
6. Optionally map broker-specific symbol suffixes:
   `"symbolMap": { "EURUSD": "EURUSD.a" }`.

### What the MT5 adapter reads

`account_info()` (login, company/server, balance/equity/margin, leverage,
demo/contest/real, netting/hedging), `positions_get()`, `orders_get()`,
`symbol_info()` + `symbol_info_tick()` (bid/ask, spread in points, digits, volume
min/max/step, stops level). It never calls `order_send`, never selects symbols,
and never stores a login password.

## Demo execution (P1)

```
intent ──▶ order_preview (normalize volume, stops, filling, order_check)
        ──▶ TradePolicy (margin / volume / spread / open positions / allowlist)
        ──▶ money guardrails (per-transaction, daily, velocity, crisis)
        ──▶ single-use approval (kind="trade_order", digest over the exact order)
        ──▶ order_send (once; never retried on an ambiguous result)
        ──▶ BrokerOrder ledger + reconciliation by the operator
```

**Two independent demo gates.** The connection record must say `demo`, *and* the
broker's `account_info().trade_mode` must report `demo` at preview and again at
submit. A live record or a real account is refused with `LIVE_NOT_ENABLED` /
`LIVE_ACCOUNT_REFUSED`, even if the other gate says demo.

**The approval is the payload.** `OrderIntent.digest` covers connection, symbol,
side, type, volume, price, SL, TP, deviation, time-in-force, magic and comment.
Submitting a different order against the same approval fails with
`APPROVAL_ORDER_MISMATCH`. The approval is consumed atomically before the send,
so a second submit needs a fresh decision.

**Typed confirmation and cooling-off are enforced.** When the money guardrails
set `requiresTypedConfirmation` (for example a high-value order), the preview
returns the exact `confirmPhrase` and the submit body must repeat it; a missing
phrase returns `CONFIRMATION_REQUIRED` and does **not** consume the approval. If
the verdict carries a cooling-off, an early submit returns `COOLING_OFF` with the
remaining seconds. The operator can retry the same approval after both conditions
are satisfied, within its five-minute TTL.

Endpoints (operator-gated):

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/trading/connections/{id}/orders/preview` | validate + `order_check` + request approval; sends nothing |
| `POST` | `/trading/connections/{id}/orders/submit` | consume the approval and `order_send` once |
| `POST` | `/trading/connections/{id}/orders/{ticket}/cancel` | cancel a working order (risk-reducing; no approval) |
| `GET` | `/trading/connections/{id}/orders/ledger` | local submitted-order ledger |
| `GET` | `/trading/orders/{orderId}` | one ledger row |
| `GET` | `/trading/approvals` | `trade_order` approvals |
| `POST` | `/trading/approvals/{id}/decide` | approve or deny (operator only) |

Agent tools add `order_preview` (creates an approval, never sends) and
`order_ledger`. There is deliberately **no `order_submit` agent tool**: submitting
is an operator action on the same approval the preview created.

**Never retry an ambiguous send.** A timeout, a lost IPC reply or any exception
after `order_send` marks the ledger `unknown` and tells the operator to check the
terminal. Eclipse does not resend, because MetaTrader has no client order id and a
blind retry can double the position.

**What `order_check` proves.** Volume step/min/max, stops distance, symbol trade
mode, filling mode, pending-price side, and the margin impact. `order_check` is
not a promise the fill will happen; it is the broker's pre-trade verdict.

**A preview refusal is an outcome, not a server error.** When the account mode or
terminal switch blocks a preview, the API returns `allowed: false` with
`error.code` (`ALGO_TRADING_DISABLED`, `DEMO_ACCOUNT_REQUIRED`, `LIVE_NOT_ARMED`,
`LIVE_ARM_EXPIRED`) and `reasons`, not a 500. The operator/agent can read the exact
gate. MT5 IPC sessions are serialized in-process, so concurrent broker tool calls
cannot collide in `initialize`.

## Live execution (P2)

Arming is a separate, operator-only action:

```
POST /trading/connections/{id}/arm
{ "confirmation": "ARM LIVE 12345678", "ttlSeconds": 1800 }
```

Before the arm is stored, Eclipse reads the broker account and requires:

1. the connection mode is `live`;
2. `account_info().trade_mode` is **real**;
3. Algo Trading is enabled in the terminal;
4. a **non-zero magic** is set, so the kill switch only touches Eclipse orders;
5. a **positive `maxMargin`** is set, a mandatory live cap.

The arm is time-boxed (60 s to 8 h) and is cleared by a mode/config change, a failed
probe, expiry, or the kill switch. Disarm explicitly with
`POST /trading/connections/{id}/disarm`.

**Every live order is a second decision.** The preview returns
`confirmPhrase: "LIVE BUY 0.1 EURUSD"` and always sets
`requiresTypedConfirmation`. Submit must repeat that exact phrase; a missing or
wrong phrase returns `CONFIRMATION_REQUIRED` without consuming the approval. The
single-use approval still binds the exact order digest, and the money guardrails
still apply (caps, crisis mode, cooling-off).

**Kill switch.** `POST /trading/connections/{id}/kill` cancels every working order
whose magic matches the connection, then disarms. It refuses when the magic is 0.
It does **not** close open positions: a close is a different action that is not yet
exposed; use the terminal until that is designed.

## Unattended demo graph orders (P3)

A Graph Studio node cannot show an approval card. P3 adds an explicit substitute:
an operator-created **mandate** for ONE demo connection.

```
POST /trading/connections/{id}/mandates
{
  "confirmation": "MANDATE DEMO My demo",
  "symbols": ["EURUSD", "GBPUSD"],
  "maxOrders": 20,
  "maxMargin": 500,
  "ttlSeconds": 86400
}
```

A mandate names the allowed symbols, a margin cap per order, a maximum number of
orders and an expiry (60 s to 7 days). It is demo-only: creating one on a live
connection returns `LIVE_MANDATES_DISABLED`. Every use is counted atomically, so a
looping graph cannot exceed `maxOrders`. Revocation is immediate
(`POST /trading/mandates/{id}/revoke`).

The Graph Studio node `trading.broker_order` takes an order intent plus a
`connectionId` and `mandateId`. It runs only in **paper** mode; the compiler and the
front door still refuse a live trading node. The node calls the SAME
`BrokerService.submit_order` path, so the connection policy, money guardrails,
demo/real account check and ambiguity rules all still apply. The mandate is
consumed before the send and the ledger records `mandateId`.

There is still no unattended live trading. A live mandate is not implemented; the
compiler refuses live trading graphs, and `create_mandate` refuses a live
connection. That remains a separate design with a separate review.

**Agent-driven demo execution.** Settings → Broker connection can create and
revoke the same mandates. Once an active mandate exists, ask Eclipse in chat to
analyze a market and place one order under it. The agent calls `order_submit`
directly (it previews and submits in one call), and the result appears in the
position book and ledger. The agent cannot create the mandate, arm live, cancel,
or exceed the mandate’s symbols / margin cap / order count / expiry. A verified
demo run placed ticket **11164809214** (EURUSD BUY 0.01, SL 1.11125, TP 1.12260)
under mandate `mnd_c82ba003d785`.

## Reconciliation (P4)

The broker is authoritative, so Eclipse keeps a durable local copy of what it
says happened:

```
POST /trading/connections/{id}/sync
GET  /trading/connections/{id}/reconciliation
GET  /trading/connections/{id}/fills
```

One sync reads positions, working orders and deal history, then writes:

| Table | Contents |
|---|---|
| `BrokerFill` | one row per deal, deduped by `(connectionId, dealTicket)` |
| `BrokerPositionSnapshot` | the current positions, replaced atomically each sync |
| `BrokerSyncState` | last sync time, advisory cursor, status, counts and the last error |

It also reconciles in-flight ledger orders: an order whose broker history is
`filled`, `partial`, `cancelled`, `rejected` or `expired` is moved to that state.
An order still present in the working set is marked `placed`. A sync never guesses:
an unknown or missing broker answer leaves the ledger row alone.

A failed sync records `error`/`unavailable` in `BrokerSyncState` and keeps the last
good fills and snapshot; it never deletes history or fabricates a fill.

**Background loop.** The reconciler is OFF by default. Set
`TRADING_RECONCILE_SECONDS` (minimum 15) to run it on a cadence; it only touches
connections whose status is `connected` or `unavailable`, and it never places an
order. Manual `POST .../sync` always works.

**History window.** Each sync asks MetaTrader for the last 7 days of deals, with a
2-day future margin. `history_deals_get` expects **server** time, and the Python
process clock can be hours behind or ahead (the current demo is +2h); a tight
local-time cursor silently drops the newest fill. Dedupe by deal ticket absorbs the
overlap, so the stored cursor is advisory, not authoritative.

## Surface

| Layer | File |
|---|---|
| Contracts | `python/harness/trade/model.py` |
| Adapter protocol | `python/harness/trade/adapter.py` |
| Registry | `python/harness/trade/registry.py` |
| Store (`agent-memory.db`) | `python/harness/trade/store.py` |
| Service | `python/harness/trade/service.py` |
| Pre-trade limits | `python/harness/trade/policy.py` |
| Demo mandates | `python/harness/trade/mandates.py` |
| Approval + guardrail seam | `python/harness/trade/authorizer.py` |
| MT5 adapter | `python/harness/trade/adapters/mt5.py` |
| Reconciliation | `python/harness/trade/reconcile.py` |
| Graph node | `python/harness/graph_runtime/trading_nodes.py`, `src/lib/graph-studio/registry-trading.ts` |
| Tools | `python/harness/trade/tools.py` |
| Boot wiring | `python/harness/trade/bootstrap.py`, `service.py` |
| Routes | `python/harness/routers/trading.py` |
| Front door | `src/app/api/trading/[[...path]]/route.ts`, `src/lib/harness/trading-routes.ts` |
| Client | `src/lib/harness/trading-client.ts` |
| Settings UI | `src/components/screens/trading-settings.tsx` |
| Sidebar connect | `src/components/layout/sidebar-broker-dialog.tsx` |
| Dashboard widgets | `src/lib/dashboard/trading-widgets.tsx` |

Routes are operator-gated (loopback or runtime token); the front door injects
the token and never exposes it. The allowlist includes preview/submit/cancel,
arm/disarm/kill, sync/reconciliation/fills, mandate create/revoke and
approval-decide paths, but no bare order-send path: `POST /trading/orders`
returns an honest `501`.

Agent tools: `broker_connections`, `broker_account`, `broker_positions`,
`broker_orders`, `broker_quote`, `order_preview` (requests an approval, sends
nothing), `broker_mandates`, `order_submit` (the ONE effectful tool),
`order_ledger`, `broker_reconciliation` and `broker_fills`. `order_submit` requires
an active operator-created **demo** mandate; it cannot create/revoke a mandate,
arm live, cancel an order, or submit live. `order_cancel`, arm/disarm and the kill
switch remain operator routes.

**Why `order_submit` is admitted by a mandate, not the generic approval card.**
An unattended mandate already carries the operator's consent, scope and caps. The
generic approval gate would double-gate it and make an "analyze then trade" run
impossible. The tool therefore runs through the same `BrokerService.submit_order`
path, and that handler/service enforces the demo account mode, policy, money
guardrails, symbol allowlist, max margin and the mandate order count. Live mandates
do not exist, so the agent cannot reach live.

The dashboard's five `trading` widgets (Quick Trade, Open Positions, Working
Orders, Margin Usage, Today P&L) now read the FIRST saved connection and poll it
every 15 s. Quick Trade runs preview → approve → submit against the same API and
shows the policy/guardrail reasons; Working Orders can cancel a ticket (risk-reducing,
no approval); a missing connection renders a Settings → Broker connection setup note instead
of a fake number. Today P&L is broker deals since local midnight plus the account's
floating P&L, labelled as broker-reported.

The shell's quick-launcher row (next to **Gateway** and **Graph**) also carries a
**broker icon** (handshake) with an **MT5** badge in its popup. In the collapsed
rail it stays in the footer. It opens a compact broker dialog with the live status
dot, account, **Test**, **Sync**, and an **Add & test connection** form — so a user
can connect MT5 from any screen without opening Settings. The dialog uses the same
`rounded-2xl border border-white/10 glass-card-strong` recipe as the Gateway/Graph
dialogs. Live arming and mandates remain in Settings → Broker connection.

## Roadmap

| Phase | Adds | Gate |
|---|---|---|
| **P0 (done)** | attach + read account/positions/orders/quotes | read-only |
| **P1 (done)** | demo order submission via `order_check` -> approval -> `order_send` | connection AND broker account must be `demo`; single-use approval |
| **P2 (done)** | armed live submission + kill switch | real account, Algo Trading, typed arm phrase, non-zero magic, positive `maxMargin`, time-boxed arm, per-order `LIVE ...` phrase |
| **P3 (done)** | Graph Studio `trading.broker_order` + bounded, revocable demo mandates | paper-mode graph + operator paper grant + demo connection + active mandate; live trading nodes remain refused |
| **P4 (this)** | durable fills/positions/order-state reconciliation | broker history is the only source; a failed sync is an error, never a fake fill |
| P5 | close/flatten + unattended live mandates | separate design + review; not enabled by P4 |

P4 deliberately does not add position closing or live automation. Reconciliation
makes the existing manual live path observable; those are separate risk decisions.

## Honest boundaries

- Windows-only for MT5; other hosts report `PLATFORM_UNSUPPORTED`.
- The Python package attaches to a **running terminal**; it cannot conjure one.
- `initialize(path)` may start a terminal that is not running. The operator
  should log in first; Eclipse never supplies a password.
- Quotes are the broker's feed, not JDDS. They are broker-specific and may differ
  from other providers.
- Reads are synchronous IPC calls; every call opens a short session. A future
  streaming/reconciliation loop will own a long-lived session.
- Live submission requires an **armed** connection, a real account, a non-zero
  magic and a positive `maxMargin`; a demo account is refused on a live connection
  and a real account is refused on a demo connection. The check reads
  `account_info()` itself.
- The kill switch cancels **working orders only** (by magic). It does not close
  positions. Closing a position is a separate action and is not implemented yet.
- Unattended mandates are **demo-only**. A live graph is refused by the compiler
  and the front door, and a live connection cannot create a mandate.
- Reconciliation copies what the broker reports. It does not mark positions to
  market itself; `currentPrice`/`profit` are the broker's values at sync time.
- The background reconciler is off unless `TRADING_RECONCILE_SECONDS` is set.
- A demo fill is still a real broker round-trip (latency, requotes, spread), but
  it is not evidence that a live strategy is profitable.
