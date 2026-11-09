---
title: AI & Financial Disclosures
status: Current
last-verified: 2026-11-09
---

# AI & Financial Disclosures

This is the canonical, versioned text the product shows at the point of use.
The source of truth in code is `src/lib/legal/disclosure.ts`; this document
explains **where** each form appears and **why**, so a copy change and a
placement change cannot drift apart.

> Not legal advice. The enforceable limitation of liability belongs in the
> Terms of Service reviewed by counsel. These notices are evidence of a named
> risk shown conspicuously at the point of use — they are not immunity.

## Version

- Current: **2026-11-09**
- A recorded acceptance counts only for the exact version it names. Bump
  `RISK_DISCLOSURE_VERSION` whenever the substance changes; the first-run
  wizard then asks again.

## The three forms

| Form | Where | Behavior |
|---|---|---|
| Label + short sentence | Under every settled assistant answer (`chat-history.tsx`) and in Canvas reports (`response-view.tsx`, opt-in `showNotice`) | Always visible; expands to the full notice. Not dismissible. |
| Composer one-liner | Inside the shared composer (`chat-input.tsx`) and the floating Assistant dock (`chat-dock.tsx`) | Always visible; expands to the full notice. |
| Full notice + checkbox | New install: first-run wizard, first step (`welcome-step.tsx`). Existing install: one-time `risk-ack-gate.tsx` modal mounted in the root layout. | Required before Continue/Skip (wizard) or before the app is usable (gate); acceptance is recorded. |
| Order ownership | Trade approval card (`trade-approval-banner.tsx`) | Required checkbox before Confirm & send: the order is the user's decision, verified with the broker. The existing typed live phrase is still required. |

The full text also appears in the chat surfaces via the expandable `<details>`
element, so the user never has to leave the answer to read the specifics.

## Recorded acceptance

`POST /api/setup` requires `riskAck.version` to equal the current version. The
standalone `POST /api/legal/risk-ack` records the same acceptance for an install
that never ran the new wizard (an upgrade). On success both write `risk_ack_v1`
in SystemConfig:

```json
{ "version": "2026-11-09", "acceptedAt": "2026-11-09T…Z", "mode": "personal" }
```

`GET /api/setup` (and `GET /api/legal/risk-ack`) returns the status, so the
wizard and the in-app gate re-ask after a version bump. Resetting setup deletes
the record. An install migrated before this feature keeps its onboarding state;
the gate presents the current notice once instead of forcing a full re-setup.

## Why these words

- **Specific, not "use at your own risk".** Vague boilerplate is weak evidence.
- **Placed at the point of use.** A notice only at signup, contradicted by the
  product, is not credible (see `LEGAL-COMPLIANCE-BLUEPRINT.md` §3.1–3.2).
- **Matches the product's behaviour.** The product already labels output
  `COMPUTED` / `SOURCED` / `UNVERIFIED`, shows data freshness, and keeps trades
  proposal-only. The notice says the same things.
- **Names the user's role.** The account owner authorises each order and owns
  the decision; the broker is the source of truth for execution.

## What this does not do

- It does not prevent a lawsuit or waive non-waivable rights.
- It does not replace Terms, a Risk Disclosure, an AI Usage Disclosure, or the
  live-trading acknowledgement tracked in `README.md`.
- It does not excuse a contradiction elsewhere in the product (marketing claims,
  guaranteed-return language, a feature that acts without the user).
