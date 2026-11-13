---
title: W0 — Flag Matrix and Harness Review Gate
status: Active
last-verified: 2026-11-12
---

# Flag Matrix and Harness Review Gate

This is the review companion to
`docs/harness/roadmap/w0-baseline-and-guardrails-plan.md`. It exists so a
reviewer can answer two questions without reading the whole programme:

1. What flag controls this change, and what is its kill switch?
2. Does this change add a second loop/scheduler/approval path/model client?

---

## Flag matrix

| Flag | Default | Values | Owner | Kill switch | Remove by |
|---|---|---|---|---|---|
| `HARNESS_MODEL_GATEWAY` | `shadow` | `shadow|on|off` | W1 | `off` uses `step.invoke_model_step` | after W1 green for 2 weeks |
| `HARNESS_MODEL_ATTEMPTS` | `3` | 1–10 | W1 | `1` disables same-candidate retry | replaced by provider policy |
| `HARNESS_MODEL_FIRST_TOKEN_S` | `45` | 5–300 | W1 | increase to call timeout | after W1 |
| `HARNESS_CREDENTIAL_POOL` | `on` | on/off | W1 | `off` uses the run key | after W1 |
| `HARNESS_MODEL_FALLBACK_ALLOW_DEGRADED` | `off` | on/off | W1 | `off` skips materially worse fallbacks | after W1 |
| `HARNESS_USAGE_ANCHOR` | `on` | on/off | W2 | `off` uses 4-char heuristic | after W2 |
| `HARNESS_COMPRESSION_LADDER` | `shadow` | shadow/on/off | W2 | `off` uses skeleton only | after W2 |
| `HARNESS_CONTEXT_GATE_PCT` | `50` | 10..90 | W2 | soft gate; hard/emergency at +20/+35 | after W2 |
| `HARNESS_PARALLEL_TOOLS` | `off` | shadow/on/off | W3 | `off` or concurrency `1` | after W3 |
| `HARNESS_TOOL_CONCURRENCY` | `6` | 1–12 | W3 | `1` forces serial | after W3 |
| `HARNESS_TOOL_BATCH_TIMEOUT_S` | `120` | 10–600 | W3 | batch deadline | after W3 |
| `HARNESS_TOOL_GUARDRAILS` | `warn` | warn/halt/off | W3 | `off` disables | after W3 |
| `HARNESS_TOOL_DISCLOSURE` | `auto` | auto/on/off | W3 | `off` keeps eager tools | after W3 |
| `HARNESS_TOOL_DISCLOSURE_THRESHOLD_PCT` | `8` | 1–50 | W3 | `50` effectively disables auto | after W3 |
| `HARNESS_AUTONOMY` | `off` | on/off | recovery/W4 | global kill switch; `off` vetoes W4 | permanent |
| `HARNESS_GOAL_LOOP` | `off` | off/shadow/on | W4 | `off` hides goal/loop execution; `shadow` records verdicts only | after W4 |
| `HARNESS_GOAL_MAX_TURNS` | `20` | 1–100 | W4 | hard goal turn ceiling | after W4 |
| `HARNESS_GOAL_GATE_TIMEOUT_S` | `600` | 30–3600 | W4 | per-gate ceiling | after W4 |
| `HARNESS_GOAL_JUDGE_PROVIDER` | `""` | string | W4 | optional judge provider | after W4 |
| `HARNESS_GOAL_JUDGE_MODEL` | `""` | string | W4 | optional judge model | after W4 |
| `HARNESS_GOAL_MAX_TOKENS` | `0` | 0–10,000,000 | W4 | optional per-turn token cap | after W4 |
| `HARNESS_LOOP_MIN_INTERVAL_S` | `60` | 30–86400 | W4 | minimum loop cadence | after W4 |
| `HARNESS_LOOP_MAX_TICKS` | `50` | 1–1000 | W4 | default loop cap | after W4 |
| `HARNESS_LOOP_MAX_NO_CHANGE` | `3` | 1–20 | W4 | pause after unchanged replies | after W4 |
| `HARNESS_SKILL_EXEC_EVAL` | `on` | on/off | W5 | `off` uses static eval | after W5 |
| `HARNESS_SKILL_CURATOR` | `dry_run` | dry_run/propose/apply/off | W5 | `off` disables | after W5 |
| `HARNESS_MEMORY_HYBRID` | `off` | on/off | W5 | `off` uses lexical only | after W5 |
| `HARNESS_SKILL_EVAL_RETRY_HOURS` | `12` | 0–720 | W5 | `0` retries immediately; a positive value holds an unchanged failed attempt | after W5 |
| `HARNESS_FENCED_PROGRESS` | `on` | on/off | W6 | `off` uses `update_run` | after W6 |
| `HARNESS_CHECKPOINT_ATOMIC` | `on` | on/off | W6 | `off` uses two commits | after W6 |
| `HARNESS_EVENT_SEQ` | `on` | on/off | W6 | `off` uses per-emitter seq | after W6 |
| `HARNESS_EFFECT_TOKENS` | `shadow` | shadow/enforce/off | W6 | `off` disables token check | target: enforce |
| `HARNESS_FILE_CHECKPOINTS` | `off` | off/warn/enforce (`on`→enforce) | W7 | `off` disables snapshots | after W7 |
| `HARNESS_FILE_CHECKPOINT_MAX_MB` | `500` | 50–5000 | W7 | lower the store cap | after W7 |
| `HARNESS_FILE_CHECKPOINT_RETENTION` | `50` | 1–500 | W7 | prune more/less | after W7 |
| `HARNESS_ASYNC_DELEGATION` | `off` | on/off | W7 | `off` uses synchronous delegate | after W7 |
| `HARNESS_DELEGATION_SCHEMA_REPAIR` | `on` | on/off | W7 | `off` validates without repair | after W7 |
| `HARNESS_DELEGATION_STEER_MAX` | `4` | 0–8 | W7 | `0` disables steering | after W7 |
| `HARNESS_DELEGATION_COMPLETION` | `card` | card/continue/off | W7 | `off` hides completion | after W7 |
| `HARNESS_EVIDENCE_ENFORCE` | `off` | on/off | W5 | `off` records but does not disclose | after W5 |
| `HARNESS_FLAG_STRICT` | `off` | on/off | W0 | `off` allows invalid values | permanent |

