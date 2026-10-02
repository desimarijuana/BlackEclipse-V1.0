# Phase 14 — The code capability, reachable from chat — progress

Gates as unchecked boxes before the work started (roadmap §5). Raw output of every
gate is pasted below once run. All commands run from `Black-Eclipse-site/`.

- [x] G1 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_code_request_intent.py -v`
- [x] G2 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_chat_code_profile.py -v`
- [x] G3 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_code_reachability.py -v`
- [x] G4 — `npx vitest run src/components/chat/chat-capability-panel.test.ts src/lib/i18n/plain-language.test.ts`
- [x] G5 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q`
- [x] G6 — `grep -n "code_commit\|code_push\|code_open_pr\|code_deploy" python/harness/agents.py`
- [x] G7 — `npm run check:all && npm run build`

## Audit notes (measured before implementing)

Each claim in the phase file was read against the tree:

- **(a) The chat agent has no code tool.** True as written: `ECLIPSE_AGENT.tools`
  has 27 names and none can read a file, apply a change or run a command.
- **(b) No `autonomy` on the chat path.** True: `grep -rn "autonomy"
  src/lib/harness/run-service.ts src/lib/harness/python-client.ts` returns **no
  matches**; `RunRequestPayload` has no `autonomy` field. The only caller that
  sets one is `src/app/api/code/tasks/route.ts`.
- **(c) `analysis_run` off from chat.** True: `grep -rn
  "analysisEnabled\|analysis_run" src` returns **0**; `RunRequest.analysisEnabled`
  defaults `False` and no front-door code sends it.
- **(d) `createCodeTask` has no caller in `src/`.** True: it is defined in
  `code-client.ts` + `code-browser.ts` and used only by
  `src/app/api/code/tasks/route.ts`. No UI component calls it.
- **(e) A code job already exists but is unreachable from the task list.** True:
  `jobs/model.py::JobTarget` supports `agent_id`/`workspace_root`/`autonomy` and
  `jobs/scheduler.py::_run_job` passes `workspace=RunWorkspace(root=...)` and
  `autonomy=target.autonomy` into `RunRequest`. `jobs/templates.py` ships
  `build-fix-finance-app`.

**Correction to the phase file's §7/§8 file map.** Work item 7 names
`src/lib/harness/chat-capability.ts` as a *thin call to a new
`python/harness/routers/code.py` `/code/intent` route*. That is the design used
here: the classifier is called over HTTP so the TS side never re-implements the
rules (one runtime, §3.1). A `POST /code/intent` route is therefore added
(operator-gated read, per work item 8).

**A missing prerequisite the phase file does not name.** A `code_change` turn must
be bound to a server-resolved workspace or the write tools refuse with
`WORKSPACE_UNBOUND`. The front door has no way to learn the runtime's resolved
root (`resolve_workspace` takes no request field on the common path). A narrow,
read-only `GET /code/root` route is added so `startChatRun` can send the
confirmation ref; the runtime still binds only its own server-resolved root and
this value can only CONFIRM it (Phase 1 semantics). It grants nothing.

### Existing tests whose expectations I changed

None. No existing test expectation was modified; all new assertions are additive.

## Gate output

All commands run from `Black-Eclipse-site/`.

### G1 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_code_request_intent.py -v`

