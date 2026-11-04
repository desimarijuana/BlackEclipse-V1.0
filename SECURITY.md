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
- The container and deployment defaults (`Dockerfile`, `docker-compose.yml`,
  `.dockerignore`), including secret leaks into images.
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
- **Secrets never enter git.** `.env*`, databases, private keys, `mcp-servers.json`
  and the connector key are ignored *and* checked by a pre-commit hook and CI.
- **Encrypted credentials at rest in the app DB** (AES-256-GCM), with the
  caveat that the key file lives on the same host. Encryption protects a copied
  database, not a compromised machine.
- **Least privilege in the container.** Non-root user, all capabilities dropped,
  `no-new-privileges`.

## Operator checklist before exposing the app

1. `HARNESS_AUTH=required` and a unique `HARNESS_AUTH_SECRET` (≥ 32 random bytes).
2. A unique `CRON_SECRET` and a `CONNECTOR_SECRET_KEY`.
3. `node scripts/security-preflight.js` passes with `NODE_ENV=production`.
4. TLS terminated by a reverse proxy; `BE_BIND_ADDR` left at loopback.
5. A real account created through `/api/auth/setup` (the setup route closes after
   the first account).
6. Back up the data volume, and keep `.env`, `.connector-key` and
   `python/.black-eclipse/channels/secret.key` out of those backups' public copies.

See `Black-Eclipse-site/docs/DEPLOYMENT.md`,
`Black-Eclipse-site/docs/data-and-privacy.md` (data map, encrypted vault,
local-only mode, wipe), and `Black-Eclipse-site/docs/harness/security.md` for the
architecture, and `Black-Eclipse-site/docs/harness/authentication.md` for the auth
decision path.
