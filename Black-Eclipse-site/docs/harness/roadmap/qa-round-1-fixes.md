---
title: QA Round 1 — Self-Knowledge & Learning-Loop Fix Plan
status: In progress (Q1–Q5 implemented; live QA re-run pending)
last-verified: 2026-10-18
---

# QA Round 1 — Self-Knowledge & Learning-Loop Fix Plan

**Progress:** `docs/harness/roadmap/progress/qa-round-1-progress.md` (Q1 done;
Q1.1/Q1.2 QA follow-ups done; Q2–Q5 implemented; Q6 acceptance tests landed —
the live four-prompt re-run remains manual).

**Who this is for:** whoever implements the fixes for the first scripted QA run of
the self-evolution loop (chat → learning review → memory → browser), run
2026-10-18 and transcribed in-session.

**What happened.** Four prompts were run against the live chat: (1) an honest
failure test plus "open Memory → Reviews", (2) "run a learning review for the
last run", (3) "accept a review proposal that touches permissions/tools", (4)
"show my recent learning reviews in plain language". The *safety floor held* —
every claim and refusal below is evidence-backed (see §2). The failures are in
the agent's **self-knowledge** (it could not see its own screens or stores) and
in **QA reachability** (it could not reach the app it was asked to operate).

**This file is the plan.** Six phases (Q1–Q6), each with the measured root
cause, the exact work items, the acceptance gates and a paste-ready prompt.
Use the roadmap operating loop (`docs/harness/roadmap/README.md` §5): progress
log at `docs/harness/roadmap/progress/qa-round-1-progress.md`, verify every
gate independently, close docs per `AGENTS.md`.

**Ordering.** Q1 first (it is the direct fix for the most damaging claim).
Q2 and Q3 are independent and can run in parallel. Q4 unblocks every
browser-driven QA step. Q5 is small and independent. Q6 re-runs the script.

---

## 1. Findings ledger (all file:line verified in this tree)

