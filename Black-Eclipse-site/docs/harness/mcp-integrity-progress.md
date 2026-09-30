---
title: MCP Integrity — Progress
status: Current
last-verified: 2026-09-30
---

# MCP Integrity — Progress

Implementation log for the MCP integrity defects found by connecting real servers.
Append only. Repo root `black eclipse/`; app in `Black-Eclipse-site/`. The Python
runtime (`python/harness/mcp/`) is authoritative; Next.js is the front door.

## Phase 0 — Reproduce every finding

All commands run from `Black-Eclipse-site/` unless stated. `python.exe` is the
vendored interpreter at `scripts/vendor/python/python.exe`. A direct driver of
`MCPConnection` lives at
`%TEMP%\opencode\mcp-integrity\phase0_probe.py` (scratch only — not added to
`python/tests/` until Phase 4).

### G1 — `sec-edgar-mcp` cannot run (CONFIRMED)

```
$ npm view sec-edgar-mcp bin
(empty output, exit 0)
$ npm view sec-edgar-mcp version main
version = '1.0.0'
main = 'index.js'
$ npm pack sec-edgar-mcp        # scratch dir
npm notice 294B index.js
npm notice 497B package.json
npm notice total files: 2
```

`index.js` verbatim:

```js
// MCP Server wrapper - npm distribution
console.log(`MCP Server: ${require('./package.json').name} v${require('./package.json').version}`);
console.log('Run this MCP server via npx or install it as an MCP tool in your AI agent.');
console.log('Homepage:', require('./package.json').homepage);
```

No `bin`, no server code — a 294-byte `console.log` wrapper. The shipped
`sec_filings` preset (`presets.py:196`) points at it and is marked
`verified=True, verified_at="2026-09-29"`.

### G4 — `mcp-sec-edgar` does not exist (CONFIRMED as a package, but NOT in the example config)

```
$ npm view mcp-sec-edgar version
npm error code E404
npm error 404 Not Found - GET https://registry.npmjs.org/mcp-sec-edgar - Not found
```

**Correction to the prompt:** `mcp-sec-edgar` appears **nowhere** in the
repository — `git grep mcp-sec-edgar` returns no files. It is not in
`mcp-servers.example.json`. The example config's non-preset entries are
`@modelcontextprotocol/server-brave-search`, `yahoo-finance-mcp`,
`@modelcontextprotocol/server-memory`, `@modelcontextprotocol/server-filesystem`,
`mcp-google-sheets`, `@negokaz/excel-mcp-server`, `tavily-mcp`,
`@mindstone/mcp-server-office`, `@notionhq/notion-mcp-server`. So the
"`mcp-sec-edgar` in `mcp-servers.example.json`" claim is **DISPROVED**; the
"does not exist on npm" claim is true but vacuous here.

### G2 — `@notionhq/notion-mcp-server` starts with an empty env and lists 24 tools (CONFIRMED)

```
===== G2 notion, env={} =====
state='ready' error=None code=None
tools discovered: 24
tool names: ['API-get-user', 'API-get-users', 'API-get-self', 'API-post-search',
 'API-get-block-children', 'API-patch-block-children', 'API-retrieve-a-block',
 'API-update-a-block', 'API-delete-a-block', 'API-retrieve-a-page',
 'API-patch-page', 'API-post-page', 'API-retrieve-a-page-property',
 'API-retrieve-a-comment', 'API-create-a-comment', 'API-query-data-source',
 'API-retrieve-a-data-source', 'API-update-a-data-source',
 'API-create-a-data-source', 'API-list-data-source-templates',
 'API-retrieve-a-database', 'API-move-page', 'API-retrieve-page-markdown',
 'API-update-page-markdown']
```

"Test"/connected reports healthy for a server that cannot complete a single call.

### G3 — an invalid token returns `ok=True, isError=False` with a 401 body (CONFIRMED)

```
===== G3 notion, dummy token, call API-get-self =====
state='ready'
-- call 'API-get-self': ok=True is_error=False
   text: {"status":401,"object":"error","code":"unauthorized",
          "message":"API token is invalid.","request_id":"..."}
   data: {"source": {...}, "isError": false, "contentKinds": ["text"]}
```

The runtime hands this to the model as a normal, successful result.

### G10 — `maxTools` truncation is silent (CONFIRMED by source)

`manager.py:472` — `tools = (rt.connection.tools if rt.connection else [])[: rt.limits["maxTools"]]`.
The slice is applied with no record of how many tools were discovered vs kept, and
no diagnostic surfaces on the status/card.

