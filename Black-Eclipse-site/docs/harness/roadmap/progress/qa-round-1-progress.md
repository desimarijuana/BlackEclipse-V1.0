---
title: "QA Round 1 — Progress log"
status: In progress
last-verified: 2026-10-18
---

# QA Round 1 — Progress log

Operating loop: `docs/harness/roadmap/README.md` §5. Phase plan:
`docs/harness/roadmap/qa-round-1-fixes.md`.

Baseline before Q1 (the plan itself was docs-only): `tsc` clean; vitest 344
files / 3536 tests pass; Python 8 failed / 7008 passed — the documented known
set (AAPL stored bars, skill load drift, size ratchets) plus the working-tree
WIP tool-admission failures (`skill_learning_set` / `skill_version_activate`).

## Gate checklist

### Q1 — App surface truth

- [x] `src/lib/app-surfaces.ts` derives every `AppTab` (+ sub-tabs + deep links)
      from the existing sources — no hand-maintained second copy
- [x] `POST /ui/surfaces` syncs the inventory; `UiSurface` persists it on
      `agent-memory.db`; an empty batch is a no-op
- [x] `ui_get_application_map` returns `screens` separately from `pages`; the
      tool text names each screen, sub-tab and deep link under explicit headers
- [x] `ui_list_blueprints` is described as the user's dashboards only
- [x] deterministic first-run dashboard id (`main`) stops duplicate "Main"
      blueprint rows from fresh non-persistent browser sessions
- [x] Python UI tests: 60 passed
      (`test_ui_surfaces`, `test_ui_api`, `test_ui_tools`, `test_ui_service`,
      `test_ui_store`)
- [x] Adjacent Python gates: 91 passed
      (`test_ui_agent_e2e`, `test_ui_mode`, `test_ui_engineering`, `test_ui_cli`,
      `test_ui_focus`, `test_tool_contracts`, `test_tool_output_bound`,
      `test_plain_language`, `test_surface_honesty`)
- [x] Vitest: 32 passed (`app-surfaces` 5, `ui-sync` 6, `registry` 21)
- [x] `npx tsc --noEmit` clean

### Raw output

```
python -m pytest tests/test_ui_surfaces.py tests/test_ui_api.py \
  tests/test_ui_tools.py tests/test_ui_service.py tests/test_ui_store.py -q
60 passed, 1 warning in 9.76s

python -m pytest tests/test_ui_agent_e2e.py tests/test_ui_mode.py \
  tests/test_ui_engineering.py tests/test_ui_cli.py tests/test_ui_focus.py \
  tests/test_tool_contracts.py tests/test_tool_output_bound.py \
  tests/test_plain_language.py tests/test_surface_honesty.py -q
91 passed in 16.79s

npx vitest run src/lib/app-surfaces.test.ts src/lib/harness/ui-sync.test.ts \
  src/lib/search/registry.test.ts
Test Files 3 passed (3); Tests 32 passed (32)
```

### Full suite after Q1

```
npm run test
vitest: 345 files / 3544 tests ALL PASS (Q1 adds 1 file / 8 tests)
pytest: 5 failed, 7018 passed, 27 skipped (1001.93s)
```

The five failures are the documented pre-existing set, none touched by Q1:
`test_graph_api` (AAPL stored bars), `test_phase_s_stabilization` +
`test_size_budget` (user-WIP size ratchets `main.py` 1203 /
`persistence.py` 1441 / `service.py` 1520), `test_skills_api` (skills load
drift). `tsc --noEmit` clean.

The plan's "agent e2e" gate is satisfied deterministically at the tool
boundary (`test_tool_text_names_screens_tabs_and_deep_links`): the tool result
itself now contains "Eclipse Memory", "Learning Reviews" and the exact
`/?tab=memory&sub=memory.reviews` href. A live-model paraphrase test would add
nondeterminism without testing more of this contract.

## Deviations from the plan

- The plan's Q1 contract mentioned tagging `pages` with `kind: "user-page"`.
  Implemented as a **structural split** (`screens` vs `pages`) instead, because
  `BlueprintSummary.kind` already means `page | workspace` on the wire and
  reusing it would change an existing contract. The separation is stronger:
  two different lists, not one list with a tag.
- "Never mirror an unseeded default" was dropped in favour of the deterministic
  seed id. With a stable `main` id the mirror upserts one page instead of
  creating N; skipping the publish entirely would hide the board the user
  actually has from the agent, which is the capability this bridge exists for.

### Q1.1 — rendered-tab truth + agent guidance (QA re-run follow-up)

The Q1 QA run passed the separation/deep-link checks but exposed two defects:
the agent never called `ui_get_application_map` (it grepped the repo; prompt 1
failed to produce a link), and the map under-reported the rendered bars
(Memory 15 vs 8 declared, Skills Maintenance missing; labels differed).

- [x] `src/lib/app-screens.ts` is the ONE tab source for Memory (15 tabs) and
      Skills (10 tabs), including labels and legacy slug aliases
