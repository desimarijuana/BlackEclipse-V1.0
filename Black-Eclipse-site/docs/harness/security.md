---
title: Security — one decision path for every privileged operation
status: Current
last-verified: 2026-10-08
---

# Security

**Who this is for:** anyone adding a capability that reads, writes, deletes,
executes, connects, browses, deploys or moves money — and anyone who needs to know
why a tool was allowed, denied or held for approval.

## TL;DR

- The **Security Gateway** (`python/harness/security/gateway.py`) is the ONE
  authorization path. Every privileged operation is described by an
  `AuthorizationRequest` and answered with exactly one `AuthorizationDecision`:
  `ALLOW`, `DENY` or `APPROVAL_REQUIRED`.
- It **composes**, and never replaces, the existing per-subsystem policies
  (`code/policy.py`, `browser/policy.py`, `computer/policy.py`, `git/safety.py`,
  `execution/policy.py`, `plugins/permissions.py`, `skills/permissions.py`, …).
- The **Security Floor** is immutable and evaluated first. It hard-denies
  credential/key material, the security configuration, OS directories and
  destructive infrastructure actions, and it mandates approval for production,
  financial and infrastructure classes. No profile, skill, plugin, MCP server,
  prompt or request field can weaken it.
- **Everything fails closed.** A missing approval store, an unreachable secret
  provider, a broken policy or an internal error yields `DENY` — never a silent
  allow.
- Every decision is written to an **append-only, hash-chained audit** on the ONE
  `agent-memory.db`, mirrored to the Event System (`security.*`) and to
  observability metrics.

## The pipeline

`SecurityGateway.authorize()` evaluates a request in a fixed order; each stage can
only make the outcome *more* restrictive:

```
AuthorizationRequest
   │
   ├─ 1. session / workspace isolation      (SessionRegistry)
   ├─ 2. Security Floor   HARD_DENY / HARD_ALLOW / MANDATORY_APPROVAL (terminal)
   ├─ 3. Risk Engine      server-side, by severity
   ├─ 4. Policy Engine    layered, restrict-only
   ├─ 5. Capability Engine an explicit capability satisfies an approval
   ├─ 6. Approval Engine  standing grant, then a pending single-use approval
   └─ AuthorizationDecision { decision, reason, risk, policy, matchedRules,
                              approvalId, capabilityId, expiration, auditReference }
```

- `authorize()` never raises.
- `check()` returns a boolean.
- `require()` raises `SecurityDenied` / `ApprovalRequired` for anything not
  `ALLOW`.

## Vocabulary

| Type | Meaning |
|---|---|
| `Permission` | `DISCOVER / READ / WRITE / DELETE / EXECUTE / NETWORK / CREDENTIAL / ADMIN` |
| `RiskLevel` | `NONE / LOW / MEDIUM / HIGH / CRITICAL` (ordered by severity) |
| `Environment` | `DEVELOPMENT / STAGING / PRODUCTION` |
| `Verdict` (floor) | `HARD_DENY / HARD_ALLOW / MANDATORY_APPROVAL` |
| `ApprovalType` | `ONCE / TASK / SESSION / RESOURCE / TOOL / TIME_LIMITED / ADMIN` |
| `Decision` | `ALLOW / DENY / APPROVAL_REQUIRED` |

Permissions are **resource-scoped globs**, never a global boolean, e.g.
`filesystem.write:/workspace/project/**`. See `security/permissions.py`.

## The Floor (`security/floor.py`)

Terminal rules, evaluated before policy:

- **Hard-deny** sensitive paths for *any* filesystem operation: `~/.ssh`,
  `~/.aws`, `~/.kube`, `~/.gnupg`, `.env`/`.env.*`, `*.pem`/`*.key`/`*.p12`,
  `secrets.json|yaml`, the Eclipse security config
  (`.black-eclipse/security/**`), `jdds.db`, `agent-memory.db`, `auth.db`.
- **Hard-deny** the same sensitive paths, OS directories (`/etc/**`, `/usr/**`,
  `/bin/**`, `/sys/**`, `/proc/**`, `/root/**`, `/var/**`, `C:\Windows\**`, …) and
  the destructive action classes (`database.admin`, `deploy.destroy`,
  `financial.withdraw`, `financial.transfer`, `security.admin`,
  `credential.admin`).
