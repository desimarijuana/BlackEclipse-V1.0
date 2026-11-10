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

## Disclosure

A security vulnerability is reported per `SECURITY.md`; a personal-data breach
follows `PRIVACY-NOTICE.md` and the DPA. Public statements are factual and
approved by the owner.

## Test

Before hosted launch: one tabletop (S1 credential leak) and one restore drill.
Record the date and the gaps found.