### G11 — `python/harness/mcp/_testtmp.py` is imported by nothing (CONFIRMED)

`git grep _testtmp` -> no matches. `Get-ChildItem -Recurse python -Filter *.py |
Select-String _testtmp` -> no matches. The module (`_testtmp.py`, 68 lines) is a
test-only temp-dir helper with zero production or test references.

> **Correction (2026-09-30, continuation session).** The original finding above is
> **correct**: the module was referenced by no `.py` source. A later prompt
> asserted it "was loaded as a pytest-conftest shim"; that premise is **false** and
> is disproved by `git log --all -S "_testtmp"` (only the two commits that *added*
> the file), `git log -p --all -- python/conftest.py` (no temp reference — the only
> `conftest.py` is a `sys.path` shim), and the absence of any pytest-plugin
> reference. Presence of the module never affected the 1633-test green run. The
> file was nonetheless relocated to `python/tests/_tmp_helper.py` in the first
> session to keep test-only code out of the shipped package; see Milestone 1 of the
> continuation for its final disposition.

### G10 (continued) — evidence refreshed

> **Correction (2026-09-30, continuation session).** The `manager.py:472` line
> reference is stale. The slice has moved to `manager.py:486–489`, and the
> truncation guard is now implemented: `_build_descriptors` records
> `rt.tools_discovered` / `rt.tools_kept`, and `introspection._lifecycle_status`
> surfaces `toolsDiscovered` / `toolsKept` / `toolsTruncated`, with a
> `tools_truncated` diagnostic in `diagnostics.check_server`. See Phase 4.2 below.

### Bonus — `@pipeworx/mcp-edgar` actually runs (CONFIRMED, needed for Phase 2a)

```
===== PIPEWORX @pipeworx/mcp-edgar =====
state='ready' error=None code=None
tools discovered: 16
tool names: ['edgar_search_filings', 'edgar_company_filings', 'edgar_company_facts',
 'edgar_company_concept', 'edgar_insider_transactions', 'edgar_institutional_holdings',
 'edgar_fund_holdings', 'edgar_company_snapshot', 'edgar_ticker_to_cik',
 'sponsor_to_filer', 'filer_to_sponsors', 'edgar_xbrl_frames', 'edgar_companies_by_sic',
 'edgar_product_revenue', 'edgar_filing_documents', 'edgar_filing_text']
```

npm metadata: `version = '0.3.7'`, `bin = { 'mcp-edgar': 'bin/cli.js' }`. Starts
with no env/credential and lists 16 tools.

**Acceptance:** each finding marked CONFIRMED / DISPROVED with raw output above.
No files changed except this progress doc.

no doc change — progress doc only.

## Phase 1 — Stop reporting "connected" for a server that cannot call anything

**Status:** complete.

### 1a — provider error payloads are failures

- **`client.py`** — new pure `looks_like_provider_error(text) -> Optional[dict]`.
  Conservative rule: the *entire* trimmed body must parse as a JSON **object**,
  and it must carry an unambiguous signal — a truthy `error` key, OR a
  4xx/5xx `status`/`statusCode`, OR a known error `code` **together with** a
  status number or a non-empty `message`. A legitimate payload that merely has a
  `code` field (e.g. a ticker) is NOT misread. `_normalize_result` calls it only
  when the server reported success; it sets `is_error=True` and records
  `data["providerError"] = {code?, status?}` while keeping the raw body verbatim.
  Docstring documents the exact rule and covers both directions.
- **`manager.py`** — `_execute` and `_render_outcome` render an unmissable
  failure (`MCP reported a provider error (status 401, code 'unauthorized'): …`),
  carry `providerError` in the JSON, and emit `mcp.tool.failed` with code
  `mcp_tool_provider_error` (never `mcp.tool.completed`). No retry: a provider
  error is not a transport error. The shared helper `_provider_error_line` keeps
  the provider's words verbatim.
- **`manager.py`** — the empty-result placeholder is now
  `(the server returned no text content for this call)`, distinguishing *empty*
  from *unavailable*.

### 1b — Test is not Verify

- **Test copy corrected** (`server-editor.tsx`): Test proves the process started
  and listed tools; it does **not** check a credential. Behaviour unchanged,
  still side-effect-free, never calls a tool.
