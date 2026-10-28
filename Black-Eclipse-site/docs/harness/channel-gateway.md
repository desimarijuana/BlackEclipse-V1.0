---
title: Channel Gateway — remote control over external messaging
status: Current
last-verified: 2026-10-16
---

# Channel Gateway

**Who this is for:** anyone connecting an external account (Telegram, Discord,
email, …) to Eclipse, or a developer changing how a remote message becomes an
action.

The Channel Gateway lets a user see and drive Eclipse from where they already
are. It is a first-class core subsystem (`python/harness/channels/`), not a plugin
and not a second agent loop. See ADR-H199.

## The trust model (read this first)

An inbound message is **untrusted** until it resolves to a verified
`ChannelBinding`. A chat id or a `From:` header is spoofable, so:

1. A signed-in Eclipse user mints a **short-lived, single-use link code** in
   Settings › Connections (`POST /channels/link-code`), choosing the channel kind
   and the **control scope**.
2. The user sends `/link <code>` from the external account.
3. `claim_link_code` validates the code (kind match, unexpired, unused), consumes
   it **atomically**, and writes a `ChannelBinding`. Only then can the account act.

Control scopes, least → most privileged:

| Scope | May |
|---|---|
| `viewer` | Read-only commands and `/do` on **read** tools. |
| `assistant` | + free text and `/run` go to the agent. |
| `operator` | + `/do` on an **allow-listed** mutating tool, each gated by `/confirm`. |

## The pipeline

```
provider poll/webhook → ChannelService.handle_inbound
   → idempotency (native message id)
   → resolve binding (or handle /link)
   → per-binding rate limit
   → ChannelDispatcher.dispatch
        '/command'      → control command (help/whoami/…)
        '/do <tool>'    → ONE ToolRegistry (read, or operator+confirm+allowlist)
        '/confirm <tok>'→ complete a pending mutation
        free text       → service.run (agent turn)
   → reply via the outbound transport → audit (category=channel)
```

Every step is enforced in ONE place (`ChannelService`) so no provider can skip
idempotency, scope, or audit.

## Command vocabulary

`/start` `/help` `/whoami` `/bindings` `/link` `/unlink` `/run` `/do` `/confirm`
`/cancel`, plus the explicit mutation verbs `/trade` `/alert` `/backtest`.
Anything that is not a known command is a natural-language agent turn. Usage
help: `python/harness/channels/commands.py`.

### Explicit mutation verbs

`/trade <details>`, `/alert <details>`, `/backtest <details>` are a STRONGER gate
than plain agent text: they require the `operator` scope AND always ask for an
in-channel `/confirm` before running, then execute as an agent turn with a
directive (`python/harness/channels/dispatch.py` `_MUTATION_DIRECTIVES`). A
`viewer`/`assistant` binding can never trigger one. The operation ends on the
agent's own tools, so the effect is still authorized by the Security Gateway; the
verb only adds the operator-scope + confirmation gate in front of it.

## Mutations need an in-channel confirmation

A mutating `/do` (a tool whose permission is not `read`) is refused unless the
binding is `operator` **and** the tool is on the channel's `operatorTools`
allowlist. It then creates a single-use, short-TTL `Confirmation` bound to
`(binding, tool)`; the user replies `/confirm <token>` to execute. The
confirmation is claimed atomically (a second use is rejected). The underlying
effect is still authorized by the Security Gateway.

> **Not a bypass.** The channel never self-authorizes an effect. `/do` builds a
> `ToolContext` whose `authorize_effect` is `make_security_authorizer(...)`, so a
> mutating tool passes through the same gateway, floor and policy as an agent
> tool call. The `operatorTools` allowlist is an ADDITIONAL operator bound.

## Providers

Providers split by transport (ADR-H200):

| Kind | Transport | Inbound | Public endpoint? |
|---|---|---|---|
| `telegram` | pull | `getUpdates` long-poll + `sendMessage` | **No** |
| `discord` | pull | Gateway WebSocket bot + REST | **No** |
| `email` | pull | IMAP poll + SMTP replies | **No** |
| `slack` | both | Socket Mode (no public URL) or Events API (signed) + Web API replies | **No / Yes** |
| `lark` | both | WebSocket long connection (`lark-oapi`) or event webhook (verified/decrypted) + IM API replies | **No / Yes** |
| `teams` | push | Bot Framework webhook (JWT verified) + connector replies | **Yes** |
| `google_chat` | push | Chat app webhook (Google JWT verified) + Chat API replies | **Yes** |
| `whatsapp` | push | Cloud API (signed) + Graph API replies | **Yes** |
| `webhook` | push | signed generic inbound + HTTP reply | **Yes** |

