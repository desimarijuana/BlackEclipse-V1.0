---
title: Tool-Loop Integrity — Progress
status: Current
last-verified: 2026-09-30
---

# Tool-Loop Integrity — Progress

Implementation log for the four tool-loop defects fixed in this pass. Append only.
Repo root `black eclipse/`; app in `Black-Eclipse-site/`. The Python runtime
(`python/harness/`) is authoritative; Next.js is the front door.

## Phase 0 — Baseline and claim verification

Measured from `Black-Eclipse-site/` against the working tree before any edit:

| Gate | Baseline |
|---|---|
| `npx tsc --noEmit` | exit 0 |
| `npx eslint .` | 0 errors / 24 warnings |
| `npx vitest run` | **1 failed / 1936 passed** (164 files) |
| `./scripts/vendor/python/python.exe -m pytest python/tests -q` | **1687 passed** |
| `node scripts/test-evals.js` | ALL PASS |
| `npm run check:all` | FAILED at tests (vitest) — Phase 1 |

Each prompt claim, re-derived:

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | `weekly.test.ts` `buildMonthlyWrapped` red | **CONFIRMED** | `npx vitest run src/lib/journal/analytics/weekly.test.ts` → 1 failed (`expected +0 to be 2`, line 101) |
| 2 | dedupe map is per-run, keyed `name+canonical-args` | **CONFIRMED** | `grep _stable_key\|seen_calls graph.py` → `seen_calls` created once in `build_graph` (line 246) |
| 3 | no generic bound on native tool-result text | **CONFIRMED** | `grep truncat\|max_chars graph.py tools.py` → no bound on `ToolResult.text`; `_bound_output` exists only in `mcp/execution.py` |
| 4 | an approved effectful call is reusable for its whole TTL | **CONFIRMED** | `grep find_active\|usedAt\|single_use approvals.py` → no consumption clause, no `usedAt`; `find_active` returns any APPROVED unexpired row |

The failing test's cause was independently verified: fixtures are fixed 2026-09;
`now.getUTCMonth()` at `2026-09-30T20:12` EDT is `2026-10-01T00:12` UTC → prefix
`2026-10` → 0 matches. Latent since commit; not a flake, not a concurrent write
(mtimes 2026-09-09).

## Phase 1 — The UTC month-rollover time bomb

**Goal.** The release gate is green and cannot silently rot again.

- `src/lib/journal/analytics/weekly.test.ts`: the `buildMonthlyWrapped` test now
  passes `(year=2026, month=8)` explicitly and builds fixtures from that period;
  the two fixtures carry explicit September `exitTime`s. A second test asserts the
  opposite branch: a period with no matching trades yields `trades === 0` and
  `bestMarket === null`.
- **Sweep.** `rg -n "getUTCFullYear|getUTCMonth|getMonth\(\)|getFullYear\(\)|toISOString\(\)\.slice\(0, ?7\)" src --glob "*.test.ts" --glob "*.test.tsx"` → exactly one hit, the fixed file (`weekly.test.ts:100`). **None found beyond the fixed file.**
- `CONTRIBUTING.md` gained a "Time-dependent tests" rule (pass the period
  explicitly or derive the fixture from it; journal dates are UTC everywhere).

**Evidence:** single-file run → 9 passed; full `npx vitest run` → 1941 passed /
164 files; the other seven tests in `weekly.test.ts` unchanged and green.

## Phase 2 — Dedupe scoped to one agent step (ADR-H90)

**Goal.** Duplicate suppression stops one *turn* repeating itself without blocking
a legitimate re-issue across turns.

- `python/harness/graph.py`: `seen_calls` moved from `build_graph` scope to inside
  `tools_node`, so it resets every agent step. Key stays `(name, _stable_key(args))`
  (deliberately NOT the message id). Comment records the retrieval-cache interaction
  (per-run fetch dedupe still applies, so re-issues do not multiply upstream calls).
- Tests (`python/tests/test_graph.py`, existing `ScriptedModel`, real registry):
  1. `test_identical_tool_call_across_turns_executes_twice` — the same `(name, args)`
     at two steps runs twice; the second result is fresh; two `tool.completed`; no
     refusal.
  2. `test_identical_tool_call_within_one_turn_still_refuses` — one execution, one
     `tool.failed`/`TOOL_FORBIDDEN`, only one persisted call.

**Evidence:** those two tests pass; `grep "Duplicate call" python/harness python/tests`
→ **one hit, the source itself** (no prior coverage existed). Full Python suite →
1700 passed. `graph.py` changed ~14 lines; measured 1857 after extracting the
streaming helpers (Phase 3).

## Phase 3 — Bounded native tool-result text (ADR-H91)

**Goal.** No tool result can silently consume an unbounded slice of the context
window, and any trimming is visible.

- `python/harness/tools.py`: `MAX_TOOL_RESULT_CHARS = 24_000` +
  `bound_tool_text(text, limit)`; `ToolResult` gains
  `truncated` / `shown_chars` / `total_chars`. `ToolRegistry.execute` bounds the
  text at the one seam; `data` untouched. Under the bound → byte-identical.
- `python/harness/graph.py`: `tool.completed` carries the fields; a truncated
  result also emits `tool.truncated` (sizes only, once).