```
============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\MSI\Documents\Default Project\black eclipse\Black-Eclipse-site\scripts\vendor\python\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\MSI\Documents\Default Project\black eclipse\Black-Eclipse-site\python
configfile: pytest.ini
plugins: anyio-4.15.1, langsmith-0.13.0, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 22 items

python\tests\test_code_request_intent.py::test_labelled_verdicts[what's the price of AAPL-not_code] PASSED [  4%]
python\tests\test_code_request_intent.py::test_labelled_verdicts[how do the checks work here-code_question] PASSED [  9%]
python\tests\test_code_request_intent.py::test_labelled_verdicts[add a drawdown recipe and run the tests-code_change] PASSED [ 13%]
python\tests\test_code_request_intent.py::test_labelled_verdicts[build me a report-not_code] PASSED [ 18%]
python\tests\test_code_request_intent.py::test_labelled_verdicts[tell me about NVDA's margins-not_code] PASSED [ 22%]
python\tests\test_code_request_intent.py::test_labelled_verdicts[what is the market cap of MSFT-not_code] PASSED [ 27%]
python\tests\test_code_request_intent.py::test_follow_up_after_a_code_change_turn_is_a_change PASSED [ 31%]
python\tests\test_code_request_intent.py::test_follow_up_after_a_finance_turn_is_not_a_change PASSED [ 36%]
python\tests\test_code_request_intent.py::test_follow_up_uses_the_last_user_turn_only PASSED [ 40%]
python\tests\test_code_request_intent.py::test_empty_query_is_not_code PASSED [ 45%]
python\tests\test_code_request_intent.py::test_code_questions_are_read_only[how would you add a component here] PASSED [ 50%]
python\tests\test_code_request_intent.py::test_code_questions_are_read_only[what's wrong with the parser] PASSED [ 54%]
python\tests\test_code_request_intent.py::test_code_questions_are_read_only[why does the endpoint return 500?] PASSED [ 59%]
python\tests\test_code_request_intent.py::test_code_questions_are_read_only[can you tell me how the type error happens] PASSED [ 63%]
python\tests\test_code_request_intent.py::test_code_questions_are_read_only[where is the config file] PASSED [ 68%]
python\tests\test_code_request_intent.py::test_a_question_with_no_code_subject_is_not_code PASSED [ 72%]
python\tests\test_code_request_intent.py::test_a_pasted_path_is_a_change PASSED [ 77%]
python\tests\test_code_request_intent.py::test_a_stack_trace_is_a_change PASSED [ 81%]
python\tests\test_code_request_intent.py::test_the_same_input_always_yields_the_same_verdict PASSED [ 86%]
python\tests\test_code_request_intent.py::test_the_verdict_is_never_a_float_confidence PASSED [ 90%]
python\tests\test_code_request_intent.py::test_ambiguous_bare_noun_is_not_code PASSED [ 95%]
python\tests\test_code_request_intent.py::test_directive_without_a_software_object_is_not_code PASSED [100%]

============================= 22 passed in 0.06s ==============================
```

### G2 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_chat_code_profile.py -v`

```
============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\MSI\Documents\Default Project\black eclipse\Black-Eclipse-site\scripts\vendor\python\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\MSI\Documents\Default Project\black eclipse\Black-Eclipse-site\python
configfile: pytest.ini
plugins: anyio-4.15.1, langsmith-0.13.0, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 7 items

python\tests\test_chat_code_profile.py::test_chat_code_tools_is_exactly_the_declared_set PASSED [ 14%]
python\tests\test_chat_code_profile.py::test_external_actions_are_absent_from_the_chat_profile PASSED [ 28%]
python\tests\test_chat_code_profile.py::test_the_profile_is_a_strict_subset_of_the_edit_verify_surface PASSED [ 42%]
python\tests\test_chat_code_profile.py::test_declared_tools_are_unchanged_by_this_phase PASSED [ 57%]
python\tests\test_chat_code_profile.py::test_edit_verify_turn_binds_write_and_execute_but_no_external PASSED [ 71%]
python\tests\test_chat_code_profile.py::test_plan_only_turn_binds_read_only PASSED [ 85%]
python\tests\test_chat_code_profile.py::test_unknown_profile_yields_nothing_the_classifier_would_send PASSED [100%]

============================== 7 passed in 0.76s ==============================
```

### G3 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_code_reachability.py -v`

```
============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\MSI\Documents\Default Project\black eclipse\Black-Eclipse-site\scripts\vendor\python\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\MSI\Documents\Default Project\black eclipse\Black-Eclipse-site\python
configfile: pytest.ini
plugins: anyio-4.15.1, langsmith-0.13.0, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 6 items

python\tests\test_code_reachability.py::test_a_code_change_turn_binds_write_and_execute PASSED [ 16%]
python\tests\test_code_reachability.py::test_a_code_change_turn_never_binds_an_external_action PASSED [ 33%]
python\tests\test_code_reachability.py::test_a_finance_turn_binds_no_change_or_execute_tool PASSED [ 50%]
python\tests\test_code_reachability.py::test_a_code_question_turn_has_read_tools_and_no_write_tool PASSED [ 66%]
python\tests\test_code_reachability.py::test_an_unknown_autonomy_binds_no_write_tool PASSED [ 83%]
python\tests\test_code_reachability.py::test_the_external_actions_are_not_in_the_chat_profile_at_all PASSED [100%]

============================== 6 passed in 0.75s ==============================
```

