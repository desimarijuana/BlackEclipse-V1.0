---
title: Eclipse MCP Phase 6.1 — UI Parity, Round-Trip Integrity, Leftovers
status: Current
last-verified: 2026-09-30
---

# Eclipse MCP Phase 6.1 — Progress

Implementation log for the milestones in the Phase 6.1 prompt. Phase 6 shipped
server-side and green; this phase fixes what it left broken at the front door and
in the settings UI. The Python runtime remains authoritative; Next.js is the
front door. Source code is authoritative wherever the prompt disagrees with it.

## Milestone 0 — Audit, baseline, red test

**Baseline checks (2026-09-29, vendored Python, `Black-Eclipse-site/`):**

| Check | Result |
|---|---|
| `npx tsc --noEmit` | pass (exit 0) |
| `npx vitest run` | **1837 passed / 148 files** |
| `python -m pytest python/tests/` | **1566 passed** |
| `npm run test` | (run at end of phase) |

Working tree at start contained unrelated user changes (`jdds.db`,
`public/geo/world.geo.json`, `scripts/fetch-world-geo.mjs`,
`docs/investor-eye-architecture.md`) plus the Phase-6 change set. None were
touched. `jdds.db` was already modified for unrelated reasons and is left as
found.

**Bug reproduction (verified against the current tree).** With `MCPServerConfig`
`x` persisted fully, then `upsert_mcp_config` applied with a partial config
shaped exactly like the current UI payload:

```
field                     before (operator)                 after a UI save
trust                     untrusted                         full
lazy                      True                              False
keepalive_interval        60                                None
client_cert               /c.pem                            None
tools                     {'resources': True, 'prompts': True}   {}
data_source_tools         {'get_quote': 'quote'}            {}
tool_effects              {'get_quote': 'read'}             {}
confirmed_catalog_digest  abc123                            None
max_tools                 25                                200
selected_tools            ['get_quote']                     ['get_quote']
```

Confirmed: one edit-and-save silently downgrades `untrusted` -> `full`, disables
resources/prompts, drops the MCP->native data-source declaration, discards every
tool effect, and invalidates the catalog confirmation.

**Cause (both halves confirmed in source):**

1. `MCPServerInput` (TS) and `draftToPayload` (UI) carry only the Phase-5E field
   set, so every Phase-6 field is absent from the POST body.
2. `upsert_mcp_config` (`python/harness/mcp/config.py:603`) reconstructs the
   server from the incoming model, i.e. absent means default. Only `env` is
   preserved. `model_fields_set` is never consulted.

**Field inventory (confirmed against `public_dict()` and `MCPServerView`):**

- `public_dict()` emits, and TS `MCPServerView` does NOT carry: `trust`,
  `untrusted`, `selectedTools` object form, `toolEffects` editable form,
  `confirmedCatalogDigest` (is carried but `dataSourceTools` etc. not),
  `lazy`, `keepaliveInterval`, `idleTimeoutSeconds`, `maxLifetimeSeconds`,
  `sslVerify`, `clientCertConfigured`, `tools`.
- `MCPServerInput` omits every one of those plus `trust`, `selectedTools` object
  form, `tools`, `lazy`, the keepalive/idle/lifetime trio, `sslVerify`,
  `clientCert`, `clientKey`.
- `MCPServerState` (TS) misses `"lazy"` and `"unavailable"`. Manager emits
  `lazy`, `unavailable`, `closed`, `connected`, `disabled`, `pending`,
  `failed`, `failed_refused`.
- `MCPTransport` misses `"sse"`.
- `MCPAuthView.kind` misses `"oauth"`; `config.py:254` accepts
  `header | query | oauth`.
- `MCPIntegrationView` misses `verified_at`, `verified_against`, `oauth`.
  `IntegrationSpec.to_public()` is `asdict`, so they are already on the wire.

**Red test (Milestone 0 deliverable).** `python/tests/test_mcp_config_roundtrip.py`
was written first and is red on the current code: **6 failed, 8 passed**. The
failing set is the safety contract (`test_partial_upsert_preserves_every_omitted_field`,
`test_absent_field_is_not_sent_by_a_subset_caller`,
`test_omission_cannot_widen_trust_or_effects`,
`test_omission_cannot_drop_data_source_or_confirmation`,
`test_install_reinstall_does_not_reset_user_changes`,
`test_public_dict_round_trip_is_identity_for_surviving_keys`). The wire-shape
failure is representative:

```
E   AssertionError: wire key 'limits' did not survive a round trip
E   {'outputLimitBytes': 100000} != {'outputLimitBytes': 50000}
E   {'maxTools': 200} != {'maxTools': 25}
E   {'startupTimeoutMs': 10000} != {'startupTimeoutMs': 5000}
```

`test_confirm_preserves_everything_else` already passes: the confirm route loads
the stored config and `model_copy`s one field, so it preserves the rest. The
install/re-install path is red because `install_mcp_integration` builds a fresh
default config and upserts it, resetting prior user changes.

