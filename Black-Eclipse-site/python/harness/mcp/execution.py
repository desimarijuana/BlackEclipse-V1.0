"""MCP result rendering and session-expiry handling (MCP integrity extraction).

Extracted from `manager.py` (pure move) so the facade stays under its size
ratchet. `MCPManager` inherits `ExecutionMixin`; behavior and the tested call
surface are unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import redact_secrets
from .runtime import MCPToolDescriptor, _ServerRuntime

READ_EFFECT = "read"


def provider_error_line(provider_error: dict[str, Any], body: str) -> str:
    """An unmissable, explicit failure line for a provider-side error body.

    The provider's own words are preserved verbatim in `body`; only a labelled
    prefix is added so the model and UI cannot mistake it for retrieved data.
    """
    status = provider_error.get("status")
    code = provider_error.get("code")
    details = []
    if status is not None:
        details.append(f"status {status}")
    if code:
        details.append(f"code {code!r}")
    descriptor = f" ({', '.join(details)})" if details else ""
    return f"MCP reported a provider error{descriptor}:\n{body}"


class ExecutionMixin:
    """Result bounding/rendering and the honest session-expiry policy."""

    def _bound_output(
        self, rt: _ServerRuntime, text: str, data: Any
    ) -> tuple[str, Any, bool]:
        """Bound and redact result content. Returns (text, data, truncated)."""
        secret_free = redact_secrets(text or "", rt.all_secret_values())
        limit = rt.limits["outputLimitBytes"]
        encoded = secret_free.encode("utf-8", errors="replace")
        truncated = len(encoded) > limit
        if truncated:
            secret_free = encoded[:limit].decode("utf-8", errors="ignore")
        safe_data = dict(data or {})
        if truncated:
            safe_data["truncated"] = True
        return secret_free, safe_data, truncated

    async def _handle_session_expiry(
        self,
        rt: _ServerRuntime,
        descriptor: MCPToolDescriptor,
        args: dict[str, Any],
        ctx: Any,
        emit: Any,
        exc: Any,
    ) -> tuple[str, Any]:
        """Honest session-expiry policy: replay a READ once, never a write.

        A non-read call is NEVER replayed; it returns an explicit
        `outcome_uncertain` outcome that says the effect may or may not have
        happened and must be verified. A read triggers one reconnect + replay.
        """
        from .lifecycle import is_session_error

        if descriptor.effect != READ_EFFECT:
            await emit("mcp.tool.failed", {
                "serverId": rt.config.id, "tool": descriptor.original_name,
                "code": "mcp_outcome_uncertain",
            })
            data = {
                "source": {"kind": "mcp", "serverId": rt.config.id, "tool": descriptor.original_name},
                "provenance": {
                    "verification": "external",
                    "source": {"kind": "mcp", "serverId": rt.config.id, "tool": descriptor.original_name},
                    "eclipseVerified": False,
                    "outcomeUncertain": True,
                },
                "outcomeUncertain": True,
            }
            text = (
                f"MCP tool {descriptor.original_name!r} on server {rt.config.id!r} hit a session "
                "error mid-call. Because this tool has an EXTERNAL EFFECT it was NOT retried: the "
                "action may or may not have completed. Verify the outcome on the server before "
                "assuming either result."
            )
            return text, data
        if not is_session_error(str(exc)):
            raise exc
        reconnected = await self._reconnect_on_call(rt)
        if not reconnected:
            from .client import MCPClosedError

            raise MCPClosedError(
                f"MCP server {rt.config.id!r} session expired and could not be reconnected",
                code="mcp_server_unavailable",
            )
        await emit("mcp.tool.retried", {
            "serverId": rt.config.id, "tool": descriptor.original_name, "reason": "session_expired",
        })
        async with rt.semaphore:
            outcome = await rt.connection.call_tool(
                descriptor.original_name, args, timeout_ms=rt.limits["callTimeoutMs"]
            )
        # Reuse the normal result path by returning the rendered body.
        return self._render_outcome(rt, descriptor, outcome)

    def _render_outcome(self, rt: _ServerRuntime, descriptor: MCPToolDescriptor, outcome: Any) -> tuple[str, Any]:
        text, data, truncated = self._bound_output(rt, outcome.text, outcome.data)
        retrieved_at = datetime.now(timezone.utc).isoformat()
        provenance = {
            "verification": "external",
            "source": {"kind": "mcp", "serverId": rt.config.id, "tool": descriptor.original_name,
                       "transport": rt.config.transport},
            "retrievedAt": retrieved_at,
            "eclipseVerified": False,
            "truncated": truncated,
        }
        data = {**(data or {}), "provenance": provenance}
        header = (
            f"MCP result from server {rt.config.id!r}, tool {descriptor.original_name!r} "
            f"(EXTERNAL source, retrieved {retrieved_at}; NOT Eclipse-verified). "
            "Cross-check anything material against Eclipse's own data."
        )
        body = text if text else "(the server returned no text content for this call)"
        if truncated:
            body += (
                f"\n\n[TRUNCATED: output exceeded the {rt.limits['outputLimitBytes']}-byte "
                "limit and was cut off; it is incomplete.]"
            )
        provider_error = (outcome.data or {}).get("providerError")
        if provider_error is not None:
            return f"{header}\n{provider_error_line(provider_error, body)}", data
        if not outcome.ok:
            return f"{header}\nMCP reported an error:\n{body}", data
        return f"{header}\n{body}", data


__all__ = ["ExecutionMixin", "provider_error_line"]
