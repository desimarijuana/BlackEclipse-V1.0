---
title: Self-Editing Harness — program plan and status
status: Current
last-verified: 2026-10-14
---

# Self-Editing Harness — program plan and status

**What this is.** The program that lets Eclipse **edit its own code** the way a
person does: read the repo, make a change in a review copy, run the checks, review
the change, and land it — with the safety floor the repo already uses
(single-use, digest-bound operator approvals, a frozen authority set, one
runtime). It is a *wiring and safety* program: most machinery already existed; the
work was reachability, the advertised-but-dead defect class, the extension layer,
and the landing/rollback/self-hosting discipline.

**Method.** Grounded in `docs/harness/construction-first-audit.md` (round 3) and
the roadmap (`docs/harness/roadmap/`). Every claim below is a merged change with
tests; nothing is "planned" unless it says so.

## Status

| # | Track | State | Evidence |
|---|---|---|---|
| A1 | Portfolio write authorizer (the reported bug) | ✅ | `portfolio/authorizers.py`, `test_portfolio_authorizer.py` |
| 1.2 | Advertised-but-dead: **general guard** (all agent allowlists) | ✅ | `test_advertised_tool_admission_all.py` |
| 1.2 | Fixes the guard surfaced | ✅ | `code_rename_symbol` routing (`code/authorizers.py`), `image_generate` (`vision/authorizers.py`), `learning_progress_update` (local-write admission) |
| 1.1 | Classifier reachability | ✅ (measured) | `test_code_request_intent.py` |
| E | `/eclipsesdk` chat command | ✅ | `src/lib/harness/commands.ts` (+ palette in `chat-input.tsx`), `run-service.ts`, `schemas.py` |
| 4 | Extension layer (agent-authored skills) | ✅ | `skills/manage_tools.py`, `test_skill_manage_tools.py` |
| 3.3 | Promotion rollback | ✅ | `code/promotion.py`, `test_code_promotion_rollback.py` |
| B1/B4 | Self-hosting gate (classify + guard + authority refusal) | ✅ | `code/selfhost.py`, `test_selfhost_landing.py` |
| 6 | Terminal hardline floor | ✅ (verified) | `code/terminal.py`, `test_terminal_floor.py` |
| 3 | i18n + plain-language for new copy | ✅ | `dictionaries/en.ts` (`code.command.*`, `code.promote.*`), `plain-language.test.ts` |
| 2 | Rollback + restart/build verdict in the chat UI | ✅ | `src/components/chat/promote-change.tsx`, `src/app/api/code/promotions/[rollbackId]/rollback/route.ts` |
| 7 | Self-edit E2E acceptance (real `ApprovalStore`) | ✅ | `python/tests/test_self_edit_e2e.py` |
| B2 | Real restart seam (front door owns it) | ✅ | `python-runtime.ts::restartPythonRuntime`, `POST /api/harness/runtime/restart`, "Restart Eclipse now" in `promote-change.tsx`; the front door also auto-restarts on a stale runtime (`ensurePythonRuntimeUncached` detects harness source newer than the running process). **Durability:** a restart is DEFERRED while runs are in flight (`activeRuns` in `/health`), and a runtime that answered recently is treated as busy, not hung — so a self-edit paused on an approval is never orphaned mid-flight (`runtime-supervision.ts`). If a restart still catches a paused run, boot reports it honestly as `RUN_INTERRUPTED` (nothing applied), not a generic orphan (`run_recovery.py`). |

## Deliberately NOT done (and why)

| Item | Why |
|---|---|
| **Infra/cloud mutations admitted** (`k8s_*`, `helm_*`, `terraform_*`, `deploy_*`) | No admission branch/approval kind yet; kept refused ON PURPOSE and pinned in `test_advertised_tool_admission_all.py` (audit §6, R3-07). |
| **Construction scenarios in `construction_v1.json`** | The focused E2E (`test_self_edit_e2e.py`) covers the self-edit acceptance; the full scripted-trace scenarios in the eval dataset are not authored yet. |
| **Project-local extension discovery (4.4)** | `skills/project_skills.py` already implements it. |
| **"Create a page" Next.js kit (Track 2)** | Kits exist (`code/kits/`); a dedicated page/widget shape is not verified. |

## How a self-edit works today

1. The user types `/eclipsesdk <instruction>` (or the classifier detects a coding
   request). The front door (`run-service.ts`) strips the command and sends
   `autonomy: "edit_verify"` + `command`; the runtime binds the chat code profile.
2. The agent edits a **disposable worktree** (`code/worktree.py`); writes are gated
   by `code/authorizers.py` (portfolio/vision/skill/… layers).
3. A review card previews the exact file set; one **single-use approval** puts it
   into the real checkout (`code/promotion.py` → `apply_promotion`), which captures
   the originals for **rollback**.
4. If the change touches Eclipse's own live code, `code/selfhost.py` classifies it:
   a runtime change needs a restart + health check (auto-rollback on failure), a
   front-end change needs a build gate, and an **authority** change is refused.

## Related

- `docs/harness/construction-first-audit.md` — round 3 ground truth.
- `docs/harness/architecture.md` — the authorizer chain, the extension layer, the
  self-hosting gate.
- `docs/portfolio-accounting.md`, `docs/harness/roadmap/phase-15-attachments-and-artifacts.md`.