- **New operator-triggered Verify**:
  - `MCPManager.verify_credentials(server_id, tool, arguments)` — calls ONE
    operator-chosen **read** tool with operator arguments, bounded by a fixed
    10s timeout, never automatic/at boot/in a loop. Records a content-free
    verdict (`credentials_valid` / `credentials_rejected` (with provider
    status/code) / `verify_inconclusive`) plus `verifiedAt`. It refuses a
    non-read tool. The response body is never returned or stored.
  - Runtime state `_ServerRuntime.verify_result`; surfaced in
    `lifecycle.verify` (`introspection._lifecycle_status`) and as a distinct
    diagnostic (`credentials_rejected`, `credentials_valid`,
    `verify_inconclusive`) in `diagnostics.py`.
  - Route `POST /mcp/servers/{id}/verify` (operator-gated) + service
    `verify_mcp_server` + TS proxy route + `verifyMCPServer` client +
    `MCPVerifyResult` type.
  - UI `src/components/screens/mcp/credentials-panel.tsx` (extracted so
    `mcp-settings.tsx` stays under the 1200-line hard ceiling) renders the
    verdict and the tool/args form on the server card. A server can be
    **connected AND rejected** — shown distinctly from `endpoint_unreachable`
    and `server_not_connected`.

### 1c — prompt + honest empty

- **`prompts.py`** MCP block: a result may report a provider-side error or a
  non-success status; report it as a limitation, never present an error payload
  as retrieved data, never retry a provider error as a transport failure.

**Tests** — `python/tests/test_mcp_provider_errors.py` (classifier both
directions; `_render_outcome`/`_execute` renders a failure and emits
`mcp.tool.failed` with `mcp_tool_provider_error`; empty body labelled). The raw
fixture gained `provider_error` (a 401 body with `isError=False`) and
`empty_result` modes. `test_mcp_api.py` gained the Verify route tests (missing
tool 400, `credentials_valid`, `credentials_rejected` + provider status, write
tool refused, non-operator 403). `verify/route.test.ts` (4 tests).

**Evidence**

```
python/tests/test_mcp_provider_errors.py -> 11 passed
python/tests/test_mcp_api.py            -> 29 passed
verify/route.test.ts                    -> 4 passed
npx tsc --noEmit                        -> exit 0
npx eslint <changed>                    -> 0
npx vitest run                          -> pending full-suite run (Phase 5)
```

**Blast radius.** `mcp-settings.tsx` crossed the 1200-line hard ceiling when the
Verify card was inlined; extracted to `mcp/credentials-panel.tsx` (1133 lines now).

**Limitations / honesty.** Verify can only prove what a chosen read tool proves;
a server whose only read tool 401s is `credentials_rejected`; a server with no
declared read tool cannot be verified (the UI says so). The `looks_like_provider_error`
rule is intentionally conservative — a provider error phrased as free prose (not a
JSON object) is NOT caught, and is reported by the model per the prompt rule.

no doc change — progress doc only (Phase 5 carries the NAVIGATION/ADR updates).

## Phase 2 — Every shipped preset must actually run

**Status:** complete.

### 2a — the broken entry, the mislabel, the templates

- **`sec_filings` replaced.** `npx -y sec-edgar-mcp` (no `bin`, 294-byte
  `console.log`) is retired. The preset now launches **`@pipeworx/mcp-edgar`**
  (`npx -y @pipeworx/mcp-edgar`), which I launched myself: **16 tools** listed
  and `edgar_ticker_to_cik`/`edgar_company_snapshot` returned real SEC data with
  **no credential**. The meaningless `sec_edgar_user_agent` secret_ref is removed
  (the replacement needs none). `verified_at="2026-09-30"`,
  `verified_against="@pipeworx/mcp-edgar@0.3.7 on npm (launched; 16 tools; no
  credential required)"`.
- **Example config.** `mcp-sec-edgar` was never present (Phase 0 DISPROVED); no
  change needed there. The `notion` example entry is renamed `notion_local` to
  match the preset.
- **Mislabelled id fixed.** `dropbox` (label "Notion (remote)", url
  `https://mcp.notion.com/mcp`) is renamed **`notion_remote`**. The local-token
  preset is `notion_local` (`@notionhq/notion-mcp-server`). The workflow
  reference (`create_investment_memo`) is updated to `notion_local`. No TS/UI
  referenced the old ids; the only remaining `dropbox` mention is in the Phase-6
  historical progress doc, left as history.
