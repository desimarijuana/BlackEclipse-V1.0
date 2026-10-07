---
title: Browser Automation Runtime
status: Current
last-verified: 2026-10-07
---

# Browser Automation Runtime

**Who this is for:** a developer changing the browser capability, adding a
provider, or debugging why a `browser_*` tool refused.

This is the *how it works*. The decisions and their rationale are in
[`decisions.md`](./decisions.md) (ADR-H134). The tool-by-tool contract is
generated from `python/harness/browser/schemas.py` (`INPUT_SCHEMAS` +
`TOOL_META`).

## What it is

A first-class, provider-agnostic browser subsystem — not a flat set of Playwright
functions. It is a normal capability of the harness: its tools register on the ONE
`ToolRegistry`, so validation, permission, timeout, effect authorization and the
event stream apply unchanged; its metadata persists on the ONE agent-memory
connection; its secrets resolve through Eclipse's existing encrypted vault tier.

```
Agent → browser_* tool → ToolRegistry → BrowserManager → BrowserSession
      → BrowserProvider (Local Chromium / CDP / optional) → Chromium
```

The model never sees a raw Playwright object; it sees `browser_*` tools and
accessibility snapshots with stable references (`@e1`, `@e2`, …).

## Layer map (`python/harness/browser/`)

| File | Responsibility |
|---|---|
| `tools.py` | The `browser_*` toolset: navigation, observation, interaction, waiting, tabs, files, debugging, storage, interception. Handler table + `register_browser_tools`. |
| `tool_admin.py` | The admin tools: sessions, profiles, vault, human-in-the-loop, device emulation. |
| `tool_support.py` | The ONE implementation of: manager/session resolution, the policy gate (ASK → single-use approval), destructive-action detection, injection scan, result shaping, upload confinement. |
| `schemas.py` | The model-facing JSON input schemas + `TOOL_META` (permission/risk/effect/timeout/description). |
| `manager.py` | `BrowserManager`: the process-wide pool, provider registry, router, vault, profiles, concurrency limit, idle sweep, deterministic shutdown. |
| `session.py` | `BrowserSession`: identity, state machine, tabs, navigation, interaction (action→observe→verify), waiting, files, console/network/errors, dialogs, storage, permissions, CAPTCHA detection, lifecycle. |
| `router.py` | `BrowserProviderRouter`: capability/policy/availability-based provider selection with a plain rationale. |
| `providers/` | `base.py` (`BrowserProvider`/`LaunchOptions`/`ProviderSession`), `local_chromium.py` (Playwright), `cdp.py` (CDP attach + controlled command surface), `optional.py` (Browser Use / Browserbase / Lightpanda / agent-browser / Firecrawl — honest availability, never faked). |
| `capabilities.py` | The `BrowserCapabilities` record per provider (the router's data). |
| `observation.py` | `SnapshotEngine`: accessibility-first snapshots, Eclipse ref renumbering, paging to disk (`persist_artifact`). |
| `inspection.py` | `find` (describe matching elements + their snapshot refs, no interaction) and `highlight` (transient outline). |
| `evidence.py` | `record_browser_source`: records a consulted `http(s)` page on the run's existing `source_sink`, so browser-derived facts reach the answer's Sources panel. |
| `resolver.py` | `Resolver`/`Target`: the locator engine (ref → role/name → label → text → placeholder → testid → CSS → XPath → coordinates) with stale-element re-resolution. |
| `verification.py` | `Verifier`: before/after `PageState`, expected-effect checks, structured result. |
| `vision.py` | `VisionEngine`: screenshot artifacts + a live visual map + the DOM/vision `fuse` decision. |
| `vision_model.py` | `BrowserVisionInterpreter`: optional real visual Q&A over the screenshot through the harness model runtime (`task="vision"`); honest `available:false` when no multimodal model is configured. |
| `execution.py` | `browser_exec`: the sandboxed program parser (JSON steps or a restricted `browser.<op>(...)` AST) + bounded runner. |
| `waiting.py` | The wait operations (`wait`, `wait_for_*`), extracted from `session.py`. |
| `policy.py` | The ONE security authority: permission vocabulary + levels, domain policy, private-target detection, destructive patterns, the prompt-injection boundary (`wrap_untrusted`). |
| `vault.py` | `BrowserVault`: credential REFERENCES resolved internally; metadata persisted without values. |
| `profiles.py` | `ProfileManager`: confined persistent-profile lifecycle. |
| `store.py` | `BrowserStore`: sessions/profiles/traces/downloads/vault-metadata tables on `agent-memory.db`. |
| `trace.py` | `BrowserTrace`: bounded, content-free step record + summary, persisted and emitted. |
| `config.py` | The `browser:` configuration section (env + optional `.black-eclipse/browser.json`). |
| `errors.py` | The structured error family (`BrowserLaunchError`, `BrowserTimeoutError`, `BrowserHumanInterventionRequired`, …). |
| `authorizers.py` | The effect authorizer that admits an effectful browser tool into the run's authorizer chain; the handler's policy engine does the real check. |

## The browser toolset

Registered only when the capability is enabled AND Playwright imports, so the
model is never told about a tool that will refuse. `BROWSER_TOOLS` (in
`agents.py`) is the declared set offered to the finance agent, the code agent and
the chat code profile; `code.policy.allowed_tools` removes the effectful half at
`plan_only`.

Core groups:

- **Navigation:** `browser_launch`, `browser_close`, `browser_status`,
  `browser_navigate`, `browser_back`, `browser_forward`, `browser_refresh`,
  `browser_stop`.
- **Observation:** `browser_snapshot` (primary), `browser_extract`,
  `browser_screenshot`, `browser_vision`, `browser_visual_find`,
  `browser_get_images`, `browser_get_text`, `browser_get_links`,
  `browser_get_forms`, `browser_get_accessibility_tree`, `browser_get_dom`,
  `browser_find`, `browser_highlight`.
- **Visual fallback / fusion:** `browser_visual_locate` (DOM+vision fusion with a
  confidence rationale), `browser_visual_find`, `browser_visual_click`.
- **Interaction:** `browser_click`, `browser_type`, `browser_fill`,
  `browser_select`, `browser_check`, `browser_uncheck`, `browser_press`,
  `browser_hover`, `browser_scroll`, `browser_drag`.
- **Waiting:** `browser_wait`, `browser_wait_for_element`, `_text`, `_url`,
  `_load_state`, `_navigation`, `_network`, `_popup`, `_download`.
- **Tabs:** `browser_tabs`, `browser_new_tab`, `browser_switch_tab`,
  `browser_close_tab`, `browser_new_window`, `browser_switch_window`.
- **Files:** `browser_download`, `browser_upload` (workspace-confined).
- **Debugging:** `browser_console`, `browser_network`, `browser_errors`,
  `browser_evaluate`, `browser_cdp`, `browser_exec`, `browser_dialog`.
- **Storage:** `browser_cookies`, `browser_storage`, `browser_permissions`.
- **Sessions:** `browser_session_create|list|pause|resume|destroy`.
- **Profiles:** `browser_profile_create|list|use|delete`.
- **Vault:** `browser_vault_list|unlock|fill|enter_code|save_login`.
- **Human:** `browser_request_human`, `browser_pause`, `browser_resume`.
- **Device:** `browser_emulate_device`, `browser_set_viewport|user_agent|locale|timezone|geolocation`.
- **Network control:** `browser_intercept` (elevated).

## Accessibility-first observation

`browser_snapshot` asks Playwright for the page's accessibility tree
(`aria_snapshot(mode="ai")`), which annotates nodes with a Playwright ref
(`[ref=e12]`). `observation.parse_snapshot` RENUMBERS those to Eclipse's own
stable, per-snapshot references (`@e1`, `@e2`, …) in first-appearance order and
keeps the mapping.

When the rendered snapshot exceeds `snapshotMaxChars` (default 24,000) the FULL
text is written to `artifactsRoot/snapshots/<session>/snapshot-<n>-<stamp>.txt`
and the model receives a bounded head plus the path — the same gitignored
artifacts area the rest of the harness uses, never the operator's checkout.

## Element resolution and verification

`Resolver.resolve_verified` resolves a `Target` (a `@eN` ref or an object such as
`{role, name}` / `{label}` / `{css}`) to a live locator, confirms it matches, and
— for a stale ref — takes a fresh snapshot and re-resolves by role+name. It never
blindly fails.

Every important action is `action → observe → verify`: `Verifier` captures a
bounded `PageState` before and after, checks the caller's expectations
(`urlChanged`, `elementAppears`, `textAppears`, `dialogAppeared`, …), and returns
`{success, action, state_changed, checks, evidence, summary}`. The click tool
does not report success merely because the call returned.

Observation hierarchy: accessibility tree → DOM → structured page state → vision.
`browser_vision` is the fallback for canvas/graphical pages; `vision.fuse` picks
DOM vs vision from confidence and records why. `browser_find` and
`browser_highlight` support disambiguation: `find` describes every element a
locator matches (with its snapshot ref, role, name and text) WITHOUT interacting,
and `highlight` briefly outlines a target so it can be confirmed or screenshotted.

`browser_vision` **interprets** the screenshot when the run has a multimodal
model: `vision_model.BrowserVisionInterpreter` resolves the run's model settings
through the harness model runtime (`task="vision"`, which requires a model whose
`vision` capability is known-good) and asks a bounded visual question, returning
prose plus any located elements. When no multimodal model is configured the
interpretation is honestly `available: false` and the raw screenshot + DOM map are
returned unchanged — no fabricated description.

## Evidence and research integration

A page the browser actually consulted is provenance. On navigation, snapshot and
extract, `evidence.record_browser_source` records the real `http(s)` URL, title and
retrieval time on the run's existing `source_sink` (the `SourceCollector` every
retrieval tool feeds). The browser-derived fact then appears in the answer's
Sources panel with its URL — never fabricated, and never promoted into a verified
`claim`. Internal pages (`about:blank`, `data:`) are never recorded. The collector
shape is reused, not duplicated.

