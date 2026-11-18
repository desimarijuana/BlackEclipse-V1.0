---
title: Monetization
status: Live
last-verified: 2026-11-17
---

# Monetization

How BlackEclipse makes money **without** charging for the licence.

## The position

> **Code is MIT. The paid surface is the product.**

The repository is the distribution channel, not the product. Every licensing
decision follows from one rule: **never trade reach for a licence fee.** A
restrictive licence kills adoption, and adoption is the entire marketing engine —
the project has no ad budget, no sales team, and a single maintainer.

The one exception is forced, not chosen: `Black-Eclipse-site/pine-engine/` is
AGPL-3.0-only because it depends on `pinets`. Nothing there is for sale.

## What is sold

| Surface | Why people pay | Status |
|---|---|---|
| **Pro features** — multi-portfolio, team workspaces, audit trails, scheduled research | Convenience for people already using the free app | Not built |
| **Marketplace listings** — paid strategies, widgets, agent templates | Distribution for third-party builders; the platform takes a cut | Not built |
| **Live data tier** — real-time quotes, premium fundamentals, verified-research depth | JDdS is the differentiator but live feeds cost money | Not built |
| **Support and setup** for teams | Someone to call | Not built |
| **Commercial licence** — only if a company cannot accept MIT | Rare; do not design around it | Available on request |

Each one is *additive*: the free app stays complete for a single operator. There
is no crippled core, no nag screen, no time bomb.

## What is never sold

- **Access to the licence.** Noncommercial licensing is rejected — see below.
- **The user's data.** No brokering, no training on private portfolios.
- **Fake certainty.** Premium tiers may serve better data; they never fake a
  number, and unavailable data stays `UNAVAILABLE`.

## Rejected options, and why

| Option | Why it was rejected |
|---|---|
| **Noncommercial (PolyForm NC)** | Not OSI-approved. Corporate OSS policy rejects it, so it removes exactly the audience that makes the project visible. The project would get no free users and no paying ones |
| **BUSL / "fair-code"** | Blocks *competitors*, not *commercial use*. A fund using it to trade is not a competitor, so the protection is imaginary while the community cost is real |
| **AGPL the whole app** | Forces source disclosure but does not prevent anyone from **selling** it. Wrong lever — it hurts adoption without creating revenue |
| **Feature-gating the desktop app** | The app is desktop-first and offline; a phone-home paywall is both crackable and hostile to the trust the product needs |

The full reasoning behind the licence/DCO/CLA choices lives in
[`legal/LEGAL-COMPLIANCE-BLUEPRINT.md`](./legal/LEGAL-COMPLIANCE-BLUEPRINT.md)
(§1.4 contributor agreements, §6 licensing).

## Guardrails

1. **No licence change without a decision record.** MIT stays. The only planned
   exception path is a commercial edition under a separate licence, which the
   [`CLA`](../../CLA.md) keeps possible.
2. **No new Blocker-class dependency that forces copyleft into the core.** Keep
   AGPL-shaped dependencies inside `pine-engine/` or another isolated program.
3. **Monetized code lives behind a service boundary** — sync, cloud, teams, live
   feeds — so a paid surface can exist without relicensing the app.
4. **Every paid surface must be labelled in the UI.** Simulated or stale data is
   never sold as live.
5. **The name is the moat.** Trademark is what stops a fork taking the users;
   see [`/TRADEMARK.md`](../../TRADEMARK.md).

## The honest risks

- **Free users may never convert.** Mitigation: sell to teams and builders, not
  hobbyists; keep the paid surface genuinely additive.
- **A fork can out-execute the project.** MIT permits it. The defence is the
  brand, the data, and shipping speed — not the licence.
- **A single maintainer cannot run a marketplace.** Sequence it last; pro
  features and live data come first.

## Related

- [`/CLA.md`](../../CLA.md) — why contributions grant relicensing rights
- [`/TRADEMARK.md`](../../TRADEMARK.md) — what the licence does not give away
- [`legal/TRADEMARK-POLICY.md`](./legal/TRADEMARK-POLICY.md) — the long-form policy
- [`OPEN-SOURCE-READINESS.md`](./OPEN-SOURCE-READINESS.md) — the public-release gate
