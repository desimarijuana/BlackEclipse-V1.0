---
title: Legal & Compliance
status: Draft
last-verified: 2026-11-07
---

# Legal & Compliance

This folder holds the project's legal, compliance, and risk-management artifacts.
It is **not legal advice**. It is the working record of the position the project
intends to take, the controls it relies on, and the documents it still needs.

## Start here

- [**LEGAL-COMPLIANCE-BLUEPRINT.md**](./LEGAL-COMPLIANCE-BLUEPRINT.md) - the full
  framework: entity, regulation, AI risk, trading risk, privacy, licensing,
  product controls, documents, incidents, roadmap, and jurisdiction uncertainty.
- [**disclosures.md**](./disclosures.md) - the canonical, versioned AI/financial
  notice text and exactly where each form appears in the product.
- **The contract pack (all Draft):** [Terms](./TERMS-OF-SERVICE.md),
  [Privacy](./PRIVACY-NOTICE.md), [Risk](./RISK-DISCLOSURE.md),
  [AI Usage](./AI-USAGE-DISCLOSURE.md), [Acceptable Use](./ACCEPTABLE-USE.md),
  [Automated Trading](./AUTOMATED-TRADING-DISCLAIMER.md), [DPA](./DPA.md),
  [Subprocessors](./SUBPROCESSORS.md), [Cookies](./COOKIE-NOTICE.md),
  [Trademark](./TRADEMARK-POLICY.md), [Incident Response](./INCIDENT-RESPONSE.md),
  [Complaints](./COMPLAINTS.md), [Records](./RECORDS-RETENTION.md),
  [Regulatory Status](./REGULATORY-STATUS.md).

## The position in one paragraph

BlackEclipse is self-directed research and order-entry software. It is not a
broker, investment adviser, portfolio manager, or fiduciary. It does not manage
accounts, exercise discretion, hold client assets, pool funds, guarantee results,
or share profits/losses. The user owns the broker account, authorises each order,
sets their own risk limits, and is responsible for their decisions and local law.
The broker is the source of truth for execution. AI output and market data can be
wrong, incomplete, or delayed.

The product must keep matching that paragraph. A disclaimer that the product
contradicts is weaker than no disclaimer at all.

## Document register

Legend: **Live** = exists and is used; **Draft** = written, not yet reviewed;
**Needed** = must exist before hosted/live use.

> **All `Draft` documents are templates written from the blueprint, not legal
> advice. Counsel review is the remaining gate.** A hosted launch must not treat
> a Draft as Live, and no Draft is enforceable until the entity, jurisdiction,
> and contact placeholders are completed.

| Document | Status | Owner | Notes |
|---|---|---|---|
| `LICENSE` (MIT) | Live | Project | Repository root |
| `SECURITY.md` | Live | Maintainers | Safe-harbour wording added |
| `CONTRIBUTING.md` | Live | Maintainers | DCO sign-off required |
| [`DCO`](../../DCO) | Live | Maintainers | DCO 1.1; `git commit -s` |
| [Terms of Service](./TERMS-OF-SERVICE.md) | Draft | Founder + counsel | Template; localise entity/law/liability cap |
| [Privacy Notice](./PRIVACY-NOTICE.md) | Draft | Founder + counsel | Align to the data map and hosting model |
| [Risk Disclosure](./RISK-DISCLOSURE.md) | Draft | Founder + counsel | Full notice behind the in-product text |
| Financial Disclaimer | Draft | Founder + counsel | In-product copy shipped (`disclosures.md`, v2026-11-09); Terms + counsel review still needed |
| [AI Usage Disclosure](./AI-USAGE-DISCLOSURE.md) | Draft | Founder | Point-of-use notice + first-run acceptance shipped; hosted Terms still needed |
| [Acceptable Use Policy](./ACCEPTABLE-USE.md) | Draft | Founder + counsel | Abuse, market manipulation, third-party accounts |
| [Automated Trading Disclaimer](./AUTOMATED-TRADING-DISCLAIMER.md) | Draft | Founder + counsel | Required before the first live arm |
| [Data Processing Agreement](./DPA.md) | Draft | Counsel | Roles, subprocessors, transfers, audit |
| [Trademark & Brand Policy](./TRADEMARK-POLICY.md) | Draft | Founder | Protect the name while keeping code open |
| [Cookie / Tracking Notice](./COOKIE-NOTICE.md) | Draft | Founder | Only if a hosted deployment uses tracking |
| [Subprocessor List](./SUBPROCESSORS.md) | Draft | Founder | Complete before a hosted launch; keep current |
| [Incident Response Policy](./INCIDENT-RESPONSE.md) | Draft | Founder/security | Tabletop exercise still open |
| [Complaints & Dispute Policy](./COMPLAINTS.md) | Draft | Founder | Real channel + response targets required |
| [Records Retention Policy](./RECORDS-RETENTION.md) | Draft | Founder | Per data class, legal hold |
| [Regulatory Status Statement](./REGULATORY-STATUS.md) | Draft | Founder + counsel | "What we are / are not"; per market |
| Sanctions & Export Policy | Later | Counsel | Before scaling to restricted markets |
| Code of Conduct | Recommended | Maintainers | Contributor Covenant |

## What to ship first

1. Incorporate and assign IP to the company.
2. Add clickwrap acceptance and version logging for Terms, Privacy, and Risk.
3. Add a separate live-trading acknowledgment before the first arm.
4. Add jurisdiction and account-ownership attestations.
5. Publish the core notice in the README and in-app.
6. Adopt a DCO and a trademark policy.
7. Create an incident/complaints inbox and a simple evidence-retention rule.

## What not to claim

- Do not say the platform is "guaranteed", "risk-free", "accurate", or a
  substitute for a licensed adviser.
- Do not treat the MIT licence as a user contract or as immunity from liability.
- Do not rely on a disclaimer that the product's behaviour contradicts.
- Do not add discretionary management, copy-trading, pooled funds, custody, or
  performance fees without licensed advice.

## Related

- [`../fiduciary-advice.md`](../fiduciary-advice.md) - the Advisory Gate.
- [`../trading.md`](../trading.md) - execution controls and audit.
- [`../data-and-privacy.md`](../data-and-privacy.md) - data map and privacy.
- [`../harness/security.md`](../harness/security.md) - security architecture.
- [`../../../SECURITY.md`](../../../SECURITY.md) - disclosure policy.
- [`../../../CONTRIBUTING.md`](../../CONTRIBUTING.md) - contribution process.
