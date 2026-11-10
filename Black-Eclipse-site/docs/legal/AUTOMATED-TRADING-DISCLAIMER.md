---
title: Automated Trading Disclaimer (draft)
status: Draft
last-verified: 2026-11-09
---

# Automated Trading Disclaimer — DRAFT

> **DRAFT — not legal advice; counsel review required.** This is the separate
> acknowledgement to show before the first live arm, in addition to the Risk
> Disclosure and the Terms.

## The model

Order entry is **proposal-only by default**. A live order requires all of:

- an **armed** live connection, time-boxed and operator-controlled;
- a **bounded mandate** (symbols, margin, order count, maximum TTL) that the
  agent cannot create;
- a **typed confirmation** naming the order;
- the broker's own controls (Algo Trading, magic, margin, permissions).

**Unattended live trading is refused.** A mandate is demo-only unless a
workflow-version-pinned live mandate is explicitly created by the operator.
Paper execution is a simulation.

## Risks the user accepts

- Execution, price, liquidity, slippage, and rejection are the broker's domain
  and are not guaranteed.
- A bug, a model error, a stale feed, a network or broker outage, or a host
  failure can prevent, duplicate, or delay an order or a cancellation.
- A stop, limit, or kill switch reduces risk; it does not remove it.
- The user is the decision maker and remains responsible for every order and
  for their local law.

## User acknowledgement

By arming a live connection, the user confirms they understand the above, that
the account is theirs and permitted to trade, that they have set their own risk
limits, and that they will verify orders with the broker. The acceptance is
recorded with a version and timestamp.

`[ENTITY]`, `[CONTACT]`.