### G4 — `npx vitest run src/components/chat/chat-capability-panel.test.ts src/lib/i18n/plain-language.test.ts`

```
 ✓ src/components/chat/chat-capability-panel.test.ts (5 tests) 6ms
 ✓ src/lib/i18n/plain-language.test.ts (4 tests) 10ms

 Test Files  2 passed (2)
      Tests  9 passed (9)
```

### G5 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q`

```
.........................                                                [100%]
25 passed in 2.20s
```

### G6 — `grep -n "code_commit\|code_push\|code_open_pr\|code_deploy" python/harness/agents.py`

```
python\harness\agents.py:141:    "code_commit", "code_push", "code_open_pr", "code_deploy",
python\harness\agents.py:169:# and deliberately NO external action - `code_commit`/`code_push`/`code_open_pr`/
python\harness\agents.py:170:# `code_deploy` stay on the Code Tasks surface where the approval panel lives.
python\harness\agents.py:181:# Deliberately ABSENT: code_commit, code_push, code_open_pr, code_deploy.
```

Line 141 is inside `CODE_AGENT_TOOLS`; 169–181 are `CHAT_CODE_TOOLS`'s comments.
The four names appear **nowhere** in `CHAT_CODE_TOOLS` itself.

### G7 — `npm run check:all && npm run build`

```
[check-all] tests (vitest + python): npm run test
 Test Files  176 passed (176)
      Tests  2014 passed (2014)
================= 2378 passed, 1 warning in 204.53s (0:03:24) =================
...
  contradiction gate: PASS
  compaction gate: PASS
  Code verification eval — code-verify-v1
  code_verify gate: PASS
    dataset=code-tasks-v1 checksum=9e3896284be04e482fadecdccb6dc527
  safety: S1=PASS, S2=PASS, S3=PASS, S4=PASS, S5=PASS, S6=PASS, S7=PASS, S8=PASS, S9=PASS, S10=PASS, S11=PASS
  code gate: PASS
  route_health gate: PASS
  workflow gate: PASS
  resume gate: PASS
  capability_matrix gate: PASS
eval gates: ALL PASS

[check-all] ALL GATES PASSED
```

`npm run build` then exited 0 (the final route table printed, ending in
`○ (Static)` / `ƒ (Dynamic)`). The first build attempt caught a real defect the
static gates could not: the client panel transitively imported the server-only
`code-client` (`Can't resolve 'fs'` / `'child_process'`). Fixed by splitting the
pure view contract into `src/lib/harness/chat-capability-view.ts`; the rebuild is
clean. Observed counts (not predicted): vitest **176 files / 2014 tests**, pytest
**2378 passed**.

## Audit follow-up (same session)

A fresh `npm run check:all` after the close-out FAILED on
`src/lib/gitignore-guard.test.ts` — the line-ending guard found **mixed CRLF/LF in
`docs/harness/decisions.md`**. This was introduced by the ADR-H117 append itself: a
PowerShell `Add-Content` wrote the new ADR block with CRLF into an LF file. Fixed
by normalizing the file back to LF; re-verified no file in the tree has mixed
endings. Re-run: `npm run check:all` → `ALL GATES PASSED`, vitest 176/2014, pytest
**2384 passed** (the extra ~6 pytest nodes over the close-out figure are the
concurrent agent's `python/harness/finance_facts/` + `retrieval_tools.py` work, not
this phase). Phase gates unchanged: 22 + 7 + 6 + 9 passed.

## Audit findings (what a fresh review of this phase's own work found)

