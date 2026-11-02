---
title: Graph Studio — Integration, HTTP & Webhook Node Plan
status: In progress (P0 implemented)
last-verified: 2026-11-01
---

# Integration, HTTP & webhook node improvement plan

**Scope assumption.** "These nodes" is read as the **`integration` category** plus
the **trigger family**. Today that is exactly one integration node
(`integration.http`) and two triggers (`trigger.manual`, `trigger.schedule`).
If you meant the finance/quant/research packs, this plan does not cover them; the
same method applies, but the node specs differ.

**What this document is:** an implementation-ready plan: the verified current
state, the defects, a proposed node catalogue, per-node contracts, the inbound
webhook security model, the cross-layer work, the test matrix, and a ticket-sized
work breakdown.

**What it is not:** a decision record. Items marked **DECISION** need an answer
before the ticket starts. An accepted decision becomes an app-level ADR in
`skills/ARCHITECT.md` (mirrored into `docs/DECISIONS.md`).

## 0. Implementation status (2026-11-01)

| Item | Status | Notes |
| --- | --- | --- |
| HTTP redirect/SSRF fix | **done** | `http_client.py` re-checks every hop, caps redirects, refuses HTTPS→HTTP, redacts logs. |
| `integration.http@1.1.0` | **done** | query/body modes, retries, response cap, `ok`/`headers`/`durationMs`/`truncated`; `1.0.0` stays registered and keeps its output shape. |
| `trigger.webhook@1.0.0` | **done** | zero-config node + `triggerContext` plumbing through run-server → Python service → executor. |
| `WorkflowWebhook` + receipts | **done** | `prisma/schema.prisma`; applied with `prisma db push` (no migration directory in this repo). |
| Public `/api/webhooks/[slug]` | **done** | HMAC + timestamp replay window, token mode, 64 KiB cap, rate limit, idempotency receipt, middleware exemption. |
| Safe/armed authority | **done** | safe = test run; armed pins version + content hash + network grant; write/trading refused; digest re-checked per delivery. |
| Webhook inspector + card | **done** | create/copy/rotate/pause/arm, last delivery/status/error. |
| `integration.webhook_send` | **done** | signed outbound webhook. |
| Test-with-network | **done** | explicit confirmation in the Test tab and card action. |
| Demo templates + seed | **done** | `templates.ts` adds *Webhook to HTTP* and *Signed webhook*; `scripts/seed-integration-demo.mts` seeds both workflows, arms the inbound webhook and writes a signed-request helper. Verified live against postman-echo (inbound run 200; outbound signature echoed). |
| Vault credential refs (P1.3) | not started | env-var references only, as D5 recommended for P0. |
| `integration.graphql` / `integration.mcp_tool` (P2) | not started | catalogue remains generic-first. |
| Dedicated "Respond to webhook" node | deferred | `wait` response mode returns the terminal output. |

Decisions taken as recommended: **D1 A (armed, safe by default)**, **D2 HMAC
default + optional token**, **D3 immediate `202` by default**, **D4 additive
1.1.0**, **D5 env-only for now**, **D7 terminal output, no respond node**.

---

## 1. Current state (verified in the tree before implementation)

> Historical audit. §0 is the live status; the defects below were the baseline
> the implementation closed in P0.