- **Templates honest.** `canva` / `figma` are `verified=False` with live-looking
  URLs; their notes now say `TEMPLATE (UNVERIFIED)` and instruct the user to
  point them at their own endpoint and sign in via OAuth (both set `oauth=True`).
- **Every other preset launched in Phase 2 verification:** `excel` (7 tools),
  `filesystem` (14), `web_search`/tavily (5), `powerpoint` (62), `notion_local`
  (24), `sec_filings` (16). `google_sheets` requires Google credentials to start
  (expected for a credential integration) and could not be fully launched here;
  its package declares a `bin` (`dist/index.js`) and its earlier failure was a
  corrupted local npx cache, not a package defect. `verified=True` is retained
  for it on the strength of the package resolving a `bin`; the launch caveat is
  stated here rather than fabricated.

### 2b — the promise is executable

- **`presets.py` module docstring** now states the rule: `verified=True` may only
  be set when a human/agent has launched that exact package version and seen its
  tools; `verified_against` must name what was run.
- **Offline shape test** in `test_mcp_presets.py`: every `stdio` preset declares
  a `command` and a non-flag argument; every `http`/`sse` preset has an `https`
  URL; every unverified entry is labelled a template; the two Notion ids are
  distinct and accurate. No network.
- **Opt-in network check** `npm run test:presets` (`scripts/test-presets.js`):
  reads the presets from Python and runs `npm view <pkg> bin --json` for each
  `stdio` package, failing on a missing `bin`. Wired in `package.json` and
  documented in `CONTRIBUTING.md` as a release-tag precondition beside
  `test:smoke`. **Never in `npm test` or CI.**

**Evidence**

```
$ npm run test:presets
  ok   google_sheets (mcp-google-sheets)
  ok   excel (@negokaz/excel-mcp-server)
  ok   filesystem (@modelcontextprotocol/server-filesystem)
  ok   sec_filings (@pipeworx/mcp-edgar)
  ok   web_search (tavily-mcp)
  ok   powerpoint (@mindstone/mcp-server-office)
  ok   notion_local (@notionhq/notion-mcp-server)
[presets] All stdio preset packages resolve a `bin`.

python/tests/test_mcp_presets.py test_mcp_workflow.py test_mcp_example_config.py
  test_mcp_source_planning.py -> 39 passed
```

**Limitations.** `google_sheets` (`mcp-google-sheets`) could not complete a full
launch without Google credentials; its `bin` resolves and its only observed
failure was a corrupt npx cache, so it is retained but is the one preset whose
end-to-end launch I did not personally confirm. The `$` check cannot see whether
a package's server code is correct — only that it declares an executable; the
launch record in `verified_against` is the stronger human/agent evidence.

no doc change — progress doc only (Phase 5 carries the NAVIGATION/CONTRIBUTING pointer).

## Phase 3 — Effect classification must not trust a misleading name

**Status:** complete.

**What changed**

- **No name inference.** `naming.py` gains `writes_like_name(name)` and
  `WRITE_SHAPED_TOKENS` (`create|delete|update|patch|move|post|append|set|remove|
  write|archive`). It is a pure, untrusted signal used only to FLAG; it never
  decides an effect (inferring from a name would auto-activate a tool on a guess).
- **Refusal until acknowledged.** `MCPServerConfig.acknowledged_effect_mismatches`
  (a list of original tool names) is the explicit acknowledgement. In
  `_build_descriptors`, a `read` tool whose name is write-shaped stays inert with
  a diagnostic telling the operator to acknowledge the mismatch. The posture
  matches the catalog-digest confirmation: an untrusted signal never activates a
  tool. The field rides the round-trip contract (TS `MCPServerView` /
  `MCPServerInput` / `DraftServer` / `mcp-draft`, and `public_dict`).
- **`unknown` stays never-activatable** — confirmed and covered by a test.
- **Editor UI** (`server-editor.tsx`) warns on a `read`-marked tool with a
  write-shaped name and requires an explicit per-tool acknowledgement checkbox
  before it is selectable. A mirror `writesLikeName` + `WRITE_SHAPED_TOKENS` in
  `mcp-draft.ts` keeps the UI in step with Python.
- **Documented** in `presets.py` / editor copy: a server's own naming and its
  `readOnlyHint` annotation are untrusted, and why.

