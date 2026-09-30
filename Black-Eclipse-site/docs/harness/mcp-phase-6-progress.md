---
title: Eclipse MCP Phase 6 — Progress
status: Current
last-verified: 2026-09-29
---

# Eclipse MCP Phase 6 — Progress

Implementation log for the eight milestones in the Phase 6 MCP hardening prompt.
The agentic runtime is Python (`python/harness/mcp/`); Next.js is the front door.
Source code was authoritative wherever the prompt disagreed with it.

## Milestone 0 — Audit and baseline

**Baseline checks (2026-09-29, vendored Python, `Black-Eclipse-site/`):**

| Check | Result |
|---|---|
| `npx tsc --noEmit` | pass (exit 0) |
| `python -m pytest python/tests/ -q` | pass — **1446 collected, all pass** |
| MCP four files (`test_mcp*.py`) | pass |

Working tree at start contained unrelated user changes (`jdds.db`,
`public/geo/world.geo.json`, `scripts/fetch-world-geo.mjs`, `docs/CHANGELOG.md`,
`docs/investor-eye-architecture.md`). None were touched; `jdds.db` was left
modified.

**Findings re-confirmed against the exact tree:**

- **M1 confirmed** — `MCPManager._connect` catches a startup failure and returns
  with `state="failed"`; no retry/backoff. Recovery is only `POST /mcp/reload`.
- **M2 confirmed** — no `keepalive`/`idle`/`ping`/`expired` anywhere in
  `harness/mcp/`; a mid-call session error is a generic `MCPCallError`.
- **M3 confirmed** — no orphan reaping; shutdown relies on the lifespan only.
- **M4 confirmed** — every enabled server is spawned eagerly in `start()`; no
  lazy mode and no on-disk schema cache.
- **M5 confirmed** — `_build_descriptors` uses `original in set(config.selected_tools)`.
- **M6 confirmed** — `ssrf.py` guards URLs only; no static screening of a stdio
  entry (`bash -c`, `sh -c`, egress/exfil shapes).
- **M7 confirmed** — no `${` interpolation in `config.py`.
- **M8 confirmed** — `env` values persist in `mcp-servers.json`; `secret_refs` is
  the preferred path; `chmod 0600` is a no-op on Windows.
- **M9 confirmed** — `enabled_effects` default `["read"]`; no coarse trust tier.
- **M10 confirmed** — `namespace_tool` produces `mcp_<server>_<tool>` (single
  underscore) plus an 8-char digest on sanitization collision.
- **M11 confirmed** — `auth` validator accepts only `header`/`query`; no OAuth.
- **M12 confirmed** — `_http_transport` passes only `headers`; no TLS/CA/mTLS/SSE.
- **M13 confirmed** — `mcp/__init__.py` states resources/prompts are out of scope.
- **M14 confirmed** — no `sampling`/`elicitation` handling.
- **M15 confirmed** — MCP is not a `RetrievalSource`.
- **M16 confirmed** — `sec_filings`, `calendar`, `dropbox` point at
  `mcp.example.com`; `verified` is a bare bool; no one-click install.
- **M17 confirmed** — `GET /mcp/servers`, `GET /mcp/approvals`,
  `GET /mcp/integrations`, `GET /mcp/workflows`, `POST /mcp/diagnostics` carry no
  `require_mcp_operator`; mutations do.
- **M18 confirmed** — `_normalize_result` maps image/audio to
  `"[image content omitted]"`.
- **M19 confirmed but benign** — `httpx2` is imported inside `_http_transport`
  and is a **declared transitive dependency of `mcp>=2,<3`** (`mcp` requires
  `httpx2>=2.5.0`); installed 2.13.0. Not an accident, but not pinned in our own
  `requirements.txt`.
- **M20 confirmed** — `ApprovalStore` records `requestedByRunId`, `decidedBy`,
  `actionSummary`, `affectedData`, `risk`; the TS `MCPApprovalView` carries all
  of them and the UI renders them (bulk/stale is UI work).

**SDK capability note.** The vendored SDK (`mcp` 2.2.0, protocol 2025-11-25 /
`2024-11-05`) already ships `mcp.client.auth` (`OAuthClientProvider` with PKCE
and a `TokenStorage` protocol), `mcp.client.sse` (`sse_client`), and
`mcp.client.subscriptions`. It does **not** implement the RFC 8628 device flow,
so that must be written inside our layer. This means Milestone 3 can reuse the
SDK's OAuth client rather than adding a dependency.

