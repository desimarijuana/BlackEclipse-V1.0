"""The Channel Gateway provider registry.

One place to declare a provider's operator-visible contract and how to build
its transport. Keep provider modules free of registry knowledge: they expose a
class, the registry decides when it applies.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .provider import ConfigField, ProviderContext, ProviderSpec

log = logging.getLogger("harness.channels.registry")


_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        kind="telegram",
        label="Telegram",
        description="Bot long-poll inbound and sendMessage outbound. No public URL required.",
        inbound_mode="poll",
        config_fields=(
            ConfigField("botToken", "Bot token", secret=True, required=True, placeholder="123456:ABC-DEF."),
        ),
    ),
    ProviderSpec(
        kind="discord",
        label="Discord",
        description="Gateway WebSocket inbound and REST outbound. No public URL required.",
        inbound_mode="poll",
        config_fields=(
            ConfigField("botToken", "Bot token", secret=True, required=True),
        ),
    ),
    ProviderSpec(
        kind="email",
        label="Email",
        description="IMAP inbox polling and SMTP replies. No public URL required.",
        inbound_mode="poll",
        config_fields=(
            ConfigField("imapHost", "IMAP host", required=True),
            ConfigField("imapUser", "IMAP username"),
            ConfigField("imapPass", "IMAP password", secret=True),
            ConfigField("imapPort", "IMAP port", placeholder="993"),
            ConfigField("smtpHost", "SMTP host"),
            ConfigField("smtpPort", "SMTP port", placeholder="587"),
            ConfigField("smtpUser", "SMTP username"),
            ConfigField("smtpPass", "SMTP password", secret=True),
            ConfigField("fromAddress", "From address"),
            ConfigField("pollSeconds", "Poll interval (seconds)", placeholder="60"),
        ),
    ),
    ProviderSpec(
        kind="slack",
        label="Slack",
        description="Socket Mode (no public URL) or Events webhook inbound; Web API outbound.",
        inbound_mode="both",
        capabilities=frozenset({"threads", "reactions", "files"}),
        config_fields=(
            ConfigField("botToken", "Bot token", secret=True, required=True, placeholder="xoxb-..."),
            ConfigField("signingSecret", "Signing secret", secret=True, hint="Required for the HTTP webhook path"),
            ConfigField("appToken", "App-level token", secret=True, placeholder="xapp-..."),
            ConfigField("defaultChannel", "Default channel ID"),
        ),
    ),
    ProviderSpec(
        kind="whatsapp",
        label="WhatsApp",
        description="Meta WhatsApp Cloud API webhook inbound and Graph API outbound.",
        inbound_mode="push",
        capabilities=frozenset({"templates", "media"}),
        config_fields=(
            ConfigField("accessToken", "Access token", secret=True, required=True),
            ConfigField("phoneNumberId", "Phone number ID", required=True),
            ConfigField("appSecret", "App secret", secret=True, hint="Required for inbound signature verification"),
            ConfigField("verifyToken", "Webhook verify token", secret=True, hint="Required for the subscription handshake"),
            ConfigField("apiVersion", "Graph API version", placeholder="v21.0"),
        ),
    ),
    ProviderSpec(
        kind="teams",
        label="Microsoft Teams",
        description="Bot Framework webhook inbound and connector outbound.",
        inbound_mode="push",
        capabilities=frozenset({"threads", "cards"}),
        config_fields=(
            ConfigField("appId", "Bot app ID", required=True),
            ConfigField("appPassword", "Bot app password", secret=True, required=True),
            ConfigField("tenantId", "Tenant ID", placeholder="common"),
            ConfigField("defaultConversationId", "Default conversation ID"),
            ConfigField("defaultServiceUrl", "Default service URL", placeholder="https://smba.trafficmanager.net/teams"),
        ),
    ),
    ProviderSpec(
        kind="google_chat",
        label="Google Chat",
        description="Chat app webhook inbound and Chat API outbound via service account or ADC.",
        inbound_mode="push",
        capabilities=frozenset({"threads", "cards"}),
        any_required=(("credentialsJson",), ("useAdc",)),
        flag_fields=frozenset({"useAdc"}),
        config_fields=(
            ConfigField("credentialsJson", "Service-account JSON", secret=True, hint="Inline JSON or a key-file path"),
            ConfigField("useAdc", "Use Application Default Credentials", placeholder="true"),
            ConfigField("projectNumber", "Google Cloud project number", hint="Required to verify inbound webhooks"),
            ConfigField("defaultSpaceId", "Default space ID", placeholder="spaces/AAAA..."),
            ConfigField("pubsubAudience", "Pub/Sub audience", hint="Alternative to project number for Pub/Sub delivery"),
        ),
    ),
    ProviderSpec(
        kind="lark",
        label="Lark / Feishu",
        description="Lark WebSocket (no public URL) or event webhook inbound; IM API outbound.",
        inbound_mode="both",
        capabilities=frozenset({"threads", "rich_text", "reactions"}),
        config_fields=(
            ConfigField("appId", "App ID", required=True),
            ConfigField("appSecret", "App secret", secret=True, required=True),
            ConfigField("defaultChatId", "Default chat ID"),
            ConfigField("verificationToken", "Event verification token", secret=True),
            ConfigField("encryptKey", "Event encrypt key", secret=True),
            ConfigField("domain", "Domain", placeholder="open.feishu.cn"),
            ConfigField("useWebsocket", "Use WebSocket long connection", placeholder="true"),
        ),
    ),
    ProviderSpec(
        kind="webhook",
        label="Webhook",
        description="Generic signed webhook inbound and one authenticated HTTP POST outbound.",
        inbound_mode="push",
        config_fields=(
            ConfigField("replyUrl", "Reply URL", required=True),
            ConfigField("replyToken", "Reply bearer token", secret=True),
            ConfigField("webhookSecret", "Inbound signing secret", secret=True),
        ),
    ),
)

PROVIDERS: dict[str, ProviderSpec] = {spec.kind: spec for spec in _SPECS}
KINDS: tuple[str, ...] = tuple(PROVIDERS)
PUSH_KINDS: frozenset[str] = frozenset(
    k for k, s in PROVIDERS.items() if s.inbound_mode in ("push", "both")
)
POLL_KINDS: frozenset[str] = frozenset(
    k for k, s in PROVIDERS.items() if s.inbound_mode in ("poll", "both")
)


def spec_for(kind: str) -> Optional[ProviderSpec]:
    return PROVIDERS.get(kind)


def is_configured(kind: str, get: Any) -> bool:
    spec = PROVIDERS.get(kind)
    return bool(spec and spec.is_configured(get))


def build_provider(ctx: ProviderContext) -> Any:
    """Construct a transport for `ctx.kind`, or None when it is incomplete.

    A missing required credential is an honest None: the channel is simply not
    running. Import provider modules lazily so the registry stays cheap and a
    missing optional dependency never blocks boot.
    """
    kind = ctx.kind
    cfg = ctx.config

    def _s(key: str) -> str:
        return ctx.secret(key)

    if kind == "telegram":
        token = _s("botToken")
        if not token:
            log.info("telegram channel enabled but no bot token configured")
            return None
        from .providers.telegram import TelegramProvider  # noqa: PLC0415

        return TelegramProvider(bot_token=token)

    if kind == "discord":
        token = _s("botToken")
        if not token:
            log.info("discord channel enabled but no bot token configured")
            return None
        from .providers.discord import DiscordProvider  # noqa: PLC0415

        return DiscordProvider(bot_token=token)

    if kind == "email":
        host = _s("imapHost")
        if not host:
            log.info("email channel enabled but no IMAP host configured")
            return None
        from .providers.email import EmailProvider  # noqa: PLC0415

        return EmailProvider(
            imap_host=host,
            imap_user=_s("imapUser"),
            imap_pass=_s("imapPass"),
            imap_port=int(cfg.get("imapPort") or 993),
            smtp_host=_s("smtpHost"),
            smtp_port=int(cfg.get("smtpPort") or 587),
            smtp_user=_s("smtpUser"),
            smtp_pass=_s("smtpPass"),
            from_address=_s("fromAddress"),
            poll_seconds=int(cfg.get("pollSeconds") or 60),
        )

    if kind == "slack":
        token = _s("botToken")
        if not token:
            log.info("slack channel enabled but no bot token configured")
            return None
        from .providers.slack import SlackProvider  # noqa: PLC0415

        return SlackProvider(
            bot_token=token,
            app_token=_s("appToken"),
            signing_secret=_s("signingSecret"),
            default_channel=str(cfg.get("defaultChannel") or ""),
        )

    if kind == "whatsapp":
        token, phone = _s("accessToken"), _s("phoneNumberId")
        if not token or not phone:
            log.info("whatsapp channel enabled but no access token / phone number id configured")
            return None
        from .providers.webhooks import WhatsappProvider  # noqa: PLC0415

        return WhatsappProvider(
            access_token=token,
            phone_number_id=phone,
            api_version=str(cfg.get("apiVersion") or "v21.0"),
        )

    if kind == "teams":
        app_id, app_password = _s("appId"), _s("appPassword")
        if not app_id or not app_password:
            log.info("teams channel enabled but no app id / app password configured")
            return None
        from .providers.teams import TeamsProvider  # noqa: PLC0415

        return TeamsProvider(
            app_id=app_id,
            app_password=app_password,
            tenant_id=str(cfg.get("tenantId") or "common"),
            default_conversation_id=_s("defaultConversationId"),
            default_service_url=str(cfg.get("defaultServiceUrl") or ""),
        )

    if kind == "google_chat":
        creds = _s("credentialsJson")
        use_adc = str(cfg.get("useAdc") or "").strip().lower() in ("1", "true", "yes", "on")
        if not creds and not use_adc:
            log.info("google_chat channel enabled but no credentials JSON / ADC configured")
            return None
        from .providers.google_chat import GoogleChatProvider  # noqa: PLC0415

        return GoogleChatProvider(
            credentials_json=creds,
            use_adc=use_adc,
            default_space_id=_s("defaultSpaceId"),
        )

    if kind == "lark":
        app_id, app_secret = _s("appId"), _s("appSecret")
        if not app_id or not app_secret:
            log.info("lark channel enabled but no app id / app secret configured")
            return None
        from .providers.lark import LarkProvider  # noqa: PLC0415

        return LarkProvider(
            app_id=app_id,
            app_secret=app_secret,
            default_chat_id=_s("defaultChatId"),
            domain=str(cfg.get("domain") or "open.feishu.cn"),
            use_websocket=str(cfg.get("useWebsocket") or "true").strip().lower()
            not in ("0", "false", "no", "off"),
        )

    if kind == "webhook":
        url = _s("replyUrl")
        if not url:
            log.info("webhook channel enabled but no reply URL configured")
            return None
        from .providers.webhooks import WebhookProvider  # noqa: PLC0415

        return WebhookProvider(reply_url=url, token=_s("replyToken"))

    return None


__all__ = [
    "KINDS",
    "POLL_KINDS",
    "PROVIDERS",
    "PUSH_KINDS",
    "build_provider",
    "is_configured",
    "spec_for",
]
