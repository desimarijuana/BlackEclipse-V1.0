"""The Channel Gateway service — the process-wide facade.

Owns the store, the dispatcher, the running provider pollers and the operator API
used by Settings › Connections. `handle_inbound` is the single entry every
provider calls; it enforces idempotency, binding resolution, rate limiting, reply
delivery and audit in ONE place so no provider can skip a step.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from ..security.ratelimit import RateLimiter
from .config import (
    REDACTED,
    channel_model_settings,
    channels_enabled,
    is_sensitive_key,
    polling_enabled,
    redact_config,
    resolve_secret_like,
    turns_per_hour,
)
from .secrets import ChannelSecrets, SecretUnavailable
from .dispatch import ChannelDispatcher
from .identity import claim_link_code, create_link_code
from .model import CHANNEL_KINDS, ChannelBinding, DispatchResult, InboundMessage, new_id
from .store import ChannelStore
from .transport import OutboundMessage

log = logging.getLogger("harness.channels.service")

# Kinds that own a background poll/stream task. Push providers (slack, whatsapp,
# webhook) receive inbound at the webhook route and need only an outbound
# transport, so they are registered without a task.
_POLL_KINDS = {"telegram", "discord", "email"}

# Bound for an outbound send via the one-sender primitive.
_MAX_OUTBOUND = 4000


class ChannelService:
    def __init__(self, service: Any) -> None:
        self._service = service
        self.store = ChannelStore(getattr(service, "store", None))
        # Credentials are encrypted at rest; only ciphertext reaches the DB.
        self.secretbox = ChannelSecrets(self.store)
        self._dispatcher = ChannelDispatcher(self._service, self.store, config_for=self.config_for)
        self._outbound: dict[str, Any] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        budget = max(1, turns_per_hour())
        self._limiter = RateLimiter(rate_per_minute=budget / 60.0, burst=budget)
        self._started = False

    # ── config ───────────────────────────────────────────────────────────────
    def config_for(self, kind: str) -> dict[str, Any]:
        row = self.store.get_config(kind)
        return dict(row["config"]) if row else {}

    def _enabled(self, kind: str) -> bool:
        row = self.store.get_config(kind)
        return bool(row and row["enabled"])

    def configure(self, kind: str, *, enabled: bool, config: dict[str, Any]) -> dict[str, Any]:
        """Persist a channel's config (operator-only). Restarts its poller live.

        Sensitive values (tokens, passwords, signing secrets) are moved into the
        encrypted vault; only their NAME is retained elsewhere. A non-sensitive
        value stays in the config JSON. If the vault is unavailable, a sensitive
        value falls back to the config JSON (zero-config preserved) — logged, and
        surfaced honestly by `secretsEncrypted`.
        """
        if kind not in CHANNEL_KINDS:
            raise ValueError(f"unknown channel kind: {kind}")
        existing = self.config_for(kind)
        merged = {**existing, **(config or {})}
        plain: dict[str, Any] = {}
        for key, value in merged.items():
            if not is_sensitive_key(key):
                plain[key] = value
                continue
            if value in (None, ""):
                continue
            if self.secretbox.available:
                try:
                    self.secretbox.set(kind, key, str(value))
                    continue
                except SecretUnavailable:
                    pass
            plain[key] = value  # legacy fallback: not encrypted at rest
        self.store.set_config(kind, enabled=enabled, config=plain)
        self._refresh_provider(kind)
        return self.describe_config(kind)

    def describe_config(self, kind: str) -> dict[str, Any]:
        row = self.store.get_config(kind)
        plain = dict(row["config"]) if row else {}
        names = self.secretbox.names(kind) if self.secretbox.available else []
        # Sensitive keys present in the vault are echoed as a redacted PRESENCE
        # marker, so the UI can say "configured" without ever seeing a value.
        view = {**plain, **{name: REDACTED for name in names}}
        return {
            "channel": kind,
            "enabled": bool(row and row["enabled"]),
            "configured": self._is_configured(kind, view),
            "config": redact_config(view),
            "secrets": sorted(set(names) | {k for k in plain if is_sensitive_key(k)}),
            "secretsEncrypted": self.secretbox.available,
            "updatedAt": row["updatedAt"] if row else None,
        }

    def describe_all(self) -> list[dict[str, Any]]:
        return [self.describe_config(kind) for kind in CHANNEL_KINDS]

    def _is_configured(self, kind: str, config: Optional[dict[str, Any]] = None) -> bool:
        def _has(key: str) -> bool:
            return bool(self.secret_value(kind, key))

        if kind in ("telegram", "discord", "slack"):
            return _has("botToken")
        if kind == "email":
            return _has("imapHost")
        if kind == "whatsapp":
            return _has("accessToken") and _has("phoneNumberId")
        if kind == "webhook":
            return _has("replyUrl")
        return bool(config)

    def delete_config(self, kind: str) -> bool:
        self._stop_provider(kind)
        if self.secretbox.available:
            try:
                self.secretbox.delete(kind)
            except Exception:  # noqa: BLE001 - best-effort secret cleanup
                log.warning("channel secret cleanup failed", exc_info=True)
        return self.store.delete_config(kind)

    # ── secrets ──────────────────────────────────────────────────────────────
    def _secrets(self) -> Any:
        gateway = getattr(self._service, "security", None)
        return getattr(gateway, "secrets", None) if gateway is not None else None

    def secret_value(self, kind: str, key: str) -> str:
        """The resolved value of one config field.

        Order: the encrypted vault, then a config value (a legacy literal or a
        `secret://` reference resolved through the Security Gateway's secrets
        manager). Empty when absent. Never logs or exposes the value.
        """
        vaulted: Optional[str] = None
        if self.secretbox.available:
            try:
                vaulted = self.secretbox.get(kind, key)
            except SecretUnavailable:
                vaulted = None
        raw = vaulted if vaulted is not None else self.config_for(kind).get(key)
        return str(resolve_secret_like(self._secrets(), raw) or "").strip()

    # ── linking ──────────────────────────────────────────────────────────────
    def create_link_code(
        self, *, kind: str, scope: str, user_id: Optional[str], tenant_id: Optional[str],
        ttl_s: Optional[int] = None,
    ) -> dict[str, Any]:
        if kind not in CHANNEL_KINDS:
            raise ValueError(f"unknown channel kind: {kind}")
        code = create_link_code(
            self.store, kind=kind, user_id=user_id, tenant_id=tenant_id, scope=scope, ttl_s=ttl_s
        )
        return code.to_dict()

    def list_bindings(self, *, kind: Optional[str] = None) -> list[dict[str, Any]]:
        return [b.to_dict() for b in self.store.list_bindings(kind=kind)]

    def set_binding_scope(self, binding_id: str, scope: str) -> bool:
        return self.store.set_binding_scope(binding_id, scope)

    def revoke_binding(self, binding_id: str) -> bool:
        return self.store.revoke_binding(binding_id)

    # ── inbound ──────────────────────────────────────────────────────────────
    async def handle_inbound(self, message: InboundMessage) -> Optional[DispatchResult]:
        """Process one inbound message end-to-end. Returns None for a duplicate."""
        if not message.platform_message_id:
            message.platform_message_id = new_id("chpm")
        if not self.store.mark_seen(message.kind, message.platform_message_id):
            return None  # idempotent: a re-delivered update is ignored

        binding = self.store.find_binding(message.kind, message.external_id)
        if binding is None or binding.status != "active":
            result = self._handle_unlinked(message)
            await self._deliver(message.kind, message.external_chat, result.reply, binding_id=None)
            self._record(message, binding=None, result=result)
            return result

        if not self._limiter.allow(binding.id):
            result = DispatchResult(
                status="rate_limited",
                reply="You're sending messages too quickly — please wait a moment.",
            )
            await self._deliver(message.kind, message.external_chat, result.reply, binding_id=binding.id)
            self._record(message, binding=binding, result=result)
            return result

        self.store.touch_binding(binding.id)
        try:
            result = await self._dispatcher.dispatch(binding, message.text)
        except Exception as exc:  # noqa: BLE001 - a dispatch failure is an honest error
            log.warning("channel dispatch failed", exc_info=True)
            result = DispatchResult(status="error", reply=f"Something went wrong: {exc}")

        await self._deliver(message.kind, message.external_chat, result.reply, binding_id=binding.id)
        self._record(message, binding=binding, result=result)
        return result

    def _handle_unlinked(self, message: InboundMessage) -> DispatchResult:
        text = message.text.strip()
        if text.lower().startswith("/link"):
            parts = text.split(maxsplit=1)
            code = parts[1].strip() if len(parts) > 1 else ""
            if not code:
                return DispatchResult(status="error", reply="Usage: /link <code>")
            binding, reason = claim_link_code(
                self.store,
                kind=message.kind,
                code=code,
                external_id=message.external_id,
                external_chat=message.external_chat,
                display_name=message.display_name,
            )
            if binding is None:
                return DispatchResult(status="error", reply=reason)
            return DispatchResult(
                status="linked",
                reply=(
                    "✅ Linked to Eclipse.\n\n"
                    + self._dispatcher._whoami(binding)  # noqa: SLF001 - same package
                    + "\n\nSend /help to see what you can do."
                ),
                details={"bindingId": binding.id},
            )
        return DispatchResult(
            status="unlinked",
            reply=(
                "This account isn't linked to Eclipse yet.\n"
                "Open Eclipse › Settings › Connections, generate a link code, then send "
                "/link <code> here."
            ),
        )

    # ── reply delivery ───────────────────────────────────────────────────────
    async def _deliver(self, kind: str, chat: str, text: str, *, binding_id: Optional[str]) -> None:
        if not text:
            return
        transport = self._outbound.get(kind)
        delivered = False
        if transport is not None:
            try:
                delivered = await transport.send(OutboundMessage(kind=kind, external_chat=chat, text=text))
            except Exception:  # noqa: BLE001 - a delivery failure is logged, not raised
                log.warning("channel delivery failed for %s", kind, exc_info=True)
        self._record_outbound(kind, chat, binding_id, text, delivered)

    def _record_outbound(self, kind: str, chat: str, binding_id: Optional[str], text: str, delivered: bool) -> None:
        try:
            self.store.record_message(
                kind=kind, direction="out", external_id=None, external_chat=chat,
                binding_id=binding_id, platform_message_id=None, text=text,
                status="delivered" if delivered else "not_delivered",
            )
        except Exception:  # noqa: BLE001
            log.debug("channel outbound record failed", exc_info=True)
        self._audit(
            type="channel.reply", action="reply", resource=kind, result="sent" if delivered else "undelivered",
            payload={"bindingId": binding_id},
        )

    def _record(self, message: InboundMessage, *, binding: Optional[ChannelBinding], result: DispatchResult) -> None:
        try:
            self.store.record_message(
                kind=message.kind, direction="in", external_id=message.external_id,
                external_chat=message.external_chat, binding_id=binding.id if binding else None,
                platform_message_id=message.platform_message_id, text=message.text,
                status=result.status, run_id=result.run_id,
            )
        except Exception:  # noqa: BLE001
            log.debug("channel inbound record failed", exc_info=True)
        self._audit(
            type="channel.inbound", action="dispatch", resource=message.kind,
            result=result.status, user_id=binding.user_id if binding else None,
            tenant_id=binding.tenant_id if binding else None,
            payload={"bindingId": binding.id if binding else None, "runId": result.run_id},
        )

    def _audit(self, **kwargs: Any) -> None:
        gateway = getattr(self._service, "security", None)
        audit = getattr(gateway, "audit", None) if gateway is not None else None
        if audit is None:
            return
        try:
            kwargs.setdefault("category", "channel")
            audit.record(**kwargs)
        except Exception:  # noqa: BLE001 - audit must never break delivery
            log.debug("channel audit failed", exc_info=True)

    # ── one-sender primitive ─────────────────────────────────────────────────
    async def send_outbound(self, kind: str, external_chat: str, text: str) -> dict[str, Any]:
        """Send one outbound message through a configured channel's transport.

        This is the ONE outbound sender: any subsystem (or the operator API) can
        push a message to a linked destination without re-implementing a provider.
        It reuses the stored config (built transiently if the poller is not
        running) and records the delivery. Never raises for a send failure.
        """
        if kind not in CHANNEL_KINDS:
            raise ValueError(f"unknown channel kind: {kind}")
        body = str(text or "").strip()
        if not body:
            return {"ok": False, "reason": "empty message"}
        if not external_chat:
            return {"ok": False, "reason": "no destination"}
        provider = self._outbound.get(kind) or self._build_provider(kind)
        if provider is None:
            return {"ok": False, "reason": "channel is not configured"}
        try:
            sent = await provider.send(
                OutboundMessage(kind=kind, external_chat=external_chat, text=body[:_MAX_OUTBOUND])
            )
        except Exception:  # noqa: BLE001 - a send failure is reported, not raised
            log.warning("channel outbound send failed", exc_info=True)
            sent = False
        self._record_outbound(kind, external_chat, None, body, bool(sent))
        return {"ok": bool(sent)}

    # ── provider lifecycle ───────────────────────────────────────────────────
    def start(self) -> None:
        if self._started or not channels_enabled():
            return
        self._started = True
        for kind in CHANNEL_KINDS:
            self._start_provider(kind)

    async def stop(self) -> None:
        for kind in list(self._tasks):
            self._stop_provider(kind)
        self._outbound.clear()
        self._started = False

    def _start_provider(self, kind: str) -> None:
        if kind in self._outbound or not self._enabled(kind):
            return
        provider = self._build_provider(kind)
        if provider is None:
            return
        self._outbound[kind] = provider
        # Only pull/stream providers own a background task; push providers
        # (slack/whatsapp/webhook) receive inbound at the webhook route and only
        # need the outbound transport registered above. Pollers are also skipped
        # when polling is disabled (outbound still works).
        if kind not in _POLL_KINDS or not polling_enabled():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            log.debug("no running loop; channel provider %s deferred", kind)
            return
        self._tasks[kind] = loop.create_task(self._run_provider(kind, provider))

    async def _run_provider(self, kind: str, provider: Any) -> None:
        try:
            await provider.run(self.handle_inbound)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a provider crash must not kill the runtime
            log.warning("channel provider %s stopped unexpectedly", kind, exc_info=True)

    def _stop_provider(self, kind: str) -> None:
        task = self._tasks.pop(kind, None)
        provider = self._outbound.pop(kind, None)
        if task is not None:
            task.cancel()
        if provider is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(provider.stop())
            except RuntimeError:
                pass

    def _refresh_provider(self, kind: str) -> None:
        if self._started:
            self._stop_provider(kind)
            self._start_provider(kind)

    def _build_provider(self, kind: str) -> Any:
        cfg = self.config_for(kind)

        def _s(key: str) -> str:
            return self.secret_value(kind, key)

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
            from .providers.webhooks import SlackProvider  # noqa: PLC0415

            return SlackProvider(bot_token=token)
        if kind == "whatsapp":
            token, phone = _s("accessToken"), _s("phoneNumberId")
            if not token or not phone:
                log.info("whatsapp channel enabled but no access token / phone number id configured")
                return None
            from .providers.webhooks import WhatsappProvider  # noqa: PLC0415

            return WhatsappProvider(
                access_token=token, phone_number_id=phone,
                api_version=str(cfg.get("apiVersion") or "v21.0"),
            )
        if kind == "webhook":
            url = _s("replyUrl")
            if not url:
                log.info("webhook channel enabled but no reply URL configured")
                return None
            from .providers.webhooks import WebhookProvider  # noqa: PLC0415

            return WebhookProvider(reply_url=url, token=_s("replyToken"))
        return None

    # ── introspection ────────────────────────────────────────────────────────
    def list_messages(self, *, kind: Optional[str] = None, binding_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.list_messages(kind=kind, binding_id=binding_id, limit=limit)

    def health(self) -> dict[str, Any]:
        return {
            "enabled": channels_enabled(),
            "polling": polling_enabled(),
            "started": self._started,
            "activePollers": sorted(self._tasks),
            "channels": self.describe_all(),
            "bindings": len(self.store.list_bindings(limit=1000)),
            "turnsPerHour": turns_per_hour(),
            "model": {
                "provider": channel_model_settings().provider,
                "model": channel_model_settings().model,
            },
        }

    def expire_pending(self) -> None:
        """Mark expired confirmations (called opportunistically)."""
        from ..persistence import now_iso  # noqa: PLC0415

        try:
            self.store.expire_confirmations(before_iso=now_iso())
        except Exception:  # noqa: BLE001
            pass


__all__ = ["ChannelService"]