- **Mandatory approval** for `database.write/delete`, `deploy.production/staging`,
  every live/cancel financial action, `security.*`, and `plugin/mcp.invoke`.
- **Mandatory approval** for filesystem/database writes and deletes in
  `PRODUCTION`.

The floor may only be changed through `SecurityFloor.add_rule(..., admin=True)` —
a path the agent has no access to, and which the floor itself hard-denies
(`security.policy` acts on `.black-eclipse/security/**`).

## The Risk Engine (`security/risk.py`)

Risk is computed server-side from the action class, resource, environment,
irreversibility, external side effects, financial impact, credential sensitivity,
network destination, scope and blast radius. A caller-supplied hint (e.g. from
`request.context["risk"]`) can **only raise**, never lower, the score. Any action
whose risk is `HIGH` or above requires an approval unless a capability or standing
grant covers the exact request.

## The Policy Engine (`security/policy.py`)

- **Profiles:** `LOCKDOWN`, `SECURE`, `DEVELOPER`, `AUTONOMOUS`, `CUSTOM`.
  `AUTONOMOUS` never means "security off" — it pre-approves LOW-risk
  reads/execution while every dangerous class and the whole floor stay intact.
- **Inheritance:** `system → organization → user → project → agent → task`,
  composed **restrict-only** (the most restrictive match wins). A lower layer can
  only make a rule stricter.
- **Read-only/paper financial actions** (`financial.research`, `market_read`,
  `portfolio_read`, `paper_trade`) are allowed by the baseline; live actions are
  not.
- **Hot reload** is atomic: the candidate is parsed, validated and compiled into
  new immutable documents; only if every document is valid does it replace the
  live policy. An invalid policy is rejected and the known-good policy stays.

## Approvals (`security/approval.py`)

The approval engine is a typed broker over the **existing single-use store**
(`mcp/approvals.py`, `McpApproval` with `kind="security"`) and standing grants
(`grants.py`). An approval is bound to the exact action, resource, session and
task, and single-use: a successful claim consumes it and a repeat needs a fresh
decision. A timeout, a missing store, or any communication failure fails closed.

## Capabilities (`security/capabilities.py`)

Issue / validate / delegate / restrict / revoke / expire. The invariant:
**delegation may only reduce or preserve authority.** A delegated capability is
refused if it would widen the action, resource, scope, session, task, expiry or
drop a parent constraint. A valid capability bound to the exact request satisfies
an approval (but never a floor hard-deny). Capabilities persist on
`agent-memory.db` and are revoked when a session closes.

## Secrets (`security/secrets.py`)

- Referenced by identifier: `secret://<provider>/<name>`. Providers: `env`, a
  local development file provider (`.black-eclipse/security/secrets.local.json`),
  the **OS keychain** (`OsKeychainProvider` — Windows Credential Manager, macOS
  Keychain, Linux Secret Service), and a configurable **CLI provider**
  (`CliSecretProvider`) for Vault / AWS Secrets Manager / 1Password / GCP / Azure
  via an operator-set argv template (`BLACK_ECLIPSE_SECRETS_CLI`, JSON of
  `name → argv` with `{name}`). A provider that is missing reports unavailable —
  never a fabricated value.
- **Scoped** by consumer/session/task/action/time. A consumer without a grant is
  refused; `inject_env` resolves only the named refs (so arbitrary host secrets
  never reach a subprocess).
- **Redaction:** every resolved value is registered with the `SecretRegistry`,
  which strips it (and its URL/JSON encodings) from logs, tool output, errors,
  telemetry and the audit trail, in addition to pattern-based redaction.
- The LLM receives a reference/`has()` probe, never the value, wherever possible.

## Sandbox (`security/sandbox.py`)

The physical execution boundary, deliberately separate from authorization (the
Permission Engine decides *whether*; the sandbox decides *where/how*). The
`ExecutionSandbox` interface exposes `create`/`start`/`execute`/`mount`/
`network_policy`/`inject_secret`/`collect_output`/`terminate`/`destroy`.

- **`DockerSandbox`** — a real container boundary: `--network none|bridge`,
  read-only rootfs, non-root user, `--cap-drop ALL`, `no-new-privileges`,
  memory/pids/cpu limits, explicit read-only mounts, and secret env.