A bundled, inert `system.browser-research` skill (`skills/library/system/`) teaches
the workflow through progressive disclosure; it ships `status: disabled` and does
nothing until an operator enables it.

## Session isolation and delegation

`session_of` resolves, in order: an explicit `session_id`; a session owned by THIS
run or agent (`BrowserManager.list_active`); the most recently active session as a
last resort. A delegated subagent therefore never drives the parent's browser.
Multiple agents/tasks run simultaneously with isolated contexts.

## DOM + vision fusion

`browser_visual_locate` (`vision.locate`) fuses the DOM locator (visible text,
confidence from match count) with a visual match over the screenshot when a
multimodal model is configured. It reports the chosen path, both confidences and a
plain rationale, carries a stable snapshot reference when known, and emits
`browser.visual.locate` so the fusion is observable in the trace.

## Providers and routing

`BrowserCapabilities` is a data record; the router selects a provider from
configuration, required capabilities, security policy, availability and the
target's privacy. A **private/local** target (`localhost`, `127.0.0.1`,
RFC1918, `*.local`) always routes to `local_chromium`; a cloud provider is
refused for it (never route private content to the cloud). A non-interactive
extraction task routes to `firecrawl`. Every decision carries a plain rationale
emitted in `browser.session.created`.

P0 providers (implemented): `LocalChromiumProvider` (Playwright, an
Eclipse-managed isolated or persistent Chromium, never the user's Chrome),
`CDPProvider` (attach + controlled CDP). P1/P2 providers (`browser_use`,
`browserbase`, `lightpanda`, `agent_browser`, `firecrawl`) implement the SAME
interface and report an honest `availability()` reason when their dependency or
credential is absent — none is faked.

## CDP

`browser_cdp` sends a command through the session's own CDP connection. Only the
`Browser`, `Page`, `Runtime`, `Network`, `Target` and `DOM` domains are allowed
(`providers/cdp.py:ALLOWED_CDP_DOMAINS`); a command outside them is refused, so
"controlled CDP access" never becomes unrestricted host access. A `Runtime.*`
command is `evaluate_js`-gated and a `Network.*` command is
`network_inspection`-gated.

## `browser_exec`

A program is either a JSON list of steps or a restricted Python-subset source
string. `execution.parse_program` walks the source with `ast`: every statement
must be a top-level call of `browser.<op>(...)` with literal arguments; any
import, loop, comprehension, f-string, name reference or attribute chain outside
the closed `OPS` vocabulary is REFUSED, never executed. The runner is bounded by
`max_steps` (hard cap 200), a wall-clock timeout, and a cancellation check, and
records a trace.

## Security model

`policy.py` is the ONE authority. It answers, before a sensitive action:

- **Permissions** (`navigate`, `click`, `type`, `upload`, `download`,
  `evaluate_js`, `read_cookies`, `write_cookies`, `network_inspection`,
  `credentials`, `external_submission`, `payments`) at levels **ALLOW / DENY /
  ASK**. Fail-closed defaults: credentials and payments DENY; uploads,
  `evaluate_js`, `write_cookies` and external submission ASK.
- **Domain policy**: allowed / blocked / approval domains, checked before
  navigation and sensitive actions.
- **Destructive-action protection**: a click whose label matches a destructive
  phrase (delete / pay / send / submit…) is elevated to ASK (or DENY for a
  payment when payments are off).
- **Prompt-injection boundary**: page content is UNTRUSTED. Every observation is
  wrapped by `wrap_untrusted` (`<<<UNTRUSTED_PAGE_CONTENT>>>`); `scan_injection`
  flags instruction-like text and the tool notes it. Page content can never
  override system policy, tools, or user intent.

An ASK verdict routes through the SAME single-use, digest-bound approval store the
rest of the harness uses (`kind="browser_action"`), including the pause-for-
decision path. `browser_request_human` moves the session to `HUMAN_REQUIRED`;
`browser_resume` returns it to `READY`.

## Sessions, isolation and profiles

`BrowserSession` tracks `session_id`, `agent_id`, `task_id`, `profile_id`,
provider, backend, browser type, tabs/active tab, timestamps, state and
permissions, and enforces an explicit state machine (`CREATING → READY →
NAVIGATING/ACTING/OBSERVING → …`, failures `FAILED`/`DISCONNECTED`/
`HUMAN_REQUIRED`/`TERMINATED`). Multiple agents/tasks run simultaneously with
isolated contexts; a named **profile** shares cookies/storage persistently and
nothing is shared unless a profile is named.

Cleanup is deterministic: `BrowserManager.stop()` closes every session and stops
the idle sweeper; a session closes pages → context → browser in order; a
`TERMINATING → TERMINATED` transition is enforced.

## Files, persistence and artifacts

Downloads are tracked (filename, source, size, path, checksum, status) and saved
under `artifactsRoot/downloads`; uploads are confined to the run's workspace root
(never an arbitrary host file). Screenshots, snapshots and traces live under
`artifactsRoot` (`screenshots/`, `snapshots/`, `traces/`). Session/profile/trace/
download metadata persists in `agent-memory.db` (never `jdds.db`, never
`eclipse_memory.db`); the vault table holds only references.

## Configuration

Resolved by `config.load_browser_config()` from defaults, an optional
`.black-eclipse/browser.json` (a `browser:` object or the object directly, path
overridable with `HARNESS_BROWSER_CONFIG`), then env vars. Key knobs:
`HARNESS_BROWSER_ENABLED`, `HARNESS_BROWSER_PROVIDER`, `HARNESS_BROWSER_HEADLESS`,
`HARNESS_BROWSER_MAX_SESSIONS`, `HARNESS_BROWSER_MAX_STEPS`,
`HARNESS_BROWSER_MAX_EXEC_SECONDS`, `HARNESS_BROWSER_IDLE_TIMEOUT`,
`HARNESS_BROWSER_ALLOW_CREDENTIALS`, `HARNESS_BROWSER_ALLOW_PAYMENTS`,
`HARNESS_BROWSER_ARTIFACTS_DIR`, and the per-provider flags
(`HARNESS_BROWSERBASE_*`, `HARNESS_LIGHTPANDA_*`, …). Hard ceilings
(`MAX_SESSIONS_CEILING` etc.) can be lowered but never removed. `/health` returns
a content-free `browser` block; `/browser/capabilities` returns the full provider
table.

## Observability and tracing

Every action emits `browser.*` events on the run's emitter (`browser.launched`,
`browser.navigated`, `browser.snapshot`, `browser.clicked`, `browser.downloaded`,
`browser.permission.denied`, `browser.human.requested`, …). A `BrowserTrace`
records each step (action, safe params, observation summary, verification, provider,
timing, error) bounded to a cap, and is readable via `GET /browser/traces`.