- [x] the screen components import the same arrays — bar, deep links and the
      synced map cannot drift
- [x] Memory deep links now reach Profiles / Providers / Files / Skills
      (previously rendered but unmapped)
- [x] `app-surfaces.ts` uses the rendered arrays and their labels
      ("Facts", "Session Search", "Reviews", "Health/Export", …)
- [x] `prompts.py`: `ui_get_application_map` FIRST for where-is-X; never infer
      app screens from saved pages or repository greps
- [x] gates: `tsc` clean; vitest 18 passed (app-surfaces 7 incl. rendered-tab
      pins, ui-sync 6, size-budget 5 — memory screen 2474 ≤ 2488); Python 72
      passed (`test_prompt_segments`, `test_plain_language`, `test_ui_surfaces`,
      `test_ui_api`, `test_ui_agent_e2e`, `test_tool_contracts`)
- [x] prompt-char ratchet re-pinned 29,994→30,420 (one guidance bullet; both
      pins updated) — the two ceiling tests pass; full suite before the re-pin
      was 7 failed / 7030 passed (the two extras were those ceilings), the
      remaining 5 are the documented known set

### Q1.2 — UI tools in the chat code profile (QA re-run follow-up)

The Q1.1 QA passed wherever the map tool was bound (prompt 3 returned the exact
15 rendered Memory tabs and the new deep links from `ui_get_application_map`),
but four of five runs reported the tool "not bound". The classifier routes
turns containing "repository"/"tabs"/"list" to the chat code profile, and
`CHAT_CODE_TOOLS` omitted every `ui_*` tool.

- [x] `CHAT_CODE_TOOLS` now includes `*UI_TOOLS` — the app map survives a
      coding-turn surface; UI config only, no fs/network/shell authority
- [x] exact-set declaration updated in `test_chat_code_profile.py`
- [x] stale tab-list header comments fixed in the Memory and Skills screens
- [x] gates: 57 targeted Python tests pass (`test_chat_code_profile`,
      `test_code_agent`, `test_ui_surfaces`, `test_ui_agent_e2e`,
      `test_prompt_segments`, `test_tool_contracts`); `tsc` clean; full suite:
      vitest 345 files / 3546 tests pass, Python 5 failed / 7049 passed (the
      documented known set, incl. concurrently-grown user-WIP size ratchets)

### Q2 — Learning-loop visibility

- [x] `learning_review_list` + `learning_candidate_list` registered read-only in
      `memory_tools.py`; they read the same records as Memory → Reviews and
      Skills → Learning Queue, with honest empty states
- [x] banner deep link fixed: `graph_context.py` + TS fallback now
      `/?tab=skills&sub=skills.learning` (tests updated)
- [x] prompt guidance added; ceiling re-pinned 30,420→30,897
- [x] gates: `test_learning_tools.py` (6), `test_memory_tools`,
      `test_chat_code_profile`, `src/lib/chat/memory-action.test.ts` (14)

### Q3 — Memory inventory

- [x] `memory action=inventory` returns whole-store counts by status/lifecycle
      (counts only) and states why list/search differ
- [x] `memory_provider_status` renders the native `health.detail` count
- [x] gates: `test_memory_tools.py::test_memory_inventory_reports_whole_store_counts`

### Q4 — Browser reachability & honest errors

- [x] navigation failures carry their classified cause in the tool sentence
      (`browser/session.py`), not only metadata
- [x] app-origin probe + ONE retry on the first reachable origin
      (`browser/app_origin.py`, `browser/tools.py`); refusal lists the probe
      trail
- [x] boot overlay (`[data-global-loader][data-pct]`) reported as "still
      starting" in navigate + snapshot
- [x] `app_api_get`: GET-only, loopback-only, `/api/` prefix, no redirects,
      200 KB cap, registered read/low and allowlisted on both chat surfaces
- [x] ADR-H220; `docs/harness/browser-runtime.md`
- [x] gates: `test_browser_app_origin.py` (7), `test_app_api_tools.py` (7)

### Q5 — Chat step budget

- [x] `chat_step_budget`: 12 default for `eclipse-agent`,
      `ECLIPSE_CHAT_MAX_STEPS` clamped 1..32, explicit per-run agent config wins
- [x] the `run.started` event reports the same resolved budget
- [x] ADR-H221
- [x] gates: `test_chat_step_budget.py` (5)

### Q6 — Acceptance

- [x] cross-cutting acceptance suite `test_qa_round1_acceptance.py` (7)
- [ ] live re-run of the original four prompts in chat — manual; requires the
      app and a model (the only open item)

## Known limits

- Only Memory and Skills come from extracted rendered tab arrays. The other
  screens still derive sub-tabs from the palette registry; a full audit of every
  rendered tab bar remains (those two were the ones the QA run proved drifted).
- The search palette itself still lacks `skills.maintenance` and several Memory
  sub-pages; the agent map is correct, but the palette gap is a separate
  (smaller) fix.

## Remaining

Q2–Q6 pending.
