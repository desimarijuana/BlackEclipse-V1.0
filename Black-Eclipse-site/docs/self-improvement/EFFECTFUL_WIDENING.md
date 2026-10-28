# Operator-Approved Effectful Widening

This is the separate lane for tools that are **not** read-only. The read-only
queue (`WIDENING_QUEUE.md`) deliberately refuses effectful/financial tools; this
lane accepts them only through an explicit two-step approval flow.

## The two decisions

1. **Propose** — an operator names the exact tool, writes a justification, sets
   a short TTL (1–24h) and hard caps. The response contains a one-time approval
   token; only its SHA-256 hash is stored.
2. **Approve** — a separate call presents the token. It creates a
   `widen_effect_tool` grant with the same TTL and caps.

There is no autonomous route that creates or approves one of these grants. The
self-modification loop never calls `propose` or `approve`.

## Caps

- `maxCallsPerDay` (1–100) and `maxCallsTotal` (1–500) are always required.
- Optional `maxNotionalPerCall` / `maxNotionalPerDay`, read from one top-level
  argument named by `notionalField` (default `notional`).
- Calls are counted before the handler runs, so a failed effect still consumes
  its slot.

The call cap is authoritative for every granted tool. The notional cap is a
best-effort bound on one named argument; it is not a substitute for the
per-call effect approval.

## Runtime behavior

- A grant only makes the tool visible to `eclipse-agent`'s surface.
- Every invocation still goes through the existing effect authorizer and the
  Security Gateway. A grant does **not** pre-authorize the effect.
- `tools.py` calls `check_call` after authorization and before the handler; an
  over-cap call returns `WIDENING_CAP_EXCEEDED`.
- Grants expire on schedule, are excluded from the overlay immediately, and are
  revoked durably by the self-modification tick. Revocation is immediate.

## Surfaces

- `POST /evolution/effectful-widening/propose`
- `POST /evolution/effectful-widening/{id}/approve`
- `GET /evolution/effectful-widening`
- `GET /evolution/effectful-widening/grants`
- `POST /evolution/effectful-widening/grants/{id}/revoke`

All are operator-gated.

## Tests

`test_effectful_widening.py`: rejects missing justification and read-only tools,
requires the token, activates the grant, exposes it on the surface, enforces
per-call and total caps, and removes it on revocation.

## Boundary

This does not make effectful autonomy autonomous. The operator chooses the exact
tool, the window and the caps; the runtime can stop the calls but cannot widen
itself. Financial tools remain additionally subject to the existing finance
guardrails and per-call approvals.