| # | QA observation | Verdict | Measured root cause |
|---|---|---|---|
| F1 | "Memory → Reviews does not exist in this build" | **FALSE — agent error**, caused by a real tool gap | `ui_get_application_map` returns only saved dashboard `UiBlueprint` rows — `python/harness/ui/service.py:227-239` reads `self._store.list_blueprints(...)`. The runtime has **no screen/tab vocabulary at all** (catalog is widgets only, `ui/catalog.py:183-253`). The real surfaces live in `src/lib/app-tabs.ts`, `src/lib/sidebar/config.ts`, `src/lib/search/registry.ts` (subroutes incl. `memory.reviews`) — none synced to Python. |
| F2 | "32 pages, all named Main, same widgets" | TRUE — mechanism understood | `browser_launch` uses a non-persistent context (`browser/tools.py:71`) → empty localStorage → `use-dashboards.ts:158-164` seeds a fresh random-id "Main" dashboard → `dashboard-screen.tsx:103-114` mirror-publishes a new blueprint each session (idempotency key `dash-bp:<dashboardId>`, `dashboard-blueprint.ts:45-57`). Noise, not corruption — but it pollutes the agent's map. |
| F3 | "Only buttons create a review; zero reviews exist" | **FALSE — agent error**, caused by a tool gap | The auto review queue persists rows on every completed/failed run after idle (`service.py:1163-1167,1411-1426,1453-1458`; `learning_review.py:54,521-531,559-600`). **No agent tool reads `LearningReview` or `LearningCandidate`** — the allowlist has only memory/skill/session reads (`agents.py:340-510`). The agent guessed; a button is not required. |
| F4 | Banner "Review in Learning Queue" → raw JSON | TRUE — copy bug | `graph_context.py:446` sets `learnQueuePath: "/api/learning/candidates"`; TS default mirrors it (`src/lib/chat/memory-action.ts:154`). It should be an app deep link (`/?tab=skills&sub=skills.learning`, format per `src/lib/search/deep-link.ts`). |
| F5 | "memory list (5) and memory search (4) returned different, non-overlapping subsets; no totals" | TRUE — by construction, unnecessarily confusing | `memory list` = user scope, active only, recency, limit 20 (`memory_tools.py:179-192` → `store.py:94-128`); native search = user+general, lexical relevance gate, different status filters (`memory_tools.py:442-457` → `retrieval.py:284-405`). Neither reports a total (`count` = page size). `memory_lifecycle_counts()` exists (`store.py:130-162`) but no agent tool calls it; `memory_provider_status` text omits `health.detail` (`memory_tools.py:500-507`). |
| F6 | In-app browser stuck at "Loading 95%", six `/api/*` failed | TRUE but **by design** — misread | The six are the boot warm-up set (`global-loader.tsx:11-18`) aborted after `maxDelay` 2500 ms (`:32,51-66`); cold dev compiles exceed it. "95%" is `TopLoader`'s deliberate cap (`top-loader.tsx:41-49`). Not a broken app; the agent had no boot-state vocabulary. |
| F7 | `127.0.0.1:3000` → `BROWSER_NAVIGATION_FAILED`, "loopback is a policy boundary" | Cause misdiagnosed; error hidden | Policy does **not** block loopback (`browser/policy.py:53-66`, `router.py:114-171`). The failure is a Playwright transport throw — most likely the canonical-host redirect (`src/middleware.ts:58-75`) to `blackeclipse` with the proxy/hosts path failing in that context. `session.py:435-439` hides the real error in `metadata.error`. |
| F8 | `shell_run curl localhost:3000/api/learning-review/run` forbidden; no way to read the app's own API | TRUE — sanctioned-path gap | `curl` is on the hard DENY list (`code/terminal.py:72-80`); `health_check` returns status only (`execution/application/tools.py:639-659`); web fetch blocks loopback (`src/lib/web-research.ts:140-150`). The only sanctioned paths are the UI itself or operator routes. |
| F9 | Runs hit the step limit mid-navigation | TRUE | Chat agent is capped at 8 model steps (`agents.py:299-302`; `schemas.py:118-130`); no env or global override for chat runs. |
| F10 | Window focus change demanded an approval | TRUE — by policy | `focus_app` is ASK by default (`computer/policy.py:66`). Correct posture; optional fast-path when the window is already foreground. |

**Preserved behaviors (do not regress; add regression tests in Q6).** The
TWTR/BBBYQ honest `UNAVAILABLE` with named failing routes; "no data was
fabricated"; the refusal to accept a permission-touching proposal and the
correct statement that durable/permission writes terminate at operator
approval; the degraded-source flag on the web fallback.

---

## 2. Phase Q1 — App surface truth (self-knowledge)

**Goal.** The runtime knows the app's real screens and tabs, with deep links,
and reports them distinctly from the user's saved dashboards. The agent can
answer "where is X in the app?" and never claims a screen does not exist.

**Root cause.** §1 F1 + F2.

**Work items.**

1. **TS manifest** — new `src/lib/app-surfaces.ts` (data only, small): one
   entry per `AppTab` (`app-tabs.ts`) with its sidebar label
   (`src/lib/sidebar/config.ts`) and its sub-tabs/subroutes derived from the
   search registry (`src/lib/search/registry.ts:196-268`; reuses
   `destinationToHref` from `src/lib/search/deep-link.ts`). One source, no
   second hand-maintained copy.
2. **Host → runtime sync** — extend `src/lib/harness/ui-sync.ts` with
   `syncAppSurfaces()` (same idempotent-once pattern as `syncCoreCatalog`),
   mounted in `src/components/layout/ui-catalog-sync.tsx`; add
   `registerSurfaces` to `src/lib/harness/ui-client.ts` over the existing
   `/ui/*` proxy.
3. **Runtime store + map** — persist surfaces in `python/harness/ui/`
   (additive table on the same store); `service.get_application_map` returns
   `screens` (with tabs + deep links) **separately from** `pages` (user
   dashboards) and `components`; `tools.py:78-90` prints screens with their
   deep links; tool description says explicitly: *saved dashboards are the
   user's pages; app screens are fixed and enumerated here*.
