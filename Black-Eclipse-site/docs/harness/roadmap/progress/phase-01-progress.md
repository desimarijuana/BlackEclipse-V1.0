---
title: "Phase 1 — Progress log (repository navigator, read-only)"
phase: 1
status: Done
last-verified: 2026-10-01
---

# Phase 1 — Progress log

Operating loop: `docs/harness/roadmap/README.md` §5. Phase file:
`docs/harness/roadmap/phase-01-repository-navigator.md`.

Baseline before Phase 1 (from Phase 0 close): vitest 168 files / 1962 tests;
pytest 1777 nodes; eval gates ALL PASS.

## Gate checklist

- [x] G1 — `npm run check:all`
- [x] G2 — new tests, verbose
- [x] G3 — fixture question returns `path:line`
- [x] G4 — three distinct escape codes
- [x] G5 — `jdds.db` → `PROTECTED_PATH`
- [x] G6 — secret line redacted + one `code.redacted` event
- [x] G7 — navigator holds only the five read tools
- [x] G8 — jargon gate
- [x] G9 — `git status --short` (jdds.db absent)

## Recon — the real shapes (read in full before editing)

- `code/policy.py` (355 lines as shipped by Phase 0): `resolve_within(root,
  candidate) -> Path` raised `PolicyDenial(code, reason)` with only TWO codes
  (`OUTSIDE_WORKSPACE`, `PROTECTED_PATH`). Phase 1 refines this so the three
  escape vectors carry DISTINCT codes (`PATH_TRAVERSAL`, `PATH_OUTSIDE_WORKSPACE`,
  `SYMLINK_ESCAPE`) plus `IGNORED_PATH`/`NOT_FOUND`; `reason` (operator text) is
  unchanged.
- `tools.py`: `ToolRegistry.execute` builds a generic arg model where every
  non-required field defaults to `None`; a strict handler must therefore drop
  `None` keys before its own pydantic model validates (see `_present`).
- `graph.py`: ONE `ToolContext(...)` construction in `build_graph` (line ~300);
  `effective_allowlist` expands only for `allowMcpTools`. graph.py measured 1615
  lines against its 1857 ratchet — the Phase 1 change is 3 lines.
- `session_index.py`: `redact()` inlined its own secret regexes; Phase 1 extracts
  `redact_span(text, marker)` + `secret_pattern_name(text)` from the SAME rules so
  `redact()` delegates and the file reader shares one pattern set.
- `agents.py`/`service.py`: one registration block; the preset is additive.
- Roadmap assumed the ADR series ended at H92; it actually ended at **H99** after
  Phase 0, so Phase 1's ADR is **ADR-H100** (not H103).

## G1 / G3 — raw `npm run check:all`

```
 Test Files  169 passed (169)
      Tests  1966 passed (1966)
================= 1808 passed, 1 warning in 142.08s (0:02:22) =================
  retrieval gate: PASS
  contradiction gate: PASS
  compaction gate: PASS
  route_health gate: PASS
  workflow gate: PASS
  resume gate: PASS
  capability_matrix gate: PASS
eval gates: ALL PASS
[check-all] ALL GATES PASSED
```

Vitest rose **168/1962 → 169/1966** (+1 file/+4: the new
`plain-language.test.ts`). Pytest rose **1777 → 1808** (+31: the new Phase 1
nodes in `test_code_workspace.py` + `test_code_tools.py`).

## G2 — raw `pytest test_code_workspace.py test_code_tools.py -v` (tail)

```
python\tests\test_code_workspace.py ... 21 passed
python\tests\test_code_tools.py ... 10 passed
==================== 31 passed in 0.54s ====================
```

## G4 — raw three distinct escape codes

```
test_confine_traversal_is_refused PASSED
test_confine_absolute_outside_is_refused PASSED
test_confine_symlink_escape_is_refused PASSED
-> PATH_TRAVERSAL, PATH_OUTSIDE_WORKSPACE, SYMLINK_ESCAPE
```

## G5 — raw `jdds or protected`

```
test_jdds_db_is_protected_not_binary PASSED
test_protected_paths_are_refused_for_read PASSED
test_confine_refuses_a_protected_file_before_binary PASSED
-> PROTECTED_PATH for jdds.db (never BINARY_FILE)
```

## G6 — raw `redact`

```
test_secret_shaped_line_is_redacted_with_one_event PASSED
-> «redacted» in the text; the secret value appears in no text, data or event
   payload; exactly one code.redacted event (path + line numbers + pattern name)
```

## G7 — raw navigator allowlist

```
['workspace_docs', 'workspace_list', 'workspace_read', 'workspace_search', 'workspace_status']
finance tools present: []
```

## G8 — raw `npx vitest run src/lib/i18n/plain-language.test.ts`

```
 Test Files  1 passed (1)
      Tests  4 passed (4)
```

## G9 — raw `git status --short`

```
 M Black-Eclipse-site/docs/CHANGELOG.md
 M Black-Eclipse-site/docs/NAVIGATION.md
 M Black-Eclipse-site/docs/harness/decisions.md
 M Black-Eclipse-site/docs/harness/roadmap/README.md
 M Black-Eclipse-site/docs/harness/roadmap/phase-00-policy-and-baseline.md
 M Black-Eclipse-site/docs/harness/roadmap/phase-01-repository-navigator.md
 M Black-Eclipse-site/python/harness/agents.py
 M Black-Eclipse-site/python/harness/graph.py
 M Black-Eclipse-site/python/harness/prompts.py
 M Black-Eclipse-site/python/harness/schemas.py
 M Black-Eclipse-site/python/harness/service.py
 M Black-Eclipse-site/python/harness/session_index.py
 M Black-Eclipse-site/python/harness/skills/manifest.py
 M Black-Eclipse-site/python/harness/skills/permissions.py
 M Black-Eclipse-site/python/harness/tools.py
 M Black-Eclipse-site/src/lib/harness/index.ts
 M Black-Eclipse-site/src/lib/harness/python-client.ts
 M Black-Eclipse-site/src/lib/harness/run-service.ts
 M Black-Eclipse-site/src/lib/harness/types.ts
 M Black-Eclipse-site/src/lib/harness/validation.ts
 M Black-Eclipse-site/src/lib/i18n/dictionaries/en.ts
?? Black-Eclipse-site/docs/harness/roadmap/progress/
?? Black-Eclipse-site/python/harness/code/
?? Black-Eclipse-site/python/tests/fixtures/
?? Black-Eclipse-site/python/tests/test_code_policy.py
?? Black-Eclipse-site/python/tests/test_code_tools.py
?? Black-Eclipse-site/python/tests/test_code_workspace.py
?? Black-Eclipse-site/scripts/scratch/
?? Black-Eclipse-site/src/lib/i18n/plain-language.test.ts
?? Black-Eclipse-site/src/lib/i18n/refusal-copy.ts
```

`jdds.db` does not appear; no `*.db` staged.

## Static checks

- `grep realpath python/harness/code/` → `workspace.py` only.
- `grep subprocess python/harness/code/` → `workspace.py` only (the fixed,
  argument-free `git` probe).
- `grep "def resolve_within|def confine"` → one definition each.
