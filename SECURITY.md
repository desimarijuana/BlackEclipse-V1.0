# Security Policy

BlackEclipse is a **single-user, local-first** agentic finance workbench. It can
run shell commands, browse the web, read and write files, and hold API keys — so
a deployment that is reachable by someone else is a deployment that can be
operated by someone else. Treat the front door and the harness as one trust
boundary.

## Supported versions

Only the latest commit on the default branch is supported. There are no
long-lived release branches; fixes land on `main` and are deployed from there.

| Version | Supported |
| --- | --- |
| `main` (latest) | ✅ |
| Older commits | ❌ |

## Reporting a vulnerability

**Please do not open a public issue for a suspected vulnerability.**

Use GitHub's private reporting channel:

1. Go to the repository's **Security** tab → **Advisories** → **Report a
   vulnerability**.
2. Include: affected commit, the route/tool involved, reproduction steps, impact,
   and any proof-of-concept (redact real credentials).
3. If private advisories are unavailable, open a minimal issue asking for a
   private contact channel — **without** details — and a maintainer will follow up.

You can expect an acknowledgement within **72 hours** and a status update within
**7 days**. Please give us **90 days** before public disclosure; we will credit
you in the advisory unless you ask otherwise.

## Safe harbour

We will not pursue or support legal action against a researcher who acts in
good faith within the in-scope list, avoids privacy violations and data
destruction, does not exfiltrate or publicly disclose user data, and gives us a
reasonable opportunity to fix the issue before disclosure. This is a statement
of intent, not a waiver of any third party's rights and not legal advice.

## In scope

- Authentication and session handling (`src/lib/auth/`), including the
  `HARNESS_AUTH=off` escape hatch and the fail-closed behaviour when
  `HARNESS_AUTH_SECRET` is missing.
- The harness security gateway and its fail-closed paths
  (`python/harness/security/`), tool isolation, and the shell/browser/git/file
  surfaces.
- Credential handling: connector encryption (`src/lib/connectors/secrets.ts`),
  channel secrets, provider API keys, and anything that writes them to disk, logs,
  events, memory, or a model prompt.
- Tenant/session isolation and approval bypasses.
- The committed-secret gate (`scripts/scan-secrets.js`) and ignore rules.

## Out of scope

- Vulnerabilities in upstream dependencies that have not been shown to be
  reachable here. Please report those upstream; we will pick up the fix.
- Findings that require an already-compromised host, a local attacker with your
  OS user, or physical access.
- Self-XSS, missing rate limits on a loopback-only development server, or
  clickjacking of a page that is not authenticated.
- "The agent can run commands" — that is the product. Authorization,
  approval, and audit around it are in scope.

## Security model (what "secure" means here)

- **Local by default.** The dev server binds loopback. The container publishes on
  `127.0.0.1` unless you deliberately set `BE_BIND_ADDR`.
- **Fail closed.** A required control that is missing (auth secret, operator
  secret, approval store, policy error) refuses the operation; it never falls
  back to "allow".
- **Two request-boundary rules protect the accountless desktop.** A central
  same-origin gate rejects cross-site mutating API calls (and any browser
  request marked `Sec-Fetch-Site: cross-site`) even when `HARNESS_AUTH=off`; the
  Python runtime trusts a request as an operator only when both the peer address
  and the `Host` header name loopback. This closes drive-by CSRF and DNS
  rebinding. `X-Forwarded-Host` is honoured only when `BE_TRUST_PROXY=1`.
- **Secrets never enter git.** `.env*`, databases, private keys, `mcp-servers.json`
  and the connector key are ignored *and* checked by a pre-commit hook and CI.
- **Encrypted credentials at rest in the app DB** (AES-256-GCM), with the
  caveat that the key file lives on the same host. Encryption protects a copied
  database, not a compromised machine.
- **Least privilege in the container.** Non-root user, all capabilities dropped,
  `no-new-privileges`.

### Known limitations (2026-11-15 security audit)

- The product provisions **one operator account**; multi-user isolation is not a
  supported or tested claim.
- Session revocation is authoritative on privileged routes (shell, workspace,
  artifacts, terminal, security admin, runtime restart); read-only routes may
  accept a signed token until its 7-day expiry. Rotate `HARNESS_AUTH_SECRET`
  after a suspected token theft.
- Journals, memories and runs are plaintext SQLite protected by OS file
  permissions; only connector credentials are encrypted.
- Python dependencies are hash-locked in `python/requirements.lock` and installed
  from it in CI; some transitive Node **High** advisories remain tracked in the
  audit. Install-time downloads are TLS-verified but not checksum-verified for
  every desktop payload component.
- The detailed audit, including reproduction detail, lives in `security/audit/`
  and is **not** part of the public release.

### Residual risks accepted for the source release

These are documented, not hidden. Read them before deploying beyond a single
operator on the same machine.

- **The agent can execute code by design.** Approval, the security gateway and
  the destructive-command hardline are the boundary; raw PTY keystrokes remain an
  operator-only path.
- **The desktop runs with `HARNESS_AUTH=off`.** The same-origin/CSRF gate and the
  loopback peer + `Host` check are the compensating controls, not a login.
- **Multi-user is not supported.** Run creation overrides `userId` from the
  verified identity, but other run-creating routes have not all been audited to
  the same standard. Do not expose one instance to multiple people.
- **Read-only routes may honour a signed token until expiry.** Revocation is
  authoritative on privileged routes only; rotate `HARNESS_AUTH_SECRET` after any
  suspected token theft.
- **Journals, memories and runs are plaintext at rest.** Protection is the OS
  account and file permissions.
- **The optional quant container runs as root** inside a restricted sandbox.

## Operator checklist before exposing the app

1. `HARNESS_AUTH=required` and a unique `HARNESS_AUTH_SECRET` (≥ 32 random bytes).
2. A unique `CRON_SECRET` and a `CONNECTOR_SECRET_KEY`.
3. `node scripts/security-preflight.js` passes with `NODE_ENV=production`.
4. TLS terminated by a reverse proxy; `BE_BIND_ADDR` left at loopback. If the
   proxy sets `X-Forwarded-Host`, also set `BE_TRUST_PROXY=1` so the same-origin
   check compares the real external host; leave it unset otherwise.
5. A real account created through `/api/auth/setup` (the setup route closes after
   the first account).
6. Back up the data volume, and keep `.env`, `.connector-key` and
   `python/.black-eclipse/channels/secret.key` out of those backups' public copies.

See `Black-Eclipse-site/docs/DEPLOYMENT.md`,
`Black-Eclipse-site/docs/data-and-privacy.md` (data map, encrypted vault,
local-only mode, wipe), and `Black-Eclipse-site/docs/harness/security.md` for the
architecture, and `Black-Eclipse-site/docs/harness/authentication.md` for the auth
decision path.