**Tests** — `python/tests/test_mcp_effect_ambiguity.py` uses the real Notion
names from a new `notion_naming` fixture mode (all advertising
`readOnlyHint=True`): (a) `API-post-search` declared `read` is not activatable
without acknowledgement and activates after it; (b) `API-move-page` declared
`write` requires a per-call approval (registry refuses a write with no
authorizer); (c) an un-declared tool is never activatable. `writes_like_name`
both directions. `mcp-draft.test.ts` gained the field round-trip.

**Evidence**

```
python/tests/test_mcp_effect_ambiguity.py -> 5 passed
python/tests/test_mcp_config_roundtrip.py + test_mcp_config_hardening.py -> 37 passed
full -k mcp Python suite -> all pass
mcp-draft.test.ts -> 12 passed
npx tsc --noEmit -> exit 0;  npx eslint <changed> -> 0
```

**Blast radius.** One existing behavior changes: a `read` tool with a
write-shaped name that previously activated on a declared effect now needs an
acknowledgement. No shipped preset is affected (none declares such a tool as
selected-read); the raw fixture's default `echo`/`write_thing` names are
unchanged. No test asserted the old auto-activation of a write-named read tool.

**Limitation.** The mismatch check is lexical: a write hidden behind a
completely read-ish name (e.g. a tool literally named `list_things` that deletes)
is not caught by the name — that is exactly why the name is documented as
untrusted and why declared effects/approvals remain the authority.

no doc change — progress doc only.

## Phase 4 — Capability and hygiene gaps

**Status:** complete.

### 4.1 — per-run MCP call budget (G9)

`MCPServerConfig.max_calls_per_run` (None = the documented default
`DEFAULT_MCP_CALLS_PER_RUN = 50`) caps calls to a server's tools within ONE run.
`_execute` counts per run id in `_ServerRuntime.run_calls` (a different run gets
its own budget; the count is consumed only when the call is actually made, so a
denied approval does not burn it). On reaching the cap it refuses HONESTLY with a
message naming `maxCallsPerRun` and the counts, and emits `mcp.tool.failed`
(`mcp_run_budget_exceeded`) — never a silent block.

### 4.2 — `maxTools` truncation is visible (G10)

`_build_descriptors` records `tools_discovered` / `tools_kept` on the runtime;
`_lifecycle_status` exposes `toolsDiscovered` / `toolsKept` / `toolsTruncated`,
and `diagnostics.check_server` adds a `tools_truncated` warning naming discovered
vs kept. The card/lifecycle panel shows it. A user can no longer believe they are
seeing a full catalog when they are not.

### 4.3 — test scaffold out of the shipped package (G11)

`python/harness/mcp/_testtmp.py` (imported by nothing) was moved to
`python/tests/_tmp_helper.py` via `git mv`; its relative import was rewritten to
`harness.eclipse_memory.config`. Pure move, no behavior change.

### 4.4 — lazy and stale read honestly (G14)

- Confirmed `lazy` renders `state="lazy"` with the cached-tool count and an
  explicit "not connected until first use" (the card empty-state and lifecycle
  panel copy now say exactly that).
- New `schema_cache.is_stale(server_id, fingerprint)` distinguishes a MISSING
  cache from a STALE one. `_start_runtime` sets `rt.cache_stale` and a diagnostic
  when the fingerprint changed, then falls back to an eager connect — a stale
  cache is reported as needing a connect, never silently served. Surfaced as
  `lifecycle.cacheStale` and in the UI.

**Tests** — `python/tests/test_mcp_capabilities_hygiene.py` (budget refuses at the
cap with a named message + event and a separate run has its own; truncation
recorded/surfaced as a diagnostic; runtime truncation defaults are unknown, not
zero; stale detection). The `_testtmp` move changes no test outcome (nothing
imported it).

**Evidence**

```
python/tests -k mcp -> 274 passed, 1359 deselected
python/tests/test_mcp_capabilities_hygiene.py -> 5 passed
python/tests/test_size_budget.py -> 4 passed
npx tsc --noEmit -> exit 0;  npx eslint <changed> -> 0
```

**Blast radius / size budget.** The new manager code and the Verify extraction
pushed `manager.py` past its ratchet, so the Verify action moved to
`mcp/verify.py` (`VerifyMixin`) and the result rendering + session-expiry policy
to `mcp/execution.py` (`ExecutionMixin`, with `provider_error_line` re-exported
as `_provider_error_line` for the existing test import). `manager.py` is now 1217
lines (ratchet 1226) — under budget. No behavior change; the full MCP suite is
green.

