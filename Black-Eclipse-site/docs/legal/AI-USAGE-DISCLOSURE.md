---
title: AI Usage Disclosure (draft)
status: Draft
last-verified: 2026-11-09
---

# AI Usage Disclosure — DRAFT

> **DRAFT — not legal advice.** This expands the in-product AI notice; the
> canonical point-of-use text is `disclosures.md`. Counsel must review the
> hosted version and the EU AI Act transparency statement.

## What the AI does

BlackEclipse uses large language models and other machine-learning models to
research, summarise, draft, calculate, and propose actions through tools. It is
a **probabilistic system**: the same input can produce a different answer. It
can be wrong, incomplete, outdated, or confidently incorrect.

## What it does not do

- It is not a fiduciary, adviser, broker, or guarantor.
- It does not place a live order by itself: order entry is proposal-only and
  requires the operator's arming, a bounded mandate, the typed confirmation,
  and the broker's own controls.
- It does not make a fabricated fact true by labelling it. `COMPUTED`,
  `SOURCED`, and `UNVERIFIED` describe provenance; they are not a guarantee.

## Data sent to models

A prompt, retrieved text, attachments, and tool results can be sent to the model
provider the user selects. `ECLIPSE_PRIVACY=local-models` refuses remote model
endpoints; a local Ollama/LM Studio keeps the data on the host. The model
provider's terms and retention apply to what it receives.

## Human oversight

The product keeps the user in the loop: approvals, a visible plan, provenance,
and a kill switch. The user must verify material numbers and each order. A
recorded risk/AI acceptance is evidence the notice was shown, not a transfer of
responsibility.

## Transparency (EU AI Act / similar)

The assistant identifies itself as an AI system at the point of use. Output
that is generated is distinguishable from broker-confirmed facts. Where the law
requires a specific disclosure, `[ENTITY]` must add it before operating in that
market.

## Reporting a problem

A wrong answer, a fabricated source, or an unsafe action: `[CONTACT]` and the
in-product report action. Do not rely on the output while a report is open.
