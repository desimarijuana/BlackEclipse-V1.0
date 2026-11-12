---
title: Eclipse Mobile — Testing Strategy
status: Proposed
last-verified: 2026-11-12
---

# Testing strategy

The runtime is the part that can lose a user's conversation or double-spend a
provider call. It gets the strongest tests. The UI gets enough to protect the
flows.

## 1. Test pyramid

| Level | Scope | Runs | Gate |
| --- | --- | --- | --- |
| L1 pure unit | parsers, digest, schedule maths, redaction, budget, state machine | every push | yes |
| L2 SQLite integration | migrations, transactions, cascade, FTS, event gaps | every push | yes |
| L3 provider fixtures | recorded SSE → normalized events | every push | yes |
| L4 contract conformance | schemas vs desktop/mobile fixtures | every push | yes |
| L5 UI component | chat reducer, sheets, keyboard/safe-area layout | every push | yes |
| L6 device smoke | install, stream, background, notification | per PR to `mobile/**` | yes |
| L7 device exploratory | the 12-step checklist on real hardware | per release candidate | yes |
| L8 performance/security | budgets, SSRF, redaction, tamper | per release candidate | yes |

Coverage is reported but only **runtime-critical** modules have a threshold:
`agent/*`, `store/*`, `security/*` ≥ 85% line coverage. UI coverage is not gated;
behaviour is.

## 2. Rust unit tests (L1)

| Module | Cases |
| --- | --- |
| `agent/context` | persona first, last-N window, failed turns excluded, group author labels, budget trim order, overflow error |
| `agent/loop` | no-tool completion, one tool round-trip, max steps, max tool calls, cancel between steps |
| `agent/retry` | 401 no retry, 429 retry with `Retry-After`, 500 retry, stream cut with/without tool call |
| `agent/policy` | read vs network vs write; first-host approval; standing grant scope |
| `agent/approval` | canonical JSON, digest stability, tamper, expiry, single use, remember scope |
| `agent/tools/*` | schema validation, unknown fields, size/time caps, truncation marker |
| `security/ssrf` | every blocked CIDR, IPv4-mapped IPv6, redirect chain, DNS rebinding, userinfo, non-443 |
| `security/redact` | OpenAI/Anthropic/Google/OpenRouter formats, `Bearer`, exact configured value, redactor failure |
| `security/digest` | key order, number normalization, unicode, nested arrays |
| `schedule` | cron/interval/one-time, DST spring/fall, timezone change, month-end, catch-up |
| `store/events` | monotonic seq, duplicate insert fails, gap query, `last_seq` invariant |
| `store/migrations` | fresh DB, v1→v2, failed migration rollback, newer DB refused |

Property tests (proptest) for:

- event sequence monotonicity under arbitrary insert orders;
- canonical JSON digest equality under key permutation;
- URL parser: no private address passes for arbitrary host encodings;
- markdown parser: never panics on arbitrary bytes (bounded input).

## 3. SQLite integration tests (L2)

Use a temp file, not `:memory:`, for WAL and crash tests. One test per invariant in
`data-model.md` §12:

```
start_run_is_atomic
client_message_id_is_idempotent
event_seq_is_unique
last_seq_matches_max
delete_bot_cascades
fts_stays_in_sync
json_columns_reject_invalid
newer_schema_is_refused
vacuum_into_produces_consistent_copy
secure_delete_removes_freed_pages   // best effort, documented
```

Concurrency: two tasks append to different threads in parallel; one task starts
the same bot twice; assert one run and gap-free `thread_seq`.

## 4. Provider fixtures (L3)

Record real streams once, commit them as fixtures, and never call the network in
CI.

```
mobile/src-tauri/tests/fixtures/
  openai/text.sse
  openai/tool_call.sse
  openai/parallel_tools.sse
  openai/rate_limit_429.json
  openai/stream_cut.sse
  anthropic/text.sse
  anthropic/tool_use.sse
  google/text.jsonl
  google/function_call.jsonl
```

Rules:

- Fixtures are captured with a test key and contain no real prompt or account data.
- Each fixture has a `.expected.json` of normalized `ProviderEvent`s.
- A provider change must update the fixture in the same PR with a note.
- A "live" suite runs weekly (manual or scheduled) against a cheap model and is
  never a required gate; it reports drift.

## 5. Contract conformance (L4)

`packages/agent-contracts` owns JSON Schemas. Tests:

1. Every mobile event payload validates against `run-event.schema.json`.
2. Captured desktop fixtures from `src/lib/agent/events.ts` normalize into the same
   envelope (allow the documented differences: desktop `transient`, mobile
   `message.checkpoint`).
3. Bot/thread/message/approval fixtures validate.
4. An unknown `v` is rejected.
5. Generated TS and Rust types are up to date (`generate.mjs --check`).

Desktop fixtures can be produced without touching production code by running the
existing Vitest suites with a recorder, or by exporting the payload literals from
`events.ts` tests. If a real divergence is found, record it in
`risks-and-decisions.md`; do not "fix" the desktop in this project.

## 6. UI component tests (L5)

Environment: Vitest + `happy-dom` + `@testing-library/react`.