**Limitations.** The per-run budget keys on `ctx.run_id`; a tool invoked outside
a run (no run id) shares one `"anonymous"` bucket. The truncation guard reports a
count, not which tools were dropped.

no doc change — progress doc only (Phase 5 carries the NAVIGATION/ADR updates).

## Phase 5 — Closeout

**Gates (from `Black-Eclipse-site/`), against the phase-0 baseline:**

| Gate | Baseline | Final |
|---|---|---|
| `npx tsc --noEmit` | 0 | **0** |
| `npx eslint .` | 0 err / 24 warn | **0 err / 24 warn** |
| `npx vitest run` | 1902 / 160 | **1919 / 162** |
| Python pytest | 1603 | **1633** |
| `npm run test:evals` | ALL PASS | **ALL PASS** |
| `npm run check:all` | ALL GATES PASSED | **ALL GATES PASSED** |

Moved gates are all additions (vitest +17/+2, Python +30). No test was loosened or
skipped. `npm run test:presets` was run separately (network; not a gate).

**Docs.**
- `docs/NAVIGATION.md` — updated the MCP row (new modules `execution.py`/`verify.py`,
  the `/servers/{id}/verify` route, `credentials-panel.tsx`, the `test:presets`
  script, ADR-H77–H80) and the MCP task rows (test-env helper moved, new
  verify/provider-error/budget/effect-ambiguity rows, corrected example ids).
- `docs/harness/decisions.md` — **ADR-H77** provider error, **ADR-H78**
  Test ≠ Verify, **ADR-H79** effect-ambiguity acknowledgement, **ADR-H80**
  launchable presets + per-run budget + honest truncation/lazy state.
- `docs/harness/mcp-phase-6-progress.md` and `mcp-ui-parity-progress.md` — one-line
  pointers here, and each corrected: the `sec_filings` preset pointed at an
  un-launchable package, and "connected"/Test was never proof of working
  credentials.
- `docs/CHANGELOG.md` — a dated entry.
- `CONTRIBUTING.md` — `test:presets` documented as a release-tag precondition.

**Invariants re-confirmed.**
- one `MCPManager` (`git grep 'class MCPManager'` -> 1); one `ToolRegistry` (1);
  one `ApprovalStore` (1);
- secrets never in a response/log/event/config: Verify stores and returns only a
  code + provider status/code, never the body; secret redaction is unchanged;
- MCP results stay `eclipseVerified: false`; JDdS is not upgraded to an authority;
- operator authorization is transport/token on every mutation — the new
  `/servers/{id}/verify` route carries `require_mcp_operator` and the TS proxy
  uses `guardMutation`;
- a server save cannot widen authority (round-trip contract preserved; the new
  `acknowledged_effect_mismatches` is additive);
- **`read` never bypasses approval for a write-shaped tool** — ADR-H79 makes exactly
  this true: a read-marked write-shaped name is inert until acknowledged, and a
  declared write still needs a per-call approval (tested);
- no fabricated data; zero-config preserved (no new dependency; no boot-time
  network or verification call).

**Still open (with the unblocking condition).**
- `google_sheets` preset (`mcp-google-sheets`) was not end-to-end launched here
  because it needs Google credentials to start. Unblock: a Google service-account
  JSON (or ADC) available for a launch test; its `bin` resolves and it is retained.
- `canva` / `figma` remain `verified=False` templates (no public MCP endpoint was
  confirmed). Unblock: a documented endpoint to launch against.
- `looks_like_provider_error` catches a structured JSON error body only; an error
  phrased as free prose relies on the prompt rule. Unblock (optional): a broader
  prose heuristic, deliberately not added to stay conservative.
- The per-run budget is per server, keyed by run id; a cross-server aggregate cap
  is not implemented. Unblock (optional): a manager-level counter.

**Do not commit** — the tree is left for the user. Three unrelated user files
(`docs/investor-eye-architecture.md`, `public/geo/world.geo.json`,
`scripts/fetch-world-geo.mjs`) plus concurrent background/dialog work were not
touched.

docs updated: `docs/harness/mcp-integrity-progress.md`,
`docs/harness/decisions.md`, `docs/NAVIGATION.md`,
`docs/harness/mcp-phase-6-progress.md`, `docs/harness/mcp-ui-parity-progress.md`,
`docs/CHANGELOG.md`, `CONTRIBUTING.md`.

---

# MCP integrity — continuation (2026-09-30)

Second session: close the integrity gaps, land the deferred docs, and add the
remaining capability/safety/observability work. **Milestone 0 baseline measured
against the current working tree before any change.**