## Milestone 1 — Config contract, screening, honest surfaces

**Status:** complete.

**What changed**

- **`interpolation.py` (new)** — one pure `interpolate(text, env)` with the
  documented order (process env → built-ins `workspaceFolder`/`userHome`/
  `pathSeparator`). `interpolate_remote` fails closed naming the variable; a
  present-but-empty value counts as unresolved. `MCPServerConfig.resolved_connection()`
  applies the remote rule to `url`/`auth`/`ssl_verify` and the literal-fallback
  rule to stdio `command`/`args`; `resolve_environment` interpolates local `env`.
- **`screening.py` (new)** — static screening (`screen_entry`, `screen_stdio`):
  shell interpreter + inline flag, `;`/`&&`/`|`/backtick/`$(`/`${` control ops,
  download/execute + exfil tokens, an IOC package-name seed (matched only on the
  package token), and a warn-only plaintext-`env`-secret check. **Refuse, not
  sanitize.** Wired at load (`config.load_mcp_configs`), at save
  (`routers/mcp.py`), and at spawn (`manager._connect`).
- **Trust tier** — `MCPServerConfig.trust` (`full` default, anything else fails
  closed to `untrusted`). An untrusted server needs a per-call approval for every
  non-read call regardless of `enabled_effects`, and only an operator-declared
  effect may activate a tool (never an annotation). This is additive to the
  existing effect rule.
- **Filters** — `selected_tools` accepts the legacy list (exact, byte-for-byte
  unchanged) and `{include, exclude}` with fnmatch globs; include wins over
  exclude; empty include selects nothing (`resolve_selected`).
- **Naming** — `mcp__<server>__<tool>` (double underscore). `mcp__a__b_c` and
  `mcp__a_b__c` are distinct; the identity digest survives only as a genuine
  collision last resort. Activation keys on ORIGINAL names, so saved configs
  activate the same tools. ADR-H67.
- **M17 resolved** — the Python read routes (`GET /mcp/servers`,
  `GET /mcp/approvals`, `GET /mcp/integrations`, `GET /mcp/workflows`,
  `POST /mcp/diagnostics`) now carry `require_mcp_operator`; the TS front door
  already carries the operator token. Tests assert a non-operator 403 and a
  loopback 200 for each.
- **M19 resolved** — `httpx2` is a declared transitive dependency of `mcp>=2`
  (not accidental); now pinned `httpx2>=2.5,<3` in `requirements.txt` with the
  reason.
- **UI/types** — `public_dict()` surfaces `trust`/`untrusted`, `lazy`,
  keepalive/idle/lifetime, `sslVerify`, `tools`; `mcp-types.ts` extended.

**Tests added** — `python/tests/test_mcp_config_hardening.py` (interpolation
order, fail-closed remote, literal fallback, filter matrix, screening table,
trust tier, naming) and a parametrized read-route gate test in `test_mcp_api.py`.

**Checks (2026-09-29):** `npx tsc --noEmit` pass; vitest 1837 passed;
Python suite **1479 passed** (1446 → +33). No gate moved.

**Limitations / honesty:** the IOC list is a documentation-backed *seed*, not a
completeness claim (stated in the module). Screening is best-effort
defense-in-depth — the primary boundary remains argv-only spawn with no shell.
`trust` gates approval but does not sandbox the process.

## Milestone 2 — Lifecycle resilience

**Status:** complete.

**What changed**

- **`lifecycle.py` (new)** — `RetryBudget` with separate initial-connect and
  reconnect budgets (`MAX_INITIAL_ATTEMPTS=3`, `MAX_RECONNECT_ATTEMPTS=4`),
  full-jitter exponential backoff, and a terminal `exhausted` state that is
  reported. `is_session_error`, `should_recycle`, `keepalive_due` are pure
  decision helpers.
- **Reconnect with backoff** — `MCPManager._connect_with_retry` retries an
  initial failure; a terminal failure is reported with the attempt count. Startup
  still never crashes the service; cancellation propagates.
- **Call-time reconnect seam** — a call arriving at a `failed`/`closed`/`lazy`
  server triggers ONE bounded `_reconnect_on_call` under a per-server lock; after
  reconnecting it re-fetches the live descriptor and re-checks selection/digest/
  effect, and re-registers only tools that pass the same authority checks.
