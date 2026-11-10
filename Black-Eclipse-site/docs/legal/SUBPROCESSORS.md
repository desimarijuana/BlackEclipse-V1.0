---
title: Subprocessor List (draft)
status: Draft
last-verified: 2026-11-09
---

# Subprocessor List — DRAFT

> **DRAFT.** Keep current before a hosted launch. A self-hosted install has no
> subprocessors operated by `[ENTITY]`; the operator's own providers apply.

| Subprocessor | Purpose | Data | Location | Transfer mechanism |
|---|---|---|---|---|
| `[HOSTING PROVIDER]` | servers, storage, network | all hosted data | `[REGION]` | `[SCC / adequacy / other]` |
| `[MODEL PROVIDER(S)]` | model inference the customer selects | prompts, retrieved text, attachments | `[REGION]` | `[MECHANISM]` |
| `[EMAIL PROVIDER]` | transactional mail | email address, message metadata | `[REGION]` | `[MECHANISM]` |
| `[MONITORING PROVIDER]` | errors, logs, uptime | technical data | `[REGION]` | `[MECHANISM]` |
| `[PAYMENTS PROVIDER]` | billing, if paid | billing data | `[REGION]` | `[MECHANISM]` |

The customer's own broker, data vendors, and MCP servers are **not** `[ENTITY]`
subprocessors; the customer contracts with them directly.

**Change log.** Add a dated row whenever a subprocessor is added or replaced,
and notify hosted customers as the DPA requires.