- **Justification of 24 000:** `CHARS_PER_TOKEN=4` → ~6 000 tokens;
  `graph.MAX_HISTORY_CHARS=40_000` bounds the whole conversation, so one result
  must be a fraction; `research.synthesis.MAX_PACKET_CHARS=24_000` is the largest
  synthesized packet the runtime already accepts.
- Tests: `python/tests/test_tool_output_bound.py` (6 tests: bound helper both
  directions, at-bound, JSON can't be mistaken for complete, seam sets fields,
  under-bound untouched) + `test_graph.py` `test_oversized_native_tool_result_emits_tool_truncated`.

**Blast radius (measured):** exactly ONE native tool can exceed the bound —
`session_open`, a bounded message *window* with no character ceiling. A maximal
30×3 000-char window measured **25 612 chars** → trimmed to 24 000. The constant was
**not** raised to hide it. No other native tool reaches it.

**Extraction:** the model-streaming helpers (`_ainvoke_streaming`, `_merge_chunks`,
`_text`, `_FINALIZE_INSTRUCTION`) moved to `python/harness/model_stream.py` (pure
move, imported back with the same private aliases) to keep `graph.py` under its
ratchet.

## Phase 4 — Single-use approval lifetime (ADR-H92)

**Goal.** The lifetime of an approval is a stated, enforced, tested semantic.

Chose **Option A — single-use**; rejected Option B (an explicit, operator-only
repeatable/standing grant: a larger surface adding a dangerous-if-misread toggle
for no demonstrated need).

- `python/harness/mcp/approvals.py`: `CONSUMED` status; `usedAt` column (additive
  migration); `consume()` = atomic guarded `UPDATE ... WHERE status='approved'` +
  rowcount check; `is_authorized` documented as a non-consuming probe; `request`
  returns a fresh PENDING row for a consumed call (never the consumed row). The
  authorizer consumes once and marks the call-scope digest on `ctx`; the manager's
  `_execute` re-assert authorizes without re-consuming. Shared
  `invoke_effect_authorizer` handles both authorizer signatures.
- `python/harness/tools.py`: `ToolContext.effect_authorized_digest`; the registry
  clears the scope per call and routes the authorizer through the shared helper.
- Round-trip: `MCPApprovalView` (`mcp-types.ts`) gains `consumed` + `usedAt`; the
  approvals UI (extracted to `src/components/screens/mcp/approvals-panel.tsx`) gains
  a `consumed` filter, badge, and "consumed {usedAt}" line.

**Tests:** `test_mcp.py` (+`test_approval_is_single_use`,
`test_concurrent_identical_authorizations_cannot_both_pass`,
`test_consumed_approval_status_is_exposed`, expiry→consume None, and the e2e
`test_approved_effectful_call_runs_once_then_is_refused` through both seams).
No existing test assumed silent reuse — the workflow e2e still performs one
approved export.

**Evidence:** full MCP subset + full Python suite → 1700 passed. No secret material
is stored, returned, logged, or emitted on any new path (the claim carries only
`approvalId` + a boolean).

## Phase 5 — Closeout

| Gate | Baseline | Final |
|---|---|---|
| `npx tsc --noEmit` | 0 | **0** |
| `npx eslint .` | 0 err / 24 warn | **0 err / 24 warn** |
| `npx vitest run` | 1 failed / 1936 passed | **1941 passed / 164 files** |
| Python pytest | 1687 | **1700** |
| `node scripts/test-evals.js` | ALL PASS | **ALL PASS** |
| `npm run check:all` | FAILED (vitest) | **ALL GATES PASSED** |

Docs: `docs/harness/decisions.md` (ADR-H90/H91/H92),
`docs/harness/architecture.md` (§ execution graph, § effectful approvals),
`docs/NAVIGATION.md` (agentic runtime + approvals rows), `CONTRIBUTING.md`,
`docs/CHANGELOG.md`, this doc.

Ratchets: `graph.py` re-pinned **1916 → 1857** (a genuine shrink from the
`model_stream.py` extraction); `mcp/manager.py` **1106** unchanged (the shared
authorizer helper kept it at 1102); `mcp-settings.tsx` extracted to 1088 (was 1202,
over the 1200 hard ceiling).

**Honest non-properties.**
- `tool.truncated` is emitted on the Python event stream and persisted in the run
  trace; it is **not** wired into a specific chat UI activity line. A UI consumer
  was not added (stated rather than implied).
- The Phase 3 bound is measured against native tools only; MCP results already have
  their own operator-configurable `outputLimitBytes` seam and were not re-measured
  beyond confirming the two bounds compose (MCP output is bounded first, then the
  24k seam applies).
- The dedupe guard keys on canonical args within a step; a model that emits the same
  call with trivially different argument ORDER is already normalized by
  `_stable_key`'s `sort_keys`.

**Working tree.** Not committed. `jdds.db` and the four unrelated user paths
(`docs/investor-eye-architecture.md`, `public/geo/world.geo.json`,
`scripts/fetch-world-geo.mjs`, `scripts/scratch/mcp-servers.liveproof.json`) were
not touched.

no doc change — progress doc only (the ADR/architecture/NAVIGATION/CONTRIBUTING/
CHANGELOG updates are recorded above).