**Other write paths checked (requirement 6):**

- `service.install_mcp_integration` -> `upsert_mcp_config(MCPServerConfig(**entry))`
  with a fresh default config; re-install resets user changes (red test added).
- `POST /mcp/servers/{id}/confirm` -> `target.model_copy(update={...})` then
  `upsert_mcp_config`; preserves everything else (green test added).

**Existing tests asserting old semantics (blast radius, requirement 7):**
`test_mcp.py::test_config_roundtrip_upsert_and_remove` asserts that upserting
`MCPServerConfig(id="a", command="python", enabled=False)` over a stored config
turns `enabled` off. Under preserve-on-absent, `enabled` IS explicitly present
(`False` is a supplied value), so that assertion remains valid and unchanged. No
existing test asserts replace-all for an omitted field; the blast radius is
limited to the new behavior the current code never had.

## Milestone 1 — Round-trip integrity (security downgrade fixed)

**Status:** complete. The M0 red test is green (**14 passed**).

**What changed**

- **Python (the guarantee).** `upsert_mcp_config` preserves every field of the
  stored server not present in the incoming model's `model_fields_set` (never
  `if value is not None`), keeping the documented `env`/`env_keys` merge intact.
  `public_dict()` now also emits the raw operator-set bounds
  (`startupTimeoutMs`/`catalogTimeoutMs`/`callTimeoutMs`/`outputLimitBytes`/
  `maxConcurrency`/`maxTools`) so a view->model->view round trip is lossless;
  the clamped values remain under `limits`.
- **Install.** `AgenticService.install_mcp_integration` is create-if-absent:
  re-installing a preset leaves an existing (possibly user-modified) entry
  untouched and returns `alreadyInstalled: true`.
- **TS.** `MCPServerView`/`MCPServerInput` carry every inventory field with the
  exact camelCase names; `selectedTools` accepts both shapes; `sslVerify` is
  `boolean | "custom-ca"` on the view and `boolean | string` on the input;
  `clientCertConfigured` is the only certificate fact echoed.
- **One mapping module.** `src/lib/harness/mcp-draft.ts` owns
  `draftFromServer`/`draftToInput` (and `emptyDraft`, `selectedToolNames`);
  `mcp-settings.tsx` uses them. `mcp-draft.test.ts` proves the round trip is
  field-complete (11 tests).

**Blast radius (requirement 7).** One existing test relied on the old
replace-all semantics: `test_mcp_api.py::test_annotation_only_server_activates_after_confirm`
popped `tool_effects` and relied on an earlier test's declaration being wiped by a
module-scoped shared config. Under preserve-on-absent the declaration survives, so
the test now clears the effect **explicitly** (`body["tool_effects"] = {}`) — which
is the correct way to say "annotation only" under the new contract. No other test
asserted replace-all for an omitted field; `test_mcp.py::test_config_roundtrip_upsert_and_remove`
still passes because `enabled=False` is explicitly present.

**Evidence.** `test_mcp_config_roundtrip.py` — 14 passed (preserve/clear matrix,
authority-widening invariants, idempotent re-save byte-stable, install/confirm
preserve). `mcp-draft.test.ts` — 11 passed.

**Checks (after M1):** `tsc` exit 0; vitest 1848 passed / 149 files; Python 1566.

## Milestone 2 — Wire and client completeness

**Status:** complete.

- `MCPServerState` gains `"lazy"` and `"unavailable"` (and `failed_refused`);
  `stateDot` labels each honestly (lazy is "cached, not connected"; unavailable is
  "Runtime unavailable", not a server failure).
- `MCPTransport` gains `"sse"`; the editor transport select adds the option with
  help text distinguishing it from Streamable HTTP.
- `MCPAuthView.kind` gains `"oauth"`; the auth select adds it and hides the
  secret-ref/name/prefix fields (an OAuth server needs no vault secret). The
  runtime validator already accepts `kind: "oauth"`.
- `installMCPIntegration` and `getMCPSupplyChain` added to `mcp-client.ts`;
  `MCPIntegrationView` gains `verified_at`/`verified_against`/`oauth`.

**Checks (after M2):** `tsc` exit 0 (unchanged baselines).

## Milestone 3 — Editor reachability

**Status:** complete. `ServerEditor` (+ `Panel`/`EffectBadge`/`stateDot`) and a
`MCPLifecyclePanel` were extracted to `src/components/screens/mcp/`; the screen
file stays composition. The editor covers, grouped and collapsible: trust tier,
tool filters (list or include/exclude), per-tool effects, native data sources,
capability toggles + resource-scheme narrowing, lifecycle (lazy/keepalive/idle/
lifetime), TLS/mTLS (never echoing a stored value, with an explicit clear), the
limits (defaults stated inline) and OAuth (sign in/out with device-flow
`verificationUri`/`userCode`). Every value round-trips via `mcp-draft`.

**Checks:** `tsc` exit 0; vitest 1848.