4. **Seed noise fix** — give the first-run seeded dashboard a deterministic id
   (`use-dashboards.ts:158-164`) so the mirror idempotency key is stable, and
   never mirror an unseeded default.

**Contract.**
`screens: [{ id, label, deepLink: "/?tab=…", tabs: [{ id, label, deepLink:
"/?tab=…&sub=…" }] }]`; `pages` keep their current shape but carry
`kind: "user-page"`.

**Gates.**
- `python/tests/test_ui_surfaces.py` (new): the map contains `memory` with a
  `reviews` tab whose deep link is `/?tab=memory&sub=memory.reviews`; contains
  `skills` with `learning`; surfaces survive a reopen (store round-trip).
- `npx vitest run src/lib/search/registry.test.ts src/lib/harness/ui-sync.test.ts`
  plus a new completeness test: every `AppTab` has a surface entry.
- Agent e2e (python): ask "where can I see learning reviews?" → the answer
  names Memory → Reviews with the deep link. Ask "does the app have a Reviews
  screen?" → yes.
- `npx tsc --noEmit`.

**Docs.** `docs/ui-engineering.md` (map contract), NAVIGATION row (already
added for this plan; the phase updates the UI-engineering row).

**Paste-ready prompt.**

> Read `docs/harness/roadmap/qa-round-1-fixes.md` §2 (Phase Q1). Implement it:
> the app-surface manifest module, the host→runtime sync, the runtime store and
> `ui_get_application_map` `screens` section, the deterministic seed id, and
> the gates named there. One source of truth for surfaces; no second copy. Run
> the phase gates plus `npx tsc --noEmit`. Update `docs/ui-engineering.md`,
> append the CHANGELOG entry, and report `docs updated: …`.

---

## 3. Phase Q2 — Learning-loop visibility to the agent

**Goal.** The agent can read the learning review queue and the learning
candidates — truthfully, in plain language — and the banner deep-links to the
right screen.

**Root cause.** §1 F3 + F4.

**Work items.**

