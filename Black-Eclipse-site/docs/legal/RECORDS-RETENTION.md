---
title: Records Retention Policy (draft)
status: Draft
last-verified: 2026-11-09
---

# Records Retention Policy — DRAFT

> **DRAFT — not legal advice.** Counsel must set the periods for
> `[JURISDICTION]`. A legal hold overrides every deletion below.

| Data class | Where | Retention | Why |
|---|---|---|---|
| Account + auth | auth DB | life of the account + `[N]` days | service, security |
| Chat, memory, journal, theses, portfolio | `agent-memory.db`, `eclipse-memory.db`, `jdds.db` | until the user deletes; user-controlled | the product's purpose |
| Broker connections + encrypted credentials | `agent-memory.db` | until disconnected + `[N]` days | the connection |
| Run events + security audit | `agent-memory.db` | `[N]` days / `[N]` months | evidence, incident response |
| Usage, cost, model requests | `agent-memory.db` | `[N]` months | budget, billing |
| Backups | `backups/` or the operator's volume | `[KEEP]` archives (default 14) | recovery |
| Legal acceptance | SystemConfig | life of the account + `[N]` years | consent evidence |
| Complaints + incidents | `[STORE]` | `[N]` years | dispute, regulator |
| Billing/tax | `[STORE]` | `[N]` years | tax law |

## Deletion

The user can delete data in the product; the operator can run the documented
wipe (`npm run data:wipe`). Deletion removes the live rows; a backup expires on
its retention schedule. A legal hold suspends deletion for the named matter.

## Review

Review annually and after a material legal or product change. The date and the
reviewer are recorded in `docs/legal/README.md`.
