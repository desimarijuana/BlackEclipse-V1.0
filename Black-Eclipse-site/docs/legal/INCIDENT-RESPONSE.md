---
title: Incident Response Policy (draft)
status: Draft
last-verified: 2026-11-09
---

# Incident Response Policy — DRAFT

> **DRAFT — not legal advice.** Owner: Founder/security. The open item in the
> register is a **tabletop exercise**; this draft is the plan it will test.

## Severity

| Level | Example | First response |
|---|---|---|
| S1 | data breach, credential compromise, unauthorised live order | contain now; notify per law; page the owner |
| S2 | service outage, broker/model outage, security control failure | contain; restore; notify affected users if needed |
| S3 | degraded feature, stale data, a single failed run | triage; fix in the normal flow |
| S4 | cosmetic or single-user issue | ticket |

## Steps

1. **Detect.** Health watch, alerts, logs, a user report, or a security advisory.
2. **Contain.** Revoke sessions/keys, disarm trading, stop the affected worker,
   preserve state. Do not delete evidence.
3. **Assess.** What data, which users, which systems, what legal duty
   (GDPR 72-hour, contractual, broker, regulator).
4. **Notify.** The owner, affected users, the broker/provider, and the
   supervisory authority where required. Use the approved wording; do not
   speculate.
5. **Recover.** Restore from the tested backup, verify integrity, re-enable
   with the smallest safe scope.
6. **Postmortem.** Timeline, cause, impact, the fix, the test that prevents a
   recurrence. Blameless; recorded.

## Evidence

Keep the audit log, the affected run ids, the backup taken before recovery, and
the timeline. A legal hold suspends deletion.

## Runnable controls

Each containment step has a command, not only prose:

| Step | Command | What it proves |
|---|---|---|
| Revoke one user | `node scripts/revoke-sessions.js --disable-user <name>` | the session rows are deleted and the user is disabled |
| Revoke every session | `node scripts/revoke-sessions.js` | all cookies stop resolving on the next request |
| List accounts/sessions | `node scripts/revoke-sessions.js --list` | who exists, who is disabled, how many live sessions |
| Rotate the signing key | change `HARNESS_AUTH_SECRET`, restart | every token not in the DB also stops verifying |
| Check a leaked instance is still up | `bash scripts/health-watch.sh` | the alert path fires |
| Disarm trading | the product's kill switch / operator disarm | no new live order is accepted |

`revoke-sessions.js` takes `--db`, then `HARNESS_AUTH_DB`, then
`.black-eclipse/auth.db`. Deleting a row takes effect on the next request; the
app does not need a restart for it.

## Disclosure

A security vulnerability is reported per `SECURITY.md`; a personal-data breach
follows `PRIVACY-NOTICE.md` and the DPA. Public statements are factual and
approved by the owner.

## Drill record

**2026-11-09 — S1 "leaked session" tabletop + live containment drill.** Ran
against an isolated production-posture instance (`HARNESS_AUTH=required`, a
generated ≥32-char `HARNESS_AUTH_SECRET`, a temporary `HARNESS_AUTH_DB` and
`BE_DATA_DIR`, port 3101), so the running soak instance was not touched.

| Step | Result |
|---|---|
| Unauthenticated `GET /api/alerts` | **401** |
| First-run setup + login | **200**, session cookie issued |
| `GET /api/auth/me` with the session | `authenticated: true`, user named |
| `node scripts/revoke-sessions.js --disable-user irdrill` | 1 session revoked, user disabled |
| Same cookie, `GET /api/auth/me` | `authenticated: false` |
| Same cookie, `GET /api/alerts` | **401** |
| Login again as the disabled user | **401** |
| No cookie, `GET /api/alerts` | **401** |

Gaps found and handled:

- The plan said "revoke sessions" but had no command. Added
  `scripts/revoke-sessions.js` (`--list`, `--user`, `--disable-user`, `--db`).
- A health failure with no webhook reached nobody. The Windows wrapper now shows
  a desktop notification, keeps an `ALERT-ACTIVE.txt` marker and exits non-zero;
  that is local evidence, not a pager, so `ALERT_WEBHOOK_URL` is still the
  off-machine gate.
- `eventcreate` cannot write a new source without elevation, so it was dropped
  in favour of the desktop notification.
- A protected route in a brand-new data dir returns 500 (no market DB); the
  auth gate still answers 401 before the handler runs, which is why the drill
  reads `/api/auth/me` for identity.

Not exercised: trading disarm (no live broker in the drill), the 72-hour
regulator notification (no real entity), and a restored backup after an actual
breach (the restore drill already passes separately).