- **Session-expiry policy** — `client.MCPSessionError` classifies a mid-call
  transport/session drop. A **read** is reconnected and replayed exactly once
  (`mcp.tool.retried`); a **write/external_action** is NEVER replayed and returns
  an explicit `outcomeUncertain: true` outcome saying the effect may or may not
  have happened.
- **Keepalive** — optional per-server `keepalive_interval`; one manager lifecycle
  task pings a live session and routes a failure into reconnect. Stdio is not
  pinged unless set.
- **Stdio recycle** — optional `idle_timeout_seconds` / `max_lifetime_seconds`;
  the lifecycle task recycles a child (fresh process, same config) only when
  `in_flight == 0`, preserving the catalog digest, and re-registers its tools.
- **Orphan reaping** — `orphan_supervisor.py` (stdlib-only). On POSIX it starts
  ONE supervisor that detects parent death by pipe EOF and sweeps registered
  process groups TERM→grace→KILL; clean shutdown unregisters. On Windows the MCP
  SDK already spawns each child in a Job Object with `KILL_ON_JOB_CLOSE`, so the
  supervisor is a no-op there (verified by a real-kill test).
- **Lazy startup + schema cache** — `schema_cache.py` persists a per-server tool
  manifest keyed by a fingerprint of the connection-defining config. A `lazy`
  server registers from cache at boot (`state="lazy"`, no spawn); a missing or
  fingerprint-mismatched entry falls back to a normal eager connect. `lazy`
  defaults off. Status surfaces report `lifestyle.lazyActive` /
  `cachedTools` / "not yet connected".
- **Status/diagnostics** — `statuses()`/`public_configs()` carry a bounded
  `lifecycle` block (attempts, reconnects, last error code, keepalive failures,
  recycled reason); `diagnostics.py` adds `server_lazy`, `server_unavailable` and
  `server_untrusted` states.

**Tests added** — `python/tests/test_mcp_lifecycle.py` (budget, initial-retry
terminal, session classification, read-replay vs no-replay-write, keepalive/
recycle decisions, cache fingerprint + roundtrip + stale/missing fallback + lazy
first-call, reconnect authority bound) and `python/tests/test_mcp_orphan_reaping.py`
(real spawn, hard parent kill, assert no survivor). Fixture additions:
`crash_on_call` in `raw_fixture.py`.

**Checks (2026-09-29):** `npx tsc --noEmit` pass; vitest 1837 pass; Python suite
**1494 passed** (1479 → +15).

**Limitations / honesty:** the POSIX keepalive loop uses `send_ping` with a
bounded timeout; a ping failure is treated as a session signal (a false positive
costs one reconnect). The orphan supervisor registers a child's process group by
polling `ps` for up to ~4s after spawn; on a platform without `ps`/pgid
semantics it is a no-op and the SDK's own teardown remains the guarantee. The
Windows guarantee is the SDK Job Object, not our code — tested, not assumed.

## Milestone 3 — Remote transport and authentication (closes 5D)

**Status:** complete.

**What changed**

- **OAuth 2.1.** The authorization-code + PKCE path uses the MCP SDK's own
  `OAuthClientProvider` (`mcp/client/auth`) — no new dependency. `oauth.py` adds
  a `BridgeTokenStore` (`TokenStorage`) that reads/writes the encrypted vault over
  the authenticated bridge (`mcp_oauth_token_get/set/clear`), plus a minimal
  **RFC 8628 device flow** the SDK does not provide (pending/slow_down/expiry).
- **Token storage.** `src/lib/harness/mcp-oauth-store.ts` stores tokens encrypted
  in JDDS (`SystemConfig.key='mcp_oauth_tokens_v1'`, AES-256-GCM) keyed by server
  id; saving refuses (never plaintext) if encryption is unavailable. New bridge
  capabilities in `data-bridge.ts` and the `/api/harness/data` whitelist.
- **Auth lifecycle.** `MCPManager.oauth_login`/`oauth_logout`, operator-gated
  routes `POST /mcp/servers/{id}/login|logout` + TS proxies + `mcpOauthLogin/Logout`.
  Clearing credentials leaves the server configured but disconnected.
- **Auth/TLS diagnostics.** `diagnostics.py` adds `oauth_rejected` (distinct from
  unreachable), `oauth_refresh_failed`, `oauth_not_logged_in`, `oauth_expired`,
  `ca_bundle_missing`, `client_cert_missing`, `tls_verification_disabled`; the TS
  diagnostics route passes token STATUS (no values).