## Testing

- `python/tests/test_browser_unit.py` — policy, router, snapshot parsing, exec
  parsing/refusals, config, provider availability, vault references, registration
  (no browser launched).
- `python/tests/test_browser_integration.py` — the acceptance flow against a REAL
  Chromium driving `python/tests/browser_app.py` (a stdlib local test app:
  /login, /forms, /tables, /modal, /dialog, /iframe, /upload, /download, /dynamic,
  /console-error, /network-error, /navigation, /popup, /challenge). Skips cleanly
  when Playwright/Chromium is absent, so the offline suite still gates the app.

## Self-healing

`scripts/doctor.js` probes `import playwright` and repairs it via
`python/requirements.txt` (best-effort), and REPORTS whether the Chromium binary
is present, naming `python -m playwright install chromium` — it never
auto-downloads the browser. The Python Playwright is pinned to the 1.62 series so
it shares the SAME chromium build the app's Node Playwright already caches.

## Cloud providers

`BrowserbaseProvider` is a REAL cloud backend: when enabled
(`HARNESS_BROWSERBASE_ENABLED`) with a credential reference
(`HARNESS_BROWSERBASE_API_KEY_REF`) and optional project id, it creates a session
through the Browserbase REST API and attaches over CDP through the SAME Playwright
driver the local provider uses. The credential is resolved internally through the
vault and never shown to the model; when it cannot be resolved, the provider
reports an honest `CREDENTIAL_UNAVAILABLE`. A private/local target still never
routes to it.

## Not available in this environment

A provider whose dependency or credential is absent reports
`available: false` with a reason and is never faked: `firecrawl` (needs the
package or `FIRECRAWL_API_KEY`), `browserbase` (needs an enabled config + a
vault credential reference), `lightpanda` (needs an endpoint), `agent_browser`
(needs the executable), `browser_use` (needs the `browser-use` package).
