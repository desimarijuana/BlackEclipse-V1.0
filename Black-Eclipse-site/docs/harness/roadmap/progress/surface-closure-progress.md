---
title: "Surface closure — progress log (make the code + jobs surfaces reachable)"
status: Done
last-verified: 2026-10-01
---

# Surface closure — progress log

**Task.** Make the code capability (roadmap phases 5 + 12.5), the jobs capability
(phase 6) and the capability statement reachable from the running Eclipse app.
Front-door only — no runtime change, no second execution path.

**Operating rules:** `docs/harness/roadmap/README.md` §3.1 (one runtime), the
`AGENTS.md` docs obligation, and the task's own non-goals. This work is
uncommitted by instruction.

## Measured baseline (Phase 0, before any change)

`npm run check:all` from `Black-Eclipse-site/`:

```
vitest:  Test Files 174 passed (174);  Tests 1983 passed (1983)
pytest:  2278 passed, 1 warning
eval gates: ALL PASS
```

One `check:all` run during the baseline failed
`test_kill_leaves_no_orphan_python_process` (3 vs 2 process count); it passes in
isolation and is the documented concurrency flake, unrelated to any file touched
here. The clean re-run above (2278) is the regression baseline.

Pre-change reachability (all as the prompt predicted, except the last — a false
positive):

| Probe | Expected | Observed |
|---|---|---|
| `grep -rn "screens/code" src \| grep -v screens/code/ \| wc -l` | 0 | **0** |
| `grep -rn "screens/jobs" src \| grep -v screens/jobs/ \| wc -l` | 0 | **0** |
| `grep -rn "jobs" src/lib/sidebar/config.ts src/components/layout/sidebar.tsx \| wc -l` | 0 | **0** |
| `grep -rn "capability\." src/components src/app \| wc -l` | 0 | **1** — a false positive: the route folder `src/app/api/data/[capability]/route.ts` contains the literal `capability`. Phase 12's `capability.*` i18n keys are **not** rendered anywhere; confirmed by reading the dictionary (`capability.title` etc. exist) and finding no consumer. |

## Phase 1 — the code capability is now reachable

The seven Phase-5 panels existed but nothing imported them. A thin container was
needed (there was no single `code-screen.tsx`); it wires the EXISTING `code-client`
to the EXISTING panels, exactly as `jobs-screen.tsx` does.

- **New** `src/components/screens/code/code-screen.tsx` — the container. Fetches
  `listCodeTasks`/`listCodeApprovals`, loads the selected task + its change, and
  renders `TaskList` + `TaskDetail` (which composes `PlanReview`, `DiffViewer`,
  `CheckResults` → the Phase-4 `CodeVerificationPanel`, and `WorktreeActions`) and
  `CodeApprovals`. A `useSubroute('code', …)` handler brings the approvals panel
  forward on a `code.approvals` palette request. No agentic logic.
- `src/components/screens/stock-chat.tsx` — a `dynamic(...)` import for
  `code-screen` and a keep-alive `visited.has('code')` block, in the same shape as
  the `skills`/`memory` blocks. It takes no `isOperator` prop (it does not need
  one — the runtime gates the mutations).
- `src/lib/harness/code-client.ts` — added `getCodeTaskDiff`/`resumeCodeTask` so
  the container can render the change and the resume action (the diff and resume
  routes already existed; this only types them).
- `src/lib/app-tabs.ts` — `'code'` added to the ONE tab vocabulary.
- `src/lib/sidebar/config.ts` — `{ id: 'code', label: 'Code Tasks', icon: SquareCode, group: 'agentic' }`.
- `src/lib/search/registry.ts` — `page-code` + `sub-code-approvals`.
- `src/lib/i18n/dictionaries/en.ts` + `nav.ts` + `global-search.tsx` (icon map) +
  `plain-language.test.ts` (denylist prefix) — the `nav.code` key, the container's
  `code.task.heading`/`listHeading`/`detailPlaceholder`/`reload`/`loadFailed` keys,
  and the `code`/`calendar` icon names.

Evidence (post-change grep, was 0):

```
grep -rn "screens/code" src --include=*.tsx | grep -v "^src/components/screens/code/" | wc -l
# → 1   (the dynamic import in stock-chat.tsx)
```

Reachability test: `code-screens.test.ts` → *"is reachable from the shell: the tab
is mounted and the nav points at it"* (asserts `stock-chat.tsx` contains
`screens/code/code-screen` and `visited.has('code')`). `tsc --noEmit` clean.

## Phase 2 — the jobs surface is now reachable

Same shape, for jobs.

- `src/components/screens/stock-chat.tsx` — `dynamic(...)` import for
  `jobs-screen` + a keep-alive `visited.has('jobs')` block. `JobsScreen` takes no
  props (verified by reading it), so no operator gate is imposed at the mount: the
  screen fetches through the operator-gated `/jobs` proxy, and its mutations are
  gated by `guardMutation` on the front door and `require_operator` in the runtime.
  A client-side gate would be presentational, not a boundary, so none was added.