## Milestone 4 — Status, lifecycle and approvals

**Status:** complete. The server card renders the runtime's bounded `lifecycle`
block (connect attempts, reconnects, in-flight, keepalive failures, last error
code, recycled reason, retry budget, metrics trio) with an explicit "unknown" when
omitted, a lazy/cached state distinct from connected, the advertised-vs-enabled
capabilities, and sampling/elicitation consumption. The approvals panel filters by
status (pending/approved/denied/expired/all) and renders `actionSummary`,
`affectedData`, `risk`, `decidedBy`, `reason`, `expiresAt` and `requestedByRunId`;
no bulk/standing approval. A malformed config entry is now shown loudly with its
message and a recovery note.

## Milestone 5 — Product surface: install, supply chain, presets

**Status:** complete. Front-door routes
`POST /api/harness/mcp/integrations/[id]/install` and
`GET /api/harness/mcp/supply-chain` follow the confirm route pattern
(`guardMutation` + 503 envelope). The wizard installs a preset and states plainly
that the entry was written disabled with nothing selected and what to do next.
Integration cards show `verified`/`verified_at`/`verified_against`, the community
and OAuth flags, and notes; an unverified entry reads as a template. A read-only
supply-chain panel renders the offline report and says so when empty.
`mcp-servers.example.json` now demonstrates every Phase-6 key, validated by
`test_mcp_example_config.py` (3 tests). The route has
`route.test.ts` (3 tests: forward, 503, cross-origin 403).

## Milestone 6 — Python leftovers and the god-file split

**Status:** complete.

- **A11 non-text content.** `client._normalize_result` reports MIME type and
  decoded byte size for image/audio blocks (`"[image content omitted: image/png,
  ~240 bytes]"` plus a `nonTextContent` metadata list) — the bytes themselves are
  never carried. The run result path is text + structured JSON only, so a binary
  transport is a **documented non-goal**: metadata is as far as the current path
  honestly supports. Test
  `test_non_text_content_reports_mime_and_size_not_opaque_omission`.
- **A12 resource schemes.** Optional per-server `resource_schemes` narrows the
  URI schemes a server may read; `effective_resource_schemes` intersects with the
  global allowlist (a hard ceiling), so narrowing can only ever remove a scheme.
  Tests prove a narrowed server cannot read outside its list and that the global
  ceiling still applies. Surfaced in the editor and the example config.
- **A9 split.** `manager.py` (1579 -> 1226 lines) pure-extracted, no behavior
  change: `runtime.py` (`_ServerRuntime` + descriptors + pure helpers),
  `introspection.py` (`IntrospectionMixin`), `oauth_flow.py` (`OAuthFlowMixin`).
  `MCPManager` remains the facade and re-exports the moved names, so the tested
  import/patch surface (`harness.mcp.manager`) is unchanged. Proven by the
  existing suite, not new tests.

**Blast-radius note (screening).** The example-config test exposed that the static
screen refused any `${` in args, but `${VAR}` interpolation is a supported
Phase-6 feature. `_contains_control` now strips a recognized interpolation token
before the control-operator scan (a residual `${` such as `${evil $(cmd)}` is
still refused). No existing test asserted that interpolation must be refused.

**Final checks (2026-09-30):** `npx tsc --noEmit` exit 0; `npx vitest run`
**1851 passed / 150 files** (baseline 1837/148; +14, +2 files); Python
**1587 passed** (baseline 1566; +21). `npm run test` runs vitest + the Python
suite. `jdds.db` untouched by this work (still modified in the tree for unrelated
reasons, left exactly as found).

**Limitations.** The interactive OAuth authorization-code browser leg remains the
Phase-6 documented manual https step; the device flow is wired in the UI. A
non-text MCP result carries metadata only (no binary transport). The supply-chain
report is offline-only. `resource_schemes` is a narrowing; `_ALLOWED_RESOURCE_SCHEMES`
remains the ceiling.

**Correction (2026-09-30, MCP integrity).** Any earlier impression that
"connected" or the **Test** action means a server is verified is **wrong**. Test
only proves the process started and listed tools; a server can be connected and
reject every call. Credential proof is the separate operator-triggered **Verify**
action. See `docs/harness/mcp-integrity-progress.md` and ADR-H77/H78.

**Superseded by (2026-09-30, continuation).** The editor/card now report an
exclude-mode manual selection shadowed by the live globs, and the lifecycle panel
shows the circuit-breaker state; the current state is in
`docs/harness/mcp-integrity-progress.md` and ADR-H81–H84.

**Addendum (2026-09-30, engineering hardening).** The four items above were
revisited: non-text results now state that content exists and was not shown; the
supply-chain report is explicitly `offlineOnly`/`upstreamChecked: false` and its
date is a review date, not a live check; `resource_schemes` reachability was
verified end-to-end; and the OAuth authorization-code leg keeps its named
unblocking condition (a local https callback or a hosted redirect URI). See
`docs/harness/engineering-hardening-progress.md` Phase 6.
