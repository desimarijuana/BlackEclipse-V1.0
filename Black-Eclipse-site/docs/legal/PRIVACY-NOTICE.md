---
title: Privacy Notice (draft)
status: Draft
last-verified: 2026-11-09
---

# Privacy Notice — DRAFT

> **DRAFT — not legal advice.** Counsel must review and align this with the data
> map in `docs/data-and-privacy.md`, the chosen hosting model, and
> `[JURISDICTION]`. Placeholders: `[ENTITY]`, `[CONTACT]`, `[DPO]`,
> `[RETENTION]`, `[SUBPROCESSORS]`.

## 1. Who is responsible

- **Self-hosted (default):** the operator who runs the instance is the
  controller. Data stays in that operator's `jdds.db`, `agent-memory.db`,
  `eclipse-memory.db`, and `.black-eclipse/` on their host. `[ENTITY]` does not
  receive it.
- **Hosted (`[ENTITY]` operates the service):** `[ENTITY]` is the controller for
  account and usage data, and a processor for data the customer submits where a
  **Data Processing Agreement** applies.

## 2. What we process

| Category | Examples | Purpose |
|---|---|---|
| Account | username, password hash, session cookie | authenticate, secure the account |
| Product data | portfolios, watchlists, journal, theses, chat history, settings | provide the features the user asks for |
| Model and tool data | prompts, retrieved sources, tool results, usage/cost | run the agent, show provenance, budget |
| Connected services | broker connection metadata, encrypted credentials | read the account the user connects |
| Technical | logs, IP, user agent, errors, health | operate, secure, debug |
| Legal acceptance | risk/AI notice version + timestamp | evidence of consent |

Credentials for brokers and providers are stored **encrypted** (AES-256-GCM)
where the product supports it; the key is on the same host, so this protects a
copied database, not a compromised machine.

## 3. Why we process it (legal bases)

Contract (provide the service), legitimate interests (secure and improve it),
consent (optional model providers, marketing, non-essential cookies), and legal
obligation (records, tax, abuse). Where consent is the basis, it can be withdrawn.

## 4. Sharing

We do not sell personal data. We share it with the **subprocessors** listed in
`SUBPROCESSORS.md`, the broker the user connects, and a model provider the user
selects. A hosted deployment may transfer data internationally under
`[TRANSFER MECHANISM]`. The user's provider choices control which model endpoint
receives a prompt; `ECLIPSE_PRIVACY=local-models` refuses remote endpoints.

## 5. Retention

`[RETENTION]` per category, or until the user deletes it. Legal hold and
security logs may be kept longer where required. The operator can run the
documented personal-data wipe (`npm run data:wipe`).

## 6. Security

Encryption in transit where configured, hashed passwords, signed sessions,
encrypted credentials at rest, least-privilege container defaults, and an
audit log. No system is perfectly secure; report a vulnerability per
`SECURITY.md`.

## 7. Rights

Access, correction, deletion, restriction, portability, objection, and
withdrawal of consent, subject to law. `[CONTACT]` / `[DPO]`. A complaint can go
to the supervisory authority in `[JURISDICTION]`.

## 8. Children

The service is not for children under `[AGE]`.

## 9. Changes

Material changes are notified in the product; the version and acceptance are
recorded.

## 10. Contact

`[ENTITY]`, `[ADDRESS]`, `[CONTACT]`. Effective `[EFFECTIVE DATE]`.