- `'jobs'` added to `src/lib/app-tabs.ts`; the sidebar section
  `{ id: 'jobs', label: 'Scheduled Jobs', icon: CalendarClock, group: 'agentic' }`;
  registry rows `page-jobs` + `sub-jobs-library`; the `nav.jobs` key and the
  `calendar` icon name.

Evidence (post-change grep, was 0):

```
grep -rn "screens/jobs" src --include=*.tsx | grep -v "^src/components/screens/jobs/" | wc -l
# → 1   (the dynamic import in stock-chat.tsx)
```

Reachability test: `jobs-screens.test.ts` → *"is reachable from the shell: the tab
is mounted and the nav points at it"*.

**Which job-editor affordances are now reachable.** The Phase-11 destination /
per-target picker is reachable: `JobsScreen` renders `JobEditor` when the user
starts a new job, and that editor's `DELIVERY_ADAPTERS` buttons + destination input
(added in Phase 11) render in that branch. The template library (`TemplatePicker`)
renders when there are no jobs yet, and is also a palette destination
(`sub-jobs-library`). The delivery outcome (`jobs.delivery.message.*`) surfaces on
the run row via `JobDetail`. Nothing in the jobs editor is left dark by the mount.

## Phase 3 — one AppTab vocabulary, stale statuses, corrected rows

**(a) Drift.** `AppTab` was declared twice. Both now re-export the ONE declaration
in the new `src/lib/app-tabs.ts`:

```
// src/components/layout/sidebar.tsx   →  import type { AppTab } from '@/lib/app-tabs'; export type { AppTab };
// src/lib/search/types.ts             →  import type { AppTab } from '@/lib/app-tabs'; export type { AppTab };
```

`src/lib/app-tabs.test.ts` proves it two ways: a compile-time `Equal<ShellTab,
SearchTab>` assignment (a drift fails `tsc --noEmit`) and a runtime check that
every sidebar section has a `navLabelKey`. No wider refactor.

**(b) Status.** `phase-11-progress.md` and `phase-12-progress.md` flipped
`status: In progress → Done`, each with an appended closure note (append-only). The
phase files and the README index were already Done.

**(c) NAVIGATION rows** 65 and 70 corrected to name the mounted container and the
shell mount; `last-verified` bumped on this doc (it was re-read).

**The two expected test failures** (fixed to their new explicit intent, not
weakened — neither literal was replaced by a `.length` computed from the source it
tests):

- `src/lib/sidebar/config.test.ts:21` — the shortcut list `[…F12, '']` became
  `[…F12, '', '', '']` (three sections now have no default).
- `src/lib/sidebar/config.test.ts:57` — the v1-migration shortcut list, same change.

## Tests added (the delta)

| File | Added |
|---|---|
| `src/lib/app-tabs.test.ts` | new — 3 tests (type guard + label coverage + id uniqueness) |
| `src/lib/sidebar/config.test.ts` | +2 tests (code/jobs sections enabled + plain labels) |
| `src/lib/search/registry.test.ts` | +1 test (code/jobs pages resolve to their tabs) |
| `src/components/screens/code/code-screens.test.ts` | +2 tests (reachability + label) |
| `src/components/screens/jobs/jobs-screens.test.ts` | +2 tests (reachability + label) |

## Closeout — measured

`npm run check:all` from `Black-Eclipse-site/`:

```
vitest:  Test Files 175 passed (175);  Tests 1993 passed (1993)
pytest:  2278 passed, 1 warning
eval gates: ALL PASS
[check-all] ALL GATES PASSED
```

The vitest delta is **+1 file / +10 tests** over the 1983/174 baseline — exactly the
10 tests added above. Pytest is unchanged at 2278 (no Python file was touched). The
eval gates are unchanged and pass. The frozen four
(`code/policy.py`, `skills/permissions.py`, `mcp/approvals.py`, `scripts/check-all.js`)
are byte-unchanged; `jdds.db`, `agent-memory.db` and `scripts/scratch/` are untouched.

## Honest limitations

- **The mounted screens were not exercised in a live browser.** The gates prove
  they compile, are reachable from the shell's source, and fetch through the real
  `/api/code` and `/api/jobs` proxies. They do not prove the screens render
  correctly against a live Python runtime with real tasks/jobs. That requires
  running `npm run dev` and clicking through.
- **The capability statement page is deliberately not mounted.** Its user-facing
  reader surface is a product choice for the operator (the task's own non-goal), so
  the `capability.*` keys exist but are still unrendered. The Phase-12 eval report
  and the generated statement stay engineering-facing.
- **Reachability is asserted on shell source text**, not by rendering the shell.
  That is deliberate (mounting is not otherwise observable from a unit test) but it
  cannot catch a runtime condition that hides the block.
- **The flaky `test_kill_leaves_no_orphan_python_process`** may fail once in a full
  concurrent `check:all` run; it is unrelated to this change (no Python file was
  touched) and passes in isolation.