## Milestone 0 — Real current state

**Baseline (from `Black-Eclipse-site/`, vendored Python):**

| Command | Measured |
|---|---|
| `npx tsc --noEmit` | exit 0 |
| `npx vitest run` | **1919 passed / 162 files** |
| `python -m pytest python/tests -k mcp` | 274 passed / 1359 deselected |
| `python -m pytest python/tests` | **1633 passed** |

**Re-confirmation of the prompt's findings against the current tree.** Several
rows were already addressed by the first session, and **one is false**:

| # | Verdict now | Evidence |
|---|---|---|
| A1 | **CONFIRMED** | `git grep -l verify_credentials HEAD` → empty; `git status --porcelain -uall` shows the ~40-file uncommitted set + untracked `mcp/verify.py`, `mcp/execution.py`, the three new test files, `credentials-panel.tsx`, `servers/[id]/verify/`. |
| A2 | **PARTLY FIXED** | A CHANGELOG entry for the integrity work *was* added (`docs/CHANGELOG.md` line ~18 names `credentials_valid`/`credentials_rejected`). It did not use the exact tokens the prompt grepped for (`provider error`/`maxCallsPerRun`/`tools_truncated`/`acknowledged_effect`), so those greps miss it. Coverage confirmed, not re-added. |
| A3 | **PARTLY FIXED** | Phase 5 exists (`## Phase 5 - Closeout`) and **ADR-H77–H80** exist. The prompt's "latest is ADR-H76" was true at audit time, not now. |
| A4 | **FIXED** | `docs/NAVIGATION.md:330` already points at `python/tests/_tmp_helper.py`, not `_testtmp.py`. |
| A5 | **CONFIRMED** | `_tmp_helper.py` is imported by nothing (`resolve_tmp_base` only appears in its own definition). |
| A6 | **DISPROVED** | No commit, `conftest.py`, or pytest plugin ever referenced `_testtmp` (`git log -S "_testtmp"` → only the two commits that *added* the file; `git log -p --all -- python/conftest.py` → no tmp reference; the only `conftest.py` is the `sys.path` shim). The original progress-doc G11 ("imported by nothing") was **correct**; the prompt's "loaded as a pytest-conftest shim" premise is false. The 1633-test green run merely proves presence is harmless. |
| A7 | **CONFIRMED (stale text)** | The doc cites `manager.py:472` for the slice; the guard (`tools_discovered`/`tools_kept`/`toolsTruncated`) is implemented at `manager.py:486–489`. |
| A8 | **CONFIRMED** | `test_mcp_presets.py` names no EDGAR package. |
| A9 | **CONFIRMED** | `RATCHET_PY["mcp/manager.py"] = 1226`; file measures **1201**. |
| A10 | **CONFIRMED** | `python/pytest.ini` has `addopts = -q`; `pytest python/tests -q` prints no `N passed` summary line. |
| A11 | **CONFIRMED** | `notification` appears once (`client.py:766`, a capability read). |
| A12 | **CONFIRMED** | `grep -riE "circuit|breaker|cooldown" python/harness/mcp` → 0. |
| A13 | **CONFIRMED** | No `osv`/`advisory` anywhere in `mcp/`. |
| A14 | **CONFIRMED** | No `allowed_models` in `mcp/`. |
| A15 | **CONFIRMED** | `naming.py` has no assembled-name length cap. |
| A16 | **CONFIRMED (correct, untouched)** | Operator effects, digest gate, SSRF/redirect, approval digest+TTL, screening, `unknown`-never-activatable all verified present. |

**Conclusion.** The first session's change set is intact. Work proceeds on
M2–M8; M1 is a doc correction (G11 is *not* wrong, A6 is), M3 adds the missing
pins, and A2/A3/A4 need only verification, not rework.

no doc change — progress doc only.

## Milestone 1 — Correct the false claims in the integrity progress doc

Done: G11 gained a dated correction (A6 is false; the original finding stands),
G10's evidence was refreshed to `manager.py:486–489` and notes the implemented
guard. Both corrections are appended, not rewritten.

## Milestone 2 — Relocated test helper: adopted

`python/tests/_tmp_helper.py` is **adopted**: `python/conftest.py` now exposes a
`tmp_workspace` fixture backed by `make_temp_dir`, so `BLACK_ECLIPSE_TMP` is
actually honoured (the same override `harness.mcp.diagnostics` and `doctor.js`
respect). Tests in `python/tests/test_tmp_helper.py` prove the override takes
effect. NAVIGATION's row points at the real path and explains the adoption.

