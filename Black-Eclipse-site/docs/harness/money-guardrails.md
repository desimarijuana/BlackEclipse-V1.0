---
title: Money-movement guardrails
status: Current
last-verified: 2026-10-28
---

# Money-movement guardrails

**Who this is for:** anyone changing how a financial action is authorized, or
wondering why Eclipse stopped a transfer.

Eclipse already has a single-use, digest-bound approval store
(`mcp/approvals.py`) and a Security Gateway that can only add restriction. This
layer adds the **financial-harm checks** those layers do not attempt: scam and
coercion, impaired spending, crisis, aggregate limits and a money-specific
confirmation gate.

The layer is **deterministic and model-free**. No LLM decides whether money
moves. Every verdict is explainable and replayable.

## The contract

```
tool call → Security Gateway (floor / policy / risk)
          → FinanceGuardrailService.evaluate(MoneyIntent)
          → allow | confirm | escalate | deny
          → single-use approval store → ApprovalCard (typed confirm + cooling)
```

`python/harness/finance_guardrails/models.py` holds the contracts:

- `MoneyIntent` — action, amount/currency, counterparty, instrument, account,
  channel, run, and the visible text used for signal scanning.
- `GuardrailVerdict` — decision, reasons, matched rules, risk, cooling-off,
  typed-confirmation phrase, escalation target.
- `combine(...)` merges rule verdicts and can only choose the *more restrictive*
  decision. Reasons accumulate so the operator sees every signal.

## The pipeline (`service.py`)

Order is absolute → soft:

1. **Panic pause** (`crisis.panic-pause`) — denies every money intent on every
   channel, even when the guardrail mode is `off`.
2. **Crisis mode** — blocks discretionary trading; escalates irreversible
   transfers/payments with a long cooling-off and the trusted contact.
3. **Limits** (`limits.py`) — per-transaction cap, daily cap, velocity, and
   counterparty allow/block lists, measured over the persisted ledger.
4. **Scam / coercion** (`scam.py`) — deterministic markers: urgency, secrecy,
   impersonated authority/support, remote-access requests, guaranteed returns,
   advance fees, gift cards, wire-only rails, off-platform moves. Two or more
   high-severity markers deny; one confirms with a 15-minute cooling-off.
5. **Impaired spending** (`impaired.py`) — a self-declared state adds a
   30-minute pause; behavioural signals (amount ≫ 3× the user's p95, three
   roughly doubling movements) confirm with a pause.
6. **Novelty / high value** — a first-time counterparty on an irreversible rail
   always confirms; a high-value threshold confirms with cooling-off.

A `confirm` is **not** a pass. It routes the exact intent through the same
single-use approval store (`kind="money_guardrail"`). The digest covers action,
amount, currency, counterparty, instrument, account and tool, so an operator
approval can never authorize a different payload. The runtime re-checks the
cooling-off elapsed time when it consumes the approval, so a fast click cannot
bypass it.

## Enforcement points

The guardrail is called from the points where a real action would occur:

| Channel | Where | Behaviour |
|---|---|---|
| Computer Use | `computer/tools.py` `_finance_prepare` and `_computer_use` (click/type) | deny refuses; confirm forces approval even in autonomous mode |
| Browser | `browser/tools.py` `_click` | a payment-shaped click passes guardrails before the page is touched |
| MCP | `mcp/approvals.py` `make_effect_authorizer` | evaluated **before** grants/approvals; a standing grant cannot bypass a deny; confirm adds a cooling check |
| Shell / terminal | `code/authorizers.py` `_wrap_with_money_guardrails` | a command naming a broker/payment surface plus a money verb is gated before its own command approval |
| Native tools | `finance_guardrail_status` / `finance_guardrail_check` | read-only: the agent may ask, never change |
| Native broker orders (P1 demo) | `trade/authorizer.py` | evaluated before the single-use `trade_order` approval; a deny refuses; the approval is required even for an allow |

The generic `computer_use` click gate is deliberate: a prompt telling the model
not to click Submit was never enforcement.

## Persistence

`store.py` owns two tables on the ONE `agent-memory.db` connection (idempotent
DDL, no migration step):

- `MoneyGuardrailConfig` — the operator's singleton settings.
- `MoneyIntent` — every evaluated intent, decision, reasons, rules and risk.
  Aggregates (today, 30 days, last hour, p95) are derived from it.

Nothing in these tables is secret.

## Operator surface

Python routes (`python/harness/routers/finance_guardrails.py`, operator-gated):

| Route | Purpose |
|---|---|
| `GET /finance-guardrails/status` | config + aggregates + recent decisions |
| `GET /finance-guardrails/intents` | the ledger |
| `PUT /finance-guardrails/config` | caps, mode, counterparties, crisis/impaired/panic, trusted contact |
| `POST /finance-guardrails/evaluate` | dry-run a hypothetical intent (never recorded) |

Front door: `src/app/api/finance-guardrails/[[...path]]/route.ts` (allowlisted,
injects the runtime operator token). Client:
`src/lib/harness/finance-guardrails-client.ts`. UI: **Settings › Money
Guardrails** (`src/components/screens/money-guardrails-settings.tsx`).

The agent can call `finance_guardrail_status` and `finance_guardrail_check`.
Neither can change state. Crisis/impaired/panic are human switches only.

## Configuration defaults

| Setting | Default | Meaning |
|---|---|---|
| `mode` | `guard` | `off` disables the guardrails (panic still applies) |
| `perTxnCap` / `dailyCap` | `0` | `0` = no cap |
| `velocityPerHour` | `0` | `0` = no limit |
| `highValue` | `0` | `0` = off |
| `coolingSeconds` | `120` | floor for high/critical confirmations |
| `baselineMultiplier` | `3` | flag amounts above this multiple of p95 |
| `impairedMode` / `crisisMode` / `panicPaused` | `false` | human switches |
| `allowlist` / `blocklist` | `[]` | counterparty controls |

## Honest boundaries

- Signals are heuristics, not a fraud verdict. They add friction; they never
  accuse. A `deny` states exactly which rule fired.
- The classifier is deterministic. A sophisticated scam with no recognised
  markers is not detected by text alone; limits, novelty and the confirm gate are
  the backstop.
- Only money-moving shapes are classified. Ledger bookkeeping
  (`portfolio_*`, `journal_add_trade`) is not a money movement.
- `terminal_run`/`shell_run` are recognised only when the command names a
  broker/payment surface; opaque scripts remain gated by the shell/terminal
  approvals and the Security Floor.

## Tests

`python/tests/test_finance_guardrails.py` covers each rule, intent recognition,
the ledger aggregates, the cooling-off enforcement and single-use consumption.