- **`LocalSandbox`** — process isolation over the existing `code/sandbox.py`
  primitive (Windows Job Object / POSIX process groups) with an allowlist-only
  environment. It reports `filesystemIsolation: false` / `networkIsolation: false`
  honestly — it is not a container.
- **`UnavailableSandbox`** — fails every operation closed.

`select_sandbox()` prefers Docker, then Local, then Unavailable — it never returns
an unbounded backend. `BLACK_ECLIPSE_SANDBOX_BACKEND` forces a preference.
`BLACK_ECLIPSE_SANDBOX_REQUIRED` (`1` = any backend must exist, `docker` = Docker
must be active) makes the gateway **refuse** an execution action when the required
isolation is absent, audited as `security.sandbox.blocked`.

## Network (`security/network.py`)

Default **DENY**. Rules match domain / subdomain / IP / CIDR / port / protocol /
method / path / direction. Every outbound URL is re-checked by the canonical SSRF
guard (`mcp/ssrf.py`) and DNS is resolved and pinned so a rebinding host cannot
slip between the check and the connection. Private/loopback/link-local/metadata
targets are always refused. Redirects are re-validated on every hop.

**Graph operator runs** use the same SSRF guard from `graph_runtime/nodes.py`
(no loopback, 1 MB response cap, hard timeout). The front door
(`run-authorization.ts`) derives grants from the node registry, enables network
only on an explicit operator request, and refuses trading and external write
nodes. Test runs never perform network, write or trading effects.

## Session isolation (`security/context.py`)

One `SecurityContext` per session. A request that presents a different session or
a workspace different from the context's binding is refused before policy.
Closing a session revokes its capabilities.

## Multi-tenancy & identity (`security/identity.py`)

The runtime never trusts a caller-supplied `userId`/`tenantId`. The Next.js front
door authenticates the user and mints a short-lived (5 min) HS256 JWT with
`HARNESS_AUTH_SECRET` (`src/lib/harness/runtime-identity.ts`); proxies forward it
as `X-Harness-Identity`. `identity.py` verifies it with stdlib only and yields a
verified `Identity` (`user_id`, `tenant_id`, `roles`, `session_id`).

Precedence: **session token → operator** (loopback or the operator secret) **→
anonymous**. In multi-tenant mode (`HARNESS_MULTI_TENANT=1`, or auto-on when the
front door requires auth) an anonymous caller is refused (401) via
`require_identity` / `require_tenant`.

Tenant isolation in the security plane: capabilities, secret grants, sessions and
audit records all carry `tenantId` and never cross tenants; the gateway refuses an
untenanted request in multi-tenant mode. Beyond loopback the runtime refuses to
start without `CRON_SECRET` (and `HARNESS_AUTH_SECRET` in multi-tenant mode); the
security endpoints are per-tenant rate-limited.

**Physical tenant stores (`security/tenant_store.py`).** The strongest isolation
is physical: `TenantStoreRegistry.store_for(tenant_id)` returns that tenant's own
`AgentMemoryStore` at `.black-eclipse/tenants/<tenant>/agent-memory.db`
(`BLACK_ECLIPSE_TENANT_DB_DIR`), with the id strictly sanitized (no traversal).
Two tenants get two databases, so a missing `WHERE` cannot leak rows. **The run
path does not yet route its data through the tenant store** (see Honest
boundaries).

**Identity header rollout + run-path tenant.** Every `[[...path]]/route.ts` proxy
forwards `X-Harness-Identity` (`runtimeIdentityHeaders`), and the explicit
`/runs`, `/chat` and `/chat/stream` routes now attach it too. The Python `/runs`
boundary resolves the verified identity to the run's `tenantId`, the graph puts it
on the `ToolContext`, and the security gateway scopes every effect decision to it
— so multi-tenant runs authorize under the correct tenant. **Run *data* still
lands in the shared store** until the run path is routed through
`TenantStoreRegistry`.

**Preflight.** `npm run security:preflight` (`scripts/security-preflight.js`)
fails closed on a network-facing deployment missing `HARNESS_AUTH_SECRET` /
`CRON_SECRET` and prints the manual controls (TLS proxy, edge rate limiting,
KMS, WORM audit, per-tenant keys).