- **TLS/mTLS/SSE.** `ssl_verify: true|false|CA-path`, `client_cert`/`client_key`
  (combined PEM, `[cert,key]`, `[cert,key,pass]`), `transport: "sse"`, all sharing
  the SSRF pre-check and lifecycle.
- **Redirect/origin policy.** `redirect_guard.py` re-validates every hop (origin
  change, https drop, private/metadata target) via an httpx2 response hook.

**Tests** — `test_mcp_oauth.py`, `test_mcp_tls.py`, fixture `oauth_fixture.py`
(offline device-login end-to-end).

**Checks:** tsc pass; vitest 1837; Python 1566.

**Limitations:** the interactive authorization-code path is wired through the SDK
provider (bridge-backed store + caller handlers) and tested at that seam; the SDK
refuses to build its OAuth URLs over plain http (RFC 8252 https requirement), so
the interactive browser leg remains a documented manual step over https. The
device flow is covered end-to-end offline.

## Milestone 4 — Capability surface: resources, prompts, subscriptions

**Status:** complete for resources + prompts; **subscriptions documented as a
non-goal** (see below).

**What changed**

- `client.py` discovers capabilities from `initialize` and lists resources/prompts
  only when advertised; `read_resource`/`get_prompt` are bounded and
  capability-aware.
- `manager._register_utilities` registers `list_resources`/`read_resource`/
  `list_prompts`/`get_prompt` per server **only** when the live session advertises
  the capability AND `tools.resources`/`tools.prompts` is set (default off). A
  resource URI scheme allowlist refuses `javascript:` etc. Prompt text is returned
  as inert data. Status exposes `capabilities`/`resources`/`prompts`.
- Fixture `fastmcp_fixture.py` gained a resource and a prompt.

**Subscriptions: non-goal (honest).** Implemented only if ownership, rate
limiting, a bounded queue, a drop-oldest policy with an honest drop count, and a
decision that a notification triggers nothing all hold. Rather than invent a
second event bus, subscriptions are **not implemented**; a notification cannot
trigger a run or a write. Recorded in the ADR.

**Tests** — `test_mcp_resources_prompts.py` (advertised-vs-enabled matrix, bounded
labelled resource read, inert prompt, URI authorization, no-resources server).

**Checks:** tsc pass; vitest 1837; Python 1566.

## Milestone 5 — Server-initiated interactions: sampling and elicitation

**Status:** complete.

**What changed** — `interactions.py`: `SamplingPolicy` (off by default per
server), `build_sampling_callback` (max-tokens/RPM caps, max tool rounds, timeout,
audit counters, a harness event; refuses when disabled or unbound), and
`build_elicitation_callback` (form-mode routes through the approval authorizer;
URL-mode declined; per-call consent, never remembered). Wired into the
`ClientSession`; counters surface in `lifecycle.interactions`.

**Tests** — `test_mcp_sampling.py`, `test_mcp_injection_adversarial.py`
(disabled-refusal, RPM cap, approval routing, URL-mode decline, adversarial
content changes no state, no standing approval).

**Checks:** tsc pass; vitest 1837; Python 1566.

**Limitations:** sampling runs on the runtime's own model adapter; when a server
requests sampling during a run the run's model serves it, capped by the policy.
Outside a run (no run model bound) a request is refused with
`mcp_sampling_unavailable` — honest, never a fake model.

## Milestone 6 — MCP-aware source planning and the finance product layer

**Status:** complete (planning primitives + presets + install + audit).

**What changed**

- `mcp_retrieval.py`: `SourceCandidate` with provider-independent provenance,
  three distinct freshness states (`fresh`/`stale`/`missing`) plus `failed`,
  `plan_candidates` (prefer the fresher eligible source; **preserve conflicts**),
  and `build_mcp_retrieval_source` (a `RetrievalSource` adapter for a declared
  MCP tool; a generic tool stays directly callable).
- `presets.py`: replaced `mcp.example.com` placeholders with real endpoints
  (Twelve Data, Atlassian, Notion remote) plus a real SEC-EDGAR community package;
  `verified_at`/`verified_against` (auto-defaulted, never absent); `oauth` flag;
  `integration_to_config` and an operator-gated
  `POST /mcp/integrations/{id}/install` (writes a DISABLED, nothing-selected entry).