1. **Read-only tools** (new module `python/harness/learning_tools.py`, or an
   additive section in `memory_tools.py` if it stays small):
   - `learning_review_list` — wraps `store.list_learning_reviews`
     (`persistence.py:1113-1124`) plus the health counters behind
     `GET /learning-review/health` (`routers/sessions.py:253-256`). Row:
     `{id, runId, status(queued|running|completed|failed), mode, outcome, createdAt}`.
   - `learning_candidate_list` — wraps `EclipseMemoryStore.list_candidates`
     (`store.py:1051-1060`). Row: `{id, status, kind, createdAt, summary}`.
   - Both: `permission="read"`, honest empty state ("No reviews yet — one is
     queued automatically after every completed or failed run, after a short
     idle"), never a fabricated count. Register on the ONE registry; allowlist
     on `ECLIPSE_AGENT` (`agents.py`).
   - Honesty note in the description: the review list is **not** user-scoped
     today; do not imply per-user filtering.
2. **Banner deep link** — `graph_context.py:446` `learnQueuePath` →
   `/?tab=skills&sub=skills.learning`; update the TS fallback
   (`memory-action.ts:154`) and its tests (`memory-action.test.ts:86-104`).
   Check the panel renders it as a link (`memory-action-panel.tsx:152-166`).
3. **Prompt guidance** — one paragraph in `prompts.py`: after a run, a review
   is queued automatically; the agent can list reviews/candidates with the two
   tools and must never state "zero" without reading them.

**Gates.**
- `python/tests/test_learning_tools.py` (new): both tools registered, read
  permission, return rows after a completed run + queue tick, honest empty
  state, plain-language strings.
- `python/tests/test_learning_review.py` extended: `learnQueuePath` is an app
  deep link (`startswith("/?")`).
- `npx vitest run src/lib/chat/memory-action.test.ts`.
- QA re-run of prompt 4 returns actual reviews, or the honest empty state with
  the "how reviews are created" sentence.

**Docs.** `docs/harness/memory-skills-evolution-plan.md` (status note),
NAVIGATION row for learning-review tools.

**Paste-ready prompt.**

> Read `docs/harness/roadmap/qa-round-1-fixes.md` §3 (Phase Q2). Implement the
> two read-only learning tools, the banner deep-link fix, and the prompt
> guidance exactly as specified, with the gates named there. Reuse the existing
> stores and health counters — do not create new persistence. Append the
> CHANGELOG entry and report `docs updated: …`.

---

## 4. Phase Q3 — Memory inventory honesty

**Goal.** "What is in my memory store?" has a truthful, single answer.

**Root cause.** §1 F5.

**Work items.**

1. `memory` tool gains `action:"inventory"` — counts by status and type via
   `memory_lifecycle_counts()` (`store.py:130-162`), plus the scope of the
   calling context; no content, counts only. Output names the two read
   semantics explicitly (list = recent/active/user scope; search = relevance
   over user+general).
2. `memory_provider_status` text renders the native `health.detail` count
   ("N active") it already computes (`native.py:57-63`; text at
   `memory_tools.py:500-507`).
3. Tool descriptions updated to state what each action can and cannot see.

**Gates.**
- `python/tests/test_memory_tools.py` extended: inventory counts match the
  store; provider-status text contains the count; plain-language check.
- QA re-run of the memory question: totals stated, no contradictory subsets.

**Paste-ready prompt.**

> Read `docs/harness/roadmap/qa-round-1-fixes.md` §4 (Phase Q3). Add the
> `memory` inventory action, render the provider-status count, update the
> descriptions, and pass the gates named there. Counts only — never fabricate
> or estimate. Append the CHANGELOG entry and report `docs updated: …`.

---

## 5. Phase Q4 — Browser QA reachability & honest errors

**Goal.** The agent can operate the running app (with deep links), reads the
real failure cause when it cannot, and has one sanctioned read path to the
app's own GET APIs.

**Root cause.** §1 F6 + F7 + F8.

**Work items.**

1. **Q4a — Error honesty.** `browser/session.py:428-470`: surface the
   transport cause (structured class + one plain sentence) into the tool
   result, not only `metadata.error`. Classes: host not resolvable
   (canonical-host redirect landed on a host this machine cannot resolve),
   connection refused, timeout, redirect loop.
2. **Q4b — App-origin navigation.** Resolve the app's canonical origin the way
   the front door does (`BE_CANONICAL_HOST` + proxy awareness, or loopback when
   the proxy is absent) and use it for app navigation; follow the 307 to the
   canonical host correctly. Also: launching with `url` bypasses the policy
   gate while `navigate` does not (`manager.py:270-271` vs `tools.py:115`) —
   make this consistent or document it.
3. **Q4c — Boot-state vocabulary.** Snapshot/navigate recognise the boot
   overlay (`global-loader.tsx`) and the six by-design warm-up aborts; report
   "app still starting" (with the loader state) instead of "stuck"; add the
   app-boot note to the browser tool description.
4. **Q4d — Sanctioned local read (decision).** Either (a) a bounded read-only
   tool `app_api_get` — GET only, origin fixed to the app (`HARNESS_CALLBACK_URL`
   / canonical host), path allowlist `/api/**` minus known mutations, response
   size cap, no approval, `permission="read"` — or (b) rely on the fixed
   browser only and document that agents cannot read app APIs directly.
   **Recommend (a)**; it removes this whole class of dead-ends for QA. Either
   way, write the ADR.

**Gates.**
- Unit tests for the error classifier (fake Playwright errors → class +
  sentence).
- Browser smoke (skip-if-offline): navigate to the app origin, `?tab=memory`
  renders, Reviews tab reachable.
- New tool tests (if Q4d-a): allowlist enforced, mutations refused, size cap,
  honest 503 when the app is down.
- ADR-H entry in `docs/harness/decisions.md`.

**Docs.** `docs/harness/browser-runtime.md` (error classes, app-boot note,
canonical-origin navigation), NAVIGATION row.

**Paste-ready prompt.**

> Read `docs/harness/roadmap/qa-round-1-fixes.md` §5 (Phase Q4). Implement
> Q4a–Q4c; for Q4d follow the recommendation (bounded `app_api_get`) unless a
> security objection is recorded. Keep the existing policy posture: no new
> hosts, loopback stays local-first. Pass the gates named there; write the
> ADR; update `docs/harness/browser-runtime.md`; append the CHANGELOG entry.

---

## 6. Phase Q5 — Chat step budget

**Goal.** A navigation-heavy QA conversation is not cut off at 8 model steps
while retaining the safety cap.

**Root cause.** §1 F9.

**Work items.**

1. Make the chat agent's budget configurable: env
   `ECLIPSE_CHAT_MAX_STEPS` (clamped 1–32), applied when the caller supplies no
   `agent` config (`agents.py:299-302`; resolver in `graph.py:447-451`).
   Default: raise chat from 8 to 12 (measured: the QA navigation runs needed
   12–20 steps; browser/computer runs carry separate, larger budgets already —
   `browser/config.py:98`).
2. Optional (small): `focus_app` fast-path when the target window is already
   foreground; keep ASK otherwise.
3. ADR note for the budget change (why 12, what the ceiling is).

**Gates.**
- `python/tests/test_chat_step_budget.py` (new): env override, clamp, default.
- Policy test unchanged for `focus_app` (if fast-path landed: already-focused
  allowed, otherwise ASK).

**Paste-ready prompt.**

> Read `docs/harness/roadmap/qa-round-1-fixes.md` §6 (Phase Q5). Implement the
> env-configurable chat step budget (default 12, clamp 1–32) and the optional
> focus fast-path. Do not touch the browser/computer budgets. Pass the gates;
> record the ADR note; append the CHANGELOG entry.

---

## 7. Phase Q6 — Re-run QA Round 1 + closeout

**Goal.** The original four prompts are re-run and each is verifiable against
an explicit acceptance table; the preserved behaviors get regression tests.

**Work items.**

1. Regression tests for §1 "Preserved behaviors": honest `UNAVAILABLE` on a
   delisted symbol with named failing routes; a permission-touching review
   proposal refused end-to-end; plain-language gate.
2. Re-run the four QA prompts. Acceptance:
   | Prompt | Pass condition |
   |---|---|
   | Fails-honestly + open Reviews | `UNAVAILABLE` evidence retained; agent names Memory → Reviews with a working deep link (Q1) |
   | Run a learning review | Either executes it or names the exact manual step *and* shows the queued review via `learning_review_list` (Q2) |
   | Accept permission proposal | Refused with the operator-approval explanation (unchanged) |
   | Recent reviews in plain language | Real rows with statuses, or the honest empty-state sentence (Q2); memory totals stated (Q3) |
3. Close docs: progress log checkboxes, CHANGELOG, NAVIGATION, ADRs, status →
   Done.

**Gate.** `npm run test` + `npx tsc --noEmit` + `npm run check:all`, compared
against the documented known-failure set.

---

## 8. Non-goals (whole round)

- **No new surfaces for the agent to mutate.** Q2/Q3 tools are read-only; Q4d
  is GET-only. Nothing here widens write authority.
- **No loosening of operator gating** (`/evolution/**`, `/ui/*`, decision
  gates) or the approval store.
- **No second registry, store, or sync channel** — Q1 rides the existing
  `ui-sync` bridge; Q2/Q3 ride the existing stores; Q4 rides the existing
  browser tool.
- **No UI redesign.** The only UI-adjacent change is the banner deep link and
  the deterministic seed id.
- **No fabrication anywhere.** "No reviews yet" is a first-class answer; counts
  come from the stores.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Q1 manifest drifts from the real sidebar | Completeness vitest over `AppTab` + the registry; the manifest is data-only and derived |
| Q2 review rows leak cross-user information | Today's list is unscoped; the tool states it explicitly; a scoping decision is deferred until profiles are used |
| Q4d becomes an SSRF or auth-bypass vector | Origin fixed to the app, GET-only, path allowlist, size cap, no header forwarding; reviewed in the ADR |
| Q5 raises cost/latency for ordinary chats | Only the *cap* changes (8→12 default), still env-controlled; runs remain bounded |