**Boundary:** this is the multi-tenant *security plane* + identity seam + a
physical-isolation primitive. Full per-tenant **data** isolation (routing runs,
memory, tasks, artifacts, JDdS reads through tenant stores) is the follow-on
data-plane migration and is not claimed here.

## Audit + observability (`security/audit.py`, `security/store.py`)

Every sensitive operation records an audit event (timestamp, actor, agent,
session, task, tool, action, resource, decision, risk, policy, approval,
capability, result, error). Records are append-only and hash-chained: each row
stores the previous row's hash, and `verify_chain()` walks the chain and reports
the first break. Events are mirrored to the Event System namespace `security.*`
and to observability counters (`security_permission_requests_total`,
`security_permission_denials_total`, `security_hard_blocks_total`,
`security_network_denials_total`, …). **No secret value is ever written.**

**Anchoring:** set `BLACK_ECLIPSE_SECURITY_AUDIT_LOG` to a path and the trail is
also written to an append-only JSONL sink with an HMAC-signed rolling head
(`AuditSink`), so tamper-evidence survives outside the runtime's writable
database. `GET /security/audit/verify` walks both chains.

## Migration — every effectful capability goes through the gateway

`security/classification.py` maps a tool name to `(action, resource, permission)`
by importing the **canonical effect tuples from `code/policy.py`**
(`FS_WRITE_TOOLS`, `WRITE_TOOLS`, `GIT_WRITE/EXTERNAL_TOOLS`,
`APP_RUNTIME_WRITE_TOOLS`, `APP_RUNTIME_K8S_WRITE_TOOLS`, `BROWSER_EFFECTFUL_TOOLS`,
`COMPUTER_EFFECTFUL_TOOLS`, `VISION_EXTERNAL_TOOLS`, `EXTERNAL_ACTION_TOOLS`,
`INTEL_WRITE_TOOLS`, `TERMINAL_WRITE_TOOLS`) plus the `mcp__`/`plugin_`/`skill_`
prefix families. `build_effect_authorizer` wraps the whole composed chain with
`make_security_authorizer`, so **every non-read tool** of **every capability** is
classified and passes through the gateway. A tool added to a capability's effect
set is therefore classified automatically; the bypass-audit test
(`test_security_bypass_audit.py`) fails if any canonical effect tool is
unclassified.

Coverage: filesystem, shell/code execution, git/VCS, application-runtime,
infrastructure/deployment, database (via `execute_sql`), browser, computer use
(+ financial firewall), vision, plugins, MCP and skills.

**Approval semantics:** the gateway enforces the Security Floor (hard-deny) and a
policy deny as **terminal**; approvals (policy-driven *and* floor-mandated) are
**deferred** to the capability's own established single-use, digest-bound approval
chain (`defer_policy_approval=True`). That gives exactly one approval and one
audit, with no double prompt. Hard denies are never deferred.

Read-only tools are not passed to the effect authorizer at all (the registry only
calls it for non-read tools), so the classifier may return `None` for them safely.

## Operator surface

`/security/*` (operator-gated; proxy `/api/security/**`):

| Route | Purpose |
|---|---|
| `GET /security/status` · `/health` · `/metrics` | live posture |
| `GET /security/policy` · `POST /security/policy/reload` | inspect / atomically replace policy |
| `GET /security/audit` · `/audit/verify` | read the trail / verify the hash chain |
| `GET/POST /security/capabilities` · `POST …/{id}/revoke` | issue / revoke |
| `GET /security/approvals` · `POST …/{id}/decide` | the approval queue |
| `POST /security/check` · `/network/check` | dry-run decision |

Operator UI: **Settings › Security** (`src/components/screens/security-settings.tsx`)
shows posture, pending approvals (approve-once / always-allow / deny),
capabilities (revoke) and audit-chain validity. It decides through the API — it is
never the authority itself.

## Configuration

