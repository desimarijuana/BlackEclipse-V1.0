---
title: Risk Disclosure (draft)
status: Draft
last-verified: 2026-11-09
---

# Risk Disclosure — DRAFT

> **DRAFT — not legal advice.** Counsel must review and localise. This is the
> full notice behind the in-product text; the canonical point-of-use wording
> lives in `disclosures.md` and `src/lib/legal/disclosure.ts`.

## Trading and markets

Trading involves a **risk of loss** that can exceed the amount invested when
leverage or derivatives are used. Prices can move quickly, liquidity can
disappear, and a stop or limit order is not a guarantee of execution. Past
performance does not predict future results. The user is responsible for
understanding the instrument, the venue, the margin rules, and their own
suitability.

## Software, data, and models

BlackEclipse is software, not a broker or adviser. Market data can be delayed,
incomplete, stale, or wrong; a provider can change or withdraw a feed. AI output
can be **hallucinated**, can misread a document, or can apply the wrong period,
currency, or definition. The product labels output `COMPUTED`, `SOURCED`, or
`UNVERIFIED` and shows freshness, but no label makes a number true. **Verify
material facts and every order with the broker or the official source.**

## Automation and outages

A network, provider, model, broker, or host outage can prevent a signal, an
order, a cancellation, or a reconciliation. A bug can produce an unintended
order. The product's guards (arming, per-order approval, typed phrase, risk
limits, kill switch, bounded mandates, reconciliation) reduce but do not remove
this risk. **Do not rely on the software as the only control over a live
account.**

## No guarantee

`[ENTITY]` does not guarantee profit, accuracy, availability, execution, or
that the software is free of defects. The user owns the decision and the
account. Nothing here waives a right that cannot be waived by law.