| Area | What exists | Where |
| --- | --- | --- |
| Integration nodes | **One**: `integration.http@1.0.0` | `src/lib/graph-studio/registry.ts:224`, `python/harness/graph_runtime/nodes.py:1008` |
| HTTP methods | GET, POST, PUT, PATCH, DELETE | same |
| Request body | JSON only, from the `body` port or `bodyJson` | `_exec_http` |
| Headers | `headersJson` (plain) + `credentialEnvJson` (header -> ENV var name) | `_custom_headers`, `_credential_headers` |
| Response | `status`, `body` (JSON parsed, else `{text, contentType}`) | `_exec_http` |
| Limits | 1 MB response cap, 60 s timeout, SSRF check, loopback refused | `MAX_HTTP_RESPONSE_BYTES`, `check_outbound_url` |
| Inbound webhooks | `POST /api/workflows/[id]/trigger` only | `src/app/api/workflows/[id]/trigger/route.ts` |
| Webhook node | **None.** There is no `trigger.webhook`; the docs' "all three trigger nodes" is stale | `grep trigger.webhook` = 0 hits |
| Webhook auth | **None.** "Secret-bearing webhook triggers are Phase 8/10 work" | route header comment |
| Webhook envelope | Always a TEST run -> no network/write/trading | `startPersistedRun({ testRun: true })` |
| Node testing | Network nodes are **refused** (403) | `node-test-ui.ts:23`, `/graphs/nodes/test` |
| Contract parity | TS registry -> generated JSON -> Python asserts node-for-node | `npm run graph:manifest`, `registry.manifest.json` |

### 1.1 Defects and gaps

1. **SSRF bypass through redirects (security).** `_exec_http` runs
   `check_outbound_url` on the *initial* URL only. `urllib.request.urlopen`
   follows 3xx redirects by default, so a public URL can redirect to
   `169.254.169.254`, `127.0.0.1`, or a private host with no second check.
2. **A webhook endpoint that requires `CRON_SECRET`.** The trigger route calls
   `guardMutation`; an external service has no `Origin` and is not loopback, so
   the route only works on a local host or with the global cron secret. The new
   endpoint must authenticate itself, not use the mutation guard.