Defaults preserve today's behaviour. A default change requires an ADR and a
canary. A flag older than its `remove_by` is a review failure.

---

## Reviewer checklist

Copy this into the PR description.

```
## Harness seam review

- [ ] Existing seam extended (file/function): ______________________
- [ ] No second agent loop / scheduler / approval path / model client /
      tool registry / event bus / memory store / database file.
- [ ] Flag: ______________________  Default: ______  Kill switch: ______
- [ ] `run.flags` / event / metric emitted: ______________________
- [ ] Test fails if the old path is used (kill-switch test): __________
- [ ] Contract changed? If yes, ADR: ______________________
- [ ] New dependency? If yes, why is it lighter than the alternative: ____
- [ ] Offline gate / audit / tsc run: ______________________
- [ ] Rollback note: ______________________
```

Reject immediately if the PR:

- adds a `while`/agent loop outside `graph.py`;
- adds a `TICK_SECONDS` loop outside `jobs/`, `automation/`, `tasks/` or
  `fabric/`;
- adds an approval store outside `security/approval.py` /
  `mcp/approvals.py`;
- adds a provider SDK call outside `model_runtime/` / `step.py`;
- registers tools outside `ToolRegistry`;
- creates a new SQLite file.

---

## W0 verification

Current first-slice evidence:

- `python/tests/test_flags.py` — parsing, clamping, enum, snapshot, strict.
- `python/tests/test_kill_switches.py` — every declared flag has a resolvable
  off/minimum state (path assertions are added per workstream).
- `python/tests/test_run_flags.py` — event + context + graph integration.
- `python/tests/test_w0_baseline.py` — read-only metrics, unknown handling,
  CLI JSON/Markdown.
- `python/tests/test_size_budget.py` — graph.py remains at/below its pin
  (the snapshot helper's 11 added lines were offset by moving the context-blob
  helpers to `history.py`).
- `npx tsc --noEmit` — clean.