1. **CRLF contamination in the ADR append** — fixed (see above).
2. **The empty task list had no way in.** Fixed (composer above the list).
3. **Classifier precision** — see "Limitations closed" below; fixed.
4. **§6.4's `ChatCapabilityView` is now a first-class `RunResult` field** — the
   deviation is closed. `RunResult.capability` carries
   `{kind, profile, headline, verification}`; it is derived by
   `python/harness/code/capability.py::capability_from_verification` from the
   run's persisted `codeVerification` blob (the profile rides INSIDE that existing
   additive blob as `autonomy`/`workspaceId` — no new column, so the
   `persistence.py` size ratchet is untouched). The front door mirrors it in
   `chat-capability-view.ts::coerceChatCapability`; the panel prefers the
   runtime view and falls back to the flat fields for an older row.

## Limitations closed (follow-up, same session)

The audit above measured four limitations. Three are now fixed:

1. **The classifier now reaches the user's literal wish.** `_SOFTWARE_OBJECTS`
   gained the artifacts the product exists to build — `application`, `app`,
   `algorithm`, `dashboard`, `tool`, `pipeline`, `backtest`, `simulator`,
   `screener`, `indicator`, `bot`, `cli`, `tracker`, `chart`, … — so
   "create a new application", "build me a Monte Carlo simulator" and "build
   algorithms" now return `code_change` (they previously returned `not_code`).
2. **Homograph precision.** A term that is both a directive and an object
   ("test", "build", "run", "check") no longer self-matches: the object must be a
   word the directive does not already supply. "test the market for a reversal"
   and "build a portfolio of stocks" are `not_code` again. The weakest collisions
   (`source`, `state`, `context`, `type`) were dropped from the object set.
3. **Questions and symptoms.** `what does/do/are` join the question openers; a
   reported symptom with a software object or path ("the app crashes when I
   click") and a named error/exception ("it says TypeError on line 5") now
   classify as `code_change`.

Tests: `test_code_request_intent.py` grew from 22 to **43** cases
(`test_the_create_an_application_wish_is_a_change`,
`test_a_reported_symptom_is_a_change`,
`test_finance_verbs_are_not_mistaken_for_code_changes`,
`test_more_code_questions_are_read_only`).

4. **Refusals are now surfaced in plain language.** The runtime's
   `code.refused` / `code.patch.refused` events are normalised into an activity
   row that renders the i18n refusal sentence (`refusal.PROFILE_DENIED`, …) with
   the raw code behind "details", instead of a bare technical operation label.
   Tests: `events.test.ts` (two refusal cases); `activity-item.tsx` renders
   `reasonKey` via `useT`.
5. **§6.4's capability view is now a first-class `RunResult.capability`.** The
   profile (`autonomy`/`workspaceId`) is persisted inside the existing
   `codeVerification` blob; `code/capability.py` derives the view
   (`{kind, profile, headline, verification}`) with an i18n headline KEY; the TS
   side mirrors it (`coerceChatCapability`) and the panel prefers it, falling
   back to the flat fields for an older row. No new persisted column, so the
   `persistence.py` ratchet is untouched. Tests:
   `test_capability_view_derives_from_the_verification_blob`,
   `test_capability_view_for_a_read_only_turn_is_plan_only`,
   the `coerceChatCapability` vitest case.

Gate counts after the fixes: G1 **43 passed**; G2 7; G3 9; G4 10 (+ events 36);
G5 25; G7 vitest **178/2027**, pytest **2415**, `npm run build` exit 0.

## Final gate output (re-run after all fixes)

```
# G1
============================= 43 passed in 0.09s ==============================

# G3
============================== 8 passed in 0.72s ==============================

# G4
 Test Files  2 passed (2)
      Tests  10 passed (10)

# G7
 Test Files  178 passed (178)
      Tests  2027 passed (2027)
================= 2415 passed, 1 warning in 169.29s (0:02:49) =================
eval gates: ALL PASS
[check-all] ALL GATES PASSED
# npm run build -> exit 0
```

(G2 remains 7; G5 remains 25; G6 unchanged — the external actions appear only in
`CODE_AGENT_TOOLS` and comments, never in `CHAT_CODE_TOOLS`.)

## Honest non-property

I did not verify a live end-to-end chat turn against a running model: no provider
is configured in this environment, so the classifier→`startChatRun`→runtime path
is proven by unit tests and the proxy contracts, not by an observed run. The
`/code/intent` route is asserted only through the Python classifier tests and the
TypeScript compile; it was not exercised over HTTP against a booted runtime.
