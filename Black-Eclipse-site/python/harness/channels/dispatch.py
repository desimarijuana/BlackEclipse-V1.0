"""The dispatch pipeline — the ONE place a channel message becomes an action.

Order, every time:

    parse → scope check → (control command | agent turn | whitelisted tool)
          → confirm gate for mutations → execute → reply

It never runs its own agent loop, tool registry or effect authorizer: an agent
turn goes through `service.run`, a tool goes through the ONE `ToolRegistry`, and a
mutating tool's effect is authorised by the Security Gateway via
`make_security_authorizer`. The channel contributes SCOPE gating and an in-channel
confirmation gate; the gateway remains the effect authority.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Optional

from ..schemas import ModelSettings, RunInput, RunRequest
from . import commands
from .config import channel_model_settings, confirmation_ttl_seconds, resolve_secret_like
from .model import Attachment, ChannelBinding, DispatchResult, new_id, scope_allows
from .store import ChannelStore

log = logging.getLogger("harness.channels.dispatch")

_SCOPE_LABEL = {
    "viewer": "view only",
    "assistant": "ask the agent",
    "operator": "full control (mutations need confirmation)",
}
_MAX_REPLY = 3500

# How an explicit mutation verb becomes an agent directive (executed AFTER the
# operator confirms). The agent already holds the tools and its own effect
# authorizer; the verb adds an operator-scope + confirmation gate in front of it.
_MUTATION_DIRECTIVES = {
    "trade": "Record this trade in the journal/portfolio: {details}. Use the appropriate "
             "journal or portfolio tool and report the exact result (never invent numbers).",
    "alert": "Create this price alert: {details}. Use the alerts capability and confirm the "
             "exact alert that was created.",
    "backtest": "Run this backtest: {details}. Use the quant/backtest tools and report the "
                "resulting metrics.",
}


class ChannelDispatcher:
    def __init__(
        self,
        service: Any,
        store: ChannelStore,
        *,
        config_for: Callable[[str], dict[str, Any]],
    ) -> None:
        self._service = service
        self._store = store
        self._config_for = config_for

    # ── entry ────────────────────────────────────────────────────────────────
    async def dispatch(
        self,
        binding: ChannelBinding,
        message_text: str,
        *,
        attachments: Optional[list[Attachment]] = None,
    ) -> DispatchResult:
        parsed = commands.parse(message_text)
        if parsed.is_command:
            return await self._dispatch_command(binding, parsed)
        return await self._agent_turn(binding, parsed.raw, attachments=attachments)

    async def _dispatch_command(self, binding: ChannelBinding, parsed: commands.ParsedCommand) -> DispatchResult:
        spec = commands.spec_for(parsed.verb)
        if spec is None:
            return DispatchResult(
                status="unknown_command",
                reply=f"Unknown command /{parsed.verb}.\n\n{commands.help_text()}",
            )
        if not scope_allows(binding.scope, spec.scope):
            return DispatchResult(
                status="denied",
                reply=(
                    f"/{spec.name} needs the '{spec.scope}' scope; this account is "
                    f"'{binding.scope}' ({_SCOPE_LABEL.get(binding.scope, binding.scope)})."
                ),
            )
        if parsed.verb in ("start", "help"):
            return DispatchResult(status="ok", reply=commands.help_text())
        if parsed.verb == "whoami":
            return DispatchResult(status="ok", reply=self._whoami(binding))
        if parsed.verb == "bindings":
            return DispatchResult(status="ok", reply=self._bindings(binding))
        if parsed.verb == "unlink":
            self._store.revoke_binding(binding.id)
            return DispatchResult(status="ok", reply="This account is now unlinked from Eclipse.")
        if parsed.verb == "run":
            objective = parsed.args[0] if parsed.args else ""
            if not objective.strip():
                return DispatchResult(status="error", reply="Usage: /run <what you want the agent to do>")
            return await self._agent_turn(binding, objective)
        if parsed.verb == "confirm":
            return await self._confirm(binding, parsed)
        if parsed.verb == "cancel":
            return self._cancel(binding, parsed)
        if parsed.verb == "do":
            return await self._handle_do(binding, parsed, confirmed=False)
        if parsed.verb in commands.MUTATION_VERBS:
            return await self._handle_mutation_verb(binding, parsed, confirmed=False)
        return DispatchResult(status="error", reply="Unsupported command.")

    # ── control replies ──────────────────────────────────────────────────────
    def _whoami(self, binding: ChannelBinding) -> str:
        lines = [
            f"You are linked to Eclipse as {binding.display_name or binding.external_id}.",
            f"Channel: {binding.kind}",
            f"Scope: {binding.scope} ({_SCOPE_LABEL.get(binding.scope, binding.scope)})",
        ]
        if binding.user_id:
            lines.append(f"Eclipse user: {binding.user_id}")
        if binding.tenant_id:
            lines.append(f"Tenant: {binding.tenant_id}")
        return "\n".join(lines)

    def _bindings(self, binding: ChannelBinding) -> str:
        rows = [
            b for b in self._store.list_bindings(limit=200)
            if b.external_id == binding.external_id and b.status == "active"
        ]
        if not rows:
            return "No active bindings."
        return "Active bindings:\n" + "\n".join(
            f"- {b.kind}:{b.external_id} ({b.scope})" for b in rows
        )

    # ── agent turn ───────────────────────────────────────────────────────────
    def _model_settings(self, binding: ChannelBinding) -> ModelSettings:
        base = channel_model_settings()
        override = self._config_for(binding.kind)
        return ModelSettings(
            provider=str(override.get("provider") or base.provider),
            model=str(override.get("model") or base.model),
            base_url=override.get("baseUrl") or base.base_url,
            api_key=resolve_secret_like(self._secrets(), override.get("apiKey")) or base.api_key,
        )

    async def _agent_turn(
        self,
        binding: ChannelBinding,
        text: str,
        *,
        attachments: Optional[list[Attachment]] = None,
    ) -> DispatchResult:
        if not scope_allows(binding.scope, "assistant"):
            return DispatchResult(
                status="denied",
                reply=(
                    "Asking the agent needs the 'assistant' scope or above; this account is "
                    f"'{binding.scope}' ({_SCOPE_LABEL.get(binding.scope, binding.scope)})."
                ),
            )
        query = str(text or "").strip()
        attachment_block = _attachment_context(attachments or [])
        if attachment_block:
            query = f"{query}\n\n{attachment_block}".strip()
        if not query:
            return DispatchResult(status="error", reply="Send a question or /help.")
        run_id = new_id("chr")
        context: dict[str, Any] = {"channel": binding.kind, "bindingId": binding.id}
        if attachments:
            context["attachments"] = [attachment.to_dict() for attachment in attachments]
        request = RunRequest(
            runId=run_id,
            input=RunInput(
                query=query[:4000],
                context=context,
            ),
            agentId=str(self._config_for(binding.kind).get("agentId") or "eclipse-agent"),
            modelSettings=self._model_settings(binding),
            userId=binding.user_id,
            tenantId=binding.tenant_id,
            sessionId=f"channel:{binding.id}",
            conversationId=f"channel-{binding.id}",
            callbackBaseUrl=_callback_url(),
            callbackToken=os.environ.get("CRON_SECRET"),
        )
        try:
            result = await self._service.run(request)
        except Exception as exc:  # noqa: BLE001 - a runtime failure is an honest error
            log.warning("channel agent run failed", exc_info=True)
            return DispatchResult(status="error", reply=f"The agent run failed: {exc}", run_id=run_id)
        output = getattr(result, "output", None)
        status = str(getattr(getattr(result, "status", None), "value", getattr(result, "status", "")))
        if not output:
            error = getattr(result, "error", None)
            detail = getattr(error, "message", None) if error is not None else None
            return DispatchResult(
                status="error",
                reply=detail or "The agent produced no answer.",
                run_id=run_id,
                details={"runStatus": status},
            )
        return DispatchResult(status="ok", reply=str(output)[:_MAX_REPLY], run_id=run_id)

    # ── tool bridge (/do) ────────────────────────────────────────────────────
    async def _handle_do(
        self, binding: ChannelBinding, parsed: commands.ParsedCommand, *, confirmed: bool
    ) -> DispatchResult:
        if not parsed.args:
            return DispatchResult(status="error", reply="Usage: /do <tool> <json-args>")
        raw = parsed.args[0]
        name, _, json_text = raw.partition(" ")
        name = name.strip()
        if not name:
            return DispatchResult(status="error", reply="Usage: /do <tool> <json-args>")
        tool = self._service.registry.get(name)
        if tool is None:
            return DispatchResult(status="error", reply=f"Unknown tool '{name}'.")
        try:
            args = json.loads(json_text) if json_text.strip() else {}
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except (ValueError, TypeError) as exc:
            return DispatchResult(status="error", reply=f"Invalid JSON args: {exc}")

        mutating = tool.permission != "read"
        if mutating:
            if not scope_allows(binding.scope, "operator"):
                return DispatchResult(
                    status="denied",
                    reply=f"'{name}' changes state and needs the 'operator' scope.",
                )
            allowed = self._config_for(binding.kind).get("operatorTools") or []
            if name not in allowed:
                return DispatchResult(
                    status="denied",
                    reply=(
                        f"'{name}' is not on this channel's operator tool allowlist. "
                        "Add it in Settings › Connections to use it here."
                    ),
                )
            if not confirmed:
                confirmation = self._store.create_confirmation(
                    token=new_id("chc").replace("chc_", "")[:8].upper(),
                    binding_id=binding.id,
                    command_text=parsed.raw,
                    action=f"do:{name}",
                    resource=name,
                    expires_at=_utc_plus(confirmation_ttl_seconds()),
                )
                return DispatchResult(
                    status="confirmation_required",
                    reply=(
                        f"⚠️ '{name}' changes state.\nReply /confirm {confirmation.token} within "
                        f"{confirmation_ttl_seconds()}s to run it."
                    ),
                    details={"confirmationToken": confirmation.token},
                )
        return await self._execute_tool(binding, name, args)

    async def _execute_tool(self, binding: ChannelBinding, name: str, args: dict[str, Any]) -> DispatchResult:
        from ..tools import ToolContext  # noqa: PLC0415 - avoid an import cycle at module load

        run_id = new_id("chr")
        ctx = ToolContext(
            run_id=run_id,
            log=lambda *_: None,
            user_id=binding.user_id,
            tenant_id=binding.tenant_id,
            tool_registry=self._service.registry,
        )
        gateway = getattr(self._service, "security", None)
        if gateway is not None:
            try:
                from ..security.integration import make_security_authorizer  # noqa: PLC0415

                ctx.authorize_effect = make_security_authorizer(None, run_id=run_id, gateway=gateway)
            except Exception:  # noqa: BLE001 - no authorizer ⇒ non-read tools are refused
                ctx.authorize_effect = None
        try:
            result = await self._service.registry.execute(name, f"ch_{run_id}", dict(args), ctx)
        except Exception as exc:  # noqa: BLE001 - a tool failure is an honest error
            log.warning("channel tool call failed", exc_info=True)
            return DispatchResult(status="error", reply=f"Tool '{name}' failed: {exc}", run_id=run_id)
        if result.ok:
            return DispatchResult(status="ok", reply=str(result.text)[:_MAX_REPLY], run_id=run_id)
        error = result.error
        message = getattr(error, "message", None) if error is not None else None
        return DispatchResult(
            status="error", reply=message or f"Tool '{name}' was refused.", run_id=run_id
        )

    # ── explicit mutation verbs (/trade, /alert, /backtest) ───────────────────
    async def _handle_mutation_verb(
        self, binding: ChannelBinding, parsed: commands.ParsedCommand, *, confirmed: bool
    ) -> DispatchResult:
        detail = parsed.args[0].strip() if parsed.args else ""
        if not detail:
            return DispatchResult(status="error", reply=f"Usage: /{parsed.verb} <details>")
        directive = _MUTATION_DIRECTIVES[parsed.verb].format(details=detail)
        if not confirmed:
            confirmation = self._store.create_confirmation(
                token=new_id("chc").replace("chc_", "")[:8].upper(),
                binding_id=binding.id,
                command_text=parsed.raw,
                action=f"verb:{parsed.verb}",
                resource=parsed.verb,
                expires_at=_utc_plus(confirmation_ttl_seconds()),
            )
            return DispatchResult(
                status="confirmation_required",
                reply=(
                    f"⚠️ /{parsed.verb} changes state.\nReply /confirm {confirmation.token} within "
                    f"{confirmation_ttl_seconds()}s to run it."
                ),
                details={"confirmationToken": confirmation.token},
            )
        return await self._agent_turn(binding, directive)

    # ── confirmations ────────────────────────────────────────────────────────
    async def _confirm(self, binding: ChannelBinding, parsed: commands.ParsedCommand) -> DispatchResult:
        if not parsed.args:
            return DispatchResult(status="error", reply="Usage: /confirm <token>")
        token = parsed.args[0].strip()
        existing = self._store.get_confirmation(token)
        if existing is None or existing.binding_id != binding.id:
            return DispatchResult(status="error", reply="That confirmation token is not valid here.")
        if existing.status != "pending":
            return DispatchResult(status="error", reply=f"That confirmation is already {existing.status}.")
        if _is_expired(existing.expires_at):
            self._store.set_confirmation_status(token, "expired")
            return DispatchResult(status="error", reply="That confirmation has expired.")
        claimed = self._store.claim_confirmation(token)
        if claimed is None:
            return DispatchResult(status="error", reply="That confirmation could not be claimed.")
        if claimed.action.startswith("do:"):
            reparsed = commands.parse(claimed.command_text)
            return await self._handle_do(binding, reparsed, confirmed=True)
        if claimed.action.startswith("verb:"):
            reparsed = commands.parse(claimed.command_text)
            return await self._handle_mutation_verb(binding, reparsed, confirmed=True)
        return DispatchResult(status="ok", reply="Confirmed.")

    def _cancel(self, binding: ChannelBinding, parsed: commands.ParsedCommand) -> DispatchResult:
        if not parsed.args:
            return DispatchResult(status="error", reply="Usage: /cancel <token>")
        token = parsed.args[0].strip()
        existing = self._store.get_confirmation(token)
        if existing is None or existing.binding_id != binding.id:
            return DispatchResult(status="error", reply="That confirmation token is not valid here.")
        if existing.status == "pending":
            self._store.set_confirmation_status(token, "cancelled")
        return DispatchResult(status="ok", reply="Cancelled.")

    # ── helpers ──────────────────────────────────────────────────────────────
    def _secrets(self) -> Any:
        gateway = getattr(self._service, "security", None)
        return getattr(gateway, "secrets", None) if gateway is not None else None


def _callback_url() -> str:
    return os.environ.get("HARNESS_CALLBACK_URL") or f"http://127.0.0.1:{os.environ.get('PORT', '3000')}"


def _utc_plus(seconds: int) -> str:
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _is_expired(iso: str) -> bool:
    from datetime import datetime, timezone  # noqa: PLC0415

    try:
        when = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when <= datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return True


def _attachment_context(attachments: list[Attachment]) -> str:
    """A compact, honest note about files the user attached.

    The channel never silently downloads or executes an attachment. The agent
    gets metadata and a provider reference so it can ask the user or use an
    authenticated tool; it must not invent file contents.
    """
    if not attachments:
        return ""
    lines = ["Attachments (metadata only — do not invent their contents):"]
    for attachment in attachments:
        label = attachment.name or attachment.id or "attachment"
        details: list[str] = []
        if attachment.mime_type:
            details.append(attachment.mime_type)
        if attachment.size is not None:
            details.append(f"{attachment.size} bytes")
        reference = attachment.url or attachment.provider_data.get("file_key") or attachment.provider_data.get(
            "resource_name"
        )
        if reference:
            details.append(f"ref={reference}")
        lines.append(f"- {label}" + (f": {', '.join(details)}" if details else ""))
    return "\n".join(lines)


__all__ = ["ChannelDispatcher"]