The provider contract is declared once in `channels/provider.py` +
`channels/registry.py`: kind, label, inbound mode, config fields, required
credentials and capabilities. The service, webhook router and Connections UI all
read from that registry, so adding a provider is a spec + a factory.

**Pull channels** need no public endpoint, so `npm install && npm run dev` stays
zero-config. **Push channels** receive inbound at the ONE public route
`POST /channels/webhook/{kind}`, which is **signature-verified** — the caller is a
third party that cannot present the operator token, so the HMAC over the RAW body
(`channels/verify.py`) is the gate. Slack uses the v0 scheme with a 5-minute
replay window; WhatsApp uses `X-Hub-Signature-256`; the generic webhook uses
`X-Eclipse-Signature: sha256=<hmac>`. A missing/mismatched signature is refused.
The Next.js middleware exempts `/api/channels/webhook/` from the session gate; the
front-door route forwards the raw body byte-for-byte plus only the signature
headers.

Config fields (all visible in Settings → Connections):

- Telegram / Discord: `botToken`.
- Email: IMAP/SMTP host/user/pass + `fromAddress`.
- Slack: `botToken`, `appToken` (Socket Mode), `signingSecret` (webhook only),
  `defaultChannel`.
- Lark: `appId`, `appSecret`, `defaultChatId`, `verificationToken`,
  `encryptKey`, `domain`, `useWebsocket`.
- Teams: `appId`, `appPassword`, `tenantId`, `defaultConversationId`,
  `defaultServiceUrl`.
- Google Chat: `credentialsJson` (or `useAdc`), `projectNumber`,
  `defaultSpaceId`, `pubsubAudience`.
- WhatsApp: `accessToken`, `phoneNumberId`, `appSecret`, `verifyToken`.
- Webhook: `replyUrl`, `replyToken`, `webhookSecret`.

### Provider setup guide

| Provider | Required credentials | Inbound setup |
|---|---|---|
| Slack | bot token + app-level token | Enable Socket Mode; subscribe to `message`/`app_mention`. Webhook fallback needs the signing secret + Event Subscriptions URL. |
| Lark | app id + app secret | Preferred: install `lark-oapi` (the `channels` extra) and keep `useWebsocket=true`. Webhook fallback: subscribe to `im.message.receive_v1`, set verification token and optional encrypt key. |
| Teams | bot app id + app password | Azure Bot messaging endpoint = `/api/channels/webhook/teams`. JWT is validated against Bot Framework OpenID metadata; `serviceUrl` must be a Microsoft host. |
| Google Chat | service-account JSON (or ADC) | Chat app HTTP endpoint = `/api/channels/webhook/google_chat`; `projectNumber` is the expected JWT audience. |
| WhatsApp | access token + phone number id + app secret + verify token | Meta webhook URL = `/api/channels/webhook/whatsapp`. |

The public webhook base is the app origin, e.g.
`https://your-host/api/channels/webhook/{kind}`. Slack Socket Mode and Lark
WebSocket need **no** public URL.

### Public URL (Teams / Google Chat / WhatsApp)

Eclipse is local-first; these three providers need a public HTTPS origin that
forwards to the Next.js app (default `http://127.0.0.1:3000`). A tunnel is
enough for a single user:

```bash
cloudflared tunnel --url http://127.0.0.1:3000
# or: ngrok http 3000
```

Use the tunnel's HTTPS origin as the webhook base in each provider console:
`https://<tunnel-host>/api/channels/webhook/teams` (and likewise
`/google_chat`, `/whatsapp`). Do **not** point providers at the Python runtime
port `8765`; the Next.js route is the signature-preserving entry point.
`HARNESS_CALLBACK_URL` is a different setting (runtime → app callback), not the
public webhook origin.

### Attachments

Inbound attachments are normalized into provider-neutral metadata
(`Attachment`: name, MIME type, size, reference). The agent receives that
metadata in the turn context (plus a compact note in the query) and is told not
to invent contents; the channel never silently downloads or executes a file.

Outbound files are supported by `POST /channels/send`:

```json
{
  "kind": "slack",
  "chat": "C123",
  "text": "see attached",
  "attachments": [
    {"name": "report.pdf", "mimeType": "application/pdf", "contentBase64": "..."},
    {"name": "chart.png", "mimeType": "image/png", "url": "https://..."}
  ]
}
```

Limits: 10 files per send, 10 MB per file, HTTPS-only URLs, no redirects.
Slack, Lark, Google Chat, Teams, WhatsApp and the generic webhook upload or
attach natively; other providers currently send text only.

(WhatsApp ships the official Cloud API path; the unofficial local
Baileys/WhatsApp Web path is deliberately not included.)

## Configuration & secrets