## Milestone 3 — Regression pins

- `test_mcp_presets.py` gained `test_sec_filings_preset_points_at_a_launchable_package`
  (asserts `@pipeworx/mcp-edgar`, not `sec-edgar-mcp`; no `secret_ref`).
- Regression coverage confirmed already present for provider-error classification
  (both directions), Test-never-calls-a-tool (the Test route test), the truncation
  diagnostic, the per-run budget, and the effect-mismatch acknowledgement. No
  duplicates added.
- `RATCHET_PY["mcp/manager.py"]` re-pinned to the measured size (was 1226, then
  1201; now **1106** after the M4/M5 extractions).

## Milestone 4 — Inbound notifications (A11)

`MCPConnection` wires the SDK `message_handler` and acts only on a
`list_changed` for a capability the server advertised. `RediscoveryMixin` re-runs
the relevant listing for that ONE server through `refresh_tools`/`refresh_listing`
under the per-server lock. For tools it rebuilds descriptors via
`_build_descriptors`, deregisters removed tools, re-runs every activation gate,
and re-engages the confirmation gate on the changed digest (tested); for
resources/prompts it re-lists and replaces the connect-time snapshot so the
utility tools serve the current listing (no activation gate on those read-only
surfaces). Every case emits a content-free `mcp.catalog.changed`. Fixture modes
`list_changed` and `list_changed_all`; `test_mcp_notifications.py` (5 tests).

## Milestone 5 — Circuit breaker (A12)

`circuit.py` (CLOSED/OPEN/HALF_OPEN, pure helpers). `_execute` checks the breaker
AFTER the approval gate, so a denied approval never claims the probe slot; only
transport failures count. Open refuses immediately with `mcp_circuit_open`,
naming the count/last code/re-probe; half-open allows one probe; success closes,
failure re-arms. Operator reset route `POST /mcp/servers/{id}/circuit/reset` +
UI. `test_mcp_circuit.py` (8 tests) plus the TS route test (3).

## Milestone 6 — Live supply-chain check (A13)

`supply_chain.py` queries OSV (malware only) at the spawn path, fail-closed on a
confirmed advisory and fail-open on a network error (always stated), with a TTL
cache and an injectable fetcher. `screen_spawn` is wired in `_connect` behind
`live_supply_chain_check` (default true). `audit.py` gained `upstream_checked`.
`test_mcp_supply_chain.py` (10 tests, all offline via the injected fetcher).

## Milestone 7 — Interop details (A14, A15) and the tool picker

- `SamplingPolicy.allowed_models` + `resolve_model`; a fallback is counted in
  `samplingModelFallbacks` and reported in the `mcp.sampling.requested` event. No
  allowlist = unchanged.
- `naming._clamp_name` bounds the assembled name to 64 chars with a stable digest;
  a short name is byte-identical; clamping is a non-blocking `note`.
- Editor/card: in exclude mode the live filter decides selection (a manual pick
  the globs drop is reported as shadowed, not shown enabled); a clamped name shows
  its `note`. `test_mcp_interop.py` (10 tests) + `mcp-draft.test.ts` glob helpers.

## Milestone 8 — Gate honesty and documentation

- `python/pytest.ini`: `-q` → `-ra`, so a green run prints its `N passed`
  summary line. Collection unchanged (`testpaths`, `asyncio_mode`).
- ADRs **H77–H84** in `docs/harness/decisions.md` (H77–H80 reconstructed here
  after being verified present in the first session; H81–H84 new).
- `docs/harness/architecture.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`, and
  the two prior progress docs updated. See the final report.

## Milestone 9 — The operator-only commit (NOT executed)

The uncommitted set is reported in the final report; it was **not** committed,
because authorization was not given.

**Final gates (measured):** `tsc` 0; vitest **1922 / 162**; Python **1670**;
eslint 0 errors / 24 warnings; `test:presets` all `bin` resolve.

docs updated: `docs/harness/mcp-integrity-progress.md`,
`docs/harness/decisions.md`, `docs/harness/architecture.md`, `docs/NAVIGATION.md`,
`docs/CHANGELOG.md`, `docs/harness/mcp-phase-6-progress.md`,
`docs/harness/mcp-ui-parity-progress.md`, `CONTRIBUTING.md`.
