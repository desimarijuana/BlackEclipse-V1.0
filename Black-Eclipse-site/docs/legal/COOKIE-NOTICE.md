---
title: Cookie & Tracking Notice (draft)
status: Draft
last-verified: 2026-11-09
---

# Cookie & Tracking Notice — DRAFT

> **DRAFT — only needed for a hosted deployment that uses non-essential
> tracking.** Counsel review required. A self-hosted install uses only the
> storage described in `docs/data-and-privacy.md`.

## Essential

| Name | Purpose | Type | Lifetime |
|---|---|---|---|
| `eclipse_session` | signed session cookie (auth) | HTTP-only, SameSite | `[TTL]` |
| `be_locale_v1` | interface language | localStorage | until cleared |
| `be_theme_v1` | theme cache | localStorage | until cleared |
| `be_sidebar_v1` | sidebar layout | localStorage | until cleared |

## Optional

`[ANALYTICS / MARKETING / SUPPORT WIDGETS]` — only with consent, listed here with
provider, purpose, and lifetime. No optional tracker is set before consent.

## Control

A consent banner `[YES/NO]`, a preferences centre `[YES/NO]`, and a delete
action. Withdrawing consent stops future collection; it does not delete data
already lawfully collected (use the privacy request channel).