| Env | Default | Meaning |
|---|---|---|
| `BLACK_ECLIPSE_SECURITY_ENABLED` | `1` | master switch (off is never a silent bypass of nothing — the subsystem simply is not installed) |
| `BLACK_ECLIPSE_SECURITY_PROFILE` | `secure` | baseline policy profile |
| `BLACK_ECLIPSE_SECURITY_POLICY` / `BLACK_ECLIPSE_SECURITY_DIR` | `.black-eclipse/security/policy.json` | policy file |
| `BLACK_ECLIPSE_SECURITY_ALLOW_LOOPBACK` | `0` | allow loopback in the network policy |
| `BLACK_ECLIPSE_SECURITY_AUDIT` | `1` | audit on/off |
| `BLACK_ECLIPSE_SECURITY_AUDIT_LOG` | off | path to an external JSONL audit sink |
| `BLACK_ECLIPSE_SECURITY_AUDIT_KEY` | `eclipse-audit` | HMAC key for the sink head |
| `BLACK_ECLIPSE_ENVIRONMENT` | `development` | default environment (`production` arms the prod gates) |
| `BLACK_ECLIPSE_SECRETS_FILE` | `.black-eclipse/security/secrets.local.json` | local dev secret file |
| `BLACK_ECLIPSE_SECRETS_SERVICE` | `eclipse` | keychain service name |
| `BLACK_ECLIPSE_SECRETS_CLI` | off | JSON `name → argv` templates for Vault/AWS/1Password/GCP/Azure |
| `BLACK_ECLIPSE_SANDBOX_BACKEND` | auto | force `docker` or `local` |
| `BLACK_ECLIPSE_SANDBOX_REQUIRED` | off | `1` or `docker` — refuse execution without that backend |
| `BLACK_ECLIPSE_TENANT_DB_DIR` | `.black-eclipse/tenants` | per-tenant store root |
| `HARNESS_MULTI_TENANT` | auto | require tenant identity (auto-on when front-door auth is on) |
| `HARNESS_AUTH_SECRET` | — | the front door's signing secret; verifies the identity token |
| `BLACK_ECLIPSE_DEFAULT_TENANT` | — | default tenant for operator/loopback requests |
| `BLACK_ECLIPSE_RATE_LIMIT_PER_MIN` | `240` | per-tenant rate limit on the security endpoints |

## Tests

`python/tests/test_security_core.py` (floor/policy/risk/permission/capability),
`test_security_adversarial.py` (red-team scenarios), `test_security_failure.py`
(fail-closed), `test_security_concurrency.py` (single-use claims, revocation,
reload races), `test_security_network_secrets.py`, `test_security_integration.py`
(the authorizer seam), `test_security_api.py` (the route seam),
`test_security_bypass_audit.py` (every effect tool is classified),
`test_security_sandbox.py`, `test_security_audit_sink.py`,
`test_security_secret_providers.py`, `test_security_tenancy.py` (identity +
tenant isolation), `test_security_ratelimit.py` and `test_security_tenant_store.py`
(per-tenant physical isolation). All passing (see `pytest -k security`).

## Honest boundaries

- All effectful capabilities are now classified and pass through the gateway, but
  **approvals for them are deferred to each capability's own single-use chain**
  (by design, to avoid a double prompt). The gateway's own approval queue
  (`/security/approvals`) carries approvals created by the standalone gateway path
  (e.g. `POST /security/check`), not the per-capability ones — those keep their
  existing operator surfaces (MCP approvals, code actions, git, browser/computer ASK).
- The gateway enforces the floor, a policy deny, risk scoring and audit for every
  effect; the per-capability handler still performs its own finer-grained,
  real-path/per-domain check (`code/policy.resolve_within`, browser domain policy,
  git risk, computer finance firewall). The gateway complements those, it does not
  replace them.
- The `DockerSandbox` requires the `docker` CLI; without it execution runs in the
  `LocalSandbox` (process isolation only, no filesystem/network isolation) or, if no
  primitive exists, `UnavailableSandbox` (fail closed). The sandbox is an available
  boundary, not yet wired as the mandatory wrapper around every execution path.
- The OS keychain / CLI secret providers are real integrations but report
  unavailable unless the native store or the configured CLI is present.
- Identity is now **verified at the edge** and tenant-scoped in the security plane
  (ADR-H161). But full per-tenant **data** isolation — every run, memory, task,
  artifact and JDdS read carrying and enforcing a tenant — is a data-plane
  migration across every subsystem's storage that is **not yet done**. Do not run
  one database for mutually untrusted tenants until that lands. The runtime now
  refuses to start beyond loopback without the secrets; still place it behind the
  authenticated front door and a TLS reverse proxy.