- `audit.py`: a read-only, offline supply-chain report over preset/configured
  packages with an unpinned flag and a last-checked date; `GET /mcp/supply-chain`.

**Tests** — `test_mcp_source_planning.py`, `test_mcp_presets.py`.

**Checks:** tsc pass; vitest 1837; Python 1566.

**Limitations:** none outstanding for this milestone — a declared MCP data tool
is now planned by the REAL retrieval layer (`FinancialRetrievalLayer` receives
`mcp_sources` from the run's MCP manager, and `plan_retrieval` considers the
declared source before generic web). An undeclared MCP tool stays directly
callable and is never forced through the contract. Provenance stays
`secondary`/`eclipseVerified=false`; a JDdS result is never upgraded.

## Milestone 7 — Eclipse as an MCP server (closes 5H)

**Status:** complete for the narrow read-only surface.

**What changed** — `server_exposure.py`: its own bearer auth
(`HARNESS_MCP_SERVER_TOKEN`, distinct from the operator secret; unconfigured =
disabled, not open), a narrow read-only surface (`eclipse_status`,
`eclipse_list_receipts`, `eclipse_get_receipt`) reading through the existing
service, bounded pagination, structured errors naming the rule, a recorded
protocol version (`2025-11-25`), a schema-hygiene guard (no secret/env/vault key),
and an ASGI app refusing an unauthenticated request with 401.

**Interop transcript (Hermes, real machine):**
```
$ hermes mcp test eclipse-interop
  Transport: HTTP → http://127.0.0.1:8799/mcp
    Authorization: ***
  ✓ Connected (1031ms)
  ✓ Tools discovered: 3
    eclipse_status / eclipse_list_receipts / eclipse_get_receipt
```
Hermes config/env were restored afterwards.

**Tests** — `test_mcp_server_exposure.py` (schema hygiene, pagination bound,
structured error, auth matrix, an offline SDK client listing/calling a tool over
Streamable HTTP, a SECOND offline client over SSE, and an unauthenticated 401).

**Checks:** tsc pass; vitest 1837; Python 1566.

## Milestone 8 — Operations, measurement, and honest documentation

**Status:** complete.

**What changed**

- Adversarial suite `test_mcp_adversarial.py`: credential isolation (echoed token
  → `***`), catalog flood bounded, oversized output truncated+labelled, malformed
  schema, duplicate names distinct, mid-call death honest, cancelled run no hang,
  and a context-growth measurement.
- **Context-growth numbers** (measured, real MCPServer tool schemas):
  1 tool ≈ 258 chars (~64 tokens); 10 ≈ 2,580 (~645); 50 ≈ 12,980 (~3,245);
  200 ≈ 52,180 (~13,045). A 200-tool server costs ~13k tokens of schema — real but
  bounded by `maxTools` (default 200) and the include/exclude filters; lazy mode
  avoids the boot cost. Mitigation: filters + `maxTools` + lazy.
- Metrics/health surface: `lifecycle.metrics.` (calls/errors/avgLatencyMs),
  reconnect counts, last error code, keepalive failures, sampling/elicitation
  consumption, approval counts (existing) — all content-free.
- Graceful degradation: `MCP_AVAILABLE` guards; when `mcp` is not importable the
  service returns honest `unavailable` states and never boots a fake agent;
  `doctor.js` still probes `import mcp`. Test `test_mcp_graceful_degradation.py`.
- Docs: architecture MCP section, `mcp/__init__.py` docstring, NAVIGATION rows,
  and ADRs H67–H72.

**Checks (final):** `npx tsc --noEmit` pass; vitest **1837 passed**; Python
**1566 passed** (baseline 1446 → +120). `jdds.db` untouched by this work.

**Post-close-out completion (2026-09-29).** The three deferred seams were closed:
(1) M6 — declared MCP data tools now flow into the REAL retrieval layer via
`mcp_manager`→`ToolContext`→`FinancialRetrievalLayer(mcp_sources=...)` and
`plan_retrieval(additional_sources=...)`; (2) M5 — server sampling runs on the
run's OWN model adapter via `AgenticService._sampling_model_factory`; (3) M7 — a
second offline client (SSE transport) added alongside the Streamable-HTTP client.
M3's authorization-code path remains a documented manual https step (the SDK
refuses plain-http OAuth URLs); the construction seam is tested. New ADR: H73.

**Limitations (all phases):** see the per-milestone notes. Nothing is fabricated;
every unimplemented seam is stated rather than stubbed.