Non-sensitive channel config lives in `ChannelConfig` on `agent-memory.db`.
**Credentials are encrypted at rest.** When a channel is saved, every sensitive
key (`*token*`, `*password*`, `*secret*`, `*webhook*`, `*key*`, …) is encrypted
with a Fernet key and written as ciphertext to the `ChannelSecret` table — the
plaintext never reaches the database, the config JSON, a log, or an API response.
The key lives OUTSIDE the DB in `.black-eclipse/channels/secret.key` (0600; env
override `BLACK_ECLIPSE_CHANNELS_SECRET_KEY`), the same pattern as the Plugin
Platform.

`GET /channels` never returns a value: a configured credential is echoed as a
redacted presence marker (`"botToken": "***"`) plus a `secrets` name list, with
`secretsEncrypted` reporting whether the vault is active.

Resolution order for a credential (`ChannelService.secret_value`):

1. the encrypted vault (`ChannelSecret`), then
2. the config value — a legacy literal (from before the vault) or a
   `secret://<provider>/<name>` reference resolved through the Security Gateway's
   `SecretsManager`.

If `cryptography` is unavailable the vault reports `secretsEncrypted: false` and a
sensitive value falls back to the legacy literal config so zero-config still
works — an honest degradation, never a silent plaintext write when the vault is
present. Deleting a channel (`DELETE /channels/{kind}`) purges its secrets too.

## Model for autonomous turns

A channel has no front door to resolve LLM config, so an agent turn uses the
runtime-wide background model (`HARNESS_CHANNEL_*` → `HARNESS_JOB_*` → default),
exactly like `jobs` and `automation`. See `channels/config.py`.

## HTTP surface (`/channels/*`, operator-gated)

| Method | Path | Purpose |
|---|---|---|
| GET | `/channels/health` | Gateway status, pollers, bindings, model |
| GET | `/channels` | Per-channel config (redacted) |
| PUT | `/channels/{kind}` | Enable + set config |
| DELETE | `/channels/{kind}` | Disable + clear config |
| POST | `/channels/link-code` | Mint a link code (kind + scope) |
| GET | `/channels/bindings` | List bindings |
| POST | `/channels/bindings/{id}/scope` | Change a binding's scope |
| DELETE | `/channels/bindings/{id}` | Revoke a binding |
| POST | `/channels/inbound` | Ingest a normalized message (operator; UI/tests) |
| POST | `/channels/send` | Send text and/or up to 10 files through a configured channel (the ONE sender) |
| GET | `/channels/messages` | Recent inbound/outbound history |
| GET | `/channels/webhook/{kind}` | Public provider handshake (WhatsApp `hub.challenge`) |
| POST | `/channels/webhook/{kind}` | Public signed inbound (slack/lark/teams/google_chat/whatsapp/webhook) |

### The one-sender primitive

`POST /channels/send {kind, chat, text}` sends through a configured channel's
transport (`ChannelService.send_outbound`) — the ONE outbound sender any
subsystem can use, so nothing re-implements a provider. It builds the transport
transiently when the poller is not running, records the delivery, and never
raises for a send failure (`{ok: false, reason}`).

## Notifications

A remote message is announced app-wide by `ChannelActivityWatcher`
(`src/lib/notifications/channel-watcher.tsx`, mounted in the root layout). It
polls `GET /api/channels/messages`, diffs new inbound messages with the pure
`channel-diff.ts`, and raises the shared `be:alert-notify` event (tab `settings`,
kind `agent`). The first poll seeds without notifying, so booting never replays
history; outbound replies are never announced.

## Configuration flags

| Env var | Meaning |
|---|---|
| `HARNESS_CHANNELS_ENABLED` | Subsystem on/off (default on) |
| `HARNESS_CHANNELS_POLLING` | Start local pollers (default on) |
| `HARNESS_CHANNELS_TURNS_PER_HOUR` | Per-binding autonomous-turn budget |
| `HARNESS_CHANNELS_LINK_TTL_S` | Link-code lifetime (default 600s) |
| `HARNESS_CHANNELS_CONFIRM_TTL_S` | Confirmation lifetime (default 120s) |
| `HARNESS_CHANNEL_PROVIDER` / `_MODEL` / `_BASE_URL` / `_API_KEY` | Agent-turn model |

## Tests

`python/tests/test_channels_core.py` (store/identity/dispatch/confirmation),
`python/tests/test_channels_api.py` (the `/channels/*` surface),
`python/tests/test_channels_registry.py` (registry + fast ACK),
`test_channels_{slack,lark,teams,google_chat}.py` (provider parsing, signatures,
token caching and outbound payloads).

`python/scripts/channels_smoke.py` is the live smoke runner (`--health`,
`--list`, `--link KIND`, `--send KIND CHAT TEXT`). It talks to a running runtime
with `HARNESS_PY_URL` (default `http://127.0.0.1:8765`) and `CRON_SECRET`.