3. **Webhooks cannot act.** Every webhook-triggered run is a test run, so a
   webhook workflow cannot call `integration.http` (network is denied in test
   runs even if granted). The common use case ("payment webhook -> enrich via
   API -> append to a sheet") is impossible today.
4. **No webhook identity.** There is no token, signature, replay window,
   idempotency, method filter, or per-workflow endpoint.
5. **HTTP node is request-only.** No query params, no auth helper, no response
   headers, no `ok`/duration outputs, no retry, no redirect control, no body
   modes (form/text), no response-type control, no truncation policy.
6. **Response fidelity.** A JSON scalar/array is returned as-is but the port is
   declared `object`; non-JSON text is wrapped. Callers cannot tell "2xx with
   empty body" from "request failed" without inspecting `status`.
7. **Log leak.** The executor logs the full URL (`f"{method} {url} -> {status}"`),
   including query strings that may carry a token.
8. **No test path for HTTP.** The integration node cannot be exercised from the
   editor at all, so every change needs a full run.
9. **Docs drift.** `docs/graph-studio.md` claims three trigger nodes and that
   webhooks are Phase 8/10.

---

## 2. Design principles (non-negotiable)

- **One contract, two registries.** Every node is declared in
  `src/lib/graph-studio/registry.ts` (or a split module), mirrored in
  `python/harness/graph_runtime/`, then `npm run graph:manifest` regenerates the
  JSON. Never hand-edit the manifest.
- **The front door authenticates; the runtime executes.** Next.js verifies the
  inbound webhook, resolves the pinned workflow from JDDS, derives grants, and
  calls `startPersistedRun`. Python never reads JDDS.
- **No widening by request.** A webhook request carries a payload, never
  authority. Grants come from the registry + the pinned IR, exactly like an
  operator run.
- **Default deny.** Unknown methods, changed graphs, missing signatures, stale
  timestamps, oversized bodies, and disabled webhooks all fail closed.
- **Reuse, don't rebuild.** Reuse `check_outbound_url`, `runInput` validation,
  `startPersistedRun`, `rateLimit`, `encryptSecret`/`decryptSecret`
  (`src/lib/connectors/secrets.ts`), the schedule-tab pattern, and the operator
  authorization dialog.
- **Additive versioning.** New behaviour lands as a new node version
  (`integration.http@1.1.0`); `1.0.0` stays registered so saved graphs never
  silently change.
- **Small files.** HTTP request mechanics go to a new
  `python/harness/graph_runtime/http_client.py`; the node module stays a
  contract + thin adapter.

---

## 3. Target node catalogue

| Priority | Node | Category | Purpose | Side effect |
| --- | --- | --- | --- | --- |
| **P0** | `integration.http@1.1.0` | integration | Complete outbound HTTP request | `network` |
| **P0** | `trigger.webhook@1.0.0` | trigger | Inbound HTTP webhook (signed) | `none` |
| **P1** | `integration.webhook_send@1.0.0` | integration | Signed outbound webhook delivery | `network` |
| **P2** | `integration.graphql@1.0.0` | integration | Query/mutation with variables | `network` |
| **P2** | `integration.mcp_tool@1.0.0` | integration | Call a configured MCP tool (user-directed) | depends on tool |
| **P2+** | Vendor templates, not node types | — | Slack/Discord/Sheets are starter graphs built from HTTP + auth | — |

**Explicit non-goals for this plan:** a general crawler, long-running socket
nodes (WebSocket/SSE), database connectors, and vendor SDKs. Vendor parity is
achieved with `integration.http` + credential references and a template, so the
registry does not grow one node per SaaS.

---

## 4. P0 — `integration.http@1.1.0`

### 4.1 Contract

**Ports**

| Direction | Id | Type | Notes |
| --- | --- | --- | --- |
| in | `body` | `any` (was `object`) | Wired body wins over `bodyJson` |
| in | `url` | `string`, optional | New; wired URL wins over config |
| out | `status` | `number` | unchanged |
| out | `body` | `any` | unchanged id; JSON as-is, text as string, non-JSON object as `{text, contentType}` |
| out | `headers` | `object` | New; safe response header subset, lowercased |
| out | `ok` | `boolean` | New; `200 <= status < 300` |
| out | `contentType` | `string` | New |
| out | `durationMs` | `number` | New |
| out | `truncated` | `boolean` | New |

Keeping the ids `status` and `body` means every existing edge keeps working.

**Added config (all additive)**

| Key | Kind | Default | Bounds | Meaning |
| --- | --- | --- | --- | --- |
| `queryJson` | json string | `""` | 8 000 chars, 50 keys | Appended to the URL with proper encoding |
| `bodyMode` | enum | `json` | `json \| text \| form` | How the body value is encoded |
| `responseType` | enum | `auto` | `auto \| json \| text` | Parsing policy |
| `maxResponseBytes` | number | `1_000_000` | 1 000..10 000 000 | Response cap |
| `onOversize` | enum | `error` | `error \| truncate` | Cap behaviour |
| `followRedirects` | bool | `false` | — | Manual, re-checked redirects |
| `maxRedirects` | number | `3` | 0..5 | Redirect hop cap |
| `failOnHttpError` | bool | `true` | — | 4xx/5xx raises a node error (new version only) |
| `retries` | number | `0` | 0..3 | Attempts after the first |
| `retryBackoffMs` | number | `500` | 100..10 000 | Base backoff |
| `retryUnsafe` | bool | `false` | — | Allow retrying POST/PATCH |
| `method` | enum | `GET` | + `HEAD`, `OPTIONS` | Extended |

Existing `url`, `bodyJson`, `headersJson`, `credentialEnvJson`, `timeoutMs`
keep their names and meanings.

### 4.2 Semantics

1. **URL resolution:** wired `url` -> config `url`; parse, run
   `check_outbound_url`; merge `queryJson` (existing query params preserved,
   arrays repeat the key, `null` is skipped).
2. **Body resolution:** wired `body` -> `bodyJson` -> none. `json` ->
   `application/json`; `text` -> `text/plain; charset=utf-8`; `form` ->
   `application/x-www-form-urlencoded` (nested values are refused, flat only).
   GET/HEAD/OPTIONS never send a body (a body is ignored with a log line, not a
   silent drop).
3. **Auth:** keep the existing two mechanisms. `headersJson` stays plain and
   refuses sensitive names. `credentialEnvJson` maps `Header -> ENV_VAR`; the
   value is resolved in the runtime and never stored. A UI-only **auth preset**
   (None / Bearer / Basic / API key) writes the corresponding
   `credentialEnvJson` entry; it does **not** add a second config shape.
4. **Response:** read at most `maxResponseBytes + 1`. Over the cap:
   `error` (default) fails the node with the byte limit, `truncate` keeps the
   prefix and sets `truncated: true`. `responseType: auto` parses JSON when the
   content type is JSON or the text starts with `{`/`[`; otherwise returns text.
5. **`failOnHttpError`:** when true, a non-2xx response fails the node with a
   structured error (`status`, `contentType`, bounded preview, `retryable`).
   `ok` is still emitted on success paths. Redirects with
   `followRedirects: false` are not errors; `status` is the 3xx and `headers`
   includes `location`.
6. **Retries:** retry only on network errors, `408`, `429`, and `5xx`; backoff
   `retryBackoffMs * 2^attempt` plus jitter, capped at 10 s; honour `Retry-After`
   when present (cap 10 s). Retry only idempotent methods unless `retryUnsafe`.
   The run's per-node timeout is the outer bound.
7. **Redirects (manual opener):** follow at most `maxRedirects`, re-run
   `check_outbound_url` **on every hop**, refuse an `https -> http` downgrade,
   and refuse a redirect into loopback/private ranges. This closes defect 1.1.
8. **Observability:** one log line per attempt, `METHOD host/path -> status
   (N ms)`; query strings and credential values are redacted. The node also
   emits `durationMs`.

### 4.3 Security checklist

- [ ] SSRF on the initial URL **and every redirect hop**.
- [ ] No embedded credentials in URLs; no loopback from a graph node.
- [ ] Header names/values validated; no CRLF; transport headers refused.
- [ ] Sensitive request headers only through `credentialEnvJson`.
- [ ] Request body cap (1 MB) before sending.
- [ ] Response cap with an explicit `token`/`error` policy.
- [ ] Never log or return credential values or `Set-Cookie`.
- [ ] DNS resolution hardening (optional H1): resolve the host and reject
      private/link-local/loopback answers, with a documented residual TOCTOU
      risk.

### 4.4 UI (`config-fields.ts`, inspector, node card)

- Group fields: **Request**, **Body**, **Auth**, **Response**, **Advanced**
  (the existing group mechanism is enough; no new control kind).
- `url` + `method` stay inline/quick on the card.
- Add a **Copy as cURL** action and a **Test** action (see 6.2).
- The run output panel should show status, `ok`, duration, content type, and a
  bounded body/headers preview.

---

## 5. P0 — inbound `trigger.webhook@1.0.0`

### 5.1 Node contract

Zero-config at the node, exactly like `trigger.schedule`: the node declares no
endpoint/secret. A `WorkflowWebhook` row owns that state and is linked by
`nodeId`, so the graph and the endpoint cannot drift apart.

| Direction | Id | Type | Meaning |
| --- | --- | --- | --- |
| out | `start` | `any` | Parsed body (unchanged trigger semantics) |
| out | `headers` | `object` | Lowercased, allowlisted request headers |
| out | `query` | `object` | Query parameters |
| out | `method` | `string` | `GET` / `POST` |
| out | `receivedAt` | `datetime` | Server receive time |
| out | `meta` | `object` | `{ webhookId, deliveryId, signatureVerified }` |

Capabilities: `webhook.receive` (new, inbound only). `sideEffects: 'none'` so a
webhook trigger never counts as an outbound network requirement in
`summarizeRunNeeds`.

**Cross-layer contract addition:** the run request gains an optional
`triggerContext` (`{ kind: 'webhook', body, headers, query, method, receivedAt,
webhookId, deliveryId }`). `startPersistedRun` forwards it; `NodeExecContext`
carries it; `_exec_trigger` emits the structured outputs when present and still
emits `start = runInput`. This is additive to the run DTO, not an IR change.

### 5.2 Data model (JDDS / Prisma)

New `WorkflowWebhook` model, following `WorkflowSchedule`:

```prisma
model WorkflowWebhook {
  id               String   @id @default(cuid())
  workflowId       String
  nodeId           String?
  name             String
  slug             String   @unique          // URL path, random, not a secret
  secretCipher     String                    // AES-256-GCM via connectors/secrets
  secretHint       String                    // last 4 chars, UI only
  enabled          Boolean  @default(true)
  mode             String   @default("safe") // safe | armed
  allowedMethods   String   @default("[\"POST\"]")
  responseMode     String   @default("immediate") // immediate | wait
  responseTimeoutMs Int     @default(10000)
  verificationMode String   @default("hmac") // hmac | token | both
  version          Int?                      // pinned when armed
  grantsJson       String?                   // derived grants + contentHash
  lastReceivedAt   DateTime?
  lastRunId        String?
  lastStatus       String?
  lastError        String?
  createdAt        DateTime @default(now())
  updatedAt        DateTime @updatedAt

  workflow Workflow @relation(fields: [workflowId], references: [id], onDelete: Cascade)

  @@index([workflowId, nodeId])
}
```

Add a bounded `WorkflowWebhookReceipt` (`webhookId`, `deliveryId`,
`receivedAt`, `expiresAt`, unique `(webhookId, deliveryId)`) for replay and
idempotency dedupe, purged by the same tick mechanism. Do **not** commit
`jdds.db`; ship a Prisma migration and follow
`.opencode/skills/black-eclipse-db/SKILL.md`.

The secret is generated server-side, shown **once**, stored encrypted with
`encryptSecret`, never returned by a list/get API. Rotating replaces the cipher
and invalidates the old secret immediately.

### 5.3 Public endpoint

`POST|GET /api/webhooks/[slug]`

- Add `/api/webhooks/` to `PUBLIC_PREFIXES` in `src/middleware.ts` (same
  precedent as `/api/channels/webhook/`). The signature is the gate; do **not**
  call `guardMutation` (an external service satisfies neither the Origin nor the
  loopback rule).
- Flow: lookup by `slug` -> enabled? -> node still present in the current IR? ->
  method allowed? -> body cap (64 KiB, matching `validateRunInput`) -> verify ->
  replay/idempotency -> parse JSON (non-JSON becomes `{text}`) -> `startPersistedRun`
  -> respond.
- Verification:
  - HMAC (default): `X-Eclipse-Signature: sha256=<hex>` over
    `"<timestamp>.<rawBody>"`, `X-Eclipse-Timestamp` within 300 s,
    `crypto.timingSafeEqual`. Reject missing/stale/mismatched signatures with
    401; reject replayed delivery ids with 409/200-duplicate.
  - Token (optional): `X-Eclipse-Token` compared to the decrypted secret with a
    timing-safe compare. Never accept a secret in the query string by default.
- Rate limit per webhook (reuse `rateLimit`) and per IP best-effort.
- Errors are deliberately uninformative (`401`, `404`, `405`, `413`, `409`,
  `503`) so the endpoint cannot be used to enumerate workflows.
- `GET` verification: when `verificationMode` includes challenge echo, a valid
  request with `challenge` returns the challenge value without starting a run.

### 5.4 Authorization model — **DECISION D1**

| Option | Behaviour | Verdict |
| --- | --- | --- |
| **A. Armed webhook** | Default `safe` (test run). Operator can **Arm** the webhook: pins the current workflow version, derives grants exactly like `authorizeGraphRun`, stores `grantsJson` + content hash. Requests then start an operator run against the pinned version with those grants. Deleting the pinned version or a digest mismatch refuses delivery; a later save does **not** move the pin (re-arm to pin a newer version). | **Recommended** |
| B. Always test-run | Simple, but makes the feature unable to do the job it exists for. | Reject as the only mode |
| C. Per-request approval | Impossible for unattended callers. | Reject |

Arming is an explicit UI confirmation (same dialog as operator runs), requires
the workflow to be saved, and is refused when the graph needs trading, file
writes, or any effect the operator run dialog does not support. Rotating the
secret or editing the graph does not silently widen authority: the arm stores
the exact version and digest it was granted for, and keeps running that pinned
version until the operator re-arms.

### 5.5 Response modes

- `immediate` (default): `202 { accepted: true, runId }` after the run is
  accepted. The caller polls the run if it cares.
- `wait`: poll the existing `GET /graphs/runs/{id}` up to
  `responseTimeoutMs` (max 30 s) and return
  `{ ok, runId, status, output }`; on timeout return `202` with the run id.
- A dedicated **Respond to Webhook** node is **not** in P0. The terminal output
  is the response body, which covers the common case without holding the
  request open across the runtime.

### 5.6 UI

- New **Webhook** tab in `node-inspector.tsx`, modeled on the Schedule tab:
  endpoint URL + copy button, create/rotate secret (shown once), enabled toggle,
  method filter, response mode, safe/armed switch with the authorization
  summary, last delivery/status/error.
- The node card shows the same live state as the schedule card: Active/Paused
  dot, endpoint host + slug, last received, last status, and "No webhook yet -
  open the Webhook tab".
- Deleting the node pauses/disables its webhook on the next reconcile, mirroring
  the schedule rule that a deleted trigger cannot keep firing.

---

## 6. P1 — ergonomics and the missing test path

### 6.1 `integration.webhook_send@1.0.0`

Signed outbound delivery: URL, JSON body, `secretEnv`, optional
`deliveryId`, idempotency key. Emits `X-Eclipse-Signature`,
`X-Eclipse-Timestamp`, `X-Eclipse-Delivery`. Reuses the HTTP client, SSRF rules,
retry policy, and 1 MB cap. This is the mirror image of 5.3 and the node most
graphs need to complete a webhook loop.

### 6.2 Operator-confirmed node test for network nodes

`node-test-ui.ts` currently refuses every `network` node. Add a **Test with
network** confirm (only for `integration.http` / `integration.webhook_send`):
the inspector lists the exact host and method, the request goes through the
existing node-test endpoint with an explicit `allowNetwork: true` operator flag,
and the Python endpoint grants network for that single node. Write/trading/model
remain refused. Default stays "Test" without network.

### 6.3 Credential references beyond env

Today `credentialEnvJson` resolves only runtime process env vars. Add a
`vault:<name>` reference resolved by the front door from the encrypted connector
secret store and sent per run (in memory, never persisted), mirroring
`modelSettings`. This is what makes vendor templates viable without storing keys
in node config.

### 6.4 Polish

- `node-examples.ts`: one input -> output example per integration node.
- Templates: "Webhook -> enrich via HTTP -> result", "Poll an API every 15 min",
  "Send a signed webhook".
- Copy-as-cURL / copy-webhook-URL buttons.
- Response preview with headers, status, timing, truncation banner.

---

## 7. P2 — generic connectors (not vendor sprawl)

1. **`integration.graphql`** - endpoint + query + variables + operation name +
   credential reference; reuses the HTTP client, returns `data` + `errors`.
2. **`integration.mcp_tool`** - pick a configured MCP server + tool + JSON
   arguments; results are explicitly *not* Eclipse-verified and never routed
   through JDDS, matching the MCP rule. Capability/side-effect class comes from
   the selected tool, and the run envelope still decides.
3. Vendor starter graphs (Slack, Discord, Telegram, Sheets) built from
   `integration.http` + auth preset + template, not new node types.

Deferred until there is a concrete request: WebSocket, SMTP/email, S3, DB
connectors, pagination node, `integration.http.respond`.

---

## 8. Cross-layer work

| Layer | Change |
| --- | --- |
| TS registry | New `registry-integration.ts` module added to `DEFINITIONS`; `integration.http@1.1.0`; `trigger.webhook@1.0.0`; config fields + required field; node examples; templates |
| Manifest | `npm run graph:manifest`; both suites prove parity |
| Python registry | `trigger.webhook` in `nodes.py`; HTTP moved to `http_client.py`; `integration.webhook_send`; `NodeExecContext.trigger_context` |
| Compiler/executor | Add `webhook.receive` handling (no network requirement); no new effect class |
| Front door | `run-server.ts` forwards `triggerContext`; `run-authorization.ts` keeps inbound triggers out of `requiresNetwork`; new webhook store + route; middleware public prefix |
| Prisma | `WorkflowWebhook` + receipts migration; schema relation on `Workflow` |
| UI | Webhook tab; HTTP grouped fields; card state; test-with-network confirm; authorization summary |
| Docs | `graph-studio.md`, `NAVIGATION.md`, `CHANGELOG.md`, ADR if D1 is accepted |

---

## 9. Test matrix

**TS unit**
- `registry.test.ts`: new types/versions resolve; `getNodeDefinition` picks 1.1.0.
- `manifest.test.ts` + Python `test_graph_registry_manifest.py`: parity.
- `config-fields.test.ts`: every new field has a label and bounds.
- `run-authorization.test.ts`: `trigger.webhook` is not counted as outbound
  network; armed grants are a subset; unknown/edited pinned graph is refused.
- Webhook crypto: HMAC vector, stale timestamp, wrong body, constant-time path.

**Python unit**
- `http_client` with an injected fake transport (no real network):
  query merge, body modes, JSON/text/truncate, retry on 429/5xx only, backoff
  bound, `Retry-After`, redirect hop re-check blocks loopback/private and
  `https -> http`, header validation, credential resolution, redacted logs.
- `_exec_trigger` with `trigger_context` emits all outputs; without it, only
  `start` (legacy graphs unchanged).

**Route/integration**
- Missing/duplicate `WorkflowWebhook` -> 404/409.
- Disabled webhook -> 404; wrong method -> 405; oversized body -> 413.
- Valid HMAC -> 202 + run; invalid -> 401 with no run row.
- Replay within the window -> 409, one run only.
- Safe mode: a graph with `integration.http` still fails the test-run envelope.
- Armed mode: run starts on the pinned version; editing the graph -> refusal
  until re-armed; a changed content hash -> refusal.
- `wait` mode returns the terminal output; timeout returns 202.

**Manual acceptance**
- Create webhook -> copy URL -> `curl` with HMAC -> run appears in History.
- Rotate secret -> old signature 401, new signature 202.
- `integration.http`: GET with query, POST JSON, form body, 404 with
  `failOnHttpError`, retry on 429, truncate at the cap, redirect to private host
  blocked, duration/headers shown.
- Test-with-network refuses until the confirm is checked.

---

## 10. Work breakdown

| # | Ticket | Depends on | Est. |
| --- | --- | --- | --- |
| P0.1 | Extract `http_client.py`; manual redirect opener; per-hop SSRF; redacted logging; v1.0.0 inherits the fix | — | 1.5 d |
| P0.2 | `integration.http@1.1.0` TS + Python contracts, config fields, manifest | P0.1 | 1 d |
| P0.3 | Executor features: query, body modes, response type/cap, retries, `failOnHttpError`, new outputs | P0.1 | 2 d |
| P0.4 | `WorkflowWebhook` + receipts model, migration, store module | — | 1 d |
| P0.5 | Public `/api/webhooks/[slug]` + HMAC/token verify + replay/idempotency + rate limit + middleware prefix | P0.4 | 1.5 d |
| P0.6 | `trigger.webhook` contract + `triggerContext` plumbing (run-server -> runtime -> executor) | P0.5 | 1 d |
| P0.7 | Webhook tab + card state + copy/rotate + disable-on-delete reconcile | P0.5 | 1.5 d |
| P0.8 | Arm model: pin version, derive/store grants, re-check digest, authorization UI | P0.4, P0.6 | 1.5 d |
| P0.9 | Templates, node examples, docs, CHANGELOG, ADR | P0.3-P0.8 | 1 d |
| P1.1 | `integration.webhook_send` | P0.1 | 1 d |
| P1.2 | Test-with-network confirm (TS + Python node-test) | P0.3 | 1 d |
| P1.3 | Vault credential references | P0.3 | 1.5 d |
| P2.1 | `integration.graphql` | P0.3 | 1 d |
| P2.2 | `integration.mcp_tool` | P1.3 | 2 d |

P0 is roughly **11-12 focused days**; P1 +3.5; P2 +3.

---

## 11. Compatibility and migration

- **No IR version bump.** New node types and an additive run-DTO field do not
  change the canonical graph schema.
- **Two HTTP versions live side by side.** `1.0.0` keeps its current defaults
  (`failOnHttpError: false`, no redirects config) but shares the security fix.
  `1.1.0` is opt-in by inserting a new node. Do **not** silently rewrite saved
  node versions.
- **Existing trigger route stays** at
  `POST /api/workflows/[id]/trigger` for compatibility (local/CRON_SECRET
  callers); it keeps the test-run envelope. The new/secure path is
  `/api/webhooks/[slug]`.
- **Old webhook-less graphs** are untouched; `trigger.manual` remains
  zero-config.
- **Docs correction:** remove "three trigger nodes" until the third one ships.

---

## 12. Documentation obligation

- `docs/graph-studio.md`: replace the Phase 8/10 webhook note; document the
  integration node catalogue, the HTTP contract, the webhook auth model, response
  modes, arm semantics, and the new test path.
- `docs/NAVIGATION.md`: add a row for this plan next to the logic-nodes row.
- `docs/CHANGELOG.md`: one entry per shipped ticket (require).
- ADR: if **D1 Arm** is accepted, add an app ADR (`ADR-NNN`) in
  `skills/ARCHITECT.md` and mirror it in `docs/DECISIONS.md` (including the
  "no widening by request" rule and the pinned-version/digest check).
- Do **not** commit `jdds.db`; the migration is the change.

---

## 13. Decisions needed before coding

1. **D1 - webhook authority.** Adopt the "armed webhook" model (A), or keep
   webhooks test-run-only (B)? Recommendation: **A**, safe by default.
2. **D2 - webhook proof.** HMAC + timestamp as the default, optional token
   header, or token-only? Recommendation: **HMAC default, token optional**;
   never a secret in the query string.
3. **D3 - default response.** `202 + runId` (recommended) vs waiting for the
   terminal output. `wait` stays opt-in with a 30 s cap.
4. **D4 - HTTP versioning.** Additive `1.1.0` (recommended) vs a breaking
   `2.0.0`. `1.1.0` keeps saved graphs working.
5. **D5 - credentials.** Env-only for now, or vault references in P1?
   Recommendation: ship env-only with P0, add `vault:` in P1.
6. **D6 - scope.** Is the first delivery just P0 (HTTP + inbound webhook), or
   should P1's signed outbound webhook and the test path ship together?
7. **D7 - sync reply.** Terminal-output-as-response is enough for v1, or do you
   want a dedicated "Respond to webhook" node (defer; it requires holding the
   HTTP request across the runtime).

---

## 14. Definition of done (P0)

- [ ] `integration.http@1.1.0` and `trigger.webhook@1.0.0` exist in both
      registries and the generated manifest; parity tests pass.
- [ ] Every redirect hop is SSRF-checked; a redirect to a private host is
      refused with a clear error and a test proves it.
- [ ] A signed webhook starts exactly one run; a bad signature, stale
      timestamp, or replay starts none.
- [ ] Safe mode cannot perform network/write effects; armed mode runs only the
      pinned, digest-verified graph version.
- [ ] Secrets are encrypted at rest, shown once, never logged or returned.
- [ ] The Webhook tab can create, copy, rotate, disable, and arm a webhook.
- [ ] `integration.http` can be exercised from the editor after an explicit
      network confirmation.
- [ ] `npm run test` and `npx tsc --noEmit` pass.
- [ ] Docs + CHANGELOG updated; no `jdds.db` commit.