| Area | Cases |
| --- | --- |
| Streaming reducer | delta applied once, checkpoint replaces text, duplicate event ignored by seq |
| Composer | send disabled while empty, IME composition does not send, attachment chip removal |
| Keyboard | `visualViewport` mock: composer stays above the keyboard |
| Safe area | snapshot with insets > 0; no content under the notch |
| Bot list | unread, paused, last-run labels; empty state |
| Approval sheet | exact args shown, allow/deny/remember, disabled while pending |
| Group room | per-member status, one failure does not hide others, cancel one |
| Markdown | streaming half-table does not throw; code block copy; links |
| Accessibility | roles/labels for sheets and buttons; focus trap; screen-reader order |

Do not snapshot whole screens. Snapshot the small, stable pieces (pills, message
header, empty state).

## 7. Device smoke (L6/L7)

### Automated smoke (per PR touching `mobile/**`)

- Android emulator: install, launch, create a bot with a mock provider, send,
  assert the assistant message exists after relaunch.
- iOS simulator: same, on `macos-latest`.
- Tools: Appium (WebView context) or Maestro for the happy path. If the WebView
  context is flaky, keep the automated part to launch + native notification and
  keep the rest manual. Do not fake coverage.

### Manual release checklist

The 12 steps in `ios-android-compatibility.md` §8, plus:

13. Airplane mode → send → clear error, retry works when back online.
14. Deny notification permission → schedule still visible, explains alerts are off.
15. Rotate / large font / RTL locale → no clipped primary action.
16. Delete all data → app restarts empty, no file left in the sandbox.
17. Upgrade install over the previous build → history intact, migration ran.
18. Background 30 minutes → return; no duplicate run, state is honest.

Record device model, OS version and result in the release PR. "Passed on
simulator" is not a substitute for a physical device.

## 8. Performance and security (L8)

| Test | Method | Budget |
| --- | --- | --- |
| Cold start | instrument `app_ready` timestamp | ≤ 2.0 s mid-range |
| Streaming latency | mock provider emits at a fixed rate; measure event→paint | ≤ 100 ms p95 overhead |
| Long thread | 2,000 messages; scroll + search | 60 fps, search ≤ 300 ms |
| Memory | 200 messages + one 5 MB attachment | JS heap ≤ 120 MB, RSS ≤ 200 MB |
| DB write | 2 KB message checkpoint | ≤ 5 ms p95 |
| Battery | 30 min chat on cellular | ≤ 5% on 4,000 mAh |
| App size | release APK/IPA | ≤ 40 MB |
| SSRF suite | adversarial URLs | 100% blocked |
| Redaction suite | key formats + exact value | 0 leaks |
| Approval tamper | mutate digest/args | 0 executions |

Performance numbers are recorded per device in `docs/mobile/` release notes; a
regression > 20% blocks the release until explained.

## 9. Crash and failure injection

Add a **debug-only** `BE_FAULT` hook compiled behind `cfg(debug_assertions)` or a
test feature:

```
BE_FAULT=before_run_insert
BE_FAULT=after_run_insert
BE_FAULT=before_first_token
BE_FAULT=after_tool_request
BE_FAULT=before_tool_execute
BE_FAULT=after_tool_execute
BE_FAULT=before_terminal_event
```

The test harness sets the fault, runs, kills the process, reopens the DB and
asserts:

- no duplicate user message;
- no orphan run in `running`;
- `tool_calls` in `running` become `unknown`, never re-executed;
- approval pending → expired;
- assistant message becomes `interrupted` with the checkpointed text.

## 10. Time, locale and network tests

- Freeze time with an injected clock; never call `SystemTime::now()` directly in
  domain code.
- DST: a `daily 08:00` schedule in `America/New_York` fires once on the spring
  forward day and once on the fall back day, at the intended local time.
- Travel: changing the device timezone recomputes `next_run_at` but does not shift
  the stored IANA zone.
- Locale: `en`, `ar` (RTL), `de` (long words), `ja` (no spaces); no clipped primary
  action at 200% font scale.
- Network: offline, captive portal, TLS error, slow 3G (throttle), provider 429.

## 11. CI

```yaml
# .github/workflows/mobile.yml (sketch)
jobs:
  contracts:   ubuntu-latest  # generate --check + schema validation
  rust:        ubuntu-latest  # fmt, clippy, test, audit, deny
  web:         ubuntu-latest  # tsc, eslint, vitest
  android:     ubuntu-latest  # tauri android build + emulator smoke
  ios:         macos-latest   # tauri ios build + simulator smoke
```

Rules:

- No test ever calls a real provider. Live tests are separate and manual.
- No secrets in PR builds. Signing and store upload are release-only.
- Cache Cargo and Gradle; keep the pipeline under ~25 minutes.
- A flaky device test is quarantined with an issue, not retried forever.

## 12. What is deliberately not tested

- Apple/Google background scheduling at exact times (not controllable; test the
  state machine instead).
- Provider model quality (not our contract).
- OS-level attacks (jailbreak, malicious keyboard) — documented as out of scope.
- Visual pixel parity with the desktop app (mobile is a different product).

## 13. Release gate

A build is shippable only when:

1. All L1–L5 suites pass.
2. L6 smoke passes on Android and iOS.
3. The manual checklist is signed off on at least one physical device per OS.
4. The security acceptance list passes.
5. No performance budget regresses > 20% without a recorded reason.
6. Privacy label/Data Safety text matches the actual network calls in the build.
